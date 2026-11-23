from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doom import build_disk, check_effects, check_frame


class DemoSound(unittest.TestCase):
    def capture(self, runs):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "demo.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setparams((2, 2, 1000, 0, "NONE", ""))
            for level, frames in runs:
                wav.writeframes(struct.pack("<hh", level, -level) * frames)
        return path

    def test_separate_effects(self):
        path = self.capture([(6500, 100), (600, 300)] * 3)
        self.assertEqual(check_effects(path, 1.2), (3, 1.2))
        with self.assertRaisesRegex(ValueError, "duration"):
            check_effects(path, 20)
        long_capture = self.capture([(6500, 500), (0, 1000)] * 3)
        with self.assertRaisesRegex(ValueError, "duration"):
            check_effects(long_capture, 1)

    def test_reject_silence_continuous_sound_and_clicks(self):
        for runs in ([(0, 1200)], [(6500, 1200)], [(30000, 1), (0, 399)] * 3,
                     [(6500, 180), (0, 20)] * 6):
            with self.subTest(runs=runs), self.assertRaisesRegex(ValueError, "bursts"):
                check_effects(self.capture(runs), 1.2)


class GameFrame(unittest.TestCase):
    def test_centre_contains_game_colours(self):
        row = bytes(range(240)) * 4
        check_frame(b"P6\n320 200\n255\n" + row * 200)

    def test_integer_scale_and_center(self):
        # 2x with a one-pixel margin on every side.
        width = 642
        row = bytes(3) + b"".join(bytes([i % 256]) * 6 for i in range(320)) + bytes(3)
        border = bytes(3 * width)
        pixels = bytearray(border + row * 400 + border)
        header = b"P6\n642 402\n255\n"
        self.assertEqual(check_frame(header + pixels), 2)
        for index in (3 * (width + 2), 3 * (width * 2 + 1)):
            pixels[index] ^= 1
            with self.assertRaisesRegex(ValueError, "incorrect framebuffer scaling"):
                check_frame(header + pixels)
            pixels[index] ^= 1

    def test_requested_scale(self):
        # A 1x frame centred on a 642x402 screen, checked at the scale asked for.
        width = 642
        row = bytes(3 * 161) + bytes(range(240)) * 4 + bytes(3 * 161)
        border = bytes(3 * width)
        pixels = border * 101 + row * 200 + border * 101
        header = b"P6\n642 402\n255\n"
        self.assertEqual(check_frame(header + pixels, 1), 1)
        with self.assertRaisesRegex(ValueError, "doesn't fit"):
            check_frame(header + pixels, 3)

    def test_firmware_colours_in_margin(self):
        margin = bytes(range(48))
        row = margin + bytes(320 * 3) + margin
        with self.assertRaisesRegex(ValueError, "missing game image"):
            check_frame(b"P6\n352 200\n255\n" + row * 200)

    def test_incomplete_screendump(self):
        with self.assertRaisesRegex(ValueError, "invalid QEMU screendump"):
            check_frame(b"P6\n320 200\n255\n" + bytes(320 * 199 * 3))


@unittest.skipUnless(shutil.which("mksquashfs") and shutil.which("unsquashfs"), "requires squashfs-tools")
class DataDisk(unittest.TestCase):
    def test_payload_contents_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            executable = directory / "input"
            executable.write_bytes(b"ELF fixture")
            wad = directory / "wad"
            wad.write_bytes(b"IWAD fixture")
            disk = build_disk(directory, executable, wad)
            root = directory / "extracted"
            subprocess.run(["unsquashfs", "-no-progress", "-d", root, disk], check=True,
                           stdout=subprocess.DEVNULL)
            self.assertEqual((root / "fbdoom").read_bytes(), executable.read_bytes())
            self.assertEqual((root / "fbdoom").stat().st_mode & 0o777, 0o755)
            self.assertEqual((root / "freedoom1.wad").read_bytes(), wad.read_bytes())
            self.assertEqual((root / "demo.rsp").read_text().split(),
                             ["-iwad", "/data/freedoom1.wad", "-nosound", "-timedemo", "demo1"])

    def test_sound_and_scale_in_response_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "input").write_bytes(b"ELF fixture")
            (directory / "wad").write_bytes(b"IWAD fixture")
            disk = build_disk(directory, directory / "input", directory / "wad", 1, with_sound=True)
            root = directory / "extracted"
            subprocess.run(["unsquashfs", "-no-progress", "-d", root, disk], check=True,
                           stdout=subprocess.DEVNULL)
            self.assertEqual((root / "demo.rsp").read_text().split(),
                             ["-iwad", "/data/freedoom1.wad", "-nomusic", "-scaling", "1",
                              "-timedemo", "demo1"])
