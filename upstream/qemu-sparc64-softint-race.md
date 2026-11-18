# QEMU sparc64: a guest's `%softint` write can drop a tick interrupt that fires at the same time

Material for a bug report to QEMU. Found by reading the code and caught once in a trace (below). The
patch is pve-qemu's `debian/patches/wsh/0036-target-sparc-write-softint-under-the-BQL.patch`, with
the qtest `sun4u-softint-test` in `wsh/0037` (both in `submodules/pve-qemu.patch`). QEMU doesn't
take AI-generated code, so this note describes the change for a patch written by hand.

- **Affected:** QEMU 11.1.3 (where it was seen). `do_modify_softint()` has taken the BQL only around
  `cpu_check_irqs()` since `5ee5993001` ("sparc/sparc64: grab BQL before calling cpu_check_irqs");
  not bisected further.
- **Who to tell:** Mark Cave-Ayland and Artyom Tarasenko (SPARC, `MAINTAINERS` "SPARC TCG CPUs"), on
  qemu-devel@nongnu.org.

## What we saw

Tribblix m34 (illumos) on `-M sun4u` (QEMU 11.1.3, TCG, one CPU), with our OpenBIOS patches including
0016 (`upstream/openbios-sparc64-client-interface-interrupts.md`). In 3 of about 9 long runs (45-150
minutes of guest time each, the host busy with other emulated guests), plus 2 more before 0016, the
kernel's clock stopped for good:

- the guest sits in its idle loop (`idle` → `generic_idle_cpu`) with `%pil` 0 and `PSTATE.IE` set;
- `-d int` logs no trap at all for seconds at a time, and no level-14 interrupt ever again; device
  interrupts (vector traps, levels 12 and 6) are still taken when a key is pressed;
- after the last level-14 interrupt the kernel never writes `%tick_cmpr` again (trace
  `sparc64_cpu_tick_set_limit`), and `%softint` holds no tick;
- everything that sleeps hangs: the live CD finished its SMF import (no timers needed) and then did
  nothing; an install stopped in the middle.

Each time with heavy interrupt traffic (network downloads, the CD-ROM's IDE interrupts during the
SMF import, device configuration); two of the three ran while other emulated guests kept the host
busy.

## Cause

illumos programs `%tick_cmpr` for its next clock tick and waits for the level-14 interrupt; it
doesn't reprogram until that interrupt has been handled (`cbe_level14` → `cyclic_fire`, then
`tick_rtt` clears `TICK_INT` and makes sure the compare value is still in the future). If the
interrupt is lost, the clock is gone.

In QEMU the tick timer fires in the main loop thread, holding the BQL
(`hw/sparc64/sparc64.c`, `tick_irq()`):

```c
    env->softint |= SOFTINT_TIMER;
    cpu_kick_irq(cpu);
```

while the guest's `wr %set_softint`, `wr %clear_softint` and `wr %softint` run in the vCPU thread,
without the BQL (`target/sparc/int64_helper.c`):

```c
void HELPER(clear_softint)(CPUSPARCState *env, uint64_t value)
{
    if (do_modify_softint(env, env->softint & (uint32_t)~value)) {
```

`do_modify_softint()` stores the new value and takes the BQL only afterwards, for
`cpu_check_irqs()`. If `tick_irq()` sets `SOFTINT_TIMER` between the vCPU's read of `env->softint`
and its store, the store writes the old value back and the tick's bit is gone. illumos writes
`%set_softint`/`%clear_softint` for every device interrupt, so the window comes up often; a host
that preempts the vCPU thread in the middle of the helper makes it much wider.

## The trace

A live CD boot with the trace events `sparc64_cpu_tick_*`, `int_helper_*softint` and
`sparc64_cpu_check_irqs_*` (about 380 000 level-14 interrupts went through before this point). The
guest's level-10 handler (`pil_interrupt`, which clears `1 << pil` in `%softint`, nothing else)
runs with interrupts disabled when the tick fires:

```
sparc64_cpu_tick_set_limit tick set_limit limit=0xbfaa24f57 (enabled) ...
int_helper_clear_softint new 0x00000400
sparc64_cpu_check_irqs_set_irq Set CPU IRQ 10 old=0x0 new=0x4a
sparc64_cpu_tick_irq_fire tick_irq: fire
sparc64_cpu_check_irqs_disabled Interrupts disabled, pil=0x00004400 pil_in=0x00000000 softint=0x00000401 current interrupt 0x4a
int_helper_clear_softint new 0x00000000
int_helper_set_softint new 0x00001000
...
```

`tick_irq()` sees `softint` = 0x401 (level 10 and the tick). The guest then clears bit 10 (0x400),
and the result is 0x000 instead of 0x001: the vCPU had read 0x400 before the tick's bit was set and
stored 0x400 & ~0x400. No `tick_irq_fire`, `tick set_limit` or `Set CPU IRQ 14` follows in the
remaining 2 500 trace lines (about ten minutes, while the SMF import, which needs no timer, went on
from about 20 to 46 of 95 manifests).

## Fix

Do the read-modify-write under the BQL, which `tick_irq()`, `stick_irq()` and `hstick_irq()` already
hold when they set their bits. In `target/sparc/int64_helper.c`:

- `helper_set_softint()`, `helper_clear_softint()` and `helper_write_softint()` start with
  `BQL_LOCK_GUARD();`, so the read of `env->softint`, the new value, the store, the
  `cpu_check_irqs()` call and the trace all happen with the lock held (the guard takes the lock only
  if the caller doesn't hold it already, and `BQL_LOCK_GUARD` works in the user-mode build too, where
  these supervisor-only instructions never get this far);
- `do_modify_softint()` no longer takes and drops the lock around `cpu_check_irqs()` itself.

No other code writes `env->softint` from the vCPU thread; `rd %softint` reads it without the lock,
which is fine. `ppc` (`excp_helper.c`) and `riscv` (`cpu_helper.c`) take the BQL the same way for
interrupt state that their timers change. An atomic or/and on `env->softint` would close the race
only if the three timer callbacks also used atomics, and `cpu_check_irqs()` needs the BQL anyway.
A plain `bql_lock()`/`bql_unlock()` pair in each helper would do the same as the guard.

The cost is one uncontended lock per `%softint` write; with the BQL held by the main loop the vCPU
waits for it, as it already did for `cpu_check_irqs()` whenever interrupts were enabled.

## Test

`tests/qtest/sun4u-softint-test.c` runs a 27-instruction boot PROM on `-M sun4u -accel tcg` (from
power-on reset: RED state, MMU off, `PSTATE.IE` clear, so the level-14 interrupt is never taken and
`TICK_INT` stays in `%softint`). The PROM arms `%tick_cmpr` 10 us ahead (1000 ticks at 100 MHz,
`INT_DIS` cleared), then sets and clears soft interrupt 1 with `%set_softint`/`%clear_softint` in a
loop until `%softint` shows `TICK_INT`, clears it, counts the tick in RAM and arms the next one. If
16M rounds go by without the tick it counts the tick as lost. The test polls the two counters and
passes after 20000 ticks with none lost (at most 10 s; it took under a second here).

The race can't be triggered on demand, but the loop does almost nothing but `%softint` writes, so a
tick usually lands inside one:

| Binary | Runs | Result |
| --- | --- | --- |
| without the fix | 30 | 30 failed, every one within the first three ticks |
| with the fix | 30 | 30 passed, 20 001-20 399 ticks each, none lost |

With the fix a tick can't be lost, so the test doesn't fail spuriously; without it the test failed
every time here, but nothing guarantees that on another host.

## Results with the fix

`make check-qtest-sparc` and `check-qtest-sparc64` pass as before with the fix (only the known
`qmp-test` `oob` failures). Long Tribblix runs with the fix (a `lab.py install tribblix-m34-sun4u
--check` through PVE and two lab installs on a busy host) were started on 2026-11-18 and had not
finished when this was written; their results go into `submodules/SPARC.md` ("Tribblix on sun4u").
