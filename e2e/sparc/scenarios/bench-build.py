"""Build the bench disk: boot the build disk (Solaris 2.6 + gcc, README "The bench disk") with the
hand-over CD (bench/handover.py) and a blank Sun-labelled disk as DISK2, run the CD's build.sh, which
compiles the benchmarks and puts them on DISK2, then `init 5`.

    sunlabel.py /mnt/sparc/runs/bb/bench.raw 32
    lab.py run scenarios/bench-build.py --out /mnt/sparc/runs/bb --var MACHINE=SS-20 \
        --var DISK=<copy of sol26-ss20-build.raw> --var ISO=handover.iso --var DISK2=/mnt/sparc/runs/bb/bench.raw

The disk is changed (the build directory stays in /export/home/bench-build): give it a copy.

  PROMPT        the login prompt (regex)                                     (console login:)
  BUILD_TIMEOUT seconds for build.sh                                         (3600)

Metrics: compile_<name>_s (guest wall seconds of each compile: dhry, whetstone, nbench, lmbench).
"""
import re

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args
from idle import run_timed

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "DISK2_RO": "0", "DISK2_ID": "4",
            "PROMPT": "console login:", "BUILD_TIMEOUT": "3600"}


def qemu_args(v, out):
    if not v.get("DISK2"):
        raise SystemExit("set DISK2=<blank Sun-labelled disk> (bench/sunlabel.py)")
    return sparc32_args(v, out)


def run(m, v):
    prom_boot(m, v, "disk")
    login(m, v["PROMPT"])
    # vold mounts the CD under /cdrom/<volume name> (or is about to); a fixed place is simpler
    out, _ = run_timed(m, "/etc/init.d/volmgt stop; sleep 3; mount | nawk '$1 ~ /^.cdrom./ { print $1 }' | "
                          "xargs -n1 umount; mkdir -p /hand; mount -F hsfs -o ro /dev/dsk/c0t6d0s0 /hand && "
                          "echo HAND-MOUNTED")
    if not re.search(r"^HAND-MOUNTED", out, re.M):
        raise AssertionError(f"mounting the hand-over CD failed:\n{out}")
    m.send("sh /hand/bench/build.sh /hand c0t%sd0 2>&1; echo BUILD-END\r" % v["DISK2_ID"])
    out = m.expect(r"^((?:.*\n)*?)BUILD-END$", int(v["BUILD_TIMEOUT"])).group(1)
    m.snap("build.sh done")
    for name, s in re.findall(r"^COMPILE (\S+) ([\d.]+)", out, re.M):
        m.metrics[f"compile_{name}_s"] = float(s)
    if not re.search(r"^BUILD-OK", out, re.M):
        fail = re.search(r"^BUILD-FAILED.*", out, re.M)
        raise AssertionError(fail.group(0) if fail else f"no BUILD-OK:\n{out[-2000:]}")
    m.log(f"metrics: {m.metrics}")
    power_off(m, "init 5")
