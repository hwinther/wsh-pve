#!/usr/bin/env python3
"""The first-megabyte matrix: what DOS 6.22 gets of 640K-1M under QEMU/SeaBIOS in a PVE VM, per VM
configuration (VGA model, NIC option ROM, dummy option ROMs) and per CONFIG.SYS (HIMEM, EMM386 NOEMS /
RAM / HIGHSCAN, I= ranges).

    dos_mem.py --vmid 302 --runs /work/runs/mem1 [--only stock --only dummy100k] [--configs a,b]

Runs on the PVE node (the e2e node with the lab, pve.Dockerfile) against an installed `msdos622` VM
(`lab.py install msdos622`): adds the tools disk (dos_tools.py, built from dos_drivers.iso) as ide1 =
D:, writes the dummy ROMs to /var/lib/vz/template/dos/, and for each VARIANT sets the VM's options
(`qm set`, `args:` for what PVE has no option for), runs scenarios/dos-mem.py against it and reads the
results from the tools disk. Each variant also gets SeaBIOS's debug log (isa-debugcon on port 0x402,
which costs no memory): it says where option ROMs went and "Space available for UMB". Prints a Markdown
table (also <runs>/summary.md, <runs>/results.json); every screen is evidence in <runs>/<variant>/.

The parsing functions are pure and tested in tests/test_dos_mem.py.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROMDIR = "/var/lib/vz/template/dos"

# CONFIG.SYS variants (C:\DOS from SETUP). `{gap}` is the I= range of the free gap SeaBIOS reports.
HIMEM = "DEVICE=C:\\DOS\\HIMEM.SYS"
EMM = "DEVICE=C:\\DOS\\EMM386.EXE"
CONFIGS = {
    "none": ["FILES=30"],
    "himem": [HIMEM, "DOS=HIGH", "FILES=30"],
    "emm-noems": [HIMEM, f"{EMM} NOEMS", "DOS=HIGH,UMB", "FILES=30"],
    "emm-ram": [HIMEM, f"{EMM} RAM", "DOS=HIGH,UMB", "FILES=30"],
    "emm-highscan": [HIMEM, f"{EMM} NOEMS HIGHSCAN", "DOS=HIGH,UMB", "FILES=30"],
    "emm-noems-gap": [HIMEM, f"{EMM} NOEMS I={{gap}}", "DOS=HIGH,UMB", "FILES=30"],
    "emm-ram-gap": [HIMEM, f"{EMM} RAM I={{gap}}", "DOS=HIGH,UMB", "FILES=30"],
    # too far: into SeaBIOS's own data at the top of the E segment (it is writable RAM)
    "emm-noems-e": [HIMEM, f"{EMM} NOEMS I={{gap_start}}-EFFF", "DOS=HIGH,UMB", "FILES=30"],
}

# VM variants: options for `qm set` (None deletes), plus extra `args:` beyond the debug console.
VARIANTS = {
    "stock": {},  # the msdos622 profile: std VGA, ne2k_pci
    "no-nic": {"net0": None},
    "nic-romfile-empty": {"_args": "-global ne2k_pci.romfile="},
    "cirrus": {"vga": "cirrus"},
    "vmware": {"vga": "vmware"},
    "dummy4k": {"_args": f"-option-rom {ROMDIR}/dummy4k.rom"},
    "dummy32k": {"_args": f"-option-rom {ROMDIR}/dummy32k.rom"},
    "dummy100k": {"_args": f"-option-rom {ROMDIR}/dummy100k.rom"},
    "owner-dummy": {"_args": f"-option-rom {ROMDIR}/owner-dummy.rom"},
    "no-nic-no-vapic": {"net0": None, "_args": "-global apic-common.vapic=off"},
}
FULL = ",".join(CONFIGS)
BRIEF = "himem,emm-noems,emm-noems-gap"


def gap_range(gap):
    """`cd800-e9000` (SeaBIOS, end exclusive) -> ("CE00", "E8FF"): 4K-aligned EMM386 segments."""
    a, b = (int(x, 16) for x in gap.split("-"))
    start = (a + 0xFFF) & ~0xFFF
    end = (b & ~0xFFF) - 1
    return f"{start >> 4:04X}", f"{end >> 4:04X}"


def config_lines(name, gap=""):
    lines = CONFIGS[name]
    if any("{gap" in x for x in lines):
        if not gap:
            raise ValueError(f"{name} needs the SeaBIOS UMB gap")
        s, e = gap_range(gap)
        lines = [x.format(gap=f"{s}-{e}", gap_start=s) for x in lines]
    return lines


# --- parsing -----------------------------------------------------------------------------------------

def parse_seabios(log):
    """Option ROMs and the free gap from SeaBIOS's debug log (the last boot in it: the log grows with
    every reset)."""
    log = log.split("SeaBIOS (version")[-1]
    roms = [int(x, 16) << 4 for x in re.findall(r"Running option rom at ([0-9a-f]{4}):0003", log)]
    m = re.search(r"Space available for UMB: ([0-9a-f]+)-([0-9a-f]+)", log)
    return {"roms": [f"{r:05X}" for r in roms],
            "umb_gap": f"{m.group(1)}-{m.group(2)}" if m else "",
            "gap_kb": (int(m.group(2), 16) - int(m.group(1), 16)) // 1024 if m else 0,
            "genroms": re.findall(r"/rom@genroms/([^\s]+)", log)}


def _num(s):
    return int(s.replace(",", ""))


def parse_mem(text):
    """MEM or MEM /D: free conventional, largest executable, largest free UMB, upper totals, the free
    upper blocks (segment, bytes) from the upper memory detail, and the page frame when listed."""
    out = {}
    m = re.search(r"Largest executable program size\s+([\d,]+)", text)
    if m:
        out["largest_exe"] = _num(m.group(1))
    m = re.search(r"Largest free upper memory block\s+([\d,]+)", text)
    if m:
        out["largest_umb"] = _num(m.group(1))
    m = re.search(r"^\s*Conventional\s+([\d,]+)K?\s+([\d,]+)K?\s+([\d,]+)K?", text, re.M)
    if m:
        out["conv_free"] = _num(m.group(3))
    m = re.search(r"^\s*Upper\s+([\d,]+)K?\s+([\d,]+)K?\s+([\d,]+)K?", text, re.M)
    if m:
        out["upper_total"], out["upper_used"], out["upper_free"] = (_num(m.group(i)) for i in (1, 2, 3))
    m = re.search(r"^\s*Reserved\s+([\d,]+)K?", text, re.M)
    if m:
        out["reserved"] = _num(m.group(1))
    up = text.split("Upper Memory Detail", 1)
    if len(up) == 2:
        body = up[1].split("Memory Summary", 1)[0]
        rows = re.findall(r"^\s*([0-9A-F]{5})\s+(?:(\d+)\s+)?([\d,]+)\s+\(\s*\d+K\)\s+(\S*)\s*(.*?)\s*$", body, re.M)
        out["umb_blocks"] = [(seg, _num(size), name, kind) for seg, _region, size, name, kind in rows]
        out["umb_free_blocks"] = [(seg, size) for seg, size, name, kind in out["umb_blocks"] if "Free" in kind]
    out["high"] = bool(re.search(r"resident in the high memory area", text))
    return out


def parse_emm386(text):
    out = {"active": bool(re.search(r"EMM386.*(active|Active)", text)) and "not installed" not in text}
    m = re.search(r"Page frame segment[ .]*([0-9A-F]{4})", text)
    out["page_frame"] = m.group(1) if m else None
    m = re.search(r"Available expanded memory[ .]*(\d+) KB", text)
    out["ems_kb"] = int(m.group(1)) if m else None
    return out


UMASCAN_ROWS = ["F000", "E000", "D000", "C000", "B000", "A000"]


def parse_umascan(screen):
    """UMASCAN's map: {segment row: 32 cells (2K each)} with R (ROM), + (RAM), V (video), E (EMS
    frame), U (unknown), . (unused), and the runs of each kind from C0000 to EFFFF."""
    rows = {}
    for line in screen.splitlines():
        m = re.match(r"^[│|]?\s*([A-F]000) (.{8}) (.{8}) (.{8}) (.{8})", line)
        if m and m.group(1) in UMASCAN_ROWS:
            rows[m.group(1)] = "".join(m.group(i) for i in range(2, 6)).replace(" ", ".")
    cells = "".join(rows.get(r, "?" * 32) for r in ("C000", "D000", "E000"))
    runs, start = [], 0
    for i in range(1, len(cells) + 1):
        if i == len(cells) or cells[i] != cells[start]:
            runs.append({"kind": cells[start], "start": f"{0xC0000 + start * 2048:05X}",
                         "kb": (i - start) * 2})
            start = i
    return {"rows": rows, "runs": runs,
            "largest_unused_kb": max([r["kb"] for r in runs if r["kind"] == "."], default=0),
            "largest_ram_kb": max([r["kb"] for r in runs if r["kind"] == "+"], default=0)}


def summarise(r, files):
    """One row of the table from a dos-mem.py result and the files it wrote."""
    mem = parse_mem(files.get(f"K{r['n']}.TXT", "")) if not r.get("hang") else {}
    emm = parse_emm386(files.get(f"K{r['n']}E.TXT", "")) if not r.get("hang") else {}
    blocks = mem.get("umb_free_blocks", [])
    return {"config": r["config"], "hang": r.get("hang"), "conv_free": mem.get("conv_free"),
            "largest_exe": mem.get("largest_exe"), "largest_umb": mem.get("largest_umb"),
            "upper_total": mem.get("upper_total"), "umb_blocks": blocks, "page_frame": emm.get("page_frame"),
            "umascan": r.get("umascan", {}).get("runs"), "line": " ".join(r["lines"][1:2])}


# --- the runner ----------------------------------------------------------------------------------------

def sh(*cmd, check=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(map(str, cmd))}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def prepare(vmid, iso):
    import dos_tools

    os.makedirs(ROMDIR, exist_ok=True)
    for kb in (4, 32, 100):
        with open(f"{ROMDIR}/dummy{kb}k.rom", "wb") as f:
            f.write(dos_tools.option_rom(kb))
    with open(f"{ROMDIR}/owner-dummy.rom", "wb") as f:
        f.write(dos_tools.owner_rom())
    conf = sh("qm", "config", vmid)
    if "ide1:" not in conf:
        raw = f"{ROMDIR}/tools-{vmid}.raw"
        dos_tools.build_disk(iso, raw)
        sh("qm", "set", vmid, "--ide1", f"local:0,import-from={raw},format=raw")
        os.unlink(raw)
    conf = dict(line.split(": ", 1) for line in sh("qm", "config", vmid).splitlines() if ": " in line)
    return conf


def apply_variant(vmid, base, variant, sblog):
    opts = VARIANTS[variant]
    for k in ("vga", "net0"):
        want = opts.get(k, base.get(k)) if k in opts else base.get(k)
        if want is None:
            sh("qm", "set", vmid, "--delete", k, check=False)
        else:
            sh("qm", "set", vmid, f"--{k}", want)
    args = f"-chardev file,id=sb,path={sblog} -device isa-debugcon,iobase=0x402,chardev=sb"
    if opts.get("_args"):
        args += " " + opts["_args"]
    sh("qm", "set", vmid, "--args", args)


def tools_disk(vmid):
    conf = dict(line.split(": ", 1) for line in sh("qm", "config", vmid).splitlines() if ": " in line)
    return sh("pvesm", "path", conf["ide1"].split(",")[0])


def read_out(vmid):
    import dos_tools

    disk = tools_disk(vmid)
    names = re.findall(r"^(\S+)\s+TXT", sh("mdir", "-i", f"{disk}@@{dos_tools.SPT * 512}", "::/OUT",
                                            check=False), re.M)
    return {f"{n}.TXT": dos_tools.read_file(disk, f"OUT/{n}.TXT") for n in names}


def table(rows):
    def kb(x):
        return "-" if x is None else f"{x // 1024}K"

    out = ["| VM | CONFIG.SYS | SeaBIOS ROMs / free gap | conventional free | largest program | UMB total | "
           "largest UMB | free UMB blocks | EMS frame | UMASCAN C000-EFFF |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if r.get("hang"):
            out.append(f"| {r['variant']} | {r['config']} | {r['seabios']} | hang: {r['hang'][:60]} | | | | | | |")
            continue
        blocks = ", ".join(f"{s}:{n // 1024}K" for s, n in r["umb_blocks"]) or "-"
        scan = " ".join(f"{x['kind']}{x['kb']}" for x in (r["umascan"] or []))
        out.append(f"| {r['variant']} | {r['config']} | {r['seabios']} | {kb(r['conv_free'])} | {kb(r['largest_exe'])} | "
                   f"{kb(r['upper_total'])} | {kb(r['largest_umb'])} | {blocks} | {r['page_frame'] or '-'} | {scan} |")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vmid", required=True)
    p.add_argument("--runs", required=True)
    p.add_argument("--iso", default="/mnt/sparc/iso/dos_drivers.iso")
    p.add_argument("--only", action="append", help="variants (default: all)")
    p.add_argument("--configs", help=f"CONFIG.SYS variants for every VM variant (stock: {FULL}; others: {BRIEF})")
    a = p.parse_args()
    os.makedirs(a.runs, exist_ok=True)
    base = prepare(a.vmid, a.iso)
    rows = []
    for variant in a.only or list(VARIANTS):
        work = os.path.join(a.runs, variant)
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        sblog = os.path.join(work, "seabios.log")
        apply_variant(a.vmid, base, variant, sblog)
        configs = a.configs or (FULL if variant == "stock" else BRIEF)
        print(f"=== {variant}: {configs}", flush=True)
        with open(os.path.join(work, "lab.log"), "w", encoding="utf-8") as log:
            subprocess.run([sys.executable, os.path.join(HERE, "lab.py"), "run",
                            os.path.join(HERE, "scenarios", "dos-mem.py"), "--pve", a.vmid, "--out", work,
                            "--var", f"CONFIGS={configs}", "--var", f"SBLOG={sblog}",
                            "--var", f"MSD={'1' if variant == 'stock' else '0'}"],
                           stdout=log, stderr=subprocess.STDOUT, timeout=3600)
        res = json.load(open(os.path.join(work, "result.json"), encoding="utf-8"))
        sb = parse_seabios(open(sblog, encoding="latin-1").read()) if os.path.exists(sblog) else {}
        files = read_out(a.vmid)
        for name, text in files.items():
            with open(os.path.join(work, name), "w", encoding="utf-8") as f:
                f.write(text)
        mem = res.get("metrics", {}).get("dos_mem", [])
        seabios = f"{' '.join(sb.get('roms', []))} / {sb.get('umb_gap', '?')} ({sb.get('gap_kb', '?')}K)"
        for r in mem:
            rows.append({"variant": variant, "seabios": seabios, **summarise(r, files)})
        if res["code"]:
            rows.append({"variant": variant, "config": "-", "seabios": seabios, "hang": res["status"].splitlines()[0]})
        print(f"=== {variant}: {res['status'].splitlines()[0]} ({res['elapsed']}s)", flush=True)
    # back to the profile
    apply_variant(a.vmid, base, "stock", "/dev/null")
    sh("qm", "set", a.vmid, "--delete", "args", check=False)
    t = table(rows)
    print("\n" + t)
    with open(os.path.join(a.runs, "summary.md"), "w", encoding="utf-8") as f:
        f.write(t + "\n")
    with open(os.path.join(a.runs, "results.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
