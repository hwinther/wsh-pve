"""What an idle multiprocessor Solaris guest costs the host, and how fast work reaches its idle CPUs.
Boots an installed disk with the bench disk (DISK2, "The bench disk") on target 4, logs in as root,
measures QEMU's host CPU use at the shell and the guest clock, then times work that has to wake an
idle CPU: pipe round trips between two processes (lmbench lat_pipe), short processes (fork, exec,
`expr` in a shell loop), pipelines, `sleep`, and CPU-bound jobs alone and SMP at once. Ends with
`init 5`. For the multiprocessor idle halt (`solaris-smp-idle`); runs with one CPU as well.

    lab.py run scenarios/smp-idle.py --out /mnt/sparc/runs/si --var DISK=<copy of an installed disk> \
        --var DISK2=/mnt/sparc/disks/bench-sol26.raw --var MACHINE=SS-20 --var SMP=2

  SETTLE      seconds after login before measuring                          (30)
  SECONDS     seconds the idle host CPU use is measured over                (60)
  CPU_BELOW   fail unless that is below this % of a core                    (none)
  CLOCK_SLACK seconds the guest clock may be off after SECONDS              (3)
  ROUNDS      times each short test is repeated (the median is kept)        (3)
  STRESS      seconds of SMP + 1 shell loops that keep waking idle CPUs (short nawk jobs, `sleep 1`,
              pipelines, `expr`), psrinfo every 60 s; 0 = none              (0)
  PROMPT      the login prompt (regex)                                      (console login:)
  BOOT_TIMEOUT seconds from QEMU start to the login prompt                  (1800)

Metrics (result.json): cpus, boot_s, cpu_pct (idle), clock_drift_s, echo_ms (median host time from
Return to the end of `true`), sleep10_s (ten `sleep 1`), lat_pipe_us and lat_fork_us (lmbench, guest
microseconds), expr200_s (a shell loop of 200 `expr`), pipeline_s (dd | cat | cat of 10 MB in 512-byte
writes), burst_s (SMP short nawk jobs started together and waited for, ROUNDS times in a row),
dhry_one_s/dhry_par_s and nawk_one_s/nawk_par_s (one copy, then SMP copies at once, host seconds),
stress_cpu_pct (QEMU's host CPU use over the timed tests); with STRESS: stress_s, wake_rounds (all
loops' rounds), stress_wake_cpu_pct.
"""
import re
import statistics
import time

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args
from idle import guest_clock, run_timed

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "DISK2_ID": "4", "DISK2_RO": "1",
            "PROMPT": "console login:", "SETTLE": "30", "SECONDS": "60", "CPU_BELOW": "",
            "CLOCK_SLACK": "3", "ROUNDS": "3", "STRESS": "0", "BOOT_TIMEOUT": "1800"}

JOBS = {
    "dhry": "echo 20000000 | /bench/bin/dhry >/dev/null",
    "nawk": "nawk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}' >/dev/null",
}
SHORT = "nawk 'BEGIN{for(i=0;i<50000;i++)s=(s+i*i)%9973;print s}' >/dev/null"


def qemu_args(v, out):
    if not v.get("DISK2"):
        raise SystemExit("set DISK2=<the bench disk>")
    return sparc32_args(v, out)


def script(m, path, line):
    """A one-line guest script (no $, ` or "): SMP copies of a command would not fit the tty's line."""
    run_timed(m, f'echo "{line}" > {path}')


def lmbench_us(m, command):
    out, _ = run_timed(m, f"ENOUGH=100000 {command} 2>&1")
    found = re.findall(r"([\d.]+) microseconds", out)
    if not found:
        raise AssertionError(f"no result from {command!r}:\n{out}")
    return float(found[-1])


def run(m, v):
    smp = int(v.get("SMP") or 1)
    rounds = int(v["ROUNDS"])
    prom_boot(m, v, "disk")
    login(m, v["PROMPT"], int(v["BOOT_TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    dev = f"/dev/dsk/c0t{v['DISK2_ID']}d0s0"
    out, _ = run_timed(m, f"drvconfig; disks; mkdir -p /bench; mount -F ufs -o ro {dev} /bench && "
                          "test -x /bench/bin/lat_pipe && echo BENCH-MOUNTED")
    if not re.search(r"^BENCH-MOUNTED", out, re.M):
        raise AssertionError(f"mounting the bench disk ({dev}) failed:\n{out}")
    out, _ = run_timed(m, "psrinfo", 120)
    m.metrics["cpus"] = len(re.findall(r"on-line", out))
    if m.metrics["cpus"] != smp:
        raise AssertionError(f"psrinfo lists {m.metrics['cpus']} CPUs on-line, expected {smp}:\n{out}")

    # Idle
    time.sleep(int(v["SETTLE"]))
    g0, h0 = guest_clock(m)
    m.cpu_use(int(v["SECONDS"]), v["CPU_BELOW"] or None)
    g1, h1 = guest_clock(m)
    drift = ((g1 - g0) % 86400) - (h1 - h0)
    m.metrics["clock_drift_s"] = round(drift, 1)
    m.log(f"guest clock: {(g1 - g0) % 86400}s over {h1 - h0:.1f}s on the host")
    if abs(drift) > float(v["CLOCK_SLACK"]):
        raise AssertionError(f"guest clock off by {drift:.1f}s after {h1 - h0:.0f}s")
    times = sorted(run_timed(m, "true")[1] for _ in range(10))
    m.metrics["echo_ms"] = round(1000 * times[len(times) // 2])
    m.metrics["sleep10_s"] = round(run_timed(m, "; ".join(["sleep 1"] * 10))[1], 1)
    m.snap("idle measured")

    # Work that wakes an idle CPU
    c0, t0 = m.cpu_seconds(), time.time()
    m.metrics["lat_pipe_us"] = round(statistics.median(
        lmbench_us(m, "/bench/bin/lat_pipe") for _ in range(rounds)), 1)
    m.metrics["lat_fork_us"] = round(statistics.median(
        lmbench_us(m, "/bench/bin/lat_proc fork") for _ in range(rounds)), 1)
    m.metrics["expr200_s"] = round(statistics.median(
        run_timed(m, "i=0; while [ $i -lt 200 ]; do i=`expr $i + 1`; done")[1] for _ in range(rounds)), 2)
    m.metrics["pipeline_s"] = round(statistics.median(
        run_timed(m, "dd if=/dev/zero bs=512 count=20000 2>/dev/null | cat | cat >/dev/null")[1]
        for _ in range(rounds)), 2)
    script(m, "/tmp/short", SHORT)
    burst = " ".join(["sh /tmp/short &"] * max(smp, 2)) + " wait"
    m.metrics["burst_s"] = round(run_timed(m, "; ".join([burst] * rounds))[1], 2)
    for name, job in JOBS.items():
        script(m, f"/tmp/{name}", job)
        _, one = run_timed(m, f"sh /tmp/{name}")
        _, par = run_timed(m, " ".join([f"sh /tmp/{name} &"] * smp) + " wait")
        m.metrics[f"{name}_one_s"] = round(one, 1)
        m.metrics[f"{name}_par_s"] = round(par, 1)
    m.metrics["stress_cpu_pct"] = round(100 * (m.cpu_seconds() - c0) / (time.time() - t0), 1)
    m.log(f"metrics: {m.metrics}")
    m.snap("timed")
    if int(v["STRESS"]):
        stress(m, smp, int(v["STRESS"]))
    run_timed(m, "cd /; umount /bench")
    power_off(m, "init 5")


def stress(m, smp, seconds):
    """SMP + 1 shell loops that keep waking idle CPUs (short jobs, sleeps, pipes, short processes) for
    `seconds`, while psrinfo must answer every 60 s; then the rounds each loop managed."""
    run_timed(m, "rm -f /tmp/wake.n*; touch /tmp/wake")
    m.send("cat > /tmp/wake.sh <<'EOF'\r")
    for line in WAKE.split("\n"):
        m.send(line + "\r")
    m.send("EOF\recho WRITTEN-''DONE\r")
    m.expect(r"WRITTEN-DONE", 600)
    c0, t0 = m.cpu_seconds(), time.time()
    run_timed(m, " ".join(f"sh /tmp/wake.sh {i} &" for i in range(smp + 1)) + " echo started")
    while time.time() - t0 < seconds:
        time.sleep(min(60, max(0, seconds - (time.time() - t0))))
        out, took = run_timed(m, "psrinfo", 120)
        n = len(re.findall(r"on-line", out))
        m.log(f"{int(time.time() - t0)} s: {n} CPUs on-line, psrinfo {took:.1f} s")
        if n != smp:
            raise AssertionError(f"during the stress psrinfo lists {n} CPUs on-line:\n{out}")
    run_timed(m, "rm /tmp/wake; wait", 600)
    m.metrics["stress_s"] = round(time.time() - t0)
    m.metrics["stress_wake_cpu_pct"] = round(100 * (m.cpu_seconds() - c0) / (time.time() - t0), 1)
    out, _ = run_timed(m, "cat /tmp/wake.n*")
    m.metrics["wake_rounds"] = sum(int(x) for x in re.findall(r"^(\d+)\s*$", out, re.M))
    m.log(f"stress: {m.metrics['wake_rounds']} rounds in {m.metrics['stress_s']} s")


# The stress loop, one shell per copy: $1 = its number
WAKE = r"""n=0
while [ -f /tmp/wake ]; do
nawk 'BEGIN{for(i=0;i<20000;i++)s=(s+i*i)%9973;print s}' >/dev/null
sleep 1
dd if=/dev/zero bs=512 count=2000 2>/dev/null | cat | cat >/dev/null
i=0; while [ $i -lt 10 ]; do i=`expr $i + 1`; done
echo $n | cat | nawk '{print $1}' >/dev/null
n=`expr $n + 1`; echo $n > /tmp/wake.n$1
done"""
