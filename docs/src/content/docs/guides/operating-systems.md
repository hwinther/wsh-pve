---
title: Guest operating systems
description: Operating systems known to work with the WSH PVE extensions and tips for each
---

The WSH extensions are aimed at running older and non-x86 operating systems that benefit from legacy devices (cirrus / cg3 display, sb16 / adlib audio, ne2k / pcnet / lance network) and alternative architectures.

The operating systems below are known to work. OS-specific driver packs and detailed walkthroughs will be expanded over time.

:::note
This page is a work in progress. Driver packs, curated images, and detailed per-OS guides are planned but not yet published.
:::

| Operating system | Architecture | Notes |
| ---------------- | ------------ | ----- |
| Linux (as old as 2.x) | x86_64, sparc, sparc64 | Generally works with legacy devices; on sparc64 the Debian 12 ports installer starts but its install fails (see the [SPARC guide](/guides/sparc/#sparc64-sun4u)) |
| SunOS 4.1.3+ / Solaris 2.1+ | sparc | See the [SPARC guide](/guides/sparc/); on sparc32 SunOS 4.1.3 (SS-10), 4.1.3_U1B and 4.1.4, Solaris 2.1 and 2.2 (SS-10) and 2.3 Edition II to 9 install (8 and 9 on the SS-5 and the SS-20); 2.2-2.4 under OpenBIOS with `pve-qemu-kvm` 11.1.3-2+wsh22 or later, 2.3 and 2.4 on the SS-20 also with 2 or 4 CPUs, 2.1 with 11.1.3-2+wsh29 or later, the original SunOS 4.1.3 with 11.1.3-2+wsh31 or later; on sparc64 (sun4u with OpenBIOS) Solaris 10 installs from its DVD and the installed system boots (the lab's `sol10-sun4u` target), and so do Solaris 8 2/02 with `pve-qemu-kvm` 11.1.3-2+wsh23 or later and Solaris 9 9/05 with 11.1.3-2+wsh25 or later (OpenBIOS patch 0025; `sol8-sun4u`, `sol9-sun4u`); Solaris 7 reaches its installer; 2.5.1 and 2.6 don't boot |
| illumos (Tribblix m34) | sparc64 | On sun4u with OpenBIOS the live CD boots and installs to the IDE disk, and the installed system boots, with an `openbios-sparc64` that has patches 0016 and 0017 (`pve-qemu-kvm` 11.1.3-2+wsh19 or later); slow under emulation (about 45 minutes to the live CD's login). See the [SPARC guide](/guides/sparc/#tribblix-illumos) |
| NeXTSTEP 3.3, OPENSTEP 4.2 | sparc | Both install in the lab on an SS-5 with `ss5.bin` and a TCX framebuffer and run the Workspace, with the VM option `machine: SS-5,esp-irq-latency=500` (the SCSI interrupt delay; pve-qemu-kvm 11.1.3-2+wsh24 and qemu-server 9.2.19+wsh2 or later). Without it the install hangs on the disk. See the [SPARC guide](/guides/sparc/#nextstep-33-and-openstep-42) |
| NetBSD | sparc, sparc64 | NetBSD 11.1 installs and runs on sparc (SS-5, SS-20) and sparc64 (sun4u); the lab installs it with one command ([Lab install targets](/guides/lab-install/)) |
| OpenBSD | sparc, sparc64 | OpenBSD 5.9, the last release for 32-bit sparc, installs and runs on the SS-5 and SS-20 with OpenBIOS and a serial display (`vga: serial0`; with `cg3` or `tcx` its kernel panics), one CPU (`openbsd59-ss5`, `openbsd59-ss20`; see the [SPARC guide](/guides/sparc/#installing-openbsd-59)). OpenBSD 8.0 installs and runs on sun4u with `pve-qemu-kvm` 11.1.3-2+wsh22 or later (OpenBIOS patch 0023; before, the installed kernel stops right after the loader); keep ntpd off (`rcctl disable ntpd`): with a reachable NTP server the IDE disk timed out after ntpd slewed the clock (rarely it times out and hangs without ntpd too). The lab installs both with one command (`openbsd59-ss5`, `openbsd59-ss20`, `openbsd80-sun4u`, [Lab install targets](/guides/lab-install/)) |
| FreeBSD | sparc64 | FreeBSD 12.4, the last release with sparc64, installs and runs on sun4u with OpenBIOS (IDE disk, `hme0`, serial console); reboot and power-off need OpenBIOS patches 0032 and 0033, which aren't in a package yet. The lab installs it with one command (`freebsd124-sun4u`, [Lab install targets](/guides/lab-install/)) |
| MS-DOS 3+ | x86_64 | Performance improved with a curated set of drivers and patches |
| Windows 1.x and up | x86_64 | Works with legacy display/network/audio devices |
| Windows 9x | x86_64 | VBE-enhanced drivers, plus 3DFX/Mesa passthrough for 3D acceleration |

## Linux

<!-- TODO: recommended device choices and any kernel/driver caveats per architecture -->

Older Linux releases (down to the 2.x kernel series) run on the legacy devices added by the extensions. Use the [reference pages](/reference/architecture/) to pick a display, network card, and audio device the guest has drivers for.

On sparc (sun4m), Red Hat Linux 6.2 (kernel 2.2.14) installs from its CD on the SS-5 and SS-20 profiles with OpenBIOS and a serial console; the lab installs it unattended with kickstart in about six minutes ([Lab install targets](/guides/lab-install/)). Give the disk a small `/boot` as its first partition: SILO, the SPARC boot loader, can't load its second stage from far into the disk on these machines.

Debian 4.0 "etch" (kernel 2.6.18), the last Debian release for sun4m, installs on the same profiles from its netinst CD with packages from `archive.debian.org`; the lab installs it unattended with a preseed file ([Lab install targets](/guides/lab-install/)). It needs `pve-qemu-kvm` 11.1.3-2+wsh20 or later (the ESP fix `wsh/0038`), see the [SPARC guide](/guides/sparc/).

## SunOS / Solaris

Solaris and SunOS run on the emulated SPARC platforms. See the dedicated [SPARC guide](/guides/sparc/) for the recommended machine, BIOS, disk, and network layout. For an installed Solaris 2.6, 7, 8 or 9 VM (sun4m) with known login details from one command on a node, see [Lab install targets](/guides/lab-install/).

## MS-DOS

<!-- TODO: link/publish the curated driver and patch collection referenced in the README -->

MS-DOS 3 and later run on x86_64. Performance and compatibility improve significantly with a curated collection of drivers and patches. The [DOS guide](/guides/dos/) has the recommended VM, installing MS-DOS 6.22 from floppies by hand or with the lab, and what DOS gets of the first megabyte.

## Windows

<!-- TODO: document the VBE-enhanced and 3DFX/Mesa driver packs and where to obtain them -->

Windows releases from 1.x onward are supported on x86_64. For Windows 9x, the VBE-enhanced display drivers and the experimental 3DFX/Mesa passthrough (see [Display](/reference/display/)) enable accelerated graphics.

## Graphical and audio forwarding

Several of these guests rely on legacy display and audio devices that cannot be used with SPICE. The extensions can forward GTK/SDL output and ALSA/PulseAudio/PipeWire audio to the host instead — see the [Audio device](/reference/audiodev/) and [Display](/reference/display/) references for configuration details.
