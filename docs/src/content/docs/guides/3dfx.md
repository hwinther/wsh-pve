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

## Glide on the host: wsh-openglide

The Glide half of the pass-through renders with a host library: qemu-3dfx loads `libglide2x.so` (`libglide3x.so` for a Glide 3 guest) and hands it the guest's Glide calls. That library is OpenGLide, from [kjliew/qemu-xtra](https://github.com/kjliew/qemu-xtra), and the optional `wsh-openglide` package ships it:

```bash
apt install wsh-openglide
```

Without it a Glide guest gets no Glide device. The Mesa/OpenGL pass-through doesn't need it. The package has two platforms: OpenGLide's X11/GLX one, for the VM's SDL window on an X display, and an EGL offscreen one added by wsh-pve, for a VM without a local window (see below).

## Where the Glide frames show

- **In the VM's console (VNC, noVNC), with no X server.** This is what a VM with 3DFX/Mesa enabled gets in PVE by default: the console is VNC, there is no SDL window. qemu-3dfx then has the Glide library render offscreen (EGL, on Mesa's surfaceless platform: a GPU's render node, or Mesa's software renderer without one) and copies every frame into the VM's console, where the PVE console, a screenshot (`screendump`) or any other display shows it in place of the VGA picture. When the game closes its Glide window, the console shows the VGA again. The same happens with `-display none`, `egl-headless`, `dbus` or `gtk`.
- **In an SDL window on an X display** (the `server=` option of the display, which uses `-display sdl` instead of VNC): OpenGLide renders into that window with GLX, as before.

`QEMU_3DFX_OFFSCREEN=1` in QEMU's environment renders offscreen even with an SDL window (the frames then show in it as the console's picture). Offscreen needs a `wsh-openglide` with the EGL platform (its libraries export `getOffscreenFrame`); with an older one, or when EGL can't give a desktop OpenGL context, the guest's `grSstWinOpen()` fails and QEMU says why on its standard error, but keeps running.

Not done offscreen yet: Glide gamma (`grGammaCorrectionValue`, gamma tables; GLX sets it on the X server) and multisampling (`ContextMSAA` in `glide.cfg`). A game that draws into the front buffer without swapping is shown at most 50 ms late, and its last frame only once it makes another Glide call. The Mesa/OpenGL pass-through still needs the SDL window: without one, QEMU ends when a Mesa guest starts.

Each frame costs one read of the window's pixels (`glReadPixels`) on the vCPU thread and a copy on QEMU's main loop. Measured in CI's setup (TCG, Mesa llvmpipe, 640x480, the test scene): a read takes 0.14 to 0.2 ms, the console has the frame about 0.03 ms after it, and the guest still draws 1100 to 1750 frames per second of the test scene (about 2100 with the SDL window).

OpenGLide keeps its settings in `OpenGLid.ini` and writes a log, `OpenGLid.log` (and `OpenGLid.err` after an error). For a VM with 3DFX/Mesa enabled they are in `/run/qemu-server/<vmid>-3dfx/` on the node: qemu-server creates that directory (owned by root, mode 0700) when it starts the VM and passes it to OpenGLide in the `OPENGLIDE_DIR` environment variable. The directory stays after the VM stops, so the log of the last run can be read, and goes with the next reboot of the node. To change a setting, edit `OpenGLid.ini` there while the VM is stopped; after a reboot the file comes back with the defaults. Up to `wsh-openglide` 0.1 and qemu-server `9.2.20+wsh1` the files were written into `/` of the node, QEMU's working directory once it has started in the background, and OpenGLide ended QEMU (exit status 0, so the VM just stopped) when it couldn't write there. It no longer does: without a writable directory it runs with its defaults and no log.

qemu-3dfx itself reads `glide.cfg` and `mesagl.cfg` from QEMU's working directory, which is `/` under PVE, so they don't apply to VMs PVE starts.

The package's CI tests need no Windows and no game. `packages/wsh-openglide/test.sh` (in wsh-pve) renders a Glide 2 and a Glide 3 scene through the installed libraries under Xvfb with Mesa's software renderers and checks the pixels, also from a working directory it can't write to, then renders them again offscreen with no X server. `e2e/3dfx/test.sh` boots two small Linux guests in `qemu-system-x86_64-3dfx` with an SDL display on Xvfb. The first draws the same scene through qemu-3dfx's Linux guest wrapper for Glide, with QEMU started the way PVE starts it, and the test checks that OpenGLide's files land in `OPENGLIDE_DIR`. The second draws it through the Mesa/OpenGL pass-through: qemu-3dfx has no Linux guest wrapper for Mesa, so the test's guest program talks to the pass-through device directly, the way the Windows `OPENGL32.DLL` does. Each guest reads its frame back through the pass-through, and the test checks those pixels and the VM's window. With `GLIDE_DISPLAY=vnc` the Glide guest runs headless (`-display none` and VNC, no X server installed), and the test checks the frame in QEMU's screendump of the console and that the console goes back to the VGA afterwards. A pull request that changes the qemu-3dfx code, the port or the package runs the headless and the SDL run against a binary built from it (`qemu-3dfx-check.yml`).

On a host whose X server offers a 32-bit ARGB visual (Xvfb with its Composite extension, for example), the first Glide frame can end QEMU with an X `BadMatch` error. OpenGLide picks that visual for its GLX context, while SDL's window uses the 24-bit default.

## How the host binary is built

The 3dfx binary is built from the same QEMU tree as the rest of `pve-qemu-kvm` (Proxmox's patches and the WSH ones), plus qemu-3dfx's Glide and Mesa devices and a port of its QEMU patch (upstream's targets QEMU 9.2; the port is `submodules/pve-qemu-qemu-3dfx.patch` in wsh-pve). The host binary, the release notes and the `qemu-3dfx-drivers-<shortsha>` release of a build all name the commit the `qemu-3dfx` submodule is pinned to.

### How the pin moves

The pin moves only through a pull request. Every evening `sync-qemu-3dfx.yml` brings the fork up to date with upstream, then `promote-qemu-3dfx.yml` (also started by hand) compares the fork's master with the pin. When upstream has new commits it pushes the branch `promote/qemu-3dfx` (main plus the new pin) and opens or updates one PR, `chore(deps): promote qemu-3dfx to <shortsha>`. The PR lists the upstream commits and what they changed (upstream's QEMU patches, the device code that goes into the binary, the guest drivers), and the result of two checks: whether the port still applies (`scripts/refresh-qemu-3dfx-patch.sh --check`; when it doesn't, the promotion tries a mechanical refresh and commits it to the branch) and whether `qemu-system-x86_64` with qemu-3dfx builds (`scripts/check-qemu-3dfx-build.sh`, about three minutes instead of the full package build). A failed check still opens the PR, as a draft with "(3dfx check failed)" in its title. The job that builds upstream's code has only a read-only token; a second job, which builds and runs nothing, pushes the branch and edits the PR. Nothing is merged automatically. When upstream has nothing new, a PR left open is closed. A branch with someone else's commits on it (a port fixed by hand) is left alone. Any PR that changes the pin, the port or pve-qemu runs the same build check (`qemu-3dfx-check.yml`). Merging the PR builds the guest drivers and `pve-qemu-kvm` at the new pin. Our port follows upstream's `00-qemu92x-mesa-glide.patch` only by hand: when the PR shows a change to that file, carry it over.

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
