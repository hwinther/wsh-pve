# OpenBIOS: a BEL on the framebuffer console hangs Solaris and SunOS (sparc32)

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0026-fb8-blink-screen-dont-wait-on-a-counter-that-may-be-stopped.patch`;
`openbios/Dockerfile` builds `openbios-sparc32` and `openbios-sparc64` with it, and pve-qemu installs
them over QEMU's images.

## Summary

On sparc32 (`qemu-system-sparc -M SS-5`, cg3 or TCX), a client OS whose console is the framebuffer
and that writes it through the PROM (Solaris 2.x, SunOS 4.1.4) hangs on the first BEL it prints:
the screen turns to inverse video (white background to black) and stays that way, and the console
takes no more output. Bash's completion bell (Tab with no unique match) is enough; so is
`echo ^G`. The machine itself keeps running in OpenBIOS: the guest's other work stops because the
console write never returns.

- **Affected:** `fb8-blink-screen` in `forth/device/display.fs` and `get-msecs`/`ms` in
  `forth/device/other.fs`, unchanged in current master `e5ac46dd24` (QEMU 11.1.3's `roms/openbios`).
- **Reached by:** every client that sends BEL to the firmware's terminal emulator while it owns the
  trap table: Solaris 2.6 and 9 and SunOS 4.1.4 on the framebuffer console were seen to hang (below).
  Not affected: a serial console (BEL goes to the client's own serial driver, or OpenBIOS's serial
  output, which doesn't blink), and NetBSD (its own `cgthree`/wscons driver draws the console once
  the kernel has attached it).
- **Also in the same code:** `2000 ms` is a hexadecimal 2000 (Forth's base is 16 there), so even at
  the firmware's own prompt the blink lasts 8.2 s; and the BEL case of `(term-emit)` leaves the flag
  `execute-device-method` returns for `/screen`'s (missing) `ring-bell` on the data stack, one cell
  per BEL (`0 > 7 emit ok` is followed by `1 >`).
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org; the code is at <https://github.com/openbios/openbios>. No issue about it
  in github.com/openbios/openbios (searched "blink", "bell", "hang console", 2026-11-20).

## Root cause

The terminal emulator answers BEL with `blink-screen`; `fb8-install` (used by `cgthree.fs`,
`tcx.fs`, `vga.fs`) sets it to:

```forth
: fb8-blink-screen ( -- )
  fb8-invert-screen 2000 ms
  fb8-invert-screen
  ;
```

`ms` polls `get-msecs` until it passes the deadline. On sparc32 `get-msecs` reads the Forth
variable `obp-ticks`, and the only thing that advances it is OpenBIOS's level-14 timer handler,
`irq_entry14` in `arch/sparc32/vectors.S` (10 per tick; `romvec.c` points `obp_ticks` and the
romvec's `pv_ticks` at the variable). Once Solaris or SunOS run, the trap base register points at
the kernel's own trap table, so that handler is never entered again, and `obp-ticks` stands still.
The client's console write (`pv_putstr`/`pv_nbputchar` or the v2 `write` on stdout) reaches
`(term-emit)`, which calls `fb8-blink-screen`, which inverts the screen and then waits for a counter
that will never move.

With our patch 0022 (romvec calls at PIL 15) the timer interrupt is masked during the call as well.
That shouldn't be needed for the hang (the client's trap table alone keeps `irq_entry14` from
running), but the lab only ran firmware with 0022; a run without it is still to do before this
goes upstream.

sun4u: `get-msecs` returns its fallback there (`obp-ticks` stays 0 at the prompt, so it counts its
own calls; `get-msecs .d` twice, 10 s apart, printed 0 and 1), so `ms` ends after that many calls
and the wait doesn't hang. The blink is just too short to see.

## Evidence

Solaris 2.6 5/98 End User on an SS-5 (QEMU 11.1.3 with the pve-qemu series, OpenBIOS
`e5ac46dd24` + our 0001-0025, cg3 at 1024x768, console on the framebuffer and the Sun keyboard),
`boot disk -s`, root password, then in the single-user shell:

```sh
echo B | tr B '\007'; echo AFTER-BEL
```

The screen went from the white (pale yellow) background to black and stayed so for the 30 s
watched; `AFTER-BEL` never appeared. Monitor while it was hung:

```
pc: ffd075dc  npc: ffd075e0
psr: 04400fe5            (PIL 15, supervisor, traps enabled)
$tbr = 0xf0040050        (the kernel's trap table)
obp_ticks (0xffda142c) -> 0xffd27cbc: 20970, and 20970 again 5 s later
PC samples: semis, dovar, enterforth, next, docon (the Forth inner interpreter)
```

The symbols are from `openbios-builtin.elf.nostrip` of a build of the same sources (its `.text` is
byte-identical to the packaged image's). SunOS 4.1.4 on the same machine (`boot disk -s`, the same
command): the same picture, `$tbr = 0xfe022050`, `obp_ticks` 22290 twice. Solaris 9 9/05: the same
hang. At the firmware's own prompt `7 emit` keeps the screen inverted for 9 to 11 s (the lab's
screenshots; `0x2000` ms = 8.2 s) and the prompt then reads `1 >`.

## Fix

Bound the wait so it ends whatever the client has done to the trap table or the interrupt level,
and use decimal numbers:

```forth
: fb8-blink-screen ( -- )
  fb8-invert-screen
  get-msecs d# 100 +
  d# 20000 0 do
    dup get-msecs - 0< if leave then
  loop
  drop
  fb8-invert-screen
  ;
```

At most 100 ms by the counter when it runs; at most 20000 reads of it when it doesn't (80-140 ms
under TCG on the lab's host, where 100000 reads took 400-680 ms at the prompt). A real OBP's flash
is brief as well. In `(term-emit)`, `execute-device-method drop`.

Alternatives considered: making `ms` work while a client owns the traps would mean reading a
hardware counter directly (the sun4m counter-timer's count on sparc32, `%tick` on sparc64), per
architecture, and `ms` has no other caller in the tree; and no wait at all would make the blink
invisible. The bounded loop is the smallest change that never hangs.

## Tested

The lab's `e2e/sparc/scenarios/fb-bell.py` (BEL at the firmware prompt, then in the guest's shell,
then three in a row; screenshots for the inversion, OCR for the shell's answer): see the table in
`submodules/SPARC.md`, "BEL on the framebuffer console". In short: with the fix Solaris 2.6, Solaris
9 and SunOS 4.1.4 come back after one and after three BELs, with the screen in its colours; without
it all three hang; NetBSD 11.1 and a Solaris serial console are unaffected either way.

## Sending it upstream

The bug and the fix are in OpenBIOS code that no LEMU patch touches, but the lab ran it on
pve-qemu's QEMU, which carries LEMU patches (ESCC and others), and on OpenBIOS with our 0001-0025.
Reproduce it once on plain QEMU 11.1.3 with its own OpenBIOS image (`echo` of a BEL in Solaris 2.6
on the cg3 console) before reporting, as the "Hold" rule in `README.md` asks for QEMU bugs.

The fix was written with an AI agent (Claude Code). Say so in the report, or describe the bug and
the fix in prose and let the maintainer write the patch.
