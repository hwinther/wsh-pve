# wisp-test: big-endian testing in seconds

A GitHub Action that runs a C program on big-endian, strict-alignment Linux and passes or fails
on its exit status. It builds the program for sparc32 (SPARC V8, a SPARCstation 5) with nolibc by default,
boots it in wisp (`e2e/wisp/`, a Linux 7.3 `tinyconfig` kernel with a tiny PID 1) under QEMU from
Ubuntu's packages, and reads the exit code back. From starting QEMU to its exit takes 2 to 4
seconds; the first run on a runner also spends 10 to 30 seconds installing QEMU and the cross
compiler with `apt-get`.

On x86 or arm64 a program that reads a little-endian file format with `memcpy` into an `int`, or
loads a `uint32_t` from an odd address, works. On sparc the first gives the wrong value and the
second is killed with `SIGBUS`. This action shows both on a pull request.

```yaml
jobs:
  big-endian:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: hwinther/wsh-pve/.github/actions/wisp-test@<full commit SHA> # pin a commit
        with:
          sources: tests/byteorder_test.c src/parse.c
          cflags: -Iinclude -Wall
```

By default the program is PID 1's child in a system that has nothing else: no shell, no files but `/test`
itself, no network. Its stdout and stderr go to the serial console, which is the step's log.
Exit code 0 passes; any other exit code, or a signal, fails the step.

For a network service, the runner can wait for a serial readiness message and check a forwarded
TCP port before stopping QEMU. See the [HTTP service example](examples/httpd.md).

## Inputs

| Input | Default | What it is |
| --- | --- | --- |
| `sources` | | C files to build with the selected libc, whitespace-separated, globs allowed, relative to the working directory. Give this or `binary` |
| `binary` | | A static binary for the architecture, built by you (any C library, see "Your own toolchain") |
| `arch` | `sparc32` | `sparc32` (big-endian, V8, `SS-5`), `sparc64` (big-endian, V9, `sun4u`) or `x86_64` (little-endian, `pc`: the control, where a byte-order bug passes) |
| `libc` | `nolibc` | C library for source builds. Use `uclibc` on sparc32 or x86_64 for uClibc-ng |
| `toolchain` | | Local uClibc-ng SDK tarball to use instead of downloading it |
| `toolchain-url` | the architecture's tarball in the `wisp-toolchain` release | URL to download for a uClibc-ng build |
| `toolchain-sha256` | | Expected SHA-256 of the local or downloaded SDK tarball |
| `cflags` | | More compiler flags, after the default `-O2` (`-DFIXED`, `-Iinclude`, `-Wall -Werror`) |
| `args` | | Arguments for the program, whitespace-separated, no quoting |
| `mode` | `test` | PID 1 runs the payload with `wisp=test` or `wisp=run`. Run mode emits the WISP-RUN start and exit markers |
| `network` | `false` | Boot the format 2 kit's `kernel-net` with QEMU user networking and `ip=dhcp`. Format 1 kits still work in default test mode with networking off |
| `forward` | | Guest TCP port (1–65535) to forward to a free port on runner loopback. Requires `network: true` |
| `ready` | | Bash extended regex matched against serial lines from the run start marker (test mode uses the banner). With no regex the check starts at that marker |
| `check` | | Bash command on the runner. Exit 0 passes, any other status fails. QEMU stops after the check. The timeout includes readiness and the check |
| `timeout` | `60` | Seconds from starting QEMU to its exit; a test that runs longer is an `error` |
| `machine` | | QEMU `-M` instead of the default: `SS-10`, `SS-20`, `SS-4`, `SPARCClassic`, `SPARCbook` for sparc32 |
| `qemu-args` | | More QEMU arguments, whitespace-separated (`-m 256`) |
| `kit` | | A kit directory or `wisp-test-kit.tar.xz` to use instead of downloading `kit-url` |
| `kit-url` | the `wisp-test-kit` release of this repository | Where the kit (kernels and nolibc headers) comes from |
| `kit-sha256` | | The kit tarball's SHA-256 (the release has it in `wisp-test-kit.tar.xz.sha256`); checked when set |
| `install` | `true` | `apt-get install` QEMU and the cross compiler when they are missing |

## Outputs

| Output | What it is |
| --- | --- |
| `result` | `pass` or `fail` from the runner check when supplied, otherwise from the guest exit status. Build, boot and timeout errors produce `error` |
| `port` | Runner loopback TCP port, also available as `WISP_PORT` to the check. The forward closes when QEMU stops |
| `exit-code` | The program's exit code when PID 1 reports it. Empty when killed or stopped by the check |
| `signal` | The number of the signal that killed it, `0` if none. sparc numbers differ from x86: `SIGBUS` is 10 there, 7 on x86 |
| `signal-name` | `SIGBUS`, `SIGSEGV`, `SIGILL`, ... |
| `seconds` | From starting QEMU to its exit |
| `log` | The path of the console log |

The step fails unless the result is `pass`. To expect a failure (a known bug), set
`continue-on-error: true` and check `steps.<id>.outputs.result`, as this repository's self-test does
(`.github/workflows/wisp-test-action.yml`).

## How it works

1. QEMU (`qemu-system-sparc`, whose package also has `qemu-system-sparc64` and OpenBIOS, or
   `qemu-system-x86`) and, for nolibc source builds, the cross compiler (`gcc-sparc64-linux-gnu`) come from Ubuntu's archive.
2. The format 2 kit holds wisp's tier-1 and network kernels per architecture and the headers wisp's
   PID 1 is built with: the kernel's UAPI headers and nolibc (`tools/include/nolibc`, the C library
   of the kernel's own selftests, headers only). `e2e/wisp/kit.sh` packs it; the self-test workflow
   publishes it to the `wisp-test-kit` release.
3. In the default mode, the sources are built static against nolibc: `sparc64-linux-gnu-gcc -m32 -mcpu=v8 -static
   -nostdlib -nostdinc` for sparc32, `-m64` for sparc64. On sparc, nolibc's `_start` is replaced
   (`start-sparc.c`): gcc puts a stack frame in front of nolibc's, which then reads `argc`, `argv`
   and the environment from the wrong place. sparc32 also gets `libgcc-sparc32.c`: `/` and `%` on
   64-bit integers are calls to libgcc (`__udivdi3`, `__divdi3`, `__umoddi3`, `__moddi3`), and
   Ubuntu's 32-bit sparc libgcc is V8+, which the kernel refuses. The file has those and
   `__udivmoddi4` and `__divmoddi4`, as shift-subtract long division (one quotient bit per step,
   the V8 `udiv` when both operands fit in 32 bits); division by zero gets `SIGFPE`, as on sparc64
   and x86_64. `tests/div64.c`, signed and unsigned with known results, checks them on all three.
4. The binary goes into a one-file initramfs as `/test`. QEMU boots the kernel with `-initrd`; the
   kernel unpacks it next to the built-in one, and PID 1, started with `wisp=test`, runs `/test`
   with the `args`, waits for it and prints `WISP-TEST v=1 exit=N signal=N ms=N`, then powers the
   machine off.

## Build with uClibc-ng

On an x86_64 Linux runner, set `libc: uclibc` to compile with the released Buildroot SDK.
The action extracts and relocates the SDK, then links your program statically. The SDK includes
uClibc-ng and libgcc for sparc32 V8 or x86_64. The same wisp kernel runs the resulting binary.

```yaml
- uses: hwinther/wsh-pve/.github/actions/wisp-test@<full commit SHA>
  with:
    libc: uclibc
    arch: sparc32
    sources: tests/sort.c
```

The self-test runs `e2e/wisp/toolchain/hello/hello.c` on both targets. It exercises `qsort`,
`snprintf` and 64-bit division. To pin the SDK, set `toolchain-sha256` to the digest in the
release's `wisp-toolchain-<arch>.tar.xz.sha256` file. See the [local example](examples/uclibc.md).

## Limits

- **nolibc is not a full C library.** It has `printf` and friends (integers, strings, pointers:
  no floating point), `malloc`/`free` (each allocation is an `mmap`), the string and memory
  functions, `strtol`, `atoi`, `getenv`, `<stdint.h>`, `<endian.h>` (`htole32`, `be32toh`, ...),
  unbuffered `FILE *` wrappers over file descriptors (`fopen`, `fgets`, `fwrite`) and the system
  calls. It has no `qsort`, no locale, no `<math.h>` beyond `fabs`, no threads, no `setjmp`, no
  C++. For a fuller C library, use uClibc-ng or your own toolchain (below). Build the unit you want to check,
  with a small `main` that checks it, not the whole program.
- **nolibc on sparc32 has only the division helpers of libgcc**: there is no V8 libgcc, so the action links
  its own 64-bit division helpers there (`libgcc-sparc32.c`, below). Other libgcc helpers, such
  as the one `__builtin_popcount` calls (`__popcountsi2`), still fail to link there
  (`undefined reference to ...`). sparc64 and x86_64 link the compiler's libgcc.
- **sparc32 is V8**, as on a real SPARCstation 5: no V9 instructions. Ubuntu's 32-bit sparc libgcc
  and glibc are V8+ (`EM_SPARC32PLUS`, V9 code) even with `-mcpu=v8`, and the sparc32 kernel
  refuses such a binary; the action stops with a message when given one.
- **Default guest environment**: no files except `/test`, no `/proc`, `/sys` or `/dev` beyond
  `/dev/console`, no network, one CPU (wisp's tier-1 kernel is uniprocessor), 128 MB of memory on
  sparc32 (256 on sparc64; more with `qemu-args: -m 256`, the SS-5's maximum).
- **Emulated speed**: QEMU translates the guest's code (TCG), which is several times slower than
  the runner's CPU, and the boot costs 2 to 4 s of the `timeout`. Raise it for long tests.
- **x86_64 nolibc builds for the baseline**: the action adds `-march=x86-64`, the level QEMU's default
  `qemu64` CPU runs (Ubuntu 26.04's amd64v3 gcc defaults to `x86-64-v3`, which gets `SIGILL`
  there). A `binary` built for a newer level needs `qemu-args: -cpu max` (TCG emulates up to
  x86-64-v3, not AVX-512).
- **ubuntu-latest on x86_64**: the action uses `apt-get` and `sudo`. On other runners, install
  `qemu-system-sparc` (or `qemu-system-x86`) and `gcc-sparc64-linux-gnu` yourself and set
  `install: false`.
- `args` go on the kernel command line after `--` and are split on whitespace: no quoting, no
  spaces inside an argument.

## Your own toolchain

`binary` takes any static ELF for the architecture. For sparc64, Ubuntu's `gcc-sparc64-linux-gnu`
with its glibc (`libc6-dev-sparc64-cross`) builds a real C library program:

```sh
sparc64-linux-gnu-gcc -static -O2 -o test_sparc64 test.c
```

A static glibc `printf` and `malloc` program runs (checked on Ubuntu 24.04). Whether more does
depends on the system calls it makes: the `tinyconfig` kernel has no futexes, so threads don't
work, and no `/proc`. For sparc32 V8 there is no packaged C library (see "Limits"); Buildroot with
uClibc-ng builds one.

## Running it locally

`wisp-test.sh` is the whole action and runs on any Debian or Ubuntu host (as root or with sudo):

```sh
WISP_SOURCES=examples/endian.c WISP_ARCH=sparc32 ./wisp-test.sh     # fails: the bug
WISP_SOURCES=examples/endian.c WISP_CFLAGS=-DFIXED ./wisp-test.sh   # passes
```

Settings are the inputs as `WISP_*` environment variables (the script's header lists them).
`examples/endian.c` (a little-endian record read with `memcpy`) and `examples/align.c` (a
`uint32_t` read from an odd address) are the self-test's programs, each with its fix under
`-DFIXED`.
