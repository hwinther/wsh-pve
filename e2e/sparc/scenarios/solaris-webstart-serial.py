"""Solaris 8 (1/01, 2/02) and 9 (the original DVD, 9/05) initial install with Web Start on the serial
console, to an installed disk that is powered off. Solaris 8: the Installation CD, then Software 1 of
2 and 2 of 2 swapped in when the installer asks; Solaris 9: the DVD. Written for `lab.py install`
of sol8-ss20, sol9-ss20, sol8-ss5 and sol9-ss5 (attach mode, a PVE VM); the VM needs
`auto-boot?=false` in OpenBIOS (install.py sets `-prom-env` for the install phase only, targets.py "prom_env"):

  1. Solaris 8: the Installation CD's mini-root asks to format the boot disk and put a swap slice at
     its start, copies a mini-root there and reboots with `reboot -- <that slice>`. OpenBIOS drops
     the boot string, so with auto-boot? true it boots slice a, finds nothing (`ufsboot: cannot
     determine filesystem type of root device`) and powers off; with false it stops at `0 >` and
     this scenario boots slice b by path. Solaris 9: the DVD asks for the language, the locale and
     the terminal type, and runs Web Start from the DVD.
  2. Web Start runs in command line mode (no framebuffer): the system identification questions
     (host name, address, netmask, IPv6, 9: default route and Kerberos, name service, time zone,
     root password), then the installer's: 9: no automatic reboot or eject; media (CD), 8: "Please
     insert the Solaris 8 Software 1 of 2 CD"; Custom Install (8's Default Install also wants the
     Documentation and Computer Systems Supplement CDs), the C locale, no extra CDs or products,
     32-bit, the software group (SOFTWARE), its default packages, auto-layout on c0t3d0. Solaris 8
     asks for Software 2 of 2 after the first CD's packages.
  3. At the end it asks for Return to reboot; the reboot stops at `0 >` and this scenario powers the
     VM off there (`power-off`). The first boot is solaris-firstboot.py's.

Variables:
  HOSTNAME, IP, NETMASK   the system identification answers        (solaris, 10.0.2.15, 255.255.255.0)
  TIMEZONE                a file under /usr/share/lib/zoneinfo     (MET)
  ROOT_PASSWORD           set by the installer (doesn't echo)       (none)
  SOFTWARE                the software group: 1 Entire Plus OEM, 2 Entire, 3 Developer, 4 End User,
                          5 Core                                   (2)
  SWAPS                   "scsi6=local:iso/<Software 1 of 2> scsi6=local:iso/<Software 2 of 2>": the
                          CDs, in order, for the "Please insert" prompts (install.py passes them)
  PROMPT_TIMEOUT          seconds to wait for the next prompt      (3600: package installation)

Prompts are matched on the last lines of the screen, in the order of prompts(); an unknown prompt
fails the run with the screen in the evidence rather than guessing.
"""
import re
import time

from _sparc32 import DEFAULTS as BASE, ESP, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "HOSTNAME": "solaris", "IP": "10.0.2.15", "NETMASK": "255.255.255.0",
            "TIMEZONE": "MET", "ROOT_PASSWORD": "", "SOFTWARE": "2", "SWAPS": "", "PROMPT_TIMEOUT": "3600"}
# The end of a line that waits for input: "... [y,n,?,q]", "[n]:", "(y/n):", "(y/n)", "[]", "-->",
# "[?]", and on Solaris 9 the same followed by a key hint: "<Press ENTER to continue> {"!" exits}".
# A closing parenthesis counts only after a choice like "(y/n)": the line the installer prints when
# it starts a CD's packages, "Installing Solaris 8 packages (part 2)", stays on the screen for a while
# before the progress bar and is no prompt.
HINT = r'\s*\{"[^{}]*\}'
PROMPT_END = r"(?:[:?\]>]|\[[^\]]*\]|\([a-z]+(?:/[a-z]+)+\))(?:" + HINT + r")?\s*$"
# Prompts without such an ending: Solaris 9 9/05's license question ("Enter 'y' to accept the license
# agreement. Enter 'n' to decline the license agreement and exit the install.")
PROMPT_END_BARE = r"exit the install\.\s*$"
# "Please insert the Solaris 8 Software 1 of 2 CD." (before the install), "Please insert the CD for
# Solaris 8 Software 2 of 2 (SPARC Platform Edition)." (after the first CD's packages); 8 2/02 asks
# for the first one as "Please insert the first Solaris Software disc from which you will install ...",
# the second as "Please insert the CD/DVD for Solaris 8 Software 2 of 2 (2/02 SPARC Platform Edition)."
INSERT = (r"Please insert the (?:CD for |CD/DVD for )?Solaris \d+ (?P<what>Software \d of 2)"
          r"|Please insert the (?P<which>\w+) Solaris Software disc")
CD_ROW = r"^\s*\[([X\- ])\]\s+(\d+)\s+(\S.*?)\s{2,}"


def qemu_args(v, out):
    return sparc32_args(v, out)


def tail(screen, n=6):
    """The last n non-empty lines of the screen, joined, whitespace collapsed (prompts wrap), without
    Solaris 9's key hint after a prompt (`{"<" goes back, "!" exits}`)."""
    lines = [x for x in screen.splitlines() if x.strip()][-n:]
    return re.sub(r"\s+", " ", re.sub(HINT, "", " ".join(lines))).strip()


def waits_for_input(screen):
    """Whether the screen's last non-empty line ends like a prompt."""
    last = next((x for x in reversed(screen.splitlines()) if x.strip()), "")
    return bool(re.search(PROMPT_END, last) or re.search(PROMPT_END_BARE, last))


def wait_prompt(m, since, timeout):
    """Wait until output came after serial cursor `since` and the console settled on a prompt."""
    end = time.time() + timeout
    while True:
        m.quiet(3, timeout)
        screen = m.screen_text()
        if m.serial_cursor() > since and waits_for_input(screen):
            return screen
        if time.time() > end:
            raise RuntimeError(f"no prompt within {timeout}s; the screen:\n{screen}")
        time.sleep(2)


def answer(m, text, title=None):
    """Type the answer; returns the serial cursor that output must pass before the next prompt
    counts (the echo of the answer and its line end don't)."""
    if title:
        m.snap(title)
    cursor = m.serial_cursor()
    m.send(text + "\r")
    return cursor + len(text) + 6


class Installer:
    def __init__(self, m, v):
        self.m, self.v = m, v
        self.swaps = [tuple(x.split("=", 1)) for x in v["SWAPS"].split()]
        self.cd, self.mark = None, None  # the CD whose products are on screen, and its [X]/[-]/[ ]

    def insert(self, screen):
        found = list(re.finditer(INSERT, tail(screen, 8)))[-1]
        what = found["what"] or f"the {found['which']} Software disc"
        if not self.swaps:
            raise RuntimeError(f"the installer asks for {what}; SWAPS has no more CDs")
        drive, volume = self.swaps.pop(0)
        self.m.change_medium(drive, volume)
        time.sleep(5)  # the target notices the new medium (unit attention) before it is read
        return ""

    def finished(self, screen):
        """"Enter n when finished [n]": the CD list or one CD's product list, whichever header came
        last on the screen (a long product list scrolls its header off)."""
        # Solaris 8: "Select the CDs and products you would like to install."; 9: "Select the
        # products you would like to install." (and the same per-product "Products marked ...")
        cds = max(screen.rfind("Select the CDs and products"), screen.rfind("Select the products you would like"))
        if cds > screen.rfind("Products marked with an [X]"):
            return self.cd_list(screen[cds:])
        return self.products(screen)

    def cd_list(self, screen):
        """The CDs (Documentation, Software 2 of 2, Supplement): open each selected one to deselect
        it. Software 2 of 2 follows the software group, whatever its row says."""
        for mark, num, name in re.findall(CD_ROW, screen, re.M):
            if mark != " " and not re.search(r"Software \d of \d", name):
                self.cd, self.mark = num, mark
                return num
        return "n"

    def products(self, screen):
        """One CD's products: toggle the CD until its own row is [ ] (a partly selected one, [-],
        becomes [X] first), then back to the CD list."""
        if self.cd is None:
            raise RuntimeError(f"a product list without a CD chosen:\n{screen}")
        return self.cd if self.mark != " " else "n"

    def track(self, screen):
        """Note the current CD's mark whenever its row is on the screen (it scrolls off on long lists)."""
        if self.cd is not None:
            rows = [mk for mk, num, _ in re.findall(CD_ROW, screen, re.M) if num == self.cd]
            if rows:
                self.mark = rows[-1]

    def locale(self, screen, what):
        rx = r"(\d+)\s+POSIX\b" if what == "region" else r"(\d+)\.\s+English \(POSIX C\)"
        found = re.search(rx, screen)
        if not found:
            raise RuntimeError(f"no POSIX {what} on the screen:\n{screen}")
        return found.group(1)


def prompts(inst, v):
    """(regex on the last lines, answer: a string or a function of the screen, step title or None)."""
    return [
        # system identification (command line mode)
        (r"<Press Return to continue>$", "", "Web Start command line"),
        (r"Is this machine networked \(y/n\) \[n\]\?$", "y", None),
        (r"configure using DHCP \[n\]\?$", "n", None),
        (r"Enter host name \[\]:$", v["HOSTNAME"], None),
        (r"Enter this machine's IP Address \[\]:$", v["IP"], None),
        (r"Enter the subnet netmask \[[\d.]*\]:$", v["NETMASK"], None),
        (r"Enable IPv6 \[n\]:$", "n", None),
        # Solaris 9: the default route (1 = find one: router discovery; it has no "none") and Kerberos
        (r"your router discovery method \[1\]:$", "1", None),
        (r"The route could not be detected at this time\..*1\. Accept 2\. Cancel .*\[1\]$", "1", None),
        (r"Kerberos.*\[n\]\s*[:?]?$", "n", None),
        (r"name service you would like \[\d\]:$", "5", "name service: none"),
        (r"how you would like to specify the time zone \[\d\]:$", "3", None),
        (r"time zone file or '-' for a list of files \[-\]:$", v["TIMEZONE"], None),
        (r"Do you want to use this date and time \(y/n\) \[y\]\?$", "y", None),
        (r"Enter the root password again \[\]:$", v["ROOT_PASSWORD"], None),  # doesn't echo
        (r"Enter the root password \[\]:$", v["ROOT_PASSWORD"], None),
        (r"Enter 'y' to apply these values .*\(y/n\):$", "y", "system identification"),
        # the installer
        (r"<Press ENTER to continue>$", "", None),
        # Solaris 9's installer options: no reboot (it ends at a prompt instead) and no eject
        (r"Reboot automatically after software installation \[y\]\?$", "n", None),
        (r"Eject a CD/DVD automatically after software installation \[y\]\?$", "n", None),
        (r"Enter 'y' if this is correct, or 'n' to make changes \[y\]$", "y", "installer options"),
        (r"Media \[1\]:$", "1", None),
        (r"(?:" + INSERT + r").*\[\]$", inst.insert, "insert a CD"),
        (r"type of install you would like \[1\]:$", "2", "custom install"),
        (r"Enter n when finished\. \[n\]$", "", "regions"),  # the regions: English only
        (r"enter n to use the default\. \[n\]$", lambda s: inst.locale(s, "region"), None),
        (r"desired locale to be used after the system has been installed, or enter n to choose a new region\. \[n\]$",
         lambda s: inst.locale(s, "locale"), "locale C"),
        (r"Toggle .* \[n\]\?$", "y", None),
        (r"\[n To Finish\]-->$", "n", None),
        # Solaris 9 9/05: the license after the installer options (paged above, then this)
        (r"Enter 'y' to accept the license agreement\..* exit the install\.$", "y", "license agreement"),
        (r"Enter n when finished \[n\]$", inst.finished, "CDs and products"),
        (r"Web Start Ready product scan location \[1\]:$", "1", None),
        (r"installed with 32-bit support only\. Enter the number corresponding to your choice \[2\]$", "2",
         "32-bit only"),
        (r"desired Solaris software group \[\d\]:$", v["SOFTWARE"], "software group"),
        (r"Default Packages or Custom Packages \[1\]$", "1", None),
        (r"Layout file systems on disk c0t3d0 \(bootdisk\) \(y/n\) \[y\]\?$", "y", None),
        (r"Enter y to preserve data or n to skip data preservation\. \[n\]$", "n", None),  # Solaris 9
        (r"or 'Done' to proceed with the install \[\d\]:$", "", "file system layout"),  # Done: 3 (8), 4 (9)
        (r"Enter 'y' to accept these values and start the installation.*\(y/n\):$", "y", "start the installation"),
        # after each CD's packages (the default is Done), the media for Software 2 of 2 ("Media [1]:"
        # above), and the end
        (r"information, or enter \d to continue \[\d\]:$", "", "installation details"),
        # 8 2/02, after each CD after the first went in: "Ready to Install 1. Install Now 2. Start
        # Over ..." (anchored at the end: an answered copy, "... [1]? 1", is never matched again)
        (r"Ready to Install .*1\. Install Now .*What would you like to do \[1\]\?$", "1", "install the next CD"),
        # Solaris 9: a summary that moves on by itself after 30-90 s
        (r"Enter 'p' to pause\. Enter 'c' to continue\. \[c\]$", "c", None),
        (r"<Press Return to reboot the system>(?: \[\])?$", "", "reboot"),
    ]


def mini_root(m):
    """The Solaris 8 Installation CD: the boot disk becomes a swap slice at cylinder 0 (the default
    512 MB) with a mini-root on it, and the reboot into it ends at the OpenBIOS prompt (auto-boot?
    false), where the mini-root's slice is booted by path."""
    answer(m, "y", "format the boot disk")
    for rx, reply, title in [(r"Enter a swap slice size between .*\[\?\]", "", "swap slice size"),
                             (r"Can the swap slice start at the beginning of the disk\s+\[y,n,\?,q\]", "y", None),
                             (r"Is this OK\s+\[y,n,\?,q\]", "y", "swap slice")]:
        m.expect(rx, 900)
        m.quiet(1, 60)
        answer(m, reply, title)
    m.expect(r"Rebooting to continue the installation", 1800)
    m.expect(r"0 >", 300)
    m.snap("OpenBIOS prompt after the mini-root copy")
    m.send(f"boot {ESP}/sd@3,0:b\r")
    m.expect(r"SunOS Release 5\.\d", 600)


def run(m, v):
    prom_boot(m, v, "cdrom")
    m.expect(r"SunOS Release 5\.\d", 900)
    m.snap("kernel banner")
    # Up to command line mode: the Solaris 8 Installation CD's mini-root first; the Solaris 9 DVD
    # runs Web Start from the DVD after asking for the language, the locale (a paged list, 0 is
    # English C) and the terminal type
    while True:
        # 8 1/01 asks "... c0t3d0? [y,n,?,q]", 8 2/02 without the question mark
        i = m.expect_any([r"Do you want to format /dev/dsk/c0t3d0\??\s+\[y,n,\?,q\]", r"Select a Language",
                          r"Please make a choice \(0 - \d\d+\)", r"What type of terminal are you using",
                          r"Running in command line mode"], 1800)
        m.quiet(1, 60)
        if i == 0:
            mini_root(m)
        elif i in (1, 2):
            answer(m, "0", ["", "language", "locale"][i])
        elif i == 3:
            answer(m, "3", "terminal type")  # DEC VT100
        else:
            break

    inst = Installer(m, v)
    table = prompts(inst, v)
    since = m.serial_cursor()
    timeout = int(v["PROMPT_TIMEOUT"])
    while True:
        screen = wait_prompt(m, since, timeout)
        inst.track(screen)
        text = tail(screen)
        for rx, reply, title in table:
            if re.search(rx, text):
                break
        else:
            m.snap("unknown prompt")
            raise RuntimeError(f"unknown prompt: {text[-300:]}")
        if callable(reply):
            reply = reply(screen)
        since = answer(m, reply, title)
        if title == "reboot":
            break
    if inst.swaps:
        raise RuntimeError(f"the installer never asked for {len(inst.swaps)} of the CDs in SWAPS")
    # The reboot stops at the OpenBIOS prompt (auto-boot? false): power off there; the first boot is
    # solaris-firstboot.py's
    m.expect(r"0 >", 900)
    m.snap("OpenBIOS prompt after the installation")
    m.send("power-off\r")
    m.wait_exit(120)
