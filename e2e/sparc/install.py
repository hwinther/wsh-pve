"""Install a named target (targets.py) into a new PVE VM, on the PVE node, as root:

    lab.py install sol26-ss5 --vmid 120 [--storage local] [--media-storage local] [--bridge vmbr0]
        [--name NAME] [--root-password PW] [--user NAME [--user-password PW]] [--hostname H] [--ip A]
        [--disk-size 3G|9G] [--data-disk GIB [--data-mount /data|/usr/local]]
        [--post-install BUNDLE [--local-env]]
        [--check [--export DIR]] [--template] [--keep-on-failure] [--allow-untested-media] [--timeout S] [--out DIR]
    lab.py boot-test sol26-ss5 --disk /mnt/os/disks/install-sol26-ss5.raw --vmid 121 [--keep] [--out DIR]
    lab.py targets [--json]
    lab.py media [<target>] [--storage local | --dir DIR] [--no-checksum]
    lab.py media <target> --convert SOURCE [--storage local | --dir DIR]

`install` (1) checks that the target's media are on the storage under their expected names with the
tested size and sha256, (2) refuses a VMID that exists anywhere in the cluster, (3) creates the VM
through the API (`pvesh create`) with the target's profile, a disk (Sun-labelled where the installer
needs it) and the media in their drives, (4) runs the install method (targets.py, "method") against
it in attach mode (lab.run_scenario with --pve), (5) ejects the media, sets the boot order to the
disk, boots once to set the root password, write /etc/wsh-lab-target and add the optional user, and
powers off, (6) with --check boots again and logs in with the documented password and checks the
marker, (7) writes the login details and target metadata into the VM's description, (8) with
--template converts it to a template, and prints a summary. The evidence of every phase (serial log,
steps with screenshots, recordings) is in --out. On a failure the VM is destroyed, or with
--keep-on-failure stopped and kept with "FAILED" in its description; the exit code is 1.

With --export DIR (needs --check, the target's default install), a passing install's first disk is
copied to DIR/install-<target>.raw with install-<target>.json (what made it) beside it, replacing the
previous ones only when complete. `boot-test` creates a VM with the target's profile from a copy of
that disk (`import-from`: the stored disk is only read), boots it through PVE, runs the target's check
(the --check boot: login, marker, state) and destroys the VM: minutes instead of the install's hours.
"""
import datetime
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

import answer_media
import lab
import sunlabel
import targets

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = os.path.join(HERE, "scenarios")
# What --root-password and --user-password may be: typed on a console and kept in the VM's
# description, so plain characters only; Solaris 2.x uses the first 8.
PASSWORD = re.compile(r"[A-Za-z0-9._@%+=,-]{1,8}")
USERNAME = re.compile(r"[a-z][a-z0-9]{0,7}")


class InstallFailed(Exception):
    pass


def run(*cmd, check=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and r.returncode:
        raise InstallFailed(f"{' '.join(map(str, cmd[:4]))}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def pvesh_get(path, **params):
    args = [x for k, val in params.items() for x in (f"--{k}", val)]
    return json.loads(run("pvesh", "get", path, *args, "--output-format", "json") or "null")


def node():
    return socket.gethostname().split(".")[0]


# --- media ----------------------------------------------------------------------------------------

_SHA256 = {}


def sha256(path):
    """The file's sha256, computed once per file, size and time (a medium may be looked at twice)."""
    st = os.stat(path)
    key = (os.path.realpath(path), st.st_size, st.st_mtime_ns)
    if key not in _SHA256:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        _SHA256[key] = h.hexdigest()
    return _SHA256[key]


class NoFloppyContent(InstallFailed):
    pass


def all_storage_content():
    """{storage: set of content types} from /etc/pve/storage.cfg (via the API)."""
    return {s["storage"]: set(s.get("content", "").split(",")) for s in pvesh_get("/storage") or []}


def storage_content(storage):
    """The content types of one storage, or None when the node can't say."""
    try:
        return all_storage_content().get(storage)
    except InstallFailed:
        return None


def find_medium(name, storage=None, directory=None):
    """(volume ID or None, local path or None) of the medium `name`: on a PVE storage (its content of
    the medium's type) or, with `directory`, as `<dir>/<name>` or `<dir>/<lab path>`. On a storage
    without a volume of that name, a volume of the medium's size and sha256 under any other name is it
    (a mirror storage's `Solaris__2.6__solaris_2.6_598_sparc.iso`, a renamed upload)."""
    med = targets.MEDIA[name]
    if directory:
        for rel in (name, med["lab"]):
            if os.path.isfile(os.path.join(directory, rel)):
                return None, os.path.join(directory, rel)
        return None, None
    if med["content"] == "floppy":
        types = storage_content(storage)
        if types is not None and "floppy" not in types:
            others = [s for s, t in all_storage_content().items() if "floppy" in t]
            raise NoFloppyContent(
                f"storage {storage} doesn't have the 'floppy' content type (it has {','.join(sorted(types))}): "
                f"enable it with `pvesm set {storage} --content {','.join(sorted(types | {'floppy'}))}`"
                + (f", or use --media-storage/--storage {' or '.join(others)}" if others else
                   "; no storage on this node has it"))
    try:
        content = pvesh_get(f"/nodes/{node()}/storage/{storage}/content", content=med["content"])
    except InstallFailed as e:
        raise InstallFailed(f"storage {storage}: {e} (does it exist and hold {med['content']} content?)")
    volid = f"{storage}:{med['content']}/{name}"
    if any(c.get("volid") == volid for c in content or []):
        return volid, run("pvesm", "path", volid)
    return find_by_checksum(med, content)


def find_by_checksum(med, content):
    """(volume ID, path) of the first volume in `content` (a storage's content list) with the medium's
    size and sha256, or (None, None). Only volumes of the right size are read."""
    for c in content or []:
        if c.get("size") != med["size"] or not c.get("volid"):
            continue
        try:
            path = run("pvesm", "path", c["volid"])
            if sha256(path) == med["sha256"]:
                return c["volid"], path
        except (InstallFailed, OSError):
            continue
    return None, None


def check_media(names, storage=None, directory=None, checksum=True):
    """One row per medium: name, volid, path, size, sha256, state ("ok", "missing", "size differs",
    "checksum differs", "not checked") and ok (the medium is the tested one)."""
    rows = []
    for name in names:
        med = targets.MEDIA[name]
        note = None
        try:
            volid, path = find_medium(name, storage, directory)
        except NoFloppyContent as e:
            volid, path, note = None, None, str(e)
        row = {"name": name, "volid": volid, "path": path, "content": med["content"], "size": None,
               "sha256": None, "state": "no floppy storage" if note else "missing", "ok": False, "note": note}
        if path:
            row["size"] = os.path.getsize(path)
            if row["size"] != med["size"]:
                row["state"] = "size differs"
            elif not checksum:
                row["state"] = "not checked"
            else:
                row["sha256"] = sha256(path)
                row["ok"] = row["sha256"] == med["sha256"]
                row["state"] = "ok" if row["ok"] else "checksum differs"
        rows.append(row)
    return rows


def convert_medium(name, source, dest, checksum=True):
    """Write the medium `name` (a MEDIA entry with "from") to the file `dest` from `source`, the medium
    it is made from: refuses a source of another size, or with `checksum` another sha256, and removes a
    result whose sha256 isn't the tested one. Returns the result's sha256."""
    med = targets.MEDIA[name]
    if "from" not in med:
        raise InstallFailed(f"{name} is used as it is, not converted")
    if "files" in med["from"]:
        return convert_files(name, source, dest, checksum)
    src = targets.MEDIA[med["from"]["name"]]
    size_in, offset, size_out = targets.CONVERSIONS[med["from"]["convert"]]
    if os.path.getsize(source) != src["size"]:
        raise InstallFailed(f"{source}: {os.path.getsize(source)} bytes, not {src['size']} ({med['from']['name']})")
    if checksum and sha256(source) != src["sha256"]:
        raise InstallFailed(f"{source}: not the tested {med['from']['name']} (sha256 {src['sha256']})")
    if os.path.exists(dest):
        raise InstallFailed(f"{dest} exists already")
    h = hashlib.sha256()
    tmp = dest + ".part"
    try:
        with open(source, "rb") as f, open(tmp, "wb") as o:
            for sector in iter(lambda: f.read(size_in), b""):
                data = sector[offset:offset + size_out]
                o.write(data)
                h.update(data)
        if h.hexdigest() != med["sha256"]:
            raise InstallFailed(f"the result's sha256 is {h.hexdigest()}, not the tested {med['sha256']}")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return h.hexdigest()


def convert_files(name, source, dest, checksum=True):
    """convert_medium for a medium made from several files (MEDIA "from" with "files", {file name:
    (size, sha256)}): `source` is the directory with them (the release's), each must have its size
    and, with `checksum`, its sha256; the CD is written with targets.FILE_CONVERSIONS[convert] (a function
    of answer_media) and must be the tested one byte for byte."""
    med = targets.MEDIA[name]
    if not os.path.isdir(source):
        raise InstallFailed(f"{source}: not a directory ({name} is made from the files {', '.join(med['from']['files'])})")
    if os.path.exists(dest):
        raise InstallFailed(f"{dest} exists already")
    files = {}
    for fname, (size, digest) in med["from"]["files"].items():
        path = os.path.join(source, fname)
        if not os.path.isfile(path) or os.path.getsize(path) != size:
            raise InstallFailed(f"{path}: missing or not {size} bytes")
        with open(path, "rb") as f:
            files[fname] = f.read()
        if checksum and hashlib.sha256(files[fname]).hexdigest() != digest:
            raise InstallFailed(f"{path}: not the tested file (sha256 {digest})")
    data = getattr(answer_media, targets.FILE_CONVERSIONS[med["from"]["convert"]])(files)
    digest = hashlib.sha256(data).hexdigest()
    if digest != med["sha256"] or len(data) != med["size"]:
        raise InstallFailed(f"the result's sha256 is {digest}, not the tested {med['sha256']}")
    tmp = dest + ".part"
    try:
        with open(tmp, "wb") as o:
            o.write(data)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return digest


# --- the VM ---------------------------------------------------------------------------------------

def vm_exists(vmid):
    if os.path.exists(f"/etc/pve/qemu-server/{vmid}.conf") or os.path.exists(f"/etc/pve/lxc/{vmid}.conf"):
        return True
    return any(str(r.get("vmid")) == str(vmid) for r in pvesh_get("/cluster/resources", type="vm") or [])


def disk_choice(t, name):
    """The target's first disk at --disk-size `name` (None: its default): t["disk"] with the size and
    label of targets.DISKS[name] and "name". Only the sizes the target was tested with (its "sizes")."""
    disk = dict(t["disk"])
    sizes = disk.get("sizes") or []
    if name is None:
        return {**disk, "name": sizes[0] if sizes else f"{disk['size']}G"}
    if name not in sizes:
        tested = f"tested with {', '.join(sizes)}" if sizes else "tested with its one disk only"
        raise SystemExit(f"--disk-size {name}: {t.get('title', 'this target')} is {tested}")
    return {**disk, "size": targets.DISKS[name]["size"], "geometry": targets.DISKS[name]["geometry"], "name": name}


DATA_DISK_BUS = "scsi4"  # SCSI target 4: after the boot disk (3) in OpenBIOS's probe, before the CD (6)
DATA_DISK_DEVICE = "c0t4d0"  # what Solaris calls it


DATA_MOUNTS = ("/data", "/usr/local")  # --data-mount


def data_mount(a):
    """Where the data disk is mounted: --data-mount, else /usr/local with --post-install (the bundles'
    BASEDIR), else /data."""
    if getattr(a, "data_mount", None):
        return a.data_mount
    if getattr(a, "post_install", None):
        return targets.POST_INSTALL[a.post_install]["basedir"]
    return "/data"


def check_post_install(a):
    """Refuses (SystemExit) --data-mount, --post-install and --local-env where they don't apply: the
    bundle only on the targets it was tested on, onto a data disk mounted on its BASEDIR and big
    enough; --local-env only with a bundle that brings the login shell."""
    bundle, local_env = getattr(a, "post_install", None), getattr(a, "local_env", False)
    if getattr(a, "data_mount", None) and a.data_disk is None:
        sys.exit("--data-mount: only with --data-disk")
    if local_env and not bundle:
        sys.exit("--local-env: only with --post-install (it puts the bundle's /usr/local/bin on PATH and "
                 "makes its bash the user's login shell)")
    if not bundle:
        return
    b = targets.POST_INSTALL[bundle]
    if a.target not in b["targets"]:
        sys.exit(f"--post-install {bundle}: tested on {', '.join(b['targets'])}, not {a.target}")
    if a.data_disk is None:
        sys.exit(f"--post-install {bundle}: needs --data-disk (at least {b['min_data_disk']} GiB): its packages go "
                 f"to {b['basedir']}, and /usr has too little space on the 3G and 9G layouts")
    if a.data_disk < b["min_data_disk"]:
        sys.exit(f"--post-install {bundle}: --data-disk {b['min_data_disk']} GiB or more")
    if data_mount(a) != b["basedir"]:
        sys.exit(f"--post-install {bundle}: the data disk must be on {b['basedir']} (not --data-mount {a.data_mount})")
    if local_env and not b.get("shell"):
        sys.exit(f"--local-env: {bundle} brings no login shell")


DEFAULT_IP, DEFAULT_NETMASK = "10.0.2.15", "255.255.255.0"
DOMAIN = re.compile(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", re.I)


def network_choice(t, a):
    """The guest's network from --ip (an address or `dhcp`), --netmask, --gateway, --dns, --domain and
    --vlan, checked against what the target was tested with (t["net_modes"]): a dict for the
    scenarios, the marker and the VM's notes. Refuses (SystemExit) what the target doesn't support
    rather than making a VM without a network."""
    modes = t.get("net_modes") or []
    if modes == ["none"]:  # the guest configures no network (DOS): only the NIC's bridge and VLAN apply
        given = [o for o in ("ip", "netmask", "gateway", "dns", "domain") if getattr(a, o, None)]
        if given:
            raise SystemExit(f"--{given[0]}: {a.target} configures no network in the guest")
        if a.vlan is not None and not 1 <= a.vlan <= 4094:
            raise SystemExit("--vlan takes a VLAN tag, 1-4094")
        return {"mode": "none", "vlan": a.vlan, "bridge": a.bridge, "ip": None, "netmask": None, "gateway": None,
                "dns": [], "domain": None}
    mode = "dhcp" if (a.ip or "").lower() == "dhcp" else "static"
    if mode not in modes:
        raise SystemExit(f"--ip {a.ip or DEFAULT_IP}: {a.target} supports {', '.join(modes) or 'no network settings'}"
                         " (what was tested)")
    for opt, why in (t.get("net_refuse") or {}).items():
        if getattr(a, opt, None):
            raise SystemExit(f"--{opt}: not with {a.target} ({why})")
    if a.vlan is not None and not 1 <= a.vlan <= 4094:
        raise SystemExit("--vlan takes a VLAN tag, 1-4094")
    net = {"mode": mode, "vlan": a.vlan, "bridge": a.bridge, "ip": None, "netmask": None, "gateway": None,
           "dns": [], "domain": (a.domain or "").lower() or None}
    try:
        net["dns"] = [str(ipaddress.IPv4Address(x.strip())) for x in (a.dns or "").split(",") if x.strip()]
    except ValueError as e:
        raise SystemExit(f"--dns: {e}")
    if len(net["dns"]) > 3:
        raise SystemExit("--dns: at most 3 name servers")
    if net["domain"] and not DOMAIN.fullmatch(net["domain"]):
        raise SystemExit(f"--domain {a.domain}: not a domain name")
    if net["domain"] and not net["dns"] and mode == "static":
        raise SystemExit("--domain needs --dns (the name servers to ask)")
    if mode == "dhcp":
        if a.netmask or a.gateway:
            raise SystemExit("--netmask and --gateway come from the DHCP server with --ip dhcp")
        return net
    try:
        iface = ipaddress.IPv4Interface(f"{a.ip or DEFAULT_IP}/{a.netmask or DEFAULT_NETMASK}")
    except ValueError as e:
        raise SystemExit(f"--ip/--netmask: {e}")
    if iface.ip in (iface.network.network_address, iface.network.broadcast_address) and iface.network.prefixlen < 31:
        raise SystemExit(f"--ip {iface.ip} is the network's or broadcast address of {iface.network}")
    net.update(ip=str(iface.ip), netmask=str(iface.netmask), network=str(iface.network.network_address),
               prefix=iface.network.prefixlen)
    # Not needed with an --apt-proxy at an address on the guest's own network (the lab's apt cache
    # pinhole, pve_matrix.py --apt-cache): apt and debian-installer hand the proxy whole URLs. Nor in
    # a boot test (`boot_test`), which installs nothing
    local_proxy = proxy_on_network(apt_proxy_choice(t, getattr(a, "apt_proxy", None)), iface.network)
    for opt in t.get("net_require") or []:
        if not getattr(a, opt, None) and not local_proxy and not getattr(a, "boot_test", False):
            raise SystemExit(f"--{opt}: {a.target} needs it with a static address (its installer fetches packages),"
                             " unless --apt-proxy is an address on the guest's network")
    if a.gateway:
        try:
            gw = ipaddress.IPv4Address(a.gateway)
        except ValueError as e:
            raise SystemExit(f"--gateway: {e}")
        if gw not in iface.network or gw == iface.ip:
            raise SystemExit(f"--gateway {gw} isn't another address in {iface.network}")
        net["gateway"] = str(gw)
    return net


APT_PROXY = re.compile(r"https?://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:(?P<port>[0-9]{1,5}))?/?")


def apt_proxy_choice(t, url, env=os.environ):
    """--apt-proxy, else WSH_LAB_APT_PROXY: an http(s)://host[:port] URL for the targets whose installer
    fetches packages itself (the target's "apt_proxy": Debian's netinst), None without one. --apt-proxy
    for another target, or anything but such a URL (a path, user:password@, spaces), is refused before
    a VM is made; the environment variable applies only to the targets that take it."""
    if not url:
        url = env.get("WSH_LAB_APT_PROXY") if t.get("apt_proxy") else None
        if not url:
            return None
    elif not t.get("apt_proxy"):
        raise SystemExit(f"--apt-proxy: {t.get('title', 'this target')} fetches no packages during the install")
    m = APT_PROXY.fullmatch(url)
    if not m or (m["port"] and not 0 < int(m["port"]) < 65536):
        raise SystemExit(f"--apt-proxy {url}: not an http(s)://host[:port] URL")
    return url


def proxy_on_network(url, network):
    """Whether an --apt-proxy URL names an IPv4 address inside `network` (an ipaddress network): the
    guest reaches it without a router or a name server."""
    m = APT_PROXY.fullmatch(url or "")
    if not m:
        return False
    host = re.match(r"https?://([^:/]+)", url).group(1)
    try:
        return ipaddress.IPv4Address(host) in network
    except ValueError:
        return False


def network_text(net, nic="le0", dhcp_note=None):
    """One line for the VM's notes and the summary; `dhcp_note`: what the guest takes from the DHCP
    server (the target's "dhcp_note"; Solaris's by default)."""
    where = f"bridge {net['bridge']}" + (f", VLAN {net['vlan']}" if net["vlan"] else "")
    if net["mode"] == "none":
        return f"none configured in the guest (the NIC is on {where})"
    if net["mode"] == "dhcp":
        s = f"{nic} by DHCP"
        extra = [dhcp_note or "router, name servers and host name from the DHCP server (host name unknown if it sends none)"]
        if net["dns"]:
            extra.append(f"DNS {', '.join(net['dns'])} unless the server sends name servers")
    else:
        s = f"{nic} {net['ip']}/{net['prefix']} (netmask {net['netmask']}), static"
        extra = [f"default router {net['gateway']}" if net["gateway"] else "no default route",
                 f"DNS {', '.join(net['dns'])}" if net["dns"] else "no name service"]
    if net.get("domain"):
        extra.append(f"domain {net['domain']}")
    where = f"bridge {net['bridge']}" + (f", VLAN {net['vlan']}" if net["vlan"] else "")
    return f"{s}; {'; '.join(extra)} ({where})"


def drive_volume(drive, vol, as_disk=False):
    """A medium's drive value for the VM config: CDs as media=cdrom, floppies read only (they are
    shared reference media; a written image no longer matches its sha256). `as_disk` (the medium's
    "as_disk" in targets.py): the CD answers as a read-only disk (qemu-server's sparc32-only
    cd_as_disk=1; Solaris 2.4/2.5.1 boot their installer only from such a CD)."""
    if drive.startswith("floppy"):
        return f"{vol},ro=1"
    return f"{vol},media=cdrom" + (",cd_as_disk=1" if as_disk else "")


def vm_params(t, a, volids, disk_image, disk=None):
    """The options for `pvesh create /nodes/<node>/qemu`; `disk`: disk_choice() (the default disk)."""
    p = dict(t["profile"])
    p["net0"] = f"{p['net0']},bridge={a.bridge}"
    if getattr(a, "vlan", None):
        p["net0"] += f",tag={a.vlan}"
    disk = disk or t["disk"]
    if disk_image:
        p[disk["bus"]] = f"{a.storage}:0,import-from={disk_image},format=raw"
    else:
        p[disk["bus"]] = f"{a.storage}:{disk['size']},format=raw"
    for med in t["media"]:
        if med.get("at", "start") == "start":
            vol = volids[med["name"]]
            p[med["drive"]] = drive_volume(med["drive"], vol, med.get("as_disk", False))
    p.update(vmid=a.vmid, name=a.name or a.target, tags="wsh-lab",
             description=f"wsh-lab install of {a.target} in progress (lab.py install)")
    return p


def create_vm(t, a, volids, work, disk=None):
    disk = disk or t["disk"]
    disk_image = None
    if disk.get("label") == "sun":
        disk_image = sunlabel.write_disk(os.path.join(work, "disk-label.raw"), disk["size"], disk["geometry"])
    try:
        params = vm_params(t, a, volids, disk_image, disk)
        run("pvesh", "create", f"/nodes/{node()}/qemu", *[x for k, val in params.items() for x in (f"--{k}", val)])
    finally:
        if disk_image and os.path.exists(disk_image):
            os.unlink(disk_image)
    save_config(a.vmid, work)


def save_config(vmid, work):
    conf = run("qm", "config", vmid)
    with open(os.path.join(work, "vm.conf"), "w", encoding="utf-8") as f:
        f.write(conf + "\n")


def add_data_disk(a, work):
    """--data-disk: a second disk on DATA_DISK_BUS with a Sun label (sunlabel.data_geometry), added
    after the install so the installer's disk selection never sees it; the first boot makes its
    device nodes, newfs's slice 0 and mounts it on /data (solaris-firstboot.py, DATA_DISK)."""
    image = sunlabel.write_disk(os.path.join(work, "data-disk-label.raw"), a.data_disk,
                                sunlabel.data_geometry(a.data_disk))
    try:
        run("qm", "set", a.vmid, f"--{DATA_DISK_BUS}", f"{a.storage}:0,import-from={image},format=raw")
    finally:
        os.unlink(image)
    save_config(a.vmid, work)


def set_prom_env(vmid, env):
    """OpenBIOS variables for the install phase only (targets.py, install "prom_env"), as QEMU's
    -prom-env in the VM's `args` (root only; qemu-server has no option for them). Solaris 8's Web
    Start needs auto-boot? false: it reboots with a boot string that OpenBIOS drops. Job.finish()
    removes them again, so the installed VM's config has no `args`."""
    if re.search(r"(?m)^args:", run("qm", "config", vmid)):
        raise InstallFailed(f"VM {vmid} has `args` already; prom_env would replace them")
    run("qm", "set", vmid, "--args", " ".join(f"-prom-env {k}={val}" for k, val in env.items()))


def vm_running(vmid):
    return "status: running" in run("qm", "status", vmid, check=False)


def destroy_vm(vmid):
    run("qm", "stop", vmid, check=False)
    run("qm", "destroy", vmid, "--purge", "--destroy-unreferenced-disks", "1", check=False)


# --- stored disks ----------------------------------------------------------------------------------
# `lab.py install --check --export DIR` copies the first disk of an install that passed its check to
# DIR/install-<target>.raw (sparse, written to a temporary name and renamed: the previous disk stays
# until the new one has passed) with install-<target>.json beside it, which says what made it.
# `lab.py boot-test <target> --disk DIR/install-<target>.raw` boots a copy of it in a new VM through PVE
# and runs the target's check (the --check boot). The prefix keeps them apart from the hand-made
# disks in the same directory (matrix.py's netbsd111-sparc64-installed.raw, sol10-sun4u-installed.raw).

STORED_BY = "lab.py install --check --export (wsh-pve e2e/sparc)"
# What the stored disk must be: the target's default install, so that the boot test can log in with
# the default password and the check needs nothing but the first disk
EXPORT_REFUSED = {"root_password": "--root-password", "user": "--user", "user_password": "--user-password",
                  "data_disk": "--data-disk", "post_install": "--post-install", "template": "--template"}
PACKAGES = ("pve-qemu-kvm", "qemu-server", "pve-manager", "wsh-lab")  # wsh-lab: None when run from a clone


def stored_disk(directory, target):
    """The stored disk of a target and its sidecar: (DIR/install-<target>.raw, DIR/install-<target>.json)."""
    base = os.path.join(directory, f"install-{target}")
    return base + ".raw", base + ".json"


def read_sidecar(directory, target):
    """The sidecar of the target's stored disk (a dict), or None when there is no stored disk; raises
    InstallFailed for a disk that this machinery didn't write (no sidecar, another target's, unreadable),
    which neither the boot test nor an export touches."""
    raw, side = stored_disk(directory, target)
    if not os.path.exists(raw) and not os.path.exists(side):
        return None
    if not os.path.isfile(raw):
        raise InstallFailed(f"{side} without {os.path.basename(raw)}")
    try:
        with open(side, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError) as e:
        raise InstallFailed(f"{raw} has no readable sidecar {os.path.basename(side)} ({e}): not a stored disk"
                            " of lab.py install --export; move it away") from None
    if not isinstance(meta, dict) or meta.get("target") != target or meta.get("by") != STORED_BY:
        raise InstallFailed(f"{side} isn't the sidecar of {target}'s stored disk (target {meta.get('target')!r})"
                            if isinstance(meta, dict) else f"{side}: not a JSON object")
    return meta


def export_problems(a):
    """Why --export can't be used with these options ([] when it can): it needs --check, the target's
    default install and a writable directory with no foreign file under the stored disk's name."""
    if not getattr(a, "export", None):
        return []
    out = []
    if not a.check:
        out.append("--export needs --check: only a disk that passed its check is stored")
    out += [f"--export stores the target's default install, not one with {opt} (the boot test logs in with"
            f" the default password and checks the first disk only)" for key, opt in EXPORT_REFUSED.items()
            if getattr(a, key, None)]
    if not os.path.isdir(a.export):
        out.append(f"--export {a.export}: no such directory")
    elif not os.access(a.export, os.W_OK):
        out.append(f"--export {a.export}: not writable")
    else:
        try:
            read_sidecar(a.export, a.target)
        except InstallFailed as e:
            out.append(f"--export: {e}")
    return out


def sparse_copy(src, dest, block=1 << 20):
    """Copy src to dest leaving holes where src has all-zero blocks (the disk images are sparse), then
    fsync dest."""
    zero = bytes(block)
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        while True:
            chunk = fi.read(block)
            if not chunk:
                break
            if chunk == zero[:len(chunk)]:
                fo.seek(len(chunk), os.SEEK_CUR)
            else:
                fo.write(chunk)
        fo.truncate()
        fo.flush()
        os.fsync(fo.fileno())


def write_stored_disk(src, directory, target, meta):
    """src (the VM's disk image) as the target's stored disk with `meta` in its sidecar, atomically:
    both are written to temporary names first and renamed over the old ones only when complete."""
    raw, side = stored_disk(directory, target)
    tmp_raw, tmp_side = f"{raw}.tmp-{os.getpid()}", f"{side}.tmp-{os.getpid()}"
    try:
        sparse_copy(src, tmp_raw)
        meta = {**meta, "target": target, "by": STORED_BY, "disk": os.path.basename(raw),
                "bytes": os.path.getsize(tmp_raw)}
        with open(tmp_side, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            f.write("\n")
        os.replace(tmp_raw, raw)
        os.replace(tmp_side, side)
    finally:
        for p in (tmp_raw, tmp_side):
            if os.path.exists(p):
                os.unlink(p)
    return raw, side


def package_versions(names=PACKAGES):
    """The installed versions of the PVE packages the lab depends on ({name: version or None})."""
    out = {}
    for n in names:
        r = subprocess.run(["dpkg-query", "-W", "-f", "${Version}", n], capture_output=True, text=True)
        out[n] = r.stdout.strip() if r.returncode == 0 else None
    return out


def vm_disk_path(vmid, bus):
    """The image file of the VM's disk on `bus` (its volume through `pvesm path`)."""
    m = re.search(rf"(?m)^{re.escape(bus)}: ([^,\s]+)", run("qm", "config", vmid))
    if not m or m.group(1) == "none":
        raise InstallFailed(f"VM {vmid} has no disk on {bus}")
    return run("pvesm", "path", m.group(1))


def export_disk(job):
    """--export: the installed VM's first disk as the target's stored disk (after a passing check)."""
    a, t = job.a, job.target
    meta = {"title": t["title"], "installed": job.started.isoformat().replace("+00:00", "Z"),
            "exported": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
            .replace("+00:00", "Z"),
            "minutes": round((time.time() - job.t0) / 60, 1),
            "phases": {p["phase"]: p["elapsed"] for p in job.phases},
            "packages": package_versions(), "profile": t["profile"], "boot_disk": job.disk["bus"],
            "disk_size": job.disk["name"], "hostname": job.hostname, "network": job.net_text(),
            "root_password": "the default (targets.DEFAULT_ROOT_PASSWORD)",
            "media": [{"name": m["name"], "sha256": m["sha256"]} for m in job.media],
            "lab_commit": os.environ.get("WSH_LAB_COMMIT") or None}
    src = vm_disk_path(a.vmid, job.disk["bus"])
    raw, _ = write_stored_disk(src, a.export, a.target, meta)
    job.log(f"exported {job.disk['bus']} ({src}) to {raw} after {meta['minutes']} min")
    return raw


def boot_test_vm_params(t, a, disk_file):
    """The VM of a boot test: the target's profile as `install` leaves it (the media drives empty, the
    boot order on the disk), the disk imported from a copy of the stored disk."""
    p = dict(t["profile"])
    p["net0"] = f"{p['net0']},bridge={a.bridge}"
    p[t["disk"]["bus"]] = f"{a.storage}:0,import-from={disk_file},format=raw"
    for drive in dict.fromkeys(med["drive"] for med in t["media"]):
        p[drive] = "none" if drive.startswith("floppy") else "none,media=cdrom"
    p.update(boot=f"order={t['boot']}", vmid=a.vmid, name=a.name or f"{a.target}-boot-test", tags="wsh-lab",
             description=f"wsh-lab boot test of {a.target} from {disk_file} (lab.py boot-test)")
    return p


def boot_test_problems(a):
    """Why `lab.py boot-test` can't run ([] when it can) and the stored disk's sidecar."""
    t = targets.TARGETS.get(a.target)
    if not t:
        return [f"unknown target {a.target!r}; `lab.py targets` lists them"], None
    if t["status"] != "automated" or "check" not in t:
        return [f"{a.target} has no check to run (not an automated target)"], None
    d, name = os.path.dirname(os.path.abspath(a.disk)), os.path.basename(a.disk)
    if name != os.path.basename(stored_disk(d, a.target)[0]):
        return [f"--disk {a.disk}: {a.target}'s stored disk is named {os.path.basename(stored_disk(d, a.target)[0])}"], None
    try:
        meta = read_sidecar(d, a.target)
    except InstallFailed as e:
        return [str(e)], None
    if meta is None:
        return [f"--disk {a.disk}: no such file (lab.py install {a.target} --check --export {d} makes it)"], None
    return [], meta


def cmd_boot_test(a):
    """lab.py boot-test: a new VM from a copy of the target's stored disk, booted through PVE, the
    target's check run against it, the VM destroyed (kept stopped with --keep)."""
    problems, meta = boot_test_problems(a)
    if problems:
        sys.exit("\n".join(problems))
    if not shutil.which("qm"):
        sys.exit("lab.py boot-test runs on the PVE node (as root), where qm and pvesh are")
    t = targets.TARGETS[a.target]
    a.vmid = str(a.vmid)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    a.out = os.path.abspath(a.out or os.path.join("/var/lib/wsh-lab/boot-tests", f"{a.target}-{a.vmid}-{stamp}"))
    os.makedirs(a.out, exist_ok=True)
    # the defaults of `install` (the stored disk is the target's default install: export_problems)
    for k, val in dict(root_password=None, user_password=None, user=None, hostname=meta.get("hostname"), ip=None,
                       netmask=None, gateway=None, dns=None, domain=None, vlan=None, apt_proxy=None, disk_size=None,
                       data_disk=None, data_mount=None, post_install=None, local_env=False, keyboard=None,
                       timeout=None).items():
        setattr(a, k, getattr(a, k, val))
    a.boot_test = True  # no install: the Debian targets' net_require doesn't apply
    job = Job(a)
    result = {"target": a.target, "vmid": a.vmid, "out": a.out, "started": job.started.isoformat(),
              "disk": os.path.abspath(a.disk), "stored": {k: meta.get(k) for k in ("installed", "packages", "minutes")}}
    created = False
    try:
        if vm_exists(a.vmid):
            raise InstallFailed(f"VM {a.vmid} exists already: lab.py boot-test never overwrites a VM")
        params = boot_test_vm_params(t, a, os.path.abspath(a.disk))
        job.log(f"creating VM {a.vmid} from a copy of {a.disk} (installed {meta.get('installed')})")
        run("pvesh", "create", f"/nodes/{node()}/qemu", *[x for k, val in params.items() for x in (f"--{k}", val)])
        created = True
        save_config(a.vmid, a.out)
        job.log(f"created VM {a.vmid} on {node()}")
        METHODS[t["method"]]().check(job)
        result.update(code=0, status="passed")
    except (InstallFailed, lab.QemuDied, lab.Timeout, OSError) as e:
        result.update(code=1, status=f"failed: {e}")
        job.log(f"FAILED: {e}")
    finally:
        if created:
            if a.keep:
                run("qm", "stop", a.vmid, check=False)
                job.log(f"VM {a.vmid} kept (--keep), stopped")
            else:
                destroy_vm(a.vmid)
                job.log(f"VM {a.vmid} destroyed")
    result.update(elapsed=round(time.time() - job.t0, 1), phases=job.phases)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\n== lab.py boot-test {a.target} -> VM {a.vmid}: {result['status']} in {result['elapsed'] / 60:.1f} min"
          f"\n   disk:     {a.disk} (installed {meta.get('installed')}, {meta.get('packages')})"
          f"\n   evidence: {a.out}")
    return result["code"]


# --- install methods -------------------------------------------------------------------------------

class MediaSwapper:
    """Changes media while an installer runs: for each (regex, drive, volume) in order, wait for the
    regex in the console output and then put the volume into the drive (lab.PveMachine.change_medium,
    i.e. `qm set`, live). Reads the serial output by cursor (Machine.serial_wait), so it doesn't move
    the scenario's own expect() position. A VM without a serial console (DOS) is followed on its VGA
    text screen instead (_run_vga); see README.md, "DOS install targets"."""

    def __init__(self, m, swaps, screen=None):
        self.m, self.swaps, self.done = m, list(swaps), []
        self.stop = threading.Event()
        # "vga": the prompts are on the VGA text screen (DOS), read by lab.Machine.vga_screen(); the
        # default follows the serial console, or the screen when the VM has none
        self.screen = screen or ("vga" if hasattr(m, "vga_screen") and not getattr(m, "ser", None) else "serial")
        self.cursor = m.serial_cursor() if self.screen == "serial" else 0  # only what comes from now on
        self.thread = threading.Thread(target=self._run_vga if self.screen == "vga" else self._run, daemon=True)
        self.thread.start()

    def _run_vga(self, interval=0.5):
        """The screen-text variant: a prompt is acted on when its regex matches the whole screen; the
        next regex is only looked for once the previous one no longer matches (the installer has moved
        on), so a prompt still on the screen is never acted on twice."""
        previous = None
        for pattern, drive, volume in self.swaps:
            rx = re.compile(pattern, re.M)
            while not self.stop.is_set():
                try:
                    s = self.m.vga_screen()
                except Exception:  # the VM went away: the scenario reports it
                    return
                text = s.text if s.text_mode else ""
                if previous and previous.search(text):
                    pass  # the last prompt is still up
                elif rx.search(text):
                    self.m.change_medium(drive, volume)
                    self.done.append((pattern, drive, volume))
                    previous = rx
                    break
                else:
                    previous = None
                self.stop.wait(interval)

    def _run(self):
        cursor = self.cursor
        for pattern, drive, volume in self.swaps:
            while not self.stop.is_set():
                try:
                    r = self.m.serial_wait(pattern, cursor, timeout=5)
                except Exception:  # the VM went away: the scenario reports it
                    return
                if r["matched"]:
                    cursor = r["cursor"]
                    self.m.change_medium(drive, volume)
                    self.done.append((pattern, drive, volume))
                    break
                cursor = max(cursor, r["cursor"] - 400)  # a prompt split across two reads still matches


class Scripted:
    """The installer answered on the console by a scenario (expect on the serial console or OCR of the
    framebuffer), then a first-boot scenario for the root password, the marker and the user."""

    def install(self, job):
        t = job.target
        # The installer always gets a static address (Solaris 2.6's has no DHCP choice); the first boot
        # turns it into DHCP, adds the netmask, the router and DNS (solaris-firstboot.py, NET_*)
        v = {**t["install"].get("vars", {}), "HOSTNAME": job.hostname, "IP": job.net["ip"] or DEFAULT_IP,
             "NETMASK": job.net["netmask"] or DEFAULT_NETMASK}
        # An installer with a DHCP choice of its own (Solaris 10: the scenario's DHCP variable) takes
        # --ip dhcp there
        if "DHCP" in v and job.net.get("mode") == "dhcp":
            v["DHCP"] = "yes"
        if t["install"].get("root_password"):  # the installer sets it (Web Start), not the first boot
            v["ROOT_PASSWORD"] = job.root_password
        if t["install"].get("prom_env"):
            set_prom_env(job.a.vmid, t["install"]["prom_env"])
        if t["install"].get("memory"):  # the install phase only (Job.finish sets the profile's again)
            run("qm", "set", job.a.vmid, "--memory", t["install"]["memory"])
            job.log(f"memory {t['install']['memory']} MB for the install phase")
        later =[(med["at"], med["drive"], drive_volume(med["drive"], job.volids[med["name"]]).removesuffix(",media=cdrom"))
                 for med in t["media"] if med.get("at", "start") != "start"]
        swaps = [s for s in later if s[0] != "scenario"]
        # "at": "scenario": the scenario inserts them in this order itself (prompts that don't say
        # which disk they want, e.g. FreeDOS's "Insert diskette containing file ...")
        v["SWAPS"] = " ".join(f"{drive}={vol}" for at, drive, vol in later if at == "scenario")
        # "retry_on": a failure that left the disk untouched (Solaris 10: a panic while the DVD boots)
        # gets one more try, its evidence in install-retry1/
        retry_on = t["install"].get("retry_on")
        for attempt in range(2 if retry_on else 1):
            try:
                job.phase("install" if not attempt else f"install-retry{attempt}", t["install"]["scenario"], v,
                          job.a.timeout or t["install"]["timeout"], swaps)
                return
            except InstallFailed as e:
                if attempt or not retry_on or not re.search(retry_on, str(e)) or vm_running(job.a.vmid):
                    raise
                job.log(f"install: {e}; trying once more")

    def firstboot(self, job):
        t = job.target
        v = {**t["firstboot"].get("vars", {}), "ROOT_PASSWORD": job.root_password, "MARKER": job.marker(),
             "USER": job.a.user or "", "USER_PASSWORD": job.user_password if job.a.user else "",
             "DATA_DISK": DATA_DISK_DEVICE if job.a.data_disk else "", "DATA_MOUNT": job.data_mount, **net_vars(job),
             "KEYBOARD": getattr(job.a, "keyboard", None) or "us", "NIC_NAME": job.nic}
        job.phase("firstboot", t["firstboot"]["scenario"], v, t["firstboot"]["timeout"])

    def check(self, job):
        t = job.target
        # The disk's layout as the guest sees it goes into the evidence (check/serial.raw)
        # (the target's check "commands", else Solaris's)
        v = {**t["check"].get("vars", {}), "ROOT_PASSWORD": job.root_password,
             "COMMANDS": t["check"].get("commands") or "uname -a; hostname; cat /etc/wsh-lab-target; df -k;"
                         f" prtvtoc /dev/rdsk/{t.get('device', 'c0t3d0')}s2; ifconfig -a; netstat -rn",
             "CHECK": rf"(?m)^target={re.escape(job.a.target)}$", "KEYBOARD": getattr(job.a, "keyboard", None) or "us"}
        dc = t.get("dhcp_check")
        if dc and job.net.get("mode") == "dhcp":
            # the lease and the network beyond it: every regex must match (lookaheads; the scenario
            # takes one regex, and an inline (?m) is only allowed at its start)
            v["COMMANDS"] += "; " + dc["commands"]
            v["CHECK"] = "(?m)" + "".join(f"(?=[\\s\\S]*?{rx.removeprefix('(?m)')})"
                                          for rx in [v["CHECK"], *dc["expect"]])
        if job.a.user:
            # without the password field: SunOS 4 keeps the hash in /etc/passwd itself
            v["COMMANDS"] += f"; grep '^{job.a.user}:' /etc/passwd | cut -d: -f1,3-"
        if job.a.data_disk:
            v["COMMANDS"] += f"; prtvtoc /dev/rdsk/{DATA_DISK_DEVICE}s2; df -k {job.data_mount}"
        if getattr(job.a, "post_install", None):
            v.update(post_install_checks(job))
        job.phase("check", t["check"]["scenario"], v, t["check"]["timeout"])


class Unattended(Scripted):
    """The installer reads its answers from a medium made on the node (answer_media.py: never from vendor
    files, nothing secret on it): written to the media storage as wsh-lab-answers-<vmid>.iso, put
    into the target's install "answers" drive for the install phase only, then the drive is removed
    and the image deleted, whatever the install did. The install scenario types the boot line and
    answers what the answer file leaves on the screen; first boot and check are Scripted's."""

    def install(self, job):
        a, ans = job.a, job.target["install"]["answers"]
        if "iso" not in (storage_content(a.media_storage) or {"iso"}):
            raise InstallFailed(f"storage {a.media_storage} has no iso content for the answer CD")
        volid = f"{a.media_storage}:iso/wsh-lab-answers-{a.vmid}.iso"
        path = run("pvesm", "path", volid)
        if os.path.exists(path):
            raise InstallFailed(f"{path} exists already (another install of VM {a.vmid}?)")
        n = job.net
        data = answer_media.image(ans["format"], n["ip"] or DEFAULT_IP, n["netmask"] or DEFAULT_NETMASK,
                                  n.get("gateway"), n.get("dns") or (), n.get("domain"), job.hostname,
                                  getattr(job, "apt_proxy", None))
        try:
            with open(path, "wb") as f:
                f.write(data)
            job.log(f"answer CD ({ans['format']}): {volid}, {len(data)} bytes, in {ans['drive']}")
            run("qm", "set", a.vmid, f"--{ans['drive']}", f"{volid},media=cdrom")
            save_config(a.vmid, a.out)
            super().install(job)
        finally:
            run("qm", "set", a.vmid, "--delete", ans["drive"], check=False)
            if os.path.exists(path):
                os.unlink(path)
            job.log(f"answer CD removed ({ans['drive']}, {volid})")


class PostInstall:
    """--post-install BUNDLE (targets.POST_INSTALL): after the first boot, the bundle's CD in its own
    drive for this phase only (removed again whatever the phase did, like Unattended's answer CD),
    then scenarios/solaris-post-install.py adds its packages onto the data disk and, with
    --local-env, sets up PATH and the user's login shell."""

    def run(self, job):
        a, b = job.a, targets.POST_INSTALL[job.a.post_install]
        volid = job.volids[b["medium"]]
        try:
            run("qm", "set", a.vmid, f"--{b['drive']}", f"{volid},media=cdrom")
            job.log(f"post-install {a.post_install}: {volid} in {b['drive']}")
            save_config(a.vmid, a.out)
            v = {"ROOT_PASSWORD": job.root_password, "BUNDLE": a.post_install, "CD": f"c0t{b['drive'][4:]}d0",
                 "DIR": b["dir"], "DATA_DISK": DATA_DISK_DEVICE, "BASEDIR": b["basedir"],
                 "USER": a.user or "", "LOCAL_ENV": "1" if a.local_env else "", "LOGIN_SHELL": b["shell"]}
            job.phase("postinstall", "solaris-post-install.py", v, b["timeout"])
        finally:
            run("qm", "set", a.vmid, "--delete", b["drive"], check=False)
            job.log(f"post-install CD removed ({b['drive']})")


def post_install_checks(job):
    """The --check boot's extra commands, each with the regex its output must have: BASEDIR is the
    data disk, the bundle's commands answer, pkginfo knows every package the post-install added; with
    --local-env root's PATH, root's shell still /sbin/sh, and the user's login shell and `which bash`.
    One command per console line (the tty takes 256 characters)."""
    a, b = job.a, targets.POST_INSTALL[job.a.post_install]
    base, pkgs = b["basedir"], f"/etc/wsh-lab-{a.post_install}.pkgs"
    pairs = [(f"df -k {base} | tail -1 | sed 's/^/df: /'", rf"df: /dev/dsk/{DATA_DISK_DEVICE}s0\s.*\s{re.escape(base)}[ \t]*$")]
    pairs += list(b["check"])
    pairs.append((f"n=0; for p in `cat {pkgs}`; do pkginfo -q $p && n=`expr $n + 1`; done;"
                  f" echo pkginfo knows $n of `cat {pkgs} | wc -w` packages", r"pkginfo knows ([1-9]\d*) of \1 packages"))
    if a.local_env:
        pairs += [("echo root PATH=$PATH", rf"root PATH=\S*:{re.escape(base)}/bin"),
                  ("grep '^root:' /etc/passwd | cut -d: -f1,7", r"(?m)^root:/sbin/sh[ \t]*$")]
        if a.user:
            pairs += [(f"grep '^{a.user}:' /etc/passwd | cut -d: -f1,7", rf"(?m)^{a.user}:{re.escape(b['shell'])}[ \t]*$"),
                      # su -c doesn't start a login shell: $SHELL (the user's) -l reads what a login reads
                      (f"su - {a.user} -c '$SHELL -l -c \"which bash\"' | sed 's/^/which: /'",
                       rf"which: {re.escape(b['shell'])}[ \t]*$")]
    return {"MORE_COMMANDS": "\n".join(c for c, _ in pairs), "MORE_EXPECT": "\n".join(rx for _, rx in pairs)}


def net_vars(job):
    """The network for the first-boot scenario (solaris-firstboot.py)."""
    n = job.net
    return {"NET_MODE": n["mode"], "NET_IP": n["ip"] or "", "NET_NETMASK": n["netmask"] or "",
            "NET_NETWORK": n.get("network") or "", "NET_GATEWAY": n["gateway"] or "",
            "NET_DNS": " ".join(n["dns"]), "NET_DOMAIN": n["domain"] or "", "HOSTNAME": job.hostname,
            "NET_IF": job.nic}


METHODS = {"scripted": Scripted, "unattended": Unattended}


class Job:
    """One `lab.py install` run."""

    def __init__(self, a):
        self.a = a
        self.target = targets.TARGETS[a.target]
        self.root_password = a.root_password or targets.DEFAULT_ROOT_PASSWORD
        self.user_password = a.user_password or self.root_password
        self.hostname = a.hostname or self.target["hostname"]
        self.disk = disk_choice(self.target, a.disk_size)
        self.data_mount = data_mount(a)
        self.net = network_choice(self.target, a)
        self.apt_proxy = apt_proxy_choice(self.target, getattr(a, "apt_proxy", None))
        self.started = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        self.t0 = time.time()
        self.phases = []
        self.volids, self.media = {}, []

    @property
    def nic(self):
        """What the guest calls its NIC (the target's `nic`, le0 for Solaris 2.x on sun4m)."""
        return self.target.get("nic", "le0")

    def net_text(self):
        return network_text(self.net, self.nic, self.target.get("dhcp_note"))

    def log(self, msg):
        line = f"[{time.time() - self.t0:7.1f}s] {msg}"
        print(line, flush=True)
        with open(os.path.join(self.a.out, "install.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def marker(self):
        t = self.target
        lines = [f"target={self.a.target}", f"title={t['title']}",
                 f"installed={self.started.isoformat().replace('+00:00', 'Z')}",
                 "by=wsh-pve e2e/sparc lab.py install", f"hostname={self.hostname}",
                 f"catalogue_tested={(t.get('tested') or {}).get('date', 'not yet')}"]
        lines += [f"medium={m['name']} sha256={m['sha256'] or 'unchecked'}" for m in self.media]
        lines.append(f"network={self.net_text()}")
        lines.append(f"disk={self.disk_text()}")
        if self.a.data_disk:
            lines.append(f"data_disk={DATA_DISK_DEVICE} {self.a.data_disk}G on {self.data_mount}")
        if getattr(self.a, "post_install", None):
            lines.append(f"post_install={self.a.post_install}" + (" local_env" if self.a.local_env else ""))
        if self.a.user:
            lines.append(f"user={self.a.user}")
        return "\n".join(lines)

    def disk_text(self):
        d = self.disk
        label = f", {d['geometry']['name']} label" if d.get("geometry") else ""
        return f"{d['name']} ({d['bus']}, {d['size']} GiB image{label})"

    def phase(self, name, scenario, v, timeout, swaps=()):
        """Run one scenario against the VM (lab.run_scenario in attach mode); a stall (no end within
        `timeout` s) stops the VM, which ends the scenario with the evidence kept."""
        out = os.path.join(self.a.out, name)
        stalled, extra = threading.Event(), {}

        def on_machine(m):
            def stall():
                stalled.set()
                m.log(f"no end within {timeout}s: stopping VM {self.a.vmid}")
                run("qm", "stop", self.a.vmid, check=False)
            extra["timer"] = threading.Timer(timeout, stall)
            extra["timer"].daemon = True
            extra["timer"].start()
            if swaps:
                extra["swapper"] = MediaSwapper(m, swaps)

        self.log(f"{name}: {os.path.basename(scenario)} (timeout {timeout}s), evidence in {out}")
        try:
            res = lab.run_scenario(os.path.join(SCENARIOS, scenario), out, {k: str(val) for k, val in v.items()},
                                   pve=self.a.vmid, on_machine=on_machine)
        except SystemExit as e:  # PveMachine: qm start failed, the console is taken, ...
            raise InstallFailed(f"{name}: {e}")
        finally:
            if "timer" in extra:
                extra["timer"].cancel()
            if "swapper" in extra:
                extra["swapper"].stop.set()
        if stalled.is_set():
            res = {**res, "code": 1, "status": f"stalled: no end within {timeout}s ({res['status'].splitlines()[0]})"}
        self.phases.append({"phase": name, "scenario": scenario, "code": res["code"],
                            "status": res["status"].splitlines()[0][:300], "elapsed": res["elapsed"], "out": out})
        self.log(f"{name}: {res['status'].splitlines()[0][:200]} ({res['elapsed']}s)")
        if res["code"]:
            raise InstallFailed(f"{name}: {res['status'].splitlines()[0][:300]}")
        if vm_running(self.a.vmid):
            raise InstallFailed(f"{name}: the VM is still running after the scenario")

    def description(self, failed=None):
        t, a = self.target, self.a
        login = t["login"]
        if failed:
            head = [f"FAILED wsh-lab install of {a.target}: {failed}", f"Evidence: {a.out}", ""]
        else:
            head = []
        lines = head + [
            f"wsh-lab target: {a.target} - {t['title']}",
            f"{'Install started' if failed else 'Installed'} {self.started:%Y-%m-%d %H:%M} UTC by lab.py install"
            " (wsh-pve e2e/sparc)",
            "",
            login_line(login, self.root_password),
        ]
        if a.user:
            lines.append(f"User: {a.user} / {self.user_password}")
        if login.get("password") is not False:
            lines.append("These passwords are public lab defaults (targets.py): change them before this VM is"
                         " reachable from anywhere untrusted.")
        lines += [
            f"Console: {login['console'].replace('<vmid>', str(a.vmid))}",
            f"Hostname: {self.hostname}",
            f"Network: {self.net_text()}",
            f"Disk: {self.disk_text()}" + (f"; data disk {DATA_DISK_DEVICE} ({DATA_DISK_BUS}) {a.data_disk} GiB on"
                                         f" {self.data_mount}" if a.data_disk else ""),
            f"Marker: {t.get('marker', '/etc/wsh-lab-target')}",
        ]
        if getattr(a, "post_install", None):
            lines.append(f"Post-install: {a.post_install} ({targets.POST_INSTALL[a.post_install]['title']})"
                         + ("; PATH in /etc/profile, the user's login shell bash (root's stays /sbin/sh)"
                            if a.local_env else ""))
        lines += [
            "Media: " + ", ".join(f"{m['name']} (sha256 {(m['sha256'] or 'unchecked')[:16]}...)" for m in self.media),
        ]
        return "\n".join(lines)

    def finish(self):
        """Eject the media and boot from the disk from now on."""
        for drive in dict.fromkeys(med["drive"] for med in self.target["media"]):
            lab.pve_set_medium(self.a.vmid, drive, "none")
        run("qm", "set", self.a.vmid, "--boot", f"order={self.target['boot']}")
        if self.target.get("install", {}).get("prom_env"):
            run("qm", "set", self.a.vmid, "--delete", "args")
            self.log("install-time prom_env removed (args)")
        if self.target.get("install", {}).get("memory"):
            run("qm", "set", self.a.vmid, "--memory", self.target["profile"]["memory"])
            self.log(f"memory {self.target['profile']['memory']} MB (the profile's) from now on")
        self.log(f"media ejected, boot order {self.target['boot']}")


def cmd_install(a):
    if a.target not in targets.TARGETS:
        sys.exit(f"unknown target {a.target!r}; `lab.py targets` lists them")
    t = targets.TARGETS[a.target]
    if t["status"] != "automated":
        sys.exit(f"{a.target} is in the catalogue only, not automated: {t['blocked']}")
    disk_choice(t, a.disk_size)  # refuses a size the target wasn't tested with
    network_choice(t, a)  # refuses a network setting the target doesn't support
    if a.data_disk is not None:
        if t.get("firstboot", {}).get("scenario") != "solaris-firstboot.py":
            sys.exit(f"--data-disk: only for the Solaris targets (their first boot sets it up), not {a.target}")
        if not 1 <= a.data_disk <= 32:
            sys.exit("--data-disk takes 1-32 (GiB)")
    check_post_install(a)
    problems = export_problems(a)  # before the install: a refused export mustn't cost hours first
    if problems:
        sys.exit("\n".join(problems))
    if not shutil.which("qm"):
        sys.exit("lab.py install runs on the PVE node (as root), where qm and pvesh are")
    for opt, rx in (("--root-password", PASSWORD), ("--user-password", PASSWORD), ("--user", USERNAME)):
        val = getattr(a, opt[2:].replace("-", "_"))
        if val and not rx.fullmatch(val):
            sys.exit(f"{opt} must match {rx.pattern}")
    a.vmid = str(a.vmid)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    a.out = os.path.abspath(a.out or os.path.join("/var/lib/wsh-lab/installs", f"{a.target}-{a.vmid}-{stamp}"))
    os.makedirs(a.out, exist_ok=True)
    job = Job(a)
    method = METHODS[t["method"]]()
    result = {"target": a.target, "vmid": a.vmid, "out": a.out, "started": job.started.isoformat()}
    created = False
    try:
        if vm_exists(a.vmid):
            raise InstallFailed(f"VM {a.vmid} exists already: lab.py install never overwrites a VM")
        names = [m["name"] for m in t["media"]]
        if a.post_install:  # checked up front with the target's: a missing CD fails before the install
            names.append(targets.POST_INSTALL[a.post_install]["medium"])
        job.media = check_media(names, storage=a.media_storage, checksum=True)
        for row in job.media:
            job.log(f"medium {row['name']}: {row['state']}" + (f" ({row['volid']})" if row["volid"] else ""))
        bad = [r for r in job.media if not r["ok"]]
        if any(r["note"] for r in bad):
            raise InstallFailed(next(r["note"] for r in bad if r["note"]))
        if any(r["state"] == "missing" for r in bad):
            raise InstallFailed("missing media: " + ", ".join(f"{a.media_storage}:{r['content']}/{r['name']}"
                                                             for r in bad if r["state"] == "missing"))
        if bad and not a.allow_untested_media:
            raise InstallFailed("not the tested media (" + "; ".join(f"{r['name']}: {r['state']}" for r in bad)
                                + "); --allow-untested-media to use them anyway")
        job.volids = {r["name"]: r["volid"] for r in job.media}
        create_vm(t, a, job.volids, a.out, job.disk)
        created = True
        job.log(f"created VM {a.vmid} ({a.name or a.target}) on {node()}")
        method.install(job)
        job.finish()
        if a.data_disk:
            add_data_disk(a, a.out)
            job.log(f"data disk: {a.data_disk} GiB on {DATA_DISK_BUS} ({DATA_DISK_DEVICE}), Sun-labelled")
        method.firstboot(job)
        if a.post_install:
            PostInstall().run(job)
        if a.check:
            method.check(job)
        run("qm", "set", a.vmid, "--description", job.description())
        if getattr(a, "export", None):
            result["stored"] = export_disk(job)
        if a.template:
            run("qm", "template", a.vmid)
            job.log(f"VM {a.vmid} is now a template")
        result.update(code=0, status="passed")
    except (InstallFailed, lab.QemuDied, lab.Timeout, OSError) as e:
        result.update(code=1, status=f"failed: {e}")
        job.log(f"FAILED: {e}")
        if created:
            if a.keep_on_failure:
                run("qm", "stop", a.vmid, check=False)
                run("qm", "set", a.vmid, "--description", job.description(failed=str(e)[:500]), check=False)
                job.log(f"VM {a.vmid} kept (--keep-on-failure), stopped")
            else:
                destroy_vm(a.vmid)
                job.log(f"VM {a.vmid} destroyed (--keep-on-failure keeps it)")
    result.update(elapsed=round(time.time() - job.t0, 1), phases=job.phases,
                  media=[{k: r[k] for k in ("name", "volid", "size", "sha256", "state")} for r in job.media])
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(summary(job, result))
    return result["code"]


def login_line(login, password):
    """The login line of the VM's notes; a DOS target has no login at all."""
    if login.get("password") is False:
        return "Login: none (no user and no password: the guest boots to its prompt)"
    return f"Login: {login['user']} / {password}"


def summary(job, result):
    a, t = job.a, job.target
    lines = ["", f"== lab.py install {a.target} -> VM {a.vmid}: {result['status']} in {result['elapsed'] / 60:.1f} min"]
    lines += [f"   {p['phase']:9} {p['elapsed']:7.0f}s  {p['status'][:100]}" for p in result["phases"]]
    if result["code"] == 0:
        lines += [("   login:    " + login_line(t["login"], job.root_password)[7:]
                   if t["login"].get("password") is False else
                   f"   login:    {t['login']['user']} / {job.root_password}"
                   + (f", {a.user} / {job.user_password}" if a.user else "") + "  (public lab defaults)"),
                  f"   console:  {t['login']['console'].replace('<vmid>', a.vmid)}",
                  f"   hostname: {job.hostname}; marker {t.get('marker', '/etc/wsh-lab-target')}",
                  f"   network:  {job.net_text()}",
                  f"   start:    qm start {a.vmid}" + ("  (a template: clone it first)" if a.template else "")]
    lines.append(f"   evidence: {a.out}")
    return "\n".join(lines)


def cmd_targets(a):
    if a.json:
        print(json.dumps(targets.TARGETS, indent=1, default=str))
        return 0
    print(f"{'target':20} {'status':10} {'machine':16} {'media':44} title")
    for name, t in targets.TARGETS.items():
        p = t["profile"]
        mach = f"{p.get('machine')} {p.get('memory')}M"
        media = ", ".join(m["name"] for m in t["media"])
        print(f"{name:20} {t['status']:10} {mach:16} {media[:44]:44} {t['title']}")
        if t["status"] == "automated":
            sizes = t["disk"].get("sizes") or [f"{t['disk']['size']}G"]
            print(f"{'':20} --disk-size {' | '.join(sizes)} (tested; default {sizes[0]})")
            bundles = [b for b, p in targets.POST_INSTALL.items() if name in p["targets"]]
            if bundles:
                print(f"{'':20} --post-install {' | '.join(bundles)} (with --data-disk; local media)")
        else:
            print(f"{'':20} blocked: {t['blocked']}")
    print(f"\nlogin of an installed target: root / {targets.DEFAULT_ROOT_PASSWORD} unless --root-password"
          " (public lab default)")
    return 0


def cmd_media(a):
    names = list(targets.TARGETS) if not a.target else [a.target]
    if a.target and a.target not in targets.TARGETS:
        sys.exit(f"unknown target {a.target!r}")
    if not a.dir and not shutil.which("pvesh"):
        sys.exit("lab.py media looks at a PVE storage (run it on the node) or a directory (--dir)")
    if a.convert:
        return media_convert(a)
    where = a.dir or f"storage {a.storage}"
    seen, bad = {}, 0
    for name in names:
        t = targets.TARGETS[name]
        print(f"{name} ({t['status']}):")
        for med in t["media"]:
            if med["name"] not in seen:
                seen[med["name"]] = check_media([med["name"]], storage=a.storage, directory=a.dir,
                                                checksum=not a.no_checksum)[0]
            r, exp = seen[med["name"]], targets.MEDIA[med["name"]]
            bad += t["status"] == "automated" and not r["ok"]
            where_found = r["volid"] or r["path"] or f"not in {where}"
            print(f"  {r['state']:17} {med['name']:46} {exp['size']:>11}  {exp['sha256']}  {where_found}")
            if "from" in exp and r["state"] == "missing":
                if "files" in exp["from"]:
                    print(f"  {'':17} made from {', '.join(exp['from']['files'])}: lab.py media {name} --convert"
                          " <the directory with them>")
                else:
                    print(f"  {'':17} made from {exp['from']['name']}: lab.py media {name} --convert <that file>")
    notes = sorted({r["note"] for r in seen.values() if r.get("note")})
    for n in notes:
        print(f"\n{n}")
    return 1 if bad else 0


def media_convert(a):
    """lab.py media <target> --convert SOURCE: the target's medium made from SOURCE (MEDIA "from": a
    medium, or a directory with the files a "files" medium is made of), written under its expected
    name into --dir or the storage's ISO directory."""
    if not a.target:
        sys.exit("--convert needs the target whose medium it makes")
    names = [m["name"] for m in targets.TARGETS[a.target]["media"] if "from" in targets.MEDIA[m["name"]]]
    if not names:
        sys.exit(f"{a.target}'s media are used as they are; nothing to convert")
    for name in names:
        med = targets.MEDIA[name]
        if a.dir:
            dest = os.path.join(a.dir, name)
        else:
            if med["content"] not in (storage_content(a.storage) or set()):
                sys.exit(f"storage {a.storage} has no {med['content']} content")
            dest = run("pvesm", "path", f"{a.storage}:{med['content']}/{name}")
        print(f"{name}: from {a.convert} ({med['from'].get('name') or 'its files'}, {med['from']['convert']}) to {dest}")
        try:
            digest = convert_medium(name, a.convert, dest)
        except (InstallFailed, OSError) as e:
            sys.exit(f"{name}: {e}")
        print(f"{name}: written, sha256 {digest} (the tested medium)")
    return 0


def add_commands(sub):
    i = sub.add_parser("install", help="install a target into a new PVE VM (on the node, as root)")
    i.add_argument("target")
    i.add_argument("--vmid", required=True, type=int)
    i.add_argument("--storage", default="local", help="storage for the VM's disk (local)")
    i.add_argument("--media-storage", default="local", help="storage with the install media (local)")
    i.add_argument("--bridge", default="vmbr0", help="bridge for the VM's NIC (vmbr0)")
    i.add_argument("--name", help="VM name (the target's name)")
    i.add_argument("--hostname", help="the guest's host name (the target's)")
    i.add_argument("--vlan", type=int, metavar="TAG", help="VLAN tag of the VM's NIC (net0 tag=; none)")
    i.add_argument("--ip", metavar="ADDRESS|dhcp",
                   help=f"the guest's static address ({DEFAULT_IP}), or dhcp where the target supports it")
    i.add_argument("--netmask", help=f"with a static address: its netmask ({DEFAULT_NETMASK})")
    i.add_argument("--gateway", help="with a static address: the default router (none)")
    i.add_argument("--dns", metavar="A[,B,C]", help="name servers: the guest resolves host names with DNS (none)")
    i.add_argument("--domain", help="the DNS domain (and search domain) of the guest, with --dns or DHCP")
    i.add_argument("--apt-proxy", metavar="URL",
                   help="targets that fetch packages during the install (Debian's netinst): an HTTP proxy for"
                        " them, e.g. an apt-cacher-ng (WSH_LAB_APT_PROXY; none: straight to the archive). At an"
                        " address on the guest's network it replaces --gateway and --dns")
    i.add_argument("--root-password", help=f"root's password ({targets.DEFAULT_ROOT_PASSWORD}: a public default)")
    i.add_argument("--user", help="also add this user (home under /export/home; NetBSD: /home)")
    i.add_argument("--user-password", help="the user's password (the root password)")
    i.add_argument("--disk-size", metavar="SIZE",
                   help="the first disk: one of the sizes the target was tested with (`targets` lists them; "
                        "Solaris 2.6: 3G, the default, or 9G)")
    i.add_argument("--data-disk", type=int, metavar="GIB",
                   help="also a second, Sun-labelled disk of 1-32 GiB on scsi4, newfs'd and mounted on /data "
                        "(or --data-mount)")
    i.add_argument("--data-mount", choices=DATA_MOUNTS,
                   help="with --data-disk: where it is mounted (/data; /usr/local with --post-install)")
    i.add_argument("--post-install", metavar="BUNDLE", choices=sorted(targets.POST_INSTALL),
                   help="Solaris: after the first boot, add a bundle's packages from its local CD onto the data "
                        "disk on /usr/local (sun26gnu: the owner's GNU package CD, sun26gnu.iso; needs --data-disk)")
    i.add_argument("--local-env", action="store_true",
                   help="with --post-install: /usr/local/bin and sbin on PATH (/etc/profile, the user's .profile), "
                        "MANPATH, and bash as --user's login shell (root keeps /sbin/sh)")
    i.add_argument("--check", action="store_true", help="boot once more, log in and check the marker")
    i.add_argument("--export", metavar="DIR",
                   help="with --check, when it passes: copy the first disk to DIR/install-<target>.raw (atomically,"
                        " sparse) with install-<target>.json saying what made it, for `boot-test` (e.g. /mnt/os/disks)")
    i.add_argument("--template", action="store_true", help="convert the VM to a template at the end")
    i.add_argument("--keep-on-failure", action="store_true", help="keep (stopped) instead of destroying a failed VM")
    i.add_argument("--allow-untested-media", action="store_true", help="accept media with another checksum")
    i.add_argument("--timeout", type=int, help="seconds the install phase may take (the target's)")
    i.add_argument("--keyboard", help="DOS targets: the keyboard layout KEYB loads, e.g. no (us: none)")
    i.add_argument("--out", help="evidence directory (/var/lib/wsh-lab/installs/<target>-<vmid>-<time>)")
    b = sub.add_parser("boot-test", help="boot a copy of a target's stored disk (install --export) in a new VM and"
                                         " run the target's check (on the node, as root)")
    b.add_argument("target")
    b.add_argument("--disk", required=True, help="the stored disk: <dir>/install-<target>.raw")
    b.add_argument("--vmid", required=True, type=int)
    b.add_argument("--storage", default="local", help="storage for the VM's copy of the disk (local)")
    b.add_argument("--bridge", default="vmbr0", help="bridge for the VM's NIC (vmbr0)")
    b.add_argument("--name", help="VM name (<target>-boot-test)")
    b.add_argument("--keep", action="store_true", help="keep the VM (stopped) instead of destroying it")
    b.add_argument("--out", help="evidence directory (/var/lib/wsh-lab/boot-tests/<target>-<vmid>-<time>)")
    t = sub.add_parser("targets", help="list the install targets")
    t.add_argument("--json", action="store_true")
    m = sub.add_parser("media", help="check the targets' media on a storage or in a directory")
    m.add_argument("target", nargs="?")
    m.add_argument("--storage", default="local")
    m.add_argument("--dir", help="look in this directory instead of a PVE storage")
    m.add_argument("--no-checksum", action="store_true", help="compare sizes only")
    m.add_argument("--convert", metavar="SOURCE",
                   help="make the target's converted medium from SOURCE (e.g. the SunOS CD from its raw BIN, "
                        "OpenBSD 5.9's sets CD from the release's directory), into --dir or the storage")


COMMANDS = {"install": cmd_install, "boot-test": cmd_boot_test, "targets": cmd_targets, "media": cmd_media}
