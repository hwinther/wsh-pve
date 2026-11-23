/*
 * glide-render: render a known Glide scene through the host Glide library that qemu-3dfx loads
 * (libglide2x.so / libglide3x.so from wsh-openglide) and check its pixels. No guest, no QEMU.
 *
 *   glide-render [--glide3] [--own-window | --egl [--dmabuf]] [--no-front] [--ppm FILE]
 *   glide-render --check-window WINDOW-ID [--ppm FILE]
 *   glide-render --check-ppm FILE
 *
 * The library is opened the way qemu-3dfx's init_glide2x() opens it: dlopen() of the unversioned
 * name ("libglide2x.so", or "libglide3x.so" for a Glide 3 guest), and every entry point looked up
 * by its plain name, for Glide 3 "wrap3x_<name>" first. Like qemu-3dfx with an SDL display, it
 * calls setConfig() with the QEMU and windowed flags and the '$g2X' signature, and hands
 * grSstWinOpen() an X11 window of its own (QEMU hands it the SDL window's X11 id). --own-window
 * passes 0 instead and lets the library make its window, without setConfig() (a plain Glide app).
 *
 * The scene (scene.h), 640x480: a dark blue clear, a red triangle on the left, a green one on the
 * right and a Gouraud triangle in the middle (red, green and blue corners). It is read back twice:
 * with grLfbReadRegion() (RGB565, the path a guest's LFB read takes) and with XGetImage() of the
 * window (what a screenshot of the display shows). The LFB read is done twice:
 * of the back buffer before the swap and of the front buffer after it. Each probe point must be
 * within a small tolerance of its expected colour. Exit 0 when every probe matches. --no-front
 * reports the front-buffer read without counting it: Mesa's llvmpipe returns black for a front
 * buffer read after a swap of a double-buffered window (softpipe returns the frame), a driver
 * matter rather than the library's.
 *
 * --egl renders offscreen, with no X server: setConfig() gets the offscreen flag as well (what
 * qemu-3dfx passes when the VM has no SDL window), grSstWinOpen() no window, and the frame is read
 * a third way, with getOffscreenFrame() (what qemu-3dfx copies into the VM's console). The front
 * buffer is a framebuffer object's attachment there, so its read counts with every driver.
 * --dmabuf (with --egl) also checks the frame as a GL display gets it: through the dmabuf the
 * library exports (getOffscreenDmabuf, getOffscreenScanout), mapped (or, when it isn't linear,
 * imported through EGL) and compared with the read, without and with a gamma ramp (check_dmabuf).
 *
 * --check-window renders nothing: it checks the probes in an existing 640x480 window, such as the
 * SDL window of a VM whose guest draws the same scene through qemu-3dfx (e2e/3dfx). --check-ppm
 * checks them in a binary PPM (P6) of at least 640x480, such as QEMU's screendump of a VM's console
 * (e2e/3dfx with a VNC display), from its top left corner.
 *
 * Needs an X server (Xvfb with Mesa's llvmpipe in CI), except with --egl and --check-ppm.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <dlfcn.h>
#include <linux/dma-buf.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>

#include "scene.h"

/* qemu-3dfx glidewnd.c */
#define WRAPPER_FLAG_WINDOWED 0x01
#define WRAPPER_FLAG_QEMU 0x80
#define WRAPPER_FLAG_OFFSCREEN 0x100 /* packages/wsh-openglide/patches/0002-egl-offscreen.patch */

/* A Glide 3 vertex of our own layout (grVertexLayout): position, then colour */
typedef struct {
	float x, y;
	float r, g, b;
} Vertex3;

typedef uintptr_t (*fn_open)(uintptr_t, uint32_t, uint32_t, uint32_t, uint32_t, int, int);
static struct {
	void (*GlideInit)(void);
	void (*SstSelect)(int);
	fn_open SstWinOpen;
	void (*BufferClear)(uint32_t, uint8_t, uint16_t);
	void (*DrawTriangle)(const void *, const void *, const void *);
	void (*BufferSwap)(int);
	int (*LfbReadRegion)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, void *);
	void (*VertexLayout)(uint32_t, int32_t, uint32_t);
	void (*SstWinClose2)(void);
	int (*SstWinClose3)(uintptr_t);
	void (*GlideShutdown)(void);
	void (*setConfig)(uint32_t, void *);
	void (*setConfigRes)(int, void *);
	int (*getOffscreenSize)(int *, int *);
	int (*getOffscreenFrame)(void *, int, int, int);
} gr;

static void *lib;
static int glide3;

/* qemu-3dfx's lookup: for a Glide 3 guest the wrap3x_ variant when the library has one */
static void *sym(const char *name, int required)
{
	char wrap[128];
	void *p = NULL;
	if (glide3) {
		snprintf(wrap, sizeof(wrap), "wrap3x_%s", name);
		p = dlsym(lib, wrap);
	}
	if (!p)
		p = dlsym(lib, name);
	if (!p && required) {
		fprintf(stderr, "FAIL: %s has no %s\n", glide3 ? "libglide3x.so" : "libglide2x.so", name);
		exit(2);
	}
	return p;
}

static uint16_t lfb_back[W * H], lfb_front[W * H], *lfb;
static uint8_t lfb_px(int x, int y, int c)
{
	return rgb565_channel(lfb[y * W + x], c);
}

/* An RGB image of W x H or more, rows top down: a getOffscreenFrame() read (flipped) or a PPM */
static uint8_t *rgb_img;
static int rgb_w;
static uint8_t rgb_px(int x, int y, int c)
{
	return rgb_img[((size_t)y * rgb_w + x) * 3 + c];
}

static void write_rgb_ppm(const char *path)
{
	FILE *f = fopen(path, "wb");
	if (!f) {
		perror(path);
		return;
	}
	fprintf(f, "P6\n%d %d\n255\n", W, H);
	for (int y = 0; y < H; y++)
		fwrite(rgb_img + (size_t)y * rgb_w * 3, 1, W * 3, f);
	fclose(f);
}

/* --check-ppm: the probes in a P6 image (QEMU's screendump writes P6, maxval 255) */
static int check_ppm(const char *path)
{
	FILE *f = fopen(path, "rb");
	int w, h, maxval;
	if (!f) {
		perror(path);
		return 2;
	}
	if (fscanf(f, "P6 %d %d %d", &w, &h, &maxval) != 3 || maxval != 255 || fgetc(f) == EOF) {
		fprintf(stderr, "FAIL: %s is not a binary PPM with maxval 255\n", path);
		fclose(f);
		return 2;
	}
	if (w < W || h < H) {
		fprintf(stderr, "FAIL: %s is %dx%d, smaller than %dx%d\n", path, w, h, W, H);
		fclose(f);
		return 1;
	}
	rgb_w = w;
	rgb_img = malloc((size_t)w * h * 3);
	if (!rgb_img || fread(rgb_img, 3, (size_t)w * h, f) != (size_t)w * h) {
		fprintf(stderr, "FAIL: %s is truncated\n", path);
		fclose(f);
		return 2;
	}
	fclose(f);
	int failed = scene_check("screendump", rgb_px, 1);
	printf("%s (%dx%d): %s\n", path, w, h, failed ? "FAILED" : "all probes match");
	return failed ? 1 : 0;
}

static XImage *ximg;
static uint8_t x_px(int x, int y, int c)
{
	unsigned long v = XGetPixel(ximg, x, y);
	unsigned long mask = c == 0 ? ximg->red_mask : c == 1 ? ximg->green_mask : ximg->blue_mask;
	int shift = 0;
	while (mask && !(mask & 1)) {
		mask >>= 1;
		shift++;
	}
	return (uint8_t)(((v >> shift) & mask) * 255 / (mask ? mask : 1));
}

static void write_ppm(const char *path)
{
	FILE *f = fopen(path, "wb");
	if (!f) {
		perror(path);
		return;
	}
	fprintf(f, "P6\n%d %d\n255\n", W, H);
	for (int y = 0; y < H; y++)
		for (int x = 0; x < W; x++) {
			uint8_t rgb[3] = {x_px(x, y, 0), x_px(x, y, 1), x_px(x, y, 2)};
			fwrite(rgb, 1, 3, f);
		}
	fclose(f);
}

static void triangle(const float pos[3][2], const float rgb[3][3])
{
	if (glide3) {
		Vertex3 v[3];
		for (int i = 0; i < 3; i++)
			v[i] = (Vertex3){pos[i][0], pos[i][1], rgb[i][0], rgb[i][1], rgb[i][2]};
		gr.DrawTriangle(&v[0], &v[1], &v[2]);
	} else {
		Vertex2 v[3] = {scene_vertex2(pos, rgb, 0), scene_vertex2(pos, rgb, 1), scene_vertex2(pos, rgb, 2)};
		gr.DrawTriangle(&v[0], &v[1], &v[2]);
	}
}

/* --check-window: the probes in another program's window */
static int check_window(const char *id, const char *ppm)
{
	Display *dpy = XOpenDisplay(NULL);
	if (!dpy) {
		fprintf(stderr, "FAIL: no X display\n");
		return 2;
	}
	Window win = (Window)strtoul(id, NULL, 0);
	XWindowAttributes wa;
	if (!win || !XGetWindowAttributes(dpy, win, &wa)) {
		fprintf(stderr, "FAIL: no window %s\n", id);
		return 2;
	}
	if (wa.width != W || wa.height != H) {
		fprintf(stderr, "FAIL: window %s is %dx%d, not %dx%d\n", id, wa.width, wa.height, W, H);
		return 1;
	}
	ximg = XGetImage(dpy, win, 0, 0, W, H, AllPlanes, ZPixmap);
	if (!ximg) {
		fprintf(stderr, "FAIL: XGetImage of window %s\n", id);
		return 1;
	}
	int failed = scene_check("window", x_px, 1);
	if (ppm)
		write_ppm(ppm);
	printf("window %s: %s\n", id, failed ? "FAILED" : "all probes match");
	return failed ? 1 : 0;
}

/* --dmabuf (with --egl): the frame as qemu-3dfx hands it to a GL display, through the dmabuf the
 * library exports (getOffscreenDmabuf) and fills (getOffscreenScanout), mapped here and compared
 * with getOffscreenFrame()'s read of the same frame, pixel for pixel (both rows bottom up): without
 * a gamma ramp (a blit), with grGammaCorrectionValue(2.0) and, for Glide 3, a table of a different
 * ramp per channel (grLoadGammaTable; the copy is a shader pass then, the read applies the ramp on
 * the CPU), and once more without a ramp. Needs a render node or /dev/udmabuf. */
/* A dmabuf that isn't linear (e.g. NVIDIA's block-linear layout) can't be read through a mapping:
 * it is imported (EGL_EXT_image_dma_buf_import_modifiers) on the library's own EGL display into a
 * texture of a context of ours and read with glReadPixels into egl_pixels (RGBA, the dmabuf's first
 * row first, as a mapping would have it). The library's context is made current again after each
 * read. libEGL is dlopen()ed (glide-render links nothing but libX11 and libdl), so the EGL and GL
 * types and enums are spelled out here. */
typedef void *(*egl_proc_t)(const char *);
static struct {
	void *(*get_current_display)(void);
	void *(*get_current_surface)(int);
	void *(*get_current_context)(void);
	unsigned (*make_current)(void *, void *, void *, void *);
	int (*bind_api)(unsigned);
	int (*query_api)(void);
	void *(*create_context)(void *, void *, void *, const int *);
	int (*destroy_context)(void *, void *);
	void *(*create_image)(void *, void *, unsigned, void *, const int *);
	int (*destroy_image)(void *, void *);
	int (*get_error)(void);
	const char *(*query_string)(void *, int);
	void (*image_target)(unsigned, void *);
	void (*gen_textures)(int, unsigned *);
	void (*bind_texture)(unsigned, unsigned);
	void (*tex_parameteri)(unsigned, unsigned, int);
	void (*gen_framebuffers)(int, unsigned *);
	void (*bind_framebuffer)(unsigned, unsigned);
	void (*framebuffer_texture)(unsigned, unsigned, unsigned, unsigned, int);
	unsigned (*check_framebuffer)(unsigned);
	void (*pixel_storei)(unsigned, int);
	void (*read_pixels)(int, int, int, int, unsigned, unsigned, void *);
	void *dpy, *ctx, *image;
	unsigned tex, fbo;
} ei;
static uint8_t *egl_pixels;

static int egl_switch(int ours, void **saved)
{
	if (ours) {
		saved[0] = ei.get_current_display();
		saved[1] = ei.get_current_surface(0x3059); /* EGL_DRAW */
		saved[2] = ei.get_current_surface(0x305A); /* EGL_READ */
		saved[3] = ei.get_current_context();
		saved[4] = (void *)(intptr_t)ei.query_api();
		return ei.bind_api(0x30A2) && ei.make_current(ei.dpy, NULL, NULL, ei.ctx); /* EGL_OPENGL_API */
	}
	ei.bind_api((unsigned)(intptr_t)saved[4]);
	return ei.make_current(saved[0], saved[1], saved[2], saved[3]);
}

/* 0 and why when the dmabuf can't be imported */
static const char *egl_import(int fd, int stride, int offset, uint32_t fourcc, uint64_t modifier)
{
	void *egl = dlopen("libEGL.so.1", RTLD_NOW), *saved[5];
	egl_proc_t gpa = egl ? (egl_proc_t)dlsym(egl, "eglGetProcAddress") : NULL;
	static char why[128];
	if (!gpa)
		return "no libEGL.so.1";
	/* the core EGL functions from the library, the rest (extensions, GL) through eglGetProcAddress */
#define EI(f, name) *(void **)&ei.f = dlsym(egl, name) ? dlsym(egl, name) : gpa(name)
	EI(get_current_display, "eglGetCurrentDisplay");
	EI(get_current_surface, "eglGetCurrentSurface");
	EI(get_current_context, "eglGetCurrentContext");
	EI(make_current, "eglMakeCurrent");
	EI(bind_api, "eglBindAPI");
	EI(query_api, "eglQueryAPI");
	EI(create_context, "eglCreateContext");
	EI(destroy_context, "eglDestroyContext");
	EI(create_image, "eglCreateImageKHR");
	EI(destroy_image, "eglDestroyImageKHR");
	EI(get_error, "eglGetError");
	EI(query_string, "eglQueryString");
	EI(image_target, "glEGLImageTargetTexture2DOES");
	EI(gen_textures, "glGenTextures");
	EI(bind_texture, "glBindTexture");
	EI(tex_parameteri, "glTexParameteri");
	EI(gen_framebuffers, "glGenFramebuffers");
	EI(bind_framebuffer, "glBindFramebuffer");
	EI(framebuffer_texture, "glFramebufferTexture2D");
	EI(check_framebuffer, "glCheckFramebufferStatus");
	EI(pixel_storei, "glPixelStorei");
	EI(read_pixels, "glReadPixels");
#undef EI
	if (!ei.get_current_display || !ei.make_current || !ei.create_image || !ei.image_target || !ei.read_pixels ||
	    !ei.query_api || !ei.check_framebuffer)
		return "libEGL lacks an entry point";
	ei.dpy = ei.get_current_display();
	const char *exts = ei.dpy ? ei.query_string(ei.dpy, 0x3055) : NULL; /* EGL_EXTENSIONS */
	if (!exts || !strstr(exts, "EGL_EXT_image_dma_buf_import_modifiers") || !strstr(exts, "EGL_KHR_surfaceless_context") ||
	    !strstr(exts, "EGL_KHR_no_config_context"))
		return "the library's EGL display imports no dmabuf with a modifier (or needs a surface or config)";
	static const int none[] = {0x3038};
	ei.ctx = ei.create_context(ei.dpy, NULL, NULL, none);
	if (!ei.ctx || !egl_switch(1, saved)) {
		snprintf(why, sizeof(why), "no context of our own (0x%04x)", ei.get_error());
		return why;
	}
	/* EGL_WIDTH, EGL_HEIGHT, EGL_LINUX_DRM_FOURCC_EXT, plane 0's FD, OFFSET, PITCH, MODIFIER_LO, _HI */
	const int attrs[] = {0x3057, W, 0x3056, H, 0x3271, (int)fourcc, 0x3272, fd, 0x3273, offset, 0x3274, stride,
			     0x3443, (int)(modifier & 0xffffffff), 0x3444, (int)(modifier >> 32), 0x3038};
	ei.image = ei.create_image(ei.dpy, NULL, 0x3270, NULL, attrs); /* EGL_LINUX_DMA_BUF_EXT */
	unsigned status = 0;
	if (ei.image) {
		ei.gen_textures(1, &ei.tex);
		ei.bind_texture(0x0DE1, ei.tex);		/* GL_TEXTURE_2D */
		ei.tex_parameteri(0x0DE1, 0x2801, 0x2600); /* MIN_FILTER NEAREST */
		ei.tex_parameteri(0x0DE1, 0x2800, 0x2600); /* MAG_FILTER NEAREST */
		ei.image_target(0x0DE1, ei.image);
		ei.gen_framebuffers(1, &ei.fbo);
		ei.bind_framebuffer(0x8D40, ei.fbo);				  /* GL_FRAMEBUFFER */
		ei.framebuffer_texture(0x8D40, 0x8CE0, 0x0DE1, ei.tex, 0); /* COLOR_ATTACHMENT0 */
		status = ei.check_framebuffer(0x8D40);
	} else
		snprintf(why, sizeof(why), "eglCreateImage 0x%04x", ei.get_error());
	egl_switch(0, saved);
	if (!ei.image)
		return why;
	if (status != 0x8CD5) { /* GL_FRAMEBUFFER_COMPLETE */
		snprintf(why, sizeof(why), "framebuffer incomplete (0x%04x)", status);
		return why;
	}
	egl_pixels = malloc((size_t)W * H * 4);
	return egl_pixels ? NULL : "out of memory";
}

static int egl_read(void)
{
	void *saved[5];
	if (!egl_switch(1, saved))
		return 0;
	ei.pixel_storei(0x0D05, 1);					      /* GL_PACK_ALIGNMENT */
	ei.read_pixels(0, 0, W, H, 0x1908, 0x1401, egl_pixels); /* GL_RGBA, GL_UNSIGNED_BYTE */
	return egl_switch(0, saved);
}

static void egl_release(void)
{
	void *saved[5];
	if (ei.image && egl_switch(1, saved)) {
		ei.destroy_image(ei.dpy, ei.image);
		egl_switch(0, saved);
	}
	if (ei.ctx)
		ei.destroy_context(ei.dpy, ei.ctx);
	free(egl_pixels);
	egl_pixels = NULL;
}

#define FOURCC(a, b, c, d) ((uint32_t)(a) | ((uint32_t)(b) << 8) | ((uint32_t)(c) << 16) | ((uint32_t)(d) << 24))

static int dmabuf_compare(const char *what, uint32_t want, const uint8_t *map, int stride, uint32_t fourcc, int fd,
			  int (*frame)(void *, int, int, int), int (*scanout)(void))
{
	static uint8_t bgrx[W * H * 4];
	struct dma_buf_sync sync = {0};
	/* the dmabuf's bytes for red, green, blue */
	int ri = 0, gi = 1, bi = 2, diffs = 0, maxd = 0;
	if (fourcc == FOURCC('A', 'R', '2', '4') || fourcc == FOURCC('X', 'R', '2', '4'))
		ri = 2, bi = 0;
	if (!scanout()) {
		fprintf(stderr, "FAIL: dmabuf %s: getOffscreenScanout refused the frame\n", what);
		return 1;
	}
	if (!frame(bgrx, W, H, W * 4)) {
		fprintf(stderr, "FAIL: dmabuf %s: getOffscreenFrame\n", what);
		return 1;
	}
	if (egl_pixels) {
		/* imported, not mapped: read now that the copy is finished (glReadPixels gives RGBA) */
		if (!egl_read()) {
			fprintf(stderr, "FAIL: dmabuf %s: the imported dmabuf can't be read\n", what);
			return 1;
		}
		map = egl_pixels, stride = W * 4, ri = 0, bi = 2;
	}
	sync.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ;
	ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync);
	for (int y = 0; y < H; y++)
		for (int x = 0; x < W; x++) {
			const uint8_t *d = map + (size_t)y * stride + x * 4, *f = bgrx + ((size_t)y * W + x) * 4;
			int dr = abs(d[ri] - f[2]), dg = abs(d[gi] - f[1]), db = abs(d[bi] - f[0]);
			int m = dr > dg ? (dr > db ? dr : db) : (dg > db ? dg : db);
			if (m) {
				if (!diffs)
					fprintf(stderr, "dmabuf %s: first difference at (%d, %d) from the bottom: "
						"dmabuf #%02x%02x%02x, read #%02x%02x%02x\n", what, x, y,
						d[ri], d[gi], d[bi], f[2], f[1], f[0]);
				diffs++;
				maxd = m > maxd ? m : maxd;
			}
		}
	sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
	ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync);
	/* the clear colour at the top left (the last row in memory), for the log */
	const uint8_t *tl = map + (size_t)(H - 1) * stride;
	printf("dmabuf %s: top left #%02x%02x%02x, %d of %d pixels differ from the read (max %d)\n", what,
	       tl[ri], tl[gi], tl[bi], diffs, W * H, maxd);
	if (diffs)
		fprintf(stderr, "FAIL: dmabuf %s: the dmabuf isn't the frame getOffscreenFrame reads\n", what);
	uint32_t got = ((uint32_t)tl[ri] << 16) | ((uint32_t)tl[gi] << 8) | tl[bi];
	if (abs((int)(got >> 16) - (int)(want >> 16)) > 1 || abs((int)((got >> 8) & 0xff) - (int)((want >> 8) & 0xff)) > 1 ||
	    abs((int)(got & 0xff) - (int)(want & 0xff)) > 1) {
		fprintf(stderr, "FAIL: dmabuf %s: top left #%06x, not #%06x\n", what, got, want);
		diffs++;
	}
	return diffs ? 1 : 0;
}

static int check_dmabuf(void)
{
	int (*dmabuf)(int *, int *, int *, unsigned int *, unsigned long *) = sym("getOffscreenDmabuf", 0);
	int (*scanout)(void) = sym("getOffscreenScanout", 0);
	void (*gamma)(float) = sym("grGammaCorrectionValue", 1);
	void (*table)(uint32_t, uint32_t *, uint32_t *, uint32_t *) = glide3 ? sym("grLoadGammaTable", 0) : NULL;
	int fd = -1, stride = 0, offset = 0, failed = 0;
	unsigned int fourcc = 0;
	unsigned long modifier = 0;
	if (!dmabuf || !scanout) {
		fprintf(stderr, "FAIL: the library has no getOffscreenDmabuf/getOffscreenScanout\n");
		return 1;
	}
	if (!dmabuf(&fd, &stride, &offset, &fourcc, &modifier)) {
		fprintf(stderr, "FAIL: getOffscreenDmabuf (no render node and no /dev/udmabuf?)\n");
		return 1;
	}
	printf("dmabuf: fd %d, stride %d, offset %d, fourcc %.4s, modifier 0x%lx\n", fd, stride, offset,
	       (const char *)&fourcc, modifier);
	if (fourcc != FOURCC('A', 'B', '2', '4') && fourcc != FOURCC('X', 'B', '2', '4') &&
	    fourcc != FOURCC('A', 'R', '2', '4') && fourcc != FOURCC('X', 'R', '2', '4')) {
		printf("info: not a 32-bit RGB dmabuf (fourcc %.4s): not verified\n", (const char *)&fourcc);
		close(fd);
		return 0;
	}
	size_t len = (size_t)offset + (size_t)stride * H;
	uint8_t *map;
	/* DRM_FORMAT_MOD_LINEAR, or DRM_FORMAT_MOD_INVALID (none given): mapped; another modifier (or
	 * GLIDE_RENDER_IMPORT=egl, that path with llvmpipe): imported through EGL */
	const char *env = getenv("GLIDE_RENDER_IMPORT");
	if ((modifier != 0 && modifier != 0x00ffffffffffffffUL) || (env && !strcmp(env, "egl"))) {
		const char *why = egl_import(fd, stride, offset, fourcc, modifier);
		if (why) {
			printf("info: modifier 0x%lx: not verified (the EGL import failed: %s)\n", modifier, why);
			egl_release();
			close(fd);
			return 0;
		}
		printf("dmabuf: modifier 0x%lx, imported through EGL and read with glReadPixels\n", modifier);
		map = egl_pixels;
		offset = 0;
	} else
		map = mmap(NULL, len, PROT_READ, MAP_SHARED, fd, 0);
	if (map == MAP_FAILED) {
		perror("FAIL: mmap of the dmabuf");
		close(fd);
		return 1;
	}
	failed += dmabuf_compare("without a ramp", 0x000080, map + offset, stride, fourcc, fd, gr.getOffscreenFrame, scanout);
	gamma(2.0f);
	failed += dmabuf_compare("gamma 2.0", 0x0000b5, map + offset, stride, fourcc, fd, gr.getOffscreenFrame, scanout);
	if (table) {
		/* red gamma 2.0, green inverted, blue halved */
		static uint32_t r[256], g[256], b[256];
		for (int i = 0; i < 256; i++) {
			uint32_t k = 0; /* round(255 * sqrt(i / 255)) = round(sqrt(255 * i)) */
			while ((2 * k + 1) * (2 * k + 1) <= 4u * 255 * i)
				k++;
			r[i] = k;
			g[i] = 255 - i;
			b[i] = i / 2;
		}
		table(256, r, g, b);
		failed += dmabuf_compare("a table per channel", 0x00ff40, map + offset, stride, fourcc, fd, gr.getOffscreenFrame,
					 scanout);
	}
	gamma(1.0f);
	failed += dmabuf_compare("the ramp reset", 0x000080, map + offset, stride, fourcc, fd, gr.getOffscreenFrame, scanout);
	if (egl_pixels)
		egl_release();
	else
		munmap(map, len);
	close(fd);
	return failed;
}

int main(int argc, char **argv)
{
	int own_window = 0, no_front = 0, egl = 0, dmabuf = 0;
	const char *ppm = NULL, *window_id = NULL, *check = NULL;
	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--glide3"))
			glide3 = 1;
		else if (!strcmp(argv[i], "--own-window"))
			own_window = 1;
		else if (!strcmp(argv[i], "--egl"))
			egl = 1;
		else if (!strcmp(argv[i], "--check-ppm") && i + 1 < argc)
			check = argv[++i];
		else if (!strcmp(argv[i], "--dmabuf"))
			dmabuf = 1;
		else if (!strcmp(argv[i], "--no-front"))
			no_front = 1;
		else if (!strcmp(argv[i], "--ppm") && i + 1 < argc)
			ppm = argv[++i];
		else if (!strcmp(argv[i], "--check-window") && i + 1 < argc)
			window_id = argv[++i];
		else {
			fprintf(stderr,
				"usage: %s [--glide3] [--own-window | --egl] [--no-front] [--ppm FILE]\n"
				"       %s --check-window WINDOW-ID [--ppm FILE]\n"
				"       %s --check-ppm FILE\n",
				argv[0], argv[0], argv[0]);
			return 2;
		}
	}
	if (window_id)
		return check_window(window_id, ppm);
	if (check)
		return check_ppm(check);
	if ((egl && own_window) || (dmabuf && !egl)) {
		fprintf(stderr, "--egl and --own-window exclude each other, --dmabuf needs --egl\n");
		return 2;
	}
	const char *soname = glide3 ? "libglide3x.so" : "libglide2x.so";
	lib = dlopen(soname, RTLD_NOW);
	if (!lib) {
		fprintf(stderr, "FAIL: dlopen(%s): %s\n", soname, dlerror());
		return 2;
	}
	printf("loaded %s\n", soname);

	gr.GlideInit = sym("grGlideInit", 1);
	gr.SstSelect = sym("grSstSelect", 1);
	gr.SstWinOpen = (fn_open)sym("grSstWinOpen", 1);
	gr.BufferClear = sym("grBufferClear", 1);
	gr.DrawTriangle = sym("grDrawTriangle", 1);
	gr.BufferSwap = sym("grBufferSwap", 1);
	gr.LfbReadRegion = sym("grLfbReadRegion", 1);
	gr.GlideShutdown = sym("grGlideShutdown", 1);
	gr.setConfig = sym("setConfig", 1);
	gr.setConfigRes = sym("setConfigRes", 1);
	if (egl) {
		gr.getOffscreenSize = sym("getOffscreenSize", 1);
		gr.getOffscreenFrame = sym("getOffscreenFrame", 1);
	}
	if (glide3) {
		gr.VertexLayout = sym("grVertexLayout", 1);
		gr.SstWinClose3 = sym("grSstWinClose", 1);
	} else {
		gr.SstWinClose2 = sym("grSstWinClose", 1);
	}

	Display *dpy = NULL;
	if (!egl) {
		dpy = XOpenDisplay(NULL);
		if (!dpy) {
			fprintf(stderr, "FAIL: no X display (DISPLAY=%s)\n", getenv("DISPLAY") ? getenv("DISPLAY") : "");
			return 2;
		}
	}

	Window win = 0;
	if (!own_window && !egl) {
		/* the stand-in for QEMU's SDL window */
		win = XCreateSimpleWindow(dpy, DefaultRootWindow(dpy), 0, 0, W, H, 0, 0, 0);
		XSelectInput(dpy, win, StructureNotifyMask);
		XMapWindow(dpy, win);
		for (XEvent ev;;) {
			XNextEvent(dpy, &ev);
			if (ev.type == MapNotify)
				break;
		}
	}

	gr.GlideInit();
	gr.SstSelect(0);
	if (!own_window) {
		uint32_t sign = 0x58326724; /* '$g2X': qemu-3dfx's conf_glide2x() */
		gr.setConfig(WRAPPER_FLAG_QEMU | WRAPPER_FLAG_WINDOWED | (egl ? WRAPPER_FLAG_OFFSCREEN : 0), &sign);
		gr.setConfigRes(0, NULL);
		if (sign == 0x324c4453)
			printf("note: the library signs as SDL2 (built with SDL): qemu-3dfx would hand it the SDL window\n");
	}
	uintptr_t ctx = gr.SstWinOpen((uintptr_t)win, GR_RESOLUTION_640x480, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB,
				      GR_ORIGIN_UPPER_LEFT, 2, 1);
	if (!ctx) {
		fprintf(stderr, "FAIL: grSstWinOpen\n");
		return 1;
	}
	printf("grSstWinOpen: ok (%s)\n", egl ? "offscreen" : own_window ? "the library's window" : "our window");

	if (glide3) {
		gr.VertexLayout(GR_PARAM_XY, (int32_t)offsetof(Vertex3, x), GR_PARAM_ENABLE);
		gr.VertexLayout(GR_PARAM_RGB, (int32_t)offsetof(Vertex3, r), GR_PARAM_ENABLE);
	}

	/* two frames: the second one is checked, in the back buffer before its swap and in the front
	 * buffer after it */
	int failed = 0, back_ok = 0, front_ok;
	for (int frame = 0; frame < 2; frame++) {
		gr.BufferClear(SCENE_CLEAR, 0xff, 0xffff);
		triangle(red_tri, red_rgb);
		triangle(green_tri, green_rgb);
		triangle(gouraud_tri, gouraud_rgb);
		if (frame == 1)
			back_ok = gr.LfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, lfb_back);
		gr.BufferSwap(1);
	}
	front_ok = gr.LfbReadRegion(GR_BUFFER_FRONTBUFFER, 0, 0, W, H, W * 2, lfb_front);

	lfb = lfb_back;
	if (!back_ok) {
		fprintf(stderr, "FAIL: grLfbReadRegion of the back buffer\n");
		failed++;
	} else {
		failed += scene_check("LFB back", lfb_px, 1);
	}
	lfb = lfb_front;
	if (!front_ok) {
		fprintf(stderr, "%s: grLfbReadRegion of the front buffer\n", no_front ? "info" : "FAIL");
		failed += !no_front;
	} else {
		failed += scene_check("LFB front", lfb_px, !no_front);
	}

	if (egl) {
		int w = 0, h = 0;
		static uint8_t bgrx[W * H * 4];
		if (!gr.getOffscreenSize(&w, &h) || w != W || h != H) {
			fprintf(stderr, "FAIL: getOffscreenSize: %dx%d, not %dx%d\n", w, h, W, H);
			failed++;
		} else if (!gr.getOffscreenFrame(bgrx, W, H, W * 4)) {
			fprintf(stderr, "FAIL: getOffscreenFrame\n");
			failed++;
		} else {
			/* B G R X, rows bottom up */
			rgb_w = W;
			rgb_img = malloc(W * H * 3);
			for (int y = 0; y < H; y++)
				for (int x = 0; x < W; x++)
					for (int c = 0; c < 3; c++)
						rgb_img[(y * W + x) * 3 + c] = bgrx[((H - 1 - y) * W + x) * 4 + 2 - c];
			failed += scene_check("offscreen frame", rgb_px, 1);
			if (ppm)
				write_rgb_ppm(ppm);
			if (dmabuf)
				failed += check_dmabuf();
		}
	} else if (!own_window) {
		XSync(dpy, False);
		ximg = XGetImage(dpy, win, 0, 0, W, H, AllPlanes, ZPixmap);
		if (!ximg) {
			fprintf(stderr, "FAIL: XGetImage\n");
			failed++;
		} else {
			failed += scene_check("X11 window", x_px, 1);
			if (ppm)
				write_ppm(ppm);
		}
	}

	if (glide3)
		gr.SstWinClose3(ctx);
	else
		gr.SstWinClose2();
	gr.GlideShutdown();
	printf("%s: %s\n", glide3 ? "glide3x" : "glide2x", failed ? "FAILED" : "all probes match");
	return failed ? 1 : 0;
}
