#!/usr/bin/env python3
"""Boot wisp-netbsd (the NetBSD sibling of wisp) under a QEMU binary and check its markers.

    ./run.py --arch sparc32 [--arch sparc64 ...|--arch all] [--machine SS-20 ...] [--qemu-dir DIR]
             [--label tcg] [--repeat 2] [--json results.jsonl] [--log-dir logs]

Each run starts QEMU with -kernel out/<arch>/kernel (a NetBSD kernel with its memory-disk root and
PID 1 inside) on a serial console and stops at power-off (or at --timeout). On sparc64 the same
kernel boots from out/sparc64/disk.img instead, through OpenBIOS's "boot disk", NetBSD's bootblk
and ofwboot: OpenBIOS's -kernel on sun4u only starts Linux images. PID 1 prints wisp's
markers, so this runner reuses e2e/wisp/run.py for booting, parsing the result line, the CRC
check and the tables; only the kernel's first line differs (NetBSD's banner, not "Linux
version"), and the WISP-CHECK lines (clock, file) are checked here. Python standard library only.
"""

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_wisp_run():
    """e2e/wisp/run.py (or /wisp/run.py in the image) as the module wisp_run: this file is run.py
    too, so a plain import would find itself."""
    for candidate in (os.path.join(HERE, "..", "wisp"), "/wisp"):
        path = os.path.join(candidate, "run.py")
        if os.path.isfile(path):
            sys.path.insert(0, candidate)  # for its own imports (shell, tier2)
            spec = importlib.util.spec_from_file_location("wisp_run", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError("wisp's run.py not found (e2e/wisp or /wisp)")


wisp_run = load_wisp_run()

# arch -> QEMU binary, machine arguments, memory (MiB), how the kernel is loaded ("kernel":
# QEMU's -kernel; "disk": the boot disk). The arch names are wisp's (the result line's arch= must
# match), the kernels NetBSD's sparc, sparc64 and amd64.
ARCHES = {
    "sparc32": ("qemu-system-sparc", ["-M", "SS-5"], 128, "kernel"),
    "sparc64": ("qemu-system-sparc64", ["-M", "sun4u"], 256, "disk"),
    "x86_64": ("qemu-system-x86_64", ["-M", "pc"], 128, "kernel"),
}

# The checks PID 1 runs before its result line; each must say ok=1.
CHECKS = ("clock", "file")

# Console markers, in boot order. NetBSD's kernel prints its copyright, then
# "NetBSD 11.1 (WISP)", each line after a "[   1.0000000] " time stamp; PID 1's lines are wisp's.
MARKERS = (
    ("t_kernel", re.compile(r"(?:^|\] )NetBSD \d+\.\d+\S* \(")),
    ("t_banner", re.compile(r"^WISP-BANNER ")),
    ("t_result", re.compile(r"^WISP-RESULT ")),
)
wisp_run.MARKERS = MARKERS

CHECK_LINE = re.compile(r"^WISP-CHECK name=(\w+) ok=(\d)(.*)$")


def qemu_command(arch, qemu_dir=None, kernel=None, machine=None, memory=None, firmware=None,
                 out=None):
    """The QEMU command line for one boot. NetBSD takes no console= (it uses the firmware's
    console device, ttya on sparc, com0 on the PC), so there is no -append."""
    binary, machine_args, default_mem, load = ARCHES[arch]
    if qemu_dir:
        binary = os.path.join(qemu_dir, binary)
    if machine:
        machine_args = ["-M", machine, *machine_args[2:]]
    cmd = [binary, *machine_args, "-m", str(memory or default_mem), "-display", "none",
           "-serial", "stdio", "-monitor", "none", "-no-reboot", "-nodefaults"]
    if firmware:
        cmd += ["-L", firmware]
    out = out or os.path.join(HERE, "out")
    if load == "disk":
        # an IDE disk can't be read-only: snapshot=on keeps the image as it is
        disk = os.path.join(out, arch, "disk.img")
        cmd += ["-drive", f"file={disk},format=raw,if=ide,index=0,snapshot=on", "-boot", "c"]
    else:
        cmd += ["-kernel", kernel or os.path.join(out, arch, "kernel")]
    return cmd


def scan_checks(lines):
    """{name: {"ok": bool, field: value, ...}} of the WISP-CHECK lines."""
    checks = {}
    for _, text in lines:
        m = CHECK_LINE.match(text.strip())
        if not m:
            continue
        fields = dict(item.partition("=")[::2] for item in m.group(3).split())
        checks[m.group(1)] = {"ok": m.group(2) == "1", **fields}
    return checks


def evaluate(arch, raw):
    """wisp's evaluation of the result line, plus the checks."""
    rec = wisp_run.evaluate(arch, raw, None)
    checks = scan_checks(raw["lines"])
    for name in CHECKS:
        if name not in checks:
            rec["problems"].append(f"no {name} check")
        elif not checks[name]["ok"]:
            rec["problems"].append(f"{name} check failed")
    rec["checks"] = checks
    rec["ok"] = not rec["problems"]
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arch", action="append", choices=[*ARCHES, "all"], required=True)
    ap.add_argument("--qemu-dir", help="directory with the qemu-system-* binaries (default: PATH)")
    ap.add_argument("--label", default="", help="free text recorded with each run")
    ap.add_argument("--machine", action="append",
                    help="override -M (e.g. SS-20 for sparc32); repeat it to boot each in turn")
    ap.add_argument("--memory", type=int, help="override -m (MiB)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--firmware", default=os.environ.get("WISP_FIRMWARE"),
                    help="QEMU -L directory (default: $WISP_FIRMWARE)")
    ap.add_argument("--out", default=os.path.join(HERE, "out"), help="build output directory")
    ap.add_argument("--json", help="append one JSON object per run to this file")
    ap.add_argument("--log-dir", help="write each run's timestamped console log here")
    args = ap.parse_args(argv)

    arches = list(ARCHES) if "all" in args.arch else args.arch
    records = []
    for arch in arches:
        for machine in args.machine or [None]:
            for n in range(1, args.repeat + 1):
                cmd = qemu_command(arch, args.qemu_dir, None, machine, args.memory,
                                   args.firmware, args.out)
                log_path = None
                if args.log_dir:
                    os.makedirs(args.log_dir, exist_ok=True)
                    tag = "-".join(x for x in (arch, args.label, machine, str(n)) if x)
                    log_path = os.path.join(args.log_dir, f"{tag}.log")
                raw = wisp_run.boot(cmd, args.timeout, log_path)
                rec = evaluate(arch, raw)
                rec.update(label=args.label, run=n, machine_arg=machine or ARCHES[arch][1][1],
                           qemu=cmd[0])
                records.append(rec)
                line = json.dumps(rec, sort_keys=True)
                print(line, flush=True)
                if args.json:
                    with open(args.json, "a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
    print(wisp_run.table(records), file=sys.stderr)
    return 0 if all(r["ok"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
