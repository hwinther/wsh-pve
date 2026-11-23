from contextlib import redirect_stdout
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sound import measure


class CapturedTone(unittest.TestCase):
    def capture(self, hz=440, ms=1000, right=4096, gap=False, tail=0):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "capture.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setparams((2, 2, 8000, 0, "NONE", ""))
            data = bytearray(1600)
            for i in range(ms * 8):
                sign = 1 if (i * hz) % 8000 < 4000 else -1
                if gap and 2000 <= i < 4000:
                    sign = 0
                data.extend(struct.pack("<hh", sign * 4096, sign * right))
            wav.writeframes(data + bytes(288 * 4) + struct.pack("<hh", 800, -800) * tail + bytes(3200))
        return path

    def test_padded_stereo(self):
        for ms, mhz in measure(self.capture()):
            self.assertEqual(ms, 1000)
            self.assertLessEqual(abs(mhz - 440000), 500)

    def test_stale_samples_after_gap(self):
        expected = measure(self.capture())
        report = io.StringIO()
        with redirect_stdout(report):
            self.assertEqual(measure(self.capture(tail=27)), expected)
        self.assertIn("27-frame tail after 36.0 ms", report.getvalue())

    def test_reject_bad_sound(self):
        for params in (dict(right=0), dict(hz=220), dict(ms=700), dict(ms=1300), dict(gap=True),
                       dict(ms=0), dict(tail=800)):
            with self.subTest(params=params), self.assertRaises(ValueError):
                measure(self.capture(**params))

    def test_qemu_zero_lengths(self):
        path = self.capture()
        expected = measure(path)
        data = bytearray(path.read_bytes())
        data[4:8] = data[40:44] = bytes(4)
        path.write_bytes(data)
        self.assertEqual(measure(path), expected)
        self.assertEqual(path.read_bytes(), data)
