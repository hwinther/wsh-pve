# OpenBIOS: sun4u IDE tree differs from OBP; Solaris 10 can't use its DVD or disk (two bugs)

Material for bug reports to OpenBIOS. We carry the fixes as
`openbios/patches/0010-sparc64-pathres-interposed-package-gets-the-device-my-unit.patch` and
`openbios/patches/0011-sparc64-put-ide-drives-under-the-controller.patch`; `openbios/Dockerfile`
builds `openbios-sparc64` with them, and pve-qemu-kvm 11.1.3-2+wsh13 ships that firmware.

## Summary

On `qemu-system-sparc64 -M sun4u`, OpenBIOS creates a node per IDE channel and numbers the drives
inside it: `/pci@1f,0/pci@1,1/ide@3/ide@0/disk@0`, `.../ide@3/ide@1/cdrom@0`. OBP on an Ultra 5/10
puts the drives directly under the controller, addressed `target,lun`, where target is 2 × channel
+ unit: `ide@3/disk@0,0` and `ide@3/cdrom@2,0`. Solaris builds the same unit addresses for its
`dad`/`sd` nodes. It maps the firmware's boot path by them and binds its drivers to the drive nodes
through their `compatible` property. With OpenBIOS's tree, Solaris 10 1/13 runs into two problems:

- Booted from its DVD, its installer refuses the DVD:
  `ERROR: The disc you inserted is not a Solaris OS CD/DVD.`
- An installed system (once the tree is flat but without `compatible`) can't mount root:
  `Cannot load drivers for /pci@1f,0/pci@1,1/ide@3/disk@0,0:a`, `vfs_mountroot: cannot mount root`.

Flattening the tree exposed a second bug, in path resolution. An interposed package (the
`disk-label` package that `open-dev` puts on top of a disk or CD-ROM) answers `my-unit` with 0 0.
NetBSD's `ofwboot` reads the boot device's target and lun with `my-unit` on exactly that instance.
With `cdrom@2,0` it passed target 0, and the kernel took `wd0` instead of `cd0` as its root device.
With the old channel nodes NetBSD made up for the zeros with an OpenBIOS-specific offset.

- **Affected:** current master `e5ac46dd24` (QEMU 11.1.3), sun4u. `handle-interposers` is generic
  code.
- **Who to tell:** Mark Cave-Ayland, openbios@openbios.org.

## Evidence

`" cdrom" open-dev to my-self my-unit .s` at the `ok` prompt, with the flat tree:

| | `my-unit` |
| --- | --- |
| without 0010 | `0 0` |
| with 0010 | `0 2` (lun 0, target 2) |

The lab's `sparc64` matrix (NetBSD 11.1/9.3 CD and install, OpenBSD 8.0 `bsd.rd`, Debian 12):

| | Result |
| --- | --- |
| flat tree without 0010 | 5/9 (NetBSD's CD and install: `root device (default wd0a):`) |
| 0010 + 0011 | 9/9 |

With 0011, Solaris 10's installer maps the boot path to `/devices/pci@1f,0/pci@1,1/ide@3/sd@2,0:f`.
It accepts the DVD and lists the disk as `c0t0d0`. The installed system mounts root from
`/pci@1f,0/pci@1,1/ide@3/dad@0,0` (counts in `submodules/SPARC.md`, "Solaris on sun4u").

## Fix

- 0010, `forth/device/pathres.fs` `handle-interposers`: after linking the interposed instance,
  copy its parent instance's `my-unit` into it.
- 0011, `drivers/ide.c` (sparc64 only):
  - The controller gets `#address-cells` 2, `#size-cells` 0, and a `target,lun`
    `decode-unit`/`encode-unit` pair bound to its node.
  - The channel nodes go.
  - The drive nodes keep OBP's names `disk`/`cdrom`, get a two-cell `reg` (target, 0), and get
    `compatible` `ide-disk`/`ide-cdrom`.

paulsheer/openbios `5d7938c2` and maxinjohn/proxmox-solaris (`solaris.sh`) also flatten the tree:

- paulsheer names the nodes `dad`/`sd`.
- proxmox-solaris uses `dad@unit,0` with the target equal to the unit, which only works with the
  CD-ROM on the primary channel.

These patches are separate implementations and keep OBP's names.
