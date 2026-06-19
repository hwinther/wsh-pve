---
title: SPARC Guests
description: Running 32-bit and 64-bit SPARC guests on Proxmox VE with the WSH extensions
---

The WSH extensions add emulated SPARC and SPARC64 platforms so you can run Sun workstation operating systems such as SunOS / Solaris under Proxmox VE. SPARC emulation is experimental and sensitive to configuration — this guide collects the settings that are known to work.

:::caution
SPARC support is experimental. Only a narrow set of machine, BIOS, disk, and network combinations are known to boot. Treat these guests as best-effort, and keep them on a test host where possible.
:::

## Choosing an architecture

| Architecture | QEMU binary | Default machine |
| ------------ | ----------- | --------------- |
| sparc (32-bit) | `qemu-system-sparc` | SS-5 |
| sparc64 (64-bit) | `qemu-system-sparc64` | sun4u |

Set this in the VM's [Architecture](/reference/architecture/) panel. Selecting a SPARC architecture filters the machine, BIOS, disk, and network options to the supported subset.

## Recommended hardware layout

- **Machine** — `SS-5` for sparc, `sun4u` for sparc64 (see [Machine](/reference/machine/)).
- **BIOS / firmware** — OpenBIOS is the easiest and most reliable choice. The bundled `SS5`, `SS10`, and `SS20` PROM files are the only PROMs that are somewhat stable, and each expects a matching hardware layout (see [BIOS](/reference/bios/)).
- **Processor / memory** — a single CPU and around 512 MB of RAM for sparc32; the CPU model is fixed by the machine (see [Processors](/reference/processors/)).
- **Disk** — SCSI bus only.
- **CD-ROM** — SCSI.
- **Network** — `lance` (sparc; built into the machine and not hot-pluggable) or `sunhme` (sparc64). See [Network device](/reference/netdev/).
- **Display** — `cg3` (preferred) or `tcx` framebuffer; a serial console is also available (see [Display](/reference/display/) and [Serial port](/reference/serial/)).
- **Audio** — not currently working on SPARC.
- **USB / PCI passthrough** — not supported on SPARC.

## Installing SunOS / Solaris

<!-- TODO: expand with exact media versions and step-by-step screenshots -->

1. Create a VM and set the [Architecture](/reference/architecture/) to `sparc` (or `sparc64`).
2. Confirm the machine, BIOS, disk bus, and network card match the layout above.
3. Attach the installation media as a SCSI CD-ROM.
4. Make sure a network device is present **before** installing — on SunOS/Solaris the network only works if it was present at install time.
5. Boot the VM. Installation can take a long time and host CPU usage may sit near 100% for the emulated core; this is expected.

<!-- TODO: publish ready-to-use SUN-formatted raw images referenced in the project README -->

## Known limitations

- Audio does not work on SPARC guests.
- sparc32 is typically limited to a single CPU and ~512 MB of RAM.
- Only the `SS5`, `SS10`, and `SS20` PROM files are reasonably stable.
- sparc64 currently seems to only work with the OpenSPARC `disk.s10hw2` image.

## Further reading

- Read [about the SPARC platform](https://wiki.qemu.org/Documentation/Platforms/SPARC) in the QEMU documentation
- See the [Guest operating systems](/guides/operating-systems/) overview for OS-specific notes
