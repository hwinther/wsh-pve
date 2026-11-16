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

- **Host** — the `pve-qemu-kvm` package ships `/usr/bin/qemu-system-x86_64-3dfx`, QEMU built with qemu-3dfx next to the standard binaries. It embeds a short revision string (the first 7 characters of the qemu-3dfx commit), which `qemu-system-x86_64-3dfx --version` prints as `featuring qemu-3dfx@<shortsha>-<build time>`.
- **Guest** — the wrapper drivers installed inside Windows embed the same `__REV__` string.

The wrapper refuses to load against a host binary with a different revision, so the two versions are locked together by design.

To find the matching pair:

1. Check the `pve-qemu-kvm` release notes — they state which qemu-3dfx commit the build was made against (for example `qemu-3dfx-drivers-b47f30a`) — or run `qemu-system-x86_64-3dfx --version` on the host.
2. Download the guest drivers from the [releases page](https://github.com/hwinther/wsh-pve/releases) with the **same short SHA** — the release is tagged `qemu-3dfx-drivers-<shortsha>` and includes a `VERSION.txt` recording the full commit.

## Enabling on the host

1. Set the guest **Architecture** to `x86_64` (see [Architecture](/reference/architecture/)).
2. Enable the **3DFX/Mesa** option in the [Display](/reference/display/) panel. When selected, the guest is started with the passthrough-patched `qemu-system-x86_64-3dfx` binary instead of the standard one.

## How the host binary is built

The 3dfx binary is built from the same QEMU tree as the rest of `pve-qemu-kvm` (Proxmox's patches and the WSH ones), plus qemu-3dfx's Glide and Mesa devices and a port of its QEMU patch (upstream's targets QEMU 9.2; the port is `submodules/pve-qemu-qemu-3dfx.patch` in wsh-pve). The host binary, the release notes and the `qemu-3dfx-drivers-<shortsha>` release of a build all name the commit the `qemu-3dfx` submodule is pinned to.

### How the pin moves

The pin moves only through a pull request. Every evening `sync-qemu-3dfx.yml` brings the fork up to date with upstream, then `promote-qemu-3dfx.yml` (also started by hand) compares the fork's master with the pin. When upstream has new commits it pushes the branch `promote/qemu-3dfx` (main plus the new pin) and opens or updates one PR, `chore(deps): promote qemu-3dfx to <shortsha>`. The PR lists the upstream commits and what they changed (upstream's QEMU patches, the device code that goes into the binary, the guest drivers), and the result of two checks: whether the port still applies (`scripts/refresh-qemu-3dfx-patch.sh --check`; when it doesn't, the promotion tries a mechanical refresh and commits it to the branch) and whether `qemu-system-x86_64` with qemu-3dfx builds (`scripts/check-qemu-3dfx-build.sh`, about three minutes instead of the full package build). A failed check still opens the PR, as a draft with "(3dfx check failed)" in its title. Nothing is merged automatically. When upstream has nothing new, a PR left open is closed. A branch with someone else's commits on it (a port fixed by hand) is left alone. Any PR that changes the pin, the port or pve-qemu runs the same build check (`qemu-3dfx-check.yml`). Merging the PR builds the guest drivers and `pve-qemu-kvm` at the new pin. Our port follows upstream's `00-qemu92x-mesa-glide.patch` only by hand: when the PR shows a change to that file, carry it over.

## When the package has no 3dfx binary

The 3dfx build is optional: when the qemu-3dfx patches stop applying to a new QEMU, `pve-qemu-kvm` is built and published without `qemu-system-x86_64-3dfx`, and VMs with 3DFX/Mesa enabled don't start (`unable to stat file '/usr/bin/qemu-system-x86_64-3dfx'`). Such a build is reported in an issue titled "pve-qemu-kvm built without the optional extra: 3dfx" and in the release notes. This was the case from `11.1.1-1+wsh1` (October 2026, the move to QEMU 11.1) until the qemu-3dfx patch was refreshed for QEMU 11.1.3. To check a host:

```bash
ls /usr/bin/qemu-system-x86_64-3dfx && /usr/bin/qemu-system-x86_64-3dfx --version | grep qemu-3dfx
```

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
