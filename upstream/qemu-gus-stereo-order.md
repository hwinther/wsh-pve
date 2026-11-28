# QEMU: the Gravis Ultrasound swaps left and right (a voice panned left is heard on the right)

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0192`, with the qtest
`wsh/0193`; not in a published package yet. Our own finding in QEMU's code, independent of LEMU
(column "may send" in [README.md](README.md)). Found by the x86 audio matrix (`e2e/audio/`), whose
DOS test program plays one tone on a voice panned hard left and another on a voice panned hard
right.

**Reproduced on plain QEMU** (2026-11-28): `qemu-system-x86_64` built from the v11.1.3 tag (a clean
checkout, `--target-list=x86_64-softmmu`, no patch of ours), `-device gus` with a `wav` audiodev:
the qtest below fails in its left case, with the voice in the right channel (3840) and 0 in the
left. The same tree with only the change described below passes both cases. The code is the same
in QEMU master (v11.2.0-rc2, `hw/audio/gusemu_mixer.c` lines 174-175).

## Summary

`gus_mixvoices()` in `hw/audio/gusemu_mixer.c` (GUSemu's mixer) fills a buffer of 16-bit stereo
frames that `gus.c` hands to QEMU's audio layer as is (`as.nchannels = 2`). Its comment says the
frames are "first right then left interleaved", and the mixing statement does that:

```c
                /* mix samples into buffer */
                *(bufferpos + 2 * sample)     += (int16_t) ((sample1 * PanningPos) >> 4);        /* right */
                *(bufferpos + 2 * sample + 1) += (int16_t) ((sample1 * (15 - PanningPos)) >> 4); /* left */
```

QEMU's audio frames are left first (as in a WAV file; the CS4231A's output, for one, comes out
left first in the same test), so the GUS's output comes out mirrored: a voice at pan position 0 (full left on the GF1) is
heard on the right, one at 15 (full right) on the left, and a game or player that pans its
instruments has its stereo image reversed. Mono content and centred voices sound the same either way,
which may be why it went unnoticed.

- **Affected:** `-device gus` on every machine with an ISA bus, every audio backend. Both 8-bit
  and 16-bit voices go through the one statement above; nothing else in `gus.c` or `gusemu_*`
  orders the channels. QEMU 11.1.3 and master; from the code, every release since the GUS came
  in (not checked how far back).
- **Who to tell:** `MAINTAINERS`, "Overall Audio frontends" (`hw/audio/`).
- **Tracker:** searched on 2026-11-28 for "gus", "gravis", "ultrasound", "gus stereo", "gus left"
  and "gus panning": nothing about the channel order (the GUS issues there are DMA overflows and
  #106, "gravis ultrasound not working", closed).

## What the hardware does

- The GF1's voice pan position register (register 0Ch) has 16 positions, 0 full left, 7 the
  middle and 15 full right. DOSBox Staging's `src/hardware/audio/gus.cpp` quotes the Gravis SDK for
  it ("0 representing the full-left rotation, 7 being the mid-point, and 15 being the full-right
  rotation") and mixes position 0 into its frame's `left`.
- Linux's GUS driver (`sound/isa/gus/gus_pcm.c`, `snd_gf1_pcm_trigger_up()`) plays a stereo
  stream on two voices and gives the left channel's voice pan 1 and the right channel's 14
  (`pan = runtime->channels == 2 ? (!voice ? 1 : 14) : 8;`), so a stereo file played by Linux in
  a guest comes out swapped on QEMU too (not tried in a guest; read from the source).

## Where in the code

`hw/audio/gusemu_mixer.c`, `gus_mixvoices()`, the two lines quoted above, and the comment above the
function:

```c
/* samples are always 16bit stereo (4 bytes each, first right then left interleaved) */
```

`gus.c` opens its voice with two channels and `GUS_callback()` passes `s->mixbuf` to
`audio_be_write()` without reordering.

## Fix (in prose)

Swap the two slots: the first sample of each frame (left) gets `sample1 * (15 - PanningPos) >> 4`,
the second (right) `sample1 * PanningPos >> 4`, and the comment says left first. No migration
change: no state is added or reinterpreted (the mix buffer is rebuilt on every callback).

Not changed: the pan law. QEMU's mixer pans linearly in sixteenths (position 15 gives the right
channel 15/16 of the voice and the left nothing, position 0 the left 15/16), where the SDK and
DOSBox Staging keep the power constant; that is a separate question and doesn't swap anything.

Tested in our lab with that change (11.1.3 with our series): the audio matrix's DOS program, which
writes a 40-sample sine period into the GF1's DRAM and plays it on voice 0 (pan 0, 551.25 Hz) and
voice 1 (pan 15, 1102.5 Hz), gives 551.25 Hz on the left channel and 1102.5 Hz on the right; the
same build without the change gives them the other way round. The matrix's other DOS cases (SB16,
AdLib, PC speaker, the three together and the CS4231A) pass as before.

## A test without a guest

`tests/qtest/gus-test.c` (wsh/0193), `-M pc -device gus,audiodev=snd0` with `-audiodev
wav,id=snd0,path=...,out.frequency=44100,out.channels=2,out.format=s16`, all through port I/O:

- reset the GF1 and set it running (register 4Ch: 0, then 3), 14 active voices (0Eh: `0xcd`);
- write 17 bytes of `0x40` into DRAM from address 0 through the DRAM I/O port (address in 43h/44h,
  data at 347h): a constant level;
- voice 0 (342h): loop start 0, loop end 16 samples (`16 << 9`), current position 0, frequency
  1024, current volume `0xf000`, volume ramp stopped (0Dh: 3), pan position 0 (or 15), voice
  control 8 (running, looping);
- step the virtual clock 300 ms, quit, and read the wav file: every frame with sound must have the
  voice in the panned-to channel (3840: 4096 at that volume, times 15/16) and 0 in the other, for at
  least 100 ms of frames.

Plain v11.1.3: `/x86_64/gus/pan/left` fails (`assertion failed (off == 0): (3840 == 0)`). With
the change both cases pass.
