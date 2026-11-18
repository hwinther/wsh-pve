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
| `sol24-ss5` | Solaris 2.4 HW 3/95, End User | SS-5, `ss5.bin` (Sun PROM), 256 MB, serial console, Sun-labelled 3G disk on `scsi3`, lance; the CD answers as a disk (`cd_as_disk=1`) | `solaris_2.4_sparc.iso` | `root` / `wshlab` | ~10 min |
| `sol251-ss5` | Solaris 2.5.1 11/97, End User | as `sol24-ss5` | `solaris_2.5.1_1197.iso` | `root` / `wshlab` | ~45 min |
| `sol26-ss20` | Solaris 2.6 5/98, End User | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as above | `solaris_2.6_598_sparc.iso` | `root` / `wshlab` | ~12 min |
| `sol7-ss5` | Solaris 7 3/99, End User | as `sol26-ss5`, 3G disk | `Sol7.399InstallationSparc.iso` | `root` / `wshlab` | ~11 min |
| `sol7-ss20` | Solaris 7 3/99, End User | as `sol26-ss20`, 3G disk | `Sol7.399InstallationSparc.iso` | `root` / `wshlab` | ~10 min |
| `sol8-ss20` | Solaris 8 1/01, Entire Group, installed by Web Start from three CDs (swapped by the install) | SS-20, OpenBIOS, 512 MB, one CPU, 9G disk | `sun-solaris-8-0101-installation-sparc.iso`, `sun-solaris-8-0101-software-cd1-sparc.iso`, `sun-solaris-8-0101-software-cd2-sparc.iso` | `root` / `wshlab` | ~30 min |
| `sol9-ss20` | Solaris 9, End User, Web Start from the DVD | as `sol8-ss20` | `SOL_9_SPARC_DVD.iso` | `root` / `wshlab` | ~27 min |
| `sol10-sun4u` | Solaris 10 1/13, the default software group | sparc64 (sun4u), OpenBIOS, 1024 MB, serial console, a blank 16 GiB disk on `ide0`, the DVD on `ide2`, `sunhme`; needs `pve-qemu-kvm` 11.1.3-2+wsh13 or later | `sol-10-u11-ga-sparc-dvd.iso` | `root` / `wshlab` | ~110 min |
| `tribblix-m34-sun4u` | Tribblix m34 for SPARC (illumos), the base system on a ZFS root | sparc64 (sun4u), OpenBIOS, 2048 MB, serial console, a blank 8 GiB disk on `ide0`, the live CD on `ide2`, `sunhme`; needs an `openbios-sparc64` with patches 0016 and 0017 (no published package yet) | `tribblix-sparc-0m34.iso` | `root` / `wshlab` | TBD |
| `sunos414-ss5` | SunOS 4.1.4 (Solaris 1.1.2), Programmer, suninstall's Quick install | SS-5, OpenBIOS, 256 MB (64 MB during the install), serial console, 3 GiB disk on `scsi3` (SUN2.9G label, `/usr` slice cut to 1 GB), lance | `sunos414-cd.iso` (made from the CD's raw BIN, see "Media") | `root` / `wshlab` | ~6 min |
| `msdos622` | MS-DOS 6.22 from the three Setup floppies | i440fx, SeaBIOS, Pentium, TCG, 32 MB, std VGA, 1 GiB IDE disk, ne2k_pci (unused), floppy first in the boot order | `msdos622-disk1.img` ... `-disk3.img` (on `local:floppy/`) | none (no password; VGA console) | ~5 min |
| `freedos14` | FreeDOS 1.4, Floppy Edition, base install | as `msdos622` | `freedos14-boot.img`, `freedos14-disk1.img` ... `-disk6.img` (on `local:floppy/`) | none (VGA console) | ~11 min |
| `netbsd111-sparc64` | NetBSD 11.1, without X11 | sun4u, OpenBIOS, 512 MB, serial console, 8 GiB blank disk on `ide0`, CD on `ide2`, sunhme | `NetBSD-11.1-sparc64.iso` | `root` / `wshlab` | ~11 min |
| `netbsd111-sparc` | NetBSD 11.1, Minimal | SS-5, OpenBIOS, 256 MB, serial console, 3 GiB blank disk on `scsi3`, lance | `NetBSD-11.1-sparc.iso` | `root` / `wshlab` | ~7 min |
| `netbsd111-sparc-ss20` | NetBSD 11.1, Minimal | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as `netbsd111-sparc` | `NetBSD-11.1-sparc.iso` | `root` / `wshlab` | ~7 min |

The DOS targets are driven on the VGA text screen (read exactly from the text buffer), swap the
floppies when the installer asks, write a known `CONFIG.SYS`/`AUTOEXEC.BAT` (MS-DOS: HIMEM, `DOS=HIGH`,
no SMARTDRV) and the marker `C:\WSHLAB.TXT`; `--keyboard no` adds `KEYB NO`. The [DOS
guide](/guides/dos/) has the VM settings and what DOS gets of the first megabyte.

An SS-5 install doesn't boot on SS-10/SS-20 (the device paths differ), so each machine has its own
target. Solaris 8 and 9 are SS-20 only: Web Start is a Java program, and the SS-5's CPU runs the
lab's Solaris jobs about 9 times slower than the SS-20's. Solaris 9 is not supported on sun4m by
Sun (8 was the last release for it), but its installer and installed 32-bit kernel run on the
emulated SS-20; treat it as a curiosity. During the Solaris 8 and 9 installs the VM has
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
Every sun4u guest has the MAC address 52:54:00:12:34:56 whatever `net0` says, so two of them on one
network clash (the [sparc guide](/guides/sparc/#solaris-10)).

`tribblix-m34-sun4u` boots Tribblix's live CD (it imports its service descriptions on every boot,
so its login prompt takes about 45 minutes), answers the keyboard question with US-English, logs in
as root and runs the CD's own installer (`live_install.sh -G`: a ZFS root pool on the whole disk)
with the network down, so the result doesn't depend on the internet (with a network the installer
fetches some packages from pkgs.tribblix.org; without one it skips those few, see the sparc lab's
README). The first boot sets root's password, writes the marker, sets a static address with `ipadm`,
the default route, DNS and the optional user, and locks the live CD's `jack` account that the
installer copies along. The pool shows DEGRADED after the install: the fault manager counts the I/Os
that ZFS had to retry on the emulated IDE disk (no data errors); the first boot runs `zpool clear
rpool` (whether the mark stays away wasn't checked yet). In about one of three long runs the
guest's clock stops and the phase stalls until its timeout (a race in QEMU, see the sparc
guide). Like Solaris 10, don't `reboot` it: stop and start the VM.

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
off and nothing listens on the network (sysinst's defaults). Two things to know about sparc64: every
sparc64 VM has the same system MAC address (52:54:00:12:34:56, whatever `net0` says), so put only
one of them on a network segment; and NetBSD/sparc64 keeps a host core at 100% for as long as it
runs (no idle on sun4u). If a `halt -p` during the install never powers the VM off (seen once on
sparc64), the tool breaks into NetBSD's kernel debugger after 5 minutes, records its state in the
evidence and powers off from there.

**Solaris 2.4 and 2.5.1** (`sol24-ss5`, `sol251-ss5`) boot their installer only from a CD that
answers as a disk, and 2.4 only under a Sun PROM: their VMs have the SPARCstation 5 PROM (`bios:
ss5.bin`, part of the package's optional Sun PROM extra) and the CD-ROM drive has `cd_as_disk=1`
(`scsi6: local:iso/<cd>.iso,media=cdrom,cd_as_disk=1`; needs qemu-server with that option). The
CD also shows up in the installer's disk list as `c0t6d0`; the install selects only `c0t3d0`. After
the install the CD is ejected as for every target (`none`, an empty CD-ROM drive). Both take a
static address only (no DHCP client before 2.6). 2.4 shows a year after 1999 as 19xx in its date
screen and refuses it; the install types the 4-digit year there. 2.4's auto-layout makes small
slices (`/` 25 MB, `/usr` 108 MB, swap 130 MB, the rest of the disk `/export/home`), and it has no
`hostname` command. 2.5.1's install ends with its Maintenance Update, which takes most of its time.

## Media

The media must be on the node's storage (`local` by default, content type ISO image) under these
names, and they must be the tested media: `lab.py install` checks the size and the sha256 and refuses
anything else unless `--allow-untested-media`. Nothing is downloaded by the install; Sun and Oracle
software is never part of this project.

| File name | Size (bytes) | sha256 |
| --- | --- | --- |
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

The NetBSD CDs are freely redistributable: download them from
`https://cdn.netbsd.org/pub/NetBSD/NetBSD-11.1/images/` (the release's `SHA512` file has their
SHA512 checksums). Upload a medium through the storage's **ISO
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
install -m 644 e2e/sparc/{lab,recording,install,targets,targets_dos,vgatext,sunlabel}.py /opt/wsh-lab/lab/
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
(a second disk, mounted on `/data`; Solaris only), `--root-password`, `--user NAME` (and `--user-password`; a non-root
user with its home under `/export/home`; SunOS 4.1.4: `/home/<host>`; NetBSD: `/home`), `--check` (boot once more, log in with the documented
password and check the marker), `--template` (convert the finished VM to a template),
`--keep-on-failure`, `--allow-untested-media`, `--timeout` (seconds the install phase may take) and
`--out` (the evidence directory; default `/var/lib/wsh-lab/installs/<target>-<vmid>-<time>`).

What it does:

1. Checks the media (name, size, sha256) and refuses a VMID that exists anywhere in the cluster:
   it never overwrites a VM.
2. Creates the VM through the API with the target's profile, a disk with a Sun label (the Solaris
   2.6 installer lists only labelled disks; the label is written by the tool, no template needed;
   Solaris 10 labels a blank disk itself) and the CD in its drive, tagged `wsh-lab`.
3. Starts it and answers the installer on the serial console (the lab's scenario for that release).
   The install ends with `halt`, which powers the VM off (Solaris 10: the tool stops the VM when the
   installer's reboot doesn't come back).
4. Ejects the CD (the drive stays, empty) and sets the boot order to the disk.
5. Boots the installed system once: answers the first-boot questions with the root password, writes
   `/etc/wsh-lab-target`, adds the optional user, shuts down with `init 5`.
6. With `--check`, boots again, logs in as root with the password and checks the marker.
7. Writes the login, console, host name, network, marker and media into the VM's notes
   (description), optionally converts it to a template, and prints a summary.

While it runs the tool owns the VM's serial console: close `qm terminal` and the web console's
xterm.js first, they would get nothing. Measured in the PVE test container on the lab host
(TCG, two host cores for the container, one guest at a time, packages of 2026-11-16): `sol26-ss5`
took 11.8 minutes (install 407 s, first boot 182 s, check 105 s), `sol26-ss20` 12.1 minutes (413 s,
191 s, 105 s). Without `--check` it is two minutes less. `sol10-sun4u` (packages of 2026-11-17,
`pve-qemu-kvm` 11.1.3-2+wsh13): 108.5, 109.6 and 110.7 minutes in three runs that passed (install about 81 minutes, first boot about 19, check about 9; the first boot imports Solaris's service descriptions, and `init 5` takes 3 to 6 minutes).

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

On `sol26-ss20` (512 MB of memory) swap is 295 MB and `/export/home` 6973 MB. `/` and `/usr` are as small as on the 3G disk (auto-layout sizes them for the software, End User
System Support), so the extra space is all in `/export/home`. Software that installs under `/opt`
or `/usr` needs a layout of its own (the installer's Customize) or a link into `/export/home`.

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
`/etc/defaultrouter`, `/etc/resolv.conf`, or `/etc/dhcp.le0` for DHCP) and reboot.

## Licence keys

None of the current targets needs one. Later targets that do (Windows) will read keys from a local
file that is never committed, mask them in `result.json` (the lab masks every variable named
`*_KEY`, `*_PASSWORD` or `*SECRET`) and type them only where the installer doesn't echo them, so
they stay out of the logs and recordings.

## How it is tested

The sparc lab's `pve` matrix runs `lab.py install sol26-ss5 --check` every week in a PVE node in a
container with the published packages, and the `install` matrix runs every automated target (by
hand from the `sparc lab` workflow; with `sol10-sun4u` it takes about two and a half hours and needs
the Solaris 10 DVD in the lab's media directory). `e2e/sparc/tests/test_targets.py` checks the catalogue: every
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
