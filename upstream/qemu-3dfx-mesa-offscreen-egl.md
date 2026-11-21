# qemu-3dfx: the MESA GL pass-through without an SDL window (EGL pbuffer, frames into the console)

Material for the owner, who decides whether and how to offer it to kjliew (qemu-3dfx is his
project; nothing has been sent or posted, and the code was written with an AI assistant, which he
may not want). It follows the Glide change of
[qemu-3dfx-glide-offscreen-egl.md](qemu-3dfx-glide-offscreen-egl.md) and is carried in the same
`submodules/qemu-3dfx.patch`; ROADMAP.md, Streaming, "Stage 1b".

## What it does

qemu-3dfx's MESA GL pass-through (`hw/mesa`) makes a GLX context on the VM's SDL window
(`mglcntx_linux.c`), and with any other display (`-display vnc`/`none`/`egl-headless`/`dbus`,
`sdl,gl=on`) the guest's first `wglChoosePixelFormat` ends QEMU in `sdl_display_valid()` (or, with
no X server, in `XOpenDisplay(NULL)` returning NULL). With the change, when the display isn't SDL
without GL (the Glide device's choice, `fxdisp_choose()`, `QEMU_3DFX_OFFSCREEN=1` forces it):

- a new `hw/mesa/mglcntx_egl.c` takes over `mglcntx_linux.c`'s entry points from the guest's DLL
  attach (`MGLTmpContext`) to its detach (`MGLWndRelease`); `mglcntx_linux.c` only gets one
  `if (MGLEglActive()) return MGLEgl...()` line per entry point, so the SDL/GLX path is unchanged;
- libEGL.so.1 is `dlopen()`ed (no new link dependency): a desktop GL context on Mesa's surfaceless
  EGL display (else the first EGL device, else the default display), current on an EGL pbuffer the
  size of the guest's display (the first graphic console's surface, brought up to date with
  `qemu_console_hw_update()` when the window is made, and again at a `wglMakeCurrent` while its
  frames aren't shown). The pbuffer is the window: the guest's framebuffer 0, `GL_BACK` and the
  default viewport are its, so no GL call is rewritten (an FBO in its place would need
  `glBindFramebuffer(..., 0)`, `glDrawBuffer`, `glReadBuffer` and the framebuffer queries
  intercepted). `wglCreateContextAttribsARB` maps to `EGL_KHR_create_context` (same attribute
  bits), the ARB pbuffers to EGL pbuffers, `wglUseFontBitmapsA` to the built-in font
  (`fgFontGenList`, as the SDL-GL backend does), swap intervals to no-ops;
- at every `wglSwapBuffers` the frame is read (`glReadPixels` of framebuffer 0, the guest's read and
  pack state saved and put back; a pbuffer has no swap) and handed to `hw/3dfx/fxdisp.c`, which the
  Glide change added: it now has one instance per device and a read callback. It copies the frame
  into the first graphic console in a main-loop bottom half; `MGLActivateHandler`'s
  `mesa_renderer_stat()` calls (and `mesa_gui_fullscreen()`, which the blitter and the frame
  counter call) go through `MGLRendererStat()`/`MGLGuiFullscreen()`, which switch the console's
  pass-through instead of the SDL window when offscreen, so the VGA comes back when the guest
  deactivates its window or ends its context;
- `wglSetDeviceGammaRamp3DFX` (which the guest's `OPENGL32.DLL` also routes `SetDeviceGammaRamp`
  to) is kept and applied when fxdisp copies a frame (a lookup table on the CPU, only while it
  isn't the identity), as the X server's ramp is with GLX;
- a guest's multisampled pixel format gets a multisampled EGL config only when a 4x4 test pbuffer
  of it gives a clear colour back through the same read; otherwise (Mesa's llvmpipe returns
  `GL_INVALID_OPERATION` for `glReadPixels` of a multisampled pbuffer, and black through a resolving
  `glBlitFramebuffer`) it renders without and says so;
- no libEGL, no EGL display, no config or no context: the guest's `wglChoosePixelFormat` returns 0
  (with the window "ready", so the guest doesn't spin), `wglCreateContext` fails, QEMU prints why and
  keeps running.

Two smaller changes to the Glide side came with it: a frame drawn without a swap (front-buffer
rendering) and followed by no further Glide call is now read 50 ms later on the vCPU thread that
made the last call (`async_run_on_cpu()` from a main-loop timer; the GL context is current there),
where it used to wait for the next call; and OpenGLide's EGL platform keeps the gamma ramp
(`grGammaCorrectionValue`, `grLoadGammaTable`) and applies it in `getOffscreenFrame()`
(`packages/wsh-openglide/patches/0002-egl-offscreen.patch`).

## Evidence

The Windows-free test of this repository (`e2e/3dfx`, `GLIDE_DISPLAY=vnc`): a Linux guest that
speaks the mesapt protocol itself (`mesa-guest.c`: revision handshake, the wgl calls, single GL
calls, `glReadPixels` through the frame memory, `wglSetDeviceGammaRamp3DFX`) draws the test scene;
QEMU has `-display none -vnc`, no X server is installed; the frame is checked in QEMU's screendump
(8 probes, 640x480), then the console's colour after a gamma ramp of 2.0 (0x80 blue to 0xb5), and the
console back at the VGA afterwards. The same run with the Glide guest checks front-buffer drawing
reaching the console with no further call and Glide gamma. Numbers are in ROADMAP.md (Stage 1b).

## Not done

MSAA where the EGL driver can't give a multisampled pbuffer back (llvmpipe, softpipe); GL drawn into
the front buffer without a swap (read only at swaps); following a display mode change while the
frames are shown; the guest cursor (`wglSetDeviceCursor3DFX`) and mouse warps offscreen; Glide on
top of an active GL window (`glide_on_mesa` in the SDL code); macOS and Windows hosts (the EGL path
is Linux only; `mglcntx_egl.h` stubs it out elsewhere). Not tried with a Windows guest or a real
game.
