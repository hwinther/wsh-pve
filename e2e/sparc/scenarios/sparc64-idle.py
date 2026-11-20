"""Boot an installed sparc64 disk on sun4u, log in and measure what the idle guest costs the host (QEMU's
CPU use over SECONDS), whether the guest clock kept time, and how long a CPU-bound JOB takes; then
optionally LOAD seconds of load, and power off. The sparc64 counterpart of idle.py.

    lab.py run scenarios/sparc64-idle.py --out /mnt/runs/nb-idle --var GUEST=netbsd \
        --var DISK=/mnt/runs/nb-idle/disk.raw

The disk is changed: give it a copy. Only meaningful on an otherwise idle host.

  GUEST       netbsd | openbsd | debian | solaris10 (_sparc64.GUESTS), or tribblix (_tribblix.py: bash,
              init 5); the stored install-* disks take PASSWORD=wshlab
  CHECK       a command run after login; CHECK_EXPECT (regex) must be in its output  (none)
  WAIT        a command run after CHECK that ends what the guest still does after boot, or waits for
              it (TIMEOUT seconds), so that the guest is idle when measured: NetBSD's makemandb,
              Solaris's sendmail retries on the console               (none)
  SETTLE      seconds after login before measuring               (30)
  SECONDS     seconds to measure over                            (60)
  CPU_BELOW   fail unless QEMU uses less than this % of a core   (none)
  CPU_ABOVE   fail unless it uses more (a guest that doesn't idle) (none)
  CLOCK_SLACK seconds the guest clock may be off after SECONDS   (3)
  JOB         a CPU-bound command, timed on the host (the same awk loop runs on NetBSD sparc32, see
              submodules/SPARC.md; its input is /dev/null: Solaris's old awk reads it even with only a
              BEGIN rule)                                        (awk loop, 1000000 rounds)
  LOAD        seconds of load after the measurements: JOB and a 64 MB file written, read and removed,
              in a loop (needs a POSIX sh: not Solaris's /bin/sh); the guest must still answer
              afterwards                                         (0: none)
  TRACE_EXPECT a regex that must be in trace.log at the end (with TRACE; e.g. TRACE=sparc64_idle_match
              and "Solaris idle loop")                           (none)

Metrics (result.json): cpu_pct, clock_drift_s, job_s, sleep10_s (host time of ten `sleep 1`),
load_rounds.
"""
import os
import re
import time

import _tribblix
from _sparc64 import DEFAULTS as BASE, guest_defaults, login, power_off, qemu_args as sparc64_args, shell

JOB = "awk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}' </dev/null"
DEFAULTS = {**BASE, "BOOT": "c", "GUEST": "", "PROMPT": "", "USER": "", "PASSWORD": "", "POWEROFF": "",
            "COMMANDS": "", "CHECK": "", "CHECK_EXPECT": "", "WAIT": "", "SETTLE": "30", "SECONDS": "60",
            "CPU_BELOW": "", "CPU_ABOVE": "", "CLOCK_SLACK": "3", "JOB": JOB, "LOAD": "0", "TIMEOUT": "900",
            "TRACE_EXPECT": ""}


def qemu_args(v, out):
    guest_defaults(v)
    return sparc64_args(v, out)


def guest_clock(m):
    out, _ = shell(m, "date '+T=%H:%M:%S'")
    h, mi, s = (int(x) for x in re.search(r"T=(\d\d):(\d\d):(\d\d)", out).groups())
    return h * 3600 + mi * 60 + s, time.time()


def run(m, v):
    if v["GUEST"] == "tribblix":
        _tribblix.login(m, v["PASSWORD"], int(v["TIMEOUT"]))
    else:
        login(m, v, int(v["TIMEOUT"]))
    m.metrics["boot_s"] = round(m.elapsed(), 1)
    if v["CHECK"]:
        out, _ = shell(m, v["CHECK"])
        m.snap(f"check: {v['CHECK']}")
        if v["CHECK_EXPECT"] and not re.search(v["CHECK_EXPECT"], out):
            raise AssertionError(f"no {v['CHECK_EXPECT']!r} in the output of {v['CHECK']!r}:\n{out}")
    if v["WAIT"]:
        _, t = shell(m, v["WAIT"], int(v["TIMEOUT"]))
        m.log(f"{v['WAIT']}: {t:.0f}s")
    time.sleep(int(v["SETTLE"]))
    g0, h0 = guest_clock(m)
    m.cpu_use(int(v["SECONDS"]), v["CPU_BELOW"] or None, v["CPU_ABOVE"] or None)
    g1, h1 = guest_clock(m)
    drift = ((g1 - g0) % 86400) - (h1 - h0)
    m.metrics["clock_drift_s"] = round(drift, 1)
    m.log(f"guest clock: {(g1 - g0) % 86400}s over {h1 - h0:.1f}s on the host")
    if abs(drift) > float(v["CLOCK_SLACK"]):
        raise AssertionError(f"guest clock off by {drift:.1f}s after {h1 - h0:.0f}s")
    if v["JOB"]:
        out, t = shell(m, v["JOB"])
        m.metrics["job_s"] = round(t, 1)
        m.log(f"{v['JOB']}: {t:.1f}s ({out.strip()[-40:]})")
    _, sleeps = shell(m, "; ".join(["sleep 1"] * 10))
    m.metrics["sleep10_s"] = round(sleeps, 1)
    m.snap("measured")
    if int(v["LOAD"]):
        # as a script: a command line over 255 characters is cut off by the BSD tty
        lines = [f"end=$(($(date +%s)+{v['LOAD']})); n=0", "while [ $(date +%s) -lt $end ]; do",
                 f"  {v['JOB']} >/dev/null",
                 "  dd if=/dev/zero of=/var/tmp/load bs=64k count=1024 2>/dev/null",
                 "  cat /var/tmp/load >/dev/null; rm -f /var/tmp/load; n=$((n+1))", "done; echo ROUNDS=$n"]
        m.send("cat > /tmp/load.sh <<'EOF'\r" + "\r".join(lines) + "\rEOF\r")
        shell(m, "true")
        out, _ = shell(m, "sh /tmp/load.sh", int(v["LOAD"]) + 900)
        m.metrics["load_rounds"] = int(re.search(r"ROUNDS=(\d+)", out).group(1))
        out, _ = shell(m, "uptime")
        m.snap("after the load")
    if v["TRACE_EXPECT"]:
        trace = open(os.path.join(m.out, "trace.log"), encoding="utf-8", errors="replace").read()
        if not re.search(v["TRACE_EXPECT"], trace):
            raise AssertionError(f"no {v['TRACE_EXPECT']!r} in trace.log")
    off = _tribblix.power_off(m) if v["GUEST"] == "tribblix" else power_off(m, v)
    m.metrics["poweroff_s"] = round(off, 1)
