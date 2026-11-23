from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framebuffer import check_ppm, mandel_image


class Screendump(unittest.TestCase):
    def setUp(self):
        white = b"\xff" * 3
        bars = bytes.fromhex("000000 0000ff 00ff00 00ffff ff0000 ff00ff ffff00 ffffff")
        row = b"".join(bars[i:i+3] * 2 for i in range(0, len(bars), 3))
        self.ppm = b"P6\n16 3\n255\n" + white * 16 + white + row[3:] + white * 16

    def test_visible_raster(self):
        check_ppm(self.ppm, 16, 3)

    def test_wrong_dimensions_truncation_border_and_bar(self):
        for image in (self.ppm.replace(b"16 3", b"8 6"), self.ppm[:-1],
                      self.ppm[:-1] + b"\x00", self.ppm.replace(b"\x00\x00\xff", b"\xff\x00\x00", 1)):
            with self.subTest(), self.assertRaises(ValueError):
                check_ppm(image, 16, 3)


class Mandelbrot(unittest.TestCase):
    def test_sampled_counts_and_palette(self):
        checksum, rows = mandel_image(4, 2)
        self.assertEqual(checksum, 107)
        self.assertEqual(rows, [bytes.fromhex("0000ff 00ff00 00ffff ff0000"),
                                bytes.fromhex("0000ff 000000 000000 000000")])

    def test_wrong_mandel_pixel(self):
        _, rows = mandel_image(19, 7)
        ppm = b"P6\n19 7\n255\n" + b"".join(rows)
        check_ppm(ppm, 19, 7, rows)
        with self.assertRaisesRegex(ValueError, r"pixel \(18,6\)"):
            check_ppm(ppm[:-1] + bytes([ppm[-1] ^ 1]), 19, 7, rows)
