"""Boot an installed Solaris disk to the login prompt, log in as root and record the system state, then
shut down. Answers the first-boot questions (root password: none) when they come up.

    lab.py run scenarios/solaris-boot-disk.py --out /srv/sparc/runs/boot \
        --var DISK=/srv/sparc/runs/boot/disk.raw

The scenario boots whatever DISK holds and changes it (first-boot setup, logs): give it a copy.

Boot device: OpenBIOS's `disk` alias does not find the disk on SCSI target 3 ("No valid state has been
set by load or init-program"), so prom_boot() types the full device path at the `0 >` prompt. The Sun
PROMs boot target 3 with `boot disk`.
"""
from _sparc32 import DEFAULTS as BASE, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1",
            "COMMANDS": "uname -a; prtconf | head -3; df -k; ifconfig -a"}


def qemu_args(v, out):
    return sparc32_args(v, out)


def run(m, v):
    prom_boot(m, v, "disk")
    m.expect(r"SunOS Release", 600)
    m.snap("kernel banner")
    while True:
        i = m.expect_any([r"Root password:", r"Re-enter your root password", r"Press Return to continue",
                          r"console login:"], 1800)
        if i == 3:
            break
        m.snap(["root password", "re-enter root password", "press return", ""][i])
        m.send("\r")
    m.snap("console login")
    m.send("root\r")
    m.expect(r"#\s*$", 120)
    m.send(v["COMMANDS"] + "\r")
    m.quiet(5, 120)
    m.snap("system state")
    power_off(m, "init 5")
