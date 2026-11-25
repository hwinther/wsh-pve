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
| `0016-tests-qtest-test-the-Solaris-idle-halt-on-sun4m` | qtest `sun4m-solaris-idle-test` for 0014-0015; a decoy 1 in the PROM at `disp_nrunnable`'s RAM address checks that the helper reads RAM with the MMU off | ours | not in QEMU |
| `0017-target-sparc-flush-the-TLB-on-a-no-fault-bit-change-` | Solaris on SS-5 ran call-heavy user code 4-10x slower than on SS-20: its microSPARC window-trap handlers set and clear the MMU no-fault bit (NF) twice per trap, and QEMU flushed its whole TLB on every NF change. Now NF flushes only while the TLB holds an entry made for a fault in no-fault mode (the only entries that depend on it); boot mode flushes as before. Trace event `sparc_mmu_ctrl_flush` ("Why SS-5 was slower", "Benchmarks") | ours | not fixed; see `upstream/qemu-srmmu-control-register-flush.md` |
| `0018-tests-qtest-test-no-fault-mode-and-the-TLB-on-sun4m` | qtest `sun4m-mmu-nofault-test` for 0017: an entry made in no-fault mode must not survive NF being cleared (SS-5 and SS-20) | ours | not in QEMU |
| `0019-target-sparc-let-a-write-to-psr-in-a-delay-slot-end-` | Solaris 2.x with more than one CPU (SS-10/SS-20) hung within minutes: a write to `%psr` in a delay slot (Solaris's `splx`) didn't end the translation block, so an interrupt it unmasked wasn't taken until something else stopped the CPU; a CPU spinning in such a loop never took the other CPU's cross-call ("SMP") | ours | not fixed (since 8.2.0, `25524734c6`); see `upstream/qemu-sun4m-smp-psr-delay-slot.md` |
| `0020-tests-qtest-test-an-interrupt-let-in-from-a-delay-sl` | qtest `sun4m-pil-delay-slot-test` for 0019: a pending soft interrupt must be taken after PIL is lowered by a plain `wr %psr` and by one in the delay slot of `ba`, `bne`, `bne,a` and `jmpl` | ours | not in QEMU |
| `0021-ide-cmd646-latch-the-interrupt-status-bits-until-the` | The cmd646 (sun4u's built-in IDE) cleared its interrupt status bits (MRDMODE, CFR, ARTTIM23) when the drive dropped INTRQ, i.e. when the guest read the drive's status. Solaris 10 reads the status and then polls those bits: `WARNING: Interrupt not seen after set_features` for every IDE device. Now they stay set until the guest writes 1 to them in config space (the BMDMA mirror of MRDMODE doesn't clear them); the PCI interrupt line keeps following INTRQ (driving it from the latched bits broke Linux and OpenBSD), kept in a field that a device reset clears and that isn't in the migration stream ("Solaris on sun4u") | ours | not fixed; see `upstream/qemu-cmd646-interrupt-latch.md` |
| `0022-tests-qtest-test-the-cmd646-interrupt-status-latch-o` | qtest `sun4u-cmd646-test` for 0021: after SET FEATURES and a status read the bits stay set until written 1, the interrupt line (seen through the sabre) follows INTRQ, and a reset with INTRQ up leaves the line low | ours | not in QEMU |
| `0023-target-sparc-halt-idle-CPUs-in-the-Solaris-multiproc` | With 2-4 CPUs every idle vCPU of Solaris 2.5.1-9 spun at 100% of a host core: the multiprocessor idle loop never calls `idle_cpu`, and nothing tells an idle CPU that it has work. The translator recognises the call of `disp_getwork` in that loop and halts the CPU there; the halt ends when another CPU queues work for it (checked on its next `wr %psr`), on an interrupt, or after 10 ms. The Solaris idle helpers read `disp_nrunnable` through a page table walk instead of `probe_access_flags()`, which asserts when another CPU has flushed the TLB entry (with the MMU off the address is taken as physical: the debug lookup would read the PROM) ("SMP", "Idle with more than one CPU") | ours | not in QEMU |
| `0024-hw-sparc-sun4m-add-the-solaris-smp-idle-option-on-by` | `-M <sun4m>,solaris-smp-idle=on\|off` for 0023, on by default, does nothing with one CPU | ours | not in QEMU |
| `0025-tests-qtest-test-the-Solaris-multiprocessor-idle-hal` | qtest `sun4m-solaris-smp-idle-test` for 0023-0024, with the same PROM decoy | ours | not in QEMU |
| `0026-target-sparc-let-sparc32-ld-and-st-fsr-ignore-rd` | sparc32 raised an illegal instruction trap for `ld [..], %fsr` and `st %fsr, [..]` with rd other than 0; V7 and V8 chips ignore rd there. The `_sigtramp` of an old static SunOS 4 libc saves and restores the FSR with rd 4 (`c92ba0e0`, `c90ba0e0`), so such programs died with SIGILL at their first signal after using the FPU (LEMU's case: Island Productivity's 1992 licence daemon `islandLIC`). sparc32 takes any rd again, as before QEMU 8.2; sparc64 doesn't change | [LEMU `0cdd14c1`](https://github.com/tenox7/lemu/commit/0cdd14c1487c30b14a983db634658fd7a29789b2) by Antoni Sawicki | not fixed (since 8.2.0, `3d3c06737b`); see `upstream/qemu-sparc32-ldfsr-rd.md` |
| `0027-tests-qtest-test-ld-and-st-fsr-with-any-rd-on-sun4m` | qtest `sun4m-fsr-rd-test` for 0026: `ld %fsr` and `st %fsr` with rd 0, 4 (the exact words above) and 31 run without a trap and the FSR reads back | ours | not in QEMU |
| `0028-hw-audio-cs4231-play-sound-through-the-apc-dma-engin` | The SS-5's CS4231 was a register stub: its APC DMA kept what was written and never interrupted, so every program that waited for the end of a sound on `/dev/audio` hung (SunOS 4.1.4). The APC now plays its playback buffers, read through the IOMMU, into the machine's audiodev at the codec's rate (u-law, A-law, 8-bit, 16-bit LE and BE; ADPCM plays silence), with PI, PD, PM and PMI and the DAC volume. Capture is not done: the capture pipe reads as empty ("Audio") | [LEMU `2938ff88`](https://github.com/tenox7/lemu/commit/2938ff887a938b396b44588927bd14f90faa8e0c) by Antoni Sawicki | not in QEMU |
| `0029-hw-sparc-sun4m-give-the-cs4231-its-interrupt-level-i` | The machine side of 0028: `-machine audiodev=` on sun4m, the codec's IOMMU link, and its interrupt on bit 9 (processor level 5, OpenBIOS's `intr` 5; 0030 moves it) | [LEMU `42d32575`](https://github.com/tenox7/lemu/commit/42d325754c976b2eda0c7113c42f321a65373af6) by Antoni Sawicki | not in QEMU |
| `0030-hw-sparc-sun4m-raise-the-SS-5-s-cs4231-at-SBus-level` | The real SS-5 has the codec at SBus level 5, processor level 9 (`ss5.bin` 2.15 gives the node `intr 0x39`). On bit 9, Solaris, which takes OpenBIOS's `interrupts 5`, never got its interrupt: audioplay stopped after the first second with `processor level 3 SBus interrupt not serviced`. Now SBus level 5 (bit 11), through an OR gate with the cg3 or TCX, which use that level too. Needs openbios patch 0018 for SunOS 4 | ours | not in QEMU (upstream wires the stub to bit 5, processor level 11) |
| `0031-hw-audio-cs4231-start-without-sound-when-there-is-no` | With 0028 an SS-5 without `-machine audiodev` asked for QEMU's default audio backend, and with none available didn't start (`no default audio driver available`). It still takes the default backend (LEMU's SunOS kit plays through it), but without one it now starts with a warning (`cs4231: no sound: no default audio driver available`), opens no voice and keeps its registers only. The version reviewed in LEMU ([lemu-port.md](../upstream/lemu-port.md)); the first one here opened no voice without an audiodev | ours | — |
| `0032-hw-audio-cs4231-play-out-the-last-samples-when-playb` | The APC takes its samples up to 50 ms ahead of the codec's clock; turning the voice off when the pipe ran empty or the driver stopped the DMA dropped what the mixer still held, so every sound lost its last 50 ms. The voice stays on for 200 ms after playback stops | ours | — |
| `0033-tests-qtest-test-CS4231-playback-through-the-APC-DMA` | qtest `sun4m-cs4231-test` for 0028-0032: two u-law buffers behind IOMMU mappings, PEN, PI/PD/PM/PMI at SBus level 5 (processor level 9) in real time, every sample decoded in a `wav` audiodev; DMA off and the reset bit | ours | not in QEMU |
| `0034-hw-sparc64-sun4u-take-the-IDPROM-MAC-address-from-a-` | sun4u wrote QEMU's default MAC `52:54:00:12:34:56` into the IDPROM unless the NIC was the onboard `-nic`; a NIC added with `-device` (as qemu-server adds `sunhme`) didn't exist yet. OpenBIOS gives the guest that address as the system MAC and NetBSD and Solaris use it for `hme0` (NetBSD's `wm` too), so every guest had the same MAC and host id whatever `net0` said. Without an onboard NIC the IDPROM is now written again when the machine is complete: from the first `sunhme`, else the first NIC of any model ("The sun4u system MAC") | ours (in review) | not fixed; see `upstream/qemu-sun4u-idprom-mac.md` |
| `0035-tests-qtest-test-the-IDPROM-MAC-address-on-sun4u` | qtest `sun4u-idprom-test` for 0034: reads the IDPROM from the NVRAM; default address without a NIC, a `-device sunhme`'s address, the first `sunhme` after a `virtio-net-pci`, the first NIC without a `sunhme`, the onboard `-net nic` ahead of a `-device sunhme` | ours (in review) | not in QEMU |
| `0036-target-sparc-write-softint-under-the-BQL` | The guest's `%set_softint`, `%clear_softint` and `%softint` writes read, modified and wrote `env->softint` in the vCPU thread without the BQL, while the tick, stick and hstick timers set their bits from the main loop holding it: a tick that fired in between was written over. illumos arms its next clock tick only after handling the last one, so Tribblix lost its clock for good in about one of three long runs. The three helpers now hold the BQL for the read-modify-write ("Tribblix on sun4u") | ours (in review) | not fixed; see `upstream/qemu-sparc64-softint-race.md` |
| `0037-tests-qtest-test-that-a-tick-during-a-softint-write-` | qtest `sun4u-softint-test` for 0036: a boot PROM sets and clears soft interrupt 1 in a loop with interrupts off while 10 us ticks fire, and counts the ticks it sees and loses; passes after 20000 ticks with none lost | ours (in review) | not in QEMU |
| `0038-esp-don-t-count-the-message-out-bytes-as-part-of-the` | `esp_cdb_ready()` counted the IDENTIFY and other message out bytes in the command FIFO as CDB bytes. Linux 2.6.18's `esp` driver (Debian 4.0 on SS-5) selects with ATN and Stop, sends a 5-byte SDTR message and then the CDB one byte per Transfer Information: its first CDB byte alone made a "complete" 6-byte command, the target answered ILLEGAL REQUEST and Linux reset the bus and took the disk and CD-ROM offline. Only the bytes after the messages count now | ours (in review) | not fixed; see `upstream/qemu-esp-cdb-ready-after-message-out.md` |
| `0039-tests-qtest-test-a-CDB-sent-byte-by-byte-after-a-mes` | qtest `sun4m-esp-test` for 0038: Select with ATN and Stop, an SDTR message and TEST UNIT READY byte by byte on the SS-5's ESP without DMA; the command phase lasts until the sixth byte, the command gets GOOD (after the reset's unit attention) | ours (in review) | not in QEMU |
| `0040-esp-let-the-interrupt-come-late-as-from-a-real-targe` | The ESP finishes a command in the register write that started it and raised its interrupt in the same instruction. NeXTSTEP 3.3 and OPENSTEP 4.2 then saw the command end while the issuing thread held their SCSI driver's lock, ran the completion at PIL 4 and spun on that lock for good: every install hung on the disk. `sysbus-esp` gets `irq-latency-us`, 0 (off) on every machine: set, the interrupt, `STAT_INT` and the line together, comes from a timer that long after the event; the interrupt register and the bus phase are set at once (OpenBIOS polls the interrupt register); reading it, the chip's reset command and a device reset cancel a pending interrupt, and migration carries it (subsection `esp/irq_pending`). Per VM through qemu-server's `machine: SS-5,esp-irq-latency=500` ("qemu-server"). At 500 every ESP interrupt comes 0.5 ms later, about 2 ms per disk command, so it stays off unless a guest needs it ("NeXTSTEP 3.3 and OPENSTEP 4.2") | ours | not fixed; see `upstream/qemu-esp-irq-latency.md` (#2620, #2674) |
| `0041-tests-qtest-test-the-ESP-interrupt-latency-on-sun4m` | qtest `sun4m-esp-test` for 0040, four more cases on the SS-5 (the line read through the ESP DMA's `DMA_INTR`): by default the interrupt comes at once; with `-global sysbus-esp.irq-latency-us=500`, after Select with ATN and Stop neither `STAT_INT` nor the line shows for 500 us, both do then; the interrupt register has its bits at once, and reading it, the chip's reset command and a system reset cancel the interrupt | ours | not in QEMU |
| `0042-target-sparc-halt-the-CPU-in-the-idle-loop-of-sun4u-` | Every sun4u guest spun in its idle loop and kept a host core at 100% for as long as the VM ran: no kernel that runs on QEMU's sun4u can stop an UltraSPARC-IIi (Solaris and illumos halt only through the SPARC64-VI module, NetBSD and Linux only through the sun4v hypervisor, OpenBSD's `sleep` is patched in only on CPUs with several strands). The translator recognises the call in the idle loop of NetBSD 9 and 11 (`cpu_idle()`), OpenBSD (`cpu_idle_cycle()`) and Solaris 9, 10 and illumos (`idle_cpu`, as Sun's compiler and as gcc lay it out) by the words around it, and halts the CPU there while the word that says there is work (`ci_want_resched`, `spc_whichqs`, `disp_nrunnable`) is 0, interrupts are enabled at level 0 and nothing is pending; the next interrupt wakes it ("sparc64 (sun4u)", "Idle"). `-trace sparc64_idle_match` shows the match | ours, after LEMU's SunOS idle (0012) | not in QEMU |
| `0043-hw-sparc64-sun4u-add-the-idle-halt-option-on-by-defa` | `-M sun4u,idle-halt=on\|off` for 0042, on by default (sun4u has one CPU); not on `sun4v` | ours | not in QEMU |
| `0044-tests-qtest-test-the-idle-halt-on-sun4u` | qtest `sun4u-idle-test` for 0042-0043: a boot PROM with each recognised loop layout (NetBSD, OpenBSD, Solaris 10, Tribblix) must stop counting when idle, and keep counting with `idle-halt=off`, with work, with interrupts disabled and at PIL 15; with a 1 ms tick each tick must wake it, run its handler, and the loop must run far fewer rounds than with `idle-halt=off` | ours | not in QEMU |
| `0045-hw-pci-host-sabre-keep-PCI-interrupts-to-one-request` | The sabre keeps one interrupt request to the CPU at a time and makes the next when the guest clears the current one; an OBIO interrupt waited for that, a PCI interrupt replaced the outstanding request. The CPU drops a vector sent while it is busy, so a PCI interrupt arriving between the first request and the guest's acknowledge was lost, the guest's clear of the first request was ignored (no longer `irq_request`), and every OBIO interrupt (IDE, serial console) stayed blocked: OpenBSD 8.0's `wd0: timeout`, then a guest that takes no interrupt, with the NIC on pciB ("sparc64 (sun4u)", "IDE timeouts without ntpd") | ours | not fixed; see `upstream/qemu-sabre-pci-interrupt-replaces-request.md` |
| `0046-tests-qtest-test-the-sabre-s-interrupt-requests-on-s` | qtest `sun4u-sabre-irq-test` for 0045: the sabre's lines driven from the test, its requests intercepted; a PCI interrupt raised while the IDE request or another PCI request is outstanding waits until the guest clears it, and the serial console's interrupt gets through after both; fails without 0045 | ours | not in QEMU |
| `0047-target-sparc-keep-fetching-from-the-current-page-acr` | Solaris 2.1 stopped QEMU after its device configuration: `Trap 0x21 (Instruction Access Error) while interrupts disabled` at `pc f0014768` (`srmmu_mmu_flushctx`). Its kernel switches, with traps disabled, to a context whose level 1 table it hasn't filled yet, flushes it and switches back, all in one page of kernel text; QEMU's TLB flush on the context write made the next fetch walk the new context and fail. A context register change now keeps the old context's translation of the writing instruction's page, and an instruction fetch in that page that fails with traps disabled uses it (execute only); trace event `sparc_mmu_ifetch_hold` ("Older Sun releases on sun4m") | ours | not fixed; see `upstream/qemu-sparc32-context-switch-ifetch.md` |
| `0048-tests-qtest-test-an-instruction-fetch-across-a-conte` | qtest `sun4m-mmu-ctx-ifetch-test` for 0047: a boot PROM switches with traps disabled to a context that maps other RAM and not the PROM, stores, flushes the context, stores and switches back; both stores must land in that context's RAM and the PROM must reach its end (SS-10, SS-5). With traps enabled the first fetch there must take an instruction access exception. The traps-off cases fail without 0047 (QEMU stops with the same `Trap 0x21`), also on plain QEMU 11.1.3 | ours | not in QEMU |
| `0049-target-sparc-take-a-bus-error-on-a-SuperSPARC-load-o` | SunOS 4.1.3 panicked on the SS-10 after `SUNW,fdtwo0` (`BAD TRAP: cpu=0 type=29`): its generic sun4m kernel probes for VME controllers with its fault catcher armed and reads physical `0xd.0108_0000`, where an SS-10 has nothing, and 4.1.3's `trap()` sends only trap 0x09 (data access exception) to the catcher. QEMU raised trap 0x29 (data access error) for a bus error on every sparc32 CPU; the SuperSPARC takes a bus error on a load as trap 0x09 and on an instruction fetch as trap 0x01, with FT=5 (access bus error) in the SFSR. New CPU feature `buserr-access-exc`, on the `TI-SuperSparc-*` models only (SS-10, SS-20, SS-600MP): loads and fetches take 0x09/0x01, the SFSR and SFAR as before. Stores, the MMU bypass ASIs 0x20-0x2f, the MXCC stream registers and unimplemented ASIs keep 0x29; microSPARC, TurboSPARC and LEON are unchanged; `-cpu TI-SuperSparc-II,-buserr-access-exc` turns it off; trace event `sparc_bus_error_access_exc` ("Older Sun releases on sun4m") | ours | not fixed; see `upstream/qemu-sparc32-supersparc-bus-error-trap.md` |
| `0050-tests-qtest-test-the-trap-a-bus-error-takes-on-sun4m` | qtest `sun4m-bus-error-trap-test` for 0049: a boot PROM maps an unassigned physical region, enables traps and makes one access there; a handler in RAM stores the trap type, SFSR and SFAR. SS-10: a load takes 0x09, a fetch 0x01; a store, an ASI 0x20 and an ASI 0x2d load and a load with the feature off take 0x29. SS-5: load, store and ASI 0x20 load 0x29, fetch 0x21. FT=5 in every case, the address in the SFAR for data accesses. Without 0049 (and on plain QEMU 11.1.3) the two SS-10 load and fetch cases fail | ours | not in QEMU |
| `0053-target-sparc-defer-the-fp_exception-of-an-IEEE-754-e` | The SPARCstation LX's own PROM (`lx.bin`) stopped in its POST at `FPU SP Trap Priority <  Test` (`Unexpected Synchronous Trap Taken, Trap Type = 00000008`, then `qemu: fatal: Trap 0x03`): it divides by zero with all IEEE traps enabled, follows that with a misaligned FP store and expects trap 7 on the store, then trap 8 on a later FP instruction with the `fdivs` in the FQ. QEMU raised trap 8 on the `fdivs` itself ("we do not model the fp_exception_pending state"). The sparc32 FPUs defer it (V8 manual 7.3 and appendix L, the microSPARC-I and -IIep manuals, the SuperSPARC documentation): an FPop with an IEEE exception enabled in TEM now writes no result, goes into the FQ and enters fp_exception_pending; the next FPop, FBfcc, FP load or FP store (STFSR and STDFQ too) takes trap 8, with its own pc, qne 1 and the FPop in the FQ. A misaligned FP load or store takes trap 7 first and the exception stays pending (alignment as in V8: 8 bytes for LDDF/STDF/STDFQ). All sparc32 CPU models, system emulation only (linux-user and sparc64 unchanged); unimplemented_FPop and sequence_error as before; migrated in subsection `cpu/fp_pending` | ours | not fixed; see `upstream/qemu-sparc32-deferred-fp-exception.md` |
| `0054-tests-qtest-test-the-deferred-fp_exception-trap-on-s` | qtest `sun4m-fp-deferred-trap-test` for 0053: a boot PROM runs `fdivs` 1/0 with TEM set, two integer instructions and the FP instruction under test; the handler stores the trap type, `%l1`/`%l2`, the FSR, drains the FQ with STDFQ and stores `%f3`. An FPop (`fadds`, `fmovs`), an aligned `st`/`ld` of an FP register, STFSR and FBfcc take trap 8 there (ftt IEEE, cexc dz, qne 1, the FQ entry the `fdivs`, `%f3` unchanged, qne 0 after STDFQ); a misaligned `st`, `ld` and a 4-byte aligned `std` take trap 7, the STFSR after them trap 8; no exception, masked traps and a misaligned store with nothing pending as before. SS-5, SS-10 and LX, 36 cases; on plain QEMU 11.1.3 the 27 trap cases fail | ours | not in QEMU |
| `0055-hw-sparc-sun4m-take-at-most-128-MB-of-RAM-on-the-mic` | `-M LX`, `SPARCClassic` and `SPARCbook` (microSPARC-I) took `-m 256`, and OpenBIOS then stopped with `Trap 0x21`: the microSPARC-I's context table pointer holds physical bits 26:8 only (QEMU's mask is right), and its memory interface takes 128 MB (TMS390S10 reference guide: 27 address bits, four banks of 32 MB). New hwdef field `max_ram` (128 MB on those three; the 256 MB memory space and the empty slot above RAM unchanged): more is refused with "Too much memory for this machine" | ours | not reported; see `upstream/qemu-sparc32-deferred-fp-exception.md` ("Also") |
| `0056-hw-sparc-sun4m-map-the-SPARCstation-LX-s-on-board-SB` | The SPARCstation LX has a cgsix (GX) in SBus slot 3, the DBRI in slot 2 and a parallel port (bpp) in slot 4 on the board, and its PROM (`lx.bin`) carries their FCode and probes them on every boot. `-M LX` had none: the PROM took a data access error in the cgsix probe (THC, slot 3 offset `0x301094`) and stopped at `ok` without its banner, then another one resetting the DBRI (slot 2 offset `0x10000`); NetBSD 9.3 panicked in `bppattach()` (DMA CSR at `0x7c800000`). Unimplemented devices for the three on `-M LX`, as the SS-20 has its DBRI and bpp: the DBRI at `0x50000000` (the SS-20's layout), the bpp at `0x7c800000`, and a new hwdef field `cg6_base` for the cgsix's 16 MB at `0x60000000`; read 0, writes ignored, at the low priority of unimplemented devices (the TCX or cg3 that `-vga` puts in slot 2 keeps its addresses); the other machines unchanged | ours | not reported; see `upstream/qemu-sun4m-lx-onboard-sbus.md` |
| `0057-hw-sparc-sun4m-give-the-DBRI-an-FCode-PROM-that-make` | The DBRI's own FCode PROM, at offset `0x1000` of its slot, which the LX, SS-10 and SS-20 PROMs load, read 0, so they made its node without a `name` or `reg`: SunOS 4.1.4 on the LX panicked in its autoconfiguration (`BAD TRAP: cpu=0 type=9 ... kernel read fault at addr=0x0`), as did Solaris 2.1/2.2 on the SS-20 PROM ("Older Sun releases on sun4m"); with a name only, SunOS 4.1.4's GENERIC kernel still panicked in its `dbri` driver. The window (0x40 bytes, below a frame buffer in the same slot) now holds a small FCode program of ours that makes the node a DBRI has: `name` `SUNW,DBRIe`, `reg` at slot offset `0x10000` (the register stub) and its interrupt at SBus level 5 (`intr` 0x39). The drivers find no codec behind the stub and go without sound (SunOS 4.1.4 `dbri: DBRI Reg8 bad!`, Solaris 2.6 `WARNING: dbri: DBRI Reg8 bad!`, NetBSD 9.3 `dbri0: no codec detected, aborting`) | ours | not reported; see `upstream/qemu-sun4m-ss20-dbri-unnamed-node.md` |
| `0058-tests-qtest-test-the-on-board-SBus-devices-of-sun4m` | qtest `sun4m-onboard-sbus-test` for 0056-0057: the LX's cgsix, DBRI and bpp regions at their addresses and priority with the default TCX's ROM above them, none on the SS-5, and the DBRI's FCode (header, checksum, length, program, zeros after it, big-endian wide reads) on the LX and the SS-20 | ours | not in QEMU |
| `0059-hw-rtc-m48t59-keep-the-NVRAM-in-a-drive-and-leave-it` | QEMU wrote OpenBIOS's NVRAM layout into the sun4m M48T08 at every start and kept nothing across runs, so the Sun PROMs (SS-5, SS-20, LX) found their checksum wrong, set `diag-switch?` and stopped at `ok` on every power-on. A `drive` property for the sysbus M48Txx's NVRAM bytes (written through per byte, clock registers left out); on sun4m a blank image gets QEMU's contents once, any other image is left alone except the IDPROM (from `-M` and the MAC) and, with `-prom-env`, OpenBIOS's partitions; the M48T08 at `/machine/nvram` ("The NVRAM kept in a volume") | ours | not in QEMU |
| `0060-tests-qtest-test-the-sun4m-NVRAM-kept-in-a-drive` | qtest `sun4m-nvram-test` for 0059: no image, a blank image, persistence across two runs (guest writes stored, clock registers not, the IDPROM following the MAC), `-prom-env`, a larger image, `-blockdev` and `query-block`'s path, a read-only image | ours | not in QEMU |
| `0061-hw-dma-sparc32_dma-reset-the-lance-DMA-s-base-addres` | The lance has 24-bit addresses; the ledma adds the upper 8 bits of the DVMA address from its fourth register (`E_BASE_ADDR`, "defaults to 0xff" in the DMA2 description the file cites), which QEMU reset to 0. Solaris 2.6's `le` driver never writes it, and the SS-20 PROM sets it only when it probes with `diag-switch?` true, so when the PROM booted by itself (`diag-switch?` false) the lance asked for `0x0040f000` instead of `0xff40f000`, the IOMMU (64 MB range) faulted at level 15, and the kernel recursed into its level-15 handler until QEMU stopped (`Trap 0x29`). Reset value `0xff000000` for the ledma only ("SS-20 PROM: auto-boot and the lance DMA") | ours | not in QEMU |
| `0062-tests-qtest-test-the-lance-DMA-s-base-address-regist` | qtest `sun4m-ledma-test` for 0061: the register after start and `system_reset` (SS-5, SS-20, LX), the ESP channel's stays 0, and the lance's init block read through a 64 MB IOMMU from `0xff400000` (an IOMMU error at `0x00400000` with the register at 0); fails without 0061 | ours | not in QEMU |
| `0063-hw-sparc-sun4m-map-the-SPARCserver-600MP-s-VMEbus-in` | SunOS 4.1.2 on `-M SS-600MP` stopped before its banner (`Unhandled Exception 0x00000029`, `pc f80a6054`): its early setup for the 600MP reads and writes the VMEbus interface registers at physical `0xf.df01_0000` (offsets 0, 4 and 8: control, AFSR, AFAR) through the MMU bypass ASI 0x2f, where QEMU had nothing (a bypass load keeps trap 0x29 with 0049). An unimplemented device over that page (reads 0, writes ignored), on the SS-600MP only; no VMEbus model, so the VME spaces stay empty and the kernel's VME probes find nothing ("Older Sun releases on sun4m") | ours | not reported; see `upstream/qemu-sun4m-ss600mp-vme-lebuffer.md` |
| `0064-hw-sparc-sun4m-give-the-SPARCserver-600MP-s-lance-it` | The 600MP's lance works in a buffer memory of its own, the `lebuffer` at SBus slot f offset `0x40000` (128 KB, up to the lance at `0x60000`), not through a DMA engine; QEMU gave the machine the SS-10's `ledma` and DVMA, and SunOS 4.1.2 knows only the lebuffer (a lance directly on the SBus it refuses: `le0: not used - unsupported SBus card for this architecture!`). A `lebuffer-size` property on the sparc32 DMA device: the lance's addresses (modulo the size) go to a RAM region in an address space of its own, which the board maps through an alias at `0xe.f004_0000`, and its interrupt goes straight to the board, past the ledma's interrupt enable; set on the SS-600MP only (with openbios 0028's `lebuffer` node) | ours | not reported; see `upstream/qemu-sun4m-ss600mp-vme-lebuffer.md` |
| `0065-tests-qtest-test-the-SPARCserver-600MP-s-VMEbus-regi` | qtest `sun4m-ss600mp-test` for 0063-0064: the VME registers' unimplemented device (reads 0), the lebuffer's RAM and address space, the lance initialized from an init block in it (station address), sending from a descriptor there, handing it back and interrupting without the ledma's enable; the SS-10 unchanged | ours | not in QEMU |
| `0066-hw-sparc-sun4m-give-the-DBRI-registers-that-take-its` | The DBRI's registers (slot offset `0x10000` on the SS-20 and the LX) were an unimplemented device that reads 0. A reconfiguration boot of Solaris 2.6 under the SS-20 or SS-10 PROM panicked in `dbri` (`WARNING: dbri: DBRI Reg8 bad!`, `BAD TRAP: type=9 ... addr=0`): the driver's first command found REG8, the command queue pointer, outside its queue, and its chip error routine walked all 14 pipes, of which the 12 ISDN ones are never set up when the node has `isdn-disabled`, which the SS-20 and SS-10 PROMs give it and the LX PROM doesn't. A model of the registers, new file `hw/sparc/sun4m_dbri.c` (`sun-DBRI`): they keep what is written, REG0's soft reset clears them, writing REG8 or REG0's P bit walks the command queue through the IOMMU (each command by its length, JUMP followed) to a WAIT and leaves REG8 on it; no data, no interrupt, the PIO pins in REG2 read low, so the drivers find no codec ("The `dbri` panic on reconfiguration boots under the SS-20 PROM") | ours | not in QEMU |
| `0067-tests-qtest-test-the-DBRI-s-registers-and-command-qu` | qtest `sun4m-dbri-test` for 0066 on the SS-20 and the LX: the registers after start, kept values, soft reset, PIO pins low; a queue of one-, two- and three-word commands with a JUMP to another page read through the IOMMU leaves REG8 on its WAIT, the P bit goes on from there (or stays when nothing was added) and doesn't stay set, a queue on an unmapped page leaves REG8 as written; fails against the 0001-0062 build | ours | not in QEMU |
| `0068-hw-pci-host-sabre-reset-the-PCI-control-status-regis` | `sabre_reset()` left the PCI control/status registers (`0x2000`-`0x202f`) as the guest last wrote them; Solaris writes its error bits back there, and after a reset (its reboot, OpenBIOS 0030) every boot warned `pcipsy0: SERR asserted on pci bus`. They are cleared on reset, as at power-on ("The firmware reboot on sun4u") | ours | not in QEMU |
| `0069-tests-qtest-test-the-sabre-s-PCI-control-registers-a` | qtest `sun4u-sabre-reset-test` for 0068 | ours | not in QEMU |
| `0070-target-sparc-halt-the-CPU-in-Linux-s-idle-loop-on-su` | Linux on sun4u spun in its idle loop at 100% of a host core: `arch_cpu_idle()` only touches the NMI watchdog there (it yields to the hypervisor on sun4v), and no kernel option changes that. The translator recognises `arch_cpu_idle()` at its call of `arch_touch_nmi_watchdog()` by the `tlb_type` test next to it and the start of the sun4v branch, as gcc lays it out either way round (Linux 6.1 and 7.3: `be` to the sun4v branch; 6.17 and 7.0: `bne` around it), and halts the CPU there at `%pil` 14 (interrupts disabled, as the idle loop calls it), with nothing pending and `TIF_NEED_RESCHED` clear; the tick, stick and interrupt vector wake it whatever `%pil`, and the interrupt is taken when the loop enables interrupts. The window around a call grows to 24 words before it; words on another page read as 0 ("sparc64 (sun4u)", "Idle") | ours, after LEMU's SunOS idle (0012) | not in QEMU |
| `0071-target-sparc-recognise-the-idle-loop-of-Solaris-7-an` | Solaris 7 and 8 spun in `idle()` on sun4u: Sun's older compiler lays the loop out the other way round from 9 and 10 (`be` to the call through `idle_cpu`, `swtch()` first). The translator recognises that layout too and halts at the call as for Solaris 9 and 10 (`-trace sparc64_idle_match`: `Solaris 7/8`) | ours, after LEMU's SunOS idle (0012) | not in QEMU |
| `0072-tests-qtest-test-the-Linux-and-Solaris-7-8-idle-loop` | qtest `sun4u-idle-test` for 0070-0071: the Solaris 7/8 layout with the cases of the others, and Linux 7.3, 6.1 and 7.0's `arch_cpu_idle()` in a loop that disables interrupts to level 14 round it: it must halt there, not with `TIF_NEED_RESCHED` set, without `PSTATE.IE`, at level 0 or 15, and a 1 ms tick must wake it at level 14 and be taken when the loop enables interrupts; 51 cases | ours | not in QEMU |
| `0114-target-sparc-halt-the-CPU-in-FreeBSD-s-idle-loop-on-` | FreeBSD 12.4 on sun4u spun in its idle loop at 100% of a host core: ULE's `sched_idletd()` calls `cpu_idle()`, which is empty on sparc64. The translator recognises the call by the `tdq_cpu_idle` stores and the `tdq_load` test round it and halts there; FreeBSD's kernel runs at TL 1, so it is halted at TL 1 (the others still only at TL 0), and without the 100 us poll, which its loop (a steal attempt and its own `sched_idlespins` between calls) never ended: halted at the first call, one round of the loop after each wake (`SPARC64_IDLE_TL1`, `SPARC64_IDLE_NO_POLL`). Idle at the shell 8.7% instead of 105-107% ("FreeBSD 12.4 on sun4u") | ours, after LEMU's SunOS idle (0012) | not in QEMU |
| `0115-tests-qtest-test-the-FreeBSD-idle-loop-on-sun4u` | qtest `sun4u-idle-test` for 0114: the FreeBSD layout at TL 1 with the cases of the others, a TL>0 trap table for the tick there, and a `tl-up` case for every layout (one trap level above where its kernel idles: no halt); 70 cases with 0111's Linux 3.2 | ours | not in QEMU |
| `0120-target-sparc-keep-SuperSPARC-instruction-fetches-in-` | Sun's SS-600MP boot PROM stopped QEMU within seconds (`Trap 0x01 (Instruction Access Fault) while interrupts disabled`): its MMU register test, run from the PROM in boot mode with traps disabled, sets the MMU enable bit, and QEMU translated the next instruction fetch. On the SuperSPARC the boot mode bit (bit 13 of the MMU control register) sends every instruction fetch to the PROM whether the MMU is on or not, and data accesses are translated. New CPU feature `boot-mode-ifetch`, on the `TI-SuperSparc-*` models only: an instruction fetch in boot mode uses the physical MMU index, which maps it to the PROM as with the MMU off; `-cpu TI-SuperSparc-II,-boot-mode-ifetch` turns it off. OpenBIOS clears boot mode when it turns the MMU on, so it isn't affected. The PROM then loops in its later tests ("Older Sun releases on sun4m", "Sun's own SS-600MP boot PROM") | ours | not reported |
| `0121-tests-qtest-test-SuperSPARC-boot-mode-with-the-MMU-o` | qtest `sun4m-boot-mode-ifetch-test` for 0120: a PROM turns the MMU on with traps disabled while context 0 maps virtual 0 to RAM holding other code; the next fetch must come from the PROM in boot mode on SS-10, SS-20 (`TI-SuperSparc-50`) and SS-600MP, and from RAM with boot mode cleared, with `-boot-mode-ifetch` and on SS-5. `sun4m-mmu-ctx-ifetch-test` and `sun4m-bus-error-trap-test` now write the MMU enable bit alone (clearing boot mode, as OpenBIOS and an OS do) | ours | not in QEMU |
| `0122-hw-audio-cs4231-raise-pi-and-pmi-when-the-codec-gets` | SunOS 4.1.4 hung in AUDIO_DRAIN after short sounds (SimCity for HyperLook, then OpenWindows: `xnews: Warning: input queue lock broken!`): the APC set PI and PMI together when it took the samples, up to 50 ms ahead of the codec; `audio_4231_cintr` checks PMI first and lost it. PI now comes when the codec reaches the buffer and PMI when it has played the last one (from a timer, after an enabled PI is cleared, and not when a next buffer was loaded); PD shows with the PI; a buffer loaded while the codec still plays the one before is taken at once. A new vmstate subsection `cs4231/irqs` carries a PI or PMI still due and is sent only then, so older streams load | ours, on LEMU's CS4231 (0028); from [hwinther/lemu `ff412bc835`](https://github.com/hwinther/lemu/commit/ff412bc835386f6a30ff4492886e934a54c0f9b0) | not in QEMU |
| `0123-tests-qtest-test-the-cs4231-s-pi-and-pmi-for-a-short` | `sun4m-cs4231-test` for 0122: `short-buffer`, `short-tail`, `load-on-pd`, `short-chain` and `migrate` cases (7 in all), and `playback` expects the second PI and the PMI when the codec has played the buffer. Applies with line offsets of -1 (our 0030 changes the test's header). `migrate` waits for the destination with `query-status` until `running` (`wait_running()`, 10 s at most): on 11.1.3 the destination resumes after `-incoming` before the test's QMP client has negotiated, so the RESUME event was lost and the case hung; LEMU took the same change into its commit | ours, from [hwinther/lemu `c92620599a`](https://github.com/hwinther/lemu/commit/c92620599a8b19e90b671e47f1b04a3a2646c22d) | not in QEMU |
| `0124-hw-audio-cs4231-set-the-codec-s-int-and-pi-with-the-` | Linux's `snd_cs4231_sbus_interrupt()` returns `IRQ_NONE` unless INT (bit 0 of the codec status register, offset 8) is set, before it reads and clears the APC CSR; the model kept that register at 0, so with openbios 0034 the APC interrupt was never cleared and QEMU stopped (`Trap 0x02 (Illegal Instruction) while interrupts disabled`). INT and PI in I24 are now set where `cs_play_irqs()` raises the APC's PI and PMI: they follow the APC interrupt, not the codec's own counter (I14/I15, IEN in I10), which isn't modelled. A write to I24 clears the bits written as 0 and INT when none of PI/CI/TI is left; a write to the status register clears INT. The interrupt line still follows the APC CSR alone (SunOS and Solaris never clear INT). No vmstate change: the bits are in `regs` and `dregs`. Written to the LEMU maintainer's requirements ("Audio", "Linux") | ours, on LEMU's CS4231 (0028, 0122); LEMU took it unchanged (local `9fbdd5b68a`, not pushed) | not in QEMU (LEMU-origin code, not proposed) |
| `0125-tests-qtest-test-the-cs4231-s-int-status-bit-and-i24` | `sun4m-cs4231-test` case `codec-int` for 0124 (8 cases in all): INT and I24's PI clear before playback, set at the APC's PI; clearing the APC's PI alone drops the line and leaves INT; writing I24 with PI kept leaves both, writing 0 clears both; PMI sets them again, a status write clears INT while the line stays up until PMI is cleared. Fails without 0124 (`'codec_int(qts)' should be TRUE`) | ours, on LEMU's CS4231; LEMU took it unchanged (local `0e81145602`, not pushed) | not in QEMU |
| `0126-hw-audio-cs4231-clear-i24-s-pi-ci-and-ti-on-a-status` | 0124's write to the status register cleared INT only, so I24 still read PI after it. The CS4231 datasheet, and QEMU's ISA model (`cs4231a.c`, `case Status`), clear PI, CI and TI in I24 as well; now so does this model. The interrupt line still follows the APC CSR alone. No vmstate change. Asked for in the LEMU maintainer's review of 0124 | ours, on LEMU's CS4231 (0028, 0124); offered to LEMU, not taken yet | not in QEMU (LEMU-origin code, not proposed) |
| `0127-tests-qtest-test-that-a-cs4231-status-write-clears-i` | `codec-int` reads I24 after the status write at PMI: PI, CI and TI clear. Fails without 0126 (`codec_read(qts, CS_IRQSTAT) & CS_IRQ_ALL == 0`: `0x10 == 0`) | ours, on LEMU's CS4231; offered to LEMU, not taken yet | not in QEMU |
| `0128-hw-audio-cs4231-drop-what-the-apc-took-past-the-code` | The APC takes up to 50 ms ahead of the codec's clock and the model wrote those samples into the audiodev at once, so 0032's play-out after a stop played all of them. Linux stops in the middle of a buffer (when its last period has played it zeroes the counts and turns the DMA off), with the APC up to 50 ms into the next period of its ring: ~150 frames of old samples followed the tone ("Audio", "Linux"). With a `wav` audiodev most of them were in the file before the stop, so they cannot be taken back in the audiodev. What the APC takes now waits in a FIFO in the model (16 KB, converted) and goes to the audiodev when the codec clock gets to it; the take-ahead itself (address, count, PI, PD, PM, PMI) is unchanged. A driver stop of the DMA (PDMA_GO cleared, or the count zeroed while playing) drops what lies past the codec's position; the end of the pipe (PMI) still plays everything, as 0032. A pause or PEN off drops nothing: SunOS 4.1.4 pauses and turns PEN off as soon as the APC shows the pipe empty, up to 50 ms before the codec has played the last buffer (dropping there cut its trailing 5 ms sound after 3 ms). The playback address and count now read as the codec's position (what the APC took from the current buffer past the codec is subtracted from the address, added to the count): Linux finishes a drain when its position, read from the address, passes the end of its data, and read 50 ms ahead it sometimes stopped at its last period's interrupt, so the drop cut 22 ms of the tone. A vmstate subsection `cs4231/fifo` (the FIFO, the codec's end and what was taken from the current buffer) is sent only while the FIFO holds samples, so older streams load; without it a migration 20 ms into a 100 ms buffer read the address 560 bytes further on, PMI came 10 ms after it instead of 80, and 400 of 640 frames were lost (before 0128 the same migration lost 187 frames and PMI came 43 ms early) | ours, on LEMU's CS4231 (0028, 0032); offered to LEMU, not taken yet | not in QEMU (LEMU-origin code, not proposed) |
| `0129-tests-qtest-test-cs4231-stops-and-migration-with-sam` | `sun4m-cs4231-test` cases `mid-stop` and `migrate-fifo` (10 cases in all). `migrate-fifo` migrates 20 ms into a 100 ms buffer with samples taken ahead: the address and count read the codec's position on both sides, PMI comes 75-90 ms later (80) and the destination's `wav` audiodev gets the other 80 ms (640 frames); the qtest clock starts at 0 in each process, so the destination's is stepped to the source's. `mid-stop`: one 100 ms buffer into a `wav` audiodev, stopped 40 ms after its PI as Linux stops (next count and address, count and address to 0, then the CSR without `PDMA_GO`); the file must hold 320 frames (+-16) and nothing past them. `playback` still checks that a stop at PMI plays every sample. Fails without 0128 (720 frames) | ours, on LEMU's CS4231; offered to LEMU, not taken yet | not in QEMU |
| `0133-hw-sparc64-migrate-the-sabre-the-IOMMU-the-ebus-and-` | Nothing in sun4u's interrupt path was in the migration stream: the sabre had no VMState of its own (only the generic PCI host bridge's, with none of its registers), nor had the sun4u IOMMU, the ebus or the sabre's PCI function, and the sparc64 CPU's section leaves out SOFTINT and the interrupt vector. After a migration, a `loadvm` (which resets the machine first) or a `-loadvm`/`-incoming` in a new QEMU the guest ran but took no interrupt from the on-board devices: the interrupt mapping registers came back disabled, the outstanding request was forgotten and the serial console never answered (wisp, Debian 7); the IOMMU came back off (a disk's DMA to the DVMA address taken as physical) and the ebus's BAR0 unmapped. Now the sabre migrates its interrupt mapping registers, the lines that are up, the outstanding request, the PCI control registers and the reset status; the IOMMU its registers; the ebus and the sabre's PCI function their PCI configuration space; the CPU, in subsection `cpu/sparc64_irq` (sent when one is set), SOFTINT, `ivec_status`/`ivec_data` and 0042's `idle_halted`. sun4u has no versioned machine types: streams from older packages no longer load (`Unknown section or instance 'PCIHost'`; they resumed without interrupts anyway), and newer streams don't load into older QEMUs. Began as the browser build's `web/patches/sun4u-migration-state.patch` (sabre and CPU), now taken from the series ("Snapshots and migration on sun4u") | ours | not in QEMU |
| `0134-tests-qtest-test-the-sabre-s-the-IOMMU-s-and-the-ebu` | qtest `sun4u-migration-test` for 0133, the machine saved to a file and loaded with `-incoming` into a new QEMU: `sabre` (enabled IMRs and a PCI control register read as on the source; with an IDE request outstanding and the NIC's waiting behind it, clearing the IDE request brings the NIC's), `iommu` (control and TSB base), `pci-config` (the ebus's BAR0, command register and interrupt line, the sabre function's interrupt line); each fails without 0133. The CPU subsection isn't covered (the qtest accelerator runs no guest code) | ours | not in QEMU |
| `0135-hw-net-sunhme-stop-the-receiver-on-a-reset-until-the` | A write of the ETX and ERX bits to the sunhme's global reset register only cleared the bits again: the receiver kept taking frames into the old ring and the pending status kept the line up. Linux resets both when it takes the interface down, then frees the ring's buffers and its interrupt; a frame arriving after that (50 ms to 6 s after the reset in the traces) still went into the released ring and raised an interrupt nobody handled, the sabre waited for its clear and held back every other interrupt: Debian 13 lost its IDE interrupts at power-off (`READ DMA` timeouts with the drive `DRDY`), or panicked in `happy_meal_interrupt` when the interface came up again. An ERX reset now clears the receiver's DMA enable (ERX configuration bit 0, which the drivers set with the ring), no frame is taken while it is clear, and each reset drops its engine's status bits and updates the line ("sparc64 (sun4u)", "The lost IDE interrupt at Debian 13's power-off") | ours | not fixed |
| `0136-tests-qtest-test-the-sunhme-s-receiver-after-a-reset` | qtest `sun4u-sunhme-reset-test` for 0135: a sunhme in slot 0 of pciB set up as the firmware and a driver would (bridge window, BAR, a 32-entry ring in RAM), frames from a socket netdev, the sabre's request for ino 0x10 intercepted; `rx`, `no-rx-after-reset` (a frame after a global reset raises nothing and leaves the ring alone, with DMA enabled again the next goes into descriptor 1) and `reset-drops-status`. The last two fail without 0135 | ours | not in QEMU |
| `0137-hw-pci-host-sabre-drop-a-slot-s-request-when-the-gue` | A PCI interrupt-map register written without the valid bit dropped the outstanding request only when the request's ino equalled the slot number (0-7), not when it was one of the slot's four inos: a request of ino 0x10 (the NIC on pciB) stayed when slot 4 was disabled, and the sabre then waited for a clear the guest doesn't send for a disabled interrupt. Now the request's slot (`irq_request >> 2`) is compared, as the OBIO branch compares the ino. Found by reading `sabre.c` while tracing the lost IDE interrupt; Linux 7.0 leaves the NIC's map register valid when it frees the interrupt, so it wasn't that, and no other guest was traced for it | ours | not fixed; see `upstream/qemu-sabre-pci-interrupt-replaces-request.md` |
| `0138-tests-qtest-test-disabling-a-PCI-interrupt-on-the-sa` | `sun4u-sabre-irq-test` cases `pci-disable-drops-request` and `pci-disable-other-slot` for 0137 (5 cases in all): disabling slot 4 drops the NIC's outstanding request so the IDE request gets through, enabling it again requests the NIC's line, and leaves the requests of ino 0x14 (slot 5) and ino 4 (slot 1) alone. Both fail without 0137 | ours | not in QEMU |
| `0141-hw-char-escc-end-a-break-with-an-interrupt-for-its-s` | A break on a serial line (QMP `chardev-send-break`, a telnet BREAK) set RR0's Break/Abort bit for good, and the interrupt stayed up with nothing in RR3 or RR2 naming it: Solaris and SunOS on ttya spun in their serial interrupt, Linux never reached the firmware prompt, NetBSD never entered ddb. The bit now goes to 1 and back to 0, each change latching an external/status interrupt (WR1 bit 0 and WR15 bit 7) that RR3 and the vector in RR2 name and the Reset Ext/Status Interrupts command clears; the break ends one character time after it began, but not before the guest has reset the interrupt of its start, with a NUL in the receiver ("Stop-A") | ours, on the LEMU ESCC patches | not fixed |
| `0142-tests-qtest-test-a-break-on-a-serial-line-of-the-sun` | qtest `sun4m-escc-break-test` for 0141 (breaks on ttya and ttyb of an SS-5 through null chardevs): `start-and-end` (the start latched past the character time until the guest resets it, then the end with the NUL, receive named first), `end-after-char-time`, `polled` (no interrupt enabled), `channel-b` (its vector), `channel-reset`; all five fail without 0141 | ours | |
| `0139-target-sparc-halt-Linux-s-idle-loop-on-sun4u-under-t` | 0070's Linux helper checked for a pending interrupt and then set `cs->halted` without the BQL. A tick or stick interrupt that fired between the two (`tick_irq()` runs in the main loop with the BQL) set `SOFTINT` and `halted = 0` before the helper set it to 1; at `%pil` 14 it is masked, raises no `CPU_INTERRUPT_HARD`, so the vCPU thread slept through it, and Linux, not having taken the tick, armed no next one: asleep until the next interrupt vector, or for good on an idle guest. The helper now checks again and halts under the BQL. The other idle helpers (0042, 0071, 0110, 0114) halt at `%pil` 0, where the tick raises `CPU_INTERRUPT_HARD`, which the vCPU thread checks under the BQL before it sleeps; they keep the window without the effect. Found by reading, never seen on a guest ("sparc64 (sun4u)", "Idle") | ours | not in QEMU |
| `0140-tests-qtest-test-a-tick-between-the-idle-check-and-t` | `sun4u-idle-test` case `tick-race` for every idle loop (80 cases in all): QEMU writes the `sparc64_idle` trace, which comes between the check and the halt, to a FIFO the test has filled, so the CPU waits there with nothing pending while the tick fires; let go, it must take the tick and go on. Without 0139 the three Linux layouts fail every time (no round and no tick afterwards), the `%pil` 0 loops pass either way. Skipped without the `log` trace backend and on Windows. The test now runs about 70 s: 240 s in `slow_qtests` | ours | not in QEMU |

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

0034-0035 apply on top of 0001-0027 (written before 0028-0030; they touch `hw/sparc64/sun4u.c` and the
`qtests_sparc64` list only). `sun4u-idprom-test` passes 5/5 with 0034 (`qemu-system-sparc64` built
from 0001-0027 + 0034-0035); against the packaged 11.1.3-2+wsh16 binary its `device` case fails
with `52:54:00:12:34:56` in the IDPROM. `sun4u-cmd646-test` still passes 2/2. Lab results under
"The sun4u system MAC".

0001-0039 apply to 11.1.3 with `patch -F0` (0034-0035 regenerated on top of 0033). `sun4u-softint-test`
passed 30 of 30 runs with 0036 (20 001-20 399 ticks each, none lost, under a second each) and failed
30 of 30 without it, each run losing a tick within its first three. `sun4m-esp-test` passes with
0038 and fails without it (the first CDB byte after the SDTR message already ends the command
phase).

0001-0041 apply to 11.1.3 with `patch -F0` (the whole series, Proxmox's patches included, from
`pve-qemu.patch` onto a fresh tree: the result is the tree the binaries below were built from).
`sun4m-esp-test` passes 5/5 with 0040-0041; with 0040 left out the three cases that set the
latency don't start (no such property) and `irq-latency-default-off` passes. (The first versions of
0040 set 500 on every sun4m machine; with that one left out, `irq-latency` failed with STAT_INT
right after the selection.) With 0001-0041 the `qtest-sparc` and
`qtest-sparc64` suites: 40 OK, 4 skipped, and the two `qmp-test` `oob` failures as before;
`am53c974-test` (i386) 12/12. A save and load by hand (`migrate` to a file 100 us after a
selection, `-incoming` from it, qtest clock) kept the pending interrupt: none right after `cont`,
STAT_INT and the line 500 us later. Lab results under "NeXTSTEP 3.3 and OPENSTEP 4.2".

Carried back from the port of these patches to a LEMU fork (its `feat/sparc-fixes` branch), into
the existing patches: 0023's helper takes `disp_nrunnable`'s address as physical when the MMU is
off (the debug lookup tries an instruction fetch first, which boot mode takes from the PROM; real
guests run with the MMU on and never hit it), and 0016 and 0025 put a decoy 1 in the PROM at that
RAM address, so their idle cases fail with the old lookup (checked with the 0001-0037 binary: both
fail); 0021's `cmd646_reset()` clears `intrq`, and 0022's new `reset-drops-intrq` case fails
without it; checkpatch-style clean-ups in those tests and in 0021/0023 (line lengths, comments, a
table instead of `atoi`/`strtoul`). The `SOL_*` macro comments in `translate.c` (0014/0023) were
left as they are. Lab regression with the 0001-0039 binaries (2026-11-18): `smoke` 3/3, `idle`
13/13 (SunOS 4.1.4 and 2.5.1 among them), `smp` 3/3, `solaris10` 2/2, `sparc64` 9/9 (two cases,
`nb111-cd-vga-sparc64` and `nb111-virtio-sparc64`, failed at the start in the first run because the
lab's firmware directory lacked `vgabios-stdvga.bin` and `efi-virtio.rom`, a setup error, and
passed when re-run with them). With 0001-0039 the `qtest-sparc` and `qtest-sparc64` suites: 40 OK, 4 skipped,
and the two `qmp-test` `oob` failures as before (`sun4m-esp-test` 1/1, `sun4u-idprom-test` 5/5,
`sun4u-softint-test` 1/1, `sun4u-cmd646-test` 3/3, every sun4m qtest above).

0042-0044 apply on top of 0001-0041 with `patch -F0`. `sun4u-idle-test` passes 24/24 with them;
against the binary built without them its first case, `netbsd/idle`, fails (the loop went on: 6.1
million rounds in 300 ms), and against an earlier build of 0042 that took a BPcc branch only on `%icc`,
`tribblix/idle` fails (its loop ends with `ba,pt %xcc`, as Tribblix's gcc lays it out).
With 0001-0044 the `qtest-sparc` and `qtest-sparc64` suites: 41 OK, 4 skipped, and the two
`qmp-test` `oob` failures as before (`sun4m-solaris-idle-test` 5/5, `sun4m-solaris-smp-idle-test`
4/4). Lab regression with the 0001-0044 `qemu-system-sparc64` (2026-11-20): `sparc64` 10/10 (with the
new `nb111-idle-sparc64`, 2.7%, and `nb111-noidle-spins-sparc64`, 100.5%), `solaris10` 2/2, and
`wsh-lab boot-test` through PVE (the binary bind-mounted into the test node, packages 11.1.3-2+wsh26) of
the stored disks of `netbsd111-sparc64`, `netbsd93-sparc64`, `openbsd80-sun4u`, `sol9-sun4u`,
`sol10-sun4u` and `tribblix-m34-sun4u`: 6/6 passed (Tribblix 33.7 min). Results under "sparc64 (sun4u)", "Idle".

0047-0048 apply on top of 0001-0046 with `patch -F0`. `sun4m-mmu-ctx-ifetch-test` passes 4/4 with
them; against the binary built from 0001-0046 its two `traps-off` cases stop QEMU with `Trap 0x21
(Instruction Access Error) while interrupts disabled` at the first fetch in the new context (as
Solaris 2.1 does), and the two `traps-on` cases pass. Plain QEMU 11.1.3 (no patch of ours or
LEMU's) fails the same way. With 0001-0048 the `qtest-sparc` and `qtest-sparc64` suites: 43 OK, 4
skipped, and the two `qmp-test` `oob` failures as before. Lab boots with the 0001-0048 binaries
(2026-11-20, OpenBIOS 0001-0026, `solaris-boot-disk.py` on copies of the stored disks, trace event
`sparc_mmu_ifetch_hold` on): the installed `sol21-ss10` disk's first boot passes (`SunOS
sol21-ss10 5.1 Generic sun4m sparc`, 42 uses of the kept translation); `sol22-ss10`,
`sol23-ss5`, `sol24-ss20` and `sol251-ss5` pass with no use; `netbsd93-sparc64` (sun4u,
`netbsd-boot-disk.py`) passes with the same build's `qemu-system-sparc64`. The same 2.1 disk on
plain QEMU 11.1.3 stops at `pc f0014768` 12 s after the kernel banner.

0049-0050 apply on top of 0001-0048 (2026-11-20). `sun4m-bus-error-trap-test` passes 10/10 with
them; against plain QEMU 11.1.3 its `ss10/load` and `ss10/fetch` cases fail (trap 0x29 and 0x21) and
the other cases pass (the feature-off case needs the feature to exist). With 0001-0050 the
`qtest-sparc` suite: 25 OK, 2 skipped, and the `qmp-test` `oob` failure as before (the sparc64
target was only compiled: `target/sparc/ldst_helper.c` and `cpu.c` build). Lab, with the
0001-0050 `qemu-system-sparc` (the `openbios-sparc32` of pve-qemu-kvm 11.1.3-2+wsh30, the check
scenarios on copies of the stored disks, trace event `sparc_bus_error_access_exc` on): SunOS 4.1.3
installs on the SS-10 and boots ("Older Sun releases on sun4m"), and 34 of 34 stored disks boot and
pass their check as before: 18 on the SS-10 and SS-20 (Solaris 2.6 on the SS-20 also with 4 CPUs),
16 on the SS-5 (two of them under `ss5.bin`); the list is under "Older Sun releases on sun4m".

0053-0055 apply on top of 0001-0052 (2026-11-21, lab builds of 11.1.3; not in a package yet).
`sun4m-fp-deferred-trap-test` passes 36/36 with them; against plain QEMU 11.1.3 its 27 trap cases
fail (trap 8 at the `fdivs`) and the other 9 pass. With 0001-0055 the `qtest-sparc` and
`qtest-sparc64` suites: 45 OK, 4 skipped, and the two `qmp-test` `oob` failures as before
(`sparc-linux-user`, `sparc32plus-linux-user` and `sparc64-linux-user` build too). The LX PROM's
POST passes its FPU tests ("SPARCstation LX with its own PROM"), the SS-5 PROM's POST prints the
same as before. SIGFPE in a real system: a small C program (gcc 2.95.3 on the Solaris 2.6 build
disk; statically linked, through a scratch disk, for the SS-5) enables the divide-by-zero trap,
runs `fdivs` 1/0 and catches SIGFPE. On Solaris 2.6 on the SS-20 and on the SS-5 (the stored
`sol26-ss5`) it gets SIGFPE with `FPE_FLTDIV` and `si_addr` at the `fdivs` in 504 of 504 cases,
with 0053 at the next FP instruction (`fdivs` + 100; without it `fdivs` + 4), and also with 50
system calls or a `sleep(1)` between the two (on the SS-20 the kernel then takes the trap, on the
SS-5 a libc routine); the masked case gives +inf with the sticky dz flag, and the program's own
sums and nawk and bc give the same digits as without 0053; the system keeps running and shuts down
cleanly. 0055: `-m 256` is refused on LX, SPARCClassic and SPARCbook, the SS-5 still takes it, and
OpenBIOS reaches its prompt with 128 MB on all three (with 256 MB it stopped with `Trap 0x21`, also
on plain 11.1.3). Lab boots with the 0001-0055 `qemu-system-sparc` (the `openbios-sparc32` of
pve-qemu-kvm 11.1.3-2+wsh30, the check scenarios on copies of the stored disks): 34 of 34 stored disks
boot and pass their check as before: 18 on the SS-10 and SS-20 (Solaris 2.6 on the SS-20 also with 4
CPUs), 16 on the SS-5 (two of them under `ss5.bin`); the same list as for 0049-0050 above. With the OpenBIOS image of the lab container
(built 2026-11-18) `sol22-ss10` stops in OpenBIOS before its kernel, with and without 0053; the
wsh30 OpenBIOS boots it.

0056-0058 apply on top of 0001-0055 (2026-11-21, lab builds of 11.1.3; not in a package yet).
`sun4m-onboard-sbus-test` passes 4/4 with them; against the 0001-0055 build its LX region and both
DBRI FCode cases fail and the SS-5 case passes. With 0001-0058 the `qtest-sparc` and
`qtest-sparc64` suites: 46 OK, 4 skipped, and the two `qmp-test` `oob` failures as before. The LX
PROM boots Solaris 2.6, NetBSD 9.3, SunOS 4.1.4 and 4.1.3_U1B ("SPARCstation LX with its own
PROM"). Regression with the 0001-0058 `qemu-system-sparc` (the wsh30 `openbios-sparc32`, check
scenarios on copies of the stored disks): 12 of 12 boot and pass their check: `sol26-ss20` (also
with 4 CPUs), `sol7-ss20`, `netbsd93-sparc-ss20`, `openbsd59-ss20`, `sol26-ss10`, `sol22-ss10`,
`sol7-ss10`, `sol26-ss5`, `netbsd93-sparc`, `openbsd59-ss5` and `sol8-ss5-prom` (`ss5.bin`).
Under the SS-20's Sun PROM (`ss20_v2.25_rom`, `-cpu TI-SuperSparc-50`), the `sol26-ss20` disk boots
and passes with and without 0057 (with it `prtconf -D` lists `SUNW,DBRIe` with the `dbri` driver
and no `/dev/audio`), and the Solaris 2.2 CD reaches its installer without `PROM_NAME_UNNAMED`
(without 0057: `BAD TRAP: type=9`, `panic: Data fault`). OpenBIOS on `-M LX` as before (the LX
section).

0059-0060 apply on top of 0001-0058 (2026-11-21, lab builds of 11.1.3; not in a package yet):
`sun4m-nvram-test` 7/7, `qtest-sparc` 28 OK with `m48t59-test` and `prom-env-test`, 2 skipped and the
`qmp-test` `oob` failure as before ("The NVRAM kept in a volume").

0061-0062 apply on top of 0001-0060 (2026-11-21, lab build of 11.1.3; not in a package yet):
`sun4m-ledma-test` 5/5 (its lance and reset cases fail without 0061), `qtest-sparc` 29 OK, 2 skipped
and the `qmp-test` `oob` failure as before.

0070-0072 apply on top of 0001-0067 (2026-11-22, lab build of 11.1.3; not in a package yet; the whole
series with `patch -F0` on the pinned 11.1.3, 145 patches). `sun4u-idle-test` passes 51/51 with them;
against the 0001-0067 build the `idle` and `tick` cases of `solaris7` and the three Linux layouts fail
(the loop went on: 1.1-10.6 million rounds in 300 ms) and the old layouts' cases pass. 0070 and
0071 each build without a warning. With 0001-0072 the `qtest-sparc` and `qtest-sparc64` suites: 50 OK,
4 skipped, and the two `qmp-test` `oob` failures as before.
Lab regression with the 0001-0072 `qemu-system-sparc64` (2026-11-22): `sparc64` 10/10
(`nb111-idle-sparc64` 2.4%, `nb111-noidle-spins-sparc64` 99.8%), `solaris10` 2/2, and `wsh-lab
boot-test` through PVE (the binary bind-mounted into the test node behind a wrapper that adds the
version suffix qemu-server parses and `-L /usr/share/kvm`; packages 11.1.3-3+wsh13) of the stored
`sol8-sun4u` and `sol7-sun4u` disks: 2/2 passed (4.5 and 4.1 min). The sparc32 binary wasn't tested
again: 0070-0072 change only code built for sparc64. Results under "sparc64 (sun4u)", "Idle".

When pve-qemu moves to a new QEMU: check each patch still applies, drop any that upstream has
taken, and run `sun4m-escc-test`, `sun4m-apc-test`, `sun4m-solaris-idle-test`,
`sun4m-mmu-nofault-test`, `sun4m-pil-delay-slot-test`, `sun4m-solaris-smp-idle-test` and
`sun4m-fsr-rd-test`, `sun4m-cs4231-test`, `sun4m-esp-test`, `sun4m-mmu-ctx-ifetch-test` and
`sun4m-bus-error-trap-test`, `sun4m-fp-deferred-trap-test`, `sun4m-onboard-sbus-test`,
`sun4m-nvram-test` and `sun4m-ledma-test` (sparc),
`sun4u-cmd646-test`, `sun4u-idprom-test`, `sun4u-softint-test` and `sun4u-idle-test` (sparc64) and
`am53c974-test` (i386).

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
| `0018-sparc32-give-the-cs4231-intr-9-the-level-of-its-sbus-level` | The SS-5's `SUNW,CS4231` node had `interrupts` 5 (SBus level 5, processor level 9) and `intr` 5 (processor level 5): Solaris waits where the first says, SunOS 4 where the second says, so no wiring served both. `intr` is now 9, as the Sun PROM's `0x39`, for QEMU patch 0030 ("Audio"); 0034 makes it `0x39` | not in OpenBIOS (QEMU had no working codec) |
| `0019-sparc32-give-the-solaris-2.1-2.4-boot-block-the-obp-words-it-uses` | The Solaris 2.1-2.4 boot block is FCode that its machine code hands to `byte-load` through the romvec; it looks up OBP 2.x words by name (`romvec`, `(is`, `op-open`/`op-close`/`op-read`/`op-seek`, `adjust-header`, `?go`) and sets `load-base` with `(is`. Without them: `(is ?`, then `Unhandled Exception 0x00000009` reading the romvec at 0xffe80098. Now the words exist, `load-base` is a value (as on sparc64), and `init-program` starts code the client put at `load-base` itself ("Older Sun releases on sun4m") | not fixed; see `upstream/openbios-sparc32-old-solaris.md` |
| `0020-sparc32-keep-the-forth-heap-inside-the-firmwares-own-virtual-range` | The 128K Forth heap was mapped at 0xffce0000, below the 0xffd00000-0xfff00000 range a Sun PROM keeps to; the Solaris 2.3/2.4 kernelmap ends at 0xffd00000 and they panicked: `can't remove OBP hole`. Now above the I/O mappings, inside the firmware's reserved 2 MB | not fixed; same note |
| `0021-sparc32-take-node-0-as-the-root-node-in-the-romvec-property-operations` | OBP 2.x takes node 0 for the root in `no_proplen`/`no_getprop`/`no_nextprop`; Solaris 2.3 asks for the root's `name` that way, got -1 and panicked (`BAD TRAP: type=9 ... addr=fffff000`) | not fixed; same note |
| `0022-sparc32-run-the-romvec-calls-with-interrupts-masked` | The romvec handlers ran OpenBIOS at the client's PIL; Solaris 2.4 calls `prom_getproplen()` from its idle thread with interrupts on, and in 2 of 4 boots a second romvec call got into the (non-reentrant) Forth engine meanwhile: `BAD TRAP: type=9 ... addr=0` in OpenBIOS's `c@`. Now PIL 15 for the call, back to the caller's PIL after (sparc64's client interface does the same, 0016) | not fixed; same note |
| `0026-fb8-blink-screen-dont-wait-on-a-counter-that-may-be-stopped` | Shared Forth code (built into both images; matters on sparc32): BEL on a framebuffer console (cg3, TCX) inverted the screen and then waited `2000 ms` on `obp-ticks`, which only OpenBIOS's own level-14 timer handler advances. Solaris 2.x and SunOS 4.1.4 write their framebuffer console through the romvec with their own trap table installed, so the counter stood still and the console hung with the screen inverted on the first BEL (bash's completion bell). The wait is now at most 100 ms on the counter and at most 20000 reads of it; `2000` was hex (8.2 s at the firmware prompt). Also drops the flag the BEL case left on the data stack ("BEL on the framebuffer console") | not fixed; see `upstream/openbios-fb8-blink-screen-hangs-client-console.md` |
| `0027-sparc32-leave-out-the-apc-node-on-the-lx-and-the-voyager` | Every machine ID from 32 to 63 got the SS-5's APC node (`power-management` at SBus slot 4 offset `0x0a000000`, `0x6a000000`). QEMU has no APC there on `-M LX` (a real LX has none) or `-M Voyager` (its power controller is at `0x71300000`), and Linux's `apc` driver makes `apc_swift_idle()` its idle routine: the first idle took a data access error on the APC register, `do_sparc_fault()` followed the NULL from `search_exception_tables()`, and the nested faults ran the kernel stack down through the kernel text until QEMU stopped in the overwritten trap entry (`Trap 0x07` in `tsetup_patch2` on the LX, `Trap 0x02` on the Voyager; `e2e/wisp/README.md`, "The LX and the Voyager"). The node is now made only on the SS-5, SS-4, SPARCClassic and SPARCbook | not reported |
| `0028-sparc32-name-the-ss600mp-dma-and-lebuffer-nodes-as-sunos-4.1.2-knows-them` | SunOS 4.1.2, the first release for the SS-600MP (machine ID 66), finds the on-board SCSI and Ethernet by node name: the ESP under a DMA controller named `dma` (as on the SPARCstation 1 and 2), the lance under an `lebuffer`. OpenBIOS gave the machine the SS-10's `espdma` and `ledma`, and the kernel attached no disk and no network interface. On machine ID 66 the DMA node is `dma` (`ob_esp_init()` takes the DMA node's path, so the esp and sd nodes and the disk and cdrom aliases are under `/iommu/sbus/dma/esp`) and the lance's parent `lebuffer`, `reg` slot f `0x40000` size `0x20000` (pve-qemu 0064), without the ledma's register setup ("Older Sun releases on sun4m") | not reported |
| `0029-sparc32-leave-out-the-cs4231-node-where-qemu-has-no-codec` | Every machine ID from 32 to 63 got the SS-5's `SUNW,CS4231` node (SBus slot 4 offset `0x0c000000`, `0x6c000000`). QEMU has the codec only on the SS-5 and the SS-4, and at no other address on the Voyager, the LX, the SPARCClassic or the SPARCbook (the LX's audio is the DBRI in slot 2, `wsh/0056`). The stored `netbsd93-sparc` disk on `-M LX` panicked in autoconfiguration: `audiocs0 at sbus0 slot 4 offset 0xc000000`, then `trap 0x29` (data fault) at `0x6c000000`. 0027's APC helper is now a table of what QEMU has in slot 4 per machine ID: codec and APC on the SS-5 (32) and SS-4 (35), the APC only on the SPARCClassic (36) and SPARCbook (37), neither on the Voyager (33) or the LX (34) nor on IDs QEMU doesn't have. The disk then boots to `login:` on the LX ("SPARCstation LX with its own PROM") | not reported |

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
| `0013-sparc64-ofmem-keep-the-upper-bits-of-physical-addresses-in-align_ptr` | `align_ptr()` masked with a 32-bit `size_t`, so the firmware's heap broke once it sat above 4 GB (it is at the top of RAM): from about 4.3 GB OpenBIOS stopped before its banner (`Unhandled Exception 0x0000000000000030`; at 8192 MB `out of malloc memory (28)!` first). Generic code, applied to sparc64 only here | not fixed; see `upstream/openbios-sparc64-ram-above-4g.md` |
| `0014-sparc64-ofmem-find-claim-memory-whose-1-1-virtual-range-is-free` | A client `claim` with an alignment took the top of RAM and mapped it 1:1 without checking the virtual side; with 4 GB that is the firmware's own range, the claim failed and NetBSD stopped after its loader (`Can't claim two pages of memory.`). It now searches below `0xff000000` and lower while the virtual range is taken. Generic code, applied to sparc64 only here | as 0013 |
| `0015-sparc64-return-the-whole-physical-address-in-phys-lo` | `claim`, `SUNW,retain` and `translate` cut `phys.lo` to 32 bits, but 64-bit NetBSD and Solaris read `phys.lo` alone. With 6 and 8 GB NetBSD's kernel sat above 4 GB, `ofwboot` mapped the truncated addresses, and once memory filled up the kernel stopped (`trap type 0x10`, `panic: illegal instruction`). `phys.lo` now carries the whole address | as 0013 |
| `0016-sparc64-client-interface-runs-with-interrupts-disabled` | The client interface walked `%cwp` through every window and rewrote the trap registers (saving and restoring the caller's state) with the caller's `PSTATE.IE`. Solaris and illumos call in with interrupts enabled and their own trap table: an interrupt in between overwrote the caller's windows. Tribblix's live CD stopped on most boots (corrupted locals after a call, `bad stack overflow at TL 2`); Solaris 10's one `BAD TRAP: type=4e` in the firmware was the same. Interrupts are now off from entry until the caller's `%pstate` is written back ("Tribblix on sun4u") | not fixed; see `upstream/openbios-sparc64-client-interface-interrupts.md` |
| `0017-sparc64-fcode-put-xa-plus-and-xa1-plus-into-the-64-bit-table` | The 64-bit FCode table had the entries for `xa+` (0x24a) and `xa1+` (0x24b) commented out, so every token from 0x24a on ran the word two places further down (`xlsplit` ran `xwflips`). The illumos ZFS boot block uses `xlsplit`: a Tribblix ZFS root disk stopped with `Unhandled Exception 0x30` right after the boot block had loaded its file system package; now it boots ("Tribblix on sun4u"). Generic code, applied to sparc64 only here | not fixed; see `upstream/openbios-fcode-64bit-token-table.md` |
| `0023-client-call-method-store-the-catch-result-only-when-nret-is-not-0` | Shared client-interface code (built into both images; used by sparc64 clients): `call-method` and `interpret` wrote the catch result to `args[nargs]` even when the client asked for no results (`nret` 0), over whatever followed its argument array. OpenBSD 8.0's installed sun4u kernel calls the MMU's `map` that way with the arguments on its stack, so the store hit its stack-protector canary and the kernel stopped right after the loader (`Unhandled Exception 0x30`, "sparc64"). Now stored only when `nret` > 0; the installed OpenBSD 8.0 boots to `login:` | not fixed |
| `0024-sparc64-ofmem-list-whole-pages-in-memory-available` | `/memory` `available` is built from the gaps between claimed ranges, which are recorded to the byte (the ELF loader claims the Solaris boot program's segments at 0x100000 with their exact sizes), so its entries could start inside a page (`00181540 3cef2ac0`). Solaris 7/8/9 count such an entry one page short at its top; the top-down allocator later gave a boot allocation exactly that page and the kernel panicked: `boot_alloc: pp is NULL or free` (7: `kmem_getpages: ...`). Entries are now rounded to whole pages (start up, end down) as OBP lists them; the allocator is unchanged ("Solaris 7/8/9: `pp is NULL or free`"). Generic file, `#ifdef CONFIG_SPARC64` | not fixed; see `upstream/openbios-sparc64-memory-available-pages.md` |
| `0025-sparc64-leave-out-the-ebus-floppy-node` | The ebus had an `fdthree@0,0` node with one `reg` entry of size 0 and no interrupt. OBP's `fdthree` on the Ultra 5/10 has three (the 82077, the ebus DMA engine that drives it, the auxio register); QEMU's sun4u has a PC-style FDC at I/O `0x3f0` without DMA and neither of the others, so no `reg` would describe a controller that a driver for OBP's node could run. Solaris 8 and 10 warned (`Out of range register specification from device node <fdthree>`); the first, reconfiguring boot of an installed Solaris 9 panicked in `fd` (NULL pointer, `fd_cleanup` ← `fd_attach`). The node is gone on sun4u (OpenBIOS never booted from it: `-boot a` names `/obio/SUNW,fdtwo`); sun4m's `SUNW,fdtwo` is unchanged ("Solaris 8 and 9 install targets on sun4u") | not fixed; see `upstream/openbios-sparc64-floppy-node.md` |
| `0030-sparc64-reset-the-machine-on-the-client-interface-boot-service` | The client interface `boot` service, through which Solaris, Linux and the BSDs reboot, printed `BOOT` and returned (Solaris: `prom_reboot: reboot call returned!`, Linux: `Reboot failed!`). It now resets the machine (`reset-all`), and `entry` puts back what a power-on leaves and the reset didn't: SOFTINT and the interrupt receive register cleared (Solaris 10 left level 6 pending: `Unhandled Exception 0x6`, 0012's hang), TICK.NPT set (else the firmware's timer keeps firing into the miss handler and the next kernel), and after any reset but the first the RAM below the firmware cleared, except a `-kernel`/`-initrd` image (Solaris 9/10 panicked on the old page structures). The bootspec isn't kept ("The firmware reboot on sun4u") | not reported |
| `0031-sparc64-give-the-solaris-2.5.1-2.6-boot-block-init-program-and-go` | The sun4u boot block of Solaris 2.5.1 and 2.6 (FCode UFS Reader 1.6/1.10) copies ufsboot's ELF segments into place itself, then evaluates `to load-base init-program` with `load-base` at the entry point and `?go`; OpenBIOS's `init-program` recognised no header there and there was no `?go`: `?go:`, `byte-load: exception caught!`. `init-program` looked up by name now takes unrecognised code at `load-base` as the program (as OBP), after clearing `state-valid`; `?go` starts it. Both kernels start ("Solaris 2.5.1 and 2.6 on sun4u: the boot block") | not in OpenBIOS |
| `0032-sparc64-keep-interrupts-disabled-in-the-mmu-miss-handlers` | The I- and D-MMU miss handlers enabled interrupts around their C handler ("for window spill/fill traps", which don't need them) at TL 1, where the TL>0 table's level 14 entry only retries: a timer interrupt pending then trapped again on the same instruction for good. FreeBSD 12.4's `shutdown -p now` (the `SUNW,power-off` call, with its `%tick` interrupt pending) stayed on after `Uptime:` at 100% of a host core (`-d int`: interrupt 0x4e at one PC). They now run with interrupts disabled, as the trap left them ("FreeBSD 12.4 on sun4u") | not reported |
| `0033-sparc64-save-and-restore-the-trap-state-of-tl-4-to-1` | `SAVE_CPU_TRAP_STATE`/`RESTORE_CPU_TRAP_STATE` walked `%tl` from 3 down to 0, so a few instructions of every client call ran at TL 0 (no trap state there; `rdpr %tpc` is an illegal instruction at TL 0 on the UltraSPARC), fetched in the primary context. FreeBSD runs its kernel at TL 1 with the user process's context in the primary context register: the firmware's context-0 ITLB entry missed, FreeBSD's own trap table found no mapping, and every reboot and `ofwdump` panicked (`fast instruction access mmu miss (kernel)`; QEMU then stopped with `Trap 0x00a4 while trap level (5) >= MAXTL (5)`). Now TL 4 down to 1 ("FreeBSD 12.4 on sun4u") | not reported |
| `0034-sparc32-mark-the-cs4231-intr-as-an-sbus-interrupt-0x39` | Linux reads `intr` in the encoding of Sun's PROMs (`sun4m_build_device_irq()`: below 0x20 a software interrupt, 0x20-0x2f on-board, 0x30-0x3f SBus, the low four bits the processor level), so 0018's `intr` 9 was software interrupt 9: Linux 7.3 enabled that and left SBus level 5 masked in the system interrupt mask (`slavio_check_interrupts pending 0x0 disabled 0x7ff33f7f`, bit 11 set), `cs4231` stayed at 0 in `/proc/interrupts` and wisp's `soundtest` failed with EIO after the first buffer. Now `0x39`, as the SS-5's own PROM has it and as OpenBIOS already encodes the ESP (`0x24`). SunOS 4.1.4 takes the low four bits (`SUNW,CS42310 at SBus slot 4 0xc000000 pri 9 (sbus level 5)`) and Solaris 2.6 `interrupts` (still 5); both play. Linux also needs the codec's INT status bit, which QEMU's CS4231 doesn't set ("Audio", "Linux") | ours, not proposed upstream |
| `0035-sparc64-give-the-ebus-8042-a-kdmouse-child` | The ebus `8042` has only its `kb_ps2` child (reg 0, no interrupts) and one interrupt. Linux's sparc i8042 probe (`i8042-sparcio.h`) needs a keyboard and a mouse child (`kdmouse` or `mouse`) and returns `-ENODEV`, so Linux has no PS/2 keyboard on sun4u; it also takes the keyboard child's translated address as the port base (data at + 0x60) and each child's first interrupt. New option `ps2-mouse?` (default false; `-prom-env ps2-mouse?=true`): the 8042 then gets a `kdmouse` child (reg 1), interrupts 1 and 2 on the 8042 and its children with an ebus `interrupt-map` entry for 2 to the sabre's mouse INO `0x2a` (QEMU's ISA IRQ 12), and `#size-cells` 1 with `ranges` mapping child address 0 to ebus `14,0` (without `ranges` Linux maps a child's reg 1:1, to physical 0). Off by default because Debian 7's Linux 3.2 panics in `sparc_i8042_probe()` once the probe succeeds (its sparc OF driver, also named `i8042`, takes the core's platform device); Debian 12/13 kernels print `Driver 'i8042' is already registered` and carry on without the keyboard. Linux 7.3 gets the keyboard with its OF driver renamed (`e2e/wisp/linux-patches/0001`). With the option false the tree is unchanged apart from the option in `/options`; with it true NetBSD 11.1 also takes the mouse interrupt (`pckbc0 at ebus0 addr 60-67 ipl 29 ipl 2a`) and Solaris 8-10 boot as before | ours, not proposed upstream |

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
| Solaris 2.6 | SS-5, OpenBIOS | ttya, break (QMP `chardev-send-break`) | no prompt (the hang wasn't checked; it is QEMU's) | no prompt; the guest hangs (below); with pve-qemu `wsh/0141`: prompt, a shell command after `go` works |
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

**A break on ttya hung Solaris** (any firmware; QEMU's ESCC, fixed by pve-qemu `wsh/0141`).
QEMU's `serial_receive_break()` set RR0's break bit on `CHR_EVENT_BREAK` and never cleared it, and
`escc_update_irq()` kept the channel's interrupt raised for as long as the bit and WR15's break
enable were set. Nothing named that interrupt: the model had no external/status bits in RR3, and
RR2 of channel B said "no interrupt". Solaris's `zs_high_intr()` (`uts/sun/io/zs_common.c`) reads
that vector, finds nothing, returns, and takes the interrupt again; its `zsa_xsint()`
(`zs_async.c`) would have entered the abort only when the bit went back to 0, the end of the
break. Measured (Solaris 2.6 on ttya, SS-5, OpenBIOS with 0008, root shell, QMP
`chardev-send-break id=ttya`): QEMU's CPU went from 8.5% to 100.9% of a core, the ESCC register
reads from 0 to 1.9 million in 5 s, the PC samples moved from the idle loop to kernel interrupt
code, and the shell no longer answered (no echo for 60 s; 120 s on 11.1.3-4+wsh22, QEMU at 100%
of a core all along). QEMU stays up. SunOS 4.1.4 hung the same way, Linux (wisp, 7.3) never
reached the firmware prompt, and NetBSD 9.3 never entered ddb (its console took 37 s to answer a
Return after it). Plain QEMU 11.1.3 (no wsh patches, the package's OpenBIOS) hangs Solaris 2.6 the
same way (shell dead for 120 s after the break): the bug is QEMU's, not LEMU's.

**What the drivers expect** (the Z8530 manual and the drivers' sources): the bit goes to 1 when a
break starts and back to 0 when it ends; each change latches an external/status interrupt when
WR1 bit 0 and WR15 bit 7 enable it, RR0 keeps the latched value until the guest's Reset
Ext/Status Interrupts command (WR0 0x10), and a change while latched gives a new interrupt after
that reset. The end leaves a NUL character in the receiver. Solaris and SunOS enter the PROM on
the 1-to-0 change on the console and throw the NUL away (also one received during the break);
Linux's `sunzilog` reads RR0 until the bit is 0 inside its interrupt handler, then enters the
PROM; NetBSD enters ddb at the start (`cn_check_magic(CNC_BREAK)`).

**Fix** (`wsh/0141`, ours, written on top of the LEMU ESCC patches 0002 and 0006): that latch for
the break bit, the interrupt in RR3 (bits 0 and 3) and in RR2's vector (Ch A/B External/Status,
after receive and transmit of the same channel), and the reset command. The chardev gives one
event and no length, so the break lasts one character time at the programmed rate, but at least
until the guest has reset the interrupt that showed its start, so it sees both changes in order
however late it gets to the first; then the bit goes to 0 with a second interrupt and a NUL in the
receiver. Nothing is received during the break; a channel reset drops the pending interrupt; the
state is migrated in a subsection sent only during a break or with the interrupt pending. The
interrupt now also needs WR1's external/status enable, as on the chip (the drivers set it; the
firmware polls with no interrupt enabled and isn't disturbed). `wsh/0142` is the qtest
(`sun4m-escc-break-test`, 5 cases, all fail without 0141); `sun4m-escc-test` (the Sun keyboard and
mouse, 0005) still passes.

| Guest | Machine, console | Break on ttya, 11.1.3-4+wsh22 | With `wsh/0141` (two rounds) |
| --- | --- | --- | --- |
| Solaris 2.6 | SS-5, OpenBIOS, ttya, root shell | no prompt, shell dead for 120 s, QEMU at 100% | prompt, `go`, the shell answers |
| SunOS 4.1.4 | SS-5, OpenBIOS, ttya, login prompt | no prompt, QEMU at 100% | prompt, `go`, the login prompt answers |
| NetBSD 9.3 | SS-5, OpenBIOS, ttya, login prompt | no ddb; Return answered after 37 s | `db>`, `c`, the login prompt answers |
| NetBSD 11.1 | SS-5, OpenBIOS, ttya, login prompt | not run | `db>`, `c`, the login prompt answers |
| Linux 7.3 (wisp shell) | SS-5, OpenBIOS, `-kernel`, ttyS0 | no prompt | prompt (`2 >`: two cells left on the firmware's stack), `go`, the shell answers |
| none | SS-5, OpenBIOS, the firmware's own `0 >` | | ignored (the NUL changes nothing at the prompt) |

Run with `stop-a.py CONSOLE=serial BREAK=1` (plus `GUEST=sunos SHELL=0`, `GUEST=netbsd SHELL=0
EXPECT=db> RESUME=c`, `GUEST=none EXPECT=none`) against a `qemu-system-sparc` built from the series
with 0141 over the lab image of 11.1.3-4+wsh22; wisp with the command line of its README
(`wisp=shell`) and a small QMP script. Also still passing with 0141: Stop-A on the Sun keyboard
with a cg3 console (Solaris 2.6), and the sparc qtests (`qmp-test`'s `oob` case fails with and
without it). The `stopa` matrix has the break cases (they need a pve-qemu-kvm with 0141). Not run:
Solaris 2.5.1 or the Sun PROMs (the PROM's own break handling), SS-10/SS-20, a real telnet BREAK
(the same chardev event), migration during a break.

PVE still sends no break: its serial console is a plain Unix socket chardev (`serial0`), and
xterm.js, termproxy and `qm terminal` have no break. Now that a break does what it should, PVE could
offer one through QMP (`chardev-send-break id=serial0`), e.g. as a button of the serial console;
not done here.

### BEL on the framebuffer console

Reported from Solaris 2.6 on an SS-5 (under LEMU, whose OpenBIOS is the same code): on the cg3
console, Tab in bash with no unique completion turned the white background black, and then the
console hung. Reproduced in the lab with `scenarios/fb-bell.py` (cg3, console on the framebuffer
and the Sun keyboard, `boot disk:a -s`, a BEL from `echo B | tr B '\007'` or bash's Tab), stored
disks copied, `pve-qemu-kvm` 11.1.3-2+wsh25 (firmware 0001-0025):

- The screen inverts and stays inverted; the shell never answers. While hung, `info registers`:
  PSR `04400fe5` (PIL 15, from 0022), the PC in OpenBIOS's Forth inner interpreter (`semis`,
  `dovar`, `enterforth`, `next`, `docon` in five samples; symbols from `openbios-builtin.elf.nostrip`
  of the same sources, whose `.text` is byte-identical to the package's), `$tbr` `0xf0040050`
  (Solaris's own trap table; SunOS 4.1.4: `0xfe022050`), and `obp_ticks` → `0xffd27cbc` read
  20970 and again 20970 five seconds later.
- **Cause:** `fb8-blink-screen` (`forth/device/display.fs`, shared by cg3, TCX and VGA) is
  "invert, `2000 ms`, invert". `ms` polls `get-msecs`, which on sparc32 reads `obp-ticks`, and only
  OpenBIOS's level-14 handler `irq_entry14` (`arch/sparc32/vectors.S`) advances it. With the
  client's trap table installed that handler never runs (and 0022 masks interrupts during the
  romvec call too), so the wait never ends: the first analysis's guess (the counter stops once the
  client owns the traps) holds.
- Two more bugs on the same path: `2000` is hex in that file (the blink at the firmware's own
  prompt lasted 9-11 s in the screenshots, 0x2000 ms = 8.2 s), and the BEL case of `(term-emit)`
  leaves `execute-device-method`'s flag for `/screen`'s missing `ring-bell` on the data stack
  (`0 > 7 emit ok`, then `1 >`).
- sun4u: `obp-ticks` stays 0 at the prompt (`get-msecs .d` twice, 10 s apart: 0, then 1: the
  fallback that counts its own calls), so `ms` ends after that many calls and never hung there; the
  stack leak was there too (`1 >`, `2 >` after two `7 emit`).

**Fix (openbios 0026):** wait at most 100 ms on the counter and at most 20000 reads of it
(100000 reads took 400-680 ms at the prompt on the lab host, so 80-140 ms when the counter stands
still), `d#` numbers, and `drop` the flag. Making `ms` itself work under a client would mean
reading the counter-timer (sparc32) or `%tick` (sparc64) directly; `ms` has no other caller in
the tree, so the blink is bounded instead.

Results (2026-11-20; "stock" = the package's firmware, "0026" = `openbios/Dockerfile` with
0001-0026 bind-mounted over it; WAIT 30 s):

| Guest (SS-5, cg3 console) | stock | 0026 |
| --- | --- | --- |
| firmware prompt, `7 emit` | inverted 9-11 s, prompt `1 >` | flash of 0-0.2 s, prompt `0 >` |
| Solaris 2.6, `echo` of a BEL | hung, screen inverted (30 s) | answered; three BELs in a row answered |
| Solaris 2.6 on TCX (`VGA=tcx`), `echo` of a BEL | not run | answered; three answered |
| Solaris 9 9/05, `echo` of a BEL | hung | answered; three answered |
| Solaris 9 9/05, bash 2.05, `echo /usr/s` + Tab | hung | answered (the flash caught in one screenshot, 0.1 s) |
| SunOS 4.1.4, `echo` of a BEL | hung | answered; three answered |
| NetBSD 11.1 (its own wscons console), `echo` of a BEL | answered | answered |
| Solaris 2.6 on the serial console (`-vga none`), `echo` of a BEL | answered (the BEL went out on ttya) | not run |
| sun4u prompt (`-vga std`), `7 emit` twice | flash 0.1 s, prompt `2 >` | prompt `0 >` |

Regression with 0026 mounted: `matrix.py smoke` 3 of 3, `matrix.py solaris10` 2 of 2,
`matrix.py sparc64` 9 of 9 (NetBSD 11.1 on `std` VGA with the console on the framebuffer
included), and the stored disks `install-sol9-ss5`, `install-netbsd111-sparc`,
`install-sunos414-ss5` booted to their check commands on a serial console (`solaris-boot-disk.py`,
`netbsd-boot-disk.py`, `sunos-boot-disk.py`, `-nographic` as `vga: serial0`): all passed, each
banner showing the 0026 build.

Workaround for packages without 0026: `set bell-style none` in `~/.inputrc`, or a serial display or
telnet/ssh (guide, "The bell on a framebuffer console").

### Audio

The SS-5's CS4231 plays sound with pve-qemu 0028-0033 and openbios 0018: the APC DMA engine reads
the guest's buffers through the IOMMU and plays them into the audiodev given with
`-machine audiodev=<id>` (qemu-server: `audio0: device=cs4231,driver=...`). The codec is built into
the machine, so there is no `-device`. Without an audiodev (no `audio0`) the chip is the old
register stub: no sound and no interrupts, and a program that waits for the end of a sound hangs,
as before (SunOS 4.1.4, LEMU's report). `driver=none` gives a working chip that nobody hears.

Without an audiodev the codec asks for QEMU's default backend (0031). qemu-server always passes
`-nodefaults`, which leaves no default, so QEMU prints one line at the start,
`warning: cs4231: no sound: no default audio driver available` (in `qm start`'s output and the
task log, which still ends `TASK OK`), and opens no host sound device; a reset prints nothing more.
Checked on 2026-11-21 with an SS-5 VM without `audio0` in the e2e PVE image and a
`qemu-system-sparc` built from 0001-0062. QEMU run by hand without `-nodefaults` takes the first
backend that loads, in the order `dbus` and `spice` (only with those displays), `pa`, `pipewire`,
`alsa`, `none`; in a container without sound `alsa` loads, and every voice open (start and each
reset) prints ALSA errors and `Could not create a backend for voice 'cs4231'`. The SS-4 has the
same codec and behaves the same.

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
  sun4m. 0030 raises SBus level 5 and openbios 0018 makes `intr` 9; then all of the above play.
- Each sound lost its last 50 ms when the driver stopped the DMA as soon as the pipe ran empty
  (0032).
- An SS-5 without an audiodev didn't start (0031). The first fix opened no voice without an
  audiodev; LEMU's review kept the default backend, with a warning when there is none.

Linux (7.3.4, wisp's `soundtest` on `kernel-fb`, lab 2026-11-23) plays with openbios 0034 and
pve-qemu 0124 together; the published 11.1.3-4+wsh11 has neither:

- The interrupt. With 0018's `intr` 9 Linux takes a software interrupt (openbios 0034): SBus level 5
  stays masked, `cs4231` counts 0 interrupts, the first 8,192-byte buffer plays (46 ms) and
  `soundtest` fails with EIO. With 0034 (`0x39`) the interrupt arrives.
- The codec's INT bit. `snd_cs4231_sbus_interrupt()` returns `IRQ_NONE` unless bit 0 of the codec
  status register (offset 8) is set, before it reads or clears the APC CSR. Before 0124 the model
  kept that register at 0, so the APC interrupt was never cleared, the level interrupt came back at
  once (the trace repeated `cs4231_mem_readl_reg read reg 2: 0x00000000` with the mask set and
  cleared), and after a few thousand rounds QEMU stopped with `Trap 0x02 (Illegal Instruction) while
  interrupts disabled` in the kernel's trap entry (`tsetup_patch2`, nested faults from
  `do_sparc_fault`). 0124 sets INT and I24's PI with the APC's PI and PMI; Linux clears them by
  writing I24 at the end of its handler. The interrupt line follows the APC alone: SunOS and Solaris
  don't clear INT (a SunOS 4.1.4 trace has no access to the status register or I24; Solaris wasn't
  traced).

With both, the unchanged `kernel-fb` reports `WISP-SOUND ... ok=1`, `/proc/interrupts` (a local
debug print, not in the repository) shows 23 `cs4231` interrupts, and the trace has 24 status reads
(23 with INT set, one 0) and 23 raises of SBus level 5 (`slavio_set_irq ... irq 11 -> pil 9 level 1`):
no storm. The tone in the WAV is 440.005 Hz for 1000.00 ms on both channels. The original whole-capture check failed
(1039-1042 ms, 424 Hz, five runs): some 150 frames of old samples follow the tone after about 36 ms.
Linux stops the DMA when its last period has played (it zeroes the counts, then pauses and clears
`PDMA_GO`); by then the APC has taken part of the next ring period, which 0032 played out after the
stop. SunOS and Solaris stop at PMI, with nothing taken ahead. pve-qemu 0128 keeps what the APC took
in a FIFO in the model until the codec clock gets to it, and a driver stop drops what lies past the
codec's position, and the address and count read as the codec's position, so Linux stops at the
interrupt after its last period. Lab, 2026-11-23, with 0001-0129 and openbios 0034, `sound.py
--arch sparc32`: before 0128 (two runs) 36.0-36.3 ms of silence, then a 153-154-frame tail. With it
(five runs): the 1000.00 ms tone (440.005 Hz, 44,100 frames), 22.2 ms of the silence Linux pads its
last period with, then no tail in one run and 8, 12, 15 and 110 frames (at most 2.5 ms) in the
others: what the codec plays between that interrupt and Linux's stop under TCG, which the real chip
also plays for the driver's interrupt latency. `sound.py` reports them as a short tail. SunOS 4.1.4
(3 runs) and Solaris 2.6 (`audioplay -v 100`, 2 runs) with 0128: 2.56 s of u-law at 400 Hz, then a
40-byte sound, half periods 55-56 samples, no gap, clean power-off, no `interrupt not serviced`.
Solaris played the 40 bytes every time; SunOS in one run of three (also before 0128: there the
40-byte buffer is loaded and SunOS stops it 3.4 ms after PEN, before the next audio callback in
which the APC would take it; the race noted below). 0126 also clears I24's PI, CI
and TI on a status register write, as the datasheet says (0124 cleared INT only). Linux clears the
flags through I24 in its interrupt handler and writes the status register only when it opens,
closes or probes the codec.

SunOS 4.1.4 and Solaris 2.6 with 0124, with 0034 and with the published firmware (3 s of u-law at
400 Hz, then 40 bytes with `dd`): the same as before, 3.05-3.08 s and 3.24-3.28 s command time, no
gap (half periods 55-56 samples; 53-57 at Solaris' join of the two sounds), no `interrupt not
serviced`, clean power-off. On SunOS the trailing 40 bytes are in the WAV in some runs and not in
others (3.005 or 3.000 s), with 0124 (two of five runs) and without it (two of three).

`dd` never closes its output file, so `/dev/audio` is closed at exit, and SunOS 4.1.4 does not
play everything still queued then. A SunOS `trace` of `dd if=p of=/dev/audio bs=40` ends with
`close` of fds 0-2 and `exit`; the audio device is fd 4. Lab, 2026-11-24: 16,000 bytes of u-law with
a block number in each 40-byte block, a `wav` audiodev at 8000 Hz stereo s16, the blocks decoded
from the file. The WAV data length and the first-to-last non-silent span are the same in every run:
the `wav` backend gets only what the codec plays. At 44.1 kHz (the lab's `AUDIO=wav`, a plain tone)
0001-0138 gave the same: 1764.9 ms with `dd bs=40`, 1999.9 ms with 400 x 40 and 1 x 16,000 bytes
and `close()`.

| Writer | QEMU | Blocks in the WAV | WAV | Guest time |
| --- | --- | --- | --- | --- |
| `dd bs=40` | 0001-0138; 0122 and 0126 without 0128; 0122 alone; LEMU `c92620599a` | 0-352 (47 lost, 1,880 bytes) | 1765.0 ms | 1.7 s (`time`) |
| `dd bs=40` | without 0122 | 0-351 (48 lost) | 1760.0 ms | 3.5 s |
| 400 x 40 bytes, `close()` | 0001-0138; 0122 alone; LEMU | all 400 | 2000.0 ms | 2014-2015 ms |
| 100 x 160, 1 x 16,000, `close()` | 0001-0138 | all 400 | 2000.0 ms | 2015 ms |
| 400 x 40 bytes, exit without `close()` | 0001-0138; LEMU | 0-352 (47 lost) | 1765.0 ms | writes 9 ms |
| 1 x 16,000 bytes, exit without `close()` | 0001-0138 | none | 0 | writes 4 ms |

The model plays every buffer it is given: the trace has 353 buffer loads in the `dd` runs, then
SunOS pauses the APC, reads the counts and clears PEN. With `close()` the call returns when the
sound has played and the APC runs to PMI. The trailing 40 bytes above are written with `dd` too,
which may be why they are missing in some runs (not traced).

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
| SS-10 | OpenBIOS | default | 256, 512 | installer; scripted install (~8.5 min) boots to login; through PVE the install targets `sol26-ss10` and `sol7-ss10` (512 MB, 2026-11-19, pve-qemu-kvm 11.1.3-2+wsh25: 15.6 and 12.3 min with `--check`, the stored disks boot-tested) |
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
| SS-600MP | Sun 600MP PROM (lab archive) | default, SuperSparc-40/50/51/60 | 256 | `qemu: fatal: Trap 0x01 (Instruction Access Fault)` within seconds, nothing printed; with pve-qemu `wsh/0120` (11.1.3-4 lab build) a silent loop in its power-on self test ("Sun's own SS-600MP boot PROM") |
| SS-4 | `ss4.bin` | default | 256 | `Probing ... at 2,0 SUNW,tcx Data Access Error`, `ok` (with and without a TCX) |
| LX | `lx.bin` | default | 64 | POST `ERROR : Unexpected Synchronous Trap Taken, Trap Type = 00000008`, then `qemu: fatal: Trap 0x03 (Privileged Instruction)`. With pve-qemu `wsh/0053` (lab build, in review) the POST passes its FPU tests and the PROM probes the SBus and stops at `ok` after `cgsix Data Access Error`; with `wsh/0056`-`0057` too it probes all slots and boots Solaris 2.6, NetBSD 9.3 and SunOS 4.1.4 over ttya with `-nographic` ("SPARCstation LX" below) |
| LX | `lx564.bin` | default | 64 | `initializing VME mmuData Access Error`, `ok`: a Themis LXE+ PROM that wants a VME bridge; with two empty slots in a lab QEMU it installs and boots Solaris 2.6 and SunOS 4.1.3_U1B ("SPARCstation LX with the Themis LXE+ PROM") |
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
| Solaris 2.5.1 CD (`CDROM_AS=hd`) | installer (terminal type question), OpenBIOS and `ss20_v2.25_rom` (-50); under OpenBIOS End User installs with its Maintenance Update and boots to login: the install target `sol251-ss20` (through PVE, 512 MB, 46.6 min with `--check`, 2026-11-19, pve-qemu-kvm 11.1.3-2+wsh25; the stored disk boot-tested). The SS-5 target keeps `ss5.bin` |
| Solaris 7 (3/99) CD | language question, SS-5 and SS-20; scripted End User install through PVE boots to login on both, on the 3G or the 9G disk (`lab.py install sol7-ss5`/`sol7-ss20 [--disk-size 9G]`, `e2e/sparc/README.md`, "Solaris 7, 8 and 9") |
| Solaris 8 (1/01) Installation CD | Web Start's first question (`Do you want to format /dev/dsk/c0t3d0?`), SS-5 and SS-20; it needs a Sun-labelled disk, a blank one ends in `No Hard disks found on the system.` Its reboot into the mini-root (`reboot -- <slice>`) loses the boot string under OpenBIOS (below, "Known gaps"); with `auto-boot?=false` and the slice booted by path, Web Start (command line mode) installs the Entire Group from Software 1 and 2 of 2 on SS-20, and it boots to login (`sol8-ss20`); the same on SS-5 with 256 MB (lab, 2026-11-19) |
| Solaris 9 DVD | language menu, SS-5 and SS-20; on SS-20 (and SS-5, lab, 2026-11-19) Web Start installs End User and the installed 32-bit kernel boots to login (`sol9-ss20`); 9 is the last release for sun4m, Solaris 10 dropped it |
| Solaris 8 2/02 Installation CD, Solaris 9 9/05 DVD | as 8 1/01 and 9, SS-5 (256 MB) and SS-20: Web Start installs (9/05 adds a license question, 8 2/02 words its CD prompts differently; `e2e/sparc/README.md`, "Solaris 8 and 9 on the SS-5") and the installed systems boot (`Generic_108528-13`, `Generic_118558-34`); install targets `sol8-ss5` and `sol9-ss5` (2026-11-19). On the SS-20 8 2/02 hung once in two lab runs after the mini-root came up |
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

### Red Hat Linux 6.2 on sun4m

Red Hat Linux 6.2 for SPARC (March 2000, kernel 2.2.14, anaconda 6.2, SILO 0.9.8) on the SS-5 and
SS-20 profiles with OpenBIOS, a serial console and the published packages (pve-qemu-kvm
11.1.3-2+wsh16): nothing to change in QEMU, OpenBIOS or qemu-server. What the guest finds:

- The CD's SILO (`cd.b`, an a.out) boots from the whole CD-ROM device: `boot .../sd@6,0`, not
  slice `d` (OpenBIOS: "No valid state has been set" for `sd@6,0:d`); OpenBIOS's `-boot d` /
  `cdrom` alias finds it too, but takes the first CD-ROM, which is the answer CD in the install
  target.
- Kernel: `ARCH: SUN4M`, `TYPE: SPARCstation 5`, `Fujitsu Swift` srmmu, the ESP as
  `ESP100A-FAST` (`sda` on target 3, `sr0`/`sr1`), `sunlance` with `net0`'s MAC, the Zilog ports
  with `Console: ttyS0` (OpenBIOS's `output-device=ttya`), a floppy controller it detects
  (`FDC 0 is a S82078B`; qemu-server offers no floppy on sparc), `cs4231` loaded at boot, and
  "Power off control detected": `poweroff` ends QEMU with 0.
- The installer runs on the serial console in text mode by itself ("using a serial console").
- SILO on the disk reads `second.b` through the PROM, and on sun4m that doesn't reach far: with
  `/` alone on a 3 GiB disk `second.b` was at byte offset ~2.1 GB and the first stage stopped after
  `S` (OpenBIOS: `File not found`; `ss5.bin`: `Program terminated`). A 32 MB `/boot` from cylinder
  0 boots under OpenBIOS by itself (`Trying disk:a`). Not narrowed down to where the limit is, or
  whether it is in SILO's first stage or in the PROMs' read path (the CD's install guide doesn't
  mention it).
- Times (TCG, a busy host): the installer's first screen ~30 s after SILO; the Base install 1.8-2.2 min
  on SS-5, ~1.4 min on SS-20; boot to `login:` ~20 s.

The install target (`redhat62-ss5`, `redhat62-ss20`) and how it is driven: `e2e/sparc/README.md`,
"Red Hat Linux 6.2".

### Debian GNU/Linux 4.0 on sun4m

Debian 4.0r9 "etch" for sparc (the netinst CD of May 2010; kernel 2.6.18-6-sparc32,
debian-installer of etch, SILO 1.4.13), the last Debian release for sun4m, on the SS-5 and SS-20
profiles with OpenBIOS and a serial console. What the guest finds:

- **The ESP needs `wsh/0038`** (pve-qemu-kvm 11.1.3-2+wsh20 and later). With pve-qemu-kvm
  11.1.3-2+wsh16 and wsh17 the kernel's old `esp.c`
  driver offlines the disk and the CD-ROMs right after loading ("Device offlined - not ready after
  error recovery"). It negotiates synchronous transfers per target: Select with ATN and Stop (one
  identify byte), Transfer Information with the 5-byte SDTR message in MESSAGE OUT, then, with the
  target in COMMAND, the CDB one byte at a time through the FIFO. QEMU kept the message bytes in the
  command FIFO (`cmdfifo_cdb_offset` 6) and `esp_cdb_ready()` compared the whole FIFO length (7 with
  the first CDB byte) with the CDB length (6), so the command went out after one byte; the disk
  answered ILLEGAL REQUEST (`asc 0x20`, the SDTR bytes taken as the CDB), REQUEST SENSE returned the
  pending unit attention, and the driver reset the bus until the midlayer gave up. The fix compares
  `len - s->cmdfifo_cdb_offset`; `do_message_phase()` already drops the extended message. With it
  (first a local build of `qemu-system-sparc`, then the published pve-qemu-kvm 11.1.3-2+wsh21),
  `sda` reads its capacity and `sr0` is
  `scsi3-mmc drive: 16x/50x cd/rw xa/form2 cdda tray`. Solaris, SunOS 4, NetBSD and Red Hat 6.2's
  2.2 kernel don't negotiate that way and never hit it.
- **The floppy drive:** QEMU's sun4m always has one (empty; qemu-server offers no floppy on sparc).
  2.6.18's floppy driver oopsed in `reset_interrupt` (NULL pointer, in keventd, "lock fdc"
  timeout) in about half of the runs, when debian-installer's partitioner opened `/dev/fd0`, and the
  guest then sat idle for good. Not narrowed down to the controller model; the install target hides
  the device instead (`e2e/sparc/README.md`, "Debian GNU/Linux 4.0").
- Kernel otherwise as Red Hat's: `ARCH: SUN4M`, Fujitsu Swift srmmu, `sunlance` with `net0`'s MAC,
  `ttyS0` as console, "Power off control detected" (`poweroff` ends the VM). 256 MB on SS-5:
  234 MB free to Linux, 47 MB of it highmem.
- SILO 1.4.13 from a 64 MB ext2 `/boot` at cylinder 0 boots by itself under OpenBIOS
  (`Trying disk:a`), `Linux` after SILO's 10 s timeout.
- Times (TCG, a busy host, three installs at once): install ~21 min, most of it fetching and
  unpacking the base system from `archive.debian.org`; boot to `login:` ~35 s.

The install target (`debian40-ss5`, `debian40-ss20`): `e2e/sparc/README.md`, "Debian GNU/Linux 4.0".

### OpenBSD 5.9 on sun4m

OpenBSD 5.9 (March 2016), the last release with the 32-bit sparc port, on the SS-5 and SS-20
profiles. It needs no QEMU, OpenBIOS or qemu-server change, but one thing of the VM's:

- **No keyboard ESCC: `-nographic`.** With a display (the lab's `-vga none`, or `-vga cg3`) QEMU's
  sun4m has the second ESCC with the Sun keyboard and mouse; OpenBSD attaches `zskbd0 at zs1
  channel 0: keyboard, type 5, layout 0x21`, then prints `stray interrupt ipl 0xc pc=...` (the ESCC
  level) again and again during autoconf and stops with `panic: crazy interrupts` (`strayintr` from
  `sparc_interrupt44c` in `cpu_configure`), the RAMDISK kernel of `cd59.iso` and the installed
  GENERIC alike, on both machines. With `-nographic` QEMU leaves that ESCC disabled (`disabled` =
  `!enable_graphics` in `sun4m.c`), `zskbd0` finds no keyboard and the kernel boots. qemu-server
  passes `-nographic` for `vga: serial0`/`serial1`, so a VM with a serial display works and one with
  `cg3` or `tcx` doesn't. Diagnosed this far: an `escc_*` trace shows the keyboard answering the
  driver's probe (reset `0xff 0x04 0x7f`, layout `0xfe 0x21`, command 11) and then the level-12
  interrupt raised and lowered for every console character; QEMU's ESCC trace events don't name the
  chip, so which pending condition OpenBSD's handlers don't claim isn't known yet. Solaris, SunOS,
  NetBSD and Linux run with the keyboard ESCC, so it is between OpenBSD's `zs`/`zskbd` and QEMU's
  keyboard channel. The QEMU wiki's "5.8: working with -nographic" fits.
- Boot: with a blank disk on target 3 OpenBIOS stops at `0 >`; `boot
  /iommu/sbus/espdma/esp/sd@6,0:d` loads OpenBSD's boot block (`OpenBSD BOOT 2.11`) and `bsd.rd` in
  ~5 s. `ss5.bin` boots the CD with `boot cdrom`. The installed disk boots by itself under OpenBIOS
  (`sd@3,0`, partition `a`, also with the 8 GiB auto layout's 111 MB root). Under `ss5.bin` the
  installed GENERIC kernel stops at `bpp0 at sbus0 slot 5 offset 0xc800000` (`data fault ...
  sfva=0x7c800000`, `panic: kernel fault`): the SS-5 PROM's tree has the parallel port `SUNW,bpp`,
  which QEMU's SS-5 doesn't emulate (OpenBIOS's tree has no such node; `bsd.rd` has no `bpp` driver);
  `boot disk -c` and `disable bpp` in UKC boot it. The SS-20 PROM's `bpp` (slot 15) attaches as
  "Unknown type", and the disk boots.
- Kernel: `mainbus0 at root: SUNW,SPARCstation-5`, `cpu0: MB86904 @ 170 MHz` (SS-20: `TMS390Z50 v0
  or TMS390Z55 @ 170 MHz`), `esp0` with `sd0` on target 3 and `cd0`/`cd1` on 5 and 6 (OpenBSD
  numbers the CD-ROMs in target order), `le0` with `net0`'s MAC, `audiocs0` on the SS-5,
  `power0 at obio0`, so `halt -p` powers the machine off ("attempting to power down...", QEMU
  exits) from `bsd.rd` and the installed system. No multiprocessor kernel exists for sparc: on an
  SS-20 with 4 CPUs the others are `cpu at mainbus0 not configured`.
- The installer: `cd59.iso` has no sets (the release has no `install59.iso` for sparc). The sets
  come from a second CD made on the node from the release's files (`answer_media.openbsd_sets()`);
  it needs Rock Ridge names, because 5.9's `cd9660` shows plain ISO 9660 names in upper case
  (`BASE59.TGZ`), which the installer doesn't take for sets. With `SHA256.sig` on the CD the
  installer checks the signature and each set, if it finds 512 MB free on `/tmp`, `/home` or
  `/usr/src` to copy them to (an 8 GiB disk's auto layout has that, a 3 GiB disk's doesn't).
- Times (TCG, one guest per host core): the questions ~1 min, the sets ~2-3 min (base, comp, man,
  game, 108 MB), the first boot to `login:` 2.5-3 min (host key generation), a later boot ~25 s; a
  100 MB `dd` on the disk 29-35 MB/s written, 49-57 MB/s read.

The install targets (`openbsd59-ss5`, `openbsd59-ss20`): `e2e/sparc/README.md`, "OpenBSD 5.9 on
sun4m".

### Older Sun releases on sun4m

Solaris 2.1, 2.2, 2.3 Edition II and 2.5 (HW 1/96), SunOS 4.1.2, 4.1.3 and 4.1.3_U1B, against the
first release Sun supports on each machine (SS-10: SunOS 4.1.3, Solaris 2.1; SS-20: 4.1.3_U1B, 2.3;
SS-5: 4.1.3_U1B with patch 101508, 2.3 Edition II). pve-qemu-kvm 11.1.3-2+wsh21, serial console,
lab first, then through PVE (qemu-server 9.2.19+wsh1). The full table, the times and the scenario
changes are in `e2e/sparc/README.md`, "Older Sun releases".

| System | Machine, firmware | Result |
| --- | --- | --- |
| Solaris 2.3 Edition II | SS-5 `ss5.bin`, SS-20 `ss20_v2.25_rom`, CD as a disk | installs (End User, Quick Install, ~5-6 min) and boots (~10-11 min through PVE); the targets until the package had 0019-0022 |
| Solaris 2.3 Edition II | SS-5 and SS-20 OpenBIOS with openbios 0019-0022, CD as a disk | installs (Quick Install, 5-6 min) and boots (`SunOS solaris 5.3 Generic_101498-02 sun4m`); targets `sol23-ss5`, `sol23-ss20` through PVE with pve-qemu-kvm 11.1.3-2+wsh22 (~9-10 min). The SS-20 with 2 and 4 CPUs too (below). From a `scsi-cd` the kernel can't mount root, as under `ss5.bin`. Before 0019: `Unhandled Exception 0x00000009` after the boot block |
| Solaris 2.4 HW 3/95 | SS-5 and SS-20 OpenBIOS with openbios 0019-0022, CD as a disk | installs (4-5 min) and boots (`SunOS solaris 5.4 generic sun4m`); targets `sol24-ss5` (until +wsh22 with `ss5.bin`), `sol24-ss20` (~8 min). The SS-20 with 2 and 4 CPUs too |
| Solaris 2.5 HW 1/96 | SS-5 and SS-20, OpenBIOS, CD as a disk | installs (~5 min) and boots; targets `sol25-ss5`, `sol25-ss20` (~9 min). From a `scsi-cd` the kernel hangs after its banner |
| SunOS 4.1.3_U1B | SS-5, SS-20 (and SS-10), OpenBIOS, 64 MB for the install | installs with the 4.1.4 scenarios unchanged (~2.5 min) and boots; on the SS-5 without patch 101508; targets `sunos413u1b-ss5`, `sunos413u1b-ss20` (~6 min) |
| Solaris 2.2 | SS-10 OpenBIOS with openbios 0019-0022, CD as a disk | installs (the 2.3 path: Quick Install, ~5 min) and boots (`SunOS solaris 5.2 Generic sun4m`); target `sol22-ss10` (~9 min) |
| Solaris 2.1 | SS-10 OpenBIOS with openbios 0019-0022, CD as a disk | the kernel configures its devices, then QEMU stops: `qemu: fatal: Trap 0x21 (Instruction Access Error) while interrupts disabled` at `pc f0014768` (`srmmu_mmu_flushctx`); the same with `-cpu TI-SuperSparc-40`. From a `scsi-cd`: `cannot mount root`. With pve-qemu `wsh/0047` (below; pve-qemu-kvm 11.1.3-2+wsh29 and later) it installs (Standalone Quick Install, End-User) and boots (`SunOS sol21-ss10 5.1 Generic sun4m sparc`); target `sol21-ss10` (~10 min) |
| Solaris 2.1, 2.2 | SS-20 `ss20_v2.25_rom` (-50), CD as a disk | the kernel starts, then `BAD TRAP: type=9 ... kernel read fault at addr=0x0`, `panic: Data fault`, on the SBus node the PROM leaves unnamed (64 and 256 MB). Named at the prompt (`PROM_NAME_UNNAMED=1`), 2.2's CD reaches its installer; 2.1 under `ss10_v2.25_rom` or `ss20_v2.25_rom` (on QEMU's SS-20) needs the QEMU change too, then installs and boots. With pve-qemu `wsh/0057` (lab, in review) the node has its name, and the 2.2 CD reaches its installer without `PROM_NAME_UNNAMED` |
| SunOS 4.1.3 | SS-10 and SS-20, OpenBIOS (32 or 64 MB, also `-cpu TI-SuperSparc-40`) | the CD's kernel probes the devices, then `BAD TRAP: cpu=0 type=29` (data access error) after `SUNW,fdtwo0`, where 4.1.3_U1B mounts its munixfs root: a bus error in a probe took the wrong trap (below). With pve-qemu `wsh/0049` (below; pve-qemu-kvm 11.1.3-2+wsh31 and later) it installs on the SS-10 with the 4.1.4 scenarios unchanged and boots (`SunOS sunos413 4.1.3 3 sun4m`); target `sunos413-ss10` (~6 min) |
| SunOS 4.1.3 | SS-20 `ss20_v2.25_rom` (-50) | `BAD TRAP: cpu=0 type=9` |
| SunOS 4.1.2 | SS-600MP, OpenBIOS | the kernel loads (`Boot: vmunix`, romvec version 3), then `Unhandled Exception 0x00000029` before its banner. With pve-qemu `wsh/0063`-`0065` and openbios 0028 (lab, 2026-11-21): installs with the 4.1.4 scenarios (`SERIAL_7BIT=1`, 64 MB, ~2.5 min) and boots (`SunOS sunos412 4.1.2 1 sun4m`, 256 MB; 512 MB to 2 GB boot too), `le0` answers ping; one CPU only (below). Target `sunos412-ss600mp` through PVE with qemu-server's SS-600MP profile (~7 min) |

**Solaris 2.1-2.4 under OpenBIOS (openbios 0019-0022).** Four gaps, one behind the other, each
found by booting the 2.3 CD (lab, pve-qemu-kvm 11.1.3-2+wsh21 with the patched `openbios-sparc32`
mounted over the package's):

1. The boot block on slice d (an a.out at 0x4000) is a little machine code around an FCode
   program, which it hands to `byte-load` through the romvec's Forth interpreter. The FCode reads
   UFS and loads `/ufsboot` with OBP 2.x words it looks up by name: `romvec` (else it uses
   0xffe80010, where those PROMs keep it: the `Unhandled Exception 0x00000009` at `0xffd076c8`,
   OpenBIOS's `@`), `(is` (the `(is ?` it printed) on `load-base`, `op-open`/`op-close`/`op-read`/
   `op-seek`, `adjust-header`, `init-program` on code it has already copied to its ELF addresses,
   `?go`. 0019 adds them (found with OpenBIOS's `CONFIG_DEBUG_OBP` output and `detok` on the
   boot block's FCode).
2. The 2.3 and 2.4 kernels' kernelmap is 0xfc000000-0xffd00000 (`Sysbase`/`Syslimit` in their
   symbol tables; 2.1's ends at 0xfe400000) and they panic with `can't remove OBP hole` on a
   mapping in `/virtual-memory` `available` that reaches past 0xffd00000: OpenBIOS's Forth heap at
   0xffce0000. 0020 moves the heap into the firmware's own 0xffd00000-0xfff00000.
3. Right after its banner the 2.3 kernel asks for the root's `name` with node 0, which OBP takes
   as the root; OpenBIOS said -1, and the kernel's buffer of that size ended in `BAD TRAP: type=9
   ... addr=fffff000`. 0021 maps node 0 to the root in the property calls.
4. 2.4 then panicked in 2 of 4 boots inside OpenBIOS (`addr=0`, `c@` under `obp_proplen`), called
   from its idle thread (`init_swift_idle_cpu` → `prom_getproplen` for `platform-pm`) with
   interrupts on: a second romvec call got into the Forth engine meanwhile. 0022 masks interrupts
   for every romvec call, as the sparc64 client interface does (0016).

Since pve-qemu-kvm 11.1.3-2+wsh22 (0019-0022 published) the targets run under OpenBIOS:
`sol23-ss5`, `sol23-ss20`, `sol24-ss5` (all three had the Sun PROMs before), the new `sol24-ss20`
and `sol22-ss10` (2.2's only sun4m machine), each installed twice through PVE with `--check`
(2026-11-19, e2e/sparc/README.md, "Older Sun releases"). OpenBIOS replaced the Sun PROMs in the
targets rather than adding variants: as reliable in these runs, no Sun firmware needed, and more than
one CPU on the SS-20. The scenarios accept OpenBIOS's end of a 2.3 install and of `init 5` (it
reboots: OpenBIOS's banner instead of `ok`).

**More than one CPU for 2.3 and 2.4** (SS-20, OpenBIOS, the targets' installed disks with `cores`
2 and 4 through PVE): every CPU on-line in `psrinfo`, 4 or 8 parallel `nawk` loops at 100% `usr` on
every CPU in `mpstat`, then 10 minutes of CPU and disk load on 4 CPUs (6 shell loops of `nawk` and
`cat /usr/bin/*`; `psrinfo` every ~5 minutes, all on-line), `init 5`: all passed, for both releases.
Idle at the login prompt the 4 vCPUs used 5% of a host core: these releases' idle loop doesn't spin
the way 2.5.1-9's multiprocessor idle loop does (which 0023-0024 of the QEMU patches halt).

Regression with the images `openbios/Dockerfile` builds from 0001-0023 (lab image of the published
package, ours mounted over its `openbios-sparc32`/`openbios-sparc64`): `smoke` 3/3, `idle` 13/13,
`sparc64` 9/9, `solaris10` 2/2, and OpenBSD 8.0's installed sun4u disk to `login:` (0023).

What it would take for the rest:
- **Solaris 2.1/2.2 on the SS-20 PROM, diagnosis (2026-11-20):** the node is QEMU's. Its SS-20
  puts an unimplemented device (reads 0) where the DBRI's FCode PROM would be (`sun-DBRI.prom`,
  SBus slot e); the Sun SS-20 and SS-10 PROMs make an SBus node for it without a `name` (`ls` in
  `/iommu/sbus`: `<Unnamed>`), and the 2.1/2.2 kernels strcmp its name: the traceback is
  `get_neighbors` (`$nowalgnd` in strcmp, `pc=0xf002b300`), `di_dfs` three levels deep,
  `impl_init_tree`, `startup`. Later releases don't mind. Named at the PROM prompt before `boot`
  (the lab's `PROM_NAME_UNNAMED=1`: `<phandle> <setter> execute " SUNW,DBRIe" device-name
  device-end`, with the setter that `see find-device` shows, since OBP 2.x has no word to select a
  node by phandle), the 2.2 CD boots to its installer under `ss20_v2.25_rom` with QEMU 11.1.3 and wsh/0001-0041 alone,
  and 2.1 gets as far as under OpenBIOS (below). Without the stub (a lab build that skips it) the
  probe of slot e by `ss10_v2.25_rom` faults (`Data Access Error`, `ok`), so the PROM wants something there; a
  QEMU fix would give the stub a minimal FCode header or name, not remove it. pve-qemu `wsh/0057`
  (in review) does that: the window holds an FCode program that makes the node a DBRI has (`name`
  `SUNW,DBRIe`, `reg`, interrupt; found on the LX, where SunOS 4.1.4 panics on the same node), and
  the 2.2 CD reaches its installer under `ss20_v2.25_rom` without `PROM_NAME_UNNAMED` (2026-11-21;
  2.1 not retried); Solaris 2.6 binds its `dbri` driver to the node and runs as before.
- **The Sun SS-10 PROM:** `ss10_v2.25_rom` doesn't get through POST on QEMU's SS-10 (`Cpu #0 Data
  Access Error` with the default CPU; `Probing Memory Bank #4 Data Access Error` with
  `-cpu TI-SuperSparc-50`, "SS-10 and SS-20"), but runs on QEMU's SS-20 with `-cpu
  TI-SuperSparc-50`, where it calls the machine a "SPARCstation 10BSX". The 2.1 results under a
  Sun PROM below are from that combination.
- **Solaris 2.1 on SS-10 (OpenBIOS), diagnosis (2026-11-20):** a QEMU matter, neither the firmware
  nor the machine model. The trap comes in the first context flush the kernel does, for a new
  process's context (0x80a, then 0x809, ...). `srmmu_l1setup` gives the context a fresh level 1
  table: it writes the table's address into the context table entry (`mmu_writeptp`), and only then
  copies the kernel's 1 KB of level 1 entries (`kl1pt`) into it. `mmu_writeptp` sees that the entry
  held a valid table before (`hat_kern_setup` points every context at the kernel's table) and
  flushes the context: `srmmu_mmu_flushctx` disables traps, writes the context register, flushes
  (`sta %g0, [0x300] 3`) and writes the old context back, all in one page of kernel text. Stopped
  there with the gdb stub (QEMU monitor `xp` for the walk): the entry for context 0x80a is
  `0x00ea5681`, a table at physical 0xea56800 whose entry for 0xf0000000 is still 0, while context 0
  maps the same page to physical 0xef10000. QEMU flushes its whole TLB on the context write, the
  next fetch (`pc f0014768`) walks the new context and fails, and with traps disabled
  `sparc_cpu_tlb_fill()` maps it to "neverland", whose fetch raises the instruction access error in
  error state. Solaris 2.2 does the copy first (its `srmmu_l1setup` calls `bcopy` before
  `mmu_writeptp`), so 2.2-2.4 never get there. The SuperSPARC runs this code (Sun shipped 2.1 for
  the SS-10): it doesn't need a new translation for the instructions that follow in the same page.
  The QEMU change, pve-qemu `wsh/0047` (qtest `wsh/0048`; first tested as a standalone patch on
  11.1.3 with wsh/0001-0041):
  when the context register changes, remember how the old context translates the page of the
  instruction that writes it; an instruction fetch in that page that fails to translate while traps
  are disabled uses that translation (execute only) instead of neverland. Only a case that used to
  stop QEMU changes. With it (lab, OpenBIOS 0001-0026, SS-10, 256 MB, CD as a disk) the 2.1 CD
  boots, `solaris-install-serial.py` installs it (2.1's own suninstall menus after sysidtool:
  Standalone Quick Install, End-User Cluster; 5 min, 3 of them copying packages), and the target's
  first-boot and check scenarios pass on the installed disk (`solaris-firstboot.py`,
  `solaris-boot-disk.py`); the held translation is used twice per new context (after the context
  write and after the flush), 52 times in a boot to `login:`, a few commands and `init 5`. The
  installed 2.2, 2.3 (SS-5), 2.4 (SS-20) and 2.5.1 (SS-5, SS-20) target disks boot the same with it,
  and never use it. Open: at boot 2.1 doesn't mount `/opt` and `/export/home` (`mountall` checks
  them, `mount /opt` by hand works), most likely its clock (the kernel warns about a "preposterous
  time" with QEMU's 2026 clock); not traced. Write-up:
  `upstream/qemu-sparc32-context-switch-ifetch.md`. Through PVE on the published pve-qemu-kvm
  11.1.3-2+wsh30 (qemu-server 9.2.19+wsh4, 2026-11-20): `lab.py install sol21-ss10 --check` passed
  3/3 (three at once, 9.7-10.1 min: install 5.3 min, first boot 2.9-3.3, check 1.2-1.3), so
  `sol21-ss10` is an automated target (e2e/sparc/README.md, "Older Sun releases"). Again on the
  11.1.3-3 series (pve-qemu-kvm 11.1.3-3+wsh6, qemu-server 9.2.20+wsh3, 2026-11-21): 2/2 passed (two
  at once on a busy host, 11.2-11.7 min), so `wsh/0047` came over to the new base intact.
- **Solaris 2.1 under the Sun PROMs (2026-11-20):** the trap is the kernel's own (its context
  table), so the firmware makes no difference. QEMU's SS-20 with `ss10_v2.25_rom`, `-cpu
  TI-SuperSparc-50`, 256 MB, CD as a disk, `PROM_NAME_UNNAMED=1`: without the change the CD's kernel
  and the installed disk stop QEMU with the same `Trap 0x21` at `pc f0014768`; with it
  `solaris-install-serial.py` installs (4.9 min), and first boot (1.4 min) and the check (1.3 min)
  pass (`SunOS sol21-ss10 5.1 Generic sun4m sparc`). The disk installed under OpenBIOS on the SS-10
  boots there too, and `ss20_v2.25_rom` boots the PROM-installed disk. The SPARCstation LX (lab
  QEMU, `feat/lab-lx564`) installs and boots 2.1 with the change as well.
- **Solaris 2.1 with 2 CPUs (SS-10, OpenBIOS, the change):** the installed disk stops QEMU at the
  second CPU's start: `Trap 0x21 ... while interrupts disabled` at `pc fbe78060`, `%o7` in
  `cpu_exists`, `%i7` in `cpu_startup`; not traced.
- **SunOS 4.1.3 (original), diagnosis:** the `BAD TRAP: type=29` after `SUNW,fdtwo0` is a probe.
  The kernel arms its fault catcher and reads kernel VA 0xff009000 (`ld [%o5]` at `0xf00a0970`,
  QEMU `-d in_asm`), which the QEMU monitor (`gva2gpa`, VM stopped at the trap) puts at physical
  `0xd.0108_0000` on the SS-10. QEMU has nothing there and answers with a synchronous data access
  error (trap 0x29), which this kernel's catcher doesn't take. (`-d unimp` also shows 64-bit reads
  of the MXCC error register, ASI 2 `0x01c00e00`, which QEMU doesn't implement; they come from the
  boot program and the trap path, not before the fault.) The address is a VME controller's: the
  CD's kernel is the generic sun4m one, which also runs the SS-600MP, and `mbconfig` -> `doprobe`
  -> `peekl` probes for VME controllers with `nofault` set. 4.1.3's `trap()` reaches the nofault
  path (the longjmp back into `peekl`) only for trap 0x09, the data access exception; it has no
  case for 0x29. 4.1.3_U1 added cases for 0x21 and 0x29, which is why 4.1.3_U1B boots. On the
  SuperSPARC a bus error on a read is a data access exception, the cause in the SFSR (FT=5,
  access bus error): a test on a real SS-20 (SuperSPARC-II) posted to the OpenBIOS list in 2013
  found "sbus timeout: read = Data Access Exception, write = Level 15 int". QEMU's
  `sparc_raise_mmu_fault()` (`target/sparc/ldst_helper.c`) sets FT=5 but raised trap 0x29 (or
  0x21 for a fetch) on every sparc32 CPU. The fix, pve-qemu `wsh/0049` (qtest `wsh/0050`): a CPU
  feature `buserr-access-exc` on the `TI-SuperSparc-*` models only, with which a bus error on a
  load takes trap 0x09 and on an instruction fetch trap 0x01, the SFSR and SFAR as before. What
  the hardware does for the rest isn't measured, so it stays as it was: stores keep trap 0x29 (no
  level 15 interrupt modelled), and so do the MMU bypass ASIs 0x20-0x2f, the MXCC stream and
  unimplemented ASIs; the microSPARC (SS-5, LX and the other microSPARC machines), TurboSPARC and
  LEON keep trap 0x29 for everything. With it (lab, 2026-11-20, a local build of 11.1.3 with
  wsh/0001-0050): the 4.1.3 CD (`Solaris_1.1.img`, 2048-byte sectors, as a `scsi-cd`) installs on
  the SS-10 with the 4.1.4 scenarios unchanged (`sunos-install-serial.py` Programmer at 64 MB,
  `sunos-firstboot.py`, `sunos-boot-disk.py` at 256 MB: `SunOS sunos413 4.1.3 3 sun4m`), 4 passes of
  4: two with the lab image's `openbios-sparc32`, two with the one of pve-qemu-kvm 11.1.3-2+wsh30
  (install 124-138 s, first boot 91-95 s, check 45-50 s). The CD's kernel takes the new trap 9 times before its installer (five reads
  of the VME controller registers at `0xd.0108_0000`-`0xd.0108_1000`, four of the empty SBus slots
  at `0xe.0000_0000`-`0xe.3000_0000`). The stock OpenBIOS of QEMU 11.1.3 boots the CD as well:
  plain QEMU 11.1.3 panics there in the same place, and the build with the patch gets to the
  installer's first question. Stored installed disks boot as before with it (their check scenarios
  on copies, the openbios of +wsh30), 34 of 34: on the SS-10 and SS-20 `sunos413u1b-ss20`,
  `sol22-ss10`, `sol23-ss20`, `sol24-ss20`, `sol25-ss20`, `sol251-ss20`, `sol26-ss10`,
  `sol26-ss20` (also with 4 CPUs), `sol7-ss10`, `sol7-ss20`, `sol8-ss20`, `sol9-ss20`,
  `netbsd93-sparc-ss20`, `netbsd111-sparc-ss20`, `openbsd59-ss20`, `debian40-ss20` and
  `redhat62-ss20`, each taking the new trap 4-17 times (the four empty SBus slots at every boot,
  and SunOS 4.1.3_U1B's VME probes); on the SS-5 `sunos414-ss5`, `sunos413u1b-ss5`, `sol23-ss5`,
  `sol24-ss5`, `sol25-ss5`, `sol251-ss5` and `sol8-ss5-prom` (`ss5.bin`), `sol26-ss5`, `sol7-ss5`,
  `sol8-ss5`, `sol9-ss5`, `netbsd93-sparc`, `netbsd111-sparc`, `openbsd59-ss5`, `debian40-ss5` and
  `redhat62-ss5`, which never take it (microSPARC-II). Write-up:
  `upstream/qemu-sparc32-supersparc-bus-error-trap.md`. Through PVE on the
  published pve-qemu-kvm 11.1.3-2+wsh31 (qemu-server 9.2.19+wsh4, 2026-11-21): `lab.py install
  sunos413-ss10 --check` passed 5 of 6 (5.9-6.1 min, install 2.2-2.4 min, first boot 2.5, check
  0.9; 10.5 min on a busy host); the other stopped in its first boot on a `duplicate IP address`
  console message from a second guest with the same address (the test setup, not the guest). So
  `sunos413-ss10` is an automated target (e2e/sparc/README.md, "Older Sun releases").
- **SunOS 4.1.2 on SS-600MP (2026-11-21, lab):** installs and boots on one CPU under OpenBIOS
  with pve-qemu `wsh/0063`-`0065` and openbios 0028; three gaps, one behind the other, found by
  booting the CD (a local build of 11.1.3 with wsh/0001-0060 and the new patches, `-M SS-600MP`,
  the default `TI-SuperSparc-II`, serial console):
  1. **Before the banner** (`Unhandled Exception 0x00000029`, `pc f80a6054`, OpenBIOS's trap
     handler: the kernel hasn't installed its own yet). `-d in_asm`: for machine type 0x71 the
     kernel reads and clears the SBus AFSR/AFAR (`0xf.e000_1000`), the ECC memory controller's
     fault registers (`0xf.0000_0008`-`0014`), sets its enable bit, then reads, changes (sets bit
     30, clears 31 and 28) and writes back the VMEbus interface's control register at
     `0xf.df01_0000` (and touches `+4`, `+8`), all with `lda`/`sta` in the MMU bypass ASI 0x2f.
     QEMU has nothing at `0xf.df01_0000`, and a bypass load that hits nothing keeps trap 0x29
     (`wsh/0049` changes only normal loads and fetches on the SuperSPARC). `wsh/0063`: an
     unimplemented device over that page on the SS-600MP. The banner follows (`SunOS Release 4.1.2
     (MUNIX) #1`, `cpu = SUNW,SPARCsystem-600TI,TMS390Z55`) and the installer's menu, but with no
     disk (`swap on ns0b`) or network: nothing under `espdma`/`ledma` attached.
  2. **No disk:** the kernel walks the tree by node names and knows the ESP's DMA controller as
     `dma`. Renamed at the OpenBIOS prompt (`" /iommu/sbus/espdma" find-device " dma" device-name`),
     it attaches `dma0 at SBus slot f 0x81000`, `esp0`, `sd0` and `sr0`. Openbios 0028 does that on
     machine ID 66, with the esp and sd nodes and the aliases under `/iommu/sbus/dma/esp`; the
     scenarios boot by path through `_sparc32.esp(v)`.
  3. **No network:** an `le` node directly on the SBus (made at the prompt) attaches, but
     `ifconfig le0` says `le0: not used - unsupported SBus card for this architecture!`. The 600MP's
     lance works in a buffer memory of its own (`lebuffer`, slot f `0x40000`, the old
     `SS600MP_LEBUFFER` note in OpenBIOS's `sbus.c`), and 4.1.2's `le` driver wants that on sun4m.
     `wsh/0064` gives the SS-600MP's lance 128 KB of RAM there as its own address space (its 24-bit
     addresses are offsets in it) and its interrupt without the ledma's enable bit; openbios 0028
     names the node `lebuffer`. `lebuffer0 at SBus slot f 0x40000`, `le0 at SBus slot f 0x60000 pri
     6`, and `ping 10.0.2.2` over user networking answers.

  Then `sunos-install-serial.py` installs it (Programmer, 64 MB, the 4.1.4 scenarios unchanged
  apart from the ESP path; 109-166 s), and `sunos-firstboot.py` and `sunos-boot-disk.py` at 256 MB
  pass (`SunOS sunos412 4.1.2 1 sun4m`). One more difference from 4.1.4: its `getty` sends the
  console in 7 bits with even parity in bit 7 (`sunos412 login:` arrives as `\363\365\356o...`), so
  the scenarios run with `SERIAL_7BIT=1`, which masks bit 7 before the terminal (`serial.raw`
  keeps it). The CD's kernel and the installed GENERIC take no VME device and no floppy (QEMU's
  SS-600MP has none). Three passes from an empty disk; the last with the regenerated `pve-qemu.patch`
  built from scratch and the OpenBIOS `openbios/Dockerfile` builds from 0001-0028: install 109 s,
  first boot 91 s, check 44 s, and `ping 10.0.2.2` answered with `NET=user`.
  Regression (the same builds): `make check-qtest-sparc` 29 passed, 2 skipped, 1 failed (`qmp-test`'s
  `/sparc/qmp/oob`, which fails the same way without the three patches and failed before them in the
  lab), with the new `sun4m-ss600mp-test` 4/4; wisp on SS-5, SS-10, SS-20 and LX 4/4 (`status=ok`, the
  CRC checked); the stored `sol26-ss5` disk (Solaris 2.6, SS-5) and `sunos413u1b-ss20` disk (SunOS
  4.1.3_U1B, SS-20, the ledma path) boot to a root shell and `ping 10.0.2.2` answers on both.
  **More than one CPU:** with `-smp 2` the kernel sees `mod1 = TI,TMS390Z55 (mid = 9)` and starts
  it (`cpu1 at Mbus 0x9`), and CPU 1 panics in `check_cpuid` at once (QEMU then stops: `Trap 0xc8
  ... while interrupts disabled`, the halt after the panic, in error state). `-d exec,cpu` with
  `-dfilter` on that function: the per-CPU ID (1), the cached and TLB-flushed reads of it and the
  CPU number in `%tbr` agree; the last check, the module ID in bits 15-16 of the MMU control
  register (`lda [0] 4`, `>> 15 & 3`), reads 0 (`cpuid mid err`). The kernel expects the module ID
  there, as on the 600MP's Ross modules (it skips the checks when those bits are all ones); on the
  SuperSPARC they are other control bits, and QEMU has no Ross CPU model. So SMP needs the Ross
  module, or one of the cheaper ways in "Sun's own SS-600MP boot PROM" below: not done. (Sun's
  600MP PROM doesn't need a Ross module after all; see that paragraph.)
  **Through PVE (2026-11-22):** qemu-server's and pve-manager's SS-600MP profile ("Supported
  profiles"), built from this branch, with the published pve-qemu-kvm 11.1.3-3+wsh14 (it has
  `wsh/0063`-`0065` and openbios 0028; +wsh13 was the first), in the PVE test container from
  `e2e/pve/Dockerfile` with the lab: `lab.py install sunos412-ss600mp --check` passed twice (6.7 and
  6.5 min: install 151/135 s, first boot 165/168 s, check 61/64 s; `SunOS sunos412 4.1.2 1 sun4m`, the marker, `le0` with
  `inet 10.0.2.15 netmask ffffff00`, the finished VM `scsi6: none,media=cdrom`, `boot: order=scsi3`).
  The installed disk then booted to the check's root shell with 512 MB (`mem = 507772K`), 1024 MB
  (`mem = 1032060K`) and 2048 MB (`mem = 2080636K`) through PVE (the profile's limit lifted in the
  test container for that); the profile offers 1024 MB at most, the wizard presets 256. Under
  OpenBIOS the SS-600MP draws its banner and prompt on cg3 and on TCX; 4.1.2 itself was run on the
  serial console only. So `sunos412-ss600mp` is an automated target (e2e/sparc/README.md, "Older Sun
  releases").
- **Sun's own SS-600MP boot PROM (2026-11-22, lab):** the lab's PROM archive
  has one 600MP image (512 KB, "sparcsystem 600 bootprom selftest v5.6"). Its strings name the CPU
  modules it knows: the Cypress/Ross 605 (`ross605`, the CY7C601/CY7C605 modules the 600MP first
  shipped with), the Ross 625 (hyperSPARC) and the TI SuperSPARC with or without its MXCC (`viking`,
  TMS390Z50/Z55), each with its own register and cache tests. So the PROM doesn't need a Ross model:
  QEMU's SuperSPARC is one of its modules, and what stops it is its power-on self test (POST).
  1. **Published pve-qemu-kvm 11.1.3-4+wsh4** (the lab image), `-M SS-600MP -bios <600MP PROM>`,
     256 MB: nothing on ttya or cg3, and within seconds QEMU stops with `Trap 0x01 (Instruction
     Access Fault) while interrupts disabled, Error state` (`pc f0000010`, the PROM's trap table;
     the fault itself at `f002c454`). The same with `-cpu TI-SuperSparc-40`, `-50`, `-51` and `-60`.
     `-d in_asm`: the PROM's MMU register test, run from the PROM in boot mode with traps off,
     writes a walking one through the writable bits of the MMU control register (ASI 4, register 0,
     mask `0x14783`). Bit 0 turns the MMU on, QEMU translates the next instruction fetch with no
     context table set up, and the fetch of the trap vector faults too. On the SuperSPARC the boot
     mode bit (bit 13) sends every instruction fetch to the PROM whether the MMU is on or not; data
     accesses are translated (Linux's `asm/viking.h`). QEMU kept fetches in the PROM only with the
     MMU off. pve-qemu `wsh/0120` (the CPU feature `boot-mode-ifetch` on the `TI-SuperSparc-*`
     models) and its qtest `wsh/0121`.
  2. **With `wsh/0120`** the PROM runs on, still silent (its POST routine prints to ttya only while
     bit 2 of the system control register at `0xf.f1f0_0000` is set, which QEMU never sets; probably
     the 600MP's diagnostic switch, not checked), and never leaves its CPU module tests. The next
     test writes and reads back the SuperSPARC store buffer's diagnostic registers (ASI `0x30` tags
     and `0x31` data as doublewords, then `0x32` control), which QEMU doesn't keep (reads give 0). On
     a mismatch the PROM's error path sets a flag in its scratch area at NVRAM offset `0x1834`, and
     the test loop then repeats the failing test (loop on error), with no message and no progress
     (about 10 minutes in the same test, cg3 blank).
  3. **Lab-only experiments** (not carried): with those three registers stored, the default
     `TI-SuperSparc-II` (with MXCC) next fails on the MXCC's stream data registers (ASI 2,
     `0x01c0_0000` on, which QEMU takes on stores but reads as 0); with `-cpu TI-SuperSparc-50` (no
     MXCC) it passes them and fails the I-cache tag RAM test (ASI `0x0c`, "wrong i$ stag"). With
     the four cache tag and data ASIs (`0x0c`-`0x0f`) stored too it leaves the CPU module tests and
     fails the board's counter-timer tests at `0xf.f130_0000` ("Can not toggle timer/counter bits",
     "Limit bit not set"), still silent and looping. The PROM's strings list more SuperSPARC tests
     after those (TLB RAM, MMU table walk, probe and flush, TLB lock, table walk ECC and parity
     errors, cache flash clear, MRU and lock, read miss and write hit) and board tests (ECC memory,
     I/O cache tags, VME loopback, register size checks of the lance, ESP and others); how many of
     them run without the diagnostic switch isn't known. Not tried: Cypress or Ross modules (QEMU
     has none), more than one CPU, the VME or I/O cache as the PROM sees them.

  **Cause:** not the CPU module type, not the MBus module IDs, and so far not the 600MP's VME,
  IOMMU or lebuffer: the PROM checks the SuperSPARC's diagnostic internals (boot mode, store
  buffer, cache RAMs, MXCC) and the board's counters in its POST, where QEMU models only what an
  operating system uses, and it loops on the first failure. The SS-20 PROM's POST, by comparison,
  passes on QEMU with `-cpu TI-SuperSparc-50` (no MXCC, "SS-10 and SS-20").
  **Scope:**
  - *Sun's PROM on a SuperSPARC SS-600MP:* medium to large. The diagnostic registers as storage are
    small each (the store buffer; the cache tag and data RAMs need the TMS390Z50 geometry), the
    counter tests are unknown, and each step needs a lab loop like the one above; tests that check
    cache behaviour through those registers (miss and hit, MRU, lock, flash clear) need a cache
    model behind them, which is large. A way to skip or shorten the POST wasn't found.
  - *A Ross or Cypress CPU model* (RT620/RT625 hyperSPARC or CY7C601/CY7C605): large. QEMU had
    name-only definitions ("Cypress CY7C601", "CY7C611", "Ross RT620", "Ross RT625": IU and MMU
    versions, nothing else) until it removed them in 2013 (`6a4e177114`, "only half
    implemented"); there is no Ross MMU control register layout (module ID in bits 15-18 on the
    RT625), no instruction cache control register (ICCR) and no Ross cache or flush ASIs. MAME's
    `sun4.cpp` lists the sun4m machines and has SPARCstation 10/20 entries but no hyperSPARC or
    Ross code (a code search), TME emulates sun2, sun3 and sun4c, and no qemu-devel thread with
    such a model was found; LEMU wasn't checked. Such a model also faces the PROM's Ross
    register and cache tests, so by itself it doesn't boot Sun's PROM either.
  - *What either would unlock:* Sun's PROM on the 600MP only after its POST passes. SunOS 4.1.2's
    second CPU needs the module ID in bits 15-16 of the MMU control register, or those bits all
    ones, where the kernel skips the check. On the SuperSPARC those bits are AC and TC
    (alternate and table walk cacheable), which a Sun PROM may set on a module with an MXCC;
    whether OpenBIOS setting them on machine ID 66 is enough is a lead, not tested (with 2 CPUs
    and the bits forced in a lab build, the 4.1.2 CD's MUNIX kernel lists `mod1` and reaches the
    installer menu but prints no `cpu1 at Mbus` line; the installed GENERIC kernel, which starts
    CPU 1, wasn't run). Older SunOS: 4.1.2 is the first release with sun4m (machine ID 66
    above), and the lab has 4.0.3C (sun4c) and nothing from 4.1.1, so nothing to gain. Solaris
    2.6's "This hardware platform is not supported" under OpenBIOS already runs on the
    SuperSPARC, so a CPU model isn't the obvious cause; not investigated.
  Regression for `wsh/0120`-`0121` (a local build of 11.1.3 with the whole series, lab):
  `make check-qtest-sparc` 32 passed, 2 skipped, 1 failed (`qmp-test`'s `/sparc/qmp/oob`, as
  before), `sun4m-boot-mode-ifetch-test` 6/6 (its SS-10 boot mode case fails without 0120);
  `sun4m-mmu-ctx-ifetch-test` and `sun4m-bus-error-trap-test` had kept boot mode on while turning
  the MMU on and now write the enable bit alone. The stored `sol26-ss20` disk boots to `console
  login:` under OpenBIOS and under the SS-20 PROM (`ss20_v2.25_rom`, `TI-SuperSparc-50`, `boot
  disk3`), whose output to its `ok` prompt is byte for byte the same as with the published build;
  OpenBIOS on the SS-600MP reaches its prompt and boots the SunOS 4.1.2 CD to the installer menu.
- **qemu-server profiles:** nothing new is needed for the targets added (SS-5 `ss5.bin`, SS-20
  `ss20_v2.25_rom`, OpenBIOS, `cd_as_disk`). A Sun PROM for the SS-10 would need QEMU to boot it
  first; then `'ss10_v2.25_rom' => { 'max-cpus' => 1 }` (and a `cpu` if it needs one) under
  `'SS-10'` in `$SPARC32_PROFILES`, the same in pve-manager's `sparc32Profiles`, and the hint that
  it doesn't run removed. The SS-600MP has a profile since `sunos412-ss600mp` (OpenBIOS only, one
  CPU, 1024 MB; "Supported profiles"); Solaris 2.6 still refuses the platform under OpenBIOS.

### SPARCstation LX with its own PROM (lab only)

Sun's LX PROM `lx.bin` (from the lab's PROM archive; like the other Sun PROMs it never goes into
this repository) on `-M LX`, measured 2026-11-21 in the lab with local builds of 11.1.3 (not a
package). Up to pve-qemu `wsh/0052`, and on plain QEMU 11.1.3, its POST stops at `FPU SP Trap
Priority <  Test` with `Unexpected Synchronous Trap Taken, Trap Type = 00000008` and QEMU aborts
(`Trap 0x03 (Privileged Instruction) while interrupts disabled`). The test divides by zero with all
IEEE traps enabled, then stores an FP register to a misaligned address: it wants the alignment trap
(7) on the store and the deferred fp_exception (8) on a later FP instruction, with the `fdivs` in
the FQ, as the microSPARC does; QEMU took trap 8 on the `fdivs` itself. pve-qemu `wsh/0053` (qtest
`wsh/0054`, in review) defers the trap for every sparc32 CPU ("QEMU fixes" above). With 0001-0054
the POST passes all its FPU tests (single and double precision CEXC tests, `Trap Priority >` and
`<`), finds 2 banks of 32 MB with `-m 64` (4 with `-m 128`), probes the SBus (`espdma esp sd st
SUNW,bpp ledma le` in slot 4, `mmcodec` in slot 2) and stops at `ok` after `cgsix Data Access Error`
in slot 3. POST errors that stay, as with the earlier QEMU: the MMU TLB/CAM and cache RAM/tag
pattern tests (QEMU has no diagnostic access to those arrays) and `PROC0 Counter/Timer Test`. The
SS-5 PROM's POST (`ss5.bin`) prints the same with and without 0053.

**The on-board SBus devices (pve-qemu `wsh/0056`-`0058`, in review).** The LX has a cgsix (GX) in
SBus slot 3, the DBRI audio chip in slot 2 and a parallel port in slot 4, all on the board; the PROM
carries their FCode (the PROM map and the detokenized cgsix FCode are in
[mdehling/sslx-vesa-mod](https://github.com/mdehling/sslx-vesa-mod), a reference for the layout;
nothing from it is in this repository) and probes the three slots on every boot, whatever the
console. With 0001-0055 (lab, 2026-11-21, `-d unimp` and a lab log of failed bus accesses):

- with `-vga none` (what the scenarios' `-nodefaults` with `NOGRAPHIC=1` gives) the slot 2 probe
  faults first: its FCode byte-loads the DBRI's own FCode PROM at slot offset `0x1000`, where QEMU
  had nothing, and the PROM prints `Probing ... at 2,0  Data Access Error` and goes straight to
  `ok`. That ends its start-up: no banner, no auto-boot, and `boot disk` from that `ok` gets
  `Data Access Exception` after the memory test. It isn't `auto-boot?` or the diag switch;
- with QEMU's default TCX in slot 2 the TCX's ROM answers there (an unnamed node with an `mmcodec`
  child), and the cgsix probe's first write (THC, slot 3 offset `0x301094`) faults instead:
  `cgsix Data Access Error`, `ok`, the result above;
- past both (with lab stubs) the PROM prints its banner and then takes another data access error
  writing the DBRI's reset bit (slot 2 offset `0x10000`);
- slots 0 and 1 (`0x30000000`, `0x40000000`) take the same error on their first byte, which the
  PROM expects of an empty slot (`Nothing there`).

0056 maps the three as unimplemented devices on `-M LX` (the cgsix's 16 MB at `0x60000000`, the
DBRI at `0x50000000` as on the SS-20, the bpp at `0x7c800000`, which NetBSD reads at attach), below
whatever `-vga` puts in slot 2. The cgsix node is then made from zeros (rev 0, 1 MB, 1152x900) but
nothing draws on it with `-nographic`: NetBSD 9.3 attaches `cgsix0` as a second display, Solaris
2.6's cgsix driver fails to attach (`drvconfig: Driver (cgsix) failed to attach`), SunOS 4.1.4
attaches `cgsix0` with no console on it, and none of them hangs. The DBRI's node was then still
made without a `name` or `reg`: the PROM byte-loads the DBRI's own FCode PROM at slot offset
`0x1000`, where QEMU read 0, and SunOS 4.1.4 panics on such a node (`BAD TRAP: cpu=0 type=9 ...
kernel read fault at addr=0x0` in its autoconfiguration; the CD's kernel too, and very likely the
4.1.3_U1B panic noted earlier). Named by hand at `ok`, the CD kernel got to its installer but the
installed GENERIC kernel still panicked in its `dbri` driver; with `reg` and `intr` added by hand it
booted. 0057 makes that window an FCode program of ours that gives the node what a DBRI's has
(`name` `SUNW,DBRIe`, `reg` slot offset `0x10000`, interrupt at SBus level 5): the PROM prints
`SUNW,DBRIe mmcodec` for slot 2, as a real LX does, and the drivers find no codec and do without
sound (SunOS 4.1.4 `dbri: DBRI Reg8 bad!`, `Audio: no Audio device found`; Solaris 2.6 `WARNING:
dbri: DBRI Reg8 bad!`; NetBSD 9.3 `dbri0: chip never acked WAIT`, `no codec detected, aborting`,
about 3 s at boot). It changes the SS-10/SS-20 PROMs' DBRI node the same way (below, "Older Sun
releases on sun4m"). qtest `wsh/0058`.

The PROM's NVRAM checksum fails on QEMU's NVRAM (`Incorrect configuration checksum`, `Setting
diag-switch? NVRAM parameter to true`), so at power-on it tests memory, tries `net`, fails (`Can't
open boot device`) and stops at `ok`, as `ss5.bin` does; `prom_boot()` types `boot disk` or `boot
cdrom` there. The scenarios need `NOGRAPHIC=1` (no keyboard, so the PROM reads ttya). POST errors as
above. Results with the 0001-0058 `qemu-system-sparc` (lab build of 11.1.3, 2026-11-21, `lx.bin`,
`-nographic`, one CPU):

| System | Media | Result |
| --- | --- | --- |
| Solaris 2.6 5/98 | CD (`scsi-cd`) | installs (`solaris-install-serial.py`, End User, 7.6 min) and passes its first boot (2.7 min), both with 0056 alone (before 0057); with 0001-0058 the disk boots and passes its check with 64 and 128 MB (1.9-2.2 min): `SunOS sol26-lx 5.6 Generic_105181-05 sun4m sparc SUNW,SPARCstation-LX`. `drvconfig` attaches `dbri` (no codec) and `bpp`, and the system keeps running |
| Solaris 2.6 | stored `install-sol26-ss5` (a copy) | the kernel boots, then `mount: /dev/dsk/c0t3d0s6 no such device` and it halts, as under the Themis PROM: the disk's `/dev/dsk` links name the SS-5's ESP path (slot 5 in OpenBIOS's numbering), the LX's is in slot 4 |
| NetBSD 9.3 | stored `install-netbsd93-sparc` (a copy) | boots to `login:` and passes `netbsd-boot-disk.py` with 64 and 128 MB (1.2 min); `cgsix0`, `bpp0` and `dbri0` (no codec) attach |
| SunOS 4.1.4 | CD (`sunos414-cd.iso`) | installs (`sunos-install-serial.py`, Programmer, 3.4 min), first boot (1.7 min) and check (1.3 min) pass with 64 MB, and the disk boots and passes with 128 MB: `SunOS ... 4.1.4 2 sun4m` |
| SunOS 4.1.3_U1B | CD (`sunos_4.1.3U1B.iso`) | installs with the 4.1.4 scenario (Programmer, 3.4 min), first boot (1.7 min) and check (1.4 min) pass with 64 MB: `SunOS ... 4.1.3_U1 2 sun4m`; the autoconfiguration panic seen before (without 0056-0057) was very likely the same DBRI node |

The lab commands (copies of the stored disks; `<lx.bin>` from the lab's PROM archive):

```sh
lab.py run scenarios/solaris-install-serial.py --out runs/s26-lx --var MACHINE=LX --var MEM=64 \
    --var BIOS=<lx.bin> --var NOGRAPHIC=1 --var ISO=<solaris_2.6_598_sparc.iso> \
    --var TEMPLATE=<sparc-SUN2.9G.raw.template.xz> --var HOSTNAME=sol26-lx
lab.py run scenarios/solaris-firstboot.py --out runs/s26-lx-fb --var MACHINE=LX --var MEM=64 \
    --var BIOS=<lx.bin> --var NOGRAPHIC=1 --var DISK=<the installed disk> --var ROOT_PASSWORD=wshlab
lab.py run scenarios/netbsd-boot-disk.py --out runs/nb93-lx --var ARCH=sparc --var MACHINE=LX \
    --var MEM=64 --var BIOS=<lx.bin> --var NOGRAPHIC=1 --var DISK=<copy of install-netbsd93-sparc.raw> \
    --var ROOT_PASSWORD=wshlab
lab.py run scenarios/sunos-install-serial.py --out runs/s414-lx --var MACHINE=LX --var MEM=64 \
    --var BIOS=<lx.bin> --var NOGRAPHIC=1 --var ISO=<sunos414-cd.iso> --var DISK=<a SUN29G_SUNOS4 disk>
```

`solaris-boot-disk.py` and `sunos-firstboot.py`/`sunos-boot-disk.py` the same way. `DISK` in
`solaris-install-serial.py` is the Solaris disk name (`c0t3d0`), so run outside PVE the image is
created as a file of that name in the working directory. QEMU underneath (`_sparc32.qemu_args`):

```sh
qemu-system-sparc -nodefaults -M LX -m 64 -bios lx.bin -boot c -nographic \
  -drive file=disk.raw,if=none,id=hd,format=raw -device scsi-hd,scsi-id=3,drive=hd \
  -drive file=cd.iso,if=none,id=cd,format=raw,readonly=on,media=cdrom \
  -device scsi-cd,scsi-id=6,drive=cd,physical_block_size=512 -net nic,model=lance
```

OpenBIOS on `-M LX` probes the same slots: with 0056-0058 the `sol26-ss5` disk boots and passes
its check (OpenBIOS puts the ESP in slot 5 as on the SS-5) and the 2.6 CD reaches the installer's
first question, as with 0001-0055; the only change in its output is one more `Invalid FCode start
byte` (for slot 4 in its numbering, at `0x60000000`, which read as a bus error before). The stored
`netbsd93-sparc` disk panicked there with and without 0056-0058 (`audiocs0` at `0x6c000000`: OpenBIOS
gave the LX the SS-5's CS4231 node, which the LX doesn't have; the install CD's kernel leaves it
unconfigured). Linux 7.3 (wisp, the tiny test system, `e2e/wisp/`) stopped on `-M LX` at its first idle
on the APC node OpenBIOS gave it at `0x6a000000`; OpenBIOS 0027 leaves that node out on the LX
and the Voyager, and 0029 the CS4231 node on every machine where QEMU has no codec (all but the
SS-5 and the SS-4). Measured 2026-11-21 on the lab host with `qemu-system-sparc` built from
pve-qemu 0001-0065 and OpenBIOS 0001-0029, on a copy of the stored `netbsd93-sparc` disk, `-M LX -m 64
-nographic`: with 0001-0028 the kernel panics 7 s in (`audiocs0 at sbus0 slot 4 offset 0xc000000 level 5
(ipl 9)`, `trap 0x29: pc=0xf002ab80 sfsr=0xb6 sfva=0x6c000000`, `panic:`); with 0029 nothing attaches in
slot 4, the disk boots to `login:` in 47 s, root logs in and `halt -p` ends it. The same disk on `-M SS-5`
with 0029 still attaches `audiocs0 ... : CS4231A` and `audio0`, and so does `-M SS-4`; `-M SPARCClassic`
has only the `power-management` node in slot 4 and `-M Voyager` nothing there, and both reach `login:`.
Solaris 2.6 on a copy of the stored `sol26-ss5` disk (`-M SS-5`, `-machine audiodev=` a `wav` backend)
attaches `audiocs` (`prtconf -D`) and 2 s of u-law written with `dd` to `/dev/audio` reach the wav file,
byte for byte the same file as with 0001-0028. With either firmware that `dd` had not returned 45 s
later (not looked into; the measurements under "Audio" used `audioplay`).

**In PVE (qemu-server and pve-manager, `feat/sparc-lx-pve-profile`).** `machine: LX` is a
sparc32 profile ("Supported profiles"): `bios: lx.bin` only (no OpenBIOS: it gave the LX the
SS-5's CS4231, on which the NetBSD disk panicked; OpenBIOS 0029 leaves the node out, the profile is unchanged), at most 128 MB, one CPU, `vga: serial0` (the
default when no display is set) or `none`, the built-in ESP and lance, no audio (DBRI). cfg2cmd
tests `sparc32-lx-*.conf` and `sparc32-ss5-lx-prom-error.conf`; the wizard sets the PROM and
`serial0` (with its socket) when LX is picked. Measured 2026-11-21 in the lab's PVE container
(qemu-server and pve-manager of the branch, pve-qemu-kvm 11.1.3-3+wsh4, `lx.bin` copied into
`/usr/share/kvm` by hand): `qm start` of the `sol26-lx` disk (64 MB), `boot disk` at `ok`, login
prompt after 81 s; the wizard's VM gets `bios: lx.bin`, `vga: serial0`, `serial0: socket`, 128 MB.

**The PROM file** goes into `pve-qemu-kvm` like the other Sun PROMs (`restore-sparc`, the
`sun-proms` extra). Without it QEMU stops at start (`could not load prom 'lx.bin'`).

**Auto-boot: the PROM's NVRAM** (fixed by the NVRAM volume, "The NVRAM kept in a volume" below;
the analysis that led to it follows). QEMU's `nvram_init()` (`hw/sparc/sun4m.c`) writes
OpenBIOS's layout into the M48T08: a CHRP system partition with the `-prom-env` variables from offset
0, a free partition after it, and the Sun IDPROM (machine type, MAC, host ID) at `0x1fd8`. The LX
PROM reads its own configuration from the same bytes, finds the checksum wrong (`Incorrect
configuration checksum`), writes its defaults, sets `diag-switch?` and so boots `diag-device`
(`net`), which fails, and stops at `ok`; the SS-5 and SS-20 PROMs do the same (`docs`: "Firmware
settings (NVRAM)"). Black-box dumps of the NVRAM (`pmemsave` at `0x71200000`) at QEMU's start, at
the first `ok` and after single `setenv`s (lab, 2026-11-21): byte 0 is an XOR checksum (each
`setenv` changes it by the XOR of the old and new value byte), byte 1 is `diag-switch?` (`0xff`
true, `0x00` false) and outside the checksum, the other variables sit at fixed offsets from `0x29e`
(`scsi-initiator-id`; `selftest-#megs` `0x2a2`; `auto-boot?` `0x2a7`; `boot-device` as a counted
string at `0x2a8`; `diag-device` `0x32c`; ttya/ttyb modes, `sbus-probe-list`, `input-device`,
`output-device` up to `0x5ad`). The range the checksum covers was not pinned down: bytes QEMU leaves
in the gaps between the variables change it, and two dumps fit no single contiguous range. After
`setenv diag-switch? false` and `reset` (the NVRAM survives a reset) the PROM boots the disk by
itself (Solaris 2.6 to its login prompt). So what auto-boot needs is a configuration with a correct
checksum, and two ways were weighed:

- QEMU writes a Sun-format configuration when `-bios` is a Sun PROM: needs each PROM's layout and
  checksum range (OBP 2.10 here, others on the SS-5 and SS-20), which are undocumented and would have
  to come from probing every PROM version; brittle, not done.
- The NVRAM kept across starts, as on a real machine: a block backend for the M48T59 (a machine or
  device property), and in qemu-server a small per-VM volume for it, like `efidisk0`/`tpmstate0`
  (allocation, migration, backup). PROM-independent, so the owner's `setenv diag-switch? false` (or
  `auto-boot?`, `boot-device`) would last. Done: pve-qemu `wsh/0059`-`0060` and qemu-server's
  `nvram0` ("The NVRAM kept in a volume" below).

Without the volume, as for the SS-5 and SS-20 PROMs: `boot disk` at `ok`, or `setenv diag-switch?
false` once per start (a reset keeps it).

**SunOS 4.1.4's `le0` after the first boot.** Not an LX or lance problem: the lab install ran without
`NET_IP` (`sunos-firstboot.py` writes the network files only with it), so the system has no
`/etc/hostname.le0`, `rc.boot` tries RARP (`le0: RARP timed out.`) and leaves `le0` configured but
down (`flags=40<RUNNING>`). `ifconfig le0 192.0.2.10 netmask 255.255.255.0 up` brings it up
(`flags=43<UP,BROADCAST,RUNNING>`) on the LX in PVE; that frames reach the bridge was not checked
(no peer on the lab container's bridge).

Still missing: a real cgsix model for a graphical console.

- **Memory:** the microSPARC-I's memory interface takes 128 MB (TMS390S10 reference guide: 27
  address bits, four banks of 32 MB) and its context table pointer holds physical bits 26:8, so
  with more RAM OpenBIOS's context table lands outside what the MMU can reach (`Trap 0x21`).
  pve-qemu `wsh/0055` (in review) caps `-M LX`, `SPARCClassic` and `SPARCbook` at 128 MB.

### The NVRAM kept in a volume (pve-qemu `wsh/0059`-`0060`, qemu-server `nvram0`)

So that the Sun PROMs boot by themselves after a one-time `setenv diag-switch? false` (the analysis
is under "SPARCstation LX with its own PROM", "Auto-boot"). In review, 2026-11-21; not in a package
yet. Owner note for upstream: `upstream/qemu-sun4m-nvram-backend.md`.

**QEMU (`wsh/0059`).** The sysbus M48Txx (`sysbus-m48t02/08/59`) has a `drive` property for its
NVRAM bytes; the clock registers at the end (from `0x1ff8` on the M48T08) are never loaded or
stored. The image is read at realize, and each byte the guest changes is written through
(`blk_pwrite` of one byte, only on a change, as `macio-nvram` does). The image must hold at least
the 8 KB; a larger one is fine (the first bytes are used, the rest is left alone); a read-only one
is loaded and not written. On sun4m, `nvram_init()`:

- **blank image** (all zero, as qemu-server allocates it): writes OpenBIOS's layout and the IDPROM
  as without a drive, and so into the image, once;
- **any other image**: leaves bytes `0`-`0x1fd7` alone and writes only the IDPROM (`0x1fd8`-`0x1fef`:
  format, machine type from `-M`, the NIC's MAC address, host ID, checksum) on every start. The
  IDPROM is the machine's identity, which PVE manages through `net0`; the Sun PROMs never write it
  and their configuration checksum doesn't cover it (the LX PROM auto-boots after a start with
  another MAC, lab, and a clone with a new MAC auto-boots in PVE). Decision: refresh it;
- **with `-prom-env`**: writes OpenBIOS's partitions on every start, image or not, so `-prom-env`
  applies as before (the lab install targets' `args: -prom-env auto-boot?=false`). Decision:
  override on every start, not only at init. Without `-prom-env` a restored image is not touched,
  also under OpenBIOS (qemu-server passes no `-prom-env` of its own, and OpenBIOS takes its boot
  device from fw_cfg, so its profiles behave as before). The alternative, merging `-prom-env` into
  the stored variables, was left out: OpenBIOS's system partition is only as big as QEMU makes it.

The M48T08 is the machine's child `nvram`, so `query-block` names the device of the drive
`/machine/nvram` (qemu-server's `qdev_id_to_drive_id` maps it to `nvram0`, which backup, block jobs
and the block stats need). Usage: `-drive if=none,id=nvram0,format=raw,file=nvram.raw -global
sysbus-m48t08.drive=nvram0`, or by node name with `-blockdev`. sun4u's `sysbus-m48t59` gets the
property too, unused (its board code is unchanged).

What the PROM writes (dumps of the image): only its variables and the checksum byte. After its
defaults and `setenv diag-switch? false` on a blank image, the LX image has `0xc8` at 0, `0x00` at 1,
QEMU's `system` and `free` headers still at `0x4` and `0x20`, the variables from `0x29e`, the IDPROM
at `0x1fd8`. So a test of the layout ("is this OpenBIOS's partition?") would misfire on a Sun
image; the design depends on blank/not blank and `-prom-env` only.

**qtest `wsh/0060`** `sun4m-nvram-test` (SS-5), 7 cases: no image (as before), blank image (QEMU's
contents, kept in the file, clock bytes zero), persistence across two QEMU runs with a guest write
and a clock register write (the write reaches the file, the clock isn't stored) and another MAC on
the second (only the IDPROM changes, its checksum valid), `-prom-env` over a Sun image (OpenBIOS's
partition back), a 16 KB image (the tail kept), `-blockdev` by node name with `query-block`'s
`/machine/nvram`, a read-only image. With 0001-0060 (lab build, 2026-11-21) `qtest-sparc`: 28 OK
(`sun4m-nvram-test` 7/7, `m48t59-test`, `prom-env-test`), 2 skipped, and the `qmp-test` `oob`
failure as before. `checkpatch.pl`: no style errors (only the missing Signed-off-by, as in the
other patches).

**qemu-server (`nvram0`).** A drive key like `tpmstate0`: `nvram0: <storage>:<volume>[,format=]`,
in `valid_drive_names` (so backup, restore, clone, move, migration, delete and unused-disk handling
see it) but not a boot device. Allocation as for the TPM state: `<storage>:1` makes a 4 MiB volume
(the size every storage can allocate; QEMU uses 8 KiB), raw or qcow2 by the storage's default; a
fresh volume is blank on the usual storages (on thick LVM it may hold old data, which the firmware
then treats as an invalid configuration and resets). `config_to_command` gives it a `-blockdev`
with `cache=writeback` (the firmware writes single bytes; the same reason as the EFI vars) and
`-global sysbus-m48t08.drive=drive-nvram0`, no `-device`. `assert_nvram` refuses it on anything
but `arch: sparc` (create, update, start). On a running VM adding and removing it stays pending
(hotplug tests). Restore maps `nvram0` lines (`restore_update_config`), live-restore preloads it
like the EFI disk, clone refuses another drive name for it. Tests: cfg2cmd
`sparc32-lx-sun-prom-nvram.conf` (raw), `sparc32-ss5-openbios-nvram.conf` (qcow2; the command is
the one without the volume plus the volume), `sparc64-nvram-error.conf`, `x86-nvram-error.conf`;
hotplug `sparc32-nvram-add.conf`, `sparc32-nvram-remove.conf`. `make test` in the build image: the
same two failures with and without the change (`floppy.conf`, `q35-floppy.conf`: the image's
libpve-storage-perl has no `floppy` content type).

**pve-manager.** Hardware → Add → NVRAM on sparc32 VMs only (hidden on other architectures,
disabled once the VM has one), `qemu/NvramEdit.js` (a storage selector, no size, a hint), a row
`NVRAM` in the Hardware panel, Disk Action → Move Storage while stopped, Remove leaves an unused
disk. The create wizard doesn't add it. Decision: no default; the alternative, the wizard adding
`nvram0` on the disk's storage when a Sun PROM is picked, is a small follow-up if wanted (it would
change every Sun PROM VM's layout and the e2e expectations).

**In PVE** (lab, 2026-11-21: the e2e container with the branch's qemu-server and pve-manager JS and
a 0001-0060 `qemu-system-sparc` bind-mounted, copies of the stored disks; each VM created with
`qm create ... --nvram0 local:1`, serial console):

| VM | First start | Next start, no input |
| --- | --- | --- |
| LX, `lx.bin`, Solaris 2.6 (64 MB) | `ok` after 27 s; `setenv diag-switch? false` | `login:` after 88 s |
| LX clone (`qm clone --full`, new MAC) | (the cloned volume) | `login:` |
| SS-5, `ss5.bin`, Solaris 8 (`sol8-ss5-prom`) | `ok` after 14 s; `setenv diag-switch? false` | `login:` after 46 s |
| SS-20, `ss20_v2.25_rom`, Solaris 2.6 (`sol26-ss20`, 512 MB) | `ok` after 21 s; `setenv diag-switch? false` | the PROM boots the disk by itself; QEMU then stops at `configuring network interfaces:` (before 0061, below) |
| SS-5 OpenBIOS with the volume (qcow2), Solaris 2.6 | `login:` after 59 s; the volume holds QEMU's layout | `login:` after 58 s |
| SS-20 OpenBIOS with the volume, Solaris 2.6 | `login:` after 57 s | `login:` after 58 s |
| SS-5 OpenBIOS without it | `login:` after 59 s | |

`vzdump --mode stop` includes `nvram0` (`drive-nvram0`), `qmrestore` and `qm clone --full` give
byte-identical volumes, `qm disk move ... --format qcow2` and `qm destroy --purge` work. The UI's
Add/Remove was checked in the same container (screenshots in the PR). Not tested: live migration,
backup of a running VM, snapshots with the volume, storages other than `dir`.

**SS-20 PROM: auto-boot and the lance DMA (pve-qemu `wsh/0061`-`0062`).** Before 0061, when the
SS-20 PROM booted the disk by itself, Solaris 2.6 got to `configuring network interfaces:` and QEMU
stopped with `Trap 0x29 (Data Access Error) while interrupts disabled` (pc `f00412f4`), with or
without the volume. It was not the auto-boot path as such: a `boot disk` typed at `ok` failed the
same way once the PROM had started with `diag-switch?` false (`setenv auto-boot? false` in the
volume, then `boot disk`; lab, 2026-11-21). What decides it is whether the PROM probed with
`diag-switch?` true in that QEMU process: only then does it write `0xff000000` to the ledma's
fourth register (`E_BASE_ADDR`, the upper 8 bits of the lance's 24-bit DVMA addresses; `-trace
sparc32_dma_mem_writel`: `write dmareg 0xc: 0x00000000 -> 0xff000000` during the probe, missing with
`diag-switch?` false). The earlier "typed `boot disk` works" runs had all started with
`diag-switch?` true.

What happened then (`-d int`, `-trace slavio_set_irq`, `-trace sun4m_iommu_*`): Solaris sets the
IOMMU range to 64 MB (`iostart` `0xfc000000`) and maps the lance's init block at DVMA `0xff40f000`;
its `le` driver never writes the register, QEMU had reset it to 0, so the lance asked for
`0x0040f000`, which indexes another, invalid IOMMU entry: `sun4m_iommu_bad_addr bad addr 0x40f000`,
the IOMMU's interrupt (bit 30, level 15) raised. Level 15 can't be masked; the kernel's handler at
`f0041cec` took it again and again (the `-d int` log ends in nested `External Interrupt 15` at the
same pc, `%sp` going down by `0xa8` each time) until a window overflow with traps disabled hit an
unmapped stack page: the `Trap 0x29` at `f00412f4`. On the LX the same kernel, also with a 64 MB
range and the register at 0, boots: no IOMMU error was seen there (not looked into further; the
fix gives it the right addresses too). The DMA2 description the QEMU file cites says the register
"defaults to 0xff". 0061 resets the ledma's register to `0xff000000` (the ESP channel's stays 0);
qtest 0062 checks the reset value on the SS-5, SS-20 and LX and has the lance read an init block
through a 64 MB IOMMU from `0xff400000`.

With 0001-0062 (lab, plain `qemu-system-sparc`, `-M SS-20 -cpu TI-SuperSparc-50 -m 512`, the
stored `sol26-ss20` disk, an 8 KB NVRAM image after one `setenv diag-switch? false`): three starts in
a row reach `login:` by themselves (61-65 s), `configuring network interfaces: le0.`, no trap.
Without 0061 the same image stops QEMU at every start. OpenBIOS writes the register itself
(`write dmareg 0xc: 0x00000000 -> 0xff000000` without 0061 too), which is why its profiles never
showed this.

Regressions with 0001-0062 (same lab setup, copies of the stored disks, each started without
input): OpenBIOS SS-20 (the packaged `openbios-sparc32`, `sol26-ss20`, 512 MB) to `login:` twice with
an NVRAM image and once without (56-57 s); the SS-5 PROM (`ss5.bin`, `sol8-ss5-prom`, 256 MB) after
one `setenv diag-switch? false` to `login:` twice (42-43 s); the LX PROM (`lx.bin`, Solaris 2.6, 64
MB) to `login:` twice (75-76 s); `qtest-sparc` 29 OK. Through PVE with `nvram0` since: "The SS-20
PROM through PVE" below. Not done: the network itself (the lab NIC had no host side: only `le0`
plumbing and the init block were seen), other Solaris releases on the SS-20 PROM.

**The `dbri` panic on reconfiguration boots under the SS-20 PROM (pve-qemu `wsh/0066`-`0067`).**
Any reconfiguration boot of Solaris 2.6 under the SS-20 PROM (`boot disk -r`, `touch /reconfigure`,
or the stored `sol26-enduser-ss20prom` disk's pending first boot) panicked once `drvconfig` loaded
`dbri`: `WARNING: dbri: DBRI Reg8 bad!`, then `BAD TRAP: type=9 ... addr=0 mmu_fsr=126 rw=1` in
module `dbri`, `panic: Data fault`. The SS-10 PROM (`ss10_v2.25_rom` on `-M SS-20`) did the same.
Ordinary boots don't load `dbri`, so they were fine. Found with kadb (`boot disk kadb -d`, deferred
breakpoints on the module, lab 2026-11-22) and `-d unimp`, comparing the SS-20 and the LX PROM
with the same Solaris 2.6:

- On both machines `dbri_attach` succeeds and starts the audio set-up from a timeout. Its first
  command (`mmcodec_init_pipes` calling `dbri_command`) reads REG8 (offset `0x20`), the command queue
  pointer, to see how far the chip has got. Behind 0057's FCode the registers were an
  unimplemented device: REG8 read 0, which is outside the queue, so the driver printed `Reg8 bad`
  and called its chip error routine (`dbri_panic`): reset the chip (`REG0` = 1, then `0xc`), then
  report the error to each of its 14 pipes through a pointer in each pipe's state.
- The SS-20 PROM gives the DBRI node `isdn-disabled` (and `speaker`, `input-microphone` and the
  other port properties; `.attributes` at `ok`); the LX PROM gives it none of these, but an `mmcodec`
  child. `dbri_attach` reads `isdn-disabled`, and with it `dbri_initunit` sets up only the two
  audio pipes (12 and 13): the pointers of pipes 0-11 stay null. The error routine read pipe 0's
  pointer, null, at its first step: the BAD TRAP, in the timeout thread (`callout_thread`), which
  is why the traceback ran through the kernel and not through attach. On the LX all 14 pipes are
  set up, the routine runs through, and each of the driver's further commands does the same (15
  `Reg8 bad` warnings) until it gives up.
- An `mmcodec` child added at `ok` changed nothing because `isdn-disabled` decides it, not the child.
  The register stub's reads were the trigger, not an interrupt (the fault ran in the timeout thread,
  and the stub can't raise one) or 0057's node, which the driver attached to on both machines.

0066 gives the registers a model (`hw/sparc/sun4m_dbri.c`, device `sun-DBRI`, still at priority
-1000): they keep what is written, REG0's soft reset clears them, and writing REG8, or REG0 with the
P bit (`0x8000`), makes the chip walk the command queue through the IOMMU, stepping over each
command by its length (one to three words by opcode) and following JUMP, until it stops on a
WAIT with REG8 on it. That is what the driver checks: it writes new commands over the WAIT, ends
them with a new WAIT and sets the P bit. The model moves no data and raises no interrupt, and the
PIO pins in REG2 read low, so the drivers still find no codec. With it Solaris 2.6 sets up its
pipes, gets no answer from a codec and goes without sound, without a warning, under all three PROMs
(`-trace 'sun4m_dbri_*'` shows the queue: IIQ, DTS, ten SDPs, SSPs, PAUSE). qtest 0067.

Tested in the lab (2026-11-22, plain `qemu-system-sparc` built from 11.1.3 with 0001-0067, copies of
the stored disks):

| Case | Before (0001-0062) | With 0066 |
| --- | --- | --- |
| SS-20 PROM, `sol26-ss20`, `boot disk -r` (256 MB) | BAD TRAP in `dbri`, panic | `login:` (79 s) |
| SS-20 PROM, `sol26-ss20` with `/reconfigure` | BAD TRAP in `dbri`, panic | `login:` |
| SS-20 PROM, stored `sol26-enduser-ss20prom` (pending first boot) | BAD TRAP in `dbri`, panic | through `Configuring the /devices directory` to its root password screen (115 s) |
| SS-20 PROM, `sol26-ss20`, `boot disk` | `login:` | `login:` |
| SS-10 PROM, `sol26-ss10`, `boot disk -r` | BAD TRAP in `dbri`, panic | `login:` (64 s) |
| LX PROM, Solaris 2.6 (LX install), `boot disk -r` and `boot disk` | `login:`, 15 `Reg8 bad` warnings at `-r` | `login:`, no warning |
| LX PROM, stored `sunos414` disk | `login:`; `dbri: DBRI Reg8 bad!`, `Audio: no Audio device found` | `login:`; `Audio: no Audio device found` |
| LX PROM, NetBSD 9.3 (`install-netbsd93-sparc`) | `login:`; `chip never acked WAIT`, `no mmcodec found`, `no codec detected, aborting` | the same |
| SS-5 PROM (`ss5.bin`), `sol8-ss5-prom` (no DBRI) | `login:` (0061's runs) | `login:` (61 s) |
| OpenBIOS, SS-20, `sol26-ss20` (no DBRI node) | `login:` (0061's runs) | `login:` (74 s) |

`qtest-sparc` with 0001-0067: 31 OK, 2 skipped, and the `qmp-test` `oob` failure as before (PVE's
patch turns off the OOB capability); `sun4m-dbri-test` passes 4/4 and fails against the 0001-0062
build. All 141 patches of the series apply to the pinned QEMU with `patch -p1 --fuzz=0`. Through PVE
(package) since: "The SS-20 PROM through PVE" below. Not tested: other Solaris releases under the
SS-20 PROM (2.2's CD, 0057's case, not retried), SunOS 4.1.x and Linux under the SS-20 PROM.

On a package without 0066, `exclude: drv/dbri` in `/etc/system` before the reconfiguration boot
avoids the panic (lab, the 0001-0062 build: `boot disk -r` to `login:`).

**The SS-20 PROM through PVE (pve-qemu-kvm 11.1.3-4+wsh2, qemu-server 9.2.20+wsh7, pve-manager
9.2.32+wsh11).** Both fixes above, 0061 and 0066, on a VM that PVE starts, with the published packages
(lab, 2026-11-22: the PVE test container built from the apt repository, `e2e/sparc/pve.Dockerfile`).
First the package: its changelog has #440 (0066), `qemu-system-sparc` has the `sun-DBRI` device, and
the ledma's fourth register reads `0xff000000` at reset (`xp /4wx 0xef0400010` at `-S` on `-M
SS-20`: `0xa0000000 0 0 0xff000000`), which is 0061. The VM: `machine: SS-20`, `bios:
ss20_v2.25_rom` (qemu-server adds `-cpu TI-SuperSparc-50`), 512 MB, `vga: serial0`, `nvram0: local:1`
(blank, 4 MiB raw), the lance on `vmbr0` (no host side), and a copy of the stored
`sol26-enduser-ss20prom` disk imported to target 3 (`import-from`, the stored disk only read). That
disk's first boot is still pending: a reconfiguration boot, then sysidtool's root password screen.
The disk was installed with the host name, network and time zone answered, so the root password is
the only first-boot question, and the lab's `login()` answers it (an empty password, as `matrix.py`
does for this disk); no pre-answered copy of the disk was needed.

`scenarios/sun-prom-nvram.py` through `pve_matrix.py pve`, case `sol26-ss20prom-nvram`, nothing typed
except as listed:

| Step | What happens | Time |
| --- | --- | --- |
| first start, blank volume | the PROM resets its NVRAM to defaults (`Setting diag-switch? NVRAM parameter to true`), runs the long memory test, boots the network (`le@f,c00000`), fails and stops at `ok`; `setenv diag-switch? false`, `boot disk` | `ok` after 18-25 s |
| the stored disk's first boot | `configuring network interfaces: le0.`, `Configuring the /devices directory` (the reconfiguration boot: `dbri` loads, no warning, no panic), the root password screen, `System identification is completed`, `console login:`; `eeprom` prints `diag-switch?=false`; `halt` to `ok` | 108-111 s from `ok` to the shell |
| `qm stop`, `qm start` | the short memory test, `Boot device: .../esp@f,800000/sd@3,0`, Solaris 2.6 to `console login:`, `le0` up, no `Trap 0x29` | 60 s from `qm start` (all three runs) |
| `reboot -- -r` | `Rebooting with command: -r`, the PROM boots `sd@3,0` with `-r`, `Configuring the /devices directory`, `console login:`, no panic; `eeprom` still `diag-switch?=false`; `init 5` powers the VM off (PVE ends QEMU); `/devices` has `SUNW,DBRIe@e,10000:sound,audio` and `audioctl` (the scenario checks them) | 66-76 s from `reboot` |

The whole case took 305-322 s; three runs in a row passed. A try before them showed that `init 5`
powers the SS-20 off through PVE (PVE ends QEMU) where the scenario had waited for `ok`, so the
scenario now uses `halt` before the `qm stop`. No QEMU patch was needed. The SS-10 PROM has no PVE
profile (`ss10_v2.25_rom` is refused on SS-10 and SS-20), so it stays covered by the plain-QEMU runs
above.

Without media, `e2e/tests/sparc-profiles.spec.ts` ("the SS-20 PROM with an NVRAM volume") checks
the same persistence in the e2e container: `qm showcmd` has the `-blockdev` with node `drive-nvram0`
and `-global sysbus-m48t08.drive=drive-nvram0`; the first start (blank volume) runs the long memory
test and the network boot and takes `setenv diag-switch? false` at `ok`; after `qm stop` and `qm
start` the PROM skips the long test, tries the blank disk (`Bad magic number in disk label`), then
the network, and `printenv` shows `false`. Checked by hand in the lab container with the same
commands; the Playwright test itself was not run there (no Node on the lab host).

Not tested through PVE: other Solaris releases under the SS-20 PROM, the network beyond `le0`'s
plumbing, live migration and snapshots with the volume.

### SPARCstation LX with the Themis LXE+ PROM (lab only)

QEMU's `-M LX` (microSPARC `TI,TMS390S10`) with `lx564.bin` from the lab's PROM archive, measured
2026-11-20 in the lab with local QEMU builds (11.1.3 with wsh/0001-0041; not a package). Sun's
`lx.bin` stopped QEMU in its POST up to `wsh/0052` ("SPARCstation LX with its own PROM" above).
`lx564.bin` is not a Sun LX PROM: it is the PROM of the Themis LXE+ (a VME board built around the
LX), "ROM Rev. 2.14 4.4", root node `THEMIS,LXE+`, banner `SPARCstation LXE+`. It expects an SCV64
VME bridge that QEMU's LX doesn't have.

**Stock QEMU.** POST runs (one `MMU Context Table Reg Test` error with QEMU's microSPARC, `Suspect
Swift Module`; harmless), then `initializing VME mmuData Access Error` and `ok`. The PROM stopped
before probing the SBus: `show-devs` has `/iommu@0,10000000/sbus@0,10001000` without children (no
`espdma`, `esp`, `le`), so `probe-scsi` and `boot` find nothing and `banner` gives `Data Access
Exception`. With `-d int` the fault is a physical store (`sta ... ASI 0x20`) to `0x7e0001e0`, the
SCV64's registers; after that (below) one more to `0x71360001`, the LXE+'s LED register
(`/obio/ledsmall@0,360000`).

**Lab QEMU change** (two `empty_slot`s in `hw/sparc/sun4m.c` for the LX: `0x7d000000`-`0x7fffffff`
for the VME bridge, `0x71360000` for the LED; reads 0, writes ignored; not in `pve-qemu.patch`). The
PROM then prints `initializing VME mmuerror`, its VME ranges and `THEMIS LXE+ is not a System
Controller`, probes SBus slot 4 (`espdma esp sd st SUNW,bpp ledma le`) and reaches its banner. The
kernels list `THEMIS,LXE+` as the CPU (`cpu = THEMIS,LXE+` from SunOS 4) and print `Out of range
register specification from device node <mcp>` (the VME node) at boot; nothing else differs.
`probe-scsi` lists all 8 LUNs on each target (the PROM ignores QEMU's "no such LUN"); the kernels
only use LUN 0. With `-vga none` the PROM reports a keyboard and takes input from it: `ttya io`
first (as `prom_boot()` does), or `-nographic` (`NOGRAPHIC=1`) for a PROM that reads ttya, which
SunOS 4's install needs (it reboots, and the PROM's input goes back to the keyboard).

| System | Media | Result (LX, 64 MB, serial console) |
| --- | --- | --- |
| Solaris 2.6 5/98 | CD (`scsi-cd`) | installs (`solaris-install-serial.py` unchanged, 7.2 min), first boot (2.4 min) and check (1.7 min) pass: `SunOS sol26-lx 5.6 Generic_105181-05 sun4m sparc sun4m` |
| Solaris 2.1 | CD as a disk | needs the context-switch change of `fix/sol21-trap21` too (a lab build with both): installs (2.1's suninstall, 4.9 min), first boot (1.9 min) and check (1.2 min) pass: `SunOS sol21-lx 5.1 Generic sun4m sparc`. `init 5` reboots instead of stopping (`rebooting...`, then `ok`) |
| SunOS 4.1.3_U1B | CD (`scsi-cd`), `NOGRAPHIC=1` | installs (`sunos-install-serial.py` with Sun PROM support, Programmer, 2.1 min), first boot and check pass: `SunOS ... 4.1.3_U1 2 sun4m` |
| Solaris 2.2, 2.3 Edition II, 2.4 HW 3/95, 2.5 HW 1/96, 2.5.1 11/97, 7 3/99 | CD as a disk (7: `scsi-cd`) | the CD boots to the installer's first question (`solaris-boot-cd.py`, 45-72 s); installs not run |
| Solaris 2.4, 2.5.1 | CD (`scsi-cd`) | `Cannot mount root on .../sd@6,0:d` (2.5.1: `:b`), `panic: vfs_mountroot`, as on the other machines |
| Stored disks `install-sol26-ss5`, `install-sol26-ss10`, `install-sol251-ss5` | a copy each | the kernel boots, then `mount: /dev/dsk/c0t3d0s6 no such device` and the system halts (`/usr/sbin/fsck not found`): the disk's `/dev/dsk` links name the SS-5's or SS-10's SBus path (the LX has the ESP in slot 4); `boot disk -r` the same. A disk installed on the LX boots |

- **Memory:** QEMU's LX takes up to 256 MB; the PROM probes 8 banks of 32 MB. 64 and 128 MB boot
  the installed 2.6; with 256 MB its kernel stops QEMU right after the banner (`qemu: fatal: Trap
  0x21 (Instruction Access Error) while interrupts disabled` at `pc f005d2a8`; not traced). The
  real LX takes at most 96 MB, the microSPARC-I chip 128 MB, which pve-qemu `wsh/0055` (in review)
  makes QEMU's limit for the microSPARC-I machines (above).
- **For PVE** (not done): a pve-qemu patch with the two slots (better: an `LX` variant or machine
  option for the LXE+, since a real LX PROM wouldn't want them), and in qemu-server the machine regex
  (`SS-\d{1,2}` doesn't match `LX`), an `LX` profile (`lx564.bin`, one CPU, 128 MB, no audio) in
  `$SPARC32_PROFILES` and pve-manager's `sparc32Profiles`, and `lx564.bin` in the `bios` list. The
  PROM itself goes where `ss5.bin` does: the owner adds it to the private `submodules/sparc`, and the
  `Makefile`'s PROM check and `scripts/check-qemu-extras.sh` list it, so the package puts it in
  `/usr/share/kvm`; it never goes into this repository. A catalogue target (`sol26-lx`) would fail
  `test_targets.py`'s profile check until qemu-server has the profile, so there is none yet.

### NeXTSTEP 3.3 and OPENSTEP 4.2 on sun4m

NeXTSTEP 3.3 and OPENSTEP 4.2 for Mach ran on single-CPU microSPARC II and SuperSPARC machines (NeXT's
list: SS-4, SS-5 85/110, SS-10, SS-20; no SMP, HyperSPARC or TurboSPARC). The QEMU wiki calls them
"partially working" on sun4m: they hang on disk access. They still do with our ESP fixes up to
`wsh/0039`, and the cause is known: QEMU's ESP raises its interrupt too early for NeXT's SCSI driver
(below). pve-qemu patch `wsh/0040` makes the sun4m ESP's interrupt come 500 us after the event; with
the whole series (0001-0041) both install on an SS-5 and boot to the Workspace. Lab only (no PVE
run: no package has 0040 yet), 2026-11-19, pve-qemu-kvm 11.1.3-2+wsh21 and +wsh22 (a rebuild with
the same patches) and local builds. 0040-0041 are published since pve-qemu-kvm 11.1.3-2+wsh24, with
qemu-server 9.2.19+wsh2 (the `esp-irq-latency` key) and pve-manager 9.2.31+wsh2 (the UI field);
on those packages `qm showcmd` of an SS-5 VM with the key passes `-global
sysbus-esp.irq-latency-us=500` and an x86 VM refuses it (2026-11-19). No NeXT install was run on
the published packages yet.

Media (both carry a Sun label, so OpenBIOS and OBP boot them): `nextstep33_risc.iso`, the NeXTSTEP 3.3
User CD for SPARC and PA-RISC (a SPARC + hppa kernel), and `Openstep-4.2-Intel-User.iso`, which
despite its name also carries SPARC and m68k (an m68k + i386 + SPARC kernel). Their drivers for sun4m:
`CG14FrameBuffer`, `CG6FrameBuffer`, `S24FrameBuffer` (the TCX), `SCSAController`, `SunLe`,
`TYPE5Keyboard`, `SUNMouse`, `SunAudio`. No cg3 driver: the TCX is the only QEMU framebuffer they
can use, and NeXT's S24 driver runs QEMU's 8-bit TCX (`Display: Mode configured: 1024 x 768
(RGB:256/8)`).

**How the install goes.** Everything is on the framebuffer console with the Sun keyboard: the kernel
doesn't use ttya even when OpenBIOS's `input-device`/`output-device` are ttya (only the firmware's
lines show there).

1. The CD: NeXT's `boot` (v3.3.4.17, v40.13.1) asks for the language, loads the kernel, and
   `/etc/rc.cdrom` asks three text questions (prepare to install, install on this disk, ready), runs
   `disk -i` (a NeXT label at sector 30; sector 0 gets a Sun label with only its magic and checksum,
   no slices or geometry), copies the base system (55 MB) and asks for Return to restart. 2-4 min.
2. The disk: Configure ("Summary of Devices": S24 Graphics Subsystem, SUN Mouse, Sun Lance Ethernet,
   Sun SCSI, Sun Audio, SUN TYPE5 Keyboard; Save), then the Installer's package list (all selected:
   NeXTSTEP 293 MB, OPENSTEP 532 MB; Return) and Restart. 6-15 min.
3. The disk again: the language and keyboard panel, then the Workspace, logged in as `me` (no
   password; root has none either).

The kernel waits for a network configuration server at each boot until Control-C. `sd0: Illegal
request; FATAL. op:Mode Sense` appears twice at the SCSI probe (QEMU's scsi-disk doesn't have a mode
page the driver asks for) and is harmless. The mouse works (QEMU's relative motion; NeXT accelerates
it, steps of 10 move about 9 pixels).

| System | Machine | Firmware | QEMU | CD boot | Install | Disk boot | Stop point |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS | wsh21 | language prompt in 40 s | hangs, 2 of 2 (disk preparation, base copy) | | ESP deadlock (below) |
| OPENSTEP 4.2 | SS-5 | OpenBIOS | wsh21 | language prompt | hangs while preparing the disk (1 of 1) | | ESP deadlock |
| OPENSTEP 4.2 | SS-20 | OpenBIOS | wsh21 | language prompt | hangs at `root on sd1`, before the first question (1 of 1) | | ESP deadlock |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS | wsh22 | language prompt | hangs at `root on sd1`, before the first question (1 of 1) | | ESP deadlock |
| OPENSTEP 4.2 | SS-5 | OpenBIOS | wsh22 | language prompt | hangs in `/etc/rc` after the kernel's banner, before the first question (1 of 1) | | ESP deadlock |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS | local, no delay | | hangs during the copy (1 of 1) | | ESP deadlock |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS (CD), `ss5.bin` (disk) | local, 500 us | yes | 3G and 1G disk: CD stage 2-4 min, packages 6 min (64 MB) | `ss5.bin` with `-v`: Workspace | |
| NeXTSTEP 3.3 | SS-5 | `ss5.bin` (the target's profile) | local, 500 us | yes (`boot cdrom`) | 2G disk, 256 MB: CD stage 3.5 min, packages 6 min | with `-v`: Workspace; 18 min from power-on | |
| OPENSTEP 4.2 | SS-5 | OpenBIOS (CD), `ss5.bin` (disk) | local, 500 us | yes | 3G disk: CD stage 4 min, packages 15 min | `ss5.bin` with `-v`: Workspace | |
| NeXTSTEP 3.3 | SS-20 | OpenBIOS | local, 500 us | yes | CD stage 2 min | no firmware boots it (below) | |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS, `ss5.bin` | local, 50 us | | CD stage passed once, then hung during the packages; under `ss5.bin` hung at the SCSI probe | | ESP deadlock |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS (CD), `ss5.bin` (disk) | 0001-0041, first version of 0040 (only the line late, STAT_INT at once) | yes | 3G disk: CD stage 2.5 min, then hung at 29% of the packages (497 MB, all selected) | | ESP deadlock (`pc` 0xf00c944c, PIL 4) |
| NeXTSTEP 3.3 | SS-5 | OpenBIOS (CD), `ss5.bin` (disk) | 0001-0041 | yes | 3G disk, 256 MB: CD stage 3.3 min, packages 6.6 min (497 MB, all selected) | `ss5.bin` with `-v`: language panel, Workspace | |
| OPENSTEP 4.2 | SS-5 | OpenBIOS (CD), `ss5.bin` (disk) | 0001-0041 | yes | 3G disk, 256 MB: CD stage 4.2 min, packages 8.5 min (532 MB, all selected) | `ss5.bin` with `-v`: language panel, Workspace | |
| NeXTSTEP 3.3 | SS-5 | `ss5.bin` (CD and disk) | 0001-0041 (off by default), through PVE: VM made by `qm create` with `machine: SS-5,esp-irq-latency=500`, qemu-server with the option | yes (`boot cdrom`) | 3G disk, 256 MB: CD stage 3 min, packages 7.2 min (497 MB, all selected) | `ss5.bin` with `-v`: language panel, Workspace | |

**The ESP deadlock.** Every hang has the CPU in a simple-lock spin (`ld [%l0]; cmp %o0, 0; bne`, at
0xf00c944c in the 3.3 kernel, 0xf00c9f54 in 4.2) with PSR.PIL 4, which is `esp0`'s level (`esp0 at
... pri 4`), for good: timer interrupts go on, the ESP is never touched again (`-trace esp_*`: the
last access is Enable Selection after the disconnect of a finished 8 KB write), no disk I/O. The
caller (the window's `%i7` and the saved frame) is the kernel's built-in ESP code `_esp_finish` (an
exported symbol), which calls the request's completion routine in the `SCSAController` driver, which
sends `-lock` (`_objc_msgSend`) to a lock object that is already held. The holder is the thread that
issued the request: it takes that lock, starts the command and releases the lock later, which on a
real SS-5 always happens before the target answers (milliseconds of seek and rotation). QEMU's ESP
completes the command in the register write that starts it (selection, the DMA transfer to a cached
image, message accepted) and raises the interrupt in the same instruction, so the whole
select-data-status-message-disconnect sequence runs from the first interrupt, at PIL 4, while the
issuing thread still holds the lock.

Shown with a local build (the lab host's pve-qemu tree with wsh/0001-0027 and an experimental change
in `hw/scsi/esp.c`, `qemu-system-sparc` mounted over the lab image's): `esp_raise_irq()` sets
`STAT_INT` as before but asserts the line from a `QEMU_CLOCK_VIRTUAL` timer N us later;
`esp_lower_irq()` and the soft reset cancel it. N = 0 hangs as the package does; N = 500 ran
every stage it was given without a hang: five CD stages (NeXTSTEP four, OPENSTEP one), three package
installs and three first setups to the Workspace; N = 50 hung
again (the package copy, and the SCSI probe under `ss5.bin`). A fixed delay is a model of the
target's latency, not a proof that 500 us is always enough.

**The fix, `wsh/0040`, and how to turn it on.** `sysbus-esp` has a property `irq-latency-us`, 0
(off) on every machine, so nothing changes unless a VM asks for it. NeXTSTEP 3.3 and OPENSTEP 4.2
need it at 500, no other guest does:

- in the web UI: Hardware → Machine, Advanced → "SCSI IRQ delay (µs)" = 500 (sparc32 VMs only);
- `qm set <vmid> --machine SS-5,esp-irq-latency=500` (the `machine` property string: qemu-server
  emits `-global sysbus-esp.irq-latency-us=500`; refused on other architectures; "qemu-server");
- QEMU directly: `-global sysbus-esp.irq-latency-us=500`.

It costs about 2 ms per disk command (the table below), which is why it isn't the sun4m default: the
first versions of this branch set 500 on every sun4m machine, and the owner turned that down (raw
reads 70 → 20 MB/s). The property has no `x-` prefix: VM configs carry it through qemu-server, so
it should stay stable. The
interrupt as a whole, `STAT_INT` in the status register and the line (one signal on the real chip),
comes from a `QEMU_CLOCK_VIRTUAL` timer that long after the event; the interrupt register and the bus
phase are set at once, so OpenBIOS, which polls the interrupt register, sees no change. Reading the
interrupt register before the timer fires takes the interrupt; the chip's reset command and a device
reset cancel it; a pending interrupt is migrated (subsection `esp/irq_pending`) and comes a whole
latency after loading.

The first version of 0040 did what the experiment did, only the line late and `STAT_INT` at once: its
first NeXTSTEP package install hung at 29%, in the same spin, with the property at 500 (checked in
`info qtree`). A driver that checks `STAT_INT` right after starting a command sees it end at once,
which no real target can do, so the status bit had to wait too. The other way, delaying only the end
of a SCSI command (data and status phases) as a disk's seek does, was not taken: `esp.c` ends commands
in many places, each would need its own deferral and migration state, while the interrupt has one
raise and one lower. The price is that every ESP interrupt comes 0.5 ms later, selection and bus
service included; the regressions and the disk numbers are below. A fixed delay is a model of the
target's latency, not a proof that 500 us is always enough: each system installed once with the final
0040. The diagnosis is about QEMU's own ESP, not LEMU code, so it can go to QEMU's issues
[#2620](https://gitlab.com/qemu-project/qemu/-/issues/2620) and
[#2674](https://gitlab.com/qemu-project/qemu/-/issues/2674), written by the owner
(`upstream/qemu-esp-irq-latency.md`).

**Regressions with the latency on every guest** (2026-11-19, the earlier revision of 0040 that set
500 on every sun4m machine, so every sparc32 case below ran with the delay; the lab host shared with
other agents and the `sparc lab` workflow, two to four guests at once; `qemu-system-sparc` and `-sparc64` built from the series
on Debian 13, mounted into the lab image built from main with the published pve-qemu-kvm
11.1.3-2+wsh22, and bind-mounted over `/usr/bin/qemu-system-sparc` in the e2e PVE image for the
installs). Install times: the catalogue's `minutes` for comparison, from quieter runs.

| What | Result | Time |
| --- | --- | --- |
| `matrix.py smoke` | 3/3 passed (twice: with the first version of 0040 and with the final one) | 2.8, 2.1, 1.3 min |
| `matrix.py idle` | 13/13 passed; idle QEMU at 2.4-5.9% of a core with the halts (Solaris 2.6 SS-5/SS-20, 2 and 4 CPUs, 2.5.1, SunOS 4.1.4, NetBSD 11.1), 100-198% with them off, no clock drift | 2.8-4.3 min each |
| `matrix.py machines` | 13/13 passed (SS-10/SS-20 CDs and disks, OpenBIOS and the SS-20 PROM, 512 MB, 2 and 4 CPUs) | 1.0-2.8 min each |
| `matrix.py smp` | 3/3 passed (`SOAK=600` with the `tar` through `compress` checksum: SS-20 with 2 and 4 CPUs, SS-10 with 2; Dhrystone speed-up 1.96, 3.09, 1.72) | 15-16 min each |
| `matrix.py sparc64` (sun4u has no ESP; `qemu-system-sparc64` from the same series) | 9/9 passed | 26 s-6 min each |
| `matrix.py bench`, `benchdisk` | all passed, latency on and off (the table below) | |
| `install sol26-ss5 --check` (OpenBIOS) | passed | 14.5 min (install 520 s, first boot 222 s, check 114 s; catalogue 12) |
| `install sol26-ss20 --check` (OpenBIOS) | passed | 14.3 min (504 s, 224 s, 112 s; catalogue 12) |
| `install sol24-ss5 --check` (OpenBIOS, `cd_as_disk`) | passed | 8.9 min (306 s, 141 s, 73 s; catalogue 8.2-8.3) |
| `install netbsd111-sparc --check` | passed | 7.5 min (243 s, 124 s, 71 s; catalogue 6.6-6.8) |
| `install redhat62-ss5 --check` | passed | 6.6 min (170 s, 138 s, 67 s; catalogue 5.3-5.9) |
| `install sunos414-ss5 --check` | passed | 10.3 min (374 s, 159 s, 58 s; catalogue 6, its install phase 2.2 min) |
| `install debian40-ss5 --check --gateway --dns` (the container's `vmbr0` NATed out) | passed with a public name server | 26.3 min (1356 s, 124 s, 74 s; catalogue 24) |
| the same with the lab host's LAN resolver as `--dns` | failed three times at "Configuring apt" ("Bad archive mirror", after the base system had been fetched), twice with the latency and once with it off: the name server, not the ESP | 19-20 min |
| `debian-install-sparc.py NET=user` (no PVE), latency on and off at the same time | both passed | 19.1 min, 18.4 min |

**Disk numbers, latency on and off.** The same binary twice at the same time on the same host, in
two lab containers: with the latency at 500 us and with it at 0 (the old behaviour, now the default), the cases of the `bench` and `benchdisk` matrices, one run each. The disk-bound numbers
move together; the CPU-bound ones (Dhrystone, Whetstone, nawk) moved by up to 30% either way between
the two runs, which is the shared host, not the ESP.

| Case | Raw read 64 MB (`bench.py` `read_s`, 64 KB blocks) | 64 MB write + `sync` | `lat_fs` 0 KB create / delete per s | Boot to login |
| --- | --- | --- | --- | --- |
| SS-5, OpenBIOS | 3.2 s (20 MB/s) vs 0.9 s (71 MB/s) | 2.4 s vs 2.4 s | 135 / 258 vs 327 / 774 | 129 s vs 121 s |
| SS-5, `ss5.bin` | (not in `bench`) | | 176 / 346 vs 622 / 1334 | 125 s vs 115 s |
| SS-10, OpenBIOS | (not in `bench`) | | 165 / 316 vs 823 / 1370 | 125 s vs 118 s |
| SS-20, OpenBIOS | 2.8 s (23 MB/s) vs 0.3 s | 2.4 s vs 1.9 s | 170 / 331 vs 547 / 1317 | 123-129 s vs 115-120 s |
| SS-20, `ss20_v2.25_rom` | 2.8 s vs 0.4 s | 2.7 s vs 2.2 s | 163 / 328 vs 593 / 1198 | 123-131 s vs 116-119 s |
| Solaris 2.5.1, SS-5, `ss5.bin` | (not in `bench`) | | (`lat_fs` times nothing on 2.5.1) | 84 s vs 80 s |

Each disk command costs about 2 ms more (four interrupts of 0.5 ms: selection, bus service, status,
disconnect): raw reads in 64 KB blocks fall to about 20 MB/s, synchronous metadata operations to
roughly a quarter to a third, and a boot takes 6-11% longer; the `bench-disk.py` runs took 4-32%
longer in all. Installs that write many small files feel it most: SunOS 4.1.4's install phase took
374 s against the catalogue's 132 s. 20 MB/s is still twice what the SS-5's fast SCSI bus (10 MB/s)
could carry. Not tried: a smaller latency, or deferring only the status interrupt (one interrupt per
command instead of four); either would need the NeXT installs again.

**With the final 0040 (off by default)**, the same day, `qemu-system-sparc` built from 0001-0041
mounted into the lab image without any `-global`: `smoke` 3/3 (2.6, 1.9, 1.1 min); `bench.py` on SS-5
with OpenBIOS: raw read 64 MB 0.8 s, write + `sync` 2.5 s, boot 116 s; `bench-disk.py` on the same:
`lat_fs` 849 creates / 1419 deletes per s, boot 119 s. That is the old speed (the 0-latency column
above), not the 500 us one. `qtest-sparc`/`qtest-sparc64` as before (40 OK, the two `qmp-test` `oob`
failures).

**Solaris 2.3 on the SS-20, once.** In the `install` matrix (GitHub run 44533778163, pve-qemu-kvm
11.1.3-2+wsh22) `sol23-ss20` booted its CD (as a disk, `sd@6,0:d`, OpenBIOS) to the kernel banner,
the usual `corrupt label - bad geometry` for the CD image (`Label says 1310720 blocks, Drive says
833944 blocks`: the image is shorter than the CD's label says; every passing 2.2-2.4 boot prints it
too) and `clock gained 11969 days`, turned the spinner 17 times, and then printed nothing for 900 s,
where a good boot prints `Configuring the /devices directory` after the same 17 turns (the kernel's
own disk I/O, mounting root and loading modules). The VM config was the target's (the same as
`lab.py install sol23-ss20` makes; the CD was the right device), and the target's other installs
through PVE passed (two before the matrix run, two after it). Not traced (only the console evidence is left; the VM was destroyed); it fits the ESP
deadlock above (the interrupt raised in the same register write, before the driver is ready, once
in a while), not proven. The lab's answer, until the ESP gets a latency: `solaris-install-serial.py`
fails a boot that shows no first prompt within `FIRST_PROMPT_TIMEOUT` (300 s; 35-55 s in the lab)
of the banner with "before the installer", and the Solaris 2.2-2.6 targets retry such a failure
once (`retry_on`; nothing is on the disk yet).

**Firmware.**

- OpenBIOS boots both CDs but not an installed disk: it loads NeXT's boot block, whose boot program
  (at 0x80000) stops with `Unhandled Exception 0x00000021` (instruction access) at 0x856f8 (3.3) or
  0x8a1bc (4.2), before its banner, on SS-5 and SS-20. OpenBIOS's `sun-parts` refuses a slice of size 0
  ("Partition size is 0"), and `disk -i`'s Sun label has none, but a full label written over it
  (slice a the whole disk) only moved the fault (0x85788). Not diagnosed further; the next step is
  OpenBIOS's `CONFIG_DEBUG_OBP` output for the boot program's romvec calls, to find the one that
  answers differently from the Sun PROM.
- `ss5.bin` boots the installed disk, but its boot graphics ("Boot Graphics" = "Yes" in
  `/usr/Devices/System.config/Default.table`) end in `Data Access Error` at `ok` when `boot:` times
  out, on both systems, with 64 or 256 MB. Typed at `boot:`, `-v` boots in text and everything after
  it works (Configure, the Installer and the Workspace draw on the TCX). Most likely the boot
  program draws its panel into a TCX plane that QEMU's 8-bit TCX doesn't have; "Boot Graphics" =
  "No" would avoid it in the guest (not tried).
- `ss5.bin` after its failed network boot: the first `boot disk` restarts the PROM (`Rebooting with
  command:`), as on the SS-20 ("cg3 and TCX"); `setenv diag-switch? false` first.
- `ss20_v2.25_rom` with the TCX: QEMU stops (`qemu: fatal: Trap 0x29 (Data Access Error) while
  interrupts disabled`, pc 0xf0002198) right after `boot disk`. With OpenBIOS unable to boot the disk,
  the SS-20 has no way to the second stage.
- `-a` (ask for the root device) with the CD's kernel: its `root device?` prompt takes no input,
  neither from the Sun keyboard nor from ttya, so the CD's kernel with root on the disk isn't a way
  around the firmware.

**Through PVE.** The profile exists (SS-5, `ss5.bin`, `vga: tcx`, 256 MB); the CD stage under
`ss5.bin` ran in the lab, so one firmware suffices. The catalogue lists `nextstep33-ss5` and
`openstep42-ss5` as blocked: a package carries `wsh/0040` now (11.1.3-2+wsh24), so what is left is framebuffer
scenarios (OCR of the text stage, the pointer for Configure's Save, `-v` at each `boot:`). From the
0001-0041 runs: tesseract can't read Configure's light grey panel (not even "Display"), so the
scenario has to find Configure another way (a fixed wait after the kernel's network prompt worked,
or the screen's shape); the Installer's end panel ("Restart") reads fine. The pointer starts near
(100,100) on both systems, and 40 HMP `mouse_move 10 10` plus 16 `mouse_move 10 0` put it on Save.
After `ss5.bin` restarts itself at the first `boot disk`, NeXT's 10-second `boot:` countdown can start
more than 30 s later: typing `-v` for 30 s was too short twice, 60-90 s worked.

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
| OpenBSD 8.0 | yes (`bsd.rd`), installer prompt in ~1 min | not tried | yes: base, comp, man, game from the CD, ~17 min after the questions (kernel relink included); through PVE 9-12 min (target `openbsd80-sun4u`) | with openbios 0023 (pve-qemu-kvm 11.1.3-2+wsh22 and later; before, the GENERIC kernel panics in its first firmware calls, below): `login:` in ~4 min (first boot, key generation), on ttya and on the VGA screen, DHCP on `hme0`, `halt -p` ends QEMU (exit 0); disk timeouts once ntpd ran (below) until pve-qemu `wsh/0045`; the target keeps ntpd on since |
| Debian 12.0 ports netinst | yes: GRUB menu (no timeout, Return boots), then "Select a language" in 52 s | not tried | no: partitioning (Sun label) and DHCP work, then the base system fails: `dpkg-deb` segfaults in `libc.so.6` while unpacking (below) | |
| Debian 13 ports netinst (snapshot 2026-06-11, Linux 7.0.12) | yes: GRUB menu, the installer's first screen in ~40 s | not tried | yes: preseeded, base system and the SSH server from deb.debian.org/debian-ports, GRUB on the disk, ~2.5 h (1024 MB; the network fetch under TCG is most of it); no `dpkg-deb` crash (below); target `debian13-sun4u` | yes: GRUB 2.14 (with openbios 0009 and 0011, below) to `login:` in ~3 min, DHCP on `enp2s0` (sunhme), `poweroff` ends QEMU, `reboot` comes back (openbios 0030) |
| FreeBSD 12.4 | yes: bsdinstall's console-type question in 59 s (`bootonly` and `disc1`); no interrupt storm (FreeBSD bug 239068) | not tried | yes: `bsdinstall script` from the installer's shell, kernel and base from disc1, ~10 min (target `freebsd124-sun4u`) | `login:` in 84-120 s, DHCP on `hme0`; `shutdown -p now` ends QEMU (exit 0) with openbios 0032, the reboot needs 0033, idle needs pve-qemu `wsh/0114` ("FreeBSD 12.4 on sun4u") |
| Debian 7.11 (wheezy) netinst and CD 1 | yes: SILO 1.4.14 from the CD (`Trying cdrom:f...`), Return at `boot:`, then "Select a language" (Linux 3.2.0-4) | not tried | yes, from CD 1 with a preseed file (target `debian7-sun4u`): the base system with SSH, 84 min to the reset in the lab's own QEMU, nothing fetched | yes: SILO boots `/vmlinuz` and its initrd, `login:` 152-164 s from QEMU start, DHCP and static on `eth0` (`sunhme`), `poweroff` ends QEMU (exit 0); `reboot` with pve-qemu `wsh/0112` ("Debian 7 on sun4u" below) |
| Ubuntu 9.04 server (jaunty) | yes: SILO 1.4.14, Return at `boot:`, then "Choose language" 31 s later (Linux 2.6.28-6; the boot is `quiet`) | not tried | not tried | |

**X on std VGA (measured).** NetBSD 11.1/sparc64 ran ctwm 4.1.0 and xterm 397 at 1024×768,
8-bit PseudoColor (X.Org 1.21.1.25, wsfb 0.4.0, pixman 0.46.4). The run used one TCG CPU,
1024 MB and OpenBIOS 1.1 from pve-qemu-kvm 11.1.3-2+wsh16 on 2026-11-23/24 UTC.

| Test | Result |
| --- | --- |
| Warm `startx` to visible xterm | 29.03 s from sending the command on serial to the first QMP frame with the cyan xterm. The preceding frame at 28.82 s still lacked the window. |
| Scroll 2,000 lines (134,000 bytes) | 0.38 s in a 100×56 xterm with the 6×13 font, 4.00 s on the 85×34 wscons VGA console. Guest `time -p` reported 0.35 and 3.93 s real, respectively. |
| Guest CPU while scrolling | One-second `vmstat` intervals averaged 61% user, 39% system, 0% idle across 30 consecutive xterm scrolls (5 samples). One console scroll averaged 17%, 83%, 0% (3 samples). Both exclude the initial since-boot report. |
| `x11perf` 1.2, one 3 s trial per test | 238,000 10×10 rectangles/s, 11,900 filled 100-pixel circles/s, 472,000 characters/s in 80-character lines (6×13), 3,320 scrolls/s and 2,930 window-to-window copies/s (both 500×500). |
| Move a window | A QMP relative-pointer drag on the ctwm title bar moved xterm's left edge from 2 to 170 pixels. Its top stayed at 23 pixels (`xwininfo`). |

To reproduce, boot a writable overlay of the installed disk and mount the install CD read-only.
Extract `sparc64/binary/sets/x*.tgz` into `/` with `tar -xzpf` for each set. Boot with
`-M sun4u -m 1024 -vga std` and leave OpenBIOS output on the screen. With output on `ttya`,
`genfb0` probed but opening `/dev/ttyE0` returned “Device not configured”. With VGA as console,
`wsdisplay0` attached to `genfb0` and a separate getty on `com0` provided serial control.
Set `Driver "wsfb"` and `Option "device" "/dev/ttyE0"` in the Xorg Device section, reference it
from the Screen section, then run `startx` with a client script that starts ctwm and xterm.

For scrolling, number the lines 0001 through 2000, pad each to 66 printable characters and
end each with a newline. Time `cat` between serial markers with a host monotonic clock.
In xterm, include the reply to a trailing cursor-position query (`ESC [ 6 n`) so buffered output
is consumed. On wscons, direct the same file to the active `/dev/ttyE0` and time through command
completion. Run `x11perf -repeat 1 -time 3 -rect10 -fcircle100 -ftext -scroll500 -copywinwin500`.
For a separate full-frame workload, the [wisp framebuffer timedemo](../e2e/wisp/README.md#freedoom-framebuffer-timedemo)
measured 15.54 FPS on sun4u at 4× scaling (1280×800) under Linux.

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
label and boot block are fine; it is the GENERIC kernel under OpenBIOS. Unchanged with
pve-qemu-kvm 11.1.3-2+wsh21 (OpenBIOS 0001-0017) (2026-11-19).

**Cause** (2026-11-19). The PC is in `panic()`, called by `__stack_smash_handler("prom_map_phys")`
from `pmap_bootstrap()` (QEMU `-d int` for the registers at the trap: `%i0` = "smashed stack in %s",
`%i7` in `__stack_smash_handler`; `-d exec` with `-dfilter` on the kernel's text for the calls before
it). `panic()` then reads its per-CPU buffer at 0xe0018714 (`curcpu()`), not mapped yet that early:
the data access exception. OpenBSD 8.0's `prom_map_phys` calls the MMU's `map` method with
`call-method`, `nargs` 7 and `nreturns` 0 (IEEE 1275 gives `map` no results), with the argument
array on the stack. OpenBIOS's `handle_calls` (`libopenbios/client.c`) stores the catch result in
`args[nargs]` whatever `nret` is, so it writes 0 into the cell after the array, which is the
function's stack-protector canary. `bsd.rd` is built without the stack protector (no "smashed
stack" string in it), so it boots. `Unimplemented service set-symbol-lookup` is unrelated: OpenBSD
ignores that call's result. OpenBSD changed these calls (`map`, `unmap`, both `release`s) to
`nreturns` 1 after 8.0 ("did not work with QEMU's OpenBIOS", `ofw_machdep.c` 1.39, 2026-11-13);
8.0 and older need the firmware fixed.

The fix: store the catch result only when `nret` > 0, openbios 0023 (pve-qemu-kvm 11.1.3-2+wsh22;
first prototyped on top of 0001-0018). With it the installed disk boots:
`OpenBSD 8.0 (GENERIC) #52`, `login:` in 220-270 s from QEMU start (the first boot generates its
keys), `hme0` gets 10.0.2.15 by DHCP (`inet autoconf`) and the default route, `halt -p` ends QEMU
with exit code 0 in ~10 s. With `-vga std` (console on the screen, no `-prom-env`) the boot messages
and `login:` come up on the VGA screen (the keyboard wasn't tried there). On ttya it is the console
QEMU's `-nographic` gives too; the root device didn't need entering by hand.

**Disk timeouts with a synced clock.** With QEMU's user network with outside access (`NET=user`)
`ntpd` reaches its servers, finds the guest ~430 ms off and slews the clock (`clock unsynced`,
adjtime). From then on reads from `wd0` time out (`wd0(pciide0:0:0): timeout`, `wd0d: device
timeout reading fsbn ..., retrying`) and the shell hangs in the next program that has to be read
from disk: 5 of 6 runs with `NET=user` (the sixth had QEMU's IDE, BMDMA and sabre trace events on,
which slows QEMU down). Without outside access (restricted user network) 0 of 4, also with a ping
to 10.0.2.2 every 50 ms during the reads (2300 `hme0` interrupts) and after stepping the clock with
`date` (674 MB read by `tar` from `/usr`, no timeout). With `NET=user` and ntpd disabled
(`rcctl disable ntpd`) 0 of 1, and `ftp` fetches over HTTP from the internet through `hme0`. So it
follows ntpd's slew (a timing race in the kernel's timeouts or in QEMU's IDE/timer emulation), not
the network interrupts; not followed further. That conclusion was wrong: it was the network
traffic after all ("Cause: the sabre lost a request" below). The install target `openbsd80-sun4u`
kept ntpd off (`ntpd_flags=NO` in `/etc/rc.conf.local`, set from the installer's shell before the
first boot) until pve-qemu-kvm 11.1.3-2+wsh30 had `wsh/0045`; since then ntpd stays on.

**IDE timeouts without ntpd** (through PVE, pve-qemu-kvm 11.1.3-2+wsh22, 2026-11-19; `vmbr0` has no
outside access, ntpd is off, other guests on the host, load average 4-13 on 14 cores; e2e/sparc/README.md,
"The OpenBSD 8.0 install target"). The timeouts are not ntpd's alone:

- 1 of 5 installs: while `bsd.rd` extracted `base80.tgz` from the CD, nine `cd0(pciide0:1:0):
  timeout` (`type: atapi`, `c_bcount: 2048`), then no console output for 11 minutes (no ntpd in
  `bsd.rd`).
- Boots of the installed disk reading `/usr` with `tar` (1 GB) and writing 200 MB: 5 of 6 passed;
  one stopped after `wd0(pciide0:0:0): timeout` and `wd0d: device timeout reading fsbn 3408952 ...,
  retrying`, then nothing.

The hung guest: the CPU in OpenBSD's idle loop (`pc` 0x12d9cac, `pstate` 6: interrupts enabled, PIL
0), `info blockstats` with no I/O for 321 s (`idle_time_ns`), no IDE, BMDMA or cmd646 trace event in
40 s (`trace-event ide_* on` etc. in the monitor), and no answer on the serial console to Return or
a break (`chardev-send-break`, which normally enters ddb). So after the timeouts no interrupt reaches
the CPU any more, not even the console's: a lost or stuck interrupt in QEMU's sun4u path (cmd646
INTRQ through the sabre's interrupt mapping to the CPU's interrupt vector), which ntpd's slew makes
more likely but doesn't cause. Next: `-d int` and the sabre/IVEC state at the hang, and whether
`wsh/0021`'s latch (the cmd646 interrupt status bits stay set until written 1) leaves a level that
the sabre no longer forwards. The install target failed an install that stays silent for 5 minutes
after an IDE timeout and ran it once more (`retry_on`) until `wsh/0045` (below); the detection stays,
the retry is gone.

**Cause: the sabre lost a request** (2026-11-20; QEMU built from the pve-qemu 11.1.3-2 series with
`wsh/0001`-`0044`, OpenBIOS 0001-0018 + 0023, the stored `install-openbsd80-sun4u` disk on a copy,
lab runs, not through PVE). The sabre keeps one interrupt request to the CPU at a time
(`irq_request`) and makes the next one when the guest writes the current one's clear register. An
OBIO interrupt (ino 0x20-0x3f: the cmd646 at 0x20, the serial console at 0x2b) that rises meanwhile
waits for that; a PCI interrupt (ino 0x00-0x1f: the NIC, which `-device ...,bus=pciB` puts at ino
0x10) did not, and replaced the outstanding request. The CPU takes one vector at a time and ignores
one sent while its busy bit is set (`sparc64_cpu_set_ivec_irq()`), so a NIC interrupt between the
IDE request and the guest's acknowledge was dropped there; the guest then cleared the IDE request,
which was no longer `irq_request`, and the clear was ignored. From then on no OBIO interrupt reached
the CPU (disk, console, break), and the NIC's line stayed up, so no new PCI edge either. A debug
build that logs the sabre's and the CPU's interrupt events into a ring (read with `qom-get /machine
irqdbg`) caught it in the first round of a `tar cf - /usr | cksum` with `ping -f 10.0.2.2` running
(NIC traffic in place of ntpd's): IDE request 0x20 taken by the CPU, the NIC's interrupt 34 us later
replaced it and was dropped (CPU busy), the guest's clear of 0x20 ignored, the next IDE interrupt
never requested; at the hang `irq_request` 0x10 with the lines of 0x10 and 0x20 up and the CPU halted
in the idle loop. `wsh/0021`'s latch has no part in it: the cmd646's line followed INTRQ throughout.
ntpd made it likely through its network traffic, not its clock slew; the rare hang without ntpd,
and the `cd0` timeouts during an install, presumably came from the little traffic the NIC still sees
on `vmbr0` (not traced).

`wsh/0045` makes a PCI interrupt wait for the outstanding request as an OBIO interrupt does (it is
requested when the guest clears the current one); `wsh/0046` is the qtest (`sun4u-sabre-irq-test`,
fails without 0045). Lab results (3 runs at a time on the lab host; a hang = a disk timeout on the
console and no end of the round within 5 minutes after it):

| Load | QEMU | Runs | Hung |
| --- | --- | --- | --- |
| `ping -f` + 3 rounds of `tar` (each 250-330 s) | wsh/0001-0044 | 2 (one `idle-halt=off`) | 2, in round 0 |
| | 11.1.3 + only pve's patches and our 0001, 0007, 0021-0022, 0034-0037 (no LEMU code, no idle halt) | 2 | 2, in round 0 |
| | wsh/0001-0045 | 4 (one `idle-halt=off`) | 0 (12 rounds) |
| `NET=user`, default route and DNS, `rcctl -f start ntpd` (5/5 peers, clock unsynced, offset ~350 ms), then 3 rounds of `tar` (90-110 s) | wsh/0001-0044 | 2 | 2, both while ntpd started |
| | wsh/0001-0045 | 3 | 0 (9 rounds) |
| NetBSD 9.3 (stored disk), `ping -f` + `tar` | wsh/0001-0044 | 1 | 1 (`cmdide0:0:0: lost interrupt` every 10 s) |
| NetBSD 9.3 and 11.1 (stored disks), `ping -f` + 2 rounds of `tar` | wsh/0001-0045 | 2 | 0 (4 rounds) |

`idle-halt` doesn't change the symptom: with it off the CPU spins in the idle loop instead of
halting there, and nothing else differs. Solaris 10 (stored disk) boots on 0045 to `console login:`
and powers off (`sparc64-boot-disk.py`, with a ping through `hme0`, 1 boot).

Through PVE with the published pve-qemu-kvm 11.1.3-2+wsh30 (2026-11-20, ntpd on;
e2e/sparc/README.md, "The OpenBSD 8.0 install target"): 4 of 4 complete `openbsd80-sun4u` installs
with `--check` passed without an IDE timeout in any phase (16.0-17.9 min; two with a way out through
`vmbr0`, where ntpd reached its servers), 3 of 3 boots with ntpd slewing the clock (offset ~395-449
ms, 5/5 peers) and a `tar` of `/usr` plus a 200 MB write passed without a disk timeout, and so did
a boot with `ping -f` during the `tar` (the load in the table above). Before the fix a similar load
(ntpd slewing, `tar` of `/usr`) hung 5 of 6 boots. The target therefore keeps ntpd on and has no
install retry.

Again with the published pve-qemu-kvm 11.1.3-3+wsh6 (2026-11-21): 3 of 3 installs with `--check`, a
boot-test of the stored disk and three 20-36 minute boots with ntpd running passed without a disk
timeout. The guest's timecounter is `tick` (`%tick` at the 100 MHz the firmware reports, counted by
QEMU from the host clock): ntpd synced 4.5 minutes after it started, after one 0.193 s slew (the
`mk48t59` gives the boot whole seconds), stayed synced (stratum 2-3), and corrected the frequency by
0.18 ppm, so the clock runs at the host's rate. Two of those boots lost ntpd's servers for 15-17
minutes (names not resolved, or all peers invalid) without a disk timeout; a network matter of the
test setup as far as checked, not traced (e2e/sparc/README.md, "The OpenBSD 8.0 install target").

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

**Debian 13 on sun4u** (2026-11-22; the lab image of the published pve-qemu-kvm 11.1.3-4+wsh4, 1024 MB, disk
and netinst on IDE, `sunhme`, user-mode network; e2e/sparc/README.md, "Debian 13 on sun4u"). The debian-ports
sparc64 netinst of 2026-06-11 (`debian-13.0.0-sparc64-NETINST-1.iso`, sha256 as in the snapshot's SHA256SUMS)
installs sid from deb.debian.org/debian-ports: partman's "atomic" recipe on a Sun label (`/boot` ext2, `/`
ext4, swap), the SSH server task, GRUB 2.14 (`sparc64-ieee1275`, blocklists: "Embedding is not possible"
because the Sun label nests the partitions). Three complete installs (one by hand with a preseed by URL and
DHCP, one with the target's scenario and answer CD, one `lab.py install debian13-sun4u --check --export`
through PVE with the published pve-qemu-kvm 11.1.3-4+wsh8: passed in 177 min), 2.5-2.8 h each. The stored
`install-debian13-sun4u.raw` boot-tests in 4.9 min; the target has `matrix_skip` like Tribblix, so the matrices
boot-test it and reinstall it only on request.

- **The Debian 12 failure did not come back.** No `dpkg-deb` segfault or soft lockup in either install
  (the installer's syslog and dmesg checked), and on the installed system 60 `dpkg-deb -x` of perl-base,
  libc6 and coreutils (20 rounds) passed without a failure or a kernel message. Not narrowed down, as it
  never reproduced; the Debian 12.0 netinst itself (Linux 6.1) wasn't tried again, so whether a later QEMU
  change or the newer kernel and glibc made the difference is open.
- **GRUB on OpenBIOS ("canonicalise devname failed").** The installed disk boots through GRUB to `login:`.
  With an openbios-sparc64 built from QEMU 11.1.3's OpenBIOS commit without our patches, the same disk
  stops as in the 2021 report: `error: canonicalise devname failed.`, then `Unhandled Exception 0x30`.
  grub-install keeps an OBP-style path for the disk (`/pci@1f,0/pci@1,1/ide@3/disk@0`, from Linux's
  sysfs), and GRUB's `obdisk` asks the firmware's `canon` for it; that path exists only with openbios
  0009 (`pci@1f,0`, OBP's names) and 0011 (the drives under the controller); the stock tree has
  `/pci@1fe,0/pci@1,1/ide@3/ide@0/disk@0`. Built and booted one at a time: 0009 + 0011 boot; 0009, 0010,
  0011 or 0023 alone, and 0010 + 0011, fail. An install under the stock firmware wasn't tried. What GRUB
  prints on the way is harmless: `call-method color!: exception -21` (its colours on ttya),
  `block-size`/`#blocks` failing (OpenBIOS's disk package has neither; GRUB takes 512-byte sectors), `error:
  out of memory` and `no suitable video mode found` (no framebuffer).
- **Idle.** The installed kernel is 7.0.12+deb14, the one `wsh/0070` was written against: QEMU at 6.9% and
  6.5% of a host core over 60 and 120 s at the shell (guest load average 0.09, host 0.5-1.3), against
  100.5% for this kernel without the halt ("Idle, more guests" above; not measured again here).
- **systemd's timeouts on a busy host** (2026-11-24, pve-qemu-kvm 11.1.3-4+wsh13). The stored disk's boot test
  failed on a busy lab host and passes on an idle one: systemd's 90 s for a device and for a unit's start are
  wall-clock time, udev's coldplug under TCG takes about that long when idle, and with the host loaded
  `/boot`'s device timed out and systemd stopped in emergency mode. Not a QEMU or OpenBIOS fault; the boot
  scenarios pass longer timeouts on GRUB's `linux` line, new installs get them in a drop-in (e2e/sparc/README.md,
  "Debian 13 on sun4u"). At that load (32-43 on 14 cores) one boot in 9 also lost an IDE interrupt during
  `poweroff` (`READ DMA` timed out with the drive `DRDY`, then every PIO command): the sunhme kept receiving
  after Linux had reset it, and the sabre held the IDE interrupt behind the NIC's (`wsh/0135`, "The lost IDE
  interrupt at Debian 13's power-off" below).

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

- Before pve-qemu `wsh/0042` NetBSD/sparc64 didn't idle on sun4u: QEMU kept a host core at 100% for
  as long as the VM ran, and so did every other sun4u guest. See "Idle" below. The sparc32 kernel
  idles through the sun4m APC.
- The same user-space job runs about 4x slower on sparc64 than on sparc32 SS-20 (median 36.7 s vs
  9.3 s), so sparc64 is not a faster way to run NetBSD. Not analysed further.
- Ten `sleep 1` take 10.3-10.4 s; the guest clock keeps time.
- Boot to `login:` 46-68 s; `halt -p` to QEMU's exit 8.7-9.1 s.

**Idle (pve-qemu `wsh/0042`-`0044`, in review, 2026-11-20).** Every sun4u guest spun in its idle loop:
QEMU kept a host core at 100% for as long as the VM ran. No guest has a way to stop an UltraSPARC-IIi
that QEMU could emulate instead, so the translator recognises their idle loops and halts there, like
`sunos-idle`/`solaris-idle` on sun4m (and like those, built on LEMU's technique: not for QEMU). What
each kernel does on sun4u (read in the open sources: NetBSD, OpenBSD, illumos, Linux; the loops
disassembled from the stored disks with `objdump`, `mdb -k` and QEMU's `x/i`):

| Guest | Idle loop | What the kernel could stop the CPU with on sun4u |
| --- | --- | --- |
| NetBSD 9.3, 11.1 | `idle_loop()` calls `cpu_idle()` while `sched_curcpu_runnable_p()` is false, then checks `ci_want_resched` | nothing: `cpu_idle()` calls `ci_idlespin`, which only sun4v sets (`hv_cpu_yield`); 9.3's `cpu_idle` is `retl; nop`. The ebus `power` node isn't attached (`power at ebus0 ... not configured`) |
| OpenBSD 8.0 | `sched_idle()`: `while (spc_whichqs == 0) cpu_idle_cycle();` | nothing: `cpu_idle_cycle()` yields to the hypervisor on sun4v; on sun4u it is a `nop` that is patched to `sleep` (SPARC64-VI/VII) only on CPUs with several strands |
| Solaris 9, 10; Tribblix m34 (illumos) | `idle()` with one CPU: `(*idle_cpu)()` while `CPU->cpu_disp->disp_nrunnable == 0` | nothing: `idle_cpu` becomes `cpu_halt` only if the CPU module has `cpu_halt_cpu()`, which only the SPARC64-VI module (`opl_olympus`, the `sleep` instruction) has; on UltraSPARC-II/IIi it stays `generic_idle_cpu` (`retl; nop`) |
| Solaris 7 3/99, 8 2/02 | `idle()` as in 9 and 10 | nothing, as on 9 and 10 |
| FreeBSD 12.4 | `sched_idletd()` (ULE): `cpu_idle(busy)` while `tdq_load` is 0, `tdq_cpu_idle` set round it | nothing: `cpu_idle()` is empty on sparc64 (`retl; nop`); the kernel runs at TL 1 |
| Linux 6.1-7.3 (wisp; Debian 12 and 13 installers) | the generic `do_idle()`: with interrupts disabled (`%pil` 14) and `need_resched()` clear it calls `arch_cpu_idle()`, enables interrupts and goes round again | nothing: `arch_cpu_idle()` calls `sun4v_cpu_yield` on sun4v; on sun4u it only touches the NMI watchdog. No kernel option helps: sparc64 has no cpuidle driver, `idle=poll` spins elsewhere, and `nohz` takes away clock interrupts, not the spin. No installed disk (Debian 12's install fails); measured with `-kernel` |
| Linux 3.2 (Debian 7, installed disk and installer) | `cpu_idle()` in `arch/sparc/kernel/process_64.c`, with interrupts enabled (`%pil` 0): `while (!need_resched() && !cpu_is_offline(cpu)) sparc64_yield(cpu);` | nothing: `sparc64_yield()` clears `TIF_POLLING_NRFLAG` and calls `sun4v_cpu_yield` on sun4v; on sun4u it only calls `touch_nmi_watchdog()` (pve-qemu `wsh/0110`) |

None of them uses `sir` or an `%asr` write to idle. The clock-divider power management of the
UltraSPARC-IIe/IIIi (Energy Star) slows the clock rather than stopping it, and QEMU emulates a IIi (not
looked into further). sun4v's hypervisor `cpu_yield` is out of scope.

0042 recognises one call in each loop by the words around it and takes from them where the loop keeps
the word that says there is work:

| Kernel | Call (address on the stored disk) | Word | Layout |
| --- | --- | --- | --- |
| NetBSD 11.1 | `call cpu_idle` (0x15b320c) | `ci_want_resched` (`[%i4 + 0x5a0]`) | `call runnable_p; nop; brnz %o0, out; nop` before; the same and `ld; cmp; be top; nop` after |
| NetBSD 9.3 | `call cpu_idle` (0x15191e8) | `ci_want_resched` (`[%i3 + 0x3d0]`) | the same with `cmp %o0, 0; bne out; nop` |
| OpenBSD 8.0 | `call cpu_idle_cycle` (0x1558134) | `spc_whichqs` (`[%i4]`) | `ld; cmp; bne out; nop; call; nop; b top; nop` |
| Solaris 10 1/13 | `jmpl %o1, %o7` (0x10621d0) | `disp_nrunnable` (`[%o0 + 0x24]`, `%o0` = `cpu_disp`) | Sun's compiler: `ld; cmp; bne run; sethi %hi(idle_cpu); ldx; call; ...; b` |
| Solaris 9 9/05 | `jmpl %l0, %o7` (0x104618c) | `disp_nrunnable` (`[%l2 + 0xb4]`, in the CPU structure) | the same |
| Tribblix m34 | `jmpl %g1, %o7` (0x10621c8) | `disp_nrunnable`, 0x24 past the `cpu_disp` pointer at `[%l0 + 0xd0]` (gcc loads the pointer and the count into the same `%g1`, so the helper follows the pointer again) | gcc: `ldx; ld; cmp; bne,pt %icc run; nop; ldx [%l1]; call; nop; ba,pt %xcc top` |
| Solaris 7 3/99 (0071) | `jmpl %l0, %o7` (0x1003d528) | `disp_nrunnable` (`[%i2 + 0x9c]`, in the CPU structure) | Sun's older compiler: `ld; cmp; be idle; sethi %hi(idle_cpu); call swtch; nop; b top; ...; idle: ldx; call; nop; b top` |
| Solaris 8 2/02 (0071) | the call through `idle_cpu` (0x10040660; the same in the Installation CD's kernel) | `disp_nrunnable` (`[%i3 + 0x9c]`) | the same as 7 |
| Solaris 8 1/01, Installation CD's kernel (0071) | (0x1003fab4) | `disp_nrunnable` | the same as 7 |
| Linux 7.3.4, wisp (0070) | `call arch_touch_nmi_watchdog` (0x431104) | `TIF_NEED_RESCHED` in `current_thread_info()->flags` (`[%g6 + 8]`) | gcc 14: `ld [tlb_type]; cmp 3; be %icc sun4v; nop; call; restore` (a tail call), the sun4v branch right after (`wrpr %g0, 0, %pil; rdpr %pstate; andn 2; wrpr %pstate`) |
| Linux 6.1.27, Debian 12 installer (0070) | `call arch_touch_nmi_watchdog` (0x42c280) | the same | gcc 12: `... be,pn %icc sun4v; nop; call; nop; call touch_softlockup_watchdog; nop; wrpr %g0, 0, %pil; return; nop`, then the sun4v branch |
| Linux 6.17.7 and 7.0.12, Debian 13 installers of 2025-11 and 2026-06 (0070) | `call arch_touch_nmi_watchdog` (0x43a9a0, 0x43aa40) | the same | gcc 15: `... bne,pn %icc sun4u; nop;` the sun4v branch (16 words, `return; nop` at its end), `sun4u: call; nop; call touch_softlockup_watchdog; nop; return; nop` |
| FreeBSD 12.4 (0114) | `call cpu_idle` (0xc068f230) | `tdq_load` (`[%l1 + 0x88]`) | gcc 4.2: `st %g1, [%tdq + 0x8c]; membar; ld [%tdq + 0x88]; cmp; be idle; ...; clr [%tdq + 0x8c]; b top; nop; idle:` five words, the call, `clr [%tdq + 0x8c]` after it; halted at TL 1 and without the 100 us poll ("FreeBSD 12.4 on sun4u") |
| Linux 3.2.78, Debian 7's `3.2.0-4-sparc64` (installed and installer kernel, the same image) and `-smp` (0110) | `call touch_nmi_watchdog` in `cpu_idle()` (0x42ab58; `-smp` 0x42ad7c) | the same, at `%pil` 0 | gcc 4.6: `cmp %r, 3; be,pn %icc sun4v; mov 14, %o0; call; nop; b %xcc top; nop; sun4v: call clear_bit; add %o1, 8, %o1` (the `tlb_type` load right before in the uniprocessor kernel, elsewhere in `-smp`) |

At the call the helper halts the CPU when the word is 0, `PSTATE.IE` is set, `%pil` and `%tl` are 0, and
no interrupt, interrupt vector, `%softint` bit or `pil_in` line is pending, after spinning 100 us as on
sun4m; the CPU goes on at the call after the next interrupt (the guest's `%tick`/`%stick` clock, 100 Hz
at least, or a device). QEMU's sun4u has one CPU, so only an interrupt handler can give it work. A kernel
compiled differently isn't recognised and spins as before; `-trace sparc64_idle_match` shows a match,
`-trace sparc64_idle` each halt. `-M sun4u,idle-halt=off` turns it off; through Proxmox
`args: -machine idle-halt=off` (QEMU merges the second `-machine`: checked with QEMU directly, not
through `qm`).

Found on the way: the first build only took a BPcc branch on `%icc` (it read the `cc1` bit as reserved)
and missed Tribblix's `ba,pt %xcc`, which `sun4u-idle-test`'s Tribblix layout now has; and Solaris's old
`/usr/bin/awk` reads its input even with only a `BEGIN` rule, so the job in `sparc64-idle.py` reads
`/dev/null`.

Measured with `scenarios/sparc64-idle.py` on copies of the stored install disks
(`/mnt/os/disks/install-*`, one CPU, serial console, `sunhme` on a restricted user network): the package
11.1.3-2+wsh25 ("before") and a `qemu-system-sparc64` built from 0001-0044 ("with"), started side by side
on the lab host (14 cores, a load of 6-11 from other guests), each after `WAIT` had ended what the guest
still does after boot (lab README, "Idle"). Host CPU over 60 s at the shell, the guest clock over those
60 s, ten `sleep 1` and the awk job in host seconds, `LOAD=120` rounds (BSDs):

| Guest | MEM | Host CPU before | with | Clock drift | 10 x `sleep 1` before / with | Job s before / with | Load rounds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NetBSD 11.1 | 512 | 100.8% | 3.5% | 0.0 s | 10.4 / 10.4 | 25.6 / 24.9 | 4 / 4 |
| NetBSD 11.1, `idle-halt=off` | 512 | | 100.8% | 1.0 s | 10.4 | 25.3 | 5 |
| NetBSD 9.3 | 512 | 100.9% | 3.5% | 0.0 s | 10.4 / 10.4 | 21.2 / 22.9 | 5 / 5 |
| OpenBSD 8.0 | 512 | 100.3% | 8.6% | -0.1 s | 10.5 / 10.5 | 10.0 / 11.1 | 10 / 10 |
| Solaris 10 1/13 | 1024 | 101.8% | 7.3% | 0.0 s | 10.4 / 10.5 | 8.5 / 11.4 | |
| Solaris 9 9/05 | 1024 | 102.0% | 6.8% | 0.0-1.0 s | 10.5 / 10.6 | 10.1 / 10.4 | |
| Tribblix m34, `fmd` off | 2048 | 102.4% (`idle-halt=off`) | 21.8% | -0.1 / -0.2 s | 11.7 / 11.7 | 19.2 / 18.6 | |
| Tribblix m34, `fmd` on | 2048 | 107.9% | 104.0% | -0.2 / -0.8 s | 12.7 / 12.5 | 25.0 / 24.6 | |

The guest clock reads whole seconds, so 1.0 s of drift is one tick of `date`. A single job varies by
±15% from run to run on this host whichever binary runs, so the binary with 0042-0044 was also run with
`idle-halt` on and off side by side, the job five times in a row:

| Guest | Host CPU on / off | 5 jobs on / off | Load rounds on / off |
| --- | --- | --- | --- |
| NetBSD 11.1 (`LOAD=300`) | 3.9% / 100.7% | 101.0 / 102.9 s | 3 / 3 |
| OpenBSD 8.0 (`LOAD=300`) | 5.4% / 101.2% | 40.5 / 41.9 s | 7 / 7 |
| Solaris 10 1/13 | 4.8% / 100.5% | 40.0 / 40.0 s | |

CPU-bound work takes as long as before, ten `sleep 1` take 10.4-10.6 s in every case and the clock keeps
time. What is left (3-9% on the BSDs and Solaris) is the 100 us spin before each halt at every clock tick, the guests' own
periodic work and QEMU's timers. Solaris 10 needs several minutes after the login prompt until SMF has
started everything (`svc.configd`, `inetd`, `snmpd`, `fmd` at 30-40% of the guest CPU): measured too
early it reads 100% with or without the halt. Tribblix's FMA marks its ZFS disk DEGRADED again within
minutes (the known EIO ereports, "Tribblix on sun4u", also after `zpool clear`), and `rcm_daemon` then
spins (67% of the guest CPU after 3.5 hours in one run): a guest that busy rarely reaches its idle loop,
so with `fmd` running it reads 104-108% either way. With `fmd` disabled (`svcadm disable fmd`, which a
real installation shouldn't do) it idles at 21.8% (258 111 halts traced in the run); the rest is
Tribblix's own work under emulation, not analysed. Its ten `sleep 1` take 11.7 s with and without the
halt (12.5-12.7 s with `fmd`): Tribblix's own timing, not the halt's.

**Idle, more guests (pve-qemu `wsh/0070`-`0072`, 2026-11-22).** Linux and Solaris 7 and 8 spun as well.

- **Solaris 7 and 8.** `-trace sparc64_idle_match` showed no match on the stored `sol7-sun4u` disk
  nor on the new `sol8-sun4u` one (installed for this, "Solaris 8 and 9 on sun4u" in the lab README),
  and QEMU's `x/i` at the sampled idle PC showed why: Sun's older compiler lays `idle()` out the other
  way round from 9 and 10 (table above). Solaris 8 is laid out like 7, not like 9. 0071 recognises that
  layout; the call goes through `helper_sparc64_idle()` as for 9 and 10. The kernels of the Solaris 8
  2/02 and 1/01 Installation CDs match it too (trace at their first question).
- **Linux.** The generic idle loop (`kernel/sched/idle.c`, Linux 7.3) calls `arch_cpu_idle()` with
  interrupts disabled (sparc64's `local_irq_disable()` writes `%pil` 14) once `need_resched()` is
  clear; on sun4u `arch_cpu_idle()` only touches the NMI watchdog (`arch/sparc/kernel/process_64.c`;
  6.1 also enables interrupts there, the older contract), and the loop goes round once it has enabled
  interrupts. The sun4v branch shows what the kernel itself accepts: interrupts enabled, `PSTATE.IE`
  cleared, the hypervisor's `cpu_yield` (which returns on a pending interrupt even with `IE` clear),
  `IE` set again. No upstream option makes sun4u stop the CPU: there is no cpuidle driver for sparc64,
  `CONFIG_SUN_LDOMS` and the hypervisor calls need sun4v, `idle=poll` only moves the spin, and
  `nohz` removes clock interrupts but not the spin. So 0070 recognises `arch_cpu_idle()` by its
  `tlb_type` test and the start of the sun4v branch (both orders gcc uses, table above) and halts at
  the call of `arch_touch_nmi_watchdog()` with `%pil` 14, `PSTATE.IE` set, `%tl` 0, nothing pending
  and `TIF_NEED_RESCHED` clear: waiting with interrupts disabled, as `cpu_yield` (and x86's `mwait`,
  which the comment in `do_idle()` names) do. QEMU's sun4u wakes a halted CPU whatever `%pil`: the
  tick, stick and hstick compare interrupts and the interrupt vector clear `cs->halted`
  (`hw/sparc64/sparc64.c`), and nothing on sun4u raises `pil_in`. The CPU goes on at the call; the
  interrupt is taken when the loop enables interrupts, so no state is kept across the halt (nothing
  for migration). 0042's halt needs `%pil` 0 and stays as it was. The window read around a call grew
  from 8 to 24 words before it (Debian 13's bne layout needs 20, Solaris 7's 9); words on another page than
  the call's read as 0 (illtrap, in no layout) instead of the call being skipped.
- **The lost tick at `%pil` 14 (`wsh/0139`-`0140`, 2026-11-25).** Found by reading, never seen on a guest:
  `helper_sparc64_idle_linux()` checked `%softint`, the interrupt vector and `CPU_INTERRUPT_HARD` without the
  BQL and then set `cs->halted`. The tick and stick timers run in the main loop with the BQL (`tick_irq()`
  sets `SOFTINT` and `halted = 0`, then `cpu_check_irqs()` and a kick). One that fired between the check and
  the halt was masked at `%pil` 14: no `CPU_INTERRUPT_HARD`, so `sparc_cpu_has_work()` was false and the
  vCPU thread (single-threaded TCG: sparc64 has no MTTCG) slept in `rr_wait_io_event()`, the kick's
  broadcast already gone. Linux had not taken the tick, so it armed no next one: asleep until the next
  interrupt vector, or for good on an idle guest. 0139 checks again and halts under the BQL. The other
  helpers keep the window without the effect: NetBSD, OpenBSD, Solaris 7-10, Tribblix (0042, 0071),
  Linux 3.2 (0110) and FreeBSD (0114) halt at `%pil` 0, where the tick raises `CPU_INTERRUPT_HARD`, and the
  interrupt vector raises it at any `%pil`; the vCPU thread checks it under the BQL before it sleeps.
  The qtest (0140) makes the window as long as it likes: QEMU writes the `sparc64_idle` trace between the
  check and the halt, to a FIFO the test has filled, so the CPU waits there with nothing pending while the
  1 ms tick fires. Lab build of 0001-0140 (`qemu-system-sparc64` only, Debian 13): without 0139 the three
  Linux layouts fail 15 of 15 runs (0 rounds and 0 ticks once let go), the `%pil` 0 loops pass; with it
  all ten pass 50 of 50 (302-307 ticks in 300 ms). `sun4u-idle-test` 80/80 in 68.2-68.8 s (three
  `meson test` runs, 8 in parallel; meson's default of 60 s killed it, so it gets 240 s in `slow_qtests`),
  `qtest-sparc64` 22 OK, 2 skipped, `qmp-test` `oob` failing as before. wisp (Linux 7.3.4, `wisp=shell`,
  host load 5-7 from other jobs): host CPU at the prompt over 30 s 5.7-6.8% without 0139, 6.2-6.7% with
  it (one run each at 9.4% and 14.9% under load spikes), 100.3-100.5% with `idle-halt=off`; `crc 100000`
  9.2-10.7 s in all three, guest uptime 2 s behind the host's time since QEMU's start in every run (the boot).

Measured on the lab host (14 threads, quiet: 1-minute load 0.1-1.1 at every start and end), one QEMU at
a time, "before" the 0001-0067 build, "with" the same tree with 0070-0072, "off" that one with
`-M sun4u,idle-halt=off`. Linux booted with `-kernel` (no Linux disk: Debian's install fails): wisp's
tier-1 kernel with `wisp=shell` (256 MB), host CPU over 60 s at its prompt, then the guest's uptime
against the host's clock and `crc 100000` three times (host seconds, two passes); the Debian netinst
`install/vmlinux` and `initrd.gz` from the CDs (1024 MB, `console=ttyS0`), host CPU over 60 s at the
installer's first question, and the time to it:

| Guest | Host CPU before / with / off | Clock drift | Job s before / with / off | To the prompt s before / with / off |
| --- | --- | --- | --- | --- |
| wisp, Linux 7.3.4 (two passes) | 100.5, 100.5 / 5.6, 5.3 / 100.5, 100.5% | 0.0 s | `crc 100000` 8.72-8.82 / 8.77-8.92 / 8.67-8.77 | 2.1-2.2 |
| Debian 12 installer, Linux 6.1.27 | 100.4 / 5.7 / 100.5% | | | 31.0 / 30.9 / 33.5 |
| Debian 13 installer of 2025-11, Linux 6.17.7 | 100.4 / 6.0 / 100.4% | | | 33.5 / 33.7 / 32.4 |
| Debian 13 installer of 2026-06, Linux 7.0.12 | 100.4 / 5.8 / 100.5% | | | 33.8 / 33.9 / 33.8 |
| Solaris 7 3/99, `install-sol7-sun4u` (1024 MB) | 100.5 / 2.5 / 100.5% | 0.0 s | awk 6.0 / 6.0 / 6.1 | `login:` 180.7 / 180.5 / 180.5 |
| Solaris 8 2/02, `install-sol8-sun4u` (1024 MB) | 100.5 / 3.0 / 100.5% | 0.0 s | awk 7.1 / 7.0 / 6.8 | `login:` 206.7 / 206.7 / 206.6 |

Solaris with `scenarios/sparc64-idle.py` on copies of the stored disks (the Solaris 9 variables, lab
README "Idle"; the awk job of the table above, 60 s at the shell); ten `sleep 1` took 10.1-10.2 s in
all six runs. Longer jobs, with the halt on / off: five awk jobs in a row on Solaris 8 34.5 / 34.5 s,
wisp's `crc 500000` 43.7 / 43.6 s. The Debian installer's boot is mixed work with the halt on: it
takes as long as with it off. The wisp kernel ticks 250 times a second (`HZ_PERIODIC`), so it
wakes at every tick and spins 100 us before it halts again; whether the Debian kernels stop the tick
when idle wasn't looked at (their configuration isn't on the CDs).

The guests 0042 covers, with the build with 0070-0072 (same runs, same host, `TRACE` shows their old
layout matched): NetBSD 11.1 2.6%, NetBSD 9.3 2.5%, OpenBSD 8.0 4.3%, Solaris 9 3.1% (ten `sleep 1`
10.1-10.3 s, clock drift 0.0 s); Solaris 10 and Tribblix weren't measured again. The installer kernels
of NetBSD 9.3 and 11.1 and OpenBSD 8.0's `bsd.rd` (the CDs, `sparc64-boot-cd.py` with the trace) match
the NetBSD and OpenBSD layouts as well.

**Stability** (NetBSD 11.1): 4 boots in a row of the same disk, each a new QEMU process, login,
`halt -p` (`sparc64-boot-disk.py BOOTS=4`): all passed, `login:` after 56.0, 56.1, 56.0 and 71.4 s,
power-off to QEMU's exit 8.3-8.7 s. `LOAD=300` (`sparc64-idle.py`: the awk job and a
64 MB file written, read back and removed, in a loop for 5 minutes, 9 rounds): the guest answered
afterwards and powered off. Every power-off ended QEMU with exit code 0 (more than 15 runs, including
the boot tests with DHCP and HTTP fetches over `sunhme`, `virtio-net-pci`, `e1000`, `rtl8139` and
`ne2k_pci`). No hang with NetBSD on the recommended layout (only I/O to the offline virtio-scsi disk
hung, above). OpenBSD's installer `halt` stops at OpenBIOS's `0 >` instead
of powering off (through PVE `bsd.rd`'s `halt -p` printed `halted (with powerdown)` and the VM
stayed on); `halt -p` on the installed system (openbios 0023, above) ends QEMU with exit code 0.

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
| 9 DVD | `SunOS Release 5.9 Version Generic 64-bit`, then `panic[cpu0]/thread=140a000: boot_alloc: pp is NULL or free` in `boot_mapin` ← `boot_alloc(0x30000136000, 0x2000, 0x1000)` ← `segkmem_alloc` ← `kobj_vmem_init`, from `modloadonly` in `startup_modules`. With 0024 (2026-11-19): the installer's `Select a Language` at 1024 and 2048 MB |
| 9 9/05 DVD | `SunOS Release 5.9 Version Generic_118558-34 64-bit`, then the same `boot_alloc: pp is NULL or free`, earlier in `startup_modules`: at 1024 MB `boot_alloc(0x30000058000, 0x2000)` for a `kmem_alloc` in `kobj_load_module` ← `modload` ← `mod_setup`; at 2048 MB `boot_alloc(0x30000146000, 0x82000)` (with the published `openbios-sparc64`, 0001-0023; "Solaris 7/8/9: `pp is NULL or free`" below). With 0024: the installer at 1024 and 2048 MB; at 1024 MB Web Start installs End User to the IDE disk and the installed system boots to `console login:` (the first, reconfiguring boot panicked in the floppy driver until 0025: "Solaris 7/8/9 with 0024"; the install targets `sol9-sun4u` and `sol8-sun4u`: "Solaris 8 and 9 install targets on sun4u") |
| 8 (1/01) Installation CD | `SunOS Release 5.8 Version Generic_108528-05 64-bit`, then `panic[cpu0]/thread=10408000: boot_alloc: pp is NULL or free`. With 0024: the installer's `Do you want to format /dev/dsk/c0t0d0?` at 1024 and 2048 MB |
| 8 2/02 Installation CD | `SunOS Release 5.8 Version Generic_108528-13 64-bit`, then the same panic in `setup_ddi` ← `startup_modules`: `boot_alloc(0x300001be000, 0x14000)` at 1024 MB (`0x300001f6000` at 2048 MB) for `impl_ddi_callback_init` (published firmware, as 9 9/05). With 0024: the installer at 1024 and 2048 MB; at 1024 MB the mini-root and Web Start install End User to the IDE disk (a fresh QEMU between the two) and the installed system boots to `console login:` |
| 7 (3/99) | `SunOS Release 5.7 Version Generic_106541-02`, then `panic[cpu0]/thread=10404040: kmem_getpages: pp is NULL or free`. With 0024: the installer's `Select a Language` at 1024 and 2048 MB (IDE timeouts and `Interrupt not seen after set_features` on the way) |
| 2.6 (5/98), 2.5.1 (11/97) | in the boot block: `open isn't unique.`, `?go:`, `byte-load: exception caught!`. With 0031: the kernel starts; 2.6 can't mount root from the CD, 2.5.1 traps before its banner ("Solaris 2.5.1 and 2.6 on sun4u: the boot block"). With 0036 (2.6) and 0037-0038 (2.5.1): the installers; with 0039 as well the installed systems boot ("Solaris 2.6 and 2.5.1 on sun4u: the kernels") |

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
  returned!`: OpenBIOS's client-interface `boot` service only prints `BOOT` and returns. Fixed since
  by OpenBIOS 0030 ("The firmware reboot on sun4u").
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
  the same thing on the wire. Measured since (below); fixed by pve-qemu `wsh/0034` ("The sun4u system
  MAC").

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
  fails; not traced further. So 0012 stayed `.wip`; traced and replaced by 0030 ("The firmware
  reboot on sun4u").
- **System MAC:** with `-device sunhme,mac=52:54:00:aa:bb:cc`, Solaris's `hme0` shows `ether
  52:54:0:12:34:56`. QEMU's sun4u writes the MAC of the onboard NIC into the IDPROM. The onboard NIC
  is the first `-nic`/`-net nic` of the default model, created at PCI 01.1 on bus A. A NIC added with
  `-device` (as qemu-server and the lab do) isn't seen at that point, so the IDPROM gets QEMU's
  default `52:54:00:12:34:56`. With `-net nic,model=sunhme,macaddr=...` the NIC sits at a different
  PCI path, and the installed system (whose `hme0` is the `-device` NIC on bus B) didn't configure
  it. The IDPROM MAC there wasn't read, so that variant is untested. Fixed in QEMU since: "The sun4u
  system MAC".

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
  guests on one network would clash. Fixed since by pve-qemu `wsh/0034` ("The sun4u system MAC").
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

**Tribblix on sun4u (2026-11-18).** Tribblix m34 (`tribblix-sparc-0m34.iso`, illumos built from a
pre-2024 gate, the newest SPARC release) is the first illumos tried here: QEMU issue #216 is about
an older Tribblix on sun4u (`no nucleus hblk8`, fixed by 0003). Lab, QEMU started directly, the
`_sparc64.py` layout (blank 8 GB disk on `ide.0`, the CD on `ide.1`, `sunhme`, serial console),
2048 MB:

- **Boot:** OpenBIOS boots `cdrom:f` (every slice of the CD's Sun label starts at 0; the hsfs FCode
  boot block is in sectors 1-15), the kernel prints `Welcome to Tribblix` instead of the usual
  banner, then the same harmless warnings as Solaris 10 (`could not find
  debugger-vocabulary-hook`, `ebus0 assigning default interrupt level 1 for device i80420`, `add_spec:
  No major number for sf`, `Out of range register specification from device node <fdthree>`). The
  IDE disk attaches as `dad1` at `/pci@1f,0/pci@1,1/ide@3/dad@0,0` and is `c1t0d0` (not `c0t0d0` as
  in Solaris 10); the CD is `c1t2d0`. The live CD imports its 95 SMF manifests on every boot (25-35
  minutes under TCG with other guests on the host), asks for the keyboard layout on ttya
  (Return: US-English) and comes to `tribblix console login:` after about 45 minutes. Several
  services time out on the way (`svc:/system/rbac`, `svc:/network/location`; `svc.startd` kills
  them), which costs time but nothing else. `Unimplemented service SUNW,asr-export-len` is printed
  once (an OBP extension OpenBIOS doesn't have; harmless).
- **The firmware bug (patch 0016):** with `openbios-sparc64` from 11.1.3-2+wsh15 or wsh16, or built
  from 0001-0011 or 0001-0015, 4 of 7 boots of the live CD ended with corrupted registers:
  client_handler's `%l4` (its saved `%pstate`) came back as 0 and the kernel ended in an endless
  window spill at TL 1 (twice; one of them at the live shell, just after login); or `bad stack
  overflow at TL 2` with nested trap frames from `prom_finddevice` and `%tpc` values like `0x1`
  (twice, 1024 and 3072 MB, identical register dumps). Two more hung with a dead clock (below), the
  seventh got as far as the keyboard layout question, where it was stopped. The cause: the client
  interface saves and restores the caller's register windows and trap registers with interrupts
  enabled, and illumos calls it with interrupts enabled; see
  `upstream/openbios-sparc64-client-interface-interrupts.md`. Solaris 10's one `BAD TRAP: type=4e`
  in the firmware during the `sol10-sun4u` runs is the same bug. With 0016 (firmware from the
  committed patches 0001-0011 and 0013-0016, later 0013-0017) neither came back in about ten boots:
  live CD boots in the lab and through PVE, one with 30 rounds of `prtconf -vp` and `eeprom` (device
  tree walks through the client interface) and a complete install, and the installed system's first
  and later boots. Regression with the 0013-0017 firmware: the `sparc64` matrix 9/9 and the
  `solaris10` matrix 2/2.
- **The clock stops (fixed by pve-qemu `wsh/0036`):** in 5 of 14 long runs, 2 before 0016 and 3 with it, the tick interrupt
  stopped for good: the kernel sits in its idle loop with `%pil` 0, `-d int` shows no level-14
  interrupt any more (device interrupts are still taken when a key is pressed), the kernel never
  writes `%tick_cmpr` again (QEMU trace), `%softint` holds no pending tick. Anything that sleeps hangs:
  the live CD after its SMF import (twice), during the SMF import (once, through PVE), an
  install in its package installs (once, with network downloads) and one while it configured the
  devices (through PVE). Each time with
  heavy interrupt traffic, and the two through PVE with other emulated guests busy on the host
  (leftover VMs of earlier runs). The cause: the guest's `%set_softint`/`%clear_softint` writes run in
  QEMU's vCPU thread as a read-modify-write of `env->softint` without the BQL, while the tick timer
  sets its bit from the main loop thread, so a tick that fires in between is lost
  (`upstream/qemu-sparc64-softint-race.md`, caught once in a trace: the tick fired while the guest cleared another bit, and the guest's store
  dropped it). pve-qemu `wsh/0036` takes the BQL around those writes (qtest `wsh/0037`). With it
  there were three long Tribblix runs with the fix on 2026-11-18, all passed with the clock running: `lab.py
  install tribblix-m34-sun4u --check` through PVE (257 minutes: install 141, first boot 89, check 26,
  and a further boot from the disk) and two lab installs (`tribblix-install-sparc64.py`, 141 minutes
  each: live CD login 72, install 64), all three at once with other emulated guests busy on the host.
  Before the fix 5 of 14 such runs lost the clock.
  The installed system imports the SMF manifests only on its first boot from the disk (99 of them;
  login after 70 minutes); the check boot and one more came to `console login:` after 817 and 736 s
  without importing anything, and `init 5` took 6-11 minutes.
- **Install, ZFS (Tribblix's default):** `/root/live_install.sh -G -n <host> c1t0d0` from the live
  root shell (an SMI label with one big slice 0, a ZFS pool `rpool` of version 28, a 2 GB swap zvol,
  the base overlay from the CD, `installboot -F zfs`, the boot archive) completed in 64 minutes
  (exit 0, `Welcome to Tribblix`). On the way, in both runs, FMA diagnosed `ZFS-8000-FD` ("The number
  of I/O errors associated with a ZFS device exceeded acceptable levels") a few minutes into the
  copy and marked `c1t0d0s0` DEGRADED ("too many errors"); `zpool status` showed 0 read, write and
  checksum errors and "No known data errors", `iostat -En` 0 soft, hard and transport errors on the
  disk, and `fmdump -e` 9097 `ereport.fs.zfs.io`, all but one with `zio_err = 5` (EIO), sizes from
  512 bytes to 384 KB. So single I/Os failed with EIO and succeeded when ZFS retried them. ZFS
  sends its first attempt with `B_FAILFAST`; whether `dad`/`uata` fails those early under QEMU's
  cmd646, and why, wasn't traced. The OpenIndiana SPARC README's note that root pools on the Ultra
  5/10 built-in IDE "will be unusable" (workaround: disable `fmd`) looks like the same thing on real
  hardware.
- **The ZFS boot block (patch 0017):** OpenBIOS loads the ZFS boot block from the disk and it loads
  its second stage (the `zfs-file-system` package from 512 KB into the slice), then
  `Unhandled Exception 0x0000000000000030` with the PC in `unaligned-l@`. The Forth return stack read
  from the firmware's memory after the exception showed `$open-package` → the package's `open` →
  `scan-vdev` → `x0=`, whose `xlsplit` ran `xwflips`: OpenBIOS's 64-bit FCode table lacked `xa+` and
  `xa1+`, which shifted every token from 0x24a on by two (`upstream/openbios-fcode-64bit-token-table.md`).
  With 0017 the boot block reads the pool and loads the kernel and boot archive from ZFS, and the
  installed system boots from its ZFS root.
- **Install, UFS:** `/root/ufs_install.sh -n <host> c1t0d0s0` after labelling the disk with slice 0
  for `/` and slice 1 for swap (`format-a-disk.sh`, then `fmthard`; its newfs asks `(y/n)?`). Through
  PVE it ran newfs, the copy, the overlays and `installboot -F ufs` without ZFS's EIO reports, then
  the clock stopped (below) while it configured the devices. Not booted yet; the install target
  stays with ZFS.
- **The package set:** the live CD's package catalogue names older versions than the CD carries
  (the base overlay asks for `TRIBcurl.8.12.1.1.zap`, `/pkgs` has `TRIBcurl.8.19.0.0.zap`). With a
  network the installer fetched those packages from pkgs.tribblix.org (some downloads failed with
  `has wrong size`); offline it skips them (`pkgadd: ERROR: no packages were found`: 18 skipped and
  33 installed in the ZFS run, among the skipped curl, tcsh, nss, gnutls, xz, less, GNU coreutils and
  grep), and the system they are missing from
  still boots: `live_install.sh` copies the live root first. A Tribblix issue, not reported yet.

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

**The sun4u system MAC (pve-qemu `wsh/0034`-`0035`, in review, 2026-11-18).** OpenBIOS gives the
guest the IDPROM's MAC address as the system's, and its `sunhme` node has no `local-mac-address`.
NetBSD's `hme` and `wm` and Solaris's `hme` (OBP's default `local-mac-address?=false`) program that
address into the NIC. QEMU's sun4u filled the IDPROM from the onboard `-nic` only; qemu-server and
the lab add the NIC with `-device`, which doesn't exist yet when the NVRAM is written, so the IDPROM
had `52:54:00:12:34:56` for every VM. With 0034, sun4u writes the IDPROM again once the machine is
complete: from the first `sunhme`, else from the first NIC of any model; with an onboard `-nic`, or
no NIC, nothing changes. The host id is made from the same bytes (`hostid` `80123456` before,
`80000001` with `mac=bc:24:11:00:00:01`). The alternative without a QEMU change, qemu-server passing
`-net nic,model=sunhme,macaddr=...`, puts the NIC at 01:01.1 on bus A instead of bus B: installed
Solaris systems see a new `hme` instance and leave it unconfigured, and the NIC loses its `id`.

Measured in the lab (`scenarios/_sparc64.py` with `MAC=bc:24:11:00:00:01`, the NIC with
`-device <model>,mac=...,bus=pciB` as qemu-server builds it, the installed disks, `-snapshot`):

| Guest, NIC | 11.1.3-2+wsh16 (package) | with 0034 |
| --- | --- | --- |
| NetBSD 11.1, `sunhme` | `hme0` `52:54:00:12:34:56` | `hme0` `bc:24:11:00:00:01`, DHCP lease 10.0.2.15 |
| NetBSD 11.1, `e1000` | `wm0` `52:54:00:12:34:56` | `wm0` `bc:24:11:00:00:01`, DHCP lease 10.0.2.15 |
| NetBSD 11.1, `virtio-net-pci` | `vioif0` `bc:24:11:00:00:01` | not run (the driver reads the device) |
| NetBSD 11.1, `rtl8139` | `re0` `bc:24:11:00:00:01` | not run (the driver reads the device) |
| Solaris 10 1/13, `sunhme` | `hme0` `ether 52:54:0:12:34:56`, hostid `80123456` | `hme0` `ether bc:24:11:0:0:1`, hostid `80000001`, DHCP lease, `ping 10.0.2.2` alive |

A packet capture on the netdev (`-object filter-dump`) shows the guest's frames (DHCP, ARP, ICMP)
leaving from `bc:24:11:00:00:01` with 0034 and from `52:54:00:12:34:56` without it, so a DHCP
reservation or firewall rule keyed on `net0`'s MAC now matches. The DHCP server here is QEMU's
user networking, which doesn't key on the MAC; a reservation on a real DHCP server wasn't tested.
With 0034 and the default MAC (`52:54:00:12:34:56`) Solaris boots as before (1 of 1).

The first runs used the packaged `openbios-sparc64` (without patch 0016): Solaris 10 booted to
`console login:` with 0034 and `mac=bc:24:11:00:00:01` in 3 of 5 runs, the other 2 panicked with
`BAD TRAP: type=4e` and the PC in the firmware (`0xffd0e74c` in `picld` during an `ioctl`, and
`0xffd12744` in thread 0 before user processes run); the package without 0034 booted 3 of 3. That
is the firmware bug OpenBIOS 0016 fixes (the client interface ran with interrupts enabled; "Tribblix
on sun4u"), not the IDPROM. Re-tested with 0001-0037 and `openbios-sparc64` from patches 0001-0017
(2026-11-18, the same installed disk, `-snapshot`, user networking, two boots at a time with other
guests on the host): 10 of 10 boots reached `console login:` (boot 425-553 s), no `BAD TRAP`, every
one with `hme0` `ether bc:24:11:0:0:1`, `hostid` `80000001` and `ping 10.0.2.2` alive; `init 5`
powered off each. So no comparison run without 0034 was needed.

**Solaris 7/8/9: `pp is NULL or free` (fixed by OpenBIOS patch 0024).** The kernel builds its page
structures from the boot program's copy of `/memory` `available`, and every later boot allocation
must land on a page it has a page structure for. OpenBIOS records claimed physical ranges to the
byte and builds `available` from the gaps between them; the ELF loader claims the Solaris boot
program's segments at 0x100000 with their exact sizes, so the list Solaris reads looks like
`00000000 00100000`, `00123127 00000001`, `00181540 3cef2ac0` (9 9/05, 1024 MB). Solaris 7, 8 and 9
count an entry that starts inside a page one page short at its top (measured for 8 and 9; 7's
`kmem_getpages: pp is NULL or free` goes away with the same fix), so they have no page structure
for the last page of the big entry. OpenBIOS hands out physical memory top down: once the free
pages under the firmware are used up, the next boot allocation gets exactly that page, and the
kernel panics. Solaris 10 boots with the same list.

Evidence (2026-11-19, firmware 0001-0023 plus a scratch debug patch that logs every physical
claim and release and every client `getprop` of `/memory` `available` with the list it returns;
CD on `ide.1`, serial console):

- 9 9/05, 1024 MB: the kernel reads the list five times; the last read lists `00181540 3cef2ac0`
  (end `0x3d074000`) and `3fc00000 00120000` under the firmware. Nothing is released during the
  boot. The boot allocations after that read are 8 KB `claim`s on `/memory` (align 0x1000),
  answered from `0x3fd1e000` down to `0x3fc00000`, then `0x3d072000`, the last page of the big
  entry: the panic (`translate` of the failing address at `0 >` gives `0x3d072000`).
- 8 2/02, 1024 MB: top entry `001410f0 3d254f10` (end `0x3d396000`); the failing 80 KB allocation
  ends there. 9 9/05, 2048 MB: `00181540 79e7eac0` (end `0x7a000000`); the failing 520 KB
  allocation ends there.

The earlier reading ("pages handed out after the kernel's snapshot") was wrong: every failing page
was in the snapshot, the last page of an entry with an unaligned start, and the pages under the
firmware were never released and claimed again (that was the top-down order of the claims). The
earlier table of failing allocations:

| Release, memory | Failing `boot_alloc` | First physical page | Top of `/memory` `available` at the panic |
| --- | --- | --- | --- |
| 9 9/05, 1024 MB | `0x30000058000`, 8 KB | `0x3d072000` | `0x3d062000` |
| 9 9/05, 2048 MB | `0x30000146000`, 520 KB | `0x79f7e000` | `0x79f7e000` |
| 8 2/02, 1024 MB | `0x300001be000`, 80 KB | `0x3d382000` | `0x3d37e000` |
| 8 2/02, 2048 MB | `0x300001f6000`, 80 KB | `0x7a7ec000` | `0x7a7ea000` |

Patch 0024 rounds each `/memory` `available` entry to whole pages (start up, end down) and drops
entries without one, as OBP lists them (`00182000 3cef2000` above; the 1-byte entry goes). The
allocator is unchanged: a partly claimed page is no longer listed and isn't handed out either.
With it:

**Solaris 7/8/9 with 0024** (2026-11-19; pve-qemu-kvm 11.1.3-2+wsh22 with `openbios-sparc64` built
from 0001-0024 passed as `BIOS=`; sun4u, CD on `ide.1`, a blank 8 GB disk on `ide.0`, serial
console; installs driven by a scratch wrapper around `solaris-webstart-serial.py` with the disk as
`c0t0d0`, the 64-bit question answered "64-bit and 32-bit", End User, auto-boot? false):

| Release | 1024 MB | 2048 MB |
| --- | --- | --- |
| 9 9/05 DVD (`Generic_118558-34`) | installer; Web Start installs End User to the IDE disk (~67 min, ~53 of them packages); the installed disk boots to `console login:`, root logs in, 64-bit kernel, `hme0` 10.0.2.15, `init 0` to the firmware (after a first boot that panics in `fd`, below) | installer (`Select a Language`) |
| 9 DVD (`Generic`) | installer (`Select a Language`) | installer |
| 8 2/02 (`Generic_108528-13`) | installer; mini-root to the swap slice, Web Start from it installs End User (Software 1 of 2 swapped in; ~47 min); the installed disk boots to `console login:`, as 9 9/05 | installer (`Do you want to format`) |
| 8 1/01 (`Generic_108528-05`) | installer (`Do you want to format`) | installer |
| 7 3/99 (`Generic_106541-02`) | installer (`Select a Language`), with IDE timeouts and `Interrupt not seen after set_features` on the way | installer |

Installs with 2048 MB and of 9 (original), 8 1/01 and 7 weren't run. What else stood in the way,
none of it from 0024:

- **The reboot** returns from the firmware (0012, `.wip`; fixed since by 0030, "The firmware reboot
  on sun4u"): Solaris prints `prom_reboot: reboot call returned!`, panics on it, dumps and exits to
  `0 >`. For 8's mini-root step that is where the
  install continues: `boot disk:b` after `reset-all` panicked the mini-root's kernel (`page_free` ←
  `add_physmem` ← `kphysm_init`; OpenBIOS doesn't clear RAM on reset and the old contents are still
  there), while a fresh QEMU boots `disk:b` and the install goes on. An install target for 8 would
  need a power cycle there, as a PVE VM gets with stop and start: `sol8-sun4u` does that (below).
- **The floppy node.** The first boot of the installed 9 9/05 reconfigures (`Configuring /dev and
  /devices`) and panics in the floppy driver: `BAD TRAP: type=31 ... occurred in module "fd" due to
  a NULL pointer dereference`, `ddi_regs_map_setup` ← `fd_cleanup` ← `fd_attach`. OpenBIOS's
  `fdthree@0,0` under the ebus has one `reg` entry of size 0 (`Out of range register specification
  from device node <fdthree>`, which 8 and 10 print and survive); 9's driver fails to map it and
  crashes on the way out of its attach. Renamed at `0 >` before the boot (`"
  /pci@1f,0/pci@1,1/ebus@1/fdthree" find-device`, `" nofdthree" device-name`, `device-end`) the
  boot finishes, and later boots (no reconfiguration) reach `console login:` without the rename.
  Fixed since by OpenBIOS patch 0025, which leaves the node out on sun4u (below).
- The lab's own early stop: the first 8 2/02 disk boot wanted a manual `fsck` (done in single user,
  then the boot above) because the wrapper stopped QEMU right after the installer's last Return,
  before Solaris had synced; the wrapper now waits for the firmware prompt (not repeated for 8).

Regression with the 0001-0024 firmware bind-mounted over the package's (2026-11-19): the `sparc64`
matrix 9/9, `solaris10` 2/2 (the DVD to the installer, the installed disk to login with DHCP and
ping), the installed OpenBSD 8.0 disk to `login:` and `halt -p`, the stored Tribblix m34 disk to
`login:` and `init 5` (`tribblix-boot-disk.py`, 2048 MB, 21 min), and `smoke` 3/3 (the sparc32
image doesn't get 0024; same sources as the package's).

**Solaris 8 and 9 install targets on sun4u** (2026-11-19). `sol9-sun4u` (9 9/05, the DVD) and
`sol8-sun4u` (8 2/02, the Installation CD and Software 1 of 2) are the Web Start installs of
`sol9-ss5`/`sol8-ss5` on the sparc64 profile (1024 MB, a blank 8 GiB disk on `ide0` = `c0t0d0`, the
CD on `ide2`, `sunhme`, serial console), End User, through PVE with `lab.py install` (e2e/sparc/README.md,
"Solaris 8 and 9 on sun4u"). What had to change:

- **The floppy node** (OpenBIOS patch 0025): the ebus's `fdthree` is gone on sun4u. The fix chosen
  over OBP-like `reg` entries: OBP's node on the Ultra 5/10 has three of them (the 82077, the ebus
  DMA engine that drives it, the auxio register) plus an interrupt, while QEMU's sun4u has a
  PC-style FDC at I/O `0x3f0` behind the ebus's second BAR, created without DMA
  (`hw/sparc64/sun4u.c`), and neither a DMA engine nor auxio. No `reg` set would describe a
  controller a driver for OBP's node can run, and entries pointing at nothing would let a driver
  attach and then wait for DMA. OpenBIOS never booted from the node either (`-boot a` sets
  `boot-device` to `/obio/SUNW,fdtwo`, sun4m's path), and NetBSD left it unconfigured (`fdthree at
  ebus0 addr 0-ffffffff not configured`). With 0025 the installed 9 9/05's first, reconfiguring boot
  goes through without the rename, and none of the installs prints `Out of range register
  specification from device node <fdthree>` any more.
- **The reboot** (no firmware change then; 0030 has fixed it since, "The firmware reboot on sun4u",
  and the scenario stops the VM at the firmware's banner and resets for the mini-root instead of
  power-cycling): Solaris's reboot returns (`prom_reboot:
  reboot call returned!`), the kernel panics and exits to `0 >`. `solaris-webstart-serial.py` waits
  for that prompt (Solaris has synced by then) and, at the end of the install, stops the VM there as
  `sol10-sun4u` does; `install` then ejects the media and boots `ide0`. For 8's reboot into the
  mini-root it power-cycles the VM through PVE (`lab.PveMachine.power_cycle()`: `qm stop`, `qm
  start`, the serial console reconnected, the step log and recordings go on) and boots `disk:b` at
  `0 >` (the install phase has `-prom-env auto-boot?=false`, as the sun4m Solaris 8 targets). A fresh
  QEMU process is what `reset-all` doesn't give: OpenBIOS keeps the RAM's contents across a reset,
  and the mini-root's kernel then panicked in `page_free`.
- The sun4u answers: the 64-bit question defaults to "64-bit and 32-bit support" (kept), the disk is
  `c0t0d0` (`DISK`), and with `auto-boot?` false the CD is booted at `0 >` (`boot cdrom:f`;
  `_sparc32.prom_boot()` for `ARCH` sparc64). The first boot and the check are the sun4m targets'
  `solaris-firstboot.py` and `solaris-boot-disk.py` (the VM's `-boot order=c` boots the disk).

Results through PVE (the PVE test container from `e2e/pve/Dockerfile` with the lab, published
pve-qemu-kvm 11.1.3-2+wsh23, qemu-server 9.2.19+wsh1, pve-manager 9.2.31+wsh1; "0025" = an
`openbios-sparc64` built from `openbios/` with 0001-0025 mounted over the package's; up to two guests
on the host at once, 2026-11-19):

| Run | Result | Time |
| --- | --- | --- |
| `install sol9-sun4u --check` (0025) | passed: the first boot reconfigures (`Configuring /dev and /devices`) without a panic, root/`wshlab`, the marker, `SunOS sol9-sun4u 5.9 Generic_118558-34 sun4u`, `/` 1126422 KB on `c0t0d0s0`, `hme0` 10.0.2.15/24, `boot: order=ide0`, `ide2` empty | 70.0 min (install 3559 s, first boot 401 s, check 215 s) |
| `install sol8-sun4u --check` (0025) | passed: one power cycle after the mini-root copy, Software 1 of 2 swapped in, `SunOS sol8-sun4u 5.8 Generic_108528-13 sun4u`, `/` 738902 KB, no `fdthree` warning in any phase | 56.9 min (2752 s, 378 s, 264 s) |
| `install sol8-sun4u --check` (the package's firmware) | passed; the `fdthree` warning in the install and first boot, as before | 53.4 min (2536 s, 382 s, 267 s) |
| `install sol9-sun4u --check --export` (0025), a second run | passed, the same checks; the disk and its sidecar exported | 67.2 min (3393 s, 405 s, 217 s) |
| `matrix.py sparc64` (0025) | 9 of 9 passed: NetBSD 11.1 and 9.3, OpenBSD 8.0 and Debian 12 CDs, NetBSD 11.1 on `std` VGA, install, disk, virtio and idle | 18 min (the cases added up) |
| `matrix.py solaris10` (0025) | 2 of 2 passed: the DVD and the installed disk | 12 min (the cases added up) |
| `boot-test` of the stored disks (0025): `openbsd80-sun4u`, `netbsd111-sparc64`, `sol10-sun4u`, `tribblix-m34-sun4u` | 4 of 4 passed | 3.4, 1.7, 8.6, 25.5 min |
| unit tests (`test_targets.py` with `WebStartSun4u`, `test_stored_disks.py`, `test_dos.py`, `test_freedos.py`, `test_netbsd.py`, `test_vgatext.py`; Docker, `--network none`) | 149 passed, 2 skipped | 6 s |

So 0025 breaks none of the sun4u guests the lab runs (the last four rows, all with 0025; the CI
install matrix ran on the same host at the time). `sol9-sun4u` had `matrix_skip` until a published package had 0025 (pve-qemu-kvm 11.1.3-2+wsh25);
`sol8-sun4u` runs with the published packages and is installed by `pve_matrix.py install` (about 55
min the first time, then a boot test of its stored disk).

**Solaris 7 install target on sun4u** (2026-11-20). `sol7-sun4u` (7 3/99, End User) runs suninstall
(`solaris-install-serial.py`) on the sparc64 profile with 2048 MB, the SUN2.9G label on a 3 GiB IDE
disk (`c0t0d0`; suninstall lists only labelled disks) and the CD on `ide2`; at the end `halt` returns
to `0 >` and the VM is stopped there. With 1024 MB the installer's kernel panicked in both installs as
the package copy began (`segkp_badop`; `BAD TRAP ... type=0x31` in `pkginstall`, an illegal access to
a user address in `unix`); with 2048 MB the package copy went through twice. Not diagnosed: whether
OpenBIOS's memory layout at 1 GB or the guest is at fault. The IDE timeouts and `Interrupt not seen
after set_features` on the CD's boot cost about 4 minutes and break nothing; in two runs suninstall
didn't react to F2 for 10 minutes (the kernel alive), which the scenario now answers with a second
F2 after 180 s. Installed through PVE with pve-qemu-kvm 11.1.3-2+wsh26 in 24.5 min, the 64-bit
kernel on the installed disk (`SunOS Release 5.7 Version Generic_106541-02 64-bit`); e2e/sparc/README.md,
"Solaris 7 on sun4u"; the stored disk boot-tests in 4.4 min.

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

**Solaris 2.5.1 and 2.6 on sun4u: the boot block (OpenBIOS patch 0031, 2026-11-22).** Both CDs are
for the hardware class QEMU's sun4u emulates: their mini-roots have `/platform/SUNW,Ultra-5_10` and
the Ultra 5/10 drivers (`uata` for the cmd646, `dad` for `ide-disk`, `atapicd` for `ide-cdrom`,
`simba`, `pci`), so an SBus Ultra isn't needed. With the published firmware (pve-qemu-kvm
11.1.3-4+wsh2, OpenBIOS 0001-0029; the lab's QEMU, 1024 MB, CD on `ide.1`) both stop as before:
`Evaluating FCode...`, `open isn't unique.` (a harmless redefinition warning that 7 prints too),
`?go:`, `byte-load: exception caught!`, back at `0 >`.

The cause: their boot block on slice `f` (FCode UFS Reader 1.6 on 2.5.1, 1.10 on 2.6) reads
`/platform/sun4u/ufsboot` into a buffer of its own, copies the ELF segments to their addresses
itself, and then evaluates `to load-base init-program` with `load-base` set to the entry point,
followed by `?go`. OpenBIOS's `init-program` only knows images with a header (ELF, a.out, FCode,
Forth), so it set nothing up, and OpenBIOS has no `?go` at all: the `evaluate` of `?go` threw, and
`byte-load` caught it. Solaris 7's boot block (Reader 1.11) hands `init-program` the whole ELF image
instead, which is why 7 and later never hit this. It is the same family of gap as the sparc32
patch 0019 for the 2.1-2.4 boot block.

0031 redefines `init-program` in the sparc64 dictionary for callers that look it up by name (the
copy `load` calls is compiled in and unchanged): it clears `state-valid` (the boot block runs from
`go` and left it set), lets the loaders look at `load-base` as before, and when none recognises it,
takes it as code that starts at `load-base`, as OBP does. It adds `?go`, which starts the program
when `init-program` set one up.

With 0031 the boot block works on both CDs; each then stops further on, in places that have
nothing to do with the boot block:

| CD | With 0031 |
| --- | --- |
| 2.6 (5/98) | ufsboot loads the kernel (`SunOS Release 5.6 Version Generic_105181-05`), then `Cannot assemble drivers for root /pci@1f,0/pci@1,1/ide@3/cdrom@2,0:b`, `vfs_mountroot: cannot mount root` (the same with 512 and 1024 MB; with `-v`, no driver attach line before it) |
| 2.5.1 (11/97) | ufsboot loads the kernel and starts it; before the banner, `Unhandled Exception 0x30` with the PC in the kernel's `sfmmu_add_nucleus_hblks`, reading the first page past the kernel's data segment (`0x104cc000`, the nucleus hme blocks the kernel puts in the rest of its 4 MB data page) |

Both are traced and fixed in "Solaris 2.6 and 2.5.1 on sun4u: the kernels" below (openbios
0036-0039). The guesses that stood here were half right: 2.6 did fail in the sabre's `pci` driver, but
on `ranges`, not `reg`; 2.5.1's page was indeed never mapped, because its boot program aligned
nothing without a property OpenBIOS lacked.

Regression with firmware built from 0001-0029 + 0031 (`openbios/Dockerfile`), bind-mounted over the
package's in the lab image (pve-qemu-kvm 11.1.3-4+wsh2), copies of the stored disks: the installed
NetBSD 11.1, OpenBSD 8.0, Solaris 7, 9 and 10 and Tribblix m34 (ZFS boot block) disks boot to their
login prompts and log in (8 of 8 with the two CDs below; Tribblix 35 min, the others 1.4-8.2 min), and
the Solaris 10 1/13 DVD and the Solaris 7 CD reach their installers' first questions. Not run with
0031: Solaris 8, Debian, the NetBSD and OpenBSD CDs, anything through PVE. Again with firmware from
0001-0031 including 0030 (the firmware reboot), on the published pve-qemu-kvm 11.1.3-4+wsh4:
`sparc64-reboot.py` on the stored NetBSD 11.1 disk (5.6 min) and Solaris 10 disk (31 min) passed,
login, a reboot from the guest through 0030 back to the banner and to login again; the 2.6 CD
reaches `SunOS Release 5.6` and the 2.5.1 CD its `Unhandled Exception 0x30`, as above.

**Solaris 2.6 and 2.5.1 on sun4u: the kernels (OpenBIOS 0036-0039, 2026-11-23).** Traced on the lab
with the published pve-qemu-kvm 11.1.3-4+wsh12 and `openbios-sparc64` built from `openbios/` (0001-0034),
the CDs on `ide.1`, 1024 MB, `-nographic`. Neither kernel has a working debugger under OpenBIOS, so the
tools were QEMU's gdbstub (`-s`, breakpoints by address in `unix`, in `genunix` found through a call
into `unix`, and in the loaded `pci` module; the `genunix` that runs is `/platform/sun4u/kernel/genunix`,
not `/kernel/genunix`), QEMU's trace events, and breakpoints on OpenBIOS's own `ofmem_claim*`/`ofmem_map`
for the boot program's memory requests. Sun's 2.6 source on the lab served as the reference for what
the kernel expects; nothing of it is in the repository.

- **2.6: the sabre's `ranges`.** `boot cdrom -v` added nothing (the boot arguments do reach ufsboot:
  `-a` asks for the kernel's name), and the kernel never touched the sabre: no write to its control or
  IOMMU registers, no PCI configuration access after the banner. The root path is resolved one
  component at a time; `/pci@1f,0` binds to the `pci` driver (major 111), `drv/pci` loads (module id
  21) and is unloaded again because no instance attached (`moddebug` set through the gdbstub shows the
  load and unload, nothing else). In the driver, `pci_identify` succeeds and `pci_attach` returns
  failure from its `ranges` check without printing anything: 2.6's `pci` (psycho and sabre in one
  driver) takes a `ranges` property only with at least four entries of seven cells. OpenBIOS's sabre
  had three (configuration, I/O, 32-bit memory); OBP lists the 64-bit memory space as a fourth.
  Solaris 7 and later (`pcipsy`) accept three. openbios 0036 adds the fourth entry, 64-bit memory over
  the same window. With it 2.6 attaches the bridge, simba, `uata`, `dad` and `atapicd`, mounts root
  from the CD and reaches the installer's `Select a Language`.
- **2.5.1: the 4 MB nucleus and `aligned-allocator`.** The kernel's ELF carries a page-size hint (4
  MB): the kernel expects its text and its data to be loaded as whole 4 MB pages and puts the hme
  hash and the nucleus hme blocks in the rest of the data page (from `0x104cc000` here, up to
  `0x10800000`). 2.6's ufsboot always honours the hint on sun4u: it claims `0x10000000` and
  `0x10400000` with 4 MB each, 4 MB aligned. 2.5.1's ufsboot claimed only the segments' sizes (text
  `0x40000`, data `0x26000`, then krtld's pieces up to `0x10440000`), so the kernel's first access to
  the nucleus blocks was a miss on an unmapped page. Its ufsboot honours the hint only when `/openprom`
  has an `aligned-allocator` property (as sun4m's ufsboot does in the 2.6 source); OBP has it, and
  OpenBIOS's sparc32 tree has it, the sparc64 tree didn't. openbios 0037 adds it.
- **2.5.1: locked translations.** With 0037 the banner came (`SunOS Release 5.5.1 Version
  Generic_103640-12`), then `panic: map_prom: locked translation is not global`. When it takes the
  firmware's `translations` over, 2.5.1 panics on an entry above the kernel base that has the TTE lock
  bit without the global bit; 2.6 and later panic on a global entry and clear the lock bit. OpenBIOS
  listed its own text and heap (locked in the TLB) with the lock bit. openbios 0038 leaves the lock bit
  out of the property, as OBP's list must for both releases to boot; the firmware's TLB entries stay
  locked. With 0036-0038 2.5.1 reaches the installer's `What type of terminal are you using?`.
- **The installed system: the platform name.** With 0036-0038 the 2.6 install to the IDE disk
  finished, and its first boot stopped right after the boot block: `krtld: error during initial
  load/link phase`, then `Unhandled Exception 0x0a` at PC 0. The installed root lacked
  `/platform/sun4u/kernel/cpu/SUNW,UltraSPARC-IIi` (the CD's mini-root has it), which the kernel
  linker loads before anything else. In 2.6 that entry is a link in a platform package (SMCC platform
  links), and the installer adds such packages by the root node's name (its dynamic cluster tests
  compare the first node name `prtconf` prints with a list of platforms: `SUNW,Ultra-5_10` is on it).
  OpenBIOS's root was `OpenBiosTeam,OpenBIOS`, so only the generic sun4u set went on. openbios 0039
  names the root `SUNW,Ultra-5_10`, as OBP does on that machine; Solaris looks for its kernel under
  `/platform/<name>` first and falls back to `/platform/sun4u`, so disks installed under the old name
  boot as before (the regression below), and the 2.6 and 2.5.1 CDs boot with it too (2.5.1 now also
  prints `kbd: Unknown keyboard type, Type 3 assumed`).

Both installers print the 8042 warnings of the sun4u keyboard node (`Out of range register
specification from device node <8042>`, `kd_attach regs map setup 2nd failed`), harmless here (the
console is ttya), and 2.6 the IDE timeouts on the way to the first prompt that Solaris 7 prints too
(about 3 minutes from the banner to `Select a Language`). Two more things seen, not followed further:
both releases' `hme` driver prints `Using Internal Transceiver` and `100 Mbps half-duplex Link Up`
again and again while the installer runs (at times every few seconds for minutes; Solaris 7 every 30
s), as if it kept renegotiating with QEMU's `sunhme` PHY, and 2.6 printed `WARNING: interrupt level 12
not serviced` (a spurious interrupt at PIL 12) once or twice per boot. Neither stopped anything; the
install scenario had to learn to read its screens past them (e2e/sparc/README.md, "Solaris 2.6 and
2.5.1 on sun4u").

Results through PVE (the PVE test container with the published pve-qemu-kvm 11.1.3-4+wsh12, qemu-server
9.2.20+wsh7, pve-manager 9.2.32+wsh12, `openbios-sparc64` from `openbios/` with 0001-0034 and 0036-0039
mounted over the package's; 2026-11-24):

| Run | Result | Time |
| --- | --- | --- |
| `lab.py install sol26-sun4u --check --export` | passed: suninstall End User on `c0t0d0`, `SunOS sol26-sun4u 5.6 Generic_105181-05 sun4u sparc SUNW,Ultra-5_10`, `hme0` static; `init 5` ends QEMU | 28.0 min |
| `lab.py install sol251-sun4u --check --export` | passed, with the CD's Maintenance Update (kernel `Generic_105428-01` afterwards); `init 5` ends QEMU | 66.8 min |
| `lab.py boot-test` of both stored disks | passed, `console login:` after 3.0-3.4 min | 3.9-4.3 min |
| `e2e/wisp` `run.py --arch sparc64 --repeat 2` (wisp's Linux) | passed, both runs | 3.4-3.6 s each |

Regression, boot-tests of the stored sun4u disks (`pve_matrix.py install`, each disk imported into a new
VM, the target's check: login, the marker, commands, power-off), with 0036-0038 and with 0036-0039:

| Stored disk | 0036-0038 (load 5-15) | 0036-0039 (load 2-6) |
| --- | --- | --- |
| NetBSD 11.1, 9.3 | passed (155 s, 133 s) | passed (123 s, 83 s) |
| OpenBSD 8.0 | passed (450 s) | passed (270 s) |
| FreeBSD 12.4 | passed (251 s) | passed (123 s) |
| Solaris 10 1/13 | passed (872 s) | passed (621 s) |
| Solaris 9 9/05, 8 2/02, 7 3/99 | passed (248 s, 319 s, 281 s) | passed (222 s, 275 s, 251 s) |
| Tribblix m34 | logged in, checked; `init 5` still stopping services at the 3600 s limit (services timing out under the load), counted as failed | passed (1514 s) |
| Debian 13 | emergency mode: `/boot` and swap by UUID timed out (udev under the load), counted as failed | passed (319 s; also alone, 5.3 min) |
| Debian 7.11 | passed (666 s) | passed (268 s) |

Both failures of the first round were the host's load, not the firmware: the same disks passed with
0036-0039 once the load was lower. The CDs of NetBSD, OpenBSD, Debian and Solaris 7-10 weren't booted
again; Solaris 10 isn't reinstalled (its installer now sees `SUNW,Ultra-5_10` and may add that
platform's packages). wisp's Linux (above) is the only boot of a kernel from scratch with 0039.

Published in pve-qemu-kvm 11.1.3-4+wsh15 (its `openbios-sparc64` has `SUNW,Ultra-5_10` and
`aligned-allocator`). With it, nothing mounted over the package, both stored disks boot-test through
PVE (2026-11-24, load average 22-43 on 14 cores): `sol26-sun4u` 5.8 min (`console login:` after 4.5),
`sol251-sun4u` 5.3 min (4.1). `sol26-sun4u` and `sol251-sun4u` no longer have `matrix_skip`
(e2e/sparc/README.md, "Solaris 2.6 and 2.5.1 on sun4u").

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
- Guests: NetBSD (11.1 tested end to end, 9.3's CD boots), OpenBSD 8.0 (with openbios 0023,
  pve-qemu-kvm 11.1.3-2+wsh22: the install target `openbsd80-sun4u`, ntpd off; rare IDE timeouts
  that stop the guest, "sparc64"), not Debian 12.0 ports (install fails), not Solaris for real use (with the
  package built with `openbios-sparc64` and `wsh/0021`, Solaris 10 1/13 reaches its installer and
  takes input on ttya, and its IDE disk attaches; installing, rebooting and booting the installed
  disk don't work yet, see "Solaris on sun4u"), not sun4v/niagara.
- Refuse: SCSI (LSI, virtio-scsi) and virtio-blk as the boot disk, `-smp` > 1, more than 8 GB,
  `sun4v`/`niagara`. Idle: with pve-qemu `wsh/0042`-`0044` an idle guest takes 3-9% of a host core
  (NetBSD, OpenBSD, Solaris 9/10; Tribblix about 22% with `fmd` off; "Idle" above), before them 100%
  for as long as the VM ran.
- Snapshots with RAM (`qm snapshot --vmstate 1`, `qm rollback`) and `qm suspend --todisk` work with
  pve-qemu `wsh/0133` ("Snapshots and migration on sun4u"); before it the guest resumed without
  interrupts. Live migration between nodes: not tested (single node), and qemu-server's migration
  still reads `-cpu` from the running VM ("Backup and restore"). Backup of a running guest: not tested.

### The firmware reboot on sun4u (OpenBIOS 0030, pve-qemu `wsh/0068`-`0069`, 2026-11-22)

Every system that runs on QEMU's sun4u reboots through the client interface's `boot` service, with
a boot string: Solaris 7 to 10 (`reboot`, `init 6`, `uadmin`, the installers' reboots: `mdboot()`
→ `prom_reboot()`), Linux (`machine_restart()` → `prom_reboot()`) and NetBSD/OpenBSD (`OF_boot()`).
None of them expects it to return. OpenBIOS's `boot` printed `BOOT` and returned: Solaris panicked
with `prom_reboot: reboot call returned!` and exited to `0 >`, Linux panicked with `Reboot
failed!` (with `panic=-1` it tried again for ever, which is why wisp's shell refused `reboot` on
sun4u). OpenBIOS 0012 (`.wip`) made `boot` call `reset-all`, which writes the sabre's reset control
register (`0x1fe0000f020`, bit 29); QEMU then resets the machine (`qemu_system_reset_request`) and
the CPU starts the firmware at its reset vector (`prom_addr + 0x20` on QEMU's first reset, `+ 0x40`
after that). The reset itself worked; the firmware and the next system didn't survive what QEMU's
reset leaves behind. `cpu_reset()` clears `CPUSPARCState` only up to `end_reset_fields`: SOFTINT,
the interrupt receive register, the timers' NPT bits, the MMU registers and the TLBs are kept, and
QEMU never clears RAM on a reset (the TLBs the firmware clears itself). What went wrong, in the
order the lab found it (scenario `sparc64-reboot.py`, the stored disks, standalone QEMU from the
published 11.1.3-3+wsh13):

- **A pending soft interrupt.** Solaris 10's `mdboot()` raises the PIL (`spl6`) and the client
  interface runs with interrupts off (0016), so a level 6 soft interrupt was still set in SOFTINT
  when the machine reset. `entry` enables interrupts early, the level 6 trap went to `handler_irq`
  (the firmware's `bug`) and the firmware stopped before its banner: `Unhandled Exception
  0x0000000000000006`, PC at the instruction after `entry`'s `wrpr ..., %pstate`. That is 0012's
  hang (its earlier test saw no output in 900 s; here the exception was printed). An interrupt
  vector received but not taken would have blocked every later interrupt in the same way
  (`cpu_check_irqs()` returns while the busy bit is set). 0030 clears SOFTINT and the interrupt
  receive register in `entry`, before interrupts are on.
- **TICK.NPT.** A power-on reset sets it; the guests clear it. `softint_irq` doesn't re-arm the
  firmware's 100 Hz timer while NPT is set, so after a power-on the firmware takes one timer
  interrupt and no more. After a guest's reboot the timer kept firing: into the MMU miss handler at
  TL 1, whose level 14 vector only retries without clearing SOFTINT, so the CPU spun there
  (NetBSD's `ofwboot` hung after its banner; `info registers`: PC on the `call` into the miss
  handler, `tl: 1`, `pstate: 16`), or into the next kernel before it had its own handler (NetBSD's
  kernel stopped in ddb: `kernel trap 30: data access exception`, `tt=4e`). 0030 sets NPT again in
  `entry`. At `ok` neither of these is set (the firmware never clears NPT), which is why
  `reset-all` there worked.
- **The RAM.** Solaris expects the zeroed RAM of a power-on: after a reset Solaris 10 panicked in
  `kphysm_init` (`panic[cpu0]/thread=180e000: prom page locked`, `kphysm_erase` ←
  `diff_memlists` ← `kphysm_init` ← `startup_memlist`) and Solaris 9 in `startup_memlist`, on the
  page structures of the system before; Solaris 8's mini-root panicked in `page_free` after
  `reset-all` (above, "Solaris 8 and 9 install targets on sun4u"). 0030 marks the power-on vector
  (`%l7` 0 at `0x20`, 1 at the others, stored in `sparc64_warm_reset`) and, after any later reset,
  `openbios()` clears the RAM below the firmware's own (the top of RAM, from `entry.S`), except a
  kernel and an initrd QEMU loaded with `-kernel`/`-initrd`: QEMU writes those back on every reset
  (the first version cleared them too, and wisp without `-no-reboot` stopped with `Unhandled
  Exception 0x10` at `0x40004000` after `Kernel already loaded`). It costs a few seconds per reset
  (1 GB), none at power-on.
- **The sabre's PCI control/status registers** (`0x2000`-`0x202f`) kept what Solaris last wrote,
  its error bits among them, and every Solaris boot after a reset warned `WARNING: pcipsy0: SERR
  asserted on pci bus` (harmless; never on a power-on). pve-qemu `wsh/0068` clears them in
  `sabre_reset()`, qtest `sun4u-sabre-reset-test` (`wsh/0069`).

The boot string isn't kept (as on sparc32, "Known gaps"): the firmware boots its boot device again,
so Solaris 8's `reboot -- disk:b` into its mini-root still needs `auto-boot?` false and `boot disk:b`
at `0 >`, but no power cycle any more. QEMU's own reset path (QMP `system_reset`, PVE's Reset)
goes through the same firmware entry, so it gets the same clean state.

Results (2026-11-22, lab host, up to five guests at once; "reboots" = `sparc64-reboot.py` with
`REBOOTS=3` on a copy of the stored disk, the firmware's banner back and the login prompt again
after each, in one QEMU process; QEMU is the published 11.1.3-3+wsh13 unless "+0068"):

| Run | Firmware, QEMU | Result |
| --- | --- | --- |
| Solaris 10 1/13 (`install-sol10-sun4u`), `reboot` x3 | 0030 | passed: banner 17-19 s after `reboot`, `console login:` again after 390-451 s; `SERR asserted` on each boot after a reset |
| Solaris 9 9/05 (`install-sol9-sun4u`), `reboot` x3 | 0030 | passed (10-13 s to the banner, ~180 s to login); `SERR` after each reset |
| Solaris 9 9/05, `reboot` x3 | 0001-0030, +0068 | passed, no `SERR` warning |
| Solaris 7 3/99 (`install-sol7-sun4u`, 2048 MB), `reboot` x3 | 0001-0030 | passed (10-13 s, ~207 s) |
| NetBSD 11.1 (`install-netbsd111-sparc64`), `reboot` x3 | 0030 | passed (8 s, ~80 s) |
| OpenBSD 8.0 (`install-openbsd80-sun4u`), `reboot` x3 | 0030 | passed (21-70 s, ~250 s) |
| wisp, Linux 7.3 on sun4u: `run.py --shell --reboot` x3, `--shell --tier2 --reboot`; without `-no-reboot` | 0030 | passed: QEMU exits 0 on the reset; without `-no-reboot` wisp boots again |
| the same with the published firmware | package (11.1.3-3+wsh13) | failed as before: `Reboot failed!` panics in a loop |
| wisp, `run.py --arch all --shell --reboot` as the workflow runs it (sparc64 added to that run) | published 11.1.3-4+wsh4 (0030) | passed on all four: sparc64 at the prompt in 3.2 s, QEMU's exit 0 after `reboot` at 3.6 s; `--repeat 3` on sparc64 2.6-2.8 s each; without `-no-reboot` the shell is back 2.9 s after `reboot` (a second banner, no panic) |
| `matrix.py sparc64`: `nb111-reboot-sparc64` (`reboot` x2), `nb111-reboot-bootstr-sparc64` (`reboot -- netbsd` x1) | published 11.1.3-4+wsh4 (0030) | passed: banner 12-17 s after `reboot`, `login:` again after 84-99 s; the boot string case boots `disk:a` again (`Trying disk:a...`: the string is dropped) |
| `install sol8-sun4u --check` through PVE (the PVE test container, qemu-server 9.2.20+wsh6) | 0030 | passed in 54.8 min (install 2622 s, first boot 375 s, check 265 s): two firmware resets (the mini-root reboot, the end), no power cycle |
| `matrix.py sparc64`, `matrix.py solaris10` | 0001-0030, +0068 | 10/10, 2/2 |
| wisp sun4u batch, `--shell`, `--tier2`, `--shell --tier2` | 0030 | all passed |
| `make check-qtest-sparc64` | 0001-0030 in `pc-bios`, +0068-0069 | 20 OK (`sun4u-sabre-reset-test`, `prom-env-test`, `boot-serial-test` among them), 2 skipped, `qmp-test` fails as before (the PVE patches) |

Before 0030's RAM clear, with only the SOFTINT and NPT fixes, Solaris 9 and 10 reached their
kernels after a reset and panicked in `startup_memlist`/`kphysm_init`; NetBSD and OpenBSD passed.
Not tried: Tribblix (illumos uses the same `prom_reboot()`), Solaris 8 from an installed disk
(no stored disk; its installer's two resets passed), a reboot with more than 3 GB of RAM (the clear
covers it, not measured). Debian 7 (Linux 3.2) reboots, but the RAM clear took minutes after Linux
had run until pve-qemu `wsh/0112` ("Debian 7 on sun4u" below).

### Debian 7 on sun4u (pve-qemu `wsh/0110`-`0113`, 2026-11-22)

Debian GNU/Linux 7.11 "wheezy" (2016-06-04), the last official Debian release for sparc: a 32-bit
userland on the sparc64 kernel (Linux 3.2.78, `3.2.0-4-sparc64`, gcc 4.6.3) and SILO 1.4.14 as the
boot loader. Media from cdimage.debian.org's archive (`7.11.0/sparc/iso-cd/`): the netinst (181 MB)
and CD 1 (680 MB), checked against the release's `SHA256SUMS` and `SHA512SUMS`, whose signatures
check with `gpgv` against debian-keyring's role keys (the Debian CD signing key). The lab's own QEMU
(the published pve-qemu-kvm 11.1.3-4+wsh3 unless said otherwise), `_sparc64.py`'s layout (IDE disk
and CD, `sunhme`), 512 MB (1024 MB for the first install), serial console. Installed as the lab
target `debian7-sun4u` (e2e/sparc/README.md, "Debian GNU/Linux 7 on sun4u").

- **Boot from the CD.** OpenBIOS loads SILO's first stage from the CD (`Trying cdrom:f...`, `Not a
  bootable ELF image`, `Loading a.out image...`), SILO prints `EXT2 superblock magic is wrong` twice
  (it probes the ISO 9660 partition) and its `boot:` prompt; `install` loads `/boot/sparc64` and
  `/boot/initrd.gz`. Linux 3.2 finds the CMD646 (`pata_cmd64x`, UDMA/33), the disk and CD, `sunhme`
  (`eth0`) and the serial console (`OF stdout device is: /pci@1f,0/pci@1,1/ebus@1/su@14,3f8`). The
  netinst and CD 1 both reach "Select a language". The QEMU wiki's "requires -nographic" for 7.8 is
  about the display: with `-vga none` (a serial console) nothing else is needed.
- **Install.** A preseed file on a second CD (the secondary IDE slave, `sr1`), loaded by
  `preseed/early_command` from SILO's boot line, answers everything: static `eth0`, no network mirror,
  partman's recipe on the blank disk (it writes the Sun label: `/boot` ext2, `/` ext3, swap), the
  kernel, tasksel's "SSH server". 84 minutes from the boot line to the reset in the first run (1024
  MB, a host load of 4-17): partitioning after 9 min, the base system 20-56 min (the kernel at 48),
  extra packages and the initramfs until 71, `apt-setup`, the SSH task and SILO until 84. Nothing
  crashed: no `dpkg-deb` segfault as with Debian 12's 64-bit userland (above), no soft lockup. Through
  PVE (`lab.py install debian7-sun4u --check --export`, published packages, 512 MB, a host load of
  2-4) the install took 61.6 minutes, all of it 68.5 with the first boot and the check; 182 packages
  (the base system and OpenSSH; no "standard system utilities" task).
- **SILO under OpenBIOS.** The historic reports (CRC errors in 2008, initrd read errors in 2013)
  don't happen here: SILO reads `/etc/silo.conf` from `/boot` on `sda1`, uncompresses the kernel
  ("Allocated 64 Megs of memory at 0x40000000 for kernel"), loads the 10 MB initrd ("Loading initial
  ramdisk (10109674 bytes at 0x4400000 phys, 0x40C00000 virt)") and boots `root=/dev/sda2 ro` by
  itself after its 10 s timeout. No OpenBIOS change was needed.
- **The installed system.** `login:` on `ttyS0` 152-164 s from QEMU start (126-150 s from SILO);
  `sshd` on port 22; static and DHCP on `eth0` (QEMU's user network: 10.0.2.15, router 10.0.2.2,
  name server 10.0.2.3); `apt-get update` from `archive.debian.org` (`KEYEXPIRED` warning; "Happy
  Meal out of receive descriptors, packet dropped" once under that load); `poweroff` ends QEMU with
  exit code 0 after 15 s.
- **GRUB on Debian 9/10 ports** ("canonicalise devname failed" in a 2021 report): not tried; wheezy
  uses SILO, so nothing was learned about it here.
- **Ubuntu 9.04 server sparc** (`ubuntu-9.04-server-sparc.iso` from old-releases.ubuntu.com's ports
  tree, checked against the release's `MD5SUMS` and `SHA1SUMS`; their signing key, `FBB75451`, is no
  longer in Debian's `ubuntu-keyring`, so the signatures weren't checked): the same SILO and
  debian-installer, "Choose language" 31 s after Return at SILO. Its installer kernel (2.6.28-6)
  spins at 100% with 0110 too: its idle loop isn't the 3.2 layout, and the kernel is stripped, so it
  wasn't looked at. Not installed, no target.

**The firmware's RAM clear after a reboot (`wsh/0112`-`0113`).** `reboot` goes through OpenBIOS 0030
(above): the reset works, but the banner came late. 336 s after the kernel's `Restarting system`
for a reboot after a minute at the shell (512 MB), about 5 minutes for the installer's reboot after
85 minutes (1024 MB). `info registers` at intervals: the PC in 0030's clear loop (`stxa %g0, [..]
ASI_PHYS_USE_EC`), most of the RAM cleared in a minute or two, then 30 bytes to a few KB a second
around 77-80 MB (pages the kernel had used). `perf` on QEMU: 86% in `tb_page_remove()`, 7% in
`tb_invalidate_phys_page_range__locked()`. `info jit` before the reboot: 614 000 translated blocks
after a minute at the shell, 1 600 000 after ten minutes, the 1 GB code buffer flushed twice. A
store to a page with translated code invalidates the blocks it overlaps, and taking one off its
page's list walks that list, so a page that holds many costs in proportion to their number squared.
NetBSD, OpenBSD and Solaris didn't show it (their reboots took 8-70 s), presumably fewer blocks
per page. `wsh/0112` queues a TB flush in `main_cpu_reset()` on every reset after the power-on one
(the firmware is about to overwrite the RAM anyway): the same reboot reaches the banner 2 s after
`Restarting system` and `login:` 172 s after it. qtest `wsh/0113` (`sun4u-sabre-reset-test`,
`/sun4u/reset/tb-flush`: one more TB flush in `info jit` after `system_reset`; fails without
0112).

**Translated code under Linux 3.2 (not followed).** The same numbers say that QEMU retranslates
Linux 3.2's code all the time: `info jit` after the first install showed 1 200 000 blocks in the
buffer but only 4 093 of the 524 288 hash buckets used (0.19% occupancy), 3 990 000 invalidations
and 23 buffer flushes; a boot to `login:` alone fills the 1 GB buffer once or twice. Writes to pages
that hold code drop their blocks, and the code is translated again. That likely makes the install
and the boots slow (the base system took 36 minutes); where the writes come from (the kernel's own
pages, D-cache aliasing work on spitfire, page reuse) wasn't traced. Whether it also explains the
soft lockups in `dpkg-deb` that a 2023 debian-sparc report shows on QEMU sun4u (Debian 12's 64-bit
userland) is open.

**Idle (`wsh/0110`-`0111`).** Linux 3.2 spins in `cpu_idle()` with interrupts enabled, a loop the
Linux layouts of 0070 don't match (that one is the generic `do_idle()` of later kernels, at `%pil`
14; table above). 0110 recognises 3.2's call of `touch_nmi_watchdog()` by the `tlb_type` test, the
`be,pn` to the sun4v branch with `mov 14, %o0` (`TIF_POLLING_NRFLAG`) in its delay slot and the sun4v
branch's `clear_bit()` call, and halts there at `%pil` 0 when `TIF_NEED_RESCHED` is clear (the Linux
helper now takes the `%pil` the loop runs at: 14 for 0070's kernels, 0 for 3.2). `-trace
sparc64_idle_match` shows `Linux 3.2 idle loop: call at 0x42ab58`. The kernel is tickless when idle
(`CONFIG_NO_HZ=y`, `HZ=250`), so a halted CPU stays halted until a timer or a device needs it.
qtest `wsh/0111` (`sun4u-idle-test`, `linux-3.2`: idle, off, work, noint, pil14, pil15, tick; the
idle case fails without 0110; 58 cases in all pass).

Measured with `scenarios/sparc64-idle.py` (`GUEST=debian PASSWORD=wshlab MEM=512 LOAD=120`) on copies
of the first-booted disk, one QEMU at a time on the lab host (14 threads, 1-minute load 3.5-4.7 from
other agents' work at every start and end): "before" the published pve-qemu-kvm 11.1.3-4+wsh3 (no
0070, which wouldn't match 3.2 anyway), "with" a `qemu-system-sparc64` built from the 11.1.3-4 series
with `wsh/0001`-`0072` and 0110-0112, "off" that one with `-M sun4u,idle-halt=off`. Host CPU over 60 s
at the shell after 30 s, the guest clock over that minute, the awk job, ten `sleep 1` and the rounds of
two minutes of the job plus a 64 MB write/read (host seconds):

| Run | Host CPU | Clock drift | Job s | 10 x `sleep 1` s | Load rounds | Boot to `login:` s |
| --- | --- | --- | --- | --- | --- | --- |
| before | 100.0% | 0.0 s | 12.8 | 10.5 | 9 | 168 |
| with (`TRACE=sparc64_idle_match,sparc64_idle`: 1092 halts in the run) | 0.1% | 0.0 s | 13.4 | 10.4 | 9 | 236 (an 80 s stall, below) |
| off | 100.0% | 0.0 s | 12.9 | 10.5 | 9 | 141 |

A quick check at the shell before that: 100.0% with the package, 0.1% with the build (`cpu_use`, 60 s).

**A boot stall seen twice with the halt (not explained).** Two boots with the halt sat silent for
80-95 s right after the kernel's one-off `hrtimer: interrupt took 50-67 ms` (Linux's hrtimer hang
detection), before init started udevd: the "with" run above and a boot after a firmware reset with
the build (`udevd` at 157 s, `sched: RT throttling activated` before it). 21 more boots with the halt
(tick, idle and interrupt vector traces on in 16 of them) didn't stall, nor did 10 boots without it
(the package, or `idle-halt=off`); the hrtimer message came once more with the halt, without a stall,
and never without it. Linux 3.2's
hrtimer code had a bug of this shape (after a detected hang a timer cancel could program the clock
event to a far timer and block all timers until it fired; "hrtimer: Prevent all reprogramming if
hang detected", upstream 2013); whether Debian's 3.2.78 has the fix, and why the halt would make the
hang detection more likely, wasn't checked.

### FreeBSD 12.4 on sun4u (OpenBIOS 0032-0033, pve-qemu `wsh/0114`-`0115`, 2026-11-22)

FreeBSD 12.4-RELEASE is the last release with sparc64 (removed in 13.0; the 12 branch is end of life).
Its `bootonly` and `disc1` CDs (from ftp-archive.freebsd.org, checked against the release's
`CHECKSUM.SHA256` and `CHECKSUM.SHA512`) boot on `-M sun4u` with OpenBIOS: the boot block on slice `f`,
`/boot/loader`, the GENERIC kernel (`FreeBSD 12.4-RELEASE r372781 GENERIC`, gcc 4.2.1), bsdinstall's
console-type question on ttya at 59 s. The kernel sees the hardware as `pcib0: <U2P UPA-PCI bridge>`
(Sabre, IGN 0x1f), `uart0` (the console, `ttyu0`), `atapci0: <SiI (CMD) 646U2 UDMA33 controller>`
with `ada0` and `cd0` (UDMA2), `hme0`, `eeprom0` (mk48t59 clock), timecounter and event timer `tick`
at 100 MHz, `hz` 1000; `ebus0: <power>` and the 8042 stay without a driver. The install, the installed
disk, DHCP on `hme0`, the reboot and the power-off work with the patches below; the install target is
`freebsd124-sun4u` (e2e/sparc/README.md, "The FreeBSD 12.4 install target"), which passed `--check
--export` through PVE in 14.9 min with the lab's QEMU and firmware mounted over the package's.

**No interrupt storm.** FreeBSD bug 239068 (2019) reports an endless `interrupt storm detected on
"vec2016:"` after the disks are found, on QEMU 2.12 and 3.0 (2.9 was fine). 2016 = 0x7e0 = IGN 0x1f, INO
0x20: the cmd646's OBIO interrupt. With pve-qemu-kvm 11.1.3-4+wsh3 and the lab's build of the series
it doesn't happen: neither CD boot, the install (8 minutes of extraction from `cd0` to `ada0`) nor about
20 boots of the installed disk printed a storm or an ata timeout, and `vmstat -i` shows `vec2016:
atapci0` at 18-19 interrupts a second averaged over the boot (`DISK_TROUBLE` in `_freebsd.py` fails
any run that prints either). Not followed further: which change since 2.12 fixed it (the bug is about
upstream QEMU; `wsh/0021`'s latch keeps the line on INTRQ, and `wsh/0045` keeps the sabre's
requests in order), and plain upstream QEMU 11.1.3 wasn't tried.

**Power-off: the firmware spun (OpenBIOS 0032).** `shutdown -p now` printed `Uptime:` and the
machine stayed on, QEMU at 100% of a host core. FreeBSD powers off through `ofw_exit()` with the
`SUNW,power-off` client call, the firmware's trap table back and its own timer interrupt (`%tick`
compare, 1000 Hz) pending. The PC stayed at one instruction in OpenBIOS's `reload_DMMU_tlb`, and `-d
int` showed interrupt 0x4e (level 14) taken there over and over: the MMU miss handlers enable
interrupts around their C handler at TL 1, where the TL>0 table's level-14 entry only retries without
clearing the interrupt. 0030 met the same spin after a reboot ("The firmware reboot on sun4u") and
kept the firmware's own timer from firing; FreeBSD's timer is the kernel's. 0032 leaves interrupts
disabled in both miss handlers (spill and fill traps aren't interrupts). `shutdown -p now` and the
installer's `halt -p` then end QEMU with exit 0 in 15-22 s.

**Reboot: the kernel panicked (OpenBIOS 0033).** Every `shutdown -r now` (and `ofwdump`) ended in
`panic: trap: fast instruction access mmu miss (kernel)`, and the panic's own reboot made QEMU stop
with `Trap 0x00a4 while trap level (5) >= MAXTL (5), Error state` (with the package's firmware too).
FreeBSD runs its kernel at TL 1 with the user process's context in the primary context register, and
calls the client interface from there on its own trap table (`ofw_entry()`; only `ofw_exit()` sets
the primary context to 0). OpenBIOS's `SAVE_CPU_TRAP_STATE` and `RESTORE_CPU_TRAP_STATE` walked `%tl`
from 3 down to 0, and at TL 0 the next instructions are fetched in the primary context: the
firmware's locked ITLB entry (`ffd00000`, 512 KB, context 0, not global; `info tlb`) missed, FreeBSD's
handler had no mapping for it (its kernel never takes an instruction miss on itself), and panicked.
Before user processes ran the primary context was 0, so the boot's own client calls worked. 0033
walks TL 4 down to 1 (there is no trap state at TL 0; `rdpr %tpc` there is an illegal instruction on
the UltraSPARC). The reboot then reaches `login:` again in 94 s and `ofwdump -p /chosen` works.
0032 is still needed with 0033: with a build that has 0033 and not 0032 the installed disk boots,
and `shutdown -p now` stays on after `Uptime:` as before (no QEMU exit within 300 s).

**Other sun4u guests with 0032-0033 and 0114-0115** (the lab's own QEMU, both mounted over pve-qemu-kvm
11.1.3-4+wsh3's, 2026-11-22): the `sparc64` matrix passed 10/10 (the NetBSD 11.1, 9.3, OpenBSD 8.0
and Debian 12 CDs, NetBSD on the VGA console, the NetBSD install, its disk with DHCP and an HTTP fetch
over `sunhme` and over virtio, idle 2.3% with the halt and 100.6% without); `sparc64-reboot.py` on
copies of the stored disks: NetBSD 11.1 two reboots (each back at `login:` in 84 s), OpenBSD 8.0 one
(194 s), Solaris 10 one (400 s), all powered off; Solaris 9 booted to `console login:` and powered off
(`sparc64-boot-disk.py`); FreeBSD two reboots (129-131 s each) and the power-off. qtest
`sun4u-idle-test` 63/63 (70/70 on the series with `wsh/0110`-`0113`, below).

**On the series with Debian 7's patches** (pve-qemu `wsh/0001`-`0115` and `0120`-`0121`, built from
the pinned QEMU with the whole series; OpenBIOS 0001-0033 with 0031; 2026-11-22, load average 1.8-3.5):
`sun4u-idle-test` 70/70 and `sun4u-sabre-reset-test` 2/2; FreeBSD (the stored disk from the PVE
install) idle 8.3% (103.0% with `idle-halt=off`), Debian 7 idle 0.1% (`wsh/0110` unchanged);
`sparc64-reboot.py`: FreeBSD two reboots (back at `login:` in 94 s each), Debian 7 one (149 s, with
`wsh/0112`'s TB flush), NetBSD 11.1 one (81 s); every power-off ended QEMU with exit 0.

**Idle (pve-qemu `wsh/0114`).** An idle FreeBSD kept a host core at 100%: ULE's idle thread
`sched_idletd()` calls `cpu_idle()`, which is empty on sparc64 (`retl; nop`). 0114 recognises the call
(table in "Idle" above) and halts there, with two differences from the other kernels: FreeBSD's idle
loop runs at TL 1, and between two calls it looks for work to steal and may spin itself
(`sched_idlespins`), longer than the 20 us the 100 us poll allows between rounds, so the poll never
ended and the first build (TL 1 allowed, poll kept) still read 103.5%. FreeBSD is halted at its
first idle call; once woken, the call and one round of its loop run before the next halt. The
kernel ticks 1000 times a second (`hz` 1000, `pil14: tick` ~1070/s in `vmstat -i`), so it wakes that
often.

`scenarios/sparc64-idle.py` on copies of the first-booted disk (`GUEST=freebsd PASSWORD=wshlab
LOAD=120`, one QEMU at a time, load average 2.4-6.1 on 14 threads): "before" pve-qemu-kvm 11.1.3-4+wsh3's
`qemu-system-sparc64`, "with" the series built with 0114-0115, "off" that build with
`-M sun4u,idle-halt=off`; OpenBIOS 0032-0033 in all three:

| | Host CPU idle | Clock drift over 60 s | 10 x `sleep 1` | awk job | Load rounds (120 s) | `login:` |
| --- | --- | --- | --- | --- | --- | --- |
| before | 107.0% | 0.0 s | 10.3 s | 21.4 s | 6 | 119 s |
| with | 8.7% | 0.0 s | 10.4 s | 16.7 s | 7 | 116 s |
| off | 105.0% (104.2% in an earlier run) | 0.0 s | 10.4 s | 16.9 s | 7 | 121 s |

The rest (8.7%) is the 1000 wakes a second and FreeBSD's own work after each; the CPU-bound job takes
as long with the halt as without (the "before" job ran at a higher host load).

### Snapshots and migration on sun4u (pve-qemu `wsh/0133`-`0134`, 2026-11-24)

A sun4u guest came back from every saved state without interrupts: after `loadvm`, `-loadvm` in a new
QEMU, an incoming migration or (through PVE) `qm rollback` of a snapshot with RAM and `qm start` after
`qm suspend --todisk`, the CPU ran (the guest's idle loop, its timers) but the serial console never
answered again. The sabre host bridge had no migration state of its own (its section was the generic
PCI host bridge's, which holds none of its registers), so its interrupt mapping registers came back
disabled and the request it waited to have cleared was forgotten; the sun4u IOMMU came back off; the
ebus's and the sabre's own PCI configuration space were lost (the ebus's BAR0 unmapped); and the CPU
section leaves out SOFTINT and the interrupt vector. The browser build met the same with its sun4u
snapshot and carried a patch of its own for the sabre and the CPU (guide "Browser SPARC").

pve-qemu `wsh/0133` migrates all of them: the sabre's interrupt mapping registers, the lines that are
up, the outstanding request, the PCI control registers and the reset status (section `sabre`); the
IOMMU's registers (`sun4u-iommu`); the ebus's and the sabre function's PCI configuration space; the
CPU's SOFTINT, `ivec_status`/`ivec_data` and `wsh/0042`'s `idle_halted` in subsection
`cpu/sparc64_irq`, sent only when one is set (in the runs below only FreeBSD's streams had it). sun4u
has no versioned machine types; the streams aren't compatible either way: an older package's state no
longer loads (`Unknown section or instance 'PCIHost'`; it resumed without interrupts anyway) and a
newer one doesn't load into an older QEMU (`Unknown section or instance 'sun4u-iommu'`), so a live
migration to an older QEMU fails and the source keeps running. The browser build now takes the fix
from the series (`web/patches/` keeps only the SS-5 timer patch). qtest `wsh/0134`
(`sun4u-migration-test`): `sabre`, `iommu`, `pci-config`, each failing without 0133.

Lab, `qemu-system-sparc64` built from the pinned pve-qemu tree with the series up to 0132 ("before",
the published 11.1.3-4+wsh17's sources) and with 0133-0134 ("after"), one script
(savevm, `loadvm`, a migration to a file loaded with `-incoming` by a new QEMU, then `-loadvm` in a
new QEMU), the guest checked after each restore: the console answers, `sleep 2` takes 2-3 s, a raw
read of a disk region the guest never writes gives the stored disk's md5 (DMA through the IOMMU), and
a ping to the user network's gateway (10.0.2.2) gets every reply:

| Guest | Before | After |
| --- | --- | --- |
| wisp's shell (Linux 7.3.4, `-kernel`) | console silent after all three restores | 3 of 3: uptime advancing, `crc 64` right |
| Debian 7.11 (Linux 3.2, IDE disk, `sunhme`) | console silent after all three | 3 of 3: the same md5 of a tar of `/bin`, `/sbin` and `/lib/modules` (caches dropped) as at boot, ping 0% loss |
| FreeBSD 12.4 (IDE disk, `hme0`) | console silent after all three | 3 of 3: 16 MB read raw from `ada0` with the stored disk's md5, ping 0% loss |

`info pci` and the memory map are the same on both sides of a migration (before: the ebus's BAR0 not
mapped on the destination).

Through PVE (the e2e container built from the published packages with the test build of
pve-qemu-kvm over them, the Debian 7 disk as a qcow2 volume, `serial0: socket`, `net0: sunhme` on
`vmbr0`): `qm snapshot --vmstate 1`, `qm rollback --start 1`, then `qm suspend --todisk 1` and
`qm start` ("Resumed VM, removing state"); after each the console answers, `sleep 2` takes 2 s and
the raw read of `sda` matches the stored disk. With the published 11.1.3-4+wsh17 in the same
container the commands succeed as well, but the console is silent after the rollback and after the
resume. `qm suspend` right after `qm rollback --start` waited for the config lock and timed out once
(`can't lock file`); 20 s later it went through.

The sparc64 qtests (`meson test --suite qtest-sparc64`, 24): with 0133-0134 21 pass, 2 skipped and
`qmp-test` fails in its `oob` case (`capabilities && !qlist_empty(capabilities)`), which fails the
same way on the tree without them; there `sun4u-migration-test` fails as well.
### The lost IDE interrupt at Debian 13's power-off (pve-qemu `wsh/0135`-`0138`, 2026-11-24)
**Seen:** one of 9 Debian 13 boots on a busy host (load 32-43 on 14 cores, "Debian 13 on sun4u" above) lost
the disk during `poweroff`: `ata1.00: failed command: READ DMA`, `status: { DRDY }` (the command done, no
interrupt seen) every 30 s, then the same for PIO, until ext4 aborted its journal. Not the cmd646, the idle
halt or the sabre's earlier bug: the IDE interrupt never reached the CPU because the sabre was still waiting
for the guest to clear an interrupt of the NIC that Linux no longer handled.
**Reproduction** (lab, the published pve-qemu-kvm 11.1.3-4+wsh17 in the lab image, copies of the stored
`install-debian13-sun4u.raw`, 1024 MB, `sunhme` on pciB with `-netdev user,restrict=on`). An investigation
scenario (not in the repo) logs in and then, for 300-600 s, reads the IDE disk with `dd iflag=direct` at
random offsets, pings the user network's gateway (`ping -f` bursts or `-i 0.05`) and takes `enp2s0` down and
up every 3 s; afterwards it checks the kernel log for libata timeouts and powers off. Results with the
published QEMU:
| Host | Runs | Failed |
| idle (load 0-15, other agents' jobs) | 7 | 2: both a panic in `happy_meal_interrupt` when the interface came up |
| 8 CPU-bound loops beside 4 guests (load 17-34) | 4 | 3: the same panic |
| 6 loops beside 6 guests, 3 of them on the fix (load 13-21) | 3 | 2: one panic, one lost IDE interrupt after the last `down` (`WRITE DMA` timed out with `DRDY` every 30 s, as at the power-off) |
Without the interface going down and up (`dd` and `ping -f` only) 1 run of 1 passed; the down/up loop makes
the window come up some 100-200 times a run instead of once at power-off.
**Mechanism** (QEMU trace `sabre_*`, `sparc64_cpu_ivec_raise_irq`, `sunhme_update_irq`, `sunhme_seb_write`
with `-msg timestamp=on`). Linux 7.0's `happy_meal_close()` resets the sunhme (a write of `ETX|ERX` = 3 to
the global reset register), releases the ring and frees its interrupt; it leaves the interrupt map register
of the NIC's slot valid. QEMU's sunhme only acknowledged the reset: the receiver stayed on, so the next frame
went into the old ring and set `RXTOHOST` with the interrupt unmasked. One idle-host run:
```
19:02:52.102114 sunhme_seb_write addr 0x0 value 0x3          interface down: global reset
19:02:52.155378 sunhme_update_irq ... seb: 0x10000  level: 1   a frame 53 ms later: RXTOHOST
19:02:52.155406 sabre_set_request request irq 16               ino 0x10, the CPU takes the vector
19:02:52.215127 sabre_pci_set_irq set irq_in 32 level 1        the cmd646's line: no request
19:02:53.678587 sabre_config_write addr 0xc24 val 0x800007d0   interface up: map register written,
19:02:53.678590 sabre_set_request request irq 16               the request of 0x10 sent again,
19:02:53.678607 sabre_clear_request clear request irq 16       cleared by the new open,
19:02:53.678609 sabre_set_request request irq 16               and made again (the line is still up):
                                                               happy_meal_interrupt runs before the
                                                               rings are set up, NULL dereference
```
Linux took the vector, found no handler for it and doesn't clear an interrupt it didn't handle
(`handle_fasteoi_irq()`, `IRQCHIP_EOI_IF_HANDLED`). The sabre keeps one request to the CPU at a time
(`wsh/0045`) and makes the next only when the guest clears the current one, so the IDE controller's
interrupt (ino 0x20) waited behind the NIC's: 1.46 s here, until the interface came up and its open wrote
the clear. In the run that lost the disk the frame came 6 s after the last `down`, the interface stayed down
(as at power-off), and from then on every IDE interrupt waited, 2.5 minutes until the run was stopped. On
real hardware each ino has its own state in the sabre, so a NIC interrupt left uncleared blocks only the
NIC; and the reset stops the receiver.
**Ruled out on the way:**
- **The cmd646** (`hw/ide/cmd646.c`, our latch `wsh/0021`): in every trace the controller raised its line at
  the end of the command; the sabre made no request for it.
- **The idle halt** (`wsh/0042`-`0044`, `0070`-`0072`, `0110`, `0114`): an interrupt vector sets
  `CPU_INTERRUPT_HARD` and wakes a halted CPU whatever `%pil`; here the vector was never sent. Reading the
  Linux helper for this turned up a different, unreproduced race: `helper_sparc64_idle_linux()` checks
  `%softint` without the BQL and then sets `cs->halted`; a tick that fires between the two (`tick_irq()` sets
  `TICK_INT` and `halted = 0`) is masked at `%pil` 14, sets no `CPU_INTERRUPT_HARD`, and the CPU sleeps until
  the next interrupt vector. Not seen in any run; fixed since by `wsh/0139` ("Idle", above).
- **The `%softint` race** (`wsh/0036`) and **the sabre's replaced request** (`wsh/0045`): both fixed in the
  published package and in the trace the request was not replaced but never cleared.
- **The PCI interrupt-map register:** reading `sabre_config_write()` showed that disabling a slot dropped the
  outstanding request only when its ino equalled the slot number. Linux 7.0 never disabled the NIC's slot in
  any trace (the map register is written only with the valid bit, at each open), so not this; fixed anyway in
  `wsh/0137` with a qtest (`wsh/0138`), as the drop is what keeps a guest that does disable an interrupt from
  hanging the sabre the same way.
**Fix** (`wsh/0135`): an ERX reset clears the receiver's DMA enable (bit 0 of the ERX configuration register;
Linux writes `0x70011` there when it sets the ring up) and the model takes no frame while it is clear; each
reset drops the status bits of its engine (`HOSTTOTX`, `TXALL` for ETX, `RXTOHOST`, `NORXD` for ERX) and
updates the line. `wsh/0136` is the qtest (`sun4u-sunhme-reset-test`, 3 cases, the two reset cases fail
without 0135). The sabre's one-request-at-a-time model stays: any device that interrupts after its driver is
gone can still hold back the others. Modelling the sabre's per-ino state as the hardware has it (and the
CPU's NACK and the sabre's retry for a vector sent while the CPU is busy) would remove that, at the cost of a
change in the sabre, the CPU's interrupt receive register and the migration stream; not attempted.
**Results with the fix** (the same scenario, `qemu-system-sparc64` built from the series with 0135-0138,
firmware from the published package; two more variants with frames sent to the guest from the host side
every 2 ms through a `hostfwd` UDP port, so that one arrives after nearly every reset):
| Variant | Host | Published 11.1.3-4+wsh17 | With 0135 |
| --- | --- | --- | --- |
| down/up every 3 s, `ping` | idle | 7 runs, 2 failed | not run |
| down/up every 3 s, `ping -f`, 600 s | 8 loops (load 16-34) | 4 runs, 3 failed | 4 runs, 0 failed |
| the same, both binaries in one batch | 6 loops (load 13-21) | 3 runs, 2 failed | 3 runs, 0 failed (0135 alone) |
| down/up every 3 s, host-side frames, then down and 25 MB read | idle | 2 runs, 2 failed (panic at the first close or open) | 2 runs, 0 failed |
| down once, host-side frames, 25 MB read (the power-off case) | idle | 2 runs, 2 failed (one lost IDE interrupt, `READ DMA` with `DRDY`; one panic in the close) | 2 runs, 0 failed |
18 runs on the published package, 11 failed (9 panics, 2 lost IDE interrupts); 11 with the fix, none. In the 7
fixed runs traced with the sunhme events no NIC request was left uncleared after a reset. Debian 13's network still works
(ping through each `up`, Linux sets ERX DMA again), and the stored disks of NetBSD 11.1, OpenBSD 8.0, FreeBSD
12.4, Debian 7 and Solaris 10 boot on the fixed binary and ping the user network's gateway through `hme0`
(`eth0`) before and after taking the interface down and up. NetBSD loses the first 3 of 5 pings after the
`up` with the published binary as with the fix. qtests: `sun4u-sunhme-reset-test` 3/3, `sun4u-sabre-irq-test`
5/5, `sun4u-cmd646-test` 3/3; `meson test --suite qtest-sparc64` on a loaded host: everything else as
before (the known `qmp-test` `oob` failure), `sun4u-idle-test` 70/70 but over meson's 60 s timeout at that
load (67 s alone), unrelated to these patches. Not run through PVE, and the original 9-boot power-off test
was not repeated.

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

## TCI (QEMU's TCG interpreter)

QEMU's TCG interpreter (`configure --enable-tcg-interpreter`) runs translated guest code as bytecode
in a C loop instead of emitting host machine code. It is the only TCG backend on hosts without a
native one, and the one QEMU's Emscripten (WebAssembly) build uses in 11.1.3, so these numbers are
step 1 of the "Browser SPARC" item in `ROADMAP.md`: how much slower the sparc guests get when the
native x86-64 backend is replaced by the interpreter.

**Setup (2026-11-21).** Two `qemu-system-sparc`/`qemu-system-sparc64` builds from the same tree:
QEMU 11.1.3 with pve-qemu 11.1.3-3's patch series and `submodules/pve-qemu.patch` (the wsh patches)
as of wsh-pve `d35fabb`, built on Debian 13 (gcc 14.2) with

```sh
configure --target-list=sparc-softmmu,sparc64-softmmu --disable-docs --disable-werror --disable-gtk \
  --disable-sdl --disable-vnc --disable-opengl --disable-capstone --enable-png --enable-slirp \
  [--enable-tcg-interpreter]
```

(meson then reports "TCG backend: TCI (TCG with bytecode interpreter, slow)"). Both were mounted over
`/usr/local/bin/qemu-system-sparc{,64}` in the lab image (`docker run ... -v
<build>/qemu-system-sparc:/usr/local/bin/qemu-system-sparc:ro wsh-sparc-lab ...`; firmware from the
published package). One guest at a time on the 14-vCPU lab host (a VM on an i9-9900K), each case on a
fresh copy of the stored disk, in the order TCG, TCI, TCG, TCI (two runs each):

```sh
# Solaris 2.6 End User, SS-5, OpenBIOS, 256 MB (boot, idle, dd)
lab.py run scenarios/idle.py --out <out> --var DISK=<copy of sol26-enduser-installed.raw> --var ROUNDS=3
# NetBSD 9.3 sparc, SS-5, OpenBIOS, 256 MB
lab.py run scenarios/idle.py --out <out> --var DISK=<copy of install-netbsd93-sparc.raw> \
    --var PROMPT=login: --var PASSWORD=wshlab --var ROUNDS=3 --var "CHECK=pkill makemandb; sleep 2"
# NetBSD 9.3 sparc64, sun4u, OpenBIOS, 512 MB
lab.py run scenarios/sparc64-idle.py --out <out> --var DISK=<copy of install-netbsd93-sparc64.raw> \
    --var GUEST=netbsd --var PASSWORD=wshlab --var TIMEOUT=3600 --var "WAIT=pkill makemandb; sleep 2"
# the bench disk on Solaris 2.6, SS-5, OpenBIOS (the benchdisk-sol26-openbios-ss5 case, no NIC tests)
lab.py run scenarios/bench-disk.py --out <out> --var DISK=<copy of sol26-enduser-installed.raw> \
    --var DISK2=<bench-sol26.raw> --var NET=none --var RUN_TIMEOUT=14400
```

Other agents' guests and builds shared the host during the first round of the boot and idle cases
(1-minute load 7-14) and less during the second (2-3); the bench runs had it nearly to themselves
(0.7-1.6). The first round's CPU-bound numbers are the slower ones in both builds, so the ratios
below are of the means of the two runs.

**Boot and idle** (boot = QEMU start to the shell after login, Solaris's first-boot questions
included; host CPU = QEMU's use of one host core over 60 s at the shell; both runs):

| Guest | Boot TCG | Boot TCI | Ratio | Idle host CPU TCG | TCI | CPU-bound command TCG | TCI | Ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Solaris 2.6, SS-5 | 121, 116 s | 222, 188 s | 1.7x | 4.7, 3.1% | 7.0, 4.0% | `dd`, 200000 blocks: 2.5, 1.9 s | 39.8, 23.5 s | 14x |
| Solaris 2.6, SS-5 (bench runs) | 114, 115 s | 181, 181 s | 1.6x | | | | | |
| NetBSD 9.3, SS-5 | 43, 27 s | 162, 121 s | 4.0x | 102.6, 101.8% | 102.9, 101.9% | `dd`, 200000 blocks: 10.2, 7.2 s | 62.8, 47.4 s | 6.3x |
| NetBSD 9.3, sun4u | 74, 60 s | 386, 455 s | 6.3x | 3.2, 2.6% | 3.3, 3.1% | awk job: 21.5, 14.2 s | 83.0, 67.5 s | 4.2x |

The guest clock kept time in every run (drift 0.0-0.2 s, once 0.9 s with TCI on sun4u: one tick of
`date`); ten `sleep 1` took 10.0-10.4 s with TCG and 10.4-11.7 s with TCI, the echo of a trivial
command 50 ms with TCG (the lab's polling step) and 50-89 ms with TCI.

- **Idle doesn't depend on the backend.** A guest whose idle loop halts the CPU (Solaris through
  `solaris-idle`, NetBSD on sun4u through `idle-halt`: both recognise the loop in the translator, so
  they work the same with TCI) costs 3-7% of a host core either way. NetBSD 9.3 on sun4m has no way
  to halt ("Idle") and spins at 100% with both; with TCI its idle loop just runs fewer times a second.
- **Boot suffers less than compiled code.** Solaris's boot spends much of its time waiting (device
  probes, timeouts, the first-boot form), so it takes 1.6-1.7x as long; NetBSD's boot is mostly guest
  code and takes 4-6x. OpenBIOS from reset to `bootpath:` took 2.5 s with TCG and 25.7 s with TCI.

**The bench disk** (Solaris 2.6, SS-5, OpenBIOS; mean of the 2 runs, which are within 4% of each
other in the CPU-bound rows; TCI/TCG = how many times slower TCI is: the time ratio, or the rate
ratio inverted):

| Benchmark | Unit | TCG | TCI | TCI/TCG |
| --- | --- | --- | --- | --- |
| Dhrystone 2.1 | VAX MIPS | 946 | 48.8 | 19.4x |
| Whetstone | MWIPS | 423 | 41.6 | 10.2x |
| Hanoi, 10 disks | towers/s | 20198 | 1641 | 12.3x |
| `nawk` loop | s | 4.9 | 60.3 | 12.3x |
| nbench integer index | K6/233 = 1 | 4.15 | 0.240 | 17.3x |
| nbench FP index | K6/233 = 1 | 1.70 | 0.217 | 7.8x |
| nbench memory index | K6/233 = 1 | 4.39 | 0.167 | 26.3x |
| lmbench null syscall | us | 0.40 | 4.03 | 10.1x |
| read / write | us | 1.60 / 1.38 | 20.3 / 16.7 | 12.7x / 12.0x |
| stat | us | 4.24 | 76.6 | 18.1x |
| open/close | us | 9.3 | 102.7 | 11.0x |
| signal install / catch | us | 1.07 / 13.4 | 20.1 / 140.3 | 18.8x / 10.4x |
| protection fault | us | 2.96 | 26.4 | 8.9x |
| pipe latency | us | 78 | 244 | 3.1x |
| fork+exit | us | 1372 | 6429 | 4.7x |
| fork+execve | us | 2452 | 10041 | 4.1x |
| fork+/bin/sh -c | us | 13320 | 60447 | 4.5x |
| page fault | us | 198 | 471 | 2.4x |
| mmap 8 MB | us | 1084 | 9252 | 8.5x |
| file reread 8 MB | MB/s | 987 | 39.8 | 24.8x |
| memory read 4 MB | MB/s | 15047 | 427 | 35x |
| bcopy 4 MB | MB/s | 1165 | 38.1 | 30.6x |
| memory latency 8 MB | ns | 7.97 | 33.5 | 4.2x |
| file create / delete (0k) | files/s | 1068 / 2018 | 465 / 910 | 2.3x / 2.2x |
| TCP latency / bandwidth over lo0 | us / MB/s | 216 / 308 | 650 / 22.9 | 3.0x / 13.4x |

Memory write (4 MB) spread too much under TCG (9015 and 16355 MB/s) for a ratio; TCI 484-497 MB/s.
`run.sh` took 380-383 s with TCG and 508-514 s with TCI (its CPU benchmarks scale their counts to 20 s
each, so the run hardly grows). One quirk: `/usr/bin/time` prints minutes from 60 s on, so TCI's
`nawk` loop came out as `BENCH nawk_s 1:00.3 s` in `bench.txt` and `bench-disk.py` didn't take it
into `result.json` (60.3 s in both runs, read by hand).

- **Where TCI hurts most**: tight loops over memory (bcopy, memory read, file reread: 25-35x) and
  integer code (Dhrystone, nbench integer: 17-19x). Floating point less (Whetstone 10x, nbench FP 8x):
  both builds call the same soft-float helpers, and only the code around them is interpreted. Kernel
  paths that mostly wait or run in the device models (fork, exec, pipes, page faults, file creation,
  memory latency) are 2-5x.

**Conclusion.** On a host with a native TCG backend (x86-64, aarch64 and the others QEMU has) TCI is
not worth using for these guests: compiled code runs 8-35x slower (Dhrystone 19x), a boot takes
1.6-6x as long, and idle costs the same. Its only use here is a host without a native backend, which
in practice means QEMU's WebAssembly build. There a Solaris 2.6 SS-5 reaches its login in about
3 minutes of interpreter time before WebAssembly's own overhead, and a guest that halts when idle
doesn't keep the CPU busy: enough for a serial-console demonstration in the browser (ROADMAP,
"Browser SPARC"), not for real work. sun4u is hit harder at boot (NetBSD 9.3: 7 minutes against 1),
so a browser demonstration should start with sparc32, or with a migrated snapshot taken after boot.

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
| LX | `lx.bin` (only; not in any package, see "SPARCstation LX with its own PROM") | none | 128 MB | 1 |
| SS-600MP | `openbios-sparc32` (only) | none (the machine's SuperSPARC) | 1024 MB | 1 |

- Display: `cg3` (default), `tcx`, `none`, `serial0`/`serial1` (ttya/ttyb). No resolution option
  (`-g`): qemu-server passes none, so cg3 runs at QEMU's 1024x768. The LX takes `serial0` (its
  default: QEMU has no cgsix model) or `none` (both give `-nographic`; the profile's `displays`).
- Disk on the built-in ESP at SCSI target 3, CD-ROM at target 6 (`physical_block_size=512`), the
  built-in lance with `net0`'s MAC, at most one NIC.
- SS-600MP (SunOS 4.1.2, "Older Sun releases on sun4m"): needs pve-qemu-kvm 11.1.3-3+wsh13 or later
  (`wsh/0063`-`0065`, openbios 0028); the ESP is under OpenBIOS's `dma` node and the lance under its
  `lebuffer`, the command line is the same as for the other machines. OpenBIOS only and one CPU:
  4.1.2's start of a second CPU wants a module ID in the MMU control register as on the real
  machine's Ross modules, which QEMU doesn't model, and Sun's 600MP PROM loops in its power-on self
  test (it knows the SuperSPARC, but checks diagnostic registers QEMU doesn't keep; "Sun's own
  SS-600MP boot PROM"); both refusals say so (their text names the Ross RT625). 4.1.2 boots
  with up to 2 GB; 1024 MB is offered, the wizard presets 256 (`defaultMemory` in pve-manager). The
  displays are the default list (OpenBIOS draws on cg3 and TCX; the target uses `serial0`), no
  `audio0` (no sound chip), and `nvram0` as on the other OpenBIOS machines (accepted, on the M48T08).
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
  `SS-\d{1,2}`, `SS-600MP`, `LX` and `sun4[a-z]` with an optional `+pveN` (a snapshot's `runningmachine`), type
  `sun`.
- **Profiles:** `assert_sparc32_profile` checks the machine, the firmware for the machine, memory,
  sockets × cores up to the profile's most (1 or 4), `vcpus` equal to it, no CPU hotplug, no `cpu`, the display, no guest agent, serial0/serial1 only, one lance NIC, `audio0` (SS-5 only, `device=cs4231`, no SPICE) and no `efidisk0` or `tpmstate0` (no UEFI firmware, no TPM).
  A profile's `why` gives the reason in the refusal where the generic message would mislead (the
  SS-600MP's firmware, CPUs and sound).
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
- **NVRAM:** `nvram0` (sparc32 only), a volume for the M48T08's NVRAM, so a Sun PROM's settings
  last ("The NVRAM kept in a volume").
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
- **ESP interrupt latency (NeXTSTEP, OPENSTEP):** `machine: SS-5,esp-irq-latency=500` (any sparc32
  machine; microseconds, 0-100000, unset or 0 = off) makes qemu-server emit `-global
  sysbus-esp.irq-latency-us=500` (pve-qemu `wsh/0040`): the ESP's interrupt comes that long after
  each SCSI event. NeXTSTEP 3.3 and OPENSTEP 4.2 need it ("NeXTSTEP 3.3 and OPENSTEP 4.2"); every
  other guest is better off without it, as each disk command gets about 2 ms slower at 500. It is a
  key of the `machine` property string, like `viommu`, so `qm set <vmid> --machine
  SS-5,esp-irq-latency=500` sets it and the type stays explicit. `assert_esp_irq_latency`
  (Machine.pm) refuses it on every other architecture, at create, update and start. Tests: qemu-server's
  `cfg2cmd/sparc32-ss5-esp-irq-latency.conf`, `x86-esp-irq-latency-error.conf`,
  `sparc64-esp-irq-latency-error.conf`. It takes effect at the next start.
- **Boot:** sparc64 devices get no `bootindex`; the boot device is `-boot order=c|d` from the boot
  order (`sparc64_boot_device`), and the default boot order of a new sparc64 VM has the CD-ROM first. CD-ROMs get
  `physical_block_size=512` (Sun drives used 512-byte blocks). Drives are `-blockdev` nodes as on
  x86 (the machine version follows the QEMU version), which the backup job finds.
- **Network:** sparc32 uses the built-in lance (`-net nic,model=lance,macaddr=<net0's MAC>,netdev=net0`
  next to the usual `-netdev type=tap,id=net0,...`, not hot-pluggable; sun4m creates one lance and
  only warns about a second `-net nic`). The lance is peered with the `net0` netdev directly, so
  `set_link net0` reaches it as on x86 (it used to hang off a hub behind a netdev named `lance.0`,
  and every `set_link` failed with `Device 'net0' not found`). QEMU names the NIC itself `lance.0`.
  sparc64 puts `sunhme` on `pciB` with `-device ...,mac=<net0's MAC>`; the guest's system MAC (the
  IDPROM's, which NetBSD and Solaris use for `hme0`) is the first `sunhme`'s with pve-qemu
  `wsh/0034`, so qemu-server needs no sun4u-specific NIC argument ("The sun4u system MAC").
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
  On sun4u, with Debian 7 running, they and `qm suspend --todisk 1` with `qm start` work since
  pve-qemu `wsh/0133`; before it the guest came back without interrupts ("Snapshots and migration
  on sun4u").
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
- sparc32 in the wizard and the Hardware editors: machine SS-5 (default), SS-10, SS-20, SS-600MP
  or LX (no versions), only the firmware the machine runs (picking a machine switches to its first
  firmware where the chosen one doesn't fit), memory preset to the machine's maximum (or its
  `defaultMemory`: 256 MB on the SS-600MP) and capped at it, CPU type disabled, sockets and cores disabled (nothing is submitted) except on SS-10 and
  SS-20 with OpenBIOS, where they go up to 4 CPUs in total with a hint on the cost, displays cg3 (default), tcx,
  serial0, serial1 and none, the lance NIC only, the first disk on SCSI target 3 and the CD-ROM on
  target 6.
- sparc64 in the wizard and the Hardware editors, from `sparc64Profile`: disks and CD-ROMs on IDE
  only (first disk `ide0`, CD-ROM `ide2`), memory preset to 512 MB and capped at 8192, sockets, cores
  and CPU type disabled, displays std (default), serial0 and none, the profile's NIC models (`sunhme`
  the default), Add → Network Device disabled at four NICs.
- `qemu/MachineEdit.js`: on a sparc32 VM, Hardware → Machine has "SCSI IRQ delay (µs)" behind the
  Advanced checkbox, below vIOMMU (empty = off), with a hint that only NeXTSTEP 3.3 and OPENSTEP 4.2
  need it (500 µs); it writes the `esp-irq-latency` key of `machine` and spells out the default
  machine type when it is set. A save with Advanced collapsed keeps the value. Hidden, disabled and not
  submitted on other architectures, Advanced or not.
- The architecture of an existing VM is read-only (no editor, no Add → Architecture).
- `qemu/NvramEdit.js`: Hardware → Add → NVRAM on sparc32 VMs only (`nvram0`, "The NVRAM kept in
  a volume"); not in the create wizard.
- Selectors: firmware (OpenBIOS, SPARCstation 5/20 PROM), display (TCX, CG3), network (Lance, Sun
  Happy Meal).

## Testing

- `e2e/sparc` (#197): installs and boots Solaris 2.5.1 and 2.6 unattended against the shipped
  QEMU and records every step. Its README lists what it found about devices and boot paths.
- qtests: `sun4m-escc-test` (0005), `sun4m-apc-test` (0011), `sun4m-solaris-idle-test` (0016),
  `sun4m-mmu-nofault-test` (0018), `sun4m-pil-delay-slot-test` (0020), `sun4m-fsr-rd-test` (0027),
  `sun4m-cs4231-test` (0033), `sun4m-esp-test` (0039), `sun4m-nvram-test` (0060),
  `sun4m-ledma-test` (0062),
  `sun4u-cmd646-test` (0022), `sun4u-idprom-test` (0035), `sun4u-softint-test` (0037),
  `sun4u-idle-test` (0044) and `am53c974-test` with 0007;
  they
  build in a QEMU tree with the series applied.
- cg3 sizes: the lab's `display` matrix (`scenarios/cg3-display.py`).
- cg3 and TCX: the TCX/cg3 banner and no-driver cases in `display`, the desktop cases in `display-x`
  (`scenarios/fb-display.py`, disks prepared by `solaris-tcx-packages.py`); results under "cg3 and TCX".
- Idle: the lab's `idle` matrix (`scenarios/idle.py`); on sun4u `scenarios/sparc64-idle.py`, the
  `sparc64` matrix's two idle cases and the qtest `sun4u-idle-test` (0044).
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
- Linux on sun4m: the install targets `redhat62-ss5` and `redhat62-ss20` (`lab.py install`, also in
  `pve_matrix.py install`); results under "Red Hat Linux 6.2 on sun4m".
- Packages after a Solaris install: `lab.py install ... --data-disk N --post-install sun26gnu
  [--local-env]` (the data disk on `/usr/local`, SVR4 packages with `pkgadd -n` from a CD in `scsi5`
  for one boot, PATH and the user's bash); needs the owner's local package CD, so it is in no matrix
  and no CI run; results in `e2e/sparc/README.md`, "Solaris post-install".
- Debian 4.0 on sun4m: `debian40-ss5` and `debian40-ss20` (`lab.py install`; need pve-qemu-kvm
  11.1.3-2+wsh20 or later for `wsh/0038`; out of `pve_matrix.py install`, which gives the guest no
  `--gateway`/`--dns` to reach `archive.debian.org`); results under "Debian GNU/Linux 4.0 on sun4m".
- OpenBSD 5.9 on sun4m: `openbsd59-ss5` and `openbsd59-ss20` (`lab.py install`, also in
  `pve_matrix.py install`, which makes the sets CD from `--iso`'s `other-os/openbsd5.9/`); results
  under "OpenBSD 5.9 on sun4m".

## Known gaps

- **Sound:** SS-5 only, playback only, and not in the web console ("Audio").
- **CD as a disk in the web UI:** `cd_as_disk=1` (see "Supported profiles") has no field in the CD/DVD
  editor; the editor keeps it when the medium is changed or ejected.
- **Resolution:** qemu-server has no option for `-g`; cg3 runs at 1024x768 (what the Sun PROMs and
  Solaris' X server need).
- **Live migration:** fails for a VM without `-cpu` (see "Backup and restore").
- **OpenBSD/sparc with a display:** with `vga: cg3` or `tcx` QEMU adds the keyboard ESCC, and
  OpenBSD 5.9 panics in autoconf ("crazy interrupts"); `vga: serial0` works ("OpenBSD 5.9 on sun4m").
- **SS-20 PROM with a framebuffer:** Solaris 2.6 panics at boot with the console on cg3 or TCX
  under `ss20_v2.25_rom` ("cg3 and TCX"); with a serial console it boots.
- **TCX depth:** qemu-server passes no `-g`, so TCX is 8-bit; 24-bit only works with OpenBIOS.
- **Break on a serial console:** PVE's serial console can't send one (QMP `chardev-send-break`
  can; since `wsh/0141` the guest enters its PROM or debugger, "Stop-A"). Stop-A on the keyboard
  works with a framebuffer console.
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
