"""The x86 guest's screen as exact text: the VGA text buffer read from guest memory through QMP.

In a VGA text mode the screen is a buffer of (character, attribute) byte pairs at physical 0xB8000
(0xB0000 for the monochrome mode 7), 80x25 after boot and 80x43/80x50 after `MODE CON LINES=50`.
QMP `pmemsave` copies it into a file in 1-2 ms and exactly, where a screendump + OCR takes 150-300 ms
and misreads characters (README.md, "DOS and other floppy installs").

What the buffer means comes from the BIOS data area at 0x400 (one more `pmemsave` of 256 bytes),
which the video BIOS keeps up to date for every mode set through int 10h:

    0x449  video mode (0-3 colour text, 7 monochrome text, anything else a graphics mode)
    0x44A  columns (word)
    0x44E  start of the active page in the buffer (word)
    0x450  cursor position per page, 8 x (column, row)
    0x462  active page
    0x484  rows - 1 (EGA/VGA BIOS)

A program that programs the VGA registers itself (a game's mode X, a Linux kernel) leaves the data
area stale; so does a guest that has no BIOS any more. Such a screen is reported as text only when the
buffer also looks like text (not all 0x00/0xFF, which is what QEMU returns for 0xB8000 while the VGA's
memory map points at 0xA0000 in a graphics mode); otherwise `text_mode` is False and callers fall back
to OCR of a screendump.

Characters are decoded as code page 437 with the VGA glyphs for 0x01-0x1F (the smileys, arrows and
card suits), so box drawing reads as box drawing; 0x00 is a blank.

Pure functions (decode, parse_bda, Screen) plus `read(pmem)` that takes a function reading guest
memory, `pmem(address, size) -> bytes`; lab.Machine.pmem() is that function for a QEMU of the lab's
own and for a PVE VM. tests/test_vgatext.py checks them against captured buffers.
"""
import re
import time

BDA = 0x400
BDA_SIZE = 0x100
TEXT_MODES = {0: (40, 25), 1: (40, 25), 2: (80, 25), 3: (80, 25), 7: (80, 25)}
COLOR_BASE, MONO_BASE = 0xB8000, 0xB0000

# The VGA ROM font's glyphs for the control range, as their Unicode look-alikes (what DOS shows).
LOW_GLYPHS = (" ☺☻♥♦♣♠•◘○◙♂♀♪♫☼"
              "►◄↕‼¶§▬↨↑↓→←∟↔▲▼")
CP437 = [LOW_GLYPHS[i] if i < 32 else ("⌂" if i == 127 else bytes([i]).decode("cp437")) for i in range(256)]


def decode(buf, cols, rows):
    """(lines, attributes) of a text buffer: `rows` strings of `cols` characters and `rows` bytes
    objects of `cols` attribute bytes. A short buffer is padded with blanks."""
    need = cols * rows * 2
    buf = bytes(buf[:need]).ljust(need, b"\x00")
    lines, attrs = [], []
    for r in range(rows):
        row = buf[r * cols * 2:(r + 1) * cols * 2]
        lines.append("".join(CP437[c] for c in row[0::2]))
        attrs.append(bytes(row[1::2]))
    return lines, attrs


def parse_bda(bda):
    """What the BIOS data area (256 bytes from 0x400) says about the display."""
    b = bytes(bda).ljust(BDA_SIZE, b"\x00")
    mode = b[0x49] & 0x7F  # bit 7: the mode set didn't clear the screen
    page = b[0x62] & 7
    cols = b[0x4A] | b[0x4B] << 8
    rows = b[0x84] + 1
    col, row = b[0x50 + page * 2], b[0x51 + page * 2]
    return {"mode": mode, "cols": cols, "rows": rows, "page": page, "page_offset": b[0x4E] | b[0x4F] << 8,
            "cursor": (col, row), "crtc": b[0x63] | b[0x64] << 8}


def looks_like_text(buf):
    """Whether a buffer can be a text screen: not all one byte value of 0x00 or 0xFF (an unmapped or
    graphics-mode window). A cleared text screen (space, attribute 07) is text."""
    if not buf:
        return False
    first = buf[0]
    if first in (0x00, 0xFF) and buf.count(first) == len(buf):
        return False
    return True


class Screen:
    """One reading of the screen."""

    def __init__(self, bda_info, buf, text_mode, base, reason=""):
        self.mode = bda_info["mode"]
        self.cols, self.rows = bda_info["cols"], bda_info["rows"]
        self.cursor = bda_info["cursor"]
        self.page = bda_info["page"]
        self.base = base
        self.text_mode = text_mode
        self.reason = reason
        self.raw = bytes(buf)
        if text_mode:
            self.lines, self.attrs = decode(buf, self.cols, self.rows)
        else:
            self.lines, self.attrs = [], []

    @property
    def text(self):
        """The screen as text, trailing blanks of each line removed (the interface of
        lab.Machine.screen_text)."""
        return "\n".join(line.rstrip() for line in self.lines)

    def line(self, n):
        return self.lines[n].rstrip() if 0 <= n < len(self.lines) else ""

    def cursor_line(self):
        """The line the cursor is on (the prompt the guest waits at)."""
        return self.line(self.cursor[1])

    def tail(self, n):
        """The last `n` non-empty lines up to the cursor's line."""
        upto = self.lines[:self.cursor[1] + 1] if self.cursor[1] < len(self.lines) else self.lines
        return "\n".join([x.rstrip() for x in upto if x.strip()][-n:])

    def attr_at(self, col, row):
        return self.attrs[row][col] if self.text_mode else None

    def highlighted(self, attr=None):
        """Lines (row, text) drawn with another attribute than the screen's most common one, or with
        `attr`: the selected item of a menu (DOS SETUP's bar, an FDISK option)."""
        if not self.text_mode:
            return []
        common = {}
        for a in self.attrs:
            for x in a:
                common[x] = common.get(x, 0) + 1
        base = max(common, key=common.get)
        out = []
        for r, (line, a) in enumerate(zip(self.lines, self.attrs)):
            sel = "".join(ch for ch, x in zip(line, a) if (x == attr if attr is not None else x != base))
            if sel.strip():
                out.append((r, sel.strip()))
        return out

    def as_dict(self):
        return {"mode": self.mode, "cols": self.cols, "rows": self.rows, "cursor": list(self.cursor),
                "page": self.page, "text_mode": self.text_mode, "reason": self.reason,
                "text": self.text if self.text_mode else None}


def screen_from(bda, read_buffer):
    """A Screen from the data area's bytes and `read_buffer(address, size)` for the text buffer."""
    info = parse_bda(bda)
    if info["cols"] == 0 and info["mode"] == 0:  # an empty data area: the BIOS hasn't set a mode yet
        info["mode"] = 3
    mode = info["mode"]
    if mode not in TEXT_MODES:
        return Screen(info, b"", False, None, f"graphics mode {mode:#04x}")
    # The data area can be zero before the video BIOS ran: take the mode's own size then.
    dcols, drows = TEXT_MODES[mode]
    if not 20 <= info["cols"] <= 132:
        info["cols"] = dcols
    if not (12 <= info["rows"] <= 60) or info["rows"] == 1:
        info["rows"] = drows
    base = MONO_BASE if mode == 7 else COLOR_BASE
    size = info["cols"] * info["rows"] * 2
    offset = info["page_offset"] if info["page_offset"] + size <= 0x8000 else 0
    buf = read_buffer(base + offset, size)
    if not looks_like_text(buf):
        return Screen(info, buf, False, base + offset, "the text buffer is blank (0x00/0xFF): not a text screen")
    return Screen(info, buf, True, base + offset)


def read(pmem):
    """Read the screen through `pmem(address, size) -> bytes` (two reads: data area, buffer)."""
    return screen_from(pmem(BDA, BDA_SIZE), pmem)


def wait(read_screen, pattern, timeout=300, interval=0.5, tail=0, flags=re.M, on_poll=None):
    """Poll `read_screen()` (a Screen, or None when the screen isn't readable as text) until the regex
    is on the screen (or, with tail > 0, in the last `tail` non-empty lines up to the cursor). Returns
    (match, screen); raises TimeoutError with the last screen in the message."""
    rx = re.compile(pattern, flags)
    end = time.time() + timeout
    last = None
    while True:
        s = read_screen()
        if s is not None and s.text_mode:
            last = s
            text = s.tail(tail) if tail else s.text
            m = rx.search(text)
            if m:
                return m, s
        if on_poll:
            on_poll(s)
        if time.time() > end:
            shown = last.text if last else "(no text screen)"
            raise TimeoutError(f"no {pattern!r} on the VGA text screen within {timeout}s; screen:\n{shown}")
        time.sleep(interval)
