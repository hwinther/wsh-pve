"""What the OpenBSD install, first-boot and boot scenarios share: OpenBSD/sparc64 (sun4u, OpenBIOS, disk
and CD-ROM on the built-in IDE, sunhme; _sparc64.py for a QEMU of the lab's own) and OpenBSD/sparc
(ARCH=sparc: sun4m, disk on SCSI target 3, CD-ROM on 6, lance; _sparc32.py), serial console.
Attached to a PVE VM (`--pve`, `lab.py install openbsd80-sun4u`, `openbsd59-ss5`) the VM is what PVE
built from the target's profile, and ARCH comes from its config.

The installer (bsd.rd from the install CD) is a dialogue of one-line questions on the console, each
ending in `?` and the default in brackets. installer() answers them by what they ask (INSTALL_RULES),
not by their order, so a question that a release asks or skips doesn't break it; a question no rule
knows fails the install with the question in the error.

OpenBSD 5.9 (the last release with the sparc port) asks some questions in other words than 8.0
(`Which network interface do you wish to configure?`, `(or 'dhcp' or 'none')`, `(or 'rtsol' or
'none')`, a domain example `'bar.com'`) and has no "Exit to (S)hell" question: its installer ends
with "CONGRATULATIONS!" at the shell. The rules know both. SETS_CD and SETS_PATH say where the sets
are (8.0: the install CD, cd0, the default path; 5.9 on sun4m: the sets CD on target 5, cd0, `/`).

ntpd: OpenBSD/sparc64 keeps it on, as the installer leaves it. The `wd0` read timeouts that followed
ntpd's start on sun4u were a lost interrupt in QEMU's sabre host bridge (a NIC interrupt replaced the
outstanding IDE request), fixed by pve-qemu `wsh/0045` (pve-qemu-kvm 11.1.3-2+wsh30; submodules/SPARC.md,
"sparc64", "Cause: the sabre lost a request"). OpenBSD/sparc (sun4m) still turns it off (`ntpd_flags=NO`
in /etc/rc.conf.local, what `rcctl disable ntpd` writes, set from the installer's shell before the
first boot): not tried with ntpd on there. NTPD (on | off) overrides the choice by ARCH.
"""
import re
import time

import _netbsd
import _sparc32
import _sparc64
from lab import QemuDied, Timeout

NICS = {"sparc64": "hme0", "sparc": "le0"}
DISKS = {"sparc64": "wd0", "sparc": "sd0"}


def defaults(arch):
    """The scenario's DEFAULTS for ARCH (sparc64 | sparc): the machine's variables, then these."""
    # sparc: -nographic, as qemu-server runs a sparc32 VM with a serial display (_sparc32.py, NOGRAPHIC)
    base = _sparc64.DEFAULTS if arch == "sparc64" else {**_sparc32.DEFAULTS, "VGA": "none", "NOGRAPHIC": "1"}
    return {**base, "ARCH": arch, "NIC_NAME": "", "DISK_NAME": "", "TIMEOUT": "900"}


DEFAULTS = defaults("sparc64")
PROMPT = _netbsd.PROMPT  # root's ksh prompt (`#` or `<host>#`)
# a line that is an installer question: `?`, an optional `(hint)`, an optional `[default]`
ANY_QUESTION = r"\? (\([^\n]*\) )?(\[[^\]\n]*\] )?$"
QUESTION_END = r"[?)\]] \Z"  # the output ends like a question (`?`, `[default]`, `(again)`)
IDE_TIMEOUT = r"\b(?:cd|wd)\d+\(pciide\d+:\d+:\d+\): timeout"  # the IDE driver gave up waiting
STUCK_S = 300  # s of silence after an IDE timeout that fail the install


def qemu_args(v, out):
    """The lab's own QEMU. ARCH=sparc in a scenario whose DEFAULTS are sparc64's (first boot, boot
    check): the sun4m variables it lacks are added, and QEMU, BIOS and MACHINE still at their sparc64
    defaults (which can't run sun4m) take the sun4m ones, MEM too when it is 512 on an SS-5 (its
    limit is 256); pass MACHINE=SS-20 MEM=512 for an SS-20."""
    if v.get("ARCH") == "sparc":
        sparc = defaults("sparc")
        for k, val in sparc.items():
            if k not in v or (k in ("QEMU", "BIOS", "MACHINE") and v[k] == _sparc64.DEFAULTS[k]):
                v[k] = val
        if v["MACHINE"] == "SS-5" and v["MEM"] == _sparc64.DEFAULTS["MEM"]:
            v["MEM"] = sparc["MEM"]
        return _sparc32.qemu_args(v, out)
    return _sparc64.qemu_args(v, out)


def nic(v):
    """The guest's interface: NIC_NAME, else hme0 (sparc64) or le0 (sparc)."""
    return v.get("NIC_NAME") or NICS[v.get("ARCH") or "sparc64"]


def disk(v):
    """The guest's disk: DISK_NAME, else wd0 (sparc64, IDE) or sd0 (sparc, SCSI)."""
    return v.get("DISK_NAME") or DISKS[v.get("ARCH") or "sparc64"]


def shell(m, command, timeout=300):
    return _netbsd.shell(m, command, timeout)


def login(m, password="", timeout=900):
    _netbsd.login(m, password, timeout)


def passwd(m, user, password):
    _netbsd.passwd(m, user, password)


def install_rules(v, state):
    """[(regex, answer)] for the installer's questions; `answer` is a string or a function of the match.
    `state` keeps what was answered (the interface configured, the sets selected)."""
    nic_ = nic(v)
    sets = [s for s in v.get("SETS", "").split() if s]
    cd = v.get("SETS_CD") or "cd0"

    def interface(mt):
        if mt.group(1) != "done" and nic_ not in state.setdefault("configured", []):
            state["configured"].append(nic_)
            return nic_
        return "done"

    def sets_location(mt):
        return "done" if state.get("sets_done") else cd

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
        # 8.0: "Network interface to configure? (name, lladdr, '?', or 'done') [hme0]"; 5.9: "Which
        # network interface do you wish to configure? (or 'done') [le0]"
        (r"(?:Network interface to configure|Which network interface do you wish to configure)\?"
         r" \((?:name, lladdr, '\?', )?or 'done'\) \[([^\]\n]*)\] $", interface),
        (rf"IPv4 address for {nic_}\? \(or '(?:autoconf|dhcp)' or 'none'\) \[[^\]\n]*\] $", v["IP"]),
        (rf"Netmask for {nic_}\? \[[^\]\n]*\] $", v["NETMASK"]),
        (rf"IPv6 address for {nic_}\? \(or '(?:autoconf|rtsol)' or 'none'\) \[[^\]\n]*\] $", "none"),
        # the router, name servers and domain: the first boot writes them (openbsd-firstboot.py)
        (r"Default IPv4 route\? \(IPv4 address or '?none'?\) (\[[^\]\n]*\] )?$", "none"),
        (r"DNS domain name\? \(e\.g\. '[\w.]+'\) \[[^\]\n]*\] $", ""),
        (r"DNS nameservers\? \(IP address list or 'none'\) \[[^\]\n]*\] $", "none"),
        (r"Password for root account\? \(will not echo\) $", v["ROOT_PASSWORD"]),
        (r"Password for root account\? \(again\) $", v["ROOT_PASSWORD"]),
        (r"Start sshd\(8\) by default\? \[\w+\] $", "yes"),
        (r"Do you expect to run the X Window System\? \[\w+\] $", "no"),
        (r"Setup a user\? \(.*\) \[\w+\] $", "no"),  # the first boot adds --user
        (r"Allow root ssh login\? \(.*\) \[[\w-]+\] $", "no"),
        (r"What timezone are you in\? \('\?' for list\) \[[^\]\n]*\] $", v.get("TIMEZONE") or "UTC"),
        (r"Which disk is the root disk\? \('\?' for details\) \[\w*\] $", disk(v)),
        (r"Use \(A\)uto layout, \(E\)dit auto layout, or create \(C\)ustom layout\? \[\w\] $", "a"),
        (r"Encrypt the root disk with a \(p\)assphrase or \(k\)eydisk\? \[\w+\] $", "no"),
        (r"Location of sets\? \(.*\) \[\w*\] $", sets_location),
        (r"Which CD-ROM contains the install media\? \(or 'done'\) \[\w*\] $", cd),
        (r"Pathname to the sets\? \(or 'done'\) \[[^\]\n]*\] $", v.get("SETS_PATH", "")),
        # a directory without the release's INSTALL.<arch> (the sets CD made on the node has it,
        # answer_media.openbsd_sets: the sets in its root, so SETS_PATH `/`)
        (r"INSTALL\.\w+ not found\. Use sets found here anyway\? \[\w+\] $", "yes"),
        (r"Set name\(s\)\? \(or 'abort' or 'done'\) \[done\] $", select_sets),
        (r"Continue without verification\? \[\w+\] $", "yes"),
        (r"Time appears wrong\. Set to .*\? \[\w+\] $", "yes"),
        (EXIT_QUESTION, "s"),
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


CONGRATULATIONS = r"CONGRATULATIONS! Your OpenBSD install has been successfully completed!"
EXIT_QUESTION = r"Exit to \(S\)hell, \(H\)alt or \(R\)eboot\? \[\w+\] $"


def installer(m, v, timeout):
    """Answer the installer from its first question to "Exit to (S)hell, (H)alt or (R)eboot?" (answered
    with the shell; 8.0), or to "CONGRATULATIONS!" (5.9, which then leaves its shell). Returns the
    questions answered, in order.

    A question is answered only when it is the console's last line and the console has been quiet for
    a second: a kernel message in the middle of a question makes the installer's line editor draw the
    question again, and answering both copies would answer the next question too.

    An IDE timeout on the console (`cd0(pciide0:1:0): timeout`) followed by STUCK_S seconds of silence
    fails the install ("IDE timeouts"): before pve-qemu `wsh/0045` the CD stopped answering once in
    five installs through PVE while the sets were extracted (the sabre's lost interrupt), and the
    installer would have waited for the whole timeout. Kept so that a regression fails clearly."""
    state, asked = {}, []
    rules = install_rules(v, state)
    end = time.time() + timeout
    while True:
        seen = m.expect_any([QUESTION_END, IDE_TIMEOUT, CONGRATULATIONS], max(1, end - time.time()))
        if seen == 2:
            m.snap("install complete")
            # 8.0 asks "Exit to (S)hell, ..." after it (answered with the shell); 5.9 is at its shell
            with m.cond:
                pos = m.pos
            if m.expect_any([EXIT_QUESTION, PROMPT], 120) == 1:
                with m.cond:
                    m.pos = pos  # the caller waits for the prompt
                return asked
            m.quiet(1, 30)
            asked.append(last_line(m).strip())
            m.log(f"question: {asked[-1]!r} -> 's'")
            m.send("s\r")
            return asked
        if seen == 1:
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
        if rx == EXIT_QUESTION:
            return asked
        if rx.startswith(r"Set name") and reply == "done":
            m.snap("sets selected")


def ntpd_on(v):
    """Whether the installed system runs ntpd: NTPD (on | off), else on for sparc64 and off for sparc."""
    return (v.get("NTPD") or ("on" if (v.get("ARCH") or "sparc64") == "sparc64" else "off")) == "on"


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
