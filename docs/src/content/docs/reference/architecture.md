---
title: Architecture Reference
description: Reference page for the architecture hardware panel
---

Architecture is a hardware element that is added by this extension.
If it has not been set on a guest, it defaults to the host architecture (typically x86_64).
By setting it to another architecture you change which qemu system is emulated, and specifically which qemu-system-[platform] binary will be used when starting the VM.

Currently the supported values are:

- x86_64
- aarch64
- sparc
- sparc64

## X86_64 - 64bit intel

This is the default and as WSH PVE is currently only targeted against the same architecture, it means running VMs as usual.

## Aarch64 - 64bit ARM

Aarch64 is the 64-bit execution state for the ARM architecture. It is designed for high performance and low power consumption, making it ideal for mobile and embedded devices. When setting a VM to use aarch64, the `qemu-system-aarch64` binary will be used.

## Sparc - 32bit SPARC

SPARC (Scalable Processor Architecture) is a RISC (Reduced Instruction Set Computing) architecture developed by Sun Microsystems. The 32-bit version is used in older systems and some embedded applications. When setting a VM to use sparc, the `qemu-system-sparc` binary will be used.

## Sparc64 - 64bit SPARC

Sparc64 is the 64-bit version of the SPARC architecture. It is used in high-performance computing and enterprise servers. When setting a VM to use sparc64, the `qemu-system-sparc64` binary will be used.

## Further reading

- Read [system targets](https://www.qemu.org/docs/master/system/targets.html) in the QEMU documentation
