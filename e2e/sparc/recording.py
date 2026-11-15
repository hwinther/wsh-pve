#!/usr/bin/env python3
"""Recordings of a lab run: the serial console as an asciinema cast, the framebuffer as a video.

- `CastWriter` writes what the guest prints on the serial console, as the lab receives it, to an
  asciinema v2 cast (`serial.cast`): a JSON header, then one `[time, "o", text]` event per read and a
  `[time, "m", label]` marker per lab step, which the asciinema player shows as chapters.
- `compress_cast()` writes a viewing copy with the idle gaps capped and sped up (`serial.fast.cast`).
- `FbRecorder` keeps a framebuffer frame every few seconds from the lab's display refresh and encodes
  the changed ones, time-compressed, into `fb.webm` (VP9, with `vpxenc`) with the steps as WebVTT
  cues (`fb.vtt`).
- `report_html()` is the recordings section of the run's index.html: the cast in a copy of the
  asciinema player next to it (works offline, opened from disk) and the video.

    recording.py fetch-player DIR     the pinned asciinema player into DIR (the lab images do this)
"""
import base64
import codecs
import hashlib
import html
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

# asciinema-player (Apache-2.0, https://github.com/asciinema/asciinema-player): the bundle from npm,
# checked against the registry's integrity hash. The lab images put it in PLAYER_DIR.
PLAYER_VERSION = "3.17.0"
PLAYER_INTEGRITY = "sha512-JbjNJmA2TLIeYNaOEja+kVSzXadKoqpIzVVmfBGNj2DmdtE/vExBCnkE8NYEcpaQcDvUYg8Ltt0urT80frACmw=="
PLAYER_FILES = ("asciinema-player.min.js", "asciinema-player.css")
PLAYER_DIR = os.environ.get("LAB_ASCIINEMA_PLAYER", "/usr/share/asciinema-player")

CAST_MAX = int(os.environ.get("LAB_CAST_MAX", 32 << 20))  # bytes of console output per cast


def _latin1(err):
    """Bytes that aren't UTF-8 become the Latin-1 character of the same value (as pyte reads them)."""
    return err.object[err.start:err.end].decode("latin-1"), err.end


codecs.register_error("lab-latin1", _latin1)


class CastWriter:
    """An asciinema v2 cast of the serial console.

    The console isn't guaranteed UTF-8 (OpenBIOS and Solaris print ASCII and control sequences, other
    guests UTF-8), so the bytes go through an incremental UTF-8 decoder (a character split between two
    reads is kept for the next one) that turns any byte that isn't part of valid UTF-8 into the
    Latin-1 character of that value: valid JSON either way, UTF-8 output plays as such, and 8-bit
    output looks as it does to the lab's terminal emulator. Times are seconds since the run started
    (as in steps.log), monotonic. After `limit` bytes of output the cast stops with a marker saying
    so; serial.raw keeps everything."""

    def __init__(self, path, cols, rows, t0, init="", limit=CAST_MAX, title=None):
        self.path, self.limit = path, limit
        self.lock = threading.Lock()
        self.f = open(path, "w", encoding="utf-8", newline="\n")
        self.dec = codecs.getincrementaldecoder("utf-8")("lab-latin1")
        self.offset, self.mono0 = time.time() - t0, time.monotonic()
        self.last, self.size, self.events, self.truncated, self.closed = 0.0, 0, 0, False, False
        header = {"version": 2, "width": cols, "height": rows, "timestamp": int(t0),
                  "env": {"TERM": "vt100"}}
        if title:
            header["title"] = title
        self.f.write(json.dumps(header) + "\n")
        if init:  # terminal set-up the lab's emulator assumes (not output of the guest)
            self._event(0.0, "o", init)
        self.f.flush()

    def _now(self):
        self.last = max(self.last, round(self.offset + time.monotonic() - self.mono0, 6))
        return self.last

    def _event(self, t, kind, data):
        self.f.write(json.dumps([t, kind, data], ensure_ascii=False) + "\n")
        self.events += 1

    def output(self, data):
        with self.lock:
            if self.closed or self.truncated:
                return
            text = self.dec.decode(data)
            if not text:
                return
            self.size += len(data)
            self._event(self._now(), "o", text)
            if self.size > self.limit:
                self.truncated = True
                self._event(self.last, "m", f"cast stops here: {self.limit} bytes of output (serial.raw has all)")
            self.f.flush()

    def marker(self, label):
        with self.lock:
            if not self.closed:
                self._event(self._now(), "m", label)
                self.f.flush()

    def close(self):
        with self.lock:
            if not self.closed:
                rest = self.dec.decode(b"", final=True)
                if rest and not self.truncated:
                    self._event(self._now(), "o", rest)
                self.closed = True
                self.f.close()


def read_cast(path):
    with open(path, encoding="utf-8") as f:
        header = json.loads(f.readline())
        events = [json.loads(line) for line in f if line.strip()]
    return header, events


def check_cast(path):
    """Problems with a cast file as a list of strings (empty: fine): every line JSON, a v2 header,
    events [time, "o"|"m"|"i"|"r", str] with times that never go back."""
    problems = []
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        header = json.loads(lines[0])
        if header.get("version") != 2 or not header.get("width") or not header.get("height"):
            problems.append(f"header: {lines[0][:200]}")
    except ValueError as e:
        return [f"line 1: {e}"]
    last = 0.0
    for n, line in enumerate(lines[1:], 2):
        if not line:
            continue
        try:
            t, kind, data = json.loads(line)
        except ValueError as e:
            problems.append(f"line {n}: {e}")
            continue
        if kind not in ("o", "m", "i", "r") or not isinstance(data, str) or not isinstance(t, (int, float)):
            problems.append(f"line {n}: not an event: {line[:120]}")
        elif t < last:
            problems.append(f"line {n}: time {t} before {last}")
        last = max(last, t if isinstance(t, (int, float)) else last)
    return problems


def compress_cast(src, dst, max_idle=2.0, speed=1.0):
    """Write a copy of the cast with every pause longer than `max_idle` seconds cut to `max_idle`
    (asciinema's idle time limit), and all times divided by `speed`. Returns the durations."""
    header, events = read_cast(src)
    out, prev, t2 = [], 0.0, 0.0
    for t, kind, data in events:
        t2 += min(t - prev, max_idle) / speed
        prev = t
        if kind == "o" and out and out[-1][1] == "o" and t2 - out[-1][0] < 0.02:
            out[-1][2] += data  # the console arrives a few bytes per read: one event per 20 ms is enough
        else:
            out.append([round(t2, 6), kind, data])
    header = {**header, "title": f"{header.get('title') or 'sparc lab'} (pauses cut to {max_idle:g}s"
              + (f", {speed:g}x" if speed != 1 else "") + ")"}
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(header) + "\n")
        for e in out:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    steps = {}  # step number -> time of its marker ("<n>. <title>") in the copy
    for t, kind, data in out:
        if kind == "m" and data.split(". ", 1)[0].isdigit():
            steps.setdefault(data.split(". ", 1)[0], t)
    return {"seconds": round(events[-1][0], 1) if events else 0.0, "fast_seconds": round(t2, 1), "steps": steps}


def replay(path, until_markers=False):
    """Play a cast through pyte, set up as the lab's terminal. Yields (marker label, screen text) at
    each marker with until_markers, and finally (None, screen text) at the end."""
    import pyte

    header, events = read_cast(path)
    screen = pyte.Screen(header["width"], header["height"])
    stream = pyte.Stream(screen)
    stream.use_utf8 = False  # as lab.Machine's select_other_charset("@"): charsets and SO/SI work

    def text():
        return "\n".join(line.rstrip() for line in screen.display)

    for _, kind, data in events:
        if kind == "o":
            stream.feed(data)
        elif kind == "m" and until_markers:
            yield data, text()
    yield None, text()


def check_steps(run_dir, cast="serial.cast"):
    """Replay the cast and compare the screen at each step marker ("<n>. <title>") with the lab's
    own NNN-ttya.txt. Returns (steps compared, list of the ones that differ)."""
    compared, differ = 0, []
    for label, screen in replay(os.path.join(run_dir, cast), until_markers=True):
        if not label or ". " not in label or not label.split(". ", 1)[0].isdigit():
            continue
        txt = os.path.join(run_dir, f"{int(label.split('. ', 1)[0]):03d}-ttya.txt")
        if not os.path.exists(txt):
            continue
        compared += 1
        with open(txt, encoding="utf-8") as f:
            if f.read().rstrip("\n") != screen.rstrip("\n"):
                differ.append(label)
    return compared, differ


# --- framebuffer video ---------------------------------------------------------------------------

class FbRecorder:
    """Frames from the lab's display refresh (each screendump the refresh loop makes is offered), at
    most one per `interval` seconds, scaled to at most `max_width`, kept only when they differ from
    the previous one. finish() encodes them into a WebM, time-compressed: each frame is shown for its
    real duration divided by `speed`, at least one video frame and at most `max_hold` seconds."""

    def __init__(self, out, elapsed, interval=1.0, max_width=1024):
        self.out, self.elapsed, self.interval, self.max_width = out, elapsed, interval, max_width
        self.dir = os.path.join(out, "_frames")
        os.makedirs(self.dir, exist_ok=True)
        self.frames, self.marks = [], []  # (t, png), (t, title)
        self.prev, self.next_t, self.offered, self.cpu = None, 0.0, 0, 0.0
        self.lock = threading.Lock()

    def offer(self, path):
        t = self.elapsed()
        if t < self.next_t:
            return
        c0 = time.process_time()
        from PIL import Image, ImageChops

        with self.lock:
            self.next_t = t + self.interval * 0.95
            self.offered += 1
            img = Image.open(path).convert("RGB")
            if img.width > self.max_width:
                img = img.resize((self.max_width, round(img.height * self.max_width / img.width)), Image.BILINEAR)
            if self.prev is None or img.size != self.prev.size or ImageChops.difference(img, self.prev).getbbox():
                png = os.path.join(self.dir, f"{len(self.frames):06d}.png")
                img.save(png, compress_level=1)
                self.frames.append((t, png))
                self.prev = img
        self.cpu += time.process_time() - c0

    def mark(self, title):
        self.marks.append((self.elapsed(), title))

    def finish(self, webm, fps=10, speed=10.0, max_hold=2.0):
        """Encode the frames; returns a dict for result.json (or with "error"). Removes the frames."""
        try:
            return self._encode(webm, fps, speed, max_hold)
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)

    def _encode(self, webm, fps, speed, max_hold):
        from PIL import Image

        if not self.frames:
            return {"error": "no frames"}
        end = self.elapsed()
        # how many video frames each captured frame gets
        counts = []
        for i, (t, _) in enumerate(self.frames):
            t_next = self.frames[i + 1][0] if i + 1 < len(self.frames) else max(end, t + self.interval)
            counts.append(max(1, round(min((t_next - t) / speed, max_hold) * fps)))
        w, h = Image.open(self.frames[0][1]).size
        w, h = w - w % 2, h - h % 2
        if not shutil.which("vpxenc"):
            return {"error": "vpxenc not found (Debian: vpx-tools)"}
        c0 = time.time()
        # one pass (two would read the input twice, and stdin can't be rewound)
        cmd = ["vpxenc", "--codec=vp9", "--passes=1", "--good", "--cpu-used=5", "--end-usage=q", "--cq-level=36",
               "--threads=2", "--kf-max-dist=" + str(fps * 5), "--auto-alt-ref=0", "-q", "-o", webm, "-"]
        enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        enc.stdin.write(f"YUV4MPEG2 W{w} H{h} F{fps}:1 Ip A1:1 C420jpeg XCOLORRANGE=LIMITED\n".encode())
        y_lut = [16 + round(v * 219 / 255) for v in range(256)]
        c_lut = [16 + round(v * 224 / 255) for v in range(256)]
        for (_, png), n in zip(self.frames, counts):
            img = Image.open(png).convert("RGB")
            if img.size != (w, h):  # resolution change (the guest set another mode) or odd size
                canvas = Image.new("RGB", (w, h))
                img.thumbnail((w, h))
                canvas.paste(img)
                img = canvas
            y, cb, cr = img.convert("YCbCr").split()
            half = (w // 2, h // 2)
            frame = (b"FRAME\n" + y.point(y_lut).tobytes() + cb.resize(half, Image.BOX).point(c_lut).tobytes()
                     + cr.resize(half, Image.BOX).point(c_lut).tobytes())
            for _ in range(n):
                enc.stdin.write(frame)
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        if enc.wait() or os.path.getsize(webm) < 1024:
            return {"error": f"vpxenc exited with {enc.returncode}, {os.path.getsize(webm)} bytes: "
                             f"{err.strip()[-500:]}"}
        # the steps as WebVTT cues, on the video's time line
        starts, acc = [], 0.0
        for n in counts:
            starts.append(acc)
            acc += n / fps

        def video_time(t):
            i = max([k for k, (ft, _) in enumerate(self.frames) if ft <= t] or [0])
            return min(starts[i] + max(0.0, t - self.frames[i][0]) / speed, starts[i] + counts[i] / fps)

        cues = [(video_time(t), title) for t, title in self.marks]
        vtt = os.path.splitext(webm)[0] + ".vtt"
        with open(vtt, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n")
            for k, (start, title) in enumerate(cues):
                # shown for three seconds (or until the next step), as a caption over the video
                stop = min(start + 3.0, max(start + 0.5, cues[k + 1][0] if k + 1 < len(cues) else acc))
                f.write(f"\n{_vtt_time(start)} --> {_vtt_time(stop)}\n{title}\n")
        return {"video": os.path.basename(webm), "captions": os.path.basename(vtt), "seconds": round(acc, 1),
                "size": [w, h], "frames_captured": len(self.frames), "frames_offered": self.offered,
                "video_frames": sum(counts), "bytes": os.path.getsize(webm), "fps": fps, "speed": speed,
                "capture_cpu_s": round(self.cpu, 2), "encode_s": round(time.time() - c0, 1),
                "cues": [round(c[0], 2) for c in cues]}


def _vtt_time(s):
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


# --- the run's index.html ------------------------------------------------------------------------

def copy_player(out):
    """Copy the asciinema player next to the run's index.html; False when it isn't installed."""
    if not all(os.path.exists(os.path.join(PLAYER_DIR, f)) for f in PLAYER_FILES):
        return False
    for f in PLAYER_FILES:
        shutil.copy(os.path.join(PLAYER_DIR, f), os.path.join(out, f))
    return True


def report_html(out, rec):
    """The recordings section of index.html, from the "recordings" entry of result.json. The cast is
    inlined (a page opened from disk can't fetch files next to it); the player is a local copy."""
    parts = []
    cast = rec.get("cast_fast") or rec.get("cast")
    if cast and rec.get("cast_bytes"):
        with open(os.path.join(out, cast), encoding="utf-8") as f:
            data = json.dumps(f.read()).replace("</", "<\\/")
        about = (f"serial console, {rec['cast_seconds']:.0f}s; pauses cut to {rec['max_idle']:g}s and "
                 f"{rec.get('speed', 1):g}x: {rec['fast_seconds']:.0f}s" if rec.get("cast_fast") else "serial console")
        links = " ".join(f'<a href="{html.escape(rec[k])}">{html.escape(rec[k])}</a>'
                         for k in ("cast", "cast_fast") if rec.get(k))
        if rec.get("player"):
            parts.append(
                f'<section id=rec><h2>Recording <small>{html.escape(about)}</small></h2>'
                '<div id=cast style="max-width:820px"></div>'
                f'<p>{links} (<code>asciinema play</code>, or any asciinema player)</p></section>'
                '<link rel=stylesheet href="asciinema-player.css"><script src="asciinema-player.min.js"></script>'
                f'<script>const castPlayer = AsciinemaPlayer.create({{data: {data}}}, document.getElementById("cast"),'
                ' {fit: "width", terminalFontSize: "14px", poster: "npt:0:1"});'
                ' function seekCast(t) { castPlayer.seek(t); castPlayer.play();'
                ' document.getElementById("rec").scrollIntoView(); }</script>')
        else:
            parts.append(f"<section id=rec><h2>Recording <small>{html.escape(about)}</small></h2>"
                         f"<p>{links}: play with <code>asciinema play</code> (the asciinema player isn't "
                         "installed where this run was made)</p></section>")
    fb = rec.get("fb") or {}
    if fb.get("video"):
        parts.append(
            f'<section id=fbrec><h2>Framebuffer <small>{fb["size"][0]}x{fb["size"][1]}, '
            f'{fb["frames_captured"]} distinct frames, {fb["seconds"]:.0f}s at {fb["speed"]:g}x</small></h2>'
            f'<video id=fbvideo controls preload=metadata src="{fb["video"]}" style="max-width:100%;width:1024px">'
            f'<track kind=captions label=Steps src="{fb["captions"]}" default></video>'
            '<script>function seekVideo(t) { const v = document.getElementById("fbvideo"); v.currentTime = t;'
            ' v.play(); document.getElementById("fbrec").scrollIntoView(); }</script></section>')
    elif fb.get("error"):
        parts.append(f"<p>Framebuffer video: {html.escape(fb['error'])}</p>")
    return "".join(parts)


def step_links(rec, n):
    """Links that play the recordings from step n (its marker in the cast, its cue in the video)."""
    links = []
    markers = rec.get("cast_markers") or {}
    if rec.get("player") and str(n) in markers:
        links.append(f'<a href="#rec" onclick="seekCast({markers[str(n)]});return false">play console from here</a>')
    cues = (rec.get("fb") or {}).get("cues") or []
    if (rec.get("fb") or {}).get("video") and n - 1 < len(cues):
        links.append(f'<a href="#fbrec" onclick="seekVideo({cues[n - 1]});return false">play video from here</a>')
    return " ".join(links)


# --- the player for the images -------------------------------------------------------------------

def fetch_player(dest):
    """Download the pinned asciinema player from npm, check it and unpack its bundle into dest."""
    url = f"https://registry.npmjs.org/asciinema-player/-/asciinema-player-{PLAYER_VERSION}.tgz"
    data = urllib.request.urlopen(url, timeout=60).read()
    algo, want = PLAYER_INTEGRITY.split("-", 1)
    got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if got != want:
        raise SystemExit(f"{url}: {algo} {got}, expected {want}")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for name in (*(f"package/dist/bundle/{f}" for f in PLAYER_FILES), "package/LICENSE"):
            with open(os.path.join(dest, os.path.basename(name)), "wb") as f:
                f.write(tar.extractfile(name).read())
    print(f"asciinema-player {PLAYER_VERSION} in {dest}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "fetch-player":
        fetch_player(sys.argv[2])
    else:
        sys.exit(__doc__)
