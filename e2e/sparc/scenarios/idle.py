"""Boot an installed disk, log in as root and measure what the idle guest costs the host: QEMU's CPU
use over SECONDS, whether the guest clock kept time meanwhile, and how long a CPU-bound command takes.

    lab.py run scenarios/idle.py --out /srv/sparc/runs/idle --var DISK=/srv/sparc/runs/idle/disk.raw \
        --var CPU_BELOW=10

The disk is changed (first boot, logs): give it a copy. Only meaningful on an otherwise idle host.

  PROMPT      the login prompt (regex)                          (console login:)
  CHECK       a command run after login; CHECK_EXPECT (regex) must be in its output  (none)
  SETTLE      seconds after login before measuring               (30)
  SECONDS     seconds to measure over                            (60)
  CPU_BELOW   fail unless QEMU uses less than this % of a core   (none)
  CPU_ABOVE   fail unless it uses more (a guest that doesn't idle) (none)
  CLOCK_SLACK seconds the guest clock may be off after SECONDS   (3)
  BUSY        a CPU-bound command, timed on the host             (dd if=/dev/zero of=/dev/null count=200000)
  BUSY_BELOW  fail unless it takes less than this many seconds   (none)
  TRACE_EXPECT a regex that must be in trace.log at the end (with TRACE)  (none)

The metrics (cpu_pct, clock_drift_s, busy_s) go to result.json. Machine options can go with the
machine type, e.g. MACHINE=SS-5,sunos-idle=off.
"""
import os
import re
import time

from _sparc32 import DEFAULTS as BASE, login, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "PROMPT": "console login:", "CHECK": "",
            "CHECK_EXPECT": "", "SETTLE": "30", "SECONDS": "60", "CPU_BELOW": "", "CPU_ABOVE": "",
            "CLOCK_SLACK": "3", "BUSY": "dd if=/dev/zero of=/dev/null count=200000", "BUSY_BELOW": "",
            "TRACE_EXPECT": ""}


def qemu_args(v, out):
    return sparc32_args(v, out)


def run_timed(m, command, timeout=600):
    """Run a shell command, returning its output and the host seconds from Return to the end marker."""
    m.send(f"{command}; echo END-OF-COMMAND")
    t0 = time.time()
    m.send("\r")
    out = m.expect(r"^((?:.*\n)*?)END-OF-COMMAND$", timeout).group(1)  # at a line start: not the echo
    return out, time.time() - t0


def guest_clock(m):
    """The guest's time of day in seconds and the host time it was read at."""
    out, _ = run_timed(m, "date '+T=%H:%M:%S'")
    h, mi, s = (int(x) for x in re.search(r"T=(\d\d):(\d\d):(\d\d)", out).groups())
    return h * 3600 + mi * 60 + s, time.time()


def run(m, v):
    prom_boot(m, v, "disk")
    login(m, v["PROMPT"])
    if v["CHECK"]:
        out, _ = run_timed(m, v["CHECK"])
        m.snap(f"check: {v['CHECK']}")
        if v["CHECK_EXPECT"] and not re.search(v["CHECK_EXPECT"], out):
            raise AssertionError(f"no {v['CHECK_EXPECT']!r} in the output of {v['CHECK']!r}:\n{out}")
    time.sleep(int(v["SETTLE"]))
    g0, h0 = guest_clock(m)
    m.cpu_use(int(v["SECONDS"]), v["CPU_BELOW"] or None, v["CPU_ABOVE"] or None)
    g1, h1 = guest_clock(m)
    drift = ((g1 - g0) % 86400) - (h1 - h0)
    m.metrics["clock_drift_s"] = round(drift, 1)
    m.log(f"guest clock: {(g1 - g0) % 86400}s over {h1 - h0:.1f}s on the host")
    if abs(drift) > float(v["CLOCK_SLACK"]):
        raise AssertionError(f"guest clock off by {drift:.1f}s after {h1 - h0:.0f}s")
    if v["BUSY"]:
        _, busy = run_timed(m, v["BUSY"])
        m.metrics["busy_s"] = round(busy, 1)
        m.log(f"{v['BUSY']}: {busy:.1f}s")
        if v["BUSY_BELOW"] and busy >= float(v["BUSY_BELOW"]):
            raise AssertionError(f"{v['BUSY']!r} took {busy:.1f}s, expected below {v['BUSY_BELOW']}s")
    m.snap("measured")
    if v["TRACE_EXPECT"]:
        trace = open(os.path.join(m.out, "trace.log"), encoding="utf-8", errors="replace").read()
        if not re.search(v["TRACE_EXPECT"], trace):
            raise AssertionError(f"no {v['TRACE_EXPECT']!r} in trace.log")
    m.stop()
