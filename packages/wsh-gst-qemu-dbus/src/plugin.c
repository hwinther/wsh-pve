/*
 * The qemudbus GStreamer plugin: qemudbussrc (the picture of a console of QEMU's D-Bus display)
 * and qemudbusaudiosrc (the guest's playback through QEMU's D-Bus audio), for a streaming
 * server on a Proxmox VE node (vga: ...,display=dbus with the wsh-pve qemu-server).
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "gstqemudbusaudiosrc.h"
#include "gstqemudbussrc.h"

static gboolean
plugin_init (GstPlugin * plugin)
{
  return gst_element_register (plugin, "qemudbussrc", GST_RANK_NONE, GST_TYPE_QEMU_DBUS_SRC)
      && gst_element_register (plugin, "qemudbusaudiosrc", GST_RANK_NONE,
      GST_TYPE_QEMU_DBUS_AUDIO_SRC);
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR, GST_VERSION_MINOR, qemudbus,
    "Sources for QEMU's D-Bus display and audio", plugin_init, PACKAGE_VERSION, "GPL",
    "wsh-gst-qemu-dbus", "https://github.com/hwinther/wsh-pve")
