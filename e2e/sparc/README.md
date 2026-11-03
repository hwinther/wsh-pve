# sparc lab

Installs and boots sparc guests under the QEMU we ship, unattended, and records every step: the serial
console as text and as an image, the framebuffer (cg3/tcx) as a screenshot. A run ends with an
`index.html` that shows the steps in order, so an install that went wrong on step 23 can be looked at
instead of repeated by hand.

- `lab.py` is the harness: one QEMU process with its serial port behind a VT100 emulator (pyte), its QMP
  monitor, OCR of the framebuffer (tesseract), and the step log.
- `scenarios/` are scripts against it. `_sparc32.py` is the SS-5 machine laid out the way qemu-server
  builds an `arch: sparc` VM (disk on SCSI target 3, CD-ROM on target 6 with 512-byte blocks, lance).
- `Dockerfile` builds the lab with `qemu-system-sparc` from the published `pve-qemu-kvm`, or from an
  upstream QEMU tag/commit for comparisons.

## Build

From the repository root:

```sh
docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .                         # the published build
docker build -f e2e/sparc/Dockerfile --build-arg QEMU_FROM=upstream \
  --build-arg QEMU_REF=v7.2.0 -t wsh-sparc-lab:7.2.0 .                            # upstream QEMU 7.2.0
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

Machine options are variables (`--var KEY=VALUE`), listed at the top of `scenarios/_sparc32.py`:
`BIOS` (openbios-sparc32, ss5.bin, …), `MACHINE`, `MEM`, `VGA` (cg3, tcx, none), `CONSOLE`,
`CDROM_AS` (`hd` for Solaris 2.4/2.5, which only boot the installer from a CD that answers as a disk),
`TEMPLATE`/`DISK`, `REFRESH`, `TRACE` (QEMU trace events into `trace.log`, e.g. `cg3_write` or `esp_*`).

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
- **OpenBIOS's `disk` alias doesn't reach SCSI target 3**: boot the installed disk with
  `boot /iommu@0,10000000/sbus@0,10001000/espdma@5,8400000/esp@5,8800000/sd@3,0:a`.
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
