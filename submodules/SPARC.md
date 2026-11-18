# sparc patches

Everything wsh-pve changes to run sparc (32-bit, `arch: sparc`) and sparc64 guests, by
component. The user guide is `docs/src/content/docs/guides/sparc.mdx`; this file is for whoever
maintains the patches.

| Component | Where | What |
| --- | --- | --- |
| QEMU | `submodules/pve-qemu.patch` | sparc targets, firmware, machine lists, QEMU fixes as quilt patches |
| Sun PROMs | `submodules/sparc` (private) | `ss5.bin`, `ss10_v2.25_rom`, `ss20_v2.25_rom` |
| qemu-server | `submodules/qemu-server.patch` | the sparc command line |
| pve-manager | `submodules/pve-manager.patch` | architecture choice and sparc options in the UI |

## QEMU (pve-qemu)

### Build changes

- `debian/rules`: `--target-list` adds `sparc-softmmu,sparc64-softmmu`, so `pve-qemu-kvm` ships
  `qemu-system-sparc` and `qemu-system-sparc64`. It writes `machine-versions-sparc.json` and
  `machine-versions-sparc64.json` from `-machine help`. It doesn't strip the OpenBIOS images.
- `Makefile`: `openbios-sparc32` and `openbios-sparc64` are no longer purged from the firmware.
- `debian/parse-machines.pl`: it also lists `sun4*` (`sun4u`, ...) and `SS-*` (`SS-5`, ...),
  with type `sun`.
- `debian/pve-qemu-kvm.lintian-overrides`: overrides for the OpenBIOS images (sparc binaries in
  `/usr/share/kvm`).
- `debian/rules` also copies the Sun PROMs from `submodules/sparc` to `/usr/share/kvm`. They are
  optional and left out when missing (by design: the build never fails on them); `restore-sparc`
  then prints `WARNING: optional extra sun-proms missing: ...` and the build reports it (see
  "Optional extras" in the README).

### QEMU fixes (`debian/patches/wsh/`)

| Patch | Fixes | Origin | Upstream |
| --- | --- | --- | --- |
| `0001-esp.c-return-to-disconnected-mode-on-SCSI-bus-reset` | After a SCSI bus reset the ESP rejected Select with ATN. Solaris 2.5.1 looped on "gross error in esp status" and couldn't boot its CD (QEMU 10.1 and later) | ours (#196) | not fixed; first bad commit `6f8ce26bb0`, see `upstream/qemu-esp-bus-reset.md` |
| `0002-hw-char-escc-name-the-right-interrupt-when-both-chan` | sun4m keyboard and mouse share one ESCC. With a key and a mouse byte pending together RR2 named the wrong channel: the pointer jumped, or the guest hung until the next key (Shift held while moving the mouse) | [LEMU `699cc89f`](https://github.com/tenox7/lemu/commit/699cc89f715c89caa96dabdd5ce8bc092951c21a) (#222) | not in QEMU |
| `0003-hw-char-escc-make-the-Sun-keyboard-s-lock-keys-and-k` | Every second Caps Lock/Num Lock press was lost; host key repeat came on top of the guest's own | [LEMU `c31ed88b`](https://github.com/tenox7/lemu/commit/c31ed88ba67130c06731ddbe0a73296c6164f688) (#222) | not in QEMU |
| `0004-hw-char-escc-keep-the-Sun-mouse-in-step-when-the-gue` | A full queue cut a mouse packet in half | [LEMU `181f0f52`](https://github.com/tenox7/lemu/commit/181f0f520875f5ec2d2574e28093468e689dbe6a) (#222) | not in QEMU |
| `0005-tests-qtest-test-the-Sun-keyboard-and-mouse-on-one-e` | qtest `sun4m-escc-test` for 0002-0004 and 0006 (`meson.build` context adapted to 11.1.3) | [LEMU `c7a18569`](https://github.com/tenox7/lemu/commit/c7a18569f2b54fd146f325b7499b89216c7865d4) (#222) | not in QEMU |
| `0006-hw-char-escc-lower-the-interrupt-when-the-guest-rese` | The interrupt line stayed raised after the guest reset a channel | [LEMU `c2c2781e`](https://github.com/tenox7/lemu/commit/c2c2781eb91ab837e4b8a9c3ae972c3fdd007f34) (#222) | not in QEMU |
| `0007-tests-qtest-am53c974-check-that-Select-with-ATN-work` | qtest for 0001 in `am53c974-test.c` (i386 only, not run by the x86_64 build) | ours (#223, open) | |
| `0008-hw-display-cg3-take-screens-of-any-size-up-to-8-MB` | The cg3 took 1024x768 and 1152x900 only (and 1152x900 crashed OpenBIOS). `-g` now takes 640x480 up to 8 MB of pixels with a width that 8 divides; the video RAM grows with it (1 MB at least) | [LEMU `527b9346`](https://github.com/tenox7/lemu/commit/527b934695b3e2568755606abec7446a356c961b) | not in QEMU |
| `0009-hw-sparc-sun4m-refuse-a-cg3-size-too-big-to-multiply` | The size check multiplied as `int`: `-g 65536x65536x8` wrapped to 0 and QEMU aborted allocating the video RAM | [LEMU `5836ffc3`](https://github.com/tenox7/lemu/commit/5836ffc34929e95d655006dfe38a1bbf756dc839) | not in QEMU |
| `0010-qemu-options-say-which-screen-sizes-the-cg3-takes` | `-vga cg3` and `-g` documentation | [LEMU `c2c6a828`](https://github.com/tenox7/lemu/commit/c2c6a828a382bca52e7f49fd6500d659d60c6534) | not in QEMU |
| `0011-hw-misc-slavio_misc-give-the-sun4m-APC-its-16-bytes-` | The power management (APC) region was 1 byte; the firmware's node says 16. Solaris 2.6's `pmc` driver writes offsets 2-0xc at attach and panicked (`kernel write fault at addr=0x6a000002`). Now 16 bytes: offset 0 halts the CPU as before, the others keep their value; vmstate section only when one is set. Adds qtest `sun4m-apc-test` | ours | not fixed (1 byte in every QEMU release); see `upstream/qemu-sun4m-apc-size.md` |
| `0012-target-sparc-halt-the-CPU-in-the-SunOS-4.1.4-idle-lo` | SunOS 4.1.4 spins in its idle loop; the translator recognises the loop and halts the CPU there until the next interrupt | [LEMU `ff3dbc50`](https://github.com/tenox7/lemu/commit/ff3dbc50bcdcbcc346d8742df1e61c1eaf00b3b2) | not in QEMU |
| `0013-hw-sparc-sun4m-add-the-sunos-idle-option-on-by-defau` | `-M <sun4m>,sunos-idle=on\|off` for 0012, on by default, off with `-smp` > 1 | [LEMU `fed03cc7`](https://github.com/tenox7/lemu/commit/fed03cc7f5f7c5d6e5e0144bfc1dad36d4844180) | not in QEMU |
| `0014-target-sparc-halt-the-CPU-in-the-Solaris-idle-loop` | Solaris 2.5.1-9 spin in `idle()` on every CPU module but the microSPARC-II with `pmc` (SS-10/SS-20 always); the translator recognises the call of `idle_cpu` in that loop and halts the CPU there until the next interrupt when `disp_nrunnable` is 0 | ours | not in QEMU |
| `0015-hw-sparc-sun4m-add-the-solaris-idle-option-on-by-def` | `-M <sun4m>,solaris-idle=on\|off` for 0014, on by default, off with `-smp` > 1 | ours | not in QEMU |
| `0016-tests-qtest-test-the-Solaris-idle-halt-on-sun4m` | qtest `sun4m-solaris-idle-test` for 0014-0015 | ours | not in QEMU |
| `0017-target-sparc-flush-the-TLB-on-a-no-fault-bit-change-` | Solaris on SS-5 ran call-heavy user code 4-10x slower than on SS-20: its microSPARC window-trap handlers set and clear the MMU no-fault bit (NF) twice per trap, and QEMU flushed its whole TLB on every NF change. Now NF flushes only while the TLB holds an entry made for a fault in no-fault mode (the only entries that depend on it); boot mode flushes as before. Trace event `sparc_mmu_ctrl_flush` ("Why SS-5 was slower", "Benchmarks") | ours | not fixed; see `upstream/qemu-srmmu-control-register-flush.md` |
| `0018-tests-qtest-test-no-fault-mode-and-the-TLB-on-sun4m` | qtest `sun4m-mmu-nofault-test` for 0017: an entry made in no-fault mode must not survive NF being cleared (SS-5 and SS-20) | ours | not in QEMU |
| `0019-target-sparc-let-a-write-to-psr-in-a-delay-slot-end-` | Solaris 2.x with more than one CPU (SS-10/SS-20) hung within minutes: a write to `%psr` in a delay slot (Solaris's `splx`) didn't end the translation block, so an interrupt it unmasked wasn't taken until something else stopped the CPU; a CPU spinning in such a loop never took the other CPU's cross-call ("SMP") | ours | not fixed (since 8.2.0, `25524734c6`); see `upstream/qemu-sun4m-smp-psr-delay-slot.md` |
| `0020-tests-qtest-test-an-interrupt-let-in-from-a-delay-sl` | qtest `sun4m-pil-delay-slot-test` for 0019: a pending soft interrupt must be taken after PIL is lowered by a plain `wr %psr` and by one in the delay slot of `ba`, `bne`, `bne,a` and `jmpl` | ours | not in QEMU |
| `0021-ide-cmd646-latch-the-interrupt-status-bits-until-the` | The cmd646 (sun4u's built-in IDE) cleared its interrupt status bits (MRDMODE, CFR, ARTTIM23) when the drive dropped INTRQ, i.e. when the guest read the drive's status. Solaris 10 reads the status and then polls those bits: `WARNING: Interrupt not seen after set_features` for every IDE device. Now they stay set until the guest writes 1 to clear them; the PCI interrupt line keeps following INTRQ (driving it from the latched bits broke Linux and OpenBSD) ("Solaris on sun4u") | ours | not fixed; see `upstream/qemu-cmd646-interrupt-latch.md` |
| `0022-tests-qtest-test-the-cmd646-interrupt-status-latch-o` | qtest `sun4u-cmd646-test` for 0021: after SET FEATURES and a status read the bits stay set until written 1, and the interrupt line (seen through the sabre) follows INTRQ | ours | not in QEMU |
| `0023-target-sparc-halt-idle-CPUs-in-the-Solaris-multiproc` | With 2-4 CPUs every idle vCPU of Solaris 2.5.1-9 spun at 100% of a host core: the multiprocessor idle loop never calls `idle_cpu`, and nothing tells an idle CPU that it has work. The translator recognises the call of `disp_getwork` in that loop and halts the CPU there; the halt ends when another CPU queues work for it (checked on its next `wr %psr`), on an interrupt, or after 10 ms. The Solaris idle helpers read `disp_nrunnable` through a page table walk instead of `probe_access_flags()`, which asserts when another CPU has flushed the TLB entry ("SMP", "Idle with more than one CPU") | ours | not in QEMU |
| `0024-hw-sparc-sun4m-add-the-solaris-smp-idle-option-on-by` | `-M <sun4m>,solaris-smp-idle=on\|off` for 0023, on by default, does nothing with one CPU | ours | not in QEMU |
| `0025-tests-qtest-test-the-Solaris-multiprocessor-idle-hal` | qtest `sun4m-solaris-smp-idle-test` for 0023-0024 | ours | not in QEMU |
| `0026-target-sparc-let-sparc32-ld-and-st-fsr-ignore-rd` | sparc32 raised an illegal instruction trap for `ld [..], %fsr` and `st %fsr, [..]` with rd other than 0; V7 and V8 chips ignore rd there. The `_sigtramp` of an old static SunOS 4 libc saves and restores the FSR with rd 4 (`c92ba0e0`, `c90ba0e0`), so such programs died with SIGILL at their first signal after using the FPU (LEMU's case: Island Productivity's 1992 licence daemon `islandLIC`). sparc32 takes any rd again, as before QEMU 8.2; sparc64 doesn't change | [LEMU `0cdd14c1`](https://github.com/tenox7/lemu/commit/0cdd14c1487c30b14a983db634658fd7a29789b2) by Antoni Sawicki | not fixed (since 8.2.0, `3d3c06737b`); see `upstream/qemu-sparc32-ldfsr-rd.md` |
| `0027-tests-qtest-test-ld-and-st-fsr-with-any-rd-on-sun4m` | qtest `sun4m-fsr-rd-test` for 0026: `ld %fsr` and `st %fsr` with rd 0, 4 (the exact words above) and 31 run without a trap and the FSR reads back | ours | not in QEMU |
| `0028-hw-audio-cs4231-play-sound-through-the-apc-dma-engin` | The SS-5's CS4231 was a register stub: its APC DMA kept what was written and never interrupted, so every program that waited for the end of a sound on `/dev/audio` hung (SunOS 4.1.4). The APC now plays its playback buffers, read through the IOMMU, into the machine's audiodev at the codec's rate (u-law, A-law, 8-bit, 16-bit LE and BE; ADPCM plays silence), with PI, PD, PM and PMI and the DAC volume. Capture is not done: the capture pipe reads as empty ("Audio") | [LEMU `2938ff88`](https://github.com/tenox7/lemu/commit/2938ff887a938b396b44588927bd14f90faa8e0c) by Antoni Sawicki | not in QEMU |
| `0029-hw-sparc-sun4m-give-the-cs4231-its-interrupt-level-i` | The machine side of 0028: `-machine audiodev=` on sun4m, the codec's IOMMU link, and its interrupt on bit 9 (processor level 5, OpenBIOS's `intr` 5; 0030 moves it) | [LEMU `42d32575`](https://github.com/tenox7/lemu/commit/42d325754c976b2eda0c7113c42f321a65373af6) by Antoni Sawicki | not in QEMU |
| `0030-hw-sparc-sun4m-raise-the-SS-5-s-cs4231-at-SBus-level` | The real SS-5 has the codec at SBus level 5, processor level 9 (`ss5.bin` 2.15 gives the node `intr 0x39`). On bit 9, Solaris, which takes OpenBIOS's `interrupts 5`, never got its interrupt: audioplay stopped after the first second with `processor level 3 SBus interrupt not serviced`. Now SBus level 5 (bit 11), through an OR gate with the cg3 or TCX, which use that level too. Needs openbios patch 0016 for SunOS 4 | ours | not in QEMU (upstream wires the stub to bit 5, processor level 11) |
| `0031-hw-audio-cs4231-no-sound-without-an-audiodev` | With 0028 an SS-5 without `-machine audiodev` asked for QEMU's default audio driver, and with none available didn't start (`no default audio driver available`). Without an audiodev the codec now opens no voice and keeps its registers only, as before (the PC speaker does the same) | ours | — |
| `0032-hw-audio-cs4231-play-out-the-last-samples-when-playb` | The APC takes its samples up to 50 ms ahead of the codec's clock; turning the voice off when the pipe ran empty or the driver stopped the DMA dropped what the mixer still held, so every sound lost its last 50 ms. The voice stays on for 200 ms after playback stops | ours | — |
| `0033-tests-qtest-test-CS4231-playback-through-the-APC-DMA` | qtest `sun4m-cs4231-test` for 0028-0032: two u-law buffers behind IOMMU mappings, PEN, PI/PD/PM/PMI at SBus level 5 (processor level 9) in real time, every sample decoded in a `wav` audiodev; DMA off and the reset bit | ours | not in QEMU |

The ESCC, cg3, SunOS idle, `%fsr` (0026) and CS4231 sound (0028-0029) patches are by Antoni Sawicki, from [LEMU](https://github.com/tenox7/lemu), a QEMU
fork for vintage machines (GPLv2, like QEMU). LEMU states that its code won't be sent to QEMU, so we
carry it ourselves. Each patch keeps its author and has an `Origin:` line.

Tested: `sun4m-escc-test` fails without 0002-0006 and passes 4/4 with them on 11.1.3;
`test_select_after_bus_reset_ok` fails from `6f8ce26bb0` through 11.1.3 and passes with 0001.
The full series (Proxmox's patches + ours) applies on QEMU 11.1.3; no Proxmox patch touches
`esp.c` or `escc.c`.

0008-0010 and 0012-0013 applied to 11.1.3 with line offsets only (LEMU is on QEMU master).
`sun4m-apc-test` fails without 0011 (the region is 1 byte, register 2 doesn't read back) and passes
5/5 with it. `sun4m-solaris-idle-test` passes 5/5 with 0014-0016 (its `idle` case is the `off` case
inverted: without the halt the loop keeps counting). `sun4m-mmu-nofault-test` passes 2/2 on 11.1.3
with and without 0017, and fails with NF simply dropped from the flush condition (no flag): the
store after NF is cleared goes through the stale entry instead of trapping. With 0001-0018,
`make check-qtest-sparc` (sparc-softmmu only): 18 OK, 2 skipped, `qmp-test` fails in
`/sparc/qmp/oob` (no `oob` capability), the same with 0001-0016. The lab matrices `smoke` (3),
`idle` (10), `machines` (13) and `display` (20) passed with 0017 (a `qemu-system-sparc` built from
the series, mounted into the lab image). `sun4m-pil-delay-slot-test` passes 5/5 with 0019; without
it its four delay-slot cases fail (the plain one passes). With 0001-0020: `make check-qtest-sparc`
19 OK, 2 skipped, the same `qmp-test` failure; the lab matrices `smoke` (3/3), `idle` (10/10),
`machines` (13/13), `display` (20/20) and `benchdisk` (6/6) passed, and the `smp` cases under
"SMP".

0021 applies to 11.1.3 on top of 0001-0020 with fuzz 0. `sun4u-cmd646-test` (run as
`QTEST_QEMU_BINARY=./qemu-system-sparc64 tests/qtest/sun4u-cmd646-test` in a sparc64-softmmu build)
passes 2/2 with 0021; without it `status-latched` fails (MRDMODE reads 0 after the status read),
and with the interrupt line driven from the latched bits (the variant that broke Linux and OpenBSD)
it fails too (the line stays up after the status read). `boot-serial-test` and `prom-env-test`
(sparc64) pass with it. Of the binaries in the package only `qemu-system-sparc64` contains the
cmd646 (sun4u's built-in IDE; QEMU's alpha and hppa machines have one too, and aren't built here):
`CONFIG_IDE_CMD646` is selected by those machines only, so `qemu-system-x86_64`, `-i386`,
`-aarch64`, `-arm`, `-sparc` and the 3dfx binary have no `cmd646-ide` device and no x86 machine
type can use it. Lab results under "Solaris on sun4u".

0023-0025 apply on top of 0001-0022. `sun4m-solaris-smp-idle-test` passes 4/4 with them; with
the binary built without them its `idle` case fails (15,098,675 rounds in 300 ms instead of fewer
than 300). An early version of 0023 that went on at the call after a timer wake halted again
before `disp_getwork` ran, so the timer never let the CPU look for work: the test's `idle` case
caught it (0 rounds). `sun4m-solaris-idle-test` passes 5/5 with 0023 (the read of
`disp_nrunnable` changed under it). With 0001-0025, `make check-qtest-sparc`: 20 OK, 2 skipped, the
same `qmp-test` failure. Lab results under "SMP".

0026 is LEMU's change without its `machines/sun4m/README.md` hunk; it applies to 11.1.3 on top of
0001-0025 with line offsets only. `sun4m-fsr-rd-test` passes 3/3 with it; without it the `rd4`
case fails with trap type 2 (illegal instruction) and `rd0` passes. With 0001-0027,
`make check-qtest-sparc`: 21 OK, 2 skipped, the same `qmp-test` failure;
`make check-qtest-sparc64`: 15 OK (`sun4u-cmd646-test` 2/2 among them), 2 skipped, and `qmp-test`
fails in `/sparc64/qmp/oob` the same way.

0028 and 0029 are LEMU's commits unchanged: they apply to 11.1.3 on top of 0001-0027 without fuzz.
0030-0033 are ours, from the lab ("Audio"). `sun4m-cs4231-test` passes 2/2 with 0028-0033; without
0032 its playback case fails (1200 of the 1600 samples reach the wav file). With 0001-0033 the
`qtest-sparc` and `qtest-sparc64` suites: 37 OK, 4 skipped, and the two `qmp-test` `oob` failures
as before; every sun4m qtest above passes, and an SS-5 without an audiodev starts.

When pve-qemu moves to a new QEMU: check each patch still applies, drop any that upstream has
taken, and run `sun4m-escc-test`, `sun4m-apc-test`, `sun4m-solaris-idle-test`,
`sun4m-mmu-nofault-test`, `sun4m-pil-delay-slot-test`, `sun4m-solaris-smp-idle-test` and
`sun4m-fsr-rd-test` and `sun4m-cs4231-test` (sparc),
`sun4u-cmd646-test` (sparc64) and `am53c974-test` (i386).

### QEMU 7.2

The package used to carry an extra `qemu-system-sparc-7.2` build (`pve-qemu-7.2-sparc.patch`, the
`pve-qemu-7.2-sparc` make target), which qemu-server never selected. With the ESP and ESCC fixes
the current QEMU runs the sparc guests, so it was removed; it is in the git history. For
comparisons, `e2e/sparc/qemu-7.2.Dockerfile` builds upstream QEMU 7.2.0 into the sparc lab.

### OpenBIOS (`openbios/`)

QEMU ships `openbios-sparc32` and the cg3 FCode ROM `QEMU,cgthree.bin` prebuilt.
`openbios/Dockerfile` builds both from the same OpenBIOS commit (`e5ac46dd24` for QEMU 11.1.3)
with the patches in `openbios/patches/` (the OpenBIOS build tokenizes `drivers/cgthree.fs` with
`toke` into `obj-sparc32/QEMU,cgthree.bin`), the `openbios-sparc32` make target (part of
`pve-qemu-bundle`) puts them in `build/openbios/`, and `debian/rules` installs each over QEMU's
image. Like the other extras, the package falls back to QEMU's images when the build fails
(`WARNING: optional extra openbios missing: ...`). `scripts/check-qemu-extras.sh` tells the two
apart: against the build tree it compares the package's files with `build/openbios/` and QEMU's
`pc-bios/`; on an installed package it compares the build date in `openbios-sparc32` with the
package's and the cg3 ROM with QEMU's (850 bytes; ours is 863).

| Patch | Fixes | Upstream |
| --- | --- | --- |
| `0001-esp-treat-a-selection-timeout-as-no-device` | Every empty SCSI target was probed as a device of unknown type (`UNKNOWN0`-`UNKNOWN7` aliases), so the disk on target 3 had only `disk3`: no `disk` alias, and the default boot (`disk:a disk`) failed with "No valid state has been set by load or init-program". Broken since OpenBIOS's ESP changes of 2024-09 (QEMU 9.2 and later) | not fixed; see `upstream/openbios-esp-selection-timeout.md` |
| `0002-cgthree-map-only-the-console-lines-that-fit` | OpenBIOS maps at most 0xc0000 bytes (1024x768) of framebuffer; the ROM mapped that much and drew on the whole screen, so 1152x900 took a data access fault at power-on. The firmware console now uses the lines that fit (682 at 1152x900, 409 at 1920x1080); `width`, `height` and `linebytes` still give the real size. From [LEMU `9ea85e13`](https://github.com/tenox7/lemu/commit/9ea85e132e43d55422f8d527e9dfc74bca33aa59) (`machines/sun4m/cgthree/cgthree.fs`) | not in OpenBIOS |
| `0008-sparc32-enter-the-prompt-on-op_enter-and-resume-with-go` | Stop-A (the romvec's `op_enter`) on a running Solaris or SunOS powered the machine off ("abort, power off"); it now stops at the prompt and `go` resumes the client, `boot` resets first ("Stop-A") | not fixed; see `upstream/openbios-sparc32-op-enter-powers-off.md` |
| `0016-sparc32-give-the-cs4231-intr-9-the-level-of-its-sbus-level` | The SS-5's `SUNW,CS4231` node had `interrupts` 5 (SBus level 5, processor level 9) and `intr` 5 (processor level 5): Solaris waits where the first says, SunOS 4 where the second says, so no wiring served both. `intr` is now 9, as the Sun PROM's `0x39`, for QEMU patch 0030 ("Audio") | not in OpenBIOS (QEMU had no working codec) |

Without 0002 the built `QEMU,cgthree.bin` is byte-identical to the one QEMU 11.1.3 ships; with it,
to LEMU's.

`openbios/Dockerfile` also builds `openbios-sparc64` from the same commit, as an optional extra of
its own (`openbios-sparc64`; see "Solaris on sun4u"). The sparc32 build applies every patch except
those named `*-sparc64-*`. The sparc64 build applies all of them, in a step that leaves no
`openbios-sparc64` when it fails; the `openbios-sparc32` make target then prints `WARNING: optional
extra openbios-sparc64 missing: ...` and the package keeps QEMU's image. `debian/rules` installs it
over QEMU's image like the sparc32 one. `scripts/check-qemu-extras.sh` tells ours from QEMU's against
the build tree by comparing with `build/openbios/` and `pc-bios/`; on an installed package by its
build date (within two days of the package's `qemu-system-sparc64`; QEMU 11.1.3's image says Jun 29
2026) and the Forth word `upa-portid>bustype`, which only 0009 defines.

| Patch | Fixes | Upstream |
| --- | --- | --- |
| `0003-sparc64-list-the-whole-virtual-address-space-as-available` | `/virtual-memory`'s `available` ended at `0xff000000`, so claims above it were invisible in it. 64-bit Solaris maps its kernel heap at `0x30000000000` and sizes its pool of nucleus hme blocks from the gaps in that list: Solaris 10 panicked with `no nucleus hblk8 to allocate`, Solaris 8/9 with `BOP_ALLOC failed`. The list now covers the whole 64-bit space like OBP's, with the firmware's range (`0xff000000`-4 GB) and the UltraSPARC I/II VA hole claimed | not fixed; see `upstream/openbios-sparc64-virtual-available.md` |
| `0004-sparc64-give-the-cpu-node-the-icache-size` | The CPU node's `icache-size`/`icache-line-size` carried the E-cache values (1 MB, 64 bytes on the IIi); Solaris 9 panicked with `VAC too big!` | not fixed; see `upstream/openbios-sparc64-icache-properties.md` |
| `0005-sparc64-leave-no-active-package-after-preopen` | `preopen` left `/chosen` as the active package at the prompt and for every client program, so Solaris's Forth words (`unix-tte`) went into `/chosen`'s word list and `' unix-tte is va>tte-data` failed after the kernel's `device-end` | not fixed; see `upstream/openbios-sparc64-client-forth-state.md` |
| `0006-sparc64-client-dont-define-a-forth-constant` | `11 constant forth` in `client.fs` hid the FORTH vocabulary word; `only forth also definitions` pushed `0x11` (generic code, applied to sparc64 only here) | as 0005 |
| `0007-sparc64-fcode-consume-instance-in-defining-words` | FCode `b(value)`/`b(variable)`/`b(defer)`/`b(buffer:)` left the `instance` flag set; the next Forth `defer` became an instance word and crashed with no active package (generic code, applied to sparc64 only here) | as 0005 |
| `0009-sparc64-name-upa-and-ebus-children-like-obp` | The sabre was `pci@1fe,0` and the ebus children `su@0`, `8042@0`, ...; OBP (and Solaris, which builds the same names and looks the console path up among them) has `pci@1f,0` and `su@14,3f8`. Solaris 10 never opened its console driver and its installer ignored all input on ttya. The root prints the UPA port id; the ebus node has its own two-cell space,offset `encode-unit`/`decode-unit` | not fixed; see `upstream/openbios-sparc64-node-names.md` |
| `0010-sparc64-pathres-interposed-package-gets-the-device-my-unit` | An interposed package (disk-label) answered `my-unit` with 0 0, so NetBSD's ofwboot passed target 0 for the CD-ROM and, with 0011's tree, the kernel rooted on `wd0`. It now answers with the unit of the device it sits on (generic code, applied to sparc64 only here) | not fixed; see `upstream/openbios-sparc64-ide-tree.md` |
| `0011-sparc64-put-ide-drives-under-the-controller` | Drives directly under the IDE controller as OBP has them (`ide@3/disk@0,0`, `cdrom@2,0`, target = 2 × channel + unit), with `compatible` `ide-disk`/`ide-cdrom`: the Solaris 10 installer accepts its DVD and the installed disk mounts root | as 0010 |
| `0012-…boot-service.patch.wip` | Client-interface `boot` (Solaris' reboot) resets the machine instead of returning. Resets at the `ok` prompt, but Solaris's `reboot` then hangs the VM, so it stays `.wip` (the Dockerfile only applies `*.patch`) | — |
| `0013-sparc64-ofmem-keep-the-upper-bits-of-physical-addresses-in-align_ptr` | `align_ptr()` masked with a 32-bit `size_t`, so the firmware's heap broke once it sat above 4 GB (it is at the top of RAM): from about 4.3 GB OpenBIOS stopped before its banner (`Unhandled Exception 0x0000000000000030`; at 8192 MB `out of malloc memory (28)!` first). Generic code, applied to sparc64 only here | not fixed; see `upstream/openbios-sparc64-ram-above-4g.md` |
| `0014-sparc64-ofmem-find-claim-memory-whose-1-1-virtual-range-is-free` | A client `claim` with an alignment took the top of RAM and mapped it 1:1 without checking the virtual side; with 4 GB that is the firmware's own range, the claim failed and NetBSD stopped after its loader (`Can't claim two pages of memory.`). It now searches below `0xff000000` and lower while the virtual range is taken. Generic code, applied to sparc64 only here | as 0013 |
| `0015-sparc64-return-the-whole-physical-address-in-phys-lo` | `claim`, `SUNW,retain` and `translate` cut `phys.lo` to 32 bits, but 64-bit NetBSD and Solaris read `phys.lo` alone. With 6 and 8 GB NetBSD's kernel sat above 4 GB, `ofwboot` mapped the truncated addresses, and once memory filled up the kernel stopped (`trap type 0x10`, `panic: illegal instruction`). `phys.lo` now carries the whole address | as 0013 |

When QEMU updates `roms/openbios`, set `OPENBIOS_REF` to the new commit and check the patches.

### cg3 sizes

With 0008-0010 and the ROM, `-vga cg3 -g WxH` takes 640x480 up to 8 MB of pixels (e.g.
4096x2048), width a multiple of 8, depth 8 only. Anything else stops QEMU with `Unsupported
resolution: W x H (640 x 480 or more, 8 MB of pixels at most, and a width that 8 divides)`. The
OpenBIOS console uses the top 0xc0000 bytes of the screen; the guest maps all of it. The Sun PROMs
stay at the default 1024x768. qemu-server and the UI don't offer a resolution yet.

Tested (lab `display` matrix, SS-5, OpenBIOS, console on the framebuffer): the banner and Solaris
2.6 to `console login:` at 1024x768, 1152x900, 1280x1024, 1600x1200 and 1920x1080; `ss5.bin`
shows its banner at 1024x768. Above 1024x768 the Solaris console has the lines the ROM maps (682
at 1152x900, 409 at 1920x1080), and Solaris 2.6's X server doesn't start: `/var/dt/Xerrors` has
`Mapping cg3: No such device or address` / `AddScreen failed for /dev/fb`, so dtlogin falls back to
the console. At 1024x768 dtlogin comes up. LEMU tested SunOS 4.1.4 (OpenWindows up to 3200x1800).

### cg3 and TCX

The two framebuffers QEMU's sun4m has (`hw/display/cg3.c`, `hw/display/tcx.c`, QEMU 11.1.3):

| | cg3 | TCX |
| --- | --- | --- |
| Pixels | 8-bit plane, colour map | 8-bit plane; with depth 24 also a 24-bit plane and a control plane that picks 8-bit or 24-bit per pixel (9 MB of host RAM) |
| `-g` | 640x480 up to 8 MB of pixels with 0008-0010, depth 8 (`x24`: `Unsupported depth: 24`) | 1024x768 only, depth 8 (default) or 24; other sizes `Unsupported resolution: W x H`, depth 16/32 `Unsupported depth` |
| Drawing | the CPU writes the plane (plain stores into guest RAM) | also a stippler and a blitter: one register write draws or copies up to 32 pixels (MMIO, each write a call into QEMU); "raw" variants that write the control plane too |
| Cursor | drawn by the X server into the plane | 32x32 two-colour hardware cursor (THC registers), drawn by QEMU into its display output |
| Interrupt | vertical retrace, raised only when the display is refreshed (README, "Things the lab found out") | none: the IRQ is wired but never raised |
| Firmware ROM | `QEMU,cgthree.bin` (ours) | `QEMU,tcx.bin` (OpenBIOS `drivers/tcx.fs`, QEMU's): the 8-bit or 24-bit `reg` layout and `tcx-8-bit`; the firmware console is 8-bit in both; the Sun PROMs get its 1024x768 defaults |
| Solaris | `cgthree` driver and `ddxSUNWcg3.so.1`, always installed | `tcx` (SUNWtcx) and `ddxSUNWtcx.so.1` (SUNWtcxow), installed only when the installer saw a TCX (below) |

QEMU's sun4m defaults to TCX; qemu-server passes `-vga cg3` unless `vga: tcx`, and never `-g`, so a
`vga: tcx` VM is TCX at 1024x768x8.

**Why TCX "doesn't work".** Two failure modes in Solaris, one in QEMU's TCX ROM:

1. *No TCX driver.* The installer adds the TCX cluster (SUNWCtcx: SUNWtcx = `/platform/sun4m/kernel/drv/tcx`,
   SUNWtcxow = `/usr/openwin/server/modules/ddxSUNWtcx.so.1` and `OWconfig`, SUNWtcxu = the XGL pipeline)
   only when it finds a TCX at install time: the 2.6 and 2.5.1 CDs' `.clustertoc` have
   `SUNW_CSRMBRIFF=(smcc.dctoc tcx)SUNWCtcx`. A system installed on the serial console or with the cg3
   (every lab disk, and anyone who installed with qemu-server's default) has none of it; cg3 support is
   always installed. Booted with TCX it says `NOTICE: Can't find driver for console framebuffer` (the
   console still works, through the PROM), and dtlogin gives up (`/var/dt/Xerrors`: `/dev/fb: No such
   file or directory`, `Graphics Adapter device /dev/fb is of unknown type`, `Fatal server error:
   InitOutput: Error loading module for /dev/fb`; the console: `The X-server can not be started on
   display :0...`). Fix: from the install CD, `pkgadd -d /cdrom/cdrom0/s0/Solaris_2.6/Product SUNWtcx.m
   SUNWtcxow SUNWtcxu` (SUNWtcx is per platform: `.m`; 2.5.1: `/cdrom/cdrom0/s0/Solaris_2.5.1`), then a
   reconfigure boot (the lab's `scenarios/solaris-tcx-packages.py`), or install with the TCX attached.
2. *Switching without a reconfigure boot.* Solaris 2.6 creates the `/devices` nodes and the `/dev/fb`
   link only on a reconfigure boot (`boot -r`, `touch /reconfigure`). After a switch from TCX to cg3 (or
   back) `/dev/fb` still points at the old device: `/dev/fb: No such device or address`, `Graphics
   Adapter device /dev/fb is of unknown type`, no X. `touch /reconfigure` before the change (or `boot -r`
   once after it) fixes it; fresh lab disks don't show it because an install leaves `/reconfigure` for
   the first boot.
3. *TCX 24-bit under a Sun PROM stops QEMU.* `QEMU,tcx.bin` learns the depth from OpenBIOS words
   (`depth-bits`, `openbios-video-width`); under a Sun PROM it falls back to 8 bits and describes an 8-bit
   TCX (`tcx-8-bit`, the THC at offset 0x300000), while QEMU's 24-bit TCX has its THC at 0x301000 and
   nothing at 0x300000 (for 8 bits QEMU maps a dummy at 0x301000, "NetBSD writes here", not the
   reverse). `ss5.bin` + `-g 1024x768x24`: the banner is fine, then 7-12 s after `boot disk`
   `qemu: fatal: Trap 0x29 (Data Access Error) while interrupts disabled` (pc f00412f4), 2 of 2 boots;
   most likely the tcx driver's first THC access (not traced). Not reachable through qemu-server (no
   `-g`). A fix would be in QEMU (map the THC, or a dummy, at 0x300000 for depth 24 too) or in `tcx.fs`.

1 and 2 don't depend on the machine or the depth. With the packages and a reconfigure boot, TCX ran
every Solaris case below that cg3 ran.

Not TCX, but found on the way: **SS-20 with `ss20_v2.25_rom` doesn't boot Solaris 2.6 with any
framebuffer** (cg3 or TCX, also the unmodified installed disk). After its failed network boot (the
PROM's NVRAM is invalid at every power-on, so `diag-switch?` is true), `boot disk` typed on the Sun
keyboard resets the PROM and the command is lost (`Rebooting with command:` and the network again);
with `setenv diag-switch? false` first it boots the disk after that reset and the kernel panics:
`BAD TRAP: type=9 ... kernel read fault at addr=0x0`, `MMU sfsr=126: Invalid Address`. The same disk
boots with the console on ttya (`boot disk` there doesn't reset). Not investigated further; the lab's
`machines`/`bench` cases use that PROM without a framebuffer. `ss5.bin` boots from the same state.

**Results** (console on the framebuffer, `scenarios/fb-display.py` unless stated; Solaris cases on a
fresh copy of a disk prepared with `solaris-tcx-packages.py`, whose next boot is a reconfigure boot;
"X" = dtlogin, root logged in, the CDE desktop, the depth `xdpyinfo` reports, a command typed into a
dtterm on the Sun keyboard):

| Machine | Firmware | Guest | Display | Banner | Console | X | Depth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SS-5 | OpenBIOS | 2.6 | TCX 8 | yes | yes | yes | 8 |
| SS-5 | OpenBIOS | 2.6 | TCX 24 | yes | yes | yes | 24 |
| SS-5 | OpenBIOS | 2.6 | cg3 | yes | yes | yes | 8 |
| SS-5 | OpenBIOS | 2.6, no SUNWtcx | TCX 8 | yes | yes (PROM) | no (failure mode 1) | |
| SS-5 | `ss5.bin` | 2.6 | TCX 8 | yes | yes | yes | 8 |
| SS-5 | `ss5.bin` | 2.6 | TCX 24 | yes | QEMU stops (failure mode 3) | | |
| SS-5 | `ss5.bin` | 2.6 | cg3 | yes | yes | yes | 8 |
| SS-5 | `ss5.bin` | 2.5.1 | TCX 8 | yes | yes | OpenWindows' `Xsun` started from a shell (End User 2.5.1 has no CDE/dtlogin) | 8 |
| SS-10 | OpenBIOS | 2.6 | TCX 8 | yes | yes | yes | 8 |
| SS-10 | OpenBIOS | 2.6 | TCX 24 | yes | yes | yes | 24 |
| SS-10 | OpenBIOS | 2.6 | cg3 | yes | yes | yes | 8 |
| SS-20 | OpenBIOS | 2.6 | TCX 8 | yes | yes | yes | 8 |
| SS-20 | OpenBIOS | 2.6 | TCX 24 | yes | yes | yes | 24 |
| SS-20 | OpenBIOS | 2.6 | cg3 | yes | yes | yes | 8 |
| SS-20 | OpenBIOS | 2.6, no SUNWtcx | TCX 8 | yes | yes (PROM) | no (failure mode 1) | |
| SS-20 | OpenBIOS | 2.6 | cg3 after TCX, no `-r` | | yes | no (failure mode 2); after `touch /reconfigure`: yes | |
| SS-20 | `ss20_v2.25_rom` | 2.6 | TCX 8, TCX 24, cg3 | yes | kernel panic (above) | | |
| SS-5 | OpenBIOS | SunOS 4.1.4 | TCX 8 | yes | yes (`tcx0: revision 0, screen 1024x768`, its own driver) | not tried | |
| SS-5 | OpenBIOS | SunOS 4.1.4 | cg3 | yes | yes (`cgthree0`) | not tried | |
| SS-5 | OpenBIOS | NetBSD 11.1 | TCX 8 | yes | yes (`tcx0 ... (8-bit only TCX)`, `wsdisplay0 at tcx0`) | not installed | |
| SS-5 | OpenBIOS | NetBSD 11.1 | TCX 24 | yes | yes (`tcx0 ... (S24)`) | not installed | |
| SS-5 | OpenBIOS | NetBSD 11.1 | cg3 | yes | yes | not installed | |

The SunOS and NetBSD rows are one boot each, logged in on the framebuffer by OCR and send-key (no
lab scenario: `fb-display.py` expects Solaris's prompts).

**Speed.** QEMU's host time for the lab's drawing workload (`fb-display.py BENCH=3`, root's CDE session,
from the ttya shell with `DISPLAY=:0`; median of 3, range; one guest of ours, host load 1-5 from other
jobs on 14 cores): `text` = `xterm +j` (no jump scroll) `cat`s 1500 lines, `scroll` = the same with jump
scroll, `fill` = 20 `xsetroot -solid`, `windows` = 10 `xterm -e true`. QEMU's CPU in % of a core during
each. MMIO = QEMU's `memory_region_ops_write` events in one more round, per TCX region (the plain planes
are RAM and don't show):

| Machine | Display | text s | scroll s | fill s | windows s | MMIO writes per round |
| --- | --- | --- | --- | --- | --- | --- |
| SS-20 | TCX 8 | 6.2 (6.0-6.6), 103% | 0.5 (0.5-0.6), 130% | 1.0 (0.9-1.0), 119% | 1.4 (1.4-1.5), 109% | `tcx.blit` 27.8 M, `tcx.stip` 4.8 M |
| SS-20 | TCX 24 | 7.9 (7.0-8.6), 102% | 0.7 (0.5-0.7), 123% | 0.9 (0.9-1.0), 121% | 1.3 (1.2-1.4), 109% | `tcx.rblit` 27.8 M, `tcx.stip` 4.9 M |
| SS-20 | cg3 | 1.0 (1.0-1.1), 109% | 0.2 (0.2-0.3), 149% | 0.9, 111% | 1.2 (1.1-1.2), 109% | none |
| SS-5 | TCX 8 | 7.1 (6.8-7.4), 103% | 0.7, 124% | 1.3 (1.2-1.5), 115% | 1.9 (1.9-2.1), 108% | `tcx.blit` 27.8 M, `tcx.stip` 4.9 M |
| SS-5 | TCX 24 | 8.1 (7.9-8.1), 102% | 0.9 (0.8-0.9), 124% | 1.3 (1.2-1.3), 120% | 1.8 (1.7-1.8), 106% | `tcx.rblit` 27.8 M, `tcx.stip` 5.0 M |
| SS-5 | cg3 | 1.7 (1.6-1.9), 107% | 0.3, 148% | 1.2 (1.2-1.3), 111% | 1.9 (1.6-2.0), 107% | none |

TCX's acceleration is used (about 14 million blitter and 2.4 million stippler operations per round,
each two 4-byte writes, from the X server's TCX module; the raw blitter at depth 24),
and it makes text drawing slower, not faster: 4x (SS-5) to 8x (SS-20, depth 24) the cg3's time. Each
operation is an MMIO write that leaves the translated code for a call into `tcx.c`, while the cg3's
pixels are ordinary stores into guest RAM. Fills and window creation cost the same on both. QEMU's
CPU stayed at 102-149% of a core in every test (above 100%: its display refresh and I/O threads). dtlogin
came up 76-97 s after QEMU started and the desktop (user name to a still CDE screen) took 10-18 s, on
either.

**Colours.** At depth 24 the X server's root window is 24 planes; the desktop, window frames and icons
look as at depth 8, but the Help Viewer draws its illustrations dithered black and white (in colour at
depth 8). At depth 8 TCX and cg3 look the same, the firmware console too (OpenBIOS: black on light
yellow on both; `ss5.bin` on TCX: black on white). TCX has no vertical-retrace interrupt, so the cg3's
colour-map delay with no display refresh (README) can't happen there (from the code; not measured).

**Input.** The Sun keyboard works in X on both (a command typed into a dtterm ran). Pointer movement
from QEMU's monitor (`mouse_move`) reaches the guest (the ESCC trace shows each 5-byte packet read by
the kernel), but the X pointer doesn't move, on cg3 and TCX, OpenBIOS and `ss5.bin` alike, and reading
`/dev/mouse` with dtlogin stopped gets nothing; so it's not a framebuffer matter, and it is open (not
tried with a VNC client). The TCX hardware cursor is drawn where X put it (the screen centre); with no
movement the X server never wrote the cursor position register.

**Idle.** QEMU's host CPU with the CDE desktop idle for 60 s (`solaris-idle`, the lab's 0.5 s display
refresh): TCX 8 4.4-8.8%, TCX 24 4.5-6.4%, cg3 4.2-9.5% of a core (4 measurements each, SS-5 and
SS-20), with no consistent difference between them; a running X server doesn't keep the guest busy.

**Soak.** SS-20, OpenBIOS: 600 s of back-to-back benchmark rounds on the desktop, then `xdpyinfo` and a
screenshot: TCX 8 (39 rounds), TCX 24 (36 rounds) and cg3 (52 rounds: its text test is faster)
passed, with no hang, crash or drawing errors in the screenshots. Every X case above ended with the guest still answering on ttya.

**Recommended** (from the data above):

- **cg3 stays the default for every profile.** It works on any installed system without extra
  packages, takes larger sizes under OpenBIOS, and draws text 4-8x faster than TCX here; there is
  no case where TCX was faster, and fills, window creation, login time, idle CPU and stability were
  the same.
- **TCX is the choice for 24-bit colour**, and only with OpenBIOS: SS-5, SS-10 and SS-20 ran the
  desktop at depth 24. With `ss5.bin` TCX works at depth 8 only (24 stops QEMU, failure mode 3).
  Either way Solaris needs SUNWCtcx (install with the TCX attached, or add the packages) and a
  reconfigure boot after the switch. TCX at depth 8 has nothing over cg3.
- **SS-20 with `ss20_v2.25_rom`**: neither framebuffer gets Solaris 2.6 booted (the kernel panic
  above); give that profile a serial console until that is understood.
- What qemu-server/pve-manager would need: nothing for the default. To offer 24-bit: a depth choice
  for `vga: tcx` (e.g. `vga: tcx,depth=24` → `-g 1024x768x24`; TCX takes no other size), allowed with
  `openbios-sparc32` only (or QEMU/`tcx.fs` fixed for the Sun PROMs). In the guide and the UI's help:
  changing `vga` on an installed Solaris needs `touch /reconfigure` before (or `boot -r` once after),
  and a system installed with cg3 or on the serial console needs SUNWtcx/SUNWtcxow from the CD before
  TCX works in X. For `ss20_v2.25_rom`, a note (or a serial-console default) about the framebuffer
  panic. No QEMU, qemu-server or pve-manager patch was changed for this.

### Idle

QEMU keeps a host core at 100% for a guest that spins in its idle loop. Which sparc32 guests stop
(sun4m, one CPU unless stated):

| Guest | Idles | How |
| --- | --- | --- |
| NetBSD 11.1, Linux | yes | their APC driver (`apc0 at sbus0 slot 4 offset 0xa000000`) writes register 0 of the power management node in the idle loop and QEMU halts the CPU until the next interrupt, with or without these patches. Linux not tested here |
| NetBSD 9.3 | no | its GENERIC kernel has no APC driver (`power-management ... not configured`); neither have the install kernels of 9.3 and 11.1 |
| Solaris 2.5.1-9 | yes | 0014-0015: QEMU recognises the call of `idle_cpu` in the kernel's idle loop and halts the CPU there (`solaris-idle`, on by default; `-M SS-20,solaris-idle=off` turns it off; off with `-smp` > 1). Any CPU module, SS-5 and SS-10/SS-20. `-trace sparc_solaris_idle_match` shows the match |
| Solaris 2.5.1-9, 2-4 CPUs | yes | 0023-0024: QEMU recognises the call of `disp_getwork` in the multiprocessor idle loop and halts the CPU there until another CPU queues work for it, an interrupt or 10 ms (`solaris-smp-idle`, on by default; `-M SS-20,solaris-smp-idle=off` turns it off). SS-10/SS-20 with OpenBIOS. `-trace sparc_solaris_idle_mp_match` shows the match ("SMP") |
| Solaris 2.6 + `pmc` | yes | also without 0014: the `pmc` driver (package `SUNWvygdr.m` on the 2.6 CD, not installed by default) lets the idle loop write APC register 0, SS-5 only; needs 0011. Steps below |
| SunOS 4.1.4 | yes | 0012-0013: QEMU recognises the kernel's idle loop and halts the CPU there (`sunos-idle`, on by default; `-M SS-5,sunos-idle=off` turns it off; off with `-smp` > 1). `-trace sparc_sunos_idle_match` shows the match |

**Solaris idle loop.** With one CPU, `idle()` (`uts/common/disp/disp.c`, in the platform `unix`) loops
`while (ncpus == 1)`: `swtch()` when `CPU->cpu_disp.disp_nrunnable` is not 0, else `(*idle_cpu)()`.
Only the microSPARC-II module (`FMI,MB86904`, also in `default`) sets `idle_cpu`, to `swift_idle_cpu`,
which jumps through `pm_platform_power` (genunix): `ddi_no_platform_power` (`retl; mov -1, %o0`) unless
`pmc` replaced it with its APC write. The SuperSPARC module (`TI,TMS390Z55`) doesn't touch `idle_cpu`,
so it stays `generic_idle_cpu` (`retl; nop`): 2.6 on SS-5 without `pmc` and every Solaris on SS-10/SS-20
spin. Disassembled from the installed kernels and the install media (sun4m `unix`):

| Release | Kernel | Load of `disp_nrunnable` | Call of `idle_cpu` | Layout |
| --- | --- | --- | --- | --- |
| 2.5.1 | Generic_103640-12 | `ld [%i5], %o4` (`%i5` = CPU + 0x48) | `0xf0075ca4` | `2.5.1` |
| 2.6 | Generic_105181-05 | `ld [%i0 + 0x58], %o0` | `0xf006fa58` | `2.6/7/8` |
| 7 | Generic_106541-02 | `ld [%i0 + 0x54], %o0` | `0xf006e0f4` | `2.6/7/8` |
| 8 | Generic_108528-05 | `ld [%i3 + 0x54], %g2` | `0xf006d894` | `2.6/7/8` |
| 9 | Generic | `ld [%l1 + 0x60], %g2` | `0xf006cb38` | `9` |

Each layout is the words from that load to `call %reg` (load, `cmp`/`tst`, branch, `sethi %hi(idle_cpu)`,
[`call swtch`, `nop`, `b top`, delay slot], `ld [%y + lo], %z`), with registers, offsets and addresses
masked; the translator also checks that they use the registers consistently and that the CPU pointer
isn't overwritten. At the call the helper halts when `disp_nrunnable` is 0 (read again, non-faulting),
PSR.ET is set, PIL is 0 and no interrupt is pending, after spinning 100 us; the CPU goes on at the call
after the next interrupt (at least the 100 Hz clock). With one CPU only an interrupt handler can make a
thread runnable. Halting in place of `idle_cpu` is what `idle_cpu` is for (disp.c: "to stop the
pipeline and save power"); with `pmc` the APC write and the halt are the same thing. Other kernel
patch levels than those above weren't available; one compiled differently doesn't match and spins as
before.

At the installer's first question on SS-20 (OpenBIOS, one CPU, `solaris-boot-cd.py IDLE=60`), each
release's kernel matched at the address above and QEMU used: 2.5.1 (`CDROM_AS=hd`) 2.2%, 2.6 2.2%,
7 2.3%, 8 (Installation CD) 3.8%, 9 2.7%; 9 with `solaris-idle=off` 100.5%. Installed 7/8/9 weren't
tested.

With more than one CPU, `idle()` runs another loop: it polls `disp_getwork()` (work stealing from other
CPUs' queues) and never calls `idle_cpu`, and `cpu_resched()` doesn't poke an idle CPU (`!CPU_IDLING`),
so a halted CPU wouldn't see work queued for it until its next interrupt, and only one CPU gets the
clock. That's why `solaris-idle` is off with `-smp` > 1; 0023-0024 (`solaris-smp-idle`) halt that loop
with wake-ups of their own ("SMP", "Idle with more than one CPU").

Not used: the APC on SS-10/SS-20 (real machines have none, but OpenBIOS creates the `power-management`
node there, QEMU maps the device at `0xefa000000`, "XXX should not exist"; the Sun PROMs don't): NetBSD
11.1 attaches `apc0` there and idles, but Solaris only reaches it from the microSPARC-II module, whose
`swift_idle_cpu` isn't loaded on a SuperSPARC. `pmc` alone can't help there; pointing `idle_cpu` at
something that calls `pm_platform_power` would take a kernel patch per build (an `/etc/system` `set`
of a raw address, or a loadable module built with a compiler the guest doesn't have). The viking
module's sources (`cpu/vik*`) have no power-down or standby code.

Solaris 2.6 + `pmc`, in the guest, from the 2.6 CD (not needed with 0014):

```sh
mount -F hsfs -o ro /dev/dsk/c0t6d0s0 /mnt
pkgadd -d /mnt/Solaris_2.6/Product SUNWvygdr.m     # y twice
echo 'pmc "power-management"' >> /etc/driver_aliases
echo 'forceload: drv/pmc' >> /etc/system
touch /reconfigure; init 6
```

Without 0011 that kernel panics at boot (`kernel write fault at addr=0x6a000002`, `panic: trap:
unexpected MMU trap`).

Tested with the lab's `scenarios/idle.py` (SS-5, OpenBIOS, QEMU's host CPU use over 60 s at the
shell after login; the `idle` matrix has the cases with 0011-0013 except NetBSD 9.3):

| Guest | Package | Host CPU | Guest clock over 60 s | `dd if=/dev/zero of=/dev/null` |
| --- | --- | --- | --- | --- |
| Solaris 2.6 + `pmc` | with 0011-0013 | 2.3% | 60 s | 1.6 s (200000 blocks) |
| Solaris 2.6 + `pmc` | 11.1.3-2+wsh3 | panics at boot | | |
| Solaris 2.6 | with 0011-0013 | 101.8% | 60 s | 1.7 s |
| Solaris 2.6 | 11.1.3-2+wsh3 | 101.5% | 60 s | 1.7 s |
| SunOS 4.1.4 | with 0011-0013 | 2.3% | 60 s | 9.7 s (20000 blocks) |
| SunOS 4.1.4, `sunos-idle=off` | with 0011-0013 | 100.3% | 60 s | 10.2 s |
| SunOS 4.1.4 | 11.1.3-2+wsh3 | 100.3% | 60 s | 9.5 s |
| NetBSD 11.1 | with 0011-0013 | 2.4% | 60 s | 8.4 s (200000 blocks) |
| NetBSD 11.1 | 11.1.3-2+wsh3 | 2.4% | 60 s | 8.5 s |
| NetBSD 9.3 | with 0011-0013 | 100.6% | 60 s | 7.0 s |
| NetBSD 9.3 | 11.1.3-2+wsh3 | 100.6% | 61 s | 6.6 s |

With 0011-0016 (the `idle` matrix, OpenBIOS unless stated, one CPU; echo = median host time from Return
to the end of `true`, 50 ms in every case, the lab's polling step; ten `sleep 1` took 10.1-10.2 s in
every case):

| Guest | Machine | Host CPU | Guest clock over 60 s | `dd` |
| --- | --- | --- | --- | --- |
| Solaris 2.6 | SS-20 | 3.3% | 60 s | 1.8 s |
| Solaris 2.6, `solaris-idle=off` | SS-20 | 101.6% | 60 s | 2.0 s |
| Solaris 2.6 | SS-5 | 3.4% | 60 s | 1.6 s |
| Solaris 2.6, `solaris-idle=off` | SS-5 | 101.6% | 60 s | 1.6 s |
| Solaris 2.6 + `pmc` | SS-5 | 2.3% | 60 s | 1.8 s |
| Solaris 2.6 + `pmc`, `solaris-idle=off` | SS-5 | 2.3% | 60 s | 1.7 s |
| Solaris 2.5.1 (`ss5.bin`) | SS-5 | 3.2% | 60 s | 1.4 s |
| SunOS 4.1.4 | SS-5 | 2.4% | 60 s | 9.7 s |
| SunOS 4.1.4, `sunos-idle=off` | SS-5 | 100.3% | 60 s | 9.8 s |
| NetBSD 11.1 | SS-5 | 2.4% | 60 s | 8.1 s |

The ~1% over `pmc` is the 100 us spin before each halt (100 clock ticks a second); with `pmc` the first
`idle_cpu` call of that spin halts through the APC.

### Stop-A

Stop-A (L1-A) on a running Solaris under OpenBIOS turned the VM off. QMP `send-key` `stop` + `a`
(what `qm sendkey <vmid> stop-a` and a VNC client's Stop key send; qcode `stop` is Linux `KEY_STOP`,
Sun keycode 0x01, the L1/Stop key; `f11`/`f12` are the Sun F11/F12) at Solaris 2.6's console login
and at dtlogin, SS-5, OpenBIOS, cg3, `pve-qemu-kvm` 11.1.3-2+wsh10: OpenBIOS printed `abort, power
off` on ttya, wrote the power-off bit (`-trace slavio_aux2_mem_writeb`: `Write aux2 0x01`, which is
`qemu_system_shutdown_request(SHUTDOWN_CAUSE_GUEST_SHUTDOWN)`), and QEMU exited 3 s after the keys
with status 0 and nothing on stderr: a guest power-off, not a crash. PVE runs QEMU with
`-no-shutdown` and qmeventd ends it after a guest shutdown, which is why the VM was gone and
nothing was logged. On the framebuffer nothing showed (OpenBIOS's `printk` goes to ttya).

**Cause.** Solaris's abort sequence calls `abort_sequence_enter()` → `debug_enter()` (sun4m
`machdep.c`: `splzs()`, idles the other CPUs) → `prom_enter_mon()` → the romvec's `op_enter`, which
OpenBIOS calls `pv_abort`. OpenBIOS's `obp_abort()` (`arch/sparc32/romvec.c`) printed the message
and powered off, while `op_enter` means "the prompt, and back on `go`" (the Sun PROMs do that).
QEMU and the keyboard path are fine: the chord reaches Solaris as the Sun keyboard sends it.

**Fix** (`openbios/patches/0008`): `obp_abort()` raises PIL to 15, runs a Forth word `(enter)` and
returns to the client when it ends. `(enter)` saves the input source (the client was started from
the `boot` that `boot-command` evaluates), takes an input buffer of its own, prints `Type  'go' to
resume` and runs the outer interpreter. While a client is entered `go` ends that interpreter, and
`boot` runs `reset-all` first (the client still occupies memory; the Sun PROMs reset too). PIL 15
because the console is polled and the client's keyboard/serial handlers would take the keys (Solaris
itself raised to level 12 before the call). OpenBIOS's mappings are in the client's MMU context as
for every romvec call, so the prompt, the framebuffer console and `reset-all` work there. The
prompt prints `ok` after `go` before returning; harmless. `sync` (dump through the client's sync
hook) isn't implemented. Upstream material: `upstream/openbios-sparc32-op-enter-powers-off.md`.

**What it affects** (`scenarios/stop-a.py`, two rounds each unless stated; "prompt" = `Type  'go'
to resume` and `0 >` on the console, the CPU in the firmware, `go` resumes and the guest answers):

| Guest | Machine, firmware | Console, input | wsh10 (stock OpenBIOS behaviour) | With 0008 |
| --- | --- | --- | --- | --- |
| Solaris 2.6 | SS-5, OpenBIOS | cg3, console login, Stop-A | VM off | prompt; a login after `go` works |
| Solaris 2.6 | SS-5, OpenBIOS | cg3, dtlogin, Stop-A | VM off | prompt drawn over the X screen (as on a Sun); dtlogin takes a user name after `go` |
| Solaris 2.6 | SS-5, OpenBIOS | cg3, console, Stop-A then `boot` | | resets, boots to login again |
| Solaris 2.6 | SS-10, OpenBIOS | cg3, console, Stop-A | not run (same firmware path) | prompt |
| Solaris 2.6 | SS-20, OpenBIOS | cg3, console, Stop-A | VM off | prompt |
| Solaris 2.6 | SS-20, OpenBIOS, 2 CPUs | cg3, console, Stop-A | not run | prompt (one round) |
| Solaris 2.6 | SS-5, OpenBIOS | cg3, console, `a` then `stop` | not run | ignored: `a` typed at the login |
| Solaris 2.6 | SS-5, OpenBIOS | ttya, Stop-A on the keyboard | not run | ignored (the keyboard isn't the console) |
| Solaris 2.6 | SS-5, OpenBIOS | ttya, break (QMP `chardev-send-break`) | no prompt (the hang wasn't checked; it is QEMU's) | no prompt; the guest hangs (below) |
| SunOS 4.1.4 | SS-5, OpenBIOS | cg3, Stop-A | VM off | prompt |
| NetBSD 11.1 | SS-5, OpenBIOS | cg3, Stop-A | its kernel debugger (`db>`), `c` continues | the same |
| none | SS-5, OpenBIOS | the firmware's own `0 >`, Stop-A | ignored | ignored |
| Solaris 2.5.1 | SS-5, `ss5.bin` | cg3, console, Stop-A | `ok`, `go` resumes | (firmware not changed) |
| Solaris 2.6 | SS-5, `ss5.bin` | cg3, dtlogin, Stop-A | `ok`, `go` resumes | (firmware not changed) |

Not run: Solaris 7/8 (no installed disks), the SS-20 Sun PROM, TCX (the firmware path is the same).

Tested with `openbios-sparc32` and `QEMU,cgthree.bin` built by `openbios/Dockerfile` (0001, 0002,
0008) over the published `pve-qemu-kvm` 11.1.3-2+wsh10 (`LAB_FIRMWARE`): the `stopa` matrix 9/9
(and the break case, since dropped from it, failed as above), and no regression in `smoke` (3/3),
`machines` (13/13), `display` (20/20) and `idle` (10/10). No QEMU change; no qtest (the bug isn't
in a device).

**A break on ttya hangs Solaris** (any firmware; a QEMU ESCC bug, not fixed here). QEMU's
`serial_receive_break()` sets RR0's break bit on `CHR_EVENT_BREAK` and never clears it, and
`escc_update_irq()` keeps the external/status interrupt raised for as long as the bit and the
break interrupt enable are set. Solaris's `zsa_xsint()` (`uts/sun/io/zs_async.c`) resets the
status and waits for the bit to go back to 0, the end of the break, which is where it would enter
the abort; that never comes, and the interrupt never goes away. Measured (Solaris 2.6 on ttya,
SS-5, OpenBIOS with 0008, root shell, QMP `chardev-send-break id=ttya`): QEMU's CPU went from 8.5%
to 100.9% of a core, the ESCC register reads from 0 to 1.9 million in 5 s, the PC samples moved
from the idle loop to kernel interrupt code, and the shell no longer answered (no echo for 60 s).
QEMU stays up. Not reachable through PVE (its serial console is a plain Unix socket, xterm.js and
`qm terminal` send no break), but a `-serial mon:stdio` Ctrl-A b, a telnet chardev or QMP would.
A fix would be in QEMU's ESCC: a break with an end (clear the bit after a character time, with the
NUL character a real break leaves in the receiver), so Solaris sees the transition and enters the
prompt; a candidate for a `wsh/` patch and an upstream report.

### Audio

The SS-5's CS4231 plays sound with pve-qemu 0028-0033 and openbios 0016: the APC DMA engine reads
the guest's buffers through the IOMMU and plays them into the audiodev given with
`-machine audiodev=<id>` (qemu-server: `audio0: device=cs4231,driver=...`). The codec is built into
the machine, so there is no `-device`. Without an audiodev (no `audio0`) the chip is the old
register stub: no sound and no interrupts, and a program that waits for the end of a sound hangs,
as before (SunOS 4.1.4, LEMU's report). `driver=none` gives a working chip that nobody hears.

Measured in the lab (2026-11-18) with a `qemu-system-sparc` built from 0001-0033 and the patched
`openbios-sparc32`, `-audiodev wav` (44.1 kHz stereo; the lab variable `AUDIO=wav` does the same).
The sound is a 3-second 400 Hz square wave of u-law bytes made in the guest with `nawk`: none of
the installed disks has Sun's demo sounds (SunOS's Programmer install has no `/usr/demo/SOUND`,
the Solaris End User installs no `SUNWauda`). It went as raw bytes to `/dev/audio` on SunOS, and
with a 24-byte `.au` header through `audioplay -v 100` on Solaris:

| Guest | Firmware | Command time | In the wav file |
| --- | --- | --- | --- |
| SunOS 4.1.4 (`SUNW,CS42310 ... pri 9`) | OpenBIOS | 3.03 s | 3.000 s, 400.0 Hz, every half period 55-56 samples; peak -35.3 dBFS (SunOS's default play gain) |
| Solaris 2.6 | OpenBIOS | 3.16 s | 3.000 s, 400.0 Hz, half periods 55-56 samples, peak -12.3 dBFS (the samples' own level, 7932) |
| Solaris 2.6 | `ss5.bin` | 3.39 s | the same |
| Solaris 2.5.1 | OpenBIOS | 3.21 s | the same |
| Solaris 2.5.1 | `ss5.bin` | 3.22 s | the same |

No sample was lost or repeated, there were no gaps, and the command ends when the sound does. All
runs had `-vga none` (the lab's serial console): sound with the cg3 or TCX interrupting on the same
SBus level through the OR gate was not played. With a cg3 attached, Solaris 2.6 (OpenBIOS) booted
with its console on the cg3, up to its first-boot questions. What was wrong on the way, and is
fixed:

- With LEMU's interrupt (bit 9, processor level 5, which matches OpenBIOS's old `intr` 5) SunOS
  4.1.4 played, but Solaris 2.6 stopped after 1.02 s with `WARNING: processor level 3 SBus interrupt
  not serviced` on the console: Solaris attaches the driver by `interrupts` (SBus level 5). The Sun
  PROM's node says `intr 0x39`, an SBus interrupt at processor level 9, which is SBus level 5 on
  sun4m. 0030 raises SBus level 5 and openbios 0016 makes `intr` 9; then all of the above play.
- Each sound lost its last 50 ms when the driver stopped the DMA as soon as the pipe ran empty
  (0032).
- An SS-5 without an audiodev didn't start (0031).

Not done or not tested: capture (the capture pipe reads as empty, so a recording program gets no
data); ADPCM (plays silence); Solaris 7 and later and NetBSD (not run); Sun's demo `.au` files and
LEMU's `/usr/demo/SOUND/play` (not on our disks; LEMU measured `spacemusic.au` at 6.00 s, peak
-5.2 dBFS); the host backends (`alsa`, `pa`, `pipewire`) on a real node: qemu-server emits them,
the lab used only `wav` (the qtests `wav` and `none`).

QEMU's mixer doubles a mono voice played into a mono output (it adds left and right), so a wav
audiodev with `out.channels=1` is 6 dB too loud; the qtest uses stereo. The `wav` backend leaves the
header's sizes at 0 when the guest powers the machine off; the samples follow the 44-byte header.

Where the sound goes on PVE: SPICE carries sound only to a SPICE display, which sparc32 doesn't
have, so qemu-server refuses `driver=spice` on sparc. The web console (noVNC) has no sound.
`alsa`, `pa` and `pipewire` play on the node's own sound device or sound server (with `pa`, the
existing `server=` option points at a PulseAudio server, as on x86); `none` is silent.

SS-10 and SS-20 have a DBRI with a CS4215 instead, which QEMU doesn't emulate: qemu-server refuses
`audio0` there. sun4u: no sound device was tested, and `audio0` is refused.

### SS-10 and SS-20

Which machine, firmware, CPU count and RAM run Solaris, and whether anything beats SS-5 + one CPU
+ 256 MB. Measured with the published `pve-qemu-kvm` 11.1.3-2+wsh3 (no idle patches) in the lab, serial
console, Solaris 2.6 (5/98) unless stated. QEMU has no HyperSPARC CPU model; the extra PROMs are
from [andarazoroflove/sparc](https://github.com/andarazoroflove/sparc) (not in the package).

**Firmware.** "Installer" = the 2.6 CD boots to its first question.

| Machine | Firmware | `-cpu` | RAM | Result |
| --- | --- | --- | --- | --- |
| SS-5 | OpenBIOS | default | 256 | installer; installed disk to login |
| SS-5 | `ss5.bin` | default | 256 | SS-5 disk to login |
| SS-5 | `ss5-170.bin` | default | 256 | installer |
| SS-10 | OpenBIOS | default | 256, 512 | installer; scripted install (~8.5 min) boots to login |
| SS-10 | `ss10_v2.25_rom` | default | 256 | `Cpu #0 Data Access Error`, `ok` |
| SS-10 | `ss10_v2.25_rom` | SuperSparc-40/50/60 | 64-512 | `Probing Memory Bank #4 Data Access Error`, `ok` |
| SS-20 | `ss10_v2.25_rom` | SuperSparc-50 | 256 | installer |
| SS-20 | OpenBIOS | default | 256, 512 | installer, also `-smp 2` and `-smp 4`; scripted install boots to login |
| SS-20 | OpenBIOS | default | 640, 768 | kernel: `BAD TRAP: type=9 ... kernel read fault at addr=0x0`, `panic: Data fault`, reboot loop (SS-10: same at 1024) |
| SS-20 | OpenBIOS | default | 1024 | `out of malloc memory (1008)!`, then `kernel write fault at addr=0x0`, `panic: Data fault` |
| SS-20 | `ss20_v2.25_rom` | default (SuperSparc-II), -51, -61 | 256 | `Cpu #0 Data Access Error`, `ok`; `banner`: `Data Access Exception`; `boot cdrom`: `qemu: fatal: Trap 0x29 (Data Access Error) while interrupts disabled` |
| SS-20 | `ss20_v2.25_rom` | SuperSparc-40/50/60 | 256, 512, 1024 | installer; scripted install (-50) boots to login. The PROM probes 8 banks of 64 MB, so 512 MB at most (1024 runs as 512) |
| SS-20 | `ross225r.bin` | default | 256 | `Cpu #0 Data Access Error`, `ok` |
| SS-20 | `ross225r.bin` | SuperSparc-50 | 256 | installer (POST: `TI, TMS390Z50`) |
| SS-20 | `cpu10.bin` | SuperSparc-50 | 256 | `Incorrect configuration checksum`, `Data Access Error`, `ok` |
| SS-600MP | OpenBIOS | default | 256 | kernel: `This hardware platform is not supported by this release of Solaris.` (1 and 2 CPUs) |
| SS-4 | `ss4.bin` | default | 256 | `Probing ... at 2,0 SUNW,tcx Data Access Error`, `ok` (with and without a TCX) |
| LX | `lx.bin` | default | 64 | POST `ERROR : Unexpected Synchronous Trap Taken, Trap Type = 00000008`, then `qemu: fatal: Trap 0x03 (Privileged Instruction)` |
| LX | `lx564.bin` | default | 64 | `initializing VME mmuData Access Error`, `ok` (not an LX PROM) |
| Voyager | `voyager.bin` | default | 256 | `qemu: fatal: Trap 0x02 (Illegal Instruction)` after `Power-ON Reset` |

The Sun SS-20 PROM reaches `ok` and boots with `-cpu TI-SuperSparc-40`, `-50` or `-60` only.
qemu-server passes `-cpu TI-SuperSparc-50` for SS-20 with `ss20_v2.25_rom` ("Supported profiles").
With `-smp 2` the PROM reports `Cpu #1 Nothing there`, Solaris lists one CPU and QEMU burns one host
core (the second vCPU is never started); with 1024 MB Solaris reports `Memory size: 512 Megabytes`.
A disk installed with OpenBIOS on SS-20 boots with the Sun SS-20 PROM and the reverse (both SS-20,
`-cpu TI-SuperSparc-50` for the PROM); the SS-10 OpenBIOS install boots on SS-20 too. An SS-5 install doesn't boot on SS-10/SS-20 (above).

The 2.6 CD on SS-20 with one CPU and 256 MB sometimes stops after `Configuring devices...` /
`fdintr: nobody sleeping (c0 0 0)`, the CPU in the kernel's `idle` loop (an interrupt that never comes):
2 of 2 such cases in one `machines` run (OpenBIOS and the Sun PROM), 1 of 6 boots in a row on an idle
host, 0 of 18 with other guests running. Installed disks didn't show it (33 benchmark boots).

`-cpu` other than the machine's default, booting the installed 2.6 with OpenBIOS: SS-5 boots only
with its default `Fujitsu-MB86904`; `TI-MicroSparc-I` stops QEMU (`Trap 0x21 (Instruction Access
Error)`), `TI-MicroSparc-II`, `-IIep` and `Fujitsu-MB86907` with `Trap 0x29 (Data Access Error)` at
`pc f00412f4`, `TI-SuperSparc-II` hangs OpenBIOS after `Not a bootable ELF image`. SS-20 boots with
`TI-SuperSparc-II` (default), `-50`, `-51`, `-60`; `-40`, `-61` and `Fujitsu-MB86904` stop QEMU with
`Trap 0x29` at `pc f00412f4`.

**Other guests on SS-20** (OpenBIOS unless stated):

| Guest | Result |
| --- | --- |
| Solaris 2.5.1 CD (`CDROM_AS=hd`) | installer (terminal type question), OpenBIOS and `ss20_v2.25_rom` (-50) |
| Solaris 7 (3/99) CD | language question, SS-5 and SS-20; scripted End User install through PVE boots to login on both (`lab.py install sol7-ss5`/`sol7-ss20`, `e2e/sparc/README.md`, "Solaris 7, 8 and 9") |
| Solaris 8 (1/01) Installation CD | Web Start's first question (`Do you want to format /dev/dsk/c0t3d0?`), SS-5 and SS-20; it needs a Sun-labelled disk, a blank one ends in `No Hard disks found on the system.` Its reboot into the mini-root (`reboot -- <slice>`) loses the boot string under OpenBIOS (below, "Known gaps"); with `auto-boot?=false` and the slice booted by path, Web Start (command line mode) installs the Entire Group from Software 1 and 2 of 2 on SS-20, and it boots to login (`sol8-ss20`) |
| Solaris 9 DVD | language menu, SS-5 and SS-20; on SS-20 Web Start installs End User and the installed 32-bit kernel boots to login, although Sun dropped sun4m after 8 (`sol9-ss20`) |
| NetBSD 11.1, SS-5 disk | boots on SS-20; GENERIC attaches one CPU (`cpu at mainbus0 not configured`, `hw.ncpu = 1`) and `apc0`, idles at 2.4% of a core with `-smp 2` |
| NetBSD 11.1 GENERIC.MP (from the ISO) | `-smp 2`: `cpu0: booting secondary processors: cpu1`, `hw.ncpu = 2`; five 16-256 MB writes with `sync` pass; idle ~4% of a core |

**SMP** (before 0019; the cause and the fix are under "SMP" below). Solaris 2.6 on SS-20 with
OpenBIOS brings up every CPU (`psrinfo`: 2 or 4 on-line, OpenBIOS `CPUs: 4 x TI,TMS390Z55`), but it
wasn't stable:

| CPUs | RAM | What happened |
| --- | --- | --- |
| 2 | 256 | 256 MB `dd` + `sync`: hung in 4 of 4 tries (writes up to 128 MB passed); bench runs (64 MB): 3 of 3 passed |
| 2 | 512 | hung once during boot (`volume management starting.`); bench runs: 3 of 3 passed |
| 2 | 256 | `SOAK=300` (2 shells looping the job and a 10 MB `dd`): hung within the first minute; the same with one CPU ran the 300 s |
| 2 | 256 | `TI-SuperSparc-50` and `-60`: 256 MB write hung too; `-40` stops QEMU at boot |
| 2 | 256 | `-accel tcg,thread=single`: hung at boot after `Configuring the /devices directory`, same place as below |
| 4 | 256 | bench: 1 of 3 passed; one hung in `prtconf` right after login, one in the 64 MB write |
| 4 | 512 | bench runs (64 MB): 3 of 3 passed |

Every hang looks the same: no answer on the console, all vCPUs at 100%, one CPU in
`xc_sync_cache+0x1a0` (waiting for the other CPU to acknowledge a cross-call), the other CPU looping
in `splx`/`splr`. Not a multi-threaded TCG race (single-threaded TCG hangs the same way), not the CPU
variant; NetBSD's MP kernel survives the same writes. Fixed by 0019 ("SMP").

**Benchmark** (`scenarios/bench.py`, one QEMU on an idle 14-core host, 3 boots each, median and
range; host seconds): `job` = `nawk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}'`,
`parallel` = that many copies at once as CPUs, `write` = 64 MB `dd` to /export/home + `sync`, `read`
= 64 MB `dd` from the raw slice, `boot` = QEMU start to `console login:`; host CPU in % of one core.

| Configuration | job s | parallel s | write s | read s | boot s | host CPU idle | host CPU parallel |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SS-5 OpenBIOS 256 | 47.1 (47.0-47.7) | 47.4 (46.8-47.6) | 1.9 (1.8-1.9) | 0.6 (0.6-0.7) | 58.6 (57.9-59.0) | 102 | 101 |
| SS-5 `ss5.bin` 256 | 47.9 (47.7-48.2) | 47.8 (47.4-49.4) | 1.9 (1.8-1.9) | 0.6 (0.6-0.7) | 59.4 (59.3-60.6) | 102 | 101 |
| SS-10 OpenBIOS 256 | 5.2 (5.2-5.3) | 5.2 (5.1-5.2) | 1.7 (1.7-1.8) | 0.3 | 55.7 (55.6-58.4) | 102 | 101 |
| SS-20 OpenBIOS 1 CPU 256 | 5.1 (5.0-5.2) | 5.1 (5.0-5.3) | 1.7 (1.7-1.8) | 0.3 | 57.2 (56.2-57.5) | 102 | 101 |
| SS-20 OpenBIOS 1 CPU 512 | 5.3 (5.3-5.4) | 5.4 (5.2-5.4) | 1.8 (1.7-1.8) | 0.3 | 58.2 (57.9-58.6) | 102 | 101 |
| SS-20 OpenBIOS 2 CPUs 256 | 8.6 (8.5-9.4) | 6.7 (6.4-6.8) | 2.8 (2.6-2.9) | 0.4 | 57.5 (56.9-57.9) | 198 | 198 |
| SS-20 OpenBIOS 2 CPUs 512 | 8.3 (8.2-8.6) | 6.2 (6.2-6.3) | 2.7 (2.6-2.7) | 0.4 (0.3-0.4) | 57.6 (56.6-58.0) | 198 | 199 |
| SS-20 OpenBIOS 4 CPUs 256 | 16.1 (16.0, 16.2) | 11.0 (10.7, 11.3) | 5.2 (1 run) | 0.7 (1 run) | 59.4 (58.3-62.3) | 340 | 360 |
| SS-20 OpenBIOS 4 CPUs 512 | 14.8 (14.8-15.3) | 10.9 (10.0-11.0) | 4.2 (4.0-4.6) | 0.5 (0.5-0.6) | 59.4 (58.4-72.1) | 342 | 359 |
| SS-20 `ss20_v2.25_rom` -50 256 | 5.3 (5.2-5.6) | 5.3 | 2.0 (1.9-2.1) | 0.3 | 57.8 (57.7-58.3) | 102 | 101 |
| SS-20 `ss20_v2.25_rom` -50 512 | 5.3 (5.2-5.4) | 5.2 (5.2-5.4) | 1.7 (1.7-1.8) | 0.3 | 57.9 (57.8-58.3) | 102 | 101 |

With 0014-0015 (`solaris-idle`), the same benchmark on fresh copies of the installed disks (`boot` includes
the first-boot questions, so it isn't comparable with the table above), 11.1.3-2+wsh5 against the
same package with 0014-0016, alternating, one CPU, OpenBIOS, 256 MB:

| Configuration | job s | parallel s | write s | read s | boot s | host CPU idle | host CPU parallel |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SS-20, wsh5 (3 boots) | 5.3 (5.2-5.6) | 5.1 (5.1-5.3) | 1.9 (1.8-2.0) | 0.3 | 111.4 (110.9-111.4) | 102 | 101 |
| SS-20, with 0014-0016 (3 boots) | 5.1 (5.0-5.2) | 5.0 (5.0-5.3) | 1.8 (1.8-1.9) | 0.3 (0.3-0.4) | 111.4 (110.0-111.6) | 3.3 | 69 |
| SS-5, wsh5 (2 boots) | 47.4, 50.2 | 47.6, 49.1 | 1.8, 2.0 | 0.7 | 113.9, 115.6 | 102 | 101 |
| SS-5, with 0014-0016 (3 boots) | 47.1 (46.8-48.2) | 48.1 (47.7-50.7) | 2.1 (1.9-3.7) | 0.7 (0.7-0.8) | 114.1 (113.7-115.0) | 3.4 | 96 |
| SS-5, with 0014-0016, `solaris-idle=off` | 47.8 | 46.5 | 1.8 | 0.6 | 114.4 | 102 | 101 |

The jobs, disk times and boot are the same within the noise (the one 3.7 s SS-5 write didn't come
back in two more boots). "Host CPU parallel" drops because the guest idles for part of the timed
window (shell start, terminal output) where it used to spin. `SOAK=300` on SS-20 with `solaris-idle`
passed (job 5.1 s after it); with `solaris-idle`, 4 SS-20 and 5 SS-5 (2.6 and 2.5.1) boots to login
ended in a clean `init 5`.

- One CPU: SS-10 and SS-20 run the job 9x faster than SS-5; firmware and 256 vs 512 MB make no
  difference. Disk I/O is the same within 0.3 s; boot time (~57 s) is the same everywhere (mostly
  fixed waits, not CPU).
- More CPUs: one job gets slower (1.7x with 2 CPUs, ~3x with 4), several at once finish sooner than
  one after another on one CPU (2 jobs: 6.5 s vs 10.2 s; 4 jobs: 10.9 s vs 20.4 s), writes take
  longer, and each idle vCPU burns a host core (`solaris-idle` is off with more than one CPU). And it
  hung (above; fixed by 0019, measured again with it under "SMP").

**Why SS-5 was slower** (fixed by 0017; the numbers in this section and the one above are without
it). Times in the guest (`/usr/bin/time`, seconds), one CPU, OpenBIOS:

| Job | SS-5 | SS-20 |
| --- | --- | --- |
| `ksh` integer loop, 30000 rounds (no FPU) | 5.9 | 0.9 |
| `nawk` loop above, 300000 rounds | 14.6 | 1.6 |
| `nawk` `sqrt`/`sin`, 100000 rounds | 4.2 | 0.5 |
| 100 x `/bin/true` + `expr` (user + sys) | 1.1 + 2.4 | 0.6 + 1.7 |
| `dd` 1.3 GB `/dev/zero` to `/dev/null` (kernel) | 1.9 | 1.8 |
| `dd` 64 MB to `/tmp` (tmpfs, kernel) | 1.2 | 1.4 |

User-mode code is 6-9x slower on SS-5, kernel work isn't. During the `nawk` loop the guest takes
~39000 window overflow and as many underflow traps a second (QEMU `log int`), and QEMU counts ~377000
TLB flushes a second (`info jit`; on SS-20 ~100). Solaris's generic window-trap handlers, which it
uses with the microSPARC-II (`_window_overflow`, `_window_underflow`), set and clear the no-fault bit
in the MMU control register around the user-stack access (`sta %g1, [%g0] 0x04` twice per trap), and
QEMU flushes its whole software TLB whenever that bit changes (`target/sparc/ldst_helper.c`,
`ASI_M_MMUREGS` register 0: `if ((oldreg ^ new) & (MMU_NF | mmu_bm)) tlb_flush(cs)`). With a
SuperSPARC, Solaris uses `vik_window_underflow`/`vik_wo_user`, which probe the stack page with an MMU
probe (`lda [...] 0x03`) and write no MMU register. Half the guest PC samples on SS-5 are in
`_window_overflow`. QEMU's CPU models differ only in MMU/FPU version and MXCC (mul/div are on for all),
and NetBSD runs the same awk loop equally fast on SS-5 and SS-20 (1.85 s / 1.80 s). So the gap follows
the Solaris kernel's CPU module, i.e. the CPU model; SS-5 boots only with its microSPARC, so the
machine can't be separated from it. It hits any user program that calls deeper than the register
windows (shells, interpreters, compilers: nearly all), which makes it a general difference for
Solaris 2.6 user-space work, not one kind of operation; compiled loops with shallow call chains
(Dhrystone, Whetstone, nbench) don't reach it ("Benchmarks").

**The fix (0017).** NF decides whether a failed translation traps; it changes no translation that
succeeds. In QEMU 11.1.3 the only TLB entries that depend on it are the ones `sparc_cpu_tlb_fill()`
(`mmu_helper.c`) makes for a failed translation while NF is set or traps are disabled: RWX on a page
the check refused, or redirected to an unassigned address. `get_physical_address()` reads NF only
once the access check has failed, and every such path ends in that branch or a trap. 0017 sets
`env->mmu_nf_entries` there, and the control register write flushes on a change of NF only while
it is set (then clears it). Each bit of the control register, for the CPU models QEMU has
(microSPARC I/II/IIep, MB86904/MB86907, SuperSPARC 40-61/II, LEON; no HyperSPARC model):

| Bit | Read by QEMU | Flush |
| --- | --- | --- |
| E (0) | `cpu_mmu_index()`: MMU off = `MMU_PHYS_IDX`, a TLB of its own; `gen_st_asi()` ends the TB after the write | never (none since QEMU's `MMU_PHYS_IDX`, 2016) |
| NF (1) | the no-fault branch of `sparc_cpu_tlb_fill()`, and `sparc_raise_mmu_fault()` at the time of an access | was: every change; now: a change while an entry from that branch exists |
| boot mode (`mmu_bm`: 0x4000 microSPARC, 0x2000 SuperSPARC, none on LEON) | instruction fetches with the MMU off (`get_physical_address()`) | every change, as before |
| cache enables, store buffer, parity, PSO, snoop, AC, MBus mode, refresh | nothing in `target/sparc` | never, as before |
| implementation/version (31-24) | read only | |

A stale `mmu_nf_entries` only costs one extra flush; CPU reset and `loadvm` flush the TLB anyway,
and the flag isn't migrated (the TLB isn't either). The entries made with traps disabled (`psret ==
0`, NF clear) are flushed at the next NF change as before; nothing else drops them early, as before
(with traps disabled a real CPU would go into error mode on a fault). The context register (reg 2)
keeps its flush: QEMU's TLB isn't tagged with the context, so a context switch has to flush.
`-trace sparc_mmu_ctrl_flush` lists the control register flushes that remain. The qtest
`sun4m-mmu-nofault-test` (0018) checks that an entry made in no-fault mode doesn't survive NF being
cleared; it fails with NF simply dropped from the flush condition.

Solaris writes NF in three places (read from the 2.6 kernel): the generic window overflow and
underflow handlers (used with the microSPARC-II module), the trap entry code when a user window
must be saved for a trap, interrupt or system call (every CPU module), and the illegal-instruction
handler (fetching the user's instruction). The second is most likely why SS-20 gains too (signal
delivery, protection faults, `mmap`, fork; inferred, not traced per path). Other guests on SS-5
with 0017 and `-trace sparc_mmu_ctrl_flush` (the `idle.py` steps: boot, login, `dd`, idle): SunOS
4.1.4 uses NF too (372 flushes after a fault in no-fault mode, its `dd` of 20000 blocks 8.0 s where
the idle table above has 9.7 s; one run); NetBSD 11.1 never sets it (only the boot-time flush).

Flushes with and without 0017 (`info jit`, "TLB full flushes" + "TLB partial flushes"; a flush that
finds not all MMU indexes dirty counts as partial), per host second, one boot per binary and
machine, bench disk parts run one after another (scratch scenario, not in the lab):

| Phase | SS-5 without | SS-5 with | SS-20 without | SS-20 with |
| --- | --- | --- | --- | --- |
| idle at the shell (10 s) | not measured | 3 | 3 | 2 |
| `nawk` loop | 282,000 (64 s) | 490 (7 s) | 700 (8 s) | 330 (8 s) |
| Hanoi (20 s) | 302,000 | 160 | 240 | 115 |
| lmbench subset | 16,200 (147 s) | 4,500 (148 s) | 7,000 (150 s) | 3,600 (150 s) |

The SS-5 run without 0017 had host load ~4 from other guests, so its times are longer than in
"Benchmarks". In the whole run with 0017 (boot, the three parts, `init 5`; ~15 min) the trace showed
7,955 control register flushes, every one NF cleared after a fault in no-fault mode (`0x04050303 ->
0x04050301`), and one at boot (boot mode off, MMU on). What remains in lmbench is mostly context
switches (fork, exec, pipe), on both machines.

**Recommended** (from the data above and "Benchmarks"):

- With 0017, **SS-5, SS-10 and SS-20 run Solaris equally fast** (one CPU, OpenBIOS or the Sun
  PROMs). Pick the machine by what the guest needs: SS-5 for existing SS-5 disks, Solaris 2.4 (Sun
  PROM only) and SunOS 4.1.4; SS-20 (or SS-10) for 512 MB. fork/exec are still ~1.2-1.3x slower on
  SS-5 (not investigated further). Without 0017 (packages up to 11.1.3-2+wsh7), SS-20 runs
  call-heavy user code 4-10x faster than SS-5.
- An SS-20 needs its own install on that machine type (the SS-5 disks don't boot there). 2.5.1, 7,
  8 and 9 installers also start there. With 0014-0015 an idle guest uses ~3% of a host core on
  either. `pmc` is no longer needed to idle on SS-5.
- More than one CPU for Solaris only with 0019 (before, it hangs), on SS-10/SS-20 with OpenBIOS, and
  only for parallel work: one job runs slower and every vCPU takes a host core even when idle ("SMP").
  NetBSD's MP kernel works with 2 CPUs (not benchmarked).
- RAM: 256 MB on SS-5 (QEMU's limit), at most 512 MB on SS-10/SS-20; 512 shows no speed benefit over
  256 in this benchmark.
- The Sun SS-10/SS-20 PROMs only with the SS-20 machine and `-cpu TI-SuperSparc-50` (or -40/-60);
  qemu-server passes -50 for `ss20_v2.25_rom` on SS-20. They bring no speed benefit over OpenBIOS. The
  SS-10 PROM doesn't run on the SS-10 machine.
- Not SS-600MP (Solaris 2.6 refuses it), and none of the other PROMs tried except `ss5-170.bin` and
  `ross225r.bin` (which runs as a SuperSPARC SS-20).

### SMP

**Why Solaris hung with more than one CPU** (fixed by 0019). A hung Solaris 2.6 (SS-20, OpenBIOS,
`-smp 2`, a 256 MB `dd` and `sync`), from the monitor and from gdb attached to QEMU:

- CPU 1 at PIL 13, spinning in `xc_sync_cache` on CPU 0's acknowledgement word.
- CPU 0 in `splr`/`splx`, PIL going between 4, 13 and 15: the loop of a failing `mutex_tryenter` on
  the cross-call mailbox lock that CPU 1 holds (`xc_grab_mutex`; at a PIL below 13 it leaves the
  cross-call to the interrupt handler).
- `info pic`: CPU 0 has soft interrupt 13 pending (`0x20000000`, the cross-call), CPU 1 the system
  timer (level 10; Solaris had moved the interrupt target to CPU 1, which is at PIL 13).
- CPU 0's state in QEMU: `pil_in = 0x2000`, `interrupt_index = 0x1d` (level 13), traps enabled,
  `CPU_INTERRUPT_HARD` requested, not halted. All set for the interrupt whenever PIL is 4, and it is
  never taken.

QEMU looks at pending interrupts only when a vCPU comes back to its main loop; translated blocks
chain into each other without that check. A write to `%psr` ends its block so that the main loop
looks (`DISAS_EXIT`), but in a delay slot that was dropped: the translator turned it into a chained
jump to the branch target. Solaris lowers PIL in a delay slot in `splx`/`splr` (`bl,a 1f; wr %o3,
newpil, %psr`) and raises it with a plain `wr %psr`. So CPU 0 looked at its interrupts only at PIL
15 and never at PIL 4, and nothing else made it look: the timer goes to the other CPU. Setting CPU
0's `icount_decr` from gdb (what a kick does) let the interrupt in, and both CPUs went on. With one
CPU the next timer interrupt does the same within 10 ms, which is why nobody noticed. QEMU before
8.2 emitted the exit in the `wrpsr` code itself and it worked in a delay slot; 8.2 (`25524734c6`)
broke it, in the release that also turned on multi-threaded TCG for sparc (`ec860e5d03`). The
details and the code are in `upstream/qemu-sun4m-smp-psr-delay-slot.md`.

**The fix (0019).** The translator keeps the exit for an instruction in a delay slot: after a
conditional branch it computes the branch at run time into pc/npc instead of chaining both ways;
after `jmpl`/`rett` the PC is in the CPU state already. The only effect is one more exit to the
main loop per such write, i.e. an extra look at pending interrupts, so no guest can depend on the
old behaviour: an interrupt that was unmasked is taken now instead of at the next unrelated exit.
Every sparc32 guest gets it (Solaris, SunOS, NetBSD, Linux, one CPU or more); sparc64 shares the
code but raises its interrupts from the `wrpr %pil` helper and is not affected (only its `membar
#Sync` sets the exit). The qtest `sun4m-pil-delay-slot-test` (0020) raises a soft interrupt at PIL
15 and lowers PIL with a plain `wr %psr` and with one in the delay slot of `ba`, `bne`, `bne,a` and
`jmpl`, after a first round that makes the blocks chain; without 0019 the four delay-slot cases fail,
the plain one passes.

**Results** (`qemu-system-sparc` built from the series with and without 0019, in the lab image;
`scenarios/smp-soak.py`, Solaris 2.6 installed on SS-20, OpenBIOS, 256 MB, the bench disk; the host
shared with other agents' guests, 1-minute load 4-11):

| Case | Without 0019 | With 0019 |
| --- | --- | --- |
| SS-20, 2 CPUs, `bench.py DISK_MB=256 SOAK=600` (256 MB `dd` + `sync`, then 600 s of 2 shells looping the `nawk` job and a 10 MB write) | hung in the write (upstream v8.2.0 unpatched: the same) | passed (write 11.9 s) |
| SS-20, 2 CPUs, `smp-soak.py SOAK=1800` | | passed: 155 rounds of 3 loops, no `cksum` mismatch, both CPUs 100% busy (median of the 60 s `mpstat` samples), 130-460 cross-calls a second per CPU (`xcal`), QEMU 201% of a host core |
| SS-20, 4 CPUs, `SOAK=1800` | | passed: 294 rounds, no mismatch, all four CPUs 99% busy, QEMU 394% |
| SS-10, 4 CPUs, `SOAK=900` | | passed: 155 rounds, no mismatch, 99% busy, QEMU 394% |
| SS-20, 2 CPUs, `-accel tcg,thread=single` | hung at boot (table above) | no hang, but crawling: 42 minutes to the login prompt (2 minutes with one thread per vCPU, the default), two Dhrystone copies at once 72.6 s against 22.1 s for one, and 12 minutes into the soak `psrinfo` took longer than the lab's 120 s to answer (the guest still running); 2 boots |
| SS-20, 4 CPUs, `thread=single` | | Solaris gave up on two CPUs at boot (`WARNING: cpu 2 failed to start`, `cpu 3`) and hadn't got past `Hostname: solaris` after 2 hours (stopped) |
| The 2.5.1 (`CDROM_AS=hd`), 7 (3/99), 8 (1/01 Installation CD, Sun-labelled disk) and 9 install media to the installer's first question, SS-20, 2 and 4 CPUs | | 8 of 8 passed |

Single-threaded TCG is unusable with more than one CPU, fix or not: the vCPUs take turns in one host
thread, and a CPU spinning on a cross-call acknowledgement keeps its time slice while the CPU that
would answer waits for its turn, so every cross-call costs about a slice. QEMU before 8.2 ran sparc
this way (multi-threaded TCG for sparc came with `ec860e5d03`), which is why upstream v8.1.5 with 2
CPUs didn't reach the login prompt in 600 s either (with one CPU it took 116 s). qemu-server never
passes `thread=single`.

**Speed-up** (`smp-soak.py SOAK=0`, with 0019 and without 0023, so the idle CPUs spin; 3 boots per
CPU count, alternating, median; host load 3.6-5.0 from other agents' guests; with 0023 see "Idle with
more than one CPU"). `dhry` = Dhrystone with 20,000,000 runs (fixed work,
shallow calls), `nawk` = the `nawk` loop (deep calls: window traps); "1 job" = one copy alone, "N
jobs" = as many copies as CPUs at once, host seconds; "throughput" = N copies on one CPU one after
another (N x the 1-CPU time) divided by N copies at once on N CPUs:

| CPUs | dhry, 1 job | dhry, N jobs | dhry throughput | nawk, 1 job | nawk, N jobs | nawk throughput | QEMU host CPU, idle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 13.3 s | | 1.0x | 6.2 s | | 1.0x | 3% (`solaris-idle`) |
| 2 | 14.4 s | 14.2 s | 1.87x | 10.4 s | 8.0 s | 1.55x | 198% |
| 4 | 17.7 s | 19.6 s | 2.71x | 17.7 s | 13.0 s | 1.91x | 340% |

- **Parallel work gets faster**: 2 CPUs finish two jobs 1.6-1.9x sooner than one CPU, 4 CPUs four
  jobs 1.9-2.7x sooner. The host pays one core per vCPU whether the guest is busy or idle (busy:
  98-100% per vCPU in the soaks; idle: 198% and 340%, no idle halt with more than one CPU).
- **A single job gets slower** the more CPUs there are: Dhrystone 8% (2 CPUs) and 33% (4), the
  `nawk` loop 68% and 185%. It is the other CPUs' idle loop: with CPUs 1-3 of a 4-CPU guest taken
  off-line (`psradm -f 1 2 3`; an off-line CPU spins on its flags instead of polling the other
  CPUs' run queues in `disp_getwork()`), the `nawk` loop took 8.6-8.8 s instead of 18.4-18.7 s (one
  CPU: 6.2 s). Why that polling slows the busy vCPU this much under QEMU wasn't traced; the halt in
  the multiprocessor idle loop (0023, "Idle with more than one CPU" below) removes it.
- Writes get slower too (64 MB `dd` + `sync`: 1.8-2.8 s with one CPU, 3.7 s with 2, 6.2 s with 4;
  one boot each).
- So more than one CPU pays only for guests that run several CPU-bound processes at once (builds,
  batch jobs); for one interactive user one CPU is faster and idles at 3% instead of 100% per vCPU.

**One CPU** loses nothing with 0019: `bench-disk.py` on SS-20 and SS-5 (OpenBIOS) with the binaries
with and without it, one boot each, host load 1.0-2.0: Dhrystone 923.8 / 923.2 (SS-20) and 956.2 /
953.7 (SS-5) VAX MIPS, Hanoi 17837 / 18941 and 19995 / 19575 towers/s, the `nawk` loop 5.1 / 5.1 and
5.1 / 4.7 s, nbench, null syscall, pipe, signal, fork and `sh -c` within the spread of "Benchmarks"
(one outlier: lmbench's TCP connect over `lo0` on SS-5 with 0019, 13.3 ms against ~1.0-1.2 ms in
the other three runs, a test whose spread was already 56% above). The `benchdisk` matrix (6/6) with
0019 is in the range of the "With 0017" table, on a busier host (load ~5).

**Idle with more than one CPU (0023-0025, `solaris-smp-idle`).** `solaris-idle` and `sunos-idle`
stay off with more than one CPU (`smp_cpus == 1` in 0013/0015); before 0023 every vCPU of an idle
guest kept a host core busy: 198% of a core with 2 CPUs and 341% with 4, against 4% with one.

The multiprocessor loop of `idle()` (`uts/common/disp/disp.c`) never calls `idle_cpu`. Each round it
spins while `CPU_QUIESCED` is set, `swtch()`es when its own `disp_nrunnable` is not 0, skips the rest
when `CPU_OFFLINE` is set, and otherwise calls `disp_getwork()`, which takes a thread from the
partition's kernel preemption queue (real-time threads, `setkpdq()`) or from another CPU with more
than one thread queued. Nothing tells an idle CPU that it has work: `setbackdq()`/`setfrontdq()` put a
thread on its queue and count it in `disp_nrunnable`, `cpu_resched()` pokes (soft interrupt) only a CPU
that runs a thread (`!CPU_IDLING`), `set_idle_cpu`/`unset_idle_cpu` do nothing on sun4m, and only one
CPU takes the 100 Hz clock. So a halt until the next interrupt, as with one CPU, could leave work
waiting indefinitely. 0023 halts there with wake-ups of its own:

- **At the call of `disp_getwork`.** The translator recognises it by the 14 words from the load of
  `disp_nrunnable` to the call (registers, offsets and call targets masked, register use checked:
  the base of the load in a local or in register, `cpu_flags` loaded and tested for `CPU_OFFLINE` in
  the same register). The helper halts when `disp_nrunnable` is 0, PSR.ET is set, PIL is 0 and no
  interrupt is pending, after the loop has found nothing for 100 us (the poll of the one-CPU halt; a
  round that comes more than 20 us after the one before starts it again, so a CPU that ran a thread
  in between polls again before it halts).
- **Woken by the CPU that queues work.** Solaris queues a thread at a raised PIL and lowers PIL with a
  `wr %psr` afterwards (`disp_lock_exit`, `splx`); `helper_wrpsr` (which takes the BQL anyway) checks
  the halted CPUs and kicks each whose `disp_nrunnable` is no longer 0, and one of them when the
  writing CPU has more than one thread queued (what `disp_getwork` would take from it). The halting
  CPU sets its bit in the mask of halted CPUs and reads `disp_nrunnable` again after a full barrier;
  the writer reads the mask after a full barrier, so one of the two sees the other. The kick is a
  flag that `sparc_cpu_has_work()` returns, set with the BQL held so the vCPU thread can't miss it.
- **Woken by interrupts**, as with one CPU (cross-calls, pokes, the clock on its CPU).
- **Woken by a 10 ms timer**, for work that reaches the CPU any other way (a real-time thread on the
  kernel preemption queue, a race). `disp_getwork` runs once then and the CPU halts again if it found
  nothing, so a missed wake-up costs at most 10 ms, and an idle vCPU wakes ~100 times a second.
- Either way the CPU goes on at the call of `disp_getwork`. A CPU halted there at migration (or
  `savevm`) is woken on the destination (vmstate subsection `cpu/solaris_idle_mp`, sent only then):
  the destination has neither its timer nor the writer's mask.
- The Solaris idle helpers (one CPU too) now read `disp_nrunnable` through a host pointer looked up
  once by a page table walk. The first version used `probe_access_flags()` like 0014, and QEMU
  aborted at boot (`sparc_cpu_tlb_fill: Assertion '!probe' failed`) when another CPU had flushed the
  TLB entry since the loop's load. With one CPU nothing flushes in between, which is why 0014 never
  hit it.

Disassembled from the install media and the installed 2.6 SS-20 disk (sun4m `unix`, `x/i` in the
QEMU monitor with 2 CPUs; the same kernels as in the one-CPU table under "Idle"):

| Release | Load of `disp_nrunnable` | Call of `disp_getwork` | Layout |
| --- | --- | --- | --- |
| 2.5.1 | `ld [%l7], %l3` (`%l7` = CPU + 0x48) | `0xf0075d14` | `2.5.1` (`tst`, `lduh [%reg]`, `bne` + `nop`) |
| 2.6 | `ld [%i0 + 0x58], %o0` | `0xf006faa8` | `2.6/7/8/9` |
| 7 | `ld [%i0 + 0x54], %o0` | `0xf006e144` | `2.6/7/8/9` |
| 8 | `ld [%i3 + 0x54], %g2` | `0xf006d8e4` | `2.6/7/8/9` |
| 9 | `ld [%l1 + 0x60], %g2` | `0xf006cbb4` | `2.6/7/8/9` |

`-trace sparc_solaris_idle_mp_match` shows the match, `sparc_solaris_idle_mp` each halt and
`sparc_solaris_idle_mp_wake` what ended it (`queued`, `steal`, `timer`, `timer, work queued`).
NetBSD's MP kernel and SunOS don't match and run as before.

At the installer's first question on SS-20 (OpenBIOS, `solaris-boot-cd.py IDLE=30`, 30 s, run beside
other lab guests), each release's kernel matched at the address above and QEMU used, with 2 / 4
CPUs: 2.5.1 (`CDROM_AS=hd`) 3.1% / 4.3%, 7 2.8% / 3.8%, 8 (Installation CD) 5.0% / 5.3%, 9 5.3% /
9.2%. Installed 2.5.1, 7, 8 and 9 with more than one CPU weren't tested (no such disks).

**Results** (`scenarios/smp-idle.py`, Solaris 2.6 installed on SS-20, OpenBIOS, 256 MB, the bench
disk; `qemu-system-sparc` built from the series without 0023-0025 ("before") and with them, mounted
into the lab image; 2 runs each for 2 and 4 CPUs, 1 for one CPU, where "with" is 0014 with the new
read; host load 1.5-4.7 from other agents' guests). Idle = 60 s at the shell 30 s after login;
"timed tests" = everything from `lat_pipe` to the CPU-bound jobs; `burst` = 3 x (max(N, 2) short
`nawk` jobs at once); `dhry`/`nawk` as under "Speed-up" (one copy, then N copies at once; with one CPU
both are one copy):

| | 1 CPU before | 1 CPU with | 2 CPUs before | 2 CPUs with | 4 CPUs before | 4 CPUs with |
| --- | --- | --- | --- | --- | --- | --- |
| QEMU host CPU, idle | 4.0% | 3.5-3.7% | 198% | 4.1-4.3% | 341% | 5.0-5.3% |
| guest clock over 62 s | 0 s | 0 s | 0 s | 0 s, +2 s | 0 s | 0 s |
| echo of `true` / ten `sleep 1` | 50 ms / 10.1 s | 50 ms / 10.0-10.1 s | 50 ms / 10.1 s | 50 ms / 10.1 s | 50 ms / 10.1-10.2 s | 50 ms / 10.1 s |
| `lat_pipe` | 87 us | 89-95 us | 94-98 us | 98-101 us | 151-153 us | 90-102 us |
| `lat_proc fork` | 1321 us | 1281-1465 us | 1815-1871 us | 1734-1816 us | 2811-2892 us | 2679-3053 us |
| 200 `expr` in a loop | 2.13 s | 2.16-2.17 s | 2.65-2.67 s | 2.62-2.81 s | 4.18-4.27 s | 3.33-3.51 s |
| `dd \| cat \| cat`, 10 MB | 0.69 s | 0.54-0.58 s | 0.30-0.31 s | 0.27-0.33 s | 0.35-0.37 s | 0.27-0.29 s |
| `burst` | 1.79 s | 1.74-2.02 s | 1.12-1.22 s | 1.13-1.15 s | 2.08-2.23 s | 2.11-2.12 s |
| `dhry`, 1 / N jobs | 12.2 / 12.0 s | 11.9-12.5 / 11.9-12.1 s | 12.0-12.9 / 11.9-12.3 s | 12.5-12.6 / 12.5-12.8 s | 13.3-14.2 / 13.4-14.0 s | 12.0-12.4 / 12.7-13.1 s |
| `nawk`, 1 / N jobs | 6.3 / 5.6 s | 5.3-5.4 / 5.2-5.4 s | 8.6-8.7 / 6.5-6.8 s | 5.3-5.4 / 6.6-6.7 s | 15.5-16.5 / 11.0-11.4 s | 5.4-5.6 / 10.6-11.0 s |
| QEMU host CPU, timed tests | 52% | 51-52% | 198% | 74% | 352-353% | 113-115% |

- **Idle**: an idle guest with 2 or 4 CPUs costs about what one with one CPU costs, 4-5% of a core
  instead of one core per vCPU.
- **A single job is no longer slowed down** by the other CPUs: the `nawk` loop alone takes 5.3-5.6 s
  with 2 and 4 CPUs (one CPU: 5.3-6.3 s) instead of 8.6 s and 16 s; Dhrystone, which slowed down
  less, is at its one-CPU time too. Why the polling slowed the busy vCPU wasn't traced. Each round of
  the polling loop writes `%psr` twice in `disp_getwork` (`splhigh`/`splx`), and `helper_wrpsr` takes
  the BQL every time, which is the likeliest cause.
- **Wake-ups**: pipe round trips, `fork`, short processes, pipelines and bursts take as long as before
  with 2 CPUs and less time with 4 (where 3 polling CPUs slowed them down). In a first version a CPU
  that ran a thread for less than 100 us between two idle rounds didn't poll again before halting
  (the poll restarted only after a 100 us gap): `lat_pipe` with 2 CPUs took 111-120 us, and `-trace`
  counted 2,000-2,600 halts a second during `lat_pipe`; with the 20 us rule 230-260, and `lat_pipe`
  takes 98-101 us (before: 94-98 us).
- **Parallel work** is as fast as before with 2 CPUs and a little faster with 4.
- **Wake-up stress** (`smp-idle.py STRESS=600`: N + 1 shell loops of a short `nawk` job, `sleep 1`,
  a pipeline, 10 `expr` and a pipe into `nawk`, `psrinfo` every 60 s; before and with run side by
  side, beside the regression matrices, host load 5.5-7.8): no hang, every CPU on-line, `psrinfo`
  answered in 0.1 s each time. 2 CPUs: 1079 rounds before, 1020 with (-5.5%), QEMU 197% against 99%
  of a core over the stress; 4 CPUs: 1294 and 1297 rounds, 350% against 235%. On a busy host a
  halted vCPU thread takes longer to be scheduled when it is woken, which is the likely cost in the
  2-CPU case; it wasn't measured on an idle host.
- **Guest clock**: one 2-CPU run with 0023 above read the guest 2 s ahead after 62 s (`date`, whole
  seconds); every other run, before and with, and five runs of earlier versions read 0. A check of
  the clock tick itself didn't reproduce it: `lbolt` (through
  `adb -k`) and `date` every 124 s, 3 times per run, idle at the shell, against the host's
  time, before with 2 CPUs and with 0023 with 2 and 4: `lbolt` within 0.03 s (3 ticks) in all nine
  intervals, `date` within its one-second steps (-0.5 to +0.6 s).

**Checks with 0023-0025** (the same binary, run beside each other and other agents' guests):

| Check | Result |
| --- | --- |
| 2.6 SS-20 disk booted to login, `psrinfo` (`solaris-boot-disk.py`), 5 boots each with 1, 2 and 4 CPUs | 15/15 passed |
| 2.5.1, 7, 8, 9 install media to the installer, 2 and 4 CPUs | 8/8 passed, each kernel matched (above) |
| NetBSD 11.1 `GENERIC.MP` (the kernel from the 11.1 ISO on a copy of the installed disk), SS-20, 2 CPUs, `idle.py` | `hw.ncpu = 2`; QEMU 3.5% of a core idle, 3.4% without 0023 (its own APC idle; the recogniser doesn't match) |
| Migration of an idle 2-CPU 2.6 to a file and back (`migrate exec:`, then a new QEMU with `-incoming`) | completed; the destination answered on ttya and idled at 4.1% (5.1% before the migration), both CPUs halting again there |
| `pve` case `sol26-ss20-smp2` (2 CPUs through PVE, the binary bind-mounted over the node's `qemu-system-sparc`) | passed: `psrinfo` 2 on-line, Dhrystone 12.8 s alone and 12.7 s as 2 copies, the `nawk` loop 5.3 s and 6.5 s |
| Stop-A with 2 CPUs (`stop-a.py SMP=2`, SS-20, not in a matrix) | the firmware prompt and `go` work, but the scenario looks only at CPU 0's PC: Solaris enters the PROM on the CPU that took the keyboard interrupt and `prom_idlecpu()` (OpenBIOS) leaves the other running. Round 1 passed with CPU 0 in the PROM and CPU 1 halted at `disp_getwork`; round 2 failed with CPU 1 in the PROM and CPU 0 in a kernel wait loop. Without 0023 the same: 1 of 2 runs failed round 1 (CPU 1 in the PROM, CPU 0 in the idle loop), the other passed. A scenario limit with more than one CPU, not a hang |
| `sun4m-solaris-smp-idle-test`, `sun4m-solaris-idle-test` | 4/4, 5/5 |
| Lab matrices | `smoke` 3/3, `machines` 13/13, `idle` 13/13 (with the 3 new multiprocessor cases; one CPU unchanged: Solaris, SunOS, NetBSD below 10%), `stopa` 9/9, `smp` 3/3 (`SOAK=600` with 2 and 4 CPUs on SS-20 and 2 on SS-10) |

**The profiles** (qemu-server, pve-manager; needs `pve-qemu-kvm` 11.1.3-2+wsh10 or later, the
first package with 0019):

- `$SPARC32_PROFILES` (`PVE::QemuServer::Machine`) has a most-CPUs value per machine and firmware,
  mirrored in pve-manager's `sparc32Profiles` (`Architecture.js`). SS-10 and SS-20 with
  `openbios-sparc32`: 4 (`mc->max_cpus = 4` in QEMU's `hw/sparc/sun4m.c` for both). SS-20 with
  `ss20_v2.25_rom`: 1 (below). SS-5: 1 (QEMU's default `max_cpus` of 1). The default stays one CPU.
- `assert_sparc32_profile` accepts any sockets x cores up to that value: sun4m has no CPU topology,
  QEMU creates that many CPUs and the guest sees each as a CPU module. More is refused with a
  message naming the machine, firmware and limit (`sparc: SS-20 with firmware ss20_v2.25_rom takes
  at most 1 CPU (sockets x cores), not 2 (the Sun PROM starts only the first CPU; openbios-sparc32
  takes up to 4)`). `-smp` is built as for x86 (`N,sockets=S,cores=C,maxcpus=N`), which QEMU's sun4m
  takes; never `-accel tcg,thread=single`. No CPU hotplug: `vcpus` other than sockets x cores is
  refused, and so is `cpu` in `hotplug` with more than one CPU (with one, the command is the same
  either way, so existing configs stay valid); a CPU count changed on a running VM stays pending.
- qemu-server never passes `solaris-idle` or `sunos-idle`: they are on by QEMU's default and 0013/0015
  turn them off by themselves with more than one CPU, so the command line names no idle option
  that would do nothing. The same goes for `solaris-smp-idle` (0024), which does nothing with one CPU.
- pve-manager: sockets and cores enabled on the CPU tab and in Hardware → Processors only for SS-10
  and SS-20 with OpenBIOS, capped at 4 in total (both fields refuse a product above it); reset to
  one and disabled when the machine or firmware changes to one with a limit of 1. A hint says that
  Solaris sees each vCPU as a CPU of its own, that each takes a host core even while the guest is
  idle, and that one job runs slower than with one CPU (true before pve-qemu 0023; the hint is to be
  updated once the qemu-server/pve-manager rework in #289 is in). `vcpus` stays disabled.
- The minimum `pve-qemu-kvm` is documented, not enforced. qemu-server's `debian/control` keeps
  Proxmox's `pve-qemu-kvm (>= 11.0.3-3)`: this repository has never raised it for a feature that
  needs a newer QEMU (the sparc profiles, cg3, idle and floppy all didn't), and a version relation
  can't say "has wsh patch 0019" anyway (a later Proxmox `pve-qemu-kvm` such as 11.1.3-3 would
  satisfy `>= 11.1.3-2+wsh10` without it). One CPU stays the default, so nobody gets more without
  choosing it; a runtime probe of the QEMU binary was left out as the wrong tool in qemu-server.

**Why the Sun PROM profile stays at one CPU.** The SS-20 PROM (OBP 2.25) doesn't learn the CPU
count from QEMU: only OpenBIOS reads it from fw_cfg (`FW_CFG_MAX_CPUS`). According to the documented
disassembly of OBP 2.25 in MiSTer-devel/SunSparcStation20_MiSTer (`docs/rom-disassembly/ss20-obp-2.25/`,
GPL-2.0-or-later; that FPGA SS-20 runs Solaris 8 and NetBSD on two CPUs under the Sun PROM), the PROM
expects every CPU module to run from reset, read its own MBus module ID from the MSI's MID register
(physical `0xf_e000_2000`, IDs 8-11), report through per-CPU mailboxes in the NVRAM, and be stopped
and started through the MSI arbiter-enable register (`0xf_e000_1008`). QEMU keeps the secondary CPUs
halted until they are started the way OpenBIOS does it, so the PROM's probe of the other modules
times out (`Cpu #1 Nothing there`, "SS-10 and SS-20"). This was read there, not verified on QEMU.
Making it work would mean changing QEMU's sun4m: under a Sun PROM start all CPUs from reset, add the
MID register and the arbiter's stop/start semantics. A possible later item, not a small one; no code
from that repository is in this one.

**512 MB on SS-10/SS-20, an unverified lead.** The same README says their OpenBIOS build splits the
memory into several `/memory` entries because older ones list all memory in one entry and Solaris 8
panics early. Solaris 2.6 panicking at boot with more than 512 MB under OpenBIOS ("SS-10 and SS-20")
may be the same thing; not tried.

### Benchmarks

Recognised period benchmarks from the lab's bench disk (`e2e/sparc/README.md`, "The bench disk";
versions, sources, flags and parameters in `e2e/sparc/bench/README`): Dhrystone 2.1, Whetstone
(double precision), the BYTE UNIX Benchmarks' Towers of Hanoi (recursive, 10 disks), nbench/BYTEmark
2.2.3 (`MINSECONDS=2`), a fixed lmbench 3.0-a9 subset and the `nawk` loop from above. The same
binaries everywhere: gcc 2.95.3, `-O2 -mcpu=v8`, static. The `benchdisk` matrix, pve-qemu-kvm
11.1.3-2+wsh7, Solaris 2.6 (5/98) unless stated, one CPU, 256 MB, one bench QEMU at a time on the
14-vCPU lab host (a VM on an i9-9900K), 3 runs of 50 minutes, all 18 cases passed. The host's
1-minute load during the runs, the bench QEMU's own ~1 included: median 1.7, 1.4 and 1.0 (max 3.6,
2.5 and 3.0); other QEMU guests ran beside runs 1 and 2, the start of a package build beside run 3, no
CI lab run. Median and spread ((max - min) / median) of the 3 runs; "SS-5 slower" = SS-5 OpenBIOS
against SS-20 OpenBIOS (time ratio, or rate ratio inverted); us = microseconds.

| Benchmark | Unit | SS-5 OpenBIOS | SS-5 `ss5.bin` | SS-10 OpenBIOS | SS-20 OpenBIOS | SS-20 `ss20_v2.25_rom` | 2.5.1, SS-5 `ss5.bin` | SS-5 slower |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhrystone 2.1 | VAX MIPS | 950 (15%) | 938 (6%) | 929 (3%) | 939 (4%) | 942 (6%) | 963 (6%) | 1.0x |
| Whetstone | MWIPS | 432 (8%) | 423 (5%) | 433 (3%) | 432 (4%) | 435 (1%) | 432 (5%) | 1.0x |
| Hanoi, 10 disks | towers/s | 4588 (8%) | 4777 (5%) | 18746 (3%) | 19466 (2%) | 19117 (2%) | 4949 (5%) | 4.2x |
| `nawk` loop | s | 48.7 (5%) | 50.3 (6%) | 5.2 (8%) | 5.1 (2%) | 5.1 (2%) | 47.6 (2%) | 9.5x |
| nbench integer index | K6/233 = 1 | 3.97 (7%) | 4.17 (3%) | 4.20 (4%) | 4.23 (3%) | 4.22 (6%) | 4.22 (2%) | 1.1x |
| nbench FP index | K6/233 = 1 | 1.74 (2%) | 1.77 (5%) | 1.78 (1%) | 1.80 (1%) | 1.78 (4%) | 1.78 (3%) | 1.0x |
| nbench memory index | K6/233 = 1 | 4.06 (4%) | 4.18 (7%) | 4.31 (1%) | 4.30 (3%) | 4.26 (3%) | 4.26 (2%) | 1.1x |
| lmbench null syscall | us | 0.44 (17%) | 0.40 (35%) | 0.40 (5%) | 0.38 (6%) | 0.39 (7%) | 0.40 (3%) | 1.2x |
| read / write | us | 1.83 / 1.64 | 1.84 / 1.67 | 1.91 / 1.66 | 1.78 / 1.62 | 1.79 / 1.59 | 1.29 / 1.01 | 1.0x |
| stat | us | 4.6 (39%) | 4.5 (35%) | 4.3 (9%) | 4.3 (5%) | 4.3 (4%) | 5.3 (7%) | 1.1x |
| open/close | us | 54.5 (7%) | 52.9 (55%) | 11.2 (30%) | 10.1 (5%) | 9.4 (11%) | 44.7 (11%) | 5.4x |
| signal install / catch | us | 1.15 / 62.9 | 1.23 / 63.0 | 1.22 / 41.5 | 1.04 / 40.2 | 1.07 / 38.9 | 1.03 / 58.7 | 1.1x / 1.6x |
| protection fault | us | 12.6 (17%) | 9.0 (107%) | 16.1 (8%) | 14.6 (64%) | 14.4 (18%) | 15.5 (43%) | 0.9x |
| pipe latency | us | 115 (8%) | 117 (13%) | 84 (10%) | 85 (5%) | 83 (2%) | 100 (10%) | 1.4x |
| fork+exit | us | 2018 (8%) | 2069 (24%) | 1476 (18%) | 1473 (10%) | 1466 (2%) | 1985 (1%) | 1.4x |
| fork+execve | us | 2984 (11%) | 3057 (19%) | 2507 (22%) | 2496 (18%) | 2546 (11%) | 3085 (11%) | 1.2x |
| fork+/bin/sh -c | us | 20322 (12%) | 21198 (29%) | 15307 (10%) | 14152 (20%) | 15467 (9%) | 21628 (8%) | 1.4x |
| page fault | us | 218 (1%) | 220 (12%) | 209 (9%) | 206 (1%) | 210 (6%) | 226 (4%) | 1.1x |
| mmap 8 MB | us | 3355 (4%) | 3315 (19%) | 2613 (3%) | 2352 (10%) | 2585 (23%) | 3177 (5%) | 1.4x |
| file reread 8 MB | MB/s | 556 (7%) | 556 (5%) | 945 (6%) | 968 (7%) | 998 (7%) | 1004 (4%) | 1.7x |
| memory read / write 4 MB | MB/s | 12622 / 16910 | 12203 / 16079 | 13705 / 16036 | 8640 / 16122 | 14468 / 15787 | 15028 / 16014 | 0.7x / 1.0x |
| bcopy 4 MB | MB/s | 1121 (10%) | 1130 (11%) | 1050 (5%) | 1096 (11%) | 1038 (9%) | 1122 (3%) | 1.0x |
| memory latency 8 MB | ns | 19.6 (35%) | 16.6 (22%) | 13.7 (36%) | 12.1 (46%) | 16.8 (15%) | 12.0 (40%) | 1.6x |
| file create / delete (0k) | files/s | 906 / 1872 | 975 / 1904 | 1081 / 2159 | 1066 / 2105 | 1071 / 2103 | skipped | 1.2x / 1.1x |

The individual nbench tests, lmbench's raw output and the `uname`/`psrinfo` of each case are in each
case's `bench.txt` and `result.json`. Boot to login (fresh disks, first-boot questions included) took
110-115 s everywhere (2.5.1: 71 s), `run.sh` 330-430 s.

- **Where the SS-5 gap is, and where not.** Dhrystone, Whetstone and nbench run as fast on SS-5 as on
  SS-20 (ratio 1.0-1.1, within the spread): compiled code whose call chains fit the 8 register
  windows rarely takes a window trap, so it never reaches the microSPARC trap handlers' MMU-control
  writes and QEMU's TLB flushes ("Why SS-5 was slower"). Code that calls deeper does: Hanoi (calls ten
  deep) 4.2x, the `nawk` loop 9.5x, and in the kernel open/close 5.4x, file reread 1.7x, signal
  delivery 1.6x, pipe, fork, `sh -c` and mmap ~1.4x. The plain system-call entry (null, read, write:
  1.0-1.2x, within the spread), page faults and bcopy are about the same. These are the numbers the SS-5 TLB-flush fix should move
  (Hanoi, `nawk`, open/close, file reread first) while Dhrystone, Whetstone and nbench stay as they
  are. They did: "With 0017" below.
- **Firmware and machine don't matter**: `ss5.bin` vs OpenBIOS on SS-5, the Sun SS-20 PROM vs
  OpenBIOS, SS-10 vs SS-20 are within the spread everywhere. Solaris 2.5.1 on SS-5 behaves like 2.6
  on SS-5 (same CPU-bound numbers and gap; its read/write are a little faster).
- **Noise**: the CPU-bound numbers spread 2-8% (Dhrystone up to 15% in one case); single lmbench
  latencies have outliers of 30-100% (protection fault, open/close with `ss5.bin`, read/write): a
  regression check should look at the medians of several runs, or at the large ratios. Memory
  read/write/latency at 4-8 MB are the host's caches (QEMU models no cache or memory timing), not a
  property of the guest machine.

**With 0017** (the SS-5 TLB fix, "Why SS-5 was slower"). Two `qemu-system-sparc` binaries built
from the same tree (11.1.3 with the series up to 0016, and the same plus 0017), the same configure
flags, run in the lab image with the binary mounted over the package's ("Build" in
`e2e/sparc/README.md`); the `benchdisk` cases, 3 runs each, alternating "without" (SS-5 OpenBIOS,
SS-20 OpenBIOS, 2.5.1) and "with" (all six cases), 2026-11-16. Each run waited for a 1-minute load
below 2.5 first; another agent's QEMU guests ran on the host throughout (load at the case starts
1.3-2.7, at the ends up to 3.0). Median (spread); "with 0017" columns for every case, "without"
for three:

| Benchmark | Unit | SS-5 OpenBIOS without | SS-5 OpenBIOS with | SS-5 `ss5.bin` with | SS-10 with | SS-20 OpenBIOS without | SS-20 OpenBIOS with | SS-20 PROM with | 2.5.1 SS-5 without | 2.5.1 SS-5 with | SS-5 / SS-20 with |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhrystone 2.1 | VAX MIPS | 947 (2%) | 918 (1%) | 945 (2%) | 954 (11%) | 971 (1%) | 959 (6%) | 932 (5%) | 963 (3%) | 931 (5%) | 1.0x |
| Whetstone | MWIPS | 444 (2%) | 428 (2%) | 432 (1%) | 430 (8%) | 432 (2%) | 432 (2%) | 433 (4%) | 439 (1%) | 436 (1%) | 1.0x |
| Hanoi, 10 disks | towers/s | 4834 (3%) | 18927 (6%) | 18078 (11%) | 18345 (5%) | 19512 (10%) | 18137 (6%) | 17767 (13%) | 4833 (1%) | 18036 (1%) | 1.0x |
| `nawk` loop | s | 47.1 (1%) | 5.1 (10%) | 5.0 (8%) | 5.0 (0%) | 5.4 (7%) | 5.1 (14%) | 5.2 (15%) | 47.3 (5%) | 5.1 (14%) | 1.0x |
| nbench integer / FP / memory | K6/233 = 1 | 4.24 / 1.78 / 4.29 | 4.10 / 1.74 / 4.25 | 4.07 / 1.73 / 4.17 | 4.15 / 1.76 / 4.24 | 4.24 / 1.76 / 4.27 | 4.22 / 1.75 / 4.30 | 4.04 / 1.72 / 4.22 | 4.20 / 1.75 / 4.32 | 4.15 / 1.74 / 4.30 | 1.0x |
| lmbench null syscall | us | 0.40 (7%) | 0.41 (11%) | 0.38 (2%) | 0.44 (14%) | 0.39 (10%) | 0.40 (3%) | 0.39 (18%) | 0.41 (7%) | 0.41 (15%) | 1.0x |
| read / write | us | 1.81 / 1.51 | 1.87 / 1.57 | 1.80 / 1.63 | 1.92 / 1.36 | 1.31 / 1.08 | 1.80 / 1.59 | 1.78 / 1.63 | 1.27 / 1.02 | 1.21 / 1.00 | 1.0x |
| stat | us | 4.4 (2%) | 4.3 (16%) | 4.4 (9%) | 4.2 (2%) | 4.2 (4%) | 4.5 (4%) | 4.3 (3%) | 5.5 (26%) | 5.2 (6%) | 1.0x |
| open/close | us | 52.6 (11%) | 11.0 (18%) | 10.2 (24%) | 10.3 (37%) | 8.2 (28%) | 10.0 (2%) | 10.0 (19%) | 45.2 (12%) | 7.2 (8%) | 1.1x |
| signal install / catch | us | 1.14 / 60.4 | 1.08 / 13.5 | 1.09 / 13.3 | 1.16 / 13.8 | 1.08 / 39.0 | 1.13 / 13.4 | 1.07 / 13.8 | 1.01 / 60.4 | 1.00 / 14.6 | 1.0x |
| protection fault | us | 12.8 (8%) | 3.1 (46%) | 3.4 (49%) | 4.7 (34%) | 13.0 (12%) | 3.1 (37%) | 2.8 (55%) | 12.5 (27%) | 1.9, 1.1 (2 runs) | 1.0x |
| pipe latency | us | 125 (21%) | 86 (4%) | 82 (13%) | 90 (36%) | 83 (5%) | 89 (3%) | 85 (17%) | 95 (6%) | 77 (8%) | 1.0x |
| fork+exit | us | 1824 (7%) | 1595 (5%) | 1584 (5%) | 1192 (87%) | 1427 (6%) | 1223 (7%) | 1264 (22%) | 2032 (9%) | 1700 (11%) | 1.3x |
| fork+execve | us | 2906 (13%) | 2601 (5%) | 2572 (7%) | 2125 (61%) | 2258 (21%) | 2164 (13%) | 2067 (5%) | 3006 (4%) | 2497 (4%) | 1.2x |
| fork+/bin/sh -c | us | 18867 (5%) | 14574 (8%) | 13470 (7%) | 12034 (67%) | 15218 (9%) | 12275 (3%) | 12944 (5%) | 21356 (13%) | 16514 (7%) | 1.2x |
| page fault | us | 217 (11%) | 206 (6%) | 207 (6%) | 199 (24%) | 208 (7%) | 200 (6%) | 196 (4%) | 220 (3%) | 216 (9%) | 1.0x |
| mmap 8 MB | us | 3365 (13%) | 1300 (32%) | 1109 (13%) | 1136 (55%) | 2428 (4%) | 1148 (15%) | 1093 (16%) | 3350 (2%) | 1216 (19%) | 1.1x |
| file reread 8 MB | MB/s | 569 (7%) | 921 (30%) | 924 (20%) | 966 (32%) | 960 (9%) | 947 (10%) | 1079 (14%) | 979 (5%) | 895 (26%) | 1.0x |
| bcopy 4 MB | MB/s | 1062 (5%) | 1001 (10%) | 1052 (5%) | 1123 (28%) | 1088 (8%) | 1068 (14%) | 1092 (11%) | 1126 (8%) | 1132 (1%) | 1.1x |
| file create / delete (0k) | files/s | 1074 / 2089 | 1004 / 2051 | 1049 / 2039 | 1096 / 2115 | 1133 / 2117 | 1098 / 2012 | 1014 / 2007 | skipped | skipped | 1.1x / 1.0x |

Memory read/write/latency left out (host caches, see "Noise"). 26 of 27 cases passed; the one
failure was 2.5.1 with 0017 in run 2: `BENCH-ERROR lm_prot_fault` with no output. lmbench reports
the protection fault as the time of a fault plus signal catch minus the time of a signal catch
(`lat_sig.c`), and its `micro()` prints nothing when that comes to 0 (`lib_timing.c`: `if (micro ==
0.0) return;`); with 0017 the remainder is 1-5 us with a spread of 35-80%, so a run can hit 0. The
other two 2.5.1 runs gave 1.9 and 1.1 us. It happens without 0017 too: 15 rounds of `lat_sig catch`
and `lat_sig prot` on 2.5.1 (SS-5, `ss5.bin`) gave no protection-fault line in 2 rounds without
0017 (the others 1.4-26 us, catch 56-69 us) and in 4 rounds with it (1.3-5.7 us, catch 13.6-23
us); every round ended normally.

- **The SS-5 gap is closed.** Hanoi 4.0x → 1.0x, the `nawk` loop 8.7x → 1.0x (47.1 s → 5.1 s),
  open/close 6.4x → 1.1x (SS-5 / SS-20 OpenBIOS in these runs), file reread, pipe and signal delivery the same as SS-20. 2.5.1 on SS-5
  gains the same. Dhrystone, Whetstone, nbench, null/read/write, page faults and bcopy didn't move
  (within the spread; Dhrystone with 0017 is 2-3% lower on SS-5 in the medians, within the spread of
  the other cases).
- **SS-20 gains too**, where Solaris's common trap entry saves a user window with NF set: signal
  catch 39.0 → 13.4 us, protection fault 13.0 → 3.1 us, mmap 2428 → 1148 us, fork 1427 → 1223 us,
  `sh -c` 15218 → 12275 us.
- **What remains**: fork, exec and `sh -c` are 1.2-1.3x slower on SS-5 than on SS-20, with and
  without 0017 in the same proportion, as in the table above; not investigated (the flush rate in
  lmbench is 4,500/s on SS-5 and 3,600/s on SS-20 with 0017, mostly context switches).
- **Soak** (with 0017, a scratch scenario, not in the lab): rounds of three concurrent jobs (a `tar`
  of the bench disk through `compress`/`uncompress`, 300,000 `nawk` lines through `sort -n`, a
  300-step `expr` fork loop), each with `cksum`s, then `fsck -n` of `/export/home` (unmounted) and
  of `/`. With 64 MB of RAM, so that the guest pages and window spills hit missing stack pages (the
  no-fault path that still flushes): Solaris 2.6 on SS-5 (OpenBIOS) 30 rounds in 25 min, 75,951
  flushes after a fault in no-fault mode, every round the same checksums as SS-20 (5 rounds, 256 MB),
  both `fsck -n` clean. Solaris 2.5.1 on SS-5 (`ss5.bin`) the same: 30 rounds, 165,864 such
  flushes, the same checksums, `/export/home` clean; `fsck -n` of the mounted `/` reports three
  unreferenced directories (inodes 15618, 23595, 23664) and the superblock state, exactly as on a
  fresh boot of that disk without 0017 and without the soak, so that is the installed disk, not
  the soak.

**Against the real machines.** Published figures (the Sun ones are from sales material and not
labelled as Dhrystone 1.1 or 2.1, Sun's compilers; approximate as a comparison):

| Measure | Real machine | Emulated (above) |
| --- | --- | --- |
| Dhrystone "MIPS" | SS-5/70 100.3, SS-5/85 112.5, SS-20/50 142.3, SS-20/61 167.4 [1] | ~940 VAX MIPS (Dhrystone 2.1) on all: ~6.6x an SS-20/50, ~8x an SS-5/85 |
| SPECint92 | SS-5/110 (microSPARC-II 110 MHz) 78.6 [2], SS-20/50 69.2-72.0 [1, 3] | not measured: the real SS-5/110 and SS-20/50 were within ~15% of each other in integer code, where the emulated SS-5 is equal in compiled loops but 4-10x slower in call-heavy code |
| null system call | 9 us (write to /dev/null) [4] | 1.6 us (write) |
| fork+exit / +execve / +sh -c | 14 / 69 / 281 ms [4] | 1.5 / 2.5 / 14 ms (SS-20), 2.0 / 3.0 / 20 ms (SS-5), static binaries |
| pipe latency | 278 us [4] | 85 us (SS-20), 115 us (SS-5) |
| file create / delete (0k, UFS) | 25,000 / 11,111 us each [4] | ~0.9 / ~0.5 ms each |
| memory read / write, latency | 38 / 31 MB/s (8 MB), 1236 ns [4] | ~13,000 / ~16,000 MB/s, ~15 ns (host caches) |

[1] Sun Microsystems price list figures, July 1994, in the sun-managers summary "Need MIPS ratings"
(1995, https://sunmanagers.org/1995/0166.html), including SPECint92 for SS-20/50 72.0.
[2] SPEC CINT92 result, SPARCstation 5 Model 110, Apogee C 3.051
(https://netlib.org/performance/html/spec.sun511_1.cint92.6_95.notes.html).
[3] SPEC CINT92 summary table (https://netlib.org/performance/html/spec.cint92.6_94.col0.html).
[4] McVoy and Staelin, "lmbench: Portable tools for performance analysis", USENIX 1996, Sun
SC1000 (SuperSPARC 50 MHz, the SS-20/50's CPU, SunOS 5.5 beta, multiprocessor kernel, dynamic
binaries), tables 2, 6, 7, 9, 11 and 16
(https://www.usenix.org/legacy/publications/library/proceedings/sd96/full_papers/mcvoy.pdf).

So the emulated machines run CPU-bound code ~7x faster than an SS-20/50 and kernel paths 3x (pipe
latency) to ~25x (exec, file creation; the paper's binaries were dynamic, its UFS synchronous)
faster, memory is effectively unlimited, and the emulated SS-5's handicap is an emulation artefact of
deep call chains, not the real machines' relation (a 110 MHz microSPARC-II roughly matched a 50 MHz
SuperSPARC).

**Network.** lmbench 3.0-a9's network tests from the bench disk with them
(`bench-sol26-net.raw`, sha256 `a0f7eb6d...bd93a`; `e2e/sparc/README.md`, "Network"; the five programs
linked dynamically, the rest as above): over `lo0` inside the guest, and over the on-board lance
(`le0`) to lmbench's servers in the lab container, the same lmbench built for Linux. `le0` is given
10.0.2.15/24 at run time. Two paths between QEMU and the container: QEMU user networking (slirp,
`NET=user`, what the `benchdisk` matrix uses and what a VM with `-netdev user` gets), where the peer
at 10.0.2.2 is QEMU's own user-mode TCP/IP stack relaying to a container socket; and a tap interface
in the container (`NET=tap`, what a bridged VM gets, minus the bridge), where the container's kernel
answers. The `benchdisk` matrix 3 times (6/6, 6/6 and 5/6 passed: in the third run lat_sig's
protection-fault test printed nothing on 2.5.1, the old non-network test with the large spread
above; its network numbers are in the table; the other results of these runs are within the spread
of the table above), and `ONLY=nic NET=tap` 3 times on SS-5 and SS-20
(OpenBIOS) between the matrix runs, all passed. Same QEMU and host as above; the host's 1-minute load
during the matrix runs, the bench QEMU included: median 2.5, 2.6 and 2.2 (max 2.9, 3.5 and 4.1),
other agents' QEMU guests beside every run. Median and spread of the 3 runs; one-byte round trips
in us, bandwidth in MB/s with lmbench's 64 KB messages; "in" = container to guest, "out" = guest to
container.

| Benchmark | Unit | SS-5 OpenBIOS | SS-5 `ss5.bin` | SS-10 OpenBIOS | SS-20 OpenBIOS | SS-20 `ss20_v2.25_rom` | 2.5.1, SS-5 `ss5.bin` | SS-5 slower |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TCP round trip, `lo0` | us | 282 (5%) | 293 (12%) | 229 (49%) | 236 (3%) | 222 (2%) | 258 (1%) | 1.2x |
| UDP round trip, `lo0` | us | 277 (5%) | 291 (1%) | 234 (9%) | 240 (11%) | 246 (3%) | 439 (8%) | 1.2x |
| TCP connect, `lo0` | us | 1351 (9%) | 1281 (4%) | 1168 (56%) | 1307 (21%) | 1271 (27%) | 3198 (18%) | 1.0x |
| TCP bandwidth, `lo0` | MB/s | 201 (13%) | 205 (3%) | 294 (39%) | 286 (24%) | 271 (47%) | 161 (15%) | 1.4x |
| Sun RPC round trip, TCP / UDP, `lo0` | us | 938 / 601 | 953 / 654 | 371 / 338 | 380 / 338 | 387 / 342 | 925 / 544 | 2.5x / 1.8x |
| TCP round trip, `le0`, slirp | us | 260 (6%) | 265 (5%) | 209 (1%) | 196 (7%) | 217 (12%) | 416 (61%) | 1.3x |
| UDP round trip, `le0`, slirp | us | 247 (4%) | 276 (4%) | 213 (10%) | 202 (5%) | 220 (11%) | 368 (5%) | 1.2x |
| TCP bandwidth in / out, `le0`, slirp | MB/s | 15.1 / 14.8 | 15.1 / 15.2 | 15.7 / 15.1 | 15.1 / 15.8 | 15.0 / 15.1 | 15.4 / 15.0 | 1.0x / 1.1x |
| TCP round trip, `le0`, tap | us | 276 (14%) | | | 195 (6%) | | | 1.4x |
| UDP round trip, `le0`, tap | us | 264 (7%) | | | 195 (13%) | | | 1.4x |
| TCP bandwidth in / out, `le0`, tap | MB/s | 27.8 / 15.1 | | | 29.0 / 14.1 | | | 1.0x / 0.9x |

Bandwidth spreads: slirp in 6-31%, out 7-28%; tap in 11-17%, out 3-14%. RPC spreads 1-27%.

- **What a user of the VM feels over its NIC**: about 15 MB/s each way and a 0.2 ms round trip
  (SS-20; SS-5 0.26 ms) with user networking. A real lance is 10 Mbit/s Ethernet, ~1.1 MB/s of TCP
  payload at best; QEMU's lance doesn't model the wire, so the emulated one is ~13x faster than the
  real thing and bounded only by emulation.
- **What bounds it.** The guest-to-container direction stays at ~14-16 MB/s with tap as with slirp,
  on every profile: that limit is on the guest's side (Solaris's TCP send path and the lance
  emulation under TCG; QEMU used 92-100% of a host core during the runs). The container-to-guest
  direction doubles with tap (15 to 28-29 MB/s), so with slirp that direction is bounded by QEMU's
  user-mode stack. Round trips are the same with tap and slirp within the spread: the time is spent
  in the guest, not in slirp.
- **SS-5 vs SS-20**: the same kind of gap as in the system-call tests above. Round trips over `lo0`
  and `le0` 1.2-1.4x, `lo0` bandwidth 1.4x, and Sun RPC, which goes through more library layers (TLI,
  XDR), 1.8-2.5x; the NIC bandwidth is the same on both (its limits are elsewhere). Firmware and SS-10
  vs SS-20 are within the spread again.
- **Solaris 2.5.1** (SS-5, against 2.6 with `ss5.bin`): UDP round trips 1.3x (`le0`) to 1.5x (`lo0`)
  slower, TCP connect 2.5x slower, `lo0` bandwidth 0.8x; the `lo0` TCP round trip and the NIC
  bandwidth are the same. Its `le0` TCP round trip varied a lot (251-506 us).
- **Not included**: `lat_fifo` loops on Linux too (an lmbench bug: the writer it forks keeps
  benchmp's flag-only SIGTERM handler, so nothing ends it). `lat_ctx` and `bw_pipe`, left out of the
  first round for looping, ran normally when tried by hand on SS-20 for this round; not yet run on
  every profile.

## sparc64 (sun4u)

What runs on `qemu-system-sparc64` from the published `pve-qemu-kvm` 11.1.3-2+wsh7, measured in the
lab (`e2e/sparc`, `scenarios/_sparc64.py`, `sparc64` matrix): `-M sun4u`, OpenBIOS
(`openbios-sparc64`, the only firmware in the package for it), one CPU, TCG, 512 MB unless stated,
serial console unless stated.

**What boots.** "CD" = the install CD to the installer's first prompt; times are from QEMU start.

| Guest | CD, serial console | CD, VGA console | Install | Installed disk |
| --- | --- | --- | --- | --- |
| NetBSD 11.1 | yes, sysinst in 46 s | yes: sysinst on the screen in 54 s (no terminal question there); `b` Return on the PS/2 keyboard switches it to German | yes: sysinst "without X11", ~7.5 min | yes: `login:` in 48-58 s; `halt -p` ends QEMU (exit 0) |
| NetBSD 9.3 | yes | not tried | not tried | |
| OpenBSD 8.0 | yes (`bsd.rd`), installer prompt in ~1 min | not tried | yes: base, comp, man, game from the CD, ~17 min after the questions (kernel relink included) | no: the GENERIC kernel loads, then OpenBIOS stops (below) |
| Debian 12.0 ports netinst | yes: GRUB menu (no timeout, Return boots), then "Select a language" in 52 s | not tried | no: partitioning (Sun label) and DHCP work, then the base system fails: `dpkg-deb` segfaults in `libc.so.6` while unpacking (below) | |

OpenBSD's installed `/bsd` (GENERIC, 10.6 MB text) stops right after the loader:

```
[ using 1654104 bytes of bsd ELF symbol table ]
Unimplemented service set-symbol-lookup ([2] -- [0])
Unhandled Exception 0x0000000000000030
PC = 0x00000000013e04a8 NPC = 0x00000000013e04ac
Stopping execution
```

The same with 256 MB, 1 GB, `-cpu TI-UltraSparc-II` and `Sun-UltraSparc-IIIi`. `bsd.rd` (4 MB) from the
same disk (`-prom-env auto-boot?=false`, `boot disk:a bsd.rd`) boots to the installer, so the disk,
label and boot block are fine; it is the GENERIC kernel under OpenBIOS. Not followed further.

The Debian installer (kernel 6.1.0-9-sparc64, 1024 MB, disk on IDE, `sunhme`, user-mode network) gets
the network by DHCP, partitions the disk (Sun label, ext2 `/boot`, ext4 `/`, swap) and installs the
base system from the CD, which fails both times it was tried, on different packages:

```
dpkg-deb[11703]: segfault at fffff801036dea74 ip fffff801017a8c44 (rpc fffff80100b1df84) sp fffff8010361c041 error 1 in libc.so.6[fffff80101700000+18e000]
dpkg-deb: error: <decompress> subprocess was killed by signal (Segmentation fault)
dpkg: error processing archive /var/cache/apt/archives/perl-base_5.36.0-5_sparc64.deb (--install):
```

(the second time `libc6_2.36-4_sparc64.deb`, 15 min into the base system). Unpacking that same
`perl-base` package three times by hand in the installer's shell worked, so it is an intermittent
crash of user-space code under emulation (in glibc), not a missing instruction. About 25 min of a
run until the failure; not pursued further (a newer Debian ports snapshot wasn't tried).

**Hardware layout.** OpenBIOS "boots" = loads the guest from it with `-boot c`/`-boot d` (its `disk`
and `cdrom` aliases). Guest = the driver attaches and the device works (disk: read and write 10 MB
raw; NIC: DHCP from QEMU's user network and an HTTP fetch).

| Device | OpenBIOS | NetBSD 11.1 | OpenBSD 8.0 (`bsd.rd`) |
| --- | --- | --- | --- |
| IDE, built-in CMD646 (`ide-hd`/`ide-cd` on `ide.0`/`ide.1`) | boots disk and CD-ROM | `wd0`, `cd0` | `wd0`, `cd0` |
| LSI 53C895A (`lsi53c895a` + `scsi-hd`/`scsi-cd`) | `Cannot manage 'SCSI bus controller' PCI device type 'scsi'`; no boot | `esiop0` attaches, every probe ends in `command timeout`, `scsi bus reset`; no disk (`/dev/rsd0c: Device not configured`) | `siop0` attaches, `timeout on SCSI command`, `scsi bus reset` over and over; no installer prompt within 15 min |
| virtio-scsi-pci | `Cannot manage 'SCSI bus controller'`; no boot | `sd0` found, then `vioscsi_scsipi_request: error 12 loading DMA map`, `sd0: drive offline`; I/O hangs | `"Qumranet Virtio 1.x SCSI" ... not configured` |
| virtio-blk-pci | has a driver (`/pci@1fe,0/pci@1/scsi@0/disk`), but `disk`/`cdrom` don't point there: `Trying disk:a... No valid state has been set by load or init-program`. By path (`boot /pci@1fe,0/pci@1/scsi@0/disk:a`) it loads NetBSD's boot block and kernel, which then can't match its root: `FATAL: boot device not found, check your firmware settings!` | `ld0`, works | `"Qumranet Virtio 1.x Storage" ... not configured` |
| `sunhme` | | `hme0`, works | `hme0`, works (the installer's DHCP) |
| `virtio-net-pci` | | `vioif0`, works | `"Qumranet Virtio 1.x Network" ... not configured` |
| `e1000` | | `wm0`, works | `em0` attaches (traffic not tested) |
| `rtl8139` | | `re0`, works | `re0` attaches (traffic not tested) |
| `ne2k_pci` | | `ne0`, works | `ne0` attaches (traffic not tested) |
| `pcnet` | | no driver: `AMD PCnet-PCI Ethernet ... not configured` | `pcn0` attaches with address `ff:ff:ff:ff:ff:ff`: unusable |

- **Debian 12 installer** (Linux 6.1): IDE as `sda`/`sr0`; `virtio-net-pci` as the only NIC gets its
  DHCP lease; the LSI under `sym53c8xx` fails like on the BSDs (`ABORT operation timed-out`, `BUS RESET`,
  `Device offlined - not ready after error recovery`, for every target, ~20 min of probing); the
  installer has no `virtio_blk`/`virtio_scsi` module, so those weren't tested on Linux.
- The LSI fails in all three guests the same way (commands never complete), so it looks like the
  device model on this machine, not a guest driver; not followed further.
- `pciB` takes at most four devices: a fifth stops QEMU with `PCI: no slot/function available for
  e1000, all in use or reserved` (qemu-server puts the NIC and every controller there).
- **bootindex breaks booting.** With `bootindex` on the devices QEMU hands OpenBIOS a boot list it
  follows instead of its aliases, but the paths don't exist in OpenBIOS's tree: `Trying
  /pci@1fe,0/pci@1,1/ide@3/disk:f...`, `.../ide@3/cdrom...`, `/pci@1fe,0/pci@1/ethernet@0...`, then
  `No valid state has been set by load or init-program` (OpenBIOS's own path is
  `/pci@1fe,0/pci@1,1/ide@3/ide@1/cdrom@0`). Same IDE layout without `bootindex`: boots. With
  `strict=on` it also appends `HALT`.
- **Display.** `-vga std`: OpenBIOS draws its console with its built-in VGA driver (the package has no
  `QEMU,VGA.bin`, none is needed); NetBSD's installer comes up on the screen and the keyboard (i8042
  PS/2, keys sent with QMP `send-key`; VNC not tried) drives it. With a VGA attached OpenBIOS puts its console there; for a
  serial console with a VGA, `-prom-env input-device=ttya -prom-env output-device=ttya`. Without a
  VGA (`-vga none`) the console is ttya, the built-in 16550 on the ebus.
- **CPUs.** sun4u, sun4v and niagara take one CPU: `-smp 2` stops QEMU with `Invalid SMP CPUs 2. The
  max CPUs supported by machine 'sun4u' is 1`.
- **RAM** (NetBSD 11.1): 256, 2048 and 3072 MB boot (`hw.physmem64` = all of it); 4096 MB: `panic:
  Can't claim two pages of memory.` right after the loader, then `Unhandled Exception
  0x0000000000000030`; 8192 MB: OpenBIOS itself stops (`out of malloc memory (28)!`, `Unhandled
  Exception 0x0000000000000030`). QEMU accepts up to what the host can allocate. The Debian installer
  ran with 1024 MB. Three OpenBIOS bugs, fixed by patches 0013-0015; see "More than 3 GB" below.
- **`-cpu`**: default `TI-UltraSparc-IIi` (what OpenBIOS reports, `SUNW,UltraSPARC-IIi`). Nothing
  needs another model.

**Idle and speed** (`scenarios/sparc64-idle.py` against `idle.py` on the NetBSD 11.1 sparc32 disk
`netbsd111-installed.raw` on SS-20, alternating, 3 boots each, one CPU, OpenBIOS; QEMU's host CPU over
60 s at the shell; job = `awk 'BEGIN{for(i=0;i<1000000;i++)s=(s+i*i)%9973;print s}'`, host seconds;
the host had a load of 5-7 from other guests on its 14 cores):

| Guest | Machine | Host CPU idle | Guest clock over 60 s | job s |
| --- | --- | --- | --- | --- |
| NetBSD 11.1 sparc64 | sun4u, 512 MB | 101.1, 100.9, 101.3% | 60 s (drift 0.0-0.1 s) | 41.8, 33.2, 36.7 |
| NetBSD 11.1 sparc32 | SS-20, 256 MB | 3.2, 2.8, 2.8% | 60 s | 9.7, 9.3, 6.7 |

- NetBSD/sparc64 doesn't idle on sun4u: QEMU keeps a host core at 100% for as long as the VM runs.
  The kernel spins in its idle loop: nothing on QEMU's sun4u lets the guest stop the CPU (no APC
  like sun4m's; the `power` node isn't used, NetBSD: `power at ebus0 addr 7240-7243 ipl 1 not
  configured`). Stopping that would take QEMU idle-loop detection like `sunos-idle`/`solaris-idle` on
  sun4m (out of scope here). The sparc32 kernel idles through the sun4m APC.
- The same user-space job runs about 4x slower on sparc64 than on sparc32 SS-20 (median 36.7 s vs
  9.3 s), so sparc64 is not a faster way to run NetBSD. Not analysed further.
- Ten `sleep 1` take 10.3-10.4 s; the guest clock keeps time.
- Boot to `login:` 46-68 s; `halt -p` to QEMU's exit 8.7-9.1 s.

**Stability** (NetBSD 11.1): 4 boots in a row of the same disk, each a new QEMU process, login,
`halt -p` (`sparc64-boot-disk.py BOOTS=4`): all passed, `login:` after 56.0, 56.1, 56.0 and 71.4 s,
power-off to QEMU's exit 8.3-8.7 s. `LOAD=300` (`sparc64-idle.py`: the awk job and a
64 MB file written, read back and removed, in a loop for 5 minutes, 9 rounds): the guest answered
afterwards and powered off. Every power-off ended QEMU with exit code 0 (more than 15 runs, including
the boot tests with DHCP and HTTP fetches over `sunhme`, `virtio-net-pci`, `e1000`, `rtl8139` and
`ne2k_pci`). No hang with NetBSD on the recommended layout (only I/O to the offline virtio-scsi disk
hung, above). OpenBSD's installer `halt` stops at OpenBIOS's `0 >` instead
of powering off (`halt -p` on an installed system couldn't be tried).

**Solaris on sun4u** (OpenBIOS, CD-ROM on the IDE, `-boot d`, serial console). With QEMU's
`openbios-sparc64`, none reaches an installer. With the patched build from `openbios/`
(patches 0003-0007 and 0009, below), Solaris 10 1/13 boots to the installer and takes input on ttya.
The package built from the change that installs it (see "Packaging") has that firmware and the
cmd646 fix (QEMU `wsh/0021`). OpenBIOS finds the sun4u boot block on slice `f` of each CD and runs it.

**What the package gives for Solaris 10** (the package built from that change, nothing added by
hand; the lab's `solaris10` matrix, `sparc64-boot-cd.py GUEST=solaris10`, 1024 MB, blank disk on
`ide.0`, the 1/13 DVD on `ide.1`, serial console): the DVD boots to the installer in about 3
minutes; the IDE disk attaches (`/pci@1f,0/pci@1,1/ide@3/dad@0,0 (dad0)`, then `Corrupt label;
wrong magic number` for the blank disk) without `Interrupt not seen after set_features`; the
language (`0`) and terminal type (`3`, VT100) questions are answered on ttya, and the installer's
first screen comes up (`The Oracle Solaris Installation Program`, F2_Continue). That is as far as
the test goes, and about as far as a user gets: what follows needs changes that aren't in the
package (below, "Solaris 10 beyond the first prompt"):

- installing: the installer accepts the DVD as install media only with the OBP-style IDE tree,
  an unmerged OpenBIOS change that breaks NetBSD's CD boot;
- rebooting after an install (`prom_reboot: reboot call returned!`) and booting the installed disk
  (`Cannot load drivers for .../disk@0,0:a`, `vfs_mountroot: cannot mount root`).

Controls with the same case: the published 11.1.3-2+wsh10 (QEMU's `openbios-sparc64`) fails with
`panic - kernel: no nucleus hblk8 to allocate` before the installer; that package's QEMU with the
new firmware mounted over its image (no cmd646 latch) reaches the language prompt, and the case
fails on `Interrupt not seen after set_features` (4 times on the console). With the package, the
`sparc64` matrix passed 9/9 (NetBSD 11.1 and 9.3 CDs, OpenBSD 8.0 `bsd.rd`, the Debian 12
installer, NetBSD on VGA, the NetBSD install to the IDE disk, its disk with `sunhme` and with
virtio, idle), `smoke` 3/3 and `machines` 13/13 (sparc32, which uses no cmd646), and the `pve`
matrix cases `alpine-x86_64` (CD on `ide2`, i440fx's PIIX IDE), `alpine-aarch64` and
`netbsd-sparc64` 3/3 through PVE (the e2e node built from the package). The same Solaris 10 checks
pass through PVE too (`pve_matrix.py solaris10`: the sparc64 profile as the wizard makes it, 1024
MB, `vga: serial0`; 205 s). The whole install also runs through PVE: `lab.py install sol10-sun4u
--check` (`e2e/sparc/README.md`, "The Solaris 10 install target") on a VM made with the sparc64
profile as it is (blank disk on `ide0`, DVD on `ide2`, `-boot order=d` for the install and
`order=ide0` -> `-boot order=c` after it); nothing in the profile had to change.

With the patched `openbios-sparc64` (1024 MB; `fw/openbios-sparc64-p5` in the lab's scratch
directory, the same source as `openbios/Dockerfile` builds):

| CD | Where it stops |
| --- | --- |
| 10 1/13 (u11) DVD | `SunOS Release 5.10 Version Generic_147147-26 64-bit`, `Configuring devices.`, the installer's `Select a Language` prompt (~3 min). `hme0` attaches (`Attempting to configure interface hme0...`, `Skipped interface hme0` without a bootparams server). The IDE driver warns `WARNING: Interrupt not seen after set_features` once per device (fixed in QEMU, below). With 0003-0007 the installer took no input on ttya; 0009 fixes that (below). Also `could not find debugger-vocabulary-hook>threads` (optional Forth symbol lookup, harmless), `i8042: undefined symbol 'i_ddi_alloc_ispec'` (no PS/2 keyboard), `Out of range register specification from device node <fdthree>` |
| 9 DVD | `SunOS Release 5.9 Version Generic 64-bit`, then `panic[cpu0]/thread=140a000: boot_alloc: pp is NULL or free` in `boot_mapin` ← `boot_alloc(0x30000136000, 0x2000, 0x1000)` ← `segkmem_alloc` ← `kobj_vmem_init`, from `modloadonly` in `startup_modules` |
| 8 (1/01) Installation CD | `SunOS Release 5.8 Version Generic_108528-05 64-bit`, then `panic[cpu0]/thread=10408000: boot_alloc: pp is NULL or free` |
| 7 (3/99) | `SunOS Release 5.7 Version Generic_106541-02`, then `panic[cpu0]/thread=10404040: kmem_getpages: pp is NULL or free` |
| 2.6 (5/98), 2.5.1 (11/97) | unchanged: `open isn't unique.`, `byte-load: exception caught!` in the boot block |

How each patch moved them (each verified by booting with and without it):

- 0003 (`/virtual-memory` `available` covers the whole address space): Solaris 10 gets past `no
  nucleus hblk8 to allocate` to the installer prompt. Solaris 9 gets past `BOP_ALLOC failed` to `VAC
  too big!`.
- 0004 (I-cache size in the CPU node): Solaris 9 gets past `VAC too big!` to `boot_alloc: pp is
  NULL or free`. Solaris 8 lands on the same panic with both patches.
- 0005-0007 (no active package at the prompt, no `forth` constant, FCode `instance` consumed):
  Solaris 10's `' unix-tte is va>tte-data` succeeds, so the firmware translates kernel addresses
  with the kernel's own handler, as on OBP. Before that it was `unix-tte:interpret: exception -13
  caught` (the installer came up anyway). 0005 without 0007 crashes Solaris 10 in OpenBIOS
  (`Unhandled Exception 0x00000000ffeb6520` in `@`, also with 0006), so they belong together.
- Solaris 7's change from `bottom of stack not aligned` to `kmem_getpages: pp is NULL or free`
  came with the full set; which patch moved it wasn't bisected.

**Regression** with the patched firmware bind-mounted over the package's
`/usr/share/kvm/openbios-sparc64` in the lab image: the `sparc64` matrix passes 9/9, as with
0003+0004 alone. That covers NetBSD 11.1 CD on serial and VGA, the sysinst install, the
installed disk with DHCP/HTTP over `sunhme` and `virtio-net-pci`, and idle; also NetBSD 9.3 CD,
OpenBSD 8.0 `bsd.rd` and the Debian 12 installer. Unchanged, with the stock and the patched
firmware alike: OpenBSD's installed GENERIC kernel (`Unimplemented service set-symbol-lookup`,
`Unhandled Exception 0x0000000000000030`) and NetBSD with 4096 MB (`panic: Can't claim two pages
of memory.`).

**Solaris 10: console input (solved by patch 0009).** With 0003-0007 the installer printed `Select a
Language` and then ignored every key. A debug print in QEMU's 16550 receive path showed the cause:
the characters arrived in the UART (LSR `0x60` → `0x61`, data ready), and nothing ever read them.
The `su` driver had attached (FCR `0x0f`, MCR `0x0b`, 9600 baud, IER `0`), but Solaris never opened
it as the console. Solaris builds OBP's names for its device nodes (`pci@1f,0` for the sabre, from
the UPA port id; `su@14,3f8` for the ebus 16550, from space,offset) and looks the firmware's stdin
path up among them. OpenBIOS named them `pci@1fe,0` and `su@0`, so nothing matched. Patch 0009
names them like OBP: the stdin instance path is now `/pci@1f,0/pci@1,1/ebus@1/su@14,3f8`. Solaris
10 echoes the `0` and goes on to `What type of terminal are you using?`, and from there through the
installer's curses screens on ttya. Verified with QEMU 11.1.3 as packaged and with the standalone
build.
Rechecked with firmware built from the committed patches minus one (each build records its source
commit): without 0009, Solaris 10 reaches `Select a Language` and ignores input again; without 0003,
it panics with `no nucleus hblk8 to allocate` at 1024 MB but reaches the installer (and takes input)
at 2048 MB. So 0003 is needed at 1 GB and not at 2 GB.
0009 defines the ebus `decode-unit`/`encode-unit` pair in Forth over the bridge methods the ebus
node already has, so OpenBIOS prints `decode-unit isn't unique.` and `encode-unit isn't unique.` at
power-on (cosmetic). A variant with a method table of its own for the ebus node (as paulsheer does)
avoids the messages but hasn't been tested on its own.

**Solaris 10 beyond the first prompt** (lab scratch scenario driving the installer by screen title;
firmware 0003-0007 and 0009 (the method-table variant) plus the IDE-tree change (an early form of 0011, without `compatible`), standalone QEMU 11.1.3 with the
cmd646 patch below, 1024 MB, 16 GB disk on `ide.0`, DVD on `ide.1`, `sunhme` on user networking):

- **IDE interrupt.** QEMU clears the cmd646 interrupt status bits (MRDMODE/CFR/ARTTIM23) when the
  drive drops INTRQ, which happens when the guest reads the drive's status register. Solaris reads
  the status and then polls those bits, and warned `WARNING: Interrupt not seen after set_features`
  once per device. The standalone QEMU patch `ide/cmd646: latch the interrupt status bits until the
  guest clears them` keeps them latched until the guest writes 1 to clear them, while the PCI
  interrupt line keeps following INTRQ. With it the warning is gone and the disk attaches as `dad0`.
  A first version also drove the interrupt line from the latched bits, as paulsheer/qemu does. That
  left the line asserted for guests that don't clear the bits: Linux disabled the interrupt (`irq 7:
  nobody cared`) and OpenBSD hung at boot (matrix 7/9). Notes: `upstream/qemu-cmd646-interrupt-latch.md`.
  In the package as `wsh/0021`, with the qtest `sun4u-cmd646-test` (`wsh/0022`).
- **The DVD as install media and the disk.** With OpenBIOS's IDE tree (a node per channel,
  `ide@3/ide@1/cdrom@0`), the installer refused the DVD: `ERROR: The disc you inserted is not a
  Solaris OS CD/DVD.` OBP on an Ultra 5/10 puts the drives directly under the controller as
  `disk@0,0` and `cdrom@2,0` (target = 2 × channel + unit), which is how Solaris names its `dad`/`sd`
  nodes. With that tree (patch 0011; NetBSD needs 0010 with it, below), the boot
  path maps to `/devices/pci@1f,0/pci@1,1/ide@3/sd@2,0:f`. The installer accepts the DVD and lists
  the disk as `c0t0d0` (16382 MB).
- **Install.** The interactive text installer on ttya runs through system identification (network
  with DHCP on `hme0`, time zone, root password), software selection (the default group, 4053 MB),
  disk selection and automatic layout, and installs: `Solaris 10 software installation succeeded`,
  boot blocks on `c0t0d0s0`, `Creating boot_archive for /a`, `syncing file systems... done`, in
  about 60 minutes of copying. That is 1 of 3 attempts. One attempt was stopped early by the
  scenario (1.1 GB in). One panicked about 17 minutes into the copy: `panic[cpu0]/thread=...: bad
  unknown trap at TL 1`, with `%tt` `045` (interrupt level 5) and `uata:ghd_intr` on the stack.
  This is an intermittent kernel panic around the IDE interrupt path. paulsheer reports similar
  crashes ("not stable", within an hour). Not found.
- **Reboot.** After the install, `rebooting...` ends in `panic - kernel: prom_reboot: reboot call
  returned!`: OpenBIOS's client-interface `boot` service only prints `BOOT` and returns. A fix (reset
  the machine) is written but not tested yet.
- **The installed disk.** OpenBIOS loads the boot block and the boot archive from `disk@0,0:a`, and
  the kernel starts (`SunOS Release 5.10`). Then `Cannot load drivers for
  /pci@1f,0/pci@1,1/ide@3/disk@0,0:a`, `Cannot assemble drivers for root`, `vfs_mountroot: cannot
  mount root`. Solaris finds no driver for a node named `disk`: Solaris maps OBP's IDE nodes to its
  `dad` driver through their `compatible` property (`ide-disk`, which paulsheer's and
  proxmox-solaris's trees set). This is the next step; not tried yet.
- **`hme0`.** It attaches and is configured from the installer's answers. Traffic isn't verified
  yet; that needs the installed system. QEMU writes the default MAC `52:54:00:12:34:56` into the
  sun4u IDPROM unless the NIC is the machine's onboard `-nic`. qemu-server and the lab add `sunhme`
  with `-device`, so every guest gets that system MAC whatever `mac=` says. proxmox-solaris reports
  the same thing on the wire. Measured since (below).

**Status on the published pve-qemu-kvm 11.1.3-2+wsh13 (2026-11-17).** QEMU and `openbios-sparc64`
from the package as installed in the lab image (no own builds), Solaris 10 1/13 DVD, 1024 MB, a
16 GB disk on `ide.0`, the DVD on `ide.1`, `sunhme` on user networking, serial console:

- **Install:** 2 of 2 completed (`scenarios/solaris10-install-sparc64.py`), each about 80 minutes:
  ~14 min to the end of the questions, ~61 min of package copying, then `Solaris 10 software
  installation succeeded`, the boot archive and `syncing file systems... done`. No panic in these two.
  Before the package (standalone QEMU patch, pre-release firmware) 1 of 3 attempts completed: one
  was stopped early, one panicked with `bad unknown trap at TL 1` (above). Counting only attempts
  that ran to an end: 3 of 4 completed, the panic not seen on the package (0 of 2).
- **The installer's reboot:** ends with `panic - kernel: prom_reboot: reboot call returned!` (2 of 2).
  The client-interface `boot` service only prints `BOOT` and returns.
- **Installed disk:** first boot to `console login:` after 836 s (keyboard-layout question answered
  with F2). After that, 376 s to `console login:` in the `solaris10` matrix. `format` lists `c0t0d0`,
  `hme0` has 10.0.2.15 from DHCP, `ping 10.0.2.2` is `alive`, and `init 5` ends QEMU with exit code 0.
  The `solaris10` matrix (installer start and installed disk) passes 2/2.
- **0012 (reboot, still `.wip`):** firmware built from 0001-0011 + 0012 (`.src.txt` records the
  tree). On the installed disk, `reboot` prints `syncing file systems... done` and `rebooting...`,
  then nothing for 900 s: the VM hangs (1 of 1). `reset-all` at the `ok` prompt does reset the
  machine (the banner comes back, 1 of 1). Resetting from inside the client interface call is what
  fails; not traced further. So 0012 stays `.wip`.
- **System MAC:** with `-device sunhme,mac=52:54:00:aa:bb:cc`, Solaris's `hme0` shows `ether
  52:54:0:12:34:56`. QEMU's sun4u writes the MAC of the onboard NIC into the IDPROM. The onboard NIC
  is the first `-nic`/`-net nic` of the default model, created at PCI 01.1 on bus A. A NIC added with
  `-device` (as qemu-server and the lab do) isn't seen at that point, so the IDPROM gets QEMU's
  default `52:54:00:12:34:56`. With `-net nic,model=sunhme,macaddr=...` the NIC sits at a different
  PCI path, and the installed system (whose `hme0` is the `-device` NIC on bus B) didn't configure
  it. The IDPROM MAC there wasn't read, so that variant is untested.

**Status with 0010-0011 (2026-11-17).** Firmware built from the committed patches 0001-0011 (build
records its source commit), Solaris 10 1/13 DVD, 1024 MB, 16 GB disk on `ide.0`, DVD on `ide.1`:

- NetBSD 11.1 CD: roots on `cd0` (it took `wd0` with the flat tree before 0010). `sparc64` matrix
  9/9 on the packaged QEMU 11.1.3-2+wsh7.
- Installer: accepts the DVD and lists `c0t0d0`. The complete install (`Solaris 10 software
  installation succeeded`, boot archive created) was measured with 0011's predecessor (same tree,
  no `compatible`) and the standalone QEMU with the cmd646 patch, not repeated with 0011.
- Installed disk (that install's disk, firmware 0001-0011, QEMU with the cmd646 patch): boots to
  the first-boot keyboard question and to `console login:` in 412 s. Root logs in on ttya. `format`
  lists `c0t0d0` at `/pci@1f,0/pci@1,1/ide@3/dad@0,0`. `hme0` gets 10.0.2.15 by DHCP and
  `ping 10.0.2.2` answers `alive`. `init 5` powers QEMU off (exit 0).
- The sun4u system MAC: with `-device sunhme,mac=52:54:00:aa:bb:cc`, Solaris uses `ether
  52:54:0:12:34:56`. QEMU writes its default MAC into the IDPROM when the NIC isn't `-nic`, so two
  guests on one network would clash. Not fixed.
- Not measured with this set: the install on the packaged QEMU (without the cmd646 patch); the
  reboot (0012, `.wip`); Solaris 7/8/9.

**NetBSD with the OBP-style IDE tree.** Without 0010, NetBSD's CD boot stopped at `root device
(default wd0a):`: it booted `cdrom@2,0:f` but took `wd0` for root (the `sparc64` matrix was 5/9).
NetBSD's ofwboot reads the boot device's target with `my-unit` on the instance `open-dev` returns,
which is the interposed disk-label package, and OpenBIOS answered 0 0 there; with the channel
nodes NetBSD made up for that with an OpenBIOS-specific offset. 0010 makes the interposed package
answer with the device's unit (`0 2` for `cdrom@2,0`), and NetBSD roots on `cd0` again.

**More than 3 GB (patches 0013-0015, 2026-11-18).** QEMU's sun4u takes any `-m`; OpenBIOS was the
limit, with three bugs (`upstream/openbios-sparc64-ram-above-4g.md`):

- 0013: `align_ptr()` in `ofmem_common.c` masked with a 32-bit `size_t`. The firmware's heap sits
  at the top of RAM; once that is above 4 GB the first `malloc()` got a truncated address. With the
  package's firmware (11.1.3-2+wsh15): 4352 to 7168 MB stop before the banner with `Unhandled
  Exception 0x0000000000000030` (PC in `ofmem_posix_memalign`), 8192 MB with `out of malloc memory
  (28)!` first. 6144 MB stops like 4352.
- 0014: a client `claim` with an alignment took the top of RAM and mapped it 1:1 without checking
  the virtual range. With 4096 MB that is the firmware's own range (`0xff000000`-4 GB): NetBSD's
  first claim (`pmap_alloc_bootargs()`) failed and the kernel stopped right after the loader
  (`Unhandled Exception 0x0000000000000030` at `0x13f5394` with the package's firmware and with 0013
  alone).
- 0015: `claim`, `SUNW,retain` and `translate` cut `phys.lo` to 32 bits, but NetBSD (`CELL2HDQ`) and
  64-bit Solaris (`p1275_cells2ull`) read `phys.lo` alone. With 0013+0014 NetBSD booted with 6144 and
  8192 MB, but `ofwboot` mapped its allocations at the truncated addresses (a firmware trace: claim
  `0x17fe7e000`, map `0x7fe7e000`), and while a tmpfs was being filled (about 55 s into it, the same with both sizes) the kernel stopped with `trap
  type 0x10: cpu 0, pc=1000d00` and `panic: illegal instruction` (its trap table overwritten).

Measured with `openbios-sparc64` built from the committed patches 0001-0011 and 0013-0015 (commit
`6e4e296`, the `openbios/Dockerfile` steps in the lab's builder image) on the published QEMU
11.1.3-2+wsh15, the installed disks booted with `-snapshot`, one CPU, serial console. The load: swap
off, copies of a 32 MB random file written into a tmpfs (NetBSD `mount_tmpfs`, Solaris `/tmp`) until
most of RAM is used, then the MD5 of every copy:

| Guest | RAM | Reports | Load | Result |
| --- | --- | --- | --- | --- |
| NetBSD 11.1 | 3072 MB | `hw.physmem64` 3221225472, `avail memory = 2995 MB` | 64 copies (2 GB) | all identical, power off |
| NetBSD 11.1 | 4096 MB | `hw.physmem64` 4294967296, `avail memory = 4001 MB` | 96 copies (3 GB) | all identical, power off |
| NetBSD 11.1 | 6144 MB | `hw.physmem64` 6442450944, `avail memory = 6014 MB` | 160 copies (5 GB) | all identical, power off |
| NetBSD 11.1 | 8192 MB | `hw.physmem64` 8589934592, `avail memory = 8026 MB` | 224 copies (7 GB) | all identical, power off |
| Solaris 10 1/13 | 2048 MB | `Memory size: 2048 Megabytes`, `::memstat` total 1999 MB | 32 copies (1 GB) | all identical, `init 5` |
| Solaris 10 1/13 | 3072 MB | `Memory size: 3072 Megabytes`, total 3002 MB | 64 copies (2 GB) | all identical, `init 5` |
| Solaris 10 1/13 | 4096 MB | `Memory size: 4096 Megabytes`, total 4010 MB | 96 copies (3 GB), freelist 440 MB left | all identical, `init 5` |
| Solaris 10 1/13 | 8192 MB | `Memory size: 8192 Megabytes`, total 8033 MB | 192 copies (6 GB), freelist 1484 MB left | all identical, `init 5` |

Solaris needs about 30 minutes (4096 MB) to 38 minutes (8192 MB) for the run, most of it the boot
and `digest`. `prtdiag` was run but its output not checked. NetBSD with 6144 MB and the firmware
before 0015 is the crash above; with 0013+0014 the 3072 and 4096 MB NetBSD runs and the 2048 and
3072 MB Solaris runs passed as well. Regression with this firmware in the lab image: the `sparc64`
matrix 9/9 and the `solaris10` matrix 2/2 (DVD to the installer, installed disk at 1024 MB with
`format`, DHCP and ping).

Not measured: more than 8 GB, other RAM sizes between 4 and 8 GB than 6144 MB, Solaris with 6144 MB,
OpenBSD and Debian with more than 3 GB, more than 3 GB through PVE (the profile's cap is 8192 MB,
the largest size measured, since pve-qemu-kvm 11.1.3-2+wsh16 carries 0013-0015).

**maxinjohn/proxmox-solaris** (2026-11-14, one script, no licence; read for facts only). It installs
Solaris 10 by JumpStart (RARP/NFS from the host, `boot ... - install` from a `boot-command`). Its
README notes that keystrokes don't reach Solaris on the serial console; patch 0009 here is the
cause and fix. Its OpenBIOS patch:

- maps the sabre's unit address between `1f` and `1fe` (as 0009 does);
- flattens the IDE tree as `dad@unit,0`, with the target equal to the unit, so the CD-ROM must be
  on the primary channel;
- has no `available`/`ofmem` change. That works at its default of 2048 MB; at 1024 MB Solaris 10
  panics with `no nucleus hblk8 to allocate` without 0003 (rechecked).

Its QEMU change is a binary patch of the packaged `qemu-system-sparc64`: it keeps the cmd646 status
bits latched, and it removes multiword DMA and UDMA from the disk's IDENTIFY data, because "DMA
completion never arrives" after Solaris switches to MDMA2. It also patches Solaris's `uata` to stay
on PIO. Here the install copied 4 GB to the disk with the latch patch alone and without an `ATA
transport failed`, so DMA didn't fail in these runs. Whether Solaris used DMA or PIO wasn't measured.

**Solaris 7/8/9: `pp is NULL or free`.** After the kernel has built its page structures from the
boot program's snapshot of `/memory` `available`, further boot allocations must come from pages
in that snapshot. The page behind Solaris 9's failing allocation is physical `0x3d092000`, near
the top of 1 GB (`translate` at `0 >` after the panic). OpenBIOS hands out physical memory top
down. The kernel doesn't know this page: either it was outside the snapshot, or it was freed and
reused after the snapshot. Not found which. The Solaris 2.6 source (reference) shows the
mechanism: `boot_getpages` and `page_numtopp`, with page structures built from the boot
program's `physavail`. Likely places to look: OpenBIOS's byte-granular `ofmem` lists (fragments
like `0x0011ae64` length 4 in `available`), and whether anything releases physical memory during
boot.

**paulsheer/openbios + paulsheer/qemu** (2026-10-30, one commit each on top of the same
OpenBIOS `e5ac46d`). They report Solaris 10 reaching the installer and mounting root, "not
stable", crashing within an hour. The OpenBIOS commit changes the device tree: IDE disks as
`dad@0,0`/`sd@`, sabre children named by `upa-portid`, PCI bridge `ranges`, e1000/LSI entries,
no `fdthree`, and client-interface return guards. The QEMU commit fixes the cmd646 interrupt
latch and makes the LSI answer as a 53C895. Nothing in it touches `ofmem`, `unix-tte` or the
console. We read the diff but didn't build or run it. With this QEMU, our patches alone get to
the same installer prompt, so the two are complementary. Its IDE `dad`/`sd` naming and the
cmd646 fix are the obvious next candidates for the disk once input works.

Older prior work: Mark Cave-Ayland's 2010-2016 OpenBIOS commits for Milax/OpenSolaris and Solaris 9
(kmdb support `d7c28ea`, `va>tte-data` `44af623`, the `available` limit `45b60c8`/`6e3d3fd`, which
this work partly reverts). The 2020 qemu-devel thread "Emulating Solaris 10 on SPARC64 sun4u"
(Jasper Lowell) got to `Configuring devices` and the cmd646 `Interrupt not seen` warning.
Artyom Tarasenko's Solaris 10 work was on `niagara` with Sun's firmware. QEMU issues #216 and #293
report `no nucleus hblk8` and `BOP_ALLOC failed` with no diagnosis.

With QEMU's `openbios-sparc64` (512 MB; `scenarios/sparc64-boot-cd.py GUEST=solaris`):

| CD | Where it stops |
| --- | --- |
| 2.5.1 (11/97) | in the boot block: `Evaluating FCode...`, `open isn't unique.`, `?go:`, `byte-load: exception caught!`, back at `0 >` |
| 2.6 (5/98) | the same |
| 7 (3/99) | `open isn't unique.`, the kernel loads (spinner), then `panic[cpu0]/thread=10404040: bottom of stack not aligned`, `rebooting...`, `BOOTpanic - kernel: prom_reboot: reboot call returned!`, `EXIT`, `0 >` |
| 8 (1/01) Installation CD | the kernel starts: `panic[cpu0]/thread=10408000: BOP_ALLOC failed`, in `segkmem_alloc` ← `kmem_init` ← `mod_read_system_file` ← `kobj_open_file` ← `startup_memlist`; `skipping system dump - no dump device configured`, `rebooting...`, then as 7 |
| 8 (1/01) Software CD 1 | OpenBIOS: `Can't read ELF header`, `Can't read a.out header`, `Can't read FCode header from ihandle ...`, `No valid state has been set by load or init-program` |
| 9 DVD | `panic[cpu0]/thread=140a000: BOP_ALLOC failed`, the same call chain as 8 |
| 10 1/13 (u11) DVD | `Ignoring failed claim for va 1000000 memsz af6d6!` (and for `1402000`, `1800000`), then `SunOS Release 5.10 Version Generic_147147-26 64-bit`; the kernel's Forth debugger setup fails in OpenBIOS (`could not find debugger-vocabulary-hook>threads:interpret: exception -13 caught`, then the text of `data64.fth`/`kdbg.fth` echoed), and it stops with `panic - kernel: no nucleus hblk8 to allocate`, `EXIT`, `0 >`. The same with 512, 1024 and 2048 MB |
| 2.6 with the CD on the LSI | OpenBIOS: `Trying cdrom:f...`, `Trying cdrom...`, `No valid state has been set by load or init-program` |

2.5.1/2.6's boot block (FCode) throws inside OpenBIOS before it loads anything; 7 loads its kernel and
panics at once; 8 and 9 get into the kernel and fail its first boot-time memory allocation
(`BOP_ALLOC`, which the boot program serves through the firmware). All of it happens in the
firmware/boot-program interplay before any device driver runs, so no disk or NIC choice changes it.
Solaris 9 fails identically with 256, 512, 1024 and 2048 MB: `boot_alloc(0x30000018000, 0x2000,
0x1000)` (8 KB of kernel heap at that virtual address, 4 KB aligned), called from `segkmem_alloc` while
`kmem_init` reads `/etc/system`; the heap allocations before it (`0x30000000000`-`0x30000016000`)
succeeded. Solaris 8 fails the same way at `0x30000016000`.

What OpenBIOS reports at `0 >` after the panics (`" /virtual-memory" find-device .properties`, the same
for `/memory`; 1024 MB):

- Solaris 9: 66 translations, the kernel heap as single 8 KB pages, the last one being
  `0x30000018000` itself (mapped to physical `0x3fd20000`). So the firmware did map the page the
  boot program then reported as failed; the claim's result is what the boot program rejected (not
  traced further). Both free lists (`available` of `/memory` and `/virtual-memory`) contain fragments
  that aren't page aligned: `0x0011ae64` of length 4, a range starting at `0x0013a490`. OpenBIOS's
  `ofmem` keeps byte-granular free lists and claims of odd sizes (the boot program and kernel
  segments use them, e.g. `memsz af6d6`) leave such holes.
- Solaris 10: 180 translations, 102 of them single 8 KB pages of the kernel heap at
  `0x300_0000_2000`-`0x300_0016_8000`, the physical pages handed out top down (`0x31814000`,
  `0x31812000`, `0x31810000`, ...), so neighbouring virtual pages never form one larger translation.
  Solaris takes the firmware's translations over into its own page tables at boot from a fixed pool of
  "nucleus" hme blocks; `no nucleus hblk8 to allocate` is that pool running dry, consistent with the
  long list of 8 KB translations (a real OBP hands over far fewer, larger ones).

The diagnosis made from these numbers was only half right. `no nucleus hblk8` was not caused by
the many small translations. Solaris sizes the hme-block pool from the gaps in `/virtual-memory`'s
`available`, and OpenBIOS left the 64-bit heap out of that list (patch 0003). Solaris 8/9's
`BOP_ALLOC failed` went away with the same patch. Physical allocation order, translation merging
and byte-granular claims weren't changed, and no failure seen so far needed them.

**Packaging.** `openbios/Dockerfile` builds `openbios-sparc64` next to `openbios-sparc32`, and
`debian/rules` (`submodules/pve-qemu.patch`) copies `build/openbios/openbios-sparc64` over
`$(destdir)/usr/share/kvm/openbios-sparc64` when it exists, as for sparc32. It is an optional extra
of its own (`openbios-sparc64`): when the Dockerfile's sparc64 step fails, the package keeps QEMU's
image, the build prints `WARNING: optional extra openbios-sparc64 missing: ...` and `build-deb.yml`
opens an issue. `scripts/check-qemu-extras.sh` tells the two images apart ("OpenBIOS" above).
The package build was checked on the lab host the way CI builds it (`make pve-qemu-bundle` in
`pve-build:13`, `-j8`): the series applies with fuzz 0, the 3dfx and the main build took 13
minutes together, and `check-qemu-extras.sh` against the build tree and on the bare `.deb` lists
3dfx, openbios, openbios-sparc64 and sun-proms present.

**sun4v and niagara.** `-M sun4v` with `openbios-sparc64` (the only firmware in the package) stops QEMU
at once: `qemu: fatal: Trap 0x0010 while trap level (6) >= MAXTL (6), Error state`, `pc:
0000000000000200` (the sun4u OpenBIOS can't run on a sun4v CPU, which starts in hyperprivileged mode),
with or without a NetBSD, OpenBSD or Debian CD; no sun4v guest kernel is reached, whatever the CD
carries. `-M niagara`: `rom: file nvram1 : error Failed to open file "nvram1"`, `Unable to load a
firmware for -M niagara`. Niagara needs Sun's OpenSPARC T1 firmware set (`nvram1`, the hypervisor,
OpenBoot and reset images) and, for QEMU's documented Solaris 10 path, the `disk.s10hw2` image from
the same package; neither is in the package. With that firmware supplied by hand, see "sparc64:
niagara (sun4v)" below.

**Sun OBP on sun4u: status.** Tried with the Ultra 5/10 flash update patch 106121-18 (OBP 3.31.0,
POST 3.1.0; proprietary, not in the repository or the package). Its `flash-update-Ultra510-*` files
are SPARC standalone ELF updaters; `.data` holds four 512 KB images, each behind a 0x20-byte header:
two identical OBP images and two identical POST images (each starts with an `OBMD` header naming
`OBP`/`POST`, reset code at offset 0x20). QEMU maps `-bios` at `0x1fff0000000` (4 MB window) and
starts the CPU at offset 0x20. No console output with any arrangement:

- OBP alone (and OBP + POST): the reset code programs the APB/Simba bus numbers and the ebus BAR
  (`0xf1000000`) in PCI config space, reads a soft-reset marker at ebus offset 0x10, then probes the
  SuperIO (PC97317) configuration port at ebus `0x30002e` (`0x1fff130002e`). Nothing answers there
  (QEMU's ebus puts its ISA devices elsewhere and has no SuperIO configuration registers), and it
  falls into a dead loop at PROM offset 0x258, about 100 instructions after reset. Same with `-cpu
  TI-UltraSparc-II`/`-IIe`, 256/512 MB, `-nographic` or VGA.
- POST alone (and POST + OBP): `qemu: fatal: Trap 0x0010 while trap level (5) >= MAXTL (5), Error
  state` at offset 0x2c, `wr %g0, 0, %asr18` (the UltraSPARC dispatch control register, which QEMU's
  sparc64 CPU doesn't implement; illegal instruction in RED state).

Closing the gap would take a model of the real Ultra 5 I/O map in QEMU (SuperIO with its
configuration registers at the real ebus offsets, the NVRAM/IDPROM, flash and RIO devices where OBP
expects them, `%dcr`), not a small fix; each step would show the next missing piece. So there is no
Sun PROM route to Solaris on sun4u here (unlike `ss5.bin` for Solaris 2.4 on sparc32). The images
were extracted only in the lab's scratch directory and deleted afterwards.

**What qemu-server built before the profile** (`qm showcmd`, qemu-server 9.2.15+wsh4) for a VM
from the create wizard (`arch: sparc64`, `scsi0` disk, `scsi2` CD-ROM, `net0: sunhme`, no `scsihw`,
`vga` and `bios` unset):

```
-smp '1,sockets=1,cores=1,maxcpus=1' -nodefaults
-boot 'menu=on,strict=on,reboot-timeout=1000,splash=/usr/share/qemu-server/bootsplash.jpg'
-vga std -m 512
-device 'virtio-balloon-pci,id=balloon0,free-page-reporting=on'
-device 'lsi,id=scsihw0,bus=pciB'
-device 'scsi-hd,bus=scsihw0.0,scsi-id=0,drive=drive-scsi0,id=scsi0,...,bootindex=100,...'
-device 'scsi-cd,bus=scsihw0.0,scsi-id=2,drive=drive-scsi2,id=scsi2,...,bootindex=101,physical_block_size=512'
-device 'sunhme,mac=...,netdev=net0,id=net0,bootindex=102,bus=pciB'
-machine 'accel=tcg,type=sun4u+pve0'
```

QEMU started it, but it booted nothing: OpenBIOS has no LSI driver and followed the `bootindex` list
(`LAYOUT=pve` in the lab, NetBSD 11.1 CD: `No valid state has been set by load or init-program` at
once).

**What qemu-server builds now** (the sparc64 profile, `src/test/cfg2cmd/sparc64-wizard-default.conf`):
the wizard's VM (`ide0` disk, `ide2` CD-ROM with the ISO, `net0: sunhme`, 512 MB) gets `boot:
order=ide2;ide0;net0` from the API and

```
-smp '1,sockets=1,cores=1,maxcpus=1' -nodefaults
-boot 'order=d,menu=on,strict=on,reboot-timeout=1000,splash=/usr/share/qemu-server/bootsplash.jpg'
-vga std -m 512
-device 'ide-hd,bus=ide.0,unit=0,drive=drive-ide0,id=ide0,write-cache=on'
-device 'ide-cd,bus=ide.1,unit=0,drive=drive-ide2,id=ide2,physical_block_size=512'
-device 'sunhme,mac=...,netdev=net0,id=net0,bus=pciB'
-machine 'accel=tcg,type=sun4u+pve0'
```

Through PVE (the lab's `pve` matrix, case `netbsd-sparc64`: that VM with a blank 1 GB disk, the
NetBSD 11.1 CD and `vga: serial0`), OpenBIOS prints `Trying cdrom:f...`, boots the CD by itself and
NetBSD reaches sysinst and its shell in 57 s; nothing is typed at the OpenBIOS prompt.

Done for sparc64 (was → now), in `submodules/qemu-server.patch` and mirrored in
`submodules/pve-manager.patch`:

| | Was | Now |
| --- | --- | --- |
| Disk bus | `lsi` on `pciB` + `scsi-hd` (wizard: SCSI only) | the built-in IDE, `ide0`-`ide3` (`ide0` → `ide-hd,bus=ide.0,unit=0`, `ide1`: `ide.0` unit 1); the wizard's first disk is `ide0`, the Hardware editors offer only IDE |
| CD-ROM | `scsi-cd` on the LSI, `scsi2` | `ide2` → `ide-cd,bus=ide.1,unit=0` (OpenBIOS's `cdrom` alias), `physical_block_size=512` |
| SCSI, virtio-blk, SATA | offered | refused (`sparc64: scsi0 can't be used, disks and CD-ROMs go on the built-in IDE (ide0 to ide3)`); virtio-blk works as a NetBSD data disk but OpenBIOS can't boot it, so it is left out rather than special-cased |
| Boot order | `bootindex=` on every device, `-boot menu=on,strict=on,...` | no `bootindex` on sparc64; `-boot 'order=d,menu=on,strict=on,...'` (or `order=c`) from the first drive of `boot: order=` that holds something: a CD-ROM with a medium `d`, a disk `c`; empty CD-ROMs, cloud-init drives and NICs are skipped; none: no `order=` (QEMU's default, the disk). A new sparc64 VM gets its CD-ROM first in the default boot order (OpenBIOS boots one device and doesn't fall back to the next), so it boots the install CD, and the disk once the CD is ejected. Network boot isn't offered (not tested) |
| Display none | `vga: none` → `-vga none -nographic` | as was |
| Serial console (`vga: serial0`) | `-nographic`, `-chardev ...serial0`, `-serial chardev:serial0` (since qemu-server 9.2.15+wsh3; before, an `isa-serial` that OpenBIOS never used) | as was: the ebus's first 16550 (OpenBIOS's ttya, NetBSD `com0`); OpenBIOS and the NetBSD CD to sysinst on it, tested through PVE |
| Displays | any | `std` (default), `serial0`, `none`; others refused |
| NIC | `sunhme` on `pciB`, any model | `sunhme` (default), `virtio`, `e1000`, `rtl8139`, `ne2k_pci`; `pcnet` refused (no NetBSD driver) |
| PCI slots | NIC and every SCSI/virtio controller on `pciB`; a fifth device stopped QEMU (`no slot/function available`) | only NICs go there (the controllers are refused): at most four, refused with `sparc64: at most 4 network devices fit on PCI bus B, not 5 (...)` |
| CPUs | `-smp 1,...` from sockets × cores; QEMU refused more | sockets × cores > 1 refused; the `cpu` option refused (it was never passed) |
| RAM | anything | at most 8192 MB, the largest size measured (without OpenBIOS patches 0013-0015 4096 MB panics NetBSD and 8192 MB stops OpenBIOS, see "More than 3 GB"); the wizard presets 512 MB |
| Machine | `sun4[a-z]` | `sun4u` only (`sun4v` refused; `niagara` never matched the machine format) |
| Firmware | no `-bios` unless `bios` is set | `bios` unset or `openbios-sparc64` |
| virtio-balloon | `virtio-balloon-pci` without a bus: it took one of pciB's four slots (with four NICs QEMU refused the fourth, `PCI: no slot/function available for rtl8139`), and OpenBIOS can't manage it (`Cannot manage 'undefined' PCI device type`) | none, and no balloon polling at start: four NICs fit |
| Hotplug, arch | off for sparc; arch on create only | as was |

The checks (`assert_sparc64_profile` in `PVE::QemuServer::Machine`, from `$SPARC64_PROFILE`) run where
the sparc32 ones do: on create, on every config update against the config as it will be, and in
`config_to_command` (start, `qm showcmd`, vzdump). An existing config outside the profile (a VM from
the old wizard) stays readable and is refused when it is started or changed; a change that makes it
valid is accepted.

**Recommended profile** for sparc64 in Proxmox (one profile; the sparc32 table's counterpart):

| Machine | Firmware (`bios`) | `-cpu` | RAM | CPUs | Disk | CD-ROM | NIC | Display |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sun4u` | `openbios-sparc64` (default; no `-bios` needed) | none (TI UltraSparc IIi) | 512 MB default, 256-8192 MB | 1 | `ide0` (built-in IDE, primary master; `ide1` as a second disk) | `ide2` (secondary master) | `sunhme` (default); `virtio`, `e1000`, `rtl8139`, `ne2k_pci` for NetBSD | `std` (VGA + PS/2 keyboard), `serial0` or `none` |

- Boot from the first drive of `boot: order=` that holds something, as `-boot order=c|d`, no
  `bootindex`. qemu-server holds this profile as `$SPARC64_PROFILE` (above); the wizard creates it.
- Guests: NetBSD (11.1 tested end to end, 9.3's CD boots). Not OpenBSD 8.0 (installed kernel
  doesn't start), not Debian 12.0 ports (install fails), not Solaris for real use (with the
  package built with `openbios-sparc64` and `wsh/0021`, Solaris 10 1/13 reaches its installer and
  takes input on ttya, and its IDE disk attaches; installing, rebooting and booting the installed
  disk don't work yet, see "Solaris on sun4u"), not sun4v/niagara.
- Refuse: SCSI (LSI, virtio-scsi) and virtio-blk as the boot disk, `-smp` > 1, more than 8 GB,
  `sun4v`/`niagara`. Expect a host core at 100% per running VM: NetBSD doesn't idle on sun4u (below).
- Live migration, backup, snapshots with RAM: not tested for sparc64.

## sparc64: niagara (sun4v)

Whether Solaris 10 1/13 (u11) comes up on `-M niagara` (QEMU's sun4v machine: one UltraSPARC T1
strand), reproducing the work published at unix0.cc in 2026, and how far that is from a usable
VM. Measured 2026-11-16 with `qemu-system-sparc64` from the published `pve-qemu-kvm` 11.1.3-2+wsh7
unless stated, in the lab image, with the firmware supplied by hand (`scenarios/niagara-boot.py`,
which skips when the firmware isn't there). Sun's firmware, the T1 archive, the Solaris images and
the self-built firmware stay outside the repository and the package.

**Sources.** The unix0.cc articles (2026-07 to 2026-10: "the first touch", "Machine Description"
parts 1 and 2, "Solaris u10/u11 is successfully booted on 1GB config (tlb MD fix)", "256MB page
enabling" parts 1 and 2, "rebuilding sun4v hypervisor with PCIe") and the author's repositories
on GitHub under `unix0cc`: `md` (machine-description sources and built MD pairs), `mdbuild` (Sun's
`mdgen`/`mdlint` ported to GNU make), `md-artefacts` (boot logs per MD and guest),
`qemu-experimental-patches` (QEMU patches) and `sun4v-qemu-kit` (builds the whole firmware set from
source). Commits used: `md` c1b7b905, `sun4v-qemu-kit` e94cd4b8, `qemu-experimental-patches`
303e22db.

**What QEMU's machine is** (`hw/sparc64/niagara.c`, 11.1.3): it loads six files from `-L`
(`reset.bin` at `0xfff0000000`, `q.bin` the hypervisor at +0x10000, `openboot.bin` at +0x80000,
the hypervisor's machine description `1up-hv.bin` at `0x1f12080000`, the guest's machine
description `1up-md.bin` at `0x1f12000000`, `nvram1` at `0x1f11000000`); without any of them it
stops with `Unable to load a firmware for -M niagara`. Devices: a 16550 at `0x1f10000000` (the
console), `sun4v_rtc`, an unimplemented-device stub over the I/O bridge range, and the "virtual
disk": the first `if=pflash` drive is copied whole into a RAM region at `0x1f40000000` at start
(`rom_add_file_fixed`), on top of `-m`. That disk is writable by the guest, but only in RAM: nothing
reaches the file, every boot starts from the file again, and the image costs its size in host RAM
(the 2.2 GB DVD: 2.2 GB). An image of 2 GiB or more used to fail with `could not load ram disk`;
fixed upstream by `76dbe26fd6` (2026-07, by the unix0.cc author), which is in 11.1.0 and so in our
11.1.3 (the kit's README names 11.0.3 and 10.0.12 as the first fixed stable releases).
`max_cpus = 1`. No PCI, no NIC, no LDC channels, no sun4v virtual disk (`vdc`/`vds`) or network
(`vnet`) service anywhere in QEMU.

### Firmware: where from, and the licences

| What | Where | Licence (as stated in the files) |
| --- | --- | --- |
| OpenSPARC T1 archive `OpenSPARCT1_Arch.1.5.tar.bz2` (199 MB, sha256 `833b086196e2...`) | still downloadable from Oracle: `https://download.oracle.com/technetwork/systems/opensparc/OpenSPARCT1_Arch.1.5.tar.bz2` (HTTP 200 on 2026-11-16, no click-through); `S10image/` holds `reset.bin q.bin openboot.bin nvram1 1up-md.bin 1up-hv.bin` (2006) and `disk.s10hw2` (512 MB, Solaris 10 3/05 HW2) | the archive's `README` lists `GPLv2_License_OpenSPARCT1.txt`, `THIRDPARTYLICENSEREADME.txt`, `BINARY_SLA.txt` and `BSD+_License.txt`, but `BINARY_SLA.txt` isn't in the archive. Nothing names the licence of the `S10image/` binaries. The hypervisor and OpenBoot sources in the same archive carry Sun's BSD+ header ("Redistribution and use of this software in source and binary forms, with or without modification, are permitted provided that ... Redistribution in binary form must reproduce the above copyright notice ..."); the machine-description configurations (`legion/src/config/niagara/`) are GPL-2 |
| Sun's four firmware blobs (`reset.bin q.bin openboot.bin nvram1`) | also committed to GitHub: `unix0cc/md` `fw_blobs/` (byte-identical to `S10image/`, checked), and a set in `artyom-tarasenko/qemu-sun4v-md` (branch `1GiB-experimental`, not compared) | as above: copies, no added grant |
| OpenSPARC T2 archive `OpenSPARCT2_Arch.1.2.tar.bz2` (374 MB) | Oracle, same path, HTTP 200 | `BSD+_License.txt` (the text above) for the hypervisor and OpenBoot source |
| `sun4v-qemu-kit` (GitHub `unix0cc/sun4v-qemu-kit`) | builds all six files from the T2 archive's hypervisor and OpenBoot source (vendored unchanged in `src/`, patches applied to a copy), on Linux with the Debian/Ubuntu sparc64 cross toolchain and qemu-user, or on Solaris | `LICENSE`: "This repository is not one license": Sun's hypervisor and OpenBoot code BSD+; the machine descriptions (`md/`, derived from Sun's T1 configurations) GPL-2.0-only, so `1up-md.bin`/`1up-hv.bin` are GPL-2 object code; the kit's own files BSD-2-Clause. OpenBoot's build starts from one prebuilt Sun binary, `src/obp/obp/os/sun/sparc/forth.dic` ("We redistribute them under Sun's BSD+ grant ... That is our reading, not a statement in the files"); an experimental bootstrap from cforth (MIT) avoids it |

Assessment for the repository owner (not a legal opinion):

- (a) **Sun's prebuilt `S10image/` binaries in a Debian package: not advisable.** They are almost
  certainly built from the BSD+ sources, which would allow binary redistribution with the notice,
  but the archive itself doesn't say so: the `README` points to a `BINARY_SLA.txt` that isn't there,
  and that missing file is the one that would govern binaries. Others mirror them on GitHub, which
  proves nothing. `disk.s10hw2` is a Solaris installation and is out of the question.
- (b) **Building from source in CI looks permitted.** The hypervisor and OpenBoot are BSD+
  (binary redistribution allowed with the copyright notice and disclaimer reproduced in the
  package's documentation, no endorsement), the MDs GPL-2 (ship or point to the exact `md/`
  source; the kit commit is that source), the kit's own build files BSD-2-Clause. The residual
  doubts: the one prebuilt `forth.dic` (and six more dictionaries the build regenerates) carry no
  header, and the kit's authors say their BSD+ reading of them is their own; some T2-archive MD
  examples the kit followed say only "Use is subject to license terms". The kit is a one-author
  project that says AI was used throughout. Verified here: `./configure --with-md-mem=1024 && make
  -j6 all` at e94cd4b8 in a Debian 13 container (gcc 14.2, binutils 2.44, qemu-user 10.0.13; image
  1.24 GB) builds the set in 30 s, and that set boots both Solaris guests below.

### Does it start (stock firmware set)

Sun's `S10image/` set from the T1 archive, as shipped:

| Run | Result |
| --- | --- |
| no disk, `-m 256` | `OpenBoot 4.20.0, 256 MB memory available` on a "Sun Fire T2000, No Keyboard", `ok` 0.6 s after start |
| `disk.s10hw2`, `-m 256`, `boot disk` | Solaris 10 3/05 HW2 (`Generic_118822-23`, the `hsimd` driver for the Legion disk): `console login:` after 29 s; root without a password; `uname`: `SunOS unknown 5.10 Generic_118822-23 sun4v sparc sun4v`; `prtconf`: 256 MB; `psrinfo`: one virtual processor "at 5 MHz"; root `/dev/dsk/c0t0d0s0` (491 MB, UFS, writable in RAM); `ifconfig -a`: `lo0` only |
| Solaris 10 1/13 DVD, `-m 256`, `boot /virtual-devices/disk@0:f` | the boot archive and `unix` load from the DVD (OpenBoot reads it as an HSFS ramdisk); the kernel panics in `lgrp_init` ← `mlsetup`, `ERROR: Last Trap: Level 14 Interrupt`, back at `ok`. Sun's 2006 MD has an `mblock` node that no arc reaches (unix0.cc part 1: `lgrp_traverse: No memory blocks found`) |

### The Solaris 10 1/13 installer

What the published work changes:

- **Machine description** (not the hypervisor or OpenBoot). The guest MD needs a `memory` node
  linked to the `mblock`, a `cpus` node, `mmu-page-size-list` and `mmu-#va-bits` on the CPU, a
  `cache` node and a per-CPU `tlb` node (without it: `failed to get MMU CTX domain index` in
  `sfmmu_cpu_init`), and the memory size raised from 256 MB to 1024 MB in both MDs (`1up.pdesc`
  `mblock.size`, `1up.hdesc` `GUEST(...)`). Built with `mdgen`; `unix0cc/md` has the sources, the
  patches and the built pairs (`bin/tlb_fix/1024`).
- **QEMU**: none for 1024 MB. The `int64_t` vdisk size fix (`76dbe26fd6`) is upstream. The TTE
  page-size patch ("target/sparc: implement TTE page-size for 32M/256M pages", v2, posted to
  qemu-devel 2026-09-18, not in master on 2026-11-16) matters only above 1024 MB, where Solaris
  maps the kernel with 256 MB pages (below).
- RAM: `-m` must equal the MD's size.

Measured (`niagara-boot.py ISO=sol-10-u11-ga-sparc-dvd.iso`, at `ok`: `boot
/virtual-devices/disk@0:f`; the installer on the serial console, terminal type DEC VT100):

| Firmware | `-m` | QEMU | Result |
| --- | --- | --- | --- |
| Sun's set + `unix0cc/md` `bin/tlb_fix/1024` MD pair | 1024 | package | `SunOS Release 5.10 Version Generic_147147-26 64-bit` at 19 s, `Configuring devices.`, `Serial console, reverting to text install`, "Select a Language" at 212 s, the terminal type, "The Oracle Solaris Installation Program", F2, "Identify This System" at 262 s |
| `sun4v-qemu-kit` built here (legion, 1024 MB) | 1024 | package | the same, kernel at 17 s, "Select a Language" at 172 s, "Identify This System" at 211 s; no network screens (no interface), "Host Name", "Confirm Information", "Time Zone", "Country or Region", "Date and Time", "Confirm Information", "Root Password", "Enabling remote services" (`WALK=40`), then at 301 s `System identification complete.`, `/sbin/install-begin: test: argument expected`, `Exiting to shell...` and a root shell; there `format`: `No disks found!`, `/dev/dsk` empty, `/` is `/ramdisk-root:a` (217 MB, 99% full), `ifconfig -a`: `lo0` only |
| Sun's set + `md` `_test/pagesize_256m/2048` | 2048 | package | hangs: `Loading: /platform/sun4v/kernel/sparcv9/unix`, `WARNING: max-cpus property missing ...`, then nothing for 900 s (no kernel banner), one host core busy |
| the same | 2048 | v11.1.3 + the TTE patch, built here | kernel banner at 16 s, "Select a Language" at 313 s, "Identify This System" at 389 s |

On the way the kernel prints `WARNING: max-cpus property missing from MD platform node`, `NOTICE:
Disabling watchdog as watchdog services are not available`, `Using RPC Bootparams for network
configuration information.` and `svc:/system/filesystem/local:default: WARNING: /usr/sbin/zfs mount
-a failed`; all harmless here. The serial logs are in the lab's evidence directory, not here.

### What is missing for real use

- **A writable disk, and the install media.** The installer never gets to the disk question: after
  system identification `install-begin` looks for the DVD as a block device under `/dev/dsk` (to
  mount the packages), finds none and exits to a shell. So a usable install needs both a disk and
  the DVD visible to Solaris as a device (or an install server on a network). There is no disk an
  installer could use either: the Legion disk is a RAM copy of a file (above), and only a guest
  with Sun's `hsimd` driver sees it as a disk (`disk.s10hw2` does; the Solaris 10/11 media don't). The DVD reaches the installer only because OpenBoot loads its boot
  archive as a ramdisk root. QEMU has no sun4v virtual I/O at all: the sun4v way (LDC channels in
  the hypervisor plus a virtual disk server, `vds`/`vdc`, and `vsw`/`vnet` for the network, as in
  LDoms) would need LDC endpoints in the MDs, a service on the other end of each channel (in a real
  system a control domain; here QEMU), and the hypervisor's LDC code; none of it exists. The author
  chose PCIe instead (`sun4v-qemu-kit` `TARGET=pci`: a rebuilt hypervisor with Fire I/O, a PCIe root
  nexus in the MD, OpenBoot's `/pci@0` with an e1000 and a CMD646 IDE). The firmware side is
  published; the QEMU side (a "vpci" host bridge, CMD646 and mptsas for this machine, sun4v mondo
  queues, strand halt) is not: it sits in the author's unpublished `test/` stack. The kit's
  `build_matrix` reports Solaris 10 u11 installed on the CMD646 disk booting to `console login:`
  with `e1000g` up and 200 MB written and read, on that unpublished QEMU. Not reproducible here.
- **Network**: none (no device; `ifconfig -a` shows `lo0`). Same answer as the disk.
- **More than one CPU**: `max_cpus = 1` in QEMU; the T1 archive's 32-strand MDs (`1g32p-*`) can't be
  used. Cross-calls would also need sun4v mondo queues in QEMU (the author's 0004, unpublished).
- **RAM**: `-m` must equal the MD (otherwise `qemu: fatal: Trap 0x0032 ... MAXTL (6)` before any
  output, per the kit's README). Up to 1024 MB works on the package's QEMU; above that Solaris
  10 1/13 uses 256 MB pages and needs the TTE patch (above). The image on `if=pflash` adds its full
  size in host RAM.
- **Power-off and reset** (both firmware sets): Solaris's `init 5` on `disk.s10hw2` ends at
  `Program terminated` / `ok` with Sun's set (34 s), and with the kit's set QEMU aborts (`qemu:
  fatal: Trap 0x0034 while trap level (6) >= MAXTL (6)`, exit code -6, 39 s). At `ok`,
  `reset-all` and `power-off` do nothing visible with Sun's set (the prompt comes back, QEMU keeps
  running); with the kit's set `reset-all` aborts QEMU (`Trap 0x0032 ... MAXTL (6)`). QMP
  `system_powerdown` makes OpenBoot print `ERROR: /virtual-devices@100/console@1: Last Trap:
  Watchdog Reset`, and QMP `system_reset` brings no banner back within 60 s (both with Sun's set;
  not tried with the kit's). So the machine can only
  be stopped by killing QEMU, which PVE can do (`qm stop`), but a guest shutdown never ends the VM.
- **Idle**: none. QEMU's host CPU over 60 s: 103% of a core at the `ok` prompt, 100% at the Solaris
  10 HW2 shell, 101% at the installer screen; 100% with the kit's firmware too. Neither Sun's
  hypervisor nor QEMU stops an idle strand. The author publishes two QEMU patches for it
  (`qemu-experimental-patches` `devel/0023` strand halt, `devel/0024` wake-up), meant for a
  self-built hypervisor and not proposed upstream; they depend on patches from his unpublished
  `test/` stack (0010, the `%asr26` write decode, and 0004, mondo queues), so they can't be applied
  on their own.
- **Speed**: the guest reports 5 MHz (the MD's clock value). Boot to the installer takes 3-4
  minutes at 1024 MB (6.5 at 2048 MB): the kernel banner comes at 16-19 s, the rest is the
  miniroot starting its services. The HW2 disk logs in after 29-37 s.

### Estimate, and which way to go

"Solaris 10 installed to disk on niagara", from here:

1. A disk and a NIC. Either reproduce the PCIe route in QEMU (a sun4v PCIe host bridge as the
   rebuilt hypervisor's Fire code expects it, MSI/interrupt delivery through the hypervisor's
   interrupt queues, mondo queues, CMD646 on that bus) or build sun4v LDC plus a `vds` disk server
   and `vsw` network service in QEMU. Either is new device-model work, by our estimate thousands of
   lines and weeks rather than days (not measured: nothing of it was attempted here), and the firmware side would have to be built from `sun4v-qemu-kit`
   (`TARGET=pci`) because Sun's prebuilt hypervisor has Fire I/O compiled out. The cheaper
   alternative is to wait for, or ask, the author to publish the QEMU stack they already run.
2. A strand halt (idle), power-off/reset through the hypervisor, and probably the TTE patch
   (for more than 1 GB). Smaller: days, partly published.
3. qemu-server: a firmware path for six user-supplied or self-built files, `-M niagara`, `if=pflash`,
   `-m` tied to the firmware's MD, no hotplug. Small once 1 and 2 exist.

Against that, sun4u ("Solaris on sun4u" above): QEMU's sun4u is an Ultra 5-like machine whose
devices are the Ultra 5/10's own, which Solaris 8-10 drive (CMD646 IDE, hme), and everything is open source and already in
the package (OpenBIOS is GPL). What fails is OpenBIOS's memory management (`ofmem`), a contained
piece of firmware, with an open end behind it.

Recommendation: **pursue sun4u (`ofmem`) first, keep niagara as a demonstration.** Reasons: on
niagara the hard part is a disk and a NIC that only exist as someone else's unpublished QEMU work,
and every step needs non-Debian firmware built from a third-party kit with mixed licences; on sun4u
the disk and network models are done and the firmware is ours to patch. Revisit niagara if the
unix0.cc QEMU stack (vpci, CMD646 for sun4v, strand halt) is published or reaches upstream: then the
firmware can be built in CI from `sun4v-qemu-kit` and the remaining work is mostly packaging and
qemu-server.

## Supported profiles

The contract for sparc32 (`arch: sparc`, always TCG), from the measurements under "SS-10 and
SS-20" and "SMP". qemu-server holds it as `$SPARC32_PROFILES` in `PVE::QemuServer::Machine` and validates
and builds the command from it; pve-manager mirrors it in `PVE.qemu.Architecture.sparc32Profiles`.

| Machine | Firmware (`bios`) | `-cpu` | RAM | CPUs |
| --- | --- | --- | --- | --- |
| SS-5 (default) | `openbios-sparc32` (default), `ss5.bin` | none (machine default) | 256 MB | 1 |
| SS-10 | `openbios-sparc32` | none | 512 MB | 1-4 |
| SS-20 | `openbios-sparc32` | none | 512 MB | 1-4 |
| SS-20 | `ss20_v2.25_rom` | `TI-SuperSparc-50` | 512 MB | 1 |

- Display: `cg3` (default), `tcx`, `none`, `serial0`/`serial1` (ttya/ttyb). No resolution option
  (`-g`): qemu-server passes none, so cg3 runs at QEMU's 1024x768.
- Disk on the built-in ESP at SCSI target 3, CD-ROM at target 6 (`physical_block_size=512`), the
  built-in lance with `net0`'s MAC, at most one NIC.
- `ss10_v2.25_rom` stays readable in existing configs but matches no profile (it doesn't run on
  QEMU's SS-10).
- CPUs: sockets x cores, one by default. 2-4 only on SS-10/SS-20 with OpenBIOS and only with
  `pve-qemu-kvm` 11.1.3-2+wsh10 or later (patch 0019; Solaris hangs without it); details, cost and
  why the Sun PROM stays at one under "SMP".
- sparc64 has one profile, `$SPARC64_PROFILE` in `PVE::QemuServer::Machine` (mirrored in
  `PVE.qemu.Architecture.sparc64Profile`): `sun4u`, `openbios-sparc64`, one CPU, up to 8192 MB, disks
  and CD-ROMs on the built-in IDE, `-boot order=c|d` instead of `bootindex`, no balloon, at most four
  NICs (`sunhme`, `virtio`, `e1000`, `rtl8139`, `ne2k_pci`), displays `std`, `serial0`, `none`. Details
  under "sparc64 (sun4u)".

## qemu-server

`submodules/qemu-server.patch`, everything gated on `arch` matching `sparc`:

- **Architecture:** `arch` (the `pve-qm-cpu-arch` option) takes `sparc` and `sparc64`, on create
  only: changing it on an existing VM is refused for every architecture (x86_64 to aarch64 too), and
  so is deleting it when that changes the architecture. The CPU model and CPU flag capability APIs
  return empty lists for sparc.
- **Binaries:** `sparc` → `/usr/bin/qemu-system-sparc`, `sparc64` → `/usr/bin/qemu-system-sparc64`.
- **Machines:** `SS-5` (sparc) and `sun4u` (sparc64) by default; the machine regex accepts
  `SS-\d{1,2}` and `sun4[a-z]` with an optional `+pveN` (a snapshot's `runningmachine`), type `sun`.
- **Profiles:** `assert_sparc32_profile` checks the machine, the firmware for the machine, memory,
  sockets × cores up to the profile's most (1 or 4), `vcpus` equal to it, no CPU hotplug, no `cpu`, the display, no guest agent, serial0/serial1 only, one lance NIC and `audio0` (SS-5 only, `device=cs4231`, no SPICE).
  It runs on create (before the config exists), on every config update against the config as it
  will be (pending changes and deletions included), and in `config_to_command` (start, `qm showcmd`,
  vzdump). `assert_sparc64_profile` does the same for sparc64 (machine, firmware, memory, one CPU, no
  `cpu`, the display, serial0/serial1, no guest agent, IDE only, the NIC models and at most four NICs). Reading a config (`GET .../config`, the VM list, `qm config`) never checks it: a config
  outside the profiles stays readable and is refused only when it is started or changed, with a
  message naming the allowed values; a change that makes it valid is accepted.
- **Firmware:** `bios` accepts `openbios-sparc32`, `openbios-sparc64`, `ss5.bin`,
  `ss10_v2.25_rom`, `ss20_v2.25_rom`, passed as `-bios`.
- **CPU:** `-cpu` only from the profile (`TI-SuperSparc-50` for SS-20 + `ss20_v2.25_rom`); the generic
  `cpu` option is refused on sparc32 and never emitted on sparc or sparc64.
- **Display:** `vga` accepts `tcx` and `cg3`, passed as `-vga <type>`; sparc32 defaults to `cg3`
  (QEMU's sun4m has no `std`).
- **Disks:** sparc32 drives are `scsi-hd`/`scsi-cd` on the built-in ESP
  (`channel=0,scsi-id=<unit>,lun=0`); sparc64 drives are `ide-hd`/`ide-cd` on the built-in IDE
  (`bus=ide.<n>,unit=<n>`).
- **CD as a disk:** Solaris 2.4 and 2.5.1 boot their installer only from a CD that answers as a
  disk; from a `scsi-cd` their kernel panics with `vfs_mountroot: cannot mount root`. A sparc32
  SCSI CD-ROM with an ISO takes `cd_as_disk=1` (`scsi6: local:iso/<cd>.iso,media=cdrom,cd_as_disk=1`):
  qemu-server then emits `scsi-hd` (with the CD-ROM's `physical_block_size=512`) instead of
  `scsi-cd`. The drive stays a CD-ROM to PVE (`media=cdrom`): its blockdev is read only, and it is
  not backed up, snapshotted, cloned or freed, as before. `assert_cd_as_disk` (Machine.pm) refuses it
  on every other architecture, on a disk (no `media=cdrom`), on the host's CD-ROM drive or a `/dev`
  path, at create, update and start; other buses don't have the option in their schema (`ide2:
  invalid format`). Without a medium (`none`) the drive is an empty `scsi-cd`, so ejecting from the
  web UI (which keeps the option) still works. A medium change, an eject or turning the option on or
  off on a running VM stays pending until the next start (a `scsi-hd` has no removable medium).
  Tests: qemu-server's `cfg2cmd/sparc32-ss5-cd-as-disk.conf`, `sparc32-cd-as-disk-ejected.conf`,
  four `*-cd-as-disk-*-error.conf`, `hotplug/sparc32-cd-as-disk-*.conf`; e2e
  `sparc-profiles.spec.ts` ("a CD that answers as a disk"); the lab's `sol251-ss5` and `sol24-ss5`
  install targets through PVE. The web UI has no field for it (set with `qm set` or the API).
- **Boot:** sparc64 devices get no `bootindex`; the boot device is `-boot order=c|d` from the boot
  order (`sparc64_boot_device`), and the default boot order of a new sparc64 VM has the CD-ROM first. CD-ROMs get
  `physical_block_size=512` (Sun drives used 512-byte blocks). Drives are `-blockdev` nodes as on
  x86 (the machine version follows the QEMU version), which the backup job finds.
- **Network:** sparc32 uses the built-in lance (`-net nic,model=lance,macaddr=<net0's MAC>,netdev=net0`
  next to the usual `-netdev type=tap,id=net0,...`, not hot-pluggable; sun4m creates one lance and
  only warns about a second `-net nic`). The lance is peered with the `net0` netdev directly, so
  `set_link net0` reaches it as on x86 (it used to hang off a hub behind a netdev named `lance.0`,
  and every `set_link` failed with `Device 'net0' not found`). QEMU names the NIC itself `lance.0`.
  sparc64 puts `sunhme` on `pciB`.
- **Machine version:** QEMU's sparc machines have no versioned variants, so a running VM's machine
  (`SS-5+pve0`, `sun4u+pve0` from `query-machines`) carries none. `get_machine_version` in
  `PVE::QemuServer::Machine` resolves it to the QEMU version (of the running process when a VMID is
  given, else of the installed binary), as `config_to_command` does; `is_machine_version_at_least`
  uses it. Before, every check on a running sparc VM died with `internal error: cannot check version
  of invalid string '10'`.
- **Serial:** serial0/serial1 are the machine's ttya/ttyb, `-serial chardev:serialN` (no
  `isa-serial`); on sparc64 too, where an `isa-serial` was a third port beside the ebus ones and
  OpenBIOS's console never reached the socket.
- **`smm=off`** is never added on sun4m or sun4u (neither has the property; sun4u failed to start).
- **`-bios`** only on sparc: it was also passed for `bios: ovmf`, which an aarch64 VM refuses next to
  its pflash.
- **Left out on sparc:** `-smbios`, PCI passthrough (ignored with a message), USB and the tablet,
  vmgenid, virtio-balloon.
- **Snapshots with RAM:** a sparc VM usually runs without `-cpu`, so `runningcpu` is only recorded
  when there is one.
- **Sound:** `audio0: device=cs4231,driver=none|alsa|pa|pipewire` on SS-5 emits
  `-audiodev <driver>,id=<driver>-backend0` and `-machine audiodev=<driver>-backend0` (the CS4231 is
  built in: no `-device`). `cs4231` is a new value of `audio0`'s `device`; no driver was added.
  Refused: `driver=spice`, the default (no SPICE display on sparc32), another device on SS-5,
  `audio0` on SS-10/SS-20 (DBRI, not emulated) and on sparc64 (`assert_sparc32_profile`,
  `assert_sparc64_profile`), and `cs4231` on any other architecture (`assert_audio_device`); all at
  create, update and start. Needs a pve-qemu-kvm with 0028-0033: older ones have no `audiodev` on
  sun4m and don't start the VM. Tests: `cfg2cmd/sparc32-ss5-audio*.conf`,
  `sparc32-ss20-audio-error.conf`, `sparc64-audio-error.conf`, `audio-cs4231-x86-error.conf`; e2e
  `sparc-profiles.spec.ts` ("sound on the SS-5"). Details under "Audio".

### Operations on a running VM

Tested in the e2e container (`e2e/tests/running-vm.spec.ts`, every sparc32 profile, sun4u and an x86
control) and with qemu-server's hotplug tests (`src/test/hotplug/sparc*.conf`):

- **Live:** CD-ROM medium change, eject (`none`) and insert; net0's bridge, VLAN tag, `link_down`
  (Disconnect), rate limit and firewall (the tap is re-plugged on the host, the guest's link goes
  down and up); disk resize; clone and move disk (blockdev-mirror); snapshot with and without RAM
  and rollback; backup in snapshot mode; `qm monitor`, `sendkey`, `suspend`/`resume`, `reset`,
  `shutdown`/`stop`, `status --verbose`.
- **Pending until the next start:** a new NIC model or MAC (the lance is built in; sun4u's PCI
  buses have no hotplug), adding or removing a disk, memory. qemu-server treats every hotplug
  feature as off for sparc (`hotplug` is ignored), so these are stored as pending without an error
  and applied on the next start.
- **Pending until the next start** as well: the CPU count (sockets, cores) where the profile allows
  more than one; no CPU hotplug.
- **Refused:** a CPU count above the profile's (`sparc: SS-5 with firmware openbios-sparc32 takes at
  most 1 CPU ...`, the profile check);
  conversion to a template while running and migration to the same node (as for every VM).
- Not tested: live migration (see below).
- sparc32 has no balloon device: the start no longer warns that it can't set its polling interval.

### Backup and restore

Tested in the e2e container (`e2e/tests/sparc-profiles.spec.ts`), without a guest OS:

- `vzdump --mode stop` and `qmrestore` to a new VMID work for every profile: the restored config
  equals the original except for the disk volume, and the disk image has the same checksum.
- `vzdump --mode snapshot` of a running VM works (QEMU's backup job sees the `-blockdev` drives);
  there is no guest agent, so no fs-freeze.
- `qm snapshot --vmstate 1` and `qm rollback` work (SS-5 OpenBIOS and SS-20 PROM tested). Before
  this they failed with `could not read commandline of running machine` (no `-cpu`), then with
  `unable to parse value of 'runningmachine'` (`SS-5+pve0` didn't match the machine regex).
- Not tested: live migration (`QemuMigrate` still reads `-cpu` from the running VM, which fails
  without one), and backups while a guest OS writes.

## pve-manager

`submodules/pve-manager.patch`:

- `qemu/AudioEdit.js`: on a sparc VM the Audio Device editor offers only `cs4231` and no SPICE
  driver (`none` preselected).
- `qemu/Architecture.js`: SPARC (32-bit) and SPARC (64-bit) in the create wizard's vCPU
  Architecture (an advanced option); per architecture the OS types (Linux, Solaris, Other),
  machines, firmware, displays, SCSI controller and buses; the mirrored sparc32 profiles; the
  firmware display names that both the selectors and the renderers use.
- sparc32 in the wizard and the Hardware editors: machine SS-5 (default), SS-10 or SS-20 (no
  versions), only the firmware the machine runs, memory preset to and capped at the machine's
  maximum, CPU type disabled, sockets and cores disabled (nothing is submitted) except on SS-10 and
  SS-20 with OpenBIOS, where they go up to 4 CPUs in total with a hint on the cost, displays cg3 (default), tcx,
  serial0, serial1 and none, the lance NIC only, the first disk on SCSI target 3 and the CD-ROM on
  target 6.
- sparc64 in the wizard and the Hardware editors, from `sparc64Profile`: disks and CD-ROMs on IDE
  only (first disk `ide0`, CD-ROM `ide2`), memory preset to 512 MB and capped at 8192, sockets, cores
  and CPU type disabled, displays std (default), serial0 and none, the profile's NIC models (`sunhme`
  the default), Add → Network Device disabled at four NICs.
- The architecture of an existing VM is read-only (no editor, no Add → Architecture).
- Selectors: firmware (OpenBIOS, SPARCstation 5/20 PROM), display (TCX, CG3), network (Lance, Sun
  Happy Meal).

## Testing

- `e2e/sparc` (#197): installs and boots Solaris 2.5.1 and 2.6 unattended against the shipped
  QEMU and records every step. Its README lists what it found about devices and boot paths.
- qtests: `sun4m-escc-test` (0005), `sun4m-apc-test` (0011), `sun4m-solaris-idle-test` (0016),
  `sun4m-mmu-nofault-test` (0018), `sun4m-pil-delay-slot-test` (0020), `sun4m-fsr-rd-test` (0027),
  `sun4m-cs4231-test` (0033) and `am53c974-test` with 0007;
  they
  build in a QEMU tree with the series applied.
- cg3 sizes: the lab's `display` matrix (`scenarios/cg3-display.py`).
- cg3 and TCX: the TCX/cg3 banner and no-driver cases in `display`, the desktop cases in `display-x`
  (`scenarios/fb-display.py`, disks prepared by `solaris-tcx-packages.py`); results under "cg3 and TCX".
- Idle: the lab's `idle` matrix (`scenarios/idle.py`).
- Stop-A: the lab's `stopa` matrix (`scenarios/stop-a.py`); results under "Stop-A".
- SMP: the lab's `smp` matrix (`scenarios/smp-soak.py`, the bench disk) and the qtest
  `sun4m-pil-delay-slot-test` (0020); results under "SMP".
- Machines, firmware and speed: the lab's `machines` and `bench` matrices (`scenarios/bench.py`);
  results under "SS-10 and SS-20".
- sparc64: the lab's `sparc64` matrix (`scenarios/_sparc64.py`, `sparc64-*.py`,
  `netbsd-install-sparc64.py`); results under "sparc64 (sun4u)".
- Recognised benchmarks (Dhrystone, Whetstone, Hanoi, nbench, lmbench subset): the lab's `benchdisk`
  matrix (`scenarios/bench-disk.py` with the bench disk); results under "Benchmarks", the baseline
  for QEMU changes.
- Profiles: qemu-server's `src/test/cfg2cmd/sparc32-*.conf` (the command per profile and the refused
  combinations, 2 and 4 CPUs among them) and `src/test/hotplug/sparc32-cores-add.conf`, and
  `e2e/tests/sparc-profiles.spec.ts` (API and wizard per profile, refusals, more than one CPU,
  backup/restore, and that the lab's machine arguments match `qm showcmd`). A real boot with 2 CPUs
  through PVE: the lab's `pve` matrix, case `solaris26-ss20-smp2`.
- sparc64 profile: qemu-server's `src/test/cfg2cmd/sparc64-*.conf` (the wizard layout, serial
  console, an ejected CD, each refusal) and `e2e/tests/sparc64-profile.spec.ts` (API, `-boot`, QEMU
  accepts it, refusals, an old-wizard VM, the wizard and the Hardware editors).
- Running VMs: `e2e/tests/running-vm.spec.ts` (CD medium, net0 changes, pending changes and other
  operations on a started VM per profile, sun4u and an x86 control) and qemu-server's
  `src/test/hotplug/sparc*.conf` and `src/test/run_machine_version_tests.pl`.
- What PVE starts: the lab's attach mode and `pve_matrix.py` (`e2e/sparc/README.md`, "Attach to a PVE
  VM"; the `pve` choice of the `sparc lab` workflow) create VMs through the API in the e2e container
  and drive the QEMU that PVE started: the Solaris 2.6 install and first boot on the default SS-5
  profile, NetBSD 11.1 sparc64 to its shell (laid out as the wizard creates it, OpenBIOS booting the
  CD by itself), Alpine aarch64 and x86_64 to a login.

## Known gaps

- **Sound:** SS-5 only, playback only, and not in the web console ("Audio").
- **CD as a disk in the web UI:** `cd_as_disk=1` (see "Supported profiles") has no field in the CD/DVD
  editor; the editor keeps it when the medium is changed or ejected.
- **Resolution:** qemu-server has no option for `-g`; cg3 runs at 1024x768 (what the Sun PROMs and
  Solaris' X server need).
- **Live migration:** fails for a VM without `-cpu` (see "Backup and restore").
- **SS-20 PROM with a framebuffer:** Solaris 2.6 panics at boot with the console on cg3 or TCX
  under `ss20_v2.25_rom` ("cg3 and TCX"); with a serial console it boots.
- **TCX depth:** qemu-server passes no `-g`, so TCX is 8-bit; 24-bit only works with OpenBIOS.
- **Break on a serial console:** QEMU's ESCC never ends a break; Solaris on ttya then spins in its
  serial interrupt and hangs ("Stop-A"). PVE can't send a break; Stop-A on the keyboard works with a
  framebuffer console.
- **OpenBIOS `cdrom` alias:** it doesn't find a CD that answers as a disk; boot that by device
  path (`sd@6,0:d`).
- **sparc32 reboot with a boot string:** OpenBIOS ignores the arguments of a client's reboot
  (`reboot -- disk:b`) and boots `boot-device` again; Solaris 8's Web Start relies on it to start
  its mini-root from the swap slice. `setenv` at the `0 >` prompt doesn't survive the reset; the
  install target sets `-prom-env auto-boot?=false` (`args`) for the install only and boots the
  slice by path. A fix in OpenBIOS (keep the boot string across the reset) is not written. SunOS
  4.1.4's CD does the same after copying its miniroot to `sd0b` (option 1, reboot); its install
  target works around it the same way (`boot .../sd@3,0:b -sw` at `0 >`).
- **SunOS 4.1.4's install kernel and 256 MB:** the CD's kernel (`munix`, booted from slice d) stops
  QEMU right after it is loaded with 256 MB: `qemu: fatal: Trap 0x29 (Data Access Error) while
  interrupts disabled, Error state` in the node's journal, the VM is off (pve-qemu-kvm
  11.1.3-2+wsh15, SS-5, OpenBIOS, through PVE; the same with the lab's own QEMU). 64 MB works, and
  the installed kernel runs with 256 MB. qemu-server has nothing per boot, so the install target
  sets `memory: 64` for its install phase and the profile's 256 afterwards (`qm set`); not
  investigated in QEMU.
- **SunOS 4.1.4 on ttya holds back output:** the last character of a burst of console output often
  arrives only when the next key is typed (a curses cursor move, a field's echo). Seen under `suninstall` and sys-config, not with Solaris; the lab's
  SunOS scenarios match the text before it. Cause not investigated (the guest's `zs` driver or
  QEMU's ESCC transmit interrupt).
