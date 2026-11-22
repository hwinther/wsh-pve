#!/usr/bin/env python3
"""Boots wisp's shell on a native qemu-system-sparc and saves the machine at the first prompt as a
migration stream, for the Browser SPARC page to start from (`-incoming file:...`) instead of booting.

    make-snapshot.py <qemu-system-sparc> <openbios-sparc32> <kernel> <out dir> [memory MB]

The native QEMU must be built from the same tree as the WebAssembly one (same version, same patches),
and the machine options must be the page's exactly, including the file paths inside the page's file
system (/fw, /wisp), since -bios and -kernel are loaded again before the incoming migration replaces
the RAM. Writes <out dir>/wisp-ss5-<memory>m.state (the stream) and wisp-ss5-<memory>m.log (the
console transcript up to the prompt, which the page shows in the terminal before it resumes).
Standard library only.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

PROMPT = "wisp:sparc32>"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def machine_args(memory):
    # Keep in step with docs/public/browser-sparc/browser-sparc.js.
    return [
        "-M", "SS-5", "-m", str(memory), "-nodefaults", "-display", "none", "-monitor", "none",
        "-serial", "chardev:console",
        "-bios", "/fw/openbios-sparc32", "-kernel", "/wisp/kernel",
        "-append", "console=ttyS0 wisp=shell",
    ]


def connect(path, deadline):
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            return s
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


class Qmp:
    def __init__(self, sock):
        self.f = sock.makefile("rwb")
        self._read()  # greeting
        self.cmd("qmp_capabilities")

    def _read(self):
        while True:
            msg = json.loads(self.f.readline())
            if "event" not in msg:
                return msg

    def cmd(self, name, **args):
        self.f.write(json.dumps({"execute": name, "arguments": args}).encode() + b"\n")
        self.f.flush()
        reply = self._read()
        if "error" in reply:
            raise RuntimeError(f"{name}: {reply['error']}")
        return reply["return"]


def main():
    qemu, bios, kernel, out = sys.argv[1:5]
    memory = int(sys.argv[5]) if len(sys.argv) > 5 else 128
    os.makedirs(out, exist_ok=True)
    name = f"wisp-ss5-{memory}m"
    root = tempfile.mkdtemp(prefix="wsh-snap-")
    try:
        # The page's paths, /fw/openbios-sparc32 and /wisp/kernel, as symlinks where they are
        # missing (this runs in a build container).
        for path, src in (("/fw/openbios-sparc32", bios), ("/wisp/kernel", kernel)):
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                os.symlink(os.path.abspath(src), path)
        con = os.path.join(root, "console.sock")
        qmp_path = os.path.join(root, "qmp.sock")
        args = [qemu] + machine_args(memory) + [
            "-chardev", f"socket,id=console,path={con},server=on,wait=on",
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
        ]
        proc = subprocess.Popen(args)
        deadline = time.monotonic() + 30
        s = connect(con, deadline)
        transcript = b""
        s.settimeout(120)
        start = time.monotonic()
        while PROMPT not in ANSI.sub("", transcript[-300:].decode("utf-8", "replace")):
            data = s.recv(65536)
            if not data:
                raise RuntimeError("console closed before the prompt")
            transcript += data
        print(f"prompt after {time.monotonic() - start:.1f} s", file=sys.stderr)
        time.sleep(0.5)  # let the guest settle in its read()
        q = Qmp(connect(qmp_path, time.monotonic() + 10))
        # Migrated while running (QEMU stops it for the last pass): a machine stopped first would
        # arrive paused, since the run state travels with the stream.
        state = os.path.join(out, name + ".state")
        if os.path.exists(state):
            os.unlink(state)
        q.cmd("migrate", uri=f"file:{os.path.abspath(state)}")
        while True:
            status = q.cmd("query-migrate").get("status")
            if status == "completed":
                break
            if status in ("failed", "cancelled"):
                raise RuntimeError(f"migration {status}")
            time.sleep(0.2)
        q.cmd("quit")
        proc.wait(timeout=30)
        with open(os.path.join(out, name + ".log"), "wb") as f:
            f.write(transcript)
        print(f"{state}: {os.path.getsize(state)} bytes", file=sys.stderr)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
