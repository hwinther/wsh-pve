"""Play the shell's reference tone and check the samples captured by QEMU."""

import argparse
import io
import os
from pathlib import Path
import struct
import sys
import wave

import run
import shell


DEVICES = {
    "sparc32": ["-machine", "audiodev=snd0"],
    "x86_64": ["-device", "AC97,audiodev=snd0"],
    "sparc64": ["-device", "AC97,audiodev=snd0"],
}
RESULT = "WISP-SOUND v=1 dev=/dev/dsp rate=44100 fmt=s16le ch=2 hz=440 ms=1000 frames=44100 ok=1"


def wav_device(arch, path):
    return ["-audiodev", f"wav,id=snd0,path={str(path).replace(',', ',,')}", *DEVICES[arch]]


def read_pcm(path):
    """Read QEMU's little-endian stereo PCM capture."""
    capture = bytearray(path.read_bytes())
    # QEMU 11 can leave both lengths zero even after a clean guest power-off.
    # Complete its canonical PCM header in memory, preserving the original evidence.
    if (len(capture) >= 44 and capture[:8] == b"RIFF\0\0\0\0" and
            capture[8:20] == b"WAVEfmt \x10\0\0\0" and capture[36:44] == b"data\0\0\0\0"):
        if (len(capture) - 44) % 4:
            raise ValueError("partial stereo frame")
        struct.pack_into("<I", capture, 4, len(capture) - 8)
        struct.pack_into("<I", capture, 40, len(capture) - 44)
    with wave.open(io.BytesIO(capture), "rb") as wav:
        rate, channels = wav.getframerate(), wav.getnchannels()
        if wav.getsampwidth() != 2 or channels != 2 or rate <= 0:
            raise ValueError("expected signed 16-bit stereo PCM")
        frames = wav.getnframes()
        data = wav.readframes(frames)
        if len(data) != frames * 4:
            raise ValueError("truncated capture")
    return rate, data


def measure(path):
    """Measure the first tone on each channel, allowing a short DMA tail."""
    rate, data = read_pcm(path)
    results = []
    for channel in range(2):
        first = last = tail_start = tail_end = None
        first_rise = last_rise = rises = sign = active = 0
        for i, frame in enumerate(struct.iter_unpack("<hh", data)):
            value = frame[channel]
            if abs(value) < 32:
                continue
            if first is None:
                first = i
            if last is not None and (i - last - 1) * 1000 > rate * 10:
                if tail_start is None:
                    tail_start = i
                tail_end = i
                continue
            last = i
            active += 1
            current = 1 if value > 0 else -1
            if sign < 0 and current > 0:
                if rises == 0:
                    first_rise = i
                last_rise = i
                rises += 1
            sign = current
        if first is None:
            raise ValueError(f"silent channel {channel}")
        span = last - first + 1
        ms = (span * 1000 + rate // 2) // rate
        interval = last_rise - first_rise
        mhz = ((rises - 1) * rate * 1000 + interval // 2) // interval if interval else 0
        if not (900 <= ms <= 1100 and 426800 <= mhz <= 453200 and active * 10 >= span * 9):
            raise ValueError(f"channel {channel}: {ms} ms, {mhz} mHz, {active}/{span} active frames")
        if tail_start is not None:
            tail = tail_end - tail_start + 1
            if tail * 1000 > rate * 50:
                raise ValueError(f"channel {channel}: unexpected {tail}-frame tail")
            print(f"channel {channel}: {tail}-frame tail after "
                  f"{(tail_start - last - 1) * 1000 / rate:.1f} ms of silence")
        results.append((ms, mhz))
    return results


def check(arch, dest):
    machine = run.ARCHES[arch][1][1]
    wav = dest / f"{machine}.wav"
    log = wav.with_suffix(".log")
    cmd = run.qemu_command(arch, interactive=True, firmware=os.getenv("WISP_FIRMWARE"),
                           kernel=str(Path(run.HERE) / "out" / arch / "kernel-fb"),
                           extra=wav_device(arch, wav))
    wav.unlink(missing_ok=True)
    raw = shell.drive(cmd, ["soundtest 440 1000", "poweroff"], timeout=60)
    log.write_text(raw["text"])
    lines = shell.clean(raw["text"]).splitlines()
    reports = [line for line in lines if line.startswith("WISP-SOUND ")]
    for line in reports:
        print(f"{machine} {line}", flush=True)
    if raw["exit_code"] or "  powering off" not in lines:
        raise ValueError(f"guest did not power off cleanly, see {log}")
    for channel, (ms, mhz) in enumerate(measure(wav)):
        print(f"{machine} channel {channel}: {ms} ms, {mhz // 1000}.{mhz % 1000:03} Hz")
    if reports != [RESULT]:
        raise ValueError(f"unexpected soundtest response, see {log}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=DEVICES, action="append")
    parser.add_argument("--output", type=Path, default=Path(run.HERE) / "out/sound")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    failed = False
    for arch in args.arch or DEVICES:
        try:
            check(arch, args.output.resolve())
        except (OSError, ValueError, wave.Error, EOFError) as exc:
            print(f"{arch}: {exc}", file=sys.stderr)
            failed = True
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
