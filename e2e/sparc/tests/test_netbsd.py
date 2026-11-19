"""NetBSD 11.1/sparc64 installed from its official CD under the lab's own QEMU (the published
pve-qemu-kvm, TCG, sun4u): the steps of `lab.py install netbsd111-sparc64` without a PVE node, for CI.

sysinst on the serial console (scenarios/netbsd-install-sparc64.py), then the first boot that sets
root's password, the marker, the host name and a static address (netbsd-firstboot.py), then a boot
that logs in with that password and checks the marker (netbsd-boot-disk.py).

    docker run --rm -e WSH_LAB_GUEST_TESTS=1 --entrypoint python3 wsh-sparc-lab -m unittest -v tests/test_netbsd.py

  WSH_LAB_GUEST_TESTS=1  required: without it the test is skipped (it installs a guest and may download)

  NETBSD_ISO     NetBSD-11.1-sparc64.iso; without it the pinned one (targets.MEDIA, "url") is
                 downloaded and its sha256 checked, into NETBSD_CACHE (default /tmp/wsh-lab-netbsd)
  NETBSD_OUT     where the evidence goes (default: a temporary directory, removed when the test passes)
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import lab  # noqa: E402
import targets  # noqa: E402

sys.modules.setdefault("lab", lab)

TARGET = "netbsd111-sparc64"
NAME = "NetBSD-11.1-sparc64.iso"



# A whole guest install that may download its medium (minutes, network): only when asked for, so a plain
# `unittest discover` stays offline and fast. The CI workflows set WSH_LAB_GUEST_TESTS=1.
GUEST_TESTS = os.environ.get("WSH_LAB_GUEST_TESTS") == "1"

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def netbsd_iso():
    """The CD, checked against targets.MEDIA (size and sha256 of the tested medium)."""
    med = targets.MEDIA[NAME]
    path = os.environ.get("NETBSD_ISO")
    if not path:
        cache = os.environ.get("NETBSD_CACHE", "/tmp/wsh-lab-netbsd")
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, NAME)
        if not os.path.exists(path) or os.path.getsize(path) != med["size"] or sha256(path) != med["sha256"]:
            with urllib.request.urlopen(med["url"], timeout=600) as r, open(path + ".part", "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            os.replace(path + ".part", path)
    if os.path.getsize(path) != med["size"] or sha256(path) != med["sha256"]:
        raise RuntimeError(f"{path}: not the tested {NAME} (size {med['size']}, sha256 {med['sha256']})")
    return path


def qemu():
    if not shutil.which("qemu-system-sparc64"):
        raise unittest.SkipTest("no qemu-system-sparc64")


@unittest.skipUnless(GUEST_TESTS, "a guest install that may download its CD; set WSH_LAB_GUEST_TESTS=1")
class NetBSD(unittest.TestCase):
    def test_install_firstboot_check(self):
        qemu()
        iso = netbsd_iso()
        out = os.environ.get("NETBSD_OUT") or tempfile.mkdtemp(prefix="wsh-lab-netbsd-")
        t = targets.TARGETS[TARGET]
        common = {"DISK": os.path.join(out, "disk.raw"), "DISK_GB": str(t["disk"]["size"]),
                  "MEM": str(t["profile"]["memory"])}
        sc = os.path.join(HERE, "scenarios")
        times = {}

        def phase(name, scenario, v):
            t0 = time.time()
            res = lab.run_scenario(os.path.join(sc, scenario), os.path.join(out, name), {**common, **v}, no_ocr=True)
            times[name] = round(time.time() - t0)
            self.assertEqual(res["code"], 0, f"{name}: {res['status']}")

        phase("install", t["install"]["scenario"], {**t["install"]["vars"], "ISO": iso})
        marker = f"target={TARGET}\nby=test_netbsd.py"
        phase("firstboot", t["firstboot"]["scenario"],
              {"ROOT_PASSWORD": targets.DEFAULT_ROOT_PASSWORD, "MARKER": marker, "HOSTNAME": t["hostname"],
               "NET_MODE": "static", "NET_IP": "10.0.2.15", "NET_NETMASK": "255.255.255.0", "NET_GATEWAY": "10.0.2.2",
               "NIC_NAME": t["nic"]})
        phase("check", t["check"]["scenario"],
              {"ROOT_PASSWORD": targets.DEFAULT_ROOT_PASSWORD, "COMMANDS": t["check"]["commands"],
               "CHECK": rf"(?m)^target={TARGET}$[\s\S]*inet 10\.0\.2\.15/24 "})
        print(f"\nNetBSD/sparc64 install {times['install']}s, first boot {times['firstboot']}s, check {times['check']}s;"
              f" evidence in {out}", flush=True)
        if not os.environ.get("NETBSD_OUT"):
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
