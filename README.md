# wsh-pve

| | |
|---|---|
| **Packages** | [![Proxmox VE](https://debian.wshosting.no/badges/pve.svg)](https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages) [![Debian](https://debian.wshosting.no/badges/distro.svg)](https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages) [![pve-manager](https://debian.wshosting.no/badges/pkg-pve-manager.svg)](https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages) [![qemu-server](https://debian.wshosting.no/badges/pkg-qemu-server.svg)](https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages) [![pve-qemu-kvm](https://debian.wshosting.no/badges/pkg-pve-qemu-kvm.svg)](https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages) [![libpve-storage-perl](https://debian.wshosting.no/badges/pkg-libpve-storage-perl.svg)](https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages) [![wsh-lab](https://debian.wshosting.no/badges/pkg-wsh-lab.svg)](https://debian.wshosting.no/guides/lab-install/) |
| **Build and publish** | [![E2E on main](https://github.com/hwinther/wsh-pve/actions/workflows/e2e.yml/badge.svg?branch=main&event=push)](https://github.com/hwinther/wsh-pve/actions/workflows/e2e.yml) [![Apt repository and docs (GitHub Pages)](https://github.com/hwinther/wsh-pve/actions/workflows/repo-update.yml/badge.svg)](https://github.com/hwinther/wsh-pve/actions/workflows/repo-update.yml) [![Submodule patches apply](https://github.com/hwinther/wsh-pve/actions/workflows/check-patches.yml/badge.svg?branch=main)](https://github.com/hwinther/wsh-pve/actions/workflows/check-patches.yml) |
| **Tests** | [![E2E tests](https://debian.wshosting.no/badges/tests-e2e.svg)](https://github.com/hwinther/wsh-pve/actions/workflows/e2e.yml?query=branch%3Amain+event%3Apush) |
| **Security** | [![zizmor - GitHub Actions SAST](https://github.com/hwinther/wsh-pve/actions/workflows/zizmor.yml/badge.svg?branch=main)](https://github.com/hwinther/wsh-pve/actions/workflows/zizmor.yml) [![poutine - GitHub Actions SAST](https://github.com/hwinther/wsh-pve/actions/workflows/poutine.yml/badge.svg?branch=main)](https://github.com/hwinther/wsh-pve/actions/workflows/poutine.yml) |

Badges are rendered by [`repo-update.yml`](https://github.com/hwinther/wsh-pve/blob/main/.github/workflows/repo-update.yml) from the apt repository and the quality summary of the newest E2E run on main.

WSH Proxmox Virtualization Environment patches: old and non-x86 guests as ordinary Proxmox VMs (created, configured, backed up and started from the web UI and API), on tested machine profiles, with the QEMU and firmware fixes they need.

## What runs where

| Guest | x86 | sparc32 SS-5 | sparc32 SS-10/SS-20 | sparc64 sun4u | aarch64 |
| --- | :-: | :-: | :-: | :-: | :-: |
| ☀️ SunOS 4.1.3_U1B | | ✅ | ✅ ⁴ | | |
| ☀️ SunOS 4.1.4 | | ✅ | | | |
| ☀️ Solaris 2.2 | | | ✅ ⁵ 🔧 | | |
| ☀️ Solaris 2.3, 2.4 | | ✅ ⁶ 🔧 | ✅ ⁴ ⁶ 🔧 | | |
| ☀️ Solaris 2.5.1 | | ✅ ¹ 🔧 | | | |
| ☀️ Solaris 2.5 | | ✅ ⁶ | ✅ ⁴ ⁶ | | |
| ☀️ Solaris 2.6, 7 | | ✅ 🔧 | ✅ | | |
| ☀️ Solaris 8, 9 | | ✅ ³ | ✅ ⁴ | ✅ ³ 🔧 | |
| ☀️ Solaris 10 | | | | ✅ 🔧 | |
| 🔥 illumos (Tribblix m34) | | | | ✅ 🔧 | |
| 🚩 NetBSD 11.1 | | ✅ | ✅ | ✅ | |
| 🐡 OpenBSD 5.9, 8.0 | | ✅ ⁹ | ✅ ⁹ | ✅ ⁷ 🔧 | |
| ⬛ NeXTSTEP 3.3, OPENSTEP 4.2 | | ◐ ⁸ | | | |
| 🎩 Red Hat Linux 6.2 | | ✅ | ✅ | | |
| 🌀 Debian 4.0 | | ✅ 🔧 | ✅ 🔧 | | |
| 🌀 Debian 12 (ports) | | | | ◐ ² | |
| 🏔️ Alpine Linux | ✔ | | | | ✔ |
| 💾 MS-DOS 6.22, FreeDOS 1.4 | ✅ | | | | |
| 💾🪟🐧 MS-DOS 3+, Windows 1.x-9x (3dfx/Mesa 3D), Linux 2.x | ✔ | | | | |

🔧 doesn't work with stock QEMU 11.1 and OpenBIOS: needs this repository's patches (table below) · ✅ installs unattended with `wsh-lab install <target>` through PVE and is checked after its first boot ([lab install targets](https://debian.wshosting.no/guides/lab-install/)) · ✔ runs (booted through PVE in the tests, or installed by hand) · ◐ the installer boots, the install or the installed system doesn't finish · blank: not tried or not supported.
¹ with the Sun PROM `ss5.bin` and the CD answering as a disk (`cd_as_disk=1`) · ² see the [SPARC guide](https://debian.wshosting.no/guides/sparc/#sparc64-sun4u) · ³ the SS-5 and sun4u targets install 8 2/02 and 9 9/05; on sun4u with pve-qemu-kvm 11.1.3-2+wsh23 or later, and for 9 also OpenBIOS patch 0025, which is in no package yet (without it the installed system's first boot panics in the floppy driver) · ⁴ on the SS-20 · ⁵ on the SS-10 (its only sun4m machine), OpenBIOS with `cd_as_disk=1`, pve-qemu-kvm 11.1.3-2+wsh22 or later · ⁶ OpenBIOS with `cd_as_disk=1` (2.3 and 2.4: pve-qemu-kvm 11.1.3-2+wsh22 or later; on the SS-20 also with 2 or 4 CPUs) · ⁷ pve-qemu-kvm 11.1.3-2+wsh22 or later; ntpd off (with a network that reaches NTP servers the disk times out after ntpd slews the clock); now and then an IDE timeout stops the guest's disk without ntpd too, see ² · ⁸ in the lab: the installer boots, then hangs on the disk with the published `pve-qemu-kvm` (an ESP interrupt timing problem); with an ESP fix not yet in a package it installs with `ss5.bin` and a TCX. Solaris 2.1 and the original SunOS 4.1.3, whose only sun4m machine is the SS-10, don't boot: their kernels stop early (2.1: QEMU itself stops after the device configuration; 4.1.3: a bad trap in a device probe), and the SS-10 Sun PROM doesn't run on QEMU's SS-10 · ⁹ OpenBSD 5.9, the last release for 32-bit sparc (8.0 is the sun4u column), OpenBIOS, one CPU; a serial display only (with a framebuffer QEMU adds the Sun keyboard, and 5.9's kernel panics); the sets come from a CD that `wsh-lab media` makes from the release's files.

### What stock QEMU and OpenBIOS can't do

The 🔧 cells, and what breaks without the patches carried here (`pve-qemu-kvm`'s `wsh/` series and `openbios/patches/`; details in [`submodules/SPARC.md`](submodules/SPARC.md)). Rows without 🔧 aren't known to need them, but not every one was tried on stock QEMU.

| Guest | Without the patches | Fixed by |
| --- | --- | --- |
| Solaris 2.2-2.4 under OpenBIOS | the boot block stops (`(is ?`, exception 0x9); 2.3/2.4 kernels panic (`can't remove OBP hole`, `BAD TRAP`) | OpenBIOS 0019-0022 |
| Solaris 2.5.1 | its CD loops on "gross error in esp status" (QEMU 10.1 and later) | QEMU `wsh/0001` |
| Solaris 2.6 on the SS-5 | panics when its `pmc` driver attaches (the APC region is 1 byte) | QEMU `wsh/0011` |
| Solaris 2.5.1-9 with 2-4 CPUs (SS-10/SS-20) | hangs within minutes (an interrupt unmasked in a delay slot isn't taken) | QEMU `wsh/0019` |
| Solaris 10 on sun4u | doesn't reach or finish its installer (`no nucleus hblk8`, no console input, DVD and disk not found, `Interrupt not seen`) | OpenBIOS 0003-0011, QEMU `wsh/0021` |
| Solaris 8 and 9 on sun4u | the kernel panics early (`BOP_ALLOC failed`, `VAC too big!`, then `boot_alloc: pp is NULL or free`); with those fixed, 9's first boot after the install panics in the floppy driver | OpenBIOS 0003-0011, 0024, 0025 (9), QEMU `wsh/0021` |
| Tribblix (illumos) on sun4u | firmware crashes on the live CD, the ZFS boot block crashes; the clock stops in a third of long runs | OpenBIOS 0016-0017, QEMU `wsh/0036` |
| OpenBSD 8.0 on sun4u | the installed kernel panics right after the loader | OpenBIOS 0023 |
| Debian 4.0 | the disk and CD go offline at the first command (`esp` driver) | QEMU `wsh/0038` |
| NeXTSTEP 3.3, OPENSTEP 4.2 | hang on disk access | an ESP interrupt-latency patch, in progress |
| sun4u guests with more than 3 GB | OpenBIOS stops before its banner, NetBSD can't claim memory | OpenBIOS 0013-0015 |

Not about whether a guest runs, but also carried: idle CPUs that stop instead of spinning (SunOS 4.1.4, Solaris 2.5.1-9, from LEMU and ours), sound on the SS-5 (CS4231, from LEMU), cg3 at any size (LEMU), the SS-5 as fast as the SS-20 (`wsh/0017`), each sun4u VM's own MAC (`wsh/0034`), Stop-A that stops instead of powering off (OpenBIOS 0008).

Profiles, limits and known problems per system: [guest operating systems](https://debian.wshosting.no/guides/operating-systems/), [SPARC](https://debian.wshosting.no/guides/sparc/), [DOS](https://debian.wshosting.no/guides/dos/).

## Getting started

To get started continue to the [setup guide](https://debian.wshosting.no/guides/setup/)

## Build

Run `make build-containers` to build the PVE build image which creates debian packages from the submodules and the djgpp build image which is used to build windows drivers.
This is an optional step as the packages are already published in the apt repository at [debian.wshosting.no](https://debian.wshosting.no/guides/setup/).

Run `make all` to build the debian packages and copy them into the build directory.
Run `make repo-update` to populate a debian package repository under the repo directory, you will need a gpg key in order to sign the packages.

Run `make wsh-lab` for the optional `wsh-lab` package (the sparc lab, `e2e/sparc`, as `apt install wsh-lab` and a `wsh-lab` command on a PVE node; see [Lab install targets](https://debian.wshosting.no/guides/lab-install/)). It is `Architecture: all`, depends on none of the patched packages, and the `wsh-lab package` workflow builds, tests and publishes it with them.

Run `make 3dfx-drivers` to build the qemu-3dfx guest drivers (Windows/DOS), and `make pve-qemu-bundle` for the `pve-qemu-kvm` package with the 3dfx/Mesa pass-through binary (`qemu-system-x86_64-3dfx`, from `make pve-qemu-3dfx`).

### Optional extras

`pve-qemu-kvm` (`make pve-qemu-bundle`) has four parts that never fail its build: when one doesn't build, the package is built and published without it.

| Extra | Make target | In the package | Without it |
| --- | --- | --- | --- |
| `3dfx` | `pve-qemu-3dfx` | `/usr/bin/qemu-system-x86_64-3dfx` | VMs with 3DFX/Mesa enabled don't start |
| `openbios` | `openbios-sparc32` | `openbios-sparc32`, `QEMU,cgthree.bin` from `openbios/` | QEMU's images, without the fixes in `submodules/SPARC.md` |
| `openbios-sparc64` | `openbios-sparc32` (the same `openbios/Dockerfile`) | `openbios-sparc64` from `openbios/` | QEMU's image: Solaris 10 on sun4u stops at `no nucleus hblk8 to allocate` |
| `sun-proms` | `restore-sparc` (private `submodules/sparc`) | `ss5.bin`, `ss10_v2.25_rom`, `ss20_v2.25_rom` | VMs with a Sun PROM don't start |

A target whose extra drops out prints `WARNING: optional extra <name> missing: <reason>`. `scripts/check-qemu-extras.sh --deb <file>` (or `--root /` on a host) lists what a package has. The `build-deb.yml` run of `pve-qemu` puts that list in its job summary and release notes, opens an issue per missing extra (updated by later builds, closed by the first one that has it again; the Sun PROMs are only expected in this repository, not in forks), and the e2e tests (`e2e/tests/qemu-extras.spec.ts`) fail when a published package lacks one.

The 3dfx binary is QEMU from the same tree as the package (Proxmox's patches, then ours from `pve-qemu.patch`) plus [qemu-3dfx](https://github.com/hwinther/qemu-3dfx) at the `submodules/qemu-3dfx` commit: its `hw/3dfx` and `hw/mesa`, and `submodules/pve-qemu-qemu-3dfx.patch`, our port of its QEMU patch (upstream's targets QEMU 9.2), applied as the quilt patch `wsh/0099-WSH-qemu-3dfx.patch`. When a new pve-qemu breaks that patch, `pve-qemu-3dfx` says so before the long build, and `scripts/refresh-qemu-3dfx-patch.sh` refreshes it: it applies the patch to that tree, merges it with `git apply --3way` when it doesn't apply and leaves the conflicts to resolve, then rewrites it (`--continue`); `--check` only tests it.

The `submodules/qemu-3dfx` pin moves only through a pull request: the daily sync keeps the fork up to date, and `promote-qemu-3dfx.yml` opens or updates one PR (`promote/qemu-3dfx`) with the upstream commits, `refresh-qemu-3dfx-patch.sh --check` and `scripts/check-qemu-3dfx-build.sh`, which builds only `qemu-system-x86_64` with qemu-3dfx from the package's tree (a few minutes). PRs that change the pin, the port or pve-qemu run the same build (`qemu-3dfx-check.yml`). Details in the [3dfx guide](docs/src/content/docs/guides/3dfx.md).

## Development

Run `make dev-links` to symlink the PVE pm and js files that are currently altered, in order to be able to reload and observe changes quickly.
Note: There are still manual steps in this process due to the pvemanagerlib.js file being cached in the browser, and changes to the PVE API will often require a `systemctl restart pvedaemon pveproxy`

## Roadmap

[ROADMAP.md](ROADMAP.md): what is done, what is in progress and what comes next.

## Usage

Once the packages have been installed on a PVE host, the proxmox frontend will have additional options, some of which are listed here:

* SPARC guests: sparc32 (sun4m) with OpenBIOS or an original Sun boot PROM, and sparc64 (sun4u) with OpenBIOS
  * Limited to the tested profiles: SS-5 (up to 256 MB, one CPU), SS-10 or SS-20 (up to 512 MB, 1 to 4 CPUs with OpenBIOS), and sun4u (up to 8192 MB, one CPU, IDE disks); see the [SPARC guide](https://debian.wshosting.no/guides/sparc/).
  * Sound on the SS-5 (CS4231, `audio0: device=cs4231`); none on the SS-10/SS-20 or sun4u.
  * Add the network device before installing Solaris: the installer configures the interfaces it finds.
  * An installed VM with known login details from one command on a node: the [lab install targets](https://debian.wshosting.no/guides/lab-install/) (`wsh-lab` package) cover SunOS 4.1.4, Solaris 2.4-10, NetBSD, Red Hat Linux 6.2 and more. Sun software and disks with it installed are not published.
  * Installs take a long time under emulation and keep a host core at 100% meanwhile; pin the VM to a slow core or use a test node. Once installed, SunOS 4.1.4 and Solaris 2.5.1-9 on sun4m stop the CPU when idle; sun4u guests don't yet.

* Floppy disk support: a dedicated `floppy` storage content type (stored in `template/floppy` next to the iso folder) with upload/listing in the UI, up to two floppy drives per VM (A:/B:) with boot-from-floppy and live media swap. Enable the **Floppy image** content type on a storage first (Datacenter → Storage → edit), or the storage list in **Add → Floppy Drive** stays empty - see the [floppy reference](https://debian.wshosting.no/reference/floppy/)

* Selecting an architecture and CPU outside of the default x86(-64) set (on create only; an existing VM keeps its architecture)

* Support for forwarding GTK/SDL UI and alsa/pulseaudio/pipewire audio to the host.
* The reason behind this is that old operating systems do not have matching virtio drivers, and some even benefit from the older devices such as cirrus or cg3 display. Those displays can not be used in combination with SPICE and VNC can be challenging to use especially with the mouse pointer bug (which is hacked together through a mousepad driver for operating systems that recognize such a device)
* Streaming display and audio from a headless node (a desktop in a container with Sunshine or Wolf) is planned; see "x86 retro" in the [roadmap](ROADMAP.md).

* Operating systems that are known to work: Linux as old as 2.x, SunOS 4.1.4 and Solaris 2.4 and up, illumos (Tribblix), NetBSD, MS-DOS 3 and up, Windows 1.x and up, Windows 9x with VBE-enhanced drivers and 3dfx/Mesa passthrough for 3D acceleration. Notes per system are in the [guest operating systems guide](https://debian.wshosting.no/guides/operating-systems/), with the [SPARC](https://debian.wshosting.no/guides/sparc/), [DOS](https://debian.wshosting.no/guides/dos/) and [3dfx](https://debian.wshosting.no/guides/3dfx/) guides.

### Graphical forwarding to host

1. Start X as a regular user
2. Run `xhost SI:localuser:root` to allow root to connect to your session
3. Configure pulseaudio or pipewire to allow unrestricted access (below)
4. In the VM's Hardware tab, set **Display → Server** to the X display (for example `:0`); the VM then gets a GTK window (SDL when 3DFX/Mesa is enabled) instead of VNC. Set the audio device's **server** to the PulseAudio socket (default `unix:/tmp/pulse-server`). See the [Display](https://debian.wshosting.no/reference/display/) and [Audio device](https://debian.wshosting.no/reference/audiodev/) references.

#### Pulseaudio configuration

* For pulseaudio, add the following to /etc/pulse/client.conf:

```bash
default-server = unix:/tmp/pulse-server
enable-memfd = yes
auto-connect-localhost = yes
cookie-file = /tmp/.pulse-cookie
```

* Edit /etc/pulse/default.pa and modify the line related to the unix protocol:

```bash
load-module module-native-protocol-unix auth-group=audio socket=/tmp/pulse-server
```

* Add root to the audio group:

```bash
sudo usermod -aG audio root
```

#### Pipewire

* Add the following to the file `/usr/share/pipewire/pipewire-pulse.conf` under the addresses section:

```bash
# Find this
pulse.properties = {
    # the addresses this server listens on
    server.address = [
        # And add the following section:
        "unix:native"
        {
          address = "unix:/tmp/pulse-server"
          client.access = "unrestricted"
        }
```

* Restart the service and verify that the unix-socket is created under /tmp

```bash
systemctl --user restart pipewire-pulse.service

ls -la /tmp/pulse-server

srwxrwxrwx 1 user user 0 Sep  6 21:41 /tmp/pulse-server
```
