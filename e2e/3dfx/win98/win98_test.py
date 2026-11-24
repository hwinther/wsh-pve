#!/usr/bin/env python3
"""The Glide and OpenGL pass-through of qemu-3dfx in a real Windows 98 SE guest, end to end.

    win98_test.py --template WIN98SE.raw --drivers qemu-3dfx-drivers-<rev>.zip --out OUT --private PRIV \\
        [--tests glide2,glide3,opengl] [--display vnc|egl|sdl] [--accel auto|tcg|kvm] [--bench N]

The operator's own installed Windows 98 SE disk (--template, raw, one FAT32 partition; never
modified, never in the repository) is copied into PRIV, and onto the copy go, with mtools:

  - qemu-3dfx's guest drivers of the binary under test (--drivers: the qemu-3dfx-drivers-<rev>
    release of wsh-pve, the revision the binary names): FXMEMMAP.VXD, GLIDE.DLL, GLIDE2X.DLL and
    GLIDE3X.DLL into C:\\WINDOWS\\SYSTEM, GLIDE2X.OVL into C:\\WINDOWS, OPENGL32.DLL next to the test
    program in C:\\WIN3DFX;
  - our test programs (built by build.sh): glidetst.exe, gltest.exe and w3drun.exe, with RUN.TXT,
    the list w3drun.exe works through; w3drun.exe also goes into the Start menu's StartUp folder,
    so it starts once the desktop is up, runs the tests one at a time and powers Windows off.

QEMU (qemu-system-x86_64-3dfx, --qemu) boots the copy with the devices of the PVE VM the disk was
installed in (an identical device set keeps Windows' new-hardware wizard away; see qemu_command()):
headless as PVE runs a VM with `vga: std,mesa=1` (no display, a VNC server, the HMP monitor on a
socket), the same with QEMU's egl-headless display (--display egl: the console has GL, so qemu-3dfx
hands the Glide and OpenGL frames to it as a dmabuf; the captures then come from the VNC server, as QEMU's
screendump has no surface to read while the console scans a dmabuf out; needs /dev/udmabuf or a
render node), or with an SDL window on an X display (--display sdl, Xvfb). The test programs print to COM1
(QEMU writes it to a file); on "<TAG>: FRAME" the harness takes a screendump of the console
(headless: where qemu-3dfx shows the frame) or a capture of the SDL window and checks the probes of
packages/wsh-openglide/tests/scene.h, the scene every 3dfx test draws; on "<TAG>: CLOSED" it
checks that the console shows Windows again (not the scene). With --hold 6 or more the frame is
checked a second time 1.5 s before the hold ends: a frame the program holds without a swap must
stay (the OpenGL wrapper's display timer gave it back to the VGA about 4 s after the last swap). A
test passes when the guest program reports PASS (its own read-back matched), the console showed the
frame (both times with a long hold), and Windows came back.

With --pve VMID the harness runs on a PVE node (the e2e PVE container: e2e/3dfx/win98-test.sh --pve)
and PVE starts the VM instead: `qm create` with the same devices (`cpu: pentium3`, `scsihw: lsi`,
`vga: std,mesa=1`, with --display egl also `mesa-display=egl-headless`, an rtl8139 NIC, AC97, the
tablet), COM1 and QEMU's messages to files through `args` (-D
with a log mask keeps a daemonized QEMU's stderr in that file), then `qm start`. The frames are read
where PVE's console reads them: QEMU's screendump through the VM's QMP socket, or (egl) PVE's VNC
socket, with a VNC password set through QMP; OpenGLide's log comes from the directory qemu-server
gives it. PVE attaches only a storage's disks, so the run adds a directory storage in PRIV
(`w3d<VMID>`) with the disk copy hard-linked into it. Windows powering off stops the VM; the VM and
the storage are removed afterwards.

PRIV keeps the disk copy and the screendumps, which show Windows: they stay on the machine that ran
the test. OUT gets only our own text: summary.json and summary.md (verdicts, probe values, times,
frame rates), the serial log, QEMU's output, OpenGLide's log and the guest's C:\\WIN3DFX\\LOG.TXT.
Exit status 0 when every test passed, 1 when one failed, 2 on a setup error, 77 when the binary has
no qemu-3dfx.
"""
import argparse
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SCENE_H = os.path.join(TOP, "packages", "wsh-openglide", "tests", "scene.h")

# test name -> (serial tag, program, arguments)
TESTS = {
    "glide2": ("GLIDE2", "GLIDETST.EXE", ""),
    "glide3": ("GLIDE3", "GLIDETST.EXE", "glide3"),
    "opengl": ("OPENGL", "GLTEST.EXE", ""),
}
# The guest drivers of a qemu-3dfx-drivers release and where they go on C:
DRIVERS = {
    "fxmemmap.vxd": "WINDOWS/SYSTEM",
    "glide.dll": "WINDOWS/SYSTEM",
    "glide2x.dll": "WINDOWS/SYSTEM",
    "glide3x.dll": "WINDOWS/SYSTEM",
    "glide2x.ovl": "WINDOWS",
    "opengl32.dll": "WIN3DFX",
}
STARTUP = "WINDOWS/Start Menu/Programs/StartUp"
LINE_RE = re.compile(r"^(W3DRUN|GLIDE2|GLIDE3|OPENGL): (.*)$")


def log(msg):
    print(f"win98-test: {msg}", flush=True)


# --- the scene and its probes (parsed from scene.h, so there is one definition) ---------------------

def parse_scene(text):
    """Probes, tolerance and the Gouraud triangle of scene.h's C source."""
    def floats(name):
        m = re.search(r"\b%s\[3\]\[\d\]\s*=\s*\{(.*?)\};" % re.escape(name), text, re.S)
        if not m:
            raise ValueError(f"scene.h: no {name}")
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m.group(1))]
        n = len(nums) // 3
        return [nums[i * n:(i + 1) * n] for i in range(3)]

    m = re.search(r"probes\[\]\s*=\s*\{(.*?)\n\};", text, re.S)
    if not m:
        raise ValueError("scene.h: no probes[]")
    probes = []
    for p in re.finditer(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\d)\s*\}',
                         m.group(1)):
        probes.append({"what": p.group(1), "x": int(p.group(2)), "y": int(p.group(3)),
                       "rgb": [int(p.group(i), 0) for i in (4, 5, 6)], "gouraud": p.group(7) == "1"})
    if not probes:
        raise ValueError("scene.h: probes[] has no entries")
    tol = re.search(r"#define TOLERANCE (\d+)", text)
    w = re.search(r"#define W (\d+)", text)
    h = re.search(r"#define H (\d+)", text)
    scene = {"probes": probes, "tolerance": int(tol.group(1)), "w": int(w.group(1)), "h": int(h.group(1)),
             "gouraud_tri": floats("gouraud_tri"), "gouraud_rgb": floats("gouraud_rgb")}
    for p in probes:
        if p["gouraud"]:
            p["rgb"] = gouraud_expect(scene, p["x"], p["y"])
    return scene


def gouraud_expect(scene, x, y):
    """scene.h's gouraud_expect(): the colour at the centre of pixel (x, y)."""
    v, c = scene["gouraud_tri"], scene["gouraud_rgb"]
    px, py = x + 0.5, y + 0.5
    d = (v[1][1] - v[2][1]) * (v[0][0] - v[2][0]) + (v[2][0] - v[1][0]) * (v[0][1] - v[2][1])
    l0 = ((v[1][1] - v[2][1]) * (px - v[2][0]) + (v[2][0] - v[1][0]) * (py - v[2][1])) / d
    l1 = ((v[2][1] - v[0][1]) * (px - v[2][0]) + (v[0][0] - v[2][0]) * (py - v[2][1])) / d
    l2 = 1 - l0 - l1
    return [int(l0 * c[0][i] + l1 * c[1][i] + l2 * c[2][i] + 0.5) for i in range(3)]


def read_ppm(path):
    """(width, height, rgb bytes) of a binary PPM (P6, maxval 255), as QEMU's screendump writes it."""
    with open(path, "rb") as f:
        data = f.read()
    return parse_ppm(data)


def parse_ppm(data):
    fields, i = [], 0
    while len(fields) < 4:
        while i < len(data) and data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while i < len(data) and data[i:i + 1] != b"\n":
                i += 1
            continue
        j = i
        while j < len(data) and not data[j:j + 1].isspace():
            j += 1
        if j == i:
            raise ValueError("PPM: truncated header")
        fields.append(data[i:j])
        i = j
    if fields[0] != b"P6" or int(fields[3]) != 255:
        raise ValueError(f"PPM: not P6 with maxval 255 ({fields[0]!r}, {fields[3]!r})")
    w, h = int(fields[1]), int(fields[2])
    pix = data[i + 1:i + 1 + w * h * 3]
    if len(pix) != w * h * 3:
        raise ValueError(f"PPM: {len(pix)} bytes of pixels for {w}x{h}")
    return w, h, pix


def parse_xwd(data):
    """(width, height, rgb bytes) of an X window dump (xwd -silent) in ZPixmap with 24 or 32 bits per
    pixel and 8-bit colour masks, as Xvfb's TrueColor visual gives it."""
    if len(data) < 100:
        raise ValueError("XWD: truncated header")
    f = struct.unpack(">25I", data[:100])
    header, version, fmt, _, w, h = f[0], f[1], f[2], f[3], f[4], f[5]
    byte_order, bpp, bpl = f[7], f[11], f[12]
    masks, ncolors = f[14:17], f[19]
    if version != 7 or fmt != 2 or bpp not in (24, 32):
        raise ValueError(f"XWD: version {version}, format {fmt}, {bpp} bits per pixel: not handled")
    shifts = []
    for m in masks:
        if m not in (0xff, 0xff00, 0xff0000, 0xff000000):
            raise ValueError(f"XWD: colour mask {m:#x} not handled")
        s = 0
        while not (m >> s) & 1:
            s += 1
        shifts.append(s)
    off = header + ncolors * 12
    step = bpp // 8
    endian = "little" if byte_order == 0 else "big"
    out = bytearray(w * h * 3)
    for y in range(h):
        row = data[off + y * bpl:off + y * bpl + w * step]
        if len(row) < w * step:
            raise ValueError("XWD: truncated image")
        for x in range(w):
            v = int.from_bytes(row[x * step:(x + 1) * step], endian)
            o = (y * w + x) * 3
            out[o], out[o + 1], out[o + 2] = ((v >> s) & 0xff for s in shifts)
    return w, h, bytes(out)


def check_probes(scene, w, h, pix, scaled=False):
    """Every probe of the scene in an RGB image: a list of results and the number of mismatches. The
    frame is expected at the top left (the console is the frame's size when qemu-3dfx shows it), or,
    with scaled, stretched over the whole image (an SDL window keeps the guest desktop's size and
    qemu-3dfx scales the frame into it)."""
    out, bad, tol = [], 0, scene["tolerance"]
    for p in scene["probes"]:
        x, y = p["x"], p["y"]
        if scaled:
            x, y = int((x + 0.5) * w / scene["w"]), int((y + 0.5) * h / scene["h"])
        if x >= w or y >= h:
            got = None
            ok = False
        else:
            o = (y * w + x) * 3
            got = list(pix[o:o + 3])
            ok = all(abs(got[c] - p["rgb"][c]) <= tol for c in range(3))
        bad += not ok
        out.append({"what": p["what"], "x": x, "y": y, "want": p["rgb"], "got": got, "ok": ok})
    return out, bad


# --- the serial log ------------------------------------------------------------------------------

class Serial:
    """The test programs' lines in QEMU's serial file, read as it grows."""

    def __init__(self, path):
        self.path, self.pos, self.partial, self.lines = path, 0, b"", []

    def poll(self):
        """New complete lines (tag, text) since the last call."""
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except FileNotFoundError:
            return []
        self.pos += len(data)
        return self.feed(data)

    def feed(self, data):
        new = []
        buf = self.partial + data
        *complete, self.partial = re.split(rb"\r?\n", buf)
        for raw in complete:
            line = raw.decode("latin-1").strip("\r\x00")
            m = LINE_RE.match(line)
            if m:
                new.append((m.group(1), m.group(2)))
                self.lines.append((m.group(1), m.group(2)))
        return new


def parse_bench(text):
    """'BENCH <n> frames in <ms> ms, <fps> fps' -> dict, or None."""
    m = re.match(r"BENCH (\d+) frames in (\d+) ms, ([\d.]+) fps", text)
    if not m:
        return None
    return {"frames": int(m.group(1)), "ms": int(m.group(2)), "fps": float(m.group(3))}


def verdict_of(text):
    """The guest's verdict of a line, or None: PASS, FAIL <n> or ERROR <what>."""
    if text == "PASS":
        return "PASS"
    if re.match(r"(FAIL \d+|ERROR .*)$", text):
        return text
    return None


# --- the disk ------------------------------------------------------------------------------------

def partition_offset(mbr):
    """Byte offset of the first FAT partition in an MBR (types 01, 04, 06, 0B, 0C, 0E)."""
    if len(mbr) < 512 or mbr[510:512] != b"\x55\xaa":
        raise ValueError("no MBR signature")
    for i in range(4):
        e = mbr[446 + 16 * i:446 + 16 * (i + 1)]
        if e[4] in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E):
            return struct.unpack_from("<I", e, 8)[0] * 512
    raise ValueError("no FAT partition in the MBR")


def clean_bits(boot):
    """(offset of FAT[1] in the partition for each FAT, the clean-shutdown mask) from a FAT boot
    sector: FAT32 keeps "volume clean" in bit 27 of FAT[1] and "no disk error" in bit 26, FAT16 in
    bits 15 and 14. Windows clears the clean bit while it runs and sets it when it shuts down."""
    bps, = struct.unpack_from("<H", boot, 11)
    reserved, = struct.unpack_from("<H", boot, 14)
    nfats = boot[16]
    fat16_size, = struct.unpack_from("<H", boot, 22)
    if fat16_size:
        return [(reserved + i * fat16_size) * bps + 2 for i in range(nfats)], 2, 0xC000
    fat32_size, = struct.unpack_from("<I", boot, 36)
    return [(reserved + i * fat32_size) * bps + 4 for i in range(nfats)], 4, 0x0C000000


def mark_clean(raw):
    """Marks the copy's FAT partition as cleanly shut down, as Windows leaves it, so Windows doesn't
    start ScanDisk (which takes minutes) when the template was copied from a VM that was running or
    killed. Returns whether it had to."""
    with open(raw, "r+b") as f:
        part = partition_offset(f.read(512))
        f.seek(part)
        offsets, size, mask = clean_bits(f.read(512))
        changed = False
        for o in offsets:
            f.seek(part + o)
            fmt = "<I" if size == 4 else "<H"
            v, = struct.unpack(fmt, f.read(size))
            if v & mask != mask:
                f.seek(part + o)
                f.write(struct.pack(fmt, v | mask))
                changed = True
        return changed


MDIR_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})")


def rtc_after(mdir_outputs, hours=1):
    """QEMU's -rtc base for the guest: an hour after the newest of the registry files' times (mdir
    output), when Windows last ran. Booting at the wall-clock time instead can cross a daylight saving
    change since then, and Windows 98 then stops at a "New clock settings" dialog that waits for OK."""
    import datetime
    times = []
    for out in mdir_outputs:
        for m in MDIR_DATE_RE.finditer(out):
            y, mo, d, h, mi = (int(x) for x in m.groups())
            times.append(datetime.datetime(y, mo, d, h, mi))
    if not times:
        return None
    return (max(times) + datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")


class Fat:
    """C: of a raw disk copy, through mtools."""

    def __init__(self, raw):
        with open(raw, "rb") as f:
            self.img = f"{raw}@@{partition_offset(f.read(512))}"
        self.env = dict(os.environ, MTOOLS_SKIP_CHECK="1", MTOOLS_LOWER_CASE="0")

    def listing(self, path):
        """mdir's listing of a file, hidden and system ones too."""
        return self.m("mdir", "-a", "-i", self.img, f"::/{path}", check=False).stdout

    def m(self, *args, check=True):
        return subprocess.run(list(args), env=self.env, check=check, capture_output=True, text=True,
                              errors="replace")

    def exists(self, path):
        return self.m("mdir", "-b", "-i", self.img, f"::/{path}", check=False).returncode == 0

    def mkdir(self, path):
        if not self.exists(path):
            self.m("mmd", "-i", self.img, f"::/{path}")

    def put(self, src, dst):
        self.m("mcopy", "-o", "-i", self.img, src, f"::/{dst}")

    def get(self, path, dst):
        return self.m("mcopy", "-o", "-n", "-i", self.img, f"::/{path}", dst, check=False).returncode == 0

    def delete(self, path):
        self.m("mdel", "-i", self.img, f"::/{path}", check=False)


def unpack_drivers(src, dest):
    """The guest drivers (a release zip or a directory) into dest, names in lower case; returns the
    revision VERSION.txt names, if any."""
    os.makedirs(dest, exist_ok=True)
    found = {}
    if os.path.isdir(src):
        for root, _, files in os.walk(src):
            for f in files:
                found[f.lower()] = os.path.join(root, f)
        for name, path in found.items():
            shutil.copyfile(path, os.path.join(dest, name))
    else:
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = os.path.basename(info.filename).lower()
                with z.open(info) as s, open(os.path.join(dest, name), "wb") as d:
                    shutil.copyfileobj(s, d)
                found[name] = name
    missing = [n for n in DRIVERS if n not in found]
    if missing:
        raise ValueError(f"the drivers have no {', '.join(missing)}")
    rev = None
    vt = os.path.join(dest, "version.txt")
    if os.path.exists(vt):
        with open(vt, errors="replace") as f:
            m = re.search(r"\b([0-9a-f]{7,40})\b", f.read())
        rev = m.group(1)[:7] if m else None
    return rev


def run_list(tests, hold, bench, timeout, delay, stay=False, gap=8):
    """RUN.TXT for w3drun.exe (CR LF lines): a pause of gap seconds between the programs, for the
    check that the console shows Windows again."""
    lines = [f"delay {delay}"]
    for i, t in enumerate(tests):
        if i:
            lines.append(f"delay {gap}")
        _, prog, args = TESTS[t]
        a = " ".join(x for x in (args, f"hold={hold}", f"bench={bench}") if x)
        lines.append(f"run {timeout} {prog} {a}")
    lines.append("stay" if stay else "shutdown")
    return "\r\n".join(lines) + "\r\n"


def prepare_disk(args, raw, bindir, drivers_dir):
    fat = Fat(raw)
    report = {}
    fat.mkdir("WIN3DFX")
    for name, where in DRIVERS.items():
        dst = f"{where}/{name.upper()}"
        report[dst] = "replaced" if fat.exists(dst) else "added"
        fat.put(os.path.join(drivers_dir, name), dst)
    for exe in ("w3drun.exe", "glidetst.exe", "gltest.exe"):
        fat.put(os.path.join(bindir, exe), f"WIN3DFX/{exe.upper()}")
    runtxt = os.path.join(args.private, "RUN.TXT")
    with open(runtxt, "w", newline="") as f:
        f.write(run_list(args.tests, args.hold, args.bench, args.test_timeout, args.delay, args.stay))
    fat.put(runtxt, "WIN3DFX/RUN.TXT")
    fat.delete("WIN3DFX/DONE.TXT")
    fat.delete("WIN3DFX/LOG.TXT")
    fat.put(os.path.join(bindir, "w3drun.exe"), f"{STARTUP}/W3DRUN.EXE")
    return fat, report


# --- QEMU ----------------------------------------------------------------------------------------

def qemu_rev(qemu):
    """(qemu-3dfx revision, version text) of a QEMU binary's --version."""
    out = subprocess.run([qemu, "--version"], capture_output=True, text=True).stdout
    m = re.search(r"qemu-3dfx@([0-9a-f]{7})-", out)
    lines = [ln.strip() for ln in out.splitlines() if ln.startswith("QEMU") or "qemu-3dfx" in ln]
    return (m.group(1) if m else None), ", ".join(lines)


# The x86-64-v2 extensions on top of the Pentium III. The guest drivers of the older qemu-3dfx-drivers
# releases were built with -march=x86-64-v2 (SSE2 up to SSE4.2, SSSE3, POPCNT in GLIDE2X.DLL,
# GLIDE3X.DLL and OPENGL32.DLL): under TCG a `cpu: pentium3` guest takes an invalid-opcode fault in
# them ("This program has performed an illegal operation" on the first Glide call). Under KVM the
# host CPU runs them whatever the guest's CPUID says. Releases built for the Pentium say so in
# VERSION.txt ("built for i586"); those run on the plain pentium3.
TCG_CPU_FEATURES = "+sse2,+sse3,+ssse3,+sse4.1,+sse4.2,+popcnt"
BASELINE_RE = re.compile(r"^built for (i[3-6]86)\b", re.M)


def drivers_baseline(drv_dir):
    """The guest CPU the unpacked drivers were built for ("i586"), from VERSION.txt; None when it
    doesn't say (the older releases, built for x86-64-v2, or a build without VERSION.txt)."""
    vt = os.path.join(drv_dir, "version.txt")
    if not os.path.exists(vt):
        return None
    with open(vt, errors="replace") as f:
        m = BASELINE_RE.search(f.read())
    return m.group(1) if m else None


def guest_cpu(accel, baseline=None):
    """The guest CPU for --cpu auto: the VM's pentium3; under TCG with the x86-64-v2 extensions
    unless the drivers were built for an older CPU."""
    return "pentium3" if accel == "kvm" or baseline else f"pentium3,{TCG_CPU_FEATURES}"


OFFSCREEN_RE = re.compile(r"(glidept|mesapt): offscreen closed after ([\d.]+) s: (\d+) swaps \(([\d.]+) per s\), "
                          r"(\d+) reads of ([\d.]+) ms average.*?(\d+) frames to the console, ([\d.]+) ms after")
# With a GL display (--display egl), the line after it: how many frames went as a dmabuf
DMABUF_RE = re.compile(r"[^\n]*\n(glidept|mesapt): dmabuf scanout: (\d+) frames copied to the dmabuf in ([\d.]+) ms "
                       r"average, the display's update ([\d.]+) ms a frame, (\d+) held while the display was busy, "
                       r"(\d+) frames read back instead")
# On the line after that, with two scanout buffers (qemu-3dfx and wsh-openglide from Stage 2's fourth slice)
DOUBLE_RE = re.compile(r"[^\n]*\n(glidept|mesapt): dmabuf scanout: double-buffered, (\d+) of the held frames "
                       r"replaced")
# mesapt, offscreen: the display timer fired without a swap and the frame stays (once per pause)
HELD_RE = re.compile(r"offscreen: no swap for (\d+) ms, the frame stays")


def offscreen_stats(qemu_log):
    """The offscreen windows QEMU reported on closing them (qemu-3dfx's glidept and mesapt lines), in
    order: device, seconds open, swaps, swaps per second, reads, read ms average, frames to the
    console, ms from read to console; with a dmabuf scanout also the frames copied to the dmabuf, the
    copy's ms average, the display's ms per frame and the frames read back instead, and whether it
    was double-buffered (with how many held frames a newer one replaced)."""
    out = []
    for m in OFFSCREEN_RE.finditer(qemu_log):
        o = {"device": m.group(1), "open_s": float(m.group(2)), "swaps": int(m.group(3)),
             "swaps_per_s": float(m.group(4)), "reads": int(m.group(5)), "read_ms": float(m.group(6)),
             "frames_to_console": int(m.group(7)), "console_ms": float(m.group(8))}
        d = DMABUF_RE.match(qemu_log, m.start())
        if d and d.group(1) == o["device"]:
            o.update({"dmabuf_frames": int(d.group(2)), "dmabuf_ms": float(d.group(3)),
                      "display_ms": float(d.group(4)), "held": int(d.group(5)), "read_back": int(d.group(6))})
            db = DOUBLE_RE.match(qemu_log, d.end())
            o["double_buffered"] = bool(db and db.group(1) == o["device"])
            if o["double_buffered"]:
                o["replaced"] = int(db.group(2))
        out.append(o)
    return out


# What a binary says when it can show the pass-through without an SDL window: the Glide offscreen
# display (stage 1), the Mesa one (stage 1b); the strings e2e/3dfx/test.sh looks for
GLIDE_OFFSCREEN_MARK = b"offscreen %dx%d, frames to"
MESA_OFFSCREEN_MARK = b"rendering offscreen, EGL"


def select_tests(spec, display, binary):
    """The tests to run: spec as given, or for "auto" the ones the binary can show (headless: Glide
    with its offscreen display, OpenGL with the Mesa one; with SDL all three)."""
    if spec != "auto":
        return [t.strip() for t in spec.split(",") if t.strip()]
    if display == "sdl":
        return list(TESTS)
    tests = []
    if GLIDE_OFFSCREEN_MARK in binary:
        tests += ["glide2", "glide3"]
    if MESA_OFFSCREEN_MARK in binary:
        tests.append("opengl")
    return tests


def qemu_command(args, raw, serial, mon, vnc):
    """The device set of the PVE VM the template was installed in (cpu: pentium3, 512 MB, scsihw: lsi
    with the disk on scsi0, vga: std,mesa=1, rtl8139, AC97, tablet), at PVE's PCI addresses: Windows
    98 identifies a PCI device by its slot, and a device it hasn't seen there starts the new-hardware
    wizard, which waits for input."""
    accel = args.accel
    if accel == "auto":
        accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
    cpu = args.cpu
    if cpu == "auto":
        cpu = guest_cpu(accel, getattr(args, "drivers_baseline", None))
    args.cpu_used = cpu
    cmd = [args.qemu, "-name", "win98-3dfx", "-machine", f"pc,accel={accel}", "-cpu", cpu,
           "-m", str(args.memory), "-smp", "1", "-nodefaults", "-rtc", f"base={args.rtc_base}", "-boot", "c",
           "-no-reboot",
           "-device", "pci-bridge,id=pci.1,chassis_nr=1,bus=pci.0,addr=0x1e",
           "-device", "pci-bridge,id=pci.2,chassis_nr=2,bus=pci.0,addr=0x1f",
           "-device", "piix3-usb-uhci,id=uhci,bus=pci.0,addr=0x1.0x2",
           "-device", "usb-tablet,id=tablet,bus=uhci.0,port=1",
           "-device", "VGA,id=vga,bus=pci.0,addr=0x2",
           "-device", "virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x3",
           "-audiodev", "none,id=snd0",
           "-device", "AC97,id=audio0,bus=pci.0,addr=0x4,audiodev=snd0",
           "-device", "lsi,id=scsihw0,bus=pci.0,addr=0x5",
           "-drive", f"file={raw},if=none,id=drive-scsi0,format=raw,cache=unsafe",
           "-device", "scsi-hd,bus=scsihw0.0,scsi-id=0,drive=drive-scsi0,id=scsi0,bootindex=100",
           "-netdev", "user,id=net0,restrict=on",
           "-device", "rtl8139,netdev=net0,id=net0dev,bus=pci.0,addr=0x12,mac=bc:24:11:3d:f0:98",
           "-chardev", f"file,id=com1,path={serial}", "-device", "isa-serial,chardev=com1",
           "-monitor", f"unix:{mon},server=on,wait=off"]
    if args.display == "sdl":
        cmd += ["-display", "sdl"]
    elif args.display == "egl":
        cmd += ["-display", "egl-headless", "-vnc", f"unix:{vnc}"]
    else:
        cmd += ["-display", "none", "-vnc", f"unix:{vnc}"]
    return cmd, accel


class Monitor:
    def __init__(self, path):
        self.path = path

    def cmd(self, line, wait=0.3):
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(5)
                s.connect(self.path)
                time.sleep(0.1)
                s.recv(65536)
                s.sendall(line.encode() + b"\n")
                time.sleep(wait)
                return s.recv(65536).decode(errors="replace")
        except OSError as e:
            return f"(monitor: {e})"

    def screendump(self, path):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        self.cmd(f"screendump {path}")
        for _ in range(50):
            if os.path.exists(path) and os.path.getsize(path) > 15:
                break
            time.sleep(0.1)
        time.sleep(0.2)
        return os.path.exists(path)


class Qmp:
    """A VM's QMP socket (PVE: /var/run/qemu-server/<vmid>.qmp), one connection per command, as
    qemu-server uses it."""

    def __init__(self, path):
        self.path = path

    def cmd(self, execute, **arguments):
        """The command's "return" value; raises OSError or RuntimeError (its "error")."""
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(10)
            s.connect(self.path)
            f = s.makefile("rwb")

            def reply():
                while True:
                    line = f.readline()
                    if not line:
                        raise OSError("QMP: connection closed")
                    msg = json.loads(line)
                    if "return" in msg or "error" in msg:
                        return msg

            f.readline()  # the greeting
            for name, a in (("qmp_capabilities", {}), (execute, arguments)):
                f.write(json.dumps({"execute": name, "arguments": a}).encode() + b"\n")
                f.flush()
                msg = reply()
                if "error" in msg:
                    raise RuntimeError(f"QMP {name}: {msg['error'].get('desc', msg['error'])}")
            return msg["return"]

    def screendump(self, path):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        try:
            self.cmd("screendump", filename=path)
        except (OSError, RuntimeError):
            return False
        return os.path.exists(path) and os.path.getsize(path) > 15


# --- DES, for the VNC authentication of PVE's console (a VNC password is always on there) ------------

_DES_IP = [58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
           64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
           61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7]
_DES_FP = [40, 8, 48, 16, 56, 24, 64, 32, 39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
           37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27,
           34, 2, 42, 10, 50, 18, 58, 26, 33, 1, 41, 9, 49, 17, 57, 25]
_DES_E = [32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17,
          16, 17, 18, 19, 20, 21, 20, 21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1]
_DES_P = [16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10, 2, 8, 24, 14, 32, 27, 3, 9,
          19, 13, 30, 6, 22, 11, 4, 25]
_DES_PC1 = [57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3,
            60, 52, 44, 36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37,
            29, 21, 13, 5, 28, 20, 12, 4]
_DES_PC2 = [14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2,
            41, 52, 31, 37, 47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36, 29, 32]
_DES_SHIFTS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_DES_S = [[int(x) for x in s.split()] for s in (
    "14 4 13 1 2 15 11 8 3 10 6 12 5 9 0 7 0 15 7 4 14 2 13 1 10 6 12 11 9 5 3 8 "
    "4 1 14 8 13 6 2 11 15 12 9 7 3 10 5 0 15 12 8 2 4 9 1 7 5 11 3 14 10 0 6 13",
    "15 1 8 14 6 11 3 4 9 7 2 13 12 0 5 10 3 13 4 7 15 2 8 14 12 0 1 10 6 9 11 5 "
    "0 14 7 11 10 4 13 1 5 8 12 6 9 3 2 15 13 8 10 1 3 15 4 2 11 6 7 12 0 5 14 9",
    "10 0 9 14 6 3 15 5 1 13 12 7 11 4 2 8 13 7 0 9 3 4 6 10 2 8 5 14 12 11 15 1 "
    "13 6 4 9 8 15 3 0 11 1 2 12 5 10 14 7 1 10 13 0 6 9 8 7 4 15 14 3 11 5 2 12",
    "7 13 14 3 0 6 9 10 1 2 8 5 11 12 4 15 13 8 11 5 6 15 0 3 4 7 2 12 1 10 14 9 "
    "10 6 9 0 12 11 7 13 15 1 3 14 5 2 8 4 3 15 0 6 10 1 13 8 9 4 5 11 12 7 2 14",
    "2 12 4 1 7 10 11 6 8 5 3 15 13 0 14 9 14 11 2 12 4 7 13 1 5 0 15 10 3 9 8 6 "
    "4 2 1 11 10 13 7 8 15 9 12 5 6 3 0 14 11 8 12 7 1 14 2 13 6 15 0 9 10 4 5 3",
    "12 1 10 15 9 2 6 8 0 13 3 4 14 7 5 11 10 15 4 2 7 12 9 5 6 1 13 14 0 11 3 8 "
    "9 14 15 5 2 8 12 3 7 0 4 10 1 13 11 6 4 3 2 12 9 5 15 10 11 14 1 7 6 0 8 13",
    "4 11 2 14 15 0 8 13 3 12 9 7 5 10 6 1 13 0 11 7 4 9 1 10 14 3 5 12 2 15 8 6 "
    "1 4 11 13 12 3 7 14 10 15 6 8 0 5 9 2 6 11 13 8 1 4 10 7 9 5 0 15 14 2 3 12",
    "13 2 8 4 6 15 11 1 10 9 3 14 5 0 12 7 1 15 13 8 10 3 7 4 12 5 6 11 0 14 9 2 "
    "7 11 4 1 9 12 14 2 0 6 10 13 15 3 5 8 2 1 14 7 4 10 8 13 15 12 9 0 3 5 6 11")]


def _des_perm(v, table, width):
    out = 0
    for p in table:
        out = (out << 1) | ((v >> (width - p)) & 1)
    return out


def des_encrypt(key, block):
    """One 8-byte block of DES (ECB): all the VNC authentication needs, and not in Python's library."""
    k = _des_perm(int.from_bytes(key, "big"), _DES_PC1, 64)
    c, d = k >> 28, k & 0xFFFFFFF
    subkeys = []
    for s in _DES_SHIFTS:
        c = ((c << s) | (c >> (28 - s))) & 0xFFFFFFF
        d = ((d << s) | (d >> (28 - s))) & 0xFFFFFFF
        subkeys.append(_des_perm((c << 28) | d, _DES_PC2, 56))
    v = _des_perm(int.from_bytes(block, "big"), _DES_IP, 64)
    left, right = v >> 32, v & 0xFFFFFFFF
    for sk in subkeys:
        x = _des_perm(right, _DES_E, 32) ^ sk
        f = 0
        for i in range(8):
            six = (x >> (42 - 6 * i)) & 0x3F
            f = (f << 4) | _DES_S[i][(((six & 0x20) >> 4) | (six & 1)) * 16 + ((six >> 1) & 0xF)]
        left, right = right, left ^ _des_perm(f, _DES_P, 32)
    return _des_perm((right << 32) | left, _DES_FP, 64).to_bytes(8, "big")


def vnc_auth_response(password, challenge):
    """The VNC authentication's reply: the 16-byte challenge encrypted with the password (8 bytes,
    zero padded) as the DES key, each byte's bits mirrored, as RFB's VNC authentication has it."""
    key = bytes(int(f"{b:08b}"[::-1], 2) for b in password.encode()[:8].ljust(8, b"\0"))
    return des_encrypt(key, challenge[:8]) + des_encrypt(key, challenge[8:16])


def vnc_grab(path, password=None):
    """The console's picture as the VNC server at path sends it, as (width, height, rgb) or None (RFB
    3.8, raw encoding; no authentication, or the VNC authentication with password, as on PVE). For
    --display egl: while qemu-3dfx's dmabuf is scanned out, egl-headless reads it into a surface of
    its own for VNC, and QEMU's screendump has none."""
    def recv(s, n):
        b = b""
        while len(b) < n:
            c = s.recv(n - len(b))
            if not c:
                raise EOFError
            b += c
        return b
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(5)
            s.connect(path)
            recv(s, 12)
            s.sendall(b"RFB 003.008\n")
            types = recv(s, recv(s, 1)[0])
            if password is not None and 2 in types:
                s.sendall(b"\x02")
                s.sendall(vnc_auth_response(password, recv(s, 16)))
            elif 1 in types:
                s.sendall(b"\x01")
            else:
                return None
            if struct.unpack(">I", recv(s, 4))[0] != 0:
                return None
            s.sendall(b"\x01")
            w, h = struct.unpack(">HH", recv(s, 4))
            recv(s, 16)
            recv(s, struct.unpack(">I", recv(s, 4))[0])
            s.sendall(struct.pack(">BxxxBBBBHHHBBBxxx", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
            s.sendall(struct.pack(">BxHi", 2, 1, 0))
            s.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, w, h))
            fb = bytearray(w * h * 3)
            while True:
                t = recv(s, 1)[0]
                if t == 2:
                    continue
                if t == 3:
                    recv(s, 3)
                    recv(s, struct.unpack(">I", recv(s, 4))[0])
                    continue
                if t != 0:
                    return None
                recv(s, 1)
                for _ in range(struct.unpack(">H", recv(s, 2))[0]):
                    x, y, rw, rh, enc = struct.unpack(">HHHHi", recv(s, 12))
                    if enc != 0:
                        return None
                    px = recv(s, rw * rh * 4)
                    for r in range(rh):
                        o = ((y + r) * w + x) * 3
                        row = px[r * rw * 4:(r + 1) * rw * 4]
                        fb[o:o + rw * 3:3] = row[2::4]
                        fb[o + 1:o + rw * 3:3] = row[1::4]
                        fb[o + 2:o + rw * 3:3] = row[0::4]
                return w, h, bytes(fb)
    except (OSError, EOFError):
        return None


def write_ppm(path, w, h, pix):
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h) + pix)


def capture(args, mon, path):
    """What the VM shows, as (width, height, rgb) or None, also written to path (PPM): headless,
    QEMU's screendump of the console (egl: the VNC server's picture); with SDL, the QEMU window on
    the X display (xwd). With --pve: through the VM's QMP socket and PVE's VNC socket."""
    if args.pve:
        if args.display == "egl":
            # again before every grab: PVE's console (vncproxy) sets its own ticket as the password
            # whenever someone opens the VM's noVNC console
            try:
                mon.cmd("set_password", protocol="vnc", password=PVE_VNC_PASSWORD)
            except (OSError, RuntimeError):
                pass
            r = vnc_grab(pve_path(args.pve, "vnc"), PVE_VNC_PASSWORD)
            if r:
                write_ppm(path, *r)
            return r
        return read_ppm(path) if mon.screendump(path) else None
    if args.display == "egl":
        r = vnc_grab(os.path.join(args.private, "vnc.sock"))
        if r:
            write_ppm(path, *r)
        return r
    if args.display != "sdl":
        return read_ppm(path) if mon.screendump(path) else None
    tree = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True).stdout
    m = re.search(r"^\s+(0x[0-9a-f]+) \"[^\"]*QEMU[^\"]*\"", tree, re.M)
    if not m:
        return None
    r = subprocess.run(["xwd", "-silent", "-id", m.group(1)], capture_output=True)
    if r.returncode or not r.stdout:
        return None
    w, h, pix = parse_xwd(r.stdout)
    write_ppm(path, w, h, pix)
    return w, h, pix


def frame_check(args, scene, mon, priv, name):
    """The console (or the SDL window) while the frame is up: a dict for the summary. Headless the
    console must be the frame (640x480); an SDL window keeps the desktop's size and shows the frame
    scaled into it."""
    img = capture(args, mon, os.path.join(priv, f"{name}-frame.ppm"))
    source = "SDL window" if args.display == "sdl" else "screendump"
    if not img:
        return {"ok": False, "source": source, "error": "no capture"}
    w, h, pix = img
    sdl = args.display == "sdl"
    probes, bad = check_probes(scene, w, h, pix, scaled=sdl)
    return {"ok": bad == 0 and (sdl or (w, h) == (scene["w"], scene["h"])), "source": source,
            "size": f"{w}x{h}", "probes": probes, "mismatches": bad}


def after_check(args, scene, mon, priv, name, desktop):
    """The console (or the SDL window) after the program closed its 3D window: Windows' picture
    again, not the scene. A capture every half second for up to --vga-wait seconds: the VGA takes
    the console back on its next update."""
    path = os.path.join(priv, f"{name}-after.ppm")
    t0 = time.monotonic()
    res = {"ok": False, "error": "no capture"}
    while True:
        img = capture(args, mon, path)
        if img:
            w, h, pix = img
            _, bad = check_probes(scene, w, h, pix, scaled=args.display == "sdl")
            size = f"{w}x{h}"
            # the scene's probes no longer match (most of them), and the size is the desktop's
            ok = bad >= len(scene["probes"]) // 2 and (desktop is None or size == desktop)
            res = {"ok": ok, "size": size, "desktop": desktop, "scene_probes_matching": len(scene["probes"]) - bad,
                   "after_s": round(time.monotonic() - t0, 1)}
            if ok:
                return res
        if time.monotonic() - t0 > args.vga_wait:
            return res
        time.sleep(0.5)


class LocalVm:
    """QEMU started by the harness itself, as qemu_command() builds it."""

    def __init__(self, args, raw, serial_path):
        self.args, self.priv, self.out = args, args.private, args.out
        self.ogl = os.path.join(self.priv, "openglide")
        os.makedirs(self.ogl, exist_ok=True)
        self.cmd, self.accel = qemu_command(args, raw, serial_path, os.path.join(self.priv, "mon.sock"),
                                            os.path.join(self.priv, "vnc.sock"))
        self.mon = Monitor(os.path.join(self.priv, "mon.sock"))

    def start(self):
        env = dict(os.environ, OPENGLIDE_DIR=self.ogl)
        if self.args.display != "sdl":
            env.pop("DISPLAY", None)
        with open(os.path.join(self.out, "qemu-command.txt"), "w") as f:
            f.write(" ".join(self.cmd) + "\n")
        self.qlog = open(os.path.join(self.out, "qemu.log"), "wb")
        log(f"QEMU ({self.accel}, {self.args.display}): {' '.join(self.cmd)}")
        self.proc = subprocess.Popen(self.cmd, stdout=self.qlog, stderr=subprocess.STDOUT, env=env, cwd=self.priv)

    def exited(self):
        """None while QEMU runs, else how it ended."""
        rc = self.proc.poll()
        return None if rc is None else f"QEMU exited with status {rc}"

    def stop(self):
        if self.args.display != "sdl":
            self.mon.screendump(os.path.join(self.priv, "timeout.ppm"))
        self.mon.cmd("quit")
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def finish(self):
        """Waits for QEMU; True when it ended cleanly (Windows powered off)."""
        self.proc.wait()
        self.qlog.close()
        return self.proc.returncode == 0


PVE_VNC_PASSWORD = "w3dtest"


def pve_path(vmid, what):
    """qemu-server's per-VM paths: the QMP and VNC sockets, the pid file, OpenGLide's directory."""
    return {"qmp": f"/var/run/qemu-server/{vmid}.qmp", "vnc": f"/var/run/qemu-server/{vmid}.vnc",
            "pid": f"/var/run/qemu-server/{vmid}.pid", "openglide": f"/run/qemu-server/{vmid}-3dfx"}[what]


def pve_create_options(args, volume, serial_path, qlog_path, accel, cpu):
    """`qm create` options for the template's VM (the device set of qemu_command(); PVE adds the PCI
    bridges, the UHCI controller, the balloon and the PCI addresses itself). COM1 and QEMU's own
    messages go to files through args: with -D and a log mask, a daemonized QEMU keeps its stderr in
    the log file instead of /dev/null, and stderr is where qemu-3dfx prints its figures. The mask is
    `plugin` (output of TCG plugins, of which there are none), so nothing else lands there.

    Where the template's VM had its devices, so Windows finds no new hardware (the wizard waits for
    input): a machine version before 11.1 (from 11.1 on qemu-server adds a third PCI bridge, pci.4),
    no vmgenid (an ACPI device Windows 98 doesn't know), and AC97 through args at 00:04.0, where the
    template's VM had it (qemu-server's `audio0` now puts it behind the second bridge)."""
    vga = "std,mesa=1" + (",mesa-display=egl-headless" if args.display == "egl" else "")
    extra = (f"-audiodev none,id=snd0 -device AC97,id=audio0,bus=pci.0,addr=0x4,audiodev=snd0 "
             f"-chardev file,id=com1,path={serial_path} -device isa-serial,chardev=com1 -d plugin -D {qlog_path}")
    opts = ["--name", "win98-3dfx", "--ostype", "other", "--machine", "pc-i440fx-11.0", "--vmgenid", "0",
            "--cpu", cpu, "--memory", str(args.memory),
            "--sockets", "1", "--cores", "1", "--scsihw", "lsi", "--scsi0", f"{volume},cache=unsafe",
            "--boot", "order=scsi0", "--vga", vga, "--net0", "rtl8139=BC:24:11:3D:F0:98,bridge=vmbr0",
            "--tablet", "1", "--kvm", "1" if accel == "kvm" else "0", "--args", extra]
    if args.rtc_base == "localtime":
        opts += ["--localtime", "1"]
    elif args.rtc_base:
        opts += ["--startdate", args.rtc_base]
    return opts


class PveVm:
    """The VM created and started by PVE (--pve VMID): qm create, qm start, the console through QMP
    and PVE's VNC socket, qm stop and qm destroy."""

    def __init__(self, args, raw, serial_path):
        self.args, self.vmid, self.priv, self.out = args, str(args.pve), args.private, args.out
        accel = args.accel
        if accel == "auto":
            accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
        cpu = args.cpu
        if cpu == "auto":
            cpu = guest_cpu(accel, getattr(args, "drivers_baseline", None))
        if "," in cpu:
            raise SystemExit(f"win98-test: --pve: PVE's cpu option takes no CPUID flags ({cpu}); use KVM "
                             "or guest drivers built for i586")
        self.accel, args.cpu_used = accel, cpu
        self.qlog_path = os.path.join(self.out, "qemu.log")
        self.ogl = pve_path(self.vmid, "openglide")
        self.mon = Qmp(pve_path(self.vmid, "qmp"))
        # PVE attaches only disks of a storage: a directory storage of this run in PRIVATE, and the disk
        # copy hard-linked into it, so the copy stays when `qm destroy` deletes the storage's link
        self.storage = f"w3d{self.vmid}"
        self.store_dir = os.path.join(self.priv, "pve-storage")
        self.raw, self.disk = raw, os.path.join(self.store_dir, "images", self.vmid, "disk.raw")
        self.opts = pve_create_options(args, f"{self.storage}:{self.vmid}/disk.raw", serial_path, self.qlog_path,
                                       accel, cpu)
        self.pid = None

    def qm(self, *a, check=True):
        r = subprocess.run(["qm", *a], capture_output=True, text=True)
        if check and r.returncode:
            raise SystemExit(f"win98-test: qm {' '.join(a[:2])}: {(r.stderr or r.stdout).strip()}")
        return r

    def start(self):
        if self.qm("status", self.vmid, check=False).returncode == 0:
            raise SystemExit(f"win98-test: VM {self.vmid} exists already on this node: pick a free --pve VMID")
        open(self.qlog_path, "wb").close()
        os.makedirs(os.path.dirname(self.disk), exist_ok=True)
        if os.path.exists(self.disk):
            os.unlink(self.disk)
        os.link(self.raw, self.disk)
        subprocess.run(["pvesm", "remove", self.storage], capture_output=True)
        r = subprocess.run(["pvesm", "add", "dir", self.storage, "--path", self.store_dir, "--content", "images"],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"win98-test: pvesm add dir {self.storage}: {(r.stderr or r.stdout).strip()}")
        self.qm("create", self.vmid, *self.opts)
        with open(os.path.join(self.out, "qemu-command.txt"), "w") as f:
            f.write("qm create %s %s\n\n" % (self.vmid, " ".join(self.opts)))
            f.write(self.qm("showcmd", self.vmid, "--pretty").stdout)
        log(f"PVE VM {self.vmid} ({self.accel}, {self.args.display}): qm create {self.vmid} {' '.join(self.opts)}")
        self.qm("start", self.vmid)
        try:
            with open(pve_path(self.vmid, "pid")) as f:
                self.pid = int(f.read().split()[0])
        except (OSError, ValueError, IndexError):
            raise SystemExit(f"win98-test: no pid file of VM {self.vmid} after qm start")
        if self.args.display == "egl":
            # PVE's VNC socket always asks for a password (noVNC gets a ticket): set one of ours
            self.mon.cmd("set_password", protocol="vnc", password=PVE_VNC_PASSWORD)

    def exited(self):
        """None while the VM's QEMU runs (PVE gives no exit status)."""
        return None if os.path.exists(f"/proc/{self.pid}") else "the VM stopped (QEMU exited)"

    def stop(self):
        if self.args.display != "egl":
            self.mon.screendump(os.path.join(self.priv, "timeout.ppm"))
        self.qm("stop", self.vmid, check=False)

    def finish(self):
        """Copies OpenGLide's files and destroys the VM; True when the VM stopped by itself."""
        for name in ("OpenGLid.log", "OpenGLid.err"):
            if os.path.exists(os.path.join(self.ogl, name)):
                shutil.copyfile(os.path.join(self.ogl, name), os.path.join(self.out, name))
        stopped = self.exited() is not None
        self.qm("destroy", self.vmid, "--purge", "1", check=False)
        subprocess.run(["pvesm", "remove", self.storage], capture_output=True)
        shutil.rmtree(self.store_dir, ignore_errors=True)
        return stopped


def run_vm(args, scene, raw):
    priv, out = args.private, args.out
    serial_path = os.path.join(out, "serial.log")
    open(serial_path, "wb").close()
    vm = PveVm(args, raw, serial_path) if args.pve else LocalVm(args, raw, serial_path)
    t_start = time.monotonic()
    vm.start()
    mon = vm.mon
    ser = Serial(serial_path)
    res = {"accel": vm.accel, "display": args.display, "tests": {}, "events": []}
    if args.pve:
        res["pve_vmid"] = int(args.pve)
    for t in args.tests:
        res["tests"][t] = {"tag": TESTS[t][0], "guest": None, "frame": None, "after": None, "bench": None,
                           "lines": []}
    by_tag = {TESTS[t][0]: t for t in args.tests}
    desktop = None
    held_due = {}  # test -> when to check its frame again, late in a long hold
    deadline = t_start + args.timeout
    status = "running"
    while True:
        for tag, text in ser.poll():
            now = round(time.monotonic() - t_start, 1)
            log(f"[{now:7.1f}s] {tag}: {text}")
            if tag == "W3DRUN":
                if text.startswith("START"):
                    res["events"].append({"t": now, "what": "desktop (w3drun started)"})
                    res["boot_s"] = now
                    # the size of the desktop, as Windows reports it
                    m = re.search(r"screen (\d+x\d+)", text)
                    desktop = res["desktop"] = m.group(1) if m else None
                elif text.startswith(("EXIT", "TIMEOUT", "DONE", "SHUTDOWN")):
                    res["events"].append({"t": now, "what": text})
                    if text == "SHUTDOWN":
                        res["shutdown_s"] = now
                continue
            t = by_tag.get(tag)
            if not t:
                continue
            r = res["tests"][t]
            r["lines"].append(text)
            if text.startswith("START"):
                r["start_s"] = now
            elif text == "FRAME":
                r["frame_s"] = now
                if args.hold >= 6:
                    held_due[t] = time.monotonic() + args.hold - 1.5
                time.sleep(1)
                r["frame"] = frame_check(args, scene, mon, priv, t)
                log(f"{t}: frame in the console: {'ok' if r['frame']['ok'] else 'NO'} "
                    f"({r['frame'].get('size', '')} {r['frame'].get('mismatches', '')})")
            elif text.startswith("BENCH"):
                r["bench"] = parse_bench(text)
            elif text == "CLOSED":
                r["closed_s"] = now
                time.sleep(0.5)
                r["after"] = after_check(args, scene, mon, priv, t, desktop)
                log(f"{t}: after the 3D window: {r['after']}")
            elif verdict_of(text):
                r["guest"] = verdict_of(text)
        for t, due in list(held_due.items()):
            if time.monotonic() >= due:
                del held_due[t]
                r = res["tests"][t]
                h = r["held"] = frame_check(args, scene, mon, priv, f"{t}-held")
                h["at_s"] = round(time.monotonic() - t_start - r["frame_s"], 1)
                log(f"{t}: frame still in the console {h['at_s']} s after FRAME: "
                    f"{'ok' if h['ok'] else 'NO'} ({h.get('size', '')} {h.get('mismatches', '')})")
        ended = vm.exited()
        if ended:
            status = ended
            break
        if time.monotonic() > deadline:
            status = f"timeout after {args.timeout} s"
            vm.stop()
            break
        time.sleep(0.2)
    for tag, text in ser.poll():
        t = by_tag.get(tag)
        if t:
            res["tests"][t]["lines"].append(text)
            if verdict_of(text):
                res["tests"][t]["guest"] = verdict_of(text)
    clean = vm.finish()
    res["status"] = status
    res["total_s"] = round(time.monotonic() - t_start, 1)
    res["powered_off"] = "shutdown_s" in res and clean and not status.startswith("timeout")
    with open(os.path.join(out, "qemu.log"), errors="replace") as f:
        qlog = f.read()
    res["offscreen"] = offscreen_stats(qlog)
    res["display_timer_held"] = len(HELD_RE.findall(qlog))
    if not args.pve:
        for name in ("OpenGLid.log", "OpenGLid.err"):
            if os.path.exists(os.path.join(vm.ogl, name)):
                shutil.copyfile(os.path.join(vm.ogl, name), os.path.join(out, name))
    return res


def evaluate(res, tests):
    """Each test's verdict and the overall one."""
    all_ok = True
    for t in tests:
        r = res["tests"][t]
        why = []
        if r["guest"] != "PASS":
            why.append(f"guest: {r['guest'] or 'no verdict'}")
        if not r["frame"] or not r["frame"]["ok"]:
            why.append("the console didn't show the frame" if r["frame"] else "no frame")
        if r.get("held") and not r["held"]["ok"]:
            why.append(f"the held frame was gone {r['held'].get('at_s', '?')} s after FRAME")
        if r["after"] is None or r["after"]["ok"] is False:
            why.append("Windows didn't come back in the console" if r["after"] else "never closed")
        r["verdict"] = "PASS" if not why else "FAIL: " + "; ".join(why)
        all_ok &= not why
    return all_ok


def summary_md(res, info):
    lines = ["## qemu-3dfx in Windows 98 SE", "",
             f"Binary: `{info['qemu_version']}` (qemu-3dfx {info['qemu_rev']}), guest drivers {info['drivers_rev']} "
             f"(built for {info.get('drivers_baseline', 'x86-64-v2 (not stated)')}), "
             f"{res['accel']}, display {res['display']}, CPU {info['cpu']}"
             f"{', started by PVE (VM %d)' % res['pve_vmid'] if res.get('pve_vmid') else ''}", "",
             f"Boot to desktop {res.get('boot_s', '?')} s, total {res['total_s']} s, end: {res['status']}"
             f"{', powered off by Windows' if res.get('powered_off') else ''}", "",
             "| Test | Verdict | Guest | Console frame | Held frame | Windows back | Frame rate |",
             "|---|---|---|---|---|---|---|"]
    for t, r in res["tests"].items():
        fr = r["frame"] or {}
        af = r["after"] or {}
        bench = r["bench"]
        rate = "%s fps (%d frames in %d ms)" % (bench["fps"], bench["frames"], bench["ms"]) if bench else "-"
        back = "ok" if af.get("ok") else ("n/a" if af and af.get("ok") is None else "no")
        hf = r.get("held")
        held = "-" if not hf else f"{'ok' if hf.get('ok') else 'no'} at {hf.get('at_s', '?')} s"
        lines.append(f"| {t} | {r.get('verdict', '')} | {r['guest'] or '-'} | "
                     f"{'ok' if fr.get('ok') else 'no'} {fr.get('size', '')} | {held} | {back} {af.get('size', '')} | "
                     f"{rate} |")
    if res.get("offscreen"):
        lines += ["", "QEMU's offscreen windows (qemu-3dfx's own figures):", "",
                  "| Device | Open | Swaps | Reads | Read average | Read to console | As a dmabuf |",
                  "|---|---|---|---|---|---|---|"]
        for o in res["offscreen"]:
            dmabuf = (f"{o['dmabuf_frames']} frames, copy {o['dmabuf_ms']} ms, display {o['display_ms']} ms, "
                      f"{o['read_back']} read back" if "dmabuf_frames" in o else "-")
            if o.get("double_buffered"):
                dmabuf += f", double-buffered ({o['replaced']} held frames replaced)"
            lines.append(f"| {o['device']} | {o['open_s']} s | {o['swaps']} ({o['swaps_per_s']}/s) | {o['reads']} | "
                         f"{o['read_ms']} ms | {o['console_ms']} ms | {dmabuf} |")
    if res.get("display_timer_held"):
        lines += ["", f"QEMU kept a held OpenGL frame when the display timer fired {res['display_timer_held']} "
                  "time(s) (\"offscreen: no swap for ... the frame stays\")."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--template", required=True, help="the installed Windows 98 SE disk (raw, read only)")
    ap.add_argument("--drivers", required=True, help="qemu-3dfx-drivers-<rev>.zip, or its unpacked directory")
    ap.add_argument("--out", required=True, help="logs and the summary (our own text only)")
    ap.add_argument("--private", required=True, help="the disk copy and the screendumps (stay on this host)")
    ap.add_argument("--tests", default="auto", help="glide2, glide3, opengl, separated by commas; auto: those the "
                    "binary can show headless (opengl needs the Mesa offscreen display) or all with --display sdl")
    ap.add_argument("--display", choices=("vnc", "egl", "sdl"), default="vnc")
    ap.add_argument("--accel", choices=("auto", "tcg", "kvm"), default="auto")
    ap.add_argument("--cpu", default="auto", help="QEMU -cpu; auto: pentium3, under TCG with SSE2-SSE4.2 and POPCNT "
                    "when the drivers don't say they were built for i586 (the older, x86-64-v2 releases)")
    ap.add_argument("--memory", type=int, default=512)
    ap.add_argument("--rtc", default="auto", help="QEMU's -rtc base: auto (an hour after Windows last ran), "
                    "localtime or a date")
    ap.add_argument("--qemu", default="/usr/bin/qemu-system-x86_64-3dfx")
    ap.add_argument("--bin", default="/w3d/bin", help="the built test programs (build.sh)")
    ap.add_argument("--hold", type=int, default=5, help="seconds each frame stays up; from 6 the frame is checked "
                    "again 1.5 s before the end")
    ap.add_argument("--bench", type=int, default=2000, help="frames drawn after the check, for a frame rate")
    ap.add_argument("--delay", type=int, default=10, help="seconds w3drun waits after the desktop is up")
    ap.add_argument("--test-timeout", type=int, default=300, help="per test program, in the guest")
    ap.add_argument("--timeout", type=int, default=1500, help="the whole VM run")
    ap.add_argument("--keep-disk", action="store_true")
    ap.add_argument("--vga-wait", type=float, default=6, help="seconds for the console to show Windows again")
    ap.add_argument("--stay", action="store_true", help="leave Windows running after the tests (until --timeout)")
    ap.add_argument("--pve", type=int, metavar="VMID", help="run on this PVE node: PVE creates and starts the VM "
                    "with this (free) VMID (display vnc or egl)")
    ap.add_argument("--in-place", action="store_true", help="--template is already this run's own copy (in "
                    "--private): prepare and boot it instead of copying it")
    args = ap.parse_args(argv)
    if args.pve and args.display == "sdl":
        ap.error("--pve runs headless, as PVE does: --display vnc or egl")
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.private, exist_ok=True)

    if not os.access(args.qemu, os.X_OK):
        log(f"SKIP: no {args.qemu} (the optional 3dfx extra is missing)")
        return 77
    rev, version = qemu_rev(args.qemu)
    if not rev:
        log(f"SKIP: {args.qemu} names no qemu-3dfx revision")
        return 77
    with open(args.qemu, "rb") as f:
        binary = f.read()
    args.tests = select_tests(args.tests, args.display, binary)
    if not args.tests:
        log("SKIP: this binary can't show qemu-3dfx's output without an SDL window (no offscreen display)")
        return 77
    for t in args.tests:
        if t not in TESTS:
            ap.error(f"unknown test {t} ({', '.join(TESTS)})")
    log(f"tests: {', '.join(args.tests)}")
    with open(SCENE_H) as f:
        scene = parse_scene(f.read())
    drv_dir = os.path.join(args.private, "drivers")
    drv_rev = unpack_drivers(args.drivers, drv_dir)
    args.drivers_baseline = drivers_baseline(drv_dir)
    log(f"{version}; qemu-3dfx {rev}; guest drivers {drv_rev or 'unknown revision'}")
    if drv_rev and drv_rev != rev:
        log(f"ERROR: the guest drivers ({drv_rev}) are not the binary's revision ({rev}): the wrappers refuse it")
        return 2
    info = {"qemu_version": version, "qemu_rev": rev, "drivers_rev": drv_rev,
            "drivers_baseline": args.drivers_baseline or "x86-64-v2 (not stated)", "cpu": args.cpu,
            "tests": args.tests}

    raw = os.path.join(args.private, "disk.raw")
    t0 = time.monotonic()
    if args.in_place:
        raw = args.template
    else:
        subprocess.run(["cp", "--reflink=auto", "--sparse=always", args.template, raw], check=True)
    os.chmod(raw, 0o600)
    info["marked_clean"] = mark_clean(raw)
    fat, files = prepare_disk(args, raw, args.bin, drv_dir)
    info["files"] = files
    args.rtc_base = args.rtc
    if args.rtc == "auto":
        args.rtc_base = rtc_after([fat.listing("WINDOWS/SYSTEM.DAT"), fat.listing("WINDOWS/USER.DAT")]) or "localtime"
    info["rtc"] = args.rtc_base
    info["prepare_s"] = round(time.monotonic() - t0, 1)
    log(f"disk copy prepared in {info['prepare_s']} s: {files}")

    res = run_vm(args, scene, raw)
    info["cpu"] = args.cpu_used
    if fat.get("WIN3DFX/LOG.TXT", os.path.join(args.out, "guest-log.txt")):
        log("the guest's C:\\WIN3DFX\\LOG.TXT is in guest-log.txt")
    ok = evaluate(res, args.tests)
    res["info"] = info
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(res, f, indent=1)
    md = summary_md(res, info)
    with open(os.path.join(args.out, "summary.md"), "w") as f:
        f.write(md)
    print(md)
    if not args.keep_disk:
        os.unlink(raw)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
