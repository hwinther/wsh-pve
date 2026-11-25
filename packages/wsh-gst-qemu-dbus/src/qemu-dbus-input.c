/*
 * qemu-dbus-input: keyboard and mouse input for a console of QEMU's D-Bus display, from simple
 * text commands on standard input, one per line (the input path a streaming server drives; see
 * qemu-dbus-input(1) for the whole protocol):
 *
 *   key CODE 1|0        press or release a key by its Linux input event code (KEY_A = 30)
 *   qkey QNUM 1|0       the same by QEMU's key number (xtkbd, extended keys 0x80 | code)
 *   btn BUTTON 1|0      left, middle, right, wheel-up, wheel-down, side, extra (or 0-6)
 *   wheel N             N steps of the wheel, up (N > 0) or down (N < 0)
 *   rel DX DY           relative motion
 *   abs X Y [W H]       absolute position in the console's pixels, or scaled from a W x H area
 *   query               prints the mouse mode and the console's size
 *   sync                prints "sync N" once QEMU has answered the N commands sent so far
 *
 * Mouse motion goes the way the guest's pointer takes it, which QEMU says in the Mouse
 * interface's IsAbsolute property (true with a USB or virtio tablet, false with a PS/2 or Sun
 * mouse): with an absolute pointer, rel moves a pointer position the bridge keeps (clamped to the
 * console) and sends it as SetAbsPosition; with a relative one, abs sends the difference from the
 * previous abs position as RelMotion (the first abs only sets that position). Changes of the mode
 * are printed ("mode absolute|relative"). Keys still down when standard input ends are released.
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "qemudbus.h"

#include <gio/gunixinputstream.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct
{
  GMainLoop *loop;
  GDBusConnection *bus;
  gchar *path;
  GDBusProxy *mouse;
  GDBusProxy *console;
  GDataInputStream *in;
  gboolean quiet;

  guint64 sent, answered;
  GQueue syncs;                 /* the sent counts "sync" waits for, as guint64 in pointers */
  gboolean eof;

  gboolean absolute;
  gint px, py;                  /* the pointer, for rel on an absolute pointer */
  gboolean have_last;           /* the last abs position, for abs on a relative pointer */
  gint lx, ly;
  GHashTable *pressed;          /* QEMU key numbers down */
} Bridge;

static void out (const gchar * fmt, ...) G_GNUC_PRINTF (1, 2);

static void
out (const gchar * fmt, ...)
{
  va_list ap;

  va_start (ap, fmt);
  vprintf (fmt, ap);
  va_end (ap);
  putchar ('\n');
  fflush (stdout);
}

/*
 * Linux input event codes to QEMU's key numbers. 1-83 are the same in both (the XT set 1 make
 * codes); the rest as QEMU's keycodemapdb maps them (linux -> qcode -> qnum).
 */
static guint
linux_to_qnum (guint code)
{
  if (code >= 1 && code <= 83)
    return code;
  switch (code) {
    case 85:                   /* KEY_ZENKAKUHANKAKU */
      return 0x76;
    case 86:                   /* KEY_102ND */
      return 0x56;
    case 87:                   /* KEY_F11 */
      return 0x57;
    case 88:                   /* KEY_F12 */
      return 0x58;
    case 89:                   /* KEY_RO */
      return 0x73;
    case 92:                   /* KEY_HENKAN */
      return 0x79;
    case 93:                   /* KEY_KATAKANAHIRAGANA */
      return 0x70;
    case 94:                   /* KEY_MUHENKAN */
      return 0x7b;
    case 96:                   /* KEY_KPENTER */
      return 0x9c;
    case 97:                   /* KEY_RIGHTCTRL */
      return 0x9d;
    case 98:                   /* KEY_KPSLASH */
      return 0xb5;
    case 99:                   /* KEY_SYSRQ */
      return 0x54;
    case 100:                  /* KEY_RIGHTALT */
      return 0xb8;
    case 102:                  /* KEY_HOME */
      return 0xc7;
    case 103:                  /* KEY_UP */
      return 0xc8;
    case 104:                  /* KEY_PAGEUP */
      return 0xc9;
    case 105:                  /* KEY_LEFT */
      return 0xcb;
    case 106:                  /* KEY_RIGHT */
      return 0xcd;
    case 107:                  /* KEY_END */
      return 0xcf;
    case 108:                  /* KEY_DOWN */
      return 0xd0;
    case 109:                  /* KEY_PAGEDOWN */
      return 0xd1;
    case 110:                  /* KEY_INSERT */
      return 0xd2;
    case 111:                  /* KEY_DELETE */
      return 0xd3;
    case 113:                  /* KEY_MUTE */
      return 0xa0;
    case 114:                  /* KEY_VOLUMEDOWN */
      return 0xae;
    case 115:                  /* KEY_VOLUMEUP */
      return 0xb0;
    case 116:                  /* KEY_POWER */
      return 0xde;
    case 117:                  /* KEY_KPEQUAL */
      return 0x59;
    case 119:                  /* KEY_PAUSE */
      return 0xc6;
    case 121:                  /* KEY_KPCOMMA */
      return 0x7e;
    case 124:                  /* KEY_YEN */
      return 0x7d;
    case 125:                  /* KEY_LEFTMETA */
      return 0xdb;
    case 126:                  /* KEY_RIGHTMETA */
      return 0xdc;
    case 127:                  /* KEY_COMPOSE */
      return 0xdd;
    default:
      return 0;
  }
}

static gint
parse_button (const gchar * s)
{
  static const gchar *names[] = { "left", "middle", "right", "wheel-up", "wheel-down", "side",
    "extra", NULL
  };
  gchar *end;
  glong n;
  gint i;

  for (i = 0; names[i]; i++)
    if (!g_ascii_strcasecmp (s, names[i]))
      return i;
  n = strtol (s, &end, 0);
  return (*s && !*end && n >= 0 && n <= 6) ? (gint) n : -1;
}

static gboolean
parse_int (const gchar * s, gint * v)
{
  gchar *end;
  gint64 n;

  if (!s)
    return FALSE;
  n = g_ascii_strtoll (s, &end, 0);
  if (!*s || *end || n < G_MININT || n > G_MAXINT)
    return FALSE;
  *v = (gint) n;
  return TRUE;
}

static guint
console_dim (Bridge * b, const gchar * name)
{
  GVariant *v = g_dbus_proxy_get_cached_property (b->console, name);
  guint n = 0;

  if (v) {
    n = g_variant_get_uint32 (v);
    g_variant_unref (v);
  }
  return n;
}

static void
update_mode (Bridge * b, gboolean announce)
{
  GVariant *v = g_dbus_proxy_get_cached_property (b->mouse, "IsAbsolute");
  gboolean absolute = v ? g_variant_get_boolean (v) : FALSE;

  if (v)
    g_variant_unref (v);
  if (announce && absolute != b->absolute)
    out ("mode %s", absolute ? "absolute" : "relative");
  b->absolute = absolute;
}

static void
check_syncs (Bridge * b)
{
  while (b->syncs.length
      && GPOINTER_TO_SIZE (g_queue_peek_head (&b->syncs)) <= b->answered) {
    out ("sync %" G_GUINT64_FORMAT, (guint64) GPOINTER_TO_SIZE (g_queue_pop_head (&b->syncs)));
  }
  if (b->eof && b->answered == b->sent && !b->syncs.length)
    g_main_loop_quit (b->loop);
}

static void
call_done (GObject * source, GAsyncResult * res, gpointer user_data)
{
  Bridge *b = user_data;
  GError *error = NULL;
  GVariant *reply = g_dbus_connection_call_finish (G_DBUS_CONNECTION (source), res, &error);

  if (reply) {
    g_variant_unref (reply);
  } else {
    gchar *msg = g_dbus_error_get_remote_error (error);

    g_dbus_error_strip_remote_error (error);
    out ("error %s%s%s", error->message, msg ? " " : "", msg ? msg : "");
    g_free (msg);
    g_error_free (error);
  }
  b->answered++;
  check_syncs (b);
}

static void
call (Bridge * b, const gchar * iface, const gchar * method, GVariant * args)
{
  b->sent++;
  g_dbus_connection_call (b->bus, QEMUDBUS_NAME, b->path, iface, method, args, NULL,
      G_DBUS_CALL_FLAGS_NO_AUTO_START, -1, NULL, call_done, b);
}

static void
key (Bridge * b, guint qnum, gboolean down)
{
  if (down)
    g_hash_table_add (b->pressed, GUINT_TO_POINTER (qnum));
  else
    g_hash_table_remove (b->pressed, GUINT_TO_POINTER (qnum));
  call (b, "org.qemu.Display1.Keyboard", down ? "Press" : "Release",
      g_variant_new ("(u)", qnum));
}

static void
set_abs (Bridge * b, gint x, gint y)
{
  guint w = console_dim (b, "Width"), h = console_dim (b, "Height");

  if (!w || !h) {
    out ("error the console has no size yet");
    return;
  }
  b->px = CLAMP (x, 0, (gint) w - 1);
  b->py = CLAMP (y, 0, (gint) h - 1);
  call (b, "org.qemu.Display1.Mouse", "SetAbsPosition", g_variant_new ("(uu)", b->px, b->py));
}

static void
command (Bridge * b, gchar * line)
{
  gchar **arg = g_strsplit_set (g_strstrip (line), " \t", -1);
  guint argc = 0;
  gint v1, v2, v3, v4;

  /* runs of blanks */
  {
    guint i, j = 0;

    for (i = 0; arg[i]; i++) {
      if (*arg[i])
        arg[j++] = arg[i];
      else
        g_free (arg[i]);
    }
    arg[j] = NULL;
    argc = j;
  }
  if (!argc || arg[0][0] == '#')
    goto done;

  if (!strcmp (arg[0], "key") || !strcmp (arg[0], "qkey")) {
    guint qnum;

    if (argc != 3 || !parse_int (arg[1], &v1) || !parse_int (arg[2], &v2) || v1 < 0
        || (v2 != 0 && v2 != 1)) {
      out ("error usage: %s CODE 1|0", arg[0]);
      goto done;
    }
    qnum = arg[0][0] == 'q' ? (guint) v1 : linux_to_qnum (v1);
    if (!qnum) {
      out ("error no QEMU key number for Linux key code %d (use qkey)", v1);
      goto done;
    }
    key (b, qnum, v2);
  } else if (!strcmp (arg[0], "btn")) {
    gint button = argc == 3 ? parse_button (arg[1]) : -1;

    if (button < 0 || !parse_int (arg[2], &v2) || (v2 != 0 && v2 != 1)) {
      out ("error usage: btn left|middle|right|wheel-up|wheel-down|side|extra|0-6 1|0");
      goto done;
    }
    call (b, "org.qemu.Display1.Mouse", v2 ? "Press" : "Release",
        g_variant_new ("(u)", (guint) button));
  } else if (!strcmp (arg[0], "wheel")) {
    gint i;

    if (argc != 2 || !parse_int (arg[1], &v1) || v1 == 0 || ABS (v1) > 100) {
      out ("error usage: wheel N (N steps, up if positive, at most 100)");
      goto done;
    }
    for (i = 0; i < ABS (v1); i++) {
      call (b, "org.qemu.Display1.Mouse", "Press", g_variant_new ("(u)", v1 > 0 ? 3u : 4u));
      call (b, "org.qemu.Display1.Mouse", "Release", g_variant_new ("(u)", v1 > 0 ? 3u : 4u));
    }
  } else if (!strcmp (arg[0], "rel")) {
    if (argc != 3 || !parse_int (arg[1], &v1) || !parse_int (arg[2], &v2)) {
      out ("error usage: rel DX DY");
      goto done;
    }
    if (b->absolute)
      set_abs (b, b->px + v1, b->py + v2);
    else if (v1 || v2)
      call (b, "org.qemu.Display1.Mouse", "RelMotion", g_variant_new ("(ii)", v1, v2));
  } else if (!strcmp (arg[0], "abs")) {
    if ((argc != 3 && argc != 5) || !parse_int (arg[1], &v1) || !parse_int (arg[2], &v2)
        || (argc == 5 && (!parse_int (arg[3], &v3) || !parse_int (arg[4], &v4) || v3 <= 0
                || v4 <= 0))) {
      out ("error usage: abs X Y [W H]");
      goto done;
    }
    if (argc == 5) {
      guint w = console_dim (b, "Width"), h = console_dim (b, "Height");

      v1 = (gint) ((gint64) v1 * w / v3);
      v2 = (gint) ((gint64) v2 * h / v4);
    }
    if (b->absolute) {
      set_abs (b, v1, v2);
    } else {
      if (b->have_last && (v1 != b->lx || v2 != b->ly))
        call (b, "org.qemu.Display1.Mouse", "RelMotion",
            g_variant_new ("(ii)", v1 - b->lx, v2 - b->ly));
      b->px = v1;
      b->py = v2;
    }
    b->have_last = TRUE;
    b->lx = v1;
    b->ly = v2;
  } else if (!strcmp (arg[0], "query")) {
    update_mode (b, FALSE);
    out ("mode %s width %u height %u", b->absolute ? "absolute" : "relative",
        console_dim (b, "Width"), console_dim (b, "Height"));
  } else if (!strcmp (arg[0], "sync")) {
    g_queue_push_tail (&b->syncs, GSIZE_TO_POINTER ((gsize) b->sent));
    check_syncs (b);
  } else {
    out ("error unknown command '%s' (key, qkey, btn, wheel, rel, abs, query, sync)", arg[0]);
  }
done:
  g_strfreev (arg);
}

static void read_next (Bridge * b);

static void
release_all (Bridge * b)
{
  GHashTableIter it;
  gpointer qnum;

  g_hash_table_iter_init (&it, b->pressed);
  while (g_hash_table_iter_next (&it, &qnum, NULL)) {
    b->sent++;
    g_dbus_connection_call (b->bus, QEMUDBUS_NAME, b->path, "org.qemu.Display1.Keyboard",
        "Release", g_variant_new ("(u)", GPOINTER_TO_UINT (qnum)), NULL,
        G_DBUS_CALL_FLAGS_NO_AUTO_START, -1, NULL, call_done, b);
  }
  g_hash_table_remove_all (b->pressed);
}

static void
line_read (GObject * source, GAsyncResult * res, gpointer user_data)
{
  Bridge *b = user_data;
  GError *error = NULL;
  gsize len;
  gchar *line = g_data_input_stream_read_line_finish_utf8 (b->in, res, &len, &error);

  if (!line) {
    if (error) {
      g_printerr ("qemu-dbus-input: standard input: %s\n", error->message);
      g_error_free (error);
    }
    /* the end: let go of the keys, then quit once QEMU has answered everything */
    release_all (b);
    b->eof = TRUE;
    check_syncs (b);
    return;
  }
  command (b, line);
  g_free (line);
  read_next (b);
}

static void
read_next (Bridge * b)
{
  g_data_input_stream_read_line_async (b->in, G_PRIORITY_DEFAULT, NULL, line_read, b);
}

static void
mouse_changed (GDBusProxy * proxy, GVariant * changed, GStrv invalidated, gpointer user_data)
{
  update_mode (user_data, !((Bridge *) user_data)->quiet);
}

int
main (int argc, char **argv)
{
  gchar *address = NULL;
  gint vmid = -1, console = 0, timeout = 10;
  gboolean quiet = FALSE, version = FALSE;
  GOptionEntry entries[] = {
    {"address", 'a', 0, G_OPTION_ARG_STRING, &address,
        "D-Bus address of the VM's display bus", "ADDRESS"},
    {"vmid", 'v', 0, G_OPTION_ARG_INT, &vmid,
        "PVE VM whose bus to use (/run/wsh-dbus-display/<vmid>.sock)", "VMID"},
    {"console", 'c', 0, G_OPTION_ARG_INT, &console, "QEMU console index (default 0)", "N"},
    {"timeout", 't', 0, G_OPTION_ARG_INT, &timeout,
        "Seconds to wait for QEMU on the bus (default 10)", "S"},
    {"quiet", 'q', 0, G_OPTION_ARG_NONE, &quiet,
        "Print only errors and the answers to query and sync", NULL},
    {"version", 0, 0, G_OPTION_ARG_NONE, &version, "Print the version", NULL},
    {NULL}
  };
  GOptionContext *ctx = g_option_context_new ("- keyboard and mouse for QEMU's D-Bus display");
  GError *error = NULL;
  Bridge b = { 0 };
  gchar *addr;
  GInputStream *stdin_stream;

  g_option_context_set_summary (ctx,
      "Reads commands from standard input, one per line, and sends them to the keyboard and\n"
      "mouse of a console of QEMU's D-Bus display:\n\n"
      "  key CODE 1|0      a key by its Linux input event code, pressed (1) or released (0)\n"
      "  qkey QNUM 1|0     a key by QEMU's key number\n"
      "  btn BUTTON 1|0    left, middle, right, wheel-up, wheel-down, side, extra (or 0-6)\n"
      "  wheel N           N wheel steps, up if positive\n"
      "  rel DX DY         relative motion\n"
      "  abs X Y [W H]     absolute position in the console's pixels, or scaled from W x H\n"
      "  query             prints the mouse mode and the console's size\n"
      "  sync              prints \"sync N\" once QEMU has answered the N commands so far\n\n"
      "The guest's pointer decides how motion goes (QEMU's IsAbsolute); see qemu-dbus-input(1).");
  g_option_context_add_main_entries (ctx, entries, NULL);
  if (!g_option_context_parse (ctx, &argc, &argv, &error)) {
    g_printerr ("qemu-dbus-input: %s\n", error->message);
    return 2;
  }
  g_option_context_free (ctx);
  if (version) {
    printf ("qemu-dbus-input %s\n", PACKAGE_VERSION);
    return 0;
  }
  addr = qemudbus_resolve_address (address, vmid);
  if (!addr || console < 0 || timeout <= 0) {
    g_printerr ("qemu-dbus-input: give --address or --vmid (see --help)\n");
    return 2;
  }
  b.bus = qemudbus_connect (addr, (guint) timeout * 1000, NULL, &error);
  if (!b.bus) {
    g_printerr ("qemu-dbus-input: %s: %s\n", addr, error->message);
    return 1;
  }
  b.path = g_strdup_printf ("/org/qemu/Display1/Console_%d", console);
  b.mouse = g_dbus_proxy_new_sync (b.bus, G_DBUS_PROXY_FLAGS_DO_NOT_AUTO_START, NULL,
      QEMUDBUS_NAME, b.path, "org.qemu.Display1.Mouse", NULL, &error);
  if (b.mouse)
    b.console = g_dbus_proxy_new_sync (b.bus, G_DBUS_PROXY_FLAGS_DO_NOT_AUTO_START, NULL,
        QEMUDBUS_NAME, b.path, "org.qemu.Display1.Console", NULL, &error);
  if (!b.mouse || !b.console) {
    g_printerr ("qemu-dbus-input: %s on %s: %s\n", b.path, addr, error->message);
    return 1;
  }
  {
    GVariant *v = g_dbus_proxy_get_cached_property (b.mouse, "IsAbsolute");

    if (!v) {
      g_printerr ("qemu-dbus-input: %s on %s has no mouse (org.qemu.Display1.Mouse)\n",
          b.path, addr);
      return 1;
    }
    g_variant_unref (v);
  }
  b.quiet = quiet;
  b.pressed = g_hash_table_new (NULL, NULL);
  g_queue_init (&b.syncs);
  update_mode (&b, FALSE);
  b.px = console_dim (&b, "Width") / 2;
  b.py = console_dim (&b, "Height") / 2;
  g_signal_connect (b.mouse, "g-properties-changed", G_CALLBACK (mouse_changed), &b);
  if (!quiet)
    out ("ready %s mode %s width %u height %u", b.path, b.absolute ? "absolute" : "relative",
        console_dim (&b, "Width"), console_dim (&b, "Height"));

  stdin_stream = g_unix_input_stream_new (0, FALSE);
  b.in = g_data_input_stream_new (stdin_stream);
  g_object_unref (stdin_stream);
  b.loop = g_main_loop_new (NULL, FALSE);
  read_next (&b);
  g_main_loop_run (b.loop);

  g_object_unref (b.in);
  g_object_unref (b.mouse);
  g_object_unref (b.console);
  g_dbus_connection_flush_sync (b.bus, NULL, NULL);
  g_object_unref (b.bus);
  g_hash_table_unref (b.pressed);
  g_free (b.path);
  g_free (addr);
  g_free (address);
  return 0;
}
