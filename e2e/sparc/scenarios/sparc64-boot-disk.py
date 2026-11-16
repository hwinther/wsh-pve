"""Boot an installed sparc64 disk on sun4u to its login prompt, log in, run COMMANDS (each output must
match its CHECK regex, if given), then power off and check that QEMU ended, BOOTS times.

    lab.py run scenarios/sparc64-boot-disk.py --out /mnt/sparc/runs/nb-disk \
        --var DISK=/mnt/sparc/runs/nb-disk/disk.raw --var GUEST=netbsd

The guest changes the disk (logs, first-boot setup): give it a copy.

  GUEST     netbsd | openbsd | debian: login prompt, account and power-off command (_sparc64.GUESTS)
  PROMPT, USER, PASSWORD, POWEROFF  override GUEST's
  COMMANDS  shell commands run one after another, separated by ' ;; '   (GUEST's system state)
  CHECK     regexes their outputs must match, separated by ' ;; ' in the same order (empty: none)
  BOOTS     how many times to start QEMU, log in and power off (each boot after the first is a new
            QEMU process on the same disk, as PVE starts a VM; its console goes to serial-bootN.raw)  (1)
  TIMEOUT   seconds from QEMU start to the login prompt          (900)

Metrics (result.json): boot_s (QEMU start to the login prompt, per boot), poweroff_s (power-off
command to QEMU's exit, per boot).
"""
import os
import re
import time

import lab
from _sparc64 import DEFAULTS as BASE, guest_defaults, login, power_off, qemu_args as sparc64_args, shell

DEFAULTS = {**BASE, "BOOT": "c", "GUEST": "", "PROMPT": "", "USER": "", "PASSWORD": "", "COMMANDS": "",
            "CHECK": "", "POWEROFF": "", "BOOTS": "1", "TIMEOUT": "900"}


def qemu_args(v, out):
    guest_defaults(v)
    return sparc64_args(v, out)


def boot_once(m, v, n):
    login(m, v, int(v["TIMEOUT"]))
    m.metrics.setdefault("boot_s", []).append(round(time.time() - m.t0, 1))
    commands = [c.strip() for c in v["COMMANDS"].split(";;") if c.strip()]
    checks = [c.strip() for c in v["CHECK"].split(";;")] if v["CHECK"] else []
    for i, command in enumerate(commands):
        out, _ = shell(m, command)
        if i < len(checks) and checks[i] and not re.search(checks[i], out):
            m.snap(f"check failed: {command}")
            raise AssertionError(f"no {checks[i]!r} in the output of {command!r}:\n{out}")
    m.snap(f"boot {n}: system state")
    m.metrics.setdefault("poweroff_s", []).append(round(power_off(m, v), 1))


def run(m, v):
    qemu = m.args[:-8]  # without the serial, QMP and display arguments Machine adds
    boot_once(m, v, 1)
    for n in range(2, int(v["BOOTS"]) + 1):
        # a new QEMU process on the same disk; the steps and metrics stay in m, which lab.py reports
        m.raw.close()
        os.replace(os.path.join(m.out, "serial.raw"), os.path.join(m.out, f"serial-boot{n - 1}.raw"))
        nm = lab.Machine(m.out, qemu, ocr=m.ocr)
        nm.steps, nm.metrics = m.steps, m.metrics
        nm.log(f"boot {n}")
        try:
            boot_once(nm, v, n)
        finally:
            if nm.proc.poll() is None:
                nm.stop()
