#!/usr/bin/env python3
"""Record wisp's shell running a few commands as an asciinema v2 cast, in real time.

    record.py --arch sparc32 --out wisp-mandel-ss5.cast [--kernel K] [--machine M] [mandel ...]

Boots the tier-1 kernel with wisp=shell (the QEMU command line run.py uses), types each command at
the prompt a character at a time, as a person would, and ends with `poweroff`; the cast covers the
whole run from starting QEMU to its exit, with a marker per step (chapters in the asciinema player).
The console goes through the sparc lab's CastWriter (e2e/sparc/recording.py). The docs' wisp demo
casts (guide "wisp", "Mandelbrot on three architectures") are made with this and uploaded to the
`media` release by hand; they are not in git.
"""
import argparse
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sparc"))

import recording  # noqa: E402
import run  # noqa: E402
import shell  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arch", required=True, choices=sorted(run.ARCHES))
    ap.add_argument("--out", required=True, help="the cast to write")
    ap.add_argument("--kernel", help="default: out/<arch>/kernel")
    ap.add_argument("--machine", help="QEMU -M instead of the architecture's default")
    ap.add_argument("--qemu-dir", help="directory with the qemu-system-* binaries (default: PATH)")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--keydelay", type=float, default=0.08, help="seconds between typed characters")
    ap.add_argument("commands", nargs="*", default=["mandel"])
    args = ap.parse_args(argv)

    cmd = run.qemu_command(args.arch, args.qemu_dir, args.kernel, args.machine, interactive=True)
    machine = args.machine or run.ARCHES[args.arch][1][1]
    t0 = time.time()
    cast = recording.CastWriter(args.out, 80, 24, t0, title=f"wisp {args.arch} ({machine}): "
                                + ", ".join(args.commands + ["poweroff"]))
    print(" ".join(cmd), file=sys.stderr)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    text, cond = [""], threading.Condition()

    def reader():
        while True:
            data = os.read(proc.stdout.fileno(), 4096)
            if data:
                cast.output(data)
            with cond:
                if not data:
                    text.append(None)
                    cond.notify_all()
                    return
                text[0] += data.decode("utf-8", "replace")
                cond.notify_all()

    threading.Thread(target=reader, daemon=True).start()
    timer = threading.Timer(args.timeout, proc.kill)
    timer.start()

    def wait_prompt(count):
        with cond:
            while not (len(shell.PROMPT.findall(shell.clean(text[0]))) >= count
                       and re.search(r"> $", shell.clean(text[0]))):
                if text[-1] is None:
                    return False
                cond.wait(0.5)
        return True

    cast.marker("1. boot")
    times, ok = {}, True
    for n, command in enumerate(args.commands + ["poweroff"], 1):
        if not wait_prompt(n):
            ok = False
            break
        times.setdefault("prompt", f"{time.time() - t0:.1f} s")
        time.sleep(0.6)
        cast.marker(f"{n + 1}. {command}")
        for ch in command + "\n":
            proc.stdin.write(ch.encode())
            proc.stdin.flush()
            time.sleep(args.keydelay)
    rc = proc.wait()
    timer.cancel()
    time.sleep(0.2)
    cast.close()
    times["exit"] = f"{time.time() - t0:.1f} s"
    footer = shell.FOOTER.search(shell.clean(text[0]))
    if footer:  # mandel's own line: points and milliseconds
        times["mandel"] = shell.clean(text[0])[footer.start():].splitlines()[0].strip()
    print(f"{args.out}: QEMU exit {rc}, " + ", ".join(f"{k} {v}" for k, v in times.items()),
          file=sys.stderr)
    return 0 if ok and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
