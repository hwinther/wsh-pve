/*
 * wshspace's Glide 3 backend (Windows GLIDE3X.DLL).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stddef.h>

#include "space.h"
#include "glide3.h"

void *memset(void *d, int c, size_t n);

struct glide3_api g3;

typedef struct {
	float x, y, q;
	float r, g, b, a;
	float s, t;
} Vertex3;

typedef struct {
	int32_t small_lod_log2, large_lod_log2, aspect_log2, format;
	void *data;
} GrTexInfo3;

static struct {
	GrTexInfo3 info;
	uint32_t addr, bytes;
	int size, levels, alpha, loaded;
} tex[TEX_COUNT];
static uint32_t tex_next, tex_max, context;
static int inited;
static char version[96];
static uint16_t texbuf[256 * 256 * 4 / 3 + 1];
static uint16_t lfb[1024 * 768];
static int read_w, fog_n = 64;
static float fog_start = -1, fog_end = -1;
static uint32_t fog_rgb;

static int log2i(int v)
{
	int l = 0;
	while (v > 1)
		v >>= 1, l++;
	return l;
}

static int g3_res_ok(int w, int h)
{
	return (w == 640 && h == 480) || (w == 800 && h == 600) || (w == 1024 && h == 768);
}

static int g3_open(int w, int h)
{
	if (!inited) {
		g3.grGlideInit();
		g3.grSstSelect(0);
		inited = 1;
	}
	int res = w == 1024 ? GR_RESOLUTION_1024x768 : w == 800 ? GR_RESOLUTION_800x600 : GR_RESOLUTION_640x480;
	context = g3.grSstWinOpen(g3.hwnd, res, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB, GR_ORIGIN_UPPER_LEFT, 2, 1);
	if (!context)
		return -1;
	read_w = w;
	const char *v = g3.grGetString(GR_VERSION), *r = g3.grGetString(GR_RENDERER);
	space_fmt(version, sizeof(version), "Glide %s (%s)", v ? v : "?", r ? r : "?");
	g3.grCoordinateSpace(GR_WINDOW_COORDS);
	g3.grVertexLayout(GR_PARAM_XY, (int32_t)offsetof(Vertex3, x), GR_PARAM_ENABLE);
	g3.grVertexLayout(GR_PARAM_Q, (int32_t)offsetof(Vertex3, q), GR_PARAM_ENABLE);
	g3.grVertexLayout(GR_PARAM_RGB, (int32_t)offsetof(Vertex3, r), GR_PARAM_ENABLE);
	g3.grVertexLayout(GR_PARAM_A, (int32_t)offsetof(Vertex3, a), GR_PARAM_ENABLE);
	g3.grVertexLayout(GR_PARAM_ST0, (int32_t)offsetof(Vertex3, s), GR_PARAM_ENABLE);
	g3.grDepthBufferMode(GR_DEPTHBUFFER_WBUFFER);
	g3.grCullMode(GR_CULL_DISABLE);
	g3.grTexCombine(GR_TMU0, GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, 0, 0);
	int32_t n = 0;
	if (g3.grGet(GR_FOG_TABLE_ENTRIES, sizeof(n), &n) && n > 0 && n <= 64)
		fog_n = n;
	tex_next = g3.grTexMinAddress(GR_TMU0);
	tex_max = g3.grTexMaxAddress(GR_TMU0);
	for (int i = 0; i < TEX_COUNT; i++)
		tex[i].loaded = 0;
	fog_start = fog_end = -1;
	return 0;
}

static void g3_close(int final)
{
	if (context)
		g3.grSstWinClose(context);
	context = 0;
	if (final && inited)
		g3.grGlideShutdown();
	if (final)
		inited = 0;
}

static const char *g3_version(void)
{
	return version;
}

static void g3_clear(uint32_t rgb)
{
	g3.grDepthMask(1);
	g3.grBufferClear(rgb | 0xff000000U, 0, GR_WDEPTHVALUE_FARTHEST);
}

static void g3_tex_load(int id, int size, int levels, const uint32_t *argb, int alpha)
{
	uint32_t n = 0;
	for (int s = size, l = 0; l < levels; l++, s >>= 1)
		n += (uint32_t)(s * s);
	glide_convert(argb, n, alpha, texbuf);
	GrTexInfo3 *ti = &tex[id].info;
	ti->large_lod_log2 = log2i(size);
	ti->small_lod_log2 = log2i(size >> (levels - 1));
	ti->aspect_log2 = 0;
	ti->format = alpha ? GR_TEXFMT_ARGB_4444 : GR_TEXFMT_RGB_565;
	ti->data = texbuf;
	if (!tex[id].loaded) {
		tex[id].bytes = g3.grTexTextureMemRequired(GR_MIPMAPLEVELMASK_BOTH, ti);
		tex[id].addr = (tex_next + 7) & ~7U;
		tex_next = tex[id].addr + tex[id].bytes;
		if (tex_next > tex_max)
			space_log("INFO Glide 3: texture %d at 0x%x past TMU end 0x%x", id, tex[id].addr, tex_max);
		tex[id].loaded = 1;
	}
	tex[id].size = size, tex[id].levels = levels, tex[id].alpha = alpha;
	g3.grTexDownloadMipMap(GR_TMU0, tex[id].addr, GR_MIPMAPLEVELMASK_BOTH, ti);
}

static void g3_tex_update(int id, const uint32_t *argb)
{
	g3_tex_load(id, tex[id].size, 1, argb, tex[id].alpha);
}

static void g3_state(const struct rstate *s)
{
	if (s->tex >= 0) {
		g3.grTexSource(GR_TMU0, tex[s->tex].addr, GR_MIPMAPLEVELMASK_BOTH, &tex[s->tex].info);
		int f = s->filter ? GR_TEXTUREFILTER_BILINEAR : GR_TEXTUREFILTER_POINT_SAMPLED;
		g3.grTexFilterMode(GR_TMU0, f, f);
		g3.grTexMipMapMode(GR_TMU0, s->filter && tex[s->tex].levels > 1 ? GR_MIPMAP_NEAREST : GR_MIPMAP_DISABLE, 0);
		int c = s->clamp ? GR_TEXTURECLAMP_CLAMP : GR_TEXTURECLAMP_WRAP;
		g3.grTexClampMode(GR_TMU0, c, c);
		g3.grColorCombine(GR_COMBINE_FUNCTION_SCALE_OTHER, GR_COMBINE_FACTOR_LOCAL, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_TEXTURE, 0);
		g3.grAlphaCombine(GR_COMBINE_FUNCTION_SCALE_OTHER, GR_COMBINE_FACTOR_LOCAL, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_TEXTURE, 0);
	} else {
		g3.grColorCombine(GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_CONSTANT, 0);
		g3.grAlphaCombine(GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_CONSTANT, 0);
	}
	if (s->blend == BLEND_ALPHA)
		g3.grAlphaBlendFunction(GR_BLEND_SRC_ALPHA, GR_BLEND_ONE_MINUS_SRC_ALPHA, GR_BLEND_ONE, GR_BLEND_ZERO);
	else if (s->blend == BLEND_ADD)
		g3.grAlphaBlendFunction(GR_BLEND_SRC_ALPHA, GR_BLEND_ONE, GR_BLEND_ONE, GR_BLEND_ZERO);
	else
		g3.grAlphaBlendFunction(GR_BLEND_ONE, GR_BLEND_ZERO, GR_BLEND_ONE, GR_BLEND_ZERO);
	g3.grDepthBufferFunction(s->depth ? GR_CMP_LESS : GR_CMP_ALWAYS);
	g3.grDepthMask(s->depth);
	g3.grFogMode(s->fog ? GR_FOG_WITH_TABLE : GR_FOG_DISABLE);
}

static void g3_fog(float start, float end, uint32_t rgb)
{
	if (start == fog_start && end == fog_end && rgb == fog_rgb)
		return;
	static uint8_t table[64];
	glide_fog_table(start, end, table, fog_n);
	g3.grFogTable(table);
	g3.grFogColorValue(rgb | 0xff000000U);
	fog_start = start, fog_end = end, fog_rgb = rgb;
}

static void g3_tris(const struct dvtx *v, int n)
{
	Vertex3 g[3];
	for (int i = 0; i + 2 < n; i += 3) {
		for (int k = 0; k < 3; k++) {
			const struct dvtx *d = &v[i + k];
			Vertex3 *o = &g[k];
			o->x = d->x, o->y = d->y, o->q = d->oow;
			o->r = d->r, o->g = d->g, o->b = d->b, o->a = d->a;
			o->s = d->s * 256 * d->oow;
			o->t = d->t * 256 * d->oow;
		}
		g3.grDrawTriangle(&g[0], &g[1], &g[2]);
	}
}

static void g3_swap(int vsync)
{
	g3.grBufferSwap(vsync ? 1 : 0);
}

static int g3_read(void)
{
	uint16_t px;
	g3.grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, 1, 1, 2, &px);
	return g3.grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, (uint32_t)space_view.w, (uint32_t)space_view.h,
				  (uint32_t)space_view.w * 2, lfb) != 0;
}

static void g3_pixel(int x, int y, uint8_t rgb[3])
{
	uint16_t v = lfb[y * read_w + x];
	for (int c = 0; c < 3; c++)
		rgb[c] = glide_565(v, c);
}

static int g3_gamma(float g)
{
	g3.guGammaCorrectionRGB(g, g, g);
	return 1;
}

const struct backend glide3_backend = {
	"Glide 3", g3_open, g3_close, g3_version, g3_clear, g3_tex_load, g3_tex_update, g3_state, g3_fog,
	g3_tris, g3_swap, g3_read, g3_pixel, g3_gamma, g3_res_ok,
};
