---
title: Floppy Device Reference
description: A reference page for the floppy hardware panel.
---

The WSH patches add first-class floppy disk support to Proxmox VE: floppy images are a dedicated storage content type, and VMs can have up to two floppy drives (`floppy0` = A:, `floppy1` = B:) that show up in the Hardware panel next to the CD/DVD drive. This is mainly aimed at DOS-era and Windows 9x guests, which often need boot or driver floppies during installation.

## Storage setup

Floppy images use the `floppy` content type and live in `template/floppy/` next to `template/iso/` on directory-based storages (Directory, NFS, CIFS, BTRFS, CephFS).

1. Go to **Datacenter → Storage**, edit a storage and enable the **Floppy image** content type. The `template/floppy` directory is created automatically when the storage is activated.
2. A **Floppy Images** tab appears on the storage, with upload and download-from-URL support. Accepted extensions are `.img`, `.ima` and `.vfd`.

Note: `.img` files are accepted by both the ISO Images and the Floppy Images upload dialogs — the tab you upload through decides whether the file becomes an `iso/` or a `floppy/` volume, so make sure to use the Floppy Images tab for floppy images.

## Adding a floppy drive

In the VM's **Hardware** panel choose **Add → Floppy Drive**, pick the drive number (0 = A:, 1 = B:) and select a floppy image — or attach one from the CLI:

```sh
qm set 100 --floppy0 local:floppy/dos622-boot.img
```

An empty drive can be configured with `--floppy0 none`, useful when the guest OS should be able to have media inserted later.

On `i440fx` machines the floppy drives attach to the chipset's onboard floppy controller; on `q35` an `isa-fdc` controller is added automatically.

## Booting from floppy

Floppy drives appear in **Options → Boot Order** like any other bootable device:

```sh
qm set 100 --boot order=floppy0;ide0
```

The legacy boot letter `a` (`boot: a`) also maps to the floppy drives.

## Swapping disks on a running VM

Editing the floppy drive of a running VM swaps the medium live — no restart needed. This makes multi-disk installations (installer asks for "disk 2") work the same way as changing a CD. Adding or removing a whole floppy *drive* on a running VM is registered as a pending change and applied on the next restart.

## Write behaviour

Floppy drives are **writable by default**, matching real hardware — DOS installers and guests frequently write volume labels, settings or files to floppies. Add `ro=1` to make a drive read-only:

```sh
qm set 100 --floppy0 local:floppy/master-boot.img,ro=1
```

Keep in mind that images in `template/floppy/` are shared:

- Two VMs mounting the same image writable at the same time can corrupt it.
- Floppy volumes are treated as removable reference media (like ISOs): they are **not** included in backups or snapshots, are not copied on clone (the clone references the same image), and are never deleted when a VM is destroyed. A snapshot rollback does not roll back floppy contents.

If a guest needs a private writable floppy, upload a copy of the image first.

## Limitations

- Maximum of two floppy drives per VM (`floppy0`, `floppy1`).
- x86_64 guests only.
- Floppy drive add/remove on a running VM is a pending change (media swap is live).

## Further reading

- [Machine Reference](/reference/machine/) — i440fx vs q35
- [Operating Systems guide](/guides/operating-systems/) — DOS and Windows 9x notes
