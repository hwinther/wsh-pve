"""A NetBSD install target installed from its official CD under the lab's own QEMU (the published
pve-qemu-kvm, TCG): the steps of `lab.py install <target>` without a PVE node, for CI. The target is
`netbsd111-sparc64` unless NETBSD_TARGET names another NetBSD target (netbsd93-sparc64 on sun4u,
netbsd111-sparc, netbsd93-sparc on an SS-5, the -ss20 ones on an SS-20).

sysinst on the serial console (scenarios/netbsd-install-sparc64.py or netbsd-install-sparc.py), then
the first boot that sets root's password, the marker, the host name and a static address
(netbsd-firstboot.py), then a boot that logs in with that password and checks the marker
(netbsd-boot-disk.py).

    docker run --rm -e WSH_LAB_GUEST_TESTS=1 --entrypoint python3 wsh-sparc-lab -m unittest -v tests/test_netbsd.py
    docker run --rm -e WSH_LAB_GUEST_TESTS=1 -e NETBSD_TARGET=netbsd93-sparc64 --entrypoint python3 wsh-sparc-lab \
        -m unittest -v tests/test_netbsd.py

  WSH_LAB_GUEST_TESTS=1  required: without it the test is skipped (it installs a guest and may download)

  NETBSD_TARGET  the install target (default netbsd111-sparc64)
  NETBSD_ISO     the target's CD; without it the pinned one (targets.MEDIA, "url") is downloaded into
                 NETBSD_CACHE (default /tmp/wsh-lab-netbsd). Either way its size, sha256 and sha512
                 (the release's images/SHA512) are checked
  NETBSD_OUT     where the evidence goes (default: a temporary directory, removed when the test passes)
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fetch_media  # noqa: E402
import lab  # noqa: E402
import targets  # noqa: E402

sys.modules.setdefault("lab", lab)

TARGET = os.environ.get("NETBSD_TARGET") or "netbsd111-sparc64"


# A whole guest install that may download its medium (minutes, network): only when asked for, so a plain
# `unittest discover` stays offline and fast. The CI workflows set WSH_LAB_GUEST_TESTS=1.
GUEST_TESTS = os.environ.get("WSH_LAB_GUEST_TESTS") == "1"


def netbsd_iso(name):
    """The target's CD, checked against targets.MEDIA[name] (fetch_media.py downloads the pinned one)."""
    path = os.environ.get("NETBSD_ISO")
    if not path:
        return fetch_media.fetch(name, os.environ.get("NETBSD_CACHE", "/tmp/wsh-lab-netbsd"))
    med = targets.MEDIA[name]
    if not fetch_media.tested(path, med):
        raise RuntimeError(f"{path}: not the tested {name} (size {med['size']}, sha256 {med['sha256']},"
                           f" sha512 {med.get('sha512', '-')})")
    return path


def machine(t):
    """The scenarios' variables for the target's machine, as its PVE profile has it: sparc64 (sun4u,
    the scenarios' defaults) or sparc32 (MACHINE, every scenario on _sparc32's defaults)."""
    p = t["profile"]
    if p["arch"] == "sparc64":
        return "qemu-system-sparc64", {"DISK_GB": str(t["disk"]["size"]), "MEM": str(p["memory"])}
    # netbsd-firstboot.py and netbsd-boot-disk.py default to sparc64: give them the whole sparc32 machine
    sys.path.insert(0, os.path.join(HERE, "scenarios"))
    import _netbsd
    v = {**_netbsd.defaults("sparc"), "MACHINE": p["machine"], "MEM": str(p["memory"])}
    for key in ("ISO", "DISK", "SETS"):  # set per phase below
        v.pop(key, None)
    return "qemu-system-sparc", v


@unittest.skipUnless(GUEST_TESTS, "a guest install that may download its CD; set WSH_LAB_GUEST_TESTS=1")
class NetBSD(unittest.TestCase):
    def test_install_firstboot_check(self):
        t = targets.TARGETS.get(TARGET)
        self.assertTrue(t and t["install"]["scenario"].startswith("netbsd-install-"), f"not a NetBSD target: {TARGET}")
        binary, mvars = machine(t)
        if not shutil.which(binary):
            raise unittest.SkipTest(f"no {binary}")
        iso = netbsd_iso(t["media"][0]["name"])
        out = os.environ.get("NETBSD_OUT") or tempfile.mkdtemp(prefix="wsh-lab-netbsd-")
        common = {**mvars, "DISK": os.path.join(out, "disk.raw")}
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
        print(f"\n{TARGET}: install {times['install']}s, first boot {times['firstboot']}s, check {times['check']}s;"
              f" evidence in {out}", flush=True)
        if not os.environ.get("NETBSD_OUT"):
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
