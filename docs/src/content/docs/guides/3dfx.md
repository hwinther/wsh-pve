---
title: 3DFX / Mesa passthrough
description: Enabling experimental 3D acceleration for Windows 9x/2000/ME guests and matching host and guest versions
---

The WSH extensions bundle a QEMU build patched with [qemu-3dfx](https://github.com/hwinther/qemu-3dfx), which passes 3D rendering through to the host. This enables hardware-accelerated 3D (Glide and OpenGL/Mesa) in old Windows guests via a set of guest-side wrapper drivers.

:::caution
This is an experimental feature. It requires a matching pair of host QEMU and guest drivers — see version pairing below.
:::

## Version pairing

3DFX/Mesa passthrough has two halves that **must be built from the same `qemu-3dfx` commit**:

- **Host** — the `pve-qemu-kvm` package bundles the qemu-3dfx patch. The patched `qemu-system-x86_64` binary embeds a short revision string (`__REV__`, the first 7 characters of the qemu-3dfx commit).
- **Guest** — the wrapper drivers installed inside Windows embed the same `__REV__` string.

The wrapper refuses to load against a host binary with a different revision, so the two versions are locked together by design.

To find the matching pair:

1. Check the `pve-qemu-kvm` release notes — they state which qemu-3dfx commit the build was made against (for example `qemu-3dfx-drivers-b47f30a`).
2. Download the guest drivers from the [releases page](https://github.com/hwinther/wsh-pve/releases) with the **same short SHA** — the release is tagged `qemu-3dfx-drivers-<shortsha>` and includes a `VERSION.txt` recording the full commit.

## Enabling on the host

1. Set the guest **Architecture** to `x86_64` (see [Architecture](/reference/architecture/)).
2. Enable the **3DFX/Mesa** option in the [Display](/reference/display/) panel. When selected, the guest is started with the passthrough-patched `qemu-system-x86_64-3dfx` binary instead of the standard one.

## Installing the guest drivers

Download `qemu-3dfx-drivers-<shortsha>.zip` from the releases page (matching your `pve-qemu-kvm` version). It extracts to a single folder containing the Glide and OpenGL/Mesa wrappers:

`fxmemmap.vxd`, `fxptl.sys`, `glide.dll`, `glide2x.dll`, `glide2x.dxe`, `glide2x.ovl`, `glide3x.dll`, `glide3x.dxe`, `instdrv.exe`, `opengl32.dll`, `wglinfo.exe`

Transfer the files into the guest and install the ones for your Windows version:

**Windows 9x / ME**

- Copy `FXMEMMAP.VXD`, `GLIDE.DLL`, `GLIDE2X.DLL`, and `GLIDE3X.DLL` to `C:\WINDOWS\SYSTEM`
- Copy `GLIDE2X.OVL` to `C:\WINDOWS`
- Copy `OPENGL32.DLL` into each game's installation folder

**Windows 2000 / XP**

- Copy `FXPTL.SYS` to `%SystemRoot%\system32\drivers`
- Copy `GLIDE.DLL`, `GLIDE2X.DLL`, and `GLIDE3X.DLL` to `%SystemRoot%\system32`
- Run `INSTDRV.EXE` (requires Administrator privileges)
- Copy `OPENGL32.DLL` into each game's installation folder

## Further reading

- The [qemu-3dfx project](https://github.com/hwinther/qemu-3dfx)
- The [Display reference](/reference/display/) for the graphics card and 3DFX/Mesa options
