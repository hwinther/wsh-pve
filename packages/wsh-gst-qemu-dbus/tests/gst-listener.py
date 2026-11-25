#!/usr/bin/env python3
"""qemudbussrc in place of e2e/3dfx/dbus-listener.py, for e2e/3dfx/test.sh's dbus mode with real
GL frames (the Glide and Mesa guests): DBUS_LISTENER=<this file> GLIDE_DISPLAY=dbus.

Takes the same arguments, ADDR OUT [DELAY_MS], and does what the test reads from that listener: a
pipeline `qemudbussrc ! videoconvert ! video/x-raw,format=RGB ! appsink` writes the newest frame to
OUT as a P6 image (at most every 100 ms, and the last one), and at the end (SIGTERM, or QEMU
closing the connection) it prints the summary line in dbus-listener.py's form: dmabuf scanouts,
dmabuf updates and their rate, the formats (as DRM fourccs, from the caps qemudbussrc set). The
element answers every UpdateDMABUF itself as soon as it has copied the frame, so DELAY_MS (a late
reply) doesn't apply and is ignored. Also prints qemudbussrc's statistics and how many frames
reached the appsink.

Needs the wsh-gst-qemu-dbus package, python3-gi, gir1.2-gstreamer-1.0 and
gir1.2-gst-plugins-base-1.0.
"""
import os
import re
import signal
import sys
import time

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

ADDR, OUT = sys.argv[1], sys.argv[2]
# GStreamer's formats as the DRM fourccs dbus-listener.py prints
FOURCC = {"RGBx": "XB24", "RGBA": "AB24", "BGRx": "XR24", "BGRA": "AR24", "xRGB": "BX24",
          "ARGB": "BA24", "RGB16": "RG16"}

Gst.init(None)
pipeline = Gst.parse_launch(
    f"qemudbussrc name=src address={ADDR} ! videoconvert ! video/x-raw,format=RGB ! "
    "appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true")
src = pipeline.get_by_name("src")
sink = pipeline.get_by_name("sink")
st = {"samples": 0, "latest": None, "written": None, "first": None, "last": None,
      "formats": set()}


def on_caps(pad, info):
    event = info.get_event()
    if event.type == Gst.EventType.CAPS:
        s = event.parse_caps().get_structure(0)
        fmt = s.get_string("format")
        st["formats"].add("%s %dx%d" % (FOURCC.get(fmt, fmt), s.get_int("width")[1],
                                       s.get_int("height")[1]))
    return Gst.PadProbeReturn.OK


src.get_static_pad("src").add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, on_caps)


def on_sample(appsink):
    sample = appsink.emit("pull-sample")
    now = time.monotonic()
    st["first"] = st["first"] or now
    st["last"] = now
    st["samples"] += 1
    st["latest"] = sample
    return Gst.FlowReturn.OK


sink.connect("new-sample", on_sample)


def write_frame():
    sample = st["latest"]
    if sample is None or sample is st["written"]:
        return True
    st["written"] = sample
    s = sample.get_caps().get_structure(0)
    w, h = s.get_int("width")[1], s.get_int("height")[1]
    buf = sample.get_buffer()
    ok, info = buf.map(Gst.MapFlags.READ)
    if not ok:
        return True
    stride = len(info.data) // h
    rows = b"".join(bytes(info.data[y * stride:y * stride + w * 3]) for y in range(h))
    buf.unmap(info)
    tmp = OUT + ".tmp"
    with open(tmp, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h) + rows)
    os.replace(tmp, OUT)
    return True


def finish(*_):
    write_frame()
    stats = src.get_property("stats") or ""
    counts = dict((k, int(v)) for k, v in re.findall(r"([a-z-]+)=(\d+)", stats))
    secs = (st["last"] - st["first"]) if st["first"] else 0
    updates = counts.get("dmabuf-updates", 0)
    pixels = counts.get("updates", 0) + counts.get("map-updates", 0)
    print("dbus-listener: %d dmabuf scanouts, %d dmabuf updates (%.1f per s), %d pixel updates "
          "in 0 refreshes (0.0 per s); formats: %s" % (
              counts.get("dmabuf-scanouts", 0), updates, updates / secs if secs else 0, pixels,
              "; ".join(sorted(st["formats"])) or "none"), flush=True)
    print("gst-listener: qemudbussrc %s; %d frames reached the appsink (%.1f per s)" % (
        stats, st["samples"], st["samples"] / secs if secs else 0), flush=True)
    pipeline.set_state(Gst.State.NULL)
    os._exit(0)


def on_message(bus, msg):
    if msg.type == Gst.MessageType.EOS:
        finish()
    elif msg.type == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("gst-listener: error: %s (%s)" % (err.message, dbg), flush=True)
        finish()
    elif msg.type == Gst.MessageType.WARNING:
        err, dbg = msg.parse_warning()
        print("dbus-listener: %s (%s)" % (err.message, dbg), flush=True)


bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, finish)
GLib.timeout_add(100, write_frame)
if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
    print("gst-listener: the pipeline doesn't start", flush=True)
    sys.exit(1)
print("dbus-listener: registered on console 0 through qemudbussrc (replies at once)", flush=True)
GLib.MainLoop().run()
