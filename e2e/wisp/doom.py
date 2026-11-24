#!/usr/bin/env python3
"""Boot Freedoom Phase 1 DEMO1 and check its fixed length and framebuffer output, or play it (--play)."""

import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

import framebuffer
import run
import sound
import tier2

# 13-byte vanilla 1.9 header, 7,117 four-byte ticcmds, then DEMOMARKER.
GAMETICS = 7117
TIMED = re.compile(rb"timed (\d+) gametics in (\d+) realtics \(([\d.]+) fps\)")
# The prebuilt kernel-fb and fbdoom per architecture, with SHA256SUMS (.github/workflows/wisp-fb.yml)
RELEASE = "https://github.com/hwinther/wsh-pve/releases/download/wisp-fb"
# The response file on the data disk, by play mode
RESPONSE = {False: "demo.rsp", True: "play.rsp"}


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


def check_effects(path, play_seconds):
    """Count sustained loud bursts separated by quiet intervals in the stereo mix."""
    rate, data = sound.read_pcm(path)
    duration = len(data) / (4 * rate)
    if not max(1, play_seconds / 2) <= duration <= play_seconds * 1.5 + 2:
        raise ValueError(f"unexpected WAV duration {duration:.2f} s for {play_seconds:.2f} s demo")
    # Effects overlap in the accelerated demo. Use stereo RMS over 10 ms
    # windows. Require a threefold rise from the quiet level to the loud level.
    window = struct.Struct(f"<{2 * max(1, rate // 100)}h")
    usable = len(data) - len(data) % window.size
    bursts = loud = quiet = 0
    in_burst = False
    for samples in window.iter_unpack(memoryview(data)[:usable]):
        power = sum(s * s for s in samples) // len(samples)
        loud = loud + 1 if power >= 6144 ** 2 else 0
        quiet = quiet + 1 if power <= 2048 ** 2 else 0
        if quiet >= 3:
            in_burst = False
        elif loud >= 2 and not in_burst:
            bursts += 1
            in_burst = True
    # Two is enough: on a fast runner the accelerated demo merges effects (2 seen on a
    # GitHub runner, 4-5 on the lab); silence, one continuous sound and clicks give 0 or 1
    if bursts < 2:
        raise ValueError(f"expected several sound effects, found {bursts} bursts")
    return bursts, duration


async def boot(arch, display, disk, dest, timeout, scale=None, with_sound=False, kernel=None):
    machine = run.ARCHES[arch][1][1]
    suffix = "-sound" if with_sound else ""
    stem = dest / f"{machine}-{display}{suffix}"
    wav = stem.with_suffix(".wav")
    audio = []
    if with_sound:
        wav.unlink(missing_ok=True)
        audio = sound.wav_device(arch, wav)
    ppm = stem.with_suffix(".ppm")
    with tempfile.TemporaryDirectory() as tmp, stem.with_suffix(".log").open("wb") as log:
        monitor = Path(tmp) / "qmp"
        # Each machine's first tier-2 disk is sda, where PID 1 mounts the payload.
        disk_profile = {"disks": tier2.PROFILES[tier2.family(arch)][0]["disks"][:1]}
        drive = tier2.qemu_args(disk_profile, [disk])
        cmd = run.qemu_command(
            arch, kernel=str(kernel or Path(run.HERE) / "out" / arch / "kernel-fb"),
            memory=128 if arch == "sparc32" else 256,
            firmware=os.getenv("WISP_FIRMWARE"),
            append_extra=["quiet", "wisp=run", "wisp_data=/dev/sda", "wisp_run=/data/fbdoom",
                          "--", "@/data/demo.rsp"],
            extra=[*audio, "-accel", "tcg", "-snapshot", *drive, *framebuffer.display_args(display, arch),
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
        wall = time.monotonic() - start
        if with_sound:
            bursts, duration = check_effects(wav, real / 35)
            print(f"{machine}/{display}: {bursts} bursts in {duration:.2f} s, {wav}", flush=True)
        print(f"{machine}/{display}: {tics} gametics, {real} realtics, {fps:.2f} FPS, "
              f"{wall:.2f} s wall, {started:.2f} s boot-to-start, {scale}x, {ppm}", flush=True)


def response(scale=None, with_sound=False, play=False, fps=False):
    """fbDOOM's arguments in the response file: the timedemo, or play from the title screen."""
    # fbDOOM's own -scaling; without it, the largest integer factor that fits the screen
    words = ["-iwad", "/data/freedoom1.wad", "-nomusic" if with_sound else "-nosound"]
    if scale:
        words += ["-scaling", str(scale)]
    if fps:
        words.append("-fps")
    if not play:
        words += ["-timedemo", "demo1"]
    return " ".join(words) + "\n"


def build_disk(directory, executable, wad, scale=None, with_sound=False, play=False, fps=False):
    root = directory / "data"
    root.mkdir()
    binary = root / "fbdoom"
    shutil.copyfile(executable, binary)
    binary.chmod(0o755)
    shutil.copyfile(wad, root / "freedoom1.wad")
    (root / RESPONSE[play]).write_text(response(scale, with_sound, play, fps))
    disk = directory / "doom.squashfs"
    subprocess.run(["mksquashfs", root, disk, "-comp", "xz", "-no-xattrs", "-all-root",
                    "-noappend", "-quiet", "-no-progress"], check=True)
    return disk


# --- play mode -----------------------------------------------------------------------------------

def load_fetch():
    """e2e/wisp/doom/fetch.py (doom/ is a directory next to this module, so not `import doom.fetch`)."""
    spec = importlib.util.spec_from_file_location("wisp_doom_fetch", Path(run.HERE) / "doom" / "fetch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_sums(text):
    """{name: sha256} from sha256sum output."""
    sums = {}
    for line in text.splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"bad SHA256SUMS line: {line!r}")
            sums[name.lstrip("*")] = digest
    return sums


def from_release(arch, directory, base=RELEASE):
    """Download kernel-fb-<arch> and fbdoom-<arch> from the wisp-fb release; check their SHA-256."""
    fetch = load_fetch()
    directory.mkdir(parents=True, exist_ok=True)
    with urlopen(f"{base}/SHA256SUMS", timeout=90) as response_:
        sums = parse_sums(response_.read().decode())
    paths = []
    for name in (f"kernel-fb-{arch}", f"fbdoom-{arch}"):
        if name not in sums:
            raise ValueError(f"{name} is not in the release's SHA256SUMS")
        fetch.fetch(directory, name, f"{base}/{name}", sums[name])
        paths.append(directory / name)
    return paths


def audio_backend(arch, qemu=None, env=os.environ):
    """A host audio backend QEMU has and the host offers (pipewire, pa, alsa), else None."""
    qemu = qemu or run.ARCHES[arch][0]
    try:
        out = subprocess.run([qemu, "-audiodev", "help"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    have = set(out.split())
    runtime = Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    if "pipewire" in have and (Path(env.get("PIPEWIRE_RUNTIME_DIR") or runtime) / "pipewire-0").exists():
        return "pipewire"
    if "pa" in have and (env.get("PULSE_SERVER") or (runtime / "pulse" / "native").exists()):
        return "pa"
    if "alsa" in have and Path("/dev/snd").is_dir():
        return "alsa"
    return None


def local_display(arch, qemu=None, env=os.environ):
    """gtk or sdl when QEMU has it and there is a desktop session, else None."""
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return None
    qemu = qemu or run.ARCHES[arch][0]
    try:
        out = subprocess.run([qemu, "-display", "help"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return next((d for d in ("gtk", "sdl") if d in out.split()), None)


def accel(arch):
    """KVM for the pc on an x86_64 host that lets us open /dev/kvm, else TCG."""
    if arch == "x86_64" and os.uname().machine == "x86_64" and os.access("/dev/kvm", os.R_OK | os.W_OK):
        return "kvm"
    return "tcg"


def play_command(arch, display, kernel, disk, out=("vnc", 0), audio=None, monitor=None, accelerator=None):
    """The QEMU command for play mode: the machine's display and keyboard, the data disk, and VNC
    on 0.0.0.0:590N or a local window."""
    disk_profile = {"disks": tier2.PROFILES[tier2.family(arch)][0]["disks"][:1]}
    extra = []
    if audio:
        extra += ["-audiodev", f"{audio},id=snd0", *sound.DEVICES[arch]]
    extra += ["-accel", accelerator or accel(arch), "-snapshot", *tier2.qemu_args(disk_profile, [disk]),
              *framebuffer.display_args(display, arch)]
    if monitor:
        extra += ["-qmp", f"unix:{monitor},server=on,wait=off"]
    cmd = run.qemu_command(arch, kernel=str(kernel), memory=128 if arch == "sparc32" else 256,
                           firmware=os.getenv("WISP_FIRMWARE"),
                           append_extra=["quiet", "wisp=run", "wisp_data=/dev/sda", "wisp_run=/data/fbdoom",
                                         "--", f"@/data/{RESPONSE[True]}"],
                           extra=extra)
    kind, value = out
    if kind == "vnc":
        cmd += ["-vnc", f"0.0.0.0:{value}"]
    else:
        # run.qemu_command's -display none is replaced by the local window
        cmd[cmd.index("-display") + 1] = value
    return cmd


class Lines:
    """Serial lines from QEMU, written to a log, waited for by pattern."""

    def __init__(self, proc, log, echo=False):
        self.proc, self.log, self.echo = proc, log, echo
        self.lines = []
        self.changed = asyncio.Event()
        self.task = asyncio.ensure_future(self.read())

    async def read(self):
        async for raw in self.proc.stdout:
            self.log.write(raw)
            self.log.flush()
            if self.echo:
                sys.stdout.buffer.write(raw)
                sys.stdout.flush()
            self.lines.append(raw.rstrip(b"\r\n"))
            self.changed.set()
        self.changed.set()

    async def wait(self, pattern, start=0, timeout=120):
        """The index and match of the first line from `start` on that matches."""
        regex = re.compile(pattern)
        deadline = time.monotonic() + timeout
        index = start
        while True:
            while index < len(self.lines):
                match = regex.search(self.lines[index])
                if match:
                    return index, match
                index += 1
            if self.task.done():
                raise RuntimeError(f"QEMU exited before {pattern!r}; see {self.log.name}")
            self.changed.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError(f"no {pattern!r} in {timeout:.0f} s; see {self.log.name}")
            try:
                await asyncio.wait_for(self.changed.wait(), remaining)
            except asyncio.TimeoutError:
                pass


def check_overlay(data, scale):
    """The FPS box in the game frame's top-left corner: dark background, bright digits, nothing else."""
    _, dimensions, _, pixels = data.split(b"\n", 3)
    width, height = map(int, dimensions.split())
    s = max(2, scale)
    left = (width - 320 * scale) // 2
    top = (height - 200 * scale) // 2
    seen = set()
    # the box spans at least one digit: (4 + 1) x 7 cells of s pixels
    for y in range(top + s, top + 8 * s):
        start = (y * width + left + s) * 3
        row = pixels[start:start + 5 * s * 3]
        seen.update(row[i:i + 3] for i in range(0, len(row), 3))
    if len(seen) != 2:
        raise ValueError(f"expected two colours in the FPS box, found {len(seen)}")
    dark, bright = sorted(seen, key=sum)
    if sum(dark) > 96 or sum(bright) < 600:
        raise ValueError(f"FPS box colours {tuple(dark)} and {tuple(bright)} don't contrast")


def status_bar_differs(before, after, scale):
    """Whether the bottom 32 game rows (DOOM's status bar in a game) changed."""
    _, dimensions, _, a = before.split(b"\n", 3)
    b = after.split(b"\n", 3)[3]
    width, height = map(int, dimensions.split())
    top = (height - 200 * scale) // 2 + 168 * scale
    left = (width - 320 * scale) // 2
    return any(a[(y * width + left) * 3:(y * width + left + 320 * scale) * 3] !=
               b[(y * width + left) * 3:(y * width + left + 320 * scale) * 3]
               for y in range(top, top + 32 * scale))


async def play_check(proc, monitor, dest, stem, log, scale, fps, step_time):
    """Wait for the title, start a game with Esc, Enter, Enter, Enter, check the frames, the FPS lines
    and the ` toggle, then quit with Backspace and expect PID 1's clean exit."""
    lines = Lines(proc, log)
    index, _ = await lines.wait(rb"^fbdoom: frame 70$", timeout=600)
    reader, writer = await asyncio.open_unix_connection(monitor)
    try:
        if "QMP" not in json.loads(await reader.readline()):
            raise RuntimeError("missing QMP greeting")
        await framebuffer.qmp(reader, writer, "qmp_capabilities")

        async def screendump(name):
            path = dest / f"{stem}-{name}.ppm"
            await framebuffer.qmp(reader, writer, "screendump", filename=str(path))
            return path.read_bytes()

        async def key(name):
            await framebuffer.qmp(reader, writer, "send-key", keys=[{"type": "qcode", "data": name}],
                                  **{"hold-time": 100})
            await asyncio.sleep(step_time)

        title = await screendump("title")
        found = check_frame(title, scale)
        print(f"{stem}: title frame {found}x", flush=True)
        if fps:
            index, match = await lines.wait(rb"^fbdoom: fps (\d+)$", index, timeout=60)
            await lines.wait(rb"^fbdoom: fps (\d+)$", index + 1, timeout=60)
            check_overlay(await screendump("overlay"), found)
            print(f"{stem}: {match[0].decode()}, overlay drawn", flush=True)
        for name in ("esc", "ret", "ret", "ret"):
            await key(name)
        await asyncio.sleep(2 * step_time)
        game = await screendump("game")
        check_frame(game, found)
        if not status_bar_differs(title, game, found):
            raise ValueError("the bottom of the frame didn't change after starting a game")
        print(f"{stem}: game started (status bar drawn)", flush=True)
        if fps:
            await key("grave_accent")
            quiet = len(lines.lines)
            await asyncio.sleep(max(3, 2 * step_time))
            if any(line.startswith(b"fbdoom: fps ") for line in lines.lines[quiet:]):
                raise ValueError("FPS lines continued after ` turned the overlay off")
            await key("grave_accent")
            _, match = await lines.wait(rb"^fbdoom: fps (\d+)$", quiet, timeout=60)
            print(f"{stem}: ` toggled the overlay off and on ({match[0].decode()})", flush=True)
        await key("backspace")
    finally:
        writer.close()
        await writer.wait_closed()
    await lines.wait(rb"^WISP-RUN v=1 exit=0 signal=0 ms=\d+$", index, timeout=120)
    await lines.task
    if await proc.wait():
        raise RuntimeError(f"QEMU exited with {proc.returncode}; see {log.name}")
    print(f"{stem}: Backspace quit, PID 1 reported exit=0", flush=True)


async def play(args, kernel, disk, display, audio, out):
    machine = run.ARCHES[args.arch][1][1]
    stem = f"{machine}-{display}-play"
    dest = args.output.resolve()
    with tempfile.TemporaryDirectory() as tmp, (dest / f"{stem}.log").open("wb") as log:
        monitor = Path(tmp) / "qmp"
        cmd = play_command(args.arch, display, kernel, disk, out, audio, monitor)
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=subprocess.DEVNULL,
                                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            if args.check:
                scale = args.scale or None
                step = 1.0 if accel(args.arch) == "kvm" else args.step_time
                await asyncio.wait_for(play_check(proc, monitor, dest, stem, log, scale, args.fps, step),
                                       args.timeout)
            else:
                lines = Lines(proc, log, echo=True)
                await lines.task
                await proc.wait()
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 10)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()


def play_main(parser, args):
    if args.from_release and (args.kernel or args.binary):
        parser.error("--from-release downloads the kernel and fbdoom: drop --kernel/--binary")
    display = args.display or framebuffer.DISPLAYS[args.arch][0]
    cache = args.cache.resolve()
    if args.from_release:
        kernel, binary = from_release(args.arch, cache, args.release_url)
        print(f"wisp-fb release: {kernel.name}, {binary.name} (SHA-256 checked) in {cache}", flush=True)
    else:
        kernel = args.kernel or Path(run.HERE) / "out" / args.arch / "kernel-fb"
        binary = args.binary
        if not binary:
            parser.error("--play needs --binary (or --from-release)")
        if not kernel.exists():
            parser.error(f"no {kernel}: build it (TIER_FB=1 build.sh {args.arch}), or --kernel/--from-release")
    wad = args.wad or load_fetch().wad(cache)
    if not shutil.which("mksquashfs"):
        parser.error("the data disk needs mksquashfs: apt install squashfs-tools")
    audio = None
    if args.sound:
        audio = audio_backend(args.arch)
        if not audio:
            print("sound: no host audio backend (pipewire, pa or alsa) found; QEMU's 'none' instead", flush=True)
            audio = "none"
    if args.local:
        local = local_display(args.arch)
        if not local:
            parser.error("--local: QEMU has no gtk/sdl display here or there is no desktop session; use --vnc")
        out = ("local", local)
    else:
        out = ("vnc", int(args.vnc.lstrip(":")))
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        disk = build_disk(Path(tmp), binary, wad, args.scale or None, args.sound, play=True, fps=args.fps)
        where = f"VNC on 0.0.0.0:{5900 + out[1]} (display :{out[1]})" if out[0] == "vnc" else f"a {out[1]} window"
        print(f"{args.arch} {display}: {where}; ` toggles the FPS overlay, Backspace quits", flush=True)
        asyncio.run(play(args, kernel, disk, display, audio, out))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=framebuffer.DISPLAYS, required=True)
    parser.add_argument("--display", help="default: all framebuffer devices for this architecture "
                                          "(--play: the first, cg3 on sparc32)")
    parser.add_argument("--binary", type=Path, help="the static fbdoom executable")
    parser.add_argument("--wad", type=Path, help="freedoom1.wad (--play: default fetched by doom/fetch.py's pin)")
    parser.add_argument("--kernel", type=Path, help="kernel-fb (default out/<arch>/kernel-fb)")
    parser.add_argument("--output", type=Path, default=Path(run.HERE) / "out/doom")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--scale", type=int,
                        help="fbDOOM's frame scale: 1 (the timedemo's default, the fast check), 2, ...; "
                             "0 for the largest integer factor that fits (--play's default)")
    parser.add_argument("--sound", action="store_true",
                        help="timedemo: enable OSS effects and check the WAV capture; --play: a host audio backend")
    parser.add_argument("--fps", action="store_true", help="pass -fps: the FPS overlay and 'fbdoom: fps N' lines")
    play_args = parser.add_argument_group("play mode")
    play_args.add_argument("--play", action="store_true",
                           help="play from the title screen instead of the timedemo")
    play_args.add_argument("--vnc", default=":0", metavar=":N", help="VNC on 0.0.0.0:590N (:0)")
    play_args.add_argument("--local", action="store_true", help="a local gtk or sdl window instead of VNC")
    play_args.add_argument("--from-release", action="store_true",
                           help="download kernel-fb and fbdoom from the wisp-fb release (SHA-256 checked)")
    play_args.add_argument("--release-url", default=RELEASE, help=argparse.SUPPRESS)
    play_args.add_argument("--cache", type=Path, default=Path(run.HERE) / "out/wisp-fb",
                           help="where downloads go (out/wisp-fb)")
    play_args.add_argument("--check", action="store_true",
                           help="drive it instead of a person: QMP screendumps, Esc and Enter to start a game, "
                                "the FPS lines and the ` toggle, Backspace to quit")
    play_args.add_argument("--step-time", type=float, default=3.0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    displays = framebuffer.DISPLAYS[args.arch]
    if args.display and args.display not in displays:
        parser.error(f"choose a display from {displays}")
    if args.play:
        if args.scale is None:
            args.scale = 0
        return play_main(parser, args)
    if args.scale is None:
        args.scale = 1
    if not (args.binary and args.wad):
        parser.error("the timedemo needs --binary and --wad")
    args.output.mkdir(parents=True, exist_ok=True)
    kernel = args.kernel or Path(run.HERE) / "out" / args.arch / "kernel-fb"
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        scale = args.scale or None
        disk = build_disk(directory, args.binary, args.wad, scale, args.sound, fps=args.fps)
        for display in [args.display] if args.display else displays:
            asyncio.run(boot(args.arch, display, disk, args.output.resolve(), args.timeout, scale, args.sound,
                             kernel))


if __name__ == "__main__":
    main()
