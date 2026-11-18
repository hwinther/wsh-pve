# QEMU: sparc32 raises an illegal instruction for `ld`/`st %fsr` with rd other than 0

Material for a bug report to upstream QEMU. The bug was found and fixed by Antoni Sawicki in
[LEMU](https://github.com/tenox7/lemu) (commit
[`0cdd14c1`](https://github.com/tenox7/lemu/commit/0cdd14c1487c30b14a983db634658fd7a29789b2),
"target/sparc: let sparc32 ld and st %fsr ignore rd"); credit him as the finder. We carry his change
in pve-qemu as `debian/patches/wsh/0026-target-sparc-let-sparc32-ld-and-st-fsr-ignore-rd.patch`,
with our qtest `tests/qtest/sun4m-fsr-rd-test.c` in
`debian/patches/wsh/0027-tests-qtest-test-ld-and-st-fsr-with-any-rd-on-sun4m.patch` (both in
`submodules/pve-qemu.patch`).

## Summary

On V7 and V8 the rd field of LDFSR (`op=3, op3=0x21`) and STFSR (`op=3, op3=0x25`) is unused and
ignored by the hardware. Since the move of these instructions to decodetree, QEMU's sparc32 decodes
them only with rd 0 and raises an illegal instruction trap for any other rd.

Old static SunOS 4 binaries have rd 4 there: the `_sigtramp` of an old libc saves the FSR with
`c92ba0e0` (`st %fsr, [%sp + 0xe0]`) and restores it with `c90ba0e0` (`ld [%sp + 0xe0], %fsr`).
Such a program dies with SIGILL at its first signal after it has used the FPU. LEMU's example is
`islandLIC`, the 1992 FLEXlm licence daemon of Island Productivity Series 3.0, which died about a
minute after it started under SunOS 4.1.4 on `-M SS-5`.

- **Affected:** `qemu-system-sparc` 8.2.0 and later, up to v11.1.3 and master (`6883fb508c`,
  2026-11-17, still has `LDFSR 11 00000 100001` and `STFSR 11 00000 100101` in
  `target/sparc/insns.decode`). sparc64 is right to refuse most of these: in V9 rd 0 is
  LDFSR/STFSR, rd 1 LDXFSR/STXFSR, rd 3 LDXEFSR, and the rest are reserved.
- **Introduced by:** `3d3c06737b` ("target/sparc: Move LDFSR, STFSR to decodetree", 2023-10,
  first in v8.2.0). Before it, the legacy decoder's `case 0x21` and `case 0x25` checked rd only
  under `TARGET_SPARC64` (for rd 1) and otherwise loaded or stored the FSR whatever rd was.
- **Same kind of bug, already fixed upstream:** `b6cdd6c605` ("target/sparc: Loosen decode of
  STBAR for v8", issue #3097) and `49d669ccf3` ("target/sparc: Loosen decode of RDY for v7"), both
  v10.2.0, both fixing over-strict decodes from the same decodetree series.
- **Who to tell:** `MAINTAINERS`, "SPARC TCG CPUs" (`target/sparc/`): Mark Cave-Ayland (M), Artyom
  Tarasenko (M); Richard Henderson wrote the decodetree conversion.

## Where in the code

`target/sparc/insns.decode`, v11.1.3 and master:

```
LDFSR       11 00000 100001 ..... . .............          @n_r_ri
LDXFSR      11 00001 100001 ..... . .............          @n_r_ri
LDXEFSR     11 00011 100001 ..... . .............          @n_r_ri
...
STFSR       11 00000 100101 ..... . .............          @n_r_ri
STXFSR      11 00001 100101 ..... . .............          @n_r_ri
```

With rd fixed at `00000`, an LDFSR or STFSR word with any other rd matches nothing on sparc32 and
the translator raises `TT_ILL_INSN`.

## Fix (in prose)

Decode LDFSR and STFSR with any rd, after the V9 patterns: an overlapping group in which LDXFSR
(rd 1) and LDXEFSR (rd 3), or STXFSR (rd 1), come first and LDFSR/STFSR follow with an `rd:5`
field. On sparc32 the 64-bit `trans_` functions return false and decoding falls through to
LDFSR/STFSR. In `trans_LDFSR` and `trans_STFSR`, refuse rd other than 0 when `avail_64(dc)`, so
sparc64 keeps raising the trap for the reserved values. This restores what sparc32 did before
8.2.0 and changes nothing for sparc64.

## Reproducing

Without a guest OS: a boot PROM on `-M SS-5` (MMU off) that sets `PSR.EF`, stores a value at
`[%sp + 0xe0]`, executes `c90ba0e0` and `c92ba0e0`, and stores a marker. On v11.1.3 it takes trap
type 2 (illegal instruction) at the `ld`; with the fix it reaches the marker and the FSR value reads
back. Our qtest `sun4m-fsr-rd-test` does this for rd 0, 4 and 31. With SunOS 4.1.4: a program that
uses the FPU and then catches a signal, linked statically against an old libc whose `_sigtramp`
has these words.

## What was verified

- **The qtest:** with the wsh-pve series (0001-0025) on v11.1.3 and without the fix, `rd0` passes
  and `rd4` fails with trap type 2; with the fix `rd0`, `rd4` and `rd31` pass. The other sparc
  qtests and `sun4u-cmd646-test` (sparc64) pass with it.
- **History:** `git show 3d3c06737b` in a QEMU clone (the legacy `case 0x21`/`case 0x25` above),
  `git tag --contains 3d3c06737b` (first in v8.2.0), and master's `insns.decode` (unchanged).
- **The SunOS 4 programs:** LEMU's commit reports the SIGILL on the old build and that `islandLIC`
  stays up with the fix. Not reproduced here.
- **Existing reports:** the QEMU GitLab issues API, searched on 2026-11-18 for "LDFSR", "STFSR",
  "fsr sparc", "sparc illegal instruction", "sigtramp", "SunOS SIGILL" and "fsr rd", and a web
  search for LDFSR/STFSR rd decodetree illegal instruction: nothing about this. #2340 ("SPARC fp
  operation INVALID trap hangs on offending instruction", closed) touches `trans_LDFSR` but is a
  different problem; #2385 (SIGILL stepping over `std` in gdb) is unrelated.

## Sending it upstream

QEMU declines contributions that include or are derived from AI-generated content
(`docs/devel/code-provenance.rst`). This note and our qtest were written with an AI agent, and LEMU
states that its code won't be sent to QEMU, so the route is a bug report that describes the problem
and the fix in prose, crediting Antoni Sawicki, and leaves the patch to the maintainers (or to
Antoni, if he wants to send his own).

- Bug report: open a GitLab issue at <https://gitlab.com/qemu-project/qemu/-/issues> with the
  summary, the code location, the two instruction words and the fix in prose.
- Cc Mark Cave-Ayland and Artyom Tarasenko (`scripts/get_maintainer.pl -f target/sparc/translate.c`).
- Drop 0026 and 0027 once a fixed QEMU reaches pve-qemu.
