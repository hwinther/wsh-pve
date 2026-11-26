# wisp-netbsd, wisp's NetBSD sibling

A second, independent OS test of the machines wisp (`e2e/wisp`) boots: a small NetBSD 11.1 kernel
with a memory-disk root that holds one program, `/sbin/init`, a static C program against NetBSD's
own libc. It boots with `-kernel` (on sparc64 from a small boot disk) on the serial console,
prints wisp's markers, runs two checks and wisp's compute loop, and powers the machine off. Where
wisp asks "does Linux run on this QEMU machine", wisp-netbsd asks the same of a kernel written by
other people, with other drivers, other firmware calls and other ways of being started.

| Architecture | NetBSD port | QEMU | Machines | Console |
| --- | --- | --- | --- | --- |
| `sparc32` | sparc (sun4m, V8) | `qemu-system-sparc` | `SS-5` (default), `SS-10`, `SS-20`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`, `Voyager`, all with the published OpenBIOS | `zs0` channel A (ttya) |
| `sparc64` | sparc64 | `qemu-system-sparc64` | `sun4u`, from a boot disk (see "Loading the kernel") | `com0` on the EBus (su) |
| `x86_64` | amd64 | `qemu-system-x86_64` | `pc` (default), `q35` | `com0` |

Everything comes from NetBSD's own sources; nothing prebuilt is downloaded. NetBSD's `build.sh`
builds the cross toolchain and the kernel in a Debian container without root (`build.sh -U`).

## What PID 1 prints

```
WISP-BANNER wsh-pve wisp-netbsd v1
WISP-INFO uname: NetBSD 11.1 sparc
WISP-INFO cpus: 1 memory: 114560 kB pid: 1
WISP-CHECK name=clock ok=1 sleep_ms=200 mono_ms=207 real_ms=207
WISP-CHECK name=file ok=1 bytes=65536 remount=1 errno=0
WISP-RESULT v=1 arch=sparc32 machine=sparc release=11.1 cpus=1 mem_kb=114560 uptime_ms=1207 loops=4096 crc=0x35a46014 loop_ms=426 status=ok
```

- The banner, `WISP-INFO` and `WISP-RESULT` lines are wisp's (`e2e/wisp/README.md`, "What PID 1
  prints"), so `run.py` here parses them with wisp's own `run.py`. The CRC is wisp's: the same
  loop gives the same CRC on Linux and NetBSD, big- and little-endian.
- `uptime_ms` is `CLOCK_MONOTONIC` when PID 1 starts (NetBSD counts it from boot). CPUs and memory
  come from `sysctl` (`hw.ncpu`, `hw.physmem64`).
- `loops` is always 4096: NetBSD hands init no kernel command line, so there is no `loops=`.
- The clock check: a 200 ms `nanosleep` must take 150-2000 ms on `CLOCK_MONOTONIC`, and
  `CLOCK_REALTIME` must move by the same amount within 100 ms.
- The file check: PID 1 remounts the memory-disk root read-write (`MNT_UPDATE`), writes 64 KiB
  of a pattern to a file, reads it back, compares and removes it.
- `status=ok` only when both checks passed and the program runs as PID 1 (`checkfailed`,
  `notpid1` otherwise).
- Power-off: `reboot(RB_HALT | RB_POWERDOWN)`. On sun4m NetBSD asks the firmware (`power-off`)
  and falls back on the power register (`power0`); on sun4u it uses the firmware's power-off; on
  the PC, ACPI. QEMU runs with `-no-reboot`. If `reboot()` returns, PID 1 prints
  `WISP-POWEROFF-FAILED`.
- PID 1 starts without open files; it opens `/dev/console` (a node in the image) as stdin, stdout
  and stderr.

## Loading the kernel

**sparc32: QEMU's `-kernel` with OpenBIOS works as it is.** QEMU's sun4m loader takes NetBSD's
ELF kernel (linked at `0xf0004000`) to physical `0x4000`, as it does Linux's image; OpenBIOS
says `Kernel already loaded` and starts it with the romvec; and NetBSD's `locore` runs from there
without its boot loader or a `bootinfo` (it then has no symbol table for `ddb`, which this kernel
leaves out anyway). No disk image, no netboot, no OpenBIOS or QEMU change, on all eight sun4m
machines QEMU has.

**sparc64: from a boot disk.** OpenBIOS's `-kernel` on sun4u jumps to a fixed address where QEMU
puts a Linux image (`IMAGE_VIRT_ADDR + 0x4000`, `arch/sparc64/boot.c`); NetBSD's kernel is linked
at `0x01000000` and expects `ofwboot`'s `bootinfo`, so the jump returns and OpenBIOS falls back to
the disk. The kernel boots instead the way NetBSD boots on a real sun4u: `build.sh` makes
`disk.img`, a Sun disk label with partition `a` over a small FFS file system holding `ofwboot` and
the kernel (`netbsd`), and NetBSD's Forth `bootblk` (`installboot`) after the label. `run.py` gives
it to QEMU as an IDE disk (`snapshot=on`, `-boot c`); OpenBIOS runs the bootblk, which loads
`ofwboot`, which loads the kernel. Reading the 3.6 MB kernel through OpenBIOS's IDE driver takes
most of the 8.7 s before the kernel's first line. A `-kernel` path would need an OpenBIOS change
(start an ELF at its entry, and give NetBSD what `ofwboot` gives it); the test doesn't need one.

**amd64: `-kernel` through the PVH entry.** QEMU's `-kernel` takes no 64-bit multiboot image, but
it starts an ELF kernel with a Xen `PHYS32_ENTRY` note (PVH). NetBSD's amd64 kernel has one with
`options XEN` (without `XENPV`), and its `start_pvh` works under a VMM that isn't Xen. The console
is set in the configuration (`CONSDEVNAME="com"`), since there is no boot loader to choose it.

## Building

```sh
docker build -f e2e/wisp-netbsd/Dockerfile -t wsh-wisp-netbsd .      # from the repository root
docker run --rm -v "$PWD/e2e/wisp-netbsd/build:/wisp-netbsd/build" \
  -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out" wsh-wisp-netbsd ./build.sh sparc32 sparc64 x86_64
docker run --rm -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out:ro" wsh-wisp-netbsd \
  ./run.py --arch sparc32 --machine SS-5 --machine SS-20
```

The image (`Dockerfile`): Debian 13 with a host compiler, NetBSD 11.1's source sets `src`,
`syssrc`, `gnusrc` and `sharesrc` from cdn.netbsd.org, each checked against a pinned SHA-256
(taken after checking the release's own `source/sets/SHA512`), unpacked into `/usr/src/netbsd`
(3.7 GB), and the published `pve-qemu-kvm` with its firmware.

`build.sh <arch>...`, per architecture into `build/<arch>/` and `out/<arch>/`:

1. **tools**: NetBSD's `build.sh -U -m <machine> tools`, its cross gcc 12.5, binutils, `nbmake`,
   `nbconfig`, `nbmakefs` and `mdsetimage`. Kept in `build/<arch>/tools` and reused.
2. **libc**: `nbmake` installs the headers and builds `lib/csu`, `lib/libc` and libgcc into
   `build/<arch>/dest`, static only (`MKPIC=no`, no profiling, debug or compat libraries). Kept.
3. **init**: `init.c`, `gcc --sysroot=build/<arch>/dest -static -Os`, stripped.
4. **ramdisk.fs**: an FFS image (`nbmakefs`, big-endian on sparc) made from a spec file, so the
   device nodes (`/dev/console`, `/dev/md0a`) need no root: `/sbin/init` plus 256 KiB of room for
   the file check, rounded up to 64 KiB.
5. **kernel**: `config/WISP.<machine>` with `MEMORY_DISK_ROOT_SIZE` set to the image's size in
   blocks, built with `build.sh kernel=...`, the image put in with `mdsetimage` (as NetBSD's
   `INSTALL` kernels get theirs), stripped.
6. **disk.img** (sparc64): `ofwboot` and `bootblk` from `sys/arch/sparc/stand`, the FFS image
   with `ofwboot` and the kernel, `installboot`, and a Sun label (`sunlabel`).

The kernel configurations start from `std.<machine>` and add only what the boot needs: the CPU,
the buses down to the console, the clock and timer, FFS, `md` with `MEMORY_DISK_IS_ROOT`, and the
power-off device. No network, no disks, no `ddb`, no modules. sparc64 adds `ksyms`: its
`machdep.c` doesn't build (`-Werror`, unused variables in `get_symbol_and_offset()`) without
`ksyms`, `DDB` or `MODULAR`.

## Sizes and times

Sizes in bytes. The kernel carries the ramdisk (`MEMORY_DISK_ROOT_SIZE` x 512 bytes inside its
data); "kernel alone" is its text plus data without the ramdisk. The sparc64 and amd64 files are
larger than what they load: their segments are aligned to 4 MB and 2 MB pages in the file.

| Architecture | kernel file (stripped) | kernel alone (text + data - ramdisk) | ramdisk | PID 1 (static libc) | sparc64 `disk.img` | wisp's Linux kernel / PID 1 |
| --- | --- | --- | --- | --- | --- | --- |
| sparc32 | 2,465,248 | 1,428,765 | 917,504 | 613,048 | | 2,457,720 / 25,304 |
| sparc64 | 4,284,272 | 1,564,383 | 983,040 | 696,336 | 4,947,968 | 3,109,128 / 25,336 |
| x86_64 | 7,548,736 | 2,738,844 | 1,048,576 | 766,608 | | 1,291,264 / 29,360 |

Times: lab host, idle (load 1 on 14 threads), published `pve-qemu-kvm` 11.1.3-4+wsh30, TCG, three
boots per machine, all 36 passed. Seconds from starting QEMU, ranges over the three runs:

| Machine | to kernel | to PID 1 | to result | to power-off | loop ms |
| --- | --- | --- | --- | --- | --- |
| sparc32 SS-5 | 1.33-1.45 | 1.62-1.78 | 2.21-2.38 | 2.23-2.40 | 347-356 |
| sparc32 SS-10 | 1.28-1.37 | 1.58-1.68 | 2.19-2.29 | 2.21-2.31 | 350-363 |
| sparc32 SS-20 | 1.25-1.35 | 1.58-1.66 | 2.17-2.27 | 2.20-2.29 | 349-354 |
| sparc32 SS-4 | 1.36-1.44 | 1.67-1.78 | 2.28-2.39 | 2.30-2.41 | 355-361 |
| sparc32 SPARCClassic | 1.35-1.39 | 1.66-1.68 | 2.25-2.27 | 2.27-2.29 | 351-363 |
| sparc32 SPARCbook | 1.29-1.38 | 1.60-1.70 | 2.19-2.30 | 2.21-2.32 | 348-351 |
| sparc32 LX | 1.30-1.38 | 1.60-1.69 | 2.19-2.29 | 2.21-2.31 | 351-355 |
| sparc32 Voyager | 1.31-1.38 | 1.61-1.68 | 2.21-2.28 | 2.23-2.31 | 355-356 |
| sparc64 sun4u (boot disk) | 8.64-8.81 | 9.51-9.66 | 10.10-10.25 | 10.14-10.29 | 351-356 |
| x86_64 pc | 0.17-0.21 | 0.78-0.84 | 1.40-1.44 | 2.43-2.48 | 351-373 |
| x86_64 q35 | 0.19-0.25 | 0.79-0.81 | 1.39-1.40 | 2.43-2.44 | 350-353 |

- "to kernel" is NetBSD's `NetBSD 11.1 (WISP)` line; before it comes the firmware (OpenBIOS's SBus
  probe on sun4m; on sun4u also the bootblk and `ofwboot` reading the kernel from the disk).
- The result line comes after the 200 ms clock check. On the PC the power-off (ACPI S5, after
  NetBSD detaches its devices) takes another second.
- PID 1's `uptime_ms` is about 1100-1360: NetBSD's uptime starts at 1 s (its console time stamps
  begin at `1.0000000`), so the kernel needs 0.1-0.4 s of its own from start to PID 1.
- For comparison, wisp's Linux 7.3 kernels power off after 1.6-3.2 s on the same machines (wisp's
  README; lab, under load).
- On sun4m NetBSD often warns `timecounter went backwards` once during autoconfiguration (14 of 16
  logged boots, never on sun4u or the PC); the clock check passes after it. Not looked into yet
  (QEMU's slavio counter-timer as NetBSD's `timer0` timecounter reads it).

PID 1 is 600-720 KB of text because NetBSD's stdio brings jemalloc (`je_*`, its statistics printer
included), `dtoa` and the locale code with it; the program itself is a few KB.

Build times on the lab host: the tools 5 minutes per architecture (`-j14`, with another
architecture's tools building at the same time), headers and libc about a minute, a kernel
11-20 s; with tools and libc kept, `build.sh` for one architecture takes 24 s.

## Tests and CI

- `tests/test_run.py`: the runner's evaluation (markers, checks, CRC, power-off, timeout) and its
  QEMU command lines, without QEMU.
- `tests/test_init.py`: `init.c` built on a Linux host with glibc (not PID 1): its lines parse and
  its CRC is wisp's.

`python3 -m unittest discover -s e2e/wisp-netbsd/tests`

`.github/workflows/wisp-netbsd.yml` builds and boots each architecture in a job of its own on a
GitHub-hosted runner, on pull requests that touch wisp-netbsd (or wisp's `run.py`), on main and
on dispatch. NetBSD's tools and libc are cached per architecture (keyed on the Dockerfile and
`build.sh`), so a warm run builds only PID 1, the ramdisk and the kernel. Not a required check.

## Next

- The `timecounter went backwards` warning on sun4m (see above).
- sparc64 boot time: a gzipped kernel on the disk (`ofwboot` reads those) should cut the 8.7 s,
  most of which is OpenBIOS reading the disk.
- sparc32 SMP: a `GENERIC.MP`-style kernel on SS-10/SS-20 with `-smp 2` and `-smp 4`.
- PID 1 without stdio: `write(2)` and a small formatter would drop jemalloc and most of the
  600 KB; later, as the ROADMAP says, our own syscall stubs instead of libc.
- Kernel size: what of the 1.4-2.7 MB is left to cut (`options` from `conf/std`, amd64's ACPI).
- Tier 2 as in wisp: the disk controllers, a NIC on user-mode networking.

## License

NetBSD's sources are under the BSD license (mostly 2-clause, some 3- and 4-clause, as the files
say); the toolchain it builds is GCC and binutils (GPL). Nothing of NetBSD is stored in this
repository: the image downloads the source sets by checksum, and the kernels are built from them.
`init.c`, `build.sh`, `run.py` and the kernel configurations are this repository's.
