/*
 * w3drun.exe: the runner of the Windows 98 3dfx test, started from the Start menu's StartUp folder
 * once Windows' desktop is up. It runs the programs C:\WIN3DFX\RUN.TXT lists, one at a time, then
 * shuts Windows down (ExitWindowsEx with power-off: QEMU ends with the VM). RUN.TXT, written by the
 * host's harness (win98_test.py), has one command a line:
 *
 *   delay <s>                     wait (the desktop settles after the start-up items)
 *   run <timeout s> <program> [<arguments>]
 *                                 run it from C:\WIN3DFX and wait for it, at most <timeout> s
 *   shutdown | stay               power off at the end (the default), or leave Windows running
 *
 * and prints, with the tag W3DRUN:
 *
 *   START <Windows version> <screen size> | RUN <program> ... | EXIT <program> <status> <ms> |
 *   TIMEOUT <program> <ms> | DONE <n> programs | SHUTDOWN
 *
 * It runs once per disk: C:\WIN3DFX\DONE.TXT (written before the shutdown) stops a second run after an
 * unexpected restart. Copyright 2026 WsHosting ENK, GPL-3.
 */
#include "w3d.h"

static char runlist[8192];

/* The next line of s (NUL-terminated, CR and LF removed); returns the rest */
static char *next_line(char *s, char **line)
{
	*line = s;
	while (*s && *s != '\n' && *s != '\r')
		s++;
	while (*s == '\n' || *s == '\r')
		*s++ = 0;
	return s;
}

static char *word(char **s)
{
	char *w = *s;
	while (**s && **s != ' ')
		(*s)++;
	if (**s)
		*(*s)++ = 0;
	while (**s == ' ')
		(*s)++;
	return w;
}

static int to_int(const char *s)
{
	int v = 0;
	while (*s >= '0' && *s <= '9')
		v = v * 10 + (*s++ - '0');
	return v;
}

static int run(int timeout_s, const char *program, const char *args)
{
	char cmd[512];
	STARTUPINFOA si;
	PROCESS_INFORMATION pi;
	memset(&si, 0, sizeof(si));
	si.cb = sizeof(si);
	wsprintfA(cmd, "%s\\%s %s", W3D_DIR, program, args);
	w3d_printf("RUN %s (timeout %d s)", cmd, timeout_s);
	uint32_t t0 = w3d_ms();
	if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, W3D_DIR, &si, &pi)) {
		w3d_printf("EXIT %s error %lu 0", program, GetLastError());
		return -1;
	}
	/* the program writes to COM1 itself while it runs; this one waits */
	DWORD w = WaitForSingleObject(pi.hProcess, (DWORD)timeout_s * 1000);
	uint32_t ms = w3d_ms() - t0;
	DWORD status = 0;
	if (w != WAIT_OBJECT_0) {
		TerminateProcess(pi.hProcess, 99);
		w3d_printf("TIMEOUT %s %u", program, ms);
		status = 99;
	} else {
		GetExitCodeProcess(pi.hProcess, &status);
		w3d_printf("EXIT %s %lu %u", program, status, ms);
	}
	CloseHandle(pi.hThread);
	CloseHandle(pi.hProcess);
	return (int)status;
}

void WinMainCRTStartup(void)
{
	w3d_tag = "W3DRUN";
	OSVERSIONINFOA v;
	memset(&v, 0, sizeof(v));
	v.dwOSVersionInfoSize = sizeof(v);
	GetVersionExA(&v);
	w3d_printf("START Windows %lu.%lu.%lu %s, screen %dx%d", v.dwMajorVersion, v.dwMinorVersion, v.dwBuildNumber & 0xffff,
		   v.szCSDVersion, GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));

	HANDLE f = CreateFileA(W3D_DIR "\\DONE.TXT", GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
	if (f != INVALID_HANDLE_VALUE) {
		CloseHandle(f);
		w3d_printf("DONE.TXT exists: ran already, nothing to do");
		ExitProcess(0);
	}
	f = CreateFileA(W3D_DIR "\\RUN.TXT", GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
	DWORD n = 0;
	if (f == INVALID_HANDLE_VALUE || !ReadFile(f, runlist, sizeof(runlist) - 1, &n, NULL)) {
		w3d_printf("ERROR no %s\\RUN.TXT", W3D_DIR);
		n = 0;
	}
	if (f != INVALID_HANDLE_VALUE)
		CloseHandle(f);
	runlist[n] = 0;

	int programs = 0, shutdown = 1;
	char *rest = runlist, *line;
	while (*rest) {
		rest = next_line(rest, &line);
		char *cmd = word(&line);
		if (!lstrcmpiA(cmd, "delay")) {
			w3d_printf("delay %s s", line);
			w3d_pump((uint32_t)to_int(line) * 1000);
		} else if (!lstrcmpiA(cmd, "run")) {
			int timeout = to_int(word(&line));
			char *program = word(&line);
			run(timeout, program, line);
			programs++;
		} else if (!lstrcmpiA(cmd, "stay")) {
			shutdown = 0;
		} else if (!lstrcmpiA(cmd, "shutdown")) {
			shutdown = 1;
		} else if (*cmd) {
			w3d_printf("info: unknown command '%s'", cmd);
		}
	}
	w3d_printf("DONE %d programs", programs);
	f = CreateFileA(W3D_DIR "\\DONE.TXT", GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
	if (f != INVALID_HANDLE_VALUE)
		CloseHandle(f);
	if (shutdown) {
		w3d_printf("SHUTDOWN");
		if (!ExitWindowsEx(EWX_SHUTDOWN | EWX_POWEROFF | EWX_FORCE, 0))
			w3d_printf("ERROR ExitWindowsEx: %lu", GetLastError());
	}
	ExitProcess(0);
}
