from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doom import (RESPONSE, build_disk, check_effects, check_frame, check_overlay, parse_sums, play_command,
                  response, status_bar_differs)
import framebuffer


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

    def test_two_effects_are_enough(self):
        path = self.capture([(6500, 100), (600, 300)] * 2 + [(600, 400)])
        self.assertEqual(check_effects(path, 1.2)[0], 2)

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


def frame(width, height, scale, paint=None):
    """A P6 screendump with a game-coloured frame centred at `scale`; paint() may override pixels."""
    left, top = (width - 320 * scale) // 2, (height - 200 * scale) // 2
    pixels = bytearray(width * height * 3)
    for y in range(200 * scale):
        for x in range(320 * scale):
            i = ((top + y) * width + left + x) * 3
            pixels[i:i + 3] = bytes([(x // scale) % 200, (y // scale) % 7 * 30, 50])
    if paint:
        paint(pixels, width, left, top)
    return f"P6\n{width} {height}\n255\n".encode() + bytes(pixels)


class Play(unittest.TestCase):
    def test_response_files(self):
        self.assertEqual(response().split(), ["-iwad", "/data/freedoom1.wad", "-nosound", "-timedemo", "demo1"])
        self.assertEqual(response(None, True, play=True, fps=True).split(),
                         ["-iwad", "/data/freedoom1.wad", "-nomusic", "-fps"])
        self.assertEqual(response(3, play=True).split()[-2:], ["-scaling", "3"])
        self.assertEqual(RESPONSE, {False: "demo.rsp", True: "play.rsp"})

    def test_sums(self):
        digest = "a" * 64
        self.assertEqual(parse_sums(f"{digest}  kernel-fb-x86_64\n{digest} *fbdoom-x86_64\n"),
                         {"kernel-fb-x86_64": digest, "fbdoom-x86_64": digest})
        with self.assertRaisesRegex(ValueError, "bad SHA256SUMS"):
            parse_sums("xyz  kernel-fb-x86_64\n")

    def test_play_command(self):
        cmd = play_command("sparc64", "std", "/k", "/d.sqfs", ("vnc", 3), "pa", "/q", "tcg")
        self.assertEqual(cmd[cmd.index("-vnc") + 1], "0.0.0.0:3")
        self.assertEqual(cmd[cmd.index("-display") + 1], "none")
        self.assertIn("virtio-keyboard-pci", cmd)
        self.assertIn("pa,id=snd0", cmd)
        self.assertIn("@/data/play.rsp", cmd[cmd.index("-append") + 1])
        local = play_command("x86_64", "std", "/k", "/d", ("local", "gtk"), accelerator="kvm")
        self.assertEqual(local[local.index("-display") + 1], "gtk")
        self.assertNotIn("-vnc", local)
        self.assertEqual(local[local.index("-accel") + 1], "kvm")
        self.assertNotIn("virtio-keyboard-pci", local)

    def test_input_devices(self):
        self.assertEqual(framebuffer.display_args("std", "x86_64"), ["-vga", "std"])
        for display, arch in (("std", "sparc64"), ("bochs-display", "aarch64")):
            self.assertEqual(framebuffer.display_args(display, arch)[2:],
                             ["-device", "virtio-keyboard-pci", "-device", "virtio-mouse-pci"])

    def overlay(self, scale, colours=((0, 0, 0), (255, 255, 255))):
        s = max(2, scale)

        def paint(pixels, width, left, top):
            for y in range(7 * s):
                for x in range(5 * s):
                    on = 1 <= x // s <= 3 and 1 <= y // s <= 5 and (x // s + y // s) % 2
                    i = ((top + s + y) * width + left + s + x) * 3
                    pixels[i:i + 3] = bytes(colours[on])
        return frame(320 * scale + 8, 200 * scale + 8, scale, paint)

    def test_overlay(self):
        for scale in (1, 3):
            data = self.overlay(scale)
            check_overlay(data, scale)
            self.assertEqual(check_frame(data, scale), scale)  # the box keeps the integer scaling
        with self.assertRaisesRegex(ValueError, "two colours"):
            check_overlay(frame(648, 408, 2), 2)
        with self.assertRaisesRegex(ValueError, "contrast"):
            check_overlay(self.overlay(2, ((90, 90, 90), (120, 120, 120))), 2)

    def test_status_bar(self):
        title = frame(320, 200, 1)

        def bar(pixels, width, left, top):
            i = ((top + 190) * width + left + 10) * 3
            pixels[i:i + 3] = bytes([255, 255, 255])
        self.assertFalse(status_bar_differs(title, title, 1))
        self.assertTrue(status_bar_differs(title, frame(320, 200, 1, bar), 1))
