"""Boot an installed Solaris disk, log in and time a fixed set of jobs, so machine configurations
(machine, firmware, CPUs, RAM) can be compared. Ends with `init 5`, so the disk can be booted again.

    lab.py run scenarios/bench.py --out /mnt/runs/b1 --var DISK=/mnt/runs/b1/disk.raw \
        --var MACHINE=SS-20 --var SMP=2

The disk is changed: give it a copy that has been booted once (solaris-boot-disk.py), or the first
boot's questions count towards the boot time. Only meaningful with nothing else running on the host.

  PROMPT    the login prompt (regex)                                         (console login:)
  SETTLE    seconds after login before measuring                             (30)
  SECONDS   seconds over which QEMU's host CPU use is measured at idle        (30)
  JOB       a CPU-bound command (only tools of the End User install)          (a nawk loop)
  PARALLEL  copies of JOB run at once for the throughput time                (SMP)
  DISK_MB   MB written to a file in /export/home (then sync) and read from its raw slice (64; with
            more than one CPU, Solaris 2.6 hung writing 256 MB before pve-qemu patch 0019, see
            submodules/SPARC.md)
  BOOT_TIMEOUT seconds from QEMU start to the login prompt                   (600)
  CPUS      fail unless psrinfo lists this many CPUs on-line                 (SMP)
  SOAK      seconds of PARALLEL copies of JOB and dd in a loop afterwards; the guest must still
            answer and psrinfo still list CPUS on-line                       (0: none)

Metrics (result.json; times are host seconds from Return to the end of the command): boot_s (QEMU
start to the login prompt), cpus, mem_mb, idle_cpu_pct, job_s, parallel_s, parallel_cpu_pct (QEMU's
host CPU use during the parallel run, in % of one core), write_s, read_s.
"""
import re
import time

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args
from idle import run_timed

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "PROMPT": "console login:", "SETTLE": "30",
            "SECONDS": "30", "JOB": "nawk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}'",
            "PARALLEL": "", "DISK_MB": "64", "CPUS": "", "SOAK": "0", "BOOT_TIMEOUT": "600"}


def qemu_args(v, out):
    return sparc32_args(v, out)


def write_file(m, path, line):
    """Put one line into a guest file through a here-document: a command line longer than the tty's
    256 characters would be cut off, so the long ones run as scripts."""
    m.send(f"cat > {path} <<'EOF'\r{line}\rEOF\r")
    run_timed(m, "true")


def run(m, v):
    smp = int(v.get("SMP") or 1)
    parallel, cpus = int(v["PARALLEL"] or smp), int(v["CPUS"] or smp)
    prom_boot(m, v, "disk")
    login(m, v["PROMPT"], int(v["BOOT_TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    out, _ = run_timed(m, "psrinfo -v; prtconf | grep Memory")
    m.snap("CPUs and memory")
    m.metrics["cpus"] = len(re.findall(r"on-line", out))
    mem = re.search(r"Memory size: (\d+) Megabytes", out)
    m.metrics["mem_mb"] = int(mem.group(1)) if mem else None
    if m.metrics["cpus"] != cpus:
        raise AssertionError(f"psrinfo lists {m.metrics['cpus']} CPUs on-line, expected {cpus}:\n{out}")
    time.sleep(int(v["SETTLE"]))
    m.metrics["idle_cpu_pct"] = round(m.cpu_use(int(v["SECONDS"])), 1)
    del m.metrics["cpu_pct"]

    write_file(m, "/tmp/job", v["JOB"])
    _, t = run_timed(m, "sh /tmp/job >/dev/null")
    m.metrics["job_s"] = round(t, 1)
    c0, t0 = m.cpu_seconds(), time.time()
    _, t = run_timed(m, " ".join(["sh /tmp/job >/dev/null &"] * parallel) + " wait")
    m.metrics["parallel_s"] = round(t, 1)
    m.metrics["parallel_cpu_pct"] = round(100 * (m.cpu_seconds() - c0) / (time.time() - t0), 1)
    # /export/home (s7) is the big slice of the End User auto-layout; / has ~50 MB free
    count = int(v["DISK_MB"]) * 16
    for key, dd in (("write_s", f"dd if=/dev/zero of=/export/home/bench bs=64k count={count}; sync"),
                    ("read_s", f"dd if=/dev/rdsk/c0t3d0s7 of=/dev/null bs=64k count={count}")):
        out, t = run_timed(m, dd)
        if f"{count}+0 records out" not in out:
            raise AssertionError(f"{dd}:\n{out}")
        m.metrics[key] = round(t, 1)
    run_timed(m, "rm -f /export/home/bench")
    m.snap("measured")
    m.log(f"metrics: {m.metrics}")

    if int(v["SOAK"]):
        # PARALLEL shells, each running JOB and a dd round trip until /tmp/soak disappears
        write_file(m, "/tmp/soak.sh", "while [ -f /tmp/soak ]; do sh /tmp/job >/dev/null; dd if=/dev/zero "
                   "of=/var/tmp/soak$1 bs=64k count=160 2>/dev/null; rm -f /var/tmp/soak$1; done")
        jobs = " ".join(f"sh /tmp/soak.sh {i} &" for i in range(parallel))
        m.send(f"touch /tmp/soak; {jobs} sleep {v['SOAK']}; rm /tmp/soak; wait; echo SOAK-DONE\r")
        m.expect(r"^SOAK-DONE", int(v["SOAK"]) + 600)
        out, _ = run_timed(m, "psrinfo; uptime")
        m.snap("after the soak")
        online = len(re.findall(r"on-line", out))
        if online != cpus:
            raise AssertionError(f"after the soak psrinfo lists {online} CPUs on-line:\n{out}")
        m.metrics["soak_s"] = int(v["SOAK"])
    power_off(m, "init 5")
