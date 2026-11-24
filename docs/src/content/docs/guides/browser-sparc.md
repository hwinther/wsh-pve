---
title: Browser SPARC
description: A SPARCstation 5 emulated in the browser, and wisp's other three machines (sun4u, PC, Arm virt), with QEMU built for WebAssembly and wisp's Linux shell on the serial console
---

[Browser SPARC](/browser-sparc/) runs QEMU in the page: by default a SPARCstation 5
(`qemu-system-sparc`) with OpenBIOS as its firmware runs [wisp](/guides/wisp/), the tiny test
system, with `wisp=shell` on its command line, and wisp's shell answers on the serial console in a
terminal (xterm.js). Type `help`, `info`, `bench`, `mandel` or `banner`; `poweroff` turns the
machine off and Restart starts it again. Nothing is sent anywhere: the page downloads its files and
runs them locally.

The buttons above the terminal pick one of wisp's other machines instead, the same ones its CI
boots (`?arch=` in the address):

| Machine | `?arch=` | QEMU | Firmware |
| --- | --- | --- | --- |
| SPARCstation 5 (the default) | `sparc32` | `qemu-system-sparc -M SS-5`, 128 MB | OpenBIOS |
| Sun Ultra class (sun4u) | `sparc64` | `qemu-system-sparc64 -M sun4u`, 256 MB | OpenBIOS |
| PC | `x86_64` | `qemu-system-x86_64 -M pc`, 128 MB | SeaBIOS |
| Arm virt | `aarch64` | `qemu-system-aarch64 -M virt -cpu cortex-a57`, 256 MB | none: QEMU loads the kernel |

Each machine is a QEMU of its own, so the SS-5's page downloads only the SS-5's files, as before.
The shell is the same on all four (built per architecture); `info` shows which one runs.

The page only runs free software: QEMU, OpenBIOS, SeaBIOS and wisp's Linux kernel and shell. No
Sun PROM, Sun disk or other Sun or Oracle software is part of it, and none ever will be.

## What runs

| File | Size | What it is |
| --- | --- | --- |
| `qemu-system-sparc.wasm`, `.js` | 12.9 MB, 0.4 MB | Upstream QEMU 11.1.3 with this project's patches (pve-qemu's `wsh/` series: all of them apply to upstream as they are) and the page's own `web/patches/` (see "How fast"), built with Emscripten for a wasm64 host. QEMU has no code generator for WebAssembly, so it runs the guest's code with TCI, its TCG interpreter |
| `qemu-system-sparc64.wasm`, `.js` | 18.5 MB, 0.4 MB | The same for sun4u |
| `qemu-system-x86_64.wasm`, `.js` | 36.2 MB, 0.4 MB | The same for the PC (every x86 board and device QEMU builds by default) |
| `qemu-system-aarch64.wasm`, `.js` | 26.5 MB, 0.4 MB | The same for Arm, with the virt board only (QEMU's `minimal` device set: all of Arm's boards made it 52 MB) |
| `openbios-sparc32`, `openbios-sparc64` | 0.4 MB, 1.6 MB | OpenBIOS from the published `pve-qemu-kvm` package, the firmware a PVE sparc VM uses |
| `bios-256k.bin`, `linuxboot_dma.bin`, `kvmvapic.bin` | 0.3 MB | SeaBIOS and the option ROMs QEMU's PC loads (for `-kernel`, and the APIC's), from the same package |
| `wisp-<arch>-kernel` | 1.3-3.1 MB | wisp's tier-1 kernel per architecture: Linux 7.3 `tinyconfig` with a one-program initramfs (PID 1 built with nolibc) |
| `wisp-ss5-128m`, `wisp-sun4u-256m`, `wisp-pc-128m`, `wisp-virt-256m` `.state` and `.log` | 4.8, 14.2, 12.9, 9.8 MB | Each machine saved at wisp's first prompt, and the console output up to there (see below) |
| `machines.json` | 2 KB | The machines' QEMU options, firmware and kernel, read by the page and by the build's snapshot scripts |
| `xterm.js`, `xterm.css` | 0.3 MB | The terminal, from Debian's `libjs-xterm` 5.5.0 |
| `coi-sw.js` | 2 KB | A service worker that makes the page cross-origin isolated (see below) |

The WebAssembly modules and the snapshots compress well: gzip takes the four modules to 4.8, 6.8,
8.3 and 8.3 MB and the snapshots to 1.3-2.5 MB.

On the SS-5, QEMU starts as

```sh
qemu-system-sparc -M SS-5 -bios /fw/openbios-sparc32 -m 128 -nodefaults -display none -monitor none \
  -chardev pipe,id=console,path=/dev/wsh-serial -serial chardev:console \
  -kernel /wisp/wisp-sparc32-kernel -append "console=ttyS0 wisp=shell" \
  -incoming file:/snap/state
```

and the other machines the same way with their own `-M` and firmware from `machines.json` (the
PC with `-L /fw -bios /fw/bios-256k.bin`, Arm with no firmware and `console=ttyAMA0`). The
firmware, the kernel and the snapshot are written into Emscripten's in-memory file system first.

**The snapshot.** Booting under the interpreter takes minutes in a browser (most of it in
OpenBIOS on the SS-5). So the build boots each machine once on a native QEMU, compiled from exactly
the same sources and patches, waits for wisp's prompt and saves the machine with a migration
(`web/scripts/make-snapshot.py`). The page loads that with `-incoming`, shows the saved console
output, and presses Enter for a fresh prompt: the machine runs within a second or two. The "Boot
from the firmware instead" link (`?cold`) skips the snapshot and boots.

The sun4u snapshot needed a fix in QEMU: its sabre host bridge had no migration state at all, so a
resumed machine came back with every interrupt mapping register disabled and the serial console
never answered. pve-qemu's `wsh/0133` migrates the sabre's interrupt state, the sun4u IOMMU, the
PCI configuration space of the ebus and of the sabre's own function, and the sparc64 CPU's SOFTINT
and interrupt vector (it began as a patch of this page's own, and PVE's snapshots and migrations of
sun4u VMs need it as well). The PC and Arm virt machines migrate as they are.

**The serial console.** `/dev/wsh-serial` is a character device the page registers in
Emscripten's file system. The file system lives on the page's main thread and QEMU's threads reach
it through proxied system calls, so the device's handlers run next to the terminal: QEMU's
`write()` goes to xterm.js, `read()` takes what was typed, and `poll()` says whether input is
waiting. QEMU's main loop sleeps in `poll()` and typing wakes it, so an idle machine costs little.
The guest's line discipline does the echo and the line editing (Backspace, Ctrl-U, Ctrl-W, Ctrl-C).

**Cross-origin isolation.** QEMU runs its threads (main loop, vCPU) as Web Workers sharing one
`SharedArrayBuffer`, which browsers allow only in a page served with the
`Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`
headers. GitHub Pages can't send headers, so on the first visit the page registers `coi-sw.js`, a
service worker that adds them to every response within `/browser-sparc/`, and reloads once. A
server that sends the headers itself needs no service worker; the page skips it when it is
already isolated.

**Browsers.** It needs WebAssembly with 64-bit memory (Memory64) and threads. It was tested with
Chromium; current Chrome, Edge and Firefox have both.

## How fast

Measured with headless Chromium 156 on a desktop PC (a 16-vCPU virtual machine), the page served
from `localhost`:

| | SS-5 (sparc32) | sun4u (sparc64) | PC (x86_64) | Arm virt (aarch64) |
| --- | --- | --- | --- | --- |
| From the snapshot to a running prompt, after QEMU starts | 1.8-2.2 s | 1.7 s | 1.6 s | 3.8 s |
| Boot from the firmware (`?cold`) to the prompt | 167 s: OpenBIOS's first line at 16 s, Linux starts at 125 s | 175 s: OpenBIOS at once, Linux at 94 s | 80 s: SeaBIOS (silent on the serial line), Linux at 65 s | 15 s: Linux at 7 s |
| `bench` (4,096 rounds of the CRC loop), wall time | 47 s | 36 s | 39 s | 37-44 s |
| `mandel`, wall time with its output | 9.6-10.9 s | 1.3-1.4 s | 0.6 s | 1.1-1.2 s |
| Guest clock against the wall clock, idle / page thread busy | 0.98-1.00 / 1.00 | 1.00 / 1.00 | 0.95-1.00 / 0.99-1.00 | 0.99-1.00 / 1.00 |

`mandel`'s 20 rows match `e2e/wisp/tests/mandel.txt` on all four, and `bench`'s own time is within
1.5% of the wall clock. The SS-5's `mandel` is slow because the terminal's drawing keeps the
page's thread busy while it prints and the guest then works through the timer ticks it was owed
(below); the other machines print the same rows in about a second. The Arm machine takes longer
from its snapshot to the prompt (the time from the restore to the answer to the first Enter); it
boots fastest, with no firmware. Under TCG in the published package `bench` takes 0.34-0.37 s, so the guest
runs about 100 times slower than QEMU's TCG on a PC, and about 5 times slower than QEMU's
interpreter built natively (`SPARC.md`, "TCI (QEMU's TCG interpreter)"): the interpreter compiled
to WebAssembly with 64-bit memory and Asyncify. Output and input are immediate once the machine is
idle.

**The guest's clock.** It keeps to the wall clock on all four (`info`'s uptime, `bench`'s time).
Builds before `web/patches/slavio-timer-missed-ticks.patch` let the SS-5's fall behind, about 3
times in the first measurements, and almost stop while the page was busy: Linux on the SS-5 counts
the system timer's 100 Hz interrupts to keep time, and QEMU raised the next one only when its main
loop came round. That loop sleeps in `poll()`, whose timeout Emscripten runs as a `setTimeout()` on
the page's main thread, so anything else on that thread (the terminal, the browser) wakes it late,
the timer then runs several periods at once, and all but one of their interrupts were lost. The
patch counts them and raises the interrupt again each time the guest clears it, so a late main loop
now delivers the ticks in a burst; natively nothing changes. Right after such a busy spell the SS-5's
shell takes a few seconds to answer while the guest works through the ticks it was owed.

The other three needed nothing: their Linux keeps time from a clock it reads rather than from
interrupts it counts (sun4u's `%stick`, the PC's TSC, Arm's generic timer), and QEMU computes those
from its virtual clock, which follows the host's, so a late main loop only delays their timer
interrupts.

The build checks it: `clock-check.py` holds up each native QEMU with `SIGSTOP`, and the workflow
runs every machine in headless Chrome with its main thread kept busy and checks `mandel` there too
(`web/scripts/browser-check.mjs`).

## Building it

`web/Dockerfile` builds the files from Debian packages only: Emscripten 6.0.5 from Debian sid,
QEMU's and its libraries' sources from Debian source packages (`apt-get source`: QEMU 11.1.3,
glib 2.84, pixman, libffi 3.5.2, pcre2, zlib, and libfdt from dtc 1.7.2 for the Arm virt machine),
Debian's kernel source and xterm.js, and OpenBIOS and SeaBIOS from this project's apt repository.
QEMU gets pve-qemu's `wsh/` patches and then the page's own in `web/patches/`, each with its reason
at the top (the SS-5 timer fix above); they go into the native QEMU
that makes the snapshots too, since a migration stream only loads into the same device models. The
SS-5, sun4u and PC emulators share one build tree with QEMU's default devices; the Arm one has a
tree of its own with only the virt board. The `Browser SPARC` workflow
(`.github/workflows/browser-sparc.yml`, run by hand) builds them, checks every machine in headless
Chrome, and can publish them as the assets of the `browser-sparc` release, which every Pages deploy
copies next to the page.

To run it locally:

```sh
web/build.sh                       # docker build; copies the files into docs/public/browser-sparc/
cd docs && npm run dev             # then open http://localhost:4321/browser-sparc/
```

Any static server for `docs/public/` works too (`python3 -m http.server`); on `localhost` the
service worker is allowed without HTTPS. `python3 -m unittest discover -s web/tests` checks that
`machines.json`, the build and the page agree.

## Not done yet

- A display: the SS-5's TCX or cg3, sun4u's and the PC's VGA, Arm's ramfb or virtio-gpu on a
  canvas, with the keyboard and mouse (and with it wisp's framebuffer kernel and fbDOOM).
- Sound (the CS4231 and the PC's sound cards through WebAudio) and networking (a WebSocket proxy).
- A smaller PC module: like Arm's, it could leave out the boards and devices the `pc` machine
  doesn't use.
- A local file picker for a user's own PROM or disk images, which never leave the browser.
- Speed: QEMU's WebAssembly code generator (an out-of-tree series, not in QEMU 11.2) instead of
  the interpreter.
