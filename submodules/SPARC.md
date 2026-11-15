# sparc patches

Everything wsh-pve changes to run sparc (32-bit, `arch: sparc`) and sparc64 guests, by
component. The user guide is `docs/src/content/docs/guides/sparc.md`; this file is for whoever
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
| `0008-hw-display-cg3-take-screens-of-any-size-up-to-8-MB` | The cg3 took 1024x768 and 1152x900 only (and 1152x900 crashed OpenBIOS). `-g` now takes 640x480 up to 8 MB of pixels with a width that 8 divides; the video RAM grows with it (1 MB at least) | [LEMU `527b9346`](https://github.com/tenox7/lemu/commit/527b934695b3e2568755606abec7446a356c961b) | not in QEMU |
| `0009-hw-sparc-sun4m-refuse-a-cg3-size-too-big-to-multiply` | The size check multiplied as `int`: `-g 65536x65536x8` wrapped to 0 and QEMU aborted allocating the video RAM | [LEMU `5836ffc3`](https://github.com/tenox7/lemu/commit/5836ffc34929e95d655006dfe38a1bbf756dc839) | not in QEMU |
| `0010-qemu-options-say-which-screen-sizes-the-cg3-takes` | `-vga cg3` and `-g` documentation | [LEMU `c2c6a828`](https://github.com/tenox7/lemu/commit/c2c6a828a382bca52e7f49fd6500d659d60c6534) | not in QEMU |
| `0011-hw-misc-slavio_misc-give-the-sun4m-APC-its-16-bytes-` | The power management (APC) region was 1 byte; the firmware's node says 16. Solaris 2.6's `pmc` driver writes offsets 2-0xc at attach and panicked (`kernel write fault at addr=0x6a000002`). Now 16 bytes: offset 0 halts the CPU as before, the others keep their value; vmstate section only when one is set. Adds qtest `sun4m-apc-test` | ours | not in QEMU |
| `0012-target-sparc-halt-the-CPU-in-the-SunOS-4.1.4-idle-lo` | SunOS 4.1.4 spins in its idle loop; the translator recognises the loop and halts the CPU there until the next interrupt | [LEMU `ff3dbc50`](https://github.com/tenox7/lemu/commit/ff3dbc50bcdcbcc346d8742df1e61c1eaf00b3b2) | not in QEMU |
| `0013-hw-sparc-sun4m-add-the-sunos-idle-option-on-by-defau` | `-M <sun4m>,sunos-idle=on\|off` for 0012, on by default, off with `-smp` > 1 | [LEMU `fed03cc7`](https://github.com/tenox7/lemu/commit/fed03cc7f5f7c5d6e5e0144bfc1dad36d4844180) | not in QEMU |

The ESCC, cg3 and SunOS idle patches are by Antoni Sawicki, from [LEMU](https://github.com/tenox7/lemu), a QEMU
fork for vintage machines (GPLv2, like QEMU). LEMU states that its code won't be sent to QEMU, so we
carry it ourselves. Each patch keeps its author and has an `Origin:` line.

Tested: `sun4m-escc-test` fails without 0002-0006 and passes 4/4 with them on 11.1.3;
`test_select_after_bus_reset_ok` fails from `6f8ce26bb0` through 11.1.3 and passes with 0001.
The full series (Proxmox's patches + ours) applies on QEMU 11.1.3; no Proxmox patch touches
`esp.c` or `escc.c`.

0008-0010 and 0012-0013 applied to 11.1.3 with line offsets only (LEMU is on QEMU master).
`sun4m-apc-test` fails without 0011 (the region is 1 byte, register 2 doesn't read back) and passes
5/5 with it.

When pve-qemu moves to a new QEMU: check each patch still applies, drop any that upstream has
taken, and run `sun4m-escc-test` and `sun4m-apc-test` (sparc) and `am53c974-test` (i386).

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
image. Like the other extras, the package falls back to QEMU's images when the build fails.

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

### Idle

QEMU keeps a host core at 100% for a guest that spins in its idle loop. Which sparc32 guests stop
(sun4m, one CPU):

| Guest | Idles | How |
| --- | --- | --- |
| NetBSD 11.1, Linux | yes | their APC driver (`apc0 at sbus0 slot 4 offset 0xa000000`) writes register 0 of the power management node in the idle loop and QEMU halts the CPU until the next interrupt, with or without these patches. Linux not tested here |
| NetBSD 9.3 | no | its GENERIC kernel has no APC driver (`power-management ... not configured`); neither have the install kernels of 9.3 and 11.1 |
| Solaris 2.6 | with `pmc` | the `pmc` driver (package `SUNWvygdr.m` on the 2.6 CD, not installed by default) lets the idle loop write APC register 0; needs 0011. Steps below |
| SunOS 4.1.4 | yes | 0012-0013: QEMU recognises the kernel's idle loop and halts the CPU there (`sunos-idle`, on by default; `-M SS-5,sunos-idle=off` turns it off; off with `-smp` > 1). `-trace sparc_sunos_idle_match` shows the match |
| Solaris 2.5.1 | no | no idle path found |

On SS-10 and SS-20 the real machines have no APC, but OpenBIOS creates the `power-management` node there
too (QEMU maps the device at `0xefa000000`, "XXX should not exist"); the Sun PROMs don't. NetBSD 11.1
attaches `apc0` on SS-20 with OpenBIOS and idles there (see "SS-10 and SS-20"); Solaris 2.6 with `pmc`
not tested there.

Solaris 2.6, in the guest, from the 2.6 CD:

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
qemu-server never passes `-cpu` on sparc, so as configured today the SS-10/SS-20 PROMs can't work.
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

- One CPU: SS-10 and SS-20 run the job 9x faster than SS-5; firmware and 256 vs 512 MB make no
  difference. Disk I/O is the same within 0.3 s; boot time (~57 s) is the same everywhere (mostly
  fixed waits, not CPU).
- More CPUs: one job gets slower (1.7x with 2 CPUs, ~3x with 4), several at once finish sooner than
  one after another on one CPU (2 jobs: 6.5 s vs 10.2 s; 4 jobs: 10.9 s vs 20.4 s), writes take
  longer, and each idle vCPU burns a host core (Solaris 2.6 has no idle on SS-10/SS-20). And it
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
  SS-5, the same disk and boot times. Needs its own install on that machine type (the SS-5 disks don't
  boot there). 2.5.1, 7, 8 and 9 installers also start there.
- SS-5 + OpenBIOS (or `ss5.bin`), 256 MB stays for what needs SS-5: existing SS-5 disks, Solaris 2.4
  (Sun PROM only), SunOS 4.1.4, the `pmc` idle setup.
- Don't offer more than one CPU for Solaris 2.6: it hangs, and one job runs slower. NetBSD's MP kernel
  works with 2 CPUs (not benchmarked).
- RAM: 256 MB on SS-5 (QEMU's limit), at most 512 MB on SS-10/SS-20; 512 shows no speed benefit over
  256 in this benchmark.
- The Sun SS-10/SS-20 PROMs only with the SS-20 machine and `-cpu TI-SuperSparc-50` (or -40/-60),
  which qemu-server would have to pass; they bring no speed benefit over OpenBIOS. The SS-10 PROM
  doesn't run on the SS-10 machine.
- Not SS-600MP (Solaris 2.6 refuses it), and none of the other PROMs tried except `ss5-170.bin` and
  `ross225r.bin` (which runs as a SuperSPARC SS-20).

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
- qtests: `sun4m-escc-test` (0005), `sun4m-apc-test` (0011) and `am53c974-test` with 0007; they
  build in a QEMU tree with the series applied.
- cg3 sizes: the lab's `display` matrix (`scenarios/cg3-display.py`).
- Idle: the lab's `idle` matrix (`scenarios/idle.py`).
- Machines, firmware and speed: the lab's `machines` and `bench` matrices (`scenarios/bench.py`);
  results under "SS-10 and SS-20".

## Known gaps

- **CD as a disk:** Solaris 2.4 and 2.5.1 only boot their installer from a CD that answers as a
  disk (`scsi-hd`). qemu-server always makes a sparc CD-ROM a `scsi-cd`.
- **RAM:** QEMU's SS-5 takes 256 MB at most (`Too much memory for this machine`); Solaris 2.6 on
  SS-10/SS-20 panics above 512 MB. qemu-server and the UI don't limit either.
- **CPU model:** the Sun SS-10/SS-20 PROMs need `-cpu TI-SuperSparc-40/50/60`, which qemu-server
  doesn't pass; Solaris 2.6 hangs with more than one CPU, which nothing prevents ("SS-10 and SS-20").
- **Machine choice:** the UI offers SS-5 only, though SS-10/SS-20 run Solaris 2.6 user space ~9x
  faster ("SS-10 and SS-20").
- **lance MAC:** fixed at `08:00:20:b5:09:67` instead of coming from the VM's `net0`.
- **Architecture changes:** changing the architecture of an existing VM should be refused.
- **OpenBIOS `cdrom` alias:** it doesn't find a CD that answers as a disk; boot that by device
  path (`sd@6,0:d`).
