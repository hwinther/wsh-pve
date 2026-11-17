"""Boot an installed Solaris 10 sun4u disk to the login prompt, log in as root, record the system state
and shut down with `init 5`: what `lab.py install sol10-sun4u --check` runs after the first boot (the
same variables as solaris-boot-disk.py, the sparc32 one).

    lab.py run scenarios/solaris10-boot-disk.py --pve 120 --out /root/runs/check \
        --var ROOT_PASSWORD=wshlab --var CHECK='(?m)^target=sol10-sun4u$'

  ROOT_PASSWORD  root's password                                          (none)
  COMMANDS       run at the root prompt and recorded                      (uname, prtconf, df, ifconfig)
  CHECK          a regex their output must contain, else the run fails    (none)
  TIMEOUT        seconds from the start to the login prompt               (1200)

A keyboard layout question on the way (a disk that never finished its first boot) is answered with F2.
"""
import re

from _sparc64 import DEFAULTS as BASE, GUESTS, login, power_off, qemu_args as sparc64_args, shell

DEFAULTS = {**BASE, "MEM": "1024", "BOOT": "c", "ROOT_PASSWORD": "", "CHECK": "", "TIMEOUT": "1200",
            "COMMANDS": "uname -a; prtconf | head -3; df -k; ifconfig -a"}


def qemu_args(v, out):
    return sparc64_args(v, out)


def run(m, v):
    g = {**GUESTS["solaris10"], "PASSWORD": v["ROOT_PASSWORD"]}
    m.expect(r"SunOS Release 5\.10", 900)
    m.snap("kernel banner")
    login(m, g, int(v["TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    out, _ = shell(m, v["COMMANDS"], 300)
    m.snap("system state")
    if v["CHECK"] and not re.search(v["CHECK"], out):
        raise AssertionError(f"no {v['CHECK']!r} in the output of the commands:\n{out}")
    m.metrics["poweroff_s"] = round(power_off(m, g), 1)
