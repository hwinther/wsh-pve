---
title: wisp, the tiny test system
description: A one-program Linux for x86, sparc32 and sparc64 that checks a QEMU build boots and measures TCG against TCI
---

wisp, the tiny test system, is the smallest Linux the lab can boot on each emulated architecture: a
kernel (`make tinyconfig` plus a few options) with a built-in initramfs that holds a single static
program as PID 1, built with the kernel's own nolibc instead of a C library. glibc and musl don't
support 32-bit SPARC V8; nolibc does (since Linux 6.16), so the same `init.c` runs on all four.

It boots straight from QEMU's `-kernel` on a serial console (no disk, no installer, no guest OS),
prints a banner, the kernel's `uname`, the CPU count and memory, runs a fixed compute loop with its
time and a checksum, prints one result line and powers the machine off. A run under TCG takes 2 to
3 seconds.

| Architecture | QEMU machine | Kernel image | PID 1 |
| --- | --- | --- | --- |
| x86_64 | `pc` | 1,287,168 bytes | 17,072 bytes |
| i386 | `pc` | 1,126,912 bytes | 14,160 bytes |
| sparc32 | `SS-5`, `SS-20`, `SS-10`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`, `Voyager` | 2,441,336 bytes | 8,716 bytes |
| sparc64 | `sun4u` | 3,092,744 bytes | 8,904 bytes |

The x86 images are compressed `bzImage`s; the sparc images are the stripped, uncompressed ELF the
OpenBIOS loader takes. PID 1 includes the interactive shell below (before it: 12,976, 8,908, 5,236
and 5,440 bytes). CI (`.github/workflows/wisp-boot.yml`) boots every architecture and machine in
the table on pull requests that touch wisp or the QEMU build, and on main; the `LX` and the
`Voyager` need OpenBIOS patch 0027, in the published `pve-qemu-kvm` since 11.1.3-3+wsh9.

## What it is for

- **A smoke test of a QEMU binary.** Does this build boot Linux on this machine, write to
  its serial console, and power off? The checksum of the compute loop is the same on every architecture,
  so a CPU model that computes wrongly fails the run.
- **Comparing backends.** TCG (the JIT) against TCI (the TCG interpreter, the only backend QEMU
  has where it can't generate host code, such as a WebAssembly build), without a guest OS's own
  start-up time in the numbers.

## Interactive mode

`wisp=shell` on the kernel command line starts a small shell on the serial console instead of the
batch run; without it, nothing changes. It is meant as the base of a browser demo (QEMU as
WebAssembly with xterm.js), so it fits an 80 x 24 terminal and uses a few ANSI colours.

```sh
qemu-system-sparc -M SS-5 -m 128 -display none -nodefaults -serial stdio -monitor none \
  -kernel e2e/wisp/out/sparc32/kernel -append "console=ttyS0 wisp=shell"
```

| Command | What it does |
| --- | --- |
| `help` | the list of commands |
| `info`, `uname` | architecture, kernel, CPUs, memory, uptime, PID |
| `bench` | the batch run's compute loop with its CRC, time and KiB/s |
| `crc <n>` | the loop's CRC after `n` rounds |
| `mandel` | an ASCII Mandelbrot set (78 x 20) in fixed-point 32-bit integer math |
| `banner` | the logo |
| `clear` | clears the screen |
| `poweroff`, `reboot` | power off or restart (`reboot` not on sun4u, where OpenBIOS doesn't restart) |

The console stays in the kernel's canonical mode: the TTY line discipline echoes and edits the line
(Backspace, Ctrl-U, Ctrl-W, Ctrl-C). `run.py --shell` drives the shell over the serial console on
all four architectures and checks every answer, down to each character of the Mandelbrot set; CI
runs it after the batch boots. On sparc, `init.c` brings its own `_start`: nolibc's lost the
kernel's arguments and environment there, so until now `loops=` never reached PID 1 on sparc.

## Building and running

Everything is in `e2e/wisp/` (see its README):

```sh
docker build -f e2e/wisp/Dockerfile -t wsh-wisp .
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./build.sh all
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --repeat 2
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --shell
```

The image has Debian 13's cross compilers, `linux-source-7.3` from trixie-backports and the
published `pve-qemu-kvm`. `run.py` prints one JSON object per run and a table: seconds from starting
QEMU to the kernel's first line, to PID 1, to the result line and to power-off, the loop time and
QEMU's peak RSS. `qemu-tci.sh` builds a TCI QEMU for the same targets; `run.py --qemu-dir` runs the
system under it.

## TCG against TCI

Measured 2026-11-21 on the lab host (14 threads, shared with other jobs; 1-minute load average 4.2
to 5.7 during the runs), kernel 7.3.4, loop of 4096 rounds, one guest at a time, two passes (values
are pass 1 / pass 2). Seconds are wall time from starting QEMU. "tcg" is the published
`pve-qemu-kvm` 11.1.3-3+wsh6; "tcg-tree" and "tci" are built from the same patched pve-qemu tree,
with and without `--enable-tcg-interpreter`. All 24 runs passed (result line, CRC, power-off).

| arch (machine) | QEMU | load | to kernel s | to PID 1 s | to power-off s | loop ms | peak RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| x86_64 (pc) | tcg | 5.7 / 5.5 | 0.8 / 0.8 | 1.4 / 1.6 | 1.8 / 2.0 | 372 / 400 | 112 / 112 |
| x86_64 (pc) | tci | 5.4 / 5.7 | 12.9 / 14.1 | 15.2 / 16.7 | 23.0 / 24.9 | 7783 / 8192 | 74 / 73 |
| i386 (pc) | tcg | 5.7 / 5.5 | 0.6 / 0.9 | 1.2 / 1.5 | 1.6 / 2.0 | 373 / 406 | 106 / 106 |
| i386 (pc) | tci | 5.0 / 5.6 | 12.1 / 12.6 | 14.4 / 14.8 | 22.1 / 22.9 | 7724 / 7986 | 64 / 64 |
| sparc32 (SS-5) | tcg | 5.5 / 5.5 | 1.4 / 1.7 | 2.4 / 2.7 | 2.8 / 3.2 | 352 / 392 | 187 / 186 |
| sparc32 (SS-5) | tcg-tree | 5.5 / 5.6 | 1.5 / 1.6 | 2.4 / 2.6 | 2.8 / 3.0 | 378 / 382 | 182 / 181 |
| sparc32 (SS-5) | tci | 4.8 / 5.0 | 14.5 / 13.7 | 18.8 / 17.7 | 25.7 / 24.0 | 6846 / 6282 | 180 / 180 |
| sparc32 (SS-20) | tcg | 5.5 / 5.6 | 1.4 / 1.7 | 2.4 / 2.8 | 2.8 / 3.2 | 369 / 374 | 187 / 186 |
| sparc32 (SS-20) | tci | 5.2 / 4.2 | 15.2 / 13.0 | 20.2 / 17.0 | 27.5 / 23.4 | 7224 / 6312 | 181 / 181 |
| sparc64 (sun4u) | tcg | 5.5 / 5.6 | 1.0 / 1.1 | 2.1 / 2.5 | 2.5 / 2.9 | 366 / 401 | 96 / 93 |
| sparc64 (sun4u) | tcg-tree | 5.4 / 5.7 | 1.0 / 1.3 | 2.2 / 2.5 | 2.6 / 2.9 | 359 / 384 | 89 / 90 |
| sparc64 (sun4u) | tci | 4.8 / 4.7 | 9.2 / 8.5 | 19.2 / 16.7 | 26.1 / 23.0 | 6779 / 6196 | 88 / 88 |

- The compute loop is 15 to 21 times slower under TCI (x86 about 20x, sparc 15 to 20x); a whole
  boot to power-off 7 to 14 times.
- Much of a TCI boot comes before the kernel's first line: SeaBIOS plus the bzImage's XZ
  decompression take 12 to 14 s (0.6 to 0.9 s under TCG), OpenBIOS loading the ELF 9 to 15 s.
  From the kernel's first line to power-off is 10 to 17 s, of which the loop is 6 to 8.
- On sparc the published package and the same-tree TCG build are equal within the noise, so the
  TCG/TCI difference there is the backend alone (x86 has no same-tree TCG build in the table).
- Peak RSS is lower under TCI on x86 (64-74 against 106-112 MiB); on sparc it is about the same
  (sparc32 180-187 MiB with `-m 128`, sparc64 88-96 MiB with `-m 256`).
- `SS-10` (TCG) passes as well (2.7 s to power-off). `-M LX` passes with OpenBIOS patch 0027 (see
  "The LX and the Voyager" below); with the published 11.1.3-3+wsh6 it stopped at the console switch.
  All eight sparc32 machines (`SS-5`, `SS-20`, `SS-10`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`,
  `Voyager`) pass with 11.1.3-3+wsh9 in 2.4 to 3.2 s to power-off, batch and shell, with the
  package's QEMU and with QEMU built from the same tree; CI boots all of them.

## The LX and the Voyager

With the published 11.1.3-3+wsh6, `-M LX` stopped the kernel right after it switched to the zs
console: `qemu: fatal: Trap 0x07 (Unaligned Memory Access) while interrupts disabled` at
`tsetup_patch2` (three of three runs, also with `-m 64`); `-M Voyager` stopped the same way with
`Trap 0x02`. The PC was only where the damage ended. OpenBIOS gives every machine ID from 32 to 63
the SS-5's SBus devices, including the APC (`power-management` at `0x6a000000`), and Linux's
`apc` driver makes `apc_swift_idle()` the idle routine. QEMU has no APC there on the LX (a real
LX has none) or the Voyager, so the first idle (right after the console switch) read its register
with a data access error (trap 0x29 at `apc_swift_idle`). The load has no exception table entry,
and `do_sparc_fault()` dereferences the NULL that `search_exception_tables()` returns: each nested
fault takes a stack frame until the kernel stack has run down through the kernel's own text,
`do_sparc_fault` and `trap_setup` included, and QEMU stops in the overwritten trap entry code.
OpenBIOS patch 0027 (`openbios/patches/`) makes the APC node only on the machines that have the
chip there (SS-5, SS-4, SPARCClassic, SPARCbook). The published `pve-qemu-kvm` carries it since
11.1.3-3+wsh9: with that package, wisp boots on the LX and the Voyager, batch and shell; with
11.1.3-3+wsh8 both still stop as above (`Trap 0x07` on the LX, `Trap 0x02` on the Voyager). With an
older package, pass a patched `openbios-sparc32` with `--firmware` (QEMU's `-L`).
