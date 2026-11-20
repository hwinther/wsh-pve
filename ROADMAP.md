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
| sparc32 `ld`/`st %fsr` with any rd (LEMU `0cdd14c1` by Antoni Sawicki, pve-qemu `wsh/0026`, qtest `wsh/0027`): old static SunOS 4 programs whose `_sigtramp` saves the FSR with rd 4 no longer die with SIGILL; a QEMU regression since 8.2, upstream note kept as a record only (LEMU origin, not for QEMU) | in review | |
| Install targets: Red Hat Linux 6.2 on SS-5 and SS-20 (`redhat62-ss5`, `redhat62-ss20`, OpenBIOS): kickstart from an answer CD the tool makes on the node (the `unattended` method, `answer_media.py`), SILO's screens answered on the serial console, `/boot` first on the disk for SILO | in review | |
| Install matrix fixes after the first full run (27/29): `sol8-ss5` no longer takes the line after the answered "Ready to Install" menu for a prompt (`PROMPT_END`); a Solaris 2.2-2.6 CD boot that hangs before the installer's first prompt (`sol23-ss20` once, likely the ESP deadlock) fails after 300 s and is retried once; Debian 4.0 in `pve_matrix.py install` through an apt cache pinhole (`--apt-cache` / `WSH_LAB_APT_CACHE`, no general way out for the guests), no `matrix_skip`; `lab.py boot-test` of a Debian disk no longer demands `--gateway`/`--dns` | in review | |
| Install targets: Debian GNU/Linux 4.0 "etch" on SS-5 and SS-20 (`debian40-ss5`, `debian40-ss20`, OpenBIOS): preseed from an answer CD the tool makes on the node, loaded by `preseed/early_command` on SILO's boot line, packages from `archive.debian.org` (expired archive key: `allow_unauthenticated`), `--apt-proxy` for a package cache; needs the ESP fix `wsh/0038` (Linux 2.6.18's `esp.c` sync negotiation), published in pve-qemu-kvm 11.1.3-2+wsh20 (both targets passed on +wsh21); out of `pve_matrix.py install`, which gives the guest no `--gateway`/`--dns` | merged | #325 |
| Sound on the SS-5: the CS4231 plays through its APC DMA (LEMU `2938ff88`, `42d32575` by Antoni Sawicki, pve-qemu `wsh/0028`-`0029`), at SBus level 5 as the real machine (`wsh/0030`, openbios 0018), no start failure without an audiodev (`wsh/0031`), no lost tail (`wsh/0032`), qtest (`wsh/0033`); qemu-server `audio0: device=cs4231` (drivers `none`, `alsa`, `pa`, `pipewire`; SPICE, SS-10/SS-20 and sparc64 refused), the UI offers only that on sparc. SunOS 4.1.4, Solaris 2.5.1 and 2.6 play in the lab under OpenBIOS and `ss5.bin`. Limits: no DBRI on SS-10/SS-20 (not emulated), nothing in the web console (no SPICE on sparc32), no capture | in review | |
| Install targets: Solaris 7 (`sol7-ss5`, `sol7-ss20`) also on the 9G disk (`--disk-size 9G`; 3G stays the default), measured through PVE | in review | |
| sun4u system MAC from `net0` (pve-qemu `wsh/0034`, qtest `wsh/0035`): QEMU wrote its default `52:54:00:12:34:56` into the IDPROM unless the NIC was the onboard `-nic`, and NetBSD and Solaris use the IDPROM's MAC for `hme0`; now it is the first `sunhme`'s (else the first NIC's), so the guest sends from the MAC in the VM config (NetBSD `hme`/`wm`, Solaris 10 `hme`). No qemu-server change; upstream note written. The Solaris host id follows the MAC (`80123456` on every VM before), so it changes on existing VMs. Solaris 10 boots 10 of 10 with it and OpenBIOS 0013-0017 (the earlier `BAD TRAP: type=4e` in 2 of 5 was the firmware bug 0016 fixes) | in review | |
| sun4u with more than 3 GB: OpenBIOS patches 0013-0015 (heap above 4 GB, `claim` against the firmware's virtual range, the whole address in `phys.lo`); NetBSD 11.1 and Solaris 10 run with up to 8 GB in the lab, an upstream note; the sparc64 profile's cap in qemu-server and the UI goes from 3072 to 8192 MB | merged | #309 |
| Install targets, Solaris post-install: the data disk on `/usr/local` (`--data-mount`), `--post-install sun26gnu` (34 GNU packages from the owner's local CD with `pkgadd -n` and an admin file, the CD in `scsi5` for that boot only) and `--local-env` (`PATH`, `MANPATH`, bash for `--user`; root keeps `/sbin/sh`), checked by `--check`; Solaris 2.6 and 7 on SS-5 and SS-20 (the 2.6 packages run on 7) | in review | |
| Older Sun releases on sun4m: install targets for Solaris 2.3 Edition II (`sol23-ss5` with `ss5.bin`, `sol23-ss20` with `ss20_v2.25_rom`; sysidtool's older screens and Quick Install), Solaris 2.5 HW 1/96 (`sol25-ss5`, `sol25-ss20`, OpenBIOS) and SunOS 4.1.3_U1B (`sunos413u1b-ss5`, `sunos413u1b-ss20`, the 4.1.4 install unchanged), all with `cd_as_disk` where Solaris needs it, 6-11 min each through PVE; Solaris 2.1/2.2 and SunOS 4.1.3 (SS-10 era) and 4.1.2 on SS-600MP measured: they don't boot (`submodules/SPARC.md`, "Older Sun releases on sun4m") | in review | |
| Solaris 2.1-2.4 under OpenBIOS on sun4m: openbios 0019-0022 (the FCode boot block's OBP 2.x words, the Forth heap inside the firmware's range, node 0 as the root, romvec calls with interrupts masked); 2.2 on SS-10, 2.3 and 2.4 on SS-5 install and boot in the lab (CD as a disk), 2.1 stops in QEMU (`Trap 0x21`); SunOS 4.1.3's `type=29` diagnosed (a probe of `0xd.0108_0000`); openbios 0023 (client interface: no catch result over the stack with `nret` 0) lets OpenBSD 8.0's installed sun4u kernel boot | in review | |
| Install targets: Solaris 8 and 9 on the SS-5 (`sol8-ss5` from 8 2/02, `sol9-ss5` from 9 9/05, 256 MB, Web Start through PVE); Web Start's screens of the later updates answered (9 9/05's license question, 8 2/02's CD prompts); 8 2/02 and 9 9/05 on sun4u measured: they stop at the same `pp is NULL or free` panic as 8 1/01 and 9 (OpenBIOS's physical allocation, `submodules/SPARC.md`) | in review | |
| Solaris 7/8/9 on sun4u: OpenBIOS 0024 lists `/memory` `available` in whole pages, which ends `boot_alloc: pp is NULL or free` (claims recorded to the byte left entries starting inside a page; Solaris 7-9 counted them one page short and a later boot allocation got the missing page). 7, 8 1/01, 8 2/02, 9, 9 9/05 reach the installer with 1 and 2 GB; 8 2/02 and 9 9/05 install and boot to `console login:` in the lab (1 GB); upstream note | in review | |
| Install targets under OpenBIOS with pve-qemu-kvm 11.1.3-2+wsh22: `sol23-ss5`, `sol23-ss20`, `sol24-ss5` move from the Sun PROMs to OpenBIOS, new `sol24-ss20` and `sol22-ss10` (Solaris 2.2 on SS-10), each installed twice through PVE (~8-10 min); 2.3 and 2.4 on the SS-20 with 2 and 4 CPUs (10 min of load on 4, idle ~5% of a host core); OpenBSD 8.0 on sun4u (`openbsd80-sun4u`, openbios 0023): the installer answered by what it asks, ntpd off, ~19 min | in review | |
| Install targets: OpenBSD 5.9, the last release for 32-bit sparc, on SS-5 and SS-20 (`openbsd59-ss5`, `openbsd59-ss20`, OpenBIOS, ~10 min): `cd59.iso` boots the installer, the sets come from a CD `lab.py media --convert` makes on the node from the release's files (Rock Ridge names, `answer_media.openbsd_sets`), the installer checks them against `SHA256.sig`; needs a serial display (with QEMU's keyboard ESCC the kernel panics, "crazy interrupts") | in review | |
| Install targets: NetBSD 9.3 on sun4u, SS-5 and SS-20 (`netbsd93-sparc64`, `netbsd93-sparc`, `netbsd93-sparc-ss20`) with the 11.1 targets' profiles and sysinst answers; 9.3's sysinst goes from the sets straight to its configuration menu (no root password prompt, no entropy question), handled in `_netbsd.sysinst` with tests for both releases; installed through PVE with `--check --export` and boot-tested from the stored disks (sun4u 18 min, SS-5 7, SS-20 6; boot tests 1.2-1.5 min) | in review | |
| Install targets: Solaris 9 9/05 and 8 2/02 on sun4u (`sol9-sun4u`, `sol8-sun4u`, End User 64-bit, Web Start through PVE); OpenBIOS 0025 leaves out the ebus floppy node (a zero-sized `reg` for hardware QEMU's sun4u doesn't have; Solaris 9's first boot panicked in `fd`); the reboot that returns on sun4u is handled by the tool: the VM is stopped at `0 >` after the install, and 8's reboot into its mini-root is a power cycle through PVE (`PveMachine.power_cycle()`) | in review | |
| Mirror storage, steps 1 and 2 of 3: ISO and floppy images on a NAS as symlinks in a `dir` storage, the folders in the link name with `__` (`Solaris__2.6__solaris_2.6_598_sparc.iso`). `wsh-lab mirror link`/`sync [--prune]`/`list` makes and checks the links (no backend change: PVE's listing follows symlinks); pve-manager groups the storage's ISO and floppy tabs by folder and shows `Solaris / 2.6 / ...` in the ISO and floppy selectors (volume IDs unchanged); `wsh-lab media`/`install` also find a medium by size and sha256 under another name. Step 3 is under "Later" | merged | #345 |
| Mirror storage, step 2b: four ways to use it (plain `__` names in any ISO/floppy storage; a local storage of links; ISOs and links on one NFS/CephFS export with relative links; an externally managed tree stitched into one) as recipes in `reference/mirror.md`; a description file `wsh-mirror.yaml` (watch directories, rules, entries with `origin: manual|import`, `auto_import`, incomplete-file patterns and a minimum age) with `wsh-lab mirror init|plan|apply|import|tidy` (flock, moves found by size and sha256, a manual entry's link only flagged, nothing removed while a share is unreachable) and `mirror timer` (a systemd timer that runs `apply`); mirror storages may be dir, btrfs, nfs, cephfs or cifs. A search field above the ISO and floppy selectors (CD/DVD and floppy editors, the wizard's OS tab): focused on open, every word must be in the name, Enter picks the first match. e2e: an NFS export from NFS-Ganesha in the compose network | in review | |
| Install targets for the matrix holes: Solaris 2.5.1 on the SS-20 under OpenBIOS (`sol251-ss20`, the CD as a disk; the SS-5 target still needs `ss5.bin`), Solaris 2.6 and 7 on the SS-10 (`sol26-ss10`, `sol7-ss10`), each installed through PVE with `--check --export` (stored disk and sidecar in `/mnt/os/disks`) and boot-tested, pve-qemu-kvm 11.1.3-2+wsh25 | in review | |
| BEL on a sparc32 framebuffer console hung Solaris 2.x and SunOS 4.1.4 with the screen inverted (bash's completion bell): OpenBIOS 0026 bounds the blink's wait (the firmware's tick counter stops once the client has its own trap table), and drops the cell each BEL left on the Forth stack; the lab's `fb-bell.py`, an upstream note, a workaround in the guide for packages without it | in review | |
| Idle on sun4u: no guest on QEMU's sun4u has a way to stop the CPU (Solaris/illumos halt only through the SPARC64-VI module, NetBSD and Linux only through the sun4v hypervisor, OpenBSD's `sleep` only on CPUs with several strands), so pve-qemu `wsh/0042`-`0044` recognise the idle loops of NetBSD 9.3/11.1, OpenBSD 8.0, Solaris 9/10 and Tribblix m34 in the translator and halt there (`idle-halt`, on by default; qtest `sun4u-idle-test`): an idle guest at the shell takes 3-9% of a host core instead of 100% (Tribblix about 22%, and only with FMA's `fmd` off: its ZFS disk faults and `rcm_daemon` spins), with the clock, ten `sleep 1` and CPU-bound jobs as before (`submodules/SPARC.md`, "sparc64 (sun4u)", "Idle") | in review | |
| Workflow tokens: `sync-from-upstream-trigger.yml` dispatches the five syncs with `GITHUB_TOKEN` (`actions: write`), and from a branch or with `dry_run` only says what it would start; `build-deb.yml` builds pve-qemu's 3dfx extra in its own job without `WORKFLOW_TOKEN` or stored credentials and hands the binary to the build job as an artifact; the optional-extras report's issue path is tested by `scripts/test-report-qemu-extras.sh` and dry-run against the open issues by `report-qemu-extras-test.yml` | in review | |

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
   - `sol10-sun4u` with `--ip dhcp` (not tested through the tool); the intermittent `bad unknown
     trap at TL 1` panic seen once before the package (none in 6 installs on it); a different one,
     `BAD TRAP: type=4e` in the firmware while the DVD boots, once in 6 DVD boots through PVE
     (`install` retries it);
   - Solaris 7/8/9 `pp is NULL or free`: fixed by OpenBIOS 0024 (`/memory` `available` in whole
     pages; its entries started inside a page and Solaris 7-9 counted them one page short). In the
     lab 7, 8 1/01, 8 2/02, 9 and 9 9/05 reach their installers with 1 and 2 GB; 8 2/02 and 9 9/05
     install to the IDE disk with 1 GB and boot to `console login:`; the install targets
     `sol9-sun4u` and `sol8-sun4u` do it through PVE (the floppy node: OpenBIOS 0025; the reboot:
     the tool stops the VM, and power-cycles it for 8's mini-root). 0025 is in pve-qemu-kvm
     11.1.3-2+wsh25 (`sol9-sun4u` installed and passed its check on it, ~74 min; no `matrix_skip`
     any more). Open: the firmware reboot itself (0012), Solaris 7 on sun4u (reaches its installer; no target yet), 2.5.1/2.6 boot-block
     exceptions.
   Details: `submodules/SPARC.md`, "Solaris on sun4u".
3. **Tribblix (illumos) on sun4u** (`feat/lab-tribblix-sun4u`). Tribblix m34, the newest SPARC
   release, needed two more OpenBIOS fixes: 0016 runs the client interface with interrupts off
   (illumos calls it with interrupts on; an interrupt while the firmware saved or restored the
   caller's register windows corrupted them on 4 of 7 live CD boots; also the cause of Solaris 10's
   one `BAD TRAP: type=4e`), and 0017 puts `xa+`/`xa1+` back into the 64-bit FCode table (every token
   from 0x24a on ran the wrong word, so the illumos ZFS boot block crashed). With both, the live CD
   boots to its login prompt, installs to the IDE disk with its own installer, and the installed disk
   boots, gets its address and powers off; `lab.py install tribblix-m34-sun4u` drives it through PVE
   (with pve-qemu-kvm 11.1.3-2+wsh20 or later; 257 minutes through PVE, too long for `pve_matrix.py
   install` under the job's 240-minute limit, so it stays out;
   3 of 3 long runs passed). The guest's clock that stopped in about one of three long runs (a QEMU
   race on `%softint`) is fixed by pve-qemu `wsh/0036`. Still open:
   - with a ZFS root FMA marks the IDE disk DEGRADED during the install (EIO on first attempts that
     ZFS retries; no data errors); a UFS install (`ROOT_FS=ufs`) avoids that but hasn't been booted;
   - the live CD's package catalogue is older than its packages, so an offline install skips some
     (curl, tcsh, GNU coreutils, ...); a Tribblix issue;
   - very slow under TCG: about 45 minutes to the live CD's login, and the first boot of the
     installed system imports the SMF manifests again.
   Details: `submodules/SPARC.md`, "Tribblix on sun4u".

## Next, in this order

1. **Idle on sparc64, what is left.** The guests with a stored disk idle (see Done: `wsh/0042`-`0044`).
   Not covered: Linux on sun4u (Debian 12's install fails, so no disk; its `arch_cpu_idle()` does
   nothing on sun4u either), Solaris 8 (no stored disk yet; its `idle()` is probably laid out like 9's,
   not checked), other kernel builds than the ones in `SPARC.md`, and sun4v/`niagara` (hypervisor
   `cpu_yield`). Each new guest: disassemble its idle loop and add a layout with a qtest case.
2. **Solaris on sun4u**: see "In progress". Solaris 10 installs through `lab.py install`; next: a
   reboot that works from Solaris (0012 hangs).
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
   - Driver and patch packs: the owner's curated DOS and Windows 9x drivers and patches (the VBE
     display drivers among them) that the README and the guest operating systems guide mention. First
     sort out what may be published: much of it is proprietary, and what isn't gets a source and a
     licence next to it; the rest stays a list of what to get and where. Then a guide per pack.
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

- **Mirror storage, step 3.** Next: a rename API for `iso` and `floppy` volumes in libpve-storage-perl (a link or a file renamed
  in place, so folders can be reorganised from the UI), and an "add link from another storage" call
  (link a volume of one storage, an NFS or CIFS storage's ISO, into the mirror storage under a folder
  name) with its UI in the storage's ISO and floppy tabs. Open questions: who may create links that
  point outside a storage (`Datastore.Allocate` on both storages at least), and what a cluster node
  without the target's mount shows.
- **A larger package CD for Solaris 2.6/7.** `sun26gnu.iso` (34 packages) came from the sunfreeware
  collection now on the lab host (521 packages for `sol26-sparc`); four of its packages have newer
  builds there (ddrescue, openssl, sed, top) and many useful ones are missing (openssh with prngd,
  gcc/binutils/make/gdb and the autotools, tar/findutils/grep/gawk, tcsh/zsh/emacs, perl, python,
  ntp, cvs/subversion). A second local-only CD and `--post-install` bundle, with dependencies in
  order and a bigger data disk. The owner will choose the set.
- **Extra OS packages per install** (owner's request, later). A way to name packages from the OS
  media that a target adds on top of its software group, for example Solaris's `SUNWaudmo` (audio
  demo files) and `SUNWxwoft` (optional X fonts, which SimCity among others needs). Likely shape:
  `wsh-lab install <target> --packages SUNWaudmo,SUNWxwoft` and/or a `packages` list in the target
  or profile. For Solaris, `pkgadd` from the mounted media in the first boot or check step, or the
  installer's Customize step where the scenario supports it; for other systems their own installer
  sets or packages.
- **More architectures.** In order of fit: HP-UX on PA-RISC (`qemu-system-hppa`, open firmware,
  upstream), PowerPC (AIX 5.1 on `40p`, AIX 7 on `pseries`, Mac OS), Quadra 800 with A/UX. AIX 3.2.5
  needs LEMU's MCA machine, which is a large out-of-tree model. IRIX and DG/UX are not feasible in
  QEMU today.
- **More sparc32 guests and older releases.** QEMU emulates sun4m only (no sun4c or sun4), so the
  floor is set by when each machine got support (Sun's System Handbook, its SPARC module guide, the
  Solaris FAQ): SunOS 4.1.3 (Solaris 1.1) on the SS-10 (one CPU; SunOS 4 has no MP on it);
  4.1.3_U1B (1.1.1B) on the SS-20 and the SS-5 (the SS-5 with the microSPARC-II kernel patch
  101508); 4.1.4 (1.1.2) is what `sunos414-ss5` installs. Solaris 2.0 is sun4c only; 2.1 already
  runs on the SS-10, 2.3 on the SS-20, and the SS-5 from 2.3 Edition II. The QEMU wiki lists
  NeXTSTEP 3.3 and OPENSTEP 4.2 as partly working on sun4m (hangs on disk access, perhaps the ESP;
  several ESP fixes are carried here since) and OpenBSD 5.8 as working with `-nographic`. Order: first what the lab
  host has media for (SunOS 4.1.4; NetBSD 9.3 on sparc and
  sparc64; OPENSTEP 4.2, whose User CD, though named "Intel", also carries the SPARC and m68k
  versions and has a Sun disk label, so OpenBIOS or OBP can boot its installer),
  NeXTSTEP 3.3 for SPARC (the SPARC/PA-RISC User CD, Sun-labelled, a SPARC and hppa kernel) and
  OpenBSD 5.9 (the last release with sparc32), all on the lab host now. Done (see "Done"): SunOS
  4.1.3_U1B, Solaris 2.3 and 2.5 install; OpenBSD 5.9 installs on SS-5 and SS-20 (`openbsd59-ss5`,
  `openbsd59-ss20`; the sets from a CD made on the node, a serial display: with QEMU's keyboard
  ESCC its kernel panics, which isn't narrowed down yet, `submodules/SPARC.md`, "OpenBSD 5.9 on
  sun4m"; 5.8's `install58.iso` wasn't needed and isn't tried);
  the original SunOS 4.1.3 and 4.1.2 (SS-600MP) don't boot. OpenBIOS 0019-0022 run the Solaris
  2.1-2.4 boot program: 2.2 (SS-10), 2.3 and 2.4 (SS-5 and SS-20) are install targets under OpenBIOS
  since pve-qemu-kvm 11.1.3-2+wsh22 (`sol22-ss10`, `sol23-ss5`, `sol23-ss20`, `sol24-ss5`,
  `sol24-ss20`; 2.3 and 2.4 on the SS-20 also run with 2 and 4 CPUs); 2.1 stops in QEMU after its
  device configuration.
  NeXTSTEP 3.3 and OPENSTEP 4.2 (lab, 2026-11-19): the disk hang is still there with our ESP fixes,
  and it is diagnosed: QEMU's ESP raises its interrupt in the instruction that starts a command, and
  NeXT's SCSI driver then spins at PIL 4 on a lock the interrupted thread holds. pve-qemu patch
  `wsh/0040` (with the qtest `wsh/0041`) adds `irq-latency-us` to `sysbus-esp`, off by default
  (it costs about 2 ms per disk command); a VM turns it on with `machine: SS-5,esp-irq-latency=500`
  (qemu-server, a field in the web UI's Machine editor). With it both install on an SS-5 to the
  Workspace (CD stage under OpenBIOS or `ss5.bin`, the installed disk only under `ss5.bin` with `-v`;
  TCX, keyboard and mouse), also through PVE; the sparc32 regressions passed with the delay on every
  guest and with it off (results and disk numbers in `submodules/SPARC.md`, "NeXTSTEP 3.3 and
  OPENSTEP 4.2"). The SS-20 has no firmware that boots the installed disk. The packages have 0040
  and the qemu-server option since pve-qemu-kvm 11.1.3-2+wsh24 and qemu-server 9.2.19+wsh2 (the
  option checked through PVE on those packages: `qm showcmd` passes `-global
  sysbus-esp.irq-latency-us=500`, x86 refuses it). Next: framebuffer scenarios and the catalogue entries
  `nextstep33-ss5`/`openstep42-ss5` (their profiles set the option) made targets; OpenBIOS's failure on the
  installed disk (exception 0x21 in NeXT's boot program) is open.
- **Solaris releases not tried yet.** With media on the lab host: 8 with `ss5.bin` on the SS-5.
  (2.2, 2.3, 2.4 on the SS-20, 2.5 and 2.1 are done: "Done" and the item above; 2.5.1 on the SS-20
  under OpenBIOS and 2.6 and 7 on the SS-10 are install targets, "Done"; 8 2/02 and 9 9/05 install on the SS-5 and SS-20, and on sun4u with OpenBIOS
  0024.) Needing media: 8 2/04, and an earlier Solaris 10 update on sun4u. Out of reach: 2.0 and SunOS
  4.1.1 or older (sun4c only), Solaris 11 (no UltraSPARC IIi).
- **OpenBSD 8.0 on sun4u: IDE timeouts, then a guest that takes no interrupt.** The installed
  kernel boots since openbios 0023 (pve-qemu-kvm 11.1.3-2+wsh22) and `openbsd80-sun4u` installs it
  through PVE with ntpd off ("Done"). Still open: with outside network access, `wd0: timeout` follows
  ntpd's clock slew in 5 of 6 boots; without ntpd it happens too, rarely (1 of 5 installs on
  the CD, one of several boots with a 1 GB `tar` of `/usr`), and the guest then sits in its idle
  loop with interrupts enabled, no I/O and no answer to the console or a break
  (`submodules/SPARC.md`, "sparc64", "IDE timeouts without ntpd"). Find the lost interrupt in QEMU's
  sun4u path (cmd646, sabre, interrupt vector; `wsh/0021`'s latch is a suspect), then drop the
  target's install retry and let it keep ntpd on. Also not tried through the tool: DHCP
  (`--ip dhcp`, the lab's own runs got an address with `inet autoconf`).
- **Scheduled reinstalls.** One install per supported profile, weekly or monthly, replacing the
  stored disk when it passes, so every disk the lab boots can be rebuilt. The machinery exists: the
  install targets (`e2e/sparc/targets.py`, `lab.py install`) and `pve_matrix.py install` (the
  `install` choice of the `sparc lab` workflow). Done: install once, then boot-test the stored disk
  (e2e/sparc/README.md, "Install once, then boot-test the stored disk"): a target without a stored
  disk is installed with `--check --export`, which keeps the disk in `/mnt/os/disks` as
  `install-<target>.raw` with a JSON sidecar (date, packages, minutes) once the check passed;
  otherwise `lab.py boot-test` boots a copy of it through PVE and runs the target's check, and the
  workflow's `reinstall` input (or `--reinstall`) installs targets again. `matrix_skip` targets
  (Tribblix ~4.3 h) are installed only on request and boot-tested once their disk exists. Debian 4.0
  is in the matrix when the repository has `WSH_LAB_APT_CACHE` (a secret or variable, HOST:PORT of
  an apt-cacher-ng the runner reaches): the guests get that cache through a pinhole on the test
  node's `vmbr0` (10.0.2.2:3142, socat, no forwarding or NAT) and nothing else; without it they are
  skipped.
  The `install` choice runs weekly (Sunday 07:17 UTC, after `smoke` and `pve`): boot tests of the
  stored disks, plus installs of targets that have none yet. Still to do: maybe a monthly
  `reinstall=all` (about 6 h, needs the 720-minute limit on a schedule), and automate more targets (Solaris 2.2-10, SunOS 4.1.3_U1B and 4.1.4, NetBSD 11.1 on sun4u, SS-5 and SS-20, OpenBSD 8.0
  on sun4u, Tribblix, and Red Hat Linux 6.2 and Debian 4.0 on SS-5 and SS-20 are automated). Today the weekly `pve` matrix reinstalls Solaris 2.6 on
  SS-5.
- **A boot through PVE on every PR that changes `qemu-server.patch`.** Alpine on aarch64 and x86
  takes about a minute and needs only a small ISO, so it could run on GitHub-hosted runners. The
  three start-up bugs fixed in #248 all passed the "QEMU accepts the command" tests.
- **More SPARC audio and cg14**, after the platform is stable. The SS-5's CS4231 plays (Done).
  Researched, not started: sun4u (OpenBSD/sparc64 has `eap` for QEMU's ES1370; NetBSD/OpenBSD USB
  audio; Solaris 10 has only USB audio), the CS4231 in an SBus slot of the SS-10/SS-20 as the MiSTer
  SS-20 core does (an FCode PROM and an OpenBIOS node), CS4231 capture, cg14 without SX (an old
  MIT-licensed model exists for QEMU 0.14; OpenBIOS has no cg14 driver), DBRI and SX last.
- **Patch coverage (idea).** Measure how much of the code we own the tests run, not upstream's:
  `submodules/*.patch` gives our lines (the `+` side of each hunk matches the patched source the
  build uses), and a small script intersects them with lcov from each layer into "X of Y own lines
  run", per patch and, on a PR, for the hunks it changes. In order: (1) the web UI, with V8 coverage
  from the existing Playwright run through monocart (`pvemanagerlib.js` is a concatenation, not
  minified, so ranges map back to `www/manager6` files from the Makefile order); (2) the Perl side
  with `Devel::Cover` on the cfg2cmd and unit tests (cheap), and maybe under e2e with
  `PERL5OPT=-MDevel::Cover` on pvedaemon/pveproxy (slow, noisy); (3) a gcov build of pve-qemu for
  the qtests and part of the lab matrix, as a manual or weekly report (which wsh patches no test
  runs). OpenBIOS has no practical coverage. A report as an artifact or PR comment, never a
  required check: coverage shows code ran, not that anything was asserted.
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
| OpenBIOS 0009 on sparc64 prints `decode-unit isn't unique.` / `encode-unit isn't unique.` at power-on | Its `drivers/pci.c` hunk redefines the two words in the ebus node, which already has the PCI bridge's methods. Harmless so far; untested idea: give the ebus node its own methods (found by the LEMU port) |
| SS-5 with OpenBIOS: `(enter)` then `go` at the prompt stops QEMU with `Trap 0x21` (instruction access error, traps off) | OpenBIOS 0008's prompt/resume path; not a supported path, reproducible with `-M SS-5 -prom-env auto-boot?=false` (found by the LEMU port) |
| The Solaris 2.6 CD on SS-20 sometimes hangs after `Configuring devices...` | 1 of 6 boots on an idle host; the `machines` matrix can fail on it |
| The SunOS 4.1.4 install kernel crashes QEMU with 256 MB (`Trap 0x29`) | 64 MB works; the installed system runs with 256 MB. The install target `sunos414-ss5` runs its install phase with 64 MB and sets 256 MB afterwards |
| `zs3: ring buffer overflow` in Solaris under load | Mouse data arrives faster than a 1200 baud mouse would send it; harmless. Pacing the ESCC mouse would remove it |
| A break on a serial console hangs Solaris | QEMU's ESCC never ends a break and keeps its interrupt raised; Solaris spins in its serial interrupt. PVE can't send a break; a QEMU ESCC patch would fix it (`submodules/SPARC.md` "Stop-A") |
| X in Solaris 2.6 only starts at 1024x768 on cg3 | Larger sizes give a text console; qemu-server has no resolution option |
| More than 512 MB on SS-10/SS-20 (Solaris 2.6 panics at boot) | Unverified lead: the MiSTer SS-20 project's OpenBIOS splits memory into several `/memory` entries because Solaris 8 panics early with all of it in one (`submodules/SPARC.md`, "SMP") |
| NeXTSTEP 3.3 and OPENSTEP 4.2 hang on the disk during their install unless the VM has `machine: SS-5,esp-irq-latency=500` | QEMU's ESP raises its interrupt in the same instruction that starts a command; NeXT's driver deadlocks. The opt-in delay (`wsh/0040`) is in pve-qemu-kvm 11.1.3-2+wsh24, qemu-server 9.2.19+wsh2 and pve-manager 9.2.31+wsh2 (the UI field); off by default, as it costs about 2 ms per disk command (`submodules/SPARC.md`, "NeXTSTEP 3.3 and OPENSTEP 4.2"; the sparc guide, "SCSI interrupt delay") |
| OpenBIOS doesn't boot an installed NeXTSTEP/OPENSTEP disk | `Unhandled Exception 0x00000021` in NeXT's boot program before its banner; `ss5.bin` boots it (with `-v`: its boot graphics end in `Data Access Error` on the 8-bit TCX). Not diagnosed |
| A disk installed on SS-5 does not boot on SS-10/SS-20 | Device paths differ; needs a repair from the CD's miniroot, not written or tested |
| Solaris 2.5.1 and 2.6 idle on SS-10/SS-20/SS-5 only for the kernel builds in `SPARC.md` | A differently compiled idle loop is not recognised and spins as before |
| sun4u idle only for the kernel builds in `SPARC.md` (NetBSD 9.3/11.1, OpenBSD 8.0, Solaris 9 9/05 and 10 1/13, Tribblix m34) | A differently compiled idle loop is not recognised and spins as before (`-trace sparc64_idle_match` shows a match) |
| A CD that answers as a disk (`cd_as_disk=1`) has no field in the web UI | Set it with `qm set` or the API; the CD/DVD editor keeps it when the medium changes |
| Live migration of a VM without `-cpu`; `qm suspend --todisk` | Not working or not tested |
| `floppy.spec.ts` "Hardware: Add -> Floppy Drive" times out on a fresh container | Passes on rerun; a cold-start flake |
| `build-deb.yml`'s separate 3dfx job has not run in a package build yet | A branch dispatch would publish, so it was checked with actionlint and a local run of the hand-over step; the first pve-qemu build on main is its test (its run should show `qemu-system-x86_64-3dfx from the 3dfx build of ...` and the release no "Optional extras missing") |

## The lab host

The self-hosted runner (label `sparc-lab`) holds what the lab needs and git does not:

| Path | Content |
| --- | --- |
| `/mnt/os/iso` | install media: SunOS 4.1.4, Solaris 2.4–10, and under `other-os/` NetBSD, OpenBSD (8.0 sparc64; 5.8 and 5.9 sparc), Debian (12 sparc64, 4.0r9 sparc netinst), Alpine, Red Hat Linux 6.2, Tribblix, NeXTSTEP 3.3 (SPARC/PA-RISC), OPENSTEP 4.2 (User and Developer) |
| `/mnt/os/floppy` | floppy images (MS-DOS 6.22, FreeDOS 1.4) |
| `/mnt/os/disks` | installed disks the matrices boot (sun4m and sun4u), the bench disk and its build disk, and the Sun-labelled disk templates |
| `/mnt/os/sun-reference/src` | SunOS 4.1.4 and Solaris 2.6 source, for reference only |
| `/mnt/os/sun-reference/prom` | Sun firmware updates, for experiments only |
| `/mnt/runs` | run output and evidence (a disk of its own, so a run that fills it stops only runs); `archive/` has the early runs |

`/mnt/os` and `/mnt/runs` replaced `/mnt/sparc` and `/srv/sparc` on 2026-11-19; symlinks under the old
paths point to the new ones for now.

None of the Sun software, firmware or source goes into this repository or into anything published
from it.

## Upstream reports to send

`upstream/README.md` lists every carried patch with a QEMU (or OpenBIOS) column; its "Rule" section
applies LEMU's request that LEMU patches and LEMU bug reports not go to QEMU. Nothing of LEMU
origin or built on LEMU code is sent from here: the ESCC, cg3, SunOS and Solaris idle, `ld`/`st %fsr`
and CS4231 audio patches stay ours to carry (the `%fsr` write-up is kept as a record only).

Write-ups the owner may send (as bug reports, or patches written by hand; QEMU and OpenBIOS decline
AI-generated code): the ESP bus reset, the 1-byte APC region, the TLB flush on every change of the
SRMMU no-fault bit, the interrupt not taken after a write to `%psr` in a delay slot (the Solaris SMP
hang), the cmd646 interrupt latch, sun4u's IDPROM ignoring a NIC added with `-device`, the sparc64
`%softint` race and the ESP CDB counted with the message out bytes (QEMU); the ESP selection
timeout, Stop-A powering the machine off, and the sparc64 fixes 0003-0011 and 0013-0017 (OpenBIOS).
Not written up yet: the TTE page-size truncation, if it is not merged upstream.

On hold until reproduced on plain QEMU without LEMU patches: the ESCC mouse rate and the ESCC break
that never ends (seen with LEMU's ESCC patches), and the audio mixer's 6 dB on a mono output and the
`wav` backend's empty header sizes (seen with LEMU's CS4231).
