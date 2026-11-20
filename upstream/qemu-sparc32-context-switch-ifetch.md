# QEMU: sun4m stops Solaris 2.1 when it flushes a context it hasn't filled yet

Material for a bug report to upstream QEMU. The change is not carried in pve-qemu yet: it exists as
a standalone patch on 11.1.3 with `debian/patches/wsh/0001-0041` (the context in `cpu.h` is
wsh/0017's `mmu_nf_entries`), tested in the lab only (`submodules/SPARC.md`, "Older Sun releases on
sun4m").

## Summary

Solaris 2.1 (SunOS 5.1, the first sun4m release) stops QEMU right after its device configuration:

```
qemu: fatal: Trap 0x21 (Instruction Access Error) while interrupts disabled, Error state
pc: f0014768  npc: f001476c
```

The kernel gives a new process's context a fresh level 1 table in `srmmu_l1setup`: it writes the
table's address into the context table entry first and copies the kernel's level 1 entries into the
table afterwards. Writing the entry flushes the context from the TLB, because the entry held a valid
table before (at boot every context points at the kernel's table): the flush routine disables traps,
writes the context register, flushes the context and writes the old context back, all within one
page of kernel text. For those few instructions the CPU runs in a context that doesn't map the
kernel yet. The SuperSPARC executes them (Sun supported 2.1 on the SS-10); QEMU doesn't. Solaris 2.2
and later copy the entries before they write the context table entry, so they never get there.

- **Affected:** sun4m with any CPU model, every QEMU release; Solaris 2.1 is the only guest seen
  hitting it.
- **Introduced by:** nothing recent: QEMU has flushed the whole TLB on a context change since the
  SRMMU emulation began, and has mapped a failed translation with traps disabled to an unassigned
  address ("neverland") since the no-fault handling was added.
- **Who to tell:** `MAINTAINERS`, "SPARC TCG CPUs" (`target/sparc/`).

## Where in the code

`target/sparc/ldst_helper.c`, `helper_st_asi()`, `ASI_M_MMUREGS` register 2: a change of the context
register calls `tlb_flush(cs)` ("we flush when the MMU context changes because QEMU has no MMU context
support").

`target/sparc/mmu_helper.c`, `sparc_cpu_tlb_fill()`: when `get_physical_address()` fails and `MMU_NF`
is set or `env->psret == 0`, the page is mapped to `0xffffffffffff0000` with full permissions. An
instruction fetch from there fails as an unassigned access (`sparc_cpu_do_transaction_failed()` ->
`sparc_raise_mmu_fault()`, `TT_CODE_ACCESS`), and with traps disabled `sparc_cpu_do_interrupt()` stops
the machine.

## How it shows up

What the guest does, from the 2.1 kernel's symbols and disassembly (no code copied):

- `srmmu_mmu_flushctx` at 0xf0014724: read `%psr`, clear ET, read the context register, write the
  context to flush (0xf0014764), `sta %g0, [0x300] 3` (flush context, 0xf0014768), compare, write the
  old context back (0xf001477c), restore `%psr`. All in the page 0xf0014000.
- It is reached from `srmmu_l1setup` -> `mmu_writeptp` (the context table entry, old value a valid
  page table descriptor) -> `srmmu_tlbflush` (level 0) -> `mmu_flushctx`. `srmmu_l1setup` calls
  `bcopy` from the kernel's level 1 table only after `mmu_writeptp` returns. 2.2's `srmmu_l1setup`
  has the two calls the other way round.

Stopped at 0xf0014764 with the gdb stub, the walk read with the monitor's `xp`:

| | context table entry | level 1 entry for 0xf0000000 | result |
| --- | --- | --- | --- |
| context 0x80a (the one being flushed) | `0x00ea5681` (table at 0xea56800) | `0x00000000` | invalid |
| context 0 | `0x00e85401` | `0x00eb6501` -> level 2 -> level 3 `0x00ef10ba` | 0xf0014768 -> physical 0xef10768 |

QEMU flushes the whole TLB at 0xf0014764, the fetch of 0xf0014768 walks context 0x80a, fails, gets the
neverland mapping (traps are disabled) and stops. `-cpu TI-SuperSparc-40` and the SS-10's default
`TI-SuperSparc-II` behave the same.

## Reproducing

The Solaris 2.1 CD on `-M SS-10` under OpenBIOS (which needs our openbios patches 0019-0022 to get
that far), the CD as a disk (`-device scsi-hd` on the image, target 6), the serial console:

```sh
qemu-system-sparc -M SS-10 -m 256 -nographic \
  -drive file=solaris2_1_sparc.iso,if=none,id=cd,format=raw,readonly=on \
  -device scsi-hd,scsi-id=6,drive=cd
# at the OpenBIOS prompt:  boot /iommu/sbus/espdma/esp/sd@6,0:d
```

It doesn't depend on OpenBIOS: under Sun's own SS-10 PROM (2.25, run on `-M SS-20 -cpu
TI-SuperSparc-50`, since it doesn't get through POST on QEMU's SS-10) the CD's kernel and an installed
disk stop at the same `pc f0014768`, and with the change below they install and boot there too (one
more step is needed first for that PROM: qemu-sun4m-ss20-dbri-unnamed-node.md). The same on `-M LX`.

About a minute after the kernel banner, after "clock gained ... days", QEMU exits with the trap
above.

## Fix (in prose)

Model what the hardware does for the instructions that follow a context change in the same page:

- In the context register write, when the value changes and before the flush, translate the page of
  the instruction doing the write (`env->pc`, which the translator saved before the helper) in the old
  context, as an instruction fetch with the current MMU index. Keep the result (virtual page, MMU
  index, physical address, page size) in the CPU state, or mark it absent if that walk fails.
- In `sparc_cpu_tlb_fill()`, before the no-fault branch: if a translation failed for an instruction
  fetch, traps are disabled, and the address and MMU index are those kept, install the kept
  translation with execute permission only and return.

The next context write replaces what is kept (writing the old context back finds the page unmapped in
the new context, so nothing is kept after it), and the flush that comes with it drops the TLB entry.
Only a fetch that would have stopped the machine is affected: with traps enabled the fault is taken
as before, and data accesses are untouched. Cost: one table walk per context change. A trace event
(`sparc_mmu_ifetch_hold`) shows each use.

Tested in our lab with that change (11.1.3 and wsh/0001-0041, OpenBIOS with our patches): the 2.1 CD
boots to its installer, installs, and the installed disk boots to `login:` (`SunOS 5.1 Generic
sun4m`); the kept translation is used twice per new context, 52 times in a boot to `login:`, a few
commands and `init 5`. Installed Solaris 2.2 (SS-10), 2.3 (SS-5) and 2.4 (SS-20) disks boot as
before and never use it. No qtest yet.
