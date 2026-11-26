/*
 * qemudbusaudiosrc: the guest's playback through QEMU's D-Bus audio (-audiodev dbus, tied to
 * -display dbus with audiodev=) as a live audio source.
 *
 * The element registers an org.qemu.Display1.AudioOutListener on /org/qemu/Display1/Audio of the
 * VM's bus. QEMU announces each of the guest's playback streams (Init: its format; SetEnabled;
 * SetVolume; Fini) and sends its PCM in Write calls, NSamples frames each (480 by default: 10 ms
 * at 48 kHz). The element follows one stream at a time: the first that writes, until it is
 * disabled or finished. Each Write becomes one buffer in the stream's own format (qemu-server's
 * audio driver dbus: S16LE, 48 kHz, stereo); a change of format renegotiates.
 *
 * Volume: an audio backend that takes the volume itself (as the D-Bus one does) gets the guest
 * mixer's volume and mute in SetVolume instead of PCM scaled by it. With apply-volume (the
 * default) the element scales the samples by it (signed 16-bit PCM; other formats pass as they
 * are), as a sound card would.
 *
 * Silence: QEMU writes only while the guest plays. Between sounds (and before the first) the
 * element outputs silence in the stream's format in real time (silence=true, the default), so
 * the stream has no gaps: downstream, a gap at a sound's start made audiorate (in Wolf's audio
 * pipeline) push all the missing time as silence at once, and the leaky queue before it dropped
 * the sound's first 50-85 ms meanwhile. A silent buffer goes out when no Write came for its 10 ms
 * by the time it ends; while a stream is enabled, or wrote in the last 200 ms, 100 ms later (a
 * busy guest's sound comes late now and then, and that shouldn't cut it up).
 *
 * Timestamps: continuous (each buffer starts where the one before ended), so nothing overlaps
 * and nothing is dropped downstream. The start is the running time the first Write (or silent
 * buffer) arrived at, minus its duration; when the guest's sound comes more than 40 ms later
 * than its continuous time (a pause, without silence=true, or a late guest), it moves forward to
 * that again, and the gap is the downstream's to fill. Sound that runs ahead (QEMU catching up
 * with a burst of Writes) keeps its continuous time; a Write more than 200 ms ahead is dropped.
 *
 * Copyright 2026 WsHosting ENK. License: GPL-3 (see debian/copyright).
 */
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "gstqemudbusaudiosrc.h"
#include "qemudbus.h"

#include <string.h>

GST_DEBUG_CATEGORY_STATIC (gst_qemu_dbus_audio_src_debug);
#define GST_CAT_DEFAULT gst_qemu_dbus_audio_src_debug

#define AUDIO_LISTENER_XML \
  "<node>" \
  " <interface name='org.qemu.Display1.AudioOutListener'>" \
  "  <method name='Init'>" \
  "   <arg type='t' direction='in'/><arg type='y' direction='in'/><arg type='b' direction='in'/>" \
  "   <arg type='b' direction='in'/><arg type='u' direction='in'/><arg type='y' direction='in'/>" \
  "   <arg type='u' direction='in'/><arg type='u' direction='in'/><arg type='b' direction='in'/>" \
  "  </method>" \
  "  <method name='Fini'><arg type='t' direction='in'/></method>" \
  "  <method name='SetEnabled'>" \
  "   <arg type='t' direction='in'/><arg type='b' direction='in'/>" \
  "  </method>" \
  "  <method name='SetVolume'>" \
  "   <arg type='t' direction='in'/><arg type='b' direction='in'/><arg type='ay' direction='in'/>" \
  "  </method>" \
  "  <method name='Write'>" \
  "   <arg type='t' direction='in'/><arg type='ay' direction='in'/>" \
  "  </method>" \
  "  <property name='Interfaces' type='as' access='read'/>" \
  " </interface>" \
  "</node>"

/* Continuous timestamps unless a buffer arrives later than this after the previous one's end */
#define RESYNC_THRESHOLD (40 * GST_MSECOND)
/* A Write further ahead of its arrival than this is dropped */
#define MAX_AHEAD (200 * GST_MSECOND)
/* Silence: buffers of this length; while a stream is enabled or wrote within SILENCE_RECENT,
 * only SILENCE_GRACE later */
#define SILENCE_FRAMES_PER_SECOND 100
#define SILENCE_GRACE (100 * GST_MSECOND)
#define SILENCE_RECENT (200 * GST_MSECOND)
/* What waits for downstream at most; older buffers are dropped */
#define MAX_QUEUED (500 * GST_MSECOND)

enum
{
  PROP_0,
  PROP_ADDRESS,
  PROP_VMID,
  PROP_TIMEOUT,
  PROP_APPLY_VOLUME,
  PROP_SILENCE,
  PROP_STATS,
};

#define DEFAULT_VMID -1
#define DEFAULT_TIMEOUT 10
#define DEFAULT_APPLY_VOLUME TRUE
#define DEFAULT_SILENCE TRUE

static GstStaticPadTemplate src_template = GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC, GST_PAD_ALWAYS,
    GST_STATIC_CAPS ("audio/x-raw, format = (string) " GST_AUDIO_FORMATS_ALL ", "
        "rate = (int) [ 1, MAX ], channels = (int) [ 1, MAX ], layout = (string) interleaved"));

typedef struct
{
  GstAudioInfo info;
  gboolean enabled;
  gboolean mute;
  guint8 volume[8];             /* per channel, 0-255 */
  guint n_volume;
} Stream;

typedef struct
{
  GstBuffer *buf;
  GstAudioInfo info;
  GstClockTime arrival;         /* running time, or NONE */
  gboolean silent;              /* made by the element (silence=true) */
} Chunk;

struct _GstQemuDBusAudioSrc
{
  GstPushSrc parent;

  gchar *address;
  gint vmid;
  guint timeout;
  gboolean apply_volume;
  gboolean silence;

  QemuDBusPeer *peer;
  GDBusNodeInfo *node;

  GMutex lock;
  GCond cond;
  gboolean flushing;
  gboolean eos;
  GHashTable *streams;          /* id -> Stream */
  guint64 active;
  gboolean have_active;
  GQueue chunks;
  GstClockTime queued;
  GstAudioInfo last_info;       /* the newest stream's format, for silence */
  gboolean have_last_info;
  guint n_enabled;              /* streams enabled now */
  GstClockTime last_write;      /* the running time of the newest Write, or NONE */

  GstAudioInfo negotiated;      /* streaming thread only */
  gboolean have_caps;
  GstClockTime next_ts;

  guint64 n_writes, n_bytes, n_dropped, n_other, n_buffers, n_silence, n_resync, n_ahead;
};

#define gst_qemu_dbus_audio_src_parent_class parent_class
G_DEFINE_TYPE (GstQemuDBusAudioSrc, gst_qemu_dbus_audio_src, GST_TYPE_PUSH_SRC);

static void
chunk_free (Chunk * chunk)
{
  gst_buffer_unref (chunk->buf);
  g_free (chunk);
}

static GstClockTime
running_time_now (GstQemuDBusAudioSrc * src)
{
  GstClock *clock = gst_element_get_clock (GST_ELEMENT (src));
  GstClockTime now, base;

  if (!clock)
    return GST_CLOCK_TIME_NONE;
  now = gst_clock_get_time (clock);
  base = gst_element_get_base_time (GST_ELEMENT (src));
  gst_object_unref (clock);
  return now >= base ? now - base : 0;
}

static void
scale_s16 (GstBuffer * buf, const Stream * stream)
{
  GstMapInfo map;
  gint16 *s;
  gsize i, n;
  guint channels = GST_AUDIO_INFO_CHANNELS (&stream->info);

  if (!gst_buffer_map (buf, &map, GST_MAP_READWRITE))
    return;
  s = (gint16 *) map.data;
  n = map.size / 2;
  if (stream->mute) {
    memset (map.data, 0, map.size);
  } else {
    for (i = 0; i < n; i++) {
      guint ch = i % channels;
      guint v = ch < stream->n_volume ? stream->volume[ch] : 255;

      s[i] = (gint16) ((gint32) GINT16_FROM_LE (s[i]) * (gint32) v / 255);
      s[i] = GINT16_TO_LE (s[i]);
    }
  }
  gst_buffer_unmap (buf, &map);
}

static void count_enabled (GstQemuDBusAudioSrc * src);

static void
on_write (GstQemuDBusAudioSrc * src, GVariant * params)
{
  guint64 id;
  GVariant *data;
  const guint8 *bytes;
  gsize n;
  Stream *stream;
  Chunk *chunk;
  gint bpf;

  g_variant_get_child (params, 0, "t", &id);
  data = g_variant_get_child_value (params, 1);
  bytes = g_variant_get_fixed_array (data, &n, 1);

  g_mutex_lock (&src->lock);
  src->n_writes++;
  stream = g_hash_table_lookup (src->streams, &id);
  if (!stream) {
    src->n_other++;
    goto out;
  }
  if (!src->have_active) {
    src->active = id;
    src->have_active = TRUE;
    GST_INFO_OBJECT (src, "following stream %" G_GUINT64_FORMAT ": %d Hz, %d channels, %s",
        id, GST_AUDIO_INFO_RATE (&stream->info), GST_AUDIO_INFO_CHANNELS (&stream->info),
        GST_AUDIO_INFO_NAME (&stream->info));
  }
  bpf = GST_AUDIO_INFO_BPF (&stream->info);
  if (src->active != id || !bpf || n % bpf) {
    src->n_other++;
    goto out;
  }
  if (!stream->enabled) {
    /* it plays, whether or not SetEnabled said so */
    stream->enabled = TRUE;
    count_enabled (src);
  }
  src->n_bytes += n;
  chunk = g_new0 (Chunk, 1);
  chunk->buf = gst_buffer_new_memdup (bytes, n);
  chunk->info = stream->info;
  chunk->arrival = running_time_now (src);
  src->last_write = chunk->arrival;
  GST_LOG_OBJECT (src, "Write of %" G_GSIZE_FORMAT " bytes at %" GST_TIME_FORMAT, n,
      GST_TIME_ARGS (chunk->arrival));
  if (src->apply_volume && GST_AUDIO_INFO_FORMAT (&stream->info) == GST_AUDIO_FORMAT_S16LE)
    scale_s16 (chunk->buf, stream);
  g_queue_push_tail (&src->chunks, chunk);
  src->queued += gst_util_uint64_scale (n / bpf, GST_SECOND, GST_AUDIO_INFO_RATE (&stream->info));
  /* downstream isn't taking them: keep the newest */
  while (src->queued > MAX_QUEUED && src->chunks.length > 1) {
    Chunk *old = g_queue_pop_head (&src->chunks);

    src->queued -= gst_util_uint64_scale (gst_buffer_get_size (old->buf) /
        GST_AUDIO_INFO_BPF (&old->info), GST_SECOND, GST_AUDIO_INFO_RATE (&old->info));
    src->n_dropped++;
    chunk_free (old);
  }
  g_cond_broadcast (&src->cond);
out:
  g_mutex_unlock (&src->lock);
  g_variant_unref (data);
}

static void
on_init (GstQemuDBusAudioSrc * src, GVariant * params)
{
  guint64 id;
  guint8 bits, channels;
  gboolean is_signed, is_float, be;
  guint32 freq, bpf, bps;
  GstAudioFormat format;
  Stream *stream;
  guint64 *key;

  g_variant_get (params, "(tybbuyuub)", &id, &bits, &is_signed, &is_float, &freq, &channels,
      &bpf, &bps, &be);
  if (is_float)
    format = bits == 64 ? (be ? GST_AUDIO_FORMAT_F64BE : GST_AUDIO_FORMAT_F64LE)
        : (be ? GST_AUDIO_FORMAT_F32BE : GST_AUDIO_FORMAT_F32LE);
  else
    format = gst_audio_format_build_integer (is_signed, be ? G_BIG_ENDIAN : G_LITTLE_ENDIAN,
        bits, bits);
  if (format == GST_AUDIO_FORMAT_UNKNOWN || !freq || !channels) {
    GST_WARNING_OBJECT (src, "stream %" G_GUINT64_FORMAT ": %u-bit %s%s, %u Hz, %u channels: "
        "not taken", id, bits, is_float ? "float" : is_signed ? "signed" : "unsigned",
        be ? " big-endian" : "", freq, channels);
    return;
  }
  stream = g_new0 (Stream, 1);
  gst_audio_info_set_format (&stream->info, format, freq, channels, NULL);
  /* enabled with SetEnabled */
  stream->enabled = FALSE;
  stream->n_volume = 0;
  key = g_new (guint64, 1);
  *key = id;
  g_mutex_lock (&src->lock);
  g_hash_table_replace (src->streams, key, stream);
  src->last_info = stream->info;
  src->have_last_info = TRUE;
  g_mutex_unlock (&src->lock);
  GST_INFO_OBJECT (src, "stream %" G_GUINT64_FORMAT ": %s, %u Hz, %u channels", id,
      gst_audio_format_to_string (format), freq, channels);
}

/* under lock */
static void
count_enabled (GstQemuDBusAudioSrc * src)
{
  GHashTableIter iter;
  gpointer value;

  src->n_enabled = 0;
  g_hash_table_iter_init (&iter, src->streams);
  while (g_hash_table_iter_next (&iter, NULL, &value))
    if (((Stream *) value)->enabled)
      src->n_enabled++;
}

static void
on_fini (GstQemuDBusAudioSrc * src, guint64 id)
{
  g_mutex_lock (&src->lock);
  g_hash_table_remove (src->streams, &id);
  count_enabled (src);
  if (src->have_active && src->active == id)
    src->have_active = FALSE;
  g_mutex_unlock (&src->lock);
}

static void
on_set_enabled (GstQemuDBusAudioSrc * src, GVariant * params)
{
  guint64 id;
  gboolean enabled;
  Stream *stream;

  g_variant_get (params, "(tb)", &id, &enabled);
  g_mutex_lock (&src->lock);
  stream = g_hash_table_lookup (src->streams, &id);
  if (stream)
    stream->enabled = enabled;
  if (!enabled && src->have_active && src->active == id)
    src->have_active = FALSE;
  count_enabled (src);
  g_cond_broadcast (&src->cond);
  g_mutex_unlock (&src->lock);
  GST_DEBUG_OBJECT (src, "stream %" G_GUINT64_FORMAT ": %s", id, enabled ? "enabled" : "disabled");
}

static void
on_set_volume (GstQemuDBusAudioSrc * src, GVariant * params)
{
  guint64 id;
  gboolean mute;
  GVariant *vol;
  const guint8 *v;
  gsize n;
  Stream *stream;

  g_variant_get_child (params, 0, "t", &id);
  g_variant_get_child (params, 1, "b", &mute);
  vol = g_variant_get_child_value (params, 2);
  v = g_variant_get_fixed_array (vol, &n, 1);
  g_mutex_lock (&src->lock);
  stream = g_hash_table_lookup (src->streams, &id);
  if (stream) {
    stream->mute = mute;
    stream->n_volume = MIN (n, G_N_ELEMENTS (stream->volume));
    memcpy (stream->volume, v, stream->n_volume);
  }
  g_mutex_unlock (&src->lock);
  GST_DEBUG_OBJECT (src, "stream %" G_GUINT64_FORMAT ": mute %d, volume %u/%u", id, mute,
      n > 0 ? v[0] : 255, n > 1 ? v[1] : 255);
  g_variant_unref (vol);
}

static void
listener_method (GDBusConnection * conn, const gchar * sender, const gchar * path,
    const gchar * iface, const gchar * method, GVariant * params, GDBusMethodInvocation * inv,
    gpointer user_data)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (user_data);

  if (!strcmp (method, "Write")) {
    on_write (src, params);
  } else if (!strcmp (method, "Init")) {
    on_init (src, params);
  } else if (!strcmp (method, "Fini")) {
    guint64 id;

    g_variant_get (params, "(t)", &id);
    on_fini (src, id);
  } else if (!strcmp (method, "SetEnabled")) {
    on_set_enabled (src, params);
  } else if (!strcmp (method, "SetVolume")) {
    on_set_volume (src, params);
  }
  g_dbus_method_invocation_return_value (inv, NULL);
}

static GVariant *
listener_get_property (GDBusConnection * conn, const gchar * sender, const gchar * path,
    const gchar * iface, const gchar * name, GError ** error, gpointer user_data)
{
  return g_variant_new_strv (NULL, 0);
}

static const GDBusInterfaceVTable listener_vtable = {
  .method_call = listener_method,
  .get_property = listener_get_property,
};

static void
on_closed (gpointer user_data)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (user_data);

  GST_INFO_OBJECT (src, "QEMU closed the connection: end of stream");
  g_mutex_lock (&src->lock);
  src->eos = TRUE;
  g_cond_broadcast (&src->cond);
  g_mutex_unlock (&src->lock);
}

static void
reset (GstQemuDBusAudioSrc * src)
{
  Chunk *chunk;

  g_hash_table_remove_all (src->streams);
  while ((chunk = g_queue_pop_head (&src->chunks)))
    chunk_free (chunk);
  src->queued = 0;
  src->have_active = FALSE;
  src->have_last_info = FALSE;
  src->n_enabled = 0;
  src->last_write = GST_CLOCK_TIME_NONE;
}

static gboolean
gst_qemu_dbus_audio_src_start (GstBaseSrc * bsrc)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (bsrc);
  GError *error = NULL;
  gchar *address;
  GDBusInterfaceInfo *interfaces[2];
  QemuDBusPeerConfig config = { 0 };

  address = qemudbus_resolve_address (src->address, src->vmid);
  if (!address) {
    GST_ELEMENT_ERROR (src, RESOURCE, SETTINGS, ("No D-Bus address"),
        ("set address (e.g. unix:path=/run/wsh-dbus-display/<vmid>.sock) or vmid"));
    return FALSE;
  }
  g_mutex_lock (&src->lock);
  reset (src);
  src->eos = FALSE;
  src->flushing = FALSE;
  src->n_writes = src->n_bytes = src->n_dropped = src->n_other = src->n_buffers = 0;
  src->n_silence = src->n_resync = src->n_ahead = 0;
  g_mutex_unlock (&src->lock);
  src->have_caps = FALSE;
  src->next_ts = GST_CLOCK_TIME_NONE;

  interfaces[0] = src->node->interfaces[0];
  interfaces[1] = NULL;
  config.address = address;
  config.object_path = "/org/qemu/Display1/Audio";
  config.interface = "org.qemu.Display1.Audio";
  config.method = "RegisterOutListener";
  config.listener_path = "/org/qemu/Display1/AudioOutListener";
  config.listener_interfaces = interfaces;
  config.vtable = &listener_vtable;
  config.user_data = src;
  config.closed = on_closed;
  config.timeout_ms = src->timeout * 1000;
  src->peer = qemudbus_peer_start (&config, &error);
  if (!src->peer) {
    GST_ELEMENT_ERROR (src, RESOURCE, OPEN_READ, ("Can't listen to QEMU's D-Bus audio"),
        ("%s: %s (is the VM's audio driver dbus, -audiodev dbus with -display dbus,audiodev=?)",
            address, error->message));
    g_error_free (error);
    g_free (address);
    return FALSE;
  }
  GST_INFO_OBJECT (src, "listening on %s", address);
  g_free (address);
  return TRUE;
}

static gchar *
stats_string (GstQemuDBusAudioSrc * src)
{
  return g_strdup_printf ("writes=%" G_GUINT64_FORMAT " bytes=%" G_GUINT64_FORMAT
      " buffers=%" G_GUINT64_FORMAT " silent-buffers=%" G_GUINT64_FORMAT " dropped=%"
      G_GUINT64_FORMAT " ahead-dropped=%" G_GUINT64_FORMAT " resyncs=%" G_GUINT64_FORMAT
      " other-streams=%" G_GUINT64_FORMAT, src->n_writes, src->n_bytes, src->n_buffers,
      src->n_silence, src->n_dropped, src->n_ahead, src->n_resync, src->n_other);
}

static gboolean
gst_qemu_dbus_audio_src_stop (GstBaseSrc * bsrc)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (bsrc);
  gchar *stats;

  qemudbus_peer_stop (src->peer);
  src->peer = NULL;
  g_mutex_lock (&src->lock);
  stats = stats_string (src);
  reset (src);
  g_mutex_unlock (&src->lock);
  GST_INFO_OBJECT (src, "stopped: %s", stats);
  g_free (stats);
  return TRUE;
}

static gboolean
gst_qemu_dbus_audio_src_unlock (GstBaseSrc * bsrc)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (bsrc);

  g_mutex_lock (&src->lock);
  src->flushing = TRUE;
  g_cond_broadcast (&src->cond);
  g_mutex_unlock (&src->lock);
  return TRUE;
}

static gboolean
gst_qemu_dbus_audio_src_unlock_stop (GstBaseSrc * bsrc)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (bsrc);

  g_mutex_lock (&src->lock);
  src->flushing = FALSE;
  g_mutex_unlock (&src->lock);
  return TRUE;
}

/* The caps follow the stream: set in create() with its first buffer */
static gboolean
gst_qemu_dbus_audio_src_negotiate (GstBaseSrc * bsrc)
{
  return TRUE;
}

static gboolean
gst_qemu_dbus_audio_src_query (GstBaseSrc * bsrc, GstQuery * query)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (bsrc);

  if (GST_QUERY_TYPE (query) == GST_QUERY_LATENCY) {
    /* one Write: QEMU's NSamples (480 by default) at the stream's rate, 10 ms at 48 kHz */
    GstClockTime min = 10 * GST_MSECOND;

    if (src->have_caps)
      min = gst_util_uint64_scale (480, GST_SECOND, GST_AUDIO_INFO_RATE (&src->negotiated));
    gst_query_set_latency (query, TRUE, min, GST_CLOCK_TIME_NONE);
    return TRUE;
  }
  return GST_BASE_SRC_CLASS (parent_class)->query (bsrc, query);
}

/* A buffer of silence in this format, frames long */
static GstBuffer *
silence_buffer (const GstAudioInfo * info, guint64 frames)
{
  GstBuffer *buf = gst_buffer_new_allocate (NULL, frames * GST_AUDIO_INFO_BPF (info), NULL);
  GstMapInfo map;

  if (gst_buffer_map (buf, &map, GST_MAP_WRITE)) {
    gst_audio_format_info_fill_silence (info->finfo, map.data, map.size);
    gst_buffer_unmap (buf, &map);
  }
  return buf;
}

/*
 * The next buffer (under lock): the oldest Write, or with silence=true a silent buffer once its
 * time is over and no Write came for it; NULL at EOS or when flushing (*ret says which).
 */
static Chunk *
next_chunk (GstQemuDBusAudioSrc * src, GstFlowReturn * ret)
{
  for (;;) {
    GstClockTime now, due, duration;
    const GstAudioInfo *info;
    Chunk *chunk;
    guint64 frames;

    if (src->flushing) {
      *ret = GST_FLOW_FLUSHING;
      return NULL;
    }
    if (src->chunks.length) {
      chunk = g_queue_pop_head (&src->chunks);
      frames = gst_buffer_get_size (chunk->buf) / GST_AUDIO_INFO_BPF (&chunk->info);
      duration = gst_util_uint64_scale (frames, GST_SECOND, GST_AUDIO_INFO_RATE (&chunk->info));
      src->queued = src->queued > duration ? src->queued - duration : 0;
      src->n_buffers++;
      return chunk;
    }
    if (src->eos) {
      *ret = GST_FLOW_EOS;
      return NULL;
    }
    now = GST_CLOCK_TIME_NONE;
    if (src->silence && src->have_last_info)
      now = running_time_now (src);
    if (!GST_CLOCK_TIME_IS_VALID (now)) {
      g_cond_wait (&src->cond, &src->lock);
      continue;
    }
    /* silence, in the negotiated format (the newest stream's before the first buffer) */
    info = src->have_caps ? &src->negotiated : &src->last_info;
    frames = MAX (1, GST_AUDIO_INFO_RATE (info) / SILENCE_FRAMES_PER_SECOND);
    duration = gst_util_uint64_scale (frames, GST_SECOND, GST_AUDIO_INFO_RATE (info));
    if (!GST_CLOCK_TIME_IS_VALID (src->next_ts))
      src->next_ts = now;
    due = src->next_ts + duration;
    if (src->n_enabled || (GST_CLOCK_TIME_IS_VALID (src->last_write)
            && now < src->last_write + SILENCE_RECENT))
      due += SILENCE_GRACE;
    if (now < due) {
      g_cond_wait_until (&src->cond, &src->lock,
          g_get_monotonic_time () + (gint64) ((due - now) / GST_USECOND) + 1);
      continue;
    }
    chunk = g_new0 (Chunk, 1);
    chunk->buf = silence_buffer (info, frames);
    chunk->info = *info;
    chunk->arrival = GST_CLOCK_TIME_NONE;
    chunk->silent = TRUE;
    src->n_silence++;
    GST_LOG_OBJECT (src, "silence at %" GST_TIME_FORMAT " (now %" GST_TIME_FORMAT ", %u enabled)",
        GST_TIME_ARGS (src->next_ts), GST_TIME_ARGS (now), src->n_enabled);
    return chunk;
  }
}

static GstFlowReturn
gst_qemu_dbus_audio_src_create (GstPushSrc * psrc, GstBuffer ** outbuf)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (psrc);
  GstFlowReturn ret = GST_FLOW_OK;
  Chunk *chunk;
  GstClockTime duration, ts, from_arrival;
  guint64 frames;

  for (;;) {
    g_mutex_lock (&src->lock);
    chunk = next_chunk (src, &ret);
    g_mutex_unlock (&src->lock);
    if (!chunk)
      return ret;
    frames = gst_buffer_get_size (chunk->buf) / GST_AUDIO_INFO_BPF (&chunk->info);
    duration = gst_util_uint64_scale (frames, GST_SECOND, GST_AUDIO_INFO_RATE (&chunk->info));

    if (!src->have_caps || !gst_audio_info_is_equal (&chunk->info, &src->negotiated)) {
      GstCaps *caps = gst_audio_info_to_caps (&chunk->info);

      GST_INFO_OBJECT (src, "stream now %" GST_PTR_FORMAT, caps);
      if (!gst_base_src_set_caps (GST_BASE_SRC (src), caps)) {
        gst_caps_unref (caps);
        chunk_free (chunk);
        GST_ELEMENT_ERROR (src, CORE, NEGOTIATION, (NULL),
            ("downstream doesn't take the guest's sound as it comes"));
        return GST_FLOW_NOT_NEGOTIATED;
      }
      gst_caps_unref (caps);
      if (src->have_caps && !chunk->silent)
        src->next_ts = GST_CLOCK_TIME_NONE;
      src->negotiated = chunk->info;
      src->have_caps = TRUE;
    }

    /* continuous; forward to the arrival when the sound comes late; never backwards */
    from_arrival = GST_CLOCK_TIME_NONE;
    if (GST_CLOCK_TIME_IS_VALID (chunk->arrival))
      from_arrival = chunk->arrival > duration ? chunk->arrival - duration : 0;
    if (!GST_CLOCK_TIME_IS_VALID (src->next_ts)) {
      ts = from_arrival;
    } else if (!GST_CLOCK_TIME_IS_VALID (from_arrival)) {
      ts = src->next_ts;
    } else if (from_arrival > src->next_ts + RESYNC_THRESHOLD) {
      GST_DEBUG_OBJECT (src, "resync: %" GST_TIME_FORMAT " instead of %" GST_TIME_FORMAT,
          GST_TIME_ARGS (from_arrival), GST_TIME_ARGS (src->next_ts));
      ts = from_arrival;
      g_mutex_lock (&src->lock);
      src->n_resync++;
      g_mutex_unlock (&src->lock);
    } else if (src->next_ts > from_arrival + MAX_AHEAD) {
      GST_DEBUG_OBJECT (src, "%" GST_TIME_FORMAT " ahead of its arrival: dropped",
          GST_TIME_ARGS (src->next_ts - from_arrival));
      chunk_free (chunk);
      g_mutex_lock (&src->lock);
      src->n_ahead++;
      g_mutex_unlock (&src->lock);
      continue;
    } else {
      ts = src->next_ts;
    }
    GST_BUFFER_PTS (chunk->buf) = ts;
    GST_BUFFER_DURATION (chunk->buf) = duration;
    if (GST_CLOCK_TIME_IS_VALID (ts))
      src->next_ts = ts + duration;
    *outbuf = chunk->buf;
    chunk->buf = NULL;
    g_free (chunk);
    return GST_FLOW_OK;
  }
}

static void
gst_qemu_dbus_audio_src_set_property (GObject * object, guint prop_id, const GValue * value,
    GParamSpec * pspec)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (object);

  switch (prop_id) {
    case PROP_ADDRESS:
      g_free (src->address);
      src->address = g_value_dup_string (value);
      break;
    case PROP_VMID:
      src->vmid = g_value_get_int (value);
      break;
    case PROP_TIMEOUT:
      src->timeout = g_value_get_uint (value);
      break;
    case PROP_APPLY_VOLUME:
      src->apply_volume = g_value_get_boolean (value);
      break;
    case PROP_SILENCE:
      src->silence = g_value_get_boolean (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_qemu_dbus_audio_src_get_property (GObject * object, guint prop_id, GValue * value,
    GParamSpec * pspec)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (object);

  switch (prop_id) {
    case PROP_ADDRESS:
      g_value_set_string (value, src->address);
      break;
    case PROP_VMID:
      g_value_set_int (value, src->vmid);
      break;
    case PROP_TIMEOUT:
      g_value_set_uint (value, src->timeout);
      break;
    case PROP_APPLY_VOLUME:
      g_value_set_boolean (value, src->apply_volume);
      break;
    case PROP_SILENCE:
      g_value_set_boolean (value, src->silence);
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
gst_qemu_dbus_audio_src_finalize (GObject * object)
{
  GstQemuDBusAudioSrc *src = GST_QEMU_DBUS_AUDIO_SRC (object);

  qemudbus_peer_stop (src->peer);
  reset (src);
  g_hash_table_unref (src->streams);
  g_dbus_node_info_unref (src->node);
  g_free (src->address);
  g_mutex_clear (&src->lock);
  g_cond_clear (&src->cond);
  G_OBJECT_CLASS (parent_class)->finalize (object);
}

static void
gst_qemu_dbus_audio_src_class_init (GstQemuDBusAudioSrcClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *element_class = GST_ELEMENT_CLASS (klass);
  GstBaseSrcClass *basesrc_class = GST_BASE_SRC_CLASS (klass);
  GstPushSrcClass *pushsrc_class = GST_PUSH_SRC_CLASS (klass);

  gobject_class->set_property = gst_qemu_dbus_audio_src_set_property;
  gobject_class->get_property = gst_qemu_dbus_audio_src_get_property;
  gobject_class->finalize = gst_qemu_dbus_audio_src_finalize;

  g_object_class_install_property (gobject_class, PROP_ADDRESS,
      g_param_spec_string ("address", "Address",
          "D-Bus address of the VM's display bus (e.g. unix:path=/run/wsh-dbus-display/130.sock)",
          NULL, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_VMID,
      g_param_spec_int ("vmid", "VM ID",
          "PVE VM whose bus to use (/run/wsh-dbus-display/<vmid>.sock) when address is unset",
          -1, G_MAXINT, DEFAULT_VMID,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_TIMEOUT,
      g_param_spec_uint ("timeout", "Timeout",
          "Seconds to wait for QEMU on the bus and for the listener's setup", 1, 3600,
          DEFAULT_TIMEOUT, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_APPLY_VOLUME,
      g_param_spec_boolean ("apply-volume", "Apply volume",
          "Scale the samples by the guest mixer's volume and mute, which QEMU passes separately "
          "(signed 16-bit PCM)", DEFAULT_APPLY_VOLUME,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_SILENCE,
      g_param_spec_boolean ("silence", "Silence",
          "Output silence in real time while the guest plays nothing, so the stream has no gaps "
          "(an encoder or audiorate downstream gets a continuous stream)", DEFAULT_SILENCE,
          G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS | GST_PARAM_MUTABLE_READY));
  g_object_class_install_property (gobject_class, PROP_STATS,
      g_param_spec_string ("stats", "Statistics", "What QEMU sent and how many buffers went out",
          NULL, G_PARAM_READABLE | G_PARAM_STATIC_STRINGS));

  gst_element_class_set_static_metadata (element_class, "QEMU D-Bus audio source",
      "Source/Audio", "The guest's playback through QEMU's D-Bus audio (-audiodev dbus)",
      "WsHosting ENK <debian@wsh.no>");
  gst_element_class_add_static_pad_template (element_class, &src_template);

  basesrc_class->start = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_start);
  basesrc_class->stop = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_stop);
  basesrc_class->unlock = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_unlock);
  basesrc_class->unlock_stop = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_unlock_stop);
  basesrc_class->negotiate = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_negotiate);
  basesrc_class->query = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_query);
  pushsrc_class->create = GST_DEBUG_FUNCPTR (gst_qemu_dbus_audio_src_create);

  GST_DEBUG_CATEGORY_INIT (gst_qemu_dbus_audio_src_debug, "qemudbusaudiosrc", 0,
      "QEMU D-Bus audio source");
}

static void
gst_qemu_dbus_audio_src_init (GstQemuDBusAudioSrc * src)
{
  src->vmid = DEFAULT_VMID;
  src->timeout = DEFAULT_TIMEOUT;
  src->apply_volume = DEFAULT_APPLY_VOLUME;
  src->silence = DEFAULT_SILENCE;
  src->node = g_dbus_node_info_new_for_xml (AUDIO_LISTENER_XML, NULL);
  g_assert (src->node);
  src->streams = g_hash_table_new_full (g_int64_hash, g_int64_equal, g_free, g_free);
  g_queue_init (&src->chunks);
  g_mutex_init (&src->lock);
  g_cond_init (&src->cond);
  gst_base_src_set_live (GST_BASE_SRC (src), TRUE);
  gst_base_src_set_format (GST_BASE_SRC (src), GST_FORMAT_TIME);
}
