---
title: Machine Reference
description: A reference page for the machine hardware panel.
---

QEMU provides several machine types that emulate different hardware configurations. Two commonly used machine types are `i440fx` and `q35`.

## i440fx

The `i440fx` machine type emulates the Intel 440FX chipset, which was commonly used in PCs in the late 1990s. It provides a traditional PCI bus and is suitable for running older operating systems and software that expect this type of hardware.

- **Advantages**:
  - Wide compatibility with older operating systems.
  - Stable and well-tested.

- **Disadvantages**:
  - Limited support for modern hardware features.
  - May not perform as well with newer operating systems.

## q35

The `q35` machine type emulates the Intel Q35 chipset, which provides a more modern hardware configuration with support for PCI Express (PCIe). This machine type is suitable for running newer operating systems and software that can take advantage of modern hardware features.

- **Advantages**:
  - Better performance with newer operating systems.
  - Support for modern hardware features like PCIe.

- **Disadvantages**:
  - May have compatibility issues with older operating systems.
  - Less mature and tested compared to `i440fx`.

## PVE WSH additions

In addition to `i440fx` and `q35` (x86_64), the WSH patches expose machine types for the other architectures in the Machine selector:

- **virt** — the QEMU `virt` machine, used for `aarch64` guests.
- **SS-5** (default), **SS-10**, **SS-20** — the SPARCstation machines for `sparc` guests (see the [supported profiles](/guides/sparc/#supported-sparc32-profiles)).
- **sun** — the Sun machine family for `sparc64` (sun4u) guests.

The available machine types are filtered by the guest's [architecture](/reference/architecture/); selecting a non-default architecture switches the machine list accordingly.

### SCSI IRQ delay (sparc32)

On a sparc32 VM, the Machine editor has **SCSI IRQ delay (µs)** behind the **Advanced** checkbox. It
writes the `esp-irq-latency` key of `machine` (`machine: SS-5,esp-irq-latency=500`). It delays the
interrupt of the SCSI controller (the ESP) by that many microseconds. It is off by default, only
NeXTSTEP 3.3 and OPENSTEP 4.2 need it (at 500), and it makes every disk command about 2 ms slower.
Other architectures refuse it. See the [SPARC guide](/guides/sparc/#scsi-interrupt-delay-esp-irq-latency).

## Further reading

- Read [about q35](https://wiki.qemu.org/Features/Q35) in the QEMU documentation
