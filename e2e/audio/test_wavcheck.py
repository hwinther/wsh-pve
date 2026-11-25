"""wavcheck.py on generated files: levels, tones, a header without sizes (as QEMU writes it), the
check against expected and absent tones, and the audio signature (e2e/wisp/audiosig.h: at each rate,
resampled, swapped, mono, cut short, with gaps and a tail; with a C compiler, that the header makes
what signature_frames() models). Standard library only.

    python3 -m unittest -v test_wavcheck.py
"""
import math
import os
import shutil
import struct
import subprocess
import tempfile
import unittest

import wavcheck

RATE = 44100


def tone(freq, secs, amp=0.4, square=False, dc=0.0):
    out = []
    for i in range(int(RATE * secs)):
        x = math.sin(2 * math.pi * freq * i / RATE)
        if square:
            x = 1.0 if x >= 0 else -1.0
        out.append(dc + amp * x)
    return out


def silence(secs):
    return [0.0] * int(RATE * secs)


def write_wav(path, mono, sizes=True, channels=2):
    pcm = bytearray()
    for x in mono:
        v = max(-32768, min(32767, int(x * 32767)))
        pcm += struct.pack("<h", v) * channels
    fmt = struct.pack("<HHIIHH", 1, channels, RATE, RATE * 2 * channels, 2 * channels, 16)
    riff = 4 + 8 + len(fmt) + 8 + len(pcm) if sizes else 0
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", riff) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(pcm) if sizes else 0) + pcm)


class WavCheck(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="wavcheck-")

    def tearDown(self):
        for n in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, n))
        os.rmdir(self.dir)

    def wav(self, mono, **kw):
        p = os.path.join(self.dir, f"{len(os.listdir(self.dir))}.wav")
        write_wav(p, mono, **kw)
        return wavcheck.analyse(p)

    def test_silence(self):
        r = self.wav(silence(2))
        self.assertEqual(r["tones"], [])
        self.assertEqual(r["loud_s"], 0)
        ok, reasons = wavcheck.check(r, expect=[440])
        self.assertFalse(ok)
        self.assertIn("silent", reasons)

    def test_sine(self):
        r = self.wav(silence(0.3) + tone(440, 1.0) + silence(0.3))
        self.assertEqual(len(r["tones"]), 1)
        self.assertAlmostEqual(r["tones"][0]["freq_hz"], 440, delta=4)
        self.assertAlmostEqual(r["tones"][0]["duration_s"], 1.0, delta=0.1)
        self.assertTrue(wavcheck.check(r, expect=[440], absent=[750, 1000])[0])

    def test_square_with_offset(self):
        # an unsigned 8-bit source converted without centring leaves a DC offset
        r = self.wav(tone(1000, 1.0, amp=0.25, square=True, dc=0.2))
        self.assertAlmostEqual(r["tones"][0]["freq_hz"], 1000, delta=10)

    def test_sequence(self):
        r = self.wav(silence(0.2) + tone(1000, 1.0, square=True) + silence(0.3) + tone(440, 1.0)
                     + silence(0.3) + tone(750, 1.0, square=True) + silence(0.2))
        self.assertEqual([round(t["freq_hz"] / 10) * 10 for t in r["tones"]], [1000, 440, 750])
        self.assertTrue(wavcheck.check(r, expect=[1000, 440, 750])[0])
        ok, reasons = wavcheck.check(r, expect=[1000], absent=[440])
        self.assertFalse(ok)
        self.assertEqual(reasons, ["unexpected 440 Hz tone"])

    def test_quiet_is_silent(self):
        r = self.wav(tone(440, 1.0, amp=0.001))  # -60 dBFS: below the threshold
        self.assertEqual(r["tones"], [])

    def test_header_without_sizes(self):
        r = self.wav(tone(660, 1.0), sizes=False)
        self.assertAlmostEqual(r["seconds"], 1.0, delta=0.01)
        self.assertAlmostEqual(r["tones"][0]["freq_hz"], 660, delta=6)
        self.assertEqual((r["header"]["riff_size"], r["header"]["data_size"]), (0, 0))
        self.assertEqual(r["header"]["data_bytes"], int(RATE * 1.0) * 4)
        self.assertFalse(r["header"]["sizes_ok"])

    def test_header_with_sizes(self):
        r = self.wav(tone(660, 1.0))
        self.assertTrue(r["header"]["sizes_ok"])
        self.assertEqual(r["header"]["data_size"], r["header"]["data_bytes"])

    def test_header_fields(self):
        h = self.wav(tone(660, 0.5))["header"]
        self.assertEqual((h["format_tag"], h["channels"], h["rate"], h["bits"]), (1, 2, RATE, 16))
        self.assertEqual((h["block_align"], h["byte_rate"], h["data_offset"]), (4, RATE * 4, 44))
        self.assertEqual(h["sizes"], "set")
        self.assertEqual(wavcheck.header_problems(h, rate=RATE, channels=2, bits=16), [])
        self.assertEqual(wavcheck.header_problems(h, rate=48000, channels=1),
                         ["rate 44100, not 48000", "channels 2, not 1"])

    def test_header_sizes_zero(self):
        h = self.wav(tone(660, 0.5), sizes=False)["header"]
        self.assertEqual(h["sizes"], "zero")
        self.assertEqual(len(wavcheck.header_problems(h)), 1)
        self.assertIn("header sizes zero", wavcheck.header_problems(h)[0])
        self.assertEqual(wavcheck.header_problems(h, sizes=("set", "zero")), [])

    def test_header_sizes_short_and_wrong(self):
        p = os.path.join(self.dir, "s.wav")
        write_wav(p, tone(660, 0.5))
        with open(p, "ab") as f:  # sizes written, then more frames after them
            f.write(b"\0" * 400)
        h = {}
        wavcheck.read_wav(p, h)
        self.assertEqual(h["sizes"], "short")
        self.assertEqual(wavcheck.sizes_state(10, 20, 1000, 44), "wrong")
        self.assertEqual(wavcheck.sizes_state(992, 956, 1000, 44), "set")

    def test_header_partial_frame(self):
        # killed in the middle of a write: the file ends inside a frame
        p = os.path.join(self.dir, "p.wav")
        write_wav(p, tone(660, 0.5), sizes=False)
        with open(p, "ab") as f:
            f.write(b"\1\2")
        h = {}
        wavcheck.read_wav(p, h)
        self.assertEqual(wavcheck.header_problems(h, sizes=("zero",)),
                         [f"{h['data_bytes']} data bytes aren't whole 4-byte frames"])

    def test_header_inconsistent_fmt(self):
        h = {"format_tag": 1, "channels": 2, "rate": RATE, "bits": 16, "block_align": 2,
             "byte_rate": RATE * 2, "data_bytes": 8, "sizes": "set"}
        self.assertEqual(wavcheck.header_problems(h),
                         ["block align 2, not 4 (2 x 16 bit)", f"byte rate {RATE * 2}, not {RATE * 4}"])

    def test_mono(self):
        r = self.wav(tone(660, 0.5), channels=1)
        self.assertEqual(r["channels"], 1)
        self.assertAlmostEqual(r["tones"][0]["freq_hz"], 660, delta=6)


# --- the audio signature ---------------------------------------------------------------------------

AUDIOSIG_H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "wisp", "audiosig.h")
HEADER_TEST_C = r"""#include <stdio.h>
#include <stdlib.h>
#include "audiosig.h"
int main(int argc, char **argv)
{
	struct audiosig s;
	int l, r;

	(void)argc;
	audiosig_init(&s, (unsigned int)atoi(argv[1]));
	while (audiosig_next(&s, &l, &r))
		printf("%d %d\n", l, r);
	return 0;
}
"""


def write_stereo(path, frames, rate, bits=16, sizes=True):
    """(left, right) integers in -32768..32767 as a 16-bit (or 8-bit unsigned) stereo PCM file."""
    if bits == 8:
        pcm = bytes(min(255, max(0, (v >> 8) + 128)) for f in frames for v in f)
    else:
        pcm = struct.pack(f"<{2 * len(frames)}h", *(v for f in frames for v in f))
    align = 2 * bits // 8
    fmt = struct.pack("<HHIIHH", 1, 2, rate, rate * align, align, bits)
    riff = 4 + 8 + len(fmt) + 8 + len(pcm) if sizes else 0
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", riff) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(pcm) if sizes else 0) + pcm)


def resample(frames, src, dst):
    """Linear interpolation from src to dst Hz, as QEMU's mixer does it."""
    out, n = [], len(frames)
    for j in range(int(n * dst / src)):
        x = j * src / dst
        i = int(x)
        a, b = frames[i], frames[min(i + 1, n - 1)]
        t = x - i
        out.append((int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t)))
    return out


def quiet(rate, secs):
    return [(0, 0)] * int(rate * secs)


class Signature(unittest.TestCase):
    cache = {}

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="wavcheck-sig-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def sig(self, rate):
        if rate not in self.cache:
            self.cache[rate] = wavcheck.signature_frames(rate)
        return self.cache[rate]

    def check(self, frames, rate, count=1, **kw):
        p = os.path.join(self.dir, f"{len(os.listdir(self.dir))}.wav")
        write_stereo(p, frames, rate, **kw)
        return wavcheck.signatures(p, count)

    def assertSignature(self, r, rate_tol=0.01):
        self.assertEqual(r["reasons"], [])
        self.assertTrue(r["ok"])
        s = r["signatures"][0]
        self.assertAlmostEqual(s["duration_s"], 4.0, delta=4.0 * rate_tol)
        for k, seg in enumerate(s["segments"]):
            self.assertAlmostEqual(seg["left_hz"], wavcheck.SIG_LEFT_HZ[k], delta=wavcheck.SIG_LEFT_HZ[k] * rate_tol)
            self.assertAlmostEqual(seg["right_hz"], wavcheck.SIG_RIGHT_HZ[k], delta=wavcheck.SIG_RIGHT_HZ[k] * rate_tol)
        self.assertFalse(s["swapped"])
        self.assertFalse(s["mono"])
        self.assertLessEqual(max(s["max_gap_ms"]), 0.5)

    def test_frames(self):
        f = self.sig(8000)
        self.assertEqual(len(f), 32000)
        self.assertEqual(f[0], (0, 0))
        self.assertTrue(16300 < max(v for x in f for v in x) <= 16384)
        self.assertTrue(-16384 <= min(v for x in f for v in x) < -16300)
        self.assertEqual(len(self.sig(22050)), 8 * 11025)

    def test_at_each_rate(self):
        for rate in (8000, 22050, 44100):
            with self.subTest(rate=rate):
                self.assertSignature(self.check(quiet(rate, 0.3) + self.sig(rate) + quiet(rate, 0.3), rate))

    def test_resampled_to_44100(self):
        # what QEMU's wav backend records from a guest playing at 8000 or 22050 Hz
        for rate in (8000, 22050):
            with self.subTest(rate=rate):
                frames = resample(quiet(rate, 0.2) + self.sig(rate) + quiet(rate, 0.2), rate, 44100)
                self.assertSignature(self.check(frames, 44100))

    def test_rate_off_by_one_percent(self):
        # a Sound Blaster's time constant: 22222 Hz played for a signal made for 22050
        frames = resample(self.sig(22050), 22222, 44100)
        r = self.check(quiet(44100, 0.2) + frames + quiet(44100, 0.2), 44100)
        self.assertSignature(r, rate_tol=0.02)

    def test_eight_bit_and_no_sizes(self):
        r = self.check(quiet(22050, 0.2) + self.sig(22050) + quiet(22050, 0.2), 22050, bits=8, sizes=False)
        self.assertSignature(r)
        self.assertEqual(r["header"]["sizes"], "zero")

    def test_swapped(self):
        r = self.check([(b, a) for a, b in self.sig(8000)] + quiet(8000, 0.2), 8000)
        self.assertFalse(r["ok"])
        self.assertTrue(r["signatures"][0]["swapped"])
        self.assertIn("swapped", " ".join(r["reasons"]))

    def test_mono(self):
        r = self.check([((a + b) // 2,) * 2 for a, b in self.sig(22050)] + quiet(22050, 0.2), 22050)
        self.assertFalse(r["ok"])
        self.assertTrue(r["signatures"][0]["mono"])

    def test_not_stereo(self):
        p = os.path.join(self.dir, "m.wav")
        write_wav(p, silence(0.5), channels=1)
        self.assertEqual(wavcheck.signatures(p)["reasons"], ["1 channel(s), not 2"])

    def test_stops_after_the_first_buffer(self):
        r = self.check(quiet(44100, 0.2) + self.sig(44100)[:4096] + quiet(44100, 1), 44100)
        self.assertFalse(r["ok"])
        self.assertIn("0.093 s long, not 4 s", " ".join(r["reasons"]))

    def test_dropout(self):
        # 20 ms of silence in the middle: the signal ends there, the rest follows after a gap
        f = list(self.sig(44100))
        f[88200:88200 + 882] = quiet(44100, 0.02)
        r = self.check(quiet(44100, 0.2) + f + quiet(44100, 0.5), 44100)
        self.assertFalse(r["ok"])
        self.assertIn("a gap of 20.0 ms at 2.200 s", " ".join(r["reasons"]))

    def test_short_gap_on_one_channel(self):
        f = list(self.sig(44100))
        for i in range(100000, 100000 + 220):  # 5 ms
            f[i] = (0, f[i][1])
        r = self.check(quiet(44100, 0.2) + f + quiet(44100, 0.2), 44100)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["reasons"]), 1)
        self.assertRegex(r["reasons"][0], r"^signature 1: left: a gap of 4\.\d+ ms at 2\.46\d s$")

    def test_tail_of_old_samples(self):
        # the SS-5 before wsh/0128: 22 ms of padding, then ~110 frames of an old buffer
        tail = self.sig(44100)[1000:1110]
        r = self.check(quiet(44100, 0.2) + self.sig(44100) + quiet(44100, 0.022) + tail + quiet(44100, 0.5), 44100)
        self.assertSignature(r)
        self.assertAlmostEqual(r["signatures"][0]["tail"]["after_s"], 0.022, delta=0.001)
        self.assertLess(r["signatures"][0]["tail"]["duration_s"], 0.003)

    def test_a_click_before(self):
        r = self.check(quiet(22050, 0.2) + [(9000, 9000)] * 3 + quiet(22050, 0.3) + self.sig(22050)
                       + quiet(22050, 0.2), 22050)
        self.assertSignature(r)
        self.assertAlmostEqual(r["signatures"][0]["start_s"], 0.5, delta=0.001)

    def test_three_in_a_row(self):
        # wisp's `soundtest sig`: 8000, 22050 and 44100 Hz with 500 ms of silence after each
        frames = []
        for rate in (8000, 22050, 44100):
            frames += resample(self.sig(rate) + quiet(rate, 0.5), rate, 44100)
        r = self.check(quiet(44100, 0.3) + frames, 44100, count=3)
        self.assertEqual(r["reasons"], [])
        self.assertEqual(len(r["signatures"]), 3)
        r = self.check(quiet(44100, 0.3) + frames, 44100, count=2)
        self.assertEqual(r["reasons"], ["3 signature(s) in the recording, not 2"])

    def test_at_end_of_file(self):
        # QEMU killed while the signal still plays out: no silence after it
        self.assertSignature(self.check(quiet(44100, 0.2) + self.sig(44100), 44100))

    def test_close_together(self):
        # 45 ms between them, as AC97 under Linux leaves after an OSS close: not a tail of the first
        frames = quiet(44100, 0.2) + self.sig(44100) + quiet(44100, 0.045) + self.sig(44100) + quiet(44100, 0.2)
        r = self.check(frames, 44100, count=2)
        self.assertEqual(r["reasons"], [])
        self.assertEqual([s["duration_s"] for s in r["signatures"]], [4.0, 4.0])
        self.assertNotIn("tail", r["signatures"][0])

    def test_quiet_before_end_of_file(self):
        # QEMU powered off 9 ms after the signal: that silence isn't a gap in it
        self.assertSignature(self.check(quiet(44100, 0.2) + self.sig(44100) + quiet(44100, 0.009), 44100))

    def test_silent(self):
        r = self.check(quiet(8000, 2), 8000)
        self.assertEqual(r["reasons"], ["0 signature(s) in the recording, not 1"])

    @unittest.skipUnless(shutil.which("cc") or shutil.which("gcc"), "no C compiler")
    def test_header_matches(self):
        """audiosig.h makes exactly what signature_frames() models."""
        src = os.path.join(self.dir, "sig.c")
        exe = os.path.join(self.dir, "sig")
        with open(src, "w") as f:
            f.write(HEADER_TEST_C)
        cc = shutil.which("cc") or shutil.which("gcc")
        subprocess.run([cc, "-Wall", "-Wextra", "-Werror", "-I", os.path.dirname(AUDIOSIG_H), "-o", exe, src],
                       check=True)
        for rate in (8000, 22050, 44100, 48000):
            with self.subTest(rate=rate):
                out = subprocess.run([exe, str(rate)], check=True, capture_output=True, text=True).stdout
                got = [tuple(map(int, line.split())) for line in out.splitlines()]
                self.assertEqual(got, wavcheck.signature_frames(rate))


if __name__ == "__main__":
    unittest.main()
