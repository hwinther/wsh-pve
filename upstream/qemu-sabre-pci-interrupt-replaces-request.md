# QEMU: a PCI interrupt replaces the sabre's outstanding request; sun4u guests lose every OBIO interrupt

Material for a bug report to QEMU. The patch is pve-qemu's
`debian/patches/wsh/0045-hw-pci-host-sabre-keep-PCI-interrupts-to-one-request.patch` (in
`submodules/pve-qemu.patch`), with the qtest `sun4u-sabre-irq-test` in `wsh/0046`.

## Summary

On `qemu-system-sparc64 -M sun4u`, the sabre (`hw/pci-host/sabre.c`) keeps one interrupt request
to the CPU at a time (`irq_request`) and makes the next one when the guest writes the current
one's clear register (`sabre_check_irqs()`). `pci_sabre_set_irq()` waits for that with OBIO
interrupts (ino 0x20-0x3f), but not with PCI interrupts (ino 0x00-0x1f): a PCI interrupt that rises
while a request is outstanding calls `sabre_set_request()` and replaces it.

The CPU takes one interrupt vector at a time: `sparc64_cpu_set_ivec_irq()` ignores a vector sent
while the busy bit of `ASI_INTR_RECEIVE` is set. So when the PCI interrupt rises between the first
request and the guest's write that clears the busy bit, the replacing request is dropped by the
CPU. The guest handles the first vector and writes its clear register; that no longer matches
`irq_request` and is ignored. From then on the sabre waits for a clear the guest can't send:

- every OBIO interrupt is blocked (`irq_request != NO_IRQ_REQUEST`): the built-in IDE controller
  (ino 0x20), the serial console (0x2b), the keyboard;
- a PCI interrupt gets through only on a new rising edge, and the device whose vector was dropped
  keeps its (level) line up.

- **Affected:** QEMU 11.1.3, and every version with this `pci_sabre_set_irq()`.
- **Who to tell:** Mark Cave-Ayland (sun4u, sabre), on qemu-devel@nongnu.org.

## Evidence

OpenBSD 8.0 GENERIC installed on the built-in cmd646 (`ide.0`), `sunhme` on `pciB` (ino 0x10:
qemu-server puts every NIC on pciB), 512 MB, OpenBIOS with the client-interface fix of
`upstream/README.md` (OpenBIOS 0023). The guest runs `tar cf - /usr | cksum` with `ping -f` to the
user-network gateway in the background. The console shows

```
wd0(pciide0:0:0): timeout
        type: ata
        c_bcount: 16384
        c_skip: 0
wd0d: device timeout reading fsbn 4834784 of 4834784-4834815 (wd0 bn 7588640; cn 7528 tn 6 sn 38), retrying
```

and then nothing: the CPU is in OpenBSD's idle loop (PSTATE 6, PIL 0), no disk I/O, and the serial
console answers neither Return nor a break. With ntpd reaching the internet instead of the ping
flood it happened in 5 of 6 boots; without network traffic, rarely (a 1 GB `tar` of `/usr`).

A debug build logged the sabre's and the CPU's interrupt events (virtual time in ns):

```
469192482309 SET_REQ 0x20                    IDE (OBIO) request
469192482624 CPU_RAISE 0x20 (not busy)       the CPU takes the vector
469192516836 PCI_SET_IRQ 0x10 1              sunhme's interrupt, 34 us later
469192516912 SET_REQ 0x10, replacing 0x20
469192517103 CPU_RAISE 0x10 (busy)           dropped by the CPU
469192523913 TRAP_IVEC data 0x7e0            the guest takes the IDE vector
469192527679 ASI_INTR_RECEIVE write 0        and clears the busy bit
469192734496 write to OBIO clear of 0x20     ignored: irq_request is 0x10
469194096672 PCI_SET_IRQ 0x20 1              next IDE interrupt: no request
```

State at the hang: `irq_request` 0x10, `pci_irq_in` with 0x10 and 0x20 set, the CPU halted with no
vector pending.

Lab runs (details in `submodules/SPARC.md`, "Cause: the sabre lost a request"):

| QEMU | OpenBSD, `ping -f` + 3 rounds of `tar` | OpenBSD, ntpd + 3 rounds | NetBSD 9.3/11.1, `ping -f` + 2 rounds |
| --- | --- | --- | --- |
| 11.1.3 + Proxmox's patches + our 0001, 0007, 0021-0022, 0034-0037 (no LEMU code) | 2 of 2 hung in round 0 | not run | not run |
| the lab's full series (wsh/0001-0044) | 2 of 2 hung (one with `idle-halt=off`) | 2 of 2 hung | 9.3: 1 of 1 hung (`cmdide0:0:0: lost interrupt`) |
| the full series + the fix | 0 of 4 (12 rounds) | 0 of 3 (9 rounds) | 0 of 2 (4 rounds) |

The plain build still has our cmd646 latch (0021) and softint fix (0036); a run on QEMU 11.1.3
with none of our patches wasn't made. Every run used OpenBIOS with our client-interface fix (0023),
without which the installed OpenBSD kernel doesn't boot.

## Fix

In `pci_sabre_set_irq()`, request a rising PCI interrupt only when no request is outstanding, as
the OBIO branch does. The interrupt stays in `pci_irq_in` and `sabre_check_irqs()` requests it when
the guest clears the current request.

Not changed, and maybe worth a look upstream: the CPU still drops a vector sent while it is busy
(the real UltraSPARC NACKs it and the sabre retries), and a sabre lowering its line
(`sabre_clear_request()`) clears the CPU's busy bit whatever vector it holds. With one request at a
time neither matters. The PCI interrupt-map write (`0xc00 ... 0xc3f`) compares `irq_request` with
the slot number rather than the slot of the request.

The qtest (`tests/qtest/sun4u-sabre-irq-test.c`) drives the sabre's `pbm-irq` lines and intercepts
its `ivec-irq` outputs: a PCI interrupt raised while the IDE request is outstanding, or while
another PCI request is, must wait until the guest clears that request, and the serial console's
interrupt must get through afterwards. It fails without the fix.
