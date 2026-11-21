# sun4m: the lance DMA's base address register resets to 0, not 0xff

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0061` (the fix) and the
qtest `0062`; not in a published package yet. Our own change to QEMU's code, independent of LEMU
(column "may send" in [README.md](README.md)). Tested in the lab (`submodules/SPARC.md`, "SS-20
PROM: auto-boot and the lance DMA").

## What happens

The lance has 24-bit addresses. On sun4m the Ethernet channel of the DMA2 (`ledma`) adds the upper
8 bits of the 32-bit SBus DVMA address from its fourth register (offset `0xc` of the ledma, `0x1c`
of the DMA2 block). `hw/dma/sparc32_dma.c` ORs `dmaregs[3]` into every lance address and clears it
at reset with the other registers. The DMA2 description the file cites at the top calls the register
`E_BASE_ADDR` and says it "defaults to 0xff".

Solaris 2.6's `le` driver never writes the register. OpenBIOS and the SS-20 boot PROM
(`ss20_v2.25_rom`) write `0xff000000`, the PROM only when it probes with `diag-switch?` true. With
`diag-switch?` false (what lets it boot by itself) Solaris sets the IOMMU range to 64 MB, maps the
lance's init block at `0xff40f000`, and the lance asks for `0x0040f000`: an invalid IOMMU entry, an
IOMMU error at level 15, and the kernel recursing in its level-15 handler until a window overflow
with traps disabled stops QEMU:

```text
configuring network interfaces:
qemu: fatal: Trap 0x29 (Data Access Error) while interrupts disabled, Error state
pc: f00412f4  npc: f00412f8
```

`-trace sun4m_iommu_bad_addr` shows `bad addr 0x40f000` just before.

## The change (0061)

`sparc32_dma_device_reset()` sets `dmaregs[3]` to `0xff000000` for the ledma; the ESP channel's
register stays 0. Guests that write it are unaffected.

## Tested

- qtest `sun4m-ledma-test` (0062): the register after start and `system_reset` on the SS-5, SS-20
  and LX, the ESP channel's register 0, and the lance reading an init block through a 64 MB IOMMU
  from `0xff400000` (with the register written to 0, an IOMMU error at `0x00400000`). Its reset and
  lance cases fail without 0061.
- SS-20 PROM, Solaris 2.6, an NVRAM image with `diag-switch?` false: `login:` by itself on three
  starts in a row; without 0061 QEMU stops at every start. OpenBIOS SS-20, the SS-5 PROM (Solaris 8)
  and the LX PROM (Solaris 2.6) boot as before.

## Open questions for upstream

- Whether the other DMA2 registers' reset values should be checked against the same description.
