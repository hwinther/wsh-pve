# wisp, the tiny test system

A minimal, distroless Linux for every architecture the lab emulates: a kernel and a built-in
initramfs that holds one file, `/init`, a static program built with the kernel's own nolibc
(`tools/include/nolibc`, no C library). It boots with `-kernel` on a serial console in a few seconds
under TCG, prints a banner, a few checks and one result line, and powers the machine off. It checks
that a QEMU binary can boot Linux on a machine at all, and measures TCG against TCI (the TCG
interpreter) without a disk, a firmware install or a guest OS in the way. Tier 2 (a second kernel,
`kernel-t2`, and `run.py --tier2`) adds the devices the QEMU patches touch: a raw disk on each disk
controller, a NIC on QEMU's user-mode network and more than one CPU (see "Tier 2").

| Architecture | QEMU | Machine | Kernel console |
| --- | --- | --- | --- |
| `x86_64` | `qemu-system-x86_64` | `pc` | 8250, `ttyS0` |
| `i386` | `qemu-system-i386` | `pc` | 8250, `ttyS0` |
| `sparc32` | `qemu-system-sparc` | `SS-5` (also `SS-20`, `SS-10`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX` and `Voyager` with `--machine`; `LX` and `Voyager` need OpenBIOS patch 0027, in the published package since 11.1.3-3+wsh9) | ESCC (zs), `ttyS0` |
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
| `disk [dev ...]` | the tier-2 disk check (see "Tier 2") on each device, by default the ones in `wisp_disk=` (else `sda`); prints its `WISP-DISK` line |
| `net [if]` | the tier-2 network check on the interface (default `wisp_net=`, else `eth0`); prints its `WISP-NET` line |
| `smp` | the compute loop on every CPU at once; prints its `WISP-SMP` line |
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
  on x86_64, 8,908 to 14,160 on i386). Tier 2 adds 6.5 to 8.3 KB of code (see "Tier 2"). The commands are a string table and a `switch`, not a table of
  function pointers: that would need a `.data` section, and the linker pads the writable segment
  to the target's page size (64 KiB on sparc32, 1 MiB on sparc64).
- `run.py --shell` boots with `wisp=shell`, answers each prompt with the next line of a fixed script
  (`help` typed as `hepl`, two Backspaces and `lp`, then `info`, `bench`, `crc 64`, `mandel`,
  `poweroff`) and checks the answers: the command list (so the line discipline applied the
  Backspaces), the info lines, both CRCs against the model, every character of the 20 Mandelbrot
  rows against `shell.py`'s integer model (and `tests/mandel.txt`), and the power-off. With
  `--tier2` as well, it boots `kernel-t2` with the machine's first tier-2 profile (two CPUs on the
  PC, the SS-10 and the SS-20) and adds `disk`, `net` and `smp` before `poweroff`.

## Tier 2: disk, network, SMP

`kernel-t2` is the tier-1 kernel plus `config/tier2/common.config` and
`config/tier2/<arch>.config`: the block layer, SCSI disks, devtmpfs, the disk and network drivers of
each machine, packet sockets (no IP stack) and, where QEMU's machine has more than one CPU, SMP.
PID 1 is the same file in both kernels. Each check is switched on by a kernel command-line
parameter, which reaches PID 1 as an environment variable like `loops=`, and prints one more line
after the result line; without them the output is what it was. `run.py --tier2` boots each machine
once per profile below, adds the devices and the parameters, and checks the lines (and the disk
images afterwards):

| Machine | Disks (driver, guest device) | NIC (driver) | CPUs |
| --- | --- | --- | --- |
| `pc` (x86_64, i386) | PIIX3 IDE, `-drive if=ide` (`ata_piix`, `sda`); virtio-blk, `-device virtio-blk-pci` (`virtio_blk`, `vda`) | `e1000` (`e1000`); `virtio-net-pci` (`virtio_net`), in a second boot | 1, 2, 4 |
| `SS-10`, `SS-20` | ESP, `-drive if=scsi` (`sun_esp`, `sda`) | `lance` (`sunlance`) | 1, 2, 4 |
| `SS-5`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`, `Voyager` | ESP, `-drive if=scsi` (`sun_esp`, `sda`) | `lance` (`sunlance`) | 1 |
| `sun4u` | cmd646 IDE, `-drive if=ide` (`pata_cmd64x`, `sda`); virtio-blk on the PCI bus (`vda`) | `sunhme` (`sunhme`) | 1 |

```
WISP-DISK v=1 dev=sda index=0 size_kb=4096 read_kb=4096 read_crc=0x1460012b read_bad=0 read_ms=122 write_kb=1024 write_crc=0x30181bb3 write_ms=68 verify_crc=0x30181bb3 verify_bad=0 verify_ms=119 status=ok
WISP-NET v=1 if=eth0 mac=52:54:00:12:34:56 addr=10.0.2.15 peer=10.0.2.2 peer_mac=52:55:0a:00:02:02 arp_tries=1 arp_ms=23 payload=1400 echoes=8 rtt_min_us=144 rtt_avg_us=285 rtt_max_us=986 status=ok
WISP-SMP v=1 cpus=2 loops=4096 crc=0x35a46014 wall_ms=369 pinned=yes percpu=0:0x35a46014:345,1:0x35a46014:345 status=ok
```

- **Disk** (`wisp_disk=sda,vda`): `run.py` creates a 4 MiB raw image per disk for the run and fills
  it with the host pattern, a xorshift32 stream (the compute loop's generator) from a seed plus the
  disk's index, stored little-endian. PID 1 mounts devtmpfs on `/dev`, waits up to 10 s for the
  device node (disks are scanned asynchronously), reads all 4 MiB and compares them word by word
  with the host pattern (the read path, with data the guest didn't write), writes 1 MiB of its own
  pattern at offset 1 MiB, `fsync`s, drops the device's page cache (`BLKFLSBUF`, then close and open
  again) and reads the 1 MiB back from the device. The line has both CRC-32s, the words that
  differed and the times; `run.py` checks the CRCs against its model and, after QEMU has exited,
  the image: the guest's pattern at 1 MiB and the host's everywhere else, so the writes reached the
  image at the right offset and nothing else changed. No file system, no partition table.
- **Network** (`wisp_net=eth0`): one round trip and more over QEMU's user-mode network
  (`-nic user,model=...`). Of the candidates (a DNS query to slirp's 10.0.2.3, or ARP and ICMP echo
  to its gateway 10.0.2.2), ARP plus ICMP echo needs nothing outside QEMU: slirp answers both for
  10.0.2.2 itself, while its DNS forwards to the host's resolver, which a CI runner or an isolated
  lab host may not reach. No DHCP: PID 1 is 10.0.2.15. The kernel has no IP stack: PID 1 brings the
  interface up and sends and receives whole Ethernet frames on a packet socket, which saves 385 KB
  of sparc32 kernel against `CONFIG_INET` (3.70 against 3.31 MB) and drives the NIC model the same
  way. An ARP request for 10.0.2.2 goes out every 200 ms until slirp answers (`arp_tries`,
  `arp_ms`: the e1000 reports its link about 1 s after it comes up, the other NICs at once), then
  8 ICMP echo requests with 1,400 bytes of pattern (1,442-byte frames) each wait for their reply,
  whose IP and ICMP checksums and payload must be right. PID 1 also answers slirp's ARP requests
  for 10.0.2.15. The round-trip times are in microseconds from sending to the reply.
- **SMP** (`wisp_smp=1`, with `-smp N`): one child per CPU (`fork`, which is `clone` without
  `CLONE_VM`), each pinned to its CPU with `sched_setaffinity` and checked with `getcpu`, runs the
  compute loop; the CRCs come back through pipes. Every CPU must return the model's CRC, and
  `wall_ms` against the per-CPU times shows whether the vCPUs ran in parallel (MTTCG).
- On sparc32, `run.py --tier2` (or `--shell --tier2`) adds two kernel parameters.
  `esp_scsi.esp_bus_reset_settle=0`: the ESP driver otherwise waits 3 s after its bus reset for
  real disks to settle, on every boot (the ESP is on the board), which QEMU's don't need.
  `lpj=2000000`, a fixed delay-loop calibration (the lab host measures 1.7 to 2.4 million under
  TCG): in one of about 60 sparc32 boots on a loaded host, QEMU was descheduled during the kernel's
  calibration, which then settled on `lpj=8191`; with that, the boot CPU gave the second CPU a few
  milliseconds instead of 2 s to start (`Processor 1 is stuck`), and the boot hung in RCU stalls.
  With the fixed value, 30 of 30 more boots of the SS-10 and the SS-20 (devices, 2 and 4 CPUs)
  passed.

The SMP decision per architecture:

- **x86_64 and i386**: SMP in `kernel-t2` (`CONFIG_SMP`, up to 8 CPUs, found through ACPI), tested
  with `-smp 2` and `-smp 4`. QEMU runs x86 vCPUs in parallel threads (MTTCG): the wall time of 2
  or 4 loops is about one loop.
- **sparc32**: SMP in `kernel-t2` (up to 4 CPUs), tested on the `SS-10` and the `SS-20` with
  OpenBIOS and `-smp 2` and `-smp 4`. The kernel drops futex by itself (`FUTEX` depends on
  `!(SPARC32 && SMP)`: there is no compare-and-swap on V8); PID 1 uses none, nor does nolibc. The same
  SMP kernel boots the six uniprocessor sun4m machines, so there is one sparc32 `kernel-t2`. The
  tier-1 kernel stays uniprocessor.
- **sparc64**: uniprocessor. QEMU's `sun4u` takes one CPU (`Invalid SMP CPUs 2. The max CPUs
  supported by machine 'sun4u' is 1`), so an SMP kernel would have nothing to run on.

Sizes (bytes; the x86 kernels are compressed `bzImage`s, the sparc ones uncompressed ELF):

| Architecture | kernel before | kernel now | `kernel-t2` | PID 1 before | PID 1 now (code) |
| --- | --- | --- | --- | --- | --- |
| x86_64 | 1,287,168 | 1,291,264 | 1,836,032 (+545 KB) | 17,072 | 21,168 (5,784 to 12,365) |
| i386 | 1,126,912 | 1,131,008 | 1,675,776 (+545 KB) | 14,160 | 19,236 (6,265 to 13,676) |
| sparc32 | 2,441,336 | 2,449,528 | 3,311,560 (+862 KB) | 8,716 | 16,908 (7,915 to 16,168) |
| sparc64 | 3,092,744 | 3,100,936 | 4,117,384 (+1,016 KB) | 8,904 | 17,096 (7,867 to 15,988) |

The tier-1 kernel only grows by PID 1 (the tier-2 code is 6.6 to 8.3 KB; the file sizes jump more
because the writable segment starts on the next page). `kernel-t2` is separate so tier 1 keeps its
size and boot time. Of the tier-2 growth on sparc32, the IP stack would have been another 385 KB
(see "Network"); `config/tier2/common.config` also turns off what `CONFIG_NET` and `CONFIG_BLOCK`
switch on by default and nothing uses (wireless, PTP, partition tables, extra I/O schedulers, swap).

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
4. builds the image (`bzImage`, or `arch/sparc/boot/image` for sparc) with the initramfs linked in;
5. does steps 3 and 4 again for `kernel-t2` with `config/tier2/common.config` and
   `config/tier2/<arch>.config` on top (where fragments set the same option, the later one counts,
   and the check in step 3 checks the result). `TIER2=0` skips it.

Output in `out/<arch>/`: `kernel`, `kernel-t2`, `init`, `config`, `config-t2` and `sizes`. The tier-1
kernel is uniprocessor; `kernel-t2` is SMP on x86 and sparc32 (see "Tier 2").

## Run

```sh
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --label tcg --repeat 2
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch sparc32 --machine SS-20 --machine LX
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --shell
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch all --tier2
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch sparc32 --machine SS-20 --shell --tier2
./run.py --arch all --qemu-dir /path/to/tci-build --label tci --timeout 900 --json results.jsonl
```

With `--tier2`, each machine boots `kernel-t2` once per tier-2 profile (see "Tier 2"; `tier2.py`
has the profiles, the QEMU arguments and the models): the table has the disk times (read, write
with `fsync`, read-back, in ms), the ARP time and the mean echo round trip, and the SMP loop and
wall times. The disk images go to a temporary directory (`--image-dir` to choose one) and are
removed after each run.

With `--shell`, each run drives the interactive shell instead (see "Interactive mode"; `shell.py`):
the table has the seconds to the first prompt and to QEMU's exit and the `bench` and `mandel` times,
and `--log-dir` keeps the whole console transcript.

`run.py` (Python standard library) starts QEMU with `-nodefaults -display none -serial stdio
-no-reboot -kernel out/<arch>/kernel`, timestamps each console line and kills QEMU at `--timeout`. One
JSON object per run on stdout (and appended to `--json`), a Markdown table on stderr at the end; exit
code 1 if any run failed. Per run: the host's load average at the start, the seconds from starting
QEMU to the kernel's `Linux version` line, to PID 1's banner, to the result line and to QEMU's exit,
PID 1's uptime and loop time, the CRC check, and QEMU's peak RSS and CPU time from `wait4`.
`--log-dir` keeps each run's console log with its timestamps. `--machine` overrides `-M`; given
more than once, each machine is booted in turn (for every `--arch`), and the table's `machine`
column shows the `-M` of each run.

Unit tests (parsing, the CRC model, the QEMU command line, the shell transcript checks, the
Mandelbrot model against `tests/mandel.txt` and the tier-2 profiles, line checks and image
checks): `python3 -m unittest discover -s e2e/wisp/tests`.
With a C compiler on the host, `tests/test_shell.py` also builds `init.c` against the host's C
library (it is written to build with both nolibc and glibc) and runs it outside PID 1: the batch
line with `loops=64`, the shell script, the Mandelbrot rows against `tests/mandel.txt`, line
editing and errors, and (`tests/test_tier2.py`) the disk check on image files (a name with a `/` is
a path) and the SMP check on the host's CPUs. The network check needs a NIC and root, so it is
checked under QEMU only.

### A TCI build

`qemu-tci.sh <qemu source> <build dir> [targets]` configures and builds QEMU with
`--enable-tcg-interpreter` for the four targets inside the wisp image (pve-qemu's `qemu` tree with its
`debian/patches` applied, or upstream QEMU 11.1). `MODE=tcg` builds the same tree without the
interpreter, for a comparison where only the backend differs. Point `run.py --qemu-dir` at the build
directory and pass `--firmware /usr/share/kvm` (the image sets `WISP_FIRMWARE` to it) so it finds
OpenBIOS and SeaBIOS.

## CI

`.github/workflows/wisp-boot.yml` boots all four architectures, then sparc32 on the other seven
machines (`SS-20`, `SS-10`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`, `Voyager`), on a
GitHub-hosted runner (TCG) and fails when any run fails. It runs on every pull request (no `paths`
filter, so its `wisp-boot-required` check always reports; a `changes` job skips the boot when the pull
request touches neither `e2e/wisp/`, `submodules/pve-qemu.patch` nor the pve-qemu pin), on pushes to
main that change `e2e/wisp/` and by hand. After the batch runs, `run.py --arch all --shell` boots
the four architectures once more and drives the interactive shell (about 2 to 3 s each). Then tier
2: `run.py --tier2` on the four architectures and the seven other sparc32 machines (21 boots: every
disk controller, every NIC, 2 and 4 CPUs on the PC, the SS-10 and the SS-20), and `--shell
--tier2` on the four architectures.

- Which QEMU: a pull request that changes `submodules/pve-qemu.patch`, the pve-qemu pin,
  `qemu-tci.sh` or the workflow gets QEMU built from its own tree: pve-qemu with `pve-qemu.patch`, its
  `qemu` submodule and `debian/patches/series` applied with `quilt push -a --fuzz=0` (what
  dpkg-source does), then `MODE=tcg ./qemu-tci.sh` for the four targets, and `run.py --qemu-dir`. The
  firmware stays the published package's. Every other run boots the published `pve-qemu-kvm` in the
  image. No workflow builds a pve-qemu-kvm package on a pull request, so the four binaries are built
  here instead of the whole package. With 4 jobs on the lab host that took 4 minutes, the kernels 7
  (14 since tier 2 added `kernel-t2`).
- The machines: the LX and the Voyager boot only with OpenBIOS patch 0027, which the published
  package has since 11.1.3-3+wsh9. Since the firmware is the published package's in both modes, a
  pull request's QEMU binaries boot them with the fixed OpenBIOS as well. On the lab host, all 15
  boots of the step (4 architectures, 7 more sparc32 machines, 4 shells) took 36 s with QEMU built
  from the tree and passed in both modes; each boot is 1.3 to 3.2 s to power-off.
- The kernels (`out/`, both tiers) are cached, keyed on the files that make them: `Dockerfile`,
  `build.sh`, `init.c` and `config/` (with `config/tier2/`). A change to `run.py`, `tier2.py`, the
  tests or the docs reuses them.
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
  "The LX and the Voyager" below); with the published 11.1.3-3+wsh6 it stopped at the console switch.
  All eight sparc32 machines (`SS-5`, `SS-20`, `SS-10`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`,
  `Voyager`) pass with 11.1.3-3+wsh9 in 2.4 to 3.2 s to power-off, batch and shell, with the
  package's QEMU and with QEMU built from the same tree; CI boots all of them.

### Tier 2

Measured 2026-11-21 on the lab host (1-minute load average 1.3 to 4.0), TCG, one guest at a time,
one pass per QEMU: "tree" is QEMU built from main's patched tree as CI builds it (`MODE=tcg
./qemu-tci.sh`), "published" the published `pve-qemu-kvm` 11.1.3-3+wsh9; values are tree /
published. Disk times are ms to read 4 MiB, to write 1 MiB with `fsync`, and to read the 1 MiB back
from the device; ARP is ms until slirp's reply, RTT the mean of 8 echoes of 1,442-byte frames. All
21 batch boots and all 11 shell boots passed in both modes, as did tier 1 (batch and shell on all
eleven machines). A cold build of all eight kernels took 14 min with 4 jobs.

| arch (machine) | profile | disk read/write/verify ms | ARP ms | RTT us | SMP loop / wall ms | to power-off s |
| --- | --- | --- | --- | --- | --- | --- |
| x86_64 (pc) | IDE, virtio-blk, e1000 | sda 45/27/17 / 44/45/20, vda 38/18/11 / 38/19/12 | 1007 / 1009 | 194 / 255 | - | 3.5 / 3.6 |
| x86_64 (pc) | virtio-net | - | 17 / 20 | 362 / 363 | - | 2.1 / 2.2 |
| x86_64 (pc) | 2, 4 CPUs | - | - | - | 2 x 374 / 389, 4 x 377 / 389 (tree) | 2.5-2.6 |
| i386 (pc) | IDE, virtio-blk, e1000 | sda 59/41/21 / 63/38/21, vda 51/23/17 / 52/48/19 | 1009 / 1009 | 242 / 221 | - | 3.5 / 3.7 |
| i386 (pc) | virtio-net | - | 28 / 19 | 361 / 368 | - | 2.0 / 2.1 |
| i386 (pc) | 2, 4 CPUs | - | - | - | 2 x 334 / 349, 4 x 334 / 347 (tree) | 2.4-2.6 |
| sparc32 (SS-5) | ESP, lance | 128/70/110 / 121/65/101 | 22 / 23 | 321 / 344 | - | 3.3 / 3.3 |
| sparc32 (SS-20) | ESP, lance | 75/51/66 / 73/48/70 | 21 / 22 | 298 / 266 | - | 3.1 / 3.0 |
| sparc32 (SS-20) | 2, 4 CPUs | - | - | - | 2 x 346 / 384, 4 x 358 / 388 (tree) | 3.2-3.4 |
| sparc32 (SS-10) | ESP, lance | 69/44/66 / 72/49/69 | 22 / 20 | 271 / 299 | - | 3.0 / 3.0 |
| sparc32 (SS-10) | 2, 4 CPUs | - | - | - | 2 x 345 / 380, 4 x 343 / 373 (tree) | 3.2-3.4 |
| sparc32 (SS-4) | ESP, lance | 120/68/103 / 122/68/101 | 23 / 20 | 314 / 314 | - | 3.1 / 3.2 |
| sparc32 (SPARCClassic) | ESP, lance | 72/52/46 / 72/52/40 | 22 / 21 | 364 / 313 | - | 3.1 / 3.1 |
| sparc32 (SPARCbook) | ESP, lance | 74/51/41 / 74/53/41 | 23 / 25 | 303 / 394 | - | 3.1 / 3.1 |
| sparc32 (LX) | ESP, lance | 78/50/39 / 70/48/42 | 20 / 23 | 288 / 271 | - | 3.0 / 3.1 |
| sparc32 (Voyager) | ESP, lance | 119/70/112 / 127/69/107 | 21 / 21 | 271 / 376 | - | 3.1 / 3.3 |
| sparc64 (sun4u) | cmd646, virtio-blk, hme | sda 56/33/16 / 57/35/14, vda 63/42/14 / 46/22/12 | 14 / 13 | 460 / 465 | - | 3.3 / 3.3 |

- SMP runs in parallel on both: the wall time of 2 or 4 loops is about one loop plus 10 to 40 ms
  (MTTCG; the published package gives the same, 2 x 339 / 374 and 4 x 366 / 397 ms on the SS-20).
- The e1000 answers its first frames only after about 1 s (its link comes up late; the first 4 ARP
  requests go unanswered, the fifth is answered); every other NIC within 13 to 34 ms.
- The SS-5, SS-4 and Voyager read about 1.6 times slower than the other sun4m machines with the
  same ESP; not investigated.
- A tier-2 boot of a sparc32 machine is 3.0 to 3.5 s to power-off, 0.2 to 0.6 s more than tier 1;
  without `esp_scsi.esp_bus_reset_settle=0` it was 3 s more.

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
chip there (SS-5, SS-4, SPARCClassic, SPARCbook). The published `pve-qemu-kvm` carries it since
11.1.3-3+wsh9: with that package, wisp boots on the LX and the Voyager, batch and shell; with
11.1.3-3+wsh8 both still stop as above (`Trap 0x07` on the LX, `Trap 0x02` on the Voyager). With an
older package, pass a patched `openbios-sparc32` with `--firmware` (QEMU's `-L`).

OpenBIOS patch 0029 leaves out the SS-5's CS4231 node (`0x6c000000`) where QEMU has no codec: on
the Voyager, the LX, the SPARCClassic and the SPARCbook (NetBSD 9.3 panicked on it on the LX;
`submodules/SPARC.md`, "SPARCstation LX with its own PROM"). wisp's kernels have no sound driver and
never saw the node. With OpenBIOS 0001-0029 given with `--firmware` and QEMU built from the pve-qemu
tree, all eight sparc32 machines passed batch, `--shell`, `--tier2` and `--shell --tier2` on the lab
host (36 boots, 2026-11-21).

## Not done

- Tier 2 has no file system, no IP stack, no CD-ROM and no SCSI on sun4u or the PC (LSI, ESP on
  PCI); SMP is not tested on sun4u (QEMU has one CPU there) or on sun4m machines other than the
  SS-10 and the SS-20.
- Not in the table: the six other sparc32 machines (pass under TCG and boot in CI, see above) and
  the Sun PROMs (`ss5.bin` and the SS-20 PROM boot from a disk, not from `-kernel`).
- CI boots the published package or a pull request's QEMU binaries (see "CI"); a pull request that
  changes `openbios/**` is not checked with its own firmware, and TCI is not run in CI.

## Browser SPARC: wisp in a WebAssembly qemu-system-sparc

The docs site's Browser SPARC page (`/browser-sparc/`, guide "Browser SPARC") runs this kernel's
interactive mode in the browser: `qemu-system-sparc -M SS-5 -m 128` built for WebAssembly, OpenBIOS,
and `console=ttyS0 wisp=shell` with the serial console in an xterm.js terminal. `web/Dockerfile`
builds it, from Debian packages only:

- QEMU 11.1.3 from Debian's source package (`apt-get source qemu`, the release tarball without
  Debian's patches) plus pve-qemu's `wsh/` patches from `submodules/pve-qemu.patch`: all 65 apply
  to upstream with no fuzz. pve-qemu's Proxmox Backup additions need libraries that aren't built for
  Emscripten, so it is not the package's tree. Configured as QEMU's CI wasm64 jobs (`--static
  --cpu=wasm64 --disable-tools --enable-tcg-interpreter`) for `sparc-softmmu` only, without optional
  features.
- Emscripten 6.0.5 from Debian sid (QEMU's CI uses emsdk 4.0.10; trixie's 3.1.69 is older than
  QEMU's wasm64 support was written against). Two differences from the emsdk build: Emscripten 6 no
  longer defines `EMSCRIPTEN`, which QEMU tests (passed in `EMCC_CFLAGS`), and Debian's `+ds` tarball
  has no Python wheels, firmware or device trees (meson, pycotap and qemu.qmp from Debian packages,
  `--disable-install-blobs`, device trees compiled with `dtc`).
- zlib, libffi 3.5.2, pcre2, pixman and glib 2.84 built with `emcc` from Debian source packages
  (`web/scripts/build-deps.sh`, as the emsdk image builds them from upstream tarballs; pcre2 is built
  separately where the emsdk image lets glib's meson fetch it).
- This kernel (tier 1, `TIER2=0 ./build.sh sparc32`), OpenBIOS from the published `pve-qemu-kvm`,
  and xterm.js from Debian's `libjs-xterm`.
- A snapshot: `web/scripts/make-snapshot.py` boots the same machine on a native
  `qemu-system-sparc` built from the same tree, waits for the prompt and migrates it to a file
  (4.8 MB); the page starts with `-incoming file:...` and has a running prompt in under a second,
  where a boot from OpenBIOS takes 162-167 s in Chromium.

Measured in Chromium: `bench` takes 31-47 s of wall time, against 0.37 s under TCG in the published
package; `mandel`'s 20 rows match `tests/mandel.txt`. The guest's clock keeps to the wall clock since
`web/patches/slavio-timer-missed-ticks.patch` (before it, lost timer ticks put it about 3 times
behind; the guide, "How fast"). The page's console is a character device registered in Emscripten's file system
that QEMU opens with `-chardev pipe`; COOP/COEP come from a small service worker of the page's own,
since GitHub Pages can't send headers. Details: the guide.
