/*
 * mesa-guest: the /init of a minimal Linux guest that drives qemu-3dfx's MESA GL pass-through (the
 * "mesapt" device, hw/mesa), with no Windows and no game. qemu-3dfx has no Linux guest wrapper for
 * it (only the Windows OPENGL32.DLL, wrappers/mesa/src/wrapgl32.c), so this program speaks the
 * device's protocol itself, the way that DLL does, for the few calls it needs:
 *
 *   - three regions through /dev/mem: the MMIO page (MESAPT_MM_BASE), the shared FIFO/argument
 *     memory (MESA_FIFO_BASE) and the frame/texture memory (MESA_FBTM_BASE);
 *   - "DLL attach": the wrapper's revision at the end of the frame memory, then 0xA0320 to 0xFBC
 *     (QEMU loads the host's libGL.so.1 and answers 0x320a0);
 *   - wglChoosePixelFormat (0xFEC, waits for the window: 0xFB8), wglSetPixelFormat (0xFE4),
 *     wglCreateContext (0xFFC) and wglMakeCurrent (0xFF8), each a write of MESAGL_MAGIC with its
 *     arguments in the last page of the shared memory: QEMU makes a GLX context on the VM's SDL
 *     window;
 *   - GL calls one at a time: the arguments in mfifo[2...], the function's number (mglfunci.h) to
 *     0xFC0, the return value read back from 0xFC0 (no batching in the FIFO);
 *   - glReadPixels with no pack buffer: QEMU reads into the frame memory, the guest copies from it;
 *   - wglSwapBuffers (0xFF0), then wglMakeCurrent(0), wglDeleteContext and "DLL detach" (0xD0320).
 *
 * It sets the std VGA to 640x480 through the Bochs VBE registers first (the GL window is the VM's
 * window, which takes the size of the guest's display), draws the scene of
 * packages/wsh-openglide/tests/scene.h (the Glide test's, here with glBegin/glColor3f/glVertex2f in
 * normalised coordinates), reads the back buffer before the swap, checks the probes, prints one line
 * per probe and a verdict on the console:
 *
 *   MESA-GUEST: PASS | MESA-GUEST: FAIL <n> | MESA-GUEST: ERROR <what>
 *
 * then holds the frame for a few seconds (for a capture of the window on the host) and powers the
 * VM off. i386, static (the protocol passes 32-bit guest addresses). Copyright 2026 WsHosting ENK,
 * GPL-3.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/io.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <unistd.h>

#include "mglfuncs.h" /* qemu-3dfx qemu-1/hw/mesa: addresses, sizes, MESAGL_MAGIC, FEnum_gl* */
#include "scene.h"

#define MESAPT_MM_BASE 0xefffe000 /* the port's include/hw/i386/pc.h */
#define MESAVER 0x320		  /* wrapgl32.c */

static const char rev_[ALIGNED(1) + 1] = __REV__; /* "<7 hex digits>-", the host binary's */

static volatile uint32_t *ptm; /* the MMIO page */
static uint32_t *mfifo;	       /* shared memory: FIFO, then data; the last pages carry wgl arguments */
static uint32_t *fbtm;	       /* frame/texture memory: glReadPixels lands here */
static uint32_t *pt;	       /* &mfifo[1]: pt[1...] are a call's arguments */

static uint8_t pixels[W * H * 4];

static void finish(const char *verdict, int hold)
{
	printf("MESA-GUEST: %s\n", verdict);
	fflush(stdout);
	sync();
	sleep(hold);
	reboot(RB_POWER_OFF);
	for (;;)
		pause();
}

static void *map(int fd, uint32_t paddr, uint32_t len)
{
	void *p = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, paddr);
	if (p == MAP_FAILED) {
		printf("mmap of %#x (%#x bytes): %s\n", paddr, len, strerror(errno));
		return NULL;
	}
	return p;
}

/* the last page of the shared memory, where the wgl calls take their arguments */
static uint32_t *wgl_args(void)
{
	return &mfifo[(MGLSHM_SIZE - PAGE_SIZE) >> 2];
}

static void mmio_write(uint32_t reg, uint32_t val)
{
	__sync_synchronize();
	ptm[reg >> 2] = val;
	__sync_synchronize();
}

/* One GL call, executed at once: arguments as 32-bit words (floats by their bits) */
static uint32_t gl(uint32_t fenum, int nargs, const uint32_t *args)
{
	for (int i = 0; i < nargs; i++)
		pt[1 + i] = args[i];
	mmio_write(0xFC0, fenum);
	return ptm[0xFC0 >> 2];
}
static uint32_t f2u(float f)
{
	uint32_t u;
	memcpy(&u, &f, sizeof(u));
	return u;
}
#define GL(name, ...) gl(FEnum_##name, sizeof((uint32_t[]){0, ##__VA_ARGS__}) / 4 - 1, (uint32_t[]){0, ##__VA_ARGS__} + 1)

/* The std VGA to a 640x480x32 linear mode (Bochs VBE: index 0x1ce, data 0x1cf) */
static int vga_640x480(void)
{
	static const uint16_t regs[][2] = {{4, 0}, {1, W}, {2, H}, {3, 32}, {4, 0x41}};
	if (ioperm(0x1ce, 3, 1)) /* 16-bit accesses: 0x1ce-0x1cf and 0x1cf-0x1d0 */
		return -1;
	for (size_t i = 0; i < sizeof(regs) / sizeof(regs[0]); i++) {
		outw(regs[i][0], 0x1ce);
		outw(regs[i][1], 0x1cf);
	}
	outw(1, 0x1ce);
	return inw(0x1cf) == W ? 0 : -1;
}

static uint8_t read_px(int x, int y, int c)
{
	return pixels[((H - 1 - y) * W + x) * 4 + c]; /* GL rows go bottom up */
}

/* A coarse map of the frame on the console, for the log (as glide-guest.c) */
static void print_map(void)
{
	printf("back buffer, 40x15:\n");
	for (int y = 16; y < H; y += 32) {
		char row[41];
		for (int x = 8, i = 0; x < W; x += 16, i++) {
			int r = read_px(x, y, 0), g = read_px(x, y, 1), b = read_px(x, y, 2);
			row[i] = (r < 16 && g < 16 && b < 16)                 ? ' '
				 : (r < 16 && g < 16 && b > 100 && b < 160) ? '.'
				 : (r > g && r > b)                         ? 'r'
				 : (g > r && g > b)                         ? 'g'
				 : (b > r && b > g)                         ? 'b'
									    : '?';
		}
		row[40] = 0;
		printf("  |%s|\n", row);
	}
}

static void triangle(const float pos[3][2], const float rgb[3][3])
{
	GL(glBegin, 0x0004 /* GL_TRIANGLES */);
	for (int i = 0; i < 3; i++) {
		GL(glColor3f, f2u(rgb[i][0] / 255), f2u(rgb[i][1] / 255), f2u(rgb[i][2] / 255));
		/* scene.h's 640x480 upper-left coordinates to normalised device coordinates */
		GL(glVertex2f, f2u(pos[i][0] / (W / 2) - 1), f2u(1 - pos[i][1] / (H / 2)));
	}
	GL(glEnd);
}

int main(void)
{
	char verdict[128];

	mkdir("/dev", 0755);
	if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) && errno != EBUSY)
		finish("ERROR mount devtmpfs", 0);
	setvbuf(stdout, NULL, _IOLBF, 0);
	printf("mesa-guest: MESA GL through qemu-3dfx's mesapt, wrapper revision %.8s\n", rev_);

	if (vga_640x480())
		finish("ERROR setting the VGA to 640x480", 0);
	sleep(1); /* QEMU's display (the SDL window) follows the guest's mode on its next refresh */

	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0)
		finish("ERROR /dev/mem", 0);
	ptm = map(fd, MESAPT_MM_BASE, PAGE_SIZE);
	mfifo = map(fd, MESA_FIFO_BASE, MGLSHM_SIZE);
	fbtm = map(fd, MESA_FBTM_BASE, MGLFBT_SIZE);
	if (!ptm || !mfifo || !fbtm)
		finish("ERROR mapping the mesapt regions", 0);

	/* DLL attach (InitMesaPTMMBase(), DllMain() in wrapgl32.c) */
	pt = &mfifo[1];
	mfifo[0] = FIRST_FIFO;
	mfifo[MAX_FIFO] = ALIGNED(1) >> 2;
	pt[0] = (uint32_t)(uintptr_t)(ptm + (0xFC0 >> 2));
	memcpy(&fbtm[(MGLFBT_SIZE - ALIGNBO(1)) >> 2], rev_, ALIGNED(1));
	mmio_write(0xFBC, (0xA0 << 12) | MESAVER);
	uint32_t ver = ptm[0xFBC >> 2];
	if (ver != ((MESAVER << 8) | 0xA0)) {
		snprintf(verdict, sizeof(verdict), "ERROR init: %#x (revision refused, or no libGL.so.1 on the host)", ver);
		finish(verdict, 0);
	}
	printf("init: ok (%#x)\n", ver);

	/* wglChoosePixelFormat: display timer off (xppfd[1] = 0), a zero PIXELFORMATDESCRIPTOR */
	uint32_t *a = wgl_args();
	memset(a, 0, 64);
	mmio_write(0xFEC, MESAGL_MAGIC);
	for (int i = 0; !ptm[0xFB8 >> 2]; i++) { /* the window is made on QEMU's main loop */
		if (i == 10000000)
			finish("ERROR no GL window (glwnd_ready)", 0);
	}
	int fmt = (int)ptm[0xFEC >> 2];
	printf("wglChoosePixelFormat: %d\n", fmt);
	if (fmt <= 0)
		finish("ERROR wglChoosePixelFormat", 0);

	/* wglSetPixelFormat */
	memset(a, 0, 64);
	a[0] = (uint32_t)fmt;
	a[1] = (uint32_t)(uintptr_t)ptm;
	mmio_write(0xFE4, MESAGL_MAGIC);
	if (ptm[0xFE4 >> 2] != MESAGL_MAGIC)
		finish("ERROR wglSetPixelFormat", 0);
	printf("wglSetPixelFormat: ok\n");

	/* wglCreateContext (any DC that isn't a pbuffer's), wglMakeCurrent of the context it returns:
	 * MESAGL_MAGIC, with the wrapper's revision and build string after it */
	a[0] = MESAGL_HWNDC;
	mmio_write(0xFFC, MESAGL_MAGIC);
	a[0] = MESAGL_MAGIC;
	memcpy(&a[1], rev_, ALIGNED(1));
	strcpy((char *)&a[1] + ALIGNED(1), "mesa-guest ");
	mmio_write(0xFF8, MESAGL_MAGIC);
	printf("wglCreateContext, wglMakeCurrent: done\n");

	/* The scene, as glide-render.c and glide-guest.c draw it */
	GL(glViewport, 0, 0, W, H);
	GL(glClearColor, f2u(0), f2u(0), f2u(128.0f / 255), f2u(1));
	GL(glClear, 0x4000 /* GL_COLOR_BUFFER_BIT */);
	triangle(red_tri, red_rgb);
	triangle(green_tri, green_rgb);
	triangle(gouraud_tri, gouraud_rgb);
	GL(glFinish);
	GL(glReadPixels, 0, 0, W, H, 0x1908 /* GL_RGBA */, 0x1401 /* GL_UNSIGNED_BYTE */, 0);
	memcpy(pixels, fbtm, sizeof(pixels));
	uint32_t err = GL(glGetError);
	printf("glGetError: %#x\n", err);

	int failed = err != 0;
	if (scene_check("guest glReadPixels", read_px, 1)) {
		print_map();
		failed++;
	}

	/* wglSwapBuffers: the frame goes to the window, the host captures it now */
	uint32_t *swap = &mfifo[(MGLSHM_SIZE - ALIGNED(1)) >> 2];
	swap[0] = 0;
	swap[1] = 0;
	mmio_write(0xFF0, MESAGL_MAGIC);
	printf("wglSwapBuffers: %#x\n", swap[0]);
	printf("MESA-GUEST: FRAME\n");
	sleep(5);

	/* wglMakeCurrent(0), wglDeleteContext, DLL detach */
	a[0] = 0;
	mmio_write(0xFF8, MESAGL_MAGIC);
	mmio_write(0xFF4, MESAGL_MAGIC);
	mmio_write(0xFBC, (0xD0 << 12) | MESAVER);
	memset(&fbtm[(MGLFBT_SIZE - ALIGNBO(1)) >> 2], 0, ALIGNED(1));
	mfifo[1] = 0;

	if (failed)
		snprintf(verdict, sizeof(verdict), "FAIL %d", failed);
	else
		snprintf(verdict, sizeof(verdict), "PASS");
	finish(verdict, 1);
	return 0;
}
