#!/usr/bin/env python3
"""A minimal client of QEMU's D-Bus display (-display dbus,gl=on) for e2e/3dfx/test.sh.

Registers a listener on console 0 of the QEMU at the bus address ADDR, takes the frames QEMU hands
it as dmabufs (ScanoutDMABUF, UpdateDMABUF), maps each dmabuf and writes the newest frame to OUT
(a P6 image, at most every 100 ms and always the last one), so the harness can check its pixels
like a screendump. Each UpdateDMABUF is answered DELAY_MS later: until then QEMU keeps the console
gl-blocked, which is the back-pressure qemu-3dfx's dmabuf scanout has to respect. Frames that come
as pixels (Scanout, Update: a display without GL) are taken too. On SIGTERM it prints what it got.

  dbus-listener.py ADDR OUT [DELAY_MS]

A linear dmabuf (llvmpipe's, through /dev/udmabuf) is mapped and read as it is. One with another
modifier (e.g. NVIDIA's block-linear layout) is imported through EGL instead (libEGL's device
platform, EGL_EXT_image_dma_buf_import_modifiers) into a GL texture and read with glReadPixels;
where that fails the listener says "pixel probes skipped", writes no frame and only counts them.
DBUS_LISTENER_IMPORT=egl imports linear dmabufs through EGL too (that path, tested on llvmpipe).

DBUS_LISTENER_AUDIO=1 also registers an AudioOutListener (org.qemu.Display1.Audio) and counts the
PCM QEMU writes to it (-audiodev dbus, -display dbus,audiodev=...): the stream's format, the bytes,
the seconds of sound they make and their peak sample, in the summary line "dbus-listener: audio
...". The summary also gives the pixel updates per second (a display without GL: the console's
refresh interval, -display dbus,refresh-ms=N, bounds it while the guest's screen changes).

Needs python3-gi (Gio), and libEGL.so.1 for a dmabuf that isn't linear.
"""
import ctypes
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

# DRM_FORMAT_MOD_LINEAR and DRM_FORMAT_MOD_INVALID (no explicit modifier): mapped as they are
LINEAR = (0, 0x00ffffffffffffff)
FORCE_EGL = os.environ.get("DBUS_LISTENER_IMPORT") == "egl"
AUDIO = os.environ.get("DBUS_LISTENER_AUDIO") == "1"

AUDIO_XML = """
<node>
  <interface name="org.qemu.Display1.AudioOutListener">
    <method name="Init">
      <arg type="t" direction="in"/><arg type="y" direction="in"/><arg type="b" direction="in"/>
      <arg type="b" direction="in"/><arg type="u" direction="in"/><arg type="y" direction="in"/>
      <arg type="u" direction="in"/><arg type="u" direction="in"/><arg type="b" direction="in"/>
    </method>
    <method name="Fini"><arg type="t" direction="in"/></method>
    <method name="SetEnabled"><arg type="t" direction="in"/><arg type="b" direction="in"/></method>
    <method name="SetVolume">
      <arg type="t" direction="in"/><arg type="b" direction="in"/><arg type="ay" direction="in"/>
    </method>
    <method name="Write"><arg type="t" direction="in"/><arg type="ay" direction="in"/></method>
    <property name="Interfaces" type="as" access="read"/>
  </interface>
</node>
"""


class EglImport:
    """A dmabuf imported into a GL texture on an EGL device display, read with glReadPixels"""

    def __init__(self):
        self.egl = ctypes.CDLL("libEGL.so.1")
        e = self.egl
        vp, i, u = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint
        e.eglGetProcAddress.restype = vp
        e.eglGetProcAddress.argtypes = [ctypes.c_char_p]
        e.eglInitialize.argtypes = [vp, vp, vp]
        e.eglQueryString.restype = ctypes.c_char_p
        e.eglQueryString.argtypes = [vp, i]
        e.eglBindAPI.argtypes = [u]
        e.eglChooseConfig.argtypes = [vp, vp, vp, i, vp]
        e.eglCreateContext.restype = vp
        e.eglCreateContext.argtypes = [vp] * 4
        e.eglMakeCurrent.argtypes = [vp] * 4
        e.eglGetError.restype = i
        self.query_devices = self.proc("eglQueryDevicesEXT", i, i, vp, vp)
        self.platform_display = self.proc("eglGetPlatformDisplayEXT", vp, u, vp, vp)
        self.create_image = self.proc("eglCreateImageKHR", vp, vp, vp, u, vp, vp)
        self.destroy_image = self.proc("eglDestroyImageKHR", i, vp, vp)
        self.image_target = self.proc("glEGLImageTargetTexture2DOES", None, u, vp)
        self.gen_textures = self.proc("glGenTextures", None, i, vp)
        self.bind_texture = self.proc("glBindTexture", None, u, u)
        self.tex_parameteri = self.proc("glTexParameteri", None, u, u, i)
        self.gen_framebuffers = self.proc("glGenFramebuffers", None, i, vp)
        self.bind_framebuffer = self.proc("glBindFramebuffer", None, u, u)
        self.framebuffer_texture = self.proc("glFramebufferTexture2D", None, u, u, u, u, i)
        self.check_framebuffer = self.proc("glCheckFramebufferStatus", u, u)
        self.pixel_storei = self.proc("glPixelStorei", None, u, i)
        self.read_pixels = self.proc("glReadPixels", None, i, i, i, i, u, u, vp)
        self.gl_error = self.proc("glGetError", u)
        self.dpy = self.image = self.devices = self.buf = None
        self.tex = ctypes.c_uint(0)
        self.fbo = ctypes.c_uint(0)

    def proc(self, name, res, *args):
        addr = self.egl.eglGetProcAddress(name.encode())
        if not addr:
            raise OSError("no %s" % name)
        return ctypes.CFUNCTYPE(res, *args)(addr)

    def context(self, dpy):
        """Whether dpy has a current GL context (without a surface) that imports dmabufs"""
        e = self.egl
        if not e.eglInitialize(dpy, None, None):
            return False
        exts = (e.eglQueryString(dpy, 0x3055) or b"").split()  # EGL_EXTENSIONS
        if (b"EGL_EXT_image_dma_buf_import_modifiers" not in exts
                or b"EGL_KHR_surfaceless_context" not in exts or not e.eglBindAPI(0x30A2)):
            return False
        cfg = ctypes.c_void_p(0)  # EGL_NO_CONFIG_KHR
        if b"EGL_KHR_no_config_context" not in exts:
            n = ctypes.c_int(0)
            # EGL_SURFACE_TYPE EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE EGL_OPENGL_BIT
            attrs = (ctypes.c_int * 5)(0x3033, 0x1, 0x3040, 0x8, 0x3038)
            if (not e.eglChooseConfig(dpy, attrs, ctypes.byref(cfg), 1, ctypes.byref(n))
                    or not n.value):
                return False
        ctx = e.eglCreateContext(dpy, cfg, None, (ctypes.c_int * 1)(0x3038))
        return bool(ctx and e.eglMakeCurrent(dpy, None, None, ctx))

    def attach(self, fd, w, h, stride, fourcc, modifier):
        """Import the dmabuf fd (the caller still closes it), on the first device that takes it"""
        # EGL_WIDTH, EGL_HEIGHT, EGL_LINUX_DRM_FOURCC_EXT, plane 0's FD, OFFSET, PITCH,
        # MODIFIER_LO, MODIFIER_HI
        attrs = (ctypes.c_int * 17)(0x3057, w, 0x3056, h, 0x3271, fourcc, 0x3272, fd, 0x3273, 0,
                                    0x3274, stride, 0x3443, modifier & 0xffffffff, 0x3444,
                                    modifier >> 32, 0x3038)
        self.detach()
        if self.devices is None:
            n = ctypes.c_int(0)
            devs = (ctypes.c_void_p * 16)()
            if not self.query_devices(16, devs, ctypes.byref(n)):
                raise OSError("eglQueryDevicesEXT failed")
            self.devices = list(devs[:n.value])
        tried = []
        while True:
            if self.dpy is not None:
                # EGL_LINUX_DMA_BUF_EXT
                self.image = self.create_image(self.dpy, None, 0x3270, None, attrs)
                if self.image:
                    break
                tried.append("eglCreateImage 0x%04x" % self.egl.eglGetError())
                self.dpy = None
                self.tex.value = 0
            if not self.devices:
                raise OSError("no EGL device imports it: %s" % (", ".join(tried) or "no device"))
            # EGL_PLATFORM_DEVICE_EXT
            dpy = self.platform_display(0x313F, self.devices.pop(0), None)
            if dpy and self.context(dpy):
                self.dpy = dpy
            else:
                tried.append("a device without a context")
        if not self.tex.value:
            self.gen_textures(1, ctypes.byref(self.tex))
            self.gen_framebuffers(1, ctypes.byref(self.fbo))
        self.bind_texture(0x0DE1, self.tex.value)  # GL_TEXTURE_2D
        self.tex_parameteri(0x0DE1, 0x2801, 0x2600)  # MIN_FILTER NEAREST
        self.tex_parameteri(0x0DE1, 0x2800, 0x2600)  # MAG_FILTER NEAREST
        self.image_target(0x0DE1, self.image)
        self.bind_framebuffer(0x8D40, self.fbo.value)  # GL_FRAMEBUFFER
        self.framebuffer_texture(0x8D40, 0x8CE0, 0x0DE1, self.tex.value, 0)  # COLOR_ATTACHMENT0
        status = self.check_framebuffer(0x8D40)
        if status != 0x8CD5:  # GL_FRAMEBUFFER_COMPLETE
            raise OSError("framebuffer incomplete (0x%04x)" % status)
        self.buf = (ctypes.c_ubyte * (w * h * 4))()

    def read(self, w, h):
        """The frame as RGBA rows, the dmabuf's first row first (as a mapped one)"""
        self.pixel_storei(0x0D05, 1)  # GL_PACK_ALIGNMENT
        self.read_pixels(0, 0, w, h, 0x1908, 0x1401, self.buf)  # GL_RGBA, GL_UNSIGNED_BYTE
        err = self.gl_error()
        if err:
            raise OSError("glReadPixels 0x%04x" % err)
        return memoryview(self.buf).cast("B")

    def detach(self):
        if self.image:
            self.destroy_image(self.dpy, self.image)
            self.image = None


egl = None  # an EglImport, once a dmabuf needs one

st = {"scanouts": 0, "updates": 0, "pixels": 0, "formats": set(), "first": None, "last": None,
      "bursts": 0, "prev": 0.0}
cur = {"map": None, "w": 0, "h": 0, "stride": 0, "rgb": (2, 1, 0), "flip": False, "dirty": False,
       "pix": None, "egl": False, "skip": False}
notes = set()


def note(msg):
    if msg not in notes:
        notes.add(msg)
        print("dbus-listener: " + msg, flush=True)


def write_frame():
    if not cur["dirty"] or not cur["w"]:
        return True
    cur["dirty"] = False
    if cur["skip"]:
        return True
    w, h, stride = cur["w"], cur["h"], cur["stride"]
    if cur["egl"]:
        try:
            src = egl.read(w, h)
        except OSError as e:
            note("the imported dmabuf can't be read (%s): pixel probes skipped" % e)
            cur["skip"] = True
            return True
    else:
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
        cur.update(map=None, w=w, h=h, stride=stride, rgb=FOURCC.get(code, (2, 1, 0)), flip=y0_top,
                   dirty=True, egl=False, skip=False)
        if modifier in LINEAR and not FORCE_EGL:
            cur["map"] = mmap.mmap(fd, stride * h, mmap.MAP_SHARED, mmap.PROT_READ)
        else:
            global egl
            try:
                egl = egl or EglImport()
                egl.attach(fd, w, h, stride, fourcc, modifier)
                # glReadPixels: RGBA rows, tightly packed
                cur.update(egl=True, stride=w * 4, rgb=(0, 1, 2))
                note("modifier 0x%x: the dmabuf imported through EGL, read with glReadPixels" %
                     modifier)
            except OSError as e:
                cur["skip"] = True
                if os.path.exists(OUT):
                    os.remove(OUT)  # not an older frame (the VGA's) in its place
                note("modifier 0x%x: the EGL import failed (%s): frames not mapped, pixel probes "
                     "skipped" % (modifier, e))
        os.close(fd)
    elif name == "UpdateDMABUF":
        st["updates"] += 1
        cur["dirty"] = True
        if DELAY:
            GLib.timeout_add(DELAY, lambda: inv.return_value(None) and False)
            return
    elif name in ("Scanout", "Update"):
        # the updates of one console refresh come together: a gap of 2 ms starts the next refresh
        if now - st["prev"] > 0.002:
            st["bursts"] += 1
        st["prev"] = now
        # the pixels as bytes: unpack() would make a list of ints of them, too slow for a frame
        n = params.n_children()
        args = [params.get_child_value(i).unpack() for i in range(n - 1)]
        data = params.get_child_value(n - 1).get_data_as_bytes().get_data()
        if name == "Scanout":
            w, h, stride, fmt = args
            if cur["map"] is not None:
                cur["map"].close()
            cur.update(map=None, w=w, h=h, stride=stride, flip=False, egl=False, skip=False,
                       pix=bytearray(data), rgb=(2, 1, 0))
            st["formats"].add("pixels 0x%x %dx%d" % (fmt, w, h))
        else:
            x, y, w, h, stride, fmt = args
            for r in range(h):
                o = (y + r) * cur["stride"] + x * 4
                cur["pix"][o:o + w * 4] = data[r * stride:r * stride + w * 4]
        st["pixels"] += 1
        cur["dirty"] = True
    inv.return_value(None)


def prop(conn, sender, path, iface, name):
    return GLib.Variant("as", [])


aud = {"streams": {}, "bytes": 0, "writes": 0, "peak": 0, "bps": 0, "formats": set()}


def audio_method(conn, sender, path, iface, name, params, inv):
    args = params.unpack() if name != "Write" else (params.get_child_value(0).unpack(),)
    if name == "Init":
        sid, bits, signed, flt, freq, nch, bpf, bps, be = args
        aud["streams"][sid] = (bits, signed, be)
        aud["bps"] = aud["bps"] or bps
        aud["formats"].add("%d-bit %s %d Hz %d ch" % (bits, "signed" if signed else "unsigned",
                                                      freq, nch))
    elif name == "Write":
        sid = args[0]
        data = params.get_child_value(1).get_data_as_bytes().get_data()
        aud["writes"] += 1
        aud["bytes"] += len(data)
        bits, signed, be = aud["streams"].get(sid, (16, True, False))
        if bits == 16 and signed:
            n = len(data) // 2
            samples = memoryview(data[:n * 2]).cast("h") if not be else []
            if n and samples:
                aud["peak"] = max(aud["peak"], max(abs(min(samples)), max(samples)))
    inv.return_value(None)


def register_audio(bus):
    """RegisterOutListener without blocking the main loop: QEMU sets up its side of the
    connection (and its proxies of our listeners) while the call is open, and our side answers
    only while the loop runs"""
    ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    fds = Gio.UnixFDList.new()
    fds.append(theirs.fileno())

    def connected(_, res):
        aconn = Gio.DBusConnection.new_finish(res)
        aconn.register_object("/org/qemu/Display1/AudioOutListener",
                              Gio.DBusNodeInfo.new_for_xml(AUDIO_XML).interfaces[0],
                              audio_method, prop, None)
        aconn.start_message_processing()
        audio_conn.append(aconn)
        print("dbus-listener: registered an AudioOutListener", flush=True)

    def registered(_, res):
        # QEMU sets up the connection and its proxy (a call to us) before its reply leaves:
        # the reply can come late or not at all, while the listener works
        try:
            bus.call_with_unix_fd_list_finish(res)
        except GLib.Error as e:
            note("RegisterOutListener: %s (the listener works anyway)" % e.message)
        theirs.close()

    bus.call_with_unix_fd_list("org.qemu", "/org/qemu/Display1/Audio", "org.qemu.Display1.Audio",
                               "RegisterOutListener", GLib.Variant("(h)", (0,)), None,
                               Gio.DBusCallFlags.NONE, -1, fds, None, registered)
    stream = Gio.Socket.new_from_fd(ours.detach()).connection_factory_create_connection()
    Gio.DBusConnection.new(stream, None, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                           Gio.DBusConnectionFlags.DELAY_MESSAGE_PROCESSING, None, None,
                           connected)
    return False


def stats(*_):
    secs = (st["last"] - st["first"]) if st["first"] else 0
    print("dbus-listener: %d dmabuf scanouts, %d dmabuf updates (%.1f per s), %d pixel updates "
          "in %d refreshes (%.1f per s); formats: %s" % (
              st["scanouts"], st["updates"], st["updates"] / secs if secs else 0, st["pixels"],
              st["bursts"], st["bursts"] / secs if secs else 0,
              "; ".join(sorted(st["formats"])) or "none"), flush=True)
    if AUDIO:
        print("dbus-listener: audio %d writes, %d bytes (%.2f s), peak %d; formats: %s" %
              (aud["writes"], aud["bytes"], aud["bytes"] / aud["bps"] if aud["bps"] else 0,
               aud["peak"], "; ".join(sorted(aud["formats"])) or "none"), flush=True)
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
audio_conn = []
if AUDIO:
    GLib.idle_add(register_audio, bus)
GLib.timeout_add(100, write_frame)
print("dbus-listener: registered on console 0, replies to UpdateDMABUF after %d ms" % DELAY,
      flush=True)
GLib.MainLoop().run()
