/*
 * A host-side check of wshdemo's OpenGL backend (be_gl.c) without Windows: the same backend and
 * core on the host's Mesa, in an EGL pbuffer of Mesa's surfaceless platform (no X server, no GPU
 * needed), so that its drawing and its -check probes can be tried where the Windows exe can't run.
 * qemu-3dfx's OpenGL pass-through hands a Windows guest's GL calls to the same Mesa on the host.
 * A development aid, not shipped:
 *
 *   apt-get install gcc libegl1 libgl1 libegl-mesa0 libgl1-mesa-dri
 *   gcc -O2 -o wshdemo-egl demo.c music.c be_gl.c plat_egl.c /usr/lib/x86_64-linux-gnu/libEGL.so.1 \
 *       /usr/lib/x86_64-linux-gnu/libGL.so.1
 *   ./wshdemo-egl -check -bench 300
 *   WSHDEMO_SHOTS=/tmp ./wshdemo-egl -time 40     (every 120th frame as a PPM in /tmp)
 *
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#include "demo.h"
#include "gl11.h"

#define DECL(ret, name, args) ret name args;
GL_FUNCS(DECL)
#define FILL(ret, name, args) glf.name = name;

/* EGL 1.5, declared here to need no development package */
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

uint32_t plat_us(void)
{
	struct timeval tv;
	gettimeofday(&tv, 0);
	return (uint32_t)tv.tv_sec * 1000000U + (uint32_t)tv.tv_usec;
}
void plat_out(const char *line)
{
	printf("%s\n", line);
	fflush(stdout);
}
int plat_key(void)
{
	return -1;
}
/* no sound here: the music is checked by music-test.c */
void plat_audio_init(int enable)
{
	(void)enable;
}
void plat_audio_tick(void)
{
}
void plat_audio_close(void)
{
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

int glw_open(int w, int h)
{
	EGLint major, minor, num;
	EGLConfig cfg;
	static const EGLint cattr[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_RED_SIZE, 8,
				       EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_NONE};
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
/* WSHDEMO_SHOTS=DIR: every 120th frame into DIR/frame-N.ppm, to look at */
void glw_swap(int vsync)
{
	static int frame;
	static uint8_t px[MAX_PIXELS * 4];
	const char *dir = getenv("WSHDEMO_SHOTS");
	(void)vsync;
	if (dir && frame++ % 120 == 0) {
		int w = demo_view.w, h = demo_view.h;
		char path[256];
		snprintf(path, sizeof(path), "%s/frame-%04d.ppm", dir, frame - 1);
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
	eglSwapBuffers(dpy, surf);
}
int glw_gamma(const uint16_t ramp[3][256])
{
	(void)ramp;
	return 0;
}

int main(int argc, char **argv)
{
	GL_FUNCS(FILL)
	return demo_main(argc, argv, &gl_backend);
}
