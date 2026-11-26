/*
 * VBELIST.EXE: lists the VESA BIOS Extensions modes a DOS guest's video BIOS offers (with qemu-3dfx's
 * VMs, SeaVGABIOS on QEMU's std VGA), to compare with what a DOS game or Glide program asks for.
 * A DJGPP program; built by build.sh next to GLIDEDOS.EXE.
 *
 * It calls INT 10h AX=4F00 with a "VBE2" signature and prints the VBE version, the video memory and
 * the OEM strings, then AX=4F01 for each mode of the BIOS's mode list:
 *
 *   VBELIST: VBE 3.0 memory=131072 KB oem="..." vendor="..." product="..." rev="..."
 *   VBELIST: MODE 0x0118 1024x768x32 model=direct lfb=yes supported=yes attr=0x00bb
 *   VBELIST: MODES 123 listed, 120 supported, 118 with a linear frame buffer
 *
 * model is the memory model (text, cga, planar, packed, direct, yuv, or its number), lfb whether
 * the mode offers a linear frame buffer (attribute bit 7), supported the attribute's bit 0 (the
 * hardware can show the mode with this memory and monitor). Output goes to standard output and to
 * COM1 (115200 8N1, written to the UART directly); -nocom: standard output only (for a batch file
 * that has sent the console to COM1 already). Exit status 0, or 1 without VBE.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <dpmi.h>
#include <go32.h>
#include <pc.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/farptr.h>
#include <sys/movedata.h>

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

static void com1_init(void)
{
	/* the BIOS's COM1 base (0 without a serial port), then 115200 8N1 with the FIFO on */
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

static void out(const char *fmt, ...)
{
	char line[256];
	va_list ap;
	va_start(ap, fmt);
	int n = vsnprintf(line, sizeof(line) - 2, fmt, ap);
	va_end(ap);
	if (n < 0)
		return;
	printf("VBELIST: %s\n", line);
	fflush(stdout);
	if (com1) {
		for (const char *s = "VBELIST: "; *s; s++)
			com1_put(*s);
		for (const char *s = line; *s; s++)
			com1_put(*s);
		com1_put('\r');
		com1_put('\n');
	}
}

/* A real-mode far pointer (segment:offset) as a linear address */
static unsigned long far_lin(unsigned long segoff)
{
	return ((segoff >> 16) << 4) + (segoff & 0xffff);
}

/* A string at a real-mode far pointer, printable ASCII only */
static void far_str(unsigned long segoff, char *buf, int n)
{
	unsigned long a = far_lin(segoff);
	int i = 0;
	if (segoff)
		for (; i < n - 1; i++) {
			unsigned char c = _farpeekb(_dos_ds, a + i);
			if (!c)
				break;
			buf[i] = (char)(c >= 32 && c < 127 && c != '"' ? c : '?');
		}
	buf[i] = 0;
}

static int vbe_call(int ax, int cx, __dpmi_regs *r)
{
	memset(r, 0, sizeof(*r));
	r->x.ax = (unsigned short)ax;
	r->x.cx = (unsigned short)cx;
	r->x.es = __tb >> 4;
	r->x.di = __tb & 0x0f;
	__dpmi_int(0x10, r);
	return r->x.ax == 0x004f;
}

int main(int argc, char **argv)
{
	int nocom = 0;
	for (int i = 1; i < argc; i++)
		nocom |= !strcmp(argv[i], "-nocom");
	if (!nocom)
		com1_init();

	unsigned char info[512];
	__dpmi_regs r;
	memset(info, 0, sizeof(info));
	memcpy(info, "VBE2", 4);
	dosmemput(info, sizeof(info), __tb);
	if (!vbe_call(0x4f00, 0, &r)) {
		out("ERROR no VBE (INT 10h AX=4F00 returned AX=%04x)", r.x.ax);
		return 1;
	}
	dosmemget(__tb, sizeof(info), info);
	if (memcmp(info, "VESA", 4)) {
		out("ERROR INT 10h AX=4F00 returned no VESA signature");
		return 1;
	}
	unsigned ver = info[4] | info[5] << 8, mem64k = info[0x12] | info[0x13] << 8;
	unsigned long oem, vendor = 0, product = 0, rev = 0, list;
	memcpy(&oem, info + 0x06, 4);
	memcpy(&list, info + 0x0e, 4);
	if (ver >= 0x200) {
		memcpy(&vendor, info + 0x16, 4);
		memcpy(&product, info + 0x1a, 4);
		memcpy(&rev, info + 0x1e, 4);
	}
	/* The mode list and the strings before any output: they may lie in the transfer buffer (the
	 * info block's own reserved area), which DOS output through stdio and 4F01 overwrite */
	static unsigned short modes[1024];
	int nmodes = 0;
	unsigned long a = far_lin(list);
	while (nmodes < 1024) {
		unsigned short m = _farpeekw(_dos_ds, a + 2 * nmodes);
		if (m == 0xffff)
			break;
		modes[nmodes++] = m;
	}
	char s_oem[64], s_vendor[64], s_product[64], s_rev[64];
	far_str(oem, s_oem, sizeof(s_oem));
	far_str(vendor, s_vendor, sizeof(s_vendor));
	far_str(product, s_product, sizeof(s_product));
	far_str(rev, s_rev, sizeof(s_rev));
	out("VBE %u.%u memory=%u KB oem=\"%s\" vendor=\"%s\" product=\"%s\" rev=\"%s\"", ver >> 8, ver & 0xff,
	    mem64k * 64, s_oem, s_vendor, s_product, s_rev);

	static const char *models[] = {"text", "cga", "hercules", "planar", "packed", "nonchain4", "direct", "yuv"};
	int supported = 0, lfbs = 0;
	for (int i = 0; i < nmodes; i++) {
		unsigned char mi[256];
		memset(mi, 0, sizeof(mi));
		dosmemput(mi, sizeof(mi), __tb);
		if (!vbe_call(0x4f01, modes[i], &r)) {
			out("MODE 0x%04x no information (AX=%04x)", modes[i], r.x.ax);
			continue;
		}
		dosmemget(__tb, sizeof(mi), mi);
		unsigned attr = mi[0] | mi[1] << 8, w = mi[0x12] | mi[0x13] << 8, h = mi[0x14] | mi[0x15] << 8;
		unsigned bpp = mi[0x19], model = mi[0x1b];
		int lfb = (attr & 0x80) != 0, sup = (attr & 0x01) != 0;
		char mname[16];
		if (model < sizeof(models) / sizeof(models[0]))
			snprintf(mname, sizeof(mname), "%s", models[model]);
		else
			snprintf(mname, sizeof(mname), "%u", model);
		out("MODE 0x%04x %ux%ux%u model=%s lfb=%s supported=%s attr=0x%04x", modes[i], w, h, bpp, mname,
		    lfb ? "yes" : "no", sup ? "yes" : "no", attr);
		supported += sup;
		lfbs += lfb;
	}
	out("MODES %d listed, %d supported, %d with a linear frame buffer", nmodes, supported, lfbs);
	return 0;
}
