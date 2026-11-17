"""Measure the first megabyte as DOS sees it, for several CONFIG.SYS variants in one VM.

For each name in CONFIGS (dos_mem.CONFIGS): write C:\\CONFIG.SYS, restart (Ctrl-Alt-Del), and at the
prompt run UMASCAN (the owner's map of 640K-1M in 2K cells, read from the VGA text screen: ROM, RAM,
video, EMS frame, unused), `MEM /D` (modules, upper memory detail, summary) and `EMM386` (status,
page frame) into D:\\OUT\\K<n>*.TXT on the tools disk (dos_tools.py), and with MSD=1 `MSD /P` once. The
runner (dos_mem.py) reads those files with mtools after the VM stops and makes the table. A config that
doesn't reach the prompt within BOOT_TIMEOUT is recorded as a hang and the VM is reset.

Variables: CONFIGS (comma separated), GAP (the free gap SeaBIOS reports as "Space available for UMB",
e.g. cd800-e9000, for the `*-gap` configs' I= range; or SBLOG, the SeaBIOS debug log to read it from),
BOOT_TIMEOUT (120), MSD (0).
"""
import json
import os
import sys
import time

import _dos
import lab

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dos_mem  # noqa: E402

DEFAULTS = {"CONFIGS": "himem,emm-noems", "BOOT_TIMEOUT": "120", "MSD": "0", "GAP": "", "SBLOG": ""}


def qemu_args(v, out):
    return _dos.qemu_args({**v, "BOOT": v.get("BOOT", "c")}, out)


def restart(m, timeout):
    m.fb_key("ctrl", "alt", "delete")
    time.sleep(3)
    return _dos.at_prompt(m, timeout)


def recover(m, gap, timeout):
    """After a hang: reset, skip CONFIG.SYS/AUTOEXEC.BAT with F5 at "Starting MS-DOS..." (as a person
    would) and put the HIMEM-only CONFIG.SYS back."""
    m.reset()
    m.vga_expect(r"Starting MS-DOS", timeout=60, interval=0.1)
    _dos.key(m, "f5")
    _dos.at_prompt(m, timeout)
    _dos.write_file(m, "C:\CONFIG.SYS", dos_mem.config_lines("himem", gap))


def measure(m, v, n, name, r, timeout):
    """Boot one CONFIG.SYS and take its measurements into r."""
    restart(m, timeout)
    r["boot_screen"] = m.vga_screen().text
    m.vga_snap(f"K{n} {name}: booted")
    _dos.run(m, "CLS", timeout=30)  # a machine that boots and then hangs fails here
    _dos.type_text(m, "D:\UMASCAN\n")
    # the frame and "Press Esc" come first, the map once every 2K cell is tested: F000 is ROM
    s = m.vga_expect(r"F000 R", timeout=120)
    r["umascan"] = dos_mem.parse_umascan(s.text)
    r["umascan_screen"] = s.text
    m.vga_snap(f"K{n} {name}: UMASCAN")
    _dos.key(m, "esc")
    _dos.at_prompt(m, 30)
    _dos.run(m, f"MEM /D >D:\OUT\K{n}.TXT", timeout=60)
    _dos.run(m, f"EMM386 >D:\OUT\K{n}E.TXT", timeout=60)
    _dos.run(m, "CLS")
    r["mem_screen"] = _dos.run(m, "MEM")
    m.vga_snap(f"K{n} {name}: MEM")
    if v["MSD"] == "1" and n == 1:
        _dos.run(m, "MSD /P D:\OUT\MSD.TXT", timeout=180)


def save(m, gap, results):
    m.metrics["dos_mem"] = results
    m.metrics["gap"] = gap
    with open(os.path.join(m.out, "dos-mem.json"), "w", encoding="utf-8") as f:
        json.dump({"gap": gap, "results": results}, f, indent=1)


def run(m, v):
    timeout = int(v["BOOT_TIMEOUT"])
    _dos.boot_to_prompt(m, 300)
    gap = v["GAP"]
    if not gap and v["SBLOG"] and os.path.exists(v["SBLOG"]):
        gap = dos_mem.parse_seabios(open(v["SBLOG"], encoding="latin-1").read()).get("umb_gap", "")
    _dos.run(m, "DEL D:\OUT\*.TXT")
    results = []
    for n, name in enumerate(v["CONFIGS"].split(","), 1):
        lines = dos_mem.config_lines(name, gap)
        r = {"n": n, "config": name, "lines": lines}
        results.append(r)
        _dos.run(m, "CLS")
        _dos.write_file(m, "C:\CONFIG.SYS", lines)
        try:
            measure(m, v, n, name, r, timeout)
        except lab.QemuDied:
            save(m, gap, results)
            raise
        except Exception as e:  # a config that hangs the machine (at boot or after) is a result too
            r["hang"] = str(e).splitlines()[0]
            m.vga_snap(f"K{n} {name}: hangs")
            recover(m, gap, timeout)
        save(m, gap, results)
    _dos.write_file(m, "C:\CONFIG.SYS", dos_mem.config_lines("himem", gap))
