#!/usr/bin/env python3
"""The Glide and OpenGL pass-through of qemu-3dfx in a real Windows 98 SE guest, end to end.

    win98_test.py --template WIN98SE.raw --drivers qemu-3dfx-drivers-<rev>.zip --out OUT --private PRIV \\
        [--tests glide2,glide3,opengl] [--display vnc|sdl] [--accel auto|tcg|kvm] [--bench N]

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
socket) or with an SDL window on an X display (--display sdl, Xvfb). The test programs print to COM1
(QEMU writes it to a file); on "<TAG>: FRAME" the harness takes a screendump of the console
(headless: where qemu-3dfx shows the frame) or a capture of the SDL window and checks the probes of
packages/wsh-openglide/tests/scene.h, the scene every 3dfx test draws; on "<TAG>: CLOSED" it
checks that the console shows Windows again (not the scene). A test passes when the guest program
reports PASS (its own read-back matched), the console showed the frame, and Windows came back.

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


def offscreen_stats(qemu_log):
    """The offscreen windows QEMU reported on closing them (qemu-3dfx's glidept and mesapt lines), in
    order: device, seconds open, swaps, swaps per second, reads, read ms average, frames to the
    console, ms from read to console."""
    out = []
    for m in OFFSCREEN_RE.finditer(qemu_log):
        out.append({"device": m.group(1), "open_s": float(m.group(2)), "swaps": int(m.group(3)),
                    "swaps_per_s": float(m.group(4)), "reads": int(m.group(5)), "read_ms": float(m.group(6)),
                    "frames_to_console": int(m.group(7)), "console_ms": float(m.group(8))})
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


def write_ppm(path, w, h, pix):
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h) + pix)


def capture(args, mon, path):
    """What the VM shows, as (width, height, rgb) or None, also written to path (PPM): headless,
    QEMU's screendump of the console; with SDL, the QEMU window on the X display (xwd)."""
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


def run_vm(args, scene, raw):
    priv, out = args.private, args.out
    serial_path = os.path.join(out, "serial.log")
    mon_path = os.path.join(priv, "mon.sock")
    vnc_path = os.path.join(priv, "vnc.sock")
    ogl = os.path.join(priv, "openglide")
    os.makedirs(ogl, exist_ok=True)
    open(serial_path, "wb").close()
    cmd, accel = qemu_command(args, raw, serial_path, mon_path, vnc_path)
    env = dict(os.environ, OPENGLIDE_DIR=ogl)
    if args.display != "sdl":
        env.pop("DISPLAY", None)
    with open(os.path.join(out, "qemu-command.txt"), "w") as f:
        f.write(" ".join(cmd) + "\n")
    qlog = open(os.path.join(out, "qemu.log"), "wb")
    log(f"QEMU ({accel}, {args.display}): {' '.join(cmd)}")
    t_start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=qlog, stderr=subprocess.STDOUT, env=env, cwd=priv)
    mon = Monitor(mon_path)
    ser = Serial(serial_path)
    res = {"accel": accel, "display": args.display, "tests": {}, "events": []}
    for t in args.tests:
        res["tests"][t] = {"tag": TESTS[t][0], "guest": None, "frame": None, "after": None, "bench": None,
                           "lines": []}
    by_tag = {TESTS[t][0]: t for t in args.tests}
    desktop = None
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
        if proc.poll() is not None:
            status = f"QEMU exited with status {proc.returncode}"
            break
        if time.monotonic() > deadline:
            status = f"timeout after {args.timeout} s"
            if args.display != "sdl":
                mon.screendump(os.path.join(priv, "timeout.ppm"))
            mon.cmd("quit")
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        time.sleep(0.2)
    for tag, text in ser.poll():
        t = by_tag.get(tag)
        if t:
            res["tests"][t]["lines"].append(text)
            if verdict_of(text):
                res["tests"][t]["guest"] = verdict_of(text)
    proc.wait()
    qlog.close()
    res["status"] = status
    res["total_s"] = round(time.monotonic() - t_start, 1)
    res["powered_off"] = "shutdown_s" in res and status.startswith("QEMU exited with status 0")
    with open(os.path.join(out, "qemu.log"), errors="replace") as f:
        res["offscreen"] = offscreen_stats(f.read())
    for name in ("OpenGLid.log", "OpenGLid.err"):
        if os.path.exists(os.path.join(ogl, name)):
            shutil.copyfile(os.path.join(ogl, name), os.path.join(out, name))
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
        if r["after"] is None or r["after"]["ok"] is False:
            why.append("Windows didn't come back in the console" if r["after"] else "never closed")
        r["verdict"] = "PASS" if not why else "FAIL: " + "; ".join(why)
        all_ok &= not why
    return all_ok


def summary_md(res, info):
    lines = ["## qemu-3dfx in Windows 98 SE", "",
             f"Binary: `{info['qemu_version']}` (qemu-3dfx {info['qemu_rev']}), guest drivers {info['drivers_rev']} "
             f"(built for {info.get('drivers_baseline', 'x86-64-v2 (not stated)')}), "
             f"{res['accel']}, display {res['display']}, CPU {info['cpu']}", "",
             f"Boot to desktop {res.get('boot_s', '?')} s, total {res['total_s']} s, end: {res['status']}"
             f"{', powered off by Windows' if res.get('powered_off') else ''}", "",
             "| Test | Verdict | Guest | Console frame | Windows back | Frame rate |", "|---|---|---|---|---|---|"]
    for t, r in res["tests"].items():
        fr = r["frame"] or {}
        af = r["after"] or {}
        bench = r["bench"]
        rate = "%s fps (%d frames in %d ms)" % (bench["fps"], bench["frames"], bench["ms"]) if bench else "-"
        back = "ok" if af.get("ok") else ("n/a" if af and af.get("ok") is None else "no")
        lines.append(f"| {t} | {r.get('verdict', '')} | {r['guest'] or '-'} | "
                     f"{'ok' if fr.get('ok') else 'no'} {fr.get('size', '')} | {back} {af.get('size', '')} | {rate} |")
    if res.get("offscreen"):
        lines += ["", "QEMU's offscreen windows (qemu-3dfx's own figures):", "",
                  "| Device | Open | Swaps | Reads | Read average | Read to console |", "|---|---|---|---|---|---|"]
        for o in res["offscreen"]:
            lines.append(f"| {o['device']} | {o['open_s']} s | {o['swaps']} ({o['swaps_per_s']}/s) | {o['reads']} | "
                         f"{o['read_ms']} ms | {o['console_ms']} ms |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--template", required=True, help="the installed Windows 98 SE disk (raw, read only)")
    ap.add_argument("--drivers", required=True, help="qemu-3dfx-drivers-<rev>.zip, or its unpacked directory")
    ap.add_argument("--out", required=True, help="logs and the summary (our own text only)")
    ap.add_argument("--private", required=True, help="the disk copy and the screendumps (stay on this host)")
    ap.add_argument("--tests", default="auto", help="glide2, glide3, opengl, separated by commas; auto: those the "
                    "binary can show headless (opengl needs the Mesa offscreen display) or all with --display sdl")
    ap.add_argument("--display", choices=("vnc", "sdl"), default="vnc")
    ap.add_argument("--accel", choices=("auto", "tcg", "kvm"), default="auto")
    ap.add_argument("--cpu", default="auto", help="QEMU -cpu; auto: pentium3, under TCG with SSE2-SSE4.2 and POPCNT "
                    "when the drivers don't say they were built for i586 (the older, x86-64-v2 releases)")
    ap.add_argument("--memory", type=int, default=512)
    ap.add_argument("--rtc", default="auto", help="QEMU's -rtc base: auto (an hour after Windows last ran), "
                    "localtime or a date")
    ap.add_argument("--qemu", default="/usr/bin/qemu-system-x86_64-3dfx")
    ap.add_argument("--bin", default="/w3d/bin", help="the built test programs (build.sh)")
    ap.add_argument("--hold", type=int, default=5, help="seconds each frame stays up")
    ap.add_argument("--bench", type=int, default=2000, help="frames drawn after the check, for a frame rate")
    ap.add_argument("--delay", type=int, default=10, help="seconds w3drun waits after the desktop is up")
    ap.add_argument("--test-timeout", type=int, default=300, help="per test program, in the guest")
    ap.add_argument("--timeout", type=int, default=1500, help="the whole VM run")
    ap.add_argument("--keep-disk", action="store_true")
    ap.add_argument("--vga-wait", type=float, default=6, help="seconds for the console to show Windows again")
    ap.add_argument("--stay", action="store_true", help="leave Windows running after the tests (until --timeout)")
    args = ap.parse_args(argv)
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
