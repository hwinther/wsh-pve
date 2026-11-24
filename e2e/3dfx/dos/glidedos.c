/*
 * GLIDEDOS.EXE: the Glide pass-through of qemu-3dfx from DOS (FreeDOS), with no game. A DJGPP program
 * linked with libfxgl2.a, the import library dxe3gen makes next to qemu-3dfx's DOS wrapper
 * GLIDE2X.DXE (wrappers/3dfx/dxe): the library's stubs load GLIDE2X.DXE (dlopen, found through
 * LD_LIBRARY_PATH) on the first Glide call, as in a DJGPP Glide game. The wrapper maps the glidept
 * MMIO page and the shared FIFO by their physical addresses through the DPMI host (CWSDPMI) and
 * forwards every Glide call to QEMU, which renders it with the host's libglide2x.so (wsh-openglide),
 * offscreen into the VM's console when the VM has no SDL window (VNC, as PVE runs it).
 *
 * It draws the scene of packages/wsh-openglide/tests/scene.h, as e2e/3dfx/glide-guest.c does from a
 * Linux guest: a dark blue clear, a red and a green triangle and a Gouraud one. It reads the second
 * frame back through the pass-through (grLfbReadRegion of the back buffer before the swap, twice:
 * the first read, with the frame's calls still queued, comes back shifted, see glide-guest.c; and of
 * the front buffer after it, reported only), checks the probes and prints
 *
 *   GLIDEDOS: FRAME                 the frame is up: the host checks the VM's console now
 *
 * then holds the frame (hold=<s>, 5 by default), draws bench=<n> more frames for a frame rate
 * (GLIDEDOS: BENCH <n> frames in <ms> ms, <fps> fps), closes the Glide window and prints its verdict:
 *
 *   GLIDEDOS: PASS | GLIDEDOS: FAIL <n> | GLIDEDOS: ERROR <what>, then GLIDEDOS: CLOSED
 *
 * on standard output, which the test's batch file sends to COM1 (CTTY COM1). Exit status 0 PASS,
 * 1 FAIL, 2 ERROR. Built by build.sh in the DJGPP image (djgpp.Dockerfile).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "scene.h"

/* The Glide 2 entry points of glidedxe.c (cdecl; every argument is a 32-bit word, pointers too) */
void grGlideInit(void);
void grGlideGetVersion(uint32_t);
void grSstSelect(uint32_t);
uint32_t grSstWinOpen(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
void grBufferClear(uint32_t, uint32_t, uint32_t);
void grDrawTriangle(uint32_t, uint32_t, uint32_t);
void grBufferSwap(uint32_t);
uint32_t grLfbReadRegion(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
void grSstWinClose(void);
void grGlideShutdown(void);

static uint16_t lfb_queued[W * H], lfb_back[W * H], lfb_front[W * H], *lfb;
static uint8_t lfb_px(int x, int y, int c)
{
	return rgb565_channel(lfb[y * W + x], c);
}

static void finish(const char *verdict, int status)
{
	printf("GLIDEDOS: %s\n", verdict);
	printf("GLIDEDOS: CLOSED\n");
	fflush(stdout);
	exit(status);
}

/* A coarse map of a read-back frame, for the log (see glide-guest.c) */
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

static void scene(void)
{
	grBufferClear(SCENE_CLEAR, 0xff, 0xffff);
	triangle(red_tri, red_rgb);
	triangle(green_tri, green_rgb);
	triangle(gouraud_tri, gouraud_rgb);
}

int main(int argc, char **argv)
{
	int hold = 5, bench = 0;
	char verdict[64], version[80];
	for (int i = 1; i < argc; i++) {
		if (!strncmp(argv[i], "hold=", 5))
			hold = atoi(argv[i] + 5);
		else if (!strncmp(argv[i], "bench=", 6))
			bench = atoi(argv[i] + 6);
	}
	setvbuf(stdout, NULL, _IOLBF, 0);
	printf("glidedos: Glide 2 through qemu-3dfx's GLIDE2X.DXE (DJGPP), hold %d s, bench %d\n", hold, bench);

	/* The import library's stubs dlopen() the wrapper on the first call and abort the program when
	 * it isn't there; open it first to say why. The stubs then get the same, already loaded, module. */
	void *dxe = dlopen("glide2x.dxe", RTLD_GLOBAL);
	if (!dxe) {
		snprintf(verdict, sizeof(verdict), "ERROR dlopen glide2x.dxe: %.36s", dlerror());
		finish(verdict, 2);
	}
	printf("dlopen glide2x.dxe: ok\n");

	memset(version, 0, sizeof(version));
	grGlideInit();
	grGlideGetVersion((uint32_t)(uintptr_t)version);
	version[sizeof(version) - 1] = 0;
	/* The wrapper's grGlideGetVersion() returns without a word when its Init() failed (the MMIO not
	 * mapped, or the host refused the handshake: another revision); every other call would then
	 * write through a null pointer */
	if (!version[0])
		finish("ERROR no Glide device (the wrapper's handshake with glidept failed: mapping or revision)", 2);
	printf("grGlideGetVersion: %s\n", version);
	grSstSelect(0);
	if (!grSstWinOpen(0, GR_RESOLUTION_640x480, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB, GR_ORIGIN_UPPER_LEFT, 2, 1))
		finish("ERROR grSstWinOpen (no Glide device, a wrapper of another revision, or no libglide2x.so on the host)", 2);
	printf("grSstWinOpen: ok\n");

	int queued_ok = 0, back_ok = 0, front_ok;
	for (int frame = 0; frame < 2; frame++) {
		scene();
		if (frame == 1) {
			queued_ok = grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, (uint32_t)(uintptr_t)lfb_queued);
			back_ok = grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, (uint32_t)(uintptr_t)lfb_back);
		}
		grBufferSwap(1);
	}
	front_ok = grLfbReadRegion(GR_BUFFER_FRONTBUFFER, 0, 0, W, H, W * 2, (uint32_t)(uintptr_t)lfb_front);

	int failed = 0;
	lfb = lfb_queued;
	if (queued_ok && scene_check("guest LFB queue", lfb_px, 0))
		print_map("back buffer, read with calls queued");
	lfb = lfb_back;
	if (!back_ok) {
		printf("FAIL grLfbReadRegion of the back buffer\n");
		failed++;
	} else if (scene_check("guest LFB back", lfb_px, 1)) {
		print_map("back buffer");
		failed++;
	}
	lfb = lfb_front;
	if (!front_ok)
		printf("info grLfbReadRegion of the front buffer\n");
	else
		scene_check("guest LFB front", lfb_px, 0);

	/* the frame stays in the console until the window closes: the host checks it now */
	printf("GLIDEDOS: FRAME\n");
	fflush(stdout);
	sleep(hold);

	if (bench > 0) {
		uclock_t t0 = uclock();
		for (int frame = 0; frame < bench; frame++) {
			scene();
			grBufferSwap(0);
		}
		uclock_t t1 = uclock();
		double ms = (double)(t1 - t0) * 1000.0 / UCLOCKS_PER_SEC;
		printf("GLIDEDOS: BENCH %d frames in %.0f ms, %.1f fps\n", bench, ms, ms > 0 ? bench * 1000.0 / ms : 0);
	}
	grSstWinClose();
	grGlideShutdown();
	if (failed)
		snprintf(verdict, sizeof(verdict), "FAIL %d", failed);
	else
		snprintf(verdict, sizeof(verdict), "PASS");
	finish(verdict, failed ? 1 : 0);
	return 0;
}
