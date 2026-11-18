"""Boot an installed Red Hat Linux 6.2 (SPARC) disk to its login prompt on ttyS0, log in as root and
record the system state, then power off. `lab.py install` checks the Red Hat targets with it
(ROOT_PASSWORD, COMMANDS with `cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/redhat-boot-disk.py --pve 9600 --out /root/runs/check --var ROOT_PASSWORD=wshlab

  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                     (uname, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails   (none)
"""
import _redhat

DEFAULTS = {**_redhat.DEFAULTS, "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df -k; /sbin/ifconfig -a"}


def qemu_args(v, out):
    return _redhat.qemu_args(v, out)


def run(m, v):
    _redhat.boot_disk(m, v)
    _redhat.login(m, v["ROOT_PASSWORD"])
    out = _redhat.shell(m, v["COMMANDS"], 300)
    m.snap("system state")
    _redhat.check_output(out, v["CHECK"], v["COMMANDS"])
    _redhat.power_off(m)
