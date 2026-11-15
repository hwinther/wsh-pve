"""The cg3 at the size RES gives (-g): the firmware banner on the framebuffer and, with DISK, an
installed Solaris booted to its login prompt. Every framebuffer screenshot is checked for the
requested size and for not being blank.

    lab.py run scenarios/cg3-display.py --out /srv/sparc/runs/fb --var RES=1152x900 \
        [--var DISK=/srv/sparc/runs/fb/disk.raw]

CONSOLE=fb (the default here) puts the PROM and Solaris consoles on the framebuffer and the
scenario reads them by OCR. Without DISK it stops after the banner; with it, it takes one more
screenshot SETTLE seconds after the login prompt (90; 0 = none). Sizes other than 1024x768 need
QEMU with the cg3 patches and their FCode ROM (pve-qemu 0008-0010, openbios/patches/0002).
"""
import time

from _sparc32 import DEFAULTS as BASE, qemu_args as sparc32_args

DEFAULTS = {**BASE, "CONSOLE": "fb", "RES": "1024x768", "BOOT": "c", "NO_CD": "1", "SETTLE": "90"}

BANNER = r"Welcome to Open|for detailed information|SPARCstation 5|ROM Rev"  # OCR reads OpenBIOS as "OpenBros"


def qemu_args(v, out):
    v["GUEST"] = "1" if v["DISK"] else ""  # sparc32_args fills DISK with a blank disk
    return sparc32_args(v, out)


def check(m, title, v):
    w, h = (int(x) for x in v["RES"].split("x")[:2])
    m.fb_check(m.snap(title)["fb_png"], (w, h))


def run(m, v):
    m.fb_expect(BANNER, 300)
    check(m, "firmware banner", v)
    if not v["GUEST"]:
        m.stop()
        return
    # First boot asks for a root password (none: Return twice). The screen keeps the earlier prompts,
    # so only the last lines count; dtlogin's messages can follow the login prompt.
    while True:
        i = m.fb_expect_any([r"console login:", r"password:", r"Press Return to continue"], 1800, tail=8)
        if i == 0:
            break
        m.snap(["", "root password", "press return"][i])
        m.fb_type("\r")
        time.sleep(5)
    check(m, "console login", v)
    if int(v["SETTLE"]):
        # dtlogin (End User installs) starts the X server on the cg3 after the prompt
        time.sleep(int(v["SETTLE"]))
        check(m, f"{v['SETTLE']}s after the login prompt", v)
    m.stop()
