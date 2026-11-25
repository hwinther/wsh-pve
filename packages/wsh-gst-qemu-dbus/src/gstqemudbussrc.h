/*
 * qemudbussrc: the picture of a console of QEMU's D-Bus display as a live video source
 * (gstqemudbussrc.c).
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifndef GST_QEMU_DBUS_SRC_H
#define GST_QEMU_DBUS_SRC_H

#include <gst/base/gstpushsrc.h>
#include <gst/gst.h>
#include <gst/video/video.h>

G_BEGIN_DECLS

#define GST_TYPE_QEMU_DBUS_SRC (gst_qemu_dbus_src_get_type ())
G_DECLARE_FINAL_TYPE (GstQemuDBusSrc, gst_qemu_dbus_src, GST, QEMU_DBUS_SRC, GstPushSrc)

G_END_DECLS

#endif
