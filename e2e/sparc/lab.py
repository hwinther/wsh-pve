#!/usr/bin/env python3
"""Drive a sparc guest under QEMU the way a person would: watch the serial console and the
framebuffer, type on either, and record every step with screenshots.

The guest's serial port goes through a VT100 emulator (pyte), so a full-screen installer on ttya can be
matched and captured as text. The framebuffer (cg3/tcx) is captured with QMP `screendump` and can be
matched through OCR (tesseract); keys reach the guest's Sun keyboard through QMP `send-key`.

Run a scenario:   lab.py run scenarios/solaris26-serial-install.py --out /work/run1 [--var KEY=VALUE ...]
Interactive:      lab.py serve --out /work/s1 -- <qemu args>     (then `lab.py ctl ...` from another shell)
"""
import argparse
import html
import importlib.util
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time

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


class Machine:
    """One QEMU process plus its serial console, QMP monitor and a step log with screenshots."""

    def __init__(self, out, qemu_args, cols=80, rows=24, ocr=True):
        import pyte

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
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        # 8-bit, not UTF-8 (pyte ignores charset switches in UTF-8 mode), and G1 = DEC line drawing as
        # on a VT100 after Solaris's terminfo init: the installer draws its boxes with SO/SI, which
        # would otherwise show as letters ("qqqq").
        self.stream.select_other_charset("@")
        self.stream.feed(b"\x1b)0")
        self.text = ""  # serial output, escape sequences removed, from which expect() consumes
        self.pos = 0
        self.cond = threading.Condition()
        self.steps = []
        self.ocr = ocr
        self.t0 = time.time()
        self.raw = open(os.path.join(out, "serial.raw"), "wb")
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

    def _reader(self):
        while True:
            try:
                data = self.ser.recv(4096)
            except OSError:
                data = b""
            with self.cond:
                if not data:
                    self.cond.notify_all()
                    return
                self.raw.write(data)
                self.raw.flush()
                self.stream.feed(data)
                self.text += ANSI.sub(b"", data).replace(b"\r", b"").decode("latin-1")
                self.cond.notify_all()

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
                except Exception:
                    pass
                time.sleep(interval)

        threading.Thread(target=loop, daemon=True).start()
        self.log(f"display refresh every {interval}s")

    def fb_text(self, png):
        if not self.ocr:
            return ""
        r = subprocess.run(["tesseract", png, "-", "--psm", "6"], capture_output=True, text=True)
        return r.stdout

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
            if ch.isalpha():
                keys = ["shift", ch.lower()] if ch.isupper() else [ch]
            elif ch.isdigit():
                keys = [ch]
            elif ch in SHIFTED:
                keys = ["shift", SHIFTED[ch]]
            else:
                keys = [QCODES[ch]]
            self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in keys], **{"hold-time": hold})
            time.sleep(delay)

    def fb_key(self, *qcodes):
        """Press one key or a chord, e.g. fb_key("stop", "a") for Stop-A."""
        self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in qcodes], **{"hold-time": 100})

    # --- the step log ---------------------------------------------------------------------------

    def snap(self, title, fb=True, term=True):
        """Record a step: the terminal screen (text + PNG) and the framebuffer screenshot."""
        n = len(self.steps) + 1
        base = f"{n:03d}"
        step = {"n": n, "t": round(self.elapsed(), 1), "title": title}
        if term:
            text = self.screen_text()
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
        for s in self.steps:
            imgs = "".join(
                f'<a href="{os.path.basename(s[k])}"><img src="{os.path.basename(s[k])}" alt="{k}"></a>'
                for k in ("ttya_png", "fb_png") if s.get(k))
            rows.append(f"<section><h2>{s['n']}. {html.escape(s['title'])} <small>{s['t']}s</small></h2>"
                        f"<div class=imgs>{imgs}</div></section>")
        st = f"<p class=status>{html.escape(status)}</p>" if status else ""
        with open(os.path.join(self.out, "index.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html><meta charset=utf-8><title>sparc lab run</title><style>"
                    "body{font:14px system-ui;margin:16px;background:#fff;color:#111}"
                    ".imgs{display:flex;gap:8px;flex-wrap:wrap}img{max-width:600px;border:1px solid #ccc}"
                    ".status{font-weight:bold}code{white-space:pre-wrap}</style>"
                    f"<h1>sparc lab run</h1><p><code>{html.escape(shlex.join(self.args))}</code></p>{st}"
                    + "".join(rows))

    def wait_exit(self, timeout=120):
        """Wait for the guest to power the machine off; returns QEMU's exit code."""
        code = self.proc.wait(timeout)
        self.log(f"QEMU exited with {code}")
        return code

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

    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    cw, ch = 9, 18
    img = Image.new("RGB", (cols * cw + 16, rows * ch + 16), "#101010")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(text.split("\n")[:rows]):
        d.text((8, 8 + i * ch), line, font=font, fill="#d8d8d8")
    img.save(path)
    return path


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
    sc = load_scenario(a.scenario)
    v = {**getattr(sc, "DEFAULTS", {}), **parse_vars(a.var)}
    os.makedirs(a.out, exist_ok=True)
    m = Machine(a.out, sc.qemu_args(v, a.out), ocr=not a.no_ocr)
    m.refresh(float(v.get("REFRESH") or 0))
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
    if not a.keep_running:
        m.stop()
    else:
        m.log("keeping QEMU running (Ctrl-C to stop)")
        try:
            m.proc.wait()
        except KeyboardInterrupt:
            m.stop()
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"status": status, "code": code, "elapsed": round(m.elapsed(), 1), "vars": v}, f, indent=2)
    return code


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
    v = parse_vars(a.var)
    if a.scenario:
        sc = load_scenario(a.scenario)
        v = {**getattr(sc, "DEFAULTS", {}), **v}
        a.qemu_args = sc.qemu_args(v, a.out)
    m = Machine(a.out, a.qemu_args, ocr=not a.no_ocr)
    m.refresh(float(v.get("REFRESH") or 0))
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
    return 0


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
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("scenario")
    r.add_argument("--out", required=True)
    r.add_argument("--var", action="append", help="KEY=VALUE for the scenario")
    r.add_argument("--no-ocr", action="store_true")
    r.add_argument("--keep-running", action="store_true")
    s = sub.add_parser("serve")
    s.add_argument("--out", required=True)
    s.add_argument("--no-ocr", action="store_true")
    s.add_argument("--scenario", help="take the QEMU command from this scenario's qemu_args()")
    s.add_argument("--var", action="append")
    s.add_argument("qemu_args", nargs=argparse.REMAINDER)
    c = sub.add_parser("ctl")
    c.add_argument("--out", required=True)
    c.add_argument("op")
    c.add_argument("args", nargs="*")
    a = p.parse_args()
    if getattr(a, "qemu_args", None) and a.qemu_args[0] == "--":
        a.qemu_args = a.qemu_args[1:]
    return {"run": cmd_run, "serve": cmd_serve, "ctl": cmd_ctl}[a.cmd](a)


if __name__ == "__main__":
    sys.modules["lab"] = sys.modules["__main__"]  # scenarios import QemuDied etc. from this module
    sys.exit(main())
