/*
 * The Glide test scene of wsh-openglide's tests, shared by glide-render.c (the host library alone)
 * and e2e/3dfx's guest program (the whole pass-through, from a Linux guest through QEMU): what is
 * drawn, where it is probed and what each probe must show.
 *
 * 640x480, origin upper left: a dark blue clear, a red triangle on the left, a green one on the
 * right and a Gouraud triangle in the middle (red, green and blue corners). A probe matches when
 * every channel is within TOLERANCE of the expected colour. Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_GLIDE_SCENE_H
#define WSH_GLIDE_SCENE_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define W 640
#define H 480

/* Glide 2 SDK constants (sdk2_glide.h, sdk2_sst1vid.h) */
#define GR_RESOLUTION_640x480 0x7
#define GR_REFRESH_60Hz 0x0
#define GR_COLORFORMAT_ARGB 0x0
#define GR_ORIGIN_UPPER_LEFT 0x0
#define GR_BUFFER_FRONTBUFFER 0x0
#define GR_BUFFER_BACKBUFFER 0x1
#define GR_PARAM_XY 0x01
#define GR_PARAM_RGB 0x20
#define GR_PARAM_ENABLE 0x01
#define SCENE_CLEAR 0xff000080 /* ARGB */

/* The Glide 2 vertex (GLIDE_NUM_TMU 2), as a Glide 2 guest passes it */
typedef struct {
	float sow, tow, oow;
} TmuVertex;
typedef struct {
	float x, y, z, r, g, b, ooz, a, oow;
	TmuVertex tmuvtx[2];
} Vertex2;

/* Triangles, in Glide screen coordinates */
static const float red_tri[3][2] = {{40, 400}, {200, 80}, {260, 400}};
static const float green_tri[3][2] = {{380, 400}, {440, 80}, {600, 400}};
static const float gouraud_tri[3][2] = {{220, 460}, {320, 300}, {420, 460}};
static const float red_rgb[3][3] = {{255, 0, 0}, {255, 0, 0}, {255, 0, 0}};
static const float green_rgb[3][3] = {{0, 255, 0}, {0, 255, 0}, {0, 255, 0}};
static const float gouraud_rgb[3][3] = {{255, 0, 0}, {0, 255, 0}, {0, 0, 255}};

/* A Glide 2 vertex for corner i of a triangle */
static inline Vertex2 scene_vertex2(const float pos[3][2], const float rgb[3][3], int i)
{
	Vertex2 v;
	memset(&v, 0, sizeof(v));
	v.x = pos[i][0];
	v.y = pos[i][1];
	v.r = rgb[i][0];
	v.g = rgb[i][1];
	v.b = rgb[i][2];
	v.a = 255;
	v.oow = 1;
	return v;
}

struct probe {
	const char *what;
	int x, y;
	uint8_t r, g, b; /* for a Gouraud probe: computed from the corners (gouraud_expect) */
	int gouraud;
};

static const struct probe probes[] = {
	{"clear, top left", 10, 10, 0x00, 0x00, 0x80, 0},
	{"clear, top right", 630, 10, 0x00, 0x00, 0x80, 0},
	{"clear, between the triangles", 320, 150, 0x00, 0x00, 0x80, 0},
	{"red triangle", 166, 293, 0xff, 0x00, 0x00, 0},
	{"green triangle", 473, 293, 0x00, 0xff, 0x00, 0},
	/* the Gouraud triangle: barycentric mixes of its corners' colours */
	{"Gouraud triangle, centroid", 320, 407, 0, 0, 0, 1},
	{"Gouraud triangle, near the blue corner", 400, 452, 0, 0, 0, 1},
	{"Gouraud triangle, near the green corner", 320, 320, 0, 0, 0, 1},
};
#define TOLERANCE 24 /* per channel: RGB565 steps, dithering, and the interpolation near a corner */

/* The colour Gouraud shading gives at (x, y), sampled at the pixel's centre */
static inline void gouraud_expect(int x, int y, uint8_t rgb[3])
{
	const float(*v)[2] = gouraud_tri;
	float px = x + 0.5f, py = y + 0.5f;
	float d = (v[1][1] - v[2][1]) * (v[0][0] - v[2][0]) + (v[2][0] - v[1][0]) * (v[0][1] - v[2][1]);
	float l0 = ((v[1][1] - v[2][1]) * (px - v[2][0]) + (v[2][0] - v[1][0]) * (py - v[2][1])) / d;
	float l1 = ((v[2][1] - v[0][1]) * (px - v[2][0]) + (v[0][0] - v[2][0]) * (py - v[2][1])) / d;
	float l2 = 1 - l0 - l1;
	for (int c = 0; c < 3; c++)
		rgb[c] = (uint8_t)(l0 * gouraud_rgb[0][c] + l1 * gouraud_rgb[1][c] + l2 * gouraud_rgb[2][c] + 0.5f);
}

/* Check every probe against px(x, y, channel); print one line per probe. counted = 0 reports
 * mismatches as "info" without counting them. Returns the number of counted mismatches. */
static inline int scene_check(const char *source, uint8_t (*px)(int, int, int), int counted)
{
	int failed = 0;
	for (size_t i = 0; i < sizeof(probes) / sizeof(probes[0]); i++) {
		struct probe p = probes[i];
		if (p.gouraud) {
			uint8_t rgb[3];
			gouraud_expect(p.x, p.y, rgb);
			p.r = rgb[0];
			p.g = rgb[1];
			p.b = rgb[2];
		}
		int r = px(p.x, p.y, 0), g = px(p.x, p.y, 1), b = px(p.x, p.y, 2);
		int ok = abs(r - p.r) <= TOLERANCE && abs(g - p.g) <= TOLERANCE && abs(b - p.b) <= TOLERANCE;
		printf("%-4s %-15s %-40s (%3d,%3d) got #%02x%02x%02x want #%02x%02x%02x\n",
		       ok ? "ok" : counted ? "FAIL" : "info", source, p.what, p.x, p.y, r, g, b, p.r, p.g, p.b);
		failed += !ok && counted;
	}
	return failed;
}

/* One channel of an RGB565 pixel, scaled to 0..255 */
static inline uint8_t rgb565_channel(uint16_t v, int c)
{
	switch (c) {
	case 0: return (uint8_t)(((v >> 11) & 0x1f) * 255 / 31);
	case 1: return (uint8_t)(((v >> 5) & 0x3f) * 255 / 63);
	default: return (uint8_t)((v & 0x1f) * 255 / 31);
	}
}

#endif
