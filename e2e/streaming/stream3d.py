#!/usr/bin/env python3
"""The client side of e2e/streaming/test.sh: a Moonlight session to Wolf on the node container,
driving the wisp guest and measuring what the client gets.

It runs wsh-moonlight-probe (a paired Moonlight client that decodes every frame and reports it
with its times, see moonlight-probe.c), the guest's serial line and QMP over TCP from the node
container, and checks, each a PASS/FAIL line in OUTDIR/summary.txt:

  stream    the session starts and frames arrive (H.264, decoded in software)
  picture   wisp's `fbtest` bars in a decoded frame, compared with QEMU's screendump (H.264 is
            lossy: the mean difference per channel must stay small)
  latency   end to end, guest to client: `mandel fb` and `fbtest` alternately; from the guest's
            report that fbtest drew its bars (the serial line) to the first decoded frame that
            shows them at the bottom (the last rows fbtest draws); ROUNDS samples
  keyboard  keys sent by the client (Windows virtual-key codes, as Moonlight sends them: A, B,
            Esc) reach the guest as Linux codes 30, 48, 1 (`keytest`); latency from the client's
            send to the guest's serial line
  mouse     absolute positions, relative motion and the left and right buttons from the client
            reach the guest's PS/2 mouse (`mousetest`) as the motion they add up to
  sound     `soundtest 440 MS` in the client's decoded audio: a 440 Hz tone of about MS ms
            without a dropout (no quiet 10 ms window inside it), and the audio steady (never
            more than AHEAD_MS of sound arriving at once: a burst, as Wolf's audiorate made when
            the source's stream had a gap, comes with dropped sound when the host is busy); and
            from the command to the first loud packet at the client
  pacing    a burst of BURST draws typed at once (`mandel fb` and `fbtest` in turn, rows
            written without a pause for a few seconds): frames per second at the client, how
            many of them carry a new picture (the probe's changed share > 0), and the spread of
            the intervals, against the D-Bus display's refresh (REFRESH_MS)

Every latency sample is in OUTDIR/latency.txt (fbtest typed, the guest's report, the frame at the
client), every frame of the burst in OUTDIR/pacing.txt.

usage: stream3d.py --node HOST --keydir DIR --app NAME --outdir DIR [--rounds N]
                   [--refresh-ms N] [--name NAME] [--width W --height H --fps F]
                   [--serial ADDR --qmp ADDR --start cont|reset]
                   [--probe-prefix CMD --probe-outdir DIR] [--shared DIR]

On a node (a VM from `qm start`, Wolf and the probe in a container), it runs on the node:
  --serial unix:/var/run/qemu-server/VMID.serial0 --qmp unix:/var/run/qemu-server/VMID.qmp
  --start reset --probe-prefix "pct exec CTID -- env HOME=/root PATH=/usr/local/bin:/usr/bin:/bin"
  with OUTDIR and --shared in a directory bind-mounted into the container, --probe-outdir the
  same directory as the container sees it.
"""

import argparse
import json
import math
import os
import re
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time

RESULTS = []
NAME = ""
# wisp's prompt, coloured: wisp:x86_64> with ANSI escapes (no spaces in them)
PROMPT = r"wisp\S*> "
BURST = 40
# the most audio that may arrive at the client at once (ms of sound beyond the time it took)
AHEAD_MS = 250
BARS = [(0, 0, 0), (0, 0, 255), (0, 255, 0), (0, 255, 255), (255, 0, 0), (255, 0, 255),
        (255, 255, 0), (255, 255, 255)]


def log(msg):
    print(msg, flush=True)


def result(name, ok, detail):
    RESULTS.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


class Serial:
    """The guest's serial console over TCP, read in the background, every chunk timestamped"""

    def __init__(self, address, logpath):
        self.sock = connect(address)
        self.sock.settimeout(None)
        self.buf = b""
        self.times = []  # (offset in buf, time it arrived)
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
            t = time.time()
            with self.lock:
                self.times.append((len(self.buf), t))
                self.buf += data
            self.logfile.write(data)
            self.logfile.flush()

    def text(self, since=0):
        with self.lock:
            data = self.buf[since:]
        return data.decode(errors="replace")

    def mark(self):
        with self.lock:
            return len(self.buf)

    def time_at(self, offset):
        """when the byte at offset arrived"""
        with self.lock:
            t = None
            for off, when in self.times:
                if off > offset:
                    break
                t = when
            return t

    def send(self, line):
        self.sock.sendall(line.encode() + b"\r")

    def expect(self, pattern, timeout, since=0):
        """(match, arrival time of the match's end) or (None, None); offsets are in bytes of
        the decoded text, which is ASCII here"""
        deadline = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < deadline:
            m = rx.search(self.text(since))
            if m:
                return m, self.time_at(since + m.end() - 1)
            time.sleep(0.002)
        return None, None

    def command(self, cmd, done, timeout, prompt=PROMPT):
        deadline = time.time() + timeout
        rx = re.compile(prompt)
        while len(rx.findall(self.text())) <= self.prompts:
            if time.time() > deadline:
                return None, None, None
            time.sleep(0.02)
        self.prompts = len(rx.findall(self.text()))
        since = self.mark()
        t = time.time()
        self.send(cmd)
        m, when = self.expect(done, timeout, since)
        return m, when, t


def connect(address):
    """a socket to unix:PATH or HOST:PORT"""
    if address.startswith("unix:"):
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(30)
        s.connect(address[5:])
    else:
        host, _, port = address.rpartition(":")
        s = socket.create_connection((host, int(port)), timeout=30)
    return s


def qmp(address, cmd, **arguments):
    s = connect(address)
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


class Probe:
    """wsh-moonlight-probe with its stdin and its event lines"""

    def __init__(self, cmd, logpath):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.frames = []  # (index, rx s, dec s, frame number, type, bytes, size, hash, colours)
        self.events = []  # (kind, time s, rest)
        self.lock = threading.Lock()
        self.log = open(logpath, "w")
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            self.log.write(line + "\n")
            parts = line.split()
            if not parts:
                continue
            with self.lock:
                if parts[0] == "frame" and len(parts) >= 17:
                    self.frames.append((int(parts[1]), int(parts[2]) / 1e6, int(parts[3]) / 1e6,
                                        int(parts[4]), int(parts[5]), int(parts[6]), parts[7],
                                        int(parts[8]), [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
                                                   for c in parts[9:17]]))
                elif parts[0] in ("sent", "audio-onset", "audio-quiet") and len(parts) >= 2:
                    self.events.append((parts[0], int(parts[1]) / 1e6, " ".join(parts[2:])))
                else:
                    self.events.append((parts[0], time.time(), " ".join(parts[1:])))

    def send(self, line):
        self.log.write(f"> {line}\n")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def wait_event(self, kind, timeout, since=0, pattern=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                for e in self.events[since:]:
                    if e[0] == kind and (pattern is None or re.search(pattern, e[2])):
                        return e
            if self.proc.poll() is not None:
                return None
            time.sleep(0.005)
        return None

    def nevents(self):
        with self.lock:
            return len(self.events)

    def frames_since(self, t):
        with self.lock:
            return [f for f in self.frames if f[2] >= t]

    def close(self):
        try:
            self.send("quit")
            return self.proc.wait(15)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            self.proc.kill()
            return None


def is_bars(colours, tol=70):
    return all(all(abs(c - e) <= tol for c, e in zip(col, exp)) for col, exp in zip(colours, BARS))


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
    w, h = int(fields[1]), int(fields[2])
    return w, h, data[pos + 1:pos + 1 + w * h * 3]


def compare(a, b, w, h):
    """mean absolute difference per channel; share of pixels off by more than 48 in a channel
    (every 3rd pixel of every 3rd row)"""
    total = 0
    off = 0
    n = 0
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            o = (y * w + x) * 3
            d = [abs(a[o + i] - b[o + i]) for i in range(3)]
            total += sum(d)
            off += max(d) > 48
            n += 1
    return total / (n * 3), off / n


def read_wav(path):
    data = open(path, "rb").read()
    pos = 12
    rate = channels = None
    pcm = b""
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"fmt ":
            _, channels, rate = struct.unpack("<HHI", data[pos + 8:pos + 16])
        if cid == b"data":
            pcm = data[pos + 8:]
            break
        pos += 8 + size
    frame = 2 * channels
    n = len(pcm) // frame
    return rate, channels, struct.unpack(f"<{n * channels}h", pcm[:n * frame])[0::channels]


def tone(samples, rate, want):
    """(seconds of sound, its frequency, dropouts) of the loud part, in 10 ms windows. The
    frequency counts rising edges through a quarter of the peak within each run of loud windows,
    over the time from the run's first to its last rising edge, so a dropout (quiet windows
    inside the tone) shortens the sound without bending the pitch. Dropouts: quiet runs within
    the tone, the want seconds from its first loud window (after it, AC97 may play a few ms of
    its old buffer)"""
    window = max(1, rate // 100)
    loud = []
    for i in range(0, len(samples) - window, window):
        chunk = samples[i:i + window]
        if math.sqrt(sum(s * s for s in chunk) / window) > 1000:
            loud.append(i)
    if not loud:
        return 0.0, 0.0, 0
    level = max(abs(s) for i in loud for s in samples[i:i + window]) // 4
    # contiguous runs of loud windows, the edges counted over each run
    runs = []
    for i in loud:
        if runs and i == runs[-1][1]:
            runs[-1][1] = i + window
        else:
            runs.append([i, i + window])
    # per run, the rising edges' count over the time from its first to its last rising edge
    cycles = 0
    span = 0
    for a, b in runs:
        state = 0
        rising = []
        for n, s in enumerate(samples[a:b]):
            if state <= 0 and s > level:
                state = 1
                rising.append(n)
            elif state >= 0 and s < -level:
                state = -1
        if len(rising) > 1:
            cycles += len(rising) - 1
            span += (rising[-1] - rising[0]) / rate
    end = runs[0][0] + int(want * rate) - 3 * window
    dropouts = sum(1 for a, _ in runs[1:] if a < end)
    return len(loud) * window / rate, cycles / span if span else 0.0, dropouts


def bridge_time(path, line, after):
    """when wolf-input-bridge read the event it logged as line, the first after a time"""
    try:
        for entry in open(path):
            t, _, cmd = entry.rstrip("\n").partition(" ")
            if cmd == line and int(t) / 1e6 >= after:
                return int(t) / 1e6
    except (OSError, ValueError):
        pass
    return None


def stats(values):
    if not values:
        return "none"
    v = sorted(values)
    return (f"median {statistics.median(v):.1f}, min {v[0]:.1f}, max {v[-1]:.1f}, mean"
            f" {statistics.mean(v):.1f} (n={len(v)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", required=True, help="Wolf's host as the client reaches it")
    ap.add_argument("--serial", help="the guest's serial line: unix:PATH or HOST:PORT (default NODE:4555)")
    ap.add_argument("--qmp", help="QEMU's QMP: unix:PATH or HOST:PORT (default NODE:4556)")
    ap.add_argument("--start", choices=("cont", "reset"), default="cont",
                    help="cont (QEMU paused, test.sh) or reset (a VM already running, qm start)")
    ap.add_argument("--probe-prefix", default="",
                    help="run the probe through this command, e.g. 'pct exec 9300 --' on a node")
    ap.add_argument("--probe-outdir", default="",
                    help="OUTDIR as the probe sees it (default OUTDIR; with --probe-prefix a shared mount)")
    ap.add_argument("--keydir", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--refresh-ms", type=int, default=30)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--sound-ms", type=int, default=2000)
    ap.add_argument("--skip", default="")
    ap.add_argument("--shared", default="/shared",
                    help="a directory both containers mount (QEMU's screendump lands there)")
    args = ap.parse_args()
    args.serial = args.serial or f"{args.node}:4555"
    args.qmp = args.qmp or f"{args.node}:4556"
    skip = set(filter(None, args.skip.split(",")))
    global NAME
    NAME = args.name
    out = args.outdir
    os.makedirs(out, exist_ok=True)
    node = args.node

    probe_out = args.probe_outdir or out
    probe = Probe([*args.probe_prefix.split(), "wsh-moonlight-probe", "--width", str(args.width),
                   "--height", str(args.height), "--fps", str(args.fps), node, args.keydir, args.app,
                   probe_out], f"{out}/probe.log")
    serial = None
    try:
        conn = probe.wait_event("connected", 60)
        first = None
        if conn:
            deadline = time.time() + 30
            while time.time() < deadline and not first:
                f = probe.frames_since(0)
                first = f[0] if f else None
                time.sleep(0.05)
        result("stream", bool(conn and first),
               f"session started; first frame {first[6]} {first[2] - conn[1]:.2f} s after the"
               f" connection" if conn and first else
               f"no {'frame' if conn else 'connection'} (see probe.log)")
        if not (conn and first):
            return finish(out)

        serial = Serial(args.serial, f"{out}/serial.log")
        # QEMU started paused (-S, test.sh) goes on; a VM that runs already (qm start) restarts,
        # so its boot prompt comes and its picture starts from the console's text
        qmp(args.qmp, "cont" if args.start == "cont" else "system_reset")
        m, _ = serial.expect(PROMPT, 300)
        if not m:
            result("boot", False, "no wisp prompt within 300 s")
            return finish(out)

        if "picture" not in skip:
            m, t_drawn, _ = serial.command("fbtest", r"WISP-FB [^\n]*drawn=1[^\n]*\n", 60)
            ok = False
            detail = "fbtest didn't draw"
            if m:
                deadline = time.time() + 20
                shown = None
                while time.time() < deadline and not shown:
                    shown = next((f for f in probe.frames_since(t_drawn - 1) if is_bars(f[8])), None)
                    time.sleep(0.02)
                if shown:
                    time.sleep(1.0)  # the guest's fbdev worker may still copy; x264 refines
                    qmp(args.qmp, "screendump", filename=f"{args.shared}/screendump.ppm")
                    n = probe.nevents()
                    probe.send(f"snap {probe_out}/frame.ppm")
                    snap = probe.wait_event("snap", 10, n)
                    dump = f"{args.shared}/screendump.ppm"
                    for _ in range(50):
                        if os.path.exists(dump) and os.path.getsize(dump) > 0:
                            break
                        time.sleep(0.1)
                    try:
                        w, h, ref = read_ppm(dump)
                        w2, h2, got = read_ppm(f"{out}/frame.ppm")
                        if (w, h) != (w2, h2):
                            detail = f"frame {w2}x{h2}, screendump {w}x{h}"
                        else:
                            mean, share = compare(ref, got, w, h)
                            # 4:2:0 chroma smears the bars' colour edges over a pixel or two
                            ok = mean < 4 and share < 0.03
                            detail = (f"{w}x{h}: mean difference {mean:.2f}/255, {share * 100:.2f}% of"
                                      f" pixels off by more than 48 (the decoded frame against QEMU's"
                                      f" screendump; H.264 at the client's bitrate)")
                    except (OSError, ValueError, IndexError) as e:
                        detail = f"no comparison: {e} (snap {snap})"
                else:
                    detail = "the bars never reached the client"
            result("picture", ok, detail)

        if "latency" not in skip:
            lat = []
            dec = []
            rounds = ["# fbtest typed, guest's report, frame complete at the client, decoded, frame index"]
            for i in range(args.rounds):
                m, _, _ = serial.command("mandel fb", r"WISP-FBMANDEL [^\n]*\n", 120)
                if not m:
                    break
                # wait for the client to show something other than the bars at the bottom
                deadline = time.time() + 20
                while time.time() < deadline:
                    fs = probe.frames_since(time.time() - 0.3)
                    if fs and not is_bars(fs[-1][8]):
                        break
                    time.sleep(0.02)
                time.sleep(0.3)
                m, t_drawn, t_cmd = serial.command("fbtest", r"WISP-FB [^\n]*drawn=1[^\n]*\n", 60)
                if not m:
                    break
                deadline = time.time() + 10
                shown = None
                while time.time() < deadline and not shown:
                    shown = next((f for f in probe.frames_since(t_cmd) if is_bars(f[8])), None)
                    time.sleep(0.01)
                if shown:
                    lat.append((shown[2] - t_drawn) * 1000)
                    dec.append((shown[2] - shown[1]) * 1000)
                    rounds.append(f"{t_cmd:.6f} {t_drawn:.6f} {shown[1]:.6f} {shown[2]:.6f} {shown[0]}")
            result("latency", len(lat) >= max(1, args.rounds // 2),
                   f"guest drew fbtest's bars (serial line) -> decoded at the client, ms: {stats(lat)};"
                   f" of that, the client's software decode {stats(dec)}")
            with open(f"{out}/latency.txt", "w") as f:
                f.write("\n".join(rounds) + "\n")

        if "pacing" not in skip:
            # A burst: BURST commands typed at once, fbtest and mandel fb in turn, so the guest
            # draws without a pause (each draw writes rows for 30-120 ms)
            while len(re.findall(PROMPT, serial.text())) <= serial.prompts:
                time.sleep(0.02)
            since = serial.mark()
            t0 = time.time()
            for i in range(BURST):
                serial.send("fbtest" if i % 2 else "mandel fb")
            done = None
            deadline = time.time() + 120
            while time.time() < deadline:
                if len(re.findall(r"WISP-FB(?:MANDEL)? [^\n]*\n", serial.text(since))) >= BURST:
                    done = time.time()
                    break
                time.sleep(0.01)
            time.sleep(0.5)
            # the last prompt of the burst is the one the next command is typed at
            serial.prompts = len(re.findall(PROMPT, serial.text())) - 1
            t_end = (done or time.time()) + 0.2
            fs = [f for f in probe.frames_since(t0 + 0.1) if f[2] <= t_end]
            if len(fs) > 2:
                span = fs[-1][1] - fs[0][1]
                iv = [(b[1] - a[1]) * 1000 for a, b in zip(fs, fs[1:])]
                new = [f for f in fs if f[7] > 0]
                niv = [(b[1] - a[1]) * 1000 for a, b in zip(new, new[1:])]
                fps = (len(fs) - 1) / span if span > 0 else 0
                nfps = len(new) / span if span > 0 else 0
                result("pacing", fps > 5 and done is not None,
                       f"refresh-ms {args.refresh_ms} (QEMU looks for changes at most"
                       f" {1000 / args.refresh_ms:.1f} times/s): during {span:.2f} s of drawing"
                       f" ({BURST} draws) {fps:.1f} frames/s reached the client, {nfps:.1f}/s with a new"
                       f" picture; intervals between frames ms: {stats(iv)}, stdev"
                       f" {statistics.pstdev(iv):.1f}; between new pictures: {stats(niv)}")
                with open(f"{out}/pacing.txt", "w") as f:
                    f.write("# frame complete at the client (s), decoded, changed (per mille)\n")
                    f.write("".join(f"{x[1]:.6f} {x[2]:.6f} {x[7]}\n" for x in fs))
            else:
                result("pacing", False, f"only {len(fs)} frames during the burst")

        if "keyboard" not in skip:
            since = serial.mark()
            serial.command("keytest", r"WISP-KEYBOARD[^\n]*\n|keyboard unavailable", 30)
            time.sleep(0.5)
            lat = []
            via = []  # (client -> Wolf's device read by the bridge, bridge -> guest's serial line)
            for vk, code in ((0x41, 30), (0x42, 48), (0x1B, 1)):
                mark = serial.mark()
                n = probe.nevents()
                probe.send(f"key {vk} down")
                probe.send(f"key {vk} up")
                sent = probe.wait_event("sent", 5, n)
                m, when = serial.expect(rf"WISP-KEY v=1 code={code} value=1", 10, mark)
                if m and sent:
                    lat.append((when - sent[1]) * 1000)
                    t_bridge = bridge_time(f"{args.shared}/wolf-input-bridge.log", f"key {code} 1", sent[1])
                    if t_bridge:
                        via.append(((t_bridge - sent[1]) * 1000, (when - t_bridge) * 1000))
            got = re.findall(r"WISP-KEY v=1 code=(\d+)", serial.text(since))
            split = ""
            if via:
                split = (f"; of that, client -> Wolf's uinput keyboard read by the bridge {stats([a for a, _ in via])},"
                         f" bridge -> guest {stats([b for _, b in via])}")
            result("keyboard", got[:3] == ["30", "48", "1"],
                   f"guest got codes {got} (client sent VK 0x41, 0x42, 0x1b); client send -> guest's"
                   f" serial line, ms: {stats(lat)}{split}")

        if "mouse" not in skip:
            since = serial.mark()
            m, _, _ = serial.command("mousetest", r"WISP-MOUSE dev[^\n]*\n|mouse unavailable", 30)
            time.sleep(0.5)
            # Moonlight's absolute position -> Wolf's absolute mouse (19200 x 12000) -> abs X Y W H
            # -> the bridge: on the guest's PS/2 mouse the first position only sets the bridge's
            # pointer, the next one moves by the difference (+60, +30 console pixels); Moonlight's
            # relative motion -> Wolf's relative mouse -> rel 10 0
            cx, cy = args.width // 2, args.height // 2
            probe.send(f"pos {cx} {cy} {args.width} {args.height}")
            time.sleep(0.3)
            probe.send("move 10 0")
            time.sleep(0.3)
            probe.send(f"pos {cx + 60} {cy + 30} {args.width} {args.height}")
            time.sleep(0.3)
            n = probe.nevents()
            probe.send("button left down")
            sent = probe.wait_event("sent", 5, n)
            probe.send("button left up")
            time.sleep(0.2)
            probe.send("button right down")
            probe.send("button right up")
            mm, when = serial.expect(r"WISP-MOUSE-EV type=1 code=272 value=1", 10, since)
            serial.expect(r"WISP-MOUSE-EV type=1 code=273 value=1|mousetest: ", 10, since)
            text = serial.text(since)
            ev = [(int(t), int(c), int(v)) for t, c, v in
                  re.findall(r"WISP-MOUSE-EV type=(\d+) code=(\d+) value=(-?\d+)", text)]
            left = (1, 272, 1) in ev
            right = (1, 273, 1) in ev
            dx = sum(v for t, c, v in ev if t == 2 and c == 0)
            dy = sum(v for t, c, v in ev if t == 2 and c == 1)
            blat = (when - sent[1]) * 1000 if mm and sent else None
            dev = m.group(0).strip() if m else "no mousetest device"
            result("mouse", left and right and (dx, dy) == (70, 30),
                   f"{dev}; relative motion X {dx:+d}, Y {dy:+d} (client: position, move 10 0,"
                   f" position +60,+30: +70, +30); left {'yes' if left else 'no'}, right"
                   f" {'yes' if right else 'no'}"
                   + (f"; left button client -> guest's serial line {blat:.1f} ms" if blat is not None else ""))

        if "sound" not in skip:
            n = probe.nevents()
            m, _, t_cmd = serial.command(f"soundtest 440 {args.sound_ms}", r"WISP-SOUND[^\n]*\n",
                                         30 + args.sound_ms / 1000 * 3)
            onset = probe.wait_event("audio-onset", 1, n)
            time.sleep(1.0)
            probe.close()
            # the probe prints it as it stops; its reader thread may still be on the way there
            ahead = None
            deadline = time.time() + 3
            while ahead is None and time.time() < deadline:
                with probe.lock:
                    # in the probe's last line (done ...), which a library's log may precede
                    ahead = next((float(m.group(1)) for e in probe.events
                                  for m in [re.search(r"audio-ahead=([0-9.]+)", f"{e[0]} {e[2]}")] if m), None)
                time.sleep(0.05)
            try:
                rate, channels, samples = read_wav(f"{out}/sound.wav")
                want = args.sound_ms / 1000
                secs, hz, dropouts = tone(samples, rate, want)
                # the whole tone without a dropout (quiet 10 ms windows inside it), the audio steady
                result("sound", abs(hz - 440) < 440 * 0.01 and want * 0.9 < secs < want * 1.15
                       and dropouts == 0 and ahead is not None and ahead <= AHEAD_MS,
                       f"{secs:.2f} s of sound at {hz:.1f} Hz in the client's decoded audio ({rate} Hz,"
                       f" {channels} channels, {dropouts} dropouts); the most audio at once"
                       f" {'%.0f ms' % ahead if ahead is not None else 'unknown'} (at most {AHEAD_MS});"
                       f" guest {m.group(0).strip() if m else 'no result'};"
                       + (f" soundtest typed -> first loud packet at the client {(onset[1] - t_cmd) * 1000:.0f} ms"
                          if onset and t_cmd else " no onset seen"))
            except (OSError, ValueError, struct.error, TypeError) as e:
                result("sound", False, f"the client's WAV: {e}")
    finally:
        if probe.proc.poll() is None:
            probe.close()
    return finish(out)


def finish(out):
    with open(f"{out}/summary.txt", "a") as f:
        for n, ok, detail in RESULTS:
            f.write(f"{'PASS' if ok else 'FAIL'} {NAME}: {n}: {detail}\n")
    return 0 if RESULTS and all(ok for _, ok, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
