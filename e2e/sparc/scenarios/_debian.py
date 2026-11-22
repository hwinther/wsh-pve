"""What the Debian install, first-boot and boot scenarios share: Debian GNU/Linux 4.0 "etch" (sparc) on
sun4m (_sparc32.py, the console on ttya; Linux calls it ttyS0; README.md, "Debian GNU/Linux 4.0"), and
with ARCH=sparc64 Debian GNU/Linux 7 "wheezy" (sparc) on sun4u (_sparc64.py: disk and CD-ROM on the
built-in IDE, sunhme, serial console; README.md, "Debian GNU/Linux 7 on sun4u"). Attached to a PVE VM
(`--pve`) the VM is what PVE built from the target's profile, and ARCH comes from its config.

  ARCH         sparc (sun4m, etch) | sparc64 (sun4u, wheezy)                           (sparc)
  ANSWERS_ISO  the answer CD (a lab QEMU of its own): an ISO 9660 image with preseed.cfg and
               wshlab on SCSI target 5 (sparc64: the secondary IDE slave, after the install CD);
               the netinst on target 6 (sparc64: CD 1 on the secondary master) is the install CD.
               Default: <out>/preseed.iso, written from answer_media.preseed() (sparc64:
               preseed_wheezy()) with IP, NETMASK, GATEWAY, DNS, DOMAIN and HOSTNAME. Attached to a
               PVE VM, the VM has it already (`lab.py install` puts it on scsi5, sparc64 on ide3)
"""
import os
import time

import _redhat
import _sparc32
import _sparc64

DEFAULTS = {**_sparc32.DEFAULTS, "VGA": "none", "BOOT": "c", "ANSWERS_ISO": "", "ARCH": "sparc"}
ANSWERS_TARGET = "5"  # the answer CD's SCSI target: after the disk (3), before the netinst (6)
PROMPT = r":~# ?$"  # root's bash prompt in its home, `<host>:~# `
# sparc64 (wheezy): the answer CD is the secondary IDE slave, Linux's second CD-ROM (sr1) after the
# install CD on the secondary master (sr0); what `lab.py install` calls ide3
ANSWERS_DEV64 = "/dev/sr1"
SPARC64_MEM = "512"

# The rest is _redhat's: a Linux root shell on ttyS0 behaves the same
shell = _redhat.shell
passwd = _redhat.passwd
power_off = _redhat.power_off
check_output = _redhat.check_output


def sparc64(v):
    return v.get("ARCH") == "sparc64"


def answers_iso(v, out):
    """ANSWERS_ISO, or the answer CD written from the network variables into `out`."""
    import answer_media
    iso = v["ANSWERS_ISO"]
    if not iso:
        iso = os.path.join(out, "preseed.iso")
        with open(iso, "wb") as f:
            f.write(answer_media.image("preseed-wheezy" if sparc64(v) else "preseed", v["IP"], v["NETMASK"],
                                       v["GATEWAY"] or None, v["DNS"].split(), v["DOMAIN"] or None,
                                       v["HOSTNAME"] or None))
    return iso


def qemu_args64(v, out, answers=False):
    """ARCH=sparc64: _sparc64's machine (disk on the primary IDE master, the CD on the secondary
    master, sunhme) with `answers` the answer CD on the secondary slave. The sun4m variables still at
    their defaults take the sun4u ones (QEMU, BIOS, MACHINE; MEM SPARC64_MEM, VGA none), and the sun4u
    ones the scenario lacks are added."""
    for k, val in _sparc64.DEFAULTS.items():
        if k not in v or (k in ("QEMU", "BIOS", "MACHINE") and v[k] == _sparc32.DEFAULTS[k]):
            v[k] = val
    if v["MEM"] == _sparc32.DEFAULTS["MEM"]:
        v["MEM"] = SPARC64_MEM
    if v.get("NO_CD"):
        v["ISO"] = ""
    if answers:
        v["BOOT"] = "d"  # the install: OpenBIOS's `cdrom` alias, as PVE's boot order does
    args = _sparc64.qemu_args(v, out)
    if answers:
        iso = answers_iso(v, out)
        args += ["-drive", f"file={iso},if=none,id=drive-answers,format=raw,readonly=on,media=cdrom",
                 "-device", "ide-cd,bus=ide.1,unit=1,drive=drive-answers,id=drive-answers-dev"]
    return args


def qemu_args(v, out, answers=False):
    """The lab's own QEMU: _sparc32's machine (disk on target 3, CD on 6), with `answers` the answer CD
    on target 5 (ANSWERS_ISO, or one written from the network variables); ARCH=sparc64: qemu_args64."""
    if sparc64(v):
        return qemu_args64(v, out, answers)
    args = _sparc32.qemu_args(v, out)
    if answers:
        iso = answers_iso(v, out)
        t = ANSWERS_TARGET
        args += ["-drive", f"file={iso},if=none,id=drive-scsi{t},format=raw,readonly=on,media=cdrom",
                 "-device", f"scsi-cd,channel=0,scsi-id={t},lun=0,drive=drive-scsi{t},id=scsi{t},physical_block_size=512"]
    return args


def boot_line(target=ANSWERS_TARGET):
    """What the install scenario types at the netinst's SILO `boot:` prompt: the `install` image at
    priority critical in English, and preseed/early_command, which debian-installer runs at start-up
    (S35initrd-preseed) before any question: load the SCSI and CD drivers itself (hw-detect hasn't
    run yet), mount the answer CD read-only by its target and run `wshlab` from it
    (answer_media.PRESEED_LOADER). The mount is retried until udev has made the device node.

    Kept short and plain on purpose: Linux 2.6.18 on sparc32 keeps 256 bytes of command line (the
    rest is cut off silently; this is about 200 with SILO's `cdrom`); it reads every word that starts
    with `-` as boot switches, letter by letter (`-h` halts, `-p` switches to the PROM console, others
    only print "Unknown boot switch"), so the only option is `-r`; and debian-installer takes a word
    with a `.` in it for a module parameter, so the script has no extension."""
    return ('install priority=critical locale=en_US preseed/early_command="modprobe esp;modprobe sr_mod;'
            f'modprobe isofs;until mount -r /dev/scsi/host0/bus0/target{target}/lun0/cd /mnt;do sleep 1;done;'
            'sh /mnt/wshlab"')


def boot_line64(dev=ANSWERS_DEV64):
    """What the install scenario types at SILO's `boot:` prompt on wheezy's CD 1 (sparc64): the
    `install` image at priority critical in English, and preseed/early_command, which loads the IDE,
    CD-ROM and ISO 9660 drivers itself (hw-detect hasn't run yet), mounts the answer CD read-only and
    runs `wshlab` from it (answer_media.PRESEED_LOADER_WHEEZY). The mount is retried until udev has
    made the device node."""
    return ('install priority=critical locale=en_US preseed/early_command="modprobe pata_cmd64x;modprobe sr_mod;'
            f'modprobe isofs;until mount -r -t iso9660 {dev} /mnt;do sleep 1;done;sh /mnt/wshlab"')


def kernel_banner(v):
    """The kernel's version line: Linux 2.6.18 (etch, sun4m) or 3.2 (wheezy, sun4u)."""
    return r"Linux version 3\.2" if sparc64(v) else r"Linux version 2\.6"


def boot_cd(m, v=None, timeout=600):
    """To SILO's `boot:` prompt on the install CD. sun4m: OpenBIOS stops at `0 >` (the disk on target 3
    comes first and doesn't boot); the CD boots as a whole device (`sd@6,0`), like Red Hat's. sun4u:
    OpenBIOS boots the CD by itself (`-boot d`, or PVE's boot order), else `cdrom:f` at `0 >`."""
    if v is not None and sparc64(v):
        if m.expect_any([r"0 >", r"boot: $"], timeout) == 0:
            m.snap("OpenBIOS prompt")
            m.send("boot cdrom:f\r")
            m.expect(r"boot: $", timeout)
        return
    _redhat.boot_cd(m, timeout)


def boot_disk(m, v, timeout=900):
    """The installed disk to the kernel: OpenBIOS boots SILO from target 3 (sun4u: the IDE disk; by
    itself, or by path or alias at `0 >`); SILO's `boot:` takes the default image (`Linux`) after 10 s,
    or at once with Return."""
    _sparc32.prom_boot(m, v, "disk")
    banner = kernel_banner(v)
    if m.expect_any([r"boot: $", banner], timeout) == 0:
        m.snap("SILO")
        m.send("\r")
        m.expect(banner, 300)
    m.snap("kernel banner")


def login(m, password="", timeout=900):
    """Wait for `login:` on ttyS0 (getty -L ttyS0, which the installer adds for a serial console) and
    log in as root (`password`, none by default)."""
    m.expect(r"login: ?$", timeout)
    m.snap("login prompt")
    m.send("root\r")
    if password:
        m.expect(r"Password: ?$", 60)
        # login prints the prompt before it turns echo off: typed at once, the first character was
        # echoed and the rest lost once ("Login incorrect")
        time.sleep(1.5)
        m.send(password + "\r")
    m.expect(PROMPT, 120)
    time.sleep(0.5)
    shell(m, "true")  # past the login messages
