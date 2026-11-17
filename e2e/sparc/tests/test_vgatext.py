"""The VGA text reader (vgatext.py) against text buffers and BIOS data areas: built here byte by byte,
and captured from a FreeDOS 1.4 guest (tests/data/, freely redistributable text).

    python3 -m unittest -v tests/test_vgatext.py      (in e2e/sparc; standard library only)
"""
import gzip
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import vgatext  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def bda(mode=3, cols=80, rows=25, cursor=(0, 0), page=0, offset=0):
    b = bytearray(256)
    b[0x49] = mode
    b[0x4A:0x4C] = cols.to_bytes(2, "little")
    b[0x4E:0x50] = offset.to_bytes(2, "little")
    b[0x50 + page * 2], b[0x51 + page * 2] = cursor
    b[0x62] = page
    b[0x63:0x65] = (0x3D4 if mode != 7 else 0x3B4).to_bytes(2, "little")
    b[0x84] = rows - 1
    return bytes(b)


def screen(lines, cols=80, rows=25, attr=0x07, attrs=None):
    buf = bytearray()
    for r in range(rows):
        text = lines[r] if r < len(lines) else ""
        raw = text.encode("cp437") if isinstance(text, str) else text
        raw = raw.ljust(cols, b" ")[:cols]
        for c, ch in enumerate(raw):
            buf += bytes([ch, (attrs or {}).get((c, r), attr)])
    return bytes(buf)


class Memory:
    """Guest memory for vgatext.read(): the data area at 0x400 and buffers by address."""

    def __init__(self, regions):
        self.regions = regions
        self.reads = []

    def __call__(self, addr, size):
        self.reads.append((addr, size))
        for base, data in self.regions.items():
            if base <= addr < base + len(data):
                return data[addr - base:addr - base + size]
        return b"\xff" * size


class Decode(unittest.TestCase):
    def test_plain_text_and_trailing_blanks(self):
        lines, attrs = vgatext.decode(screen(["C:\\>dir", "", "Volume in drive C"]), 80, 25)
        self.assertEqual(len(lines), 25)
        self.assertEqual(lines[0].rstrip(), "C:\\>dir")
        self.assertEqual(len(lines[0]), 80)
        self.assertEqual(attrs[0][0], 0x07)

    def test_box_drawing_and_glyphs(self):
        raw = bytes([0xC9, 0xCD, 0xBB, 0x20, 0xB3, 0xDB, 0x01, 0x10, 0x00, 0xFE])
        lines, _ = vgatext.decode(screen([raw]), 80, 25)
        self.assertEqual(lines[0][:10], "╔═╗ │█☺► ■")

    def test_short_buffer_is_padded(self):
        lines, attrs = vgatext.decode(b"A\x07B\x07", 80, 2)
        self.assertEqual(lines[0].rstrip(), "AB")
        self.assertEqual(lines[1].strip(), "")


class DataArea(unittest.TestCase):
    def test_fields(self):
        info = vgatext.parse_bda(bda(mode=3, cols=80, rows=50, cursor=(4, 17), offset=0))
        self.assertEqual((info["mode"], info["cols"], info["rows"], info["cursor"]), (3, 80, 50, (4, 17)))

    def test_cursor_of_the_active_page(self):
        b = bytearray(bda(page=1))
        b[0x50:0x52] = bytes([9, 9])
        b[0x52:0x54] = bytes([3, 7])
        self.assertEqual(vgatext.parse_bda(bytes(b))["cursor"], (3, 7))

    def test_mode_bit7_ignored(self):
        self.assertEqual(vgatext.parse_bda(bda(mode=0x83))["mode"], 3)


class Read(unittest.TestCase):
    def test_80x25_colour(self):
        mem = Memory({0x400: bda(cursor=(4, 2)), 0xB8000: screen(["Starting MS-DOS...", "", "C:\\>"])})
        s = vgatext.read(mem)
        self.assertTrue(s.text_mode)
        self.assertEqual(s.cursor_line(), "C:\\>")
        self.assertEqual(s.text.splitlines()[0], "Starting MS-DOS...")
        self.assertEqual(mem.reads, [(0x400, 256), (0xB8000, 4000)])

    def test_80x50(self):
        lines = [f"line {i}" for i in range(50)]
        mem = Memory({0x400: bda(rows=50, cursor=(0, 49)), 0xB8000: screen(lines, rows=50)})
        s = vgatext.read(mem)
        self.assertEqual((s.rows, s.lines[49].rstrip()), (50, "line 49"))
        self.assertEqual(mem.reads[1], (0xB8000, 8000))

    def test_80x43(self):
        mem = Memory({0x400: bda(rows=43), 0xB8000: screen(["x"] * 43, rows=43)})
        self.assertEqual(len(vgatext.read(mem).lines), 43)

    def test_monochrome_mode7(self):
        mem = Memory({0x400: bda(mode=7), 0xB0000: screen(["MDA"])})
        s = vgatext.read(mem)
        self.assertEqual((s.base, s.line(0)), (0xB0000, "MDA"))

    def test_40_columns(self):
        mem = Memory({0x400: bda(mode=1, cols=40), 0xB8000: screen(["forty"], cols=40)})
        self.assertEqual(vgatext.read(mem).cols, 40)

    def test_second_page(self):
        page1 = screen(["page one"])
        mem = Memory({0x400: bda(page=1, offset=4096, cursor=(0, 0)),
                      0xB8000: screen(["page zero"]).ljust(4096, b"\x00") + page1})
        self.assertEqual(vgatext.read(mem).line(0), "page one")

    def test_graphics_mode_is_not_text(self):
        mem = Memory({0x400: bda(mode=0x13)})
        s = vgatext.read(mem)
        self.assertFalse(s.text_mode)
        self.assertIn("graphics", s.reason)
        self.assertEqual(len(mem.reads), 1)  # no buffer read at all

    def test_blank_window_is_not_text(self):
        # the data area says text, but 0xB8000 reads all 0xFF (VGA memory mapped at 0xA0000)
        mem = Memory({0x400: bda(mode=3)})
        self.assertFalse(vgatext.read(mem).text_mode)

    def test_cleared_text_screen_is_text(self):
        mem = Memory({0x400: bda(), 0xB8000: screen([])})
        s = vgatext.read(mem)
        self.assertTrue(s.text_mode)
        self.assertEqual(s.text.strip(), "")

    def test_zero_data_area_before_the_video_bios(self):
        mem = Memory({0x400: bytes(256), 0xB8000: screen(["SeaBIOS (version rel-1.17.0)"])})
        s = vgatext.read(mem)
        self.assertEqual((s.cols, s.rows, s.line(0)), (80, 25, "SeaBIOS (version rel-1.17.0)"))

    def test_highlighted_menu_bar(self):
        attrs = {(c, 5): 0x70 for c in range(10, 10 + len("Configure unallocated disk space"))}
        buf = screen(["Setup", "", "", "", "", "          Configure unallocated disk space", "          Exit"],
                     attr=0x1F, attrs=attrs)
        s = vgatext.read(Memory({0x400: bda(), 0xB8000: buf}))
        self.assertEqual(s.highlighted(), [(5, "Configure unallocated disk space")])

    def test_tail_up_to_the_cursor(self):
        mem = Memory({0x400: bda(cursor=(4, 3)), 0xB8000: screen(["a", "b", "", "C:\\>", "", "stale"])})
        self.assertEqual(vgatext.read(mem).tail(2), "b\nC:\\>")


class Wait(unittest.TestCase):
    def test_matches_after_polls(self):
        frames = iter([None, vgatext.read(Memory({0x400: bda(mode=0x12)})),
                       vgatext.read(Memory({0x400: bda(), 0xB8000: screen(["Welcome to Setup."])}))])
        m, s = vgatext.wait(lambda: next(frames), r"Welcome to Setup", timeout=5, interval=0)
        self.assertEqual(m.group(0), "Welcome to Setup")

    def test_timeout_shows_the_screen(self):
        s = vgatext.read(Memory({0x400: bda(), 0xB8000: screen(["Insert diskette"])}))
        with self.assertRaises(TimeoutError) as cm:
            vgatext.wait(lambda: s, r"C:\\>", timeout=0, interval=0)
        self.assertIn("Insert diskette", str(cm.exception))


class Captured(unittest.TestCase):
    """Buffers dumped from a FreeDOS 1.4 guest through QMP pmemsave (data area + text buffer)."""

    def load(self, name):
        if not os.path.exists(os.path.join(DATA, name)):
            self.skipTest(f"tests/data/{name} not captured yet")
        with gzip.open(os.path.join(DATA, name), "rb") as f:
            raw = f.read()
        return raw[:256], raw[256:]

    def test_freedos_installer(self):
        area, buf = self.load("vga-freedos-installer.bin.gz")
        s = vgatext.read(Memory({0x400: area, 0xB8000: buf}))
        self.assertTrue(s.text_mode)
        self.assertIn("Welcome to the FreeDOS 1.4 installation program.", s.text)
        self.assertRegex(s.cursor_line(), r"\[Y,N\]\?")
        self.assertIn("█", s.text)  # the logo is drawn with block characters

    def test_freedos_prompt(self):
        area, buf = self.load("vga-freedos-prompt.bin.gz")
        s = vgatext.read(Memory({0x400: area, 0xB8000: buf}))
        self.assertRegex(s.cursor_line(), r"^[A-Z]:\\[^>]*>$")


if __name__ == "__main__":
    unittest.main()
