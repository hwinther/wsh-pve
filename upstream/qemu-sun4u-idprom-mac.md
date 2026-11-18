# QEMU: sun4u puts the default MAC address in the IDPROM when the NIC is added with -device

Material for a bug report to QEMU. The patch is pve-qemu's
`debian/patches/wsh/0034-hw-sparc64-sun4u-take-the-IDPROM-MAC-address-from-a-.patch`, with the
qtest `sun4u-idprom-test` in `wsh/0035` (both in `submodules/pve-qemu.patch`).

## Summary

On `qemu-system-sparc64 -M sun4u` (and `sun4v`), the MAC address in the IDPROM (the last 32 bytes
of the m48t59 NVRAM) comes from the onboard NIC only: the first `-nic`/`-net nic` of the machine's
default model (`sunhme`), which `sun4uv_init()` creates at 01:01.1 on bus A. A NIC added with
`-device`, which is how management tools add NICs, doesn't exist yet when `sun4uv_init()` writes
the NVRAM, so the IDPROM gets `qemu_macaddr_default_if_unset()`'s first address,
`52:54:00:12:34:56`.

OpenBIOS gives the guest the IDPROM's MAC address as the system's. Its `sunhme` node has no
`local-mac-address` (only the sungem's has one, `drivers/pci.c`), so NetBSD's `hme` and Solaris's
`hme` (with OBP's default `local-mac-address?=false`) program the system MAC address into the NIC.
NetBSD's `wm` (`e1000`) uses it as well. The result: every such guest sends from
`52:54:00:12:34:56` whatever `mac=` says, and two guests on one network clash. The host id is made
from the same bytes, so all guests have the same host id too.

- **Affected:** QEMU 11.1.3 (where it was measured). The code that takes the MAC address from the
  onboard NIC only is the same in the `sun4u.c` copies we have read; not bisected.
- **Who to tell:** Mark Cave-Ayland (sun4u, `MAINTAINERS` "Sun4u"), on qemu-devel@nongnu.org.

## Where in the code

`hw/sparc64/sun4u.c`, `sun4uv_init()`:

```c
    nd = qemu_find_nic_info(mc->default_nic, true, NULL);
    if (nd) {
        pci_dev = pci_new_multifunction(PCI_DEVFN(1, 1), mc->default_nic);
        ...
        memcpy(&macaddr, &nd->macaddr.a, sizeof(MACAddr));
        onboard_nic = true;
    }
    pci_init_nic_devices(pci_busB, mc->default_nic);

    /* If we don't have an onboard NIC, grab a default MAC address so that
     * we have a valid machine id */
    if (!onboard_nic) {
        qemu_macaddr_default_if_unset(&macaddr);
    }
    ...
    sun4u_NVRAM_set_params(nvram, ..., (uint8_t *)&macaddr);
```

Using `-nic` instead isn't a way out for a management tool: bus A has no free slot, the onboard NIC
sits at a different PCI path from the `-device` NIC on bus B (an installed Solaris sees a new
`hme` instance and leaves it unconfigured), and `-nic` has no `id` or `bootindex`.

## How it shows up

`-device sunhme,mac=bc:24:11:00:00:01,netdev=net0,bus=pciB`, installed disks, QEMU 11.1.3:

| Guest | NIC | Address the guest uses |
| --- | --- | --- |
| NetBSD 11.1 | `sunhme` | `hme0: Ethernet address 52:54:00:12:34:56` |
| NetBSD 11.1 | `e1000` | `wm0: Ethernet address 52:54:00:12:34:56` |
| NetBSD 11.1 | `virtio-net-pci`, `rtl8139` | `bc:24:11:00:00:01` (these read the device) |
| Solaris 10 1/13 | `sunhme` | `ether 52:54:0:12:34:56` |

## Fix

Without an onboard NIC, write the IDPROM again from a machine-init-done notifier, when every
`-device` NIC exists and before the firmware runs: from the first NIC (in creation order) of the
machine's default model, else from the first NIC of any model. With an onboard NIC, or without
any NIC, the IDPROM is what it was. The host id follows the MAC address as before.

The qtest (`tests/qtest/sun4u-idprom-test.c`) opens the simba's I/O window over the NVRAM (PCI
I/O 0x2000 on bus 1) and reads the IDPROM: default address without a NIC, a `-device sunhme`'s
address, the first `sunhme` after a `virtio-net-pci`, the first NIC when there is no `sunhme`, and
the onboard `-net nic` ahead of a `-device sunhme`. Without the fix the `-device` case fails with
`52:54:00:12:34:56`.

## Regression check

The NetBSD and Solaris cases above with the fix, and the sparc64 lab matrix; results in
`submodules/SPARC.md` ("The sun4u system MAC").
