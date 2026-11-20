# Fixes, their authors and the upstream trackers

An index of the QEMU and OpenBIOS patches this repository carries, who wrote each, and where the
same problem shows up upstream. It exists so the state can be compared again later: what upstream
has fixed meanwhile, which threads a write-up could help, and what is still only here.

Checked on 2026-11-18 against:

- QEMU's tracker, [gitlab.com/qemu-project/qemu/-/issues](https://gitlab.com/qemu-project/qemu/-/issues)
  (searched titles and descriptions for the device, register and symptom names below);
- OpenBIOS's tracker, [github.com/openbios/openbios/issues](https://github.com/openbios/openbios/issues)
  (none of the problems below);
- the compatibility table of the [QEMU SPARC wiki page](https://wiki.qemu.org/Documentation/Platforms/SPARC)
  (last edited 2025-06-02).

The mailing lists (qemu-devel, openbios) were not searched.

## Rule: what may go to QEMU

LEMU's [README](https://github.com/tenox7/lemu) says:

> LEMU code does not go back to QEMU. Please don't send LEMU patches or LEMU bug reports to the
> QEMU project.

This repository follows that, for QEMU and for OpenBIOS (QEMU's sparc firmware, built from QEMU's
`roms/openbios` and looked after by the same people). The **QEMU** and **OpenBIOS** columns below
say, per patch:

- **LEMU origin: not for QEMU**: the patch is Antoni Sawicki's, from LEMU (`From:` and `Origin:`
  lines). Neither the patch nor a bug report about what it fixes goes to QEMU or OpenBIOS from here.
- **built on LEMU: not for QEMU**: our own patch, but on top of LEMU code or built on a LEMU
  technique (the Solaris and sun4u idle halts follow LEMU's SunOS idle; the audio patches sit on
  LEMU's CS4231; 0027 tests LEMU's 0026). Not sent either.
- **may send**: our own fix of QEMU's or OpenBIOS's code, independent of LEMU. The owner may send it,
  as a bug report or as a patch written by hand: QEMU and OpenBIOS don't take AI-generated code, and
  the patches and write-ups here were written with an AI agent.
- **hold**: a QEMU bug seen only while running LEMU code. It may be reported only after it has been
  reproduced on plain QEMU, without any LEMU patch (see "Hold" below).

The owner respects LEMU's wish and hopes it changes one day; if LEMU's author allows it, these
columns change with it. Sending our patches *to LEMU* (for example the carry-backs from our port to
a LEMU fork, see `submodules/SPARC.md`; the patch-to-commit table is in [lemu-port.md](lemu-port.md))
is a separate matter and not covered by this rule.

## Who wrote what

| Author | Where their work lives | Tracker |
| --- | --- | --- |
| Antoni Sawicki (LEMU) | [github.com/tenox7/lemu](https://github.com/tenox7/lemu), a QEMU fork for vintage machines (GPL-2.0) | [tenox7/lemu issues](https://github.com/tenox7/lemu/issues) |
| wsh-pve (this repository) | `submodules/pve-qemu.patch` (`debian/patches/wsh/`), `openbios/patches/` | this repository's issues |

Each carried patch keeps its author in its `From:` line, and LEMU's have an `Origin:` line with the
commit. Details of each fix are in [`submodules/SPARC.md`](../submodules/SPARC.md).

## QEMU (`debian/patches/wsh/` in pve-qemu-kvm)

| Patch | Fixes | Author / origin | QEMU | Upstream tracker | Write-up |
| --- | --- | --- | --- | --- | --- |
| 0001 | ESP rejects Select with ATN after a SCSI bus reset | wsh-pve | may send | none found | [qemu-esp-bus-reset.md](qemu-esp-bus-reset.md) |
| 0002 | ESCC: RR2/RR3 name the wrong channel when both have an interrupt; each channel's line showed both channels' state, so the other line stayed raised | Antoni Sawicki, [LEMU `699cc89f`](https://github.com/tenox7/lemu/commit/699cc89f715c89caa96dabdd5ce8bc092951c21a) | LEMU origin: not for QEMU | [QEMU #4714](https://gitlab.com/qemu-project/qemu/-/issues/4714) (open, 2026-10-18): the stale line, found independently on a Linux SS-20; it doesn't cover RR2/RR3 | none |
| 0003 | ESCC: every second Caps Lock/Num Lock press lost; host key repeat on top of the guest's | Antoni Sawicki, [LEMU `c31ed88b`](https://github.com/tenox7/lemu/commit/c31ed88ba67130c06731ddbe0a73296c6164f688) | LEMU origin: not for QEMU | none found | none |
| 0004 | ESCC: a full queue cut a Sun mouse packet in half | Antoni Sawicki, [LEMU `181f0f52`](https://github.com/tenox7/lemu/commit/181f0f520875f5ec2d2574e28093468e689dbe6a) | LEMU origin: not for QEMU | none found ([#2518](https://gitlab.com/qemu-project/qemu/-/issues/2518), "vertical mouse leaps", is closed and about something else) | none |
| 0005 | qtest `sun4m-escc-test` for 0002-0004, 0006 | Antoni Sawicki, [LEMU `c7a18569`](https://github.com/tenox7/lemu/commit/c7a18569f2b54fd146f325b7499b89216c7865d4) | LEMU origin: not for QEMU | | |
| 0006 | ESCC: the line stayed raised after the guest reset a channel | Antoni Sawicki, [LEMU `c2c2781e`](https://github.com/tenox7/lemu/commit/c2c2781eb91ab837e4b8a9c3ae972c3fdd007f34) | LEMU origin: not for QEMU | part of what [#4714](https://gitlab.com/qemu-project/qemu/-/issues/4714) describes | none |
| 0007 | qtest: am53c974 Select with ATN after a bus reset | wsh-pve | may send | | (with 0001) |
| 0008 | cg3 at any size up to 8 MB | Antoni Sawicki, [LEMU `527b9346`](https://github.com/tenox7/lemu/commit/527b934695b3e2568755606abec7446a356c961b) | LEMU origin: not for QEMU | none ([#2679](https://gitlab.com/qemu-project/qemu/-/issues/2679) asks for 1152x900 on TCX, a different device) | |
| 0009 | cg3 size check overflowed as `int` | Antoni Sawicki, [LEMU `5836ffc3`](https://github.com/tenox7/lemu/commit/5836ffc34929e95d655006dfe38a1bbf756dc839) | LEMU origin: not for QEMU | none found | |
| 0010 | `-vga cg3` / `-g` documentation | Antoni Sawicki, [LEMU `c2c6a828`](https://github.com/tenox7/lemu/commit/c2c6a828a382bca52e7f49fd6500d659d60c6534) | LEMU origin: not for QEMU | | |
| 0011 | sun4m APC maps 1 byte; the firmware says 16 | wsh-pve | may send | none found | [qemu-sun4m-apc-size.md](qemu-sun4m-apc-size.md) |
| 0012, 0013 | SunOS 4.1.4 idle: halt in its idle loop (`sunos-idle`) | Antoni Sawicki, [LEMU `ff3dbc50`](https://github.com/tenox7/lemu/commit/ff3dbc50bcdcbcc346d8742df1e61c1eaf00b3b2), [`fed03cc7`](https://github.com/tenox7/lemu/commit/fed03cc7f5f7c5d6e5e0144bfc1dad36d4844180) | LEMU origin: not for QEMU | a feature, not a bug | |
| 0014-0016 | Solaris 2.5.1-9 idle (`solaris-idle`), with a qtest | wsh-pve, after LEMU's SunOS idle (0012-0013) | built on LEMU: not for QEMU | a feature | |
| 0017, 0018 | sun4m flushes the whole TLB on every change of the SRMMU no-fault bit (SS-5 slow) | wsh-pve | may send | none found | [qemu-srmmu-control-register-flush.md](qemu-srmmu-control-register-flush.md) |
| 0019, 0020 | An interrupt unmasked by `wr %psr` in a delay slot isn't taken (Solaris SMP hang) | wsh-pve | may send | none found | [qemu-sun4m-smp-psr-delay-slot.md](qemu-sun4m-smp-psr-delay-slot.md) |
| 0021, 0022 | cmd646 clears its interrupt status bits when INTRQ drops (Solaris 10 "Interrupt not seen after set_features") | wsh-pve (the `intrq` reset fix carried back from our port to a LEMU fork is a fix to our own patch); same problem fixed differently in [paulsheer/qemu `51d72e16`](https://github.com/paulsheer/qemu/commit/51d72e16), and reported in the 2020 qemu-devel thread "Emulating Solaris 10 on SPARC64 sun4u" | may send | none in the tracker | [qemu-cmd646-interrupt-latch.md](qemu-cmd646-interrupt-latch.md) |
| 0023-0025 | Idle CPUs of multiprocessor Solaris halt (`solaris-smp-idle`), with a qtest | wsh-pve, on the idle framework of 0012-0016 | built on LEMU: not for QEMU | a feature | |
| 0026 | sparc32 `ld`/`st %fsr` with rd other than 0 raise an illegal instruction (old SunOS 4 `_sigtramp`; since 8.2) | Antoni Sawicki, [LEMU `0cdd14c1`](https://github.com/tenox7/lemu/commit/0cdd14c1487c30b14a983db634658fd7a29789b2) | LEMU origin: not for QEMU | none found | [qemu-sparc32-ldfsr-rd.md](qemu-sparc32-ldfsr-rd.md) (a record only) |
| 0027 | qtest `sun4m-fsr-rd-test` for 0026 | wsh-pve | built on LEMU: not for QEMU | | (with 0026) |
| 0028 | CS4231: play sound through the APC DMA engine (the SS-5's codec was a register stub) | Antoni Sawicki, [LEMU `2938ff88`](https://github.com/tenox7/lemu/commit/2938ff887a938b396b44588927bd14f90faa8e0c) | LEMU origin: not for QEMU | none found | none |
| 0029 | sun4m: `audiodev=`, the codec's IOMMU link and interrupt | Antoni Sawicki, [LEMU `42d32575`](https://github.com/tenox7/lemu/commit/42d325754c976b2eda0c7113c42f321a65373af6) | LEMU origin: not for QEMU | | none |
| 0030 | The SS-5's CS4231 at SBus level 5, as on the real machine (Solaris got no interrupt) | wsh-pve, on 0028-0029 | built on LEMU: not for QEMU | | none |
| 0031 | CS4231: no start failure without an audiodev | wsh-pve, on 0028 | built on LEMU: not for QEMU | | none |
| 0032 | CS4231: the last 50 ms of each sound were dropped | wsh-pve, on 0028 | built on LEMU: not for QEMU | | none |
| 0033 | qtest `sun4m-cs4231-test` for 0028-0032 | wsh-pve | built on LEMU: not for QEMU | | none |
| 0034, 0035 | sun4u writes QEMU's default MAC into the IDPROM when the NIC is added with `-device`, so every guest has the same MAC and host id | wsh-pve | may send | none found | [qemu-sun4u-idprom-mac.md](qemu-sun4u-idprom-mac.md) |
| 0036, 0037 | sparc64 `%softint` writes race the tick timers outside the BQL; a lost tick stops illumos's clock | wsh-pve | may send | none found | [qemu-sparc64-softint-race.md](qemu-sparc64-softint-race.md) |
| 0038, 0039 | ESP counts the message out bytes as CDB bytes; a byte-by-byte CDB after SDTR (Linux 2.6.18) is dispatched too early | wsh-pve | may send | none found | [qemu-esp-cdb-ready-after-message-out.md](qemu-esp-cdb-ready-after-message-out.md) |
| 0040, 0041 | ESP raises its interrupt in the instruction that starts a command; NeXTSTEP 3.3 and OPENSTEP 4.2 deadlock in their SCSI driver (reproduced on every install with 11.1.3-2+wsh21 and +wsh22). Our own fix to QEMU's ESP: `irq-latency-us` on `sysbus-esp`, off by default, 500 us for those guests (qemu-server's `esp-irq-latency` machine option) | wsh-pve | may send | [#2620](https://gitlab.com/qemu-project/qemu/-/issues/2620), [#2674](https://gitlab.com/qemu-project/qemu/-/issues/2674) (the freeze; no cause named; #2674's graphics glitches not seen on the 8-bit TCX) | [qemu-esp-irq-latency.md](qemu-esp-irq-latency.md) |
| 0042-0044 | sun4u idle: no guest on QEMU's sun4u can stop the CPU (nothing to emulate: Solaris/illumos halt only through the SPARC64-VI module, NetBSD and Linux only through the sun4v hypervisor, OpenBSD's `sleep` only on CPUs with several strands), so the translator recognises the idle loops of NetBSD 9/11, OpenBSD 8.0, Solaris 9/10 and Tribblix (illumos) and halts there (`idle-halt`), with a qtest | wsh-pve, after LEMU's SunOS idle (0012-0013) | built on LEMU: not for QEMU | a feature | |
| 0045, 0046 | sun4u: a PCI interrupt replaces the sabre's outstanding interrupt request; the CPU drops it while busy, the guest's clear of the first request is ignored, and every OBIO interrupt (IDE, serial console) stays blocked (OpenBSD 8.0 `wd0: timeout`, then a dead guest) | wsh-pve | may send | not searched (added 2026-11-20) | [qemu-sabre-pci-interrupt-replaces-request.md](qemu-sabre-pci-interrupt-replaces-request.md) |
| 0047, 0048 | sun4m: Solaris 2.1 flushes a context whose level 1 table it hasn't filled yet, with traps disabled and from one page of kernel text; QEMU's TLB flush on the context write makes the next fetch fail and QEMU stops (`Trap 0x21 ... while interrupts disabled`). The old context's translation of that page is kept for fetches with traps disabled; qtest `sun4m-mmu-ctx-ifetch-test`. Reproduced on plain QEMU 11.1.3 (the qtest and the 2.1 disk) | wsh-pve | may send | not searched (added 2026-11-20) | [qemu-sparc32-context-switch-ifetch.md](qemu-sparc32-context-switch-ifetch.md) |

Counts: may send 21 (0001, 0007, 0011, 0017-0022, 0034-0041, 0045-0048); LEMU origin 13 (0002-0006,
0008-0010, 0012-0013, 0026, 0028-0029); built on LEMU 14 (0014-0016, 0023-0025, 0027, 0030-0033,
0042-0044).

Not carried, write-up only: the sparc64 TTE page-size bits (32 MB and 256 MB pages), needed for
`niagara` above 1 GB; the patch is by the unix0.cc author
([unix0cc/qemu-experimental-patches](https://github.com/unix0cc/qemu-experimental-patches)).
[qemu-sparc64-tte-page-size.md](qemu-sparc64-tte-page-size.md).

Not carried, write-up only (wsh-pve, may send as a report): on the SS-20, the DBRI stub
(`sun-DBRI.prom`) reads as zeros, Sun's SS-10/SS-20 PROMs make an SBus node without a name for it,
and Solaris 2.1/2.2 panic on that node (`BAD TRAP: type=9` in `get_neighbors`); the lab names it at
the PROM prompt. [qemu-sun4m-ss20-dbri-unnamed-node.md](qemu-sun4m-ss20-dbri-unnamed-node.md).

## OpenBIOS (`openbios/patches/`)

| Patch | Fixes | Author / origin | OpenBIOS | Upstream tracker | Write-up |
| --- | --- | --- | --- | --- | --- |
| 0001 | sparc32: an empty SCSI target probed as present; no `disk` alias | wsh-pve | may send | none found | [openbios-esp-selection-timeout.md](openbios-esp-selection-timeout.md) |
| 0002 | cgthree ROM mapped and drew more than OpenBIOS maps (1152x900 and up) | Antoni Sawicki, [LEMU `9ea85e13`](https://github.com/tenox7/lemu/commit/9ea85e132e43d55422f8d527e9dfc74bca33aa59) | LEMU origin: not for QEMU | none found | none |
| 0003 | sparc64: `/virtual-memory` `available` stops at 0xff000000 | wsh-pve; partly reverts Mark Cave-Ayland's `45b60c8`/`6e3d3fd` | may send | QEMU [#216](https://gitlab.com/qemu-project/qemu/-/issues/216) (Tribblix, "no nucleus hblk8 to allocate") and [#293](https://gitlab.com/qemu-project/qemu/-/issues/293) (Solaris 8, "BOP_ALLOC failed"), both closed as stale without a cause | [openbios-sparc64-virtual-available.md](openbios-sparc64-virtual-available.md) |
| 0004 | sparc64: the CPU node reports the E-cache as the I-cache (Solaris 9 "VAC too big!") | wsh-pve | may send | none found | [openbios-sparc64-icache-properties.md](openbios-sparc64-icache-properties.md) |
| 0005-0007 | sparc64: Forth state at client start breaks Solaris 10's `unix-tte` | wsh-pve | may send | none found | [openbios-sparc64-client-forth-state.md](openbios-sparc64-client-forth-state.md) |
| 0008 | sparc32: Stop-A powers the guest off | wsh-pve | may send | none found | [openbios-sparc32-op-enter-powers-off.md](openbios-sparc32-op-enter-powers-off.md) |
| 0009 | sparc64: node names differ from OBP (`pci@1fe,0`, `su@0`), so Solaris takes no console input | wsh-pve; [paulsheer/openbios `5d7938c2`](https://github.com/paulsheer/openbios/commit/5d7938c2) and [maxinjohn/proxmox-solaris](https://github.com/maxinjohn/proxmox-solaris) name them the same way (read, not copied) | may send | none found | [openbios-sparc64-node-names.md](openbios-sparc64-node-names.md) |
| 0010, 0011 | sparc64: the IDE tree differs from OBP; Solaris 10 can't use its DVD or disk | wsh-pve; paulsheer and maxinjohn flatten the tree differently | may send | none found | [openbios-sparc64-ide-tree.md](openbios-sparc64-ide-tree.md) |
| 0012 (`.wip`, not built) | sparc64: client-interface `boot` should reset the machine | wsh-pve | not ready | none found | none; it hangs when Solaris calls it |
| 0013-0015 | sparc64 with 4 GB of RAM or more: the heap above 4 GB, a `claim` against the firmware's own virtual range, `phys.lo` cut to 32 bits | wsh-pve | may send | none found | [openbios-sparc64-ram-above-4g.md](openbios-sparc64-ram-above-4g.md) |
| 0016 | sparc64: the client interface switches window and trap state with interrupts enabled (Tribblix; Solaris 10's `BAD TRAP: type=4e`) | wsh-pve | may send | none found | [openbios-sparc64-client-interface-interrupts.md](openbios-sparc64-client-interface-interrupts.md) |
| 0017 | sparc64: `xa+`/`xa1+` missing from the 64-bit FCode table, so every token from 0x24a on runs the wrong word (illumos ZFS boot block) | wsh-pve | may send | none found | [openbios-fcode-64bit-token-table.md](openbios-fcode-64bit-token-table.md) |
| 0018 | sparc32: the SS-5's `SUNW,CS4231` node gets `intr` 9, the processor level of its SBus level 5, as in the Sun PROM (`intr 0x39`) | wsh-pve, for QEMU 0030 | built on LEMU: not for QEMU | | none |
| 0019-0022 | sparc32: Solaris 2.1-2.4 don't boot: the FCode boot block's OBP 2.x words, the Forth heap below 0xffd00000 (`can't remove OBP hole`), node 0 as the root in the property calls, romvec calls with interrupts enabled (2.4's idle thread) | wsh-pve | may send | none found | [openbios-sparc32-old-solaris.md](openbios-sparc32-old-solaris.md) |
| 0023 | client interface: `call-method`/`interpret` store the catch result in `args[nargs]` even with `nret` 0, over the client's stack (OpenBSD 8.0's installed sun4u kernel: stack-protector canary after its `map` call) | wsh-pve | may send | none found | none (the patch's message has the evidence) |
| 0024 | sparc64: `/memory` `available` lists partial pages (claims recorded to the byte), and Solaris 7/8/9 panic `boot_alloc: pp is NULL or free` on the last page of such an entry | wsh-pve | may send | none found | [openbios-sparc64-memory-available-pages.md](openbios-sparc64-memory-available-pages.md) |
| 0025 | sparc64: the ebus `fdthree` node has one `reg` entry of size 0 for hardware QEMU's sun4u doesn't have (OBP's has the 82077, the ebus DMA engine and auxio); Solaris 9's `fd` driver panics on it in a reconfiguration boot | wsh-pve | may send | not searched (added 2026-11-19) | [openbios-sparc64-floppy-node.md](openbios-sparc64-floppy-node.md) |
| 0026 | sparc32 framebuffer console: a BEL from the client (Solaris 2.x, SunOS 4.1.4) inverts the screen and hangs the console: `fb8-blink-screen` waits `2000 ms` (hex) on `obp-ticks`, which stops once the client owns the trap table; also one cell left on the data stack per BEL | wsh-pve | may send | none found (searched 2026-11-20) | [openbios-fb8-blink-screen-hangs-client-console.md](openbios-fb8-blink-screen-hangs-client-console.md) |

Counts: may send 23 (0001, 0003-0011, 0013-0017, 0019-0026), LEMU origin 1 (0002), built on LEMU 1
(0018), not ready 1 (0012, `.wip`). 0018 is our code, but it exists only for QEMU 0030's wiring of LEMU's CS4231
(upstream QEMU's codec is a stub that never interrupts), so it goes with the audio patches.

## Hold: QEMU bugs seen only with LEMU code in the build

Reportable only after they have been reproduced on plain QEMU, without any LEMU patch:

| What | Seen with | Notes |
| --- | --- | --- |
| QEMU's audio mixer doubles a mono voice played into a mono output (it adds left and right): a `wav` audiodev with `out.channels=1` is 6 dB too loud | LEMU's CS4231 (0028-0029) | `submodules/SPARC.md` "Audio"; needs a device without LEMU code that plays a mono voice |
| The `wav` audio backend leaves the header's sizes at 0 when the guest powers the machine off | LEMU's CS4231 (0028-0029) | the same |
| A serial BREAK on ttya hangs Solaris: QEMU's ESCC sets RR0's break bit and never clears it | ESCC with LEMU's 0002-0006 | `submodules/SPARC.md` "Stop-A"; the code read is QEMU's own `serial_receive_break()`, but the lab binary had LEMU's ESCC patches |
| `zs3: ring buffer overflow` under load: mouse data arrives faster than a 1200 baud mouse sends it | ESCC with LEMU's 0002-0006 | `ROADMAP.md` known issues; harmless |

## Open upstream issues that match what the lab sees, not fixed here

| Issue | What | Here |
| --- | --- | --- |
| [#3263](https://gitlab.com/qemu-project/qemu/-/issues/3263) | SS-20 doesn't report SMP to Sun's PROM | Same finding: OBP 2.25 sees one CPU (`SPARC.md`, "SMP") |
| [#3265](https://gitlab.com/qemu-project/qemu/-/issues/3265) | SS-10 can't boot OBP 2.25R | Not tried |
| [#2723](https://gitlab.com/qemu-project/qemu/-/issues/2723) (closed), [#2015](https://gitlab.com/qemu-project/qemu/-/issues/2015), [#3038](https://gitlab.com/qemu-project/qemu/-/issues/3038) | `Trap 0x29 (Data Access Error) while interrupts disabled` | The SunOS 4.1.4 install kernel with 256 MB; the install target uses 64 MB |
| [#2534](https://gitlab.com/qemu-project/qemu/-/issues/2534) | Solaris can't be powered off with `system_powerdown` on sun4m | Not checked against PVE's shutdown |
| [#597](https://gitlab.com/qemu-project/qemu/-/issues/597) | `sunhme` sometimes hangs the VM | Not seen |
| [#1163](https://gitlab.com/qemu-project/qemu/-/issues/1163), [#2017](https://gitlab.com/qemu-project/qemu/-/issues/2017) | Solaris 2.2 doesn't boot; Solaris 2.4 with the Sun PROM times out | Not tried |
| [#260](https://gitlab.com/qemu-project/qemu/-/issues/260) | `-M sun4v` aborts on a Tribblix ISO | `niagara`/sun4v parked |
| [#3147](https://gitlab.com/qemu-project/qemu/-/issues/3147) | Solaris 11.4 detects sigsetjmp/siglongjmp between threads | Solaris 11 not run here |

Seen in the lab, not in any tracker and not fixed: OpenBIOS drops the boot string of
`reboot -- <args>` on sparc32. Since the first version of this index, NetBSD on sun4u with 4 GB
and more is fixed by OpenBIOS 0013-0015 and the sun4u IDPROM MAC by QEMU 0034; the serial BREAK
hang is under "Hold" above.
