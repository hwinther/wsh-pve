"""Boot an installed FreeBSD/sparc64 disk to its login prompt, log in as root and record the system state,
then power off with `shutdown -p now`. `lab.py install freebsd124-sun4u --check` and `lab.py boot-test`
run it (ROOT_PASSWORD, COMMANDS with `cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/freebsd-boot-disk.py --out /work/check --var DISK=/work/check/disk.raw --var ROOT_PASSWORD=wshlab

  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                     (uname, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails   (none)
  COMMANDS_TIMEOUT  seconds COMMANDS may take                            (600)
  REBOOT         1: `shutdown -r now` first and the login again, then the power-off  (none)

Disk trouble on the console (an ata timeout, or the kernel's `interrupt storm detected`, FreeBSD bug
239068 on older QEMU: _freebsd.DISK_TROUBLE) fails the run.

The scenario boots whatever the disk holds and changes it (logs): give it a copy outside PVE.
"""
import re
import time

import _freebsd

DEFAULTS = {**_freebsd.DEFAULTS, "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df -k; ifconfig -a", "COMMANDS_TIMEOUT": "600", "REBOOT": ""}


def qemu_args(v, out):
    return _freebsd.qemu_args(v, out)


def run(m, v):
    t0 = time.time()
    m.expect(_freebsd.KERNEL, 600)
    m.snap("kernel banner")
    _freebsd.login(m, v["ROOT_PASSWORD"])
    m.metrics["login_s"] = round(time.time() - t0, 1)
    out = _freebsd.shell(m, v["COMMANDS"], int(v["COMMANDS_TIMEOUT"]))
    m.snap("system state")
    if v["CHECK"] and not re.search(v["CHECK"], out):
        raise AssertionError(f"no {v['CHECK']!r} in the output of {v['COMMANDS']!r}")
    _freebsd.check_disk(m)
    if v["REBOOT"]:
        t1 = time.time()
        m.send("shutdown -r now\r")
        m.expect(_freebsd.KERNEL, 900)
        _freebsd.login(m, v["ROOT_PASSWORD"])
        m.metrics["reboot_s"] = round(time.time() - t1, 1)
        _freebsd.shell(m, "uptime")
        m.snap("after the reboot")
        _freebsd.check_disk(m)
    _freebsd.power_off(m, v)
