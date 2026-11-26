#!/usr/bin/env python3
"""Record one wisp-netbsd boot as an asciinema v2 cast, in real time.

    record.py --arch sparc32 --machine SS-4 --cast wisp-netbsd-ss4.cast [--out out] [--qemu-dir DIR]

Boots the kernel with run.py's QEMU command line and writes the serial console through the sparc
lab's CastWriter (e2e/sparc/recording.py), from starting QEMU to its exit at the power-off, with a
marker (a chapter in the asciinema player) at NetBSD's kernel banner, PID 1's banner and the result
line. Nothing is typed: PID 1 runs its checks and powers the machine off by itself. Exit code 0 when
the result line says status=ok and QEMU exited 0. The living museum's casts of the sun4m machines
that have no install recording (SS-4, SPARCclassic, LX, Voyager, SPARCbook) are made with this and
uploaded to the `media` release by hand; they are not in git.
"""
import argparse
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(HERE, "..", "sparc"))

import run  # noqa: E402  (wisp-netbsd's run.py)
import recording  # noqa: E402

LABELS = {"t_kernel": "NetBSD kernel", "t_banner": "PID 1", "t_result": "result"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arch", required=True, choices=sorted(run.ARCHES))
    ap.add_argument("--machine", help="QEMU -M instead of the architecture's default")
    ap.add_argument("--cast", required=True, help="the cast to write")
    ap.add_argument("--out", default=os.path.join(HERE, "out"), help="build output directory")
    ap.add_argument("--qemu-dir", help="directory with the qemu-system-* binaries (default: PATH)")
    ap.add_argument("--timeout", type=float, default=120)
    args = ap.parse_args(argv)

    cmd = run.qemu_command(args.arch, args.qemu_dir, None, args.machine, out=args.out)
    machine = args.machine or run.ARCHES[args.arch][1][1]
    t0 = time.time()
    cast = recording.CastWriter(args.cast, 80, 24, t0, title=f"wisp-netbsd {args.arch} ({machine}): boot to power-off")
    print(" ".join(cmd), file=sys.stderr)
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    timer = threading.Timer(args.timeout, proc.kill)
    timer.start()
    cast.marker("1. firmware")
    seen, times, buf, result = set(), {}, b"", ""
    while True:
        data = os.read(proc.stdout.fileno(), 4096)
        if not data:
            break
        cast.output(data)
        buf += data
        *lines, buf = buf.split(b"\n")
        for line in lines:
            text = line.decode("utf-8", "replace").strip("\r")
            for name, pattern in run.MARKERS:
                if name not in seen and pattern.search(text):
                    seen.add(name)
                    times[name] = round(time.time() - t0, 2)
                    cast.marker(f"{len(seen) + 1}. {LABELS.get(name, name)}")
            if text.startswith("WISP-RESULT "):
                result = text
    rc = proc.wait()
    timer.cancel()
    times["exit"] = round(time.time() - t0, 2)
    cast.close()
    ok = rc == 0 and "status=ok" in result
    print(f"{args.cast}: QEMU exit {rc}, " + ", ".join(f"{k} {v} s" for k, v in times.items())
          + f"; {result or 'no result line'}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
