---
title: Network Device Reference
description: A reference page for the network device hardware panel.
---

QEMU provides various network devices that emulate different network hardware configurations. These devices allow virtual machines to communicate with each other and with the outside world.

This reference page outlines the network devices made available by the WSH PVE patches and their key characteristics.

## WSH PVE added devices

- ne2k_pci - RTL8029 NE2000 PCI, perhaps the most widely supported NIC on older systems
- pcnet - AMD PCnet FAST, an alternative to ne2k but the implementation does not seem to be as stable so use it as a last resort
- sunhme - Sun Happy Meal (sparc64 only), this is probably the only network card that works with 64bit sparc
- lance - Lance Am7990 (sparc only), this is the only network card that will work with 32bit sparc - it is hardcoded into the machine implementation

## Further reading

- Read [about reference](https://diataxis.fr/reference/) in the Diátaxis framework
