/*
 * Glide 2 entry points for wshracer, filled dynamically or by import stubs by each platform front
 * end (Linux libglide.so.2, DOS GLIDE2X.DXE, Windows GLIDE2X.DLL).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_RACER_GLIDE2_H
#define WSH_RACER_GLIDE2_H

#include <stdint.h>

#ifdef _WIN32
#define GCALL __stdcall
#else
#define GCALL
#endif

#define GLIDE2_FUNCS(X)                                                                                         \
	X(void, grGlideInit, (void), 0)                                                                        \
	X(void, grGlideShutdown, (void), 0)                                                                    \
	X(void, grGlideGetVersion, (char *version), 4)                                                         \
	X(void, grSstSelect, (int which), 4)                                                                   \
	X(uint32_t, grSstWinOpen, (uint32_t hwnd, int res, int refresh, int cformat, int origin, int ncol, int naux), 28) \
	X(void, grSstWinClose, (void), 0)                                                                      \
	X(void, grBufferClear, (uint32_t color, uint32_t alpha, uint32_t depth), 12)                           \
	X(void, grBufferSwap, (int interval), 4)                                                               \
	X(void, grDrawTriangle, (const void *a, const void *b, const void *c), 12)                             \
	X(uint32_t, grLfbReadRegion, (int buf, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t stride, void *dst), 28) \
	X(void, grColorCombine, (int func, int factor, int local, int other, int invert), 20)                  \
	X(void, grAlphaCombine, (int func, int factor, int local, int other, int invert), 20)                  \
	X(void, grAlphaBlendFunction, (int rgb_sf, int rgb_df, int a_sf, int a_df), 16)                        \
	X(void, grTexCombine, (int tmu, int rgb_func, int rgb_factor, int a_func, int a_factor, int rgb_inv, int a_inv), 28) \
	X(void, grTexFilterMode, (int tmu, int minf, int magf), 12)                                            \
	X(void, grTexMipMapMode, (int tmu, int mode, int blend), 12)                                           \
	X(void, grTexClampMode, (int tmu, int s, int t), 12)                                                   \
	X(void, grTexSource, (int tmu, uint32_t addr, int even_odd, const void *info), 16)                     \
	X(void, grTexDownloadMipMap, (int tmu, uint32_t addr, int even_odd, const void *info), 16)             \
	X(uint32_t, grTexMinAddress, (int tmu), 4)                                                             \
	X(uint32_t, grTexMaxAddress, (int tmu), 4)                                                             \
	X(uint32_t, grTexTextureMemRequired, (int even_odd, const void *info), 8)                              \
	X(void, grDepthBufferMode, (int mode), 4)                                                              \
	X(void, grDepthBufferFunction, (int func), 4)                                                          \
	X(void, grDepthMask, (int on), 4)                                                                      \
	X(void, grFogMode, (int mode), 4)                                                                      \
	X(void, grFogColorValue, (uint32_t color), 4)                                                          \
	X(void, grFogTable, (const uint8_t *table), 4)                                                         \
	X(void, grGammaCorrectionValue, (float gamma), 4)                                                      \
	X(void, grCullMode, (int mode), 4)

#define GLIDE2_MEMBER(ret, name, args, bytes) ret(GCALL *name) args;
struct glide2_api {
	GLIDE2_FUNCS(GLIDE2_MEMBER)
	uint32_t hwnd;
};
extern struct glide2_api g2;
extern const struct backend glide2_backend;

#define GR_RESOLUTION_640x480 0x7
#define GR_RESOLUTION_800x600 0x8
#define GR_RESOLUTION_960x720 0x9
#define GR_RESOLUTION_856x480 0xa
#define GR_RESOLUTION_1024x768 0xc
#define GR_RESOLUTION_1280x1024 0xd
#define GR_RESOLUTION_1600x1200 0xe
#define GR_REFRESH_60Hz 0x0
#define GR_COLORFORMAT_ARGB 0x0
#define GR_ORIGIN_UPPER_LEFT 0x0
#define GR_BUFFER_FRONTBUFFER 0x0
#define GR_BUFFER_BACKBUFFER 0x1
#define GR_TMU0 0x0
#define GR_COMBINE_FUNCTION_ZERO 0x0
#define GR_COMBINE_FUNCTION_LOCAL 0x1
#define GR_COMBINE_FUNCTION_SCALE_OTHER 0x3
#define GR_COMBINE_FACTOR_ZERO 0x0
#define GR_COMBINE_FACTOR_LOCAL 0x1
#define GR_COMBINE_LOCAL_ITERATED 0x0
#define GR_COMBINE_OTHER_TEXTURE 0x1
#define GR_COMBINE_OTHER_CONSTANT 0x2
#define GR_BLEND_ZERO 0x0
#define GR_BLEND_SRC_ALPHA 0x1
#define GR_BLEND_ONE 0x4
#define GR_BLEND_ONE_MINUS_SRC_ALPHA 0x5
#define GR_TEXTUREFILTER_POINT_SAMPLED 0x0
#define GR_TEXTUREFILTER_BILINEAR 0x1
#define GR_MIPMAP_DISABLE 0x0
#define GR_MIPMAP_NEAREST 0x1
#define GR_TEXTURECLAMP_WRAP 0x0
#define GR_TEXTURECLAMP_CLAMP 0x1
#define GR_MIPMAPLEVELMASK_BOTH 0x3
#define GR_TEXFMT_RGB_565 0xa
#define GR_TEXFMT_ARGB_4444 0xc
#define GR_DEPTHBUFFER_WBUFFER 0x2
#define GR_CMP_LESS 0x1
#define GR_CMP_LEQUAL 0x3
#define GR_CMP_ALWAYS 0x7
#define GR_FOG_DISABLE 0x0
#define GR_FOG_WITH_TABLE 0x2
#define GR_CULL_DISABLE 0x0
#define GR_WDEPTHVALUE_FARTHEST 0xffff

#define GLIDE_MAX_PIXELS (1600 * 1200)
int glide_res(int w, int h);

#endif
