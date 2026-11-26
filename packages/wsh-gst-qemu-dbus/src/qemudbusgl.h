/*
 * Reading a dmabuf that can't be mapped (a GPU's tiled layout, NVIDIA's block-linear) through EGL:
 * the dmabuf imported as an EGLImage (EGL_EXT_image_dma_buf_import, with its modifier), drawn
 * into an RGBA framebuffer and read back with glReadPixels. qemudbussrc uses it for the console's
 * dmabufs of -display dbus,gl=on on a GPU node.
 *
 * Not thread-safe: one caller at a time. The context is made current for each call and released
 * after it, so the calls may come from any thread (the D-Bus thread, then stop's thread).
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifndef QEMUDBUSGL_H
#define QEMUDBUSGL_H

#include <glib.h>

G_BEGIN_DECLS

typedef struct _QemuDBusGL QemuDBusGL;

/*
 * An EGL display and a GLES 2 context: the EGL device of render_node (a path such as
 * /dev/dri/renderD128), or with NULL the first device with a render node, else a software device
 * (Mesa's llvmpipe), else Mesa's surfaceless platform. NULL with error set when there is none.
 */
QemuDBusGL *qemudbus_gl_new (const gchar * render_node, GError ** error);
void qemudbus_gl_free (QemuDBusGL * gl);
/* the device and the GL renderer, for the log */
const gchar *qemudbus_gl_describe (QemuDBusGL * gl);

/*
 * Imports a dmabuf (one plane), replacing the image before; the fd stays the caller's. fourcc is
 * a DRM fourcc, modifier a DRM format modifier (DRM_FORMAT_MOD_INVALID: the driver's implicit
 * layout).
 */
gboolean qemudbus_gl_import (QemuDBusGL * gl, int fd, guint width, guint height, guint stride,
    guint32 fourcc, guint64 modifier, GError ** error);
/*
 * Reads rows y .. y + h of the imported image into dst as BGRA bytes (B, G, R, A in memory; the
 * dmabuf's own channel order doesn't matter), width * 4 bytes a row, row r of the image at
 * dst + r * width * 4. Rows in the dmabuf's memory order.
 */
gboolean qemudbus_gl_read (QemuDBusGL * gl, guint y, guint h, guint8 * dst, GError ** error);

G_END_DECLS

#endif
