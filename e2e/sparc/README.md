# sparc lab

Installs and boots sparc guests under the QEMU we ship, unattended, and records every step: the serial
console as text and as an image, the framebuffer (cg3/tcx) as a screenshot. A run ends with an
`index.html` that shows the steps in order, so an install that went wrong on step 23 can be looked at
instead of repeated by hand.

- `lab.py` is the harness: one QEMU process with its serial port behind a VT100 emulator (pyte), its QMP
  monitor, OCR of the framebuffer (tesseract), and the step log.
- `recording.py` records each run: the serial console as an asciinema cast, the framebuffer as a
  time-lapse video (see "Recordings").
- `scenarios/` are scripts against it. `_sparc32.py` is the machine (SS-5 by default) laid out the way
  qemu-server builds an `arch: sparc` VM (disk on SCSI target 3, CD-ROM on target 6 with 512-byte
  blocks, lance).
- `matrix.py` runs a fixed list of cases (scenario + variables) and summarises them; the
  `sparc lab` workflow runs it on a self-hosted runner.
- `Dockerfile` builds the lab with `qemu-system-sparc` from the published `pve-qemu-kvm`, the QEMU
  that PVE runs. `qemu-7.2.Dockerfile` adds an upstream QEMU (7.2.0 by default, built on Debian 12)
  on top of it, for comparing against the version sparc guests used to run on.
- Attach mode (`lab.py run --pve <vmid>`) drives a VM that Proxmox VE started instead of its own
  QEMU; `pve_matrix.py` creates VMs through the PVE API and runs scenarios against them, inside the
  e2e PVE node with the lab added (`pve.Dockerfile`). See "Attach to a PVE VM".
- `mcp_server.py` lets an AI assistant see and drive a running VM (a PVE VM or a `lab.py serve`
  QEMU) through MCP: screen, keys, serial console, waiting for a pattern. Optional, with its own
  dependencies (`mcp-requirements.txt`, `mcp.Dockerfile`). See "MCP server".
- `lab.py install <target>` (`install.py`, the catalogue in `targets.py`) installs a named target
  into a new PVE VM on a node: tested profile, media checked by name and sha256, the install driven
  by the scenarios in attach mode, a known root password and a marker file at the end. See "Install
  targets".

## Build

From the repository root:

```sh
docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .                             # the published build
docker build -f e2e/sparc/qemu-7.2.Dockerfile -t wsh-sparc-lab:7.2.0 e2e/sparc        # + upstream QEMU 7.2.0
```

The scenarios run the first `qemu-system-sparc` in `PATH`, and `/usr/local/bin` comes before the
package's `/usr/bin`. To try a QEMU built from a patched tree (e.g. `ninja qemu-system-sparc` in
the pve-qemu tree with the `debian/patches` series applied, built on Debian 13 so the image's
libraries fit), mount the binary there:
`docker run ... -v $PWD/build/qemu-system-sparc:/usr/local/bin/qemu-system-sparc:ro wsh-sparc-lab ...`.
The firmware still comes from the package (`LAB_FIRMWARE`). `qemu.cmd` doesn't show which binary
ran; the version line in `qemu-system-sparc --version` does (a local build has no
`pve-qemu-kvm_...` suffix). `pr-qemu.sh` and `pr-qemu.Dockerfile` do this for both sparc emulators
and the OpenBIOS images of a pull request (see "Before merge" under "NetBSD install targets").

## Run a scenario

The install media and disk templates are not in the image; mount the directories with them (on the
lab host `/mnt/os`, with the ISOs in `iso/` and the Sun-labelled disk templates in `disks/`, and
`/mnt/runs` for the output).

```sh
docker run --rm -v /mnt/os:/mnt/os -v /mnt/runs:/mnt/runs wsh-sparc-lab run scenarios/solaris-install-serial.py \
  --out /mnt/runs/s26 \
  --var ISO=/mnt/os/iso/solaris_2.6_598_sparc.iso \
  --var TEMPLATE=/mnt/os/disks/sparc-SUN2.9G.raw.template.xz
```

Exit code 0 = passed, 1 = a step timed out, 2 = QEMU died (a crash: `qemu.stderr` has the message), 3 =
anything else. The output directory has `index.html`, `steps.log`, `serial.raw` (everything the guest
wrote to ttya), `qemu.cmd`, `qemu.stderr`, `NNN-ttya.{txt,png}` / `NNN-fb.png` per step, `result.json`,
the recordings (`serial.cast`, `serial.fast.cast` and, with a framebuffer, `fb.webm` and `fb.vtt`; see
"Recordings") and the guest disk.

| Scenario | What it does | Time (11.1, one core) |
| -------- | ------------ | --------------------- |
| `solaris-install-serial.py` | Solaris 2.x initial install (End User) on ttya, ends powered off (2.3: at the PROM's `ok`, QEMU stopped) | 2.6: ~9 min; 2.5.1 (`CDROM_AS=hd BIOS=ss5.bin`): ~60 min, mostly its Maintenance Update; 2.4 (the same, through PVE): ~5 min; 2.5 (`CDROM_AS=hd`): ~5 min; 2.3 (`CDROM_AS=hd BIOS=ss5.bin`, Quick Install): ~6 min |
| `solaris-boot-disk.py` | boots an installed disk (OpenBIOS or `BIOS=ss5.bin`), answers first-boot questions, logs in, records `uname`/`df`/`ifconfig`, shuts down | ~2-3 min |
| `solaris-boot-cd.py` | boots an install CD to the installer's first question (language or terminal type) and stops; `IDLE` measures QEMU's host CPU use there | ~1 min |
| `cg3-display.py` | the cg3 at the size `RES` gives, console on the framebuffer: the PROM banner and, with `DISK`, Solaris to `console login:` (first-boot questions answered by OCR), each screenshot checked for that size and for not being blank | banner: seconds; disk: ~4 min |
| `fb-display.py` | cg3 or TCX (`VGA`, `RES=1024x768x24` for TCX's 24-bit mode), console on the framebuffer: the banner, Solaris to its login prompt and, with `X=1`, dtlogin, a root login into CDE, the depth (`DEPTH`), the keyboard (`INPUT`), idle CPU (`IDLE`), a drawing benchmark (`BENCH`, `ACCEL` counts TCX's blitter writes) and a soak (`SOAK`); `EXPECT=console` checks why X doesn't start instead. Its checks run on a ttya shell, so the disk needs `PREPARE=1` (or `solaris-tcx-packages.py TTYA_LOGIN=1` first) | X: ~4-5 min; `BENCH=3`: ~8 min |
| `fb-bell.py` | BEL on the cg3 console (keyboard and framebuffer): `7 emit` at the OpenBIOS prompt, then `GUEST` (`solaris`/`sunos4`: `boot disk:a -s`; `netbsd`: a root login) echoes a BEL in its shell, then three; the screenshots show whether the screen inverted and came back, OCR whether the shell answered. `EXPECT=hang` shows the hang of firmware without openbios 0026 (with `info registers`, `$tbr` and the firmware's tick count, `TICKS_SYM`); `LOOP=1` times the firmware's wait loop. Not in a matrix | ~2 min |
| `solaris-tcx-packages.py` | adds the TCX packages (SUNWtcx.m, SUNWtcxow, SUNWtcxu) to an installed Solaris from its CD and touches `/reconfigure`; `TTYA_LOGIN=1` also gives root a login on ttya while the console is on the framebuffer | ~3-4 min |
| `idle.py` | boots an installed disk, logs in, then measures QEMU's host CPU use over `SECONDS` (`CPU_BELOW`/`CPU_ABOVE` set the limits), checks that the guest clock kept time, times a CPU-bound command (`BUSY`), the echo of `true` and ten `sleep 1`; the numbers go to `result.json` (`metrics`) | ~3-4 min |
| `niagara-boot.py` | `-M niagara` (sun4v) with an OpenSPARC T1 firmware set the user supplies (`FW`, never in the image): OpenBoot's `ok`, with `DISK` the T1 archive's `disk.s10hw2` to a root shell and `init 5`, with `ISO` a Solaris 10 DVD to the text installer (`WALK` walks on through its screens); skipped (exit 0, `status` "skipped: ...") when the firmware isn't there. See `submodules/SPARC.md`, "sparc64: niagara (sun4v)" | `ok`: 1 s; disk: ~2 min; installer: ~4-5 min |
| `bench.py` | boots an installed Solaris disk, checks the CPUs `psrinfo` lists (`CPUS`, default `SMP`), then times boot to login, a `nawk` loop, `PARALLEL` copies of it at once (default `SMP`), a 64 MB write + `sync` and a raw read, with QEMU's host CPU use idle and during the parallel run; `SOAK` adds a load phase. `init 5` at the end | SS-5: ~5 min, SS-20: ~3 min |
| `bench-disk.py` | boots an installed Solaris disk with the bench disk (`DISK2`, "The bench disk") on target 4, mounts it, runs its `run.sh` (Dhrystone, Whetstone, Hanoi, nbench, lmbench subset with its network tests over `lo0`, the `nawk` loop, and lmbench over `le0` to the lab container: `NET=user` by default, `tap`, or `none`) and puts every `BENCH` value into `result.json`, with the host's load average; `init 5` at the end | ~10-12 min (7-8 of them `run.sh`) |
| `smp-soak.py` | boots an installed Solaris disk with `SMP` CPUs and the bench disk (`DISK2`), checks that `psrinfo` lists them on-line, times one and `SMP` copies of Dhrystone and the `nawk` loop (speed-up), then loads every CPU for `SOAK` seconds (Dhrystone, Hanoi, `nawk`, a `tar` of the bench disk through `compress` with its `cksum` checked, a write, a fork loop; `SMP` + 1 shells) while `mpstat 60` records the CPUs; fails on a hang, a CPU off-line, a checksum mismatch or a CPU below `BUSY` % busy | `SOAK` + ~5 min |
| `smp-idle.py` | boots an installed Solaris disk with `SMP` CPUs and the bench disk (`DISK2`), checks `psrinfo`, measures QEMU's host CPU use at the shell over `SECONDS` and the guest clock, the echo of `true` and ten `sleep 1`, then times work that has to wake an idle CPU: lmbench `lat_pipe` and `lat_proc fork`, a shell loop of 200 `expr`, a `dd \| cat \| cat` pipeline, bursts of short `nawk` jobs, one and `SMP` copies of Dhrystone and the `nawk` loop; `STRESS` adds `SMP` + 1 shell loops of short jobs, `sleep 1`, pipelines and `expr` for that many seconds with `psrinfo` every 60 s. For `solaris-smp-idle` (`submodules/SPARC.md`, "SMP"); numbers in `result.json` | ~7 min + `STRESS` |
| `bench-build.py` | boots the build disk with the hand-over CD and a blank labelled `DISK2`, runs `build.sh`, which compiles the benchmarks and makes `DISK2` the bench disk; compile times go to `result.json` | ~3 min (SS-20) |
| `redhat-install-sparc.py` | Red Hat Linux 6.2 from its CD with kickstart (the answer CD on target 5, written from `IP`/`NETMASK` unless `KS_ISO`), SILO's three screens answered; stops the VM when the install reboots. Needs a Sun-labelled disk (`TEMPLATE`) | ~2.5 min |
| `redhat-firstboot.py`, `redhat-boot-disk.py` | boot an installed Red Hat 6.2 disk to `login:` on ttyS0; the first sets root's password, the marker, host name, router, DNS and a user, the second records `COMMANDS` (and checks `CHECK`); both `poweroff` | ~1-2 min |
| `debian-install-sparc.py` | Debian 4.0 (etch) from the netinst CD with a preseed file (the answer CD on target 5, written from `IP`/`NETMASK`/`GATEWAY`/`DNS`/`DOMAIN`/`HOSTNAME` unless `ANSWERS_ISO`), loaded by `preseed/early_command` on SILO's boot line; the packages come from `archive.debian.org` (`NET=user` reaches it); stops the VM when the install reboots, fails at the first question box. Needs QEMU with `wsh/0038` (pve-qemu-kvm 11.1.3-2+wsh20 or later) | ~20 min |
| `debian-firstboot.py`, `debian-boot-disk.py` | boot an installed Debian 4.0 disk to `login:` on ttyS0; the first sets root's password, the marker and a user, the second records `COMMANDS` (and checks `CHECK`); both `poweroff` | ~1.5 min |
| `stop-a.py` | boots an installed disk (`GUEST`: solaris, sunos, netbsd; `none` = the firmware's own prompt) to its login prompt, sends Stop-A (`KEYS`, QMP `send-key`) or a break on ttya (`BREAK=1`, QMP `chardev-send-break`), checks that QEMU is still up and the guest is at the firmware prompt (`EXPECT=prom`: the CPU's PC in the firmware, `Type 'go' to resume` on the console), then `go` (or `boot`, or what `RESUME` says) and that the guest answers; `REPEAT` rounds | ~2-4 min |
| `sun-prom-nvram.py` | attach mode only (`--pve`): a Sun PROM VM with a blank `nvram0`; `setenv diag-switch? false` at the first `ok`, the disk's (first) boot to `login:`, then `qm stop`/`qm start` without input (the PROM must boot by itself) and `reboot -- -r`, both to `login:`; fails on `BAD TRAP`, `panic` or a QEMU `Trap`; times in `result.json` (`metrics`). `pve_matrix.py pve`, case `sol26-ss20prom-nvram` | ~5-5.5 min (SS-20 PROM) |

Machine options are variables (`--var KEY=VALUE`), listed at the top of `scenarios/_sparc32.py`:
`BIOS` (openbios-sparc32, ss5.bin, …), `MACHINE`, `MEM`, `SMP` (`-smp` only when > 1), `CPU` (`-cpu`,
e.g. `TI-SuperSparc-50`, which the Sun SS-20 PROM needs; none by default), `TCG_THREAD` (`-accel
tcg,thread=single|multi`), `VGA` (cg3, tcx, none), `RES` (`-g`, e.g. `1152x900`), `CONSOLE`,
`CDROM_AS` (`hd` for Solaris 2.4/2.5, which only boot the installer from a CD that answers as a disk),
`TEMPLATE`/`DISK`, `DISK2` (a second disk on target `DISK2_ID`, 4; read only unless `DISK2_RO=0`),
`REFRESH`, `TRACE` (QEMU trace events into `trace.log`, e.g. `cg3_write` or `esp_*`), `PROM_ENV`
(OpenBIOS variables as `-prom-env`, space separated, e.g. `auto-boot?=false` for Web Start).
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
| `MACHINE=SS-10` (`MEM` up to 2048) | SS-10, OpenBIOS |
| `MACHINE=SS-20` (`MEM` up to 2048) | SS-20, OpenBIOS |
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
exits 1 if any case failed. A `solaris-boot-cd.py` case that never reaches the installer's first
question boots once more, in `<runs>/<case>-retry1/` (`RETRY`: Solaris's init can lose the end of
the installer's `rcS`, `submodules/SPARC.md`, "The CD boot that stops after `Configuring
devices...`"). The install CDs and the installed disks are separate directories, both mounted read
only:

```sh
docker run --rm -v /mnt/os/iso:/mnt/os/iso:ro -v /mnt/os/disks:/mnt/os/disks:ro \
  -v /mnt/runs:/mnt/runs --entrypoint python3 wsh-sparc-lab matrix.py smoke \
  --runs /mnt/runs/m1 --iso /mnt/os/iso --disks /mnt/os/disks
```

| Matrix | Cases | Time |
| ------ | ----- | ---- |
| `smoke` | Solaris 2.6 disk with OpenBIOS, 2.5.1 disk with `BIOS=ss5.bin`, 2.6 CD to the installer with OpenBIOS; all SS-5 | ~6 min |
| `machines` | SS-10/SS-20: the 2.6 CD to the installer with OpenBIOS (256 and 512 MB, SS-20 also `SMP=2` and `SMP=4`) and with the Sun SS-20 PROM (`CPU=TI-SuperSparc-50`, 512 MB), the 2.5.1 CD (`CDROM_AS=hd`) with both on SS-20, and the SS-10/SS-20 installed disks to login (OpenBIOS, SS-20 also 512 and 2048 MB, SS-10 also 1024 MB, and the Sun PROM; more than 512 MB needs pve-qemu `wsh/0143` and openbios 0040) | ~25 min |
| `display` | `cg3-display.py`: `BIOS=ss5.bin` banner at 1024x768, and the 2.6 disk with OpenBIOS at 1024x768, 1152x900, 1280x1024, 1600x1200 and 1920x1080; `fb-display.py`: the TCX banner at depth 8 and 24 and the cg3 banner with every profile's machine and firmware, and the 2.6 disk without the TCX packages on TCX (no driver, no X) | ~35 min |
| `display-x` | `fb-display.py X=1 INPUT=1 IDLE=60`: the 2.6 disks (TCX packages added by `PREPARE`) into the CDE desktop on TCX 8, TCX 24 and cg3 with SS-5 (OpenBIOS, `ss5.bin`: not TCX 24), SS-10 and SS-20 (OpenBIOS) | ~100 min |
| `idle` | `idle.py`, OpenBIOS unless stated: Solaris 2.6 on SS-5 and SS-20 with `solaris-idle` (below 10% of a core, `sparc_solaris_idle_match` traced) and with `solaris-idle=off` (above 80%), 2.6 with the `pmc` driver on SS-5 with and without `solaris-idle` (below 10%), 2.5.1 on SS-5 with `ss5.bin` (below 10%, traced), SunOS 4.1.4 with `sunos-idle` (below 10%, and `sparc_sunos_idle_match` traced) and with `sunos-idle=off` (above 80%), NetBSD 11.1 (`apc0` attached, below 10%), Solaris 2.6 on SS-20 with 2 and 4 CPUs and `solaris-smp-idle` (below 20%, `sparc_solaris_idle_mp_match` traced) and with 2 CPUs and `solaris-smp-idle=off` (above 150%) | ~45 min |
| `bench` | `bench.py` with Solaris 2.6 on SS-5 (OpenBIOS) and SS-20 (OpenBIOS and the Sun PROM), one CPU each; numbers only, on an otherwise idle host | ~13 min |
| `sparc64` | `sun4u` (see "sparc64"): the NetBSD 11.1, NetBSD 9.3, OpenBSD 8.0 and Debian 12 CDs to their installers on the serial console, NetBSD 11.1 on the VGA console with the keyboard, the NetBSD 11.1 install, its disk booted twice with DHCP and an HTTP fetch over `sunhme`, with `virtio-net-pci` and `virtio-blk`, and idle: halted in its idle loop (below 10% of a core, `sparc64_idle_match` traced) and with `idle-halt=off` (above 80%; both need a package with pve-qemu `wsh/0042`-`0044`), and `sparc64-reboot.py`: the disk's `reboot` twice and `reboot -- netbsd` once, each back to the firmware's banner and `login:` in the same QEMU process (needs openbios-sparc64 patch 0030, pve-qemu-kvm 11.1.3-4+wsh3 or later; the firmware drops the boot string, so the second case only checks that such a reboot comes back); needs `--disks /mnt/os/disks` | ~38 min |
| `benchdisk` | `bench-disk.py` (the bench disk, `--bench`) with Solaris 2.6 on SS-5 (OpenBIOS, `ss5.bin`), SS-10 (OpenBIOS) and SS-20 (OpenBIOS, the Sun PROM), and 2.5.1 on SS-5 (`ss5.bin`); one CPU, 256 MB, QEMU user networking for the `le0` tests; numbers only, on an otherwise idle host | ~65 min |
| `smp` | `smp-soak.py` (the bench disk, `--bench`, `SOAK=600`) with Solaris 2.6 on SS-20 (OpenBIOS) with 2 and 4 CPUs, 2 CPUs and 2048 MB, and on SS-10 with 2 CPUs; needs a package with pve-qemu patch 0019 (before it 2.6 hung with more than one CPU), the 2048 MB case also `wsh/0143` and openbios 0040 | ~65 min |
| `stopa` | `stop-a.py`: Stop-A on Solaris 2.6 at the console login (SS-5, SS-10, SS-20) and at dtlogin, then `boot` instead of `go`, the chord the wrong way round; SunOS 4.1.4, NetBSD 11.1 (its debugger, `c`), the firmware's own prompt; a break on a ttya console for Solaris 2.6, SunOS 4.1.4, NetBSD 11.1 and the firmware's prompt (needs pve-qemu `wsh/0141`); all OpenBIOS. Needs OpenBIOS with `openbios/patches/0008` (before it Stop-A powered the VM off) | ~30 min |
| `solaris10` | (`pve_matrix.py solaris10` runs the same checks on a VM created through PVE) `sparc64-boot-cd.py GUEST=solaris10`: the Solaris 10 1/13 DVD on `sun4u` to the installer's first screen, the language and terminal questions answered on ttya, the IDE disk attached (`dad0`) without `Interrupt not seen after set_features`. **Needs the Sun DVD** `sol-10-u11-ga-sparc-dvd.iso` in `--iso` (Oracle's media, not in the repository) and a package with the patched `openbios-sparc64` and pve-qemu `wsh/0021`; with older packages it fails. `sol10-disk-sparc64` boots the installed disk `sol10-sun4u-installed.raw` (made by `solaris10-install-sparc64.py`, Sun software, lab host only) to `console login:` and checks `format`, the DHCP lease on `hme0` and a ping; the disk lives in `/mnt/os/disks`, so run this matrix with `disks_dir=/mnt/os/disks` | ~4 min + ~7 min |
| `solaris10-install` | `solaris10-install-sparc64.py`: the whole Solaris 10 1/13 text install from the DVD to the IDE disk on `sun4u`, answered on ttya. Manual only, needs `--timeout 9000` (the workflow choice passes it). Through PVE: the install target `sol10-sun4u` ("The Solaris 10 install target") | ~80 min |

`display` needs a `pve-qemu-kvm` with the cg3 patches (`submodules/SPARC.md`); with an older one
every size but 1024x768 fails at QEMU's `Unsupported resolution` (1152x900: OpenBIOS faults).
`idle` needs one with the idle patches (0011-0016): with an older one the `pmc` disk panics at boot,
`sunos-idle=off`/`solaris-idle=off` are unknown machine options and Solaris without `pmc` spins. Its
multiprocessor cases need pve-qemu patches 0023-0024 (`solaris-smp-idle`): without them
`solaris-smp-idle=off` is an unknown option and every vCPU spins.

The disks are `sol26-enduser-installed.raw` and `sol251-enduser-installed.raw` (End User installs by
`solaris-install-serial.py` on SS-5), `sol26-enduser-ss10-installed.raw`, `sol26-enduser-ss20-installed.raw`
(the same on SS-10 and SS-20 with OpenBIOS, `MACHINE=SS-10`/`SS-20`, ~8.5 min each) and
`sol26-enduser-ss20prom-installed.raw` (SS-20 with `BIOS=ss20_v2.25_rom CPU=TI-SuperSparc-50`; its first boot
is still pending: a reconfiguration boot and the root password screen, which `login()` answers),
`sol26-enduser-pmc-installed.raw` (the 2.6 one with the `pmc`
driver), `netbsd111-installed.raw` (see "Idle") and `sunos414-installed.raw` (see "SunOS 4.1.4"), the CDs
`solaris_2.6_598_sparc.iso` and `solaris_2.5.1_1197.iso`.

`.github/workflows/sparc-lab.yml` runs a matrix (`smoke` unless chosen otherwise) on demand and every
week, never for pull requests or pushes: it needs the media, on a self-hosted runner labelled
`sparc-lab`. It builds the lab image without cache (so it has the newest published package), mounts
the three directories (inputs, defaulting to the paths above) and the bench disk's directory when the
bench disk exists (`bench_disk`), puts the table in the job summary, uploads everything but the disks
as an artifact and removes its run directory. The artifact has every
case's recordings (see "Recordings"): open a case's `index.html` from the downloaded artifact to play
them.

## Attach to a PVE VM

`lab.py run <scenario> --pve <vmid>` (and `serve --pve <vmid>`) drives a VM that PVE starts, on the
PVE node itself (where `qm` and `/var/run/qemu-server/` are), instead of starting QEMU:

- **Serial console:** `/var/run/qemu-server/<vmid>.serial<N>`, which the VM has with `serialN: socket`
  (the port `vga: serialN` names, else the first socket; `--var SERIAL=N` picks another). Same VT100
  emulation, `expect()`, `send()` and `key()` as with a QEMU of its own.
- **Monitor:** QMP on `<vmid>.qmp`, one connection per command (send-key, screendump, `hmp()`).
  QEMU serves one client there at a time, and PVE's own tools (`qm`, pvestatd, the API) connect per
  command and give up after a few seconds: a lab that stayed connected made `qm sendkey` fail
  (`unable to connect to VM 100 qmp socket - timeout after 51 retries`) and dropped the QEMU version
  from `qm status --verbose`. The lab waits its turn while another client has the socket, and waits
  for QEMU to close each connection before opening the next: a client that connects right after the
  previous one closed gets the greeting but no replies (seen with QEMU 11.1 under PVE). `qm monitor` /
  the API's `monitor` call would also work but start a Perl process per key.
- **Framebuffer:** `screendump` through QMP, so OCR steps work; keys through QMP `send-key`. VNC
  without a client doesn't refresh the display, so `REFRESH` works as with a QEMU of its own.
- **Lifecycle:** a stopped VM is started with `qm start` (the lab connects to the serial socket while
  `qm start` runs; a VM with `freeze: 1` gets `cont` once it is connected, not tested) and stopped with `qm stop` when the
  scenario ends (`--keep-running` leaves it running and detaches); a running VM is attached to and left
  running. PVE runs QEMU with `-no-shutdown` and qmeventd ends it when the guest powers off, so a
  power-off is QEMU's pid (`<vmid>.pid`) going away: `wait_exit()` works, "QEMU died" reports `qm
  status`, and the exit code isn't visible (taken as 0).
- **Console ownership:** the lab owns the serial console while it runs. QEMU serves one client per
  serial socket and a second one waits unanswered, so the lab refuses to start when the socket
  already has a client (`qm terminal`, the web console's xterm.js), and `qm terminal` gets nothing
  until the lab is done.
- **Not the same as starting QEMU:** the VM's hardware is its PVE config, so `qemu_args()` isn't used
  (`DISK`, `ISO`, `TEMPLATE`, `MACHINE`, ... set nothing). `TRACE` is turned on through the monitor
  (`logfile` + `trace-event`) once attached, so events before that are missed. `cpu_use()` reads the
  pid from `<vmid>.pid` and works. Output the guest wrote before the lab connected is lost when
  attaching to a running VM.

Scenarios run in both modes: `pve_vars()` reads the VM's config (`qm config`) and sets what the
scenarios read as variables, between the scenario's `DEFAULTS` and `--var`: `ARCH`, `MEM`, `SERIAL`,
`CONSOLE` (`serial` without a display, else `fb`) and, for `arch: sparc`, `MACHINE`, `BIOS`, `VGA`
(`none` for `vga: serialN`), `BOOT=c` (qemu-server sets no boot device, so OpenBIOS tries the disk first and
`prom_boot()` boots the CD at the `0 >` prompt), `CDROM_AS` (`hd` for a target 6 CD-ROM with
`cd_as_disk=1` and a medium, or a target 6 disk without `media=cdrom`) and `REFRESH`. With a Sun
PROM, `prom_boot()` types `ttya io` on the keyboard only when the banner says `Keyboard Present`:
qemu-server starts a VM without a framebuffer with `-nographic`, which leaves the keyboard out, and
the PROM (`No Keyboard`) reads ttya by itself. `solaris-install-serial.py` and `solaris-boot-disk.py` ran unchanged
against a PVE VM; `solaris-boot-cd.py`, `idle.py` and `bench.py` read only these variables but weren't
run in attach mode; `cg3-display.py` needs `--var GUEST=1` or `GUEST=` (its `qemu_args()` sets it).
`alpine-boot-cd.py` and `netbsd-boot-cd.py` are attach mode only.

### Provision a Solaris VM on a PVE node

The sparc32 default profile with the text installer on ttya (`vga: serial0`), a Sun-labelled blank
disk imported from the template as `scsi3`, the Solaris 2.6 CD on target 6:

```sh
xz -dk sparc-SUN2.9G.raw.template.xz          # the installer lists only Sun-labelled disks
qm create 100 --arch sparc --name sol26 --memory 256 --ostype solaris --net0 lance,bridge=vmbr0 \
  --serial0 socket --vga serial0 \
  --scsi3 local:0,import-from=/root/sparc-SUN2.9G.raw.template,format=raw \
  --scsi6 local:iso/solaris_2.6_598_sparc.iso,media=cdrom
python3 lab.py run scenarios/solaris-install-serial.py --pve 100 --out /root/runs/install
python3 lab.py run scenarios/solaris-boot-disk.py --pve 100 --out /root/runs/boot
```

`lab.py install sol26-ss5 --vmid 100` does all of this and more in one command (see "Install
targets"). (`qm disk import 100 <template.raw> local --format raw` and then `qm set 100 --scsi3 <volume>` does
the same as `import-from` for an existing VM.) The install ends with `halt`, which powers the VM off;
the disk then boots first with the CD still attached. Measured in the e2e container (TCG, one guest at a time):
install 550-575 s, first boot to `console login:`, `uname`/`df`/`ifconfig` and `init 5` 163 s. The lab
needs `python3-pyte`, `python3-pil`, `tesseract-ocr` and `fonts-dejavu-core` on the node.

### `pve_matrix.py`

`pve_matrix.py pve` creates each VM through the API (`pvesh create /nodes/<node>/qemu`, the media linked
into the `local` storage), runs its scenarios in `<runs>/<case>/<n>-<scenario>/`, destroys the VM
and prints a summary like `matrix.py`:

| Case | VM | Scenarios |
| ---- | -- | --------- |
| `sol26-install-ss5` | the install target `sol26-ss5`, created by `lab.py install` (SS-5, OpenBIOS, `vga: serial0`, a Sun-labelled disk on target 3, the 2.6 CD on target 6) | `lab.py install sol26-ss5 --check`: install, first boot (root password, marker), CD ejected, then a boot that logs in with the documented password and checks `/etc/wsh-lab-target` |
| `alpine-aarch64` | `arch: aarch64`, virt, OVMF (AAVMF), `vga: serial0`, the Alpine 3.19 CD on virtio-scsi | `alpine-boot-cd.py`: login prompt, root, `uname -m` |
| `netbsd-sparc64` | `arch: sparc64` as the create wizard makes it (sun4u, OpenBIOS, a blank disk on `ide0`, the NetBSD 11.1 CD on `ide2`, `sunhme`, 512 MB, the API's default boot order), `vga: serial0` | `netbsd-boot-cd.py` with `BOOT=` (OpenBIOS must boot the CD by itself): sysinst, its shell, `uname -m` |
| `alpine-x86_64` | `kvm: 0`, `vga: std`, `serial0: socket`, the Alpine 3.19 CD on `ide2` | `alpine-boot-cd.py` on the VGA console (OCR, send-key), `uname -m` also through the serial port |
| `sol26-ss20-smp2` | SS-20, OpenBIOS, `cores: 2`, 512 MB, `vga: serial0`, the installed 2.6 SS-20 disk imported to target 3, the bench disk (`--bench`) imported read only to target 4 | `smp-soak.py` with `SMP=2 SOAK=0`: `psrinfo` lists 2 CPUs on-line, then Dhrystone and the `nawk` loop alone and as 2 copies at once |
| `sol26-ss20prom-nvram` | SS-20, the Sun SS-20 PROM (`ss20_v2.25_rom`), 512 MB, `vga: serial0`, a blank `nvram0` (`local:1`), the stored `sol26-enduser-ss20prom-installed.raw` imported to target 3 (its first boot still pending) | `sun-prom-nvram.py`: `setenv diag-switch? false` at the first `ok`, `boot disk`, the first boot (reconfiguration, root password) to `login:`, `eeprom` shows `diag-switch?=false`, `halt`; `qm stop`/`qm start` and the PROM must boot the disk by itself to `login:`; `reboot -- -r` to `login:` with the DBRI's nodes in `/devices`; any `BAD TRAP`, `panic` or QEMU `Trap` fails it (pve-qemu `wsh/0061` and `wsh/0066`, pve-qemu-kvm 11.1.3-4+wsh2 or later) |

One run took 12 min for `sol26-install-ss5` and about a minute for each of the others;
`sol26-ss20prom-nvram` 5-5.5 min (first boot to the shell 108-111 s, the auto-boot 60 s, `boot -r` 66-76 s;
pve-qemu-kvm 11.1.3-4+wsh2, 2026-11-22). Run one case alone with `--only`, e.g. `python3
pve_matrix.py pve --only sol26-ss20prom-nvram --runs <dir>`. `sun-prom-nvram.py` runs in attach mode
only (`lab.py run scenarios/sun-prom-nvram.py --pve <vmid>`) and needs a VM whose `nvram0` is blank:
a volume the PROM has written boots by itself at the first start, which the scenario reports as a
failure.

`pve_matrix.py recordings` (not in the weekly run) has the cases only the docs' recordings need (see
"Recordings in the docs"): `sol26-ss20-smp4`, the stored disk `install-sol26-ss20.raw` on SS-20 with
OpenBIOS and `cores: 4`, `solaris-boot-disk.py` with `psrinfo` (CPU 3 on-line) and `mpstat 1 3`
(116 s); `sol22-install-ss10`, Solaris 2.2 on SS-10 with OpenBIOS (pve-qemu-kvm 11.1.3-2+wsh22 or
later), the CD image as a disk on target 6 (`cd_as_disk=1`), `solaris-install-serial.py` onto the
Sun-labelled template disk, then `solaris-boot-disk.py` (first boot, root password, `uname -a` must
show 5.2) (379 s: install 284 s, boot 84 s). Both passed on 2026-11-19.

It runs in the e2e PVE node with the lab added, privileged like the e2e container, the media
mounted read only:

```sh
docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
docker build -f e2e/sparc/pve.Dockerfile -t wsh-pve-lab e2e/sparc
docker run -d --name pve-lab --hostname pve --privileged --tmpfs /run --tmpfs /run/lock \
  -v /mnt/os/iso:/mnt/os/iso:ro -v /mnt/os/disks:/mnt/os/disks:ro \
  -v /mnt/os/disks:/mnt/os/disks:ro -v /mnt/runs:/mnt/runs wsh-pve-lab
docker exec pve-lab python3 pve_matrix.py pve --runs /mnt/runs/p1
```

The `sparc lab` workflow does this for the `pve` choice, and every week after `smoke` (its own
schedule), building both images from the published packages. The aarch64 and sparc64 cases need the
qemu-server fixes below: with a published package that lacks them they fail at `qm start`. The
sparc64 case also needs the sparc64 profile (qemu-server's `-boot order=` instead of `bootindex`):
without it OpenBIOS stops at its prompt and the case fails there. `sol26-ss20-smp2` needs qemu-server
with the CPU limits per profile (before, the API refuses a second CPU) and `pve-qemu-kvm`
11.1.3-2+wsh10 or later (before, Solaris hangs with 2 CPUs).

What qemu-server's command line had to change (`submodules/qemu-server.patch`):

- **`-bios ovmf` for every OVMF VM:** the patch passed `bios` as `-bios` for sparc and for `bios:
  ovmf`. An aarch64 OVMF VM then didn't start (`The contents of the first flash device may be
  specified with -bios or with -drive if=pflash... but you cannot use both`; x86 OVMF VMs not
  checked). Now sparc only.
- **sparc64 `smm=off`:** `should_disable_smm` skipped sun4m but not sun4u, which has no such property:
  a sparc64 VM with a serial display didn't start (`Property 'sun4u-machine.smm' not found`). Now
  skipped for `sun4*` too.
- **sparc64 serial ports:** they were `-device isa-serial`, a third 16550 next to the two the sun4u
  ebus already has, so OpenBIOS's ttya had no chardev and the socket stayed silent. Now `-serial
  chardev:serialN` as on sparc32.

- **sparc64 profile:** OpenBIOS can't drive the SCSI controller the wizard used to propose (`lsi`,
  "Cannot manage 'SCSI bus controller' PCI device") and doesn't boot the `bootindex` paths QEMU hands
  it (`/pci@1fe,0/pci@1,1/ide@3/cdrom:f`, "No valid state has been set"), so the case used to type
  `boot cdrom:f` at the prompt. Now sparc64 disks and CD-ROMs go on the built-in IDE (cmd646), the
  boot device is `-boot order=d|c` from the boot order, a new VM has its CD first, and there is no
  `virtio-balloon-pci`; the case boots without typing (`submodules/SPARC.md`, "sparc64 (sun4u)").

## Install targets

`lab.py install <target> --vmid N` installs a named target into a new PVE VM, on the node, as root,
and ends with an installed VM that is powered off and has documented login details. The user guide
is `docs/src/content/docs/guides/lab-install.md` (what a target is, media, how to run it on a node,
what it leaves, the security note); this section is how it is built and tested.

- **`targets.py`** is the catalogue, data only: per target the PVE profile (options for `pvesh
  create`), the disk (bus, size, a Sun label's geometry), the media by expected file name, the
  install method and its scenarios, the login, host name, network, duration and what was tested;
  `MEDIA` has each tested medium's size and sha256 (from the lab host's media; no medium is in the
  repository). The expected names are the names the media already have on the lab host and in the
  docs, so there is no mapping table. Targets marked `catalogue` are listed with what blocks them.
- **`install.py`** is the command (`install`, `targets`, `media` are subcommands of `lab.py`). It
  checks the media on the storage (`pvesh get .../storage/<s>/content`, `pvesm path`, size and
  sha256; `--allow-untested-media` accepts another checksum, a missing medium is always refused),
  refuses a VMID that exists anywhere in the cluster (`/cluster/resources`), creates the VM with
  `pvesh create` (the disk imported with `import-from` from an image that `sunlabel.py` labels:
  the same first sector as `sparc-SUN2.9G.raw.template.xz`, so no template is needed), then runs
  the method's phases through `lab.run_scenario(..., pve=vmid)` (what `lab.py run --pve` does),
  each with its own evidence directory under `--out`: `install/`, `firstboot/` and, with `--check`,
  `check/`. Between them it ejects the media (`qm set --scsi6 none,media=cdrom`: the drive stays)
  and sets `boot: order=<disk>`. At the end it writes the login, console, host name, network,
  marker and media checksums into the VM's description, converts to a template with `--template`,
  and writes `result.json` (phases, times, media) and `install.log`.
- **Stalls and failures:** each phase has a timeout (the target's; `--timeout` for the install
  phase). When it passes, the VM is stopped, the scenario ends with "QEMU died", and the phase is
  reported as `stalled`. Any failure leaves the evidence; the VM is destroyed, or with
  `--keep-on-failure` stopped and kept with `FAILED ...` and the evidence path in its description.
  Exit code 0 or 1. Idempotent where that is safe: `targets` and `media` only read, and a second
  `install` on the same VMID refuses instead of repairing or replacing it (destroy the VM first).
- **Secrets:** `lab.run_scenario` masks every variable named `*PASSWORD`, `*_KEY` or `*SECRET` in
  `result.json`; passwords are typed only at prompts that don't echo, so they are in no cast or
  screenshot. The VM's description has the passwords on purpose. The rule for later targets with
  licence keys: a local file that is never committed, a `*_KEY` variable, typed where the installer
  doesn't echo it.

### Install methods

A target's `method` picks a class in `install.METHODS` with three steps, `install`, `firstboot`
and `check`, each a scenario run against the VM:

1. **Scripted (implemented):** the installer is answered on the console by a scenario, as a person
   would (`expect()` on the serial console, OCR of the framebuffer). Solaris 2.6 uses
   `solaris-install-serial.py`, unchanged (the variables `HOSTNAME` and `IP` come from the target and
   `--hostname`/`--ip`), then `solaris-firstboot.py` (the first-boot questions answered with the root
   password, `/etc/wsh-lab-target`, the optional user, `init 5`), and `solaris-boot-disk.py` with
   `ROOT_PASSWORD`, `COMMANDS` and `CHECK` for `--check`. Solaris 7 uses the same three unchanged;
   Solaris 8 uses `solaris-webstart-serial.py` for the install (Web Start, see "Solaris 7, 8 and 9"
   below) and the same first boot and check. SunOS 4.1.4 has its own three
   (`sunos-install-serial.py`, `sunos-firstboot.py`, `sunos-boot-disk.py`; "SunOS 4.1.4" below).
   The NetBSD targets use `netbsd-install-sparc64.py` or `netbsd-install-sparc.py`, then
   `netbsd-firstboot.py` and `netbsd-boot-disk.py` (see "NetBSD install targets" below), OpenBSD
   `openbsd-install-sparc64.py` (8.0) or `openbsd-install-sparc.py` (5.9 on sun4m, with a sets CD
   made on the node), `openbsd-firstboot.py` and `openbsd-boot-disk.py` ("The OpenBSD 8.0 install
   target", "OpenBSD 5.9 on sun4m"), FreeBSD `freebsd-install-sparc64.py` (bsdinstall's own
   `bsdinstall script`, typed into the installer's shell), `freebsd-firstboot.py` and
   `freebsd-boot-disk.py` ("The FreeBSD 12.4 install target"); a target's `check` can bring its own
   `commands`.
2. **Unattended by the installer's own mechanism (used by Red Hat 6.2 and Debian 4.0; designed, not used for Solaris):**
   `install.Unattended` writes an answer CD on the node (`answer_media.py`: a one-directory ISO 9660
   image made by the standard library from the target's answers, never from vendor files, nothing
   secret on it) to the media storage as `wsh-lab-answers-<vmid>.iso`, puts it into the target's
   install `answers` drive for the install phase only, and removes the drive and the image
   afterwards, also when the install fails; first boot and check are the scripted ones. See "Red
   Hat Linux 6.2" (kickstart) and "Debian GNU/Linux 4.0" (preseed) below. Solaris 2.6
   reads a `sysidcfg` and a custom JumpStart profile (`rules.ok`) only from a diskette or over NFS
   (`boot net - install`, with RARP/bootparams). The sparc32 profiles have no floppy drive (the
   `floppy` content type and `floppyN` are x86 only), a boot server is out of scope, and the other
   media-only way, a remastered install CD with the profile on it, would mean writing modified Sun
   media on the node. The scripted install, by contrast, has passed every weekly `pve` run in 9-10
   minutes, so it stays. The data model leaves room for it: a method whose `install` step builds a
   small answer image (an ISO or floppy made on the node from the target's answers, never from vendor
   files) and attaches it as a second medium before the installer starts; it fits installers that
   look for an answer file on removable media (Windows' `autounattend.xml` on a floppy or CD, Debian
   preseed on a second CD).
3. **Media swapping (used by `msdos622`):** a medium in `media` with `at: <regex>` is inserted into
   its `drive` when the installer shows that prompt: `install.MediaSwapper` follows the serial output
   by cursor (`Machine.serial_wait`, so the scenario's own `expect()` position doesn't move) or, for a
   VM without a serial console, the VGA text screen (a prompt is acted on once; the next regex is
   looked for only after the previous one has left the screen), and calls
   `PveMachine.change_medium(drive, volume)`, i.e. `qm set <vmid> --scsi6 <volume>,media=cdrom` (or
   `--floppy0 <volume>,ro=1`), which PVE applies live. With `at: "scenario"` the media are handed to
   the scenario in order as `SWAPS` instead, for prompts that don't say which disk they want
   (FreeDOS: "Insert diskette containing file A:\FREEDOS.024"; `sol8-ss20`: Software 1 of 2 and 2 of
   2, whose prompts are worded differently, and the scenario must wait for the medium before it
   answers); `tests/test_targets.py` and `tests/test_dos.py` check the order and that each prompt is
   acted on once.

### DOS install targets

`msdos622` (MS-DOS 6.22 from the three Setup floppies) and `freedos14` (FreeDOS 1.4, Floppy Edition)
are in `targets_dos.py`, merged into `targets.py`. The user guide is
`docs/src/content/docs/guides/dos.md` (the VM, the install by hand and with the lab, the memory
findings).

- **Profile** (`targets_dos.X86_DOS`): `machine: pc` (`isapc` isn't accepted by qemu-server),
  `cpu: pentium`, `kvm: 0`, 32 MB, `balloon: 0`, `tablet: 0`, `vga: std`, `ne2k_pci` (unused;
  `ne2k_isa` doesn't start, qemu-server puts it on the PCI bus), a 1 GiB IDE disk, `boot:
  order=floppy0;ide0`, no serial port. Floppies are attached `ro=1`. `tests/test_dos.py` checks it.
- **Media:** floppy images (`content: floppy`) on a storage with the `floppy` content type, under
  plain names (`msdos622-disk1.img` ... `-disk3.img`, `msdos622-supp.img`, `freedos14-boot.img`,
  `freedos14-disk1.img` ... `-disk6.img`). `install` and `lab.py media` say so when the storage lacks
  the content type (with the `pvesm set` command); `pve_matrix.py` links them from `--floppy`
  (`/mnt/os/floppy`) and adds the content type to the test node's `local`.
- **The screen** is the VGA text buffer (`vgatext.py`): the BIOS data area at 0x400 (mode, columns,
  rows, page, cursor) and the buffer at 0xB8000 (0xB0000 in mode 7), each read with QMP `pmemsave`
  into a private temporary file in a few ms; 40/80 columns, 25/43/50 rows, CP437 with the VGA glyphs,
  attributes (`Screen.highlighted()` for a menu bar). A graphics mode (the data area's mode, or a
  window that reads all 0x00/0xFF) is reported as not text and `vga_text()` falls back to OCR.
  `Machine.vga_expect(regex, tail=n)` waits on it, `vga_snap()` records it as a step
  (`NNN-vga.txt` and its rendering). The MCP server's `screen_text` uses it for x86 VMs in a text
  mode (`method: vga-text`, else `ocr`). Limits: a program that sets VGA registers itself leaves the
  data area stale (taken as text only when the buffer looks like text); the cursor is the BIOS's
  (`int 10h`), not the CRTC's; nothing reads 132-column VESA text modes yet.
- **Keys** go through QMP `send-key` (US layout), 50 ms held and 60 ms apart (the BIOS buffer holds
  15 keys). Files are typed as `ECHO line>>file`, one command per line, and read back: `COPY CON`
  flushes the keyboard buffer when it starts reading, and lines typed while it opened the file were
  lost. With `--keyboard no` the check switches to the US layout with Ctrl-Alt-F1 before typing.
- **Phases:** `dos622-install.py` (SETUP: configure the unallocated space, restart, format,
  settings, `C:\DOS`, disks 2 and 3 through the swapper, remove the floppy, first boot to `C:\>`),
  `dos-firstboot.py` (known `CONFIG.SYS`/`AUTOEXEC.BAT` without SMARTDRV, the idle TSR
  `C:\DOS\WSHIDLE.COM` typed in with `DEBUG` by `_dos.debug_write` and loaded by `AUTOEXEC.BAT`, the
  marker `C:\WSHLAB.TXT`), `dos-boot-disk.py` (`VER`, the marker, `MEM`, and with `IDLE_BELOW` the
  host CPU of the VM idling at the prompt: both targets check below 25% of a core).
  `freedos-install.py` answers FDI (partition and reboot, format, six disk swaps, eject before the
  last reboot). All scenarios also run under the
  lab's own QEMU (`_dos.qemu_args`: `FLOPPY`, `DISK`, `DISK2`, `OPTION_ROMS`, ...).
- **Idle:** DOS keeps a host core at 100% at its prompt without an idle driver. MS-DOS gets
  `WSHIDLE.COM` (`dos_tools.py com --name wshidle`: `STI; HLT` in INT 28h and INT 2Fh AX=1680h, 142
  bytes, assembled in Python from hand-encoded instructions); FreeDOS's installer already loads
  `FDAPM APMDOS`. `scenarios/dos-idle.py` measures it (host CPU at the prompt, the BIOS timer, a typed
  `ECHO`, `BUSY`: programs that count loop iterations, `dos_tools.py com --name busy|busyk`); numbers
  and the comparison with `POWER.EXE` in the DOS guide, "Idle".
- **CI** (`.github/workflows/sparc-lab-dos.yml`, GitHub-hosted): the unit tests, then
  `tests/test_freedos.py` in the lab image: FreeDOS from the Actions cache (`fetch_media.py`, checked by
  sha256; `e2e/README.md`, "Downloaded media in the Actions cache"), installed from its seven
  floppies, booted from the disk, marker and idle checked. No Microsoft media.

Tested in the PVE test container on the lab host (TCG, published packages pve-qemu-kvm
11.1.3-2+wsh11, qemu-server 9.2.15+wsh6, pve-manager 9.2.28+wsh4), 2026-11-17:

| Run | Result | Time |
| --- | --- | --- |
| `install msdos622 --vmid 302 --check` | passed: both swaps by the VGA swapper, marker, `VER`, `MEM` 614K free with KEYB NO / 621K without | 4.1 min (install 42 s, first boot 165 s, check 18 s) |
| `install freedos14 --vmid 303 --check` | passed: six swaps by the scenario, eject before the reboot, marker, `VER` | 10.3 min (install 366 s, first boot 177 s, check 35 s) |
| `tests/test_freedos.py` in the lab image (`e2e/sparc/Dockerfile`) | passed: six swaps, marker, `VER` | 392 s |
| unit tests (`test_vgatext.py`, `test_dos.py`, `test_targets.py`), after the rebase onto the wsh-lab package and network choices | 65 passed | 6 s |
| `pve_matrix.py install --only install-msdos622 --only install-freedos14` (rebased, PVE image from the branch) | 2/2 passed | 282 s, 678 s |
| `pve_matrix.py pve` and `matrix.py smoke` on the rebased branch | 5/5 and 3/3 passed | |
| the MCP server (`tests/test_mcp_server.py`, and `screen_text` on a FreeDOS guest under `lab.py serve`) | 6 tests passed; `method: vga-text`, 6 ms per call | |

With the idle driver (published pve-qemu-kvm 11.1.3-2+wsh26, qemu-server 9.2.19+wsh2, pve-manager
9.2.31+wsh4), 2026-11-20:

| Run | Result | Time |
| --- | --- | --- |
| `install msdos622 --vmid 9302 --check --export /mnt/os/disks` | passed: `WSHIDLE.COM` typed in (142 bytes, `DIR` checked), `MEM` 621K free, idle 2.3% of a core; stored disk replaced | 7.4 min (install 79 s, first boot 281 s, check 44 s) |
| `boot-test msdos622` / `boot-test freedos14` from the stored disks | passed, idle 2.5% / 1.8% | 0.9 / 1.3 min |
| unit tests (`test_dos.py`, `test_targets.py`, `test_vgatext.py`, `test_stored_disks.py`, `test_freedos.py` skipped without `WSH_LAB_GUEST_TESTS`) | 169 passed, 2 skipped | 6 s |
| `dos-boot-disk.py IDLE_BELOW=25` under the lab's own QEMU (TCG) on a copy of the stored FreeDOS disk, as `test_freedos.py` runs it | passed, idle 0.9% | 49 s |

### The first-megabyte matrix

`dos_mem.py --vmid <installed msdos622> --runs DIR` measures what DOS gets of 640K-1M per VM variant
(VGA model, NIC and its option ROM, dummy option ROMs of 4K/32K/100K, the owner's original dummy
file, `apic-common.vapic=off`, and `legacy-layout`: qemu-server's `machine: pc,legacy-bios-layout=1`,
which needs a qemu-server with it) and per `CONFIG.SYS` (none, HIMEM, EMM386 `NOEMS`/`RAM`/`HIGHSCAN`,
`I=` the free gap, `I=` into SeaBIOS's data). It adds the tools disk as D: (`dos_tools.py`: a FAT16
image built with mtools from the owner's utility CD, never committed; a disk rather than a floppy
or the CD because a CD needs MSCDEX, which would take the memory being measured), writes the ROMs to
`/var/lib/vz/template/dos/`, sets the variant (`qm set`, `args:` with SeaBIOS's debug console on
port 0x402), runs `scenarios/dos-mem.py` (per config: write `CONFIG.SYS`, Ctrl-Alt-Del, UMASCAN from
the VGA screen, `MEM /D` and `EMM386` into `D:\OUT`; a config that hangs DOS is recorded and undone
with F5) and reads the files back with mtools. It prints the table into `summary.md`; the results
are in the DOS guide.

### Memory profiles

`dos_profiles.py` keeps DOS memory profiles as data (per flavour, `msdos` and `freedos`: `full`
everything high without EMS, `ems` with the page frame at D800, `maxconv` HIMEM only, `noemm` HIMEM
with the drivers low, `installed` the disk's own files) and tries them without a PVE node and
without typing: for each profile it copies an installed disk (sparse), writes the profile's
`CONFIG.SYS` (`FDCONFIG.SYS`) and `AUTOEXEC.BAT` onto the copy with mtools, together with our own
test programs (`dos_tools.py com`, hand-assembled, a few hundred bytes each) and `MEASURE.BAT`,
boots it in the lab's own QEMU (`scenarios/dos-profile.py`, sb16 + adlib + PC speaker into a WAV
file, `-d guest_errors,unimp`) and reads the guest's results back from the copy:

| Measure | From |
| --- | --- |
| free conventional, largest program, upper, XMS, EMS | `MEM` (both DOSes' summary), `MEM /C` as evidence |
| EMS pages and page frame | `EMSCHK.COM` (EMMXXXX0, INT 67h AH=42h/41h) |
| VGA retrace | `VGARTRC.COM`: eight reads of 3DAh in a row with display enable, within a second (`dumb` never gives two) |
| 3C0h in the data state | `VGAAR.COM`: reads the attribute address after writing 20h, restores PAS; `FAIL` before pve-qemu `wsh/0051` |
| Sound Blaster, audio | `SNDCHK.COM` (DSP reset and version at 220h, an AdLib tone, a PC speaker beep) and the WAV (seconds with sound) |
| display, QEMU's complaints | a last screendump (share of lit pixels), the lines of `qemu-d.log` |

`--games-disk D.raw --games FILE` adds a game per run (`RUN.BAT` after the measurements; the scenario
presses the keys and samples the screen: distinct frames, last change, back at the prompt), and
`--menu` writes the profiles as one multi-configuration `CONFIG.SYS` (MS-DOS `[MENU]` blocks, FreeDOS
`n?` lines) and picks each entry at the startup menu. `--extra local.json` adds a disk's own drivers
(CD-ROM, mouse, KEYB, an idle TSR) for lab runs; that file stays on the lab host.

```sh
python3 dos_profiles.py show --flavour msdos            # the CONFIG.SYS and AUTOEXEC.BAT of each profile
python3 dos_profiles.py run --flavour freedos --disk c.raw --out /work/prof --vga std,retrace=precise
```

CI (`sparc-lab-dos.yml`) runs `tests/test_dos_profiles.py` on the disk `test_freedos.py` just
installed: the five FreeDOS profiles under `-vga std,retrace=precise`, `full` once more under `std`
(VGARTRC must time out there) and the four menu entries, each checked (MEM read, EMS frame only in
`ems`, VGARTRC, VGAAR, SB DSP 4.05, sound in the WAV, the screen lit). The lab's MS-DOS runs and
their results are in the DOS guide ("Memory profiles").

| Check (2026-11-21, lab image with pve-qemu-kvm 11.1.3-3+wsh2, TCG) | Result | Time |
| --- | --- | --- |
| `tests/test_dos_profiles.py` (19 tests; the guest part on a copy of the stored FreeDOS disk, two other guests running) | 19 passed | 73 s |
| `VGAAR.COM` under pve-qemu-kvm 11.1.3-2+wsh16 (without `wsh/0051`) | `2000 FAIL`, screen lit | 7 s |

### The Solaris 10 install target

`sol10-sun4u` installs Solaris 10 1/13 from its DVD on the sparc64 profile (sun4u, OpenBIOS, a blank
16 GiB disk on `ide0`, the DVD on `ide2`, `sunhme`, `vga: serial0`, 1024 MB). Needs `pve-qemu-kvm`
11.1.3-2+wsh13 or later (the patched `openbios-sparc64`, `wsh/0021`) and qemu-server with the
sparc64 profile (`-boot order=d|c`).

- **install:** `solaris10-install-sparc64.py`, the same scenario as the lab's own install, with
  `DHCP=no`: host name, address and netmask typed into the installer's screens (no default route);
  the handlers match the screen title, and the network's confirmation screen must show the three
  values. The installer asks for the root password itself, so the target says `root_password: True`
  and `install` passes `ROOT_PASSWORD` (masked) to the install phase. With `--ip dhcp`, `install`
  sets `DHCP=yes`: the installer's `DHCP for hme0` screen says yes, then only the IPv6 and
  confirmation screens follow (no host name or address screens). At the installer's reboot
  the scenario stops the VM (`qm stop`, after "syncing file systems... done"): at the firmware's
  banner (openbios-sparc64 with patch 0030 resets the machine) or, with older firmware, when the
  reboot returns (`prom_reboot: reboot call returned!`); `install` then ejects the DVD and sets
  `boot: order=ide0`, as for the other targets. A panic before the language prompt (seen once in six DVD boots through PVE:
  `BAD TRAP: type=4e` with the PC in the firmware, from `prom_finddevice` in `vfs_mountroot`) fails
  the scenario at once with "before the installer"; the target's `retry_on` matches that, and
  `install` runs the install phase once more (evidence in `install-retry1/`): nothing is on the
  disk yet.
- **firstboot:** `solaris10-firstboot.py`: F2 at the keyboard layout question, root login with the
  installer's password, the marker, the optional user (`useradd`, `passwd`: Solaris 10 applies
  `MINNONALPHA=1` from `/etc/default/passwd` to root too and refuses `wshlab`, so the rule is
  relaxed for that one call and the file put back), `/etc/defaultrouter`
  and DNS (with `--ip dhcp`: `/etc/dhcp.hme0` checked, the host name written to `/etc/nodename`
  and as `inet <name>` to `/etc/hostname.hme0`, so dhcpagent asks the server for it and Solaris 10
  falls back to nodename when the server sends none; the installer leaves the name `unknown`),
  `init 5` (158-188 s in the three runs that passed, 356 s once: `svc:/network/inetd-upgrade` times out on the way down).
- **check:** `solaris10-boot-disk.py` with the usual `COMMANDS` (`prtvtoc` of `c0t0d0s2`, the
  target's `device`) and `CHECK`; with `--ip dhcp` also the target's `dhcp_check`: the `DHCP` flag
  on `hme0`, the router from `dhcpinfo -i hme0 Router` and `is alive` from a ping of it.
- `pve_matrix.py install` gives an install case the sum of the target's phase timeouts plus 10
  minutes when that is more than twice `--timeout` (Solaris 10: 4.75 h instead of 2 h).

Tested in the PVE test container on the lab host (14 host cores shared with another agent's runs,
TCG, published packages pve-qemu-kvm 11.1.3-2+wsh13, qemu-server 9.2.15+wsh6, pve-manager
9.2.28+wsh4), 2026-11-17:

| Run | Result | Time |
| --- | --- | --- |
| `install sol10-sun4u --vmid 101 --check` | passed: the install's network screens with 10.0.2.15/24, root/`wshlab`, the marker, `ide2: none,media=cdrom`, `boot: order=ide0` (`-boot order=c`); `df -k`: `/` 6.9 GB on `c0t0d0s0` (4.5 GB used), `/export/home` 8.6 GB on `s7`, swap on `s1`; the VM's disk 4.6 GB on the storage (sparse) | 108.5 min (install 4849 s, first boot 1164 s, check 481 s) |
| `install sol10-sun4u --vmid 102 --check --bridge vmbr1 --ip 10.77.0.50 --gateway 10.77.0.1 --dns 10.77.0.1 --domain lab.test --user lab` | failed in the first boot: `passwd lab` refused `wshlab` (`MINNONALPHA`, fixed); the fixed first boot run again on the kept VM passed, and a further boot showed `default 10.77.0.1`, `10.77.0.1 is alive`, `resolv.conf`, `lab` with a password (`logins -x`: `PS`) | install 4829 s |
| `pve_matrix.py install --only install-sol10-sun4u` (two sparc64 installs at once on the host) | failed: kernel panic while booting the DVD (`BAD TRAP: type=4e`, PC in the firmware, from `prom_finddevice` in `vfs_mountroot`), 20 min lost to the language prompt's timeout; the scenario now stops at the panic and `install` retries once (`retry_on`) | 21 min |
| the same again | passed | 109.6 min (4883 s, 1135 s, 541 s) |
| `install sol10-sun4u --vmid 103 --check` with the vmbr1 options and `--user lab` as above | passed: `passwd: password successfully changed for lab`, `default 10.77.0.1` in the check | 110.7 min (4907 s, 1167 s, 548 s) |
| unit tests (`test_targets.py` with the Solaris 10 handlers and the retry, `test_dos.py`, `test_vgatext.py`, `test_freedos.py`) | 71 passed, 1 skipped | 17 s |
| `pve_matrix.py pve` and `matrix.py smoke` on the branch | 5/5 and 3/3 passed | |

`--ip dhcp`, 2026-11-22, the PVE test container with the published pve-qemu-kvm 11.1.3-4+wsh4
(openbios 0030), qemu-server 9.2.20+wsh7, pve-manager 9.2.32+wsh11; dnsmasq on `vmbr0` with
10.0.2.2/24 as router and name server, a lease range from 10.0.2.15 (the addresses of QEMU's user
network); other agents' guests on the host:

| Run | Result | Time |
| --- | --- | --- |
| `install sol10-sun4u --vmid 9501 --check --ip dhcp` | passed: the installer took a lease (for net0's MAC) during system identification, its reboot came back at the firmware's banner (0030); the first boot found `/etc/dhcp.hme0` (host name `unknown` until it wrote `/etc/nodename`); in the check `Hostname: sol10-sun4u` (the client sent the name, dnsmasq echoed it in option 12), `hme0` `<UP,BROADCAST,RUNNING,MULTICAST,DHCP,IPv4>` 10.0.2.25/24, `default 10.0.2.2`, `router=10.0.2.2`, `10.0.2.2 is alive` | 119.8 min (install 5378 s, first boot 1266 s, check 526 s) |
| unit tests (`test_targets.py`, with the DHCP variable and check regex) | 116 passed | <1 s |

### Run it

On a node, from the `wsh-lab` package (`apt install wsh-lab`, see "The wsh-lab package" below;
`wsh-lab` is `lab.py`), from a clone (`python3 lab.py ...`; the guide also has a venv under
`/opt/wsh-lab`), or in the e2e PVE container with the lab (`pve.Dockerfile`):

```sh
wsh-lab targets
wsh-lab media                                   # every target's media on storage local
wsh-lab install sol26-ss5 --vmid 120 --check    # --template, --user lab, --keep-on-failure ...
```

The `pve` matrix's `sol26-install-ss5` case is `lab.py install sol26-ss5 --check` (so the weekly test
and the user command are the same code), and `pve_matrix.py install` goes through every automated
target (the `install` choice of the `sparc lab` workflow): installed once, then boot-tested from its
stored disk (see "Install once, then boot-test the stored disk" below). `pve_matrix.py` links each target's media from `--iso` into the test
node's `local` storage under the expected names; a converted medium (the SunOS CD) that `--iso`
doesn't have is made there from its source with `lab.py media --convert` (about 6 minutes more for
`sunos414-ss5` in the `install` choice, which needs `sunos_4.1.4_install.iso` in `--iso`). `tests/test_targets.py` (standard library only,
`python3 -m unittest -v tests/test_targets.py` in `e2e/sparc`) checks every target's profile against
`$SPARC32_PROFILES`/`$SPARC64_PROFILE` in `submodules/qemu-server.patch` (skipped without the
repository around it), unique names, the Sun label against the template's first MiB, the VM
options, the media swapper and the masking.

Tested in the PVE test container on the lab host (`pve.Dockerfile`, two host cores, one guest at a
time) with the published packages (pve-qemu-kvm 11.1.3-2+wsh10, qemu-server 9.2.15+wsh6,
pve-manager 9.2.28+wsh4), on 2026-11-16:

| Run | Result | Time |
| --- | --- | --- |
| `install sol26-ss5 --vmid 120 --check` from an empty VMID | passed: login `root`/`wshlab`, the marker, the description, `scsi6: none,media=cdrom`, `boot: order=scsi3` | 11.8 min (install 407 s, first boot 182 s, check 105 s) |
| the same again on VMID 120 | refused (`VM 120 exists already`), exit 1, nothing touched | 0 s |
| `install sol26-ss20 --vmid 121 --check --user lab --template` | passed: `lab` added with its password, converted to a template | 12.1 min (413 s, 191 s, 105 s) |
| the CD missing from `local:iso` | refused before creating anything, exit 1 | 2 s |
| a zero-filled file of the right size under the CD's name | refused (`checksum differs`), exit 1 | 3 s |
| that file with `--allow-untested-media --timeout 240 --keep-on-failure` | the boot never reaches the installer; stopped at 240 s, `stalled`, exit 1, evidence kept, VM kept stopped with `FAILED ...` in its description | 4.2 min |
| the same with `--timeout 60`, without `--keep-on-failure` | `stalled`, exit 1, evidence kept, VM and disk destroyed | 1.2 min |
| `pve_matrix.py pve --only sol26-install-ss5 --only netbsd-sparc64 --only alpine-x86_64` | 3/3 passed; `publish_media.py` finds the install's cast at its new path | 697 s, 58 s, 70 s |
| `matrix.py smoke` (lab image built from the branch: the new `login()` with an empty password) | 3/3 passed | 162 s, 113 s, 66 s |
| the `/opt/wsh-lab` venv from the guide (uv 0.13.8, `lab-requirements.txt`) | pyte and Pillow 13.0.0 from the venv, `targets`, `media`, the terminal renderer; a whole install from the venv was not run | |

The first run failed at the first boot and found a bug in the old `login()`: sysidroot's root
password form draws all its prompts at once, and matching them one by one typed the password ahead
of the form (it ended up echoed, root without a password). With an empty password that never
mattered. The password appears in none of the evidence files of the passing runs.

### Install once, then boot-test the stored disk

An install proves the installer still works; most regressions a package brings show up already when
the installed system boots. So the `install` matrix keeps one installed disk per target and installs
again only when asked:

- **`lab.py install <target> --check --export DIR`**: when the check passes, the VM's first disk is
  copied (sparse) to `DIR/install-<target>.raw`, and `DIR/install-<target>.json` beside it says what
  made it: the target, install date, `minutes`, the phases' seconds, the `pve-qemu-kvm`,
  `qemu-server` and `pve-manager` versions, the profile, disk size, host name, network, media
  checksums (and `lab_commit` from `WSH_LAB_COMMIT` when set). Both are written to temporary names
  and renamed when complete, so the previous disk stays until a new install has passed. `--export`
  takes only the target's default install: it refuses `--root-password`, `--user`,
  `--user-password`, `--data-disk`, `--post-install` and `--template` (the boot test logs in with
  the default password and checks the first disk), needs `--check` and a writable `DIR`, and
  refuses before installing anything when a file under the stored disk's name has no sidecar of its
  own (it never replaces a disk it didn't write). The `install-` prefix keeps the stored disks apart
  from the hand-made ones in the same directory (`matrix.py`'s `sol10-sun4u-installed.raw` was made
  with DHCP and is booted by the `solaris10` matrix).
- **`lab.py boot-test <target> --disk DIR/install-<target>.raw --vmid N`**: a new VM with the
  target's profile as `install` leaves it (media drives empty, `boot: order=<disk>`), its disk
  imported from the stored disk (`import-from` copies it into the VM's storage; the stored disk is
  only read), started by PVE, then the target's check scenario, the same `--check` runs (login with
  the default password, `target=<name>` in `/etc/wsh-lab-target`, the target's commands, power off).
  The VM is destroyed afterwards (`--keep` keeps it stopped). Evidence and `result.json` (with the
  stored disk's install date and packages) in `--out`. It refuses a disk without its sidecar or with
  another target's.
- **`pve_matrix.py install`** decides per target (`plan()`): its stored disk in `--disks` missing →
  `install --check --export <disks>`; there → `boot-test`; `--reinstall TARGET[,TARGET]` installs
  those again, `--reinstall` alone (or `all`) every target without `matrix_skip`. A target with
  `matrix_skip` is never installed by the matrix unless `--reinstall` names it: without a stored disk
  it is listed as `skip`, with one it is boot-tested. A target with `matrix_needs: apt_cache` (the
  Debian targets, whose netinst fetches the base system) is installed only when the matrix has an
  apt cache (`--apt-cache HOST:PORT` or `WSH_LAB_APT_CACHE`, "The apt cache pinhole" below);
  without one it is skipped like a `matrix_skip` target, also when `--reinstall` names it. A file
  under the stored disk's name that isn't ours fails the case. The summary counts skipped cases
  separately.

`matrix_skip` thus marks the targets an unattended run shouldn't install: Tribblix (3.5-4.3 h) and
`debian13-sun4u` (2.5-3 h, its packages fetched over the network, and only with the apt cache), both too
much of the 240-minute job and left out of the monthly `--reinstall all` (720 minutes); they are
installed on request (`--reinstall <target>`), their stored disks boot-tested otherwise. `--export` accepts the network options, so a Debian disk can also be
made by hand on a node with a route out (`lab.py install debian40-ss5 --vmid N --check --export
/mnt/os/disks --gateway G --dns D`); the matrix boot-tests a stored disk without any network (the
check needs none).

**The apt cache pinhole.** The guests' bridge in the PVE test container, `vmbr0`, has no route out,
and the Debian targets get no general way out either: `pve_matrix.py --apt-cache HOST:PORT` (or the
`WSH_LAB_APT_CACHE` environment variable; the `sparc lab` workflow passes the repository secret or
variable `WSH_LAB_APT_CACHE`) gives them one destination only, an apt cache (apt-cacher-ng) the
node reaches. Before the first install that needs it, the node gets `10.0.2.2/24` on `vmbr0`
(`APT_PINHOLE_IP`, in the targets' default network 10.0.2.0/24), IP forwarding off
(`net.ipv4.ip_forward=0`), and a transient systemd service `wsh-lab-apt-cache` running
`socat TCP4-LISTEN:3142,bind=10.0.2.2,fork,reuseaddr TCP:HOST:PORT`; the matrix checks that an HTTP
request through it gets an answer (when it gets none, those installs fail and the rest of the
matrix runs). The targets that fetch packages are installed with
`--apt-proxy http://10.0.2.2:3142` and no `--gateway` or `--dns`: apt and debian-installer hand an
HTTP proxy whole URLs, so the cache resolves `archive.debian.org` and the guest needs neither a
router nor a name server (`net_require` is satisfied by a proxy at an address on the guest's own
network, `install.proxy_on_network()`). What a guest on `vmbr0` can reach: the cache through
10.0.2.2:3142, the other guests on `vmbr0`, and the node itself (10.0.2.2: its services such as the
PVE API answer there; the test container has no firewall). Not: anything past the node (no default
route in the guest, and with one set by hand no forwarding or NAT in the node), nor a name server. The cache's address isn't printed, isn't in the
evidence (the guest and its logs see only 10.0.2.2) and isn't in the repository; the installed
system keeps `Acquire::http::Proxy "http://10.0.2.2:3142"` in `/etc/apt/apt.conf` (harmless
elsewhere: apt fails to connect). Without a cache the matrix skips the Debian targets (no stored
disk) and changes nothing on `vmbr0`. The `sparc lab` workflow's `install` choice mounts `disks_dir` writable and has a
`reinstall` input (empty by default: boot-test what is stored, install what is missing); any
`reinstall` raises the job's limit from 240 to 720 minutes, so `reinstall=tribblix-m34-sun4u` makes
a new Tribblix disk on the runner. The workflow runs `install` weekly (Sunday 07:17 UTC) and with
`reinstall=all` on the first Saturday of the month (07:17 UTC, 720 minutes). By hand on the node (or in the PVE test container):

```sh
wsh-lab install tribblix-m34-sun4u --vmid 9401 --check --export /mnt/os/disks   # ~4.3 h, once
wsh-lab boot-test tribblix-m34-sun4u --disk /mnt/os/disks/install-tribblix-m34-sun4u.raw --vmid 9402
python3 pve_matrix.py install --runs /mnt/runs/i1 --reinstall tribblix-m34-sun4u --only install-tribblix-m34-sun4u
```

`tests/test_stored_disks.py` (standard library only) covers the names, the sidecar, the atomic
replace (a failed copy keeps the old disk), the sparse copy, the refusals and `plan()`.

Tested in the PVE test container on the lab host with the published packages (pve-qemu-kvm
11.1.3-2+wsh21, qemu-server 9.2.19+wsh1, pve-manager 9.2.31+wsh1), 2026-11-19, with up to three
guests on the host at once (the Tribblix install ran beside the full matrix):

| Run | Result | Time |
| --- | --- | --- |
| unit tests (`test_stored_disks.py`, `test_targets.py`, `test_dos.py`, `test_vgatext.py`) | 117 passed | 6 s |
| `pve_matrix.py install --only install-netbsd111-sparc`, empty disks directory | installed and exported: `install-netbsd111-sparc.raw` (3 GiB, 277 MB allocated) and its sidecar | 6.5 min |
| the same again | `boot-test` from the stored disk, VM destroyed | 66 s |
| `--only install-tribblix-m34-sun4u --reinstall tribblix-m34-sun4u` | installed and exported (8 GiB, 1.1 GB allocated) | 207 min: install 111, first boot 71, check 25 |
| the same without `--reinstall` | `boot-test` passed | 25.7 min: login after 13.7, `init 5` 10.7 |
| `pve_matrix.py install` (the workflow's default), Tribblix still installing | 18/18 passed, 2 skipped (Debian): 15 installed and exported, Tribblix (its disk had just appeared) and `netbsd111-sparc` boot-tested | 5.6 h of installs; `sol10-sun4u` 107 min |
| `pve_matrix.py install` once more, every disk stored | 18/18 passed, 2 skipped: all boot-tests | 56 min: Tribblix 25.8, `sol10-sun4u` 8.8, the others 25-119 s each |
| `boot-test sol10-sun4u` beside the matrix | passed | 11.7 min |
| refusals on the node: `boot-test` of `sol10-sun4u-installed.raw`, `install --export` without `--check`, `boot-test` of a missing disk, `--reinstall nope` | refused, exit 1, nothing created | |

### Solaris 7, 8 and 9

**Solaris 7** (3/99, `sol7-ss5`, `sol7-ss20`) asks 2.6's questions plus two whose defaults fit:
Subnets (yes, 255.255.255.0) and Select 64 Bit (no). `solaris-install-serial.py` answers it
unchanged; the installer writes `/etc/netmasks` itself, so `solaris-firstboot.py` now replaces the
classful entry instead of adding a second one (the first one wins).

**Solaris 8** (1/01, `sol8-ss20`) is installed by Web Start, which runs in command line mode on a
serial console without a framebuffer. `solaris-webstart-serial.py` answers it by prompt (the last
lines of the screen against a table; an unknown prompt fails the run). The flow, as recorded:

1. The Installation CD's mini-root formats the boot disk (it lists only a Sun-labelled disk; a
   blank one ends in `No Hard disks found on the system.`), puts a 512 MB swap slice at cylinder 0,
   copies a mini-root to it and reboots with `reboot -l -q -- <that slice>` (`/sbin/cd0_install`).
   OpenBIOS's reboot drops the boot string: with `auto-boot?` true it boots `disk`, whose boot block
   opens slice a (`ufsboot: cannot determine filesystem type of root device`) and powers off. The
   target therefore has `install: {"prom_env": {"auto-boot?": "false"}}`: `install.set_prom_env()`
   sets `args: -prom-env auto-boot?=false` before the install phase (refused if the VM has `args`
   already) and `Job.finish()` deletes `args` again. OpenBIOS then stops at `0 >` after every reset,
   and the scenario boots `.../sd@3,0:b`. A `setenv auto-boot? false` typed at the prompt doesn't
   survive the reset.
2. Web Start's system identification (it sets the root password itself, so the target has
   `"root_password": True` and the first boot gets no root password form), then media (CD),
   `Please insert the Solaris 8 Software 1 of 2 CD.`, the install type. **Default Install** also
   selects the Documentation and the Computer Systems Supplement CDs (not in the target), so the
   scenario takes **Custom Install**: English and the C locale, the Documentation and Supplement
   CDs deselected (a partly selected CD toggles `[-]` -> `[X]` -> `[ ]`), no extra products, 32-bit,
   the Entire Group with its default packages, auto-layout on c0t3d0 (`/` 1106 MB, swap 512 MB,
   `/export/home` 5976 MB).
3. After the first CD's packages: `Please specify the media from which you will install Solaris 8
   Software 2 of 2`, `Please insert the CD for Solaris 8 Software 2 of 2 (SPARC Platform Edition).`
   The two Software CDs are media with `at: "scenario"`: the scenario puts the next one in (`qm set
   --scsi6`, live) when a prompt asks, waits 5 s and answers; it fails if a CD in `SWAPS` was never
   asked for. Then `<Press Return to reboot the system>`; the reboot stops at `0 >`, where the
   scenario types `power-off`.

The End User Group would need only Software 1 of 2 (its 274 packages are all on that CD, from the
CD's `.clustertoc`); Entire uses both, so the target exercises the swap. Booting Software 1 of 2
directly would give the classic `suninstall` instead of Web Start; not tried.

**Solaris 9** (the DVD, `sol9-ss20`): the last release for sun4m (Solaris 10 dropped it); the DVD's installer
and the installed 32-bit kernel (`SunOS Release 5.9 Version Generic 32-bit`) run on the emulated
SS-20 with OpenBIOS. The DVD asks for the language, a paged locale list (0 = English C) and the
terminal type, then runs the same Web Start from the DVD (no mini-root copy) with a few more
questions: the default route (1 = find one; "could not be detected", Accept), Kerberos (no), no
automatic reboot or eject, data preservation (no), and summaries that pause 30-90 s (`c`). The
target installs the End User Group. Its prompts carry a key hint (`<Press ENTER to continue>
{"!" exits}`) that the scenario strips.

The SS-20 targets came first because Web Start is Java and the SS-5 then ran Solaris about 9 times
slower than the SS-20; since #262 the two are equally fast, and 8 and 9 install on the SS-5 with
256 MB too (`sol8-ss5`, `sol9-ss5`, "Solaris 8 and 9 on the SS-5" below).

Tested in the PVE test container on the lab host with the published packages (pve-qemu-kvm
11.1.3-2+wsh13, qemu-server 9.2.15+wsh6, pve-manager 9.2.28+wsh4), 2026-11-17, each with `--check`
(the check boot logs in with `root`/`wshlab` and finds the marker):

| Run | Result | Time |
| --- | --- | --- |
| `install sol7-ss20` | passed; `SunOS sol7-ss20 5.7 Generic_106541-02 sun4m sparc SUNW,SPARCstation-20`; `/` 86546 KB, `/usr` 288827, `/export/home` 2094553; `le0 10.0.2.15 netmask ffffff00` | 10.3 min (install 334 s, first boot 182 s, check 86 s) |
| `install sol7-ss5` (alongside the first Solaris 8 attempts) | passed; one `10.0.0.0` entry in `/etc/netmasks` | 10.7 min (341 s, 197 s, 89 s) |
| `install sol8-ss20` (alongside the Solaris 9 attempts) | passed; `SunOS sol8-ss20 5.8 Generic_108528-05 sun4m`; both Software CDs installed (`Installation details: Solaris 8 Software 2 Installed`); `df -k` `/` 1097262 KB (638893 used), `/export/home` 6021365; the finished VM has no `args` and `scsi6: none,media=cdrom` | 29.6 min (1443 s, 215 s, 94 s) |
| `install sol9-ss20` | passed; `SunOS sol9-ss20 5.9 Generic sun4m sparc SUNW,SPARCstation-20`; `df -k` `/` 803854 KB (439790 used), `/export/home` 6294629 | 26.7 min (1192 s, 289 s, 96 s) |
| `pve_matrix.py install --only install-sol7-ss5 --only install-sol7-ss20 --only install-sol8-ss20 --only install-sol9-ss20` (one guest at a time, after the code above was final) | 4/4 passed | sol7-ss5 11.0 min (358 s, 198 s, 87 s); sol7-ss20 10.7 min (336 s, 198 s, 91 s); sol8-ss20 28.9 min (1399 s, 216 s, 95 s); sol9-ss20 26.8 min (1207 s, 284 s, 94 s) |
| `pve_matrix.py pve` (regression, same code) | 5/5 passed | `sol26-install-ss5` 764 s, the others 59-233 s |
| `matrix.py smoke` (lab image with the branch's `e2e/sparc`) | 3/3 passed | 159 s, 110 s, 68 s |

`pve_matrix.py install` runs every automated target, so the `install` choice of the `sparc lab`
workflow now needs the Solaris 7, 8 and 9 media too and takes about 80 min longer. Not tried: an
SS-5 install of 8 or 9, a 3G disk for 8 or 9, `--ip dhcp` with 7, 8 and 9 (their `net_modes` is
`["static"]` until it is; the first boot writes the same files as for 2.6), `--gateway`, `--dns`,
`--vlan`, `--user` and `--data-disk` with them.

### Solaris 8 and 9 on the SS-5

`sol8-ss5` (8 2/02, Entire Group, three CDs) and `sol9-ss5` (9 9/05, End User, the DVD) are the
SS-20 targets' Web Start installs on an SS-5 with 256 MB (OpenBIOS, 9G disk). They use the later
updates, whose Web Start differs in four screens that `solaris-webstart-serial.py` now answers:

- 9 9/05 shows a license after the installer options (paged, then `Enter 'y' to accept the license
  agreement. Enter 'n' to decline the license agreement and exit the install.`). The question
  ends in neither a colon nor a default in brackets, so `wait_prompt()` also settles on that line
  (`PROMPT_END_BARE`).
- 8 2/02's Installation CD asks `Do you want to format /dev/dsk/c0t3d0 [y,n,?,q]` (8 1/01: `c0t3d0?`).
- 8 2/02 asks for the CDs as `Please insert the first Solaris Software disc from which you will
  install the Solaris Operating Environment.` and `Please insert the CD/DVD for Solaris 8 Software 2
  of 2 (2/02 SPARC Platform Edition).` (`INSERT`), and once the second CD is in, `Ready to Install
  1. Install Now 2. Start Over 3. Exit Installation What would you like to do [1]?` (1).
- After that answer the installer prints `Installing Solaris 8 packages (part 2)` and, a while
  later, the progress bar. `PROMPT_END` used to take any closing parenthesis as the end of a prompt
  (for `(y/n)`), so when the console went quiet on that line the scenario took it for a prompt,
  found none in its table (the answered menu, `... [1]? 1`, doesn't match: the table's patterns
  end at the question) and failed with `unknown prompt` (install matrix run 44533778163, the only
  failure of `sol8-ss5` so far; it depends on how long the line stays the last one). Now a closing
  parenthesis ends a prompt only after a choice such as `(y/n)` (`waits_for_input()`); the menu
  itself is answered whenever it is on the screen. The prompt endings of the passing 8 2/02 and 9
  9/05 runs' snapshots are the same under both rules. In both runs with the fix the progress
  bar came 4-4.5 s after that line (`serial.cast`), more than the 3 s of quiet `wait_prompt()` waits
  for, so the old rule would most likely have failed there again.

The SS-20 targets stay on 8 1/01 and the original 9 DVD: the later updates install there too (lab
runs below), but no faster (8 2/02 took 31 min against 24 for 8 1/01, and hung once), and the old
media have more passing runs and the stored disks of the weekly matrix. To run Web Start in the
lab's own QEMU (not through PVE), give the scenario `PROM_ENV=auto-boot?=false BOOT=c` (what `install.py` sets through `args` and attach
mode) and, for Solaris 8, `SWAPS="drive-scsi6=<Software 1 of 2> drive-scsi6=<Software 2 of 2>"`.

Lab runs (the lab image with the published pve-qemu-kvm 11.1.3-2+wsh22, 9G template, up to three
guests on the host at once, 2026-11-19); install = the Web Start scenario, boot = `solaris-boot-disk.py`
on the installed disk:

| Release | Machine | Install | Disk boot |
| --- | --- | --- | --- |
| 8 1/01 (Entire, both Software CDs) | SS-5, 256 MB | passed, 24.6 min | `SunOS sol8-ss5 5.8 Generic_108528-05 sun4m`, 2.4 min |
| 9 (the original DVD, End User) | SS-5, 256 MB | passed, 21.0 min | `SunOS sol9-ss5 5.9 Generic sun4m`, 3.7 min |
| 9 9/05 (End User) | SS-5, 256 MB | passed, 23.6 min | `SunOS sol9-ss5 5.9 Generic_118558-34 sun4m`, `/` 1126542 KB, 3.7 min |
| 9 9/05 (End User) | SS-20, 512 MB | passed, 23.3 min | `SunOS sol9-ss20 5.9 Generic_118558-34 sun4m`, 3.4 min |
| 8 2/02 (Entire, both Software CDs) | SS-5, 256 MB | passed through PVE (below); the lab runs found the three new screens | |
| 8 2/02 (Entire, both Software CDs) | SS-20, 512 MB | 1 of 2: the first hung after the mini-root's `Skipping interface le0` (no output for 30 min, Web Start never started); the second passed, 30.9 min | `SunOS sol8-ss20 5.8 Generic_108528-13 sun4m`, `/` 1237902 KB, 2.5 min |

Through PVE (the PVE test container from `e2e/pve/Dockerfile` with the lab, pve-qemu-kvm
11.1.3-2+wsh22, qemu-server 9.2.19+wsh1, pve-manager 9.2.31+wsh1):

| Run | Result | Time |
| --- | --- | --- |
| `install sol9-ss5 --check` | passed; login `root`/`wshlab`, the marker, `le0` 10.0.2.15/24 static | 29.8 min (install 1420 s, first boot 270 s, check 73 s) |
| `install sol8-ss5 --check` | passed; both Software CDs swapped in by the scenario, the same login, marker and network | 37.2 min (install 1897 s, first boot 216 s, check 97 s) |
| `pve_matrix.py install --only install-sol8-ss5` with the `PROMPT_END` fix (scratch `--disks`, pve-qemu-kvm 11.1.3-2+wsh22, another guest running), twice | passed both; after the answered "Ready to Install" the console stayed 4.0 and 4.5 s on `Installing Solaris 8 packages (part 2)` before the progress bar, and the scenario waited for the next prompt (`installation details`, 5-6 min later) | 34.6 min (install 1733 s, first boot 216 s, check 97 s); 36.7 min (1853 s, 217 s, 98 s) |
`pve_matrix.py install` installs both too (about 67 min more for the `install` choice, which needs
the 8 2/02 CDs and the 9 9/05 DVD in `--iso`). The same releases install on sun4u too: "Solaris 8
and 9 on sun4u" below. Not tried: `--ip dhcp`, `--disk-size 3G` and the
other network options with these two, and repeated runs of `sol9-ss5` (one PVE run, and one in the matrix). The SS-20 hang with 8 2/02 happened once in
two runs and wasn't diagnosed.

**Under the Sun PROM: `sol8-ss5-prom`.** The same 8 2/02 install on an SS-5 with `bios: ss5.bin`.
The Installation CD boots from the plain `scsi-cd` (no `cd_as_disk`), and the VM needs no `args`:
the Sun PROM honours the boot string that OpenBIOS drops. Two places in `solaris-webstart-serial.py`
differ (`sun_prom()`: a sun4m VM whose `BIOS` isn't OpenBIOS):

- After the mini-root copy the PROM resets and prints `Rebooting with command: .../sd@3,0:b` and
  `Boot device: ...sd@3,0:b`, then boots the mini-root by itself; `mini_root()` waits for that
  (`SUN_PROM_BOOT`) instead of a prompt and types nothing.
- After the installer's last Return the PROM resets, tries its default boot device (the network:
  `Boot device: /iommu/sbus/ledma@5,8400010/le@5,8c00000`, `Did not receive expected loopback
  packet`) and stops at `ok`. The SS-5 PROM has no `power-off`, so the scenario stops the VM there
  (`qm stop`), as after a sun4u install.

The first boot and the check are `sol251-ss5`'s Sun PROM paths in `_sparc32` (`No Keyboard`, `boot
disk`), unchanged. Through PVE (the PVE test container from `e2e/pve/Dockerfile` with the lab,
published pve-qemu-kvm 11.1.3-2+wsh26, qemu-server 9.2.19+wsh2, pve-manager 9.2.31+wsh4; up to three
other guests on the host, 2026-11-20):

| Run | Result | Time |
| --- | --- | --- |
| `install sol8-ss5-prom --check --export /mnt/os/disks` | passed; both Software CDs swapped in, `SunOS sol8-ss5-prom 5.8 Generic_108528-13 sun4m sparc SUNW,SPARCstation-5`, the marker, `/` 1237902 KB (713405 used) on `c0t3d0s0`, `/export/home` 5878709 KB, `le0` 10.0.2.15/24; stored disk and sidecar | 47.2 min (install 2439 s, first boot 240 s, check 115 s) |
| `boot-test sol8-ss5-prom --disk /mnt/os/disks/install-sol8-ss5-prom.raw` | passed | 2.2 min |

About ten minutes slower than `sol8-ss5` under OpenBIOS, most likely the busier host (one run each
on different days). `pve_matrix.py install` installs it too (about 47 min the first time, then a
boot test of its stored disk; the same 8 2/02 CDs in `--iso`). Not tried: a second run, Solaris 9 under `ss5.bin`, and the network options other than the
default static address.

### Solaris 8 and 9 on sun4u

`sol9-sun4u` (9 9/05, the DVD) and `sol8-sun4u` (8 2/02, the Installation CD and Software 1 of 2)
run the same `solaris-webstart-serial.py` on the sparc64 profile of `sol10-sun4u` (1024 MB, `sunhme`,
`vga: serial0`) with a blank 8 GiB disk on `ide0` and the media on `ide2`, End User. They need
`openbios-sparc64` with patch 0024 (pve-qemu-kvm 11.1.3-2+wsh23 or later); `sol9-sun4u` also needs
0025 (the ebus floppy node left out; without it 9's first boot panics in `fd`), in pve-qemu-kvm
11.1.3-2+wsh25 and later (`submodules/SPARC.md`, "Solaris 8 and 9 install targets on sun4u"). What the scenario
does differently on sun4u (`ARCH` sparc64 from the VM's config, `DISK=c0t0d0`):

- **Boot:** `_sparc32.prom_boot()` lets OpenBIOS boot by itself (`Trying cdrom:f...`/`disk:a`,
  from qemu-server's `-boot order=`) or, at `0 >` (`auto-boot?` false), types `boot cdrom:f` or
  `boot disk:a`. So `solaris-firstboot.py` and `solaris-boot-disk.py` serve the sun4u targets
  unchanged.
- **Answers:** the 64-bit question's default on sun4u is 1 (64-bit and 32-bit support), kept; the
  format question and the layout name `c0t0d0`.
- **Reboots:** with openbios-sparc64 patch 0030 Solaris's reboot resets the machine (the firmware's
  banner; `submodules/SPARC.md`, "The firmware reboot on sun4u"). After the installer's last
  Return the scenario stops the VM at that banner (`m.stop()`, i.e. `qm stop`; Solaris has synced
  the disk by then, and 9 would boot the DVD again), as `solaris10-install-sparc64.py` does;
  `install` ejects the media and sets `boot: order=ide0`. After 8's mini-root copy the firmware
  resets and stops at `0 >` (the VM's `args: -prom-env auto-boot?=false`, the target's
  `prom_env`), where the scenario boots `disk:b` (`resets` in `result.json`'s metrics counts the
  resets). With firmware before 0030 the reboot returns (`prom_reboot: reboot call returned!`, a
  panic, `EXIT`, `0 >`): the scenario stops the VM at that prompt at the end, and after 8's
  mini-root copy calls `lab.PveMachine.power_cycle()`: `qm stop`, then `qm start` with the serial
  console connected while it starts, the same terminal, step log and recordings (a marker "power
  cycle N" in the cast, `power_cycles` in `result.json`'s metrics, the second `qm start`'s output
  in `qm-start-2.log`). Only a VM the lab started is power-cycled; outside PVE (the lab's own QEMU)
  the scenario fails there with a message. Before 0030 a `reset-all` at the prompt didn't do
  either: the RAM kept its contents, and the mini-root's kernel panicked in `page_free`.
- **Media:** End User needs only Software 1 of 2 (the one `at: "scenario"` medium), put into `ide2`
  live when the mini-root's Web Start asks for the first Software disc.

Results through PVE (the PVE test container from `e2e/pve/Dockerfile` with the lab, published
pve-qemu-kvm 11.1.3-2+wsh23, qemu-server 9.2.19+wsh1, pve-manager 9.2.31+wsh1; "0025" = an
`openbios-sparc64` built from `openbios/` with 0001-0025 mounted over the package's; up to two guests
on the host at once, 2026-11-19):

| Run | Result | Time |
| --- | --- | --- |
| `install sol9-sun4u --check` (0025) | passed: the first boot reconfigures (`Configuring /dev and /devices`) without a panic, root/`wshlab`, the marker, `SunOS sol9-sun4u 5.9 Generic_118558-34 sun4u`, `/` 1126422 KB on `c0t0d0s0`, `hme0` 10.0.2.15/24, `boot: order=ide0`, `ide2` empty | 70.0 min (install 3559 s, first boot 401 s, check 215 s) |
| `install sol8-sun4u --check` (0025) | passed: one power cycle after the mini-root copy, Software 1 of 2 swapped in, `SunOS sol8-sun4u 5.8 Generic_108528-13 sun4u`, `/` 738902 KB, no `fdthree` warning in any phase | 56.9 min (2752 s, 378 s, 264 s) |
| `install sol8-sun4u --check` (the package's firmware) | passed; the `fdthree` warning in the install and first boot, as before | 53.4 min (2536 s, 382 s, 267 s) |
| `pve_matrix.py install --only install-sol8-sun4u` (pve-qemu-kvm 11.1.3-3+wsh13, qemu-server 9.2.20+wsh6, pve-manager 9.2.32+wsh10; 2026-11-22) | passed: one power cycle, `SunOS sol8-sun4u 5.8 Generic_108528-13 sun4u`; the stored disk `install-sol8-sun4u.raw` and its sidecar | 52.4 min (2489 s, 375 s, 262 s) |
| `install sol9-sun4u --check --export` (0025), a second run | passed, the same checks; the disk and its sidecar exported | 67.2 min (3393 s, 405 s, 217 s) |
| `matrix.py sparc64` (0025) | 9 of 9 passed: NetBSD 11.1 and 9.3, OpenBSD 8.0 and Debian 12 CDs, NetBSD 11.1 on `std` VGA, install, disk, virtio and idle | 18 min (the cases added up) |
| `matrix.py solaris10` (0025) | 2 of 2 passed: the DVD and the installed disk | 12 min (the cases added up) |
| `boot-test` of the stored disks (0025): `openbsd80-sun4u`, `netbsd111-sparc64`, `sol10-sun4u`, `tribblix-m34-sun4u` | 4 of 4 passed | 3.4, 1.7, 8.6, 25.5 min |
| unit tests (`test_targets.py` with `WebStartSun4u`, `test_stored_disks.py`, `test_dos.py`, `test_freedos.py`, `test_netbsd.py`, `test_vgatext.py`; Docker, `--network none`) | 149 passed, 2 skipped | 6 s |

So 0025 breaks none of the sun4u guests the lab runs (the last four rows, all with 0025; the CI
install matrix ran on the same host at the time). 0025 is published in pve-qemu-kvm 11.1.3-2+wsh25
(built after #350; its `openbios-sparc64` has no `fdthree` node), and on that package with no firmware
mounted `install sol9-sun4u --check` passed (74.2 min: install 3778 s, first boot 410 s, check 236 s;
the first boot reconfigured without a panic, no `fdthree` warning) and `boot-test` of the stored disk
passed (4.1 min), 2026-11-19; so `sol9-sun4u` no longer has `matrix_skip`, and the weekly matrix
boot-tests its stored disk. `sol8-sun4u` runs with the published packages and is installed by `pve_matrix.py install` (about 55
min the first time, then a boot test of its stored disk). Solaris 7 is the next section.

### Solaris 7 on sun4u

`sol7-sun4u` (7 3/99, End User) runs suninstall, `solaris-install-serial.py`, on the sparc64 profile
with 2048 MB, the CD on `ide2` and a 3 GiB disk on `ide0` with the SUN2.9G label (`sun_disk("3G",
bus="ide0")`: suninstall lists only labelled disks, and Solaris's `dad` driver takes the template's
label on the IDE disk as it is). The sun4m answers serve unchanged; what is new in the scenario:

- **The disk** is `DISK` (`c0t0d0`; default `c0t3d0`), in `disks()` and the target's `device`.
- **The end:** the installer ends at a root shell, as on sun4m; on sun4u `halt` returns to OpenBIOS's
  `0 >` (no power-off for Solaris), and `halt_sun4u()` stops the VM there. No reboot happens during
  the install, so no power cycle.
- **2048 MB:** with 1024 MB the kernel panicked as the package copy began in both installs
  (`panic[cpu0]/thread=70179200: segkp_badop`; `BAD TRAP: ... type=0x31 ... pkginstall`, an illegal
  access to a user address in `unix`); with 2048 MB the two installs that got that far copied
  the packages. Not diagnosed. A panic during the packages now fails the scenario at once (`PANIC`)
  instead of after the 7200 s wait for the postinstall phase.
- **F2 again (`KEY_RETRY=180`):** in two of the runs suninstall sat on a screen for 10 minutes after
  F2 (`Preserve Data?`, `Mount Remote File Systems?`), the kernel alive (hme0's `Link Up` every
  30 s). In the first, a second guest with the same address was on the bridge (`IP: Hardware address
  ... trying to be our address`), the second had no such message. `press_on()` sends F2 once more
  when the same screen is still up after 180 s (twice at most); the sun4m targets keep `KEY_RETRY=0`.
  The passing runs didn't need it, so the repeat itself is tested only by the unit test.
- **Slower CD boot:** IDE timeouts (`timeout: abort request ... reset bus`) and `Interrupt not seen
  after set_features` while the CD boots, about 4 minutes from the kernel banner to `Select a
  Language` (`FIRST_PROMPT_TIMEOUT=1200`). The installed system prints the same warning once.

The installed system boots the 64-bit kernel (`SunOS Release 5.7 Version Generic_106541-02 64-bit`);
the first boot and the check are `solaris-firstboot.py` and `solaris-boot-disk.py`, unchanged.

Through PVE (the PVE test container, published pve-qemu-kvm 11.1.3-2+wsh26, qemu-server 9.2.19+wsh2,
pve-manager 9.2.31+wsh4; up to three other guests on the host, 2026-11-20):

| Run | Result | Time |
| --- | --- | --- |
| `install sol7-sun4u`, 1024 MB | the screens answered, `c0t0d0` selected; `segkp_badop` panic at `Beginning Solaris software installation` | stopped at 7 min |
| the same, 1024 MB, a second run | `BAD TRAP ... pkginstall`, `panic[cpu0]: trap` at the same point | 6.9 min |
| install with 2048 MB for the install phase only, without `--check` | passed; the first boot (1024 MB) reached `console login:`, set the marker and network | 21.3 min (install 880 s, first boot 374 s) |
| `install sol7-sun4u --check --export`, 2048 MB (another guest with 10.0.2.15 on the bridge) | failed: no reaction to F2 on `Preserve Data?` for 10 min | 17.2 min |
| the same with `--ip 10.0.2.32`, alone on its address | failed: no reaction to F2 on `Mount Remote File Systems?` for 10 min | 16.9 min |
| the same with `KEY_RETRY=180` (`--ip 10.0.2.32`) | passed, no F2 repeated; `SunOS sol7-sun4u 5.7 Generic_106541-02 sun4u`, the marker, `/` 125103 KB, `/usr` 412907 KB (73% used), `/export/home` 1904237 KB on `c0t0d0`, `hme0` 10.0.2.32/24; stored disk and sidecar | 24.5 min (install 814 s, first boot 380 s, check 254 s) |
| `boot-test sol7-sun4u --disk /mnt/os/disks/install-sol7-sun4u.raw` | passed (`console login:` after 3.4 min) | 4.4 min |

Not tried: the 9G disk, a 32-bit-only install (64-bit off), `--ip dhcp` and the other network options,
and 2.6 or 2.5.1 with this target (they have their own, below).

### Solaris 2.6 and 2.5.1 on sun4u

`sol26-sun4u` (2.6 5/98) and `sol251-sun4u` (2.5.1 11/97) run the same suninstall as `sol7-sun4u` on
the sparc64 profile with 1024 MB (both kernels are 32-bit), the CD on `ide2` as an IDE CD-ROM (no
`as_disk`, unlike 2.5.1 on sun4m) and the SUN2.9G-labelled 3 GiB disk on `ide0`. Their kernels need
OpenBIOS 0036 (2.6), 0037 and 0038 (2.5.1) on top of 0031, and the installed systems 0039 (the root
named `SUNW,Ultra-5_10`, so that the installer adds the platform packages; `submodules/SPARC.md`,
"Solaris 2.6 and 2.5.1 on sun4u: the kernels"). `pve-qemu-kvm` 11.1.3-4+wsh15 is the first package
with them; both targets are in the install matrix (no `matrix_skip`). What the scenario
needed for them:

- **Console messages over the screens.** Both releases' `hme` driver prints `Using Internal
  Transceiver` and `Link Up` while the installer runs, at times every few seconds for minutes. They
  landed on `Select Disks` over the `[ ] c0t0d0` entry, and on `Preserve Data?` they scrolled the title
  off the terminal, so the scenario saw no screen. The installer doesn't redraw on Ctrl-L. So the
  scenario now also reads the screens from the serial stream since its last F2 (`f2_cursor`): a title
  drawn there counts as the next screen when the terminal shows none (`drawn_title()`), and the disk
  entry is taken as drawn when it is hidden (`disks()`).
- **A slow preinstall phase.** After the last `Confirm Information` 2.6 printed its preinstall and begin
  script lines for over 180 s before the next screen; with `KEY_RETRY` the scenario found no screen
  title and gave up. `press_on()` now waits again without F2 while no screen is up and the installer
  wrote something besides console messages; with nothing but console messages since F2 the screen is
  the old one, scrolled, and F2 goes again.
- **The prompt after `halt`.** OpenBIOS's prompt shows the stack depth, and 2.6's `halt` returns with
  14 cells on it: `e > `, not `0 > `. `halt_sun4u()` takes any depth.
- **Warnings that cost nothing:** the 8042 node's (`Out of range register specification from device
  node <8042>`, `kd_attach regs map setup 2nd failed`) and, on 2.6, the IDE timeouts on the way to the
  first prompt that Solaris 7 prints too.

Through PVE (the PVE test container with the published pve-qemu-kvm 11.1.3-4+wsh12, qemu-server
9.2.20+wsh7, pve-manager 9.2.32+wsh12, and `openbios-sparc64` built from `openbios/` with 0001-0034 and
0036-0039 mounted over the package's; other guests on the host, load average 11-15 on 14 cores; 2026-11-23):

| Run | Result | Time |
| --- | --- | --- |
| `install sol26-sun4u --check --export` (`pve_matrix.py install --reinstall`), first runs with 0036-0038 | failed in the scenario on the console messages, the preinstall phase and the prompt after `halt` (the bullets above), one after the other | |
| the same, scenario fixed, 0036-0038 | install passed; the first boot from the IDE disk stopped after the boot block (`krtld: error during initial load/link phase`): the platform packages were missing, hence 0039 | install 20.5 min |
| the same with 0036-0039 | passed: `SunOS sol26-sun4u 5.6 Generic_105181-05 sun4u sparc SUNW,Ultra-5_10`, the marker, `/` 87586 KB (31% used), `/usr` 237749 KB (73%), `/export/home` 2146879 KB on `c0t0d0`, `hme0` 10.0.2.15/24; stored disk and sidecar written | 28.0 min (install 1026 s, first boot 378 s, check 261 s) |
| `install sol251-sun4u --check --export`, first runs with 0036-0038 | failed in the scenario on the console messages over the disk list (the first bullet above) | |
| the same with 0036-0039 | passed: suninstall, the packages, then the CD's Maintenance Update (`Installing SUNWpatch.sun4u`, `Building package data base`, about 47 minutes of the install); `SunOS sol251-sun4u 5.5.1 Generic_105428-01 sun4u sparc SUNW,Ultra-5_10`, the marker, `/` 127229 KB (22%), `/usr` 111589 KB (86%), `/export/home` 2184383 KB on `c0t0d0`, `hme0` 10.0.2.15/24; `init 5` ends QEMU; stored disk and sidecar written | 66.8 min (install 3456 s, first boot 311 s, check 223 s) |
| `boot-test sol26-sun4u` and `boot-test sol251-sun4u` on the stored disks | passed (`console login:` after 3.4 and 3.0 min) | 4.3 and 3.9 min |

With the published packages (the PVE test container built from them: pve-qemu-kvm 11.1.3-4+wsh15, whose
`/usr/share/kvm/openbios-sparc64` is the patched one, `SUNW,Ultra-5_10` and `aligned-allocator` in it;
qemu-server 9.2.20+wsh7, pve-manager 9.2.32+wsh12; nothing mounted over the package; host builds running
niced beside it, load average 22-43 on 14 cores; 2026-11-24):

| Run | Result | Time |
| --- | --- | --- |
| `boot-test sol26-sun4u --disk <disks>/install-sol26-sun4u.raw` | passed: banner after 52 s, `console login:` after 4.5 min, `SunOS sol26-sun4u 5.6 Generic_105181-05 sun4u sparc SUNW,Ultra-5_10`, the marker, power-off | 5.8 min |
| `boot-test sol251-sun4u --disk <disks>/install-sol251-sun4u.raw` | passed: banner after 41 s, `console login:` after 4.1 min (the IDE timeouts on the way), `SunOS sol251-sun4u 5.5.1 Generic_105428-01 sun4u sparc SUNW,Ultra-5_10`, the marker, power-off | 5.3 min |

Not tried: the 9G disk, more or less memory, the network options other than the default static address,
an install with the published packages (the stored disks were installed with 0036-0039 mounted on
+wsh12), and a boot with firmware older than +wsh15 (which can't work: 0036-0039 are needed by the
installed systems as by the CDs).

### Solaris 2.4 and 2.5.1

`sol24-ss5` (2.4 Hardware 3/95) and `sol251-ss5` (2.5.1 11/97) boot their installer only from a CD
that answers as a disk, and 2.4 (until pve-qemu-kvm 11.1.3-2+wsh22, whose OpenBIOS 0019-0022 boot
it: "Older Sun releases") only under a Sun PROM: SS-5 with `bios: ss5.bin`, and the CD's
medium has `as_disk: True`, which `install.drive_volume()` turns into qemu-server's `cd_as_disk=1`
(`scsi6: local:iso/<cd>.iso,media=cdrom,cd_as_disk=1`, a read-only `scsi-hd` on target 6;
`submodules/SPARC.md`, "Supported profiles"). `targets.problems()` allows `as_disk` only on a sparc32
SCSI drive at the start (a medium swap would wait for the next start). `pve_vars()` sets
`CDROM_AS=hd` for such a drive, so `solaris-install-serial.py` answers the installer as in the
lab's own QEMU; the installer also lists the CD as `c0t6d0`, and `disks()` marks only `c0t3d0`.
Two things were new through PVE:

- **No keyboard under the Sun PROM.** qemu-server starts a VM with `vga: serial0` with
  `-nographic`, which leaves out the Sun keyboard: the PROM says `SPARCstation 5, No Keyboard` and
  reads ttya. `prom_boot()` typed `ttya io` on the keyboard and waited 30 s for `ok` in vain (the
  first run); it now types it only after `Keyboard Present` (the lab's own QEMU, `-vga none`).
  Under PVE the PROM tries the network first (`Boot device: .../le@5,8c00000`, `Can't open boot
  device`) and stops at `ok`, where `prom_boot()` types `boot cdrom` (the PROM's `cdrom` alias is
  `sd@6,0:d`, which works for the `scsi-hd` too) and later `boot disk`.
- **2.4's date screen:** it shows 2026 as `Year (4 digits) : 1912`, and confirming that ends in
  `Unable to convert given date` and the time zone screen again, in a loop. `date()` types the
  4-digit year (`YEAR`, default the host's) over the highlighted field when it shows a year before
  1970; 2.4 then takes 2026. 2.5.1 and later take the year they show.

2.5.1's install ends with its Maintenance Update (`install_mu`: "It will take from 15 to 45 minutes
to determine the file system space requirements"), so the root shell comes up to an hour after the
postinstall phase starts: the target sets `FINISH_TIMEOUT=6000` (the scenario's wait for the shell,
1800 s by default; the first run through PVE hit that). The first boot and the check are those of
2.6 (`solaris-firstboot.py`, `solaris-boot-disk.py`, a static address only: there is no DHCP client
before 2.6). 2.4 has no `hostname` command (the check's `hostname` prints `not found`; the marker
has the name), and its auto-layout makes small slices on the 3G disk: `/` 25 MB, swap 129 MB,
`/usr` 108 MB (85% used), `/export/home` 2.4 GB.

Tested in the PVE test container on the lab host, 2026-11-18: the published packages (pve-qemu-kvm
11.1.3-2+wsh16, pve-manager 9.2.30+wsh1) with qemu-server built from this branch (9.2.18 plus
`cd_as_disk`), each with `--check`. Another agent's container ran on the host at the same time, and
some runs overlapped (noted):

| Run | Result | Time |
| --- | --- | --- |
| `install sol251-ss5` (first) | failed: `ttya io` on a keyboard the VM doesn't have (above) | 1 min |
| `install sol251-ss5` | failed in the Maintenance Update: no root shell within the scenario's 1800 s (above) | 34 min |
| `install sol24-ss5` (first) | stopped by hand in the date loop (above) | 6 min |
| `install sol24-ss5` (alongside the 2.5.1 run) | passed; `SunOS sol24-ss5 5.4 generic sun4m sparc`; the marker; `le0 10.0.2.15 netmask ffffff00`; the slices above | 9.3 min (install 315 s, first boot 141 s, check 85 s) |
| `install sol251-ss5` (`FINISH_TIMEOUT=6000`; the sol26 run overlapped its first 15 min) | passed; `SunOS sol251-ss5 5.5.1 Generic_103640-12 sun4m sparc SUNW,SPARCstation-5`; the marker; `/` 123024 KB, `/usr` 110550 (87% used), `/export/home` 2313661; `le0 10.0.2.15 netmask ffffff00`; the finished VM has `scsi6: none,media=cdrom` | 43.9 min (install 2336 s, of which ~18 min without console output in the Maintenance Update; first boot 182 s, check 98 s) |
| `install sol26-ss5` (regression of the scenario changes, alongside 2.5.1) | passed | 14.4 min (install 518 s, first boot 218 s, check 111 s) |
| `matrix.py smoke` (lab image with the branch's `e2e/sparc`: the 2.5.1 disk under `ss5.bin` takes the `Keyboard Present` path) | 3/3 passed | 161 s, 111 s, 66 s |
| `solaris-boot-cd.py` 2.5.1 CD, `CDROM_AS=hd`, SS-20 with the SS-20 PROM (lab image) | passed (installer's first question) | 57 s |

`pve_matrix.py install` runs every automated target, so the `install` choice of the `sparc lab`
workflow now also needs the 2.4 and 2.5.1 CDs and takes about 55 min longer; with a published
qemu-server that lacks `cd_as_disk` both cases fail at VM creation (`cd_as_disk: property is not
defined in schema`). Not tried: a 9G disk, `--user`, `--data-disk` and the network options other
than the default static address with 2.4 and 2.5.1; Solaris 2.4 on SS-20; a second run of each
(one passing run each so far).

### Matrix holes: 2.5.1 on the SS-20, 2.6 and 7 on the SS-10

`sol251-ss20` is `sol251-ss5` on an SS-20 under OpenBIOS (512 MB, one CPU): OpenBIOS boots the
2.5.1 CD as a disk and the installed system, so the SS-20 needs no Sun PROM (the SS-20 PROM wasn't
tried). The same `FINISH_TIMEOUT=6000` for the Maintenance Update. `sol26-ss10` and `sol7-ss10` are
the SS-20 targets on QEMU's SS-10 (OpenBIOS, 512 MB, one CPU, the 3G disk); `solaris-install-serial.py`
needed no change for any of them.

Tested in the PVE test container on the lab host with the published packages (pve-qemu-kvm
11.1.3-2+wsh25, qemu-server 9.2.19+wsh2, pve-manager 9.2.31+wsh4), 2026-11-19, each with
`--check --export /mnt/os/disks` and then `boot-test` of the stored disk; up to five guests ran on
the host at once (these three, a `sol9-sun4u` install and a boot test), so the times are upper bounds:

| Run | Result | Time |
| --- | --- | --- |
| `install sol251-ss20 --check --export` | passed; `SunOS sol251-ss20 5.5.1 Generic_103640-12 sun4m sparc SUNW,SPARCstation-20`; the marker; stored disk and sidecar | 46.6 min (install 2517 s, most of it the Maintenance Update; first boot 171 s, check 87 s) |
| `install sol26-ss10 --check --export` | passed; `SunOS sol26-ss10 5.6`; the marker; stored disk and sidecar | 15.6 min (install 562 s, first boot 229 s, check 120 s) |
| `install sol7-ss10 --check --export` | passed; `SunOS sol7-ss10 5.7 Generic_106541-02 sun4m sparc SUNW,SPARCstation-10`; the marker; stored disk and sidecar | 12.3 min (install 400 s, first boot 218 s, check 96 s) |
| `boot-test` of each stored disk | `sol251-ss20` passed; `sol26-ss10` passed; `sol7-ss10` passed | 1.5 min; 2.1 min; 1.9 min |

Not tried: DHCP, `--user`, the 9G disk, `--data-disk` and `--post-install` with these three; more
than one CPU; a second run of each.

### Older Sun releases: Solaris 2.1-2.5, SunOS 4.1.2-4.1.3_U1B

The sun4m floor by machine (Sun's documents): the SS-10 from SunOS 4.1.3 and Solaris 2.1, the SS-20
from 4.1.3_U1B and 2.3, the SS-5 from 4.1.3_U1B (with the kernel patch 101508) and 2.3 Edition II.
Each release was first booted and installed in the lab's own QEMU (pve-qemu-kvm 11.1.3-2+wsh21),
then the ones that installed got targets:

- **`sol23-ss5`, `sol23-ss20`** (Solaris 2.3 Edition II): only from a CD that answers as a disk, as
  2.4; first only under a Sun PROM (`ss5.bin`, or `ss20_v2.25_rom` with qemu-server's `-cpu
  TI-SuperSparc-50`), under OpenBIOS since openbios 0019-0022 (pve-qemu-kvm 11.1.3-2+wsh22; the
  targets have OpenBIOS since, below). 2.3's sysidtool asks one question per screen (a sentence, a box with a field or a
  menu whose cursor is `>`, "Press Return to continue."), with no title line, so
  `solaris-install-serial.py` has a second path for it (`OLD_SCREENS`, `old_select()` by menu
  label, `old_date()`): host name, networked yes, the address, name service none, no subnets,
  Europe / Middle Europe, the date (the 19xx year typed over as for 2.4; Return walks the five
  fields and takes the form after the last), then the installer's own menus: Quick Install, End
  User (already marked), `c0t3d0` (already marked), Begin Install. It ends with "Installation
  successful..." and reboots by itself; the Sun PROM then fails its network boot and stops at `ok`
  (OpenBIOS prints its banner and boots the disk), where the scenario stops the VM. First boot: the root password on its own screen ("What is your
  root password?", "Please re-enter your root password."), handled by `_sparc32.login()`, which
  also answers a forced "Choose a new password." at the first login with the same password (seen
  once by hand, not in the scripted runs). `init 5` reboots on 2.3 instead of powering off:
  `power_off()` takes "rebooting..." like "Program terminated" and waits for `ok`.
- **`sol24-ss5`, `sol24-ss20`** (Solaris 2.4 HW 3/95) and **`sol22-ss10`** (Solaris 2.2, on the
  SS-10, its only sun4m machine): OpenBIOS with 0019-0022 and the CD as a disk. 2.4 has 2.6's
  screens (`sol24-ss5` had `ss5.bin` until +wsh22, "Solaris 2.4 and 2.5.1"); 2.2 takes the 2.3 path
  of `solaris-install-serial.py` (it makes the file systems on a cleared screen instead of 2.3's
  progress screen). 2.2's CD image is `Solaris_2.2.img` (checked against the md5 that came with the copy).
- **`sol25-ss5`, `sol25-ss20`** (Solaris 2.5 HW 1/96): OpenBIOS on both machines, the CD as a disk
  (from a `scsi-cd` the kernel hangs after its banner, as 2.5.1's did); the screens are 2.6's, and
  there is no Maintenance Update.
- **`sol21-ss10`** (Solaris 2.1, the first sun4m release, SS-10 only): OpenBIOS with 0019-0022 and
  the CD as a disk, as `sol22-ss10`. `solaris-install-serial.py` takes the 2.3 path through
  sysidtool, then 2.1's own suninstall menus (`suninstall_21()`: Standalone Quick Install, the
  End-User Cluster on `c0t3d0`, reboot after the install: yes). Its kernel needs the QEMU fix
  `wsh/0047` (pve-qemu-kvm 11.1.3-2+wsh29 and later; without it QEMU stops after the device
  configuration, `Trap 0x21`), so it was catalogue only until that package was published; results
  through PVE below the OpenBIOS targets.
- **`sunos413u1b-ss5`, `sunos413u1b-ss20`** (SunOS 4.1.3_U1B): the `sunos414-ss5` target with
  another CD and, for the SS-20, its profile: the same three scenarios unchanged, 64 MB during the
  install, OpenBIOS. The CD is a plain image with 2048-byte sectors (no `--convert`). Without patch
  101508 the CD's and the installed kernel run on the SS-5 (`SunOS Release 4.1.3_U1 (MUNIX) #2`).
  The SS-10 also installs it in the lab (152 s), not made a target.
- **`sunos412-ss600mp`** (SunOS 4.1.2, Solaris 1.0.1, the SPARCserver 600MP, one CPU): the
  `sunos414-ss5` target with its own CD (2048-byte sectors, no `--convert`), the SS-600MP at 256 MB
  and `SERIAL_7BIT=1` in every phase: its `getty` sends even parity in bit 7, which the harness masks
  before the terminal (`serial.raw` keeps it). The scenarios boot the ESP by its path on the machine
  (`_sparc32.esp()`: `/iommu/sbus/dma/esp` on the SS-600MP, openbios 0028). It needs pve-qemu
  `wsh/0063`-`0065` and openbios 0028 (pve-qemu-kvm 11.1.3-3+wsh13 and later) and qemu-server's
  SS-600MP profile (OpenBIOS only, one CPU, up to 1024 MB; `submodules/SPARC.md`, "Supported
  profiles"), so it was catalogue only until both existed; results through PVE below the OpenBIOS
  targets.
- **`sunos412-ss600mp-prom`**: the same install under Sun's own 600MP PROM (`bios: ss600mp.bin`), 256 MB
  in every phase (the PROM's self test loops with 64 or 128 MB) and no `prom_env`. It needs pve-qemu
  `wsh/0188` (QEMU gives the PROM a configuration with `auto-boot?` and `diag-switch?` false, so every
  start stops at `ok` on ttya without a keyboard), qemu-server with `ss600mp.bin` in the SS-600MP
  profile and the image in `/usr/share/kvm` (no package has it; `wsh-sun-proms` knows its hash).
  sunos-install-serial.py's Sun PROM path unchanged: `boot cdrom`, the miniroot booted by the PROM from
  its reboot string, `boot disk` for the first boot and the check. Results through PVE below.
- **`sunos413-ss10`** (the original SunOS 4.1.3, Solaris 1.1, SS-10 only): the `sunos414-ss5`
  target with its own CD (`Solaris_1.1.img`, 2048-byte sectors, no `--convert`) and the SS-10's
  profile (256 MB, one CPU, OpenBIOS): the same three scenarios unchanged, 64 MB during the install.
  Its kernel needs the QEMU fix `wsh/0049` (pve-qemu-kvm 11.1.3-2+wsh31 and later; without it the
  CD's kernel panics in its VME probe, `BAD TRAP: cpu=0 type=29`), so it was catalogue only until
  that package was published; results through PVE below the OpenBIOS targets.

Results in the lab's own QEMU (serial console, Sun-labelled 3G disk, `solaris-boot-cd.py` for "CD
boots", the install scenarios for "installs", their first boot and check for "boots"):

| System | Machine, firmware | CD boots | Installs | Disk boots | Stop point / note |
| --- | --- | --- | --- | --- | --- |
| Solaris 2.3 Ed. II | SS-5, OpenBIOS (CD or as a disk) | no | | | `Unhandled Exception 0x00000009`, PC `0xffd076c8`, right after the boot block (`(is ?`); fixed by openbios 0019-0022 |
| Solaris 2.3 Ed. II | SS-5, OpenBIOS with openbios 0019-0022, CD as a disk | yes | yes (5.5 min) | yes (login in 54 s) | `SunOS solaris 5.3 Generic_101498-02 sun4m`; from a `scsi-cd`: `cannot mount root`, as under `ss5.bin` |
| Solaris 2.4 HW 3/95 | SS-5, OpenBIOS with openbios 0019-0022, CD as a disk | yes | yes (4.2 min) | yes (69 s) | `SunOS solaris 5.4 generic sun4m`; before 0022 a panic in OpenBIOS in 2 of 4 boots |
| Solaris 2.3 Ed. II | SS-5, `ss5.bin`, CD as a disk | yes (48 s) | yes (6.0 min) | yes | `SunOS sol23-ss5 5.3 Generic_101498-02 sun4m` |
| Solaris 2.3 Ed. II | SS-5, `ss5.bin`, `scsi-cd` | kernel only | | | `panic: vfs_mountroot: cannot mount root` |
| Solaris 2.3 Ed. II | SS-20, `ss20_v2.25_rom` -50, 512 MB, CD as a disk | yes (47 s) | yes (5.3 min) | yes | `SunOS sol23-ss20 5.3 Generic sun4m` |
| Solaris 2.5 HW 1/96 | SS-5, OpenBIOS, `scsi-cd` | kernel only | | | hangs after the banner (the spinner turns) |
| Solaris 2.5 HW 1/96 | SS-5, OpenBIOS, CD as a disk | yes (50 s) | yes (4.6 min) | yes | `SunOS sol25-ss5 5.5 Generic sun4m sparc SUNW,SPARCstation-5` |
| Solaris 2.5 HW 1/96 | SS-5, `ss5.bin`, CD as a disk | yes (55 s) | not tried | | |
| Solaris 2.5 HW 1/96 | SS-20, OpenBIOS, 512 MB, CD as a disk | yes | yes (4.7 min) | yes | `SunOS sol25-ss20 5.5 Generic sun4m sparc SUNW,SPARCstation-20` |
| SunOS 4.1.3_U1B | SS-5, OpenBIOS, 64 MB | yes | yes (139 s) | yes (256 MB) | `SunOS sunos413 4.1.3_U1 2 sun4m` |
| SunOS 4.1.3_U1B | SS-20, OpenBIOS, 64 MB | yes | yes (153 s) | yes (512 MB) | |
| SunOS 4.1.3_U1B | SS-10, OpenBIOS, 64 MB | yes | yes (132 s) | not tried | |
| Solaris 2.1 | SS-10, OpenBIOS | no | | | `Unhandled Exception 0x00000009` as 2.3 |
| Solaris 2.1 | SS-10, OpenBIOS with openbios 0019-0022, CD as a disk | kernel only | | | after device configuration `qemu: fatal: Trap 0x21 (Instruction Access Error) while interrupts disabled` (also `-cpu TI-SuperSparc-40`) |
| Solaris 2.1 | the same with a QEMU change (a local build of 11.1.3 with wsh/0001-0041; `submodules/SPARC.md`) | yes (52 s) | yes (5.0 min; 2.1's suninstall: Standalone Quick Install, End-User Cluster) | yes | `SunOS sol21-ss10 5.1 Generic sun4m sparc`; `/opt` and `/export/home` not mounted at boot (by hand they mount) |
| Solaris 2.1 | SS-20, `ss20_v2.25_rom` -50, CD as a disk, 256 or 64 MB | kernel only | | | `BAD TRAP: type=9 ... kernel read fault at addr=0x0`, `panic: Data fault` in `get_neighbors` (from `impl_init_tree`): a strcmp on the name of the SBus node the PROM makes, without a name, for QEMU's DBRI stub in slot e. `ss10_v2.25_rom` on the SS-20 the same |
| Solaris 2.1 | SS-20, `ss10_v2.25_rom` -50 ("SPARCstation 10BSX"), 256 MB, CD as a disk, `PROM_NAME_UNNAMED=1` | kernel only | | | with the node named the kernel gets as far as under OpenBIOS: `Trap 0x21` at `pc f0014768`; the installed disk too |
| Solaris 2.1 | the same with the QEMU change | yes | yes (4.9 min, `solaris-install-serial.py`) | yes (first boot 1.4 min, check 1.3 min) | `SunOS sol21-ss10 5.1 Generic sun4m sparc`; the OpenBIOS-installed disk boots there too, and `ss20_v2.25_rom` boots the PROM-installed one (2026-11-20) |
| Solaris 2.1 | SS-10, OpenBIOS, 2 CPUs, the QEMU change | kernel only | | | the installed disk: `Trap 0x21` at `pc fbe78060`, called from `cpu_startup` (the second CPU's start); not traced |
| Solaris 2.2 | SS-10, OpenBIOS, CD as a disk | no | | | `Unhandled Exception 0x00000009` |
| Solaris 2.2 | SS-10, OpenBIOS with openbios 0019-0022, CD as a disk | yes | yes (the 2.3 path) | yes | `SunOS solaris 5.2 Generic sun4m` |
| Solaris 2.2 | SS-20, `ss20_v2.25_rom` -50, CD as a disk | kernel only | | | the same `BAD TRAP: type=9` and `panic: Data fault` (the unnamed node) |
| Solaris 2.2 | the same with `PROM_NAME_UNNAMED=1` (QEMU 11.1.3 with wsh/0001-0041, no other change) | yes (55 s) | not tried | | 2026-11-20 |
| SunOS 4.1.3 | SS-10, OpenBIOS, 64 or 32 MB, also `-cpu TI-SuperSparc-40` | kernel only | | | `BAD TRAP: cpu=0 type=29` (data access error) after `SUNW,fdtwo0`, where 4.1.3_U1B goes on to its munixfs root: a probe read of physical `0xd.0108_0000`, where QEMU has nothing (`submodules/SPARC.md`) |
| SunOS 4.1.3 | SS-10, OpenBIOS, 64 MB (256 MB after the install), QEMU 11.1.3 with wsh/0001-0050 (`wsh/0049`: a bus error on a SuperSPARC load takes trap 0x09) | yes | yes (124-138 s) | yes (256 MB) | `SunOS sunos413 4.1.3 3 sun4m`, the 4.1.4 scenarios unchanged, four passes (2026-11-20); target `sunos413-ss10` since pve-qemu-kvm 11.1.3-2+wsh31 (through PVE below) |
| SunOS 4.1.3 | SS-20, OpenBIOS | kernel only | | | the same |
| SunOS 4.1.3 | SS-20, `ss20_v2.25_rom` -50, 64 MB | kernel only | | | `BAD TRAP: cpu=0 type=9` |
| SunOS 4.1.2 | SS-600MP, OpenBIOS | no | | | the kernel loads (`Boot: vmunix`), then `Unhandled Exception 0x00000029` before its banner |
| SunOS 4.1.2 | SS-600MP, OpenBIOS with openbios 0028, 64 MB (256 MB after the install), QEMU 11.1.3 with wsh/0001-0060 and wsh/0063-0065 (the VMEbus interface registers, the lance's lebuffer) | yes | yes (109-166 s) | yes (256 MB) | `SunOS sunos412 4.1.2 1 sun4m`, the 4.1.4 scenarios with the ESP under `dma` and `SERIAL_7BIT=1`; `le0` answers ping with `NET=user`; with 2 CPUs CPU 1 panics in `check_cpuid` (the Ross module ID in the MMU control register, `submodules/SPARC.md`) (2026-11-21) |

The SS-10 Sun PROM doesn't run on QEMU's SS-10 ("SS-10 and SS-20" in `submodules/SPARC.md`), so
2.1, 2.2 and 4.1.3 had OpenBIOS on the SS-10 or the SS-20 PROM on the SS-20 (they predate the
SS-20). Not tried: 2.3 under OpenBIOS with a framebuffer console, 2.5 SS-5 installs under `ss5.bin`,
2.6-era tricks for 2.1/2.2 (other `-cpu` models on the SS-20 PROM), 4.1.2 on the SS-10.

**`sunos412-ss600mp` through PVE** (the PVE test container from `e2e/pve/Dockerfile` with the lab,
`PACKAGES=mixed`: the published pve-qemu-kvm 11.1.3-3+wsh14 and libpve-storage-perl 9.1.18+wsh2, with
qemu-server and pve-manager built from the branch that adds the SS-600MP profile), 2026-11-22:

| Run | Result | Time |
| --- | --- | --- |
| `install sunos412-ss600mp --check` (VM 1) | passed; `SunOS sunos412 4.1.2 1 sun4m`; the marker; `le0` with `inet 10.0.2.15 netmask ffffff00`; the finished VM `machine: SS-600MP`, `memory: 256`, `scsi6: none,media=cdrom`, `boot: order=scsi3` | 6.7 min (install 151 s, first boot 165 s, check 61 s) |
| `install sunos412-ss600mp --check` (VM 2, the final packages: the profile at 1024 MB) | passed; the same | 6.5 min (135 s, 168 s, 64 s) |
| VM 1's disk, `sunos-boot-disk.py` at 512, 1024 and 2048 MB (the profile's limit lifted in the container) | passed each: `mem = 507772K`, `1032060K`, `2080636K` | 50-66 s each |
| the profile's API checks of `sparc-profiles.spec.ts` as `qm create`/`qm showcmd` (serial0, cg3, TCX and `nvram0` started frozen in QEMU; the refusals; an SS-20 with 2 CPUs changed to SS-600MP) | 17/17 passed | |
| unit tests (`test_targets.py`) | passed | |

Again with the published packages only (the same container, `PACKAGES=repo`, built `--no-cache`:
pve-qemu-kvm 11.1.3-4+wsh4, qemu-server 9.2.20+wsh7 and pve-manager 9.2.32+wsh11, which have the
SS-600MP profile), `pve_matrix.py install --only install-sunos412-ss600mp` into an empty `--disks`,
2026-11-22: passed in 6.2 min (install 143 s, first boot 150 s, check 51 s). It is the source of the
gallery's `sunos412-*-ss600mp` recordings ("Recordings in the docs").

**`sunos412-ss600mp-prom` through PVE** (the lab's PVE container image with the published packages,
qemu-system-sparc built from the series to `wsh/0189` and qemu-server's `Machine.pm` and `QemuServer.pm`
with `ss600mp.bin` copied over theirs, the PROM image in `/usr/share/kvm`), 2026-11-26:

| Run | Result | Time |
| --- | --- | --- |
| `install sunos412-ss600mp-prom --check` (VM 9601, first) | install passed (154 s: `No Keyboard`, `ok`, `boot cdrom`, the miniroot booted by the PROM, Quick install, `ok` after the reboot); the first boot then saw no console output for 4 minutes (the PROM at its `ok`, progress bytes `0xaa 0xaa`), stopped by hand; a `qm start` of the same VM by hand printed the banner and `ok` | |
| `install sunos412-ss600mp-prom --check` (a new VM 9601) | passed; `SunOS sunos412 4.1.2 1 sun4m`, the marker, `le0` 10.0.2.15; the finished VM `bios: ss600mp.bin`, `scsi6: none,media=cdrom`, `boot: order=scsi3` | 6.3 min (install 145 s, first boot 159 s, check 57 s) |
| `install sunos412-ss600mp-prom --check` (again, a new VM 9601) | passed; the same | 6.2 min (142 s, 160 s, 58 s) |
| the SS-600MP cases of `sparc-profiles.spec.ts` against that node | 12 passed, 1 skipped (the older qemu-server's refusal) | |
| unit tests (`test_targets.py`) | 137 passed | |

On the cg3 (the stored disk in the lab's own QEMU, `fb-bell.py GUEST=sunos4 MACHINE=SS-600MP
VGA=cg3`, console on the framebuffer and the Sun keyboard): `boot disk:a -s` boots 4.1.2 to its
single-user shell, which answers, and BEL comes back (passed, 96 s). The kernel prints `No default
frame buffer found` and attaches no `cgthree`, so the text on the screen is the PROM's terminal
(OpenBIOS) drawing what the kernel hands the romvec, not a SunOS frame buffer driver; the first
keys typed after the shell came up were lost once. So the gallery has the serial console only.

Not tried: `--user`, `--gateway`, the 9G disk, a boot test of the stored disk, multi-user on the
framebuffer console, TCX.

The rows "with openbios 0019-0022" ran the lab image of the published package with a patched
`openbios-sparc32` mounted over `/usr/share/kvm/openbios-sparc32`, one run each (the 2.3 install
with 0019-0021 before 0022 existed; 2.4, the disk boots and 2.2 with 0019-0022, 2.2's second
install with the image `openbios/Dockerfile` builds from 0001-0023); `solaris-install-serial.py` and
`solaris-boot-disk.py` with `CDROM_AS=hd` (and `MACHINE=SS-10` for 2.2). With them the scenarios
take OpenBIOS's side of 2.3's reboots (the end of the install and `init 5`: OpenBIOS's banner
instead of the Sun PROM's `ok`) and 2.2's install (it makes the file systems on a cleared screen
instead of 2.3's progress screen). Through PVE with the published package that has the patches: the
next table but one.

Through PVE (the PVE test container on the lab host, pve-qemu-kvm 11.1.3-2+wsh21, qemu-server
9.2.19+wsh1, pve-manager 9.2.31+wsh1; up to three guests at a time, another agent's runs on the host
too), each `lab.py install <target> --check`, 2026-11-19:

| Run | Result | Time |
| --- | --- | --- |
| `install sol23-ss5` | passed; `SunOS sol23-ss5 5.3 Generic_101498-02 sun4m sparc`; the marker; `le0 10.0.2.15 netmask ffffff00`; the finished VM `bios: ss5.bin`, `scsi6: none,media=cdrom` | 10.8 min (install 381 s, first boot 156 s, check 96 s) |
| `install sol23-ss20` | passed; `SunOS sol23-ss20 5.3 Generic sun4m sparc`; `bios: ss20_v2.25_rom`, 512 MB | 10.1 min (336 s, 157 s, 97 s) |
| `install sol25-ss5` | passed; `SunOS sol25-ss5 5.5 Generic sun4m sparc SUNW,SPARCstation-5` | 8.6 min (260 s, 160 s, 80 s) |
| `install sol25-ss20` | passed; `SunOS sol25-ss20 5.5 Generic sun4m sparc SUNW,SPARCstation-20` | 8.6 min (262 s, 164 s, 78 s) |
| `install sunos413u1b-ss5` | passed; `SunOS sunos413 4.1.3_U1 2 sun4m`; `/dev/sd0a` 91744 KB, `/dev/sd0g` 976987 KB | 6.3 min (152 s, 153 s, 54 s) |
| `install sunos413u1b-ss20` | passed | 6.4 min (149 s, 155 s, 57 s) |
| `install sol24-ss5` (regression of `_sparc32.login()`/`power_off()` under `ss5.bin`) | passed | 8.3 min (263 s, 139 s, 80 s) |
| `install sol26-ss5` (regression, OpenBIOS) | passed | 12.9 min (438 s, 216 s, 106 s) |
| unit tests (`test_targets.py`, `test_dos.py`, `test_vgatext.py`) | 107 passed | |

**OpenBIOS targets with the published patches** (pve-qemu-kvm 11.1.3-2+wsh22, qemu-server
9.2.19+wsh1, pve-manager 9.2.31+wsh1, the PVE test container built `--no-cache`; up to three guests
at a time, another agent's guests on the host too), each `lab.py install <target> --check`,
2026-11-19. `sol23-ss5`, `sol23-ss20` and `sol24-ss5` changed from the Sun PROMs to OpenBIOS (as
reliable here, no Sun firmware needed, more than one CPU on the SS-20), `sol24-ss20` and
`sol22-ss10` are new:

| Run | Result | Time |
| --- | --- | --- |
| `install sol22-ss10` | passed; `SunOS sol22-ss10 5.2 Generic sun4m sparc`; the marker | 8.8 min (install 294 s, first boot 140 s, check 75 s) |
| `install sol22-ss10` (second run) | passed | 9.1 min (318 s, 136 s, 75 s) |
| `install sol23-ss5` (twice) | passed both; `SunOS sol23-ss5 5.3 Generic_101498-02 sun4m sparc`; `bios: openbios-sparc32` | 9.8 min (358 s, 141 s, 74 s); 9.8 min (355 s, 140 s, 78 s) |
| `install sol23-ss20` | passed; `SunOS sol23-ss20 5.3 Generic sun4m sparc` | 9.0 min (306 s, 140 s, 80 s) |
| `install sol23-ss20` (second run) | passed | 9.2 min (326 s, 137 s, 75 s) |
| `install sol24-ss5` (twice) | passed both; `SunOS sol24-ss5 5.4 generic sun4m sparc` | 8.3 min (280 s, 131 s, 70 s); 8.2 min (270 s, 131 s, 72 s) |
| `install sol24-ss20` | passed; `SunOS sol24-ss20 5.4 generic sun4m sparc` | 7.9 min (256 s, 130 s, 73 s) |
| `install sol24-ss20` (second run) | passed | 7.9 min (258 s, 129 s, 70 s) |
| the installed `sol23-ss20` and `sol24-ss20` VMs with `cores: 2` (`solaris-boot-disk.py --pve`: `psrinfo -v`, 4 `nawk` loops at once, `mpstat 10 3`, `psrinfo`, `init 5`) | passed both; 2 CPUs on-line, both at 100% `usr` during the loops | 2.2 min each |
| the same with `cores: 4` (8 loops) | passed both; 4 CPUs on-line, all at 100% `usr`; load average 6.5 | 3.4 min each |
| the same VMs with `cores: 4` at the login prompt, QEMU's host CPU over 30 s | 5% of a host core each (the idle loop of 2.3/2.4 doesn't spin; QEMU's `solaris-smp-idle` matches only 2.5.1-9) | |
| a 10-minute soak on 4 CPUs (6 shell loops of `nawk` and `cat /usr/bin/*`, `psrinfo` after ~5 and ~10 min with `MORE_EXPECT` `3 +on-line`, `init 5`) | passed both (2.3 and 2.4) | 11.3 min each |
| unit tests (`test_targets.py`, `test_dos.py`, `test_vgatext.py`, `test_stored_disks.py`, in the PVE lab image with `--network none`) | 129 passed (the profiles checked against `qemu-server.patch`) | |

Not tried: `--user`, `--gateway`, the 9G disk and DHCP on these targets, 2.2 with more than one CPU
(the SS-10 profile allows 4), and a framebuffer console. The stored Sun PROM disk of `sol24-ss5`
(`install-sol24-ss5.raw` in the matrix's directory, installed under `ss5.bin`) under the new
OpenBIOS profile: `lab.py boot-test sol24-ss5` passed (1.3 min), so the matrix's next boot test of
it passes without a reinstall (a `--reinstall` gives it an OpenBIOS install).

**A CD boot that hangs before the installer** (the first full `install` matrix, GitHub run
44533778163). `sol23-ss20` timed out after 900 s waiting for the terminal prompt. Its console:
the CD booted as a disk (`boot .../sd@6,0:d`, the right device; the VM config was the target's,
the same as `lab.py install sol23-ss20` makes), the kernel banner, `corrupt label - bad geometry`
(`Label says 1310720 blocks, Drive says 833944 blocks`: the image is shorter than the CD's label;
every passing 2.2-2.4 boot prints it), `clock gained 11969 days`, 17 turns of the spinner, then
nothing. A good boot prints `Configuring the /devices directory` after the same 17 turns. The same
target passed before (twice, above) and after (the runs below), so it is intermittent, not the
matrix's VM; most likely the ESP deadlock (`submodules/SPARC.md`, "The ESP deadlock": QEMU raises
the disk's interrupt in the register write that starts the command), not traced. The scenario now
fails such a boot early: `solaris-install-serial.py` waits `FIRST_PROMPT_TIMEOUT` (300 s; 35-55 s
in the lab runs) from the banner to the first prompt and then fails with "before the installer";
the Solaris 2.2-2.6 targets (`SOLARIS_SCRIPTED`) have `retry_on: "before the installer"`, so
`install` boots the CD once more (evidence in `install-retry1/`; nothing is on the disk yet). A
second hang in a row still fails the case. The retry itself ran only in the unit tests (no hang in
the runs below).

| Run (through PVE, `pve_matrix.py install --only install-sol23-ss20`, scratch `--disks`) | Result | Time |
| --- | --- | --- |
| run 1 (the scenario before the early-hang change; Debian or Solaris 8 at the same time) | passed; banner to the terminal prompt 34 s | 8.4 min (install 273 s, first boot 135 s, check 74 s) |
| run 2 (with `FIRST_PROMPT_TIMEOUT` and `retry_on`) | passed (banner to the terminal prompt 34 s), no retry needed | 8.7 min (277 s, 145 s, 80 s) |

`pve_matrix.py install` runs every automated target, so the `install` choice of the `sparc lab`
workflow now also needs the 2.3, 2.5 and 4.1.3_U1B CDs (`--iso` with the lab host's layout:
`sun_solaris/Solaris/2.3/SPARC/`, `sun_solaris/Solaris/2.5/SPARC/`,
`sunos_202004/SunOS/SPARC/4.1.3U1B/`) and takes about 50 min longer. Not tried: `--user`,
`--gateway`, `--data-disk`, the 9G disk and a second run of each (one passing run each so far).

**`sol21-ss10` through PVE** (the PVE test container from `e2e/pve/Dockerfile` with the lab, built
`--no-cache` from the published packages: pve-qemu-kvm 11.1.3-2+wsh30, qemu-server 9.2.19+wsh4,
pve-manager 9.2.32+wsh4), three `lab.py install sol21-ss10 --check` at the same time on VMIDs of
their own, 2026-11-20:

| Run | Result | Time |
| --- | --- | --- |
| `install sol21-ss10` (VM 1) | passed; `SunOS sol21-ss10 5.1 Generic sun4m sparc`; the marker; `le0 10.0.2.15 netmask ffffff00`; the finished VM `scsi6: none,media=cdrom`, `boot: order=scsi3` | 9.9 min (install 317 s, first boot 188 s, check 74 s) |
| `install sol21-ss10` (VM 2) | passed | 9.7 min (315 s, 176 s, 79 s) |
| `install sol21-ss10` (VM 3) | passed | 10.1 min (317 s, 198 s, 77 s) |
| unit tests (`test_targets.py`) | passed | |

The install itself: CD boot and sysidtool ~100 s, suninstall's package copy ~3 min, then 2.1 reboots
by itself into OpenBIOS. The first boot spends ~80 s between the kernel banner and the root password
question. As in the lab runs, `df -k` in the check lists `/` and `/usr` only: `/opt` and
`/export/home` are not mounted at boot. 2.1 has no `hostname` command (the check's `hostname`
prints "not found"; `uname -a` and the marker carry the name). `pve_matrix.py install` now also
needs the 2.1 CD in `--iso` (`sun_solaris/Solaris/2.1/SPARC/`). Not tried: `--user`, `--gateway`,
the 9G disk, a boot test of the stored disk, more than one CPU (traps, `submodules/SPARC.md`).

Again on the 11.1.3-3 series (the same container, built `--no-cache` from the published packages:
pve-qemu-kvm 11.1.3-3+wsh6, qemu-server 9.2.20+wsh3, pve-manager 9.2.32+wsh6, libpve-storage-perl
9.1.18+wsh2), two `lab.py install sol21-ss10 --check` at the same time while other agents' builds
and guests kept the host busy (load 8-18 of 14 cores), 2026-11-21. VM 1 wrote into the install
matrix's case layout and is the source of the gallery's recordings:

| Run | Result | Time |
| --- | --- | --- |
| `install sol21-ss10` (VM 1) | passed; `SunOS sol21-ss10 5.1 Generic sun4m sparc`; the marker; `le0` with `inet 10.0.2.15 netmask ffffff00`; the finished VM `scsi6: none,media=cdrom`, `boot: order=scsi3` | 11.7 min (install 385 s, first boot 204 s, check 93 s) |
| `install sol21-ss10` (VM 2) | passed; the same | 11.2 min (388 s, 177 s, 88 s) |
| unit tests (`test_targets.py`) | passed | |

Both guests had the same static address on one bridge and neither minded (SunOS 4.1.3 does, below).
The longer install and check against the +wsh30 runs are the busy host, not the packages.

**`sunos413-ss10` through PVE** (the PVE test container from `e2e/pve/Dockerfile` with the lab, built
`--no-cache` from the published packages: pve-qemu-kvm 11.1.3-2+wsh31, qemu-server 9.2.19+wsh4,
pve-manager 9.2.32+wsh4, libpve-storage-perl 9.1.18+wsh2), `lab.py install sunos413-ss10 --check`
on VMIDs of their own, two at a time, 2026-11-21:

| Run | Result | Time |
| --- | --- | --- |
| `install sunos413-ss10` (VM 1) | passed; `SunOS sunos413 4.1.3 3 sun4m`; the marker; `le0` with `inet 10.0.2.15 netmask ffffff00`; the finished VM `scsi6: none,media=cdrom`, `boot: order=scsi3` | 10.6 min (install 404 s, first boot 151 s, check 55 s) |
| `install sunos413-ss10` (VM 2) | passed | 10.4 min (397 s, 154 s, 51 s) |
| `install sunos413-ss10` (VM 3) | failed in the first boot (stopped by hand): the install passed (155 s), then the guest's `duplicate IP address!!` message, from VM 4 on the same bridge with the same address, came right after `login:` and the scenario waited for a prompt at the end of the line | |
| `install sunos413-ss10` (VM 4) | passed | 6.1 min (142 s, 149 s, 54 s) |
| `install sunos413-ss10` (VM 5) | passed | 5.9 min (134 s, 149 s, 52 s) |
| `install sunos413-ss10 --ip 10.0.2.16` (VM 6, next to VM 5) | passed; `inet 10.0.2.16` | 5.9 min (136 s, 148 s, 52 s) |
| unit tests (`test_targets.py`) | passed | |

VMs 1 and 2 ran while the host was busy with other builds and guests (the install's package copy
took ~5.5 min instead of ~1.5). Two SunOS 4 guests with the same static address on one bridge
report each other on the console (`vmunix: duplicate IP address!!`); one such message after the
login prompt stopped VM 3, so parallel runs need `--ip` (VM 6). `pve_matrix.py install` runs one
target at a time and now also needs the 4.1.3 CD in `--iso`
(`sunos_202004/SunOS/SPARC/4.1.3/Solaris_1.1.img`, next to 4.1.3_U1B's). Not tried: `--user`,
`--gateway`, the 9G disk, a boot test of the stored disk.

### NetBSD install targets

`netbsd111-sparc64` (sun4u, the sparc64 profile: an 8 GiB blank disk on `ide0`, the CD on `ide2`,
`sunhme`, 512 MB), `netbsd111-sparc` (SS-5, 256 MB) and `netbsd111-sparc-ss20` (SS-20, 512 MB, one
CPU; both with a 3 GiB blank disk on `scsi3`, the CD on `scsi6`, lance) install NetBSD 11.1 from the
official CDs (`NetBSD-11.1-sparc64.iso`, `NetBSD-11.1-sparc.iso`; their SHA512 matches the release's
`images/SHA512`). No Sun label is needed: sysinst writes its own disklabel on the blank disk.

1. **Install.** sysinst on the serial console (vt100), the same answers on both architectures
   (`_netbsd.sysinst()`): English, install to hard disk, the first disk, the default partition
   sizes, the sets (`SETS`: `b` = without X11 on sparc64, `c` = Minimal on sparc), from the CD-ROM,
   root without a password, entropy "not now", the configuration menu's defaults, Exit. On sparc64
   the CD's kernel asks only the terminal type (OpenBIOS boots the CD by itself; the API's boot
   order has the CD first) and Exit leaves a shell, where the scenario types `sync; halt -p`. On
   sparc OpenBIOS stops at `0 >` (the blank disk on target 3 comes first) and the scenario boots the
   CD by path; the CD's kernel runs a microroot that loads the installation tools from the CD
   (`1` = cdrom, `/dev/cd0a`, the path of `instfs.tgz`, the terminal type, `I`), and after Exit it
   halts and powers the VM off by itself (`Back in microroot; halting machine...`).
2. **First boot** (`netbsd-firstboot.py`): root logs in without a password, `passwd root` sets the
   password at its prompts (NetBSD's passwd asks once more after an all-lower-case password, then
   takes it), the marker, `/etc/myname`, the network, the optional user (`useradd -m`, home under
   `/home`, group `wheel`), `sync; halt -p`.
3. **Check** (`netbsd-boot-disk.py`, the target's `check` `commands`): logs in with the password,
   records `uname -a`, `hostname`, the marker, `df -k`, the disklabel, `ifconfig -a`, `netstat -rn
   -f inet` and `/etc/resolv.conf`, requires `target=<name>`, `halt -p`.

**NetBSD 9.3** (`netbsd93-sparc64`, `netbsd93-sparc`, `netbsd93-sparc-ss20`): the same profiles,
scenarios and answers with the 9.3 CDs (`NetBSD-9.3-sparc64.iso`, `NetBSD-9.3-sparc.iso` from
archive.netbsd.org; their SHA512 matches the release's `images/SHA512`). The one difference in
sysinst: after the sets 9.3 asks neither for root's password nor about entropy and shows its
configuration menu at once (root's password is an item there, `***EMPTY***`), so `_netbsd.sysinst()`
waits for any of `AFTER_SETS` and answers the password and entropy screens only when they come
(`tests/test_targets.py`, `NetBSDSysinst`). Through PVE (packages of 2026-11-19, pve-qemu-kvm
11.1.3-2+wsh25), one install each: `netbsd93-sparc64` 18.4 min (install 833 s, first boot 144 s,
check 103 s; the install phase takes about twice as long as 11.1's, not looked into), `netbsd93-sparc` 6.8 min
(190 s, 120 s, 72 s), `netbsd93-sparc-ss20` 6.1 min (169 s, 117 s, 53 s); boot tests of the stored
disks 1.5, 1.3 and 1.2 min.

Network, in NetBSD's own files: static = `/etc/ifconfig.<nic>` (`inet <ip> netmask <mask>`),
`defaultroute=<gw>` in `/etc/rc.conf`, the address and host name in `/etc/hosts`; DHCP =
`dhcpcd=YES` in `/etc/rc.conf` (dhcpcd takes the address, router and name servers and writes
`/etc/resolv.conf` through resolvconf; it sends no host name and keeps `/etc/myname`, so the notes
say so, `dhcp_note`); `--dns`/`--domain` = `/etc/resolv.conf`. The NIC is `hme0` on sparc64 and
`le0` on sparc (`nic` in the target, for the notes and the marker). The installed systems listen on
no port (`netstat -an` has no `LISTEN` on sparc64 or on SS-20; `/etc/inetd.conf` has every service
commented out) and sshd is off (sysinst's default).

With pve-qemu-kvm before `wsh/0034` every sparc64 VM gets the system MAC `52:54:00:12:34:56` (the
IDPROM's default, `hme0: Ethernet address 52:54:00:12:34:56` whatever `net0` says; see "Network"
above and `submodules/SPARC.md`, "The sun4u system MAC"), so only one of them per bridge segment
gets a usable address; with `wsh/0034` it is `net0`'s. On sparc the lance uses `net0`'s MAC. NetBSD/sparc64 doesn't idle on sun4u (a host core at 100% while it runs).

**A halt that never powers off.** In the first sparc64 run, the first boot's `halt -p` stopped after
halt's SIGTERM (`syslogd[500]: Exiting on signal 15`, then nothing: no `syncing disks`) and the VM
was still running ten minutes later. It didn't come back: four more sparc64 first boots, their
four check boots, a further DHCP boot and nine boot/login/halt rounds on an installed sparc64 VM
through PVE all powered off about 9 s after `halt -p`. `_netbsd.power_off()` now waits 300 s; if the VM is still up it sends a break on the
console (QMP `chardev-send-break`), which enters NetBSD's kernel debugger, records `ps`, `bt`,
`show uvmexp` and the stacks of `halt` and `makemandb` (`bt/a`), and powers off with `reboot 0x808`
(RB_HALT | RB_POWERDOWN: the disks are synced); the run passes with `halt_hung: 1` in its metrics
and the debugger output in its evidence. The break, the debugger and `reboot 0x808` were tried on
an installed sparc64 VM (a scratch scenario that skips `halt -p`): QEMU exited 0, and `bt/a` showed
`makemandb` (the man page index NetBSD builds in the background at boot) in `biowait`. Not seen on sparc.

Tested in the PVE test container on the lab host (the e2e PVE image with pve-qemu-kvm
11.1.3-2+wsh15, qemu-server 9.2.15+wsh6, pve-manager 9.2.28+wsh4; up to three guests at a time; the
lab host is a VM on an i9-9900K), 2026-11-17, each with `--check`:

| Run | Result | Time |
| --- | --- | --- |
| `install netbsd111-sparc64` (first version) | install passed; first boot: `halt -p` hung (above), stopped at the 600 s power-off limit, failed | install 383 s |
| `install netbsd111-sparc64` | passed; `NetBSD netbsd111-sparc64 11.1 ... sparc64`, the marker, `hme0 10.0.2.15/24` | 10.8 min (install 391 s, first boot 144 s, check 100 s) |
| `install netbsd111-sparc64` | passed | 11.2 min (404 s, 145 s, 105 s) |
| `install netbsd111-sparc64 --bridge vmbr1 --ip dhcp` | passed; dnsmasq leased 10.77.0.111 to `52:54:00:12:34:56` (the IDPROM MAC, not `net0`'s), `default 10.77.0.1` and `resolv.conf` from the lease, `hostname` = `netbsd111-sparc64`; a further boot: both pings by name, no `LISTEN` socket | 10.1 min (364 s, 135 s, 94 s) |
| `install netbsd111-sparc` (first version) | sysinst passed; the scenario expected a shell after Exit, but the microroot powers off by itself: failed, fixed (`finish_install()`) | 3.6 min |
| `install netbsd111-sparc` | passed; `/dev/sd0a` 3064094 KB (210624 used), swap `sd0b` 32 MB, `le0 10.0.2.15/24` with `net0`'s MAC | 6.6 min (201 s, 116 s, 62 s) |
| `install netbsd111-sparc` | passed | 6.8 min (212 s, 118 s, 63 s) |
| `install netbsd111-sparc --bridge vmbr1 --ip dhcp` | passed; lease 10.77.0.142 from dnsmasq, `default 10.77.0.1` and `resolv.conf` (`domain lab.test`, `nameserver 10.77.0.1`) from the lease, `hostname` = `netbsd111-sparc`; a further boot: `ping gw.lab.test` and `ping far.lab.test` (through the router) 2/2 | 6.8 min (221 s, 111 s, 63 s) |
| `install netbsd111-sparc-ss20` | passed | 6.7 min (205 s, 122 s, 62 s) |
| `install netbsd111-sparc-ss20 --bridge vmbr1 --ip 10.77.0.60 --gateway 10.77.0.1 --dns 10.77.0.1 --domain lab.test` | passed; `default 10.77.0.1`, `resolv.conf` as given; a further boot: both pings by name, no `LISTEN` socket | 7.3 min (216 s, 136 s, 67 s) |
| nine boot, login, `halt -p` rounds on the installed `netbsd111-sparc64` VM (`netbsd-boot-disk.py --pve`) | 9/9 passed | 85-100 s each |
| `tests/test_netbsd.py` with the lab's own QEMU (in the PVE container, `NETBSD_ISO` = the lab host's copy) | passed | 623 s (install 415 s, first boot 109 s, check 97 s) |
| `install netbsd111-sparc --user lab --user-password ... --template` | passed; `lab:*:1000:100::/home/lab:/bin/sh` (in `wheel`), `passwd lab` exit 0, converted to a template; the passwords are in no evidence file but the VM's notes (a login as `lab` wasn't tried) | 6.8 min (199 s, 133 s, 60 s) |
| `pve_matrix.py install --only install-netbsd111-sparc64 --only install-netbsd111-sparc --only install-netbsd111-sparc-ss20` (the final code, one guest at a time) | 3/3 passed | sparc64 9.9 min (347 s, 140 s, 94 s); SS-5 6.5 min (197 s, 118 s, 62 s); SS-20 6.3 min (190 s, 117 s, 58 s) |
| `pve_matrix.py pve` and `matrix.py smoke` (regressions, the final code; smoke in the PVE container, whose pve-qemu-kvm is the lab image's) | 5/5 and 3/3 passed | `sol26-install-ss5` 741 s, the others 48-215 s; smoke 156 s, 110 s, 67 s |

`pve_matrix.py install` runs every automated target, so the `install` choice of the `sparc lab`
workflow now also needs the two NetBSD CDs (`other-os/` under `--iso`) and takes about 23 min longer.
Not tried: `--vlan` (`bridge vlan add` on the test container's bridge failed with `Invalid
argument` this time; NetBSD doesn't see the tag), a login as the `--user` user, sparc64 with more
memory, SS-10, and the sets other than these two.

**In CI.** The NetBSD CDs are freely redistributable, so `sparc lab NetBSD`
(`.github/workflows/sparc-lab-netbsd.yml`, on pull requests that change `e2e/sparc` and by hand)
runs `tests/test_netbsd.py` in the lab image on GitHub-hosted runners, one job per target:
`netbsd111-sparc64`, `netbsd93-sparc64`, `netbsd93-sparc` and `netbsd93-sparc-ss20`
(`NETBSD_TARGET`; without it the test runs `netbsd111-sparc64`). Each job downloads its CD from the
URL in `targets.MEDIA` with `fetch_media.py` (`cdn.netbsd.org` for 11.1, `archive.netbsd.org` for
9.3; cached between runs, saved by main only and restored by pull requests: `e2e/README.md`,
"Downloaded media in the Actions cache"), checks its size, sha256 and sha512 (the release's
`images/SHA512`), and runs the target's
three scenarios with the lab's own QEMU (TCG; sun4u, or the SS-5/SS-20 with `_sparc32`'s machine):
install, first boot (password, marker, host name, a static address and router), check (logs in
with the password, requires the marker and `inet 10.0.2.15/24`). On the lab host the 11.1 sun4u
run took 623 s; the jobs' limits are 60 min (11.1 sun4u), 90 min (9.3 sun4u, whose sysinst is
twice as slow) and 45 min (9.3 on the SS-5 and SS-20).

**Before merge.** `sparc lab NetBSD` installs under the published pve-qemu-kvm, so a QEMU or OpenBIOS
change would first meet these installs after it is merged and built. `sparc lab PR QEMU`
(`.github/workflows/sparc-lab-pr-qemu.yml`) runs the same four targets on pull requests that change
`submodules/pve-qemu.patch`, the pve-qemu pin or `openbios/`, with that pull request's sources
instead of the package (no workflow builds pve-qemu-kvm on a pull request):

1. `qemu-system-sparc` and `qemu-system-sparc64` from its pve-qemu tree: the pin with
   `pve-qemu.patch` applied, its `qemu` submodule (`--depth 1`), and `pr-qemu.sh` in the lab image,
   which pushes every patch of `debian/patches/series` with quilt and no fuzz (a patch that doesn't
   apply fails the job, naming it) and builds only `--target-list=sparc-softmmu,sparc64-softmmu`
   (Proxmox's patches included; the configure options are not the package's: no GTK, SDL, OpenGL,
   docs). The compiler runs through ccache, cached per pull request, so a later push rebuilds only
   what its patches touch. `--version` says `wsh-pr-<commit>`.
2. `openbios-sparc32`, `openbios-sparc64` and `QEMU,cgthree.bin` from `openbios/Dockerfile`. The
   package build keeps QEMU's `openbios-sparc64` when its build fails (all patches go in with one
   `git apply`, so one that doesn't apply drops the image with a warning); here any missing image
   fails the job.
3. `pr-qemu.Dockerfile` puts them into the lab image: the binaries in `/usr/local/bin` (before the
   package's `/usr/bin`; the build fails if a binary misses a library of the image), the three
   images over the package's in `LAB_FIRMWARE`. The Sun PROMs stay the package's.
4. `tests/test_netbsd.py` for `netbsd111-sparc64`, `netbsd93-sparc64`, `netbsd93-sparc` and
   `netbsd93-sparc-ss20`, as in `sparc lab NetBSD` (same CD cache, same limits).

What was built is in the run summary and in `versions.txt` (the `sparc-pr-qemu` artifact, and in
each job's evidence): the commit, both `--version` lines, the pve-qemu pin and QEMU version, the
patch's sha256, the series' length and last patch, the OpenBIOS commit and its patches, and the
images' sha256. On GitHub-hosted runners, like `sparc lab NetBSD`, so fork pull requests run it with
a read-only token and no secrets, and the `sparc-lab` runner still never runs pull request code. Not
a required check (it runs only when its paths change).

By hand, from the repository root (the pve-qemu tree prepared as in the workflow's "Prepare the
pve-qemu tree" step):

```sh
docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .
mkdir -p build/sparc-pr/firmware
docker build --output type=local,dest=build/sparc-pr/firmware -f openbios/Dockerfile openbios
docker run --rm -v "$PWD:/src" -w /src --entrypoint sh wsh-sparc-lab \
  e2e/sparc/pr-qemu.sh submodules/pve-qemu build/pr-qemu build/sparc-pr/bin
# versions.txt is what the workflow writes; any file does for a local image
echo local > build/sparc-pr/versions.txt
docker build -f e2e/sparc/pr-qemu.Dockerfile -t wsh-sparc-lab:pr build/sparc-pr
docker run --rm -e WSH_LAB_GUEST_TESTS=1 -e NETBSD_TARGET=netbsd93-sparc --entrypoint python3 wsh-sparc-lab:pr \
  -m unittest -v tests/test_netbsd.py
```

Tried on the lab host (14 vCPUs, busy with other builds and guests: load 10-22), 2026-11-24, the
workflow's steps by hand with main's `pve-qemu.patch` (166 patches, last `wsh/0132`) and
`openbios/` (38 patches); the four installs ran at once with the host's copies of the CDs
(`NETBSD_ISO`):

| Run | Result | Time |
| --- | --- | --- |
| lab image, OpenBIOS (all three images), QEMU cold (empty ccache, 1,360 compiles) | built; `QEMU emulator version 11.1.3 (wsh-pr-<commit>)`, binaries in `/usr/local/bin`, the images' sha256 in `versions.txt` | 220 s, 107 s, 169 s |
| QEMU again, warm ccache | 1,358 of 1,360 compiles from the cache | 78 s |
| QEMU with one patch changed (`wsh/0021`, `hw/ide/cmd646.c`) | 3 compiles, the rest from the cache | 172 s (busier host) |
| the four installs with main's build | 4/4 passed | `netbsd111-sparc64` 16.4 min (install 649 s, first boot 156 s, check 171 s); `netbsd93-sparc64` 31.3 min (1595 s, 132 s, 144 s); `netbsd93-sparc` 6.1 min (203 s, 86 s, 76 s); `netbsd93-sparc-ss20` 6.0 min (195 s, 88 s, 75 s) |
| a context line of `wsh/0021` changed (the series doesn't apply) | failed in `pr-qemu.sh`: `1 out of 3 hunks FAILED`, `the series doesn't apply: ../debian/patches/wsh/0021-... fails` | 68 s |
| a context line of OpenBIOS `0039-sparc64-...` changed | `openbios/Dockerfile` built (exit 0, `WARNING: openbios-sparc64 not built`); the step failed: `openbios-sparc64 was not built` | 36 s |
| `wsh/0021` changed so that the cmd646 never raises INTRQ (applies and builds) | `netbsd93-sparc` passed (5.4 min); `netbsd111-sparc64` failed: `wd0c: device timeout`, then `waiting for devices: atabus0 atabus1 wd0` until `no 'Terminal type' within 900s` | 15 min (the scenario's 900 s for `Terminal type`) |

### The OpenBSD 8.0 install target

`openbsd80-sun4u` (the sparc64 profile: sun4u, OpenBIOS, 512 MB, an 8 GiB blank disk on `ide0`, the
CD on `ide2`, `sunhme`) installs OpenBSD 8.0 from `install80.iso` (467599360 bytes, its sha256 the
one in the release's `SHA256`; freely redistributable, but not downloaded by any test). It needs
openbios 0023 (pve-qemu-kvm 11.1.3-2+wsh22): before, the installed GENERIC kernel stops right after
the loader (`submodules/SPARC.md`, "sparc64"). ntpd stays on, which needs pve-qemu `wsh/0045`
(pve-qemu-kvm 11.1.3-2+wsh30 and later, last tested on 11.1.3-3+wsh6; "ntpd and the IDE timeouts"
below).

- **Install** (`openbsd-install-sparc64.py`, `_openbsd.py`): OpenBIOS boots the CD's `bsd.rd`; the
  installer's questions are one line each, ending in `?` and the default in brackets.
  `_openbsd.installer()` answers them by what they ask (`install_rules()`: a regex per question),
  not in a fixed order, so a question a release adds or skips (8.0 asks about disk encryption and
  no X question on sparc64, and the time zone only after the sets) doesn't break it, and a question
  no rule knows fails the install with that question in the error. A question is answered only when
  it is the console's last line and the console has been quiet for a second: in the first run a
  kernel message (`duplicate IP address`, from a Solaris VM with the same default address on the
  bridge) came in the middle of a question, the installer's line editor drew the question again,
  and answering both copies answered the next question too (the passwords then didn't match). The
  answers: terminal `vt220`, the host name, `hme0` with the static address and netmask, no IPv6, no
  route, the default DNS domain, no name servers, root's password (the target's `root_password`:
  the installer asks for it), sshd yes, no user, root ssh login no, `wd0`, no encryption, the auto
  layout, the sets from `cd0` with `-x*` (`SETS`: base, comp, man, game, `bsd`, `bsd.rd`), yes to the
  missing `SHA256.sig` (the CD has none), time zone UTC, then **S**hell (8.0 asks that after
  "CONGRATULATIONS!", 5.9 is at its shell then: `installer()` answers either). From the installer's
  shell it unmounts and halts; ntpd stays on, as the installer leaves it (`NTPD=off` writes
  `ntpd_flags=NO` into the new system's `/etc/rc.conf.local`, as for 5.9 on sun4m); `bsd.rd`'s `halt
  -p` stops at "halted" without powering off, so the scenario stops the VM.
- **First boot** (`openbsd-firstboot.py`): login as root with the installer's password, the marker,
  `/etc/myname` (`<host>.<domain>` with `--domain`), `/etc/hostname.hme0` (`inet <ip> <netmask>`),
  `/etc/mygate` (`--gateway`), `/etc/resolv.conf` (`--dns`, `--domain`), the address in
  `/etc/hosts`, the optional `--user` (`useradd -m -G wheel -s /bin/ksh`, `passwd`), a check that
  ntpd is enabled and running (`rcctl get ntpd flags` not `NO`, `ntpd` processes), `halt -p`.
- **Check** (`openbsd-boot-disk.py`): login, `uname -a`, the marker, `df -k`, the disklabel,
  `ifconfig hme0`, the routes, `resolv.conf`, `rcctl get ntpd flags`, `pgrep -lx ntpd` (one console
  line: OpenBSD's tty takes 255 characters, which `tests/test_targets.py` checks); a `wd` timeout
  anywhere on the console fails it.

**ntpd and the IDE timeouts.** Until 2026-11-20 the target turned ntpd off and ran a hung install
once more. With QEMU's user network with outside access, ntpd found the guest ~430 ms off and slewed
the clock, and from then on `wd0` reads timed out in 5 of 6 boots (`submodules/SPARC.md`, "Disk
timeouts with a synced clock"); without ntpd it happened too, rarely (the runs below). The cause was
in QEMU's sun4u sabre host bridge: a PCI interrupt (the NIC on pciB) replaced the outstanding IDE
interrupt request, the CPU dropped it while busy, the guest's clear of the IDE request was then
ignored, and no disk or console interrupt reached the CPU again. ntpd's part was its network
traffic, not the slew. pve-qemu `wsh/0045` (pve-qemu-kvm 11.1.3-2+wsh30) fixes it (`submodules/SPARC.md`,
"Cause: the sabre lost a request"), so the target now keeps ntpd on, checks that it runs, and has no
install retry; an IDE timeout followed by 5 minutes of silence still fails the install
(`_openbsd.installer()`, `STUCK_S`), so a regression shows.

Through PVE with ntpd on (the PVE test container with the published pve-qemu-kvm 11.1.3-2+wsh30,
qemu-server 9.2.19+wsh4, pve-manager 9.2.32+wsh4, 2026-11-20; other sparc32 guests running on the
host at the same time, load average 2-5 on 14 cores). For the runs with a way out, the container
routed `vmbr0` to the outside (NAT) with the router at 10.0.2.2:

| Run | Result | Time |
| --- | --- | --- |
| `install openbsd80-sun4u` (the first run with ntpd on) | failed after the install: the sets went in without an IDE timeout, but `installer()` stopped at "CONGRATULATIONS!" and never answered 8.0's "Exit to (S)hell" question, a break from the OpenBSD 5.9 targets (#343), fixed since (`EXIT_QUESTION`) | 10.1 min |
| `install openbsd80-sun4u` | passed; `rcctl get ntpd flags` empty (enabled), three `ntpd` processes; no IDE timeout in any phase | 16.0 min (install 454 s, first boot 286 s, check 204 s) |
| `install openbsd80-sun4u --ip 10.0.2.32 --gateway 10.0.2.2 --dns <a resolver> --domain lab.example --user lab` (a way out) | passed; `default 10.0.2.2`, the user, ntpd running; no IDE timeout | 16.8 min (459 s, 324 s, 209 s) |
| three boots of that VM with disk load (`openbsd-boot-disk.py --pve` with `COMMANDS`: `sleep 90; ntpctl -s a`, `tar cf - /usr \| cksum`, a 200 MB `dd` write, `ntpctl -s s`) | 3 of 3 passed without a disk timeout; ntpd had 5/5 peers and was slewing the clock (`clock unsynced, clock offset is 394.891ms`, 448.652 ms in the third) while `tar` read `/usr`; one ended `clock synced` | 6.4-7.0 min each |
| `install openbsd80-sun4u --export <scratch>` | passed; disk exported; no IDE timeout | 16.8 min (451 s, 294 s, 238 s) |
| `install openbsd80-sun4u --ip 10.0.2.35 --gateway 10.0.2.2 --dns <a resolver> --domain lab.example` (a way out) | passed; ntpd running; no IDE timeout | 17.9 min (506 s, 334 s, 218 s) |
| `boot-test openbsd80-sun4u` of the exported disk | passed; no disk timeout | 3.8 min |
| a boot of the second VM (a way out) with `ping -f -c 300000 10.0.2.2` in the background during `tar cf - /usr \| cksum` (the load that hung 2 of 2 lab runs before `wsh/0045`) | passed; all 300 000 pings, `tar` 1 083 427 840 bytes, then `clock synced`; no disk timeout | 11.5 min |

Again on the Proxmox 11.1.3-3 base (the PVE test container with the published pve-qemu-kvm
11.1.3-3+wsh6, qemu-server 9.2.20+wsh3, pve-manager 9.2.32+wsh6, 2026-11-21; the same target, ntpd
on, no retry). The first two installs ran side by side while other agents built QEMU on the host
(load average 8-20 on 14 cores), the third at 1-2. For the runs with a way out the container routed
`vmbr0` to the outside (NAT) with the router at 10.0.2.2:

| Run | Result | Time |
| --- | --- | --- |
| `install openbsd80-sun4u --check --export <scratch>` | passed; `rcctl get ntpd flags` empty, three `ntpd` processes; no IDE timeout in any phase; disk exported | 24.9 min (install 730 s, first boot 418 s, check 316 s) |
| `install openbsd80-sun4u --check --ip 10.0.2.32 --gateway 10.0.2.2 --dns <a resolver> --domain lab.example` (a way out, at the same time) | passed; `default 10.0.2.2`, ntpd running; no IDE timeout | 25.3 min (739 s, 466 s, 289 s) |
| `install openbsd80-sun4u --check --ip 10.0.2.34` | passed; no IDE timeout | 16.1 min (466 s, 286 s, 198 s) |
| `boot-test openbsd80-sun4u` of the stored disk (installed on +wsh30) | passed; no disk timeout | 4.4 min |
| three boots of the second VM (a way out) of 20-35 min each with ntpd running (`openbsd-boot-disk.py --pve` with `COMMANDS`: `ntpctl -s s` every 3 minutes, a `tar cf - /usr \| cksum` in one) | 3 of 3 passed without a disk timeout; ntpd synced in all three (below) | 20-36 min each |

ntpd on sun4u, measured in the third of those boots (the guest's `sysctl kern.timecounter`: `tick`,
the only choice: `%tick` of the 100 MHz UltraSPARC IIi, which QEMU counts from the host's clock).
ntpd started ~1 min after the kernel, had 5/5 peers 23 s later, slewed the clock once by 0.193 s
(the boot reads the `mk48t59` clock in whole seconds), said `clock is now synced` 4.5 min after it
started and stayed synced for the remaining 26 minutes (stratum 2-3), with a frequency correction
of 0.18 ppm (`adjusting clock frequency by 0.181219 to 0.181219ppm`): the guest's clock runs at the
host's rate, and nothing to fix in the lab or QEMU. The HTTPS constraints read -0.3 to -1.8 s (their
`Date:` header has whole seconds). The other two boots behaved worse on the network side, not the
clock's: in one ntpd never resolved its servers (`not resolved from pool pool.ntp.org`, 0/5 peers for
17 min) and in the other it synced, lost all five peers for ~15 minutes and then synced again (sub-ms
offsets at the end); a short boot after the first, with `host pool.ntp.org` and pings through the
NAT, found the outside reachable and ntpd with 5/5 peers, and a packet count on the VM's tap during the third boot showed NTP every
minute in both directions without a gap. Not traced further (no capture ran during the two bad
boots, and other containers on the host were being started then); neither had a disk timeout.

Earlier, through PVE with ntpd off (the same container and packages as the OpenBIOS Solaris runs
above, pve-qemu-kvm 11.1.3-2+wsh22, 2026-11-19; the test bridge `vmbr0` had no way out):

| Run | Result | Time |
| --- | --- | --- |
| `install openbsd80-sun4u --ip 10.0.2.30` (first run with the final scenario; another VM had 10.0.2.15) | passed; `OpenBSD openbsd80-sun4u 8.0 GENERIC#52 sparc64`; the marker; `/` 1 GB, swap 256 MB, `/usr` 3 GB (1 GB used), `/home` 2 GB; `hme0` 10.0.2.30/24 with net0's MAC; `rcctl get ntpd flags` = `NO` | 18.5 min (install 541 s, first boot 333 s, check 219 s) |
| `install openbsd80-sun4u --ip 10.0.2.31 --export <scratch>` (two 4-CPU Solaris soaks on the host at the same time) | passed; disk exported | 22.4 min (694 s, 391 s, 233 s) |
| `install openbsd80-sun4u --ip 10.0.2.32 --gateway 10.0.2.2 --dns 10.0.2.3 --domain lab.example --user lab` (before the stuck detection existed) | failed: while `bsd.rd` extracted `base80.tgz` (34%) from the CD, nine `cd0(pciide0:1:0): timeout`, then no console output; VM stopped by hand after 11 minutes of silence | 17 min |
| the same again | passed; `OpenBSD openbsd80-sun4u.lab.example 8.0 GENERIC#52 sparc64`; `default 10.0.2.2`, `resolv.conf` with `domain lab.example` and `nameserver 10.0.2.3`; `lab:1000:1000::/home/lab:/bin/ksh` | 18.5 min (528 s, 348 s, 216 s) |
| `install openbsd80-sun4u` (the defaults, the final scenario with the stuck detection and the retry) | passed (no IDE timeout, so no retry); `hme0` 10.0.2.15/24 | 18.0 min (538 s, 316 s, 211 s) | |
| `boot-test openbsd80-sun4u` of the exported disk | passed | 5.1 min |
| six boots of that disk with disk load (`openbsd-boot-disk.py --pve` with `COMMANDS`: `tar cf - /usr \| cksum`, 1 083 463 680 bytes, and a 200 MB `dd` write; one or two other guests running) | 5 of 6 passed without a timeout (`tar` 2m24s-3m15s, `dd` 6-8 s); one stopped after `wd0(pciide0:0:0): timeout` and `wd0d: device timeout reading fsbn 3408952 ..., retrying` (below) | ~6-7 min each |

**IDE timeouts without ntpd** (before `wsh/0045`). Two of these runs hit the IDE timeouts with ntpd
off and no outside network: an install on the CD and a boot under disk load, at a host load average
of 4-13 on 14 cores. Both guests then stopped for good. The hung boot, inspected in the QEMU monitor before it was
stopped: the CPU in OpenBSD's idle loop (`pc` 0x12d9cac, `pstate` 6: interrupts on, PIL 0), no I/O
on the disk for 321 s (`info blockstats`, `idle_time_ns`), no IDE, BMDMA or cmd646 trace event in 40
s, and no answer on the serial console to Return or a break (which enters ddb on a live system). So
after the timeouts no interrupt reaches the CPU, not even the console's; the state is in the run's
evidence (`hang-state.txt`). It was the sabre's lost interrupt request above (`submodules/SPARC.md`,
"IDE timeouts without ntpd", "Cause: the sabre lost a request"). Until `wsh/0045` the target's
`retry_on: "IDE timeouts"` ran such an install once more; that retry is gone, and a hung first boot
or check fails at its phase timeout.

Every `halt -p` after a boot printed `reorder_kernel: failed -- see /usr/share/relink/kernel/GENERIC/relink.log`:
each boot relinks the kernel in the background (KARL), which takes longer than these short boots
under TCG, and the halt stops it; the old kernel stays, and the next boot tries again. Not tried
through the tool: DHCP (`--ip dhcp` is refused; the lab's own runs got an address with `inet
autoconf`), more memory, the VGA console.

### The FreeBSD 12.4 install target

`freebsd124-sun4u` (the sparc64 profile: sun4u, OpenBIOS, 512 MB, an 8 GiB blank disk on `ide0`, the
CD on `ide2`, `sunhme`) installs FreeBSD 12.4-RELEASE, the last release with sparc64 (the 12 branch
is end of life), from `FreeBSD-12.4-RELEASE-sparc64-disc1.iso` (640942080 bytes; size, sha256 and
sha512 as in the release's `CHECKSUM.SHA256-FreeBSD-12.4-RELEASE-sparc64` and `CHECKSUM.SHA512-...`
on ftp-archive.freebsd.org; freely redistributable, not downloaded by any test). It needs openbios
0032 and 0033 for the power-off and the reboot (before, `shutdown -p now` stays on after `Uptime:`
and every reboot panics: `submodules/SPARC.md`, "FreeBSD 12.4 on sun4u"), which no published
`pve-qemu-kvm` has yet: the target has `matrix_skip` until one does, and pve-qemu `wsh/0114` for
idle.

- **Install** (`freebsd-install-sparc64.py`, `_freebsd.py`): OpenBIOS boots the CD's boot block, the
  loader and the GENERIC kernel; bsdinstall asks for the console type on ttya (`vt100`) and shows its
  welcome dialog, where the scenario takes **S**hell (the button's hot key: dialog reads vt100's
  cursor keys as `ESC O C`, and the ESC of `ESC [ C` cancels the dialog, which is the Live CD). In
  the installer's shell it types `/tmp/installerconfig` line by line with `echo` and runs
  `bsdinstall script /tmp/installerconfig`, the installer's own unattended mode: the preamble
  `PARTITIONS=ada0` (the auto layout: VTOC8, `freebsd-ufs` 7.6 GB and swap 410 MB),
  `DISTRIBUTIONS="kernel.txz base.txz"` from the CD's `/usr/freebsd-dist`, `nonInteractive=YES`, and a
  setup script that runs in the new system (`sysrc`: the host name, `ifconfig_hme0` with the static
  address, `dumpdev=NO`, `sendmail_enable=NONE`, `sshd_enable=YES`). No dialog screen is driven by its
  layout. A non-zero exit fails the install with the end of `/tmp/bsdinstall_log`. Then `halt -p`
  (the installer's `shutdown -p now` only prints "System shutdown time has arrived").
- **First boot** (`freebsd-firstboot.py`): login as root (no password yet), root's password at
  `passwd`'s prompts (through `sh -c`: root's shell is csh, and the echoed command line must not
  itself look like the result), the marker, `hostname` in `/etc/rc.conf`, the network with `sysrc`
  (`ifconfig_hme0="inet <ip> netmask <mask>"` and `defaultrouter`, or `ifconfig_hme0="DHCP"`),
  `/etc/resolv.conf` for `--dns`/`--domain`, the optional `--user` (`pw useradd -G wheel`), `shutdown
  -p now`.
- **Check** (`freebsd-boot-disk.py`): login, `uname -a`, the marker, `df -k`, `gpart show ada0`,
  `ifconfig hme0`, the routes, `resolv.conf`, `vmstat -i`; disk trouble on the console (an ata
  timeout, or the `interrupt storm detected` of FreeBSD bug 239068, `_freebsd.DISK_TROUBLE`) fails it.
  `REBOOT=1` reboots once (`shutdown -r now`) and logs in again before the power-off.

Lab runs (the lab's own QEMU, `NET=user`; pve-qemu-kvm 11.1.3-4+wsh3's `qemu-system-sparc64` or the
same tree built with `wsh/0114`-`0115`, OpenBIOS 0001-0030 + 0032-0033 mounted over the package's;
2026-11-22, load average 2-9 on 14 cores):

| Run | Result | Time |
| --- | --- | --- |
| `sparc64-boot-cd.py` with the bootonly CD, `EXPECT=Console type` (package firmware) | passed: no interrupt storm, `ada0`/`cd0` on `ata2`/`ata3` (`atapci0: <SiI (CMD) 646U2 UDMA33 controller>`) | bsdinstall's question at 59 s |
| `freebsd-install-sparc64.py` with disc1 | passed; `bsdinstall script` exit 0 | 10.3 min (the script 8.1 min); `halt -p` to QEMU's exit 15 s |
| `freebsd-firstboot.py`, `NET_MODE=dhcp` | passed | `login:` at 97 s, 2.7 min in all |
| `freebsd-boot-disk.py REBOOT=1` | passed: `hme0` 10.0.2.15/24 by DHCP, `default 10.0.2.2`, `nameserver 10.0.2.3`; `vec2016: atapci0` at 19/s | `login:` at 84 s, the reboot to `login:` 94 s, `shutdown -p now` to QEMU's exit 19 s |

Through PVE (`pve_matrix.py install --only install-freebsd124-sun4u --reinstall freebsd124-sun4u`: the PVE
test container with the published pve-qemu-kvm 11.1.3-4+wsh4, qemu-server 9.2.20+wsh7, pve-manager
9.2.32+wsh11, and the lab's `qemu-system-sparc64` and `openbios-sparc64` above mounted over the
package's; 2026-11-22, load average ~2-3):

| Run | Result | Time |
| --- | --- | --- |
| `install freebsd124-sun4u --check --export <disks>` | passed: `FreeBSD freebsd124-sun4u 12.4-RELEASE r372781 GENERIC sparc64`, the marker, `/` 7.6 GB on `ada0a` (697 MB used), `hme0` 10.0.2.15/24 (the defaults: static, no route); no disk trouble in any phase; disk exported (8 GiB, 691 MB allocated) | 14.9 min (install 574 s, first boot 201 s, check 107 s; `login:` at 76 s) |

The exported disk is not in the stored disks yet: with `matrix_skip` the weekly install matrix would
still boot-test a stored disk, on the published packages, where the power-off spins.

Not tried: the VGA console, more memory, other NICs, `--user` and a static address through the
tool, the bootonly CD's network install.

### OpenBSD 5.9 on sun4m

`openbsd59-ss5` (SS-5, 256 MB) and `openbsd59-ss20` (SS-20, 512 MB, one CPU), both OpenBIOS with
`vga: serial0`, install OpenBSD 5.9 for sparc, the last release with the 32-bit sparc port (the
port was discontinued after it), onto a blank 8 GiB disk on `scsi3`, lance (`le0`). No QEMU,
OpenBIOS or qemu-server change.

**The media.** The release has no CD with the sets for sparc (its signed `SHA256` lists no
`install59.iso`), only `cd59.iso` (4048896 bytes, `bsd.rd` and the boot blocks) and the sets as
files. The target has two CDs: `cd59.iso` on `scsi6`, which boots, and on `scsi5` a sets CD made on
the node from the release's files, `openbsd59-sparc-sets.iso`: `lab.py media openbsd59-ss5
--convert <the release's directory>` checks each file's size and sha256 (`MEDIA` "from" "files":
`bsd`, `bsd.rd`, `base59.tgz`, `comp59.tgz`, `man59.tgz`, `game59.tgz`, `SHA256.sig`,
`INSTALL.sparc`, as in the release's signed `SHA256`), writes the CD with
`answer_media.openbsd_sets()` and keeps it only if it is the tested image (116387840 bytes, sha256
`d1bd7d02...`): no dates, sorted names, so the same files give the same image on every node, and
`lab.py install` checks it like any other medium. `pve_matrix.py` makes it the same way from
`--iso`'s `other-os/openbsd5.9/`. The files are freely redistributable
(`https://ftp.eu.openbsd.org/pub/OpenBSD/5.9/sparc/`, the official mirror that keeps old
releases; its `SHA256` is the lab host's byte for byte); no test downloads them.

The names on that CD are Rock Ridge names (`iso9660(..., rock_ridge=...)`: SP and an `RRIP_1991A`
ER in the root's "." record, NM and PX in each file's record). The first version had only ISO 9660
names (`BASE59.TGZ`, `BSD.RD`): OpenBSD 5.9's `cd9660` shows them in upper case, as they are, and
the installer "found no OpenBSD/sparc 5.9 sets" (it looks for `base59.tgz`). With Rock Ridge, Linux
(`isoinfo -R`) and OpenBSD show the release's names, `SHA256.sig` and `INSTALL.sparc` included, so
the installer checks the sets itself: `Signature Verified` (signify with the 5.9 base key in
`bsd.rd`), then `Verifying` each set against the signed list.

That check needs room: the installer copies the sets to a file system with more than 512 MB free
on `/tmp`, `/home` or `/usr/src` (or 2 GB on any other) first. The auto layout of a 3 GiB disk
(`/` 852 MB, swap 184 MB, `/usr` 1.7 GB, `/home` 327 MB) has none: "Cannot determine prefetch area.
Continue without verification?", and the sets go on unchecked. On 8 GiB the auto layout has the
full set of partitions (`/` 111 MB, swap 480 MB, `/tmp` 170 MB, `/var` 162 MB, `/usr` 932 MB,
`/usr/X11R6` 531 MB, `/usr/local` 2.1 GB, `/usr/src` 1 GB, `/usr/obj` 1.3 GB, `/home` 1.3 GB), and
it checks; the target's install has `VERIFY=1`, which fails an install without `Signature
Verified`.

- **Install** (`openbsd-install-sparc.py`, `_openbsd.py` with `ARCH=sparc`): the disk is blank, so
  OpenBIOS stops at `0 >` and `_sparc32.prom_boot()` boots `/iommu/sbus/espdma/esp/sd@6,0:d`
  (OpenBSD's boot block, `OpenBSD BOOT 2.11`, `bsd.rd` in ~5 s). `_openbsd.installer()` answers by
  what is asked, with rules for 5.9's wording where it differs from 8.0's ("Which network
  interface do you wish to configure? (or 'done') [le0]", "(or 'dhcp' or 'none')", "(or 'rtsol' or
  'none')", "IPv4 address or none" without quotes, the `'bar.com'` domain example, "INSTALL.sparc
  not found", "Cannot determine prefetch area"). 5.9 has no "Exit to (S)hell" question: it ends
  with "CONGRATULATIONS!" at its shell, which ends the dialogue. An installer question with a hint
  after its `?` ("(or 'rtsol' or 'none')") now counts as a question, so one without a rule fails at
  once instead of waiting for the install's timeout (`ANY_QUESTION`). The sets CD on target 5 is
  `cd0` (the boot CD on 6 is `cd1`): "Location of sets? (cd0 cd1 disk http nfs or 'done')" `cd0`,
  "Pathname to the sets?" `/`, the default selection (everything on the CD: `bsd`, `bsd.rd`, base,
  comp, man, game). Time zone UTC; no kernel relink in 5.9 (KARL came in 6.2). Then, as for 8.0,
  `ntpd_flags=NO` in the new system's `/etc/rc.conf.local` and `halt -p`, which powers the SS-5 and
  SS-20 off ("attempting to power down...", QEMU exits).
- **First boot** (`openbsd-firstboot.py`, unchanged but for `NIC_NAME` `le0`): OpenBIOS boots
  `sd@3,0` by itself; `login:` after 2.5-3 min (the first boot generates the host keys: RSA, DSA,
  ECDSA, ED25519 under TCG), then the marker, `/etc/myname`, `/etc/hostname.le0`, `/etc/mygate`,
  `/etc/resolv.conf`, `/etc/hosts`, the optional user, ntpd off and not running, `halt -p`.
- **Check** (`openbsd-boot-disk.py`): `login:` ~25 s after QEMU starts; `uname -a` (`OpenBSD
  <host> 5.9 GENERIC#2 sparc`), the marker, `df -k`, the disklabel of `sd0`, `ifconfig le0` (net0's
  MAC), the routes, `resolv.conf`, ntpd's flags (one console line under 255 characters).

**The keyboard ESCC panic.** The first lab runs used `-vga none`, as the other sparc32 scenarios
do: QEMU then still has the second ESCC with the Sun keyboard and mouse, the kernel attaches
`zskbd0 at zs1 channel 0: keyboard, type 5`, and right after it (in autoconf, `cpu_configure`) it
prints `stray interrupt ipl 0xc` (the ESCCs' level) over and over and stops with `panic: crazy
interrupts`, on the SS-5 and SS-20 alike, `bsd.rd` and the installed GENERIC alike; with `-vga cg3`
the same on the framebuffer console. With `-nographic` QEMU disables that ESCC (its `disabled`
property is `!enable_graphics`), the kernel finds no keyboard (`zskbd0 at zs1 channel 0`, no type)
and boots. qemu-server passes `-nographic` for `vga: serialN`, so the targets run that way; the lab
scenarios have `NOGRAPHIC=1` for it (`_sparc32.py`; `_openbsd.defaults("sparc")` sets it). An
`escc_*` trace of the panicking boot shows the keyboard answering its probe (reset: `0xff 0x04
0x7f`, layout: `0xfe 0x21`, then command 11) and the level-12 interrupt raised and dropped for each
console character after it; QEMU's ESCC trace events don't say which of the two chips they come
from, so which interrupt nobody claims isn't narrowed down. Solaris, SunOS, NetBSD and Linux run
with that ESCC present (the lab's `-vga none`), so it is between OpenBSD 5.9's `zs`/`zskbd` and
QEMU's keyboard channel; the QEMU wiki's "working with -nographic" for 5.8 is probably the same
thing.

Lab runs (`wsh-sparc-lab` with the published pve-qemu-kvm 11.1.3-2+wsh22, one guest per QEMU,
2026-11-19):

| Run | Result | Time |
| --- | --- | --- |
| `cd59.iso`, SS-5 and SS-20, OpenBIOS, `-vga none` | `bsd.rd` panics after `zskbd0` ("crazy interrupts", above) | 6 s |
| the same with `-nographic`, sets CD with ISO 9660 names only | the installer runs; "found no OpenBSD/sparc 5.9 sets" (upper-case names) | |
| install, SS-5 and SS-20, 3 GiB disk, Rock Ridge sets CD | passed; the sets unchecked ("Cannot determine prefetch area") | 2.5-3 min |
| first boot (`--var ARCH=sparc NET=user`, router, DNS, domain, a user) | passed on both: `login:` after 160-180 s, `halt -p` powers off | 4.3-4.6 min |
| check with a disk and network load: `ping 10.0.2.2`, a 100 MB `dd` write and read on `/home`, `tar cf - /usr/share \| cksum` (68 MB) | passed on both: write 29-35 MB/s, read 49-57 MB/s, `tar` 12 s; 3/3 pings | ~1 min |
| install, SS-5, 8 GiB disk | passed, `Signature Verified` and every set verified | 4 min |
| boot of the SS-20 disk with 4 CPUs (`SMP=4`) | boots; OpenBSD/sparc has no multiprocessor kernel: `cpu at mainbus0 not configured` three times | |
| boot of the installed disk with `-vga cg3` | the same panic, on the framebuffer | |
| install, SS-5 with `ss5.bin` (`boot cdrom`; 3 GiB) | passed | 3.2 min |
| boot of that disk under `ss5.bin` (`boot disk`) | the GENERIC kernel stops: `bpp0 at sbus0 slot 5 offset 0xc800000`, `data fault: pc=0xf82abaa0 sfva=0x7c800000`, `panic: kernel fault` | |
| the same with `boot disk -c`, `disable bpp` at `UKC>` | boots, `"SUNW,bpp" ... not configured`, login; `halt -p` powers off | 2.6 min |
| install, SS-20 with `ss20_v2.25_rom` and `TI-SuperSparc-50`, then a boot of that disk (`boot disk`) | both passed; `bpp0 at sbus0 slot 15 offset 0x4800000: Unknown type` | 2.6 min, 2.9 min |

Through PVE (the e2e PVE image with the published pve-qemu-kvm 11.1.3-2+wsh22, qemu-server
9.2.19+wsh1, pve-manager 9.2.31+wsh1; `lab.py media openbsd59-ss5 --convert
/mnt/os/iso/other-os/openbsd5.9` on the node first, which wrote the tested image):

| Run | Result | Time |
| --- | --- | --- |
| `install openbsd59-ss5 --check --ip 10.0.2.41` (3 GiB disk, before `VERIFY`) | passed; the sets unchecked | 10.1 min (212 s, 317 s, 57 s) |
| `install openbsd59-ss20 --check --ip 10.0.2.42 --gateway 10.0.2.2 --dns 10.0.2.3 --domain lab.example --user lab` (3 GiB) | passed; `OpenBSD openbsd59-ss20.lab.example 5.9 GENERIC#2 sparc`, `default 10.0.2.2`, `le0` with net0's MAC | 10.3 min (196 s, 348 s, 60 s) |
| `install openbsd59-ss5 --check` (8 GiB, `VERIFY=1`: the final target) | passed; `Signature Verified`; `/` 111 MB, `/usr` 932 MB (319 MB used), `/home` 1.3 GB; ntpd `NO` | 10.2 min (242 s, 297 s, 55 s) |
| `install openbsd59-ss20 --check --ip 10.0.2.44` (8 GiB) | passed; `Signature Verified`; `le0` 10.0.2.44/24 | 10.0 min (224 s, 306 s, 54 s) |
| `install openbsd59-ss5 --check --export <scratch>` (8 GiB) | passed; disk exported (`install-openbsd59-ss5.raw` and `.json`) | 12.2 min (199 s, 455 s, 52 s) |
| `install openbsd59-ss20 --check --ip 10.0.2.46 --user lab` (8 GiB) | passed; `lab:1000:1000::/home/lab:/bin/ksh` | 10.2 min (184 s, 356 s, 57 s) |
| `install openbsd59-ss5 --check --ip 10.0.2.47 --gateway 10.0.2.2 --dns 10.0.2.3 --domain lab.example --user lab` (8 GiB) | passed; `OpenBSD openbsd59-ss5.lab.example 5.9 GENERIC#2 sparc`, `default 10.0.2.2`, `domain lab.example`, `nameserver 10.0.2.3`, `lab:1000:1000::/home/lab:/bin/ksh` | 10.7 min (194 s, 373 s, 57 s) |
| `boot-test openbsd59-ss5` of the exported disk | passed | 1.0 min |

The `--check` boots and the boot test found no disk timeout and ntpd off (`NO`, no process).
`pve_matrix.py install` runs both targets (no `matrix_skip`, ~20 min together), so the `install`
choice of the `sparc lab` workflow needs the release's files under `--iso`'s
`other-os/openbsd5.9/`.

**`ss5.bin` and the parallel port.** The SS-5 PROM's device tree has a `SUNW,bpp` (SBus slot 5,
offset `0xc800000`) that QEMU's SS-5 doesn't emulate; OpenBIOS's tree has none. `bsd.rd` has no
`bpp` driver and installs, but the installed GENERIC attaches `bpp0` there and takes a data fault
reading it (`sfva=0x7c800000`). `disable bpp` in UKC (`boot disk -c`) boots it; the SS-20 PROM's
`bpp` (slot 15) reads back as "Unknown type" and doesn't fault. The targets use OpenBIOS, so this
isn't in them.

Not tried through the tool: DHCP (`--ip dhcp` is refused), `ss5.bin` and the SS-20 PROM (lab only,
above), SS-10, X11, a framebuffer (it would panic, above).

### Red Hat Linux 6.2

`redhat62-ss5` (SS-5, 256 MB) and `redhat62-ss20` (SS-20, 512 MB, one CPU), both OpenBIOS with
`vga: serial0`, install Red Hat Linux 6.2 for SPARC (`redhat-6.2-sparc.iso`, the one install CD;
kernel 2.2.14) onto a Sun-labelled 3 GiB disk on `scsi3`, the CD on `scsi6`, lance (`eth0`). The
32-bit kernel and initrd on the CD run on QEMU's sun4m as they are: ESP (`sda`, `sr0`), lance
(`sunlance`), the Zilog serial port as the console (`ttyS0`, from the PROM's `output-device`), and
"Power off control detected", so `poweroff` ends the VM. No QEMU, OpenBIOS or qemu-server change.

1. **Install** (the `unattended` method, `redhat-install-sparc.py`). anaconda 6.2 reads a
   kickstart file with `ks=cdrom:/ks.cfg` from the first CD-ROM it can mount, and the install
   source from the first one with `RedHat/instimage` on it. `install.Unattended` writes the answer
   CD (`answer_media.kickstart()`: the address and netmask, `/boot` 32 MB, `/` the rest but swap
   128 MB, the Base group plus `iputils`, time zone MET, `reboot`) and puts it on `scsi5`, which
   Linux finds before the Red Hat CD on `scsi6` (`sr0` and `sr1`). OpenBIOS stops at `0 >` (the
   disk comes first and doesn't boot); the scenario boots the CD as a whole device
   (`boot /iommu/sbus/espdma/esp/sd@6,0`: its SILO isn't in slice `d`, where Solaris's is) and types
   `linux ks=cdrom:/ks.cfg` at SILO's `boot:`. Kickstart answers everything but SILO's three
   screens (6.2's `lilo` command skips the step "lilo"; on SPARC the step is "silo"), which the
   scenario takes with F12 (`\e[24~`, newt's "next screen": no kernel options, SILO in the first
   sector of `/dev/sda1`, the PROM boot device and alias boxes as they come). The packages take
   about 100 s. The install ends with `reboot`; the scenario stops the VM at OpenBIOS's banner.
2. **First boot** (`redhat-firstboot.py`): SILO on the disk, root logs in on the serial console
   without a password (the kickstart's `%post` left it empty; the installer had already put
   `getty console` in `/etc/inittab` and `console` in `/etc/securetty`), `passwd root` at its
   prompts, the marker, `HOSTNAME=` in `/etc/sysconfig/network` and the address in `/etc/hosts`
   (anaconda 6.2 didn't take kickstart's `network --hostname` into the installed system, so the host
   name is set here and the kickstart file has none), `GATEWAY=` and `/etc/resolv.conf`, the
   optional user (`useradd -m`, home under `/home`, `bash`), `poweroff`.
3. **Check** (`redhat-boot-disk.py`): logs in with the password, records `uname -a`, `hostname`,
   the marker, `df -k`, `fdisk -l /dev/sda`, `ifconfig -a`, `route -n` and `resolv.conf`, requires
   `target=<name>`.

Found on the way:

- **Blank disk:** anaconda asks "Bad Partition Table ... Initialize / Skip Drive" for a disk without
  a label, and kickstart's `zerombr yes` doesn't answer it on SPARC; the target's disk has the Sun
  label `sunlabel.py` writes for Solaris (SUN2.9G), and `clearpart --all` replaces its slices.
- **SILO and the end of the disk:** with `/` alone on the 3 GiB disk, SILO's first stage printed `S`
  and stopped (OpenBIOS: `File not found`, `halt, power off`; `ss5.bin`: `Program terminated`):
  `/boot/second.b` was at 4 KB block 526410, past 2 GB, and SILO's first stage reads its second
  stage through the PROM, which on sun4m doesn't reach that far. A 32 MB `/boot` as the first
  partition (`sda1`, cylinder 0) fixes it; `/` is `sda2`, swap `sda4`.
- `%packages` has no `ping` with Base alone (`iputils` is in "Networked Workstation"), so the
  kickstart file adds `iputils`. kudzu is turned off in `%post` (its hardware probe asks on the
  console at boot).
- **sendmail at boot:** with only the short host name in `/etc/hosts` and no DNS, every boot
  waited 120 s at `Starting sendmail:` (a check boot of 166 s instead of ~60). The first boot writes
  `<host>.<domain> <host>` (`.localdomain` without `--domain`, as Red Hat names `localhost`).
- **A flaky end marker:** root's `ls` is an alias with `--color`; once its last escape sequence
  arrived split over two reads of the console, so `lab.Machine` (which strips escape sequences
  per read) kept a `[m` in front of `END-OF-COMMAND` and the first boot waited for it until it was
  stopped (the install failed cleanly: VM destroyed, answer CD gone). The first boot runs `/bin/ls`
  now; stripping across reads in `lab.py` would fix it for every scenario (not done here).
- Network: a static address only (`net_modes`); DHCP (Red Hat 6.2 has `pump`) wasn't tried.
  The lance uses `net0`'s MAC, as for Solaris.

Tested in the PVE test container on the lab host (the e2e PVE image with the published
pve-qemu-kvm 11.1.3-2+wsh16, qemu-server 9.2.18+wsh3, pve-manager 9.2.30+wsh2, libpve-storage-perl
9.1.18+wsh1; TCG; the host's 14 cores shared with two other agents' runs, so the times are from a
busy host), 2026-11-18:

| Run | Result | Time |
| --- | --- | --- |
| the CD with the lab's own QEMU (SS-5, OpenBIOS), `linux text` | the installer's language screen on ttya after ~30 s | |
| `redhat-install-sparc.py`, then `redhat-firstboot.py` (lab QEMU), `/` alone | the install passed; the disk didn't boot (SILO's `S`, above), also not with `ss5.bin` | install 136 s |
| install, first boot, check with the lab's own QEMU (`/boot` first) | 3/3 passed; `df -k`: `/dev/sda2` 2.6 GB (134 MB used), `/dev/sda1` 32 MB on `/boot`; `ping` missing (now in the kickstart file) | 139 s, 104 s, 61 s |
| `install redhat62-ss5 --vmid 9600 --check --gateway 10.0.2.2 --dns 10.0.2.2 --domain lab.test` | passed; `scsi5` and `local:iso/wsh-lab-answers-9600.iso` gone afterwards, `scsi6: none,media=cdrom`, `boot: order=scsi3`; `eth0` with `net0`'s MAC, `default 10.0.2.2`, `resolv.conf` as given; the password in no evidence file | 5.9 min (install 130 s, first boot 144 s, check 62 s) |
| a further boot of VM 9600 with 10.0.2.2 on the container's `vmbr0`: `ping -c 3 10.0.2.2` | 2 of 3 answered (the first went to ARP) | 38 s |
| `install redhat62-ss20 --vmid 9601 --check --user lab` | failed in the first boot: the `ls` end marker (above), stopped by hand; VM destroyed, `scsi5` and the answer CD gone | install 84 s |
| the same again (`/bin/ls`) | passed; `lab:x:500:500::/home/lab:/bin/bash`, `passwd lab` exit 0; the check boot waited 120 s for sendmail (above) | 6.6 min (85 s, 127 s, 166 s) |
| `install redhat62-ss20 --vmid 9601 --check` (`.localdomain` in `/etc/hosts`) | passed; a further boot: `netstat -an` lists one listener, sendmail on `0.0.0.0:25`; on at boot: atd, keytable, gpm, netfs, network, random, linuxconf, sendmail, syslog, crond | 4.3 min (83 s, 114 s, 44 s) |
| `pve_matrix.py install --only install-redhat62-ss5` (the final code; the CD linked from `--iso`) | 1/1 passed, VM destroyed afterwards | 5.3 min (106 s, 131 s, 61 s) |

The installed systems listen on port 25 only (sendmail, on every address); Red Hat 6.2's Base has
no inetd. `pve_matrix.py install` runs both targets, so the `install` choice of the `sparc lab`
workflow needs `other-os/redhat-6.2-sparc.iso` under `--iso` and takes about 11 min longer. Not tried: DHCP, `--vlan`, the 9G disk, SS-10, `ss5.bin` or the SS-20 PROM for the
install, other package groups (X needs a framebuffer and `Xsun`), a login as the `--user` user.

### Debian GNU/Linux 4.0

`debian40-ss5` (SS-5, 256 MB) and `debian40-ss20` (SS-20, 512 MB, one CPU), both OpenBIOS with
`vga: serial0`, install Debian GNU/Linux 4.0r9 "etch" for sparc (`debian-40r9-sparc-netinst.iso`,
the last Debian release for sun4m; kernel 2.6.18-6-sparc32) onto a blank 3 GiB disk on `scsi3`,
the netinst CD on `scsi6`, lance (`eth0`). They need **`pve-qemu-kvm` 11.1.3-2+wsh20 or later**
(the ESP fix `wsh/0038`, below). `pve_matrix.py install` installs them when it has an apt cache
(`--apt-cache` / `WSH_LAB_APT_CACHE`; "The apt cache pinhole" above): `lab.py install <target>
--check --export <disks> --apt-proxy http://10.0.2.2:3142`, no router and no name server, the cache
the guest's only way out. Without a cache it skips them (`matrix_needs: apt_cache`).

1. **Install** (the `unattended` method, `debian-install-sparc.py`). `install.Unattended` writes
   the answer CD (`answer_media.preseed()` and the loader script `wshlab`) and puts it on `scsi5`.
   The scenario boots the netinst as a whole device (`boot .../sd@6,0`, like Red Hat's) and types
   one line at SILO's `boot:` (`_debian.boot_line()`):
   `install priority=critical locale=en_US preseed/early_command="modprobe esp;modprobe sr_mod;modprobe isofs;until mount -r /dev/scsi/host0/bus0/target5/lun0/cd /mnt;do sleep 1;done;sh /mnt/wshlab"`.
   debian-installer reads the kernel command line into its database at start-up and runs
   `preseed/early_command` before its first question (`S35initrd-preseed`), so the command loads
   the SCSI and CD drivers itself, mounts the answer CD by its target and runs `wshlab`, which
   loads `preseed.cfg` with `debconf-set-selections`, unmounts the CD (`umount -l`; busybox's plain
   `umount` gets `ENOSYS` there) and deletes its SCSI device (`/sys/.../device/delete`), and hides
   the floppy drive (below). From then on nothing is asked: the network (static, from `--ip`,
   `--netmask`, `--gateway`, `--dns`, `--domain` and the host name), the mirror
   (`archive.debian.org`, `/debian`, suite `etch`, through `--apt-proxy` if given), the disk
   (partman-auto with a recipe: `/boot` ext2 40-64 MB first, `/` ext3, swap 128-256 MB), the base
   system and the kernel from the archive, no tasks, no popularity contest, SILO on the disk, the
   reboot. The scenario stops the VM at OpenBIOS's banner, and fails at once with a snapshot if a
   question box (`[!!] ...`) shows up.
2. **First boot** (`debian-firstboot.py`): SILO boots `Linux` from the disk by itself; root logs
   in on `ttyS0` without a password (the preseed file's late command emptied it; the installer
   adds `T0:23:respawn:/sbin/getty -L ttyS0 9600 vt102` for a serial console), `passwd root` at its
   prompts, the marker, the optional user (`useradd -m`, home under `/home`, `bash`), `poweroff`.
   The network files are the installer's (`/etc/network/interfaces`, `/etc/resolv.conf`,
   `/etc/hostname`).
3. **Check** (`debian-boot-disk.py`): logs in with the password and records `uname -a`,
   `hostname`, the marker, `/etc/debian_version` (`4.0`), `df -k`, `fdisk -l /dev/sda`,
   `ifconfig -a`, `route -n`, `resolv.conf`, `sources.list` and the listening ports; requires
   `target=<name>`.

Why the preseed file comes this way:

- `preseed/file=/cdrom/...` reads from the install CD, and a second CD isn't mounted by d-i at
  all; `preseed/url` needs a web server on the node; a preseed file in the initrd would mean
  remastering Debian's media. The early command on the boot line reads the tool's own CD instead.
- **The answer CD must disappear:** Etch's `cdrom-detect` mounts the first CD-ROM that mounts
  (`list-devices cd`: `sr0`, the answer CD on target 5, before the netinst on target 6) and only
  then checks `.disk/info`, so with the answer CD still there it gives up ("not a Debian CD").
- **The boot line's limits:** Linux 2.6.18 on sparc32 keeps 256 bytes of command line and cuts
  the rest silently; it reads every word that starts with `-` as boot switches letter by letter
  (`-h` halts, `-p` moves the console to the PROM; others print "Unknown boot switch"), so the
  command has only `-r`; and d-i takes a word with a `.` for a module parameter
  (`/mnt/wshlab.sh` gave "register-module: cannot create /var/lib/register-module//mnt/wshlab.params"),
  so the script has no extension. The mount is retried because the device node comes from udev a
  moment after `modprobe`.
- **The expired archive key:** `archive.debian.org` still serves etch for sparc, but every key
  that signed it has expired (the installed system's `apt-key list`: the etch automatic signing
  key `6070D3A1` in 2009, `55BE302B` and `6D849617` in 2012-2013). The installer is told not to
  check: `debian-installer/allow_unauthenticated` (base-installer 1.76etch1) runs debootstrap
  without `--keyring` and writes `APT::Get::AllowUnauthenticated "true"` for the rest of the install
  (finish-install removes it: the installed `apt.conf.d` has only `00trustcdrom` and `70debconf`).
  An install without it wasn't tried. `apt-setup/security_host` is left empty (etch's security
  archive isn't served at `security.debian.org`). On the installed system etch's apt (0.6.46) takes
  the archive as it is: `apt-get update` prints no GPG warning, `apt-get -s install less` none about
  authentication, and `apt-get -y install iproute` installed it.
- `--apt-proxy URL` (or `WSH_LAB_APT_PROXY`), an http(s)://host[:port] URL such as an apt-cacher-ng
  (`http://aptcache.example:3142`), becomes `mirror/http/proxy`: debootstrap and apt fetch through
  it, and d-i writes it to the installed `/etc/apt/apt.conf` (`Acquire::http::Proxy`), as it does
  for any install with a proxy, so later `apt-get` runs use it too (remove the line to go direct).
  Only targets with `apt_proxy` take it (the option is refused for the others; the variable is
  ignored for them).
- The network is static only (`net_modes`), and `--gateway` and `--dns` are required
  (`net_require`): the install fetches from the archive, so the router and name server must reach
  it, or the proxy. An `--apt-proxy` by address on the guest's own network replaces both
  (`install.proxy_on_network()`): apt and debian-installer hand an HTTP proxy whole URLs
  (`GET http://archive.debian.org/...`), so the guest resolves no names and needs no router.
  etch's netcfg puts the network's first address (10.0.2.1) in for an empty router and name
  server; the late command then removes the `gateway` line from `/etc/network/interfaces` and the
  `nameserver` lines from `/etc/resolv.conf`, so the installed system has neither.
- `lab.py boot-test` of a stored Debian disk no longer asks for `--gateway`/`--dns` (it installs
  nothing; before, it refused, so the matrix could never have boot-tested one). The boot-test VM
  has a new MAC, which etch's udev (`z25_persistent-net.rules`) names `eth1`, so the boot test
  runs with the network down; the check doesn't need it.
- The late command also comments out the netinst's `deb cdrom:` line in `sources.list`.

Found on the way:

- **QEMU's ESP and Linux 2.6.18 (`wsh/0038`):** with the published `pve-qemu-kvm` (11.1.3-2+wsh16
  and wsh17) the netinst's kernel takes the disk and both CD-ROMs offline ("sd 0:0:3:0: scsi: Device
  offlined - not ready after error recovery", "rejecting I/O to offline device"), and d-i can't
  mount its CD ("No medium found"). The old `esp.c` driver negotiates synchronous transfers with
  Select with ATN and Stop, a 5-byte SDTR message out, then sends the CDB a byte at a time;
  `esp_cdb_ready()` compared the whole command FIFO (identify and message bytes included) with the
  CDB length, so the first CDB byte alone counted as a complete 6-byte command, the target answered
  ILLEGAL REQUEST (`asc 0x20`), and the driver reset the bus until it gave up. One line in
  `hw/scsi/esp.c` fixes it (`len - s->cmdfifo_cdb_offset >= cdblen`): the install, first boot and
  check below ran first on a `qemu-system-sparc` built with it, then on the published
  pve-qemu-kvm 11.1.3-2+wsh21 (the fix is in +wsh20 and later). Solaris, SunOS, NetBSD and Red Hat 6.2's
  2.2 kernel don't send that message sequence.
- **The floppy drive:** QEMU's sun4m always has an (empty) floppy drive. partman's disk scan opens
  `/dev/fd0`, and in about half the runs Linux 2.6.18's floppy driver then oopsed in keventd
  (`reset_interrupt+0xb8`, a NULL pointer, with the driver's "lock fdc" timeout), after which the
  installer never left "Scanning disks... 41%". `floppy=0,allowed_drive_mask` didn't help; `wshlab`
  adds a udev rule that ignores `fd[0-9]*` and removes the device nodes, and the scan skips it
  (none of the later runs hung).
- **A blank disk:** on the lab's Sun-labelled 3 GiB disk partman's new Sun label kept a geometry
  from the old one, `/` got 352 MB and the recipe failed ("Failed to partition the selected disk").
  On a blank disk partman writes the label itself (255 heads, 63 sectors, 391 cylinders): `sda1`
  `/boot` 64 MB from cylinder 0, `sda2` `/` 2.9 GB, `sda3` the whole disk, `sda4` swap 185 MB.
- `partman-auto/disk` (`/dev/discs/disc0/disc`) is needed, or partman asks for the partitioning
  method even at priority critical.
- The installed base system has no `ip` (`iproute` isn't in it): the check uses `route -n`.

Tested 2026-11-18 on the lab host (TCG; the host's 14 cores shared with other agents' runs and
builds, so the times are from a busy host), the PVE runs on the e2e PVE image with the published
pve-manager 9.2.30+wsh3, qemu-server 9.2.18+wsh4, pve-qemu-kvm 11.1.3-2+wsh17 and
libpve-storage-perl 9.1.18+wsh1, `/usr/bin/qemu-system-sparc` bind-mounted from the local build with
the ESP fix:

| Run | Result | Time |
| --- | --- | --- |
| the netinst with the lab's own QEMU (pve-qemu-kvm 11.1.3-2+wsh16), SS-5, OpenBIOS, `install` at SILO | the installer's language screen on ttya | |
| the same at priority critical, the netinst alone; `TRACE=esp_*` | "Your installation CD-ROM couldn't be mounted"; `dmesg`: both disk and CD-ROM "Device offlined"; the trace shows the SDTR sequence and the 1-byte command (above) | |
| the same with a local `qemu-system-sparc` built with the `esp_cdb_ready()` fix | `sda: 6291456 512-byte hdwr sectors`, `sr0: scsi3-mmc drive`; the installer loads its components from the CD | |
| `debian-install-sparc.py` (lab QEMU with the fix, `NET=user`) before the floppy and blank-disk fixes, about 15 runs | about half hung at "Scanning disks... 41%" (the floppy oops, in the kernel log of the runs that printed it at full log level); the others reached partman and failed with "Failed to partition the selected disk" on the Sun-labelled disk | |
| `debian-install-sparc.py`, `debian-firstboot.py`, `debian-boot-disk.py` (lab QEMU with the fix, `NET=user`, blank disk, three installs at once) | 3/3 installs passed; first boot and check of one: `uname -a` `2.6.18-6-sparc32`, `/etc/debian_version` `4.0`, `df -k` `/dev/sda2` 2.8 GB (296 MB used), `/dev/sda1` 60 MB on `/boot`; `apt-get update` from the archive works | 1258-1280 s, 84 s, 77 s |
| `install debian40-ss5 --vmid 9900 --check --user lab --gateway --dns --apt-proxy` (the PVE test container, its `vmbr0` routed to the internet, `qemu-system-sparc` replaced by the build with the fix) | passed; `scsi5` and `local:iso/wsh-lab-answers-9900.iso` gone afterwards, `scsi6: none,media=cdrom`, `boot: order=scsi3`; `/etc/apt/apt.conf` has the proxy; a further boot: `apt-get -y install iproute` worked, `ping archive.debian.org` answered | 23.3 min (install 1180 s, first boot 132 s, check 68 s) |
| `install debian40-ss20 --vmid 9901 --check --gateway --dns` (straight to the archive) | passed; no `apt.conf`; `netstat -ltn` lists no listener (inetd: "no services enabled"); a further boot: `apt-get update` no GPG warning | 19.2 min (965 s, 111 s, 59 s) |
| `install debian40-ss20 --vmid 9902 --check --user lab --gateway --dns --apt-proxy` (the final code) | passed; the install's end seen at OpenBIOS's banner; `lab:1000:1000::/home/lab:/bin/bash` | 16.3 min (774 s, 124 s, 62 s) |
| `install debian40-ss5 ...` without `--gateway` or with `--apt-proxy ftp://...`; `install redhat62-ss5 --apt-proxy ...` | refused before a VM is made | 0 s |

Rerun 2026-11-19 on the published packages only (the e2e PVE image built from the apt repo:
pve-qemu-kvm 11.1.3-2+wsh21, qemu-server 9.2.19+wsh1, pve-manager 9.2.31+wsh1, libpve-storage-perl
9.1.18+wsh1; nothing bind-mounted), the container's `vmbr0` routed to the internet, two installs at
once on the shared lab host:

| Run | Result | Time |
| --- | --- | --- |
| `install debian40-ss5 --check --user lab --gateway --dns --apt-proxy` | passed; `uname -a` `2.6.18-6-sparc32`, `/etc/debian_version` `4.0`, `/dev/sda2` 2.8 GB (296 MB used) | 21.6 min (install 1068 s, first boot 134 s, check 73 s) |
| `install debian40-ss20 --check --gateway --dns` (straight to the archive) | passed | 17.4 min (849 s, 111 s, 65 s) |
| `install debian40-ss5 --check --gateway --dns` (straight to the archive) | passed | 26.0 min (1325 s, 132 s, 87 s) |
| `install debian40-ss20 --check --user lab --gateway --dns` with `WSH_LAB_APT_PROXY` | passed; `lab:1000:1000::/home/lab:/bin/bash` | 20.7 min (1021 s, 134 s, 67 s) |
| `install debian40-ss5 --vmid N --out DIR --check`, the command `pve_matrix.py install` ran then | refused: "--gateway: debian40-ss5 needs it with a static address", so the targets kept `matrix_skip` | 0 s |

Through the apt cache pinhole (the PVE test container built `--no-cache`: pve-qemu-kvm
11.1.3-2+wsh22, qemu-server 9.2.19+wsh1, pve-manager 9.2.31+wsh1; `pve_matrix.py install --only
<case> --apt-cache <the owner's apt-cacher-ng> --disks <scratch>`, another Solaris install at the
same time, 2026-11-19):

| Run | Result | Time |
| --- | --- | --- |
| `install-debian40-ss5` (`--apt-proxy http://10.0.2.2:3142`, no `--gateway`/`--dns`) | passed and exported; d-i fetched its components, the base system and the kernel through the pinhole; the check showed `nameserver 10.0.2.1` and a default route via 10.0.2.1 (netcfg's defaults, now removed by the late command) | 20.2 min (install 1005 s, first boot 118 s, check 68 s) |
| the same disk booted again (`boot-test --keep`, then `debian-boot-disk.py` with probe commands; the interface brought up by hand, as `eth1`) | `ping 1.1.1.1`: network unreachable; `wget http://1.1.1.1/` and `wget http://archive.debian.org/debian/` fail; with `route add default gw 10.0.2.2`: ping and wget to 1.1.1.1 still fail (no forwarding in the node); `http_proxy=http://10.0.2.2:3142 wget .../dists/etch/Release` and `apt-get update` (the installed `Acquire::http::Proxy`) work | 2.1 min |
| `install-debian40-ss20` (the same, with the late command that drops netcfg's 10.0.2.1) | passed and exported; the check: only the `10.0.2.0/24` route on `eth0`, no default route, no `nameserver` in `/etc/resolv.conf` | 20.1 min (1002 s, 116 s, 63 s) |
| `pve_matrix.py install --only install-debian40-ss5 --only install-debian40-ss20` without a cache, the two stored disks in `--disks` | both boot-tested and passed (no `--gateway`/`--dns` asked for any more) | 1.4 min, 1.2 min |
| the same with an empty `--disks` and `WSH_LAB_APT_CACHE` empty (as the workflow without the secret) | both `skip`, exit 0, nothing done on `vmbr0` | 0 s |
Not tried: DHCP (d-i's default; `--ip dhcp` is refused for now), `--vlan`, SS-10, `ss5.bin` or the
SS-20 PROM, more than one CPU, tasks beyond the base system, the netinst on sun4u (Etch's sparc64
kernel; the sun4u profile's IDE and `sunhme` were not tried with it).

### Debian 13 on sun4u

`debian13-sun4u` (sun4u, OpenBIOS, 1024 MB, `vga: serial0`) installs Debian 13 from the debian-ports sparc64
netinst (`debian-13.0.0-sparc64-NETINST-1-2026-06-11.iso`, the snapshot of 2026-06-11, Linux 7.0.12) onto a
blank 8 GiB disk on `ide0`, the netinst on `ide2`, `sunhme` (`enp2s0`). Ports have sid only: the base system,
the kernel, the SSH server and GRUB come from `deb.debian.org/debian-ports` (or `--apt-proxy`), so the
network is static with `--gateway` and `--dns`, as for Debian 4.0. `matrix_skip`: 2.5-3 hours.

1. **Install** (`unattended`, `debian13-install-sparc64.py`): the answer CD (`answer_media.preseed_ports()`
   and the loader `wshlab`) goes on `ide3`, Linux's `sr1` behind the netinst's `sr0`. At the netinst's GRUB
   menu (no timeout) the scenario types `c`, then `linux /install/vmlinux priority=critical
   locale=en_US.UTF-8 keymap=us preseed/early_command="modprobe pata_cmd64x;...;sh /mnt/wshlab" --- quiet`,
   `initrd /install/initrd.gz` and `boot` (`_debian13.boot_options()`). The early command mounts the
   answer CD, `wshlab` loads `preseed.cfg` with `debconf-set-selections`, unmounts it and deletes its drive
   (`/sys/block/sr1/device/delete`). Then nothing is asked: static network, the ports mirror (signed: the
   netinst brings debian-ports-archive-keyring), partman's "atomic" recipe on a Sun label it writes
   (`/boot` ext2, `/` ext4, swap), tasksel `ssh-server` only, GRUB on the disk, the reboot (OpenBIOS 0030),
   where the scenario stops the VM. Root gets the hash `*` and the late command empties it.
2. **First boot** (`debian13-firstboot.py`): GRUB's menu (5 s) boots the disk; root logs in on ttyS0 without
   a password, `chpasswd` sets it (no echo), the marker, the optional user (`useradd -m`, `bash`), `poweroff`.
3. **Check** (`debian13-boot-disk.py`): logs in with the password and records `uname -a`, the marker,
   `/etc/debian_version`, `df -k`, `lsblk`, `ip -br addr`, `ip route`, `resolv.conf`, `sources.list` and
   `systemctl is-active ssh`.

Found on the way:

- **GRUB escapes quotes in `$options`:** typed through the menu's own `set options=...; boot_one`, GRUB split
  the variable at the spaces and passed `preseed/early_command=\"modprobe` to the kernel, and the command
  failed ("exit code 2"). Typed on the `linux` line, GRUB's quoting keeps it one word, which the kernel
  unquotes.
- **user-setup and `!`:** `passwd/root-password-crypted password !` means "not preseeded" to user-setup,
  which then asks for a password; `*` doesn't.
- `quiet` hides the kernel banner; the scenario waits for the installer's syslog start.
- The netinst's GRUB and the installed one print `call-method color!: exception -21` and fail
  `block-size`/`#blocks` on OpenBIOS; harmless. The installed GRUB needs openbios 0009 and 0011
  (`submodules/SPARC.md`, "Debian 13 on sun4u").
- **OSC strings on the console:** systemd 258's shell prompt wraps every command in OSC 3008 context
  strings (`ESC ] 3008;start=...ESC \`), so a command's output no longer started its line in the lab's
  text and `shell()` waited for `END-OF-COMMAND` forever. `lab.py` now strips OSC and DCS strings like
  the CSI sequences, holding back one that a read cuts off (`Machine._strip()`).
- **systemd's 90 s timeouts on a busy host:** the boot test of the stored disk failed on a busy lab host
  (`no 'login: ?$' within 900s`, 17.1 min) and passed on an idle one. systemd gives a device 90 s to show up
  and a unit 90 s to start, both in wall-clock time. Under TCG, udev's coldplug alone takes about that long:
  on an idle host, through PVE, the swap partition's `/dev/disk/by-uuid` link came after the 90 s (`Timed out
  waiting for device`, swap left off) and `/boot`'s just in time. With the host busy, `/boot`'s device times
  out too, `local-fs.target` fails and systemd stops in emergency mode ("Enter root password for system
  maintenance"), so `login:` never comes; with more load ttyS0's device and journald's start time out as
  well. The boot scenarios now edit GRUB's entry at the menu (`e`, to the `linux` line, `Ctrl-E`) and append
  `systemd.default_timeout_start_sec=600 systemd.default_device_timeout_sec=600` (`_debian13.grub_append`;
  the disk's `grub.cfg` stays as it is), and wait up to 30 min for `login:`; the install's late command
  writes the same timeouts into `/etc/systemd/system.conf.d/wsh-lab-tcg.conf`, for disks installed from now
  on (the stored disk predates it). Units with their own `TimeoutSec=90s` (`systemd-modules-load`,
  `systemd-journal-flush`) can still fail on a busy host; the boot gets past them.

**In the matrix:** `matrix_skip` like Tribblix: neither the weekly install matrix (240 minutes) nor the
monthly `--reinstall all` (720 minutes) installs it; it is installed on request (`pve_matrix.py install
--reinstall debian13-sun4u`, which also needs the apt cache, `matrix_needs`), and otherwise the stored
disk `install-debian13-sun4u.raw` (in `--disks`) is boot-tested, without any network.

Tested 2026-11-22 on the lab host (TCG, one install at a time, other matrices on the host):

| Run | Result | Time |
| --- | --- | --- |
| `debian13-install-sparc64.py` with the lab's own QEMU (published pve-qemu-kvm 11.1.3-4+wsh4), `NET=user`, `GATEWAY=10.0.2.2 DNS=10.0.2.3` | passed; then `debian13-firstboot.py` and `debian13-boot-disk.py` on the disk: passed | 153.9 min; 5.0 and 4.6 min |
| `install debian13-sun4u --vmid 9913 --check --gateway 10.0.2.2 --dns 1.1.1.1 --export <disks>` (the PVE test container from the published packages: pve-qemu-kvm 11.1.3-4+wsh8, qemu-server 9.2.20+wsh7, pve-manager 9.2.32+wsh11; its `vmbr0` given 10.0.2.2 and NATed out by hand) | passed and exported; the check: `ssh` active, `enp2s0` 10.0.2.15/24, the route via 10.0.2.2 | 177.4 min (install 9947 s, first boot 385 s, check 285 s) |
| `boot-test debian13-sun4u` of the stored disk | passed (GRUB, `login:`, the check commands, `poweroff`) | 4.9 min |

The boot test on a busy host, 2026-11-24 (the stored disk's copies; pve-qemu-kvm 11.1.3-4+wsh13, qemu-server
9.2.20+wsh7, pve-manager 9.2.32+wsh12; the lab host has 14 cores):

| Run | Result | Time |
| --- | --- | --- |
| `debian13-boot-disk.py` with the lab's own QEMU, host idle (load 0-1) | passed; no systemd timeout; `login:` 209 s after the initrd | 4.6 min |
| `boot-test debian13-sun4u` through PVE, host idle | passed, but the swap device timed out (swap off); `login:` 261 s after the initrd | 5.8 min |
| the same VM booted again while other jobs loaded the host (load 19-34) | `/boot`'s device, swap, ttyS0 and journald's start timed out; emergency mode, no `login:` | stopped after 21 min |
| with the GRUB options, the lab's own QEMU, host load 3-14 | passed; `/boot`'s device found at 147 s, swap at 188 s (kernel time), no timeout | 6.7 min |
| all at once with 8 CPU-bound loops (host load 32-43): 4 boots without the options, 4 with them, 1 `boot-test` through PVE with them | without: 4 of 4 `no 'login: ?$' within 900s` (`/boot` and swap timed out, `local-fs.target` failed); with: 4 of 4 reached `login:`, 15-16.5 min after the initrd, 3 passed; the PVE boot test passed (`login:` 20 min after the initrd) | 15.5 min; 19.5-22.8 min; 27.5 min |

The one that reached `login:` and failed was a different fault: during `poweroff` a `READ DMA` on the IDE disk
timed out with the drive's status `DRDY` (the command done, its interrupt never seen), libata fell back to
PIO, every further command timed out the same way, ext4 aborted its journal and `poweroff` didn't finish in
600 s. Once in 9 boots, only at that load. The cause was QEMU's sunhme, not the IDE controller: when
`poweroff` takes the interface down Linux resets the NIC and frees its interrupt, the model kept receiving,
and the interrupt of the next frame was never cleared, so the sabre held every IDE interrupt behind it.
Fixed by pve-qemu `wsh/0135` (`submodules/SPARC.md`, "The lost IDE interrupt at Debian 13's power-off").

Not tried: `--apt-proxy` (the pinhole), DHCP (`--ip dhcp` is refused; the hand install used it and got
its lease), `--user` through PVE (the lab run added one), the VGA console.
### Debian GNU/Linux 7 on sun4u

`debian7-sun4u` installs Debian GNU/Linux 7.11 "wheezy", the last official Debian release for sparc
(32-bit userland, the sparc64 kernel Linux 3.2.0-4, SILO), on the sparc64 profile: sun4u, OpenBIOS,
512 MB, `vga: serial0`, a blank 8 GiB disk on `ide0`, CD 1 (`debian-7.11.0-sparc-CD-1.iso`) on
`ide2`, `sunhme` (`eth0`). It is the first installed Linux disk on sparc64 here (Debian 12's install
fails, `submodules/SPARC.md`, "sparc64 (sun4u)"). Everything comes from CD 1, so the install needs no
router, name server or apt cache, and `pve_matrix.py install` installs it like the BSD targets.

1. **Install** (the `unattended` method, `debian-install-sparc.py` with `ARCH=sparc64`; the same
   scenarios as Debian 4.0, `_debian.py` picks the machine by `ARCH`). `install.Unattended` writes the
   answer CD (`answer_media.preseed_wheezy()` and the loader `wshlab`) and puts it on `ide3`, the
   secondary slave: Linux's `sr1`, after CD 1 on the secondary master (`sr0`). OpenBIOS boots CD 1
   (`Trying cdrom:f...`, SILO 1.4.14) and the scenario types at SILO's `boot:`
   (`_debian.boot_line64()`):
   `install priority=critical locale=en_US preseed/early_command="modprobe pata_cmd64x;modprobe sr_mod;modprobe isofs;until mount -r -t iso9660 /dev/sr1 /mnt;do sleep 1;done;sh /mnt/wshlab"`.
   `wshlab` loads `preseed.cfg` with `debconf-set-selections`, unmounts the CD (`umount -l`: plain
   `umount` fails with "Device or resource busy", the script itself is open on it, and d-i shows
   "Failed to run preseeded command") and deletes its device, so `cdrom-detect` and `apt-setup` see
   only CD 1. The preseed file: static `eth0` (a router and name servers only when given), no
   network mirror (`apt-setup/use_mirror false`, no security or updates services), the disk with
   partman-auto's recipe (`/boot` ext2 128 MB first, `/` ext3, swap 385 MB; partman writes the Sun
   label), the kernel `linux-image-sparc64`, root's hash `*`, no user, tasksel's "SSH server" and
   `openssh-server`, SILO on the disk. The scenario stops the VM at the kernel's `Restarting system`
   (with the published package the firmware's RAM clear after that reset took minutes, see below).
2. **First boot** (`debian-firstboot.py`): OpenBIOS boots SILO from the disk (`Trying disk:a...`),
   SILO loads `/vmlinuz` and `/initrd.img` (10 MB) by itself after its 10 s timeout, root logs in on
   `ttyS0` without a password (the installer's `T0:23:respawn:/sbin/getty -L ttyS0 9600 vt102`),
   `passwd root`, the marker, the optional user, `poweroff`.
3. **Check** (`debian-boot-disk.py`): the target's commands (`uname -a`, `hostname`, the marker,
   `/etc/debian_version` `7.11`, `df -k`, `/proc/partitions`, `ifconfig`, `route -n`, `resolv.conf`,
   `sources.list`, `netstat -ltn`, `pgrep -l sshd`), `poweroff`.

What the installed system does (lab QEMU, published pve-qemu-kvm 11.1.3-4+wsh3 unless said otherwise):

- `login:` 126-150 s after SILO (152-164 s from QEMU start); `sshd` listens on port 22.
- **DHCP:** with `iface eth0 inet dhcp` in `/etc/network/interfaces`, `ifup eth0` gets 10.0.2.15
  from QEMU's user network (`DHCPOFFER from 10.0.2.2`), the default route via 10.0.2.2 and
  `nameserver 10.0.2.3`; with `deb http://archive.debian.org/debian wheezy main`, `apt-get -o
  Acquire::Check-Valid-Until=false update` fetched 11.5 MB (the expired archive keys give a
  `KEYEXPIRED` warning, as for etch). Under that load `sunhme` logged "Happy Meal out of receive
  descriptors, packet dropped" once.
- **`poweroff`** ends QEMU with exit code 0, 15 s after the command.
- **`reboot`** works through OpenBIOS 0030's firmware reset, but with the published package the
  firmware's RAM clear after the reset crawled: QEMU still held 600 000-1 600 000 translated blocks
  from Linux, and each store to a page full of them is slow (`submodules/SPARC.md`, "Debian 7 on
  sun4u"). The installer's final reset (1024 MB, after 85 minutes) reached the banner after about 5
  minutes, a `reboot` after a minute at the shell (512 MB) after 336 s. With
  pve-qemu `wsh/0112` (a TB flush on every reset after the power-on one) the banner comes 2 s after
  `Restarting system` and `login:` 172 s after it.
- **Idle:** see "Idle" below (pve-qemu `wsh/0110`).

The boot-test VM has a new MAC, which wheezy's udev (`70-persistent-net.rules`) names `eth1`, so the
boot test runs with the network down, as for etch; the check doesn't need it.

Tested 2026-11-22 on the lab host. Lab runs with the published pve-qemu-kvm 11.1.3-4+wsh3 (the lab
image), PVE runs in the PVE test container built `--no-cache` from the published packages
(pve-qemu-kvm 11.1.3-4+wsh4, qemu-server 9.2.20+wsh7, pve-manager 9.2.32+wsh11, libpve-storage-perl
9.1.18+wsh2), one install at a time, other agents' work on the host (1-minute load 2-17):

| Run | Result | Time |
| --- | --- | --- |
| CD 1 and the netinst, `serve`, Return at SILO | "Select a language" on ttya | ~60 s |
| the install by hand through `serve` (1024 MB, the first preseed loader) | installed; d-i showed "Failed to run preseeded command" (the loader's plain `umount`), the answers were loaded anyway and the install went on; the reset's firmware banner after about 5 minutes (RAM clear) | 84 min to the reset |
| that disk: SILO, `login:`, DHCP, `apt-get update`, `poweroff`, `reboot` | as described above | |
| `debian-firstboot.py ARCH=sparc64 ROOT_PASSWORD=wshlab USER=lab`, then `debian-boot-disk.py ARCH=sparc64` with the target's commands, on copies | passed; `7.11`, `/boot` 120 MB ext2 on `sda1`, `/` 7.5 GB on `sda2`, swap on `sda4`, `sshd` on port 22 | 197 s, 179 s |
| `debian-install-sparc.py ARCH=sparc64` (the final loader), the lab's own QEMU, to the kernel | `-boot d`, the boot line typed, `Kernel command line: ... early_command`, no preseed error (stopped there: one install at a time) | 2 min |
| `pve_matrix.py install --only install-debian7-sun4u`, empty `--disks` (`lab.py install debian7-sun4u --check --export`) | passed and exported (`install-debian7-sun4u.raw`, 8 GiB, 836 MB allocated); the answer CD in `ide3` and gone afterwards, `boot: order=ide0` | 68.5 min (install 3693 s, first boot 219 s, check 176 s) |
| the same again, the disk stored | `boot-test debian7-sun4u` passed | 175 s |

Not tried: `--ip dhcp` (refused, as for etch), `--user` through PVE (the first boot's `useradd` ran in
the lab), `--vlan`, VGA, more memory, the netinst with a network mirror, `reboot` through PVE.

### The Tribblix install target

`tribblix-m34-sun4u` installs Tribblix m34 for SPARC (illumos) from its live CD
(`tribblix-sparc-0m34.iso`, from iso.tribblix.org; the download page's SHA-1 matches) on the
sparc64 profile: sun4u, OpenBIOS, 2048 MB, a blank 8 GiB disk on `ide0`, the CD on `ide2`,
`sunhme`, `vga: serial0`. It needs `openbios-sparc64` with patches 0016 and 0017 (in pve-qemu-kvm
11.1.3-2+wsh20 and later; see `submodules/SPARC.md`, "Tribblix on sun4u"): with the firmware of
11.1.3-2+wsh16 the live CD stops or hangs on most boots, and a ZFS root doesn't boot. With the
published 11.1.3-2+wsh21 the install took 207 minutes on 2026-11-19; its disk is kept as
`install-tribblix-m34-sun4u.raw` and boot-tested in about 26 minutes (see "Install once, then
boot-test the stored disk").

1. **Install** (`tribblix-install-sparc64.py`): the live CD boots by itself (`-boot order=d`),
   imports its SMF manifests, asks for the keyboard layout (Return) and comes to `console login:`;
   the scenario logs in as root with the live CD's password (`tribblix`), turns off bash's bracketed
   paste mode (its `ESC [?2004l` in front of each command's output hid `shell()`'s marker), finds the
   IDE disk (`c1t0d0`, the one at `ide@3/dad@0,0`), takes the network down and runs
   `/root/live_install.sh -G -n <host name> c1t0d0` (Tribblix's default: a ZFS root pool on the whole
   disk; FMA marks the disk DEGRADED during the copy, see SPARC.md). It powers off with `init 5`.
   `ROOT_FS=ufs` labels the disk instead (`format-a-disk.sh`, then `fmthard`: slice 0 for `/`,
   `SWAP_MB` = 1 GB of swap on slice 1) and runs `echo y | /root/ufs_install.sh -n <host name>
   c1t0d0s0` (its newfs asks); that ran through PVE up to its last steps but hasn't been booted.
2. **First boot** (`tribblix-firstboot.py`): root logs in with `tribblix` (the installer copies the
   live CD's `/etc`), `passwd root` sets the target's password (with `MINNONALPHA` relaxed for that
   call, as on Solaris 10), `passwd -l jack` locks the live CD's user, the marker, the network with
   `ipadm` (`-T static` with the address and `route -p add default`, or `-T dhcp`), DNS
   (`/etc/resolv.conf`, `nsswitch.dns`), the optional user, `zpool clear rpool` (the DEGRADED mark),
   `init 5`. NWAM (`network/physical:nwam`) is switched off for `network/physical:default` first; its
   stop method times out under TCG and leaves it in maintenance, so the scenario polls and clears it
   instead of `svcadm disable -s`. The first boot imports the SMF
   manifests again (99 of them), which takes most of its time.
3. **Check** (`tribblix-boot-disk.py`, the target's `commands`): logs in with the password, records
   `uname -a`, `hostname`, the marker, `df -k /`, `prtvtoc` of the disk, `ipadm show-addr`, the routes
   and `resolv.conf`, requires `target=<name>`, `init 5`.

**Offline on purpose.** The live CD's package catalogue is older than the packages on the CD
(the install asks for `TRIBcurl.8.12.1.1.zap`, `/pkgs` on the CD has `TRIBcurl.8.19.0.0.zap`), so the base overlay's install
looks for some packages on pkgs.tribblix.org instead of the CD. With a network it fetched them (and
some downloads failed with `has wrong size`); without one those packages are skipped (`pkgadd:
ERROR: no packages were found`) and the rest of the system comes from the live CD's own root, which
`live_install.sh` copies first. The scenario takes the network down before the install so the
result doesn't depend on the internet.

**Slow.** Under TCG with other guests on the host: about 45-72 minutes from power-on to the live
CD's login prompt (most of it the SMF import), 48-64 minutes for `live_install.sh`, 60-70 minutes
for the installed system's first boot (it imports the 99 SMF manifests again), 12-17 minutes to the
login prompt on later boots (no import), and `init 5` takes 4-13
minutes because service methods time out on the way down (`_tribblix.power_off()` waits 30). Many
service methods time out on the way up as well (`svc:/network/location`, `rbac`, `routing/route`,
`update-man-index`; `svc.startd` kills them); the system comes up anyway. Before pve-qemu
`wsh/0036` the guest's clock stopped for good in about one of three long runs (submodules/SPARC.md,
"Tribblix on sun4u": a race in QEMU) and the phase stalled until its timeout.

Tested in the lab and in the PVE test container on the lab host (TCG, pve-qemu-kvm 11.1.3-2+wsh16
with `openbios-sparc64` built from this branch's patches, qemu-server 9.2.18+wsh1, pve-manager
9.2.30+wsh1; the container's packages from Proxmox's no-subscription and test repositories, which
the published packages needed that day), 2026-11-18:

| Run | Result | Time |
| --- | --- | --- |
| live CD, lab, firmware without 0016 (wsh15, wsh16, 0001-0011, 0001-0015), 7 boots | 4 corrupted registers (window spill loop, `bad stack overflow at TL 2`), 2 dead clocks, 1 to the keyboard question | |
| live CD, lab, with 0016: by hand, `live_install.sh -G` offline | passed: `install-exit=0`, 33 packages installed, 18 skipped (offline), `rpool` DEGRADED (FMA, no data errors) | login ~45 min, install 64 min |
| the same with a network | the clock stopped during the overlay install | |
| installed ZFS disk, firmware without 0017 | `Unhandled Exception 0x30` in the boot block | |
| installed ZFS disk, with 0017: first boot by hand | `tribblix-m34 console login:` after the SMF import | ~60 min |
| `tribblix-firstboot.py` on that disk (static, `--user`) | passed: root's password, `jack` locked, marker, `hme0/v4 static 10.0.2.15/24`, default route, DNS, user `lab` | 38 min (login 17, power-off 9) |
| `tribblix-boot-disk.py` on that disk | the commands passed (`target=tribblix-m34-sun4u`, `hme0/v4` static after the reboot, `jack LK`, `lab`); the default route was missing after the reboot (since then also in `/etc/defaultrouter`); `init 5` took longer than the 900 s the scenario waited then (now 1800) | login 16 min |
| `tribblix-install-sparc64.py ROOT_FS=zfs`, lab | passed: disk `c1t0d0` found, offline, `live_install.sh` exit 0, 18 packages skipped, `rpool` DEGRADED, `init 5` | 106 min (live CD login 55, install 48, power-off 3) |
| `lab.py install tribblix-m34-sun4u --vmid 9401`/`9402` (ZFS, first versions) | the live CD booted through PVE, login after 48 min; the scenario's marker never matched behind bash's bracketed paste escapes (fixed); stopped | |
| `--vmid 9403` (UFS) | label written, `ufs_install.sh` waited at newfs's `(y/n)?` (fixed: `echo y \|`); stopped | |
| `--vmid 9404` (UFS) | the clock stopped during the live CD's SMF import (11/95); stopped | |
| `--vmid 9405 --check` (UFS) | see below | |
| unit tests (`test_targets.py`, `test_dos.py`, `test_vgatext.py`) | 78 passed | 6 s |
| `matrix.py sparc64` and `solaris10` with the 0013-0017 firmware | 9/9 and 2/2 passed | |

With pve-qemu `wsh/0001-0037` (`qemu-system-sparc64` built from the branch, `wsh/0036` fixing the
clock) and the 0001-0017 firmware, in the PVE test container (`wsh/0001-0039` for the lab runs),
2026-11-18, three long runs at once with other emulated guests on the host:

| Run | Result | Time |
| --- | --- | --- |
| `lab.py install tribblix-m34-sun4u --vmid 9801 --check` | passed: offline install, 18 packages skipped, first boot (static `hme0`, root's password, marker), check | 257 min: install 141 (live CD login 61), first boot 89 (login 70, 99 manifests imported), check 26 (login 14) |
| one more boot of that disk (`tribblix-boot-disk.py --pve 9801`) | passed, no SMF import | login 12 min, `init 5` 6.5 min |
| `tribblix-install-sparc64.py`, lab, twice | passed both: `live_install.sh` exit 0, 18 packages skipped | 141 min each (live CD login 72, install 64) |

### NeXTSTEP 3.3 and OPENSTEP 4.2 (catalogue)

`nextstep33-ss5` and `openstep42-ss5` are catalogue entries: with the published pve-qemu-kvm
(11.1.3-2+wsh21 and +wsh22) both installers hang in NeXT's SCSI driver, an ESP interrupt that comes too early
(`submodules/SPARC.md`, "NeXTSTEP 3.3 and OPENSTEP 4.2", has the diagnosis, the results per machine
and firmware and the QEMU fix). pve-qemu patch `wsh/0040` lets the ESP's interrupt come later
(`-global sysbus-esp.irq-latency-us=500`, off by default); qemu-server's `machine:
SS-5,esp-irq-latency=500` passes it, and the entries' profiles set it. With a `qemu-system-sparc`
built from 0001-0041 both install on an SS-5 and reach the Workspace (in the lab with `-global`, and
NeXTSTEP also through PVE with the option). The entries stay in the catalogue until published
packages have both and the scenarios below exist. What a scenario will have to do, from the lab runs (2026-11-19, by hand with
`serve`/`ctl`, no scenario file yet):

- **Machine:** `VGA=tcx` (NeXT has no cg3 driver; its S24 driver runs the 8-bit TCX), a blank disk
  (1-3 GiB tested; the installer writes a NeXT label), `BIOS=ss5.bin CONSOLE=fb` for the disk.
  OpenBIOS boots the CD but not the installed disk; the CD stage also runs under `ss5.bin` (`setenv
  diag-switch? false`, then `boot cdrom`). SS-20: no firmware boots the installed disk.
- **Everything is on the framebuffer** with the Sun keyboard (`fb_type`, `fb_key`), and OCR reads
  the text stage (tesseract misreads "Type" as "Tue"/"Tupe" and "start installing" as "start,
  installing": match on other words). The CD stage: `English language` → `1`, `prepare to install`
  → `1`, `on this disk` → `1`, `Ready to install` → `1`, then `restart the computer` → Return
  (about 2-4 min).
- **Each disk boot under `ss5.bin`:** after a failed network boot the first `boot disk` restarts the
  PROM, so `setenv diag-switch? false` first; at NeXT's `boot:` type `-v` within its 10 s (its boot
  graphics end in `Data Access Error` on QEMU's TCX). The lab typed `-v` and Return every 2 s from
  `boot disk` on, because OCR polling is slower than the countdown: 30 s was sometimes too short
  (the PROM's restart came first), 60-90 s worked. Then Control-C at "No response from network
  configuration server".
- **Configure's "Summary of Devices"** needs the pointer on Save (608,457 at 1024x768): HMP
  `mouse_move` in steps of at most 10 (NeXT accelerates; a step of 10 moves about 9 pixels), with the
  pointer found in the screendump by its shape and the move corrected until it is there, then
  `mouse_button 1`/`0`. From the pointer's start near (100,100), 40 `mouse_move 10 10` and 16
  `mouse_move 10 0` land on Save on both systems. OCR can't read this panel (light grey), so it
  has to be recognised another way. The Installer's package list and Restart, and the language panel and its
  alert after the reboot, take Return.
- **Times** (TCG, one guest at a time or two): the CD stage 2-4 min, the packages 6 min (NeXTSTEP,
  293 MB) to 15 min (OPENSTEP, 532 MB), each boot to the desktop 2-3 min.

### Disk sizes

`targets.DISKS` names the disks `--disk-size` offers after the templates they reproduce, and each
Sun-labelled target lists the ones it was tested with (`sun_disk("3G", "9G")`: `sizes`, the first
the default); `install.disk_choice()` refuses any other. `sunlabel.write_disk()` writes the label
and its five backup copies (odd sectors 1-9 of the last track), so its images are the templates:
`cmp` against `sparc-SUN2.9G.raw.template.xz` and `sparc-Qemu9G.raw.template.xz` decompressed
found no difference, and `tests/test_targets.py` pins each template's label sector (sha256) and its
non-zero sectors. The 9G geometry is the owner's template's (QEmu8G: 16202 data + 2 alternate
cylinders, 16 heads, 60 sectors, pcyl 16204 in the label; the sparc guide's "custom type" line
says 16200/2/16202), not a new one. `--data-disk` uses `sunlabel.data_geometry()` (16 heads x 128
sectors, 1 MiB per cylinder, slice 0 and 2 the whole disk) and needs no `format` in the guest;
`sunlabel.py disk|data` writes either kind from the command line.

Tested in the PVE test container on the lab host (published packages, the package built from
this branch, one guest at a time), 2026-11-17:

| Run | Result | Time |
| --- | --- | --- |
| `install sol26-ss5 --disk-size 9G --check` | passed; the installer lists `c0t3d0 (7594 MB) boot disk`, auto-layout `/` 83 MB, swap 148 MB, `/usr` 242 MB, `/export/home` 7120 MB; `df -k`: `/` 80335 KB (22292 used), `/usr` 232831 (152500), `/export/home` 7174949 (9); `prtvtoc`: 16204 cylinders, 16202 accessible, slices 0 (0-171839), 1, 2, 6, 7 (971520-15553919) | 12.2 min (429 s, 184 s, 106 s) |
| `install sol26-ss20 --disk-size 9G --data-disk 2 --check` | passed; auto-layout as on SS-5 but swap 295 MB (512 MB of memory) and `/export/home` 6973 MB; `df -k` `/export/home` 7026317 KB; the data disk: `prtvtoc` 2048 cylinders (2046 accessible) of 16 x 128, slice 0 4190208 sectors, `newfs` 2046 MB in 64 cylinder groups, `/data` 2030575 KB mounted from `/etc/vfstab` at the check boot | 12.3 min (408 s, 205 s, 107 s) |
| `install sol26-ss5 --disk-size 8G` | refused: `is tested with 3G, 9G`, exit 1, nothing created | 0 s |

Solaris 7 on the 9G disk, 2026-11-18 (published packages: qemu-server 9.2.18+wsh3, pve-manager
9.2.30+wsh2, pve-qemu-kvm 11.1.3-2+wsh16, libpve-storage-perl 9.1.18+wsh1; the host shared with
three other agents' runs). Nothing but the targets' `sizes` changed: Solaris 7's installer and kernel
take the QEmu8G label as 2.6's do (16204 cylinders, far below the label's 65535 and the 1 TB VTOC and
UFS limits of a 32-bit kernel), and auto-layout puts `/` at cylinder 0 as on the 3G disk:

| Run | Result | Time |
| --- | --- | --- |
| `install sol7-ss20 --disk-size 9G --check` | passed; the installer lists `c0t3d0 (7594 MB) boot disk`, auto-layout `/` 89 MB, swap 295 MB, `/usr` 299 MB, `/export/home` 6910 MB; `df -k`: `/` 85615 KB (23990 used), `/usr` 288143 (186974, 72355 free), `/export/home` 6963389 (9); `prtvtoc`: 16204 cylinders, 16202 accessible, slices 0 (0-182399), 1, 2, 6, 7 (1400640-15553919) | 11.7 min (382 s, 208 s, 93 s) |
| `install sol7-ss5 --disk-size 9G --check` | passed; as on SS-20 but swap 148 MB (256 MB of memory) and `/export/home` 7057 MB; `df -k` `/export/home` 7111805 KB, `/usr` the same 288143 (72355 free) | 14.1 min (529 s, 204 s, 95 s) |
| `install sol7-ss20 --disk-size 8G` | refused: `is tested with 3G, 9G`, exit 1, nothing created | 0 s |

3G stays Solaris 7's default: End User fits it with room to spare, the 9G install took about a minute
longer on SS-20 (the bigger `/export/home` newfs; the SS-5 run's longer install phase is within the
busy host's spread), and 2.6 has the same default. Solaris 8 defaults to 9G because its Entire Group
needs more than 3 GB.

Not done: a 9G install of Solaris 2.5.1 (Solaris 8 and 9 are tested with the 9G disk only,
a 3G one not tried); the in-guest `format` route for a
blank second disk.

### Solaris post-install

Three options for the Solaris targets, after the first boot:

- `--data-mount /usr/local` (with `--data-disk`): the first boot mounts the data disk on `/usr/local`
  instead of `/data` (`solaris-firstboot.py`, `DATA_MOUNT`; anything already in `/usr/local` is
  copied onto the new file system first). `/data` stays the default: it is what `--data-disk` was
  tested and documented with, and an empty `/usr/local` on its own disk only pays off once something
  installs there, which is what `--post-install` does (it picks `/usr/local` by itself).
- `--post-install BUNDLE` (`targets.POST_INSTALL`): a CD of SVR4 packages goes into its own drive
  (`scsi5`, `c0t5d0`) for one more boot only, and is removed again whatever that boot did, as the
  Red Hat answer CD is (`install.PostInstall`). `solaris-post-install.py` checks that the bundle's
  `basedir` is the data disk in `df -k`, makes the drive's device nodes (`drvconfig; disks`), stops
  vold, mounts the CD (`mount -F hsfs -o ro`), writes an admin file (`mail=`,
  `instance=overwrite`, `partial`, `runlevel`, `idepend`, `rdepend`, `space`, `setuid`, `conflict`
  and `action` `nocheck`, `basedir=default`) and runs `pkgadd -n -a <admin> -d <datastream> all` for
  every datastream in the bundle's directory, one console line per package (`pkgadd ok: <pkg>` or
  `pkgadd FAILED (exit N)`), pkgadd's own output in `/var/sadm/wsh-lab-<bundle>.log` and the added
  instances in `/etc/wsh-lab-<bundle>.pkgs`. Exit codes 0, 10 and 20 count as added; the phase fails
  when one package fails or none was added. A bundle needs `--data-disk` (its packages go to
  `/usr/local`; `/usr` has about 70 MB free on the 3G and 9G layouts) and is offered only on the
  targets it was tested on: Solaris 2.6 and 7 on SS-5 and SS-20 (the 2.6 packages run on 7).
- `--local-env` (with `--post-install`): `/usr/local/bin` and `/usr/local/sbin` at the end of `PATH`
  and `MANPATH` in `/etc/profile` and in the `--user` account's `~/.profile`, and that account's login
  shell the bundle's bash (`usermod -s`). Root keeps `/sbin/sh`: single-user mode mounts only the root
  file system, so a root shell on the data disk would leave no way to log in for repairs (and `/sbin/sh`
  is statically linked for that reason). Appending rather than prepending keeps Sun's commands first
  for everyone; the user can reorder `PATH` in `~/.profile`.

`--check` then also checks that `/usr/local` is the data disk (`df -k`), runs the bundle's commands
(`bash --version`, `vim --version`, `wget --version`), that `pkginfo` knows every package the
post-install added and, with `--local-env`, root's `PATH`, root's shell and the user's login shell and
`which bash` (`MORE_COMMANDS`/`MORE_EXPECT` in `solaris-boot-disk.py`, one console line per command:
the tty takes 256 characters a line).

The one bundle, `sun26gnu`, is the owner's own CD image of free software packages for Solaris 2.6
(`sun26gnu.iso` in `MEDIA`, `local_only`: no URL, in no target's media, so neither CI nor the
matrices ever ask for it). Only its `gnu/pkgs` directory is used: 34 package datastreams (bash 4.1,
coreutils, vim 7.3, wget, curl, less, screen, sudo, rsync, openssl, ncurses, libgcc and others), all
with `BASEDIR=/usr/local`. The CD's own `installgnu.sh` isn't used (csh, waits for Enter, expects vold's
`/cdrom/sun26gnu`); the image has no Rock Ridge (Joliet only), so Solaris sees its ISO 9660 names in
lower case (`bash_4.1_sol26_sparc_local`), which `pkgadd -d` takes as they are. Its patches and
third-party programs are left alone. Neither the image nor anything from it is in the repository, and
runs with it are not published as recordings.

Tested in the PVE test container on the lab host, 2026-11-18 (published packages: pve-qemu-kvm
11.1.3-2+wsh17, qemu-server 9.2.18+wsh4, pve-manager 9.2.30+wsh3; up to three of these installs at
once on a host shared with other agents' runs, so the times are on the slow side). The runs are
local evidence only, not recordings for the docs:

| Run | Result | Time |
| --- | --- | --- |
| `install sol26-ss20 --ip 10.0.2.16 --data-disk 2 --post-install sun26gnu --local-env --user lab --check` | passed; `/usr/local` was empty on the installed system (nothing to copy), the first boot mounted the new UFS there (`df -k` 2030575 KB); the post-install boot: `/usr/local` the data disk from `/etc/vfstab`, `pkgadd ok` for all 34, `post-install sun26gnu: 34 installed, 0 failed`, 168050 KB used; `lab`: `PATH=/usr/bin::/usr/local/bin:/usr/local/sbin` and `/usr/local/bin/bash` from a login shell; the check boot: `GNU bash, version 4.1.0(2)-release (sparc-sun-solaris2.6)`, `VIM - Vi IMproved 7.3`, `GNU Wget 1.12 built on solaris2.6.`, `pkginfo knows 34 of 34 packages`, root's `PATH` ends in `/usr/local/bin:/usr/local/sbin`, `root:/sbin/sh`, `lab:/usr/local/bin/bash`, `which: /usr/local/bin/bash`; `scsi5` gone from the config | 24.6 min (install 589 s, first boot 297 s, post-install 412 s, check 148 s) |
| `install sol26-ss5 --ip 10.0.2.17 --data-disk 1 --post-install sun26gnu --check` | passed; 34 installed, 0 failed; `/usr/local` 984047 KB, 168050 used (19%); the check's five commands as above | 23.8 min (597 s, 287 s, 374 s, 136 s) |
| `install sol7-ss20 --data-disk 2 --post-install sun26gnu --local-env --user lab --check` | passed; the 2.6 packages install and run on Solaris 7 (`SunOS sol7-ss20 5.7 Generic_106541-02`): 34 installed, 0 failed, the same 168050 KB, every check as on 2.6 | 23.2 min (507 s, 265 s, 453 s, 134 s) |
| `install sol7-ss5 --ip 10.0.2.18 --data-disk 1 --post-install sun26gnu --local-env --check` (no `--user`: `/etc/profile` only) | passed; 34 installed, 0 failed; `/usr/local` 984047 KB, 168050 used; root's `PATH` ends in `/usr/local/bin:/usr/local/sbin`, `root:/sbin/sh` | 21.7 min (451 s, 245 s, 438 s, 131 s) |

Adding the 34 packages takes 4 to 5 minutes of the post-install boot (the rest is the boot, the
typing and `init 5`). Two earlier runs failed and changed the scenarios: a regex that ended in `\s*$`
took the newline before the prompt when the output had only arrived up to it, so the prompt's
`\n#` never came (now `[ \t]*$`); and `su - lab -c 'which bash'` printed `no bash in /usr/bin .`:
Solaris's `su` runs the user's shell with `-c` but not as a login shell, so neither `/etc/profile`
nor `~/.profile` was read (now `su - lab -c '$SHELL -l -c "which bash"'`). Not tried: a 9G first
disk with the post-install (the data disk is the same either way), DHCP, and a reboot of the
finished VM by hand beyond the post-install and check boots, which both mount `/usr/local` from
`/etc/vfstab`.

### Network

`install.network_choice()` turns `--ip` (an address or `dhcp`), `--netmask`, `--gateway`, `--dns`,
`--domain` and `--vlan` into one checked setting: a mode the target lists in `net_modes` (what was
tested), addresses that parse, a router inside the subnet, at most three name servers, a VLAN tag of
1-4094; anything else exits before a VM is made. `--vlan` becomes `tag=` on `net0` at creation.
The installer always gets a static address (Solaris 2.6's has no DHCP screen and no DNS choice:
NIS+, NIS, Other, None); `solaris-firstboot.py`'s `network()` then writes what 2.6's start-up
scripts read (`rootusr`, `inetinit`, `inetsvc`, read on the installed system):
`/etc/netmasks` under the classful network number (2.6's lookup key) and the subnet's,
`/etc/defaultrouter`, `/etc/resolv.conf` and `hosts: files dns`, or for DHCP `/etc/dhcp.le0` (the
scripts then run `ifconfig le0 auto-dhcp primary`, set the host name from `dhcpinfo Hostname`, or
`unknown`, take the router from the lease, and write `resolv.conf`, the `hosts:` line and the
`/etc/hosts` entry). The marker gets a `network=` line and the VM's notes a `Network:` line with
the same text; the check phase records `ifconfig -a` and `netstat -rn`.

Before this change the installer's address had no `/etc/netmasks` entry and came up with the class
A mask (`inet 10.0.2.15 netmask ff000000`, read on an installed 9G VM), although the notes said /24.

The test network (in the PVE test container): `vmbr1`, VLAN-aware, with 10.77.0.1/24 untagged and
`vmbr1.20` 10.77.20.1/24 on VLAN 20, dnsmasq on both (DHCP .100-.150, router and DNS itself, domain
`lab.test`, `gw.lab.test`, `far.lab.test` = 10.78.0.1, an address of the container that the guest
reaches only through its default router). After each install (`--check`), a further boot ran
`hostname; ifconfig -a; netstat -rn; cat /etc/resolv.conf; ping gw.lab.test; ping far.lab.test;
nslookup far.lab.test` and required `far.lab.test is alive`. 2026-11-17:

| Run | Result | Time |
| --- | --- | --- |
| `install sol26-ss5 --bridge vmbr1 --ip dhcp --check` | passed; lease 10.77.0.111/24 from dnsmasq, default route 10.77.0.1 from the lease, `resolv.conf` (`domain lab.test`, `nameserver 10.77.0.1`) and `hosts: files dns # Added by DHCP` written by 2.6's own `inetsvc`; the client sent `sol26-ss5` as its name, dnsmasq echoed it (option 12), `hostname` = `sol26-ss5`; the further boot: `gw.lab.test is alive`, `far.lab.test is alive`, `nslookup` answered by 10.77.0.1 | 12.6 min |
| `install sol26-ss20 --bridge vmbr1 --vlan 20 --ip dhcp --check`, dnsmasq `dhcp-host=<MAC>,s20dhcp` | passed; `net0: lance=...,bridge=vmbr1,tag=20`; the lease came from the VLAN 20 side (`DHCPACK(vmbr1.20) 10.77.20.137`), so the tag reaches the wire; `hostname` = `s20dhcp` (the server's name wins); router 10.77.20.1, DNS as above, both pings | 12.7 min |
| `install sol26-ss5 --bridge vmbr1 --vlan 20 --ip 10.77.20.50 --gateway 10.77.20.1 --dns 10.77.20.1 --domain lab.test --check` | passed; `le0 10.77.20.50 netmask ffffff00`, `default 10.77.20.1`, `/etc/netmasks` `10.0.0.0 255.255.255.0` and `10.77.20.0 255.255.255.0`, `hosts: files dns`; both pings, `nslookup` | 12.7 min |
| `install sol26-ss20 --bridge vmbr1 --ip 10.77.0.60 --netmask 255.255.255.0 --gateway 10.77.0.1 --dns 10.77.0.1 --domain lab.test --check` | passed; `le0 10.77.0.60 netmask ffffff00`, `default 10.77.0.1`, both pings | 12.3 min |
| `install sol26-ss5 --bridge vmbr1 --ip dhcp --check` with dnsmasq `--dhcp-ignore-names` (a server that sends no name) | passed; lease 10.77.0.150, the boot prints `Hostname: unknown`, `hostname` and `uname -n` say `unknown`, and `/etc/hosts` gets `10.77.0.150 unknown # Added by DHCP`; the ping by name through the router works | 13.1 min |
| `--ip 10.0.2.15 --gateway 10.0.3.1`; `--ip dhcp --netmask 255.255.255.0` | refused before a VM is made: `--gateway 10.0.3.1 isn't another address in 10.0.2.0/24`; `--netmask and --gateway come from the DHCP server with --ip dhcp` | 0 s |

**MAC addresses.** On sparc32 the lance uses the MAC of `net0`: Solaris's `ifconfig le0` showed
`ether bc:24:11:ca:76:c9` for `net0: lance=BC:24:11:CA:76:C9` (and the same for every run above),
dnsmasq saw each DHCP VM's own `net0` MAC in its requests and gave each its own lease. That fits QEMU's
sun4m putting the NIC's address in the IDPROM; the sparc64 problem (the IDPROM's default MAC on
every VM) doesn't show on SS-5 or SS-20.

### The wsh-lab package

`packages/wsh-lab/` packages the lab as the optional Debian package `wsh-lab` in the apt repository
(`apt install wsh-lab`; the guide's "Install the lab on a node" is the user side):

- **Contents:** `lab.py`, `recording.py`, `install.py`, `targets.py`, `sunlabel.py`, `mcp_server.py`,
  `scenarios/*.py`, `tests/test_targets.py`, both requirements files and the asciinema player for the
  run pages, in `/usr/share/wsh-lab/`; `/usr/bin/wsh-lab` (`lab.py`, `--version` reads
  `/usr/share/wsh-lab/VERSION`) and `/usr/bin/wsh-lab-mcp` (the MCP server, run from the venv that
  `wsh-lab-mcp --setup` makes; see "MCP server"); two man pages. `Architecture: all`; `Depends`
  only on Debian's `python3-pyte`, `python3-pil` and `fonts-dejavu-core`; `Suggests`
  `tesseract-ocr`, `vpx-tools`, `python3-venv` and `qemu-server`. No package depends on it, and it
  depends on none of the patched packages. dh_python3 byte-compiles the private directory in
  postinst and removes the bytecode in prerm; the only maintainer script of its own is the postrm
  that removes `/var/lib/wsh-lab/mcp-venv` on purge (the install evidence there stays).
- **Version:** `packages/wsh-lab/version.sh`: `0.<N>+g<sha7>`, `N` the number of commits up to HEAD
  that touch the package's inputs (the files above and `packages/wsh-lab/`), `sha7` the newest of
  them. On main every change of an input raises `N`, and a commit that changes none of them gives
  the same version; the changelog is generated with that commit's date (`SOURCE_DATE_EPOCH`), so
  the same commit in the same build image builds the same `.deb`. No changelog commit is pushed.
- **Build:** `make wsh-lab` (in `packages/wsh-lab/build.Dockerfile`, Debian 13 pinned by digest,
  plain `dh`; `build.sh` assembles the tree, generates the changelog, runs `dpkg-buildpackage` and
  then lintian with `--fail-on error,warning`) into `build/wsh-lab/`. The two lintian overrides
  (the requirements files read as documentation) are in `debian/wsh-lab.lintian-overrides`.
- **Test:** `packages/wsh-lab/test.sh` in a clean `debian:trixie`: `apt install` of the `.deb`
  with its dependencies, `wsh-lab --version`/`--help`, `targets`, `media --dir` (missing, wrong
  size), `install` refused off a PVE node, the catalogue's tests against the installed copy,
  `wsh-lab-mcp` without a venv (explains, writes nothing to stdout), with `WSH_LAB_TEST_MCP=1`
  `--setup` (without `python3-venv`: refused with the hint; with it: the venv from PyPI) and
  `--check`, then `apt purge` and `autoremove`, after which the file system must be what it was
  before the install.
- **CI** (`.github/workflows/wsh-lab.yml`): on pull requests that touch the inputs, build, lintian
  and the test; nothing is published. On main, the same, then a release `wsh-lab-<version>` with the
  `.deb` (skipped when that release exists: one upload per version), then the Pages deploy
  (`repo-update.yml`), which downloads the `.deb` of the newest `wsh-lab-*` release into
  `repo/incoming` before `make repo-update`, so reprepro includes it with the four patched packages'
  debs. Without a release yet the repository is built as before.

Tested on 2026-11-16: two builds of the same commit gave byte-identical `.deb`s; lintian clean;
`test.sh` with `WSH_LAB_TEST_MCP=1` passed (10 catalogue tests, 1 skipped without the qemu-server
patch; the venv from PyPI; nothing left after the purge). In the PVE test container on the lab
host with the published packages and the package built from this branch installed by apt (no
checkout in the container), `wsh-lab install sol26-ss5 --vmid 9201 --check` passed in 11.9 min
(install 416 s, first boot 179 s, check 103 s).

## Recordings

Every run (`run` and `serve`, a QEMU of its own or `--pve`) records the serial console, and with a
framebuffer a time-lapse video of it, next to the rest of the evidence (`recording.py`):

- **`serial.cast`**: what the guest wrote to the serial console, as an
  [asciinema v2](https://docs.asciinema.org/manual/asciicast/v2/) cast: a header with the lab's terminal
  size (80x24), then `[seconds, "o", text]` per read from the socket, timed from the start of the
  run like `steps.log`, and a `[seconds, "m", "<n>. <title>"]` marker per step, which players show as
  chapters. The console isn't guaranteed UTF-8 (OpenBIOS and Solaris print ASCII and VT100
  sequences): bytes are decoded as UTF-8 where they are valid UTF-8 (a character split between two
  reads waits for the rest) and as Latin-1 otherwise, the way the lab's terminal emulator reads them,
  so the file is valid JSON and plays as the lab saw it. It starts with `ESC ) 0` (G1 = line drawing),
  which the emulator assumes. Only output: what the lab types shows as the guest echoes it, and keys
  typed on the framebuffer keyboard aren't serial output at all. Bounded at 32 MB of output
  (`LAB_CAST_MAX`; a marker says where it stopped, `serial.raw` keeps everything). Writing it costs
  nothing measurable (the lab's own CPU time for a 160 s boot was 0.28-0.36 s with and without it). A
  2.5 min boot is ~25 KB, the 9-10 min Solaris install 170-190 KB.
- **`serial.fast.cast`**: a viewing copy with every pause cut to 1 s (`CAST_MAX_IDLE`, what the
  asciinema player's idle time limit does) and then played 2x (`CAST_SPEED`), reads closer than 20 ms
  merged. The Solaris 2.6 install (553 and 630 s in two runs) plays in 158-183 s (68 KB; 358 s with
  pauses cut to 2 s alone: the installer's screens and the lab's typing leave hundreds of gaps under
  a second), a 155 s boot in 17 s.
- **`fb.webm`** (and **`fb.vtt`**), for a machine with a display (sparc32 with cg3/tcx; in attach mode
  any VM whose console isn't serial): a frame every second (`FB_VIDEO`, seconds; `0` = no video) taken
  from the display refresh the lab runs anyway (`REFRESH`: the frames are its screendumps, so there is
  no second poller and in attach mode no extra QMP connections; without a refresh the recording starts
  one at that interval), scaled to at most 1024 pixels wide (`FB_VIDEO_WIDTH`), kept only when it
  differs from the previous one. At the end they are encoded with `vpxenc` (VP9) at 10 frames a second
  (`FB_VIDEO_FPS`), each shown for its real time divided by 10 (`FB_VIDEO_SPEED`), between one video
  frame and 2 s: the 227 s `cg3-display.py` run at 1024x768 becomes a 17-19 s video of 270-300 KB
  (32-35 distinct frames). `fb.vtt` has the steps as captions. Cost on that run: the lab's CPU time
  went from 0.4 s to 2.4 s over the 224 s (under 1% of a core, the run took as long), plus ~3 s to
  encode at the end; the frames are PNGs in `_frames/` until then (a few MB at most). `vpx-tools`
  adds ~4.5 MB to the image; `ffmpeg` would add ~410 MB (258 packages). So it is on by default.

`result.json` lists them under `recordings` (durations, sizes, the step marker times, the video's
frame counts and encode time), and `index.html` plays them: the viewing copy in the asciinema player
(a copy of its pinned release next to the page, `asciinema-player.min.js` and `.css`, 200 KB, so the
page works opened from a downloaded artifact; the cast is inlined because a page opened from disk can't
fetch files next to it) and the video in a `<video>` element, each step with links that play from
there. The images fetch the player at build time (`recording.py fetch-player`: asciinema-player
3.17.0, Apache-2.0, from npm, its integrity hash checked) into `/usr/share/asciinema-player`; without
it the page links the cast files instead.

Casts contain everything the console showed, including what was typed and echoed (the scenarios'
root passwords are empty or test values).

`lab.py cast <run dir>` checks a cast (every line JSON, times never going back), writes the viewing
copy again with other limits (`--max-idle`, `--speed`, `--output`; the docs' install copy is
`--max-idle 1 --speed 3`, about 2 minutes) and, with `--check`, replays
the cast through the same terminal emulator and compares the screen at each step marker with that
step's `NNN-ttya.txt`:

```sh
docker run --rm -v /mnt/runs:/mnt/runs wsh-sparc-lab cast /mnt/runs/m1/sol26-disk-openbios-ss5 --check
```

No GIF or SVG rendering: that needs a terminal renderer (agg, svg-term) that isn't in the image; the
asciinema player is the way to watch them.

### Recordings in the docs

The [SPARC lab recordings](https://debian.wshosting.no/guides/sparc-recordings/) page and the SPARC
guide embed a few curated recordings. None of them is in git (a re-recording would replace the whole
file each time): they are the assets of a GitHub release tagged `media` (a prerelease, never
"latest", not a software release), and `repo-update.yml`, the job behind every Pages deploy, copies
them into the site as `/recordings/` (`gh release download media`). The site then serves them itself,
with content types from their extensions (the release serves octet-stream attachments without CORS,
which neither `<video>` nor the asciinema player's fetch can use). A deploy without the release or an
asset logs a warning and goes on.

The pages embed them same-site: `<LabCast src="/recordings/<name>.cast" caption="..." />` and
`<LabVideo src="/recordings/<name>.webm" captions="/recordings/<name>.vtt"
poster="/recordings/<name>-poster.png" />` (`docs/src/components/`). Where a file isn't there (a
fork, a local build, a deploy that couldn't fetch the release) they show a short note linking to the
release instead of a player. For local work, `npm run fetch-media` in `docs/` downloads the release
assets into `docs/public/recordings/` (git-ignored); `npm run build` doesn't need them.

| Asset | From | Made with |
| ----- | ---- | --------- |
| `sol26-install-ss5.cast` | `solaris-install-serial.py` on SS-5 (`pve` matrix: `sol26-install-ss5/1-solaris-install-serial`) | `lab.py cast <run> --max-idle 1 --speed 3 --output ...` |
| `sol26-boot-ss20.cast` | `machines`: `sol26-disk-openbios-ss20` | `--max-idle 1 --speed 1` |
| `netbsd-sparc64-pve.cast`, `alpine-aarch64-pve.cast` | `pve`: `netbsd-sparc64/1-netbsd-boot-cd`, `alpine-aarch64/1-alpine-boot-cd` | `--max-idle 1 --speed 1` |
| `sol26-cg3-ss5.webm`, `.vtt`, `-poster.png` | `display`: `sol26-disk-openbios-cg3-1024x768` | its `fb.webm`, `fb.vtt` and `001-fb.png` |
| `tribblix-m34-boot-sun4u.cast` | `install` (stored disk): `install-tribblix-m34-sun4u/1-boot-test-tribblix-m34-sun4u/check` | `--max-idle 1 --speed 2` |
| `sol10-boot-sun4u.cast` | `install` (stored disk): `install-sol10-sun4u/1-boot-test-sol10-sun4u/check` | `--max-idle 1 --speed 1` |
| `netbsd111-install-ss5.cast`, `netbsd111-boot-ss5.cast` | `install` (no stored disk): `install-netbsd111-sparc/1-install-netbsd111-sparc/install`, `.../check` | `--speed 2`, `--speed 1` |
| `sunos413-install-ss5.cast`, `sunos413-boot-ss5.cast` | `install` (no stored disk): `install-sunos413u1b-ss5/1-install-sunos413u1b-ss5/install`, `.../check` | `--max-idle 1 --speed 1` |
| `freedos14-install.webm`, `freedos14-boot.webm` (`.vtt`, `-poster.png`) | `install` (no stored disk): `install-freedos14/1-install-freedos14/install`, `.../check` | their `fb.webm`, `fb.vtt` and `001-fb.png` |
| `debian40-install-ss5.cast`, `debian40-boot-ss5.cast` | `lab.py install debian40-ss5 --check --gateway G --dns D --out <runs>/debian40-ss5/1-install-debian40-ss5`: `install`, `check` | `--speed 4`, `--speed 1` |
| `sol26-smp4-ss20.cast` | `pve_matrix.py recordings`: `sol26-ss20-smp4/1-solaris-boot-disk` | `--max-idle 1 --speed 1` |
| `sol22-install-ss10.cast`, `sol22-boot-ss10.cast` | `pve_matrix.py recordings`: `sol22-install-ss10/1-solaris-install-serial`, `2-solaris-boot-disk` | `--speed 2`, `--speed 1` |
| `sunos413-install-ss10.cast`, `sunos413-boot-ss10.cast` | `lab.py install sunos413-ss10 --check --out <runs>/install-sunos413-ss10/1-install-sunos413-ss10`: `install`, `check` | `--max-idle 1 --speed 1` |
| `sunos412-install-ss600mp.cast`, `sunos412-boot-ss600mp.cast` | `pve_matrix.py install --only install-sunos412-ss600mp` (no stored disk): `install-sunos412-ss600mp/1-install-sunos412-ss600mp/install`, `.../check` | `--max-idle 1 --speed 1` |
| `sol21-install-ss10.cast`, `sol21-boot-ss10.cast` | `lab.py install sol21-ss10 --check --out <runs>/install-sol21-ss10/1-install-sol21-ss10`: `install`, `check` | `--speed 2`, `--speed 1` |
| `openbsd80-install-sun4u.cast`, `openbsd80-boot-sun4u.cast` | `lab.py install openbsd80-sun4u --check --export <dir> --out <runs>/install-openbsd80-sun4u/1-install-openbsd80-sun4u`: `install`, `check` | `--speed 3`, `--speed 2` |
| `openbsd59-install-ss5.cast`, `openbsd59-boot-ss5.cast` | `install` (no stored disk): `install-openbsd59-ss5/1-install-openbsd59-ss5/install`, `.../check` | `--speed 2`, `--speed 1` |
| `redhat62-install-ss5.cast`, `redhat62-boot-ss5.cast` | `install` (no stored disk): `install-redhat62-ss5/1-install-redhat62-ss5/install`, `.../check` | `--speed 1`, `--speed 1` |
| `sol9-boot-sun4u.cast` | `install` (stored disk): `install-sol9-sun4u/1-boot-test-sol9-sun4u/check` | `--max-idle 1 --speed 1` |

The install-target rows come from runs in the PVE test container: `pve_matrix.py install` with the
stored disks for the boot-tests and with an empty `--disks` directory for the installs (so it installs
and exports there), `pve_matrix.py recordings` (cases only the gallery needs; Solaris 2.2 needs
pve-qemu-kvm 11.1.3-2+wsh22 or later), and the Debian install by hand, because it needs a route out
(`pve_matrix.py` passes no `--gateway`/`--dns`). Solaris 2.1, OpenBSD 8.0 and SunOS 4.1.3 on SS-10
are `lab.py install <target> --check` runs into the install matrix's case layout (the targets' own
test runs, the OpenBSD one the run that stored the disk; 2026-11-20 with pve-qemu-kvm 11.1.3-2+wsh30
for OpenBSD, 2026-11-21 with 11.1.3-3+wsh6 for Solaris 2.1 and with 11.1.3-2+wsh31 for SunOS, as OpenBSD 5.9, Red Hat 6.2 and the Solaris 9
boot). The SunOS 4.1.3_U1B SS-5 recordings keep their `sunos413-*-ss5` names; the original 4.1.3 on
SS-10 is `sunos413-*-ss10`. All of them can write into one `--runs` directory; `publish_media.py`
then picks them up in one go (its docstring lists the commands).

To replace one by hand (the release exists; to create it once:
`gh release create media --repo hwinther/wsh-pve --prerelease --latest=false --title "sparc lab media"
--notes "Recordings the docs embed, made by the sparc lab (e2e/sparc). Not a software release."`):

```sh
python3 lab.py cast <run dir> --max-idle 1 --speed 3 --output sol26-install-ss5.cast
gh release upload media sol26-install-ss5.cast --repo hwinther/wsh-pve --clobber
```

The next Pages deploy (any package build, a docs push, the run after E2E, or running "Update github
pages" by hand) publishes it. `publish_media.py <runs dir> <out dir>` does the table above for a
whole matrix run (only cases that passed), and the `sparc lab` workflow runs it when started by hand
with `publish_media` ticked: a separate job (`contents: write`, only for that) takes the run's
artifact after every case passed and uploads what it found with `--clobber`. It is off by default and
never runs on the schedule. A new recording needs a row in `publish_media.py` and a component on the
page.

Keep the clips short and documentary (the recordings show Sun/Oracle software running): no licence
keys, no media contents.

## Idle

Which guests stop spinning the host CPU when idle, and the results, are in `submodules/SPARC.md`
("Idle"). Solaris 2.5.1-9 idle through the `solaris-idle` machine option (any machine, one CPU);
`TRACE=sparc_solaris_idle_match` shows which loop layout matched (`2.5.1`, `2.6/7/8`, `9`). `sol26-enduser-pmc-installed.raw` is `sol26-enduser-installed.raw` with Solaris 2.6's `pmc`
driver installed from the 2.6 CD by the steps there. `modinfo | grep pmc` then lists `pmc (Power
Management prototype v1.1)` and `prtconf -D` shows `power-management, instance #0 (driver name: pmc)`.

On sun4u (`scenarios/sparc64-idle.py`) the guests idle through the `idle-halt` machine option (pve-qemu
`wsh/0042`-`0044`, `0070`-`0072`, `0110`-`0111` and `0114`-`0115`, on by default; `-M sun4u,idle-halt=off` turns it off); `TRACE=sparc64_idle_match`
shows which loop matched (`NetBSD`, `OpenBSD`, `Solaris`, `Solaris 7/8`, `Linux`, `Linux 3.2`, `FreeBSD`). The stored install disks
(`/mnt/os/disks/install-*-sun4u.raw`, `install-netbsd*-sparc64.raw`) take `PASSWORD=wshlab`; each guest
does something for a while after boot, which `WAIT` ends or waits out before the measurement:

| Guest | Variables |
| --- | --- |
| NetBSD 9.3, 11.1 | `GUEST=netbsd`, `WAIT=pkill makemandb; sleep 2` (the copied disk rebuilds its manual page index at every boot) |
| OpenBSD 8.0 | `GUEST=openbsd`, `WAIT=while pgrep -f reorder_kernel >/dev/null; do sleep 5; done` (the kernel relink after boot) |
| FreeBSD 12.4 | `GUEST=freebsd`, `PASSWORD=wshlab` (the target's disk after its first boot; the scenario runs its commands in `sh`, as root's csh ends a here-document only at the quoted word), no `WAIT` |
| Debian 7 (`install-debian7-sun4u.raw`) | `GUEST=debian`, `PASSWORD=wshlab` (nothing to wait for; the scenario's `LOAD` works too) |
| Solaris 10 | `GUEST=solaris10`, `MEM=1024`, `TIMEOUT=1800`, `` WAIT=svcadm disable -s sendmail webconsole; while svcs -H -o state \| grep '[*]' >/dev/null \|\| [ `svcs -H -o state milestone/multi-user` != online ]; do sleep 5; done ``, `SETTLE=180` (SMF goes on starting services for minutes after the login prompt) |
| Solaris 7, 8, 9 | `GUEST=solaris10`, `MEM=1024`, `TIMEOUT=1800`, `WAIT=/etc/init.d/sendmail stop`, `SETTLE=60` |
| Tribblix m34 | `GUEST=tribblix`, `MEM=2048`, `TIMEOUT=2400`, `WAIT=svcadm disable network/routing/route:default; svcadm disable -s fmd; zpool clear rpool; pkill rcm_daemon;` and the Solaris 10 loop, `SETTLE=180` (`route:default` times out again and again without a router; FMA marks the ZFS disk DEGRADED and `rcm_daemon` spins, so without `fmd` off the guest is never idle) |

`LOAD` needs a POSIX shell, so it is for the BSDs only; on Solaris the scenario's `awk` job reads
`/dev/null` (Solaris's old `awk` reads its input even with only a `BEGIN` rule, and swallowed the
commands typed after it).

`netbsd111-installed.raw` is NetBSD 11.1 from `NetBSD-11.1-sparc.iso` (`ISO=...`, `VGA=none`, by hand
through `serve`, ~10 min): microroot `1` (cdrom), Return twice, terminal type Return, `I`; sysinst: `a`
(English), `a` (install), `b` (yes), `a` (sd0), `b` (default partition sizes), `x`, `b`, `c` (Minimal
installation), `a` (CD-ROM); root password empty, entropy `x` (not now), `x` (finished configuring),
Return, `x` (exit), then `sync; halt -p`. Its GENERIC kernel attaches `apc0`; NetBSD 9.3's has no APC
driver and spins. `netbsd-install-sparc.py` now gives the same answers by script (the
`netbsd111-sparc` install target); the disk itself wasn't remade.

## The bench disk

Recognised period benchmarks for Solaris guests, built once in a guest and kept on a small disk that
any installed Solaris 2.5.1-2.6 (7-9 untried) mounts: Dhrystone 2.1, Whetstone (double precision),
the BYTE UNIX Benchmarks' Towers of Hanoi, nbench/BYTEmark 2.2.3 and a fixed lmbench 3.0-a9 subset
with lmbench's network tests (over `lo0`, and over `le0` to a peer outside the guest), plus the
earlier `nawk` loop, with a driver that prints one `BENCH <name> <value> <unit>` line per result. `bench/README` (also on the disk) lists versions, sources, flags, parameters and licences.
`bench-disk.py` runs it and the `benchdisk` matrix compares machines and firmware; the results are in `submodules/SPARC.md` ("Benchmarks"). Neither disk image, nor the downloaded
sources, nor anything from the Solaris CD is in the repository: only the scripts in `bench/`.

| File (lab host) | What |
| --- | --- |
| `/mnt/os/disks/bench-sol26.raw` | the bench disk: 32 MiB, Sun label, UFS on slice 0 (`bench/README` is its README). The one measured in `submodules/SPARC.md`: sha256 `4fc0babd3639e67ec9ab6f5176a7d645316849759ad1e5b1d6e48335933a2206`, without the network tests (every rebuild differs: `newfs` and file times) |
| `/mnt/os/disks/bench-sol26-net.raw` | the same with lmbench's network tests (`bench/net.sh`), measured in `submodules/SPARC.md` ("Network"): sha256 `a0f7eb6d0c04cccbd1078e02c7876e7fe79c568b235194a653e6a759c22bd93a` |
| `/mnt/os/disks/sol26-ss20-build.raw` | the build disk: `sol26-enduser-ss20-installed.raw` + the 2.6 development packages + gcc 2.95.3 (sha256 `6be744e08cc3c7e34d7ed634d4f717d7f17f1c8a521e32fc23dbada86131eaa2`; boot only copies of it) |
| `/mnt/os/disks/bench-downloads/` | the sources and the gcc package as downloaded and checked by `bench/handover.py` (untrusted third-party files: only for the hand-over CD) |

`DISK2` attaches a second disk on SCSI target `DISK2_ID` (4), read only unless `DISK2_RO=0`. Target 4,
not 0-2: OpenBIOS takes the first disk it probes for its `disk` alias, so with a disk on target 1 it
tries to boot that one (`Not a bootable ELF image`) instead of target 3; with target 4 OpenBIOS and the
Sun PROMs boot target 3 as before. The installs saw no disk on target 4, so `bench-disk.py` and
`build.sh` run `drvconfig; disks` (`/devices` and `/dev` entries for it) before using
`/dev/dsk/c0t4d0s0`; no reconfiguration boot is needed (tried on target 1 and 4, 2.6 and 2.5.1).

**Build disk** (once; ~15 min by hand through `serve`; SS-20, where deep-calling programs such as gcc
run several times faster than on SS-5, `submodules/SPARC.md` "Benchmarks"):

1. Copy `sol26-enduser-ss20-installed.raw` to `/mnt/os/disks/sol26-ss20-build.raw` and `serve` it
   with `MACHINE=SS-20 ISO=solaris_2.6_598_sparc.iso`; answer the first-boot questions, log in as root.
2. From the 2.6 CD (vold mounts it on `/cdrom/cdrom0/s0`), with an admin file of `action=nocheck`,
   `instance=overwrite` and the other checks off: `pkgadd -n -a /tmp/admin -d
   /cdrom/cdrom0/s0/Solaris_2.6/Product SUNWhea SUNWarc SUNWsprot SUNWbtool SUNWlibm`. The End User
   install has none of these; what each brings: headers (SUNWhea), `libc.a` and the other archive
   libraries plus `values-Xa.o` (SUNWarc), `as` and `make` (SUNWsprot), `ar`/`ranlib` for lmbench's
   library (SUNWbtool), `libm.a` (SUNWlibm). `ld` (SUNWtoo) is installed already. Solaris 2.6 ships no
   `crt1.o`; gcc brings its own.
3. Swap the CD for the hand-over CD (below; `eject cdrom`, `ctl hmp "change drive-scsi6 <iso> raw
   read-only"`, `/etc/init.d/volmgt stop`, `mount -F hsfs -o ro /dev/dsk/c0t6d0s0 /mnt`) and install
   gcc on the big slice: `/` is too small for pkgadd's spool and `/usr` too small for gcc, so
   `mkdir /export/home/local; ln -s /export/home/local /usr/local; TMPDIR=/export/home/tmp pkgadd -n
   -a /tmp/admin -d /mnt/gcc/gcc-2.95.3-sol26-sparc-local all` (Sunfreeware's SMCgcc, gcc 2.95.3,
   using Sun's `as`/`ld`). Remove `/export/home/tmp`, `sync; init 5`.

**Hand-over CD and bench disk** (each rebuild; ~3 min). `bench/handover.py` downloads the sources and
the gcc package (pinned URLs and sha256 in the script, kept in the download directory), gunzips what
the guest can't, and writes an ISO 9660/Rock Ridge CD with them, `build.sh`, `run.sh`, `lmbench.sh`,
`net.sh`, `nbench.cfg`, the disk's README and a `SOURCES` file. `bench/sunlabel.py` makes a blank disk
with a Sun label (slice 0 = all but the 2 alternate cylinders), and `bench-build.py` boots a copy of
the build disk with both, runs `build.sh` (compile with fixed flags, `newfs` slice 0, copy binaries,
sources and README, check that Dhrystone runs from the disk) and reports the compile times. From the
repository root, on the lab host:

```sh
docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .
W=/mnt/runs/bench-build; mkdir -p $W
D=/mnt/os/disks/bench-downloads   # handover.py checks the files there, fetches missing ones
docker run --rm -v $W:$W -v $D:$D --entrypoint python3 wsh-sparc-lab -I bench/handover.py $D $W/handover.iso
python3 e2e/sparc/bench/sunlabel.py $W/bench.raw 32
cp --sparse=always /mnt/os/disks/sol26-ss20-build.raw $W/disk.raw
docker run --rm -v $W:$W wsh-sparc-lab run scenarios/bench-build.py --out $W/run --var MACHINE=SS-20 \
  --var DISK=$W/disk.raw --var ISO=$W/handover.iso --var DISK2=$W/bench.raw
cp $W/bench.raw /mnt/os/disks/bench-sol26.raw; sha256sum /mnt/os/disks/bench-sol26.raw
```

**Network.** `run.sh` runs lmbench's `lat_tcp`, `lat_udp`, `lat_connect`, `bw_tcp` and `lat_rpc` over
`lo0` with the rest of lmbench, and, when `BENCH_PEER` is set, `lat_tcp`, `lat_udp` and `bw_tcp` over
`le0` against lmbench's servers on that peer (`nic_*`; `bench/README`, "Network"). `bench-disk.py`
provides the peer: it gives `le0` 10.0.2.15/24 with `ifconfig` (at run time only; nothing is written
to the disk), checks that 10.0.2.2 answers `ping`, starts lmbench's Linux servers in the lab container
(`/opt/lmbench-peer`: the same lmbench 3.0-a9, unmodified, fetched by `handover.py fetch` with its
pinned sha256 and built by `bench/peer-build.sh` in the image) and runs `run.sh` with
`BENCH_PEER=10.0.2.2`. The direction from the guest needs `bw_tcp`'s server in the guest: afterwards
`bench-disk.py` starts it there and runs the client in the container (`nic_bw_out`). `NET` picks the
path between QEMU and the container:

- `NET=user` (default, the `benchdisk` matrix): QEMU user networking (slirp). 10.0.2.2 is QEMU's own
  user-mode TCP/IP stack, which relays each connection over a socket of the container; the
  guest-to-container direction goes through a host forward (`hostfwd_add` on the monitor, removed
  again afterwards). What a VM with `-netdev user` gets.
- `NET=tap`: a tap interface in the container (`labtap0`, 10.0.2.2/24, the same addresses), so the
  container's kernel answers; QEMU's slirp is out of the path. The container needs
  `--cap-add NET_ADMIN --device /dev/net/tun`. What a VM on a bridge gets, minus the bridge.
- `NET=none`: no peer, the `nic_*` tests are a `BENCH-SKIP` line.

```sh
docker run --rm --cap-add NET_ADMIN --device /dev/net/tun -v /mnt/runs:/mnt/runs \
  -v /mnt/os/disks:/mnt/os/disks:ro wsh-sparc-lab run scenarios/bench-disk.py --out /mnt/runs/bt \
  --var DISK=<copy of an installed disk> --var DISK2=/mnt/os/disks/bench-sol26-net.raw --var NET=tap --var ONLY=nic
```

**Run it**: `bench-disk.py` with `DISK2=` the bench disk, or the matrix (the bench disk's directory
mounted read only, `--bench` defaults to `/mnt/os/disks/bench-sol26.raw`; a missing bench disk fails
every case):

```sh
docker run --rm -v /mnt/os/disks:/mnt/os/disks:ro -v /mnt/os/disks:/mnt/os/disks:ro \
  -v /mnt/runs:/mnt/runs --entrypoint python3 wsh-sparc-lab matrix.py benchdisk \
  --runs /mnt/runs/b1 --bench /mnt/os/disks/bench-sol26.raw
```

The summary adds a table with one row per benchmark and one column per case. Each case's directory
has `bench.txt` (run.sh's output with the units, `uname -a`, `psrinfo -v`) and `result.json`
(`metrics`: every value, plus `boot_s`, `run_s`, `run_cpu_pct` and the host's 1-minute load average at
the start and end, `load1_start`/`load1_end`).

## SunOS 4.1.4

`lab.py install sunos414-ss5` installs it through PVE (the install target; the user side is in
`docs/src/content/docs/guides/lab-install.md`). It follows the hand install below, with three
scenarios on the serial console:

- **The medium** is the BIN cut to 2048-byte sectors, `sunos414-cd.iso` (329297920 bytes, sha256
  `7b9b092a63bf5dde9f09eea25614c6da58e5c065758a8c24b96be1574bcaa0c8`), made by the user with
  `lab.py media sunos414-ss5 --convert sunos_4.1.4_install.iso` (`install.convert_medium`: the
  source's size and sha256 first, the 2048 data bytes at offset 16 of each 2352-byte sector, the
  result's sha256, else nothing is left behind). `targets.MEDIA` has it with `"from": {"name":
  "sunos_4.1.4_install.iso", "convert": "bin2352"}`; `lab.py media` prints the command for a
  missing one, and `pve_matrix.py` converts it into the test node's `local` storage when `--iso` has
  only the BIN. The `scsi6` CD-ROM is qemu-server's `scsi-cd` with `physical_block_size=512`, as in
  the lab: nothing else to change.
- **The disk** is SUN2.9G with slice g cut to 1000 cylinders (`targets.SUN29G_SUNOS4`, written by
  `sunlabel.write_disk`), so Quick install's "preserve the data partitions" newfs's a (/) and g
  (/usr) as the label has them.
- **The install phase** (`sunos-install-serial.py`) runs with 64 MB and `args: -prom-env
  auto-boot?=false`, both for that phase only (`install: {"memory": 64, "prom_env": ...}`;
  `Job.finish()` sets the profile's 256 MB and deletes `args`). At `0 >` it boots the CD's slice d,
  answers `1` (mini-root) and `2` (no format), takes `1` (reboot), boots
  `.../sd@3,0:b -sw` at `0 >`, runs `suninstall` with `TERM=vt100`: `1` (Quick), `y` (preserve),
  Programmer from the menu (Space moves, `x` selects), `y` to start, `y` to reboot, and powers off
  at `0 >` (`power-off`). suninstall's own part took under 2 minutes, the whole phase 126-146 s.
- **The first boot** (`sunos-firstboot.py`) boots the disk by itself and answers sys-config by its
  screen codes (`SysConfA1` host name ... `SysConfI5` user password; `_sunos4.sysconfig`): `2`
  (manual setup), the host name, Greenwich Mean Time / GMT, accept the time, networked with the
  static address, no NIS, the root password twice, and the user (`--user`: full name `wsh-lab
  user`, uid 1001, group staff, csh, home `/home/<host>/<user>`) or none. Then it logs in, starts
  `/bin/sh` (root's csh would expand `!`), writes the marker and `/etc/netmasks` (the netmask
  under the classful network number: without it `le0` comes up with `netmask ff000000`) and, with
  `--gateway`, `/etc/defaultrouter` (4.1.4's `rc.boot` and `rc.local` read both), and `halt`s
  (OpenBIOS powers off).
- **The check** (`sunos-boot-disk.py`) logs in and runs the target's `check: {"commands": ...}`
  (`uname -a`, the marker, `df`, `dkinfo sd0`, `ifconfig -a`, `netstat -rn`).

Tested in the PVE test container on the lab host with the published packages (pve-qemu-kvm
11.1.3-2+wsh15, qemu-server 9.2.15+wsh6, pve-manager 9.2.28+wsh4), one guest at a time, 2026-11-17:

| Run | Result | Time |
| --- | --- | --- |
| `media sunos414-ss5 --convert sunos_4.1.4_install.iso` into `local`, then `media sunos414-ss5` | written, sha256 as above; `ok`; without the medium `media` printed `missing` and the `--convert` command | |
| `install sunos414-ss5 --check` | passed; `SunOS sunos414 4.1.4 2 sun4m`; `df`: `/dev/sd0a` 91744 KB (3838 used), `/dev/sd0g` 976987 (65530 used); `le0 10.0.2.15 netmask ffffff00`; the finished VM: `memory: 256`, no `args`, `scsi6: none,media=cdrom`, `boot: order=scsi3` | 5.8 min (install 126 s, first boot 151 s, check 55 s) |
| `install sunos414-ss5 --check --user lab --ip 10.0.2.20 --gateway 10.0.2.2 --hostname sun4 --template` | passed; `default 10.0.2.2 UG` in `netstat -rn`, `lab:1001:10:wsh-lab user:/home/sun4/lab:/bin/csh`, a template | 6.5 min (133 s, 182 s, 53 s) |
| `pve_matrix.py install --only install-sunos414-ss5`, `--iso` with the BIN only (the converted CD removed first) | 1/1 passed; the CD converted into `local` by `lab.py media --convert` | 6.1 min (139 s, 151 s, 54 s) |
| `install sunos414-ss5 --check --user lab --root-password ... --user-password ...` (not the defaults) | passed; then a boot by hand: `lab` logs in with its password (`uid=1001(lab) gid=10(staff)`, home `/home/sunos414/lab`); neither password is in the evidence directory, and `/etc/passwd` is shown without its hash field | 6.6 min (146 s, 172 s, 57 s) |
| `--ip dhcp`, `--dns 10.0.2.3`, `--data-disk 2`, `--disk-size 9G` | refused before a VM is made | 0 s |
| the CD booted with 256 MB (a VM made by hand like the target's) | `qemu: fatal: Trap 0x29 (Data Access Error) while interrupts disabled, Error state` in the journal right after the kernel loaded, VM off | 9 s |
| unit tests (`test_targets.py`, `test_dos.py`, `test_vgatext.py`) | 73 passed | |
| `pve_matrix.py pve` (regression, same code) | 5/5 passed | `sol26-install-ss5` 825 s (the host was shared with other runs), the others 67-240 s |
| `matrix.py smoke` (the lab image with the branch's `e2e/sparc`, pve-qemu-kvm 11.1.3-2+wsh13 in that image) | 3/3 passed | 159 s, 111 s, 65 s |

Not tried: Typical_user, Full_install and Mini_install through the scenario, a second disk, `--vlan`,
a router that answers (the routes were checked, not traffic through them), the lab's own QEMU
instead of PVE for the three scenarios.

The lazy redraw that kept the hand install off the scripted driver is the console holding back the
last character of a burst until the next key (a menu's cursor move, a field's echo): the scenarios
match the text before it, sys-config's screen codes and, on the menu, the entry list, and never wait
for that character. DNS (`--dns`, `--domain`) is refused (`net_refuse`: 4.1.4's libc resolves
through `/etc/hosts` or NIS), and so is `--ip dhcp` (no DHCP client).

`sunos414-installed.raw` was installed by hand through `serve`. The machine is the lab's SS-5 with
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

## sparc64

`scenarios/_sparc64.py` is the sparc64 machine: `sun4u` with `openbios-sparc64`, one CPU, 512 MB,
serial console, and the disk, CD-ROM and NIC on a choice of buses (`DISK_BUS`, `CD_BUS`: `ide`,
`lsi`, `virtio-scsi`, `virtio-blk`; `NIC`: any PCI model, on `pciB`). The default is the layout that
works: disk on the built-in IDE's primary master, CD-ROM on its secondary master, `sunhme`.
`LAYOUT=pve` is what qemu-server builds for a sparc64 VM from the create wizard today (LSI 53C895A,
`bootindex`, `-vga std`, virtio-balloon); `BOOTINDEX=1` adds only the `bootindex` values. Results are in
`submodules/SPARC.md` ("sparc64").

| Scenario | What it does | Time |
| -------- | ------------ | ---- |
| `sparc64-boot-cd.py` | boots a CD (`GUEST=netbsd`, `openbsd`, `debian`, `solaris`, or `EXPECT`) to the installer's first prompt; `CONSOLE=fb` waits for it on the VGA screen (OCR) and `TYPE` types on the keyboard | ~1 min |
| `netbsd-install-sparc64.py` | NetBSD/sparc64 install with sysinst on the serial console (`SETS=b`: without X11), root without a password, ends powered off | ~8 min |
| `netbsd-install-sparc.py` | the same for NetBSD/sparc on sun4m (SS-5, `MACHINE=SS-20`): the CD's microroot, then the same sysinst answers (`SETS=c`: Minimal); the microroot powers off after Exit | ~3.5 min |
| `netbsd-firstboot.py`, `netbsd-boot-disk.py` | either architecture (`ARCH`; from the VM with `--pve`): the install targets' first boot (root password, marker, host name, network, user) and check boot ("NetBSD install targets") | ~2 min each |
| `openbsd-install-sparc64.py` | OpenBSD/sparc64 install from `install80.iso` on the serial console, the questions answered by what they ask (`_openbsd.py`), ntpd left on, halted ("The OpenBSD 8.0 install target") | ~9-12 min |
| `openbsd-install-sparc.py` | OpenBSD/sparc 5.9 on sun4m (SS-5, `MACHINE=SS-20`): `cd59.iso` on target 6, the sets CD on 5 (`SETS_ISO`, or written from the release's directory `SETS_DIR`), the same rules, `-nographic` ("OpenBSD 5.9 on sun4m") | ~3-4 min |
| `openbsd-firstboot.py`, `openbsd-boot-disk.py` | either architecture (`ARCH=sparc` for sun4m; from the VM with `--pve`): the install targets' first boot (marker, host name, network, user, ntpd check) and check boot | sparc64 ~4-6 min, sparc 1-5 min |
| `freebsd-install-sparc64.py` | FreeBSD 12.4 from disc1 on the serial console: bsdinstall's console type, its Shell, `bsdinstall script` (the auto layout on `ada0`, kernel and base from the CD), `halt -p` ("The FreeBSD 12.4 install target") | ~10 min |
| `freebsd-firstboot.py`, `freebsd-boot-disk.py` | the install target's first boot (root password, marker, host name, network with `sysrc`, user) and check boot (`REBOOT=1` reboots once first) | ~2-3 min each |
| `sparc64-boot-disk.py` | boots an installed disk (`GUEST=...`), logs in, runs `COMMANDS` (each output checked against `CHECK`), powers off and checks that QEMU ended; `BOOTS` times | ~1.5 min a boot |
| `sparc64-reboot.py` | boots an installed disk (`GUEST=netbsd`, `openbsd`, `solaris10`, `solaris` for 7/8/9), logs in and reboots from the guest (`REBOOT`, default `reboot`; `init 6` works too) `REBOOTS` times in the same QEMU process: each time the firmware's banner must come back and the disk boot to the login prompt again; a returned reboot call, `0 >` or no banner fails it (with `info registers` in the step log). Needs openbios-sparc64 with patch 0030 (`submodules/SPARC.md`, "The firmware reboot on sun4u"). The `sparc64` matrix runs it on the NetBSD 11.1 disk (`nb111-reboot-sparc64`, `nb111-reboot-bootstr-sparc64` with `REBOOT=reboot -- netbsd`) | NetBSD ~1.5 min a reboot, Solaris 3-8 min |
| `sparc64-idle.py` | the sparc64 `idle.py`: QEMU's host CPU use at the shell, the guest clock, ten `sleep 1`, the time of an `awk` loop (`JOB`), and `LOAD` seconds of CPU and file load; `WAIT` first ends or waits out what the guest does after boot; NetBSD, OpenBSD, FreeBSD, Solaris 9/10 and Tribblix (see "Idle") | ~4 min (Solaris ~15, Tribblix ~35) |
| `debian-install-sparc.py`, `debian-firstboot.py`, `debian-boot-disk.py` with `ARCH=sparc64` | Debian 7.11 on sun4u from CD 1 with a preseed answer CD on the secondary IDE slave, its first boot and check ("Debian GNU/Linux 7 on sun4u") | install ~85 min, first boot ~3.5 min, check ~3 min |
| `debian13-install-sparc64.py` | Debian 13 (debian-ports sid) from the sparc64 netinst with a preseed file on an answer CD (IDE secondary slave, `sr1`): the kernel options typed on the netinst's GRUB `linux` line, preseed/early_command loads the file; stops the VM when the install reboots, fails at the first question box ("Debian 13 on sun4u") | ~2.5 h |
| `debian13-firstboot.py`, `debian13-boot-disk.py` | boot the installed Debian 13 disk through GRUB to `login:` on ttyS0; the first sets root's password (chpasswd), the marker and a user, the second records `COMMANDS` (and checks `CHECK`); both `poweroff` | ~4 min |

The disks are `netbsd111-sparc64-installed.raw` (NetBSD 11.1, `netbsd-install-sparc64.py` with the
defaults, by hand through `serve` with the same answers) and `openbsd80-sparc64-installed.raw`
(OpenBSD 8.0 from `install80.iso`: `I`, `vt100`, hostname, `hme0` autoconf, no IPv6, root password
`lab`, no sshd, no user, `UTC`, `wd0`, auto layout, sets from `cd0`, `-x*`, `yes` to the missing
`SHA256.sig`, `h`; its installed kernel boots with openbios 0023, see `submodules/SPARC.md`). They are kept in
`/mnt/os/disks` on the lab host, so the `sparc64` matrix runs with `--disks /mnt/os/disks`
(workflow input `disks_dir`). The CDs are in `other-os/` under `--iso`.

## Drive a guest by hand

`serve` starts QEMU and takes commands from `ctl`; every `Machine` method is a command. This is how
new scenarios are written: step through the installer by hand, then copy the steps.

```sh
docker run -d --name lab -v /mnt/os:/mnt/os -v /mnt/runs:/mnt/runs wsh-sparc-lab serve --out /mnt/runs/x \
  --scenario scenarios/_sparc32.py --var ISO=/mnt/os/iso/solaris_2.6_598_sparc.iso --var VGA=none
ctl() { docker exec lab python3 lab.py ctl --out /mnt/runs/x "$@"; }
ctl expect "Select a Language" 900
ctl screen_text                  # the serial console as text
ctl send '"0\r"'                 # JSON strings for control characters
ctl key f2                       # Esc-2; also enter, esc, ctrl-n, ctrl-p, ...
ctl snap "after the language"    # record a step (terminal + framebuffer screenshot)
ctl screendump now               # the framebuffer as /mnt/runs/x/now.png
ctl hmp "info registers"         # any monitor command
```

## MCP server

`mcp_server.py` (`wsh-lab-mcp`) is a [Model Context Protocol](https://modelcontextprotocol.io/)
server that lets an AI assistant (Claude Code, or any MCP client) look at and type on a running VM
the way the scenarios do: the screen as an image or as text, keys and text on the guest's keyboard
or the serial console, the serial output, and waiting for a pattern. It is a thin layer over
`lab.py` (the same `Machine` methods, `PveQmp`, key tables and OCR) for two kinds of VM:

- **PVE VMs** by VMID, on the node that runs them (or in the e2e PVE container): the sockets in
  `/var/run/qemu-server/`, as attach mode uses them, without starting, stopping or recording anything.
- **Lab VMs**: a QEMU that `lab.py serve --out DIR` runs; the server sends a fixed set of `Machine`
  calls to `DIR/ctl.sock`.

It speaks MCP over stdin/stdout only (no listening port) and is built on the official Python SDK
(`mcp` 2.3.0, `MCPServer`). It is an optional extra: nothing in the patched Debian packages or the lab's
matrices uses it, and its dependencies live in their own venv.

### Safety model

The server runs where the VM's sockets are, which on a PVE node means as root. It is meant to give
an assistant one VM's console, not the node:

- **VMs are opt-in.** Only the VMs named when it starts can be touched: `--vm VMID` (repeatable),
  `--tag TAG` (every VM *on this node* whose PVE tags include TAG, looked up with `pvesh get
  /cluster/resources` at most every 10 s, so removing the tag revokes access) and `--lab NAME=DIR`.
  Without any of them it refuses to start. Every tool takes a `vm` and refuses anything else with
  `VM '105' isn't one this server may touch (allowed: 9001; VMs tagged mcp)`; `list_vms` shows only
  the allowed VMs. `--vm` is the strict form; `--tag` delegates the decision to whoever may edit a
  VM's tags in PVE (`VM.Config.Options`).
- **A fixed set of operations.** The QMP commands it sends are `screendump` (into the server's own
  `0700` temporary directory), `send-key`, `query-status` and, only with `--allow-reset`,
  `system_reset`. There is no QMP or monitor passthrough unless `--allow-hmp` adds the `hmp` tool,
  which is annotated destructive: the human monitor can do anything QEMU can, including writing host
  files and running commands (`migrate exec:...`), so `--allow-hmp` on a node is root for the
  assistant. `stop_vm` (`qm stop`) needs `--allow-stop`; nothing starts a VM. Lab VMs get the same
  operations through `ctl.sock` (the lab's `serve` would take any `Machine` method; the server sends
  only its list).
- **No files.** It never opens disk images, offers no file transfer, and reads nothing under
  `/etc/pve` but `qm config <vmid>` of an allowed VM (and whether `/etc/pve/qemu-server/<vmid>.conf`
  exists). With `--tag`, `pvesh get /cluster/resources` also lists the other VMs' names and tags to
  the server (not to the assistant).
- **Guest output is data.** Serial text and OCR text are returned as tool results with control
  characters removed, never interpolated into anything that runs; the server's instructions tell the
  assistant not to follow instructions found in them. Regular expressions come from the assistant
  and only run in Python's `re`.
- **Annotations.** `list_vms`, `vm_status`, `screenshot`, `screen_text`, `serial_read` and `wait_for`
  are read-only; `send_keys` and `type_text` are destructive (typing into a root shell can do
  anything in the guest); `serial_release` is neither; `reset_vm`, `stop_vm` and `hmp` are
  destructive. Clients treat annotations as hints: what protects the node is the allow-list and
  the missing tools, not the annotations.

Known holes:

- The keyboard is full control of the guest, and through it of whatever the guest can reach on the
  network. Give the assistant a VM you would give a person at its console.
- The server and its dependencies (`mcp`, `pydantic`, ...) run as root on the node; a bug in them is
  root on the node. Give the SSH key that starts it a forced command (below), so it can't open a
  shell.
- It bypasses PVE's permission system and task log: PVE sees `qm config` and QMP connections from
  root, not a PVE user. Use `--vm` lists per assistant/user instead of relying on PVE roles.
- `ctl.sock` of a `lab.py serve` run takes any `Machine` method from anyone who can open it; the
  server limits itself, the socket doesn't (as before: it is in the run directory).

### Serial console and QMP: sharing with PVE

- **Serial:** QEMU serves one client per serial socket; a second one is accepted but gets nothing.
  The server connects to `<vmid>.serialN` on the first call that needs it (`serial_read`, `wait_for`
  on `serial`/`terminal`, `screen_text` of the terminal, typing to `serial`), refuses with a clear
  message when another client already has it (`qm terminal`, the web console's xterm.js), and then
  holds it, so no output is lost between calls: guest output arrives while the assistant is thinking.
  `serial_release` gives it back, and it is released by itself after `--serial-idle` seconds (900)
  without a serial call, and when the server exits. The server exits as soon as its client's end of
  stdin closes, even in the middle of a long `wait_for`, so a lost client doesn't keep the console
  (tested with a client that went away during a wait; a dropped SSH connection closes the same pipe
  through sshd, not tested). Before that check, a client killed during a 600 s wait left the server
  holding the console until the wait ended. While the server holds it, `qm terminal`
  gets nothing. Output from before the server connected is not available (as in attach mode).
- **QMP:** PVE starts QEMU with one QMP socket for tools (`<vmid>.qmp`; qmeventd has its own
  connection, where QEMU is the client). QEMU serves one client at a time there, so the server uses
  `lab.PveQmp`: one connection per command, waiting its turn while `qm`/pvestatd have the socket, as
  PVE's own tools do. `qm status --verbose` kept its QMP fields while the server ran (below).
- **cg3 refresh:** for a sparc32 VM with a framebuffer the server takes a screendump every
  `--refresh` seconds (1) once a tool has touched the VM, as the lab's `REFRESH` does: without
  display updates the cg3 delivers no vertical-retrace interrupt and Solaris never loads its colour
  map ("Things the lab found out"). `--refresh 0` turns it off.

### Install and run

**On a PVE node, from the package:** `apt install wsh-lab` (the wsh-pve repository) puts the
server in `/usr/share/wsh-lab/` and `wsh-lab-mcp` in `/usr/bin`. Its Python SDK (`mcp`, with
pydantic, starlette, ...) isn't packaged in Debian 13, and the package doesn't carry a copy of it:
`wsh-lab-mcp --setup` (as root, once; needs `python3-venv` and access to PyPI) makes a venv in
`/var/lib/wsh-lab/mcp-venv` from `/usr/share/wsh-lab/mcp-requirements.txt` (the pinned file below,
`pip --require-hashes --only-binary=:all:`), and `wsh-lab-mcp` then runs the server from it. It
says so on stderr (never on stdout, the MCP stream) when the venv is missing, or was made for
another wsh-lab version or Python, and stops. `apt purge wsh-lab` (or `wsh-lab-mcp --remove-venv`)
removes the venv.

```sh
apt install wsh-lab python3-venv
wsh-lab-mcp --setup
wsh-lab-mcp --vm 9001 --check   # what it would allow
```

In the client commands below, use `wsh-lab-mcp --vm 9001` in place of
`/opt/wsh-lab-mcp/bin/python /opt/wsh-lab-mcp/lab/mcp_server.py --vm 9001`.

**On a PVE node without the package**, and without new system packages: a venv made by [uv](https://docs.astral.sh/uv/) (one
static binary; `python3 -m venv` would need `python3-venv`), the pinned and hash-checked
dependencies, and the lab's three files. As root:

```sh
uv venv /opt/wsh-lab-mcp --python /usr/bin/python3
uv pip install --python /opt/wsh-lab-mcp/bin/python --require-hashes -r e2e/sparc/mcp-requirements.txt
install -d /opt/wsh-lab-mcp/lab && install -m 644 e2e/sparc/lab.py e2e/sparc/recording.py e2e/sparc/mcp_server.py /opt/wsh-lab-mcp/lab/
/opt/wsh-lab-mcp/bin/python /opt/wsh-lab-mcp/lab/mcp_server.py --vm 9001 --check   # what it would allow
```

`pyte` and Pillow come from the requirements; `screen_text`/`wait_for` on a framebuffer need
`tesseract-ocr` on the node (without it they say so; screenshots and the serial tools work).
`uv run e2e/sparc/mcp_server.py ...` also works (the script carries its dependencies inline), but
without hash checking. Removing it is `rm -r /opt/wsh-lab-mcp`.

**In a container:** `mcp.Dockerfile` adds the venv (`/opt/wsh-lab-mcp`) and `wsh-lab-mcp` to either
lab image. The server has to run in the container that has the sockets, so for PVE VMs that is the
PVE node with the lab (`pve.Dockerfile`), not a separate container with `/var/run/qemu-server`
mounted (that would hand it every VM's sockets):

```sh
docker build -f e2e/sparc/mcp.Dockerfile -t wsh-lab-mcp e2e/sparc                                  # on wsh-sparc-lab
docker build -f e2e/sparc/mcp.Dockerfile --build-arg BASE=wsh-pve-lab -t wsh-pve-lab-mcp e2e/sparc  # on wsh-pve-lab
docker exec -i pve-lab wsh-lab-mcp --tag mcp                       # a PVE VM in the test node
docker exec -i lab wsh-lab-mcp --lab sol=/mnt/runs/x         # next to `lab.py serve --out /mnt/runs/x`
```

**From a client** (not tested here: no interactive client was run). Claude Code, with the server on
a node over SSH:

```sh
claude mcp add wsh-lab -- ssh -T root@pve-node /opt/wsh-lab-mcp/bin/python /opt/wsh-lab-mcp/lab/mcp_server.py --vm 9001
```

or in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "wsh-lab": {
      "command": "ssh",
      "args": ["-T", "root@pve-node", "/opt/wsh-lab-mcp/bin/python", "/opt/wsh-lab-mcp/lab/mcp_server.py", "--vm", "9001"]
    }
  }
}
```

Better, a key that can do nothing else: in the node's `/root/.ssh/authorized_keys`,
`restrict,command="/opt/wsh-lab-mcp/bin/python /opt/wsh-lab-mcp/lab/mcp_server.py --vm 9001" ssh-ed25519 AAAA...`;
the client then runs `ssh -T -i <that key> root@pve-node` and the allow-list is fixed on the node. A
long `wait_for` can outlast a client's tool timeout (Claude Code: `MCP_TOOL_TIMEOUT`); keep
`timeout_s` below it and call again.

### Tools

| Tool | What it does | Example |
| ---- | ------------ | ------- |
| `list_vms` | the allowed VMs: running, arch, machine, display (`framebuffer`/`serial`), `vga`, serial port and who holds it | `{}` |
| `vm_status` | QMP run state (`running`, `paused`, ...), host CPU use of the QEMU process over 0.5 s (% of one core), pid, serial state | `{"vm": "9001"}` |
| `screenshot` | the display as a PNG (QMP `screendump`), scaled to `max_width` (1024; 0 = native), with `screen_id`; `if_changed_since` returns no image when the screen hasn't changed | `{"vm": "9001", "max_width": 800, "if_changed_since": "3fa1c0..."}` |
| `screen_text` | the screen as text: `terminal` (the serial console's 80x24 VT100 screen, exact) or `display` (OCR of the framebuffer); `screen_id`/`if_changed_since` as above | `{"vm": "9001", "source": "display"}` |
| `serial_read` | serial output from a cursor (default: where the last read or match ended), at most `max_chars` (4000, up to 20000); returns the next cursor, `more`, `lost` | `{"vm": "200", "cursor": 1834}` |
| `wait_for` | a regex on the serial output (from a cursor), the terminal screen, or the display's OCR text (every `interval_s`), up to `timeout_s` (600 max); `last_lines` looks only at the bottom of a screen, where the prompt the guest waits at is (a console keeps the old ones); a timeout returns `matched: false` and what was seen | `{"vm": "9001", "source": "display", "pattern": "console login:", "last_lines": 6, "timeout_s": 600}` |
| `send_keys` | keys and chords in order, on the display keyboard (QMP qcodes) or the serial console: `ret`, `esc`, `f2`, `ctrl-c`, `ctrl-alt-delete`, `Stop-A`, `L1-A` (= Stop-A), `shift-tab` | `{"vm": "9001", "keys": ["Stop-A"], "to": "display"}` |
| `type_text` | text, one character at a time (`delay_ms`: 80 on the display, 50 on serial; old guests drop faster input); returns the serial cursor from before, for `wait_for` | `{"vm": "200", "text": "uname -a\n", "to": "serial"}` |
| `serial_release` | give the serial socket back to `qm terminal`/the web console | `{"vm": "200"}` |
| `reset_vm` | QMP `system_reset` (`--allow-reset`) | `{"vm": "9001"}` |
| `stop_vm` | `qm stop` / QEMU quits (`--allow-stop`) | `{"vm": "9001"}` |
| `hmp` | any human monitor command (`--allow-hmp`) | `{"vm": "9001", "command": "info registers"}` |

The usual loop is `type_text` → `wait_for` with the cursor it returned (so a prompt from before the
command doesn't match) → `serial_read` or `screen_text` for the rest. `to` defaults to the display
when the VM has one. Stop-A has no serial form: a Sun PROM on ttya takes a BREAK, which a socket
chardev can't send.

**How good the screen text is:** the serial terminal is exact (it is the emulator the scenarios
match against). A framebuffer is OCR (tesseract `--psm 6`, small screens scaled 2x first): good on
text consoles in a fixed font (OpenBIOS and the Solaris console on cg3/tcx, VGA text mode), with
the usual confusions (OpenBIOS's `0 >` read as `o>`, `System` as `Sustem`, quotes); poor on GUIs (CDE, the
OpenWindows installer), where the screenshot is the better tool. Match OCR with loose patterns.

**Left out:** the mouse (the lab has no pointer support, and the Sun mouse is relative: positions
would be guesses; the keyboard drives the PROM, the consoles and the text installer); starting VMs
and changing media (that is PVE's job, with its permissions); snapshots; file transfer; an HTTP
transport (a listening port on a node needs authentication; SSH already provides it).

### A PVE VM: Solaris 2.6 on a cg3

Run in the e2e PVE node with the lab and the MCP layer (`mcp.Dockerfile` on `wsh-pve-lab`), from the
SDK's client over stdio (`wsh-lab-mcp --tag mcp --allow-reset`, as `docker exec -i` would start it).
The VM: `arch: sparc`, SS-5, OpenBIOS, 256 MB, `vga: cg3` (console on the framebuffer, 1024x768),
`serial0: socket`, a copy of `sol26-enduser-installed.raw` imported as `scsi3`, tag `mcp`, and
`args: -prom-env auto-boot?=false` so OpenBIOS waits at its prompt; started with `qm start`. A
second, untagged VM was there too.

- `list_vms` showed only the tagged VM (`sparc`, `SS-5`, `framebuffer`, `cg3`, `serial0` free);
  `screenshot` of the untagged one was refused.
- At the prompt, `wait_for` on the display found `Welcome to Open` and `screen_text` read the banner
  (`Welcome to OpenBIOS v1.1 built on ...`, `Type 'help' for detailed information`); the `0 >`
  prompt itself came out as `o> m`, so a pattern for it didn't match. `screenshot`: 1024x768 PNG;
  again with `if_changed_since`: `unchanged`, no image.
- `type_text "boot disk\n"` to the display (send-key on the Sun keyboard), then `wait_for`
  (`console login:|Root password:|Press Return`, `last_lines: 6`, OCR every 10 s): the first boot
  of the copy stopped at the root password screen (Return twice); the next boot reached `sol26
  console login:` 62 s after `boot disk`. `screen_text` read the boot messages with OCR slips
  (`Sustem` for `System`, `50126` for `sol26`); the screenshot is exact. On the very first boot
  the X server (dtlogin) came up after the prompt, and OCR then read `Welcome to sol26`, `Please
  enter your user name`.
- Sharing: while the server ran (QMP per command, a refresh screendump every second), `qm status
  --verbose` still had `qmpstatus: running` and `running-qemu: 11.1.3`, and `qm sendkey 9001 shift`
  returned 0. With a test client connected to `9001.serial0` first, `serial_read` refused (`in use
  by another client`); after it closed, the server took the socket, and `serial_release` gave it back.
- `vm_status`: 99.9% of a core at the OpenBIOS prompt (it spins), 6-66% at the Solaris prompt.
- `send_keys ["Stop-A"]` at the Solaris console prompt ended QEMU within 3 s (qmeventd: `read:
  Connection reset by peer`, then its cleanup; no guest power-off event), twice: at the console
  prompt and at the dtlogin screen. Not investigated;
  PVE doesn't keep QEMU's stderr, so run it under `lab.py` (`qemu.stderr`) to see why.

### Test

`tests/test_mcp_server.py` boots an Alpine x86_64 CD (no Sun software) under `lab.py serve`, starts the
server over stdio with the SDK's client and checks: the tool list (no `reset_vm`/`stop_vm`/`hmp`
unless enabled), `list_vms`, `vm_status`, the login prompt on the serial console, a login and a
command's output found by cursor, a `wait_for` timeout, `serial_read` paging, the terminal screen
and `if_changed_since`, typing on the VGA console (its output written to `/dev/ttyS0` comes back on
the serial port), `send_keys`, screenshots (a PNG of the size reported, scaled to `max_width`), the
OCR text, and refusals for VMs that aren't allowed. Without `MCP_TEST_ISO` it downloads the pinned
`alpine-virt-3.24.4-x86_64.iso` (70 MB, sha256 checked). It also checks that the server exits
at once when its client goes away during a long `wait_for`. 60-75 s under TCG with two cores:

```sh
docker run --rm --entrypoint /opt/wsh-lab-mcp/bin/python wsh-lab-mcp -m unittest -v tests/test_mcp_server.py
```

The `MCP server` job in `.github/workflows/sparc-lab-mcp.yml` runs it on pull requests that touch the
lab.

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
- **Solaris 2.6 with more than one CPU hung** (SS-20, OpenBIOS; fixed by pve-qemu patch 0019):
  writing 256 MB, sometimes while booting. One CPU waited in `xc_sync_cache` for a cross-call the
  other never took: QEMU didn't look at pending interrupts after a write to `%psr` in a delay slot,
  where Solaris's `splx` lowers the interrupt level. The `smp` matrix loads 2 and 4 CPUs; the
  `machines` matrix boots the installed disks with one CPU.
- **Solaris 2.6 ran user code 4-10x slower on SS-5 than on SS-20** (fixed by pve-qemu patch
  0017): its microSPARC window-trap handlers toggle the MMU no-fault bit, and QEMU flushed its whole
  TLB on each toggle. With 0017 the `benchdisk` numbers of SS-5 and SS-20 match, except
  fork/exec at 1.2-1.3x (`submodules/SPARC.md`, "Why SS-5 was slower", "Benchmarks"); with an older
  package the gap is still there.
- **With a working `disk` alias the Solaris 2.6 installer pre-selects the boot disk**
  (`[X] c0t3d0 ... boot disk`); `disks()` only marks it when it isn't selected yet.
- **Solaris 2.4 and 2.5.1 need the CD as a disk** (`CDROM_AS=hd`): from a `scsi-cd` their kernel
  panics with `vfs_mountroot: cannot mount root`. Through PVE that is the CD-ROM drive's
  `cd_as_disk=1` (qemu-server, sparc32 only; the install targets' `as_disk`). A CD that answers as
  a disk is also listed as an install target (`c0t6d0`).
- **Solaris 2.4 doesn't boot under OpenBIOS** ("Unhandled Exception 0x00000009", any CD device);
  2.4 and 2.5.1 boot with `ss5.bin`. 2.5.1 installed and booted fine on 11.1.3+wsh1 (the ESP fix).
- **Stop-A powered the VM off under OpenBIOS** (fixed by `openbios/patches/0008`): its `op_enter`
  printed `abort, power off` on ttya and wrote the power-off bit, so QEMU ended with status 0. Now
  the guest stops at `0 >` and `go` resumes it. The firmware's small print over dtlogin is beyond
  OCR, so `stop-a.py` also checks where the CPU is (`info registers`: OpenBIOS runs at 0xffd00000
  and up). A break on ttya (`BREAK=1`) hung Solaris on a serial console until pve-qemu `wsh/0141`:
  QEMU's ESCC never ended the break and kept its interrupt raised (`submodules/SPARC.md`,
  "Stop-A"). The `stopa` matrix's break cases need a pve-qemu-kvm with that patch.
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
