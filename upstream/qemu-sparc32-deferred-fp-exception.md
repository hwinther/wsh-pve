# QEMU: sparc32 raises fp_exception on the FPop instead of deferring it (the LX PROM's POST stops)

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0053`, with the qtest
`wsh/0054`; not in a published package yet. Our own finding in QEMU's code, independent of LEMU
(column "may send" in [README.md](README.md)). Tested in the lab (`submodules/SPARC.md`,
"SPARCstation LX with its own PROM").

**Reproduced on plain QEMU** (2026-11-21): `qemu-system-sparc` built from the v11.1.3 tag (a clean
checkout, `--target-list=sparc-softmmu`, no patch of ours or LEMU's) runs Sun's SPARCstation LX boot
PROM on `-M LX -m 64 -nographic -bios <the LX PROM>`, and its POST stops:

```
FPU SP Trap Priority >  Test
FPU SP Trap Priority <  Test
     ERROR : Unexpected Synchronous Trap Taken, Trap Type = 00000008, PSR = 414010c4, PC = 70003194, TBR = 00000080
     STATUS : Entering scope loop .... Press <A> key to Abort!qemu: fatal: Trap 0x03 (Privileged Instruction) while interrupts disabled, Error state
```

Our build (11.1.3 with our series, which includes the change described below) passes all the
PROM's FPU tests and reaches its `ok` prompt; plain QEMU with only the change was not built. The
qtest below fails on plain 11.1.3 in all 27 of its trap cases and passes in the other 9. The Sun
PROM can't go into a report: the qtest shows the same without it.

## Summary

The sparc32 FPUs defer fp_exception: an FPop that raises an IEEE 754 exception enabled in FSR.TEM
moves the FPU to fp_exception_pending, the integer unit goes on, and the trap is taken by the next
floating-point instruction, with the FPop in the floating-point queue (FQ). QEMU raises the trap on
the FPop itself and fakes the deferral by advancing pc/npc past it; `target/sparc/int32_helper.c`
and `translate.c` say so ("We do not model the fp_exception_pending state"). Software can see the
difference when the next FP instruction has a higher-priority trap of its own, which then wins.

The LX PROM's `FPU SP Trap Priority <` test does `fdivs` by zero with TEM = 0x1f and then a store
of an FP register to a misaligned address. It expects mem_address_not_aligned (trap 7, priority 10)
on the store and the fp_exception (trap 8, priority 11) on a later FP instruction, whose handler
reads the FSR and drains the FQ with STDFQ while qne is set. QEMU delivers trap 8 at the `fdivs`.
The double-precision version does the same with a doubleword store that is 4-byte but not 8-byte
aligned.

- **Affected:** every sparc32 CPU model in system emulation (sun4m, LEON); QEMU 11.1.3 and, from the
  code, earlier releases (not checked how far back). Seen with the LX boot PROM; operating systems
  get their SIGFPE either way (below).
- **Not affected:** linux-user (the trap goes straight to the signal) and sparc64.
- **Who to tell:** `MAINTAINERS`, "SPARC TCG CPUs" (`target/sparc/`).

## Evidence for the behaviour

- SPARC V8 manual, section 7.3: an fp_exception may be deferred, also past a precise trap, and "an
  outstanding floating-point exception is provoked into causing an fp_exception trap by execution of
  any FPop, load or store floating-point (including STFSR), or FBfcc instruction". Appendix L models
  the FPUs of the implementations it covers with three states, fp_execute, fp_exception_pending and
  fp_exception: the FPU moves to fp_exception, loads the FQ and traps "when the IU attempts to execute
  any floating-point instruction".
- TI TMS390S10 (microSPARC-I) reference guide, revision 02 of 15 December 1992, section 3.0.3: the
  same three states: the FPU moves to fp_exception "when the IU attempts to execute any
  floating-point instruction", FBfcc included; a 1-entry FQ.
- microSPARC-IIep user's manual (April 1997), section 4.3: the same, "when the integer unit dispatches
  any floating-point instruction (including FBCC)"; section 3.11.1: when several traps occur on one
  instruction only the highest-priority one is taken, "lower priority traps are ignored since it is
  assumed that lower priority traps will persist, recur, or are meaningless".
- The Viking (TI TMS390Z50, SuperSPARC) user documentation, November 1990: "fp_exception is a
  deferred trap and is always reported to the next FPOP or FPEV (ldf or stf)".
- The LX PROM's POST expects exactly that (above).

## Where in the code

- `target/sparc/fop_helper.c`, `check_ieee_exceptions()`: an enabled exception raises `TT_FP_EXCP`
  at once.
- `target/sparc/int32_helper.c`, `sparc_cpu_do_interrupt()`: for `TT_FP_EXCP` with qne clear it fills
  the FQ with the current instruction and advances pc/npc, "to mimic delayed trap delivery as if by
  the subsequent insn".
- `target/sparc/translate.c`, `gen_trap_iffpexception()`: honours the fp_exception state (qne set:
  sequence_error), and its comment says the pending state isn't modelled; the FP stores and STFSR
  skip it ("Store insns are ok in fp_exception_pending state").

## Fix (in prose)

For IEEE 754 exceptions in system emulation on sparc32:

- In `check_ieee_exceptions()`, an enabled exception sets cexc and ftt as now, then restores the
  CPU state, records the FPop's address and opcode in the FQ entry (qne stays 0), sets a new
  `fp_pending` flag, moves pc/npc past the FPop and leaves the TB (`cpu_loop_exit`): the FPop writes
  no result and no fcc.
- A new TB flag carries `fp_pending` into translation. Every FPop, FBfcc, FP load (LDF, LDDF,
  LDFSR) and FP store (STF, STDF, STFSR, STDFQ) then calls a helper first, which sets qne, clears
  the flag and raises `TT_FP_EXCP` on that instruction (no pc advance in `sparc_cpu_do_interrupt()`
  for it).
- For a load or store the helper checks the address first: misaligned (V8 alignment, 8 bytes for the
  doubleword ones) raises `TT_UNALIGNED` and leaves the exception pending. Traps that come before
  the FPU sees the instruction (fp_disabled, a privileged STDFQ) don't touch it.
- The flag and the FQ entry go into a new migration subsection.

unimplemented_FPop, invalid_fp_register and sequence_error keep QEMU's current handling in our patch;
deferring unimplemented_FPop the same way would be the consistent next step. QEMU's own doubleword
FP accesses on sparc32 check 4-byte alignment only (`MO_ALIGN_4`, a sparc64 relaxation), which V8
doesn't allow; our patch uses the V8 rule only for the pending check, which the PROM's
double-precision test needs.

Tested in our lab with that change (11.1.3 with our series): the LX PROM's POST passes all its FPU
tests; the SS-5 PROM's POST prints the same as before. Solaris 2.6 on the SS-20 and on the SS-5
delivers SIGFPE with `FPE_FLTDIV` and `si_addr` at the `fdivs` in 504 of 504 cases; with the change
the trap is taken at the next FP instruction (without it: 4 bytes after the `fdivs`), and when
system calls come between the two, on the SS-20 in the kernel, which still delivers the right
signal. The system keeps
running, and C, nawk and bc give the same FP results as before. Our 34 stored sparc32 installs
(Solaris 2.2-9, SunOS 4.1.3_U1B and 4.1.4, NetBSD 9.3 and 11.1, OpenBSD 5.9, Debian 4.0, Red Hat 6.2
on SS-5, SS-10 and SS-20) boot and pass their checks as before.

## A test without the PROM

`tests/qtest/sun4m-fp-deferred-trap-test.c` (wsh/0054): a boot PROM written by the test enables the
FPU and traps, loads 1.0, 0.0 and 3.0 into `%f1`-`%f3` and an FSR with TEM set, then runs `fdivs
%f1, %f2, %f3`, two integer instructions, the FP instruction under test and an STFSR. The trap
handler notes a mem_address_not_aligned trap and returns past the instruction; any other trap stores
the trap type, `%l1`, `%l2`, the FSR, drains the FQ with STDFQ when qne is set, stores the FSR again
and `%f3`. Expected:

- `fadds`, `fmovs`, an aligned `st` and `ld` of an FP register, STFSR and `fba` after the `fdivs`:
  trap 8 at that instruction, after the integer instructions ran; ftt 1 (IEEE), cexc dz, qne 1; the
  FQ entry is the `fdivs` (address and opcode); qne 0 after STDFQ; `%f3` still 3.0.
- A misaligned `st` or `ld`, and an `std` aligned to 4 but not 8: trap 7 at that instruction, then
  trap 8 at the STFSR after it with the same state.
- `fdivs` 1/1, the traps masked (+inf, cexc and aexc dz) and a misaligned store with no exception
  pending: no FP trap, as now.

Each on SS-5, SS-10 and LX (36 cases).

## Also: microSPARC-I memory size

Seen in the same work, separate: `-M LX`, `SPARCClassic` and `SPARCbook` (TI-MicroSparc-I) accept
`-m 256`, and OpenBIOS then stops with `Trap 0x21 (Instruction Access Error) while interrupts
disabled` (plain 11.1.3 as well). QEMU's `mmu_ctpr_mask` of 0x007ffff0 for that CPU is right: the
TMS390S10 reference guide gives the context table pointer as physical bits 26:8 and the memory
interface as 27 bits, "limiting the maximum memory for a microSPARC-based system to 128MB". Our
`wsh/0055` refuses more than 128 MB on those three machines (a new `max_ram` in the sun4m hwdef,
the 256 MB memory space unchanged). A one-line report would do.
