/*
 * Procedural asset generator for wshkeep (.kkrieger-style: zero external data files):
 *   - 7 mipmapped gothic dungeon textures (stone ashlar, flagstones, oak/iron door, caustic
 *     liquid, forged metal/bone mesh detail, flame/rune flare, shadowed pixel HUD font)
 *   - 13 sculpted 3D meshes (4 monsters, 6 dungeon props/pickups, 3 first-person weapons)
 *   - Real-time 16-bit stereo dark-cathedral synth + echo + dungeon combat SFX
 * All math is Pentium-safe x87 float/int.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_KEEP_GEN_H
#define WSH_KEEP_GEN_H

#define PI 3.14159265f
#define TAU 6.28318530f

/* --- Pentium-safe freestanding x87 math (no libm / GLIBC_2.1+ / MSVCRT dependency) --- */
static double k_sin(double x)
{
	int k = (int)(x * (1.0 / 6.28318530717958647692));
	x -= k * 6.28318530717958647692;
	if (x > 3.14159265358979323846)
		x -= 6.28318530717958647692;
	if (x < -3.14159265358979323846)
		x += 6.28318530717958647692;
	double x2 = x * x, r = x, t = x;
	for (int i = 1; i <= 9; i++) {
		t *= -x2 / ((2 * i) * (2 * i + 1));
		r += t;
	}
	return r;
}
static float k_sinf(float x) { return (float)k_sin((double)x); }
static float k_cosf(float x) { return (float)k_sin((double)x + 1.57079632679489661923); }
static float k_fabsf(float x) { return x < 0.0f ? -x : x; }
static int k_abs(int x) { return x < 0 ? -x : x; }
static float k_sqrtf(float x)
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
static float k_atan2f(float y, float x)
{
#if defined(__i386__) || defined(__x86_64__)
	float r;
	__asm__("fpatan" : "=t"(r) : "0"(x), "u"(y) : "st(1)");
	return r;
#else
	if (x == 0.0f && y == 0.0f)
		return 0.0f;
	float ay = k_fabsf(y) + 1e-10f, r, ang;
	if (x >= 0.0f) {
		r = (x - ay) / (x + ay);
		ang = 0.78539816f;
	} else {
		r = (x + ay) / (ay - x);
		ang = 2.35619449f;
	}
	ang += (0.1963f * r * r - 0.9817f) * r;
	return y < 0.0f ? -ang : ang;
#endif
}
#define sinf k_sinf
#define cosf k_cosf
#define sqrtf k_sqrtf
#define fabsf k_fabsf
#define atan2f k_atan2f
#define abs k_abs

static uint32_t rng_s = 0x5753484bU;
static uint32_t rnd(void)
{
	rng_s ^= rng_s << 13;
	rng_s ^= rng_s >> 17;
	rng_s ^= rng_s << 5;
	return rng_s;
}
static float rndf(void)
{
	return (rnd() & 0xffffff) * (1.0f / 16777216.0f);
}

static uint32_t hash2(int x, int y, uint32_t seed)
{
	uint32_t h = (uint32_t)x * 374761393U + (uint32_t)y * 668265263U + seed * 2246822519U;
	h = (h ^ (h >> 13)) * 1274126177U;
	return h ^ (h >> 16);
}

static float vnoise(float x, float y, int period, uint32_t seed)
{
	int ix = (int)(x + 4096.0f) - 4096;
	int iy = (int)(y + 4096.0f) - 4096;
	float fx = x - ix, fy = y - iy;
	fx = fx * fx * (3.0f - 2.0f * fx);
	fy = fy * fy * (3.0f - 2.0f * fy);
	int m = period - 1;
	float a = (hash2(ix & m, iy & m, seed) & 0xffff) * (1.0f / 65535.0f);
	float b = (hash2((ix + 1) & m, iy & m, seed) & 0xffff) * (1.0f / 65535.0f);
	float c = (hash2(ix & m, (iy + 1) & m, seed) & 0xffff) * (1.0f / 65535.0f);
	float d = (hash2((ix + 1) & m, (iy + 1) & m, seed) & 0xffff) * (1.0f / 65535.0f);
	return (a + (b - a) * fx) + ((c + (d - c) * fx) - (a + (b - a) * fx)) * fy;
}

static float fbm_tile(int px, int py, int size, int base_p, int octaves, uint32_t seed)
{
	float sum = 0, amp = 0.5f;
	int p = base_p;
	for (int o = 0; o < octaves; o++) {
		sum += amp * vnoise((float)px * p / size, (float)py * p / size, p, seed + (uint32_t)o * 97U);
		amp *= 0.5f;
		p <<= 1;
	}
	return sum;
}

static uint8_t clamp8(int v)
{
	return (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
}
static uint32_t pack_argb(int a, int r, int g, int b)
{
	return ((uint32_t)clamp8(a) << 24) | ((uint32_t)clamp8(r) << 16) | ((uint32_t)clamp8(g) << 8) | clamp8(b);
}

static uint32_t mipbuf[256 * 256 * 4 / 3 + 16];

static int gen_mipmaps(uint32_t *buf, int size)
{
	int levels = 1;
	uint32_t *src = buf, *dst = buf + size * size;
	for (int s = size; s > 1; s >>= 1) {
		int h = s >> 1;
		for (int y = 0; y < h; y++) {
			for (int x = 0; x < h; x++) {
				uint32_t p0 = src[(y * 2) * s + (x * 2)];
				uint32_t p1 = src[(y * 2) * s + (x * 2 + 1)];
				uint32_t p2 = src[(y * 2 + 1) * s + (x * 2)];
				uint32_t p3 = src[(y * 2 + 1) * s + (x * 2 + 1)];
				uint32_t c = 0;
				for (int sh = 0; sh <= 24; sh += 8) {
					uint32_t avg = (((p0 >> sh) & 0xff) + ((p1 >> sh) & 0xff) +
							((p2 >> sh) & 0xff) + ((p3 >> sh) & 0xff) + 2) >> 2;
					c |= avg << sh;
				}
				dst[y * h + x] = c;
			}
		}
		src = dst;
		dst += h * h;
		levels++;
	}
	return levels;
}

static void build_textures(const struct backend *be)
{
	/* 0: TEX_FONT (128x128 ARGB, 16x8 grid of 8x16 cells with crisp black drop shadow) */
	memset(mipbuf, 0, 128 * 128 * 4);
	for (int ch = 32; ch < 96; ch++) {
		int gx = ((ch - 32) & 15) * 8, gy = ((ch - 32) >> 4) * 16;
		const uint8_t *gl = font_glyph(ch);
		for (int ry = 0; ry < 7; ry++) {
			for (int rx = 0; rx < 5; rx++) {
				if ((gl[ry] >> (4 - rx)) & 1) {
					int px = gx + 1 + rx, py = gy + 2 + ry;
					if (!mipbuf[(py + 1) * 128 + px + 1])
						mipbuf[(py + 1) * 128 + px + 1] = 0xd8000000U;
					mipbuf[py * 128 + px] = 0xffffffffU;
				}
			}
		}
	}
	be->tex_load(TEX_FONT, 128, 1, mipbuf, 1);

	/* 1: TEX_WALL (256x256 mipmapped gothic ashlar stone blocks + carved frieze + moss/soot) */
	for (int y = 0; y < 256; y++) {
		int row = y >> 5; /* 8 courses of 32px stone blocks */
		int ry = y & 31;
		int frieze = (row == 1);
		for (int x = 0; x < 256; x++) {
			float n1 = fbm_tile(x, y, 256, 8, 4, 101);
			float n2 = fbm_tile(x, y, 256, 32, 3, 211);
			int shift = (row & 1) ? 32 : 0;
			int bw = (row == 3 || row == 6) ? 32 : 64;
			int bx = (x + shift + (int)((n1 - 0.5f) * 3.0f)) & (bw - 1);
			int bhash = (int)(hash2((x + shift) / bw, row, 77) & 31) - 16;
			int mortar = (ry < 2 || ry == 31 || bx < 2 || bx == bw - 1);
			int bevel = (!mortar && (ry == 2 || bx == 2)) ? 22 : (!mortar && (ry == 30 || bx == bw - 2)) ? -20 : 0;
			int base = 136 + bhash + (int)((n1 - 0.5f) * 44.0f + (n2 - 0.5f) * 26.0f) + bevel;
			int r = base + 4, g = base + 2, b = base - 2;
			if (frieze && !mortar && ry >= 7 && ry <= 24) {
				int rx2 = (x >> 4) & 15, lx = x & 15;
				int rune = ((lx == 4 || lx == 11) && ry >= 9 && ry <= 22) ||
					   (ry == 9 && lx >= 4 && lx <= 11) ||
					   (ry == 16 && ((rx2 & 1) ? (lx >= 4 && lx <= 9) : (lx >= 6 && lx <= 11)));
				if (rune) {
					r -= 38;
					g -= 30;
					b -= 18;
				} else {
					r += 12;
					g += 10;
					b += 6;
				}
			}
			if (mortar) {
				r = 46 + (int)(n2 * 18.0f);
				g = 48 + (int)(n2 * 22.0f);
				b = 44 + (int)(n2 * 16.0f);
			}
			/* Damp moss near floor & soot near ceiling */
			if (y > 212 && n1 > 0.52f) {
				float m = (y - 212) * (1.0f / 44.0f) * (n1 - 0.45f) * 1.8f;
				r = (int)(r * (1.0f - 0.45f * m) + 34 * m);
				g = (int)(g * (1.0f - 0.20f * m) + 78 * m);
				b = (int)(b * (1.0f - 0.50f * m) + 30 * m);
			}
			if (y < 28) {
				float s = (28 - y) * (1.0f / 28.0f) * 0.42f;
				r = (int)(r * (1.0f - s));
				g = (int)(g * (1.0f - s));
				b = (int)(b * (1.0f - s));
			}
			mipbuf[y * 256 + x] = pack_argb(255, r, g, b);
		}
	}
	be->tex_load(TEX_WALL, 256, gen_mipmaps(mipbuf, 256), mipbuf, 0);

	/* 2: TEX_FLOOR (256x256 mipmapped gothic flagstones & octagonal mosaic) */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float n1 = fbm_tile(x, y, 256, 8, 4, 303);
			float n2 = fbm_tile(x, y, 256, 24, 3, 409);
			int cx = x & 63, cy = y & 63;
			int dx = cx < 32 ? 31 - cx : cx - 32;
			int dy = cy < 32 ? 31 - cy : cy - 32;
			int seam = (cx < 2 || cy < 2 || dx + dy > 46 || dx + dy == 45);
			int diamond = (dx + dy > 46);
			int th = (int)(hash2(x >> 6, y >> 6, diamond ? 911 : 503) & 23) - 11;
			int base = (diamond ? 104 : 132) + th + (int)((n1 - 0.5f) * 38.0f + (n2 - 0.5f) * 24.0f);
			if (!seam && (cx == 2 || cy == 2))
				base += 16;
			int r = base + (diamond ? 10 : 2), g = base, b = base - (diamond ? 6 : -3);
			if (seam) {
				r = 40 + (int)(n2 * 16.0f);
				g = 42 + (int)(n2 * 18.0f);
				b = 44 + (int)(n2 * 16.0f);
			}
			mipbuf[y * 256 + x] = pack_argb(255, r, g, b);
		}
	}
	be->tex_load(TEX_FLOOR, 256, gen_mipmaps(mipbuf, 256), mipbuf, 0);

	/* 3: TEX_DOOR (256x256 mipmapped iron-bound oak planks, rivets & central runic lock) */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float grain = fbm_tile(x * 3, y, 256, 8, 4, 607);
			int plank = x >> 5, px = x & 31;
			int ph = (int)(hash2(plank, 0, 613) & 15) - 8;
			int r = 112 + ph + (int)((grain - 0.5f) * 46.0f);
			int g = 74 + (ph >> 1) + (int)((grain - 0.5f) * 32.0f);
			int b = 44 + (ph >> 2) + (int)((grain - 0.5f) * 20.0f);
			if (px == 0 || px == 31)
				r >>= 1, g >>= 1, b >>= 1;
			/* Iron cross-straps, border frame, and rivets */
			int strap = (y < 14 || y > 241 || x < 12 || x > 243 || (y >= 52 && y <= 68) || (y >= 188 && y <= 204));
			float dx = x - 128.0f, dy = y - 128.0f;
			float d2 = dx * dx + dy * dy;
			int boss = (d2 < 34.0f * 34.0f);
			if (strap || boss) {
				float m = fbm_tile(x, y, 256, 16, 3, 641);
				int ir = 88 + (int)(m * 42.0f);
				r = ir;
				g = ir + 2;
				b = ir + 8;
				int rx = (x - 16) & 31, ry2 = (y - 60);
				if (!boss && ((rx - 8) * (rx - 8) + ry2 * ry2 < 18 ||
					      (rx - 8) * (rx - 8) + (y - 196) * (y - 196) < 18)) {
					r += 48;
					g += 46;
					b += 42;
				}
			}
			/* Glowing golden/arcane seal ring on central boss */
			if (d2 > 16.0f * 16.0f && d2 < 25.0f * 25.0f) {
				r = 225;
				g = 185;
				b = 95;
			} else if (d2 <= 9.0f * 9.0f && (y > 126 || d2 < 36.0f)) {
				r = 24;
				g = 20;
				b = 18;
			}
			mipbuf[y * 256 + x] = pack_argb(255, r, g, b);
		}
	}
	be->tex_load(TEX_DOOR, 256, gen_mipmaps(mipbuf, 256), mipbuf, 0);

	/* 4: TEX_LIQUID (128x128 mipmapped caustic veins, tinted per floor for water/lava/ether) */
	for (int y = 0; y < 128; y++) {
		for (int x = 0; x < 128; x++) {
			float n1 = fbm_tile(x, y, 128, 4, 4, 709);
			float n2 = fbm_tile(x + 37, y + 19, 128, 8, 3, 733);
			float v = n1 - n2;
			if (v < 0)
				v = -v;
			float vein = 1.0f - v * 3.2f;
			if (vein < 0)
				vein = 0;
			int lum = 78 + (int)(n1 * 72.0f + vein * vein * 135.0f);
			mipbuf[y * 128 + x] = pack_argb(255, lum, lum, lum);
		}
	}
	be->tex_load(TEX_LIQUID, 128, gen_mipmaps(mipbuf, 128), mipbuf, 0);

	/* 5: TEX_MESH (256x256 mipmapped hammered steel/bone/armor surface detail) */
	for (int y = 0; y < 256; y++) {
		for (int x = 0; x < 256; x++) {
			float n1 = fbm_tile(x, y, 256, 12, 4, 811);
			float n2 = fbm_tile(x * 2, y, 256, 24, 3, 829);
			int plate = ((x & 63) < 2 || (y & 63) < 2);
			int lum = 152 + (int)((n1 - 0.5f) * 62.0f + (n2 - 0.5f) * 34.0f);
			if (plate)
				lum -= 46;
			else if ((x & 63) == 3 || (y & 63) == 3)
				lum += 26;
			mipbuf[y * 256 + x] = pack_argb(255, lum + 4, lum + 2, lum);
		}
	}
	be->tex_load(TEX_MESH, 256, gen_mipmaps(mipbuf, 256), mipbuf, 0);

	/* 6: TEX_FLARE (64x64 ARGB radial flame/spell corona) */
	for (int y = 0; y < 64; y++) {
		for (int x = 0; x < 64; x++) {
			float dx = (x - 31.5f) * (1.0f / 31.5f);
			float dy = (y - 31.5f) * (1.0f / 31.5f);
			float d = sqrtf(dx * dx + dy * dy);
			float core = d < 1.0f ? (1.0f - d) : 0.0f;
			float a = core * core * (1.35f - 0.35f * core);
			if (a > 1.0f)
				a = 1.0f;
			int c = 200 + (int)(core * 55.0f);
			mipbuf[y * 64 + x] = pack_argb((int)(a * 255.0f), c, c, c);
		}
	}
	be->tex_load(TEX_FLARE, 64, 1, mipbuf, 1);
}

/* --- Procedural 3D Meshes (Monsters, Dungeon Props, Pickups, and First-Person Weapons) --- */
enum {
	MESH_SENTINEL = 0,
	MESH_GARGOYLE = 1,
	MESH_GOLEM = 2,
	MESH_ARCHON = 3,
	MESH_SCONCE = 4,
	MESH_PILLAR = 5,
	MESH_CHEST = 6,
	MESH_KEY = 7,
	MESH_VIAL = 8,
	MESH_PORTAL = 9,
	MESH_WPN_HALBERD = 10,
	MESH_WPN_ROD = 11,
	MESH_WPN_SCEPTER = 12,
	MESH_COUNT = 13,
};

struct mtri {
	float v[3][3];
	float u[3], t[3];
	uint8_t r, g, b, glow;
};

struct mesh_span {
	int first, count;
};

#define MAX_MTRIS 2048
static struct mtri mtris[MAX_MTRIS];
static int n_mtris;
static struct mesh_span meshes[MESH_COUNT];

static void m_tri(const float a[3], const float b[3], const float c[3], uint32_t rgb, int glow)
{
	if (n_mtris >= MAX_MTRIS)
		return;
	float ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
	float vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
	float nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
	float nl = sqrtf(nx * nx + ny * ny + nz * nz);
	float shade = 0.80f;
	if (nl > 1e-6f) {
		nx /= nl, ny /= nl, nz /= nl;
		float d = nx * 0.35f + ny * 0.78f + nz * 0.52f;
		shade = glow ? 1.0f : (0.52f + 0.48f * (d < -0.5f ? -0.5f : d));
	}
	struct mtri *t = &mtris[n_mtris++];
	for (int k = 0; k < 3; k++) {
		const float *p = k == 0 ? a : k == 1 ? b : c;
		t->v[k][0] = p[0], t->v[k][1] = p[1], t->v[k][2] = p[2];
		t->u[k] = (p[0] + p[2]) * 0.18f + 0.5f;
		t->t[k] = p[1] * 0.18f + 0.5f;
	}
	t->r = clamp8((int)(((rgb >> 16) & 0xff) * shade));
	t->g = clamp8((int)(((rgb >> 8) & 0xff) * shade));
	t->b = clamp8((int)((rgb & 0xff) * shade));
	t->glow = (uint8_t)glow;
}

static void m_quad(const float a[3], const float b[3], const float c[3], const float d[3], uint32_t rgb, int glow)
{
	m_tri(a, b, c, rgb, glow);
	m_tri(a, c, d, rgb, glow);
}

static void m_box(float cx, float cy, float cz, float hx, float hy, float hz, uint32_t rgb, int glow)
{
	float p[8][3] = {
		{cx - hx, cy - hy, cz - hz}, {cx + hx, cy - hy, cz - hz},
		{cx + hx, cy + hy, cz - hz}, {cx - hx, cy + hy, cz - hz},
		{cx - hx, cy - hy, cz + hz}, {cx + hx, cy - hy, cz + hz},
		{cx + hx, cy + hy, cz + hz}, {cx - hx, cy + hy, cz + hz},
	};
	static const uint8_t f[6][4] = {
		{4, 5, 6, 7}, {1, 0, 3, 2}, {0, 4, 7, 3},
		{5, 1, 2, 6}, {3, 7, 6, 2}, {0, 1, 5, 4},
	};
	for (int i = 0; i < 6; i++)
		m_quad(p[f[i][0]], p[f[i][1]], p[f[i][2]], p[f[i][3]], rgb, glow);
}

/* Tapered vertical column/frustum along Y */
static void m_column(float cx, float y0, float y1, float cz, float r0, float r1, int sides, uint32_t rgb, int glow)
{
	for (int i = 0; i < sides; i++) {
		float a0 = i * (2.0f * PI / sides), a1 = (i + 1) * (2.0f * PI / sides);
		float c0 = cosf(a0), s0 = sinf(a0), c1 = cosf(a1), s1 = sinf(a1);
		float p0[3] = {cx + c0 * r0, y0, cz + s0 * r0};
		float p1[3] = {cx + c1 * r0, y0, cz + s1 * r0};
		float p2[3] = {cx + c1 * r1, y1, cz + s1 * r1};
		float p3[3] = {cx + c0 * r1, y1, cz + s0 * r1};
		m_quad(p0, p1, p2, p3, rgb, glow);
		if (r1 > 0.02f) {
			float top[3] = {cx, y1, cz};
			m_tri(top, p3, p2, rgb, glow);
		}
	}
}

/* Double-pyramid crystal / gem */
static void m_crystal(float cx, float cy, float cz, float r, float h, int sides, uint32_t rgb, int glow)
{
	float top[3] = {cx, cy + h, cz}, bot[3] = {cx, cy - h, cz};
	for (int i = 0; i < sides; i++) {
		float a0 = i * (2.0f * PI / sides), a1 = (i + 1) * (2.0f * PI / sides);
		float m0[3] = {cx + cosf(a0) * r, cy, cz + sinf(a0) * r};
		float m1[3] = {cx + cosf(a1) * r, cy, cz + sinf(a1) * r};
		m_tri(m0, m1, top, rgb, glow);
		m_tri(m1, m0, bot, rgb, glow);
	}
}

static void build_meshes(void)
{
	n_mtris = 0;

	/* 0: MESH_SENTINEL — Horned Skeletal Warden with shield & broadsword (y = 0..7.2) */
	meshes[MESH_SENTINEL].first = n_mtris;
	m_box(-0.75f, 1.4f, 0.0f, 0.36f, 1.4f, 0.38f, 0x6c727e, 0); /* left greave */
	m_box(0.75f, 1.4f, 0.0f, 0.36f, 1.4f, 0.38f, 0x6c727e, 0);  /* right greave */
	m_box(0.0f, 3.0f, 0.0f, 1.05f, 0.45f, 0.55f, 0x8a2824, 0);  /* crimson tabard belt */
	m_box(0.0f, 4.35f, 0.0f, 1.18f, 1.05f, 0.62f, 0x868c98, 0); /* cuirass */
	m_box(0.0f, 4.45f, 0.66f, 0.65f, 0.68f, 0.08f, 0xc8be9e, 0);/* bone rib-crest */
	m_box(-1.55f, 5.05f, 0.0f, 0.52f, 0.42f, 0.55f, 0x9aa2b0, 0);/* pauldrons */
	m_box(1.55f, 5.05f, 0.0f, 0.52f, 0.42f, 0.55f, 0x9aa2b0, 0);
	m_box(-1.60f, 3.85f, 0.35f, 0.30f, 0.85f, 0.32f, 0xb8af94, 0);/* left arm + kite shield */
	m_box(-1.95f, 3.80f, 0.65f, 0.14f, 1.35f, 0.95f, 0x767e8e, 0);
	m_box(-2.05f, 3.80f, 0.65f, 0.08f, 0.45f, 0.35f, 0xc89a3c, 0);
	m_box(1.60f, 3.85f, 0.45f, 0.30f, 0.85f, 0.32f, 0xb8af94, 0);/* right arm + broadsword */
	m_box(1.65f, 3.35f, 1.05f, 0.48f, 0.12f, 0.16f, 0xc89a3c, 0);
	m_box(1.65f, 4.95f, 1.35f, 0.10f, 1.65f, 0.24f, 0xd8e2f0, 0);
	m_box(0.0f, 6.05f, 0.05f, 0.62f, 0.66f, 0.62f, 0xd4ccb2, 0);/* skull + horned helm */
	m_box(0.0f, 6.45f, 0.0f, 0.68f, 0.36f, 0.68f, 0x626874, 0);
	m_box(-0.24f, 6.05f, 0.69f, 0.14f, 0.09f, 0.05f, 0xff4422, 1);/* glowing eyes */
	m_box(0.24f, 6.05f, 0.69f, 0.14f, 0.09f, 0.05f, 0xff4422, 1);
	m_column(-0.72f, 6.45f, 7.45f, 0.15f, 0.22f, 0.03f, 5, 0xc2b698, 0);
	m_column(0.72f, 6.45f, 7.45f, 0.15f, 0.22f, 0.03f, 5, 0xc2b698, 0);
	meshes[MESH_SENTINEL].count = n_mtris - meshes[MESH_SENTINEL].first;

	/* 1: MESH_GARGOYLE — Winged Stone Stalker (hovering y = 1.6..7.2) */
	meshes[MESH_GARGOYLE].first = n_mtris;
	m_box(0.0f, 4.2f, 0.0f, 1.05f, 1.15f, 0.72f, 0x76706c, 0);
	m_box(-0.68f, 2.4f, 0.2f, 0.32f, 0.85f, 0.34f, 0x645e5a, 0);
	m_box(0.68f, 2.4f, 0.2f, 0.32f, 0.85f, 0.34f, 0x645e5a, 0);
	m_box(-1.35f, 4.1f, 0.55f, 0.34f, 0.80f, 0.34f, 0x7e7872, 0);
	m_box(1.35f, 4.1f, 0.55f, 0.34f, 0.80f, 0.34f, 0x7e7872, 0);
	m_box(0.0f, 5.75f, 0.35f, 0.64f, 0.56f, 0.68f, 0x86807a, 0);
	m_column(-0.55f, 6.15f, 7.25f, 0.1f, 0.20f, 0.03f, 5, 0x524c48, 0);
	m_column(0.55f, 6.15f, 7.25f, 0.1f, 0.20f, 0.03f, 5, 0x524c48, 0);
	m_box(-0.24f, 5.80f, 1.04f, 0.14f, 0.10f, 0.05f, 0xffaa22, 1);
	m_box(0.24f, 5.80f, 1.04f, 0.14f, 0.10f, 0.05f, 0xffaa22, 1);
	{
		/* Swept stone bat-wings (both sides, double-sided) */
		for (int s = -1; s <= 1; s += 2) {
			float sh[3] = {s * 0.9f, 5.0f, -0.35f};
			float el[3] = {s * 2.85f, 6.35f, -0.95f};
			float tp[3] = {s * 3.85f, 4.35f, -1.25f};
			float bt[3] = {s * 1.65f, 3.15f, -0.65f};
			m_quad(sh, el, tp, bt, 0x625a58, 0);
			m_quad(bt, tp, el, sh, 0x564e4c, 0);
		}
	}
	meshes[MESH_GARGOYLE].count = n_mtris - meshes[MESH_GARGOYLE].first;

	/* 2: MESH_GOLEM — Heavy Iron Construct with glowing furnace core (y = 0..8.2) */
	meshes[MESH_GOLEM].first = n_mtris;
	m_box(-1.05f, 1.65f, 0.0f, 0.58f, 1.65f, 0.62f, 0x5c6470, 0);
	m_box(1.05f, 1.65f, 0.0f, 0.58f, 1.65f, 0.62f, 0x5c6470, 0);
	m_box(0.0f, 4.75f, 0.0f, 1.75f, 1.65f, 1.05f, 0x727c8a, 0);
	m_crystal(0.0f, 4.85f, 1.02f, 0.65f, 0.75f, 6, 0xff6a18, 1); /* furnace heart */
	m_box(-2.35f, 5.55f, 0.0f, 0.72f, 0.68f, 0.78f, 0x8490a0, 0);
	m_box(2.35f, 5.55f, 0.0f, 0.72f, 0.68f, 0.78f, 0x8490a0, 0);
	m_box(-2.45f, 3.45f, 0.45f, 0.56f, 1.45f, 0.58f, 0x66707c, 0);
	m_box(2.45f, 3.45f, 0.45f, 0.56f, 1.45f, 0.58f, 0x66707c, 0);
	m_box(0.0f, 7.05f, 0.15f, 0.82f, 0.68f, 0.78f, 0x7e8896, 0);
	m_box(0.0f, 7.10f, 0.94f, 0.54f, 0.14f, 0.05f, 0xff8820, 1); /* visor slit */
	meshes[MESH_GOLEM].count = n_mtris - meshes[MESH_GOLEM].first;

	/* 3: MESH_ARCHON — Sanctum Sovereign Boss (tall crowned armored figure + arcane staff) */
	meshes[MESH_ARCHON].first = n_mtris;
	m_column(0.0f, 0.0f, 4.4f, 0.0f, 1.55f, 0.95f, 8, 0x3e2458, 0); /* armored robe */
	m_box(0.0f, 5.45f, 0.0f, 1.28f, 1.35f, 0.78f, 0x5c3c7e, 0);
	m_crystal(0.0f, 5.55f, 0.80f, 0.46f, 0.62f, 6, 0x48e8ff, 1);
	m_column(-1.85f, 5.4f, 8.2f, -0.15f, 0.52f, 0.06f, 5, 0xd4a640, 0);/* gold shoulder spires */
	m_column(1.85f, 5.4f, 8.2f, -0.15f, 0.52f, 0.06f, 5, 0xd4a640, 0);
	m_box(0.0f, 7.35f, 0.05f, 0.68f, 0.72f, 0.68f, 0x2c2038, 0);
	m_column(0.0f, 7.95f, 9.15f, 0.05f, 0.74f, 0.45f, 6, 0xe8ba48, 0); /* crown */
	m_box(-0.25f, 7.38f, 0.74f, 0.16f, 0.10f, 0.05f, 0x50f4ff, 1);
	m_box(0.25f, 7.38f, 0.74f, 0.16f, 0.10f, 0.05f, 0x50f4ff, 1);
	m_box(1.95f, 4.6f, 0.75f, 0.12f, 3.8f, 0.12f, 0xc89e3c, 0);        /* twin-crystal staff */
	m_crystal(1.95f, 8.7f, 0.75f, 0.48f, 0.78f, 6, 0x58f4ff, 1);
	meshes[MESH_ARCHON].count = n_mtris - meshes[MESH_ARCHON].first;

	/* 4: MESH_SCONCE — Iron wall torch bracket & brazier cup */
	meshes[MESH_SCONCE].first = n_mtris;
	m_box(0.0f, 0.0f, -0.55f, 0.28f, 0.65f, 0.10f, 0x4e525a, 0);
	m_box(0.0f, -0.15f, -0.15f, 0.10f, 0.10f, 0.42f, 0x5a5e68, 0);
	m_column(0.0f, -0.65f, 0.55f, 0.22f, 0.12f, 0.38f, 6, 0x62584c, 0);
	m_crystal(0.0f, 0.68f, 0.22f, 0.28f, 0.34f, 6, 0xff9828, 1);
	meshes[MESH_SCONCE].count = n_mtris - meshes[MESH_SCONCE].first;

	/* 5: MESH_PILLAR — Octagonal gothic stone column (normalized y = 0..1, scaled to ceiling) */
	meshes[MESH_PILLAR].first = n_mtris;
	m_box(0.0f, 0.06f, 0.0f, 2.15f, 0.06f, 2.15f, 0x8e8c88, 0);
	m_column(0.0f, 0.12f, 0.88f, 0.0f, 1.65f, 1.55f, 8, 0xa2a09a, 0);
	m_box(0.0f, 0.94f, 0.0f, 2.20f, 0.06f, 2.20f, 0x8e8c88, 0);
	meshes[MESH_PILLAR].count = n_mtris - meshes[MESH_PILLAR].first;

	/* 6: MESH_CHEST — Gold-clasped reliquary treasure chest */
	meshes[MESH_CHEST].first = n_mtris;
	m_box(0.0f, 0.95f, 0.0f, 1.65f, 0.95f, 1.15f, 0x7c4c28, 0);
	m_box(0.0f, 2.15f, 0.0f, 1.72f, 0.38f, 1.22f, 0x925a30, 0);
	m_box(-1.10f, 1.25f, 0.0f, 0.18f, 1.32f, 1.26f, 0xc89c38, 0);
	m_box(1.10f, 1.25f, 0.0f, 0.18f, 1.32f, 1.26f, 0xc89c38, 0);
	m_box(0.0f, 1.65f, 1.24f, 0.34f, 0.42f, 0.12f, 0xf4cc50, 1);
	meshes[MESH_CHEST].count = n_mtris - meshes[MESH_CHEST].first;

	/* 7: MESH_KEY — Floating Golden Runic Key */
	meshes[MESH_KEY].first = n_mtris;
	m_box(0.0f, 2.8f, 0.0f, 0.72f, 0.72f, 0.18f, 0xffd248, 1);
	m_box(0.0f, 1.15f, 0.0f, 0.18f, 1.15f, 0.16f, 0xf2be38, 1);
	m_box(0.45f, 0.42f, 0.0f, 0.36f, 0.18f, 0.16f, 0xffd248, 1);
	m_box(0.38f, 0.88f, 0.0f, 0.28f, 0.14f, 0.16f, 0xffd248, 1);
	meshes[MESH_KEY].count = n_mtris - meshes[MESH_KEY].first;

	/* 8: MESH_VIAL — Faceted vitality/mana crystal prism */
	meshes[MESH_VIAL].first = n_mtris;
	m_crystal(0.0f, 1.6f, 0.0f, 0.85f, 1.45f, 6, 0xe8f4ff, 1);
	m_box(0.0f, 1.6f, 0.0f, 0.95f, 0.16f, 0.95f, 0xc8a448, 0);
	meshes[MESH_VIAL].count = n_mtris - meshes[MESH_VIAL].first;

	/* 9: MESH_PORTAL — Twin carved runic obelisks & gothic arch */
	meshes[MESH_PORTAL].first = n_mtris;
	m_column(-3.4f, 0.0f, 9.2f, 0.0f, 0.95f, 0.72f, 6, 0x747888, 0);
	m_column(3.4f, 0.0f, 9.2f, 0.0f, 0.95f, 0.72f, 6, 0x747888, 0);
	m_box(0.0f, 9.6f, 0.0f, 4.4f, 0.65f, 0.95f, 0x84889a, 0);
	m_crystal(0.0f, 10.6f, 0.0f, 0.75f, 0.95f, 6, 0x60e8ff, 1);
	meshes[MESH_PORTAL].count = n_mtris - meshes[MESH_PORTAL].first;

	/* 10: MESH_WPN_HALBERD — First-person Iron Halberd (local view-space weapon coords) */
	meshes[MESH_WPN_HALBERD].first = n_mtris;
	m_box(0.0f, -0.35f, 0.0f, 0.065f, 1.85f, 0.065f, 0x7a4e2c, 0); /* ash shaft */
	m_box(0.0f, 0.85f, 0.0f, 0.11f, 0.18f, 0.11f, 0xb8943c, 0);   /* brass collar */
	m_column(0.0f, 1.02f, 2.05f, 0.0f, 0.12f, 0.015f, 4, 0xd8e2ee, 0); /* spear tip */
	{
		/* Crescent axe blade + rear spike */
		float a0[3] = {-0.05f, 0.72f, 0.0f}, a1[3] = {-0.78f, 1.25f, 0.12f};
		float a2[3] = {-0.72f, 0.35f, 0.10f}, a3[3] = {-0.05f, 0.45f, 0.0f};
		float b0[3] = {0.05f, 0.82f, 0.0f}, b1[3] = {0.48f, 0.68f, -0.04f}, b2[3] = {0.05f, 0.56f, 0.0f};
		m_quad(a0, a1, a2, a3, 0xdce6f2, 0);
		m_quad(a3, a2, a1, a0, 0xc2ccd8, 0);
		m_tri(b0, b1, b2, 0xc8d2de, 0);
		m_tri(b2, b1, b0, 0xc8d2de, 0);
	}
	meshes[MESH_WPN_HALBERD].count = n_mtris - meshes[MESH_WPN_HALBERD].first;

	/* 11: MESH_WPN_ROD — First-person Ember Rod with glowing fire-ruby */
	meshes[MESH_WPN_ROD].first = n_mtris;
	m_column(0.0f, -1.6f, 0.85f, 0.0f, 0.085f, 0.070f, 6, 0x5c3e2a, 0);
	m_box(0.0f, 0.88f, 0.0f, 0.18f, 0.10f, 0.18f, 0xc88e34, 0);
	m_box(-0.20f, 1.18f, 0.0f, 0.05f, 0.32f, 0.05f, 0x625a54, 0);
	m_box(0.20f, 1.18f, 0.0f, 0.05f, 0.32f, 0.05f, 0x625a54, 0);
	m_box(0.0f, 1.18f, -0.20f, 0.05f, 0.32f, 0.05f, 0x625a54, 0);
	m_crystal(0.0f, 1.25f, 0.0f, 0.24f, 0.38f, 6, 0xff7820, 1);
	meshes[MESH_WPN_ROD].count = n_mtris - meshes[MESH_WPN_ROD].first;

	/* 12: MESH_WPN_SCEPTER — First-person Storm Scepter with twin wings & cyan crystal */
	meshes[MESH_WPN_SCEPTER].first = n_mtris;
	m_column(0.0f, -1.6f, 0.82f, 0.0f, 0.080f, 0.075f, 6, 0x8898b2, 0);
	m_box(0.0f, 0.86f, 0.0f, 0.24f, 0.10f, 0.14f, 0xd8b44c, 0);
	m_box(-0.32f, 1.22f, 0.0f, 0.08f, 0.42f, 0.06f, 0xc8d8ee, 0);
	m_box(0.32f, 1.22f, 0.0f, 0.08f, 0.42f, 0.06f, 0xc8d8ee, 0);
	m_crystal(0.0f, 1.28f, 0.0f, 0.28f, 0.46f, 6, 0x48f0ff, 1);
	meshes[MESH_WPN_SCEPTER].count = n_mtris - meshes[MESH_WPN_SCEPTER].first;
}

/* --- Procedural Dark-Cathedral Soundtrack + Stereo Echo + Dungeon SFX --- */
enum {
	SFX_STEP = 0,
	SFX_SWING = 1,
	SFX_FIREBOLT = 2,
	SFX_SCEPTER = 3,
	SFX_DOOR = 4,
	SFX_PICKUP = 5,
	SFX_MON_HIT = 6,
	SFX_HURT = 7,
};

static struct {
	volatile float danger; /* 0..1 monster proximity intensity */
	volatile int sfx_type;
	volatile float sfx_t;
	uint32_t step, tick_rem, lfsr;
	uint32_t ph_org1, ph_org2, ph_arp, ph_drum, ph_sfx;
	float env_arp, env_drum;
	int16_t echo_l[4096], echo_r[4096];
	int echo_pos;
} snd = {0.0f, -1, 0.0f, 0, 0, 0x9e3779b9U, 0, 0, 0, 0, 0, 0, 0, {0}, {0}, 0};

static void keep_sfx(int type)
{
	snd.sfx_type = type;
	snd.sfx_t = 0.001f;
	snd.ph_sfx = 0;
}

static uint32_t hz_inc(float hz, int rate)
{
	return (uint32_t)(hz * (65536.0f * 65536.0f / (float)rate));
}

static int32_t tri_wave(uint32_t ph)
{
	int32_t x = (int32_t)(ph >> 16);
	return x < 32768 ? (x * 2 - 32768) : (98304 - x * 2);
}

static struct {
	int on, rate;
	uint32_t sig_frames;
	struct audiosig sig;
} atest;

void keep_audio_mix(int16_t *stereo_pcm, int frames, int rate)
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
	/* D harmonic minor / Phrygian gothic progression */
	static const float root_hz[4] = {73.42f, 65.41f, 58.27f, 69.30f}; /* D2, C2, Bb1, C#2 */
	static const float arp_hz[16] = {
		293.66f, 349.23f, 440.00f, 587.33f, 523.25f, 440.00f, 349.23f, 329.63f,
		261.63f, 329.63f, 392.00f, 523.25f, 466.16f, 440.00f, 349.23f, 277.18f,
	};
	uint32_t sp_step = (uint32_t)(rate * 19 / 100); /* ~190ms eighth-note cathedral pulse */
	float danger = snd.danger;
	float dt = 1.0f / (float)rate;

	for (int i = 0; i < frames; i++) {
		if (snd.tick_rem == 0) {
			snd.tick_rem = sp_step;
			snd.step++;
			snd.env_arp = 1.0f;
			if ((snd.step & 3) == 0 || (danger > 0.35f && (snd.step & 1) == 0)) {
				snd.env_drum = 0.55f + 0.45f * danger;
				snd.ph_drum = 0;
			}
		}
		snd.tick_rem--;

		int bar = (snd.step >> 3) & 3;
		float root = root_hz[bar];
		snd.ph_org1 += hz_inc(root, rate);
		snd.ph_org2 += hz_inc(root * 1.502f, rate); /* fifth + slight chorus detune */
		snd.ph_arp += hz_inc(arp_hz[snd.step & 15], rate);

		snd.lfsr = (snd.lfsr >> 1) ^ (-(int32_t)(snd.lfsr & 1U) & 0xd0000001U);
		int32_t noise = (int32_t)(int16_t)(snd.lfsr & 0xffff);

		/* Pipe-organ drone (fundamental + octave + fifth) */
		int32_t org = (tri_wave(snd.ph_org1) >> 1) + (tri_wave(snd.ph_org1 << 1) >> 2) + (tri_wave(snd.ph_org2) >> 2);
		org = (org * 18) >> 6;

		/* Plucked minor arpeggio */
		int32_t saw = (int32_t)(snd.ph_arp >> 16) - 32768;
		int32_t arp = (int32_t)(saw * snd.env_arp * 0.16f);
		snd.env_arp *= 0.99935f;

		/* Subterranean war-drum */
		float dfreq = 48.0f + 78.0f * snd.env_drum * snd.env_drum;
		snd.ph_drum += hz_inc(dfreq, rate);
		int32_t drum = (int32_t)(tri_wave(snd.ph_drum) * snd.env_drum * 0.28f);
		snd.env_drum *= 0.9989f;

		/* One-shot dungeon SFX */
		int32_t sfx = 0;
		int st = snd.sfx_type;
		if (st >= 0) {
			float t = snd.sfx_t;
			snd.sfx_t = t + dt;
			if (st == SFX_STEP) {
				if (t < 0.08f) {
					snd.ph_sfx += hz_inc(95.0f - t * 500.0f, rate);
					sfx = (int32_t)((tri_wave(snd.ph_sfx) * 0.4f + noise * 0.35f) * (1.0f - t * 12.5f) * 0.28f);
				} else
					snd.sfx_type = -1;
			} else if (st == SFX_SWING) {
				if (t < 0.18f) {
					snd.ph_sfx += hz_inc(420.0f - t * 1400.0f, rate);
					sfx = (int32_t)((noise * 0.6f + tri_wave(snd.ph_sfx) * 0.4f) * (1.0f - t * 5.5f) * 0.42f);
				} else
					snd.sfx_type = -1;
			} else if (st == SFX_FIREBOLT) {
				if (t < 0.24f) {
					snd.ph_sfx += hz_inc(540.0f - t * 1650.0f, rate);
					sfx = (int32_t)((tri_wave(snd.ph_sfx) * 0.65f + noise * 0.45f) * (1.0f - t * 4.1f) * 0.48f);
				} else
					snd.sfx_type = -1;
			} else if (st == SFX_SCEPTER) {
				if (t < 0.32f) {
					snd.ph_sfx += hz_inc(880.0f - t * 1800.0f + ((int)(t * 90.0f) & 1) * 220.0f, rate);
					sfx = (int32_t)((tri_wave(snd.ph_sfx) * 0.7f + noise * 0.35f) * (1.0f - t * 3.1f) * 0.52f);
				} else
					snd.sfx_type = -1;
			} else if (st == SFX_DOOR) {
				if (t < 0.42f) {
					snd.ph_sfx += hz_inc(78.0f + (int)(t * 40.0f) * 3.0f, rate);
					sfx = (int32_t)((tri_wave(snd.ph_sfx) * 0.55f + noise * 0.35f) * (1.0f - t * 2.3f) * 0.40f);
				} else
					snd.sfx_type = -1;
			} else if (st == SFX_PICKUP) {
				if (t < 0.30f) {
					float f = t < 0.10f ? 587.33f : t < 0.20f ? 880.0f : 1174.66f;
					snd.ph_sfx += hz_inc(f, rate);
					sfx = (int32_t)(tri_wave(snd.ph_sfx) * (1.0f - t * 3.2f) * 0.46f);
				} else
					snd.sfx_type = -1;
			} else if (st == SFX_MON_HIT || st == SFX_HURT) {
				if (t < 0.22f) {
					float f = (st == SFX_HURT ? 150.0f : 210.0f) - t * 480.0f;
					snd.ph_sfx += hz_inc(f < 45.0f ? 45.0f : f, rate);
					sfx = (int32_t)((tri_wave(snd.ph_sfx) * 0.6f + noise * 0.5f) * (1.0f - t * 4.5f) * 0.52f);
				} else
					snd.sfx_type = -1;
			} else {
				snd.sfx_type = -1;
			}
		}

		/* Stereo cathedral echo cross-feed */
		int ep = snd.echo_pos;
		int32_t el = snd.echo_l[ep], er = snd.echo_r[ep];
		int32_t dry_l = org + drum + sfx + ((snd.step & 1) ? arp : (arp >> 1));
		int32_t dry_r = org + drum + sfx + ((snd.step & 1) ? (arp >> 1) : arp);
		int32_t out_l = dry_l + (er >> 2);
		int32_t out_r = dry_r + (el >> 2);
		snd.echo_l[ep] = (int16_t)(out_l < -32000 ? -32000 : out_l > 32000 ? 32000 : out_l);
		snd.echo_r[ep] = (int16_t)(out_r < -32000 ? -32000 : out_r > 32000 ? 32000 : out_r);
		snd.echo_pos = (ep + 1) & 4095;

		stereo_pcm[i * 2] = snd.echo_l[ep];
		stereo_pcm[i * 2 + 1] = snd.echo_r[ep];
	}
}

#endif
