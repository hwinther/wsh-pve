/*
 * glide-guest: the /init of a minimal Linux guest that drives qemu-3dfx's Glide pass-through, with no
 * Windows and no game. It is linked statically (i386) with qemu-3dfx's own Linux guest wrapper
 * (wrappers/3dfx/dso/glidedso.c, the libglide.so.2 of a Linux guest), which maps the glidept MMIO
 * page and the shared FIFO through /dev/mem and forwards every Glide call to QEMU. QEMU hands the
 * calls to the host's libglide2x.so (wsh-openglide), which renders them into the VM's SDL window, or
 * offscreen into the VM's console when it has no SDL window (VNC).
 *
 * It draws the scene of packages/wsh-openglide/tests/scene.h twice, reads the second frame back
 * through the pass-through (grLfbReadRegion of the back buffer before the swap and of the front
 * buffer after it: host pixels that come back through the shared memory), checks the probes, prints
 * one line per probe (and a coarse map of a frame that doesn't match) and a verdict on the console:
 *
 *   GLIDE-GUEST: PASS | GLIDE-GUEST: FAIL <n> | GLIDE-GUEST: ERROR <what>
 *
 * then holds the frame for a few seconds (for a capture of the window on the host) and powers the
 * VM off. The front-buffer read counts only with GLIDE_GUEST_FRONT=1 on the kernel command line
 * (Mesa's llvmpipe returns black for it, softpipe the frame; see glide-render.c). With
 * GLIDE_GUEST_BENCH=<n>, after the hold it draws the scene <n> more times, a swap each, and prints
 *
 *   GLIDE-GUEST: BENCH <n> frames in <s> s, <fps> fps
 *
 * (the whole round trip: guest wrapper, glidept, the host library and, offscreen, the read of each
 * frame into the console). With GLIDE_GUEST_EXTRA=1 (the headless run), after the hold it also
 * draws into the front buffer without a swap and prints "GLIDE-GUEST: FRONTDRAW", then sets a gamma
 * of 2.0, draws and swaps the scene and prints "GLIDE-GUEST: GAMMA", each held for a few seconds for
 * a screendump on the host. Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "scene.h"

/* The Glide 2 entry points of glidedso.c: every argument is a 32-bit word (pointers too: i386) */
void grGlideInit(void);
void grSstSelect(uint32_t);
uint32_t grSstWinOpen(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
void grBufferClear(uint32_t, uint32_t, uint32_t);
void grDrawTriangle(uint32_t, uint32_t, uint32_t);
void grBufferSwap(uint32_t);
uint32_t grLfbReadRegion(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
void grRenderBuffer(uint32_t);
void grGammaCorrectionValue(uint32_t);
void grSstWinClose(void);
void grGlideShutdown(void);

static uint16_t lfb_back[W * H], lfb_front[W * H], *lfb;
static uint8_t lfb_px(int x, int y, int c)
{
	return rgb565_channel(lfb[y * W + x], c);
}

/* A coarse map of a read-back frame on the console, for the log: one letter per 16x32 pixels
 * (r, g, b: mostly that channel; . the clear colour; space black; ? anything else) */
static void print_map(const char *what)
{
	printf("%s, 40x15:\n", what);
	for (int y = 16; y < H; y += 32) {
		char row[41];
		for (int x = 8, i = 0; x < W; x += 16, i++) {
			int r = lfb_px(x, y, 0), g = lfb_px(x, y, 1), b = lfb_px(x, y, 2);
			row[i] = (r < 16 && g < 16 && b < 16)                 ? ' '
				 : (r < 16 && g < 16 && b > 100 && b < 160) ? '.'
				 : (r > g && r > b)                         ? 'r'
				 : (g > r && g > b)                         ? 'g'
				 : (b > r && b > g)                         ? 'b'
									    : '?';
		}
		row[40] = 0;
		printf("  |%s|\n", row);
	}
}

static void triangle(const float pos[3][2], const float rgb[3][3])
{
	Vertex2 v[3] = {scene_vertex2(pos, rgb, 0), scene_vertex2(pos, rgb, 1), scene_vertex2(pos, rgb, 2)};
	grDrawTriangle((uint32_t)(uintptr_t)&v[0], (uint32_t)(uintptr_t)&v[1], (uint32_t)(uintptr_t)&v[2]);
}

static void finish(const char *verdict, int hold)
{
	printf("GLIDE-GUEST: %s\n", verdict);
	fflush(stdout);
	sync();
	sleep(hold);
	reboot(RB_POWER_OFF);
	for (;;)
		pause();
}

int main(void)
{
	char verdict[64];
	int front = 0, bench = 0, extra = 0;
	const char *env = getenv("GLIDE_GUEST_FRONT"); /* the kernel passes unknown key=value as env */
	if (env && !strcmp(env, "1"))
		front = 1;
	env = getenv("GLIDE_GUEST_EXTRA");
	if (env && !strcmp(env, "1"))
		extra = 1;
	env = getenv("GLIDE_GUEST_BENCH");
	if (env)
		bench = atoi(env);

	mkdir("/dev", 0755);
	if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) && errno != EBUSY)
		finish("ERROR mount devtmpfs", 0);
	/* glidedso.c reads glide.cfg from the working directory, if there is one */
	if (chdir("/"))
		finish("ERROR chdir", 0);
	setvbuf(stdout, NULL, _IOLBF, 0);
	printf("glide-guest: Glide 2 through qemu-3dfx (front-buffer read %s)\n", front ? "counted" : "reported");

	grGlideInit();
	grSstSelect(0);
	if (!grSstWinOpen(0, GR_RESOLUTION_640x480, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB, GR_ORIGIN_UPPER_LEFT, 2, 1))
		finish("ERROR grSstWinOpen (no Glide device, or the host has no libglide2x.so)", 0);
	printf("grSstWinOpen: ok\n");

	/* Frame 1 is checked. Its back buffer is read twice before the swap: first with the frame's
	 * triangles still queued in the FIFO, then again once that read has drained it. qemu-3dfx puts
	 * the pixels of a read that drains queued calls after their data in the shared memory, while
	 * the wrapper copies them from its start (glidept_mm.c sets hshm past the drained data;
	 * glidedso.c, like the Windows wrapper, reads at mdata + ALIGNED(1)): that first read comes
	 * back shifted by the queued data. It is reported, not counted (an upstream matter); the
	 * second one counts. */
	int queued_ok = 0, back_ok = 0, front_ok;
	static uint16_t lfb_queued[W * H];
	for (int frame = 0; frame < 2; frame++) {
		grBufferClear(SCENE_CLEAR, 0xff, 0xffff);
		triangle(red_tri, red_rgb);
		triangle(green_tri, green_rgb);
		triangle(gouraud_tri, gouraud_rgb);
		if (frame == 1) {
			queued_ok = grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, (uint32_t)(uintptr_t)lfb_queued);
			back_ok = grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, (uint32_t)(uintptr_t)lfb_back);
		}
		grBufferSwap(1);
	}
	front_ok = grLfbReadRegion(GR_BUFFER_FRONTBUFFER, 0, 0, W, H, W * 2, (uint32_t)(uintptr_t)lfb_front);

	int failed = 0;
	lfb = lfb_queued;
	if (queued_ok) {
		if (scene_check("guest LFB queue", lfb_px, 0))
			print_map("back buffer, read with calls queued");
	}
	lfb = lfb_back;
	if (!back_ok) {
		printf("FAIL grLfbReadRegion of the back buffer\n");
		failed++;
	} else if (scene_check("guest LFB back", lfb_px, 1)) {
		print_map("back buffer");
		failed++;
	}
	lfb = lfb_front;
	if (!front_ok) {
		printf("%s grLfbReadRegion of the front buffer\n", front ? "FAIL" : "info");
		failed += front;
	} else {
		failed += scene_check("guest LFB front", lfb_px, front) != 0;
	}

	/* the frame stays in the window until the window closes: the host captures it now */
	printf("GLIDE-GUEST: FRAME\n");
	sleep(5);
	if (extra) {
		uint16_t px;
		float g;
		uint32_t gu;
		/* Front-buffer drawing without a swap: a dark red clear, then at once a dark green one, each
		 * followed by a call that flushes the wrapper's FIFO (a 1x1 LFB read), then nothing. The
		 * first is read at once (no read for 5 s); the second comes less than 50 ms after that read
		 * and must still reach the console with no further call (QEMU reads it 50 ms later). */
		grRenderBuffer(GR_BUFFER_FRONTBUFFER);
		grBufferClear(0xff600000, 0xff, 0xffff);
		grLfbReadRegion(GR_BUFFER_FRONTBUFFER, 0, 0, 1, 1, 2, (uint32_t)(uintptr_t)&px);
		grBufferClear(0xff006000, 0xff, 0xffff);
		grLfbReadRegion(GR_BUFFER_FRONTBUFFER, 0, 0, 1, 1, 2, (uint32_t)(uintptr_t)&px);
		printf("GLIDE-GUEST: FRONTDRAW\n");
		sleep(3);
		grRenderBuffer(GR_BUFFER_BACKBUFFER);
		/* Gamma 2.0 (grGammaCorrectionValue): the scene again, the host checks the clear colour */
		g = 2.0f;
		memcpy(&gu, &g, sizeof(gu));
		grGammaCorrectionValue(gu);
		grBufferClear(SCENE_CLEAR, 0xff, 0xffff);
		triangle(red_tri, red_rgb);
		triangle(green_tri, green_rgb);
		triangle(gouraud_tri, gouraud_rgb);
		grBufferSwap(1);
		printf("GLIDE-GUEST: GAMMA\n");
		sleep(3);
		g = 1.0f;
		memcpy(&gu, &g, sizeof(gu));
		grGammaCorrectionValue(gu);
	}
	if (bench > 0) {
		struct timespec t0, t1;
		clock_gettime(CLOCK_MONOTONIC, &t0);
		for (int frame = 0; frame < bench; frame++) {
			grBufferClear(SCENE_CLEAR, 0xff, 0xffff);
			triangle(red_tri, red_rgb);
			triangle(green_tri, green_rgb);
			triangle(gouraud_tri, gouraud_rgb);
			grBufferSwap(0);
		}
		clock_gettime(CLOCK_MONOTONIC, &t1);
		double secs = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
		printf("GLIDE-GUEST: BENCH %d frames in %.2f s, %.1f fps\n", bench, secs, secs > 0 ? bench / secs : 0);
	}
	grSstWinClose();
	grGlideShutdown();
	if (failed)
		snprintf(verdict, sizeof(verdict), "FAIL %d", failed);
	else
		snprintf(verdict, sizeof(verdict), "PASS");
	finish(verdict, 1);
	return 0;
}
