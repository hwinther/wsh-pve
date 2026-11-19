# QEMU: the ESP raises its interrupt in the instruction that starts a command

Material for the owner, for QEMU issues [#2620](https://gitlab.com/qemu-project/qemu/-/issues/2620)
and [#2674](https://gitlab.com/qemu-project/qemu/-/issues/2674) (NeXTSTEP and OPENSTEP for SPARC
freeze while installing). The patch is pve-qemu's
`debian/patches/wsh/0040-esp-raise-the-interrupt-late-on-sun4m-as-a-real-targ.patch`, with four
qtest cases in `sun4m-esp-test` in `wsh/0041` (both in `submodules/pve-qemu.patch`). QEMU doesn't
take AI-generated code, so this note describes the change for a report or a patch written by hand.

## Summary

QEMU's ESP (`hw/scsi/esp.c`) runs a SCSI command to its end inside the register write that starts
it when the backend answers at once (selection, a DMA transfer from a cached image, the status and
message phases), and `esp_raise_irq()` raises the interrupt line in the same call, so the guest takes
the interrupt in the next instruction. A real target takes milliseconds to seek and answer.

NeXTSTEP 3.3 and OPENSTEP 4.2 depend on that time. Their SCSI driver (`SCSAController`, on the
kernel's `_esp_*` code) starts a command while it holds a lock, and the completion routine that the
ESP interrupt runs (`_esp_finish` and the driver's completion, `-lock` sent with `_objc_msgSend`)
takes the same lock. With the interrupt in the next instruction, the completion runs at PIL 4 (the
ESP's level) on top of the thread that still holds the lock and spins on it for good: timer
interrupts go on, the ESP is never touched again, no further disk I/O.

- **Affected:** QEMU 11.1.3 (where it was found, with and without our other ESP patches, `wsh/0001`
  and `wsh/0038`). `esp_raise_irq()` has raised the line at once for as long as the file has
  existed; not bisected, upstream master not checked.
- **Existing reports:** #2620 and #2674 describe the symptom (installs freeze; "partially working"
  on the QEMU wiki's SPARC page). Neither names a cause.
- **Who to tell:** Mark Cave-Ayland (most of the ESP work, and the sparc32 machines); `MAINTAINERS`
  lists `hw/scsi/*` under SCSI: Paolo Bonzini (M), Fam Zheng (R). qemu-devel@nongnu.org.

## How it shows up

`-M SS-5` (or SS-20), TCX, the NeXTSTEP 3.3 SPARC/PA-RISC User CD or the OPENSTEP 4.2 User CD
(which carries the SPARC kernel too), a blank disk. Both installers boot and then hang on the disk:
while mounting root, preparing the disk or copying the base system, on every attempt (six installs
with pve-qemu-kvm 11.1.3-2+wsh21 and +wsh22). Every hang has the CPU in a simple-lock spin
(`ld [%l0]; cmp %o0, 0; bne`, 0xf00c944c in the 3.3 kernel, 0xf00c9f54 in 4.2) with PSR.PIL 4.
`-trace esp_*` shows the last ESP access is Enable Selection after the disconnect of a finished
8 KB write.

## Fix

Let the interrupt as a whole, `STAT_INT` in the status register and the line (one signal on the
chip), come a fixed time after the event, from a `QEMU_CLOCK_VIRTUAL` timer; the interrupt register
(`RINTR`), the sequence step and the bus phase are set at once as today:

- `esp_raise_irq()`: nothing if `STAT_INT` is set or an interrupt is pending; with a latency, mark it
  pending and `timer_mod()`; without, set `STAT_INT` and raise the line as before.
- The timer's callback, if the interrupt is still pending, sets `STAT_INT` and raises the line.
- `esp_lower_irq()` (reading `RINTR`) also takes a pending interrupt: a driver that polls `RINTR`,
  as OpenBIOS does, gets its bits at once and no interrupt later. `esp_hard_reset()` (and so the
  chip's reset command and the parent's reset line) drops a pending one.
- The pending flag goes into a subsection of `vmstate_esp` (`esp/irq_pending`, sent only while
  something is pending), whose `post_load` re-arms the timer a whole latency ahead.
- A `sysbus-esp` property `x-irq-latency-us` (default 0, today's behaviour, for every other
  machine), copied into `ESPState` at realize. The sun4m machines set 500 as a compat property in
  each concrete machine class (an abstract `MachineClass` has no `compat_props` array), so
  `-global sysbus-esp.x-irq-latency-us=0` turns it off again.

Delaying only the line and setting `STAT_INT` at once (the first experiment) is not enough: with it
at 500 us a NeXTSTEP package install still hung once, in the same spin. A driver that checks
`STAT_INT` right after starting a command sees the command end at once, which no real target can
do.

Measured on SS-5: line-only 0 and 50 us hang (50 us: the package copy, or the SCSI probe under the
Sun PROM `ss5.bin`); line-only 500 us installed both systems in the earlier experiment and hung once
here; the whole interrupt at 500 us installed both systems and booted them to the Workspace (one
install each). A fixed delay models the target's latency; it is not a proof that 500 us is always
enough.

The other way, delaying only the end of a SCSI command (its data and status phases) as a disk's seek
does, was not taken: `esp.c` finishes commands from many places (`esp_command_complete`,
`esp_transfer_data`, the DMA and non-DMA TI paths, `write_response`), and each would need its own
deferral and migration state, while the interrupt has one raise and one lower. Every ESP interrupt
now comes 0.5 ms later on sun4m, selection and bus service included, about 2 ms per disk command:
Solaris 2.6 reads its raw disk at about 20 MB/s instead of 70-200 MB/s and creates files at a
quarter to a third of the rate (`submodules/SPARC.md`, "NeXTSTEP 3.3 and OPENSTEP 4.2", has the
numbers and the regressions). For QEMU a smaller default, or deferring only the status interrupt,
may be worth measuring.

## Test

`tests/qtest/sun4m-esp-test.c` (cases `irq-latency*`) on the SPARCstation 5, the line read through
the `DMA_INTR` bit of the ESP DMA's CSR (0x78400000), which follows it: after Select with ATN and Stop
neither `STAT_INT` nor the line shows 1 ns before 500 us, both do at 500 us; `RINTR` has its bits at
once, and reading it before then, the chip's reset command and `system_reset` cancel the interrupt;
with `-global sysbus-esp.x-irq-latency-us=0` the interrupt comes in the same instruction. Without the
fix `irq-latency` fails (`STAT_INT` right after the selection). A save/load by hand (`migrate` to a
file 100 us after a selection, `-incoming` from it) kept the pending interrupt: nothing right after
`cont`, `STAT_INT` and the line 500 us later.
