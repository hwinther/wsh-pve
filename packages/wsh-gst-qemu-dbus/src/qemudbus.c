/*
 * The connection to QEMU's D-Bus display shared by the qemudbus elements (qemudbus.h).
 *
 * How QEMU sets up a listener (ui/dbus-console.c, audio/dbusaudio.c): the client calls
 * RegisterListener(h) on Console_<n> (RegisterOutListener(h) on Audio) with one end of a socket
 * pair. QEMU replies (the console does it first, the audio afterwards), then makes a D-Bus server
 * connection on that socket and authenticates it synchronously, then creates proxies of the
 * listener object, which read its properties synchronously ("Interfaces": which optional
 * interfaces the listener has). QEMU's main loop is blocked through all of that, so our end of
 * the socket must authenticate and answer on a main loop of its own while the call is open: the
 * connection is made asynchronously, with message processing held back until the listener
 * object is registered, and the Register call is asynchronous too.
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#include "qemudbus.h"

#include <errno.h>
#include <gio/gunixfdlist.h>
#include <sys/socket.h>
#include <unistd.h>

struct _QemuDBusPeer
{
  QemuDBusPeerConfig config;    /* the strings are copies */
  gchar *address, *object_path, *interface, *method, *listener_path;
  GDBusInterfaceInfo **interfaces;

  GMainContext *context;
  GMainLoop *loop;
  GThread *thread;
  GCancellable *cancellable;

  GDBusConnection *bus;
  GDBusConnection *conn;        /* the peer connection QEMU calls us on */
  GArray *registrations;
  gulong closed_handler;
  GSource *timeout;

  GMutex lock;
  GCond cond;
  gboolean done;
  GError *error;
};

gchar *
qemudbus_resolve_address (const gchar * address, gint vmid)
{
  if (address && *address)
    return g_strdup (address);
  if (vmid >= 0)
    return g_strdup_printf (QEMUDBUS_VM_ADDRESS_FMT, vmid);
  return NULL;
}

GDBusConnection *
qemudbus_connect (const gchar * address, guint timeout_ms, GCancellable * cancellable,
    GError ** error)
{
  GDBusConnection *bus;
  gint64 deadline = g_get_monotonic_time () + (gint64) timeout_ms * 1000;

  bus = g_dbus_connection_new_for_address_sync (address,
      G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT |
      G_DBUS_CONNECTION_FLAGS_MESSAGE_BUS_CONNECTION, NULL, cancellable, error);
  if (!bus)
    return NULL;
  /* QEMU may still be starting (qemu-server starts the bus first) */
  for (;;) {
    GVariant *reply;
    gboolean owned = FALSE;

    reply = g_dbus_connection_call_sync (bus, "org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus", "NameHasOwner", g_variant_new ("(s)", QEMUDBUS_NAME),
        G_VARIANT_TYPE ("(b)"), G_DBUS_CALL_FLAGS_NONE, -1, cancellable, error);
    if (!reply) {
      g_object_unref (bus);
      return NULL;
    }
    g_variant_get (reply, "(b)", &owned);
    g_variant_unref (reply);
    if (owned)
      return bus;
    if (g_get_monotonic_time () > deadline) {
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
          "nobody owns %s on %s (is the VM running with -display dbus?)", QEMUDBUS_NAME, address);
      g_object_unref (bus);
      return NULL;
    }
    if (g_cancellable_set_error_if_cancelled (cancellable, error)) {
      g_object_unref (bus);
      return NULL;
    }
    g_usleep (100 * 1000);
  }
}

/* The outcome of the setup, once: start() waits for it */
static void
peer_finish (QemuDBusPeer * peer, GError * error)
{
  g_mutex_lock (&peer->lock);
  if (!peer->done) {
    peer->done = TRUE;
    peer->error = error;
    error = NULL;
  }
  g_cond_broadcast (&peer->cond);
  g_mutex_unlock (&peer->lock);
  g_clear_error (&error);
}

static void
peer_closed (GDBusConnection * conn, gboolean remote_peer_vanished, GError * error,
    gpointer user_data)
{
  QemuDBusPeer *peer = user_data;

  peer_finish (peer, g_error_new (G_IO_ERROR, G_IO_ERROR_CLOSED,
          "QEMU closed the listener's connection"));
  if (peer->config.closed)
    peer->config.closed (peer->config.user_data);
}

static void
peer_connected (GObject * source, GAsyncResult * res, gpointer user_data)
{
  QemuDBusPeer *peer = user_data;
  GError *error = NULL;
  GDBusConnection *conn = g_dbus_connection_new_finish (res, &error);
  guint i;

  if (!conn) {
    if (!g_error_matches (error, G_IO_ERROR, G_IO_ERROR_CANCELLED))
      g_prefix_error (&error, "the listener's connection: ");
    peer_finish (peer, error);
    return;
  }
  peer->conn = conn;
  for (i = 0; peer->interfaces[i]; i++) {
    guint id = g_dbus_connection_register_object (conn, peer->listener_path,
        peer->interfaces[i], peer->config.vtable, peer->config.user_data, NULL, &error);

    if (!id) {
      peer_finish (peer, error);
      return;
    }
    g_array_append_val (peer->registrations, id);
  }
  peer->closed_handler = g_signal_connect (conn, "closed", G_CALLBACK (peer_closed), peer);
  /* QEMU's calls (the properties first) are answered from here on */
  g_dbus_connection_start_message_processing (conn);
  peer_finish (peer, NULL);
}

static void
peer_registered (GObject * source, GAsyncResult * res, gpointer user_data)
{
  QemuDBusPeer *peer = user_data;
  GError *error = NULL;
  GVariant *reply;

  reply = g_dbus_connection_call_with_unix_fd_list_finish (G_DBUS_CONNECTION (source), NULL,
      res, &error);
  if (reply) {
    g_variant_unref (reply);
    return;
  }
  /* QEMU refused (no such console, no -audiodev dbus): it won't connect */
  if (!g_error_matches (error, G_IO_ERROR, G_IO_ERROR_CANCELLED))
    g_prefix_error (&error, "%s on %s: ", peer->method, peer->object_path);
  peer_finish (peer, error);
}

static gboolean
peer_timed_out (gpointer user_data)
{
  QemuDBusPeer *peer = user_data;

  peer_finish (peer, g_error_new (G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
          "QEMU didn't set up the listener within %u ms", peer->config.timeout_ms));
  return G_SOURCE_REMOVE;
}

/* On the peer's thread, its context the thread's default */
static void
peer_setup (QemuDBusPeer * peer)
{
  GError *error = NULL;
  GSocket *sock;
  GSocketConnection *stream;
  GUnixFDList *fds;
  int sv[2];

  peer->bus = qemudbus_connect (peer->address, peer->config.timeout_ms, peer->cancellable,
      &error);
  if (!peer->bus) {
    peer_finish (peer, error);
    return;
  }
  if (socketpair (AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sv) < 0) {
    peer_finish (peer, g_error_new (G_IO_ERROR, g_io_error_from_errno (errno),
            "socketpair: %s", g_strerror (errno)));
    return;
  }
  sock = g_socket_new_from_fd (sv[0], &error);
  if (!sock) {
    close (sv[0]);
    close (sv[1]);
    peer_finish (peer, error);
    return;
  }
  stream = g_socket_connection_factory_create_connection (sock);
  g_object_unref (sock);
  g_dbus_connection_new (G_IO_STREAM (stream), NULL,
      G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT |
      G_DBUS_CONNECTION_FLAGS_DELAY_MESSAGE_PROCESSING, NULL, peer->cancellable,
      peer_connected, peer);
  g_object_unref (stream);

  fds = g_unix_fd_list_new_from_array (&sv[1], 1);      /* takes the fd */
  g_dbus_connection_call_with_unix_fd_list (peer->bus, QEMUDBUS_NAME, peer->object_path,
      peer->interface, peer->method, g_variant_new ("(h)", 0), NULL, G_DBUS_CALL_FLAGS_NONE,
      -1, fds, peer->cancellable, peer_registered, peer);
  g_object_unref (fds);

  peer->timeout = g_timeout_source_new (peer->config.timeout_ms);
  g_source_set_callback (peer->timeout, peer_timed_out, peer, NULL);
  g_source_attach (peer->timeout, peer->context);
}

static gpointer
peer_thread (gpointer data)
{
  QemuDBusPeer *peer = data;
  guint i;

  g_main_context_push_thread_default (peer->context);
  peer_setup (peer);
  g_main_loop_run (peer->loop);

  /* Teardown on this thread, so no handler of ours runs after it */
  if (peer->timeout) {
    g_source_destroy (peer->timeout);
    g_source_unref (peer->timeout);
  }
  if (peer->conn) {
    if (peer->closed_handler)
      g_signal_handler_disconnect (peer->conn, peer->closed_handler);
    for (i = 0; i < peer->registrations->len; i++)
      g_dbus_connection_unregister_object (peer->conn,
          g_array_index (peer->registrations, guint, i));
    g_dbus_connection_close_sync (peer->conn, NULL, NULL);
    g_clear_object (&peer->conn);
  }
  if (peer->bus) {
    g_dbus_connection_close_sync (peer->bus, NULL, NULL);
    g_clear_object (&peer->bus);
  }
  while (g_main_context_iteration (peer->context, FALSE));
  g_main_context_pop_thread_default (peer->context);
  return NULL;
}

QemuDBusPeer *
qemudbus_peer_start (const QemuDBusPeerConfig * config, GError ** error)
{
  QemuDBusPeer *peer = g_new0 (QemuDBusPeer, 1);
  guint n = 0;

  peer->config = *config;
  peer->address = g_strdup (config->address);
  peer->object_path = g_strdup (config->object_path);
  peer->interface = g_strdup (config->interface);
  peer->method = g_strdup (config->method);
  peer->listener_path = g_strdup (config->listener_path);
  while (config->listener_interfaces[n])
    n++;
  peer->interfaces = g_new0 (GDBusInterfaceInfo *, n + 1);
  for (n = 0; config->listener_interfaces[n]; n++)
    peer->interfaces[n] = g_dbus_interface_info_ref (config->listener_interfaces[n]);
  peer->registrations = g_array_new (FALSE, FALSE, sizeof (guint));
  peer->context = g_main_context_new ();
  peer->loop = g_main_loop_new (peer->context, FALSE);
  peer->cancellable = g_cancellable_new ();
  g_mutex_init (&peer->lock);
  g_cond_init (&peer->cond);

  peer->thread = g_thread_new ("qemudbus", peer_thread, peer);
  g_mutex_lock (&peer->lock);
  while (!peer->done)
    g_cond_wait (&peer->cond, &peer->lock);
  g_mutex_unlock (&peer->lock);
  if (peer->error) {
    g_propagate_error (error, peer->error);
    peer->error = NULL;
    qemudbus_peer_stop (peer);
    return NULL;
  }
  return peer;
}

void
qemudbus_peer_stop (QemuDBusPeer * peer)
{
  guint i;

  if (!peer)
    return;
  g_cancellable_cancel (peer->cancellable);
  g_main_loop_quit (peer->loop);
  g_thread_join (peer->thread);

  g_main_loop_unref (peer->loop);
  g_main_context_unref (peer->context);
  g_object_unref (peer->cancellable);
  g_array_unref (peer->registrations);
  for (i = 0; peer->interfaces[i]; i++)
    g_dbus_interface_info_unref (peer->interfaces[i]);
  g_free (peer->interfaces);
  g_free (peer->address);
  g_free (peer->object_path);
  g_free (peer->interface);
  g_free (peer->method);
  g_free (peer->listener_path);
  g_clear_error (&peer->error);
  g_mutex_clear (&peer->lock);
  g_cond_clear (&peer->cond);
  g_free (peer);
}
