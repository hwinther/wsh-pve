/*
 * glide-render: render a known Glide scene through the host Glide library that qemu-3dfx loads
 * (libglide2x.so / libglide3x.so from wsh-openglide) and check its pixels. No guest, no QEMU.
 *
 *   glide-render [--glide3] [--own-window | --egl] [--no-front] [--ppm FILE]
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
#include <stddef.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>

#include "scene.h"

/* qemu-3dfx glidewnd.c */
#define WRAPPER_FLAG_WINDOWED 0x01
#define WRAPPER_FLAG_QEMU 0x80
#define WRAPPER_FLAG_OFFSCREEN 0x100 /* packages/wsh-openglide/patches/20-egl-offscreen.patch */

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

int main(int argc, char **argv)
{
	int own_window = 0, no_front = 0, egl = 0;
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
	if (egl && own_window) {
		fprintf(stderr, "--egl and --own-window exclude each other\n");
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
