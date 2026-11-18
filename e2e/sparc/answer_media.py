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


def image(fmt, ip, netmask, gateway=None, dns=(), domain=None, hostname=None, proxy=None):
    """The answer CD of a target's install "answers" format, from the network `lab.py install` gives
    the installer (--ip, --netmask; the preseed file also takes --gateway, --dns, --domain, the host
    name and --apt-proxy: Debian's netinst fetches its packages during the install)."""
    if fmt == "kickstart":
        return iso9660({"KS.CFG": kickstart(ip, netmask).encode()}, "WSH_LAB_KS")
    if fmt == "preseed":
        return iso9660({"PRESEED.CFG": preseed(ip, netmask, gateway, dns, domain, hostname, proxy).encode(),
                        "WSHLAB": PRESEED_LOADER.encode()}, "WSH_LAB_PRESEED")
    raise ValueError(f"answer format {fmt!r}")


FORMATS = ("kickstart", "preseed")


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


# --- Debian GNU/Linux 4.0 "etch" ---------------------------------------------------------------------

# What preseed/early_command on SILO's boot line runs (debian-installer reads the kernel command line
# into its database at start-up and runs that command right away, before any question): the answer
# CD's SCSI target is in the command (_debian.boot_line), this script (`wshlab`) is on the CD. It loads the
# preseed file, unmounts the CD and takes it out of the kernel's sight, because Etch's cdrom-detect
# mounts the first CD-ROM that mounts at all as the install CD and gives up when that isn't Debian's
# (the answer CD on target 5 comes before the netinst on 6); and it hides the floppy drive.
PRESEED_LOADER = """# lab.py install (wsh-pve e2e/sparc answer_media.PRESEED_LOADER): run by preseed/early_command
set -e
debconf-set-selections /mnt/preseed.cfg
dev=
while read d m rest; do [ "$m" != /mnt ] || dev=$d; done < /proc/mounts
sys=$(udevinfo -q path -n "$dev")
umount -l /mnt  # busybox's plain umount fails here (ENOSYS); the lazy one works
echo 1 > "/sys$sys/device/delete"
# The floppy drive QEMU's sun4m always has (empty): partman's disk scan opens it, and Linux 2.6.18's
# floppy driver oopses in reset_interrupt (NULL pointer, in keventd), which stops the installer;
# without a device node the scan skips it
echo 'KERNEL=="fd[0-9]*", OPTIONS+="ignore_device"' > /etc/udev/rules.d/00-wsh-lab-nofloppy.rules
rm -rf /dev/fd[0-9]* /dev/floppy
logger -t wsh-lab "preseed loaded from $dev; $sys removed; no floppy device nodes"
"""

ETCH_MIRROR = ("archive.debian.org", "/debian")  # etch's packages since 2012 (sparc: still served)


def preseed(ip, netmask, gateway=None, dns=(), domain=None, hostname=None, proxy=None, timezone="Etc/UTC"):
    """Debian 4.0 (etch) debian-installer's preseed file for `lab.py install` (README.md, "Debian
    GNU/Linux 4.0"): the network static on eth0 (the netinst fetches the base system from
    archive.debian.org, so the router and a name server must reach it), etch from archive.debian.org
    without a signature check, the first (blank) disk with /boot (40-64 MB, ext2) first, then /
    (ext3) and 128-256 MB swap, no tasks (the base system and the kernel), SILO on the disk, reboot at
    the end.

    The disk: SILO's first stage reads its second stage through the PROM, which on sun4m reads only
    the start of the disk (Red Hat 6.2: /boot/second.b past 2 GB never loaded), hence /boot first.
    partman-auto/disk names it (devfs name), or partman asks for the partitioning method; partman
    writes the Sun label itself (on an old one the new label kept its geometry and / didn't fit).

    The archive: every key that signed etch on archive.debian.org has expired (2009-2013);
    debian-installer's own debian-installer/allow_unauthenticated makes debootstrap run without
    --keyring and apt allow unauthenticated packages until the end of the install (base-installer
    writes /etc/apt/apt.conf.d/00AllowUnauthenticated and finish-install removes it). The security
    archive (security.debian.org, apt-setup/security_host) is left out: etch's isn't served there.

    `proxy` (--apt-proxy, e.g. an apt-cacher-ng): mirror/http/proxy, which debootstrap and apt use
    during the install; debian-installer also writes it to the installed system's /etc/apt/apt.conf
    (Acquire::http::Proxy), its documented behaviour, so later apt-get runs use the same cache.

    Root gets the hash `*` here (no password works) and the late command empties it, so nothing secret is
    on the image: the first boot logs in on ttyS0 without one and sets it (debian-firstboot.py).
    The late command also comments out the netinst's `deb cdrom:` line in sources.list (the CD is
    ejected after the install; apt would ask for it).
    No user is made here (passwd/make-user false); the first boot adds the optional one."""
    dns = list(dns or [])
    for what, val in (("ip", ip), ("netmask", netmask), ("gateway", gateway), ("timezone", timezone),
                      *(("dns", d) for d in dns), ("domain", domain), ("hostname", hostname)):
        if val is not None and not re.fullmatch(r"[A-Za-z0-9._/+-]+", val):
            raise ValueError(f"preseed {what} {val!r}")
    if proxy is not None and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?/?", proxy):
        raise ValueError(f"preseed proxy {proxy!r}: an http(s)://host[:port] URL")
    if not gateway or not dns:
        raise ValueError("preseed: the netinst needs a router (--gateway) and a name server (--dns)")
    recipe = ("wshlab :: "
              "40 500 64 ext2 $bootable{ } method{ format } format{ } use_filesystem{ } filesystem{ ext2 } mountpoint{ /boot } . "
              "1000 10000 1000000000 ext3 method{ format } format{ } use_filesystem{ } filesystem{ ext3 } mountpoint{ / } . "
              "128 512 256 linux-swap method{ swap } format{ } .")
    host, directory = ETCH_MIRROR
    return f"""\
# lab.py install (wsh-pve e2e/sparc answer_media.preseed): Debian GNU/Linux 4.0 (etch), sparc
d-i preseed/early_command string
d-i debian-installer/locale string en_US
d-i console-keymaps-sun/keymap select us
d-i netcfg/choose_interface select eth0
d-i netcfg/disable_dhcp boolean true
d-i netcfg/get_ipaddress string {ip}
d-i netcfg/get_netmask string {netmask}
d-i netcfg/get_gateway string {gateway}
d-i netcfg/get_nameservers string {" ".join(dns)}
d-i netcfg/confirm_static boolean true
d-i netcfg/get_hostname string {hostname or "debian"}
d-i netcfg/get_domain string {domain or ""}
d-i mirror/country string enter information manually
d-i mirror/http/hostname string {host}
d-i mirror/http/directory string {directory}
d-i mirror/http/proxy string {proxy or ""}
d-i mirror/suite string etch
d-i debian-installer/allow_unauthenticated string true
d-i apt-setup/security_host string
d-i clock-setup/utc boolean true
d-i time/zone string {timezone}
d-i partman-auto/disk string /dev/discs/disc0/disc
d-i partman-auto/method string regular
d-i partman-auto/expert_recipe string {recipe}
d-i partman/confirm_write_new_label boolean true
d-i partman/choose_partition select Finish partitioning and write changes to disk
d-i partman/confirm boolean true
d-i passwd/root-login boolean true
d-i passwd/root-password-crypted password *
d-i passwd/make-user boolean false
tasksel tasksel/first multiselect
popularity-contest popularity-contest/participate boolean false
d-i finish-install/reboot_in_progress note
d-i preseed/late_command string chroot /target passwd -d root; chroot /target sed -i 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list
"""
