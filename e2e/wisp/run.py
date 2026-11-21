#!/usr/bin/env python3
"""Boot wisp (the tiny test system) under a QEMU binary and report what it measured.

    ./run.py --arch sparc32 [--arch sparc64 ...|--arch all] [--qemu-dir DIR] [--label tcg]
             [--repeat 2] [--loops N] [--machine SS-20 ...] [--json results.jsonl] [--log-dir logs]
             [--shell]

Each run starts QEMU with -kernel out/<arch>/kernel on a serial console, reads the console with
timestamps, and stops at power-off (or at --timeout). One JSON object per run goes to stdout (and
to --json), a Markdown table to stderr at the end. Python standard library only.

Measured per run: the host's load average at the start, wall time from starting QEMU to the
kernel's first line, to PID 1's banner, to its result line and to QEMU's exit, PID 1's own
uptime and compute-loop time, and QEMU's peak RSS (from wait4). The loop's CRC is checked
against the value every architecture must produce for that loop count.

With --shell, the kernel gets wisp=shell and PID 1 starts its interactive shell instead: run.py
answers the prompts with a fixed script (help typed with a Backspace, info, bench, crc 64,
mandel, poweroff; shell.py) and checks the answers, including every row of the Mandelbrot set.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import zlib

import shell

HERE = os.path.dirname(os.path.abspath(__file__))

# What init.c prints without a loops= parameter.
DEFAULT_LOOPS = 4096

# arch -> QEMU binary, machine arguments, memory (MiB), console argument
ARCHES = {
    "x86_64": ("qemu-system-x86_64", ["-M", "pc"], 128, "console=ttyS0"),
    "i386": ("qemu-system-i386", ["-M", "pc"], 128, "console=ttyS0"),
    "sparc32": ("qemu-system-sparc", ["-M", "SS-5"], 128, "console=ttyS0"),
    "sparc64": ("qemu-system-sparc64", ["-M", "sun4u"], 256, "console=ttyS0"),
}

RESULT_PREFIX = "WISP-RESULT "
RESULT_INTS = ("v", "cpus", "mem_kb", "uptime_ms", "loops", "loop_ms")
RESULT_REQUIRED = ("v", "arch", "machine", "release", "cpus", "mem_kb", "uptime_ms", "loops",
                   "crc", "loop_ms", "status")

# Console markers, in boot order, and the name of the time they set.
MARKERS = (
    ("t_kernel", re.compile(r"Linux version ")),
    ("t_banner", re.compile(r"^WISP-BANNER ")),
    ("t_result", re.compile(r"^WISP-RESULT ")),
)


def parse_result(line):
    """Parse a WISP-RESULT line into a dict (numbers as int, crc as int). Raises ValueError."""
    line = line.strip()
    pos = line.find(RESULT_PREFIX)
    if pos < 0:
        raise ValueError("not a result line")
    fields = {}
    for item in line[pos + len(RESULT_PREFIX):].split():
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise ValueError(f"bad field: {item!r}")
        fields[key] = value
    missing = [k for k in RESULT_REQUIRED if k not in fields]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    out = dict(fields)
    for key in RESULT_INTS:
        try:
            out[key] = int(fields[key])
        except ValueError:
            raise ValueError(f"{key} is not a number: {fields[key]!r}") from None
    if not re.fullmatch(r"0x[0-9a-f]{8}", fields["crc"]):
        raise ValueError(f"bad crc: {fields['crc']!r}")
    out["crc"] = int(fields["crc"], 16)
    return out


def expected_crc(loops):
    """The CRC init.c's compute() must return: CRC-32 of the xorshift32 stream, little endian."""
    x = 2463534242
    crc = 0
    words = 4096
    for _ in range(loops):
        chunk = bytearray(words * 4)
        for i in range(words):
            x ^= (x << 13) & 0xFFFFFFFF
            x ^= x >> 17
            x ^= (x << 5) & 0xFFFFFFFF
            chunk[i * 4:i * 4 + 4] = x.to_bytes(4, "little")
        crc = zlib.crc32(chunk, crc)
    return crc


# Precomputed with expected_crc(), which takes a while in Python for large counts.
KNOWN_CRC = {64: 0x36C8A4F9, 1024: 0xB1C5DBCC, 4096: 0x35A46014}


def crc_for(loops, compute_limit=256):
    """Expected CRC for a loop count, or None if unknown and too slow to compute here."""
    if loops in KNOWN_CRC:
        return KNOWN_CRC[loops]
    if loops <= compute_limit:
        KNOWN_CRC[loops] = expected_crc(loops)
        return KNOWN_CRC[loops]
    return None


def qemu_command(arch, qemu_dir=None, kernel=None, machine=None, memory=None, loops=None,
                 firmware=None, extra=(), interactive=False):
    """The QEMU command line for one boot."""
    binary, machine_args, default_mem, console = ARCHES[arch]
    if qemu_dir:
        binary = os.path.join(qemu_dir, binary)
    if machine:
        machine_args = ["-M", machine]
    append = f"{console} panic=-1"
    if loops:
        append += f" loops={loops}"
    if interactive:
        append += " wisp=shell"
    cmd = [binary, *machine_args, "-m", str(memory or default_mem), "-display", "none",
           "-serial", "stdio", "-monitor", "none", "-no-reboot", "-nodefaults"]
    if firmware:
        cmd += ["-L", firmware]
    cmd += ["-kernel", kernel or os.path.join(HERE, "out", arch, "kernel"), "-append", append]
    cmd += list(extra)
    return cmd


def scan_console(lines):
    """Times of the markers in [(t, text), ...]: {name: t} plus 'result' (the parsed line)."""
    times = {}
    result = None
    poweroff_failed = False
    for t, text in lines:
        for name, pattern in MARKERS:
            if name not in times and pattern.search(text):
                times[name] = t
        if result is None and text.startswith(RESULT_PREFIX):
            try:
                result = parse_result(text)
            except ValueError as exc:
                times["result_error"] = str(exc)
        if text.startswith("WISP-POWEROFF-FAILED"):
            poweroff_failed = True
    return times, result, poweroff_failed


def boot(cmd, timeout, log_path=None):
    """Run QEMU, read its console with timestamps; return the raw run record."""
    load = os.getloadavg()
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True)
    lines = []

    def reader():
        for raw in proc.stdout:
            lines.append((time.monotonic() - t0, raw.decode("utf-8", "replace").rstrip("\r\n")))

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    timed_out = threading.Event()

    def kill():
        timed_out.set()
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    timer = threading.Timer(timeout, kill)
    timer.start()
    _, status, rusage = os.wait4(proc.pid, 0)
    t_exit = time.monotonic() - t0
    timer.cancel()
    proc.returncode = os.waitstatus_to_exitcode(status)
    thread.join(5)
    if log_path:
        with open(log_path, "w", encoding="utf-8") as fh:
            for t, text in lines:
                fh.write(f"{t:9.3f} {text}\n")
    return {
        "load1": round(load[0], 2), "load5": round(load[1], 2),
        "t_exit": t_exit, "exit_code": proc.returncode, "timed_out": timed_out.is_set(),
        "max_rss_kb": rusage.ru_maxrss, "user_s": round(rusage.ru_utime, 3),
        "sys_s": round(rusage.ru_stime, 3), "lines": lines,
    }


def evaluate(arch, raw, loops):
    """Turn a raw run record into the reported one; 'ok' only if everything checks out."""
    times, result, poweroff_failed = scan_console(raw["lines"])
    rec = {"arch": arch}
    for key in ("load1", "load5", "exit_code", "timed_out", "max_rss_kb", "user_s", "sys_s"):
        rec[key] = raw[key]
    for name in ("t_kernel", "t_banner", "t_result"):
        rec[name] = round(times[name], 3) if name in times else None
    rec["t_exit"] = round(raw["t_exit"], 3)
    problems = []
    if result is None:
        problems.append(times.get("result_error", "no result line"))
    else:
        for key in ("machine", "release", "cpus", "mem_kb", "uptime_ms", "loops", "loop_ms",
                    "status"):
            rec[key] = result[key]
        rec["crc"] = f"0x{result['crc']:08x}"
        if result["arch"] != arch:
            problems.append(f"arch {result['arch']} != {arch}")
        if result["status"] != "ok":
            problems.append(f"status {result['status']}")
        if result["loops"] != (loops or DEFAULT_LOOPS):
            problems.append(f"loops {result['loops']} != {loops or DEFAULT_LOOPS}")
        want = crc_for(result["loops"])
        if want is None:
            rec["crc_checked"] = False
        else:
            rec["crc_checked"] = True
            if result["crc"] != want:
                problems.append(f"crc 0x{result['crc']:08x} != 0x{want:08x}")
    if poweroff_failed:
        problems.append("power-off failed")
    if raw["timed_out"]:
        problems.append("timed out")
    elif raw["exit_code"] != 0:
        problems.append(f"QEMU exit code {raw['exit_code']}")
    rec["ok"] = not problems
    rec["problems"] = problems
    return rec


def evaluate_shell(arch, raw, loops, script=shell.SCRIPT):
    """The reported record of a --shell run; 'ok' only if every answer checks out."""
    answers = shell.split_transcript(raw["text"])
    problems, numbers = shell.check_answers(arch, script, answers, crc_for,
                                            loops or DEFAULT_LOOPS)
    rec = {"arch": arch, "mode": "shell"}
    for key in ("load1", "load5", "exit_code", "timed_out", "max_rss_kb", "user_s", "sys_s",
                "t_prompt", "prompt_s"):
        rec[key] = raw[key]
    rec["t_exit"] = round(raw["t_exit"], 3)
    rec.update(numbers)
    if "WISP-POWEROFF-FAILED" in raw["text"]:
        problems.append("power-off failed")
    if raw["timed_out"]:
        problems.append("timed out")
    elif raw["exit_code"] != 0:
        problems.append(f"QEMU exit code {raw['exit_code']}")
    rec["ok"] = not problems
    rec["problems"] = problems
    return rec


def shell_table(records):
    """Markdown table of --shell runs."""
    head = ("| arch | machine | label | load1 | to prompt s | bench ms | mandel ms | to exit s "
            "| peak RSS MiB | ok |")
    rows = [head, "|" + " --- |" * 10]
    for r in records:
        def f(v, fmt="{:.2f}"):
            return "-" if v is None else fmt.format(v)
        rows.append(f"| {r['arch']} | {machine_of(r)} | {r.get('label', '')} "
                    f"| {f(r['load1'])} | {f(r['t_prompt'])} | {f(r.get('bench_ms'), '{}')} "
                    f"| {f(r.get('mandel_ms'), '{}')} | {f(r['t_exit'])} "
                    f"| {f(r['max_rss_kb'] / 1024, '{:.0f}')} | {'yes' if r['ok'] else 'NO'} |")
    return "\n".join(rows)


def machine_of(rec):
    """The -M of a record: the --machine it ran with, or its architecture's default."""
    return rec.get("machine_arg") or ARCHES[rec["arch"]][1][1]


def table(records):
    """Markdown table of the runs."""
    head = ("| arch | machine | label | load1 | to kernel s | to PID 1 s | to result s | to exit s "
            "| PID 1 uptime ms | loop ms | peak RSS MiB | ok |")
    rows = [head, "|" + " --- |" * 12]
    for r in records:
        def f(v, fmt="{:.2f}"):
            return "-" if v is None else fmt.format(v)
        rows.append(f"| {r['arch']} | {machine_of(r)} | {r.get('label', '')} | {f(r['load1'])} "
                    f"| {f(r['t_kernel'])} "
                    f"| {f(r['t_banner'])} | {f(r['t_result'])} | {f(r['t_exit'])} "
                    f"| {f(r.get('uptime_ms'), '{}')} | {f(r.get('loop_ms'), '{}')} "
                    f"| {f(r['max_rss_kb'] / 1024, '{:.0f}')} | {'yes' if r['ok'] else 'NO'} |")
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arch", action="append", choices=[*ARCHES, "all"], required=True)
    ap.add_argument("--qemu-dir", help="directory with the qemu-system-* binaries (default: PATH)")
    ap.add_argument("--label", default="", help="free text recorded with each run, e.g. tcg or tci")
    ap.add_argument("--machine", action="append",
                    help="override -M (e.g. SS-20 for sparc32); repeat it to boot each in turn")
    ap.add_argument("--memory", type=int, help="override -m (MiB)")
    ap.add_argument("--loops", type=int, help=f"compute loops (init's default: {DEFAULT_LOOPS})")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--firmware", default=os.environ.get("WISP_FIRMWARE"),
                    help="QEMU -L directory (default: $WISP_FIRMWARE)")
    ap.add_argument("--out", default=os.path.join(HERE, "out"), help="build output directory")
    ap.add_argument("--json", help="append one JSON object per run to this file")
    ap.add_argument("--log-dir", help="write each run's timestamped console log here")
    ap.add_argument("--shell", action="store_true",
                    help="boot with wisp=shell and drive the interactive shell (shell.py)")
    args = ap.parse_args(argv)

    arches = list(ARCHES) if "all" in args.arch else args.arch
    records = []
    runs = [(arch, machine) for arch in arches for machine in (args.machine or [None])]
    for arch, machine in runs:
        kernel = os.path.join(args.out, arch, "kernel")
        cmd = qemu_command(arch, args.qemu_dir, kernel, machine, args.memory, args.loops,
                           args.firmware, interactive=args.shell)
        for n in range(1, args.repeat + 1):
            log_path = None
            if args.log_dir:
                os.makedirs(args.log_dir, exist_ok=True)
                tag = "-".join(x for x in (arch, args.label, machine,
                                           "shell" if args.shell else "", str(n)) if x)
                log_path = os.path.join(args.log_dir, f"{tag}.log")
            if args.shell:
                raw = shell.drive(cmd, shell.SCRIPT, args.timeout)
                if log_path:
                    with open(log_path, "w", encoding="utf-8") as fh:
                        fh.write(raw["text"])
                rec = evaluate_shell(arch, raw, args.loops)
            else:
                raw = boot(cmd, args.timeout, log_path)
                rec = evaluate(arch, raw, args.loops)
            rec.update(label=args.label, run=n, machine_arg=machine, qemu=cmd[0])
            records.append(rec)
            line = json.dumps(rec, sort_keys=True)
            print(line, flush=True)
            if args.json:
                with open(args.json, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
    print((shell_table if args.shell else table)(records), file=sys.stderr)
    return 0 if all(r["ok"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
