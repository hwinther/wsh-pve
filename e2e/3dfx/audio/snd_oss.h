/*
 * The Linux sound backend of the 3dfx programs (wshspace, wshdemo): OSS /dev/dsp (snd-pcm-oss on
 * ALSA), 16-bit stereo, opened non-blocking, polled from the main loop, with plain ioctl()s so the
 * program needs nothing newer than glibc 2.0 and no other library; silent without the device.
 * Included by the program's plat_linux.c (after <fcntl.h>, <sys/ioctl.h>, <unistd.h>), which defines
 * SND_MIX(pcm, frames, rate) to its mixer first. Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_SND_OSS_H
#define WSH_SND_OSS_H

#define SNDCTL_DSP_SPEED       0xc0045002UL
#define SNDCTL_DSP_SETFMT      0xc0045005UL
#define SNDCTL_DSP_CHANNELS    0xc0045006UL
#define SNDCTL_DSP_SETFRAGMENT 0xc004500aUL
#define SNDCTL_DSP_GETOSPACE   0x8010500cUL

static int dsp_fd = -1, dsp_rate = 22050;
static uint32_t dsp_last_us;
static int16_t dsp_buf[1024 * 2];

void plat_audio_init(int enable)
{
	if (!enable || dsp_fd >= 0)
		return;
	dsp_fd = open("/dev/dsp", O_WRONLY | O_NONBLOCK);
	if (dsp_fd < 0)
		return;
	int frag = (4 << 16) | 12; /* 4 fragments of 4096 bytes */
	int fmt = 0x10;            /* AFMT_S16_LE */
	int ch = 2;
	int rate = 22050;
	ioctl(dsp_fd, SNDCTL_DSP_SETFRAGMENT, &frag);
	if (ioctl(dsp_fd, SNDCTL_DSP_SETFMT, &fmt) < 0 || fmt != 0x10 ||
	    ioctl(dsp_fd, SNDCTL_DSP_CHANNELS, &ch) < 0 || ch != 2 ||
	    ioctl(dsp_fd, SNDCTL_DSP_SPEED, &rate) < 0) {
		close(dsp_fd);
		dsp_fd = -1;
		return;
	}
	dsp_rate = rate;
	dsp_last_us = plat_us() - 50000U;
}

void plat_audio_tick(void)
{
	if (dsp_fd < 0)
		return;
	uint32_t now = plat_us();
	uint32_t dt_us = now - dsp_last_us;
	if (dt_us > 100000U)
		dt_us = 100000U;
	int frames = (int)((double)dt_us * (double)dsp_rate * 1e-6);
	/* With the device's fill level: at least 2048 frames (two fragments, 93 ms) queued, or the
	 * card runs dry after the first fragment (-audiotest saw a 7 ms gap there on AC97), and no
	 * more than fits (frames mixed and then not written would be lost) */
	struct { int fragments, fragstotal, fragsize, bytes; } space;
	if (ioctl(dsp_fd, SNDCTL_DSP_GETOSPACE, &space) == 0) {
		int queued = (space.fragstotal * space.fragsize - space.bytes) / 4;
		if (frames < 2048 - queued)
			frames = 2048 - queued;
		if (frames > space.bytes / 4)
			frames = space.bytes / 4;
	}
	if (frames < 128)
		return;
	if (frames > 1024)
		frames = 1024;
	SND_MIX(dsp_buf, frames, dsp_rate);
	ssize_t w = write(dsp_fd, dsp_buf, (size_t)frames * 4);
	if (w > 0)
		dsp_last_us = now;
}

void plat_audio_close(void)
{
	if (dsp_fd >= 0) {
		close(dsp_fd);
		dsp_fd = -1;
	}
}

#endif
