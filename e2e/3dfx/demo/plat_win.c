/*
 * wshdemo's Windows front end (9x/ME/2000/XP), one WSHDEMO.EXE for the three APIs: Glide 2
 * (GLIDE2X.DLL), Glide 3 (GLIDE3X.DLL) and OpenGL (qemu-3dfx's OPENGL32.DLL, which has to sit next
 * to the program: Windows' own in the system directory is a software renderer). -api glide2|glide3|
 * opengl picks one; without it a small window asks.
 *
 * Built like the Windows 98 test programs (e2e/3dfx/win98, w3d.h): mingw-w64 without its C runtime
 * (Windows 98's MSVCRT.DLL is too old for it), its own entry point, KERNEL32, USER32 and GDI32 only,
 * and the DLLs loaded with LoadLibrary. Output goes to COM1 (115200 8N1) and to C:\WIN3DFX\LOG.TXT
 * when that directory exists (w3d.h). Keys come from the 3D window (a popup over the screen).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include "w3d.h"

#include "demo.h"
#include "gl11.h"
#include "glide2.h"
#include "glide3.h"

static HMODULE lib;
static const char *lib_name, *tagname = "WSHDEMO";
static HWND wnd;
static int keys[32], key_head, key_tail;

/* --- output, time, keys ------------------------------------------------------------------------- */

void plat_out(const char *line)
{
	w3d_line(line);
}

uint32_t plat_us(void)
{
	static double scale;
	LARGE_INTEGER f, c;
	if (scale == 0)
		scale = QueryPerformanceFrequency(&f) && f.QuadPart ? 1e6 / (double)f.QuadPart : -1;
	if (scale > 0 && QueryPerformanceCounter(&c))
		return (uint32_t)(int64_t)((double)c.QuadPart * scale);
	return GetTickCount() * 1000U;
}

static void pump(void)
{
	MSG msg;
	while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
		TranslateMessage(&msg);
		DispatchMessageA(&msg);
	}
}

int plat_key(void)
{
	pump();
	if (key_head == key_tail)
		return -1;
	int k = keys[key_tail];
	key_tail = (key_tail + 1) % 32;
	return k;
}

void plat_sleep(int ms)
{
	uint32_t end = GetTickCount() + (uint32_t)ms;
	do {
		pump();
		Sleep(ms < 10 ? (DWORD)ms : 10);
	} while ((int32_t)(end - GetTickCount()) > 0);
}

static void push_key(int k)
{
	int next = (key_head + 1) % 32;
	if (next != key_tail)
		keys[key_head] = k, key_head = next;
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
	switch (m) {
	case WM_SETCURSOR:
		SetCursor(NULL);
		return TRUE;
	case WM_CHAR:
		push_key((int)(w & 0xff));
		return 0;
	case WM_CLOSE:
		push_key(27);
		return 0;
	}
	return DefWindowProcA(h, m, w, l);
}

/* The 3D window: a black popup in front, over the screen (w x h with OpenGL, which takes the
 * window's size; the Glide frame doesn't depend on it) */
static HWND make_window(int w, int h)
{
	static int registered;
	HINSTANCE hi = GetModuleHandleA(NULL);
	if (!registered) {
		WNDCLASSA wc;
		memset(&wc, 0, sizeof(wc));
		wc.style = CS_OWNDC;
		wc.lpfnWndProc = wndproc;
		wc.hInstance = hi;
		wc.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
		wc.lpszClassName = "WSHDEMO";
		RegisterClassA(&wc);
		registered = 1;
	}
	HWND hw = CreateWindowExA(WS_EX_TOPMOST, "WSHDEMO", "wshdemo", WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
				  0, 0, w, h, NULL, NULL, hi, NULL);
	if (hw) {
		SetForegroundWindow(hw);
		SetFocus(hw);
		plat_sleep(100);
	}
	return hw;
}

/* --- the wrapper's build string ----------------------------------------------------------------- */

int plat_wrapper_rev(char *buf, int n)
{
	if (!lib)
		return 0;
	const uint8_t *base = (const uint8_t *)lib;
	const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)base;
	const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
	const IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
	for (int i = 0; i < nt->FileHeader.NumberOfSections; i++)
		if ((s[i].Characteristics & IMAGE_SCN_MEM_READ) && !(s[i].Characteristics & IMAGE_SCN_MEM_EXECUTE) &&
		    demo_find_buildstr(base + s[i].VirtualAddress, s[i].Misc.VirtualSize, buf, n))
			return 1;
	return 0;
}

/* --- loading the wrapper ------------------------------------------------------------------------ */

static void fail(const char *what, int status)
{
	char line[200];
	wsprintfA(line, "%s: ERROR %s", tagname, what);
	w3d_line(line);
	wsprintfA(line, "%s: CLOSED", tagname);
	w3d_line(line);
	w3d_com_release();
	ExitProcess((UINT)status);
}

/* An export: stdcall names are decorated (_name@bytes) in the Glide DLLs; the plain one too */
static FARPROC sym(const char *name, int argbytes)
{
	char dec[96], what[160];
	wsprintfA(dec, "_%s@%d", name, argbytes);
	FARPROC p = GetProcAddress(lib, dec);
	if (!p)
		p = GetProcAddress(lib, name);
	if (!p) {
		wsprintfA(what, "%s has no %s", lib_name, name);
		fail(what, 2);
	}
	return p;
}

static void load(const char *name)
{
	char what[160];
	lib_name = name;
	lib = LoadLibraryA(name);
	if (!lib) {
		wsprintfA(what, "LoadLibrary %s: error %lu (not installed, or the wrapper refuses a host of another revision)", name,
			  GetLastError());
		fail(what, 2);
	}
}

/* --- OpenGL: the window, the display mode and the context ---------------------------------------- */

static struct {
	int(WINAPI *ChoosePixelFormat)(HDC, const PIXELFORMATDESCRIPTOR *);
	BOOL(WINAPI *SetPixelFormat)(HDC, int, const PIXELFORMATDESCRIPTOR *);
	HGLRC(WINAPI *CreateContext)(HDC);
	BOOL(WINAPI *MakeCurrent)(HDC, HGLRC);
	BOOL(WINAPI *DeleteContext)(HGLRC);
	BOOL(WINAPI *SwapBuffers)(HDC);
	PROC(WINAPI *GetProcAddress)(LPCSTR);
} wgl;
static HDC hdc;
static HGLRC ctx;
static int mode_changed, cur_interval = -1;
static BOOL(WINAPI *swap_interval)(int);
static BOOL(WINAPI *set_gamma)(HDC, LPVOID);

int glw_open(int w, int h)
{
	DEVMODEA dm;
	memset(&dm, 0, sizeof(dm));
	dm.dmSize = sizeof(dm);
	dm.dmPelsWidth = (DWORD)w;
	dm.dmPelsHeight = (DWORD)h;
	dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
	LONG r = ChangeDisplaySettingsA(&dm, CDS_FULLSCREEN);
	if (r == DISP_CHANGE_SUCCESSFUL)
		mode_changed = 1;
	else
		demo_log("INFO ChangeDisplaySettings to %dx%d: %d (the screen is %dx%d)", w, h, (int)r, GetSystemMetrics(SM_CXSCREEN),
			 GetSystemMetrics(SM_CYSCREEN));
	wnd = make_window(w, h);
	if (!wnd)
		return -1;
	hdc = GetDC(wnd);
	PIXELFORMATDESCRIPTOR pfd;
	memset(&pfd, 0, sizeof(pfd));
	pfd.nSize = sizeof(pfd);
	pfd.nVersion = 1;
	pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
	pfd.iPixelType = PFD_TYPE_RGBA;
	pfd.cColorBits = 32;
	pfd.cDepthBits = 24;
	pfd.iLayerType = PFD_MAIN_PLANE;
	int fmt = wgl.ChoosePixelFormat(hdc, &pfd);
	if (!fmt || !wgl.SetPixelFormat(hdc, fmt, &pfd)) {
		demo_log("INFO wglChoosePixelFormat/wglSetPixelFormat failed");
		return -1;
	}
	ctx = wgl.CreateContext(hdc);
	if (!ctx || !wgl.MakeCurrent(hdc, ctx)) {
		demo_log("INFO wglCreateContext/wglMakeCurrent failed (the host can't make a GL context)");
		return -1;
	}
	*(PROC *)&swap_interval = wgl.GetProcAddress("wglSwapIntervalEXT");
	*(FARPROC *)&set_gamma = GetProcAddress(lib, "wglSetDeviceGammaRamp3DFX");
	if (!set_gamma)
		*(PROC *)&set_gamma = wgl.GetProcAddress("wglSetDeviceGammaRamp3DFX");
	cur_interval = -1;
	return 0;
}

void glw_close(int final)
{
	if (ctx) {
		wgl.MakeCurrent(NULL, NULL);
		wgl.DeleteContext(ctx);
	}
	ctx = NULL;
	if (hdc)
		ReleaseDC(wnd, hdc);
	hdc = NULL;
	if (wnd)
		DestroyWindow(wnd);
	wnd = NULL;
	if (final && mode_changed)
		ChangeDisplaySettingsA(NULL, 0);
	if (final)
		mode_changed = 0;
	pump();
}

void glw_swap(int vsync)
{
	if (swap_interval && cur_interval != vsync) {
		swap_interval(vsync);
		cur_interval = vsync;
	}
	wgl.SwapBuffers(hdc);
}

int glw_gamma(const uint16_t ramp[3][256])
{
	return set_gamma && set_gamma(hdc, (LPVOID)ramp);
}

static void load_gl(void)
{
	load("OPENGL32.DLL");
	/* qemu-3dfx's wrapper next to the program, not Windows' own */
	char path[MAX_PATH], exe[MAX_PATH];
	GetModuleFileNameA(lib, path, sizeof(path));
	GetModuleFileNameA(NULL, exe, sizeof(exe));
	int n = lstrlenA(exe);
	while (n > 0 && exe[n - 1] != '\\')
		n--;
	CharUpperA(path);
	CharUpperA(exe);
	if (n == 0 || lstrlenA(path) < n || memcmp(path, exe, (size_t)n))
		fail("Windows' own OPENGL32.DLL was loaded: put qemu-3dfx's OPENGL32.DLL next to WSHDEMO.EXE", 2);
#define GL_LOAD(ret, name, args) *(FARPROC *)&glf.name = sym(#name, -1);
	GL_FUNCS(GL_LOAD)
	*(FARPROC *)&wgl.ChoosePixelFormat = sym("wglChoosePixelFormat", -1);
	*(FARPROC *)&wgl.SetPixelFormat = sym("wglSetPixelFormat", -1);
	*(FARPROC *)&wgl.CreateContext = sym("wglCreateContext", -1);
	*(FARPROC *)&wgl.MakeCurrent = sym("wglMakeCurrent", -1);
	*(FARPROC *)&wgl.DeleteContext = sym("wglDeleteContext", -1);
	*(FARPROC *)&wgl.SwapBuffers = sym("wglSwapBuffers", -1);
	*(FARPROC *)&wgl.GetProcAddress = sym("wglGetProcAddress", -1);
}

/* --- the menu ----------------------------------------------------------------------------------- */

static int menu_choice;
static LRESULT CALLBACK menuproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
	if (m == WM_COMMAND && LOWORD(w) >= 1 && LOWORD(w) <= 4) {
		menu_choice = LOWORD(w);
		return 0;
	}
	if (m == WM_CLOSE) {
		menu_choice = 4;
		return 0;
	}
	return DefWindowProcA(h, m, w, l);
}

/* 1 Glide 2, 2 Glide 3, 3 OpenGL, 4 quit */
static int menu(void)
{
	HINSTANCE hi = GetModuleHandleA(NULL);
	WNDCLASSA wc;
	memset(&wc, 0, sizeof(wc));
	wc.lpfnWndProc = menuproc;
	wc.hInstance = hi;
	wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
	wc.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
	wc.lpszClassName = "WSHDEMOMENU";
	RegisterClassA(&wc);
	int ww = 300, wh = 230;
	HWND m = CreateWindowExA(0, "WSHDEMOMENU", "wshdemo", WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_VISIBLE,
				 (GetSystemMetrics(SM_CXSCREEN) - ww) / 2, (GetSystemMetrics(SM_CYSCREEN) - wh) / 2, ww, wh, NULL, NULL,
				 hi, NULL);
	CreateWindowExA(0, "STATIC", "qemu-3dfx pass-through demo: pick the API", WS_CHILD | WS_VISIBLE | SS_CENTER, 10, 10,
			ww - 26, 20, m, NULL, hi, NULL);
	static const char *labels[4] = {"Glide 2 (GLIDE2X.DLL)", "Glide 3 (GLIDE3X.DLL)", "OpenGL (OPENGL32.DLL)", "Quit"};
	for (int i = 0; i < 4; i++)
		CreateWindowExA(0, "BUTTON", labels[i], WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 40, 38 + i * 40, ww - 86, 30, m,
				(HMENU)(INT_PTR)(i + 1), hi, NULL);
	while (!menu_choice) {
		MSG msg;
		if (GetMessageA(&msg, NULL, 0, 0) <= 0)
			break;
		TranslateMessage(&msg);
		DispatchMessageA(&msg);
	}
	DestroyWindow(m);
	pump();
	return menu_choice ? menu_choice : 4;
}

/* --- the entry point ---------------------------------------------------------------------------- */

static char argbuf[1024], *argv_[64];

static int split_args(void)
{
	GetModuleFileNameA(NULL, argbuf, 260);
	int argc = 0, o = lstrlenA(argbuf) + 1;
	argv_[argc++] = argbuf;
	for (const char *s = w3d_args(); *s && argc < 63 && o < (int)sizeof(argbuf) - 2;) {
		while (*s == ' ' || *s == '\t')
			s++;
		if (!*s)
			break;
		argv_[argc++] = argbuf + o;
		int quoted = *s == '"';
		if (quoted)
			s++;
		while (*s && o < (int)sizeof(argbuf) - 2 && (quoted ? *s != '"' : *s != ' ' && *s != '\t'))
			argbuf[o++] = *s++;
		if (quoted && *s)
			s++;
		argbuf[o++] = 0;
	}
	return argc;
}

void WinMainCRTStartup(void)
{
	int argc = split_args(), api = 0;
	for (int i = 1; i + 1 < argc; i++) {
		if (!lstrcmpiA(argv_[i], "-api"))
			api = !lstrcmpiA(argv_[i + 1], "glide2") ? 1 : !lstrcmpiA(argv_[i + 1], "glide3") ? 2 : !lstrcmpiA(argv_[i + 1], "opengl") ? 3 : -1;
		if (!lstrcmpiA(argv_[i], "-tag"))
			tagname = argv_[i + 1];
	}
	w3d_com_hold();
	if (api < 0)
		fail("-api is glide2, glide3 or opengl", 2);
	if (api == 0)
		api = menu();
	if (api == 4) {
		w3d_com_release();
		ExitProcess(0);
	}
	int status;
	if (api == 3) {
		load_gl();
		status = demo_main(argc, argv_, &gl_backend);
	} else if (api == 2) {
		load("GLIDE3X.DLL");
#define G3_LOAD(ret, name, args, bytes) *(FARPROC *)&g3.name = sym(#name, bytes);
		GLIDE3_FUNCS(G3_LOAD)
		wnd = make_window(GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
		g3.hwnd = (uint32_t)(uintptr_t)wnd;
		status = demo_main(argc, argv_, &glide3_backend);
	} else {
		load("GLIDE2X.DLL");
#define G2_LOAD(ret, name, args, bytes) *(FARPROC *)&g2.name = sym(#name, bytes);
		GLIDE2_FUNCS(G2_LOAD)
		wnd = make_window(GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
		g2.hwnd = (uint32_t)(uintptr_t)wnd;
		status = demo_main(argc, argv_, &glide2_backend);
	}
	if (wnd)
		DestroyWindow(wnd);
	FreeLibrary(lib);
	w3d_com_release();
	ExitProcess((UINT)status);
}
