#!/usr/bin/env python3
"""Boot Freedoom Phase 1 DEMO1 and check its fixed length and framebuffer output."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import framebuffer
import run

# 13-byte vanilla 1.9 header, 7,117 four-byte ticcmds, then DEMOMARKER.
GAMETICS = 7117
TIMED = re.compile(rb"timed (\d+) gametics in (\d+) realtics \(([\d.]+) fps\)")


def check_frame(data, scale=None):
    """Check the game frame in a screendump; scale None means the largest integer factor that fits."""
    header, dimensions, maximum, pixels = data.split(b"\n", 3)
    width, height = map(int, dimensions.split())
    if (header != b"P6" or maximum != b"255" or width < 320 or height < 200
            or len(pixels) != width * height * 3):
        raise ValueError("invalid QEMU screendump")
    # Count colours inside the game frame. Firmware text can survive in the margins.
    largest = min(width // 320, height // 200)
    if scale is None:
        scale = largest
    elif not 1 <= scale <= largest:
        raise ValueError(f"scale {scale} doesn't fit {width}x{height}")
    left = (width - 320 * scale) // 2
    top = (height - 200 * scale) // 2
    colours = set()
    for y in range(top, top + 200 * scale, scale):
        start = (y * width + left) * 3
        row = pixels[start:start + 320 * scale * 3]
        samples = [row[i:i+3] for i in range(0, len(row), scale * 3)]
        if (row != b"".join(pixel * scale for pixel in samples)
                or any(pixels[start + n * width * 3:start + n * width * 3 + len(row)] != row
                       for n in range(1, scale))):
            raise ValueError("incorrect framebuffer scaling")
        colours.update(samples)
    if len(colours) >= 16:
        return scale
    raise ValueError("missing game image in the centre of the screendump")


async def check(proc, monitor, ppm, log, boot_time, want_scale=None):
    mounted = exited = False
    started = scale = None
    result = None
    async for raw in proc.stdout:
        log.write(raw)
        log.flush()
        line = raw.strip()
        if line == b"WISP-DATA v=1 dev=/dev/sda fs=squashfs mounted=1":
            mounted = True
            print(line.decode(), flush=True)
        elif mounted and line == b"WISP-RUN v=1 start":
            started = time.monotonic() - boot_time
        elif started and line == b"fbdoom: frame 70":
            reader, writer = await asyncio.open_unix_connection(monitor)
            try:
                if "QMP" not in json.loads(await reader.readline()):
                    raise RuntimeError("missing QMP greeting")
                await framebuffer.qmp(reader, writer, "qmp_capabilities")
                await framebuffer.qmp(reader, writer, "screendump", filename=str(ppm))
            finally:
                writer.close()
                await writer.wait_closed()
            scale = check_frame(ppm.read_bytes(), want_scale)
        elif started and (match := TIMED.fullmatch(line)):
            tics, real = map(int, match.groups()[:2])
            fps = float(match[3])
            if tics != GAMETICS or real <= 0 or abs(fps - 35 * tics / real) > 0.01:
                raise ValueError(f"unexpected timing: {line!r}")
            result = tics, real, fps
        elif result and re.fullmatch(rb"WISP-RUN v=1 exit=0 signal=0 ms=\d+", line):
            exited = True
    rc = await proc.wait()
    if rc or not (scale and exited):
        raise RuntimeError(f"QEMU exit {rc}, screenshot scale {scale}, clean demo exit {exited}; see {log.name}")
    return (*result, started, scale)


async def boot(arch, display, disk, dest, timeout, scale=None):
    machine = run.ARCHES[arch][1][1]
    stem = dest / f"{machine}-{display}"
    ppm = stem.with_suffix(".ppm")
    with tempfile.TemporaryDirectory() as tmp, stem.with_suffix(".log").open("wb") as log:
        monitor = Path(tmp) / "qmp"
        controller = "scsi" if arch == "sparc32" else "ide"
        cmd = run.qemu_command(
            arch, kernel=str(Path(run.HERE) / "out" / arch / "kernel-fb"),
            memory=128 if arch == "sparc32" else 256,
            firmware=os.getenv("WISP_FIRMWARE"),
            append_extra=["quiet", "wisp=run", "wisp_data=/dev/sda", "wisp_run=/data/fbdoom",
                          "--", "@/data/demo.rsp"],
            extra=["-accel", "tcg", "-drive",
                   f"file={disk},format=raw,if={controller},index=0,snapshot=on", "-vga", display,
                   "-qmp", f"unix:{monitor},server=on,wait=off"])
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=subprocess.DEVNULL,
                                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            tics, real, fps, started, scale = await asyncio.wait_for(
                check(proc, monitor, ppm, log, start, scale), timeout)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.communicate()
        print(f"{machine}/{display}: {tics} gametics, {real} realtics, {fps:.2f} FPS, "
              f"{time.monotonic() - start:.2f} s wall, {started:.2f} s boot-to-start, {scale}x, {ppm}", flush=True)


def build_disk(directory, executable, wad, scale=None):
    root = directory / "data"
    root.mkdir()
    binary = root / "fbdoom"
    shutil.copyfile(executable, binary)
    binary.chmod(0o755)
    shutil.copyfile(wad, root / "freedoom1.wad")
    # fbDOOM's own -scaling; without it, the largest integer factor that fits the screen
    scaling = f" -scaling {scale}" if scale else ""
    (root / "demo.rsp").write_text(f"-iwad /data/freedoom1.wad -nosound{scaling} -timedemo demo1\n")
    disk = directory / "doom.squashfs"
    subprocess.run(["mksquashfs", root, disk, "-comp", "xz", "-no-xattrs", "-all-root",
                    "-noappend", "-quiet", "-no-progress"], check=True)
    return disk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=framebuffer.DISPLAYS, required=True)
    parser.add_argument("--display", help="default: all framebuffer devices for this architecture")
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--wad", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(run.HERE) / "out/doom")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--scale", type=int, default=1,
                        help="fbDOOM's frame scale: 1 (default, the fast timedemo check), 2, ...; "
                             "0 for the largest integer factor that fits, as when playing")
    args = parser.parse_args()
    displays = framebuffer.DISPLAYS[args.arch]
    if args.display and args.display not in displays:
        parser.error(f"choose a display from {displays}")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        scale = args.scale or None
        disk = build_disk(directory, args.binary, args.wad, scale)
        for display in [args.display] if args.display else displays:
            asyncio.run(boot(args.arch, display, disk, args.output.resolve(), args.timeout, scale))


if __name__ == "__main__":
    main()
