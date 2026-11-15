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
            QEMU process on the same disk, as PVE starts a VM)   (1)
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


def run(m, v):
    boots = int(v["BOOTS"])
    qemu = m.args[:-8]  # without the serial, QMP and display arguments Machine adds
    for n in range(1, boots + 1):
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
        if n < boots:
            m.raw.close()
            os.replace(os.path.join(m.out, "serial.raw"), os.path.join(m.out, f"serial-boot{n}.raw"))
            steps, metrics = m.steps, m.metrics
            m.__dict__.update(lab.Machine(m.out, qemu, ocr=m.ocr).__dict__)
            m.steps, m.metrics = steps, metrics
            m.log(f"boot {n + 1}")
