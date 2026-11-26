#!/usr/bin/env python3
"""qemudbussrc, qemudbusaudiosrc and qemu-dbus-input against a wisp guest
(packages/wsh-gst-qemu-dbus/test.sh runs it).

QEMU runs a wisp framebuffer kernel (e2e/wisp, `kernel-fb-<arch>`) paused, with its D-Bus display
and the audio driver dbus on a bus as qemu-server makes it. As an unprivileged member of
wsh-display this starts two gst-launch-1.0 pipelines and the input bridge:

  qemudbussrc ! videoconvert ! video/x-raw,format=RGB ! multifilesink   (raw RGB frames)
  qemudbusaudiosrc ! wavenc ! filesink                                  (the guest's sound)
  qemu-dbus-input                                                       (commands on its stdin)

then lets the guest boot and checks, each a PASS/FAIL line also listed in OUTDIR/summary.txt:

  picture   wisp's `fbtest` colour bars in the newest frame match QEMU's screendump
  path      the element got the picture the expected way (pixels, shared map or dmabufs; with
            dmabufs, how long the replies to UpdateDMABUF took, and with --dmabuf-import egl that
            EGL read them)
  keyboard  keys sent through the bridge reach the guest (`keytest`: evdev codes 30, 48, 1)
  mouse     buttons and motion through the bridge reach the guest (`mousetest`), relative on a
            PS/2 mouse (rel, and abs turned into relative motion), absolute on a virtio tablet
            (abs, and rel moving the bridge's pointer)
  sound     `soundtest 440 MS` in the WAV the audio pipeline wrote: a 440 Hz tone of about MS ms
            without a dropout (a quiet 10 ms window inside it), after the silence the element
            outputs while the guest plays nothing
  eos       when QEMU quits, the video pipeline ends by itself (EOS) and exits 0

Also measured (no pass/fail): the time from `fbtest` to the matching frame, and from a line written
to the bridge to the guest's report of the key.

usage: stream_test.py --arch ARCH --serial SOCK --qmp SOCK --address ADDR --outdir DIR
                      [--user U] [--expect pixels|map|dmabuf] [--mouse relative|absolute]
                      [--shared-map true|false] [--dmabuf-import auto|mmap|egl]
                      [--sound-ms MS] [--skip CHECK,...] [--start cont|reset]
"""

import argparse
import glob
import json
import math
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

RESULTS = []
NAME = ""


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
        self.prompts = 0
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
            time.sleep(0.005)
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
    """(mean absolute difference per channel, share of pixels that differ at all) of two RGB
    images, every pixel"""
    if a == b:
        return 0.0, 0.0
    total = 0
    differ = 0
    for o in range(0, w * h * 3, 3):
        d = abs(a[o] - b[o]) + abs(a[o + 1] - b[o + 1]) + abs(a[o + 2] - b[o + 2])
        total += d
        differ += d > 0
    return total / (w * h * 3), differ / (w * h)


def read_wav(path):
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
            pcm = data[pos + 8:pos + 8 + size]
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


def tone(samples, rate, want):
    """(seconds of sound, its frequency, peak, dropouts) of the loud part; the frequency counts
    rising edges through a quarter of the peak (hysteresis) over the tone, the want seconds from
    its first loud 10 ms window (after it, AC97 may play a few ms of its old buffer); dropouts: runs
    of quiet windows within the tone"""
    window = max(1, rate // 100)
    loud = []
    for i in range(0, len(samples) - window, window):
        chunk = samples[i:i + window]
        if math.sqrt(sum(s * s for s in chunk) / window) > 1000:
            loud.append(i)
    if not loud:
        return 0.0, 0.0, max((abs(s) for s in samples), default=0), 0
    first = loud[0]
    end = first + int(want * rate) - 3 * window
    inside = [i for i in loud if i < end]
    last = inside[-1] + window
    dropouts = sum(1 for a, b in zip(inside, inside[1:]) if b - a > window)
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
    return len(loud) * window / rate, edges / ((last - first) / rate), peak, dropouts


def as_user(user, cmd):
    """cmd run as user (a member of wsh-display), or as it is without one"""
    if not user:
        return cmd
    return ["setpriv", f"--reuid={user}", f"--regid={user}", "--init-groups", *cmd]


def wait_log(path, pattern, timeout):
    deadline = time.time() + timeout
    rx = re.compile(pattern)
    while time.time() < deadline:
        try:
            m = rx.search(open(path, errors="replace").read())
        except FileNotFoundError:
            m = None
        if m:
            return m
        time.sleep(0.1)
    return None


class Bridge:
    """qemu-dbus-input with its stdin and stdout"""

    def __init__(self, cmd, logpath):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(logpath + ".err", "w"), text=True, bufsize=1)
        self.lines = []
        self.lock = threading.Lock()
        self.log = open(logpath, "w")
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            with self.lock:
                self.lines.append(line.rstrip("\n"))
            self.log.write(line)
            self.log.flush()

    def send(self, *lines):
        self.log.write("".join(f"> {line}\n" for line in lines))
        self.proc.stdin.write("".join(f"{line}\n" for line in lines))
        self.proc.stdin.flush()

    def expect(self, pattern, timeout):
        deadline = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < deadline:
            with self.lock:
                for line in self.lines:
                    m = rx.search(line)
                    if m:
                        return m
            time.sleep(0.01)
        return None

    def errors(self):
        with self.lock:
            return [line for line in self.lines if line.startswith("error")]

    def close(self):
        try:
            self.proc.stdin.close()
            return self.proc.wait(10)
        except (subprocess.TimeoutExpired, BrokenPipeError):
            self.proc.kill()
            return None


def newest_frame(frames):
    files = glob.glob(os.path.join(frames, "f*.rgb"))
    return max(files, key=lambda f: int(re.search(r"f(\d+)\.rgb$", f).group(1))) if files else None


def stop(proc, timeout=15):
    """SIGINT, which gst-launch -e turns into EOS; the exit code"""
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", required=True)
    ap.add_argument("--name", help="the run's name in the results (default: the arch)")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--qmp", required=True)
    ap.add_argument("--address", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--user", default="", help="run the clients as this member of wsh-display")
    ap.add_argument("--expect", choices=("pixels", "map", "dmabuf"), default="map")
    ap.add_argument("--mouse", choices=("relative", "absolute"), default="relative")
    ap.add_argument("--shared-map", default="true")
    ap.add_argument("--dmabuf-import", choices=("auto", "mmap", "egl"), default="auto")
    ap.add_argument("--sound-ms", type=int, default=2000)
    ap.add_argument("--skip", default="")
    ap.add_argument("--boot-timeout", type=float, default=300)
    ap.add_argument("--start", choices=("cont", "reset"), default="cont",
                    help="how the guest starts once the clients are attached: QMP cont (QEMU"
                    " started with -S) or system_reset (a VM already running, e.g. from qm start)")
    args = ap.parse_args()
    skip = set(filter(None, args.skip.split(",")))
    global NAME
    NAME = args.name or args.arch
    out = args.outdir
    frames = os.path.join(out, "frames")
    os.makedirs(frames, exist_ok=True)
    if args.user:
        subprocess.run(["chown", "-R", args.user, out], check=True)
    prompt = r"wisp:\S+> "
    # GST_DEBUG adds to the levels the checks read
    debug = "qemudbussrc:4,qemudbusaudiosrc:4"
    if os.environ.get("GST_DEBUG"):
        debug += "," + os.environ["GST_DEBUG"]
    env = {**os.environ, "GST_DEBUG": debug, "GST_DEBUG_NO_COLOR": "1"}
    procs = []

    video_log = f"{out}/video.log"
    video = subprocess.Popen(as_user(args.user, [
        "gst-launch-1.0", "-e", "qemudbussrc", f"address={args.address}",
        f"shared-map={args.shared_map}", f"dmabuf-import={args.dmabuf_import}", "!",
        "videoconvert", "!", "video/x-raw,format=RGB", "!",
        "multifilesink", f"location={frames}/f%06d.rgb", "max-files=40"]),
        env=env, stdout=open(video_log, "w"), stderr=subprocess.STDOUT)
    procs.append(video)
    audio = None
    wav = f"{out}/sound.wav"
    if "sound" not in skip:
        audio = subprocess.Popen(as_user(args.user, [
            "gst-launch-1.0", "-e", "qemudbusaudiosrc", f"address={args.address}", "!", "wavenc",
            "!", "filesink", f"location={wav}"]),
            env=env, stdout=open(f"{out}/audio.log", "w"), stderr=subprocess.STDOUT)
        procs.append(audio)
    bridge = Bridge(as_user(args.user, ["qemu-dbus-input", "--address", args.address]),
                    f"{out}/bridge.log")
    try:
        ok = wait_log(video_log, r"listening on", 30)
        result("connect", bool(ok) and video.poll() is None,
               "qemudbussrc registered its listener" if ok else
               f"qemudbussrc didn't register (exit {video.poll()}): see video.log")
        if not ok:
            return finish(out)
        if audio and not wait_log(f"{out}/audio.log", r"listening on", 30):
            result("sound", False, "qemudbusaudiosrc didn't register its listener: see audio.log")
            skip.add("sound")
        ready = bridge.expect(r"^ready .* mode (\w+) width (\d+) height (\d+)", 30)
        if not ready:
            result("bridge", False, f"qemu-dbus-input didn't connect: {bridge.lines}")
            skip.update(("keyboard", "mouse"))
        else:
            log(f"bridge: {ready.group(0)}")

        serial = Serial(args.serial, f"{out}/serial.log")
        qmp(args.qmp, "cont" if args.start == "cont" else "system_reset")
        if not serial.expect(prompt, args.boot_timeout):
            result("boot", False, f"no wisp prompt within {args.boot_timeout:.0f} s")
            return finish(out)

        if "picture" not in skip:
            serial.command(prompt, "fbtest", r"WISP-FB[^\n]*\n|fbtest:[^\n]*\n", 60)
            # The guest's DRM fbdev emulation copies its shadow buffer to the VGA's memory in a
            # worker, so QEMU's picture can change for a moment after fbtest: a fresh screendump
            # every half second until the newest frame matches one
            t0 = time.time()
            dump = f"{out}/screendump.ppm"
            best = None
            dumped = 0
            while time.time() - t0 < 20:
                if time.time() - dumped >= 0.5:
                    qmp(args.qmp, "screendump", filename=dump)
                    w, h, ref = read_ppm(dump)
                    dumped = time.time()
                f = newest_frame(frames)
                if f and os.path.getsize(f) == w * h * 3:
                    got = open(f, "rb").read()
                    mean, share = compare(ref, got, w, h)
                    best = (mean, share, time.time() - t0, f)
                    if mean < 0.5 and share < 0.001:
                        break
                time.sleep(0.1)
            if best is None:
                result("picture", False, f"no {w}x{h} frame from qemudbussrc within 20 s")
            else:
                mean, share, delay, f = best
                with open(f"{out}/frame.ppm", "wb") as ppm:
                    ppm.write(b"P6\n%d %d\n255\n" % (w, h) + open(f, "rb").read())
                result("picture", mean < 0.5 and share < 0.001,
                       f"{w}x{h}: mean difference {mean:.3f}/255, {share * 100:.3f}% of pixels"
                       f" differ (the newest frame against QEMU's screendump, {delay:.2f} s"
                       f" after fbtest)")

        if "keyboard" not in skip:
            since = serial.mark()
            serial.command(prompt, "keytest", r"WISP-KEYBOARD[^\n]*\n|keyboard unavailable", 30)
            time.sleep(0.5)
            lat = []
            for code in (30, 48, 1):
                mark = serial.mark()
                t = time.time()
                bridge.send(f"key {code} 1", f"key {code} 0")
                if serial.expect(rf"WISP-KEY v=1 code={code} value=1", 10, mark):
                    lat.append((time.time() - t) * 1000)
            got = re.findall(r"WISP-KEY v=1 code=(\d+)", serial.text(since))
            detail = f"guest got codes {got}"
            if lat:
                detail += f"; bridge input to the guest's serial line {min(lat):.1f}-{max(lat):.1f} ms"
            result("keyboard", got[:3] == ["30", "48", "1"] and not bridge.errors(), detail)

        if "mouse" not in skip:
            mode = ready.group(1) if ready else "?"
            bridge.send("query")
            q = bridge.expect(r"^mode (\w+) width (\d+) height (\d+)$", 10)
            if q:
                mode = q.group(1)
            cw, ch = (int(q.group(2)), int(q.group(3))) if q else (0, 0)
            since = serial.mark()
            m = serial.command(prompt, "mousetest", r"WISP-MOUSE dev[^\n]*\n|mouse unavailable", 30)
            time.sleep(0.5)
            if args.mouse == "relative":
                # rel 10 5, then abs 100,100 -> 130,120: relative 30, 20
                bridge.send("rel 10 5", "abs 100 100", "abs 130 120", "sync")
            else:
                # the centre, then 10 to the right through rel (the bridge's own pointer)
                bridge.send(f"abs {cw // 2} {ch // 2}", "rel 10 0", "sync")
            bridge.expect(r"^sync ", 10)
            time.sleep(0.3)
            bridge.send("btn left 1", "btn left 0", "btn right 1", "btn right 0", "sync")
            serial.expect(r"WISP-MOUSE-EV type=1 code=273 value=1|mousetest: ", 15, since)
            text = serial.text(since)
            ev = [(int(t), int(c), int(v)) for t, c, v in
                  re.findall(r"WISP-MOUSE-EV type=(\d+) code=(\d+) value=(-?\d+)", text)]
            left = (1, 272, 1) in ev
            right = (1, 273, 1) in ev
            if args.mouse == "relative":
                dx = sum(v for t, c, v in ev if t == 2 and c == 0)
                dy = sum(v for t, c, v in ev if t == 2 and c == 1)
                motion_ok = (dx, dy) == (40, 25)
                motion = f"relative motion X {dx:+d}, Y {dy:+d} (sent rel 10 5 and abs 100,100 -> 130,120: +40, +25)"
            else:
                xs = [v for t, c, v in ev if t == 3 and c == 0]
                ys = [v for t, c, v in ev if t == 3 and c == 1]
                want = [(cw // 2) * 0x7fff // cw, (cw // 2 + 10) * 0x7fff // cw]
                wanty = (ch // 2) * 0x7fff // ch
                motion_ok = (len(xs) >= 2 and all(abs(a - b) <= 2 for a, b in zip(xs[-2:], want))
                             and ys and abs(ys[-1] - wanty) <= 2)
                motion = (f"absolute X {xs}, Y {ys} (sent abs {cw // 2},{ch // 2} and rel 10 0 on a"
                          f" {cw}x{ch} console: X {want}, Y {wanty} of 0-32767)")
            dev = m.group(0).strip() if m else "no mousetest device"
            result("mouse", left and right and motion_ok and mode == args.mouse
                   and not bridge.errors(),
                   f"bridge mode {mode}; {dev}; left {'yes' if left else 'no'}, right"
                   f" {'yes' if right else 'no'}; {motion}"
                   + (f"; bridge errors {bridge.errors()}" if bridge.errors() else ""))

        if "sound" not in skip:
            m = serial.command(prompt, f"soundtest 440 {args.sound_ms}", r"WISP-SOUND[^\n]*\n",
                               30 + args.sound_ms / 1000 * 3)
            log(f"guest: {m.group(0).strip() if m else 'no soundtest result'}")
            time.sleep(1.0)
            rc = stop(audio)
            stats = wait_log(f"{out}/audio.log", r"stopped: ([^\n]*)", 5)
            try:
                rate, channels, samples = read_wav(wav)
                want = args.sound_ms / 1000
                secs, hz, peak, dropouts = tone(samples, rate, want)
                result("sound", rc == 0 and abs(hz - 440) < 440 * 0.01 and want * 0.9 < secs < want * 1.15
                       and dropouts == 0,
                       f"{secs:.2f} s of sound at {hz:.1f} Hz (peak {peak}, {dropouts} dropouts) in the WAV from"
                       f" qemudbusaudiosrc ({rate} Hz, {channels} channels; gst-launch exit {rc};"
                       f" {stats.group(1) if stats else 'no stats'})")
            except (OSError, ValueError) as e:
                result("sound", False, f"the WAV: {e} (gst-launch exit {rc})")

        # QEMU quits: the video pipeline ends by itself
        try:
            qmp(args.qmp, "quit")
        except (OSError, RuntimeError, json.JSONDecodeError):
            pass
        try:
            rc = video.wait(20)
        except subprocess.TimeoutExpired:
            rc = None
        stats = wait_log(video_log, r"stopped: ([^\n]*)", 5)
        stats = stats.group(1) if stats else ""
        if "eos" not in skip:
            result("eos", rc == 0, f"the video pipeline exited {rc} after QEMU quit"
                   + (" (EOS)" if re.search(r"Got EOS from element", open(video_log, errors="replace").read()) else ""))
        counts = dict((k, int(v)) for k, v in re.findall(r"([a-z-]+)=(\d+)(?=[ /]|$)", stats))
        if args.expect == "dmabuf":
            reply = re.search(r"dmabuf-reply-us=(\d+)/(\d+)", stats)
            ok = counts.get("dmabuf-scanouts", 0) > 0 and counts.get("dmabuf-updates", 0) > 0
            if args.dmabuf_import == "egl":
                ok = ok and counts.get("dmabuf-egl-scanouts", 0) == counts.get("dmabuf-scanouts", 0)
            detail = f"dmabufs ({stats})"
            if reply:
                detail += f"; UpdateDMABUF answered in {int(reply.group(1))} us on average, {int(reply.group(2))} us at most"
        elif args.expect == "map":
            ok = counts.get("map-scanouts", 0) > 0 and counts.get("dmabuf-scanouts", 0) == 0
            detail = f"the shared map ({stats})"
        else:
            ok = counts.get("scanouts", 0) > 0 and counts.get("map-scanouts", 0) == 0
            detail = f"pixels in the messages ({stats})"
        result("path", ok and counts.get("frames", 0) > 0, f"expected {detail}")
    finally:
        bridge.close()
        for p in procs:
            if p.poll() is None:
                stop(p, 5)
    return finish(out)


def finish(out):
    with open(f"{out}/summary.txt", "a") as f:
        for n, ok, detail in RESULTS:
            f.write(f"{'PASS' if ok else 'FAIL'} {NAME}: {n}: {detail}\n")
    return 0 if RESULTS and all(ok for _, ok, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
