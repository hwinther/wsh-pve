"""Load a multiprocessor Solaris guest for a while and check that it stays up, with every CPU
on-line and busy, and time how much a parallel workload gains from the CPUs. Boots an installed
disk with the bench disk (DISK2, "The bench disk") on target 4. Ends with `init 5`.

    lab.py run scenarios/smp-soak.py --out /mnt/sparc/runs/s1 --var DISK=<copy of an installed disk> \
        --var DISK2=/mnt/sparc/disks/bench-sol26.raw --var MACHINE=SS-20 --var SMP=2 --var SOAK=1800

Steps: psrinfo must list SMP CPUs on-line; the speed-up: one copy of each JOBS benchmark, then SMP
copies at once (host seconds from Return to the end; `speedup` = SMP x one / all); the soak: SMP + 1
shell loops for SOAK seconds, each round running Dhrystone, Hanoi, the nawk loop, a tar of the bench
disk through compress/uncompress (its cksum checked against a reference), a 10 MB write and a fork
loop, while `mpstat 60` records the CPUs; every 300 s psrinfo again, which must answer within 120 s.
Afterwards the round counts, no cksum mismatch, every CPU on-line, and in the mpstat samples every
CPU busy (usr + sys at least BUSY %, median over the samples).

  SOAK      seconds of load, 0 = the speed-up only                              (1800)
  BUSY      the median usr + sys % each CPU must reach during the soak         (50)
  PROMPT    the login prompt (regex)                                            (console login:)
  BOOT_TIMEOUT seconds from QEMU start to the login prompt                      (1800)

Metrics: cpus, boot_s, for each job one_s/par_s/speedup (dhry, nawk), soak_s, rounds (all
loops), cksum_errors, cpu_busy_min (the least busy CPU's median usr + sys), soak_cpu_pct (QEMU's host
CPU use during the soak, % of one core), soak_cpu_per_vcpu.
"""
import re
import statistics
import time

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args
from idle import run_timed

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "DISK2_ID": "4", "DISK2_RO": "1",
            "PROMPT": "console login:", "SOAK": "1800", "BUSY": "50", "BOOT_TIMEOUT": "1800"}

# Fixed amounts of work; one copy of each takes ~5-12 s on one emulated SuperSPARC
JOBS = {
    "dhry": "echo 20000000 | /bench/bin/dhry >/dev/null",
    "nawk":"nawk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}' >/dev/null",
}

# The soak's loop, one shell per copy: $1 = its number. Lines short enough for the tty.
LOOP = r"""n=0
while [ -f /tmp/soak ]; do
echo 2000000 | /bench/bin/dhry >/dev/null
/bench/bin/hanoi 2 >/dev/null 2>&1
nawk 'BEGIN{for(i=0;i<200000;i++)s=(s+i*i)%9973;print s}' >/dev/null
c=`cd /bench; tar cf - bin | compress | uncompress | cksum`
[ "$c" = "`cat /tmp/ref`" ] || echo "$1 $n $c" >> /tmp/soak.err
dd if=/dev/zero of=/var/tmp/soak$1 bs=64k count=160 2>/dev/null; rm -f /var/tmp/soak$1
i=0; while [ $i -lt 20 ]; do i=`expr $i + 1`; done
n=`expr $n + 1`; echo $n > /tmp/soak.n$1
done"""


def qemu_args(v, out):
    if not v.get("DISK2"):
        raise SystemExit("set DISK2=<the bench disk>")
    return sparc32_args(v, out)


def heredoc(m, path, lines, timeout=600):
    """Write lines into a guest file with a here-document and wait for the shell. Not run_timed: on a
    slow guest the echo of what was typed ahead can land before the marker on its line."""
    m.send(f"cat > {path} <<'EOF'\r")
    for line in lines:
        m.send(line + "\r")
    m.send("EOF\recho WRITTEN-''DONE\r")
    m.expect(r"WRITTEN-DONE", timeout)


def online(m):
    out, _ = run_timed(m, "psrinfo", 120)
    return len(re.findall(r"on-line", out)), out


def run(m, v):
    smp = int(v.get("SMP") or 1)
    prom_boot(m, v, "disk")
    login(m, v["PROMPT"], int(v["BOOT_TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    dev = f"/dev/dsk/c0t{v['DISK2_ID']}d0s0"
    out, _ = run_timed(m, f"drvconfig; disks; mkdir -p /bench; mount -F ufs -o ro {dev} /bench && "
                          "test -x /bench/bin/dhry && echo BENCH-MOUNTED")
    if not re.search(r"^BENCH-MOUNTED", out, re.M):
        raise AssertionError(f"mounting the bench disk ({dev}) failed:\n{out}")
    n, out = online(m)
    m.metrics["cpus"] = n
    m.snap("CPUs")
    if n != smp:
        raise AssertionError(f"psrinfo lists {n} CPUs on-line, expected {smp}:\n{out}")

    for name, job in JOBS.items():
        # as a script: SMP copies of the command would not fit the tty's 256-character line
        heredoc(m, f"/tmp/{name}", [job])
        _, one = run_timed(m, f"sh /tmp/{name}")
        _, par = run_timed(m, " ".join([f"sh /tmp/{name} &"] * smp) + " wait")
        m.metrics[f"{name}_one_s"] = round(one, 1)
        m.metrics[f"{name}_par_s"] = round(par, 1)
        m.metrics[f"{name}_speedup"] = round(smp * one / par, 2)
    m.log(f"speed-up: {m.metrics}")
    if not int(v["SOAK"]):  # the speed-up only
        run_timed(m, "cd /; umount /bench")
        power_off(m, "init 5")
        return

    run_timed(m, "cd /bench; tar cf - bin | compress | uncompress | cksum > /tmp/ref; cd /; cat /tmp/ref")
    heredoc(m, "/tmp/loop.sh", LOOP.split("\n"))
    run_timed(m, "rm -f /tmp/soak.err /tmp/soak.n* /tmp/mpstat; touch /tmp/soak")
    soak = int(v["SOAK"])
    c0, t0 = m.cpu_seconds(), time.time()
    jobs = " ".join(f"sh /tmp/loop.sh {i} &" for i in range(smp + 1))
    run_timed(m, f"mpstat 60 {soak // 60} > /tmp/mpstat 2>&1 & {jobs} echo started")
    while time.time() - t0 < soak:
        time.sleep(min(300, max(0, soak - (time.time() - t0))))
        n, out = online(m)  # the guest must still answer
        m.log(f"{int(time.time() - t0)} s: {n} CPUs on-line")
        if n != smp:
            raise AssertionError(f"during the soak psrinfo lists {n} CPUs on-line:\n{out}")
    run_timed(m, "rm /tmp/soak; wait", 900)
    m.metrics["soak_s"] = round(time.time() - t0)
    cpu = 100 * (m.cpu_seconds() - c0) / (time.time() - t0)
    m.metrics["soak_cpu_pct"] = round(cpu, 1)
    m.metrics["soak_cpu_per_vcpu"] = round(cpu / smp, 1)

    # the markers are split in the command, so that its echo doesn't contain them
    out, _ = run_timed(m, "cat /tmp/soak.n*; echo ERR''ORS; cat /tmp/soak.err 2>/dev/null; echo MP''STAT; "
                          "cat /tmp/mpstat; psrinfo; uptime")
    out = out[out.find("\n") + 1:]  # the command's echo
    m.snap("after the soak")
    with open(f"{m.out}/soak.txt", "w", encoding="utf-8") as f:
        f.write(out)
    head, _, rest = out.partition("ERRORS")
    errors, _, rest = rest.partition("MPSTAT")
    m.metrics["rounds"] = sum(int(x) for x in re.findall(r"^(\d+)\s*$", head, re.M))
    m.metrics["cksum_errors"] = len([x for x in errors.splitlines() if x.strip()])
    # mpstat: CPU minf mjf xcal intr ithr csw icsw migr smtx srw syscl usr sys wt idl; the first
    # sample is since boot, so it is left out
    busy = {}
    for line in rest.splitlines():
        f = line.split()
        if len(f) == 16 and f[0].isdigit():
            busy.setdefault(int(f[0]), []).append(int(f[12]) + int(f[13]))
    medians = {c: statistics.median(s[1:]) for c, s in busy.items() if len(s) > 1}
    m.metrics["cpu_busy"] = medians
    m.metrics["cpu_busy_min"] = min(medians.values()) if medians else None
    m.log(f"metrics: {m.metrics}")
    if m.metrics["rounds"] == 0 or m.metrics["cksum_errors"]:
        raise AssertionError(f"soak: {m.metrics['rounds']} rounds, {m.metrics['cksum_errors']} cksum errors")
    if len(medians) != smp or m.metrics["cpu_busy_min"] < int(v["BUSY"]):
        raise AssertionError(f"mpstat: not every CPU busy: {medians}")
    n, out = online(m)
    if n != smp:
        raise AssertionError(f"after the soak psrinfo lists {n} CPUs on-line:\n{out}")
    run_timed(m, "cd /; umount /bench")
    power_off(m, "init 5")
