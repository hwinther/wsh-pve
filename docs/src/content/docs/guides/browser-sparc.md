---
title: Browser SPARC
description: A SPARCstation 5 emulated in the browser, with QEMU built for WebAssembly, OpenBIOS and wisp's Linux shell on the serial console
---

[Browser SPARC](/browser-sparc/) runs `qemu-system-sparc` in the page: a SPARCstation 5 with
OpenBIOS as its firmware runs [wisp](/guides/wisp/), the tiny test system, with `wisp=shell` on
its command line, and wisp's shell answers on the serial console in a terminal (xterm.js). Type
`help`, `info`, `bench`, `mandel` or `banner`; `poweroff` turns the machine off and Restart starts
it again. Nothing is sent anywhere: the page downloads its files and runs them locally.

The page only runs free software: QEMU, OpenBIOS and wisp's Linux kernel and shell. No Sun PROM,
Sun disk or other Sun or Oracle software is part of it, and none ever will be.

## What runs

| File | Size | What it is |
| --- | --- | --- |
| `qemu-system-sparc.wasm`, `.js` | 12.8 MB, 0.4 MB | Upstream QEMU 11.1.3 with this project's sparc patches (pve-qemu's `wsh/` series: all of them apply to upstream as they are) and the page's own `web/patches/` (the timer fix under "How fast"), built with Emscripten for a wasm64 host. QEMU has no code generator for WebAssembly, so it runs the guest's code with TCI, its TCG interpreter |
| `openbios-sparc32` | 0.4 MB | OpenBIOS from the published `pve-qemu-kvm` package, the firmware a PVE sparc32 VM uses |
| `wisp-sparc32-kernel` | 2.4 MB | wisp's tier-1 sparc32 kernel: Linux 7.3 `tinyconfig` with a one-program initramfs (PID 1 built with nolibc) |
| `wisp-ss5-128m.state`, `.log` | 4.8 MB | The machine saved at wisp's first prompt, and the console output up to there (see below) |
| `xterm.js`, `xterm.css` | 0.3 MB | The terminal, from Debian's `libjs-xterm` 5.5.0 |
| `coi-sw.js` | 2 KB | A service worker that makes the page cross-origin isolated (see below) |

QEMU starts as

```sh
qemu-system-sparc -M SS-5 -m 128 -nodefaults -display none -monitor none \
  -chardev pipe,id=console,path=/dev/wsh-serial -serial chardev:console \
  -bios /fw/openbios-sparc32 -kernel /wisp/kernel -append "console=ttyS0 wisp=shell" \
  -incoming file:/snap/state
```

with the firmware, the kernel and the snapshot written into Emscripten's in-memory file system
first.

**The snapshot.** Booting under the interpreter takes about 2.5 minutes in a browser, most of it
in OpenBIOS. So the build boots the same machine once on a native `qemu-system-sparc`, compiled
from exactly the same sources and patches, waits for wisp's prompt and saves the machine with a
migration (`web/scripts/make-snapshot.py`). The page loads that with `-incoming`, shows the saved
console output, and presses Enter for a fresh prompt: the machine runs within a second. The
"Boot from OpenBIOS instead" link (`?cold`) skips the snapshot and boots from the firmware.

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

Measured with Chromium on a desktop PC, the page served from `localhost`:

| | Time |
| --- | --- |
| From the snapshot to a running prompt | 0.8 s after QEMU starts |
| Boot from OpenBIOS (`?cold`) to the prompt | 162-167 s: OpenBIOS's first line at 18 s, its SBus probe 69-105 s, Linux starts at 127 s |
| `bench` (4,096 rounds of the CRC loop) | 31-47 s, and the guest reports the same within 2% (11.1 s before the timer fix below); the published package under TCG 0.37 s |
| `mandel` | 2-9 s with its output, and the guest reports within 5% of it (0.27-0.53 s before the timer fix: the terminal's drawing kept the page's thread busy) |

So the guest runs about 100 times slower than QEMU's TCG on a PC, and about 5 times slower than
QEMU's interpreter built natively (OpenBIOS from reset to `bootpath:` took 26 s there, `SPARC.md`,
"TCI (QEMU's TCG interpreter)"): the interpreter compiled to WebAssembly with 64-bit memory and
Asyncify. Output and input are immediate once the machine is idle.

**The guest's clock.** It keeps to the wall clock (`info`'s uptime, `bench`'s time). Builds before
`web/patches/slavio-timer-missed-ticks.patch` let it fall behind, about 3 times in the first
measurements, and almost stop while the page was busy: Linux on the SS-5 counts the system
timer's 100 Hz interrupts to keep time, and QEMU raised the next one only when its main loop came
round. That loop sleeps in `poll()`, whose timeout Emscripten runs as a `setTimeout()` on the
page's main thread, so anything else on that thread (the terminal, the browser) wakes it late, the
timer then runs several periods at once, and all but one of their interrupts were lost. The patch
counts them and raises the interrupt again each time the guest clears it, so a late main loop now
delivers the ticks in a burst; natively nothing changes. The build checks it: `clock-check.py`
holds up a native QEMU with `SIGSTOP`, and the workflow runs the page in headless Chrome with its
main thread kept busy (`web/scripts/browser-clock-check.mjs`). Right after such a busy spell the
shell takes a few seconds to answer while the guest works through the ticks it was owed.

## Building it

`web/Dockerfile` builds the files from Debian packages only: Emscripten 6.0.5 from Debian sid,
QEMU's and its libraries' sources from Debian source packages (`apt-get source`: QEMU 11.1.3,
glib 2.84, pixman, libffi 3.5.2, pcre2, zlib), Debian's kernel source and xterm.js, and OpenBIOS
from this project's apt repository. QEMU gets pve-qemu's `wsh/` patches and then the page's own
in `web/patches/`, each with its reason at the top (so far one: the timer fix above); they go into
the native QEMU that makes the snapshot too, since a migration stream only loads into the same
device models. The `Browser SPARC` workflow (`.github/workflows/browser-sparc.yml`, run by hand)
builds them, checks the guest's clock in headless Chrome, and can publish them as the assets of
the `browser-sparc` release, which every Pages deploy copies next to the page.

To run it locally:

```sh
web/build.sh                       # docker build; copies the files into docs/public/browser-sparc/
cd docs && npm run dev             # then open http://localhost:4321/browser-sparc/
```

Any static server for `docs/public/` works too (`python3 -m http.server`); on `localhost` the
service worker is allowed without HTTPS.

## Not done yet

- A display: the SS-5's TCX or cg3 on a canvas, with the Sun keyboard and mouse.
- Sound (the CS4231 through WebAudio) and networking (a WebSocket proxy).
- A local file picker for a user's own PROM or disk images, which never leave the browser.
- Speed: QEMU's WebAssembly code generator (an out-of-tree series, not in QEMU 11.2) instead of
  the interpreter.
