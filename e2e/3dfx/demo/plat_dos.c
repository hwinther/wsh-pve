/*
 * wshdemo's DOS front end: Glide 2 through qemu-3dfx's GLIDE2X.DXE, a DJGPP program linked with
 * the DXE's dxe3gen import library (libfxgl2.a, see build-dos.sh), as e2e/3dfx/dos/glidedos.c. The
 * import library's stubs load GLIDE2X.DXE on the first Glide call, from the current directory or a
 * directory in LD_LIBRARY_PATH; it is opened first here to say why when it isn't there. Needs a DPMI
 * host: CWSDPMI.EXE next to the program or on the PATH.
 *
 * Output goes to standard output and to COM1 (115200 8N1, written to the UART directly). With
 * -nocom only to standard output: for a batch file that has sent the console to COM1 already (CTTY
 * COM1, as the DOS test's does), where every line would reach the serial log twice; FreeDOS reports
 * such a COM1 as the console, so that can't be told from the device information. Keys come from the
 * BIOS keyboard. Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <dlfcn.h>
#include <dos.h>
#include <go32.h>
#include <pc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/farptr.h>
#include <time.h>

#include "demo.h"
#include "glide2.h"

#define DECL(ret, name, args, bytes) ret name args;
GLIDE2_FUNCS(DECL)
#define FILL(ret, name, args, bytes) g2.name = name;

static int com1;

/* crt0 registers the program's unwind tables with libgcc's unwinder, which only C++ exceptions
 * use. Defining the two entry points keeps that unwinder (built for the i686, with CMOV) out of the
 * program; DJGPP's crt0 and libc themselves are i386 code. */
void __register_frame_info(const void *begin, void *object)
{
	(void)begin, (void)object;
}
void *__deregister_frame_info(const void *begin)
{
	(void)begin;
	return 0;
}

uint32_t plat_us(void)
{
	return (uint32_t)(uclock() * (1e6 / UCLOCKS_PER_SEC));
}

static void com1_init(void)
{
	/* the BIOS's COM1 base (0 without a serial port), then 115200 8N1 with the FIFO on */
	int base = _farpeekw(_dos_ds, 0x400);
	if (base != 0x3f8)
		return;
	outportb(0x3fb, 0x80);
	outportb(0x3f8, 1);
	outportb(0x3f9, 0);
	outportb(0x3fb, 0x03);
	outportb(0x3fa, 0xc7);
	outportb(0x3fc, 0x03);
	com1 = 1;
}

static void com1_put(int c)
{
	for (int i = 0; i < 100000 && !(inportb(0x3fd) & 0x20); i++)
		;
	outportb(0x3f8, (unsigned char)c);
}

void plat_out(const char *line)
{
	printf("%s\n", line);
	fflush(stdout);
	if (com1) {
		for (const char *s = line; *s; s++)
			com1_put(*s);
		com1_put('\r');
		com1_put('\n');
	}
}

int plat_key(void)
{
	return kbhit() ? getkey() : -1;
}

void plat_sleep(int ms)
{
	delay((unsigned)ms);
}

/* The build string in GLIDE2X.DXE, read from the file the import library loads */
static uint8_t filebuf[256 * 1024];
static int scan_file(const char *path, char *buf, int n)
{
	FILE *f = fopen(path, "rb");
	if (!f)
		return 0;
	size_t len = fread(filebuf, 1, sizeof(filebuf), f);
	fclose(f);
	return demo_find_buildstr(filebuf, (uint32_t)len, buf, n);
}
int plat_wrapper_rev(char *buf, int n)
{
	if (scan_file("glide2x.dxe", buf, n))
		return 1;
	const char *lp = getenv("LD_LIBRARY_PATH");
	while (lp && *lp) {
		char path[160];
		int k = 0;
		while (*lp && *lp != ';' && k < 140)
			path[k++] = *lp++;
		if (*lp == ';')
			lp++;
		strcpy(path + k, "/glide2x.dxe");
		if (k && scan_file(path, buf, n))
			return 1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	setvbuf(stdout, NULL, _IOLBF, 0);
	int nocom = 0;
	for (int i = 1; i < argc; i++)
		nocom |= !strcmp(argv[i], "-nocom");
	if (!nocom)
		com1_init();
	/* The stubs end the program when the DXE can't be loaded; say why first */
	if (!dlopen("glide2x.dxe", RTLD_GLOBAL)) {
		char line[160];
		demo_fmt(line, sizeof(line), "WSHDEMO: ERROR dlopen glide2x.dxe: %.60s (put GLIDE2X.DXE next to WSHDEMO.EXE)", dlerror());
		plat_out(line);
		plat_out("WSHDEMO: CLOSED");
		return 2;
	}
	GLIDE2_FUNCS(FILL)
	return demo_main(argc, argv, &glide2_backend);
}
