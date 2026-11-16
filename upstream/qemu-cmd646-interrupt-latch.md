# QEMU: cmd646 clears its interrupt status bits when INTRQ drops; Solaris "Interrupt not seen"

Material for a bug report to QEMU. The patch is
`ide/cmd646: keep the interrupt status bits latched until the guest clears them` (list of pending
QEMU patches in `submodules/SPARC.md`, "Solaris on sun4u"). It isn't in `pve-qemu.patch` yet.

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

In `cmd646_set_irq()`, return without changing anything when `level` is 0. The bits are cleared
only by the guest's write-1-to-clear (PCI config write, or the BMDMA register that mirrors
MRDMODE). The PCI interrupt line follows the latched bits, as before.

paulsheer/qemu `51d72e16` ("sun4u: fix cmd646 IRQ latch and LSI 53C895 identity for Solaris 10")
contains the same change to `cmd646_set_irq()`, along with LSI changes we don't need. This patch
was written separately and carries only the cmd646 part.

## Regression check

NetBSD 11.1 (CD, install to IDE, installed IDE disk), NetBSD 9.3, OpenBSD 8.0 `bsd.rd` and the
Debian 12 installer all run on the CMD646 in the sparc64 lab matrix. Results are in
`submodules/SPARC.md`.
