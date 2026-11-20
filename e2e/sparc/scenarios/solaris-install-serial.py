"""Solaris 2.x initial install over the serial console, from boot CD to an installed disk that is
powered off. Tested with 2.6 (5/98), 2.5.1 (11/97), 2.5 (HW 1/96), 2.4 (HW 3/95), 2.3 Edition II
and 2.2 (their older sysidtool screens and Quick Install: old_install(); it ends at the PROM's `ok`,
or OpenBIOS's `0 >`; 2.2 and, under OpenBIOS, 2.3 and 2.4 need openbios patches 0019-0022).

    lab.py run scenarios/solaris-install-serial.py --out /mnt/runs/s26 \
        --var ISO=/mnt/os/iso/solaris_2.6_598_sparc.iso \
        --var TEMPLATE=/mnt/os/disks/sparc-SUN2.9G.raw.template.xz

    # 2.5.1 (and 2.4) boot only from a CD that answers as a disk, and 2.4 only from a Sun PROM:
    lab.py run scenarios/solaris-install-serial.py --out /mnt/runs/s251 \
        --var ISO=/mnt/os/iso/solaris_2.5.1_1197.iso --var CDROM_AS=hd --var BIOS=ss5.bin \
        --var TEMPLATE=/mnt/os/disks/sparc-SUN2.9G.raw.template.xz

With no framebuffer (VGA=none, the default here) the installer runs in text mode on ttya; with one it
starts the OpenWindows installer there instead. The disk must carry a Sun label: the installer lists
only labelled disks (the SUN2.9G template shows up as c0t3d0, 2775 MB).

On sun4u (sol7-sun4u: ARCH sparc64 from the VM's config) the same answers with the IDE disk as
DISK=c0t0d0 (Sun-labelled too), F2 again on a screen that doesn't move on (KEY_RETRY), and at the end
`halt` to OpenBIOS's `0 >`, where the VM is stopped (halt_sun4u).

The installer is driven by screen title, not by a fixed sequence, because the releases ask different
questions in a different order (2.5.1 has no language/locale prompt but asks for a system type).

Keys on the installer's curses screens (terminal type DEC VT100): Esc-<n> for F<n>, Ctrl-N / Ctrl-P to
move (the arrow keys only beep), Return to mark [X].
"""
import re
import time

from _sparc32 import DEFAULTS as BASE, power_off, prom_boot, qemu_args as sparc32_args
from lab import Timeout

DEFAULTS = {**BASE, "VGA": "none", "HOSTNAME": "solaris", "IP": "10.0.2.15",
            "REGION_UP": "3", "ZONE_DOWN": "5",  # from United States up to Europe, then Middle Europe (MET)
            "REGION": "Europe", "ZONE": "Middle Europe",  # the same by name (2.3's menus)
            "SOFTWARE_UP": "0",  # 0 = End User System Support, 3 = Entire Distribution
            "FINISH_TIMEOUT": "1800",  # s from the postinstall phase to the root shell
            # s from the kernel banner to the first prompt (35-55 s in the lab); a boot that hangs
            # there (QEMU's ESP deadlock: the CPU spins, no more disk I/O) fails with EARLY_HANG
            "FIRST_PROMPT_TIMEOUT": "300",
            "DISK": "c0t3d0",  # the boot disk as Solaris names it (sun4u's IDE disk: c0t0d0)
            "KEY_RETRY": "0"}  # s on an unchanged screen before F2 goes again (press_on); 0 = never
# In the status of a boot that never reached the installer: nothing is on the disk yet, and
# `lab.py install` boots once more (the targets' install "retry_on")
EARLY_HANG = "before the installer"
# A kernel panic while the packages are copied (sol7-sun4u: `panic[cpu0]/thread=...: segkp_badop`)
PANIC = r"panic\[cpu\d+\]"


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
    # The installer selects the boot disk by itself when the PROM names it (OpenBIOS with a working
    # `disk` alias, "c0t3d0 ... boot disk"); otherwise mark the first entry. A CD that answers as a
    # disk is listed too (c0t6d0).
    disk = re.escape(v["DISK"])
    if not re.search(rf"\[X\] {disk}", m.screen_text()):
        m.send("\r")
    m.expect(rf"\[X\] {disk}", 60, screen=True)


def date(m, v):
    # Solaris 2.4 shows a year after 1999 as 19xx ("Year (4 digits) : 1912" in 2026) and then refuses
    # it ("Unable to convert given date"), back to the time zone. The Year field has the focus with
    # its value highlighted: typing replaces it. 2.5.1 and later take the year they show.
    year = re.search(r"Year\s+\(4 digits\)\s*:\s*(\d+)", m.screen_text())
    if year and int(year[1]) < 1970:
        m.send(v.get("YEAR") or time.strftime("%Y"))


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
    (r"^\S Date and Time [q─]", date),
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


def press_on(m, old, retry, tries=3):
    """The next screen after F2 on `old`. With `retry` (KEY_RETRY, seconds; 0 = off) F2 goes again
    when the same screen is still up after that long: on sun4u (sol7-sun4u) the installer sat on a
    screen for 10 minutes after F2 in two of four runs (Preserve Data?, Mount Remote File Systems?),
    the kernel still running (hme0's link messages every 30 s). No screen of the installer takes
    minutes to follow, so a repeated F2 doesn't land on the next one."""
    if not retry:
        return next_screen(m, old)
    title = re.search(TITLE, old, re.M).group(1)
    for attempt in range(tries):
        try:
            return next_screen(m, old, retry)
        except RuntimeError:
            now = re.search(TITLE, m.screen_text(), re.M)
            if attempt == tries - 1 or not now or now.group(1) != title:
                raise
            m.snap(f"{title}: no reaction to F2, again")
            m.key("f2")


# Solaris 2.3 (and older): sysidtool asks one question per screen, a sentence at the top, a box with a
# field or a menu (">" marks the cursor; Ctrl-N / Ctrl-P move it) and "Press Return to continue.";
# Return answers. Then the installer's own menu: Quick Install, the software configuration, the disk,
# Begin Install. It reboots by itself at the end ("Installation successful...").
OLD = r"Press Return to continue\.|\[ Solaris Installation \]"
MENU_ITEM = r"│([> ])(\S.*?)\s*│"


def old_select(m, screen, label):
    """Move the menu's cursor to the item starting with `label` and take it."""
    items = re.findall(MENU_ITEM, screen)
    names = [name for _, name in items]
    here = next((i for i, (mark, _) in enumerate(items) if mark == ">"), None)
    there = next((i for i, name in enumerate(names) if name.startswith(label)), None)
    if here is None or there is None:
        raise RuntimeError(f"no {label!r} (or no cursor) in the menu {names}")
    for _ in range(abs(there - here)):
        m.key("ctrl-n" if there > here else "ctrl-p")
    m.send("\r")


def old_date(m, v, screen):
    # Like 2.4, 2.3 shows a year after 1999 as 19xx (1912 in 2026). The cursor is in the Year field,
    # its value highlighted: typing replaces it. Return moves to the next field; Return in the last
    # one (Minute) takes the form.
    year = re.search(r"Year\s+\(4 digits\)\s*:\s*(\d+)", screen)
    if year and int(year[1]) < 1970:
        m.send(v.get("YEAR") or time.strftime("%Y"))
    for _ in range(len(re.findall(r"\((?:4 digits|\d+-\d+)\)\s*:", screen))):
        m.send("\r")
        time.sleep(1)


# Question (regex on the screen) -> answer, in this order.
OLD_SCREENS = [
    (r"What is the hostname", lambda m, v, s: m.send(v["HOSTNAME"] + "\r")),
    (r"connected to a network\?", lambda m, v, s: old_select(m, s, "Yes")),
    (r"Internet Protocol \(IP\) address\?", lambda m, v, s: m.send(v["IP"] + "\r")),
    (r"Is the following information correct\?", lambda m, v, s: old_select(m, s, "Yes")),
    (r"client of a name service\?", lambda m, v, s: old_select(m, s, "None")),
    (r"have sub-networks\?", lambda m, v, s: old_select(m, s, "No")),
    (r"What is your geographic region\?", lambda m, v, s: old_select(m, s, v["REGION"])),
    (r"What is your time zone\?", lambda m, v, s: old_select(m, s, v["ZONE"])),
    (r"What is the current date and time\?", lambda m, v, s: old_date(m, v, s)),
]


def settled_change(m, old, timeout=600):
    """The screen once it differs from `old` and has been quiet for 2 s."""
    end = time.time() + timeout
    while True:
        m.quiet(2, timeout)
        screen = m.screen_text()
        if screen != old:
            return screen
        if time.time() > end:
            raise RuntimeError(f"the installer didn't move on from:\n{old}")
        time.sleep(1)


def old_install(m, v, screen):
    """sysidtool's questions, then Quick Install (End User, the boot disk, auto-layout)."""
    if v["SOFTWARE_UP"] != "0":
        raise ValueError("the Solaris 2.3 path installs End User System Support only (SOFTWARE_UP=0)")
    while "[ Solaris Installation ]" not in screen:
        for rx, action in OLD_SCREENS:
            if re.search(rx, screen):
                m.snap(rx.replace("\\", ""))
                action(m, v, screen)
                break
        else:
            raise RuntimeError(f"an unknown sysidtool screen:\n{screen}")
        screen = settled_change(m, screen)
    m.snap("Solaris Installation")
    m.send("\r")  # ( Quick Install... ), the first button
    screen = settled_change(m, screen)
    if not re.search(r"\[\* End User System Support", screen):
        raise RuntimeError(f"End User isn't the selected configuration:\n{screen}")
    m.snap("Quick Install: Software Configurations")
    m.send("\r")  # Return on the list applies it
    screen = settled_change(m, screen)
    if not re.search(r"\[\* c0t3d0", screen):
        raise RuntimeError(f"c0t3d0 isn't selected:\n{screen}")
    m.snap("Quick Install Disk Selection")
    m.send("\r")
    screen = settled_change(m, screen)
    if "Quick Install Configuration" not in screen:
        raise RuntimeError(f"no Quick Install Configuration:\n{screen}")
    m.snap("Quick Install Configuration")
    m.send("\r")  # ( Begin Install )
    # 2.3 shows a progress screen; 2.2 clears the screen and makes the file systems first
    m.expect(r"Initial Installation of|making filesystem on", 600, screen=True)
    m.snap("installing")
    m.expect(r"Installation successful\.\.\.", 7200)
    m.snap("installation finished")
    # it reboots by itself ("Resetting" from a Sun PROM, "rebooting" under OpenBIOS); the Sun PROM
    # tries the network and stops at `ok`, OpenBIOS stops at `0 >` (or boots the disk by itself)
    m.expect(r"Resetting|rebooting", 300)
    m.expect(r"\nok |0 > |SunOS Release", 600)
    m.snap("PROM prompt after the install")
    m.stop()


def run(m, v):
    prom_boot(m, v, "cdrom")
    m.expect(r"SunOS Release 5\.\d", 900)
    m.snap("kernel banner")
    first = True
    while True:  # the prompts before the curses screens
        prompts = [r"Select a Language", r"Type a number and press Return or Enter \[0\]",
                   r"What type of terminal are you using"]
        if first:
            first = False
            wait = int(v["FIRST_PROMPT_TIMEOUT"])
            try:
                i = m.expect_any(prompts, wait)
            except Timeout:
                m.snap("hung before the installer")
                raise AssertionError(f"{EARLY_HANG}: no language, locale or terminal prompt within {wait}s of the"
                                     " kernel banner (the boot hung; nothing is on the disk yet)")
        else:
            i = m.expect_any(prompts, 900)
        m.snap(["Select a Language", "Select a Locale", "terminal type"][i])
        if i == 2:
            m.send("3\r")  # DEC VT100
            break
        m.send(["0\r", "\r"][i])

    # 2.4 and later: screens with a title line; 2.3: sysidtool's older one-question screens
    end = time.time() + 900
    while True:
        m.quiet(2, 900)
        screen = m.screen_text()
        if re.search(TITLE, screen, re.M):
            break
        if re.search(OLD, screen):
            return old_install(m, v, screen)
        if time.time() > end:
            raise RuntimeError(f"no installer screen after the terminal type:\n{screen}")
        time.sleep(1)

    screen = None
    while True:
        screen = next_screen(m, screen) if screen is None else press_on(m, screen, int(v["KEY_RETRY"]))
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
    if m.expect_any([r"Executing JumpStart postinstall phase|Customizing system files", PANIC], 7200) == 1:
        m.quiet(5, 600)
        m.snap("kernel panic")
        raise AssertionError("the kernel panicked during the package installation")
    # 2.5.1's Maintenance Update ("Building package data base") runs past 30 minutes
    m.expect(r"\n#\s*$", int(v["FINISH_TIMEOUT"]))
    m.quiet(5, 600)
    m.snap("installation finished")
    if v.get("ARCH") == "sparc64":
        halt_sun4u(m)
    else:
        power_off(m, "halt")


def halt_sun4u(m):
    """sun4u (sol7-sun4u): `halt` returns to OpenBIOS's `0 >` once Solaris has synced (OpenBIOS has no
    power-off for Solaris), and the VM is stopped there, as solaris-webstart-serial.py does after a
    sun4u install."""
    m.send("sync; halt\r")
    m.expect(r"0 > ", 600)
    m.quiet(1, 30)
    m.snap("OpenBIOS prompt after the installation")
    m.stop()
