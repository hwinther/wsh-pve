/*
 * OpenGL 1.1 entry points for wshkeep (Windows OPENGL32.DLL and host plat_egl.c).
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_KEEP_GL11_H
#define WSH_KEEP_GL11_H

#include <stdint.h>

#ifdef _WIN32
#define GLCALL __stdcall
#else
#define GLCALL
#endif

#define GL_FUNCS(X)                                                                                         \
	X(void, glViewport, (int x, int y, int w, int h))                                                  \
	X(void, glClearColor, (float r, float g, float b, float a))                                        \
	X(void, glClearDepth, (double d))                                                                  \
	X(void, glClear, (unsigned mask))                                                                  \
	X(void, glBegin, (unsigned mode))                                                                  \
	X(void, glEnd, (void))                                                                             \
	X(void, glColor4f, (float r, float g, float b, float a))                                           \
	X(void, glTexCoord2f, (float s, float t))                                                          \
	X(void, glVertex2f, (float x, float y))                                                            \
	X(void, glVertex3f, (float x, float y, float z))                                                   \
	X(void, glMatrixMode, (unsigned mode))                                                             \
	X(void, glLoadIdentity, (void))                                                                    \
	X(void, glOrtho, (double l, double r, double b, double t, double n, double f))                     \
	X(void, glFrustum, (double l, double r, double b, double t, double n, double f))                   \
	X(void, glEnable, (unsigned cap))                                                                  \
	X(void, glDisable, (unsigned cap))                                                                 \
	X(void, glBlendFunc, (unsigned s, unsigned d))                                                     \
	X(void, glDepthFunc, (unsigned f))                                                                 \
	X(void, glDepthMask, (unsigned char on))                                                           \
	X(void, glShadeModel, (unsigned mode))                                                             \
	X(void, glHint, (unsigned target, unsigned mode))                                                  \
	X(void, glFogi, (unsigned pname, int v))                                                           \
	X(void, glFogf, (unsigned pname, float v))                                                         \
	X(void, glFogfv, (unsigned pname, const float *v))                                                 \
	X(void, glGenTextures, (int n, unsigned *names))                                                   \
	X(void, glDeleteTextures, (int n, const unsigned *names))                                          \
	X(void, glBindTexture, (unsigned target, unsigned name))                                           \
	X(void, glTexImage2D, (unsigned t, int l, int ifmt, int w, int h, int b, unsigned f, unsigned ty, const void *p)) \
	X(void, glTexSubImage2D, (unsigned t, int l, int x, int y, int w, int h, unsigned f, unsigned ty, const void *p)) \
	X(void, glTexParameteri, (unsigned target, unsigned pname, int v))                                 \
	X(void, glTexEnvi, (unsigned target, unsigned pname, int v))                                       \
	X(void, glPixelStorei, (unsigned pname, int v))                                                    \
	X(void, glReadBuffer, (unsigned mode))                                                             \
	X(void, glReadPixels, (int x, int y, int w, int h, unsigned f, unsigned ty, void *p))              \
	X(void, glFinish, (void))                                                                          \
	X(const unsigned char *, glGetString, (unsigned name))

#define GL_MEMBER(ret, name, args) ret(GLCALL *name) args;
struct gl_api {
	GL_FUNCS(GL_MEMBER)
};
extern struct gl_api glf;
extern const struct backend gl_backend;

int glw_open(int w, int h);
void glw_close(int final);
void glw_swap(int vsync);
int glw_gamma(const uint16_t ramp[3][256]);

#define GL_COLOR_BUFFER_BIT 0x4000
#define GL_DEPTH_BUFFER_BIT 0x0100
#define GL_TRIANGLES 0x0004
#define GL_PROJECTION 0x1701
#define GL_MODELVIEW 0x1700
#define GL_TEXTURE_2D 0x0de1
#define GL_BLEND 0x0be2
#define GL_DEPTH_TEST 0x0b71
#define GL_FOG 0x0b60
#define GL_SRC_ALPHA 0x0302
#define GL_ONE_MINUS_SRC_ALPHA 0x0303
#define GL_ONE 0x0001
#define GL_LESS 0x0201
#define GL_LEQUAL 0x0203
#define GL_SMOOTH 0x1d01
#define GL_FOG_HINT 0x0c54
#define GL_PERSPECTIVE_CORRECTION_HINT 0x0c50
#define GL_NICEST 0x1102
#define GL_FOG_MODE 0x0b65
#define GL_FOG_START 0x0b63
#define GL_FOG_END 0x0b64
#define GL_FOG_COLOR 0x0b66
#define GL_LINEAR 0x2601
#define GL_NEAREST 0x2600
#define GL_LINEAR_MIPMAP_NEAREST 0x2701
#define GL_TEXTURE_MAG_FILTER 0x2800
#define GL_TEXTURE_MIN_FILTER 0x2801
#define GL_TEXTURE_WRAP_S 0x2802
#define GL_TEXTURE_WRAP_T 0x2803
#define GL_REPEAT 0x2901
#define GL_CLAMP_TO_EDGE 0x812f
#define GL_TEXTURE_ENV 0x2300
#define GL_TEXTURE_ENV_MODE 0x2200
#define GL_MODULATE 0x2100
#define GL_RGBA 0x1908
#define GL_UNSIGNED_BYTE 0x1401
#define GL_UNPACK_ALIGNMENT 0x0cf5
#define GL_PACK_ALIGNMENT 0x0d05
#define GL_BACK 0x0405
#define GL_VERSION 0x1f02
#define GL_RENDERER 0x1f01

#endif
