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
3. Leave **3DFX/Mesa display** at its default unless the node has a GPU (see [Choosing the display](#choosing-the-display-3dfxmesa-display)).

## Glide on the host: wsh-openglide

The Glide half of the pass-through renders with a host library: qemu-3dfx loads `libglide2x.so` (`libglide3x.so` for a Glide 3 guest) and hands it the guest's Glide calls. That library is OpenGLide, from [kjliew/qemu-xtra](https://github.com/kjliew/qemu-xtra), and the optional `wsh-openglide` package ships it:

```bash
apt install wsh-openglide
```

Without it a Glide guest gets no Glide device. The Mesa/OpenGL pass-through doesn't need it. The package has two platforms: OpenGLide's X11/GLX one, for the VM's SDL window on an X display, and an EGL offscreen one added by wsh-pve, for a VM without a local window (see below).

## Where the Glide and OpenGL frames show

- **In the VM's console (VNC, noVNC), with no X server.** This is what a VM with 3DFX/Mesa enabled gets in PVE by default: the console is VNC, there is no SDL window. qemu-3dfx then renders offscreen, on EGL with Mesa's surfaceless platform (a GPU's render node, or Mesa's software renderer without one), and copies every frame into the VM's console, where the PVE console, a screenshot (`screendump`) or any other display shows it in place of the VGA picture. Glide goes through the Glide library's EGL platform; OpenGL (the Mesa pass-through) is rendered by QEMU itself on an EGL pbuffer the size of the guest's display, which stands in for the game's window, and each frame is read when the game swaps its buffers. When the game closes its Glide window, or deactivates its OpenGL window or ends its OpenGL context, the console shows the VGA again. The same happens with `-display none`, `egl-headless`, `dbus` or `gtk`.
- **As a dmabuf, to a display with GL** (`-display egl-headless` or `-display dbus,gl=on`; in PVE, egl-headless with **3DFX/Mesa display**, see [Choosing the display](#choosing-the-display-3dfxmesa-display)). The frames are not read back: for Glide, wsh-openglide copies each one on the GPU into a buffer it shares with QEMU's display as a dmabuf, applying the game's gamma ramp in that copy (a small shader, in a GL context of its own), and the display imports it; for OpenGL, QEMU does the same itself, copying the game's window (the pbuffer) into a buffer of its own with a GL context of its own, so nothing of the game's GL state is touched, and applying the game's gamma ramp in that copy. egl-headless still reads the frame into the console for VNC; a D-Bus client (the stage 3 streaming client, for example) gets the dmabuf itself. Each window has two such buffers, and a frame is copied into the one the display doesn't have: while a D-Bus client hasn't finished with a frame, the game keeps drawing, each new frame replacing the one that waits in the other buffer, and the newest goes to the client as soon as it is done (QEMU looks every millisecond). With a `wsh-openglide` before 0.8, which has one buffer, Glide frames are held back instead and the newest follows 50 ms later. QEMU's display needs a GPU's render node, or on a node without a GPU `/dev/udmabuf`, through which Mesa's software renderer passes dmabufs (the 3dfx binary then uses Mesa's surfaceless EGL platform for its own display and says so). The frames are read back as before when the display has no GL, when `QEMU_3DFX_DMABUF=0` is set, or when the EGL driver can't export a dmabuf; for Glide also when `wsh-openglide` predates the dmabuf exports (`getOffscreenDmabuf`), and, while the game has a gamma ramp set, when it predates 0.6 (the gamma pass) or its shader can't be built; for OpenGL also when the game's window is multisampled (not seen with Mesa's software renderers, which render such a window without multisampling) and, with a gamma ramp, if the small shader that applies it can't be built. QEMU says which way it went when the window opens (`glidept: offscreen 640x480, frames to the graphic console as a dmabuf`, the same with `mesapt:` for OpenGL, or `..., read back (<why>)`) and counts both when it closes. QEMU's `screendump` can't take a picture while the console shows a dmabuf ("Error: no surface"); a VNC client can.
- **In an SDL window on an X display** (the `server=` option of the display, which uses `-display sdl` instead of VNC): OpenGLide and the OpenGL pass-through render into that window with GLX, as before.

### Choosing the display (3DFX/Mesa display)

A VM with 3DFX/Mesa enabled and a VNC console (no `server`) gets one of three QEMU displays next to its VNC server, set with the `mesa-display` property of `vga`, or **Hardware > Display > 3DFX/Mesa display** in the web UI (shown while **Enable 3DFX/Mesa** is checked):

```sh
qm set 120 --vga std,mesa=1                            # Default (read back): no -display
qm set 120 --vga std,mesa=1,mesa-display=egl-headless  # egl-headless (dmabuf)
qm set 120 --vga std,mesa=1,mesa-display=dbus          # D-Bus with OpenGL (dmabuf)
```

| `mesa-display` | QEMU gets | Glide frames | OpenGL frames |
| --- | --- | --- | --- |
| `none` (default) | `-vnc ...` only | read back into the console | read back |
| `egl-headless` | `-display egl-headless -vnc ...` | a dmabuf, which egl-headless reads into the console for VNC | read back |
| `dbus` | `-display dbus,addr=unix:path=/run/wsh-dbus-display/<vmid>.sock,gl=on -vnc ...` | a dmabuf to the D-Bus client; QEMU reads it into the console for VNC once per display refresh | a dmabuf likewise |

PVE's console (noVNC) works with all three. Which to use:

- **Without a GPU (Mesa's software renderer): the default.** egl-headless reads every frame back for VNC anyway, on QEMU's main loop, which costs more than the readback: the test scene ran at 830 to 1070 frames per second with egl-headless against 1440 to 1790 read back, and in Windows 98 at 960 to 970 against 1540 to 1700. Run through PVE (`qm start`, TCG), the test's Glide guest drew 944 frames per second with egl-headless.
- **With a GPU: egl-headless**, since a `glReadPixels` on the vCPU thread stalls a GPU's pipeline and the dmabuf way doesn't. On an NVIDIA GTX 1080 the test's Glide guest drew 1.2 to 3.7 times as many frames per second with egl-headless as read back (its OpenGL guest 0.7 to 1.5 times; both depend on the GPU's clocks, see below); see [NVIDIA GPU nodes](#nvidia-gpu-nodes) for what the node needs. AMD and Intel GPUs are untested.
- **For a streaming client on the node: `dbus`.** QEMU's D-Bus display with GL (`dbus,gl=on`), on a bus of the VM's own, hands each frame to its client as a dmabuf (the stage 3 streaming client in the ROADMAP; until then the test's listener, `e2e/3dfx/dbus-listener.py`). Upstream QEMU refuses a VNC server next to it ("Display vnc is incompatible with the GL context"); pve-qemu's `wsh/0130` lets the D-Bus console read the GL scanout back into the console's surface for VNC, as egl-headless does, but once per display refresh (30 ms, or `dbus-refresh`) instead of once per frame, so PVE's console stays. `dbus-refresh=<ms>` sets how often QEMU refreshes the display while a client listens (`wsh/0131`; QEMU's default 30 ms is about 33 updates a second). The bus, its access rules and the audio driver `dbus` are the same as without 3DFX/Mesa: see the [display reference](/reference/display/#d-bus-display).

What the node needs for egl-headless (and for `dbus`, the same):

- **A GPU's render node** (`/dev/dri/renderD*`), or on a node without one **`/dev/udmabuf`**, through which Mesa's software renderer exports and imports the dmabufs. Without either QEMU can't start egl-headless (Mesa has no `EGL_MESA_image_dma_buf_export`, "egl: render node init failed"), so qemu-server refuses to start the VM: `vga: mesa-display=egl-headless needs a GPU render node (/dev/dri/renderD*) or /dev/udmabuf on the node`.
- `/dev/udmabuf` comes from the kernel's `udmabuf` driver. Proxmox's kernels build it in (`CONFIG_UDMABUF=y` in the published configs of `proxmox-kernel-7.0.14-30-pve`, the default, and of the opt-in `7.3.5-1-pve`), as do Ubuntu's, including the kernels of GitHub's hosted runners, so the device is there from boot; check with `ls -l /dev/udmabuf`. Where it's a module, load it now and at every boot: `modprobe udmabuf` and `echo udmabuf > /etc/modules-load.d/udmabuf.conf`.
- No udev rule or group: qemu-server starts QEMU as root, in a systemd scope (`<vmid>.scope` in `qemu.slice`) without a device policy, so the device's usual `root:kvm 0660` is enough. A PVE node in a container needs the device passed in (a privileged container sees the host's).

### NVIDIA GPU nodes

Tested on a GTX 1080 with NVIDIA's proprietary driver (580). The dmabuf way needs the driver's kernel modesetting, which is off by default:

```sh
echo 'options nvidia_drm modeset=1' > /etc/modprobe.d/nvidia-drm-modeset.conf
update-initramfs -u
reboot
cat /sys/module/nvidia_drm/parameters/modeset   # Y
```

- **Without it** (`N`) NVIDIA's GBM backend doesn't start and its EGL can't export a dmabuf (`eglExportDMABUFImageMESA` fails with `EGL_BAD_MATCH`), so QEMU's display falls back to Mesa's software renderer and every frame is read back, as with `mesa-display=none`: the picture is right, only slower.
- **With it** egl-headless runs on the GPU and takes every Glide and OpenGL frame as a dmabuf (NVIDIA's own tiled layout), the gamma ramp applied on the GPU. Measured with TCG and the test scene: Glide 3502 frames per second with egl-headless against 956 read back from the same GPU (and 1150 with egl-headless on the software renderer), with a gamma ramp 2516 against 775, OpenGL 1018 against 678; through PVE (`qm start`) 3748 frames per second, 0.10 ms per frame for the copy.
- **The rates vary a lot from run to run** on that node, with the same binary: the GPU runs this light load (one 640x480 stream, about half its capacity) at reduced clocks (P5: 734 MHz core, 810 MHz memory) and drops further (P8) while the test holds a frame before its benchmark, and the node, a VM itself, shares its host's CPUs. With pve-qemu-kvm 11.1.3-4+wsh16 and `wsh-openglide` 0.8 in a PVE VM, the test's Glide guest drew 675 to 1676 frames per second with egl-headless against 545 read back, and its OpenGL guest 600 to 700 against 760 to 840 (the OpenGL copy costs about 0.5 ms there); in twelve alternating runs of the previous and the current binary both landed anywhere between about 440 and 2350 (medians 683 and 700), so the 3502 above is the top of that spread. Windows 98 in a PVE VM on the node (`vga: std,mesa=1,mesa-display=egl-headless`, KVM) passed Glide 2, Glide 3 and OpenGL with every frame as a dmabuf and the held frames kept, at 430 to 2240 frames per second with egl-headless and 470 to 870 read back.
- Where a context of QEMU's or of wsh-openglide's reads the game's frame (QEMU's copy of an OpenGL frame, wsh-openglide's gamma pass), it waits for the frame in the GPU's command stream (`EGL_KHR_wait_sync`) instead of QEMU waiting on the CPU; on the GTX 1080 that saved 0.05 to 0.15 ms a copy. Mesa's software renderers keep the CPU wait. `QEMU_3DFX_WAIT_SYNC=0` (or `1`) in QEMU's environment decides instead.
- The GPU's render node (`/dev/dri/renderD128`) does the exports and imports; `/dev/udmabuf` is only for nodes without a GPU, where Mesa's software renderer passes the dmabufs through it.
- Mesa's EGL and drivers (`libegl-mesa0`, `libgl1-mesa-dri`), which a PVE node with `pve-qemu-kvm` has already, and a `wsh-openglide` with the dmabuf export (`getOffscreenDmabuf`, published since 0.5); with an older one the Glide frames are read back with egl-headless too.

`mesa-display=egl-headless` is refused when the VM doesn't get the 3dfx binary (`mesa=0`, or another architecture than the node's), with a `server` (the SDL display) and with a display type without a VNC console (`none`, `serial*`). With `virtio-gl` the VM keeps the one `-display egl-headless,gl=core` that type always gets. QEMU's own messages (`glidept: offscreen 640x480, frames to the graphic console as a dmabuf`) go to its standard error, which is gone once PVE has started it in the background (to keep them, give the VM `args: -d plugin -D /path/to/qemu.log`: with a log file and a log mask a daemonized QEMU writes its standard error there, and the `plugin` mask logs nothing else without TCG plugins); while the game runs, the dmabufs show as open `dmabuf:` files in `/proc/<pid>/fd` of QEMU (`/run/qemu-server/<vmid>.pid`).

`QEMU_3DFX_OFFSCREEN=1` in QEMU's environment renders offscreen even with an SDL window (the frames then show in it as the console's picture). Glide offscreen needs a `wsh-openglide` with the EGL platform (its libraries export `getOffscreenFrame`); with an older one, or when EGL can't give a desktop OpenGL context, the guest's `grSstWinOpen()` fails and QEMU says why on its standard error, but keeps running. OpenGL offscreen needs `libEGL.so.1` (pve-qemu-kvm depends on `libegl1`) and Mesa's EGL; without them, or without an EGL display or context, the guest's `wglChoosePixelFormat()` and `wglCreateContext()` fail, QEMU says why (lines starting with `mesapt:`) and keeps running. Earlier builds ended QEMU when an OpenGL game started without an SDL window.

The game's gamma is applied offscreen too, when each frame is copied into the console: for Glide `grGammaCorrectionValue` and gamma tables (wsh-openglide keeps them, with no X server to set them on), for OpenGL `wglSetDeviceGammaRamp3DFX`, which the guest's `OPENGL32.DLL` also routes `SetDeviceGammaRamp` to. A game that draws into the Glide front buffer without swapping is shown at most 50 ms late, its last frame included: 50 ms after its last call QEMU reads it on the thread that drives the game's GL context.

A game that stops swapping keeps its last OpenGL frame on the console, as a Glide game does, until it deactivates its window (which Windows also does when the active window is destroyed), deletes its context or ends; then the VGA comes back. The OpenGL wrapper's display timer (`DispTimerMS`, 2 seconds by default) gives the console back to the VGA only with an SDL window, as upstream does there (after twice its time without a swap); up to pve-qemu-kvm 11.1.3-4+wsh12 it did so offscreen too, about 4 seconds after the last swap.

Not done offscreen yet:

- Glide multisampling (`ContextMSAA` in `glide.cfg`): the frame renders without it.
- OpenGL multisampling (the wrapper's `ContextMSAA`) only where the EGL driver gives a multisampled pbuffer's frame back. QEMU checks that when the game's window is made; Mesa's software renderers don't (llvmpipe fails the read, softpipe has no such config), so with them the game renders without multisampling and QEMU says so.
- OpenGL drawn into the front buffer without a swap (`glDrawBuffer(GL_FRONT)` and `glFlush`) shows only at the next swap.
- A display mode change while OpenGL frames are shown takes effect at the game's next `wglMakeCurrent` after the frames stopped (the SDL window has the same limit).
- The guest's OpenGL cursor (`wglSetDeviceCursor3DFX`) and mouse warps go to the SDL window only and are dropped offscreen (not checked with a game).
- A Glide window opened while an OpenGL window is active (Glide drawn through the OpenGL window with SDL) and an OpenGL window opened in a Glide game share the console: the last frame read wins.

Each frame costs one read of the window's pixels (`glReadPixels`) on the vCPU thread and a copy on QEMU's main loop. Measured in CI's setup (TCG, Mesa llvmpipe, 640x480, the test scene): a Glide read takes 0.14 to 0.2 ms, the console has the frame about 0.03 ms after it, and the guest still draws 1100 to 1750 frames per second of the test scene (about 2100 to 2400 with the SDL window). An OpenGL read takes 0.3 to 0.5 ms (it waits for the frame to finish rendering; 4 to 9 ms with softpipe), and the test's OpenGL guest draws 760 to 1840 frames per second offscreen, the lower figures with a gamma ramp set (about 1800 with the SDL window).

As a dmabuf (same setup, no GPU, `/dev/udmabuf`), a Glide frame costs the vCPU thread about 0.07 ms (the copy into the shared buffer and waiting for it). With egl-headless the main loop then spends 0.6 to 0.8 ms importing and reading the frame for VNC, so the guest draws fewer frames per second than with the readback (830 to 1070 against 1440 to 1790): with a software renderer and a VNC console the dmabuf way gains nothing. With `-display dbus,gl=on` and a client that maps the dmabuf, QEMU's own part is 0.04 ms. Frames drawn while the client is still busy go into the window's second buffer, each replacing the one before, and the newest goes to the client as soon as it replies: with a test client that answers 2 ms late, the guest drew 656 Glide frames per second and the client got 937 frames in the run (564 and 895 when such frames were held back and the newest followed 50 ms later), and for OpenGL 2958 against 1649 frames reached the client, while the guest's rate went from 222 to 169 frames per second (every frame is copied now, which costs 2 to 3 ms with Mesa's software renderer).

An OpenGL frame as a dmabuf costs the vCPU thread more than its readback with a software renderer: 0.8 to 1.1 ms (1.2 to 1.6 ms with a gamma ramp, which is applied in the copy), against 0.4 to 0.65 ms for the read. About 0.35 ms of it is waiting for the game's frame to finish, which the read waits for too; most of the rest is the copy itself, as Mesa's software renderer converts the window's pixel format into the shared buffer's by drawing instead of copying memory (a copy between two buffers of QEMU's own takes 0.06 ms). Measured with KVM, 640x480 and the test scene, the test's OpenGL guest draws about 330 frames per second with egl-headless as a dmabuf (main loop 0.75 ms a frame) against 360 to 450 read back, and 330 to 400 with `-display dbus,gl=on` (main loop 0.05 to 0.08 ms). On a GPU the copy is a GPU blit; that is not measured yet.

OpenGLide keeps its settings in `OpenGLid.ini` and writes a log, `OpenGLid.log` (and `OpenGLid.err` after an error). For a VM with 3DFX/Mesa enabled they are in `/run/qemu-server/<vmid>-3dfx/` on the node: qemu-server creates that directory (owned by root, mode 0700) when it starts the VM and passes it to OpenGLide in the `OPENGLIDE_DIR` environment variable. The directory stays after the VM stops, so the log of the last run can be read, and goes with the next reboot of the node. To change a setting, edit `OpenGLid.ini` there while the VM is stopped; after a reboot the file comes back with the defaults. Up to `wsh-openglide` 0.1 and qemu-server `9.2.20+wsh1` the files were written into `/` of the node, QEMU's working directory once it has started in the background, and OpenGLide ended QEMU (exit status 0, so the VM just stopped) when it couldn't write there. It no longer does: without a writable directory it runs with its defaults and no log.

qemu-3dfx itself reads `glide.cfg` and `mesagl.cfg` from QEMU's working directory, which is `/` under PVE, so they don't apply to VMs PVE starts.

The package's CI tests need no Windows and no game. `packages/wsh-openglide/test.sh` (in wsh-pve) renders a Glide 2 and a Glide 3 scene through the installed libraries under Xvfb with Mesa's software renderers and checks the pixels, also from a working directory it can't write to, then renders them again offscreen with no X server; with `/dev/udmabuf` it also maps the dmabuf the library exports for a GL display and compares it with the frame read back, pixel for pixel, without and with gamma ramps, then the second buffer (`getOffscreenDmabufAt`, 0.8), checking that a copy into it leaves the first buffer's frame alone. `e2e/3dfx/test.sh` boots two small Linux guests in `qemu-system-x86_64-3dfx` with an SDL display on Xvfb. The first draws the same scene through qemu-3dfx's Linux guest wrapper for Glide, with QEMU started the way PVE starts it, and the test checks that OpenGLide's files land in `OPENGLIDE_DIR`. The second draws it through the Mesa/OpenGL pass-through: qemu-3dfx has no Linux guest wrapper for Mesa, so the test's guest program talks to the pass-through device directly, the way the Windows `OPENGL32.DLL` does. Each guest reads its frame back through the pass-through, and the test checks those pixels and the VM's window. With `GLIDE_DISPLAY=vnc` both guests run headless (`-display none` and VNC, no X server installed), the Mesa guest a second time with a 4x multisampled pixel format, and the test checks the frame in QEMU's screendump of the console and that the console goes back to the VGA afterwards; there the Glide guest also draws into its front buffer without a swap and sets a gamma, the Mesa guest holds its first frame for 6 seconds with the Windows wrapper's display timer (2 seconds) set, deactivates its window, then sets a gamma ramp, and the test checks the console's colour after each: the held frame still shown 7 seconds after the swap, the VGA after the deactivation. `GLIDE_DISPLAY=egl` and `GLIDE_DISPLAY=dbus` run both guests with a GL display (egl-headless with VNC, or dbus,gl=on with the test's own D-Bus listener, `e2e/3dfx/dbus-listener.py`, which maps each dmabuf it gets); they need `/dev/udmabuf` (or a render node) passed to the container and are skipped without. A dmabuf that isn't linear (an NVIDIA GPU's) can't be mapped: the listener and `glide-render --dmabuf` import it through EGL and read it with `glReadPixels`, and where that import fails they say the pixel checks were skipped. On an NVIDIA node where `docker --gpus all` doesn't work (a driver from NVIDIA's installer), the tests ran with `/dev/nvidia*`, `/dev/dri` and `/dev/udmabuf` passed in, NVIDIA's EGL and GBM libraries and their glvnd and GBM json files mounted read-only, `--security-opt apparmor=unconfined` (a host's `docker-default` AppArmor profile can deny the UNIX sockets of Xvfb and QEMU's monitor) and `--init` (QEMU's `-daemonize` leaves a zombie otherwise). There the test checks both guests' frames as VNC serves them or as the listener got them, that QEMU sent them as a dmabuf, that both gamma phases' frames went as a dmabuf with the ramp applied (the Glide one also probed inside its Gouraud triangle, so a frame upside down fails; with a `wsh-openglide` before 0.6 the Glide phase is read back); with `QEMU_3DFX_DMABUF=0` in the container's environment it checks that both were read back instead. A pull request that changes the qemu-3dfx code, the port or the package runs the headless and the SDL run against a binary built from it (`qemu-3dfx-check.yml`).

Through PVE itself, `e2e/tests/3dfx-gl-display.spec.ts` (Playwright, in the e2e container) starts the same Glide guest with `qm start` (Debian's kernel and the guest through the VM's `args`), once with the default display and once with `mesa-display=egl-headless`, and checks the scene in the VM's noVNC console, plus that egl-headless has the frames' dmabufs open. It needs the guest in the container, which `e2e/3dfx/pve-guest-setup.sh [container]` builds there, and is skipped without it. On a node with neither a render node nor `/dev/udmabuf` it checks that the egl-headless VM is refused at the start instead. The `E2E` workflow builds the guest before each run (about 40 seconds; `PVE_GUEST_FETCH=1` fetches the qemu-3dfx submodule its checkout lacks) and sets `E2E_3DFX_GUEST=required`, so a failed setup fails the spec instead of skipping it; GitHub's runners have `/dev/udmabuf`, so both parts run there.

On a host whose X server offers a 32-bit ARGB visual (Xvfb with its Composite extension, for example), the first Glide frame can end QEMU with an X `BadMatch` error. OpenGLide picks that visual for its GLX context, while SDL's window uses the 24-bit default.

## Testing in a Windows 98 guest

The tests above need no Windows. `e2e/3dfx/win98-test.sh` (in wsh-pve) goes one step further: it boots a real Windows 98 SE in `qemu-system-x86_64-3dfx` and has our own programs draw the same test scene through qemu-3dfx's Windows guest wrappers, Glide 2 (`GLIDE2X.DLL`), Glide 3 (`GLIDE3X.DLL`) and OpenGL (`OPENGL32.DLL` next to the program), as a game would.

Windows is not part of wsh-pve and never will be: the operator brings an installed Windows 98 SE disk of their own. It has to be a raw image with one FAT32 partition, installed in a PVE VM with `cpu: pentium3`, 512 MB, `scsihw: lsi` with the disk on `scsi0`, `vga: std,mesa=1`, an `rtl8139` NIC, AC97 audio and the tablet (the defaults), and log on to the desktop without a password prompt. The test starts QEMU with exactly that device set, at the PCI addresses the template's VM had (two PCI bridges, AC97 at 00:04.0): Windows 98 identifies a PCI device by its slot, and a device it hasn't seen there starts the new-hardware wizard, which waits for someone to answer it. The disk is only read. Each run works on a copy, onto which mtools writes:

- the guest drivers of the binary under test (the `qemu-3dfx-drivers-<shortsha>` release, the revision `--version` names, downloaded with `gh release download`): `FXMEMMAP.VXD`, `GLIDE.DLL`, `GLIDE2X.DLL` and `GLIDE3X.DLL` into `C:\WINDOWS\SYSTEM`, `GLIDE2X.OVL` into `C:\WINDOWS`, `OPENGL32.DLL` into `C:\WIN3DFX`;
- the test programs, built with Debian's mingw-w64 without its C runtime (Windows 98's `MSVCRT.DLL` is too old for it): `glidetst.exe` (Glide 2, or Glide 3 with `glide3`), `gltest.exe` (OpenGL: it switches the display to 640x480 and makes a WGL context, as a full-screen game does) and `w3drun.exe`, which goes into the Start menu's StartUp folder, runs the programs from a list once the desktop is up and powers Windows off at the end;
- the FAT's clean-shutdown flag, so that a disk taken from a VM that was still running doesn't start ScanDisk.

The guest's clock starts an hour after the registry files' time (when Windows last ran), not at the host's time: across a change to or from daylight saving time Windows 98 stops at a "New clock settings" dialog.

Each program draws the scene, reads it back through the pass-through and checks it, and reports on COM1, which QEMU writes to a file. When a frame is up, the harness checks the probes in QEMU's screendump of the console (headless, `-display none` and VNC, as PVE runs the VM), and after the program closes its 3D window, that the console shows the Windows desktop again. With `--hold 6` or more (seconds the program keeps its frame up without a swap; 5 by default) the frame is checked a second time 1.5 seconds before the hold ends, so a frame that gives way to the desktop while the program holds it fails the test (the summary's "Held frame" column). A test passes when all of these hold. The screendumps show Windows, so they stay on the machine that ran the test; the output directory, which a CI run uploads, has only our own text: the summary (verdicts, probe values, frame rates and qemu-3dfx's read-back times), the serial log, QEMU's and OpenGLide's logs.

```bash
e2e/3dfx/win98-test.sh --template win98se.raw --out out --private private        # the published binary
e2e/3dfx/win98-test.sh --template win98se.raw --out out --private private \
  --qemu-bin build/qemu-3dfx-bin/qemu-system-x86_64-3dfx                          # one built by check-qemu-3dfx-build.sh --out
e2e/3dfx/win98-test.sh ... -- --display sdl --tests glide2,opengl --accel tcg      # harness options after --
e2e/3dfx/win98-test.sh ... -- --display egl                                       # egl-headless: Glide and OpenGL as dmabufs
e2e/3dfx/win98-test.sh ... -- --display egl --hold 9                              # each frame held 9 s, checked again at 7.5 s
e2e/3dfx/win98-test.sh ... --openglide build/wsh-openglide/wsh-openglide_<version>_amd64.deb  # a wsh-openglide of your own
e2e/3dfx/win98-test.sh ... --pve wsh-pve-e2e -- --display egl                      # PVE starts the VM (qm start)
```

`--display egl` gives QEMU `-display egl-headless` beside its VNC server and takes the pictures from the VNC server, as QEMU's screendump has none while a dmabuf is shown; `/dev/udmabuf` goes into the container when the host has it. Glide's frames go as a dmabuf with a `wsh-openglide` that exports one, which the published package does since 0.5 (`--openglide` installs another one over it); OpenGL's go as a dmabuf with the QEMU binary alone. With such a package (November 2026, KVM, `cpu: pentium3`) Glide 2 and Glide 3 pass as dmabufs at 960 to 970 frames per second (1540 to 1700 read back with `--display vnc` in the same setup), and OpenGL passes as a dmabuf too, at 600 to 770 frames per second (a copy of 0.9 to 1.1 ms; 2200 read back with `--display vnc`). The summary's table of QEMU's offscreen windows says for each how many frames went as a dmabuf and how many were read back, and whether it was double-buffered (QEMU and `wsh-openglide` from 0.8).

With `--pve CONTAINER` PVE starts the VM instead: the harness runs in that PVE container (`e2e/pve/Dockerfile`, privileged) and creates the VM with `qm create` (`vga: std,mesa=1`, with `--display egl` also `mesa-display=egl-headless`), then `qm start`. The output and private directories must be bind-mounted into the container at the same paths: the disk copy is made in the private directory and attached through a directory storage of the run's own (`w3d<vmid>`, removed afterwards). The harness reads the console where PVE's console reads it, QEMU's screendump through the VM's QMP socket or (egl-headless) PVE's VNC socket with a password it sets through QMP (again before every picture, as opening the noVNC console sets PVE's ticket), and keeps QEMU's messages through `args: -d plugin -D ...`. To keep Windows away from its new-hardware wizard the VM gets the template's device positions: a machine version before 11.1 (from 11.1 qemu-server adds a third PCI bridge), no `vmgenid`, and AC97 through `args` at 00:04.0 (qemu-server's `audio0` puts it behind a bridge). `--vmid` picks the VM's ID (default 9398). Results (November 2026, the published pve-qemu-kvm 11.1.3-4+wsh4, qemu-server 9.2.20+wsh7 and wsh-openglide 0.5, KVM, `cpu: pentium3`, Mesa's software renderer, no GPU, `/dev/udmabuf`):

| Display | Glide 2 | Glide 3 | OpenGL |
| --- | --- | --- | --- |
| `mesa-display=egl-headless` (dmabuf) | pass, 440-560 frames/s, all 2004 frames as a dmabuf (copy 0.09 ms) | pass, 640-660 frames/s, all as a dmabuf (0.08 ms) | pass, 810 frames/s, all as a dmabuf (1.0-1.6 ms) |
| default (read back) | pass, 1150 frames/s (read 0.18 ms) | pass, 1430 frames/s (0.16 ms) | pass, 440 frames/s (0.61 ms) |

The noVNC console showed the Glide and the OpenGL scene at 640x480 with egl-headless, and QEMU had 4 dmabufs open while a frame was up. With these packages an OpenGL frame that the program doesn't redraw gave the console back to the Windows desktop about 4 seconds after its last swap, with egl-headless and read back alike, with and without PVE (a held Glide frame stays): the OpenGL wrapper's display timer, `DispTimerMS` (2 seconds, twice). The test's 5-second hold is checked after one second, so it passed all the same. A frame now stays until the program deactivates its window or ends (see [Where the Glide and OpenGL frames show](#where-the-glide-and-opengl-frames-show)). Rerun with the fix (pve-qemu-kvm 11.1.3-4+wsh16 and `wsh-openglide` 0.8, or the same code built from its branch) and `--hold 9` (KVM, `cpu: pentium3`, Mesa's software renderer, `/dev/udmabuf`): Glide 2, Glide 3 and OpenGL pass with egl-headless and read back, with and without PVE, each frame still in the console 7.5 to 8 seconds after its swap; with egl-headless every frame of all three went as a dmabuf, double-buffered (OpenGL 820 frames/s, a copy of 0.66 ms, without PVE), and QEMU logged the display timer's deactivation it ignored once. The binary before (+wsh12) fails that check: the OpenGL frame was gone 7.7 seconds after its swap.

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

## DOS games

The guest drivers include two Glide 2 wrappers for DOS programs: `glide2x.dxe` (with `glide3x.dxe` for Glide 3), a DJGPP module, and `glide2x.ovl`, built with Open Watcom for games that run under a DOS extender such as DOS/4GW. They talk to the same glidept device as the Windows wrappers, so the host side, the revision pairing and the frames in the VM's console are the same.

How the wrappers reach the device: they map its MMIO page (physical `0xfbdff000`), the shared FIFO and data area (`0xfb500000`, 3 MB) and the linear frame buffer (`0xfb000000`) by their physical addresses through the DPMI host (DPMI function 0800h, "physical address mapping") and pass every Glide call and its data through that shared memory; QEMU never reads a pointer of the guest's, so paging, VCPI or a memory manager in the guest don't matter to it. No driver is loaded in DOS. Then they do the same handshake as the Windows wrappers: one built from another qemu-3dfx commit than the host binary is refused, and the program gets no Glide device.

### GLIDE2X.DXE (DJGPP games)

Tested in pure DOS: FreeDOS 1.4, booted from its floppy, passes with no memory manager, with HIMEMX, and with HIMEMX and JEMM386 (expanded memory on); see the test below. A DJGPP program needs a DPMI host: CWSDPMI, which FreeDOS installs (`C:\FREEDOS\BIN\CWSDPMI.EXE`, part of its base packages) and which a DJGPP program finds next to itself or on the `PATH`. CWSDPMI runs as a VCPI client under JEMM386 or EMM386 and takes the memory itself without one. Under Windows 9x the DOS box's DPMI host is Windows' own; that is not tested.

- Copy `GLIDE2X.DXE` (and `GLIDE3X.DXE` for a Glide 3 game) into the game's directory, or into a directory named in the `LD_LIBRARY_PATH` environment variable (DJGPP's `dlopen()` looks there).
- Make sure `CWSDPMI.EXE` is on the `PATH` or next to the game. Without a `C:` drive CWSDPMI says "cannot open swap file c:\cwsdpmi.swp" and carries on.
- The wrapper reads a `glide.cfg` in the current directory, if there is one, and hands it to the host.
- Only `GLIDE2X.DXE` is tested; `GLIDE3X.DXE` is built the same way but no test program uses it yet.

A DJGPP program links with the import library `dxe3gen -Y` makes next to the DXE (`libfxgl2.a`, `libfxgl3.a`; not in the release, `e2e/3dfx/dos/build.sh` in wsh-pve builds it): its stubs load the DXE at the first Glide call. The DXE finds the program's DJGPP runtime by looking for the start-up code of DJGPP 2.0x's `crt0` in the program's code, so a program linked with another start-up code doesn't get a Glide device.

### GLIDE2X.OVL (DOS/4GW games): not tested

`glide2x.ovl` is a 32-bit LE dynamic library (OS/2 format, the `__DLLstart_` entry point, no imports), which the game's DOS extender has to load: Glide 2 DOS games built with Watcom ship DOS/4GW for that. The OVL also relies on that extender: it opens and reads `glide.cfg` with 32-bit pointers through INT 21h, the extender's extended DOS interface, which a plain DPMI host such as CWSDPMI doesn't translate, and it uses the linear address DPMI returns as a pointer, which needs a data segment based at 0 (DOS/4GW's flat model). DOS/4GW isn't free software, no free DOS extender in Debian or FreeDOS loads LE libraries, and the DJGPP image wsh-pve builds the drivers in carries only Open Watcom's Linux tools (`binl64`: the compiler and linker), without DOS/4GW or Watcom's DOS C library, so there is no free way to load the OVL in a test. Upstream's install notes put it into `C:\WINDOWS` of a Windows 9x guest, for DOS games in its DOS box; that isn't tested either.

### The DOS test

`e2e/3dfx/dos-test.sh` (in wsh-pve) runs the DXE end to end with free software only. Its test program, `GLIDEDOS.EXE` (`e2e/3dfx/dos/glidedos.c`, built with DJGPP in the image that builds the guest drivers and linked with `libfxgl2.a`), draws the scene the other tests draw, reads it back through the pass-through with `grLfbReadRegion`, checks the probes and reports on COM1, as the Windows 98 test programs do. The guest is the boot floppy of the FreeDOS 1.4 Floppy Edition (downloaded once, or given with `--freedos-zip`, and checked against its sha256) with, written onto a copy by mtools, a `FDCONFIG.SYS` that loads the memory managers of the run and starts `GLIDE.BAT` instead of the installer, the test program, the release's `GLIDE2X.DXE`, and FreeDOS's own `CWSDPMI.EXE`, `HIMEMX.EXE` and `JEMM386.EXE`, which are not on the boot floppy: the harness takes them out of the package archive on the Floppy Edition's other floppies and checks them against the files a FreeDOS installation from those floppies has. `GLIDE.BAT` sends the console to COM1 (`CTTY COM1`), so DOS's, CWSDPMI's and the program's messages all reach the log, shows what the memory managers set up, runs the program and powers the VM off. QEMU runs headless, as PVE runs a `vga: std,mesa=1` VM; when the frame is up the harness checks the probes in QEMU's screendump of the console, and once the Glide window has closed that the console shows DOS's text screen again.

```bash
e2e/3dfx/dos-test.sh --out out                                   # the published binary, three memory profiles
e2e/3dfx/dos-test.sh --out out -- --profiles emm386 --accel tcg  # harness options after --
e2e/3dfx/dos-test.sh --out out --pve wsh-pve-e2e                 # PVE starts the VM (qm create with floppy0, qm start)
```

The `3dfx in DOS` workflow runs it on a GitHub-hosted runner for pull requests that touch the 3dfx tests or the qemu-3dfx pin, by hand and weekly. Results (November 2026, pve-qemu-kvm 11.1.3-4+wsh17, `qemu-3dfx-drivers-b94d988`, wsh-openglide 0.8, `cpu: pentium3`, 64 MB, Mesa's llvmpipe, read back, 300 frames of the test scene):

| Memory managers | QEMU, KVM | QEMU, TCG | PVE (`qm start`, KVM) |
| --- | --- | --- | --- |
| none (CWSDPMI takes the memory raw) | pass, 1590 frames/s | pass, 1580-1840 frames/s | pass, 1720 frames/s |
| HIMEMX (XMS) | pass, 1560 frames/s | pass, 1460-1550 frames/s | pass, 1750 frames/s |
| HIMEMX and JEMM386 (EMS, CWSDPMI as a VCPI client) | pass, 1300 frames/s | pass, 1260-1560 frames/s | pass, 1270 frames/s |

In each run the program's own read-back of the back and front buffers matched, the console had the frame (qemu-3dfx read each frame in 0.14 to 0.17 ms) and DOS's text screen came back after the window closed. Under TCG the rate is about the same as under KVM: the guest does little more than copy the calls into the FIFO. The first read of the back buffer, with the frame's calls still queued, comes back shifted, as from the Linux guest (see `e2e/3dfx/glide-guest.c`); the test reports it without counting it. A DXE built with another revision gets no Glide device: the program says `ERROR no Glide device` and DOS carries on.

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

### Linux guests

The same release has `qemu-3dfx-linux-glide-<shortsha>.tar.gz`: qemu-3dfx's Linux guest wrapper built as a shared library for old i386 Linux guests (Glide 2.x only). It extracts to one folder:

- `libglide.so.2`: the Glide 2.x library (soname `libglide.so.2`), the Glide 2.43 API of qemu-3dfx's wrapper
- `libglide2x.so`: a symlink to it, the name 3dfx's Linux Glide 2 shipped under and that programs and Mesa's old 3dfx (fxMesa) driver were linked against
- `README.txt`: the revision and these steps

Install it as root in the guest, after removing any other `libglide.so.2` or `libglide2x.so` (3dfx's own Glide):

```sh
cp -P libglide.so.2 libglide2x.so /usr/lib/
ldconfig
```

A program that loads Glide under another file name gets a symlink of that name to `libglide.so.2`. The wrapper maps the glidept device's MMIO page and shared memory through `/dev/mem`, so the Glide program runs as root (or setuid root, as 3dfx's Glide needed too); no kernel module is needed. The library is built for the Pentium (`-march=pentium`, no CMOV, MMX or SSE) and needs nothing newer than glibc 2.0 (only `libc.so.6`, every symbol at `GLIBC_2.0`; checked by `scripts/build-3dfx-linux-glide.sh` in wsh-pve), so distributions from the glibc 2 era (1997 on) can load it; libc5 systems can't. The revision rule is the same as for the Windows drivers.

It covers programs that call Glide 2 directly, and OpenGL programs through an old Mesa built with the 3dfx driver against Glide 2. Glide 3 (`libglide3.so.3`, which later Mesa 3dfx drivers used) and OpenGL have no Linux guest wrapper in qemu-3dfx, so a Linux game whose renderer needs those gets no acceleration from it. A modern Linux guest should not use the 3DFX/Mesa option at all: virtio-gpu with virgl (`vga: virtio-gl`) gives it OpenGL.

`e2e/3dfx/test.sh` in wsh-pve tests the library: its `glide-dso` guest links the test scene against `libglide.so.2`, loads it from `/usr/lib` through ldconfig's cache, and passes the same scene and probe checks as the statically linked guest. That guest's userland is Debian 13's i386 libc; the library itself has not been run on an old distribution.

## Further reading

- The [qemu-3dfx project](https://github.com/hwinther/qemu-3dfx)
- The [Display reference](/reference/display/) for the graphics card and 3DFX/Mesa options
