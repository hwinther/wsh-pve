/*
 * wshdemo's music: a short original tracker-style tune, synthesized at run time (music.c). Four
 * channels in integer arithmetic only, so the output is the same bytes on every target and compiler:
 *
 *   bass    a pulse wave with a slowly moving pulse width, 2 octaves under the chord
 *   arp     a 25 % pulse, a chip arpeggio that steps through the chord every tick (48 Hz), through
 *           a one-pole low-pass whose cutoff each section sets (the tunnel sweeps it open)
 *   lead    a sawtooth with delayed vibrato, through its own low-pass (tunnel and plasma only)
 *   drums   kick (a triangle falling in pitch), snare (noise and a tone), closed and open hats
 *           (high-passed noise)
 *
 * with a stereo ping-pong echo (3 rows) on the arp and the lead. 120 BPM, a row is a 16th note
 * (125 ms, 6 ticks), a bar 16 rows (2 s). The song follows the demo's parts: an intro of 2 bars
 * (4 s, the title card) and a section of 5 bars (10 s, the default -secs) for each of cube, tunnel
 * and plasma, each with its own chords, bass line, drum pattern and arp filter; then cube again:
 * 34 s for the first pass and a 30 s loop. Left alone it plays the song in that order; once the
 * demo has asked for a section (music_section(), when its part changes) it switches at the next
 * beat and repeats that section until asked for another.
 *
 * No C library, no libm, no 64-bit arithmetic. Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_MUSIC_H
#define WSH_MUSIC_H

#include <stdint.h>

enum { MUSIC_TITLE, MUSIC_CUBE, MUSIC_TUNNEL, MUSIC_PLASMA, MUSIC_SECTIONS };

#define MUSIC_BAR_MS 2000
#define MUSIC_INTRO_BARS 2
#define MUSIC_SECTION_BARS 5

/* Back to the start of the song (the intro), with the noise generator seeded from seed */
void music_reset(uint32_t seed);
/* Switch to section s (MUSIC_*) at the next beat, and stay in it; before any frame was mixed at once */
void music_section(int s);
/* The next frames of the song as 16-bit stereo (left, right) at rate Hz (8000..48000) */
void music_mix(int16_t *pcm, int frames, int rate);
/* The section and bar being mixed */
int music_now_section(void);
int music_now_bar(void);

#endif
