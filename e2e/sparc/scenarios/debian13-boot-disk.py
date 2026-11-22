"""Boot an installed Debian 13 (sparc64) disk through GRUB to its login prompt on ttyS0, log in as root
and record the system state, then power off. `lab.py install` checks the debian13-sun4u target with
it (ROOT_PASSWORD, COMMANDS with `cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/debian13-boot-disk.py --pve 9900 --out /root/runs/check --var ROOT_PASSWORD=wshlab

  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                     (uname, df, ip)
  CHECK          a regex their output must contain, else the run fails   (none)
"""
import time

import _debian13

DEFAULTS = {**_debian13.DEFAULTS, "ISO": "", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df -k; ip -br addr"}


def qemu_args(v, out):
    return _debian13.qemu_args(v, out)


def run(m, v):
    t0 = time.time()
    _debian13.boot_disk(m)
    _debian13.login(m, v["ROOT_PASSWORD"])
    m.metrics["login_s"] = round(time.time() - t0, 1)
    out = _debian13.shell(m, v["COMMANDS"], 300)
    m.snap("system state")
    _debian13.check_output(out, v["CHECK"], v["COMMANDS"])
    t1 = time.time()
    _debian13.power_off(m)
    m.metrics["poweroff_s"] = round(time.time() - t1, 1)
