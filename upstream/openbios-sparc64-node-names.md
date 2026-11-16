# OpenBIOS: sun4u node names differ from OBP (`pci@1fe,0`, `su@0`), no Solaris console input

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0009-sparc64-name-upa-and-ebus-children-like-obp.patch`; `openbios/Dockerfile`
builds `openbios-sparc64` with it.

## Summary

OpenBIOS on `qemu-system-sparc64 -M sun4u` names the sabre `pci@1fe,0` and the ebus children
`su@0`, `8042@0`, `eeprom@0`, `power@0`. OBP on an Ultra 5/10 names them `pci@1f,0` and
`su@14,3f8`, `8042@14,60`, `eeprom@14,2000`, `power@14,7240`:

- The sabre's `reg` starts with `0x1fe`, which is `0x1c0 + 2 * UPA port id`. OBP prints the port
  id (`1f`).
- An ebus child is addressed by its two `reg` cells, space and offset. OpenBIOS gave the ebus
  node the PCI bridge's `encode-unit`, which formats a PCI devfn and so prints `0`.

Solaris builds the OBP names for its own device nodes, then looks the firmware's `stdin`/`stdout`
instance paths up among them. With OpenBIOS's names Solaris 10 found no device for
`/pci@1fe,0/pci@1,1/ebus@1/su@0` and never opened the `su` driver as the console. The installer
printed its `Select a Language` prompt (output goes through the firmware) and then ignored every
key.

- **Affected:** current master `e5ac46dd24` (QEMU 11.1.3). This needs
  `openbios-sparc64-virtual-available.md` and the other patches before Solaris 10 gets this far.
- **Who to tell:** Mark Cave-Ayland, openbios@openbios.org.

## Evidence

QEMU 11.1.3 with a debug print in the 16550 receive path. After the language prompt, `0` Return
arrived in the UART (LSR `0x60` → `0x61`, data ready), and nothing ever read it. No RBR read, and
the `su` driver's open (which enables IER) never ran. The `su` driver had attached: it
programmed FCR `0x0f`, 9600 baud, MCR `0x0b`.

`" stdin" ... get-instance-path` at the `ok` prompt, before → after the fix:

```
/pci@1fe,0/pci@1,1/ebus@1/su@0
/pci@1f,0/pci@1,1/ebus@1/su@14,3f8
```

With the fix, the installer echoes `0`, goes on to `What type of terminal are you using?`, and
from there through its curses screens.

## Fix

- `arch/sparc64/tree.fs`: the root's `encode-unit` prints the UPA port id (`reg` cell 0 shifted
  right by one, 5 bits). `decode-unit` accepts both `1f` and `1fe`, so existing paths keep
  working.
- `drivers/pci.c` `ebus_config_cb()`: the ebus node gets an `encode-unit`/`decode-unit` pair for
  two hex cells, `space,offset`.
  OpenBIOS prints `decode-unit isn't unique.` / `encode-unit isn't unique.` at power-on because
  the pair is defined over the bridge methods (cosmetic; a separate method table broke NetBSD's CD
  root detection, cause not found).

paulsheer/openbios commit `5d7938c2` ("sun4u: publish a Solaris 10-compatible device tree") makes
the same two naming changes in its own way (C decode/encode functions and a separate method
table for the ebus). This patch is a separate, smaller implementation.

## Regression check

The sparc64 lab matrix (NetBSD 11.1 and 9.3, OpenBSD 8.0 `bsd.rd`, the Debian 12 installer, the
NetBSD install and installed disk) with this patch: see `submodules/SPARC.md`, "Solaris on sun4u".
