"""Boot an installed Tribblix sun4u disk to the login prompt, log in as root, record the system state
and power off with `init 5`: what `lab.py install tribblix-m34-sun4u --check` runs after the first boot.

    lab.py run scenarios/tribblix-boot-disk.py --pve 9401 --out /root/runs/check \
        --var ROOT_PASSWORD=wshlab --var CHECK='(?m)^target=tribblix-m34-sun4u$'
    lab.py run scenarios/tribblix-boot-disk.py --out /mnt/sparc/runs/tribd --var DISK=<the installed disk> \
        --var ROOT_PASSWORD=tribblix

  ROOT_PASSWORD  root's password                                          (wshlab)
  COMMANDS       run at the root prompt and recorded                      (uname, prtconf, df, ipadm)
  CHECK          a regex their output must contain, else the run fails    (none)
  TIMEOUT        seconds from the start to the login prompt               (3000)
"""
import re

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args, shell
from _tribblix import BANNER, FAIL, login, power_off

DEFAULTS = {**BASE, "MEM": "2048", "BOOT": "c", "NET": "user", "ROOT_PASSWORD": "wshlab", "CHECK": "",
            "TIMEOUT": "3000", "COMMANDS": "uname -a; prtconf | head -3; df -k /; ipadm show-addr"}


def qemu_args(v, out):
    return sparc64_args(v, out)


def run(m, v):
    if m.expect_any([BANNER, FAIL], 900) == 1:
        m.snap("failure")
        raise AssertionError("the disk didn't boot (firmware or ZFS boot block)")
    m.snap("kernel banner")
    login(m, v["ROOT_PASSWORD"], int(v["TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    out, _ = shell(m, v["COMMANDS"], 300)
    m.snap("system state")
    if v["CHECK"] and not re.search(v["CHECK"], out):
        raise AssertionError(f"no {v['CHECK']!r} in the output of the commands:\n{out}")
    m.metrics["poweroff_s"] = round(power_off(m), 1)
