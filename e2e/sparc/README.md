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
| `cg3-display.py` | the cg3 at the size `RES` gives, console on the framebuffer: the PROM banner and, with `DISK`, Solaris to `console login:` (first-boot questions answered by OCR), each screenshot checked for that size and for not being blank | banner: seconds; disk: ~4 min |
| `idle.py` | boots an installed disk, logs in, then measures QEMU's host CPU use over `SECONDS` (`CPU_BELOW`/`CPU_ABOVE` set the limits), checks that the guest clock kept time and times a CPU-bound command (`BUSY`); the numbers go to `result.json` (`metrics`) | ~3-4 min |
| `bench.py` | boots an installed Solaris disk, checks the CPUs `psrinfo` lists (`CPUS`, default `SMP`), then times boot to login, a `nawk` loop, `PARALLEL` copies of it at once (default `SMP`), a 64 MB write + `sync` and a raw read, with QEMU's host CPU use idle and during the parallel run; `SOAK` adds a load phase. `init 5` at the end | SS-5: ~5 min, SS-20: ~3 min |

Machine options are variables (`--var KEY=VALUE`), listed at the top of `scenarios/_sparc32.py`:
`BIOS` (openbios-sparc32, ss5.bin, …), `MACHINE`, `MEM`, `SMP` (`-smp` only when > 1), `CPU` (`-cpu`,
e.g. `TI-SuperSparc-50`, which the Sun SS-20 PROM needs; none by default), `TCG_THREAD` (`-accel
tcg,thread=single|multi`), `VGA` (cg3, tcx, none), `RES` (`-g`, e.g. `1152x900`), `CONSOLE`,
`CDROM_AS` (`hd` for Solaris 2.4/2.5, which only boot the installer from a CD that answers as a disk),
`TEMPLATE`/`DISK`, `REFRESH`, `TRACE` (QEMU trace events into `trace.log`, e.g. `cg3_write` or `esp_*`).
Machine options go with the type: `MACHINE=SS-5,sunos-idle=off`.

### The lab and the qemu-server profiles

The variables map onto the sparc32 profiles qemu-server accepts (`submodules/SPARC.md`, "Supported
profiles"): `MACHINE` is `machine`, `BIOS` is `bios`, `MEM` is `memory`, `VGA` is `vga`, and `CPU` is
what qemu-server passes for the profile (`TI-SuperSparc-50` for SS-20 with `ss20_v2.25_rom`, the
`SS20PROM` set in `matrix.py`; none otherwise). The defaults are the default profile (SS-5, OpenBIOS,
256 MB, cg3). Disk on target 3, CD-ROM on target 6 and the lance NIC are the same in both.

| Lab variables | Profile |
| ------------- | ------- |
| defaults | SS-5, OpenBIOS |
| `BIOS=ss5.bin` | SS-5, `ss5.bin` |
| `MACHINE=SS-10` (`MEM` up to 512) | SS-10, OpenBIOS |
| `MACHINE=SS-20` (`MEM` up to 512) | SS-20, OpenBIOS |
| `SS20PROM` (`MACHINE=SS-20 BIOS=ss20_v2.25_rom CPU=TI-SuperSparc-50`) | SS-20, `ss20_v2.25_rom` |

The lab also runs what the profiles refuse (`SMP` > 1, `MEM` above the limits, other PROMs, `RES`),
to measure it. `e2e/tests/sparc-profiles.spec.ts` ("the lab runs the same machines") reads
`DEFAULTS` from `scenarios/_sparc32.py` and `SS20PROM` from `matrix.py` and checks that `qm showcmd`
for those VMs has the same machine, firmware, CPU, memory, display and device layout, so the two
can't drift apart unnoticed.

`Machine.cpu_use(seconds, below, above)` measures QEMU's CPU time (utime + stime of all its threads, from
`/proc/<pid>/stat`) over an interval, in percent of one core. It means something only while the host
has nothing else to do.

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
| `machines` | SS-10/SS-20: the 2.6 CD to the installer with OpenBIOS (256 and 512 MB, SS-20 also `SMP=2` and `SMP=4`) and with the Sun SS-20 PROM (`CPU=TI-SuperSparc-50`, 512 MB), the 2.5.1 CD (`CDROM_AS=hd`) with both on SS-20, and the SS-10/SS-20 installed disks to login (OpenBIOS, SS-20 also 512 MB and the Sun PROM) | ~20 min |
| `display` | `cg3-display.py`: `BIOS=ss5.bin` banner at 1024x768, and the 2.6 disk with OpenBIOS at 1024x768, 1152x900, 1280x1024, 1600x1200 and 1920x1080 | ~19 min |
| `idle` | `idle.py` on SS-5 with OpenBIOS: Solaris 2.6 with the `pmc` driver (below 10% of a core) and without it (above 80%), SunOS 4.1.4 with `sunos-idle` (below 10%, and `sparc_sunos_idle_match` traced) and with `sunos-idle=off` (above 80%), NetBSD 11.1 (`apc0` attached, below 10%) | ~14 min |
| `bench` | `bench.py` with Solaris 2.6 on SS-5 (OpenBIOS) and SS-20 (OpenBIOS and the Sun PROM), one CPU each; numbers only, on an otherwise idle host | ~13 min |

`display` needs a `pve-qemu-kvm` with the cg3 patches (`submodules/SPARC.md`); with an older one
every size but 1024x768 fails at QEMU's `Unsupported resolution` (1152x900: OpenBIOS faults).
`idle` needs one with the idle patches (0011-0013): with an older one the `pmc` disk panics at boot
and `sunos-idle=off` is an unknown machine option.

The disks are `sol26-enduser-installed.raw` and `sol251-enduser-installed.raw` (End User installs by
`solaris-install-serial.py` on SS-5), `sol26-enduser-ss10-installed.raw`, `sol26-enduser-ss20-installed.raw`
(the same on SS-10 and SS-20 with OpenBIOS, `MACHINE=SS-10`/`SS-20`, ~8.5 min each) and
`sol26-enduser-ss20prom-installed.raw` (SS-20 with `BIOS=ss20_v2.25_rom CPU=TI-SuperSparc-50`),
`sol26-enduser-pmc-installed.raw` (the 2.6 one with the `pmc`
driver), `netbsd111-installed.raw` (see "Idle") and `sunos414-installed.raw` (see "SunOS 4.1.4"), the CDs
`solaris_2.6_598_sparc.iso` and `solaris_2.5.1_1197.iso`.

`.github/workflows/sparc-lab.yml` runs a matrix (`smoke` unless chosen otherwise) on demand and every
week, never for pull requests or pushes: it needs the media, on a self-hosted runner labelled
`sparc-lab`. It builds the lab image without cache (so it has the newest published package), mounts
the three directories (inputs, defaulting to the paths above), puts the table in the job summary,
uploads everything but the disks as an artifact and removes its run directory.

## Idle

Which guests stop spinning the host CPU when idle, and the results, are in `submodules/SPARC.md`
("Idle"). `sol26-enduser-pmc-installed.raw` is `sol26-enduser-installed.raw` with Solaris 2.6's `pmc`
driver installed from the 2.6 CD by the steps there. `modinfo | grep pmc` then lists `pmc (Power
Management prototype v1.1)` and `prtconf -D` shows `power-management, instance #0 (driver name: pmc)`.

`netbsd111-installed.raw` is NetBSD 11.1 from `NetBSD-11.1-sparc.iso` (`ISO=...`, `VGA=none`, by hand
through `serve`, ~10 min): microroot `1` (cdrom), Return twice, terminal type Return, `I`; sysinst: `a`
(English), `a` (install), `b` (yes), `a` (sd0), `b` (default partition sizes), `x`, `b`, `c` (Minimal
installation), `a` (CD-ROM); root password empty, entropy `x` (not now), `x` (finished configuring),
Return, `x` (exit), then `sync; halt -p`. Its GENERIC kernel attaches `apc0`; NetBSD 9.3's has no APC
driver and spins.

## SunOS 4.1.4

`sunos414-installed.raw` was installed by hand through `serve` (no scenario: the curses menus of
`suninstall` redraw lazily, a key's echo arrives with the next key). The machine is the lab's SS-5 with
OpenBIOS and the CD at target 6 with 512-byte blocks:

1. **The CD image.** `sunos_4.1.4_install.iso` is a raw BIN (2352-byte sectors, 16-byte header each), not an
   ISO: the Sun label sits at byte 16. Cut it down to the 2048 data bytes of each sector:
   `python3 -c 'import sys; f=open(sys.argv[1],"rb"); o=open(sys.argv[2],"wb"); [o.write(s[16:2064]) for s in iter(lambda: f.read(2352), b"")]' sunos_4.1.4_install.iso sunos414-cd.iso`.
   Slice d of the CD is the sun4m boot (c is another architecture, b, e and f don't boot under OpenBIOS).
2. **The disk.** `sparc-SUN2.9G.raw.template.xz` decompressed, with partition g cut to 1000 cylinders
   (about 1 GB; its label has a 2.4 GB g, and SunOS 4 file systems stop at 2 GB). Done by rewriting the label
   (8 x (start cylinder, blocks) big-endian at byte 444, then the XOR checksum of the 255 words before it at
   byte 510); `format` in the miniroot shell does the same. a (95 MB, /) and b (190 MB, swap) stay.
3. **Install kernel: `MEM=64`.** The CD's kernel stops QEMU at once with 256 MB (`qemu: fatal: Trap 0x29
   (Data Access Error) while interrupts disabled`, published package too); with 64 or 32 MB it comes up.
   The installed kernel boots with 256 MB.
4. `serve ... --var ISO=sunos414-cd.iso --var DISK=disk.raw --var VGA=none --var BOOT=c --var MEM=64`; at
   `0 >`: `boot /iommu/sbus/espdma/esp/sd@6,0:d`. Menu: `1` (install SunOS mini-root), `2` (don't format, the
   label is there). It copies the miniroot to sd0b and offers `1` (reboot); OpenBIOS ignores the boot
   string, so at `0 >`: `boot /iommu/sbus/espdma/esp/sd@3,0:b -sw`.
5. At `#`: `TERM=vt100; export TERM; suninstall`, `1` (Quick installation), `y` (preserve the data
   partitions: it installs into a and g and keeps the label), then the standard installation: Space moves,
   `x` selects. **Programmer**; `Full_install` stops at the Versatec set (`tar: directory checksum error` in
   `/etc/install/suninstall.log`, then loops on "Please mount ... volume 1"). `y` to start: a few minutes;
   `y` to reboot.
6. First boot (OpenBIOS boots the disk by itself): `2` (manual setup), Return, hostname `sunos414`, time
   zone Greenwich Mean Time / GMT (`x`), `1` (accept the time), `2` (no network), `y`, empty root password,
   `n` (no user account). Then `sunos414 login:`; root has csh and no password. `sync; halt` powers off.

The install leaves `/` 5% and `/usr` 7% used.

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
  installer on both, with 512 MB and with `SMP=2` (OpenBIOS: `CPUs: 2 x TI,TMS390Z55`). An install on
  SS-10 or SS-20 (`solaris-install-serial.py` unchanged, `MACHINE=SS-20`) boots there.
- **The Sun SS-10/SS-20 PROMs need `-cpu TI-SuperSparc-40/50/60`.** With QEMU's default
  (`TI-SuperSparc-II`) they stop at `Cpu #0 Data Access Error`; `boot` then ends QEMU. The SS-10 PROM
  also needs the SS-20 machine (on SS-10: `Probing Memory Bank #4 Data Access Error`). Results for
  every PROM tried are in `submodules/SPARC.md` ("SS-10 and SS-20").
- **Solaris 2.6 with more than one CPU hangs** (SS-20, OpenBIOS): writing 256 MB, sometimes while
  booting. CPU 0 waits in `xc_sync_cache` for a cross-call the other CPU never answers. The `machines`
  matrix therefore boots the installed disks with one CPU only.
- **Solaris 2.6 runs user code 6-9x slower on SS-5 than on SS-20**: its microSPARC window-trap
  handlers toggle the MMU no-fault bit, and QEMU flushes its whole TLB on each toggle. Kernel work and
  disk I/O are as fast; NetBSD runs the same `awk` loop equally fast on both (`submodules/SPARC.md`).
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
- **cg3 sizes** (with the cg3 patches): OpenBIOS and Solaris 2.6 boot with the console on the
  framebuffer at 1152x900 to 1920x1080, the console in the lines at the top that the cg3 ROM maps.
  Solaris 2.6's X server only starts at 1024x768; at the other sizes dtlogin gives up with
  `Mapping cg3: No such device or address` in `/var/dt/Xerrors`. The published package before the
  patches: 1152x900 hangs OpenBIOS with a blank screen ("Unhandled Exception 0x00000009" on ttya),
  other sizes stop QEMU with `Unsupported resolution`.
- The upstream image needs the framebuffer FCode ROMs (`QEMU,cgthree.bin`, `QEMU,tcx.bin`) next to
  OpenBIOS, or OpenBIOS can't create the cg3 node and Solaris sees no framebuffer.
