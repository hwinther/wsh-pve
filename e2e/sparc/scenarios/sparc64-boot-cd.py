"""Boot a sparc64 install CD (or a disk with BOOT=c) on sun4u and wait until the guest shows EXPECT on
the serial console (or, with CONSOLE=fb, on the VGA screen through OCR), then stop.

    lab.py run scenarios/sparc64-boot-cd.py --out /mnt/sparc/runs/nb --var GUEST=netbsd \
        --var ISO=/mnt/sparc/iso/other-os/NetBSD-11.1-sparc64.iso

  GUEST     netbsd | openbsd | debian: the default EXPECT for that installer  (none)
  EXPECT    regex that ends the run successfully                (GUEST's)
  FAIL      regex that ends it as failed (OpenBIOS can't boot, kernel panic, ...)
  TIMEOUT   seconds to wait for EXPECT                         (900)
  TYPE      text typed on the VGA keyboard (QMP send-key) once EXPECT matched with CONSOLE=fb, and
            TYPE_EXPECT a regex that must appear on the screen after it (does the keyboard work?)

Other variables: scenarios/_sparc64.py (DISK_BUS, CD_BUS, NIC, VGA, MEM, SMP, CPU, LAYOUT, ...).
"""
import time

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args

# What each installer shows first on the console
GUESTS = {
    "netbsd": r"Terminal type|sysinst|Installation messages in English",
    "openbsd": r"\(I\)nstall, \(U\)pgrade, \(A\)utoinstall or \(S\)hell\?",
    "debian": r"Choose a language|Select a language|\[!!\] ",
    "solaris": r"Select a Language|What type of terminal|Do you want to format|SunOS Release 5",
}
FAIL = (r"Can't open boot device|No valid state has been set|Unhandled Exception|panic:|Kernel panic|"
        r"Fast Data Access MMU Miss|No bootable|Trap 0x|BOOT: Failed|failed to boot|Boot load failed")

DEFAULTS = {**BASE, "GUEST": "", "EXPECT": "", "FAIL": FAIL, "TIMEOUT": "900", "TYPE": "", "TYPE_EXPECT": ""}


def qemu_args(v, out):
    return sparc64_args(v, out)


def run(m, v):
    expect = v["EXPECT"] or GUESTS.get(v["GUEST"], "")
    if not expect:
        raise SystemExit("set GUEST or EXPECT")
    if v["CONSOLE"] == "fb":
        i = m.fb_expect_any([expect, v["FAIL"]], int(v["TIMEOUT"]), interval=10)
        m.snap("framebuffer")
        if i == 1:
            raise AssertionError("failure text on the framebuffer")
        if v["TYPE"]:
            m.fb_type(v["TYPE"])
            time.sleep(3)
            if v["TYPE_EXPECT"]:
                m.fb_expect(v["TYPE_EXPECT"], 120, interval=5)
            m.snap(f"typed {v['TYPE']!r}")
        m.stop()
        return
    if v["GUEST"] == "debian":
        # GRUB's menu (it has no timeout on the CD): Return boots "Default install"
        m.expect(r"Default install", 300)
        m.quiet(2, 60)
        m.snap("GRUB menu")
        m.send("\r")
    i = m.expect_any([expect, v["FAIL"]], int(v["TIMEOUT"]))
    m.quiet(3, 120)
    m.snap("first prompt" if i == 0 else "failure")
    if i == 1:
        raise AssertionError("failure text on the console")
    m.stop()
