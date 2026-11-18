# QEMU sparc64: a guest's `%softint` write can drop a tick interrupt that fires at the same time

Material for a bug report to QEMU. Found by reading the code and caught once in a trace (below). We
don't carry a fix: it would be a QEMU change (`submodules/pve-qemu.patch`).

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

## Possible fix (not tested)

Do the read-modify-write under the BQL, which `tick_irq()`, `stick_irq()` and `hstick_irq()` already
hold:

```c
void HELPER(clear_softint)(CPUSPARCState *env, uint64_t value)
{
    bql_lock();
    if (do_modify_softint(env, env->softint & (uint32_t)~value)) { ... }
    bql_unlock();
}
```

and the same for `set_softint` and `write_softint`, with `do_modify_softint()` no longer taking the
lock itself. (An atomic or-and on `env->softint` would close the race too, but `cpu_check_irqs()`
needs the BQL anyway.)

## What's missing

A run of the fix long enough to show the hang is gone: with a hang in about one of three long runs
on a busy host, that takes many hours of guest time.
