/*
 * wshracer's OpenGL 1.1 backend (Windows OPENGL32.DLL and host plat_egl.c).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stddef.h>

#include "racer.h"
#include "gl11.h"

void *memset(void *d, int c, size_t n);

struct gl_api glf;

static unsigned names[TEX_COUNT];
static int levels_of[TEX_COUNT], size_of[TEX_COUNT], opened, mode2d = -1, read_w;
static char version[128];
static uint8_t texbuf[256 * 256 * 4];
static uint8_t pixels[MAX_PIXELS * 4];

static void to_rgba(const uint32_t *argb, uint32_t n)
{
	for (uint32_t i = 0; i < n; i++) {
		uint32_t c = argb[i];
		texbuf[i * 4] = (uint8_t)(c >> 16), texbuf[i * 4 + 1] = (uint8_t)(c >> 8);
		texbuf[i * 4 + 2] = (uint8_t)c, texbuf[i * 4 + 3] = (uint8_t)(c >> 24);
	}
}

static int gl_res_ok(int w, int h)
{
	static const short m[][2] = {{640, 480}, {800, 600}, {1024, 768}, {1280, 960}, {1280, 1024}, {1600, 1200}, {1920, 1080}};
	for (unsigned i = 0; i < sizeof(m) / sizeof(m[0]); i++)
		if (m[i][0] == w && m[i][1] == h)
			return 1;
	return 0;
}

static void projection(int two_d)
{
	if (two_d == mode2d)
		return;
	mode2d = two_d;
	glf.glMatrixMode(GL_PROJECTION);
	glf.glLoadIdentity();
	if (two_d) {
		glf.glOrtho(0, racer_view.w, racer_view.h, 0, -1, 1);
	} else {
		double n = racer_view.znear, x = n * racer_view.w / (2.0 * racer_view.f), y = n * racer_view.h / (2.0 * racer_view.f);
		glf.glFrustum(-x, x, -y, y, n, racer_view.zfar);
	}
	glf.glMatrixMode(GL_MODELVIEW);
}

static int gl_open(int w, int h)
{
	if (glw_open(w, h))
		return -1;
	opened = 1;
	read_w = w;
	const char *v = (const char *)glf.glGetString(GL_VERSION), *r = (const char *)glf.glGetString(GL_RENDERER);
	racer_fmt(version, sizeof(version), "OpenGL %s (%s)", v ? v : "?", r ? r : "?");
	glf.glViewport(0, 0, w, h);
	glf.glMatrixMode(GL_MODELVIEW);
	glf.glLoadIdentity();
	mode2d = -1;
	projection(0);
	glf.glShadeModel(GL_SMOOTH);
	glf.glDepthFunc(GL_LESS);
	glf.glClearDepth(1.0);
	glf.glHint(GL_FOG_HINT, GL_NICEST);
	glf.glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST);
	glf.glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);
	glf.glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
	glf.glPixelStorei(GL_PACK_ALIGNMENT, 4);
	glf.glGenTextures(TEX_COUNT, names);
	return 0;
}

static void gl_close(int final)
{
	if (opened) {
		glf.glDeleteTextures(TEX_COUNT, names);
		glw_close(final);
	}
	opened = 0;
}

static const char *gl_version(void)
{
	return version;
}

static void gl_clear(uint32_t rgb)
{
	glf.glDepthMask(1);
	glf.glClearColor(((rgb >> 16) & 0xff) / 255.0f, ((rgb >> 8) & 0xff) / 255.0f, (rgb & 0xff) / 255.0f, 1);
	glf.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
}

static void gl_tex_load(int id, int size, int levels, const uint32_t *argb, int alpha)
{
	(void)alpha;
	glf.glBindTexture(GL_TEXTURE_2D, names[id]);
	for (int l = 0, s = size; l < levels; l++, s >>= 1) {
		to_rgba(argb, (uint32_t)(s * s));
		glf.glTexImage2D(GL_TEXTURE_2D, l, GL_RGBA, s, s, 0, GL_RGBA, GL_UNSIGNED_BYTE, texbuf);
		argb += s * s;
	}
	levels_of[id] = levels, size_of[id] = size;
}

static void gl_tex_update(int id, const uint32_t *argb)
{
	glf.glBindTexture(GL_TEXTURE_2D, names[id]);
	to_rgba(argb, (uint32_t)(size_of[id] * size_of[id]));
	glf.glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, size_of[id], size_of[id], GL_RGBA, GL_UNSIGNED_BYTE, texbuf);
}

static void gl_state(const struct rstate *s)
{
	projection(s->mode2d);
	if (s->tex >= 0) {
		glf.glEnable(GL_TEXTURE_2D);
		glf.glBindTexture(GL_TEXTURE_2D, names[s->tex]);
		int mag = s->filter ? GL_LINEAR : GL_NEAREST;
		int min = !s->filter ? GL_NEAREST : levels_of[s->tex] > 1 ? GL_LINEAR_MIPMAP_NEAREST : GL_LINEAR;
		glf.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, mag);
		glf.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, min);
		int ws = s->clamp ? GL_CLAMP_TO_EDGE : GL_REPEAT;
		int wt = (s->clamp == CLAMP_ALL) ? GL_CLAMP_TO_EDGE : GL_REPEAT;
		glf.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, ws);
		glf.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wt);
	} else {
		glf.glDisable(GL_TEXTURE_2D);
	}
	if (s->blend == BLEND_NONE) {
		glf.glDisable(GL_BLEND);
	} else {
		glf.glEnable(GL_BLEND);
		glf.glBlendFunc(GL_SRC_ALPHA, s->blend == BLEND_ADD ? GL_ONE : GL_ONE_MINUS_SRC_ALPHA);
	}
	if (s->depth) {
		glf.glEnable(GL_DEPTH_TEST);
		glf.glDepthFunc(s->depth == DEPTH_RO ? GL_LEQUAL : GL_LESS);
	} else {
		glf.glDisable(GL_DEPTH_TEST);
	}
	glf.glDepthMask(s->depth == DEPTH_RW ? 1 : 0);
	if (s->fog)
		glf.glEnable(GL_FOG);
	else
		glf.glDisable(GL_FOG);
}

static void gl_fog(float start, float end, uint32_t rgb)
{
	float c[4] = {((rgb >> 16) & 0xff) / 255.0f, ((rgb >> 8) & 0xff) / 255.0f, (rgb & 0xff) / 255.0f, 1};
	glf.glFogi(GL_FOG_MODE, GL_LINEAR);
	glf.glFogf(GL_FOG_START, start);
	glf.glFogf(GL_FOG_END, end);
	glf.glFogfv(GL_FOG_COLOR, c);
}

static void gl_tris(const struct dvtx *v, int n)
{
	glf.glBegin(GL_TRIANGLES);
	for (int i = 0; i < n; i++) {
		glf.glColor4f(v[i].r / 255, v[i].g / 255, v[i].b / 255, v[i].a / 255);
		glf.glTexCoord2f(v[i].s, v[i].t);
		if (mode2d)
			glf.glVertex2f(v[i].x, v[i].y);
		else
			glf.glVertex3f(v[i].vx, v[i].vy, -v[i].vz);
	}
	glf.glEnd();
}

static void gl_swap(int vsync)
{
	glw_swap(vsync);
}

static int gl_read(void)
{
	glf.glFinish();
	glf.glReadBuffer(GL_BACK);
	glf.glReadPixels(0, 0, racer_view.w, racer_view.h, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
	return 1;
}

static void gl_pixel(int x, int y, uint8_t rgb[3])
{
	const uint8_t *p = pixels + ((racer_view.h - 1 - y) * read_w + x) * 4;
	rgb[0] = p[0], rgb[1] = p[1], rgb[2] = p[2];
}

static double ramp(double x, double g)
{
	if (x <= 0)
		return 0;
	int k = 0;
	while (x < 0.5)
		x *= 2, k++;
	double y = (x - 1) / (x + 1), y2 = y * y, ln = 0, t = y;
	for (int i = 1; i < 40; i += 2, t *= y2)
		ln += t / i;
	ln = 2 * ln - k * 0.69314718055994531;
	double e = ln / g, r = 1, term = 1;
	for (int i = 1; i < 40; i++)
		term *= e / i, r += term;
	return r;
}

static int gl_gamma(float g)
{
	static uint16_t table[3][256];
	for (int i = 0; i < 256; i++) {
		double v = ramp(i / 255.0, g) * 65535 + 0.5;
		table[0][i] = table[1][i] = table[2][i] = (uint16_t)(v > 65535 ? 65535 : v);
	}
	return glw_gamma(table);
}

const struct backend gl_backend = {
	"OpenGL", gl_open, gl_close, gl_version, gl_clear, gl_tex_load, gl_tex_update, gl_state, gl_fog,
	gl_tris, gl_swap, gl_read, gl_pixel, gl_gamma, gl_res_ok,
};
