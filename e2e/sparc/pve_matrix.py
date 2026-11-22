#!/usr/bin/env python3
"""Create VMs through the PVE API, let PVE start them and drive them with the lab in attach mode
(`lab.py run --pve <vmid>`): what Proxmox VE itself runs, provisioned and booted by the scenarios.

    pve_matrix.py pve --runs /work/runs/p1 [--iso /mnt/os/iso] [--disks /mnt/os/disks]
        [--bench /mnt/os/disks/bench-sol26.raw]

    pve_matrix.py install --runs /work/runs/i1 [--reinstall [all|TARGET[,TARGET]]]
        # every automated install target (targets.py): installed once, then boot-tested

The install matrix keeps one installed disk per target in --disks (install-<target>.raw with
install-<target>.json, lab.py install --export) and per target either
  - installs it (`lab.py install <target> --check --export <disks>`) when its stored disk is missing or
    --reinstall names it (`--reinstall` alone or `all`: every target without `matrix_skip`); the new
    disk replaces the old one only when the install passed its check, or
  - boot-tests the stored disk (`lab.py boot-test`): a VM with the target's profile from a copy of it,
    booted through PVE, the target's check (login, marker, state), the VM destroyed, or
  - skips it: a target with `matrix_skip` (too slow for the sparc lab job, or it needs more than the
    published packages) is installed only when --reinstall names it, and boot-tested once its disk exists;
    a target with `matrix_needs: apt_cache` (Debian's netinst) is installed only with --apt-cache.
A file under the stored disk's name that lab.py install didn't write fails the case (it is never replaced).

--apt-cache HOST:PORT (or WSH_LAB_APT_CACHE): an apt cache (apt-cacher-ng) the node reaches. The guests
get it and nothing else: the node's vmbr0 gets APT_PINHOLE_IP/24, a socat service forwards
APT_PINHOLE_IP:3142 to the cache, IP forwarding is off, and the targets that fetch packages are
installed with `--apt-proxy http://APT_PINHOLE_IP:3142` and no router or name server (the proxy is
handed whole URLs and resolves the archive's name itself). The cache's address isn't printed. When
the pinhole gets no answer from the cache, those installs fail and the other cases run.

Runs on the PVE node: the e2e node with the lab in it (pve.Dockerfile). Each case creates its VM
(`pvesh create /nodes/<node>/qemu`, the install media linked into the `local` storage, a disk template
or an installed disk imported with `import-from`, the bench disk too where a case uses it), runs its scenarios one after another against it, each in
<runs>/<case>/<n>-<scenario>/, and destroys the VM. Prints the summary as a Markdown table (also in
<runs>/summary.md) and exits 1 if any case failed.
"""
import argparse
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import install
import targets

HERE = os.path.dirname(os.path.abspath(__file__))
# The guests' side of the apt cache pinhole (--apt-cache): an address on the node's vmbr0 in the
# targets' default network (10.0.2.15/24), and the port socat forwards to the cache
APT_PINHOLE_IP, APT_PINHOLE_PORT, APT_PINHOLE_UNIT = "10.0.2.2", 3142, "wsh-lab-apt-cache"
APT_PINHOLE_PROXY = f"http://{APT_PINHOLE_IP}:{APT_PINHOLE_PORT}"
ISO_DIR = "/var/lib/vz/template/iso"  # the `local` storage's ISO directory
# {"install": <target>} as a case's VM config: `lab.py install <target> --check` creates and installs
# the VM (the target's media linked into the `local` storage under their expected names) instead of
# create_vm(); the case's scenarios then run against the installed VM.

# name -> [(case, VM config (`{iso}`: the CD's volume, `{template}`: the imported disk template or
#           installed disk, `{bench}`: the bench disk, --bench), install CD in --iso or None, disk in
#           --disks (`.xz`: decompressed first) or None, [(scenario, variables)])]
SPARC32 = {"arch": "sparc", "memory": 256, "ostype": "solaris", "net0": "lance,bridge=vmbr0",
           "serial0": "socket", "vga": "serial0"}
MATRICES = {
    "pve": [
        # The install target sol26-ss5 (targets.py), as a user runs it: `lab.py install sol26-ss5
        # --check` creates the VM (SS-5, OpenBIOS, ttya, a Sun-labelled disk, the 2.6 CD), installs,
        # sets the root password and the marker, ejects the CD, then boots and checks the login and
        # /etc/wsh-lab-target.
        ("sol26-install-ss5", {"install": "sol26-ss5"}, None, None, []),
        # aarch64: virt, AAVMF (bios ovmf + efidisk0), everything on the PL011 (vga serial0)
        ("alpine-aarch64", {"arch": "aarch64", "machine": "virt", "bios": "ovmf", "efidisk0": "local:0,format=raw",
                            "memory": 1024, "cores": 2, "ostype": "l26", "serial0": "socket", "vga": "serial0",
                            "scsihw": "virtio-scsi-pci", "scsi2": "{iso},media=cdrom"},
         "other-os/alpine/alpine-standard-3.19.0-aarch64.iso", None, [("alpine-boot-cd.py", {})]),
        # sparc64: the profile as the create wizard makes it (a blank disk on ide0, the CD on ide2,
        # sunhme, 512 MB, no boot order: the API puts the CD first), the console on ttya. OpenBIOS
        # must boot the CD by itself (`-boot order=d`): BOOT= types nothing at its prompt.
        ("netbsd-sparc64", {"arch": "sparc64", "memory": 512, "ostype": "other", "serial0": "socket",
                            "vga": "serial0", "net0": "sunhme,bridge=vmbr0", "ide0": "local:1,format=raw",
                            "ide2": "{iso},media=cdrom"},
         "other-os/NetBSD-11.1-sparc64.iso", None, [("netbsd-boot-cd.py", {"BOOT": ""})]),
        # sparc32 with more than one CPU (needs qemu-server with the CPU limits per profile and
        # pve-qemu-kvm 11.1.3-2+wsh10 or later, patch 0019): SS-20 with OpenBIOS and 2 CPUs, the
        # installed Solaris 2.6 SS-20 disk on target 3 and the bench disk read only on target 4.
        # smp-soak.py without the soak: psrinfo must list 2 CPUs on-line, then Dhrystone and the nawk
        # loop alone and as 2 copies at once.
        ("sol26-ss20-smp2", {**SPARC32, "machine": "SS-20", "memory": 512, "cores": 2,
                             "scsi3": "local:0,import-from={template},format=raw",
                             "scsi4": "local:0,import-from={bench},format=raw,ro=1"},
         None, "sol26-enduser-ss20-installed.raw", [("smp-soak.py", {"SMP": "2", "SOAK": "0"})]),
        # The Sun SS-20 PROM with an NVRAM volume (qemu-server nvram0, pve-qemu wsh/0059), 512 MB, the
        # stored Solaris 2.6 SS-20 PROM disk (its first boot still pending: a reconfiguration boot and
        # the root password screen) imported to target 3. sun-prom-nvram.py: `setenv diag-switch?
        # false` once at ok, then the first boot; after `qm stop`/`qm start` the PROM must boot the disk
        # by itself (wsh/0061: the lance DMA), then `reboot -- -r` (wsh/0066: dbri) to login again.
        ("sol26-ss20prom-nvram", {**SPARC32, "machine": "SS-20", "bios": "ss20_v2.25_rom", "memory": 512,
                                  "nvram0": "local:1", "scsi3": "local:0,import-from={template},format=raw"},
         None, "sol26-enduser-ss20prom-installed.raw", [("sun-prom-nvram.py", {})]),
        # x86_64 baseline under TCG: the console on VGA (OCR + send-key), a serial port next to it
        ("alpine-x86_64", {"kvm": 0, "memory": 1024, "ostype": "l26", "serial0": "socket", "vga": "std",
                           "ide2": "{iso},media=cdrom"},
         "other-os/alpine/alpine-standard-3.19.0-x86_64.iso", None, [("alpine-boot-cd.py", {})]),
    ],
    # Solaris 10 on sun4u through PVE (not in the weekly run): the sparc64 profile as the wizard makes
    # it, 1024 MB, the console on ttya. NEEDS THE SUN DVD (sol-10-u11-ga-sparc-dvd.iso in --iso; not
    # in the repository) and a pve-qemu-kvm with the patched openbios-sparc64 and wsh/0021, the same
    # checks as matrix.py's solaris10 case.
    "solaris10": [
        ("sol10-sparc64", {"arch": "sparc64", "memory": 1024, "ostype": "solaris", "serial0": "socket",
                           "vga": "serial0", "net0": "sunhme,bridge=vmbr0", "ide0": "local:8,format=raw",
                           "ide2": "{iso},media=cdrom"},
         "sol-10-u11-ga-sparc-dvd.iso", None, [("sparc64-boot-cd.py", {"GUEST": "solaris10"})]),
    ],
    # Every automated install target (targets.py): installed with --check and its disk stored when it
    # has none (or --reinstall), else that disk boot-tested; plan() decides. The "scheduled
    # reinstalls" of ROADMAP.md.
    "install": [(f"install-{t}", {"target": t}, None, None, []) for t in targets.automated()],
    # Recordings for the docs gallery that no install target makes (publish_media.py; not in the
    # weekly run): the stored Solaris 2.6 SS-20 disk (install-sol26-ss20.raw, lab.py install
    # --export) on SS-20 with OpenBIOS and 4 CPUs, booted to login; psrinfo and mpstat show the four
    # CPUs on-line and idle, then init 5. Solaris 2.2 on SS-10 with OpenBIOS (needs pve-qemu-kvm
    # 11.1.3-2+wsh22 or later: openbios 0019-0023), until it has an install target: the CD image (a
    # disk image, as a disk on target 6: cd_as_disk=1) installed onto a Sun-labelled disk on the 2.3
    # path of solaris-install-serial.py, then the first boot (root password) and login.
    "recordings": [
        ("sol22-install-ss10", {**SPARC32, "machine": "SS-10", "memory": 256,
                                "scsi3": "local:0,import-from={template},format=raw",
                                "scsi6": "{iso},media=cdrom,cd_as_disk=1"},
         "sun_solaris/Solaris/2.2/SPARC/Solaris_2.2.img", "sparc-SUN2.9G.raw.template.xz",
         [("solaris-install-serial.py", {}),
          ("solaris-boot-disk.py", {"ROOT_PASSWORD": targets.DEFAULT_ROOT_PASSWORD, "CHECK": r"SunOS \S+ 5\.2"})]),
        ("sol26-ss20-smp4", {**SPARC32, "machine": "SS-20", "memory": 512, "cores": 4,
                             "scsi3": "local:0,import-from={template},format=raw"},
         None, "install-sol26-ss20.raw",
         [("solaris-boot-disk.py", {"ROOT_PASSWORD": targets.DEFAULT_ROOT_PASSWORD, "COMMANDS": "uname -a; psrinfo",
                                    "CHECK": r"3\s+on-line", "MORE_COMMANDS": "mpstat 1 3",
                                    "MORE_EXPECT": r"3\s+\d+(\s+\d+){14}"})]),
    ],
}


def reinstall_set(values):
    """--reinstall's values (each `all` or targets, comma or space separated) as a set; SystemExit for
    an unknown or non-automated target."""
    out = set()
    for v in values or []:
        out |= set(filter(None, v.replace(",", " ").split()))
    bad = sorted(out - {"all"} - set(targets.automated()))
    if bad:
        raise SystemExit(f"--reinstall: not automated install targets: {', '.join(bad)} (`lab.py targets` lists them)")
    return out


# (the summary shows 160 characters of a status)
NO_APT_CACHE = "needs an apt cache for archive.debian.org (WSH_LAB_APT_CACHE or --apt-cache HOST:PORT)"


def plan(target, disks, reinstall=frozenset(), apt_cache=None):
    """What the install matrix does with a target: ("install" | "boot-test" | "skip" | "refuse", why)."""
    t = targets.TARGETS[target]
    try:
        meta = install.read_sidecar(disks, target)
    except install.InstallFailed as e:
        return "refuse", str(e)
    no_cache = t.get("matrix_needs") == "apt_cache" and not apt_cache
    if target in reinstall:
        if no_cache:
            return "skip", f"--reinstall {target}: {NO_APT_CACHE}"
        return "install", f"--reinstall {target}"
    if meta and "all" in reinstall and not t.get("matrix_skip") and not no_cache:
        return "install", "--reinstall all"
    if meta:
        return "boot-test", f"stored disk installed {meta.get('installed')} with {meta.get('packages')}"
    if t.get("matrix_skip"):
        return "skip", f"no stored disk; installed only on request (--reinstall {target}): {t['matrix_skip']}"
    if no_cache:
        return "skip", f"no stored disk; {NO_APT_CACHE}"
    return "install", "no stored disk"


def apt_cache_choice(value):
    """--apt-cache / WSH_LAB_APT_CACHE: HOST:PORT (a host name or IPv4 address; an http:// in front
    and a / after are dropped), None when empty; SystemExit otherwise. The value is never echoed."""
    value = (value or "").strip()
    if not value:
        return None
    m = re.fullmatch(r"(?:http://)?([A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?):([0-9]{1,5})/?", value)
    if not m or not 0 < int(m[2]) < 65536:
        raise SystemExit("--apt-cache / WSH_LAB_APT_CACHE: not HOST:PORT")
    return f"{m[1]}:{m[2]}"


def apt_cache_pinhole_cmds(cache, bridge="vmbr0"):
    """The commands that give the guests on `bridge` the apt cache and nothing else: the pinhole
    address on the bridge, IP forwarding off (a guest that takes the node for its router gets
    nowhere), and a transient systemd service with socat forwarding APT_PINHOLE_IP:APT_PINHOLE_PORT
    to the cache (a new connection to the cache per guest connection; it listens on the bridge
    address only). The first two systemctl commands clear an earlier run's service and may fail."""
    host, port = cache.rsplit(":", 1)
    return [
        ["systemctl", "stop", APT_PINHOLE_UNIT],
        ["systemctl", "reset-failed", APT_PINHOLE_UNIT],
        ["ip", "addr", "replace", f"{APT_PINHOLE_IP}/24", "dev", bridge],
        ["ip", "link", "set", bridge, "up"],
        ["sysctl", "-q", "-w", "net.ipv4.ip_forward=0"],
        ["systemd-run", f"--unit={APT_PINHOLE_UNIT}", "--property=Restart=always", "--quiet", "socat",
         f"TCP4-LISTEN:{APT_PINHOLE_PORT},bind={APT_PINHOLE_IP},fork,reuseaddr", f"TCP:{host}:{port}"],
    ]


def open_apt_cache_pinhole(cache):
    """Run apt_cache_pinhole_cmds() and check the forward: an HTTP request through it, which the
    cache answers with any status line. The cache's address stays out of the output. RuntimeError
    when it doesn't work."""
    for cmd in apt_cache_pinhole_cmds(cache):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode and cmd[:2] not in (["systemctl", "stop"], ["systemctl", "reset-failed"]):
            raise RuntimeError(f"apt cache pinhole: {' '.join(cmd[:4])} failed (exit {r.returncode})")
    for _ in range(10):
        try:
            with socket.create_connection((APT_PINHOLE_IP, APT_PINHOLE_PORT), timeout=5) as c:
                c.sendall(b"HEAD http://archive.debian.org/debian/dists/etch/Release HTTP/1.0\r\n\r\n")
                if c.recv(12).startswith(b"HTTP/"):
                    print(f"=== apt cache pinhole: {APT_PINHOLE_PROXY} on vmbr0 answers (IP forwarding off)", flush=True)
                    return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError(f"apt cache pinhole: no HTTP answer through {APT_PINHOLE_PROXY} (does the node reach the cache?)")


def boot_test_timeout(target, a):
    """Seconds `lab.py boot-test <target>` may take: the target's check and 10 minutes for the copy."""
    return max(a.timeout, targets.TARGETS[target]["check"]["timeout"] + 600)


LEFTOVERS = ("_fb_poll.png", "_refresh.ppm", "*.sock", "_frames")  # the recordings stay


def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def create_vm(name, config, iso, template, a, work):
    """The VM through the API; returns its VMID."""
    node = socket.gethostname()
    vmid = sh("pvesh", "get", "/cluster/nextid", "--output-format", "json").strip('"')
    if iso:
        os.makedirs(ISO_DIR, exist_ok=True)
        link = os.path.join(ISO_DIR, os.path.basename(iso))
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(os.path.join(a.iso, iso), link)
    raw, tmp = None, None
    if template and template.endswith(".xz"):
        raw = tmp = os.path.join(work, "template.raw")
        shutil.copy(os.path.join(a.disks, template), raw + ".xz")
        subprocess.run(["xz", "-d", "-f", raw + ".xz"], check=True)
    elif template:  # an installed disk: import-from only reads it
        raw = os.path.join(a.disks, template)
    if any("{bench}" in str(val) for val in config.values()) and not os.path.isfile(a.bench):
        raise subprocess.CalledProcessError(1, ["bench", "disk", a.bench], stderr=f"{a.bench} doesn't exist")
    params = {"vmid": vmid, "name": name.replace("_", "-"), **config}  # a DNS name
    volume = f"local:iso/{os.path.basename(iso)}" if iso else None
    args = []
    for k, val in params.items():
        args += [f"--{k}", str(val).format(iso=volume, template=raw, bench=a.bench)]
    try:
        sh("pvesh", "create", f"/nodes/{node}/qemu", *args)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    with open(os.path.join(work, "vm.conf"), "w", encoding="utf-8") as f:
        f.write(sh("qm", "config", vmid) + "\n")
    return vmid


def destroy_vm(vmid):
    subprocess.run(["qm", "stop", vmid], capture_output=True)
    subprocess.run(["qm", "destroy", vmid, "--purge", "--destroy-unreferenced-disks", "1"], capture_output=True)


def enable_floppy_content(storage="local"):
    """Add the `floppy` content type to the test node's storage (the e2e node's `local` lacks it, as
    every new storage does): floppy volumes are invisible to the API without it."""
    content = next((s.get("content", "") for s in json.loads(sh("pvesh", "get", "/storage", "--output-format", "json"))
                    if s["storage"] == storage), "")
    types = set(filter(None, content.split(",")))
    if "floppy" not in types:
        sh("pvesm", "set", storage, "--content", ",".join(sorted(types | {"floppy"})))


def link_media(target, a):
    """The target's media into the `local` storage under their expected names, as links to --iso (CDs)
    or --floppy (floppy images). A converted medium (MEDIA "from", e.g. the SunOS CD, OpenBSD 5.9's sets
    CD from the release's directory) that isn't in --iso is made there from its source with `lab.py media
    --convert`, as a user would, and kept."""
    for med in targets.TARGETS[target]["media"]:
        m = targets.MEDIA[med["name"]]
        if m["content"] == "floppy":
            enable_floppy_content()
        d = ISO_DIR if m["content"] == "iso" else os.path.join(os.path.dirname(ISO_DIR), "floppy")
        os.makedirs(d, exist_ok=True)
        link = os.path.join(d, med["name"])
        src = os.path.join(a.iso if m["content"] == "iso" else a.floppy, m["lab"])
        if "from" in m and not os.path.isfile(src):
            if os.path.isfile(link) and not os.path.islink(link):
                continue  # converted by an earlier case
            if os.path.lexists(link):
                os.unlink(link)
            source = m["from"]["dir"] if "files" in m["from"] else targets.MEDIA[m["from"]["name"]]["lab"]
            sh(sys.executable, os.path.join(HERE, "lab.py"), "media", target, "--convert", os.path.join(a.iso, source),
               "--dir", d)
            continue
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(src, link)


def run_step(name, label, out, a, cmd, timeout=None):
    """One lab.py run (a scenario or an install) with its output in <out>/lab.log; its result.json."""
    print(f"=== {name}: {' '.join(cmd)}", flush=True)
    timeout = timeout or a.timeout
    try:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "lab.log"), "w", encoding="utf-8") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        res = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    except subprocess.TimeoutExpired:
        res = {"code": 1, "status": f"timed out after {timeout}s"}
    except (OSError, ValueError) as e:
        res = {"code": 3, "status": f"no result.json ({e})"}
    res["scenario"] = label
    print(f"=== {name}: {label}: {res['status'].splitlines()[0]} ({res.get('elapsed', '?')}s)", flush=True)
    return res


def install_timeout(target, a):
    """Seconds `lab.py install <target> --check` may take: twice --timeout, or the target's phases
    (install, first boot, check) and 10 minutes when they add up to more (Solaris 10: ~2 h)."""
    t = targets.TARGETS[target]
    phases = sum(t[p]["timeout"] for p in ("install", "firstboot", "check") if p in t)
    return max(a.timeout * 2, phases + 600)


def install_net_args(target, a):
    """`lab.py install` options for the network: --apt-proxy through the pinhole for a target that
    fetches packages when the matrix has an apt cache (no --gateway or --dns: the guest gets no way out)."""
    if getattr(a, "apt_cache", None) and targets.TARGETS[target].get("apt_proxy"):
        return ["--apt-proxy", APT_PINHOLE_PROXY]
    return []


def run_case(name, config, iso, template, steps, a):
    work = os.path.join(a.runs, name)
    os.makedirs(work, exist_ok=True)
    t0, vmid, results = time.time(), None, []
    if "target" in config:
        action, why = plan(config["target"], a.disks, a.reinstall, getattr(a, "apt_cache", None))
        print(f"=== {name}: {action}: {why}", flush=True)
        if action == "skip":
            return {"code": 0, "skipped": True, "elapsed": 0, "steps": [], "status": f"skipped: {why}"}
        if action == "refuse":
            return {"code": 3, "elapsed": 0, "steps": [], "status": f"refused: {why}"}
        if action == "install" and install_net_args(config["target"], a) and getattr(a, "pinhole_error", None):
            return {"code": 3, "elapsed": 0, "steps": [], "status": a.pinhole_error}
    try:
        first = 1
        if "target" in config:
            target = config["target"]
            vmid = sh("pvesh", "get", "/cluster/nextid", "--output-format", "json").strip('"')
            lab_py = [sys.executable, os.path.join(HERE, "lab.py")]
            if action == "install":
                link_media(target, a)
                out = os.path.join(work, f"1-install-{target}")
                results.append(run_step(name, f"install {target}", out, a,
                                        [*lab_py, "install", target, "--vmid", vmid, "--out", out, "--check",
                                         "--export", a.disks, *install_net_args(target, a)],
                                        timeout=install_timeout(target, a)))
            else:
                out = os.path.join(work, f"1-boot-test-{target}")
                results.append(run_step(name, f"boot-test {target}", out, a,
                                        [*lab_py, "boot-test", target, "--vmid", vmid, "--out", out,
                                         "--disk", install.stored_disk(a.disks, target)[0]],
                                        timeout=boot_test_timeout(target, a)))
        elif "install" in config:
            target = config["install"]
            link_media(target, a)
            vmid = sh("pvesh", "get", "/cluster/nextid", "--output-format", "json").strip('"')
            out = os.path.join(work, f"1-install-{target}")
            res = run_step(name, f"install {target}", out, a,
                           [sys.executable, os.path.join(HERE, "lab.py"), "install", target, "--vmid", vmid,
                            "--out", out, "--check"], timeout=install_timeout(target, a))
            results.append(res)
            first = 2
            if res["code"]:
                steps = []
        else:
            vmid = create_vm(name, config, iso, template, a, work)
        print(f"=== {name}: VM {vmid}", flush=True)
        for n, (scenario, variables) in enumerate(steps, first):
            out = os.path.join(work, f"{n}-{scenario[:-3]}")
            cmd = [sys.executable, os.path.join(HERE, "lab.py"), "run", os.path.join(HERE, "scenarios", scenario),
                   "--pve", vmid, "--out", out, *[x for k, val in variables.items() for x in ("--var", f"{k}={val}")]]
            res = run_step(name, scenario, out, a, cmd)
            results.append(res)
            if res["code"]:
                break
    except subprocess.CalledProcessError as e:
        results.append({"code": 3, "scenario": "-", "status": f"{' '.join(e.cmd[:3])}: {e.stderr.strip()}"})
    finally:
        if vmid:
            destroy_vm(vmid)
        for pattern in LEFTOVERS:
            for p in glob.glob(os.path.join(work, "**", pattern), recursive=True):
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
    failed = next((r for r in results if r["code"]), None)
    return {"code": failed["code"] if failed else 0, "elapsed": round(time.time() - t0, 1),
            "steps": results, "status": failed["status"] if failed else "passed"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("matrix", choices=sorted(MATRICES))
    p.add_argument("--runs", required=True, help="output directory, one subdirectory per case")
    p.add_argument("--disks", default="/mnt/os/disks",
                   help="disk templates and installed disks (read only; install writes its stored disks here)")
    p.add_argument("--reinstall", nargs="?", const="all", action="append", metavar="all|TARGET[,TARGET]",
                   help="install: install these targets again (alone or `all`: every target without matrix_skip)"
                        " instead of boot-testing their stored disks")
    p.add_argument("--iso", default="/mnt/os/iso", help="install CDs (read only)")
    p.add_argument("--floppy", default="/mnt/os/floppy", help="install floppies (read only)")
    p.add_argument("--bench", default="/mnt/os/disks/bench-sol26.raw",
                   help="the bench disk (e2e/sparc/README.md, \"The bench disk\"; read only)")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per scenario")
    p.add_argument("--only", action="append", help="run only these cases")
    p.add_argument("--apt-cache", metavar="HOST:PORT",
                   help="install: an apt cache the node reaches (WSH_LAB_APT_CACHE); the targets that fetch"
                        f" packages get it as {APT_PINHOLE_PROXY} on vmbr0 and nothing else (none: they are skipped)")
    a = p.parse_args()
    if a.reinstall and a.matrix != "install":
        p.error("--reinstall: only with the install matrix")
    a.reinstall = reinstall_set(a.reinstall)
    a.apt_cache = apt_cache_choice(a.apt_cache or os.environ.get("WSH_LAB_APT_CACHE"))

    rows, failed, skipped = [], 0, 0
    cases = [c for c in MATRICES[a.matrix] if not a.only or c[0] in a.only]
    if a.apt_cache and any(install_net_args(c[1]["target"], a)
                           and plan(c[1]["target"], a.disks, a.reinstall, a.apt_cache)[0] == "install"
                           for c in cases if "target" in c[1]):
        try:
            open_apt_cache_pinhole(a.apt_cache)
        except RuntimeError as e:  # those installs fail (run_case), the rest of the matrix runs
            a.pinhole_error = str(e)
            print(f"=== {e}", flush=True)
    for name, config, iso, template, steps in cases:
        res = run_case(name, config, iso, template, steps, a)
        failed += res["code"] != 0
        skipped += bool(res.get("skipped"))
        done = ", ".join(f"`{r['scenario']}` {r.get('elapsed', '?')}s" for r in res["steps"]) or "-"
        status = res["status"].splitlines()[0][:160].replace("|", "\\|")
        result = "skip" if res.get("skipped") else "pass" if res["code"] == 0 else "FAIL"
        rows.append(f"| {name} | {done} | {result} | {res['elapsed']:.0f}s | {status} |")
    ran = len(rows) - skipped
    table = "\n".join([f"### sparc lab: {a.matrix} ({ran - failed}/{ran} passed"
                       + (f", {skipped} skipped" if skipped else "") + ")", "",
                       "| Case | Scenarios | Result | Time | Status |",
                       "| --- | --- | --- | --- | --- |", *rows])
    print("\n" + table)
    with open(os.path.join(a.runs, "summary.md"), "w", encoding="utf-8") as f:
        f.write(table + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
