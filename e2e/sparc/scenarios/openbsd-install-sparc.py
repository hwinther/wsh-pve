"""Install OpenBSD/sparc 5.9 on sun4m (SS-5 unless MACHINE says otherwise) from its small boot CD
(cd59.iso, bsd.rd only) with the sets from a second CD (a sets CD made on the node,
answer_media.openbsd_sets) on the serial console: le0 with a static address, root's password, the
auto layout on sd0, the sets base, comp, man, game (and the kernels), then ntpd off in the new system
(_openbsd.py) and halt. The disk then boots with openbsd-firstboot.py.

    lab.py run scenarios/openbsd-install-sparc.py --out /mnt/runs/ob59 \
        --var ISO=/mnt/os/iso/other-os/openbsd5.9/cd59.iso \
        --var SETS_DIR=/mnt/os/iso/other-os/openbsd5.9 --var ROOT_PASSWORD=wshlab

  ISO            the boot CD (cd59.iso), SCSI target 6
  SETS_ISO       the sets CD, SCSI target 5 (a lab QEMU of its own; attached to a PVE VM, the VM has
                 it already: `lab.py install openbsd59-ss5` puts it on scsi5)
  SETS_DIR       without SETS_ISO: the release's directory, from which <out>/sets.iso is written
                 (bsd, bsd.rd, base59.tgz, comp59.tgz, man59.tgz, game59.tgz, SHA256.sig, INSTALL.sparc)
  SETS_CD        the sets CD as the installer names it                          (cd0: target 5 comes first)
  HOSTNAME       the host name                                                  (openbsd)
  IP, NETMASK    le0's address (the first boot can change it)                   (10.0.2.15, 255.255.255.0)
  ROOT_PASSWORD  root's password, typed at the installer's prompts (no echo)     (required)
  SETS           the set selections, in order, before `done` (space separated)  (none: what the CD has)
  TIMEZONE       the installer's time zone                                       (UTC)
  VERIFY         1 = fail unless the installer checked the sets against SHA256.sig ("Signature
                 Verified"): it does only with room to copy them first (a 512 MB /tmp, /home or
                 /usr/src, a 2 GB other file system), which the auto layout gives an 8 GiB disk and
                 not a 3 GiB one ("Cannot determine prefetch area")              (none)
  INSTALL_TIMEOUT  seconds for the whole dialogue, set extraction included        (3600)

With a blank disk on target 3, OpenBIOS stops at `0 >` (or, with -boot d, boots the first CD it
finds) and _sparc32.prom_boot() boots the CD on target 6 by path.
"""
import os

import _openbsd
from _sparc32 import prom_boot

# the kernels and the sets without X11, and what lets the installer check them (SHA256.sig, signed with
# the 5.9 base key it has) and not ask about a missing INSTALL.sparc
SETS_FILES = ("bsd", "bsd.rd", "base59.tgz", "comp59.tgz", "man59.tgz", "game59.tgz", "SHA256.sig", "INSTALL.sparc")
SETS_TARGET = "5"  # after the disk (3), before the boot CD (6)

DEFAULTS = {**_openbsd.defaults("sparc"), "BOOT": "c", "HOSTNAME": "openbsd", "IP": "10.0.2.15",
            "NETMASK": "255.255.255.0", "ROOT_PASSWORD": "", "SETS": "", "SETS_ISO": "", "SETS_DIR": "",
            "SETS_CD": "cd0", "SETS_PATH": "/", "TIMEZONE": "UTC", "INSTALL_TIMEOUT": "3600", "VERIFY": ""}


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<OpenBSD sparc boot CD, cd59.iso>")
    iso = v["SETS_ISO"]
    if not iso:
        if not v["SETS_DIR"]:
            raise SystemExit("set SETS_ISO=<sets CD> or SETS_DIR=<the release's directory>")
        import answer_media
        files = {}
        for name in SETS_FILES:
            with open(os.path.join(v["SETS_DIR"], name), "rb") as f:
                files[name] = f.read()
        iso = os.path.join(out, "sets.iso")
        with open(iso, "wb") as f:
            f.write(answer_media.openbsd_sets(files))
    t = SETS_TARGET
    return _openbsd.qemu_args(v, out) + [
        "-drive", f"file={iso},if=none,id=drive-scsi{t},format=raw,readonly=on,media=cdrom",
        "-device", f"scsi-cd,channel=0,scsi-id={t},lun=0,drive=drive-scsi{t},id=scsi{t},physical_block_size=512"]


def run(m, v):
    if not v["ROOT_PASSWORD"]:
        raise SystemExit("set ROOT_PASSWORD (the installer needs one)")
    prom_boot(m, v, "cdrom")
    m.expect(r"OpenBSD [\d.]+ \(RAMDISK", int(v["TIMEOUT"]))
    m.snap("bsd.rd kernel")
    asked = _openbsd.installer(m, v, int(v["INSTALL_TIMEOUT"]))
    m.metrics["questions"] = len(asked)
    with m.cond:
        m.metrics["sets_verified"] = "Signature Verified" in m.text
    if v["VERIFY"] == "1" and not m.metrics["sets_verified"]:
        raise AssertionError("the installer didn't check the sets against SHA256.sig (no 'Signature Verified')")
    m.expect(_openbsd.PROMPT, 300)
    m.snap("installer shell")
    _openbsd.shell(m, f"mount | grep -q ' on /mnt ' || mount /dev/{_openbsd.disk(v)}a /mnt; mount")
    _openbsd.disable_ntpd(m, "/mnt")
    m.snap("ntpd off")
    _openbsd.halt_installer(m)
