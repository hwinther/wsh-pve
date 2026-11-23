#!/usr/bin/env python3
"""Boot the wisp HTTP demo and check it through QEMU's forwarded TCP port."""

import argparse
import asyncio
import http.client
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time

import run
import tier2


MACHINES = {"sparc32": "sparc", "x86_64": "x86_64", "sparc64": "sparc64", "aarch64": "aarch64"}
LOOPBACK = "127.0.0.1"


def check_response(status, body, machine, counter):
    pattern = rf"Linux [^\s]+ {machine} request={counter}\n" if counter else "bye\n"
    if status != 200 or not re.fullmatch(pattern.encode(), body):
        raise ValueError(f"unexpected HTTP response: {status} {body!r}")


def requests(port, machine):
    for path, counter in [("/", 1), ("/", 2), ("/quit", None)]:
        conn = http.client.HTTPConnection(LOOPBACK, port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read(1024)
            check_response(response.status, body, machine, counter)
            print(f"GET {path} -> {response.status} {body.decode().rstrip()}")
        finally:
            conn.close()


async def console(proc, port, arch, start):
    started = ready = exited = False
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        print(line)
        if line == "WISP-RUN v=1 start":
            started = True
        elif started and line == "WISP-HTTPD listening port=8080":
            print(f"boot to listening: {time.monotonic() - start:.3f} s")
            await asyncio.to_thread(requests, port, MACHINES[arch])
            ready = True
        elif ready and re.fullmatch(r"WISP-RUN v=1 exit=0 signal=0 ms=\d+", line):
            exited = True
    rc = await proc.wait()
    if rc or not exited:
        raise RuntimeError(f"QEMU exited with {rc}, service exit verified: {exited}")


async def boot(arch, archive, timeout):
    nic = tier2.PROFILES[tier2.family(arch)][0]["nic"]
    with socket.socket() as sock:
        sock.bind((LOOPBACK, 0))
        port = sock.getsockname()[1]
    cmd = run.qemu_command(
        arch, kernel=os.path.join(run.HERE, "out", arch, "kernel-net"),
        firmware=os.environ.get("WISP_FIRMWARE"),
        append_extra=["quiet", "wisp=run", "ip=dhcp", *tier2.kernel_args({"disks": ()}, arch)],
        extra=["-initrd", str(archive), "-nic", f"user,model={nic},hostfwd=tcp:{LOOPBACK}:{port}-:8080"])
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        await asyncio.wait_for(console(proc, port, arch, start), timeout)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.communicate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=MACHINES)
    parser.add_argument("--binary", required=True, help="static HTTP demo executable")
    parser.add_argument("--timeout", type=float, default=60, help="seconds for the whole run")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        test = Path(directory) / "test"
        shutil.copyfile(args.binary, test)
        test.chmod(0o755)
        archive = test.with_suffix(".cpio")
        with archive.open("wb") as out:
            subprocess.run(["cpio", "--quiet", "-o", "-H", "newc"], cwd=directory,
                           input=b"test\n", stdout=out, check=True)
        asyncio.run(boot(args.arch, archive, args.timeout))


if __name__ == "__main__":
    main()
