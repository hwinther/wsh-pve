"""The mirror storage tool (mirror.py) and the media lookup by size and sha256 (install.py), without a
PVE node: a storage.cfg in a temporary directory (WSH_LAB_STORAGE_CFG), source trees and storage
directories under it, and a fake `pvesm path`. Standard library only, no network:

    cd e2e/sparc && python3 -m unittest -v tests/test_mirror.py
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import install  # noqa: E402
import mirror  # noqa: E402
import targets  # noqa: E402

FLOPPY = 1474560


def write(path, size=0, data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        if data is not None:
            f.write(data)
        elif size:
            f.truncate(size)
    return path


class Env(unittest.TestCase):
    """A temporary node: storage.cfg with a dir storage `mirror` (iso, floppy), `isoonly` (iso), `nfs`
    (an nfs storage) and `alt` (content-dirs), and a source tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.store = os.path.join(t, "store")
        self.src = os.path.join(t, "nas")
        cfg = os.path.join(t, "storage.cfg")
        with open(cfg, "w") as f:
            f.write(f"""dir: local
\tpath {t}/local
\tcontent iso,vztmpl,backup

dir: mirror
\tpath {self.store}
\tcontent floppy,iso
\tshared 0

dir: isoonly
\tpath {t}/isoonly
\tcontent iso

dir: alt
\tpath {t}/alt
\tcontent iso,floppy
\tcontent-dirs iso=media/cd,floppy=media/fd

nfs: nas
\tpath /mnt/pve/nas
\tserver 192.0.2.1
\texport /media
\tcontent iso
""")
        os.environ["WSH_LAB_STORAGE_CFG"] = cfg
        self.addCleanup(os.environ.pop, "WSH_LAB_STORAGE_CFG", None)
        self.iso_dir = os.path.join(self.store, "template", "iso")
        self.fd_dir = os.path.join(self.store, "template", "floppy")

    def run_cmd(self, *argv):
        """(exit code, stdout) of `lab.py mirror <argv>`; a sys.exit message is the output too."""
        p = argparse.ArgumentParser()
        mirror.add_commands(p.add_subparsers(dest="cmd", required=True))
        a = p.parse_args(["mirror", *argv])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                rc = mirror.cmd_mirror(a)
            except SystemExit as e:
                rc = 1 if isinstance(e.code, str) else e.code
                if isinstance(e.code, str):
                    out.write(e.code)
        return rc, out.getvalue()


class TestNames(unittest.TestCase):
    def test_folders_joined_with_the_separator(self):
        self.assertEqual(mirror.link_name("Solaris/2.6/solaris_2.6_598_sparc.iso", "iso"),
                         "Solaris__2.6__solaris_2.6_598_sparc.iso")
        self.assertEqual(mirror.link_name("dos.img", "floppy"), "dos.img")
        self.assertEqual(mirror.folders("Solaris__2.6__solaris_2.6_598_sparc.iso"),
                         ["Solaris", "2.6", "solaris_2.6_598_sparc.iso"])

    def test_unsafe_characters_cleaned_like_a_pve_upload(self):
        self.assertEqual(mirror.link_name("MS DOS/6.22, en/Disk 1.IMG", "floppy"), "MS_DOS__6.22_en__Disk_1.IMG")
        self.assertEqual(mirror.clean("a  b"), "a_b")

    def test_names_that_would_not_split_back_are_refused(self):
        for rel in ("a__b/x.iso", "a/b__c.iso", "a_/x.iso", "a (1)/x.iso", "Ä/x.iso"):
            with self.subTest(rel=rel), self.assertRaises(mirror.MirrorError):
                mirror.link_name(rel, "iso")
        # a leading _ (also after a folder: 'a___x.iso' splits into 'a', '_x.iso'), a trailing one on
        # the file name are fine
        self.assertEqual(mirror.link_name("_old/x_.iso", "iso"), "_old__x_.iso")
        self.assertEqual(mirror.link_name("a/_x.iso", "iso"), "a___x.iso")
        self.assertEqual(mirror.folders("a___x.iso"), ["a", "_x.iso"])

    def test_extension_must_fit_the_content(self):
        with self.assertRaises(mirror.MirrorError):
            mirror.link_name("a/disk.ima", "iso")
        with self.assertRaises(mirror.MirrorError):
            mirror.link_name("a/cd.iso", "floppy")
        mirror.check_name("A__CD.ISO", "iso")
        for bad in ("a/b.iso", ".hidden.iso", "a b.iso", "a,b.iso", "__a.iso", "a____b.iso", "a.iso\n"):
            with self.subTest(bad=bad), self.assertRaises(mirror.MirrorError):
                mirror.check_name(bad, "iso")

    def test_content_by_extension_and_img_by_size(self):
        with tempfile.TemporaryDirectory() as d:
            small = write(os.path.join(d, "a.img"), FLOPPY)
            big = write(os.path.join(d, "b.img"), mirror.FLOPPY_MAX + 1)
            self.assertEqual(mirror.media_content(small), "floppy")
            self.assertEqual(mirror.media_content(big), "iso")
            self.assertEqual(mirror.media_content(small, "iso"), "iso")
            self.assertEqual(mirror.media_content(big, "floppy"), "floppy")
        self.assertEqual(mirror.media_content("x.ISO"), "iso")
        self.assertEqual(mirror.media_content("x.vfd"), "floppy")
        self.assertEqual(mirror.media_content("x.IMA"), "floppy")
        self.assertIsNone(mirror.media_content("x.bin"))

    def test_separator_matches_the_ui(self):
        # pve-manager.patch splits on the same separator and doesn't split names with an empty part
        patch = os.path.join(HERE, "..", "..", "submodules", "pve-manager.patch")
        if not os.path.exists(patch):
            self.skipTest("not in the repository")
        with open(patch, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(f"+        mirrorSeparator: '{mirror.SEPARATOR}'," in text, "the separator in pve-manager.patch")
        self.assertTrue("+        mirrorFolderContents: ['iso', 'floppy']," in text, "the content types in pve-manager.patch")
        self.assertEqual(mirror.folders("__a.iso"), ["__a.iso"])


class TestStorage(Env):
    def test_dirs_of_a_dir_storage(self):
        self.assertEqual(mirror.storage_dirs("mirror"), {"iso": self.iso_dir, "floppy": self.fd_dir})
        self.assertEqual(mirror.storage_dirs("isoonly"), {"iso": os.path.join(self.tmp.name, "isoonly", "template", "iso")})
        alt = os.path.join(self.tmp.name, "alt")
        self.assertEqual(mirror.storage_dirs("alt"), {"iso": os.path.join(alt, "media/cd"),
                                                      "floppy": os.path.join(alt, "media/fd")})

    def test_refusals(self):
        for storage, why in (("nas", "type nfs"), ("nosuch", "no storage"), ):
            with self.subTest(storage=storage):
                with self.assertRaisesRegex(mirror.MirrorError, why):
                    mirror.storage_dirs(storage)
        cfg = os.environ["WSH_LAB_STORAGE_CFG"]
        with open(cfg, "a") as f:
            f.write("\ndir: backups\n\tpath /x\n\tcontent backup\n")
        with self.assertRaisesRegex(mirror.MirrorError, "neither iso nor floppy"):
            mirror.storage_dirs("backups")


class TestLink(Env):
    def test_link_with_root_and_as(self):
        iso = write(os.path.join(self.src, "Solaris", "2.6", "solaris_2.6_598_sparc.iso"), 4096)
        rc, out = self.run_cmd("link", iso, "--storage", "mirror", "--root", self.src)
        self.assertEqual(rc, 0, out)
        self.assertIn("created  mirror:iso/Solaris__2.6__solaris_2.6_598_sparc.iso", out)
        link = os.path.join(self.iso_dir, "Solaris__2.6__solaris_2.6_598_sparc.iso")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), os.path.abspath(iso))
        self.assertTrue(os.path.isabs(os.readlink(link)))
        # again: already there
        rc, out = self.run_cmd("link", iso, "--storage", "mirror", "--root", self.src)
        self.assertEqual((rc, out.split()[0]), (0, "exists"))
        # without --root: the file name
        rc, out = self.run_cmd("link", iso, "--storage", "mirror")
        self.assertTrue(os.path.islink(os.path.join(self.iso_dir, "solaris_2.6_598_sparc.iso")), out)
        rc, out = self.run_cmd("link", iso, "--storage", "mirror", "--as", "sol26.iso")
        self.assertEqual(rc, 0, out)
        rc, out = self.run_cmd("link", iso, "--storage", "mirror", "--as", "a/b.iso")
        self.assertEqual(rc, 1)
        rc, out = self.run_cmd("link", iso, "--storage", "mirror", "--root", os.path.join(self.src, "Solaris", "7"))
        self.assertEqual(rc, 1)
        self.assertIn("isn't under --root", out)

    def test_floppy_goes_to_the_floppy_dir(self):
        img = write(os.path.join(self.src, "DOS", "6.22", "disk1.img"), FLOPPY)
        rc, out = self.run_cmd("link", img, "--storage", "mirror", "--root", self.src)
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.islink(os.path.join(self.fd_dir, "DOS__6.22__disk1.img")))
        # forced to iso
        rc, out = self.run_cmd("link", img, "--storage", "mirror", "--root", self.src, "--content", "iso")
        self.assertTrue(os.path.islink(os.path.join(self.iso_dir, "DOS__6.22__disk1.img")), out)
        # a storage without floppy content
        rc, out = self.run_cmd("link", img, "--storage", "isoonly")
        self.assertEqual(rc, 1)
        self.assertIn("no floppy content", out)

    def test_never_replaces_a_regular_file_and_replaces_a_link_only_with_force(self):
        a = write(os.path.join(self.src, "a", "x.iso"), 10)
        b = write(os.path.join(self.src, "b", "x.iso"), 20)
        regular = write(os.path.join(self.iso_dir, "upload.iso"), data=b"uploaded")
        rc, out = self.run_cmd("link", a, "--storage", "mirror", "--as", "upload.iso", "--force")
        self.assertEqual(rc, 1)
        self.assertIn("isn't a link", out)
        with open(regular, "rb") as f:
            self.assertEqual(f.read(), b"uploaded")
        self.assertFalse(os.path.islink(regular))
        self.run_cmd("link", a, "--storage", "mirror")
        rc, out = self.run_cmd("link", b, "--storage", "mirror")
        self.assertEqual(rc, 1)
        self.assertIn("--force", out)
        rc, out = self.run_cmd("link", b, "--storage", "mirror", "--force")
        self.assertEqual(rc, 0, out)
        self.assertEqual(os.readlink(os.path.join(self.iso_dir, "x.iso")), b)

    def test_not_a_medium(self):
        f = write(os.path.join(self.src, "readme.txt"), 1)
        rc, out = self.run_cmd("link", f, "--storage", "mirror")
        self.assertEqual(rc, 1)
        self.assertIn("not an ISO or floppy image", out)


class TestSyncAndList(Env):
    def tree(self):
        write(os.path.join(self.src, "Solaris", "2.6", "solaris_2.6_598_sparc.iso"), 8192)
        write(os.path.join(self.src, "Solaris", "7", "sol-7-sparc.ISO"), 8192)
        write(os.path.join(self.src, "DOS", "MS-DOS 6.22", "Disk 1.img"), FLOPPY)
        write(os.path.join(self.src, "DOS", "drivers.vfd"), FLOPPY)
        write(os.path.join(self.src, "top.iso"), 100)
        write(os.path.join(self.src, "notes.txt"), 1)

    def test_sync_links_the_tree_and_is_idempotent(self):
        self.tree()
        rc, out = self.run_cmd("sync", self.src, "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(os.listdir(self.iso_dir)),
                         ["Solaris__2.6__solaris_2.6_598_sparc.iso", "Solaris__7__sol-7-sparc.ISO", "top.iso"])
        self.assertEqual(sorted(os.listdir(self.fd_dir)), ["DOS__MS-DOS_6.22__Disk_1.img", "DOS__drivers.vfd"])
        self.assertIn("5 created, 0 already there, 0 pruned, 0 conflicts", out)
        rc, out = self.run_cmd("sync", self.src, "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("0 created, 5 already there", out)

    def test_dry_run_changes_nothing(self):
        self.tree()
        rc, out = self.run_cmd("sync", self.src, "--storage", "mirror", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn("5 created", out)
        self.assertFalse(os.path.exists(self.iso_dir))

    def test_conflicts_are_reported_and_skipped(self):
        self.tree()
        write(os.path.join(self.src, "bad__name", "x.iso"), 1)
        write(os.path.join(self.src, "dup", "a b.iso"), 1)
        write(os.path.join(self.src, "dup", "a_b.iso"), 1)
        write(os.path.join(self.iso_dir, "top.iso"), data=b"a regular file")
        rc, out = self.run_cmd("sync", self.src, "--storage", "mirror")
        self.assertEqual(rc, 1)
        self.assertIn("conflict", out)
        self.assertIn("bad__name", out)
        self.assertIn("dup__a_b.iso: the same name", out)
        self.assertIn("top.iso exists and isn't a link", out)
        self.assertFalse(os.path.lexists(os.path.join(self.iso_dir, "dup__a_b.iso")))
        self.assertFalse(os.path.islink(os.path.join(self.iso_dir, "top.iso")))
        self.assertTrue(os.path.islink(os.path.join(self.iso_dir, "Solaris__7__sol-7-sparc.ISO")))

    def test_prune_removes_only_dead_or_foreign_links(self):
        self.tree()
        self.run_cmd("sync", self.src, "--storage", "mirror")
        os.remove(os.path.join(self.src, "Solaris", "7", "sol-7-sparc.ISO"))
        other = write(os.path.join(self.tmp.name, "elsewhere", "other.iso"), 10)
        os.symlink(other, os.path.join(self.iso_dir, "other.iso"))
        regular = write(os.path.join(self.iso_dir, "uploaded.iso"), data=b"x")
        rc, out = self.run_cmd("list", "--storage", "mirror")
        self.assertEqual(rc, 1, out)  # a dangling link
        self.assertIn("dangling mirror:iso/Solaris__7__sol-7-sparc.ISO", out)
        self.assertIn("file     mirror:iso/uploaded.iso", out)
        rc, out = self.run_cmd("sync", self.src, "--storage", "mirror", "--prune")
        self.assertEqual(rc, 0, out)
        self.assertIn("pruned   mirror:iso/Solaris__7__sol-7-sparc.ISO", out)
        self.assertIn("pruned   mirror:iso/other.iso", out)
        self.assertIn("2 pruned", out)
        self.assertTrue(os.path.isfile(regular))
        self.assertTrue(os.path.isfile(other))
        rc, out = self.run_cmd("list", "--storage", "mirror", "--json")
        rows = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual({r["state"] for r in rows}, {"ok", "file"})
        sol = next(r for r in rows if r["name"].startswith("Solaris__2.6"))
        self.assertEqual(sol["folders"], ["Solaris", "2.6"])
        self.assertEqual(sol["size"], 8192)


class TestFindByChecksum(unittest.TestCase):
    """install.find_medium finds a target's medium under another name (a mirror link) by size+sha256."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = b"wsh-lab mirror test medium\n" * 100
        self.name = "test-medium.iso"
        targets.MEDIA[self.name] = {"title": "test", "content": "iso", "size": len(self.data),
                                    "sha256": hashlib.sha256(self.data).hexdigest(), "lab": self.name}
        self.addCleanup(targets.MEDIA.pop, self.name)
        d = os.path.join(self.tmp.name, "template", "iso")
        nas = write(os.path.join(self.tmp.name, "nas", "Test", self.name), data=self.data)
        write(os.path.join(d, "same-size.iso"), data=b"x" * len(self.data))
        write(os.path.join(d, "other.iso"), data=b"y")
        os.symlink(nas, os.path.join(d, "Test__test-medium.iso"))
        self.content = [{"volid": f"mirror:iso/{n}", "size": os.path.getsize(os.path.join(d, n))}
                        for n in sorted(os.listdir(d))]
        self.reads = []

        def fake_run(*cmd, check=True):
            if cmd[:2] == ("pvesm", "path"):
                self.reads.append(cmd[2])
                return os.path.join(d, cmd[2].split("/", 1)[1])
            raise AssertionError(cmd)

        saved = install.run, install.pvesh_get, install.node
        install.run = fake_run
        install.pvesh_get = lambda path, **kw: self.content
        install.node = lambda: "pve"
        self.addCleanup(lambda: setattr(install, "run", saved[0]) or setattr(install, "pvesh_get", saved[1])
                        or setattr(install, "node", saved[2]))

    def test_found_under_a_mirror_name(self):
        volid, path = install.find_medium(self.name, storage="mirror")
        self.assertEqual(volid, "mirror:iso/Test__test-medium.iso")
        self.assertTrue(path.endswith("Test__test-medium.iso"))
        # only volumes of the medium's size are read
        self.assertNotIn("mirror:iso/other.iso", self.reads)
        rows = install.check_media([self.name], storage="mirror")
        self.assertEqual((rows[0]["state"], rows[0]["volid"]), ("ok", "mirror:iso/Test__test-medium.iso"))

    def test_missing_when_no_volume_has_its_checksum(self):
        os.remove(os.path.join(self.tmp.name, "nas", "Test", self.name))
        self.content = [c for c in self.content if "Test__" not in c["volid"]]
        self.assertEqual(install.find_medium(self.name, storage="mirror"), (None, None))


if __name__ == "__main__":
    unittest.main()
