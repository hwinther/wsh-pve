"""Tests of wsh-sun-proms (sun_proms.py): the manifest, the checks, the choice of files from a
source and the commands, all against fake PROMs and a test manifest written here (never real
images). The git case needs git and is skipped without it; the HTTP case serves the fake files from
127.0.0.1.

  python3 -m unittest -v test_sun_proms.py          (in packages/wsh-lab/sun-proms)
"""

import contextlib
import functools
import hashlib
import http.server
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sun_proms as sp  # noqa: E402

# Fake images: what matters is that each has its own size and hash
FAKE = {
    "ss5.bin": b"fake SS-5 PROM\n" * 100,
    "ss20_v2.25_rom": b"fake SS-20 PROM\n" * 200,
    "lx.bin": b"fake LX PROM\n" * 50,
}
MACHINES = {"ss5.bin": "SS-5", "ss20_v2.25_rom": "SS-20", "lx.bin": "LX"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest_doc(files=FAKE):
    return {
        "proms": [
            {"name": n, "machine": MACHINES.get(n, "X"), "size": len(d), "sha256": sha(d), "description": f"test {n}"}
            for n, d in files.items()
        ]
    }


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-sun-proms.")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.manifest_path = self.write_json("manifest.json", manifest_doc())
        self.manifest = sp.load_manifest(self.manifest_path)
        self.kvm = os.path.join(self.tmp, "kvm")
        self.state = os.path.join(self.tmp, "var", "installed.tsv")
        # no dpkg-query (a Debian host has one; a fake one is put on PATH where it matters)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self.bin + os.pathsep + "/usr/bin:/bin"
        self.addCleanup(os.environ.__setitem__, "PATH", old_path)
        self.no_dpkg()

    def no_dpkg(self):
        self.fake_dpkg({})

    def fake_dpkg(self, owned):
        """A dpkg-query on PATH that owns OWNED ({path: package})."""
        lines = "\n".join(f'  "{p}") echo "{pkg}: {p}"; exit 0 ;;' for p, pkg in owned.items())
        path = os.path.join(self.bin, "dpkg-query")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/sh\ncase "$2" in\n{lines}\nesac\necho "dpkg-query: no path found matching pattern $2" >&2\nexit 1\n')
        os.chmod(path, 0o755)

    def write_json(self, name, doc):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        return p

    def source_dir(self, files, sub="src"):
        d = os.path.join(self.tmp, sub)
        for n, data in files.items():
            p = os.path.join(d, n)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)
        return d

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        common = ["--dir", self.kvm, "--manifest", self.manifest_path, "--state", self.state]
        argv = [argv[0], *common, *argv[1:]]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = sp.main(argv)
        return rc, out.getvalue(), err.getvalue()


class ManifestTest(Tmp):
    def test_the_shipped_manifest_loads(self):
        m = sp.load_manifest(sp.DEFAULT_MANIFEST)
        self.assertEqual(
            [p.name for p in m.proms], ["ss5.bin", "ss10_v2.25_rom", "ss20_v2.25_rom", "lx.bin", "ss600mp.bin"]
        )
        self.assertEqual({p.machine for p in m.proms}, {"SS-5", "SS-10", "SS-20", "LX", "SS-600MP"})

    def test_bad_entries_are_refused(self):
        good = manifest_doc()["proms"][0]
        cases = {
            "bad sha": [dict(good, sha256="ABC")],
            "upper-case sha": [dict(good, sha256=good["sha256"].upper())],
            "path in name": [dict(good, name="../ss5.bin")],
            "hidden name": [dict(good, name=".ss5")],
            "zero size": [dict(good, size=0)],
            "size as text": [dict(good, size="262144")],
            "no machine": [{k: v for k, v in good.items() if k != "machine"}],
            "name twice": [good, dict(good, sha256="0" * 64)],
            "sha twice": [good, dict(good, name="other.bin")],
        }
        for what, proms in cases.items():
            with self.subTest(what):
                p = self.write_json("bad.json", {"proms": proms})
                with self.assertRaises(sp.Error):
                    sp.load_manifest(p)
        p = self.write_json("empty.json", {"proms": []})
        with self.assertRaises(sp.Error):
            sp.load_manifest(p)

    def test_check(self):
        self.assertEqual(sp.check(self.manifest, "ss5.bin", FAKE["ss5.bin"]), "ok")
        self.assertEqual(sp.check(self.manifest, "ss5.bin", FAKE["ss5.bin"] + b"x"), "mismatch")
        self.assertEqual(sp.check(self.manifest, "ss5.bin", FAKE["lx.bin"]), "mismatch")
        self.assertEqual(sp.check(self.manifest, "other.bin", FAKE["lx.bin"]), "unknown")


class SourceTest(Tmp):
    def test_credentials_are_stripped(self):
        self.assertEqual(sp.strip_credentials("https://user:tok@example.org/p/x.git?t=1#f"), "https://example.org/p/x.git")
        self.assertEqual(sp.strip_credentials("ssh://git@example.org:2222/x.git"), "ssh://example.org:2222/x.git")
        self.assertEqual(sp.strip_credentials("git@example.org:you/proms.git"), "git@example.org:you/proms.git")
        self.assertEqual(sp.strip_credentials("/srv/proms"), "/srv/proms")

    def test_source_kind(self):
        d = self.source_dir(FAKE)
        archive = os.path.join(self.tmp, "p.tar")
        with tarfile.open(archive, "w"):
            pass
        self.assertEqual(sp.source_kind(d), "dir")
        self.assertEqual(sp.source_kind(archive), "archive")
        self.assertEqual(sp.source_kind("git@example.org:you/proms.git"), "git")
        self.assertEqual(sp.source_kind("https://example.org/you/proms.git"), "git")
        self.assertEqual(sp.source_kind("ssh://example.org/proms"), "git")
        self.assertEqual(sp.source_kind("https://example.org/proms/"), "http")
        self.assertEqual(sp.source_kind("https://example.org/proms/", "git"), "git")
        with self.assertRaises(sp.Error):
            sp.source_kind(os.path.join(self.tmp, "nothing"))

    def test_plain_http_only_to_this_host(self):
        sp.check_http_url("https://example.org/p/")
        sp.check_http_url("http://127.0.0.1:8080/p/")
        with self.assertRaises(sp.Error):
            sp.check_http_url("http://example.org/p/")
        with self.assertRaises(sp.Error):
            sp.check_http_url("ftp://example.org/p/")

    def test_archives_are_read_in_memory(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for n, data in [("proms/ss5.bin", FAKE["ss5.bin"]), ("../escape/lx.bin", FAKE["lx.bin"])]:
                info = tarfile.TarInfo(n)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("proms/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            t.addfile(link)
        cands = sp.archive_candidates(buf.getvalue(), "t.tgz")
        self.assertEqual(sorted(c.name for c in cands), ["lx.bin", "ss5.bin"])  # no symlink
        self.assertEqual({c.name: c.load() for c in cands}["lx.bin"], FAKE["lx.bin"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "..", "escape")))

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as z:
            z.writestr("a/ss20_v2.25_rom", FAKE["ss20_v2.25_rom"])
            z.writestr("a/", "")
        cands = sp.archive_candidates(zbuf.getvalue(), "t.zip")
        self.assertEqual([c.name for c in cands], ["ss20_v2.25_rom"])
        with self.assertRaises(sp.Error):
            sp.archive_candidates(b"not an archive at all", "x")


class PickTest(Tmp):
    def cands(self, files):
        return sp.dir_candidates(self.source_dir(files))

    def test_by_name_and_renamed(self):
        files = {"ss5.bin": FAKE["ss5.bin"], "sub/SS20-OBP-2.25.rom": FAKE["ss20_v2.25_rom"], "README": b"hi"}
        plan, problems, missing = sp.pick(self.manifest, self.cands(files), list(FAKE), False)
        self.assertEqual(problems, [])
        self.assertEqual(missing, ["lx.bin"])
        self.assertEqual({n: (c.path, v) for n, c, _, v in plan},
                         {"ss5.bin": ("ss5.bin", "ok"), "ss20_v2.25_rom": ("sub/SS20-OBP-2.25.rom", "ok")})

    def test_mismatch_refused_unless_forced(self):
        files = {"ss5.bin": b"something else"}
        plan, problems, _ = sp.pick(self.manifest, self.cands(files), ["ss5.bin"], False)
        self.assertEqual(plan, [])
        self.assertIn("--force", problems[0])
        plan, problems, _ = sp.pick(self.manifest, self.cands(files), ["ss5.bin"], True)
        self.assertEqual([(n, v) for n, _, _, v in plan], [("ss5.bin", "mismatch")])
        self.assertEqual(problems, [])

    def test_right_copy_wins_over_wrong_one(self):
        files = {"old/ss5.bin": b"x" * len(FAKE["ss5.bin"]), "new/ss5.bin": FAKE["ss5.bin"]}
        plan, problems, _ = sp.pick(self.manifest, self.cands(files), ["ss5.bin"], False)
        self.assertEqual(problems, [])
        self.assertEqual([(c.path, v) for _, c, _, v in plan], [("new/ss5.bin", "ok")])

    def test_unknown_refused_unless_forced(self):
        files = {"cpu10.bin": b"other"}
        plan, problems, _ = sp.pick(self.manifest, self.cands(files), ["cpu10.bin"], False)
        self.assertEqual(plan, [])
        self.assertIn("unknown", problems[0])
        plan, _, _ = sp.pick(self.manifest, self.cands(files), ["cpu10.bin"], True)
        self.assertEqual([(n, v) for n, _, _, v in plan], [("cpu10.bin", "unknown")])


class CommandTest(Tmp):
    def test_install_status_verify_remove(self):
        src = self.source_dir({"ss5.bin": FAKE["ss5.bin"], "lx.bin": FAKE["lx.bin"]})
        rc, out, err = self.run_cli("install", "--source", src)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("ss5.bin          installed", out)
        self.assertIn("ss20_v2.25_rom   not in the source", out)
        for n in ("ss5.bin", "lx.bin"):
            p = os.path.join(self.kvm, n)
            with open(p, "rb") as f:
                self.assertEqual(f.read(), FAKE[n])
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o644)
        self.assertEqual(sorted(os.listdir(self.kvm)), ["lx.bin", "ss5.bin"])  # no temporary files left

        # idempotent: a second run changes nothing and succeeds
        os.chmod(os.path.join(self.kvm, "lx.bin"), 0o600)
        rc, out, _ = self.run_cli("install", "--source", src)
        self.assertEqual(rc, 0)
        self.assertIn("lx.bin           already installed", out)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.kvm, "lx.bin")).st_mode), 0o644)

        rc, out, _ = self.run_cli("status", "--json")
        self.assertEqual(rc, 0)
        rows = {r["name"]: r for r in json.loads(out)["proms"]}
        self.assertEqual(rows["ss5.bin"]["state"], "ok")
        self.assertIn(f"wsh-sun-proms, from {os.path.abspath(src)}", rows["ss5.bin"]["source"])
        self.assertEqual(rows["ss20_v2.25_rom"]["state"], "missing")

        self.assertEqual(self.run_cli("verify")[0], 0)
        self.assertEqual(self.run_cli("verify", "ss5.bin", "lx.bin")[0], 0)
        self.assertEqual(self.run_cli("verify", "ss20_v2.25_rom")[0], 1)
        self.assertEqual(self.run_cli("verify", "--all")[0], 1)

        # a file changed behind the tool's back
        with open(os.path.join(self.kvm, "lx.bin"), "ab") as f:
            f.write(b"!")
        rc, out, err = self.run_cli("verify")
        self.assertEqual(rc, 1)
        self.assertIn("lx.bin", err)
        self.assertIn("changed since wsh-sun-proms installed it", out)
        rc, _, err = self.run_cli("remove")
        self.assertEqual(rc, 1)  # ss5.bin removed, lx.bin kept
        self.assertFalse(os.path.exists(os.path.join(self.kvm, "ss5.bin")))
        self.assertTrue(os.path.exists(os.path.join(self.kvm, "lx.bin")))
        rc, _, _ = self.run_cli("remove", "--force")
        self.assertEqual(rc, 0)
        self.assertEqual(os.listdir(self.kvm), [])
        self.assertFalse(os.path.exists(self.state))  # record and its directory gone
        self.assertFalse(os.path.exists(os.path.dirname(self.state)))
        self.assertEqual(self.run_cli("remove")[0], 0)  # nothing left: still fine

    def test_refusals(self):
        src = self.source_dir({"ss5.bin": b"not the right one", "cpu10.bin": b"unknown"})
        rc, _, err = self.run_cli("install", "--source", src)
        self.assertEqual(rc, 1)
        self.assertIn("refused: ss5.bin", err)
        self.assertFalse(os.path.exists(self.kvm))
        rc, _, err = self.run_cli("install", "--source", src, "cpu10.bin")
        self.assertEqual(rc, 1)
        self.assertIn("unknown to the manifest", err)
        rc, _, err = self.run_cli("install", "--source", src, "lx.bin")
        self.assertEqual(rc, 1)
        self.assertIn("lx.bin: not in the source", err)
        rc, _, err = self.run_cli("install", "--source", self.source_dir({"x": b"y"}, "empty"))
        self.assertEqual(rc, 1)
        self.assertIn("no known Sun PROM", err)

        # with --force: installed, and reported as unknown/mismatching
        rc, out, _ = self.run_cli("install", "--source", src, "--force", "ss5.bin", "cpu10.bin")
        self.assertEqual(rc, 0, out)
        rc, out, err = self.run_cli("verify")
        self.assertEqual(rc, 1)
        self.assertIn("MISMATCH", out)
        self.assertIn("cpu10.bin", out)
        # a different file already there is not replaced without --force
        good = self.source_dir({"ss5.bin": FAKE["ss5.bin"]}, "good")
        rc, _, err = self.run_cli("install", "--source", good)
        self.assertEqual(rc, 1)
        self.assertIn("--force replaces it", err)
        self.assertEqual(self.run_cli("install", "--source", good, "--force")[0], 0)
        self.assertEqual(self.run_cli("verify", "ss5.bin")[0], 0)
        # remove never touches a file it neither knows nor installed
        with open(os.path.join(self.kvm, "openbios-sparc32"), "wb") as f:
            f.write(b"x")
        self.assertEqual(self.run_cli("remove", "--force", "openbios-sparc32")[0], 1)
        self.assertTrue(os.path.exists(os.path.join(self.kvm, "openbios-sparc32")))
        self.assertEqual(self.run_cli("remove")[0], 0)
        self.assertEqual(os.listdir(self.kvm), ["openbios-sparc32"])

    def test_dry_run_changes_nothing(self):
        src = self.source_dir(FAKE)
        rc, out, _ = self.run_cli("install", "--source", src, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("would install", out)
        self.assertFalse(os.path.exists(self.kvm))
        self.assertFalse(os.path.exists(self.state))

    def test_package_files_are_left_alone(self):
        os.makedirs(self.kvm)
        pkg_file = os.path.join(self.kvm, "ss5.bin")
        with open(pkg_file, "wb") as f:
            f.write(FAKE["ss5.bin"])
        self.fake_dpkg({pkg_file: "pve-qemu-kvm"})
        src = self.source_dir(FAKE)
        rc, out, _ = self.run_cli("install", "--source", src)
        self.assertEqual(rc, 0)
        self.assertIn("ss5.bin          already there, from package pve-qemu-kvm", out)
        rc, out, _ = self.run_cli("status")
        self.assertRegex(out, r"ss5.bin +SS-5 +ok +package pve-qemu-kvm")
        self.assertRegex(out, r"lx.bin +LX +ok +wsh-sun-proms, from ")
        rc, out, _ = self.run_cli("remove", "--force")
        self.assertEqual(rc, 0)
        self.assertIn("kept: it belongs to package pve-qemu-kvm", out)
        self.assertEqual(os.listdir(self.kvm), ["ss5.bin"])
        # a package's differing file isn't replaced without --force
        with open(pkg_file, "wb") as f:
            f.write(b"older")
        rc, _, err = self.run_cli("install", "--source", src, "ss5.bin")
        self.assertEqual(rc, 1)
        self.assertIn("package pve-qemu-kvm's file", err)

    def test_archive_source(self):
        archive = os.path.join(self.tmp, "proms.tar.xz")
        with tarfile.open(archive, "w:xz") as t:
            for n, data in FAKE.items():
                info = tarfile.TarInfo(f"proms-1/{n}")
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        rc, out, err = self.run_cli("install", "--source", archive)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(sorted(os.listdir(self.kvm)), sorted(FAKE))
        self.assertEqual(self.run_cli("verify", "--all")[0], 0)

    @unittest.skipUnless(shutil.which("git", path="/usr/bin:/bin"), "needs git")
    def test_git_source(self):
        work = self.source_dir(FAKE, "work")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL="/dev/null")
        for cmd in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "-m", "fake proms"]):
            subprocess.run(["git", *cmd], cwd=work, env=env, check=True)
        bare = os.path.join(self.tmp, "proms.git")
        subprocess.run(["git", "clone", "-q", "--bare", work, bare], env=env, check=True)
        url = "file://" + bare
        old = os.environ.get("GIT_CONFIG_GLOBAL")
        os.environ["GIT_CONFIG_GLOBAL"] = "/dev/null"
        self.addCleanup(lambda: os.environ.pop("GIT_CONFIG_GLOBAL") if old is None else os.environ.__setitem__("GIT_CONFIG_GLOBAL", old))
        rc, out, err = self.run_cli("install", "--source", url, "--ref", "main")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("(git)", out)
        self.assertEqual(sorted(os.listdir(self.kvm)), sorted(FAKE))
        # a bare repository path is cloned as well
        shutil.rmtree(self.kvm)
        os.unlink(self.state)
        self.assertEqual(self.run_cli("install", "--source", bare)[0], 0)
        rc, _, err = self.run_cli("install", "--source", "file://" + os.path.join(self.tmp, "none.git"))
        self.assertEqual(rc, 1)
        self.assertIn("git clone", err)

    def test_http_source(self):
        served = self.source_dir({"ss5.bin": FAKE["ss5.bin"], "lx.bin": FAKE["lx.bin"]}, "www/proms")
        handler = functools.partial(QuietHandler, directory=os.path.dirname(served))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://user:secret@127.0.0.1:{server.server_port}/proms"
        rc, out, err = self.run_cli("install", "--source", base)
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("secret", out + err)
        self.assertEqual(sorted(os.listdir(self.kvm)), ["lx.bin", "ss5.bin"])
        with open(self.state, encoding="utf-8") as f:
            recorded = f.read()
        self.assertIn(f"http://127.0.0.1:{server.server_port}/proms", recorded)
        self.assertNotIn("secret", recorded)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    unittest.main()
