"""Boot an installed OpenBSD/sparc64 disk to its login prompt, log in as root and record the system state,
then power off with `halt -p`. `lab.py install openbsd80-sun4u --check` and `lab.py boot-test` run it
(ROOT_PASSWORD, COMMANDS with `cat /etc/wsh-lab-target`, CHECK the target's name).

    lab.py run scenarios/openbsd-boot-disk.py --pve 9210 --out /mnt/runs/check --var ROOT_PASSWORD=wshlab

  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                     (uname, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails   (none)
  COMMANDS_TIMEOUT  seconds COMMANDS may take                            (600)

A `wd` timeout on the console (`wd0(pciide0:0:0): timeout`, `wd0d: device timeout ...`) fails the run:
OpenBSD 8.0 on sun4u had them, then hung, before pve-qemu `wsh/0045` (the sabre's lost interrupt,
_openbsd.py).

The scenario boots whatever the disk holds and changes it (logs): give it a copy outside PVE.
"""
import re

import _openbsd

DEFAULTS = {**_openbsd.DEFAULTS, "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "CHECK": "",
            "COMMANDS": "uname -a; df -k; ifconfig -a", "COMMANDS_TIMEOUT": "600"}


def qemu_args(v, out):
    return _openbsd.qemu_args(v, out)


def run(m, v):
    m.expect(r"OpenBSD [\d.]+ \(GENERIC", 600)
    m.snap("kernel banner")
    _openbsd.login(m, v["ROOT_PASSWORD"])
    out = _openbsd.shell(m, v["COMMANDS"], int(v["COMMANDS_TIMEOUT"]))
    m.snap("system state")
    if v["CHECK"] and not re.search(v["CHECK"], out):
        raise AssertionError(f"no {v['CHECK']!r} in the output of {v['COMMANDS']!r}")
    timeouts = re.findall(r"wd\d+\S*: (?:device )?timeout.*", m.text)
    m.metrics["wd_timeouts"] = len(timeouts)
    if timeouts:
        raise AssertionError(f"disk timeouts on the console: {timeouts[:3]}")
    _openbsd.power_off(m, v)
