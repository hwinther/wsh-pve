/*
 * w3dstrm.exe: a Glide program for streaming a Windows 98 guest's 3dfx display (e2e/streaming,
 * stream3dfx.py). Started from the Start menu's StartUp folder, it waits for commands from the host
 * on COM1 (115200 8N1, one a line, CR or LF) and answers there, with the tag STRM:
 *
 *   ping                       PONG
 *   glide [glide3] [fps=N]     open a 640x480 Glide window (GLIDE2X.DLL, or GLIDE3X.DLL) and animate
 *                              until quit or Esc, at N frames a second (default 60, paced by the
 *                              performance counter): a white bar moving across a dark blue clear
 *                              and, in the bottom tenth, eight cells with the frame number's low
 *                              eight bits (white 1, black 0, the most significant on the left).
 *                              After each swap: F <frame> <ms> <state> (state p plain, b bars)
 *   bars | plain               (glide) the bottom cells show eight colour bars (black, blue, green,
 *                              cyan, red, magenta, yellow, white: what wsh-moonlight-probe's eight
 *                              points look for) instead of the frame number, or the number again
 *   still | move               (glide) stop the animation (the same frame drawn again) or go on
 *   tone HZ MS                 a triangle wave of HZ Hz for MS ms (at most 3000) through WinMM's
 *                              waveOut, 22050 Hz 16-bit stereo: TONE start, then TONE done
 *   quit                       (glide) close the Glide window: CLOSED
 *   run S PROGRAM [ARGS]       run PROGRAM from C:\WIN3DFX for at most S seconds, with COM1
 *                              given up meanwhile (the program writes to it): EXIT PROGRAM STATUS MS
 *   shutdown                   power Windows off
 *
 * In the Glide window, keys and the mouse are reported as Windows gets them: KEY vk=<n> scan=<n>
 * down|up, BTN l|r|m 1|0 and MOUSE X Y (the window's coordinates, at most once a frame). B held
 * down shows the bars as the bars command does (input to picture), released the number again.
 * Once a second: FPS frames=<n> ms=<ms>. The F lines go to COM1 only; the others also to
 * C:\WIN3DFX\LOG.TXT. Copyright 2026 WsHosting ENK, GPL-3.
 */
#include "w3d.h"
#define printf w3d_printf
#include "scene.h"

#include <stddef.h>

typedef struct {
	float x, y;
	float r, g, b;
} Vertex3;

typedef void(__stdcall *fn_v)(void);
typedef void(__stdcall *fn_u)(uint32_t);
typedef uint32_t(__stdcall *fn_open)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
typedef void(__stdcall *fn_clear)(uint32_t, uint32_t, uint32_t);
typedef void(__stdcall *fn_tri)(const void *, const void *, const void *);
typedef void(__stdcall *fn_layout)(uint32_t, int32_t, uint32_t);
typedef uint32_t(__stdcall *fn_close3)(uint32_t);

static struct {
	fn_v GlideInit, GlideShutdown, SstWinClose2;
	fn_u SstSelect, BufferSwap;
	fn_open SstWinOpen;
	fn_clear BufferClear;
	fn_tri DrawTriangle;
	fn_layout VertexLayout;
	fn_close3 SstWinClose3;
} gr;

static HMODULE lib;
static int glide3;

static const uint8_t bars_rgb[8][3] = {{0, 0, 0},     {0, 0, 255},   {0, 255, 0},   {0, 255, 255},
				       {255, 0, 0}, {255, 0, 255}, {255, 255, 0}, {255, 255, 255}};

/* --- COM1: lines in, and frame lines out without the log file ------------------------------------ */

static OVERLAPPED rx_ov;
static char rx_line[256];
static int rx_len;

/* The next complete command line from the host, or NULL */
static const char *com_command(void)
{
	static char line[256];
	if (w3d_com == INVALID_HANDLE_VALUE)
		return NULL;
	for (;;) {
		DWORD errors = 0, n = 0;
		COMSTAT st;
		char c;
		if (!ClearCommError(w3d_com, &errors, &st) || !st.cbInQue)
			return NULL;
		if (!rx_ov.hEvent)
			rx_ov.hEvent = CreateEventA(NULL, TRUE, FALSE, NULL);
		ResetEvent(rx_ov.hEvent);
		if (!ReadFile(w3d_com, &c, 1, &n, &rx_ov)) {
			if (GetLastError() != ERROR_IO_PENDING || WaitForSingleObject(rx_ov.hEvent, 50) != WAIT_OBJECT_0 ||
			    !GetOverlappedResult(w3d_com, &rx_ov, &n, FALSE))
				return NULL;
		}
		if (n != 1)
			return NULL;
		if (c == '\r' || c == '\n') {
			if (!rx_len)
				continue;
			rx_line[rx_len] = 0;
			memcpy(line, rx_line, (size_t)rx_len + 1);
			rx_len = 0;
			return line;
		}
		if (rx_len < (int)sizeof(rx_line) - 1)
			rx_line[rx_len++] = c;
	}
}

static void com_only(const char *fmt, ...)
{
	char buf[160];
	va_list ap;
	int n = wsprintfA(buf, "%s: ", w3d_tag);
	va_start(ap, fmt);
	n += wvsprintfA(buf + n, fmt, ap);
	va_end(ap);
	if (w3d_com != INVALID_HANDLE_VALUE)
		w3d_com_write_line(w3d_com, buf, (DWORD)n);
}

static int word_is(const char *s, const char *w)
{
	size_t n = strlen(w);
	return !memcmp(s, w, n) && (s[n] == ' ' || !s[n]);
}

static int number(const char **s)
{
	int v = 0;
	while (**s == ' ')
		(*s)++;
	while (**s >= '0' && **s <= '9')
		v = v * 10 + (*(*s)++ - '0');
	return v;
}

/* --- the tone (WinMM, loaded at run time) --------------------------------------------------------- */

typedef struct {
	uint16_t wFormatTag, nChannels;
	uint32_t nSamplesPerSec, nAvgBytesPerSec;
	uint16_t nBlockAlign, wBitsPerSample, cbSize;
} WFX;
typedef struct wvhdr {
	char *lpData;
	uint32_t dwBufferLength, dwBytesRecorded;
	uintptr_t dwUser;
	uint32_t dwFlags, dwLoops;
	struct wvhdr *lpNext;
	uintptr_t reserved;
} WVHDR;
#define TONE_RATE 22050
static int16_t tone_buf[TONE_RATE * 3 * 2];
static WVHDR tone_hdr;
static void *hwave;
static HMODULE winmm;
static uint32_t(WINAPI *p_open)(void **, UINT, const WFX *, uintptr_t, uintptr_t, DWORD);
static uint32_t(WINAPI *p_prepare)(void *, WVHDR *, UINT);
static uint32_t(WINAPI *p_unprepare)(void *, WVHDR *, UINT);
static uint32_t(WINAPI *p_write)(void *, WVHDR *, UINT);
static uint32_t(WINAPI *p_close)(void *);

static void tone_poll(void)
{
	if (hwave && (tone_hdr.dwFlags & 1U)) { /* WHDR_DONE */
		p_unprepare(hwave, &tone_hdr, sizeof(tone_hdr));
		p_close(hwave);
		hwave = NULL;
		w3d_printf("TONE done");
	}
}

static void tone(int hz, int ms)
{
	if (hwave) {
		w3d_printf("TONE busy");
		return;
	}
	if (!winmm) {
		winmm = LoadLibraryA("WINMM.DLL");
		if (winmm) {
			*(FARPROC *)&p_open = GetProcAddress(winmm, "waveOutOpen");
			*(FARPROC *)&p_prepare = GetProcAddress(winmm, "waveOutPrepareHeader");
			*(FARPROC *)&p_unprepare = GetProcAddress(winmm, "waveOutUnprepareHeader");
			*(FARPROC *)&p_write = GetProcAddress(winmm, "waveOutWrite");
			*(FARPROC *)&p_close = GetProcAddress(winmm, "waveOutClose");
		}
	}
	if (!winmm || !p_open || !p_prepare || !p_unprepare || !p_write || !p_close) {
		w3d_printf("TONE error no WINMM.DLL");
		return;
	}
	if (ms > 3000)
		ms = 3000;
	uint32_t frames = (uint32_t)TONE_RATE * (uint32_t)ms / 1000, phase = 0;
	uint32_t step = (uint32_t)(((uint64_t)hz << 32) / TONE_RATE);
	for (uint32_t i = 0; i < frames; i++) {
		/* a triangle from the phase's top bits: -8192..8191 */
		int32_t p = (int32_t)(phase >> 16), v = p < 32768 ? p - 16384 : 49151 - p;
		tone_buf[2 * i] = tone_buf[2 * i + 1] = (int16_t)(v / 2);
		phase += step;
	}
	WFX fmt = {1, 2, TONE_RATE, TONE_RATE * 4, 4, 16, 0};
	uint32_t err = p_open(&hwave, (UINT)-1, &fmt, 0, 0, 0);
	if (err) {
		hwave = NULL;
		w3d_printf("TONE error waveOutOpen %u (no sound device?)", err);
		return;
	}
	memset(&tone_hdr, 0, sizeof(tone_hdr));
	tone_hdr.lpData = (char *)tone_buf;
	tone_hdr.dwBufferLength = frames * 4;
	p_prepare(hwave, &tone_hdr, sizeof(tone_hdr));
	w3d_printf("TONE start %d Hz %d ms", hz, ms);
	p_write(hwave, &tone_hdr, sizeof(tone_hdr));
}

/* --- Glide ------------------------------------------------------------------------------------------ */

static FARPROC sym(const char *name, int argbytes)
{
	char dec[96];
	wsprintfA(dec, "_%s@%d", name, argbytes);
	FARPROC p = GetProcAddress(lib, dec);
	if (!p)
		p = GetProcAddress(lib, name);
	if (!p)
		w3d_printf("ERROR no %s", name);
	return p;
}

static void rect(float x0, float y0, float x1, float y1, const uint8_t rgb[3])
{
	const float tri[2][3][2] = {{{x0, y0}, {x1, y0}, {x1, y1}}, {{x0, y0}, {x1, y1}, {x0, y1}}};
	for (int t = 0; t < 2; t++) {
		if (glide3) {
			Vertex3 v[3];
			for (int i = 0; i < 3; i++) {
				v[i].x = tri[t][i][0];
				v[i].y = tri[t][i][1];
				v[i].r = rgb[0];
				v[i].g = rgb[1];
				v[i].b = rgb[2];
			}
			gr.DrawTriangle(&v[0], &v[1], &v[2]);
		} else {
			const float c[3][3] = {{rgb[0], rgb[1], rgb[2]}, {rgb[0], rgb[1], rgb[2]}, {rgb[0], rgb[1], rgb[2]}};
			Vertex2 v[3] = {scene_vertex2(tri[t], c, 0), scene_vertex2(tri[t], c, 1), scene_vertex2(tri[t], c, 2)};
			gr.DrawTriangle(&v[0], &v[1], &v[2]);
		}
	}
}

static volatile int key_bars, quit_key, mouse_x = -1, mouse_y = -1, mouse_moved;

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
	switch (m) {
	case WM_SETCURSOR:
		SetCursor(NULL);
		return TRUE;
	case WM_KEYDOWN:
	case WM_SYSKEYDOWN:
	case WM_KEYUP:
	case WM_SYSKEYUP: {
		int down = m == WM_KEYDOWN || m == WM_SYSKEYDOWN;
		if (down && (l & 0x40000000)) /* autorepeat */
			return 0;
		w3d_printf("KEY vk=%u scan=%u %s", (unsigned)w, (unsigned)((l >> 16) & 0xff), down ? "down" : "up");
		if (w == 'B')
			key_bars = down;
		if (w == VK_ESCAPE && down)
			quit_key = 1;
		return 0;
	}
	case WM_MOUSEMOVE:
		mouse_x = (short)LOWORD(l);
		mouse_y = (short)HIWORD(l);
		mouse_moved = 1;
		return 0;
	case WM_LBUTTONDOWN:
	case WM_LBUTTONUP:
		w3d_printf("BTN l %d", m == WM_LBUTTONDOWN);
		return 0;
	case WM_RBUTTONDOWN:
	case WM_RBUTTONUP:
		w3d_printf("BTN r %d", m == WM_RBUTTONDOWN);
		return 0;
	case WM_MBUTTONDOWN:
	case WM_MBUTTONUP:
		w3d_printf("BTN m %d", m == WM_MBUTTONDOWN);
		return 0;
	}
	return DefWindowProcA(h, m, w, l);
}

static void pump(void)
{
	MSG msg;
	while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
		TranslateMessage(&msg);
		DispatchMessageA(&msg);
	}
}

static void glide_run(const char *args)
{
	glide3 = word_is(args, "glide3");
	const char *fp = args;
	int fps = 60;
	for (; *fp; fp++)
		if (!memcmp(fp, "fps=", 4)) {
			fp += 4;
			fps = number(&fp);
			break;
		}
	if (fps < 1 || fps > 200)
		fps = 60;
	const char *dll = glide3 ? "GLIDE3X.DLL" : "GLIDE2X.DLL";
	lib = LoadLibraryA(dll);
	if (!lib) {
		w3d_printf("ERROR LoadLibrary %s: error %lu", dll, GetLastError());
		return;
	}
	gr.GlideInit = (fn_v)sym("grGlideInit", 0);
	gr.GlideShutdown = (fn_v)sym("grGlideShutdown", 0);
	gr.SstSelect = (fn_u)sym("grSstSelect", 4);
	gr.SstWinOpen = (fn_open)sym("grSstWinOpen", 28);
	gr.BufferClear = (fn_clear)sym("grBufferClear", 12);
	gr.DrawTriangle = (fn_tri)sym("grDrawTriangle", 12);
	gr.BufferSwap = (fn_u)sym("grBufferSwap", 4);
	if (glide3) {
		gr.VertexLayout = (fn_layout)sym("grVertexLayout", 12);
		gr.SstWinClose3 = (fn_close3)sym("grSstWinClose", 4);
	} else {
		gr.SstWinClose2 = (fn_v)sym("grSstWinClose", 0);
	}
	if (!gr.GlideInit || !gr.SstWinOpen || !gr.BufferSwap || !gr.DrawTriangle ||
	    (glide3 ? !gr.VertexLayout || !gr.SstWinClose3 : !gr.SstWinClose2)) {
		FreeLibrary(lib);
		return;
	}

	WNDCLASSA wc;
	memset(&wc, 0, sizeof(wc));
	wc.lpfnWndProc = wndproc;
	wc.hInstance = GetModuleHandleA(NULL);
	wc.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
	wc.lpszClassName = "W3DSTRM";
	RegisterClassA(&wc);
	HWND wnd = CreateWindowExA(WS_EX_TOPMOST, "W3DSTRM", "w3dstrm", WS_POPUP | WS_VISIBLE, 0, 0,
				   GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN), NULL, NULL, wc.hInstance, NULL);
	if (wnd) {
		SetForegroundWindow(wnd);
		SetFocus(wnd);
		w3d_pump(100);
	}
	gr.GlideInit();
	gr.SstSelect(0);
	uint32_t ctx = gr.SstWinOpen((uint32_t)(uintptr_t)wnd, GR_RESOLUTION_640x480, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB,
				     GR_ORIGIN_UPPER_LEFT, 2, 1);
	if (!ctx) {
		w3d_printf("ERROR grSstWinOpen");
		gr.GlideShutdown();
		if (wnd)
			DestroyWindow(wnd);
		FreeLibrary(lib);
		return;
	}
	if (glide3) {
		gr.VertexLayout(GR_PARAM_XY, (int32_t)offsetof(Vertex3, x), GR_PARAM_ENABLE);
		gr.VertexLayout(GR_PARAM_RGB, (int32_t)offsetof(Vertex3, r), GR_PARAM_ENABLE);
	}
	w3d_printf("GLIDE open %s 640x480, %d frames/s", dll, fps);

	static const uint8_t white[3] = {255, 255, 255}, black[3] = {0, 0, 0}, grey[3] = {96, 96, 96};
	uint32_t frame = 0, shown = 0, t0 = w3d_ms(), sec0 = t0, sec_frames = 0;
	int bars = 0, still = 0;
	quit_key = 0;
	key_bars = 0;
	for (;;) {
		const char *cmd;
		while ((cmd = com_command())) {
			if (word_is(cmd, "quit"))
				quit_key = 1;
			else if (word_is(cmd, "bars"))
				bars = 1;
			else if (word_is(cmd, "plain"))
				bars = 0;
			else if (word_is(cmd, "still"))
				still = 1;
			else if (word_is(cmd, "move"))
				still = 0;
			else if (word_is(cmd, "ping"))
				w3d_printf("PONG");
			else if (word_is(cmd, "tone")) {
				const char *s = cmd + 4;
				int hz = number(&s), ms = number(&s);
				tone(hz, ms);
			} else
				w3d_printf("info: unknown command '%s'", cmd);
		}
		if (quit_key)
			break;
		int b = bars || key_bars;
		if (!still)
			shown = frame;
		gr.BufferClear(SCENE_CLEAR, 0xff, 0xffff);
		float x = (float)((shown * 8) % 608);
		rect(x, 0, x + 32, 432, white);
		rect(0, 428, 640, 432, grey);
		for (int i = 0; i < 8; i++)
			rect((float)(i * 80), 432, (float)(i * 80 + 80), 480,
			     b ? bars_rgb[i] : (shown >> (7 - i)) & 1 ? white : black);
		gr.BufferSwap(1);
		uint32_t now = w3d_ms();
		com_only("F %u %u %c", shown, now, b ? 'b' : 'p');
		if (mouse_moved) {
			mouse_moved = 0;
			w3d_printf("MOUSE %d %d", mouse_x, mouse_y);
		}
		tone_poll();
		frame++;
		sec_frames++;
		if (now - sec0 >= 1000) {
			w3d_printf("FPS frames=%u ms=%u", sec_frames, now - sec0);
			sec0 = now;
			sec_frames = 0;
		}
		/* pace to fps by the performance counter, handling messages meanwhile */
		uint32_t next = t0 + (uint32_t)((uint64_t)frame * 1000 / (uint32_t)fps);
		do {
			pump();
			now = w3d_ms();
			if ((int32_t)(next - now) > 2)
				Sleep(1);
		} while ((int32_t)(next - now) > 0);
		if ((int32_t)(now - next) > 100) /* far behind (a stall): don't race to catch up */
			t0 = now - (uint32_t)((uint64_t)frame * 1000 / (uint32_t)fps);
	}
	if (glide3)
		gr.SstWinClose3(ctx);
	else
		gr.SstWinClose2();
	gr.GlideShutdown();
	if (wnd)
		DestroyWindow(wnd);
	UnregisterClassA("W3DSTRM", GetModuleHandleA(NULL));
	FreeLibrary(lib);
	lib = NULL;
	w3d_printf("CLOSED after %u frames", frame);
}

/* --- the command loop ------------------------------------------------------------------------------ */

/* COM1 back after another program had it: Windows may still be closing that program's handle (the
 * open is refused or times out, and w3d.h then gives the port up for good), so try for a while */
static void com_reacquire(uint32_t ms)
{
	static uint32_t failures, logged;
	uint32_t end = GetTickCount() + ms;
	for (;;) {
		w3d_com_off = 0;
		w3d_com_hold();
		if (w3d_com != INVALID_HANDLE_VALUE) {
			if (failures)
				w3d_printf("COM1 open after %u failed tries (last: %s, error %lu)", failures,
					   w3d_oc.state == 2 ? "timed out" : "refused", w3d_oc.err);
			failures = 0;
			return;
		}
		failures++;
		if (GetTickCount() - logged > 10000) { /* the log file only: COM1 is what failed */
			logged = GetTickCount();
			w3d_com_off = 1;
			w3d_printf("COM1 open failed %u times (%s, error %lu)", failures,
				   w3d_oc.state == 2 ? "timed out" : "refused", w3d_oc.err);
		}
		if ((int32_t)(end - GetTickCount()) <= 0)
			return;
		Sleep(100);
	}
}

static void run(const char *args)
{
	char cmd[300];
	STARTUPINFOA si;
	PROCESS_INFORMATION pi;
	int timeout = number(&args);
	while (*args == ' ')
		args++;
	memset(&si, 0, sizeof(si));
	si.cb = sizeof(si);
	wsprintfA(cmd, "%s\\%s", W3D_DIR, args);
	w3d_printf("RUN %s (timeout %d s)", cmd, timeout);
	w3d_com_release();
	uint32_t t0 = w3d_ms();
	DWORD status = 0;
	if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, W3D_DIR, &si, &pi)) {
		com_reacquire(3000);
		w3d_printf("EXIT %s error %lu 0", args, GetLastError());
		return;
	}
	if (WaitForSingleObject(pi.hProcess, (DWORD)timeout * 1000) != WAIT_OBJECT_0) {
		TerminateProcess(pi.hProcess, 99);
		status = 99;
	} else {
		GetExitCodeProcess(pi.hProcess, &status);
	}
	CloseHandle(pi.hThread);
	CloseHandle(pi.hProcess);
	com_reacquire(5000);
	w3d_printf("EXIT %s %lu %u", args, status, w3d_ms() - t0);
}

void WinMainCRTStartup(void)
{
	w3d_tag = "STRM";
	w3d_com_access = GENERIC_READ | GENERIC_WRITE;
	w3d_com_open_ms = 2000;
	com_reacquire(60000);
	w3d_printf("READY screen %dx%d", GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
	for (;;) {
		const char *cmd;
		if (w3d_com == INVALID_HANDLE_VALUE)
			com_reacquire(0);
		while ((cmd = com_command())) {
			if (word_is(cmd, "ping"))
				w3d_printf("PONG");
			else if (word_is(cmd, "glide") || word_is(cmd, "glide3"))
				glide_run(cmd);
			else if (word_is(cmd, "tone")) {
				const char *s = cmd + 4;
				int hz = number(&s), ms = number(&s);
				tone(hz, ms);
			} else if (word_is(cmd, "run"))
				run(cmd + 3);
			else if (word_is(cmd, "shutdown")) {
				w3d_printf("SHUTDOWN");
				w3d_com_release();
				ExitWindowsEx(EWX_SHUTDOWN | EWX_POWEROFF | EWX_FORCE, 0);
				ExitProcess(0);
			} else
				w3d_printf("info: unknown command '%s'", cmd);
		}
		tone_poll();
		w3d_pump(20);
	}
}
