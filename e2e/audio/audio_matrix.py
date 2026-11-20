"""The x86 audio matrix: which sound devices of the published pve-qemu-kvm make sound in which guest,
and whether qemu-server's `audio0:` wires them up, checked with QEMU's `wav` audio backend.

Runs inside the image of e2e/audio/Dockerfile (the e2e PVE node plus the guests):

    python3 audio_matrix.py inventory --out /runs/audio      # devices, backends, qemu-server's enum
    python3 audio_matrix.py qemu --out /runs/audio           # every case on QEMU directly
    python3 audio_matrix.py pve --out /runs/audio            # through qemu-server (needs the PVE node up)
    python3 audio_matrix.py all --out /runs/audio            # the three, then summary.md

  --only ID[,ID]   run only these cases (see CASES / PVE_CASES / PVE_WAV_SERVER)
  FREEDOS_CACHE    where the FreeDOS zip is kept (default /var/cache/audio-freedos)

Guests (built by build-guests.sh, nothing installed):
  dos    FreeDOS 1.4's boot floppy with its FDCONFIG.SYS replaced so it runs AUDIO.BAT, which runs
         AUDTEST.COM (audtest.asm): SB16 PCM 1000 Hz, OPL2 440 Hz, PC speaker 750 Hz, one after the
         other, then ACPI power off. Each case expects the tones of the devices it attaches and the
         absence of the others, so a combination shows which device made which sound.
  linux  Debian's kernel with an initramfs that loads one driver and plays a 660 Hz tone with aplay,
         then powers off; the console (ttyS0, a -serial file) says whether ALSA found the card.

A case passes when the wav file holds the expected tones (wavcheck.py) and, for Linux, the guest said
`AUDIOTEST result=ok`. The direct cases run QEMU with `-audiodev wav` themselves: they cover the
devices qemu-server doesn't offer (ES1370, virtio-sound, USB audio, the single HDA codecs) and show
what QEMU does without qemu-server in between. Through PVE each x86 value of `audio0`'s device is
set with `driver=wav`: `qm showcmd` must have the expected -device/-machine arguments and
`-audiodev wav,id=wav-backend0,path=/var/run/qemu-server/<vmid>-audio0.wav`, then a real `qm start`
runs the guest to its power off and that file must hold the tones. One more PVE case checks that
`driver=wav` with a `server=` doesn't start.

Results: <out>/results.json and <out>/summary.md (a Markdown table for the job summary); each case's
wav, serial log and QEMU log (through PVE: showcmd.txt) in <out>/<case>/. Exit status 1 when a case
that should pass fails.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile

import wavcheck

HERE = os.path.dirname(os.path.abspath(__file__))
GUESTS = os.environ.get("AUDIO_GUESTS", os.path.join(HERE, "guests"))
QEMU = "qemu-system-x86_64"

# The FreeDOS 1.4 Floppy Edition, the same pins as e2e/sparc/targets_dos.py (FREEDOS_ZIP and MEDIA
# "freedos14-boot.img"): only its boot floppy is used.
FREEDOS_ZIP = {"url": "https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/distributions/1.4/"
                      "FD14-FloppyEdition.zip",
               "sha256": "45b1fa7c52dd996c3bfa5e352ffcd410781b952a6ad629f15a4c9ec4bbaefc5a"}
FREEDOS_BOOT = {"zip": "144m/x86BOOT.img",
                "sha256": "552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc"}

# What AUDTEST plays (audtest.asm) and what the Linux guest plays (build-guests.sh)
SB16, OPL, SPK, LINUX = 1000, 440, 750, 660
DOS_TONES = [SB16, OPL, SPK]

HDA_MODS = "snd-hda-codec-generic,snd-hda-intel"

# Direct QEMU: every sound device of the package that one of the guests drives. "machine" may carry
# extra properties ("pcspk-audiodev"); "{a}" is the audiodev id.
CASES = [
    {"id": "dos-sb16", "guest": "dos", "device": "sb16", "args": ["-device", "sb16,audiodev={a}"],
     "expect": [SB16]},
    {"id": "dos-adlib", "guest": "dos", "device": "adlib", "args": ["-device", "adlib,audiodev={a}"],
     "expect": [OPL]},
    {"id": "dos-pcspk", "guest": "dos", "device": "pcspk", "machine_props": "pcspk-audiodev={a}",
     "args": [], "expect": [SPK]},
    {"id": "dos-sb16-adlib-pcspk", "guest": "dos", "device": "sb16+adlib+pcspk",
     "machine_props": "pcspk-audiodev={a}",
     "args": ["-device", "sb16,audiodev={a}", "-device", "adlib,audiodev={a}"], "expect": DOS_TONES},
    {"id": "linux-ac97", "guest": "linux", "device": "AC97", "mods": "snd-intel8x0",
     "args": ["-device", "AC97,audiodev={a}"], "expect": [LINUX]},
    {"id": "linux-es1370", "guest": "linux", "device": "ES1370", "mods": "snd-ens1370",
     "args": ["-device", "ES1370,audiodev={a}"], "expect": [LINUX]},
    {"id": "linux-intel-hda", "guest": "linux", "device": "intel-hda + hda-micro", "mods": HDA_MODS,
     "args": ["-device", "intel-hda,id=hda", "-device", "hda-micro,bus=hda.0,audiodev={a}"], "expect": [LINUX]},
    {"id": "linux-intel-hda-duplex", "guest": "linux", "device": "intel-hda + hda-duplex", "mods": HDA_MODS,
     "args": ["-device", "intel-hda,id=hda", "-device", "hda-duplex,bus=hda.0,audiodev={a}"], "expect": [LINUX]},
    {"id": "linux-ich9-intel-hda", "guest": "linux", "device": "ich9-intel-hda + hda-micro", "machine": "q35",
     "mods": HDA_MODS,
     "args": ["-device", "ich9-intel-hda,id=hda", "-device", "hda-micro,bus=hda.0,audiodev={a}"],
     "expect": [LINUX]},
    {"id": "linux-virtio-sound", "guest": "linux", "device": "virtio-sound-pci", "mods": "virtio_snd",
     "args": ["-device", "virtio-sound-pci,audiodev={a}"], "expect": [LINUX]},
    {"id": "linux-usb-audio", "guest": "linux", "device": "usb-audio (qemu-xhci)", "mods": "xhci-pci,snd-usb-audio",
     "args": ["-device", "qemu-xhci,id=xhci", "-device", "usb-audio,bus=xhci.0,audiodev={a}"], "expect": [LINUX]},
]

# Through qemu-server: every x86 value of audio0's device enum, with driver=wav. "showcmd" are
# regexes the `qm showcmd` output must match (B = the backend id qemu-server picks, wav-backend0);
# the -audiodev with the fixed path is checked for every case. The recording is PVE_WAV.
PVE_BACKEND = "wav-backend0"
PVE_WAV = "/var/run/qemu-server/{vmid}-audio0.wav"
PVE_WAV_SERVER = "pve-wav-server-refused"
PVE_CASES = [
    {"id": "pve-AC97", "audio": "AC97", "guest": "linux", "mods": "snd-intel8x0", "expect": [LINUX],
     "showcmd": [r"-device '?AC97,id=audiodev0,[^ ']*audiodev=B'?"]},
    {"id": "pve-intel-hda", "audio": "intel-hda", "guest": "linux", "mods": HDA_MODS, "expect": [LINUX],
     "showcmd": [r"-device '?intel-hda,id=audiodev0,", r"-device '?hda-micro,id=audiodev0-codec0,bus=audiodev0\.0,cad=0,audiodev=B'?",
                 r"-device '?hda-duplex,id=audiodev0-codec1,bus=audiodev0.0,cad=1,audiodev=B'?"]},
    {"id": "pve-ich9-intel-hda", "audio": "ich9-intel-hda", "machine": "q35", "guest": "linux", "mods": HDA_MODS,
     "expect": [LINUX],
     "showcmd": [r"-device '?ich9-intel-hda,id=audiodev0,", r"-device '?hda-micro,id=audiodev0-codec0,bus=audiodev0\.0,cad=0,audiodev=B'?",
                 r"-device '?hda-duplex,id=audiodev0-codec1,bus=audiodev0.0,cad=1,audiodev=B'?"]},
    {"id": "pve-sb16", "audio": "sb16", "guest": "dos", "expect": [SB16],
     "showcmd": [r"-device '?sb16,id=audiodev0,audiodev=B'?"]},
    {"id": "pve-adlib", "audio": "adlib", "guest": "dos", "expect": [OPL],
     "showcmd": [r"-device '?adlib,id=audiodev0,audiodev=B'?"]},
    {"id": "pve-pcspk", "audio": "pcspk", "guest": "dos", "expect": [SPK],
     "showcmd": [r"-machine '?pcspk-audiodev=B'?"]},
    {"id": "pve-sb16-adlib-pcspk", "audio": "sb16-adlib-pcspk", "guest": "dos", "expect": DOS_TONES,
     "showcmd": [r"-machine '?pcspk-audiodev=B'?", r"-device '?sb16,audiodev=B'?", r"-device '?adlib,audiodev=B'?"]},
]

FDCONFIG = "SWITCHES=/N /F\r\nLASTDRIVE=Z\r\nFILES=20\r\nSHELL=\\FREEDOS\\BIN\\COMMAND.COM \\FREEDOS\\BIN /E:1024 /P=\\AUDIO.BAT\r\n"
AUDIO_BAT = "@ECHO OFF\r\nSET BLASTER=A220 I5 D1 H5 T6\r\nAUDTEST SAP\r\n"


def log(*a):
    print(*a, flush=True)


def sh(*cmd, check=True, timeout=120):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: exit {r.returncode}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def kvm_usable():
    return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


# ---------------------------------------------------------------------------------------------
# inventory

def inventory():
    inv = {"packages": {}, "qemu_sound_devices": [], "audiodev_drivers": [], "qemu_server": {}}
    for p in ("pve-qemu-kvm", "qemu-server", "pve-manager"):
        inv["packages"][p] = sh("dpkg-query", "-W", "-f", "${Version}", p, check=False).strip() or None
    out = sh(QEMU, "-device", "help")
    section = re.search(r"Sound devices:\n(.*?)(?:\n\n|\Z)", out, re.S)
    for line in (section.group(1).splitlines() if section else []):
        m = re.match(r'name "([^"]+)", bus ([^,]+)(?:, alias "([^"]+)")?(?:, desc "([^"]*)")?', line.strip())
        if m:
            inv["qemu_sound_devices"].append({"name": m[1], "bus": m[2], "alias": m[3], "desc": m[4]})
    out = sh(QEMU, "-audiodev", "help")
    inv["audiodev_drivers"] = [x.strip() for x in out.splitlines()[1:] if x.strip()]
    # pcspk-audiodev is an alias property that `-machine pc,help` doesn't list: start frozen with it
    try:
        r = subprocess.run([QEMU, "-machine", "pc,accel=tcg,pcspk-audiodev=a0", "-audiodev", "none,id=a0",
                            "-display", "none", "-nodefaults", "-S"], capture_output=True, text=True, timeout=5)
        inv["pc_machine_pcspk_audiodev"] = False
        inv["pc_machine_pcspk_audiodev_error"] = r.stderr.strip()[:300]
    except subprocess.TimeoutExpired:
        inv["pc_machine_pcspk_audiodev"] = True  # still running: QEMU took it
    # audio0's enums in the installed qemu-server (the format hash is lexical, so read the source)
    for root, _, files in os.walk("/usr/share/perl5/PVE"):
        for f in files:
            if not f.endswith(".pm"):
                continue
            src = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
            m = re.search(r"my \$audio_fmt = \{(.*?)\n\};", src, re.S)
            if m:
                dev = re.search(r"device\s*=>\s*\{.*?enum\s*=>\s*\[qw\(([^)]*)\)\]", m[1], re.S)
                drv = re.search(r"driver\s*=>\s*\{.*?enum\s*=>\s*\[([^\]]*)\]", m[1], re.S)
                inv["qemu_server"] = {
                    "file": os.path.join(root, f),
                    "devices": dev[1].split() if dev else [],
                    "drivers": re.findall(r"'([^']+)'", drv[1]) if drv else [],
                    "server_option": "server" in m[1]}
    return inv


# ---------------------------------------------------------------------------------------------
# guests

def freedos_boot_floppy():
    cache = os.environ.get("FREEDOS_CACHE", "/var/cache/audio-freedos")
    os.makedirs(cache, exist_ok=True)
    boot = os.path.join(cache, "freedos14-boot.img")
    if os.path.exists(boot) and sha256(boot) == FREEDOS_BOOT["sha256"]:
        return boot
    zpath = os.path.join(cache, os.path.basename(FREEDOS_ZIP["url"]))
    if not os.path.exists(zpath) or sha256(zpath) != FREEDOS_ZIP["sha256"]:
        log(f"downloading {FREEDOS_ZIP['url']}")
        with urllib.request.urlopen(FREEDOS_ZIP["url"], timeout=300) as r, open(zpath + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(zpath + ".part", zpath)
    if sha256(zpath) != FREEDOS_ZIP["sha256"]:
        raise RuntimeError(f"{FREEDOS_ZIP['url']}: sha256 isn't {FREEDOS_ZIP['sha256']}")
    with zipfile.ZipFile(zpath) as zf, zf.open(FREEDOS_BOOT["zip"]) as src, open(boot, "wb") as dst:
        shutil.copyfileobj(src, dst)
    if sha256(boot) != FREEDOS_BOOT["sha256"]:
        raise RuntimeError(f"{FREEDOS_BOOT['zip']}: sha256 isn't {FREEDOS_BOOT['sha256']}")
    return boot


def make_dos_floppy(path):
    """The FreeDOS boot floppy that runs AUDTEST SAP instead of the installer."""
    shutil.copyfile(freedos_boot_floppy(), path)
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    tmp = os.path.dirname(path)
    for name, text in (("FDCONFIG.SYS", FDCONFIG), ("AUDIO.BAT", AUDIO_BAT)):
        with open(os.path.join(tmp, name), "w", newline="") as f:
            f.write(text)
    for name, src in (("FDCONFIG.SYS", os.path.join(tmp, "FDCONFIG.SYS")),
                      ("AUDIO.BAT", os.path.join(tmp, "AUDIO.BAT")),
                      ("AUDTEST.COM", os.path.join(GUESTS, "AUDTEST.COM"))):
        subprocess.run(["mcopy", "-o", "-i", path, src, f"::/{name}"], check=True, env=env)
    return path


def guest_args(case, out, floppy, serial):
    """QEMU arguments of the guest (no machine, no audio)."""
    if case["guest"] == "dos":
        return ["-cpu", "pentium", "-m", "32", "-vga", "std",
                "-drive", f"if=floppy,index=0,format=raw,file={floppy},readonly=on", "-boot", "a",
                "-serial", f"file:{serial}"]
    return ["-m", "256", "-serial", f"file:{serial}",
            "-kernel", os.path.join(GUESTS, "vmlinuz"), "-initrd", os.path.join(GUESTS, "initrd.gz"),
            "-append", f"console=ttyS0 panic=-1 loglevel=4 wsh.mods={case['mods']}"]


def guest_timeout(case, kvm):
    if case["guest"] == "dos":
        return 120
    return 90 if kvm else 300


def run_qemu(argv, timeout, logpath):
    """Run QEMU until the guest powers off; on timeout SIGTERM, then SIGKILL. The wav file is read
    the same way either way: QEMU leaves its header sizes 0 (wavcheck.py)."""
    t0 = time.time()
    with open(logpath, "w") as lf:
        lf.write(" ".join(shlex.quote(a) for a in argv) + "\n\n")
        lf.flush()
        p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT)
        try:
            code = p.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            p.send_signal(signal.SIGTERM)
            try:
                code = p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
                code = p.wait()
    return {"exit": code, "timed_out": timed_out, "seconds": round(time.time() - t0, 1)}


def read_text(path):
    try:
        with open(path, encoding="latin-1") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def judge(case, wav, serial, run):
    """The verdict of one run: the tones in the wav file and the guest's own report."""
    res = {"run": run, "notes": []}
    absent = [t for t in (DOS_TONES if case["guest"] == "dos" else [LINUX]) if t not in case["expect"]]
    try:
        a = wavcheck.analyse(wav)
        ok, reasons = wavcheck.check(a, case["expect"], absent)
    except (OSError, ValueError) as e:
        a, ok, reasons = None, False, [f"no wav: {e}"]
    res["wav"] = a
    res["tones_found"] = [t["freq_hz"] for t in a["tones"]] if a else []
    res["notes"] += reasons
    text = read_text(serial)
    res["serial_tail"] = text[-1500:]
    if case["guest"] == "linux":
        m = re.search(r"AUDIOTEST result=(\S+) card=(\S+)(?: index=(\S+))? rc=(\S+)", text)
        res["guest_report"] = m.group(0) if m else None
        res["card"] = m.group(2) if m else None
        if not m or m.group(1) != "ok":
            ok = False
            res["notes"].append(f"guest: {m.group(0) if m else 'no AUDIOTEST line'}")
        res["notes"] += [n.group(1) for n in re.finditer(r"AUDIOTEST note: (.*)", text)]
    else:
        res["guest_report"] = "; ".join(l.strip() for l in text.splitlines() if l.startswith(("SB16", "OPL2", "PC speaker", "AUDTEST"))) or None
        if "AUDTEST: done" not in text:
            res["notes"].append("guest: AUDTEST did not finish")
            ok = False
    if run.get("timed_out"):
        res["notes"].append(f"no power off within {run['seconds']} s")
    res["ok"] = ok
    return res


# ---------------------------------------------------------------------------------------------
# direct QEMU

def run_direct(cases, out):
    kvm = kvm_usable()
    floppy = None
    results = []
    for case in cases:
        d = os.path.join(out, case["id"])
        os.makedirs(d, exist_ok=True)
        if case["guest"] == "dos" and floppy is None:
            floppy = make_dos_floppy(os.path.join(out, "audtest-floppy.img"))
        wav, serial = os.path.join(d, "out.wav"), os.path.join(d, "serial.log")
        for p in (wav, serial):
            if os.path.exists(p):
                os.unlink(p)
        accel = "kvm:tcg" if kvm and case["guest"] == "linux" else "tcg"
        machine = f"{case.get('machine', 'pc')},accel={accel}"
        if case.get("machine_props"):
            machine += "," + case["machine_props"].format(a="snd0")
        argv = [QEMU, "-machine", machine, "-nodefaults", "-display", "none", "-no-reboot",
                "-audiodev", f"wav,id=snd0,path={wav}"]
        argv += guest_args(case, d, floppy, serial)
        argv += [x.format(a="snd0") for x in case["args"]]
        log(f"== {case['id']}")
        run = run_qemu(argv, guest_timeout(case, kvm and case["guest"] == "linux"), os.path.join(d, "qemu.log"))
        r = judge(case, wav, serial, run)
        r.update({"id": case["id"], "path": "qemu", "guest": case["guest"], "device": case["device"],
                  "expect": case["expect"], "accel": accel})
        log(f"   {'ok ' if r['ok'] else 'FAIL'} tones {r['tones_found']} {'; '.join(r['notes'])}")
        results.append(r)
    return results


# ---------------------------------------------------------------------------------------------
# through qemu-server

def qm(*a, check=True, timeout=120):
    return sh("qm", *a, check=check, timeout=timeout)


def qm_wait_stopped(vmid, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if "status: stopped" in qm("status", str(vmid), check=False):
            return round(time.time() - t0, 1)
        time.sleep(1)
    return None


def run_pve(cases, out):
    if not os.path.exists("/run/pve-e2e-ready"):
        raise RuntimeError("the PVE node isn't up (/run/pve-e2e-ready missing)")
    kvm = kvm_usable()
    floppy_dir = "/var/lib/vz/template/floppy"
    os.makedirs(floppy_dir, exist_ok=True)
    cfg = sh("pvesh", "get", "/storage/local", "--output-format", "json")
    types = set(json.loads(cfg).get("content", "").split(","))
    if "floppy" not in types:
        sh("pvesm", "set", "local", "--content", ",".join(sorted((types - {""}) | {"floppy"})))
    floppy = None
    results = []
    for n, case in enumerate(cases):
        vmid = 9100 + n
        d = os.path.join(out, case["id"])
        os.makedirs(d, exist_ok=True)
        if case["guest"] == "dos" and floppy is None:
            floppy = make_dos_floppy(os.path.join(floppy_dir, "audtest.img"))
        serial, wav = os.path.join(d, "serial.log"), os.path.join(d, "out.wav")
        recording = PVE_WAV.format(vmid=vmid)
        for p in (serial, wav, recording):
            if os.path.exists(p):
                os.unlink(p)
        qm("destroy", str(vmid), "--purge", check=False)
        use_kvm = kvm and case["guest"] == "linux"
        opts = ["--name", f"audio-{case['audio'].lower()}", "--ostype", "other",
                "--machine", case.get("machine", "pc"), "--kvm", "1" if use_kvm else "0",
                "--audio0", f"device={case['audio']},driver=wav", "--tablet", "0", "--balloon", "0"]
        if case["guest"] == "dos":
            opts += ["--memory", "32", "--cpu", "pentium", "--vga", "std",
                     "--floppy0", "local:floppy/audtest.img", "--boot", "order=floppy0",
                     "--args", f"-serial file:{serial}"]
        else:
            g = guest_args(case, d, None, serial)
            opts += ["--memory", "256", "--vga", "std", "--args", " ".join(shlex.quote(x) for x in g[2:])]
        log(f"== {case['id']} (VM {vmid})")
        r = {"id": case["id"], "path": "pve", "guest": case["guest"], "device": f"audio0: device={case['audio']}",
             "expect": case["expect"], "accel": "kvm" if use_kvm else "tcg", "notes": []}
        try:
            qm("create", str(vmid), *opts)
            cmd = qm("showcmd", str(vmid)).strip()
            with open(os.path.join(d, "showcmd.txt"), "w") as f:
                f.write(cmd + "\n")
            argv = shlex.split(cmd)
            r["audio_args"] = [f"{argv[i]} {argv[i + 1]}" for i in range(len(argv) - 1)
                               if argv[i] in ("-device", "-machine", "-audiodev")
                               and re.search(r"audio|sb16|adlib|hda|AC97", argv[i + 1])]
            want = [rx.replace("=B", "=" + PVE_BACKEND) for rx in case["showcmd"]]
            want.append(r"-audiodev '?wav,id=" + PVE_BACKEND + ",path=" + re.escape(recording) + "'?")
            missing = [rx for rx in want if not re.search(rx, cmd)]
            r["showcmd_ok"] = not missing
            if missing:
                r["notes"].append(f"showcmd lacks {missing}")
            # a real start: the guest plays into the wav file and powers off
            t0 = time.time()
            qm("start", str(vmid), timeout=180)
            took = qm_wait_stopped(vmid, guest_timeout(case, use_kvm))
            run = {"exit": None, "timed_out": took is None, "seconds": round(time.time() - t0, 1)}
            if took is None:
                qm("stop", str(vmid), check=False)
            if os.path.exists(recording):
                shutil.copyfile(recording, wav)
            j = judge(case, wav, serial, run)
            r.update({k: v for k, v in j.items() if k != "notes"})
            r["notes"] += j["notes"]
            r["wav_ok"] = j["ok"]
            r["ok"] = bool(r["showcmd_ok"] and r["wav_ok"])
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            r["ok"] = False
            r["notes"].append(str(e)[:500])
        finally:
            qm("stop", str(vmid), check=False)
            qm("destroy", str(vmid), "--purge", check=False)
        log(f"   {'ok ' if r['ok'] else 'FAIL'} tones {r.get('tones_found')} {'; '.join(r['notes'])}")
        results.append(r)
    return results


def run_pve_wav_server(out):
    """driver=wav with a server= must not start: the path is fixed, so that a VM config can't make
    QEMU (which runs as root) write anywhere else."""
    vmid = 9100 + len(PVE_CASES)
    d = os.path.join(out, PVE_WAV_SERVER)
    os.makedirs(d, exist_ok=True)
    target = os.path.join(d, "elsewhere.wav")
    if os.path.exists(target):
        os.unlink(target)
    log(f"== {PVE_WAV_SERVER} (VM {vmid})")
    r = {"id": PVE_WAV_SERVER, "path": "pve", "guest": "-", "accel": "-", "expect": [],
         "device": "audio0: device=AC97,driver=wav,server=<path>", "notes": []}
    qm("destroy", str(vmid), "--purge", check=False)
    try:
        qm("create", str(vmid), "--name", "audio-wav-server", "--ostype", "other", "--kvm", "0",
           "--memory", "32", "--audio0", f"device=AC97,driver=wav,server={target}")
        p = subprocess.run(["qm", "start", str(vmid)], capture_output=True, text=True, timeout=60)
        text = (p.stderr + p.stdout).strip()
        running = "status: running" in qm("status", str(vmid), check=False)
        r["ok"] = (p.returncode != 0 and not running and not os.path.exists(target)
                   and "can't set the path of driver 'wav'" in text)
        r["notes"].append(f"qm start: exit {p.returncode}: {text.splitlines()[-1] if text else ''}")
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        r["ok"] = False
        r["notes"].append(str(e)[:500])
    finally:
        qm("stop", str(vmid), check=False)
        qm("destroy", str(vmid), "--purge", check=False)
    log(f"   {'ok ' if r['ok'] else 'FAIL'} {'; '.join(r['notes'])}")
    return r


# ---------------------------------------------------------------------------------------------
# summary

def fmt_tones(r):
    return ", ".join(f"{t:g}" for t in r.get("tones_found") or []) or "-"


def summary(inv, results):
    lines = ["## x86 audio matrix", ""]
    if inv:
        p = inv["packages"]
        lines += [f"Packages: pve-qemu-kvm {p.get('pve-qemu-kvm')}, qemu-server {p.get('qemu-server')}, "
                  f"pve-manager {p.get('pve-manager')}. Audio backends in QEMU: {', '.join(inv['audiodev_drivers'])}. "
                  f"qemu-server drivers: {', '.join(inv['qemu_server'].get('drivers', []))}.", "",
                  "| QEMU sound device | bus | offered by qemu-server |", "|---|---|---|"]
        offered = {d.lower() for d in inv["qemu_server"].get("devices", [])}
        for dv in inv["qemu_sound_devices"]:
            names = {dv["name"].lower(), (dv["alias"] or "").lower()}
            lines.append(f"| `{dv['name']}` | {dv['bus']} | {'yes' if names & offered else 'no'} |")
        lines.append(f"| `pcspk` (machine property) | ISA | {'yes' if 'pcspk' in offered else 'no'} |")
        lines.append("")
    if results:
        lines += ["| case | path | guest | device | expected Hz | tones found | s | result | notes |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in results:
            exp = ", ".join(f"{t:g}" for t in r["expect"]) or "-"
            note = "; ".join(r.get("notes") or [])
            if r.get("card"):
                note = f"card {r['card']}" + (f"; {note}" if note else "")
            if "showcmd_ok" in r:
                bits = [f"showcmd {'ok' if r['showcmd_ok'] else 'FAIL'}",
                        f"qm start + wav {'ok' if r.get('wav_ok') else 'FAIL'}"]
                note = ", ".join(bits) + (f"; {note}" if note else "")
            h = (r.get("wav") or {}).get("header")
            if h:
                note += ("; " if note else "") + ("header sizes set" if h["sizes_ok"] else
                         f"header sizes {h['riff_size']}/{h['data_size']} for {h['data_bytes']} data bytes")
            secs = (r.get("run") or {}).get("seconds")
            lines.append(f"| {r['id']} | {r['path']} ({r['accel']}) | {r['guest']} | {r['device']} | {exp} | "
                         f"{fmt_tones(r)} | {'-' if secs is None else secs} | {'pass' if r['ok'] else 'FAIL'} | "
                         f"{note.replace('|', '/')} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("what", choices=["inventory", "qemu", "pve", "all"])
    p.add_argument("--out", default="/tmp/audio-runs")
    p.add_argument("--only", default="", help="comma-separated case ids")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    pick = (lambda cs: [c for c in cs if not only or c["id"] in only])
    path = os.path.join(a.out, "results.json")
    data = {"inventory": None, "results": []}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    if a.what in ("inventory", "all"):
        data["inventory"] = inventory()
        log(json.dumps(data["inventory"], indent=2))
    new = []
    if a.what in ("qemu", "all"):
        new += run_direct(pick(CASES), a.out)
    if a.what in ("pve", "all"):
        new += run_pve(pick(PVE_CASES), a.out)
        if not only or PVE_WAV_SERVER in only:
            new.append(run_pve_wav_server(a.out))
    ids = {r["id"] for r in new}
    data["results"] = [r for r in data["results"] if r["id"] not in ids] + new
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    md = summary(data["inventory"], data["results"])
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write(md + "\n")
    log(md)
    return 0 if all(r["ok"] for r in new) else 1


if __name__ == "__main__":
    sys.exit(main())
