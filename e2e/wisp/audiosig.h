/*
 * The audio signature: one fixed, deterministic test signal that wisp (init.c, `soundtest sig`) and
 * the 3dfx game wshspace (e2e/3dfx/space, `-audiotest`) play, and e2e/audio/wavcheck.py
 * (--signature) finds and checks in QEMU's `-audiodev wav` recording.
 *
 * The signal, at any sample rate R from 8000 to 48000 Hz:
 *
 *   8 segments of R / 2 frames each (500 ms; 4 s in all), 16-bit stereo;
 *   segment k (0..7): a triangle wave of 400 + 100 k Hz on the left channel and 600 + 150 k Hz
 *   (1.5 times the left) on the right:
 *
 *     segment     0    1    2    3    4    5    6    7
 *     left  Hz  400  500  600  700  800  900 1000 1100
 *     right Hz  600  750  900 1050 1200 1350 1500 1650
 *
 *   peak +-16384 (-6 dBFS); both phases start at 0 (the first frame is 0, 0) and run on across the
 *   segment boundaries (only the step changes), so there are no clicks; then silence.
 *
 * Each channel has its own tone in every segment, so a swap or a mono mix shows; the steps check
 * the timing; 4 s are many DMA buffers on every device (a playback that stops after the first one,
 * or drops one, shows as a short signal or a gap). The highest tone, 1650 Hz, has 4.8 samples per
 * period at 8000 Hz. A triangle has only odd harmonics, at 1/9, 1/25, ... of the fundamental's
 * power, so it survives resampling and the 8-bit Sound Blaster path.
 *
 * Integer arithmetic only: no C library, no libm, no 64-bit division (32-bit targets would need
 * libgcc for it). A 32-bit phase accumulator per channel; the step is hz * 2^32 / rate, computed in
 * two 16-bit halves. The values are exact and the same on every architecture and compiler.
 *
 *   struct audiosig s;
 *   int l, r;
 *   audiosig_init(&s, rate);
 *   while (audiosig_next(&s, &l, &r))
 *           ... l and r are -16384..16384 ...
 *
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_AUDIOSIG_H
#define WSH_AUDIOSIG_H

#define AUDIOSIG_SEGMENTS 8
#define AUDIOSIG_SEGMENT_MS 500
#define AUDIOSIG_PEAK 16384
#define AUDIOSIG_LEFT_HZ(k) (400 + 100 * (k))
#define AUDIOSIG_RIGHT_HZ(k) (600 + 150 * (k))
/* frames in the whole signal at `rate` */
#define AUDIOSIG_FRAMES(rate) (AUDIOSIG_SEGMENTS * ((rate) / 2))

struct audiosig {
	unsigned int rate, seg_frames, pos, seg;
	unsigned int phase[2], step[2];
};

/* hz * 2^32 / rate for hz < rate / 2 and rate < 65536, in 32-bit unsigned arithmetic */
static inline unsigned int audiosig_step(unsigned int hz, unsigned int rate)
{
	unsigned int hi = (hz << 16) / rate, rem = (hz << 16) % rate;

	return (hi << 16) | ((rem << 16) / rate);
}

static inline void audiosig_segment(struct audiosig *s)
{
	s->step[0] = audiosig_step(AUDIOSIG_LEFT_HZ(s->seg), s->rate);
	s->step[1] = audiosig_step(AUDIOSIG_RIGHT_HZ(s->seg), s->rate);
}

static inline void audiosig_init(struct audiosig *s, unsigned int rate)
{
	s->rate = rate;
	s->seg_frames = rate / 2;
	s->pos = s->seg = 0;
	s->phase[0] = s->phase[1] = 0;
	audiosig_segment(s);
}

/* The triangle of one phase: 0 at 0, +16384 at a quarter, -16384 at three quarters */
static inline int audiosig_triangle(unsigned int phase)
{
	int x = (int)(phase >> 16);

	return x < 16384 ? x : x < 49152 ? 32768 - x : x - 65536;
}

/* The next frame into *l and *r; 1 while the signal lasts, 0 (and silence) after it */
static inline int audiosig_next(struct audiosig *s, int *l, int *r)
{
	if (s->seg >= AUDIOSIG_SEGMENTS) {
		*l = *r = 0;
		return 0;
	}
	*l = audiosig_triangle(s->phase[0]);
	*r = audiosig_triangle(s->phase[1]);
	s->phase[0] += s->step[0];
	s->phase[1] += s->step[1];
	if (++s->pos == s->seg_frames) {
		s->pos = 0;
		if (++s->seg < AUDIOSIG_SEGMENTS)
			audiosig_segment(s);
	}
	return 1;
}

#endif
