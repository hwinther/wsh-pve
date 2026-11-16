"""Install a named target (targets.py) into a new PVE VM, on the PVE node, as root:

    lab.py install sol26-ss5 --vmid 120 [--storage local] [--media-storage local] [--bridge vmbr0]
        [--name NAME] [--root-password PW] [--user NAME [--user-password PW]] [--hostname H] [--ip A]
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


def find_medium(name, storage=None, directory=None):
    """(volume ID or None, local path or None) of the medium `name`: on a PVE storage (its content of
    the medium's type) or, with `directory`, as `<dir>/<name>` or `<dir>/<lab path>`."""
    med = targets.MEDIA[name]
    if directory:
        for rel in (name, med["lab"]):
            if os.path.isfile(os.path.join(directory, rel)):
                return None, os.path.join(directory, rel)
        return None, None
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
        volid, path = find_medium(name, storage, directory)
        row = {"name": name, "volid": volid, "path": path, "content": med["content"], "size": None,
               "sha256": None, "state": "missing", "ok": False}
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


def vm_params(t, a, volids, disk_image):
    """The options for `pvesh create /nodes/<node>/qemu`."""
    p = dict(t["profile"])
    p["net0"] = f"{p['net0']},bridge={a.bridge}"
    disk = t["disk"]
    if disk_image:
        p[disk["bus"]] = f"{a.storage}:0,import-from={disk_image},format=raw"
    else:
        p[disk["bus"]] = f"{a.storage}:{disk['size']},format=raw"
    for med in t["media"]:
        if med.get("at", "start") == "start":
            vol = volids[med["name"]]
            p[med["drive"]] = vol if med["drive"].startswith("floppy") else f"{vol},media=cdrom"
    p.update(vmid=a.vmid, name=a.name or a.target, tags="wsh-lab",
             description=f"wsh-lab install of {a.target} in progress (lab.py install)")
    return p


def create_vm(t, a, volids, work):
    disk_image = None
    if t["disk"].get("label") == "sun":
        disk_image = sunlabel.write_disk(os.path.join(work, "disk-label.raw"), t["disk"]["size"],
                                         t["disk"]["geometry"])
    try:
        params = vm_params(t, a, volids, disk_image)
        run("pvesh", "create", f"/nodes/{node()}/qemu", *[x for k, val in params.items() for x in (f"--{k}", val)])
    finally:
        if disk_image and os.path.exists(disk_image):
            os.unlink(disk_image)
    conf = run("qm", "config", a.vmid)
    with open(os.path.join(work, "vm.conf"), "w", encoding="utf-8") as f:
        f.write(conf + "\n")


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
    the scenario's own expect() position. A framebuffer console (DOS) would need a screen-text source
    instead; see README.md, "Install targets"."""

    def __init__(self, m, swaps):
        self.m, self.swaps, self.done = m, list(swaps), []
        self.stop = threading.Event()
        self.cursor = m.serial_cursor()  # only what the console prints from now on
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

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
        v = {**t["install"].get("vars", {}), "HOSTNAME": job.hostname, "IP": job.a.ip or "10.0.2.15"}
        swaps = [(med["at"], med["drive"], job.volids[med["name"]]) for med in t["media"]
                 if med.get("at", "start") != "start"]
        job.phase("install", t["install"]["scenario"], v, job.a.timeout or t["install"]["timeout"], swaps)

    def firstboot(self, job):
        t = job.target
        v = {**t["firstboot"].get("vars", {}), "ROOT_PASSWORD": job.root_password, "MARKER": job.marker(),
             "USER": job.a.user or "", "USER_PASSWORD": job.user_password if job.a.user else ""}
        job.phase("firstboot", t["firstboot"]["scenario"], v, t["firstboot"]["timeout"])

    def check(self, job):
        t = job.target
        v = {**t["check"].get("vars", {}), "ROOT_PASSWORD": job.root_password,
             "COMMANDS": "uname -a; hostname; cat /etc/wsh-lab-target",
             "CHECK": rf"(?m)^target={re.escape(job.a.target)}$"}
        if job.a.user:
            v["COMMANDS"] += f"; grep '^{job.a.user}:' /etc/passwd"
        job.phase("check", t["check"]["scenario"], v, t["check"]["timeout"])


METHODS = {"scripted": Scripted}


class Job:
    """One `lab.py install` run."""

    def __init__(self, a):
        self.a = a
        self.target = targets.TARGETS[a.target]
        self.root_password = a.root_password or targets.DEFAULT_ROOT_PASSWORD
        self.user_password = a.user_password or self.root_password
        self.hostname = a.hostname or self.target["hostname"]
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
        if self.a.user:
            lines.append(f"user={self.a.user}")
        return "\n".join(lines)

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
            f"Login: {login['user']} / {self.root_password}",
        ]
        if a.user:
            lines.append(f"User: {a.user} / {self.user_password}")
        lines += [
            "These passwords are public lab defaults (targets.py): change them before this VM is reachable"
            " from anywhere untrusted.",
            f"Console: {login['console'].replace('<vmid>', str(a.vmid))}",
            f"Hostname: {self.hostname}",
            f"Network: {t['network'].replace('10.0.2.15', a.ip or '10.0.2.15')}",
            "Marker: /etc/wsh-lab-target",
            "Media: " + ", ".join(f"{m['name']} (sha256 {(m['sha256'] or 'unchecked')[:16]}...)" for m in self.media),
        ]
        return "\n".join(lines)

    def finish(self):
        """Eject the media and boot from the disk from now on."""
        for med in self.target["media"]:
            lab.pve_set_medium(self.a.vmid, med["drive"], "none")
        run("qm", "set", self.a.vmid, "--boot", f"order={self.target['boot']}")
        self.log(f"media ejected, boot order {self.target['boot']}")


def cmd_install(a):
    if a.target not in targets.TARGETS:
        sys.exit(f"unknown target {a.target!r}; `lab.py targets` lists them")
    t = targets.TARGETS[a.target]
    if t["status"] != "automated":
        sys.exit(f"{a.target} is in the catalogue only, not automated: {t['blocked']}")
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
        if any(r["state"] == "missing" for r in bad):
            raise InstallFailed("missing media: " + ", ".join(f"{a.media_storage}:{r['content']}/{r['name']}"
                                                             for r in bad if r["state"] == "missing"))
        if bad and not a.allow_untested_media:
            raise InstallFailed("not the tested media (" + "; ".join(f"{r['name']}: {r['state']}" for r in bad)
                                + "); --allow-untested-media to use them anyway")
        job.volids = {r["name"]: r["volid"] for r in job.media}
        create_vm(t, a, job.volids, a.out)
        created = True
        job.log(f"created VM {a.vmid} ({a.name or a.target}) on {node()}")
        method.install(job)
        job.finish()
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


def summary(job, result):
    a, t = job.a, job.target
    lines = ["", f"== lab.py install {a.target} -> VM {a.vmid}: {result['status']} in {result['elapsed'] / 60:.1f} min"]
    lines += [f"   {p['phase']:9} {p['elapsed']:7.0f}s  {p['status'][:100]}" for p in result["phases"]]
    if result["code"] == 0:
        lines += [f"   login:    {t['login']['user']} / {job.root_password}"
                  + (f", {a.user} / {job.user_password}" if a.user else "") + "  (public lab defaults)",
                  f"   console:  {t['login']['console'].replace('<vmid>', a.vmid)}",
                  f"   hostname: {job.hostname}; marker /etc/wsh-lab-target",
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
        if t["status"] != "automated":
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
    i.add_argument("--ip", help="the guest's address where the installer sets a static one (10.0.2.15)")
    i.add_argument("--root-password", help=f"root's password ({targets.DEFAULT_ROOT_PASSWORD}: a public default)")
    i.add_argument("--user", help="also add this user (home under /export/home)")
    i.add_argument("--user-password", help="the user's password (the root password)")
    i.add_argument("--check", action="store_true", help="boot once more, log in and check the marker")
    i.add_argument("--template", action="store_true", help="convert the VM to a template at the end")
    i.add_argument("--keep-on-failure", action="store_true", help="keep (stopped) instead of destroying a failed VM")
    i.add_argument("--allow-untested-media", action="store_true", help="accept media with another checksum")
    i.add_argument("--timeout", type=int, help="seconds the install phase may take (the target's)")
    i.add_argument("--out", help="evidence directory (/var/lib/wsh-lab/installs/<target>-<vmid>-<time>)")
    t = sub.add_parser("targets", help="list the install targets")
    t.add_argument("--json", action="store_true")
    m = sub.add_parser("media", help="check the targets' media on a storage or in a directory")
    m.add_argument("target", nargs="?")
    m.add_argument("--storage", default="local")
    m.add_argument("--dir", help="look in this directory instead of a PVE storage")
    m.add_argument("--no-checksum", action="store_true", help="compare sizes only")


COMMANDS = {"install": cmd_install, "targets": cmd_targets, "media": cmd_media}
