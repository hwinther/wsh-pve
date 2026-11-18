# Roadmap

Where the work stands and what comes next, in order. Written 2026-11-16, refreshed 2026-11-17. The details behind each
item are in `submodules/SPARC.md` (what was measured and why), `e2e/README.md` and
`e2e/sparc/README.md` (how it is tested), and the pull requests named here.

The aim: guests of other architectures and retro x86 guests that run stably under Proxmox VE, in a
small set of tested configurations, with tests that catch regressions. More platforms in the UI
come after that, not before.

## Done

| Area | State | PRs |
| --- | --- | --- |
| Floppy drives (storage type, qemu-server, UI) | published | #183, #231 |
| sparc lab in CI: guests booted and installed on a self-hosted runner, weekly and on demand | running | #230 |
| cg3 at any size (from LEMU), FCode ROM built in `openbios/` | published | #232, #236 |
| Idle: SunOS 4.1.4 (from LEMU), Solaris 2.6 via `pmc` (16-byte APC), Solaris 2.5.1–9 on any sun4m machine | published | #233, #241 |
| SS-10/SS-20, SMP and RAM measured; benchmark scenario | merged | #235 |
| sparc32 profiles in qemu-server and the UI; backup and restore; arch set on create only | published | #239, #240 |
| Optional extras of pve-qemu-kvm: check, issue on a missing one, tests | running | #242 |
| 3dfx binary back (missing from 11.1.1-1+wsh1 to 11.1.3-2+wsh6), port to QEMU 11.1, refresh script | published | #245, #247 |
| Lab drives VMs that PVE started (`--pve`); sparc64 and aarch64 boot through PVE; `pve` matrix | running | #248, #249 |
| OVMF tests; aarch64 OVMF VMs start again | published | #248, #249 |
| Recordings: terminal casts and framebuffer videos per run; gallery in the docs, media in the `media` release | published | #250 |
| sparc64 measured: guests, disk/NIC/console layout, Solaris under OpenBIOS, Sun OBP, idle and speed | merged | #255 |
| Operations on a running sparc VM (CD change, NIC changes, pending changes, clone, move disk) | published | #252, #253 |
| TCX against cg3: why TCX failed before, cg3 stays the default | merged | #254 |
| sparc64 profile in qemu-server and the UI (IDE disks, boot letter, refusals); NetBSD boots through PVE unattended | published | #256, #257 |
| Bench disk (Dhrystone, Whetstone, nbench, lmbench, Hanoi) with network measures; `benchdisk` matrix | running | #258, #261, #263 |
| SS-5 as fast as SS-20 for Solaris (narrower TLB flush on the no-fault bit) | published | #262 |
| Solaris 10 on `niagara` measured: reaches the installer, no disk or network; parked | merged | #259 |
| Dial-up modem on a guest's serial port: cause of the PPP hang, recipe, container test | merged | #264 |
| Retro net, stages 0 and 1: one gateway image (DHCP, DNS, redirects, egress filter, VintageHive for the 1999 web and instant messaging), hermetic test in CI, guide | merged | #273 |
| Retro net archive cache: persistent store of Wayback answers, offline replay, warm-up from VintageHive's links, export/import; the test replays a synthetic dataset | merged | #274 |
| Solaris with more than one CPU on SS-10/SS-20 (interrupt after `wr %psr` in a delay slot), pve-qemu-kvm 11.1.3-2+wsh10 | published | #266 |
| Up to 4 CPUs in the SS-10/SS-20 OpenBIOS profiles (qemu-server, UI); boot with 2 CPUs through PVE in the `pve` matrix | published | #267, #270 |
| Idle with more than one CPU: Solaris 2.5.1–9 on SS-10/SS-20 halt idle vCPUs in the multiprocessor idle loop (`solaris-smp-idle`, pve-qemu `wsh/0023`-`0025`), ~4-5% of a host core idle with 2 or 4 CPUs instead of 100% per vCPU | in review | #295 |
| Stop-A on a running sparc32 guest stops at the OpenBIOS prompt and `go` resumes (it powered the VM off) | published | #276 |
| Workflow hardening (job-level permissions, explicit secrets), upstream notes for ESP, OpenBIOS and APC | merged | #237, #238 |
| Install targets: a tested 9G disk (`--disk-size 9G`, the owner's Qemu9G template byte for byte) on SS-5 and SS-20, and `--data-disk` (a labelled second disk on `/data`) | merged | #283 |
| Install targets: network choices (`--vlan`, `--ip dhcp`, `--netmask`, `--gateway`, `--dns`, `--domain`) for Solaris 2.6 on SS-5 and SS-20, tested against DHCP and DNS on a test bridge | merged | #283 |
| `wsh-lab`: the lab as an optional package in the apt repository (`apt install wsh-lab`, `wsh-lab` and `wsh-lab-mcp` commands), built and tested per PR, released per version and added to the repository by the Pages deploy | published | #283 |
| Install targets: `lab.py install <target>` on a node makes an installed VM with known login details from tested media (Solaris 2.6 on SS-5 and SS-20); the `pve` matrix runs it | merged | #275 |
| MCP server around the lab: an assistant sees and drives an allowed VM (screenshot, screen text, keys, serial, wait for a pattern; reset, stop and the monitor behind flags), shipped in `wsh-lab` | merged | #268, #283 |
| qemu-3dfx pin moves only through a promotion PR with a 3dfx-only build check | merged | #272 |
| Solaris 10 on sun4u: patched `openbios-sparc64` in the package (OBP node names, IDE tree `ide@3/disk@0,0` and `cdrom@2,0`), cmd646 interrupt latch (`wsh/0021`) with a qtest; the DVD boots to the installer, ttya takes input, the disk attaches | published | #260, #277, #280, #287 |
| DOS: `msdos622` and `freedos14` install targets from floppies, an exact VGA text reader over QMP, the first megabyte under SeaBIOS measured, a DOS guide; FreeDOS installs in CI | merged | #290 |
| Install targets: SunOS 4.1.4 on SS-5 (`sunos414-ss5`): miniroot, `suninstall` Quick install and sys-config on the serial console through PVE, the CD made from its raw BIN by `lab.py media --convert`, 64 MB for the install phase only | in review | |
| A CD that answers as a disk: `cd_as_disk=1` on a sparc32 SCSI CD-ROM (qemu-server: `scsi-hd`, read only, still a CD-ROM to PVE; refused elsewhere); install targets `sol24-ss5` (Solaris 2.4 HW 3/95, ~10 min) and `sol251-ss5` (2.5.1 11/97, ~45 min, most of it its Maintenance Update) on SS-5 with `ss5.bin` through PVE | in review | |
| sparc32 `ld`/`st %fsr` with any rd (LEMU `0cdd14c1` by Antoni Sawicki, pve-qemu `wsh/0026`, qtest `wsh/0027`): old static SunOS 4 programs whose `_sigtramp` saves the FSR with rd 4 no longer die with SIGILL; a QEMU regression since 8.2, upstream note written | in review | |
| Install targets: Red Hat Linux 6.2 on SS-5 and SS-20 (`redhat62-ss5`, `redhat62-ss20`, OpenBIOS): kickstart from an answer CD the tool makes on the node (the `unattended` method, `answer_media.py`), SILO's screens answered on the serial console, `/boot` first on the disk for SILO | in review | |
| Sound on the SS-5: the CS4231 plays through its APC DMA (LEMU `2938ff88`, `42d32575` by Antoni Sawicki, pve-qemu `wsh/0028`-`0029`), at SBus level 5 as the real machine (`wsh/0030`, openbios 0018), no start failure without an audiodev (`wsh/0031`), no lost tail (`wsh/0032`), qtest (`wsh/0033`); qemu-server `audio0: device=cs4231` (drivers `none`, `alsa`, `pa`, `pipewire`; SPICE, SS-10/SS-20 and sparc64 refused), the UI offers only that on sparc. SunOS 4.1.4, Solaris 2.5.1 and 2.6 play in the lab under OpenBIOS and `ss5.bin`. Limits: no DBRI on SS-10/SS-20 (not emulated), nothing in the web console (no SPICE on sparc32), no capture | in review | |
| Install targets: Solaris 7 (`sol7-ss5`, `sol7-ss20`) also on the 9G disk (`--disk-size 9G`; 3G stays the default), measured through PVE | in review | |
| sun4u with more than 3 GB: OpenBIOS patches 0013-0015 (heap above 4 GB, `claim` against the firmware's virtual range, the whole address in `phys.lo`); NetBSD 11.1 and Solaris 10 run with up to 8 GB in the lab, an upstream note; the sparc64 profile's cap in qemu-server and the UI goes from 3072 to 8192 MB | merged | #309 |
| Install targets, Solaris post-install: the data disk on `/usr/local` (`--data-mount`), `--post-install sun26gnu` (34 GNU packages from the owner's local CD with `pkgadd -n` and an admin file, the CD in `scsi5` for that boot only) and `--local-env` (`PATH`, `MANPATH`, bash for `--user`; root keeps `/sbin/sh`), checked by `--check`; Solaris 2.6 and 7 on SS-5 and SS-20 (the 2.6 packages run on 7) | in review | |

## In progress

Work that exists but is not merged. If this list is stale, check the open pull requests.

1. **Patches after the upstream sync** (#289, draft). The nightly sync moved pve-storage,
   qemu-server and pve-manager to upstream code that splits the volume types; the three patch files
   are refreshed there. It waits for Proxmox to publish libpve-storage-perl 9.1.17, qemu-server
   9.2.17 and pve-container 6.1.22, then the build image is rebuilt and #289 merged. Until then main
   cannot build those three packages; the published ones are unaffected. #291 (`ne2k_isa` on the
   ISA bus) is stacked on it.
2. **Solaris 10 on sun4u (OpenBIOS).** pve-qemu-kvm 11.1.3-2+wsh13 ships the patched
   `openbios-sparc64` (patches 0003-0011: the virtual `available` list, the I-cache properties, the
   Forth state at client start, OBP's node names for the console, OBP's IDE tree) and the cmd646
   interrupt latch (`wsh/0021`). On that package Solaris 10 1/13 installs from its DVD to the IDE
   disk with the text installer on ttya (2 of 2 installs, ~80 min each,
   `scenarios/solaris10-install-sparc64.py`), and the installed disk boots to `console login:`, gets
   a DHCP lease on `hme0` and powers off (`solaris10` matrix 2/2, needs the Sun DVD and the
   installed disk on the lab host). Through PVE, `lab.py install sol10-sun4u --check` installs it on
   the sparc64 profile with a static address, the root password, the marker and an optional user
   (3 of 3 complete runs passed, one with `--user` and the network options, ~110 min each; in `pve_matrix.py install`). NetBSD, OpenBSD `bsd.rd` and the
   Debian installer boot as before. Still to do:
   - reboot: the installer's reboot and `reboot`/`init 6` return from the firmware; 0012
     (`.wip`) resets at the `ok` prompt but hangs when Solaris calls it;
   - every sun4u guest gets the system MAC 52:54:00:12:34:56 (QEMU only takes the onboard `-nic`'s
     MAC into the IDPROM);
   - `sol10-sun4u` with `--ip dhcp` (not tested through the tool); the intermittent `bad unknown
     trap at TL 1` panic seen once before the package (none in 6 installs on it); a different one,
     `BAD TRAP: type=4e` in the firmware while the DVD boots, once in 6 DVD boots through PVE
     (`install` retries it);
   - Solaris 7/8/9 `pp is NULL or free`; 2.5.1/2.6 boot-block exceptions.
   Details: `submodules/SPARC.md`, "Solaris on sun4u".
3. **Tribblix (illumos) on sun4u** (`feat/lab-tribblix-sun4u`). Tribblix m34, the newest SPARC
   release, needed two more OpenBIOS fixes: 0016 runs the client interface with interrupts off
   (illumos calls it with interrupts on; an interrupt while the firmware saved or restored the
   caller's register windows corrupted them on 4 of 7 live CD boots; also the cause of Solaris 10's
   one `BAD TRAP: type=4e`), and 0017 puts `xa+`/`xa1+` back into the 64-bit FCode table (every token
   from 0x24a on ran the wrong word, so the illumos ZFS boot block crashed). With both, the live CD
   boots to its login prompt, installs to the IDE disk with its own installer, and the installed disk
   boots, gets its address and powers off; `lab.py install tribblix-m34-sun4u` drives it through PVE
   (left out of `pve_matrix.py install` until a package has 0016 and 0017). Still open:
   - the guest's clock stops for good in about one of three long runs (5 of 14, before and
     after 0016), always under heavy interrupt traffic; a race in QEMU on `%softint`, caught in a trace
     (`upstream/qemu-sparc64-softint-race.md`), would need a QEMU patch;
   - with a ZFS root FMA marks the IDE disk DEGRADED during the install (EIO on first attempts that
     ZFS retries; no data errors); a UFS install (`ROOT_FS=ufs`) avoids that but hasn't been booted;
   - the live CD's package catalogue is older than its packages, so an offline install skips some
     (curl, tcsh, GNU coreutils, ...); a Tribblix issue;
   - very slow under TCG: about 45 minutes to the live CD's login, and the first boot of the
     installed system imports the SMF manifests again.
   Details: `submodules/SPARC.md`, "Tribblix on sun4u".

## Next, in this order

1. **Idle on sparc64.** NetBSD on sun4u keeps a host core at 100% (nothing on QEMU's sun4u lets
   the guest stop the CPU; `SPARC.md`, "sparc64"); Solaris on sun4u not measured.
2. **Solaris on sun4u**: see "In progress". Solaris 10 installs through `lab.py install`; next: a
   reboot that works from Solaris (0012 hangs), then a per-VM system MAC.
3. **Solaris 10/11 on `niagara`: measured, parked as a demonstration.** Reproduced on the
   published 11.1.3 without a QEMU patch: Solaris 10 1/13 reaches its text installer ("Identify
   This System") with Sun's firmware and a fixed 1 GB machine description, or with firmware built
   from source (`sun4v-qemu-kit`, 30 s in a container; BSD+ and GPL-2, so a CI build looks
   permitted; shipping Sun's prebuilt binaries is not advisable). After system identification the
   installer exits to a shell: Solaris sees neither the DVD nor any disk as a device. No network,
   one CPU, no idle, no power-off; the TTE page-size patch is needed only above 1 GB and isn't
   upstream. Disk and network exist only in the unix0.cc author's unpublished QEMU stack (PCIe
   for sun4v). Revisit when that is published or upstream; `scenarios/niagara-boot.py` checks it
   with user-supplied firmware.
3. **x86 retro.** Starts from the owner's notes and known problems (DOS and the first megabyte of
   memory among them). Then, like sparc: measure, profiles, tests.
   - **Started with DOS.** `lab.py install msdos622` installs MS-DOS 6.22 from its three floppies
     into a PVE VM (~4 min under TCG), driven on the VGA text screen through an exact reader of the
     text buffer (`vgatext.py`), with the disk swaps done by `install.MediaSwapper`; `freedos14`
     does FreeDOS 1.4 the same way, and CI installs FreeDOS from its floppies on a GitHub-hosted
     runner. The first megabyte is measured (`dos_mem.py`, the [DOS guide](docs/src/content/docs/guides/dos.md)):
     SeaBIOS 1.17 leaves 110K of read-only gap after the VGA, NIC and vapic ROMs, EMM386 makes
     98-102K of it one UMB, no NIC and no vapic ROM give 118K, a dummy option ROM never helps, and
     an `I=` range into SeaBIOS's data at E9000 hangs DOS.
   - Next for DOS: `ne2k_isa` on the ISA bus is #291 (an ISA NIC needs no option ROM; for most
     guests `rtl8139` stays the better choice); maybe a per-VM "legacy BIOS memory layout" (NIC ROM and
     vapic ROM off without `args:`); a DOS idle driver in the image so a DOS VM stops burning a host
     core; Windows 3.1 on top of `msdos622` (its SETUP has a graphical part, so OCR or the
     screendump for those screens); other DOS versions (5.0, 6.0, PC DOS 7) as targets.
   - Audio: which devices work in which guests, and where the sound goes on a headless node
     (SPICE, PulseAudio/PipeWire over the network). Testable with QEMU's `wav` audio backend.
   - Display: std VGA, Cirrus, VMware, QXL against noVNC and SPICE, for DOS, Windows 3.x–XP and
     older Linux.
   - Streaming: QEMU on a virtual desktop in a container with Sunshine or Wolf, for 2D/3D video
     and audio in one connection (Moonlight). Prefer `-display dbus` over SDL/GTK so the VM does not
     die with the desktop; keep VNC beside it. 3dfx needs SDL and may stay the exception. The
     existing `vga: …,server=` path drops VNC, uses `-vga` instead of a device, and sets no
     `XAUTHORITY`. Prototype on the test node's GPU first.
   - Retro net: one isolated network with a service container as its gateway, reached by NIC or
     by modem on the serial port, serving the web of 1999 (Wayback Machine, ProtoWeb) and period
     services (instant messaging first; later a Battle.net-compatible server and a period IRC
     network). Stages, candidates and what was decided are in `RETRONET.md`. The dial-up part
     exists (`docs/src/content/docs/guides/dialup.md`, `e2e/dialup`), and so does the gateway for
     NIC guests (stages 0 and 1: `retronet/`, `docs/src/content/docs/guides/retronet.md`), tested in
     containers only. Next: run it on a node (as a container from the OCI image, and under Docker
     with macvlan) with a real retro guest, then stage 2, dial-up into the same network. No GUI for
     now.

## Later

- **More architectures.** In order of fit: HP-UX on PA-RISC (`qemu-system-hppa`, open firmware,
  upstream), PowerPC (AIX 5.1 on `40p`, AIX 7 on `pseries`, Mac OS), Quadra 800 with A/UX. AIX 3.2.5
  needs LEMU's MCA machine, which is a large out-of-tree model. IRIX and DG/UX are not feasible in
  QEMU today.
- **Scheduled reinstalls.** One install per supported profile, weekly or monthly, replacing the
  stored disk when it passes, so every disk the lab boots can be rebuilt. The machinery exists: the
  install targets (`e2e/sparc/targets.py`, `lab.py install`) and `pve_matrix.py install`, which
  installs every automated target with `--check` (the `install` choice of the `sparc lab` workflow).
  Still to do: run it on a schedule, export the passing disks to `/srv/sparc/disks`, and automate
  more targets (Solaris 2.4-10, SunOS 4.1.4, NetBSD 11.1 on sun4u, SS-5 and SS-20, and Red Hat
  Linux 6.2 on SS-5 and SS-20 are automated). Today the weekly `pve` matrix reinstalls Solaris 2.6 on
  SS-5.
- **A boot through PVE on every PR that changes `qemu-server.patch`.** Alpine on aarch64 and x86
  takes about a minute and needs only a small ISO, so it could run on GitHub-hosted runners. The
  three start-up bugs fixed in #248 all passed the "QEMU accepts the command" tests.
- **More SPARC audio and cg14**, after the platform is stable. The SS-5's CS4231 plays (Done).
  Researched, not started: sun4u (OpenBSD/sparc64 has `eap` for QEMU's ES1370; NetBSD/OpenBSD USB
  audio; Solaris 10 has only USB audio), the CS4231 in an SBus slot of the SS-10/SS-20 as the MiSTer
  SS-20 core does (an FCode PROM and an OpenBIOS node), CS4231 capture, cg14 without SX (an old
  MIT-licensed model exists for QEMU 0.14; OpenBIOS has no cg14 driver), DBRI and SX last.
- **Recordings from the weekly run** into the `media` release (`publish_media`, off by default).
- **More than one CPU under the SS-20 Sun PROM.** OBP 2.25 doesn't read the CPU count from QEMU; it
  expects every CPU module to run from reset, find its MBus module ID in the MSI's MID register and
  be stopped and started through the MSI arbiter, while QEMU keeps the other CPUs halted until an
  OpenBIOS-style start (`Cpu #1 Nothing there`). The map is the documented OBP 2.25 disassembly in
  MiSTer-devel/SunSparcStation20_MiSTer (`docs/rom-disassembly/ss20-obp-2.25/`), read but not
  verified on QEMU; it would mean changes to QEMU's sun4m and isn't small (`submodules/SPARC.md`,
  "SMP").

## Known and not fixed

| What | Notes |
| --- | --- |
| The Solaris 2.6 CD on SS-20 sometimes hangs after `Configuring devices...` | 1 of 6 boots on an idle host; the `machines` matrix can fail on it |
| The SunOS 4.1.4 install kernel crashes QEMU with 256 MB (`Trap 0x29`) | 64 MB works; the installed system runs with 256 MB. The install target `sunos414-ss5` runs its install phase with 64 MB and sets 256 MB afterwards |
| `zs3: ring buffer overflow` in Solaris under load | Mouse data arrives faster than a 1200 baud mouse would send it; harmless. Pacing the ESCC mouse would remove it |
| A break on a serial console hangs Solaris | QEMU's ESCC never ends a break and keeps its interrupt raised; Solaris spins in its serial interrupt. PVE can't send a break; a QEMU ESCC patch would fix it (`submodules/SPARC.md` "Stop-A") |
| X in Solaris 2.6 only starts at 1024x768 on cg3 | Larger sizes give a text console; qemu-server has no resolution option |
| More than 512 MB on SS-10/SS-20 (Solaris 2.6 panics at boot) | Unverified lead: the MiSTer SS-20 project's OpenBIOS splits memory into several `/memory` entries because Solaris 8 panics early with all of it in one (`submodules/SPARC.md`, "SMP") |
| A disk installed on SS-5 does not boot on SS-10/SS-20 | Device paths differ; needs a repair from the CD's miniroot, not written or tested |
| Solaris 2.5.1 and 2.6 idle on SS-10/SS-20/SS-5 only for the kernel builds in `SPARC.md` | A differently compiled idle loop is not recognised and spins as before |
| A CD that answers as a disk (`cd_as_disk=1`) has no field in the web UI | Set it with `qm set` or the API; the CD/DVD editor keeps it when the medium changes |
| Live migration of a VM without `-cpu`; `qm suspend --todisk` | Not working or not tested |
| `floppy.spec.ts` "Hardware: Add -> Floppy Drive" times out on a fresh container | Passes on rerun; a cold-start flake |
| `sync-from-upstream-trigger.yml` cannot work | Its `gh workflow run` steps have no token |
| `build-deb.yml` builds the 3dfx extra in a job that also holds the PAT | Should be split so the third-party build never sees the token |
| The MCP server test's `serial_read` check failed once (19 != 20 characters) | Passed on the next commit; a timing flake |
| The issue path of the optional-extras report | Has only run with nothing missing |

## The lab host

The self-hosted runner (label `sparc-lab`) holds what the lab needs and git does not:

| Path | Content |
| --- | --- |
| `/mnt/sparc/iso` | install media: SunOS 4.1.4, Solaris 2.4–10, and under `other-os/` NetBSD, OpenBSD, Debian, Alpine, Red Hat Linux 6.2 |
| `/srv/sparc/disks` | installed disks the matrices boot, and the Sun-labelled disk templates |
| `/mnt/sparc/disks` | newer disks: sparc64 installs, the bench disk and its build disk. A matrix that boots one of them needs `disks_dir=/mnt/sparc/disks`, or the file copied to `/srv/sparc/disks` (done for `netbsd111-sparc64-installed.raw`, which the `sparc64` matrix needs) |
| `/mnt/sparc/src` | SunOS 4.1.4 and Solaris 2.6 source, for reference only |
| `/mnt/sparc/prom` | Sun firmware updates, for experiments only |
| `/mnt/sparc/runs` | run output and evidence directories |

None of the Sun software, firmware or source goes into this repository or into anything published
from it.

## Upstream reports to send

Write-ups are in `upstream/`: the ESP bus reset bug (QEMU), the ESP selection timeout and Stop-A
powering the machine off (OpenBIOS),
the 1-byte APC region (QEMU), the TLB flush on every change of the SRMMU no-fault bit (QEMU) and
the interrupt not taken after a write to `%psr` in a delay slot (QEMU, the Solaris SMP hang) and
sparc32 `ld`/`st %fsr` refused with rd other than 0 (QEMU, found and fixed by Antoni Sawicki in LEMU).
QEMU declines AI-generated code contributions, so these are bug reports, not patches. Candidates
not written up yet: the TTE page-size truncation if it is not merged upstream, the ESCC mouse
rate, and the ESCC break that never ends.
