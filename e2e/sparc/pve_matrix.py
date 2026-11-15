#!/usr/bin/env python3
"""Create VMs through the PVE API, let PVE start them and drive them with the lab in attach mode
(`lab.py run --pve <vmid>`): what Proxmox VE itself runs, provisioned and booted by the scenarios.

    pve_matrix.py pve --runs /work/runs/p1 [--iso /mnt/sparc/iso] [--disks /srv/sparc/disks]

Runs on the PVE node: the e2e node with the lab in it (pve.Dockerfile). Each case creates its VM
(`pvesh create /nodes/<node>/qemu`, the install media linked into the `local` storage, a disk template
imported with `import-from`), runs its scenarios one after another against it, each in
<runs>/<case>/<n>-<scenario>/, and destroys the VM. Prints the summary as a Markdown table (also in
<runs>/summary.md) and exits 1 if any case failed.
"""
import argparse
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ISO_DIR = "/var/lib/vz/template/iso"  # the `local` storage's ISO directory

# name -> [(case, VM config (`{iso}`: the CD's volume, `{template}`: the imported disk template),
#           install CD in --iso, disk template in --disks or None, [(scenario, variables)])]
SPARC32 = {"arch": "sparc", "memory": 256, "ostype": "solaris", "net0": "lance,bridge=vmbr0",
           "serial0": "socket", "vga": "serial0"}
MATRICES = {
    "pve": [
        # The supported sparc32 profile (SS-5, OpenBIOS) with the text installer on ttya: a blank
        # Sun-labelled disk on target 3 (the installer lists only labelled disks), the CD on target 6.
        ("sol26-install-ss5", {**SPARC32, "scsi3": "local:0,import-from={template},format=raw",
                               "scsi6": "{iso},media=cdrom"},
         "solaris_2.6_598_sparc.iso", "sparc-SUN2.9G.raw.template.xz",
         [("solaris-install-serial.py", {}), ("solaris-boot-disk.py", {})]),
        # aarch64: virt, AAVMF (bios ovmf + efidisk0), everything on the PL011 (vga serial0)
        ("alpine-aarch64", {"arch": "aarch64", "machine": "virt", "bios": "ovmf", "efidisk0": "local:0,format=raw",
                            "memory": 1024, "cores": 2, "ostype": "l26", "serial0": "socket", "vga": "serial0",
                            "scsihw": "virtio-scsi-pci", "scsi2": "{iso},media=cdrom"},
         "other-os/alpine/alpine-standard-3.19.0-aarch64.iso", None, [("alpine-boot-cd.py", {})]),
        # sparc64: sun4u, OpenBIOS; the CD on the built-in IDE (OpenBIOS can't drive the lsi SCSI)
        ("netbsd-sparc64", {"arch": "sparc64", "memory": 512, "ostype": "other", "serial0": "socket",
                            "vga": "serial0", "ide2": "{iso},media=cdrom"},
         "other-os/NetBSD-11.1-sparc64.iso", None, [("netbsd-boot-cd.py", {})]),
        # x86_64 baseline under TCG: the console on VGA (OCR + send-key), a serial port next to it
        ("alpine-x86_64", {"kvm": 0, "memory": 1024, "ostype": "l26", "serial0": "socket", "vga": "std",
                           "ide2": "{iso},media=cdrom"},
         "other-os/alpine/alpine-standard-3.19.0-x86_64.iso", None, [("alpine-boot-cd.py", {})]),
    ],
}

LEFTOVERS = ("_fb_poll.png", "_refresh.ppm", "*.sock")


def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def create_vm(name, config, iso, template, a, work):
    """The VM through the API; returns its VMID."""
    node = socket.gethostname()
    vmid = sh("pvesh", "get", "/cluster/nextid", "--output-format", "json").strip('"')
    os.makedirs(ISO_DIR, exist_ok=True)
    link = os.path.join(ISO_DIR, os.path.basename(iso))
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(os.path.join(a.iso, iso), link)
    raw = None
    if template:
        raw = os.path.join(work, "template.raw")
        shutil.copy(os.path.join(a.disks, template), raw + ".xz")
        subprocess.run(["xz", "-d", "-f", raw + ".xz"], check=True)
    params = {"vmid": vmid, "name": name.replace("_", "-"), **config}  # a DNS name
    args = []
    for k, val in params.items():
        args += [f"--{k}", str(val).format(iso=f"local:iso/{os.path.basename(iso)}", template=raw)]
    try:
        sh("pvesh", "create", f"/nodes/{node}/qemu", *args)
    finally:
        if raw and os.path.exists(raw):
            os.unlink(raw)
    with open(os.path.join(work, "vm.conf"), "w", encoding="utf-8") as f:
        f.write(sh("qm", "config", vmid) + "\n")
    return vmid


def destroy_vm(vmid):
    subprocess.run(["qm", "stop", vmid], capture_output=True)
    subprocess.run(["qm", "destroy", vmid, "--purge", "--destroy-unreferenced-disks", "1"], capture_output=True)


def run_case(name, config, iso, template, steps, a):
    work = os.path.join(a.runs, name)
    os.makedirs(work, exist_ok=True)
    t0, vmid, results = time.time(), None, []
    try:
        vmid = create_vm(name, config, iso, template, a, work)
        print(f"=== {name}: VM {vmid}", flush=True)
        for n, (scenario, variables) in enumerate(steps, 1):
            out = os.path.join(work, f"{n}-{scenario[:-3]}")
            cmd = [sys.executable, os.path.join(HERE, "lab.py"), "run", os.path.join(HERE, "scenarios", scenario),
                   "--pve", vmid, "--out", out, *[x for k, val in variables.items() for x in ("--var", f"{k}={val}")]]
            print(f"=== {name}: {' '.join(cmd)}", flush=True)
            try:
                os.makedirs(out, exist_ok=True)
                with open(os.path.join(out, "lab.log"), "w", encoding="utf-8") as log:
                    subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
                res = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
            except subprocess.TimeoutExpired:
                res = {"code": 1, "status": f"timed out after {a.timeout}s"}
            except (OSError, ValueError) as e:
                res = {"code": 3, "status": f"no result.json ({e})"}
            res["scenario"] = scenario
            results.append(res)
            print(f"=== {name}: {scenario}: {res['status'].splitlines()[0]} ({res.get('elapsed', '?')}s)", flush=True)
            if res["code"]:
                break
    except subprocess.CalledProcessError as e:
        results.append({"code": 3, "scenario": "-", "status": f"{' '.join(e.cmd[:3])}: {e.stderr.strip()}"})
    finally:
        if vmid:
            destroy_vm(vmid)
        for pattern in LEFTOVERS:
            for p in glob.glob(os.path.join(work, "**", pattern), recursive=True):
                os.unlink(p)
    failed = next((r for r in results if r["code"]), None)
    return {"code": failed["code"] if failed else 0, "elapsed": round(time.time() - t0, 1),
            "steps": results, "status": failed["status"] if failed else "passed"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("matrix", choices=sorted(MATRICES))
    p.add_argument("--runs", required=True, help="output directory, one subdirectory per case")
    p.add_argument("--disks", default="/srv/sparc/disks", help="disk templates (read only)")
    p.add_argument("--iso", default="/mnt/sparc/iso", help="install CDs (read only)")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per scenario")
    p.add_argument("--only", action="append", help="run only these cases")
    a = p.parse_args()

    rows, failed = [], 0
    cases = [c for c in MATRICES[a.matrix] if not a.only or c[0] in a.only]
    for name, config, iso, template, steps in cases:
        res = run_case(name, config, iso, template, steps, a)
        failed += res["code"] != 0
        done = ", ".join(f"`{r['scenario']}` {r.get('elapsed', '?')}s" for r in res["steps"])
        status = res["status"].splitlines()[0][:120].replace("|", "\\|")
        rows.append(f"| {name} | {done} | {'pass' if res['code'] == 0 else 'FAIL'} | {res['elapsed']:.0f}s | {status} |")
    table = "\n".join([f"### sparc lab: {a.matrix} ({len(rows) - failed}/{len(rows)} passed)", "",
                       "| Case | Scenarios | Result | Time | Status |",
                       "| --- | --- | --- | --- | --- |", *rows])
    print("\n" + table)
    with open(os.path.join(a.runs, "summary.md"), "w", encoding="utf-8") as f:
        f.write(table + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
