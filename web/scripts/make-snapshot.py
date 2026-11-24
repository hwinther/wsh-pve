#!/usr/bin/env python3
"""Boots wisp's shell on a native QEMU and saves the machine at the first prompt as a migration
stream, for the Browser SPARC page to start from (`-incoming file:...`) instead of booting.

    make-snapshot.py <machines.json> <arch> <qemu dir> <files dir> <out dir> [memory MB]

<machines.json> is the page's machine table (docs/public/browser-sparc/machines.json), <arch> one
of its keys. The native QEMU (<qemu dir>/<qemu>) must be built from the same tree as the
WebAssembly one (same version, same patches), and the machine options must be the page's exactly,
including the file paths inside the page's file system (/fw/..., /wisp/...), since the firmware and
the kernel are loaded again before the incoming migration replaces the RAM. <files dir> holds the
page's files by their page names (firmware, kernel); they are linked to those paths. Writes
<out dir>/<snapshot>-<memory>m.state (the stream) and <snapshot>-<memory>m.log (the console
transcript up to the prompt, which the page shows in the terminal before it resumes).
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

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def load_machines(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prompt(arch):
    """wisp's shell prompt on <arch>, without its colours."""
    return f"wisp:{arch}>"


def kernel_path(machine):
    return "/wisp/" + machine["kernel"]


def machine_args(machine, memory=None):
    """The page's QEMU options for one machine, less the console's -chardev (the page's is a pipe,
    these scripts use a socket). Keep in step with docs/public/browser-sparc/browser-sparc.js."""
    return [
        *machine["args"], "-m", str(memory or machine["memory"]), "-nodefaults",
        "-display", "none", "-monitor", "none", "-serial", "chardev:console",
        "-kernel", kernel_path(machine), "-append", machine["append"],
    ]


def page_files(machine):
    """{page file name: path in the page's file system} for the firmware and the kernel."""
    return {**machine["files"], machine["kernel"]: kernel_path(machine)}


def link_files(machine, files_dir):
    """The page's paths as symlinks to <files dir>, where they are missing (this runs in a build
    container)."""
    for name, path in page_files(machine).items():
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            os.symlink(os.path.abspath(os.path.join(files_dir, name)), path)


def snapshot_name(machine, memory=None):
    return f"{machine['snapshot']}-{memory or machine['memory']}m"


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
    machines_json, arch, qemu_dir, files_dir, out = sys.argv[1:6]
    machine = load_machines(machines_json)[arch]
    memory = int(sys.argv[6]) if len(sys.argv) > 6 else machine["memory"]
    os.makedirs(out, exist_ok=True)
    name = snapshot_name(machine, memory)
    root = tempfile.mkdtemp(prefix="wsh-snap-")
    try:
        link_files(machine, files_dir)
        con = os.path.join(root, "console.sock")
        qmp_path = os.path.join(root, "qmp.sock")
        args = [os.path.join(qemu_dir, machine["qemu"])] + machine_args(machine, memory) + [
            "-chardev", f"socket,id=console,path={con},server=on,wait=on",
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
        ]
        proc = subprocess.Popen(args)
        deadline = time.monotonic() + 30
        s = connect(con, deadline)
        transcript = b""
        s.settimeout(120)
        start = time.monotonic()
        while prompt(arch) not in ANSI.sub("", transcript[-300:].decode("utf-8", "replace")):
            data = s.recv(65536)
            if not data:
                raise RuntimeError("console closed before the prompt")
            transcript += data
        print(f"{arch}: prompt after {time.monotonic() - start:.1f} s", file=sys.stderr)
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
