/*
 * qemudbusaudiosrc: the sound of QEMU's D-Bus audio (-audiodev dbus) as a live audio source
 * (gstqemudbusaudiosrc.c).
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifndef GST_QEMU_DBUS_AUDIO_SRC_H
#define GST_QEMU_DBUS_AUDIO_SRC_H

#include <gst/audio/audio.h>
#include <gst/base/gstpushsrc.h>
#include <gst/gst.h>

G_BEGIN_DECLS

#define GST_TYPE_QEMU_DBUS_AUDIO_SRC (gst_qemu_dbus_audio_src_get_type ())
G_DECLARE_FINAL_TYPE (GstQemuDBusAudioSrc, gst_qemu_dbus_audio_src, GST, QEMU_DBUS_AUDIO_SRC,
    GstPushSrc)

G_END_DECLS

#endif
