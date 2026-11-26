/*
 * wshdemo: a small 3dfx-era demo and test tool for qemu-3dfx's Glide and OpenGL pass-through.
 *
 * One portable core (demo.c: the parts, the font, the textures, the main loop, the checks) draws
 * through a small renderer interface (struct backend) that each API implements: be_glide2.c
 * (Glide 2: Linux libglide.so.2, DOS GLIDE2X.DXE, Windows GLIDE2X.DLL), be_glide3.c (Windows
 * GLIDE3X.DLL) and be_gl.c (Windows OPENGL32.DLL). The platform front ends (plat_linux.c,
 * plat_dos.c, plat_win.c) provide the plat_* functions below and call demo_main(); plat_egl.c runs
 * the OpenGL backend on the host's Mesa, to check it without Windows. music.c is the music, which
 * the front ends play through e2e/3dfx/audio's sound backends.
 *
 * The core uses no C library: no stdio, no libm (Windows 98's MSVCRT.DLL is too old for mingw-w64,
 * so the Windows exe has none). The front ends provide memset/memcpy (the Windows one through
 * e2e/3dfx/win98/w3d.h). Everything is built for the Pentium (-march=pentium, x87 floating point).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_DEMO_H
#define WSH_DEMO_H

#include <stdint.h>

/* A vertex as the core hands it to a backend. x, y: screen position (origin upper left, pixels);
 * oow: 1/w (w = the view-space depth, 1 for 2D); vx, vy, vz: the view-space position (camera at the
 * origin looking along +z, y up), for a backend that projects itself (OpenGL); r, g, b, a: 0..255;
 * s, t: texture coordinates, 0..1 across the texture (wrapping beyond). */
struct dvtx {
	float x, y, oow;
	float vx, vy, vz;
	float r, g, b, a;
	float s, t;
};

enum { BLEND_NONE, BLEND_ALPHA, BLEND_ADD };

/* The render state of the triangles that follow */
struct rstate {
	int tex;    /* texture id (TEX_*), or -1 for none (vertex colour only) */
	int blend;  /* BLEND_* (the source factor is the alpha: vertex alpha times texture alpha) */
	int depth;  /* 1: depth test (less) and write; 0: neither */
	int fog;    /* 1: fog (see backend.fog) */
	int filter; /* 1: bilinear (and mipmaps when the texture has them); 0: point sampled */
	int clamp;  /* 1: clamp the texture coordinates; 0: wrap */
	int mode2d; /* 1: 2D (vx, vy, vz unused; a projecting backend uses x, y) */
};

/* Texture ids: square textures, ARGB 8888 in memory (0xAARRGGBB), the mipmap levels one after the
 * other, largest first */
enum { TEX_CUBE, TEX_TUNNEL, TEX_PLASMA, TEX_FONT, TEX_COUNT };

/* What a backend needs of the view: the size and the projection (a backend that projects itself
 * builds its frustum from these) */
struct view {
	int w, h;
	float f;         /* focal length in pixels: sx = w/2 + vx*f/vz */
	float znear, zfar;
};
extern struct view demo_view;

struct backend {
	const char *api;                           /* "Glide 2", "Glide 3", "OpenGL" */
	int (*open)(int w, int h);                 /* 0 ok; may be called again (another resolution) after close */
	void (*close)(int final);                  /* final: also shut the API down (else another open follows) */
	const char *(*version)(void);              /* what the API says it is (grGlideGetVersion, GL_VERSION...) */
	void (*clear)(uint32_t rgb);               /* colour and depth (farthest) */
	/* (re)load a texture: size x size, levels mipmap levels (1 = none), alpha: has a meaningful alpha */
	void (*tex_load)(int id, int size, int levels, const uint32_t *argb, int alpha);
	void (*tex_update)(int id, const uint32_t *argb); /* level 0 again, same size: once a frame */
	void (*state)(const struct rstate *s);
	void (*fog)(float start, float end, uint32_t rgb); /* linear fog on the view-space depth */
	void (*tris)(const struct dvtx *v, int n);  /* n vertices, three a triangle */
	void (*swap)(int vsync);
	int (*read)(void);                         /* read the back buffer back (before the swap); 0 failed */
	void (*pixel)(int x, int y, uint8_t rgb[3]); /* of the last read, origin upper left */
	int (*gamma)(float g);                     /* 0: not available */
	int (*res_ok)(int w, int h);               /* whether the API can open this size */
};

/* --- provided by the front end ---------------------------------------------------------------- */

uint32_t plat_us(void);            /* microseconds, any origin (wraps) */
void plat_out(const char *line);   /* one line of output (no newline): stdout, COM1, the console */
int plat_key(void);                /* a key pressed (ASCII, 27 for Esc), or -1; also pumps messages */
void plat_sleep(int ms);
/* The wrapper's build string (qemu-3dfx's "<rev>-<time> <date> build"), found in the loaded guest
 * wrapper, into buf; 0 if not found */
int plat_wrapper_rev(char *buf, int n);
/* Sound (e2e/3dfx/audio): open the device (enable 0: don't), mix ahead into it with demo_audio_mix()
 * (polled, once a frame), close it. Without a device they do nothing. */
void plat_audio_init(int enable);
void plat_audio_tick(void);
void plat_audio_close(void);

/* --- provided by the core --------------------------------------------------------------------- */

/* argv[0] is skipped. Returns the exit status: 0 ok, 1 a check failed, 2 an error (no device). */
int demo_main(int argc, char **argv, const struct backend *be);
/* The next frames of sound, 16-bit stereo at rate Hz: the music (silent when muted), or with
 * -audiotest the audio signature */
void demo_audio_mix(int16_t *pcm, int frames, int rate);
/* Looks for qemu-3dfx's build string ("1234abc-12:34:56 Nov 24 2026 build") in buf */
int demo_find_buildstr(const uint8_t *buf, uint32_t len, char *out, int n);
/* printf-like into buf (%s %c %d %u %x with width and 0 flag, %.Nf for double); returns length */
int demo_fmt(char *buf, int n, const char *fmt, ...);
/* The output tag ("WSHDEMO", -tag) and one tagged line */
void demo_log(const char *fmt, ...);
/* ARGB 8888 to the 16-bit formats of Glide */
static inline uint16_t argb_to_565(uint32_t c)
{
	return (uint16_t)(((c >> 8) & 0xf800) | ((c >> 5) & 0x07e0) | ((c >> 3) & 0x001f));
}
static inline uint16_t argb_to_4444(uint32_t c)
{
	return (uint16_t)(((c >> 16) & 0xf000) | ((c >> 12) & 0x0f00) | ((c >> 8) & 0x00f0) | ((c >> 4) & 0x000f));
}

#endif
