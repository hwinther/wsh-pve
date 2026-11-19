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
        """(exit code, stdout and stderr) of `lab.py mirror <argv>`; a sys.exit message is the output too."""
        p = argparse.ArgumentParser()
        mirror.add_commands(p.add_subparsers(dest="cmd", required=True))
        a = p.parse_args(["mirror", *argv])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
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
        cfg = os.environ["WSH_LAB_STORAGE_CFG"]
        with open(cfg, "a") as f:
            f.write("\nlvmthin: thin\n\tvgname pve\n\tthinpool data\n\tcontent images\n")
        for storage, why in (("nas", "isn't mounted"), ("nosuch", "no storage"), ("thin", "type lvmthin")):
            with self.subTest(storage=storage):
                with self.assertRaisesRegex(mirror.MirrorError, why):
                    mirror.storage_dirs(storage)
        with open(cfg, "a") as f:
            f.write("\ndir: backups\n\tpath /x\n\tcontent backup\n")
        with self.assertRaisesRegex(mirror.MirrorError, "neither iso nor floppy"):
            mirror.storage_dirs("backups")

    def test_network_and_btrfs_storages(self):
        t = self.tmp.name
        with open(os.environ["WSH_LAB_STORAGE_CFG"], "a") as f:
            f.write(f"\nbtrfs: bt\n\tpath {t}/bt\n\tcontent iso\n"
                    f"\ncephfs: cfs\n\tcontent iso,floppy\n"
                    f"\ncifs: smb\n\tpath {t}/smb\n\tserver 192.0.2.2\n\tshare media\n\tcontent iso\n"
                    f"\ncifs: smbok\n\tpath {t}/smbok\n\tserver 192.0.2.2\n\tshare media\n\tcontent iso\n"
                    f"\toptions mfsymlinks,vers=3.0\n")
        self.assertEqual(mirror.storage_dirs("bt"), {"iso": os.path.join(t, "bt", "template", "iso")})
        saved = mirror.is_mounted
        mirror.is_mounted = lambda p: True
        self.addCleanup(setattr, mirror, "is_mounted", saved)
        self.assertEqual(mirror.storage_info("nas")["root"], "/mnt/pve/nas")
        # cephfs without a path: PVE's mount point
        self.assertEqual(mirror.storage_info("cfs")["dirs"]["floppy"], "/mnt/pve/cfs/template/floppy")
        warnings = []
        mirror.storage_info("smb", warn=warnings.append)
        self.assertEqual(len(warnings), 1)
        self.assertIn("mfsymlinks", warnings[0])
        mirror.storage_info("smbok", warn=warnings.append)
        self.assertEqual(len(warnings), 1)


class TestLinkText(Env):
    """Relative link targets when the file is inside the link directory's mount, absolute otherwise."""

    def test_styles(self):
        inside_root = write(os.path.join(self.store, "archive", "Sun", "a.iso"), 10)
        outside = write(os.path.join(self.src, "b.iso"), 10)
        self.assertEqual(mirror.link_text(inside_root, self.iso_dir, "absolute"), inside_root)
        self.assertEqual(mirror.link_text(inside_root, self.iso_dir, "relative"), "../../archive/Sun/a.iso")
        self.assertEqual(mirror.link_text(outside, self.iso_dir, "relative"),
                         os.path.relpath(os.path.realpath(outside), os.path.realpath(self.store) + "/template/iso"))
        # auto: the storage's root is a mount (an NFS export): relative inside it, absolute outside
        saved = mirror.is_mounted
        store = os.path.realpath(self.store)
        mirror.is_mounted = lambda p: os.path.realpath(p) in (store, "/")
        self.addCleanup(setattr, mirror, "is_mounted", saved)
        self.assertEqual(mirror.link_text(inside_root, self.iso_dir, "auto"), "../../archive/Sun/a.iso")
        self.assertEqual(mirror.link_text(outside, self.iso_dir, "auto"), outside)

    def test_link_and_sync_relative_on_request(self):
        iso = write(os.path.join(self.store, "archive", "x.iso"), 10)
        rc, out = self.run_cmd("link", iso, "--storage", "mirror", "--links", "relative")
        self.assertEqual(rc, 0, out)
        self.assertEqual(os.readlink(os.path.join(self.iso_dir, "x.iso")), "../../archive/x.iso")
        # the same file through an absolute link counts as already there
        rc, out = self.run_cmd("link", iso, "--storage", "mirror")
        self.assertEqual((rc, out.split()[0]), (0, "exists"), out)


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


OLD = 1_000_000_000  # an mtime long ago: older than any min_age


def aged(path, mtime=OLD):
    os.utime(path, (mtime, mtime))
    return path


class Described(Env):
    """A mirror storage with a description file: the media of case 2 (inside the storage's root, which
    stands for an NFS export holding both) and of case 3 (an externally managed tree outside it)."""

    CONFIG = """\
# the test mirror
version: 1
storage: mirror
watch:
  - archive          # inside the storage's root
  - path: {src}/torrents
    prefix: Torrents
auto_import: false
incomplete:
  patterns: ['*.part', '*.!qB', '*.incomplete']
  min_age: 5min
rules:
  - source: {src}/vmware
    prefix: VMware
    exclude: ['*/old/*']
entries:
  # hand-made
  - name: Hand__made.iso
    source: {src}/misc/whatever name.iso
    origin: manual
"""

    def setUp(self):
        super().setUp()
        self.archive = os.path.join(self.store, "archive")
        self.cfg_path = os.path.join(self.store, "wsh-mirror.yaml")
        os.makedirs(self.store, exist_ok=True)
        self.write_cfg(self.CONFIG.format(src=self.src))
        self.files = {
            "sol": aged(write(os.path.join(self.archive, "Solaris", "2.6", "sol26.iso"), data=b"sol26" * 100)),
            "dos": aged(write(os.path.join(self.archive, "DOS", "disk1.img"), FLOPPY)),
            "deb": aged(write(os.path.join(self.src, "torrents", "debian-40r9-sparc", "netinst.iso"),
                              data=b"debian" * 100)),
            "esx": aged(write(os.path.join(self.src, "vmware", "esx", "esx.iso"), data=b"esx" * 100)),
            "esxold": aged(write(os.path.join(self.src, "vmware", "old", "esx2.iso"), data=b"old" * 100)),
            "hand": aged(write(os.path.join(self.src, "misc", "whatever name.iso"), data=b"hand" * 100)),
        }
        write(os.path.join(self.archive, "readme.txt"), 1)
        # the storage's root is a mount of its own (an NFS export holding the archive and the links)
        saved = mirror.is_mounted
        store = os.path.realpath(self.store)
        mirror.is_mounted = lambda p: os.path.realpath(p) in (store, "/")
        self.addCleanup(setattr, mirror, "is_mounted", saved)

    def write_cfg(self, text):
        with open(self.cfg_path, "w") as f:
            f.write(text)

    def cfg_text(self):
        with open(self.cfg_path) as f:
            return f.read()

    def links(self):
        """{volume name: link text} of both directories."""
        out = {}
        for d in (self.iso_dir, self.fd_dir):
            if os.path.isdir(d):
                for n in os.listdir(d):
                    p = os.path.join(d, n)
                    out[n] = os.readlink(p) if os.path.islink(p) else "FILE"
        return out


class TestDescriptionFile(Described):
    def test_config_errors(self):
        for text, why in (("version: 2\n", "version 2"), ("wach: []\n", "unknown key"),
                          ("rules:\n  - prefix: x\n", "source"), ("entries:\n  - name: a.iso\n", "source is required"),
                          ("entries:\n  - {name: a.iso, source: x, origin: other}\n", "origin"),
                          ("links: sideways\n", "links"), ("incomplete: {min_age: soon}\n", "duration"),
                          ("entries:\n  - {name: a.iso, source: x}\n  - {name: a.iso, source: y}\n", "also entries"),
                          ("[1, 2]\n", "mapping"), ("a: [\n", "not valid YAML")):
            with self.subTest(text=text):
                self.write_cfg(text)
                rc, out = self.run_cmd("plan", "--storage", "mirror")
                self.assertEqual(rc, 1)
                self.assertIn(why, out)
        os.remove(self.cfg_path)
        rc, out = self.run_cmd("plan", "--storage", "mirror")
        self.assertIn("mirror init", out)
        self.assertEqual(mirror.parse_age("5min"), 300)
        self.assertEqual(mirror.parse_age(30), 30)
        self.assertEqual(mirror.parse_age("2h"), 7200)

    def test_init_writes_a_valid_commented_file(self):
        os.remove(self.cfg_path)
        rc, out = self.run_cmd("init", "--storage", "mirror", "--watch", self.archive, "--watch", self.src)
        self.assertEqual(rc, 0, out)
        text = self.cfg_text()
        self.assertIn("  - archive\n", text)  # relative to the storage's root
        self.assertIn(f"  - {self.src}\n", text)
        rc, out = self.run_cmd("init", "--storage", "mirror")
        self.assertEqual(rc, 1)
        self.assertIn("exists", out)
        rc, out = self.run_cmd("plan", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        # import fills the empty `entries: []` and keeps the comments
        rc, out = self.run_cmd("import", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        text2 = self.cfg_text()
        self.assertIn("# Single files with names of their own", text2)
        self.assertIn("#  - name: Solaris__2.6__solaris_2.6_598_sparc.iso", text2)
        self.assertIn("  - name: Solaris__2.6__sol26.iso\n    source: archive/Solaris/2.6/sol26.iso\n"
                      "    origin: import\n", text2)

    def test_plan_then_apply_case_2_relative_links_survive_another_mount_path(self):
        rc, out = self.run_cmd("plan", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("link     mirror:iso/VMware__esx__esx.iso", out)
        self.assertIn("link     mirror:iso/Hand__made.iso", out)
        self.assertIn(f"new      {self.files['sol']} as iso/Solaris__2.6__sol26.iso (`import` adds it)", out)
        self.assertIn("new      " + self.files["deb"] + " as iso/Torrents__debian-40r9-sparc__netinst.iso", out)
        self.assertNotIn("esx2.iso", out)  # excluded by the rule, and not "new" either
        self.assertNotIn("readme.txt", out)
        self.assertFalse(os.path.exists(self.iso_dir), "plan changed nothing")
        rc, out = self.run_cmd("import", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("3 entries added", out)
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        links = self.links()
        self.assertEqual(sorted(links), ["DOS__disk1.img", "Hand__made.iso", "Solaris__2.6__sol26.iso",
                                         "Torrents__debian-40r9-sparc__netinst.iso", "VMware__esx__esx.iso"])
        # the archive inside the storage's root: relative; the trees outside it: absolute
        self.assertEqual(links["Solaris__2.6__sol26.iso"], "../../archive/Solaris/2.6/sol26.iso")
        self.assertEqual(links["DOS__disk1.img"], "../../archive/DOS/disk1.img")
        self.assertEqual(links["VMware__esx__esx.iso"], self.files["esx"])
        # again: nothing to do
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("0 linked, 0 relinked, 0 unlinked, 5 in place", out)
        # the same export through another mount path: the relative links still lead to the files
        moved_store = self.store + "-other-mount"
        os.rename(self.store, moved_store)
        with open(os.path.join(moved_store, "template", "iso", "Solaris__2.6__sol26.iso"), "rb") as f:
            self.assertEqual(f.read(), b"sol26" * 100)

    def test_case_3_a_changing_tree(self):
        self.run_cmd("import", "--storage", "mirror")
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        sol_link = os.path.join(self.iso_dir, "Solaris__2.6__sol26.iso")
        # a regular file and a link the tool didn't make are never touched
        upload = write(os.path.join(self.iso_dir, "upload.iso"), data=b"uploaded")
        foreign = write(os.path.join(self.tmp.name, "elsewhere", "f.iso"), 5)
        os.symlink(foreign, os.path.join(self.iso_dir, "foreign.iso"))
        # added: a finished file, one still downloading (by name), one written a moment ago
        new_esx = aged(write(os.path.join(self.src, "vmware", "esx7", "esx7.iso"), data=b"esx7" * 100))
        write(os.path.join(self.src, "torrents", "sol10", "sol-10-u11.iso.part"), 10)
        write(os.path.join(self.src, "torrents", "sol10", "sol-10-u11.iso.!qB"), 10)
        # a client that keeps the final name in a folder marked incomplete: by the pattern, however old
        in_folder = aged(write(os.path.join(self.src, "torrents", "tribblix.incomplete", "tribblix.iso"), 10))
        fresh = write(os.path.join(self.src, "torrents", "netbsd", "NetBSD-9.4-sparc.iso"), data=b"nb" * 10)
        # removed: an imported file and the hand-made one; moved: the Solaris image (same size+sha256)
        os.remove(self.files["deb"])
        os.remove(self.files["hand"])
        new_sol = os.path.join(self.archive, "Sun", "Solaris 2.6", "sol26.iso")
        os.makedirs(os.path.dirname(new_sol))
        os.rename(self.files["sol"], new_sol)
        rc, out = self.run_cmd("plan", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("link     mirror:iso/VMware__esx7__esx7.iso", out)
        self.assertIn(f"waiting  {fresh}: changed", out)
        self.assertIn(f"waiting  {in_folder}: its name matches *.incomplete", out)
        self.assertNotIn(".part", out)  # not a medium by its extension, never linked
        self.assertIn(f"moved    entry Solaris__2.6__sol26.iso: {self.files['sol']} -> {new_sol}", out)
        self.assertIn("gone     entry Torrents__debian-40r9-sparc__netinst.iso", out)
        self.assertIn("gone     entry Hand__made.iso", out)
        self.assertIn("unmanaged mirror:iso/foreign.iso", out)
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        links = self.links()
        # the moved file keeps its volume name until tidy writes the new path into the file
        self.assertEqual(links["Solaris__2.6__sol26.iso"], "../../archive/Sun/Solaris 2.6/sol26.iso")
        self.assertTrue(os.path.isfile(sol_link))
        self.assertNotIn("Sun__Solaris_2.6__sol26.iso", links)
        self.assertIn("VMware__esx7__esx7.iso", links)
        self.assertNotIn("Torrents__debian-40r9-sparc__netinst.iso", links)  # an import entry's link: removed
        self.assertIn("Hand__made.iso", links)  # a manual entry's link: flagged, kept
        self.assertIn("flagged  mirror:iso/Hand__made.iso", out)
        self.assertNotIn("NetBSD", "".join(links))
        self.assertEqual((links["upload.iso"], links["foreign.iso"]), ("FILE", foreign))
        # tidy: follow the move, drop the gone import entry, keep the manual one; comments stay
        rc, out = self.run_cmd("tidy", "--storage", "mirror", "--dry-run")
        self.assertIn("1 followed, 1 dropped, 1 kept (dry run", out)
        before = self.cfg_text()
        rc, out = self.run_cmd("tidy", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        text = self.cfg_text()
        self.assertNotEqual(before, text)
        self.assertIn('source: "archive/Sun/Solaris 2.6/sol26.iso"', text)
        self.assertNotIn("debian-40r9", text)
        self.assertIn("Hand__made.iso", text)
        self.assertIn("# hand-made", text)
        self.assertIn("# inside the storage's root", text)
        rc, out = self.run_cmd("tidy", "--storage", "mirror", "--include-manual")
        self.assertIn("drop     Hand__made.iso", out)
        self.assertNotIn("Hand__made.iso", self.cfg_text())
        # the download finished and settled: linked by import + apply
        aged(fresh)
        rc, out = self.run_cmd("import", "--storage", "mirror")
        self.assertIn("import   Torrents__netbsd__NetBSD-9.4-sparc.iso", out)
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        links = self.links()
        self.assertIn("Torrents__netbsd__NetBSD-9.4-sparc.iso", links)
        self.assertNotIn("Hand__made.iso", links)  # no longer described: removed
        self.assertEqual(links["Solaris__2.6__sol26.iso"], "../../archive/Sun/Solaris 2.6/sol26.iso")
        rc, out = self.run_cmd("plan", "--storage", "mirror")
        self.assertIn("0 to link, 0 to relink, 0 to unlink", out)
        self.assertNotIn("moved", out)

    def test_a_linked_file_written_to_stays_linked(self):
        # a floppy image a VM writes to changes all the time: min_age only holds back new files
        self.run_cmd("import", "--storage", "mirror")
        self.run_cmd("apply", "--storage", "mirror")
        os.utime(self.files["dos"])
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("DOS__disk1.img", self.links())
        self.assertIn("5 in place, 0 not covered, 0 waiting", out)

    def test_rename_by_editing_the_file(self):
        self.run_cmd("import", "--storage", "mirror")
        self.run_cmd("apply", "--storage", "mirror")
        self.write_cfg(self.cfg_text().replace("name: Solaris__2.6__sol26.iso", "name: Sun__Solaris__2.6.iso"))
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        links = self.links()
        self.assertIn("Sun__Solaris__2.6.iso", links)
        self.assertNotIn("Solaris__2.6__sol26.iso", links)
        # an entry for a file under a rule names it instead of the rule
        self.write_cfg(self.cfg_text() + f"  - name: ESX__6.iso\n    source: {self.files['esx']}\n")
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        links = self.links()
        self.assertIn("ESX__6.iso", links)
        self.assertNotIn("VMware__esx__esx.iso", links)

    def test_auto_import_and_clashes(self):
        self.write_cfg(self.cfg_text().replace("auto_import: false", "auto_import: true"))
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("Torrents__debian-40r9-sparc__netinst.iso", self.links())
        # two files that end up with the same name: neither is linked, both reported
        aged(write(os.path.join(self.archive, "a b.iso"), 3))
        aged(write(os.path.join(self.archive, "a_b.iso"), 4))
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 1, out)
        self.assertIn("clash    mirror:iso/a_b.iso", out)
        self.assertNotIn("a_b.iso", self.links())
        # a regular file where a link should go
        self.write_cfg(self.cfg_text().replace("name: Hand__made.iso", "name: upload.iso"))
        write(os.path.join(self.iso_dir, "upload.iso"), data=b"x")
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 1, out)
        self.assertIn("conflict mirror:iso/upload.iso: a regular file", out)
        with open(os.path.join(self.iso_dir, "upload.iso"), "rb") as f:
            self.assertEqual(f.read(), b"x")

    def test_unreachable_share_keeps_the_links(self):
        self.run_cmd("import", "--storage", "mirror")
        self.run_cmd("apply", "--storage", "mirror")
        # the torrent share isn't mounted: an empty mount point
        tor = os.path.join(self.src, "torrents")
        os.rename(tor, tor + ".away")
        os.makedirs(tor)
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertIn("Torrents__debian-40r9-sparc__netinst.iso", self.links())
        self.assertIn("unreachable", out)
        rc, out = self.run_cmd("tidy", "--storage", "mirror")
        self.assertIn("kept     Torrents__debian-40r9-sparc__netinst.iso", out)
        self.assertIn("debian-40r9", self.cfg_text())

    def test_existing_links_adopted_and_sync_refused(self):
        # links made earlier by `sync` (absolute) to the same files are taken over, as relative links
        os.makedirs(self.iso_dir)
        os.symlink(self.files["sol"], os.path.join(self.iso_dir, "Solaris__2.6__sol26.iso"))
        self.run_cmd("import", "--storage", "mirror")
        rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, 0, out)
        self.assertIn("relink   mirror:iso/Solaris__2.6__sol26.iso", out)
        self.assertEqual(self.links()["Solaris__2.6__sol26.iso"], "../../archive/Solaris/2.6/sol26.iso")
        rc, out = self.run_cmd("sync", self.archive, "--storage", "mirror")
        self.assertEqual(rc, 1)
        self.assertIn("has a description file", out)

    def test_lock_and_config_elsewhere(self):
        # a second run while one holds the lock gives up with 75
        with mirror.locked(self.store):
            rc, out = self.run_cmd("apply", "--storage", "mirror")
        self.assertEqual(rc, mirror.BUSY)
        # --config: the file outside the storage (a per-node file in /etc/pve), storage taken from it
        other = os.path.join(self.tmp.name, "etc-pve", "nodes", "pve", "wsh-mirror-mirror.yaml")
        os.makedirs(os.path.dirname(other))
        os.rename(self.cfg_path, other)
        rc, out = self.run_cmd("apply", "--config", other)
        self.assertEqual(rc, 0, out)
        self.assertIn("VMware__esx__esx.iso", self.links())
        self.assertTrue(os.path.exists(os.path.join(self.store, ".wsh-mirror-state.json")))

    def test_timer_units(self):
        units = os.path.join(self.tmp.name, "systemd")
        os.makedirs(units)
        os.environ["WSH_LAB_SYSTEMD_DIR"] = units
        self.addCleanup(os.environ.pop, "WSH_LAB_SYSTEMD_DIR", None)
        calls = []
        saved = mirror.systemctl
        mirror.systemctl = lambda *args: calls.append(args)
        self.addCleanup(setattr, mirror, "systemctl", saved)
        rc, out = self.run_cmd("timer", "--storage", "mirror", "--interval", "15min")
        self.assertEqual(rc, 0, out)
        with open(os.path.join(units, "wsh-lab-mirror-mirror.timer")) as f:
            self.assertIn("OnUnitInactiveSec=15min", f.read())
        with open(os.path.join(units, "wsh-lab-mirror-mirror.service")) as f:
            service = f.read()
        self.assertRegex(service, r"ExecStart=.* mirror apply --storage mirror --quiet\n")
        self.assertIn("SuccessExitStatus=75", service)
        self.assertEqual(calls, [("daemon-reload",), ("enable", "--now", "wsh-lab-mirror-mirror.timer")])
        rc, out = self.run_cmd("timer", "--storage", "mirror", "--interval", "soon")
        self.assertEqual(rc, 1)
        rc, out = self.run_cmd("timer", "--storage", "mirror", "--remove")
        self.assertEqual(rc, 0, out)
        self.assertEqual(os.listdir(units), [])
        self.assertIn(("disable", "--now", "wsh-lab-mirror-mirror.timer"), calls)


class TestEditing(unittest.TestCase):
    """add_entries/edit_entries keep everything else in the file as it was."""

    TEXT = """\
version: 1   # v
entries:
  # first
  - name: A.iso
    source: a.iso      # where
    origin: import
  -
    name: B.iso
    source: "b c.iso"
  - {name: C.iso, source: c.iso}
# after
rules: []
"""

    def test_add_and_edit(self):
        import yaml
        text = mirror.add_entries(self.TEXT, [("D__x.iso", "d x.iso", "import")])
        self.assertTrue(text.startswith(self.TEXT.split("# after")[0]))
        self.assertIn('  - name: D__x.iso\n    source: "d x.iso"\n    origin: import\n# after\n', text)
        data = yaml.safe_load(text)
        self.assertEqual([e["name"] for e in data["entries"]], ["A.iso", "B.iso", "C.iso", "D__x.iso"])
        text = mirror.edit_entries(text, remove={1}, resource={0: "new/a.iso", 2: "true"})
        data = yaml.safe_load(text)
        self.assertEqual([(e["name"], e["source"]) for e in data["entries"]],
                         [("A.iso", "new/a.iso"), ("C.iso", "true"), ("D__x.iso", "d x.iso")])
        self.assertIn("source: new/a.iso      # where\n", text)
        self.assertIn("# first\n", text)
        self.assertIn("version: 1   # v\n", text)
        self.assertIn("# after\n", text)

    def test_add_to_missing_or_empty_entries(self):
        import yaml
        for text in ("version: 1\n", "version: 1\nentries:\n", "version: 1\nentries: []   # none yet\nrules: []\n",
                     "entries: ~\nrules: []"):
            with self.subTest(text=text):
                out = mirror.add_entries(text, [("A.iso", "a.iso", "import")])
                self.assertEqual(yaml.safe_load(out)["entries"],
                                 [{"name": "A.iso", "source": "a.iso", "origin": "import"}], out)
                if "none yet" in text:
                    self.assertIn("entries:  # none yet\n", out)


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
