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
	int hold = w3d_arg_int("hold", 5), bench = w3d_arg_int("bench", 0);
	w3d_tag = "OPENGL";
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
	int failed = 0;
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
