# OpenBIOS: sparc64 ebus `fdthree` node with a zero-sized `reg`, Solaris 9 panics in `fd`

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0025-sparc64-leave-out-the-ebus-floppy-node.patch`;
`openbios/Dockerfile` builds `openbios-sparc64` with it.

## Summary

`ebus_config_cb()` (`drivers/pci.c`) calls `ob_floppy_init(path, "fdthree", 0x3f0, 0)`, which
creates `fdthree@0,0` under the ebus with a single `reg` entry of space 0, offset 0, size 0, and
no `interrupts`. OBP's `fdthree` on the Ultra 5/10 has three `reg` entries (the 82077's registers,
the ebus DMA engine that drives the controller, the auxio register) and an interrupt.

QEMU's sun4u has none of that: its floppy controller is a PC-style ISA FDC at I/O port 0x3f0
behind the ebus's second BAR, created with `dma = -1` (`hw/sparc64/sun4u.c`), and the ebus has no
DMA engine and no auxio register. So there is no `reg`/`interrupts` set that would describe a
controller a driver for OBP's node could run.

What guests do with the node as it is:

- Solaris 8 and 10 print `WARNING: Out of range register specification from device node
  <fdthree>` and go on.
- Solaris 9 9/05: the first boot after an install reconfigures (`Configuring /dev and /devices`),
  loads `fd`, and panics:

  ```
  BAD TRAP: type=31 ... occurred in module "fd" due to a NULL pointer dereference
  ... ddi_regs_map_setup <- fd_cleanup <- fd_attach
  ```

  Renaming the node at `0 >` before the boot (`" /pci@1f,0/pci@1,1/ebus@1/fdthree" find-device`,
  `" nofdthree" device-name`, `device-end`) lets the boot finish; later boots don't reconfigure and
  don't load `fd`.
- NetBSD lists `fdthree at ebus0 addr 0-ffffffff not configured`.

OpenBIOS itself doesn't boot from the node either: with `-boot a` the sparc64 `boot-device` is
`/obio/SUNW,fdtwo`, a sun4m path.

- **Affected:** every sparc64 OpenBIOS with the ebus, up to the current master `e5ac46dd24` (QEMU
  11.1's `roms/openbios`). The Solaris 9 panic only shows once Solaris 9 gets as far as an installed
  system, which needs the fixes in `openbios-sparc64-memory-available-pages.md` and the notes it
  names.
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org.

## Fix

Don't create the floppy node on sun4u (the ebus exists only there). sun4m's `SUNW,fdtwo` and the
x86 node are unchanged. With it Solaris 9 9/05's installed disk passes its first boot without the
rename, and Solaris 8 and 10 no longer print the warning (results in `submodules/SPARC.md`, "Solaris
8 and 9 install targets on sun4u").

The alternative, an OBP-like node with three `reg` entries, would need an ebus DMA engine and an
auxio register in QEMU's sun4u model first; with entries pointing at nothing, a driver would attach
and then wait for DMA that never happens.
