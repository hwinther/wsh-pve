/*
 * wshdemo's music (see music.h): an original tune in four synthesized channels, integer arithmetic
 * only. The song is data: chords, bass lines (semitones above the chord's root), drum rows (a mask
 * of instruments) and lead melodies (MIDI notes), one bar of 16 rows each, and per section a list of
 * bars and the arp's octave, filter and rhythm. A tick (48 a second, 6 a row) runs the envelopes,
 * the arpeggio and the vibrato; every sample runs the oscillators, the filters and the echo.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include "music.h"

#define TICKS_PER_SEC 48
#define TICKS_PER_ROW 6
#define ROWS 16
#define ECHO_MAX 18000 /* 3 rows at 48000 Hz */

/* --- the song ----------------------------------------------------------------------------------- */

/* Chords as the arp plays them (MIDI notes); the bass plays the first two octaves lower */
enum { AM, F, DM, E, G, EM, BB };
static const uint8_t chords[][3] = {
	{69, 72, 76}, /* A minor: A4 C5 E5 */
	{65, 69, 72}, /* F major: F4 A4 C5 */
	{62, 65, 69}, /* D minor: D4 F4 A4 */
	{64, 68, 71}, /* E major: E4 G#4 B4 */
	{67, 71, 74}, /* G major: G4 B4 D5 */
	{64, 67, 71}, /* E minor: E4 G4 B4 */
	{70, 74, 77}, /* B flat major: A#4 D5 F5 */
};

/* Bass lines: semitones above the bass root, H holds the note, X ends it */
#define H 100
#define X 101
enum { B_NONE, B_INTRO, B_CUBE, B_TUNNEL, B_PLASMA };
static const int8_t basslines[][ROWS] = {
	{X, H, H, H, H, H, H, H, H, H, H, H, H, H, H, H},
	{0, H, H, H, H, H, H, H, H, H, H, H, H, H, X, H},
	{0, H, X, 0, X, X, 12, X, 0, H, 7, X, 12, X, 0, X},
	{0, H, H, X, 0, X, 0, H, H, X, 7, H, X, X, 12, X},
	{0, X, 12, X, 0, X, 12, X, 0, X, 12, X, 0, X, 12, 7},
};

/* Drum rows: kick, snare, closed hat, open hat */
#define K 1
#define S 2
#define C 4
#define O 8
enum { D_NONE, D_INTRO, D_CUBE, D_TUNNEL, D_PLASMA, D_FILL };
static const uint8_t drums[][ROWS] = {
	{0},
	{C, 0, C, 0, C, 0, C, 0, C, 0, C, 0, S, 0, S, S},
	{K, 0, C, 0, S, 0, C, K, 0, K, C, 0, S, 0, C, 0},
	{K, 0, C, C, S, 0, C, 0, K, 0, C, K, S, 0, C, O},
	{K, 0, O, 0, K | S, 0, O, 0, K, 0, O, 0, K | S, 0, O, C},
	{K, 0, C, 0, S, 0, K, 0, S, 0, S, 0, S, S, S, S},
};

/* Lead melodies: MIDI notes, 0 holds, 1 ends the note */
enum { L_NONE, L_T1, L_T2, L_T3, L_T4, L_T5, L_P1, L_P2, L_P3, L_P4, L_P5 };
static const uint8_t leads[][ROWS] = {
	{1},
	{69, 0, 0, 0, 72, 0, 69, 0, 67, 0, 65, 0, 69, 0, 0, 0},
	{71, 0, 0, 74, 0, 0, 79, 0, 0, 77, 0, 74, 0, 71, 0, 0},
	{67, 0, 0, 0, 71, 0, 76, 0, 0, 0, 74, 0, 71, 0, 67, 0},
	{69, 0, 0, 0, 0, 0, 76, 0, 0, 0, 81, 0, 0, 0, 79, 0},
	{80, 0, 0, 0, 0, 0, 0, 0, 76, 0, 0, 0, 71, 0, 1, 0},
	{76, 0, 81, 0, 84, 0, 83, 81, 0, 0, 76, 0, 81, 0, 83, 84},
	{86, 0, 0, 0, 84, 0, 82, 0, 0, 0, 77, 0, 82, 0, 86, 0},
	{84, 0, 0, 81, 0, 0, 77, 0, 0, 81, 0, 84, 0, 88, 0, 0},
	{83, 0, 0, 0, 80, 0, 0, 0, 76, 0, 77, 0, 80, 0, 83, 0},
	{81, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0},
};

struct bar {
	uint8_t chord, bass, drum, lead;
};
struct section {
	uint8_t nbars;
	struct bar bars[MUSIC_SECTION_BARS];
	int8_t arp_octave;      /* semitones added to the chord */
	uint8_t arp_every;      /* the arp's envelope restarts every so many rows */
	uint8_t cut_from, cut_to; /* the arp's low-pass (0..255), swept over the section */
	uint8_t lead_cut;       /* the lead's low-pass */
};
static const struct section song[MUSIC_SECTIONS] = {
	/* title: the arp alone, its filter opening, then the bass and hats with a snare fill */
	{2, {{AM, B_NONE, D_NONE, L_NONE}, {AM, B_INTRO, D_INTRO, L_NONE}}, 0, 4, 10, 150, 0},
	/* cube: the groove, no lead */
	{5, {{AM, B_CUBE, D_CUBE, L_NONE}, {F, B_CUBE, D_CUBE, L_NONE}, {DM, B_CUBE, D_CUBE, L_NONE},
	     {E, B_CUBE, D_CUBE, L_NONE}, {AM, B_CUBE, D_FILL, L_NONE}}, 0, 2, 150, 150, 0},
	/* tunnel: the lead comes in, the arp's filter sweeps open over the section */
	{5, {{F, B_TUNNEL, D_TUNNEL, L_T1}, {G, B_TUNNEL, D_TUNNEL, L_T2}, {EM, B_TUNNEL, D_TUNNEL, L_T3},
	     {AM, B_TUNNEL, D_TUNNEL, L_T4}, {E, B_TUNNEL, D_FILL, L_T5}}, 0, 2, 24, 230, 90},
	/* plasma: four to the floor, octave bass, the arp an octave up, the lead higher and brighter */
	{5, {{AM, B_PLASMA, D_PLASMA, L_P1}, {BB, B_PLASMA, D_PLASMA, L_P2}, {F, B_PLASMA, D_PLASMA, L_P3},
	     {E, B_PLASMA, D_PLASMA, L_P4}, {AM, B_PLASMA, D_FILL, L_P5}}, 12, 1, 200, 200, 170},
};

/* --- the synthesizer ---------------------------------------------------------------------------- */

/* 12-TET C8..B8 in 1/16 Hz; a lower octave is a shift right */
static const uint32_t top_octave[12] = {66976, 70959, 75178, 79648, 84385, 89402, 94719, 100351, 106318, 112640, 119338, 126434};

struct voice {
	uint32_t ph, step;
	int vol, target, smooth; /* vol, target: 0..255 (per tick); smooth: vol << 8, per sample */
	int lp;                  /* one-pole low-pass state */
	int age;                 /* ticks since the note started */
};

struct drum {
	int32_t env, dec; /* 1 << 24 down to 0 */
	uint32_t ph;
};

static struct {
	int rate, fresh, driven, want;
	int sec, bar, row, tick;
	uint32_t tick_acc, ticks, rng;
	uint32_t notes[120];
	uint32_t kick_lo, kick_hi, snare_step;
	int32_t kick_dec, snare_dec, tone_dec, hat_dec, open_dec;
	struct voice bass, arp, lead;
	int arp_note[3], arp_i, arp_cut, lead_note, lead_cut;
	struct drum kick, snare, tone, hat;
	int hat_prev;
	int echo_len, echo_pos;
	int16_t echo[2][ECHO_MAX];
} m;

/* hz16 (1/16 Hz) * 2^32 / rate, in 32-bit arithmetic (as e2e/wisp/audiosig.h's audiosig_step) */
static uint32_t step16(uint32_t hz16, uint32_t rate)
{
	uint32_t hi = (hz16 << 12) / rate, rem = (hz16 << 12) % rate;
	return (hi << 16) | ((rem << 16) / rate);
}

static void set_rate(int rate)
{
	m.rate = rate;
	for (int n = 0; n < 120; n++)
		m.notes[n] = step16(top_octave[n % 12] >> (9 - n / 12), (uint32_t)rate);
	m.kick_lo = step16(42 * 16, (uint32_t)rate);
	m.kick_hi = step16(160 * 16, (uint32_t)rate);
	m.snare_step = step16(185 * 16, (uint32_t)rate);
	/* decays: 1 << 24 over so many ms */
	m.kick_dec = (int32_t)((1U << 24) / ((uint32_t)rate * 230 / 1000));
	m.snare_dec = (int32_t)((1U << 24) / ((uint32_t)rate * 150 / 1000));
	m.tone_dec = (int32_t)((1U << 24) / ((uint32_t)rate * 60 / 1000));
	m.hat_dec = (int32_t)((1U << 24) / ((uint32_t)rate * 35 / 1000));
	m.open_dec = (int32_t)((1U << 24) / ((uint32_t)rate * 170 / 1000));
	m.echo_len = rate * 3 / 8;
	if (m.echo_len > ECHO_MAX)
		m.echo_len = ECHO_MAX;
	m.echo_pos = 0;
	for (int i = 0; i < ECHO_MAX; i++)
		m.echo[0][i] = m.echo[1][i] = 0;
}

void music_reset(uint32_t seed)
{
	int rate = m.rate;
	uint8_t *p = (uint8_t *)&m;
	for (unsigned i = 0; i < sizeof(m); i++)
		p[i] = 0;
	m.rng = seed ? seed : 0x2f6b4e1dU;
	m.fresh = 1;
	m.want = -1;
	if (rate)
		set_rate(rate);
}

void music_section(int s)
{
	if (s < 0 || s >= MUSIC_SECTIONS)
		return;
	m.driven = 1;
	if (m.fresh) {
		m.sec = s, m.bar = m.row = m.tick = 0;
		m.want = -1;
	} else {
		m.want = s;
	}
}

int music_now_section(void)
{
	return m.sec;
}

int music_now_bar(void)
{
	return m.bar;
}

static void note_on(struct voice *v, int note, int vol)
{
	v->step = m.notes[note < 0 ? 0 : note > 119 ? 119 : note];
	v->vol = vol;
	v->age = 0;
}

static void hit(struct drum *d, int32_t dec)
{
	d->env = 1 << 24;
	d->dec = dec;
}

/* The row's notes and drums (at its first tick) */
static void play_row(void)
{
	const struct section *sc = &song[m.sec];
	const struct bar *b = &sc->bars[m.bar];
	const uint8_t *ch = chords[b->chord];
	int pos = m.bar * ROWS + m.row, len = sc->nbars * ROWS;
	for (int i = 0; i < 3; i++)
		m.arp_note[i] = ch[i] + sc->arp_octave;
	m.arp_cut = sc->cut_from + (sc->cut_to - sc->cut_from) * pos / len;
	m.lead_cut = sc->lead_cut;
	if (m.row % sc->arp_every == 0)
		m.arp.vol = 255;

	int bn = basslines[b->bass][m.row];
	if (bn == X)
		m.bass.target = 0;
	else if (bn != H) {
		note_on(&m.bass, ch[0] - 24 + bn, 255);
		m.bass.target = 150;
	}

	int ln = leads[b->lead][m.row];
	if (ln == 1)
		m.lead.target = 0;
	else if (ln) {
		note_on(&m.lead, ln, 210);
		m.lead.target = 150;
		m.lead_note = ln;
	}

	int dm = drums[b->drum][m.row];
	if (dm & K)
		hit(&m.kick, m.kick_dec);
	if (dm & S) {
		hit(&m.snare, m.snare_dec);
		hit(&m.tone, m.tone_dec);
	}
	if (dm & (C | O))
		hit(&m.hat, dm & O ? m.open_dec : m.hat_dec);
}

/* An envelope's step towards its target: down by `down` a tick (to 0 by `rel` once released) */
static void env(struct voice *v, int down, int rel)
{
	if (v->target == 0)
		v->vol = v->vol > rel ? v->vol - rel : 0;
	else if (v->vol > v->target)
		v->vol = v->vol - down > v->target ? v->vol - down : v->target;
	v->age++;
}

static void tick(void)
{
	if (m.fresh) {
		m.fresh = 0;
		play_row();
	} else if (++m.tick == TICKS_PER_ROW) {
		m.tick = 0;
		if (++m.row == ROWS) {
			m.row = 0;
			if (++m.bar == song[m.sec].nbars) {
				m.bar = 0;
				/* the song's order, or the section the demo asked for again (the intro only once) */
				if (!m.driven || m.sec == MUSIC_TITLE)
					m.sec = m.sec == MUSIC_PLASMA ? MUSIC_CUBE : m.sec + 1;
			}
		}
		/* a section the demo asked for, at the next beat, in time with the beat */
		if (m.want >= 0 && m.row % 4 == 0) {
			if (m.want != m.sec)
				m.sec = m.want, m.bar = 0;
			m.want = -1;
		}
		play_row();
	}
	m.ticks++;
	/* the arp: the next note of the chord every tick, a plucked envelope */
	m.arp_i = (m.arp_i + 1) % 3;
	m.arp.step = m.notes[m.arp_note[m.arp_i]];
	m.arp.vol = m.arp.vol > 70 ? m.arp.vol - 12 : 58;
	env(&m.bass, 7, 45);
	env(&m.lead, 2, 30);
	/* the lead's vibrato, after a quarter of a second, at 6 Hz */
	static const int8_t vib[8] = {0, 2, 4, 2, 0, -2, -4, -2};
	uint32_t base = m.notes[m.lead_note];
	m.lead.step = m.lead.age > 12 ? base + (uint32_t)((int32_t)(base >> 9) * vib[m.ticks & 7]) : base;
}

/* a triangle, -16384..16384, from a phase */
static int tri(uint32_t ph)
{
	int x = (int)(ph >> 16);
	return x < 16384 ? x : x < 49152 ? 32768 - x : x - 65536;
}

static int smooth(struct voice *v)
{
	v->smooth += ((v->vol << 8) - v->smooth) >> 5;
	return v->smooth >> 8; /* 0..255 */
}

static int noise(void)
{
	m.rng ^= m.rng << 13;
	m.rng ^= m.rng >> 17;
	m.rng ^= m.rng << 5;
	return (int)(m.rng >> 17) - 16384;
}

/* a drum's level, 0..65536, falling as the square of its envelope */
static int drum_level(struct drum *d)
{
	if (d->env <= 0)
		return 0;
	int a = d->env >> 16; /* 0..256 */
	d->env -= d->dec;
	return a * a;
}

static int clamp16(int v)
{
	return v < -32767 ? -32767 : v > 32767 ? 32767 : v;
}

void music_mix(int16_t *pcm, int frames, int rate)
{
	if (rate < 8000 || rate > 48000)
		return;
	if (rate != m.rate)
		set_rate(rate);
	if (!m.rng)
		music_reset(0);
	for (int i = 0; i < frames; i++) {
		m.tick_acc += TICKS_PER_SEC;
		if (m.tick_acc >= (uint32_t)rate || m.fresh) {
			if (!m.fresh)
				m.tick_acc -= (uint32_t)rate;
			tick();
		}

		/* bass: a pulse whose width moves between 19 and 43 %, softened by a low-pass */
		uint32_t t = m.ticks & 127, duty = 0x30000000U + ((t < 64 ? t : 127 - t) << 24);
		m.bass.ph += m.bass.step;
		int bass = ((m.bass.ph < duty ? 16384 : -16384) * smooth(&m.bass)) >> 9;
		m.bass.lp += ((bass - m.bass.lp) * 90) >> 8;
		bass = m.bass.lp;

		/* arp: a 25 % pulse through the section's low-pass */
		m.arp.ph += m.arp.step;
		int arp = ((m.arp.ph < 0x40000000U ? 12000 : -4000) * smooth(&m.arp)) >> 8;
		m.arp.lp += ((arp - m.arp.lp) * m.arp_cut) >> 8;
		arp = m.arp.lp;

		/* lead: a sawtooth through its low-pass */
		m.lead.ph += m.lead.step;
		int lead = (((int)(m.lead.ph >> 17) - 16384) * smooth(&m.lead)) >> 8;
		m.lead.lp += ((lead - m.lead.lp) * m.lead_cut) >> 8;
		lead = m.lead_cut ? m.lead.lp : 0;

		/* drums */
		int drum = 0, hat = 0;
		int kl = drum_level(&m.kick);
		if (kl) {
			m.kick.ph += m.kick_lo + ((m.kick_hi - m.kick_lo) >> 16) * (uint32_t)kl;
			drum += (tri(m.kick.ph) * (kl >> 8)) >> 8;
		}
		int sl = drum_level(&m.snare), tl = drum_level(&m.tone), hl = drum_level(&m.hat);
		if (sl || tl || hl) {
			int n = noise();
			if (sl)
				drum += ((n >> 1) * (sl >> 8)) >> 8;
			if (tl) {
				m.tone.ph += m.snare_step;
				drum += (tri(m.tone.ph) * (tl >> 8)) >> 9;
			}
			if (hl) {
				hat = (((n - m.hat_prev) >> 2) * (hl >> 8)) >> 8;
				m.hat_prev = n;
			}
		}

		/* the ping-pong echo of the arp and the lead: in on the left, back and forth */
		int16_t *el = &m.echo[0][m.echo_pos], *er = &m.echo[1][m.echo_pos];
		int dl = *el, dr = *er, send = (arp + lead) >> 1;
		*el = (int16_t)clamp16(send + ((dr * 110) >> 8));
		*er = (int16_t)clamp16((dl * 110) >> 8);
		if (++m.echo_pos >= m.echo_len)
			m.echo_pos = 0;

		int l = bass + drum + ((arp * 3) >> 2) + ((lead * 5) >> 3) + ((hat * 3) >> 3) + (dl >> 1);
		int r = bass + drum + (arp >> 2) + ((lead * 7) >> 3) + ((hat * 5) >> 3) + (dr >> 1);
		pcm[i * 2] = (int16_t)clamp16((l * 13) >> 4);
		pcm[i * 2 + 1] = (int16_t)clamp16((r * 13) >> 4);
	}
}
