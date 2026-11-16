# QEMU: sun4m flushes the whole TLB on every change of the SRMMU no-fault bit

Material for a bug report to upstream QEMU. We carry the change in pve-qemu as
`debian/patches/wsh/0017-target-sparc-flush-the-TLB-on-a-no-fault-bit-change-.patch`, with the
qtest `tests/qtest/sun4m-mmu-nofault-test.c` in
`debian/patches/wsh/0018-tests-qtest-test-no-fault-mode-and-the-TLB-on-sun4m.patch` (both in
`submodules/pve-qemu.patch`).

## Summary

A write to the SRMMU control register (`ASI_M_MMUREGS`, register 0) flushes the vCPU's whole
software TLB whenever the no-fault bit (NF) changes. Solaris 2.x sets NF before it saves a user
register window to the user stack (or restores one from it) and clears it afterwards, so a missing
stack page doesn't trap inside the handler; it then reads the fault status register to see whether
the access worked. On the microSPARC-II (`-M SS-5`, `Fujitsu-MB86904`) Solaris does this in every
window overflow and underflow trap. A user program that calls deeper than the 8 register windows
(shells, `awk`, compilers, any recursion) takes tens of thousands of such traps a second, each
costing two full TLB flushes and the refills after them, and runs 4 to 10 times slower than the
same program on `-M SS-20`, whose SuperSPARC trap handlers don't touch NF.

NF decides whether a failed translation traps. It doesn't change any translation that succeeds,
and the only TLB entries that depend on it are those `sparc_cpu_tlb_fill()` installs for a failed
translation in no-fault mode (or with traps disabled), with overridden permissions. Flushing only
when such an entry exists removes nearly all of these flushes. In our measurements the SS-5 then
runs those programs as fast as the SS-20, and Solaris on the SS-20 gets faster at signal delivery,
`mmap` and `fork` too.

- **Affected:** every QEMU release with sun4m. Since `6f7e9aec5e` (March 2005) QEMU flushed on
  any change of the control register. Boot mode was added to the condition in 2007 (`6d5f237a59`, "CPU specific
  boot mode"). `af7a06bac7` ("target-sparc: Add MMU_PHYS_IDX", July 2016) took `MMU_E` out of it,
  because the MMU-off translations got their own MMU index, which left `NF | boot mode`. It is the
  same in v11.1.3 and in master (`e9fa1f66f0`, 2026-11-13).
- **Introduced by:** nothing recent. The behaviour is as old as the sun4m MMU emulation, so there
  is no regression to bisect.
- **Who to tell:** `MAINTAINERS`, "SPARC TCG CPUs" (`target/sparc/`): Mark Cave-Ayland (M), Artyom
  Tarasenko (M).

## Where in the code

`target/sparc/ldst_helper.c`, `helper_st_asi()` (sparc32), v11.1.3 and master:

```c
    case ASI_M_MMUREGS: /* write MMU regs */
    case ASI_LEON_MMUREGS: /* LEON3 write MMU regs */
        {
            int reg = (addr >> 8) & 0x1f;
            uint32_t oldreg;

            oldreg = env->mmuregs[reg];
            switch (reg) {
            case 0: /* Control Register */
                env->mmuregs[reg] = (env->mmuregs[reg] & 0xff000000) |
                    (val & 0x00ffffff);
                /* Mappings generated during no-fault mode
                   are invalid in normal mode.  */
                if ((oldreg ^ env->mmuregs[reg])
                    & (MMU_NF | env->def.mmu_bm)) {
                    tlb_flush(cs);
                }
                break;
```

The mappings that comment means are made in `target/sparc/mmu_helper.c`, `sparc_cpu_tlb_fill()`:

```c
    if ((env->mmuregs[0] & MMU_NF) || env->psret == 0)  {
        /* No fault mode: if a mapping is available, just override
           permissions. If no mapping is available, redirect accesses to
           neverland. Fake/overridden mappings will be flushed when
           switching to normal mode. */
        full.prot = PAGE_READ | PAGE_WRITE | PAGE_EXEC;
        tlb_set_page_full(cs, mmu_idx, vaddr, &full);
        return true;
    }
```

That is the only place where a TLB entry depends on NF. `get_physical_address()` reads NF in one
place, when the access check has already failed (`if (error_code && !((env->mmuregs[0] & MMU_NF)
&& is_user)) return error_code;`), and every path with a non-zero error code ends in the branch
above or in a trap. An entry made with error code 0 is the same whatever NF is.
`sparc_raise_mmu_fault()` (`ldst_helper.c`) reads NF at the time of an unassigned access and
caches nothing.

## How it shows up

Solaris 2.6 (5/98), one CPU, 256 MB, OpenBIOS, the same awk loop on both machines (`nawk
'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}'`), QEMU 11.1.3:

- `-M SS-5`: about 47 s. During the loop the guest takes about 39,000 window overflow and as many
  underflow traps a second (`-d int`), and QEMU does about 280,000 TLB flushes a second (the sum of
  "TLB full flushes" and "TLB partial flushes" in `info jit`; a flush of every dirty MMU index counts
  as partial when not all indexes are dirty).
- `-M SS-20`: about 5 s and about 700 flushes a second.

NetBSD 11.1 runs the same awk loop equally fast on both machines (1.85 s and 1.80 s), so the
machine and CPU model alone don't explain it. The difference is in the trap handlers that the guest
uses with each CPU.

What the guest does, described from the Solaris 2.6 kernel (no code copied): the window overflow
handler for a user window clears the fault status register, reads the control register, writes it
back with NF set, stores the 16 registers of the window to the user stack with ordinary stores,
writes the old control register value back, and reads the fault address and status registers. If a
fault was recorded it takes the slow path: it faults in the page and saves the window again or into
a kernel buffer. Otherwise it returns. The underflow handler does the same around the loads. Its
comment explains the choice: probing the page first and then storing would race with the page
daemon on a multiprocessor. These generic handlers are what Solaris uses with the microSPARC-II
module. The SuperSPARC module has its own handlers, which probe the page with an MMU probe (`lda
[...] 0x03`) and never write the control register. The common trap entry code (a user window that
must be saved when a trap, interrupt or system call arrives) and the illegal instruction handler
also use NF on every CPU, which is most likely why the SS-20 gains too (signal delivery, `mmap`,
`fork`; inferred, not traced per path).

## Reproducing

Any Solaris 2.5.1-9 installed on `-M SS-5` (it must be installed on that machine: an SS-5 install
doesn't boot on the SS-20 and the reverse), one CPU:

```sh
time nawk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}'
```

In the monitor, `info jit` before and after: the flush counters grow by about 280,000 a second on
the SS-5 and by a few hundred on the SS-20. The qtest below runs from a boot ROM and needs no
guest OS; it checks correctness, not the flush count.

## Fix (in prose)

Keep a per-CPU flag, set where `sparc_cpu_tlb_fill()` installs an entry with overridden
permissions (the branch above). In the control register write, flush when the boot mode bit
changes, as now, and when NF changes **and** the flag is set. Clear the flag after the flush. The
argument, bit by bit, with the CPU models QEMU has (microSPARC I/II/IIep and the MB86904/MB86907,
SuperSPARC 40-61 and II, LEON2/3; QEMU has no HyperSPARC):

- **NF (bit 1, every model):** only the entries made in the no-fault branch depend on it (see
  "Where in the code"). They are either redirected to an unassigned address or given RWX permission
  on a page the access check refused. They must not be used in normal mode, and the flag makes sure
  they aren't. The flag is set whatever made the entry (NF or `psret == 0`), so the entries made with
  traps disabled are flushed at the next NF change exactly as now. Other flushes (context switch,
  `ASI_M_FLUSH_PROBE`, reset, `loadvm`) leave the flag set at worst, and that only costs one extra
  flush. CPU reset and `cpu_common_post_load()` flush the TLB anyway.
- **Boot mode** (`def.mmu_bm`: 0x4000 on the microSPARC models, 0x2000 on SuperSPARC, none on LEON):
  it changes what an instruction fetch reads with the MMU off (`get_physical_address()`,
  `MMU_PHYS_IDX`), so it keeps its flush. Guests write it a few times at boot.
- **E (bit 0):** it selects `MMU_PHYS_IDX` or the user/kernel indexes (`cpu_mmu_index()`), whose
  entries never mix, and has not flushed since 2016. The store helper's caller ends the TB
  (`dc->npc = DYNAMIC_PC` in `gen_st_asi()`), so the next TB is looked up with the new index.
- **The rest** (cache enables, store buffer, parity, PSO, snoop, AC, the SuperSPARC MBus mode bit,
  microSPARC refresh control): nothing in `target/sparc` reads them, and they didn't flush before.
  The implementation and version bits (31-24) can't be written.

Two smaller things came up on the way:

- A trace event in the flush path (we use `sparc_mmu_ctrl_flush(old, new)`) makes the remaining
  flushes visible. In a 15-minute benchmark run on the SS-5 there were 7,955 flushes, all of them
  NF being cleared after a fault in no-fault mode (the stack page wasn't there), plus one at boot
  (boot mode off, MMU on).
- Entries made with traps disabled and NF clear (`psret == 0`) are dropped only by the next
  flush. With traps disabled a real CPU would go into error mode on a fault. This is unchanged
  here; we found it by reading the code and have not seen a guest depend on it.

## Measurements

The sparc lab's bench disk (`e2e/sparc/README.md`, "The bench disk"), Solaris 2.6 (5/98) unless
stated, one CPU, 256 MB, OpenBIOS unless stated. QEMU 11.1.3 with the wsh-pve patches, built from
the same tree with and without the change (`qemu-system-sparc` only, the same configure flags).
Medians of 3 runs, alternating between the two binaries:

| Benchmark | SS-5 before | SS-5 after | SS-20 before | SS-20 after | 2.5.1, SS-5, before | 2.5.1, SS-5, after |
| --- | --- | --- | --- | --- | --- | --- |
| awk loop above (s) | 47.1 | 5.1 | 5.4 | 5.1 | 47.3 | 5.1 |
| BYTE Towers of Hanoi, 10 disks (towers/s) | 4834 | 18927 | 19512 | 18137 | 4833 | 18036 |
| Dhrystone 2.1 (VAX MIPS) | 947 | 918 | 971 | 959 | 963 | 931 |
| nbench integer index | 4.24 | 4.10 | 4.24 | 4.22 | 4.20 | 4.15 |
| lmbench open/close (us) | 52.6 | 11.0 | 8.2 | 10.0 | 45.2 | 7.2 |
| lmbench signal catch (us) | 60.4 | 13.5 | 39.0 | 13.4 | 60.4 | 14.6 |
| lmbench protection fault (us) | 12.8 | 3.1 | 13.0 | 3.1 | 12.5 | 1.9, 1.1 |
| lmbench pipe latency (us) | 125 | 86 | 83 | 89 | 95 | 77 |
| lmbench fork+exit (us) | 1824 | 1595 | 1427 | 1223 | 2032 | 1700 |
| lmbench mmap 8 MB (us) | 3365 | 1300 | 2428 | 1148 | 3350 | 1216 |
| lmbench file reread 8 MB (MB/s) | 569 | 921 | 960 | 947 | 979 | 895 |

The host was shared with other guests (1-minute load 1.3-3.0), so single lmbench latencies spread
by up to 50%; the large ratios are well outside that. lmbench's protection-fault figure is (fault +
catch) minus (catch), and `micro()` prints nothing when that comes to 0, so with the cheaper catch
one 2.5.1 run had no value (it happens without the change too, less often).

Flushes ("TLB full flushes" + "TLB partial flushes" from `info jit`) per host second, one boot per
binary and machine, Solaris 2.6:

| Phase | SS-5 before | SS-5 after | SS-20 before | SS-20 after |
| --- | --- | --- | --- | --- |
| awk loop | 282,000 | 490 | 700 | 330 |
| Towers of Hanoi | 302,000 | 160 | 240 | 115 |
| lmbench subset | 16,200 | 4,500 | 7,000 | 3,600 |

## What was verified

- **History:** `git log -S` in a full clone of QEMU at v11.1.3 (`005c61c0ef`): the comment and an
  unconditional flush on any change came with `6f7e9aec5e` (2005-03-13). Boot mode was added in
  `6d5f237a59` (2007-11-07). `MMU_E` was dropped from the condition in `af7a06bac7` (2016-07-12).
  Master (`e9fa1f66f0`) has the same code as v11.1.3.
- **Which bits are read:** every use of `mmuregs[0]` in `target/sparc` and `hw/sparc` in v11.1.3
  was checked by hand (`cpu.c`, `ldst_helper.c`, `mmu_helper.c`, `machine.c`). E, NF and boot mode
  are the only bits read.
- **The qtest** (`sun4m-mmu-nofault-test`, SS-5 and SS-20): a boot ROM sets up three 16 MB mappings,
  turns the MMU on, sets and clears NF once with no fault, then does a user-mode store (ASI 0x0a)
  to a page the user may only read with NF set (no trap), clears NF and repeats the store, which
  must take a data access exception. It passes on unchanged 11.1.3 and with the change. With NF
  taken out of the flush condition and no flag, it fails: the second store goes through the stale
  RWX entry.
- **Guests:** with the change, the sparc lab's regression matrices passed 46 of 46 cases: Solaris
  2.5.1 and 2.6 installed disks, the 2.5.1 and 2.6 CDs, SunOS 4.1.4 and NetBSD 11.1, on SS-5,
  SS-10 and SS-20, with OpenBIOS and the Sun PROMs, serial console and cg3/TCX. A soak of 25
  minutes each on SS-5 (Solaris 2.6 and 2.5.1, 64 MB so that the guest pages and the no-fault
  path really faults: 76,000 and 166,000 flushes from it) produced the same checksums in every
  round as on SS-20, and `fsck -n` found nothing new.
- **QEMU's own tests:** `make check-qtest-sparc` on 11.1.3 with the wsh-pve series: 18 OK, 2
  skipped, 1 failed (`qmp-test`, `/sparc/qmp/oob`), which fails the same way with the binary built
  without the change.
- **Existing reports:** the QEMU GitLab issues API, searched on 2026-11-16 for "no-fault",
  "MMU_NF", "SS-5 slow", "sparc tlb_flush", "microsparc slow" and "solaris SS-5 slow", found only
  #2281 (a Solaris debugger panic, unrelated).

## Sending it upstream

QEMU declines contributions that include or are derived from AI-generated content
(`docs/devel/code-provenance.rst`). The change and the qtest here were written with an AI agent,
so the safe route is a bug report that describes the fix in prose and leaves the patch to the
maintainer, or a patch written from scratch by a person.

- Bug report: open a GitLab issue at <https://gitlab.com/qemu-project/qemu/-/issues> with the
  summary, the code locations, the bit-by-bit argument and the measurements.
- Cc Mark Cave-Ayland and Artyom Tarasenko (`scripts/get_maintainer.pl -f target/sparc/ldst_helper.c`).
- Drop our patches once a fixed QEMU reaches pve-qemu.
