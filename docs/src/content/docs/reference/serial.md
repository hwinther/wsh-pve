---
title: Serial port Reference
description: A reference page for the serial port hardware panel.
---

Serial ports give a guest a text console that can be reached from the Proxmox web UI (xterm.js) or with `qm terminal <vmid>`. They are essential for the non-x86 architectures added by the WSH patches, where graphical output is limited or unavailable.

## Adding a serial port

A VM can have up to four serial ports, `serial0` through `serial3`. Add one from the VM's Hardware panel (Add → Serial Port).

## Using a serial port as the primary console

Set the guest's **Display** to one of the *Serial terminal* entries (`serial0`–`serial3`) to route the primary console to that port instead of an emulated graphics card. This is the standard way to interact with guests that have no usable display adapter.

Once configured, open the console from the web UI, or from a node shell (escape with `Ctrl-O`):

```bash
qm terminal <vmid>
```

## Architecture notes

- **aarch64** only supports a serial console — there is no graphical display, so set Display to a serial terminal.
- **sparc / sparc64** have working framebuffers (tcx/cg3), but a serial console is still useful for headless installs and for watching OpenBIOS/PROM output during boot.
- **x86_64** guests normally use a graphics adapter, but a serial port is still handy for kernel debugging, headless servers and capturing boot logs.

## Further reading

- Read [about serial terminals](https://pve.proxmox.com/wiki/Serial_Terminal) in the Proxmox VE documentation
