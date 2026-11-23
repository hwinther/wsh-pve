#!/usr/bin/env python3
"""Boot Freedoom Phase 1 DEMO1 and check its fixed length and framebuffer output."""

import argparse
import asyncio
import json
import lzma
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


def check_frame(data):
    header, dimensions, maximum, pixels = data.split(b"\n", 3)
    width, height = map(int, dimensions.split())
    if (header != b"P6" or maximum != b"255" or width < 320 or height < 200
            or len(pixels) != width * height * 3):
        raise ValueError("invalid QEMU screendump")
    # Count colours inside the game frame. Firmware text can survive in the margins.
    left = (width - 320) // 2
    top = (height - 200) // 2
    colours = set()
    for y in range(top, top + 200):
        start = (y * width + left) * 3
        colours.update(pixels[i:i+3] for i in range(start, start + 320 * 3, 3))
        if len(colours) >= 16:
            return
    raise ValueError("missing game image in the centre of the screendump")


async def check(proc, monitor, ppm, log):
    started = captured = exited = False
    result = None
    async for raw in proc.stdout:
        log.write(raw)
        log.flush()
        line = raw.strip()
        if line == b"WISP-RUN v=1 start":
            started = True
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
            check_frame(ppm.read_bytes())
            captured = True
        elif started and (match := TIMED.fullmatch(line)):
            tics, real = map(int, match.groups()[:2])
            fps = float(match[3])
            if tics != GAMETICS or real <= 0 or abs(fps - 35 * tics / real) > 0.01:
                raise ValueError(f"unexpected timing: {line!r}")
            result = tics, real, fps
        elif result and re.fullmatch(rb"WISP-RUN v=1 exit=0 signal=0 ms=\d+", line):
            exited = True
    rc = await proc.wait()
    if rc or not (captured and exited):
        raise RuntimeError(f"QEMU exit {rc}, screenshot {captured}, clean demo exit {exited}; see {log.name}")
    return result


async def boot(arch, display, archive, dest, timeout):
    machine = run.ARCHES[arch][1][1]
    stem = dest / f"{machine}-{display}"
    ppm = stem.with_suffix(".ppm")
    with tempfile.TemporaryDirectory() as tmp, stem.with_suffix(".log").open("wb") as log:
        monitor = Path(tmp) / "qmp"
        cmd = run.qemu_command(
            arch, kernel=str(Path(run.HERE) / "out" / arch / "kernel-fb"),
            memory=128 if arch == "sparc32" else 256,
            firmware=os.getenv("WISP_FIRMWARE"),
            append_extra=["quiet", "wisp=run", "--", "@/demo.rsp"],
            extra=["-accel", "tcg", "-initrd", str(archive), "-vga", display,
                   "-qmp", f"unix:{monitor},server=on,wait=off"])
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=subprocess.DEVNULL,
                                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            tics, real, fps = await asyncio.wait_for(check(proc, monitor, ppm, log), timeout)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.communicate()
        print(f"{machine}/{display}: {tics} gametics, {real} realtics, {fps:.2f} FPS, "
              f"{time.monotonic() - start:.2f} s wall, {ppm}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=framebuffer.DISPLAYS, required=True)
    parser.add_argument("--display", help="default: all framebuffer devices for this architecture")
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--wad", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(run.HERE) / "out/doom")
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    displays = framebuffer.DISPLAYS[args.arch]
    if args.display and args.display not in displays:
        parser.error(f"choose a display from {displays}")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        test = directory / "test"
        shutil.copyfile(args.binary, test)
        test.chmod(0o755)
        shutil.copyfile(args.wad, directory / "freedoom1.wad")
        # A long direct-boot command line crashes SS-5 before PID 1 starts.
        (directory / "demo.rsp").write_text("-iwad /freedoom1.wad -nosound -scaling 1 -timedemo demo1\n")
        archive = directory / "doom.cpio"
        with archive.open("wb") as out:
            subprocess.run(["cpio", "--quiet", "-o", "-H", "newc"], cwd=directory,
                           input=b"test\nfreedoom1.wad\ndemo.rsp\n", stdout=out, check=True)
        if args.arch == "sparc32":
            compressed = archive.with_suffix(".cpio.xz")
            with archive.open("rb") as src, lzma.open(compressed, "wb", check=lzma.CHECK_CRC32) as out:
                shutil.copyfileobj(src, out)
            if compressed.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("SS-5 direct-boot initrd exceeds 8 MiB")
            archive = compressed
        for display in [args.display] if args.display else displays:
            asyncio.run(boot(args.arch, display, archive, args.output.resolve(), args.timeout))


if __name__ == "__main__":
    main()
