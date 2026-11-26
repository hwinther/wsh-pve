/*
 * wshkeep: .kkrieger-inspired procedural 3D subterranean dungeon & citadel crawler for 3dfx
 * Glide 2, Glide 3, and OpenGL 1.1 (<= 96 KB, Pentium-safe x87, zero external asset files).
 * Shared core <-> backend <-> platform contract.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_KEEP_H
#define WSH_KEEP_H

#include <stdint.h>

enum {
	TEX_FONT = 0,
	TEX_WALL = 1,
	TEX_FLOOR = 2,
	TEX_DOOR = 3,
	TEX_LIQUID = 4,
	TEX_MESH = 5,
	TEX_FLARE = 6,
	TEX_COUNT = 7,
};

enum { BLEND_NONE = 0, BLEND_ALPHA = 1, BLEND_ADD = 2 };
enum { DEPTH_OFF = 0, DEPTH_RW = 1, DEPTH_RO = 2 };
enum { CLAMP_WRAP = 0, CLAMP_ALL = 1, CLAMP_S_WRAP_T = 2 };

struct dvtx {
	float x, y;       /* screen pixels, upper-left origin */
	float oow;        /* 1/vz for Glide W-buffer & perspective UVs */
	float vx, vy, vz; /* view-space coords (vz > 0 in front of camera) */
	float r, g, b, a; /* 0..255 */
	float s, t;       /* normalized 0..1 (wraps when > 1) */
};

struct rstate {
	int tex; /* -1 for untextured */
	uint8_t blend, depth, fog, filter, clamp, mode2d;
};

struct view {
	int w, h;
	float f, znear, zfar;
};

extern struct view keep_view;

struct backend {
	const char *name;
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

/* Largest frame a backend opens (OpenGL's 1920x1080), for read-back buffers */
#define MAX_PIXELS (1920 * 1080)

enum {
	KKEY_ESC = 27,
	KKEY_SPACE = ' ',
	KKEY_ENTER = 13,
	KKEY_TAB = 9,
	KKEY_UP = 0x100,
	KKEY_DOWN = 0x101,
	KKEY_LEFT = 0x102,
	KKEY_RIGHT = 0x103,
};

struct plat_input {
	uint8_t fwd, back, strafe_l, strafe_r;
	uint8_t turn_l, turn_r, look_u, look_d;
	uint8_t attack, use_door, sprint;
	int mdx, mdy;
	uint8_t mb_l, mb_r;
};

int keep_main(int argc, char **argv, const struct backend *be);
void keep_log(const char *fmt, ...);
int keep_fmt(char *buf, int cap, const char *fmt, ...);
int keep_find_buildstr(const uint8_t *buf, uint32_t len, char *out, int outlen);

/* Procedural 16-bit stereo PCM synthesizer callback (frames = stereo sample pairs at rate Hz). */
void keep_audio_mix(int16_t *stereo_pcm, int frames, int rate);

/* Platform-supplied services */
uint32_t plat_us(void);
int plat_key(void); /* queued one-shot key press, 0 if none */
void plat_poll_input(struct plat_input *in);
void plat_out(const char *line);
void plat_sleep(int ms);
int plat_wrapper_rev(char *buf, int n);

void plat_audio_init(int enable);
void plat_audio_tick(void);
void plat_audio_close(void);

static inline uint16_t argb_to_565(uint32_t c)
{
	return (uint16_t)((((c >> 19) & 0x1f) << 11) | (((c >> 10) & 0x3f) << 5) | ((c >> 3) & 0x1f));
}
static inline uint16_t argb_to_4444(uint32_t c)
{
	return (uint16_t)((((c >> 28) & 0xf) << 12) | (((c >> 20) & 0xf) << 8) |
			  (((c >> 12) & 0xf) << 4) | ((c >> 4) & 0xf));
}

#endif
