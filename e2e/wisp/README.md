# wisp, the tiny test system

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
| `sparc32` | `qemu-system-sparc` | `SS-5` (also `SS-10`, `SS-20` and `LX` with `--machine`; `LX` needs OpenBIOS patch 0027) | ESCC (zs), `ttyS0` |
| `sparc64` | `qemu-system-sparc64` | `sun4u` | 16550 "su" on the EBus, `ttyS0` |

## What PID 1 prints

```
WISP-BANNER wsh-pve wisp v1
WISP-INFO uname: Linux 7.3.4 sparc
WISP-INFO cpus: 1 memory: 109024 kB pid: 1
WISP-RESULT v=1 arch=sparc32 machine=sparc release=7.3.4 cpus=1 mem_kb=109024 uptime_ms=332 loops=4096 crc=0x35a46014 loop_ms=368 status=ok
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
  the sun4m machines and the firmware's power-off on sun4u. QEMU runs with `-no-reboot` and the kernel
  with `panic=-1`, so a panic ends QEMU as well; if power-off returns, PID 1 prints
  `WISP-POWEROFF-FAILED`.
- On sparc, `init.c` brings its own `_start`. nolibc's is a C function around the asm that hands
  `argc`'s address to `_start_c`, and gcc (no `naked` functions on sparc) puts a `save %sp, -96, %sp`
  in front of it, so `_start_c` read `argc`, `argv` and the environment 96 bytes too low: `argc` 0
  and no `loops=` (or `wisp=`) from the kernel command line. Before this, `loops=` was silently
  ignored on sparc32 and sparc64.

## Interactive mode

`wisp=shell` on the kernel command line (it reaches PID 1 as an environment variable, like
`loops=`) starts a small shell on the serial console instead of the batch run. The banner line
comes first as in batch mode; the shell then lowers the kernel's console log level to emergencies
only, so kernel messages don't land in the middle of its output. The default (no `wisp=`) is the
batch run above, unchanged.

```sh
qemu-system-sparc -M SS-5 -m 128 -display none -nodefaults -serial stdio -monitor none \
  -kernel out/sparc32/kernel -append "console=ttyS0 wisp=shell"
```

| Command | What it does |
| --- | --- |
| `help` | the list of commands |
| `info`, `uname` | architecture, kernel (`uname`), CPUs, memory total and free, uptime, PID |
| `bench` | the compute loop of the batch run (`loops=`, default 4096 rounds) with its CRC, time and KiB/s |
| `crc <n>` | the loop's CRC after `n` rounds (1 to 1,000,000), with its time |
| `mandel` | the Mandelbrot set, 78 x 20 characters, in 4.12 fixed-point 32-bit integer math (sparc32 has no libgcc for 64-bit division, and no floating point is needed) |
| `banner` | the logo with the architecture and kernel release |
| `clear` | clears the screen (`ESC [H ESC [2J`) |
| `poweroff` | powers the machine off, as the batch run does |
| `reboot` | restarts the machine: QEMU exits with `-no-reboot`, or boots wisp again without it. Not on sun4u: OpenBIOS doesn't carry out Linux's restart request there and the kernel panics, so the shell refuses and says to use `poweroff` |

```
wisp:sparc32> crc 64
  crc32 0x36c8a4f9 after 64 rounds (1024 KiB) in 6 ms
wisp:sparc32> mandel
                                                  ..........
                                           ............+:..+......
                                       ...............:-==-:.........
                                   ................::=@@@@@#:...........
                                ...........:==-::-*-==*@@@*=-=-+:...:+...
                           ...............::-#@@@@@@@@@@@@@@@@@@@*@@*:.....
                    ......-:............::=@@@@@@@@@@@@@@@@@@@@@@@@@@::.....
             .............::-+---@=*-:::-*@@@@@@@@@@@@@@@@@@@@@@@@@@@*=:.....
         ...............::-++@@@@@@@@@@=@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@:......
        .............::-*@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%:.......
        .............::-*@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#:.......
         ...............::-=+@@@@@@@@@@=@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@:......
             .............::-+---@++-:::-*@@@@@@@@@@@@@@@@@@@@@@@@@@@*=:.....
                    ......-:............::=@@@@@@@@@@@@@@@@@@@@@@@@@@::.....
                           ...............::-#@@@@@@@@@@@@@@@@@@@*@@*:.....
                                ...........:==-::-*-==*@@@*=-+-+:...:=...
                                   ................::=@@@@@#:...........
                                       ...............:-==-:.........
                                           ............+:..+......
                                                  ..........
  78 x 20 points, 32 iterations, 90 ms
wisp:sparc32> poweroff
  powering off
reboot: Power down
```

- The layout fits an 80 x 24 terminal: `mandel` is 20 rows plus its footer, so the command, the
  picture and the next prompt fit on one screen. The prompt, the logo and `help` use a few ANSI
  colours (bold, green, blue, cyan) for a terminal such as xterm.js; everything else is plain.
- Line editing: the console stays in the kernel's canonical mode, so the TTY line discipline
  echoes and edits the line: Backspace (DEL, what xterm.js and most terminals send), Ctrl-U (the
  line), Ctrl-W (a word), Ctrl-C (drops the line). The shell itself also applies `^H` (which the
  line discipline echoes as `^H` but leaves in the line), turns a tab into a space and drops other
  control characters and `ESC [ ...` sequences such as the arrow keys. There is no history.
- Size: the shell adds about 3.5 KB to PID 1 on sparc (5,236 to 8,716 bytes on sparc32, 5,440 to
  8,904 on sparc64) and 4 KB to the x86 binaries, which are padded to 4 KiB pages (12,976 to 17,072
  on x86_64, 8,908 to 14,160 on i386). The commands are a string table and a `switch`, not a table of
  function pointers: that would need a `.data` section, and the linker pads the writable segment
  to the target's page size (64 KiB on sparc32, 1 MiB on sparc64).
- `run.py --shell` boots with `wisp=shell`, answers each prompt with the next line of a fixed script
  (`help` typed as `hepl`, two Backspaces and `lp`, then `info`, `bench`, `crc 64`, `mandel`,
  `poweroff`) and checks the answers: the command list (so the line discipline applied the
  Backspaces), the info lines, both CRCs against the model, every character of the 20 Mandelbrot
  rows against `shell.py`'s integer model (and `tests/mandel.txt`), and the power-off.

## Build

```sh
docker build -f e2e/wisp/Dockerfile -t wsh-wisp .
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./build.sh all     # or x86_64 i386 sparc32 sparc64
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
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --label tcg --repeat 2
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch sparc32 --machine SS-20
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --shell
./run.py --arch all --qemu-dir /path/to/tci-build --label tci --timeout 900 --json results.jsonl
```

With `--shell`, each run drives the interactive shell instead (see "Interactive mode"; `shell.py`):
the table has the seconds to the first prompt and to QEMU's exit and the `bench` and `mandel` times,
and `--log-dir` keeps the whole console transcript.

`run.py` (Python standard library) starts QEMU with `-nodefaults -display none -serial stdio
-no-reboot -kernel out/<arch>/kernel`, timestamps each console line and kills QEMU at `--timeout`. One
JSON object per run on stdout (and appended to `--json`), a Markdown table on stderr at the end; exit
code 1 if any run failed. Per run: the host's load average at the start, the seconds from starting
QEMU to the kernel's `Linux version` line, to PID 1's banner, to the result line and to QEMU's exit,
PID 1's uptime and loop time, the CRC check, and QEMU's peak RSS and CPU time from `wait4`.
`--log-dir` keeps each run's console log with its timestamps.

Unit tests (parsing, the CRC model, the QEMU command line, the shell transcript checks and the
Mandelbrot model against `tests/mandel.txt`): `python3 -m unittest discover -s e2e/wisp/tests`.
With a C compiler on the host, `tests/test_shell.py` also builds `init.c` against the host's C
library (it is written to build with both nolibc and glibc) and runs it outside PID 1: the batch
line with `loops=64`, the shell script, the Mandelbrot rows against `tests/mandel.txt`, line
editing and errors.

### A TCI build

`qemu-tci.sh <qemu source> <build dir> [targets]` configures and builds QEMU with
`--enable-tcg-interpreter` for the four targets inside the wisp image (pve-qemu's `qemu` tree with its
`debian/patches` applied, or upstream QEMU 11.1). `MODE=tcg` builds the same tree without the
interpreter, for a comparison where only the backend differs. Point `run.py --qemu-dir` at the build
directory and pass `--firmware /usr/share/kvm` (the image sets `WISP_FIRMWARE` to it) so it finds
OpenBIOS and SeaBIOS.

## CI

`.github/workflows/wisp-boot.yml` boots all four architectures, plus sparc32 on the SS-20, on a
GitHub-hosted runner (TCG) and fails when any run fails. It runs on every pull request (no `paths`
filter, so its `wisp-boot-required` check always reports; a `changes` job skips the boot when the pull
request touches neither `e2e/wisp/`, `submodules/pve-qemu.patch` nor the pve-qemu pin), on pushes to
main that change `e2e/wisp/` and by hand. After the batch runs, `run.py --arch all --shell` boots
the four architectures once more and drives the interactive shell (about 2 to 3 s each).

- Which QEMU: a pull request that changes `submodules/pve-qemu.patch`, the pve-qemu pin,
  `qemu-tci.sh` or the workflow gets QEMU built from its own tree: pve-qemu with `pve-qemu.patch`, its
  `qemu` submodule and `debian/patches/series` applied with `quilt push -a --fuzz=0` (what
  dpkg-source does), then `MODE=tcg ./qemu-tci.sh` for the four targets, and `run.py --qemu-dir`. The
  firmware stays the published package's. Every other run boots the published `pve-qemu-kvm` in the
  image. No workflow builds a pve-qemu-kvm package on a pull request, so the four binaries are built
  here instead of the whole package. With 4 jobs on the lab host that took 4 minutes, the kernels 7.
- The kernels (`out/`) are cached, keyed on the files that make them: `Dockerfile`, `build.sh`,
  `init.c` and `config/`. A change to `run.py`, the tests or the docs reuses them.
- The unit tests run first. The job summary has `run.py`'s tables. The artifact `wisp-boot-<pr|published>`
  has `results.jsonl` and the console logs.

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
- `SS-10` (TCG) passes as well (2.7 s to power-off). `-M LX` passes with OpenBIOS patch 0027 (see
  "The LX and the Voyager" below); with the published 11.1.3-3+wsh6 it stops at the console switch.

### The LX and the Voyager

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
chip there (SS-5, SS-4, SPARCClassic, SPARCbook). Until a `pve-qemu-kvm` with it is installed, pass
a patched `openbios-sparc32` with `--firmware` (QEMU's `-L`).

## Not done

- No network, disk or SMP checks: tier 1 is boot, CPU, memory and power-off only.
- Not in the table: SS-10 and LX (pass under TCG, see above) and the Sun PROMs (`ss5.bin`
  and the SS-20 PROM boot from a disk, not from `-kernel`).
- CI boots the published package or a pull request's QEMU binaries (see "CI"); a pull request that
  changes `openbios/**` is not checked with its own firmware, and TCI is not run in CI.

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
- wisp fits that well: no disk, a 2.4 MB kernel, output on the serial console only, and a
  result line a page can parse. With `wisp=shell` on the command line it is also something to type
  at in an xterm.js terminal (see "Interactive mode"): an 80 x 24 layout, line editing in the
  kernel's line discipline, and `bench` and `mandel` to show the emulated CPU at work.
