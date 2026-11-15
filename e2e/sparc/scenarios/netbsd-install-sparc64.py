"""Install NetBSD/sparc64 from its CD with sysinst on the serial console (sun4u, disk and CD-ROM on the
built-in IDE), root without a password, then power off. The disk then boots with
sparc64-boot-disk.py GUEST=netbsd.

    lab.py run scenarios/netbsd-install-sparc64.py --out /mnt/sparc/runs/nbi \
        --var ISO=/mnt/sparc/iso/other-os/NetBSD-11.1-sparc64.iso

  SETS      sysinst's distribution menu: a = full, b = without X11, c = minimal  (b)
  DISK_GB   size of the blank disk                                             (8)

~8 min for 11.1 without X11 on one host core (sysinst to power-off ~7 min). sysinst draws its menus
with curses: a letter moves the cursor, Return activates; each step waits for the screen it answers.
"""
import time

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args

DEFAULTS = {**BASE, "SETS": "b", "TIMEOUT": "900"}


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<NetBSD sparc64 CD>")
    return sparc64_args(v, out)


def choose(m, screen, letter, title, timeout=300):
    """Wait for `screen` (regex) on the terminal, then pick `letter` (empty: the current item)."""
    m.expect(screen, timeout, screen=True)
    m.quiet(2, 120)
    m.snap(title)
    if letter:
        m.send(letter)
        time.sleep(1)
    m.send("\r")
    time.sleep(2)


def run(m, v):
    m.expect(r"Terminal type", int(v["TIMEOUT"]))
    m.snap("terminal type")
    m.send("vt100\r")
    choose(m, r"Installation messages in English", "a", "language")
    choose(m, r"Install NetBSD to hard disk", "a", "main menu")
    choose(m, r"Shall we continue", "b", "continue")
    choose(m, r"Available disks", "a", "disk")
    choose(m, r"Use default partition sizes", "b", "partitioning")
    choose(m, r"Partition sizes ok", "x", "partition sizes")
    choose(m, r"ready to install NetBSD", "b", "last chance")
    choose(m, r"Select your distribution", v["SETS"], "distribution")
    choose(m, r"Install from", "a", "install from CD-ROM")
    # optional sets missing from the CD, then the extraction, then "complete": Return each time
    while True:
        i = m.expect_any([r"Hit enter to continue", r"New password:"], 3600)
        if i == 1:
            break
        m.quiet(2, 120)
        m.send("\r")
        time.sleep(2)
    m.snap("root password")
    m.send("\r")  # none
    choose(m, r"Not now, continue", "x", "entropy")
    # the configuration menu (time zone, root shell, sshd, ...): keep the defaults
    if m.expect_any([r"Finished configuring", r"installation of NetBSD-[\d.]+ is now complete"], 600,
                    screen=True) == 0:
        choose(m, r"Finished configuring", "x", "configuration")
    choose(m, r"installation of NetBSD-[\d.]+ is now complete", "", "complete", 600)
    choose(m, r"Exit Install System", "x", "exit")
    m.expect(r"#\s*$", 120)
    m.send("sync; halt -p\r")
    code = m.wait_exit(300)
    if code != 0:
        raise AssertionError(f"QEMU exited with {code}")
