# Our patches in LEMU

Where each patch this repository carries sits in [LEMU](https://github.com/tenox7/lemu), Antoni
Sawicki's QEMU fork for vintage machines. Our own patches are offered to LEMU from the fork
[hwinther/lemu](https://github.com/hwinther/lemu), in these branches:

- `feat/sparc-fixes`: the pve-qemu patches `wsh/0001`-`0039` (`debian/patches/wsh/`), sent as
  [tenox7/lemu#1](https://github.com/tenox7/lemu/pull/1): merged, rebased, so its 27 commits have
  new hashes on LEMU's `master` (at `af26c72531`); the table gives those. Two of the 27 exist only
  in LEMU: `d36502293e`, a functional test that boots NetBSD on sun4m and sun4u, and `1ae9cc57ca`,
  notes on the Solaris idle options and a sun4u folder in LEMU's `machines/`. The 25 wsh patches of
  ours in it keep `Forwarded: https://github.com/tenox7/lemu/pull/1` and also have
  `Applied-Upstream:` with their commit on LEMU's `master` (DEP-3 fields; "upstream" here is LEMU,
  not QEMU). `wsh/0030` has neither: it waits for `feat/openbios-fixes`.
- `fix/cs4231-pi-pmi`: `wsh/0122`-`0123` (the CS4231's PI and PMI at the codec's time), now
  `00e72649b8` and `0a78fc843f`, rebased onto `master` and sent as the draft
  [tenox7/lemu#5](https://github.com/tenox7/lemu/pull/5). Written in LEMU first and carried here
  with `Origin:` lines; LEMU took 0123's `migrate` wait into its test commit, so both are equal.
- `wsh/0124`-`0125` (the codec's INT status bit and I24's PI with the APC's playback interrupts,
  for Linux's `snd-sun-cs4231`): ours, written here on LEMU's CS4231 (0028, 0122) to the LEMU
  maintainer's requirements. LEMU took both unchanged onto a local branch `fix/cs4231-codec-int`
  (on top of `fix/cs4231-pi-pmi`, not pushed): `9fbdd5b68a` and `0e81145602`, so they are equal.
  They are on `feat/sparc-fixes-2` as well.
- `wsh/0126`-`0129`: ours, on LEMU's CS4231, after the LEMU maintainer's review of 0124: a write
  to the status register also clears PI, CI and TI in I24 (0126, qtest 0127), and a stop in the
  middle of a buffer drops what the APC took past the codec's position instead of playing it out
  (0128, qtest 0129). Taken unchanged onto `feat/sparc-fixes-2`.
- `feat/sparc-fixes-2`: a local branch in the LEMU clone, not pushed yet, on top of
  `fix/cs4231-pi-pmi`, at `329bc9e639`. It has `wsh/0040`-`0138` except `wsh/0051`-`0052` (x86
  VGA) and `wsh/0130`-`0132` (D-Bus display): 51 commits, equal but for the small deviation in the
  row of `wsh/0062`. `wsh/0059`-`0060` (sun4m NVRAM) are its last two commits,
  ported by LEMU onto its own `m48t59` storage (`wsh/0073` here, LEMU's `ae4bb79885` and
  `4b98747213` on `master`); wsh-pve then took that form. Its hashes change when it is rebased or
  pushed.
- `feat/openbios-fixes`: the OpenBIOS patches 0001-0018 and the one QEMU patch that goes with them
  (`wsh/0030` with OpenBIOS 0018), at `86c3a500ec`, still on LEMU's old `master` (`a71589ebda`).
  Not sent yet; its hashes change when it is rebased. OpenBIOS 0019-0039 are not on it. Patches of
  LEMU origin are paired with their commit on LEMU's `master`.

Last compared on 2026-11-25, by the wsh-pve side: this repository's `main` at `9051509`, LEMU's
`master` at `af26c72531` and the branches above. Every patch here has a row now. The pve-qemu
series uses `wsh/0001`-`0073`, `0110`-`0115` and `0120`-`0150`; the numbers in between are not
used (`wsh/0073` comes before `wsh/0059` in `debian/patches/series`). The code is the same for
`wsh/0001`-`0050`, `0053`-`0072`, `0110`-`0129` and `0133`-`0138` (from `wsh/0040` on only on the
local `feat/sparc-fixes-2`; `wsh/0030` waits for `feat/openbios-fixes`), and for OpenBIOS 0001-0018;
the differences in `wsh/0033`, `0038` and `0062` are the deliberate ones in their rows.
`wsh/0073` is LEMU's own code. Not in LEMU: `wsh/0051`-`0052`, `0139`-`0150` and OpenBIOS 0019-0040 (`0139`-`0150` and OpenBIOS 0040
added after that comparison, not checked against LEMU yet). So the framebuffer console's hang on a BEL (`fb8-blink-screen`), fixed here
by OpenBIOS 0026, is still open in LEMU. `wsh/0130`-`0132` are for PVE only.

Whether a patch that LEMU doesn't have would apply: the pve-qemu patches were applied in order with
`patch` to LEMU's `master` (`wsh/0030` first, then `0040`-`0138`); "applies" means without fuzz,
line offsets allowed. The OpenBIOS patches were not applied: LEMU's `machines/openbios` set starts
from the same OpenBIOS commit as ours (`e5ac46dd`), and 0019-0039 touch none of the files of 0002,
the one patch LEMU keeps elsewhere, so they go on top of its 0001-0018 as they go on ours.

**Columns:**
- **class**: as in [README.md](README.md): *ours*, *LEMU origin* or *built on LEMU*.
- **branch**: "(LEMU local)" is a branch in the LEMU clone that isn't pushed; its hashes have no
  link.
- **status**: compares the added and removed lines, ignoring context and whitespace:
  - *equal*: the same change;
  - *accepted deviation*: differs only as described;
  - *pair only*: a LEMU commit we carry, so there is nothing to compare;
  - *not forwarded*: kept here only;
  - *not in LEMU*: on no LEMU branch; then whether it would apply to LEMU: *applies*, or *needs a
    port* and why, or *not checked yet*;
  - *not relevant to LEMU*: for PVE only, with the reason.

**Changed in review** (tenox7/lemu#1):
- `wsh/0031`: LEMU's SunOS 4.1.4 kit starts the SS-5 without `-machine audiodev` and plays on the
  host's default backend, so "no sound without an audiodev" was not taken. The codec now takes the
  default backend; when there is none it starts anyway, with one warning (`cs4231: no sound: no
  default audio driver available`). wsh-pve took that version. qemu-server always passes
  `-nodefaults`, which leaves QEMU no default backend, so on PVE an SS-5 without `audio0` still
  plays nothing and opens no host sound device; its start log now has that warning
  (`submodules/SPARC.md`, "Audio").
- `wsh/0032`: only its `cs_reset()` hunk changed, after 0031. Taken as well.
- `wsh/0038`: an accepted deviation, see its row.

This page is about sending our patches *to LEMU*. What may go to QEMU is decided by the rule in
[README.md](README.md), not here.

| wsh patch | class | LEMU commit subject | hash | branch | status |
|---|---|---|---|---|---|
| wsh/0001-esp.c-return-to-disconnected-mode-on-SCSI-bus-reset | ours | hw/scsi/esp: return to disconnected mode on a scsi bus reset | [`6d455e60aa`](https://github.com/tenox7/lemu/commit/6d455e60aa) | master | accepted deviation: code comment worded differently |
| wsh/0002-hw-char-escc-name-the-right-interrupt-when-both-chan | LEMU origin | hw/char/escc: name the right interrupt when both channels have one | [`699cc89f71`](https://github.com/tenox7/lemu/commit/699cc89f71) | master | pair only |
| wsh/0003-hw-char-escc-make-the-Sun-keyboard-s-lock-keys-and-k | LEMU origin | hw/char/escc: make the Sun keyboard's lock keys and key repeat work | [`c31ed88ba6`](https://github.com/tenox7/lemu/commit/c31ed88ba6) | master | pair only |
| wsh/0004-hw-char-escc-keep-the-Sun-mouse-in-step-when-the-gue | LEMU origin | hw/char/escc: keep the Sun mouse in step when the guest falls behind | [`181f0f5208`](https://github.com/tenox7/lemu/commit/181f0f5208) | master | pair only |
| wsh/0005-tests-qtest-test-the-Sun-keyboard-and-mouse-on-one-e | LEMU origin | tests/qtest: test the Sun keyboard and mouse on one escc | [`c7a18569f2`](https://github.com/tenox7/lemu/commit/c7a18569f2) | master | pair only |
| wsh/0006-hw-char-escc-lower-the-interrupt-when-the-guest-rese | LEMU origin | hw/char/escc: lower the interrupt when the guest resets a channel | [`c2c2781eb9`](https://github.com/tenox7/lemu/commit/c2c2781eb9) | master | pair only |
| wsh/0007-tests-qtest-am53c974-check-that-Select-with-ATN-work | ours | tests/qtest: am53c974: select with atn works after a scsi bus reset | [`5c9249aa96`](https://github.com/tenox7/lemu/commit/5c9249aa96) | master | accepted deviation: two code comments worded differently |
| wsh/0008-hw-display-cg3-take-screens-of-any-size-up-to-8-MB | LEMU origin | hw/display/cg3: take screens of any size up to 8 MB | [`527b934695`](https://github.com/tenox7/lemu/commit/527b934695) | master | pair only |
| wsh/0009-hw-sparc-sun4m-refuse-a-cg3-size-too-big-to-multiply | LEMU origin | hw/sparc/sun4m: refuse a cg3 size too big to multiply | [`5836ffc349`](https://github.com/tenox7/lemu/commit/5836ffc349) | master | pair only |
| wsh/0010-qemu-options-say-which-screen-sizes-the-cg3-takes | LEMU origin | qemu-options: say which screen sizes the cg3 takes | [`c2c6a828a3`](https://github.com/tenox7/lemu/commit/c2c6a828a3) | master | pair only |
| wsh/0011-hw-misc-slavio_misc-give-the-sun4m-APC-its-16-bytes- | ours | hw/misc/slavio_misc: give the sun4m apc its 16 bytes of registers | [`12f2249c17`](https://github.com/tenox7/lemu/commit/12f2249c17) | master | equal |
| wsh/0012-target-sparc-halt-the-CPU-in-the-SunOS-4.1.4-idle-lo | LEMU origin | target/sparc: halt the CPU in the SunOS 4.1.4 idle loop | [`ff3dbc50bc`](https://github.com/tenox7/lemu/commit/ff3dbc50bc) | master | pair only |
| wsh/0013-hw-sparc-sun4m-add-the-sunos-idle-option-on-by-defau | LEMU origin | hw/sparc/sun4m: add the sunos-idle option, on by default | [`fed03cc7f5`](https://github.com/tenox7/lemu/commit/fed03cc7f5) | master | pair only |
| wsh/0014-target-sparc-halt-the-CPU-in-the-Solaris-idle-loop | built on LEMU | target/sparc: halt the cpu in the solaris idle loop | [`40a1cb142f`](https://github.com/tenox7/lemu/commit/40a1cb142f) | master | accepted deviation: instruction comments on their own lines |
| wsh/0015-hw-sparc-sun4m-add-the-solaris-idle-option-on-by-def | built on LEMU | hw/sparc/sun4m: add the solaris-idle option, on by default | [`0f1aa5f0c7`](https://github.com/tenox7/lemu/commit/0f1aa5f0c7) | master | equal |
| wsh/0016-tests-qtest-test-the-Solaris-idle-halt-on-sun4m | built on LEMU | tests/qtest: test the solaris idle halt on sun4m | [`60a4acb014`](https://github.com/tenox7/lemu/commit/60a4acb014) | master | equal |
| wsh/0017-target-sparc-flush-the-TLB-on-a-no-fault-bit-change- | ours | target/sparc: flush the tlb on a no-fault bit change only when needed | [`7f7081ce39`](https://github.com/tenox7/lemu/commit/7f7081ce39) | master | accepted deviation: the old no-fault comment reflowed |
| wsh/0018-tests-qtest-test-no-fault-mode-and-the-TLB-on-sun4m | ours | tests/qtest: test no-fault mode and the tlb on sun4m | [`7475a0c20a`](https://github.com/tenox7/lemu/commit/7475a0c20a) | master | accepted deviation: comment layout in the PROM table |
| wsh/0019-target-sparc-let-a-write-to-psr-in-a-delay-slot-end- | ours | target/sparc: let a write to %psr in a delay slot end the tb | [`bfdff3fd83`](https://github.com/tenox7/lemu/commit/bfdff3fd83) | master | equal |
| wsh/0020-tests-qtest-test-an-interrupt-let-in-from-a-delay-sl | ours | tests/qtest: test an interrupt let in from a delay slot on sun4m | [`74085832a5`](https://github.com/tenox7/lemu/commit/74085832a5) | master | accepted deviation: comment layout, names[] wrapped |
| wsh/0021-ide-cmd646-latch-the-interrupt-status-bits-until-the | ours | hw/ide/cmd646: latch the interrupt status bits until the guest clears them | [`07e0dfbcee`](https://github.com/tenox7/lemu/commit/07e0dfbcee) | master | equal |
| wsh/0022-tests-qtest-test-the-cmd646-interrupt-status-latch-o | ours | tests/qtest: test the cmd646 interrupt status latch on sun4u | [`198b8baf64`](https://github.com/tenox7/lemu/commit/198b8baf64) | master | equal |
| wsh/0023-target-sparc-halt-idle-CPUs-in-the-Solaris-multiproc | built on LEMU | target/sparc: halt idle cpus in the solaris multiprocessor idle loop | [`887eaf1155`](https://github.com/tenox7/lemu/commit/887eaf1155) | master | accepted deviation: comment placement in translate.c (solaris_idle.c identical) |
| wsh/0024-hw-sparc-sun4m-add-the-solaris-smp-idle-option-on-by | built on LEMU | hw/sparc/sun4m: add the solaris-smp-idle option, on by default | [`bc5b5b9d15`](https://github.com/tenox7/lemu/commit/bc5b5b9d15) | master | equal |
| wsh/0025-tests-qtest-test-the-Solaris-multiprocessor-idle-hal | built on LEMU | tests/qtest: test the solaris multiprocessor idle halt on sun4m | [`c8f869e97c`](https://github.com/tenox7/lemu/commit/c8f869e97c) | master | equal |
| wsh/0026-target-sparc-let-sparc32-ld-and-st-fsr-ignore-rd | LEMU origin | target/sparc: let sparc32 ld and st %fsr ignore rd | [`0cdd14c148`](https://github.com/tenox7/lemu/commit/0cdd14c148) | master | pair only |
| wsh/0027-tests-qtest-test-ld-and-st-fsr-with-any-rd-on-sun4m | built on LEMU | tests/qtest: test ld and st %fsr with any rd on sun4m | [`dbac43854d`](https://github.com/tenox7/lemu/commit/dbac43854d) | master | equal |
| wsh/0028-hw-audio-cs4231-play-sound-through-the-apc-dma-engin | LEMU origin | hw/audio/cs4231: play sound through the apc dma engine | [`2938ff887a`](https://github.com/tenox7/lemu/commit/2938ff887a) | master | pair only |
| wsh/0029-hw-sparc-sun4m-give-the-cs4231-its-interrupt-level-i | LEMU origin | hw/sparc/sun4m: give the cs4231 its interrupt level, iommu and audiodev | [`42d325754c`](https://github.com/tenox7/lemu/commit/42d325754c) | master | pair only |
| wsh/0030-hw-sparc-sun4m-raise-the-SS-5-s-cs4231-at-SBus-level | built on LEMU | hw/sparc/sun4m: raise the ss-5's cs4231 at sbus level 5 | [`e70e62b749`](https://github.com/hwinther/lemu/commit/e70e62b749) | feat/openbios-fixes | accepted deviation: the code comment names machines/openbios patch 0018; on feat/openbios-fixes next to OpenBIOS 0018, and the cs4231 qtest's level change is in this commit |
| wsh/0031-hw-audio-cs4231-start-without-sound-when-there-is-no | built on LEMU | hw/audio/cs4231: start without sound when there is no audio backend | [`27f149cdbc`](https://github.com/tenox7/lemu/commit/27f149cdbc) | master | equal: wsh-pve took the reviewed version (default backend kept, a warning when there is none, reset guard dropped; new subject and file name) |
| wsh/0032-hw-audio-cs4231-play-out-the-last-samples-when-playb | built on LEMU | hw/audio/cs4231: play out the last samples when playback stops | [`32332b27cb`](https://github.com/tenox7/lemu/commit/32332b27cb) | master | equal: wsh-pve took the reviewed version (reset hunk without the audio_be guard, after 0031) |
| wsh/0033-tests-qtest-test-CS4231-playback-through-the-APC-DMA | built on LEMU | tests/qtest: test cs4231 playback through the apc dma on sun4m | [`289850600d`](https://github.com/tenox7/lemu/commit/289850600d) | master | accepted deviation: on feat/sparc-fixes the test expects LEMU's level (bit 9, processor level 5); the level 9 check comes with wsh/0030 |
| wsh/0034-hw-sparc64-sun4u-take-the-IDPROM-MAC-address-from-a- | ours | hw/sparc64/sun4u: take the idprom mac address from a -device nic | [`5e278d30be`](https://github.com/tenox7/lemu/commit/5e278d30be) | master | equal |
| wsh/0035-tests-qtest-test-the-IDPROM-MAC-address-on-sun4u | ours | tests/qtest: test the idprom mac address on sun4u | [`7808238754`](https://github.com/tenox7/lemu/commit/7808238754) | master | equal |
| wsh/0036-target-sparc-write-softint-under-the-BQL | ours | target/sparc: write %softint under the bql | [`0ae4d73dc7`](https://github.com/tenox7/lemu/commit/0ae4d73dc7) | master | equal (applied to LEMU's HELPER() definitions) |
| wsh/0037-tests-qtest-test-that-a-tick-during-a-softint-write- | ours | tests/qtest: test that a tick during a %softint write is kept on sun4u | [`4c9bf5fb47`](https://github.com/tenox7/lemu/commit/4c9bf5fb47) | master | equal |
| wsh/0038-esp-don-t-count-the-message-out-bytes-as-part-of-the | ours | hw/scsi/esp: don't count the message out bytes as part of the cdb | [`dbfd1374f2`](https://github.com/tenox7/lemu/commit/dbfd1374f2) | master | accepted deviation: LEMU's version sits on top of LEMU [`f6b805dd07`](https://github.com/tenox7/lemu/commit/f6b805dd07) ("hw/scsi/esp: run vendor commands sent by pio"), which takes a CDB of the vendor groups as 10 bytes long, so its return line has no `cdblen < 0` test. QEMU 11.1.3 doesn't have that commit, and wsh-pve doesn't take it: its line keeps `cdblen < 0 ? false :`. Both count only the bytes after `cmdfifo_cdb_offset` |
| wsh/0039-tests-qtest-test-a-CDB-sent-byte-by-byte-after-a-mes | ours | tests/qtest: test a cdb sent byte by byte after a message out on sun4m | [`294d6ca3a8`](https://github.com/tenox7/lemu/commit/294d6ca3a8) | master | equal |
| wsh/0040-esp-let-the-interrupt-come-late-as-from-a-real-targe | ours | hw/scsi/esp: let the interrupt come late, as from a real target | `84e71e5e5d` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0041-tests-qtest-test-the-ESP-interrupt-latency-on-sun4m | ours | tests/qtest: test the esp interrupt latency on sun4m | `97e62e6ffd` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0042-target-sparc-halt-the-CPU-in-the-idle-loop-of-sun4u- | built on LEMU | target/sparc: halt the cpu in the idle loop of sun4u guests | `03d0ed1513` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0043-hw-sparc64-sun4u-add-the-idle-halt-option-on-by-defa | built on LEMU | hw/sparc64/sun4u: add the idle-halt option, on by default | `a3f916f836` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0044-tests-qtest-test-the-idle-halt-on-sun4u | built on LEMU | tests/qtest: test the idle halt on sun4u | `c735716322` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0045-hw-pci-host-sabre-keep-PCI-interrupts-to-one-request | ours | hw/pci-host/sabre: keep pci interrupts to one request at a time | `9468a902b1` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0046-tests-qtest-test-the-sabre-s-interrupt-requests-on-s | ours | tests/qtest: test the sabre's interrupt requests on sun4u | `15cef6c8f3` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0047-target-sparc-keep-fetching-from-the-current-page-acr | ours | target/sparc: keep fetching from the current page across a context switch | `e152f36d61` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0048-tests-qtest-test-an-instruction-fetch-across-a-conte | ours | tests/qtest: test an instruction fetch across a context switch on sun4m | `fce789ac81` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0049-target-sparc-take-a-bus-error-on-a-SuperSPARC-load-o | ours | target/sparc: take a bus error on a supersparc load or fetch as an access exception | `6ca40b6181` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0050-tests-qtest-test-the-trap-a-bus-error-takes-on-sun4m | ours | tests/qtest: test the trap a bus error takes on sun4m | `f4b21009a6` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0051-hw-display-vga-read-the-attribute-address-at-0x3c0-i | ours | - | none | none | not in LEMU: applies |
| wsh/0052-tests-qtest-test-reading-the-VGA-attribute-address-a | ours | - | none | none | not in LEMU: applies |
| wsh/0053-target-sparc-defer-the-fp_exception-of-an-IEEE-754-e | ours | target/sparc: defer the fp_exception of an ieee 754 exception on sparc32 | `861eb9bbf9` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal: since 2026-11-25 the helper is defined with `HELPER()` here too, as LEMU's maintainer asked |
| wsh/0054-tests-qtest-test-the-deferred-fp_exception-trap-on-s | ours | tests/qtest: test the deferred fp_exception trap on sun4m | `0806178a54` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0055-hw-sparc-sun4m-take-at-most-128-MB-of-RAM-on-the-mic | ours | hw/sparc/sun4m: take at most 128 mb of ram on the microsparc-i machines | `3ac66e70ae` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0056-hw-sparc-sun4m-map-the-SPARCstation-LX-s-on-board-SB | ours | hw/sparc/sun4m: map the sparcstation lx's on-board sbus devices | `cf186f8053` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0057-hw-sparc-sun4m-give-the-DBRI-an-FCode-PROM-that-make | ours | hw/sparc/sun4m: give the dbri an fcode prom that makes its node | `b50db2fa7d` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0058-tests-qtest-test-the-on-board-SBus-devices-of-sun4m | ours | tests/qtest: test the on-board sbus devices of sun4m | `4fb4d74e07` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0059-hw-rtc-m48t59-keep-the-NVRAM-in-a-drive-and-leave-it | built on LEMU | hw/rtc/m48t59: take a drive on the sysbus device, and leave its nvram on sun4m | `c11c33129c` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal: LEMU's port onto its `m48t59` storage (`wsh/0073`), taken here in place of the earlier write-through version |
| wsh/0060-tests-qtest-test-the-sun4m-NVRAM-kept-in-a-drive | ours | tests/qtest: test the sun4m nvram kept in a drive | `329bc9e639` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal; context only: its `meson.build` line follows `sun4m-onboard-sbus-test` here and `sun4m-dbri-test` on the branch |
| wsh/0061-hw-dma-sparc32_dma-reset-the-lance-DMA-s-base-addres | ours | hw/dma/sparc32_dma: reset the lance dma's base address register to 0xff | `2f032b3258` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0062-tests-qtest-test-the-lance-DMA-s-base-address-regist | ours | tests/qtest: test the lance dma's base address register on sun4m | `4b0c6160c9` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | accepted deviation: its `meson.build` line follows `sun4m-onboard-sbus-test`, as 0059-0060 come after it on the branch |
| wsh/0063-hw-sparc-sun4m-map-the-SPARCserver-600MP-s-VMEbus-in | ours | hw/sparc/sun4m: map the sparcserver 600mp's vmebus interface registers | `1f106dba2a` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0064-hw-sparc-sun4m-give-the-SPARCserver-600MP-s-lance-it | ours | hw/sparc/sun4m: give the sparcserver 600mp's lance its own buffer memory | `ac11d7c20e` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0065-tests-qtest-test-the-SPARCserver-600MP-s-VMEbus-regi | ours | tests/qtest: test the sparcserver 600mp's vmebus registers and lebuffer | `946c5f1064` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0066-hw-sparc-sun4m-give-the-DBRI-registers-that-take-its | ours | hw/sparc/sun4m: give the dbri registers that take its command queue | `c286e70b53` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0067-tests-qtest-test-the-DBRI-s-registers-and-command-qu | ours | tests/qtest: test the dbri's registers and command queue on sun4m | `1a0e1fda34` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0068-hw-pci-host-sabre-reset-the-PCI-control-status-regis | ours | hw/pci-host/sabre: reset the pci control/status registers | `8117738bbf` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0069-tests-qtest-test-the-sabre-s-PCI-control-registers-a | ours | tests/qtest: test the sabre's pci control registers after a reset | `7b77447da3` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0070-target-sparc-halt-the-CPU-in-Linux-s-idle-loop-on-su | built on LEMU | target/sparc: halt the cpu in linux's idle loop on sun4u | `05707468b7` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0071-target-sparc-recognise-the-idle-loop-of-Solaris-7-an | built on LEMU | target/sparc: recognise the idle loop of solaris 7 and 8 on sun4u | `9e4b0e95b4` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0072-tests-qtest-test-the-Linux-and-Solaris-7-8-idle-loop | built on LEMU | tests/qtest: test the linux and solaris 7/8 idle loops on sun4u | `2710ab1887` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0073-hw-rtc-m48t59-back-the-NVRAM-with-a-block-device | LEMU origin | hw/rtc/m48t59: keep NVRAM contents in a file; hw/rtc/m48t59: back the NVRAM with a block device | [`ae4bb79885`](https://github.com/tenox7/lemu/commit/ae4bb79885), [`4b98747213`](https://github.com/tenox7/lemu/commit/4b98747213) | master | pair only: the two squashed, without `4b98747213`'s `hw/ppc/prep.c` hunk (LEMU's 40p) |
| wsh/0110-target-sparc-halt-the-CPU-in-Linux-3.2-s-idle-loop-o | built on LEMU | target/sparc: halt the cpu in linux 3.2's idle loop on sun4u | `cdbee68f88` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0111-tests-qtest-test-the-Linux-3.2-idle-loop-on-sun4u | built on LEMU | tests/qtest: test the linux 3.2 idle loop on sun4u | `b33b632a9a` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0112-hw-sparc64-drop-the-translated-code-on-a-reset | ours | hw/sparc64: drop the translated code on a reset | `45daa7e9e7` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0113-tests-qtest-test-the-TB-flush-on-a-sun4u-reset | ours | tests/qtest: test the tb flush on a sun4u reset | `181bae395a` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0114-target-sparc-halt-the-CPU-in-FreeBSD-s-idle-loop-on- | built on LEMU | target/sparc: halt the cpu in freebsd's idle loop on sun4u | `d52ff58d64` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0115-tests-qtest-test-the-FreeBSD-idle-loop-on-sun4u | built on LEMU | tests/qtest: test the freebsd idle loop on sun4u | `6cf9ef6a7f` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0120-target-sparc-keep-SuperSPARC-instruction-fetches-in- | ours | target/sparc: keep supersparc instruction fetches in the prom in boot mode with the mmu on | `5460d36d69` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0121-tests-qtest-test-SuperSPARC-boot-mode-with-the-MMU-o | ours | tests/qtest: test supersparc boot mode with the mmu on | `a0d92c14ef` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0122-hw-audio-cs4231-raise-pi-and-pmi-when-the-codec-gets | built on LEMU | hw/audio/cs4231: raise pi and pmi when the codec gets there | [`00e72649b8`](https://github.com/hwinther/lemu/commit/00e72649b8) | fix/cs4231-pi-pmi | equal |
| wsh/0123-tests-qtest-test-the-cs4231-s-pi-and-pmi-for-a-short | built on LEMU | tests/qtest: test the cs4231's pi and pmi for a short buffer on sun4m | [`0a78fc843f`](https://github.com/hwinther/lemu/commit/0a78fc843f) | fix/cs4231-pi-pmi | equal (applies with line offsets) |
| wsh/0124-hw-audio-cs4231-set-the-codec-s-int-and-pi-with-the- | ours, on LEMU's CS4231 | hw/audio/cs4231: set the codec's int and pi with the apc's playback interrupts | `9fbdd5b68a` (LEMU local, not pushed) | fix/cs4231-codec-int (LEMU local) | equal (taken unchanged); also `7e9e3da210` on feat/sparc-fixes-2 |
| wsh/0125-tests-qtest-test-the-cs4231-s-int-status-bit-and-i24 | ours, on LEMU's CS4231 | tests/qtest: test the cs4231's int status bit and i24 pi on sun4m | `0e81145602` (LEMU local, not pushed) | fix/cs4231-codec-int (LEMU local) | equal (taken unchanged); also `832effdbbf` on feat/sparc-fixes-2 |
| wsh/0126-hw-audio-cs4231-clear-i24-s-pi-ci-and-ti-on-a-status | ours, on LEMU's CS4231 | hw/audio/cs4231: clear i24's pi, ci and ti on a status register write | `b51bdee68a` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0127-tests-qtest-test-that-a-cs4231-status-write-clears-i | ours, on LEMU's CS4231 | tests/qtest: test that a cs4231 status write clears i24 on sun4m | `6357284f8e` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0128-hw-audio-cs4231-drop-what-the-apc-took-past-the-code | ours, on LEMU's CS4231 | hw/audio/cs4231: drop what the apc took past the codec on a stop | `c443d25f9f` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0129-tests-qtest-test-cs4231-stops-and-migration-with-sam | ours, on LEMU's CS4231 | tests/qtest: test cs4231 stops and migration with samples taken ahead | `52fb03718f` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0130-ui-dbus-read-GL-scanouts-back-for-VNC-next-to-displa | ours | - | none | none | not relevant to LEMU: PVE's D-Bus display with VNC; LEMU's `ui/dbus` is newer (QEMU master) and the patch does not apply |
| wsh/0131-ui-dbus-add-display-dbus-refresh-ms-N | ours | - | none | none | not relevant to LEMU: PVE's D-Bus display; does not apply to LEMU's `ui/dbus.c` |
| wsh/0132-tests-qtest-test-display-dbus-refresh-ms | ours | - | none | none | not relevant to LEMU: qtest for 0131 |
| wsh/0133-hw-sparc64-migrate-the-sabre-the-IOMMU-the-ebus-and- | ours | hw/sparc64: migrate the sabre, the iommu, the ebus and the cpu's interrupts | `6b61ecca5f` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0134-tests-qtest-test-the-sabre-s-the-IOMMU-s-and-the-ebu | ours | tests/qtest: test the sabre's, the iommu's and the ebus's migration on sun4u | `207a514620` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0135-hw-net-sunhme-stop-the-receiver-on-a-reset-until-the | ours | hw/net/sunhme: stop the receiver on a reset until the guest enables it | `3e354640e2` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0136-tests-qtest-test-the-sunhme-s-receiver-after-a-reset | ours | tests/qtest: test the sunhme's receiver after a reset on sun4u | `94d43a43bf` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0137-hw-pci-host-sabre-drop-a-slot-s-request-when-the-gue | ours | hw/pci-host/sabre: drop a slot's request when the guest disables the slot | `c1064c7179` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0138-tests-qtest-test-disabling-a-PCI-interrupt-on-the-sa | ours | tests/qtest: test disabling a pci interrupt on the sabre | `74e9c40d0b` (LEMU local, not pushed) | feat/sparc-fixes-2 (LEMU local) | equal |
| wsh/0139-target-sparc-halt-Linux-s-idle-loop-on-sun4u-under-t | built on LEMU | - | none | none | not in LEMU: not checked yet |
| wsh/0140-tests-qtest-test-a-tick-between-the-idle-check-and-t | built on LEMU | - | none | none | not in LEMU: not checked yet |
| wsh/0141-hw-char-escc-end-a-break-with-an-interrupt-for-its-s | built on LEMU | - | none | none | not in LEMU: not checked yet |
| wsh/0142-tests-qtest-test-a-break-on-a-serial-line-of-the-sun | built on LEMU | - | none | none | not in LEMU: not checked yet |
| wsh/0143-hw-sparc-sun4m-present-the-MCC-with-more-than-512-MB | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0144-tests-qtest-test-the-memory-controller-version-with- | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0145-target-sparc-keep-the-SuperSPARC-store-buffer-diagno | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0146-target-sparc-read-back-the-MXCC-stream-data-register | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0147-target-sparc-keep-the-SuperSPARC-cache-tag-and-data- | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0148-tests-qtest-test-the-SuperSPARC-diagnostic-registers | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0149-hw-timer-slavio_timer-let-the-user-timer-reach-its-l | ours | - | none | none | not in LEMU: not checked yet |
| wsh/0150-tests-qtest-test-the-sun4m-user-timer-s-limit-and-th | ours | - | none | none | not in LEMU: not checked yet |

| OpenBIOS patch | class | LEMU side (file, commit subject) | hash | branch | status |
|---|---|---|---|---|---|
| openbios/0001-esp-treat-a-selection-timeout-as-no-device.patch | ours | machines/openbios/patches/0001-esp-treat-a-selection-timeout-as-no-device.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0002-cgthree-map-only-the-console-lines-that-fit.patch | LEMU origin | machines/sun4m/cgthree/cgthree.fs, "pc-bios: let the cg3 fcode run screens bigger than 1024 x 768" | [`9ea85e132e`](https://github.com/tenox7/lemu/commit/9ea85e132e) | master | pair only |
| openbios/0003-sparc64-list-the-whole-virtual-address-space-as-available.patch | ours | machines/openbios/patches/0003-sparc64-list-the-whole-virtual-address-space-as-available.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0004-sparc64-give-the-cpu-node-the-icache-size.patch | ours | machines/openbios/patches/0004-sparc64-give-the-cpu-node-the-icache-size.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0005-sparc64-leave-no-active-package-after-preopen.patch | ours | machines/openbios/patches/0005-sparc64-leave-no-active-package-after-preopen.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0006-sparc64-client-dont-define-a-forth-constant.patch | ours | machines/openbios/patches/0006-sparc64-client-dont-define-a-forth-constant.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0007-sparc64-fcode-consume-instance-in-defining-words.patch | ours | machines/openbios/patches/0007-sparc64-fcode-consume-instance-in-defining-words.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0008-sparc32-enter-the-prompt-on-op_enter-and-resume-with-go.patch | ours | machines/openbios/patches/0008-sparc32-enter-the-prompt-on-op_enter-and-resume-with-go.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0009-sparc64-name-upa-and-ebus-children-like-obp.patch | ours | machines/openbios/patches/0009-sparc64-name-upa-and-ebus-children-like-obp.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0010-sparc64-pathres-interposed-package-gets-the-device-my-unit.patch | ours | machines/openbios/patches/0010-sparc64-pathres-interposed-package-gets-the-device-my-unit.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0011-sparc64-put-ide-drives-under-the-controller.patch | ours | machines/openbios/patches/0011-sparc64-put-ide-drives-under-the-controller.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0012-sparc64-reset-the-machine-on-the-client-interface-boot-service.patch.wip | ours | - | - | - | not forwarded: does not work |
| openbios/0013-sparc64-ofmem-keep-the-upper-bits-of-physical-addresses-in-align_ptr.patch | ours | machines/openbios/patches/0013-sparc64-ofmem-keep-the-upper-bits-of-physical-addresses-in-align_ptr.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0014-sparc64-ofmem-find-claim-memory-whose-1-1-virtual-range-is-free.patch | ours | machines/openbios/patches/0014-sparc64-ofmem-find-claim-memory-whose-1-1-virtual-range-is-free.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0015-sparc64-return-the-whole-physical-address-in-phys-lo.patch | ours | machines/openbios/patches/0015-sparc64-return-the-whole-physical-address-in-phys-lo.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0016-sparc64-client-interface-runs-with-interrupts-disabled.patch | ours | machines/openbios/patches/0016-sparc64-client-interface-runs-with-interrupts-disabled.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0017-sparc64-fcode-put-xa-plus-and-xa1-plus-into-the-64-bit-table.patch | ours | machines/openbios/patches/0017-sparc64-fcode-put-xa-plus-and-xa1-plus-into-the-64-bit-table.patch, "machines/openbios: patches for sparc32 and sparc64 and a build script" | [`82e062a57c`](https://github.com/hwinther/lemu/commit/82e062a57c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0018-sparc32-give-the-cs4231-intr-9-the-level-of-its-sbus-level.patch | built on LEMU | machines/openbios/patches/0018-sparc32-give-the-cs4231-intr-9-the-level-of-its-sbus-level.patch, "machines/openbios: add the sparc32 patch for the cs4231's intr" | [`82153d907c`](https://github.com/hwinther/lemu/commit/82153d907c) | feat/openbios-fixes | equal (byte-identical) |
| openbios/0019-sparc32-give-the-solaris-2.1-2.4-boot-block-the-obp-words-it-uses.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0020-sparc32-keep-the-forth-heap-inside-the-firmwares-own-virtual-range.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0021-sparc32-take-node-0-as-the-root-node-in-the-romvec-property-operations.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0022-sparc32-run-the-romvec-calls-with-interrupts-masked.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0023-client-call-method-store-the-catch-result-only-when-nret-is-not-0.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0024-sparc64-ofmem-list-whole-pages-in-memory-available.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0025-sparc64-leave-out-the-ebus-floppy-node.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0026-fb8-blink-screen-dont-wait-on-a-counter-that-may-be-stopped.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0027-sparc32-leave-out-the-apc-node-on-the-lx-and-the-voyager.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0028-sparc32-name-the-ss600mp-dma-and-lebuffer-nodes-as-sunos-4.1.2-knows-them.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0029-sparc32-leave-out-the-cs4231-node-where-qemu-has-no-codec.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0030-sparc64-reset-the-machine-on-the-client-interface-boot-service.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0031-sparc64-give-the-solaris-2.5.1-2.6-boot-block-init-program-and-go.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0032-sparc64-keep-interrupts-disabled-in-the-mmu-miss-handlers.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0033-sparc64-save-and-restore-the-trap-state-of-tl-4-to-1.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0034-sparc32-mark-the-cs4231-intr-as-an-sbus-interrupt-0x39.patch | built on LEMU | - | none | none | not in LEMU: applies on feat/openbios-fixes, next to 0018 |
| openbios/0035-sparc64-give-the-ebus-8042-a-kdmouse-child.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0036-sparc64-list-the-sabre-64-bit-memory-space-in-its-ranges.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0037-sparc64-give-openprom-the-aligned-allocator-property.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0038-sparc64-leave-the-lock-bit-out-of-the-translations-property.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0039-sparc64-name-the-root-node-sun-ultra-5-10.patch | ours | - | none | none | not in LEMU: applies on feat/openbios-fixes (same OpenBIOS base) |
| openbios/0040-sparc32-take-the-srmmu-tables-from-chunks-of-a-larger-heap.patch | ours | - | none | none | not in LEMU: not checked yet |
