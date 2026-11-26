/*
 * Glide 3 entry points for wshkeep (DOS GLIDE3X.DXE and Windows GLIDE3X.DLL).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_KEEP_GLIDE3_H
#define WSH_KEEP_GLIDE3_H

#include <stdint.h>

#include "glide2.h"

#define GLIDE3_FUNCS(X)                                                                                         \
	X(void, grGlideInit, (void), 0)                                                                        \
	X(void, grGlideShutdown, (void), 0)                                                                    \
	X(void, grSstSelect, (int which), 4)                                                                   \
	X(uint32_t, grSstWinOpen, (uint32_t hwnd, int res, int refresh, int cformat, int origin, int ncol, int naux), 28) \
	X(int, grSstWinClose, (uint32_t context), 4)                                                           \
	X(const char *, grGetString, (uint32_t pname), 4)                                                      \
	X(uint32_t, grGet, (uint32_t pname, uint32_t size, int32_t *params), 12)                               \
	X(void, grVertexLayout, (uint32_t param, int32_t offset, uint32_t mode), 12)                           \
	X(void, grCoordinateSpace, (uint32_t mode), 4)                                                         \
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
	X(void, guGammaCorrectionRGB, (float r, float g, float b), 12)                                         \
	X(void, grCullMode, (int mode), 4)

#define GLIDE3_MEMBER(ret, name, args, bytes) ret(GCALL *name) args;
struct glide3_api {
	GLIDE3_FUNCS(GLIDE3_MEMBER)
	uint32_t hwnd;
};
extern struct glide3_api g3;
extern const struct backend glide3_backend;

#define GR_PARAM_XY 0x01
#define GR_PARAM_Q 0x04
#define GR_PARAM_A 0x10
#define GR_PARAM_RGB 0x20
#define GR_PARAM_ST0 0x40
#define GR_PARAM_ENABLE 0x01
#define GR_WINDOW_COORDS 0x00
#define GR_FOG_TABLE_ENTRIES 0x04
#define GR_VERSION 0xa4
#define GR_RENDERER 0xa2

void glide_fog_table(float start, float end, uint8_t *table, int n);
void glide_convert(const uint32_t *argb, uint32_t n, int alpha, uint16_t *dst);
uint8_t glide_565(uint16_t v, int c);

#endif
