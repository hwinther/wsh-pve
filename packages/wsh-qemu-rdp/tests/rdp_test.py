#!/usr/bin/env python3
"""qemu-rdp end to end against a wisp guest (packages/wsh-qemu-rdp/test.sh runs it).

QEMU runs a wisp framebuffer kernel (e2e/wisp, `kernel-fb-<arch>`) with its D-Bus display and the
audio driver dbus; qemu-rdp (wsh-qemu-rdp-unit run) serves it; FreeRDP (xfreerdp3) on an Xvfb
server connects with NLA, plays rdpsnd into a PulseAudio sink (parec records it) and is driven with
xdotool. The checks, each printed as a PASS/FAIL line and listed in OUTDIR/summary.txt:

  auth      the wrong password is refused, the right one accepted (/auth-only)
  picture   wisp's `fbtest` colour bars in FreeRDP's window match QEMU's screendump of the console
  resize    the client's window follows the guest's mode change (BIOS text mode -> framebuffer)
  keyboard  keys typed into FreeRDP's window reach the guest (`keytest`: evdev codes 30, 48, 1)
  mouse     buttons and motion reach the guest (`mousetest`; motion is relative on a PS/2 or Sun
            mouse, which needs patch 0004)
  sound     `soundtest 440 MS` arrives as rdpsnd: a 440 Hz tone of about MS milliseconds

Also measured (no pass/fail): keyboard latency (xdotool to the guest's serial line), and how long
the colour bars took to reach the client after the guest drew them.

usage: rdp_test.py --arch x86_64|sparc32 --serial SOCK --qmp SOCK --port N --user U --password P
                   --outdir DIR [--display :N] [--sound-ms MS] [--skip CHECK,...]
"""

import argparse
import math
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import json

RESULTS = []


def log(msg):
    print(msg, flush=True)


def result(name, ok, detail):
    RESULTS.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


class Serial:
    """The guest's serial console (a QEMU unix socket), read in the background."""

    def __init__(self, path, logpath):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(path)
        self.buf = b""
        self.lock = threading.Lock()
        self.logfile = open(logpath, "wb")
        self.prompts = 0  # prompts answered so far
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            try:
                data = self.sock.recv(4096)
            except OSError:
                return
            if not data:
                return
            with self.lock:
                self.buf += data
            self.logfile.write(data)
            self.logfile.flush()

    def text(self, since=0):
        with self.lock:
            data = self.buf[since:]
        return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", data.decode(errors="replace"))

    def mark(self):
        with self.lock:
            return len(self.buf)

    def send(self, line):
        self.sock.sendall(line.encode() + b"\r")

    def expect(self, pattern, timeout, since=0):
        deadline = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < deadline:
            m = rx.search(self.text(since))
            if m:
                return m
            time.sleep(0.05)
        return None

    def command(self, prompt, cmd, done, timeout):
        """Type cmd at the next shell prompt; the match of done in what follows, or None."""
        deadline = time.time() + timeout
        rx = re.compile(prompt)
        while len(rx.findall(self.text())) <= self.prompts:
            if time.time() > deadline:
                return None
            time.sleep(0.05)
        self.prompts = len(rx.findall(self.text()))
        since = self.mark()
        self.send(cmd)
        return self.expect(done, timeout, since)


def qmp(path, cmd, **arguments):
    """One QMP command on the QEMU monitor socket at path; its return value."""
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(30)
    s.connect(path)
    f = s.makefile("rwb")
    json.loads(f.readline())
    reply = None
    for execute, args in (("qmp_capabilities", {}), (cmd, arguments)):
        f.write(json.dumps({"execute": execute, "arguments": args}).encode() + b"\n")
        f.flush()
        while True:
            reply = json.loads(f.readline())
            if "return" in reply or "error" in reply:
                break
        if "error" in reply:
            raise RuntimeError(f"{execute}: {reply['error']}")
    s.close()
    return reply["return"]


def read_ppm(path):
    data = open(path, "rb").read()
    fields = []
    pos = 0
    while len(fields) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[pos:end])
        pos = end
    if fields[0] != b"P6" or fields[3] != b"255":
        raise ValueError(f"{path}: not an 8-bit P6 PPM")
    w, h = int(fields[1]), int(fields[2])
    return w, h, data[pos + 1:pos + 1 + w * h * 3]


def compare(a, b, w, h):
    """(mean absolute difference per channel, share of pixels off by more than 32) of two RGB images."""
    total = 0
    bad = 0
    step = 4  # every 4th pixel of every 4th row: plenty for colour bars
    count = 0
    for y in range(0, h, step):
        row = y * w * 3
        for x in range(0, w, step):
            o = row + x * 3
            d = max(abs(a[o] - b[o]), abs(a[o + 1] - b[o + 1]), abs(a[o + 2] - b[o + 2]))
            total += abs(a[o] - b[o]) + abs(a[o + 1] - b[o + 1]) + abs(a[o + 2] - b[o + 2])
            bad += d > 32
            count += 1
    return total / (count * 3), bad / count


def x_screenshot(display, w, h, outfile):
    """The top left w x h of the X screen (FreeRDP's window sits at 0,0 without a window manager)."""
    subprocess.run(["import", "-display", display, "-window", "root", "-crop", f"{w}x{h}+0+0",
                    "+repage", "-depth", "8", f"ppm:{outfile}"], check=True, capture_output=True)
    return read_ppm(outfile)


def xdotool(display, *args, check=True):
    return subprocess.run(["xdotool", *args], env={**os.environ, "DISPLAY": display},
                          capture_output=True, text=True, check=check)


def freerdp_window(display, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = xdotool(display, "search", "--onlyvisible", "--name", "FreeRDP", check=False).stdout.split()
        if out:
            return out[0]
        time.sleep(0.2)
    return None


def window_size(display, win):
    out = xdotool(display, "getwindowgeometry", "--shell", win).stdout
    vals = dict(line.split("=", 1) for line in out.split() if "=" in line)
    return int(vals["WIDTH"]), int(vals["HEIGHT"])


def read_wav(path):
    """(rate, channels, int16 samples of channel 0) of a WAV file, read to its end whatever its
    header's sizes say (the ALSA file plugin writes them when it closes)."""
    data = open(path, "rb").read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAV file")
    pos = 12
    rate = channels = bits = None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", data[pos + 8:pos + 24])
        if cid == b"data":
            pcm = data[pos + 8:]
            break
        pos += 8 + size + (size & 1)
    else:
        raise ValueError(f"{path}: no data chunk")
    if bits != 16:
        raise ValueError(f"{path}: {bits}-bit samples, expected 16")
    frame = 2 * channels
    n = len(pcm) // frame
    samples = struct.unpack(f"<{n * channels}h", pcm[:n * frame])[0::channels]
    return rate, channels, samples


def tone(samples, rate):
    """(seconds of sound, its frequency, peak) of the loud part. The frequency counts rising edges
    through a quarter of the peak (hysteresis): a lossy codec (Opus) rings at a square wave's
    edges, which plain zero crossings would count too."""
    window = max(1, rate // 100)
    loud = []
    for i in range(0, len(samples) - window, window):
        chunk = samples[i:i + window]
        if math.sqrt(sum(s * s for s in chunk) / window) > 1000:
            loud.append(i)
    if not loud:
        return 0.0, 0.0, max((abs(s) for s in samples), default=0)
    first, last = loud[0], loud[-1] + window
    part = samples[first:last]
    peak = max(abs(s) for s in part)
    level = peak // 4
    edges = 0
    state = 0
    for s in part:
        if state <= 0 and s > level:
            state = 1
            edges += 1
        elif state >= 0 and s < -level:
            state = -1
    seconds = len(loud) * window / rate
    return seconds, edges / ((last - first) / rate), peak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--qmp", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--display", default=":99")
    ap.add_argument("--sound-ms", type=int, default=2000)
    ap.add_argument("--skip", default="")
    ap.add_argument("--boot-timeout", type=float, default=300)
    ap.add_argument("--sink", default="rdp", help="the PulseAudio sink FreeRDP plays into")
    ap.add_argument("--input-trace", help="QEMU's trace log with input_event_* (for a guest without mousetest)")
    ap.add_argument("--start", choices=("cont", "reset", "none"), default="cont",
                    help="how the guest starts once the client is attached: QMP cont (QEMU started"
                    " with -S), system_reset (a VM already running), or not at all")
    args = ap.parse_args()
    skip = set(filter(None, args.skip.split(",")))
    out = args.outdir
    prompt = r"wisp:\S+> "
    target = f"127.0.0.1:{args.port}"
    common = [f"/v:{target}", f"/u:{args.user}", "/cert:ignore", "/log-level:WARN"]

    # auth: /auth-only does TLS and NLA (CredSSP) and stops
    if "auth" not in skip:
        bad = subprocess.run(["xfreerdp3", "/auth-only", *common, "/p:not-the-password"],
                             capture_output=True, text=True, timeout=60)
        good = subprocess.run(["xfreerdp3", "/auth-only", *common, f"/p:{args.password}"],
                              capture_output=True, text=True, timeout=60)
        open(f"{out}/auth.log", "w").write(bad.stdout + bad.stderr + "\n----\n" + good.stdout + good.stderr)
        result("auth", bad.returncode != 0 and good.returncode == 0,
               f"wrong password exit {bad.returncode}, right password exit {good.returncode}")

    # FreeRDP plays rdpsnd into PulseAudio's sink (test.sh: a null sink, the default), whose
    # monitor parec records
    wav = f"{out}/rdpsnd-{args.arch}.wav"
    recorder = subprocess.Popen(["parec", "-d", f"{args.sink}.monitor", "--file-format=wav", "--format=s16le",
                                 "--rate=48000", "--channels=2", wav],
                                stdout=subprocess.DEVNULL, stderr=open(f"{out}/parec-{args.arch}.log", "w"))
    env = {**os.environ, "DISPLAY": args.display}
    client_log = open(f"{out}/xfreerdp-{args.arch}.log", "w")
    client = subprocess.Popen(["xfreerdp3", *common, f"/p:{args.password}", "/sound:sys:pulse",
                               "-grab-keyboard", "/bpp:32"],
                              env=env, stdout=client_log, stderr=subprocess.STDOUT)
    sizes = []
    stop = threading.Event()
    try:
        win = freerdp_window(args.display)
        if not win:
            result("connect", False, "no FreeRDP window within 60 s")
            return finish(out)

        # the window's sizes as the guest changes its mode (firmware, then the kernel's framebuffer)
        def watch_sizes():
            while not stop.is_set():
                try:
                    size = window_size(args.display, win)
                except (subprocess.SubprocessError, KeyError, ValueError):
                    size = None
                if size and (not sizes or sizes[-1] != size):
                    sizes.append(size)
                time.sleep(0.05)

        threading.Thread(target=watch_sizes, daemon=True).start()
        time.sleep(0.3)
        log(f"FreeRDP window {win}: {sizes[0][0]}x{sizes[0][1]} at connect" if sizes else f"FreeRDP window {win}")

        serial = Serial(args.serial, f"{out}/serial-{args.arch}.log")
        # the guest boots now, with the client and the serial console attached
        if args.start == "cont":
            qmp(args.qmp, "cont")
        elif args.start == "reset":
            qmp(args.qmp, "system_reset")
        if not serial.expect(prompt, args.boot_timeout):
            result("boot", False, f"no wisp prompt within {args.boot_timeout:.0f} s")
            return finish(out)

        if "picture" not in skip or "resize" not in skip:
            t0 = time.time()
            m = serial.command(prompt, "fbtest", r"WISP-FB[^\n]*\n|fbtest:[^\n]*\n", 60)
            log(f"guest: {m.group(0).strip() if m else 'no fbtest result'}")
            dump = f"{out}/screendump-{args.arch}.ppm"
            qmp(args.qmp, "screendump", filename=dump)
            w, h, ref = read_ppm(dump)
            # until the client shows the same picture (or 20 s), for the delay and the comparison
            best = None
            while time.time() - t0 < 20:
                cw, ch = window_size(args.display, win)
                if (cw, ch) == (w, h):
                    _, _, got = x_screenshot(args.display, w, h, f"{out}/client-{args.arch}.ppm")
                    mean, share = compare(ref, got, w, h)
                    best = (mean, share, time.time() - t0)
                    if mean < 6 and share < 0.02:
                        break
                time.sleep(0.2)
            if "resize" not in skip:
                seen = " -> ".join(f"{a}x{b}" for a, b in sizes)
                result("resize", len(sizes) >= 2 and sizes[-1] == (w, h),
                       f"FreeRDP's window followed the guest's modes: {seen} (the guest's framebuffer:"
                       f" {w}x{h})")
            if "picture" not in skip:
                if best is None:
                    result("picture", False, f"the client never showed {w}x{h}")
                else:
                    mean, share, delay = best
                    result("picture", mean < 6 and share < 0.02,
                           f"{w}x{h}: mean difference {mean:.2f}/255, {share * 100:.2f}% of pixels off by"
                           f" more than 32 (vs QEMU's screendump; {delay:.2f} s from `fbtest` to a"
                           f" matching client picture)")

        xdotool(args.display, "windowfocus", "--sync", win, check=False)
        if "keyboard" not in skip:
            since = serial.mark()
            serial.command(prompt, "keytest", r"WISP-KEYBOARD[^\n]*\n|keyboard unavailable", 30)
            time.sleep(0.5)
            lat = []
            for key, code in (("a", 30), ("b", 48), ("Escape", 1)):
                mark = serial.mark()
                t = time.time()
                xdotool(args.display, "key", "--window", win, key)
                if serial.expect(rf"WISP-KEY v=1 code={code} value=1", 10, mark):
                    lat.append((time.time() - t) * 1000)
            got = re.findall(r"WISP-KEY v=1 code=(\d+)", serial.text(since))
            ok = got[:3] == ["30", "48", "1"]
            detail = f"guest got codes {got}"
            if lat:
                detail += f"; xdotool to the guest's serial line {min(lat):.0f}-{max(lat):.0f} ms"
            result("keyboard", ok, detail)

        if "mouse" not in skip:
            since = serial.mark()
            m = serial.command(prompt, "mousetest", r"WISP-MOUSE dev[^\n]*\n|mouse unavailable|unknown command", 30)
            in_guest = bool(m) and m.group(0).startswith("WISP-MOUSE")
            trace0 = os.path.getsize(args.input_trace) if args.input_trace and os.path.exists(args.input_trace) else 0
            time.sleep(0.5)
            for x, y in ((100, 100), (180, 140), (260, 200)):
                xdotool(args.display, "mousemove", "--window", win, str(x), str(y))
                time.sleep(0.2)
            xdotool(args.display, "click", "--window", win, "1")
            time.sleep(0.3)
            xdotool(args.display, "click", "--window", win, "3")
            if in_guest:
                serial.expect(r"mousetest: |WISP-MOUSE-EV type=1 code=273 value=1", 15, since)
                text = serial.text(since)
                rel = len(re.findall(r"WISP-MOUSE-EV type=2 ", text))
                absm = len(re.findall(r"WISP-MOUSE-EV type=3 ", text))
                left = "type=1 code=272 value=1" in text
                right = "type=1 code=273 value=1" in text
                where = "the guest's evdev (mousetest)"
            elif args.input_trace:
                # a wisp kernel without mousetest: QEMU's input layer (trace events input_event_*),
                # which hands the events to the guest's mouse
                time.sleep(1)
                with open(args.input_trace, errors="replace") as f:
                    f.seek(trace0)
                    text = f.read()
                rel = len(re.findall(r"input_event_rel ", text))
                absm = len(re.findall(r"input_event_abs ", text))
                left = re.search(r"input_event_btn .*button left, down (?:1|true)", text) is not None
                right = re.search(r"input_event_btn .*button right, down (?:1|true)", text) is not None
                where = "QEMU's input layer (trace; this wisp kernel has no mousetest)"
            else:
                left = right = False
                rel = absm = 0
                where = "nowhere: the guest has no mousetest and no --input-trace was given"
            result("mouse", left and right and (rel + absm) > 0,
                   f"in {where}: left {'yes' if left else 'no'}, right {'yes' if right else 'no'},"
                   f" motion events {rel} relative, {absm} absolute")

        if "sound" not in skip:
            size0 = os.path.getsize(wav) if os.path.exists(wav) else 0
            m = serial.command(prompt, f"soundtest 440 {args.sound_ms}", r"WISP-SOUND[^\n]*\n",
                               30 + args.sound_ms / 1000 * 3)
            log(f"guest: {m.group(0).strip() if m else 'no soundtest result'}")
            time.sleep(1.5)
            if not os.path.exists(wav):
                result("sound", False, "nothing recorded from the sink")
            else:
                rate, channels, samples = read_wav(wav)
                secs, hz, peak = tone(samples, rate)
                want = args.sound_ms / 1000
                result("sound", abs(hz - 440) < 440 * 0.03 and want * 0.8 < secs < want * 1.3,
                       f"{secs:.2f} s of sound at {hz:.1f} Hz (peak {peak}) from FreeRDP's rdpsnd output"
                       f" ({os.path.getsize(wav) - size0} bytes recorded at {rate} Hz)")
    finally:
        stop.set()
        for proc in (client, recorder):
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return finish(out)


def finish(out):
    with open(f"{out}/summary.txt", "a") as f:
        for name, ok, detail in RESULTS:
            f.write(f"{'PASS' if ok else 'FAIL'} {name}: {detail}\n")
    return 0 if RESULTS and all(ok for _, ok, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
