# QEMU: sparc32 doesn't take an interrupt unmasked by `wr %psr` in a delay slot (Solaris SMP hangs)

Material for a bug report to upstream QEMU. We carry the change in pve-qemu as
`debian/patches/wsh/0019-target-sparc-let-a-write-to-psr-in-a-delay-slot-end-.patch`, with the
qtest `tests/qtest/sun4m-pil-delay-slot-test.c` in
`debian/patches/wsh/0020-tests-qtest-test-an-interrupt-let-in-from-a-delay-sl.patch` (both in
`submodules/pve-qemu.patch`).

## Summary

QEMU looks at a vCPU's pending interrupts when the vCPU comes back to the main loop
(`cpu_handle_interrupt()`), not between chained translation blocks. An instruction that can
unmask a pending interrupt therefore ends its TB with `exit_tb` instead of chaining: on sparc32
`wr %psr` (`do_wrpsr()` sets `DISAS_EXIT`). When that instruction is in a delay slot, the request is
dropped and the TB chains on to the branch target, so an interrupt that the write let in waits until
something else stops the vCPU: the next timer or device interrupt, another vCPU's kick, an exit
request. On one CPU that is at most a clock tick and nobody notices.

Solaris 2.x lowers PIL in a delay slot in `splx()`/`splr()` (an annulled `bl,a` with the `wr %psr`
in its slot). On `-M SS-20 -smp 2` (or SS-10, or 4 CPUs) a CPU that is spinning in a loop of
`mutex_tryenter` and `splx` never takes the level 13 cross-call the other CPU sends it, and the
sender spins in `xc_sync_cache()` waiting for the acknowledgement. The system interrupt goes to one
CPU only, so the spinning CPU gets no other interrupt and the guest hangs for good, within minutes
of load (a 256 MB `dd` and `sync` hung 4 of 4 times). Single-threaded TCG hangs the same way.

- **Affected:** QEMU 8.2.0 and later on sparc32, up to v11.1.3 and master (`e9fa1f66f0`,
  2026-11-13). sparc64 shares the translator code, but its `wrpr %pil` raises the interrupt from
  the helper (`cpu_check_irqs()` calls `cpu_interrupt()`), so it doesn't depend on the exit; only its
  `membar #Sync` and the icount cases set `DISAS_EXIT` there.
- **Introduced by:** `25524734c6` ("target/sparc: Move WRPSR, SAVED, RESTORED to decodetree",
  2023-10, first in v8.2.0). Before it, the `wrpsr` case emitted `save_state(); gen_op_next_insn();
  tcg_gen_exit_tb()` itself, which worked in a delay slot. Since then it sets `DISAS_EXIT` and lets
  `sparc_tr_tb_stop()` emit the exit, but `sparc_tr_translate_insn()` replaces `DISAS_EXIT` with
  `DISAS_TOO_MANY` whenever the PC doesn't follow the instruction (`if (dc->pc != dc->base.pc_next)`,
  from the TranslatorOps conversion `6e61bc9410`, 2018), and `advance_pc()` resolves a pending
  conditional branch (`npc == JUMP_PC`) with two `goto_tb` and `DISAS_NORETURN`.
- **Who to tell:** `MAINTAINERS`, "SPARC TCG CPUs" (`target/sparc/`): Mark Cave-Ayland (M), Artyom
  Tarasenko (M).

## Where in the code

`target/sparc/translate.c`, v11.1.3 and master:

```c
static void do_wrpsr(DisasContext *dc, TCGv src)
{
    gen_helper_wrpsr(tcg_env, src);
    dc->base.is_jmp = DISAS_EXIT;
}
```

`sparc_tr_translate_insn()`, after the instruction:

```c
    if (dc->base.is_jmp == DISAS_NORETURN) {
        return;
    }
    if (dc->pc != dc->base.pc_next) {
        dc->base.is_jmp = DISAS_TOO_MANY;
    }
```

For an instruction in a delay slot `dc->pc` is the branch target (or `DYNAMIC_PC*` after `jmpl`/
`rett`), never `pc_next`, so `DISAS_EXIT` becomes `DISAS_TOO_MANY` and `sparc_tr_tb_stop()` emits
`gen_goto_tb()` (static target) or `lookup_and_goto_ptr` (dynamic). After a conditional branch that
isn't annulled, `advance_pc()` (called by `do_wr_special()` after `do_wrpsr()`) takes the `JUMP_PC`
case first and emits a `brcond` with a `goto_tb` on each side.

## How it shows up

Solaris 2.6 (5/98) installed on `-M SS-20`, OpenBIOS (the Sun PROM starts one CPU only), `-smp 2`,
256 MB, QEMU 11.1.3 with our patches (none touches this code): `dd if=/dev/zero of=/export/home/big
bs=64k count=4096; sync` never returns. With the guest hung, from the monitor and from gdb attached
to QEMU:

- CPU 1: `pc f0063ef4`, PIL 13, spinning in `xc_sync_cache()` on the other CPU's acknowledgement
  word (`ld [%o5 + 0x284]; cmp; be,a` back).
- CPU 0: in `splr`/`splx` (`pc f0067c54..f0067c8c`), PIL going between 4, 13 and 15, the loop of a
  failing `mutex_tryenter()` on the cross-call mailbox lock that CPU 1 holds.
- `info pic`: `per-cpu 0: pending 0x20000000` (soft interrupt 13 for CPU 0), `per-cpu 1: pending
  0x00000400` (the system timer, level 10, now targeted at CPU 1, which is at PIL 13).
- CPU 0's state: `pil_in = 0x2000`, `interrupt_index = 0x1d` (`TT_EXTINT | 13`), `psret = 1`,
  `interrupt_request = CPU_INTERRUPT_HARD`, not halted, `icount_decr = 0`. Everything is set for
  the interrupt to be taken whenever PIL is 4, but the vCPU never gets back to
  `cpu_handle_interrupt()` while PIL is 4: it raises PIL with a plain `wr %psr` (which exits, at PIL
  15, where the interrupt can't be taken) and lowers it with the one in the delay slot (which
  chains).
- Setting `icount_decr.u16.high` of CPU 0 from gdb a few times (what a kick does) let the
  interrupt in: `pil_in` and `interrupt_index` went to 0, CPU 1 left `xc_sync_cache()` and both CPUs
  ran on.

NetBSD's MP kernel on the same machine doesn't hang (it doesn't lower the level in a delay slot in
a loop like this), which is why this looked Solaris-specific.

## Reproducing

Without a guest OS: the qtest below. With Solaris: any Solaris 2.5.1-9 installed on SS-10 or SS-20,
booted with OpenBIOS and `-smp 2`, then a large write and `sync` or a few parallel CPU-bound jobs;
the hang comes within minutes.

The qtest (`sun4m-pil-delay-slot-test`, SS-5, one CPU, from a boot ROM): a loop raises PIL to 15
with a plain `wr %psr`, writes CPU 0's soft-interrupt set register (0 in the first round, soft
interrupt 13 from the second), counts the round in RAM and lowers PIL to 0, either with a plain `wr
%psr` or with one in the delay slot of `ba`, of a taken `bne`, of a taken `bne,a` and of `jmpl`. The
level 13 trap handler stores its trap type. The interrupt must be taken in round 2. The first round
matters: it makes the TBs chain, so the second round doesn't pass through the main loop. On v11.1.3
the plain case passes and the four delay-slot cases fail (the loop goes round and round); with the
change all five pass.

## Fix (in prose)

Keep `DISAS_EXIT` for an instruction in a delay slot:

- In `sparc_tr_translate_insn()`, don't replace `DISAS_EXIT` with `DISAS_TOO_MANY`.
- In `advance_pc()`, when `npc == JUMP_PC` and `is_jmp == DISAS_EXIT`, don't emit the two
  `goto_tb`: compute the branch into `cpu_npc` (`gen_generic_branch()`), copy it to `cpu_pc`, add 4
  to `cpu_npc`, and mark both `DYNAMIC_PC`.
- In `sparc_tr_tb_stop()`, `DISAS_EXIT`: store `dc->pc` only when it is static (after `jmpl` or
  `rett` it is in `cpu_pc` already) and `save_npc()`, then `exit_tb`. Before the change this path
  was reached only with a static PC equal to `pc_next`, so `save_state()` was enough.

This is what the code did before `25524734c6`, and it costs one exit to the main loop per such
write, which only ever adds a check. In our measurements one CPU loses nothing.

## Measurements

QEMU 11.1.3 with the wsh-pve patches, `qemu-system-sparc` built from the same tree with and without
the change, Solaris 2.6 (5/98) installed on `-M SS-20`, OpenBIOS, 256 MB:

| Test | Without the change | With it |
| --- | --- | --- |
| `-smp 2`, 256 MB `dd` + `sync`, then 600 s of 2 shells looping a CPU job and a 10 MB write | hangs in the write (also upstream v8.2.0 unpatched) | passes |
| `-smp 2`, 30 min of 3 shells looping Dhrystone, Hanoi, awk, `tar \| compress \| uncompress \| cksum`, a 10 MB write and a fork loop | not run (hangs earlier) | 155 rounds, no checksum mismatch, both CPUs 100% busy in `mpstat` |
| `-smp 4`, the same, 30 min | | 294 rounds, no mismatch, all four CPUs 99% busy |
| `-M SS-10 -smp 4`, the same, 15 min | | 155 rounds, no mismatch, 99% busy |
| Install CDs to the installer's first question, `-smp 2` and `-smp 4`: 2.5.1, 7, 8, 9 | | all pass |

One CPU, the same binaries, the sparc lab's bench disk (Solaris 2.6, OpenBIOS, one boot each, host
load 1.0-2.0): the change costs nothing measurable. Each `splx` that lowers PIL now exits to the main
loop once; the numbers are within the run-to-run spread of these benchmarks.

| Benchmark | SS-20 without | SS-20 with | SS-5 without | SS-5 with |
| --- | --- | --- | --- | --- |
| Dhrystone 2.1 (VAX MIPS) | 923.8 | 923.2 | 956.2 | 953.7 |
| Whetstone (MWIPS) | 430.1 | 427.4 | 444.4 | 425.5 |
| BYTE Towers of Hanoi (towers/s) | 17837 | 18941 | 19995 | 19575 |
| awk loop (s) | 5.1 | 5.1 | 5.1 | 4.7 |
| nbench integer / FP index | 4.15 / 1.76 | 4.13 / 1.79 | 4.14 / 1.78 | 4.15 / 1.81 |
| lmbench null syscall (us) | 0.38 | 0.39 | 0.38 | 0.41 |
| lmbench pipe latency (us) | 83.2 | 80.6 | 77.8 | 80.4 |
| lmbench signal catch (us) | 14.2 | 13.1 | 13.2 | 13.6 |
| lmbench fork+exit (us) | 1203 | 1291 | 1458 | 1366 |
| lmbench `sh -c` (us) | 13468 | 12168 | 13585 | 13643 |
| lmbench TCP round trip over `le0` (us) | 213 | 187 | 177 | 198 |

## What was verified

- **The hang and its state:** monitor and gdb on the hung QEMU (above), and that a forced exit to
  the main loop (setting `icount_decr` from gdb) let the pending interrupt in and the guest go on.
- **History:** `git log` of `target/sparc/translate.c` in a QEMU clone (master `e9fa1f66f0`): the
  `wrpsr` case emitted `save_state(); gen_op_next_insn(); tcg_gen_exit_tb()` itself until
  `25524734c6` (2023-10, v8.2.0-rc0); the `DISAS_TOO_MANY` override is from `6e61bc9410` (2018,
  v3.0). Master has the same code as v11.1.3. Upstream v8.2.0 built unpatched hangs in the 256 MB
  write with `-smp 2` like 11.1.3. v8.1.5 can't show the difference: sparc only got multi-threaded
  TCG in 8.2 (`ec860e5d03`), and with round-robin TCG two CPUs are so slow (each cross-call waits for
  the other vCPU's time slice) that the guest didn't reach its login prompt in 600 s (one CPU: 116
  s). Our build with the change and `-accel tcg,thread=single` behaves the same way: it doesn't
  hang, but the boot takes 42 minutes with 2 CPUs, and with 4 CPUs Solaris gives up on CPUs 2 and 3
  (`cpu 2 failed to start`) and hadn't finished booting after 2 hours.
- **The qtest** (`sun4m-pil-delay-slot-test`, above): four of five cases fail on v11.1.3, all pass
  with the change.
- **QEMU's own tests:** `make check-qtest-sparc` with the wsh-pve series and the change: 19 OK, 2
  skipped, 1 failed (`qmp-test`, `/sparc/qmp/oob`, no `oob` capability), the same failure as without
  the change.
- **Guests with one CPU** (no regression): the sparc lab's regression matrices passed 52 of 52
  cases with the change: Solaris 2.5.1 and 2.6 installed disks and CDs, SunOS 4.1.4 and NetBSD
  11.1, on SS-5, SS-10 and SS-20, with OpenBIOS and the Sun PROMs, serial console and cg3/TCX, the
  idle cases and the benchmark disk. The benchmark comparison is below.
- **Existing reports:** the QEMU GitLab issues API, searched on 2026-11-16 for "sparc smp",
  "solaris smp", "sun4m smp", "SS-20 smp", "sparc delay slot", "wrpsr", "sparc32 interrupt" and
  "xc_sync_cache": nothing about this. #3097 ("Solaris 8 fails to install after QEMU 8.1", SS-5,
  one CPU: 8.1.5 works, 9.2.4 and master don't) has the same version window; not reproduced here,
  so it may or may not be this bug. #3263 (the SS-20 PROM sees one CPU) and #4714 (an ESCC
  interrupt line left high, Linux SMP on SS-20) are different problems.

## Sending it upstream

QEMU declines contributions that include or are derived from AI-generated content
(`docs/devel/code-provenance.rst`). The change and the qtest here were written with an AI agent,
so the safe route is a bug report that describes the fix in prose and leaves the patch to the
maintainer, or a patch written from scratch by a person.

- Bug report: open a GitLab issue at <https://gitlab.com/qemu-project/qemu/-/issues> with the
  summary, the code locations and the evidence above.
- Cc Mark Cave-Ayland and Artyom Tarasenko (`scripts/get_maintainer.pl -f target/sparc/translate.c`).
- Drop our patches once a fixed QEMU reaches pve-qemu.
