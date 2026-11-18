"""Answer media: a small CD image made on the node from a target's answers (never from vendor files),
which the installer reads its answer file from (README.md, "Install methods", unattended).

    iso9660({"KS.CFG": b"..."}, "WSH_LAB_KS")   -> the bytes of a one-directory ISO 9660 image
    kickstart(ip=..., netmask=...)                -> Red Hat 6.2's ks.cfg (README.md, "Red Hat Linux 6.2")

Standard library only: the node needs no genisoimage, and tests/test_targets.py reads the image back
with dos_tools.Iso.
"""
import re
import struct

SECTOR = 2048
# ISO 9660 level 1 file names: 8.3, d-characters only
NAME = re.compile(r"[A-Z0-9_]{1,8}(\.[A-Z0-9_]{0,3})?")
VOLUME = re.compile(r"[A-Z0-9_]{1,32}")


def _both16(n):
    return struct.pack("<H", n) + struct.pack(">H", n)


def _both32(n):
    return struct.pack("<I", n) + struct.pack(">I", n)


# 1970-01-01 00:00:00 UTC: fixed, so the same answers give the same image
_RECORDED = bytes([70, 1, 1, 0, 0, 0, 0])
_VOLUME_DATE = b"1970010100000000\x00"


def _record(name, lba, size, is_dir):
    rec = (bytes([0]) + _both32(lba) + _both32(size) + _RECORDED + bytes([2 if is_dir else 0, 0, 0])
           + _both16(1) + bytes([len(name)]) + name)
    rec += b"\x00" * (len(rec) % 2 == 0)  # padded to an even length (33 + name length)
    return bytes([len(rec) + 1]) + rec


def iso9660(files, volume="CDROM"):
    """A one-directory ISO 9660 image (level 1, no Rock Ridge or Joliet) with `files` ({8.3 name in
    upper case: bytes}); Linux shows the names in lower case (`ks.cfg`)."""
    if not VOLUME.fullmatch(volume):
        raise ValueError(f"volume ID {volume!r}: up to 32 of A-Z 0-9 _")
    for name in files:
        if not NAME.fullmatch(name):
            raise ValueError(f"{name!r}: not an ISO 9660 level 1 name (8.3, A-Z 0-9 _)")
    names = sorted(files)
    root_lba, data_lba = 20, 21
    extents, lba = {}, data_lba
    for name in names:
        extents[name] = lba
        lba += max(1, -(-len(files[name]) // SECTOR))
    total = lba
    root = _record(b"\x00", root_lba, SECTOR, True) + _record(b"\x01", root_lba, SECTOR, True)
    for name in names:
        root += _record(f"{name};1".encode(), extents[name], len(files[name]), False)
    if len(root) > SECTOR:
        raise ValueError("too many files for one directory sector")
    path_l = bytes([1, 0]) + struct.pack("<I", root_lba) + struct.pack("<H", 1) + b"\x00\x00"
    path_m = bytes([1, 0]) + struct.pack(">I", root_lba) + struct.pack(">H", 1) + b"\x00\x00"
    pvd = (bytes([1]) + b"CD001" + bytes([1, 0]) + b" " * 32 + volume.encode().ljust(32) + b"\x00" * 8
           + _both32(total) + b"\x00" * 32 + _both16(1) + _both16(1) + _both16(SECTOR)
           + _both32(len(path_l))  # one record: 8 bytes, the root's 1-byte name and its padding
           + struct.pack("<I", 18) + struct.pack("<I", 0) + struct.pack(">I", 19) + struct.pack(">I", 0)
           + _record(b"\x00", root_lba, SECTOR, True)
           + b" " * 128 * 4 + b" " * 37 * 3 + _VOLUME_DATE * 2 + b"0" * 16 + b"\x00" + _VOLUME_DATE + bytes([1, 0]))
    terminator = bytes([255]) + b"CD001" + bytes([1])
    image = bytearray(total * SECTOR)
    for at, data in ((16, pvd), (17, terminator), (18, path_l), (19, path_m), (root_lba, root)):
        image[at * SECTOR:at * SECTOR + len(data)] = data
    for name in names:
        image[extents[name] * SECTOR:extents[name] * SECTOR + len(files[name])] = files[name]
    return bytes(image)


def image(fmt, ip, netmask):
    """The answer CD of a target's install "answers" format, from the address and netmask `lab.py
    install` gives the installer (--ip, --netmask)."""
    if fmt == "kickstart":
        return iso9660({"KS.CFG": kickstart(ip, netmask).encode()}, "WSH_LAB_KS")
    raise ValueError(f"answer format {fmt!r}")


FORMATS = ("kickstart",)


# --- Red Hat Linux 6.2 ------------------------------------------------------------------------------

def kickstart(ip, netmask, timezone="MET"):
    """Red Hat 6.2's kickstart file for `lab.py install` (anaconda 6.2 reads it with
    `ks=cdrom:/ks.cfg`, from the first CD-ROM it can mount): the Base group and iputils (ping; Base
    has none) from the install CD onto the first disk, a static address on eth0, SILO's screens left
    to the scenario (6.2's kickstart has no answer for them on SPARC), reboot at the end.

    The disk: /boot (32 MB) first, then / and 128 MB swap. SILO's first stage reads its second stage
    through the PROM, which on sun4m reads only the start of the disk: with / alone on a 3 GiB disk
    /boot/second.b landed past 2 GB and neither OpenBIOS nor the SS-5 PROM got past SILO's `S`.

    Root gets no password here: the first boot sets it at passwd's prompts (redhat-firstboot.py), so
    nothing secret is on the image; %post leaves root without one for that first login (the
    installer already put a getty on the serial console, `co:...:/sbin/getty console`, and `console`
    in /etc/securetty) and turns kudzu off, whose hardware probe asks on the console. The host name
    is the first boot's too (`network --hostname` didn't reach /etc/sysconfig/network)."""
    for what, val in (("ip", ip), ("netmask", netmask), ("timezone", timezone)):
        if not re.fullmatch(r"[A-Za-z0-9._/+-]+", val or ""):
            raise ValueError(f"kickstart {what} {val!r}")
    return f"""\
# lab.py install (wsh-pve e2e/sparc answer_media.kickstart): Red Hat Linux 6.2
lang en_US
keyboard sunkeymap
network --bootproto static --ip {ip} --netmask {netmask}
cdrom
install
zerombr yes
clearpart --all
part /boot --size 32
part / --size 1024 --grow
part swap --size 128
mouse none
timezone --utc {timezone}
rootpw --iscrypted *
auth --useshadow --enablemd5
skipx
reboot
%packages
@ Base
iputils
%post
sed 's/^root:[^:]*:/root::/' /etc/shadow > /etc/shadow.wsh && cat /etc/shadow.wsh > /etc/shadow
rm -f /etc/shadow.wsh
/sbin/chkconfig kudzu off
"""
