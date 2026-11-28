"""What a wav file from QEMU's `wav` audio backend holds: its level and the tones in it.

    python3 wavcheck.py out.wav [--expect 1000 --expect 440] [--absent 750] [--channel left]
                                [--duration 0.9 1.6]

Standard library only. The file is cut into windows of about 46 ms; a window is loud when its RMS is
above -50 dBFS, and the frequency of a loud window comes from its zero crossings (with hysteresis,
after removing the window's mean). Consecutive loud windows at the same frequency (within 3 %) make
a tone; tones shorter than 0.15 s are dropped. The test tones are pure (square waves from the
SB16, the PC speaker and the CS4231A, sines from the OPL2, the GUS and the Linux guest) and played
one after the other, so zero crossings are enough and no FFT is needed. The channels are mixed to
mono, or `channel` (`--channel left|right`) analyses one of them alone: the GUS and CS4231A tests
play a different tone on each channel at the same time. `durations` (`--duration MIN MAX`) also
wants each expected tone to last MIN to MAX seconds.

QEMU 11's wav backend leaves the RIFF and data sizes in the header at 0, whether the guest powers
off or QEMU gets `quit`, SIGTERM or SIGKILL (upstream/qemu-audio-wav-header-sizes.md): the reader
takes everything after the data chunk's header as the data, and reports the header against the file
(`header` in the result: the fmt fields, the sizes and `sizes`, see sizes_state). header_problems()
checks a header against the expected format.

    python3 wavcheck.py out.wav --signature [N]

checks the recording for N (default 1) copies of the audio signature (e2e/wisp/audiosig.h, played
by wisp's `soundtest sig` and wshspace's `-audiotest`): 8 segments of 500 ms, triangle waves of
400 + 100 k Hz on the left and 600 + 150 k Hz on the right in segment k, 4 s in all. See signatures().
"""
import argparse
import json
import math
import struct
import sys

LOUD_DBFS = -50.0
WINDOW_S = 0.046
MIN_TONE_S = 0.15
SAME_TONE = 0.03


FMT_FIELDS = ("format_tag", "channels", "rate", "byte_rate", "block_align", "bits")


def sizes_state(riff, data, file_size, data_offset):
    """What the header's sizes say about the file: "set" (both match the file), "zero" (both 0, the
    header as the backend writes it before it knows the length), "short" (they match an earlier,
    shorter file: written, then more data appended) or "wrong"."""
    if riff == file_size - 8 and data == file_size - data_offset:
        return "set"
    if riff == 0 and data == 0:
        return "zero"
    if riff == data + data_offset - 8 and data < file_size - data_offset:
        return "short"
    return "wrong"


def header_problems(header, rate=None, channels=None, bits=None, sizes=("set",)):
    """What is wrong with a header from read_wav(): its fmt chunk against itself (block align and
    byte rate) and against the expected rate/channels/bits, a data length that isn't whole frames,
    and sizes that aren't one of `sizes` (see sizes_state). An empty list when all is well."""
    p = []
    if header.get("format_tag") != 1:
        p.append(f"format tag {header.get('format_tag')}, not 1 (PCM)")
    want = {"rate": rate, "channels": channels, "bits": bits}
    for k, v in want.items():
        if v is not None and header.get(k) != v:
            p.append(f"{k} {header.get(k)}, not {v}")
    ch, b, r = header.get("channels") or 0, header.get("bits") or 0, header.get("rate") or 0
    align = ch * b // 8
    if header.get("block_align") != align:
        p.append(f"block align {header.get('block_align')}, not {align} ({ch} x {b} bit)")
    if header.get("byte_rate") != r * align:
        p.append(f"byte rate {header.get('byte_rate')}, not {r * align}")
    if align and header.get("data_bytes", 0) % align:
        p.append(f"{header.get('data_bytes')} data bytes aren't whole {align}-byte frames")
    if header.get("sizes") not in sizes:
        p.append(f"header sizes {header.get('sizes')} (RIFF {header.get('riff_size')}, data "
                 f"{header.get('data_size')} for {header.get('data_bytes')} data bytes), not {'/'.join(sizes)}")
    return p


def read_wav(path, header=None):
    """(rate, channels, mono samples as floats in -1..1). PCM 8, 16 or 32 bit. A dict passed as
    `header` gets the header's sizes and what the file holds (riff_size, data_size, data_bytes,
    data_offset, sizes_ok, sizes: see sizes_state) and the fmt chunk's fields (FMT_FIELDS)."""
    rate, ch, raw = read_interleaved(path, header)
    if ch == 1:
        return rate, ch, raw
    n = len(raw) // ch
    mono = [sum(raw[i:i + ch]) / ch for i in range(0, n * ch, ch)]
    return rate, ch, mono


def read_channels(path, header=None):
    """(rate, channels, one list of floats in -1..1 per channel); `header` as read_wav."""
    rate, ch, raw = read_interleaved(path, header)
    return rate, ch, [raw[c::ch] for c in range(ch)]


def read_interleaved(path, header=None):
    """(rate, channels, the samples of every channel interleaved, as floats in -1..1)."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"RIFF" or d[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(d):
        cid, size = d[pos:pos + 4], struct.unpack("<I", d[pos + 4:pos + 8])[0]
        body = pos + 8
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", d[body:body + 16])
        elif cid == b"data":
            # a header without sizes has 0 (or a size past the end): take the rest
            end = body + size if 0 < size <= len(d) - body else len(d)
            data = d[body:end]
            if header is not None:
                riff = struct.unpack("<I", d[4:8])[0]
                header.update({"riff_size": riff, "data_size": size, "data_bytes": len(d) - body,
                               "data_offset": body,
                               "sizes_ok": riff == len(d) - 8 and size == len(d) - body,
                               "sizes": sizes_state(riff, size, len(d), body)})
                if fmt is not None:
                    header.update(dict(zip(FMT_FIELDS, fmt)))
            break
        pos = body + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError(f"{path}: no fmt or data chunk")
    tag, ch, rate, _, _, bits = fmt
    if tag not in (1, 0xFFFE) or bits not in (8, 16, 32):
        raise ValueError(f"{path}: unsupported format tag {tag}, {bits} bit")
    sw = bits // 8
    n = len(data) // (sw * ch)
    if bits == 8:
        raw = [(b - 128) / 128.0 for b in data[:n * ch]]
    else:
        code, scale = ("h", 32768.0) if bits == 16 else ("i", 2147483648.0)
        raw = [v / scale for v in struct.unpack(f"<{n * ch}{code}", data[:n * ch * sw])]
    return rate, ch, raw


def dbfs(x):
    return 20 * math.log10(x) if x > 0 else -200.0


def window_freq(w, rate):
    """Frequency of one window from its zero crossings (mean removed, hysteresis at 10 % of the
    peak), or None when there are fewer than two full periods."""
    mean = sum(w) / len(w)
    v = [x - mean for x in w]
    peak = max(abs(x) for x in v)
    if peak == 0:
        return None
    hyst = 0.1 * peak
    state, crossings = None, []
    for i, x in enumerate(v):
        if x > hyst and state is not True:
            if state is False:
                crossings.append(i)
            state = True
        elif x < -hyst and state is not False:
            if state is True:
                crossings.append(i)
            state = False
    if len(crossings) < 5:
        return None
    return (len(crossings) - 1) / 2 / ((crossings[-1] - crossings[0]) / rate)


CHANNELS = {"left": 0, "right": 1}


def analyse(path, channel=None):
    """Levels and tones of a recording: its channels mixed, or only `channel` (an index, or "left"
    / "right")."""
    header = {}
    if channel is None:
        rate, ch, s = read_wav(path, header)
    else:
        idx = CHANNELS.get(channel, channel)
        rate, ch, chans = read_channels(path, header)
        if not isinstance(idx, int) or not 0 <= idx < ch:
            raise ValueError(f"{path}: no channel {channel} in {ch} channel(s)")
        s = chans[idx]
    wn = max(64, int(rate * WINDOW_S))
    windows = []
    for a in range(0, len(s) - wn + 1, wn):
        w = s[a:a + wn]
        rms = math.sqrt(sum(x * x for x in w) / wn)
        loud = dbfs(rms) > LOUD_DBFS
        windows.append((a / rate, rms, window_freq(w, rate) if loud else None))
    total_rms = math.sqrt(sum(x * x for x in s) / len(s)) if s else 0.0
    tones, cur = [], None
    for t, rms, f in windows:
        if f is not None and cur is not None and abs(f - cur["f"][-1]) <= SAME_TONE * cur["f"][-1]:
            cur["f"].append(f)
            cur["rms"].append(rms)
            continue
        if cur is not None:
            tones.append(cur)
        cur = {"start": t, "f": [f], "rms": [rms]} if f is not None else None
    if cur is not None:
        tones.append(cur)
    out = []
    for tn in tones:
        dur = len(tn["f"]) * wn / rate
        if dur < MIN_TONE_S:
            continue
        fs = sorted(tn["f"])
        out.append({"start_s": round(tn["start"], 3), "duration_s": round(dur, 3),
                    "freq_hz": round(fs[len(fs) // 2], 1),
                    "rms_dbfs": round(dbfs(math.sqrt(sum(r * r for r in tn["rms"]) / len(tn["rms"]))), 1)})
    loud = [w for w in windows if dbfs(w[1]) > LOUD_DBFS]
    r = {"file": path, "rate": rate, "channels": ch, "seconds": round(len(s) / rate, 3) if rate else 0,
         "rms_dbfs": round(dbfs(total_rms), 1), "loud_s": round(len(loud) * wn / rate, 3), "tones": out,
         "header": header}
    if channel is not None:
        r["channel"] = channel
    return r


def check(result, expect=(), absent=(), tol=0.04, durations=None):
    """(ok, reasons): every expected frequency is one of the tones (within tol), no absent one is;
    with durations=(min, max) the longest tone at each expected frequency lasts min to max seconds."""
    found = [t["freq_hz"] for t in result["tones"]]
    reasons = []
    for f in expect:
        if not any(abs(x - f) <= tol * f for x in found):
            reasons.append(f"no {f:g} Hz tone")
        elif durations:
            d = max(t["duration_s"] for t in result["tones"] if abs(t["freq_hz"] - f) <= tol * f)
            if not durations[0] <= d <= durations[1]:
                reasons.append(f"{f:g} Hz tone {d:g} s long, not {durations[0]:g} to {durations[1]:g} s")
    for f in absent:
        if any(abs(x - f) <= tol * f for x in found):
            reasons.append(f"unexpected {f:g} Hz tone")
    if expect and result["loud_s"] == 0:
        reasons.append("silent")
    return not reasons, reasons


# --- the audio signature (e2e/wisp/audiosig.h) ---------------------------------------------------

SIG_SEGMENTS = 8
SIG_SEGMENT_S = 0.5
SIG_SECONDS = SIG_SEGMENTS * SIG_SEGMENT_S
SIG_LEFT_HZ = tuple(400 + 100 * k for k in range(SIG_SEGMENTS))
SIG_RIGHT_HZ = tuple(600 + 150 * k for k in range(SIG_SEGMENTS))
SIG_PEAK = 16384
SIG_QUIET = 0.08      # a sample is quiet below this fraction of the recording's peak
SIG_GAP_MS = 2.0      # the longest quiet stretch on one channel inside the signal
SIG_BREAK_MS = 10.0   # both channels quiet this long: the signal has ended
SIG_TAIL_S = 0.05     # sound after the end (old ring samples) that isn't more of the signal
SIG_TAIL_WINDOW_S = 0.06  # where a tail may start after the end
SIG_SEPARATE_MS = 30.0  # sound this long after the end is another signal, sooner a dropout
SIG_TOL = 0.03        # frequencies and the duration (a card's rate may be off by about 1 %)


def signature_frames(rate):
    """The signature as audiosig.h makes it: a list of (left, right) integers, -16384..16384."""
    def step(hz):
        hi, rem = divmod(hz << 16, rate)
        return ((hi << 16) | ((rem << 16) // rate)) & 0xFFFFFFFF

    def triangle(phase):
        x = phase >> 16
        return x if x < 16384 else 32768 - x if x < 49152 else x - 65536

    out, pl, pr = [], 0, 0
    for k in range(SIG_SEGMENTS):
        sl, sr = step(SIG_LEFT_HZ[k]), step(SIG_RIGHT_HZ[k])
        for _ in range(rate // 2):
            out.append((triangle(pl), triangle(pr)))
            pl, pr = (pl + sl) & 0xFFFFFFFF, (pr + sr) & 0xFFFFFFFF
    return out


def _quiet_runs(quiet, a, b):
    """The longest run of True in quiet[a:b] and where it starts."""
    best = best_at = run = 0
    for i in range(a, b):
        if quiet[i]:
            run += 1
            if run > best:
                best, best_at = run, i - run + 1
        else:
            run = 0
    return best, best_at


def _near(f, want, tol):
    return f is not None and abs(f - want) <= tol * want


def _loud_until_break(ql, qr, a, b, brk):
    """From a to at most b: (index after the last loud sample, whether SIG_BREAK_MS of quiet on both
    channels (brk samples) or the end of the recording ended it)."""
    last, run = a, 0
    for i in range(a, b):
        if ql[i] and qr[i]:
            run += 1
            if run >= brk:
                return last, True
        else:
            last, run = i + 1, 0
    return last, b == len(ql)


def _one_signature(rate, left, right, ql, qr, onset, tol, gap_ms):
    """The signature that starts at `onset`: (result, index after it and its tail, index of its end)."""
    n = len(left)
    brk = max(1, int(rate * SIG_BREAK_MS / 1000))
    # the end: SIG_BREAK_MS of quiet, or the last sound before the end of the recording
    end, _ = _loud_until_break(ql, qr, onset, n, brk)
    res = {"start_s": round(onset / rate, 3), "duration_s": round((end - onset) / rate, 3)}
    reasons = []
    # sound that starts within SIG_TAIL_WINDOW_S after the end: old samples from a ring when it is
    # short and silence follows (a tail), more of the signal after a dropout when it starts within
    # SIG_SEPARATE_MS; later or longer sound is the next signal, left to the caller
    nxt = end
    first = next((i for i in range(end, min(n, end + int(rate * SIG_TAIL_WINDOW_S))) if not (ql[i] and qr[i])), None)
    if first is not None:
        last, ended = _loud_until_break(ql, qr, first, min(n, first + int(rate * SIG_TAIL_S) + brk + 1), brk)
        silent_ms = 1000 * (first - end) / rate
        if ended and last - first <= rate * SIG_TAIL_S:
            res["tail"] = {"after_s": round((first - end) / rate, 4), "duration_s": round((last - first) / rate, 4)}
            nxt = last
        elif silent_ms < SIG_SEPARATE_MS:
            reasons.append(f"a gap of {silent_ms:.1f} ms at {end / rate:.3f} s, then more sound")
    if abs(res["duration_s"] - SIG_SECONDS) > tol * SIG_SECONDS:
        reasons.append(f"{res['duration_s']:.3f} s long, not {SIG_SECONDS:g} s")
    gaps = []
    for q in (ql, qr):
        g, at = _quiet_runs(q, onset, end)
        gaps.append({"ms": round(1000 * g / rate, 2), "at_s": round(at / rate, 3)})
    res["max_gap_ms"] = [g["ms"] for g in gaps]
    for name, g in zip(("left", "right"), gaps):
        if g["ms"] > gap_ms:
            reasons.append(f"{name}: a gap of {g['ms']} ms at {g['at_s']} s")
    seg = (end - onset) / SIG_SEGMENTS
    segments, swapped = [], 0
    for k in range(SIG_SEGMENTS):
        a = int(onset + (k + 0.1) * seg)
        b = int(onset + (k + 0.9) * seg)
        fl = window_freq(left[a:b], rate) if b - a > 16 else None
        fr = window_freq(right[a:b], rate) if b - a > 16 else None
        segments.append({"left_hz": round(fl, 1) if fl else None, "right_hz": round(fr, 1) if fr else None})
        if not _near(fl, SIG_LEFT_HZ[k], tol) or not _near(fr, SIG_RIGHT_HZ[k], tol):
            reasons.append(f"segment {k}: {fl and round(fl, 1)} Hz left, {fr and round(fr, 1)} Hz right, "
                           f"not {SIG_LEFT_HZ[k]} and {SIG_RIGHT_HZ[k]}")
        swapped += _near(fl, SIG_RIGHT_HZ[k], tol) and _near(fr, SIG_LEFT_HZ[k], tol)
    res["segments"] = segments
    res["swapped"] = swapped >= SIG_SEGMENTS // 2
    if res["swapped"]:
        reasons.append(f"left and right swapped ({swapped} of {SIG_SEGMENTS} segments)")
    span = max(1, end - onset)
    res["rms_dbfs"] = [round(dbfs(math.sqrt(sum(x * x for x in ch[onset:end]) / span)), 1) for ch in (left, right)]
    res["reasons"] = reasons
    return res, nxt, end


def signatures(path, count=1, tol=SIG_TOL, gap_ms=SIG_GAP_MS):
    """Find `count` audio signatures (signature_frames) one after the other in a recording and check
    each: its duration (4 s, within tol), every segment's frequency on each channel (within tol, in
    the middle 80 % of the segment, the segments being an eighth of the measured duration each), no
    quiet stretch longer than gap_ms on either channel inside it, channels not swapped and not the
    same (mono). A signature starts at the first sound that lasts (no SIG_BREAK_MS of silence on both
    channels in its first 100 ms) and ends at SIG_BREAK_MS of silence on both channels (or its last
    sound before the end of the file). Sound that starts within SIG_TAIL_WINDOW_S after the end is a
    tail when it lasts at most SIG_TAIL_S and silence follows (old samples a DMA ring plays out after
    the stop, as the SS-5's CS4231 did), a dropout when it starts sooner than SIG_SEPARATE_MS after
    the end, else the next signal. Quiet is below SIG_QUIET of the recording's peak. A dict with
    `ok`, `reasons` and `signatures`."""
    header = {}
    rate, ch, chans = read_channels(path, header)
    out = {"file": path, "rate": rate, "channels": ch, "seconds": round(len(chans[0]) / rate, 3) if rate else 0,
           "header": header, "signatures": [], "reasons": []}
    if ch != 2:
        out["reasons"].append(f"{ch} channel(s), not 2")
        out["ok"] = False
        return out
    left, right = chans
    n = len(left)
    peak = max(max((abs(x) for x in left), default=0), max((abs(x) for x in right), default=0))
    out["peak_dbfs"] = round(dbfs(peak), 1)
    thresh = max(1.5 / 32768, SIG_QUIET * peak)
    ql = [abs(x) < thresh for x in left]
    qr = [abs(x) < thresh for x in right]
    brk = max(1, int(rate * SIG_BREAK_MS / 1000))
    settle = int(rate * 0.1)
    pos = 0
    while pos < n and len(out["signatures"]) < count + 1:
        onset = next((i for i in range(pos, n) if not (ql[i] and qr[i])), None)
        if onset is None:
            break
        b, _ = (0, 0) if onset + settle > n else _quiet_both(ql, qr, onset, onset + settle)
        if onset + settle > n or b >= brk:
            pos = onset + max(1, b)  # a click, not a signal
            continue
        res, pos, end = _one_signature(rate, left, right, ql, qr, onset, tol, gap_ms)
        same = sum(1 for i in range(onset, end)
                   if abs(left[i] - right[i]) < thresh)
        res["mono"] = same > 0.9 * (end - onset)
        if res["mono"]:
            res["reasons"].append("both channels the same (mono)")
        out["signatures"].append(res)
    found = len(out["signatures"])
    if found != count:
        out["reasons"].append(f"{found} signature(s) in the recording, not {count}")
    for i, s in enumerate(out["signatures"][:count]):
        out["reasons"] += [f"signature {i + 1}: {r}" for r in s["reasons"]]
    out["ok"] = not out["reasons"]
    return out


def _quiet_both(ql, qr, a, b):
    """The longest stretch in [a, b) where both channels are quiet, and where it starts."""
    return _quiet_runs([x and y for x, y in zip(ql[a:b], qr[a:b])], 0, b - a)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("wav")
    p.add_argument("--expect", type=float, action="append", default=[], help="a tone that must be there (Hz)")
    p.add_argument("--absent", type=float, action="append", default=[], help="a tone that must not be (Hz)")
    p.add_argument("--channel", choices=sorted(CHANNELS), help="analyse this channel alone, not the mix")
    p.add_argument("--duration", type=float, nargs=2, metavar=("MIN", "MAX"),
                   help="each expected tone must last MIN to MAX seconds")
    p.add_argument("--signature", type=int, nargs="?", const=1, metavar="N",
                   help="check for N copies of the audio signature (default 1) instead of tones")
    a = p.parse_args(argv)
    if a.signature is not None:
        r = signatures(a.wav, a.signature)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1
    r = analyse(a.wav, a.channel)
    ok, reasons = check(r, a.expect, a.absent, durations=a.duration)
    r["ok"], r["reasons"] = ok, reasons
    print(json.dumps(r, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
