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
| sparc        | SS-5            | Not configurable — the machine provides a fixed CPU |
| sparc64      | sun4u           | Not configurable — the machine provides a fixed CPU |

For the SPARC architectures the WSH patches intentionally do not emit a `-cpu` argument; the selected machine (SS-5 / sun4u) provides its own processor, so the CPU type field is ignored.

## SPARC limitations

SPARC emulation is sensitive to the guest operating system:

- sparc32 (SS-5) is usually limited to a **single CPU** and around **512 MB of RAM**, depending on the OS.
- Installation can be slow and host CPU usage may sit near 100% for the emulated core — this is expected. Pinning the VM to a low-frequency core, or keeping these guests on a test host, avoids reducing performance for other guests.

## Further reading

- Read [about CPU types](https://pve.proxmox.com/wiki/Qemu/KVM_Virtual_Machines#qm_cpu) in the Proxmox VE documentation
- Read [about CPU emulation](https://www.qemu.org/docs/master/system/qemu-cpu-models.html) in the QEMU documentation
