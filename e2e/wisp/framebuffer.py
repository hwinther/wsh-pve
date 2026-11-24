#!/usr/bin/env python3
"""Verify framebuffer images and keyboard input through serial and QMP."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

import run
from shell import MANDEL_ITER, MANDEL_X0, mandel_count

DISPLAYS = {"sparc32": ("cg3", "tcx"), "sparc64": ("std",), "x86_64": ("std",),
            "aarch64": ("bochs-display",)}
RGB = [bytes(255 if index & bit else 0 for bit in (4, 2, 1)) for index in range(8)]
MODE = re.compile(rb"WISP-FB v=1 dev=/dev/fb0 xres=(\d+) yres=(\d+) bpp=(8|16|32) "
                  rb"visual=(\d+) line=(\d+) drawn=1\r?\n")


def display_args(display, arch=None):
    """The display's QEMU options and the machine's keyboard where it has none of its own."""
    if display == "bochs-display":
        return ["-device", display, "-device", "virtio-keyboard-pci"]
    if arch == "sparc64":
        # Linux probes sun4u's EBus i8042 only with openbios-sparc64 0035 and ps2-mouse?=true,
        # which no published package has yet, so a virtio keyboard
        return ["-vga", display, "-device", "virtio-keyboard-pci"]
    return ["-vga", display]


def mandel_image(width, height):
    """Return the sum of the iteration counts and the packed visible RGB rows."""
    xs = [MANDEL_X0 + 12288 * x // width for x in range(width)]
    rows = []
    checksum = 0
    palette = [RGB[0]] + [RGB[1 + (n - 1) % 7] for n in range(1, MANDEL_ITER)] + [RGB[0]]
    for y in range(height):
        cy = -4712 + 9424 * y // height
        counts = [mandel_count(cx, cy) for cx in xs]
        checksum += sum(counts)
        rows.append(b"".join(palette[n] for n in counts))
    return checksum & 0xffffffff, rows


def check_ppm(data, width, height, rows=None):
    header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\n", data)
    if not header or tuple(map(int, header.groups())) != (width, height):
        raise ValueError(f"expected a {width}x{height} P6 screendump")
    pixels = memoryview(data)[header.end():]
    if width < 16 or height < 3 or len(pixels) != width * height * 3:
        raise ValueError("invalid raster dimensions or length")
    border = RGB[7] * width
    interior = RGB[7] + b"".join(RGB[x * 8 // width] for x in range(1, width - 1)) + RGB[7]
    for y in range(height):
        expected = rows[y] if rows is not None else (border if y in (0, height - 1) else interior)
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


async def check_keyboard(proc, arch, display, reader, writer, until, prompt):
    proc.stdin.write(b"keytest\n")
    # Inject only after the keyboard is open.
    while True:
        line = await until(b"\n")
        if b"WISP-KEYBOARD dev=" in line:
            break
        if b"keytest:" in line:
            raise RuntimeError(line.decode().strip())
    keys = ("a", "b", "ret", "esc")
    for key in keys:
        await qmp(reader, writer, "send-key", keys=[{"type": "qcode", "data": key}],
                  **{"hold-time": 30})
        await asyncio.sleep(0.06)
    answer = await until(prompt)
    codes = [int(n) for n in re.findall(rb"^WISP-KEY v=1 code=(\d+) value=1\r?$", answer, re.M)]
    if codes != [30, 48, 28, 1]:
        raise ValueError(f"sent {keys}, received {answer!r}")
    print(f"{arch}/{display} sent {keys}, received {codes}", flush=True)


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

        async def check_screen(path, rows=None):
            # DRM may defer copying the fbdev shadow buffer to VGA memory.
            for attempt in range(10):
                await qmp(reader, writer, "screendump", filename=str(path))
                try:
                    check_ppm(path.read_bytes(), width, height, rows)
                    break
                except ValueError:
                    if attempt == 9:
                        raise
                    await asyncio.sleep(0.1)
            print(f"{path.name}: all {width * height} pixels passed", flush=True)

        await check_screen(ppm)
        start = time.monotonic()
        proc.stdin.write(b"mandel fb\n")
        answer = await until(prompt)
        elapsed = time.monotonic() - start
        checksum, rows = mandel_image(width, height)
        expected = (f"WISP-FBMANDEL v=1 xres={width} yres={height} bpp={bpp} "
                    f"iter={MANDEL_ITER} sum={checksum}")
        if expected.encode() not in answer.splitlines():
            raise ValueError(f"expected {expected!r}, received {answer!r}")
        print(f"{arch}/{display} {expected} ({elapsed:.2f} s)", flush=True)
        await check_screen(ppm.with_name(ppm.stem + "-mandel.ppm"), rows)

        await check_keyboard(proc, arch, display, reader, writer, until, prompt)
    finally:
        writer.close()
        await writer.wait_closed()
    proc.stdin.write(b"poweroff\n")
    log.write(await proc.stdout.read())
    if await proc.wait():
        raise RuntimeError(f"{arch}/{display}: QEMU exited with {proc.returncode}")


async def boot(arch, display, dest, timeout):
    machine = run.ARCHES[arch][1][1]
    stem = dest / f"{machine}-{display}"
    with tempfile.TemporaryDirectory() as tmp, stem.with_suffix(".log").open("wb") as log:
        monitor = Path(tmp) / "qmp"
        extra = [*display_args(display, arch), "-qmp", f"unix:{monitor},server=on,wait=off"]
        if arch == "sparc64":
            # openbios-sparc64 0035: the 8042's mouse child; older firmware ignores the variable
            extra += ["-prom-env", "ps2-mouse?=true"]
        cmd = run.qemu_command(arch, kernel=str(Path(run.HERE) / "out" / arch / "kernel-fb"),
                               firmware=os.getenv("WISP_FIRMWARE"), interactive=True, extra=extra)
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
