"""`wsh-lab wisp-vm`: wisp, the tiny test system of wsh-pve (e2e/wisp), in a PVE VM on this node.

    wsh-lab wisp-vm x86_64 --vmid 900                 the wisp shell (the wisp-test kit's kernel) on serial
    wsh-lab wisp-vm sparc32 --vmid 901 --tier fb      the framebuffer kernel, the shell still on serial
    wsh-lab wisp-vm sparc32 --vmid 902 --doom --start Freedoom in fbDOOM: Console in the web UI to play
    wsh-lab wisp-vm stop|start|destroy --vmid 902

It downloads the published files with SHA-256 checks into a directory of its own (/var/lib/wsh-lab/wisp):
the `wisp-test-kit` release (the tier-1 kernels), the `wisp-fb` release (kernel-fb and the static fbdoom
per architecture) and Freedoom's own release (by the pinned URL and SHA-256 of e2e/wisp/doom/fetch.py).
--doom builds the squashfs data disk (fbdoom, freedoom1.wad, play.rsp; needs squashfs-tools) and imports
it as the VM's first disk; the kernel is booted with `args: -kernel ... -append ...` (root only, as for
the lab's prom_env), from a copy kept per VM, so a later release doesn't change an existing VM.

The VM uses the machine's PVE profile: pc (x86_64), SS-5 with OpenBIOS (sparc32), sun4u (sparc64) and virt
(aarch64). The shell VM has `vga: serial0`, so the web UI's Console is the serial shell; --tier fb and
--doom have the machine's framebuffer (std, cg3 or tcx) on the noVNC Console and its keyboard (sun4u and
virt: a virtio keyboard). It never touches an existing VMID, and stop/start/destroy only act on VMs it
made (tag wsh-lab-wisp).
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

RELEASES = "https://github.com/hwinther/wsh-pve/releases/download"
KIT = "wisp-test-kit.tar.xz"
# Freedoom Phase 1, as e2e/wisp/doom/fetch.py pins it (tests/test_wisp_vm.py checks they agree)
FREEDOOM_VERSION = "0.13.0"
FREEDOOM_URL = (f"https://github.com/freedoom/freedoom/releases/download/v{FREEDOOM_VERSION}/"
                f"freedoom-{FREEDOOM_VERSION}.zip")
FREEDOOM_SHA = "3f9b264f3e3ce503b4fb7f6bdcb1f419d93c7b546f4df3e874dd878db9688f59"
DIR = "/var/lib/wsh-lab/wisp"
TAG = "wsh-lab-wisp"
ARCHES = ("x86_64", "sparc32", "sparc64", "aarch64")
ACTIONS = ("start", "stop", "destroy")

# Per architecture: the PVE profile (pvesh create options without disk and display), the kernel console,
# the framebuffer displays the profile takes (the first is the default), the data disk's drive (the
# guest's first disk, sda) and the extra QEMU devices for the keyboard.
MACHINES = {
    "x86_64": {"profile": {"ostype": "l26", "machine": "pc", "memory": 256, "cores": 1},
               "console": "ttyS0", "displays": ("std",), "disk": "ide0", "devices": ()},
    "sparc32": {"profile": {"arch": "sparc", "machine": "SS-5", "bios": "openbios-sparc32", "memory": 128,
                            "ostype": "other"},
                "console": "ttyS0", "displays": ("cg3", "tcx"), "disk": "scsi0", "devices": ()},
    "sparc64": {"profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 256,
                            "ostype": "other"},
                "console": "ttyS0", "displays": ("std",), "disk": "ide0",
                # Linux can't use sun4u's EBus i8042 under OpenBIOS: a virtio keyboard on PCI
                "devices": ("virtio-keyboard-pci",)},
    "aarch64": {"profile": {"arch": "aarch64", "machine": "virt", "memory": 256, "cores": 1,
                            "ostype": "l26", "scsihw": "virtio-scsi-pci"},
                "console": "ttyAMA0", "displays": ("std",), "disk": "scsi0",
                "devices": ("virtio-keyboard-pci",)},
}


class WispError(Exception):
    pass


def run(*cmd, check=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and r.returncode:
        raise WispError(f"{' '.join(map(str, cmd[:4]))}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def parse_sums(text):
    """{name: sha256} from `sha256sum` output (one file or many)."""
    sums = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise WispError(f"not a sha256sum line: {line!r}")
        sums[parts[1].strip().lstrip("*")] = parts[0]
    return sums


def read_source(source, name):
    """The bytes of `name` from a release URL or a local directory laid out like one."""
    if re.match(r"https?://", source):
        with urllib.request.urlopen(f"{source}/{name}", timeout=120) as r:
            return r.read()
    with open(os.path.join(source, name), "rb") as f:
        return f.read()


def fetch(source, name, dest, digest):
    """`name` from `source` into the directory `dest`, unless a copy with `digest` is there; checked."""
    path = os.path.join(dest, name)
    if os.path.exists(path) and sha256(path) == digest:
        return path
    os.makedirs(dest, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest, prefix=f".{name}.")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(read_source(source, name))
        if sha256(tmp) != digest:
            raise WispError(f"{name}: SHA-256 mismatch (want {digest})")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def fetch_kit(source, directory, arch):
    """The wisp-test kit's tier-1 kernel for `arch` (the .tar.xz with its .sha256 beside it)."""
    want = parse_sums(read_source(source, f"{KIT}.sha256").decode()).get(KIT)
    if not want:
        raise WispError(f"{KIT}.sha256 doesn't name {KIT}")
    kit = fetch(source, KIT, os.path.join(directory, "kit"), want)
    out = os.path.join(directory, "kit", arch, "kernel")
    with tarfile.open(kit) as tar:
        member = tar.getmember(f"wisp-test-kit/{arch}/kernel")
        if not member.isfile():
            raise WispError(f"{KIT}: {member.name} is not a file")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with tar.extractfile(member) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return out


def fetch_fb(source, directory, arch, doom=False):
    """kernel-fb-<arch> (and with doom fbdoom-<arch>) from the wisp-fb release, checked by its SHA256SUMS."""
    sums = parse_sums(read_source(source, "SHA256SUMS").decode())
    paths = []
    for name in [f"kernel-fb-{arch}"] + ([f"fbdoom-{arch}"] if doom else []):
        if name not in sums:
            raise WispError(f"{name} is not in the wisp-fb release's SHA256SUMS")
        paths.append(fetch(source, name, os.path.join(directory, "fb"), sums[name]))
    return paths


def fetch_wad(directory, source=None):
    """freedoom1.wad from Freedoom's release (pinned URL and SHA-256), or from a local zip/WAD."""
    dest = os.path.join(directory, "freedoom")
    zip_name = os.path.basename(FREEDOOM_URL)
    if source and not source.endswith(".zip"):
        return source  # a WAD the user already has
    if source:
        archive = fetch(os.path.dirname(os.path.abspath(source)), os.path.basename(source), dest, FREEDOOM_SHA)
    else:
        archive = fetch(os.path.dirname(FREEDOOM_URL), zip_name, dest, FREEDOOM_SHA)
    wad = os.path.join(dest, "freedoom1.wad")
    with zipfile.ZipFile(archive) as z, z.open(f"freedoom-{FREEDOOM_VERSION}/freedoom1.wad") as src:
        with open(wad, "wb") as out:
            shutil.copyfileobj(src, out)
    return wad


def response(fps=False, sound=False):
    """fbDOOM's arguments on the data disk (play from the title screen at the largest scale)."""
    return " ".join(["-iwad", "/data/freedoom1.wad", "-nomusic" if sound else "-nosound"]
                    + (["-fps"] if fps else [])) + "\n"


def build_disk(work, fbdoom, wad, fps=False):
    """The squashfs data disk: /fbdoom, /freedoom1.wad, /play.rsp."""
    if not shutil.which("mksquashfs"):
        raise WispError("--doom builds a squashfs data disk with mksquashfs: apt install squashfs-tools")
    root = os.path.join(work, "data")
    os.makedirs(root)
    shutil.copyfile(fbdoom, os.path.join(root, "fbdoom"))
    os.chmod(os.path.join(root, "fbdoom"), 0o755)
    shutil.copyfile(wad, os.path.join(root, "freedoom1.wad"))
    with open(os.path.join(root, "play.rsp"), "w", encoding="ascii") as f:
        f.write(response(fps))
    disk = os.path.join(work, "doom.squashfs")
    run("mksquashfs", root, disk, "-comp", "xz", "-no-xattrs", "-all-root", "-noappend", "-quiet",
        "-no-progress")
    return disk


def append_line(arch, doom=False):
    """The kernel command line: the shell on serial, or fbDOOM from the data disk."""
    line = f"console={MACHINES[arch]['console']} panic=-1"
    if doom:
        return line + " quiet wisp=run wisp_data=/dev/sda wisp_run=/data/fbdoom -- @/data/play.rsp"
    return line + " wisp=shell"


def vm_args(arch, kernel, doom=False, fb=False):
    """The VM's `args`: -kernel and -append, and the keyboard device where the machine needs one."""
    words = ["-kernel", kernel, "-append", append_line(arch, doom)]
    if fb or doom:
        for device in MACHINES[arch]["devices"]:
            words += ["-device", device]
    return " ".join(shlex.quote(w) for w in words)


def vm_params(arch, vmid, kernel, display=None, fb=False, doom=False, disk=None, storage="local",
              name=None, kvm=None):
    """The options for `pvesh create /nodes/<node>/qemu`."""
    m = MACHINES[arch]
    p = dict(m["profile"])
    if fb or doom:
        display = display or m["displays"][0]
        if display not in m["displays"]:
            raise WispError(f"{arch}: display {display} isn't one of {', '.join(m['displays'])}")
        p["vga"] = display
    else:
        p["vga"] = "serial0"  # the web UI's Console is the serial shell
    p["serial0"] = "socket"
    if arch == "x86_64":
        p["kvm"] = 1 if (os.path.exists("/dev/kvm") if kvm is None else kvm) else 0
    if disk:
        p[m["disk"]] = f"{storage}:0,import-from={disk},format=raw"
    kind = "doom" if doom else "fb" if fb else "shell"
    p.update(vmid=vmid, name=name or f"wisp-{arch.replace('_', '-')}-{kind}", tags=TAG,
             description=f"wisp {kind} VM ({arch}), made by wsh-lab wisp-vm",
             args=vm_args(arch, kernel, doom, fb))
    return p


def node():
    return socket.gethostname().split(".")[0]


def pvesh_get(path, **params):
    args = [x for k, val in params.items() for x in (f"--{k}", val)]
    return json.loads(run("pvesh", "get", path, *args, "--output-format", "json") or "null")


def vm_exists(vmid):
    if os.path.exists(f"/etc/pve/qemu-server/{vmid}.conf") or os.path.exists(f"/etc/pve/lxc/{vmid}.conf"):
        return True
    return any(str(r.get("vmid")) == str(vmid) for r in pvesh_get("/cluster/resources", type="vm") or [])


def ours(vmid):
    """Whether VM `vmid` is one wisp-vm made (its tag)."""
    conf = run("qm", "config", vmid, check=False)
    tags = re.search(r"(?m)^tags: (.*)$", conf)
    return bool(tags) and TAG in re.split(r"[;, ]", tags.group(1))


def create(a):
    if a.vmid is None:
        a.vmid = int(run("pvesh", "get", "/cluster/nextid"))
    if vm_exists(a.vmid):
        raise WispError(f"VM {a.vmid} exists already; wisp-vm never touches an existing VMID")
    if a.node and a.node != node():
        raise WispError(f"--node {a.node}: run wisp-vm on that node (the kernel and disk are files on the node "
                        f"running it, {node()})")
    fb = a.tier == "fb" or a.doom
    directory = a.dir
    if fb:
        files = fetch_fb(a.fb_from, directory, a.arch, a.doom)
        kernel = files[0]
    else:
        kernel = fetch_kit(a.kit_from, directory, a.arch)
    print(f"{os.path.basename(kernel)}: SHA-256 checked, in {os.path.dirname(kernel)}")
    vm_dir = os.path.join(directory, f"vm-{a.vmid}")
    if os.path.exists(vm_dir):
        shutil.rmtree(vm_dir)  # left by a VM of this number that is gone (checked above)
    os.makedirs(vm_dir)
    with tempfile.TemporaryDirectory(dir=directory) as work:
        try:
            vm_kernel = os.path.join(vm_dir, "kernel")
            shutil.copyfile(kernel, vm_kernel)
            disk = None
            if a.doom:
                wad = fetch_wad(directory, a.wad)
                disk = build_disk(work, files[1], wad, a.fps)
                print(f"data disk: fbdoom, freedoom1.wad, play.rsp ({os.path.getsize(disk)} bytes)")
            params = vm_params(a.arch, a.vmid, vm_kernel, a.display, fb, a.doom, disk, a.storage, a.name)
            run("pvesh", "create", f"/nodes/{node()}/qemu", *[x for k, v in params.items() for x in (f"--{k}", v)])
        except BaseException:
            shutil.rmtree(vm_dir, ignore_errors=True)
            raise
    print(f"VM {a.vmid} ({params['name']}) created: vga {params['vga']}, args {params['args']}")
    if a.start:
        run("qm", "start", a.vmid)
        print(f"VM {a.vmid} started")
    if a.doom:
        print("Console (noVNC) in the web UI to play; ` toggles the FPS overlay, Backspace quits and powers off")
    elif fb:
        print(f"the shell is on serial (qm terminal {a.vmid}, or xterm.js); the framebuffer on the Console")
    else:
        print(f"the shell is on the Console (serial, xterm.js) or qm terminal {a.vmid}")
    return 0


def action(a):
    if a.vmid is None:
        raise WispError(f"{a.what} needs --vmid")
    if not vm_exists(a.vmid):
        raise WispError(f"no VM {a.vmid}")
    if not ours(a.vmid):
        raise WispError(f"VM {a.vmid} has no {TAG} tag: wisp-vm only acts on VMs it made")
    if a.what == "start":
        run("qm", "start", a.vmid)
    elif a.what == "stop":
        run("qm", "stop", a.vmid)
    else:
        run("qm", "stop", a.vmid, check=False)
        run("qm", "destroy", a.vmid, "--purge", "--destroy-unreferenced-disks", "1")
        shutil.rmtree(os.path.join(a.dir, f"vm-{a.vmid}"), ignore_errors=True)
    print(f"VM {a.vmid}: {a.what}")
    return 0


def cmd_wisp_vm(a):
    if a.what in ARCHES:
        a.arch = a.what
    if not shutil.which("qm"):
        sys.exit("wsh-lab wisp-vm runs on the PVE node (qm and pvesh), as root")
    try:
        return create(a) if a.what in ARCHES else action(a)
    except (WispError, OSError, tarfile.TarError, zipfile.BadZipFile, KeyError) as e:
        sys.exit(f"wisp-vm: {e}")


def add_commands(sub):
    w = sub.add_parser("wisp-vm", help="wisp (the tiny test system) or Freedoom in a new PVE VM (on the node, as root)",
                       description=__doc__.split("\n\n")[0])
    w.add_argument("what", choices=ARCHES + ACTIONS, help="an architecture to create a VM for, or an action")
    w.add_argument("--vmid", type=int, help="the new VM's ID (default: the next free one); the VM for an action")
    w.add_argument("--tier", choices=("shell", "fb"), default="shell",
                   help="shell: the kit's tier-1 kernel (default); fb: the framebuffer kernel")
    w.add_argument("--doom", action="store_true", help="fbDOOM and Freedoom on a data disk (implies --tier fb)")
    w.add_argument("--fps", action="store_true", help="with --doom: start with the FPS overlay on")
    w.add_argument("--display", help="with --tier fb/--doom: sparc32 cg3 (default) or tcx")
    w.add_argument("--node", help="the node (must be this one: the files live on it)")
    w.add_argument("--storage", default="local", help="storage for the data disk (local)")
    w.add_argument("--name", help="VM name (wisp-<arch>-<shell|fb|doom>)")
    w.add_argument("--start", action="store_true", help="start the VM after creating it")
    w.add_argument("--dir", default=DIR, help=f"where the downloads and the VMs' kernels go ({DIR})")
    w.add_argument("--kit-from", default=f"{RELEASES}/wisp-test-kit",
                   help="the wisp-test-kit release, or a directory with wisp-test-kit.tar.xz and its .sha256")
    w.add_argument("--fb-from", default=f"{RELEASES}/wisp-fb",
                   help="the wisp-fb release, or a directory with its files and SHA256SUMS")
    w.add_argument("--wad", help="a local freedoom-0.13.0.zip (checked) or freedoom1.wad instead of the download")


COMMANDS = {"wisp-vm": cmd_wisp_vm}
