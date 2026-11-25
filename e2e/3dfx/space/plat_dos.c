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

#define SB_RATE 22050
#define SB_BUF  32768 /* the DMA ring: 743 ms of stereo, 1.5 s of mono */
#define SB_LEAD 4096  /* frames mixed ahead of the DMA (186 ms): the longest a poll may come late */

/* sb_stereo: a DSP 4.x (Sound Blaster 16) plays 8-bit stereo at exactly SB_RATE (commands 41h and
 * C6h, still on the 8-bit DMA channel); older DSPs mono at the time constant's 22222 Hz.
 *
 * Nothing listens to the card's interrupt: plat_audio_tick() reads where the DMA is and mixes up
 * to SB_LEAD frames ahead of it. It counts the bytes written and the bytes the DMA has taken in
 * total, so a reading can never make it write over what hasn't played yet: one that runs ahead
 * of the time since the last poll is ignored (sb_glitches), and a poll so late that the DMA may
 * have passed the writer starts the lead again from the DMA (sb_resyncs: the card has played old
 * samples then; the only case that loses sound). */
static int sb_base = 0x220, sb_dma = 1, sb_on, sb_dos_sel, sb_stereo;
static uint32_t sb_phys, sb_written, sb_played, sb_last_us, sb_max_gap_us;
static int sb_write_pos, sb_last_cur;
static unsigned sb_polls, sb_torn, sb_glitches, sb_resyncs, sb_clock_back;
static int16_t mix_tmp[512 * 2];

static void sb_write_dsp(uint8_t v)
{
	for (int i = 0; i < 30000 && (inportb(sb_base + 0x0c) & 0x80); i++)
		;
	outportb(sb_base + 0x0c, v);
}

static int sb_read_dsp(void)
{
	for (int i = 0; i < 30000; i++)
		if (inportb(sb_base + 0x0e) & 0x80)
			return inportb(sb_base + 0x0a);
	return -1;
}

static int sb_reset_dsp(void)
{
	outportb(sb_base + 0x06, 1);
	delay(3);
	outportb(sb_base + 0x06, 0);
	for (int i = 0; i < 30000; i++) {
		if (inportb(sb_base + 0x0e) & 0x80) {
			if (inportb(sb_base + 0x0a) == 0xaa)
				return 1;
		}
	}
	return 0;
}

/* Where the DMA is in the ring. The 8237's address comes a byte at a time and the DMA may move
 * between the two: read until the high byte is the same before and after a low byte. */
static int sb_dma_pos(void)
{
	int lo = 0, hi = -1, prev;
	for (int i = 0; i < 8; i++) {
		prev = hi;
		outportb(0x0c, 0);
		lo = inportb(sb_dma * 2);
		hi = inportb(sb_dma * 2);
		if (hi == prev)
			break;
		sb_torn += prev >= 0;
	}
	return (int)(((uint32_t)((hi << 8) | lo) - (sb_phys & 0xffffU)) & (SB_BUF - 1));
}

/* `bytes` (whole frames) of mixed sound into the ring at sb_write_pos */
static void sb_fill(int bytes)
{
	while (bytes > 0) {
		int chunk = bytes >> sb_stereo;
		if (chunk > 512)
			chunk = 512;
		space_audio_mix(mix_tmp, chunk, SB_RATE);
		for (int i = 0; i < chunk; i++) {
			for (int c = 0; c <= sb_stereo; c++) {
				int u8 = (mix_tmp[i * 2 + c] >> 8) + 128;
				if (!sb_stereo) {
					u8 = (((int)mix_tmp[i * 2] + (int)mix_tmp[i * 2 + 1]) >> 9) + 128;
					if (u8 < 0) u8 = 0;
					if (u8 > 255) u8 = 255;
				}
				_farpokeb(_dos_ds, sb_phys + (uint32_t)sb_write_pos, (uint8_t)u8);
				sb_write_pos = (sb_write_pos + 1) & (SB_BUF - 1);
			}
		}
		bytes -= chunk << sb_stereo;
		sb_written += (uint32_t)chunk << sb_stereo;
	}
}

void plat_audio_init(int enable)
{
	if (!enable)
		return;
	const char *bl = getenv("BLASTER");
	if (bl) {
		for (const char *p = bl; *p; p++) {
			if ((*p == 'A' || *p == 'a') && p[1] >= '0' && p[1] <= '9') {
				int v = 0;
				for (const char *q = p + 1; (*q >= '0' && *q <= '9') || (*q >= 'a' && *q <= 'f') || (*q >= 'A' && *q <= 'F'); q++)
					v = v * 16 + (*q <= '9' ? *q - '0' : (*q | 32) - 'a' + 10);
				if (v >= 0x200 && v <= 0x280)
					sb_base = v;
			}
			if ((*p == 'D' || *p == 'd') && p[1] >= '0' && p[1] <= '3')
				sb_dma = p[1] - '0';
		}
	}
	if (sb_on || !sb_reset_dsp())
		return;
	sb_write_dsp(0xe1); /* DSP version: major, minor */
	sb_stereo = sb_read_dsp() >= 4;
	sb_read_dsp();

	/* Allocate 2 * SB_BUF (64 KB = 4096 paragraphs) so one 32 KB half is guaranteed not to cross a 64 KB DMA page */
	int seg = __dpmi_allocate_dos_memory((SB_BUF * 2) >> 4, &sb_dos_sel);
	if (seg < 0)
		return;
	uint32_t phys = (uint32_t)seg << 4;
	if (((phys & 0xffffU) + SB_BUF) > 0x10000U)
		phys += SB_BUF;
	sb_phys = phys;

	for (int i = 0; i < SB_BUF; i++)
		_farpokeb(_dos_ds, sb_phys + (uint32_t)i, 0x80);
	/* the lead mixed before the card starts at the ring's start */
	sb_write_pos = sb_last_cur = 0;
	sb_written = sb_played = sb_polls = sb_torn = sb_glitches = sb_resyncs = sb_clock_back = sb_max_gap_us = 0;
	sb_fill(SB_LEAD << sb_stereo);

	/* Program 8237 ISA DMA controller in single/auto-init read mode */
	static const uint8_t page_port[4] = {0x87, 0x83, 0x81, 0x82};
	outportb(0x0a, 4 | sb_dma);
	outportb(0x0c, 0);
	outportb(0x0b, 0x58 | sb_dma);
	outportb(sb_dma * 2, (uint8_t)(sb_phys & 0xffU));
	outportb(sb_dma * 2, (uint8_t)((sb_phys >> 8) & 0xffU));
	outportb(page_port[sb_dma & 3], (uint8_t)((sb_phys >> 16) & 0xffU));
	outportb(sb_dma * 2 + 1, (uint8_t)((SB_BUF - 1) & 0xffU));
	outportb(sb_dma * 2 + 1, (uint8_t)(((SB_BUF - 1) >> 8) & 0xffU));
	outportb(0x0a, sb_dma);

	sb_write_dsp(0xd1); /* speaker on */
	if (sb_stereo) {
		/* SB16: output rate, then 8-bit auto-init playback with the FIFO, unsigned stereo; the
		 * length (bytes - 1) only sets how often it interrupts, and nothing here listens */
		sb_write_dsp(0x41);
		sb_write_dsp(SB_RATE >> 8);
		sb_write_dsp(SB_RATE & 0xff);
		sb_write_dsp(0xc6);
		sb_write_dsp(0x20);
		sb_write_dsp((SB_BUF / 2 - 1) & 0xff);
		sb_write_dsp((SB_BUF / 2 - 1) >> 8);
	} else {
		/* 22050 Hz time constant (211, really 22222 Hz), 2 KB blocks, auto-init 8-bit mono */
		sb_write_dsp(0x40);
		sb_write_dsp((uint8_t)(256 - 1000000 / SB_RATE));
		sb_write_dsp(0x48);
		sb_write_dsp(0xff);
		sb_write_dsp(0x07);
		sb_write_dsp(0x1c);
	}
	sb_last_us = plat_us();
	sb_on = 1;
}

void plat_audio_tick(void)
{
	if (!sb_on)
		return;
	uint32_t now = plat_us(), gap = now - sb_last_us;
	int cur = sb_dma_pos(), bps = SB_RATE << sb_stereo;
	int adv = (cur - sb_last_cur) & (SB_BUF - 1), lead = SB_LEAD << sb_stereo;
	sb_polls++;
	/* the most the DMA can have taken since the last poll (+5 % and a 1 KB margin); uclock() can
	 * step back by tens of ms (seen without a memory manager): then the time says nothing, and
	 * any advance short of a lap is taken */
	uint32_t most = SB_BUF - lead - 1;
	if ((int32_t)gap >= 0) {
		if (gap > sb_max_gap_us)
			sb_max_gap_us = gap;
		most = (uint32_t)((double)gap * bps * 1.05e-6) + 1024;
	} else {
		sb_clock_back++;
	}
	if (most < (uint32_t)(SB_BUF - lead)) {
		if ((uint32_t)adv > most) {
			sb_glitches++; /* a reading that can't be right: wait for the next one */
			return;
		}
		sb_played += (uint32_t)adv;
	} else {
		sb_played = sb_written + 1; /* so late the DMA may have gone round: start again */
	}
	sb_last_cur = cur;
	sb_last_us = now;
	if ((int32_t)(sb_written - sb_played) < 0) {
		sb_resyncs++;
		sb_write_pos = cur & ~sb_stereo;
		sb_played = sb_written;
	}
	int todo = (lead - (int)(sb_written - sb_played)) & ~sb_stereo;
	if (todo > (64 << sb_stereo))
		sb_fill(todo);
}

void plat_audio_close(void)
{
	if (!sb_on)
		return;
	space_log("AUDIO sb%s %d Hz: %u polls, longest gap %u ms, %u torn reads, %u glitches, %u clock steps back, %u resyncs",
		  sb_stereo ? "16 stereo" : " mono", sb_stereo ? SB_RATE : 22222, sb_polls,
		  sb_max_gap_us / 1000U, sb_torn, sb_glitches, sb_clock_back, sb_resyncs);
	sb_write_dsp(0xd0);
	sb_write_dsp(0xd3);
	sb_reset_dsp();
	outportb(0x0a, 4 | sb_dma);
	__dpmi_free_dos_memory(sb_dos_sel);
	sb_on = 0;
}

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
