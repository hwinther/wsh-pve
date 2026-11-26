#!/usr/bin/env python3
"""The Glide pass-through of qemu-3dfx from DOS: FreeDOS, our DJGPP test programs and qemu-3dfx's
DOS wrappers GLIDE2X.DXE and GLIDE3X.DXE, end to end, with free software only.

    dos_test.py --drivers qemu-3dfx-drivers-<rev>.zip --bin DIR --out OUT \\
        [--profiles none,xms,emm386] [--accel auto|tcg|kvm] [--cpu pentium3] [--bench N] [--hold S] [--demo-bench N]
        [--no-glide3] [--no-space-audio] [--pve VMID]

The guest is the boot floppy of the FreeDOS 1.4 Floppy Edition (the zip given by FREEDOS_ZIP, or
downloaded once into FREEDOS_CACHE; the pins are e2e/sparc/targets_dos.py's, downloaded and checked by
e2e/sparc/fetch_media.py), with mtools putting onto a copy of it:

  - FDCONFIG.SYS, which loads the memory managers of the profile and runs GLIDE.BAT instead of the
    installer; GLIDE.BAT sends the console to COM1 (CTTY COM1), runs the test program and powers the
    VM off (FDAPM POWEROFF, which is on the floppy);
  - in A:\\GLIDE: GLIDEDOS.EXE and GLID3DOS.EXE (--bin: glidedos.c for Glide 2 and Glide 3, built
    by build.sh in the DJGPP image), GLIDE2X.DXE and GLIDE3X.DXE from the guest drivers (--drivers:
    the qemu-3dfx-drivers-<rev> release of wsh-pve, the revision the binary names; --dxe and --dxe3
    take other ones), and FreeDOS's own CWSDPMI.EXE (the DPMI host a DJGPP
    program needs), HIMEMX.EXE and JEMM386.EXE. Those three are not on the boot floppy: they are
    taken out of the Floppy Edition's package archive on its other six floppies (FreeDOS's SLICER
    format: each file a gzip stream after its name) and checked against the sha256 of the files a
    FreeDOS 1.4 installation from these floppies has.

Profiles (--profiles, each one boot): none (no memory manager: CWSDPMI switches to protected mode
itself, with raw/INT 15h memory), xms (HIMEMX: CWSDPMI over XMS), emm386 (HIMEMX and JEMM386 with
expanded memory, as FreeDOS's boot menu entry 3 loads it: CWSDPMI runs as a VCPI client).

QEMU (qemu-system-x86_64-3dfx, the published pve-qemu-kvm's) boots it headless as PVE runs a VM with
`vga: std,mesa=1` (no display, a VNC server, the HMP monitor on a socket), COM1 to a file. On
"GLIDEDOS: FRAME" the harness checks the probes of packages/wsh-openglide/tests/scene.h in QEMU's
screendump of the console, where qemu-3dfx shows the frame (stage 1, read back), and on
"GLIDEDOS: CLOSED" (the wrapper's grSstWinClose returns once QEMU closed the window) that the
console shows the VGA again (DOS's text screen, not the scene). Not on QEMU's "offscreen closed":
its stderr reaches the log late, after the next program's window was up. A profile passes when the program reports PASS (its own read-back matched), the console had
the frame and the VGA came back.

Next in the same boot, GLIDE.BAT runs GLID3DOS.EXE, the same test through Glide 3 and GLIDE3X.DXE
(its lines start with "GLIDE3DOS:"), with wait=3: DOS's text screen for 3 s before its window opens,
for the check after GLIDEDOS.EXE. It is checked the same way: its verdict, the probes in the console on
"GLIDE3DOS: FRAME" and the VGA back after "GLIDE3DOS: CLOSED". With it a profile passes only when
the Glide 3 test passed too. --no-glide3 leaves it out.

Then, in the same boot, GLIDE.BAT runs the demo (e2e/3dfx/demo, WSHDEMO.EXE from --bin, built by
its build-dos.sh) with `-check -bench N -hold S -wait 3 -nocom` (--demo-bench N, 0 leaves it out;
-wait shows DOS's text screen for 3 s first, -nocom leaves COM1 to CTTY): it draws a fixed
frame of each of its parts, reads each back and checks its probes ("WSHDEMO: CHECK part=<name>
PASS"), prints each part's frame rate, holds the last frame and prints its probes ("WSHDEMO: PROBE x
y rrggbb"), which the harness checks in the console on "WSHDEMO: FRAME". With the demo, a profile
passes only when the demo passed too (its checks, the console's probes, the VGA back afterwards).

With --pve VMID the harness runs on a PVE node (the e2e PVE container) and PVE starts the VM: the
floppy goes to storage `local` (content floppy), `qm create` with `vga: std,mesa=1`, `floppy0`,
COM1 and QEMU's messages to files through `args`, `qm start`; the console is read through the VM's
QMP socket. The VM is destroyed afterwards.

Last in the same boot, GLIDE.BAT runs wshspace (e2e/3dfx/space, WSHSPACE.EXE from --bin, built by its
build-dos.sh) with `-audiotest -nocom` and BLASTER=A220 I5 D1 H5 T6: the audio signature
(e2e/wisp/audiosig.h) through the game's own Sound Blaster backend (8-bit stereo auto-init DMA at
22050 Hz on the DSP 4.x of QEMU's `-device sb16`, iobase 220h, IRQ 5, DMA 1, which the backend polls
without an interrupt handler), recorded by `-audiodev wav` into space-audio.wav and checked by
e2e/audio/wavcheck.py --signature (per segment and channel the frequency, the duration, no gaps,
channels not swapped). With the demo it then runs `WSHDEMO.EXE -audiotest -nocom`, the same
signature through the same backend (e2e/3dfx/audio/snd_dos.h) in wshdemo, which plays its music with
it: the recording then has the signature twice. With it a profile passes only when wshspace (and
wshdemo) say PASS and the recording has the signatures. --no-space-audio leaves it out; with --pve it
is left out (PVE's audio0 has no sb16).

OUT gets summary.json, summary.md, and per profile the serial log, QEMU's output and the
screendumps (they show only FreeDOS and our scene). Exit status 0 when every profile passed, 1 when
one failed, 2 on a setup error, 77 when the binary has no qemu-3dfx or can't show Glide headless.
Copyright 2026 WsHosting ENK, GPL-3.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "win98"))
# the FreeDOS pins and their download (the image has both files at the same relative path)
sys.path.append(os.path.join(HERE, "..", "..", "sparc"))
# wavcheck.py (the audio signature) from e2e/audio, at the same relative path in the image
sys.path.append(os.path.join(HERE, "..", "..", "audio"))
import win98_test as w3d  # noqa: E402  (the scene, PPM, probes, monitors and QEMU's figures)
import fetch_media  # noqa: E402
import targets_dos  # noqa: E402
import wavcheck  # noqa: E402

# The FreeDOS 1.4 Floppy Edition: the zip (targets_dos.FREEDOS_ZIP) and its boot floppy (MEDIA)
FREEDOS_BOOT = targets_dos.MEDIA["freedos14-boot.img"]
FREEDOS_DISKS = [f"144m/x86DSK{n:02d}.img" for n in range(1, 7)]
# Files from the package archive (CWSDPMI 7b, HIMEMX, JEMM): the sha256 of those a FreeDOS 1.4
# installation from these floppies puts into C:\FREEDOS\BIN
PACKAGE_FILES = {
    "CWSDPMI.EXE": "2de899fecaa90632b8b9bdfc0305cb0375e59ae252c37e32d06c1ed3f98a8f44",
    "HIMEMX.EXE": "abd7a5f5cae2a3a34e577e20097076062dd9177bb754058b35d754537d32fbbd",
    "JEMM386.EXE": "a7baf9623c773fe99cc53a062756ead33fea40c36c7856e57ae1fe4b709ba8a7",
}
PROFILES = {
    "none": [],
    "xms": ["DEVICE=A:\\GLIDE\\HIMEMX.EXE"],
    "emm386": ["DEVICE=A:\\GLIDE\\HIMEMX.EXE", "DEVICE=A:\\GLIDE\\JEMM386.EXE X=TEST NOVME NOINVLPG"],
}
TAG = "GLIDEDOS"
TAG3 = "GLIDE3DOS"  # GLID3DOS.EXE (glidedos.c built for Glide 3), after GLIDEDOS.EXE (--no-glide3: not)
DEMO = "WSHDEMO"  # e2e/3dfx/demo, run after GLIDEDOS.EXE in the same boot (--demo-bench 0: not)
SPACE = "WSHSPACE"  # e2e/3dfx/space -audiotest, last in the same boot (--no-space-audio: not)
SPACE_BLASTER = "A220 I5 D1 H5 T6"  # QEMU's sb16 defaults
LINE_RE = re.compile(r"^(%s|%s|%s|%s): (.*)$" % (TAG, TAG3, DEMO, SPACE))
DEMO_PROBE_RE = re.compile(r"PROBE (\d+) (\d+) ([0-9a-f]{6})$")
DEMO_CHECK_RE = re.compile(r"CHECK part=(\w+) (PASS|FAIL)(.*)$")
DEMO_BENCH_RE = re.compile(r"BENCH part=(\w+) frames=(\d+) secs=([\d.]+) fps=([\d.]+)$")
DEMO_PARTS = ("cube", "tunnel", "plasma")
PVE_FLOPPY_DIR = "/var/lib/vz/template/floppy"


def log(msg):
    print(f"dos-test: {msg}", flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mtools(*cmd, check=True):
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1", MTOOLS_NO_VFAT="1")
    return subprocess.run(cmd, check=check, env=env, capture_output=True, text=True)


# --- FreeDOS ---------------------------------------------------------------------------------------

def freedos_zip(cache):
    """The Floppy Edition zip: FREEDOS_ZIP (checked, never downloaded over), else the pinned one in
    `cache`, downloaded when it isn't there. `cache` exists afterwards (freedos_files keeps the
    floppy and the package files there)."""
    os.makedirs(cache, exist_ok=True)
    try:
        if os.environ.get("FREEDOS_ZIP"):
            return fetch_media.checked(os.environ["FREEDOS_ZIP"], fetch_media.FREEDOS_ZIP_NAME)
        log(f"FreeDOS zip in {cache} (downloaded when it isn't the pinned one)")
        return fetch_media.fetch(fetch_media.FREEDOS_ZIP_NAME, cache)
    except RuntimeError as e:
        raise SystemExit(f"dos-test: {e}")


def slicer_extract(data, name, want):
    """A file out of the Floppy Edition's SLICER archive (its parts concatenated): the name, a NUL and
    a gzip stream of the file. The first copy whose content has the sha256 `want`; None if none."""
    pat = re.compile(re.escape(name.encode()) + b"\x00\x1f\x8b", re.I)
    for m in pat.finditer(data):
        try:
            d = zlib.decompressobj(31)
            content = d.decompress(data[m.end() - 2:m.end() - 2 + (1 << 20)])
        except zlib.error:
            continue
        if d.eof and hashlib.sha256(content).hexdigest() == want:
            return content
    return None


def freedos_files(cache, work):
    """The boot floppy and the package files, cached by sha256 in `cache`."""
    boot = os.path.join(cache, "freedos14-boot.img")
    files = {n: os.path.join(cache, n) for n in PACKAGE_FILES}
    if (os.path.exists(boot) and sha256(boot) == FREEDOS_BOOT["sha256"]
            and all(os.path.exists(p) and sha256(p) == PACKAGE_FILES[n] for n, p in files.items())):
        return boot, files
    zpath = freedos_zip(cache)
    parts = os.path.join(work, "slicer")
    os.makedirs(parts, exist_ok=True)
    with zipfile.ZipFile(zpath) as zf:
        with zf.open(FREEDOS_BOOT["zip"]) as src, open(boot, "wb") as dst:
            shutil.copyfileobj(src, dst)
        for disk in FREEDOS_DISKS:
            img = os.path.join(work, os.path.basename(disk))
            with zf.open(disk) as src, open(img, "wb") as dst:
                shutil.copyfileobj(src, dst)
            mtools("mcopy", "-n", "-i", img, "::/FREEDOS.*", parts)
            os.unlink(img)
    if sha256(boot) != FREEDOS_BOOT["sha256"]:
        raise SystemExit(f"dos-test: {FREEDOS_BOOT['zip']}: sha256 isn't {FREEDOS_BOOT['sha256']}")
    # FREEDOS.001, .002, ... in order (FREEDOS.SAF is the index)
    numbered = sorted((p for p in os.listdir(parts) if re.match(r"(?i)freedos\.\d{3}$", p)),
                      key=lambda p: int(p[-3:]))
    data = b"".join(open(os.path.join(parts, p), "rb").read() for p in numbered)
    for n, want in PACKAGE_FILES.items():
        content = slicer_extract(data, n, want)
        if content is None:
            raise SystemExit(f"dos-test: {n} with sha256 {want} isn't in the Floppy Edition's archive")
        with open(files[n], "wb") as f:
            f.write(content)
    shutil.rmtree(parts, ignore_errors=True)
    return boot, files


def fdconfig(profile):
    lines = ["SWITCHES=/N /F", "LASTDRIVE=Z", "FILES=20"] + PROFILES[profile]
    lines.append("SHELL=\\FREEDOS\\BIN\\COMMAND.COM \\FREEDOS\\BIN /E:1024 /P=\\GLIDE.BAT")
    return "\r\n".join(lines) + "\r\n"


def glide_bat(args, profile):
    """COM1 gets the console; MEM (and JEMM386's status) say what the profile set up for CWSDPMI."""
    status = ["A:\\GLIDE\\JEMM386.EXE"] if "JEMM386" in " ".join(PROFILES[profile]) else []
    lines = ["@ECHO OFF", "CTTY COM1", "ECHO glide.bat: start", "A:\\FREEDOS\\BIN\\MEM.EXE", *status, "A:",
             "CD \\GLIDE", "SET LD_LIBRARY_PATH=A:/GLIDE", f"GLIDEDOS.EXE hold={args.hold} bench={args.bench}",
             "ECHO glide.bat: exit %ERRORLEVEL%"]
    if args.glide3:
        # wait=3: DOS's text screen a while first, for the check after GLIDEDOS.EXE's window closed
        lines += [f"GLID3DOS.EXE wait=3 hold={args.hold} bench={args.bench}", "ECHO glide.bat: glide3 exit %ERRORLEVEL%"]
    if args.demo_bench > 0:
        # -nocom: CTTY COM1 sends its output there already; -wait: DOS's text screen shows a while first
        lines += [f"WSHDEMO.EXE -check -bench {args.demo_bench} -hold {args.hold} -wait 3 -nocom",
                  "ECHO glide.bat: demo exit %ERRORLEVEL%"]
    if args.space_audio:
        lines += [f"SET BLASTER={SPACE_BLASTER}", "WSHSPACE.EXE -audiotest -nocom",
                  "ECHO glide.bat: space exit %ERRORLEVEL%"]
        if args.demo_bench > 0:
            lines += ["WSHDEMO.EXE -audiotest -nocom", "ECHO glide.bat: demo audio exit %ERRORLEVEL%"]
    lines.append("A:\\FREEDOS\\BIN\\FDAPM.COM POWEROFF")
    return "\r\n".join(lines) + "\r\n"


def make_floppy(path, boot, files, glidedos, dxe, dxe3, profile, args):
    shutil.copyfile(boot, path)
    os.chmod(path, 0o644)
    tmp = os.path.dirname(path)
    for name, text in (("FDCONFIG.SYS", fdconfig(profile)), ("GLIDE.BAT", glide_bat(args, profile))):
        p = os.path.join(tmp, name)
        with open(p, "w", newline="") as f:
            f.write(text)
        mtools("mcopy", "-o", "-i", path, p, f"::/{name}")
    mtools("mmd", "-i", path, "::/GLIDE")
    put = {"GLIDEDOS.EXE": glidedos, "GLIDE2X.DXE": dxe, **files}
    if args.glide3:
        put["GLID3DOS.EXE"] = os.path.join(args.bin, "GLID3DOS.EXE")
        put["GLIDE3X.DXE"] = dxe3
    if args.demo_bench > 0:
        put["WSHDEMO.EXE"] = os.path.join(args.bin, "WSHDEMO.EXE")
    if args.space_audio:
        put["WSHSPACE.EXE"] = os.path.join(args.bin, "WSHSPACE.EXE")
    for name, src in put.items():
        mtools("mcopy", "-o", "-i", path, src, f"::/GLIDE/{name}")
    return {n: {"bytes": os.path.getsize(p), "sha256": sha256(p)} for n, p in put.items()}


# --- the drivers -----------------------------------------------------------------------------------

def dxe_from_drivers(src, dest):
    """GLIDE2X.DXE, GLIDE3X.DXE (None when the drivers have none) and VERSION.txt of a
    qemu-3dfx-drivers zip (or an unpacked release directory)."""
    os.makedirs(dest, exist_ok=True)
    want = ("glide2x.dxe", "glide3x.dxe", "version.txt")
    found = {}
    if os.path.isdir(src):
        for root, _, names in os.walk(src):
            for n in names:
                if n.lower() in want:
                    found[n.lower()] = os.path.join(root, n)
    else:
        with zipfile.ZipFile(src) as zf:
            for info in zf.infolist():
                n = os.path.basename(info.filename).lower()
                if n in want:
                    found[n] = os.path.join(dest, n)
                    with zf.open(info) as s, open(found[n], "wb") as d:
                        shutil.copyfileobj(s, d)
    if "glide2x.dxe" not in found:
        raise SystemExit(f"dos-test: no glide2x.dxe in {src}")
    version = open(found["version.txt"], errors="replace").read() if "version.txt" in found else ""
    return found["glide2x.dxe"], found.get("glide3x.dxe"), version


# --- a run -----------------------------------------------------------------------------------------

class Serial:
    def __init__(self, path):
        self.path, self.pos, self.partial, self.lines = path, 0, b"", []

    def poll(self):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except FileNotFoundError:
            return []
        self.pos += len(data)
        buf = self.partial + data
        *complete, self.partial = re.split(rb"\r?\n", buf)
        new = []
        for raw in complete:
            m = LINE_RE.match(raw.decode("latin-1").strip("\r\x00"))
            if m:
                new.append((m.group(1), m.group(2)))
                self.lines.append((m.group(1), m.group(2)))
        return new


def qemu_command(args, floppy, serial, mon, vnc, accel, wav=None):
    """wav: a Sound Blaster 16 (QEMU's defaults: 220h, IRQ 5, DMA 1 and 5) recorded into this file."""
    sound = ["-device", "sb16,audiodev=snd0", "-audiodev", "wav,id=snd0,path=" + wav.replace(",", ",,")] if wav else []
    return [args.qemu, "-machine", "pc", "-accel", accel, "-cpu", args.cpu, "-m", str(args.memory),
            "-nodefaults", "-vga", "std", "-display", "none", "-vnc", f"unix:{vnc}",
            "-monitor", f"unix:{mon},server=on,wait=off", "-no-reboot",
            "-drive", f"if=floppy,index=0,format=raw,file={floppy}", "-boot", "a",
            "-serial", f"file:{serial}", *sound]


class LocalVm:
    def __init__(self, args, d, floppy, serial, accel):
        self.d, self.ogl = d, os.path.join(d, "openglide")
        os.makedirs(self.ogl, exist_ok=True)
        self.cmd = qemu_command(args, floppy, serial, os.path.join(d, "mon.sock"), os.path.join(d, "vnc.sock"), accel,
                                os.path.join(d, "space-audio.wav") if args.space_audio else None)
        self.mon = w3d.Monitor(os.path.join(d, "mon.sock"))
        self.qlog_path = os.path.join(d, "qemu.log")

    def start(self):
        with open(os.path.join(self.d, "qemu-command.txt"), "w") as f:
            f.write(" ".join(self.cmd) + "\n")
        self.qlog = open(self.qlog_path, "wb")
        env = dict(os.environ, OPENGLIDE_DIR=self.ogl)
        env.pop("DISPLAY", None)
        self.proc = subprocess.Popen(self.cmd, stdout=self.qlog, stderr=subprocess.STDOUT, env=env, cwd=self.d)

    def running(self):
        return self.proc.poll() is None

    def stop(self):
        self.mon.cmd("quit")
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def finish(self):
        self.proc.wait()
        self.qlog.close()
        return self.proc.returncode == 0


class PveVm:
    """PVE starts the VM (--pve VMID): the floppy in storage `local`, qm create, qm start."""

    def __init__(self, args, d, floppy, serial, accel):
        self.vmid, self.d = str(args.pve), d
        self.qlog_path = os.path.join(d, "qemu.log")
        self.mon = w3d.Qmp(w3d.pve_path(self.vmid, "qmp"))
        self.ogl = w3d.pve_path(self.vmid, "openglide")
        self.img = f"glidedos{self.vmid}.img"
        os.makedirs(PVE_FLOPPY_DIR, exist_ok=True)
        shutil.copyfile(floppy, os.path.join(PVE_FLOPPY_DIR, self.img))
        cfg = json.loads(subprocess.run(["pvesh", "get", "/storage/local", "--output-format", "json"],
                                        check=True, capture_output=True, text=True).stdout)
        types = set(cfg.get("content", "").split(",")) - {""}
        if "floppy" not in types:
            subprocess.run(["pvesm", "set", "local", "--content", ",".join(sorted(types | {"floppy"}))], check=True)
        # COM1 and QEMU's own messages to files (see win98_test.pve_create_options: -D with a log mask
        # keeps a daemonized QEMU's stderr, where qemu-3dfx prints its figures)
        self.opts = ["--name", "glidedos", "--ostype", "other", "--machine", "pc", "--cpu", args.cpu,
                     "--memory", str(args.memory), "--balloon", "0", "--tablet", "0", "--vga", "std,mesa=1",
                     "--floppy0", f"local:floppy/{self.img}", "--boot", "order=floppy0",
                     "--kvm", "1" if accel == "kvm" else "0",
                     "--args", f"-chardev file,id=com1,path={serial} -device isa-serial,chardev=com1 "
                               f"-d plugin -D {self.qlog_path}"]
        self.pid = None

    def qm(self, *a, check=True):
        r = subprocess.run(["qm", *a], capture_output=True, text=True)
        if check and r.returncode:
            raise SystemExit(f"dos-test: qm {' '.join(a[:2])}: {(r.stderr or r.stdout).strip()}")
        return r

    def start(self):
        if self.qm("status", self.vmid, check=False).returncode == 0:
            raise SystemExit(f"dos-test: VM {self.vmid} exists already on this node: pick a free --pve VMID")
        open(self.qlog_path, "wb").close()
        self.qm("create", self.vmid, *self.opts)
        with open(os.path.join(self.d, "qemu-command.txt"), "w") as f:
            f.write("qm create %s %s\n\n" % (self.vmid, " ".join(self.opts)))
            f.write(self.qm("showcmd", self.vmid, "--pretty").stdout)
        self.qm("start", self.vmid)
        with open(w3d.pve_path(self.vmid, "pid")) as f:
            self.pid = int(f.read().split()[0])

    def running(self):
        return os.path.exists(f"/proc/{self.pid}")

    def stop(self):
        self.qm("stop", self.vmid, check=False)

    def finish(self):
        for name in ("OpenGLid.log", "OpenGLid.err"):
            if os.path.exists(os.path.join(self.ogl, name)):
                shutil.copyfile(os.path.join(self.ogl, name), os.path.join(self.d, name))
        stopped = not self.running()
        self.qm("destroy", self.vmid, "--purge", "1", check=False)
        try:
            os.unlink(os.path.join(PVE_FLOPPY_DIR, self.img))
        except FileNotFoundError:
            pass
        return stopped


def frame_check(scene, mon, path):
    if not mon.screendump(path):
        return {"ok": False, "error": "no screendump"}
    w, h, pix = w3d.read_ppm(path)
    probes, bad = w3d.check_probes(scene, w, h, pix)
    return {"ok": bad == 0 and (w, h) == (scene["w"], scene["h"]), "size": f"{w}x{h}", "probes": probes,
            "mismatches": bad}


def after_check(scene, mon, path, wait=5):
    """The VGA again once the Glide window closed: DOS's text screen, not the scene."""
    t0 = time.monotonic()
    res = {"ok": False, "error": "no screendump"}
    while time.monotonic() - t0 < wait:
        if mon.screendump(path):
            w, h, pix = w3d.read_ppm(path)
            _, bad = w3d.check_probes(scene, w, h, pix)
            res = {"ok": bad >= len(scene["probes"]) // 2 and (w, h) != (scene["w"], scene["h"]), "size": f"{w}x{h}",
                   "scene_probes_matching": len(scene["probes"]) - bad, "after_s": round(time.monotonic() - t0, 1)}
            if res["ok"]:
                break
        time.sleep(0.5)
    return res


def demo_frame_check(mon, path, probes):
    """The demo's held frame in the console: the probes it printed for it (x, y, rrggbb)."""
    if not probes:
        return {"ok": False, "error": "the demo printed no probes"}
    if not mon.screendump(path):
        return {"ok": False, "error": "no screendump"}
    w, h, pix = w3d.read_ppm(path)
    out, bad = [], 0
    for x, y, want in probes:
        o = (y * w + x) * 3
        got = pix[o:o + 3] if x < w and y < h else b"\0\0\0"
        ok = all(abs(got[c] - int(want[2 * c:2 * c + 2], 16)) <= 24 for c in range(3))
        bad += not ok
        out.append({"x": x, "y": y, "want": want, "got": got.hex(), "ok": ok})
    return {"ok": bad == 0, "size": f"{w}x{h}", "probes": out, "mismatches": bad}


def demo_line(res, text, mon, d, scene, t0):
    """One WSHDEMO line into res["demo"]."""
    r = res["demo"]
    m = DEMO_CHECK_RE.match(text)
    if m:
        r["checks"][m.group(1)] = m.group(2) + m.group(3)
        return
    m = DEMO_BENCH_RE.match(text)
    if m:
        r["bench"][m.group(1)] = float(m.group(4))
        return
    m = DEMO_PROBE_RE.match(text)
    if m:
        r["probes"].append((int(m.group(1)), int(m.group(2)), m.group(3)))
    elif text == "FRAME" and r["frame"] is None:
        time.sleep(1)
        r["frame"] = demo_frame_check(mon, os.path.join(d, "demo-frame.ppm"), r["probes"])
        log(f"{res['profile']}: demo's held frame in the console: {'probes match' if r['frame']['ok'] else r['frame']}")
    elif text == "CLOSED":
        time.sleep(0.5)
        r["after"] = after_check(scene, mon, os.path.join(d, "demo-after.ppm"))
    elif text.startswith("VERSION "):
        r["version"] = text[8:]
    elif w3d.verdict_of(text):
        r["verdict"] = w3d.verdict_of(text)


def demo_passed(r):
    return bool(r["verdict"] == "PASS" and all(r["checks"].get(p, "").startswith("PASS") for p in DEMO_PARTS)
                and r["frame"] and r["frame"]["ok"] and r["after"] and r["after"]["ok"])


def space_audio_check(rs, wav):
    """The recording of wshspace -audiotest (and wshdemo -audiotest after it): wavcheck's signature
    check, one signature into each of rs, in order."""
    try:
        sig = wavcheck.signatures(wav, len(rs))
    except (OSError, ValueError) as e:
        for r in rs:
            r["wav"] = {"ok": False, "reasons": [str(e)]}
        return
    with open(os.path.splitext(wav)[0] + ".json", "w") as f:
        json.dump(sig, f, indent=1)
    for i, r in enumerate(rs):
        w = {"ok": sig["ok"], "reasons": sig["reasons"]}
        if i < len(sig["signatures"]):
            s = sig["signatures"][i]
            w.update(duration_s=s["duration_s"], max_gap_ms=max(s["max_gap_ms"]), swapped=s["swapped"], mono=s["mono"],
                     left_hz=[g["left_hz"] for g in s["segments"]], right_hz=[g["right_hz"] for g in s["segments"]])
        r["wav"] = w


def glide3_line(res, text, mon, d, scene):
    """One GLIDE3DOS line into res["glide3"]: the same test as GLIDEDOS.EXE's, through Glide 3."""
    r = res["glide3"]
    if text == "FRAME" and r["frame"] is None:
        time.sleep(1)
        r["frame"] = frame_check(scene, mon, os.path.join(d, "glide3-frame.ppm"))
        log(f"{res['profile']}: Glide 3 screendump: {'probes match' if r['frame']['ok'] else r['frame']}")
    elif text == "CLOSED" and r["after"] is None:
        time.sleep(0.5)
        r["after"] = after_check(scene, mon, os.path.join(d, "glide3-after.ppm"))
    elif w3d.parse_bench(text):
        r["bench"] = w3d.parse_bench(text)
    elif w3d.verdict_of(text):
        r["verdict"] = w3d.verdict_of(text)


def glide3_passed(r):
    return bool(r["verdict"] == "PASS" and r["frame"] and r["frame"]["ok"] and r["after"] and r["after"]["ok"])


def run_profile(args, scene, profile, boot, files, dxe, dxe3, accel):
    d = os.path.join(args.out, profile)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    floppy = os.path.join(d, "glidedos.img")
    contents = make_floppy(floppy, boot, files, os.path.join(args.bin, "GLIDEDOS.EXE"), dxe, dxe3, profile, args)
    serial_path = os.path.join(d, "serial.log")
    open(serial_path, "wb").close()
    vm = (PveVm if args.pve else LocalVm)(args, d, floppy, serial_path, accel)
    res = {"profile": profile, "config": PROFILES[profile], "floppy": contents, "verdict": None, "frame": None,
           "after": None, "bench": None}
    if args.glide3:
        res["glide3"] = {"verdict": None, "frame": None, "after": None, "bench": None}
    if args.demo_bench > 0:
        res["demo"] = {"checks": {}, "bench": {}, "probes": [], "frame": None, "after": None, "verdict": None}
    if args.space_audio:
        res["space_audio"] = {"audiotest": None, "verdict": None, "wav": None}
        if args.demo_bench > 0:
            res["demo_audio"] = {"audiotest": None, "verdict": None, "wav": None}
    log(f"{profile}: booting FreeDOS ({'PVE VM ' + str(args.pve) if args.pve else 'QEMU'}, {accel}, cpu {args.cpu})")
    t0 = time.monotonic()
    vm.start()
    serial = Serial(serial_path)
    audio_demo = False
    try:
        while True:
            for tag, text in serial.poll():
                log(f"{profile}: {tag}: {text}")
                if tag == DEMO and text.endswith(" mode=audiotest"):
                    audio_demo = True  # wshdemo's -audiotest run: the lines that follow are its
                elif tag == DEMO and audio_demo:
                    if "demo_audio" in res:
                        if text.startswith("AUDIOTEST "):
                            res["demo_audio"]["audiotest"] = text[10:]
                        elif text == "PASS" or text.startswith("FAIL "):
                            res["demo_audio"]["verdict"] = text
                elif tag == TAG3:
                    if "glide3" in res:
                        glide3_line(res, text, vm.mon, d, scene)
                elif tag == DEMO:
                    if "demo" in res:
                        demo_line(res, text, vm.mon, d, scene, t0)
                elif tag == SPACE:
                    if "space_audio" in res:
                        if text.startswith("AUDIOTEST "):
                            res["space_audio"]["audiotest"] = text[10:]
                        elif text == "PASS" or text.startswith("FAIL "):
                            res["space_audio"]["verdict"] = text
                elif text == "FRAME" and res["frame"] is None:
                    time.sleep(1)
                    res["frame"] = frame_check(scene, vm.mon, os.path.join(d, "frame.ppm"))
                    res["frame_s"] = round(time.monotonic() - t0, 1)
                    log(f"{profile}: screendump: {'probes match' if res['frame']['ok'] else res['frame']}")
                elif text == "CLOSED" and res["after"] is None:
                    time.sleep(0.5)
                    res["after"] = after_check(scene, vm.mon, os.path.join(d, "after.ppm"))
                elif w3d.parse_bench(text):
                    res["bench"] = w3d.parse_bench(text)
                elif w3d.verdict_of(text):
                    res["verdict"] = w3d.verdict_of(text)
            if not vm.running():
                break
            if time.monotonic() - t0 > args.timeout:
                res["timeout"] = True
                log(f"{profile}: timeout after {args.timeout} s")
                vm.mon.screendump(os.path.join(d, "timeout.ppm"))
                vm.stop()
                break
            time.sleep(0.2)
    finally:
        res["powered_off"] = vm.finish()
    serial.poll()
    res["seconds"] = round(time.monotonic() - t0, 1)
    qlog = open(vm.qlog_path, errors="replace").read()
    res["offscreen"] = w3d.offscreen_stats(qlog)
    # the profile is what the guest has: XMS from HIMEMX, VCPI from JEMM386 (CWSDPMI then runs as a
    # VCPI client); without either CWSDPMI takes the memory raw (INT 15h)
    text = open(serial_path, "rb").read().decode("latin-1")
    # (FreeDOS's MEM says "Extended (XMS)" without an XMS driver too, all of it used then)
    m = re.search(r"Extended \(XMS\)\s+[\d,]+K\s+[\d,]+K\s+([\d,]+)K", text)
    res["xms"] = bool(m and m.group(1).replace(",", "") != "0")
    res["vcpi"] = "VCPI is On" in text
    res["profile_ok"] = res["xms"] == (profile != "none") and res["vcpi"] == (profile == "emm386")
    res["passed"] = bool(res["verdict"] == "PASS" and res["frame"] and res["frame"]["ok"]
                         and res["after"] and res["after"]["ok"] and res["profile_ok"])
    demo = ""
    if "glide3" in res:
        g3 = res["glide3"]
        g3["passed"] = glide3_passed(g3)
        res["passed"] = res["passed"] and g3["passed"]
        demo = (f", Glide 3 {'PASS' if g3['passed'] else 'FAIL'} (guest {g3['verdict']}, frame {g3['frame'] and g3['frame']['ok']}, "
                f"VGA after {g3['after'] and g3['after']['ok']})")
    if "demo" in res:
        res["demo"]["passed"] = demo_passed(res["demo"])
        res["passed"] = res["passed"] and res["demo"]["passed"]
        demo += f", demo {'PASS' if res['demo']['passed'] else 'FAIL'} {res['demo']['checks']} {res['demo']['bench']}"
    if "space_audio" in res:
        audio = [("wshspace", res["space_audio"])] + ([("wshdemo", res["demo_audio"])] if "demo_audio" in res else [])
        space_audio_check([a for _, a in audio], os.path.join(d, "space-audio.wav"))
        for name, sa in audio:
            sa["passed"] = bool(sa["verdict"] == "PASS" and sa["wav"]["ok"])
            res["passed"] = res["passed"] and sa["passed"]
            demo += (f", {name} -audiotest {'PASS' if sa['passed'] else 'FAIL'} ({sa['audiotest']}; "
                     f"{'signature ok' if sa['wav']['ok'] else '; '.join(sa['wav']['reasons'])})")
    log(f"{profile}: {'PASS' if res['passed'] else 'FAIL'} (XMS {res['xms']}, VCPI {res['vcpi']}, guest {res['verdict']}, "
        f"frame {res['frame'] and res['frame']['ok']}, VGA after {res['after'] and res['after']['ok']}{demo})")
    return res


def summary_md(info, results):
    lines = ["## Glide from DOS (FreeDOS, GLIDE2X.DXE%s)" % (" and GLIDE3X.DXE" if any("glide3" in r for r in results) else ""), "",
             f"{info['qemu_version']}; guest drivers {info['drivers']}; {info['accel']}, cpu {info['cpu']}"
             f"{', PVE VM ' + str(info['pve']) if info['pve'] else ''}", "",
             "| Profile | Memory | Result | Guest | Console frame | VGA after | Frames/s | Read ms |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        f, a, b = r["frame"], r["after"], r["bench"]
        off = r["offscreen"][0] if r["offscreen"] else None
        mem = "+".join(x for x, on in (("XMS", r["xms"]), ("VCPI", r["vcpi"])) if on) or "raw"
        lines.append("| %s | %s%s | %s | %s | %s | %s | %s | %s |" % (
            r["profile"], mem, "" if r["profile_ok"] else " (unexpected)", "pass" if r["passed"] else "FAIL", r["verdict"] or "no verdict",
            ("probes match" if f["ok"] else f"{f.get('mismatches', '?')} mismatches {f.get('size', '')}") if f else "no frame",
            (f"yes ({a['size']})" if a["ok"] else f"no ({a.get('size', a.get('error'))})") if a else "not seen",
            f"{b['fps']:.0f}" if b else "-", f"{off['read_ms']}" if off else "-"))
    g3s = [r for r in results if "glide3" in r]
    if g3s:
        lines += ["", "Glide 3 (GLID3DOS.EXE, GLIDE3X.DXE):", "",
                  "| Profile | Result | Guest | Console frame | VGA after | Frames/s |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for r in g3s:
            g3 = r["glide3"]
            f, a, b = g3["frame"], g3["after"], g3["bench"]
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                r["profile"], "pass" if g3["passed"] else "FAIL", g3["verdict"] or "no verdict",
                ("probes match" if f["ok"] else f"{f.get('mismatches', '?')} mismatches {f.get('size', '')}") if f else "no frame",
                (f"yes ({a['size']})" if a["ok"] else f"no ({a.get('size', a.get('error'))})") if a else "not seen",
                f"{b['fps']:.0f}" if b else "-"))
    demos = [r for r in results if "demo" in r]
    if demos:
        lines += ["", "The demo (WSHDEMO.EXE -check -bench N, e2e/3dfx/demo):", "",
                  "| Profile | Demo | Checks | Console probes | VGA after | " + " | ".join(f"{p} frames/s" for p in DEMO_PARTS) + " |",
                  "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in DEMO_PARTS) + " |"]
        for r in demos:
            dm = r["demo"]
            checks = ", ".join(f"{p} {dm['checks'].get(p, 'none').split(' ')[0].lower()}" for p in DEMO_PARTS)
            f, a = dm["frame"], dm["after"]
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                r["profile"], "pass" if dm["passed"] else f"FAIL ({dm['verdict'] or 'no verdict'})", checks,
                ("match" if f["ok"] else f"{f.get('mismatches', f.get('error'))} mismatches") if f else "no frame",
                ("yes" if a["ok"] else "no") if a else "not seen",
                " | ".join(f"{dm['bench'][p]:.0f}" if p in dm["bench"] else "-" for p in DEMO_PARTS)))
    audio = [r for r in results if "space_audio" in r]
    if audio:
        lines += ["", "-audiotest of wshspace (e2e/3dfx/space) and wshdemo (e2e/3dfx/demo) on QEMU's sb16, the audio "
                  "signature checked by wavcheck.py:", "",
                  "| Profile | Program | Result | Verdict | Duration s | Longest gap ms | Left Hz (8 segments) | Right Hz (8 segments) |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in audio:
            for name, key in (("wshspace", "space_audio"), ("wshdemo", "demo_audio")):
                if key not in r:
                    continue
                sa, w = r[key], r[key]["wav"] or {}
                lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    r["profile"], name, "pass" if sa["passed"] else "FAIL: " + "; ".join(w.get("reasons", [])),
                    sa["verdict"] or "no verdict", w.get("duration_s", "-"), w.get("max_gap_ms", "-"),
                    " ".join(f"{f:.0f}" if f else "-" for f in w.get("left_hz", [])),
                    " ".join(f"{f:.0f}" if f else "-" for f in w.get("right_hz", []))))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--drivers", required=True, help="qemu-3dfx-drivers-<rev>.zip or its unpacked directory")
    ap.add_argument("--bin", required=True, help="the directory with GLIDEDOS.EXE and GLID3DOS.EXE (build.sh) and "
                    "WSHDEMO.EXE (demo/build-dos.sh)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dxe", help="this GLIDE2X.DXE instead of the drivers' one")
    ap.add_argument("--dxe3", help="this GLIDE3X.DXE instead of the drivers' one")
    ap.add_argument("--glide3", action=argparse.BooleanOptionalAction, default=True,
                    help="GLID3DOS.EXE (in --bin) with GLIDE3X.DXE after GLIDEDOS.EXE in each boot (default on)")
    ap.add_argument("--profiles", default="none,xms,emm386")
    ap.add_argument("--accel", default="auto", choices=["auto", "kvm", "tcg"])
    ap.add_argument("--cpu", default="pentium3", help="the guest CPU (the drivers are built for i586)")
    ap.add_argument("--memory", type=int, default=64)
    ap.add_argument("--bench", type=int, default=300)
    ap.add_argument("--hold", type=int, default=5)
    ap.add_argument("--demo-bench", type=int, default=300, help="frames per part for the demo (WSHDEMO.EXE in --bin) "
                    "after the test program; 0: no demo")
    ap.add_argument("--space-audio", action=argparse.BooleanOptionalAction, default=True,
                    help="wshspace -audiotest (WSHSPACE.EXE in --bin) on an sb16 last in each boot (default on)")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--qemu", default="/usr/bin/qemu-system-x86_64-3dfx")
    ap.add_argument("--pve", type=int, help="PVE starts the VM, with this VM ID")
    args = ap.parse_args()
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    for p in profiles:
        if p not in PROFILES:
            ap.error(f"unknown profile {p} (one of {', '.join(PROFILES)})")
    os.makedirs(args.out, exist_ok=True)
    args.out = os.path.abspath(args.out)
    if args.glide3 and not os.path.exists(os.path.join(args.bin, "GLID3DOS.EXE")):
        log(f"WARNING: no GLID3DOS.EXE in {args.bin}: the Glide 3 test is left out")
        args.glide3 = False
    if args.demo_bench > 0 and not os.path.exists(os.path.join(args.bin, "WSHDEMO.EXE")):
        log(f"WARNING: no WSHDEMO.EXE in {args.bin}: the demo is left out")
        args.demo_bench = 0
    if args.space_audio and not os.path.exists(os.path.join(args.bin, "WSHSPACE.EXE")):
        log(f"WARNING: no WSHSPACE.EXE in {args.bin}: wshspace -audiotest is left out")
        args.space_audio = False
    if args.space_audio and args.pve:
        log("wshspace -audiotest is left out with --pve (no sb16 in PVE's audio0)")
        args.space_audio = False

    if not os.access(args.qemu, os.X_OK):
        log(f"SKIP: no {args.qemu} (the optional 3dfx extra is missing)")
        return 77
    rev, version = w3d.qemu_rev(args.qemu)
    if not rev:
        log(f"SKIP: {args.qemu} has no qemu-3dfx")
        return 77
    if w3d.GLIDE_OFFSCREEN_MARK not in open(args.qemu, "rb").read():
        log(f"SKIP: {args.qemu} can't show Glide without an SDL window (no offscreen display)")
        return 77
    work = os.path.join(args.out, ".work")
    os.makedirs(work, exist_ok=True)
    dxe, dxe3, drv_version = dxe_from_drivers(args.drivers, os.path.join(work, "drivers"))
    if f"{rev}-" not in drv_version and rev not in os.path.basename(os.path.normpath(args.drivers)):
        log(f"WARNING: the drivers ({os.path.basename(args.drivers)}) don't name the binary's revision {rev}")
    if args.dxe:
        dxe = args.dxe
    if args.dxe3:
        dxe3 = args.dxe3
    if args.glide3 and not dxe3:
        raise SystemExit(f"dos-test: no glide3x.dxe in {args.drivers} (--no-glide3 leaves the Glide 3 test out)")
    boot, files = freedos_files(os.environ.get("FREEDOS_CACHE", "/var/cache/glidedos-freedos"), work)
    scene = w3d.parse_scene(open(w3d.SCENE_H).read())
    accel = args.accel
    if accel == "auto":
        accel = "kvm" if os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg"
    info = {"qemu_version": version, "rev": rev, "drivers": os.path.basename(os.path.normpath(args.drivers)),
            "dxe_sha256": sha256(dxe), "dxe3_sha256": sha256(dxe3) if args.glide3 else None, "accel": accel,
            "cpu": args.cpu, "pve": args.pve}
    log(f"{version}; GLIDE2X.DXE {info['dxe_sha256'][:12]}"
        f"{'; GLIDE3X.DXE ' + info['dxe3_sha256'][:12] if args.glide3 else ''}; profiles {', '.join(profiles)}")
    results = [run_profile(args, scene, p, boot, files, dxe, dxe3, accel) for p in profiles]
    shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({"info": info, "results": results}, f, indent=1)
    md = summary_md(info, results)
    with open(os.path.join(args.out, "summary.md"), "w") as f:
        f.write(md)
    print(md)
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
