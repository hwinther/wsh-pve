#!/usr/bin/env python3
"""DOS memory profiles as data, tried on a copy of an installed DOS disk and measured.

    dos_profiles.py show --flavour msdos [--profile full] [--menu]       # the CONFIG.SYS/AUTOEXEC.BAT text
    dos_profiles.py run --flavour freedos --disk c.raw --out /work/prof [--profiles full,ems]
                        [--vga std,retrace=precise] [--extra local.json] [--menu]
                        [--games-disk d.raw --games games.txt [--only doom,keen4]]

A profile is the memory part of CONFIG.SYS (HIMEM, EMM386 or JEMMEX, DOS=HIGH,UMB), how the drivers
and TSRs are loaded (high, low, only the idle driver) and the environment a game wants (BLASTER).
`run` copies the disk (sparse) for every profile, writes the profile's CONFIG.SYS and AUTOEXEC.BAT and
our own test programs onto the copy with mtools (no typing, no boot of the original), boots it in the
lab's own QEMU (scenarios/dos-profile.py) and reads what the guest wrote back from the copy:

- MEM's summary (free conventional memory, largest program, upper memory, EMS, XMS) and MEM /C;
- VGARTRC.COM: does the VGA report display enable for several reads in a row (QEMU's `dumb` retrace
  never does, `retrace=precise` does; Wolfenstein 3D needs it);
- VGAAR.COM: does port 3C0h read back the attribute address in the data state (pve-qemu wsh/0051;
  The Incredible Machine);
- SNDCHK.COM: the Sound Blaster DSP's version, and an AdLib tone and a PC speaker beep that QEMU's wav
  audiodev records (audio present or not, from the WAV file);
- QEMU's guest_errors/unimp log, and whether the screen is lit at the end (a screendump, not black).

With --games-disk the copy also gets RUN.BAT for one game per run (D: is the games disk, attached
with snapshot=on so it is never written); the scenario presses the game's keys and samples the screen:
distinct frames, the last change, still running or back at the prompt, and sound in the WAV.
Games file lines: `name;D:|CD \\GAMES\\DOOM|DOOM;20:ret,30:spc;60` (commands, keys at seconds, seconds).

--menu writes all the flavour's profiles as one multi-configuration CONFIG.SYS (MS-DOS 6's [MENU]
blocks, FreeDOS's `n?` lines) and boots it once per entry, picking the entry at the startup menu.

`installed` keeps the disk's own CONFIG.SYS and AUTOEXEC.BAT and only appends the measurement call to
the AUTOEXEC.BAT that SHELL /P names. --extra adds lab-local data in JSON (never in the repository: a
disk's own drivers): {"drivers": {"config": [...], "autoexec": [...]}, "idle": "...", "path": "...",
"env": [...], "profiles": {"name": {...}}}.

Writes <out>/results.json (one row per run, plus the QEMU and package versions) and <out>/summary.md;
each run's lab evidence (result.json, screens, qemu-d.log, audio.wav) stays in <out>/<run>/run. The
parsers are pure and tested in tests/test_dos_profiles.py; the CI test (FreeDOS) is there too.
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = "C:\\WSHPROF"
BLASTER = "A220 I5 D1 H5 T6"  # QEMU's SB16: port 220h, IRQ 5, DMA 1 and 5, type 6; no MPU-401 (no P330)

FLAVOURS = {
    "msdos": {
        "config": "CONFIG.SYS", "mem": "C:\\DOS\\MEM.EXE", "path": "C:\\DOS",
        "idle": "C:\\DOS\\WSHIDLE.COM", "files": {"DOS/WSHIDLE.COM": "wshidle"},
        "common": ["FILES=40", "BUFFERS=20", "STACKS=9,256", "LASTDRIVE=Z"],
        "shell": "SHELL=C:\\COMMAND.COM C:\\ /E:1024 /P",
        "drivers": {"config": [], "autoexec": []},
        "menu_prompt": r"Enter a choice:",
    },
    "freedos": {
        "config": "FDCONFIG.SYS", "mem": "C:\\FREEDOS\\BIN\\MEM.EXE", "path": "C:\\FREEDOS\\BIN",
        "idle": "C:\\FREEDOS\\BIN\\FDAPM.COM APMDOS", "files": {},
        "common": ["FILES=40", "BUFFERS=20", "LASTDRIVE=Z", "SET DOSDIR=C:\\FREEDOS"],
        "shell": "{shell}=C:\\FREEDOS\\BIN\\COMMAND.COM C:\\FREEDOS\\BIN /E:1024 /P=C:\\AUTOEXEC.BAT",
        # the base install's mouse driver (not its CD-ROM pair: SHSUCDX stays low under LH)
        "drivers": {"config": [], "autoexec": ["C:\\FREEDOS\\BIN\\CTMOUSE.EXE"]},
        "menu_prompt": r"(Enter a choice|Select from Menu|press \[ENTER\])",
    },
}

_MS_HIMEM = "DEVICE=C:\\DOS\\HIMEM.SYS /TESTMEM:OFF"
_FD = "C:\\FREEDOS\\BIN\\"

# load: "high" (DEVICEHIGH/LH for every driver), "low", "idle" (only the idle driver, low).
# The I= ranges are SeaBIOS's free gap in a VM without a NIC (CD800-E8FFF; with ne2k_pci's ROM it
# starts at CE00, see the DOS guide's "The first megabyte"); never past E8FF.
PROFILES = {
    "msdos": {
        "full": {"title": "Everything high: XMS and UMB, no EMS",
                 "for": "DOS/4GW and other protected-mode games (Doom, Duke Nukem 3D), most programs",
                 "memory": [_MS_HIMEM, "DEVICE=C:\\DOS\\EMM386.EXE NOEMS I=CD00-E8FF", "DOS=HIGH,UMB"],
                 "load": "high"},
        # RAM without a size: EMM386's EMS and VCPI pool is all free XMS (taken as needed), so DOS/4GW
        # games run here too; `RAM 4096` caps VCPI at 4 MB and Duke Nukem 3D stops for lack of memory.
        "ems": {"title": "EMS page frame at D800 and UMB",
                "for": "games that want expanded memory (The Incredible Machine 2, Dune, King's Quest VII), "
                       "and DOS/4GW games through VCPI",
                "memory": [_MS_HIMEM, "DEVICE=C:\\DOS\\EMM386.EXE RAM FRAME=D800 I=CD00-D7FF I=E800-E8FF",
                           "DOS=HIGH,UMB"],
                "load": "high", "expect": {"ems": True}},
        "maxconv": {"title": "Maximum conventional memory: HIMEM only, nothing else loaded",
                    "for": "real-mode games that need the most conventional memory (Commander Keen, Larry, Dune II)",
                    "memory": [_MS_HIMEM, "DOS=HIGH"], "load": "idle"},
        "noemm": {"title": "No EMM386: HIMEM, drivers low",
                  "for": "DOS extenders that refuse V86 mode (no VCPI)",
                  "memory": [_MS_HIMEM, "DOS=HIGH"], "load": "low"},
        "installed": {"title": "The disk's own CONFIG.SYS and AUTOEXEC.BAT", "keep": True},
    },
    "freedos": {
        "full": {"title": "JEMMEX without EMS, everything high",
                 "for": "DOS/4GW and other protected-mode games, most programs",
                 "memory": [f"DEVICE={_FD}JEMMEX.EXE NOEMS X=TEST I=TEST NOVME NOINVLPG", "DOS=HIGH,UMB",
                            "DOSDATA=UMB"],
                 "load": "high"},
        "ems": {"title": "JEMMEX with the EMS page frame at D800",
                "for": "games that want expanded memory",
                "memory": [f"DEVICE={_FD}JEMMEX.EXE FRAME=D800 X=TEST NOVME NOINVLPG", "DOS=HIGH,UMB",
                           "DOSDATA=UMB"],
                "load": "high", "expect": {"ems": True}},
        "maxconv": {"title": "HIMEMX only, nothing else loaded",
                    "for": "real-mode programs that need the most conventional memory",
                    "memory": [f"DEVICE={_FD}HIMEMX.EXE", "DOS=HIGH"], "load": "idle"},
        "noemm": {"title": "No JEMM: HIMEMX, drivers low",
                  "for": "DOS extenders that refuse V86 mode",
                  "memory": [f"DEVICE={_FD}HIMEMX.EXE", "DOS=HIGH"], "load": "low"},
        "installed": {"title": "The installer's own FDCONFIG.SYS and FDAUTO.BAT (menu entry 2)", "keep": True},
    },
}

# our test programs (dos_tools.COMS) in C:\WSHPROF, and what MEASURE.BAT writes to C:\WSHPROF\OUT
PROGRAMS = {"VGARTRC.COM": "vgartrc", "VGAAR.COM": "vgaar", "SNDCHK.COM": "sndchk", "EMSCHK.COM": "emschk"}
OUTPUTS = ["MEM.TXT", "MEMC.TXT", "ENV.TXT", "EMSCHK.TXT", "VGARTRC.TXT", "VGAAR.TXT", "SNDCHK.TXT"]


# --- profiles ----------------------------------------------------------------------------------------

def flavour_data(flavour, extra=None):
    """The flavour's settings with --extra's overrides (drivers, idle, path, env)."""
    f = {**FLAVOURS[flavour], "env": []}
    for k in ("drivers", "idle", "path", "env", "common", "shell"):
        if extra and k in extra:
            f[k] = extra[k]
    return f


def profiles(flavour, extra=None):
    return {**PROFILES[flavour], **((extra or {}).get("profiles") or {})}


def _load(lines, kind, how):
    if kind == "config":
        return [("DEVICEHIGH=" if how == "high" else "DEVICE=") + x for x in lines]
    return [("LH " if how == "high" else "") + x for x in lines]


def config_lines(flavour, prof, extra=None):
    """CONFIG.SYS (or FDCONFIG.SYS) of a profile, as a list of lines."""
    f = flavour_data(flavour, extra)
    how = prof.get("load", "low")
    drivers = f["drivers"]["config"] if how in ("high", "low") else []
    shell = prof.get("shell", f["shell"]).format(shell="SHELLHIGH" if how == "high" else "SHELL")
    return list(prof["memory"]) + f["common"] + _load(drivers, "config", how) + list(prof.get("config", [])) + [shell]


def autoexec_lines(flavour, prof, extra=None):
    """AUTOEXEC.BAT of a profile, ending in the call of MEASURE.BAT."""
    f = flavour_data(flavour, extra)
    how = prof.get("load", "low")
    out = ["@ECHO OFF", "PROMPT $P$G", f"PATH {f['path']}", f"SET BLASTER={BLASTER}"] + list(f["env"])
    tsrs = f["drivers"]["autoexec"] if how in ("high", "low") else []
    if f["idle"]:
        out += _load([f["idle"]], "autoexec", "high" if how == "high" else "low")
    return out + _load(tsrs, "autoexec", how) + list(prof.get("autoexec", [])) + [f"CALL {WORK}\\MEASURE.BAT"]


def menu_lines(flavour, names, extra=None):
    """One multi-configuration CONFIG.SYS and AUTOEXEC.BAT with `names` as menu entries 1, 2, ..."""
    profs = profiles(flavour, extra)
    f = flavour_data(flavour, extra)
    cfg, auto = [], ["@ECHO OFF", "PROMPT $P$G", f"PATH {f['path']}", f"SET BLASTER={BLASTER}"] + list(f["env"])
    if flavour == "msdos":
        cfg += ["[MENU]"] + [f"MENUITEM={n.upper()}, {profs[n]['title']}" for n in names]
        cfg += [f"MENUDEFAULT={names[0].upper()},30", "", "[COMMON]"] + f["common"]
        auto += ["GOTO %CONFIG%"]
        for n in names:
            body = config_lines(flavour, profs[n], extra)
            cfg += ["", f"[{n.upper()}]"] + [x for x in body if x not in f["common"]]
            auto += [f":{n.upper()}"] + autoexec_lines(flavour, profs[n], extra)[4 + len(f["env"]):-1] + ["GOTO END"]
    else:
        cfg += [f"MENUDEFAULT=1,30"] + [f"MENU {i} - {profs[n]['title']}" for i, n in enumerate(names, 1)]
        cfg += [""] + [f"!{x}" for x in f["common"]]
        auto += ["GOTO %CONFIG%"]
        for i, n in enumerate(names, 1):
            body = config_lines(flavour, profs[n], extra)
            cfg += [""] + [f"{i}?{x}" for x in body if x not in f["common"]]
            auto += [f":{i}"] + autoexec_lines(flavour, profs[n], extra)[4 + len(f["env"]):-1] + ["GOTO END"]
    auto += [":END", f"CALL {WORK}\\MEASURE.BAT"]
    return cfg, auto


def measure_lines(flavour, sound=True):
    """MEASURE.BAT: MEM, the environment and our programs into C:\\WSHPROF\\OUT, then RUN.BAT (a game)
    when there is one. SNDCHK only without a game, so the WAV holds only the game's sound."""
    f = FLAVOURS[flavour]
    o = f"{WORK}\\OUT"
    out = ["@ECHO OFF", "ECHO WSHPROF MEASURE", f"{f['mem']} >{o}\\MEM.TXT", f"{f['mem']} /C >{o}\\MEMC.TXT",
           f"SET >{o}\\ENV.TXT", f"{WORK}\\EMSCHK.COM >{o}\\EMSCHK.TXT", f"{WORK}\\VGARTRC.COM >{o}\\VGARTRC.TXT", f"{WORK}\\VGAAR.COM >{o}\\VGAAR.TXT"]
    if sound:
        out.append(f"{WORK}\\SNDCHK.COM >{o}\\SNDCHK.TXT")
    return out + ["ECHO WSHPROF DONE", f"IF EXIST {WORK}\\RUN.BAT CALL {WORK}\\RUN.BAT"]


def run_lines(game_cmds):
    return ["ECHO WSHPROF GAME"] + list(game_cmds)


# --- the disk (mtools) --------------------------------------------------------------------------------

def partition_offset(raw):
    """Byte offset of the first FAT partition in the MBR (types 01, 04, 06, 0B, 0C, 0E)."""
    with open(raw, "rb") as fh:
        mbr = fh.read(512)
    if mbr[510:512] != b"\x55\xaa":
        raise ValueError(f"{raw}: no MBR signature")
    for i in range(4):
        e = mbr[446 + 16 * i:462 + 16 * i]
        if e[4] in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E):
            return struct.unpack_from("<I", e, 8)[0] * 512
    raise ValueError(f"{raw}: no FAT partition in the MBR")


def crlf(lines):
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


class Fat:
    """The C: partition of a raw disk through mtools."""

    def __init__(self, raw):
        self.img = f"{raw}@@{partition_offset(raw)}"
        self.env = {**os.environ, "MTOOLS_SKIP_CHECK": "1", "MTOOLS_NO_VFAT": "1"}

    def _m(self, *args, check=True):
        r = subprocess.run(list(args), capture_output=True, env=self.env)
        if check and r.returncode:
            raise RuntimeError(f"{' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
        return r

    def read(self, path):
        r = self._m("mtype", "-i", self.img, f"::/{path}", check=False)
        return None if r.returncode else r.stdout.decode("cp437")

    def write(self, path, data):
        with tempfile.NamedTemporaryFile(delete=False) as t:
            t.write(data)
        try:
            self._m("mcopy", "-o", "-i", self.img, t.name, f"::/{path}")
        finally:
            os.unlink(t.name)

    def mkdir(self, path):
        self._m("mmd", "-D", "s", "-i", self.img, f"::/{path}", check=False)

    def exists(self, path):
        return self._m("mdir", "-b", "-i", self.img, f"::/{path}", check=False).returncode == 0


def shell_autoexec(config_text):
    """The batch file SHELL ... /P=<file> names in a CONFIG.SYS (FreeDOS's FDAUTO.BAT), else AUTOEXEC.BAT."""
    m = re.search(r"/P=([A-Za-z]:\\[^\s]+)", config_text or "")
    return m.group(1)[3:] if m else "AUTOEXEC.BAT"


def inject(raw, flavour, prof=None, extra=None, game=None, menu=None):
    """Write a profile (or `menu`: (config, autoexec) lines) and our programs onto the disk image."""
    import dos_tools

    fat, f = Fat(raw), FLAVOURS[flavour]
    fat.mkdir("WSHPROF")
    fat.mkdir("WSHPROF/OUT")
    for name, com in {**PROGRAMS, **{p.split("/")[-1]: c for p, c in f["files"].items()}}.items():
        fat.write(f"WSHPROF/{name}", dos_tools.COMS[com]())
    for path, com in f["files"].items():
        if not fat.exists(path):
            fat.write(path, dos_tools.COMS[com]())
    fat.write("WSHPROF/MEASURE.BAT", crlf(measure_lines(flavour, sound=game is None)))
    if game:
        fat.write("WSHPROF/RUN.BAT", crlf(run_lines(game)))
    if menu:
        cfg, auto = menu
    elif prof.get("keep"):
        text = fat.read(f["config"]) or fat.read("CONFIG.SYS") or ""
        name = shell_autoexec(text)
        auto_text = (fat.read(name) or "@ECHO OFF\r\n").rstrip("\r\n\x1a")
        fat.write(name, (auto_text.replace("\r\n", "\n").replace("\n", "\r\n") +
                         f"\r\nCALL {WORK}\\MEASURE.BAT\r\n").encode("cp437"))
        return
    else:
        cfg, auto = config_lines(flavour, prof, extra), autoexec_lines(flavour, prof, extra)
    fat.write(f["config"], crlf(cfg))
    fat.write("AUTOEXEC.BAT", crlf(auto))


def read_outputs(raw):
    fat = Fat(raw)
    return {n: (fat.read(f"WSHPROF/OUT/{n}") or "").replace("\r", "") for n in OUTPUTS}


# --- parsing (pure) ------------------------------------------------------------------------------------

# a number in MEM's output: 31,573 (US), 31.573 or 31 573 (other COUNTRY= settings), 640
N = r"(\d{1,3}(?:[,. ]\d{3})+|\d+)"


def _k(s):
    return int(re.sub(r"[,. ]", "", s))


def parse_mem(text):
    """MEM's summary, MS-DOS 6.22 and FreeDOS alike, in K: conv_free, upper_total/free, xms_free,
    ems_total/ems_free (None when there is no EMS), largest_exe and largest_umb (bytes), high (DOS in
    the HMA)."""
    out = {}

    def row(label):
        m = re.search(rf"^\s*{label}\S*\s+{N}K?\s+{N}K?\s+{N}K?", text, re.M | re.I)
        return tuple(_k(x) for x in m.groups()) if m else None

    r = row("Conventional")
    if r:
        out["conv_total"], out["conv_used"], out["conv_free"] = r
    r = row("Upper")
    if r:
        out["upper_total"], out["upper_free"] = r[0], r[2]
    r = row(r"Extended \(XMS\)")
    if r:
        out["xms_free"] = r[2]
    # "4,480K (4,587,520 bytes)", FreeDOS's "31M (...)", and MS-DOS 6.22 with a large pool, whose
    # wider numbers push the K and the ")" past its field: "31,936 (32,702,464 bytes"
    for key, label in (("ems_total", "Total"), ("ems_free", "Free")):
        m = re.search(rf"{label} Expanded \(EMS\)\S*\s+{N}[KM]?\s*\(\s*{N} bytes", text, re.I)
        out[key] = _k(m.group(2)) // 1024 if m else None
    if out["ems_total"] is None:  # FreeDOS: a row of the table
        r = row(r"Expanded \(EMS\)")
        if r:
            out["ems_total"], out["ems_free"] = r[0], r[2]
    m = re.search(rf"Largest executable program size\s+{N}K?\s*\(\s*{N} bytes\)", text, re.I)
    if m:
        out["largest_exe"] = _k(m.group(2))
    m = re.search(rf"Largest free upper memory block\s+{N}K?\s*\(\s*{N} bytes\)", text, re.I)
    if m:
        out["largest_umb"] = _k(m.group(2))
    out["high"] = bool(re.search(r"resident in the high memory area", text, re.I))
    return out


def parse_programs(files):
    """Our programs' one-line results."""
    out = {}
    t = files.get("VGARTRC.TXT", "")
    m = re.search(r"VGARTRC (OK|TIMEOUT)\D*([0-9A-F]{4})", t)
    out["retrace"] = (m.group(1).lower(), int(m.group(2), 16)) if m else None
    m = re.search(r"VGAAR 3C0h address/data state ([0-9A-F]{2})([0-9A-F]{2}) (OK|FAIL)", files.get("VGAAR.TXT", ""))
    out["vgaar"] = {"address": m.group(1), "data": m.group(2), "ok": m.group(3) == "OK"} if m else None
    t = files.get("SNDCHK.TXT", "")
    m = re.search(r"SB DSP ([0-9A-F]{2})([0-9A-F]{2})", t)
    out["sb_dsp"] = f"{int(m.group(1), 16)}.{int(m.group(2), 16):02d}" if m else ("none" if "DSP none" in t else None)
    out["sound_played"] = "played" in t
    t = files.get("EMSCHK.TXT", "")
    m = re.search(r"EMSCHK pages ([0-9A-F]{4}) free ([0-9A-F]{4}) frame (none|[0-9A-F]{4})", t)
    out["ems"] = {"kb": int(m.group(1), 16) * 16, "free_kb": int(m.group(2), 16) * 16,
                  "frame": None if m.group(3) == "none" else m.group(3)} if m else ("none" if "EMSCHK none" in t else None)
    return out


def parse_env(text):
    return dict(x.split("=", 1) for x in text.splitlines() if "=" in x)


def wav_samples(data):
    """(rate, channels, sample width, PCM bytes) of a WAV file's bytes. QEMU writes the sizes into the
    header only when it exits normally; a killed QEMU leaves 0 there, so the data runs to the end."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos, fmt = 12, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if cid == b"fmt ":
            _, ch, rate, _, _, bits = struct.unpack_from("<HHIIHH", data, pos + 8)
            fmt = (rate, ch, bits // 8)
        elif cid == b"data" and fmt:
            end = len(data) if size == 0 else min(len(data), pos + 8 + size)
            return fmt + (data[pos + 8:end],)
        pos += 8 + size + (size & 1)
    return None


def audio_stats(path, window=0.1, threshold=500):
    """Sound in QEMU's wav audiodev file (16-bit PCM, its format): seconds recorded, seconds with sound
    (windows whose peak is above `threshold` of 32767), the peak."""
    try:
        with open(path, "rb") as fh:
            w = wav_samples(fh.read())
    except OSError:
        w = None
    if not w or w[2] != 2:
        return {"seconds": 0, "sound_s": 0, "peak": 0}
    rate, ch, width, pcm = w
    pcm = pcm[:len(pcm) - len(pcm) % 2]
    step = max(1, int(rate * window)) * ch * width
    sound, peak = 0, 0
    for i in range(0, len(pcm), step):
        chunk = pcm[i:i + step]
        vals = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        p = max(max(vals, default=0), -min(vals, default=0))
        peak = max(peak, p)
        sound += p > threshold
    return {"seconds": round(len(pcm) / (rate * ch * width), 1), "sound_s": round(sound * window, 1), "peak": peak}


def guest_errors(path, keep=5):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = [x.strip() for x in fh if x.strip()]
    except OSError:
        return {"count": 0, "first": []}
    first = []
    for x in lines:
        x = re.sub(r"0x[0-9a-f]+|\d+", "#", x)
        if x not in first:
            first.append(x)
    return {"count": len(lines), "first": first[:keep]}


def summarise(name, res, files, run_dir):
    """One results row from the lab's result.json and the files the guest wrote."""
    mem = parse_mem(files.get("MEM.TXT", ""))
    prog = parse_programs(files)
    met = res.get("metrics", {})
    row = {"profile": name, "code": res.get("code"), "status": res.get("status", "").splitlines()[0] if res.get("status") else "",
           "elapsed": res.get("elapsed"), "boot_s": met.get("boot_s"), **mem, **prog,
           "blaster": parse_env(files.get("ENV.TXT", "")).get("BLASTER"),
           "audio": audio_stats(os.path.join(run_dir, "audio.wav")),
           "guest_errors": guest_errors(os.path.join(run_dir, "qemu-d.log")),
           "screen_lit": met.get("screen_lit")}
    for k in ("game", "game_result", "game_distinct_frames", "game_last_change_s", "game_mode"):
        if k in met:
            row[k] = met[k]
    return row


def check(row, prof, retrace_expected):
    """What a CI run requires of one row; returns the list of problems (empty: fine)."""
    bad = []
    if row["code"] != 0:
        bad.append(f"run: {row['status']}")
    if not row.get("conv_free"):
        bad.append("no MEM summary")
    want_ems = prof.get("expect", {}).get("ems")
    frame = row["ems"].get("frame") if isinstance(row.get("ems"), dict) else None
    if row.get("ems") is None:
        bad.append("no EMSCHK result")
    elif want_ems and not frame:
        bad.append(f"no EMS page frame: {row['ems']}")
    elif not want_ems and not prof.get("keep") and frame:
        bad.append(f"an EMS page frame where the profile has none: {row['ems']}")
    if not row.get("retrace") or row["retrace"][0] != retrace_expected:
        bad.append(f"VGARTRC {row.get('retrace')}, expected {retrace_expected}")
    if not (row.get("vgaar") or {}).get("ok"):
        bad.append(f"VGAAR {row.get('vgaar')}")
    if row.get("sb_dsp") is not None and row["sb_dsp"] != "4.05":
        bad.append(f"SB DSP {row['sb_dsp']}")
    if row.get("sound_played") and row["audio"]["sound_s"] < 0.3:
        bad.append(f"SNDCHK played but the WAV is silent: {row['audio']}")
    if row.get("blaster") != BLASTER and not prof.get("keep"):
        bad.append(f"BLASTER {row.get('blaster')}")
    if row.get("screen_lit") is not None and row["screen_lit"] < 0.001:
        bad.append("the screen is black")
    return bad


# --- the runner ----------------------------------------------------------------------------------------

def parse_games(path):
    games = {}
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            name, cmds, keys, secs = line.split(";")
            games[name] = {"cmds": cmds.split("|"), "keys": keys, "secs": secs}
    return games


def versions(qemu):
    out = {}
    try:
        out["qemu"] = subprocess.run([qemu, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
        out["pve-qemu-kvm"] = subprocess.run(["dpkg-query", "-W", "-f", "${Version}", "pve-qemu-kvm"],
                                             capture_output=True, text=True).stdout or None
    except (OSError, IndexError):
        pass
    return out


def run_one(src, flavour, name, out, extra=None, game=None, menu=None, games_disk=None, variables=None):
    """Copy the disk, inject, boot, measure; returns the results row. The copy is removed afterwards."""
    import install
    import lab

    sys.modules.setdefault("lab", lab)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    raw = os.path.join(out, "c.raw")
    install.sparse_copy(src, raw)
    prof = None
    if menu:
        inject(raw, flavour, extra=extra, menu=menu[1], game=game and game["cmds"])
    else:
        prof = profiles(flavour, extra)[name]
        inject(raw, flavour, prof, extra, game=game and game["cmds"])
    v = {"DISK": raw, "FB_VIDEO": "0", "MENU_PROMPT": FLAVOURS[flavour]["menu_prompt"], **(variables or {})}
    if menu:
        v["MENU"] = str(menu[0])
    if game:
        v.update({"GAMES": games_disk, "GAME_SECS": game["secs"], "KEYS": game["keys"]})
    run_dir = os.path.join(out, "run")
    res = lab.run_scenario(os.path.join(HERE, "scenarios", "dos-profile.py"), run_dir, v, no_ocr=True)
    files = read_outputs(raw)
    for n, t in files.items():
        with open(os.path.join(out, n), "w", encoding="utf-8") as fh:
            fh.write(t)
    os.unlink(raw)
    row = summarise(name, res, files, run_dir)
    row["vga"] = v.get("VGA", "std")
    return row


def kb(x):
    return "-" if x is None else f"{x // 1024}K"


def ems_cell(r):
    e = r.get("ems")
    if isinstance(e, dict):
        return f"{e['kb']}K, frame {e['frame'] or 'none'}"
    return e or "-"


def table(rows):
    out = ["| Run | Result | Conventional free | Largest program | UMB free | EMS | XMS free | VGARTRC | VGAAR | "
           "SB DSP | Audio | Screen | guest_errors |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        game = f" / {r['game']}: {r.get('game_result')}, {r.get('game_distinct_frames')} frames, last change " \
               f"{r.get('game_last_change_s')}s" if r.get("game") else ""
        rt = f"{r['retrace'][0]} ({r['retrace'][1]})" if r.get("retrace") else "-"
        ar = f"{r['vgaar']['address']}/{r['vgaar']['data']}" if r.get("vgaar") else "-"
        lit = "-" if r.get("screen_lit") is None else ("lit" if r["screen_lit"] >= 0.001 else "black")
        out.append(f"| {r['profile']} ({r['vga']}) | {r['status']}{game} | {r.get('conv_free', '-')}K | "
                   f"{kb(r.get('largest_exe'))} | {r.get('upper_free', '-')}K | "
                   f"{ems_cell(r)} | {r.get('xms_free', '-')}K | "
                   f"{rt} | {ar} | {r.get('sb_dsp') or '-'} | {r['audio']['sound_s']}s | {lit} | "
                   f"{r['guest_errors']['count']} |")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--flavour", choices=sorted(FLAVOURS), required=True)
    s.add_argument("--profile")
    s.add_argument("--menu", action="store_true")
    s.add_argument("--extra")
    r = sub.add_parser("run")
    r.add_argument("--flavour", choices=sorted(FLAVOURS), required=True)
    r.add_argument("--disk", required=True, help="the installed DOS disk (raw); only read")
    r.add_argument("--out", required=True)
    r.add_argument("--profiles", help="comma separated (default: all of the flavour)")
    r.add_argument("--menu", action="store_true", help="one multi-config CONFIG.SYS, one boot per entry")
    r.add_argument("--vga", default="std", help="QEMU -vga value, e.g. std,retrace=precise")
    r.add_argument("--extra", help="lab-local JSON: drivers, idle, path, env, profiles")
    r.add_argument("--games-disk")
    r.add_argument("--games", help="games file (name;cmds;keys;secs)")
    r.add_argument("--only", help="games to run (default: all in the file)")
    r.add_argument("--var", action="append", default=[], help="more scenario variables, NAME=VALUE")
    a = p.parse_args()
    extra = json.load(open(a.extra, encoding="utf-8")) if a.extra else None
    if a.cmd == "show":
        if a.menu:
            names = [n for n, x in profiles(a.flavour, extra).items() if not x.get("keep")]
            cfg, auto = menu_lines(a.flavour, names, extra)
            print("\n".join([f"=== {FLAVOURS[a.flavour]['config']}"] + cfg + ["", "=== AUTOEXEC.BAT"] + auto))
            return 0
        for n, prof in profiles(a.flavour, extra).items():
            if (a.profile and n != a.profile) or prof.get("keep"):
                continue
            print(f"=== {n}: {prof['title']} ({prof['for']})\n--- {FLAVOURS[a.flavour]['config']}")
            print("\n".join(config_lines(a.flavour, prof, extra)))
            print("--- AUTOEXEC.BAT\n" + "\n".join(autoexec_lines(a.flavour, prof, extra)) + "\n")
        return 0
    os.makedirs(a.out, exist_ok=True)
    names = a.profiles.split(",") if a.profiles else list(profiles(a.flavour, extra))
    variables = dict(x.split("=", 1) for x in a.var)
    variables["VGA"] = a.vga
    games = parse_games(a.games) if a.games else {}
    if a.only:
        games = {k: games[k] for k in a.only.split(",")}
    runs = []  # (label, name, menu, game)
    if a.menu:
        menu_names = [n for n in names if not profiles(a.flavour, extra)[n].get("keep")]
        cfg = menu_lines(a.flavour, menu_names, extra)
        runs = [(f"menu{i}-{n}", n, (i, cfg), None) for i, n in enumerate(menu_names, 1)]
    else:
        runs = [(n, n, None, None) for n in names]
    if games:
        runs = [(f"{lbl}-{g}", n, m, games[g] | {"name": g}) for lbl, n, m, _ in runs for g in games]
    rows = []
    for label, name, menu, game in runs:
        row = run_one(a.disk, a.flavour, name, os.path.join(a.out, label), extra, game, menu, a.games_disk, variables)
        row["run"] = label
        if game:
            row["game"] = game["name"]
        rows.append(row)
        print(f"{label}: {row['status']} conv {row.get('conv_free')}K ems {row.get('ems_total')} "
              f"retrace {row.get('retrace')} vgaar {row.get('vgaar')} audio {row['audio']['sound_s']}s "
              f"{row.get('game_result', '')} {row.get('game_distinct_frames', '')}", flush=True)
        with open(os.path.join(a.out, "results.json"), "w", encoding="utf-8") as fh:
            json.dump({"flavour": a.flavour, "versions": versions(variables.get("QEMU", "qemu-system-x86_64")),
                       "vga": a.vga, "rows": rows}, fh, indent=1)
    t = table(rows)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(t + "\n")
    print("\n" + t)
    return 0 if all(r["code"] == 0 for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
