"""Solaris 2.x initial install over the serial console, from boot CD to an installed disk that is
powered off. Tested with 2.6 (5/98) and 2.5.1 (11/97).

    lab.py run scenarios/solaris-install-serial.py --out /srv/sparc/runs/s26 \
        --var ISO=/srv/sparc/solaris_2.6_598_sparc.iso \
        --var TEMPLATE=/srv/sparc/disks/sparc-SUN2.9G.raw.template.xz

    # 2.5.1 (and 2.4) boot only from a CD that answers as a disk, and 2.4 only from a Sun PROM:
    lab.py run scenarios/solaris-install-serial.py --out /srv/sparc/runs/s251 \
        --var ISO=/srv/sparc/solaris_2.5.1_1197.iso --var CDROM_AS=hd --var BIOS=ss5.bin \
        --var TEMPLATE=/srv/sparc/disks/sparc-SUN2.9G.raw.template.xz

With no framebuffer (VGA=none, the default here) the installer runs in text mode on ttya; with one it
starts the OpenWindows installer there instead. The disk must carry a Sun label: the installer lists
only labelled disks (the SUN2.9G template shows up as c0t3d0, 2775 MB).

The installer is driven by screen title, not by a fixed sequence, because the releases ask different
questions in a different order (2.5.1 has no language/locale prompt but asks for a system type).

Keys on the installer's curses screens (terminal type DEC VT100): Esc-<n> for F<n>, Ctrl-N / Ctrl-P to
move (the arrow keys only beep), Return to mark [X].
"""
import re
import time

from _sparc32 import DEFAULTS as BASE, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "HOSTNAME": "solaris", "IP": "10.0.2.15",
            "REGION_UP": "3", "ZONE_DOWN": "5",  # from United States up to Europe, then Middle Europe (MET)
            "SOFTWARE_UP": "0"}  # 0 = End User System Support, 3 = Entire Distribution


def qemu_args(v, out):
    return sparc32_args(v, out)


def move(m, direction, n):
    for _ in range(int(n)):
        m.key("ctrl-n" if direction == "down" else "ctrl-p")


def mark(m, direction, n):
    """Move the highlight and mark the option [X]."""
    move(m, direction, n)
    m.send("\r")


def software(m, v):
    if v["SOFTWARE_UP"] != "0":
        mark(m, "up", v["SOFTWARE_UP"])


def disks(m, v):
    m.send("\r")  # the first entry, c0t3d0; a CD that answers as a disk is listed too (c0t6d0)
    m.expect(r"\[X\] c0t3d0", 60, screen=True)


def no_auto_reboot(m, v):
    # With the CD first in the boot order an automatic reboot only starts the installer again.
    mark(m, "down", 1)


# Screen title (regex on the terminal screen) -> what to do before F2. Checked in this order, so a
# more specific title comes before a shorter one that also matches it.
SCREENS = [
    (r"Name Service\s*[q─]|Name service\s*$", lambda m, v: mark(m, "down", 3)),  # NIS+ -> None
    (r"Host Name", lambda m, v: m.send(v["HOSTNAME"])),
    (r"IP Address", lambda m, v: m.send(v["IP"])),
    (r"Regions", lambda m, v: mark(m, "up", v["REGION_UP"])),
    (r"Time zones", lambda m, v: mark(m, "down", v["ZONE_DOWN"])),
    (r"Select Software|^\S Software [q─]", software),
    (r"Select Disks|^\S Disks [q─]", disks),
    (r"Reboot After Installation|Begin Installing Solaris", no_auto_reboot),
    # Everything else: the defaults are what we want (Networked yes, subnet no, date, system type
    # standalone, no client services, English only, don't preserve data, auto-layout, no remote
    # mounts, the profile, the boot device warning).
]
TITLE = r"^\S (.+?) (?:─{4}|q{4})"  # an installer screen's title line: "─ Host Name ────"
LAST = r"Reboot After Installation|Begin Installing Solaris"


def next_screen(m, old, timeout=600):
    """Wait until the terminal shows an installer screen other than `old`, and it has settled."""
    end = time.time() + timeout
    while True:
        m.quiet(2, timeout)
        screen = m.screen_text()
        if screen != old and re.search(TITLE, screen, re.M):
            return screen
        if time.time() > end:
            raise RuntimeError(f"the installer didn't move on from:\n{old}")
        time.sleep(1)


def run(m, v):
    prom_boot(m, v, "cdrom")
    m.expect(r"SunOS Release 5\.\d", 900)
    m.snap("kernel banner")
    while True:  # the prompts before the curses screens
        i = m.expect_any([r"Select a Language", r"Type a number and press Return or Enter \[0\]",
                          r"What type of terminal are you using"], 900)
        m.snap(["Select a Language", "Select a Locale", "terminal type"][i])
        if i == 2:
            m.send("3\r")  # DEC VT100
            break
        m.send(["0\r", "\r"][i])

    screen = None
    while True:
        screen = next_screen(m, screen)
        title = re.search(TITLE, screen, re.M).group(1)
        m.snap(title)
        for rx, action in SCREENS:
            if re.search(rx, screen, re.M):
                action(m, v)
                break
        m.key("f2")
        if re.search(LAST, screen):
            break

    m.expect(r"Solaris Initial Install|MBytes Installed", 600, screen=True)
    m.snap("installing")
    # Package copy, then (2.6) patches and the JumpStart finish scripts, then a root shell.
    m.expect(r"Executing JumpStart postinstall phase|Customizing system files", 7200)
    m.expect(r"\n#\s*$", 1800)
    m.quiet(5, 600)
    m.snap("installation finished")
    power_off(m, "halt")
