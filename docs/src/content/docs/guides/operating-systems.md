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
| Linux (as old as 2.x) | x86_64, sparc, sparc64 | Generally works with legacy devices |
| SunOS / Solaris 2.4+ | sparc, sparc64 | See the [SPARC guide](/guides/sparc/) |
| MS-DOS 3+ | x86_64 | Performance improved with a curated set of drivers and patches |
| Windows 1.x and up | x86_64 | Works with legacy display/network/audio devices |
| Windows 9x | x86_64 | VBE-enhanced drivers, plus 3DFX/Mesa passthrough for 3D acceleration |

## Linux

<!-- TODO: recommended device choices and any kernel/driver caveats per architecture -->

Older Linux releases (down to the 2.x kernel series) run on the legacy devices added by the extensions. Use the [reference pages](/reference/architecture/) to pick a display, network card, and audio device the guest has drivers for.

## SunOS / Solaris

Solaris and SunOS run on the emulated SPARC platforms. See the dedicated [SPARC guide](/guides/sparc/) for the recommended machine, BIOS, disk, and network layout.

## MS-DOS

<!-- TODO: link/publish the curated driver and patch collection referenced in the README -->

MS-DOS 3 and later run on x86_64. Performance and compatibility improve significantly with a curated collection of drivers and patches.

## Windows

<!-- TODO: document the VBE-enhanced and 3DFX/Mesa driver packs and where to obtain them -->

Windows releases from 1.x onward are supported on x86_64. For Windows 9x, the VBE-enhanced display drivers and the experimental 3DFX/Mesa passthrough (see [Display](/reference/display/)) enable accelerated graphics.

## Graphical and audio forwarding

Several of these guests rely on legacy display and audio devices that cannot be used with SPICE. The extensions can forward GTK/SDL output and ALSA/PulseAudio/PipeWire audio to the host instead — see the [Audio device](/reference/audiodev/) and [Display](/reference/display/) references for configuration details.
