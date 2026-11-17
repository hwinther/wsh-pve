"""Install a named target (targets.py) into a new PVE VM, on the PVE node, as root:

    lab.py install sol26-ss5 --vmid 120 [--storage local] [--media-storage local] [--bridge vmbr0]
        [--name NAME] [--root-password PW] [--user NAME [--user-password PW]] [--hostname H] [--ip A]
        [--disk-size 3G|9G] [--data-disk GIB]
        [--check] [--template] [--keep-on-failure] [--allow-untested-media] [--timeout S] [--out DIR]
    lab.py targets [--json]
    lab.py media [<target>] [--storage local | --dir DIR] [--no-checksum]

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

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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
    the medium's type) or, with `directory`, as `<dir>/<name>` or `<dir>/<lab path>`."""
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
    if not any(c.get("volid") == volid for c in content or []):
        return None, None
    return volid, run("pvesm", "path", volid)


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
    if a.gateway:
        try:
            gw = ipaddress.IPv4Address(a.gateway)
        except ValueError as e:
            raise SystemExit(f"--gateway: {e}")
        if gw not in iface.network or gw == iface.ip:
            raise SystemExit(f"--gateway {gw} isn't another address in {iface.network}")
        net["gateway"] = str(gw)
    return net


def network_text(net, nic="le0"):
    """One line for the VM's notes and the summary."""
    where = f"bridge {net['bridge']}" + (f", VLAN {net['vlan']}" if net["vlan"] else "")
    if net["mode"] == "none":
        return f"none configured in the guest (the NIC is on {where})"
    if net["mode"] == "dhcp":
        s = f"{nic} by DHCP"
        extra = ["router, name servers and host name from the DHCP server (host name unknown if it sends none)"]
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


def drive_volume(drive, vol):
    """A medium's drive value for the VM config: CDs as media=cdrom, floppies read only (they are
    shared reference media; a written image no longer matches its sha256)."""
    return f"{vol},ro=1" if drive.startswith("floppy") else f"{vol},media=cdrom"


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
            p[med["drive"]] = drive_volume(med["drive"], vol)
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
        if t["install"].get("root_password"):  # the installer sets it (Web Start), not the first boot
            v["ROOT_PASSWORD"] = job.root_password
        if t["install"].get("prom_env"):
            set_prom_env(job.a.vmid, t["install"]["prom_env"])
        later = [(med["at"], med["drive"], drive_volume(med["drive"], job.volids[med["name"]]).removesuffix(",media=cdrom"))
                 for med in t["media"] if med.get("at", "start") != "start"]
        swaps = [s for s in later if s[0] != "scenario"]
        # "at": "scenario": the scenario inserts them in this order itself (prompts that don't say
        # which disk they want, e.g. FreeDOS's "Insert diskette containing file ...")
        v["SWAPS"] = " ".join(f"{drive}={vol}" for at, drive, vol in later if at == "scenario")
        job.phase("install", t["install"]["scenario"], v, job.a.timeout or t["install"]["timeout"], swaps)

    def firstboot(self, job):
        t = job.target
        v = {**t["firstboot"].get("vars", {}), "ROOT_PASSWORD": job.root_password, "MARKER": job.marker(),
             "USER": job.a.user or "", "USER_PASSWORD": job.user_password if job.a.user else "",
             "DATA_DISK": DATA_DISK_DEVICE if job.a.data_disk else "", **net_vars(job),
             "KEYBOARD": getattr(job.a, "keyboard", None) or "us"}
        job.phase("firstboot", t["firstboot"]["scenario"], v, t["firstboot"]["timeout"])

    def check(self, job):
        t = job.target
        # The disk's layout as the guest sees it goes into the evidence (check/serial.raw)
        v = {**t["check"].get("vars", {}), "ROOT_PASSWORD": job.root_password,
             "COMMANDS": "uname -a; hostname; cat /etc/wsh-lab-target; df -k; prtvtoc /dev/rdsk/c0t3d0s2;"
                         " ifconfig -a; netstat -rn",
             "CHECK": rf"(?m)^target={re.escape(job.a.target)}$", "KEYBOARD": getattr(job.a, "keyboard", None) or "us"}
        if job.a.user:
            v["COMMANDS"] += f"; grep '^{job.a.user}:' /etc/passwd"
        if job.a.data_disk:
            v["COMMANDS"] += f"; prtvtoc /dev/rdsk/{DATA_DISK_DEVICE}s2; df -k /data"
        job.phase("check", t["check"]["scenario"], v, t["check"]["timeout"])


def net_vars(job):
    """The network for the first-boot scenario (solaris-firstboot.py)."""
    n = job.net
    return {"NET_MODE": n["mode"], "NET_IP": n["ip"] or "", "NET_NETMASK": n["netmask"] or "",
            "NET_NETWORK": n.get("network") or "", "NET_GATEWAY": n["gateway"] or "",
            "NET_DNS": " ".join(n["dns"]), "NET_DOMAIN": n["domain"] or "", "HOSTNAME": job.hostname}


METHODS = {"scripted": Scripted}


class Job:
    """One `lab.py install` run."""

    def __init__(self, a):
        self.a = a
        self.target = targets.TARGETS[a.target]
        self.root_password = a.root_password or targets.DEFAULT_ROOT_PASSWORD
        self.user_password = a.user_password or self.root_password
        self.hostname = a.hostname or self.target["hostname"]
        self.disk = disk_choice(self.target, a.disk_size)
        self.net = network_choice(self.target, a)
        self.started = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        self.t0 = time.time()
        self.phases = []
        self.volids, self.media = {}, []

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
        lines.append(f"network={network_text(self.net)}")
        lines.append(f"disk={self.disk_text()}")
        if self.a.data_disk:
            lines.append(f"data_disk={DATA_DISK_DEVICE} {self.a.data_disk}G on /data")
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
            f"Network: {network_text(self.net)}",
            f"Disk: {self.disk_text()}" + (f"; data disk {DATA_DISK_DEVICE} ({DATA_DISK_BUS}) {a.data_disk} GiB on /data"
                                         if a.data_disk else ""),
            f"Marker: {t.get('marker', '/etc/wsh-lab-target')}",
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
        if a.check:
            method.check(job)
        run("qm", "set", a.vmid, "--description", job.description())
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
                  f"   network:  {network_text(job.net)}",
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
    notes = sorted({r["note"] for r in seen.values() if r.get("note")})
    for n in notes:
        print(f"\n{n}")
    return 1 if bad else 0


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
    i.add_argument("--root-password", help=f"root's password ({targets.DEFAULT_ROOT_PASSWORD}: a public default)")
    i.add_argument("--user", help="also add this user (home under /export/home)")
    i.add_argument("--user-password", help="the user's password (the root password)")
    i.add_argument("--disk-size", metavar="SIZE",
                   help="the first disk: one of the sizes the target was tested with (`targets` lists them; "
                        "Solaris 2.6: 3G, the default, or 9G)")
    i.add_argument("--data-disk", type=int, metavar="GIB",
                   help="also a second, Sun-labelled disk of 1-32 GiB on scsi4, newfs'd and mounted on /data")
    i.add_argument("--check", action="store_true", help="boot once more, log in and check the marker")
    i.add_argument("--template", action="store_true", help="convert the VM to a template at the end")
    i.add_argument("--keep-on-failure", action="store_true", help="keep (stopped) instead of destroying a failed VM")
    i.add_argument("--allow-untested-media", action="store_true", help="accept media with another checksum")
    i.add_argument("--timeout", type=int, help="seconds the install phase may take (the target's)")
    i.add_argument("--keyboard", help="DOS targets: the keyboard layout KEYB loads, e.g. no (us: none)")
    i.add_argument("--out", help="evidence directory (/var/lib/wsh-lab/installs/<target>-<vmid>-<time>)")
    t = sub.add_parser("targets", help="list the install targets")
    t.add_argument("--json", action="store_true")
    m = sub.add_parser("media", help="check the targets' media on a storage or in a directory")
    m.add_argument("target", nargs="?")
    m.add_argument("--storage", default="local")
    m.add_argument("--dir", help="look in this directory instead of a PVE storage")
    m.add_argument("--no-checksum", action="store_true", help="compare sizes only")


COMMANDS = {"install": cmd_install, "targets": cmd_targets, "media": cmd_media}
