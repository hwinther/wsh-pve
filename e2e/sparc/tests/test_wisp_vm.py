"""`wsh-lab wisp-vm` (wisp_vm.py) without a PVE node: the VM options per architecture, the kernel command
line and `args`, the SHA-256 checked downloads from a local directory laid out like the releases, the
data disk (with squashfs-tools), the refusals (an existing VMID, a VM it didn't make, another node).
Standard library only, no network:

    cd e2e/sparc && python3 -m unittest -v tests/test_wisp_vm.py
"""
import argparse
import contextlib
import hashlib
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import wisp_vm  # noqa: E402

FETCH_PY = os.path.join(HERE, "..", "wisp", "doom", "fetch.py")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


class Params(unittest.TestCase):
    def test_shell_vm_has_a_serial_console(self):
        for arch in wisp_vm.ARCHES:
            with self.subTest(arch=arch):
                p = wisp_vm.vm_params(arch, 900, "/k", kvm=False)
                self.assertEqual(p["vga"], "serial0")
                self.assertEqual(p["serial0"], "socket")
                self.assertEqual(p["tags"], wisp_vm.TAG)
                words = shlex.split(p["args"])
                self.assertEqual(words[:2], ["-kernel", "/k"])
                self.assertIn("wisp=shell", words[3])
                self.assertNotIn("-device", words)  # no framebuffer, no keyboard
                self.assertFalse(any(k.startswith(("ide", "scsi")) and k != "scsihw" for k in p))

    def test_profiles(self):
        sparc32 = wisp_vm.vm_params("sparc32", 1, "/k", fb=True)
        self.assertEqual((sparc32["arch"], sparc32["machine"], sparc32["bios"], sparc32["vga"]),
                         ("sparc", "SS-5", "openbios-sparc32", "cg3"))
        self.assertEqual(wisp_vm.vm_params("sparc32", 1, "/k", display="tcx", fb=True)["vga"], "tcx")
        sun4u = wisp_vm.vm_params("sparc64", 1, "/k", fb=True, ps2=False)
        self.assertEqual((sun4u["machine"], sun4u["bios"], sun4u["vga"]), ("sun4u", "openbios-sparc64", "std"))
        self.assertIn("-device virtio-keyboard-pci", sun4u["args"])  # firmware without the option
        virt = wisp_vm.vm_params("aarch64", 1, "/k", doom=True, disk="/d.sqfs")
        self.assertEqual((virt["arch"], virt["machine"], virt["scsihw"]), ("aarch64", "virt", "virtio-scsi-pci"))
        self.assertEqual(virt["scsi0"], "local:0,import-from=/d.sqfs,format=raw")
        self.assertIn("console=ttyAMA0", virt["args"])
        pc = wisp_vm.vm_params("x86_64", 1, "/k", doom=True, disk="/d", storage="tank", kvm=False)
        self.assertEqual((pc["vga"], pc["kvm"], pc["ide0"]), ("std", 0, "tank:0,import-from=/d,format=raw"))
        self.assertNotIn("-device", pc["args"])  # the pc's own PS/2 keyboard
        with self.assertRaisesRegex(wisp_vm.WispError, "display tcx"):
            wisp_vm.vm_params("x86_64", 1, "/k", display="tcx", fb=True)

    def test_sun4u_ps2_keyboard_and_mouse(self):
        for kw in ({"fb": True}, {"doom": True, "disk": "/d"}):
            with self.subTest(**kw):
                p = wisp_vm.vm_params("sparc64", 1, "/k", ps2=True, **kw)
                words = shlex.split(p["args"])
                self.assertEqual(words[:2], ["-kernel", "/k"])
                i = words.index("-prom-env")
                self.assertEqual(words[i + 1], "ps2-mouse?=true")
                self.assertNotIn("-device", words)  # no virtio keyboard or mouse
                self.assertFalse(any("virtio" in w for w in words))
                # qemu-server splits `args` like a shell (Text::ParseWords::shellwords): `?` stays quoted
                self.assertIn("'ps2-mouse?=true'", p["args"])
        # the shell VM has no framebuffer and so no keyboard, and only sun4u takes the option
        self.assertNotIn("-prom-env", wisp_vm.vm_params("sparc64", 1, "/k", ps2=True)["args"])
        for arch in ("x86_64", "sparc32", "aarch64"):
            with self.subTest(arch=arch):
                self.assertNotIn("-prom-env", wisp_vm.vm_params(arch, 1, "/k", fb=True, ps2=True, kvm=False)["args"])
        self.assertIn("-device virtio-keyboard-pci", wisp_vm.vm_params("aarch64", 1, "/k", fb=True, ps2=True)["args"])

    def test_ps2_follows_the_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = os.path.join(tmp, "old"), os.path.join(tmp, "new")
            with open(old, "wb") as f:
                f.write(b"\0OpenBIOS\0s\" false\" s\" auto-boot?\" bool-config\0")
            with open(new, "wb") as f:
                f.write(b"\0OpenBIOS\0kdmouse\0ps2-mouse?\0")
            self.assertTrue(wisp_vm.firmware_has_ps2(new))
            self.assertFalse(wisp_vm.firmware_has_ps2(old))
            self.assertFalse(wisp_vm.firmware_has_ps2(os.path.join(tmp, "missing")))
            for path, ps2 in ((new, True), (old, False)):
                with self.subTest(firmware=os.path.basename(path)),                         mock.patch.object(wisp_vm, "SPARC64_FIRMWARE", path):
                    args = wisp_vm.vm_params("sparc64", 1, "/k", fb=True)["args"]
                    self.assertEqual("-prom-env" in args, ps2)
                    self.assertEqual("virtio-keyboard-pci" in args, not ps2)
                    self.assertEqual(wisp_vm.ps2_input("sparc64", fb=True), ps2)
                    self.assertFalse(wisp_vm.ps2_input("sparc64", fb=False))
                    self.assertFalse(wisp_vm.ps2_input("aarch64", fb=True))

    def test_doom_command_line(self):
        words = shlex.split(wisp_vm.vm_args("sparc32", "/var/lib/wsh-lab/wisp/vm-9/kernel", doom=True))
        self.assertEqual(words[:3], ["-kernel", "/var/lib/wsh-lab/wisp/vm-9/kernel", "-append"])
        self.assertEqual(words[3], "console=ttyS0 panic=-1 quiet wisp=run wisp_data=/dev/sda "
                                   "wisp_run=/data/fbdoom -- @/data/play.rsp")
        self.assertEqual(wisp_vm.response(fps=True).split(), ["-iwad", "/data/freedoom1.wad", "-nosound", "-fps"])


class Downloads(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.release = os.path.join(self.tmp, "release")
        self.dir = os.path.join(self.tmp, "wisp")
        os.makedirs(self.release)

    def put(self, name, data):
        with open(os.path.join(self.release, name), "wb") as f:
            f.write(data)

    def test_fb_files_are_checked(self):
        self.put("kernel-fb-sparc32", b"kernel")
        self.put("fbdoom-sparc32", b"doom")
        self.put("SHA256SUMS", f"{digest(b'kernel')}  kernel-fb-sparc32\n{digest(b'doom')}  fbdoom-sparc32\n".encode())
        kernel, doom = wisp_vm.fetch_fb(self.release, self.dir, "sparc32", doom=True)
        self.assertEqual(read(doom), b"doom")
        self.assertEqual(os.path.basename(kernel), "kernel-fb-sparc32")
        self.put("kernel-fb-sparc32", b"changed")
        os.unlink(kernel)
        with self.assertRaisesRegex(wisp_vm.WispError, "SHA-256 mismatch"):
            wisp_vm.fetch_fb(self.release, self.dir, "sparc32")
        self.assertFalse(os.path.exists(kernel))
        self.assertEqual([n for n in os.listdir(os.path.dirname(kernel)) if n.startswith(".")], [])
        with self.assertRaisesRegex(wisp_vm.WispError, "not in the wisp-fb"):
            wisp_vm.fetch_fb(self.release, self.dir, "aarch64")

    def test_kit_kernel(self):
        stage = os.path.join(self.tmp, "stage", "wisp-test-kit", "x86_64")
        os.makedirs(stage)
        with open(os.path.join(stage, "kernel"), "wb") as f:
            f.write(b"bzImage")
        kit = os.path.join(self.release, wisp_vm.KIT)
        with tarfile.open(kit, "w:xz") as tar:
            tar.add(os.path.join(self.tmp, "stage", "wisp-test-kit"), "wisp-test-kit")
        self.put(f"{wisp_vm.KIT}.sha256", f"{digest(read(kit))}  {wisp_vm.KIT}\n".encode())
        kernel = wisp_vm.fetch_kit(self.release, self.dir, "x86_64")
        self.assertEqual(read(kernel), b"bzImage")
        with self.assertRaises(KeyError):
            wisp_vm.fetch_kit(self.release, self.dir, "sparc32")

    def test_bad_sums(self):
        with self.assertRaisesRegex(wisp_vm.WispError, "not a sha256sum line"):
            wisp_vm.parse_sums("abc  file\n")

    def test_wad_zip_must_match_the_pin(self):
        archive = os.path.join(self.tmp, "freedoom-0.13.0.zip")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("freedoom-0.13.0/freedoom1.wad", b"IWAD")
        with self.assertRaisesRegex(wisp_vm.WispError, "SHA-256 mismatch"):
            wisp_vm.fetch_wad(self.dir, archive)
        with mock.patch.object(wisp_vm, "FREEDOOM_SHA", digest(read(archive))):
            self.assertEqual(read(wisp_vm.fetch_wad(self.dir, archive)), b"IWAD")

    @unittest.skipUnless(os.path.exists(FETCH_PY), "needs the repository's e2e/wisp/doom/fetch.py")
    def test_freedoom_pin_matches_fetch_py(self):
        text = read(FETCH_PY, "r")
        self.assertIn(f'VERSION = "{wisp_vm.FREEDOOM_VERSION}"', text)
        self.assertIn(f'DATA_SHA = "{wisp_vm.FREEDOOM_SHA}"', text)


@unittest.skipUnless(shutil.which("mksquashfs") and shutil.which("unsquashfs"), "requires squashfs-tools")
class DataDisk(unittest.TestCase):
    def test_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in (("fbdoom", b"ELF"), ("wad", b"IWAD")):
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(data)
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            disk = wisp_vm.build_disk(work, os.path.join(tmp, "fbdoom"), os.path.join(tmp, "wad"), fps=True)
            out = os.path.join(tmp, "x")
            subprocess.run(["unsquashfs", "-no-progress", "-d", out, disk], check=True, stdout=subprocess.DEVNULL)
            self.assertEqual(sorted(os.listdir(out)), ["fbdoom", "freedoom1.wad", "play.rsp"])
            self.assertEqual(os.stat(os.path.join(out, "fbdoom")).st_mode & 0o777, 0o755)
            self.assertIn("-fps", read(os.path.join(out, "play.rsp"), "r").split())


class Refusals(unittest.TestCase):
    def args(self, **kw):
        a = argparse.Namespace(what="x86_64", arch="x86_64", vmid=900, tier="shell", doom=False, fps=False,
                               display=None, node=None, storage="local", name=None, start=False,
                               dir=tempfile.gettempdir(), kit_from="/nonexistent", fb_from="/nonexistent",
                               wad=None)
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_existing_vmid(self):
        with mock.patch.object(wisp_vm, "vm_exists", return_value=True), \
                mock.patch.object(wisp_vm, "run") as run:
            with self.assertRaisesRegex(wisp_vm.WispError, "exists already"):
                wisp_vm.create(self.args())
            run.assert_not_called()

    def test_other_node(self):
        with mock.patch.object(wisp_vm, "vm_exists", return_value=False), \
                mock.patch.object(wisp_vm, "node", return_value="pve1"):
            with self.assertRaisesRegex(wisp_vm.WispError, "run wisp-vm on that node"):
                wisp_vm.create(self.args(node="pve2"))

    def test_actions_only_on_tagged_vms(self):
        conf = "name: something\ntags: production;web\n"
        with mock.patch.object(wisp_vm, "vm_exists", return_value=True), \
                mock.patch.object(wisp_vm, "run", return_value=conf) as run:
            with self.assertRaisesRegex(wisp_vm.WispError, "only acts on VMs it made"):
                wisp_vm.action(self.args(what="destroy"))
            self.assertEqual([c.args[0] for c in run.call_args_list], ["qm"])  # only `qm config`
        conf = f"name: wisp\ntags: {wisp_vm.TAG}\n"
        with mock.patch.object(wisp_vm, "vm_exists", return_value=True), \
                mock.patch.object(wisp_vm, "run", return_value=conf) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            wisp_vm.action(self.args(what="stop"))
            self.assertEqual(run.call_args_list[-1].args, ("qm", "stop", 900))

    def test_cli(self):
        p = argparse.ArgumentParser()
        sub = p.add_subparsers(dest="cmd")
        wisp_vm.add_commands(sub)
        a = p.parse_args(["wisp-vm", "sparc32", "--doom", "--vmid", "902", "--display", "tcx"])
        self.assertEqual((a.what, a.doom, a.vmid, a.display), ("sparc32", True, 902, "tcx"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            p.parse_args(["wisp-vm", "mips"])
        self.assertTrue(re.search(r"wisp-vm", p.format_help()))


if __name__ == "__main__":
    unittest.main()
