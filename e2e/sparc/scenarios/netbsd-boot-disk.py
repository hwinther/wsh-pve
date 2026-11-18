"""Boot an installed NetBSD disk (sparc64 or sparc) to its login prompt, log in as root and record the
system state, then power off with `halt -p`. `lab.py install` checks the NetBSD targets with it
(ROOT_PASSWORD, COMMANDS with `cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/netbsd-boot-disk.py --pve 130 --out /root/runs/check --var ROOT_PASSWORD=wshlab

  ARCH           sparc64 | sparc (from the VM's config with --pve)        (sparc64)
  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                     (uname, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails   (none)

The scenario boots whatever the disk holds and changes it (logs): give it a copy outside PVE.
"""
import re

import _netbsd

DEFAULTS = {**_netbsd.defaults("sparc64"), "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df -k; ifconfig -a"}


def qemu_args(v, out):
    return _netbsd.qemu_args(v, out)


def run(m, v):
    _netbsd.boot_disk(m, v)
    m.expect(r"NetBSD [\d.]+ \(GENERIC", 600)
    m.snap("kernel banner")
    _netbsd.login(m, v["ROOT_PASSWORD"])
    out = _netbsd.shell(m, v["COMMANDS"], 300)
    m.snap("system state")
    if v["CHECK"] and not re.search(v["CHECK"], out):
        raise AssertionError(f"no {v['CHECK']!r} in the output of {v['COMMANDS']!r}")
    _netbsd.power_off(m, v)
