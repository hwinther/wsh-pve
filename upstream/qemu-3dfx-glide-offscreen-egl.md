# qemu-3dfx and OpenGLide: Glide without an SDL window (EGL offscreen, frames into the console)

Material for the owner, who decides whether and how to offer it to kjliew (qemu-3dfx and qemu-xtra
are his projects; nothing has been sent or posted, and the code was written with an AI assistant,
which he may not want). Carried here as `submodules/qemu-3dfx.patch` (qemu-3dfx side) and
`packages/wsh-openglide/patches/0002-egl-offscreen.patch` (OpenGLide side); ROADMAP.md, Streaming,
"Stage 1".

## What it does

qemu-3dfx's Glide device renders through OpenGLide into the VM's SDL window, and any other display
(`-display vnc`/`none`/`egl-headless`/`dbus`, `sdl,gl=on`) ends QEMU in `sdl_display_valid()`. With
the change, when the display isn't SDL without GL:

- qemu-3dfx passes a new `setConfig()` flag, `WRAPPER_FLAG_OFFSCREEN` (0x100), and opens the Glide
  window synchronously (no SDL timer, `stat_window` returns 0 at once);
- OpenGLide's Linux platform then opens no X display: a desktop GL compatibility context on an EGL
  display without a window (`EGL_MESA_platform_surfaceless`, else `EGL_EXT_platform_device`, else
  the default display), made current without a surface (`EGL_KHR_surfaceless_context`, else a 1x1
  pbuffer), rendering into a framebuffer object whose colour attachments 0 and 1 stand for Glide's
  back and front buffers (`OGLBuffer()` maps `GL_BACK`/`GL_FRONT` at the four places OpenGLide
  selects a buffer). `grBufferSwap` blits back to front. Two new exports, `getOffscreenSize` and
  `getOffscreenFrame`, read the front buffer (BGRX, bottom up);
- qemu-3dfx (`hw/3dfx/fxdisp.c`) reads the frame after each swap on the vCPU thread and copies it in
  a main-loop bottom half into a surface of its own on the first graphic console, which is put in
  pass-through (the existing `graphic_hw_passthrough()`); on close the console is invalidated and the
  VGA redraws;
- a library without the exports, or an EGL failure, makes `grSstWinOpen` fail instead of ending QEMU.

The SDL/GLX path is unchanged. A side effect worth mentioning: offscreen, the front-buffer read
after a swap returns the frame with Mesa's llvmpipe too (with GLX on a double-buffered window it
returns black there).

## Evidence

The Windows-free test of this repository (`e2e/3dfx`): a Linux guest drawing a Glide 2 scene through
qemu-3dfx's `glidedso.c`, QEMU with `-display none -vnc`, no X server installed; the frame checked in
QEMU's screendump (8 probes, 640x480) and the console back at the VGA's 720x400 afterwards. TCG,
Mesa llvmpipe: a frame read takes about 0.2 ms at 640x480.

## Later additions

With the MESA GL pass-through's offscreen path ([qemu-3dfx-mesa-offscreen-egl.md](qemu-3dfx-mesa-offscreen-egl.md)),
`fxdisp.c` got one instance per device with a read callback; Glide gamma offscreen (OpenGLide's EGL
platform keeps the ramp of `grGammaCorrectionValue`/`grLoadGammaTable` and applies it in
`getOffscreenFrame()`); and front-buffer drawing whose last call is followed by no other is read
50 ms later on the vCPU thread that made it (`async_run_on_cpu()` from a main-loop timer), where it
used to wait for the next Glide call.

dmabuf scanout (ROADMAP, "Stage 2"; `packages/wsh-openglide/patches/0003-egl-dmabuf-scanout.patch`):
two more exports, `getOffscreenDmabuf()` (a third renderbuffer exported once through
`EGL_MESA_image_dma_buf_export`) and `getOffscreenScanout()` (the front buffer blitted into it,
`glFinish`), which `fxdisp.c` hands to a GL display (`qemu_console_gl_scanout_dmabuf`) instead of
reading the frame back. Since wsh-openglide 0.6 a frame with a gamma ramp stays a dmabuf too: the
copy is then a shader pass (front buffer into a texture, drawn through a 256x1 lookup texture) in a
second EGL context that shares OpenGLide's objects, and the copies are finished with an EGL fence
(`EGL_KHR_fence_sync`, a client wait) where the driver has one, `glFinish` otherwise. Two things in it are not qemu-3dfx's and might interest QEMU or Mesa
people, should the owner want to mention them: QEMU's egl-headless took every dmabuf as top down
(`egl_scanout_dmabuf()` passed `false` for `y0_top`), and an EGL platform display is one handle per
process, so a library that calls `eglTerminate` on Mesa's surfaceless display also destroys the
host program's contexts on it (OpenGLide and the MESA GL path no longer terminate it).

## Not done

MSAA offscreen (`ContextMSAA`: the framebuffer object's buffers are single-sampled; multisampled
ones would need a resolve before every LFB read and swap); Windows and macOS (only OpenGLide's
Linux platform has the EGL path).
