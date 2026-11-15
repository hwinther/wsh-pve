"""Boot a Solaris 2.x install CD to the installer's first question and stop there: the boot path of
solaris-install-serial.py (PROM, CD driver, kernel, the miniroot on ttya) without the install.

    lab.py run scenarios/solaris-boot-cd.py --out /mnt/sparc/runs/cd26 \
        --var ISO=/mnt/sparc/iso/solaris_2.6_598_sparc.iso

The guest disk is blank and nothing is written to it.
"""
from _sparc32 import DEFAULTS as BASE, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none"}


def qemu_args(v, out):
    return sparc32_args(v, out)


def run(m, v):
    prom_boot(m, v, "cdrom")
    m.expect(r"SunOS Release 5\.\d", 900)
    m.snap("kernel banner")
    # 2.6, 7, 9: language; 2.5.1: terminal type (no language/locale prompt); 8 (Installation CD, Web
    # Start): the disk for the installer, which needs a Sun-labelled disk (TEMPLATE) to get there
    m.expect(r"Select a Language|What type of terminal are you using|Do you want to format", 900)
    m.quiet(2, 60)
    m.snap("installer's first question")
    m.stop()
