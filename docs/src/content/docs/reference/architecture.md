---
title: Architecture Reference
description: A reference page for the architecture hardware panel
---

Architecture is a hardware element that is added by this extension.
If it has not been set on a guest, it defaults to the host architecture (typically x86_64).
By setting it to another architecture you change which qemu system is emulated, and specifically which `qemu-system-[arch]` binary will be used when starting the VM.
It is set when the VM is created and can't be changed afterwards.

Currently the supported values are:

- x86_64
- aarch64
- sparc
- sparc64

## X86_64 - 64bit intel

This is the default architecture for WSH PVE, which currently targets only x86_64. Running VMs with this architecture will use the `qemu-system-x86_64` binary.

Note: *If you select the 3dfx/mesa option under display, the rendering passthrough patched binary `qemu-system-x86_64-3dfx` will be used instead.*

## Aarch64 - 64bit ARM

Aarch64 is the 64-bit execution state for the ARM architecture. It is designed for high performance and low power consumption, making it ideal for mobile and embedded devices. When setting a VM to use aarch64, the `qemu-system-aarch64` binary will be used.

Note: *Aarch64 will only support serial console*

## Sparc - 32bit SPARC

SPARC (Scalable Processor Architecture) is a RISC (Reduced Instruction Set Computing) architecture developed by Sun Microsystems. The 32-bit version is used in older systems and some embedded applications. When setting a VM to use sparc, the `qemu-system-sparc` binary will be used.

Note: *Only specific configurations are known to work, see the [SPARC guide](/guides/sparc/) for hints on how to use this architecture.*

## Sparc64 - 64bit SPARC

Sparc64 is the 64-bit version of the SPARC architecture. It is used in high-performance computing and enterprise servers. When setting a VM to use sparc64, the `qemu-system-sparc64` binary will be used.

Note: *sun4u with OpenBIOS runs NetBSD (installed and booted, serial or VGA console); the disk and CD-ROM must be on the built-in IDE. Solaris 10 reaches its installer there (with the package's patched `openbios-sparc64`) but doesn't install yet. See the [SPARC guide](/guides/sparc/#sparc64-sun4u).*

## Further reading

- Read [system targets](https://www.qemu.org/docs/master/system/targets.html) in the QEMU documentation
