/*
 * gen.h: procedural maths (Pentium x87, no libm), seamless fractal/cellular texture synthesis,
 * displaced 3D mesh generators (asteroids, planets, orbital ring station, interceptor drone) and
 * the polyphonic soft-synth + stereo echo audio mixer. Included by space.c.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_SPACE_GEN_H
#define WSH_SPACE_GEN_H

#define PI 3.14159265358979323846
#define TAU 6.28318530717958647692

/* --- Pentium x87 maths (no libm, no P6 instructions) ------------------------------------------ */

static double m_sin(double x)
{
	double n = x * (1.0 / TAU);
	int32_t i = (int32_t)(n >= 0 ? n + 0.5 : n - 0.5);
	x -= (double)i * TAU;
	if (x > PI * 0.5)
		x = PI - x;
	else if (x < -PI * 0.5)
		x = -PI - x;
	double x2 = x * x;
	return x * (1.0 + x2 * (-1.0 / 6.0 + x2 * (1.0 / 120.0 + x2 * (-1.0 / 5040.0 + x2 * (1.0 / 362880.0)))));
}
static double m_cos(double x)
{
	return m_sin(x + PI * 0.5);
}
static double m_sqrt(double x)
{
	if (x <= 0.0)
		return 0.0;
	double r;
	__asm__("fsqrt" : "=t"(r) : "0"(x));
	return r;
}
static float m_sqrtf(float x)
{
	return (float)m_sqrt((double)x);
}
static float m_sinf(float x)
{
	return (float)m_sin((double)x);
}
static float m_cosf(float x)
{
	return (float)m_cos((double)x);
}
static float m_fabsf(float x)
{
	return x < 0.0f ? -x : x;
}
static int clampi(int v, int lo, int hi)
{
	if (v < lo)
		return lo;
	if (v > hi)
		return hi;
	return v;
}
static float clampf(float v, float lo, float hi)
{
	if (v < lo)
		return lo;
	if (v > hi)
		return hi;
	return v;
}
static float m_atan2f(float y, float x)
{
	float ax = m_fabsf(x), ay = m_fabsf(y);
	float mn = ax < ay ? ax : ay, mx = ax > ay ? ax : ay;
	if (mx < 1e-8f)
		return 0.0f;
	float a = mn / mx, s = a * a;
	float r = ((-0.04649647f * s + 0.15931422f) * s - 0.32762276f) * s * a + a;
	if (ay > ax)
		r = 1.57079633f - r;
	if (x < 0.0f)
		r = 3.14159265f - r;
	return y < 0.0f ? -r : r;
}

typedef struct {
	float x, y, z;
} v3f;

static inline v3f v3_make(float x, float y, float z) { v3f r = {x, y, z}; return r; }
static inline v3f v3_add(v3f a, v3f b) { return v3_make(a.x + b.x, a.y + b.y, a.z + b.z); }
static inline v3f v3_sub(v3f a, v3f b) { return v3_make(a.x - b.x, a.y - b.y, a.z - b.z); }
static inline v3f v3_scale(v3f a, float s) { return v3_make(a.x * s, a.y * s, a.z * s); }
static inline float v3_dot(v3f a, v3f b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline v3f v3_cross(v3f a, v3f b)
{
	return v3_make(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}
static inline float v3_len(v3f a) { return m_sqrtf(v3_dot(a, a)); }
static inline v3f v3_norm(v3f a)
{
	float l = v3_len(a);
	return l > 1e-6f ? v3_scale(a, 1.0f / l) : v3_make(0.0f, 0.0f, 1.0f);
}

/* --- hashes & seamless procedural noise ------------------------------------------------------- */

static uint32_t hash32(uint32_t x)
{
	x ^= x >> 16;
	x *= 0x7feb352dU;
	x ^= x >> 15;
	x *= 0x846ca68bU;
	x ^= x >> 16;
	return x;
}
static float hash01(uint32_t x)
{
	return (float)(hash32(x) & 0xffffffU) * (1.0f / 16777215.0f);
}
static float rnd_next(uint32_t *s)
{
	*s = *s * 1664525U + 1013904223U;
	return (float)((*s >> 8) & 0xffffffU) * (1.0f / 16777215.0f);
}
static float smootht(float t)
{
	return t * t * (3.0f - 2.0f * t);
}

/* Seamless tileable 2D value noise over period p (power of two), x and y in [0..p) */
static float tnoise2(float x, float y, int p, uint32_t seed)
{
	int mask = p - 1;
	int ix = (int)x, iy = (int)y;
	if (x < (float)ix)
		ix--;
	if (y < (float)iy)
		iy--;
	float fx = smootht(x - (float)ix), fy = smootht(y - (float)iy);
	int x0 = ix & mask, x1 = (ix + 1) & mask;
	int y0 = iy & mask, y1 = (iy + 1) & mask;
	float a = hash01((uint32_t)(y0 * 257 + x0) ^ seed);
	float b = hash01((uint32_t)(y0 * 257 + x1) ^ seed);
	float c = hash01((uint32_t)(y1 * 257 + x0) ^ seed);
	float d = hash01((uint32_t)(y1 * 257 + x1) ^ seed);
	return (a + (b - a) * fx) * (1.0f - fy) + (c + (d - c) * fx) * fy;
}

/* Multi-octave tileable fBm for u, v in [0..1) */
static float fbm2(float u, float v, int oct, int base_p, uint32_t seed)
{
	float sum = 0.0f, amp = 0.5f, norm = 0.0f;
	int p = base_p;
	for (int i = 0; i < oct; i++) {
		sum += amp * tnoise2(u * (float)p, v * (float)p, p, seed + (uint32_t)i * 0x9e3779b9U);
		norm += amp;
		amp *= 0.5f;
		p <<= 1;
	}
	return sum / norm;
}

/* Seamless Voronoi crater profile: returns [-0.6 .. +0.35] bowl + raised ejecta rim */
static float crater2(float u, float v, int cells, uint32_t seed)
{
	float gx = u * (float)cells, gy = v * (float)cells;
	int cx = (int)gx, cy = (int)gy;
	float min_d2 = 9.0f;
	for (int dy = -1; dy <= 1; dy++) {
		for (int dx = -1; dx <= 1; dx++) {
			int nx = (cx + dx) & (cells - 1);
			int ny = (cy + dy) & (cells - 1);
			uint32_t h = hash32((uint32_t)(ny * 131 + nx) ^ seed);
			if ((h & 3U) == 0U)
				continue;
			float px = (float)(cx + dx) + 0.18f + 0.64f * ((float)(h & 255U) / 255.0f);
			float py = (float)(cy + dy) + 0.18f + 0.64f * ((float)((h >> 8) & 255U) / 255.0f);
			float ddx = gx - px, ddy = gy - py;
			float d2 = ddx * ddx + ddy * ddy;
			if (d2 < min_d2)
				min_d2 = d2;
		}
	}
	float d = m_sqrtf(min_d2) * 2.2f;
	if (d < 0.75f) {
		float t = d / 0.75f;
		return -0.55f * (1.0f - t * t);
	}
	if (d < 1.15f) {
		float t = (d - 0.75f) / 0.40f;
		return 0.28f * m_sinf(t * 3.14159f);
	}
	return 0.0f;
}

/* 3D value noise for seamless 3D mesh displacement */
static float noise3(float x, float y, float z, uint32_t seed)
{
	int ix = (int)(x + 1024.0f) - 1024;
	int iy = (int)(y + 1024.0f) - 1024;
	int iz = (int)(z + 1024.0f) - 1024;
	float fx = smootht(x - (float)ix), fy = smootht(y - (float)iy), fz = smootht(z - (float)iz);
	float c[8];
	for (int k = 0; k < 8; k++) {
		uint32_t h = (uint32_t)((ix + (k & 1)) * 73856093) ^
			     (uint32_t)((iy + ((k >> 1) & 1)) * 19349663) ^
			     (uint32_t)((iz + ((k >> 2) & 1)) * 83492791) ^ seed;
		c[k] = hash01(h);
	}
	float x00 = c[0] + (c[1] - c[0]) * fx, x10 = c[2] + (c[3] - c[2]) * fx;
	float x01 = c[4] + (c[5] - c[4]) * fx, x11 = c[6] + (c[7] - c[6]) * fx;
	float y0 = x00 + (x10 - x00) * fy, y1 = x01 + (x11 - x01) * fy;
	return y0 + (y1 - y0) * fz;
}

/* --- procedural textures (.bss only -> 0 bytes on disk) --------------------------------------- */

#define MIPSIZE(s) ((s) * (s) * 4 / 3 + 4)
static uint32_t tex_font[128 * 128];
static uint32_t tex_rock[MIPSIZE(256)];
static uint32_t tex_planet[MIPSIZE(256)];
static uint32_t tex_hull[MIPSIZE(256)];
static uint32_t tex_flare[64 * 64];
static uint32_t tex_nebula[MIPSIZE(256)];
static uint32_t tex_warp[MIPSIZE(256)];
static int mip_levels_256;

static uint32_t pack_argb(int a, int r, int g, int b)
{
	return ((uint32_t)clampi(a, 0, 255) << 24) | ((uint32_t)clampi(r, 0, 255) << 16) |
	       ((uint32_t)clampi(g, 0, 255) << 8) | (uint32_t)clampi(b, 0, 255);
}

static int make_mips(uint32_t *t, int size)
{
	int levels = 1;
	uint32_t *src = t;
	for (int s = size / 2; s >= 1; s /= 2, levels++) {
		uint32_t *dst = src + s * 2 * s * 2;
		for (int y = 0; y < s; y++)
			for (int x = 0; x < s; x++) {
				uint32_t c[4] = {
					src[(2 * y) * 2 * s + 2 * x],
					src[(2 * y) * 2 * s + 2 * x + 1],
					src[(2 * y + 1) * 2 * s + 2 * x],
					src[(2 * y + 1) * 2 * s + 2 * x + 1]
				};
				uint32_t o = 0;
				for (int sh = 0; sh < 32; sh += 8) {
					uint32_t sum = 2;
					for (int i = 0; i < 4; i++)
						sum += (c[i] >> sh) & 0xffU;
					o |= (sum >> 2) << sh;
				}
				dst[y * s + x] = o;
			}
		src = dst;
	}
	return levels;
}

static void gen_all_textures(void)
{
	/* 1. Font (128x128 ARGB4444) */
	memset(tex_font, 0, sizeof(tex_font));
	for (int c = 32; c <= 95; c++) {
		const uint8_t *g = font_glyph(c);
		int cx = ((c - 32) & 15) * 8, cy = ((c - 32) >> 4) * 8;
		for (int y = 0; y < 7; y++)
			for (int x = 0; x < 5; x++)
				if (g[y] & (0x10 >> x))
					tex_font[(cy + y) * 128 + cx + x] = 0xffffffffU;
	}

	/* 2. Asteroid Rock (256x256: fBm + Voronoi craters + baked bump relief + mineral flecks) */
	static float hmap[256 * 256];
	for (int y = 0; y < 256; y++) {
		float v = y * (1.0f / 256.0f);
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f);
			float n = fbm2(u, v, 5, 8, 0x13579bdfU);
			float cr = crater2(u, v, 8, 0x2468ace0U) * 0.65f + crater2(u, v, 16, 0x99117733U) * 0.35f;
			hmap[y * 256 + x] = n + cr * 0.55f;
		}
	}
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float h0 = hmap[y * 256 + x];
			float hx = hmap[y * 256 + ((x + 1) & 255)] - hmap[y * 256 + ((x - 1) & 255)];
			float hy = hmap[((y + 1) & 255) * 256 + x] - hmap[((y - 1) & 255) * 256 + x];
			float bump = clampf(0.72f + (hx * 2.2f + hy * 1.8f), 0.25f, 1.35f);
			float vein = fbm2(x / 256.0f + h0 * 0.2f, y / 256.0f, 3, 16, 0x55aa1234U);
			int glint = vein > 0.73f ? (int)((vein - 0.73f) * 380.0f) : 0;
			int base = (int)((95.0f + h0 * 115.0f) * bump);
			tex_rock[y * 256 + x] = pack_argb(255, base + glint, (int)(base * 0.96f) + glint, (int)(base * 0.90f) + glint * 2);
		}
	}
	mip_levels_256 = make_mips(tex_rock, 256);

	/* 3. Planet bands & clouds (256x256: domain-warped latitudinal storms & continents) */
	for (int y = 0; y < 256; y++) {
		float v = y * (1.0f / 256.0f);
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f);
			float wx = fbm2(u, v, 4, 4, 0xabcddcbaU) - 0.5f;
			float wy = fbm2(u + 0.37f, v + 0.19f, 4, 4, 0x778899aaU) - 0.5f;
			float band = 0.5f + 0.5f * m_sinf((v + wy * 0.22f) * 25.1327f + wx * 3.2f);
			float detail = fbm2(u + wx * 0.25f, v + wy * 0.25f, 5, 8, 0x31415926U);
			float lum = 0.42f + 0.34f * band + 0.32f * detail;
			int r = (int)(lum * 235.0f), g = (int)((lum * 0.94f + 0.04f * band) * 230.0f), b = (int)((lum * 0.88f + 0.12f * (1.0f - band)) * 235.0f);
			tex_planet[y * 256 + x] = pack_argb(255, r, g, b);
		}
	}
	make_mips(tex_planet, 256);

	/* 4. Sci-fi Hull Plating (256x256: .kkrieger beveled panels, rivets, vents & accent glow) */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			int px = x & 63, py = y & 31;
			int row = y >> 5;
			if (row & 1)
				px = (x + 32) & 63;
			float grime = fbm2(x / 256.0f, y / 256.0f, 4, 8, 0xdeadbeefU);
			int seam = (px < 2 || py < 2 || px == 63 || py == 31);
			int bevel = (!seam && (px == 2 || py == 2)) ? 32 : (!seam && (px == 62 || py == 30)) ? -26 : 0;
			int rivet = (!seam && (px == 5 || px == 58) && (py == 5 || py == 26));
			int vent = (row == 3 || row == 7) && py >= 10 && py <= 21 && (px & 7) < 4 && px > 8 && px < 56;
			int base = 132 + (int)((grime - 0.5f) * 48.0f) + bevel;
			if (seam)
				base = 42;
			else if (vent)
				base = 34;
			else if (rivet)
				base += 36;
			int r = base, g = base + 4, b = base + 12;
			/* Subtle glowing cyan trim strip along one row */
			if (row == 1 && py >= 14 && py <= 17 && !seam) {
				r = 90; g = 220; b = 255;
			}
			tex_hull[y * 256 + x] = pack_argb(255, r, g, b);
		}
	}
	make_mips(tex_hull, 256);

	/* 5. Corona / Plasma / Star Flare (64x64 ARGB4444) */
	for (int y = 0; y < 64; y++) {
		float dy = (y - 31.5f) / 31.5f;
		for (int x = 0; x < 64; x++) {
			float dx = (x - 31.5f) / 31.5f;
			float r = m_sqrtf(dx * dx + dy * dy);
			float core = r < 1.0f ? (1.0f - r) : 0.0f;
			core = core * core;
			float spike = (m_fabsf(dx) < 0.14f ? (1.0f - m_fabsf(dy)) * (1.0f - m_fabsf(dx) / 0.14f) : 0.0f) +
				      (m_fabsf(dy) < 0.14f ? (1.0f - m_fabsf(dx)) * (1.0f - m_fabsf(dy) / 0.14f) : 0.0f);
			int a = (int)(clampf(core * 1.15f + spike * 0.42f, 0.0f, 1.0f) * 255.0f);
			int br = (int)(clampf(core * 1.4f + 0.45f, 0.0f, 1.0f) * 255.0f);
			tex_flare[y * 64 + x] = pack_argb(a, br, br, 255);
		}
	}

	/* 6. Deep-Space Nebula (256x256: domain-warped cosmic filaments) */
	for (int y = 0; y < 256; y++) {
		float v = y * (1.0f / 256.0f);
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f);
			float qx = fbm2(u, v, 4, 4, 0x11223344U);
			float qy = fbm2(u + 0.5f, v + 0.25f, 4, 4, 0x55667788U);
			float f = fbm2(u + qx * 0.45f, v + qy * 0.45f, 5, 4, 0x99aabbccU);
			float w = clampf((f - 0.36f) * 2.1f, 0.0f, 1.0f);
			w = w * w;
			int c1 = (int)(w * 210.0f), c2 = (int)(w * qx * 240.0f);
			tex_nebula[y * 256 + x] = pack_argb(255, c1, (c1 + c2) >> 1, c2 + (c1 >> 1));
		}
	}
	make_mips(tex_nebula, 256);

	/* 7. Hyperspace Warp & Planetary Ring Bands (256x256) */
	for (int y = 0; y < 256; y++) {
		float v = y * (1.0f / 256.0f);
		for (int x = 0; x < 256; x++) {
			float u = x * (1.0f / 256.0f);
			float streak = fbm2(u * 2.0f, v * 0.5f, 4, 8, 0xfeedfaceU);
			float ring = 0.5f + 0.5f * m_sinf(v * 50.265f + streak * 4.0f);
			int c = (int)(clampf(streak * 0.75f + ring * 0.45f - 0.15f, 0.0f, 1.0f) * 255.0f);
			tex_warp[y * 256 + x] = pack_argb(255, (c * 3) >> 2, c, 255 * c / 255);
		}
	}
	make_mips(tex_warp, 256);
}

/* --- procedural 3D meshes --------------------------------------------------------------------- */

#define MAX_MESH_V 340
#define MAX_MESH_T 560

struct mtri {
	uint16_t a, b, c;
	float uv[3][2];
};

struct mesh {
	int nv, nt;
	v3f pos[MAX_MESH_V];
	v3f nrm[MAX_MESH_V];
	struct mtri tri[MAX_MESH_T];
};

enum {
	MESH_SPHERE,
	MESH_AST0,
	MESH_AST1,
	MESH_AST2,
	MESH_AST3,
	MESH_STATION,
	MESH_DRONE,
	MESH_CRYSTAL,
	MESH_COUNT
};

static struct mesh meshes[MESH_COUNT];

static void mesh_clear(struct mesh *m)
{
	m->nv = 0;
	m->nt = 0;
}

static int mesh_add_v(struct mesh *m, v3f p)
{
	if (m->nv >= MAX_MESH_V)
		return MAX_MESH_V - 1;
	m->pos[m->nv] = p;
	m->nrm[m->nv] = v3_make(0, 0, 0);
	return m->nv++;
}

static void mesh_add_tri(struct mesh *m, int a, int b, int c, float u0, float v0, float u1, float v1, float u2, float v2)
{
	if (m->nt >= MAX_MESH_T)
		return;
	struct mtri *t = &m->tri[m->nt++];
	t->a = (uint16_t)a; t->b = (uint16_t)b; t->c = (uint16_t)c;
	t->uv[0][0] = u0; t->uv[0][1] = v0;
	t->uv[1][0] = u1; t->uv[1][1] = v1;
	t->uv[2][0] = u2; t->uv[2][1] = v2;
}

static void mesh_add_quad(struct mesh *m, int a, int b, int c, int d, float u0, float v0, float u1, float v1)
{
	mesh_add_tri(m, a, b, c, u0, v0, u1, v0, u1, v1);
	mesh_add_tri(m, a, c, d, u0, v0, u1, v1, u0, v1);
}

static void mesh_calc_normals(struct mesh *m)
{
	for (int i = 0; i < m->nv; i++)
		m->nrm[i] = v3_make(0, 0, 0);
	for (int i = 0; i < m->nt; i++) {
		int a = m->tri[i].a, b = m->tri[i].b, c = m->tri[i].c;
		v3f n = v3_cross(v3_sub(m->pos[b], m->pos[a]), v3_sub(m->pos[c], m->pos[a]));
		m->nrm[a] = v3_add(m->nrm[a], n);
		m->nrm[b] = v3_add(m->nrm[b], n);
		m->nrm[c] = v3_add(m->nrm[c], n);
	}
	for (int i = 0; i < m->nv; i++)
		m->nrm[i] = v3_norm(m->nrm[i]);
}

/* Build a UV sphere (rings x segs) with optional 3D asteroid rock displacement */
static void gen_uv_sphere(struct mesh *m, int rings, int segs, int rock_seed, float sx, float sy, float sz)
{
	mesh_clear(m);
	for (int r = 0; r <= rings; r++) {
		float v = (float)r / (float)rings;
		float phi = (v - 0.5f) * (float)PI;
		float cp = m_cosf(phi), sp = m_sinf(phi);
		for (int s = 0; s <= segs; s++) {
			/* Wrap seam vertex to exact same 3D position so normals & edges stay water-tight */
			int sw = s == segs ? 0 : s;
			float th = (float)sw / (float)segs * (float)TAU;
			v3f dir = v3_make(cp * m_cosf(th), sp, cp * m_sinf(th));
			float rad = 1.0f;
			if (rock_seed) {
				uint32_t sd = (uint32_t)rock_seed * 0x45d9f3bU;
				float n1 = noise3(dir.x * 1.8f + 5.0f, dir.y * 1.8f, dir.z * 1.8f, sd);
				float n2 = noise3(dir.x * 3.7f, dir.y * 3.7f + 3.0f, dir.z * 3.7f, sd ^ 0x123456U);
				float n3 = noise3(dir.x * 7.5f, dir.y * 7.5f, dir.z * 7.5f + 2.0f, sd ^ 0xabcdefU);
				rad = 0.72f + 0.42f * n1 + 0.18f * n2 + 0.08f * n3;
				/* Carve 3 procedural 3D impact craters into the asteroid */
				for (int k = 0; k < 3; k++) {
					uint32_t ch = hash32(sd + (uint32_t)k * 977U);
					v3f cd = v3_norm(v3_make(((int)(ch & 255U) - 128) / 128.0f,
								 (((int)((ch >> 8) & 255U) - 128)) / 128.0f,
								 (((int)((ch >> 16) & 255U) - 128)) / 128.0f));
					float d = v3_dot(dir, cd);
					if (d > 0.72f) {
						float t = (d - 0.72f) / 0.28f;
						rad -= 0.22f * t * t;
					} else if (d > 0.60f) {
						float t = (d - 0.60f) / 0.12f;
						rad += 0.06f * m_sinf(t * 3.14159f);
					}
				}
			}
			v3f p = v3_make(dir.x * rad * sx, dir.y * rad * sy, dir.z * rad * sz);
			int vi = mesh_add_v(m, p);
			if (!rock_seed)
				m->nrm[vi] = dir;
		}
	}
	int stride = segs + 1;
	for (int r = 0; r < rings; r++) {
		for (int s = 0; s < segs; s++) {
			int i0 = r * stride + s, i1 = i0 + 1;
			int i2 = (r + 1) * stride + s + 1, i3 = (r + 1) * stride + s;
			float u0 = (float)s / (float)segs * (rock_seed ? 2.0f : 1.0f);
			float u1 = (float)(s + 1) / (float)segs * (rock_seed ? 2.0f : 1.0f);
			float v0 = (float)r / (float)rings * (rock_seed ? 2.0f : 1.0f);
			float v1 = (float)(r + 1) / (float)rings * (rock_seed ? 2.0f : 1.0f);
			mesh_add_tri(m, i0, i3, i2, u0, v0, u0, v1, u1, v1);
			mesh_add_tri(m, i0, i2, i1, u0, v0, u1, v1, u1, v0);
		}
	}
	if (rock_seed) {
		mesh_calc_normals(m);
		/* Average seam normals so there is no lighting crease along s == 0 / s == segs */
		for (int r = 0; r <= rings; r++) {
			int a = r * stride, b = r * stride + segs;
			v3f av = v3_norm(v3_add(m->nrm[a], m->nrm[b]));
			m->nrm[a] = m->nrm[b] = av;
		}
	}
}

static void add_box_part(struct mesh *m, v3f c, float hx, float hy, float hz, float uv_scale)
{
	static const float faces[6][9] = {
		{ 0, 0, 1,  1, 0, 0,  0, 1, 0},
		{ 0, 0,-1, -1, 0, 0,  0, 1, 0},
		{ 1, 0, 0,  0, 0,-1,  0, 1, 0},
		{-1, 0, 0,  0, 0, 1,  0, 1, 0},
		{ 0, 1, 0,  1, 0, 0,  0, 0,-1},
		{ 0,-1, 0,  1, 0, 0,  0, 0, 1},
	};
	for (int f = 0; f < 6; f++) {
		const float *F = faces[f];
		int idx[4];
		static const float crn[4][2] = {{-1,-1}, {1,-1}, {1,1}, {-1,1}};
		for (int k = 0; k < 4; k++) {
			float u = crn[k][0], v = crn[k][1];
			v3f p = v3_make(c.x + (F[0] + F[3] * u + F[6] * v) * hx,
					c.y + (F[1] + F[4] * u + F[7] * v) * hy,
					c.z + (F[2] + F[5] * u + F[8] * v) * hz);
			idx[k] = mesh_add_v(m, p);
		}
		mesh_add_quad(m, idx[0], idx[1], idx[2], idx[3], 0.0f, 0.0f, uv_scale, uv_scale);
	}
}

/* Orbital Ring Space Station: 12-segment outer torus, 4 radial spokes & central hub */
static void gen_station_mesh(struct mesh *m)
{
	mesh_clear(m);
	const int N = 12, M = 4;
	const float R = 1.0f, r = 0.16f;
	for (int i = 0; i < N; i++) {
		float a0 = (float)i / N * (float)TAU, a1 = (float)(i + 1) / N * (float)TAU;
		float ca0 = m_cosf(a0), sa0 = m_sinf(a0), ca1 = m_cosf(a1), sa1 = m_sinf(a1);
		for (int j = 0; j < M; j++) {
			float b0 = ((float)j / M + 0.125f) * (float)TAU;
			float b1 = ((float)(j + 1) / M + 0.125f) * (float)TAU;
			float cb0 = m_cosf(b0) * r, sb0 = m_sinf(b0) * r;
			float cb1 = m_cosf(b1) * r, sb1 = m_sinf(b1) * r;
			int v0 = mesh_add_v(m, v3_make((R + cb0) * ca0, (R + cb0) * sa0, sb0));
			int v1 = mesh_add_v(m, v3_make((R + cb0) * ca1, (R + cb0) * sa1, sb0));
			int v2 = mesh_add_v(m, v3_make((R + cb1) * ca1, (R + cb1) * sa1, sb1));
			int v3 = mesh_add_v(m, v3_make((R + cb1) * ca0, (R + cb1) * sa0, sb1));
			mesh_add_quad(m, v0, v1, v2, v3, 0.0f, 0.0f, 1.0f, 0.5f);
		}
	}
	/* Two perpendicular spokes + central octagonal docking hub */
	add_box_part(m, v3_make(0, 0, 0), 0.88f, 0.06f, 0.06f, 1.0f);
	add_box_part(m, v3_make(0, 0, 0), 0.06f, 0.88f, 0.06f, 1.0f);
	add_box_part(m, v3_make(0, 0, 0), 0.26f, 0.26f, 0.34f, 1.0f);
	mesh_calc_normals(m);
}

/* Hostile Sentinel / Pirate Drone: angular twin-wing delta interceptor (+z forward) */
static void gen_drone_mesh(struct mesh *m)
{
	mesh_clear(m);
	int nose  = mesh_add_v(m, v3_make( 0.00f,  0.00f,  1.25f));
	int top   = mesh_add_v(m, v3_make( 0.00f,  0.34f, -0.15f));
	int bot   = mesh_add_v(m, v3_make( 0.00f, -0.26f, -0.15f));
	int rear  = mesh_add_v(m, v3_make( 0.00f,  0.04f, -0.95f));
	int wl    = mesh_add_v(m, v3_make(-1.35f, -0.05f, -0.65f));
	int wr    = mesh_add_v(m, v3_make( 1.35f, -0.05f, -0.65f));
	int wlf   = mesh_add_v(m, v3_make(-0.55f,  0.02f,  0.35f));
	int wrf   = mesh_add_v(m, v3_make( 0.55f,  0.02f,  0.35f));
	int fin   = mesh_add_v(m, v3_make( 0.00f,  0.62f, -0.85f));
	/* Fuselage & swept delta wings (both sides wound outward) */
	mesh_add_tri(m, nose, top, wlf, 0.5f, 0.0f, 0.5f, 0.5f, 0.0f, 0.5f);
	mesh_add_tri(m, nose, wrf, top, 0.5f, 0.0f, 1.0f, 0.5f, 0.5f, 0.5f);
	mesh_add_tri(m, nose, wlf, bot, 0.5f, 0.0f, 0.0f, 0.5f, 0.5f, 0.5f);
	mesh_add_tri(m, nose, bot, wrf, 0.5f, 0.0f, 0.5f, 0.5f, 1.0f, 0.5f);
	mesh_add_tri(m, wlf, top, wl,   0.2f, 0.3f, 0.5f, 0.5f, 0.0f, 1.0f);
	mesh_add_tri(m, wrf, wr, top,   0.8f, 0.3f, 1.0f, 1.0f, 0.5f, 0.5f);
	mesh_add_tri(m, wlf, wl, bot,   0.2f, 0.3f, 0.0f, 1.0f, 0.5f, 0.5f);
	mesh_add_tri(m, wrf, bot, wr,   0.8f, 0.3f, 0.5f, 0.5f, 1.0f, 1.0f);
	mesh_add_tri(m, top, rear, wl,  0.5f, 0.5f, 0.5f, 1.0f, 0.0f, 1.0f);
	mesh_add_tri(m, top, wr, rear,  0.5f, 0.5f, 1.0f, 1.0f, 0.5f, 1.0f);
	mesh_add_tri(m, bot, wl, rear,  0.5f, 0.5f, 0.0f, 1.0f, 0.5f, 1.0f);
	mesh_add_tri(m, bot, rear, wr,  0.5f, 0.5f, 0.5f, 1.0f, 1.0f, 1.0f);
	/* Dorsal stabilizer fin */
	mesh_add_tri(m, top, fin, rear, 0.2f, 0.2f, 0.8f, 0.2f, 0.5f, 0.8f);
	mesh_add_tri(m, top, rear, fin, 0.2f, 0.2f, 0.5f, 0.8f, 0.8f, 0.2f);
	mesh_calc_normals(m);
}

/* Octahedral glowing resource crystal */
static void gen_crystal_mesh(struct mesh *m)
{
	mesh_clear(m);
	int tp = mesh_add_v(m, v3_make(0,  1.35f, 0));
	int bt = mesh_add_v(m, v3_make(0, -1.35f, 0));
	int e0 = mesh_add_v(m, v3_make( 0.75f, 0,  0.00f));
	int e1 = mesh_add_v(m, v3_make( 0.00f, 0,  0.75f));
	int e2 = mesh_add_v(m, v3_make(-0.75f, 0,  0.00f));
	int e3 = mesh_add_v(m, v3_make( 0.00f, 0, -0.75f));
	int eq[5] = {e0, e1, e2, e3, e0};
	for (int i = 0; i < 4; i++) {
		mesh_add_tri(m, tp, eq[i + 1], eq[i], 0.5f, 0.0f, 1.0f, 0.5f, 0.0f, 0.5f);
		mesh_add_tri(m, bt, eq[i], eq[i + 1], 0.5f, 1.0f, 0.0f, 0.5f, 1.0f, 0.5f);
	}
	mesh_calc_normals(m);
}

static void gen_all_meshes(void)
{
	gen_uv_sphere(&meshes[MESH_SPHERE], 12, 18, 0, 1.0f, 1.0f, 1.0f);
	gen_uv_sphere(&meshes[MESH_AST0], 8, 12, 101, 1.05f, 0.92f, 1.00f);
	gen_uv_sphere(&meshes[MESH_AST1], 8, 12, 202, 1.28f, 0.78f, 0.88f);
	gen_uv_sphere(&meshes[MESH_AST2], 8, 12, 303, 0.86f, 1.15f, 0.95f);
	gen_uv_sphere(&meshes[MESH_AST3], 8, 12, 404, 1.12f, 1.04f, 0.76f);
	gen_station_mesh(&meshes[MESH_STATION]);
	gen_drone_mesh(&meshes[MESH_DRONE]);
	gen_crystal_mesh(&meshes[MESH_CRYSTAL]);
}

/* --- .kkrieger-style procedural soft-synth & SFX mixer ---------------------------------------- */

enum {
	SFX_LASER,
	SFX_HIT,
	SFX_BOOM,
	SFX_PICKUP,
	SFX_SHIELD,
	SFX_WARP
};

struct sfx_voice {
	int active, kind;
	float t, dur;
	float phase, freq, freq_end;
};

#define MAX_SFX 8
#define ECHO_LEN 8192

static struct {
	struct sfx_voice v[MAX_SFX];
	uint32_t rng;
	float seq_time;
	int step;
	float pad_ph[3];
	float arp_ph, arp_env, arp_freq;
	float svf_lp, svf_bp;
	float eng_ph, eng_lp;
	float thrust_amt;
	int mood;        /* 0: exploration, 1: combat, 2: warp */
	uint32_t sys_key;
	int16_t echo_l[ECHO_LEN], echo_r[ECHO_LEN];
	int echo_pos;
} syn;

static void synth_trigger(int kind)
{
	int slot = 0;
	float best_t = -1.0f;
	for (int i = 0; i < MAX_SFX; i++) {
		if (!syn.v[i].active) {
			slot = i;
			break;
		}
		if (syn.v[i].t > best_t) {
			best_t = syn.v[i].t;
			slot = i;
		}
	}
	struct sfx_voice *s = &syn.v[slot];
	s->active = 1;
	s->kind = kind;
	s->t = 0.0f;
	s->phase = 0.0f;
	switch (kind) {
	case SFX_LASER:  s->dur = 0.16f; s->freq = 880.0f; s->freq_end = 130.0f; break;
	case SFX_HIT:    s->dur = 0.14f; s->freq = 260.0f; s->freq_end = 55.0f;  break;
	case SFX_BOOM:   s->dur = 0.65f; s->freq = 115.0f; s->freq_end = 24.0f;  break;
	case SFX_PICKUP: s->dur = 0.36f; s->freq = 523.25f; s->freq_end = 1046.5f; break;
	case SFX_SHIELD: s->dur = 0.25f; s->freq = 340.0f; s->freq_end = 180.0f; break;
	case SFX_WARP:   s->dur = 2.40f; s->freq = 75.0f;  s->freq_end = 560.0f; break;
	}
}

/* Approximate MIDI-like pitch frequencies from table of 12 semitones (octave 3 base: C3 = 130.81 Hz) */
static const float note_hz[12] = {
	130.81f, 138.59f, 146.83f, 155.56f, 164.81f, 174.61f,
	185.00f, 196.00f, 207.65f, 220.00f, 233.08f, 246.94f
};

static float midi_freq(int semi)
{
	int oct = 0;
	while (semi >= 12) { semi -= 12; oct++; }
	while (semi < 0)   { semi += 12; oct--; }
	float f = note_hz[semi];
	while (oct > 0) { f *= 2.0f; oct--; }
	while (oct < 0) { f *= 0.5f; oct++; }
	return f;
}

/* -audiotest: the audio signature (e2e/wisp/audiosig.h) instead of the synth, at the backend's rate */
static struct {
	int on, rate;
	uint32_t sig_frames;
	struct audiosig sig;
} atest;

void space_audio_mix(int16_t *stereo_pcm, int frames, int rate)
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
		syn.rng = 0x12345678U;
	float dt = 1.0f / (float)rate;
	static const int scale_calm[8] = {0, 2, 4, 7, 9, 11, 14, 16};
	static const int scale_comb[8] = {0, 1, 3, 5, 7, 8, 10, 12};
	const int *sc = syn.mood == 1 ? scale_comb : scale_calm;
	int root = (int)(syn.sys_key % 7U);

	for (int i = 0; i < frames; i++) {
		/* Sequencer step (eighth notes, faster in combat) */
		float step_len = syn.mood == 1 ? 0.16f : 0.28f;
		syn.seq_time += dt;
		if (syn.seq_time >= step_len || syn.arp_freq <= 0.0f) {
			syn.seq_time = 0.0f;
			syn.step = (syn.step + 1) & 31;
			uint32_t h = hash32((uint32_t)syn.step * 73U ^ syn.sys_key);
			if ((h & 3U) != 0U || syn.mood == 1) {
				int deg = sc[(h >> 3) & 7U];
				syn.arp_freq = midi_freq(root + 12 + deg);
				syn.arp_env = 1.0f;
			}
		}

		/* 3-voice warm detuned sawtooth space pad through 2-pole resonant low-pass filter */
		int chord_shift = ((syn.step >> 3) & 1) ? 5 : 0;
		float pf[3] = {
			midi_freq(root - 12 + chord_shift),
			midi_freq(root + sc[2] + chord_shift) * 1.003f,
			midi_freq(root + sc[4] + chord_shift) * 0.997f
		};
		float pad_raw = 0.0f;
		for (int k = 0; k < 3; k++) {
			syn.pad_ph[k] += pf[k] * dt;
			if (syn.pad_ph[k] >= 1.0f)
				syn.pad_ph[k] -= 1.0f;
			pad_raw += (syn.pad_ph[k] * 2.0f - 1.0f);
		}
		float cutoff = syn.mood == 2 ? 0.26f : (syn.mood == 1 ? 0.18f : 0.09f);
		syn.svf_lp += cutoff * syn.svf_bp;
		float hp = pad_raw * 0.10f - syn.svf_lp - 0.55f * syn.svf_bp;
		syn.svf_bp += cutoff * hp;
		float pad = syn.svf_lp;

		/* Crystalline FM pluck arpeggio */
		syn.arp_ph += syn.arp_freq * dt;
		if (syn.arp_ph >= 1.0f)
			syn.arp_ph -= 1.0f;
		syn.arp_env *= (1.0f - 4.5f * dt);
		if (syn.arp_env < 0.0f)
			syn.arp_env = 0.0f;
		float arp = m_sinf(syn.arp_ph * (float)TAU + 1.4f * syn.arp_env * m_sinf(syn.arp_ph * (float)TAU * 2.0f)) * syn.arp_env * 0.14f;

		/* Engine / afterburner rumble */
		float eng = 0.0f;
		if (syn.thrust_amt > 0.01f) {
			float n = rnd_next(&syn.rng) * 2.0f - 1.0f;
			syn.eng_ph += (48.0f + 42.0f * syn.thrust_amt) * dt;
			if (syn.eng_ph >= 1.0f)
				syn.eng_ph -= 1.0f;
			float raw = (syn.eng_ph * 2.0f - 1.0f) * 0.6f + n * 0.5f;
			syn.eng_lp += 0.08f * (raw - syn.eng_lp);
			eng = syn.eng_lp * syn.thrust_amt * 0.22f;
		}

		/* Polyphonic SFX voices */
		float sfx_l = 0.0f, sfx_r = 0.0f;
		for (int v = 0; v < MAX_SFX; v++) {
			struct sfx_voice *s = &syn.v[v];
			if (!s->active)
				continue;
			s->t += dt;
			if (s->t >= s->dur) {
				s->active = 0;
				continue;
			}
			float p = s->t / s->dur;
			float env = 1.0f - p;
			float f = s->freq + (s->freq_end - s->freq) * p;
			if (s->kind == SFX_PICKUP) {
				f = p < 0.33f ? 523.25f : p < 0.66f ? 659.25f : 1046.5f;
			}
			s->phase += f * dt;
			if (s->phase >= 1.0f)
				s->phase -= 1.0f;
			float sig = 0.0f;
			float nz = rnd_next(&syn.rng) * 2.0f - 1.0f;
			switch (s->kind) {
			case SFX_LASER:
				sig = (m_sinf(s->phase * (float)TAU) * 0.8f + nz * 0.25f) * env * 0.32f;
				break;
			case SFX_HIT:
				sig = (nz * 0.65f + m_sinf(s->phase * (float)TAU) * 0.4f) * env * env * 0.35f;
				break;
			case SFX_BOOM:
				sig = (m_sinf(s->phase * (float)TAU) * 0.7f + nz * 0.7f * env) * env * 0.48f;
				break;
			case SFX_PICKUP:
				sig = m_sinf(s->phase * (float)TAU) * env * 0.28f;
				break;
			case SFX_SHIELD:
				sig = m_sinf(s->phase * (float)TAU) * m_sinf(s->t * 95.0f) * env * 0.34f;
				break;
			case SFX_WARP:
				sig = (m_sinf(s->phase * (float)TAU) + 0.5f * m_sinf(s->phase * (float)TAU * 1.5f) + nz * 0.15f) *
				      m_sinf(p * 3.14159f) * 0.30f;
				break;
			}
			sfx_l += sig * ((v & 1) ? 0.85f : 1.0f);
			sfx_r += sig * ((v & 1) ? 1.0f : 0.85f);
		}

		/* Stereo ping-pong echo on music */
		int ep = syn.echo_pos;
		float el = syn.echo_l[ep] * (1.0f / 32768.0f);
		float er = syn.echo_r[ep] * (1.0f / 32768.0f);
		float ml = pad * 0.9f + arp + er * 0.42f;
		float mr = pad * 1.1f + arp * 0.7f + el * 0.42f;
		syn.echo_l[ep] = (int16_t)clampi((int)(ml * 24000.0f), -30000, 30000);
		syn.echo_r[ep] = (int16_t)clampi((int)(mr * 24000.0f), -30000, 30000);
		syn.echo_pos = (ep + 1) & (ECHO_LEN - 1);

		int out_l = clampi((int)((ml + eng + sfx_l) * 20000.0f), -32760, 32760);
		int out_r = clampi((int)((mr + eng + sfx_r) * 20000.0f), -32760, 32760);
		stereo_pcm[i * 2] = (int16_t)out_l;
		stereo_pcm[i * 2 + 1] = (int16_t)out_r;
	}
}

#endif
