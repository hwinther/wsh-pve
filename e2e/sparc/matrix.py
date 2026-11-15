#!/usr/bin/env python3
"""Run a fixed list of lab cases (scenario + variables) one after another and summarise them.

    matrix.py smoke --runs /mnt/sparc/runs/m1 [--disks /srv/sparc/disks] [--iso /mnt/sparc/iso]

Each case runs `lab.py run` in <runs>/<case>/. A case that boots an installed disk gets a sparse copy
of it there (the image in --disks is never booted), deleted again when the case is done, so <runs>
ends up with only the evidence: result.json, index.html, steps.log, screenshots. Prints the summary
as a Markdown table (also written to <runs>/summary.md) and exits 1 if any case failed.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# name -> [(case, scenario, installed disk or None, install CD or None, variables)]
# The installed disks (End User installs by solaris-install-serial.py on SS-5) and the CD.
SOL26, SOL251 = "sol26-enduser-installed.raw", "sol251-enduser-installed.raw"
SOL26PMC = "sol26-enduser-pmc-installed.raw"  # SOL26 + the pmc driver (README: "Idle")
SUNOS414 = "sunos414-installed.raw"  # Quick Install, Programmer set (README: "SunOS 4.1.4")
SUNOS = {"PROMPT": "login:", "BUSY": "dd if=/dev/zero of=/dev/null count=20000"}
NETBSD111 = "netbsd111-installed.raw"  # sysinst Minimal installation (README: "Idle")
# The same End User install on SS-10 and SS-20 (each machine needs its own install), the last one with
# the Sun SS-20 PROM. That PROM only runs with -cpu TI-SuperSparc-40/50/60 (submodules/SPARC.md).
SOL26SS10, SOL26SS20 = "sol26-enduser-ss10-installed.raw", "sol26-enduser-ss20-installed.raw"
SOL26SS20PROM = "sol26-enduser-ss20prom-installed.raw"
SS20PROM = {"MACHINE": "SS-20", "BIOS": "ss20_v2.25_rom", "CPU": "TI-SuperSparc-50"}
CD26, CD251 = "solaris_2.6_598_sparc.iso", "solaris_2.5.1_1197.iso"
MATRICES = {
    "smoke": [
        ("sol26-disk-openbios-ss5", "solaris-boot-disk.py", SOL26, None, {}),
        ("sol251-disk-ss5bin-ss5", "solaris-boot-disk.py", SOL251, None, {"BIOS": "ss5.bin"}),
        ("sol26-cd-openbios-ss5", "solaris-boot-cd.py", None, CD26, {}),
    ],
    # SS-10/SS-20: the install CDs, and the disks installed on these machines (an SS-5 disk doesn't
    # boot there: Solaris finds neither c0t3d0s6 nor le0, can't mount /usr and halts). 512 MB is the
    # most Solaris 2.6 boots with. The CD reaches the installer with 2 and 4 CPUs, but an installed
    # 2.6 with more than one CPU hangs (submodules/SPARC.md, "SS-10 and SS-20"), so no SMP disk case.
    # The 2.6 CD on SS-20 with one CPU and 256 MB sometimes stops in its idle loop after "Configuring
    # devices..." (about 1 boot in 6, OpenBIOS and Sun PROM alike).
    "machines": [
        ("sol26-cd-openbios-ss10", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-10"}),
        ("sol26-cd-openbios-ss10-512m", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-10", "MEM": "512"}),
        ("sol26-cd-openbios-ss20", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20"}),
        ("sol26-cd-openbios-ss20-512m", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20", "MEM": "512"}),
        ("sol26-cd-openbios-ss20-smp2", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20", "SMP": "2"}),
        ("sol26-cd-openbios-ss20-smp4", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20", "SMP": "4"}),
        ("sol26-cd-ss20prom-ss20-512m", "solaris-boot-cd.py", None, CD26, {**SS20PROM, "MEM": "512"}),
        ("sol251-cd-openbios-ss20", "solaris-boot-cd.py", None, CD251, {"MACHINE": "SS-20", "CDROM_AS": "hd"}),
        ("sol251-cd-ss20prom-ss20", "solaris-boot-cd.py", None, CD251, {**SS20PROM, "CDROM_AS": "hd"}),
        ("sol26-disk-openbios-ss10", "solaris-boot-disk.py", SOL26SS10, None, {"MACHINE": "SS-10"}),
        ("sol26-disk-openbios-ss20", "solaris-boot-disk.py", SOL26SS20, None, {"MACHINE": "SS-20"}),
        ("sol26-disk-openbios-ss20-512m", "solaris-boot-disk.py", SOL26SS20, None, {"MACHINE": "SS-20", "MEM": "512"}),
        ("sol26-disk-ss20prom-ss20", "solaris-boot-disk.py", SOL26SS20PROM, None, SS20PROM),
    ],
    # bench.py: the same jobs on SS-5 and SS-20 (one CPU); the numbers go to result.json. Only
    # meaningful on an otherwise idle host. The disks are fresh installs, so boot_s includes the
    # first-boot questions.
    "bench": [
        ("bench-sol26-openbios-ss5", "bench.py", SOL26, None, {}),
        ("bench-sol26-openbios-ss20", "bench.py", SOL26SS20, None, {"MACHINE": "SS-20"}),
        ("bench-sol26-ss20prom-ss20", "bench.py", SOL26SS20PROM, None, SS20PROM),
    ],
    # cg3 sizes (needs a package with the cg3 patches): OpenBIOS banner and the 2.6 disk to its login
    # prompt with the console on the framebuffer, each screenshot checked for the size; the Sun PROM
    # stays at 1024x768.
    "display": [
        ("cg3-ss5bin-1024x768", "cg3-display.py", None, None, {"BIOS": "ss5.bin"}),
        *[(f"sol26-disk-openbios-cg3-{res}", "cg3-display.py", SOL26, None, {"RES": res})
          for res in ("1024x768", "1152x900", "1280x1024", "1600x1200", "1920x1080")],
    ],
    # Host CPU use of an idle guest (needs a package with the idle patches, submodules/SPARC.md):
    # Solaris 2.6 with the pmc driver idles through the APC, without it the CPU spins.
    "idle": [
        ("sol26-pmc-idle-ss5", "idle.py", SOL26PMC, None,
         {"CHECK": "modinfo | grep pmc", "CHECK_EXPECT": r"pmc \(Power Management", "CPU_BELOW": "10"}),
        ("sol26-nopmc-spins-ss5", "idle.py", SOL26, None, {"CPU_ABOVE": "80"}),
        # SunOS 4.1.4: halted in its idle loop by the sunos-idle machine option (on by default). Its dd
        # takes ~5 ms a block, so a tenth of the count.
        ("sunos414-idle-ss5", "idle.py", SUNOS414, None,
         {**SUNOS, "TRACE": "sparc_sunos_idle_match", "TRACE_EXPECT": "SunOS idle loop", "CPU_BELOW": "10"}),
        ("sunos414-noidle-spins-ss5", "idle.py", SUNOS414, None,
         {**SUNOS, "MACHINE": "SS-5,sunos-idle=off", "CPU_ABOVE": "80"}),
        # NetBSD 11.1's apc driver writes register 0 only, as before the APC got its 16 bytes
        ("netbsd111-idle-ss5", "idle.py", NETBSD111, None,
         {"PROMPT": "login:", "CHECK": "dmesg | grep apc", "CHECK_EXPECT": "apc0 at", "CPU_BELOW": "10"}),
    ],
}

# Left behind by a run but not evidence: the guest disk, QEMU's sockets, the display refresh buffer.
LEFTOVERS = ("disk.raw", "*.sock", "_refresh.ppm", "_fb_poll.png")


def run_case(name, scenario, disk, iso, variables, a):
    out = os.path.join(a.runs, name)
    os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, os.path.join(HERE, "lab.py"), "run", os.path.join(HERE, "scenarios", scenario),
           "--out", out]
    if disk:
        copy = os.path.join(out, "disk.raw")
        subprocess.run(["cp", "--sparse=always", os.path.join(a.disks, disk), copy], check=True)
        cmd += ["--var", f"DISK={copy}"]
    if iso:
        cmd += ["--var", f"ISO={os.path.join(a.iso, iso)}"]
    cmd += [x for k, val in variables.items() for x in ("--var", f"{k}={val}")]
    print(f"=== {name}: {' '.join(cmd)}", flush=True)
    t0, code = time.time(), 3
    try:
        with open(os.path.join(out, "lab.log"), "w", encoding="utf-8") as log:
            code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout).returncode
        res = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    except subprocess.TimeoutExpired:
        res = {"code": 1, "status": f"case timed out after {a.timeout}s"}
    except (OSError, ValueError) as e:
        res = {"code": code or 3, "status": f"no result.json ({e})"}
    finally:
        for pattern in LEFTOVERS:
            for p in glob.glob(os.path.join(out, pattern)):
                os.unlink(p)
    res.setdefault("elapsed", round(time.time() - t0, 1))
    print(f"=== {name}: {res['status'].splitlines()[0]} ({res['elapsed']}s)", flush=True)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("matrix", choices=sorted(MATRICES))
    p.add_argument("--runs", required=True, help="output directory, one subdirectory per case")
    p.add_argument("--disks", default="/srv/sparc/disks", help="installed disk images (read only)")
    p.add_argument("--iso", default="/mnt/sparc/iso", help="install CDs (read only)")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per case")
    a = p.parse_args()

    rows, failed = [], 0
    for name, scenario, disk, iso, variables in MATRICES[a.matrix]:
        res = run_case(name, scenario, disk, iso, variables, a)
        failed += res["code"] != 0
        vs = " ".join(f"{k}={v}" for k, v in variables.items()).replace("|", "\\|")
        status = res["status"].splitlines()[0][:120].replace("|", "\\|")
        if res.get("metrics"):
            status += " (" + ", ".join(f"{k} {val}" for k, val in res["metrics"].items()) + ")"
        rows.append(f"| {name} | {f'`{scenario}` {vs}'.strip()} | {'pass' if res['code'] == 0 else 'FAIL'} | "
                    f"{res['elapsed']:.0f}s | {status} |")
    table = "\n".join([f"### sparc lab: {a.matrix} ({len(rows) - failed}/{len(rows)} passed)", "",
                       "| Case | Scenario | Result | Time | Status |",
                       "| --- | --- | --- | --- | --- |", *rows])
    print("\n" + table)
    with open(os.path.join(a.runs, "summary.md"), "w", encoding="utf-8") as f:
        f.write(table + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
