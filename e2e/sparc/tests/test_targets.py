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
            with self.subTest(target=name):
                cpus = int(p.get("sockets", 1)) * int(p.get("cores", 1))
                self.assertNotIn("cpu", p)
                if p["arch"] == "sparc":
                    prof = s32[p["machine"]]
                    self.assertIn(p["bios"], prof["firmware"])
                    self.assertLessEqual(int(p["memory"]), prof["max-memory"])
                    self.assertLessEqual(cpus, prof["firmware"][p["bios"]]["max-cpus"])
                    self.assertIn(p["vga"], vga32)
                    self.assertEqual(p["net0"], "lance")
                    self.assertEqual(disk["bus"], "scsi3")  # the PROMs boot target 3
                    self.assertTrue(all(m["drive"] == "scsi6" for m in t["media"]))  # CD-ROM on target 6
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

    def test_later_media_are_not_attached_at_the_start(self):
        t = targets.TARGETS["sol8-ss20"]
        vols = {m["name"]: f"local:iso/{m['name']}" for m in t["media"]}
        p = install.vm_params(t, types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="1", name="x",
                                                       target="sol8-ss20"), vols, None)
        self.assertEqual(p["scsi6"], "local:iso/sun-solaris-8-0101-installation-sparc.iso,media=cdrom")
        self.assertEqual(p["scsi3"], "local:8,format=raw")


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


if __name__ == "__main__":
    unittest.main()
