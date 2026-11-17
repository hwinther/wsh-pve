"""Install Solaris 10 1/13 on sun4u from its DVD with the text installer on ttya (disk and DVD on the
built-in IDE, sunhme with DHCP), until the installer reports success and tries to reboot. The disk then
boots with sparc64-boot-disk.py GUEST=solaris10 (the first boot asks for the keyboard layout: F2).

    lab.py run scenarios/solaris10-install-sparc64.py --out /mnt/sparc/runs/sol10i \
        --var ISO=/mnt/sparc/iso/sol-10-u11-ga-sparc-dvd.iso

  HOSTNAME   host name (asked only without DHCP)                        (sol10)
  ROOTPW     root password                                              (lab12345)
  DISK_GB    size of the blank disk; the default software group needs ~5.3 GB  (16)
  MEM        MiB                                                        (1024)

Needs pve-qemu-kvm with openbios-sparc64 from openbios/ (patches 0003-0011) and the cmd646 fix
(wsh/0021). About 80 min on one host core: ~13 min to the first installer screens, ~60 min of package
copying. The installer is driven by screen title (curses, terminal type DEC VT100): Esc-2 is F2, Ctrl-N/
Ctrl-P move, Return marks [X]; every other screen keeps its default. Keys typed while a screen is still
being drawn are lost, so each screen first settles.
"""
import re
import time

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args

DEFAULTS = {**BASE, "MEM": "1024", "NET": "user", "DISK_GB": "16", "HOSTNAME": "sol10",
            "ROOTPW": "lab12345", "TIMEOUT": "1200", "INSTALL_TIMEOUT": "10800", "MAX_SCREENS": "80"}

TITLE = r"^\S? ?(\S.+?) (?:─{4}|q{4})"  # a screen's title line: "─ Time Zone ────"


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<Solaris 10 1/13 SPARC DVD>")
    return sparc64_args(v, out)


def move(m, direction, n):
    for _ in range(int(n)):
        m.key("ctrl-n" if direction == "down" else "ctrl-p")


def root_password(m, v):
    m.send(v["ROOTPW"])
    m.key("tab")
    m.send(v["ROOTPW"])
    m.key("tab")


def name_service_none(m, v):
    # NIS+, NIS, DNS, LDAP, None: mark None, the last entry
    if not re.search(r"\[X\] None", m.screen_text()):
        move(m, "down", 8)
        m.send(" ")


def dhcp_yes(m, v):
    if not re.search(r"\[X\] Yes", m.screen_text()):
        move(m, "up", 1)
        m.send("\r")


def media_dvd(m, v):
    if not re.search(r"\[X\]  CD/DVD", m.screen_text()):
        move(m, "up", 1)
        m.send("\r")


def first_disk(m, v):
    if not re.search(r"\[X\] +c\d", m.screen_text()):
        m.send("\r")


# Screen title (regex on the terminal) -> what to do before F2; checked in this order
SCREENS = [
    (r"Root Password", root_password),
    (r"Name Service\s*[q─]", name_service_none),
    (r"DHCP for", dhcp_yes),
    (r"Choose Media", media_dvd),
    (r"Select Disks", first_disk),
    (r"Host Name", lambda m, v: m.send(v["HOSTNAME"])),
]


def next_screen(m, old, timeout=1200):
    """Wait until the terminal shows an installer screen other than `old` (or the copy progress)."""
    end = time.time() + timeout
    while True:
        try:
            m.quiet(3, 60)
        except Exception:  # the copy progress never goes quiet
            pass
        screen = m.screen_text()
        if "MBytes Installed" in screen:
            return screen
        if screen != old and re.search(TITLE, screen, re.M):
            return screen
        if time.time() > end:
            raise RuntimeError(f"no new installer screen after:\n{old}")
        time.sleep(2)


def run(m, v):
    t0 = time.time()
    m.expect(r"SunOS Release 5\.10", int(v["TIMEOUT"]))
    m.snap("kernel banner")
    m.expect(r"Please make a choice \(0 - 10\)", int(v["TIMEOUT"]))
    m.snap("language")
    m.send("0\r")
    m.expect(r"What type of terminal are you using", 600)
    m.snap("terminal type")
    m.send("3\r")  # DEC VT100

    screen, seen = None, {}
    for _ in range(int(v["MAX_SCREENS"])):
        screen = next_screen(m, screen)
        if "MBytes Installed" in screen:
            break
        title = re.search(TITLE, screen, re.M).group(1).strip()
        seen[title] = seen.get(title, 0) + 1
        m.snap(title)
        if seen[title] > 3:
            raise AssertionError(f"the installer stays on {title!r}")
        time.sleep(3)
        for rx, action in SCREENS:
            if re.search(rx, screen, re.M):
                action(m, v)
                break
        else:
            # a list with nothing marked (the help text itself says "mark it [X]."): mark the first entry
            if re.search(r"\[ \] \w", screen) and not re.search(r"\[X\] \w", screen):
                time.sleep(1)
                m.send("\r")
                m.quiet(2, 60)
        time.sleep(1)
        m.key("f2")
    m.metrics["questions_s"] = round(time.time() - t0, 1)
    m.snap("installing")

    i = m.expect_any([r"Solaris 10 software installation succeeded", r"panic\[cpu"], int(v["INSTALL_TIMEOUT"]))
    if i == 1:
        m.quiet(5, 300)
        m.snap("panic")
        raise AssertionError("kernel panic during the install")
    m.snap("installation succeeded")
    # boot blocks, boot archive, sync; Auto Reboot is the default: the firmware comes back, or (without
    # a client-interface reboot in the firmware) Solaris says the reboot call returned
    i = m.expect_any([r"OpenBIOS for Sparc64", r"reboot call returned"], 3600)
    m.metrics["install_s"] = round(time.time() - t0, 1)
    m.metrics["rebooted"] = i == 0
    m.snap("reboot")
    m.stop()
