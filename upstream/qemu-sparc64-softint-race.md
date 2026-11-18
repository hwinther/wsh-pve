# QEMU sparc64: a guest's `%softint` write can drop a tick interrupt that fires at the same time (suspected)

Material for a bug report to QEMU, **not verified yet**: this is the explanation that fits what we
measured, found by reading the code. We don't carry a fix.

## What we saw

Tribblix m34 (illumos) on `-M sun4u` (QEMU 11.1.3, TCG, one CPU), with our OpenBIOS patches including
0016 (`upstream/openbios-sparc64-client-interface-interrupts.md`). In 3 of about 9 long runs (45-150
minutes of guest time each, the host busy with other emulated guests) the kernel's clock stopped for
good:

- the guest sits in its idle loop (`idle` → `generic_idle_cpu`) with `%pil` 0 and `PSTATE.IE` set;
- `-d int` logs no trap at all for seconds at a time, and no level-14 interrupt ever again; device
  interrupts (vector traps, levels 12 and 6) are still taken when a key is pressed;
- after the last level-14 interrupt the kernel never writes `%tick_cmpr` again (trace
  `sparc64_cpu_tick_set_limit`), and `%softint` is 0 when the guest clears other bits (trace
  `int_helper_clear_softint new 0x00000000`);
- everything that sleeps hangs: the live CD finished its SMF import (no timers needed) and then did
  nothing; an install stopped in the middle of its package installs.

All three had heavy interrupt traffic at the time: one downloaded packages over the network, one
imported SMF manifests from the CD-ROM (IDE interrupts), one configured the devices of the new
system; the last two ran while other emulated guests kept the host busy. Before OpenBIOS 0016 the same hang
was seen twice as well, alongside the register window corruption that 0016 fixed.

## Suspected cause

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
`%set_softint`/`%clear_softint` for every device interrupt (`setvecint_tl1`, `pil_interrupt`), so the
window comes up often; a host that preempts the vCPU thread in the middle of the helper makes it
much wider.

## Possible fix (not tested)

Do the read-modify-write under the BQL, which `tick_irq()`, `stick_irq()` and `hstick_irq()` already
hold:

```c
void HELPER(set_softint)(CPUSPARCState *env, uint64_t value)
{
    bql_lock();
    if (do_modify_softint(env, env->softint | (uint32_t)value)) { ... }
    bql_unlock();
}
```

and the same for `clear_softint` and `write_softint`, with `do_modify_softint()` no longer taking
the lock itself. (An atomic or-and on `env->softint` would close the race too, but
`cpu_check_irqs()` needs the BQL anyway.)

## What's missing

- A trace that catches the moment: `sparc64_cpu_tick_irq_fire` followed by an
  `int_helper_clear_softint`/`int_helper_set_softint` whose new value lacks bit 0 although the guest
  didn't clear it, with no level-14 interrupt in between.
- A run of the fix long enough to show the hang is gone (with a hang in about one of three long runs,
  that takes many hours of guest time).
