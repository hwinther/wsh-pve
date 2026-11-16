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

An SS-5 install doesn't boot on SS-10/SS-20 (the device paths differ), so each machine has its own
target. Both end with the host name of the target (`sol26-ss5`, `sol26-ss20`), `le0` at 10.0.2.15/24
(static, set by the installer; `--ip` changes it; no name service, no default route), the time zone
MET, and a marker file `/etc/wsh-lab-target` with the target, the install time and the media's
checksums.

In the catalogue but not automated yet (each listed by `lab.py targets` with what blocks it):
Solaris 2.5.1 (its installer boots only from a CD that answers as a disk, which a PVE CD-ROM drive
can't be), Solaris 7 and 9 (reach their installers, no install run), Solaris 8 (Web Start and three
CDs), SunOS 4.1.4 (installed by hand only), NetBSD 11.1 sparc64 and sparc (scenario or first-boot
step missing).

## Media

The media must be on the node's storage (`local` by default, content type ISO image) under these
names, and they must be the tested media: `lab.py install` checks the size and the sha256 and refuses
anything else unless `--allow-untested-media`. Nothing is downloaded; Sun and Oracle software is
never part of this project.

| File name | Size (bytes) | sha256 |
| --- | --- | --- |
| `solaris_2.6_598_sparc.iso` | 565862400 | `17351669cb91a89562ed6bb23345879c4d18bd019a85085ad53f777e7b7a6b14` |

The catalogue also lists the media of the targets that aren't automated yet (Solaris 2.5.1, 7, 8,
9, SunOS 4.1.4, NetBSD 11.1), with their checksums. Upload a medium through the storage's **ISO
Images** tab, or copy it to `/var/lib/vz/template/iso/` on a directory storage. Floppy images (for
the DOS targets planned later) will go on a storage with the **Floppy image** content type, under
`template/floppy/`.

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
install -m 644 e2e/sparc/{lab,recording,install,targets,sunlabel}.py /opt/wsh-lab/lab/
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
`--name`, `--hostname`, `--ip`, `--disk-size` (`3G`, the default, or `9G`: see "Disk size"), `--data-disk GIB`
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
password from the notes. The network setting is the installer's static address: change
`/etc/hostname.le0` and `/etc/hosts` (and add `/etc/defaultrouter`) for your network.

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
