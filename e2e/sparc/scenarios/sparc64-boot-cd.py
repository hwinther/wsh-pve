"""Boot a sparc64 install CD (or a disk with BOOT=c) on sun4u and wait until the guest shows EXPECT on
the serial console (or, with CONSOLE=fb, on the VGA screen through OCR), then stop.

    lab.py run scenarios/sparc64-boot-cd.py --out /mnt/sparc/runs/nb --var GUEST=netbsd \
        --var ISO=/mnt/sparc/iso/other-os/NetBSD-11.1-sparc64.iso

  GUEST     netbsd | openbsd | debian | solaris: the default EXPECT for that installer  (none)
            solaris10: Solaris 10 1/13's installer driven past its first two questions on ttya
            (language 0, terminal 3 = VT100), then SOL10_EXPECT; fails on the IDE driver's
            "Interrupt not seen" warning and without a dad (IDE disk) attach line. Needs the Sun DVD
            (sol-10-u11-ga-sparc-dvd.iso, not in the repository) and the firmware and QEMU of the
            package built with openbios-sparc64 and pve-qemu wsh/0021; MEM 1024 recommended
  EXPECT    regex that ends the run successfully                (GUEST's)
  FAIL      regex that ends it as failed (OpenBIOS can't boot, kernel panic, ...)
  TIMEOUT   seconds to wait for EXPECT                         (900)
  TYPE      text typed on the VGA keyboard (QMP send-key) once EXPECT matched with CONSOLE=fb, and
            TYPE_EXPECT a regex that must appear on the screen after it (does the keyboard work?)

Other variables: scenarios/_sparc64.py (DISK_BUS, CD_BUS, NIC, VGA, MEM, SMP, CPU, LAYOUT, ...).
"""
import re
import time

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args

# What each installer shows first on the console
GUESTS = {
    "netbsd": r"Terminal type|sysinst|Installation messages in English",
    "openbsd": r"\(I\)nstall, \(U\)pgrade, \(A\)utoinstall or \(S\)hell\?",
    "debian": r"Choose a language|Select a language|\[!!\] ",
    "solaris": r"Select a Language|What type of terminal|Do you want to format|SunOS Release 5",
}
# Solaris 10 (GUEST=solaris10): what the installer shows after the terminal type has been answered
SOL10_AFTER_TERMINAL = r"The Oracle Solaris Installation Program|The Solaris Installation Program"
FAIL = (r"Can't open boot device|No valid state has been set|Unhandled Exception|panic:|Kernel panic|"
        r"Fast Data Access MMU Miss|No bootable|Trap 0x|BOOT: Failed|failed to boot|Boot load failed")

DEFAULTS = {**BASE, "GUEST": "", "EXPECT": "", "FAIL": FAIL, "TIMEOUT": "900", "TYPE": "", "TYPE_EXPECT": "",
            "SOL10_EXPECT": SOL10_AFTER_TERMINAL}


def qemu_args(v, out):
    return sparc64_args(v, out)


def run(m, v):
    if v["GUEST"] == "solaris10":
        return solaris10(m, v)
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


def solaris10(m, v):
    """Solaris 10 1/13's DVD: kernel, the IDE disk attached without the interrupt warning, then the
    language and terminal questions answered on ttya (console input works) and the next screen."""
    timeout = int(v["TIMEOUT"])
    i = m.expect_any([r"SunOS Release 5\.10", v["FAIL"]], timeout)
    if i == 1:
        m.snap("failure")
        raise AssertionError("failure text on the console before the kernel")
    i = m.expect_any([r"Please make a choice \(0 - 10\)", r"panic|" + v["FAIL"]], timeout)
    m.quiet(3, 120)
    m.snap("language" if i == 0 else "failure")
    if i == 1:
        raise AssertionError("failure text on the console before the installer")
    if "Interrupt not seen" in m.text:
        raise AssertionError("the IDE driver missed an interrupt (Interrupt not seen after set_features)")
    # The dad driver attached the primary master: "WARNING: /pci@1f,0/pci@1,1/ide@3/dad@0,0 (dad0):"
    # (then "Corrupt label; wrong magic number" for the blank disk)
    disk = re.search(r".*dad@[0-9a-f,]+ \(dad\d+\).*", m.text)
    if not disk:
        raise AssertionError("no dad (IDE disk) on the console")
    m.log(f"disk: {disk.group(0).strip()}")
    m.send("0\r")
    m.expect(r"What type of terminal are you using", 600)
    m.quiet(3, 120)
    m.snap("terminal type")
    m.send("3\r")
    m.expect(v["SOL10_EXPECT"], 900)
    m.quiet(5, 300)
    m.snap("after the terminal type")
    m.stop()
