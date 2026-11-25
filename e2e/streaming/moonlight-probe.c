/*
 * wsh-moonlight-probe: a measuring Moonlight client for e2e/streaming (stage 3d).
 *
 * Built in the client image against moonlight-embedded's libgamestream (HTTP, pairing keys, app
 * launch) and moonlight-common-c (RTSP, the video, audio and control streams), at the commits the
 * Dockerfile pins. It streams like moonlight-embedded, but instead of showing the picture it
 * decodes it in software (libavcodec) and reports every frame with its times, so a harness can
 * measure what a person in front of a client would see:
 *
 *   frame N RX_US DEC_US NUM TYPE BYTES WxH CHANGED C0 .. C7
 *       one decoded frame: when its data was complete (RX) and when it was decoded (DEC), both
 *       CLOCK_REALTIME in microseconds (the same clock as the harness and the guest's host); the
 *       host's frame number and type (1 = IDR); how much of the picture changed since the last
 *       frame (per mille of a grid of luma samples, every 16th pixel of every 16th row, that moved
 *       by more than 24 levels: 0 for a repeated picture, whatever the encoder's noise); and the colour (RRGGBB) at eight points across the bottom of the picture
 *       (x = (i + 0.5) / 8 of the width, y = 95 % of the height: one point in each of wisp
 *       fbtest's colour bars)
 *   audio-onset US / audio-quiet US
 *       the guest's sound started (a 5 ms packet louder than RMS 1000) or stopped
 *   sent US CMD   an input command went to the host at US
 *   stage NAME / connected / terminated CODE / error TEXT
 *
 * The audio is decoded (libopus) into OUTDIR/sound.wav (48 kHz, S16LE, the stream's channels).
 *
 * Commands on standard input, one per line:
 *   key VK down|up              a Windows virtual-key code (decimal or 0x..), as Moonlight sends
 *   move DX DY                  relative pointer motion
 *   pos X Y W H                 absolute pointer position X,Y on a W x H reference
 *   button left|middle|right down|up
 *   scroll N                    wheel clicks
 *   snap PATH                   write the next decoded frame to PATH as a binary PPM
 *   quit                        stop the stream (also at end of input)
 *
 * usage: wsh-moonlight-probe [--width W] [--height H] [--fps F] [--bitrate KBPS] HOST KEYDIR APP OUTDIR
 *
 * KEYDIR holds the client's key and certificate from `moonlight pair` (moonlight-embedded keeps
 * them in ~/.cache/moonlight), so the host knows this client as the paired one.
 */
#define _GNU_SOURCE
#include <client.h>
#include <errors.h>
#include <Limelight.h>

#include <getopt.h>
#include <libavcodec/avcodec.h>
#include <libswscale/swscale.h>
#include <math.h>
#include <opus_multistream.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static pthread_mutex_t out_lock = PTHREAD_MUTEX_INITIALIZER;
static volatile int running = 1;

static uint64_t now_us(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_REALTIME, &ts);
	return (uint64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static void out(const char *fmt, ...)
{
	va_list ap;

	pthread_mutex_lock(&out_lock);
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	fflush(stdout);
	pthread_mutex_unlock(&out_lock);
}

/* Video */

static AVCodecContext *vctx;
static AVFrame *vframe;
static AVPacket *vpkt;
static unsigned char *vbuf;
static size_t vbuf_size;
static unsigned long frames;
static unsigned char grid[65536];
static char snap_path[1024];
static pthread_mutex_t snap_lock = PTHREAD_MUTEX_INITIALIZER;

static int video_setup(int format, int width, int height, int fps, void *context, int flags)
{
	const AVCodec *codec;

	(void)context;
	(void)flags;
	if (!(format & VIDEO_FORMAT_MASK_H264)) {
		out("error video format 0x%x (only H.264 is decoded)\n", format);
		return -1;
	}
	codec = avcodec_find_decoder(AV_CODEC_ID_H264);
	vctx = codec ? avcodec_alloc_context3(codec) : NULL;
	if (!vctx)
		return -1;
	vctx->flags |= AV_CODEC_FLAG_LOW_DELAY;
	vctx->thread_count = 1;
	if (avcodec_open2(vctx, codec, NULL) < 0)
		return -1;
	vframe = av_frame_alloc();
	vpkt = av_packet_alloc();
	out("video %dx%d %d fps\n", width, height, fps);
	return 0;
}

static void video_cleanup(void)
{
	avcodec_free_context(&vctx);
	av_frame_free(&vframe);
	av_packet_free(&vpkt);
	free(vbuf);
	vbuf = NULL;
}

static void yuv_at(const AVFrame *f, int x, int y, unsigned char rgb[3])
{
	/* BT.601, limited range: what moonlight-common-c asks for by default */
	double Y = f->data[0][y * f->linesize[0] + x] - 16;
	double U = f->data[1][(y / 2) * f->linesize[1] + x / 2] - 128;
	double V = f->data[2][(y / 2) * f->linesize[2] + x / 2] - 128;
	double c[3] = { 1.164 * Y + 1.596 * V, 1.164 * Y - 0.392 * U - 0.813 * V, 1.164 * Y + 2.017 * U };

	for (int i = 0; i < 3; i++)
		rgb[i] = c[i] < 0 ? 0 : c[i] > 255 ? 255 : (unsigned char)lrint(c[i]);
}

static void write_ppm(const char *path, const AVFrame *f)
{
	struct SwsContext *sws = sws_getContext(f->width, f->height, f->format, f->width, f->height,
						AV_PIX_FMT_RGB24, SWS_POINT, NULL, NULL, NULL);
	unsigned char *rgb = malloc((size_t)f->width * f->height * 3);
	uint8_t *dst[1] = { rgb };
	int stride[1] = { f->width * 3 };
	FILE *fp;

	if (!sws || !rgb) {
		out("error snap %s: no memory or no converter\n", path);
		goto done;
	}
	sws_scale(sws, (const uint8_t *const *)f->data, f->linesize, 0, f->height, dst, stride);
	fp = fopen(path, "wb");
	if (!fp) {
		out("error snap %s: cannot write\n", path);
		goto done;
	}
	fprintf(fp, "P6\n%d %d\n255\n", f->width, f->height);
	fwrite(rgb, 3, (size_t)f->width * f->height, fp);
	fclose(fp);
	out("snap %s\n", path);
done:
	sws_freeContext(sws);
	free(rgb);
}

static int video_submit(PDECODE_UNIT du)
{
	uint64_t rx = now_us(), dec;
	size_t len = 0;
	char colours[8 * 7 + 1];
	unsigned changed = 0, points = 0;

	if (vbuf_size < (size_t)du->fullLength + AV_INPUT_BUFFER_PADDING_SIZE) {
		vbuf_size = du->fullLength + AV_INPUT_BUFFER_PADDING_SIZE;
		vbuf = realloc(vbuf, vbuf_size);
		if (!vbuf)
			return DR_NEED_IDR;
	}
	for (PLENTRY e = du->bufferList; e; e = e->next) {
		memcpy(vbuf + len, e->data, e->length);
		len += e->length;
	}
	memset(vbuf + len, 0, AV_INPUT_BUFFER_PADDING_SIZE);
	vpkt->data = vbuf;
	vpkt->size = (int)len;
	if (avcodec_send_packet(vctx, vpkt) < 0) {
		out("error decode frame %d\n", du->frameNumber);
		return DR_NEED_IDR;
	}
	while (avcodec_receive_frame(vctx, vframe) == 0) {
		const AVFrame *f = vframe;

		dec = now_us();
		/* a grid of luma samples, every 16th pixel of every 16th row, against the last frame */
		for (int y = 8; y < f->height; y += 16)
			for (int x = 8; x < f->width; x += 16) {
				unsigned char v = f->data[0][y * f->linesize[0] + x];

				if (points < sizeof(grid)) {
					changed += abs((int)v - grid[points]) > 24;
					grid[points] = v;
				}
				points++;
			}
		for (int i = 0; i < 8; i++) {
			unsigned char rgb[3];

			yuv_at(f, (int)((i + 0.5) * f->width / 8), f->height * 95 / 100, rgb);
			snprintf(colours + i * 7, 8, " %02x%02x%02x", rgb[0], rgb[1], rgb[2]);
		}
		out("frame %lu %llu %llu %d %d %zu %dx%d %u%s\n", frames++, (unsigned long long)rx,
		    (unsigned long long)dec, du->frameNumber, du->frameType, len, f->width, f->height,
		    points ? changed * 1000 / points : 0, colours);
		pthread_mutex_lock(&snap_lock);
		if (snap_path[0]) {
			write_ppm(snap_path, f);
			snap_path[0] = 0;
		}
		pthread_mutex_unlock(&snap_lock);
	}
	return DR_OK;
}

static DECODER_RENDERER_CALLBACKS video_callbacks = {
	.setup = video_setup,
	.cleanup = video_cleanup,
	.submitDecodeUnit = video_submit,
	.capabilities = CAPABILITY_DIRECT_SUBMIT,
};

/* Audio */

static OpusMSDecoder *adec;
static FILE *wav;
static int achannels, aframe;
static uint32_t wav_bytes;
static int16_t *apcm;
static int loud;
static char wav_path[1100];

static void wav_header(void)
{
	uint32_t rate = 48000, byte_rate = rate * achannels * 2, riff = 36 + wav_bytes, fmt_size = 16;
	uint16_t pcm = 1, ch = achannels, align = achannels * 2, bits = 16;

	fseek(wav, 0, SEEK_SET);
	fwrite("RIFF", 1, 4, wav);
	fwrite(&riff, 4, 1, wav);
	fwrite("WAVEfmt ", 1, 8, wav);
	fwrite(&fmt_size, 4, 1, wav);
	fwrite(&pcm, 2, 1, wav);
	fwrite(&ch, 2, 1, wav);
	fwrite(&rate, 4, 1, wav);
	fwrite(&byte_rate, 4, 1, wav);
	fwrite(&align, 2, 1, wav);
	fwrite(&bits, 2, 1, wav);
	fwrite("data", 1, 4, wav);
	fwrite(&wav_bytes, 4, 1, wav);
	fseek(wav, 0, SEEK_END);
	fflush(wav);
}

static int audio_init(int config, const POPUS_MULTISTREAM_CONFIGURATION oc, void *context, int flags)
{
	int err;

	(void)config;
	(void)context;
	(void)flags;
	achannels = oc->channelCount;
	aframe = oc->samplesPerFrame;
	adec = opus_multistream_decoder_create(oc->sampleRate, oc->channelCount, oc->streams,
					      oc->coupledStreams, oc->mapping, &err);
	apcm = malloc(sizeof(int16_t) * aframe * achannels);
	wav = fopen(wav_path, "wb");
	if (!adec || !apcm || !wav) {
		out("error audio init (opus %d)\n", err);
		return -1;
	}
	wav_header();
	out("audio %d Hz %d channels %d samples a packet\n", oc->sampleRate, achannels, aframe);
	return 0;
}

static void audio_cleanup(void)
{
	if (wav) {
		wav_header();
		fclose(wav);
		wav = NULL;
	}
	if (adec)
		opus_multistream_decoder_destroy(adec);
	adec = NULL;
	free(apcm);
	apcm = NULL;
}

static void audio_sample(char *data, int length)
{
	int n = opus_multistream_decode(adec, (unsigned char *)data, length, apcm, aframe, 0);
	double sum = 0;

	if (n <= 0)
		return;
	fwrite(apcm, sizeof(int16_t) * achannels, n, wav);
	wav_bytes += n * achannels * 2;
	for (int i = 0; i < n * achannels; i += achannels)
		sum += (double)apcm[i] * apcm[i];
	if (!loud && sqrt(sum / n) > 1000) {
		loud = 1;
		out("audio-onset %llu\n", (unsigned long long)now_us());
	} else if (loud && sqrt(sum / n) < 100) {
		loud = 0;
		out("audio-quiet %llu\n", (unsigned long long)now_us());
	}
	if ((wav_bytes / (n * achannels * 2)) % 200 == 0)
		wav_header();
}

static AUDIO_RENDERER_CALLBACKS audio_callbacks = {
	.init = audio_init,
	.cleanup = audio_cleanup,
	.decodeAndPlaySample = audio_sample,
	.capabilities = CAPABILITY_DIRECT_SUBMIT,
};

/* Connection */

static void stage_starting(int stage) { out("stage %s\n", LiGetStageName(stage)); }
static void stage_failed(int stage, int err) { out("error stage %s failed: %d\n", LiGetStageName(stage), err); }
static void connection_started(void) { out("connected\n"); }

static void connection_terminated(int err)
{
	out("terminated %d\n", err);
	running = 0;
}

static void log_message(const char *fmt, ...)
{
	va_list ap;

	pthread_mutex_lock(&out_lock);
	fputs("log ", stdout);
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	fflush(stdout);
	pthread_mutex_unlock(&out_lock);
}

static CONNECTION_LISTENER_CALLBACKS connection_callbacks = {
	.stageStarting = stage_starting,
	.stageFailed = stage_failed,
	.connectionStarted = connection_started,
	.connectionTerminated = connection_terminated,
	.logMessage = log_message,
};

static int button_code(const char *name)
{
	if (!strcmp(name, "left"))
		return BUTTON_LEFT;
	if (!strcmp(name, "middle"))
		return BUTTON_MIDDLE;
	if (!strcmp(name, "right"))
		return BUTTON_RIGHT;
	return 0;
}

static void command(char *line)
{
	char a[64], b[64];
	int x, y, w, h;
	uint64_t t = now_us();
	int ok = 1;

	line[strcspn(line, "\r\n")] = 0;
	if (sscanf(line, "key %63s %63s", a, b) == 2) {
		int vk = (int)strtol(a, NULL, 0);

		LiSendKeyboardEvent((short)(0x8000 | vk), strcmp(b, "down") ? KEY_ACTION_UP : KEY_ACTION_DOWN, 0);
	} else if (sscanf(line, "move %d %d", &x, &y) == 2) {
		LiSendMouseMoveEvent((short)x, (short)y);
	} else if (sscanf(line, "pos %d %d %d %d", &x, &y, &w, &h) == 4) {
		LiSendMousePositionEvent((short)x, (short)y, (short)w, (short)h);
	} else if (sscanf(line, "button %63s %63s", a, b) == 2 && button_code(a)) {
		LiSendMouseButtonEvent(strcmp(b, "down") ? BUTTON_ACTION_RELEASE : BUTTON_ACTION_PRESS, button_code(a));
	} else if (sscanf(line, "scroll %d", &x) == 1) {
		LiSendScrollEvent((signed char)x);
	} else if (sscanf(line, "snap %1000s", snap_path) == 1) {
		ok = 2;
	} else if (!strcmp(line, "quit")) {
		running = 0;
		ok = 2;
	} else {
		out("error unknown command '%s'\n", line);
		ok = 0;
	}
	if (ok == 1)
		out("sent %llu %s\n", (unsigned long long)t, line);
}

static void *stdin_thread(void *arg)
{
	char line[1100];

	(void)arg;
	while (running && fgets(line, sizeof(line), stdin)) {
		pthread_mutex_lock(&snap_lock);
		command(line);
		pthread_mutex_unlock(&snap_lock);
	}
	running = 0;
	return NULL;
}

int main(int argc, char **argv)
{
	static const struct option opts[] = {
		{ "width", required_argument, NULL, 'w' }, { "height", required_argument, NULL, 'h' },
		{ "fps", required_argument, NULL, 'f' },   { "bitrate", required_argument, NULL, 'b' },
		{ NULL, 0, NULL, 0 },
	};
	STREAM_CONFIGURATION config;
	SERVER_DATA server;
	PAPP_LIST apps = NULL;
	pthread_t input;
	int c, app_id = -1, ret;

	LiInitializeStreamConfiguration(&config);
	config.width = 1280;
	config.height = 800;
	config.fps = 60;
	config.bitrate = 10000;
	config.packetSize = 1392;
	config.streamingRemotely = STREAM_CFG_LOCAL;
	config.audioConfiguration = AUDIO_CONFIGURATION_STEREO;
	config.supportedVideoFormats = VIDEO_FORMAT_H264;
	config.colorSpace = COLORSPACE_REC_601;
	config.colorRange = COLOR_RANGE_LIMITED;
	config.encryptionFlags = ENCFLG_AUDIO;
	while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
		switch (c) {
		case 'w': config.width = atoi(optarg); break;
		case 'h': config.height = atoi(optarg); break;
		case 'f': config.fps = atoi(optarg); break;
		case 'b': config.bitrate = atoi(optarg); break;
		default: return 2;
		}
	}
	if (argc - optind != 4) {
		fprintf(stderr, "usage: %s [--width W] [--height H] [--fps F] [--bitrate KBPS] HOST KEYDIR APP OUTDIR\n", argv[0]);
		return 2;
	}
	snprintf(wav_path, sizeof(wav_path), "%s/sound.wav", argv[optind + 3]);
	ret = gs_init(&server, argv[optind], 47989, argv[optind + 1], 0, true);
	if (ret != GS_OK) {
		out("error gs_init %d: %s\n", ret, gs_error ? gs_error : "");
		return 1;
	}
	if (!server.paired) {
		out("error not paired with %s (moonlight pair first)\n", argv[optind]);
		return 1;
	}
	if (gs_applist(&server, &apps) != GS_OK) {
		out("error applist: %s\n", gs_error ? gs_error : "");
		return 1;
	}
	for (PAPP_LIST a = apps; a; a = a->next) {
		out("app %d %s\n", a->id, a->name);
		if (!strcmp(a->name, argv[optind + 2]))
			app_id = a->id;
	}
	if (app_id < 0) {
		out("error no app '%s'\n", argv[optind + 2]);
		return 1;
	}
	ret = gs_start_app(&server, &config, app_id, false, false, 0);
	if (ret != GS_OK) {
		out("error start app %d: %s\n", ret, gs_error ? gs_error : "");
		return 1;
	}
	out("launched %s %dx%d %d fps %d kbps\n", argv[optind + 2], config.width, config.height, config.fps, config.bitrate);
	pthread_create(&input, NULL, stdin_thread, NULL);
	ret = LiStartConnection(&server.serverInfo, &config, &connection_callbacks, &video_callbacks,
				&audio_callbacks, NULL, 0, NULL, 0);
	if (ret != 0) {
		out("error LiStartConnection %d\n", ret);
		gs_quit_app(&server);
		return 1;
	}
	while (running)
		usleep(20000);
	LiStopConnection();
	gs_quit_app(&server);
	out("done frames=%lu audio-bytes=%u\n", frames, wav_bytes);
	return 0;
}
