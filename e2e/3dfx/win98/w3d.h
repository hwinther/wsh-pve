/*
 * w3d.h: the little runtime of the Windows 98 3dfx test programs (w3drun.exe, glidetst.exe,
 * gltest.exe). They are built with mingw-w64 (i686) without its C runtime: Windows 98's MSVCRT.DLL
 * lacks functions that newer mingw-w64 start-up code imports, so each program has its own entry
 * point and uses only KERNEL32, USER32 and GDI32 functions that Windows 95 already had (wsprintfA
 * for formatting: no floating point there, so numbers are printed as integers or fixed point).
 *
 * Output goes to COM1 (the harness on the host reads QEMU's serial port, e2e/3dfx/win98/win98_test.py)
 * and is appended to C:\WIN3DFX\LOG.TXT, one line each. Every line a program prints starts with its
 * tag ("GLIDE2: ", "GLIDE3: ", "OPENGL: ", "W3DRUN: "); the harness keys on
 *
 *   <TAG>: START ... | <TAG>: FRAME | <TAG>: BENCH ... | <TAG>: PASS | <TAG>: FAIL <n> |
 *   <TAG>: ERROR <what> | <TAG>: CLOSED
 *
 * The serial port is opened per line and closed again: Windows serial ports are exclusive, and the
 * runner and the test program it waits for both write to it. Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_W3D_H
#define WSH_W3D_H

#include <windows.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma GCC diagnostic ignored "-Wunused-function"

#define W3D_DIR "C:\\WIN3DFX"
#define W3D_LOG W3D_DIR "\\LOG.TXT"

/* gcc may emit calls to these for struct copies and loops; there is no C runtime to provide them */
void *memset(void *d, int c, size_t n)
{
	unsigned char *p = d;
	while (n--) {
		*p++ = (unsigned char)c;
		__asm__ volatile("" : : : "memory");
	}
	return d;
}
void *memcpy(void *d, const void *s, size_t n)
{
	unsigned char *p = d;
	const unsigned char *q = s;
	while (n--) {
		*p++ = *q++;
		__asm__ volatile("" : : : "memory");
	}
	return d;
}
int memcmp(const void *a, const void *b, size_t n)
{
	const unsigned char *p = a, *q = b;
	for (; n; n--, p++, q++) {
		__asm__ volatile("" : : : "memory");
		if (*p != *q)
			return *p - *q;
	}
	return 0;
}
size_t strlen(const char *s)
{
	size_t n = 0;
	while (s[n]) {
		n++;
		__asm__ volatile("" : : : "memory");
	}
	return n;
}

static const char *w3d_tag = "W3D";
static const char *w3d_log_path = W3D_LOG;
static HANDLE w3d_com = INVALID_HANDLE_VALUE;
static HANDLE w3d_com_ev;
static int w3d_com_off;
static OVERLAPPED w3d_ov;
static char w3d_txbuf[1200];

static struct {
	volatile int state; /* 0 = opening, 1 = worker done, 2 = timed out */
	HANDLE h;
	DWORD err;
} w3d_oc;

static inline int w3d_xchg(volatile int *p, int v)
{
	__asm__ volatile("xchgl %0, %1" : "+r"(v), "+m"(*p) : : "memory");
	return v;
}

/* C:\WIN3DFX exists inside the automated Windows 98 test guest */
static int w3d_in_guest(void)
{
	DWORD a = GetFileAttributesA(W3D_DIR);
	return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

static void w3d_file_write(HANDLE h, const char *s, DWORD n)
{
	DWORD done;
	while (n && WriteFile(h, s, n, &done, NULL) && done) {
		s += done;
		n -= done;
	}
}

static DWORD WINAPI w3d_close_thread(LPVOID arg)
{
	HANDLE h = (HANDLE)arg;
	PurgeComm(h, PURGE_TXABORT | PURGE_RXABORT | PURGE_TXCLEAR | PURGE_RXCLEAR);
	CloseHandle(h);
	return 0;
}

static void w3d_abandon_com(HANDLE h)
{
	DWORD tid;
	w3d_com_off = 1;
	if (w3d_com == h)
		w3d_com = INVALID_HANDLE_VALUE;
	PurgeComm(h, PURGE_TXABORT | PURGE_RXABORT | PURGE_TXCLEAR | PURGE_RXCLEAR);
	HANDLE th = CreateThread(NULL, 0, w3d_close_thread, (LPVOID)h, 0, &tid);
	if (th) {
		WaitForSingleObject(th, 50);
		CloseHandle(th);
	}
}

static DWORD WINAPI w3d_open_thread(LPVOID arg)
{
	(void)arg;
	HANDLE h = CreateFileA("COM1", GENERIC_WRITE, 0, NULL, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, NULL);
	DWORD err = GetLastError();
	w3d_oc.h = h;
	w3d_oc.err = err;
	if (w3d_xchg(&w3d_oc.state, 1) == 2 && h != INVALID_HANDLE_VALUE) {
		PurgeComm(h, PURGE_TXABORT | PURGE_RXABORT | PURGE_TXCLEAR | PURGE_RXCLEAR);
		CloseHandle(h);
	}
	return 0;
}

/* COM1 at 115200 8N1 without flow control, opened asynchronously with a 200 ms timeout and
 * FILE_FLAG_OVERLAPPED so a physical or AMT serial port on a host PC cannot hang the program */
static HANDLE w3d_com_open(void)
{
	if (w3d_com_off)
		return INVALID_HANDLE_VALUE;
	DWORD tid;
	w3d_oc.state = 0;
	w3d_oc.h = INVALID_HANDLE_VALUE;
	w3d_oc.err = 0;
	HANDLE th = CreateThread(NULL, 0, w3d_open_thread, NULL, 0, &tid);
	if (!th) {
		w3d_com_off = 1;
		return INVALID_HANDLE_VALUE;
	}
	WaitForSingleObject(th, 200);
	if (w3d_xchg(&w3d_oc.state, 2) != 1) {
		CloseHandle(th);
		w3d_com_off = 1;
		return INVALID_HANDLE_VALUE;
	}
	WaitForSingleObject(th, 50);
	CloseHandle(th);
	HANDLE h = w3d_oc.h;
	if (h == INVALID_HANDLE_VALUE) {
		if (w3d_oc.err != ERROR_ACCESS_DENIED)
			w3d_com_off = 1;
		return INVALID_HANDLE_VALUE;
	}
	DCB dcb;
	memset(&dcb, 0, sizeof(dcb));
	dcb.DCBlength = sizeof(dcb);
	if (GetCommState(h, &dcb)) {
		dcb.BaudRate = CBR_115200;
		dcb.ByteSize = 8;
		dcb.Parity = NOPARITY;
		dcb.StopBits = ONESTOPBIT;
		dcb.fBinary = TRUE;
		dcb.fOutxCtsFlow = dcb.fOutxDsrFlow = FALSE;
		dcb.fDsrSensitivity = FALSE;
		dcb.fTXContinueOnXoff = TRUE;
		dcb.fDtrControl = DTR_CONTROL_ENABLE;
		dcb.fRtsControl = RTS_CONTROL_ENABLE;
		dcb.fOutX = dcb.fInX = FALSE;
		dcb.fAbortOnError = FALSE;
		SetCommState(h, &dcb);
	}
	COMMTIMEOUTS to = {MAXDWORD, 0, 0, 1, 100};
	SetCommTimeouts(h, &to);
	if (!w3d_com_ev)
		w3d_com_ev = CreateEventA(NULL, TRUE, FALSE, NULL);
	return h;
}

static int w3d_com_write_line(HANDLE h, const char *s, DWORD n)
{
	if (!w3d_com_ev)
		return 0;
	if (n > sizeof(w3d_txbuf) - 2)
		n = sizeof(w3d_txbuf) - 2;
	memcpy(w3d_txbuf, s, n);
	w3d_txbuf[n] = '\r';
	w3d_txbuf[n + 1] = '\n';
	DWORD total = n + 2, done = 0;
	memset(&w3d_ov, 0, sizeof(w3d_ov));
	ResetEvent(w3d_com_ev);
	w3d_ov.hEvent = w3d_com_ev;
	if (!WriteFile(h, w3d_txbuf, total, &done, &w3d_ov)) {
		if (GetLastError() != ERROR_IO_PENDING ||
		    WaitForSingleObject(w3d_com_ev, 200) != WAIT_OBJECT_0 ||
		    !GetOverlappedResult(h, &w3d_ov, &done, FALSE)) {
			w3d_abandon_com(h);
			return 0;
		}
	}
	return 1;
}

/* Keep COM1 open for a while (a test program between its start and its end); w3d_com_release()
 * gives it back for the runner */
static void w3d_com_hold(void)
{
	if (!w3d_com_off && w3d_com == INVALID_HANDLE_VALUE)
		w3d_com = w3d_com_open();
}
static void w3d_com_release(void)
{
	if (w3d_com != INVALID_HANDLE_VALUE)
		CloseHandle(w3d_com);
	w3d_com = INVALID_HANDLE_VALUE;
}

/* One line, without the tag: to COM1 and to the log file */
static void w3d_line(const char *s)
{
	DWORD n = (DWORD)strlen(s);
	if (!w3d_com_off) {
		HANDLE com = w3d_com;
		int temp = 0;
		if (com == INVALID_HANDLE_VALUE) {
			com = w3d_com_open();
			temp = 1;
		}
		if (com != INVALID_HANDLE_VALUE) {
			if (w3d_com_write_line(com, s, n) && temp)
				CloseHandle(com);
		}
	}
	HANDLE f = CreateFileA(w3d_log_path, GENERIC_WRITE, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
	if (f != INVALID_HANDLE_VALUE) {
		SetFilePointer(f, 0, NULL, FILE_END);
		w3d_file_write(f, s, n);
		w3d_file_write(f, "\r\n", 2);
		CloseHandle(f);
	}
}

/* printf-like, through wsprintfA (%s %d %u %x %c with flags and width; no floating point): the
 * line goes out with the program's tag in front, unless the format starts with '|', which prints
 * the rest as it is (probe lines from scene.h) */
static int w3d_printf(const char *fmt, ...)
{
	char buf[1100], *p = buf;
	va_list ap;
	if (*fmt == '|')
		fmt++;
	else
		p += wsprintfA(buf, "%s: ", w3d_tag);
	va_start(ap, fmt);
	wvsprintfA(p, fmt, ap);
	va_end(ap);
	/* one line per call: a trailing newline is the line's end */
	size_t n = strlen(buf);
	while (n && (buf[n - 1] == '\n' || buf[n - 1] == '\r'))
		buf[--n] = 0;
	w3d_line(buf);
	return (int)n;
}

/* Milliseconds since an arbitrary start, from the performance counter when there is one */
static uint32_t w3d_ms(void)
{
	static LARGE_INTEGER freq;
	LARGE_INTEGER now;
	if (!freq.QuadPart && !QueryPerformanceFrequency(&freq))
		freq.QuadPart = -1;
	if (freq.QuadPart > 0 && QueryPerformanceCounter(&now))
		return (uint32_t)(now.QuadPart * 1000 / freq.QuadPart);
	return GetTickCount();
}

/* The program's command line after its name (Windows 98 passes it as one string) */
static const char *w3d_args(void)
{
	const char *s = GetCommandLineA();
	if (*s == '"') {
		for (s++; *s && *s != '"'; s++)
			;
		if (*s)
			s++;
	} else {
		while (*s && *s != ' ')
			s++;
	}
	while (*s == ' ')
		s++;
	return s;
}

/* "name=<n>" in the arguments, or def */
static int w3d_arg_int(const char *name, int def)
{
	const char *s = w3d_args();
	size_t n = strlen(name);
	for (; *s; s++) {
		if ((s == w3d_args() || s[-1] == ' ') && !memcmp(s, name, n) && s[n] == '=') {
			int v = 0, neg = 0;
			s += n + 1;
			if (*s == '-')
				neg = 1, s++;
			while (*s >= '0' && *s <= '9')
				v = v * 10 + (*s++ - '0');
			return neg ? -v : v;
		}
	}
	return def;
}

/* Whether the word appears in the arguments */
static int w3d_arg_flag(const char *word)
{
	const char *s = w3d_args();
	size_t n = strlen(word);
	for (; *s; s++)
		if ((s == w3d_args() || s[-1] == ' ') && !memcmp(s, word, n) && (s[n] == ' ' || !s[n]))
			return 1;
	return 0;
}

/* Waits ms milliseconds while handling the window messages of this thread */
static void w3d_pump(uint32_t ms)
{
	uint32_t end = GetTickCount() + ms;
	do {
		MSG msg;
		while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
			TranslateMessage(&msg);
			DispatchMessageA(&msg);
		}
		Sleep(10);
	} while ((int32_t)(end - GetTickCount()) > 0);
}

/* A coarse map of a read-back frame, for the log: one letter per 16x32 pixels (r, g, b: mostly that
 * channel; . the clear colour; space black; ? anything else), as e2e/3dfx's Linux guests print it */
static void w3d_print_map(const char *what, uint8_t (*px)(int, int, int), int w, int h)
{
	w3d_printf("%s, 40x15:", what);
	for (int y = 16; y < h; y += 32) {
		char row[48];
		int i = 0;
		row[i++] = ' ';
		row[i++] = ' ';
		row[i++] = '|';
		for (int x = 8; x < w && i < 43; x += 16) {
			int r = px(x, y, 0), g = px(x, y, 1), b = px(x, y, 2);
			row[i++] = (r < 16 && g < 16 && b < 16)                 ? ' '
				   : (r < 16 && g < 16 && b > 100 && b < 160) ? '.'
				   : (r > g && r > b)                         ? 'r'
				   : (g > r && g > b)                         ? 'g'
				   : (b > r && b > g)                         ? 'b'
									      : '?';
		}
		row[i++] = '|';
		row[i] = 0;
		w3d_printf("%s", row);
	}
}

/* Frames per second times ten, for a fixed-point print */
static uint32_t w3d_fps10(uint32_t frames, uint32_t ms)
{
	return ms ? (uint32_t)((uint64_t)frames * 10000 / ms) : 0;
}

#endif
