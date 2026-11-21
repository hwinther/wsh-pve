#!/usr/bin/env python3
"""A minimal client of QEMU's D-Bus display (-display dbus,gl=on) for e2e/3dfx/test.sh.

Registers a listener on console 0 of the QEMU at the bus address ADDR, takes the frames QEMU hands
it as dmabufs (ScanoutDMABUF, UpdateDMABUF), maps each dmabuf and writes the newest frame to OUT
(a P6 image, at most every 100 ms and always the last one), so the harness can check its pixels
like a screendump. Each UpdateDMABUF is answered DELAY_MS later: until then QEMU keeps the console
gl-blocked, which is the back-pressure qemu-3dfx's dmabuf scanout has to respect. Frames that come
as pixels (Scanout, Update: a display without GL) are taken too. On SIGTERM it prints what it got.

  dbus-listener.py ADDR OUT [DELAY_MS]

Needs python3-gi (Gio); the dmabufs must be mappable (llvmpipe's, through /dev/udmabuf, are).
"""
import mmap
import os
import signal
import socket
import sys
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

XML = """
<node>
  <interface name="org.qemu.Display1.Listener">
    <method name="Scanout">
      <arg type="u" direction="in"/><arg type="u" direction="in"/><arg type="u" direction="in"/>
      <arg type="u" direction="in"/><arg type="ay" direction="in"/>
    </method>
    <method name="Update">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/>
      <arg type="i" direction="in"/><arg type="u" direction="in"/><arg type="u" direction="in"/>
      <arg type="ay" direction="in"/>
    </method>
    <method name="ScanoutDMABUF">
      <arg type="h" direction="in"/><arg type="u" direction="in"/><arg type="u" direction="in"/>
      <arg type="u" direction="in"/><arg type="u" direction="in"/><arg type="t" direction="in"/>
      <arg type="b" direction="in"/>
    </method>
    <method name="UpdateDMABUF">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/>
      <arg type="i" direction="in"/>
    </method>
    <method name="Disable"/>
    <method name="MouseSet">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/>
    </method>
    <method name="CursorDefine">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/>
      <arg type="i" direction="in"/><arg type="ay" direction="in"/>
    </method>
    <property name="Interfaces" type="as" access="read"/>
  </interface>
</node>
"""

ADDR, OUT = sys.argv[1], sys.argv[2]
DELAY = int(sys.argv[3]) if len(sys.argv) > 3 else 0
# fourcc -> the byte offsets of R, G, B in a pixel; pixman formats (Scanout) likewise
FOURCC = {b"XB24": (0, 1, 2), b"AB24": (0, 1, 2), b"XR24": (2, 1, 0), b"AR24": (2, 1, 0)}
PIXMAN_X8R8G8B8, PIXMAN_A8R8G8B8 = 0x20020888, 0x20028888

st = {"scanouts": 0, "updates": 0, "pixels": 0, "formats": set(), "first": None, "last": None}
cur = {"map": None, "w": 0, "h": 0, "stride": 0, "rgb": (2, 1, 0), "flip": False, "dirty": False,
       "pix": None}


def write_frame():
    if not cur["dirty"] or not cur["w"]:
        return True
    cur["dirty"] = False
    w, h, stride = cur["w"], cur["h"], cur["stride"]
    src = cur["map"] if cur["map"] is not None else cur["pix"]
    r, g, b = cur["rgb"]
    fb = bytearray(w * h * 3)
    for y in range(h):
        sy = (h - 1 - y) if cur["flip"] else y
        row = src[sy * stride:sy * stride + w * 4]
        o = y * w * 3
        fb[o:o + w * 3:3] = row[r::4]
        fb[o + 1:o + w * 3:3] = row[g::4]
        fb[o + 2:o + w * 3:3] = row[b::4]
    tmp = OUT + ".tmp"
    with open(tmp, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h) + bytes(fb))
    os.replace(tmp, OUT)
    return True


def method(conn, sender, path, iface, name, params, inv):
    now = time.monotonic()
    st["first"] = st["first"] or now
    st["last"] = now
    if name == "ScanoutDMABUF":
        idx, w, h, stride, fourcc, modifier, y0_top = params.unpack()
        fd = inv.get_message().get_unix_fd_list().get(idx)
        code = fourcc.to_bytes(4, "little")
        st["scanouts"] += 1
        st["formats"].add("%s %dx%d stride %d modifier 0x%x y0_top %s" %
                          (code.decode(errors="replace"), w, h, stride, modifier, y0_top))
        if cur["map"] is not None:
            cur["map"].close()
        cur.update(map=mmap.mmap(fd, stride * h, mmap.MAP_SHARED, mmap.PROT_READ), w=w, h=h,
                   stride=stride, rgb=FOURCC.get(code, (2, 1, 0)), flip=y0_top, dirty=True)
        os.close(fd)
    elif name == "UpdateDMABUF":
        st["updates"] += 1
        cur["dirty"] = True
        if DELAY:
            GLib.timeout_add(DELAY, lambda: inv.return_value(None) and False)
            return
    elif name in ("Scanout", "Update"):
        args = params.unpack()
        if name == "Scanout":
            w, h, stride, fmt, data = args
            if cur["map"] is not None:
                cur["map"].close()
            cur.update(map=None, w=w, h=h, stride=stride, flip=False,
                       pix=bytearray(bytes(data)), rgb=(2, 1, 0))
            st["formats"].add("pixels 0x%x %dx%d" % (fmt, w, h))
        else:
            x, y, w, h, stride, fmt, data = args
            data = bytes(data)
            for r in range(h):
                o = (y + r) * cur["stride"] + x * 4
                cur["pix"][o:o + w * 4] = data[r * stride:r * stride + w * 4]
        st["pixels"] += 1
        cur["dirty"] = True
    inv.return_value(None)


def prop(conn, sender, path, iface, name):
    return GLib.Variant("as", [])


def stats(*_):
    secs = (st["last"] - st["first"]) if st["first"] else 0
    print("dbus-listener: %d dmabuf scanouts, %d dmabuf updates (%.1f per s), %d pixel updates; "
          "formats: %s" % (st["scanouts"], st["updates"], st["updates"] / secs if secs else 0,
                           st["pixels"], "; ".join(sorted(st["formats"])) or "none"), flush=True)
    os._exit(0)


GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stats)
bus = Gio.DBusConnection.new_for_address_sync(
    ADDR, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
    Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
for _ in range(100):
    owner = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                          "NameHasOwner", GLib.Variant("(s)", ("org.qemu",)), None,
                          Gio.DBusCallFlags.NONE, -1, None).unpack()[0]
    if owner:
        break
    time.sleep(0.1)
else:
    sys.exit("dbus-listener: no org.qemu on the bus")
ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
fds = Gio.UnixFDList.new()
fds.append(theirs.fileno())
bus.call_with_unix_fd_list_sync("org.qemu", "/org/qemu/Display1/Console_0",
                                "org.qemu.Display1.Console", "RegisterListener",
                                GLib.Variant("(h)", (0,)), None, Gio.DBusCallFlags.NONE, -1, fds,
                                None)
theirs.close()
stream = Gio.Socket.new_from_fd(ours.detach()).connection_factory_create_connection()
conn = Gio.DBusConnection.new_sync(stream, None, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT,
                                   None, None)
conn.register_object("/org/qemu/Display1/Listener",
                     Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], method, prop, None)
conn.connect("closed", lambda *a: stats())
GLib.timeout_add(100, write_frame)
print("dbus-listener: registered on console 0, replies to UpdateDMABUF after %d ms" % DELAY,
      flush=True)
GLib.MainLoop().run()
