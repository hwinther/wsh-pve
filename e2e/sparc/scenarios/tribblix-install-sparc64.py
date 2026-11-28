"""Install Tribblix m34 SPARC on sun4u from its live CD: boot the CD on the serial console, log in as
root and run the CD's own installer, then power off with `init 5`. ROOT_FS=zfs (the default) runs
`/root/live_install.sh -G -n <host> <disk>` (Tribblix's default: an SMI label with one big slice 0, a
ZFS root pool `rpool`, the base overlay from the CD, the ZFS boot block); ROOT_FS=ufs labels the disk
(slice 0 root, slice 1 swap) and runs `/root/ufs_install.sh -n <host> <disk>s0`. The disk then boots
with tribblix-firstboot.py (root's password, marker, network) and tribblix-boot-disk.py.

    lab.py run scenarios/tribblix-install-sparc64.py --out /mnt/sparc/runs/tribi \
        --var ISO=/mnt/sparc/iso/other-os/tribblix-sparc-0m34.iso --var BIOS=<openbios-sparc64 with 0016+0017>
    lab.py run scenarios/tribblix-install-sparc64.py --pve 9401 --out /root/runs/install   # `lab.py install`

  HOSTNAME   the installed system's node name (-n)                         (tribblix)
  DISK_DEV   the disk as illumos names it  (none: the one on the IDE primary master, ide@3/dad@0,0;
             c1t0d0 on the live CD)
  ROOT_FS    zfs: live_install.sh -G, with ZFS's aggregated I/Os kept within the IDE disk driver's
             128 KB (_tribblix.limit_zfs_aggregation(): without it FMA marked the disk DEGRADED on
             the way); ufs: ufs_install.sh on slice 0, swap on slice 1 (SWAP_MB); installs and
             boots (lab, submodules/SPARC.md "Install, UFS"), not run through PVE  (zfs)
  SWAP_MB    the swap slice with ROOT_FS=ufs, rounded up to whole cylinders  (1024)
  OVERLAYS   overlays to install on top of base, from the CD (none: base only)  (none)
  BOOT_TIMEOUT    seconds from the start to the live CD's login prompt    (5400)
  INSTALL_TIMEOUT seconds for the installer                               (7200)
  MEM, DISK_GB    as in _sparc64.py                                       (2048, 8)

Needs openbios-sparc64 with patches 0016 (the client interface with interrupts off: without it the
live CD stops on most boots) and, for a ZFS root, 0017 (the 64-bit FCode tokens of the ZFS boot block)
(submodules/SPARC.md, "Tribblix on sun4u"). The live CD imports its SMF manifests on every boot: most
of the ~45-55 minutes to its login prompt go there. The network is taken down before the install:
with one, the overlay install fetches packages from pkgs.tribblix.org (the live CD's catalogue names
older versions than the CD carries), without one it skips those.
"""
import re

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args, shell
from _tribblix import BANNER, FAIL, LIVE_ROOT_PASSWORD, limit_zfs_aggregation, login, power_off

DEFAULTS = {**BASE, "MEM": "2048", "DISK_GB": "8", "NET": "user", "HOSTNAME": "tribblix", "DISK_DEV": "",
            "ROOT_FS": "zfs", "SWAP_MB": "1024", "OVERLAYS": "", "BOOT_TIMEOUT": "5400",
            "INSTALL_TIMEOUT": "7200"}
DONE = r"^Welcome to Tribblix$"  # the installers' last line but one
ERROR = r"^ERROR: .*|^installboot: .*|No space left on device|^newfs: .*[Ee]rror"


def qemu_args(v, out):
    if not v["ISO"] and not v.get("PVE_VMID"):
        raise SystemExit("set ISO=<tribblix-sparc-0m34.iso>")
    return sparc64_args(v, out)


def find_disk(m, v):
    """The disk to install to: DISK_DEV, or the one at the IDE primary master."""
    out, _ = shell(m, "uname -a; prtconf | head -3; ls -l /dev/dsk | grep 's2 -> '", 300)
    m.snap("live system")
    disk = v["DISK_DEV"]
    if not disk:  # Tribblix names it c1t0d0
        found = re.search(r"\b(c\d+t\d+d\d+)s2 -> \S*/ide@3/dad@0,0:c\s*$", out, re.M)
        if not found:
            raise AssertionError(f"no disk on the IDE primary master (dad@0,0) in the live system:\n{out}")
        disk = found.group(1)
    elif f"{disk}s2 -> " not in out:
        raise AssertionError(f"no {disk} in the live system:\n{out}")
    return disk


def label_ufs(m, v, disk):
    """An SMI label with slice 0 (root, tag 2) from cylinder 0 and slice 1 (swap, tag 3) at the end of
    the disk: format-a-disk.sh (Tribblix's, one big slice 0) for the label, fmthard for the slices."""
    raw = f"/dev/rdsk/{disk}s2"
    shell(m, f"/root/format-a-disk.sh {raw}", 300)
    out, _ = shell(m, f"spc=$(prtvtoc {raw} | awk '/sectors\\/cylinder/ {{print $2}}');"
                      f" size=$(prtvtoc {raw} | awk '$1 == \"2\" {{print $5}}');"
                      f" swap=$(( ({v['SWAP_MB']} * 2048 + spc - 1) / spc * spc )); root=$((size - swap));"
                      " printf '0 2 00 0 %s\\n1 3 01 %s %s\\n2 5 00 0 %s\\n' $root $root $swap $size > /tmp/wsh.vtoc;"
                      f" fmthard -s /tmp/wsh.vtoc {raw}; prtvtoc {raw}", 300)
    m.snap("disk label")
    if not re.search(r"^\s+1\s+3\s+01\s", out, re.M):
        raise AssertionError(f"the disk has no swap slice 1 after fmthard:\n{out}")


def run(m, v):
    if m.expect_any([BANNER, FAIL], 900) == 1:
        m.snap("failure")
        raise AssertionError("the live CD didn't start (firmware or boot block)")
    m.snap("live CD kernel")
    login(m, LIVE_ROOT_PASSWORD, int(v["BOOT_TIMEOUT"]))
    m.metrics["live_login_s"] = round(m.elapsed(), 1)
    disk = find_disk(m, v)
    m.metrics["disk"] = disk
    # Offline: with a network the overlay install fetches packages from pkgs.tribblix.org instead of
    # the CD's (and some downloads fail under emulation)
    shell(m, "for i in $(ipadm show-if -p -o ifname | grep -v '^lo'); do ipadm delete-if $i; done;"
             " netstat -rn -f inet", 120)
    if v["ROOT_FS"] == "ufs":
        label_ufs(m, v, disk)
        # its newfs asks "construct a new file system ... (y/n)?" on the terminal
        command = f"echo y | ./ufs_install.sh -n {v['HOSTNAME']} {disk}s0 {v['OVERLAYS']}".strip()
    elif v["ROOT_FS"] == "zfs":
        # before the pool exists: the live kernel's setting for the install, and the line in the live
        # /etc/system that the installer copies to the installed system
        limit_zfs_aggregation(m)
        command = f"./live_install.sh -G -n {v['HOSTNAME']} {disk} {v['OVERLAYS']}".strip()
    else:
        raise ValueError(f"ROOT_FS {v['ROOT_FS']}: ufs or zfs")
    m.log(command)
    out, secs = shell(m, f"cd /root && {command} 2>&1; echo install-exit=$?", int(v["INSTALL_TIMEOUT"]))
    m.metrics["install_s"] = round(secs, 1)
    m.snap("installer finished")
    status = re.search(r"install-exit=(\d+)", out)
    errors = re.findall(ERROR, out, re.M)
    m.metrics["packages_missing"] = len(re.findall(r"pkgadd: ERROR: no packages were found", out))
    if not status or status.group(1) != "0" or not re.search(DONE, out, re.M) or errors:
        raise AssertionError(f"the installer failed (exit {status and status.group(1)}, errors {errors[:5]})")
    check = ("df -k /a; tail -3 /a/etc/vfstab; test -s /a/platform/sun4u/boot_archive && echo archive=ok"
             if v["ROOT_FS"] == "ufs" else
             "zpool status rpool; zfs list -r rpool; zpool get -H -o value bootfs rpool | grep -q ROOT && echo archive=ok")
    out, _ = shell(m, check, 300)
    m.snap("installed system")
    if not re.search(r"^archive=ok\s*$", out, re.M):
        raise AssertionError(f"no installed system with a boot archive on {disk}:\n{out}")
    m.metrics["poweroff_s"] = round(power_off(m), 1)
