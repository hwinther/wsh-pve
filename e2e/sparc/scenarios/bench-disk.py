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
  NET          the NIC's peer for the nic_* tests: user (QEMU user networking), tap (needs
               --cap-add NET_ADMIN --device /dev/net/tun) or none (BENCH-SKIP)  (user)
  PEER_DIR     lmbench's programs for the Linux side (the lab image builds them)  (/opt/lmbench-peer)

The nic_* tests (bench/README, "Network"): le0 gets 10.0.2.15/24 at run time (ifconfig only, nothing
written to the disk), lmbench's lat_tcp, lat_udp and bw_tcp servers run in the lab container and
run.sh's clients reach them at 10.0.2.2 (BENCH_PEER). Then the other direction: bw_tcp's server in the
guest, its client in the container, through a host forward (user) or straight to 10.0.2.15 (tap).

Metrics: every BENCH value under its name (units in bench.txt, run.sh's output; nic_bw_out is measured
here), boot_s (QEMU start to the login prompt), run_s (host seconds of run.sh), run_cpu_pct (QEMU's
host CPU use meanwhile, % of one core), cpus, mem_mb, load1_start/load1_end (host load average). Fails
on a BENCH-ERROR line, on no BENCH lines, or when DISK2 doesn't exist; BENCH-SKIP lines (left out on
that release, or no NIC peer) only show in bench.txt.
"""
import os
import re
import subprocess
import time

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args
from idle import run_timed

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "DISK2_ID": "4", "DISK2_RO": "1",
            "PROMPT": "console login:", "ONLY": "", "RUN_TIMEOUT": "3600", "NET": "user",
            "PEER_DIR": "/opt/lmbench-peer"}
GUEST, PEER = "10.0.2.15", "10.0.2.2"  # user networking's guest and host side; NET=tap uses the same
BW_PORT = 31236  # bw_tcp's port (lmbench's TCP_DATA)
SERVERS = ("lat_tcp", "lat_udp", "bw_tcp")


def load1():
    with open("/proc/loadavg", encoding="ascii") as f:
        return float(f.read().split()[0])


def peer(v, *args, timeout=150):
    """Run one of the Linux-side lmbench programs and return its output (lmbench writes to stderr). A
    server (-s) forks into the background and would hold on to a pipe, so it gets no output to keep."""
    cmd = [os.path.join(v["PEER_DIR"], args[0]), *args[1:]]
    env = {**os.environ, "ENOUGH": "100000"}  # as run.sh's lmbench
    if args[1:2] == ("-s",):
        subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=timeout, check=True)
        return ""
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"killed after {timeout} s"
    return r.stdout + r.stderr


def nic_bw_out(m, v):
    """bw_tcp from the guest to the peer: the server (which sends) in the guest, the client (which
    receives and times) in the lab container. Returns a BENCH or BENCH-ERROR line."""
    target = GUEST
    if v["NET"] == "user":
        target = "127.0.0.1"
        m.hmp(f"hostfwd_add tcp:{target}:{BW_PORT}-{GUEST}:{BW_PORT}")
    try:
        run_timed(m, "/bench/bin/bw_tcp -s")
        out = peer(v, "bw_tcp", target)
        run_timed(m, "/bench/bin/bw_tcp -S localhost", 120)
    finally:
        if v["NET"] == "user":
            m.hmp(f"hostfwd_remove tcp:{target}:{BW_PORT}")
    m.log(f"bw_tcp {target}: {out.strip()}")
    value = re.search(r"([\d.]+) MB/sec\s*$", out)
    if not value or "killed" in out:
        return "BENCH-ERROR nic_bw_out " + " ".join(out.split()[-12:])
    return f"BENCH nic_bw_out {value.group(1)} MB/s"


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
    # The nic_* tests: run.sh's "nic" part, unless ONLY leaves it out (run.sh's rule: a prefix of "nic")
    nic = v["NET"] in ("user", "tap") and "nic".startswith(v["ONLY"])
    if nic and not os.path.isfile(os.path.join(v["PEER_DIR"], "bw_tcp")):
        m.log(f"no lmbench peer in {v['PEER_DIR']}: the nic_* tests are skipped")
        nic = False
    env = ""
    if nic:
        out, _ = run_timed(m, f"ifconfig le0 plumb 2>/dev/null; ifconfig le0 {GUEST} netmask 255.255.255.0 "
                              f"broadcast 10.0.2.255 up && ping {PEER} 10")
        if not re.search(rf"^{PEER} is alive", out, re.M):
            raise AssertionError(f"le0: no answer from {PEER} (NET={v['NET']}):\n{out}")
        for prog in SERVERS:
            peer(v, prog, "-s")
        env = f"BENCH_PEER={PEER} "
    c0, t0 = m.cpu_seconds(), time.time()
    m.send(f"{env}sh /bench/run.sh {v['ONLY']} 2>&1; echo RUN-END\r")
    out = m.expect(r"^((?:.*\n)*?)RUN-END$", int(v["RUN_TIMEOUT"])).group(1)
    m.metrics["run_s"] = round(time.time() - t0, 1)
    m.metrics["run_cpu_pct"] = round(100 * (m.cpu_seconds() - c0) / (time.time() - t0), 1)
    m.snap("run.sh done")
    body = out[out.find("BENCH-BEGIN"):]
    if nic:
        for prog in SERVERS:
            peer(v, prog, "-S", "127.0.0.1", timeout=60)
        end = body.rfind("BENCH-END")
        if end >= 0:
            body = body[:end] + nic_bw_out(m, v) + "\n" + body[end:]
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
