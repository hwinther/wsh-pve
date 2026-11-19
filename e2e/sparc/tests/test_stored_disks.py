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

    def test_debian_needs_no_network_options(self):
        """A boot test installs nothing: the Debian targets' net_require (--gateway/--dns for the
        netinst) doesn't apply, as cmd_boot_test marks with `boot_test` (it used to refuse)."""
        a = types.SimpleNamespace(target="debian40-ss5", ip=None, netmask=None, gateway=None, dns=None, domain=None,
                                  vlan=None, bridge="vmbr0", apt_proxy=None)
        t = targets.TARGETS["debian40-ss5"]
        with self.assertRaises(SystemExit):
            install.network_choice(t, a)
        a.boot_test = True
        self.assertEqual(install.network_choice(t, a)["gateway"], None)

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

    def test_plan_apt_cache(self):
        """Debian's netinst (matrix_needs apt_cache) installs only with an apt cache; without one it is
        skipped, also when --reinstall names it; a stored disk is boot-tested either way."""
        deb, cache = "debian40-ss5", "aptcache.example:3142"
        self.assertEqual(targets.TARGETS[deb].get("matrix_needs"), "apt_cache")
        self.assertIsNone(targets.TARGETS[deb].get("matrix_skip"))
        with tempfile.TemporaryDirectory() as d:
            action, why = pve_matrix.plan(deb, d)
            self.assertEqual(action, "skip")
            self.assertIn("WSH_LAB_APT_CACHE", why)
            self.assertEqual(pve_matrix.plan(deb, d, {deb})[0], "skip")
            self.assertEqual(pve_matrix.plan(deb, d, apt_cache=cache)[0], "install")
            self.assertEqual(pve_matrix.plan(deb, d, {deb}, cache)[0], "install")
            store(d, deb)
            self.assertEqual(pve_matrix.plan(deb, d)[0], "boot-test")
            self.assertEqual(pve_matrix.plan(deb, d, {"all"})[0], "boot-test")
            self.assertEqual(pve_matrix.plan(deb, d, {"all"}, cache)[0], "install")

    def test_apt_cache_choice(self):
        self.assertIsNone(pve_matrix.apt_cache_choice(None))
        self.assertIsNone(pve_matrix.apt_cache_choice(" "))  # an unset workflow variable
        for value in ("aptcache.example:3142", "http://aptcache.example:3142/", " aptcache.example:3142\n"):
            self.assertEqual(pve_matrix.apt_cache_choice(value), "aptcache.example:3142")
        self.assertEqual(pve_matrix.apt_cache_choice("192.0.2.7:3142"), "192.0.2.7:3142")
        for bad in ("aptcache.example", "aptcache.example:0", "aptcache.example:70000", "a b:3142",
                    "https://aptcache.example:3142", "aptcache.example:3142/debian", "-x:1"):
            with self.assertRaises(SystemExit, msg=bad) as e:
                pve_matrix.apt_cache_choice(bad)
            self.assertNotIn(bad.strip(), str(e.exception))  # never echoed (a workflow secret)

    def test_apt_cache_pinhole(self):
        """The guests get 10.0.2.2:3142 forwarded to the cache by socat, no IP forwarding, and the
        targets that fetch packages --apt-proxy there and no router or name server."""
        cmds = pve_matrix.apt_cache_pinhole_cmds("aptcache.example:3142")
        self.assertIn(["ip", "addr", "replace", "10.0.2.2/24", "dev", "vmbr0"], cmds)
        self.assertIn(["sysctl", "-q", "-w", "net.ipv4.ip_forward=0"], cmds)
        socat = cmds[-1]
        self.assertEqual(socat[:2], ["systemd-run", "--unit=wsh-lab-apt-cache"])
        self.assertEqual(socat[-2:], ["TCP4-LISTEN:3142,bind=10.0.2.2,fork,reuseaddr", "TCP:aptcache.example:3142"])
        self.assertFalse(any("MASQUERADE" in " ".join(c) or "iptables" in c[0] for c in cmds))  # no NAT
        a = types.SimpleNamespace(apt_cache="aptcache.example:3142")
        self.assertEqual(pve_matrix.install_net_args("debian40-ss20", a), ["--apt-proxy", "http://10.0.2.2:3142"])
        self.assertEqual(pve_matrix.install_net_args("sol26-ss5", a), [])
        self.assertEqual(pve_matrix.install_net_args("debian40-ss20", types.SimpleNamespace(apt_cache=None)), [])
        # what lab.py install then accepts: the proxy on the guest's network instead of --gateway/--dns
        args = parser().parse_args(["install", "debian40-ss20", "--vmid", "1",
                                    *pve_matrix.install_net_args("debian40-ss20", a)])
        net = install.network_choice(targets.TARGETS["debian40-ss20"], args)
        self.assertEqual((net["ip"], net["gateway"], net["dns"]), ("10.0.2.15", None, []))

    def test_pinhole_failure_fails_only_those_installs(self):
        with tempfile.TemporaryDirectory() as d:
            a = types.SimpleNamespace(runs=d, disks=d, reinstall=set(), timeout=3600, apt_cache="aptcache.example:3142",
                                      pinhole_error="apt cache pinhole: no HTTP answer through http://10.0.2.2:3142")
            res = pve_matrix.run_case("install-debian40-ss5", {"target": "debian40-ss5"}, None, None, [], a)
            self.assertEqual((res["code"], res["status"]), (3, a.pinhole_error))
            self.assertNotIn("aptcache.example", res["status"])
            store(d, "debian40-ss5")  # a stored disk is still boot-tested (needs no cache): not refused here
            self.assertEqual(pve_matrix.plan("debian40-ss5", d, apt_cache=a.apt_cache)[0], "boot-test")

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
