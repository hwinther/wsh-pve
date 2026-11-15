---
title: Processors Reference
description: A reference page for the processors hardware panel.
---

The Processors panel controls the number of vCPUs and the emulated CPU model. Which CPU options are usable depends on the **architecture** selected for the guest (see the [Architecture reference](/reference/architecture/)).

## CPU model by architecture

| Architecture | Default machine | CPU model |
| ------------ | --------------- | --------- |
| x86_64       | i440fx / q35    | Full PVE CPU model list (host, kvm64, named Intel/AMD models, custom) |
| aarch64      | virt            | A CPU model is applied; defaults are provided by the `virt` machine |
| sparc        | SS-5            | Not configurable — follows the machine and BIOS |
| sparc64      | sun4u           | Not configurable — the machine provides a fixed CPU |

For sparc32 the CPU follows the [profile](/guides/sparc/#supported-sparc32-profiles): no `-cpu`
argument (the machine's own CPU), except `-cpu TI-SuperSparc-50` for SS-20 with the Sun PROM. The CPU
type, sockets and cores can't be set (one CPU). sparc64 gets no `-cpu` argument.

## SPARC limitations

SPARC emulation is sensitive to the guest operating system:

- sparc32 has a **single CPU** and at most **256 MB of RAM** on SS-5, **512 MB** on SS-10/SS-20.
- Installation can be slow and host CPU usage may sit near 100% for the emulated core — this is expected. Pinning the VM to a low-frequency core, or keeping these guests on a test host, avoids reducing performance for other guests.

## Further reading

- Read [about CPU types](https://pve.proxmox.com/wiki/Qemu/KVM_Virtual_Machines#qm_cpu) in the Proxmox VE documentation
- Read [about CPU emulation](https://www.qemu.org/docs/master/system/qemu-cpu-models.html) in the QEMU documentation
