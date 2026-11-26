/*
 * wshracer: .kkrieger-style procedural asset generator & real-time racing synth.
 * Generates mipmapped 2D textures (track asphalt/curbs, canyon strata, craft hull, chevron boost
 * pads, plasma flares, atmospheric sky), 3D hovercraft & gantry meshes, and a 138 BPM electronic
 * soundtrack + hover-turbine/SFX mixer at startup/runtime with zero external data files.
 * All math is Pentium-safe x87 (-march=pentium, no CMOV/FCOMI/SSE).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_RACER_GEN_H
#define WSH_RACER_GEN_H

#include "audiosig.h"

#define PI 3.14159265358979323846
#define TAU 6.28318530717958647692

/* --- Pentium-safe freestanding math ------------------------------------------------------------- */

static double m_sin(double x)
{
	int k = (int)(x * (1.0 / TAU));
	x -= k * TAU;
	if (x > PI)
		x -= TAU;
	if (x < -PI)
		x += TAU;
	double x2 = x * x, r = x, t = x;
	for (int i = 1; i <= 9; i++) {
		t *= -x2 / ((2 * i) * (2 * i + 1));
		r += t;
	}
	return r;
}
static double m_cos(double x) { return m_sin(x + PI * 0.5); }
static float m_sinf(float x) { return (float)m_sin((double)x); }
static float m_cosf(float x) { return (float)m_cos((double)x); }

static float m_sqrtf(float x)
{
	if (x <= 0.0f)
		return 0.0f;
#if defined(__i386__) || defined(__x86_64__)
	float r;
	__asm__("fsqrt" : "=t"(r) : "0"(x));
	return r;
#else
	float g = x > 1.0f ? x * 0.5f : 1.0f;
	for (int i = 0; i < 6; i++)
		g = 0.5f * (g + x / g);
	return g;
#endif
}

static float m_fabsf(float x) { return x < 0.0f ? -x : x; }
static float clampf(float x, float lo, float hi) { return x < lo ? lo : x > hi ? hi : x; }
static int clampi(int x, int lo, int hi) { return x < lo ? lo : x > hi ? hi : x; }
static float lerpf(float a, float b, float t) { return a + (b - a) * t; }

typedef struct {
	float x, y, z;
} v3;

static inline v3 v3_make(float x, float y, float z) { v3 r = {x, y, z}; return r; }
static inline v3 v3_add(v3 a, v3 b) { return v3_make(a.x + b.x, a.y + b.y, a.z + b.z); }
static inline v3 v3_sub(v3 a, v3 b) { return v3_make(a.x - b.x, a.y - b.y, a.z - b.z); }
static inline v3 v3_scale(v3 a, float s) { return v3_make(a.x * s, a.y * s, a.z * s); }
static inline float v3_dot(v3 a, v3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline v3 v3_cross(v3 a, v3 b)
{
	return v3_make(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}
static inline float v3_len(v3 a) { return m_sqrtf(v3_dot(a, a)); }
static inline v3 v3_norm(v3 a)
{
	float l = v3_len(a);
	return l > 1e-6f ? v3_scale(a, 1.0f / l) : v3_make(0, 0, 1);
}

/* --- PRNG & procedural noise -------------------------------------------------------------------- */

static uint32_t hash32(uint32_t x)
{
	x ^= x >> 16;
	x *= 0x7feb352dU;
	x ^= x >> 15;
	x *= 0x846ca68bU;
	x ^= x >> 16;
	return x;
}

static uint32_t rng_next(uint32_t *s)
{
	uint32_t x = *s ? *s : 0x9e3779b9U;
	x ^= x << 13;
	x ^= x >> 17;
	x ^= x << 5;
	return *s = x;
}

static float rng_f01(uint32_t *s)
{
	return (float)(rng_next(s) & 0xffffffU) * (1.0f / 16777216.0f);
}

static float rng_fsym(uint32_t *s)
{
	return rng_f01(s) * 2.0f - 1.0f;
}

static float vnoise2(float x, float y, int period, uint32_t seed)
{
	int ix = (int)x - (x < (int)x ? 1 : 0);
	int iy = (int)y - (y < (int)y ? 1 : 0);
	float fx = x - ix, fy = y - iy;
	fx = fx * fx * (3.0f - 2.0f * fx);
	fy = fy * fy * (3.0f - 2.0f * fy);
	int m = period - 1;
	float n00 = (float)(hash32((uint32_t)((ix & m) + (iy & m) * 57) ^ seed) & 0xffffU) * (1.0f / 65535.0f);
	float n10 = (float)(hash32((uint32_t)(((ix + 1) & m) + (iy & m) * 57) ^ seed) & 0xffffU) * (1.0f / 65535.0f);
	float n01 = (float)(hash32((uint32_t)((ix & m) + ((iy + 1) & m) * 57) ^ seed) & 0xffffU) * (1.0f / 65535.0f);
	float n11 = (float)(hash32((uint32_t)(((ix + 1) & m) + ((iy + 1) & m) * 57) ^ seed) & 0xffffU) * (1.0f / 65535.0f);
	return lerpf(lerpf(n00, n10, fx), lerpf(n01, n11, fx), fy);
}

static float fbm2(float u, float v, int base_p, int oct, uint32_t seed)
{
	float sum = 0.0f, amp = 0.5f;
	int p = base_p;
	for (int i = 0; i < oct; i++) {
		sum += amp * vnoise2(u * (float)p, v * (float)p, p, seed + (uint32_t)i * 1013U);
		amp *= 0.5f;
		p <<= 1;
	}
	return sum;
}

static uint32_t pack_argb(int a, int r, int g, int b)
{
	return ((uint32_t)clampi(a, 0, 255) << 24) | ((uint32_t)clampi(r, 0, 255) << 16) |
	       ((uint32_t)clampi(g, 0, 255) << 8) | (uint32_t)clampi(b, 0, 255);
}

/* --- Mipmapped procedural texture synthesis ----------------------------------------------------- */

static uint32_t mipbuf[256 * 256 * 4 / 3 + 16];

static int build_mips(int size, int alpha)
{
	int levels = 1;
	uint32_t *src = mipbuf;
	for (int s = size; s > 1; s >>= 1) {
		int h = s >> 1;
		uint32_t *dst = src + s * s;
		for (int y = 0; y < h; y++) {
			for (int x = 0; x < h; x++) {
				uint32_t p0 = src[(y * 2) * s + (x * 2)];
				uint32_t p1 = src[(y * 2) * s + (x * 2 + 1)];
				uint32_t p2 = src[(y * 2 + 1) * s + (x * 2)];
				uint32_t p3 = src[(y * 2 + 1) * s + (x * 2 + 1)];
				uint32_t a = alpha ? (((p0 >> 24) + (p1 >> 24) + (p2 >> 24) + (p3 >> 24) + 2) >> 2) : 255;
				uint32_t r = (((p0 >> 16 & 255) + (p1 >> 16 & 255) + (p2 >> 16 & 255) + (p3 >> 16 & 255) + 2) >> 2);
				uint32_t g = (((p0 >> 8 & 255) + (p1 >> 8 & 255) + (p2 >> 8 & 255) + (p3 >> 8 & 255) + 2) >> 2);
				uint32_t b = (((p0 & 255) + (p1 & 255) + (p2 & 255) + (p3 & 255) + 2) >> 2);
				dst[y * h + x] = (a << 24) | (r << 16) | (g << 8) | b;
			}
		}
		src = dst;
		levels++;
	}
	return levels;
}

static void gen_textures(const struct backend *be)
{
	/* 0. TEX_FONT: 128x128 16x8 grid of 8x16 cells with crisp 5x7 glyphs + soft drop shadow */
	for (int i = 0; i < 128 * 128; i++)
		mipbuf[i] = 0;
	for (int c = 32; c < 96; c++) {
		int gx = (c & 15) * 8, gy = ((c - 32) >> 4) * 16;
		const uint8_t *gl = font_glyph(c);
		for (int r = 0; r < 7; r++) {
			for (int col = 0; col < 5; col++) {
				if ((gl[r] >> (4 - col)) & 1) {
					int px = gx + 1 + col, py = gy + 2 + r * 2;
					mipbuf[py * 128 + px] = 0xffffffffU;
					mipbuf[(py + 1) * 128 + px] = 0xd8e8f8ffU;
					if (px + 1 < gx + 8 && !mipbuf[(py + 1) * 128 + px + 1])
						mipbuf[(py + 1) * 128 + px + 1] = 0x58000000U;
				}
			}
		}
	}
	be->tex_load(TEX_FONT, 128, 1, mipbuf, 1);

	/* 1. TEX_TRACK: 256x256 racing surface (clamped in S, wrapped in T) with rumble curbs,
	 * crisp lane shoulders, expansion seams, dashed center racing stripe, and fine grain. */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f), v = y * (1.0f / 256.0f);
			float grain = fbm2(u, v, 16, 3, 0x7711U) * 28.0f - 14.0f;
			int edge = x < 128 ? x : 255 - x;
			int r, g, b;
			if (edge < 6) {
				/* Raised outer guardrail lip */
				int hi = 215 + (int)(grain * 0.5f);
				r = hi, g = hi, b = hi + 10;
			} else if (edge < 22) {
				/* Diagonal alternating racing rumble curb */
				int stripe = ((y + (x < 128 ? edge : -edge) * 2) >> 5) & 1;
				int base = stripe ? 238 : 96;
				r = base + (int)grain;
				g = (stripe ? 238 : 88) + (int)grain;
				b = (stripe ? 242 : 96) + (int)grain;
			} else if (edge < 27) {
				/* Crisp bright shoulder line */
				r = 228, g = 234, b = 242;
			} else {
				/* Brushed metallic roadbed + transverse expansion joints + center dashes */
				int seam = ((y & 63) == 0 || (y & 63) == 1) ? -22 : 0;
				int plate = (((x >> 5) + (y >> 6)) & 1) ? 6 : 0;
				int base = 112 + plate + seam + (int)grain;
				r = base, g = base + 3, b = base + 8;
				/* Subtle racing groove lines */
				if (edge == 68 || edge == 69)
					r += 16, g += 18, b += 22;
				/* Center dashed stripe + subtle chevron hint */
				int cx = x - 128;
				if (cx < 0)
					cx = -cx;
				if (cx < 4 && ((y >> 4) & 1) == 0) {
					r = 225, g = 230, b = 238;
				}
			}
			mipbuf[y * 256 + x] = pack_argb(255, r, g, b);
		}
	}
	be->tex_load(TEX_TRACK, 256, build_mips(256, 0), mipbuf, 0);

	/* 2. TEX_TERRAIN: 256x256 canyon rock / ground grid strata (tinted per circuit) */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f), v = y * (1.0f / 256.0f);
			float n = fbm2(u, v, 6, 5, 0x31a9U);
			float strata = 0.5f + 0.5f * m_sinf((v * 8.0f + n * 1.8f) * (float)TAU);
			float ridge = 1.0f - m_fabsf(fbm2(u + 0.3f, v, 8, 4, 0x9921U) * 2.0f - 1.0f);
			int lum = (int)(92.0f + n * 95.0f + strata * 34.0f + ridge * 26.0f);
			/* Subtle tech grid line so cyber/ice circuits also get crisp ground detail */
			if ((x & 31) == 0 || (y & 31) == 0)
				lum += 16;
			mipbuf[y * 256 + x] = pack_argb(255, lum, lum - 2, lum - 5);
		}
	}
	be->tex_load(TEX_TERRAIN, 256, build_mips(256, 0), mipbuf, 0);

	/* 3. TEX_HULL: 256x256 sleek aerospace hull plating, intakes, & racing stripes */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f), v = y * (1.0f / 256.0f);
			float n = fbm2(u, v, 12, 3, 0x55c3U);
			int px = x & 63, py = y & 63;
			int seam = (px == 0 || py == 0) ? -42 : (px == 1 || py == 1) ? 26 : 0;
			int vent = (py >= 24 && py < 40 && px >= 16 && px < 48 && (y & 3) < 2) ? -48 : 0;
			int stripe = (x >= 112 && x < 144) ? 34 : 0;
			int v0 = 166 + (int)(n * 26.0f) + seam + vent + stripe;
			mipbuf[y * 256 + x] = pack_argb(255, v0, v0 + 4, v0 + 10);
		}
	}
	be->tex_load(TEX_HULL, 256, build_mips(256, 0), mipbuf, 0);

	/* 4. TEX_BOOST: 128x128 glowing animated-UV triple chevron turbo pad */
	for (int y = 0; y < 128; y++) {
		for (int x = 0; x < 128; x++) {
			float cx = m_fabsf((float)x - 63.5f);
			/* Forward-pointing chevron wave along y */
			int wave = (y + (int)(cx * 0.85f)) & 31;
			int chev = wave < 14 ? (255 - wave * 12) : 28;
			int border = (x < 6 || x >= 122) ? 220 : 0;
			int lum = chev > border ? chev : border;
			int r = (lum * 110) >> 8;
			int g = (lum * 235) >> 8;
			int b = lum;
			mipbuf[y * 128 + x] = pack_argb(255, r + 20, g + 16, b);
		}
	}
	be->tex_load(TEX_BOOST, 128, build_mips(128, 0), mipbuf, 0);

	/* 5. TEX_FLARE: 64x64 radial plasma thruster / sun flare / spark sprite */
	for (int y = 0; y < 64; y++) {
		for (int x = 0; x < 64; x++) {
			float dx = (x - 31.5f) / 31.5f, dy = (y - 31.5f) / 31.5f;
			float d = m_sqrtf(dx * dx + dy * dy);
			float core = clampf(1.0f - d, 0.0f, 1.0f);
			core = core * core;
			float rays = clampf(1.0f - m_fabsf(dx) * 5.5f, 0.0f, 1.0f) * clampf(1.0f - m_fabsf(dy) * 1.3f, 0.0f, 1.0f) +
				     clampf(1.0f - m_fabsf(dy) * 5.5f, 0.0f, 1.0f) * clampf(1.0f - m_fabsf(dx) * 1.3f, 0.0f, 1.0f);
			float a = clampf(core + rays * 0.42f, 0.0f, 1.0f);
			int lum = (int)(clampf(core * 1.35f + rays * 0.5f, 0.0f, 1.0f) * 255.0f);
			mipbuf[y * 64 + x] = pack_argb((int)(a * 255.0f), lum, lum, 255);
		}
	}
	be->tex_load(TEX_FLARE, 64, 1, mipbuf, 1);

	/* 6. TEX_SKY: 256x256 seamless atmospheric cloud wisps & horizon bands */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f), v = y * (1.0f / 256.0f);
			float c1 = fbm2(u, v * 2.0f, 4, 5, 0x8842U);
			float c2 = fbm2(u + 0.4f, v * 3.0f + 0.2f, 8, 4, 0x19d7U);
			float wisp = clampf((c1 * 0.7f + c2 * 0.5f) - 0.32f, 0.0f, 1.0f);
			int lum = (int)(135.0f + wisp * 120.0f);
			mipbuf[y * 256 + x] = pack_argb(255, lum, lum, lum + 6);
		}
	}
	be->tex_load(TEX_SKY, 256, build_mips(256, 0), mipbuf, 0);
}

/* --- Procedural 3D meshes (hovercraft, gantry arch, trackside pylon) ---------------------------- */

enum {
	MESH_CRAFT_PLAYER = 0,
	MESH_CRAFT_RIVAL = 1,
	MESH_ARCH = 2,
	MESH_PYLON = 3,
	MESH_COUNT = 4,
};

struct mtri {
	v3 p[3], n;
	float u[3], v[3];
	uint8_t cr, cg, cb;
};

#define MAX_MESH_TRIS 512
static struct mtri mesh_pool[MAX_MESH_TRIS];
static int mesh_pool_n;
static struct {
	int first, count;
} meshes[MESH_COUNT];

static void emit_mtri(v3 a, v3 b, v3 c, float ua, float va, float ub, float vb, float uc, float vc,
		      uint8_t cr, uint8_t cg, uint8_t cb)
{
	if (mesh_pool_n >= MAX_MESH_TRIS)
		return;
	struct mtri *t = &mesh_pool[mesh_pool_n++];
	t->p[0] = a, t->p[1] = b, t->p[2] = c;
	t->n = v3_norm(v3_cross(v3_sub(b, a), v3_sub(c, a)));
	t->u[0] = ua, t->v[0] = va;
	t->u[1] = ub, t->v[1] = vb;
	t->u[2] = uc, t->v[2] = vc;
	t->cr = cr, t->cg = cg, t->cb = cb;
}

static void emit_mquad(v3 a, v3 b, v3 c, v3 d, uint8_t cr, uint8_t cg, uint8_t cb)
{
	emit_mtri(a, b, c, 0, 0, 1, 0, 1, 1, cr, cg, cb);
	emit_mtri(a, c, d, 0, 0, 1, 1, 0, 1, cr, cg, cb);
}

/* Extrude a 4-point cross-section ring0 -> ring1 with end caps */
static void emit_loft4(const v3 r0[4], const v3 r1[4], int cap0, int cap1, uint8_t cr, uint8_t cg, uint8_t cb)
{
	for (int i = 0; i < 4; i++) {
		int j = (i + 1) & 3;
		emit_mquad(r0[i], r0[j], r1[j], r1[i], cr, cg, cb);
	}
	if (cap0)
		emit_mquad(r0[0], r0[3], r0[2], r0[1], cr, cg, cb);
	if (cap1)
		emit_mquad(r1[0], r1[1], r1[2], r1[3], cr, cg, cb);
}

/* Build a sleek twin-prong anti-gravity hover-racer (+Z = forward, +Y = up, +X = right).
 * White/neutral base vertex colors are modulated by each racing team's livery RGB at draw time;
 * dark cockpit glass and glowing rear thruster nozzles carry distinct contrast shading. */
static void build_hovercraft(int id, int variant)
{
	meshes[id].first = mesh_pool_n;
	float w_scale = variant ? 1.08f : 1.0f;
	float nose_z = variant ? 3.55f : 3.85f;

	/* Central fuselage spine: rear (-3.0) -> mid (0.4) -> nose tip (+2.5) */
	v3 c0[4] = {
		v3_make(-0.72f, 0.38f, -3.0f), v3_make(0.72f, 0.38f, -3.0f),
		v3_make(0.92f, -0.22f, -3.0f), v3_make(-0.92f, -0.22f, -3.0f),
	};
	v3 c1[4] = {
		v3_make(-0.68f, 0.52f, 0.3f), v3_make(0.68f, 0.52f, 0.3f),
		v3_make(0.88f, -0.26f, 0.3f), v3_make(-0.88f, -0.26f, 0.3f),
	};
	v3 c2[4] = {
		v3_make(-0.22f, 0.16f, 2.5f), v3_make(0.22f, 0.16f, 2.5f),
		v3_make(0.30f, -0.14f, 2.5f), v3_make(-0.30f, -0.14f, 2.5f),
	};
	emit_loft4(c0, c1, 1, 0, 235, 240, 248);
	emit_loft4(c1, c2, 0, 1, 245, 248, 255);

	/* Tinted metallic canopy bubble on top of central hull */
	v3 k0[4] = {
		v3_make(-0.44f, 0.46f, -1.35f), v3_make(0.44f, 0.46f, -1.35f),
		v3_make(0.52f, 0.42f, -1.35f), v3_make(-0.52f, 0.42f, -1.35f),
	};
	v3 k1[4] = {
		v3_make(-0.36f, 0.86f, -0.25f), v3_make(0.36f, 0.86f, -0.25f),
		v3_make(0.50f, 0.48f, -0.25f), v3_make(-0.50f, 0.48f, -0.25f),
	};
	v3 k2[4] = {
		v3_make(-0.18f, 0.42f, 1.35f), v3_make(0.18f, 0.42f, 1.35f),
		v3_make(0.26f, 0.34f, 1.35f), v3_make(-0.26f, 0.34f, 1.35f),
	};
	emit_loft4(k0, k1, 1, 0, 70, 105, 145);
	emit_loft4(k1, k2, 0, 1, 80, 125, 170);

	/* Twin forward catamaran sponsons / nose prongs + swept winglets + vertical tail fins */
	for (int side = -1; side <= 1; side += 2) {
		float s = (float)side;
		float x_in0 = 0.65f * s, x_out0 = 1.48f * w_scale * s;
		float x_in1 = 0.56f * s, x_out1 = 1.22f * w_scale * s;
		float x_tip_in = 0.46f * s, x_tip_out = 0.72f * w_scale * s;
		v3 p0[4], p1[4], p2[4];
		if (side > 0) {
			p0[0] = v3_make(x_in0, 0.24f, -2.5f);  p0[1] = v3_make(x_out0, 0.16f, -2.5f);
			p0[2] = v3_make(x_out0, -0.24f, -2.5f); p0[3] = v3_make(x_in0, -0.24f, -2.5f);
			p1[0] = v3_make(x_in1, 0.28f, 1.1f);   p1[1] = v3_make(x_out1, 0.18f, 1.1f);
			p1[2] = v3_make(x_out1, -0.20f, 1.1f);  p1[3] = v3_make(x_in1, -0.22f, 1.1f);
			p2[0] = v3_make(x_tip_in, 0.08f, nose_z); p2[1] = v3_make(x_tip_out, 0.04f, nose_z);
			p2[2] = v3_make(x_tip_out, -0.10f, nose_z); p2[3] = v3_make(x_tip_in, -0.10f, nose_z);
		} else {
			p0[0] = v3_make(x_out0, 0.16f, -2.5f);  p0[1] = v3_make(x_in0, 0.24f, -2.5f);
			p0[2] = v3_make(x_in0, -0.24f, -2.5f);  p0[3] = v3_make(x_out0, -0.24f, -2.5f);
			p1[0] = v3_make(x_out1, 0.18f, 1.1f);   p1[1] = v3_make(x_in1, 0.28f, 1.1f);
			p1[2] = v3_make(x_in1, -0.22f, 1.1f);   p1[3] = v3_make(x_out1, -0.20f, 1.1f);
			p2[0] = v3_make(x_tip_out, 0.04f, nose_z); p2[1] = v3_make(x_tip_in, 0.08f, nose_z);
			p2[2] = v3_make(x_tip_in, -0.10f, nose_z); p2[3] = v3_make(x_tip_out, -0.10f, nose_z);
		}
		emit_loft4(p0, p1, 1, 0, 215, 222, 235);
		emit_loft4(p1, p2, 0, 1, 250, 252, 255);

		/* Swept outer airbrake wing (top & bottom faces) */
		v3 w0 = v3_make(1.25f * w_scale * s, 0.10f, 0.2f);
		v3 w1 = v3_make(1.38f * w_scale * s, 0.08f, -2.4f);
		v3 w2 = v3_make(2.45f * w_scale * s, variant ? -0.10f : 0.28f, -2.85f);
		v3 w3 = v3_make(2.25f * w_scale * s, variant ? -0.06f : 0.24f, -1.55f);
		if (side > 0) {
			emit_mquad(w0, w3, w2, w1, 245, 245, 252);
			emit_mquad(w0, w1, w2, w3, 175, 182, 195);
		} else {
			emit_mquad(w0, w1, w2, w3, 245, 245, 252);
			emit_mquad(w0, w3, w2, w1, 175, 182, 195);
		}

		/* Angled vertical tail stabilizer fin */
		v3 f0 = v3_make(0.82f * s, 0.26f, -1.4f);
		v3 f1 = v3_make(0.88f * s, 0.24f, -2.95f);
		v3 f2 = v3_make(1.18f * s, 1.05f, -3.20f);
		v3 f3 = v3_make(1.06f * s, 0.92f, -2.15f);
		emit_mquad(f0, f1, f2, f3, 235, 240, 250);
		emit_mquad(f0, f3, f2, f1, 215, 220, 232);

		/* Recessed rear thruster nozzle bell */
		float tx = 0.44f * s;
		v3 t0 = v3_make(tx - 0.24f, 0.24f, -3.05f);
		v3 t1 = v3_make(tx + 0.24f, 0.24f, -3.05f);
		v3 t2 = v3_make(tx + 0.24f, -0.14f, -3.05f);
		v3 t3 = v3_make(tx - 0.24f, -0.14f, -3.05f);
		emit_mquad(t0, t3, t2, t1, 255, 220, 160);
	}
	meshes[id].count = mesh_pool_n - meshes[id].first;
}

static void emit_box(v3 p0, v3 p1, uint8_t cr, uint8_t cg, uint8_t cb)
{
	v3 c[8] = {
		v3_make(p0.x, p0.y, p0.z), v3_make(p1.x, p0.y, p0.z),
		v3_make(p1.x, p1.y, p0.z), v3_make(p0.x, p1.y, p0.z),
		v3_make(p0.x, p0.y, p1.z), v3_make(p1.x, p0.y, p1.z),
		v3_make(p1.x, p1.y, p1.z), v3_make(p0.x, p1.y, p1.z),
	};
	emit_mquad(c[4], c[5], c[6], c[7], cr, cg, cb);
	emit_mquad(c[1], c[0], c[3], c[2], cr, cg, cb);
	emit_mquad(c[0], c[4], c[7], c[3], cr, cg, cb);
	emit_mquad(c[5], c[1], c[2], c[6], cr, cg, cb);
	emit_mquad(c[3], c[7], c[6], c[2], cr, cg, cb);
	emit_mquad(c[0], c[1], c[5], c[4], cr, cg, cb);
}

static void gen_meshes(void)
{
	mesh_pool_n = 0;
	build_hovercraft(MESH_CRAFT_PLAYER, 0);
	build_hovercraft(MESH_CRAFT_RIVAL, 1);

	/* MESH_ARCH: Overhead racing gantry arch spanning [-16..+16] across the track */
	meshes[MESH_ARCH].first = mesh_pool_n;
	emit_box(v3_make(-16.8f, -1.5f, -1.2f), v3_make(-14.6f, 12.5f, 1.2f), 190, 200, 215);
	emit_box(v3_make(14.6f, -1.5f, -1.2f), v3_make(16.8f, 12.5f, 1.2f), 190, 200, 215);
	emit_box(v3_make(-16.8f, 11.2f, -1.6f), v3_make(16.8f, 13.8f, 1.6f), 240, 245, 255);
	/* Bright underside banner strip */
	emit_box(v3_make(-13.5f, 10.6f, -0.9f), v3_make(13.5f, 11.2f, 0.9f), 255, 230, 140);
	meshes[MESH_ARCH].count = mesh_pool_n - meshes[MESH_ARCH].first;

	/* MESH_PYLON: Trackside light beacon tower */
	meshes[MESH_PYLON].first = mesh_pool_n;
	emit_box(v3_make(-0.7f, -1.0f, -0.7f), v3_make(0.7f, 7.5f, 0.7f), 185, 195, 212);
	emit_box(v3_make(-1.1f, 7.2f, -1.1f), v3_make(1.1f, 8.8f, 1.1f), 255, 245, 210);
	meshes[MESH_PYLON].count = mesh_pool_n - meshes[MESH_PYLON].first;
}

/* --- Procedural 138 BPM electronic racing synth + hover-turbine & SFX mixer -------------------- */

static struct {
	uint32_t rng;
	int music_on, track_key;
	float speed_norm; /* 0..1.35 */
	float boost_lvl;  /* 0..1 */
	float seq_t;
	int step;
	float kick_ph, kick_env;
	float hat_env, snare_env;
	float bass_ph, bass_freq, bass_env, svf_lp, svf_bp;
	float lead_ph, lead_freq, lead_env;
	float eng_ph1, eng_ph2;
	float sfx_boost, sfx_scrape, sfx_bump, sfx_lap, sfx_beep, sfx_beep_hi;
	int delay_pos;
	int16_t delay_l[4096], delay_r[4096];
} syn;

static struct {
	int on, rate;
	uint32_t sig_frames;
	struct audiosig sig;
} atest;

static float midi_hz(int note)
{
	static const float semi[12] = {
		220.00f, 233.08f, 246.94f, 261.63f, 277.18f, 293.66f,
		311.13f, 329.63f, 349.23f, 369.99f, 392.00f, 415.30f
	};
	int oct = 0;
	while (note < 0)
		note += 12, oct--;
	while (note >= 12)
		note -= 12, oct++;
	float f = semi[note];
	while (oct > 0)
		f *= 2.0f, oct--;
	while (oct < 0)
		f *= 0.5f, oct++;
	return f;
}

void racer_audio_mix(int16_t *stereo_pcm, int frames, int rate)
{
	if (rate <= 0)
		return;
	if (atest.on) {
		if (!atest.rate) {
			atest.rate = rate;
			audiosig_init(&atest.sig, (unsigned)rate);
		}
		for (int i = 0; i < frames; i++) {
			int l, r;
			atest.sig_frames += (uint32_t)audiosig_next(&atest.sig, &l, &r);
			stereo_pcm[i * 2] = (int16_t)l;
			stereo_pcm[i * 2 + 1] = (int16_t)r;
		}
		return;
	}
	if (!syn.rng)
		syn.rng = 0x51ced123U;

	float dt = 1.0f / (float)rate;
	static const int minor_sc[8] = {0, 2, 3, 5, 7, 8, 10, 12};
	static const int bass_pat[16] = {0, 0, 12, 0, 7, 0, 10, 12, 0, 0, 12, 0, 5, 7, 10, 7};
	static const int prog_root[4] = {0, -4, -2, 3}; /* i - VI - VII - III */
	int key_base = (syn.track_key & 3) * 2 + 2;     /* B, C#, D#, F minor feel */

	for (int i = 0; i < frames; i++) {
		float ml = 0.0f, mr = 0.0f;

		/* 138 BPM 16th-note electronic racing groove */
		if (syn.music_on) {
			syn.seq_t += dt;
			if (syn.seq_t >= 0.1087f || syn.bass_freq <= 0.0f) {
				syn.seq_t -= 0.1087f;
				if (syn.seq_t < 0.0f)
					syn.seq_t = 0.0f;
				int st = syn.step & 63;
				syn.step = (syn.step + 1) & 63;
				int bar_root = key_base + prog_root[(st >> 4) & 3];

				/* 4-on-the-floor kick + snare on 4 & 12 + crisp off-beat hi-hats */
				if ((st & 3) == 0) {
					syn.kick_env = 1.0f;
					syn.kick_ph = 0.0f;
				}
				if ((st & 7) == 4)
					syn.snare_env = 1.0f;
				if ((st & 3) == 2)
					syn.hat_env = 0.85f;
				else if (st & 1)
					syn.hat_env = 0.28f;

				/* Rolling 16th-note acid/saw bass */
				syn.bass_freq = midi_hz(bar_root - 24 + bass_pat[st & 15]);
				syn.bass_env = ((st & 3) == 2) ? 1.0f : 0.78f;

				/* Driving synth arpeggio / lead hook */
				uint32_t h = hash32((uint32_t)st * 97U ^ (uint32_t)syn.track_key * 17U);
				if ((st & 1) == 0 || (h & 3U) == 0U) {
					int deg = minor_sc[(h >> 2) & 7U];
					syn.lead_freq = midi_hz(bar_root + deg);
					syn.lead_env = ((st & 3) == 0) ? 0.95f : 0.65f;
				}
			}

			/* Kick drum */
			float kick = 0.0f;
			if (syn.kick_env > 0.002f) {
				float kf = 46.0f + 135.0f * syn.kick_env * syn.kick_env;
				syn.kick_ph += kf * dt;
				if (syn.kick_ph >= 1.0f)
					syn.kick_ph -= 1.0f;
				kick = m_sinf(syn.kick_ph * (float)TAU) * syn.kick_env * 0.34f;
				syn.kick_env *= (1.0f - 13.0f * dt);
			}

			/* Snare & hi-hat */
			float noise = rng_fsym(&syn.rng);
			float perc = 0.0f;
			if (syn.snare_env > 0.002f) {
				perc += noise * syn.snare_env * 0.16f;
				syn.snare_env *= (1.0f - 18.0f * dt);
			}
			if (syn.hat_env > 0.002f) {
				perc += noise * syn.hat_env * 0.09f;
				syn.hat_env *= (1.0f - 38.0f * dt);
			}

			/* Resonant sawtooth bassline */
			syn.bass_ph += syn.bass_freq * dt;
			if (syn.bass_ph >= 1.0f)
				syn.bass_ph -= 1.0f;
			syn.bass_env *= (1.0f - 7.5f * dt);
			float saw = syn.bass_ph * 2.0f - 1.0f;
			float cut = clampf(0.14f + 0.28f * syn.bass_env + 0.08f * syn.speed_norm, 0.08f, 0.52f);
			syn.svf_lp += cut * syn.svf_bp;
			float hp = saw * 0.22f - syn.svf_lp - 0.42f * syn.svf_bp;
			syn.svf_bp += cut * hp;
			float bass = syn.svf_lp;

			/* FM/pulse racing lead + stereo ping-pong echo */
			syn.lead_ph += syn.lead_freq * dt;
			if (syn.lead_ph >= 1.0f)
				syn.lead_ph -= 1.0f;
			syn.lead_env *= (1.0f - 6.8f * dt);
			float lead = (syn.lead_ph < 0.35f ? 1.0f : -0.55f) * syn.lead_env * 0.085f;

			int dpos = syn.delay_pos;
			int tap_l = (dpos - 1600) & 4095;
			int tap_r = (dpos - 2400) & 4095;
			float dl = syn.delay_l[tap_l] * (1.0f / 32768.0f);
			float dr = syn.delay_r[tap_r] * (1.0f / 32768.0f);
			syn.delay_l[dpos] = (int16_t)clampi((int)((lead + dr * 0.42f) * 32767.0f), -32000, 32000);
			syn.delay_r[dpos] = (int16_t)clampi((int)((lead * 0.8f + dl * 0.42f) * 32767.0f), -32000, 32000);
			syn.delay_pos = (dpos + 1) & 4095;

			ml = kick + bass + perc * 0.9f + lead + dl * 0.55f;
			mr = kick + bass + perc * 1.1f + lead * 0.85f + dr * 0.55f;
		}

		/* Continuous hover-turbine whine + turbo plasma roar */
		float sp = clampf(syn.speed_norm, 0.0f, 1.4f);
		float ef1 = 82.0f + sp * 195.0f + syn.boost_lvl * 65.0f;
		float ef2 = ef1 * 1.502f;
		syn.eng_ph1 += ef1 * dt;
		if (syn.eng_ph1 >= 1.0f)
			syn.eng_ph1 -= 1.0f;
		syn.eng_ph2 += ef2 * dt;
		if (syn.eng_ph2 >= 1.0f)
			syn.eng_ph2 -= 1.0f;
		float eng = (m_sinf(syn.eng_ph1 * (float)TAU) * 0.65f +
			     (syn.eng_ph2 * 2.0f - 1.0f) * 0.35f) * (0.045f + sp * 0.075f);

		/* One-shot racing SFX */
		float sfx = 0.0f;
		if (syn.sfx_boost > 0.002f) {
			sfx += (m_sinf(syn.sfx_boost * 110.0f) * 0.5f + rng_fsym(&syn.rng) * 0.4f) * syn.sfx_boost * 0.24f;
			syn.sfx_boost *= (1.0f - 2.6f * dt);
		}
		if (syn.sfx_scrape > 0.002f) {
			sfx += rng_fsym(&syn.rng) * syn.sfx_scrape * 0.22f;
			syn.sfx_scrape *= (1.0f - 12.0f * dt);
		}
		if (syn.sfx_bump > 0.002f) {
			sfx += m_sinf(syn.sfx_bump * 55.0f) * syn.sfx_bump * 0.30f;
			syn.sfx_bump *= (1.0f - 9.0f * dt);
		}
		if (syn.sfx_lap > 0.002f) {
			float lf = syn.sfx_lap > 0.55f ? 587.3f : syn.sfx_lap > 0.30f ? 784.0f : 1174.7f;
			sfx += m_sinf((1.0f - syn.sfx_lap) * lf * (float)TAU) * syn.sfx_lap * 0.22f;
			syn.sfx_lap *= (1.0f - 2.2f * dt);
		}
		if (syn.sfx_beep > 0.002f) {
			float bf = syn.sfx_beep_hi > 0.5f ? 880.0f : 440.0f;
			sfx += m_sinf((1.0f - syn.sfx_beep) * bf * (float)TAU) * syn.sfx_beep * 0.25f;
			syn.sfx_beep *= (1.0f - 5.5f * dt);
		}

		int out_l = (int)((ml + eng + sfx) * 20000.0f);
		int out_r = (int)((mr + eng + sfx) * 20000.0f);
		stereo_pcm[i * 2] = (int16_t)clampi(out_l, -32000, 32000);
		stereo_pcm[i * 2 + 1] = (int16_t)clampi(out_r, -32000, 32000);
	}
}

#endif
