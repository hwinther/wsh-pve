from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doom import check_frame


class GameFrame(unittest.TestCase):
    def test_centre_contains_game_colours(self):
        row = bytes(range(240)) * 4
        check_frame(b"P6\n320 200\n255\n" + row * 200)

    def test_firmware_colours_in_margin(self):
        margin = bytes(range(48))
        row = margin + bytes(320 * 3) + margin
        with self.assertRaisesRegex(ValueError, "missing game image"):
            check_frame(b"P6\n352 200\n255\n" + row * 200)

    def test_incomplete_screendump(self):
        with self.assertRaisesRegex(ValueError, "invalid QEMU screendump"):
            check_frame(b"P6\n320 200\n255\n" + bytes(320 * 199 * 3))
