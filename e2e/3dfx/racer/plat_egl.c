/*
 * Host-side Mesa surfaceless EGL runner for wshracer's OpenGL backend (no X server or GPU needed),
 * used to run -check, -bench, -audiotest and automated gameplay screenshot captures:
 *
 *   gcc -O2 -I../../wisp -o wshracer-egl racer.c be_gl.c plat_egl.c \
 *       /usr/lib/x86_64-linux-gnu/libEGL.so.1 /usr/lib/x86_64-linux-gnu/libGL.so.1
 *   ./wshracer-egl -check
 *   ./wshracer-egl -bench 300
 *   WSHRACER_SHOWCASE=1 WSHRACER_SHOTS=/tmp ./wshracer-egl -auto -res 800x600
 *
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#include "racer.h"
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
static int aud_enabled;
static uint32_t aud_us;

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

/* Scripted showcase tour across all 4 circuits, enclosed tunnel & nose cam when WSHRACER_SHOWCASE=1 */
int plat_key(void)
{
	static int last_f = -1;
	if (showcase_mode && last_f != sim_frame) {
		last_f = sim_frame;
		if (sim_frame == 120) return '2'; /* Switch to Neon Metropolis */
		if (sim_frame == 255) return 'c'; /* Toggle Nose Cockpit Cam inside Neon Metropolis tunnel */
		if (sim_frame == 305) return 'c'; /* Return to Chase Cam */
		if (sim_frame == 310) return '3'; /* Switch to Pacific Atoll */
		if (sim_frame == 415) return '4'; /* Switch to Glacier Peak */
		if (sim_frame == 510) return RKEY_ESC;
	}
	return 0;
}
void plat_poll_input(struct plat_input *in)
{
	memset(in, 0, sizeof(*in));
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
	aud_enabled = enable;
	aud_us = plat_us();
}
void plat_audio_tick(void)
{
	static int16_t dummy[1024 * 2];
	if (!aud_enabled)
		return;
	uint32_t now = plat_us();
	uint32_t dt = now - aud_us;
	if (showcase_mode) {
		racer_audio_mix(dummy, 368, 22050);
		aud_us = now;
		return;
	}
	int frames = (int)((double)dt * 22050.0 * 1e-6);
	if (frames < 64)
		return;
	if (frames > 1024)
		frames = 1024;
	racer_audio_mix(dummy, frames, 22050);
	aud_us = now;
}
void plat_audio_close(void)
{
	aud_enabled = 0;
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
	static uint8_t px[MAX_PIXELS * 4];
	const char *dir = getenv("WSHRACER_SHOTS");
	(void)vsync;
	int save = 0;
	if (dir) {
		if (showcase_mode)
			save = (sim_frame == 12 || sim_frame == 95 || sim_frame == 180 || sim_frame == 275 || sim_frame == 370 || sim_frame == 475);
		else
			save = (sim_frame % 60 == 0);
	}
	if (dir && save) {
		int w = racer_view.w, h = racer_view.h;
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
	showcase_mode = getenv("WSHRACER_SHOWCASE") != NULL;
	GL_FUNCS(FILL)
	return racer_main(argc, argv, &gl_backend);
}
