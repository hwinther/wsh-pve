"""Boot an installed sparc64 disk on sun4u to its login prompt, log in, then reboot from the guest
(`REBOOT`, e.g. Solaris's `reboot` or `init 6`) `REBOOTS` times: each time the firmware's banner must
come back in the same QEMU process (the machine reset by the client interface's `boot` service,
OpenBIOS patch 0030), the firmware boots the disk by itself and the guest reaches its login prompt
again. Then power off.

    lab.py run scenarios/sparc64-reboot.py --out /work/reboot \
        --var DISK=/work/reboot/disk.raw --var GUEST=solaris10 --var PASSWORD=wshlab --var REBOOTS=3

The guest changes the disk (logs, the reboot's sync): give it a copy.

  GUEST     netbsd | openbsd | freebsd | debian | solaris10 | solaris (7, 8, 9): login prompt, account,
            power-off command (_sparc64.GUESTS)
  PROMPT, USER, PASSWORD, POWEROFF, FIRSTBOOT  override GUEST's
  REBOOT    the reboot command                                   (reboot)
  REBOOTS   how many times to reboot and log in again             (3)
  TIMEOUT   seconds from QEMU start (or the banner) to the login prompt   (900)
  BANNER_TIMEOUT  seconds from the reboot command to the firmware's banner (600)

A reboot that doesn't come back fails the run: `reboot call returned` (the firmware's `boot` service
returned, as before patch 0030), the firmware's `0 >` prompt, or no banner in time; the CPU's
registers (`info registers`) are then kept in the step log.

Metrics (result.json): boot_s (QEMU start to the first login prompt), reboot_s (the reboot command to
the banner, per reboot), relogin_s (the reboot command to the next login prompt, per reboot),
poweroff_s.
"""
import time

import lab
from _sparc64 import DEFAULTS as BASE, guest_defaults, login, power_off, qemu_args as sparc64_args, shell

DEFAULTS = {**BASE, "MEM": "1024", "BOOT": "c", "GUEST": "", "PROMPT": "", "USER": "", "PASSWORD": "",
            "FIRSTBOOT": "", "POWEROFF": "", "COMMANDS": "", "REBOOT": "reboot", "REBOOTS": "3",
            "TIMEOUT": "900", "BANNER_TIMEOUT": "600"}

BANNER = r"OpenBIOS for Sparc64"
RETURNED = r"reboot call returned|Reboot failed"
PROMPT0 = r"^0 > "


def qemu_args(v, out):
    guest_defaults(v)
    return sparc64_args(v, out)


def registers(m):
    try:
        m.log("info registers:\n" + m.hmp("info registers"))
    except Exception as e:  # QEMU gone or QMP stuck: the timeout says enough
        m.log(f"info registers failed: {type(e).__name__}: {e}")


def run(m, v):
    login(m, v, int(v["TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    for n in range(1, int(v["REBOOTS"]) + 1):
        shell(m, "sync")
        m.mark(f"reboot {n}")
        t0 = time.time()
        m.send(f"{v['REBOOT']}\r")
        try:
            i = m.expect_any([BANNER, RETURNED, PROMPT0], int(v["BANNER_TIMEOUT"]))
        except lab.Timeout:
            registers(m)
            m.snap(f"reboot {n}: no banner")
            raise
        if i != 0:
            registers(m)
            m.snap(f"reboot {n}: did not reset")
            raise AssertionError(f"reboot {n}: the firmware didn't reset the machine (matched {[BANNER, RETURNED, PROMPT0][i]!r})")
        m.metrics.setdefault("reboot_s", []).append(round(time.time() - t0, 1))
        m.snap(f"reboot {n}: firmware banner")
        login(m, v, int(v["TIMEOUT"]))
        m.metrics.setdefault("relogin_s", []).append(round(time.time() - t0, 1))
        m.snap(f"reboot {n}: logged in again")
    m.metrics["poweroff_s"] = round(power_off(m, v), 1)
