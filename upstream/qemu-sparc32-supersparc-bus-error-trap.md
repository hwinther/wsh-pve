# QEMU: a bus error on a SuperSPARC load takes the wrong trap (SunOS 4.1.3 panics on SS-10)

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0049`, with the qtest
`wsh/0050`; published in pve-qemu-kvm 11.1.3-2+wsh31. Our own finding in QEMU's code, independent
of LEMU (column "may send" in [README.md](README.md)). Tested in the lab and through PVE
(`submodules/SPARC.md`, "Older Sun releases on sun4m").

**Reproduced on plain QEMU** (2026-11-20): `qemu-system-sparc` built from the v11.1.3 tag (a clean
checkout, `--target-list=sparc-softmmu`, no patch of ours or LEMU's), with the OpenBIOS image of that
tree (`pc-bios/openbios-sparc32`), boots the SunOS 4.1.3 CD's kernel on `-M SS-10 -m 64` and the
kernel panics after `SUNW,fdtwo0`:

```
SUNW,fdtwo0 at obio 0x700000 pri 11 (onboard)
BAD TRAP: cpu=0 type=29 rp=f00daba4 addr=0 mmu_fsr=0 rw=0
MMU sfsr=0: No Error
...
	psr=40400cc7 pc=f00a0970 npc=f00a0974
...
panic: trap
```

The traceback's arguments show the probe of physical `0xd.0108_0000` (below). Our build (11.1.3
with our patch series, which includes the change described below) with the same stock OpenBIOS gets
past it to the installer's first question ("What would you like to do?"); plain QEMU with only the
change was not built. The qtest below fails on plain 11.1.3 in its two SS-10 load
and fetch cases (trap 0x29 where 0x09 is expected, 0x21 where 0x01 is expected) and passes in the
others.

## Summary

QEMU raises the data access error (trap 0x29) for a bus error on a sparc32 load, and the instruction
access error (0x21) on a fetch, on every CPU model. On the SuperSPARC (SS-10, SS-20) a bus error on a
load is a data access exception (trap 0x09), with the cause in the SFSR (FT=5, access bus error), and
on an instruction fetch an instruction access exception (trap 0x01). QEMU already writes FT=5 into
the SFSR; only the trap type is wrong.

SunOS 4.1.3 (Solaris 1.1, the first SunOS 4 for the SS-10) runs a generic sun4m kernel that also
runs the SS-600MP. At boot it probes for VME controllers (`mbconfig` -> `doprobe` -> `peekl`, with
its fault catcher `nofault` armed) by reading physical `0xd.0108_0000`. An SS-10 has nothing there.
4.1.3's `trap()` sends a fault to the catcher only for trap 0x09; it has no case for 0x29, so the
probe ends in "BAD TRAP" and a panic. 4.1.3_U1 added cases for 0x21 and 0x29 to `trap()`, so
4.1.3_U1B and 4.1.4 boot on QEMU.

- **Affected:** sun4m with the `TI-SuperSparc-*` CPU models (the SS-10, SS-20 and SS-600MP
  defaults); QEMU 11.1.3 and, from the code, earlier releases (not checked how far back). SunOS
  4.1.3 is the only guest seen hitting it; 4.1.3_U1 and later take 0x29 in their catcher as well.
- **Who to tell:** `MAINTAINERS`, "SPARC TCG CPUs" (`target/sparc/`).

## Evidence for the trap type

- A test on a real SPARCstation 20 (SuperSPARC-II) posted to the OpenBIOS list in 2013 by Bob
  Breuer: "sbus timeout: read = Data Access Exception, write = Level 15 int",
  <https://mail.coreboot.org/hyperkitty/list/openbios@openbios.org/message/FO6IEKRIYDQRHBOSYBQUVQMFEQNOPX5R>.
- SunOS 4.1.3, which Sun shipped for the SS-10, catches a failed probe only through trap 0x09; its
  later updates take 0x21 and 0x29 as well. That says nothing about what the SuperSPARC does on a
  store or on an MMU bypass access.
- QEMU itself already sets FT=5 (access bus error) in the SFSR for these faults.

## Where in the code

`target/sparc/ldst_helper.c`, `sparc_raise_mmu_fault()` (the sparc32 one): after writing the SFSR
(FT=5) and the SFAR, it raises `is_exec ? TT_CODE_ACCESS : TT_DATA_ACCESS` (0x21/0x29) whenever the
MMU is on and not in no-fault mode, for every sparc32 CPU. It is reached from
`sparc_cpu_do_transaction_failed()` (loads, stores and fetches through the TLB, which includes ASI
0x20, made inline in `MMU_PHYS_IDX`), from `helper_ld_asi()`/`helper_st_asi()` for the bypass ASIs
0x21-0x2f and the MXCC stream registers, and for unimplemented ASIs.

## Reproducing

The SunOS 4.1.3 CD (`Solaris_1.1.img`, a plain image with 2048-byte sectors) as a CD-ROM on target 6,
serial console, QEMU's own OpenBIOS:

```sh
qemu-system-sparc -nodefaults -M SS-10 -m 64 -bios <v11.1.3 tree>/pc-bios/openbios-sparc32 \
  -vga none -display none -prom-env input-device=ttya -prom-env output-device=ttya \
  -prom-env 'auto-boot?=false' \
  -drive file=Solaris_1.1.img,if=none,id=cd,format=raw,readonly=on \
  -device scsi-cd,channel=0,scsi-id=6,lun=0,drive=cd -net nic,model=lance -net user \
  -chardev socket,id=ttya,path=serial.sock,server=on,wait=on -serial chardev:ttya
# connect to serial.sock; at the OpenBIOS prompt:  boot /iommu/sbus/espdma/esp/sd@6,0:d
```

That is the command line of the plain run above. The kernel prints its banner (`SunOS Release 4.1.3
(MUNIX) #3`), probes its devices and prints the BAD TRAP after `SUNW,fdtwo0`, then reboots. On our
patched build (before the change), `-d in_asm` showed the faulting `ld [%o5]` at `0xf00a0970` on
kernel VA 0xff009000, which the monitor's `gva2gpa` (VM stopped at the trap) put at physical
`0xd.0108_0000`; `-cpu TI-SuperSparc-40` and `-M SS-20` behaved the same.

## Fix (in prose)

A CPU feature for "a bus error on a load or a fetch is an access exception", set in the
`TI-SuperSparc-*` entries of `sparc_defs[]` only. In `sparc_raise_mmu_fault()`, with the feature, a
bus error on a load raises `TT_DFAULT` (0x09) and on an instruction fetch `TT_TFAULT` (0x01) instead
of 0x29/0x21; the SFSR and SFAR are written as before. Our patch leaves everything without evidence
as it was:

- stores keep 0x29 (the hardware reports a failed write later as a level 15 interrupt, the 2013 test
  says; modelling that is a separate change);
- accesses that bypass the MMU (ASI 0x20 through `MMU_PHYS_IDX`, ASIs 0x21-0x2f, the MXCC stream
  registers) and unimplemented ASIs keep 0x29: `sparc_raise_mmu_fault()` gets an `is_bypass`
  argument, which `sparc_cpu_do_transaction_failed()` sets from `mmu_idx == MMU_PHYS_IDX`;
- the microSPARC (SS-5, LX and the other microSPARC machines), TurboSPARC and LEON models are not
  changed, as nothing here says what they do.

The feature is a CPU property (`-cpu TI-SuperSparc-II,-buserr-access-exc` turns it off), and a trace
event shows each trap it changes.

Tested in our lab with that change (11.1.3 with our series, OpenBIOS with our patches): the 4.1.3 CD
installs on the SS-10 with the scripts we use for 4.1.4, and the installed disk boots to `SunOS
sunos413 4.1.3 3 sun4m` (four passes). The CD's kernel takes the new trap 9 times before its
installer: five reads of the VME controller registers at `0xd.0108_0000`-`0xd.0108_1000` and four
reads of the empty SBus slots at `0xe.0000_0000`-`0xe.3000_0000`. 34 installed disks (Solaris
2.2-9, SunOS 4.1.3_U1B and 4.1.4, NetBSD 9.3 and 11.1, OpenBSD 5.9, Debian 4.0 and Red Hat 6.2; 18 on
SS-10/SS-20, Solaris 2.6 also with 4 CPUs, and 16 on the SS-5) boot and pass their checks as before
(`submodules/SPARC.md` has the list). On the SuperSPARC machines every boot takes the new trap on
the four empty SBus slots, and nothing there minded; the SS-5 never takes it.

## A test without SunOS

`tests/qtest/sun4m-bus-error-trap-test.c` (wsh/0050): the test writes a context table, a level 1
table and a trap table into RAM. A tiny boot PROM turns the MMU on in context 0 (the PROM at virtual
0, RAM at 0x01000000, an unassigned physical region at 0x0d000000: `0xd.0d00_0000` on the SS-10,
`0x2d00_0000` on the SS-5), enables traps and makes one access at 0x0d080000; the trap handler stores
the trap type, the SFSR and the SFAR. SS-10: a load must take 0x09 and a fetch 0x01; a store, an
`lda` through ASI 0x20 and 0x2d and a load with the feature off take 0x29. SS-5: a load, a store and
an ASI 0x20 load take 0x29, a fetch 0x21. Every case checks FT=5, and the data accesses the SFAR.
