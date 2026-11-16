# QEMU: cmd646 clears its interrupt status bits when INTRQ drops; Solaris "Interrupt not seen"

Material for a bug report to QEMU. The patch is pve-qemu's
`debian/patches/wsh/0021-ide-cmd646-latch-the-interrupt-status-bits-until-the.patch` (in
`submodules/pve-qemu.patch`), with the qtest `sun4u-cmd646-test` in `wsh/0022`.

## Summary

On `qemu-system-sparc64 -M sun4u`, the built-in CMD646 IDE controller clears its per-channel
interrupt status bit as soon as the drive drops INTRQ. The bit is in MRDMODE (0x71), mirrored in
CFR (0x50) bit 2 and ARTTIM23 (0x57) bit 4. A drive drops INTRQ when its status register is read.
On the chip these bits latch and are cleared by writing 1. QEMU already sets `w1cmask` for them,
but `cmd646_set_irq()` also clears them on the falling edge.

Solaris 10's ATA driver reads the drive status and then looks at the controller's interrupt bit
after SET FEATURES. It warns once per IDE device and works on without the interrupt:

```
WARNING: Interrupt not seen after set_features
```

- **Affected:** QEMU 11.1.3, and every version with this `cmd646_set_irq()`.
- **Who to tell:** the IDE maintainer (John Snow) and Mark Cave-Ayland (sun4u), on
  qemu-devel@nongnu.org.

## Evidence

Solaris 10 1/13 DVD on `-M sun4u` (patched OpenBIOS, see `upstream/openbios-sparc64-*.md`), 8 GB
raw disk on `ide.0`, DVD on `ide.1`:

| QEMU | console |
| --- | --- |
| 11.1.3 | `WARNING: Interrupt not seen after set_features` (once per device) |
| 11.1.3 + patch | no warning; `WARNING: /pci@1f,0/pci@1,1/ide@3/dad@0,0 (dad0): Corrupt label; wrong magic number` (the blank disk attached as `dad0`) |

## Fix

In `cmd646_set_irq()`, keep the status bit set when `level` is 0. The bits are cleared only by
the guest's write-1-to-clear (PCI config write, or the BMDMA register that mirrors MRDMODE). The
PCI interrupt line follows the drives' INTRQ, kept in a new `PCIIDEState.intrq` field, not the
latched bits: a first version drove the line from the bits, and guests that never clear them
saw it stuck high (Linux: `irq 7: nobody cared`, interrupt disabled; OpenBSD hung at boot).

`intrq` isn't in the migration stream (`vmstate_ide_pci` is shared by every PCI IDE controller):
a guest migrated with INTRQ up sees the line low until the drive raises it again. An upstream
version should add it in a subsection.

paulsheer/qemu `51d72e16` ("sun4u: fix cmd646 IRQ latch and LSI 53C895 identity for Solaris 10")
latches the bits too and drives the line from them. This patch was written separately and keeps
the line on INTRQ.

The qtest (`tests/qtest/sun4u-cmd646-test.c`) sets up what OpenBIOS would (bus 1 behind the simba
at 00:01.1, the cmd646's I/O BARs), runs SET FEATURES and a status read, and checks the bits in
MRDMODE and CFR and the interrupt line through the sabre. It fails without the fix and with the
line driven from the bits.

## Regression check

NetBSD 11.1 (CD, install to IDE, installed IDE disk), NetBSD 9.3, OpenBSD 8.0 `bsd.rd` and the
Debian 12 installer all run on the CMD646 in the sparc64 lab matrix. Results are in
`submodules/SPARC.md`.
