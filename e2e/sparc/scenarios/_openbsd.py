"""What the OpenBSD/sparc64 install, first-boot and boot scenarios share (sun4u, OpenBIOS, disk and CD-ROM
on the built-in IDE, sunhme, serial console; _sparc64.py for a QEMU of the lab's own). Attached to a
PVE VM (`--pve`, `lab.py install openbsd80-sun4u`) the VM is what PVE built from the target's profile.

The installer (bsd.rd from the install CD) is a dialogue of one-line questions on the console, each
ending in `?` and the default in brackets. installer() answers them by what they ask (INSTALL_RULES),
not by their order, so a question that a release asks or skips doesn't break it; a question no rule
knows fails the install with the question in the error.

ntpd stays off in the installed system (`ntpd_flags=NO` in /etc/rc.conf.local, what `rcctl disable
ntpd` writes, set from the installer's shell before the first boot): with a network that reaches NTP
servers, ntpd's clock slew was followed by `wd0` read timeouts in 5 of 6 boots (submodules/SPARC.md,
"sparc64", "Disk timeouts with a synced clock").
"""
import re
import time

import _netbsd
import _sparc64
from lab import QemuDied, Timeout

DEFAULTS = {**_sparc64.DEFAULTS, "NIC_NAME": "hme0", "TIMEOUT": "900"}
PROMPT = _netbsd.PROMPT  # root's ksh prompt (`#` or `<host>#`)
ANY_QUESTION = r"\? (\[[^\]\n]*\] )?$"  # a line that is an installer question
QUESTION_END = r"[?)\]] \Z"  # the output ends like a question (`?`, `[default]`, `(again)`)
IDE_TIMEOUT = r"\b(?:cd|wd)\d+\(pciide\d+:\d+:\d+\): timeout"  # the IDE driver gave up waiting
STUCK_S = 300  # s of silence after an IDE timeout that fail the install


def qemu_args(v, out):
    return _sparc64.qemu_args(v, out)


def shell(m, command, timeout=300):
    return _netbsd.shell(m, command, timeout)


def login(m, password="", timeout=900):
    _netbsd.login(m, password, timeout)


def passwd(m, user, password):
    _netbsd.passwd(m, user, password)


def install_rules(v, state):
    """[(regex, answer)] for the installer's questions; `answer` is a string or a function of the match.
    `state` keeps what was answered (the interface configured, the sets selected)."""
    nic = v.get("NIC_NAME") or "hme0"
    sets = [s for s in v.get("SETS", "").split() if s]

    def interface(mt):
        if mt.group(1) != "done" and nic not in state.setdefault("configured", []):
            state["configured"].append(nic)
            return nic
        return "done"

    def sets_location(mt):
        return "done" if state.get("sets_done") else "cd0"

    def select_sets(mt):
        i = state.setdefault("selected", 0)
        state["selected"] = i + 1
        if i < len(sets):
            return sets[i]
        state["sets_done"] = True
        return "done"

    return [
        (r"\(I\)nstall, \(U\)pgrade, \(A\)utoinstall or \(S\)hell\? $", "i"),
        (r"Choose your keyboard layout \(.*\) \[[^\]\n]*\] $", ""),
        (r"Terminal type\? \[[^\]\n]*\] $", "vt220"),
        (r"System hostname\? \(short form, e\.g\. 'foo'\) (\[[^\]\n]*\] )?$", v["HOSTNAME"]),
        (r"Network interface to configure\? \(name, lladdr, '\?', or 'done'\) \[([^\]\n]*)\] $", interface),
        (rf"IPv4 address for {nic}\? \(or 'autoconf' or 'none'\) \[[^\]\n]*\] $", v["IP"]),
        (rf"Netmask for {nic}\? \[[^\]\n]*\] $", v["NETMASK"]),
        (rf"IPv6 address for {nic}\? \(or 'autoconf' or 'none'\) \[[^\]\n]*\] $", "none"),
        # the router, name servers and domain: the first boot writes them (openbsd-firstboot.py)
        (r"Default IPv4 route\? \(IPv4 address or 'none'\) (\[[^\]\n]*\] )?$", "none"),
        (r"DNS domain name\? \(e\.g\. 'example\.com'\) \[[^\]\n]*\] $", ""),
        (r"DNS nameservers\? \(IP address list or 'none'\) \[[^\]\n]*\] $", "none"),
        (r"Password for root account\? \(will not echo\) $", v["ROOT_PASSWORD"]),
        (r"Password for root account\? \(again\) $", v["ROOT_PASSWORD"]),
        (r"Start sshd\(8\) by default\? \[\w+\] $", "yes"),
        (r"Do you expect to run the X Window System\? \[\w+\] $", "no"),
        (r"Setup a user\? \(.*\) \[\w+\] $", "no"),  # the first boot adds --user
        (r"Allow root ssh login\? \(.*\) \[[\w-]+\] $", "no"),
        (r"What timezone are you in\? \('\?' for list\) \[[^\]\n]*\] $", v.get("TIMEZONE") or "UTC"),
        (r"Which disk is the root disk\? \('\?' for details\) \[\w*\] $", v.get("DISK_NAME") or "wd0"),
        (r"Use \(A\)uto layout, \(E\)dit auto layout, or create \(C\)ustom layout\? \[\w\] $", "a"),
        (r"Encrypt the root disk with a \(p\)assphrase or \(k\)eydisk\? \[\w+\] $", "no"),
        (r"Location of sets\? \(.*\) \[\w*\] $", sets_location),
        (r"Which CD-ROM contains the install media\? \(or 'done'\) \[\w*\] $", "cd0"),
        (r"Pathname to the sets\? \(or 'done'\) \[[^\]\n]*\] $", ""),
        (r"Set name\(s\)\? \(or 'abort' or 'done'\) \[done\] $", select_sets),
        (r"Continue without verification\? \[\w+\] $", "yes"),
        (r"Time appears wrong\. Set to .*\? \[\w+\] $", "yes"),
        (r"Exit to \(S\)hell, \(H\)alt or \(R\)eboot\? \[\w+\] $", "s"),
    ]


SECRET = re.compile(r"Password for root")


def last_line(m):
    with m.cond:
        return m.text.rsplit("\n", 1)[-1]


def silent(m, seconds, poll=5):
    """True when the console prints nothing for `seconds`; False as soon as it prints again."""
    with m.cond:
        size = len(m.text)
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(poll)
        with m.cond:
            if len(m.text) != size:
                return False
    return True


def which_question(rules, line):
    """The index of the rule that answers this console line, or None."""
    return next((j for j, (rx, _) in enumerate(rules) if re.search(rx, line)), None)


def installer(m, v, timeout):
    """Answer the installer from its first question to "Exit to (S)hell, (H)alt or (R)eboot?" (answered
    with the shell). Returns the questions answered, in order.

    A question is answered only when it is the console's last line and the console has been quiet for
    a second: a kernel message in the middle of a question makes the installer's line editor draw the
    question again, and answering both copies would answer the next question too.

    An IDE timeout on the console (`cd0(pciide0:1:0): timeout`) followed by STUCK_S seconds of silence
    fails the install ("IDE timeouts"): once in five installs through PVE the CD stopped answering
    while the sets were extracted, and the installer would have waited for the whole timeout."""
    state, asked = {}, []
    rules = install_rules(v, state)
    end = time.time() + timeout
    while True:
        if m.expect_any([QUESTION_END, IDE_TIMEOUT], max(1, end - time.time())) == 1:
            m.metrics["ide_timeouts"] = m.metrics.get("ide_timeouts", 0) + 1
            if silent(m, STUCK_S):
                m.snap("stuck after IDE timeouts")
                raise AssertionError(f"IDE timeouts ({m.metrics['ide_timeouts']}) and no console output for"
                                     f" {STUCK_S}s: {last_line(m).strip()!r}")
            continue
        try:
            m.quiet(1, 30)
        except Timeout:
            continue  # output still running: not waiting for an answer
        line = last_line(m)
        i = which_question(rules, line)
        if i is None:
            if re.search(ANY_QUESTION, line):
                m.snap("unknown question")
                raise AssertionError(f"the installer asks something no rule answers: {line.strip()!r}")
            continue  # a line that only ends like a question
        with m.cond:
            m.pos = len(m.text)
        rx, answer = rules[i]
        mt = re.search(rx, line)
        reply = answer(mt) if callable(answer) else answer
        question = line.strip()
        asked.append(question)
        m.log(f"question: {question!r} -> {'***' if SECRET.search(question) else repr(reply)}")
        m.send(f"{reply}\r")
        if rx.startswith(r"Exit to"):
            return asked
        if rx.startswith(r"Set name") and reply == "done":
            m.snap("sets selected")


def disable_ntpd(m, root=""):
    """ntpd off at boot: `ntpd_flags=NO` in <root>/etc/rc.conf.local (what `rcctl disable ntpd` writes)."""
    shell(m, f"grep -q '^ntpd_flags=NO$' {root}/etc/rc.conf.local 2>/dev/null || echo ntpd_flags=NO >> {root}/etc/rc.conf.local;"
             f" cat {root}/etc/rc.conf.local")


HALT_WAIT = 300  # s; `halt -p` on the installed system ends QEMU in ~10 s


def power_off(m, v=None):
    """`sync; halt -p` and wait for the VM to end (OpenBIOS powers sun4u off)."""
    m.send("sync; halt -p\r")
    wait_off(m, HALT_WAIT)


def wait_off(m, timeout=600):
    _netbsd.wait_off(m, timeout)


def halt_installer(m):
    """From the installer's shell: unmount the new system and halt. bsd.rd's halt stops at OpenBIOS's
    `0 >` instead of powering off (submodules/SPARC.md): the VM is stopped once the disks are synced."""
    shell(m, "cd /; sync; umount -a 2>/dev/null; sync; mount")
    m.send("halt -p\r")
    try:
        i = m.expect_any([r"0 > ?$", r"halted", r"[Pp]ress any key to reboot"], 300)
        m.log(f"installer halted ({['OpenBIOS prompt', 'halted', 'press a key'][i]})")
        m.quiet(3, 60)
    except QemuDied:
        return  # it powered off after all
    except Timeout:
        pass
    m.snap("installer halted")
    m.stop()
