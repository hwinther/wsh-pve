"""What the Debian GNU/Linux 4.0 "etch" (sparc) install, first-boot and boot scenarios share, on sun4m
(_sparc32.py, the console on ttya; Linux calls it ttyS0). README.md, "Debian GNU/Linux 4.0".

  ANSWERS_ISO  the answer CD (a lab QEMU of its own): an ISO 9660 image with preseed.cfg and
               wshlab.sh on SCSI target 5; the netinst on target 6 is the install CD. Default:
               <out>/preseed.iso, written from answer_media.preseed() with IP, NETMASK, GATEWAY,
               DNS, DOMAIN and HOSTNAME. Attached to a PVE VM, the VM has it already (`lab.py
               install` puts it on scsi5)
"""
import os
import time

import _redhat
import _sparc32

DEFAULTS = {**_sparc32.DEFAULTS, "VGA": "none", "BOOT": "c", "ANSWERS_ISO": ""}
ANSWERS_TARGET = "5"  # the answer CD's SCSI target: after the disk (3), before the netinst (6)
PROMPT = r":~# ?$"  # root's bash prompt in its home, `<host>:~# `

# The rest is _redhat's: a Linux root shell on ttyS0 behaves the same
shell = _redhat.shell
passwd = _redhat.passwd
power_off = _redhat.power_off
check_output = _redhat.check_output


def qemu_args(v, out, answers=False):
    """The lab's own QEMU: _sparc32's machine (disk on target 3, CD on 6), with `answers` the answer CD
    on target 5 (ANSWERS_ISO, or one written from the network variables)."""
    args = _sparc32.qemu_args(v, out)
    if answers:
        import answer_media
        iso = v["ANSWERS_ISO"]
        if not iso:
            iso = os.path.join(out, "preseed.iso")
            with open(iso, "wb") as f:
                f.write(answer_media.image("preseed", v["IP"], v["NETMASK"], v["GATEWAY"] or None,
                                           v["DNS"].split(), v["DOMAIN"] or None, v["HOSTNAME"] or None))
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


def boot_cd(m, timeout=600):
    """To SILO's `boot:` prompt on the netinst: OpenBIOS stops at `0 >` (the disk on target 3 comes
    first and doesn't boot); the CD boots as a whole device (`sd@6,0`), like Red Hat's."""
    _redhat.boot_cd(m, timeout)


def boot_disk(m, v, timeout=900):
    """The installed disk to the kernel: OpenBIOS boots SILO from target 3 (by itself, or by path at
    `0 >`); SILO's `boot:` takes the default image (`Linux`) after 10 s, or at once with Return."""
    _sparc32.prom_boot(m, v, "disk")
    if m.expect_any([r"boot: $", r"Linux version 2\.6"], timeout) == 0:
        m.snap("SILO")
        m.send("\r")
        m.expect(r"Linux version 2\.6", 300)
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
