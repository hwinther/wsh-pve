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

TODO

## Further reading

- Read [about q35](https://wiki.qemu.org/Features/Q35) in the QEMU documentation
