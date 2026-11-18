"""Boot an installed SunOS 4.1.4 disk to the login prompt, log in as root, record the system state and
power off with `halt`. `lab.py install sunos414-ss5 --check` runs it (ROOT_PASSWORD, COMMANDS with
`cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/sunos-boot-disk.py --pve 400 --out /root/runs/check --var ROOT_PASSWORD=wshlab

  ROOT_PASSWORD  root's password                                             (required)
  COMMANDS       run at /bin/sh's root prompt and recorded                   (uname, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails       (none)

A disk whose first boot hasn't run (sys-config's questions) fails here: that is sunos-firstboot.py.
"""
from _sparc32 import DEFAULTS as BASE, power_off, prom_boot, qemu_args as sparc32_args
from _sunos4 import login

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df; ifconfig -a"}


def qemu_args(v, out):
    return sparc32_args(v, out)


def run(m, v):
    prom_boot(m, v, "disk")
    m.expect(r"SunOS Release 4\.1", 600)
    m.snap("kernel banner")
    login(m, v["ROOT_PASSWORD"])
    m.send(v["COMMANDS"] + "\r")
    if v["CHECK"]:
        m.expect(v["CHECK"], 120)
    m.quiet(5, 120)
    m.snap("system state")
    power_off(m, "halt")
