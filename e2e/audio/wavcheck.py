"""What a wav file from QEMU's `wav` audio backend holds: its level and the tones in it.

    python3 wavcheck.py out.wav [--expect 1000 --expect 440] [--absent 750]

Standard library only. The file is cut into windows of about 46 ms; a window is loud when its RMS is
above -50 dBFS, and the frequency of a loud window comes from its zero crossings (with hysteresis,
after removing the window's mean). Consecutive loud windows at the same frequency (within 3 %) make
a tone; tones shorter than 0.15 s are dropped. The test tones are pure (square waves from the
SB16 and the PC speaker, sines from the OPL2 and the Linux guest) and played one after the other, so
zero crossings are enough and no FFT is needed.

QEMU 11.1's wav backend leaves the RIFF and data sizes in the header at 0, whether the guest powers
off or QEMU gets `quit` or SIGTERM: the reader takes everything after the data chunk's header as the
data, and reports the header's sizes against the file (`header` in the result).
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


def read_wav(path, header=None):
    """(rate, channels, mono samples as floats in -1..1). PCM 8, 16 or 32 bit. A dict passed as
    `header` gets the header's sizes and what the file holds (riff_size, data_size, data_bytes,
    sizes_ok)."""
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
                               "sizes_ok": riff == len(d) - 8 and size == len(d) - body})
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
    if ch == 1:
        return rate, ch, raw
    mono = [sum(raw[i:i + ch]) / ch for i in range(0, n * ch, ch)]
    return rate, ch, mono


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


def analyse(path):
    header = {}
    rate, ch, s = read_wav(path, header)
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
    return {"file": path, "rate": rate, "channels": ch, "seconds": round(len(s) / rate, 3) if rate else 0,
            "rms_dbfs": round(dbfs(total_rms), 1), "loud_s": round(len(loud) * wn / rate, 3), "tones": out,
            "header": header}


def check(result, expect=(), absent=(), tol=0.04):
    """(ok, reasons): every expected frequency is one of the tones (within tol), no absent one is."""
    found = [t["freq_hz"] for t in result["tones"]]
    reasons = []
    for f in expect:
        if not any(abs(x - f) <= tol * f for x in found):
            reasons.append(f"no {f:g} Hz tone")
    for f in absent:
        if any(abs(x - f) <= tol * f for x in found):
            reasons.append(f"unexpected {f:g} Hz tone")
    if expect and result["loud_s"] == 0:
        reasons.append("silent")
    return not reasons, reasons


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("wav")
    p.add_argument("--expect", type=float, action="append", default=[], help="a tone that must be there (Hz)")
    p.add_argument("--absent", type=float, action="append", default=[], help="a tone that must not be (Hz)")
    a = p.parse_args(argv)
    r = analyse(a.wav)
    ok, reasons = check(r, a.expect, a.absent)
    r["ok"], r["reasons"] = ok, reasons
    print(json.dumps(r, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
