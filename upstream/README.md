# Fixes, their authors and the upstream trackers

An index of the QEMU and OpenBIOS patches this repository carries, who wrote each, and where the
same problem shows up upstream. It exists so the state can be compared again later: what upstream
has fixed meanwhile, which threads a write-up could help, and what is still only here.

Checked on 2026-11-17 against:

- QEMU's tracker, [gitlab.com/qemu-project/qemu/-/issues](https://gitlab.com/qemu-project/qemu/-/issues)
  (searched titles and descriptions for the device, register and symptom names below);
- OpenBIOS's tracker, [github.com/openbios/openbios/issues](https://github.com/openbios/openbios/issues)
  (12 open issues; none of the problems below);
- the compatibility table of the [QEMU SPARC wiki page](https://wiki.qemu.org/Documentation/Platforms/SPARC)
  (last edited 2025-06-02).

The mailing lists (qemu-devel, openbios) were not searched.

QEMU and OpenBIOS don't take AI-generated code. The write-ups in this directory are bug reports a
person can send; the patches stay here. LEMU's author has said LEMU's code won't be sent to QEMU
either.

## Who wrote what

| Author | Where their work lives | Tracker |
| --- | --- | --- |
| Antoni Sawicki (LEMU) | [github.com/tenox7/lemu](https://github.com/tenox7/lemu), a QEMU fork for vintage machines (GPL-2.0) | [tenox7/lemu issues](https://github.com/tenox7/lemu/issues) |
| wsh-pve (this repository) | `submodules/pve-qemu.patch` (`debian/patches/wsh/`), `openbios/patches/` | this repository's issues |

Each carried patch keeps its author in its `From:` line, and LEMU's have an `Origin:` line with the
commit. Details of each fix are in [`submodules/SPARC.md`](../submodules/SPARC.md).

## QEMU (`debian/patches/wsh/` in pve-qemu-kvm)

| Patch | Fixes | Author / origin | Upstream tracker | Write-up |
| --- | --- | --- | --- | --- |
| 0001 | ESP rejects Select with ATN after a SCSI bus reset | wsh-pve | none found | [qemu-esp-bus-reset.md](qemu-esp-bus-reset.md) |
| 0002 | ESCC: RR2/RR3 name the wrong channel when both have an interrupt; each channel's line showed both channels' state, so the other line stayed raised | Antoni Sawicki, [LEMU `699cc89f`](https://github.com/tenox7/lemu/commit/699cc89f715c89caa96dabdd5ce8bc092951c21a) | [QEMU #4714](https://gitlab.com/qemu-project/qemu/-/issues/4714) (open, 2026-10-18): the stale line, found independently on a Linux SS-20; it doesn't cover RR2/RR3 | none |
| 0003 | ESCC: every second Caps Lock/Num Lock press lost; host key repeat on top of the guest's | Antoni Sawicki, [LEMU `c31ed88b`](https://github.com/tenox7/lemu/commit/c31ed88ba67130c06731ddbe0a73296c6164f688) | none found | none |
| 0004 | ESCC: a full queue cut a Sun mouse packet in half | Antoni Sawicki, [LEMU `181f0f52`](https://github.com/tenox7/lemu/commit/181f0f520875f5ec2d2574e28093468e689dbe6a) | none found ([#2518](https://gitlab.com/qemu-project/qemu/-/issues/2518), "vertical mouse leaps", is closed and about something else) | none |
| 0005 | qtest `sun4m-escc-test` for 0002-0004, 0006 | Antoni Sawicki, [LEMU `c7a18569`](https://github.com/tenox7/lemu/commit/c7a18569f2b54fd146f325b7499b89216c7865d4) | | |
| 0006 | ESCC: the line stayed raised after the guest reset a channel | Antoni Sawicki, [LEMU `c2c2781e`](https://github.com/tenox7/lemu/commit/c2c2781eb91ab837e4b8a9c3ae972c3fdd007f34) | part of what [#4714](https://gitlab.com/qemu-project/qemu/-/issues/4714) describes | none |
| 0007 | qtest: am53c974 Select with ATN after a bus reset | wsh-pve | | (with 0001) |
| 0008 | cg3 at any size up to 8 MB | Antoni Sawicki, [LEMU `527b9346`](https://github.com/tenox7/lemu/commit/527b934695b3e2568755606abec7446a356c961b) | none ([#2679](https://gitlab.com/qemu-project/qemu/-/issues/2679) asks for 1152x900 on TCX, a different device) | |
| 0009 | cg3 size check overflowed as `int` | Antoni Sawicki, [LEMU `5836ffc3`](https://github.com/tenox7/lemu/commit/5836ffc34929e95d655006dfe38a1bbf756dc839) | none found | |
| 0010 | `-vga cg3` / `-g` documentation | Antoni Sawicki, [LEMU `c2c6a828`](https://github.com/tenox7/lemu/commit/c2c6a828a382bca52e7f49fd6500d659d60c6534) | | |
| 0011 | sun4m APC maps 1 byte; the firmware says 16 | wsh-pve | none found | [qemu-sun4m-apc-size.md](qemu-sun4m-apc-size.md) |
| 0012, 0013 | SunOS 4.1.4 idle: halt in its idle loop (`sunos-idle`) | Antoni Sawicki, [LEMU `ff3dbc50`](https://github.com/tenox7/lemu/commit/ff3dbc50bcdcbcc346d8742df1e61c1eaf00b3b2), [`fed03cc7`](https://github.com/tenox7/lemu/commit/fed03cc7f5f7c5d6e5e0144bfc1dad36d4844180) | a feature, not a bug | |
| 0014-0016 | Solaris 2.5.1-9 idle (`solaris-idle`), with a qtest | wsh-pve, after LEMU's SunOS idle | a feature | |
| 0017, 0018 | sun4m flushes the whole TLB on every change of the SRMMU no-fault bit (SS-5 slow) | wsh-pve | none found | [qemu-srmmu-control-register-flush.md](qemu-srmmu-control-register-flush.md) |
| 0019, 0020 | An interrupt unmasked by `wr %psr` in a delay slot isn't taken (Solaris SMP hang) | wsh-pve | none found | [qemu-sun4m-smp-psr-delay-slot.md](qemu-sun4m-smp-psr-delay-slot.md) |
| 0021, 0022 | cmd646 clears its interrupt status bits when INTRQ drops (Solaris 10 "Interrupt not seen after set_features") | wsh-pve; same problem fixed differently in [paulsheer/qemu `51d72e16`](https://github.com/paulsheer/qemu/commit/51d72e16), and reported in the 2020 qemu-devel thread "Emulating Solaris 10 on SPARC64 sun4u" | none in the tracker | [qemu-cmd646-interrupt-latch.md](qemu-cmd646-interrupt-latch.md) |
| 0023-0025 | Idle CPUs of multiprocessor Solaris halt (`solaris-smp-idle`), with a qtest | wsh-pve | a feature | |

Not carried, write-up only: the sparc64 TTE page-size bits (32 MB and 256 MB pages), needed for
`niagara` above 1 GB; the patch is by the unix0.cc author
([unix0cc/qemu-experimental-patches](https://github.com/unix0cc/qemu-experimental-patches)).
[qemu-sparc64-tte-page-size.md](qemu-sparc64-tte-page-size.md).

## OpenBIOS (`openbios/patches/`)

| Patch | Fixes | Author / origin | Upstream tracker | Write-up |
| --- | --- | --- | --- | --- |
| 0001 | sparc32: an empty SCSI target probed as present; no `disk` alias | wsh-pve | none found | [openbios-esp-selection-timeout.md](openbios-esp-selection-timeout.md) |
| 0002 | cgthree ROM mapped and drew more than OpenBIOS maps (1152x900 and up) | Antoni Sawicki, [LEMU `9ea85e13`](https://github.com/tenox7/lemu/commit/9ea85e132e43d55422f8d527e9dfc74bca33aa59) | none found | none |
| 0003 | sparc64: `/virtual-memory` `available` stops at 0xff000000 | wsh-pve; partly reverts Mark Cave-Ayland's `45b60c8`/`6e3d3fd` | QEMU [#216](https://gitlab.com/qemu-project/qemu/-/issues/216) (Tribblix, "no nucleus hblk8 to allocate") and [#293](https://gitlab.com/qemu-project/qemu/-/issues/293) (Solaris 8, "BOP_ALLOC failed"), both closed as stale without a cause | [openbios-sparc64-virtual-available.md](openbios-sparc64-virtual-available.md) |
| 0004 | sparc64: the CPU node reports the E-cache as the I-cache (Solaris 9 "VAC too big!") | wsh-pve | none found | [openbios-sparc64-icache-properties.md](openbios-sparc64-icache-properties.md) |
| 0005-0007 | sparc64: Forth state at client start breaks Solaris 10's `unix-tte` | wsh-pve | none found | [openbios-sparc64-client-forth-state.md](openbios-sparc64-client-forth-state.md) |
| 0008 | sparc32: Stop-A powers the guest off | wsh-pve | none found | [openbios-sparc32-op-enter-powers-off.md](openbios-sparc32-op-enter-powers-off.md) |
| 0009 | sparc64: node names differ from OBP (`pci@1fe,0`, `su@0`), so Solaris takes no console input | wsh-pve; [paulsheer/openbios `5d7938c2`](https://github.com/paulsheer/openbios/commit/5d7938c2) and [maxinjohn/proxmox-solaris](https://github.com/maxinjohn/proxmox-solaris) name them the same way (read, not copied) | none found | [openbios-sparc64-node-names.md](openbios-sparc64-node-names.md) |
| 0010, 0011 | sparc64: the IDE tree differs from OBP; Solaris 10 can't use its DVD or disk | wsh-pve; paulsheer and maxinjohn flatten the tree differently | none found | [openbios-sparc64-ide-tree.md](openbios-sparc64-ide-tree.md) |
| 0012 (`.wip`, not built) | sparc64: client-interface `boot` should reset the machine | wsh-pve | none found | none; it hangs when Solaris calls it |

## Open upstream issues that match what the lab sees, not fixed here

| Issue | What | Here |
| --- | --- | --- |
| [#3263](https://gitlab.com/qemu-project/qemu/-/issues/3263) | SS-20 doesn't report SMP to Sun's PROM | Same finding: OBP 2.25 sees one CPU (`SPARC.md`, "SMP") |
| [#3265](https://gitlab.com/qemu-project/qemu/-/issues/3265) | SS-10 can't boot OBP 2.25R | Not tried |
| [#2723](https://gitlab.com/qemu-project/qemu/-/issues/2723) (closed), [#2015](https://gitlab.com/qemu-project/qemu/-/issues/2015), [#3038](https://gitlab.com/qemu-project/qemu/-/issues/3038) | `Trap 0x29 (Data Access Error) while interrupts disabled` | The SunOS 4.1.4 install kernel with 256 MB; the install target uses 64 MB |
| [#2534](https://gitlab.com/qemu-project/qemu/-/issues/2534) | Solaris can't be powered off with `system_powerdown` on sun4m | Not checked against PVE's shutdown |
| [#597](https://gitlab.com/qemu-project/qemu/-/issues/597) | `sunhme` sometimes hangs the VM | Not seen |
| [#1163](https://gitlab.com/qemu-project/qemu/-/issues/1163), [#2017](https://gitlab.com/qemu-project/qemu/-/issues/2017) | Solaris 2.2 doesn't boot; Solaris 2.4 with the Sun PROM times out | Not tried |
| [#2620](https://gitlab.com/qemu-project/qemu/-/issues/2620), [#2674](https://gitlab.com/qemu-project/qemu/-/issues/2674) | NeXTSTEP/OPENSTEP for SPARC freeze while installing; graphics glitches | Not tried |
| [#260](https://gitlab.com/qemu-project/qemu/-/issues/260) | `-M sun4v` aborts on a Tribblix ISO | `niagara`/sun4v parked |
| [#3147](https://gitlab.com/qemu-project/qemu/-/issues/3147) | Solaris 11.4 detects sigsetjmp/siglongjmp between threads | Solaris 11 not run here |

Seen in the lab, not in any tracker and not fixed: a serial BREAK hangs Solaris (the ESCC never
ends a break), every sun4u guest gets the IDPROM MAC 52:54:00:12:34:56 (a NIC added with `-device`
isn't seen by `sun4u.c`), OpenBIOS drops the boot string of `reboot -- <args>` on sparc32, and NetBSD
on sun4u with 4096 MB panics in a firmware `claim` (8192 MB: OpenBIOS out of malloc memory).
