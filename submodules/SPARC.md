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

The ESCC, cg3 and SunOS idle patches are by Antoni Sawicki, from [LEMU](https://github.com/tenox7/lemu), a QEMU
fork for vintage machines (GPLv2, like QEMU). LEMU states that its code won't be sent to QEMU, so we
carry it ourselves. Each patch keeps its author and has an `Origin:` line.

Tested: `sun4m-escc-test` fails without 0002-0006 and passes 4/4 with them on 11.1.3;
`test_select_after_bus_reset_ok` fails from `6f8ce26bb0` through 11.1.3 and passes with 0001.
The full series (Proxmox's patches + ours) applies on QEMU 11.1.3; no Proxmox patch touches
`esp.c` or `escc.c`.

0008-0010 and 0012-0013 applied to 11.1.3 with line offsets only (LEMU is on QEMU master).
`sun4m-apc-test` fails without 0011 (the region is 1 byte, register 2 doesn't read back) and passes
5/5 with it. `sun4m-solaris-idle-test` passes 5/5 with 0014-0016 (its `idle` case is the `off` case
inverted: without the halt the loop keeps counting).

When pve-qemu moves to a new QEMU: check each patch still applies, drop any that upstream has
taken, and run `sun4m-escc-test`, `sun4m-apc-test` and `sun4m-solaris-idle-test` (sparc) and
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

Without 0002 the built `QEMU,cgthree.bin` is byte-identical to the one QEMU 11.1.3 ships; with it,
to LEMU's.

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
(sun4m, one CPU):

| Guest | Idles | How |
| --- | --- | --- |
| NetBSD 11.1, Linux | yes | their APC driver (`apc0 at sbus0 slot 4 offset 0xa000000`) writes register 0 of the power management node in the idle loop and QEMU halts the CPU until the next interrupt, with or without these patches. Linux not tested here |
| NetBSD 9.3 | no | its GENERIC kernel has no APC driver (`power-management ... not configured`); neither have the install kernels of 9.3 and 11.1 |
| Solaris 2.5.1-9 | yes | 0014-0015: QEMU recognises the call of `idle_cpu` in the kernel's idle loop and halts the CPU there (`solaris-idle`, on by default; `-M SS-20,solaris-idle=off` turns it off; off with `-smp` > 1). Any CPU module, SS-5 and SS-10/SS-20. `-trace sparc_solaris_idle_match` shows the match |
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
clock. A halt there would need QEMU to wake the CPU on writes to the dispatch queues (or Solaris to poke
idle CPUs); that's why `solaris-idle` is off with `-smp` > 1 (also moot while 2.6 SMP hangs, "SS-10 and
SS-20").

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
| Solaris 7 (3/99) CD | language question, SS-5 and SS-20 |
| Solaris 8 (1/01) Installation CD | Web Start's first question (`Do you want to format /dev/dsk/c0t3d0?`), SS-5 and SS-20; it needs a Sun-labelled disk, a blank one ends in `No Hard disks found on the system.` |
| Solaris 9 DVD | language menu, SS-5 and SS-20 |
| NetBSD 11.1, SS-5 disk | boots on SS-20; GENERIC attaches one CPU (`cpu at mainbus0 not configured`, `hw.ncpu = 1`) and `apc0`, idles at 2.4% of a core with `-smp 2` |
| NetBSD 11.1 GENERIC.MP (from the ISO) | `-smp 2`: `cpu0: booting secondary processors: cpu1`, `hw.ncpu = 2`; five 16-256 MB writes with `sync` pass; idle ~4% of a core |

**SMP.** Solaris 2.6 on SS-20 with OpenBIOS brings up every CPU (`psrinfo`: 2 or 4 on-line,
OpenBIOS `CPUs: 4 x TI,TMS390Z55`), but it isn't stable:

| CPUs | RAM | What happened |
| --- | --- | --- |
| 2 | 256 | 256 MB `dd` + `sync`: hung in 4 of 4 tries (writes up to 128 MB passed); bench runs (64 MB): 3 of 3 passed |
| 2 | 512 | hung once during boot (`volume management starting.`); bench runs: 3 of 3 passed |
| 2 | 256 | `SOAK=300` (2 shells looping the job and a 10 MB `dd`): hung within the first minute; the same with one CPU ran the 300 s |
| 2 | 256 | `TI-SuperSparc-50` and `-60`: 256 MB write hung too; `-40` stops QEMU at boot |
| 2 | 256 | `-accel tcg,thread=single`: hung at boot after `Configuring the /devices directory`, same place as below |
| 4 | 256 | bench: 1 of 3 passed; one hung in `prtconf` right after login, one in the 64 MB write |
| 4 | 512 | bench runs (64 MB): 3 of 3 passed |

Every hang looks the same: no answer on the console, all vCPUs at 100%, CPU 0 in `xc_sync_cache+0x1a0`
(waiting for the other CPU to acknowledge a cross-call), the other CPU looping in `splx`/`splr`. Not a
multi-threaded TCG race (single-threaded TCG hangs the same way), not the CPU variant; NetBSD's MP
kernel survives the same writes. SMP isn't usable for Solaris 2.6 here.

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
  hangs (above).

**Why SS-5 is slower.** Times in the guest (`/usr/bin/time`, seconds), one CPU, OpenBIOS:

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
Solaris 2.6 user-space work, not one kind of operation.

**Recommended** (from the data above):

- **SS-20 (or SS-10), OpenBIOS, one CPU, 256-512 MB** for Solaris 2.6: ~9x faster user-space than
  SS-5, the same disk and boot times, and with 0014-0015 an idle guest uses ~3% of a host core. Needs its own install on that machine type (the SS-5 disks don't
  boot there). 2.5.1, 7, 8 and 9 installers also start there.
- SS-5 + OpenBIOS (or `ss5.bin`), 256 MB stays for what needs SS-5: existing SS-5 disks, Solaris 2.4
  (Sun PROM only), SunOS 4.1.4. `pmc` is no longer needed to idle there.
- Don't offer more than one CPU for Solaris 2.6: it hangs, and one job runs slower. NetBSD's MP kernel
  works with 2 CPUs (not benchmarked).
- RAM: 256 MB on SS-5 (QEMU's limit), at most 512 MB on SS-10/SS-20; 512 shows no speed benefit over
  256 in this benchmark.
- The Sun SS-10/SS-20 PROMs only with the SS-20 machine and `-cpu TI-SuperSparc-50` (or -40/-60);
  qemu-server passes -50 for `ss20_v2.25_rom` on SS-20. They bring no speed benefit over OpenBIOS. The
  SS-10 PROM doesn't run on the SS-10 machine.
- Not SS-600MP (Solaris 2.6 refuses it), and none of the other PROMs tried except `ss5-170.bin` and
  `ross225r.bin` (which runs as a SuperSPARC SS-20).

## Supported profiles

The contract for sparc32 (`arch: sparc`, always TCG, one CPU), from the measurements under "SS-10
and SS-20". qemu-server holds it as `$SPARC32_PROFILES` in `PVE::QemuServer::Machine` and validates
and builds the command from it; pve-manager mirrors it in `PVE.qemu.Architecture.sparc32Profiles`.

| Machine | Firmware (`bios`) | `-cpu` | RAM | CPUs |
| --- | --- | --- | --- | --- |
| SS-5 (default) | `openbios-sparc32` (default), `ss5.bin` | none (machine default) | 256 MB | 1 |
| SS-10 | `openbios-sparc32` | none | 512 MB | 1 |
| SS-20 | `openbios-sparc32` | none | 512 MB | 1 |
| SS-20 | `ss20_v2.25_rom` | `TI-SuperSparc-50` | 512 MB | 1 |

- Display: `cg3` (default), `tcx`, `none`, `serial0`/`serial1` (ttya/ttyb). No resolution option
  (`-g`): qemu-server passes none, so cg3 runs at QEMU's 1024x768.
- Disk on the built-in ESP at SCSI target 3, CD-ROM at target 6 (`physical_block_size=512`), the
  built-in lance with `net0`'s MAC, at most one NIC.
- `ss10_v2.25_rom` stays readable in existing configs but matches no profile (it doesn't run on
  QEMU's SS-10).
- sparc64 (`sun4u`, `openbios-sparc64`) has no profiles: what worked before still does, nothing more
  is checked.

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
  sockets × cores = 1, no `cpu`, the display, no guest agent, serial0/serial1 only and one lance NIC.
  It runs on create (before the config exists), on every config update against the config as it
  will be (pending changes and deletions included), and in `config_to_command` (start, `qm showcmd`,
  vzdump). Reading a config (`GET .../config`, the VM list, `qm config`) never checks it: a config
  outside the profiles stays readable and is refused only when it is started or changed, with a
  message naming the allowed values; a change that makes it valid is accepted.
- **Firmware:** `bios` accepts `openbios-sparc32`, `openbios-sparc64`, `ss5.bin`,
  `ss10_v2.25_rom`, `ss20_v2.25_rom`, passed as `-bios`.
- **CPU:** `-cpu` only from the profile (`TI-SuperSparc-50` for SS-20 + `ss20_v2.25_rom`); the generic
  `cpu` option is refused on sparc32 and never emitted on sparc or sparc64.
- **Display:** `vga` accepts `tcx` and `cg3`, passed as `-vga <type>`; sparc32 defaults to `cg3`
  (QEMU's sun4m has no `std`).
- **Disks:** sparc32 drives are `scsi-hd`/`scsi-cd` on the built-in ESP
  (`channel=0,scsi-id=<unit>,lun=0`); sparc64 puts the SCSI controller on `pciB`. CD-ROMs get
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
  vmgenid; sparc32 also gets no virtio-balloon.
- **Snapshots with RAM:** a sparc VM usually runs without `-cpu`, so `runningcpu` is only recorded
  when there is one.

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
- **Refused:** CPU changes on sparc32 (`sparc: only one CPU is supported ...`, the profile check);
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

- `qemu/Architecture.js`: SPARC (32-bit) and SPARC (64-bit) in the create wizard's vCPU
  Architecture (an advanced option); per architecture the OS types (Linux, Solaris, Other),
  machines, firmware, displays, SCSI controller and buses; the mirrored sparc32 profiles; the
  firmware display names that both the selectors and the renderers use.
- sparc32 in the wizard and the Hardware editors: machine SS-5 (default), SS-10 or SS-20 (no
  versions), only the firmware the machine runs, memory preset to and capped at the machine's
  maximum, sockets, cores and CPU type disabled (nothing is submitted), displays cg3 (default), tcx,
  serial0, serial1 and none, the lance NIC only, the first disk on SCSI target 3 and the CD-ROM on
  target 6.
- The architecture of an existing VM is read-only (no editor, no Add → Architecture).
- Selectors: firmware (OpenBIOS, SPARCstation 5/20 PROM), display (TCX, CG3), network (Lance, Sun
  Happy Meal).

## Testing

- `e2e/sparc` (#197): installs and boots Solaris 2.5.1 and 2.6 unattended against the shipped
  QEMU and records every step. Its README lists what it found about devices and boot paths.
- qtests: `sun4m-escc-test` (0005), `sun4m-apc-test` (0011), `sun4m-solaris-idle-test` (0016) and
  `am53c974-test` with 0007; they
  build in a QEMU tree with the series applied.
- cg3 sizes: the lab's `display` matrix (`scenarios/cg3-display.py`).
- cg3 and TCX: the TCX/cg3 banner and no-driver cases in `display`, the desktop cases in `display-x`
  (`scenarios/fb-display.py`, disks prepared by `solaris-tcx-packages.py`); results under "cg3 and TCX".
- Idle: the lab's `idle` matrix (`scenarios/idle.py`).
- Machines, firmware and speed: the lab's `machines` and `bench` matrices (`scenarios/bench.py`);
  results under "SS-10 and SS-20".
- Profiles: qemu-server's `src/test/cfg2cmd/sparc32-*.conf` (the command per profile and the refused
  combinations) and `e2e/tests/sparc-profiles.spec.ts` (API and wizard per profile, refusals,
  backup/restore, and that the lab's machine arguments match `qm showcmd`).
- Running VMs: `e2e/tests/running-vm.spec.ts` (CD medium, net0 changes, pending changes and other
  operations on a started VM per profile, sun4u and an x86 control) and qemu-server's
  `src/test/hotplug/sparc*.conf` and `src/test/run_machine_version_tests.pl`.
- What PVE starts: the lab's attach mode and `pve_matrix.py` (`e2e/sparc/README.md`, "Attach to a PVE
  VM"; the `pve` choice of the `sparc lab` workflow) create VMs through the API in the e2e container
  and drive the QEMU that PVE started: the Solaris 2.6 install and first boot on the default SS-5
  profile, NetBSD 11.1 sparc64 to its shell, Alpine aarch64 and x86_64 to a login.

## Known gaps

- **CD as a disk:** Solaris 2.4 and 2.5.1 only boot their installer from a CD that answers as a
  disk (`scsi-hd`). A CD-ROM drive (`media=cdrom`) is always a `scsi-cd`, and the API refuses an ISO
  volume without `media=cdrom`. Workaround: copy the ISO into a raw disk image of the VM and attach
  it as `scsi6: <volume>,ro=1,backup=0` (a read-only disk on target 6). A first-class option would be
  a sparc32-only drive flag; not added.
- **Resolution:** qemu-server has no option for `-g`; cg3 runs at 1024x768 (what the Sun PROMs and
  Solaris' X server need).
- **Live migration:** fails for a VM without `-cpu` (see "Backup and restore").
- **SS-20 PROM with a framebuffer:** Solaris 2.6 panics at boot with the console on cg3 or TCX
  under `ss20_v2.25_rom` ("cg3 and TCX"); with a serial console it boots.
- **TCX depth:** qemu-server passes no `-g`, so TCX is 8-bit; 24-bit only works with OpenBIOS.
- **OpenBIOS `cdrom` alias:** it doesn't find a CD that answers as a disk; boot that by device
  path (`sd@6,0:d`).
