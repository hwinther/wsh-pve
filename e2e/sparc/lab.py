#!/usr/bin/env python3
"""Drive a sparc guest under QEMU the way a person would: watch the serial console and the
framebuffer, type on either, and record every step with screenshots.

The guest's serial port goes through a VT100 emulator (pyte), so a full-screen installer on ttya can be
matched and captured as text. The framebuffer (cg3/tcx) is captured with QMP `screendump` and can be
matched through OCR (tesseract); keys reach the guest's Sun keyboard through QMP `send-key`.

Run a scenario:   lab.py run scenarios/solaris26-serial-install.py --out /work/run1 [--var KEY=VALUE ...]
Interactive:      lab.py serve --out /work/s1 -- <qemu args>     (then `lab.py ctl ...` from another shell)
A PVE VM:         lab.py run <scenario> --pve <vmid> --out ...   (on the PVE node; see PveMachine)
Recordings:       lab.py cast <run dir> [--max-idle 1] [--speed 2] [--check]   (-> serial.fast.cast)
Install a target: lab.py install sol26-ss5 --vmid 120 [--out DIR]   (on the PVE node; see install.py)
                  lab.py install sol26-ss5 --vmid 120 --check --export /mnt/os/disks   (store the disk)
                  lab.py boot-test sol26-ss5 --disk /mnt/os/disks/install-sol26-ss5.raw --vmid 121
                  lab.py targets | lab.py media [<target>]
Mirror storage:   lab.py mirror sync /mnt/nas/media --storage mirror [--prune]   (symlinks; see mirror.py)
                  lab.py mirror link <file> [--root DIR | --as NAME] | lab.py mirror list
                  lab.py mirror init|plan|apply|import|tidy --storage mirror   (from wsh-mirror.yaml)
                  lab.py mirror timer --storage mirror --interval 10min [--remove]

The wsh-lab package installs it as `wsh-lab` (wsh-lab install ..., wsh-lab targets, ...), with the
scenarios in /usr/share/wsh-lab/scenarios.
"""
import argparse
import html
import importlib.util
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time

import recording

ANSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][0-9A-Za-z]|\x1b[=>78DEHMNOZc]")


class QemuDied(Exception):
    pass


class Timeout(Exception):
    pass


class Qmp:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(path)
        self.file = self.sock.makefile("rwb")
        self.lock = threading.Lock()
        self._read()  # greeting
        self.cmd("qmp_capabilities")

    def _read(self):
        while True:
            line = self.file.readline()
            if not line:
                raise QemuDied("QMP connection closed")
            msg = json.loads(line)
            if "event" not in msg:
                return msg

    def cmd(self, name, **args):
        with self.lock:
            self.file.write(json.dumps({"execute": name, "arguments": args}).encode() + b"\n")
            self.file.flush()
            reply = self._read()
        if "error" in reply:
            raise RuntimeError(f"QMP {name}: {reply['error'].get('desc')}")
        return reply.get("return")


# QMP qcodes for typing on the Sun keyboard (send-key); shifted characters for a US layout.
QCODES = {" ": "spc", "\r": "ret", "\n": "ret", "\t": "tab", "-": "minus", "=": "equal", "[": "bracket_left",
          "]": "bracket_right", ";": "semicolon", "'": "apostrophe", "`": "grave_accent", "\\": "backslash",
          ",": "comma", ".": "dot", "/": "slash", "\b": "backspace"}
SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
           "_": "minus", "+": "equal", "{": "bracket_left", "}": "bracket_right", ":": "semicolon",
           '"': "apostrophe", "~": "grave_accent", "|": "backslash", "<": "comma", ">": "dot", "?": "slash"}
# Function keys on the serial console: the Solaris installer's curses screens accept Esc-<n> for F<n>.
SERIAL_KEYS = {"enter": "\r", "esc": "\x1b", "tab": "\t", "space": " ", "backspace": "\b",
               "up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C", "left": "\x1b[D",
               **{f"f{n}": f"\x1b{n}" for n in range(1, 10)}, "ctrl-c": "\x03", "ctrl-d": "\x04",
               "ctrl-n": "\x0e", "ctrl-p": "\x10", "ctrl-f": "\x06", "ctrl-b": "\x02"}


def new_terminal(cols=80, rows=24):
    """The VT100 emulator the serial console goes through: (screen, stream).

    8-bit, not UTF-8 (pyte ignores charset switches in UTF-8 mode), and G1 = DEC line drawing as on a
    VT100 after Solaris's terminfo init: the installer draws its boxes with SO/SI, which would otherwise
    show as letters ("qqqq")."""
    import pyte

    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    stream.select_other_charset("@")
    stream.feed(b"\x1b)0")
    return screen, stream


def qcodes_for(ch):
    """The QMP qcodes that type one character on a US keyboard (send-key), e.g. "A" -> shift, a."""
    if ch.isascii() and ch.isalpha():
        return ["shift", ch.lower()] if ch.isupper() else [ch]
    if ch.isascii() and ch.isdigit():
        return [ch]
    if ch in SHIFTED:
        return ["shift", SHIFTED[ch]]
    if ch in QCODES:
        return [QCODES[ch]]
    raise ValueError(f"no key for {ch!r} on a US keyboard")


def ocr(png):
    """The text tesseract reads in a screenshot (one block of text, --psm 6)."""
    r = subprocess.run(["tesseract", png, "-", "--psm", "6"], capture_output=True, text=True)
    return r.stdout


class Machine:
    """One QEMU process plus its serial console, QMP monitor and a step log with screenshots."""

    def __init__(self, out, qemu_args, cols=80, rows=24, ocr=True):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.serial_path = os.path.join(out, "serial.sock")
        self.qmp_path = os.path.join(out, "qmp.sock")
        for p in (self.serial_path, self.qmp_path):
            if os.path.exists(p):
                os.unlink(p)
        self.args = list(qemu_args) + [
            "-chardev", f"socket,id=ttya,path={self.serial_path},server=on,wait=on",
            "-serial", "chardev:ttya",
            "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
            "-display", "none",
        ]
        self.screen, self.stream = new_terminal(cols, rows)
        self.text = ""  # serial output, escape sequences removed, from which expect() consumes
        self.pos = 0
        self.text_base = 0  # characters dropped from the front of self.text (only mcp_server.py drops)
        self.cond = threading.Condition()
        self.steps = []
        self.metrics = {}  # measurements for result.json (cpu_use() and the scenario's own)
        self.ocr = ocr
        self.t0 = time.time()
        self.raw = open(os.path.join(out, "serial.raw"), "wb")
        self.cast = recording.CastWriter(os.path.join(out, "serial.cast"), cols, rows, self.t0, init="\x1b)0")
        self.stderr = open(os.path.join(out, "qemu.stderr"), "wb")
        with open(os.path.join(out, "qemu.cmd"), "w", encoding="utf-8") as f:
            f.write(shlex.join(self.args) + "\n")
        self.proc = subprocess.Popen(self.args, stdin=subprocess.DEVNULL, stdout=self.stderr, stderr=self.stderr)
        self.ser = self._connect(self.serial_path)
        threading.Thread(target=self._reader, daemon=True).start()
        self.qmp = Qmp(self._wait_for(self.qmp_path))
        self.log(f"started: {shlex.join(self.args)}")

    def _wait_for(self, path, timeout=30):
        end = time.time() + timeout
        while not os.path.exists(path):
            self._check_alive()
            if time.time() > end:
                raise Timeout(f"{path} never appeared")
            time.sleep(0.1)
        return path

    def _connect(self, path):
        self._wait_for(path)
        s = socket.socket(socket.AF_UNIX)
        s.connect(path)
        return s

    def _reader(self, sock=None):
        sock = sock or self.ser  # its own socket: PveMachine.power_cycle() replaces self.ser
        while True:
            try:
                data = sock.recv(4096)
            except OSError:
                data = b""
            with self.cond:
                if not data:
                    self.cond.notify_all()
                    return
                self._feed(data)
                self.cond.notify_all()

    def _feed(self, data):
        """One read from the serial socket (self.cond held): serial.raw, the cast, the terminal, the text."""
        self.raw.write(data)
        self.raw.flush()
        if getattr(self, "seven_bit", False):
            data = bytes(b & 0x7F for b in data)  # SERIAL_7BIT: the guest sends parity in bit 7
        self.cast.output(data)
        self.stream.feed(data)
        self.text += ANSI.sub(b"", data).replace(b"\r", b"").decode("latin-1")

    def _check_alive(self):
        code = self.proc.poll()
        if code is not None:
            self.stderr.flush()
            err = open(os.path.join(self.out, "qemu.stderr"), "rb").read().decode(errors="replace")
            raise QemuDied(f"QEMU exited with {code}: {err.strip()[-2000:]}")

    def elapsed(self):
        return time.time() - self.t0

    def log(self, msg):
        line = f"[{self.elapsed():8.1f}s] {msg}"
        print(line, flush=True)
        with open(os.path.join(self.out, "steps.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # --- serial console -------------------------------------------------------------------------

    def screen_text(self):
        with self.cond:
            return "\n".join(line.rstrip() for line in self.screen.display)

    def expect(self, pattern, timeout=300, screen=False):
        """Wait for a regex on the serial output after the previous match (or, with screen=True, anywhere
        on the emulated terminal screen). Returns the match."""
        rx = re.compile(pattern, re.M)
        end = time.time() + timeout
        with self.cond:
            while True:
                m = rx.search(self.screen_text_unlocked() if screen else self.text, 0 if screen else self.pos)
                if m:
                    if not screen:
                        self.pos = m.end()
                    self.log(f"matched {pattern!r}")
                    return m
                self._check_alive()
                left = end - time.time()
                if left <= 0:
                    raise Timeout(f"no {pattern!r} within {timeout}s; screen:\n{self.screen_text_unlocked()}")
                self.cond.wait(min(left, 2))

    def screen_text_unlocked(self):
        return "\n".join(line.rstrip() for line in self.screen.display)

    def expect_any(self, patterns, timeout=300, screen=False):
        """Like expect() for several regexes; returns the index of the one that matched first."""
        alt = "|".join(f"(?P<p{i}>{p})" for i, p in enumerate(patterns))
        m = self.expect(alt, timeout, screen)
        return next(i for i in range(len(patterns)) if m.group(f"p{i}") is not None)

    def send(self, text, delay=0.05):
        """Type on the serial console, slowly enough for the guest's tty input buffer."""
        text = str(text)
        for ch in text:
            self.ser.sendall(ch.encode("latin-1"))
            time.sleep(delay)

    def key(self, *names):
        for name in names:
            # an escape sequence must arrive in one piece, or curses takes the ESC on its own
            self.ser.sendall(SERIAL_KEYS[name.lower()].encode("latin-1"))
            time.sleep(0.4)

    def quiet(self, seconds, timeout=600):
        """Wait until the serial console has been silent for `seconds`."""
        end = time.time() + timeout
        while time.time() < end:
            with self.cond:
                size = len(self.text)
            time.sleep(seconds)
            self._check_alive()
            with self.cond:
                if len(self.text) == size:
                    return
        raise Timeout(f"serial never went quiet for {seconds}s")

    # Absolute cursors into the serial output, for a client that polls (mcp_server.py) instead of a
    # scenario that consumes with expect(): a cursor counts characters of self.text since the start,
    # so it stays valid when the front of the text is dropped. Neither touches expect()'s position.

    def serial_cursor(self):
        """The cursor at the end of the serial output so far."""
        with self.cond:
            return self.text_base + len(self.text)

    def serial_since(self, cursor=None, limit=4000):
        """At most `limit` characters of serial output from `cursor` (None: the end, so nothing yet).
        Returns the text, the cursor after it, the end, whether more follows, and how many characters
        were lost because the cursor points before what is still kept."""
        with self.cond:
            end = self.text_base + len(self.text)
            start = end if cursor is None else min(int(cursor), end)
            lost = max(0, self.text_base - start)
            start = max(start, self.text_base)
            text = self.text[start - self.text_base:start - self.text_base + int(limit)]
        nxt = start + len(text)
        return {"text": text, "cursor": nxt, "end": end, "more": nxt < end, "lost": lost}

    def serial_wait(self, pattern, cursor=None, timeout=60, context=1000):
        """Wait for a regex in the serial output after `cursor` (None: from now on). A timeout isn't an
        exception: it returns matched False, the cursor at the end and the last `context` characters.
        A match returns its text, groups, span (as cursors) and up to `context` characters before it."""
        rx = re.compile(pattern, re.M)
        end_t = time.time() + float(timeout)
        with self.cond:
            start = self.text_base + len(self.text) if cursor is None else int(cursor)
            while True:
                lo = max(start, self.text_base) - self.text_base
                m = rx.search(self.text, lo)
                if m:
                    return {"matched": True, "match": m.group(0), "groups": list(m.groups()),
                            "start": self.text_base + m.start(), "cursor": self.text_base + m.end(),
                            "before": self.text[max(lo, m.start() - int(context)):m.start()]}
                self._check_alive()
                left = end_t - time.time()
                if left <= 0:
                    return {"matched": False, "cursor": self.text_base + len(self.text),
                            "tail": self.text[max(lo, len(self.text) - int(context)):]}
                self.cond.wait(min(left, 1))

    # --- framebuffer ----------------------------------------------------------------------------

    def screendump(self, name):
        """Save the framebuffer as <name>.png; returns the path."""
        png = os.path.join(self.out, f"{name}.png")
        try:
            self.qmp.cmd("screendump", filename=png, format="png")
        except RuntimeError:  # no libpng in this QEMU build: dump PPM and convert
            ppm = png[:-4] + ".ppm"
            self.qmp.cmd("screendump", filename=ppm)
            from PIL import Image

            Image.open(ppm).save(png)
            os.unlink(ppm)
        return png

    def refresh(self, interval=0.5):
        """Update the display every `interval` seconds, the way a connected VNC client does.

        cg3 raises its vertical-retrace interrupt only from a display update, and with -display none
        (or VNC with no client connected) nothing updates the display: the guest gets no vsync at
        all, and Solaris's cgthree driver, which loads the colour map from that interrupt, waits."""
        if getattr(self, "_refreshing", False) or not interval:
            return
        self._refreshing = True
        path = os.path.join(self.out, "_refresh.ppm")

        def loop():
            while self.proc.poll() is None:
                try:
                    self.qmp.cmd("screendump", filename=path)
                    if getattr(self, "fbrec", None):  # the framebuffer video takes its frames from here
                        self.fbrec.offer(path)
                except Exception:
                    pass
                time.sleep(interval)

        threading.Thread(target=loop, daemon=True).start()
        self.log(f"display refresh every {interval}s")

    def fb_text(self, png):
        return ocr(png) if self.ocr else ""

    def fb_expect(self, pattern, timeout=300, interval=5):
        """Wait for a regex in the OCR text of the framebuffer."""
        rx = re.compile(pattern, re.I | re.M)
        end = time.time() + timeout
        n = 0
        while True:
            self._check_alive()
            png = self.screendump("_fb_poll")
            text = self.fb_text(png)
            if rx.search(text):
                self.log(f"framebuffer matched {pattern!r}")
                return text
            if time.time() > end:
                raise Timeout(f"no {pattern!r} on the framebuffer within {timeout}s; OCR:\n{text}")
            n += 1
            time.sleep(interval)

    def fb_expect_any(self, patterns, timeout=300, interval=5, tail=0):
        """Wait for any of several regexes on the framebuffer (OCR); returns the index that matched.

        The framebuffer keeps what was answered already, so `tail` > 0 looks only at the last `tail`
        lines of text: the prompt the guest is waiting at."""
        rxs = [re.compile(p, re.I | re.M) for p in patterns]
        end = time.time() + timeout
        while True:
            self._check_alive()
            text = self.fb_text(self.screendump("_fb_poll"))
            if tail:
                text = "\n".join([line for line in text.splitlines() if line.strip()][-tail:])
            for i, rx in enumerate(rxs):
                if rx.search(text):
                    self.log(f"framebuffer matched {patterns[i]!r}")
                    return i
            if time.time() > end:
                raise Timeout(f"none of {patterns!r} on the framebuffer within {timeout}s; OCR:\n{text}")
            time.sleep(interval)

    def fb_check(self, png, size=None):
        """Fail unless the screenshot `png` has `size` (width, height) and isn't one flat colour."""
        from PIL import Image

        img = Image.open(png)
        if size and img.size != tuple(size):
            raise AssertionError(f"{os.path.basename(png)} is {img.size[0]}x{img.size[1]}, "
                                 f"expected {size[0]}x{size[1]}")
        lo, hi = img.convert("L").getextrema()
        if lo == hi:
            raise AssertionError(f"{os.path.basename(png)} is blank (every pixel {lo})")
        self.log(f"{os.path.basename(png)}: {img.size[0]}x{img.size[1]}, not blank")

    def fb_stable(self, seconds=10, timeout=600, interval=2):
        """Wait until the framebuffer hasn't changed for `seconds`."""
        from PIL import Image, ImageChops

        end = time.time() + timeout
        last, since = None, time.time()
        while time.time() < end:
            self._check_alive()
            img = Image.open(self.screendump("_fb_poll")).convert("RGB")
            if last is None or ImageChops.difference(img, last).getbbox():
                last, since = img, time.time()
            elif time.time() - since >= seconds:
                return
            time.sleep(interval)
        raise Timeout(f"framebuffer never stable for {seconds}s")

    def fb_type(self, text, hold=60, delay=0.08):
        """Type on the guest keyboard (QMP send-key)."""
        for ch in text:
            keys = qcodes_for(ch)
            self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in keys], **{"hold-time": hold})
            time.sleep(delay)

    def fb_key(self, *qcodes):
        """Press one key or a chord, e.g. fb_key("stop", "a") for Stop-A."""
        self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in qcodes], **{"hold-time": 100})

    # --- the VGA text screen (x86 guests; vgatext.py) ------------------------------------------------

    def pmem(self, address, size):
        """`size` bytes of guest physical memory from `address` (QMP pmemsave into a private temporary
        file next to the evidence, read and removed)."""
        import tempfile

        fd, path = tempfile.mkstemp(prefix="_pmem", dir=self.out)
        os.close(fd)
        try:
            self.qmp.cmd("pmemsave", val=int(address), size=int(size), filename=path)
            with open(path, "rb") as f:
                return f.read()
        finally:
            os.unlink(path)

    def vga_screen(self):
        """The VGA text screen (vgatext.Screen: lines, attributes, cursor, mode); text_mode is False in a
        graphics mode, where only a screendump shows the screen."""
        import vgatext

        return vgatext.read(self.pmem)

    def vga_text(self, ocr_fallback=True):
        """The screen as text: exact from the VGA text buffer, or OCR of a screendump when the guest is
        in a graphics mode (and `ocr_fallback`)."""
        s = self.vga_screen()
        if s.text_mode:
            return s.text
        return self.fb_text(self.screendump("_fb_poll")) if ocr_fallback else ""

    def vga_expect(self, pattern, timeout=300, interval=0.5, tail=0):
        """Wait for a regex on the VGA text screen (with tail > 0: in the last `tail` non-empty lines up
        to the cursor, the prompt the guest waits at). Returns the vgatext.Screen it matched on."""
        import vgatext

        def read():
            self._check_alive()
            return self.vga_screen()

        try:
            _, s = vgatext.wait(read, pattern, timeout, interval, tail)
        except TimeoutError as e:
            raise Timeout(str(e))
        self.log(f"screen matched {pattern!r}")
        return s

    def vga_expect_any(self, patterns, timeout=300, interval=0.5, tail=0):
        """Like vga_expect() for several regexes; returns (index of the one that matched, the screen)."""
        alt = "|".join(f"(?P<p{i}>{p})" for i, p in enumerate(patterns))
        s = self.vga_expect(alt, timeout, interval, tail)
        text = s.tail(tail) if tail else s.text
        m = re.search(alt, text, re.M)
        return next(i for i in range(len(patterns)) if m.group(f"p{i}") is not None), s

    def vga_snap(self, title):
        """A step whose screen is the VGA text screen: NNN-vga.txt and its rendering, beside the
        framebuffer screenshot."""
        s = self.vga_screen()
        step = self.snap(title, fb=True, term=False)
        if s.text_mode:
            base = os.path.join(self.out, f"{step['n']:03d}-vga")
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(s.text + "\n")
            step["vga"] = s.text
            step["ttya_png"] = render_terminal(s.text, base + ".png", cols=s.cols, rows=s.rows)
            self.write_report()
        return step

    def medium(self, drive):
        """The file in a removable drive (QMP query-block), or None when it is empty. `drive`: the
        PVE/QEMU drive name (floppy0, ide2, ...)."""
        for b in self.qmp.cmd("query-block"):
            qdev = b.get("qdev", "")
            if b.get("device") in (drive, f"drive-{drive}") or qdev.endswith(f"/{drive}") or qdev == drive:
                ins = b.get("inserted")
                return ins.get("file") if ins else None
        raise RuntimeError(f"no drive {drive} in query-block")

    def change_medium(self, drive, volume):
        """Put a file into a removable drive of the lab's own QEMU (`-drive if=floppy` is floppy0), or
        "none" to empty it. PveMachine does it through PVE instead."""
        if volume == "none":
            self.qmp.cmd("eject", device=drive, force=True)
        else:
            self.qmp.cmd("blockdev-change-medium", device=drive, filename=volume)
        self.log(f"{drive}: {volume}")

    # --- the step log ---------------------------------------------------------------------------

    def snap(self, title, fb=True, term=True):
        """Record a step: the terminal screen (text + PNG) and the framebuffer screenshot."""
        n = len(self.steps) + 1
        base = f"{n:03d}"
        step = {"n": n, "t": round(self.elapsed(), 1), "title": title}
        with self.cond:  # the step's marker in the recordings, where in the console output this screen is
            text = self.screen_text_unlocked()
            self.mark(f"{n}. {title}")
        if term:
            with open(os.path.join(self.out, f"{base}-ttya.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
            step["ttya"] = text
            step["ttya_png"] = render_terminal(text, os.path.join(self.out, f"{base}-ttya.png"))
        if fb:
            try:
                png = self.screendump(f"{base}-fb")
                step["fb_png"] = png
                if self.ocr:
                    step["fb_ocr"] = self.fb_text(png)
            except (RuntimeError, QemuDied) as e:
                step["fb_error"] = str(e)
        self.steps.append(step)
        self.log(f"step {n}: {title}")
        self.write_report()
        return step

    def write_report(self, status=None):
        rows = []
        rec = getattr(self, "recordings", None) or {}
        for s in self.steps:
            imgs = "".join(
                f'<a href="{os.path.basename(s[k])}"><img src="{os.path.basename(s[k])}" alt="{k}"></a>'
                for k in ("ttya_png", "fb_png") if s.get(k))
            play = recording.step_links(rec, s["n"]) if rec else ""
            rows.append(f"<section><h2>{s['n']}. {html.escape(s['title'])} <small>{s['t']}s {play}</small></h2>"
                        f"<div class=imgs>{imgs}</div></section>")
        st = f"<p class=status>{html.escape(status)}</p>" if status else ""
        st += recording.report_html(self.out, rec) if rec else ""
        with open(os.path.join(self.out, "index.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html><meta charset=utf-8><title>sparc lab run</title><style>"
                    "body{font:14px system-ui;margin:16px;background:#fff;color:#111}"
                    ".imgs{display:flex;gap:8px;flex-wrap:wrap}img{max-width:600px;border:1px solid #ccc}"
                    ".status{font-weight:bold}code{white-space:pre-wrap}</style>"
                    f"<h1>sparc lab run</h1><p><code>{html.escape(shlex.join(self.args))}</code></p>{st}"
                    + "".join(rows))

    # --- recordings (recording.py) ---------------------------------------------------------------

    def mark(self, label):
        """A marker in the cast (a chapter in the player) and a cue in the framebuffer video."""
        self.cast.marker(label)
        if getattr(self, "fbrec", None):
            self.fbrec.mark(label)

    def record_fb(self, interval=1.0, max_width=1024):
        """Keep a framebuffer frame every `interval` seconds for fb.webm, from the display refresh
        (started at that interval when it isn't running: it is one screendump either way)."""
        self.fbrec = recording.FbRecorder(self.out, self.elapsed, interval, max_width)
        self.log(f"framebuffer video: a frame every {interval:g}s")
        self.refresh(interval)

    def finish_recordings(self, v):
        """Close the cast, write its viewing copy (serial.fast.cast) and encode the framebuffer video;
        returns what result.json lists as "recordings"."""
        self.cast.close()
        rec = {"cast": "serial.cast", "cast_bytes": self.cast.size, "cast_events": self.cast.events}
        if self.cast.truncated:
            rec["cast_truncated"] = True
        max_idle, speed = float(v.get("CAST_MAX_IDLE") or 1), float(v.get("CAST_SPEED") or 2)
        try:
            c = recording.compress_cast(os.path.join(self.out, "serial.cast"),
                                        os.path.join(self.out, "serial.fast.cast"), max_idle, speed)
            rec.update(cast_fast="serial.fast.cast", max_idle=max_idle, speed=speed, cast_seconds=c["seconds"],
                       fast_seconds=c["fast_seconds"], cast_markers=c["steps"])
        except Exception as e:
            rec["cast_error"] = f"{type(e).__name__}: {e}"
        rec["player"] = recording.copy_player(self.out)
        fb, self.fbrec = getattr(self, "fbrec", None), None
        if fb:
            try:
                rec["fb"] = fb.finish(os.path.join(self.out, "fb.webm"), fps=int(v.get("FB_VIDEO_FPS") or 10),
                                      speed=float(v.get("FB_VIDEO_SPEED") or 10))
            except Exception as e:
                rec["fb"] = {"error": f"{type(e).__name__}: {e}"}
            self.log("framebuffer video: " + (rec["fb"].get("error") or
                     f"{rec['fb']['video']}, {rec['fb']['seconds']}s, {rec['fb']['bytes'] >> 10} KiB"))
        self.recordings = rec
        return rec

    def wait_exit(self, timeout=120):
        """Wait for the guest to power the machine off; returns QEMU's exit code."""
        code = self.proc.wait(timeout)
        self.log(f"QEMU exited with {code}")
        return code

    # --- host CPU use ---------------------------------------------------------------------------

    def cpu_seconds(self):
        """CPU time QEMU has used so far (utime + stime from /proc/<pid>/stat), in seconds."""
        with open(f"/proc/{self.proc.pid}/stat", encoding="ascii") as f:
            fields = f.read().rsplit(")", 1)[1].split()  # the name in () may hold spaces
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")

    def cpu_use(self, seconds, below=None, above=None):
        """Host CPU use of QEMU over the next `seconds`, in percent of one core (all its threads).
        Fails when it isn't below `below` or above `above`. Only meaningful on an otherwise idle
        host."""
        c0, t0 = self.cpu_seconds(), time.time()
        time.sleep(seconds)
        self._check_alive()
        pct = 100 * (self.cpu_seconds() - c0) / (time.time() - t0)
        self.log(f"host CPU use over {seconds}s: {pct:.1f}% of a core")
        self.metrics["cpu_pct"] = round(pct, 1)
        if below is not None and pct >= float(below):
            raise AssertionError(f"host CPU use {pct:.1f}% over {seconds}s, expected below {below}%")
        if above is not None and pct <= float(above):
            raise AssertionError(f"host CPU use {pct:.1f}% over {seconds}s, expected above {above}%")
        return pct

    def status(self, sample=0.5):
        """Whether QEMU runs, its run state (QMP query-status: running, paused, ...) and its host CPU use
        over `sample` seconds, in percent of one core."""
        st = {"running": self.proc.poll() is None, "pid": self.proc.pid}
        if st["running"]:
            st["state"] = self.qmp.cmd("query-status").get("status")
            c0, t0 = self.cpu_seconds(), time.time()
            time.sleep(float(sample))
            st["cpu_pct"] = round(100 * (self.cpu_seconds() - c0) / (time.time() - t0), 1)
        return st

    def reset(self):
        """A hardware reset (QMP system_reset), like pressing the reset button."""
        self.qmp.cmd("system_reset")
        self.log("system_reset")

    def hmp(self, command):
        """Run a human monitor command (info registers, info mtree, sendkey stop-a, ...)."""
        return self.qmp.cmd("human-monitor-command", **{"command-line": command})

    def stop(self):
        try:
            self.qmp.cmd("quit")
        except Exception:
            pass
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def render_terminal(text, path, cols=80, rows=24):
    """Draw the terminal screen as an image, so serial steps sit next to framebuffer screenshots."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    except OSError:  # a node without fonts-dejavu-core: Pillow's own font (10.1+ scales it)
        font = ImageFont.load_default(14)
    cw, ch = 9, 18
    img = Image.new("RGB", (cols * cw + 16, rows * ch + 16), "#101010")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(text.split("\n")[:rows]):
        d.text((8, 8 + i * ch), line, font=font, fill="#d8d8d8")
    img.save(path)
    return path


# --- attach mode: a VM that Proxmox VE started --------------------------------------------------------

PVE_RUN = "/var/run/qemu-server"  # <vmid>.pid, <vmid>.qmp, <vmid>.serial<N> of every running VM


def qm(*args, check=True):
    r = subprocess.run(["qm", *map(str, args)], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"qm {' '.join(map(str, args))}: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def pve_config(vmid):
    """The VM's current config (`qm config`) as a dict."""
    return dict(line.split(": ", 1) for line in qm("config", vmid).splitlines() if ": " in line)


def pve_set_medium(vmid, drive, volume):
    """Put `volume` ("none": nothing) into the CD-ROM or floppy drive `drive` of a VM, running (PVE
    changes the medium live) or not."""
    qm("set", vmid, f"--{drive}", volume if drive.startswith("floppy") else f"{volume},media=cdrom")


def pve_serial(conf):
    """The serial port the console is on: the one `vga: serialN` names, else the first `serialN: socket`."""
    vga = conf.get("vga", "").split(",")[0]
    if vga.startswith("serial") and conf.get(vga) == "socket":
        return int(vga[6:])
    return next((n for n in range(4) if conf.get(f"serial{n}") == "socket"), None)


def pve_cdrom_as(drive):
    """`hd` when target 6 answers as a disk: a CD-ROM with cd_as_disk=1 and an image (qemu-server's
    sparc32-only option; without a medium it is a plain CD-ROM) or a read-only disk image there (the
    older workaround, the ISO copied into a VM disk); `cd` for a CD-ROM."""
    opts = drive.split(",")
    if "media=cdrom" not in opts:
        return "hd"
    return "hd" if "cd_as_disk=1" in opts and opts[0] != "none" else "cd"


def pve_vars(vmid, conf=None):
    """The scenario variables that the VM's PVE config decides, so they needn't be repeated with --var:
    ARCH, MEM, SERIAL, CONSOLE (serial without a display, else fb) and, for sparc32, what _sparc32.py's
    helpers read (MACHINE, BIOS, VGA, BOOT, CDROM_AS, REFRESH). The VM's hardware itself comes from its
    config; qemu_args() isn't used. `conf`: the config if the caller has it already."""
    c = pve_config(vmid) if conf is None else conf
    vga = c.get("vga", "").split(",")[0]
    serial = pve_serial(c)
    nofb = vga == "none" or vga.startswith("serial")
    v = {"PVE_VMID": str(vmid), "ARCH": c.get("arch", "x86_64"), "MEM": c.get("memory", ""),
         "SERIAL": "" if serial is None else str(serial), "CONSOLE": "serial" if nofb else "fb"}
    if v["ARCH"] == "sparc":
        # qemu-server passes no -prom-env: OpenBIOS puts its console on ttya only without a framebuffer
        v.update(MACHINE=c.get("machine", "SS-5"), BIOS=c.get("bios", "openbios-sparc32"), MEM=c.get("memory", "256"),
                 VGA="none" if nofb else vga or "cg3",
                 # and no boot device: sun4m boots target 3 (the disk), and the PROM prompt boots the CD
                 BOOT="c",
                 CDROM_AS=pve_cdrom_as(c.get("scsi6", "media=cdrom")),
                 REFRESH="0" if nofb else "0.5")
    return v


def unix_clients(path):
    """How many clients a listening Unix socket has now (its accepted connections in /proc/net/unix)."""
    with open("/proc/net/unix", encoding="ascii") as f:
        return sum(1 for line in f if line.split()[5:6] == ["03"] and line.rstrip().endswith(" " + path))


class PveQmp:
    """QMP on the VM's <vmid>.qmp socket, one connection per command.

    QEMU serves one client at a time there, and PVE's own tools (qm, pvestatd, the API) connect for
    every command and give up after a few seconds: a client that stays connected makes `qm sendkey`
    fail ("unable to connect to VM qmp socket - timeout") and drops the QEMU version from `qm status
    --verbose`. So this connects, runs one command and disconnects, as PVE does, and waits its turn
    while another client has the socket."""

    def __init__(self, path, timeout=30):
        self.path = path
        self.timeout = timeout
        self.lock = threading.Lock()

    def cmd(self, name, **args):
        end = time.time() + self.timeout
        with self.lock:
            while True:
                try:
                    with socket.socket(socket.AF_UNIX) as s:
                        s.settimeout(max(1.0, end - time.time()))
                        s.connect(self.path)
                        f = s.makefile("rwb")
                        for req in (None, {"execute": "qmp_capabilities"}, {"execute": name, "arguments": args}):
                            if req:
                                f.write(json.dumps(req).encode() + b"\n")
                                f.flush()
                            while True:  # the greeting or the reply, skipping events
                                line = f.readline()
                                if not line:
                                    raise QemuDied(f"{self.path}: QMP connection closed")
                                reply = json.loads(line)
                                if "event" not in reply:
                                    break
                        # Wait for QEMU to close its end: a client that connects before QEMU has
                        # handled the last one's disconnect gets the greeting but no replies.
                        try:
                            s.shutdown(socket.SHUT_WR)
                            while f.readline():
                                pass
                        except OSError:
                            pass
                    break
                except (FileNotFoundError, ConnectionRefusedError) as e:
                    raise QemuDied(f"{self.path}: {e}")
                except (BlockingIOError, socket.timeout):  # another client has it
                    if time.time() > end:
                        raise RuntimeError(f"QMP {name}: {self.path} busy for {self.timeout}s")
                    time.sleep(0.2)
        if "error" in reply:
            raise RuntimeError(f"QMP {name}: {reply['error'].get('desc')}")
        return reply.get("return")


class PveProcess:
    """What Machine uses of its QEMU process (pid, poll, wait, kill, returncode), for the QEMU that PVE
    started for a VM: the pid in <vmid>.pid. PVE runs QEMU with -no-shutdown and qmeventd ends it when
    the guest powers off, so a power-off shows as the process ending. Its exit code isn't visible and
    counts as 0."""

    def __init__(self, vmid):
        self.vmid = vmid
        with open(f"{PVE_RUN}/{vmid}.pid", encoding="ascii") as f:
            self.pid = int(f.read().strip())
        self.returncode = None

    def poll(self):
        if self.returncode is None:
            try:
                with open(f"/proc/{self.pid}/stat", encoding="ascii") as f:
                    gone = f.read().rsplit(")", 1)[1].split()[0] == "Z"
            except FileNotFoundError:
                gone = True
            if gone:
                self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        end = None if timeout is None else time.time() + timeout
        while self.poll() is None:
            if end and time.time() > end:
                raise subprocess.TimeoutExpired(f"VM {self.vmid}", timeout)
            time.sleep(0.5)
        return self.returncode

    def kill(self):
        qm("stop", self.vmid, check=False)


class PveMachine(Machine):
    """A Machine for a VM that Proxmox VE runs, by VMID, on the PVE node (where `qm` and
    /var/run/qemu-server are): serial I/O on <vmid>.serial<N> (the VM needs `serialN: socket`),
    monitor commands, screendump and send-key through PveQmp on <vmid>.qmp.

    A stopped VM is started with `qm start` and stopped again by stop() (unless keep); a running one is
    attached to and left running. The lab owns the serial console while it runs: QEMU serves one
    client per serial socket, so `qm terminal` or the web console can't share it."""

    def __init__(self, out, vmid, cols=80, rows=24, ocr=True, serial=None, keep=False):
        if not shutil.which("qm"):
            raise SystemExit("--pve: run lab.py on the PVE node, where qm and /var/run/qemu-server are")
        self.out, self.vmid, self.keep = out, str(vmid), keep
        os.makedirs(out, exist_ok=True)
        conf = pve_config(vmid)
        serial = pve_serial(conf) if serial in (None, "") else int(serial)
        self.serial_path = None if serial is None else f"{PVE_RUN}/{vmid}.serial{serial}"
        self.qmp_path = f"{PVE_RUN}/{vmid}.qmp"
        # the terminal and the step log, as in Machine
        self.screen, self.stream = new_terminal(cols, rows)
        self.text, self.pos, self.text_base = "", 0, 0
        self.cond = threading.Condition()
        self.steps, self.metrics = [], {}
        self.ocr = ocr
        self.t0 = time.time()
        self.raw = open(os.path.join(out, "serial.raw"), "wb")
        self.cast = recording.CastWriter(os.path.join(out, "serial.cast"), cols, rows, self.t0, init="\x1b)0")
        self.qmp = PveQmp(self.qmp_path)
        self.ser = None
        if self.serial_path and os.path.exists(self.serial_path) and unix_clients(self.serial_path):
            raise SystemExit(f"{self.serial_path} already has a client (qm terminal, the web console?): "
                               "close it, the lab needs the serial console to itself")
        self.started = "status: running" not in qm("status", vmid)
        self._start(conf, "qm-start.log")
        console = f"console on {self.serial_path}" if self.ser else "no serial socket (framebuffer only)"
        self.log(f"{'started' if self.started else 'attached to running'} VM {vmid} (pid {self.proc.pid}), {console}")

    def _start(self, conf, log_name):
        """`qm start` the VM if self.started (else attach to the running one), connect the serial
        console and start reading it; the QEMU process and its command line become self.proc and
        self.args."""
        if self.started:
            # Connect while `qm start` runs, so the console output from the first instruction on is seen.
            start = subprocess.Popen(["qm", "start", self.vmid], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True)
            while self.serial_path and not self.ser and start.poll() is None:
                self.ser = self._try_connect(self.serial_path)
                time.sleep(0.05)
            log = start.communicate()[0]
            with open(os.path.join(self.out, log_name), "w", encoding="utf-8") as f:
                f.write(log)
            if start.returncode:
                raise SystemExit(f"qm start {self.vmid} failed: {log.strip()[-2000:]}")
        if self.serial_path and not self.ser:
            self.ser = self._try_connect(self.serial_path)
            if not self.ser:
                raise SystemExit(f"can't connect to {self.serial_path}")
        if self.ser:
            threading.Thread(target=self._reader, args=(self.ser,), daemon=True).start()
        self.proc = PveProcess(self.vmid)
        with open(f"/proc/{self.proc.pid}/cmdline", "rb") as f:
            self.args = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        with open(os.path.join(self.out, "qemu.cmd"), "a" if log_name != "qm-start.log" else "w", encoding="utf-8") as f:
            f.write(shlex.join(self.args) + "\n")
        if self.started and conf.get("freeze") == "1":
            self.qmp.cmd("cont")  # `freeze: 1` holds the CPU until now

    def power_cycle(self):
        """Power the VM off and on again through PVE (`qm stop`, `qm start`), as a new QEMU process:
        for a guest whose reboot doesn't come back (sun4u: OpenBIOS's client-interface `boot` returns,
        submodules/SPARC.md) and where a firmware reset isn't enough (OpenBIOS keeps the RAM's old
        contents). The serial output goes on in the same terminal, log and recordings; only a VM that
        the lab started (not one it attached to) is cycled."""
        if not self.started:
            raise RuntimeError(f"VM {self.vmid} was running before the lab attached: not power-cycling it")
        out = qm("stop", self.vmid, check=False).strip()
        self.log(f"power cycle: qm stop {self.vmid}" + (f": {out}" if out else ""))
        self.proc.wait(120)
        if self.ser:
            self.ser.close()  # the reader thread ends on it
            self.ser = None
        self.metrics["power_cycles"] = n = self.metrics.get("power_cycles", 0) + 1
        with self.cond:
            self.mark(f"power cycle {n}")
        self._start(pve_config(self.vmid), f"qm-start-{n + 1}.log")
        self.log(f"power cycle: started VM {self.vmid} again (pid {self.proc.pid})")

    @staticmethod
    def _try_connect(path):
        s = socket.socket(socket.AF_UNIX)
        try:
            s.connect(path)
            return s
        except OSError:
            s.close()
            return None

    def _check_alive(self):
        if self.proc.poll() is not None:
            status = qm("status", self.vmid, check=False).strip()
            raise QemuDied(f"VM {self.vmid} is no longer running ({status}); see `journalctl` and the task log")

    def send(self, text, delay=0.05):
        if not self.ser:
            raise RuntimeError(f"VM {self.vmid} has no serial console: give it `serial0: socket`")
        super().send(text, delay)

    def key(self, *names):
        if not self.ser:
            raise RuntimeError(f"VM {self.vmid} has no serial console: give it `serial0: socket`")
        super().key(*names)

    def change_medium(self, drive, volume):
        """Put another medium into a CD-ROM or floppy drive of the running VM through PVE (`qm set`,
        which changes it live), e.g. ("scsi6", "local:iso/cd2.iso") or ("floppy0",
        "local:floppy/disk2.img"); "none" empties the drive. The VM config follows, so PVE and the
        guest agree on what is inserted."""
        pve_set_medium(self.vmid, drive, volume)
        self.log(f"{drive}: {volume}")

    def trace(self, events):
        """Turn on QEMU trace events (comma separated) in the running VM, logged to <out>/trace.log."""
        self.hmp(f"logfile {os.path.join(self.out, 'trace.log')}")
        for ev in filter(None, events.split(",")):
            self.hmp(f"trace-event {ev} on")
        self.log(f"tracing {events}")

    def stop(self):
        """Stop the VM if the lab started it (`qm stop`), else leave it running; either way detach."""
        if self.started and not self.keep and self.proc.poll() is None:
            out = qm("stop", self.vmid, check=False).strip()
            self.log(f"qm stop {self.vmid}" + (f": {out}" if out else ""))
        elif self.proc.poll() is None:
            self.log(f"VM {self.vmid} left running")
        if self.ser:
            self.ser.close()


# --- command line -----------------------------------------------------------------------------------

def load_scenario(path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))  # scenarios share helpers (_sparc32.py)
    spec = importlib.util.spec_from_file_location("scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_vars(items):
    out = {}
    for item in items or []:
        k, _, v = item.partition("=")
        out[k] = v
    return out


def cmd_run(a):
    return run_scenario(a.scenario, a.out, parse_vars(a.var), pve=a.pve, no_ocr=a.no_ocr,
                        keep_running=a.keep_running)["code"]


# Variables whose values never go into result.json: passwords and (later) licence keys. Typed values
# don't reach the recordings either as long as the guest doesn't echo them (password prompts don't).
SECRET_VARS = re.compile(r"(PASSWORD|_KEY|SECRET)$")


def masked(v):
    """The variables with the values of SECRET_VARS replaced, for result.json."""
    return {k: ("***" if SECRET_VARS.search(k) and val else val) for k, val in v.items()}


def run_scenario(scenario, out, variables=None, pve=None, no_ocr=False, keep_running=False, on_machine=None):
    """Run one scenario against a QEMU of its own or (`pve`: a VMID) a PVE VM, with the evidence in
    `out`; returns what it writes to result.json (code 0 passed, 1 timed out, 2 QEMU died, 3 error).
    `on_machine(m)` is called with the Machine before the scenario starts (lab.py install uses it to
    stop a stalled install from outside)."""
    sc = load_scenario(scenario)
    v = {**getattr(sc, "DEFAULTS", {}), **(pve_vars(pve) if pve else {}), **(variables or {})}
    os.makedirs(out, exist_ok=True)
    a = argparse.Namespace(out=out, pve=pve, no_ocr=no_ocr, keep_running=keep_running)
    m = attach(a, v) if pve else Machine(out, sc.qemu_args(v, out), ocr=not no_ocr)
    # SERIAL_7BIT=1: 7-bit console (SunOS 4.1.2's getty sends even parity in bit 7); serial.raw keeps it
    m.seven_bit = v.get("SERIAL_7BIT") == "1"
    if on_machine:
        on_machine(m)
    m.refresh(float(v.get("REFRESH") or 0))
    record_fb(m, a, v)
    status, code = "passed", 0
    try:
        sc.run(m, v)
    except QemuDied as e:
        status, code = f"QEMU died: {e}", 2
    except Timeout as e:
        status, code = f"timed out: {e}", 1
    except Exception as e:  # keep the evidence for anything else too
        status, code = f"error: {type(e).__name__}: {e}", 3
    if code:
        try:
            m.snap(f"FAILED: {status.splitlines()[0]}")
        except Exception:
            pass
    m.log(f"result: {status}")
    m.write_report(status)
    if not keep_running or pve:  # attached: stop() leaves the VM running with --keep-running
        m.stop()
    else:
        m.log("keeping QEMU running (Ctrl-C to stop)")
        try:
            m.proc.wait()
        except KeyboardInterrupt:
            m.stop()
    elapsed = round(m.elapsed(), 1)
    rec = m.finish_recordings(v)
    m.write_report(status)
    result = {"status": status, "code": code, "elapsed": elapsed, "vars": masked(v),
              "metrics": m.metrics, "recordings": rec}
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def has_framebuffer(args):
    """Whether a QEMU command line has a display device (sparc32: -vga cg3/tcx, its default)."""
    vga = [args[i + 1] for i, x in enumerate(args[:-1]) if x == "-vga"]
    return "-nographic" not in args and (not vga or vga[-1] != "none")


def record_fb(m, a, v):
    """The framebuffer video, for a machine with a display: a frame every FB_VIDEO seconds (1; 0 = no
    video), scaled to at most FB_VIDEO_WIDTH (1024) pixels wide."""
    interval = float(v.get("FB_VIDEO", "1") or 0)
    if interval and (v.get("CONSOLE") == "fb" if a.pve else has_framebuffer(m.args)):
        m.record_fb(interval, int(v.get("FB_VIDEO_WIDTH") or 1024))


def attach(a, v):
    """--pve: a PveMachine for the VM, with TRACE turned on through the monitor (no -trace to add)."""
    m = PveMachine(a.out, a.pve, ocr=not a.no_ocr, serial=v.get("SERIAL"), keep=getattr(a, "keep_running", False))
    if v.get("TRACE"):
        m.trace(v["TRACE"])
    return m


def serve_one(m, conn):
    with conn:
        req = json.loads(conn.makefile().readline())
        try:
            res = {"ok": True, "result": getattr(m, req["op"])(*req.get("args", []), **req.get("kw", {}))}
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        conn.sendall((json.dumps(res, default=str) + "\n").encode())


def cmd_serve(a):
    """Start QEMU and take commands on <out>/ctl.sock (one JSON request per connection)."""
    os.makedirs(a.out, exist_ok=True)
    v = {**(pve_vars(a.pve) if a.pve else {}), **parse_vars(a.var)}
    if a.scenario:
        sc = load_scenario(a.scenario)
        v = {**getattr(sc, "DEFAULTS", {}), **v}
        if not a.pve:
            a.qemu_args = sc.qemu_args(v, a.out)
    m = attach(a, v) if a.pve else Machine(a.out, a.qemu_args, ocr=not a.no_ocr)
    m.refresh(float(v.get("REFRESH") or 0))
    record_fb(m, a, v)
    ctl = os.path.join(a.out, "ctl.sock")
    if os.path.exists(ctl):
        os.unlink(ctl)
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(ctl)
    srv.listen(8)
    m.log(f"serving on {ctl}")
    while m.proc.poll() is None:
        srv.settimeout(1)
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        # One thread per request, so a long expect() doesn't hold up screendumps.
        threading.Thread(target=serve_one, args=(m, conn), daemon=True).start()
    m.log(f"QEMU exited with {m.proc.returncode}")
    m.finish_recordings(v)
    m.write_report()
    return 0


def cmd_cast(a):
    """lab.py cast <run dir or .cast>: check a cast and write its viewing copy with the pauses cut."""
    src = os.path.join(a.run, "serial.cast") if os.path.isdir(a.run) else a.run
    problems = recording.check_cast(src)
    for p in problems[:20]:
        print(f"{src}: {p}", file=sys.stderr)
    dst = a.output or os.path.join(os.path.dirname(src), "serial.fast.cast")
    c = recording.compress_cast(src, dst, a.max_idle, a.speed)
    print(f"{src}: {c['seconds']:.0f}s, {os.path.getsize(src) >> 10} KiB -> {dst}: {c['fast_seconds']:.0f}s, "
          f"{os.path.getsize(dst) >> 10} KiB, {len(c['steps'])} step markers")
    differ = []
    if a.check:
        compared, differ = recording.check_steps(os.path.dirname(src) or ".", os.path.basename(src))
        print(f"replayed: {compared - len(differ)}/{compared} step screens match NNN-ttya.txt"
              + "".join(f"\n  differs: {d}" for d in differ))
    return 1 if problems or differ else 0


def cmd_ctl(a):
    """lab.py ctl --out DIR <method> [args...]: call a Machine method in a running `serve`."""
    def arg(x):  # numbers, booleans and JSON values as such, anything else as a plain string
        try:
            return json.loads(x)
        except ValueError:
            return x

    args = [arg(x) for x in a.args]
    s = socket.socket(socket.AF_UNIX)
    path = os.path.join(a.out, "ctl.sock")
    for _ in range(120):  # serve may still be preparing the disk
        if os.path.exists(path):
            break
        time.sleep(1)
    s.connect(path)
    s.sendall((json.dumps({"op": a.op, "args": args}) + "\n").encode())
    res = json.loads(s.makefile().readline())
    if not res["ok"]:
        print(res["error"], file=sys.stderr)
        return 1
    r = res["result"]
    if r is not None:
        print(r if isinstance(r, str) else json.dumps(r, indent=1))
    return 0


def main():
    # LAB_PROG: the name the wsh-lab package's wrapper runs it as (/usr/bin/wsh-lab), for the help
    p = argparse.ArgumentParser(prog=os.environ.get("LAB_PROG") or None, description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("scenario")
    r.add_argument("--out", required=True)
    r.add_argument("--var", action="append", help="KEY=VALUE for the scenario")
    r.add_argument("--no-ocr", action="store_true")
    r.add_argument("--keep-running", action="store_true")
    r.add_argument("--pve", metavar="VMID", help="drive this PVE VM (on the PVE node) instead of starting QEMU")
    s = sub.add_parser("serve")
    s.add_argument("--pve", metavar="VMID", help="drive this PVE VM (on the PVE node) instead of starting QEMU")
    s.add_argument("--out", required=True)
    s.add_argument("--no-ocr", action="store_true")
    s.add_argument("--scenario", help="take the QEMU command from this scenario's qemu_args()")
    s.add_argument("--var", action="append")
    s.add_argument("qemu_args", nargs=argparse.REMAINDER)
    c = sub.add_parser("ctl")
    c.add_argument("--out", required=True)
    c.add_argument("op")
    c.add_argument("args", nargs="*")
    k = sub.add_parser("cast", help="check a run's serial.cast and write a copy with the pauses cut")
    k.add_argument("run", help="the run directory (its serial.cast) or a .cast file")
    k.add_argument("--max-idle", type=float, default=1.0, help="longest pause kept, seconds (1)")
    k.add_argument("--speed", type=float, default=2.0, help="then play this many times faster (2)")
    k.add_argument("--output", help="where to write the copy (serial.fast.cast next to the cast)")
    k.add_argument("--check", action="store_true",
                   help="replay the cast and compare the screen at each step with the lab's NNN-ttya.txt")
    import install  # install targets (install.py, targets.py): `install`, `targets`, `media`

    install.add_commands(sub)
    import mirror  # a mirror storage of symlinks (mirror.py): `mirror link|sync|list|init|plan|apply|...`

    mirror.add_commands(sub)
    a = p.parse_args()
    if getattr(a, "qemu_args", None) and a.qemu_args[0] == "--":
        a.qemu_args = a.qemu_args[1:]
    cmds = {"run": cmd_run, "serve": cmd_serve, "ctl": cmd_ctl, "cast": cmd_cast, **install.COMMANDS,
            **mirror.COMMANDS}
    return cmds[a.cmd](a)


if __name__ == "__main__":
    sys.modules["lab"] = sys.modules["__main__"]  # scenarios import QemuDied etc. from this module
    sys.exit(main())
