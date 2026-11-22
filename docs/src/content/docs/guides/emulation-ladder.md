---
title: The emulation ladder
description: The same compute loop measured native, under KVM, under TCG, under TCI, and under TCI inside WebAssembly in a browser
---

Between a guest's instructions and the host's CPU there can be nothing at all, a hardware-assisted
virtual machine, a dynamic translator, a bytecode interpreter, or that interpreter running inside a
browser's own virtual machine. The emulation ladder is one piece of work, [wisp](/guides/wisp/)'s
fixed compute loop, measured at each of those rungs — a demo idea from `ROADMAP.md` ("Later", "Demo
ideas", item 3), built from numbers the lab already has plus two rungs it doesn't yet.

| Rung | What runs | Where | Status |
| --- | --- | --- | --- |
| 1. Native | wisp's loop as a plain process, no QEMU | the host's own x86_64 CPU | open |
| 2. KVM | the same loop in wisp's `pc` kernel, `-accel kvm` | an x86_64 guest on an x86_64 host | open |
| 3. TCG | the same loop, `-accel tcg` | an x86_64 **or** a cross-architecture (sparc32/sparc64) guest | measured |
| 4. TCI | the same loop, QEMU built `--enable-tcg-interpreter` | any guest, same host | measured |
| 5. TCI in Wasm | the same loop, QEMU compiled with Emscripten | a sparc32 guest, in a browser tab | measured |
| 6. Nested | a sparc32 guest's loop, under TCG, inside an x86_64 guest, under TCI, in a browser | sparc in x86 in Wasm | open |

Rungs 3-5 remove something a real CPU does for every other rung: rung 3 (on a cross-architecture
guest) replaces the host's instruction set with a translated one; rung 4 replaces the translator's
compiled output with a bytecode loop; rung 5 moves that whole interpreter into a browser's own
JavaScript/Wasm engine. Rung 6 runs rung 3's translator *underneath* rung 5,
so the "fast" step (TCG, normally close to native) sits on top of the slowest one (TCI in Wasm) —
the sparc guest's translated code is itself interpreted, one more time, before anything executes.

## Why rungs 1 and 2 are different from 3-5

[Architecture](/reference/architecture/) explains the split this project lives by: an x86_64 guest on
an x86_64 host is the one case QEMU can run with KVM, because guest and host share an instruction
set and the CPU's own virtualization extensions do the heavy lifting (rung 2, close to rung 1).
Every sparc32, sparc64 and aarch64 guest here runs on an x86_64 host, so it is always rung 3 or
below — KVM was never an option for them, and rungs 1-2 only make sense measured on x86_64, with
wisp's `pc` machine instead of `SS-5` or `sun4u`.

## What the lab already measured (rungs 3-4)

[wisp, the tiny test system](/guides/wisp/#tcg-against-tci), runs the identical compute loop and
checksum on x86_64, i386, sparc32 and sparc64, under both backends from the same QEMU build.
Measured 2026-11-21 on the lab host:

| Architecture | Loop time, TCG | Loop time, TCI | TCI/TCG |
| --- | --- | --- | --- |
| x86_64 (`pc`) | 372-400 ms | 7783-8192 ms | ~20x |
| sparc32 (`SS-5`) | 352-392 ms | 6282-6846 ms | ~17x |
| sparc64 (`sun4u`) | 366-401 ms | 6196-6779 ms | ~17x |

A whole boot (QEMU start to power-off, OpenBIOS or SeaBIOS included) is 7-14x slower under TCI, less
than the loop alone, because most of a boot is firmware and device probes, not the compute loop
itself. [TCI (QEMU's TCG interpreter)](https://github.com/hwinther/wsh-pve/blob/main/submodules/SPARC.md)
covers the same pair of backends against a full benchmark disk (Dhrystone, Whetstone, nbench,
lmbench, Towers of Hanoi) on Solaris 2.6 and NetBSD 9.3: compiled code there runs 8-35x slower under
TCI (Dhrystone 2.1: 946 against 48.8 VAX MIPS, 19.4x), boots 1.6-6x longer, and an idle guest that
halts its CPU costs the same either way — it is the running work that TCI costs, not the waiting.

## What the lab already measured (rung 5)

[Browser SPARC](/guides/browser-sparc/#how-fast) is rung 5 end to end: the same `SS-5`/OpenBIOS
machine, with QEMU's own Emscripten build (wasm64, TCI is the only backend a WebAssembly host has),
running in a browser tab. `bench` (4,096 rounds of the same kind of compute loop) took 31-47
seconds there against 0.37 seconds for the published package's native TCG — about 100x — and about
5x slower than QEMU's TCI built natively (26 seconds, OpenBIOS reset to `bootpath:`), the added cost
of the interpreter itself running inside WebAssembly with 64-bit memory and Asyncify.

## What's still open (rungs 1, 2 and 6)

- **Native.** wisp's PID 1 (`e2e/wisp/init.c`) is a static nolibc binary with no guest OS underneath
  the loop; running the x86_64 build directly as a host process, timing only the loop, needs no new
  code, only a wrapper script and a place in the table above.
- **KVM.** wisp's `pc` machine already boots under TCG in the table above; the same kernel and
  initramfs under `-accel kvm` would give the fourth point on the x86_64 line. One wrinkle: the lab
  host these numbers were measured on is itself a VM (14 vCPUs, on an i9-9900K), so this rung needs
  nested virtualization turned on for that VM, not just a KVM module on bare metal.
- **Nested.** `browser-sparc`'s Wasm build is `qemu-system-sparc` only; nesting means building
  `qemu-system-x86_64` for Emscripten instead, booting a small x86_64 Linux guest under that (wasm64
  TCI, as rung 5 does for sparc today), and running an ordinary, natively-compiled
  `qemu-system-sparc` as a process inside that guest — TCG from the guest's point of view, but every
  instruction it emits is itself one more guest instruction for the outer interpreter to decode. Not
  done: a second Wasm target, and a root filesystem small enough to ship with it.
