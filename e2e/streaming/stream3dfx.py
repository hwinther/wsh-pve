#!/usr/bin/env python3
"""A Moonlight session to Wolf with a Windows 98 guest drawing through Glide (qemu-3dfx): the
client side of stage 3f, run on a node next to a VM from `qm start` (see the display reference,
"Streaming to Moonlight", "A Windows 98 guest with Glide").

The guest runs w3dstrm.exe (e2e/3dfx/win98/w3dstrm.c) from its StartUp folder: it takes commands
on COM1 and answers there; in its Glide window it animates at --guest-fps and writes each frame's
number into eight cells across the bottom of the picture, where wsh-moonlight-probe reads its eight
points, and reports every swap on COM1 (F <frame> <ms>). So every decoded frame at the client says
which guest frame it shows, and the serial line says when the guest swapped it. Checks, each a
PASS/FAIL line in OUTDIR/summary.txt:

  stream    the session starts and frames arrive
  glide     w3dstrm opens its Glide window (Glide 2, or 3 with --api glide3) and swaps frames
  picture   a still frame decoded at the client against QEMU's screendump (scaled to the client's
            size: Wolf scales the guest's 640x480 to it)
  latency   guest swap (its F line on the serial line) -> the first decoded frame that shows that
            frame number, for every guest frame that reached the client during --secs seconds
  pacing    the same seconds: guest frames per second, frames per second at the client, how many
            of them show a new guest frame, the spread of the intervals between new ones, and how
            many guest frames were skipped between them
  input     B held down at the client shows colour bars instead of the number: from the client's
            key press to the guest program's WM_KEYDOWN (serial line) and to the first decoded
            frame with the bars (input to picture); ROUNDS samples
  keyboard  keys A, B, Z from the client as Windows virtual keys 65, 66, 90 (scan codes 30, 48,
            44) in the guest program's window
  mouse     positions, relative motion and the left and right buttons from the client in the
            program's window (WM_MOUSEMOVE, WM_xBUTTONDOWN): reported as they arrive
  sound     `tone 440 MS` (WinMM waveOut in the guest) in the client's decoded audio: 440 Hz, the
            length, no dropout, the most audio at once; and from the command to the first loud
            packet at the client
  demo      (--demo) WSHDEMO.EXE and WSHSPACE.EXE (e2e/3dfx/demo, e2e/3dfx/space) run by w3dstrm
            for a while each: their frame rate in the guest (their FPS lines) against the new
            pictures per second at the client

Every latency sample is in OUTDIR/latency.txt, every frame of the paced seconds in pacing.txt.
--skip takes check names (comma-separated); --skip glide leaves out the Glide window and every
check that needs it (picture to demo), for a guest without qemu-3dfx's drivers: stream and sound.

usage: stream3dfx.py --node HOST --keydir DIR --app NAME --outdir DIR --serial ADDR --qmp ADDR
                     [--probe-prefix CMD --probe-outdir DIR] [--shared DIR] [--api glide2|glide3]
                     [--guest-fps N] [--secs S] [--rounds N] [--demo] [--name NAME] [--skip CHECKS]

It imports stream3d.py (the same directory) for the serial line, QMP, the probe and the analysis.
"""

import argparse
import os
import re
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stream3d  # noqa: E402
from stream3d import Probe, Serial, compare, is_bars, qmp, read_ppm, read_wav, result, stats, tone  # noqa: E402

F_RE = re.compile(r"STRM: F (\d+) (\d+) ([pb])\r?\n")


def number_of(colours):
    """the frame number's low 8 bits from the eight bottom points (white 1, black 0), or None when a
    point is neither (the bars, a frame in between, the desktop)"""
    v = 0
    for r, g, b in colours:
        lo, hi = max(r, g, b) < 70, min(r, g, b) > 185
        if not (lo or hi):
            return None
        v = v * 2 + hi
    return v


def scale(src, w, h, dw, dh):
    """nearest-neighbour scaling of an RGB picture"""
    out = bytearray(dw * dh * 3)
    xs = [min(w - 1, (x * w) // dw) * 3 for x in range(dw)]
    for y in range(dh):
        row = min(h - 1, (y * h) // dh) * w * 3
        o = y * dw * 3
        for x in range(dw):
            s = row + xs[x]
            out[o:o + 3] = src[s:s + 3]
            o += 3
    return bytes(out)


def known_frame(n):
    """w3dstrm's 640x480 picture of frame n without the bars, as RGB565 gives it back: the dark
    blue clear, the white bar at x = 8 n mod 608, the grey line above the cells, the cells"""
    clear, white, grey, black = (0, 0, 132), (255, 255, 255), (99, 97, 99), (0, 0, 0)
    w, h = 640, 480
    rows = []
    x0 = (n * 8) % 608
    top = bytes(clear * x0 + white * 32 + clear * (w - x0 - 32))
    rows += [top] * 428
    rows += [bytes(grey * w)] * 4
    cells = b"".join(bytes((white if (n >> (7 - i)) & 1 else black) * 80) for i in range(8))
    rows += [cells] * 48
    return w, h, b"".join(rows)


def f_lines(serial, since):
    """(frame, guest ms, bars, arrival time) of each F line after a mark"""
    text = serial.text(since)
    return [(int(m.group(1)), int(m.group(2)), m.group(3) == "b", serial.time_at(since + m.end() - 1))
            for m in F_RE.finditer(text)]


def tap(address, secs, path):
    """--tap-child: a second listener on the VM's console (qemudbussrc scaled to 8x10 grey pixels,
    one per cell in the bottom row) that writes when each guest frame number reached it, so the
    latency splits into QEMU and the D-Bus display (guest swap -> qemudbussrc) and the rest (Wolf,
    the encoder, the client). Runs in the streaming container, next to Wolf's own listener."""
    import subprocess
    p = subprocess.Popen(["gst-launch-1.0", "-q", "qemudbussrc", f"address={address}", "!", "videoconvert", "!",
                          "videoscale", "!", "video/x-raw,format=GRAY8,width=8,height=10", "!", "fdsink", "fd=1"],
                         stdout=subprocess.PIPE)
    end = time.time() + secs
    with open(path, "w") as f:
        while time.time() < end:
            data = p.stdout.read(80)
            if len(data) < 80:
                break
            t = time.time()
            row = data[72:80]
            v = 0
            ok = True
            for c in row:
                if 70 <= c <= 185:
                    ok = False
                v = v * 2 + (c > 128)
            f.write(f"{t:.6f} {v if ok else '-'}\n")
    p.kill()
    return 0


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--tap-child":
        return tap(sys.argv[2], float(sys.argv[3]), sys.argv[4])
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--qmp", required=True)
    ap.add_argument("--probe-prefix", default="")
    ap.add_argument("--probe-outdir", default="")
    ap.add_argument("--keydir", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--api", choices=("glide2", "glide3"), default="glide2")
    ap.add_argument("--guest-fps", type=int, default=60)
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--sound-ms", type=int, default=2000)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--skip", default="")
    ap.add_argument("--enter-after", type=int, default=0,
                    help="while w3dstrm doesn't answer, press Enter in the guest (QMP send-key) after this"
                    " many seconds and every 20 s after (a network logon dialog or a new-hardware wizard;"
                    " 0: never)")
    ap.add_argument("--shared", default="/shared")
    ap.add_argument("--tap-address", default="",
                    help="the VM's bus as the container sees it: a second listener during the latency"
                    " seconds splits the latency at qemudbussrc (a diagnostic; it adds a listener)")
    ap.add_argument("--tap-script", default="/usr/local/bin/stream3dfx.py",
                    help="this script in the container (for --tap-address)")
    args = ap.parse_args()
    skip = set(filter(None, args.skip.split(",")))
    stream3d.NAME = args.name
    out = args.outdir
    os.makedirs(out, exist_ok=True)

    serial = Serial(args.serial, f"{out}/serial.log")
    # w3dstrm answers once Windows is up and it has COM1 (lines sent before are lost)
    start = time.time()
    deadline = start + 300
    ready = None
    enter = start + args.enter_after if args.enter_after else None
    while time.time() < deadline and not ready:
        mark = serial.mark()
        serial.send("ping")
        ready, _ = serial.expect(r"STRM: PONG", 2, mark)
        if not ready and enter and time.time() > enter:
            qmp(args.qmp, "send-key", keys=[{"type": "qcode", "data": "ret"}])
            enter = time.time() + 20
    if not ready:
        result("guest", False, "w3dstrm didn't answer on COM1 within 300 s (serial.log)")
        return stream3d.finish(out)

    probe_out = args.probe_outdir or out
    probe = Probe([*args.probe_prefix.split(), "wsh-moonlight-probe", "--width", str(args.width),
                   "--height", str(args.height), "--fps", str(args.fps), args.node, args.keydir, args.app,
                   probe_out], f"{out}/probe.log")
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
               f"session started; first frame {first[6]} {first[2] - conn[1]:.2f} s after the connection"
               if conn and first else f"no {'frame' if conn else 'connection'} (see probe.log)")
        if not (conn and first):
            return stream3d.finish(out)

        # --skip glide: no Glide window (a guest without qemu-3dfx's drivers), so none of the checks that need it
        if "glide" not in skip:
            mark = serial.mark()
            cmd = "glide3" if args.api == "glide3" else "glide"
            serial.send(f"{cmd} fps={args.guest_fps}")
            m, _ = serial.expect(r"STRM: GLIDE open[^\n]*\n|STRM: ERROR[^\n]*\n", 60, mark)
            time.sleep(2)
            ok = bool(m and "GLIDE open" in m.group(0)) and len(f_lines(serial, mark)) > 30
            result("glide", ok, (m.group(0).strip() if m else "no answer") + f"; {len(f_lines(serial, mark))} swaps"
                   " in the first 2 s")
            if not ok:
                return stream3d.finish(out)
            # the number must reach the client before the measurements
            deadline = time.time() + 20
            while time.time() < deadline:
                fs = probe.frames_since(time.time() - 0.3)
                if fs and number_of(fs[-1][8]) is not None:
                    break
                time.sleep(0.05)

            if "picture" not in skip:
                mark = serial.mark()
                serial.send("still")
                time.sleep(1.5)  # the encoder refines a still picture for a few frames
                dump = f"{args.shared}/screendump.ppm"
                try:
                    os.unlink(dump)
                except OSError:
                    pass
                # QEMU's screendump has no surface while a GL console scans a dmabuf out (and no VNC
                # client makes QEMU read it back), so the reference is also the frame w3dstrm draws
                try:
                    qmp(args.qmp, "screendump", filename=dump)
                    dumped = "ok"
                except RuntimeError as e:
                    dumped = str(e)
                n = probe.nevents()
                probe.send(f"snap {probe_out}/frame.ppm")
                snap = probe.wait_event("snap", 10, n)
                ok, detail = False, "no comparison"
                for _ in range(20 if dumped == "ok" else 0):
                    if os.path.exists(dump) and os.path.getsize(dump) > 0:
                        break
                    time.sleep(0.1)
                try:
                    last = f_lines(serial, mark)
                    w2, h2, got = read_ppm(f"{out}/frame.ppm")
                    shown = number_of(probe.frames_since(time.time() - 0.2)[-1][8])
                    w, h, ref = known_frame(last[-1][0])
                    mean, share = compare(scale(ref, w, h, w2, h2), got, w2, h2)
                    # scaled twice (Wolf's filter, our nearest neighbour) and 4:2:0: edges differ
                    ok = mean < 6 and share < 0.05 and shown == last[-1][0] & 255
                    detail = (f"against the frame w3dstrm drew ({w}x{h}, scaled to the client's {w2}x{h2}): mean"
                              f" difference {mean:.2f}/255, {share * 100:.2f}% of pixels off by more than 48; the"
                              f" client's cells read frame {shown}, the guest's last swap {last[-1][0] & 255}")
                    if dumped == "ok":
                        w, h, ref = read_ppm(dump)
                        mean, share = compare(scale(ref, w, h, w2, h2), got, w2, h2)
                        ok = ok and mean < 6 and share < 0.05
                        detail += (f"; against QEMU's screendump ({w}x{h}): mean difference {mean:.2f}/255,"
                                   f" {share * 100:.2f}% off by more than 48")
                    else:
                        detail += f"; QEMU's screendump: {dumped}"
                except (OSError, ValueError, IndexError) as e:
                    detail = f"no comparison: {e} (snap {snap})"
                result("picture", ok, detail)
                serial.send("move")
                time.sleep(1)

            if "latency" not in skip or "pacing" not in skip:
                mark = serial.mark()
                tapper = None
                if args.tap_address:
                    import subprocess
                    tapper = subprocess.Popen([*args.probe_prefix.split(), "python3", args.tap_script, "--tap-child",
                                               args.tap_address, str(args.secs + 1), f"{probe_out}/tap.txt"])
                    time.sleep(1)
                t0 = time.time()
                time.sleep(args.secs)
                t1 = time.time()
                if tapper:
                    tapper.wait(30)
                lines = f_lines(serial, mark)
                frames = [f for f in probe.frames_since(t0) if f[2] <= t1 + 1]
                seen = {}  # guest frame -> (first client frame, latency)
                rows = ["# guest frame, guest swap reported (serial line, s), frame complete at the client, decoded, latency ms"]
                pac = ["# client frame complete (s), decoded, changed (per mille), guest frame (low 8 bits or -)"]
                undecoded = 0
                for f in frames:
                    v = number_of(f[8])
                    pac.append(f"{f[1]:.6f} {f[2]:.6f} {f[7]} {v if v is not None else '-'}")
                    if v is None:
                        undecoded += 1
                        continue
                    # the newest swap of a frame with these low bits before the decode
                    cand = [ln for ln in lines if ln[0] & 255 == v and ln[3] is not None and ln[3] <= f[2]
                            and f[2] - ln[3] < 2.0]
                    if not cand:
                        continue
                    g = max(cand, key=lambda ln: ln[3])
                    if g[0] not in seen:
                        seen[g[0]] = (f, (f[2] - g[3]) * 1000)
                        rows.append(f"{g[0]} {g[3]:.6f} {f[1]:.6f} {f[2]:.6f} {(f[2] - g[3]) * 1000:.1f}")
                lat = [v[1] for v in seen.values()]
                # with the tap: when each guest frame first reached qemudbussrc
                tap_at = {}
                if args.tap_address:
                    try:
                        for row in open(f"{out}/tap.txt"):
                            t, v = row.split()
                            if v != "-":
                                tap_at.setdefault(int(v), []).append(float(t))
                    except OSError:
                        pass
                split_q, split_w = [], []
                for g, (f, _) in seen.items():
                    sw = next(ln[3] for ln in lines if ln[0] == g)
                    ts = [t for t in tap_at.get(g & 255, []) if sw <= t <= f[2]]
                    if ts:
                        split_q.append((ts[0] - sw) * 1000)
                        split_w.append((f[2] - ts[0]) * 1000)
                span = (lines[-1][3] - lines[0][3]) if len(lines) > 1 else 0
                gfps = (len(lines) - 1) / span if span > 0 else 0
                cspan = frames[-1][1] - frames[0][1] if len(frames) > 1 else 0
                cfps = (len(frames) - 1) / cspan if cspan > 0 else 0
                order = sorted(seen.items(), key=lambda kv: kv[1][0][1])
                new_t = [v[0][1] for _, v in order]
                niv = [(b - a) * 1000 for a, b in zip(new_t, new_t[1:])]
                gaps = [b[0] - a[0] for a, b in zip(order, order[1:])]
                civ = [(b[1] - a[1]) * 1000 for a, b in zip(frames, frames[1:])]
                if "latency" not in skip:
                    result("latency", len(lat) >= 20,
                           f"guest swap (serial line) -> decoded at the client, ms: {stats(lat)}"
                           f" ({len(lat)} guest frames over {args.secs:.0f} s)"
                           + (f"; split at a second listener (qemudbussrc): guest swap -> qemudbussrc {stats(split_q)},"
                              f" qemudbussrc -> decoded at the client {stats(split_w)}" if args.tap_address else ""))
                if "pacing" not in skip:
                    gap_hist = {}
                    for gp in gaps:
                        gap_hist[gp] = gap_hist.get(gp, 0) + 1
                    result("pacing", cfps > 30 and len(seen) > 0,
                           f"guest {gfps:.1f} swaps/s; client {cfps:.1f} frames/s (intervals ms: {stats(civ)}, stdev"
                           f" {statistics.pstdev(civ) if civ else 0:.1f}), {len(seen) / cspan if cspan else 0:.1f}/s with a"
                           f" new guest frame (intervals ms: {stats(niv)}, stdev {statistics.pstdev(niv) if niv else 0:.1f});"
                           f" guest frames advanced between new pictures: "
                           + ", ".join(f"{k}: {gap_hist[k]}x" for k in sorted(gap_hist)[:8])
                           + f"; {undecoded} client frames without a readable number")
                with open(f"{out}/latency.txt", "w") as fh:
                    fh.write("\n".join(rows) + "\n")
                with open(f"{out}/pacing.txt", "w") as fh:
                    fh.write("\n".join(pac) + "\n")

            if "input" not in skip:
                to_guest, to_pic = [], []
                for _ in range(args.rounds):
                    mark = serial.mark()
                    n = probe.nevents()
                    probe.send("key 0x42 down")
                    sent = probe.wait_event("sent", 5, n)
                    m, when = serial.expect(r"STRM: KEY vk=66 scan=\d+ down", 5, mark)
                    deadline = time.time() + 5
                    shown = None
                    while sent and time.time() < deadline and not shown:
                        shown = next((f for f in probe.frames_since(sent[1]) if is_bars(f[8])), None)
                        time.sleep(0.005)
                    if sent and m:
                        to_guest.append((when - sent[1]) * 1000)
                    if sent and shown:
                        to_pic.append((shown[2] - sent[1]) * 1000)
                    probe.send("key 0x42 up")
                    time.sleep(0.4)
                result("input", len(to_pic) >= args.rounds // 2,
                       f"key B held: client send -> the program's WM_KEYDOWN (serial line), ms: {stats(to_guest)};"
                       f" client send -> the first decoded frame with the bars (input to picture), ms: {stats(to_pic)}")

            if "keyboard" not in skip:
                mark = serial.mark()
                for vk in (0x41, 0x42, 0x5A):
                    probe.send(f"key {vk} down")
                    probe.send(f"key {vk} up")
                    time.sleep(0.3)
                time.sleep(0.5)
                got = re.findall(r"STRM: KEY vk=(\d+) scan=(\d+) down", serial.text(mark))
                ups = re.findall(r"STRM: KEY vk=(\d+) scan=\d+ up", serial.text(mark))
                result("keyboard", got == [("65", "30"), ("66", "48"), ("90", "44")] and ups == ["65", "66", "90"],
                       f"the program got (vk, scan) {got} down and {ups} up (client: VK 0x41, 0x42, 0x5a)")

            if "mouse" not in skip:
                mark = serial.mark()
                cx, cy = args.width // 2, args.height // 2
                steps = [("pos", f"pos {cx} {cy} {args.width} {args.height}"), ("move 10 0", "move 10 0"),
                         ("pos +60,+30", f"pos {cx + 60} {cy + 30} {args.width} {args.height}"),
                         ("move 0 10", "move 0 10")]
                seen_pos = []
                for what, c in steps:
                    m0 = serial.mark()
                    probe.send(c)
                    time.sleep(0.4)
                    pos = re.findall(r"STRM: MOUSE (-?\d+) (-?\d+)", serial.text(m0))
                    seen_pos.append(f"{what} -> {pos[-1][0]},{pos[-1][1]}" if pos else f"{what} -> nothing")
                n = probe.nevents()
                probe.send("button left down")
                sent = probe.wait_event("sent", 5, n)
                bl, when = serial.expect(r"STRM: BTN l 1", 5, mark)
                probe.send("button left up")
                time.sleep(0.2)
                probe.send("button right down")
                probe.send("button right up")
                br, _ = serial.expect(r"STRM: BTN r 1", 5, mark)
                moved = sum(1 for s in seen_pos if "nothing" not in s)
                result("mouse", bool(bl and br) and moved >= 2,
                       f"the program's pointer (640x480 window): {'; '.join(seen_pos)}; left"
                       f" {'yes' if bl else 'no'}, right {'yes' if br else 'no'}"
                       + (f"; left button client -> program {(when - sent[1]) * 1000:.1f} ms" if bl and sent else ""))

            mark = serial.mark()
            serial.send("quit")
            m, _ = serial.expect(r"STRM: CLOSED[^\n]*\n", 20, mark)
            if not m:
                result("close", False, "the Glide window didn't close")

        if args.demo and "demo" not in skip and "glide" not in skip:
            for tag, prog in (("WSHDEMO", "WSHDEMO.EXE -api glide2 -part tunnel -secs 60 -nosound -time 20"),
                              ("WSHSPACE", "WSHSPACE.EXE -api glide2 -auto -nosound -time 20")):
                mark = serial.mark()
                serial.send(f"run 60 {prog}")
                m, t_start = serial.expect(r"STRM: RUN [^\n]*\n", 10, mark)
                e, t_end = serial.expect(r"STRM: EXIT [^\n]*\n", 90, mark)
                text = serial.text(mark)
                gfps = [float(x) for x in re.findall(rf"{tag}: FPS [^\n]*?fps=([0-9.]+)", text)]
                if not (m and e):
                    result(f"demo {tag}", False, "didn't run or didn't end (serial.log)")
                    continue
                # the middle of the run, away from mode changes at its start and end
                fs = [f for f in probe.frames_since(t_start + 5) if f[2] <= t_end - 2]
                span = fs[-1][1] - fs[0][1] if len(fs) > 1 else 0
                new = [f for f in fs if f[7] > 0]
                niv = [(b[1] - a[1]) * 1000 for a, b in zip(new, new[1:])]
                result(f"demo {tag}", len(fs) > 30,
                       f"{prog.split()[0]} ran ({e.group(0).strip()}); its FPS lines: {stats(gfps)}; at the client"
                       f" {(len(fs) - 1) / span if span else 0:.1f} frames/s, {len(new) / span if span else 0:.1f}/s with a"
                       f" new picture (intervals ms: {stats(niv)}, stdev {statistics.pstdev(niv) if niv else 0:.1f})")

        if "sound" not in skip:
            n = probe.nevents()
            mark = serial.mark()
            t_cmd = time.time()
            serial.send(f"tone 440 {args.sound_ms}")
            m, _ = serial.expect(r"STRM: TONE (start|error)[^\n]*\n", 10, mark)
            onset = probe.wait_event("audio-onset", 2, n)
            serial.expect(r"STRM: TONE done", args.sound_ms / 1000 + 10, mark)
            time.sleep(1.0)
            probe.close()
            ahead = None
            deadline = time.time() + 3
            while ahead is None and time.time() < deadline:
                with probe.lock:
                    ahead = next((float(x.group(1)) for ev in probe.events
                                  for x in [re.search(r"audio-ahead=([0-9.]+)", f"{ev[0]} {ev[2]}")] if x), None)
                time.sleep(0.05)
            try:
                rate, channels, samples = read_wav(f"{out}/sound.wav")
                want = args.sound_ms / 1000
                secs, hz, dropouts = tone(samples, rate, want)
                result("sound", abs(hz - 440) < 440 * 0.01 and want * 0.9 < secs < want * 1.15
                       and dropouts == 0 and ahead is not None and ahead <= stream3d.AHEAD_MS,
                       f"{secs:.2f} s of sound at {hz:.1f} Hz in the client's decoded audio ({rate} Hz,"
                       f" {channels} channels, {dropouts} dropouts); the most audio at once"
                       f" {'%.0f ms' % ahead if ahead is not None else 'unknown'} (at most {stream3d.AHEAD_MS});"
                       f" guest {m.group(0).strip() if m else 'no answer'};"
                       + (f" tone sent -> first loud packet at the client {(onset[1] - t_cmd) * 1000:.0f} ms"
                          if onset else " no onset seen"))
            except (OSError, ValueError, TypeError) as e:
                result("sound", False, f"the client's WAV: {e}")
    finally:
        if probe.proc.poll() is None:
            probe.close()
    return stream3d.finish(out)


if __name__ == "__main__":
    sys.exit(main())
