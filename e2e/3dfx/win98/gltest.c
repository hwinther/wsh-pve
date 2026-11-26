/*
 * gltest.exe: the Mesa/OpenGL pass-through of qemu-3dfx from a Windows 98 guest, with no game. As a
 * game does, it switches the display to 640x480, opens a window over it and loads OPENGL32.DLL from
 * its own directory: qemu-3dfx's guest wrapper, which has to sit next to the program (Windows'
 * own OPENGL32.DLL in C:\WINDOWS\SYSTEM is a software renderer). It checks that the wrapper is the
 * one that got loaded, makes a WGL context (wglChoosePixelFormat, wglSetPixelFormat,
 * wglCreateContext, wglMakeCurrent of the wrapper), draws the scene of
 * packages/wsh-openglide/tests/scene.h with glBegin/glColor3f/glVertex2f (as e2e/3dfx/mesa-guest.c
 * does from a Linux guest), reads the back buffer of the second frame with glReadPixels before the
 * swap, checks the probes and prints
 *
 *   OPENGL: FRAME                   the frame is up: the host checks the VM's console now
 *
 * then holds it (hold=<s>, 5 by default), draws bench=<n> more frames for a frame rate (OPENGL:
 * BENCH ...), deletes the context, puts the display mode back and prints its verdict:
 *
 *   OPENGL: PASS | OPENGL: FAIL <n> | OPENGL: ERROR <what>, then OPENGL: CLOSED
 *
 * With ctx2=1 (the harness's test opengl-ctx, tag GLCTX) it first does what Return Fire 2 does when
 * it goes from its intro to the game: a second wglCreateContext while the first context is current,
 * wglMakeCurrent of the new one and wglDeleteContext of the old one. Then it checks the pixel-store
 * state a new context has (glGetIntegerv of GL_UNPACK_ALIGNMENT and the rest, with the outputs
 * preset, so an output the call never wrote shows), and, only when that state is sane, builds a
 * 256x256 RGB texture's mipmaps with gluBuild2DMipmaps of Windows' own GLU32.DLL (which divides by
 * GL_UNPACK_ALIGNMENT: a 0 there is the divide error the game hit). The scene is then drawn with the
 * new context as above. Windows' GLU32.DLL is loaded from C:\WINDOWS\SYSTEM at run time; without it
 * that step is skipped.
 *
 * Exit status 0 PASS, 1 FAIL, 2 ERROR. See w3d.h for the output and the build. Copyright 2026
 * WsHosting ENK, GPL-3.
 */
#include "w3d.h"
#define printf w3d_printf
#include "scene.h"

#define GL_COLOR_BUFFER_BIT 0x4000
#define GL_DEPTH_BUFFER_BIT 0x0100
#define GL_TRIANGLES 0x0004
#define GL_RGBA 0x1908
#define GL_UNSIGNED_BYTE 0x1401
#define GL_BACK 0x0405
#define GL_VENDOR 0x1F00
#define GL_RENDERER 0x1F01
#define GL_VERSION 0x1F02
#define GL_PACK_ALIGNMENT 0x0D05
#define GL_PACK_ROW_LENGTH 0x0D02
#define GL_UNPACK_ROW_LENGTH 0x0CF2
#define GL_UNPACK_SKIP_ROWS 0x0CF3
#define GL_UNPACK_SKIP_PIXELS 0x0CF4
#define GL_UNPACK_ALIGNMENT 0x0CF5
#define GL_MAX_TEXTURE_SIZE 0x0D33
#define GL_TEXTURE_2D 0x0DE1
#define GL_RGB 0x1907

static struct {
	int(WINAPI *ChoosePixelFormat)(HDC, const PIXELFORMATDESCRIPTOR *);
	BOOL(WINAPI *SetPixelFormat)(HDC, int, const PIXELFORMATDESCRIPTOR *);
	HGLRC(WINAPI *CreateContext)(HDC);
	BOOL(WINAPI *MakeCurrent)(HDC, HGLRC);
	BOOL(WINAPI *DeleteContext)(HGLRC);
	BOOL(WINAPI *SwapBuffers)(HDC);
} wgl;
static struct {
	void(WINAPI *Viewport)(int, int, int, int);
	void(WINAPI *ClearColor)(float, float, float, float);
	void(WINAPI *Clear)(uint32_t);
	void(WINAPI *Begin)(uint32_t);
	void(WINAPI *End)(void);
	void(WINAPI *Color3f)(float, float, float);
	void(WINAPI *Vertex2f)(float, float);
	void(WINAPI *ReadBuffer)(uint32_t);
	void(WINAPI *PixelStorei)(uint32_t, int);
	void(WINAPI *ReadPixels)(int, int, int, int, uint32_t, uint32_t, void *);
	void(WINAPI *Finish)(void);
	const char *(WINAPI *GetString)(uint32_t);
	void(WINAPI *GetIntegerv)(uint32_t, int *);
	uint32_t(WINAPI *GetError)(void);
	void(WINAPI *GenTextures)(int, uint32_t *);
	void(WINAPI *BindTexture)(uint32_t, uint32_t);
	void(WINAPI *DeleteTextures)(int, const uint32_t *);
} gl;

static HMODULE lib;
static HWND wnd;
static HDC hdc;
static HGLRC ctx;
static int mode_changed;

static void cleanup(void)
{
	if (ctx) {
		wgl.MakeCurrent(NULL, NULL);
		wgl.DeleteContext(ctx);
		ctx = NULL;
	}
	if (hdc)
		ReleaseDC(wnd, hdc);
	hdc = NULL;
	if (wnd)
		DestroyWindow(wnd);
	wnd = NULL;
	if (mode_changed)
		ChangeDisplaySettingsA(NULL, 0);
	mode_changed = 0;
}

static void finish(const char *verdict, int status)
{
	cleanup();
	w3d_printf("%s", verdict);
	w3d_printf("CLOSED");
	w3d_com_release();
	ExitProcess(status);
}

static FARPROC sym(const char *name)
{
	FARPROC p = GetProcAddress(lib, name);
	if (!p) {
		char what[128];
		wsprintfA(what, "ERROR OPENGL32.DLL has no %s", name);
		finish(what, 2);
	}
	return p;
}

static uint8_t pixels[W * H * 4];
static uint8_t read_px(int x, int y, int c)
{
	return pixels[((H - 1 - y) * W + x) * 4 + c]; /* GL rows go bottom up */
}

/* What a game's switch from one context to another (Return Fire 2's, from its intro to the game)
 * does: a second context while the first one is current, made current, the first one deleted.
 * Windows gives the new context; a wrapper that returned NULL left the game without one. */
static int context_switch(void)
{
	HGLRC second = wgl.CreateContext(hdc);
	if (!second) {
		w3d_printf("info: a second wglCreateContext while a context is current returned NULL (Windows gives one)");
		/* what the game did next: its NULL made current, the first context deleted */
		wgl.MakeCurrent(hdc, NULL);
		wgl.DeleteContext(ctx);
		ctx = NULL;
		return 1;
	}
	if (!wgl.MakeCurrent(hdc, second)) {
		w3d_printf("info: wglMakeCurrent of the second context failed");
		wgl.DeleteContext(second);
		return 1;
	}
	if (second != ctx)
		wgl.DeleteContext(ctx);
	ctx = second;
	w3d_printf("context switch: second context %08lx made current, the first one deleted", (unsigned long)(uintptr_t)second);
	return 0;
}

/* The pixel-store state of a new context, as GLU's gluScaleImage and gluBuild2DMipmaps read it.
 * Each output is preset: a call that never writes it (no GL context on the host) shows. */
static int pixel_store_state(void)
{
	static const struct {
		uint32_t pname;
		const char *name;
		int want; /* -1: at least 256 */
	} st[] = {
		{ GL_UNPACK_ALIGNMENT, "GL_UNPACK_ALIGNMENT", 4 },
		{ GL_UNPACK_ROW_LENGTH, "GL_UNPACK_ROW_LENGTH", 0 },
		{ GL_UNPACK_SKIP_ROWS, "GL_UNPACK_SKIP_ROWS", 0 },
		{ GL_UNPACK_SKIP_PIXELS, "GL_UNPACK_SKIP_PIXELS", 0 },
		{ GL_PACK_ALIGNMENT, "GL_PACK_ALIGNMENT", 4 },
		{ GL_PACK_ROW_LENGTH, "GL_PACK_ROW_LENGTH", 0 },
		{ GL_MAX_TEXTURE_SIZE, "GL_MAX_TEXTURE_SIZE", -1 },
	};
	int bad = 0;
	for (unsigned i = 0; i < sizeof(st) / sizeof(st[0]); i++) {
		int v = 0x5eedf00d;
		gl.GetIntegerv(st[i].pname, &v);
		int ok = (st[i].want < 0) ? (v >= 256 && v != 0x5eedf00d) : (v == st[i].want);
		if (v == 0x5eedf00d)
			w3d_printf("state: %s not written by glGetIntegerv (no GL context?)", st[i].name);
		else
			w3d_printf("state: %s %d%s", st[i].name, v, ok ? "" : " (wrong)");
		bad += !ok;
	}
	return bad;
}

/* gluBuild2DMipmaps of Windows' own GLU32.DLL, as the game calls it: a 256x256 RGB texture */
static uint8_t texels[256 * 256 * 3];
static int glu_mipmaps(void)
{
	HMODULE glu = LoadLibraryA("GLU32.DLL");
	if (!glu) {
		w3d_printf("info: no GLU32.DLL (error %lu): gluBuild2DMipmaps skipped", GetLastError());
		return 0;
	}
	int(WINAPI * build2d)(uint32_t, int, int, int, uint32_t, uint32_t, const void *);
	*(FARPROC *)&build2d = GetProcAddress(glu, "gluBuild2DMipmaps");
	if (!build2d) {
		w3d_printf("info: GLU32.DLL has no gluBuild2DMipmaps: skipped");
		FreeLibrary(glu);
		return 0;
	}
	for (int i = 0; i < 256 * 256; i++) {
		texels[i * 3] = (uint8_t)i;
		texels[i * 3 + 1] = (uint8_t)(i >> 8);
		texels[i * 3 + 2] = 0x80;
	}
	uint32_t tex = 0;
	gl.GetError();
	gl.GenTextures(1, &tex);
	gl.BindTexture(GL_TEXTURE_2D, tex);
	int r = build2d(GL_TEXTURE_2D, 3, 256, 256, GL_RGB, GL_UNSIGNED_BYTE, texels);
	uint32_t err = gl.GetError();
	gl.BindTexture(GL_TEXTURE_2D, 0);
	gl.DeleteTextures(1, &tex);
	FreeLibrary(glu);
	w3d_printf("glu: gluBuild2DMipmaps 256x256 GL_RGB returned %d, glGetError 0x%04x", r, err);
	return (r != 0) || (err != 0);
}

static void triangle(const float pos[3][2], const float rgb[3][3])
{
	gl.Begin(GL_TRIANGLES);
	for (int i = 0; i < 3; i++) {
		gl.Color3f(rgb[i][0] / 255, rgb[i][1] / 255, rgb[i][2] / 255);
		/* scene.h's 640x480 upper-left coordinates to normalised device coordinates */
		gl.Vertex2f(pos[i][0] / (W / 2) - 1, 1 - pos[i][1] / (H / 2));
	}
	gl.End();
}

static void scene(void)
{
	gl.ClearColor(0, 0, 0x80 / 255.0f, 1);
	gl.Clear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
	triangle(red_tri, red_rgb);
	triangle(green_tri, green_rgb);
	triangle(gouraud_tri, gouraud_rgb);
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
	if (m == WM_SETCURSOR) {
		SetCursor(NULL);
		return TRUE;
	}
	return DefWindowProcA(h, m, w, l);
}

void WinMainCRTStartup(void)
{
	char verdict[160];
	int hold = w3d_arg_int("hold", 5), bench = w3d_arg_int("bench", 0), ctx2 = w3d_arg_int("ctx2", 0);
	w3d_tag = ctx2 ? "GLCTX" : "OPENGL";
	w3d_com_hold();
	w3d_printf("START OPENGL32.DLL from %s, 640x480, hold %d s, bench %d frames", W3D_DIR, hold, bench);

	/* The display to 640x480, as a full-screen game sets it: the pass-through's frame takes the size
	 * of the guest's display */
	DEVMODEA dm;
	memset(&dm, 0, sizeof(dm));
	dm.dmSize = sizeof(dm);
	dm.dmPelsWidth = W;
	dm.dmPelsHeight = H;
	dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
	LONG r = ChangeDisplaySettingsA(&dm, CDS_FULLSCREEN);
	if (r != DISP_CHANGE_SUCCESSFUL)
		w3d_printf("info: ChangeDisplaySettings to 640x480: %ld (the screen is %dx%d)", r,
			   GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
	else
		mode_changed = 1;

	WNDCLASSA wc;
	memset(&wc, 0, sizeof(wc));
	wc.style = CS_OWNDC;
	wc.lpfnWndProc = wndproc;
	wc.hInstance = GetModuleHandleA(NULL);
	wc.lpszClassName = "W3DGL";
	RegisterClassA(&wc);
	wnd = CreateWindowExA(WS_EX_TOPMOST, "W3DGL", "gltest", WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
			      0, 0, W, H, NULL, NULL, wc.hInstance, NULL);
	if (!wnd)
		finish("ERROR CreateWindow", 2);
	SetForegroundWindow(wnd);
	w3d_pump(200);
	hdc = GetDC(wnd);

	uint32_t t0 = w3d_ms();
	lib = LoadLibraryA("OPENGL32.DLL");
	if (!lib) {
		wsprintfA(verdict, "ERROR LoadLibrary OPENGL32.DLL: error %lu (the wrapper refuses a host of another revision)",
			  GetLastError());
		finish(verdict, 2);
	}
	char path[MAX_PATH];
	GetModuleFileNameA(lib, path, sizeof(path));
	w3d_printf("loaded %s in %u ms", path, w3d_ms() - t0);
	if (CharUpperA(path) && memcmp(path, W3D_DIR "\\", sizeof(W3D_DIR)))
		finish("ERROR Windows' own OPENGL32.DLL was loaded, not qemu-3dfx's wrapper next to the program", 2);

	*(FARPROC *)&wgl.ChoosePixelFormat = sym("wglChoosePixelFormat");
	*(FARPROC *)&wgl.SetPixelFormat = sym("wglSetPixelFormat");
	*(FARPROC *)&wgl.CreateContext = sym("wglCreateContext");
	*(FARPROC *)&wgl.MakeCurrent = sym("wglMakeCurrent");
	*(FARPROC *)&wgl.DeleteContext = sym("wglDeleteContext");
	*(FARPROC *)&wgl.SwapBuffers = sym("wglSwapBuffers");
	*(FARPROC *)&gl.Viewport = sym("glViewport");
	*(FARPROC *)&gl.ClearColor = sym("glClearColor");
	*(FARPROC *)&gl.Clear = sym("glClear");
	*(FARPROC *)&gl.Begin = sym("glBegin");
	*(FARPROC *)&gl.End = sym("glEnd");
	*(FARPROC *)&gl.Color3f = sym("glColor3f");
	*(FARPROC *)&gl.Vertex2f = sym("glVertex2f");
	*(FARPROC *)&gl.ReadBuffer = sym("glReadBuffer");
	*(FARPROC *)&gl.PixelStorei = sym("glPixelStorei");
	*(FARPROC *)&gl.ReadPixels = sym("glReadPixels");
	*(FARPROC *)&gl.Finish = sym("glFinish");
	*(FARPROC *)&gl.GetString = sym("glGetString");
	*(FARPROC *)&gl.GetIntegerv = sym("glGetIntegerv");
	*(FARPROC *)&gl.GetError = sym("glGetError");
	*(FARPROC *)&gl.GenTextures = sym("glGenTextures");
	*(FARPROC *)&gl.BindTexture = sym("glBindTexture");
	*(FARPROC *)&gl.DeleteTextures = sym("glDeleteTextures");

	PIXELFORMATDESCRIPTOR pfd;
	memset(&pfd, 0, sizeof(pfd));
	pfd.nSize = sizeof(pfd);
	pfd.nVersion = 1;
	pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
	pfd.iPixelType = PFD_TYPE_RGBA;
	pfd.cColorBits = 32;
	pfd.cDepthBits = 24;
	pfd.iLayerType = PFD_MAIN_PLANE;
	t0 = w3d_ms();
	int fmt = wgl.ChoosePixelFormat(hdc, &pfd);
	if (!fmt)
		finish("ERROR wglChoosePixelFormat", 2);
	if (!wgl.SetPixelFormat(hdc, fmt, &pfd))
		finish("ERROR wglSetPixelFormat", 2);
	ctx = wgl.CreateContext(hdc);
	if (!ctx)
		finish("ERROR wglCreateContext (the host can't make a GL context: no SDL window and no offscreen EGL)", 2);
	if (!wgl.MakeCurrent(hdc, ctx))
		finish("ERROR wglMakeCurrent", 2);
	w3d_printf("context: pixel format %d, made current in %u ms", fmt, w3d_ms() - t0);
	const char *s;
	if ((s = gl.GetString(GL_VENDOR)))
		w3d_printf("GL_VENDOR %s", s);
	if ((s = gl.GetString(GL_RENDERER)))
		w3d_printf("GL_RENDERER %s", s);
	if ((s = gl.GetString(GL_VERSION)))
		w3d_printf("GL_VERSION %s", s);

	int failed = 0;
	if (ctx2) {
		if (context_switch()) {
			int bad = pixel_store_state(); /* what GLU then read: outputs never written */
			w3d_printf("info: the context switch left no context (%d of the state not right)", bad);
			finish("FAIL 1", 1);
		}
		int bad = pixel_store_state();
		if (bad)
			failed += bad; /* GLU would divide by a GL_UNPACK_ALIGNMENT of 0: not called */
		else
			failed += glu_mipmaps();
	}

	gl.Viewport(0, 0, W, H);
	for (int frame = 0; frame < 2; frame++) {
		scene();
		if (frame == 1) {
			gl.Finish();
			gl.ReadBuffer(GL_BACK);
			gl.PixelStorei(GL_PACK_ALIGNMENT, 4);
			gl.ReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
		}
		wgl.SwapBuffers(hdc);
	}
	if (scene_check("guest glReadPixels", read_px, 1)) {
		w3d_print_map("back buffer", read_px, W, H);
		failed++;
	}

	/* the frame stays in the console until the next swap or the context's end: check it now */
	w3d_printf("FRAME");
	w3d_pump((uint32_t)hold * 1000);
	if (bench > 0) {
		t0 = w3d_ms();
		for (int frame = 0; frame < bench; frame++) {
			scene();
			wgl.SwapBuffers(hdc);
		}
		uint32_t ms = w3d_ms() - t0, fps10 = w3d_fps10((uint32_t)bench, ms);
		w3d_printf("BENCH %d frames in %u ms, %u.%u fps", bench, ms, fps10 / 10, fps10 % 10);
	}
	cleanup();
	FreeLibrary(lib);
	if (failed)
		wsprintfA(verdict, "FAIL %d", failed);
	else
		lstrcpyA(verdict, "PASS");
	finish(verdict, failed ? 1 : 0);
}
