"""Add the TCX packages to an installed Solaris disk from its install CD, so the disk can run with
`VGA=tcx`: boots the disk on ttya, logs in, `pkgadd`s PKGS from the CD (vold's /cdrom/cdrom0, else mounted by hand), touches /reconfigure (the next
boot then creates /dev/fbs/tcx0 and /dev/fb) and shuts down.

    lab.py run scenarios/solaris-tcx-packages.py --out /mnt/runs/tcxpkg \
        --var DISK=/mnt/runs/tcxpkg/disk.raw --var ISO=/mnt/os/iso/solaris_2.6_598_sparc.iso

The installer adds the TCX cluster (SUNWCtcx: SUNWtcx = kernel/drv/tcx, SUNWtcxow = the X server's
ddxSUNWtcx.so.1, SUNWtcxu = the XGL pipeline) only when it finds a TCX at install time (`.clustertoc`:
`SUNW_CSRMBRIFF=(smcc.dctoc tcx)SUNWCtcx`); a disk installed on ttya or with the cg3 has none of it.

  PRODUCT     the package directory on the CD's slice 0      (Solaris_2.6/Product)
  PKGS        packages to add (SUNWtcx is per platform: SUNWtcx.m on the CD)  (SUNWtcx.m SUNWtcxow SUNWtcxu)
  TTYA_LOGIN  1: also a root login on ttya while the console is on the framebuffer (lab
              convenience: fb-display.py's checks run there); once per disk      (none)
The disk is changed: give it a copy.
"""
from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "PRODUCT": "Solaris_2.6/Product",
            "PKGS": "SUNWtcx.m SUNWtcxow SUNWtcxu", "TTYA_LOGIN": ""}

# pkgadd without questions (Solaris 2.x admin file keys)
ADMIN = ["mail=", "instance=overwrite", "partial=nocheck", "runlevel=nocheck", "idepend=nocheck",
         "rdepend=nocheck", "space=nocheck", "setuid=nocheck", "conflict=nocheck", "action=nocheck",
         "basedir=default"]


def qemu_args(v, out):
    return sparc32_args(v, out)


def sh(m, command, timeout=600):
    """One shell command (the tty takes 256 characters a line), waiting for the prompt after it."""
    m.send(f"{command}; echo DONE-$?\r")
    return m.expect(r"DONE-(\d+)\s*\n", timeout).group(1)


def run(m, v):
    prom_boot(m, v, "disk")
    login(m)
    if v["PKGS"]:  # PKGS= (empty): only TTYA_LOGIN, e.g. to see what a disk without them does
        sh(m, "rm -f /tmp/admin")
        for line in ADMIN:
            sh(m, f"echo {line} >> /tmp/admin")
        # vold mounts the CD at /cdrom/cdrom0 by itself once it is up; mount it by hand when it hasn't
        cd = "/cdrom/cdrom0/s0"
        if sh(m, f"sleep 20; ls -d {cd}/{v['PRODUCT']}", 120) != "0":
            cd = "/mnt"
            if sh(m, "mount -F hsfs -o ro /dev/dsk/c0t6d0s0 /mnt", 120) != "0":
                raise AssertionError("can't mount the CD's slice 0")
        for pkg in v["PKGS"].split():
            sh(m, f"pkgadd -n -a /tmp/admin -d {cd}/{v['PRODUCT']} {pkg}", 1800)
        sh(m, "pkginfo " + " ".join(p.split(".")[0] for p in v["PKGS"].split()))
        sh(m, "pkgchk -l SUNWtcx SUNWtcxow | grep Pathname")
        m.snap("packages added")
        if sh(m, "pkginfo -q SUNWtcx && pkginfo -q SUNWtcxow") != "0":
            raise AssertionError("SUNWtcx/SUNWtcxow not installed")
    if v["TTYA_LOGIN"]:
        # A login on ttya only while the console is elsewhere (prtconf -F: the console framebuffer,
        # none when the console is on ttya), else it fights the console for the port. root may log
        # in only on the console (/etc/default/login CONSOLE=): allow it everywhere.
        for line in ["#!/bin/sh", "/usr/sbin/prtconf -F >/dev/null 2>&1 || exec sleep 99999999",
                     'exec /usr/lib/saf/ttymon -g -h -p "ttya login: " -d /dev/term/a -l 9600']:
            sh(m, "echo '" + line + "' >> /etc/ttya-login")
        sh(m, "chmod 755 /etc/ttya-login; echo 'ta:234:respawn:/etc/ttya-login' >> /etc/inittab")
        sh(m, "sed 's/^CONSOLE=/#CONSOLE=/' /etc/default/login > /tmp/login && cp /tmp/login /etc/default/login")
    sh(m, "touch /reconfigure")
    power_off(m, "init 5")
