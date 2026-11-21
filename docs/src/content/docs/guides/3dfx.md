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

## Where the Glide and OpenGL frames show

- **In the VM's console (VNC, noVNC), with no X server.** This is what a VM with 3DFX/Mesa enabled gets in PVE by default: the console is VNC, there is no SDL window. qemu-3dfx then renders offscreen, on EGL with Mesa's surfaceless platform (a GPU's render node, or Mesa's software renderer without one), and copies every frame into the VM's console, where the PVE console, a screenshot (`screendump`) or any other display shows it in place of the VGA picture. Glide goes through the Glide library's EGL platform; OpenGL (the Mesa pass-through) is rendered by QEMU itself on an EGL pbuffer the size of the guest's display, which stands in for the game's window, and each frame is read when the game swaps its buffers. When the game closes its Glide window, or deactivates its OpenGL window or ends its OpenGL context, the console shows the VGA again. The same happens with `-display none`, `egl-headless`, `dbus` or `gtk`.
- **As a dmabuf, to a display with GL** (`-display egl-headless` or `-display dbus,gl=on`; not what PVE sets up today). The Glide frames are not read back: wsh-openglide copies each one on the GPU into a buffer it shares with QEMU's display as a dmabuf, and the display imports it. egl-headless still reads the frame into the console for VNC; a D-Bus client (the stage 3 streaming client, for example) gets the dmabuf itself. While a D-Bus client hasn't finished with a frame, newer ones are held back, and the newest follows 50 ms later. QEMU's display needs a GPU's render node, or on a node without a GPU `/dev/udmabuf`, through which Mesa's software renderer passes dmabufs (the 3dfx binary then uses Mesa's surfaceless EGL platform for its own display and says so). The frames are read back as before when the display has no GL, when `wsh-openglide` predates the dmabuf exports (`getOffscreenDmabuf`), when `QEMU_3DFX_DMABUF=0` is set, while the game has a gamma ramp set, and for OpenGL (the Mesa pass-through) in every case so far. QEMU says which way it went when the window opens (`glidept: offscreen 640x480, frames to the graphic console as a dmabuf`, or `..., read back (<why>)`) and counts both when it closes. QEMU's `screendump` can't take a picture while the console shows a dmabuf ("Error: no surface"); a VNC client can.
- **In an SDL window on an X display** (the `server=` option of the display, which uses `-display sdl` instead of VNC): OpenGLide and the OpenGL pass-through render into that window with GLX, as before.

`QEMU_3DFX_OFFSCREEN=1` in QEMU's environment renders offscreen even with an SDL window (the frames then show in it as the console's picture). Glide offscreen needs a `wsh-openglide` with the EGL platform (its libraries export `getOffscreenFrame`); with an older one, or when EGL can't give a desktop OpenGL context, the guest's `grSstWinOpen()` fails and QEMU says why on its standard error, but keeps running. OpenGL offscreen needs `libEGL.so.1` (pve-qemu-kvm depends on `libegl1`) and Mesa's EGL; without them, or without an EGL display or context, the guest's `wglChoosePixelFormat()` and `wglCreateContext()` fail, QEMU says why (lines starting with `mesapt:`) and keeps running. Earlier builds ended QEMU when an OpenGL game started without an SDL window.

The game's gamma is applied offscreen too, when each frame is copied into the console: for Glide `grGammaCorrectionValue` and gamma tables (wsh-openglide keeps them, with no X server to set them on), for OpenGL `wglSetDeviceGammaRamp3DFX`, which the guest's `OPENGL32.DLL` also routes `SetDeviceGammaRamp` to. A game that draws into the Glide front buffer without swapping is shown at most 50 ms late, its last frame included: 50 ms after its last call QEMU reads it on the thread that drives the game's GL context.

Not done offscreen yet:

- Glide multisampling (`ContextMSAA` in `glide.cfg`): the frame renders without it.
- OpenGL multisampling (the wrapper's `ContextMSAA`) only where the EGL driver gives a multisampled pbuffer's frame back. QEMU checks that when the game's window is made; Mesa's software renderers don't (llvmpipe fails the read, softpipe has no such config), so with them the game renders without multisampling and QEMU says so.
- OpenGL drawn into the front buffer without a swap (`glDrawBuffer(GL_FRONT)` and `glFlush`) shows only at the next swap.
- A display mode change while OpenGL frames are shown takes effect at the game's next `wglMakeCurrent` after the frames stopped (the SDL window has the same limit).
- The guest's OpenGL cursor (`wglSetDeviceCursor3DFX`) and mouse warps go to the SDL window only and are dropped offscreen (not checked with a game).
- A Glide window opened while an OpenGL window is active (Glide drawn through the OpenGL window with SDL) and an OpenGL window opened in a Glide game share the console: the last frame read wins.

Each frame costs one read of the window's pixels (`glReadPixels`) on the vCPU thread and a copy on QEMU's main loop. Measured in CI's setup (TCG, Mesa llvmpipe, 640x480, the test scene): a Glide read takes 0.14 to 0.2 ms, the console has the frame about 0.03 ms after it, and the guest still draws 1100 to 1750 frames per second of the test scene (about 2100 to 2400 with the SDL window). An OpenGL read takes 0.3 to 0.5 ms (it waits for the frame to finish rendering; 4 to 9 ms with softpipe), and the test's OpenGL guest draws 760 to 1840 frames per second offscreen, the lower figures with a gamma ramp set (about 1800 with the SDL window).

As a dmabuf (same setup, no GPU, `/dev/udmabuf`), a Glide frame costs the vCPU thread about 0.07 ms (the copy into the shared buffer and waiting for it). With egl-headless the main loop then spends 0.6 to 0.8 ms importing and reading the frame for VNC, so the guest draws fewer frames per second than with the readback (830 to 1070 against 1440 to 1790): with a software renderer and a VNC console the dmabuf way gains nothing. With `-display dbus,gl=on` and a client that maps the dmabuf, QEMU's own part is 0.04 ms and the test guest draws 2100 to 2600 frames per second, as frames the client is still busy with are skipped.

OpenGLide keeps its settings in `OpenGLid.ini` and writes a log, `OpenGLid.log` (and `OpenGLid.err` after an error). For a VM with 3DFX/Mesa enabled they are in `/run/qemu-server/<vmid>-3dfx/` on the node: qemu-server creates that directory (owned by root, mode 0700) when it starts the VM and passes it to OpenGLide in the `OPENGLIDE_DIR` environment variable. The directory stays after the VM stops, so the log of the last run can be read, and goes with the next reboot of the node. To change a setting, edit `OpenGLid.ini` there while the VM is stopped; after a reboot the file comes back with the defaults. Up to `wsh-openglide` 0.1 and qemu-server `9.2.20+wsh1` the files were written into `/` of the node, QEMU's working directory once it has started in the background, and OpenGLide ended QEMU (exit status 0, so the VM just stopped) when it couldn't write there. It no longer does: without a writable directory it runs with its defaults and no log.

qemu-3dfx itself reads `glide.cfg` and `mesagl.cfg` from QEMU's working directory, which is `/` under PVE, so they don't apply to VMs PVE starts.

The package's CI tests need no Windows and no game. `packages/wsh-openglide/test.sh` (in wsh-pve) renders a Glide 2 and a Glide 3 scene through the installed libraries under Xvfb with Mesa's software renderers and checks the pixels, also from a working directory it can't write to, then renders them again offscreen with no X server. `e2e/3dfx/test.sh` boots two small Linux guests in `qemu-system-x86_64-3dfx` with an SDL display on Xvfb. The first draws the same scene through qemu-3dfx's Linux guest wrapper for Glide, with QEMU started the way PVE starts it, and the test checks that OpenGLide's files land in `OPENGLIDE_DIR`. The second draws it through the Mesa/OpenGL pass-through: qemu-3dfx has no Linux guest wrapper for Mesa, so the test's guest program talks to the pass-through device directly, the way the Windows `OPENGL32.DLL` does. Each guest reads its frame back through the pass-through, and the test checks those pixels and the VM's window. With `GLIDE_DISPLAY=vnc` both guests run headless (`-display none` and VNC, no X server installed), the Mesa guest a second time with a 4x multisampled pixel format, and the test checks the frame in QEMU's screendump of the console and that the console goes back to the VGA afterwards; there the Glide guest also draws into its front buffer without a swap and sets a gamma, the Mesa guest sets a gamma ramp, and the test checks the console's colour after each. `GLIDE_DISPLAY=egl` and `GLIDE_DISPLAY=dbus` run both guests with a GL display (egl-headless with VNC, or dbus,gl=on with the test's own D-Bus listener, `e2e/3dfx/dbus-listener.py`, which maps each dmabuf it gets); they need `/dev/udmabuf` (or a render node) passed to the container and are skipped without. There the test checks the Glide frame as VNC serves it or as the listener got it, that QEMU sent it as a dmabuf, and that the gamma phase's frames were read back. A pull request that changes the qemu-3dfx code, the port or the package runs the headless and the SDL run against a binary built from it (`qemu-3dfx-check.yml`).

On a host whose X server offers a 32-bit ARGB visual (Xvfb with its Composite extension, for example), the first Glide frame can end QEMU with an X `BadMatch` error. OpenGLide picks that visual for its GLX context, while SDL's window uses the 24-bit default.

## Testing in a Windows 98 guest

The tests above need no Windows. `e2e/3dfx/win98-test.sh` (in wsh-pve) goes one step further: it boots a real Windows 98 SE in `qemu-system-x86_64-3dfx` and has our own programs draw the same test scene through qemu-3dfx's Windows guest wrappers, Glide 2 (`GLIDE2X.DLL`), Glide 3 (`GLIDE3X.DLL`) and OpenGL (`OPENGL32.DLL` next to the program), as a game would.

Windows is not part of wsh-pve and never will be: the operator brings an installed Windows 98 SE disk of their own. It has to be a raw image with one FAT32 partition, installed in a PVE VM with `cpu: pentium3`, 512 MB, `scsihw: lsi` with the disk on `scsi0`, `vga: std,mesa=1`, an `rtl8139` NIC, AC97 audio and the tablet (the defaults), and log on to the desktop without a password prompt. The test starts QEMU with exactly that device set, at PVE's PCI addresses: Windows 98 identifies a PCI device by its slot, and a device it hasn't seen there starts the new-hardware wizard, which waits for someone to answer it. The disk is only read. Each run works on a copy, onto which mtools writes:

- the guest drivers of the binary under test (the `qemu-3dfx-drivers-<shortsha>` release, the revision `--version` names, downloaded with `gh release download`): `FXMEMMAP.VXD`, `GLIDE.DLL`, `GLIDE2X.DLL` and `GLIDE3X.DLL` into `C:\WINDOWS\SYSTEM`, `GLIDE2X.OVL` into `C:\WINDOWS`, `OPENGL32.DLL` into `C:\WIN3DFX`;
- the test programs, built with Debian's mingw-w64 without its C runtime (Windows 98's `MSVCRT.DLL` is too old for it): `glidetst.exe` (Glide 2, or Glide 3 with `glide3`), `gltest.exe` (OpenGL: it switches the display to 640x480 and makes a WGL context, as a full-screen game does) and `w3drun.exe`, which goes into the Start menu's StartUp folder, runs the programs from a list once the desktop is up and powers Windows off at the end;
- the FAT's clean-shutdown flag, so that a disk taken from a VM that was still running doesn't start ScanDisk.

The guest's clock starts an hour after the registry files' time (when Windows last ran), not at the host's time: across a change to or from daylight saving time Windows 98 stops at a "New clock settings" dialog.

Each program draws the scene, reads it back through the pass-through and checks it, and reports on COM1, which QEMU writes to a file. When a frame is up, the harness checks the probes in QEMU's screendump of the console (headless, `-display none` and VNC, as PVE runs the VM), and after the program closes its 3D window, that the console shows the Windows desktop again. A test passes when all three hold. The screendumps show Windows, so they stay on the machine that ran the test; the output directory, which a CI run uploads, has only our own text: the summary (verdicts, probe values, frame rates and qemu-3dfx's read-back times), the serial log, QEMU's and OpenGLide's logs.

```bash
e2e/3dfx/win98-test.sh --template win98se.raw --out out --private private        # the published binary
e2e/3dfx/win98-test.sh --template win98se.raw --out out --private private \
  --qemu-bin build/qemu-3dfx-bin/qemu-system-x86_64-3dfx                          # one built by check-qemu-3dfx-build.sh --out
e2e/3dfx/win98-test.sh ... -- --display sdl --tests glide2,opengl --accel tcg      # harness options after --
e2e/3dfx/win98-test.sh ... --openglide build/wsh-openglide/wsh-openglide_<version>_amd64.deb \
  -- --display egl                                                                 # egl-headless: Glide as a dmabuf
```

`--display egl` gives QEMU `-display egl-headless` beside its VNC server and takes the pictures from the VNC server, as QEMU's screendump has none while a dmabuf is shown; `/dev/udmabuf` goes into the container when the host has it. Glide's frames go as a dmabuf only with a `wsh-openglide` that exports one, which `--openglide` installs over the published package. With such a package (November 2026, KVM, `cpu: pentium3`) Glide 2 and Glide 3 pass as dmabufs at 960 to 970 frames per second (1540 to 1700 read back with `--display vnc` in the same setup), and OpenGL passes read back.

By default it runs the tests the binary can show headless (Glide with the stage 1 offscreen display, OpenGL too once the binary has the Mesa offscreen display). The `3dfx in Windows 98` workflow runs it by hand and weekly on the self-hosted lab runner, never for a pull request; the disk's path is its `template` input or the `WSH_WIN98_TEMPLATE` repository variable, and the run is skipped without one.

What it found (November 2026, KVM unless noted, llvmpipe, 640x480, 2000 frames of the test scene):

| Binary | Glide 2 | Glide 3 | OpenGL |
| --- | --- | --- | --- |
| pve-qemu-kvm 11.1.3-3+wsh5 (published, stage 1) | passes, 1400-1650 frames/s | passes, 1480-1690 frames/s | QEMU ends (a segmentation fault, no message) as soon as the guest loads `OPENGL32.DLL` without an SDL window |
| built with the Mesa offscreen display (stage 1b) | passes | passes | passes, 1890-2540 frames/s |
| pve-qemu-kvm 11.1.3-3+wsh6 (published, stage 1b), drivers built for i586, `cpu: pentium3` | passes, 730-910 frames/s (TCG and KVM) | passes, 760-1170 frames/s | passes, 840-1180 frames/s |

Windows reaches its desktop in 13-17 s under KVM and 26 s under TCG; the whole run with all three tests takes 50-70 s (KVM) or 83 s (TCG). qemu-3dfx reads a Glide frame back in 0.14 ms and an OpenGL frame in 0.3-0.4 ms, and the console has it 0.02 ms later; the desktop is back 0.6 s after the 3D window closes.

The guest drivers are built for the Pentium (see [Installing the guest drivers](#installing-the-guest-drivers)), so the test runs the VM's plain `cpu: pentium3` under TCG as well. A `qemu-3dfx-drivers` zip built before that (its `VERSION.txt` has no "built for i586" line) needs SSE2 to SSE4.2 and POPCNT; with such drivers `--cpu auto` (the default) adds `+sse2,+sse3,+ssse3,+sse4.1,+sse4.2,+popcnt` under TCG, and an explicit `--cpu` is passed on as it is.

With an SDL window on Xvfb (`--display sdl`) the frame is scaled into the window, which keeps the desktop's size (1024x768); Xvfb's screen has to be larger than that, or SDL makes the window smaller and crops the frame. There each test passed on its own, but in one VM the second or third 3D window ended QEMU with an X error (`BadRequest`, `BadLength`); not looked into further.

## How the host binary is built

The 3dfx binary is built from the same QEMU tree as the rest of `pve-qemu-kvm` (Proxmox's patches and the WSH ones), plus qemu-3dfx's Glide and Mesa devices and a port of its QEMU patch (upstream's targets QEMU 9.2; the port is `submodules/pve-qemu-qemu-3dfx.patch` in wsh-pve). The host binary, the release notes and the `qemu-3dfx-drivers-<shortsha>` release of a build all name the commit the `qemu-3dfx` submodule is pinned to.

### How the pin moves

The pin moves only through a pull request. Every evening `sync-qemu-3dfx.yml` brings the fork up to date with upstream, then `promote-qemu-3dfx.yml` (also started by hand) compares the fork's master with the pin. When upstream has new commits it pushes the branch `promote/qemu-3dfx` (main plus the new pin) and opens or updates one PR, `chore(deps): promote qemu-3dfx to <shortsha>`. The PR lists the upstream commits and what they changed (upstream's QEMU patches, the device code that goes into the binary, the guest drivers), and the result of two checks: whether the port still applies (`scripts/refresh-qemu-3dfx-patch.sh --check`; when it doesn't, the promotion tries a mechanical refresh and commits it to the branch) and whether `qemu-system-x86_64` with qemu-3dfx builds (`scripts/check-qemu-3dfx-build.sh`, about three minutes instead of the full package build). A failed check still opens the PR, as a draft with "(3dfx check failed)" in its title. The job that builds upstream's code has only a read-only token; a second job, which builds and runs nothing, pushes the branch and edits the PR. Nothing is merged automatically. When upstream has nothing new, a PR left open is closed. A branch with someone else's commits on it (a port fixed by hand) is left alone. Any PR that changes the pin, the port or pve-qemu runs the same build check (`qemu-3dfx-check.yml`). Merging the PR builds the guest drivers and `pve-qemu-kvm` at the new pin. Our port follows upstream's `00-qemu92x-mesa-glide.patch` only by hand: when the PR shows a change to that file, carry it over.

## When the package has no 3dfx binary

The 3dfx build is optional: when the qemu-3dfx patches stop applying to a new QEMU, `pve-qemu-kvm` is built and published without `qemu-system-x86_64-3dfx`, and VMs with 3DFX/Mesa enabled don't start (`unable to stat file '/usr/bin/qemu-system-x86_64-3dfx'`). Such a build is reported in an issue titled "pve-qemu-kvm built without the optional extra: 3dfx" and in the release notes. This was the case from `11.1.1-1+wsh1` (October 2026, the move to QEMU 11.1) until the qemu-3dfx patch was refreshed for QEMU 11.1.3. To check a host:

```bash
ls /usr/bin/qemu-system-x86_64-3dfx && /usr/bin/qemu-system-x86_64-3dfx --version | grep qemu-3dfx
```

The version in brackets on the first line is the `pve-qemu-kvm` version the binary was built for. Up to `11.1.3-3+wsh6` the 3dfx binary always said `+wsh1` there (its build didn't take the package's changelog), whatever version it shipped in; `dpkg-query -W pve-qemu-kvm` gives the real one.

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

The wrappers are built for a Pentium-class guest CPU: everything compiled is built with `-march=pentium` (x87 math, no MMX, SSE or later), and the build fails if a DLL, EXE or the DOS objects contain an MMX, SSE or later instruction (`scripts/check-3dfx-drivers-isa.sh` in wsh-pve). The MinGW runtime the DLLs link in is Debian's, built for the Pentium Pro, so a few of its routines (number formatting, among others) use CMOV; every CPU model from `pentium2` on has it. A `cpu: pentium3` VM runs them with or without KVM. Upstream qemu-3dfx builds them for x86-64-v2 (SSE2 to SSE4.2, POPCNT), and so did the `qemu-3dfx-drivers` releases until November 2026: a VM without KVM stops at the first Glide call with "This program has performed an illegal operation" with those unless its CPU model has the extensions, e.g. `pentium3,+sse2,+sse3,+ssse3,+sse4.1,+sse4.2,+popcnt`. A zip built for the Pentium says "built for i586" in its `VERSION.txt`.

## Further reading

- The [qemu-3dfx project](https://github.com/hwinther/qemu-3dfx)
- The [Display reference](/reference/display/) for the graphics card and 3DFX/Mesa options
