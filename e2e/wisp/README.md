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
| `fbtest` | draw eight colour bars and a white border on `/dev/fb0` and print the mode on serial (framebuffer tier) |
| `soundtest [hz] [ms]` | play a square wave through `/dev/dsp` (framebuffer tier, default 440 Hz for 1000 ms) |
| `mandel` | the Mandelbrot set, 78 x 20 characters, in 4.12 fixed-point 32-bit integer math (sparc32 has no libgcc for 64-bit division, and no floating point is needed) |
| `mandel fb` | draw the set at the native framebuffer resolution and print its iteration checksum on serial |
| `keytest` | print Linux input codes for keyboard presses until Esc or a ten-second timeout (framebuffer tier) |
| `endian` | a small guessing game about the thing this lab tests for: a round's four bytes as they sit in memory, low address first; the right answer is the 32-bit word *this machine's* CPU reads from them, so it depends on the architecture under test (unchanged on sparc, byte-swapped on x86). `endian <hex>` guesses it, `endian` alone shows the round again. Three wrong guesses end the game; a right one scores a point and deals another round |
| `disk [dev ...]` | the tier-2 disk check (see "Tier 2") on each device, by default the ones in `wisp_disk=` (else `sda`); prints its `WISP-DISK` line |
| `net [if]` | the tier-2 network check on the interface (default `wisp_net=`, else `eth0`); prints its `WISP-NET` line |
| `smp` | the compute loop on every CPU at once; prints its `WISP-SMP` line |
| `banner` | the logo with the architecture and kernel release |
| `clear` | clears the screen (`ESC [H ESC [2J`) |
| `poweroff` | powers the machine off, as the batch run does |
| `reboot` | restarts the machine: QEMU exits with `-no-reboot`, or boots wisp again without it. On sun4u Linux restarts through the firmware's `boot` service, which needs openbios-sparc64 with patch 0030 (`openbios/patches/`, in the published pve-qemu-kvm since 11.1.3-4+wsh3); with older firmware the kernel panics with "Reboot failed!" and, with `panic=-1`, tries again for ever |

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
  `endian`, `endian 0`, `poweroff`) and checks the answers: the command list (so the line
  discipline applied the Backspaces), the info lines, both CRCs against the model, every character
  of the 20 Mandelbrot rows against `shell.py`'s integer model (and `tests/mandel.txt`), the
  `endian` game's byte-order line and first round against the model (for the architecture under
  test) and that the deliberately wrong `endian 0` guess gets exactly the model's right answer,
  and the power-off. With
  `--tier2` as well, it boots `kernel-t2` with the machine's first tier-2 profile (two CPUs on the
  PC, the SS-10 and the SS-20) and adds `disk`, `net` and `smp` before `poweroff`. With `--reboot`
  the script ends with `reboot` instead of `poweroff`: the answer `restarting`, no kernel panic
  (`Reboot failed!`), and QEMU's exit code 0 (`-no-reboot` turns the reset into an exit).
- `record.py --arch A --out F.cast [command ...]` records the shell as an asciinema v2 cast in real
  time: the same QEMU command line, each command (default `mandel`) typed at the prompt a
  character at a time, then `poweroff`, with a marker per step (the sparc lab's `CastWriter`).
  The guide's "Mandelbrot on three architectures" embeds `wisp-mandel-ss5.cast`,
  `wisp-mandel-sun4u.cast` and `wisp-mandel-pc.cast`, made with it from the `wisp-test-kit`
  kernels (`--kernel <kit>/<arch>/kernel`) in `ubuntu:24.04` and uploaded to the `media` release by
  hand (not in git): 4.7, 4.6 and 3.7 s from starting QEMU to its exit, the prompt after 2.2, 2.2
  and 1.3 s; `mandel` itself 97, 13 and 6 ms.

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

## Network tier and run mode

`TIER_NET=1` builds `out/<arch>/kernel-net` and saves its resolved `config-net`. It layers
`config/tier-net/common.config` on the tier-2 fragments, reusing their packet sockets and NIC
drivers (LANCE on SS-5, e1000 on pc, HME on sun4u). The fragment adds IPv4, kernel DHCP and Unix
sockets. IPv6, netfilter and wireless are disabled. With `ip=dhcp` the kernel configures the NIC
from QEMU user networking before starting PID 1.

`wisp=run` starts a service supplied as `/test` in an external initramfs. As in `wisp=test`,
arguments after `--` and the environment reach the child. PID 1 prints `WISP-RUN v=1 start`,
reaps children while the service is running, reports its exit code, signal and elapsed
milliseconds, then powers off.

To build and run from the repository root with a local or remote Docker daemon, use one container
for the kernels, QEMU and the Python HTTP client. The SDK containers stream the static executables
into it. Choose an unused container name.

```sh
docker build -f e2e/wisp/Dockerfile -t wispnet-demo:local .
vm=wispnet-http-demo
docker run -d --name "$vm" -e TIER_NET=1 wispnet-demo:local sleep infinity
docker exec "$vm" ./build.sh sparc32 x86_64
for arch in sparc32 x86_64; do
    case "$arch" in
        sparc32) cc=sparc-buildroot-linux-uclibc-gcc ;;
        x86_64)  cc=x86_64-buildroot-linux-uclibc-gcc ;;
    esac
    sdk=ghcr.io/hwinther/wsh-pve/wisp-toolchain-$arch:2025.02.20
    docker run --rm -i "$sdk" sh -ec '"$1" -static -Os -s -x c - -o /tmp/test && cat /tmp/test' sh "$cc" \
        < e2e/wisp/services/httpd/httpd.c | docker exec -i "$vm" sh -c "cat >/tmp/httpd-$arch"
    docker exec "$vm" python3 service.py --arch "$arch" --binary "/tmp/httpd-$arch"
done
```

`service.py` packs the binary as executable `/test` and forwards a free loopback TCP port to guest
port 8080. After the listening marker, it checks two HTTP 200 replies containing the guest's Linux
release, machine and request counters 1 and 2. It then checks the reply to `GET /quit`, PID 1's
successful exit marker and QEMU's exit status.

For sun4u, build the same service with the Debian cross compiler and static glibc. Run these
commands in the same shell:

```sh
docker exec "$vm" ./build.sh sparc64
docker exec "$vm" sh -ec 'apt-get update -qq && apt-get install -y --no-install-recommends libc6-dev-sparc64-cross'
docker exec "$vm" sparc64-linux-gnu-gcc -static -Os -s services/httpd/httpd.c -o /tmp/httpd-sparc64
docker exec "$vm" python3 service.py --arch sparc64 --binary /tmp/httpd-sparc64
```

After the runs, `docker rm -f "$vm"` removes the builder and its temporary build trees.

Measured with Linux 7.3.4 and QEMU 11.1.3 (TCG, `pve-qemu-kvm_11.1.3-3+wsh11`). Sizes are
bytes for kernels built with the same PID 1. Listening time is one wall-clock measurement per
machine, from starting QEMU through DHCP and service startup to the serial readiness marker.

| Target and machine | Service libc | `kernel-t2` | `kernel-net` | Increase | To listening | `uname` machine in both HTTP replies |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| sparc32, SS-5 | uClibc-ng | 3,311,560 | 3,766,312 | 454,752 | 2.730 s | `sparc` |
| x86_64, pc | uClibc-ng | 1,836,032 | 2,024,448 | 188,416 | 4.217 s | `x86_64` |
| sparc64, sun4u | glibc | 4,117,384 | 4,583,432 | 466,048 | 2.694 s | `sparc64` |

All three returned HTTP 200 for both root requests (`request=1`, then `request=2`) and
`bye` for `/quit`. Each printed `WISP-RUN v=1 exit=0 signal=0` and powered off.

## Framebuffer tier

`TIER_FB=1` builds `out/<arch>/kernel-fb` and saves its resolved `config-fb` for sparc32,
sparc64 and x86_64. The build applies the framebuffer fragments directly to tier 2. They enable
fbdev, the framebuffer console and a single 8x8 font. Linux 7.3.4 also needs `CONFIG_PROC_FS`
to register the framebuffer character device. Without it, the driver binds and fbcon displays
text, but fbdev fails to create device 0 with error -19.

At the serial shell, `fbtest` reads the visible mode and stride from `/dev/fb0`, hides the
framebuffer console cursor, then writes a white border around eight vertical RGB bars. On an
8-bit pseudocolour display it installs an eight-entry palette. For 16- and 32-bit truecolour it
uses the driver's channel offsets and lengths. Row writes support SBus framebuffers with
device-specific mmap offsets. The `WISP-FB` line reports the mode and whether the writes succeeded.

At the same prompt, `mandel fb` computes one point per visible pixel using the text command's
4.12 fixed-point recurrence and 32-iteration limit. Points that reach the limit are black.
Escaped points cycle through the seven non-black bar colours. The `sum` in `WISP-FBMANDEL`
is the unsigned 32-bit sum of all per-pixel iteration counts.

`keytest` scans evdev nodes for a keyboard that supports the A key, prints its device name,
then reports each press (including Esc) on serial. SS-5 uses the existing Sun Zilog serial
driver's serio port and `sunkbd`. The pc uses `atkbd` on i8042. In separate boots with `console=tty0`,
typing `poweroff` on the framebuffer VT shut down the pc and SS-5.

The sun4u kernel also includes i8042 and `atkbd`. Two fixes are needed for the keyboard:

- OpenBIOS patch 0035 (`openbios/patches/`) and `-prom-env ps2-mouse?=true`: the EBus `8042`
  node has only its `kb_ps2` child. Linux 7.3.4's `i8042-sparcio.h` needs a `kdmouse` or `mouse`
  child too, and returns `-ENODEV` without it. It also takes the keyboard child's translated
  address as the port base and each child's interrupt. With the option, 0035 adds the child and
  gives the node that layout. The option is off by default: Debian 7's Linux 3.2 panics in
  `sparc_i8042_probe()` once that probe succeeds. `framebuffer.py` sets it on sun4u, and older
  firmware ignores it.
- `linux-patches/0001`, which `build.sh` applies to the unpacked kernel tree: with both children
  found, Linux's sparc OF driver, also named `i8042`, stays registered, and the core driver then
  fails with `Driver 'i8042' is already registered, aborting...`. The patch renames the OF
  driver `i8042-sparc`. It changes no kernel size in the tables here.

With both, the sun4u keytest passes: `serio: i8042 KBD port at 0x1fe02000060,0x1fe02000064`,
then key codes 30, 48, 28 and 1. That run needs `WISP_FIRMWARE` set to a copy of `/usr/share/kvm`
that has the 0035 `openbios-sparc64` (built with `openbios/Dockerfile`). The published
package's firmware doesn't have 0035 yet, and with it the result is still `keytest: keyboard
unavailable`. `framebuffer.py` accepts that one sun4u result, so CI, which boots the published
firmware, passes. It checks the key codes whenever a keyboard is present.

From `e2e/wisp` inside the build image:

```sh
TIER_FB=1 ./build.sh sparc32 sparc64 x86_64
python3 framebuffer.py
```

`framebuffer.py` checks the colour bars and Mandelbrot image pixel by pixel using QMP
screendumps. It checks the iteration sum independently, then sends A, B, Enter and Esc
through QMP and checks for Linux key codes 30, 48, 28 and 1 in order. Both PPMs and the
serial log for each machine/display go in `out/framebuffer/`. Use `--arch sparc32` to run
both SS-5 displays. CI includes the images and logs in the boot artifact's `framebuffer.tar.gz`.

SS-5 uses `FB_SBUS`, `FB_CG3` and `FB_TCX`. Both PCI machines use `DRM_BOCHS` with
`DRM_FBDEV_EMULATION` and QEMU's standard VGA. On pc, a comparison build with
`SYSFB_SIMPLEFB` and `DRM_SIMPLEDRM` also passed the pixel check in the 1024x768 16-bit VESA
mode (`vga=0x317`). With identical base options and PID 1, the compressed Bochs image was
4,096 bytes smaller.

Framebuffer and keyboard measurements before the DOOM data disk, with Linux 7.3.4 and
QEMU 11.1.3 under TCG. Kernel sizes are bytes. Disabling
unused mouse drivers in this tier kept all three framebuffer images smaller than the
colour-bar-only builds.

| Architecture and machine | Display | `kernel-t2` | `kernel-fb` | Increase | Verified screendump |
| --- | --- | ---: | ---: | ---: | --- |
| sparc32, SS-5 | cg3 and tcx | 3,315,656 | 3,397,612 | 81,956 | 1024x768, 8 bpp, both passed |
| sparc64, sun4u | std | 4,125,576 | 4,654,240 | 528,664 | 1280x800, 32 bpp, passed |
| x86_64, pc | std | 1,836,032 | 2,016,256 | 180,224 | 1280x800, 32 bpp, passed |

## Sound on the framebuffer tier

`soundtest [hz] [ms]` accepts 1–22,050 Hz and 1–10,000 ms. It sets the PCM and available
master mixer levels, writes signed 16-bit little-endian stereo at 44,100 frames/s and drains
the device before reporting success. An integer phase accumulator sets the pitch. PID 1 writes
the two sample bytes explicitly on both SPARC and x86.

The sound drivers live in `kernel-fb` with the display hardware used by games. ALSA's OSS
PCM and mixer interfaces keep setup to a few ioctls and allow a game to stream samples with
`write`. Both codecs accept the selected format directly, so the kernel omits the OSS
conversion plugins. AC97 uses a single PCI controller driver on pc and sun4u. Linux 7.3's
ES1370 driver would also pull in raw MIDI.

From this directory, run `python3 sound.py` after a `TIER_FB=1` build. Select one machine
with `--arch x86_64`, `--arch sparc32` or `--arch sparc64`. The runner attaches
`-audiodev wav,id=snd0,path=<capture.wav>` and the machine options below, waits for the
serial shell, sends `soundtest 440 1000`, then powers off. It checks the serial result and
QEMU exit status. On each WAV channel it measures the first tone (900–1100 ms), ending at a
silence longer than 10 ms. It reports up to 50 ms of trailing samples separately. The tone check
requires at least 90% of that span above the silence threshold, and measures the interval
between rising crossings (440 Hz ±3%). QEMU 11 can leave the RIFF and data lengths zero.
The reader fills them in memory. The original WAVs and serial logs are in `out/sound/`
locally and in the CI artifact's `sound/` directory.

Paired Linux 7.3.4 builds and captures with published pve-qemu-kvm 11.1.3-4+wsh10:

| Machine | Linux driver | QEMU option | `kernel-fb` before → after (bytes) | Growth | Captured tone |
| --- | --- | --- | ---: | ---: | --- |
| pc (x86_64) | `SND_INTEL8X0` | `-device AC97,audiodev=snd0` | 2,028,544 → 2,098,176 | +69,632 | 440.005 Hz, 1000 ms |
| sun4u (sparc64) | `SND_INTEL8X0` | `-device AC97,audiodev=snd0` | 4,687,392 → 4,918,296 | +230,904 | 440.005 Hz, 1000 ms |
| SS-5 (sparc32) | `SND_SUN_CS4231` | `-machine audiodev=snd0` | 3,438,612 → 3,565,840 | +127,228 | 440.074 Hz, 46 ms (failed) |

The pc and sun4u reported:

```text
WISP-SOUND v=1 dev=/dev/dsp rate=44100 fmt=s16le ch=2 hz=440 ms=1000 frames=44100 ok=1
```

On the SS-5, playback needs two fixes, OpenBIOS 0034 and pve-qemu `wsh/0124`, and the CI step
leaves the SS-5 out until a published package has both. On `11.1.3-4+wsh10` and `+wsh11`, Linux
7.3.4 registers the Sun CS4231 and the first 8192-byte buffer reaches the WAV. Playback then
stops with `WISP-SOUND v=1 ok=0 errno=5`, and `cs4231` counts no interrupts in
`/proc/interrupts`:

- The packaged OpenBIOS gives the codec `intr 9`. Linux reads values below `0x20` as
  software interrupts, so SBus level 5 stays masked. OpenBIOS patch 0034
  (`openbios/patches/`) gives the codec `0x39`, as the SS-5's own PROM does. The interrupt
  then arrives.
- Linux's SBus handler ignores the interrupt unless the codec's status register has its INT
  bit. QEMU's CS4231 didn't set that bit, so the APC interrupt was never cleared: with 0034
  alone, the interrupt repeats until QEMU stops with `Trap 0x02 (Illegal Instruction) while
  interrupts disabled`. pve-qemu `wsh/0124` sets INT, and PI in the codec's I24, with the APC's
  playback interrupts; Linux clears them by writing I24.

With both, in a lab build, the unchanged `kernel-fb` reports `ok=1`, with 23 `cs4231` interrupts,
and the tone in the WAV is 440.005 Hz for 1000.00 ms on both channels. The original
whole-capture measurement gave 1039–1042 ms at 424 Hz. The WAV contains about 150 frames
of old ring-buffer samples starting 36 ms after the tone. Linux stops the DMA when its last period has played, and by then QEMU's
APC has taken up to 50 ms of the next period, which it plays out after the stop (pve-qemu 0032).
See `submodules/SPARC.md`, "Audio".

## Freedoom framebuffer timedemo

`doom.py` builds a raw squashfs disk with `mksquashfs -comp xz` (squashfs-tools).
It contains the static `fbdoom` executable, `freedoom1.wad` and `demo.rsp`. QEMU
attaches it through ESP SCSI on SS-5 and IDE on pc and sun4u, with snapshot writes.
The framebuffer tier inherits these disk drivers from tier 2 and adds the squashfs
reader with XZ compression. Tier 2's raw disk checks need no filesystem.

In either `wisp=test` or `wisp=run`, `wisp_data=/dev/sda` asks PID 1 to wait up to
ten seconds for the device, then mount it read-only at `/data`. PID 1 reports
`WISP-DATA v=1 dev=/dev/sda fs=squashfs mounted=1` on serial. A mount failure
reports `mounted=0 errno=N` and powers off before starting the payload.
`wisp_run=/data/fbdoom` selects the executable directly, so DOOM needs no external
initramfs or launcher. The default executable is still `/test` for external initramfs
callers. DOOM passes `-- @/data/demo.rsp` to keep the OpenBIOS arguments short.
The default response file selects `-iwad /data/freedoom1.wad -nosound -timedemo demo1`.
Add `--sound` to the same `doom.py` command to attach the machine's audio device,
select `-nomusic` and save a WAV alongside the timedemo log and screendump.
The check requires at least three bursts with 20 ms of loud audio separated by 30 ms of
quiet audio. It measures stereo RMS in 10 ms windows and compares capture duration
to measured playback time. Both modes check the same 7,117 gametics.

Paired 1× runs with Linux 7.3.4 and published pve-qemu-kvm 11.1.3-3+wsh11 under TCG:

| Machine | FPS without sound | FPS with effects | Captured bursts | WAV duration |
| --- | ---: | ---: | ---: | ---: |
| pc | 252.63 | 229.16 | 5 | 29.90 s |
| sun4u | 58.01 | 55.21 | 51 | 127.62 s |

fbDOOM centers the largest integer multiple of 320×200 that fits the screen. It
expands each row once and copies it vertically, using palette indices on cg3/TCX
and native pixels on bochs. The engine uses its default 6 MiB zone. Interactive
boots use the VT keyboard on pc and SS-5. Timedemos skip keyboard setup.
The game code is GPL-2.0 and Freedoom is BSD-3-Clause. [Archive pins and patches](doom/README.md)

Framebuffer kernel sizes with Linux 7.3.4, including PID 1, in bytes:

| Architecture | Before | With data disk | Change |
| --- | ---: | ---: | ---: |
| sparc32 | 3,413,996 | 3,438,612 | +24,616 |
| sparc64 | 4,654,240 | 4,687,392 | +33,152 |
| x86_64 | 2,016,256 | 2,028,544 | +12,288 |

i386 has no framebuffer tier. The SS-5 external initramfs previously needed `CONFIG_RD_XZ`
to fit the compressed payload into the direct-boot window. The data disk removes that
requirement. With squashfs XZ enabled, the SS-5 kernel measured 3,438,612 bytes both
with and without `CONFIG_RD_XZ`. The framebuffer tier now inherits the common disabled setting.

Linux 7.3.4 and QEMU 11.1.3 under TCG, one paired run per display. Each pair used the
same CPU affinity for both runs. The four pairs ran concurrently while the size-budget
build used a separate CPU set. Each cell gives the original initramfs run at 1× followed
by the squashfs run at the indicated scale. All eight runs completed 7,117 gametics.
FPS is `35 × gametics / realtics`. Wall time runs from starting QEMU through power-off.
Boot-to-start ends at PID 1's `WISP-RUN v=1 start`, before fbDOOM opens the WAD.

| Machine and display | New frame | Realtics | FPS | Wall (s) | Boot-to-start (s) | Screendump |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| SS-5 cg3 | 3×, 960×600 | 1112 → 3049 | 224.01 → 81.70 | 39.43 → 99.20 | 7.16 → 8.52 | `SS-5-cg3.ppm` |
| SS-5 tcx | 3×, 960×600 | 1139 → 3107 | 218.70 → 80.17 | 40.21 → 100.05 | 7.18 → 7.71 | `SS-5-tcx.ppm` |
| pc std | 4×, 1280×800 | 1125 → 6467 | 221.42 → 38.52 | 34.59 → 190.79 | 2.29 → 2.63 | `pc-std.ppm` |
| sun4u std | 4×, 1280×800 | 8151 → 16034 | 30.56 → 15.54 | 237.44 → 464.06 | 4.06 → 3.70 | `sun4u-std.ppm` |

The comparison saved PPMs and matching serial logs under `out/doom/before/` and
`out/doom/after/`. Every data-disk run printed `WISP-DATA v=1 dev=/dev/sda fs=squashfs mounted=1`.

The 28,482-byte `DEMO1` lump has a 13-byte header, 7,117 four-byte commands and one end
marker. Each boot checks that independent count, the reported FPS, the successful data mount,
centered integer-scaled pixels and game colours in a QMP capture during playback, the
successful child exit on serial and QEMU's exit. A matching count
checks playback length across byte orders. `doom.py --scale` sets fbDOOM's `-scaling`: 1 by default and in CI (the timedemo's gametics don't depend on it, and 1x keeps the run short under TCG), 0 for the largest integer factor that fits, as when playing (3x on cg3/TCX, 4x on bochs). Wisp boot CI runs the complete demo on pc and
SS-5 cg3 on relevant PRs, with sound effects enabled on pc. It caches
both verified archives and writes serial logs, PPMs, the pc WAV and timing report under `RUNNER_TEMP`.

To reproduce on a Docker daemon, run the following from the repository root with a POSIX
shell, Python 3.11+ and unused container names. Set `DOCKER_HOST` to the lab daemon before
starting. Tar streams carry the inputs and evidence across the Docker connection.

```sh
set -eu
w=e2e/wisp
inputs=$w/out/doom-inputs
vm=wispdoom-run
python3 "$w/doom/fetch.py" "$inputs"
set -- "$inputs"/fbDOOM-*.tar.gz
archive=$1
docker build -f "$w/Dockerfile" -t wispdoom-runner .
docker run -d --name "$vm" wispdoom-runner sleep infinity
docker exec "$vm" sh -ec 'apt-get update -qq && apt-get install -y patch libc6-dev-sparc64-cross'
docker exec -e TIER_FB=1 -e TIER2=0 "$vm" sh build.sh sparc32 x86_64 sparc64
tar -C "$inputs" -cf - freedoom1.wad | docker exec -i "$vm" tar -C /tmp -xf -
for arch in sparc32 x86_64 sparc64; do
    sdk=$vm
    if [ "$arch" != sparc64 ]; then
        sdk=wispdoom-build-$arch
        docker run -d --name "$sdk" "ghcr.io/hwinther/wsh-pve/wisp-toolchain-$arch:2025.02.20" sleep infinity
        docker exec "$sdk" sh -ec 'apt-get update -qq && apt-get install -y make patch'
    fi
    tar -C "$w" -cf - doom | docker exec -i "$sdk" tar -C /tmp -xf -
    docker exec -i "$sdk" sh -c 'cat >/tmp/src.tgz' < "$archive"
    docker exec "$sdk" sh /tmp/doom/build.sh "$arch" /tmp/src.tgz "/tmp/fbdoom-$arch"
    if [ "$sdk" != "$vm" ]; then
        docker exec "$sdk" tar -C /tmp -cf - "fbdoom-$arch" | docker exec -i "$vm" tar -C /tmp -xf -
        docker rm -f "$sdk" >/dev/null
    fi
    docker exec "$vm" python3 doom.py --arch "$arch" --binary "/tmp/fbdoom-$arch" --wad /tmp/freedoom1.wad
done
mkdir -p "$w/out/doom"
docker exec "$vm" tar -C /wisp/out/doom -cf - . | tar -C "$w/out/doom" -xf -
docker rm -f "$vm"
docker image rm wispdoom-runner
```

## Updating the size budget

In the wisp build environment, run `TIER_NET=1 TIER_FB=1 ./build.sh all` with tier 2 enabled (the
default). Each `out/<arch>/sizes` gives the kernel, tier-2 kernel, network kernel and init
sizes in bytes, plus `kernel_fb_bytes` on the three framebuffer architectures. Run
`python3 size_budget.py` from this directory to check all four architectures.
Growth above 5% fails the boot workflow. A reduction greater than 5% prints a notice.
After reviewing an intentional change, copy the new measured byte count for each affected
field into `size-budget.json` and rerun the check.

## Test mode: the wisp-test action

`wisp=test` on the kernel command line makes PID 1 run `/test` instead of the batch run: a program
that QEMU's `-initrd` adds as a second, uncompressed initramfs, which the kernel unpacks next to
the built-in one (`CONFIG_BLK_DEV_INITRD`, already set; the kernels are the same tier-1 kernels).
PID 1 prints the banner, starts `/test` with its own arguments (what follows `--` on the kernel
command line) and environment, waits for it (reaping anything else it leaves behind), prints one
line and powers off:

```
WISP-TEST v=1 exit=1 signal=0 ms=88
WISP-TEST v=1 exit=-1 signal=10 ms=72
```

`exit` is the exit code (`-1` when a signal killed it), `signal` the signal (sparc numbers:
`SIGBUS` is 10) and `ms` the time from `fork` to `waitpid`. If `/test` can't be started, a
`WISP-TEST-ERROR exec /test failed: errno N` line comes first (2: missing or dynamic, 8: a format
the kernel refuses) and `exit` is 127.

`.github/actions/wisp-test` is a GitHub Action built on it, for other projects' endianness and
alignment bugs: it builds a C program against nolibc for sparc32 (V8, `SS-5`), sparc64 or x86_64,
packs it as `/test`, boots it under QEMU from Ubuntu's packages and passes or fails on the exit
status (its README has the inputs and the limits). It needs no kernel build: it downloads a kit
(`kit.sh`: the tier-1 and network kernels for each action architecture and the UAPI and nolibc
headers from `out/<arch>/sysroot.tar.xz`) from the `wisp-test-kit` release, which
`.github/workflows/wisp-test-action.yml` publishes when dispatched with `publish`. That workflow
also tests the action on pull requests that touch `e2e/wisp/` or the action, with the kit built in
the run: an endianness bug (`examples/endian.c`, exit code 1 on sparc) and an alignment bug
(`examples/align.c`, `SIGBUS` on sparc) that pass on x86_64, their fixes (`-DFIXED`) that pass
everywhere, the arguments on sparc (`tests/args.c`) and 64-bit division on all three
(`tests/div64.c`).

Measured 2026-11-22 on the lab host (load 8 to 10 on 14 threads) in a fresh `ubuntu:24.04`
container limited to 2 CPUs, with the action's script and a locally built kit: all 11 cases of the
self-test gave the result they should.

| case | want | result | QEMU start to exit s | whole script s |
| --- | --- | --- | --- | --- |
| endian bug sparc32 (first run: `apt-get install`) | fail | exit code 1 | 2.2 | 16.1 |
| endian bug x86_64 (installs `qemu-system-x86`) | pass | exit code 0 | 1.8 | 11.7 |
| endian fixed sparc32 | pass | exit code 0 | 2.3 | 3.0 |
| endian bug sparc64 | fail | exit code 1 | 2.4 | 3.1 |
| endian fixed sparc64 | pass | exit code 0 | 2.3 | 3.0 |
| align bug x86_64 | pass | exit code 0 | 1.6 | 2.3 |
| align bug sparc32 | fail | `SIGBUS` | 2.6 | 3.5 |
| align bug sparc64 | fail | `SIGBUS` | 2.3 | 3.0 |
| align fixed sparc32 | pass | exit code 0 | 2.3 | 3.0 |
| args sparc32 | pass | exit code 0 | 2.2 | 2.9 |
| args sparc64 | pass | exit code 0 | 2.6 | 3.3 |

Earlier passes took 1.4 to 3.7 s per boot (load 8 to 11) and 13 to 32 s for the first run. The
sparc cases also pass in `ubuntu:26.04` (QEMU 10.2.1, gcc 15) as in 24.04 (QEMU 8.2.2, gcc 13).
The kit's download (`kit-url`) was not tested, as the release doesn't exist yet.

64-bit division on sparc32: the action links `libgcc-sparc32.c` there, its own `__udivdi3`,
`__divdi3`, `__umoddi3`, `__moddi3`, `__udivmoddi4` and `__divmoddi4` (shift-subtract long
division, with the V8 `udiv` when both operands fit in 32 bits; division by zero traps with
`SIGFPE` as on the other two). Checked 2026-11-22 in `ubuntu:24.04` (2 CPUs) on the lab host
with the published kit: `tests/div64.c` (12 unsigned and signed cases: negative operands,
`INT64_MIN`, divisors above 32 bits) passes on sparc32, sparc64 and x86_64, 1.5 to 2.2 s per
boot, and the 11 other cases give their results as before.

Found on the way:

- A program built with nolibc on sparc needs the same `_start` fix as PID 1: the action renames
  nolibc's (`-D_start=wisp_nolibc_start`) and links its own (`start-sparc.c`).
- gcc reads a `uint32_t` through a misaligned pointer byte by byte on sparc by itself when it can
  see the misalignment (a pointer into an aligned array at a constant odd offset), so the
  alignment example hides the offset in a `volatile`; otherwise the bug doesn't show.
- The first CI run failed both x86_64 cases with `SIGILL` at the first number `printf` formatted:
  the `ubuntu-latest` runner (Ubuntu 26.04) installs the amd64v3 variant of the packages, and that
  gcc defaults to `-march=x86-64-v3` (`with-arch-64=x86-64-v3`), so the program had BMI2
  instructions (`shlx`) that QEMU's default `qemu64` CPU doesn't have. Reproduced in `ubuntu:26.04`
  with `APT::Architecture-Variants "amd64v3"`; the action now builds x86_64 with `-march=x86-64`
  (`-cpu max` in QEMU passed as well, but a fixed baseline doesn't depend on the runner).
- Ubuntu's 32-bit sparc libgcc and glibc (`lib32gcc-*-dev-sparc64-cross`,
  `libc6-dev-sparc-sparc64-cross`) are V8+ (`EM_SPARC32PLUS`, V9 instructions such as `bne %icc`
  and `return`), even with `-mcpu=v8`, and the sparc32 kernel refuses such a binary (`ENOEXEC`).
  So nolibc on sparc32 stays without libgcc; the action brings the 64-bit division helpers
  itself (`libgcc-sparc32.c`). A static glibc
  binary for sparc64 (`libc6-dev-sparc64-cross`) runs in the tier-1 kernel.

## A libc toolchain (uClibc-ng)

The toolchain in `e2e/wisp/toolchain/` targets static user programs on sparc32 (SPARC V8,
`SS-5`) and x86_64. PID 1 uses the kernel's nolibc. Debian's packaged 32-bit SPARC glibc and
libgcc target V8+ even with `-mcpu=v8`. Linking against those libraries produces an
`EM_SPARC32PLUS` executable that wisp's sparc32 kernel rejects.

The Dockerfile pins Buildroot LTS 2025.02.20 and the SHA-256 published in
`buildroot-2025.02.20.tar.gz.sign`. Both defconfigs use Buildroot's internal GCC and uClibc-ng.
This release's `package/uclibc/Config.in` enables uClibc-ng for `BR2_sparc` and `BR2_x86_64`
and omits `BR2_sparc64`. For sparc64, the action README documents the packaged static glibc route.

From the repository root, build one SDK image at a time:

```sh
sh e2e/wisp/toolchain/build.sh sparc32 2025.02.20
sh e2e/wisp/toolchain/build.sh x86_64 2025.02.20
```

`make sdk` packages the compiler and sysroot. The Dockerfile relocates them to
`/opt/wisp-toolchain/<arch>` and puts the compiler on the final image's `PATH`. To export the SDK
as a tarball, run `sh e2e/wisp/toolchain/build.sh <arch> --export DIR`. The manual
`publish-wisp-toolchain.yml` workflow builds and publishes a selected image to GHCR. By default it also uploads
`wisp-toolchain-<arch>.tar.xz` and its `.sha256` file to the GitHub `wisp-toolchain` release.
The wisp-test action downloads this SDK for `libc: uclibc` source builds without Docker.

Both static `hello` binaries printed `WISP-HELLO v=1 checksum=0xed3258f703d97351 status=ok`
under the published `wisp-test-kit` kernel 7.3.4. Each exited with code 0 and signal 0.

| Target | Machine | SDK image build time | Unstripped hello size | ELF |
| --- | --- | ---: | ---: | --- |
| sparc32 | SS-5 | 13 min 44 s | 84,484 bytes | 32-bit MSB SPARC (V8, `EM_SPARC`) |
| x86_64 | pc | 15 min 52 s | 51,544 bytes | 64-bit LSB x86-64 |

See [the hello smoke test](toolchain/hello/README.md) for the compile and boot commands.

## Build

```sh
docker build -f e2e/wisp/Dockerfile -t wsh-wisp .
docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./build.sh all     # or x86_64 i386 sparc32 sparc64
```

The image is Debian 13 with Debian's cross compilers (`gcc-sparc64-linux-gnu`, `gcc-i686-linux-gnu`),
`linux-source-7.3` from trixie-backports (nolibc supports sparc since 6.16; trixie itself has 6.12)
and the published `pve-qemu-kvm`. `build.sh` unpacks the kernel into `build/`, applies each
`linux-patches/*.patch` once (listed in `build/linux/.wisp-patches`; a `KSRC` tree is used as it
is) and per architecture:

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

Output in `out/<arch>/`: `kernel`, `kernel-t2`, `init`, `config`, `config-t2`, `sizes` and
`sysroot.tar.xz` (the headers `init` was built with, for the wisp-test kit). The tier-1
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
the four architectures once more and drives the interactive shell (about 2 to 3 s each), and
`--shell --reboot` the four architectures once more with `reboot` at the end (on sparc64 the
restart goes through the firmware: openbios-sparc64 patch 0030, in the published package since
11.1.3-4+wsh3). Then tier 2: `run.py --tier2` on the four architectures and the seven other sparc32 machines (21 boots: every
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
- `.github/workflows/wisp-test-action.yml` tests the wisp-test action (see "Test mode") with tier-1
  kernels from the same cache, restored only; on a miss it builds the three it needs itself.
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
