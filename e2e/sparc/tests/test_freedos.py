"""FreeDOS 1.4 installed from its floppies under the lab's own QEMU (the published pve-qemu-kvm), driven
on the VGA text screen: the DOS install machinery without Microsoft media, for CI.

Boots the Floppy Edition's boot disk, lets the installer partition the disk (it reboots), format it and
copy the six package disks, which the scenario swaps in as the installer asks (QMP
blockdev-change-medium), then boots the installed system and writes and checks the marker
(scenarios/freedos-install.py, dos-firstboot.py, dos-boot-disk.py), and that the installed system idles
at its prompt (FDAPM from the installer's FDAUTO.BAT; QEMU below targets_dos.IDLE_BELOW % of a core).
The screens are read from the VGA text buffer (vgatext.py) the whole way; no OCR.

    docker run --rm -e WSH_LAB_GUEST_TESTS=1 --entrypoint python3 wsh-sparc-lab -m unittest -v tests/test_freedos.py

  WSH_LAB_GUEST_TESTS=1  required: without it the test is skipped (it installs a guest and may download)

  FREEDOS_ZIP     FD14-FloppyEdition.zip; without it the pinned one (targets_dos.FREEDOS_ZIP) is
                  downloaded and its sha256 checked, into FREEDOS_CACHE (default /tmp/wsh-lab-freedos)
  FREEDOS_ACCEL   tcg (default) or kvm
  FREEDOS_OUT     where the evidence goes (default: a temporary directory, removed when the test passes)
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import lab  # noqa: E402
import targets_dos  # noqa: E402

sys.modules.setdefault("lab", lab)



# A whole guest install that may download its medium (minutes, network): only when asked for, so a plain
# `unittest discover` stays offline and fast. The CI workflows set WSH_LAB_GUEST_TESTS=1.
GUEST_TESTS = os.environ.get("WSH_LAB_GUEST_TESTS") == "1"

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def freedos_disks():
    """The seven 1.44 MB images (boot disk first), each checked against targets_dos.MEDIA."""
    z = targets_dos.FREEDOS_ZIP
    cache = os.environ.get("FREEDOS_CACHE", "/tmp/wsh-lab-freedos")
    os.makedirs(cache, exist_ok=True)
    zpath = os.environ.get("FREEDOS_ZIP") or os.path.join(cache, os.path.basename(z["url"]))
    if not os.path.exists(zpath) or sha256(zpath) != z["sha256"]:
        with urllib.request.urlopen(z["url"], timeout=300) as r, open(zpath + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(zpath + ".part", zpath)
    if sha256(zpath) != z["sha256"]:
        raise RuntimeError(f"{z['url']}: sha256 isn't {z['sha256']}")
    out = []
    with zipfile.ZipFile(zpath) as zf:
        for name in ["freedos14-boot.img"] + [f"freedos14-disk{n}.img" for n in range(1, 7)]:
            med = targets_dos.MEDIA[name]
            path = os.path.join(cache, name)
            if not os.path.exists(path) or sha256(path) != med["sha256"]:
                with zf.open(med["zip"]) as src, open(path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            if sha256(path) != med["sha256"]:
                raise RuntimeError(f"{med['zip']} in the zip: sha256 isn't {med['sha256']}")
            out.append(path)
    return out


def qemu():
    for name in ("qemu-system-x86_64", "kvm"):
        if shutil.which(name):
            return shutil.which(name)
    raise unittest.SkipTest("no qemu-system-x86_64")


@unittest.skipUnless(GUEST_TESTS, "a guest install that may download its floppies; set WSH_LAB_GUEST_TESTS=1")
class FreeDos(unittest.TestCase):
    def test_install_from_floppies(self):
        q = qemu()
        disks = freedos_disks()
        out = os.environ.get("FREEDOS_OUT") or tempfile.mkdtemp(prefix="wsh-lab-freedos-")
        disk = os.path.join(out, "c.raw")
        common = {"QEMU": q, "ACCEL": os.environ.get("FREEDOS_ACCEL", "tcg"), "DISK": disk, "DISK_MB": "256",
                  "FB_VIDEO": "0"}
        sc = os.path.join(HERE, "scenarios")
        t0 = time.time()
        res = lab.run_scenario(os.path.join(sc, "freedos-install.py"), os.path.join(out, "install"),
                               {**common, "FLOPPY": disks[0],
                                "SWAPS": " ".join(f"floppy0={d}" for d in disks[1:])}, no_ocr=True)
        self.assertEqual(res["code"], 0, res["status"])
        self.assertEqual(res["metrics"].get("disks"), 6)
        res = lab.run_scenario(os.path.join(sc, "dos-firstboot.py"), os.path.join(out, "firstboot"),
                               {**common, "FLAVOUR": "freedos", "MARKER": "target=freedos14\nby=test_freedos.py"},
                               no_ocr=True)
        self.assertEqual(res["code"], 0, res["status"])
        res = lab.run_scenario(os.path.join(sc, "dos-boot-disk.py"), os.path.join(out, "check"),
                               {**common, "VERSION": r"Free(DOS|Com)", "CHECK": r"(?m)^target=freedos14$",
                                "IDLE_BELOW": targets_dos.IDLE_BELOW}, no_ocr=True)
        self.assertEqual(res["code"], 0, res["status"])
        print(f"\nFreeDOS install, first boot and check: {time.time() - t0:.0f}s; evidence in {out}", flush=True)
        if not os.environ.get("FREEDOS_OUT"):
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
