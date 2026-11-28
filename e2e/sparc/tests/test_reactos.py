"""The ReactOS install target (targets_dos.py "reactos0416"): the answer file, the CD edit that puts it
on the release CD (answer_media.iso_replace), the converted medium and the VM profile. Standard
library only; no guest is started.

    python3 -m unittest -v tests/test_reactos.py     (in e2e/sparc)
"""
import hashlib
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import answer_media  # noqa: E402
import install  # noqa: E402
import targets  # noqa: E402


class AnswerFile(unittest.TestCase):
    def test_unattended_with_the_lab_defaults(self):
        text = answer_media.reactos_unattend()["/i386/unattend.inf"].decode("ascii")
        self.assertIn("\r\n", text)
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.assertRegex(text, r"(?m)^UnattendSetupEnabled = yes\r$")
        self.assertRegex(text, rf'(?m)^AdminPassword="{targets.DEFAULT_ROOT_PASSWORD}"\r$')
        self.assertRegex(text, r'(?m)^ComputerName="REACTOS"\r$')

    def test_commands_have_no_inf_separators(self):
        # ";" starts an INF comment and "," separates fields: a command with either is cut short
        text = answer_media.REACTOS_UNATTEND
        for section in ("GuiRunOnce",):
            body = re.search(rf"(?ms)^\[{section}\]\n(.*?)(?:^\[|\Z)", text).group(1)
            for line in filter(None, body.splitlines()):
                self.assertNotRegex(line, r"[;,%]", line)
        for key in ("Arguments", "UserExecute"):
            line = re.search(rf"(?m)^{key}=(.*)$", text).group(1)
            self.assertNotRegex(line, r"[;,%]", line)

    def test_refuses_names_reactos_cant_take(self):
        for bad in ({"hostname": "a" * 16}, {"hostname": "a b"}, {"password": "p;w"}, {"password": ""}):
            with self.assertRaises(ValueError):
                answer_media.reactos_unattend(**bad)


class IsoReplace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-reactos-")
        self.src = os.path.join(self.tmp, "src.iso")
        self.files = {"UNATTEND.INF": b"old answers\r\n" * 200, "OTHER.TXT": b"left alone\n"}
        with open(self.src, "wb") as f:
            f.write(answer_media.iso9660(self.files, "TEST"))

    def tearDown(self):
        for name in os.listdir(self.tmp):
            os.unlink(os.path.join(self.tmp, name))
        os.rmdir(self.tmp)

    def read(self, path):
        with open(path, "rb") as f:
            files = answer_media.iso_files(f)
            out = {}
            for name, recs in files.items():
                (_, lba, size), = set(recs)
                f.seek(lba * answer_media.SECTOR)
                out[name] = f.read(size)
        return out

    def test_replaces_in_place_and_sets_the_size(self):
        dst = os.path.join(self.tmp, "dst.iso")
        new = b"new answers\r\n"
        digest = answer_media.iso_replace(self.src, dst, {"/unattend.inf": new})
        with open(dst, "rb") as f:
            data = f.read()
        self.assertEqual(digest, hashlib.sha256(data).hexdigest())
        self.assertEqual(os.path.getsize(dst), os.path.getsize(self.src))
        got = self.read(dst)
        self.assertEqual(got["/unattend.inf"], new)
        self.assertEqual(got["/other.txt"], self.files["OTHER.TXT"])
        # only the file's own sectors and its directory record changed
        with open(self.src, "rb") as f:
            old = f.read()
        changed = {i // answer_media.SECTOR for i in range(len(old)) if old[i] != data[i]}
        with open(self.src, "rb") as f:
            (_, lba, size), = set(answer_media.iso_files(f)["/unattend.inf"])
        sectors = set(range(lba, lba + -(-size // answer_media.SECTOR)))
        self.assertTrue(changed <= sectors | {20}, changed)  # 20: the root directory of iso9660()
        self.assertTrue(changed & sectors and 20 in changed)

    def test_refuses_what_doesnt_fit_or_isnt_there(self):
        dst = os.path.join(self.tmp, "dst.iso")
        with self.assertRaises(ValueError):
            answer_media.iso_replace(self.src, dst, {"/unattend.inf": b"x" * 4097})
        with self.assertRaises(ValueError):
            answer_media.iso_replace(self.src, dst, {"/missing.inf": b"x"})
        self.assertFalse(os.path.exists(dst))
        self.assertFalse(os.path.exists(dst + ".part"))


class Target(unittest.TestCase):
    def test_in_the_catalogue(self):
        t = targets.TARGETS["reactos0416"]
        self.assertEqual(t["status"], "automated")
        p = t["profile"]
        self.assertEqual((p["machine"], p["vga"], p["ostype"]), ("pc", "std", "wxp"))
        self.assertEqual(p["tdf"], 0)  # -rtc driftfix=slew hangs the setup under TCG
        self.assertTrue(p["serial0"].startswith("socket"))
        self.assertEqual(t["disk"]["bus"], "ide0")
        self.assertEqual([m["drive"] for m in t["media"]], ["ide2"])

    def test_medium_is_made_from_the_release_cd(self):
        med = targets.MEDIA[targets.TARGETS["reactos0416"]["media"][0]["name"]]
        src = targets.MEDIA[med["from"]["name"]]
        self.assertEqual(src["sha256"], "6f15ca6e1edf5527b8489958d16c54f0da0e7948c305d7c89e74687c6cbf6855")
        self.assertEqual(med["size"], src["size"])  # edited in place: the same size
        self.assertIn(med["from"]["convert"], targets.ISO_EDITS)
        self.assertTrue(callable(getattr(answer_media, targets.ISO_EDITS[med["from"]["convert"]])))

    def test_convert_checks_source_and_result(self):
        name = targets.TARGETS["reactos0416"]["media"][0]["name"]
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.iso")
            with open(src, "wb") as f:
                f.write(b"\0" * 4096)
            with self.assertRaises(install.InstallFailed):
                install.convert_medium(name, src, os.path.join(d, "out.iso"))
            self.assertEqual(os.listdir(d), ["src.iso"])


@unittest.skipUnless(os.environ.get("WSH_LAB_GUEST_TESTS") == "1" and os.environ.get("REACTOS_ISO"),
                     "a guest install (~10 min); set WSH_LAB_GUEST_TESTS=1 and REACTOS_ISO")
class Guest(unittest.TestCase):
    """The three scenarios under the lab's own QEMU (the published pve-qemu-kvm in the lab image), as
    `lab.py install reactos0416 --check` runs them against a PVE VM:

        docker run --rm -e WSH_LAB_GUEST_TESTS=1 -e REACTOS_ISO=/iso/ReactOS-0.4.16-i386.iso -v <dir>:/iso:ro \\
          --entrypoint python3 wsh-sparc-lab -m unittest -v tests/test_reactos.py

    REACTOS_ISO   the release CD (converted into REACTOS_OUT first) or reactos0416-wshlab.iso; never
                  downloaded
    REACTOS_OUT   where the evidence goes (default: a temporary directory, removed when the test passes)
    """

    def test_install_firstboot_check(self):
        import lab

        sys.modules.setdefault("lab", lab)
        out = os.environ.get("REACTOS_OUT") or tempfile.mkdtemp(prefix="wsh-lab-reactos-")
        iso = os.environ["REACTOS_ISO"]
        name = targets.TARGETS["reactos0416"]["media"][0]["name"]
        if os.path.getsize(iso) == targets.MEDIA[name]["size"] and install.sha256(iso) != targets.MEDIA[name]["sha256"]:
            conv = os.path.join(out, name)
            if not os.path.exists(conv):
                install.convert_medium(name, iso, conv)
            iso = conv
        disk = os.path.join(out, "c.raw")
        common = {"DISK": disk, "FB_VIDEO": "0"}
        sc = os.path.join(HERE, "scenarios")
        res = lab.run_scenario(os.path.join(sc, "reactos-install.py"), os.path.join(out, "install"),
                               {**common, "ISO": iso})
        self.assertEqual(res["code"], 0, res["status"])
        res = lab.run_scenario(os.path.join(sc, "reactos-firstboot.py"), os.path.join(out, "firstboot"),
                               {**common, "MARKER": "target=reactos0416\nby=test_reactos.py"})
        self.assertEqual(res["code"], 0, res["status"])
        res = lab.run_scenario(os.path.join(sc, "reactos-boot-disk.py"), os.path.join(out, "check"),
                               {**common, "CHECK": r"(?m)^target=reactos0416$", "IDLE_BELOW": "25"})
        self.assertEqual(res["code"], 0, res["status"])
        if not os.environ.get("REACTOS_OUT"):
            import shutil

            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
