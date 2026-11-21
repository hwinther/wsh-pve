# The tiny test system

A minimal, distroless Linux for every architecture the lab emulates: a kernel and a built-in
initramfs that holds one file, `/init`, a static program built with the kernel's own nolibc
(`tools/include/nolibc`, no C library). It boots with `-kernel` on a serial console in a few seconds
under TCG, prints a banner, a few checks and one result line, and powers the machine off. It checks
that a QEMU binary can boot Linux on a machine at all, and measures TCG against TCI (the TCG
interpreter) without a disk, a firmware install or a guest OS in the way.

| Architecture | QEMU | Machine | Kernel console |
| --- | --- | --- | --- |
| `x86_64` | `qemu-system-x86_64` | `pc` | 8250, `ttyS0` |
| `i386` | `qemu-system-i386` | `pc` | 8250, `ttyS0` |
| `sparc32` | `qemu-system-sparc` | `SS-5` (also `SS-20` with `--machine`) | ESCC (zs), `ttyS0` |
| `sparc64` | `qemu-system-sparc64` | `sun4u` | 16550 "su" on the EBus, `ttyS0` |

## What PID 1 prints

```
TINY-BANNER wsh-pve tiny v1
TINY-INFO uname: Linux 7.3.4 sparc
TINY-INFO cpus: 1 memory: 109024 kB pid: 1
TINY-RESULT v=1 arch=sparc32 machine=sparc release=7.3.4 cpus=1 mem_kb=109024 uptime_ms=332 loops=4096 crc=0x35a46014 loop_ms=368 status=ok
reboot: Power down
```

- `uptime_ms`: `CLOCK_BOOTTIME` when PID 1 starts (the guest's view of its boot time).
- The compute loop: `loops` rounds of filling a 16 KiB buffer from a xorshift32 stream and running
  CRC-32 over it byte by byte in little-endian order. `crc` is the same on every architecture for
  the same loop count (`run.py` checks it, so a miscomputing CPU model fails the run); `loop_ms` is
  its `CLOCK_MONOTONIC` time. `loops=N` on the kernel command line changes the count (it reaches
  PID 1 as an environment variable); the default is 4096.
- CPU count from `sched_getaffinity`, memory from `sysinfo`: no `/proc` in the image.
- Power-off with `reboot(LINUX_REBOOT_CMD_POWER_OFF)`: ACPI on the PC, the sun4m power register on
  the SS-5/SS-20 and the firmware's power-off on sun4u. QEMU runs with `-no-reboot` and the kernel
  with `panic=-1`, so a panic ends QEMU as well; if power-off returns, PID 1 prints
  `TINY-POWEROFF-FAILED`.

## Build

```sh
docker build -f e2e/tiny/Dockerfile -t wsh-tiny .
docker run --rm -v "$PWD/e2e/tiny:/tiny" wsh-tiny ./build.sh all     # or x86_64 i386 sparc32 sparc64
```

The image is Debian 13 with Debian's cross compilers (`gcc-sparc64-linux-gnu`, `gcc-i686-linux-gnu`),
`linux-source-7.3` from trixie-backports (nolibc supports sparc since 6.16; trixie itself has 6.12)
and the published `pve-qemu-kvm`. `build.sh` unpacks the kernel into `build/` and per architecture:

1. installs the kernel's UAPI headers and the nolibc headers into a sysroot;
2. builds `init.c` with `-static -nostdlib -nostdinc -Os` (sparc32: `sparc64-linux-gnu-gcc -m32
   -mcpu=v8`, as the kernel's nolibc selftests do; i386 with `i686-linux-gnu-gcc`). The 32-bit sparc
   compiler has no libgcc, so `init.c` avoids 64-bit division and `__builtin_popcount`;
3. configures the kernel with `make tinyconfig` plus `config/common.config` (built-in uncompressed
   initramfs, ELF, printk, TTY, no SMP, no modules) and `config/<arch>.config` (serial driver and
   console; PCI and ACPI on the PC; PCI on sun4u for the EBus), and stops if `olddefconfig` dropped any
   line of the fragments;
4. builds the image (`bzImage`, or `arch/sparc/boot/image` for sparc) with the initramfs linked in.

Output in `out/<arch>/`: `kernel`, `init`, `config` and `sizes`. The kernel is uniprocessor: sparc32
SMP has no futex, and a single static init has no use for a second CPU.

## Run

```sh
docker run --rm -v "$PWD/e2e/tiny:/tiny" wsh-tiny ./run.py --arch all --label tcg --repeat 2
docker run --rm -v "$PWD/e2e/tiny:/tiny" wsh-tiny ./run.py --arch sparc32 --machine SS-20
./run.py --arch all --qemu-dir /path/to/tci-build --label tci --timeout 900 --json results.jsonl
```

`run.py` (Python standard library) starts QEMU with `-nodefaults -display none -serial stdio
-no-reboot -kernel out/<arch>/kernel`, timestamps each console line and kills QEMU at `--timeout`. One
JSON object per run on stdout (and appended to `--json`), a Markdown table on stderr at the end; exit
code 1 if any run failed. Per run: the host's load average at the start, the seconds from starting
QEMU to the kernel's `Linux version` line, to PID 1's banner, to the result line and to QEMU's exit,
PID 1's uptime and loop time, the CRC check, and QEMU's peak RSS and CPU time from `wait4`.
`--log-dir` keeps each run's console log with its timestamps.

Unit tests (parsing, the CRC model, the QEMU command line): `python3 -m unittest discover -s e2e/tiny/tests`.

### A TCI build

`qemu-tci.sh <qemu source> <build dir> [targets]` configures and builds QEMU with
`--enable-tcg-interpreter` for the four targets inside the tiny image (pve-qemu's `qemu` tree with its
`debian/patches` applied, or upstream QEMU 11.1). `MODE=tcg` builds the same tree without the
interpreter, for a comparison where only the backend differs. Point `run.py --qemu-dir` at the build
directory and pass `--firmware /usr/share/kvm` (the image sets `TINY_FIRMWARE` to it) so it finds
OpenBIOS and SeaBIOS.

## Results

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
- `SS-10` (TCG) passes as well (2.7 s to power-off). `-M LX` with OpenBIOS does not: the kernel stops
  right after switching to the zs console with `qemu: fatal: Trap 0x07 (Unaligned Memory Access)
  while interrupts disabled` at `tsetup_patch2`, three of three times, also with
  `-m 64`; not looked into.

## Not done

- No network, disk or SMP checks: tier 1 is boot, CPU, memory and power-off only.
- Not in the table: SS-10 (passes under TCG), the LX (fails, see above) and the Sun PROMs (`ss5.bin`
  and the SS-20 PROM boot from a disk, not from `-kernel`).
- No CI job; the unit tests run anywhere with Python 3.

## Notes: a WebAssembly build of qemu-system-sparc (not tried)

What a browser build of the sparc emulator would need, from reading the QEMU 11.1 tree (nothing
built):

- QEMU 11.1 builds for an Emscripten host only as **wasm64** (`configure --cpu=wasm64`, optionally
  `--wasm64-32bit-address-limit` for runtimes without full Memory64); there is no wasm32 host any
  more. TCG has no WebAssembly code generator in the tree, so `--enable-tcg-interpreter` is
  required: the TCI column above is the speed to expect, before the cost of running the interpreter
  itself as WebAssembly. Upstream CI builds it with `--static --disable-tools`.
- The cross build environment is `tests/docker/dockerfiles/emsdk-wasm64-cross.docker`: emsdk plus
  zlib, libffi, glib and pixman built from source with `-sMEMORY64=1 -sASYNCIFY=1 -pthread`.
  Coroutines use the `wasm` backend.
- pve-qemu's own additions (Proxmox Backup through libproxmox-backup-qemu0) need libraries that
  aren't built for Emscripten, so it would be upstream QEMU with only the sparc patches from
  pve-qemu's `debian/patches` (the `wsh/` ones), not the package's tree.
- At run time: OpenBIOS (`openbios-sparc32`) and this kernel image placed in Emscripten's file system
  for `-L` and `-kernel`, the serial console wired to a terminal in the page (`-serial` on a chardev
  the page reads), threads through SharedArrayBuffer (so the page needs cross-origin isolation
  headers), and no guest network without further work.
- The tiny system fits that well: no disk, a 2.4 MB kernel, output on the serial console only, and a
  result line a page can parse.
