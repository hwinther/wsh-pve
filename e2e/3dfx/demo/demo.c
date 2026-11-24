/*
 * wshdemo's core: the parts, the textures, the font, the main loop and the test modes, without a C
 * library (see demo.h). Every part draws through struct backend, so one frame looks the same in
 * Glide 2, Glide 3 and OpenGL.
 *
 *   title    a title card: the API, what it says its version is, the wrapper's build string and
 *            the resolution (interactive runs only)
 *   cube     a spinning, lit cube with a mipmapped checkerboard (bilinear), in front of a wall that
 *            is drawn after it: the depth buffer keeps the cube
 *   tunnel   a textured tunnel with linear fog, stars (additive) and a translucent square (alpha
 *            blending) in the middle
 *   plasma   a plasma computed into a 256x256 texture and uploaded every frame (the FIFO's data
 *            path), drawn over the screen as a 2D quad, with copper bars (additive)
 *
 * Test modes: -bench N draws each part N frames without vsync and prints its frame rate; -check
 * draws a fixed frame of each part (time 0, no animation), reads it back and compares a few probe
 * pixels, chosen in flat areas, with the colours the part meant to draw (within TOLERANCE per
 * channel, as packages/wsh-openglide/tests/scene.h); -hold S keeps the last frame up for S seconds,
 * after printing its probes ("PROBE x y rrggbb") and "FRAME" for a host that checks the console.
 * Output lines all start with the tag ("WSHDEMO: ", -tag). Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdarg.h>
#include <stddef.h>

#include "demo.h"
#include "font.h"

void *memset(void *d, int c, size_t n);
void *memcpy(void *d, const void *s, size_t n);

#define TOLERANCE 24
#define PI 3.14159265358979
#define MAXV 3000

struct view demo_view;
static const struct backend *be;
static const char *tag = "WSHDEMO";

/* --- maths without libm ----------------------------------------------------------------------- */

static double m_sin(double x)
{
	double n = x * (1.0 / (2 * PI));
	long i = (long)(n >= 0 ? n + 0.5 : n - 0.5);
	x -= (double)i * 2 * PI; /* -pi..pi */
	if (x > PI / 2)
		x = PI - x;
	else if (x < -PI / 2)
		x = -PI - x;
	double x2 = x * x;
	return x * (1 + x2 * (-1.0 / 6 + x2 * (1.0 / 120 + x2 * (-1.0 / 5040 + x2 * (1.0 / 362880 - x2 / 39916800.0)))));
}
static double m_cos(double x)
{
	return m_sin(x + PI / 2);
}
static double m_sqrt(double x)
{
	double r;
	__asm__("fsqrt" : "=t"(r) : "0"(x));
	return r;
}
static int m_round(double x)
{
	return (int)(x >= 0 ? x + 0.5 : x - 0.5);
}
static int clampi(int v, int lo, int hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

/* --- formatting ------------------------------------------------------------------------------- */

static int fmt_v(char *buf, int n, const char *f, va_list ap)
{
	int o = 0;
#define PUT(c)                       \
	do {                         \
		if (o < n - 1)       \
			buf[o] = (c); \
		o++;                 \
	} while (0)
	for (; *f; f++) {
		if (*f != '%') {
			PUT(*f);
			continue;
		}
		f++;
		int zero = 0, width = 0, prec = -1;
		if (*f == '0')
			zero = 1, f++;
		while (*f >= '0' && *f <= '9')
			width = width * 10 + (*f++ - '0');
		if (*f == '.') {
			prec = 0;
			for (f++; *f >= '0' && *f <= '9'; f++)
				prec = prec * 10 + (*f - '0');
		}
		char tmp[40];
		int len = 0, neg = 0;
		const char *s = tmp;
		switch (*f) {
		case 's':
			s = va_arg(ap, const char *);
			if (!s)
				s = "(null)";
			while (s[len] && (prec < 0 || len < prec))
				len++;
			break;
		case 'c':
			tmp[0] = (char)va_arg(ap, int);
			len = 1;
			break;
		case 'd':
		case 'u':
		case 'x': {
			uint32_t v;
			if (*f == 'd') {
				int32_t d = va_arg(ap, int32_t);
				neg = d < 0;
				v = neg ? (uint32_t)-d : (uint32_t)d;
			} else {
				v = va_arg(ap, uint32_t);
			}
			uint32_t base = *f == 'x' ? 16 : 10;
			char r[12];
			int k = 0;
			do {
				r[k++] = "0123456789abcdef"[v % base];
				v /= base;
			} while (v);
			if (neg)
				tmp[len++] = '-';
			while (len + k < width && zero)
				tmp[len++] = '0';
			while (k)
				tmp[len++] = r[--k];
			break;
		}
		case 'f': {
			double d = va_arg(ap, double);
			if (prec < 0)
				prec = 2;
			if (d < 0)
				tmp[len++] = '-', d = -d;
			double scale = 1;
			for (int i = 0; i < prec; i++)
				scale *= 10;
			if (d > 4e9 / scale)
				d = 4e9 / scale;
			uint32_t whole = (uint32_t)(d * scale + 0.5);
			uint32_t ip = (uint32_t)(whole / (uint32_t)scale), fp = whole % (uint32_t)scale;
			char r[12];
			int k = 0;
			do {
				r[k++] = (char)('0' + ip % 10);
				ip /= 10;
			} while (ip);
			while (k)
				tmp[len++] = r[--k];
			if (prec) {
				tmp[len++] = '.';
				for (int i = prec - 1; i >= 0; i--) {
					uint32_t div = 1;
					for (int j = 0; j < i; j++)
						div *= 10;
					tmp[len++] = (char)('0' + (fp / div) % 10);
				}
			}
			break;
		}
		case '%':
			tmp[0] = '%';
			len = 1;
			break;
		default:
			tmp[0] = '?';
			len = 1;
		}
		for (int i = len; i < width && !zero; i++)
			PUT(' ');
		for (int i = 0; i < len; i++)
			PUT(s[i]);
	}
	if (n > 0)
		buf[o < n ? o : n - 1] = 0;
	return o;
#undef PUT
}

int demo_fmt(char *buf, int n, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int r = fmt_v(buf, n, fmt, ap);
	va_end(ap);
	return r;
}

void demo_log(const char *fmt, ...)
{
	char line[512];
	int o = demo_fmt(line, sizeof(line), "%s: ", tag);
	va_list ap;
	va_start(ap, fmt);
	fmt_v(line + o, (int)sizeof(line) - o, fmt, ap);
	va_end(ap);
	plat_out(line);
}

static int str_eq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static int to_int(const char *s)
{
	int v = 0;
	while (*s >= '0' && *s <= '9')
		v = v * 10 + (*s++ - '0');
	return v;
}

/* --- qemu-3dfx's build string ------------------------------------------------------------------ */

static int is_hex(uint8_t c)
{
	return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
}
static int is_dig(uint8_t c)
{
	return c >= '0' && c <= '9';
}

/* "1234abc-12:34:56 Nov 24 2026 build" (szgrdata.h: __REV__ __TIME__ " " __DATE__ " build ") */
int demo_find_buildstr(const uint8_t *b, uint32_t len, char *out, int n)
{
	for (uint32_t p = 28; p + 6 <= len; p++) {
		if (b[p] != ' ' || b[p + 1] != 'b' || b[p + 2] != 'u' || b[p + 3] != 'i' || b[p + 4] != 'l' || b[p + 5] != 'd')
			continue;
		const uint8_t *s = b + p - 28;
		int ok = s[7] == '-' && s[10] == ':' && s[13] == ':' && s[16] == ' ' && s[20] == ' ' && s[23] == ' ';
		for (int i = 0; ok && i < 7; i++)
			ok = is_hex(s[i]);
		ok = ok && is_dig(s[8]) && is_dig(s[9]) && is_dig(s[24]) && is_dig(s[27]) && is_dig(s[22]);
		if (!ok)
			continue;
		/* "<rev> (built <date> <time>)" */
		char rev[8], date[12], tm[9];
		memcpy(rev, s, 7), rev[7] = 0;
		memcpy(date, s + 17, 11), date[11] = 0;
		memcpy(tm, s + 8, 8), tm[8] = 0;
		demo_fmt(out, n, "%s (built %s %s)", rev, date, tm);
		return 1;
	}
	return 0;
}

/* --- textures --------------------------------------------------------------------------------- */

#define MIPSIZE(s) ((s) * (s) * 4 / 3 + 1)
static uint32_t tex_cube[MIPSIZE(256)], tex_tunnel[MIPSIZE(256)], tex_plasma[256 * 256], tex_font[128 * 128];

static uint32_t argb(int a, int r, int g, int b)
{
	return ((uint32_t)clampi(a, 0, 255) << 24) | ((uint32_t)clampi(r, 0, 255) << 16) | ((uint32_t)clampi(g, 0, 255) << 8) |
	       (uint32_t)clampi(b, 0, 255);
}
static uint32_t hash(uint32_t x)
{
	x ^= x >> 16;
	x *= 0x7feb352dU;
	x ^= x >> 15;
	x *= 0x846ca68bU;
	x ^= x >> 16;
	return x;
}

/* The mipmap levels after level 0 (size x size): 2x2 averages, down to 1x1; returns the levels */
static int make_mips(uint32_t *t, int size)
{
	int levels = 1;
	uint32_t *src = t;
	for (int s = size / 2; s >= 1; s /= 2, levels++) {
		uint32_t *dst = src + s * 2 * s * 2;
		for (int y = 0; y < s; y++)
			for (int x = 0; x < s; x++) {
				uint32_t c[4] = {src[(2 * y) * 2 * s + 2 * x], src[(2 * y) * 2 * s + 2 * x + 1],
						 src[(2 * y + 1) * 2 * s + 2 * x], src[(2 * y + 1) * 2 * s + 2 * x + 1]};
				uint32_t o = 0;
				for (int sh = 0; sh < 32; sh += 8) {
					uint32_t sum = 2;
					for (int i = 0; i < 4; i++)
						sum += (c[i] >> sh) & 0xff;
					o |= (sum / 4) << sh;
				}
				dst[y * s + x] = o;
			}
		src = dst;
	}
	return levels;
}

/* The cube's checkerboard: 8x8 cells of 32 texels, orange and blue, in a dark frame */
static const int CUBE_A[3] = {255, 160, 64}, CUBE_B[3] = {48, 96, 200};
static int cube_levels;
static void gen_cube(void)
{
	for (int y = 0; y < 256; y++)
		for (int x = 0; x < 256; x++) {
			const int *c = (((x >> 5) + (y >> 5)) & 1) ? CUBE_B : CUBE_A;
			int frame = x < 6 || y < 6 || x > 249 || y > 249;
			tex_cube[y * 256 + x] = frame ? argb(255, 30, 30, 40) : argb(255, c[0], c[1], c[2]);
		}
	cube_levels = make_mips(tex_cube, 256);
}

/* The tunnel's wall: bricks of 32x16 texels with mortar and a little noise */
static int tunnel_levels;
static void gen_tunnel(void)
{
	for (int y = 0; y < 256; y++)
		for (int x = 0; x < 256; x++) {
			int row = y >> 4, bx = (x + (row & 1) * 16) & 255, col = bx >> 5;
			int mortar = (y & 15) < 2 || (bx & 31) < 2;
			uint32_t h = hash((uint32_t)(row * 64 + col));
			int n = (int)(hash((uint32_t)(y * 256 + x) ^ 0x5bd1e995U) & 31) - 16;
			if (mortar)
				tex_tunnel[y * 256 + x] = argb(255, 60 + n / 2, 56 + n / 2, 70 + n / 2);
			else
				tex_tunnel[y * 256 + x] = argb(255, 150 + (int)(h & 63) + n, 80 + (int)((h >> 8) & 31) + n,
							       60 + (int)((h >> 16) & 31) + n);
		}
	tunnel_levels = make_mips(tex_tunnel, 256);
}

/* The font: 16x6 cells of 8x8 texels for ASCII 32..127, white, the glyph in the alpha */
static void gen_font(void)
{
	memset(tex_font, 0, sizeof(tex_font));
	for (int c = FONT_FIRST; c <= FONT_LAST; c++) {
		const uint8_t *g = font_glyph(c);
		int cx = ((c - 32) & 15) * 8, cy = ((c - 32) >> 4) * 8;
		for (int y = 0; y < 7; y++)
			for (int x = 0; x < 5; x++)
				if (g[y] & (0x10 >> x))
					tex_font[(cy + y) * 128 + cx + x] = 0xffffffffU;
	}
}

/* The plasma: four sine waves (one radial) through a palette that moves with time */
static uint8_t sin64[256], radial[256 * 256];
static uint32_t pal_base[256];
static void gen_plasma_tables(void)
{
	for (int i = 0; i < 256; i++) {
		sin64[i] = (uint8_t)m_round(31.5 + 31.5 * m_sin(i * 2 * PI / 256));
		double a = i * 2 * PI / 256;
		pal_base[i] = argb(255, m_round(128 + 127 * m_sin(a)), m_round(128 + 127 * m_sin(a + 2 * PI / 3)),
				   m_round(128 + 127 * m_sin(a + 4 * PI / 3)));
	}
	for (int y = 0; y < 256; y++)
		for (int x = 0; x < 256; x++)
			radial[y * 256 + x] = (uint8_t)m_round(m_sqrt((double)((x - 128) * (x - 128) + (y - 96) * (y - 96))) * 1.5);
}
static void gen_plasma(double t)
{
	int t1 = m_round(t * 30), t2 = m_round(-t * 22), t3 = m_round(t * 17), t4 = m_round(-t * 45), shift = m_round(t * 40);
	for (int y = 0; y < 256; y++) {
		uint32_t *row = tex_plasma + y * 256;
		int sy = sin64[(y + t2) & 255];
		const uint8_t *rad = radial + y * 256;
		for (int x = 0; x < 256; x++) {
			int v = sin64[(x + t1) & 255] + sy + sin64[((x + y) / 2 + t3) & 255] + sin64[(rad[x] + t4) & 255];
			row[x] = pal_base[(v + shift) & 255];
		}
	}
}

static void upload_textures(void)
{
	be->tex_load(TEX_CUBE, 256, cube_levels, tex_cube, 0);
	be->tex_load(TEX_TUNNEL, 256, tunnel_levels, tex_tunnel, 0);
	be->tex_load(TEX_PLASMA, 256, 1, tex_plasma, 0);
	be->tex_load(TEX_FONT, 128, 1, tex_font, 1);
}

/* --- drawing helpers -------------------------------------------------------------------------- */

static struct dvtx vb[MAXV];
static int vn;
static void flush(void)
{
	if (vn)
		be->tris(vb, vn);
	vn = 0;
}
static void state(int tex, int blend, int depth, int fog, int filter, int clamp, int mode2d)
{
	struct rstate s = {tex, blend, depth, fog, filter, clamp, mode2d};
	flush();
	be->state(&s);
}
static void tri(const struct dvtx *a, const struct dvtx *b, const struct dvtx *c)
{
	if (vn + 3 > MAXV)
		flush();
	vb[vn++] = *a;
	vb[vn++] = *b;
	vb[vn++] = *c;
}
static void quad(const struct dvtx *a, const struct dvtx *b, const struct dvtx *c, const struct dvtx *d)
{
	tri(a, b, c);
	tri(a, c, d);
}
static struct dvtx v2(float x, float y, uint32_t c, float s, float t)
{
	struct dvtx v;
	memset(&v, 0, sizeof(v));
	v.x = x, v.y = y, v.oow = 1;
	v.vz = 1;
	v.r = (float)((c >> 16) & 0xff), v.g = (float)((c >> 8) & 0xff), v.b = (float)(c & 0xff), v.a = (float)(c >> 24);
	v.s = s, v.t = t;
	return v;
}
/* A view-space point, projected */
static struct dvtx v3(double x, double y, double z, double r, double g, double b, double a, double s, double t)
{
	struct dvtx v;
	v.vx = (float)x, v.vy = (float)y, v.vz = (float)z;
	v.oow = (float)(1 / z);
	v.x = (float)(demo_view.w * 0.5 + x * demo_view.f / z);
	v.y = (float)(demo_view.h * 0.5 - y * demo_view.f / z);
	v.r = (float)r, v.g = (float)g, v.b = (float)b, v.a = (float)a;
	v.s = (float)s, v.t = (float)t;
	return v;
}
static void rect(float x0, float y0, float x1, float y1, uint32_t c)
{
	struct dvtx a = v2(x0, y0, c, 0, 0), b = v2(x1, y0, c, 0, 0), d = v2(x1, y1, c, 0, 0), e = v2(x0, y1, c, 0, 0);
	quad(&a, &b, &d, &e);
}
/* Text at (x, y), each glyph 6x8 texels scaled by sc; the state must be the font's (text_state) */
static void text_state(void)
{
	state(TEX_FONT, BLEND_ALPHA, 0, 0, 0, 1, 1);
}
static float text(float x, float y, int sc, uint32_t c, const char *s)
{
	for (; *s; s++, x += 6.0f * sc) {
		int ch = *s;
		if (ch >= 'a' && ch <= 'z')
			ch -= 'a' - 'A';
		if (ch < 32 || ch > 126)
			ch = '?';
		if (ch == ' ')
			continue;
		float s0 = (float)(((ch - 32) & 15) * 8) / 128, t0 = (float)(((ch - 32) >> 4) * 8) / 128;
		float s1 = s0 + 6.0f / 128, t1 = t0 + 8.0f / 128;
		struct dvtx a = v2(x, y, c, s0, t0), b = v2(x + 6.0f * sc, y, c, s1, t0);
		struct dvtx d = v2(x + 6.0f * sc, y + 8.0f * sc, c, s1, t1), e = v2(x, y + 8.0f * sc, c, s0, t1);
		quad(&a, &b, &d, &e);
	}
	return x;
}
static int text_width(const char *s, int sc)
{
	int n = 0;
	while (s[n])
		n++;
	return n * 6 * sc;
}

/* --- the probes ------------------------------------------------------------------------------- */

struct probe {
	int x, y;
	int rgb[3];
	const char *what;
};
#define MAXPROBES 12
static struct probe probes[MAXPROBES];
static int nprobes;
static void probe(int x, int y, int r, int g, int b, const char *what)
{
	if (nprobes >= MAXPROBES)
		return;
	struct probe *p = &probes[nprobes++];
	p->x = clampi(x, 0, demo_view.w - 1), p->y = clampi(y, 0, demo_view.h - 1);
	p->rgb[0] = clampi(r, 0, 255), p->rgb[1] = clampi(g, 0, 255), p->rgb[2] = clampi(b, 0, 255);
	p->what = what;
}

/* --- the parts -------------------------------------------------------------------------------- */

static const char *api_version = "", *wrapper_rev = "not found";

/* The cube: 1 unit half-size at z 4.5, light from the upper right in front */
static const int WALL[3] = {40, 48, 72};
static void part_cube(double t, int check)
{
	double ax = check ? 0 : t * 0.61, ay = check ? 0 : t * 0.93, z0 = check ? 4.5 : 4.5 + 0.6 * m_sin(t * 0.7);
	double sx = m_sin(ax), cx = m_cos(ax), sy = m_sin(ay), cy = m_cos(ay);
	double l[3] = {0.3, 0.4, -1}, ll = m_sqrt(l[0] * l[0] + l[1] * l[1] + l[2] * l[2]);
	/* faces: the normal, then two axes across the face (s and t directions), and a tint; the front
	 * face (towards the camera) first, the back face last (the depth test keeps the front one) */
	static const double faces[6][10] = {
		{0, 0, -1, 1, 0, 0, 0, -1, 0, 1.0}, /* front: white */
		{1, 0, 0, 0, 0, 1, 0, -1, 0, 0.6}, {-1, 0, 0, 0, 0, -1, 0, -1, 0, 0.6}, {0, 1, 0, 1, 0, 0, 0, 0, 1, 0.8},
		{0, -1, 0, 1, 0, 0, 0, 0, -1, 0.8}, {0, 0, 1, -1, 0, 0, 0, -1, 0, 0.5}, /* back */
	};
	static const double tints[6][3] = {{1, 1, 1}, {1, 0.75, 0.6}, {0.6, 0.8, 1}, {0.75, 1, 0.6}, {1, 0.6, 0.9}, {1, 1, 1}};
	be->clear(argb(255, 0, 0, 0));
	state(TEX_CUBE, BLEND_NONE, 1, 0, 1, 0, 0);
	for (int f = 0; f < 6; f++) {
		const double *F = faces[f];
		double p[4][3], uv[4][2] = {{0, 0}, {1, 0}, {1, 1}, {0, 1}};
		for (int k = 0; k < 4; k++) {
			double u = uv[k][0] * 2 - 1, v = uv[k][1] * 2 - 1;
			double o[3] = {F[0] + F[3] * u + F[6] * v, F[1] + F[4] * u + F[7] * v, F[2] + F[5] * u + F[8] * v};
			/* rotate about y, then x */
			double x1 = o[0] * cy + o[2] * sy, z1 = -o[0] * sy + o[2] * cy;
			double y2 = o[1] * cx - z1 * sx, z2 = o[1] * sx + z1 * cx;
			p[k][0] = x1, p[k][1] = y2, p[k][2] = z2 + z0;
		}
		double n1x = F[0] * cy + F[2] * sy, n1z = -F[0] * sy + F[2] * cy;
		double ny = F[1] * cx - n1z * sx, nz = F[1] * sx + n1z * cx;
		double d = (n1x * l[0] + ny * l[1] + nz * l[2]) / ll;
		double shade = 0.25 + 0.75 * (d > 0 ? d : 0);
		double r = 255 * shade * tints[f][0] * F[9], g = 255 * shade * tints[f][1] * F[9], b = 255 * shade * tints[f][2] * F[9];
		if (f == 0)
			r = g = b = 255 * shade;
		struct dvtx v[4];
		for (int k = 0; k < 4; k++)
			v[k] = v3(p[k][0], p[k][1], p[k][2], r, g, b, 255, uv[k][0], uv[k][1]);
		quad(&v[0], &v[1], &v[2], &v[3]);
	}
	/* the wall behind, drawn after the cube */
	state(-1, BLEND_NONE, 1, 0, 1, 0, 0);
	double wz = 20, hx = wz * demo_view.w / demo_view.f, hy = wz * demo_view.h / demo_view.f;
	struct dvtx w[4] = {v3(-hx, hy, wz, WALL[0], WALL[1], WALL[2], 255, 0, 0), v3(hx, hy, wz, WALL[0], WALL[1], WALL[2], 255, 0, 0),
			    v3(hx, -hy, wz, WALL[0], WALL[1], WALL[2], 255, 0, 0),
			    v3(-hx, -hy, wz, WALL[0], WALL[1], WALL[2], 255, 0, 0)};
	quad(&w[0], &w[1], &w[2], &w[3]);
	flush();
	if (check) {
		/* the front face at z 3.5 spans +-f/3.5 around the centre, 8 cells across */
		double hs = demo_view.f / 3.5, shade = 0.25 + 0.75 / ll;
		static const char *what[4] = {"cube, orange cell", "cube, blue cell", "cube, blue cell", "cube, orange cell"};
		for (int i = 0; i < 4; i++) {
			int ci = 3 + (i & 1), cj = 3 + (i >> 1);
			const int *c = ((ci + cj) & 1) ? CUBE_B : CUBE_A;
			int px = m_round(demo_view.w / 2.0 - hs + (ci + 0.5) * hs / 4), py = m_round(demo_view.h / 2.0 - hs + (cj + 0.5) * hs / 4);
			probe(px, py, m_round(c[0] * shade), m_round(c[1] * shade), m_round(c[2] * shade), what[i]);
		}
		probe(demo_view.w / 12, demo_view.h / 10, WALL[0], WALL[1], WALL[2], "wall, top left");
		probe(demo_view.w * 11 / 12, demo_view.h * 9 / 10, WALL[0], WALL[1], WALL[2], "wall, bottom right");
	}
}

/* The tunnel: rings of radius 1 from z 0.8 to 36, fogged from z 4 to 12 */
#define RINGS 48
#define SEGS 16
static const int FOG[3] = {20, 10, 40};
static void part_tunnel(double t, int check)
{
	be->clear(argb(255, FOG[0], FOG[1], FOG[2]));
	be->fog(4, 12, argb(255, FOG[0], FOG[1], FOG[2]));
	state(TEX_TUNNEL, BLEND_NONE, 1, 1, 1, 0, 0);
	double scroll = check ? 0 : -t * 0.6, spin = check ? 0 : t * 0.3;
	static struct dvtx ring[2][SEGS + 1];
	for (int k = 0; k < RINGS; k++) {
		double z = 0.8 + k * 0.75;
		double ox = check ? 0 : 0.5 * m_sin(z * 0.12 + t * 0.8) * (z / 30), oy = check ? 0 : 0.35 * m_cos(z * 0.1 + t * 0.6) * (z / 30);
		for (int s = 0; s <= SEGS; s++) {
			double a = s * 2 * PI / SEGS + spin + z * 0.02;
			double shade = 0.7 + 0.3 * m_sin(a);
			ring[k & 1][s] = v3(ox + m_cos(a), oy + m_sin(a), z, 255 * shade, 255 * shade, 255 * shade, 255, s * 4.0 / SEGS,
					    z * 0.25 + scroll);
		}
		if (k)
			for (int s = 0; s < SEGS; s++)
				quad(&ring[(k - 1) & 1][s], &ring[(k - 1) & 1][s + 1], &ring[k & 1][s + 1], &ring[k & 1][s]);
	}
	/* stars flying towards the camera (additive) */
	float cxs = demo_view.w * 0.5f, cys = demo_view.h * 0.5f, unit = demo_view.h / 480.0f;
	if (!check) {
		state(-1, BLEND_ADD, 0, 0, 1, 0, 1);
		for (int i = 0; i < 64; i++) {
			uint32_t h = hash((uint32_t)i * 2654435761U);
			double z = 30 - ((h & 1023) / 1023.0 * 30 + t * 6);
			while (z < 1)
				z += 30;
			double a = ((h >> 10) & 1023) / 1023.0 * 2 * PI, r = 0.2 + ((h >> 20) & 255) / 255.0 * 0.6;
			float x = (float)(cxs + r * m_cos(a) * demo_view.f / z), y = (float)(cys - r * m_sin(a) * demo_view.f / z);
			float sz = unit * (float)(0.6 + 2.5 / z);
			int br = clampi(m_round(255 * (1 - z / 30)), 0, 255);
			rect(x - sz, y - sz, x + sz, y + sz, argb(255, br, br, clampi(br + 40, 0, 255)));
		}
	}
	/* the translucent square in the middle (alpha 128 when checked) */
	int alpha = check ? 128 : 96 + m_round(48 * m_sin(t * 2.3));
	float hs = demo_view.h / 24.0f;
	state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	rect(cxs - hs, cys - hs, cxs + hs, cys + hs, argb(alpha, 255, 255, 255));
	flush();
	if (check) {
		double a = alpha / 255.0;
		probe((int)cxs, (int)cys, m_round(FOG[0] * (1 - a) + 255 * a), m_round(FOG[1] * (1 - a) + 255 * a),
		      m_round(FOG[2] * (1 - a) + 255 * a), "translucent square over the fog");
		/* 30 pixels out (at 480 lines): the tunnel at z 14 and beyond, all fog */
		int r = demo_view.h / 16;
		probe((int)cxs + r, (int)cys, FOG[0], FOG[1], FOG[2], "fogged tunnel, right of the square");
		probe((int)cxs - r, (int)cys, FOG[0], FOG[1], FOG[2], "fogged tunnel, left of the square");
		probe((int)cxs, (int)cys - r, FOG[0], FOG[1], FOG[2], "fogged tunnel, above the square");
		probe((int)cxs, (int)cys + r, FOG[0], FOG[1], FOG[2], "fogged tunnel, below the square");
	}
}

/* The plasma's texel at screen (px, py) as bilinear filtering gives it (the quad spans the screen) */
static void plasma_sample(double px, double py, int rgb[3])
{
	double u = (px + 0.5) * 256 / demo_view.w - 0.5, v = (py + 0.5) * 256 / demo_view.h - 0.5;
	if (u < 0)
		u = 0;
	if (v < 0)
		v = 0;
	if (u > 255)
		u = 255;
	if (v > 255)
		v = 255;
	int x0 = (int)u, y0 = (int)v, x1 = x0 < 255 ? x0 + 1 : 255, y1 = y0 < 255 ? y0 + 1 : 255;
	double fx = u - x0, fy = v - y0;
	for (int c = 0; c < 3; c++) {
		int sh = 16 - 8 * c;
		double a = (tex_plasma[y0 * 256 + x0] >> sh) & 0xff, b = (tex_plasma[y0 * 256 + x1] >> sh) & 0xff;
		double d = (tex_plasma[y1 * 256 + x0] >> sh) & 0xff, e = (tex_plasma[y1 * 256 + x1] >> sh) & 0xff;
		rgb[c] = m_round((a * (1 - fx) + b * fx) * (1 - fy) + (d * (1 - fx) + e * fx) * fy);
	}
}

static void part_plasma(double t, int check)
{
	gen_plasma(t);
	be->tex_update(TEX_PLASMA, tex_plasma);
	be->clear(argb(255, 0, 0, 0));
	state(TEX_PLASMA, BLEND_NONE, 0, 0, 1, 1, 1);
	float W = (float)demo_view.w, H = (float)demo_view.h;
	struct dvtx a = v2(0, 0, 0xffffffffU, 0, 0), b = v2(W, 0, 0xffffffffU, 1, 0), c = v2(W, H, 0xffffffffU, 1, 1),
		    d = v2(0, H, 0xffffffffU, 0, 1);
	quad(&a, &b, &c, &d);
	/* copper bars: a vertical ramp up to the bar's colour and down again, added */
	static const uint32_t bars[3] = {0xffe03018U, 0xff20d040U, 0xff3060f0U};
	double yc[3], hb = H / 20;
	state(-1, BLEND_ADD, 0, 0, 1, 0, 1);
	for (int k = 0; k < 3; k++) {
		yc[k] = H * (0.5 + 0.35 * m_sin(t * 1.3 + k * 2.1));
		struct dvtx p0 = v2(0, (float)(yc[k] - hb), bars[k] & 0xff000000U, 0, 0), p1 = v2(W, (float)(yc[k] - hb), bars[k] & 0xff000000U, 0, 0);
		struct dvtx p2 = v2(W, (float)yc[k], bars[k], 0, 0), p3 = v2(0, (float)yc[k], bars[k], 0, 0);
		struct dvtx p4 = v2(W, (float)(yc[k] + hb), bars[k] & 0xff000000U, 0, 0), p5 = v2(0, (float)(yc[k] + hb), bars[k] & 0xff000000U, 0, 0);
		quad(&p0, &p1, &p2, &p3);
		quad(&p3, &p2, &p4, &p5);
	}
	flush();
	if (check) {
		/* the flattest of a grid of points away from the bars: up to four */
		struct {
			int x, y, g, rgb[3];
		} best[4];
		int nb = 0;
		for (int j = 0; j < 9; j++)
			for (int i = 0; i < 12; i++) {
				int px = (int)((i + 0.5) * W / 12), py = (int)((j + 0.5) * H / 9), near = 0;
				for (int k = 0; k < 3; k++)
					near |= py > yc[k] - hb - 6 && py < yc[k] + hb + 6;
				if (near)
					continue;
				int e[3], gmax = 0;
				plasma_sample(px, py, e);
				static const int off[4][2] = {{3, 0}, {-3, 0}, {0, 3}, {0, -3}};
				for (int o = 0; o < 4; o++) {
					int s[3];
					plasma_sample(px + off[o][0], py + off[o][1], s);
					for (int c = 0; c < 3; c++) {
						int dd = s[c] > e[c] ? s[c] - e[c] : e[c] - s[c];
						gmax = dd > gmax ? dd : gmax;
					}
				}
				if (gmax > 12)
					continue;
				int slot = nb < 4 ? nb++ : -1;
				if (slot < 0) {
					int worst = 0;
					for (int q = 1; q < 4; q++)
						worst = best[q].g > best[worst].g ? q : worst;
					if (best[worst].g <= gmax)
						continue;
					slot = worst;
				}
				best[slot].x = px, best[slot].y = py, best[slot].g = gmax;
				memcpy(best[slot].rgb, e, sizeof(e));
			}
		for (int q = 0; q < nb; q++)
			probe(best[q].x, best[q].y, best[q].rgb[0], best[q].rgb[1], best[q].rgb[2], "plasma, flat area");
	}
}

/* The title card */
static void part_title(double t, int check)
{
	(void)check;
	float W = (float)demo_view.w, H = (float)demo_view.h, unit = H / 480;
	be->clear(argb(255, 0, 0, 0));
	state(-1, BLEND_NONE, 0, 0, 1, 0, 1);
	struct dvtx a = v2(0, 0, 0xff101848U, 0, 0), b = v2(W, 0, 0xff101848U, 0, 0), c = v2(W, H, 0xff000000U, 0, 0), d = v2(0, H, 0xff000000U, 0, 0);
	quad(&a, &b, &c, &d);
	/* a copper bar behind the name */
	double y = H * 0.22 + 10 * unit * m_sin(t * 2);
	state(-1, BLEND_ADD, 0, 0, 1, 0, 1);
	struct dvtx p0 = v2(0, (float)(y - 30 * unit), 0xff000000U, 0, 0), p1 = v2(W, (float)(y - 30 * unit), 0xff000000U, 0, 0);
	struct dvtx p2 = v2(W, (float)y, 0xffc06020U, 0, 0), p3 = v2(0, (float)y, 0xffc06020U, 0, 0);
	struct dvtx p4 = v2(W, (float)(y + 30 * unit), 0xff000000U, 0, 0), p5 = v2(0, (float)(y + 30 * unit), 0xff000000U, 0, 0);
	quad(&p0, &p1, &p2, &p3);
	quad(&p3, &p2, &p4, &p5);
	text_state();
	int big = H >= 600 ? 6 : 5, sm = H >= 600 ? 3 : 2;
	text((W - text_width("WSHDEMO", big)) / 2, (float)(y - 4 * big), big, 0xffffffffU, "WSHDEMO");
	char line[160];
	const char *sub = "A 3D PASS-THROUGH TEST FOR QEMU-3DFX";
	text((W - text_width(sub, sm)) / 2, H * 0.36f, sm, 0xffc0d0ffU, sub);
	float ly = H * 0.48f, x0 = W * 0.06f;
	int maxc = (int)((W - 2 * x0) / (6 * sm)); /* characters that fit on a line */
	if (maxc > (int)sizeof(line) - 1)
		maxc = (int)sizeof(line) - 1;
	demo_fmt(line, sizeof(line), "API:     %s", be->api);
	text(x0, ly, sm, 0xffffffa0U, line);
	demo_fmt(line, sizeof(line), "VERSION: %s", api_version);
	line[maxc] = 0;
	text(x0, ly += 14 * sm, sm, 0xffffffa0U, line);
	demo_fmt(line, sizeof(line), "WRAPPER: %s", wrapper_rev);
	line[maxc] = 0;
	text(x0, ly += 14 * sm, sm, 0xffffffa0U, line);
	demo_fmt(line, sizeof(line), "SCREEN:  %dX%d", demo_view.w, demo_view.h);
	text(x0, ly += 14 * sm, sm, 0xffffffa0U, line);
	const char *keys = "SPACE NEXT  G/SHIFT-G GAMMA  R RESOLUTION  F FPS  ESC QUIT";
	int ks = sm;
	while (ks > 1 && text_width(keys, ks) > W - 16)
		ks--;
	text((W - text_width(keys, ks)) / 2, H * 0.88f, ks, 0xff90ff90U, keys);
	flush();
}

struct part {
	const char *name;
	void (*draw)(double t, int check);
};
static const struct part parts[] = {{"cube", part_cube}, {"tunnel", part_tunnel}, {"plasma", part_plasma}};
#define NPARTS 3

/* --- the HUD: frame rate and frame times ------------------------------------------------------ */

#define GRAPH 64
static float ft_ms[GRAPH];
static int ft_pos;
static double hud_fps;
static void hud(const char *part, double gamma)
{
	float unit = demo_view.h >= 600 ? 2 : 1, x0 = 8 * unit, y0 = 8 * unit;
	state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	rect(x0, y0, x0 + 150 * unit, y0 + 70 * unit, 0xa0000000U);
	/* the graph: one bar a frame, 2 pixels wide, 1 pixel per ms (green to 20 ms, yellow to 34) */
	for (int i = 0; i < GRAPH; i++) {
		float ms = ft_ms[(ft_pos + i) % GRAPH], h = ms > 40 ? 40 : ms;
		uint32_t c = ms < 20 ? 0xff40e040U : ms < 34 ? 0xffe0e040U : 0xffe04040U;
		rect(x0 + (8 + i * 2) * unit, y0 + (64 - h) * unit, x0 + (9 + i * 2) * unit, y0 + 64 * unit, c);
	}
	text_state();
	char line[64];
	demo_fmt(line, sizeof(line), "%.1f FPS", hud_fps);
	text(x0 + 6 * unit, y0 + 4 * unit, (int)unit, 0xffffffffU, line);
	demo_fmt(line, sizeof(line), "%s G%.1f", part, gamma);
	text(x0 + 6 * unit, y0 + 14 * unit, (int)unit, 0xffa0c0ffU, line);
	flush();
}

/* --- the modes -------------------------------------------------------------------------------- */

static int read_and_check(const char *name)
{
	if (!be->read()) {
		demo_log("CHECK part=%s FAIL the read-back failed", name);
		return 1;
	}
	int bad = 0;
	char details[256];
	int o = 0;
	details[0] = 0;
	for (int i = 0; i < nprobes; i++) {
		struct probe *p = &probes[i];
		uint8_t got[3];
		be->pixel(p->x, p->y, got);
		int ok = 1;
		for (int c = 0; c < 3; c++) {
			int d = got[c] - p->rgb[c];
			ok &= d >= -TOLERANCE && d <= TOLERANCE;
		}
		demo_log("INFO %s %s (%d,%d) got #%02x%02x%02x want #%02x%02x%02x %s", name, ok ? "ok  " : "FAIL", p->x, p->y, got[0], got[1],
			 got[2], p->rgb[0], p->rgb[1], p->rgb[2], p->what);
		if (!ok) {
			bad++;
			if (o < (int)sizeof(details) - 40)
				o += demo_fmt(details + o, (int)sizeof(details) - o, "%s(%d,%d) #%02x%02x%02x!=#%02x%02x%02x", o ? " " : "", p->x, p->y,
					      got[0], got[1], got[2], p->rgb[0], p->rgb[1], p->rgb[2]);
		}
	}
	if (nprobes == 0) {
		demo_log("CHECK part=%s FAIL no probe could be placed", name);
		return 1;
	}
	if (bad)
		demo_log("CHECK part=%s FAIL %d of %d probes: %s", name, bad, nprobes, details);
	else
		demo_log("CHECK part=%s PASS %d probes", name, nprobes);
	return bad != 0;
}

static int run_check(void)
{
	int failed = 0;
	for (int p = 0; p < NPARTS; p++) {
		nprobes = 0;
		parts[p].draw(0, 1);
		failed += read_and_check(parts[p].name);
		be->swap(1);
	}
	return failed;
}

static void run_bench(int frames)
{
	for (int p = 0; p < NPARTS; p++) {
		uint32_t t0 = plat_us();
		for (int f = 0; f < frames; f++) {
			parts[p].draw(f / 60.0, 0);
			be->swap(0);
		}
		double secs = (uint32_t)(plat_us() - t0) / 1e6;
		demo_log("BENCH part=%s frames=%d secs=%.2f fps=%.1f", parts[p].name, frames, secs, secs > 0 ? frames / secs : 0);
		plat_key(); /* keep a window responsive */
	}
}

static const int RES[3][2] = {{640, 480}, {800, 600}, {1024, 768}};
static const double GAMMAS[] = {1.0, 1.2, 1.4, 1.7, 2.0, 0.8};
#define NGAMMA 6

static int set_res(int w, int h)
{
	demo_view.w = w, demo_view.h = h;
	demo_view.f = (float)(h * 0.866); /* 60 degrees vertically */
	demo_view.znear = 0.5f, demo_view.zfar = 100;
	return be->open(w, h);
}

/* Interactive: the title card, then the parts in turn, until Esc (or -time) */
static int run_demo(int secs_per_part, int total_secs, int show_hud, int start_part)
{
	int part = start_part < 0 ? -1 : start_part, gi = 0, ri = 0;
	for (int i = 0; i < 3; i++)
		if (RES[i][0] == demo_view.w && RES[i][1] == demo_view.h)
			ri = i;
	uint32_t t_start = plat_us(), t_part = t_start, t_last = t_start, t_sec = t_start;
	int frames_sec = 0;
	double ms_sum = 0;
	for (;;) {
		uint32_t now = plat_us();
		double t = (uint32_t)(now - t_part) / 1e6;
		int key = plat_key();
		if (key == 27 || key == 'q' || key == 'Q')
			break;
		if (total_secs > 0 && (uint32_t)(now - t_start) / 1000000 >= (uint32_t)total_secs)
			break;
		if (key == ' ' || t > (part < 0 ? 4 : secs_per_part)) {
			part = (part + 1) % NPARTS;
			t_part = now, t = 0;
		}
		if (key == 'f' || key == 'F')
			show_hud = !show_hud;
		if (key == 'g' || key == 'G') {
			gi = (gi + (key == 'g' ? 1 : NGAMMA - 1)) % NGAMMA;
			if (be->gamma((float)GAMMAS[gi]))
				demo_log("INFO gamma %.1f", GAMMAS[gi]);
			else
				demo_log("INFO gamma: not available with %s", be->api);
		}
		if (key == 'r' || key == 'R') {
			int ow = demo_view.w, oh = demo_view.h, n = ri;
			do
				n = (n + 1) % 3;
			while (n != ri && !be->res_ok(RES[n][0], RES[n][1]));
			if (n != ri) {
				be->close(0);
				if (set_res(RES[n][0], RES[n][1]) == 0) {
					ri = n;
					demo_log("INFO resolution %dx%d", demo_view.w, demo_view.h);
				} else if (set_res(ow, oh) != 0) {
					demo_log("ERROR could not open %dx%d again", ow, oh);
					return 2;
				} else {
					demo_log("INFO %dx%d failed, back to %dx%d", RES[n][0], RES[n][1], ow, oh);
				}
				upload_textures();
				if (GAMMAS[gi] != 1.0)
					be->gamma((float)GAMMAS[gi]);
			}
		}
		const char *name = part < 0 ? "title" : parts[part].name;
		if (part < 0)
			part_title(t, 0);
		else
			parts[part].draw(t, 0);
		if (show_hud)
			hud(name, GAMMAS[gi]);
		be->swap(1);
		/* frame times, and the frame rate once a second on the log */
		now = plat_us();
		double ms = (uint32_t)(now - t_last) / 1000.0;
		t_last = now;
		ft_ms[ft_pos] = (float)ms;
		ft_pos = (ft_pos + 1) % GRAPH;
		frames_sec++;
		ms_sum += ms;
		if ((uint32_t)(now - t_sec) >= 1000000) {
			hud_fps = frames_sec * 1e6 / (uint32_t)(now - t_sec);
			demo_log("FPS part=%s fps=%.1f ms=%.2f", name, hud_fps, ms_sum / frames_sec);
			t_sec = now, frames_sec = 0, ms_sum = 0;
		}
	}
	return 0;
}

static void usage(void)
{
	static const char *lines[] = {
		"usage: wshdemo [-check] [-bench N] [-hold S] [-res WxH] [-time S] [-secs S] [-part NAME] [-gamma G]",
		"               [-nohud] [-wait S] [-tag NAME] [-api glide2|glide3|opengl (Windows)] [-nocom (DOS)]",
		"  -check      draw a fixed frame of each part, read it back and check probe pixels (exit 1 on a mismatch)",
		"  -bench N    draw each part N frames without vsync and print the frame rate",
		"  -hold S     keep the last frame up for S seconds (after -check/-bench)",
		"  -wait S     wait S seconds before opening the 3D display",
		"  -res WxH    640x480 (default), 800x600 or 1024x768",
		"  -time S     quit the interactive demo after S seconds; -secs S: seconds per part (10)",
		"  -part NAME  start with cube, tunnel or plasma (skips the title card)",
		"keys: Space next part, G/Shift-G gamma up/down, R resolution, F frame rate, Esc quit",
	};
	for (unsigned i = 0; i < sizeof(lines) / sizeof(lines[0]); i++)
		plat_out(lines[i]);
}

int demo_main(int argc, char **argv, const struct backend *backend)
{
	be = backend;
	int check = 0, bench = 0, hold = 0, w = 640, h = 480, total = 0, secs = 10, show_hud = 1, start = -1, wait = 0;
	double gamma = 1.0;
	for (int i = 1; i < argc; i++) {
		const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : 0;
		if (str_eq(a, "-check"))
			check = 1;
		else if (str_eq(a, "-nohud"))
			show_hud = 0;
		else if (str_eq(a, "-nocom"))
			; /* the DOS front end's */
		else if (v && str_eq(a, "-wait"))
			wait = to_int(v), i++;
		else if (v && str_eq(a, "-bench"))
			bench = to_int(v), i++;
		else if (v && str_eq(a, "-hold"))
			hold = to_int(v), i++;
		else if (v && str_eq(a, "-time"))
			total = to_int(v), i++;
		else if (v && str_eq(a, "-secs"))
			secs = to_int(v), i++;
		else if (v && str_eq(a, "-tag"))
			tag = v, i++;
		else if (v && str_eq(a, "-api"))
			i++; /* the Windows front end's */
		else if (v && str_eq(a, "-gamma")) {
			gamma = to_int(v);
			for (const char *d = v; *d; d++)
				if (*d == '.') {
					double sc = 0.1;
					for (d++; *d >= '0' && *d <= '9'; d++, sc /= 10)
						gamma += (*d - '0') * sc;
					break;
				}
			i++;
		} else if (v && str_eq(a, "-part")) {
			for (int p = 0; p < NPARTS; p++)
				if (str_eq(v, parts[p].name))
					start = p;
			if (start < 0) {
				usage();
				return 2;
			}
			i++;
		} else if (v && str_eq(a, "-res")) {
			w = to_int(v);
			const char *x = v;
			while (*x && *x != 'x' && *x != 'X')
				x++;
			h = *x ? to_int(x + 1) : 0;
			i++;
		} else {
			usage();
			return a[0] == '-' && (a[1] == 'h' || a[1] == '?') ? 0 : 2;
		}
	}
	const char *mode = check && bench ? "check+bench" : check ? "check" : bench ? "bench" : "demo";
	demo_log("START api=%s res=%dx%d mode=%s%s", be->api, w, h, mode, hold ? " hold" : "");
	if (!be->res_ok(w, h)) {
		demo_log("ERROR %s can't open %dx%d (640x480, 800x600 or 1024x768)", be->api, w, h);
		demo_log("CLOSED");
		return 2;
	}
	gen_cube();
	gen_tunnel();
	gen_font();
	gen_plasma_tables();
	gen_plasma(0);
	for (int s = 0; s < wait * 50 && plat_key() != 27; s++)
		plat_sleep(20);
	uint32_t t0 = plat_us();
	if (set_res(w, h) != 0) {
		demo_log("ERROR no %s device (the wrapper isn't installed, or its revision isn't the host's)", be->api);
		demo_log("CLOSED");
		return 2;
	}
	api_version = be->version();
	static char rev[96];
	if (plat_wrapper_rev(rev, sizeof(rev)))
		wrapper_rev = rev;
	demo_log("VERSION %s, wrapper %s, opened %dx%d in %u ms", api_version, wrapper_rev, w, h, (uint32_t)(plat_us() - t0) / 1000);
	upload_textures();
	if (gamma != 1.0 && !be->gamma((float)gamma))
		demo_log("INFO gamma: not available with %s", be->api);
	int failed = 0, status = 0;
	if (bench > 0)
		run_bench(bench);
	if (check)
		failed = run_check();
	if (check || bench) {
		if (hold > 0) {
			/* the last check frame is up: its probes, for a host that checks the console */
			for (int i = 0; check && i < nprobes; i++)
				demo_log("PROBE %d %d %02x%02x%02x", probes[i].x, probes[i].y, probes[i].rgb[0], probes[i].rgb[1], probes[i].rgb[2]);
			demo_log("FRAME");
			uint32_t end = plat_us();
			while ((uint32_t)(plat_us() - end) < (uint32_t)hold * 1000000U) {
				if (plat_key() == 27)
					break;
				plat_sleep(20);
			}
		}
	} else {
		status = run_demo(secs, total, show_hud, start);
	}
	if (gamma != 1.0)
		be->gamma(1.0f);
	be->close(1);
	if (status)
		demo_log("ERROR the display could not be opened again");
	else if (failed)
		demo_log("FAIL %d", failed);
	else
		demo_log("PASS");
	demo_log("CLOSED");
	return status ? status : failed ? 1 : 0;
}
