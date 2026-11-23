# Our patches in LEMU

Where each patch this repository carries sits in [LEMU](https://github.com/tenox7/lemu), Antoni
Sawicki's QEMU fork for vintage machines. Our own patches are offered to LEMU from the fork
[hwinther/lemu](https://github.com/hwinther/lemu), in two branches:

- `feat/sparc-fixes`: the pve-qemu patches (`debian/patches/wsh/`), at `5fe502d848`. Sent as
  [tenox7/lemu#1](https://github.com/tenox7/lemu/pull/1): open; the changes asked for in review
  are pushed. It also has two commits that exist only in LEMU (`c3abf5cbd1`, a functional test that
  boots NetBSD on sun4m and sun4u, and `8b25fc6b99`, notes on the Solaris idle options and a sun4u
  folder in LEMU's `machines/`). The wsh patches in it have
  `Forwarded: https://github.com/tenox7/lemu/pull/1` in their headers; none is `Applied-Upstream`
  yet.
- `fix/cs4231-pi-pmi`: `wsh/0122`-`0123` (the CS4231's PI and PMI at the codec's time), two
  commits on `feat/sparc-fixes` at `5fe502d848`. Written in LEMU first and carried here with `Origin:` lines;
  LEMU took 0123's `migrate` wait into its test commit (now `c92620599a`), so both are equal; the
  branch is LEMU PR #1. Not sent to tenox7/lemu.
- `wsh/0124`-`0125` (the codec's INT status bit and I24's PI with the APC's playback interrupts,
  for Linux's `snd-sun-cs4231`): ours, written here on LEMU's CS4231 (0028, 0122) to the LEMU
  maintainer's requirements. LEMU took both unchanged onto a local branch `fix/cs4231-codec-int`
  (on top of `fix/cs4231-pi-pmi`, not pushed): `9fbdd5b68a` and `0e81145602`, so they are equal.
- `wsh/0126`-`0129`: ours, on LEMU's CS4231, after the LEMU maintainer's review of 0124: a write
  to the status register also clears PI, CI and TI in I24 (0126, qtest 0127), and a stop in the
  middle of a buffer drops what the APC took past the codec's position instead of playing it out
  (0128, qtest 0129). Offered to LEMU, not taken yet.
- `feat/openbios-fixes`: the OpenBIOS patches and the one QEMU patch that goes with them (`wsh/0030`
  with OpenBIOS 0018), at `86c3a500ec`. Not sent yet.

Both are rebased onto LEMU's `master` at `a71589ebda`. Their hashes change again when they are
rebased. Patches of LEMU origin are paired with their commit on LEMU's `master`.

Compared against this repository at `3f3e5d8` (2026-11-18); `wsh/0031`, `0032` and `0038`, which
changed in review, were compared again on 2026-11-21. Not covered: pve-qemu `wsh/0040`-`0062` and
OpenBIOS 0019-0026, which came later. No further patch goes to LEMU until #1 is merged. So the
framebuffer console's hang on a BEL (`fb8-blink-screen`), fixed here by OpenBIOS 0026, is still open
in LEMU: neither its `master` nor `feat/openbios-fixes` has that patch.

**Columns:**
- **class**: as in [README.md](README.md): *ours*, *LEMU origin* or *built on LEMU*.
- **status**: compares the added and removed lines, ignoring context and whitespace:
  - *equal*: the same change;
  - *accepted deviation*: differs only as described;
  - *pair only*: a LEMU commit we carry, so there is nothing to compare;
  - *not forwarded*: kept here only.

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
| wsh/0001-esp.c-return-to-disconnected-mode-on-SCSI-bus-reset | ours | hw/scsi/esp: return to disconnected mode on a scsi bus reset | [`735b60df03`](https://github.com/hwinther/lemu/commit/735b60df03) | feat/sparc-fixes | accepted deviation: code comment worded differently |
| wsh/0002-hw-char-escc-name-the-right-interrupt-when-both-chan | LEMU origin | hw/char/escc: name the right interrupt when both channels have one | [`699cc89f71`](https://github.com/tenox7/lemu/commit/699cc89f71) | master | pair only |
| wsh/0003-hw-char-escc-make-the-Sun-keyboard-s-lock-keys-and-k | LEMU origin | hw/char/escc: make the Sun keyboard's lock keys and key repeat work | [`c31ed88ba6`](https://github.com/tenox7/lemu/commit/c31ed88ba6) | master | pair only |
| wsh/0004-hw-char-escc-keep-the-Sun-mouse-in-step-when-the-gue | LEMU origin | hw/char/escc: keep the Sun mouse in step when the guest falls behind | [`181f0f5208`](https://github.com/tenox7/lemu/commit/181f0f5208) | master | pair only |
| wsh/0005-tests-qtest-test-the-Sun-keyboard-and-mouse-on-one-e | LEMU origin | tests/qtest: test the Sun keyboard and mouse on one escc | [`c7a18569f2`](https://github.com/tenox7/lemu/commit/c7a18569f2) | master | pair only |
| wsh/0006-hw-char-escc-lower-the-interrupt-when-the-guest-rese | LEMU origin | hw/char/escc: lower the interrupt when the guest resets a channel | [`c2c2781eb9`](https://github.com/tenox7/lemu/commit/c2c2781eb9) | master | pair only |
| wsh/0007-tests-qtest-am53c974-check-that-Select-with-ATN-work | ours | tests/qtest: am53c974: select with atn works after a scsi bus reset | [`a6d229b71c`](https://github.com/hwinther/lemu/commit/a6d229b71c) | feat/sparc-fixes | accepted deviation: two code comments worded differently |
| wsh/0008-hw-display-cg3-take-screens-of-any-size-up-to-8-MB | LEMU origin | hw/display/cg3: take screens of any size up to 8 MB | [`527b934695`](https://github.com/tenox7/lemu/commit/527b934695) | master | pair only |
| wsh/0009-hw-sparc-sun4m-refuse-a-cg3-size-too-big-to-multiply | LEMU origin | hw/sparc/sun4m: refuse a cg3 size too big to multiply | [`5836ffc349`](https://github.com/tenox7/lemu/commit/5836ffc349) | master | pair only |
| wsh/0010-qemu-options-say-which-screen-sizes-the-cg3-takes | LEMU origin | qemu-options: say which screen sizes the cg3 takes | [`c2c6a828a3`](https://github.com/tenox7/lemu/commit/c2c6a828a3) | master | pair only |
| wsh/0011-hw-misc-slavio_misc-give-the-sun4m-APC-its-16-bytes- | ours | hw/misc/slavio_misc: give the sun4m apc its 16 bytes of registers | [`6e4020d5ba`](https://github.com/hwinther/lemu/commit/6e4020d5ba) | feat/sparc-fixes | equal |
| wsh/0012-target-sparc-halt-the-CPU-in-the-SunOS-4.1.4-idle-lo | LEMU origin | target/sparc: halt the CPU in the SunOS 4.1.4 idle loop | [`ff3dbc50bc`](https://github.com/tenox7/lemu/commit/ff3dbc50bc) | master | pair only |
| wsh/0013-hw-sparc-sun4m-add-the-sunos-idle-option-on-by-defau | LEMU origin | hw/sparc/sun4m: add the sunos-idle option, on by default | [`fed03cc7f5`](https://github.com/tenox7/lemu/commit/fed03cc7f5) | master | pair only |
| wsh/0014-target-sparc-halt-the-CPU-in-the-Solaris-idle-loop | built on LEMU | target/sparc: halt the cpu in the solaris idle loop | [`07e6cf8fce`](https://github.com/hwinther/lemu/commit/07e6cf8fce) | feat/sparc-fixes | accepted deviation: instruction comments on their own lines |
| wsh/0015-hw-sparc-sun4m-add-the-solaris-idle-option-on-by-def | built on LEMU | hw/sparc/sun4m: add the solaris-idle option, on by default | [`1ca498cbad`](https://github.com/hwinther/lemu/commit/1ca498cbad) | feat/sparc-fixes | equal |
| wsh/0016-tests-qtest-test-the-Solaris-idle-halt-on-sun4m | built on LEMU | tests/qtest: test the solaris idle halt on sun4m | [`0f4274ebf4`](https://github.com/hwinther/lemu/commit/0f4274ebf4) | feat/sparc-fixes | equal |
| wsh/0017-target-sparc-flush-the-TLB-on-a-no-fault-bit-change- | ours | target/sparc: flush the tlb on a no-fault bit change only when needed | [`b14949a1ce`](https://github.com/hwinther/lemu/commit/b14949a1ce) | feat/sparc-fixes | accepted deviation: the old no-fault comment reflowed |
| wsh/0018-tests-qtest-test-no-fault-mode-and-the-TLB-on-sun4m | ours | tests/qtest: test no-fault mode and the tlb on sun4m | [`575dfb4d0f`](https://github.com/hwinther/lemu/commit/575dfb4d0f) | feat/sparc-fixes | accepted deviation: comment layout in the PROM table |
| wsh/0019-target-sparc-let-a-write-to-psr-in-a-delay-slot-end- | ours | target/sparc: let a write to %psr in a delay slot end the tb | [`918767d258`](https://github.com/hwinther/lemu/commit/918767d258) | feat/sparc-fixes | equal |
| wsh/0020-tests-qtest-test-an-interrupt-let-in-from-a-delay-sl | ours | tests/qtest: test an interrupt let in from a delay slot on sun4m | [`fc0978ed8f`](https://github.com/hwinther/lemu/commit/fc0978ed8f) | feat/sparc-fixes | accepted deviation: comment layout, names[] wrapped |
| wsh/0021-ide-cmd646-latch-the-interrupt-status-bits-until-the | ours | hw/ide/cmd646: latch the interrupt status bits until the guest clears them | [`78abfcfe86`](https://github.com/hwinther/lemu/commit/78abfcfe86) | feat/sparc-fixes | equal |
| wsh/0022-tests-qtest-test-the-cmd646-interrupt-status-latch-o | ours | tests/qtest: test the cmd646 interrupt status latch on sun4u | [`893b76e02b`](https://github.com/hwinther/lemu/commit/893b76e02b) | feat/sparc-fixes | equal |
| wsh/0023-target-sparc-halt-idle-CPUs-in-the-Solaris-multiproc | built on LEMU | target/sparc: halt idle cpus in the solaris multiprocessor idle loop | [`34e24c2794`](https://github.com/hwinther/lemu/commit/34e24c2794) | feat/sparc-fixes | accepted deviation: comment placement in translate.c (solaris_idle.c identical) |
| wsh/0024-hw-sparc-sun4m-add-the-solaris-smp-idle-option-on-by | built on LEMU | hw/sparc/sun4m: add the solaris-smp-idle option, on by default | [`a4a004c8dc`](https://github.com/hwinther/lemu/commit/a4a004c8dc) | feat/sparc-fixes | equal |
| wsh/0025-tests-qtest-test-the-Solaris-multiprocessor-idle-hal | built on LEMU | tests/qtest: test the solaris multiprocessor idle halt on sun4m | [`c9dbe58ec3`](https://github.com/hwinther/lemu/commit/c9dbe58ec3) | feat/sparc-fixes | equal |
| wsh/0026-target-sparc-let-sparc32-ld-and-st-fsr-ignore-rd | LEMU origin | target/sparc: let sparc32 ld and st %fsr ignore rd | [`0cdd14c148`](https://github.com/tenox7/lemu/commit/0cdd14c148) | master | pair only |
| wsh/0027-tests-qtest-test-ld-and-st-fsr-with-any-rd-on-sun4m | built on LEMU | tests/qtest: test ld and st %fsr with any rd on sun4m | [`9632e6fb5d`](https://github.com/hwinther/lemu/commit/9632e6fb5d) | feat/sparc-fixes | equal |
| wsh/0028-hw-audio-cs4231-play-sound-through-the-apc-dma-engin | LEMU origin | hw/audio/cs4231: play sound through the apc dma engine | [`2938ff887a`](https://github.com/tenox7/lemu/commit/2938ff887a) | master | pair only |
| wsh/0029-hw-sparc-sun4m-give-the-cs4231-its-interrupt-level-i | LEMU origin | hw/sparc/sun4m: give the cs4231 its interrupt level, iommu and audiodev | [`42d325754c`](https://github.com/tenox7/lemu/commit/42d325754c) | master | pair only |
| wsh/0030-hw-sparc-sun4m-raise-the-SS-5-s-cs4231-at-SBus-level | built on LEMU | hw/sparc/sun4m: raise the ss-5's cs4231 at sbus level 5 | [`e70e62b749`](https://github.com/hwinther/lemu/commit/e70e62b749) | feat/openbios-fixes | accepted deviation: the code comment names machines/openbios patch 0018; on feat/openbios-fixes next to OpenBIOS 0018, and the cs4231 qtest's level change is in this commit |
| wsh/0031-hw-audio-cs4231-start-without-sound-when-there-is-no | built on LEMU | hw/audio/cs4231: start without sound when there is no audio backend | [`18c8c6eba3`](https://github.com/hwinther/lemu/commit/18c8c6eba3) | feat/sparc-fixes | equal: wsh-pve took the reviewed version (default backend kept, a warning when there is none, reset guard dropped; new subject and file name) |
| wsh/0032-hw-audio-cs4231-play-out-the-last-samples-when-playb | built on LEMU | hw/audio/cs4231: play out the last samples when playback stops | [`0673770a4b`](https://github.com/hwinther/lemu/commit/0673770a4b) | feat/sparc-fixes | equal: wsh-pve took the reviewed version (reset hunk without the audio_be guard, after 0031) |
| wsh/0033-tests-qtest-test-CS4231-playback-through-the-APC-DMA | built on LEMU | tests/qtest: test cs4231 playback through the apc dma on sun4m | [`bf9cdd6f53`](https://github.com/hwinther/lemu/commit/bf9cdd6f53) | feat/sparc-fixes | accepted deviation: on feat/sparc-fixes the test expects LEMU's level (bit 9, processor level 5); the level 9 check comes with wsh/0030 |
| wsh/0034-hw-sparc64-sun4u-take-the-IDPROM-MAC-address-from-a- | ours | hw/sparc64/sun4u: take the idprom mac address from a -device nic | [`e3344021fc`](https://github.com/hwinther/lemu/commit/e3344021fc) | feat/sparc-fixes | equal |
| wsh/0035-tests-qtest-test-the-IDPROM-MAC-address-on-sun4u | ours | tests/qtest: test the idprom mac address on sun4u | [`679d3eecc0`](https://github.com/hwinther/lemu/commit/679d3eecc0) | feat/sparc-fixes | equal |
| wsh/0036-target-sparc-write-softint-under-the-BQL | ours | target/sparc: write %softint under the bql | [`8f17a732ab`](https://github.com/hwinther/lemu/commit/8f17a732ab) | feat/sparc-fixes | equal (applied to LEMU's HELPER() definitions) |
| wsh/0037-tests-qtest-test-that-a-tick-during-a-softint-write- | ours | tests/qtest: test that a tick during a %softint write is kept on sun4u | [`4b28611dfb`](https://github.com/hwinther/lemu/commit/4b28611dfb) | feat/sparc-fixes | equal |
| wsh/0038-esp-don-t-count-the-message-out-bytes-as-part-of-the | ours | hw/scsi/esp: don't count the message out bytes as part of the cdb | [`1879f6152e`](https://github.com/hwinther/lemu/commit/1879f6152e) | feat/sparc-fixes | accepted deviation: LEMU's version sits on top of LEMU [`f6b805dd07`](https://github.com/tenox7/lemu/commit/f6b805dd07) ("hw/scsi/esp: run vendor commands sent by pio"), which takes a CDB of the vendor groups as 10 bytes long, so its return line has no `cdblen < 0` test. QEMU 11.1.3 doesn't have that commit, and wsh-pve doesn't take it: its line keeps `cdblen < 0 ? false :`. Both count only the bytes after `cmdfifo_cdb_offset` |
| wsh/0039-tests-qtest-test-a-CDB-sent-byte-by-byte-after-a-mes | ours | tests/qtest: test a cdb sent byte by byte after a message out on sun4m | [`5fe502d848`](https://github.com/hwinther/lemu/commit/5fe502d848) | feat/sparc-fixes | equal |
| wsh/0122-hw-audio-cs4231-raise-pi-and-pmi-when-the-codec-gets | built on LEMU | hw/audio/cs4231: raise pi and pmi when the codec gets there | [`ff412bc835`](https://github.com/hwinther/lemu/commit/ff412bc835) | fix/cs4231-pi-pmi | equal |
| wsh/0123-tests-qtest-test-the-cs4231-s-pi-and-pmi-for-a-short | built on LEMU | tests/qtest: test the cs4231's pi and pmi for a short buffer on sun4m | [`c92620599a`](https://github.com/hwinther/lemu/commit/c92620599a) | fix/cs4231-pi-pmi | equal (applies with line offsets) |
| wsh/0124-hw-audio-cs4231-set-the-codec-s-int-and-pi-with-the- | ours, on LEMU's CS4231 | hw/audio/cs4231: set the codec's int and pi with the apc's playback interrupts | `9fbdd5b68a` (LEMU local, not pushed) | fix/cs4231-codec-int (LEMU local) | equal (taken unchanged) |
| wsh/0125-tests-qtest-test-the-cs4231-s-int-status-bit-and-i24 | ours, on LEMU's CS4231 | tests/qtest: test the cs4231's int status bit and i24 pi on sun4m | `0e81145602` (LEMU local, not pushed) | fix/cs4231-codec-int (LEMU local) | equal (taken unchanged) |
| wsh/0126-hw-audio-cs4231-clear-i24-s-pi-ci-and-ti-on-a-status | ours, on LEMU's CS4231 | hw/audio/cs4231: clear i24's pi, ci and ti on a status register write | none | none | offered to LEMU, not taken yet |
| wsh/0127-tests-qtest-test-that-a-cs4231-status-write-clears-i | ours, on LEMU's CS4231 | tests/qtest: test that a cs4231 status write clears i24 on sun4m | none | none | offered to LEMU, not taken yet |
| wsh/0128-hw-audio-cs4231-drop-what-the-apc-took-past-the-code | ours, on LEMU's CS4231 | hw/audio/cs4231: drop what the apc took past the codec on a stop | none | none | offered to LEMU, not taken yet |
| wsh/0129-tests-qtest-test-a-cs4231-stop-in-the-middle-of-a-bu | ours, on LEMU's CS4231 | tests/qtest: test a cs4231 stop in the middle of a buffer on sun4m | none | none | offered to LEMU, not taken yet |

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
