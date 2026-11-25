/*
 * The connection to QEMU's D-Bus display (-display dbus) shared by the elements of the qemudbus
 * GStreamer plugin: the VM's bus, and one listener object of ours that QEMU calls over a
 * peer-to-peer connection it is handed in RegisterListener (or RegisterOutListener). Everything
 * D-Bus runs on a thread of its own with a main context of its own, so QEMU's calls are answered
 * while the element's streaming thread waits for downstream.
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifndef QEMUDBUS_H
#define QEMUDBUS_H

#include <gio/gio.h>

G_BEGIN_DECLS

/* QEMU owns this name on its bus; qemu-server gives each VM a bus of its own on this socket */
#define QEMUDBUS_NAME "org.qemu"
#define QEMUDBUS_VM_ADDRESS_FMT "unix:path=/run/wsh-dbus-display/%d.sock"

/* The bus address from the address and vmid properties (the address wins), or NULL */
gchar *qemudbus_resolve_address (const gchar * address, gint vmid);

typedef struct _QemuDBusPeer QemuDBusPeer;

typedef struct
{
  const gchar *address;         /* the VM's bus */
  const gchar *object_path;     /* QEMU's object the listener is registered on */
  const gchar *interface;       /* and its interface */
  const gchar *method;          /* RegisterListener or RegisterOutListener, (h) */
  const gchar *listener_path;   /* our object, where QEMU calls it */
  GDBusInterfaceInfo **listener_interfaces;     /* NULL-terminated; all on listener_path */
  const GDBusInterfaceVTable *vtable;
  gpointer user_data;           /* for the vtable and closed */
  /* called on the D-Bus thread when QEMU closes the connection (the VM stopped) */
  void (*closed) (gpointer user_data);
  guint timeout_ms;             /* for the bus, org.qemu and the listener to be set up */
} QemuDBusPeerConfig;

/*
 * Connects to the bus, waits for org.qemu, and registers the listener; returns once QEMU has
 * authenticated the peer connection (the listener is live) or with an error. The vtable's
 * handlers run on the peer's own thread until qemudbus_peer_stop().
 */
QemuDBusPeer *qemudbus_peer_start (const QemuDBusPeerConfig * config, GError ** error);
/* Closes both connections (QEMU drops the listener) and joins the thread */
void qemudbus_peer_stop (QemuDBusPeer * peer);

/* Connects to the bus and waits up to timeout_ms for org.qemu on it (the input bridge too) */
GDBusConnection *qemudbus_connect (const gchar * address, guint timeout_ms,
    GCancellable * cancellable, GError ** error);

G_END_DECLS

#endif
