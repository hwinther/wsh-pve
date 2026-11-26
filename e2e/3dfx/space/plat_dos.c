/*
 * wshspace's DOS front end: DJGPP + Glide 2 (GLIDE2X.DXE), avoiding stdio printf/fopen bloat to
 * stay comfortably below 96 KB. Tracks simultaneous held flight keys through a chained IRQ 9
 * protected-mode scancode handler, supports optional INT 33h mouse flight, and streams procedural
 * synth audio over Sound Blaster 8-bit auto-init DMA when BLASTER/DSP is present (stereo at
 * exactly 22050 Hz on a Sound Blaster 16, mono on older DSPs).
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

#include "space.h"
#include "glide2.h"

#define DECL(ret, name, args, bytes) ret name args;
GLIDE2_FUNCS(DECL)
#define FILL(ret, name, args, bytes) g2.name = name;

static int com1;

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
/* Omit unused wildcard filename globbing and DJGPP.ENV parser from DJGPP's static crt0 */
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
static int irq9_hooked, has_mouse, mlook;

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
		return -1;
	int k = getkey();
	if (k == 0x148) return KEY_UP;
	if (k == 0x150) return KEY_DOWN;
	if (k == 0x14b) return KEY_LEFT;
	if (k == 0x14d) return KEY_RIGHT;
	if (k == 'v' || k == 'V') {
		if (has_mouse) {
			mlook = !mlook;
			__dpmi_regs r;
			memset(&r, 0, sizeof(r));
			r.x.ax = 0x0b;
			__dpmi_int(0x33, &r);
		}
		return -1;
	}
	return k & 0xff;
}

void plat_poll(struct plat_input *in)
{
	uint32_t h = 0;
	/* PC XT Set 1 scancodes: W=0x11, S=0x1f, A=0x1e, D=0x20, Q=0x10, E=0x12,
	 * B=0x30, Space=0x39, LShift=0x2a, RShift=0x36, Arrows=0x48/0x50/0x4b/0x4d */
	if (sc_ext[0x48] || sc_std[0x48]) h |= IN_PITCH_UP;
	if (sc_ext[0x50] || sc_std[0x50]) h |= IN_PITCH_DOWN;
	if (sc_ext[0x4b] || sc_std[0x4b]) h |= IN_YAW_LEFT;
	if (sc_ext[0x4d] || sc_std[0x4d]) h |= IN_YAW_RIGHT;
	if (sc_std[0x1e] || sc_std[0x10]) h |= IN_ROLL_LEFT;
	if (sc_std[0x20] || sc_std[0x12]) h |= IN_ROLL_RIGHT;
	if (sc_std[0x11])                 h |= IN_THRUST;
	if (sc_std[0x1f])                 h |= IN_BRAKE;
	if (sc_std[0x2a] || sc_std[0x36] || sc_std[0x30]) h |= IN_BOOST;
	if (sc_std[0x39])                 h |= IN_FIRE;

	in->mdx = in->mdy = 0;
	in->mlook = mlook;
	if (has_mouse && mlook) {
		__dpmi_regs r;
		memset(&r, 0, sizeof(r));
		r.x.ax = 0x0b;
		__dpmi_int(0x33, &r);
		in->mdx = (int16_t)r.x.cx;
		in->mdy = (int16_t)r.x.dx;
		memset(&r, 0, sizeof(r));
		r.x.ax = 0x03;
		__dpmi_int(0x33, &r);
		if (r.x.bx & 1) h |= IN_FIRE;
		if (r.x.bx & 2) h |= IN_THRUST;
	}
	in->held = h;
}

/* --- Sound Blaster 8-bit Auto-Init DMA streaming audio (IRQ-free) ----------------------------- */

#define SND_MIX space_audio_mix
#define SND_LOG space_log
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
	return len > 0 && space_find_buildstr(filebuf, (uint32_t)len, buf, n);
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
	int nocom = 0;
	for (int i = 1; i < argc; i++)
		nocom |= !strcmp(argv[i], "-nocom");
	if (!nocom)
		com1_init();
	if (!dlopen("glide2x.dxe", RTLD_GLOBAL)) {
		char line[160];
		space_fmt(line, sizeof(line), "WSHSPACE: ERROR dlopen glide2x.dxe: %.60s", dlerror());
		plat_out(line);
		plat_out("WSHSPACE: CLOSED");
		return 2;
	}
	GLIDE2_FUNCS(FILL)
	input_init();
	int rc = space_main(argc, argv, &glide2_backend);
	input_close();
	return rc;
}
