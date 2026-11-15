# sparc lab

Installs and boots sparc guests under the QEMU we ship, unattended, and records every step: the serial
console as text and as an image, the framebuffer (cg3/tcx) as a screenshot. A run ends with an
`index.html` that shows the steps in order, so an install that went wrong on step 23 can be looked at
instead of repeated by hand.

- `lab.py` is the harness: one QEMU process with its serial port behind a VT100 emulator (pyte), its QMP
  monitor, OCR of the framebuffer (tesseract), and the step log.
- `scenarios/` are scripts against it. `_sparc32.py` is the machine (SS-5 by default) laid out the way
  qemu-server builds an `arch: sparc` VM (disk on SCSI target 3, CD-ROM on target 6 with 512-byte
  blocks, lance).
- `matrix.py` runs a fixed list of cases (scenario + variables) and summarises them; the
  `sparc lab` workflow runs it on a self-hosted runner.
- `Dockerfile` builds the lab with `qemu-system-sparc` from the published `pve-qemu-kvm`, the QEMU
  that PVE runs. `qemu-7.2.Dockerfile` adds an upstream QEMU (7.2.0 by default, built on Debian 12)
  on top of it, for comparing against the version sparc guests used to run on.

## Build

From the repository root:

```sh
docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .                             # the published build
docker build -f e2e/sparc/qemu-7.2.Dockerfile -t wsh-sparc-lab:7.2.0 e2e/sparc        # + upstream QEMU 7.2.0
```

## Run a scenario

The install media and disk templates are not in the image; mount a directory with them (here
`/srv/sparc`, holding the Solaris ISOs and `disks/`, the Sun-labelled disk templates).

```sh
docker run --rm -v /srv/sparc:/srv/sparc wsh-sparc-lab run scenarios/solaris-install-serial.py \
  --out /srv/sparc/runs/s26 \
  --var ISO=/srv/sparc/solaris_2.6_598_sparc.iso \
  --var TEMPLATE=/srv/sparc/disks/sparc-SUN2.9G.raw.template.xz
```

Exit code 0 = passed, 1 = a step timed out, 2 = QEMU died (a crash: `qemu.stderr` has the message), 3 =
anything else. The output directory has `index.html`, `steps.log`, `serial.raw` (everything the guest
wrote to ttya), `qemu.cmd`, `qemu.stderr`, `NNN-ttya.{txt,png}` / `NNN-fb.png` per step, `result.json`
and the guest disk.

| Scenario | What it does | Time (11.1, one core) |
| -------- | ------------ | --------------------- |
| `solaris-install-serial.py` | Solaris 2.x initial install (End User) on ttya, ends powered off | 2.6: ~9 min; 2.5.1 (`CDROM_AS=hd BIOS=ss5.bin`): ~60 min, mostly its Maintenance Update |
| `solaris-boot-disk.py` | boots an installed disk (OpenBIOS or `BIOS=ss5.bin`), answers first-boot questions, logs in, records `uname`/`df`/`ifconfig`, shuts down | ~2-3 min |
| `solaris-boot-cd.py` | boots an install CD to the installer's first question (language or terminal type) and stops | ~1 min |

Machine options are variables (`--var KEY=VALUE`), listed at the top of `scenarios/_sparc32.py`:
`BIOS` (openbios-sparc32, ss5.bin, …), `MACHINE`, `MEM`, `SMP` (`-smp` only when > 1), `CPU` (`-cpu`,
e.g. `TI-SuperSparc-II`; none by default), `VGA` (cg3, tcx, none), `CONSOLE`,
`CDROM_AS` (`hd` for Solaris 2.4/2.5, which only boot the installer from a CD that answers as a disk),
`TEMPLATE`/`DISK`, `REFRESH`, `TRACE` (QEMU trace events into `trace.log`, e.g. `cg3_write` or `esp_*`).

## Run a matrix

`matrix.py` runs the cases of a named list one after another, each in `<runs>/<case>/`, with a sparse
copy of the installed disk it boots (the images themselves are never booted, and the copies are
deleted when a case is done). It prints a Markdown table, writes it to `<runs>/summary.md` too, and
exits 1 if any case failed. The install CDs and the installed disks are separate directories, both
mounted read only:

```sh
docker run --rm -v /mnt/sparc/iso:/mnt/sparc/iso:ro -v /srv/sparc/disks:/srv/sparc/disks:ro \
  -v /mnt/sparc/runs:/mnt/sparc/runs --entrypoint python3 wsh-sparc-lab matrix.py smoke \
  --runs /mnt/sparc/runs/m1 --iso /mnt/sparc/iso --disks /srv/sparc/disks
```

| Matrix | Cases | Time |
| ------ | ----- | ---- |
| `smoke` | Solaris 2.6 disk with OpenBIOS, 2.5.1 disk with `BIOS=ss5.bin`, 2.6 CD to the installer with OpenBIOS; all SS-5 | ~6 min |
| `machines` | the 2.6 CD to the installer with OpenBIOS on SS-10 and SS-20, 256 and 512 MB, and SS-20 with `SMP=2` | ~6 min |

The disks are `sol26-enduser-installed.raw` and `sol251-enduser-installed.raw` (End User installs by
`solaris-install-serial.py` on SS-5), the CD `solaris_2.6_598_sparc.iso`.

`.github/workflows/sparc-lab.yml` runs a matrix (`smoke` unless chosen otherwise) on demand and every
week, never for pull requests or pushes: it needs the media, on a self-hosted runner labelled
`sparc-lab`. It builds the lab image without cache (so it has the newest published package), mounts
the three directories (inputs, defaulting to the paths above), puts the table in the job summary,
uploads everything but the disks as an artifact and removes its run directory.

## Drive a guest by hand

`serve` starts QEMU and takes commands from `ctl`; every `Machine` method is a command. This is how
new scenarios are written: step through the installer by hand, then copy the steps.

```sh
docker run -d --name lab -v /srv/sparc:/srv/sparc wsh-sparc-lab serve --out /srv/sparc/runs/x \
  --scenario scenarios/_sparc32.py --var ISO=/srv/sparc/solaris_2.6_598_sparc.iso --var VGA=none
ctl() { docker exec lab python3 lab.py ctl --out /srv/sparc/runs/x "$@"; }
ctl expect "Select a Language" 900
ctl screen_text                  # the serial console as text
ctl send '"0\r"'                 # JSON strings for control characters
ctl key f2                       # Esc-2; also enter, esc, ctrl-n, ctrl-p, ...
ctl snap "after the language"    # record a step (terminal + framebuffer screenshot)
ctl screendump now               # the framebuffer as /srv/sparc/runs/x/now.png
ctl hmp "info registers"         # any monitor command
```

## Things the lab found out

- **cg3 needs display refreshes to deliver its vertical-retrace interrupt.** QEMU raises the cg3
  interrupt only from a display update. With `-display none`, or VNC with no client connected (QEMU's
  VNC skips the update while nobody is connected), the guest gets no vsync at all. Solaris's cgthree
  driver loads the colour map on that interrupt, so the screen keeps OpenBIOS's grey ramp: the
  installer GUI is drawn, but looks almost black (pixel value = palette index). Measured on 2.6: with
  refreshes the colour map is loaded within 2 minutes of boot; without, not in 15 minutes, and one
  screendump (one interrupt) loads it. The lab refreshes every 0.5 s when a framebuffer is attached
  (`REFRESH`). Same on 7.2.0 and 11.1.
- **Terminal keys in the Solaris 2.6 text installer:** Esc-n for Fn; the arrow keys only beep, Ctrl-N
  and Ctrl-P move; Return marks `[X]`.
- **Stock OpenBIOS since QEMU 9.2 has no `disk` alias**: it probes every empty SCSI target as an
  `UNKNOWN` device, so the disk on target 3 is only `disk3` and the default boot stops with "No
  valid state has been set by load or init-program". The package carries a fix
  (`openbios/patches/`); the OpenBIOS in 7.2.0 didn't have the bug. `prom_boot()` handles both:
  it boots by device path at the `0 >` prompt, or lets OpenBIOS boot by itself.
- **One OpenBIOS device path for every machine.** The ESP sits at different unit addresses (SS-5:
  `/iommu@0,10000000/sbus@0,10001000/espdma@5,8400000/esp@5,8800000`; SS-10 and SS-20:
  `/iommu@f,e0000000/sbus@f,e0001000/espdma@f,400000/esp@f,800000`), but OpenBIOS also takes the path
  without them, `/iommu/sbus/espdma/esp/sd@6,0:d`, as its own aliases do. `prom_boot()` uses that for
  the case no alias covers: the packaged OpenBIOS's `cdrom` alias finds only a `scsi-cd`, so a CD as
  a disk (`CDROM_AS=hd`) is booted by path (the 2.6 kernel loads that way on SS-5 and SS-20, then
  panics with `vfs_mountroot: cannot mount root`: 2.6 wants a `scsi-cd`, the reverse of 2.4/2.5.1).
- **The SS-5 installed disks don't boot on SS-10/SS-20.** OpenBIOS loads the kernel and root mounts,
  but Solaris 2.6 then reports `le0: No such device or address` and `mount: /dev/dsk/c0t3d0s6 no
  such device`, and halts for want of /usr (also with `boot disk -r`). The 2.6 CD boots to the
  installer on both, with 512 MB and with `SMP=2` (OpenBIOS: `CPUs: 2 x TI,TMS390Z55`).
- **With a working `disk` alias the Solaris 2.6 installer pre-selects the boot disk**
  (`[X] c0t3d0 ... boot disk`); `disks()` only marks it when it isn't selected yet.
- **Solaris 2.4 and 2.5.1 need the CD as a disk** (`CDROM_AS=hd`): from a `scsi-cd` their kernel
  panics with `vfs_mountroot: cannot mount root`. qemu-server always makes a sparc CD-ROM a
  `scsi-cd`. A CD that answers as a disk is also listed as an install target (`c0t6d0`).
- **Solaris 2.4 doesn't boot under OpenBIOS** ("Unhandled Exception 0x00000009", any CD device);
  2.4 and 2.5.1 boot with `ss5.bin`. 2.5.1 installed and booted fine on 11.1.3+wsh1 (the ESP fix).
- **Sun PROM without a framebuffer** prints on ttya but reads the keyboard: `prom_boot()` types
  `ttya io` through send-key. `halt` ends at `ok` ("Program terminated") instead of powering off.
- **With a framebuffer, the 2.6 installer is the OpenWindows GUI** (needs the mouse); without one
  (`VGA=none`) it is the text installer on ttya.
- The upstream image needs the framebuffer FCode ROMs (`QEMU,cgthree.bin`, `QEMU,tcx.bin`) next to
  OpenBIOS, or OpenBIOS can't create the cg3 node and Solaris sees no framebuffer.
