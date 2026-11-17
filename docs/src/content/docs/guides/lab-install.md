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
telnet and the r-services from inetd; root logins are allowed on the console only).
:::

## Targets

| Target | What | Profile | Media (on `local:iso/`) | Login | Time |
| --- | --- | --- | --- | --- | --- |
| `sol26-ss5` | Solaris 2.6 5/98, End User | SS-5, OpenBIOS, 256 MB, serial console (`serial0`), Sun-labelled disk on `scsi3` (3G, or 9G with `--disk-size 9G`), lance | `solaris_2.6_598_sparc.iso` | `root` / `wshlab` | ~12 min |
| `sol26-ss20` | Solaris 2.6 5/98, End User | SS-20, OpenBIOS, 512 MB, one CPU, otherwise as above | `solaris_2.6_598_sparc.iso` | `root` / `wshlab` | ~12 min |
| `sol7-ss5` | Solaris 7 3/99, End User | as `sol26-ss5`, 3G disk | `Sol7.399InstallationSparc.iso` | `root` / `wshlab` | ~11 min |
| `sol7-ss20` | Solaris 7 3/99, End User | as `sol26-ss20`, 3G disk | `Sol7.399InstallationSparc.iso` | `root` / `wshlab` | ~10 min |
| `sol8-ss20` | Solaris 8 1/01, Entire Group, installed by Web Start from three CDs (swapped by the install) | SS-20, OpenBIOS, 512 MB, one CPU, 9G disk | `sun-solaris-8-0101-installation-sparc.iso`, `sun-solaris-8-0101-software-cd1-sparc.iso`, `sun-solaris-8-0101-software-cd2-sparc.iso` | `root` / `wshlab` | ~30 min |
| `sol9-ss20` | Solaris 9, End User, Web Start from the DVD | as `sol8-ss20` | `SOL_9_SPARC_DVD.iso` | `root` / `wshlab` | ~27 min |
| `msdos622` | MS-DOS 6.22 from the three Setup floppies | i440fx, SeaBIOS, Pentium, TCG, 32 MB, std VGA, 1 GiB IDE disk, ne2k_pci (unused), floppy first in the boot order | `msdos622-disk1.img` ... `-disk3.img` (on `local:floppy/`) | none (no password; VGA console) | ~5 min |
| `freedos14` | FreeDOS 1.4, Floppy Edition, base install | as `msdos622` | `freedos14-boot.img`, `freedos14-disk1.img` ... `-disk6.img` (on `local:floppy/`) | none (VGA console) | ~11 min |

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

In the catalogue but not automated yet (each listed by `lab.py targets` with what blocks it):
Solaris 2.5.1 (its installer boots only from a CD that answers as a disk, which a PVE CD-ROM drive
can't be), SunOS 4.1.4 (installed by hand only), NetBSD 11.1 sparc64 and sparc (scenario or
first-boot step missing).

## Media

The media must be on the node's storage (`local` by default, content type ISO image) under these
names, and they must be the tested media: `lab.py install` checks the size and the sha256 and refuses
anything else unless `--allow-untested-media`. Nothing is downloaded; Sun and Oracle software is
never part of this project.

| File name | Size (bytes) | sha256 |
| --- | --- | --- |
| `solaris_2.6_598_sparc.iso` | 565862400 | `17351669cb91a89562ed6bb23345879c4d18bd019a85085ad53f777e7b7a6b14` |
| `Sol7.399InstallationSparc.iso` | 588800000 | `3fe59c14307b924d40033f0f3a362c4384b4738a5a365a2f319d96883610c35d` |
| `sun-solaris-8-0101-installation-sparc.iso` | 584232960 | `d01915baa0503ad21fd9b99e0684e1231200ca3295e84f60a1bf310a956d51d4` |
| `sun-solaris-8-0101-software-cd1-sparc.iso` | 578023424 | `d50e437d82c96a906833fca182f813035d766b1645491eb06b221826ef9f39c8` |
| `sun-solaris-8-0101-software-cd2-sparc.iso` | 214757376 | `1b6fafd007673f924dc40103b3d2c565342b287d6ff8ad53ac07e1b4b73b44d4` |
| `SOL_9_SPARC_DVD.iso` | 3368878080 | `feb49d1fa21227a1493b5b4a083b2ca12e60577ccd84e4a22b5d3b86fd209911` |

The catalogue also lists the media of the targets that aren't automated yet (Solaris 2.5.1, SunOS
4.1.4, NetBSD 11.1), with their checksums. Upload a medium through the storage's **ISO
Images** tab, or copy it to `/var/lib/vz/template/iso/` on a directory storage.

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
(a second disk, mounted on `/data`), `--root-password`, `--user NAME` (and `--user-password`; a non-root
user with its home under `/export/home`), `--check` (boot once more, log in with the documented
password and check the marker), `--template` (convert the finished VM to a template),
`--keep-on-failure`, `--allow-untested-media`, `--timeout` (seconds the install phase may take) and
`--out` (the evidence directory; default `/var/lib/wsh-lab/installs/<target>-<vmid>-<time>`).

What it does:

1. Checks the media (name, size, sha256) and refuses a VMID that exists anywhere in the cluster:
   it never overwrites a VM.
2. Creates the VM through the API with the target's profile, a disk with a Sun label (the Solaris
   installers list only labelled disks; the label is written by the tool, no template needed) and
   the CD in its drive, tagged `wsh-lab`.
3. Starts it and answers the installer on the serial console (the lab's scenario for that release).
   The install ends with `halt`, which powers the VM off.
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
191 s, 105 s). Without `--check` it is two minutes less.

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
later, edit the same files (`/etc/hostname.le0` and `/etc/hosts` for the address, `/etc/netmasks`,
`/etc/defaultrouter`, `/etc/resolv.conf`, or `/etc/dhcp.le0` for DHCP) and reboot.

## Licence keys

None of the current targets needs one. Later targets that do (Windows) will read keys from a local
file that is never committed, mask them in `result.json` (the lab masks every variable named
`*_KEY`, `*_PASSWORD` or `*SECRET`) and type them only where the installer doesn't echo them, so
they stay out of the logs and recordings.

## How it is tested

The sparc lab's `pve` matrix runs `lab.py install sol26-ss5 --check` every week in a PVE node in a
container with the published packages, and the `install` matrix runs every automated target (by
hand from the `sparc lab` workflow). `e2e/sparc/tests/test_targets.py` checks the catalogue: every
target's profile against qemu-server's profile tables, unique names, the disk label. Details:
[`e2e/sparc/README.md`](https://github.com/hwinther/wsh-pve/tree/main/e2e/sparc#install-targets).
The `wsh-lab` package is built and tested on every pull request that changes the lab: lintian, then
in a clean Debian 13 `apt install` of the package, `wsh-lab --help`, `targets`, `media --dir`, the
catalogue's tests against the installed copy, `wsh-lab-mcp --setup` and `apt purge`, which must
leave nothing behind (`packages/wsh-lab/test.sh`).
