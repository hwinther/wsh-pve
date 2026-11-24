from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framebuffer import check_ppm, mandel_image, mouse_events


class Mouse(unittest.TestCase):
    def setUp(self):
        # SS-5 splits X and reports a compensating negative Y delta.
        self.events = [(2, 0, 5), (2, 0, 5), (2, 1, 5), (2, 1, 2), (2, 1, -2),
                       (1, 272, 1), (1, 272, 0), (1, 273, 1)]
        self.answer = b"".join(b"WISP-MOUSE-EV type=%d code=%d value=%d\r\n" % event
                               for event in self.events)

    def test_split_motion(self):
        self.assertEqual(mouse_events(self.answer), self.events)

    def test_wrong_direction_missing_axis_or_button(self):
        for answer in (self.answer.replace(b"value=-2", b"value=-8"),
                       self.answer.replace(b"type=2 code=1", b"type=2 code=8"),
                       self.answer.replace(b"272 value=0", b"273 value=0")):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                mouse_events(answer)


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
