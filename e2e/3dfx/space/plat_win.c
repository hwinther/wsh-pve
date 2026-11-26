/*
 * wshspace's Windows front end (9x/ME/2000/XP): Glide 2, Glide 3 and OpenGL in one WSHSPACE.EXE
 * without MSVCRT (imports KERNEL32, USER32 and GDI32 only). Loads WINMM.DLL dynamically at run time
 * for double-buffered procedural waveOut synth audio, with silent fallback when absent.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include "w3d.h"

#include "space.h"
#include "gl11.h"
#include "glide2.h"
#include "glide3.h"

static HMODULE lib;
static const char *lib_name, *tagname = "WSHSPACE";
static HWND wnd;
static int keys[32], key_head, key_tail;
static uint8_t vk_down[256];
static int mlook, mouse_dx, mouse_dy, mouse_btn, host_gl;
static char last_err[256];

void plat_out(const char *line)
{
	for (const char *p = line; *p; p++) {
		if (p[0] == ':' && p[1] == ' ' && !memcmp(p + 2, "ERROR ", 6)) {
			lstrcpynA(last_err, p + 8, sizeof(last_err));
			break;
		}
	}
	if (!last_err[0] && !memcmp(line, "usage: ", 7))
		lstrcpynA(last_err, line, sizeof(last_err));
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

static void push_key(int k)
{
	int next = (key_head + 1) & 31;
	if (next != key_tail) {
		keys[key_head] = k;
		key_head = next;
	}
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
	key_tail = (key_tail + 1) & 31;
	return k;
}

void plat_poll(struct plat_input *in)
{
	pump();
	uint32_t h = 0;
	if (vk_down[VK_UP])                        h |= IN_PITCH_UP;
	if (vk_down[VK_DOWN])                      h |= IN_PITCH_DOWN;
	if (vk_down[VK_LEFT])                      h |= IN_YAW_LEFT;
	if (vk_down[VK_RIGHT])                     h |= IN_YAW_RIGHT;
	if (vk_down['A'] || vk_down['Q'])          h |= IN_ROLL_LEFT;
	if (vk_down['D'] || vk_down['E'])          h |= IN_ROLL_RIGHT;
	if (vk_down['W'] || (mouse_btn & 2))       h |= IN_THRUST;
	if (vk_down['S'])                          h |= IN_BRAKE;
	if (vk_down[VK_SHIFT] || vk_down['B'])     h |= IN_BOOST;
	if (vk_down[VK_SPACE] || (mouse_btn & 1))  h |= IN_FIRE;
	in->held = h;
	in->mdx = mouse_dx;
	in->mdy = mouse_dy;
	in->mlook = mlook;
	mouse_dx = mouse_dy = 0;
}

void plat_sleep(int ms)
{
	uint32_t end = GetTickCount() + (uint32_t)ms;
	do {
		pump();
		Sleep(ms < 10 ? (DWORD)ms : 10);
	} while ((int32_t)(end - GetTickCount()) > 0);
}

static void recenter_mouse(HWND h)
{
	RECT rc;
	GetClientRect(h, &rc);
	POINT pt = {(rc.right - rc.left) / 2, (rc.bottom - rc.top) / 2};
	ClientToScreen(h, &pt);
	SetCursorPos(pt.x, pt.y);
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
	switch (m) {
	case WM_SETCURSOR:
		if (!host_gl || (mlook && LOWORD(l) == HTCLIENT)) {
			SetCursor(NULL);
			return TRUE;
		}
		break;
	case WM_KEYDOWN:
		vk_down[w & 0xff] = 1;
		if (!(l & (1 << 30))) {
			if (w == VK_UP)    push_key(KEY_UP);
			if (w == VK_DOWN)  push_key(KEY_DOWN);
			if (w == VK_LEFT)  push_key(KEY_LEFT);
			if (w == VK_RIGHT) push_key(KEY_RIGHT);
			if (w == 'V') {
				mlook = !mlook;
				if (mlook)
					recenter_mouse(h);
			}
		}
		return 0;
	case WM_KEYUP:
		vk_down[w & 0xff] = 0;
		return 0;
	case WM_CHAR:
		push_key((int)(w & 0xff));
		return 0;
	case WM_LBUTTONDOWN: mouse_btn |= 1; return 0;
	case WM_LBUTTONUP:   mouse_btn &= ~1; return 0;
	case WM_RBUTTONDOWN: mouse_btn |= 2; return 0;
	case WM_RBUTTONUP:   mouse_btn &= ~2; return 0;
	case WM_MOUSEMOVE:
		if (mlook && GetForegroundWindow() == h) {
			RECT rc;
			GetClientRect(h, &rc);
			int cx = (rc.right - rc.left) / 2, cy = (rc.bottom - rc.top) / 2;
			int mx = (int)(short)LOWORD(l), my = (int)(short)HIWORD(l);
			if (mx != cx || my != cy) {
				mouse_dx += mx - cx;
				mouse_dy += my - cy;
				recenter_mouse(h);
			}
		}
		return 0;
	case WM_KILLFOCUS:
		memset(vk_down, 0, sizeof(vk_down));
		mouse_btn = 0;
		return 0;
	case WM_CLOSE:
		push_key(27);
		return 0;
	}
	return DefWindowProcA(h, m, w, l);
}

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
		wc.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
		wc.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
		wc.lpszClassName = "WSHSPACE";
		RegisterClassA(&wc);
		registered = 1;
	}
	HWND hw;
	if (host_gl) {
		DWORD st = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPSIBLINGS | WS_CLIPCHILDREN;
		RECT r = {0, 0, w, h};
		AdjustWindowRect(&r, st, FALSE);
		int ww = r.right - r.left, wh = r.bottom - r.top;
		int x = (GetSystemMetrics(SM_CXSCREEN) - ww) / 2, y = (GetSystemMetrics(SM_CYSCREEN) - wh) / 2;
		hw = CreateWindowExA(0, "WSHSPACE", "wshspace", st | WS_VISIBLE,
				     x > 0 ? x : 0, y > 0 ? y : 0, ww, wh, NULL, NULL, hi, NULL);
	} else {
		hw = CreateWindowExA(WS_EX_TOPMOST, "WSHSPACE", "wshspace",
				     WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN,
				     0, 0, w, h, NULL, NULL, hi, NULL);
	}
	if (hw) {
		SetForegroundWindow(hw);
		SetFocus(hw);
		plat_sleep(100);
	}
	return hw;
}

/* --- runtime-optional WinMM waveOut streaming synth audio ------------------------------------- */

#define SND_MIX space_audio_mix
#include "../audio/snd_win.h"

/* --- wrapper build string & DLL loader -------------------------------------------------------- */

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
		    space_find_buildstr(base + s[i].VirtualAddress, s[i].Misc.VirtualSize, buf, n))
			return 1;
	return 0;
}

static void fail(const char *what, int status)
{
	char line[240];
	wsprintfA(line, "%s: ERROR %s", tagname, what);
	w3d_line(line);
	wsprintfA(line, "%s: CLOSED", tagname);
	w3d_line(line);
	w3d_com_release();
	if (!w3d_in_guest())
		MessageBoxA(NULL, what, "wshspace", MB_OK | MB_ICONERROR);
	ExitProcess((UINT)status);
}

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
		wsprintfA(what, "LoadLibrary %s: error %lu", name, GetLastError());
		fail(what, 2);
	}
}

/* --- OpenGL context & display mode ------------------------------------------------------------ */

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
	if (!host_gl) {
		DEVMODEA dm;
		memset(&dm, 0, sizeof(dm));
		dm.dmSize = sizeof(dm);
		dm.dmPelsWidth = (DWORD)w;
		dm.dmPelsHeight = (DWORD)h;
		dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
		if (ChangeDisplaySettingsA(&dm, CDS_FULLSCREEN) == DISP_CHANGE_SUCCESSFUL)
			mode_changed = 1;
	}
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
	if (!fmt || !wgl.SetPixelFormat(hdc, fmt, &pfd))
		return -1;
	ctx = wgl.CreateContext(hdc);
	if (!ctx || !wgl.MakeCurrent(hdc, ctx))
		return -1;
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
	if (final && mode_changed) {
		ChangeDisplaySettingsA(NULL, 0);
		mode_changed = 0;
	}
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
	if (!host_gl) {
		char path[MAX_PATH], exe[MAX_PATH];
		GetModuleFileNameA(lib, path, sizeof(path));
		GetModuleFileNameA(NULL, exe, sizeof(exe));
		int n = lstrlenA(exe);
		while (n > 0 && exe[n - 1] != '\\')
			n--;
		CharUpperA(path);
		CharUpperA(exe);
		if (n == 0 || lstrlenA(path) < n || memcmp(path, exe, (size_t)n))
			fail("Windows' own OPENGL32.DLL was loaded: put qemu-3dfx's OPENGL32.DLL next to WSHSPACE.EXE (or pass -hostgl)", 2);
	}
#define GL_LOAD(ret, name, args) *(FARPROC *)&glf.name = sym(#name, -1);
	GL_FUNCS(GL_LOAD)
	if (host_gl) {
		wgl.ChoosePixelFormat = ChoosePixelFormat;
		wgl.SetPixelFormat = SetPixelFormat;
		wgl.SwapBuffers = SwapBuffers;
	} else {
		*(FARPROC *)&wgl.ChoosePixelFormat = sym("wglChoosePixelFormat", -1);
		*(FARPROC *)&wgl.SetPixelFormat = sym("wglSetPixelFormat", -1);
		*(FARPROC *)&wgl.SwapBuffers = sym("wglSwapBuffers", -1);
	}
	*(FARPROC *)&wgl.CreateContext = sym("wglCreateContext", -1);
	*(FARPROC *)&wgl.MakeCurrent = sym("wglMakeCurrent", -1);
	*(FARPROC *)&wgl.DeleteContext = sym("wglDeleteContext", -1);
	*(FARPROC *)&wgl.GetProcAddress = sym("wglGetProcAddress", -1);
}

/* --- launcher menu & entry point -------------------------------------------------------------- */

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

static int menu(void)
{
	HINSTANCE hi = GetModuleHandleA(NULL);
	WNDCLASSA wc;
	memset(&wc, 0, sizeof(wc));
	wc.lpfnWndProc = menuproc;
	wc.hInstance = hi;
	wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
	wc.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
	wc.lpszClassName = "WSHSPACEMENU";
	RegisterClassA(&wc);
	int ww = 300, wh = 230;
	HWND m = CreateWindowExA(0, "WSHSPACEMENU", "wshspace", WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_VISIBLE,
				 (GetSystemMetrics(SM_CXSCREEN) - ww) / 2, (GetSystemMetrics(SM_CYSCREEN) - wh) / 2,
				 ww, wh, NULL, NULL, hi, NULL);
	CreateWindowExA(0, "STATIC", "wshspace: select 3D renderer", WS_CHILD | WS_VISIBLE | SS_CENTER,
			10, 10, ww - 26, 20, m, NULL, hi, NULL);
	static const char *labels[4] = {"Glide 2 (GLIDE2X.DLL)", "Glide 3 (GLIDE3X.DLL)", "OpenGL (OPENGL32.DLL)", "Quit"};
	for (int i = 0; i < 4; i++)
		CreateWindowExA(0, "BUTTON", labels[i], WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
				40, 38 + i * 40, ww - 86, 30, m, (HMENU)(INT_PTR)(i + 1), hi, NULL);
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
	int argc = split_args(), api = 0, audiotest = 0;
	for (int i = 1; i < argc; i++) {
		if (!lstrcmpiA(argv_[i], "-audiotest"))
			audiotest = 1;
		else if (!lstrcmpiA(argv_[i], "-hostgl"))
			host_gl = 1;
		else if (!lstrcmpiA(argv_[i], "-nocom"))
			w3d_com_off = 1;
		else if (i + 1 < argc && !lstrcmpiA(argv_[i], "-api")) {
			api = !lstrcmpiA(argv_[i + 1], "glide2") ? 1 : !lstrcmpiA(argv_[i + 1], "glide3") ? 2 : !lstrcmpiA(argv_[i + 1], "opengl") ? 3 : -1;
			i++;
		} else if (i + 1 < argc && !lstrcmpiA(argv_[i], "-tag")) {
			tagname = argv_[i + 1];
			i++;
		} else if (i + 1 < argc && !lstrcmpiA(argv_[i], "-log")) {
			w3d_log_path = argv_[i + 1];
			i++;
		}
	}
	w3d_com_hold();
	if (api < 0)
		fail("-api is glide2, glide3 or opengl", 2);
	if (api == 0 && host_gl)
		api = 3;
	if (audiotest) {
		/* no display: neither the renderer menu nor a renderer's DLL (a guest without them plays
		 * the signature as well) */
		int status = space_main(argc, argv_, api == 1 ? &glide2_backend : api == 2 ? &glide3_backend : &gl_backend);
		w3d_com_release();
		ExitProcess((UINT)status);
	}
	if (api == 0)
		api = menu();
	if (api == 4) {
		w3d_com_release();
		ExitProcess(0);
	}
	int status;
	if (api == 3) {
		load_gl();
		status = space_main(argc, argv_, &gl_backend);
	} else if (api == 2) {
		load("GLIDE3X.DLL");
#define G3_LOAD(ret, name, args, bytes) *(FARPROC *)&g3.name = sym(#name, bytes);
		GLIDE3_FUNCS(G3_LOAD)
		wnd = make_window(GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
		g3.hwnd = (uint32_t)(uintptr_t)wnd;
		status = space_main(argc, argv_, &glide3_backend);
	} else {
		load("GLIDE2X.DLL");
#define G2_LOAD(ret, name, args, bytes) *(FARPROC *)&g2.name = sym(#name, bytes);
		GLIDE2_FUNCS(G2_LOAD)
		wnd = make_window(GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
		g2.hwnd = (uint32_t)(uintptr_t)wnd;
		status = space_main(argc, argv_, &glide2_backend);
	}
	glw_close(1);
	FreeLibrary(lib);
	w3d_com_release();
	if (status >= 2 && !w3d_in_guest())
		MessageBoxA(NULL, last_err[0] ? last_err : "wshspace failed", "wshspace", MB_OK | MB_ICONERROR);
	ExitProcess((UINT)status);
}
