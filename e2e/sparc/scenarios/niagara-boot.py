"""-M niagara (sun4v, one UltraSPARC T1 strand) with an OpenSPARC T1 firmware set the user supplies:
OpenBoot's `ok` prompt; with DISK, Sun's Legion disk image (S10image/disk.s10hw2 from the OpenSPARC T1
archive) to a root shell; with ISO, a Solaris 10 DVD to the text installer (submodules/SPARC.md,
"sparc64: niagara (sun4v)").

    # the firmware alone: the ok prompt
    lab.py run scenarios/niagara-boot.py --out /srv/sparc/runs/nia-ok --var FW=/srv/sparc/prom/niagara
    # disk.s10hw2 (Solaris 10 3/05 HW2) to a root shell, then `init 5`
    lab.py run scenarios/niagara-boot.py --out /srv/sparc/runs/nia-hw2 --var FW=... --var MEM=256 \
        --var DISK=/srv/sparc/prom/T1/S10image/disk.s10hw2
    # Solaris 10 1/13 to the installer (needs an MD with 1024 MB and its tlb node, see SPARC.md)
    lab.py run scenarios/niagara-boot.py --out /srv/sparc/runs/nia-s10 --var FW=... --var MEM=1024 \
        --var ISO=/srv/sparc/iso/sol-10-u11-ga-sparc-dvd.iso

Nothing of the firmware is in the image or the repository. When the files aren't there the scenario
is skipped: exit code 0, result.json `status` "skipped: ...", QEMU never starts.

QEMU loads the image (DISK or ISO, the first if=pflash drive) into RAM at 0x1f40000000 on top of -m:
writes never reach the file, so nothing on the host is changed.

  QEMU      qemu-system-sparc64 binary                                   (qemu-system-sparc64)
  FW        directories with the six files QEMU loads (reset.bin q.bin openboot.bin 1up-hv.bin
            1up-md.bin nvram1), ':'-separated; each becomes an -L, the first that has a file wins
            (QEMU also looks in the current directory first)            (/srv/sparc/prom/niagara)
  MEM       MiB; must equal the memory the MD (1up-md.bin/1up-hv.bin) declares  (256)
  DISK      a Legion disk image (hsimd driver in the guest): `boot disk`, root login without a
            password, COMMANDS, then POWEROFF                           (none)
  ISO       a Solaris DVD image: `boot /virtual-devices/disk@0:f`, the installer's language
            question, English, its first screen, F2, up to the system identification screen
  BOOT      the OpenBoot command, instead of the one above              (none)
  COMMANDS  shell commands recorded after the DISK login, ';;'-separated
  POWEROFF  the command after them; QEMU's exit (code) or the `ok` prompt is recorded in
            result.json (poweroff); the prompt or exit code 0 pass, an abort fails  (init 5)
  IDLE      seconds over which QEMU's host CPU use is measured at the last stop (the ok prompt, the
            shell, the installer screen)                                (0: not measured)
  TIMEOUT   seconds for a boot to reach its prompt                      (1800)
  WALK      ISO: this many more installer screens with the defaults (F2 on each, the first choice
            marked where none is, HOSTNAME (niagara) and ROOTPW (lab) where asked), stopping at the first screen about
            disks; walk_end in result.json names the last screen       (0)
  EXTRA     more QEMU arguments, shell-quoted
  TRACE     QEMU trace events, comma separated, logged to <out>/trace.log
"""
import json
import os
import re
import shlex
import time

from _sparc64 import shell

FILES = ("reset.bin", "q.bin", "openboot.bin", "1up-hv.bin", "1up-md.bin", "nvram1")
DEFAULTS = {"QEMU": "qemu-system-sparc64", "FW": "/srv/sparc/prom/niagara", "MEM": "256", "DISK": "",
            "ISO": "", "BOOT": "", "COMMANDS": "uname -a ;; cat /etc/release ;; prtconf | head -20 ;; "
            "psrinfo -v ;; df -k ;; ls /dev/dsk /dev/rdsk ;; ifconfig -a", "POWEROFF": "init 5", "IDLE": "0",
            "TIMEOUT": "1800", "WALK": "0", "ROOTPW": "lab", "HOSTNAME": "niagara", "EXTRA": "", "TRACE": ""}
OK = r"(\{\d+\} )?ok $"


def skip(out, v, why):
    print(f"skipped: {why}", flush=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"status": f"skipped: {why}", "code": 0, "elapsed": 0, "vars": v, "metrics": {}}, f, indent=2)
    raise SystemExit(0)


def qemu_args(v, out):
    dirs = [d for d in v["FW"].split(":") if d]
    missing = [f for f in FILES if not any(os.path.isfile(os.path.join(d, f)) for d in dirs)]
    if missing:
        skip(out, v, f"no OpenSPARC T1 firmware ({', '.join(missing)}) in {v['FW']}")
    for k in ("DISK", "ISO"):
        if v[k] and not os.path.isfile(v[k]):
            skip(out, v, f"{k} {v[k]} doesn't exist")
    args = [v["QEMU"], "-M", "niagara", "-m", v["MEM"], "-nodefaults", "-nographic"]
    for d in dirs:
        args += ["-L", d]
    image = v["DISK"] or v["ISO"]
    if image:
        args += ["-drive", f"if=pflash,file={image},format=raw,readonly=on"]
    for ev in filter(None, v["TRACE"].split(",")):
        args += ["-trace", ev]
    if v["TRACE"]:
        args += ["-D", os.path.join(out, "trace.log")]
    return args + shlex.split(v["EXTRA"])


def idle(m, v):
    if int(v["IDLE"]):
        time.sleep(10)
        m.cpu_use(int(v["IDLE"]))


def run(m, v):
    m.expect(r"OpenBoot [\d.]+.*memory available", 300)
    m.expect(OK, 300)
    m.metrics["ok_s"] = round(m.elapsed(), 1)
    m.snap("ok prompt")
    if v["DISK"]:
        disk(m, v)
    elif v["ISO"]:
        installer(m, v)
    else:
        if v["BOOT"]:
            m.send(v["BOOT"] + "\r")
            m.quiet(30, int(v["TIMEOUT"]))
            m.snap(v["BOOT"])
        idle(m, v)


def disk(m, v):
    m.send((v["BOOT"] or "boot disk") + "\r")
    m.expect(r"SunOS Release 5\.\d+", int(v["TIMEOUT"]))
    m.expect(r"console login: ?$", int(v["TIMEOUT"]))
    m.metrics["login_s"] = round(m.elapsed(), 1)
    m.snap("console login")
    m.send("root\r")
    m.expect(r"# ?$", 300)
    shell(m, "true")
    for c in filter(None, (c.strip() for c in v["COMMANDS"].split(";;"))):
        shell(m, c)
        m.snap(c)
    idle(m, v)
    if v["POWEROFF"]:
        t0 = time.time()
        m.send(v["POWEROFF"] + "\r")
        while time.time() - t0 < 600:
            code = m.proc.poll()
            if code is not None:
                m.metrics["poweroff"] = f"QEMU exited with {code}"
                break
            if re.search(OK, m.text[m.pos:], re.M):
                m.metrics["poweroff"] = "ok prompt"
                break
            time.sleep(1)
        else:
            raise AssertionError(f"neither QEMU's exit nor the ok prompt within 600 s of {v['POWEROFF']!r}")
        m.metrics["poweroff_s"] = round(time.time() - t0, 1)
        m.log(f"after {v['POWEROFF']!r}: {m.metrics['poweroff']} ({m.metrics['poweroff_s']} s)")
        if m.proc.poll() is None:
            m.snap(v["POWEROFF"])
        elif m.proc.poll() != 0:  # QEMU aborted (a fatal trap): qemu.stderr has the registers
            raise AssertionError(f"{m.metrics['poweroff']} after {v['POWEROFF']!r}")


def installer(m, v):
    m.send((v["BOOT"] or "boot /virtual-devices/disk@0:f") + "\r")
    m.expect(r"SunOS Release 5\.\d+", int(v["TIMEOUT"]))
    m.metrics["kernel_s"] = round(m.elapsed(), 1)
    m.snap("kernel banner")
    m.expect(r"Select a Language", int(v["TIMEOUT"]))
    m.quiet(3, 120)
    m.metrics["installer_s"] = round(m.elapsed(), 1)
    m.snap("installer: language")
    m.send("0\r")
    m.expect(r"What type of terminal|Installation Program", 600)
    if "terminal" in m.text[m.pos - 200:m.pos]:
        m.quiet(2, 60)
        m.snap("terminal type")
        m.send("3\r")  # DEC VT100
        m.expect(r"Installation Program", 600)
    m.quiet(3, 120)
    m.snap("installer: first screen")
    m.key("f2")
    m.expect(r"Identify This System|Network Connectivity|Host Name", 900, screen=True)
    m.quiet(3, 120)
    m.snap("installer: system identification")
    idle(m, v)
    walk(m, v)


def screen_title(text):
    t = re.search(r"^─ (.+?) ─", text, re.M)
    return t.group(1).strip() if t else text.strip().splitlines()[-1] if text.strip() else ""


def walk(m, v):
    """Up to WALK more installer screens with the defaults: mark the first choice where nothing is
    marked yet, ROOTPW at a password prompt, then F2 (Esc-2); stops at a screen about disks or when a
    screen doesn't change."""
    for i in range(int(v["WALK"])):
        text = m.screen_text()
        title = screen_title(text)
        if re.search(r"Select Disks|No disks|no disks|disk.*found", text, re.I):
            m.metrics["walk_end"] = title
            m.snap(f"installer: {title} (disks)")
            return
        if title == "Host Name":
            m.send(v["HOSTNAME"])
        elif re.search(r"Root Password|password:", text, re.I) and re.search(r"[Pp]assword: *$", text, re.M):
            m.send(v["ROOTPW"] + "\r")
            m.quiet(2, 60)
            m.send(v["ROOTPW"] + "\r")
        elif "[ ]" in text and "[X]" not in text:
            for keys in ((), ("ctrl-n",), ("ctrl-p",)):  # the highlight isn't always on the first entry
                m.key(*keys)
                m.send("\r")
                m.quiet(2, 60)
                if "[X]" in m.screen_text():
                    break
        m.key("f2")
        try:
            m.quiet(4, 900)
        except Exception:
            pass
        after = m.screen_text()
        m.snap(f"installer: {screen_title(after)}")
        if after == text:
            m.metrics["walk_end"] = f"stuck at {title}"
            raise AssertionError(f"installer screen {title!r} didn't change after F2")
    m.metrics["walk_end"] = screen_title(m.screen_text())
