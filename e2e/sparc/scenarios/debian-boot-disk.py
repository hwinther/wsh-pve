"""Boot an installed Debian 4.0 (sparc) disk to its login prompt on ttyS0, log in as root and record the
system state, then power off. `lab.py install` checks the Debian targets with it (ROOT_PASSWORD,
COMMANDS with `cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/debian-boot-disk.py --pve 9900 --out /root/runs/check --var ROOT_PASSWORD=wshlab

  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                     (uname, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails   (none)
"""
import _debian

DEFAULTS = {**_debian.DEFAULTS, "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df -k; /sbin/ifconfig -a"}


def qemu_args(v, out):
    return _debian.qemu_args(v, out)


def run(m, v):
    _debian.boot_disk(m, v)
    _debian.login(m, v["ROOT_PASSWORD"])
    out = _debian.shell(m, v["COMMANDS"], 300)
    m.snap("system state")
    _debian.check_output(out, v["CHECK"], v["COMMANDS"])
    _debian.power_off(m)
