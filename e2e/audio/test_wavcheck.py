"""wavcheck.py on generated files: levels, tones, a header without sizes (as QEMU writes it), and the
check against expected and absent tones. Standard library only.

    python3 -m unittest -v test_wavcheck.py
"""
import math
import os
import struct
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

    def test_mono(self):
        r = self.wav(tone(660, 0.5), channels=1)
        self.assertEqual(r["channels"], 1)
        self.assertAlmostEqual(r["tones"][0]["freq_hz"], 660, delta=6)


if __name__ == "__main__":
    unittest.main()
