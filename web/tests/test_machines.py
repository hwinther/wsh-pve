"""The Browser SPARC machine table (docs/public/browser-sparc/machines.json) against the build and
the page: every machine's emulator, firmware and kernel is built and bundled, gets a snapshot, and
has a link in the page's picker.

    python3 -m unittest discover -s web/tests -v

Standard library only.
"""
import importlib.util
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PAGE = os.path.join(ROOT, "docs", "public", "browser-sparc")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").removesuffix(".py"),
                                                  os.path.join(ROOT, "web", "scripts", name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


snap = load_script("make-snapshot.py")
MACHINES = snap.load_machines(os.path.join(PAGE, "machines.json"))
ARCHES = ("sparc32", "sparc64", "x86_64", "aarch64")


class MachineTable(unittest.TestCase):
    def test_arches(self):
        self.assertEqual(tuple(MACHINES), ARCHES)

    def test_fields(self):
        for arch, m in MACHINES.items():
            with self.subTest(arch=arch):
                for key in ("name", "detail", "qemu", "args", "memory", "maxMemory", "files",
                            "kernel", "append", "snapshot"):
                    self.assertIn(key, m)
                self.assertEqual(m["kernel"], f"wisp-{arch}-kernel")
                self.assertLessEqual(m["memory"], m["maxMemory"])
                self.assertIn("wisp=shell", m["append"].split())
                # the console is the page's: no -serial, -chardev or -m in the table
                for opt in ("-serial", "-chardev", "-m", "-kernel", "-append"):
                    self.assertNotIn(opt, m["args"])

    def test_snapshot_names_unique(self):
        names = [m["snapshot"] for m in MACHINES.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_firmware_paths(self):
        for arch, m in MACHINES.items():
            with self.subTest(arch=arch):
                for name, path in m["files"].items():
                    self.assertEqual(path, "/fw/" + name)
                # every file the options name is written into the file system
                for arg in m["args"]:
                    if arg.startswith("/fw/"):
                        self.assertIn(arg, m["files"].values())

    def test_sparc32_command(self):
        # the SS-5's options as the page had them before the machine table (the kernel's path
        # aside: each machine's kernel has its own now)
        self.assertEqual(snap.machine_args(MACHINES["sparc32"]), [
            "-M", "SS-5", "-bios", "/fw/openbios-sparc32", "-m", "128", "-nodefaults",
            "-display", "none", "-monitor", "none", "-serial", "chardev:console",
            "-kernel", "/wisp/wisp-sparc32-kernel", "-append", "console=ttyS0 wisp=shell",
        ])
        self.assertEqual(snap.snapshot_name(MACHINES["sparc32"]), "wisp-ss5-128m")

    def test_page_files(self):
        self.assertEqual(snap.page_files(MACHINES["x86_64"]), {
            "bios-256k.bin": "/fw/bios-256k.bin", "linuxboot_dma.bin": "/fw/linuxboot_dma.bin",
            "kvmvapic.bin": "/fw/kvmvapic.bin", "wisp-x86_64-kernel": "/wisp/wisp-x86_64-kernel",
        })
        self.assertEqual(snap.page_files(MACHINES["aarch64"]),
                         {"wisp-aarch64-kernel": "/wisp/wisp-aarch64-kernel"})


class BuildCoversTable(unittest.TestCase):
    def test_qemu_targets(self):
        text = read("web", "scripts", "build-qemu.sh")
        targets = re.search(r"^TARGETS=\$\{TARGETS:-([^}]*)\}", text, re.M).group(1).split(",")
        targets += re.search(r"^MINIMAL_TARGETS=\$\{MINIMAL_TARGETS-([^}]*)\}", text, re.M).group(1).split(",")
        bins = {"qemu-system-" + t.removesuffix("-softmmu") for t in targets}
        self.assertEqual(bins, {m["qemu"] for m in MACHINES.values()})

    def test_dockerfile(self):
        text = read("web", "Dockerfile")
        loops = re.findall(r"for a in ([a-z0-9_ ]+); do", text)
        self.assertTrue(loops)
        for loop in loops:
            self.assertEqual(tuple(loop.split()), ARCHES)
        self.assertIn("./build.sh " + " ".join(ARCHES), text)
        bundle = text[text.index("AS bundle"):]
        for arch, m in MACHINES.items():
            for name in m["files"]:
                with self.subTest(file=name):
                    self.assertIn(name, bundle)

    def test_dockerignore(self):
        self.assertIn("!docs/public/browser-sparc/machines.json",
                      read("web", "Dockerfile.dockerignore").split())


class PageCoversTable(unittest.TestCase):
    def test_picker(self):
        html = read("docs", "public", "browser-sparc", "index.html")
        self.assertEqual(tuple(re.findall(r'data-arch="([^"]+)"', html)), ARCHES)

    def test_script_reads_table(self):
        js = read("docs", "public", "browser-sparc", "browser-sparc.js")
        self.assertIn('fetch("machines.json")', js)
        # the page's options in the order make-snapshot.py's machine_args() has them, around the
        # console's -chardev
        for opt in ('"-nodefaults"', '"-display", "none"', '"-monitor", "none"',
                    '"-serial", "chardev:console"', '"-kernel", kernelPath', '"-append", machine.append'):
            self.assertIn(opt, js)


if __name__ == "__main__":
    unittest.main()
