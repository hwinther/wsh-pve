"""What the Red Hat Linux 6.2 (SPARC) install, first-boot and boot scenarios share, on sun4m (_sparc32.py,
the console on ttya; Linux calls it ttyS0). README.md, "Red Hat Linux 6.2".

  KS_ISO   the answer CD (a lab QEMU of its own): an ISO 9660 image with ks.cfg, on SCSI target 5,
           the first CD-ROM Linux finds (sr0), so `ks=cdrom:/ks.cfg` reads it; the Red Hat CD on
           target 6 is sr1 and the install source. Default: <out>/ks.iso, written from
           answer_media.kickstart() with IP and NETMASK. Attached to a PVE VM, the VM has it
           already (`lab.py install` puts it on scsi5)
"""
import os
import re
import time

import _sparc32
from lab import QemuDied

DEFAULTS = {**_sparc32.DEFAULTS, "VGA": "none", "BOOT": "c", "KS_ISO": ""}
KS_TARGET = "5"  # the answer CD's SCSI target: before the Red Hat CD (6), after the disk (3)
PROMPT = r"\]# ?$"  # root's bash prompt, `[root@<host> <dir>]# `
F12 = "\x1b[24~"  # newt's "next screen": the screen's defaults, as OK


def qemu_args(v, out, answers=False):
    """The lab's own QEMU: _sparc32's machine (disk on target 3, CD on 6), with `answers` the answer CD
    on target 5 (KS_ISO, or one written from the kickstart variables)."""
    args = _sparc32.qemu_args(v, out)
    if answers:
        import answer_media
        iso = v["KS_ISO"]
        if not iso:
            iso = os.path.join(out, "ks.iso")
            with open(iso, "wb") as f:
                f.write(answer_media.image("kickstart", v["IP"], v["NETMASK"]))
        t = KS_TARGET
        args += ["-drive", f"file={iso},if=none,id=drive-scsi{t},format=raw,readonly=on,media=cdrom",
                 "-device", f"scsi-cd,channel=0,scsi-id={t},lun=0,drive=drive-scsi{t},id=scsi{t},physical_block_size=512"]
    return args


def fkey(m, seq):
    """A function key's escape sequence in one write (newt would take a lone ESC on its own)."""
    m.ser.sendall(seq.encode("latin-1"))
    time.sleep(0.4)


def boot_cd(m, timeout=600):
    """To SILO's `boot:` prompt on the Red Hat CD. OpenBIOS stops at `0 >` (the disk on target 3 comes
    first and doesn't boot); the CD boots as a whole device (`sd@6,0`): its SILO isn't in slice d,
    where _sparc32.prom_boot() looks for Solaris's."""
    if m.expect_any([r"0 >", r"boot: $"], timeout) == 0:
        m.snap("OpenBIOS prompt")
        m.send(f"boot {_sparc32.ESP}/sd@6,0\r")
        m.expect(r"boot: $", timeout)


def boot_disk(m, v, timeout=900):
    """The installed disk to the kernel: OpenBIOS boots SILO from target 3 (by itself, or by path at
    `0 >`), Return at SILO's `boot:` takes the default image (`linux`)."""
    _sparc32.prom_boot(m, v, "disk")
    if m.expect_any([r"boot: $", r"Linux version 2\.2"], timeout) == 0:
        m.snap("SILO")
        m.send("\r")
        m.expect(r"Linux version 2\.2", 300)
    m.snap("kernel banner")


def shell(m, command, timeout=300):
    """Run a command at root's prompt and return its output (up to the marker line)."""
    m.send(f"{command}; echo END-OF-COMMAND")
    m.send("\r")
    return m.expect(r"^((?:.*\n)*?)END-OF-COMMAND\s*$", timeout).group(1)  # at a line start: not the echo


def login(m, password="", timeout=900):
    """Wait for `login:` on ttyS0 and log in as root (`password`, none by default)."""
    m.expect(r"login: ?$", timeout)
    m.snap("login prompt")
    m.send("root\r")
    if password:
        m.expect(r"Password: ?$", 60)
        m.send(password + "\r")
    m.expect(PROMPT, 120)
    shell(m, "true")  # past the login messages


def passwd(m, user, password):
    """Set `user`'s password with passwd(1) at its prompts (`New UNIX password:`, `Retype new UNIX
    password:`; they don't echo). A short or dictionary password gets `BAD PASSWORD`, which root
    may ignore: the same answer goes to every prompt until passwd ends."""
    m.send(f"passwd {user}; echo PASSWD-RC=$?\r")
    for _ in range(6):
        r = m.expect(r"(?P<prompt>[Pp]assword: ?$)|PASSWD-RC=(?P<rc>\d+)", 120)
        if r.group("rc") is not None:
            break
        time.sleep(0.5)
        m.send(password + "\r")
    else:
        raise AssertionError(f"passwd {user} kept asking")
    if r.group("rc") != "0":
        raise AssertionError(f"passwd {user} failed (exit {r.group('rc')})")
    shell(m, "true")


def power_off(m, timeout=300):
    """`sync; poweroff` and wait for the VM to end (Linux powers sun4m off through the AUXIO register:
    "Power off control detected" in the boot messages)."""
    m.send("sync; poweroff\r")
    try:
        code = m.wait_exit(timeout)
    except QemuDied:
        code = m.proc.returncode
    if code != 0:
        raise AssertionError(f"QEMU exited with {code} at power-off")


def check_output(out, pattern, what):
    if pattern and not re.search(pattern, out):
        raise AssertionError(f"no {pattern!r} in the output of {what!r}")
