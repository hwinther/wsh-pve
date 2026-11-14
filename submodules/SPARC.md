# sparc patches

Everything wsh-pve changes to run sparc (32-bit, `arch: sparc`) and sparc64 guests, by
component. The user guide is `docs/src/content/docs/guides/sparc.md`; this file is for whoever
maintains the patches.

| Component | Where | What |
| --- | --- | --- |
| QEMU | `submodules/pve-qemu.patch` | sparc targets, firmware, machine lists, QEMU fixes as quilt patches |
| QEMU 7.2 extra | `submodules/pve-qemu-7.2-sparc.patch` | an extra `qemu-system-sparc-7.2` build |
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
- `debian/rules` also copies the Sun PROMs from `submodules/sparc` to `/usr/share/kvm` and the
  `qemu-system-sparc-7.2`/`qemu-system-sparc64-7.2` binaries when they were built. Both are
  optional and are left out silently when missing (by design: the build never fails on them).

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

The ESCC patches are by Antoni Sawicki, from [LEMU](https://github.com/tenox7/lemu), a QEMU fork
for vintage machines (GPLv2, like QEMU). LEMU states that its code won't be sent to QEMU, so we
carry it ourselves. Each patch keeps its author and has an `Origin:` line.

Tested: `sun4m-escc-test` fails without 0002-0006 and passes 4/4 with them on 11.1.3;
`test_select_after_bus_reset_ok` fails from `6f8ce26bb0` through 11.1.3 and passes with 0001.
The full series (Proxmox's patches + ours) applies on QEMU 11.1.3; no Proxmox patch touches
`esp.c` or `escc.c`.

When pve-qemu moves to a new QEMU: check each patch still applies, drop any that upstream has
taken, and run `sun4m-escc-test` (sparc) and `am53c974-test` (i386).

### QEMU 7.2 extra binary

`pve-qemu-7.2-sparc.patch` builds pve-qemu 7.2 with the sparc targets (and gtk, sdl and
PulseAudio). Its `qemu-system-sparc`/`qemu-system-sparc64` are packaged as
`qemu-system-sparc-7.2`/`qemu-system-sparc64-7.2`, for comparing against the old version. qemu-server
never selects them; run them by hand.

## qemu-server

`submodules/qemu-server.patch`, everything gated on `arch` matching `sparc`:

- **Binaries:** `sparc` → `/usr/bin/qemu-system-sparc`, `sparc64` → `/usr/bin/qemu-system-sparc64`.
- **Machines:** `SS-5` (sparc) and `sun4u` (sparc64) by default; the machine regex accepts
  `SS-\d{1,2}` and `sun4[a-z]`, type `sun`.
- **Firmware:** `bios` accepts `openbios-sparc32`, `openbios-sparc64`, `ss5.bin`,
  `ss10_v2.25_rom`, `ss20_v2.25_rom`.
- **Display:** `vga` accepts `tcx` and `cg3`, passed as `-vga <type>`.
- **Disks:** sparc32 drives are `scsi-hd`/`scsi-cd` on the built-in ESP
  (`channel=0,scsi-id=<unit>,lun=0`); sparc64 puts the SCSI controller on `pciB`. CD-ROMs get
  `physical_block_size=512` (Sun drives used 512-byte blocks).
- **Network:** sparc32 uses the built-in lance (`-net nic,model=lance`, not hot-pluggable);
  sparc64 puts `sunhme` on `pciB`.
- **Left out on sparc:** `-smbios`, the CPU type (the machine's default), PCI passthrough
  (ignored with a message) and USB.

## pve-manager

`submodules/pve-manager.patch`:

- `qemu/Architecture.js` and `QemuArchEdit.js`: the Architecture panel with `sparc` and
  `sparc64`. Each offers Linux/Other/Solaris OS types, the SS-5/sun4u machine, SCSI only, and
  the matching firmware.
- Selectors: machine (`SS-5 (sun/sparc)`, `sun4u (sun/sparc64)`), firmware (OpenBIOS, SS5/SS10/SS20
  PROM), display (TCX, CG3), network (Lance, Sun Happy Meal).
- The CD, display, audio and hardware views take the architecture into account.

## Testing

- `e2e/sparc` (#197): installs and boots Solaris 2.5.1 and 2.6 unattended against the shipped
  QEMU and records every step. Its README lists what it found about devices and boot paths.
- qtests: `sun4m-escc-test` (0005) and `am53c974-test` with 0007; they build in a QEMU tree
  with the series applied.

## Known gaps

- **CD as a disk:** Solaris 2.4 and 2.5.1 only boot their installer from a CD that answers as a
  disk (`scsi-hd`). qemu-server always makes a sparc CD-ROM a `scsi-cd`.
- **RAM:** QEMU's SS-5 takes 256 MB at most (`Too much memory for this machine`); qemu-server
  and the UI don't limit it, and the guide says ~512 MB.
- **lance MAC:** fixed at `08:00:20:b5:09:67` instead of coming from the VM's `net0`.
- **Architecture changes:** changing the architecture of an existing VM should be refused.
- **OpenBIOS boot aliases:** `disk` doesn't reach SCSI target 3 and `cdrom` doesn't find a CD
  that answers as a disk; boot those by device path.

## Candidates from LEMU, not carried

- **cg3 at any size** (`hw/display/cg3.c` and a new `QEMU,cgthree.bin`): stock QEMU's cg3 works
  at 1024x768 only, and 1152x900 crashes OpenBIOS. LEMU makes 640x480 to 3200x1800 work, which
  would allow a resolution setting.
- **SunOS 4 idle** (`target/sparc/sunos_idle.c`): halts the CPU in SunOS 4.1.4's idle loop
  (2-4% host CPU instead of 100%). Only for that kernel; Solaris 2.x doesn't benefit.
