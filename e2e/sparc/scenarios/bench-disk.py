"""Run the bench disk (README "The bench disk"): boot an installed Solaris disk with the bench disk as
DISK2 (read only, SCSI target 4), mount it, run its /bench/run.sh and put every `BENCH <name> <value>
<unit>` line into result.json, then `init 5`.

    lab.py run scenarios/bench-disk.py --out /mnt/sparc/runs/bd --var DISK=/mnt/sparc/runs/bd/disk.raw \
        --var DISK2=/mnt/sparc/disks/bench-sol26.raw --var MACHINE=SS-20

The installed disk is changed (first boot, logs): give it a copy. Only meaningful on an otherwise
idle host: the host's load average goes into result.json at the start and the end.

  PROMPT       the login prompt (regex)                                     (console login:)
  ONLY         run only the benchmarks whose name starts with this (run.sh's argument)  (all)
  RUN_TIMEOUT  seconds for run.sh                                           (3600)

Metrics: every BENCH value under its name (units in bench.txt, run.sh's output), boot_s (QEMU start
to the login prompt), run_s (host seconds of run.sh), run_cpu_pct (QEMU's host CPU use meanwhile, %
of one core), cpus, mem_mb, load1_start/load1_end (host load average). Fails on a BENCH-ERROR line, on
no BENCH lines, or when DISK2 doesn't exist; BENCH-SKIP lines (left out on that release) only show in
bench.txt.
"""
import os
import re
import time

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args
from idle import run_timed

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "DISK2_ID": "4", "DISK2_RO": "1",
            "PROMPT": "console login:", "ONLY": "", "RUN_TIMEOUT": "3600"}


def load1():
    with open("/proc/loadavg", encoding="ascii") as f:
        return float(f.read().split()[0])


def qemu_args(v, out):
    if not v.get("DISK2"):
        raise SystemExit("set DISK2=<the bench disk>")
    return sparc32_args(v, out)  # fails when DISK2 doesn't exist


def run(m, v):
    m.metrics["load1_start"] = load1()
    prom_boot(m, v, "disk")
    login(m, v["PROMPT"])
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    # The /dev links for target 4 exist only if the install saw a disk there: make them.
    dev = f"/dev/dsk/c0t{v['DISK2_ID']}d0s0"
    out, _ = run_timed(m, f"drvconfig; disks; mkdir -p /bench; mount -F ufs -o ro {dev} /bench && "
                          "test -f /bench/run.sh && echo BENCH-MOUNTED")
    if not re.search(r"^BENCH-MOUNTED", out, re.M):
        raise AssertionError(f"mounting the bench disk ({dev}) failed:\n{out}")
    m.snap("bench disk mounted")
    c0, t0 = m.cpu_seconds(), time.time()
    m.send(f"sh /bench/run.sh {v['ONLY']} 2>&1; echo RUN-END\r")
    out = m.expect(r"^((?:.*\n)*?)RUN-END$", int(v["RUN_TIMEOUT"])).group(1)
    m.metrics["run_s"] = round(time.time() - t0, 1)
    m.metrics["run_cpu_pct"] = round(100 * (m.cpu_seconds() - c0) / (time.time() - t0), 1)
    m.snap("run.sh done")
    body = out[out.find("BENCH-BEGIN"):]
    with open(os.path.join(m.out, "bench.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    m.metrics["cpus"] = len(re.findall(r"on-line", body))
    mem = re.search(r"Memory size: (\d+) Megabytes", body)
    m.metrics["mem_mb"] = int(mem.group(1)) if mem else None
    results = re.findall(r"^BENCH (\S+) ([-\d.e+]+) (\S+)\s*$", body, re.M)
    for name, value, _unit in results:
        m.metrics[name] = float(value)
    m.metrics["load1_end"] = load1()
    m.log(f"metrics: {m.metrics}")
    errors = re.findall(r"^BENCH-ERROR .*", body, re.M)
    if errors or not results or "BENCH-END" not in body:
        raise AssertionError("run.sh: " + ("; ".join(errors) if errors else f"no results:\n{body[-2000:]}"))
    run_timed(m, "cd /; umount /bench")
    power_off(m, "init 5")
