"""Install once, then boot-test the stored disk (install.py --export / boot-test, pve_matrix.py's install
matrix), the parts that need no PVE node: the stored disk's name and sidecar, the atomic sparse copy,
the refusals and what the matrix decides per target. Standard library only:

    cd e2e/sparc && python3 -m unittest -v tests/test_stored_disks.py
"""
import argparse
import json
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import install  # noqa: E402
import pve_matrix  # noqa: E402
import targets  # noqa: E402


def parser():
    p = argparse.ArgumentParser()
    install.add_commands(p.add_subparsers(dest="cmd"))
    return p


def store(d, target, src_bytes=b"disk", **meta):
    src = os.path.join(d, "src.raw")
    with open(src, "wb") as f:
        f.write(src_bytes)
    try:
        return install.write_stored_disk(src, d, target, {"installed": "2026-11-19T10:00:00Z", **meta})
    finally:
        os.unlink(src)


class StoredDisk(unittest.TestCase):
    def test_names(self):
        self.assertEqual(install.stored_disk("/mnt/os/disks", "tribblix-m34-sun4u"),
                         ("/mnt/os/disks/install-tribblix-m34-sun4u.raw", "/mnt/os/disks/install-tribblix-m34-sun4u.json"))
        # never the hand-made disks matrix.py boots (same directory)
        import matrix
        handmade = {v for k, v in vars(matrix).items() if isinstance(v, str) and v.endswith(".raw")}
        for t in targets.automated():
            self.assertNotIn(os.path.basename(install.stored_disk("/d", t)[0]), handmade)

    def test_sidecar_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as d:
            raw, side = store(d, "netbsd111-sparc", b"old", minutes=7.1)
            meta = install.read_sidecar(d, "netbsd111-sparc")
            self.assertEqual((meta["target"], meta["by"], meta["disk"], meta["bytes"], meta["minutes"]),
                             ("netbsd111-sparc", install.STORED_BY, "install-netbsd111-sparc.raw", 3, 7.1))
            store(d, "netbsd111-sparc", b"newer", minutes=6.9)
            with open(raw, "rb") as f:
                self.assertEqual(f.read(), b"newer")
            self.assertEqual(install.read_sidecar(d, "netbsd111-sparc")["minutes"], 6.9)
            self.assertEqual(sorted(os.listdir(d)), ["install-netbsd111-sparc.json", "install-netbsd111-sparc.raw"])

    def test_failed_copy_keeps_the_old_disk(self):
        with tempfile.TemporaryDirectory() as d:
            raw, _ = store(d, "sol26-ss5", b"good")
            with self.assertRaises(OSError):
                install.write_stored_disk(os.path.join(d, "missing.raw"), d, "sol26-ss5", {})
            with open(raw, "rb") as f:
                self.assertEqual(f.read(), b"good")
            self.assertEqual(sorted(os.listdir(d)), ["install-sol26-ss5.json", "install-sol26-ss5.raw"])

    def test_sparse_copy(self):
        with tempfile.TemporaryDirectory() as d:
            src, dest = os.path.join(d, "a"), os.path.join(d, "b")
            data = b"x" * 100 + bytes(3 << 20) + b"tail" + bytes(5000)
            with open(src, "wb") as f:
                f.write(data)
            install.sparse_copy(src, dest)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), data)
            if hasattr(os.stat(dest), "st_blocks"):  # holes where the source has zero blocks
                self.assertLess(os.stat(dest).st_blocks * 512, len(data))

    def test_foreign_files_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            raw, side = install.stored_disk(d, "sol26-ss5")
            self.assertIsNone(install.read_sidecar(d, "sol26-ss5"))
            open(raw, "wb").close()  # a disk without a sidecar
            with self.assertRaisesRegex(install.InstallFailed, "no readable sidecar"):
                install.read_sidecar(d, "sol26-ss5")
            with open(side, "w") as f:
                json.dump({"target": "sol7-ss5", "by": install.STORED_BY}, f)
            with self.assertRaisesRegex(install.InstallFailed, "isn't the sidecar of sol26-ss5"):
                install.read_sidecar(d, "sol26-ss5")
            os.unlink(raw)
            with self.assertRaisesRegex(install.InstallFailed, "without install-sol26-ss5.raw"):
                install.read_sidecar(d, "sol26-ss5")


class Export(unittest.TestCase):
    def args(self, d, *extra):
        return parser().parse_args(["install", "sol26-ss5", "--vmid", "9950", "--check", "--export", d, *extra])

    def test_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.export_problems(self.args(d)), [])
            self.assertEqual(install.export_problems(self.args(d, "--disk-size", "9G", "--ip", "10.0.2.20")), [])
            store(d, "sol26-ss5")  # replacing its own stored disk
            self.assertEqual(install.export_problems(self.args(d)), [])
        self.assertEqual(install.export_problems(parser().parse_args(["install", "sol26-ss5", "--vmid", "1"])), [])

    def test_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            a = parser().parse_args(["install", "sol26-ss5", "--vmid", "1", "--export", d])
            self.assertIn("--export needs --check", " ".join(install.export_problems(a)))
            for extra, opt in ((["--root-password", "x"], "--root-password"), (["--user", "lab"], "--user"),
                               (["--data-disk", "2"], "--data-disk"), (["--template"], "--template")):
                with self.subTest(opt=opt):
                    self.assertIn(f"not one with {opt}", " ".join(install.export_problems(self.args(d, *extra))))
            self.assertIn("no such directory", " ".join(install.export_problems(self.args(os.path.join(d, "nope")))))
            open(install.stored_disk(d, "sol26-ss5")[0], "wb").close()
            self.assertIn("no readable sidecar", " ".join(install.export_problems(self.args(d))))

    def test_cmd_install_refuses_before_anything(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit) as e:
            install.cmd_install(parser().parse_args(["install", "sol26-ss5", "--vmid", "1", "--export", d]))
        self.assertIn("--export needs --check", str(e.exception))


class BootTest(unittest.TestCase):
    def args(self, disk, target="tribblix-m34-sun4u"):
        return parser().parse_args(["boot-test", target, "--disk", disk, "--vmid", "9951"])

    def test_problems(self):
        with tempfile.TemporaryDirectory() as d:
            raw, _ = install.stored_disk(d, "tribblix-m34-sun4u")
            self.assertIn("no such file", install.boot_test_problems(self.args(raw))[0][0])
            store(d, "tribblix-m34-sun4u", packages={"pve-qemu-kvm": "11.1.3-2+wsh21"})
            problems, meta = install.boot_test_problems(self.args(raw))
            self.assertEqual((problems, meta["packages"]["pve-qemu-kvm"]), ([], "11.1.3-2+wsh21"))
            # another target's disk, or a disk under another name
            self.assertIn("stored disk is named install-sol10-sun4u.raw",
                          install.boot_test_problems(self.args(raw, "sol10-sun4u"))[0][0])
            self.assertIn("unknown target", install.boot_test_problems(self.args(raw, "nope"))[0][0])
            with self.assertRaises(SystemExit) as e:
                install.cmd_boot_test(self.args(os.path.join(d, "sol10-sun4u-installed.raw"), "sol10-sun4u"))
            self.assertIn("stored disk is named", str(e.exception))

    def test_vm_params(self):
        a = types.SimpleNamespace(target="tribblix-m34-sun4u", vmid="9951", bridge="vmbr0", storage="local", name=None)
        p = install.boot_test_vm_params(targets.TARGETS[a.target], a, "/mnt/os/disks/install-tribblix-m34-sun4u.raw")
        self.assertEqual(p["ide0"], "local:0,import-from=/mnt/os/disks/install-tribblix-m34-sun4u.raw,format=raw")
        self.assertEqual((p["ide2"], p["boot"], p["net0"], p["memory"], p["machine"]),
                         ("none,media=cdrom", "order=ide0", "sunhme,bridge=vmbr0", 2048, "sun4u"))
        self.assertEqual(p["name"], "tribblix-m34-sun4u-boot-test")
        a.target = "msdos622"  # floppy drives stay empty floppies (as lab.pve_set_medium leaves them)
        p = install.boot_test_vm_params(targets.TARGETS[a.target], a, "/d/x.raw")
        for med in targets.TARGETS[a.target]["media"]:
            self.assertEqual(p[med["drive"]], "none" if med["drive"].startswith("floppy") else "none,media=cdrom")


class MatrixPlan(unittest.TestCase):
    def test_every_automated_target_is_a_case(self):
        self.assertEqual([c[1]["target"] for c in pve_matrix.MATRICES["install"]], targets.automated())

    def test_plan(self):
        slow = "tribblix-m34-sun4u"
        self.assertTrue(targets.TARGETS[slow].get("matrix_skip"))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pve_matrix.plan("netbsd111-sparc", d)[0], "install")
            self.assertEqual(pve_matrix.plan(slow, d)[0], "skip")
            self.assertIn(f"--reinstall {slow}", pve_matrix.plan(slow, d)[1])
            self.assertEqual(pve_matrix.plan(slow, d, {"all"})[0], "skip")  # `all` leaves the slow ones out
            self.assertEqual(pve_matrix.plan(slow, d, {slow})[0], "install")
            store(d, "netbsd111-sparc")
            store(d, slow)
            self.assertEqual(pve_matrix.plan("netbsd111-sparc", d)[0], "boot-test")
            self.assertEqual(pve_matrix.plan(slow, d)[0], "boot-test")
            self.assertEqual(pve_matrix.plan("netbsd111-sparc", d, {"all"})[0], "install")
            self.assertEqual(pve_matrix.plan(slow, d, {"all"})[0], "boot-test")
            self.assertEqual(pve_matrix.plan(slow, d, {slow})[0], "install")
            open(install.stored_disk(d, "sol26-ss5")[0], "wb").close()  # not ours: never replaced
            self.assertEqual(pve_matrix.plan("sol26-ss5", d, {"all", "sol26-ss5"})[0], "refuse")

    def test_reinstall_values(self):
        self.assertEqual(pve_matrix.reinstall_set(None), set())
        self.assertEqual(pve_matrix.reinstall_set(["all"]), {"all"})
        self.assertEqual(pve_matrix.reinstall_set(["sol26-ss5,netbsd111-sparc", " tribblix-m34-sun4u "]),
                         {"sol26-ss5", "netbsd111-sparc", "tribblix-m34-sun4u"})
        self.assertEqual(pve_matrix.reinstall_set([""]), set())  # the workflow input's default
        with self.assertRaisesRegex(SystemExit, "nope"):
            pve_matrix.reinstall_set(["sol26-ss5 nope"])

    def test_skipped_case_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            a = types.SimpleNamespace(runs=d, disks=d, reinstall=set(), timeout=3600)
            res = pve_matrix.run_case("install-tribblix-m34-sun4u", {"target": "tribblix-m34-sun4u"}, None, None, [], a)
            self.assertEqual((res["code"], res.get("skipped"), res["steps"]), (0, True, []))
            open(install.stored_disk(d, "sol26-ss5")[0], "wb").close()
            res = pve_matrix.run_case("install-sol26-ss5", {"target": "sol26-ss5"}, None, None, [], a)
            self.assertEqual(res["code"], 3)
            self.assertIn("refused", res["status"])

    def test_timeouts(self):
        a = types.SimpleNamespace(timeout=3600)
        self.assertEqual(pve_matrix.boot_test_timeout("tribblix-m34-sun4u", a), 4200)
        self.assertEqual(pve_matrix.boot_test_timeout("netbsd111-sparc", a), 3600)


if __name__ == "__main__":
    unittest.main()
