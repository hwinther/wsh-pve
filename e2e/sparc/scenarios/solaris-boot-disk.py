"""Boot an installed Solaris disk to the login prompt, log in as root and record the system state, then
shut down. Answers the first-boot questions (root password: ROOT_PASSWORD, none by default) when they
come up.

    lab.py run scenarios/solaris-boot-disk.py --out /srv/sparc/runs/boot \
        --var DISK=/srv/sparc/runs/boot/disk.raw

  ROOT_PASSWORD  root's password, for the login and the first-boot questions  (none)
  COMMANDS       run at the root prompt and recorded                         (uname, prtconf, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails       (none)

The scenario boots whatever DISK holds and changes it (first-boot setup, logs): give it a copy.
`lab.py install` checks a VM it installed with this scenario (ROOT_PASSWORD, COMMANDS `cat
/etc/wsh-lab-target`, CHECK the target's name).

Boot device: stock OpenBIOS since QEMU 9.2 has no `disk` alias ("No valid state has been set by load
or init-program"), so prom_boot() types the full device path at the `0 >` prompt; the packaged
OpenBIOS boots the disk by itself. The Sun PROMs boot target 3 with `boot disk`.
"""
from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; prtconf | head -3; df -k; ifconfig -a"}


def qemu_args(v, out):
    return sparc32_args(v, out)


def run(m, v):
    prom_boot(m, v, "disk")
    m.expect(r"SunOS Release", 600)
    m.snap("kernel banner")
    login(m, password=v["ROOT_PASSWORD"])
    m.send(v["COMMANDS"] + "\r")
    if v["CHECK"]:
        m.expect(v["CHECK"], 120)
    m.quiet(5, 120)
    m.snap("system state")
    power_off(m, "init 5")
