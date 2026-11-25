/*
 * qemudbussrc: the picture of a console of QEMU's D-Bus display (-display dbus) as a live video
 * source.
 *
 * The element registers a listener (org.qemu.Display1.Listener) on Console_<console> of the VM's
 * bus and keeps a copy of the console's picture, which QEMU updates through it:
 *
 *   Scanout / Update             pixels in the message (a display without GL, no shared map)
 *   ScanoutMap / UpdateMap       the console's surface in shared memory (Listener.Unix.Map,
 *                                offered unless shared-map=false); QEMU writes into it and says
 *                                which rectangle changed
 *   ScanoutDMABUF / UpdateDMABUF a dmabuf (-display dbus,gl=on: GL scanouts, and the 2D surface
 *                                uploaded to a texture). A linear dmabuf is mapped and the
 *                                changed rectangle copied out before the reply: QEMU keeps the
 *                                console gl-blocked (the guest's GL frames wait) until the
 *                                listener replies to UpdateDMABUF, so the reply goes at once.
 *                                A dmabuf with another modifier (a GPU's tiled layout) can't be
 *                                mapped: the element says so once and outputs nothing for it.
 *
 * Every change since the last buffer makes one buffer: a copy of the whole picture, in the
 * console's own format (BGRx for QEMU's usual x8r8g8b8), timestamped with the running time it was
 * taken at (a live source with a variable frame rate, framerate=0/1; videorate makes a fixed one).
 * When QEMU closes the connection (the VM stopped) the element sends EOS.
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "gstqemudbussrc.h"
#include "qemudbus.h"

#include <errno.h>
#include <gio/gunixfdlist.h>
#include <linux/dma-buf.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

GST_DEBUG_CATEGORY_STATIC (gst_qemu_dbus_src_debug);
#define GST_CAT_DEFAULT gst_qemu_dbus_src_debug

#define DRM_FORMAT_MOD_LINEAR 0ULL
#define DRM_FORMAT_MOD_INVALID 0x00ffffffffffffffULL

#define LISTENER_XML \
  "<node>" \
  " <interface name='org.qemu.Display1.Listener'>" \
  "  <method name='Scanout'>" \
  "   <arg type='u' direction='in'/><arg type='u' direction='in'/><arg type='u' direction='in'/>" \
  "   <arg type='u' direction='in'/><arg type='ay' direction='in'/>" \
  "  </method>" \
  "  <method name='Update'>" \
  "   <arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='i' direction='in'/>" \
  "   <arg type='i' direction='in'/><arg type='u' direction='in'/><arg type='u' direction='in'/>" \
  "   <arg type='ay' direction='in'/>" \
  "  </method>" \
  "  <method name='ScanoutDMABUF'>" \
  "   <arg type='h' direction='in'/><arg type='u' direction='in'/><arg type='u' direction='in'/>" \
  "   <arg type='u' direction='in'/><arg type='u' direction='in'/><arg type='t' direction='in'/>" \
  "   <arg type='b' direction='in'/>" \
  "  </method>" \
  "  <method name='UpdateDMABUF'>" \
  "   <arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='i' direction='in'/>" \
  "   <arg type='i' direction='in'/>" \
  "  </method>" \
  "  <method name='Disable'/>" \
  "  <method name='MouseSet'>" \
  "   <arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='i' direction='in'/>" \
  "  </method>" \
  "  <method name='CursorDefine'>" \
  "   <arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='i' direction='in'/>" \
  "   <arg type='i' direction='in'/><arg type='ay' direction='in'/>" \
  "  </method>" \
  "  <property name='Interfaces' type='as' access='read'/>" \
  " </interface>" \
  " <interface name='org.qemu.Display1.Listener.Unix.Map'>" \
  "  <method name='ScanoutMap'>" \
  "   <arg type='h' direction='in'/><arg type='u' direction='in'/><arg type='u' direction='in'/>" \
  "   <arg type='u' direction='in'/><arg type='u' direction='in'/><arg type='u' direction='in'/>" \
  "  </method>" \
  "  <method name='UpdateMap'>" \
  "   <arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='i' direction='in'/>" \
  "   <arg type='i' direction='in'/>" \
  "  </method>" \
  " </interface>" \
  "</node>"

enum
{
  PROP_0,
  PROP_ADDRESS,
  PROP_VMID,
  PROP_CONSOLE,
  PROP_TIMEOUT,
  PROP_SHARED_MAP,
  PROP_STATS,
};

#define DEFAULT_VMID -1
#define DEFAULT_CONSOLE 0
#define DEFAULT_TIMEOUT 10
#define DEFAULT_SHARED_MAP TRUE

#define SRC_FORMATS "{ BGRx, BGRA, RGBx, RGBA, xRGB, ARGB, BGR, RGB, RGB16, RGB15 }"

static GstStaticPadTemplate src_template = GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC, GST_PAD_ALWAYS,
    GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE (SRC_FORMATS)));

typedef enum
{
  PICTURE_NONE,                 /* nothing yet, or disabled */
  PICTURE_OWN,                  /* pixels: our copy (Scanout/Update, or read from a dmabuf) */
  PICTURE_MAP,                  /* map: QEMU's surface, shared */
} PictureKind;

struct _GstQemuDBusSrc
{
  GstPushSrc parent;

  /* properties */
  gchar *address;
  gint vmid;
  guint console;
  guint timeout;
  gboolean shared_map;

  QemuDBusPeer *peer;
  GDBusNodeInfo *node;

  GMutex lock;
  GCond cond;
  gboolean flushing;
  gboolean eos;

  /* the console's picture, under lock */
  PictureKind kind;
  GstVideoFormat format;
  guint width, height, stride;
  guint8 *pixels;
  gsize pixels_size;
  guint8 *map;                  /* the shared surface's mapping, and its length */
  gsize map_len;
  gsize map_offset;
  int dmabuf_fd;                /* the current dmabuf, mapped if linear */
  guint8 *dmabuf;
  gsize dmabuf_len;
  guint dmabuf_stride;
  gboolean dmabuf_flip;
  gboolean dirty;

  /* what was negotiated */
  GstVideoInfo info;
  gboolean have_info;

  /* counters (under lock) */
  guint64 n_scanout, n_update, n_map_scanout, n_map_update, n_dmabuf_scanout, n_dmabuf_update;
  guint64 n_dmabuf_unmapped, n_frames;
  gint64 dmabuf_us_total, dmabuf_us_max;        /* UpdateDMABUF: from its arrival to the reply */
  gboolean warned_modifier;
};

#define gst_qemu_dbus_src_parent_class parent_class
G_DEFINE_TYPE (GstQemuDBusSrc, gst_qemu_dbus_src, GST_TYPE_PUSH_SRC);

/* pixman's format codes (PIXMAN_FORMAT(bpp, type, a, r, g, b)) as GStreamer formats */
static GstVideoFormat
format_from_pixman (guint32 code)
{
  switch (code) {
    case 0x20020888:           /* x8r8g8b8 */
      return GST_VIDEO_FORMAT_BGRx;
    case 0x20028888:           /* a8r8g8b8 */
      return GST_VIDEO_FORMAT_BGRA;
    case 0x20030888:           /* x8b8g8r8 */
      return GST_VIDEO_FORMAT_RGBx;
    case 0x20038888:           /* a8b8g8r8 */
      return GST_VIDEO_FORMAT_RGBA;
    case 0x20080888:           /* b8g8r8x8 */
      return GST_VIDEO_FORMAT_xRGB;
    case 0x20088888:           /* b8g8r8a8 */
      return GST_VIDEO_FORMAT_ARGB;
    case 0x18020888:           /* r8g8b8 */
      return GST_VIDEO_FORMAT_BGR;
    case 0x18030888:           /* b8g8r8 */
      return GST_VIDEO_FORMAT_RGB;
    case 0x10020565:           /* r5g6b5 */
      return GST_VIDEO_FORMAT_RGB16;
    case 0x10020555:           /* x1r5g5b5 */
      return GST_VIDEO_FORMAT_RGB15;
    default:
      return GST_VIDEO_FORMAT_UNKNOWN;
  }
}

/* DRM fourccs (little-endian packed) */
static GstVideoFormat
format_from_fourcc (guint32 fourcc)
{
  switch (fourcc) {
    case GST_MAKE_FOURCC ('X', 'R', '2', '4'):
      return GST_VIDEO_FORMAT_BGRx;
    case GST_MAKE_FOURCC ('A', 'R', '2', '4'):
      return GST_VIDEO_FORMAT_BGRA;
    case GST_MAKE_FOURCC ('X', 'B', '2', '4'):
      return GST_VIDEO_FORMAT_RGBx;
    case GST_MAKE_FOURCC ('A', 'B', '2', '4'):
      return GST_VIDEO_FORMAT_RGBA;
    case GST_MAKE_FOURCC ('B', 'X', '2', '4'):
      return GST_VIDEO_FORMAT_xRGB;
    case GST_MAKE_FOURCC ('B', 'A', '2', '4'):
      return GST_VIDEO_FORMAT_ARGB;
    case GST_MAKE_FOURCC ('R', 'G', '1', '6'):
      return GST_VIDEO_FORMAT_RGB16;
    default:
      return GST_VIDEO_FORMAT_UNKNOWN;
  }
}

static guint
format_bpp (GstVideoFormat format)
{
  const GstVideoFormatInfo *finfo = gst_video_format_get_info (format);

  return GST_VIDEO_FORMAT_INFO_PSTRIDE (finfo, 0);
}

/* under lock */
static void
picture_release_map (GstQemuDBusSrc * src)
{
  if (src->map) {
    munmap (src->map, src->map_len);
    src->map = NULL;
    src->map_len = 0;
  }
}

static void
picture_release_dmabuf (GstQemuDBusSrc * src)
{
  if (src->dmabuf) {
    munmap (src->dmabuf, src->dmabuf_len);
    src->dmabuf = NULL;
    src->dmabuf_len = 0;
  }
  if (src->dmabuf_fd >= 0) {
    close (src->dmabuf_fd);
    src->dmabuf_fd = -1;
  }
}

static void
picture_release (GstQemuDBusSrc * src)
{
  picture_release_map (src);
  picture_release_dmabuf (src);
  g_clear_pointer (&src->pixels, g_free);
  src->pixels_size = 0;
  src->kind = PICTURE_NONE;
  src->width = src->height = src->stride = 0;
  src->dirty = FALSE;
}

/* our own copy of a width x height picture with this stride (under lock) */
static void
picture_own (GstQemuDBusSrc * src, GstVideoFormat format, guint width, guint height,
    guint stride)
{
  gsize size = (gsize) stride * height;

  picture_release_map (src);
  if (src->pixels_size != size) {
    g_free (src->pixels);
    src->pixels = g_malloc0 (size);
    src->pixels_size = size;
  }
  src->kind = PICTURE_OWN;
  src->format = format;
  src->width = width;
  src->height = height;
  src->stride = stride;
}

/* Whether x, y, w, h lies within the picture; clamps it otherwise */
static gboolean
clip_rect (GstQemuDBusSrc * src, gint * x, gint * y, gint * w, gint * h)
{
  if (*x < 0 || *y < 0 || *w <= 0 || *h <= 0 || (guint) * x >= src->width
      || (guint) * y >= src->height)
    return FALSE;
  if ((guint) (*x + *w) > src->width)
    *w = src->width - *x;
  if ((guint) (*y + *h) > src->height)
    *h = src->height - *y;
  return TRUE;
}

static void
dmabuf_sync (int fd, guint64 flags)
{
  struct dma_buf_sync sync = {.flags = flags | DMA_BUF_SYNC_READ };

  /* a udmabuf or a GPU's buffer; failure only means no cache maintenance */
  while (ioctl (fd, DMA_BUF_IOCTL_SYNC, &sync) < 0 && errno == EINTR);
}

/* the rows y .. y + h of the mapped dmabuf into our copy, flipped if it's bottom up (under lock) */
static void
dmabuf_read (GstQemuDBusSrc * src, gint x, gint y, gint w, gint h)
{
  guint bpp = format_bpp (src->format);
  gint row;

  if (src->dmabuf_flip) {
    /* a GL scanout with its first row at the bottom: the whole picture, turned over */
    x = 0;
    y = 0;
    w = src->width;
    h = src->height;
  }
  dmabuf_sync (src->dmabuf_fd, DMA_BUF_SYNC_START);
  for (row = y; row < y + h; row++) {
    guint from = src->dmabuf_flip ? src->height - 1 - row : (guint) row;

    memcpy (src->pixels + (gsize) row * src->stride + (gsize) x * bpp,
        src->dmabuf + (gsize) from * src->dmabuf_stride + (gsize) x * bpp, (gsize) w * bpp);
  }
  dmabuf_sync (src->dmabuf_fd, DMA_BUF_SYNC_END);
}

static void
picture_changed (GstQemuDBusSrc * src)
{
  src->dirty = TRUE;
  g_cond_broadcast (&src->cond);
}

static int
take_fd (GDBusMethodInvocation * inv, GVariant * params, GError ** error)
{
  GUnixFDList *fds = g_dbus_message_get_unix_fd_list (g_dbus_method_invocation_get_message (inv));
  gint32 handle;

  g_variant_get_child (params, 0, "h", &handle);
  if (!fds) {
    g_set_error (error, G_DBUS_ERROR, G_DBUS_ERROR_INVALID_ARGS, "no file descriptor");
    return -1;
  }
  return g_unix_fd_list_get (fds, handle, error);
}

static void
on_scanout (GstQemuDBusSrc * src, GVariant * params)
{
  guint32 width, height, stride, code;
  GVariant *data;
  gsize n;
  const guint8 *bytes;
  GstVideoFormat format;

  g_variant_get_child (params, 0, "u", &width);
  g_variant_get_child (params, 1, "u", &height);
  g_variant_get_child (params, 2, "u", &stride);
  g_variant_get_child (params, 3, "u", &code);
  data = g_variant_get_child_value (params, 4);
  bytes = g_variant_get_fixed_array (data, &n, 1);
  format = format_from_pixman (code);
  if (format == GST_VIDEO_FORMAT_UNKNOWN || !width || !height
      || stride < width * format_bpp (format) || n < (gsize) stride * height) {
    GST_WARNING_OBJECT (src, "Scanout %ux%u stride %u pixman format 0x%08x (%" G_GSIZE_FORMAT
        " bytes) not taken", width, height, stride, code, n);
    g_variant_unref (data);
    return;
  }
  g_mutex_lock (&src->lock);
  picture_release_dmabuf (src);
  picture_own (src, format, width, height, stride);
  memcpy (src->pixels, bytes, (gsize) stride * height);
  src->n_scanout++;
  picture_changed (src);
  g_mutex_unlock (&src->lock);
  g_variant_unref (data);
  GST_DEBUG_OBJECT (src, "Scanout %ux%u %s", width, height, gst_video_format_to_string (format));
}

static void
on_update (GstQemuDBusSrc * src, GVariant * params)
{
  gint32 x, y, w, h, row;
  guint32 stride, code;
  GVariant *data;
  gsize n;
  const guint8 *bytes;
  guint bpp;
  gint w0;

  g_variant_get_child (params, 0, "i", &x);
  g_variant_get_child (params, 1, "i", &y);
  g_variant_get_child (params, 2, "i", &w);
  g_variant_get_child (params, 3, "i", &h);
  g_variant_get_child (params, 4, "u", &stride);
  g_variant_get_child (params, 5, "u", &code);
  data = g_variant_get_child_value (params, 6);
  bytes = g_variant_get_fixed_array (data, &n, 1);
  w0 = w;
  g_mutex_lock (&src->lock);
  if (src->kind != PICTURE_OWN || format_from_pixman (code) != src->format
      || !clip_rect (src, &x, &y, &w, &h)) {
    GST_DEBUG_OBJECT (src, "Update %d,%d %dx%d outside the picture", x, y, w, h);
    goto out;
  }
  bpp = format_bpp (src->format);
  if (stride < (guint) w0 * bpp || n < (gsize) stride * (h - 1) + (gsize) w * bpp)
    goto out;
  for (row = 0; row < h; row++)
    memcpy (src->pixels + (gsize) (y + row) * src->stride + (gsize) x * bpp,
        bytes + (gsize) row * stride, (gsize) w * bpp);
  src->n_update++;
  picture_changed (src);
out:
  g_mutex_unlock (&src->lock);
  g_variant_unref (data);
}

static gboolean
on_scanout_map (GstQemuDBusSrc * src, GDBusMethodInvocation * inv, GVariant * params,
    GError ** error)
{
  guint32 offset, width, height, stride, code;
  GstVideoFormat format;
  gsize len;
  void *map;
  int fd = take_fd (inv, params, error);

  if (fd < 0)
    return FALSE;
  g_variant_get_child (params, 1, "u", &offset);
  g_variant_get_child (params, 2, "u", &width);
  g_variant_get_child (params, 3, "u", &height);
  g_variant_get_child (params, 4, "u", &stride);
  g_variant_get_child (params, 5, "u", &code);
  format = format_from_pixman (code);
  if (format == GST_VIDEO_FORMAT_UNKNOWN || !width || !height
      || stride < width * format_bpp (format)) {
    close (fd);
    g_set_error (error, G_DBUS_ERROR, G_DBUS_ERROR_NOT_SUPPORTED,
        "ScanoutMap %ux%u stride %u pixman format 0x%08x not supported", width, height, stride,
        code);
    return FALSE;
  }
  len = (gsize) offset + (gsize) stride * height;
  map = mmap (NULL, len, PROT_READ, MAP_SHARED, fd, 0);
  close (fd);
  if (map == MAP_FAILED) {
    g_set_error (error, G_DBUS_ERROR, G_DBUS_ERROR_FAILED, "mmap: %s", g_strerror (errno));
    return FALSE;
  }
  g_mutex_lock (&src->lock);
  picture_release (src);
  src->kind = PICTURE_MAP;
  src->map = map;
  src->map_len = len;
  src->map_offset = offset;
  src->format = format;
  src->width = width;
  src->height = height;
  src->stride = stride;
  src->n_map_scanout++;
  picture_changed (src);
  g_mutex_unlock (&src->lock);
  GST_DEBUG_OBJECT (src, "ScanoutMap %ux%u %s", width, height,
      gst_video_format_to_string (format));
  return TRUE;
}

static void
on_update_map (GstQemuDBusSrc * src)
{
  g_mutex_lock (&src->lock);
  if (src->kind == PICTURE_MAP) {
    src->n_map_update++;
    picture_changed (src);
  }
  g_mutex_unlock (&src->lock);
}

static gboolean
on_scanout_dmabuf (GstQemuDBusSrc * src, GDBusMethodInvocation * inv, GVariant * params,
    GError ** error)
{
  guint32 width, height, stride, fourcc;
  guint64 modifier;
  gboolean y0_top;
  GstVideoFormat format;
  void *map = NULL;
  gsize len;
  int fd = take_fd (inv, params, error);

  if (fd < 0)
    return FALSE;
  g_variant_get_child (params, 1, "u", &width);
  g_variant_get_child (params, 2, "u", &height);
  g_variant_get_child (params, 3, "u", &stride);
  g_variant_get_child (params, 4, "u", &fourcc);
  g_variant_get_child (params, 5, "t", &modifier);
  g_variant_get_child (params, 6, "b", &y0_top);
  format = format_from_fourcc (fourcc);
  len = (gsize) stride * height;
  if (format != GST_VIDEO_FORMAT_UNKNOWN && width && height
      && stride >= width * format_bpp (format)
      && (modifier == DRM_FORMAT_MOD_LINEAR || modifier == DRM_FORMAT_MOD_INVALID)) {
    map = mmap (NULL, len, PROT_READ, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED) {
      GST_WARNING_OBJECT (src, "mmap of the dmabuf: %s", g_strerror (errno));
      map = NULL;
    }
  }
  g_mutex_lock (&src->lock);
  picture_release_dmabuf (src);
  src->n_dmabuf_scanout++;
  if (!map) {
    /* nothing to show: frames stop until a scanout we can read */
    close (fd);
    picture_release (src);
    if (!src->warned_modifier) {
      src->warned_modifier = TRUE;
      g_mutex_unlock (&src->lock);
      GST_ELEMENT_WARNING (src, STREAM, FORMAT, ("Can't read the console's dmabuf"),
          ("%ux%u fourcc %" GST_FOURCC_FORMAT " modifier 0x%" G_GINT64_MODIFIER "x: only "
              "linear dmabufs of 8-bit RGB formats are mapped; this console's frames are "
              "dropped", width, height, GST_FOURCC_ARGS (fourcc), modifier));
      return TRUE;
    }
    g_mutex_unlock (&src->lock);
    return TRUE;
  }
  picture_own (src, format, width, height, width * format_bpp (format));
  src->dmabuf_fd = fd;
  src->dmabuf = map;
  src->dmabuf_len = len;
  src->dmabuf_stride = stride;
  src->dmabuf_flip = y0_top;
  dmabuf_read (src, 0, 0, width, height);
  picture_changed (src);
  g_mutex_unlock (&src->lock);
  GST_DEBUG_OBJECT (src, "ScanoutDMABUF %ux%u %" GST_FOURCC_FORMAT " stride %u modifier 0x%"
      G_GINT64_MODIFIER "x y0_top %d", width, height, GST_FOURCC_ARGS (fourcc), stride,
      modifier, y0_top);
  return TRUE;
}

static void
on_update_dmabuf (GstQemuDBusSrc * src, GVariant * params)
{
  gint32 x, y, w, h;

  g_variant_get (params, "(iiii)", &x, &y, &w, &h);
  g_mutex_lock (&src->lock);
  if (src->dmabuf && src->kind == PICTURE_OWN && clip_rect (src, &x, &y, &w, &h)) {
    dmabuf_read (src, x, y, w, h);
    src->n_dmabuf_update++;
    picture_changed (src);
  } else {
    src->n_dmabuf_unmapped++;
  }
  g_mutex_unlock (&src->lock);
}

static void
listener_method (GDBusConnection * conn, const gchar * sender, const gchar * path,
    const gchar * iface, const gchar * method, GVariant * params, GDBusMethodInvocation * inv,
    gpointer user_data)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (user_data);
  GError *error = NULL;

  if (!strcmp (method, "UpdateDMABUF")) {
    gint64 t0 = g_get_monotonic_time (), us;

    /* read before the reply, which lets QEMU go on (and the guest draw into it again) */
    on_update_dmabuf (src, params);
    g_dbus_method_invocation_return_value (inv, NULL);
    us = g_get_monotonic_time () - t0;
    g_mutex_lock (&src->lock);
    src->dmabuf_us_total += us;
    src->dmabuf_us_max = MAX (src->dmabuf_us_max, us);
    g_mutex_unlock (&src->lock);
    return;
  } else if (!strcmp (method, "Update")) {
    on_update (src, params);
  } else if (!strcmp (method, "UpdateMap")) {
    on_update_map (src);
  } else if (!strcmp (method, "Scanout")) {
    on_scanout (src, params);
  } else if (!strcmp (method, "ScanoutMap")) {
    if (!on_scanout_map (src, inv, params, &error)) {
      GST_WARNING_OBJECT (src, "ScanoutMap: %s", error->message);
      g_dbus_method_invocation_take_error (inv, error);
      return;
    }
  } else if (!strcmp (method, "ScanoutDMABUF")) {
    if (!on_scanout_dmabuf (src, inv, params, &error)) {
      GST_WARNING_OBJECT (src, "ScanoutDMABUF: %s", error->message);
      g_dbus_method_invocation_take_error (inv, error);
      return;
    }
  } else if (!strcmp (method, "Disable")) {
    g_mutex_lock (&src->lock);
    picture_release (src);
    g_mutex_unlock (&src->lock);
    GST_DEBUG_OBJECT (src, "Disable");
  }
  /* MouseSet, CursorDefine: the cursor isn't drawn into the picture (yet) */
  g_dbus_method_invocation_return_value (inv, NULL);
}

static GVariant *
listener_get_property (GDBusConnection * conn, const gchar * sender, const gchar * path,
    const gchar * iface, const gchar * name, GError ** error, gpointer user_data)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (user_data);
  const gchar *with_map[] = { "org.qemu.Display1.Listener.Unix.Map", NULL };
  const gchar *none[] = { NULL };

  return g_variant_new_strv (src->shared_map ? with_map : none, -1);
}

static const GDBusInterfaceVTable listener_vtable = {
  .method_call = listener_method,
  .get_property = listener_get_property,
};

static void
on_closed (gpointer user_data)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (user_data);

  GST_INFO_OBJECT (src, "QEMU closed the connection: end of stream");
  g_mutex_lock (&src->lock);
  src->eos = TRUE;
  g_cond_broadcast (&src->cond);
  g_mutex_unlock (&src->lock);
}

static gboolean
gst_qemu_dbus_src_start (GstBaseSrc * bsrc)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (bsrc);
  GError *error = NULL;
  gchar *address, *path;
  GDBusInterfaceInfo *interfaces[3];
  QemuDBusPeerConfig config = { 0 };

  address = qemudbus_resolve_address (src->address, src->vmid);
  if (!address) {
    GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS, ("No D-Bus address"),
        ("set address (e.g. unix:path=/run/wsh-dbus-display/<vmid>.sock) or vmid"));
    return FALSE;
  }
  g_mutex_lock (&src->lock);
  picture_release (src);
  src->eos = FALSE;
  src->flushing = FALSE;
  src->have_info = FALSE;
  src->warned_modifier = FALSE;
  src->n_scanout = src->n_update = src->n_map_scanout = src->n_map_update = 0;
  src->n_dmabuf_scanout = src->n_dmabuf_update = src->n_dmabuf_unmapped = src->n_frames = 0;
  src->dmabuf_us_total = src->dmabuf_us_max = 0;
  g_mutex_unlock (&src->lock);

  path = g_strdup_printf ("/org/qemu/Display1/Console_%u", src->console);
  interfaces[0] = src->node->interfaces[0];
  interfaces[1] = src->node->interfaces[1];
  interfaces[2] = NULL;
  config.address = address;
  config.object_path = path;
  config.interface = "org.qemu.Display1.Console";
  config.method = "RegisterListener";
  config.listener_path = "/org/qemu/Display1/Listener";
  config.listener_interfaces = interfaces;
  config.vtable = &listener_vtable;
  config.user_data = src;
  config.closed = on_closed;
  config.timeout_ms = src->timeout * 1000;
  src->peer = qemudbus_peer_start (&config, &error);
  if (!src->peer) {
    GST_ELEMENT_ERROR (src, RESOURCE, OPEN_READ, ("Can't listen to QEMU's D-Bus display"),
        ("%s, %s: %s", address, path, error->message));
    g_error_free (error);
    g_free (address);
    g_free (path);
    return FALSE;
  }
  GST_INFO_OBJECT (src, "listening on %s, %s (shared map %s)", address, path,
      src->shared_map ? "offered" : "not offered");
  g_free (address);
  g_free (path);
  return TRUE;
}

static gchar *
stats_string (GstQemuDBusSrc * src)
{
  return g_strdup_printf ("scanouts=%" G_GUINT64_FORMAT " updates=%" G_GUINT64_FORMAT
      " map-scanouts=%" G_GUINT64_FORMAT " map-updates=%" G_GUINT64_FORMAT " dmabuf-scanouts=%"
      G_GUINT64_FORMAT " dmabuf-updates=%" G_GUINT64_FORMAT " dmabuf-unread=%" G_GUINT64_FORMAT
      " dmabuf-reply-us=%" G_GINT64_FORMAT "/%" G_GINT64_FORMAT " frames=%" G_GUINT64_FORMAT,
      src->n_scanout, src->n_update, src->n_map_scanout, src->n_map_update,
      src->n_dmabuf_scanout, src->n_dmabuf_update, src->n_dmabuf_unmapped,
      src->n_dmabuf_update ? src->dmabuf_us_total / (gint64) src->n_dmabuf_update : 0,
      src->dmabuf_us_max, src->n_frames);
}

static gboolean
gst_qemu_dbus_src_stop (GstBaseSrc * bsrc)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (bsrc);
  gchar *stats;

  qemudbus_peer_stop (src->peer);
  src->peer = NULL;
  g_mutex_lock (&src->lock);
  stats = stats_string (src);
  picture_release (src);
  g_mutex_unlock (&src->lock);
  /* the test harness reads this line (GST_DEBUG=qemudbussrc:4) */
  GST_INFO_OBJECT (src, "stopped: %s", stats);
  g_free (stats);
  return TRUE;
}

static gboolean
gst_qemu_dbus_src_unlock (GstBaseSrc * bsrc)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (bsrc);

  g_mutex_lock (&src->lock);
  src->flushing = TRUE;
  g_cond_broadcast (&src->cond);
  g_mutex_unlock (&src->lock);
  return TRUE;
}

static gboolean
gst_qemu_dbus_src_unlock_stop (GstBaseSrc * bsrc)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (bsrc);

  g_mutex_lock (&src->lock);
  src->flushing = FALSE;
  g_mutex_unlock (&src->lock);
  return TRUE;
}

/* the caps of the current picture (under lock), or NULL before the first */
static GstCaps *
picture_caps (GstQemuDBusSrc * src, GstVideoInfo * info)
{
  GstCaps *caps;

  if (src->kind == PICTURE_NONE || !src->width)
    return NULL;
  gst_video_info_set_format (info, src->format, src->width, src->height);
  GST_VIDEO_INFO_FPS_N (info) = 0;
  GST_VIDEO_INFO_FPS_D (info) = 1;
  caps = gst_video_info_to_caps (info);
  return caps;
}

static GstCaps *
gst_qemu_dbus_src_get_caps (GstBaseSrc * bsrc, GstCaps * filter)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (bsrc);
  GstVideoInfo info;
  GstCaps *caps;

  g_mutex_lock (&src->lock);
  caps = picture_caps (src, &info);
  g_mutex_unlock (&src->lock);
  if (!caps)
    caps = gst_pad_get_pad_template_caps (GST_BASE_SRC_PAD (bsrc));
  if (filter) {
    GstCaps *tmp = gst_caps_intersect_full (filter, caps, GST_CAPS_INTERSECT_FIRST);

    gst_caps_unref (caps);
    caps = tmp;
  }
  return caps;
}

/* The caps follow the picture: set in create() once there is one */
static gboolean
gst_qemu_dbus_src_negotiate (GstBaseSrc * bsrc)
{
  return TRUE;
}

static GstFlowReturn
gst_qemu_dbus_src_create (GstPushSrc * psrc, GstBuffer ** outbuf)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (psrc);
  GstVideoInfo info;
  GstVideoFrame frame;
  GstBuffer *buf;
  const guint8 *from;
  guint row, bpp, dstride;
  guint8 *to;

  g_mutex_lock (&src->lock);
  for (;;) {
    GstCaps *caps;

    while (!src->dirty && !src->flushing && !src->eos)
      g_cond_wait (&src->cond, &src->lock);
    if (src->flushing) {
      g_mutex_unlock (&src->lock);
      return GST_FLOW_FLUSHING;
    }
    if (!src->dirty) {
      g_mutex_unlock (&src->lock);
      return GST_FLOW_EOS;
    }
    caps = picture_caps (src, &info);
    if (!caps) {
      src->dirty = FALSE;
      continue;
    }
    if (src->have_info && gst_video_info_is_equal (&info, &src->info)) {
      gst_caps_unref (caps);
      break;
    }
    /* a new size or format: renegotiate, then look at the picture again */
    g_mutex_unlock (&src->lock);
    GST_INFO_OBJECT (src, "picture now %" GST_PTR_FORMAT, caps);
    if (!gst_base_src_set_caps (GST_BASE_SRC (src), caps)) {
      gst_caps_unref (caps);
      GST_ELEMENT_ERROR (src, CORE, NEGOTIATION, (NULL),
          ("downstream doesn't take the console's picture as %dx%d %s",
              GST_VIDEO_INFO_WIDTH (&info), GST_VIDEO_INFO_HEIGHT (&info),
              gst_video_format_to_string (GST_VIDEO_INFO_FORMAT (&info))));
      return GST_FLOW_NOT_NEGOTIATED;
    }
    gst_caps_unref (caps);
    g_mutex_lock (&src->lock);
    src->info = info;
    src->have_info = TRUE;
  }

  buf = gst_buffer_new_allocate (NULL, GST_VIDEO_INFO_SIZE (&src->info), NULL);
  if (!gst_video_frame_map (&frame, &src->info, buf, GST_MAP_WRITE)) {
    g_mutex_unlock (&src->lock);
    gst_buffer_unref (buf);
    return GST_FLOW_ERROR;
  }
  from = src->kind == PICTURE_MAP ? src->map + src->map_offset : src->pixels;
  bpp = format_bpp (src->format);
  to = GST_VIDEO_FRAME_PLANE_DATA (&frame, 0);
  dstride = GST_VIDEO_FRAME_PLANE_STRIDE (&frame, 0);
  for (row = 0; row < src->height; row++)
    memcpy (to + (gsize) row * dstride, from + (gsize) row * src->stride,
        (gsize) src->width * bpp);
  gst_video_frame_unmap (&frame);
  src->dirty = FALSE;
  src->n_frames++;
  g_mutex_unlock (&src->lock);

  *outbuf = buf;
  return GST_FLOW_OK;
}

static void
gst_qemu_dbus_src_set_property (GObject * object, guint prop_id, const GValue * value,
    GParamSpec * pspec)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (object);

  switch (prop_id) {
    case PROP_ADDRESS:
      g_free (src->address);
      src->address = g_value_dup_string (value);
      break;
    case PROP_VMID:
      src->vmid = g_value_get_int (value);
      break;
    case PROP_CONSOLE:
      src->console = g_value_get_uint (value);
      break;
    case PROP_TIMEOUT:
      src->timeout = g_value_get_uint (value);
      break;
    case PROP_SHARED_MAP:
      src->shared_map = g_value_get_boolean (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_qemu_dbus_src_get_property (GObject * object, guint prop_id, GValue * value,
    GParamSpec * pspec)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (object);

  switch (prop_id) {
    case PROP_ADDRESS:
      g_value_set_string (value, src->address);
      break;
    case PROP_VMID:
      g_value_set_int (value, src->vmid);
      break;
    case PROP_CONSOLE:
      g_value_set_uint (value, src->console);
      break;
    case PROP_TIMEOUT:
      g_value_set_uint (value, src->timeout);
      break;
    case PROP_SHARED_MAP:
      g_value_set_boolean (value, src->shared_map);
      break;
    case PROP_STATS:
      g_mutex_lock (&src->lock);
      g_value_take_string (value, stats_string (src));
      g_mutex_unlock (&src->lock);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_qemu_dbus_src_finalize (GObject * object)
{
  GstQemuDBusSrc *src = GST_QEMU_DBUS_SRC (object);

  qemudbus_peer_stop (src->peer);
  picture_release (src);
  g_dbus_node_info_unref (src->node);
  g_free (src->address);
  g_mutex_clear (&src->lock);
  g_cond_clear (&src->cond);
  G_OBJECT_CLASS (parent_class)->finalize (object);
}

static void
gst_qemu_dbus_src_class_init (GstQemuDBusSrcClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *element_class = GST_ELEMENT_CLASS (klass);
  GstBaseSrcClass *basesrc_class = GST_BASE_SRC_CLASS (klass);
  GstPushSrcClass *pushsrc_class = GST_PUSH_SRC_CLASS (klass);

  gobject_class->set_property = gst_qemu_dbus_src_set_property;
  gobject_class->get_property = gst_qemu_dbus_src_get_property;
  gobject_class->finalize = gst_qemu_dbus_src_finalize;

  g_object_class_install_property (gobject_class, PROP_ADDRESS,
      g_param_spec_string ("address", "Address",
          "D-Bus address of the VM's display bus (e.g. unix:path=/run/wsh-dbus-display/130.sock)",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_VMID,
      g_param_spec_int ("vmid", "VM ID",
          "PVE VM whose bus to use (/run/wsh-dbus-display/<vmid>.sock) when address is unset",
          -1, G_MAXINT, DEFAULT_VMID,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_CONSOLE,
      g_param_spec_uint ("console", "Console", "QEMU console index (Console_<n>)",
          0, G_MAXUINT, DEFAULT_CONSOLE,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_TIMEOUT,
      g_param_spec_uint ("timeout", "Timeout",
          "Seconds to wait for QEMU on the bus and for the listener's setup", 1, 3600,
          DEFAULT_TIMEOUT, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_SHARED_MAP,
      g_param_spec_boolean ("shared-map", "Shared map",
          "Offer QEMU the shared memory map of the console's surface (Listener.Unix.Map); "
          "without it a display without GL sends the pixels in each update",
          DEFAULT_SHARED_MAP,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_STATS,
      g_param_spec_string ("stats", "Statistics",
          "What QEMU sent and how many buffers went out", NULL,
          G_PARAM_READABLE | G_PARAM_STATIC_STRINGS));

  gst_element_class_set_static_metadata (element_class, "QEMU D-Bus display source",
      "Source/Video", "The picture of a console of QEMU's D-Bus display (-display dbus)",
      "WsHosting ENK <debian@wsh.no>");
  gst_element_class_add_static_pad_template (element_class, &src_template);

  basesrc_class->start = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_start);
  basesrc_class->stop = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_stop);
  basesrc_class->unlock = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_unlock);
  basesrc_class->unlock_stop = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_unlock_stop);
  basesrc_class->get_caps = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_get_caps);
  basesrc_class->negotiate = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_negotiate);
  pushsrc_class->create = GST_DEBUG_FUNCPTR (gst_qemu_dbus_src_create);

  GST_DEBUG_CATEGORY_INIT (gst_qemu_dbus_src_debug, "qemudbussrc", 0,
      "QEMU D-Bus display source");
}

static void
gst_qemu_dbus_src_init (GstQemuDBusSrc * src)
{
  src->vmid = DEFAULT_VMID;
  src->console = DEFAULT_CONSOLE;
  src->timeout = DEFAULT_TIMEOUT;
  src->shared_map = DEFAULT_SHARED_MAP;
  src->dmabuf_fd = -1;
  src->node = g_dbus_node_info_new_for_xml (LISTENER_XML, NULL);
  g_assert (src->node);
  g_mutex_init (&src->lock);
  g_cond_init (&src->cond);
  gst_base_src_set_live (GST_BASE_SRC (src), TRUE);
  gst_base_src_set_format (GST_BASE_SRC (src), GST_FORMAT_TIME);
  gst_base_src_set_do_timestamp (GST_BASE_SRC (src), TRUE);
}
