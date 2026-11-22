#!/usr/bin/env python3
"""Checks that wisp's clock keeps up with the host when QEMU's main loop runs late, on the native
qemu-system-sparc the snapshot comes from.

    clock-check.py <qemu-system-sparc> <snapshot .state> [min ratio]

Linux on sun4m counts the system timer's interrupts to keep time. In the browser, QEMU's main loop
often wakes up later than the timer's 10 ms period (its poll() timeout is a setTimeout() on the
page's thread), and the timer then runs several periods at once; without
web/patches/slavio-timer-missed-ticks.patch all but one of those ticks were lost and the guest's
clock ran about 3x slow. Natively the main loop is on time, so this provokes the same thing: it
resumes the snapshot, stops QEMU with SIGSTOP for 2 s at a time (the virtual clock follows the
host clock, so 200 periods pass while it is stopped), and compares the guest's uptime (wisp's
`info`) with the host's clock. Exits 1 below the ratio (default 0.95).

Needs /fw/openbios-sparc32 and /wisp/kernel, as make-snapshot.py leaves them. Standard library only.
"""
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

import importlib.util

# make-snapshot.py's machine options and helpers (a hyphen in its name, so loaded by path)
_spec = importlib.util.spec_from_file_location(
    "make_snapshot", os.path.join(os.path.dirname(os.path.abspath(__file__)), "make-snapshot.py"))
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)

UPTIME = re.compile(r"uptime\s+(\d+\.\d+) s")


def main():
    qemu, state = sys.argv[1:3]
    min_ratio = float(sys.argv[3]) if len(sys.argv) > 3 else 0.95
    memory = int(re.search(r"-(\d+)m\.state$", state).group(1))
    root = tempfile.mkdtemp(prefix="wsh-clock-")
    con = os.path.join(root, "console.sock")
    proc = subprocess.Popen([qemu] + snap.machine_args(memory) + [
        "-chardev", f"socket,id=console,path={con},server=on,wait=on",
        "-incoming", f"file:{os.path.abspath(state)}",
    ])
    try:
        s = snap.connect(con, time.monotonic() + 30)
        s.settimeout(60)
        buf = b""

        def until(pattern):
            nonlocal buf
            while True:
                m = pattern.search(snap.ANSI.sub("", buf.decode("utf-8", "replace")))
                if m:
                    return m
                data = s.recv(65536)
                if not data:
                    raise RuntimeError("console closed")
                buf += data

        def uptime():
            nonlocal buf
            buf = b""
            t0 = time.monotonic()
            s.sendall(b"info\r")
            guest = float(until(UPTIME).group(1))
            return (t0 + time.monotonic()) / 2, guest

        time.sleep(1)
        s.sendall(b"\r")
        until(re.compile(re.escape(snap.PROMPT)))
        w0, g0 = uptime()
        for _ in range(5):
            proc.send_signal(signal.SIGSTOP)
            time.sleep(2)
            proc.send_signal(signal.SIGCONT)
            time.sleep(1)
        w1, g1 = uptime()
        ratio = (g1 - g0) / (w1 - w0)
        print(f"clock-check: guest {g1 - g0:.2f} s in {w1 - w0:.2f} s of host time with QEMU stopped "
              f"10 s of it: ratio {ratio:.3f} (minimum {min_ratio})", file=sys.stderr)
        return 0 if ratio >= min_ratio else 1
    finally:
        proc.kill()
        proc.wait()


if __name__ == "__main__":
    sys.exit(main())
