/*
 * Reading a dmabuf through EGL (qemudbusgl.h).
 *
 * The display: EGL_EXT_platform_device, so no window system and no GBM: the EGL device whose render
 * node is the one asked for, or the first with a render node (a GPU), or a software device (Mesa's
 * llvmpipe, EGL_MESA_device_software), or Mesa's surfaceless platform. A GLES 2 context without a
 * surface (EGL_KHR_surfaceless_context). Each imported dmabuf is an EGLImage bound to an external
 * texture (GL_OES_EGL_image_external, so a layout the driver can only sample, not render to, works
 * too), drawn 1:1 with GL_NEAREST into an RGBA texture of the same size, red and blue swapped
 * (so the bytes read back are B, G, R, A: GStreamer's BGRx, the console's usual format, which
 * downstream converts fastest), and read back with glReadPixels, which waits for the draw. GL_NEAREST at the texels' centres gives the pixels as
 * they are; only the rows asked for are drawn (scissor) and read.
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#include "qemudbusgl.h"

#include <gio/gio.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <string.h>
#include <sys/stat.h>

#define DRM_FORMAT_MOD_LINEAR 0ULL
#define DRM_FORMAT_MOD_INVALID 0x00ffffffffffffffULL

#ifndef EGL_DRM_RENDER_NODE_FILE_EXT
#define EGL_DRM_RENDER_NODE_FILE_EXT 0x3377
#endif
#ifndef EGL_PLATFORM_SURFACELESS_MESA
#define EGL_PLATFORM_SURFACELESS_MESA 0x31DD
#endif

struct _QemuDBusGL
{
  EGLDisplay dpy;
  EGLContext ctx;
  gchar *description;
  gboolean modifiers;           /* EGL_EXT_image_dma_buf_import_modifiers */

  PFNEGLCREATEIMAGEKHRPROC create_image;
  PFNEGLDESTROYIMAGEKHRPROC destroy_image;
  PFNGLEGLIMAGETARGETTEXTURE2DOESPROC image_target_texture;

  GLuint program, vbo, fbo, target, source;
  GLint pos_attr;
  EGLImageKHR image;
  guint width, height;          /* of the image, and of the target texture */
  guint target_width, target_height;
};

static const char vertex_shader[] =
    "attribute vec2 pos;\n"
    "varying vec2 tc;\n"
    "void main () {\n" "  tc = pos * 0.5 + 0.5;\n" "  gl_Position = vec4 (pos, 0.0, 1.0);\n" "}\n";

static const char fragment_shader[] =
    "#extension GL_OES_EGL_image_external : require\n"
    "#ifdef GL_FRAGMENT_PRECISION_HIGH\n"
    "precision highp float;\n"
    "#else\n"
    "precision mediump float;\n"
    "#endif\n"
    "uniform samplerExternalOES tex;\n"
    "varying vec2 tc;\n" "void main () {\n" "  gl_FragColor = texture2D (tex, tc).bgra;\n" "}\n";

static gboolean
has_extension (const char *list, const char *name)
{
  gsize len = strlen (name);
  const char *p = list;

  while (p && (p = strstr (p, name))) {
    if ((p == list || p[-1] == ' ') && (p[len] == ' ' || p[len] == '\0'))
      return TRUE;
    p += len;
  }
  return FALSE;
}

static gboolean
same_node (const char *a, const char *b)
{
  struct stat sa, sb;

  if (!a || !b)
    return FALSE;
  if (!strcmp (a, b))
    return TRUE;
  return stat (a, &sa) == 0 && stat (b, &sb) == 0 && S_ISCHR (sa.st_mode)
      && sa.st_rdev == sb.st_rdev;
}

/* The display of an EGL device: the render node asked for, else the first GPU, else software */
static EGLDisplay
device_display (const gchar * render_node, gchar ** description)
{
  const char *client = eglQueryString (EGL_NO_DISPLAY, EGL_EXTENSIONS);
  PFNEGLQUERYDEVICESEXTPROC query_devices;
  PFNEGLQUERYDEVICESTRINGEXTPROC query_device_string;
  PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform_display;
  EGLDeviceEXT devices[16], gpu = NULL, software = NULL;
  const char *gpu_node = NULL;
  EGLint n = 0, i;

  if (!client || !has_extension (client, "EGL_EXT_platform_device")
      || !has_extension (client, "EGL_EXT_device_enumeration"))
    return EGL_NO_DISPLAY;
  query_devices = (PFNEGLQUERYDEVICESEXTPROC) eglGetProcAddress ("eglQueryDevicesEXT");
  query_device_string =
      (PFNEGLQUERYDEVICESTRINGEXTPROC) eglGetProcAddress ("eglQueryDeviceStringEXT");
  get_platform_display =
      (PFNEGLGETPLATFORMDISPLAYEXTPROC) eglGetProcAddress ("eglGetPlatformDisplayEXT");
  if (!query_devices || !query_device_string || !get_platform_display
      || !query_devices (G_N_ELEMENTS (devices), devices, &n))
    return EGL_NO_DISPLAY;
  for (i = 0; i < n; i++) {
    const char *exts = query_device_string (devices[i], EGL_EXTENSIONS);
    const char *node = NULL;

    if (exts && has_extension (exts, "EGL_EXT_device_drm_render_node"))
      node = query_device_string (devices[i], EGL_DRM_RENDER_NODE_FILE_EXT);
    if (node && *node) {
      if (render_node ? same_node (node, render_node) : !gpu) {
        gpu = devices[i];
        gpu_node = node;
      }
    } else if (exts && has_extension (exts, "EGL_MESA_device_software") && !software) {
      software = devices[i];
    }
  }
  if (gpu) {
    *description = g_strdup_printf ("EGL device %s", gpu_node);
    return get_platform_display (EGL_PLATFORM_DEVICE_EXT, gpu, NULL);
  }
  if (software && !render_node) {
    *description = g_strdup ("EGL software device");
    return get_platform_display (EGL_PLATFORM_DEVICE_EXT, software, NULL);
  }
  return EGL_NO_DISPLAY;
}

static GLuint
compile (GLenum type, const char *source, GError ** error)
{
  GLuint shader = glCreateShader (type);
  GLint ok = 0;

  glShaderSource (shader, 1, &source, NULL);
  glCompileShader (shader);
  glGetShaderiv (shader, GL_COMPILE_STATUS, &ok);
  if (!ok) {
    char log[512] = "";

    glGetShaderInfoLog (shader, sizeof log, NULL, log);
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "shader: %s", log);
    glDeleteShader (shader);
    return 0;
  }
  return shader;
}

static gboolean
make_current (QemuDBusGL * gl, GError ** error)
{
  if (!eglMakeCurrent (gl->dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, gl->ctx)) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "eglMakeCurrent: 0x%x", eglGetError ());
    return FALSE;
  }
  return TRUE;
}

static void
release_current (QemuDBusGL * gl)
{
  eglMakeCurrent (gl->dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
}

static gboolean
setup_gl (QemuDBusGL * gl, GError ** error)
{
  static const GLfloat quad[] = { -1, -1, 1, -1, -1, 1, 1, 1 };
  const char *exts = (const char *) glGetString (GL_EXTENSIONS);
  GLuint vs, fs;
  GLint ok = 0;

  if (!exts || !has_extension (exts, "GL_OES_EGL_image_external")) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
        "the GL context has no GL_OES_EGL_image_external");
    return FALSE;
  }
  vs = compile (GL_VERTEX_SHADER, vertex_shader, error);
  if (!vs)
    return FALSE;
  fs = compile (GL_FRAGMENT_SHADER, fragment_shader, error);
  if (!fs) {
    glDeleteShader (vs);
    return FALSE;
  }
  gl->program = glCreateProgram ();
  glAttachShader (gl->program, vs);
  glAttachShader (gl->program, fs);
  glBindAttribLocation (gl->program, 0, "pos");
  glLinkProgram (gl->program);
  glDeleteShader (vs);
  glDeleteShader (fs);
  glGetProgramiv (gl->program, GL_LINK_STATUS, &ok);
  if (!ok) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "the shader program doesn't link");
    return FALSE;
  }
  gl->pos_attr = 0;
  glUseProgram (gl->program);
  glUniform1i (glGetUniformLocation (gl->program, "tex"), 0);
  glGenBuffers (1, &gl->vbo);
  glBindBuffer (GL_ARRAY_BUFFER, gl->vbo);
  glBufferData (GL_ARRAY_BUFFER, sizeof quad, quad, GL_STATIC_DRAW);
  glGenTextures (1, &gl->source);
  glGenTextures (1, &gl->target);
  glGenFramebuffers (1, &gl->fbo);
  glPixelStorei (GL_PACK_ALIGNMENT, 4);
  return TRUE;
}

QemuDBusGL *
qemudbus_gl_new (const gchar * render_node, GError ** error)
{
  QemuDBusGL *gl = g_new0 (QemuDBusGL, 1);
  const char *exts, *renderer;
  EGLint major, minor;
  EGLint ctx_attrs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
  EGLConfig config = NULL;
  gchar *where = NULL;

  gl->dpy = device_display (render_node, &where);
  if (gl->dpy == EGL_NO_DISPLAY && !render_node) {
    const char *client = eglQueryString (EGL_NO_DISPLAY, EGL_EXTENSIONS);

    if (client && has_extension (client, "EGL_MESA_platform_surfaceless")) {
      PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform_display =
          (PFNEGLGETPLATFORMDISPLAYEXTPROC) eglGetProcAddress ("eglGetPlatformDisplayEXT");

      if (get_platform_display) {
        gl->dpy = get_platform_display (EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
        where = g_strdup ("EGL surfaceless platform");
      }
    }
  }
  if (gl->dpy == EGL_NO_DISPLAY) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND, "no EGL device%s%s",
        render_node ? " for " : "", render_node ? render_node : "");
    goto fail;
  }
  if (!eglInitialize (gl->dpy, &major, &minor)) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "eglInitialize (%s): 0x%x", where,
        eglGetError ());
    gl->dpy = EGL_NO_DISPLAY;
    goto fail;
  }
  exts = eglQueryString (gl->dpy, EGL_EXTENSIONS);
  if (!has_extension (exts, "EGL_EXT_image_dma_buf_import")
      || !has_extension (exts, "EGL_KHR_surfaceless_context")) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
        "%s: no EGL_EXT_image_dma_buf_import or EGL_KHR_surfaceless_context", where);
    goto fail;
  }
  gl->modifiers = has_extension (exts, "EGL_EXT_image_dma_buf_import_modifiers");
  gl->create_image = (PFNEGLCREATEIMAGEKHRPROC) eglGetProcAddress ("eglCreateImageKHR");
  gl->destroy_image = (PFNEGLDESTROYIMAGEKHRPROC) eglGetProcAddress ("eglDestroyImageKHR");
  gl->image_target_texture = (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)
      eglGetProcAddress ("glEGLImageTargetTexture2DOES");
  if (!gl->create_image || !gl->destroy_image || !gl->image_target_texture) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "%s: no EGLImage functions",
        where);
    goto fail;
  }
  if (!eglBindAPI (EGL_OPENGL_ES_API)) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "%s: no OpenGL ES", where);
    goto fail;
  }
  if (!has_extension (exts, "EGL_KHR_no_config_context")) {
    EGLint attrs[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE };
    EGLint n = 0;

    if (!eglChooseConfig (gl->dpy, attrs, &config, 1, &n) || n < 1) {
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "%s: no GLES 2 config", where);
      goto fail;
    }
  }
  gl->ctx = eglCreateContext (gl->dpy, config, EGL_NO_CONTEXT, ctx_attrs);
  if (gl->ctx == EGL_NO_CONTEXT) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "%s: eglCreateContext: 0x%x", where,
        eglGetError ());
    goto fail;
  }
  if (!make_current (gl, error))
    goto fail;
  if (!setup_gl (gl, error)) {
    release_current (gl);
    goto fail;
  }
  renderer = (const char *) glGetString (GL_RENDERER);
  gl->description = g_strdup_printf ("%s, EGL %d.%d (%s), GL renderer %s%s", where, major,
      minor, eglQueryString (gl->dpy, EGL_VENDOR), renderer ? renderer : "?",
      gl->modifiers ? "" : ", no modifiers");
  release_current (gl);
  g_free (where);
  return gl;

fail:
  g_free (where);
  qemudbus_gl_free (gl);
  return NULL;
}

void
qemudbus_gl_free (QemuDBusGL * gl)
{
  if (!gl)
    return;
  if (gl->dpy != EGL_NO_DISPLAY) {
    if (gl->ctx != EGL_NO_CONTEXT && make_current (gl, NULL)) {
      if (gl->program)
        glDeleteProgram (gl->program);
      if (gl->vbo)
        glDeleteBuffers (1, &gl->vbo);
      if (gl->fbo)
        glDeleteFramebuffers (1, &gl->fbo);
      if (gl->source)
        glDeleteTextures (1, &gl->source);
      if (gl->target)
        glDeleteTextures (1, &gl->target);
      release_current (gl);
    }
    if (gl->image != EGL_NO_IMAGE_KHR)
      gl->destroy_image (gl->dpy, gl->image);
    if (gl->ctx != EGL_NO_CONTEXT)
      eglDestroyContext (gl->dpy, gl->ctx);
    /* not eglTerminate: the display is shared by every user of this device in the process */
  }
  g_free (gl->description);
  g_free (gl);
}

const gchar *
qemudbus_gl_describe (QemuDBusGL * gl)
{
  return gl->description;
}

gboolean
qemudbus_gl_import (QemuDBusGL * gl, int fd, guint width, guint height, guint stride,
    guint32 fourcc, guint64 modifier, GError ** error)
{
  EGLint attrs[32];
  int n = 0;
  EGLImageKHR image;
  GLenum err;

  if (modifier != DRM_FORMAT_MOD_INVALID && modifier != DRM_FORMAT_MOD_LINEAR && !gl->modifiers) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
        "modifier 0x%" G_GINT64_MODIFIER "x, but EGL can't import modifiers", modifier);
    return FALSE;
  }
  attrs[n++] = EGL_WIDTH;
  attrs[n++] = width;
  attrs[n++] = EGL_HEIGHT;
  attrs[n++] = height;
  attrs[n++] = EGL_LINUX_DRM_FOURCC_EXT;
  attrs[n++] = fourcc;
  attrs[n++] = EGL_DMA_BUF_PLANE0_FD_EXT;
  attrs[n++] = fd;
  attrs[n++] = EGL_DMA_BUF_PLANE0_OFFSET_EXT;
  attrs[n++] = 0;
  attrs[n++] = EGL_DMA_BUF_PLANE0_PITCH_EXT;
  attrs[n++] = stride;
  if (modifier != DRM_FORMAT_MOD_INVALID && gl->modifiers) {
    attrs[n++] = EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT;
    attrs[n++] = (EGLint) (modifier & 0xffffffff);
    attrs[n++] = EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT;
    attrs[n++] = (EGLint) (modifier >> 32);
  }
  attrs[n++] = EGL_NONE;

  if (!make_current (gl, error))
    return FALSE;
  image = gl->create_image (gl->dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, attrs);
  if (image == EGL_NO_IMAGE_KHR) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "eglCreateImageKHR: 0x%x",
        eglGetError ());
    release_current (gl);
    return FALSE;
  }
  glBindTexture (GL_TEXTURE_EXTERNAL_OES, gl->source);
  glTexParameteri (GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
  glTexParameteri (GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
  glTexParameteri (GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
  glTexParameteri (GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
  gl->image_target_texture (GL_TEXTURE_EXTERNAL_OES, (GLeglImageOES) image);
  if (gl->image != EGL_NO_IMAGE_KHR)
    gl->destroy_image (gl->dpy, gl->image);
  gl->image = image;
  gl->width = width;
  gl->height = height;
  if (gl->target_width != width || gl->target_height != height) {
    glBindTexture (GL_TEXTURE_2D, gl->target);
    glTexImage2D (GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glBindFramebuffer (GL_FRAMEBUFFER, gl->fbo);
    glFramebufferTexture2D (GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, gl->target, 0);
    gl->target_width = width;
    gl->target_height = height;
    if (glCheckFramebufferStatus (GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "%ux%u RGBA framebuffer incomplete",
          width, height);
      gl->target_width = gl->target_height = 0;
      release_current (gl);
      return FALSE;
    }
  }
  err = glGetError ();
  release_current (gl);
  if (err != GL_NO_ERROR) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "binding the image: GL error 0x%x", err);
    return FALSE;
  }
  return TRUE;
}

gboolean
qemudbus_gl_read (QemuDBusGL * gl, guint y, guint h, guint8 * dst, GError ** error)
{
  GLenum err;

  if (gl->image == EGL_NO_IMAGE_KHR || !h || y + h > gl->height) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT, "nothing to read");
    return FALSE;
  }
  if (!make_current (gl, error))
    return FALSE;
  glBindFramebuffer (GL_FRAMEBUFFER, gl->fbo);
  glViewport (0, 0, gl->width, gl->height);
  glEnable (GL_SCISSOR_TEST);
  glScissor (0, y, gl->width, h);
  glDisable (GL_BLEND);
  glUseProgram (gl->program);
  glActiveTexture (GL_TEXTURE0);
  glBindTexture (GL_TEXTURE_EXTERNAL_OES, gl->source);
  /* the texture again from the image, so the driver drops what it may have cached of the buffer,
   * which QEMU has drawn into since */
  gl->image_target_texture (GL_TEXTURE_EXTERNAL_OES, (GLeglImageOES) gl->image);
  glBindBuffer (GL_ARRAY_BUFFER, gl->vbo);
  glEnableVertexAttribArray (gl->pos_attr);
  glVertexAttribPointer (gl->pos_attr, 2, GL_FLOAT, GL_FALSE, 0, NULL);
  /* texture row r (the dmabuf's memory row r) lands in framebuffer row r, which glReadPixels
   * returns as row r */
  glDrawArrays (GL_TRIANGLE_STRIP, 0, 4);
  glReadPixels (0, y, gl->width, h, GL_RGBA, GL_UNSIGNED_BYTE, dst + (gsize) y * gl->width * 4);
  err = glGetError ();
  release_current (gl);
  if (err != GL_NO_ERROR) {
    g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED, "reading the image: GL error 0x%x", err);
    return FALSE;
  }
  return TRUE;
}
