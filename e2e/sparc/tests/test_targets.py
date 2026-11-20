"""The install target catalogue (targets.py) and the parts of install.py that need no PVE node: every
target's profile fits qemu-server's profile tables (read from submodules/qemu-server.patch when the
repository is there), names are unique, the Sun label is the lab template's, the VM options, the
media swapper and the masking of secrets in result.json. Standard library only:

    cd e2e/sparc && python3 -m unittest -v tests/test_targets.py
"""
import hashlib
import os
import re
import sys
import tempfile
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import install  # noqa: E402
import lab  # noqa: E402
import sunlabel  # noqa: E402
import targets  # noqa: E402

PATCH = os.path.join(HERE, "..", "..", "submodules", "qemu-server.patch")


def perl_block(text, start):
    """The text of a Perl hash literal that starts at the line `start` (to its closing `};`)."""
    i = text.index(start)
    return text[i:text.index("\n+};", i)]


def qemu_server_profiles():
    """$SPARC32_PROFILES, the sparc32 display list and $SPARC64_PROFILE from the qemu-server patch."""
    with open(PATCH, encoding="utf-8") as f:
        text = f.read()
    s32 = {}
    block = perl_block(text, "+our $SPARC32_PROFILES = {")
    for m in re.finditer(r"'(SS-\d+)' => \{\n\+\s+'max-memory' => (\d+),(.*?)\n\+    \},", block, re.S):
        fw = {f: {"max-cpus": int(n), "cpu": cpu}
              for f, cpu, n in re.findall(r"'([\w.-]+)' => \{ (?:cpu => '([\w-]+)', )?'max-cpus' => (\d+) \}", m[3])}
        s32[m[1]] = {"max-memory": int(m[2]), "firmware": fw}
    vga32 = re.search(r"my \$sparc32_vga_types = \[qw\(([^)]*)\)\]", text)[1].split()
    block = perl_block(text, "+our $SPARC64_PROFILE = {")
    s64 = {"machine": re.search(r"machine => '(\w+)'", block)[1],
           "firmware": re.search(r"firmware => '([\w-]+)'", block)[1],
           "max-memory": int(re.search(r"'max-memory' => (\d+)", block)[1]),
           "vga": re.search(r"vga => \[qw\(([^)]*)\)\]", block)[1].split(),
           "nic": re.search(r"nic => \[qw\(([^)]*)\)\]", block)[1].split()}
    return s32, vga32, s64


class Catalogue(unittest.TestCase):
    def test_structure(self):
        self.assertEqual(targets.problems(), [])

    def test_names(self):
        rx = re.compile(r"[a-z][a-z0-9-]{1,30}[a-z0-9]")  # PVE VM names and host names
        for name, t in targets.TARGETS.items():
            self.assertRegex(name, rx)
            if t["login"].get("password") is not False:  # DOS targets have no host name
                self.assertRegex(t["hostname"], rx)
        self.assertEqual(len({n.lower() for n in targets.MEDIA}), len(targets.MEDIA), "file names unique")
        self.assertEqual(len({m["lab"] for m in targets.MEDIA.values()}), len(targets.MEDIA))
        for name, med in targets.MEDIA.items():
            self.assertNotIn("/", name)
            self.assertRegex(name, r"\.(iso|img|ima|vfd)$")
        self.assertTrue(set(targets.automated()) >= {"sol26-ss5", "sol26-ss20"})

    def test_default_password(self):
        self.assertRegex(targets.DEFAULT_ROOT_PASSWORD, install.PASSWORD)

    @unittest.skipUnless(os.path.exists(PATCH), "needs the repository's submodules/qemu-server.patch")
    def test_profiles(self):
        s32, vga32, s64 = qemu_server_profiles()
        self.assertEqual(set(s32), {"SS-5", "SS-10", "SS-20"})  # the parser found the table
        self.assertEqual(s32["SS-20"]["firmware"]["ss20_v2.25_rom"]["cpu"], "TI-SuperSparc-50")
        for name, t in targets.TARGETS.items():
            p, disk = t["profile"], t["disk"]
            if p.get("arch", "x86_64") not in ("sparc", "sparc64"):
                continue  # x86 (DOS): tests/test_dos.py
            with self.subTest(target=name):
                cpus = int(p.get("sockets", 1)) * int(p.get("cores", 1))
                self.assertNotIn("cpu", p)
                if p["arch"] == "sparc":
                    prof = s32[p["machine"].split(",")[0]]  # the type, without machine options
                    self.assertIn(p["bios"], prof["firmware"])
                    self.assertLessEqual(int(p["memory"]), prof["max-memory"])
                    self.assertLessEqual(cpus, prof["firmware"][p["bios"]]["max-cpus"])
                    self.assertIn(p["vga"], vga32)
                    self.assertEqual(p["net0"], "lance")
                    self.assertEqual(disk["bus"], "scsi3")  # the PROMs boot target 3
                    # the CD-ROM on target 6; a second CD (OpenBSD 5.9's sets) on 5, after the disk
                    self.assertEqual(t["media"][0]["drive"], "scsi6")
                    self.assertTrue(all(m["drive"] in ("scsi6", "scsi5") for m in t["media"]))
                else:
                    self.assertEqual(p["arch"], "sparc64")
                    self.assertEqual(p["machine"], s64["machine"])
                    self.assertEqual(p["bios"], s64["firmware"])
                    self.assertLessEqual(int(p["memory"]), s64["max-memory"])
                    self.assertEqual(cpus, 1)
                    self.assertIn(p["vga"], s64["vga"])
                    self.assertIn(p["net0"], s64["nic"])
                    self.assertTrue(re.fullmatch(r"ide[0-3]", disk["bus"]))
                    self.assertTrue(all(re.fullmatch(r"ide[0-3]", m["drive"]) for m in t["media"]))
                self.assertEqual(t["boot"], disk["bus"])
                for key in ("serial0",):
                    self.assertEqual(p.get(key), "socket")  # the lab drives the serial console


# The templates' label sectors (the first 512 bytes of sparc-SUN2.9G.raw.template.xz and
# sparc-Qemu9G.raw.template.xz decompressed, as `xz -dc | head -c 512 | sha256sum` gives them) and
# every sector in the templates that isn't zero: the label at 0 and its five backup copies.
TEMPLATES = {
    "3G": {"label": "c0db810d2270f33fa53a075c37fe75cf13e6f71513b14eca07a8e5856a428d6e", "bytes": 3 << 30,
           "nonzero": [0, 5688046, 5688048, 5688050, 5688052, 5688054]},
    "9G": {"label": "a05ef673f547bffb212946f0b1185cd84210b7ecd993bbffea8be4e965425725", "bytes": 8 << 30,
           "nonzero": [0, 15555781, 15555783, 15555785, 15555787, 15555789]},
}


class Label(unittest.TestCase):
    def test_labels_are_the_templates(self):
        for name, tpl in TEMPLATES.items():
            with self.subTest(disk=name):
                d = targets.DISKS[name]
                self.assertEqual(hashlib.sha256(sunlabel.label(**d["geometry"])).hexdigest(), tpl["label"])
                self.assertEqual([0] + sunlabel.backup_sectors(**d["geometry"]), tpl["nonzero"])
                self.assertEqual(d["size"] << 30, tpl["bytes"])

    def test_images_are_the_templates(self):
        # the whole image: the label sector at each of the template's non-zero sectors, zeros elsewhere
        # (checked around them and by the file system's allocation: the image stays sparse)
        for name, tpl in TEMPLATES.items():
            d = targets.DISKS[name]
            path = os.path.join(tempfile.gettempdir(), f"label-test-{name}-{os.getpid()}.raw")
            try:
                sunlabel.write_disk(path, d["size"], d["geometry"])
                with self.subTest(disk=name), open(path, "rb") as f:
                    self.assertEqual(os.path.getsize(path), tpl["bytes"])
                    for s in tpl["nonzero"]:
                        f.seek(s * 512 - (512 if s else 0))
                        before = f.read(512) if s else b""
                        sector = f.read(512)
                        after = f.read(512)
                        self.assertEqual(hashlib.sha256(sector).hexdigest(), tpl["label"])
                        self.assertEqual(before + after, bytes(len(before) + len(after)))
                    if hasattr(os.stat_result, "st_blocks"):
                        self.assertLess(os.stat(path).st_blocks * 512, 1 << 20)  # sparse
            finally:
                os.unlink(path)

    def test_sun29g_is_the_template(self):
        # the first MiB of sparc-SUN2.9G.raw.template.xz decompressed (the label, then zeros)
        d = bytearray(1 << 20)
        d[:512] = sunlabel.label(**targets.SUN29G)
        self.assertEqual(hashlib.sha256(d).hexdigest(),
                         "8d742a0f178d42f87509967b20cbc40b3a4351ffb99c3fcb94e832cf5378d599")

    def test_checksum_and_disk(self):
        d = sunlabel.label(**targets.SUN29G)
        ck = 0
        for i in range(0, 512, 2):
            ck ^= int.from_bytes(d[i:i + 2], "big")
        self.assertEqual(ck, 0)  # the XOR over all 256 words, the checksum included
        self.assertEqual(d[508:510], b"\xda\xbe")
        path = os.path.join(tempfile.gettempdir(), f"label-test-{os.getpid()}.raw")
        try:
            sunlabel.write_disk(path, 3, targets.SUN29G)
            self.assertEqual(os.path.getsize(path), 3 << 30)
            with open(path, "rb") as f:
                self.assertEqual(f.read(512), d)
        finally:
            os.unlink(path)


class DiskSizes(unittest.TestCase):
    def test_tested_sizes(self):
        self.assertEqual(targets.TARGETS["sol26-ss5"]["disk"]["sizes"], ["3G", "9G"])
        self.assertEqual(targets.TARGETS["sol26-ss20"]["disk"]["sizes"], ["3G", "9G"])
        # Solaris 7: 9G tested 2026-11-18 on both; 3G stays the default (End User fits, as on 2.6)
        self.assertEqual(targets.TARGETS["sol7-ss5"]["disk"]["sizes"], ["3G", "9G"])
        self.assertEqual(targets.TARGETS["sol7-ss20"]["disk"]["sizes"], ["3G", "9G"])

    def test_choice(self):
        t = targets.TARGETS["sol26-ss5"]
        self.assertEqual(install.disk_choice(t, None)["name"], "3G")
        nine = install.disk_choice(t, "9G")
        self.assertEqual((nine["size"], nine["geometry"]["name"]), (8, "QEmu8G"))
        for bad in ("8G", "4G", "9g"):
            with self.assertRaises(SystemExit) as e:
                install.disk_choice(t, bad)
            self.assertIn("3G, 9G", str(e.exception))
        with self.assertRaises(SystemExit):  # a target without a Sun label has no sizes
            install.disk_choice(targets.TARGETS["netbsd111-sparc64"], "9G")

    def test_vm_params_9g(self):
        t = targets.TARGETS["sol26-ss20"]
        a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="121", name=None, target="sol26-ss20")
        p = install.vm_params(t, a, {"solaris_2.6_598_sparc.iso": "local:iso/x.iso"}, None, install.disk_choice(t, "9G"))
        self.assertEqual(p["scsi3"], "local:8,format=raw")

    def test_sol7_choice(self):
        for name in ("sol7-ss5", "sol7-ss20"):
            t = targets.TARGETS[name]
            self.assertEqual(install.disk_choice(t, None)["name"], "3G")
            nine = install.disk_choice(t, "9G")
            self.assertEqual((nine["size"], nine["geometry"]["name"]), (8, "QEmu8G"))
            a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="122", name=None, target=name)
            p = install.vm_params(t, a, {"Sol7.399InstallationSparc.iso": "local:iso/x.iso"}, None, nine)
            self.assertEqual(p["scsi3"], "local:8,format=raw")

    def test_data_disk_label(self):
        for gib in (1, 4, 32):
            g = sunlabel.data_geometry(gib)
            d = sunlabel.label(**g)
            ck = 0
            for i in range(0, 512, 2):
                ck ^= int.from_bytes(d[i:i + 2], "big")
            self.assertEqual(ck, 0)
            self.assertLessEqual(g["ncyl"] + g["acyl"], 65535)  # 16-bit cylinder counts
            self.assertEqual((g["ncyl"] + g["acyl"]) * g["heads"] * g["sectors"] * 512, gib << 30)
            self.assertEqual(g["parts"][0][3], g["ncyl"] * g["heads"] * g["sectors"])  # slice 0: all data cylinders
        for bad in (0, 33):
            with self.assertRaises(ValueError):
                sunlabel.data_geometry(bad)


def net_args(**kw):
    a = dict(target="sol26-ss5", bridge="vmbr0", vlan=None, ip=None, netmask=None, gateway=None, dns=None, domain=None)
    a.update(kw)
    return types.SimpleNamespace(**a)


class Network(unittest.TestCase):
    t = targets.TARGETS["sol26-ss5"]

    def test_default(self):
        n = install.network_choice(self.t, net_args())
        self.assertEqual((n["mode"], n["ip"], n["netmask"], n["gateway"], n["dns"]),
                         ("static", "10.0.2.15", "255.255.255.0", None, []))
        self.assertEqual(install.network_text(n),
                         "le0 10.0.2.15/24 (netmask 255.255.255.0), static; no default route; no name service"
                         " (bridge vmbr0)")

    def test_static_full(self):
        n = install.network_choice(self.t, net_args(ip="192.168.40.7", netmask="255.255.252.0", gateway="192.168.41.1",
                                                    dns="192.168.40.2, 1.1.1.1", domain="Lab.Example", vlan=40))
        self.assertEqual((n["network"], n["prefix"], n["gateway"], n["dns"], n["domain"], n["vlan"]),
                         ("192.168.40.0", 22, "192.168.41.1", ["192.168.40.2", "1.1.1.1"], "lab.example", 40))
        self.assertIn("VLAN 40", install.network_text(n))

    def test_dhcp(self):
        n = install.network_choice(self.t, net_args(ip="DHCP"))
        self.assertEqual((n["mode"], n["ip"]), ("dhcp", None))
        self.assertTrue(install.network_text(n).startswith("le0 by DHCP"))

    def test_refusals(self):
        for kw, msg in ((dict(ip="10.0.0.300"), "--ip"), (dict(netmask="255.0.255.0"), "--ip/--netmask"),
                        (dict(gateway="10.0.3.1"), "isn't another address"), (dict(gateway="10.0.2.15"), "isn't another"),
                        (dict(ip="10.0.2.0"), "network's or broadcast"), (dict(dns="a.b.c.d"), "--dns"),
                        (dict(dns="1.1.1.1,1.0.0.1,8.8.8.8,9.9.9.9"), "at most 3"), (dict(domain="lab.test"), "needs --dns"),
                        (dict(dns="1.1.1.1", domain="bad_domain"), "not a domain"), (dict(vlan=4095), "1-4094"),
                        (dict(ip="dhcp", gateway="10.0.2.2"), "come from the DHCP server")):
            with self.subTest(**kw), self.assertRaises(SystemExit) as e:
                install.network_choice(self.t, net_args(**kw))
            self.assertIn(msg, str(e.exception))

    def test_unsupported_mode_is_refused(self):
        t = {**self.t, "net_modes": ["static"]}
        with self.assertRaises(SystemExit) as e:
            install.network_choice(t, net_args(ip="dhcp"))
        self.assertIn("supports static", str(e.exception))

    def test_every_automated_target_says_what_it_supports(self):
        for name in targets.automated():
            modes = targets.TARGETS[name]["net_modes"]
            # "none": the guest configures no network (the DOS targets, tests/test_dos.py)
            self.assertTrue(set(modes) <= {"static", "dhcp"} or modes == ["none"], name)

    def test_netmasks_by_classful_network(self):
        # Solaris 2.6 looks /etc/netmasks up by the class A/B/C network number
        sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-firstboot.py"))
        self.assertEqual([sc.classful(x) for x in ("10.0.2.15", "172.16.5.4", "192.168.40.7")],
                         ["10.0.0.0", "172.16.0.0", "192.168.40.0"])

    def test_vlan_in_net0(self):
        a = types.SimpleNamespace(bridge="vmbr1", vlan=20, storage="local", vmid="1", name=None, target="sol26-ss5")
        p = install.vm_params(self.t, a, {"solaris_2.6_598_sparc.iso": "local:iso/x.iso"}, None)
        self.assertEqual(p["net0"], "lance,bridge=vmbr1,tag=20")


class VmParams(unittest.TestCase):
    def test_sol26_ss5(self):
        a = types.SimpleNamespace(bridge="vmbr1", storage="tank", vmid="120", name=None, target="sol26-ss5")
        p = install.vm_params(targets.TARGETS["sol26-ss5"], a, {"solaris_2.6_598_sparc.iso": "local:iso/x.iso"},
                              "/work/disk-label.raw")
        self.assertEqual(p["scsi3"], "tank:0,import-from=/work/disk-label.raw,format=raw")
        self.assertEqual(p["scsi6"], "local:iso/x.iso,media=cdrom")
        self.assertEqual(p["net0"], "lance,bridge=vmbr1")
        self.assertEqual((p["arch"], p["machine"], p["bios"], p["memory"]), ("sparc", "SS-5", "openbios-sparc32", 256))
        self.assertEqual((p["name"], p["vmid"], p["tags"]), ("sol26-ss5", "120", "wsh-lab"))

    def test_cd_as_disk(self):
        # Solaris 2.2-2.5.1: the CD-ROM answers as a disk (qemu-server's cd_as_disk); 2.5.1 under a Sun
        # PROM, 2.2-2.5 under OpenBIOS (2.2-2.4 with openbios 0019-0022)
        for name, iso, bios in (("sol251-ss5", "solaris_2.5.1_1197.iso", "ss5.bin"),
                                ("sol24-ss5", "solaris_2.4_sparc.iso", "openbios-sparc32"),
                                ("sol24-ss20", "solaris_2.4_sparc.iso", "openbios-sparc32"),
                                ("sol23-ss5", "Solaris2.3Edition-II.iso", "openbios-sparc32"),
                                ("sol23-ss20", "Solaris2.3Edition-II.iso", "openbios-sparc32"),
                                ("sol22-ss10", "Solaris_2.2.img", "openbios-sparc32"),
                                ("sol25-ss5", "solaris2.5_sparc.iso", "openbios-sparc32"),
                                ("sol25-ss20", "solaris2.5_sparc.iso", "openbios-sparc32"),
                                ("sol251-ss20", "solaris_2.5.1_1197.iso", "openbios-sparc32")):
            a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="1", name=None, target=name)
            p = install.vm_params(targets.TARGETS[name], a, {iso: f"local:iso/{iso}"}, None)
            self.assertEqual(p["scsi6"], f"local:iso/{iso},media=cdrom,cd_as_disk=1")
            self.assertEqual(p["bios"], bios)
        self.assertEqual(install.drive_volume("scsi6", "local:iso/x.iso"), "local:iso/x.iso,media=cdrom")
        # as_disk only where qemu-server takes it: a sparc32 SCSI CD-ROM, inserted at the start
        saved = targets.TARGETS["sol26-ss5"]
        try:
            for med in ({"drive": "ide2", "as_disk": True}, {"drive": "scsi6", "as_disk": True, "at": "scenario"}):
                targets.TARGETS["sol26-ss5"] = {**saved, "media": [{"name": "solaris_2.6_598_sparc.iso", **med}]}
                self.assertTrue(any("as_disk" in p for p in targets.problems()), med)
        finally:
            targets.TARGETS["sol26-ss5"] = saved
        # what pve_vars() tells the scenarios (CDROM_AS), from the drive as `qm config` prints it
        for drive, want in (("local:iso/x.iso,cd_as_disk=1,media=cdrom,size=1M", "hd"),
                            ("none,cd_as_disk=1,media=cdrom", "cd"), ("local:iso/x.iso,media=cdrom", "cd"),
                            ("local:1/vm-1-disk-1.raw,ro=1,backup=0", "hd")):
            self.assertEqual(lab.pve_cdrom_as(drive), want, drive)

    def test_later_media_are_not_attached_at_the_start(self):
        t = targets.TARGETS["sol8-ss20"]
        vols = {m["name"]: f"local:iso/{m['name']}" for m in t["media"]}
        p = install.vm_params(t, types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="1", name="x",
                                                       target="sol8-ss20"), vols, None)
        self.assertEqual(p["scsi6"], "local:iso/sun-solaris-8-0101-installation-sparc.iso,media=cdrom")
        self.assertEqual(p["scsi3"], "local:8,format=raw")


class FakeScreen:
    """What the Solaris 10 installer's screen handlers use of a Machine: the screen, keys and text."""

    def __init__(self, screen):
        self.screen, self.typed = screen, []

    def screen_text(self):
        return self.screen

    def key(self, *names):
        self.typed += names

    def send(self, text):
        self.typed.append(text)


class Solaris10(unittest.TestCase):
    t = targets.TARGETS["sol10-sun4u"]
    sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris10-install-sparc64.py"))

    def test_vm_params(self):
        a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="130", name=None, target="sol10-sun4u")
        p = install.vm_params(self.t, a, {"sol-10-u11-ga-sparc-dvd.iso": "local:iso/sol10.iso"}, None)
        self.assertEqual((p["ide0"], p["ide2"]), ("local:16,format=raw", "local:iso/sol10.iso,media=cdrom"))
        self.assertEqual((p["arch"], p["memory"], p["net0"]), ("sparc64", 1024, "sunhme,bridge=vmbr0"))

    def test_network_text_names_hme0(self):
        n = install.network_choice(self.t, net_args(target="sol10-sun4u"))
        self.assertTrue(install.network_text(n, self.t["nic"]).startswith("hme0 10.0.2.15/24"))
        with self.assertRaises(SystemExit):
            install.network_choice(self.t, net_args(target="sol10-sun4u", ip="dhcp"))

    def test_select_moves_from_the_marked_choice(self):
        m = FakeScreen("  Default Route for hme0\n      [X] Detect one\n      [ ] Specify one\n      [ ] None\n")
        self.sc.select(m, "None")
        self.assertEqual(m.typed, ["ctrl-n", "ctrl-n", "\r"])
        m = FakeScreen("      [ ] Yes\n      [X] No\n")
        self.sc.select(m, "No")
        self.assertEqual(m.typed, [])

    def test_install_retries_an_early_panic_once(self):
        class Job:
            target, volids, net = self.t, {}, {"ip": "10.0.2.15", "netmask": "255.255.255.0"}
            hostname, root_password, a = "sol10-sun4u", "wshlab", types.SimpleNamespace(timeout=None, vmid="1")

            def __init__(self, failures):
                self.failures, self.phases, self.logs = list(failures), [], []

            def phase(self, name, scenario, v, timeout, swaps=()):
                self.phases.append((name, v["ROOT_PASSWORD"]))
                if self.failures:
                    raise install.InstallFailed(f"{name}: error: AssertionError: {self.failures.pop(0)}")

            def log(self, msg):
                self.logs.append(msg)

        orig, install.vm_running = install.vm_running, lambda vmid: False
        try:
            job = Job(["before the installer: kernel panic while booting the DVD"])
            install.Scripted().install(job)
            self.assertEqual(job.phases, [("install", "wshlab"), ("install-retry1", "wshlab")])
            job = Job(["before the installer: panic"] * 2)
            with self.assertRaises(install.InstallFailed):
                install.Scripted().install(job)
            self.assertEqual(len(job.phases), 2)
            job = Job(["kernel panic during the install"])  # the disk may be half written: no retry
            with self.assertRaises(install.InstallFailed):
                install.Scripted().install(job)
            self.assertEqual(len(job.phases), 1)
        finally:
            install.vm_running = orig

    def test_netmask_kept_or_replaced(self):
        screen = "                    Netmask for hme0 255.255.255.0\n"
        m = FakeScreen(screen)
        self.sc.netmask(m, {"NETMASK": "255.255.255.0"})
        self.assertEqual(m.typed, [])
        m = FakeScreen(screen)
        self.sc.netmask(m, {"NETMASK": "255.255.252.0"})
        self.assertEqual(m.typed, ["backspace"] * 13 + ["255.255.252.0"])


class FakeConsole:
    """What MediaSwapper uses of a Machine: the serial output by cursor and change_medium()."""

    def __init__(self):
        self.text, self.changes, self.cond = "", [], threading.Condition()

    def feed(self, s):
        with self.cond:
            self.text += s
            self.cond.notify_all()

    def serial_cursor(self):
        return len(self.text)

    def serial_wait(self, pattern, cursor=None, timeout=60):
        end = time.time() + timeout
        with self.cond:
            while True:
                m = re.compile(pattern, re.M).search(self.text, cursor or 0)
                if m:
                    return {"matched": True, "cursor": m.end()}
                if time.time() > end:
                    return {"matched": False, "cursor": len(self.text)}
                self.cond.wait(0.05)

    def change_medium(self, drive, volume):
        self.changes.append((drive, volume))


class Swapper(unittest.TestCase):
    def test_in_order_once_each(self):
        c = FakeConsole()
        c.feed("old output: Please insert Software 1 of 2\n")  # before the swapper: ignored
        s = install.MediaSwapper(c, [(r"insert Software 1 of 2", "scsi6", "local:iso/cd1.iso"),
                                     (r"insert Software 2 of 2", "scsi6", "local:iso/cd2.iso")])
        c.feed("installing...\nPlease insert Software 2 of 2\n")  # out of order: waits for disc 1 first
        c.feed("Please insert Software 1 of 2\n")
        time.sleep(0.5)
        c.feed("Please insert Software 2 of 2\n")
        s.thread.join(5)
        s.stop.set()
        self.assertEqual(c.changes, [("scsi6", "local:iso/cd1.iso"), ("scsi6", "local:iso/cd2.iso")])


class Masking(unittest.TestCase):
    def test_secrets(self):
        v = lab.masked({"ROOT_PASSWORD": "wshlab", "USER_PASSWORD": "x", "PRODUCT_KEY": "AAAA", "USER": "lab",
                        "MARKER": "target=x", "EMPTY_PASSWORD": ""})
        self.assertEqual(v, {"ROOT_PASSWORD": "***", "USER_PASSWORD": "***", "PRODUCT_KEY": "***", "USER": "lab",
                             "MARKER": "target=x", "EMPTY_PASSWORD": ""})


class SolarisEarlyHang(unittest.TestCase):
    """solaris-install-serial.py: a CD boot that hangs between the kernel banner and the first prompt
    (sol23-ss20 in install matrix run 44533778163: QEMU's ESP deadlock) fails after
    FIRST_PROMPT_TIMEOUT with "before the installer", which the targets retry once."""

    def test_scenario_fails_early_with_the_retry_text(self):
        sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-install-serial.py"))
        self.assertEqual(sc.DEFAULTS["FIRST_PROMPT_TIMEOUT"], "300")
        waits = []

        class M:
            def expect(self, rx, timeout=300):
                return None

            def expect_any(self, patterns, timeout=300):
                waits.append(timeout)
                raise lab.Timeout(f"no prompt within {timeout}s")

            def snap(self, title):
                pass

        orig, sc.prom_boot = sc.prom_boot, lambda m, v, dev: None
        try:
            with self.assertRaises(AssertionError) as e:
                sc.run(M(), dict(sc.DEFAULTS))
        finally:
            sc.prom_boot = orig
        self.assertEqual(waits, [300])
        self.assertTrue(str(e.exception).startswith(sc.EARLY_HANG))
        for name, t in targets.TARGETS.items():
            if t.get("install", {}).get("scenario") == "solaris-install-serial.py":
                self.assertTrue(re.search(t["install"]["retry_on"], str(e.exception)), name)

    def test_install_boots_once_more(self):
        t = targets.TARGETS["sol23-ss20"]

        class Job:
            target, volids, net = t, {}, {"ip": "10.0.2.15", "netmask": "255.255.255.0", "mode": "static",
                                          "gateway": None, "dns": [], "domain": None}
            hostname, root_password, a = "sol23-ss20", "wshlab", types.SimpleNamespace(timeout=None, vmid="1")

            def __init__(self, failures):
                self.failures, self.phases = list(failures), []

            def phase(self, name, scenario, v, timeout, swaps=()):
                self.phases.append(name)
                if self.failures:
                    raise install.InstallFailed(f"{name}: failed: AssertionError: {self.failures.pop(0)}")

            def log(self, msg):
                pass

        orig, install.vm_running = install.vm_running, lambda vmid: False
        try:
            job = Job(["before the installer: no language, locale or terminal prompt within 300s"])
            install.Scripted().install(job)
            self.assertEqual(job.phases, ["install", "install-retry1"])
            job = Job(["timed out: no 'Disk' within 900s"])  # later: the disk may be written
            with self.assertRaises(install.InstallFailed):
                install.Scripted().install(job)
            self.assertEqual(job.phases, ["install"])
        finally:
            install.vm_running = orig


class WebStart(unittest.TestCase):
    """solaris-webstart-serial.py's prompt table against screens of the Solaris 8 and 9 runs."""

    @classmethod
    def setUpClass(cls):
        cls.sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-webstart-serial.py"))

    def reply(self, inst, screen):
        v = {**self.sc.DEFAULTS, "HOSTNAME": "h1", "IP": "10.0.2.15", "ROOT_PASSWORD": "pw"}
        text = self.sc.tail(screen)
        for rx, reply, _ in self.sc.prompts(inst, v):
            if re.search(rx, text):
                inst.track(screen)
                return reply(screen) if callable(reply) else reply
        return None

    def test_prompts(self):
        inst = self.sc.Installer(None, {"SWAPS": ""})
        for screen, want in [
            ("   Is this machine networked (y/n) [n]?", "y"),
            ("   Enter host name []:", "h1"),
            ("   Enter the subnet netmask [255.255.255.0]:", "255.255.255.0"),
            ("   Enter the root password again []:", "pw"),
            ("   Please enter the number corresponding to your router discovery method [1]:", "1"),
            ("Solaris Web Start will assist you in installing software for Solaris.\n"
             '   <Press ENTER to continue> {"!" exits}', ""),
            ("   Reboot automatically after software installation [y]?", "n"),
            ("Available regions:\n0     POSIX\n   If you wish to change the locale to be used, enter the number next\n"
             "   to the desired region to choose the locale to be used after the system\n"
             "   has been installed or enter n to use the default.  [n]", "0"),
            ("Available locales for POSIX:\n 2.   English (POSIX C) ( C )\n"
             "   Please enter the number next to the desired locale to be used after the\n"
             "   system has been installed, or enter n to choose a new region.  [n]", "2"),
            ("   Select the number corresponding to a file system operation, 'Return to\n"
             "   beginning' to change selections, or 'Done' to proceed with the install [4]:", ""),
            ("    <--[90%]--[ENTER To Continue]--[n To Finish]-->", "n"),
            # Solaris 9 9/05: the license question has no default in brackets
            ("   Enter 'y' to accept the license agreement. Enter 'n' to decline the license\n"
             "   agreement and exit the install.", "y"),
            # Solaris 8 2/02 after the second Software CD went in
            ("   Solaris 8 packages (part 2)  291.3 MB\n   Ready to Install\n   1. Install Now\n   2. Start Over\n"
             "   3. Exit Installation\n   What would you like to do [1]?", "1"),
            ("   <Press Return to reboot the system>", ""),
            ('<Press Return to reboot the system> {"!" exits}\n    []', ""),
            ("   the next step unless you select \"Pause\". Enter 'p' to pause. Enter 'c' to\n   continue. [c]", "c"),
        ]:
            self.assertEqual(self.reply(inst, screen), want, screen)
        self.assertIsNone(self.reply(inst, "   Something new [q]:"))

    def test_prompt_ends(self):
        """wait_prompt() settles on a line ending like a prompt, and on 9/05's bare license line."""
        sc = self.sc
        for last in ("   Enter host name []:", "   Media [1]:", "    <--[25%]--[ENTER To Continue]--[n To Finish]-->",
                     "   agreement and exit the install."):
            self.assertTrue(re.search(sc.PROMPT_END, last) or re.search(sc.PROMPT_END_BARE, last), last)
        for last in ("Reading disc for Solaris Operating Environment...", "Installing SUNWcsr."):
            self.assertFalse(re.search(sc.PROMPT_END, last) or re.search(sc.PROMPT_END_BARE, last), last)
        for last in ("   Enter 'y' to apply these values (y/n)", "Exit the install (yes/no)"):
            self.assertTrue(re.search(sc.PROMPT_END, last), last)

    def test_answered_ready_to_install_is_no_prompt(self):
        """8 2/02 after Software 2 of 2 (install matrix run 44533778163): the answered "Ready to
        Install" menu with the next line, "Installing Solaris 8 packages (part 2)", the last on the
        screen until the progress bar comes. Its closing parenthesis is no prompt end: wait_prompt()
        keeps waiting, and the answered menu ("... [1]? 1") matches no prompt of the table."""
        screen = ("Product: Solaris 8 packages (part 2)\nLocation: /\nSize: 291.3 MB\n"
                  "Solaris 8 packages (part 2)    291.3 MB\n\n\n\nReady to Install\n\n1. Install Now\n2. Start Over\n"
                  "3. Exit Installation\n\n   What would you like to do [1]? 1\n\nInstalling Solaris 8 packages (part 2)\n\n")
        self.assertFalse(self.sc.waits_for_input(screen))
        self.assertIsNone(self.reply(self.sc.Installer(None, {"SWAPS": ""}), screen))
        self.assertTrue(self.sc.waits_for_input(screen + "|-1%--------------25%---\n\n   Enter 'y' (y/n):"))
        # and the menu is answered whenever it is up (once per CD after the first)
        menu = screen[:screen.index("? 1") + 1]
        inst = self.sc.Installer(None, {"SWAPS": ""})
        self.assertTrue(self.sc.waits_for_input(menu))
        self.assertEqual([self.reply(inst, menu) for _ in range(2)], ["1", "1"])

    def test_cds_are_deselected(self):
        """Documentation and Supplement off (a partly selected CD goes [-] -> [X] -> [ ]), Software 2
        of 2 left to the software group."""
        inst = self.sc.Installer(None, {"SWAPS": ""})
        prompt = "\n   Enter the number corresponding to a CD to view its information.\n   Enter n when finished [n]"
        cds = ("Select the CDs and products you would like to install.\n"
               " [{0}]  0  Solaris 8 Documentation English    204.4 MB\n"
               " [ ]  1  Solaris 8 Software 2 of 2    0.0 MB\n"
               " [{1}]  2  Computer Systems Supplement CD    233.9 MB" + prompt)
        products = ("Products marked with an [X] will be installed.\n [{0}]  2     Computer Systems Supplement CD"
                    "    233.9 MB\n [ ]  2.0   Alternate Pathing 2.3.1    2.6 MB" + prompt)
        self.assertEqual(self.reply(inst, cds.format("X", "-")), "0")
        self.assertEqual(self.reply(inst, cds.format(" ", "-")), "2")
        self.assertEqual(self.reply(inst, products.format("-")), "2")
        self.assertEqual(self.reply(inst, "   Toggle Computer Systems Supplement CD [n]?"), "y")
        self.assertEqual(self.reply(inst, products.format("X")), "2")
        self.assertEqual(self.reply(inst, products.format(" ")), "n")
        self.assertEqual(self.reply(inst, cds.format(" ", " ")), "n")

    def test_cds_go_in_in_order(self):
        changes = []
        m = types.SimpleNamespace(change_medium=lambda d, vol: changes.append((d, vol)))
        inst = self.sc.Installer(m, {"SWAPS": "scsi6=local:iso/cd1.iso scsi6=local:iso/cd2.iso"})
        self.sc.time.sleep, sleep = (lambda s: None), self.sc.time.sleep
        try:
            self.assertEqual(self.reply(inst, "Please insert the Solaris 8 Software 1 of 2 CD.\n"
                                              "To select a different media, enter B to go Back.\n    []"), "")
            self.assertEqual(self.reply(inst, "Please insert the CD for Solaris 8 Software 2 of 2 (SPARC Platform "
                                              "Edition).\nAfter you insert the CD, please press Enter.\n    []"), "")
            with self.assertRaises(RuntimeError):
                self.reply(inst, "Please insert the Solaris 8 Software 1 of 2 CD.\n    []")
        finally:
            self.sc.time.sleep = sleep
        self.assertEqual(changes, [("scsi6", "local:iso/cd1.iso"), ("scsi6", "local:iso/cd2.iso")])

    def test_first_disc_wording_of_8_0202(self):
        changes = []
        m = types.SimpleNamespace(change_medium=lambda d, vol: changes.append((d, vol)))
        inst = self.sc.Installer(m, {"SWAPS": "scsi6=local:iso/cd1.iso scsi6=local:iso/cd2.iso"})
        self.sc.time.sleep, sleep = (lambda s: None), self.sc.time.sleep
        try:
            self.assertEqual(self.reply(inst, "Please insert the first Solaris Software disc from which you will\n"
                                              "install the Solaris Operating Environment.\n"
                                              "To select a different media, enter B to go Back.\n    []"), "")
            self.assertEqual(self.reply(inst, "Please insert the CD/DVD for Solaris 8 Software 2 of 2 (2/02 SPARC\n"
                                              "Platform Edition). After you insert the disc, please press Enter.\n"
                                              "Enter S to skip this disc and go on to the next one.\n"
                                              "To select a different media, enter B to go Back.\n    []"), "")
        finally:
            self.sc.time.sleep = sleep
        self.assertEqual(changes, [("scsi6", "local:iso/cd1.iso"), ("scsi6", "local:iso/cd2.iso")])

    def test_prom_env_only_during_the_install(self):
        for name in ("sol8-ss20", "sol9-ss20"):
            self.assertEqual(targets.TARGETS[name]["install"]["prom_env"], {"auto-boot?": "false"})


class ScriptedConsole:
    """What the Web Start scenario's boot steps use of a Machine, over scripted console output: expect
    and expect_any consume `text` like lab.Machine; power_cycle() appends `after_cycle` (the new
    QEMU's output)."""

    def __init__(self, text, after_cycle="", can_cycle=True):
        self.text, self.pos, self.after_cycle = text, 0, after_cycle
        self.sent, self.cycles, self.stopped = [], 0, False
        if can_cycle:
            self.power_cycle = self._power_cycle

    def expect(self, pattern, timeout=300, screen=False):
        m = re.compile(pattern, re.M).search(self.text, self.pos)
        if not m:
            raise lab.Timeout(f"no {pattern!r}")
        self.pos = m.end()
        return m

    def expect_any(self, patterns, timeout=300, screen=False):
        m = self.expect("|".join(f"(?P<p{i}>{p})" for i, p in enumerate(patterns)), timeout)
        return next(i for i in range(len(patterns)) if m.group(f"p{i}") is not None)

    def _power_cycle(self):
        self.cycles += 1
        self.text += self.after_cycle

    def send(self, text):
        self.sent.append(text)

    def serial_cursor(self):
        return len(self.text)

    def quiet(self, seconds, timeout=600):
        pass

    def snap(self, title):
        pass

    def stop(self):
        self.stopped = True


class WebStartSun4u(unittest.TestCase):
    """sol8-sun4u and sol9-sun4u: the Web Start installs on sun4u (IDE disk c0t0d0, the 64-bit default,
    the reboot that returns to `0 >` and the power cycle after 8's mini-root copy)."""

    @classmethod
    def setUpClass(cls):
        cls.sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-webstart-serial.py"))
        import _sparc32
        cls.sparc32 = _sparc32

    def test_targets(self):
        for name, medium in (("sol9-sun4u", "solaris-2.9-sparc.iso"), ("sol8-sun4u", "Sol8.0202.Sparc.iso")):
            t = targets.TARGETS[name]
            with self.subTest(target=name):
                self.assertEqual(t["status"], "automated")
                self.assertEqual(t["profile"], targets.SUN4U_SOLARIS)
                self.assertEqual(t["profile"]["memory"], 1024)
                self.assertEqual(t["disk"], {"bus": "ide0", "size": 8, "label": None})
                self.assertEqual((t["device"], t["boot"], t["nic"]), ("c0t0d0", "ide0", "hme0"))
                self.assertEqual(t["media"][0], {"name": medium, "drive": "ide2"})
                self.assertEqual(t["install"]["scenario"], "solaris-webstart-serial.py")
                self.assertEqual(t["install"]["vars"]["DISK"], "c0t0d0")
                self.assertTrue(t["install"]["root_password"])
                self.assertEqual(t["firstboot"]["scenario"], "solaris-firstboot.py")
                a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="8701", name=None, target=name)
                p = install.vm_params(t, a, {m["name"]: f"local:iso/{m['name']}" for m in t["media"]}, None)
                self.assertEqual((p["ide0"], p["ide2"]), ("local:8,format=raw", f"local:iso/{medium},media=cdrom"))
                self.assertEqual(p["net0"], "sunhme,bridge=vmbr0")
        # 9 runs Web Start from the DVD: no prom_env; 8 stops at `0 >` for its mini-root, and End User
        # takes Software 1 of 2 only
        self.assertNotIn("prom_env", targets.TARGETS["sol9-sun4u"]["install"])
        # 9 needs openbios 0025, published in pve-qemu-kvm 11.1.3-2+wsh25: the weekly matrix runs it
        self.assertNotIn("matrix_skip", targets.TARGETS["sol9-sun4u"])
        self.assertEqual(targets.TARGETS["sol9-sun4u"]["tested"]["packages"]["pve-qemu-kvm"], "11.1.3-2+wsh25")
        self.assertNotIn("matrix_skip", targets.TARGETS["sol8-sun4u"])
        t8 = targets.TARGETS["sol8-sun4u"]
        self.assertEqual(t8["install"]["prom_env"], {"auto-boot?": "false"})
        self.assertEqual(t8["media"][1:], [{"name": "Sol8.0202.Sparc-Software_1of2.iso", "drive": "ide2",
                                            "at": "scenario"}])

    def reply(self, screen, disk="c0t0d0"):
        v = {**self.sc.DEFAULTS, "HOSTNAME": "h1", "ROOT_PASSWORD": "pw", "DISK": disk}
        text = self.sc.tail(screen)
        for rx, reply, _ in self.sc.prompts(self.sc.Installer(None, {"SWAPS": ""}), v):
            if re.search(rx, text):
                return reply(screen) if callable(reply) else reply
        return None

    def test_prompts(self):
        bits = ("1. Software will be installed with 64-bit and 32-bit support (Recommended).\n"
                "2. Software will be installed with 32-bit support only.\n"
                "   Enter the number corresponding to your choice [{}]")
        self.assertEqual(self.reply(bits.format(1)), "1")  # sun4u keeps 64-bit
        self.assertEqual(self.reply(bits.format(2), "c0t3d0"), "2")  # sun4m: 32-bit only, as before
        layout = "   Layout file systems on disk {} (bootdisk) (y/n) [y]?"
        self.assertEqual(self.reply(layout.format("c0t0d0")), "y")
        self.assertIsNone(self.reply(layout.format("c0t3d0")))  # not the disk DISK names
        self.assertEqual(self.reply(layout.format("c0t3d0"), "c0t3d0"), "y")

    def test_mini_root_power_cycles_on_sun4u(self):
        before = ("Rebooting to continue the installation.\nsyncing file systems... done\nrebooting...\n"
                  "BOOTpanic - kernel: prom_reboot: reboot call returned!\nEXIT\n0 > ")
        after = "OpenBIOS for Sparc64\nWelcome to OpenBIOS v1.1\n0 > "
        m = ScriptedConsole("Enter a swap slice size between 384MB and 8000MB [?]\n"
                            "Can the swap slice start at the beginning of the disk [y,n,?,q]\n"
                            "Is this OK [y,n,?,q]\n" + before, after + "SunOS Release 5.8 Version Generic_108528-13 64-bit\n")
        self.sc.mini_root(m, {**self.sc.DEFAULTS, "ARCH": "sparc64", "DISK": "c0t0d0"})
        self.assertEqual(m.cycles, 1)
        self.assertEqual(m.sent[-1], "boot disk:b\r")
        # sun4m: the reboot stops at `0 >` (auto-boot? false) and the slice is booted by path, no cycle
        m = ScriptedConsole("Enter a swap slice size between 384MB and 2000MB [?]\n"
                            "Can the swap slice start at the beginning of the disk [y,n,?,q]\nIs this OK [y,n,?,q]\n"
                            "Rebooting to continue the installation.\nrebooting...\n0 > SunOS Release 5.8\n")
        self.sc.mini_root(m, dict(self.sc.DEFAULTS))
        self.assertEqual((m.cycles, m.sent[-1]), (0, f"boot {self.sc.ESP}/sd@3,0:b\r"))
        # without PVE (a QEMU of the lab's own) there is nothing to cycle: a clear failure
        m = ScriptedConsole("Enter a swap slice size between 384MB and 8000MB [?]\nCan the swap slice start at the beginning of the disk [y,n,?,q]\n"
                            "Is this OK [y,n,?,q]\n" + before, can_cycle=False)
        with self.assertRaisesRegex(RuntimeError, "through PVE"):
            self.sc.mini_root(m, {**self.sc.DEFAULTS, "ARCH": "sparc64"})

    def test_prom_boot_on_sun4u(self):
        v = {**self.sparc32.DEFAULTS, "ARCH": "sparc64"}
        m = ScriptedConsole("Welcome to OpenBIOS v1.1\n  Type 'help' for detailed information\n0 > ")
        self.sparc32.prom_boot(m, v, "cdrom")
        self.assertEqual(m.sent, ["boot cdrom:f\r"])  # auto-boot? false: the alias at the prompt
        m = ScriptedConsole("Welcome to OpenBIOS v1.1\nTrying disk:a...\nNot a bootable ELF image\n")
        self.sparc32.prom_boot(m, v, "disk")
        self.assertEqual(m.sent, [])  # the boot order: OpenBIOS boots by itself

    def test_power_cycle_only_a_vm_the_lab_started(self):
        calls = []
        m = object.__new__(lab.PveMachine)
        m.vmid, m.started, m.metrics, m.ser = "8702", True, {}, None
        m.proc = types.SimpleNamespace(wait=lambda timeout=None: 0, pid=1)
        m.log = lambda msg: None
        m.mark = lambda label: calls.append(("mark", label))
        m.cond = threading.Condition()
        m._start = lambda conf, log_name: calls.append(("start", log_name))
        orig = lab.qm, lab.pve_config
        lab.qm = lambda *args, check=True: calls.append(("qm",) + args) or ""
        lab.pve_config = lambda vmid: {}
        try:
            m.elapsed = lambda: 0
            m.power_cycle()
            m.power_cycle()
            self.assertEqual(calls, [("qm", "stop", "8702"), ("mark", "power cycle 1"), ("start", "qm-start-2.log"),
                                     ("qm", "stop", "8702"), ("mark", "power cycle 2"), ("start", "qm-start-3.log")])
            self.assertEqual(m.metrics["power_cycles"], 2)
            m.started = False
            with self.assertRaisesRegex(RuntimeError, "running before the lab attached"):
                m.power_cycle()
        finally:
            lab.qm, lab.pve_config = orig


class WebStartSunProm(unittest.TestCase):
    """sol8-ss5-prom: sol8-ss5's Web Start install under the Sun PROM (ss5.bin), which boots the
    mini-root from the reboot's boot string and stops at `ok` after the install."""

    @classmethod
    def setUpClass(cls):
        cls.sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-webstart-serial.py"))

    def test_target(self):
        t, base = targets.TARGETS["sol8-ss5-prom"], targets.TARGETS["sol8-ss5"]
        self.assertEqual(t["profile"], {**base["profile"], "bios": "ss5.bin"})
        self.assertEqual((t["media"], t["disk"], t["boot"]), (base["media"], base["disk"], base["boot"]))
        self.assertNotIn("prom_env", t["install"])  # -prom-env is OpenBIOS's; the Sun PROM boots the slice
        self.assertEqual({k: v for k, v in t["install"].items() if k != "prom_env"},
                         {k: v for k, v in base["install"].items() if k != "prom_env"})
        self.assertIn("ss5.bin", t["title"])

    def test_sun_prom(self):
        self.assertTrue(self.sc.sun_prom({"BIOS": "ss5.bin"}))
        self.assertFalse(self.sc.sun_prom({"BIOS": "openbios-sparc32"}))
        self.assertFalse(self.sc.sun_prom({"BIOS": "openbios-sparc64", "ARCH": "sparc64"}))

    def test_mini_root_booted_by_the_prom(self):
        m = ScriptedConsole("Enter a swap slice size between 384MB and 8000MB [?]\n"
                            "Can the swap slice start at the beginning of the disk [y,n,?,q]\nIs this OK [y,n,?,q]\n"
                            "Rebooting to continue the installation.\nsyncing file systems... done\nrebooting...\n"
                            "Resetting ...\nSPARCstation 5, No Keyboard\n"
                            "Boot device: /iommu/sbus/espdma@5,8400000/esp@5,8800000/sd@3,0:b   File and args:\n"
                            "SunOS Release 5.8 Version Generic_108528-13 32-bit\n")
        self.sc.mini_root(m, {**self.sc.DEFAULTS, "BIOS": "ss5.bin"})
        self.assertEqual(m.cycles, 0)
        self.assertNotIn("boot", m.sent[-1])  # nothing typed at a prompt: the PROM booted it


class Sol7Sun4u(unittest.TestCase):
    """sol7-sun4u: suninstall (solaris-install-serial.py) on sun4u, on a Sun-labelled IDE disk (c0t0d0),
    stopped at `0 >` after the install."""
    t = targets.TARGETS["sol7-sun4u"]

    @classmethod
    def setUpClass(cls):
        cls.sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-install-serial.py"))

    def test_target(self):
        t = self.t
        self.assertEqual(t["profile"], {**targets.SUN4U_SOLARIS, "memory": 2048})  # 1024: panics in pkgadd
        self.assertNotIn("memory", t["install"])
        self.assertEqual((t["disk"]["bus"], t["disk"]["label"], t["disk"]["sizes"]), ("ide0", "sun", ["3G"]))
        self.assertEqual((t["device"], t["boot"], t["nic"]), ("c0t0d0", "ide0", "hme0"))
        self.assertEqual(t["install"]["vars"]["DISK"], "c0t0d0")
        self.assertEqual(t["media"], [{"name": "Sol7.399InstallationSparc.iso", "drive": "ide2"}])
        a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="9401", name=None, target="sol7-sun4u")
        p = install.vm_params(t, a, {"Sol7.399InstallationSparc.iso": "local:iso/Sol7.399InstallationSparc.iso"},
                              "/tmp/disk-label.raw")
        self.assertEqual(p["ide0"], "local:0,import-from=/tmp/disk-label.raw,format=raw")
        self.assertEqual(p["ide2"], "local:iso/Sol7.399InstallationSparc.iso,media=cdrom")
        self.assertEqual(p["net0"], "sunhme,bridge=vmbr0")

    def test_disk_selection(self):
        class M(FakeScreen):
            def expect(self, rx, timeout=60, screen=False):
                if not re.search(rx, self.screen):
                    raise lab.Timeout(rx)
        m = M("─ Select Disks ────\n  [X] c0t0d0   2775 MB  (boot disk)\n")
        self.sc.disks(m, {**self.sc.DEFAULTS, "DISK": "c0t0d0"})
        self.assertEqual(m.typed, [])  # already selected
        with self.assertRaises(lab.Timeout):  # sun4m's default disk isn't there
            self.sc.disks(M("─ Select Disks ────\n  [X] c0t0d0   2775 MB\n"), dict(self.sc.DEFAULTS))

    def test_f2_again_on_an_unchanged_screen(self):
        self.assertEqual(self.t["install"]["vars"]["KEY_RETRY"], "180")
        self.assertEqual(self.sc.DEFAULTS["KEY_RETRY"], "0")  # sun4m: as before
        old = "─ Mount Remote File Systems? ────\n  Esc-2_Continue\n"
        new = "─ Profile ────\n  Esc-2_Continue\n"
        calls = []

        def fake_next(m, prev, timeout=600):
            calls.append(timeout)
            if len(calls) < 2:
                raise RuntimeError("the installer didn't move on")
            return new

        m = FakeScreen(old)
        m.snap = lambda title: None
        orig, self.sc.next_screen = self.sc.next_screen, fake_next
        try:
            self.assertEqual(self.sc.press_on(m, old, 180), new)
            self.assertEqual((calls, m.typed), ([180, 180], ["f2"]))
            calls.clear()
            m.screen = new  # the screen did change: no second F2, the failure stands
            with self.assertRaises(RuntimeError):
                self.sc.press_on(m, old, 180)
            calls[:] = [0]
            self.assertEqual(self.sc.press_on(m, old, 0), new)  # KEY_RETRY 0: next_screen's own wait
        finally:
            self.sc.next_screen = orig

    def test_panic_during_the_packages_fails_the_install(self):
        self.assertTrue(re.search(self.sc.PANIC, "panic[cpu0]/thread=70179200: segkp_badop"))
        self.assertFalse(re.search(self.sc.PANIC, "Executing JumpStart postinstall phase"))

    def test_halt_stops_at_the_prompt(self):
        m = ScriptedConsole("syncing file systems... done\nProgram terminated\n0 > ")
        self.sc.halt_sun4u(m)
        self.assertEqual((m.sent, m.stopped), (["sync; halt\r"], True))


class SunOS4(unittest.TestCase):
    """sunos414-ss5: the converted CD, the install-phase memory, the refused network options and the
    sys-config screens of the first boot."""
    t = targets.TARGETS["sunos414-ss5"]

    def test_target(self):
        self.assertEqual(self.t["install"]["memory"], 64)
        self.assertEqual(self.t["profile"]["memory"], 256)
        self.assertEqual(self.t["install"]["prom_env"], {"auto-boot?": "false"})
        g = self.t["disk"]["geometry"]
        self.assertEqual(g["parts"][6], (4, 0, 282, 2079000))  # g: 1000 cylinders of 21 x 99
        self.assertLess(g["parts"][6][3] * 512, 2 << 30)
        self.assertEqual(g["parts"][:6], targets.SUN29G["parts"][:6])
        cd = targets.MEDIA["sunos414-cd.iso"]
        src = targets.MEDIA[cd["from"]["name"]]
        self.assertEqual(cd["size"], src["size"] // 2352 * 2048)

    def test_convert(self):
        bin_ = b"".join(bytes([0] + [255] * 10 + [0]) + bytes(4) + bytes([i]) * 2048 + bytes(288) for i in range(3))
        cd = b"".join(bytes([i]) * 2048 for i in range(3))
        media = {"raw.iso": {"content": "iso", "size": len(bin_), "sha256": hashlib.sha256(bin_).hexdigest(),
                             "lab": "raw.iso"},
                 "cd.iso": {"content": "iso", "size": len(cd), "sha256": hashlib.sha256(cd).hexdigest(),
                            "lab": "cd.iso", "from": {"name": "raw.iso", "convert": "bin2352"}}}
        saved = dict(targets.MEDIA)
        targets.MEDIA.update(media)
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "raw.iso")
            with open(src, "wb") as f:
                f.write(bin_)
            self.assertEqual(install.convert_medium("cd.iso", src, os.path.join(d, "cd.iso")), media["cd.iso"]["sha256"])
            with open(os.path.join(d, "cd.iso"), "rb") as f:
                self.assertEqual(f.read(), cd)
            with self.assertRaises(install.InstallFailed):  # never overwrites
                install.convert_medium("cd.iso", src, os.path.join(d, "cd.iso"))
            media["cd.iso"]["sha256"] = "0" * 64  # a result that isn't the tested medium is removed
            with self.assertRaises(install.InstallFailed):
                install.convert_medium("cd.iso", src, os.path.join(d, "other.iso"))
            self.assertEqual(sorted(os.listdir(d)), ["cd.iso", "raw.iso"])
            with open(src, "r+b") as f:  # another source of the same size
                f.write(b"x")
            with self.assertRaises(install.InstallFailed):
                install.convert_medium("cd.iso", src, os.path.join(d, "third.iso"))
        finally:
            targets.MEDIA.clear()
            targets.MEDIA.update(saved)
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            os.rmdir(d)

    def test_network(self):
        n = install.network_choice(self.t, net_args(target="sunos414-ss5", ip="10.0.2.20", gateway="10.0.2.2"))
        self.assertEqual((n["ip"], n["gateway"]), ("10.0.2.20", "10.0.2.2"))
        for kw, msg in ((dict(dns="10.0.2.3"), "--dns: not with"), (dict(ip="dhcp"), "supports static")):
            with self.subTest(**kw), self.assertRaises(SystemExit) as e:
                install.network_choice(self.t, net_args(target="sunos414-ss5", **kw))
            self.assertIn(msg, str(e.exception))

    def test_sysconfig_screens(self):
        sc = lab.load_scenario(os.path.join(HERE, "scenarios", "sunos-firstboot.py"))
        import _sunos4
        v = {**sc.DEFAULTS, "HOSTNAME": "sun4", "ROOT_PASSWORD": "pw", "NET_IP": "10.0.2.20", "USER": "lab",
             "USER_PASSWORD": "upw"}
        rules = _sunos4.sysconfig_rules(v)

        def reply(screen):
            i = _sunos4.which(rules, screen)
            answer = rules[i][1]
            return answer(screen) if callable(answer) else answer

        regions = (" SysConfB1                    SYSTEM CONFIGURATION\n                                   TIME ZONE\n"
                   + "\n".join(f"                        *   {r}" for r in (
                       "United States", "Canada", "Mexico", "South America", "Europe", "Asia",
                       "Australia and New Zealand", "Greenwich Mean Time")))
        for screen, want in [
            ("Enter choice (1, 2, or 3) and press the RETURN key.", "2\r"),
            (" SysConfA1                    SYSTEM CONFIGURATION\n        Hostname =>", "sun4\r"),
            (regions, " " * 7 + "x"),
            (" SysConfC8              SYSTEM CONFIGURATION\n                        GREENWICH MEAN TIME", "x"),
            (" SysConfE1                    SYSTEM CONFIGURATION\n                                     NETWORK", "1\r"),
            (" SysConfE2   NETWORK ADDRESS\n     Network Address (e.g. 192.9.200.1) =>", "10.0.2.20\r"),
            (" SysConfH1   SUPERUSER PASSWORD\n     Password =>", "pw\r"),
            (" SysConfH1   SUPERUSER PASSWORD\n  Retype new password:", "pw\r"),
            (" SysConfI1   USER ACCOUNT\n  Do you want to set up a user account(y/n)?", "y\r"),
            (" SysConfI3   USER ACCOUNT - USER NAME\n     User name => luser", "\b" * 12 + "lab\r"),
            (" SysConfI5   USER PASSWORD\n  Retype new password:", "upw\r"),
        ]:
            self.assertEqual(reply(screen), want, screen)
        self.assertIsNone(_sunos4.which(rules, "something else"))
        no_user = _sunos4.sysconfig_rules({**v, "USER": "", "NET_IP": ""})
        self.assertEqual(no_user[_sunos4.which(no_user, " SysConfI1 ")][1], "n\r")
        self.assertEqual(no_user[_sunos4.which(no_user, " SysConfE1 ")][1], "2\r")


class OlderSun(unittest.TestCase):
    """Solaris 2.3 (sysidtool's older screens, Quick Install) and SunOS 4.1.3_U1B (the 4.1.4 install)."""
    sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-install-serial.py"))

    def test_sunos413u1b(self):
        base = targets.TARGETS["sunos414-ss5"]
        for name, machine, memory in (("sunos413u1b-ss5", "SS-5", 256), ("sunos413u1b-ss20", "SS-20", 512)):
            t = targets.TARGETS[name]
            self.assertEqual((t["profile"]["machine"], t["profile"]["memory"]), (machine, memory))
            self.assertEqual(t["profile"]["bios"], "openbios-sparc32")
            self.assertEqual((t["install"], t["firstboot"], t["check"], t["disk"]),
                             (base["install"], base["firstboot"], base["check"], base["disk"]))
            self.assertEqual(t["media"], [{"name": "sunos_4.1.3U1B.iso", "drive": "scsi6"}])
            self.assertNotIn("from", targets.MEDIA["sunos_4.1.3U1B.iso"])  # 2048-byte sectors already
            self.assertIn("4.1.3_U1B", t["net_refuse"]["dns"])
        self.assertIn("4.1.4", base["net_refuse"]["dns"])  # the copy didn't change the 4.1.4 target

    def test_sun_media_have_no_url(self):
        for name in ("Solaris2.3Edition-II.iso", "solaris2.5_sparc.iso", "sunos_4.1.3U1B.iso", "Solaris_2.2.img"):
            self.assertNotIn("url", targets.MEDIA[name])
            self.assertFalse(targets.MEDIA[name]["lab"].startswith("/"))

    def test_openbios_targets(self):
        # Solaris 2.2-2.4 under OpenBIOS (openbios 0019-0022, pve-qemu-kvm 11.1.3-2+wsh22): one CPU, the CD
        # as a disk, static address only, tested with the package that has the patches
        for name, machine, memory in (("sol22-ss10", "SS-10", 256), ("sol23-ss5", "SS-5", 256),
                                      ("sol23-ss20", "SS-20", 512), ("sol24-ss5", "SS-5", 256),
                                      ("sol24-ss20", "SS-20", 512)):
            with self.subTest(target=name):
                t = targets.TARGETS[name]
                p = t["profile"]
                self.assertEqual((p["machine"], p["bios"], p["memory"]), (machine, "openbios-sparc32", memory))
                self.assertNotIn("cores", p)
                self.assertEqual([m.get("as_disk") for m in t["media"]], [True])
                self.assertEqual(t["net_modes"], ["static"])
                self.assertEqual(t["install"]["scenario"], "solaris-install-serial.py")
                self.assertEqual(t["tested"]["packages"]["pve-qemu-kvm"], "11.1.3-2+wsh22")
                self.assertIn("OpenBIOS", t["title"])
                self.assertGreater(t["minutes"], 0)
        med = targets.MEDIA["Solaris_2.2.img"]
        self.assertEqual((med["size"], med["lab"]), (388608000, "sun_solaris/Solaris/2.2/SPARC/Solaris_2.2.img"))

    def test_matrix_holes(self):
        # Solaris 2.5.1 on the SS-20 under OpenBIOS (the SS-5 target needs ss5.bin), 2.6 and 7 on the
        # SS-10: one CPU, 512 MB, the SS-20's install unchanged, a static address only, the 3G disk
        for name, machine, medium, as_disk in (
                ("sol251-ss20", "SS-20", "solaris_2.5.1_1197.iso", True),
                ("sol26-ss10", "SS-10", "solaris_2.6_598_sparc.iso", None),
                ("sol7-ss10", "SS-10", "Sol7.399InstallationSparc.iso", None)):
            with self.subTest(target=name):
                t = targets.TARGETS[name]
                p = t["profile"]
                self.assertEqual(t["status"], "automated")
                self.assertEqual((p["arch"], p["machine"], p["bios"], p["memory"]),
                                 ("sparc", machine, "openbios-sparc32", 512))
                self.assertNotIn("cores", p)
                self.assertEqual(t["media"], [{"name": medium, "drive": "scsi6", **({"as_disk": True} if as_disk else {})}])
                self.assertEqual(t["disk"]["sizes"], ["3G"])
                self.assertEqual((t["boot"], t["hostname"]), ("scsi3", name))
                self.assertEqual(t["net_modes"], ["static"])
                self.assertEqual(t["install"]["scenario"], "solaris-install-serial.py")
                self.assertIn(machine.replace("SS-", "SPARCstation "), t["title"])
                self.assertIn("OpenBIOS", t["title"])
                self.assertNotIn("matrix_skip", t)
                self.assertGreater(t["minutes"], 0)
                self.assertEqual(t["tested"]["packages"]["pve-qemu-kvm"], "11.1.3-2+wsh25")
                self.assertIn("--export", t["tested"]["with"])
        # 2.5.1's Maintenance Update: the same long wait for the root shell as on the SS-5
        self.assertEqual(targets.TARGETS["sol251-ss20"]["install"]["vars"],
                         targets.TARGETS["sol251-ss5"]["install"]["vars"])

    def test_old_select(self):
        m = FakeScreen("Will this system be connected to a network?\n\n     ┌────┐\n     │>No │\n     │ Yes│\n"
                       "     └────┘\n")
        self.sc.old_select(m, m.screen, "Yes")
        self.assertEqual(m.typed, ["ctrl-n", "\r"])
        m = FakeScreen("    │ NIS+ Client             │\n    │ NIS (formerly yp) Client│\n"
                       "    │>None - use /etc files   │\n")
        self.sc.old_select(m, m.screen, "NIS+")
        self.assertEqual(m.typed, ["ctrl-p", "ctrl-p", "\r"])
        with self.assertRaises(RuntimeError):
            self.sc.old_select(FakeScreen(""), "    │>No │\n    │ Yes│\n", "Maybe")

    def test_old_date(self):
        screen = "".join(f"    │ {f} :  {v}   │\n" for f, v in (
            ("Year   (4 digits)", "1912"), ("Month  (1-12)    ", "11"), ("Day    (1-31)    ", "19"),
            ("Hour   (0-23)    ", "01"), ("Minute (0-59)    ", "45")))
        orig, self.sc.time.sleep = self.sc.time.sleep, lambda s: None
        try:
            m = FakeScreen(screen)
            self.sc.old_date(m, {"YEAR": "2026"}, screen)
            self.assertEqual(m.typed, ["2026"] + ["\r"] * 5)  # the year typed over 1912, Return x5
            m = FakeScreen(screen.replace("1912", "1996"))
            self.sc.old_date(m, {}, m.screen)
            self.assertEqual(m.typed, ["\r"] * 5)
        finally:
            self.sc.time.sleep = orig

    def test_old_screens_in_order(self):
        def rule(screen):
            return next(rx for rx, _ in self.sc.OLD_SCREENS if re.search(rx, screen))
        self.assertIn("hostname", rule("What is the hostname for your workstation?"))
        # the confirmation repeats what was answered; it must not match the question screens
        self.assertIn("correct", rule("Is the following information correct?\n\nHostname:  sol23-ss5\n"
                                      "Connected to network:  Yes\nIP address:  10.0.2.15\n"))
        self.assertIn("correct", rule("Is the following information correct?\n\nTime zone:  MET\n"))


class InstallerConsole:
    """What _openbsd.installer() uses of a Machine: the serial text with expect()/quiet(), send() and log.
    `script`: the console output, one chunk at the start and one after each answer (the echo of the
    answer is added unless it answers a password question)."""

    def __init__(self, script):
        self.script = list(script)
        self.text, self.pos, self.sent = self.script.pop(0), 0, []
        self.cond = threading.Condition()
        self.metrics = {}

    def expect(self, pattern, timeout=300, screen=False):
        m = re.compile(pattern, re.M).search(self.text, self.pos)
        if not m:
            raise lab.Timeout(f"no {pattern!r} in {self.text[self.pos:]!r}")
        self.pos = m.end()
        return m

    def expect_any(self, patterns, timeout=300, screen=False):
        m = self.expect("|".join(f"(?P<p{i}>{p})" for i, p in enumerate(patterns)), timeout)
        return next(i for i in range(len(patterns)) if m.group(f"p{i}") is not None)

    def quiet(self, seconds, timeout=600):
        pass

    def send(self, text):
        self.sent.append(text)
        echo = "" if "Password" in self.text.rsplit("\n", 1)[-1] else text.rstrip("\r")
        self.text += echo + "\n" + (self.script.pop(0) if self.script else "")

    def log(self, msg):
        pass

    def snap(self, title):
        pass


class SysinstConsole(InstallerConsole):
    """What _netbsd.sysinst() uses of a Machine: `script` holds sysinst's screens, the first at the start
    and the next after each Return (a letter only moves the cursor). screen=True looks at the screen
    shown now, the serial text from where the last match ended otherwise."""

    def __init__(self, script):
        super().__init__(script)
        self.shown = self.text

    def expect(self, pattern, timeout=300, screen=False):
        if not screen:
            return super().expect(pattern, timeout)
        m = re.compile(pattern, re.M).search(self.shown)
        if not m:
            raise lab.Timeout(f"no {pattern!r} on the screen {self.shown!r}")
        return m

    def expect_any(self, patterns, timeout=300, screen=False):
        m = self.expect("|".join(f"(?P<p{i}>{p})" for i, p in enumerate(patterns)), timeout, screen)
        return next(i for i in range(len(patterns)) if m.group(f"p{i}") is not None)

    def send(self, text):
        self.sent.append(text)
        if text.endswith("\r"):
            self.shown = self.script.pop(0) if self.script else ""
            self.text += "\n" + self.shown


class NetBSDSysinst(unittest.TestCase):
    """The NetBSD targets (11.1 and 9.3) and sysinst's answers (_netbsd.sysinst), with the screens
    where the releases differ."""
    # sysinst's screens up to the sets, the same in 11.1 and 9.3 (shortened)
    BEFORE_SETS = ["a: Installation messages in English", "a: Install NetBSD to hard disk",
                   "Shall we continue?\n a: No\n b: Yes", "Available disks\n a: wd0", "b: Use default partition sizes",
                   "x: Partition sizes ok", "Are you sure? ... ready to install NetBSD", "Select your distribution",
                   "Install from\n a: CD-ROM / DVD", "Hit enter to continue"]
    END = ["The installation of NetBSD-{r} is now complete.\n Hit enter to continue",
           "x: Exit Install System", "# "]

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(HERE, "scenarios"))
        import _netbsd
        cls.nb = _netbsd

    def setUp(self):
        self.sleep, self.nb.time.sleep = self.nb.time.sleep, lambda s: None

    def tearDown(self):
        self.nb.time.sleep = self.sleep

    def test_targets(self):
        for name, release, iso, disk in [
                ("netbsd111-sparc64", "11.1", "NetBSD-11.1-sparc64.iso", "wd0"),
                ("netbsd111-sparc", "11.1", "NetBSD-11.1-sparc.iso", "sd0"),
                ("netbsd111-sparc-ss20", "11.1", "NetBSD-11.1-sparc.iso", "sd0"),
                ("netbsd93-sparc64", "9.3", "NetBSD-9.3-sparc64.iso", "wd0"),
                ("netbsd93-sparc", "9.3", "NetBSD-9.3-sparc.iso", "sd0"),
                ("netbsd93-sparc-ss20", "9.3", "NetBSD-9.3-sparc.iso", "sd0")]:
            t = targets.TARGETS[name]
            self.assertIn(f"NetBSD {release} ", t["title"], name)
            self.assertEqual(t["media"][0]["name"], iso, name)
            self.assertIn(f"disklabel {disk} ", t["check"]["commands"], name)
            self.assertEqual(t["firstboot"]["scenario"], "netbsd-firstboot.py", name)
            med = targets.MEDIA[iso]
            self.assertEqual(med["lab"], f"other-os/{iso}", name)
            self.assertTrue(med["url"].endswith(f"/NetBSD-{release}/images/{iso}"), name)
        # the same profiles, installs and checks per machine in both releases
        for old, new in [("netbsd93-sparc64", "netbsd111-sparc64"), ("netbsd93-sparc", "netbsd111-sparc"),
                         ("netbsd93-sparc-ss20", "netbsd111-sparc-ss20")]:
            a, b = targets.TARGETS[old], targets.TARGETS[new]
            for key in ("profile", "disk", "install", "check", "boot", "nic"):
                self.assertEqual(a[key], b[key], f"{old} {key}")

    def run_sysinst(self, script, sets="b"):
        m = SysinstConsole(script)
        at_shell = self.nb.sysinst(m, {"SETS": sets})
        return m, at_shell

    def test_sysinst_111(self):
        # 11.1: root's password and the entropy question after the sets, then the configuration menu
        m, at_shell = self.run_sysinst(self.BEFORE_SETS + [
            "New password:", "x: Not now, continue", "x: Finished configuring",
            *(s.format(r="11.1") for s in self.END)])
        self.assertTrue(at_shell)
        self.assertEqual(m.sent, ["a", "\r", "a", "\r", "b", "\r", "a", "\r", "b", "\r", "x", "\r", "b", "\r",
                                  "b", "\r", "a", "\r", "\r", "\r", "x", "\r", "x", "\r", "\r", "x", "\r"])

    def test_sysinst_93(self):
        # 9.3: no password prompt and no entropy question; root's password is an item of the
        # configuration menu, left empty (netbsd-firstboot.py sets it)
        m, at_shell = self.run_sysinst(self.BEFORE_SETS + [
            "The extraction of the selected sets for NetBSD-9.3 is complete.\n Hit enter to continue",
            " d: Change root password   ***EMPTY***\n> x: Finished configuring",
            *(s.format(r="9.3") for s in self.END)], sets="c")
        self.assertTrue(at_shell)
        self.assertEqual(m.sent, ["a", "\r", "a", "\r", "b", "\r", "a", "\r", "b", "\r", "x", "\r", "b", "\r",
                                  "c", "\r", "a", "\r", "\r", "\r", "x", "\r", "\r", "x", "\r"])
        self.assertNotIn("Not now", m.text[:m.text.index("Finished configuring")])

    def test_sysinst_sparc_microroot_halts(self):
        # the sparc CD's microroot halts by itself after "Exit Install System"
        m, at_shell = self.run_sysinst(self.BEFORE_SETS + [
            "x: Finished configuring", "The installation of NetBSD-9.3 is now complete.",
            "x: Exit Install System", "Back in microroot; halting machine"], sets="c")
        self.assertFalse(at_shell)


class OpenBSD80(unittest.TestCase):
    """openbsd80-sun4u: the target, the installer's questions answered by what they ask (_openbsd.py),
    the check's console line."""
    t = targets.TARGETS["openbsd80-sun4u"]

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(HERE, "scenarios"))
        import _openbsd
        cls.ob = _openbsd

    def v(self, **kw):
        return {"HOSTNAME": "openbsd80-sun4u", "IP": "10.0.2.15", "NETMASK": "255.255.255.0",
                "ROOT_PASSWORD": "pw", "SETS": "-x*", **kw}

    def test_target(self):
        t, p = self.t, self.t["profile"]
        self.assertEqual((p["arch"], p["machine"], p["bios"], p["net0"]), ("sparc64", "sun4u", "openbios-sparc64", "sunhme"))
        self.assertEqual((t["disk"]["bus"], t["disk"]["label"], t["boot"], t["nic"]), ("ide0", None, "ide0", "hme0"))
        self.assertEqual(t["media"], [{"name": "install80.iso", "drive": "ide2"}])
        self.assertTrue(t["install"]["root_password"])  # the installer asks for it
        self.assertEqual(t["install"]["retry_on"], "IDE timeouts")  # _openbsd.installer()'s error
        self.assertEqual(t["net_modes"], ["static"])
        self.assertEqual(t["tested"]["packages"]["pve-qemu-kvm"], "11.1.3-2+wsh22")  # openbios 0023
        self.assertGreater(t["minutes"], 0)
        med = targets.MEDIA["install80.iso"]
        self.assertEqual((med["size"], med["lab"]), (467599360, "other-os/openbsd8.0/install80.iso"))
        a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="9210", name=None, target="openbsd80-sun4u")
        vp = install.vm_params(t, a, {"install80.iso": "local:iso/install80.iso"}, None)
        self.assertEqual((vp["ide0"], vp["ide2"]), ("local:8,format=raw", "local:iso/install80.iso,media=cdrom"))

    def test_check_fits_one_console_line(self):
        # OpenBSD's tty takes 255 characters; the check adds --user's grep and the end marker
        line = self.t["check"]["commands"] + "; grep '^someuser:' /etc/passwd | cut -d: -f1,3-; echo END-OF-COMMAND"
        self.assertLess(len(line), 255)
        self.assertIn("rcctl get ntpd flags", self.t["check"]["commands"])

    def test_rules(self):
        rules = self.ob.install_rules(self.v(SETS="-x* -game*"), {})
        for line, want in [
            ("(I)nstall, (U)pgrade, (A)utoinstall or (S)hell? ", "i"),
            ("Terminal type? [sun] ", "vt220"),
            ("System hostname? (short form, e.g. 'foo') ", "openbsd80-sun4u"),
            ("Network interface to configure? (name, lladdr, '?', or 'done') [hme0] ", "hme0"),
            ("IPv4 address for hme0? (or 'autoconf' or 'none') [autoconf] ", "10.0.2.15"),
            ("Netmask for hme0? [255.255.255.0] ", "255.255.255.0"),
            ("IPv6 address for hme0? (or 'autoconf' or 'none') [autoconf] ", "none"),
            ("Network interface to configure? (name, lladdr, '?', or 'done') [done] ", "done"),
            ("Default IPv4 route? (IPv4 address or 'none') ", "none"),
            ("Password for root account? (again) ", "pw"),
            ("Encrypt the root disk with a (p)assphrase or (k)eydisk? [no] ", "no"),
            ("Location of sets? (cd0 disk http nfs or 'done') [http] ", "cd0"),
            ("Set name(s)? (or 'abort' or 'done') [done] ", "-x*"),
            ("Set name(s)? (or 'abort' or 'done') [done] ", "-game*"),
            ("Set name(s)? (or 'abort' or 'done') [done] ", "done"),
            ("Location of sets? (cd0 disk http nfs or 'done') [done] ", "done"),
            ("Exit to (S)hell, (H)alt or (R)eboot? [reboot] ", "s"),
        ]:
            i = self.ob.which_question(rules, line)
            self.assertIsNotNone(i, line)
            rx, answer = rules[i]
            self.assertEqual(answer(re.search(rx, line)) if callable(answer) else answer, want, line)
        self.assertIsNone(self.ob.which_question(rules, "duplicate IP address 10.0.2.15 sent from ethernet address"))

    def test_installer_answers_a_redrawn_question_once(self):
        # a kernel message in the middle of a question: the line editor draws it again, and only the
        # copy on the last line is answered (answering both answered the next question too)
        q = "DNS domain name? (e.g. 'example.com') [my.domain] "
        m = InstallerConsole([
            "(I)nstall, (U)pgrade, (A)utoinstall or (S)hell? ",
            q + "duplicate IP address 10.0.2.15 sent from ethernet address 52:54:00:00:00:01\n\n" + q,
            "DNS nameservers? (IP address list or 'none') [none] ",
            "Password for root account? (will not echo) ",
            "Password for root account? (again) ",
            "Exit to (S)hell, (H)alt or (R)eboot? [reboot] ",
            "# ",
        ])
        asked = self.ob.installer(m, self.v(), 60)
        self.assertEqual(m.sent, ["i\r", "\r", "none\r", "pw\r", "pw\r", "s\r"])
        self.assertEqual(len(asked), 6)

    def test_installer_fails_when_stuck_after_ide_timeouts(self):
        # the CD stopped answering while the sets were extracted (once in five installs): fail after
        # STUCK_S seconds of silence instead of waiting for the install's whole timeout
        script = ["Installing base80.tgz    34% |*****    |  60 MB    05:00 ETA\ncd0(pciide0:1:0): timeout\n"
                  "\ttype: atapi\n\tc_bcount: 2048\n"]
        saved = self.ob.silent
        try:
            self.ob.silent = lambda m, seconds, poll=5: True
            m = InstallerConsole(script)
            with self.assertRaises(AssertionError) as e:
                self.ob.installer(m, self.v(), 60)
            self.assertIn("IDE timeouts (1)", str(e.exception))
            # output goes on after a timeout (the driver recovered): the questions are answered as before
            self.ob.silent = lambda m, seconds, poll=5: False
            m = InstallerConsole([script[0] + "Location of sets? (cd0 disk http nfs or 'done') [done] ", "# "])
            with self.assertRaises(lab.Timeout):  # no Exit question in this script: ends at its end
                self.ob.installer(m, self.v(), 60)
            self.assertEqual(m.sent, ["cd0\r"])
            self.assertEqual(m.metrics["ide_timeouts"], 1)
        finally:
            self.ob.silent = saved
        self.assertTrue(re.search(self.ob.IDE_TIMEOUT, "wd0(pciide0:0:0): timeout"))
        self.assertIsNone(re.search(self.ob.IDE_TIMEOUT, "wd0d: device timeout reading fsbn 64"))

    def test_installer_stops_at_an_unknown_question(self):
        m = InstallerConsole(["Do you want to frobnicate? [no] "])
        with self.assertRaises(AssertionError) as e:
            self.ob.installer(m, self.v(), 60)
        self.assertIn("frobnicate", str(e.exception))
        self.assertEqual(m.sent, [])


class OpenBSD59(unittest.TestCase):
    """openbsd59-ss5 and openbsd59-ss20: the targets, the sets CD made from the release's files
    (answer_media.openbsd_sets, install.convert_files) and 5.9's installer questions (_openbsd.py)."""
    names = ("openbsd59-ss5", "openbsd59-ss20")

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(HERE, "scenarios"))
        import _openbsd
        cls.ob = _openbsd

    def v(self, **kw):
        return {"ARCH": "sparc", "HOSTNAME": "openbsd59-ss5", "IP": "10.0.2.15", "NETMASK": "255.255.255.0",
                "ROOT_PASSWORD": "pw", "SETS": "", "SETS_CD": "cd0", "SETS_PATH": "/", **kw}

    def test_targets(self):
        for name in self.names:
            t, p = targets.TARGETS[name], targets.TARGETS[name]["profile"]
            self.assertEqual((p["arch"], p["bios"], p["net0"], p["vga"]), ("sparc", "openbios-sparc32", "lance", "serial0"))
            self.assertEqual((t["disk"]["bus"], t["disk"]["label"], t["boot"], t["nic"]), ("scsi3", None, "scsi3", "le0"))
            # the sets CD on target 5 comes before the boot CD on 6: the installer's cd0
            self.assertEqual(t["media"], [{"name": "cd59.iso", "drive": "scsi6"},
                                          {"name": "openbsd59-sparc-sets.iso", "drive": "scsi5"}])
            self.assertEqual(t["install"]["scenario"], "openbsd-install-sparc.py")
            self.assertTrue(t["install"]["root_password"])
            # 8 GiB: room for the installer's check of the sets, which the install requires
            self.assertEqual((t["disk"]["size"], t["install"]["vars"]["VERIFY"]), (8, "1"))
            self.assertEqual(t["check"]["scenario"], "openbsd-boot-disk.py")
            line = t["check"]["commands"] + "; grep '^someuser:' /etc/passwd | cut -d: -f1,3-; echo END-OF-COMMAND"
            self.assertLess(len(line), 255)  # OpenBSD's tty takes 255 characters
            self.assertEqual(t["net_modes"], ["static"])
        self.assertEqual(targets.TARGETS["openbsd59-ss5"]["profile"]["machine"], "SS-5")
        self.assertEqual(targets.TARGETS["openbsd59-ss20"]["profile"]["machine"], "SS-20")

    def test_media(self):
        cd, sets = targets.MEDIA["cd59.iso"], targets.MEDIA["openbsd59-sparc-sets.iso"]
        self.assertEqual((cd["size"], cd["lab"]), (4048896, "other-os/openbsd5.9/cd59.iso"))
        self.assertTrue(cd["url"].startswith("https://ftp.eu.openbsd.org/pub/OpenBSD/5.9/sparc/"))
        f = sets["from"]
        self.assertEqual((f["convert"], f["dir"]), ("openbsd-sets", "other-os/openbsd5.9"))
        self.assertEqual(sorted(f["files"]), sorted(["bsd", "bsd.rd", "base59.tgz", "comp59.tgz", "man59.tgz",
                                                     "game59.tgz", "SHA256.sig", "INSTALL.sparc"]))
        # the files are the scenario's (a lab QEMU of its own writes the same CD from SETS_DIR)
        sc = lab.load_scenario(os.path.join(HERE, "scenarios", "openbsd-install-sparc.py"))
        self.assertEqual(sorted(sc.SETS_FILES), sorted(f["files"]))
        # an ISO 9660 image of these files: their sectors and the volume's 21 sectors before them
        sectors = sum(max(1, -(-size // 2048)) for size, _ in f["files"].values())
        self.assertEqual(sets["size"], (21 + sectors) * 2048)

    def test_openbsd_sets(self):
        import answer_media
        import dos_tools
        files = {"bsd": b"k" * 3000, "bsd.rd": b"r", "base59.tgz": b"b" * 5000, "SHA256.sig": b"s\n",
                 "INSTALL.sparc": b"i"}
        data = answer_media.openbsd_sets(files)
        self.assertEqual(data, answer_media.openbsd_sets(dict(reversed(list(files.items())))))  # reproducible
        with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
            f.write(data)
        try:
            iso = dos_tools.Iso(f.name)
            self.assertEqual(sorted(p for p, _ in iso.walk()), ["BASE59.TGZ", "BSD", "BSD.RD", "INSTALL.SPA", "SHA256.SIG"])
            self.assertEqual(iso.cat("BSD"), files["bsd"])
            iso.f.close()
        finally:
            os.unlink(f.name)
        # the Rock Ridge names, as OpenBSD's cd9660 reads them (NM in each record, SP and the RRIP ER in "."
        root = data[20 * 2048:21 * 2048]
        self.assertIn(b"SP\x07\x01\xbe\xef\x00", root[:256])
        self.assertIn(b"ER", root[:256])
        self.assertIn(b"RRIP_1991A", root[:256])
        for name in files:
            self.assertIn(b"NM" + bytes([5 + len(name), 1, 0]) + name.encode(), root)
        self.assertEqual(answer_media.iso_name("INSTALL.sparc"), "INSTALL.SPA")
        self.assertEqual(answer_media.iso_name("site59-openbsd.tgz"), "SITE59_O.TGZ")
        with self.assertRaises(ValueError):  # two names that end up the same in ISO 9660
            answer_media.openbsd_sets({"abcdefgh1.tgz": b"", "abcdefgh2.tgz": b""})
        with self.assertRaises(ValueError):
            answer_media.iso9660({"A": b""}, rock_ridge={"A": "a/b"})
        # without Rock Ridge the image is what it always was (the answer CDs)
        plain = answer_media.iso9660({"KS.CFG": b"x"}, "WSH_LAB_KS")
        self.assertNotIn(b"RRIP_1991A", plain)

    def test_convert_files(self):
        files = {"bsd": b"kernel", "base59.tgz": b"base" * 1000}
        import answer_media
        cd = answer_media.openbsd_sets(files)
        media = {"sets.iso": {"content": "iso", "size": len(cd), "sha256": hashlib.sha256(cd).hexdigest(), "lab": "sets.iso",
                              "from": {"convert": "openbsd-sets", "dir": "rel",
                                       "files": {n: (len(b), hashlib.sha256(b).hexdigest()) for n, b in files.items()}}}}
        saved = dict(targets.MEDIA)
        targets.MEDIA.update(media)
        d = tempfile.mkdtemp()
        try:
            rel = os.path.join(d, "rel")
            os.mkdir(rel)
            for n, b in files.items():
                with open(os.path.join(rel, n), "wb") as f:
                    f.write(b)
            self.assertEqual(install.convert_medium("sets.iso", rel, os.path.join(d, "sets.iso")), media["sets.iso"]["sha256"])
            with open(os.path.join(d, "sets.iso"), "rb") as f:
                self.assertEqual(f.read(), cd)
            with self.assertRaises(install.InstallFailed):  # never overwrites
                install.convert_medium("sets.iso", rel, os.path.join(d, "sets.iso"))
            with self.assertRaises(install.InstallFailed):  # a file, not the directory
                install.convert_medium("sets.iso", os.path.join(rel, "bsd"), os.path.join(d, "x.iso"))
            with open(os.path.join(rel, "bsd"), "wb") as f:  # another file of the same size
                f.write(b"KERNEL")
            with self.assertRaises(install.InstallFailed) as e:
                install.convert_medium("sets.iso", rel, os.path.join(d, "x.iso"))
            self.assertIn("not the tested file", str(e.exception))
            self.assertEqual(sorted(os.listdir(d)), ["rel", "sets.iso"])
        finally:
            targets.MEDIA.clear()
            targets.MEDIA.update(saved)
        self.assertEqual(targets.problems(), [])

    def test_rules(self):
        # the questions as OpenBSD 5.9's installer asked them on the SS-5
        rules = self.ob.install_rules(self.v(), {})
        for line, want in [
            ("(I)nstall, (U)pgrade, (A)utoinstall or (S)hell? ", "i"),
            ("Terminal type? [sun] ", "vt220"),
            ("System hostname? (short form, e.g. 'foo') ", "openbsd59-ss5"),
            ("Which network interface do you wish to configure? (or 'done') [le0] ", "le0"),
            ("IPv4 address for le0? (or 'dhcp' or 'none') [dhcp] ", "10.0.2.15"),
            ("Netmask for le0? [255.255.255.0] ", "255.255.255.0"),
            ("IPv6 address for le0? (or 'rtsol' or 'none') [none] ", "none"),
            ("Which network interface do you wish to configure? (or 'done') [done] ", "done"),
            ("Default IPv4 route? (IPv4 address or none) ", "none"),
            ("DNS domain name? (e.g. 'bar.com') [my.domain] ", ""),
            ("DNS nameservers? (IP address list or 'none') [none] ", "none"),
            ("Password for root account? (will not echo) ", "pw"),
            ("Start sshd(8) by default? [yes] ", "yes"),
            ("Setup a user? (enter a lower-case loginname, or 'no') [no] ", "no"),
            ("Allow root ssh login? (yes, no, prohibit-password) [no] ", "no"),
            ("Which disk is the root disk? ('?' for details) [sd0] ", "sd0"),
            ("Use (A)uto layout, (E)dit auto layout, or create (C)ustom layout? [a] ", "a"),
            ("Location of sets? (cd0 cd1 disk http nfs or 'done') [cd0] ", "cd0"),
            ("Pathname to the sets? (or 'done') [5.9/sparc] ", "/"),
            ("INSTALL.sparc not found. Use sets found here anyway? [no] ", "yes"),
            ("Set name(s)? (or 'abort' or 'done') [done] ", "done"),
            ("Cannot determine prefetch area. Continue without verification? [no] ", "yes"),
            ("Location of sets? (cd0 cd1 disk http nfs or 'done') [done] ", "done"),
        ]:
            i = self.ob.which_question(rules, line)
            self.assertIsNotNone(i, line)
            rx, answer = rules[i]
            self.assertEqual(answer(re.search(rx, line)) if callable(answer) else answer, want, line)

    def test_installer_ends_at_congratulations(self):
        # 5.9 has no "Exit to (S)hell" question: it ends at its shell after CONGRATULATIONS
        m = InstallerConsole([
            "(I)nstall, (U)pgrade, (A)utoinstall or (S)hell? ",
            "Location of sets? (cd0 cd1 disk http nfs or 'done') [cd0] ",
            "Pathname to the sets? (or 'done') [5.9/sparc] ",
            "Set name(s)? (or 'abort' or 'done') [done] ",
            "Installing game59.tgz   100% |*****|  2771 KB    00:02\n"
            "Location of sets? (cd0 cd1 disk http nfs or 'done') [done] ",
            "Saving configuration files...done.\nMaking all device nodes...done.\n"
            "CONGRATULATIONS! Your OpenBSD install has been successfully completed!\n"
            "To boot the new system, enter 'reboot' at the command prompt.\n# ",
        ])
        asked = self.ob.installer(m, self.v(), 60)
        self.assertEqual(m.sent, ["i\r", "cd0\r", "/\r", "done\r", "done\r"])
        self.assertEqual(len(asked), 5)

    def test_unknown_question_with_a_hint(self):
        # a question with a `(hint)` after its `?` is a question too: no rule, the install fails at once
        m = InstallerConsole(["IPv6 address for le0? (or 'slaac' or 'none') [none] "])
        with self.assertRaises(AssertionError) as e:
            self.ob.installer(m, self.v(), 60)
        self.assertIn("slaac", str(e.exception))

    def test_lab_machine(self):
        # ARCH=sparc in a scenario with sparc64's DEFAULTS (first boot, check): a sun4m QEMU, -nographic
        v = {**self.ob.DEFAULTS, "ARCH": "sparc", "NO_CD": "1", "DISK": os.devnull}
        args = self.ob.qemu_args(v, tempfile.gettempdir())
        self.assertEqual(args[0], "qemu-system-sparc")
        self.assertIn("-nographic", args)
        self.assertEqual(args[args.index("-m") + 1], "256")
        self.assertIn("type=SS-5", " ".join(args))
        v = {**self.ob.DEFAULTS, "ARCH": "sparc", "NO_CD": "1", "DISK": os.devnull, "MACHINE": "SS-20"}
        args = self.ob.qemu_args(v, tempfile.gettempdir())
        self.assertEqual(args[args.index("-m") + 1], "512")
        self.assertEqual((self.ob.nic({"ARCH": "sparc"}), self.ob.disk({"ARCH": "sparc"})), ("le0", "sd0"))
        self.assertEqual((self.ob.nic({}), self.ob.disk({})), ("hme0", "wd0"))


class NeXT(unittest.TestCase):
    """nextstep33-ss5 and openstep42-ss5: catalogue entries until framebuffer scenarios drive their
    installs (the ESP interrupt delay is published; SPARC.md, "NeXTSTEP 3.3 and OPENSTEP 4.2")."""
    names = {"nextstep33-ss5": "nextstep33_risc.iso", "openstep42-ss5": "Openstep-4.2-Intel-User.iso"}

    def test_catalogue_only(self):
        for name, medium in self.names.items():
            t = targets.TARGETS[name]
            self.assertEqual(t["status"], "catalogue")
            self.assertNotIn(name, targets.automated())
            self.assertIn("ESP", t["blocked"])
            self.assertEqual(t["media"], [{"name": medium, "drive": "scsi6"}])

    def test_profile(self):
        # the installed disk boots only under ss5.bin; the installer and the system need the framebuffer:
        # TCX, which NeXT's S24 driver drives (it has no cg3 driver)
        for name in self.names:
            p = targets.TARGETS[name]["profile"]
            self.assertEqual((p["arch"], p["machine"], p["bios"], p["vga"]),
                             ("sparc", "SS-5,esp-irq-latency=500", "ss5.bin", "tcx"))
            self.assertEqual(targets.TARGETS[name]["disk"], {"bus": "scsi3", "size": 2, "label": None})

    def test_media_are_local(self):
        for medium in self.names.values():
            m = targets.MEDIA[medium]
            self.assertNotIn("url", m)  # commercial media
            self.assertTrue(m["lab"].startswith("other-os/"))


class RedHat62(unittest.TestCase):
    """redhat62-ss5/-ss20: the unattended method (kickstart from an answer CD made on the node), the
    answer CD itself, the kickstart file and the drive it goes into."""
    names = ("redhat62-ss5", "redhat62-ss20")

    def test_targets(self):
        for name in self.names:
            t = targets.TARGETS[name]
            self.assertEqual((t["method"], t["status"], t["nic"]), ("unattended", "automated", "eth0"))
            self.assertEqual(t["install"]["answers"], {"format": "kickstart", "drive": "scsi5"})
            self.assertEqual([m["name"] for m in t["media"]], ["redhat-6.2-sparc.iso"])
            self.assertEqual(t["media"][0]["drive"], "scsi6")  # the install source: sr1, after the answers' sr0
            self.assertEqual((t["disk"]["bus"], t["disk"]["label"]), ("scsi3", "sun"))  # anaconda wants a label
            self.assertEqual(t["net_modes"], ["static"])
            self.assertEqual(install.METHODS[t["method"]], install.Unattended)
        self.assertEqual(targets.TARGETS["redhat62-ss5"]["profile"]["machine"], "SS-5")
        self.assertEqual(targets.TARGETS["redhat62-ss20"]["profile"]["machine"], "SS-20")
        a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="9600", name=None, target="redhat62-ss5")
        p = install.vm_params(targets.TARGETS["redhat62-ss5"], a, {"redhat-6.2-sparc.iso": "local:iso/rh.iso"},
                              "/work/disk-label.raw")
        self.assertEqual(p["scsi6"], "local:iso/rh.iso,media=cdrom")
        self.assertNotIn("scsi5", p)  # the answer CD goes in for the install phase only (Unattended)

    def test_answers_drive_checked(self):
        saved = targets.TARGETS["redhat62-ss5"]
        try:
            for answers in ({"format": "kickstart", "drive": "scsi6"}, {"format": "kickstart", "drive": "scsi3"},
                            {"format": "kickstart"}, None):
                install_ = {**saved["install"], "answers": answers}
                targets.TARGETS["redhat62-ss5"] = {**saved, "install": install_}
                self.assertTrue(any(p.startswith("redhat62-ss5:") for p in targets.problems()), answers)
        finally:
            targets.TARGETS["redhat62-ss5"] = saved
        self.assertEqual(targets.problems(), [])

    def test_iso9660(self):
        import answer_media
        import dos_tools
        data = answer_media.iso9660({"KS.CFG": b"hello\n", "B.TXT": b"x" * 5000}, "WSH_LAB_KS")
        self.assertEqual(len(data) % 2048, 0)
        self.assertEqual(data, answer_media.iso9660({"KS.CFG": b"hello\n", "B.TXT": b"x" * 5000}, "WSH_LAB_KS"))
        with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
            f.write(data)
        try:
            iso = dos_tools.Iso(f.name)
            self.assertEqual(sorted(p for p, _ in iso.walk()), ["B.TXT", "KS.CFG"])
            self.assertEqual(iso.cat("ks.cfg"), b"hello\n")
            self.assertEqual(iso.cat("B.TXT"), b"x" * 5000)
            iso.f.close()
        finally:
            os.unlink(f.name)
        self.assertEqual(data[16 * 2048 + 40:16 * 2048 + 72].rstrip(), b"WSH_LAB_KS")
        for bad in ({"ks.cfg": b""}, {"TOOLONGNAME.CFG": b""}, {"A-B": b""}):
            with self.assertRaises(ValueError):
                answer_media.iso9660(bad)

    def test_kickstart(self):
        import answer_media
        ks = answer_media.kickstart("10.77.0.60", "255.255.252.0")
        self.assertIn("network --bootproto static --ip 10.77.0.60 --netmask 255.255.252.0\n", ks)
        lines = ks.splitlines()
        # /boot first (SILO's second stage must be near the start of the disk), then /, then swap
        parts = [line.split()[1] for line in lines if line.startswith("part ")]
        self.assertEqual(parts, ["/boot", "/", "swap"])
        for cmd in ("cdrom", "install", "zerombr yes", "clearpart --all", "skipx", "reboot", "%packages", "@ Base"):
            self.assertIn(cmd, lines)
        self.assertIn("rootpw --iscrypted *", lines)  # no password: the first boot sets it
        self.assertLess(lines.index("%packages"), lines.index("%post"))
        for bad in (("10.0.2.15; rm -rf /", "255.255.255.0"), ("10.0.2.15", "")):
            with self.assertRaises(ValueError):
                answer_media.kickstart(*bad)
        iso = answer_media.image("kickstart", "10.0.2.15", "255.255.255.0")
        self.assertIn(answer_media.kickstart("10.0.2.15", "255.255.255.0").encode(), iso)
        with self.assertRaises(ValueError):
            answer_media.image("autoyast", "10.0.2.15", "255.255.255.0")

    def test_unattended_install(self):
        """The answer CD is written to the media storage, put into scsi5 for the install phase only, and
        the drive and the image are gone afterwards, also when the install fails."""
        d = tempfile.mkdtemp()
        calls = []

        def fake_run(*cmd, check=True):
            calls.append(cmd)
            if cmd[:2] == ("pvesm", "path"):
                return os.path.join(d, cmd[2].split("/")[-1])
            return ""

        class Job:
            target = targets.TARGETS["redhat62-ss5"]
            volids, net, hostname = {}, {"ip": "10.0.2.20", "netmask": "255.255.255.0"}, "rh"
            root_password = "wshlab"
            a = types.SimpleNamespace(timeout=None, vmid="9600", media_storage="local", out=d)

            def __init__(self, fail=False):
                self.fail, self.phases, self.logs = fail, [], []

            def phase(self, name, scenario, v, timeout, swaps=()):
                path = os.path.join(d, "wsh-lab-answers-9600.iso")
                with open(path, "rb") as f:
                    self.phases.append((name, scenario, f.read()))
                if self.fail:
                    raise install.InstallFailed("install: stalled")

            def log(self, msg):
                self.logs.append(msg)

        saved = install.run, install.storage_content, install.save_config
        install.run, install.storage_content = fake_run, lambda s: {"iso", "images"}
        install.save_config = lambda vmid, work: None
        try:
            job = Job()
            install.Unattended().install(job)
            (name, scenario, data), = job.phases
            self.assertEqual((name, scenario), ("install", "redhat-install-sparc.py"))
            self.assertEqual(data, install.answer_media.image("kickstart", "10.0.2.20", "255.255.255.0"))
            self.assertIn(("qm", "set", "9600", "--scsi5", "local:iso/wsh-lab-answers-9600.iso,media=cdrom"), calls)
            self.assertEqual(calls[-1], ("qm", "set", "9600", "--delete", "scsi5"))
            self.assertEqual(os.listdir(d), [])
            calls.clear()
            with self.assertRaises(install.InstallFailed):
                install.Unattended().install(Job(fail=True))
            self.assertEqual(calls[-1], ("qm", "set", "9600", "--delete", "scsi5"))
            self.assertEqual(os.listdir(d), [])
            with open(os.path.join(d, "wsh-lab-answers-9600.iso"), "wb"):
                pass  # an image left by someone else is never overwritten
            with self.assertRaises(install.InstallFailed):
                install.Unattended().install(Job())
            install.storage_content = lambda s: {"images"}
            os.unlink(os.path.join(d, "wsh-lab-answers-9600.iso"))
            with self.assertRaises(install.InstallFailed):  # no iso content on the media storage
                install.Unattended().install(Job())
        finally:
            install.run, install.storage_content, install.save_config = saved
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            os.rmdir(d)


def post_args(**kw):
    a = dict(target="sol26-ss20", data_disk=2, data_mount=None, post_install="sun26gnu", local_env=False, user=None)
    a.update(kw)
    return types.SimpleNamespace(**a)


class PostInstall(unittest.TestCase):
    """--data-mount, --post-install and --local-env (README.md, "Solaris post-install")."""
    b = targets.POST_INSTALL["sun26gnu"]

    def test_medium_is_local_only(self):
        med = targets.MEDIA["sun26gnu.iso"]
        self.assertEqual((med["size"], med["content"], med["lab"]), (287309824, "iso", "sun26gnu.iso"))
        self.assertTrue(med["sha256"].startswith("7630cbd8866bdf64"))
        self.assertTrue(med.get("local_only"))
        self.assertNotIn("url", med)  # never downloaded: CI can't and mustn't need it
        # no target's own media: `lab.py media`, pve_matrix.py and the CI matrices never ask for it
        self.assertFalse([n for n, t in targets.TARGETS.items() if any(m["name"] == "sun26gnu.iso" for m in t["media"])])

    def test_bundle(self):
        self.assertEqual(targets.problems(), [])
        self.assertEqual(self.b["medium"], "sun26gnu.iso")
        self.assertEqual((self.b["basedir"], self.b["drive"], self.b["shell"]), ("/usr/local", "scsi5", "/usr/local/bin/bash"))
        for name in self.b["targets"]:
            self.assertEqual(targets.TARGETS[name]["status"], "automated")
            self.assertEqual(targets.TARGETS[name]["firstboot"]["scenario"], "solaris-firstboot.py")

    def test_bundle_problems(self):
        saved = dict(targets.POST_INSTALL)
        try:
            targets.POST_INSTALL["x"] = {**self.b, "medium": "nope.iso", "targets": ["redhat62-ss5"]}
            out = " ".join(targets.problems())
            self.assertIn("nope.iso isn't in MEDIA", out)
            self.assertIn("redhat62-ss5 isn't a Solaris target", out)
            targets.POST_INSTALL["x"] = {**self.b, "drive": "scsi6"}
            self.assertIn("drive scsi6 is taken", " ".join(targets.problems()))
        finally:
            targets.POST_INSTALL.clear()
            targets.POST_INSTALL.update(saved)

    def test_accepted(self):
        for kw in ({}, dict(target="sol26-ss5", data_disk=1), dict(local_env=True, user="lab"),
                   dict(data_mount="/usr/local"), dict(local_env=True)):
            with self.subTest(**kw):
                install.check_post_install(post_args(**kw))
                self.assertEqual(install.data_mount(post_args(**kw)), "/usr/local")

    def test_data_mount(self):
        self.assertEqual(install.data_mount(post_args(post_install=None)), "/data")
        self.assertEqual(install.data_mount(post_args(post_install=None, data_mount="/usr/local")), "/usr/local")
        install.check_post_install(post_args(post_install=None, data_mount="/usr/local"))
        self.assertEqual(install.data_mount(types.SimpleNamespace(data_disk=2)), "/data")  # callers without the options

    def test_refusals(self):
        for kw, msg in ((dict(target="redhat62-ss5"), "tested on sol26-ss5, sol26-ss20, sol7-ss5, sol7-ss20, not redhat62-ss5"),
                        (dict(target="sol10-sun4u"), "not sol10-sun4u"),
                        (dict(data_disk=None), "needs --data-disk"),
                        (dict(data_mount="/data"), "must be on /usr/local"),
                        (dict(post_install=None, local_env=True), "--local-env: only with --post-install"),
                        (dict(post_install=None, data_disk=None, data_mount="/usr/local"), "--data-mount: only with --data-disk")):
            with self.subTest(**kw), self.assertRaises(SystemExit) as e:
                install.check_post_install(post_args(**kw))
            self.assertIn(msg, str(e.exception))
        saved = dict(targets.POST_INSTALL)
        try:
            targets.POST_INSTALL["sun26gnu"] = {**self.b, "min_data_disk": 3}
            with self.assertRaises(SystemExit) as e:
                install.check_post_install(post_args(data_disk=2))
            self.assertIn("--data-disk 3 GiB or more", str(e.exception))
            targets.POST_INSTALL["sun26gnu"] = {**self.b, "shell": None}
            with self.assertRaises(SystemExit) as e:
                install.check_post_install(post_args(local_env=True))
            self.assertIn("brings no login shell", str(e.exception))
        finally:
            targets.POST_INSTALL.clear()
            targets.POST_INSTALL.update(saved)

    def test_cli(self):
        import argparse
        p = argparse.ArgumentParser()
        install.add_commands(p.add_subparsers(dest="cmd"))
        a = p.parse_args(["install", "sol26-ss20", "--vmid", "9300", "--data-disk", "2", "--post-install", "sun26gnu",
                          "--local-env", "--user", "lab"])
        self.assertEqual((a.data_disk, a.data_mount, a.post_install, a.local_env), (2, None, "sun26gnu", True))
        a = p.parse_args(["install", "sol26-ss20", "--vmid", "1", "--data-disk", "2", "--data-mount", "/usr/local"])
        self.assertEqual((a.data_mount, a.post_install, a.local_env), ("/usr/local", None, False))
        import contextlib
        import io
        for bad in (["--post-install", "nope"], ["--data-mount", "/opt"]):
            with self.subTest(bad=bad), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                p.parse_args(["install", "sol26-ss20", "--vmid", "1", *bad])

    def test_cd_only_for_the_phase(self):
        """The bundle's CD goes into scsi5 for the post-install phase and is removed afterwards, also
        when the phase fails."""
        calls, phases = [], []

        def fake_run(*cmd, check=True):
            calls.append(cmd)
            return ""

        class Job:
            volids = {"sun26gnu.iso": "local:iso/sun26gnu.iso"}
            root_password = "wshlab"
            a = types.SimpleNamespace(vmid="9300", out="/x", post_install="sun26gnu", local_env=True, user="lab")

            def __init__(self, fail=False):
                self.fail = fail

            def phase(self, name, scenario, v, timeout, swaps=()):
                phases.append((name, scenario, v, timeout))
                if self.fail:
                    raise install.InstallFailed("postinstall: stalled")

            def log(self, msg):
                pass

        saved = install.run, install.save_config
        install.run, install.save_config = fake_run, lambda vmid, work: None
        try:
            install.PostInstall().run(Job())
            (name, scenario, v, timeout), = phases
            self.assertEqual((name, scenario, timeout), ("postinstall", "solaris-post-install.py", 5400))
            self.assertEqual((v["CD"], v["DIR"], v["DATA_DISK"], v["BASEDIR"], v["LOCAL_ENV"], v["USER"], v["LOGIN_SHELL"]),
                             ("c0t5d0", "gnu/pkgs", "c0t4d0", "/usr/local", "1", "lab", "/usr/local/bin/bash"))
            self.assertEqual(calls[0], ("qm", "set", "9300", "--scsi5", "local:iso/sun26gnu.iso,media=cdrom"))
            self.assertEqual(calls[-1], ("qm", "set", "9300", "--delete", "scsi5"))
            calls.clear()
            with self.assertRaises(install.InstallFailed):
                install.PostInstall().run(Job(fail=True))
            self.assertEqual(calls[-1], ("qm", "set", "9300", "--delete", "scsi5"))
        finally:
            install.run, install.save_config = saved

    def test_checks(self):
        """The --check boot's extra commands: one console line each, and each regex matches what the
        guest prints but not the command line the console echoes."""
        job = types.SimpleNamespace(a=post_args(local_env=True, user="lab"))
        v = install.post_install_checks(job)
        cmds, rxs = v["MORE_COMMANDS"].split("\n"), v["MORE_EXPECT"].split("\n")
        self.assertEqual(len(cmds), len(rxs))
        self.assertEqual(len(cmds), 1 + 3 + 1 + 2 + 2)
        good = ["df: /dev/dsk/c0t4d0s0      2033311  241000 1731318    13%    /usr/local",
                "GNU bash, version 4.1.0(1)-release (sparc-sun-solaris2.6)", "VIM - Vi IMproved 7.3 (2010 Aug 15)",
                "GNU Wget 1.12 built on solaris2.6.", "pkginfo knows 35 of 35 packages",
                "root PATH=/usr/sbin:/usr/bin:/usr/local/bin:/usr/local/sbin", "root:/sbin/sh",
                "lab:/usr/local/bin/bash", "which: /usr/local/bin/bash"]
        for cmd, rx, out in zip(cmds, rxs, good):
            with self.subTest(cmd=cmd):
                self.assertLess(len(cmd), 250)
                self.assertTrue(re.search(rx, out + "\n", re.M), (rx, out))
                self.assertFalse(re.search(rx, "# " + cmd + "\n", re.M), (rx, cmd))
        self.assertFalse(re.search(rxs[4], "pkginfo knows 34 of 35 packages"))
        self.assertFalse(re.search(rxs[4], "pkginfo knows 0 of 0 packages"))
        self.assertFalse(re.search(rxs[0], "df: /dev/dsk/c0t3d0s0 1 2 3 4% /usr/local"))  # / on the root disk
        v = install.post_install_checks(types.SimpleNamespace(a=post_args()))
        self.assertEqual(len(v["MORE_COMMANDS"].split("\n")), 5)  # without --local-env

    def test_post_install_scenario(self):
        sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-post-install.py"))
        lines = sc.pkgadd_script({"BUNDLE": "sun26gnu", "DIR": "gnu/pkgs"})
        self.assertTrue(all(len(line) <= 200 for line in lines + sc.ADMIN_LINES))
        self.assertIn("pkgadd -n -a /var/sadm/wsh-lab-admin -d $d all >> $L 2>&1; rc=$?", "\n".join(lines))
        admin = dict(line.split("=", 1) for line in sc.ADMIN_LINES)
        self.assertEqual(admin["basedir"], "default")
        self.assertEqual(admin["instance"], "overwrite")
        self.assertEqual(admin["mail"], "")
        for key in ("partial", "runlevel", "idepend", "rdepend", "space", "setuid", "conflict", "action"):
            self.assertEqual(admin[key], "nocheck", key)

    def test_boot_disk_more_commands(self):
        """solaris-boot-disk.py types MORE_COMMANDS one per line and expects MORE_EXPECT for each."""
        sc = lab.load_scenario(os.path.join(HERE, "scenarios", "solaris-boot-disk.py"))
        self.assertEqual((sc.DEFAULTS["MORE_COMMANDS"], sc.DEFAULTS["MORE_EXPECT"]), ("", ""))
class Debian40(unittest.TestCase):
    """debian40-ss5/-ss20: the unattended method with a preseed file (answer CD on scsi5, loaded by
    preseed/early_command), the network the netinst needs, --apt-proxy, the boot line's limits."""
    names = ("debian40-ss5", "debian40-ss20")

    def test_targets(self):
        for name in self.names:
            t = targets.TARGETS[name]
            self.assertEqual((t["method"], t["status"], t["nic"]), ("unattended", "automated", "eth0"))
            self.assertEqual(t["install"]["answers"], {"format": "preseed", "drive": "scsi5"})
            self.assertEqual(t["media"], [{"name": "debian-40r9-sparc-netinst.iso", "drive": "scsi6"}])
            self.assertEqual((t["disk"]["bus"], t["disk"]["label"]), ("scsi3", None))  # partman labels it
            self.assertEqual((t["net_modes"], t["net_require"], t["apt_proxy"]),
                             (["static"], ["gateway", "dns"], True))
            # in pve_matrix only with an apt cache (the pinhole on vmbr0); no matrix_skip
            self.assertEqual(t["matrix_needs"], "apt_cache")
            self.assertNotIn("matrix_skip", t)
            self.assertEqual(t["tested"]["packages"]["pve-qemu-kvm"], "11.1.3-2+wsh21")
            self.assertIn("cat /etc/debian_version", t["check"]["commands"])
            self.assertEqual(install.METHODS[t["method"]], install.Unattended)
        self.assertEqual(targets.TARGETS["debian40-ss5"]["profile"]["machine"], "SS-5")
        self.assertEqual(targets.TARGETS["debian40-ss20"]["profile"]["machine"], "SS-20")

    def test_network_needs_router_and_dns(self):
        def a(**kw):
            base = dict(target="debian40-ss5", ip=None, netmask=None, gateway=None, dns=None, domain=None,
                        vlan=None, bridge="vmbr0")
            return types.SimpleNamespace(**{**base, **kw})
        t = targets.TARGETS["debian40-ss5"]
        for bad in (a(), a(gateway="10.0.2.2"), a(dns="10.0.2.3"), a(ip="dhcp")):
            with self.assertRaises(SystemExit):
                install.network_choice(t, bad)
        net = install.network_choice(t, a(gateway="10.0.2.2", dns="10.0.2.3", domain="lab.test"))
        self.assertEqual((net["ip"], net["gateway"], net["dns"]), ("10.0.2.15", "10.0.2.2", ["10.0.2.3"]))

    def test_network_proxy_on_the_guests_network(self):
        """An --apt-proxy by address on the guest's own network (pve_matrix's pinhole) replaces
        --gateway and --dns; a proxy by name or elsewhere doesn't."""
        def a(**kw):
            base = dict(target="debian40-ss5", ip=None, netmask=None, gateway=None, dns=None, domain=None,
                        vlan=None, bridge="vmbr0", apt_proxy=None)
            return types.SimpleNamespace(**{**base, **kw})
        t = targets.TARGETS["debian40-ss5"]
        net = install.network_choice(t, a(apt_proxy="http://10.0.2.2:3142"))
        self.assertEqual((net["ip"], net["gateway"], net["dns"]), ("10.0.2.15", None, []))
        net = install.network_choice(t, a(ip="192.0.2.20", apt_proxy="http://192.0.2.1:3142/"))
        self.assertEqual(net["gateway"], None)
        for bad in (a(apt_proxy="http://aptcache.example:3142"), a(apt_proxy="http://10.0.3.2:3142"),
                    a(ip="192.0.2.20", apt_proxy="http://10.0.2.2:3142")):
            with self.assertRaises(SystemExit, msg=bad.apt_proxy):
                install.network_choice(t, bad)
        self.assertTrue(install.proxy_on_network("http://10.0.2.2:3142", install.ipaddress.ip_network("10.0.2.0/24")))
        self.assertFalse(install.proxy_on_network(None, install.ipaddress.ip_network("10.0.2.0/24")))

    def test_apt_proxy(self):
        t, rh = targets.TARGETS["debian40-ss5"], targets.TARGETS["redhat62-ss5"]
        url = "http://aptcache.example:3142"
        self.assertIsNone(install.apt_proxy_choice(t, None, env={}))
        self.assertEqual(install.apt_proxy_choice(t, url, env={}), url)
        self.assertEqual(install.apt_proxy_choice(t, None, env={"WSH_LAB_APT_PROXY": url + "/"}), url + "/")
        # the environment variable applies only to targets that fetch packages; the option is refused
        self.assertIsNone(install.apt_proxy_choice(rh, None, env={"WSH_LAB_APT_PROXY": url}))
        with self.assertRaises(SystemExit):
            install.apt_proxy_choice(rh, url, env={})
        for bad in ("aptcache.example:3142", "ftp://aptcache.example", "http://u:p@aptcache.example:3142",
                    "http://aptcache.example:3142/debian", "http://aptcache.example:99999", "http://a b"):
            with self.assertRaises(SystemExit, msg=bad):
                install.apt_proxy_choice(t, bad, env={})

    def test_preseed(self):
        import answer_media
        ps = answer_media.preseed("10.77.0.60", "255.255.255.0", "10.77.0.1", ["10.77.0.1", "10.77.0.2"],
                                  "lab.test", "deb40")
        lines = ps.splitlines()
        for line in ("d-i netcfg/disable_dhcp boolean true", "d-i netcfg/get_ipaddress string 10.77.0.60",
                     "d-i netcfg/get_gateway string 10.77.0.1",
                     "d-i netcfg/get_nameservers string 10.77.0.1 10.77.0.2",
                     "d-i netcfg/get_hostname string deb40", "d-i netcfg/get_domain string lab.test",
                     "d-i mirror/http/hostname string archive.debian.org", "d-i mirror/suite string etch",
                     "d-i mirror/http/proxy string ", "d-i debian-installer/allow_unauthenticated string true",
                     "d-i apt-setup/security_host string", "d-i passwd/root-password-crypted password *",
                     "d-i passwd/make-user boolean false", "d-i preseed/early_command string",
                     "d-i preseed/late_command string chroot /target passwd -d root; chroot /target sed -i"
                     " 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list"):
            self.assertIn(line, lines)
        recipe = next(line for line in lines if "expert_recipe" in line)
        self.assertEqual(re.findall(r"mountpoint\{ (\S+) \}", recipe), ["/boot", "/"])  # /boot first (SILO)
        self.assertLess(recipe.index("/boot"), recipe.index("linux-swap"))
        self.assertIn("d-i mirror/http/proxy string http://aptcache.example:3142",
                      answer_media.preseed("10.0.2.15", "255.255.255.0", "10.0.2.2", ["10.0.2.3"],
                                           proxy="http://aptcache.example:3142").splitlines())
        # a proxy by address replaces the router and the name server (pve_matrix's pinhole)
        lines = answer_media.preseed("10.0.2.15", "255.255.255.0", proxy="http://10.0.2.2:3142").splitlines()
        for line in ("d-i netcfg/get_gateway string ", "d-i netcfg/get_nameservers string ",
                     "d-i mirror/http/proxy string http://10.0.2.2:3142"):
            self.assertIn(line, lines)
        # etch's netcfg puts in 10.0.2.1 for both; the late command takes them out again
        late = next(line for line in lines if "late_command" in line)
        self.assertIn("chroot /target sed -i '/^[[:space:]]*gateway /d' /etc/network/interfaces", late)
        self.assertIn("chroot /target sed -i '/^nameserver /d' /etc/resolv.conf", late)
        self.assertNotIn("gateway /d", next(line for line in ps.splitlines() if "late_command" in line))
        for bad in (dict(gateway=None), dict(dns=[]), dict(hostname="a b"), dict(proxy="http://x/;rm"),
                    dict(dns=["10.0.2.3; reboot"]), dict(gateway=None, proxy="http://aptcache.example:3142")):
            kw = {"gateway": "10.0.2.2", "dns": ["10.0.2.3"], **bad}
            with self.assertRaises(ValueError, msg=bad):
                answer_media.preseed("10.0.2.15", "255.255.255.0", **kw)

    def test_answer_cd(self):
        import answer_media
        import dos_tools
        data = answer_media.image("preseed", "10.0.2.15", "255.255.255.0", "10.0.2.2", ["10.0.2.3"], None,
                                  "debian40-ss5", "http://aptcache.example:3142")
        with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
            f.write(data)
        try:
            iso = dos_tools.Iso(f.name)
            self.assertEqual(sorted(p for p, _ in iso.walk()), ["PRESEED.CFG", "WSHLAB"])
            self.assertIn(b"d-i netcfg/get_hostname string debian40-ss5\n", iso.cat("preseed.cfg"))
            self.assertEqual(iso.cat("wshlab"), answer_media.PRESEED_LOADER.encode())
            iso.f.close()
        finally:
            os.unlink(f.name)
        loader = answer_media.PRESEED_LOADER
        self.assertIn("debconf-set-selections /mnt/preseed.cfg", loader)
        self.assertIn("/device/delete", loader)  # Etch's cdrom-detect must not find the answer CD

    def test_boot_line(self):
        sys.path.insert(0, os.path.join(HERE, "scenarios"))
        import _debian
        line = _debian.boot_line()
        self.assertTrue(line.startswith('install priority=critical locale=en_US preseed/early_command="'))
        self.assertIn("/dev/scsi/host0/bus0/target5/lun0/cd /mnt", line)
        self.assertLessEqual(len("cdrom " + line), 230)  # Linux 2.6.18 on sparc32 keeps 256 bytes
        # sparc32 reads words starting with - as boot switches (-h halts, -p: PROM console)
        self.assertEqual([w for w in line.split() if w.startswith("-")], ["-r"])
        self.assertNotIn(".", line.split("early_command=")[1])  # d-i reads a.b=c as a module parameter
        self.assertEqual("scsi" + _debian.ANSWERS_TARGET,
                         targets.TARGETS["debian40-ss5"]["install"]["answers"]["drive"])


if __name__ == "__main__":
    unittest.main()
