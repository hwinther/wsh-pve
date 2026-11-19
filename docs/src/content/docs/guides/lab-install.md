---
title: Lab install targets
description: One command on a Proxmox VE node that creates a VM with a tested profile and installs a guest OS into it unattended, ending with known login details
---

An **install target** is a guest the sparc lab can install by itself: a tested VM profile (machine,
firmware, memory, display, disk and NIC), the install media it needs under expected file names, how
the installer is driven, and the login the finished VM has. One command on a PVE node creates the VM,
installs the guest, sets a known root password, ejects the media and leaves an installed VM that is
powered off, with its login details in the VM's notes.

:::caution[Publicly known passwords]
The targets' root password (`wshlab` unless you pass `--root-password`) is written in this public
documentation, in the repository and in each VM's notes. These are throwaway lab VMs: don't reuse a
real password, and change the password before a VM is reachable from anywhere untrusted. The tool
enables no network service beyond what the guest's installer enables by default (Solaris 2.6 runs
telnet and the r-services from inetd; Solaris 10 keeps its installer's default "remote services
enabled", which includes telnet; root logins are allowed on the console only).
:::

## Targets

| Target | What | Profile | Media (on `local:iso/`) | Login | Time |
| --- | --- | --- | --- | --- | --- |
| `sol26-ss5` | Solaris 2.6 5/98, End User | SS-5, OpenBIOS, 256 MB, serial console (`serial0`), Sun-labelled disk on `scsi3` (3G, or 9G with `--disk-size 9G`), lance | `solaris_2.6_598_sparc.iso` | `root` / `wshlab` | ~12 min |
| `sol22-ss10` | Solaris 2.2, End User (Quick Install) | SS-10, OpenBIOS, 256 MB, one CPU, serial console, Sun-labelled 3G disk on `scsi3`, lance; the CD answers as a disk (`cd_as_disk=1`); needs `pve-qemu-kvm` 11.1.3-2+wsh22 or later | `Solaris_2.2.img` | `root` / `wshlab` | ~9 min |
| `sol23-ss5` | Solaris 2.3 Edition II, End User (Quick Install) | SS-5, OpenBIOS, 256 MB, otherwise as `sol22-ss10` (also needs +wsh22) | `Solaris2.3Edition-II.iso` | `root` / `wshlab` | ~10 min |
| `sol23-ss20` | Solaris 2.3 Edition II, End User (Quick Install) | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as `sol23-ss5` | `Solaris2.3Edition-II.iso` | `root` / `wshlab` | ~9 min |
| `sol24-ss5` | Solaris 2.4 HW 3/95, End User | as `sol23-ss5` | `solaris_2.4_sparc.iso` | `root` / `wshlab` | ~8 min |
| `sol24-ss20` | Solaris 2.4 HW 3/95, End User | as `sol23-ss20` | `solaris_2.4_sparc.iso` | `root` / `wshlab` | ~8 min |
| `sol251-ss5` | Solaris 2.5.1 11/97, End User | SS-5, `ss5.bin` (Sun PROM), 256 MB, serial console, Sun-labelled 3G disk on `scsi3`, lance; the CD answers as a disk (`cd_as_disk=1`) | `solaris_2.5.1_1197.iso` | `root` / `wshlab` | ~45 min |
| `sol25-ss5` | Solaris 2.5 HW 1/96, End User | SS-5, OpenBIOS, 256 MB, serial console, Sun-labelled 3G disk on `scsi3`, lance; the CD answers as a disk (`cd_as_disk=1`) | `solaris2.5_sparc.iso` | `root` / `wshlab` | ~9 min |
| `sol25-ss20` | Solaris 2.5 HW 1/96, End User | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as `sol25-ss5` | `solaris2.5_sparc.iso` | `root` / `wshlab` | ~9 min |
| `sol26-ss20` | Solaris 2.6 5/98, End User | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as above | `solaris_2.6_598_sparc.iso` | `root` / `wshlab` | ~12 min |
| `sol7-ss5` | Solaris 7 3/99, End User | as `sol26-ss5` (3G disk, or 9G with `--disk-size 9G`) | `Sol7.399InstallationSparc.iso` | `root` / `wshlab` | ~11 min |
| `sol7-ss20` | Solaris 7 3/99, End User | as `sol26-ss20` (3G disk, or 9G with `--disk-size 9G`) | `Sol7.399InstallationSparc.iso` | `root` / `wshlab` | ~10 min |
| `sol8-ss20` | Solaris 8 1/01, Entire Group, installed by Web Start from three CDs (swapped by the install) | SS-20, OpenBIOS, 512 MB, one CPU, 9G disk | `sun-solaris-8-0101-installation-sparc.iso`, `sun-solaris-8-0101-software-cd1-sparc.iso`, `sun-solaris-8-0101-software-cd2-sparc.iso` | `root` / `wshlab` | ~30 min |
| `sol9-ss20` | Solaris 9, End User, Web Start from the DVD | as `sol8-ss20` | `SOL_9_SPARC_DVD.iso` | `root` / `wshlab` | ~27 min |
| `sol8-ss5` | Solaris 8 2/02, Entire Group, installed by Web Start from three CDs (swapped by the install) | SS-5, OpenBIOS, 256 MB, 9G disk, otherwise as `sol26-ss5` | `Sol8.0202.Sparc.iso`, `Sol8.0202.Sparc-Software_1of2.iso`, `Sol8.0202.Sparc-Software_2of2.iso` | `root` / `wshlab` | ~37 min |
| `sol9-ss5` | Solaris 9 9/05, End User, Web Start from the DVD | as `sol8-ss5` | `solaris-2.9-sparc.iso` | `root` / `wshlab` | ~30 min |
| `sol10-sun4u` | Solaris 10 1/13, the default software group | sparc64 (sun4u), OpenBIOS, 1024 MB, serial console, a blank 16 GiB disk on `ide0`, the DVD on `ide2`, `sunhme`; needs `pve-qemu-kvm` 11.1.3-2+wsh13 or later | `sol-10-u11-ga-sparc-dvd.iso` | `root` / `wshlab` | ~110 min |
| `tribblix-m34-sun4u` | Tribblix m34 for SPARC (illumos), the base system on a ZFS root | sparc64 (sun4u), OpenBIOS, 2048 MB, serial console, a blank 8 GiB disk on `ide0`, the live CD on `ide2`, `sunhme`; needs pve-qemu-kvm 11.1.3-2+wsh20 or later (OpenBIOS patches 0016 and 0017, QEMU `wsh/0036`) | `tribblix-sparc-0m34.iso` | `root` / `wshlab` | ~4.3 h |
| `sunos414-ss5` | SunOS 4.1.4 (Solaris 1.1.2), Programmer, suninstall's Quick install | SS-5, OpenBIOS, 256 MB (64 MB during the install), serial console, 3 GiB disk on `scsi3` (SUN2.9G label, `/usr` slice cut to 1 GB), lance | `sunos414-cd.iso` (made from the CD's raw BIN, see "Media") | `root` / `wshlab` | ~6 min |
| `sunos413u1b-ss5` | SunOS 4.1.3_U1B (Solaris 1.1.1B), Programmer, suninstall's Quick install | as `sunos414-ss5` | `sunos_4.1.3U1B.iso` | `root` / `wshlab` | ~6 min |
| `sunos413u1b-ss20` | SunOS 4.1.3_U1B (Solaris 1.1.1B), Programmer, suninstall's Quick install | SS-20, OpenBIOS, 512 MB (64 MB during the install), one CPU, otherwise as `sunos414-ss5` | `sunos_4.1.3U1B.iso` | `root` / `wshlab` | ~6 min |
| `msdos622` | MS-DOS 6.22 from the three Setup floppies | i440fx, SeaBIOS, Pentium, TCG, 32 MB, std VGA, 1 GiB IDE disk, ne2k_pci (unused), floppy first in the boot order | `msdos622-disk1.img` ... `-disk3.img` (on `local:floppy/`) | none (no password; VGA console) | ~5 min |
| `freedos14` | FreeDOS 1.4, Floppy Edition, base install | as `msdos622` | `freedos14-boot.img`, `freedos14-disk1.img` ... `-disk6.img` (on `local:floppy/`) | none (VGA console) | ~11 min |
| `openbsd80-sun4u` | OpenBSD 8.0, all sets but X11 (base, comp, man, game), ntpd off | sun4u, OpenBIOS, 512 MB, serial console, 8 GiB blank disk on `ide0`, CD on `ide2`, sunhme; needs `pve-qemu-kvm` 11.1.3-2+wsh22 or later (OpenBIOS patch 0023) | `install80.iso` | `root` / `wshlab` | ~19 min |
| `openbsd59-ss5` | OpenBSD 5.9 (the last release for 32-bit sparc), all sets but X11 (base, comp, man, game), checked against the release's signature by the installer, ntpd off | SS-5, OpenBIOS, 256 MB, serial console (needed: with a framebuffer the kernel panics), 8 GiB blank disk on `scsi3`, the boot CD on `scsi6`, the sets CD on `scsi5`, lance (`le0`) | `cd59.iso`, `openbsd59-sparc-sets.iso` (made on the node, below) | `root` / `wshlab` | ~10 min |
| `openbsd59-ss20` | as `openbsd59-ss5` | SS-20, OpenBIOS, 512 MB, one CPU (OpenBSD/sparc has no multiprocessor kernel), otherwise as `openbsd59-ss5` | `cd59.iso`, `openbsd59-sparc-sets.iso` | `root` / `wshlab` | ~10 min |
| `netbsd111-sparc64` | NetBSD 11.1, without X11 | sun4u, OpenBIOS, 512 MB, serial console, 8 GiB blank disk on `ide0`, CD on `ide2`, sunhme | `NetBSD-11.1-sparc64.iso` | `root` / `wshlab` | ~11 min |
| `netbsd111-sparc` | NetBSD 11.1, Minimal | SS-5, OpenBIOS, 256 MB, serial console, 3 GiB blank disk on `scsi3`, lance | `NetBSD-11.1-sparc.iso` | `root` / `wshlab` | ~7 min |
| `netbsd111-sparc-ss20` | NetBSD 11.1, Minimal | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as `netbsd111-sparc` | `NetBSD-11.1-sparc.iso` | `root` / `wshlab` | ~7 min |
| `redhat62-ss5` | Red Hat Linux 6.2, Base, installed by kickstart | SS-5, OpenBIOS, 256 MB, serial console, Sun-labelled 3G disk on `scsi3`, lance (`eth0`); an answer CD on `scsi5` during the install only | `redhat-6.2-sparc.iso` | `root` / `wshlab` | ~6 min |
| `redhat62-ss20` | Red Hat Linux 6.2, Base, installed by kickstart | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as `redhat62-ss5` | `redhat-6.2-sparc.iso` | `root` / `wshlab` | ~5 min |
| `debian40-ss5` | Debian GNU/Linux 4.0 (etch), the base system, installed by preseed from the netinst CD and `archive.debian.org`; needs `pve-qemu-kvm` 11.1.3-2+wsh20 or later (the ESP fix `wsh/0038`) | SS-5, OpenBIOS, 256 MB, serial console, Sun-labelled 3G disk on `scsi3`, lance (`eth0`); an answer CD on `scsi5` during the install only; `--gateway` and `--dns` required | `debian-40r9-sparc-netinst.iso` | `root` / `wshlab` | ~22-26 min |
| `debian40-ss20` | as `debian40-ss5` | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as `debian40-ss5` | `debian-40r9-sparc-netinst.iso` | `root` / `wshlab` | ~17-21 min |

The DOS targets are driven on the VGA text screen (read exactly from the text buffer), swap the
floppies when the installer asks, write a known `CONFIG.SYS`/`AUTOEXEC.BAT` (MS-DOS: HIMEM, `DOS=HIGH`,
no SMARTDRV) and the marker `C:\WSHLAB.TXT`; `--keyboard no` adds `KEYB NO`. The [DOS
guide](/guides/dos/) has the VM settings and what DOS gets of the first megabyte.

`wsh-lab targets` also lists catalogue entries that don't install yet, each with what blocks it.
`nextstep33-ss5` and `openstep42-ss5` (NeXTSTEP 3.3 and OPENSTEP 4.2 on an SS-5 with `ss5.bin` and the
TCX) wait for a `pve-qemu-kvm` with a fix to the ESP's interrupt timing: with the published package
their installers hang on the disk (see the [SPARC guide](/guides/sparc/#nextstep-33-and-openstep-42)).

An SS-5 install doesn't boot on SS-10/SS-20 (the device paths differ), so each machine has its own
target. Solaris 8 and 9 install on both: the SS-5 targets use the later updates (8 2/02, 9 9/05),
whose Web Start the install answers too; the SS-5 takes about as long as the SS-20 with 256 MB.
Solaris 9 is the last release for sun4m (Solaris 10 dropped it); its installer and installed 32-bit
kernel run on the emulated SS-5 and SS-20. During the Solaris 8 and 9 installs the VM has
`args: -prom-env auto-boot?=false` (Web Start reboots with a boot string that OpenBIOS ignores, so
the install stops at the firmware prompt and boots the right slice itself); the install removes it
again, the finished VM has no `args`.

All Solaris targets end with the host name of the target (`sol26-ss5`, `sol8-ss20`, ...), `le0` at 10.0.2.15/24
(static; no name service, no default route) unless the network options say otherwise (see
"Network": static or DHCP, VLAN, netmask, router, DNS), the time zone MET, and a marker file `/etc/wsh-lab-target` with the target, the install time and the media's
checksums. The Solaris 7, 8 and 9 targets take a static address only for now (`--ip dhcp` was
tested with 2.6, not with them, so `lab.py install` refuses it).

`sol10-sun4u` runs Solaris 10's text installer on the serial console with a static address on
`hme0` (host name `sol10-sun4u`, no DHCP: `--ip dhcp` is refused), the time zone the installer
lists first (Africa/Algiers), auto-layout (`/` 6.6 GB, swap 1 GB, the rest `/export/home`) and the
root password from `--root-password`. Its reboot at the end doesn't come back (`prom_reboot: reboot
call returned!`: OpenBIOS has no reboot for Solaris yet), so the tool stops the VM there, ejects the
DVD and boots the disk. Don't use `reboot` or `init 6` in the guest either; stop and start the VM.
Once in six DVD boots the kernel panicked before the installer's first question (a trap in the
firmware); the tool then runs the install once more, since nothing is on the disk yet.
With pve-qemu-kvm before `wsh/0034` every sun4u guest has the MAC address 52:54:00:12:34:56
whatever `net0` says, so two of them on one network clash; with it the guest uses `net0`'s address
(the [sparc guide](/guides/sparc/#solaris-10)).

`tribblix-m34-sun4u` boots Tribblix's live CD (it imports its service descriptions on every boot,
so its login prompt takes 45-70 minutes), answers the keyboard question with US-English, logs in
as root and runs the CD's own installer (`live_install.sh -G`: a ZFS root pool on the whole disk)
with the network down, so the result doesn't depend on the internet (with a network the installer
fetches some packages from pkgs.tribblix.org; without one it skips those few, see the sparc lab's
README). The first boot sets root's password, writes the marker, sets a static address with `ipadm`,
the default route, DNS and the optional user, and locks the live CD's `jack` account that the
installer copies along. The pool shows DEGRADED after the install: the fault manager counts the I/Os
that ZFS had to retry on the emulated IDE disk (no data errors); the first boot runs `zpool clear
rpool` (whether the mark stays away wasn't checked yet). Most of the time goes to the SMF import:
through PVE the install took 141 minutes (the live CD's login after 61), the first boot 89 (its
login after 70: it imports the 99 service descriptions again) and `--check` 26. Only that first
boot from the disk imports them: later boots come to `console login:` in 12-14 minutes (two
measured, 736 and 817 s), and `init 5` takes another 6-11. Before pve-qemu `wsh/0036` the guest's
clock stopped in about one of three long runs (a race in QEMU, see the sparc guide). Like Solaris
10, don't `reboot` it: stop and start the VM.

**SunOS 4.1.4** (`sunos414-ss5`) copies the CD's miniroot to the swap slice, reboots into it and
runs `suninstall`'s Quick install (Programmer: everything but the full set; `/` 95 MB, swap 190 MB,
`/usr` 1 GB, the rest of the disk unused, since SunOS 4 file systems stop at 2 GB). The first boot
answers sys-config: the host name (`sunos414`), time zone GMT, the static address, no NIS, the root
password and the optional user. It differs from the Solaris targets in a few ways:

- The CD's install kernel stops QEMU with 256 MB (`qemu: fatal: Trap 0x29 (Data Access Error)` in the
  node's journal, and the VM is off), so the VM has 64 MB during the install and the target's 256 MB
  afterwards. Like Solaris 8 and 9 it has `args: -prom-env auto-boot?=false` during the install
  only: OpenBIOS drops the boot string of the miniroot's reboot, so the install boots it by path.
- Network: a static address only (SunOS 4.1.4 has no DHCP client), with `--netmask` and
  `--gateway`. `--dns` and `--domain` are refused: its C library resolves host names through
  `/etc/hosts` or NIS, not DNS. The address goes into `/etc/hostname.le0` and `/etc/hosts`
  (sys-config), the netmask into `/etc/netmasks`, the router into `/etc/defaultrouter`.
- `--user NAME` is made by sys-config: uid 1001, group `staff`, `csh`, home `/home/<host>/NAME`.
- Root's shell is `csh`; the console is the serial port (`qm terminal`).
- The disk has one size, so there is no `--disk-size`, and no `--data-disk`.

The NetBSD targets are installed by sysinst on the serial console (the sparc CD first runs a
small "microroot" that loads the installer from the CD), on a blank disk (sysinst writes its own
label). The first boot sets root's password, writes the marker `/etc/wsh-lab-target` and
`/etc/myname`, and sets up the network in NetBSD's own files: `/etc/ifconfig.hme0` (sparc64) or
`/etc/ifconfig.le0` (sparc) and `defaultroute=` in `/etc/rc.conf` for a static address,
`dhcpcd=YES` for DHCP (the host name stays the target's), `/etc/resolv.conf` for `--dns`. sshd is
off and nothing listens on the network (sysinst's defaults). Two things to know about sparc64: with
pve-qemu-kvm before `wsh/0034` every sparc64 VM has the same system MAC address (52:54:00:12:34:56,
whatever `net0` says), so put only one of them on a network segment (with it, `net0`'s address);
and NetBSD/sparc64 keeps a host core at 100% for as long as it
runs (no idle on sun4u). If a `halt -p` during the install never powers the VM off (seen once on
sparc64), the tool breaks into NetBSD's kernel debugger after 5 minutes, records its state in the
evidence and powers off from there.

**Red Hat Linux 6.2** (`redhat62-ss5`, `redhat62-ss20`) installs unattended with kickstart, the
installer's own answer file: the tool writes a small CD with `ks.cfg` (made from your network
options, nothing secret on it) to the media storage as `wsh-lab-answers-<vmid>.iso`, puts it into
`scsi5` for the install, and removes the drive and the file afterwards, whether the install passed
or not. Only SILO's three screens, which 6.2's kickstart doesn't answer on SPARC, are typed on the
serial console. The disk gets `/boot` (32 MB) first, then `/` and 128 MB swap: SILO's first stage
can't load its second stage from far into the disk on these machines. The installed system has the
Base package group plus `ping`, the time zone MET, the console on the serial port (`ttyS0`) and
`eth0` with a static address (`--ip`, `--netmask`, `--gateway`, `--dns`, `--domain`; `--ip dhcp` is
refused, not tested yet); the first boot sets root's password, the host name
(`/etc/sysconfig/network`, `/etc/hosts`), the router and DNS, writes the marker
`/etc/wsh-lab-target` and adds the optional `--user` (home under `/home`). The only network
service is sendmail on port 25 (on every address; Base has no inetd), as the installer sets it up;
it is a 2000-era system with its known holes, so keep it off untrusted networks
(`chkconfig sendmail off` turns sendmail off). `poweroff` in the guest powers the VM off.

**Debian GNU/Linux 4.0 "etch"** (`debian40-ss5`, `debian40-ss20`), the last Debian release for
these machines, installs unattended from the netinst CD with a preseed file, debian-installer's own
answer file. The tool writes a small CD with the preseed file and a loader script (made from your
options, nothing secret on it) as `wsh-lab-answers-<vmid>.iso`, puts it into `scsi5` for the
install and removes it afterwards; the only thing typed is one boot line at SILO's prompt, which
makes the installer read that CD before its first question. The installer then fetches the base
system and the kernel from `archive.debian.org`, so the guest needs a way out: give `--gateway` and
`--dns` that reach the internet (they are required; the address defaults to 10.0.2.15/24 as for the
other targets), or `--apt-proxy URL` for an HTTP proxy such as an apt-cacher-ng
(`--apt-proxy http://aptcache.example:3142`, or the `WSH_LAB_APT_PROXY` environment variable; the
installed system's apt keeps using it, from `/etc/apt/apt.conf`). etch's archive signing keys
expired years ago, so the install runs with debian-installer's `allow_unauthenticated` (the
packages come from the archive without a signature check; the installed system's `apt-get` then
works as usual). The disk (blank,
3 GiB) gets `/boot` (64 MB) first, then `/` and swap; the system is the base system with the console
on `ttyS0`, `eth0` with the static address, the time zone UTC, no security updates (etch's are
gone). The first boot sets root's password, writes the marker and adds the optional `--user` (home
under `/home`). These targets need `pve-qemu-kvm` 11.1.3-2+wsh20 or later, which has the ESP fix
`wsh/0038` (Linux 2.6.18's SCSI driver takes the disk offline without it).

**Solaris 2.4 and 2.5.1** (`sol24-ss5`, `sol24-ss20`, `sol251-ss5`) boot their installer only
from a CD that answers as a disk: the CD-ROM drive has `cd_as_disk=1` (`scsi6:
local:iso/<cd>.iso,media=cdrom,cd_as_disk=1`; needs qemu-server with that option). 2.5.1's VM has
the SPARCstation 5 PROM (`bios: ss5.bin`, part of the package's optional Sun PROM extra); 2.4 runs
under OpenBIOS with the OpenBIOS patches 0019-0022 (`pve-qemu-kvm` 11.1.3-2+wsh22 or later; before,
only under a Sun PROM, and the 2.4 target had `ss5.bin`). The
CD also shows up in the installer's disk list as `c0t6d0`; the install selects only `c0t3d0`. After
the install the CD is ejected as for every target (`none`, an empty CD-ROM drive). Both take a
static address only (no DHCP client before 2.6). 2.4 shows a year after 1999 as 19xx in its date
screen and refuses it; the install types the 4-digit year there. 2.4's auto-layout makes small
slices (`/` 25 MB, `/usr` 108 MB, swap 130 MB, the rest of the disk `/export/home`), and it has no
`hostname` command. 2.5.1's install ends with its Maintenance Update, which takes most of its time.

**Solaris 2.2, 2.3 and 2.5** need the same CD-as-disk drive. 2.3 Edition II (`sol23-ss5`,
`sol23-ss20`, the first release for the SS-5; the SS-20 needs 2.3 or later) runs under OpenBIOS
with the patches 0019-0022, like 2.4 (`pve-qemu-kvm` 11.1.3-2+wsh22 or later; with an older package
OpenBIOS stops right after the boot block, `Unhandled Exception 0x00000009`; until then the 2.3 and
2.4 targets had the Sun PROMs `ss5.bin` and `ss20_v2.25_rom`, and a VM of your own with them still
installs those releases).
Its installer asks one question per screen and installs with Quick Install (End User; `/` 17 MB,
swap 512 MB, `/opt` 9 MB, `/usr` 120 MB, the rest `/export/home`), then reboots by itself. Its
first boot asks for the root password on its own screen, and the first login may insist on a new
password: the install types the same one. 2.3 shows the year as 19xx like 2.4 (typed over), keeps
its clock in 1970 after a reboot, and its `init 5` reboots instead of powering off (OpenBIOS
starts again and boots the disk; stop the VM after `rebooting...`). **Solaris 2.2** (`sol22-ss10`)
runs only on the SS-10 of QEMU's machines (its only supported sun4m machine; under the SS-20 PROM
its kernel panics) and installs exactly like 2.3 (the same one-question screens and Quick Install).
Its CD image is `Solaris_2.2.img`, a plain 2048-byte-sector image with an `.img` name, which PVE's
ISO storage accepts as it is. 2.5 (HW 1/96; `sol25-ss5`, `sol25-ss20`) boots under OpenBIOS on both
machines and installs like 2.6, without 2.5.1's Maintenance Update. Static address only for all of
them.

**More CPUs on the SS-20 for 2.3 and 2.4.** The targets install with one CPU. Afterwards the VM
can have 2 or 4 (`qm set <vmid> --cores 4`; the SS-20 profile with OpenBIOS allows up to 4): 2.3 and
2.4 boot with every CPU on-line (`psrinfo`), share a parallel load across all of them, and stayed up
through 10 minutes of CPU and disk load on 4 CPUs (lab runs through PVE, 2026-11-19). Idle CPUs
don't keep the host busy (4 CPUs at the login prompt: 5% of a host core). Not on the SS-5 (one CPU)
and not with a Sun PROM (`ss20_v2.25_rom` starts one CPU only).

**OpenBSD 8.0** (`openbsd80-sun4u`) boots the install CD's `bsd.rd` and answers the installer's
questions on the serial console by what they ask, not by their order: the host name, `hme0` with the
static address (`--ip`, `--netmask`; no IPv6), root's password, sshd on (root logins over ssh off),
no user, the auto layout on `wd0` (`/` 1 GB, swap 256 MB, `/usr` 3 GB, `/home` 2 GB), the sets
from the CD without X11, the time zone UTC. Before the first boot the install turns **ntpd off**
(`ntpd_flags=NO` in `/etc/rc.conf.local`, what `rcctl disable ntpd` writes): with a network that
reaches NTP servers, the disk timed out (`wd0: timeout`) in 5 of 6 boots after ntpd started slewing
the clock (see the [sparc guide](/guides/sparc/#sparc64-sun4u)); turn it on again only if you want to
try that out. The disk can also time out without ntpd: through PVE once in five installs the CD
stopped answering while the sets were extracted (the tool notices 5 minutes of silence after the
`cd0: timeout` messages and runs the install once more), and one of several heavy disk boots hung
after `wd0: timeout` (stop and start the VM). The cause is being looked into (QEMU's sun4u interrupt
path, see the roadmap). The first boot writes the marker, `/etc/myname`, the network files
(`/etc/hostname.hme0`, `/etc/mygate` for `--gateway`, `/etc/resolv.conf` for `--dns`/`--domain`, the
address in `/etc/hosts`) and the optional `--user` (group `wheel`, `ksh`, home under `/home`), and
powers off with `halt -p`. Static address only (`--ip dhcp` is refused: not tested through the tool;
the lab's own runs got a DHCP address with `inet autoconf` in `/etc/hostname.hme0`). The first boot
takes about 5 minutes (key generation, the library relink); every boot relinks the kernel in the
background, and a `halt -p` before that ends says `reorder_kernel: failed` (harmless: the old
kernel stays). It needs `pve-qemu-kvm` 11.1.3-2+wsh22 or later: with older OpenBIOS the installed
kernel stops right after the loader (`Unhandled Exception 0x30`). Like the other sun4u targets, it
keeps a host core busy while it runs.

**OpenBSD 5.9** (`openbsd59-ss5`, `openbsd59-ss20`) boots `cd59.iso`'s installer and answers it the
same way as 8.0 (5.9 words some questions differently): `le0` with the static address, root's
password, sshd on (root logins over ssh off), no user, the auto layout on `sd0` (on 8 GiB: `/` 111
MB, swap 480 MB, `/tmp`, `/var`, `/usr` 932 MB, `/usr/X11R6`, `/usr/local` 2.1 GB, `/usr/src`,
`/usr/obj`, `/home` 1.3 GB), the sets from the sets CD (`cd0`) with the installer's check of
`SHA256.sig` (the install fails without "Signature Verified"), time zone UTC, ntpd off before the
first boot (as for 8.0). The first boot (about 5 minutes: it generates the host keys) writes the
marker, `/etc/myname`, `/etc/hostname.le0`, `/etc/mygate`, `/etc/resolv.conf`, the address in
`/etc/hosts` and the optional `--user`, and powers off with `halt -p`. Static address only. The VM
keeps `vga: serial0`: with `cg3` or `tcx` QEMU adds the Sun keyboard, and OpenBSD 5.9's kernel
panics while it configures the devices ("crazy interrupts"). More CPUs on the SS-20 boot but stay
unused.

**SunOS 4.1.3_U1B** (`sunos413u1b-ss5`, `sunos413u1b-ss20`; Solaris 1.1.1B, the first SunOS 4 for
the SS-5 and SS-20) installs exactly like 4.1.4: the same miniroot, `suninstall` and sys-config
screens, the same disk layout, network options and refusals, 64 MB during the install. Its CD is a
plain image (no conversion). Sun lists the kernel patch 101508 for the SS-5's microSPARC-II; the CD's
kernel and the installed one run without it on QEMU's SS-5. Host name `sunos413`.

## Media

The media must be on the node's storage (`local` by default, content type ISO image) under these
names, and they must be the tested media: `lab.py install` checks the size and the sha256 and refuses
anything else unless `--allow-untested-media`. Nothing is downloaded by the install; Sun and Oracle
software is never part of this project.

| File name | Size (bytes) | sha256 |
| --- | --- | --- |
| `Solaris2.3Edition-II.iso` | 426979328 | `e1c85daa46da28704bf21cb0e5bb71471c78516da6550a8230ed89a1f61d1d8f` |
| `Solaris_2.2.img` | 388608000 | `276af9322e3f311b8bd8e4a567feb47ccc771cf9fd98a02aac61db749cbdafd8` |
| `solaris2.5_sparc.iso` | 378101760 | `33f7b716af2354725c510b54e9e5f1bf7962352302137604e7c3570941b22259` |
| `sunos_4.1.3U1B.iso` | 335851520 | `37bbb203e0e4267bb0977aa9237e777bdda840b03cb5a6044cf777bfe8ebb202` |
| `solaris_2.4_sparc.iso` | 455819264 | `c23fe150a9963e5dacbfc988fa700c5f2c7506d36ad0b40910e77444709d1fa4` |
| `solaris_2.5.1_1197.iso` | 452157440 | `18da51043271d0aa69d6fc098b84156673ef4f0728dace4a9e679f79d70d2422` |
| `solaris_2.6_598_sparc.iso` | 565862400 | `17351669cb91a89562ed6bb23345879c4d18bd019a85085ad53f777e7b7a6b14` |
| `Sol7.399InstallationSparc.iso` | 588800000 | `3fe59c14307b924d40033f0f3a362c4384b4738a5a365a2f319d96883610c35d` |
| `sun-solaris-8-0101-installation-sparc.iso` | 584232960 | `d01915baa0503ad21fd9b99e0684e1231200ca3295e84f60a1bf310a956d51d4` |
| `sun-solaris-8-0101-software-cd1-sparc.iso` | 578023424 | `d50e437d82c96a906833fca182f813035d766b1645491eb06b221826ef9f39c8` |
| `sun-solaris-8-0101-software-cd2-sparc.iso` | 214757376 | `1b6fafd007673f924dc40103b3d2c565342b287d6ff8ad53ac07e1b4b73b44d4` |
| `SOL_9_SPARC_DVD.iso` | 3368878080 | `feb49d1fa21227a1493b5b4a083b2ca12e60577ccd84e4a22b5d3b86fd209911` |
| `sol-10-u11-ga-sparc-dvd.iso` | 2314731520 | `b1df86b976282145fd317d9def4efc27d7d64589f5542184a3e781c0787cf02b` |
| `sunos414-cd.iso` (made from the BIN below) | 329297920 | `7b9b092a63bf5dde9f09eea25614c6da58e5c065758a8c24b96be1574bcaa0c8` |
| `NetBSD-11.1-sparc64.iso` | 694026240 | `a782b26be57325c8419fdb02030ea4e686a6ccf097baad2dae0a1a0c39e96f4e` |
| `NetBSD-11.1-sparc.iso` | 367329280 | `4a8985ecf7d21dad66c34c184d1535a9f901ee4ccc4d962c37558545b63b4636` |
| `redhat-6.2-sparc.iso` | 623771648 | `74bdc6de56d3120f05372232cd4dae313d015e62be4b359672d9f8edca300987` |
| `debian-40r9-sparc-netinst.iso` | 146124800 | `91aeb8639d53252215c99b69fa07ef1ae0e2bafec1c3c77fdfb9094327dd3afd` |
| `install80.iso` (OpenBSD 8.0 sparc64) | 467599360 | `b8a80e5a10424ef32863d28dac7ae343666adfcfe0bbdfb4fc0230c130a560cb` |
| `cd59.iso` (OpenBSD 5.9 sparc) | 4048896 | `34fb9b618b8d36bd7425e4505f1604f1bd23e1795b41bb19dc2cb9958fccc330` |
| `openbsd59-sparc-sets.iso` (made from the 5.9 release's files, below) | 116387840 | `d1bd7d02404299396b57c3ed39e4c1fc928d9c1743e6702e10c11dcd05d8c6af` |

The NetBSD CDs are freely redistributable: download them from
`https://cdn.netbsd.org/pub/NetBSD/NetBSD-11.1/images/` (the release's `SHA512` file has their
SHA512 checksums). The Debian 4.0 netinst CD is freely redistributable too:
`https://cdimage.debian.org/mirror/cdimage/archive/4.0_r9/sparc/iso-cd/debian-40r9-sparc-netinst.iso`.
So is OpenBSD's: `https://cdn.openbsd.org/pub/OpenBSD/8.0/sparc64/install80.iso` (its sha256 is in
the release's `SHA256` file there); 5.9 is on the official EU mirror, which keeps the old releases:
`https://ftp.eu.openbsd.org/pub/OpenBSD/5.9/sparc/` (`cd59.iso` and the files for the sets CD).
Upload a medium through the storage's **ISO
Images** tab, or copy it to `/var/lib/vz/template/iso/` on a directory storage.

**The SunOS 4.1.4 CD** circulates as a raw CD image (a "BIN": 2352-byte sectors, each with a 16-byte
sync and header before its 2048 bytes of data), here named `sunos_4.1.4_install.iso` (378178080
bytes, sha256 `6088d836cf582128cdd69661c4b62399fbd6f4db9b817188b2d1509cebbb5f48`). QEMU reads it
as data from byte 0, so it has to be cut to its 2048-byte data first. The tool does that and checks
both files:

```sh
wsh-lab media sunos414-ss5 --convert /path/to/sunos_4.1.4_install.iso   # into local:iso/sunos414-cd.iso
wsh-lab media sunos414-ss5 --convert /path/to/sunos_4.1.4_install.iso --storage nas-iso
```

It refuses a source of another size or checksum and writes `sunos414-cd.iso` only when the result
has the checksum in the table above. The same by hand, from the BIN, is
`python3 -c 'import sys; f=open(sys.argv[1],"rb"); o=open(sys.argv[2],"wb"); [o.write(s[16:2064]) for s in iter(lambda: f.read(2352), b"")]' sunos_4.1.4_install.iso sunos414-cd.iso`,
then `sha256sum sunos414-cd.iso`.

**The OpenBSD 5.9 sets CD.** OpenBSD/sparc 5.9 has no install CD with the sets, only `cd59.iso`,
which boots the installer. The targets give it the sets on a second CD that the tool makes on the
node from the release's files: put `bsd`, `bsd.rd`, `base59.tgz`, `comp59.tgz`, `man59.tgz`,
`game59.tgz`, `SHA256.sig` and `INSTALL.sparc` (from `https://ftp.eu.openbsd.org/pub/OpenBSD/5.9/sparc/`)
in one directory, then

```sh
wsh-lab media openbsd59-ss5 --convert /path/to/openbsd5.9   # into local:iso/openbsd59-sparc-sets.iso
```

It checks each file's size and sha256 (those in the release's signed `SHA256`) and writes
`openbsd59-sparc-sets.iso` only when the result has the checksum in the table above (the image is
the same on every node: no dates, sorted names). The same CD serves `openbsd59-ss20`. The installer
checks the sets again itself, against `SHA256.sig` with the release's key.

The DOS targets' floppy images go on a storage with the **Floppy image** content type (no storage
has it until it is enabled: `pvesm set local --content iso,vztmpl,backup,floppy`, the whole list),
through its **Floppy Images** tab or into `template/floppy/`. `lab.py media` says when the storage
lacks the content type. The install attaches them read only. Microsoft's floppies are never part of
this project; FreeDOS is freely redistributable (`FD14-FloppyEdition.zip`, the `144m/` images).

| File name | Size (bytes) | sha256 |
| --- | --- | --- |
| `msdos622-disk1.img` | 1474560 | `b88030401122d234ea6aafba3cfed7de2b7b1782700a67be5498edca6f9fec5d` |
| `msdos622-disk2.img` | 1474560 | `e1d48a415495a17d65316d5328a91d7df0910fb1e42b0b07e7dbf8a4b4df305a` |
| `msdos622-disk3.img` | 1474560 | `52a3b4e7f5973c38f2517dbb20426bf5c8bd62f202e84a85d3d7283401d5e63c` |
| `msdos622-supp.img` (Supplemental Disk, not used by the install) | 1474560 | `774ea0611b5602133f7719339294eb6936d1256bb534733ecdd9c9de47e57090` |

The FreeDOS images (`freedos14-boot.img` = `x86BOOT.img`, `freedos14-diskN.img` = `x86DSK0N.img`)
and their checksums are in `e2e/sparc/targets_dos.py`.

Check what a node has:

```sh
wsh-lab media                 # every target's media on storage local, with sha256
wsh-lab media sol26-ss5 --storage nas-iso
wsh-lab media --dir /path/to/isos --no-checksum
```

## Install the lab on a node

The lab runs as root on the node, where `qm`, `pvesh` and the VMs' sockets are. On a node that has
the [wsh-pve repository](/guides/setup/):

```sh
apt install wsh-lab
wsh-lab --version
```

`wsh-lab` is an optional package (`Architecture: all`): nothing else depends on it, it depends on
none of the patched packages (it works with whatever `qemu-server` is installed, which is where the
sparc profiles come from), and it pulls in only Debian's `python3-pyte`, `python3-pil` and
`fonts-dejavu-core`. It puts the lab in `/usr/share/wsh-lab/` and two commands in `/usr/bin`:
`wsh-lab` (`lab.py`: `install`, `targets`, `media`, `run`, `serve`, ...) and `wsh-lab-mcp` (the
lab's [MCP server](https://github.com/hwinther/wsh-pve/tree/main/e2e/sparc#mcp-server)). Suggested,
not installed by default: `tesseract-ocr` (only for targets driven on a framebuffer; none yet),
`vpx-tools` (the framebuffer video in the evidence) and `python3-venv` (for `wsh-lab-mcp --setup`).
`apt purge wsh-lab` removes everything it installed, including the MCP server's venv; the evidence
of your installs in `/var/lib/wsh-lab/installs/` stays.

The package's version is `0.<N>+g<commit>`: `N` counts the commits that changed the lab, so a
newer lab always has a higher version, and the commit is the newest of them. It is built by the
`wsh-lab package` workflow from the repository at that commit and published with the other
packages.

**Without the package**, from a clone of the repository: either Debian's packages and the files
as they are,

```sh
apt install python3-pyte python3-pil fonts-dejavu-core
alias wsh-lab='python3 /path/to/wsh-pve/e2e/sparc/lab.py'
```

or, without new system packages, a venv made by [uv](https://docs.astral.sh/uv/) with the pinned,
hash-checked dependencies:

```sh
uv venv /opt/wsh-lab --python /usr/bin/python3
uv pip install --python /opt/wsh-lab/bin/python --require-hashes -r e2e/sparc/lab-requirements.txt
install -d /opt/wsh-lab/lab/scenarios
install -m 644 e2e/sparc/{lab,recording,install,targets,targets_dos,vgatext,sunlabel,answer_media}.py /opt/wsh-lab/lab/
install -m 644 e2e/sparc/scenarios/*.py /opt/wsh-lab/lab/scenarios/
alias wsh-lab='/opt/wsh-lab/bin/python /opt/wsh-lab/lab/lab.py'
```

Removing that is `rm -r /opt/wsh-lab`.

## Run it

```sh
wsh-lab targets                                 # the catalogue
wsh-lab install sol26-ss5 --vmid 120 --check    # ~12 min
```

Options: `--storage` (the VM's disk, `local`), `--media-storage` (`local`), `--bridge` (`vmbr0`),
`--vlan`, `--ip` (an address or `dhcp`), `--netmask`, `--gateway`, `--dns`, `--domain` (see "Network"),
`--name`, `--hostname`, `--disk-size` (`3G`, the default, or `9G`: see "Disk size"), `--data-disk GIB`
(a second disk, mounted on `/data`, or `/usr/local` with `--data-mount /usr/local`; Solaris only),
`--post-install sun26gnu` and `--local-env` (Solaris 2.6 and 7: see "Packages under /usr/local"), `--root-password`, `--user NAME` (and `--user-password`; a non-root
user with its home under `/export/home`; SunOS 4.1.4: `/home/<host>`; NetBSD, Red Hat and Debian: `/home`), `--apt-proxy URL` (Debian 4.0: an HTTP proxy for the packages the installer fetches; also
`WSH_LAB_APT_PROXY`), `--check` (boot once more, log in with the documented
password and check the marker), `--template` (convert the finished VM to a template),
`--keep-on-failure`, `--allow-untested-media`, `--timeout` (seconds the install phase may take) and
`--out` (the evidence directory; default `/var/lib/wsh-lab/installs/<target>-<vmid>-<time>`).

What it does:

1. Checks the media (name, size, sha256) and refuses a VMID that exists anywhere in the cluster:
   it never overwrites a VM.
2. Creates the VM through the API with the target's profile, a disk with a Sun label (the Solaris
   2.6 installer lists only labelled disks; the label is written by the tool, no template needed;
   Solaris 10 labels a blank disk itself) and the CD in its drive, tagged `wsh-lab`.
3. Starts it and answers the installer on the serial console (the lab's scenario for that release;
   Red Hat 6.2 and Debian 4.0 read most answers from the kickstart or preseed CD the tool adds for this step only).
   The install ends with `halt`, which powers the VM off (Solaris 10: the tool stops the VM when the
   installer's reboot doesn't come back; Red Hat: when the install reboots).
4. Ejects the CD (the drive stays, empty) and sets the boot order to the disk.
5. Boots the installed system once: answers the first-boot questions with the root password, writes
   `/etc/wsh-lab-target`, adds the optional user, shuts down with `init 5`.
6. With `--post-install`, boots once more with the package CD in a drive of its own, adds the
   packages to the data disk (and with `--local-env` sets up `PATH` and the user's shell), shuts
   down and removes the drive (see "Packages under /usr/local").
7. With `--check`, boots again, logs in as root with the password and checks the marker.
8. Writes the login, console, host name, network, marker and media into the VM's notes
   (description), optionally converts it to a template, and prints a summary.

While it runs the tool owns the VM's serial console: close `qm terminal` and the web console's
xterm.js first, they would get nothing. Measured in the PVE test container on the lab host
(TCG, two host cores for the container, one guest at a time, packages of 2026-11-16): `sol26-ss5`
took 11.8 minutes (install 407 s, first boot 182 s, check 105 s), `sol26-ss20` 12.1 minutes (413 s,
191 s, 105 s). Without `--check` it is two minutes less. `sol10-sun4u` (packages of 2026-11-17,
`pve-qemu-kvm` 11.1.3-2+wsh13): 108.5, 109.6 and 110.7 minutes in three runs that passed (install about 81 minutes, first boot about 19, check about 9; the first boot imports Solaris's service descriptions, and `init 5` takes 3 to 6 minutes).

### Keep the installed disk, boot it again later

A slow install only has to run once. With `--export DIR` (together with `--check`), the installed
VM's first disk is copied to `DIR/install-<target>.raw` when the check passes, with
`install-<target>.json` beside it (install date, minutes, package versions, profile, network, media
checksums). The previous copy is replaced only when the new one is complete. `boot-test` then makes
a new VM with the target's profile from a copy of that disk, boots it, logs in and checks the marker
(the same check as `--check`), and destroys the VM:

```sh
wsh-lab install tribblix-m34-sun4u --vmid 130 --check --export /mnt/os/disks   # ~4.3 h, once
wsh-lab boot-test tribblix-m34-sun4u --disk /mnt/os/disks/install-tribblix-m34-sun4u.raw --vmid 131
```

`--export` stores only the target's default install (it refuses `--root-password`, `--user`,
`--data-disk`, `--post-install` and `--template`) and never replaces a file it didn't write itself.
`boot-test` takes `--storage`, `--bridge`, `--name`, `--out` and `--keep` (keep the VM, stopped).

## Disk size

The first disk comes in the sizes a target was tested with; `wsh-lab targets` lists them, and any
other `--disk-size` is refused with the tested ones named. Both are the lab's disk templates byte for
byte (the label and its backup copies), written by the tool, so no template is needed:

| `--disk-size` | Image | Label (as `format` names it) | Template |
| --- | --- | --- | --- |
| `3G` (default) | 3 GiB | `SUN2.9G cyl 2734 alt 2 hd 21 sec 99` (2775 MB usable) | `sparc-SUN2.9G.raw.template.xz` |
| `9G` | 8 GiB | `QEmu8G cyl 16202 alt 2 hd 16 sec 60` (7594 MB usable) | `sparc-Qemu9G.raw.template.xz` |

Solaris 2.6's installer asks the same questions on both; its auto-layout puts `/` first (slice 0
from cylinder 0, where OpenBIOS boots it), then swap, `/usr`, and gives the rest to `/export/home`.
On a 9G disk (`sol26-ss5`, measured):

| Slice | Mount | Size | Used after the install |
| --- | --- | --- | --- |
| 0 | `/` | 80 MB | 22 MB |
| 1 | swap | 148 MB | |
| 6 | `/usr` | 233 MB | 153 MB (57 MB free) |
| 7 | `/export/home` | 7175 MB | 7103 MB free |

On `sol26-ss20` (512 MB of memory) swap is 295 MB and `/export/home` 6973 MB. Solaris 7
(`sol7-ss5`, `sol7-ss20`, measured) lays out the 9G disk the same way: `/` 86 MB (24 MB used),
`/usr` 288 MB (187 MB used, 72 MB free), swap 148 MB on SS-5 and 295 MB on SS-20, `/export/home`
7112 MB on SS-5 and 6963 MB on SS-20; the install takes about a minute longer than on the 3G disk.
3G stays the default for Solaris 2.6 and 7 (End User fits it); Solaris 8 and 9 have only the 9G
disk. `/` and `/usr` are as small as on the 3G disk (auto-layout sizes them for the software, End User
System Support), so the extra space is all in `/export/home`. Software that installs under `/opt`
or `/usr` needs a layout of its own (the installer's Customize) or a link into `/export/home`
(for example `/usr/local` as a link to `/export/home/local`), or a `--data-disk` mounted there.

### A second disk

`--data-disk GIB` (1-32) adds a second disk on `scsi4` (`c0t4d0` in Solaris) after the install,
with a Sun label whose slice 0 is the whole disk; the first boot makes its device nodes, puts a UFS
on it and mounts it on `/data` from `/etc/vfstab`. The same by hand for a VM that exists (powered
off), as root on the node and then in the guest:

```sh
python3 /usr/share/wsh-lab/sunlabel.py data 4 /var/tmp/data.raw   # 4 GiB, labelled (no format needed)
qm set 120 --scsi4 local:0,import-from=/var/tmp/data.raw,format=raw && rm /var/tmp/data.raw
qm start 120
# in the guest:
drvconfig; disks                     # device nodes for the new target
newfs /dev/rdsk/c0t4d0s0             # answer y
mkdir /data
echo '/dev/dsk/c0t4d0s0 /dev/rdsk/c0t4d0s0 /data ufs 2 yes -' >> /etc/vfstab
mount /data
```

A blank disk (`qm set 120 --scsi4 local:4`) instead needs a label from `format` in the guest
(`format c0t4d0`, then `type`, `Other` and the geometry, then `label`), since 2.6 can't work out an
emulated disk's geometry by itself; the labelled image avoids that. `python3
/usr/share/wsh-lab/sunlabel.py disk 9G <image>` writes the install targets' 9G disk the same way.

`--data-mount /usr/local` mounts the data disk on `/usr/local` instead (whatever was in `/usr/local`
is copied onto it first). `/data` stays the default; `--post-install` below picks `/usr/local` by
itself.

### Packages under /usr/local

On Solaris 2.6 and 7 (`sol26-ss5`, `sol26-ss20`, `sol7-ss5`, `sol7-ss20`), `--post-install sun26gnu` adds the SVR4 packages from the
owner's own CD image of free software for Solaris 2.6 (bash 4.1, coreutils, vim 7.3, wget, curl,
less, screen, sudo, rsync and the libraries they need: 34 packages, all under `/usr/local`) after the
first boot. That image, `sun26gnu.iso`, is a local medium: it is not published or downloaded, and
`wsh-lab media` doesn't list it; put it on the media storage under that name (it is checked by size
and sha256 like the install media) or leave the option out.

```sh
wsh-lab install sol26-ss20 --vmid 120 --data-disk 2 --post-install sun26gnu --local-env --user lab --check
```

- `--post-install` needs `--data-disk` (1 GiB or more), which is then mounted on `/usr/local`:
  `/usr` has about 70 MB free on the 3G and 9G layouts, too little for the packages (164 MB
  installed). The CD goes into a drive of its own (`scsi5`) for one more boot and is removed again,
  also when that boot fails. Every package is added with `pkgadd -n` and an admin file, so nothing
  asks; the console shows one line per package, pkgadd's output is in `/var/sadm/wsh-lab-sun26gnu.log`
  in the guest, and one package that fails fails the install.
- `--local-env` (only with `--post-install`) puts `/usr/local/bin` and `/usr/local/sbin` at the end
  of `PATH` (and `/usr/local/man` in `MANPATH`) in `/etc/profile` and the `--user` account's
  `.profile`, and makes bash that account's login shell. Root keeps `/sbin/sh`: in single-user mode
  only the root file system is mounted, and root must still be able to log in when the data disk
  isn't there.
- With `--check`, the check boot also checks that `/usr/local` is the data disk, `bash --version`,
  `vim --version` and `wget --version`, that `pkginfo` lists every package, and with `--local-env`
  the user's login shell and `which bash`.

Measured (2026-11-18, the PVE test container, other installs running at the same time): the
post-install boot took 6 to 7.5 minutes, 4 to 5 of them adding the packages; with `--check` the whole
`sol26-ss20` install took 24.6 minutes, `sol26-ss5` 23.8, `sol7-ss20` 23.2 and `sol7-ss5` 21.7. `/usr/local` then
holds 164 MB (`df -k`: 168050 KB used).

## Network

The VM's NIC goes on `--bridge` (`vmbr0`), with `--vlan TAG` as the `tag=` of `net0`. In the
guest, a target supports the modes its catalogue entry lists as tested (`wsh-lab targets --json`,
`net_modes`); anything else is refused before a VM is made:

- **Static** (default): `--ip` (`10.0.2.15`), `--netmask` (`255.255.255.0`), `--gateway` (none: no
  default route), `--dns` (up to three name servers; none: `/etc/hosts` only) and `--domain`.
- **DHCP**: `--ip dhcp`. Address, netmask, default router, name servers, domain and host name come
  from the DHCP server. `--dns`/`--domain` are used only if the server sends no name servers.

Solaris 10 (`sol10-sun4u`) supports the static mode only: its installer gets the host name, the
address and the netmask (and no default route); the first boot writes `/etc/defaultrouter` and,
with `--dns`, `/etc/resolv.conf` and `hosts: files dns`. DHCP isn't offered yet because it wasn't
tested through the tool (the lab's own runs used it).

How Solaris 2.6 does it (both machines): its installer asks only for a static address and whether
the system is on a subnet, and its name service choices are NIS+, NIS, Other and None, so the
installer gets the address and the first boot writes the rest into the files 2.6's start-up
scripts read: `/etc/netmasks` (the netmask, filed under the class A/B/C network number, which is
what 2.6 looks up), `/etc/defaultrouter`, `/etc/resolv.conf` with `hosts: files dns` in
`/etc/nsswitch.conf`; for DHCP, `/etc/dhcp.le0`. The DHCP client (`/sbin/dhcpagent`, 1997) is part
of the core software, so the End User install has it; with `/etc/dhcp.le0` the start-up scripts
run `ifconfig le0 auto-dhcp primary`, take the default router from the lease, and write
`/etc/resolv.conf`, the `hosts:` line and the address in `/etc/hosts` from it.

Two things to know about Solaris 2.6 under DHCP:

- **The host name is the one the DHCP server answers with** (option 12). 2.6's client sends its
  current name (the target's host name) in its request; a server that echoes it, as dnsmasq does,
  keeps it, and a server with its own name for the VM's MAC address (in its notes and `qm config`;
  dnsmasq `dhcp-host=bc:24:11:12:34:56,myname`) renames the system. A server that sends no name
  leaves it as `unknown` (2.6's start-up script sets that: tooltalk and sendmail need a name).
- Before this change the installer's address had no netmask entry, so `le0` came up as
  `10.0.2.15 netmask ff000000` (class A), not /24 as the notes said; every install now writes
  `/etc/netmasks`.

## What it leaves

- The VM, powered off (or a template), booting from its disk, the CD drive empty, with the notes:

  ```text
  wsh-lab target: sol26-ss5 - Solaris 2.6 5/98 End User on a SPARCstation 5 (OpenBIOS)
  Installed 2026-11-16 20:30 UTC by lab.py install (wsh-pve e2e/sparc)

  Login: root / wshlab
  These passwords are public lab defaults (targets.py): change them before ...
  Console: serial0 (qm terminal 120)
  ...
  ```

- The evidence directory: `install.log`, `result.json` (phases, times, media checksums), `vm.conf`
  and one directory per phase (`install/`, `firstboot/`, `check/`), each with the serial log, a
  step-by-step `index.html` with screenshots of the console, and the console recording. Passwords
  are masked in the `result.json` files and aren't echoed on the console, so they are in no log or
  recording (except the VM's notes, on purpose).

On a failure (a missing or different medium, an existing VMID, an installer that stops answering
within the time limit) the exit code is 1, the evidence stays, and the VM is destroyed, or with
`--keep-on-failure` kept, stopped, with `FAILED ...` and the evidence path in its notes.

Start it with `qm start 120` and log in on the serial console (`qm terminal 120`) as `root` with the
password from the notes. The notes say how the network was set up ("Network" above); to change it
later, edit the same files (`/etc/hostname.le0`, `hostname.hme0` on Solaris 10, and `/etc/hosts` for the address, `/etc/netmasks`,
`/etc/defaultrouter`, `/etc/resolv.conf`, or `/etc/dhcp.le0` for DHCP) and reboot. On Red Hat 6.2:
`/etc/sysconfig/network` (host name, `GATEWAY=`),
`/etc/sysconfig/network-scripts/ifcfg-eth0`, `/etc/hosts` and `/etc/resolv.conf`. On Debian 4.0:
`/etc/network/interfaces`, `/etc/hostname`, `/etc/hosts` and `/etc/resolv.conf`.

## Licence keys

None of the current targets needs one. Later targets that do (Windows) will read keys from a local
file that is never committed, mask them in `result.json` (the lab masks every variable named
`*_KEY`, `*_PASSWORD` or `*SECRET`) and type them only where the installer doesn't echo them, so
they stay out of the logs and recordings.

## How it is tested

The sparc lab's `pve` matrix runs `lab.py install sol26-ss5 --check` every week in a PVE node in a
container with the published packages, and the `install` matrix (by hand from the `sparc lab`
workflow) goes through every automated target: a target whose stored disk is missing is installed
with `--check --export`, the others are boot-tested from their stored disks, and the workflow's
`reinstall` input installs named targets (or `all`) again. Tribblix and the Debian targets are
installed only when `reinstall` names them. Installing `sol10-sun4u` needs the Solaris 10 DVD in
the lab's media directory. `e2e/sparc/tests/test_targets.py` checks the catalogue: every
target's profile against qemu-server's profile tables, unique names, the disk label. Details:
[`e2e/sparc/README.md`](https://github.com/hwinther/wsh-pve/tree/main/e2e/sparc#install-targets).
On pull requests that change the lab, the `sparc lab NetBSD` workflow downloads the NetBSD/sparc64
CD from cdn.netbsd.org (checked against its sha256) and runs the `netbsd111-sparc64` target's
install, first boot and check with the lab's own QEMU on a GitHub-hosted runner, without PVE (about
10 minutes on the lab host).
The `wsh-lab` package is built and tested on every pull request that changes the lab: lintian, then
in a clean Debian 13 `apt install` of the package, `wsh-lab --help`, `targets`, `media --dir`, the
catalogue's tests against the installed copy, `wsh-lab-mcp --setup` and `apt purge`, which must
leave nothing behind (`packages/wsh-lab/test.sh`).
