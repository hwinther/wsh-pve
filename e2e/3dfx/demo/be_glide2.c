/*
 * wshdemo's Glide 2 backend, for every guest the wrapper exists in (Linux libglide.so.2, DOS
 * GLIDE2X.DXE, Windows GLIDE2X.DLL): through the table g2 the front end fills (glide2.h).
 *
 * Screen-space vertices (GrVertex with one TMU's s/w, t/w), a W-buffer (GR_CMP_LESS on 1/oow),
 * table fog on W, RGB 565 textures (ARGB 4444 with alpha) placed one after the other from
 * grTexMinAddress, mipmaps downloaded in one grTexDownloadMipMap. The read-back drains the FIFO
 * with a 1x1 read first: a read that has queued calls in front of it comes back shifted (see
 * e2e/3dfx/glide-guest.c). Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stddef.h>

#include "demo.h"
#include "glide2.h"

void *memset(void *d, int c, size_t n);

struct glide2_api g2;

/* The Glide 2 vertex (GLIDE_NUM_TMU 2) */
typedef struct {
	float sow, tow, oow;
} TmuVertex;
typedef struct {
	float x, y, z, r, g, b, ooz, a, oow;
	TmuVertex tmuvtx[2];
} GrVertex;

/* GrTexInfo: smallLod, largeLod, aspectRatio, format, data */
typedef struct {
	int32_t small_lod, large_lod, aspect, format;
	void *data;
} GrTexInfo;

static struct {
	GrTexInfo info;
	uint32_t addr, bytes;
	int size, levels, alpha, loaded;
} tex[TEX_COUNT];
static uint32_t tex_next, tex_max;
static int inited, opened;
static char version[80];
static uint16_t texbuf[256 * 256 * 4 / 3 + 1];
static uint16_t lfb[1024 * 768];
static int read_w;
static float fog_start = -1, fog_end = -1;
static uint32_t fog_rgb;

/* guFogTableIndexToW: the W of each of the 64 fog table entries */
static double fog_w(int i)
{
	double w = 8;
	for (int k = 0; k < (i >> 2); k++)
		w *= 2;
	return w / (8 - (i & 3));
}
void glide_fog_table(float start, float end, uint8_t *table, int n)
{
	for (int i = 0; i < n; i++) {
		double f = (fog_w(i) - start) / (end - start);
		table[i] = (uint8_t)(f <= 0 ? 0 : f >= 1 ? 255 : (int)(f * 255 + 0.5));
	}
}
void glide_convert(const uint32_t *argb, uint32_t n, int alpha, uint16_t *dst)
{
	if (alpha)
		for (uint32_t i = 0; i < n; i++)
			dst[i] = argb_to_4444(argb[i]);
	else
		for (uint32_t i = 0; i < n; i++)
			dst[i] = argb_to_565(argb[i]);
}
uint8_t glide_565(uint16_t v, int c)
{
	switch (c) {
	case 0: return (uint8_t)(((v >> 11) & 0x1f) * 255 / 31);
	case 1: return (uint8_t)(((v >> 5) & 0x3f) * 255 / 63);
	default: return (uint8_t)((v & 0x1f) * 255 / 31);
	}
}

static int lod_of(int size) /* GR_LOD_256 0 ... GR_LOD_1 8 */
{
	int l = 0;
	for (int s = 256; s > size; s >>= 1)
		l++;
	return l;
}

static int g2_res_ok(int w, int h)
{
	return (w == 640 && h == 480) || (w == 800 && h == 600) || (w == 1024 && h == 768);
}

static int g2_open(int w, int h)
{
	if (!inited) {
		/* the wrapper's grGlideGetVersion returns nothing when it found no glidept device or the host
		 * refused its revision; every other call would then write through a null pointer */
		memset(version, 0, sizeof(version));
		g2.grGlideGetVersion(version);
		version[sizeof(version) - 1] = 0;
		if (!version[0])
			return -1;
		g2.grGlideInit();
		g2.grSstSelect(0);
		inited = 1;
	}
	int res = w == 1024 ? GR_RESOLUTION_1024x768 : w == 800 ? GR_RESOLUTION_800x600 : GR_RESOLUTION_640x480;
	if (!g2.grSstWinOpen(g2.hwnd, res, GR_REFRESH_60Hz, GR_COLORFORMAT_ARGB, GR_ORIGIN_UPPER_LEFT, 2, 1))
		return -1;
	opened = 1;
	read_w = w;
	g2.grDepthBufferMode(GR_DEPTHBUFFER_WBUFFER);
	g2.grCullMode(GR_CULL_DISABLE);
	g2.grTexCombine(GR_TMU0, GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, 0, 0);
	tex_next = g2.grTexMinAddress(GR_TMU0);
	tex_max = g2.grTexMaxAddress(GR_TMU0);
	for (int i = 0; i < TEX_COUNT; i++)
		tex[i].loaded = 0;
	fog_start = fog_end = -1;
	return 0;
}

static void g2_close(int final)
{
	if (opened)
		g2.grSstWinClose();
	opened = 0;
	if (final && inited)
		g2.grGlideShutdown();
	if (final)
		inited = 0;
}

static const char *g2_version(void)
{
	return version;
}

static void g2_clear(uint32_t rgb)
{
	g2.grDepthMask(1); /* grBufferClear leaves the depth buffer alone while depth writes are off */
	g2.grBufferClear(rgb | 0xff000000U, 0, GR_WDEPTHVALUE_FARTHEST);
}

static void g2_tex_load(int id, int size, int levels, const uint32_t *argb, int alpha)
{
	uint32_t n = 0;
	for (int s = size, l = 0; l < levels; l++, s >>= 1)
		n += (uint32_t)(s * s);
	glide_convert(argb, n, alpha, texbuf);
	GrTexInfo *ti = &tex[id].info;
	ti->large_lod = lod_of(size);
	ti->small_lod = lod_of(size >> (levels - 1));
	ti->aspect = 3; /* GR_ASPECT_1x1 */
	ti->format = alpha ? GR_TEXFMT_ARGB_4444 : GR_TEXFMT_RGB_565;
	ti->data = texbuf;
	if (!tex[id].loaded) {
		tex[id].bytes = g2.grTexTextureMemRequired(GR_MIPMAPLEVELMASK_BOTH, ti);
		tex[id].addr = (tex_next + 7) & ~7U;
		tex_next = tex[id].addr + tex[id].bytes;
		if (tex_next > tex_max)
			demo_log("INFO Glide 2: texture %d at 0x%x past the texture memory's end 0x%x", id, tex[id].addr, tex_max);
		tex[id].loaded = 1;
	}
	tex[id].size = size, tex[id].levels = levels, tex[id].alpha = alpha;
	g2.grTexDownloadMipMap(GR_TMU0, tex[id].addr, GR_MIPMAPLEVELMASK_BOTH, ti);
}

static void g2_tex_update(int id, const uint32_t *argb)
{
	g2_tex_load(id, tex[id].size, 1, argb, tex[id].alpha);
}

static void g2_state(const struct rstate *s)
{
	if (s->tex >= 0) {
		g2.grTexSource(GR_TMU0, tex[s->tex].addr, GR_MIPMAPLEVELMASK_BOTH, &tex[s->tex].info);
		int f = s->filter ? GR_TEXTUREFILTER_BILINEAR : GR_TEXTUREFILTER_POINT_SAMPLED;
		g2.grTexFilterMode(GR_TMU0, f, f);
		g2.grTexMipMapMode(GR_TMU0, s->filter && tex[s->tex].levels > 1 ? GR_MIPMAP_NEAREST : GR_MIPMAP_DISABLE, 0);
		int c = s->clamp ? GR_TEXTURECLAMP_CLAMP : GR_TEXTURECLAMP_WRAP;
		g2.grTexClampMode(GR_TMU0, c, c);
		/* colour and alpha: the texture's times the vertex's */
		g2.grColorCombine(GR_COMBINE_FUNCTION_SCALE_OTHER, GR_COMBINE_FACTOR_LOCAL, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_TEXTURE, 0);
		g2.grAlphaCombine(GR_COMBINE_FUNCTION_SCALE_OTHER, GR_COMBINE_FACTOR_LOCAL, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_TEXTURE, 0);
	} else {
		g2.grColorCombine(GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_CONSTANT, 0);
		g2.grAlphaCombine(GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_ZERO, GR_COMBINE_LOCAL_ITERATED, GR_COMBINE_OTHER_CONSTANT, 0);
	}
	if (s->blend == BLEND_ALPHA)
		g2.grAlphaBlendFunction(GR_BLEND_SRC_ALPHA, GR_BLEND_ONE_MINUS_SRC_ALPHA, GR_BLEND_ONE, GR_BLEND_ZERO);
	else if (s->blend == BLEND_ADD)
		g2.grAlphaBlendFunction(GR_BLEND_SRC_ALPHA, GR_BLEND_ONE, GR_BLEND_ONE, GR_BLEND_ZERO);
	else
		g2.grAlphaBlendFunction(GR_BLEND_ONE, GR_BLEND_ZERO, GR_BLEND_ONE, GR_BLEND_ZERO);
	g2.grDepthBufferFunction(s->depth ? GR_CMP_LESS : GR_CMP_ALWAYS);
	g2.grDepthMask(s->depth);
	g2.grFogMode(s->fog ? GR_FOG_WITH_TABLE : GR_FOG_DISABLE);
}

static void g2_fog(float start, float end, uint32_t rgb)
{
	if (start == fog_start && end == fog_end && rgb == fog_rgb)
		return;
	static uint8_t table[64];
	glide_fog_table(start, end, table, 64);
	g2.grFogTable(table);
	g2.grFogColorValue(rgb | 0xff000000U);
	fog_start = start, fog_end = end, fog_rgb = rgb;
}

static void g2_tris(const struct dvtx *v, int n)
{
	GrVertex g[3];
	memset(g, 0, sizeof(g));
	for (int i = 0; i + 2 < n; i += 3) {
		for (int k = 0; k < 3; k++) {
			const struct dvtx *d = &v[i + k];
			GrVertex *o = &g[k];
			o->x = d->x, o->y = d->y;
			o->r = d->r, o->g = d->g, o->b = d->b, o->a = d->a;
			o->oow = d->oow;
			/* texture coordinates span 0..256 across a square texture, divided by w */
			o->tmuvtx[0].sow = d->s * 256 * d->oow;
			o->tmuvtx[0].tow = d->t * 256 * d->oow;
			o->tmuvtx[0].oow = d->oow;
		}
		g2.grDrawTriangle(&g[0], &g[1], &g[2]);
	}
}

static void g2_swap(int vsync)
{
	g2.grBufferSwap(vsync ? 1 : 0);
}

static int g2_read(void)
{
	uint16_t px;
	g2.grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, 1, 1, 2, &px); /* drains the queued calls */
	return g2.grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, (uint32_t)demo_view.w, (uint32_t)demo_view.h,
				  (uint32_t)demo_view.w * 2, lfb) != 0;
}

static void g2_pixel(int x, int y, uint8_t rgb[3])
{
	uint16_t v = lfb[y * read_w + x];
	for (int c = 0; c < 3; c++)
		rgb[c] = glide_565(v, c);
}

static int g2_gamma(float g)
{
	g2.grGammaCorrectionValue(g);
	return 1;
}

const struct backend glide2_backend = {
	"Glide 2", g2_open, g2_close, g2_version, g2_clear, g2_tex_load, g2_tex_update, g2_state, g2_fog,
	g2_tris, g2_swap, g2_read, g2_pixel, g2_gamma, g2_res_ok,
};
