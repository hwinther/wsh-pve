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
`pve-qemu-kvm_...` suffix).

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
wrote to ttya), `qemu.cmd`, `qemu.stderr`, `NNN-ttya.{txt,png}` / `NNN-fb.png` per step, `result.json`,
the recordings (`serial.cast`, `serial.fast.cast` and, with a framebuffer, `fb.webm` and `fb.vtt`; see
"Recordings") and the guest disk.

| Scenario | What it does | Time (11.1, one core) |
| -------- | ------------ | --------------------- |
| `solaris-install-serial.py` | Solaris 2.x initial install (End User) on ttya, ends powered off | 2.6: ~9 min; 2.5.1 (`CDROM_AS=hd BIOS=ss5.bin`): ~60 min, mostly its Maintenance Update |
| `solaris-boot-disk.py` | boots an installed disk (OpenBIOS or `BIOS=ss5.bin`), answers first-boot questions, logs in, records `uname`/`df`/`ifconfig`, shuts down | ~2-3 min |
| `solaris-boot-cd.py` | boots an install CD to the installer's first question (language or terminal type) and stops; `IDLE` measures QEMU's host CPU use there | ~1 min |
| `cg3-display.py` | the cg3 at the size `RES` gives, console on the framebuffer: the PROM banner and, with `DISK`, Solaris to `console login:` (first-boot questions answered by OCR), each screenshot checked for that size and for not being blank | banner: seconds; disk: ~4 min |
| `fb-display.py` | cg3 or TCX (`VGA`, `RES=1024x768x24` for TCX's 24-bit mode), console on the framebuffer: the banner, Solaris to its login prompt and, with `X=1`, dtlogin, a root login into CDE, the depth (`DEPTH`), the keyboard (`INPUT`), idle CPU (`IDLE`), a drawing benchmark (`BENCH`, `ACCEL` counts TCX's blitter writes) and a soak (`SOAK`); `EXPECT=console` checks why X doesn't start instead. Its checks run on a ttya shell, so the disk needs `PREPARE=1` (or `solaris-tcx-packages.py TTYA_LOGIN=1` first) | X: ~4-5 min; `BENCH=3`: ~8 min |
| `solaris-tcx-packages.py` | adds the TCX packages (SUNWtcx.m, SUNWtcxow, SUNWtcxu) to an installed Solaris from its CD and touches `/reconfigure`; `TTYA_LOGIN=1` also gives root a login on ttya while the console is on the framebuffer | ~3-4 min |
| `idle.py` | boots an installed disk, logs in, then measures QEMU's host CPU use over `SECONDS` (`CPU_BELOW`/`CPU_ABOVE` set the limits), checks that the guest clock kept time, times a CPU-bound command (`BUSY`), the echo of `true` and ten `sleep 1`; the numbers go to `result.json` (`metrics`) | ~3-4 min |
| `niagara-boot.py` | `-M niagara` (sun4v) with an OpenSPARC T1 firmware set the user supplies (`FW`, never in the image): OpenBoot's `ok`, with `DISK` the T1 archive's `disk.s10hw2` to a root shell and `init 5`, with `ISO` a Solaris 10 DVD to the text installer (`WALK` walks on through its screens); skipped (exit 0, `status` "skipped: ...") when the firmware isn't there. See `submodules/SPARC.md`, "sparc64: niagara (sun4v)" | `ok`: 1 s; disk: ~2 min; installer: ~4-5 min |
| `bench.py` | boots an installed Solaris disk, checks the CPUs `psrinfo` lists (`CPUS`, default `SMP`), then times boot to login, a `nawk` loop, `PARALLEL` copies of it at once (default `SMP`), a 64 MB write + `sync` and a raw read, with QEMU's host CPU use idle and during the parallel run; `SOAK` adds a load phase. `init 5` at the end | SS-5: ~5 min, SS-20: ~3 min |
| `bench-disk.py` | boots an installed Solaris disk with the bench disk (`DISK2`, "The bench disk") on target 4, mounts it, runs its `run.sh` (Dhrystone, Whetstone, Hanoi, nbench, lmbench subset with its network tests over `lo0`, the `nawk` loop, and lmbench over `le0` to the lab container: `NET=user` by default, `tap`, or `none`) and puts every `BENCH` value into `result.json`, with the host's load average; `init 5` at the end | ~10-12 min (7-8 of them `run.sh`) |
| `smp-soak.py` | boots an installed Solaris disk with `SMP` CPUs and the bench disk (`DISK2`), checks that `psrinfo` lists them on-line, times one and `SMP` copies of Dhrystone and the `nawk` loop (speed-up), then loads every CPU for `SOAK` seconds (Dhrystone, Hanoi, `nawk`, a `tar` of the bench disk through `compress` with its `cksum` checked, a write, a fork loop; `SMP` + 1 shells) while `mpstat 60` records the CPUs; fails on a hang, a CPU off-line, a checksum mismatch or a CPU below `BUSY` % busy | `SOAK` + ~5 min |
| `bench-build.py` | boots the build disk with the hand-over CD and a blank labelled `DISK2`, runs `build.sh`, which compiles the benchmarks and makes `DISK2` the bench disk; compile times go to `result.json` | ~3 min (SS-20) |

Machine options are variables (`--var KEY=VALUE`), listed at the top of `scenarios/_sparc32.py`:
`BIOS` (openbios-sparc32, ss5.bin, …), `MACHINE`, `MEM`, `SMP` (`-smp` only when > 1), `CPU` (`-cpu`,
e.g. `TI-SuperSparc-50`, which the Sun SS-20 PROM needs; none by default), `TCG_THREAD` (`-accel
tcg,thread=single|multi`), `VGA` (cg3, tcx, none), `RES` (`-g`, e.g. `1152x900`), `CONSOLE`,
`CDROM_AS` (`hd` for Solaris 2.4/2.5, which only boot the installer from a CD that answers as a disk),
`TEMPLATE`/`DISK`, `DISK2` (a second disk on target `DISK2_ID`, 4; read only unless `DISK2_RO=0`),
`REFRESH`, `TRACE` (QEMU trace events into `trace.log`, e.g. `cg3_write` or `esp_*`).
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
| `display` | `cg3-display.py`: `BIOS=ss5.bin` banner at 1024x768, and the 2.6 disk with OpenBIOS at 1024x768, 1152x900, 1280x1024, 1600x1200 and 1920x1080; `fb-display.py`: the TCX banner at depth 8 and 24 and the cg3 banner with every profile's machine and firmware, and the 2.6 disk without the TCX packages on TCX (no driver, no X) | ~35 min |
| `display-x` | `fb-display.py X=1 INPUT=1 IDLE=60`: the 2.6 disks (TCX packages added by `PREPARE`) into the CDE desktop on TCX 8, TCX 24 and cg3 with SS-5 (OpenBIOS, `ss5.bin`: not TCX 24), SS-10 and SS-20 (OpenBIOS) | ~100 min |
| `idle` | `idle.py`, OpenBIOS unless stated: Solaris 2.6 on SS-5 and SS-20 with `solaris-idle` (below 10% of a core, `sparc_solaris_idle_match` traced) and with `solaris-idle=off` (above 80%), 2.6 with the `pmc` driver on SS-5 with and without `solaris-idle` (below 10%), 2.5.1 on SS-5 with `ss5.bin` (below 10%, traced), SunOS 4.1.4 with `sunos-idle` (below 10%, and `sparc_sunos_idle_match` traced) and with `sunos-idle=off` (above 80%), NetBSD 11.1 (`apc0` attached, below 10%) | ~35 min |
| `bench` | `bench.py` with Solaris 2.6 on SS-5 (OpenBIOS) and SS-20 (OpenBIOS and the Sun PROM), one CPU each; numbers only, on an otherwise idle host | ~13 min |
| `sparc64` | `sun4u` (see "sparc64"): the NetBSD 11.1, NetBSD 9.3, OpenBSD 8.0 and Debian 12 CDs to their installers on the serial console, NetBSD 11.1 on the VGA console with the keyboard, the NetBSD 11.1 install, its disk booted twice with DHCP and an HTTP fetch over `sunhme`, with `virtio-net-pci` and `virtio-blk`, and idle; needs `--disks /mnt/sparc/disks` | ~25 min |
| `benchdisk` | `bench-disk.py` (the bench disk, `--bench`) with Solaris 2.6 on SS-5 (OpenBIOS, `ss5.bin`), SS-10 (OpenBIOS) and SS-20 (OpenBIOS, the Sun PROM), and 2.5.1 on SS-5 (`ss5.bin`); one CPU, 256 MB, QEMU user networking for the `le0` tests; numbers only, on an otherwise idle host | ~65 min |
| `smp` | `smp-soak.py` (the bench disk, `--bench`, `SOAK=600`) with Solaris 2.6 on SS-20 (OpenBIOS) with 2 and 4 CPUs and on SS-10 with 2 CPUs; needs a package with pve-qemu patch 0019 (before it 2.6 hung with more than one CPU) | ~50 min |

`display` needs a `pve-qemu-kvm` with the cg3 patches (`submodules/SPARC.md`); with an older one
every size but 1024x768 fails at QEMU's `Unsupported resolution` (1152x900: OpenBIOS faults).
`idle` needs one with the idle patches (0011-0016): with an older one the `pmc` disk panics at boot,
`sunos-idle=off`/`solaris-idle=off` are unknown machine options and Solaris without `pmc` spins.

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
`prom_boot()` boots the CD at the `0 >` prompt), `CDROM_AS` (`hd` for a target 6 without
`media=cdrom`) and `REFRESH`. `solaris-install-serial.py` and `solaris-boot-disk.py` ran unchanged
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

(`qm disk import 100 <template.raw> local --format raw` and then `qm set 100 --scsi3 <volume>` does
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
| `sol26-install-ss5` | SS-5, OpenBIOS, `vga: serial0`, the SUN2.9G template on target 3, the 2.6 CD on target 6 | `solaris-install-serial.py`, then `solaris-boot-disk.py` |
| `alpine-aarch64` | `arch: aarch64`, virt, OVMF (AAVMF), `vga: serial0`, the Alpine 3.19 CD on virtio-scsi | `alpine-boot-cd.py`: login prompt, root, `uname -m` |
| `netbsd-sparc64` | `arch: sparc64` as the create wizard makes it (sun4u, OpenBIOS, a blank disk on `ide0`, the NetBSD 11.1 CD on `ide2`, `sunhme`, 512 MB, the API's default boot order), `vga: serial0` | `netbsd-boot-cd.py` with `BOOT=` (OpenBIOS must boot the CD by itself): sysinst, its shell, `uname -m` |
| `alpine-x86_64` | `kvm: 0`, `vga: std`, `serial0: socket`, the Alpine 3.19 CD on `ide2` | `alpine-boot-cd.py` on the VGA console (OCR, send-key), `uname -m` also through the serial port |
| `sol26-ss20-smp2` | SS-20, OpenBIOS, `cores: 2`, 512 MB, `vga: serial0`, the installed 2.6 SS-20 disk imported to target 3, the bench disk (`--bench`) imported read only to target 4 | `smp-soak.py` with `SMP=2 SOAK=0`: `psrinfo` lists 2 CPUs on-line, then Dhrystone and the `nawk` loop alone and as 2 copies at once |

One run took 12 min for `sol26-install-ss5` and about a minute for each of the others.

It runs in the e2e PVE node with the lab added, privileged like the e2e container, the media
mounted read only:

```sh
docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
docker build -f e2e/sparc/pve.Dockerfile -t wsh-pve-lab e2e/sparc
docker run -d --name pve-lab --hostname pve --privileged --tmpfs /run --tmpfs /run/lock \
  -v /mnt/sparc/iso:/mnt/sparc/iso:ro -v /srv/sparc/disks:/srv/sparc/disks:ro \
  -v /mnt/sparc/disks:/mnt/sparc/disks:ro -v /mnt/sparc/runs:/mnt/sparc/runs wsh-pve-lab
docker exec pve-lab python3 pve_matrix.py pve --runs /mnt/sparc/runs/p1
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
docker run --rm -v /mnt/sparc/runs:/mnt/sparc/runs wsh-sparc-lab cast /mnt/sparc/runs/m1/sol26-disk-openbios-ss5 --check
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

`netbsd111-installed.raw` is NetBSD 11.1 from `NetBSD-11.1-sparc.iso` (`ISO=...`, `VGA=none`, by hand
through `serve`, ~10 min): microroot `1` (cdrom), Return twice, terminal type Return, `I`; sysinst: `a`
(English), `a` (install), `b` (yes), `a` (sd0), `b` (default partition sizes), `x`, `b`, `c` (Minimal
installation), `a` (CD-ROM); root password empty, entropy `x` (not now), `x` (finished configuring),
Return, `x` (exit), then `sync; halt -p`. Its GENERIC kernel attaches `apc0`; NetBSD 9.3's has no APC
driver and spins.

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
| `/mnt/sparc/disks/bench-sol26.raw` | the bench disk: 32 MiB, Sun label, UFS on slice 0 (`bench/README` is its README). The one measured in `submodules/SPARC.md`: sha256 `4fc0babd3639e67ec9ab6f5176a7d645316849759ad1e5b1d6e48335933a2206`, without the network tests (every rebuild differs: `newfs` and file times) |
| `/mnt/sparc/disks/bench-sol26-net.raw` | the same with lmbench's network tests (`bench/net.sh`), measured in `submodules/SPARC.md` ("Network"): sha256 `a0f7eb6d0c04cccbd1078e02c7876e7fe79c568b235194a653e6a759c22bd93a` |
| `/mnt/sparc/disks/sol26-ss20-build.raw` | the build disk: `sol26-enduser-ss20-installed.raw` + the 2.6 development packages + gcc 2.95.3 (sha256 `6be744e08cc3c7e34d7ed634d4f717d7f17f1c8a521e32fc23dbada86131eaa2`; boot only copies of it) |
| `/mnt/sparc/disks/bench-downloads/` | the sources and the gcc package as downloaded and checked by `bench/handover.py` (untrusted third-party files: only for the hand-over CD) |

`DISK2` attaches a second disk on SCSI target `DISK2_ID` (4), read only unless `DISK2_RO=0`. Target 4,
not 0-2: OpenBIOS takes the first disk it probes for its `disk` alias, so with a disk on target 1 it
tries to boot that one (`Not a bootable ELF image`) instead of target 3; with target 4 OpenBIOS and the
Sun PROMs boot target 3 as before. The installs saw no disk on target 4, so `bench-disk.py` and
`build.sh` run `drvconfig; disks` (`/devices` and `/dev` entries for it) before using
`/dev/dsk/c0t4d0s0`; no reconfiguration boot is needed (tried on target 1 and 4, 2.6 and 2.5.1).

**Build disk** (once; ~15 min by hand through `serve`; SS-20, where deep-calling programs such as gcc
run several times faster than on SS-5, `submodules/SPARC.md` "Benchmarks"):

1. Copy `sol26-enduser-ss20-installed.raw` to `/mnt/sparc/disks/sol26-ss20-build.raw` and `serve` it
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
W=/mnt/sparc/runs/bench-build; mkdir -p $W
D=/mnt/sparc/disks/bench-downloads   # handover.py checks the files there, fetches missing ones
docker run --rm -v $W:$W -v $D:$D --entrypoint python3 wsh-sparc-lab -I bench/handover.py $D $W/handover.iso
python3 e2e/sparc/bench/sunlabel.py $W/bench.raw 32
cp --sparse=always /mnt/sparc/disks/sol26-ss20-build.raw $W/disk.raw
docker run --rm -v $W:$W wsh-sparc-lab run scenarios/bench-build.py --out $W/run --var MACHINE=SS-20 \
  --var DISK=$W/disk.raw --var ISO=$W/handover.iso --var DISK2=$W/bench.raw
cp $W/bench.raw /mnt/sparc/disks/bench-sol26.raw; sha256sum /mnt/sparc/disks/bench-sol26.raw
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
docker run --rm --cap-add NET_ADMIN --device /dev/net/tun -v /mnt/sparc/runs:/mnt/sparc/runs \
  -v /mnt/sparc/disks:/mnt/sparc/disks:ro wsh-sparc-lab run scenarios/bench-disk.py --out /mnt/sparc/runs/bt \
  --var DISK=<copy of an installed disk> --var DISK2=/mnt/sparc/disks/bench-sol26-net.raw --var NET=tap --var ONLY=nic
```

**Run it**: `bench-disk.py` with `DISK2=` the bench disk, or the matrix (the bench disk's directory
mounted read only, `--bench` defaults to `/mnt/sparc/disks/bench-sol26.raw`; a missing bench disk fails
every case):

```sh
docker run --rm -v /srv/sparc/disks:/srv/sparc/disks:ro -v /mnt/sparc/disks:/mnt/sparc/disks:ro \
  -v /mnt/sparc/runs:/mnt/sparc/runs --entrypoint python3 wsh-sparc-lab matrix.py benchdisk \
  --runs /mnt/sparc/runs/b1 --bench /mnt/sparc/disks/bench-sol26.raw
```

The summary adds a table with one row per benchmark and one column per case. Each case's directory
has `bench.txt` (run.sh's output with the units, `uname -a`, `psrinfo -v`) and `result.json`
(`metrics`: every value, plus `boot_s`, `run_s`, `run_cpu_pct` and the host's 1-minute load average at
the start and end, `load1_start`/`load1_end`).

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
| `sparc64-boot-disk.py` | boots an installed disk (`GUEST=...`), logs in, runs `COMMANDS` (each output checked against `CHECK`), powers off and checks that QEMU ended; `BOOTS` times | ~1.5 min a boot |
| `sparc64-idle.py` | the sparc64 `idle.py`: QEMU's host CPU use at the shell, the guest clock, the time of an `awk` loop (`JOB`), and `LOAD` seconds of CPU and file load | ~4 min |

The disks are `netbsd111-sparc64-installed.raw` (NetBSD 11.1, `netbsd-install-sparc64.py` with the
defaults, by hand through `serve` with the same answers) and `openbsd80-sparc64-installed.raw`
(OpenBSD 8.0 from `install80.iso`: `I`, `vt100`, hostname, `hme0` autoconf, no IPv6, root password
`lab`, no sshd, no user, `UTC`, `wd0`, auto layout, sets from `cd0`, `-x*`, `yes` to the missing
`SHA256.sig`, `h`; its installed kernel doesn't boot, see `submodules/SPARC.md`). They are kept in
`/mnt/sparc/disks` on the lab host, so the `sparc64` matrix runs with `--disks /mnt/sparc/disks`
(workflow input `disks_dir`). The CDs are in `other-os/` under `--iso`.

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
