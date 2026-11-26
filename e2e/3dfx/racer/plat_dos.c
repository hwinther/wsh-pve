/*
 * wshracer's DOS front end: DJGPP + Glide 2 (GLIDE2X.DXE), avoiding stdio printf/fopen bloat to
 * stay comfortably below 96 KB. Tracks simultaneous held racing keys through a chained IRQ 9
 * protected-mode scancode handler, supports optional INT 33h mouse steering, and streams procedural
 * synth audio over Sound Blaster 8-bit auto-init DMA when BLASTER/DSP is present.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <dlfcn.h>
#include <dos.h>
#include <dpmi.h>
#include <fcntl.h>
#include <go32.h>
#include <pc.h>
#include <stdlib.h>
#include <string.h>
#include <sys/farptr.h>
#include <time.h>
#include <unistd.h>

#include "racer.h"
#include "glide2.h"
#include "glide3.h"

static int com1, dos_api = 2;
static const char *dxe_name = "glide2x.dxe";

/* Keep C++ unwind tables (built for i686 with CMOV) out of our Pentium binary */
void __register_frame_info(const void *begin, void *object)
{
	(void)begin, (void)object;
}
void *__deregister_frame_info(const void *begin)
{
	(void)begin;
	return 0;
}
char **__crt0_glob_function(char *arg)
{
	(void)arg;
	return 0;
}
void __crt0_load_environment_file(char *app)
{
	(void)app;
}

uint32_t plat_us(void)
{
	return (uint32_t)(uclock() * (1e6 / UCLOCKS_PER_SEC));
}

static void com1_init(void)
{
	if (_farpeekw(_dos_ds, 0x400) != 0x3f8)
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
	size_t n = strlen(line);
	write(1, line, n);
	write(1, "\r\n", 2);
	if (com1) {
		for (size_t i = 0; i < n; i++)
			com1_put(line[i]);
		com1_put('\r');
		com1_put('\n');
	}
}

void plat_sleep(int ms)
{
	delay((unsigned)ms);
}

/* --- Chained IRQ 9 hardware keyboard matrix + INT 33h mouse ----------------------------------- */

static volatile uint8_t sc_std[128], sc_ext[128], sc_e0;
static _go32_dpmi_seginfo old_irq9, new_irq9;
static int irq9_hooked, has_mouse, msteer;

static void kbd_isr(void)
{
	uint8_t b = inportb(0x60);
	if (b == 0xe0) {
		sc_e0 = 1;
	} else {
		uint8_t down = !(b & 0x80);
		uint8_t code = b & 0x7f;
		if (sc_e0) {
			sc_ext[code] = down;
			sc_e0 = 0;
		} else {
			sc_std[code] = down;
		}
	}
}

static void input_init(void)
{
	_go32_dpmi_lock_data((void *)sc_std, sizeof(sc_std));
	_go32_dpmi_lock_data((void *)sc_ext, sizeof(sc_ext));
	_go32_dpmi_lock_data((void *)&sc_e0, sizeof(sc_e0));
	_go32_dpmi_lock_code((void *)(uintptr_t)kbd_isr, 256);
	_go32_dpmi_get_protected_mode_interrupt_vector(9, &old_irq9);
	new_irq9.pm_offset = (uintptr_t)kbd_isr;
	new_irq9.pm_selector = _go32_my_cs();
	if (_go32_dpmi_chain_protected_mode_interrupt_vector(9, &new_irq9) == 0)
		irq9_hooked = 1;

	__dpmi_regs r;
	memset(&r, 0, sizeof(r));
	r.x.ax = 0;
	__dpmi_int(0x33, &r);
	has_mouse = (r.x.ax == 0xffff);
}

static void input_close(void)
{
	if (irq9_hooked) {
		_go32_dpmi_set_protected_mode_interrupt_vector(9, &old_irq9);
		irq9_hooked = 0;
	}
}

int plat_key(void)
{
	if (!kbhit())
		return 0;
	int k = getkey();
	if (k == 0x148) return RKEY_UP;
	if (k == 0x150) return RKEY_DOWN;
	if (k == 0x14b) return RKEY_LEFT;
	if (k == 0x14d) return RKEY_RIGHT;
	if (k == 'z' || k == 'Z') {
		if (has_mouse) {
			msteer = !msteer;
			__dpmi_regs r;
			memset(&r, 0, sizeof(r));
			r.x.ax = 0x0b;
			__dpmi_int(0x33, &r);
		}
		return 0;
	}
	return k & 0xff;
}

void plat_poll_input(struct plat_input *in)
{
	/* PC XT Set 1 scancodes: W=0x11, S=0x1f, A=0x1e, D=0x20, Q=0x10, E=0x12,
	 * B=0x30, Space=0x39, LShift=0x2a, RShift=0x36, Arrows=0x48/0x50/0x4b/0x4d */
	in->steer_l = (sc_ext[0x4b] || sc_std[0x4b] || sc_std[0x1e]) ? 1 : 0;
	in->steer_r = (sc_ext[0x4d] || sc_std[0x4d] || sc_std[0x20]) ? 1 : 0;
	in->air_l = sc_std[0x10] ? 1 : 0;
	in->air_r = sc_std[0x12] ? 1 : 0;
	in->throttle = (sc_ext[0x48] || sc_std[0x48] || sc_std[0x11]) ? 1 : 0;
	in->brake = (sc_ext[0x50] || sc_std[0x50] || sc_std[0x1f]) ? 1 : 0;
	in->boost = (sc_std[0x39] || sc_std[0x2a] || sc_std[0x36] || sc_std[0x30]) ? 1 : 0;
	in->mdx = in->mdy = 0;
	in->mb_l = in->mb_r = 0;
	if (has_mouse && msteer) {
		__dpmi_regs r;
		memset(&r, 0, sizeof(r));
		r.x.ax = 0x0b;
		__dpmi_int(0x33, &r);
		in->mdx = (int16_t)r.x.cx;
		in->mdy = (int16_t)r.x.dx;
		memset(&r, 0, sizeof(r));
		r.x.ax = 0x03;
		__dpmi_int(0x33, &r);
		in->mb_l = (r.x.bx & 1) ? 1 : 0;
		in->mb_r = (r.x.bx & 2) ? 1 : 0;
	}
}

/* --- Sound Blaster 8-bit Auto-Init DMA streaming audio (IRQ-free) ----------------------------- */

#define SND_MIX racer_audio_mix
#define SND_LOG racer_log
#include "../audio/snd_dos.h"

/* --- wrapper build string & main -------------------------------------------------------------- */

static uint8_t filebuf[256 * 1024];
static int scan_file(const char *path, char *buf, int n)
{
	int fd = open(path, O_RDONLY | O_BINARY);
	if (fd < 0)
		return 0;
	ssize_t len = read(fd, filebuf, sizeof(filebuf));
	close(fd);
	return len > 0 && racer_find_buildstr(filebuf, (uint32_t)len, buf, n);
}

int plat_wrapper_rev(char *buf, int n)
{
	if (scan_file(dxe_name, buf, n))
		return 1;
	const char *lp = getenv("LD_LIBRARY_PATH");
	while (lp && *lp) {
		char path[160];
		int k = 0;
		while (*lp && *lp != ';' && k < 136)
			path[k++] = *lp++;
		if (*lp == ';')
			lp++;
		path[k] = '/';
		strcpy(path + k + 1, dxe_name);
		if (k && scan_file(path, buf, n))
			return 1;
	}
	return 0;
}

static void *dxe_sym(void *dxe, const char *name)
{
	char u[64];
	u[0] = '_';
	strncpy(u + 1, name, sizeof(u) - 2);
	u[sizeof(u) - 1] = 0;
	void *p = dlsym(dxe, u);
	if (!p)
		p = dlsym(dxe, name);
	if (!p) {
		char line[160];
		racer_fmt(line, sizeof(line), "WSHRACER: ERROR %s has no %s", dxe_name, name);
		plat_out(line);
		plat_out("WSHRACER: CLOSED");
		_exit(2);
	}
	return p;
}

int main(int argc, char **argv)
{
	int nocom = 0, audiotest = 0;
	for (int i = 1; i < argc; i++) {
		nocom |= !strcmp(argv[i], "-nocom");
		audiotest |= !strcmp(argv[i], "-audiotest");
		if (!strcmp(argv[i], "-api") && i + 1 < argc) {
			const char *v = argv[++i];
			dos_api = !strcmp(v, "glide2") ? 2 : !strcmp(v, "glide3") ? 3 : -1;
		}
	}
	if (!nocom)
		com1_init();
	if (dos_api < 0) {
		plat_out("WSHRACER: ERROR -api on DOS is glide2 or glide3");
		plat_out("WSHRACER: CLOSED");
		return 2;
	}
	dxe_name = dos_api == 3 ? "glide3x.dxe" : "glide2x.dxe";
	if (!audiotest) {
		void *dxe = dlopen(dxe_name, RTLD_GLOBAL);
		if (!dxe) {
			char line[160];
			racer_fmt(line, sizeof(line), "WSHRACER: ERROR dlopen %s: %.60s", dxe_name, dlerror());
			plat_out(line);
			plat_out("WSHRACER: CLOSED");
			return 2;
		}
		if (dos_api == 3) {
#define G3_SYM(ret, name, args, bytes) *(void **)&g3.name = dxe_sym(dxe, #name);
			GLIDE3_FUNCS(G3_SYM)
		} else {
#define G2_SYM(ret, name, args, bytes) *(void **)&g2.name = dxe_sym(dxe, #name);
			GLIDE2_FUNCS(G2_SYM)
		}
	}
	input_init();
	int rc = racer_main(argc, argv, dos_api == 3 ? &glide3_backend : &glide2_backend);
	input_close();
	return rc;
}
