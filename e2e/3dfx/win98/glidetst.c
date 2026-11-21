/*
 * glidetst.exe: the Glide pass-through of qemu-3dfx from a Windows 98 guest, with no game. It loads
 * GLIDE2X.DLL (or GLIDE3X.DLL with the argument "glide3": qemu-3dfx's guest wrappers in
 * C:\WINDOWS\SYSTEM) with LoadLibrary, opens a 640x480 Glide window and draws the scene of
 * packages/wsh-openglide/tests/scene.h, as e2e/3dfx/glide-guest.c does from a Linux guest: a dark
 * blue clear, a red and a green triangle and a Gouraud one. It reads the second frame back through
 * the pass-through (grLfbReadRegion of the back buffer before the swap, twice: the first read, with
 * the frame's calls still queued, comes back shifted, see glide-guest.c; and of the front buffer
 * after it, reported only), checks the probes and prints
 *
 *   GLIDE2: FRAME                   the frame is up: the host checks the VM's console now
 *
 * then holds the frame (hold=<s>, 5 by default), draws bench=<n> more frames for a frame rate
 * (GLIDE2: BENCH <n> frames in <ms> ms, <fps> fps), closes the Glide window and prints its verdict:
 *
 *   GLIDE2: PASS | GLIDE2: FAIL <n> | GLIDE2: ERROR <what>, then GLIDE2: CLOSED
 *
 * (GLIDE3 for Glide 3). Exit status 0 PASS, 1 FAIL, 2 ERROR. See w3d.h for the output and the build.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include "w3d.h"
#define printf w3d_printf
#include "scene.h"

#include <stddef.h>

/* A Glide 3 vertex of our own layout (grVertexLayout): position, then colour, as glide-render.c */
typedef struct {
	float x, y;
	float r, g, b;
} Vertex3;

typedef void(__stdcall *fn_v)(void);
typedef void(__stdcall *fn_u)(uint32_t);
typedef uint32_t(__stdcall *fn_open)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
typedef void(__stdcall *fn_clear)(uint32_t, uint32_t, uint32_t);
typedef void(__stdcall *fn_tri)(const void *, const void *, const void *);
typedef uint32_t(__stdcall *fn_read)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, void *);
typedef void(__stdcall *fn_layout)(uint32_t, int32_t, uint32_t);
typedef uint32_t(__stdcall *fn_close3)(uint32_t);

static struct {
	fn_v GlideInit, GlideShutdown, SstWinClose2;
	fn_u SstSelect, BufferSwap;
	fn_open SstWinOpen;
	fn_clear BufferClear;
	fn_tri DrawTriangle;
	fn_read LfbReadRegion;
	fn_layout VertexLayout;
	fn_close3 SstWinClose3;
} gr;

static HMODULE lib;
static int glide3;
static const char *dll;

static void finish(const char *verdict, int status)
{
	w3d_printf("%s", verdict);
	w3d_printf("CLOSED");
	w3d_com_release();
	ExitProcess(status);
}

/* An export of the wrapper: stdcall names are decorated (_name@bytes); try the plain one too */
static FARPROC sym(const char *name, int argbytes)
{
	char dec[96];
	wsprintfA(dec, "_%s@%d", name, argbytes);
	FARPROC p = GetProcAddress(lib, dec);
	if (!p)
		p = GetProcAddress(lib, name);
	if (!p) {
		char what[128];
		wsprintfA(what, "ERROR %s has no %s", dll, name);
		finish(what, 2);
	}
	return p;
}

static void triangle(const float pos[3][2], const float rgb[3][3])
{
	if (glide3) {
		Vertex3 v[3];
		for (int i = 0; i < 3; i++) {
			v[i].x = pos[i][0];
			v[i].y = pos[i][1];
			v[i].r = rgb[i][0];
			v[i].g = rgb[i][1];
			v[i].b = rgb[i][2];
		}
		gr.DrawTriangle(&v[0], &v[1], &v[2]);
	} else {
		Vertex2 v[3] = {scene_vertex2(pos, rgb, 0), scene_vertex2(pos, rgb, 1), scene_vertex2(pos, rgb, 2)};
		gr.DrawTriangle(&v[0], &v[1], &v[2]);
	}
}

static void scene(void)
{
	gr.BufferClear(SCENE_CLEAR, 0xff, 0xffff);
	triangle(red_tri, red_rgb);
	triangle(green_tri, green_rgb);
	triangle(gouraud_tri, gouraud_rgb);
}

static uint16_t lfb_queued[W * H], lfb_back[W * H], lfb_front[W * H], *lfb;
static uint8_t lfb_px(int x, int y, int c)
{
	return rgb565_channel(lfb[y * W + x], c);
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
	if (m == WM_SETCURSOR) {
		SetCursor(NULL);
		return TRUE;
	}
	return DefWindowProcA(h, m, w, l);
}

/* A game's window: a black popup over the whole screen, in front (the Glide frame doesn't depend on
 * it: qemu-3dfx shows Glide in place of the VGA picture) */
static HWND game_window(void)
{
	WNDCLASSA wc;
	memset(&wc, 0, sizeof(wc));
	wc.lpfnWndProc = wndproc;
	wc.hInstance = GetModuleHandleA(NULL);
	wc.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
	wc.lpszClassName = "W3DGLIDE";
	RegisterClassA(&wc);
	HWND h = CreateWindowExA(WS_EX_TOPMOST, "W3DGLIDE", "glidetst", WS_POPUP | WS_VISIBLE, 0, 0,
				 GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN), NULL, NULL, wc.hInstance, NULL);
	if (h) {
		SetForegroundWindow(h);
		w3d_pump(100);
	}
	return h;
}

void WinMainCRTStartup(void)
{
	char verdict[64];
	glide3 = w3d_arg_flag("glide3");
	int hold = w3d_arg_int("hold", 5), bench = w3d_arg_int("bench", 0), counted_front = w3d_arg_flag("front");
	w3d_tag = glide3 ? "GLIDE3" : "GLIDE2";
	dll = glide3 ? "GLIDE3X.DLL" : "GLIDE2X.DLL";
	w3d_com_hold();
	w3d_printf("START %s, 640x480, hold %d s, bench %d frames (front-buffer read %s)", dll, hold, bench,
		   counted_front ? "counted" : "reported");

	uint32_t t0 = w3d_ms();
	lib = LoadLibraryA(dll);
	if (!lib) {
		wsprintfA(verdict, "ERROR LoadLibrary %s: error %lu", dll, GetLastError());
		finish(verdict, 2);
	}
	w3d_printf("loaded %s in %u ms", dll, w3d_ms() - t0);
	gr.GlideInit = (fn_v)sym("grGlideInit", 0);
	gr.GlideShutdown = (fn_v)sym("grGlideShutdown", 0);
	gr.SstSelect = (fn_u)sym("grSstSelect", 4);
	gr.SstWinOpen = (fn_open)sym("grSstWinOpen", 28);
	gr.BufferClear = (fn_clear)sym("grBufferClear", 12);
	gr.DrawTriangle = (fn_tri)sym("grDrawTriangle", 12);
	gr.BufferSwap = (fn_u)sym("grBufferSwap", 4);
	gr.LfbReadRegion = (fn_read)sym("grLfbReadRegion", 28);
	if (glide3) {
		gr.VertexLayout = (fn_layout)sym("grVertexLayout", 12);
		gr.SstWinClose3 = (fn_close3)sym("grSstWinClose", 4);
	} else {
		gr.SstWinClose2 = (fn_v)sym("grSstWinClose", 0);
	}

	HWND wnd = game_window();
	gr.GlideInit();
	gr.SstSelect(0);
	t0 = w3d_ms();
	uint32_t ctx = gr.SstWinOpen((uint32_t)(uintptr_t)wnd, GR_RESOLUTION_640x480, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB,
				     GR_ORIGIN_UPPER_LEFT, 2, 1);
	if (!ctx)
		finish("ERROR grSstWinOpen (no Glide device: the host has no libglide2x.so/libglide3x.so or can't render)", 2);
	w3d_printf("grSstWinOpen: ok in %u ms", w3d_ms() - t0);
	if (glide3) {
		gr.VertexLayout(GR_PARAM_XY, (int32_t)offsetof(Vertex3, x), GR_PARAM_ENABLE);
		gr.VertexLayout(GR_PARAM_RGB, (int32_t)offsetof(Vertex3, r), GR_PARAM_ENABLE);
	}

	/* Frame 1 is checked: its back buffer twice before the swap, the front buffer after it */
	uint32_t queued_ok = 0, back_ok = 0, front_ok;
	for (int frame = 0; frame < 2; frame++) {
		scene();
		if (frame == 1) {
			queued_ok = gr.LfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, lfb_queued);
			back_ok = gr.LfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, W, H, W * 2, lfb_back);
		}
		gr.BufferSwap(1);
	}
	front_ok = gr.LfbReadRegion(GR_BUFFER_FRONTBUFFER, 0, 0, W, H, W * 2, lfb_front);

	int failed = 0;
	lfb = lfb_queued;
	if (queued_ok && scene_check("guest LFB queue", lfb_px, 0))
		w3d_print_map("back buffer, read with calls queued", lfb_px, W, H);
	lfb = lfb_back;
	if (!back_ok) {
		w3d_printf("FAIL grLfbReadRegion of the back buffer");
		failed++;
	} else if (scene_check("guest LFB back", lfb_px, 1)) {
		w3d_print_map("back buffer", lfb_px, W, H);
		failed++;
	}
	lfb = lfb_front;
	if (!front_ok) {
		w3d_printf("%s grLfbReadRegion of the front buffer", counted_front ? "FAIL" : "info");
		failed += counted_front;
	} else {
		failed += scene_check("guest LFB front", lfb_px, counted_front) != 0;
	}

	/* the frame stays in the console until the Glide window closes: the host checks it now */
	w3d_printf("FRAME");
	w3d_pump((uint32_t)hold * 1000);
	if (bench > 0) {
		t0 = w3d_ms();
		for (int frame = 0; frame < bench; frame++) {
			scene();
			gr.BufferSwap(0);
		}
		uint32_t ms = w3d_ms() - t0, fps10 = w3d_fps10((uint32_t)bench, ms);
		w3d_printf("BENCH %d frames in %u ms, %u.%u fps", bench, ms, fps10 / 10, fps10 % 10);
	}
	if (glide3)
		gr.SstWinClose3(ctx);
	else
		gr.SstWinClose2();
	gr.GlideShutdown();
	if (wnd)
		DestroyWindow(wnd);
	FreeLibrary(lib);
	if (failed)
		wsprintfA(verdict, "FAIL %d", failed);
	else
		lstrcpyA(verdict, "PASS");
	finish(verdict, failed ? 1 : 0);
}
