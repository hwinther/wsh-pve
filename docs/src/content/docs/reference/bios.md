---
title: BIOS Reference
description: A reference page for the BIOS hardware panel.
---

The BIOS (Basic Input/Output System) initializes and tests hardware components during the booting process of a virtual machine. This section provides an overview of the BIOS options available in QEMU and their configurations.

## BIOS options

![BIOS menu](../../../assets/bios.png)

x86_64 and aarch64 can both use OVMF BIOS. For aarch64 this requires the `AAVMF_CODE` firmware from `pve-edk2-firmware-aarch64`, which is pulled in automatically as a package dependency.

Sparc and sparc64 requires either the version of OpenBIOS that matches the architecture bits, or a PROM file.
Generally speaking OpenBIOS is more safe and easier to preconfigure and boot.
However nothing scratches that nostalgic itch quite like seeing the splash logo and POST from SparcStation 5.

The supported PROM files are `ss5.bin` (machine SS-5), `ss20_v2.25_rom` (machine SS-20, which
also gets the `TI-SuperSparc-50` CPU it needs) and `lx.bin` (machine LX, the only firmware it takes;
older packages don't have it, then place your own copy in `/usr/share/kvm/` on the node);
`ss10_v2.25_rom` doesn't run on QEMU's SS-10 and isn't offered, and the SS-600MP runs OpenBIOS or Sun's 600MP PROM, `ss600mp.bin` (256 MB or more; not in any package, see [The SPARCserver 600MP](/guides/sparc/#the-sparcserver-600mp)). The BIOS selector only lists the firmware the chosen machine runs, see the
[SPARC guide](/guides/sparc/#supported-sparc32-profiles). `wsh-sun-proms` (package `wsh-lab`)
installs PROM images you are entitled to use from a source you provide and checks them against
their known SHA-256, see [Installing Sun boot PROMs with
wsh-sun-proms](/guides/sparc/#installing-sun-boot-proms-with-wsh-sun-proms).

## Further reading

- Read [about OpenBIOS](https://github.com/openbios/openbios) in the official OpenBIOS documentation
