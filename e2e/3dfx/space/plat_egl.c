/*
 * Host-side Mesa surfaceless EGL runner for wshspace's OpenGL backend (no X server or GPU needed),
 * used to run -check, -bench and automated gameplay screenshot captures:
 *
 *   gcc -O2 -o wshspace-egl space.c be_gl.c plat_egl.c /usr/lib/x86_64-linux-gnu/libEGL.so.1 \
 *       /usr/lib/x86_64-linux-gnu/libGL.so.1
 *   ./wshspace-egl -check -bench 300
 *   WSHSPACE_SHOTS=/tmp ./wshspace-egl -auto -time 10
 *
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#include "space.h"
#include "gl11.h"

#define DECL(ret, name, args) ret name args;
GL_FUNCS(DECL)
#define FILL(ret, name, args) glf.name = name;

typedef void *EGLDisplay, *EGLConfig, *EGLSurface, *EGLContext;
typedef int32_t EGLint;
EGLDisplay eglGetPlatformDisplay(unsigned platform, void *native, const intptr_t *attribs);
unsigned eglInitialize(EGLDisplay d, EGLint *major, EGLint *minor);
unsigned eglChooseConfig(EGLDisplay d, const EGLint *attribs, EGLConfig *configs, EGLint n, EGLint *num);
EGLSurface eglCreatePbufferSurface(EGLDisplay d, EGLConfig c, const EGLint *attribs);
unsigned eglBindAPI(unsigned api);
EGLContext eglCreateContext(EGLDisplay d, EGLConfig c, EGLContext share, const EGLint *attribs);
unsigned eglMakeCurrent(EGLDisplay d, EGLSurface draw, EGLSurface read, EGLContext ctx);
unsigned eglSwapBuffers(EGLDisplay d, EGLSurface s);
unsigned eglDestroySurface(EGLDisplay d, EGLSurface s);
unsigned eglDestroyContext(EGLDisplay d, EGLContext c);
unsigned eglTerminate(EGLDisplay d);

#define EGL_PLATFORM_SURFACELESS_MESA 0x31dd
#define EGL_SURFACE_TYPE 0x3033
#define EGL_PBUFFER_BIT 0x0001
#define EGL_RENDERABLE_TYPE 0x3040
#define EGL_OPENGL_BIT 0x0008
#define EGL_RED_SIZE 0x3024
#define EGL_GREEN_SIZE 0x3023
#define EGL_BLUE_SIZE 0x3022
#define EGL_DEPTH_SIZE 0x3025
#define EGL_WIDTH 0x3057
#define EGL_HEIGHT 0x3056
#define EGL_NONE 0x3038
#define EGL_OPENGL_API 0x30a2

static EGLDisplay dpy;
static EGLSurface surf;
static EGLContext ctx;
static int sim_frame;
static int showcase_mode;

uint32_t plat_us(void)
{
	if (showcase_mode)
		return (uint32_t)sim_frame * 16667U;
	struct timeval tv;
	gettimeofday(&tv, 0);
	return (uint32_t)tv.tv_sec * 1000000U + (uint32_t)tv.tv_usec;
}
void plat_out(const char *line)
{
	printf("%s\n", line);
	fflush(stdout);
}

/* Optional scripted showcase sequence when WSHSPACE_SHOWCASE=1 is set */
int plat_key(void)
{
	static int last_f = -1;
	if (showcase_mode && last_f != sim_frame) {
		last_f = sim_frame;
		if (sim_frame == 2)   return ' ';   /* Launch from title */
		if (sim_frame == 3)   return 't';   /* Lock nearest asteroid target */
		if (sim_frame == 120) return 'm';   /* Open galaxy starmap */
		if (sim_frame == 130) return 'm';   /* Close starmap */
		if (sim_frame == 150) return 'u';   /* Open ship upgrades */
		if (sim_frame == 160) return 'u';   /* Close upgrades */
		if (sim_frame == 180) return 'j';   /* Engage hyperspace warp */
		if (sim_frame == 330) return 't';   /* Lock Sentinel drone in Vega Gate */
		if (sim_frame == 360) return 27;    /* Quit after arriving in system 2 */
	}
	return -1;
}
void plat_poll(struct plat_input *in)
{
	in->held = 0;
	in->mdx = in->mdy = 0;
	in->mlook = 0;
	if (showcase_mode && ((sim_frame >= 4 && sim_frame < 115) || (sim_frame >= 332 && sim_frame < 358)))
		in->held = IN_FIRE | IN_THRUST;
}
void plat_sleep(int ms)
{
	usleep((useconds_t)ms * 1000);
}
int plat_wrapper_rev(char *buf, int n)
{
	(void)buf, (void)n;
	return 0;
}
void plat_audio_init(int enable)
{
	(void)enable;
}
void plat_audio_tick(void)
{
	/* Also exercise the soft-synth mixer in headless runs to verify it stays clean */
	static int16_t dummy[256 * 2];
	space_audio_mix(dummy, 256, 22050);
}
void plat_audio_close(void)
{
}

int glw_open(int w, int h)
{
	EGLint major, minor, num;
	EGLConfig cfg;
	static const EGLint cattr[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
				       EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_NONE};
	if (!dpy && (!(dpy = eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, 0, 0)) || !eglInitialize(dpy, &major, &minor)))
		return -1;
	if (!eglChooseConfig(dpy, cattr, &cfg, 1, &num) || num < 1)
		return -1;
	EGLint sattr[] = {EGL_WIDTH, w, EGL_HEIGHT, h, EGL_NONE};
	if (!(surf = eglCreatePbufferSurface(dpy, cfg, sattr)) || !eglBindAPI(EGL_OPENGL_API) ||
	    !(ctx = eglCreateContext(dpy, cfg, 0, 0)) || !eglMakeCurrent(dpy, surf, surf, ctx))
		return -1;
	return 0;
}
void glw_close(int final)
{
	eglMakeCurrent(dpy, 0, 0, 0);
	eglDestroyContext(dpy, ctx);
	eglDestroySurface(dpy, surf);
	if (final)
		eglTerminate(dpy), dpy = 0;
}
void glw_swap(int vsync)
{
	static uint8_t px[1024 * 768 * 4];
	const char *dir = getenv("WSHSPACE_SHOTS");
	(void)vsync;
	int save = 0;
	if (dir) {
		if (showcase_mode)
			save = (sim_frame == 0 || sim_frame == 46 || sim_frame == 125 || sim_frame == 155 || sim_frame == 210 || sim_frame == 346);
		else
			save = (sim_frame % 60 == 0);
	}
	if (dir && save) {
		int w = space_view.w, h = space_view.h;
		char path[256];
		snprintf(path, sizeof(path), "%s/frame-%04d.ppm", dir, sim_frame);
		glf.glFinish();
		glf.glReadBuffer(GL_BACK);
		glf.glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, px);
		FILE *f = fopen(path, "wb");
		if (f) {
			fprintf(f, "P6\n%d %d\n255\n", w, h);
			for (int y = h - 1; y >= 0; y--)
				for (int x = 0; x < w; x++)
					fwrite(px + (y * w + x) * 4, 1, 3, f);
			fclose(f);
		}
	}
	sim_frame++;
	eglSwapBuffers(dpy, surf);
}
int glw_gamma(const uint16_t ramp[3][256])
{
	(void)ramp;
	return 0;
}

int main(int argc, char **argv)
{
	showcase_mode = getenv("WSHSPACE_SHOWCASE") != NULL;
	GL_FUNCS(FILL)
	return space_main(argc, argv, &gl_backend);
}
