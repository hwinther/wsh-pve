#!/usr/bin/env python3
"""Drive fbtest on serial and verify the visible pixels through QMP."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import run

DISPLAYS = {"sparc32": ("cg3", "tcx"), "sparc64": ("std",), "x86_64": ("std",)}
RGB = [bytes(255 if index & bit else 0 for bit in (4, 2, 1)) for index in range(8)]
MODE = re.compile(rb"WISP-FB v=1 dev=/dev/fb0 xres=(\d+) yres=(\d+) bpp=(8|16|32) "
                  rb"visual=(\d+) line=(\d+) drawn=1\r?\n")


def check_ppm(data, width, height):
    header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\n", data)
    if not header or tuple(map(int, header.groups())) != (width, height):
        raise ValueError(f"expected a {width}x{height} P6 screendump")
    pixels = memoryview(data)[header.end():]
    if width < 16 or height < 3 or len(pixels) != width * height * 3:
        raise ValueError("invalid raster dimensions or length")
    border = RGB[7] * width
    interior = RGB[7] + b"".join(RGB[x * 8 // width] for x in range(1, width - 1)) + RGB[7]
    for y in range(height):
        expected = border if y in (0, height - 1) else interior
        row = pixels[y * width * 3:(y + 1) * width * 3]
        if row != expected:
            x = next(i for i, (a, b) in enumerate(zip(row, expected)) if a != b) // 3
            raise ValueError(f"pixel ({x},{y}) is {tuple(row[3*x:3*x+3])}, "
                             f"expected {tuple(expected[3*x:3*x+3])}")


async def qmp(reader, writer, command, **arguments):
    writer.write(json.dumps({"execute": command, "arguments": arguments}).encode() + b"\n")
    await writer.drain()
    while True:
        reply = json.loads(await reader.readline())
        if "return" in reply:
            return
        if "event" not in reply:
            raise RuntimeError(f"{command}: {reply}")


async def exercise(proc, arch, display, monitor, ppm, log):
    async def until(marker):
        try:
            data = await proc.stdout.readuntil(marker)
        except asyncio.IncompleteReadError as exc:
            log.write(exc.partial)
            raise RuntimeError(f"QEMU exited before {marker!r}; see {log.name}") from exc
        log.write(data)
        return data

    prompt = b"\x1b[0m> "
    await until(prompt)
    proc.stdin.write(b"fbtest\n")
    answer = await until(prompt)
    mode = MODE.search(answer)
    if not mode:
        raise RuntimeError(f"{arch}/{display}: {answer.decode(errors='replace')}")
    print(f"{arch}/{display} {mode[0].decode().strip()}", flush=True)
    width, height, bpp, visual, stride = map(int, mode.groups())
    if (bpp, visual) not in ((8, 3), (16, 2), (32, 2)) or stride < width * (bpp // 8):
        raise ValueError(f"unexpected framebuffer layout: {mode[0]!r}")
    reader, writer = await asyncio.open_unix_connection(monitor)
    try:
        if "QMP" not in json.loads(await reader.readline()):
            raise RuntimeError("missing QMP greeting")
        await qmp(reader, writer, "qmp_capabilities")
        # DRM may defer copying the fbdev shadow buffer to VGA memory.
        for attempt in range(10):
            await qmp(reader, writer, "screendump", filename=str(ppm))
            try:
                check_ppm(ppm.read_bytes(), width, height)
                break
            except ValueError:
                if attempt == 9:
                    raise
                await asyncio.sleep(0.1)
    finally:
        writer.close()
        await writer.wait_closed()
    proc.stdin.write(b"poweroff\n")
    log.write(await proc.stdout.read())
    if await proc.wait():
        raise RuntimeError(f"{arch}/{display}: QEMU exited with {proc.returncode}")
    print(f"{ppm}: all {width * height} pixels passed")


async def boot(arch, display, dest, timeout):
    machine = run.ARCHES[arch][1][1]
    stem = dest / f"{machine}-{display}"
    with tempfile.TemporaryDirectory() as tmp, stem.with_suffix(".log").open("wb") as log:
        monitor = Path(tmp) / "qmp"
        cmd = run.qemu_command(arch, kernel=str(Path(run.HERE) / "out" / arch / "kernel-fb"),
                               firmware=os.getenv("WISP_FIRMWARE"), interactive=True,
                               extra=["-vga", display, "-qmp", f"unix:{monitor},server=on,wait=off"])
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        try:
            await asyncio.wait_for(exercise(proc, arch, display, monitor,
                                            stem.with_suffix(".ppm"), log), timeout)
        finally:
            if proc.returncode is None:
                proc.kill()
                log.write((await proc.communicate())[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=DISPLAYS, action="append")
    parser.add_argument("--output", type=Path, default=Path(run.HERE) / "out/framebuffer")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    failures = 0
    for arch in args.arch or DISPLAYS:
        for display in DISPLAYS[arch]:
            try:
                asyncio.run(boot(arch, display, args.output.resolve(), args.timeout))
            except (OSError, ValueError, RuntimeError, EOFError, asyncio.TimeoutError) as exc:
                print(f"{arch}/{display}: {type(exc).__name__}: {exc}", file=sys.stderr)
                failures += 1
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
