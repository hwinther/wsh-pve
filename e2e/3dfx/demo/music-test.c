/*
 * A host test of wshdemo's music (music.c), with the C library: renders the song with a fixed seed
 * and checks that it is there and right, without a sound device.
 *
 *   music-test [-rate R] [-secs S] [-wav FILE]
 *
 * Renders S seconds (default 64: the intro and the cube, tunnel, plasma and cube sections) at R Hz
 * (default 22050) in blocks of odd sizes, as the backends ask for them, and checks
 *   - the song's order: the section at each second (4 s intro, then 10 s each, cube again at 34 s);
 *   - every section non-silent on both channels (RMS), the channels different (stereo), the peak
 *     under full scale most of the time (under 0.1 % of the samples clipped);
 *   - the bass's notes: the cube's first two bars (A minor, F major) have their bass root (A2 110 Hz,
 *     F2 87.3 Hz) stronger than the other's (Goertzel);
 *   - a second render in blocks of other sizes is the same, sample for sample;
 *   - music_section(): asked for the tunnel 1 s in, it plays the tunnel within a beat and is still
 *     in it 15 s later.
 * Prints "MUSICTEST rate=R secs=S fnv=XXXXXXXX ..." (FNV-1a of the samples: music.c is integer
 * arithmetic, so it is the same on every target; build-linux.sh compares the i386 and the host's)
 * and PASS or FAIL lines; exit 0 on PASS. -wav writes the render as a 16-bit stereo WAV.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "music.h"

static int fails;
static void check(int ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	fails += !ok;
}

static int16_t *render(int rate, int frames, const int *blocks, int nblocks, int *sections)
{
	int16_t *pcm = calloc((size_t)frames * 2, sizeof(int16_t));
	music_reset(12345);
	for (int pos = 0, b = 0; pos < frames; b++) {
		int n = blocks[b % nblocks];
		if (n > frames - pos)
			n = frames - pos;
		music_mix(pcm + pos * 2, n, rate);
		/* the section at each whole second (sampled at the block that crosses it) */
		if (sections && (pos + n) / rate != pos / rate)
			sections[(pos + n) / rate] = music_now_section();
		pos += n;
	}
	return pcm;
}

static double goertzel(const int16_t *pcm, int from, int n, double hz, int rate)
{
	double w = 2 * M_PI * hz / rate, c = 2 * cos(w), s1 = 0, s2 = 0;
	for (int i = 0; i < n; i++) {
		double x = (pcm[(from + i) * 2] + pcm[(from + i) * 2 + 1]) * 0.5;
		double s0 = x + c * s1 - s2;
		s2 = s1, s1 = s0;
	}
	return sqrt(s1 * s1 + s2 * s2 - c * s1 * s2) / n;
}

static void write_wav(const char *path, const int16_t *pcm, int frames, int rate)
{
	FILE *f = fopen(path, "wb");
	if (!f)
		return;
	uint32_t data = (uint32_t)frames * 4, v;
	fwrite("RIFF", 1, 4, f);
	v = 36 + data, fwrite(&v, 4, 1, f);
	fwrite("WAVEfmt ", 1, 8, f);
	v = 16, fwrite(&v, 4, 1, f);
	uint16_t fmt[2] = {1, 2};
	fwrite(fmt, 2, 2, f);
	v = (uint32_t)rate, fwrite(&v, 4, 1, f);
	v = (uint32_t)rate * 4, fwrite(&v, 4, 1, f);
	uint16_t al[2] = {4, 16};
	fwrite(al, 2, 2, f);
	fwrite("data", 1, 4, f);
	fwrite(&data, 4, 1, f);
	fwrite(pcm, 4, (size_t)frames, f);
	fclose(f);
}

int main(int argc, char **argv)
{
	int rate = 22050, secs = 64;
	const char *wav = 0;
	for (int i = 1; i + 1 < argc; i += 2) {
		if (!strcmp(argv[i], "-rate"))
			rate = atoi(argv[i + 1]);
		else if (!strcmp(argv[i], "-secs"))
			secs = atoi(argv[i + 1]);
		else if (!strcmp(argv[i], "-wav"))
			wav = argv[i + 1];
	}
	if (secs < 40 || rate < 8000 || rate > 48000) {
		fprintf(stderr, "usage: music-test [-rate 8000..48000] [-secs S >= 40] [-wav FILE]\n");
		return 2;
	}
	int frames = rate * secs;
	static const int blocks_a[] = {1024, 333, 7, 4096, 512}, blocks_b[] = {97, 2048, 1, 640};
	int *sec_at = calloc((size_t)secs + 1, sizeof(int));
	int16_t *pcm = render(rate, frames, blocks_a, 5, sec_at);

	uint32_t fnv = 2166136261U;
	const uint8_t *bytes = (const uint8_t *)pcm;
	for (size_t i = 0; i < (size_t)frames * 4; i++)
		fnv = (fnv ^ bytes[i]) * 16777619U;
	long clipped = 0, peak = 0, differ = 0;
	for (int i = 0; i < frames * 2; i++) {
		int v = abs(pcm[i]);
		peak = v > peak ? v : peak;
		clipped += v >= 32767;
		if (!(i & 1))
			differ += pcm[i] != pcm[i + 1];
	}
	printf("MUSICTEST rate=%d secs=%d fnv=%08x peak=%ld clipped=%ld\n", rate, secs, fnv, peak, clipped);

	/* the order: intro to 4 s, then 10 s a section; a second's section is checked 1 s after a change */
	static const char *names[] = {"title", "cube", "tunnel", "plasma"};
	int order_ok = 1;
	for (int s = 1; s < secs; s++) {
		int want = s < 4 ? MUSIC_TITLE : MUSIC_CUBE + ((s - 4) / 10) % 3;
		if ((s - 4) % 10 != 0 && s != 4 && sec_at[s] != want) {
			printf("     at %d s: %s, not %s\n", s, names[sec_at[s]], names[want]);
			order_ok = 0;
		}
	}
	check(order_ok, "the song's order: intro 4 s, then cube, tunnel, plasma 10 s each, cube again at 34 s");

	/* RMS per section (from 0.5 s in to 0.5 s before its end) and channel */
	static const int from_s[] = {0, 4, 14, 24, 34}, to_s[] = {4, 14, 24, 34, 44};
	char line[200];
	for (int k = 0; k < 5; k++) {
		double sum[2] = {0, 0};
		int a = from_s[k] * rate + rate / 2, b = to_s[k] * rate - rate / 2;
		for (int i = a; i < b; i++)
			for (int c = 0; c < 2; c++)
				sum[c] += (double)pcm[i * 2 + c] * pcm[i * 2 + c];
		double l = sqrt(sum[0] / (b - a)), r = sqrt(sum[1] / (b - a));
		snprintf(line, sizeof(line), "%s (%d-%d s) is not silent: RMS left %.0f, right %.0f (over 800)",
			 names[k == 4 ? 1 : k], from_s[k], to_s[k], l, r);
		check(l > 800 && r > 800, line);
	}
	snprintf(line, sizeof(line), "stereo: left and right differ in %.1f %% of the frames", 100.0 * differ / frames);
	check(differ > frames / 2, line);
	snprintf(line, sizeof(line), "%ld samples at full scale (under 0.1 %%), peak %ld", clipped, peak);
	check(clipped * 1000 < (long)frames * 2, line);

	/* the bass: bar 1 of the cube (4-6 s) on A, bar 2 (6-8 s) on F */
	double a1 = goertzel(pcm, 4 * rate, 2 * rate, 110.0, rate), f1 = goertzel(pcm, 4 * rate, 2 * rate, 87.31, rate);
	double a2 = goertzel(pcm, 6 * rate, 2 * rate, 110.0, rate), f2 = goertzel(pcm, 6 * rate, 2 * rate, 87.31, rate);
	snprintf(line, sizeof(line), "the bass: cube bar 1 A2 %.0f > F2 %.0f, bar 2 F2 %.0f > A2 %.0f", a1, f1, f2, a2);
	check(a1 > 2 * f1 && f2 > 2 * a2, line);

	/* the same in other block sizes */
	int16_t *again = render(rate, frames, blocks_b, 4, 0);
	check(!memcmp(pcm, again, (size_t)frames * 4), "deterministic: a second render in other block sizes is the same");
	if (wav)
		write_wav(wav, pcm, frames, rate);
	free(again);

	/* driven: the tunnel asked for 1 s in */
	int16_t buf[2 * 512];
	music_reset(12345);
	music_section(MUSIC_CUBE);
	int at = -1;
	for (int pos = 0; pos < 17 * rate; pos += 512) {
		if (pos / 512 == rate / 512)
			music_section(MUSIC_TUNNEL);
		music_mix(buf, 512, rate);
		if (at < 0 && pos > rate && music_now_section() == MUSIC_TUNNEL)
			at = pos;
	}
	snprintf(line, sizeof(line), "music_section(): the tunnel %.2f s after it was asked for (within a beat), still at 17 s: %s",
		 at < 0 ? -1.0 : (double)(at - rate) / rate, names[music_now_section()]);
	check(at >= 0 && at - rate <= rate / 2 + 512 && music_now_section() == MUSIC_TUNNEL, line);

	printf("%s\n", fails ? "FAIL" : "PASS");
	free(pcm);
	free(sec_at);
	return fails ? 1 : 0;
}
