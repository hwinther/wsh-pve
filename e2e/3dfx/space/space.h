/*
 * wshspace: a .kkrieger-inspired procedural 3D space exploration & mining game for 3dfx Glide and
 * OpenGL, built for DOS (DJGPP + GLIDE2X.DXE), Windows 9x/ME/2000/XP (GLIDE2X.DLL, GLIDE3X.DLL,
 * OPENGL32.DLL, no MSVCRT) and i386 Linux (glibc 2.0 + libglide.so.2) under 96 KB with zero
 * external data files.
 *
 * One portable core (space.c: procedural noise, textures, displaced 3D meshes, 5-plane frustum
 * clipper, 6DoF cockpit flight, star systems, asteroid mining, enemy drones, station upgrades,
 * galaxy starmap, hyperspace warp, and soft-synth audio) renders through struct backend and reads
 * input/audio through plat_*. Everything is built for the original Pentium (-march=pentium, x87
 * floating point, no libm, no P6 CMOV/FCOMI).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_SPACE_H
#define WSH_SPACE_H

#include <stdint.h>

/* Projected + view-space vertex handed to a backend.
 * x, y: screen position (origin upper left, pixels); oow: 1/vz (1 for 2D), kept in (0..1] by
 * znear >= 1.0 so Voodoo's 16-bit W-buffer and table fog stay in their native range;
 * vx, vy, vz: view-space coordinates (+z forward, +y up) for OpenGL; r, g, b, a: 0..255;
 * s, t: texture coordinates, 0..1 across the texture (wrapping beyond). */
struct dvtx {
	float x, y, oow;
	float vx, vy, vz;
	float r, g, b, a;
	float s, t;
};

enum { BLEND_NONE, BLEND_ALPHA, BLEND_ADD };

struct rstate {
	int tex;    /* TEX_* or -1 for untextured vertex colour */
	int blend;  /* BLEND_* */
	int depth;  /* 1: depth test (less) and write; 0: neither (2D, skybox, additive particles) */
	int fog;    /* 1: linear depth fog */
	int filter; /* 1: bilinear (+ mipmaps if levels > 1); 0: point sampled */
	int clamp;  /* 1: clamp UVs; 0: wrap */
	int mode2d; /* 1: screen-space 2D; 0: 3D view/projected */
};

enum {
	TEX_FONT,
	TEX_ROCK,
	TEX_PLANET,
	TEX_HULL,
	TEX_FLARE,
	TEX_NEBULA,
	TEX_WARP,
	TEX_COUNT
};

struct view {
	int w, h;
	float f;
	float znear, zfar;
};
extern struct view space_view;

struct backend {
	const char *api;
	int (*open)(int w, int h);
	void (*close)(int final);
	const char *(*version)(void);
	void (*clear)(uint32_t rgb);
	void (*tex_load)(int id, int size, int levels, const uint32_t *argb, int alpha);
	void (*tex_update)(int id, const uint32_t *argb);
	void (*state)(const struct rstate *s);
	void (*fog)(float start, float end, uint32_t rgb);
	void (*tris)(const struct dvtx *v, int n);
	void (*swap)(int vsync);
	int (*read)(void);
	void (*pixel)(int x, int y, uint8_t rgb[3]);
	int (*gamma)(float g);
	int (*res_ok)(int w, int h);
};

/* Continuous flight controls + discrete special keys */
enum {
	IN_PITCH_UP   = 1 << 0,
	IN_PITCH_DOWN = 1 << 1,
	IN_YAW_LEFT   = 1 << 2,
	IN_YAW_RIGHT  = 1 << 3,
	IN_ROLL_LEFT  = 1 << 4,
	IN_ROLL_RIGHT = 1 << 5,
	IN_THRUST     = 1 << 6,
	IN_BRAKE      = 1 << 7,
	IN_BOOST      = 1 << 8,
	IN_FIRE       = 1 << 9
};

enum {
	KEY_UP    = 256,
	KEY_DOWN  = 257,
	KEY_LEFT  = 258,
	KEY_RIGHT = 259
};

struct plat_input {
	uint32_t held;
	int mdx, mdy;
	int mlook;
};

/* --- provided by the platform front end ------------------------------------------------------- */

uint32_t plat_us(void);
void plat_out(const char *line);
int plat_key(void);
void plat_poll(struct plat_input *in);
void plat_sleep(int ms);
int plat_wrapper_rev(char *buf, int n);
void plat_audio_init(int enable);
void plat_audio_tick(void);
void plat_audio_close(void);

/* --- provided by the portable core ------------------------------------------------------------ */

int space_main(int argc, char **argv, const struct backend *be);
void space_audio_mix(int16_t *stereo_pcm, int frames, int rate);
int space_find_buildstr(const uint8_t *buf, uint32_t len, char *out, int n);
int space_fmt(char *buf, int n, const char *fmt, ...);
void space_log(const char *fmt, ...);

static inline uint16_t argb_to_565(uint32_t c)
{
	return (uint16_t)(((c >> 8) & 0xf800) | ((c >> 5) & 0x07e0) | ((c >> 3) & 0x001f));
}
static inline uint16_t argb_to_4444(uint32_t c)
{
	return (uint16_t)(((c >> 16) & 0xf000) | ((c >> 12) & 0x0f00) | ((c >> 8) & 0x00f0) | ((c >> 4) & 0x000f));
}

#endif
