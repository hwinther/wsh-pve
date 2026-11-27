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
| sparc lab in CI: guests booted and installed on a self-hosted runner, weekly (plus a monthly `reinstall=all`) and on demand | running | #230 |
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
| Idle with more than one CPU: Solaris 2.5.1–9 on SS-10/SS-20 halt idle vCPUs in the multiprocessor idle loop (`solaris-smp-idle`, pve-qemu `wsh/0023`-`0025`), ~4-5% of a host core idle with 2 or 4 CPUs instead of 100% per vCPU | merged | #295 |
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
| DOS idle: `WSHIDLE.COM` (HLT on DOS idle) in the `msdos622` install, FreeDOS's FDAPM verified; 1-2% of a host core at the prompt instead of 100%, keyboard, timer and busy programs unaffected (`POWER.EXE` measured: idles, but slows keyboard-polling programs 2.5-10x); checks in both targets and the FreeDOS CI test | merged | #361 |
| DOS: `machine: ...,legacy-bios-layout=1` in qemu-server and the UI (x86 with SeaBIOS only): NICs without option ROM, no vapic ROM; the `msdos622` VM's UMB grows from 98K to 114K (102K to 118K with `I=`) through PVE | merged | #361 |
| Install targets: SunOS 4.1.4 on SS-5 (`sunos414-ss5`): miniroot, `suninstall` Quick install and sys-config on the serial console through PVE, the CD made from its raw BIN by `lab.py media --convert`, 64 MB for the install phase only | merged | #299 |
| A CD that answers as a disk: `cd_as_disk=1` on a sparc32 SCSI CD-ROM (qemu-server: `scsi-hd`, read only, still a CD-ROM to PVE; refused elsewhere); install targets `sol24-ss5` (Solaris 2.4 HW 3/95, ~10 min) and `sol251-ss5` (2.5.1 11/97, ~45 min, most of it its Maintenance Update) on SS-5 with `ss5.bin` through PVE | merged | #314 |
| sparc32 `ld`/`st %fsr` with any rd (LEMU `0cdd14c1` by Antoni Sawicki, pve-qemu `wsh/0026`, qtest `wsh/0027`): old static SunOS 4 programs whose `_sigtramp` saves the FSR with rd 4 no longer die with SIGILL; a QEMU regression since 8.2, upstream note kept as a record only (LEMU origin, not for QEMU) | merged | #315 |
| Install targets: Red Hat Linux 6.2 on SS-5 and SS-20 (`redhat62-ss5`, `redhat62-ss20`, OpenBIOS): kickstart from an answer CD the tool makes on the node (the `unattended` method, `answer_media.py`), SILO's screens answered on the serial console, `/boot` first on the disk for SILO | merged | #320 |
| Install matrix fixes after the first full run (27/29): `sol8-ss5` no longer takes the line after the answered "Ready to Install" menu for a prompt (`PROMPT_END`); a Solaris 2.2-2.6 CD boot that hangs before the installer's first prompt (`sol23-ss20` once, likely the ESP deadlock) fails after 300 s and is retried once; Debian 4.0 in `pve_matrix.py install` through an apt cache pinhole (`--apt-cache` / `WSH_LAB_APT_CACHE`, no general way out for the guests), no `matrix_skip`; `lab.py boot-test` of a Debian disk no longer demands `--gateway`/`--dns` | merged | #348 |
| Install targets: Debian GNU/Linux 4.0 "etch" on SS-5 and SS-20 (`debian40-ss5`, `debian40-ss20`, OpenBIOS): preseed from an answer CD the tool makes on the node, loaded by `preseed/early_command` on SILO's boot line, packages from `archive.debian.org` (expired archive key: `allow_unauthenticated`), `--apt-proxy` for a package cache; needs the ESP fix `wsh/0038` (Linux 2.6.18's `esp.c` sync negotiation), published in pve-qemu-kvm 11.1.3-2+wsh20 (both targets passed on +wsh21); out of `pve_matrix.py install`, which gives the guest no `--gateway`/`--dns` | merged | #325 |
| Sound on the SS-5: the CS4231 plays through its APC DMA (LEMU `2938ff88`, `42d32575` by Antoni Sawicki, pve-qemu `wsh/0028`-`0029`), at SBus level 5 as the real machine (`wsh/0030`, openbios 0018), no start failure without an audiodev (`wsh/0031`), no lost tail (`wsh/0032`), qtest (`wsh/0033`); qemu-server `audio0: device=cs4231` (drivers `none`, `alsa`, `pa`, `pipewire`; SPICE, SS-10/SS-20 and sparc64 refused), the UI offers only that on sparc. SunOS 4.1.4, Solaris 2.5.1 and 2.6 play in the lab under OpenBIOS and `ss5.bin`. Limits: no DBRI on SS-10/SS-20 (not emulated), nothing in the web console (no SPICE on sparc32), no capture | merged | #317 |
| Install targets: Solaris 7 (`sol7-ss5`, `sol7-ss20`) also on the 9G disk (`--disk-size 9G`; 3G stays the default), measured through PVE | merged | #316 |
| sun4u system MAC from `net0` (pve-qemu `wsh/0034`, qtest `wsh/0035`): QEMU wrote its default `52:54:00:12:34:56` into the IDPROM unless the NIC was the onboard `-nic`, and NetBSD and Solaris use the IDPROM's MAC for `hme0`; now it is the first `sunhme`'s (else the first NIC's), so the guest sends from the MAC in the VM config (NetBSD `hme`/`wm`, Solaris 10 `hme`). No qemu-server change; upstream note written. The Solaris host id follows the MAC (`80123456` on every VM before), so it changes on existing VMs. Solaris 10 boots 10 of 10 with it and OpenBIOS 0013-0017 (the earlier `BAD TRAP: type=4e` in 2 of 5 was the firmware bug 0016 fixes) | merged | #321 |
| sun4u with more than 3 GB: OpenBIOS patches 0013-0015 (heap above 4 GB, `claim` against the firmware's virtual range, the whole address in `phys.lo`); NetBSD 11.1 and Solaris 10 run with up to 8 GB in the lab, an upstream note; the sparc64 profile's cap in qemu-server and the UI goes from 3072 to 8192 MB | merged | #309 |
| Install targets, Solaris post-install: the data disk on `/usr/local` (`--data-mount`), `--post-install sun26gnu` (34 GNU packages from the owner's local CD with `pkgadd -n` and an admin file, the CD in `scsi5` for that boot only) and `--local-env` (`PATH`, `MANPATH`, bash for `--user`; root keeps `/sbin/sh`), checked by `--check`; Solaris 2.6 and 7 on SS-5 and SS-20 (the 2.6 packages run on 7) | merged | #322 |
| Older Sun releases on sun4m: install targets for Solaris 2.3 Edition II (`sol23-ss5` with `ss5.bin`, `sol23-ss20` with `ss20_v2.25_rom`; sysidtool's older screens and Quick Install), Solaris 2.5 HW 1/96 (`sol25-ss5`, `sol25-ss20`, OpenBIOS) and SunOS 4.1.3_U1B (`sunos413u1b-ss5`, `sunos413u1b-ss20`, the 4.1.4 install unchanged), all with `cd_as_disk` where Solaris needs it, 6-11 min each through PVE; Solaris 2.1/2.2 and SunOS 4.1.3 (SS-10 era) and 4.1.2 on SS-600MP measured: they don't boot (`submodules/SPARC.md`, "Older Sun releases on sun4m") | merged | #331 |
| Solaris 2.1-2.4 under OpenBIOS on sun4m: openbios 0019-0022 (the FCode boot block's OBP 2.x words, the Forth heap inside the firmware's range, node 0 as the root, romvec calls with interrupts masked); 2.2 on SS-10, 2.3 and 2.4 on SS-5 install and boot in the lab (CD as a disk), 2.1 stops in QEMU (`Trap 0x21`: its kernel flushes a new context before it has filled its level 1 table; pve-qemu `wsh/0047`, with the qtest `wsh/0048`, lets it install and boot in the lab, `upstream/qemu-sparc32-context-switch-ifetch.md`; target `sol21-ss10` since 11.1.3-2+wsh29, below); SunOS 4.1.3's `type=29` diagnosed (a probe of `0xd.0108_0000`); openbios 0023 (client interface: no catch result over the stack with `nret` 0) lets OpenBSD 8.0's installed sun4u kernel boot | merged | #334 |
| Install targets: Solaris 8 and 9 on the SS-5 (`sol8-ss5` from 8 2/02, `sol9-ss5` from 9 9/05, 256 MB, Web Start through PVE); Web Start's screens of the later updates answered (9 9/05's license question, 8 2/02's CD prompts); 8 2/02 and 9 9/05 on sun4u measured: they stop at the same `pp is NULL or free` panic as 8 1/01 and 9 (OpenBIOS's physical allocation, `submodules/SPARC.md`) | merged | #342 |
| Solaris 7/8/9 on sun4u: OpenBIOS 0024 lists `/memory` `available` in whole pages, which ends `boot_alloc: pp is NULL or free` (claims recorded to the byte left entries starting inside a page; Solaris 7-9 counted them one page short and a later boot allocation got the missing page). 7, 8 1/01, 8 2/02, 9, 9 9/05 reach the installer with 1 and 2 GB; 8 2/02 and 9 9/05 install and boot to `console login:` in the lab (1 GB); upstream note | merged | #346 |
| Install targets under OpenBIOS with pve-qemu-kvm 11.1.3-2+wsh22: `sol23-ss5`, `sol23-ss20`, `sol24-ss5` move from the Sun PROMs to OpenBIOS, new `sol24-ss20` and `sol22-ss10` (Solaris 2.2 on SS-10), each installed twice through PVE (~8-10 min); 2.3 and 2.4 on the SS-20 with 2 and 4 CPUs (10 min of load on 4, idle ~5% of a host core); OpenBSD 8.0 on sun4u (`openbsd80-sun4u`, openbios 0023): the installer answered by what it asks, ntpd off, ~19 min | merged | #341 |
| Install targets: OpenBSD 5.9, the last release for 32-bit sparc, on SS-5 and SS-20 (`openbsd59-ss5`, `openbsd59-ss20`, OpenBIOS, ~10 min): `cd59.iso` boots the installer, the sets come from a CD `lab.py media --convert` makes on the node from the release's files (Rock Ridge names, `answer_media.openbsd_sets`), the installer checks them against `SHA256.sig`; needs a serial display (with QEMU's keyboard ESCC the kernel panics, "crazy interrupts") | merged | #343 |
| Install targets: NetBSD 9.3 on sun4u, SS-5 and SS-20 (`netbsd93-sparc64`, `netbsd93-sparc`, `netbsd93-sparc-ss20`) with the 11.1 targets' profiles and sysinst answers; 9.3's sysinst goes from the sets straight to its configuration menu (no root password prompt, no entropy question), handled in `_netbsd.sysinst` with tests for both releases; installed through PVE with `--check --export` and boot-tested from the stored disks (sun4u 18 min, SS-5 7, SS-20 6; boot tests 1.2-1.5 min) | merged | #353 |
| Install targets: Solaris 9 9/05 and 8 2/02 on sun4u (`sol9-sun4u`, `sol8-sun4u`, End User 64-bit, Web Start through PVE); OpenBIOS 0025 leaves out the ebus floppy node (a zero-sized `reg` for hardware QEMU's sun4u doesn't have; Solaris 9's first boot panicked in `fd`); the reboot that returns on sun4u is handled by the tool: the VM is stopped at `0 >` after the install, and 8's reboot into its mini-root is a power cycle through PVE (`PveMachine.power_cycle()`) | merged | #350 |
| Mirror storage, steps 1 and 2 of 3: ISO and floppy images on a NAS as symlinks in a `dir` storage, the folders in the link name with `__` (`Solaris__2.6__solaris_2.6_598_sparc.iso`). `wsh-lab mirror link`/`sync [--prune]`/`list` makes and checks the links (no backend change: PVE's listing follows symlinks); pve-manager groups the storage's ISO and floppy tabs by folder and shows `Solaris / 2.6 / ...` in the ISO and floppy selectors (volume IDs unchanged); `wsh-lab media`/`install` also find a medium by size and sha256 under another name. Step 3 is under "Later" | merged | #345 |
| Mirror storage, step 2b: four ways to use it (plain `__` names in any ISO/floppy storage; a local storage of links; ISOs and links on one NFS/CephFS export with relative links; an externally managed tree stitched into one) as recipes in `reference/mirror.md`; a description file `wsh-mirror.yaml` (watch directories, rules, entries with `origin: manual|import`, `auto_import`, incomplete-file patterns and a minimum age) with `wsh-lab mirror init|plan|apply|import|tidy` (flock, moves found by size and sha256, a manual entry's link only flagged, nothing removed while a share is unreachable) and `mirror timer` (a systemd timer that runs `apply`); mirror storages may be dir, btrfs, nfs, cephfs or cifs. A search field above the ISO and floppy selectors (CD/DVD and floppy editors, the wizard's OS tab): focused on open, every word must be in the name, Enter picks the first match. e2e: an NFS export from NFS-Ganesha in the compose network | merged | #349 |
| Install targets for the matrix holes: Solaris 2.5.1 on the SS-20 under OpenBIOS (`sol251-ss20`, the CD as a disk; the SS-5 target still needs `ss5.bin`), Solaris 2.6 and 7 on the SS-10 (`sol26-ss10`, `sol7-ss10`), each installed through PVE with `--check --export` (stored disk and sidecar in `/mnt/os/disks`) and boot-tested, pve-qemu-kvm 11.1.3-2+wsh25 | merged | #355 |
| Install target `sol8-ss5-prom`: Solaris 8 2/02 (Entire Group, Web Start, three CDs) on the SS-5 under the Sun PROM `ss5.bin`, no `args`: the PROM boots the mini-root from Web Start's boot string by itself and stops at `ok` after the install, where the tool stops the VM; installed through PVE with `--check --export` (47 min) and boot-tested from the stored disk (2.2 min), pve-qemu-kvm 11.1.3-2+wsh26 | merged | #363 |
| Install target `sol7-sun4u`: Solaris 7 3/99 End User on sun4u with suninstall (`solaris-install-serial.py`: the disk as `DISK=c0t0d0`, `halt` to `0 >` and the VM stopped there), the SUN2.9G label on the IDE disk, 2048 MB (with 1024 the kernel panicked twice as the package copy began: `segkp_badop`, a BAD TRAP in `pkginstall`; not diagnosed), F2 sent again after 180 s on an unchanged screen (`KEY_RETRY`; two runs sat on a screen after F2); installed through PVE with `--check --export` (24.5 min) and boot-tested from the stored disk (4.4 min), pve-qemu-kvm 11.1.3-2+wsh26 | merged | #363 |
| BEL on a sparc32 framebuffer console hung Solaris 2.x and SunOS 4.1.4 with the screen inverted (bash's completion bell): OpenBIOS 0026 bounds the blink's wait (the firmware's tick counter stops once the client has its own trap table), and drops the cell each BEL left on the Forth stack; the lab's `fb-bell.py`, an upstream note, a workaround in the guide for packages without it | merged | #354 |
| Mirror storage, step 3: libpve-storage-perl renames an `iso`/`floppy` volume in place (`PUT .../content/{volume}` with `rename`; a link is renamed, never its target) and links a volume of another storage in (`POST .../storage/{storage}/link-volume`; relative on one file system inside its mount, absolute otherwise). Both refuse a name that exists, a `/`, unsafe characters and an extension of the other content type; they need `Datastore.Allocate` on the storage, the link also on the source storage (a link republishes the source to everyone who may use the mirror); a storage with a description file is refused (its next `apply` would undo the change), and a link in a shared storage to a volume not every node has. A dangling link is listed with size 0 and `unavailable: 1` instead of hidden. pve-manager: Rename (folder, file name, the new volume ID, the VMs that use it) and Add link from storage (the CD editor's search-field selector) in the ISO and floppy tabs, shown only where allowed; unavailable links flagged in the tabs and left out of the selectors. Unit tests (`media_volume_test.pm`) and e2e (API, UI, permissions, description file, NFS) | merged | #356 |
| qemu-server `audio0: driver=wav`, for tests and recordings: QEMU's file recorder writes `/var/run/qemu-server/<vmid>-audio0.wav` (a fixed path, `server=` refused with it) for every device, `cs4231` included; not in the UI's list. `server=` is described as the PulseAudio server and its messages no longer print into `qm showcmd`. The audio matrix (#359) records through it with a real `qm start` instead of rewriting the showcmd line | merged | #362 |
| Idle on sun4u: no guest on QEMU's sun4u has a way to stop the CPU (Solaris/illumos halt only through the SPARC64-VI module, NetBSD and Linux only through the sun4v hypervisor, OpenBSD's `sleep` only on CPUs with several strands), so pve-qemu `wsh/0042`-`0044` recognise the idle loops of NetBSD 9.3/11.1, OpenBSD 8.0, Solaris 9/10 and Tribblix m34 in the translator and halt there (`idle-halt`, on by default; qtest `sun4u-idle-test`): an idle guest at the shell takes 3-9% of a host core instead of 100% (Tribblix about 22%, and only with FMA's `fmd` off: its ZFS disk faults and `rcm_daemon` spins), with the clock, ten `sleep 1` and CPU-bound jobs as before (`submodules/SPARC.md`, "sparc64 (sun4u)", "Idle") | merged | #364 |
| Workflow tokens: `sync-from-upstream-trigger.yml` dispatches the five syncs with `GITHUB_TOKEN` (`actions: write`), and from a branch or with `dry_run` only says what it would start; `build-deb.yml` builds pve-qemu's 3dfx extra in its own job without `WORKFLOW_TOKEN` or stored credentials and hands the binary to the build job as an artifact; the optional-extras report's issue path is tested by `scripts/test-report-qemu-extras.sh` and dry-run against the open issues by `report-qemu-extras-test.yml` | merged | #360 |
| Install target `sol21-ss10`: Solaris 2.1 End User on the SS-10 (OpenBIOS, one CPU, the CD as a disk), automated now that pve-qemu-kvm 11.1.3-2+wsh29 and later have `wsh/0047` (the sparc32 context-switch fetch); installed three times through PVE with `--check` on the published 11.1.3-2+wsh30, qemu-server 9.2.19+wsh4, pve-manager 9.2.32+wsh4 (3/3 passed, 9.7-10.1 min with three at once: install 5.3 min, first boot 2.9-3.3, check 1.2-1.3), and twice on 11.1.3-3+wsh6, qemu-server 9.2.20+wsh3, pve-manager 9.2.32+wsh6 (2/2 passed, 11.2-11.7 min on a busy host; the gallery's recordings are from this run); `/opt` and `/export/home` still not mounted at boot | merged | #378 |
| OpenBSD 8.0 on sun4u with ntpd on: the IDE timeouts (`wd0: timeout`, then a guest that takes no interrupt) were a lost interrupt in QEMU's sabre (a PCI interrupt replaced the outstanding IDE request), fixed by pve-qemu `wsh/0045` (qtest `wsh/0046`, pve-qemu-kvm 11.1.3-2+wsh30); `openbsd80-sun4u` keeps ntpd on and checks it runs, no install retry (the stuck detection stays): 4 of 4 installs through PVE with `--check` (two with a way out, ntpd synced), 3 of 3 boots under disk load with ntpd slewing, no IDE timeout, ~17 min; the installer's "Exit to (S)hell" after "CONGRATULATIONS!" is answered again (broken by the OpenBSD 5.9 targets); again on pve-qemu-kvm 11.1.3-3+wsh6 (2026-11-21): 3 of 3 installs, a boot-test of the stored disk, ntpd synced within 5 minutes with a 0.18 ppm frequency correction (timecounter `tick`), no IDE timeout | merged | #391 |
| SunOS 4.1.3 on the SS-10: a bus error on a SuperSPARC load or instruction fetch takes the data or instruction access exception (trap 0x09/0x01, SFSR FT=5) instead of the access error (0x29/0x21), pve-qemu `wsh/0049` (CPU feature `buserr-access-exc` on the `TI-SuperSparc-*` models only; stores, the MMU bypass ASIs and the microSPARC unchanged), qtest `wsh/0050`; 4.1.3's kernel panicked in its VME probe (`BAD TRAP: type=29`). In the lab the 4.1.3 CD installs, boots and passes the check with the 4.1.4 scenarios (4 passes of 4, ~4.5 min each), stored SS-10/SS-20 and SS-5 disks boot as before (34 of 34: 18 on SS-10/SS-20, Solaris 2.6 also with 4 CPUs, and 16 on the SS-5); reproduced on plain QEMU 11.1.3. Target `sunos413-ss10` since 11.1.3-2+wsh31 (below), `upstream/qemu-sparc32-supersparc-bus-error-trap.md` | merged | #392 |
| Install target `sunos413-ss10`: the original SunOS 4.1.3 Programmer install on the SS-10 (OpenBIOS, one CPU, the 4.1.4 scenarios unchanged), automated now that pve-qemu-kvm 11.1.3-2+wsh31 and later have `wsh/0049` (the SuperSPARC bus error trap); installed six times through PVE with `--check` on the published 11.1.3-2+wsh31, qemu-server 9.2.19+wsh4, pve-manager 9.2.32+wsh4 (5/6 passed, 5.9-6.1 min: install 2.2-2.4 min, first boot 2.5, check 0.9; 10.5 min on a busy host; one stopped on a console message from a second guest with the same static address, a test setup fault) | merged | #395 |
| The Incredible Machine 1 and 2 (DOS) black on std and cirrus (every VGA model has the code): a read of the attribute address register (3C0h) returned 0 in the flip-flop's data state, the games restore what they read there after loading the palette, which clears the palette address source bit. pve-qemu `wsh/0051` returns the address in both states in `vga.c` and `cirrus_vga.c` (as the VGA and DOSBox do; 3C1h and the flip-flop unchanged), qtest `wsh/0052` (std, isa-vga, cirrus, vmware: 8 cases, all fail on plain QEMU 11.1.3). In the lab (11.1.3 with wsh/0001-0052, MS-DOS 6.22 with the owner's games) both games show their screens on std and cirrus (black without the patch; reproduced on plain 11.1.3 with the games, a 512-byte boot sector and the qtest); Doom, Doom II, Duke Nukem 3D, Wolfenstein 3D (`retrace=precise`), Keen 1 and 4, Larry 1, Dune and Dune II end on the same screen as without the patch (the same screendump, or the same running demo); the stored `msdos622` and `freedos14` disks pass their checks on std and cirrus; qtest-sparc unchanged. `upstream/qemu-vga-ar-index-read.md` | merged | #397 |
| SPARCstation LX boot PROM (`lx.bin`, lab only): its POST stopped at `FPU SP Trap Priority <` because QEMU raised fp_exception on the excepting FPop; the sparc32 FPUs defer it to the next FP instruction, and a misaligned FP store after it takes its alignment trap first. pve-qemu `wsh/0053` models fp_exception_pending for IEEE 754 exceptions on every sparc32 CPU (system emulation; linux-user and sparc64 unchanged; V8 manual 7.3 and appendix L, the microSPARC and SuperSPARC manuals), qtest `wsh/0054` (36 cases on SS-5, SS-10 and LX; the 27 trap cases fail on plain QEMU 11.1.3), and `wsh/0055` caps the microSPARC-I machines (LX, SPARCClassic, SPARCbook) at the chip's 128 MB (OpenBIOS stopped with `Trap 0x21` at 256). In the lab the LX PROM passes all its FPU tests and reaches `ok` (still missing: stubs for its built-in SBus devices, then SunOS); Solaris 2.6 on SS-20 and SS-5 gets SIGFPE (`FPE_FLTDIV`, `si_addr` at the `fdivs`) 504 of 504 times and keeps running; 34 of 34 stored sparc32 disks boot and pass their checks as before (SS-5, SS-10, SS-20, Solaris 2.6 also with 4 CPUs); reproduced on plain QEMU 11.1.3. `upstream/qemu-sparc32-deferred-fp-exception.md` | merged | #399 |
| SPARCstation LX with its own PROM (`lx.bin`, lab only) boots to a login prompt over ttya (`-nographic`): the PROM probes its on-board cgsix (slot 3), DBRI (slot 2) and bpp (slot 4) on every boot and stopped at `ok` on the first bus error. pve-qemu `wsh/0056` maps the three as unimplemented devices on `-M LX` (below a `-vga` frame buffer), `wsh/0057` answers the DBRI's FCode PROM window with an FCode program of ours that makes the node a DBRI has (name, `reg`, interrupt; SunOS 4.1.4 panicked on the node without it, as Solaris 2.1/2.2 do on the SS-20 PROM), qtest `wsh/0058`. In the lab: Solaris 2.6 installs from CD and boots (64 and 128 MB), NetBSD 9.3's stored disk boots (64, 128 MB), SunOS 4.1.4 and 4.1.3_U1B install and boot; the drivers find no codec behind the DBRI stub, the cgsix node stays unused; the Solaris 2.2 CD reaches its installer under the SS-20 PROM without the lab's node naming; 12 of 12 stored sparc32 disks boot as before, OpenBIOS on `-M LX` as before; qtest-sparc/sparc64 46 OK. `upstream/qemu-sun4m-lx-onboard-sbus.md`, `upstream/qemu-sun4m-ss20-dbri-unnamed-node.md` | merged | #405 |
| SPARCstation LX in PVE: `machine: LX` with `bios: lx.bin` as a sparc32 profile in qemu-server and pve-manager (at most 128 MB, one CPU, `vga: serial0` by default or `none`, no OpenBIOS, no audio), cfg2cmd tests `sparc32-lx-*`, e2e in `sparc-profiles.spec.ts` (skipped against packages without the profile; QEMU started only where the node has `lx.bin`). In the lab's PVE container `qm start` boots the Solaris 2.6 LX disk to its login prompt (`boot disk` at `ok`). `lx.bin` goes into `pve-qemu-kvm` with the other Sun PROMs (`sun-proms` extra) (`submodules/SPARC.md`, "SPARCstation LX with its own PROM") | merged | #408 |
| DOS games: `vga: ...,retrace=precise` in qemu-server and the UI (Hardware > Display, "VGA retrace: Precise (DOS games)"; x86 with a display on QEMU's VGA core: std, cirrus, vmware, qxl, virtio). QEMU takes its precise VGA retrace emulation only as a `-vga` option (no device property), so qemu-server adds `-vga none,retrace=precise` next to the `-device`; refused with `none`, `serial*`, `tcx`, `cg3` and off x86 at create, update and start. Wolfenstein 3D waits for display enable without vertical retrace on port 3DAh, which QEMU's default `dumb` emulation never reports: through PVE (TCG, the owner's MS-DOS 6.22 disks, the local qemu-server) it stays black in mode 13h for a minute with `vga: std` and shows its title and menu screens with `std,retrace=precise` (12 distinct screens in 60 s against 2). cfg2cmd tests, e2e (API, `qm showcmd`, QEMU accepts it, refusals, the UI field) with `test.fail` probes until a package has it | merged | #394 |
| DOS memory profiles as data (`e2e/sparc/dos_profiles.py`, `scenarios/dos-profile.py`): Full (XMS + UMB, no EMS), EMS (frame at D800, set explicitly), Maximum conventional, No EMM386 and the disk's own files, for MS-DOS 6.22 and FreeDOS 1.4, also as one startup-menu `CONFIG.SYS`. Each profile is written onto a sparse copy of an installed disk with mtools (now in the lab image) and booted in the lab's QEMU; measured with `MEM` and four hand-assembled programs of ours (`dos_tools.py`: `EMSCHK` pages and frame, `VGARTRC` display enable on 3DAh, `VGAAR` the 3C0h data-state read, `SNDCHK` SB DSP + AdLib + PC speaker into the WAV), the screen and QEMU's guest-error log, and optionally a game per run (frames, last change, sound). CI: `tests/test_dos_profiles.py` in `sparc-lab-dos.yml` on the FreeDOS disk the job just installed (five profiles, the menu, plain `std` where VGARTRC must time out). VGAAR fails under pve-qemu-kvm 11.1.3-2+wsh16 and passes on 11.1.3-3+wsh2. Lab run on 11.1.3-3+wsh2 with the owner's MS-DOS 6.22 disks: the five profiles and a game matrix per profile; recommended profiles and results in the DOS guide ("Memory profiles") | merged | #403 |
| DOS memory profiles, follow-up: the MS-DOS EMS profile gives EMM386 `RAM` without a size, so its EMS and VCPI pool is all free XMS (`RAM 4096` capped VCPI at 4 MB and Duke Nukem 3D, DOS/4GW, stopped for lack of memory); with it one boot runs all nine games of the matrix (Wolfenstein 3D with `retrace=precise`). A profile can bring its own `SHELL` line (also in a startup-menu block); MS-DOS 6.22's `MEM` line for a large EMS pool (no K, no closing parenthesis) is parsed. Wolfenstein 3D's black screen on plain `std` pinned down in the lab: its CRTC routine waits for several reads of "blanked, not in vertical retrace" on 3DAh, which `dumb` never gives (bits 0 and 3 flip together), and its timer-based timeout can't fire because the counter isn't running yet (sampled under TCG and KVM); no `CONFIG.SYS` changes it. DOS guide and display reference updated | merged | #409 |
| 3dfx in a real Windows 98 SE guest (`e2e/3dfx/win98-test.sh`, workflow `3dfx in Windows 98`, by hand and weekly on the lab runner): the operator's own installed disk (never in the repository; path from an input or `WSH_WIN98_TEMPLATE`) is copied, the binary's `qemu-3dfx-drivers` release and our own test programs (mingw-w64, no C runtime: `glidetst.exe` for Glide 2 and 3, `gltest.exe` for OpenGL, `w3drun.exe` in StartUp, which powers Windows off) are written onto the copy with mtools, QEMU gets PVE's device set at PVE's PCI addresses (no new-hardware wizard); the programs report on COM1, the harness checks the frame in the console's screendump and the desktop after it; screendumps stay on the runner, the artifact has only logs and probe values. Published 11.1.3-3+wsh5: Glide 2 and 3 pass headless (KVM and TCG), OpenGL ends QEMU (SIGSEGV on loading `OPENGL32.DLL`); a binary from #407: all three pass (KVM 50-70 s a run, TCG 83 s; 1400-1700 Glide and 1900-2500 OpenGL frames/s). Found: the release's guest drivers need SSE2-SSE4.2/POPCNT, so `cpu: pentium3` without KVM faults ("illegal operation"); booting at the host's time can stop Windows 98 at a daylight-saving dialog | merged | #410 |
| 3dfx guest drivers for a Pentium-class guest: `submodules/qemu-3dfx-drivers.patch` builds every compiled part with `-march=pentium` (MinGW DLLs/EXEs and the DJGPP DXEs) or `-5s` (Watcom OVL) instead of upstream's `-march=x86-64-v2`; `scripts/check-3dfx-drivers-isa.sh` disassembles the result in `make 3dfx-drivers` and fails on MMX/SSE or later (CMOV from Debian's i686 MinGW runtime is allowed); `VERSION.txt` says "built for i586" and the Windows 98 harness's `--cpu auto` adds the SSE extensions under TCG only for older zips. Windows 98 test with published 11.1.3-3+wsh6: Glide 2, Glide 3 and OpenGL pass with `cpu: pentium3` under TCG and KVM. Also: the 3dfx binary's `--version` always said `+wsh1`, as `make pve-qemu-3dfx` versioned a fresh pve-qemu without `submodules/pve-qemu.changelog.patch`; it now applies it before `dch` like the pve-qemu target, and `build-deb.yml` warns when the banner and the package version differ (a build that waited in the queue) | merged | #415 |
| wisp, the tiny test system, tier 1 (`e2e/wisp/`, guide "wisp"): a kernel (Linux 7.3.4 from Debian's `linux-source-7.3`, `tinyconfig` plus a fragment per architecture, uniprocessor) with a built-in initramfs whose only file is a static PID 1 built with the kernel's nolibc (no C library; sparc32 as V8 with `-m32 -mcpu=v8`), for x86_64 and i386 (`pc`), sparc32 (`SS-5`, `SS-20`, `SS-10`, `SS-4`, `SPARCClassic`, `SPARCbook`, `LX`, `Voyager`) and sparc64 (`sun4u`). It boots with `-kernel` on the serial console, prints a banner, `uname`, CPU count, memory, a compute loop (xorshift32 + CRC-32, the same checksum on every architecture) with its time and one result line, and powers off; `run.py` (stdlib, unit tests) boots it under a given QEMU and reports times to PID 1 and power-off, loop time and peak RSS; `qemu-tci.sh` builds a TCI QEMU. Kernels 1.1-1.3 MB (x86 bzImage) and 2.4/3.1 MB (sparc32/sparc64 ELF), PID 1 5-13 KB. Lab, load 4-6 on 14 threads, two passes, all 24 runs pass: to power-off 1.6-3.2 s under TCG (published 11.1.3-3+wsh6), 22-28 s under TCI; the loop 15-21 times slower under TCI, and 9-15 s of a TCI boot pass before the kernel's first line (firmware, plus XZ decompression on x86). `-M LX` (and `-M Voyager`) with OpenBIOS stopped Linux 7.3 at its first idle: OpenBIOS gave them the SS-5's APC node, which QEMU (and a real LX) doesn't have there, Linux's `apc_swift_idle()` took a data access error on it and the nested faults overwrote the kernel text (`Trap 0x07` in `tsetup_patch2`); OpenBIOS patch 0027 makes the APC node only on the SS-5, SS-4, SPARCClassic and SPARCbook, and the LX and the Voyager pass (`e2e/wisp/README.md`, "The LX and the Voyager"). CI: `wisp-boot.yml` boots the eleven machines (the four architectures, then sparc32 on the seven other machines; the LX and the Voyager since the published 11.1.3-3+wsh9 carries OpenBIOS patch 0027, verified on the lab with the package's QEMU and with QEMU built from the tree: 15 boots in 36 s, all pass) on a GitHub-hosted runner for pull requests that touch `e2e/wisp/`, `pve-qemu.patch` or the pve-qemu pin (for the latter two with qemu-system-{x86_64,i386,sparc,sparc64} built from the pull request's patched tree), and on main with the published package; kernels cached, `wisp-boot-required` gate | merged | #417, #422, #427 |
| wisp interactive mode (`e2e/wisp/`, README "Interactive mode"): `wisp=shell` on the kernel command line starts a small shell in PID 1 on the serial console instead of the batch run (the default is unchanged): `help`, `info`/`uname`, `bench`, `crc <n>`, `mandel` (ASCII Mandelbrot, 78 x 20, 4.12 fixed point in 32-bit integers), `banner`, `clear`, `poweroff`, `reboot` (not on sun4u, where OpenBIOS doesn't restart). Canonical TTY mode: the line discipline does the echo and Backspace, Ctrl-U, Ctrl-W, Ctrl-C; an 80 x 24 layout with a few ANSI colours, for the Browser SPARC demo. `run.py --shell` drives it over the console on all four architectures and checks every answer (Mandelbrot character by character against a Python model and `tests/mandel.txt`); unit tests also build `init.c` against the host's glibc and drive it there; CI runs `--shell` after the batch boots. PID 1 grows by about 3.5 KB on sparc (5.2 to 8.7 KB sparc32, 5.4 to 8.9 KB sparc64) and 4 KB on x86. Found on the way: nolibc's sparc `_start` gets a `save` prologue from gcc and read `argc`/`envp` 96 bytes too low, so `loops=` never reached PID 1 on sparc; `init.c` now has its own `_start` there (an upstream nolibc fix candidate) | merged | #428 |
| wisp tier 2: disk, network, SMP (`e2e/wisp/`, README "Tier 2"): a second kernel per architecture, `kernel-t2` (`config/tier2/`), with the block layer, devtmpfs, each machine's disk and NIC drivers, packet sockets and SMP where QEMU's machine has more than one CPU; the tier-1 kernel and its output are unchanged. `run.py --tier2` boots every machine once per profile: a 4 MiB raw image per disk controller (pc: PIIX3 IDE and virtio-blk; sun4m: ESP SCSI; sun4u: cmd646 IDE and virtio-blk on its PCI bus), PID 1 reads and checks it, writes 1 MiB, syncs, drops the page cache and reads it back, and run.py checks the image afterwards; a NIC on QEMU's user-mode network (pc: e1000 and virtio-net; sun4m: lance; sun4u: hme) with ARP and 8 ICMP echoes of 1,400 bytes to slirp's 10.0.2.2, frames built by PID 1 on a packet socket (no IP stack in the kernel: 385 KB less on sparc32; no host network or DNS involved); the compute loop on every CPU with `sched_setaffinity` on pc and on the SS-10 and SS-20 (`-smp 2` and `4`; the sparc32 SMP kernel drops futex, which wisp doesn't use, and boots the uniprocessor sun4m machines too; sun4u has one CPU in QEMU). The shell has `disk`, `net` and `smp` (`run.py --shell --tier2`). `kernel-t2` is 0.55 MB larger on x86 (bzImage), 0.86 MB on sparc32 and 1.0 MB on sparc64 (ELF); PID 1 has 6.6-8.3 KB more code. Lab: all 32 tier-2 boots (21 batch, 11 shell) pass with the published 11.1.3-3+wsh9 and with QEMU built from the tree, and tier 1 still passes; `run.py` fixes the sparc32 delay-loop calibration (`lpj=`), which a descheduled QEMU could leave at 8191 so that the second CPU was given up as stuck. CI runs tier 2 after the shell boots | merged | #433 |
| Sun PROMs' NVRAM kept across starts: pve-qemu `wsh/0059` gives the sun4m M48T08 a `drive` (written through per byte; a blank image gets QEMU's contents once, any other is left alone except the IDPROM from `-M` and the MAC, and OpenBIOS's partitions when `-prom-env` is given), qtest `wsh/0060`; qemu-server `nvram0` (sparc32 only, 4 MiB like the TPM state, `-blockdev` + `-global sysbus-m48t08.drive`, in backup/restore/clone/move like a disk; cfg2cmd and hotplug tests) and Hardware → Add → NVRAM in pve-manager (no wizard default). In PVE (lab): after one `setenv diag-switch? false` the LX PROM (Solaris 2.6) and the SS-5 PROM (Solaris 8) boot to `login:` on every start without input, also a clone with a new MAC; OpenBIOS SS-5/SS-20 with and without the volume as before; qtest-sparc 28 OK. The SS-20 PROM's own auto-boot stopped QEMU in Solaris 2.6 (`Trap 0x29`, also without the volume): fixed by `wsh/0061`, next row. `submodules/SPARC.md`, "The NVRAM kept in a volume"; sparc guide, "Making a Sun PROM VM boot by itself"; `upstream/qemu-sun4m-nvram-backend.md` | merged | #418 |
| SS-20 PROM boots Solaris 2.6 by itself: the ledma's upper-address register (`E_BASE_ADDR`, the top 8 bits of the lance's 24-bit DVMA addresses) reset to 0 in QEMU; the DMA2 description says it defaults to `0xff`. Solaris 2.6's `le` never writes it and the SS-20 PROM sets it only when it probes with `diag-switch?` true, so with `diag-switch?` false (auto-boot, or a typed `boot disk` after such a start) the lance read its init block from `0x0040f000` instead of `0xff40f000`, the 64 MB IOMMU faulted at level 15 and the kernel recursed in its level-15 handler until QEMU stopped (`Trap 0x29`). pve-qemu `wsh/0061` resets it to `0xff000000` (ledma only), qtest `wsh/0062` `sun4m-ledma-test` (fails without 0061). Lab, plain QEMU 0001-0062: the stored `sol26-ss20` disk on the SS-20 PROM with an NVRAM image boots to `login:` by itself on three starts in a row; OpenBIOS SS-20, the SS-5 PROM (Solaris 8) and the LX PROM (Solaris 2.6) as before; qtest-sparc 29 OK. Through PVE: the "SS-20 PROM through PVE" row. `submodules/SPARC.md`, "SS-20 PROM: auto-boot and the lance DMA" | merged | #424 |
| sparc: no EFI Disk or TPM State. pve-manager hides both in Hardware → Add for sparc32 and sparc64 (as NVRAM is shown for sparc32 only) and the wizard's Add TPM (OVMF was already not offered); qemu-server refuses `efidisk0`/`tpmstate0` on sparc32 at create, update and start (a `tpmstate0` was taken and the start then failed: `qemu-system-sparc` has no `tpm-tis`; sparc64 already refused both). `qm showcmd` prints only the command again: two debug prints are gone (`-- Using <display> display ...` for a `vga` with `server=`, and `sparc/sparc64 does not support PCI devices, ignoring: ...` on every sparc VM); the cfg2cmd runner gets `EXPECT_NO_STDOUT`. cfg2cmd tests, e2e with `test.fail` probes until the packages have it | merged | #421 |
| SunOS 4.1.2 on the SPARCserver 600MP (lab only, one CPU): installs and boots under OpenBIOS. Its kernel sets up the 600MP's VMEbus interface registers (`0xf.df01_0000`, MMU bypass) before its banner, where QEMU had nothing (`Unhandled Exception 0x00000029`): pve-qemu `wsh/0063` maps them as an unimplemented device. It finds the disk only under a DMA node named `dma` and the lance only under an `lebuffer`, the 600MP's buffer memory the lance works in: `wsh/0064` gives the SS-600MP's lance 128 KB of its own at slot f `0x40000` (no ledma, no DVMA), openbios 0028 names the nodes `dma` and `lebuffer` on machine ID 66; qtest `wsh/0065`. The 4.1.4 scenarios install it (the ESP path by machine, `SERIAL_7BIT=1` for its getty's parity bit) and the installed system answers ping. Two CPUs: the kernel's start of CPU 1 checks the module ID in the MMU control register, which needs the Ross module (not modelled). Published in pve-qemu-kvm 11.1.3-3+wsh13 (`submodules/SPARC.md`, "Older Sun releases on sun4m"). New pve-qemu patches start at `wsh/0063` (#424 adds 0061-0062) | merged | #430 |
| SS-600MP profile in qemu-server and pve-manager, and `sunos412-ss600mp` an automated target: `machine: SS-600MP` with OpenBIOS only and one CPU (a Sun PROM or a second CPU is refused with the reason: the Ross RT625 module, which QEMU doesn't model, that Sun's 600MP PROM and 4.1.2's start of CPU 1 need), up to 1024 MB (4.1.2 booted with 256 MB to 2 GB through PVE; the wizard presets 256), the usual displays (OpenBIOS draws on cg3 and TCX), no `audio0` (no sound chip), `nvram0` as on the other OpenBIOS machines. pve-manager: SS-600MP in the sparc32 Machine choices, OpenBIOS picked with it, CPU fields disabled, `defaultMemory`. cfg2cmd and machine-version tests; e2e `sparc-profiles.spec.ts` ("the SPARCserver 600MP", skipped on packages without the profile). Through PVE with the published pve-qemu-kvm 11.1.3-3+wsh14: `lab.py install sunos412-ss600mp --check` passed twice (e2e/sparc/README.md, "Older Sun releases") | merged | #438 |
| OpenBIOS on the SPARCstation LX: NetBSD 9.3 boots. OpenBIOS gave every machine ID from 32 to 63 the SS-5's CS4231 node (`0x6c000000`), but QEMU has the codec only on the SS-5 and the SS-4 (the LX's audio is the DBRI in slot 2), and the stored `netbsd93-sparc` disk panicked on `-M LX` when `audiocs` attached (data fault at `0x6c000000`). openbios 0029 turns 0027's APC helper into a table of the slot-4 devices QEMU has per machine ID (codec and APC on the SS-5 and SS-4, APC only on the SPARCClassic and SPARCbook, neither on the Voyager and LX). Lab: the disk boots to `login:` on `-M LX`; on SS-5 and SS-4 NetBSD still attaches `audiocs0`, Solaris 2.6 on SS-5 its `audiocs`; wisp passes on all eight sparc32 machines (batch, shell, tier 2); `check-qtest-sparc` as before. The LX profile in PVE still takes `lx.bin` only | merged | #436 |
| `wsh-sun-proms` in the `wsh-lab` package: installs Sun boot PROM images you are entitled to use, from a source you provide (a directory, a tar or zip archive, a git repository with your own credentials, or an HTTPS URL; no default source), into `/usr/share/kvm` where qemu-server's sparc32 profiles and the UI find them; `install`, `status`, `verify`, `remove`, idempotent, mode 0644; each file checked against a committed manifest of names, sizes and SHA-256 (`packages/wsh-lab/sun-proms/manifest.json`, no images), unknown or differing files refused without `--force`; files a package owns are left to dpkg. `check-qemu-extras.sh` names the source of each PROM on a node (package, `wsh-sun-proms` or not recorded). Unit tests and fake PROMs only (`test_sun_proms.py`, `packages/wsh-lab/test.sh`, `scripts/test-check-qemu-extras.sh`). Whether the `pve-qemu-kvm` build keeps its optional `sun-proms` extra or leaves the PROMs to this tool alone is a later owner decision | merged | #437 |
| Browser SPARC, step 2: wisp's shell in the browser (`web/`, `docs/public/browser-sparc/`, guide "Browser SPARC"): `qemu-system-sparc -M SS-5` built for WebAssembly (wasm64, TCI) from Debian packages only: Emscripten 6.0.5 from sid, upstream QEMU 11.1.3 from Debian's source package plus all 65 `wsh/` patches (they apply to upstream with no fuzz), glib/pixman/libffi/pcre2/zlib from Debian source packages; OpenBIOS from the published package, wisp's tier-1 kernel, Debian's xterm.js. The console is a character device in Emscripten's file system behind `-chardev pipe`; COOP/COEP from the page's own service worker. A snapshot taken at the prompt by a native build of the same tree (`make-snapshot.py`, 4.8 MB) starts the page in 0.8 s; a boot from OpenBIOS takes 162-167 s in Chromium. `bench` 31-35 s (about 100x TCG, 5x native TCI), `mandel` matches `tests/mandel.txt`; the guest clock ran about 3x behind (fixed, next row). `browser-sparc.yml` (by hand) builds the files and can publish them as the `browser-sparc` release, which `repo-update.yml` copies into the Pages site | merged | #439 |
| Browser SPARC: the guest clock keeps to the wall clock (`web/patches/slavio-timer-missed-ticks.patch`, guide "Browser SPARC", "How fast"). It ran about 3x behind because ticks were lost: Linux on sun4m keeps time by counting the slavio system timer's 100 Hz interrupts, the timer is a ptimer run from QEMU's main loop, and in the browser that loop sleeps in a `poll()` whose timeout Emscripten runs as a `setTimeout()` on the page's main thread, so it wakes late whenever that thread is busy; the ptimer then runs the missed periods back to back and every match after the first found the interrupt still pending. The page-only patch counts those matches and raises the interrupt again each time the guest clears it (by reading the limit), capped at a minute of backlog, migrated in a subsection sent only when non-zero; `build-qemu.sh` applies `web/patches/*.patch` after the wsh series, to the wasm and the native (snapshot) build. Measured in headless Chromium: `mandel` (its output keeps the page busy) guest/wall 0.085 before, 0.955 after; `bench` 0.98-0.99 both (snapshot and `?cold`); with the page thread kept busy with 30 ms tasks: guest/wall 0.009-0.017 before, 0.999 after (Firefox 0.041, 1.001); idle 0.97-0.98 before, 1.000 after; natively with QEMU stopped by `SIGSTOP` 10 s out of 15: 0.322 before, 1.000 after (native, undisturbed: 1.000). Checks: `clock-check.py` (the `SIGSTOP` test, run by `web/Dockerfile` after the snapshot, fails the build below 0.95) and `browser-clock-check.mjs` (the page in the runner's headless Chrome, idle and busy, below 0.9), a step in `browser-sparc.yml`. The published assets need a rebuild with `publish` (the snapshot is regenerated by the same build) | merged | #445 |
| Browser SPARC, wisp's other machines (phase 1, serial shell): `/browser-sparc/?arch=` with `sparc64`, `x86_64` or `aarch64` next to the SS-5 (buttons above the terminal; the SS-5 stays the default and its page loads only its own files). `docs/public/browser-sparc/machines.json` holds each machine's QEMU options, firmware and kernel for the page and the snapshot scripts; `build-qemu.sh` builds `qemu-system-sparc`, `-sparc64` and `-x86_64` in one tree with their default devices and `-aarch64` in a second with QEMU's `minimal` device set (the virt board alone: 26.5 MB of WebAssembly instead of 52); wasm sizes 12.9 / 18.5 / 36.2 / 26.5 MB (gzip 4.8 / 6.8 / 8.3 / 8.3), snapshots 4.8 / 14.2 / 12.9 / 9.8 MB. Firmware: OpenBIOS sparc64 and SeaBIOS (`bios-256k.bin`, `linuxboot_dma.bin`, `kvmvapic.bin`) from the published `pve-qemu-kvm`; Arm virt boots `-kernel` with no firmware. Real work: sun4u snapshots resumed without interrupts (the serial console stayed silent) because the sabre host bridge had no VMState; `web/patches/sun4u-migration-state.patch` migrates its interrupt state and the CPU's SOFTINT and interrupt vector (generic, a candidate for pve-qemu `wsh/` and upstream); libfdt for Emscripten from Debian's dtc source (its meson build insists on a shared library, so the sources are compiled into a static archive, which also goes into Emscripten's sysroot because QEMU uses `find_library()`); QEMU's EDK2 blob unpacking switched off (Debian's `+ds` tarball has no blobs); the kernel stage needed `patch` since #488 (main's `web/Dockerfile` failed there). Just builds: the PC and Arm virt (migration, clock, console unchanged). Measured in headless Chromium 156: snapshot to prompt 1.6-2.2 s (3.8 s on Arm); cold boot 167 / 175 / 80 / 15 s (SS-5 / sun4u / PC / Arm); `bench` 47 / 36 / 39 / 37-44 s; `mandel` matches `tests/mandel.txt` on all four; guest/wall clock 0.95-1.00 idle and 0.99-1.00 with the page thread busy on all four (only the SS-5 needed its timer fix; the others read clocks derived from QEMU's virtual clock). `clock-check.py` runs for every machine in the build, `browser-check.mjs` (was `browser-clock-check.mjs`) checks `mandel` and the clock for every machine in `browser-sparc.yml`, `web/tests/` checks that the table, build and page agree. The published assets need a rebuild with `publish` | in review | |
| Reconfiguration boots under the SS-20 PROM: Solaris 2.6 panicked in `dbri` at `boot -r` (and the stored `sol26-enduser-ss20prom` disk's first boot; the SS-10 PROM too). The driver's first command read REG8, the command queue pointer, as 0 from the register stub, and its chip error routine walked 14 pipes of which the 12 ISDN ones are never set up when the PROM gives the node `isdn-disabled` (SS-20 and SS-10 PROMs; the LX PROM doesn't, which is why the LX ran on). pve-qemu `wsh/0066` models the DBRI's registers: they walk the command queue through the IOMMU to its WAIT and leave REG8 there, no data, no interrupt, PIO pins low, so the drivers find no codec without tripping; qtest `wsh/0067`. In the lab: `boot disk -r` to `login:` under the SS-20 and SS-10 PROMs, the stored disk through its first boot; ordinary boots, the LX PROM (Solaris 2.6, SunOS 4.1.4, NetBSD 9.3), `ss5.bin` and OpenBIOS SS-20 as before; `qtest-sparc` 31 OK. On older packages `exclude: drv/dbri` in `/etc/system` avoids it. `submodules/SPARC.md`, "The `dbri` panic on reconfiguration boots under the SS-20 PROM" | merged | #440 |
| sun4u firmware reboot: OpenBIOS 0030 makes the client interface `boot` service (Solaris's `reboot`/`init 6`/installer reboot, Linux's restart, the BSDs' `OF_boot`) reset the machine; 0012's hang was a level 6 soft interrupt Solaris left pending (QEMU keeps SOFTINT across a reset), then TICK.NPT left clear (the firmware's timer kept firing) and the old RAM contents (Solaris 9/10 panicked on the previous page structures): `entry` clears SOFTINT and the interrupt receive register, sets NPT, and the RAM below the firmware is cleared after any reset but the first. pve-qemu `wsh/0068`-`0069` clear the sabre's PCI control registers on reset (`SERR asserted` warning). Solaris 10, 9, 7, NetBSD 11.1, OpenBSD 8.0 reboot 3x to login; `install sol8-sun4u` through PVE without a power cycle; wisp's shell `reboot` on sun4u (refusal removed, `run.py --reboot`); scenario `sparc64-reboot.py`. `submodules/SPARC.md`, "The firmware reboot on sun4u" | merged | #441 |
| Idle on sun4u for more guests: Linux and Solaris 7/8. Linux's `arch_cpu_idle()` only touches the NMI watchdog on sun4u (no kernel option changes that), so pve-qemu `wsh/0070` recognises it at its call of `arch_touch_nmi_watchdog()` (the `tlb_type` test and the sun4v branch next to it, both ways gcc lays it out) and halts there at `%pil` 14, as the idle loop calls it with interrupts disabled (the tick and interrupt vector wake a halted CPU whatever `%pil`); `wsh/0071` the idle loop of Solaris 7 3/99 and 8 2/02 (Sun's older compiler lays it out the other way round from 9; not like 9's, as guessed); qtest `wsh/0072` (51 cases). Lab: the wisp kernel (7.3.4) and the Debian 12/13 installer kernels (6.1.27, 6.17.7, 7.0.12) at 5.3-6.0% of a host core instead of 100%, Solaris 7 and 8 at the shell at 2.5-3.0%, CPU-bound work, ten `sleep 1` and the clock as before; NetBSD 9.3/11.1, OpenBSD 8.0 and Solaris 9 still idle (2.5-4.3%), `sparc64` 10/10, `solaris10` 2/2, `qtest-sparc64` as before, the Solaris 7 and 8 disks boot-tested through PVE. New stored disk `install-sol8-sun4u.raw` (`lab.py install sol8-sun4u --check --export`, 52 min through PVE). `submodules/SPARC.md`, "sparc64 (sun4u)", "Idle" | merged | #442 |
| Debian 13 on sun4u: the debian-ports sparc64 netinst (2026-06-11, Linux 7.0.12) installs with the SSH server and boots through GRUB 2.14 to `login:` (DHCP, `poweroff`, `reboot`); install target `debian13-sun4u` (preseed from an answer CD on `ide3`, the options typed on GRUB's `linux` line, packages from deb.debian.org/debian-ports, `matrix_skip`: ~2.5 h). The Debian 12 `dpkg-deb` crash did not come back (two installs, 60 `dpkg-deb -x` afterwards). GRUB's "canonicalise devname failed" (2021 report) reproduced with OpenBIOS without our patches and is fixed by openbios 0009 + 0011 (OBP's `pci@1f,0` and the drives under the controller, the path grub-install keeps). Idle with `wsh/0070`: 6.5-6.9% of a host core. Through PVE with the published packages: `lab.py install debian13-sun4u --check --export` passed (177 min), the stored `install-debian13-sun4u.raw` boot-tests in 4.9 min; `matrix_skip` like Tribblix (out of the weekly and the monthly reinstall). `lab.py` now strips OSC strings (systemd 258's prompt). `submodules/SPARC.md`, "Debian 13 on sun4u" | merged | #468 |
| SS-20 PROM through PVE: `wsh/0061` (auto-boot) and `wsh/0066` (reconfiguration boot) checked on a PVE VM with the published pve-qemu-kvm 11.1.3-4+wsh2 (qemu-server 9.2.20+wsh7, pve-manager 9.2.32+wsh11): SS-20, `ss20_v2.25_rom`, 512 MB, `nvram0`, a copy of the stored `sol26-enduser-ss20prom` disk. One `setenv diag-switch? false` at the first `ok`, then the disk's pending first boot (a reconfiguration boot, no `dbri` panic; the root password, its only first-boot question, answered by the lab) to `login:` in 108-111 s; after `qm stop`/`qm start` the PROM boots Solaris 2.6 to `login:` by itself in 60 s (`le0` up, no `Trap 0x29`); `reboot -- -r` to `login:` in 66-76 s with the DBRI's `/devices` nodes made; three runs passed. New scenario `sun-prom-nvram.py`, case `sol26-ss20prom-nvram` in `pve_matrix.py pve` (weekly); e2e `sparc-profiles.spec.ts` checks the NVRAM persistence without media. No QEMU change; the SS-10 PROM has no PVE profile. `submodules/SPARC.md`, "The SS-20 PROM through PVE" | merged | #443 |
| wisp-test, a GitHub Action for big-endian testing (`.github/actions/wisp-test`, demo idea 2; `e2e/wisp/README.md`, "Test mode"): builds a C program against nolibc for sparc32 (V8, `SS-5`), sparc64 (`sun4u`) or x86_64 (the little-endian control), boots it as `/test` in wisp's tier-1 kernel under QEMU from Ubuntu's packages and passes or fails on its exit code or signal (outputs `result`, `exit-code`, `signal-name`, ...). wisp's PID 1 gains `wisp=test`: it runs `/test` from a second initramfs given with `-initrd`, with the arguments after `--`, and prints `WISP-TEST v=1 exit=N signal=N ms=N`. The kernels and the nolibc headers come as a 7 MB kit (`e2e/wisp/kit.sh`) from the `wisp-test-kit` release, which `wisp-test-action.yml` publishes when dispatched with `publish`; on pull requests it tests the action with the run's own kit: an endianness bug (exit code 1 on sparc) and an alignment bug (`SIGBUS` on sparc) that pass on x86_64, their fixes, and the arguments (`wisp-test-action-required` gate, not required). Lab, `ubuntu:24.04` with 2 CPUs: all 11 cases as expected, 1.6-2.6 s from starting QEMU to its exit, 2.3-3.5 s with the build, 12-32 s for a first run with `apt-get install`; also passes in `ubuntu:26.04`. Found: nolibc programs on sparc need PID 1's `_start` fix too; Ubuntu's 32-bit sparc libgcc and glibc are V8+, which the sparc32 kernel refuses, so no 64-bit division on sparc32 | merged | #447 |
| FreeBSD 12.4 on sun4u (the last release with sparc64; media from ftp-archive.freebsd.org, checksums checked): disc1 and bootonly boot to bsdinstall on ttya in 59 s, no interrupt storm (FreeBSD bug 239068's `vec2016`, the cmd646, doesn't recur); install target `freebsd124-sun4u` (`bsdinstall script` from the installer's shell, kernel and base, VTOC8 on `ada0`; first boot with static or DHCP on `hme0`; check with `vmstat -i`), 14.9 min through PVE with `--check --export` (the lab's QEMU and firmware mounted over the published package's; `matrix_skip` until a package has them). OpenBIOS 0032 (the MMU miss handlers no longer enable interrupts at TL 1: `shutdown -p now` spun there on FreeBSD's pending tick) and 0033 (the trap-state walk skips TL 0, where the fetch used the client's primary context: every FreeBSD reboot and `ofwdump` panicked); pve-qemu `wsh/0114` halts FreeBSD's idle loop (at TL 1, no 100 us poll) and qtest `wsh/0115` (70 cases with Linux 3.2's): idle 105-107% -> 8.7% of a host core, clock, `sleep 1` and CPU-bound work unchanged | merged | #456 |
| Debian 7.11 "wheezy" on sun4u, the first installed Linux disk on sparc64: lab target `debian7-sun4u` (the sparc64 profile, 512 MB, CD 1 on `ide2`, a preseed answer CD on `ide3` loaded by `preseed/early_command` from SILO's boot line, everything from CD 1: no network, no apt cache; the base system with SSH). SILO 1.4.14 boots the installed kernel and initrd under OpenBIOS unchanged; Linux 3.2 gets DHCP or a static address on `sunhme`, `poweroff` ends QEMU. pve-qemu `wsh/0110`-`0111`: Linux 3.2's `cpu_idle()` (at `%pil` 0) recognised, 100% to 0.1% of a host core at the shell. `wsh/0112`-`0113`: a TB flush on every sun4u reset after the power-on one, as OpenBIOS 0030's RAM clear crawled through pages full of Linux's translated blocks (a reboot took 5-6 minutes to the banner, now 2 s). Through PVE: `pve_matrix.py install` installed and exported it in 68.5 min with the published packages (pve-qemu-kvm 11.1.3-4+wsh4), and boot-tested the stored disk (175 s); stored as `install-debian7-sun4u.raw`. Ubuntu 9.04 server reaches its installer (not installed). Not fixed: Linux 3.2 under TCG retranslates constantly (install ~85 min), and a boot stall seen twice in 25 boots with the halt, in none of 10 without (`submodules/SPARC.md`, "Debian 7 on sun4u") | merged | #454 |
| 3dfx stage 2 through PVE: the Windows 98 harness gains `--pve CONTAINER` (`win98-test.sh`; `win98_test.py --pve VMID`): the harness runs in the e2e PVE container, `qm create` (`vga: std,mesa=1[,mesa-display=egl-headless]`, the disk copy through a directory storage of the run's own, COM1 and `-d plugin -D <log>` through `args`, which keeps a daemonized QEMU's standard error in the log) and `qm start`; the console is read through the VM's QMP socket (screendump) or PVE's VNC socket (VNC authentication, our own DES; the password set through QMP before each picture, since opening noVNC sets PVE's ticket). The template's device positions keep the new-hardware wizard away: machine version before 11.1 (11.1 adds bridge `pci.4`), `vmgenid: 0`, AC97 at 00:04.0 through `args` (qemu-server's `audio0` sits behind a bridge). Lab, published pve-qemu-kvm 11.1.3-4+wsh4, qemu-server 9.2.20+wsh7, wsh-openglide 0.5, KVM, `cpu: pentium3`, the i586 guest drivers of `qemu-3dfx-drivers-b94d988`, llvmpipe, `/dev/udmabuf`: egl-headless Glide 2 440-560, Glide 3 640-660, OpenGL 810 frames/s in two runs, every frame as a dmabuf (copies 0.08-0.09 ms Glide, 1.0-1.6 ms OpenGL); read back 1150, 1430 and 440; the scene in the noVNC console with egl-headless, 4 dmabufs open in QEMU. Also: the frame spec (`3dfx-gl-display.spec.ts`) runs in `e2e.yml`, which builds its guest before the suite (`pve-guest-setup.sh` with `PVE_GUEST_FETCH=1` for the submodule, ~40 s; `E2E_3DFX_GUEST=required` fails the spec when that setup failed); GitHub's runners have `/dev/udmabuf`; Proxmox's kernels have `CONFIG_UDMABUF=y`. Found: an older x86-64-v2 drivers zip faults under KVM with PVE's `cpu: pentium3` (`pinsrd`, SSE4.1; the release is i586 now); an OpenGL frame the guest doesn't redraw gives way to the VGA after ~4 s (also without PVE and read back) | merged | #450 |
| `sol10-sun4u` with `--ip dhcp`: the installer's DHCP screen answered yes (`/etc/dhcp.hme0`), the first boot keeps the host name in `/etc/nodename` and `inet <name>` in `/etc/hostname.hme0` (dhcpagent asks the server for it; Solaris 10 falls back to nodename), `--check` also needs the `DHCP` flag on `hme0`, the router from `dhcpinfo` and a ping of it. Through PVE (published pve-qemu-kvm 11.1.3-4+wsh4, with openbios 0030: the installer's reboot came back at the firmware banner), dnsmasq on the bridge in 10.0.2.0/24: passed in 119.8 min, `hme0` 10.0.2.25 by DHCP, `default 10.0.2.2`, `10.0.2.2 is alive`, host name `sol10-sun4u` (sent by the client and echoed by the server). `e2e/sparc/README.md`, "The Solaris 10 install target" | merged | #451 |
| Solaris 2.5.1/2.6 boot block on sun4u: their FCode boot block (UFS Reader 1.6/1.10) copies ufsboot's ELF segments into place itself, then evaluates `to load-base init-program` with `load-base` at the entry point and `?go`; OpenBIOS's `init-program` recognised nothing there and had no `?go` (`?go:`, `byte-load: exception caught!`). openbios 0031: `init-program` looked up by name takes unrecognised code at `load-base` as the program (as OBP), `?go` starts it. Both CDs are Ultra 5/10 media (their mini-roots have `SUNW,Ultra-5_10`, `uata`, `dad`, `atapicd`), so QEMU's machine class fits. With 0031 both kernels start and stop further on: 2.6 can't assemble the root drivers for the CD (`vfs_mountroot`), 2.5.1 traps before its banner on an unmapped page of its nucleus data (item 2 under "Next"). `submodules/SPARC.md`, "Solaris 2.5.1 and 2.6 on sun4u: the boot block" | merged | #451 |
| A libc toolchain for wisp (uClibc-ng via Buildroot, `e2e/wisp/toolchain/`): Buildroot 2025.02.20 SDKs build static programs on sparc32 (SPARC V8, `SS-5`) and x86_64 (no sparc64: this release's uClibc-ng Buildroot config omits `BR2_sparc64`, so sparc64 keeps the packaged static glibc route); published to GHCR and the `wisp-toolchain` release (SDK tarball and SHA-256). wisp-test's `libc: uclibc` input downloads that SDK (or a given tarball or URL) and links source builds against it without Docker | merged | #466, #467 |
| wisp network tier (`kernel-net`, README "Network tier and run mode"): IPv4, kernel DHCP and Unix sockets layered on tier 2's packet sockets and NIC drivers; `wisp=run` starts a service supplied as `/test`, reporting its exit code, signal and elapsed time, then powers off; a demo static HTTP service (nolibc/uClibc-ng on sparc32 and x86_64, glibc on sparc64) answers two requests and `/quit` over QEMU user networking. The wisp-test action gained `mode` (test/run), `network`, `forward`, `ready` and `check` inputs and a format 2 `wisp-test-kit` (adds `kernel-net`); `size_budget.py` checks kernel and init size growth against `size-budget.json` | merged | #469, #470 |
| wisp framebuffer tier (`kernel-fb`, README "Framebuffer tier"): fbdev and a framebuffer console on cg3/TCX (`SS-5`) and DRM_BOCHS (sun4u, pc); `fbtest` draws colour bars and a white border, checked pixel by pixel against QMP screendumps (`framebuffer.py`). `mandel fb` draws the Mandelbrot set at the native resolution with an iteration checksum, and `keytest` reports keyboard presses through evdev (on sun4u through a virtio keyboard, or the PS/2 one with OpenBIOS 0035, see below) | merged | #471, #472 |
| Freedoom framebuffer timedemo (`doom.py`, README "Freedoom framebuffer timedemo"): fbDOOM (GPL-2.0) with Freedoom Phase 1 0.13.0 (BSD-3-Clause) runs `DEMO1 -timedemo` on the framebuffer tier; 7,117 gametics checked (count, FPS, a nonblank QMP capture and the child's exit) on SS-5 cg3 and tcx, pc and sun4u; wisp boot CI runs the complete demo on pc and SS-5 cg3 on relevant PRs | merged | #473 |
| wisp data disk: read-only squashfs (XZ) in `kernel-fb`; PID 1 mounts `wisp_data=<dev>` on `/data` and runs `wisp_run=<path>` from it, so fbDOOM and the Freedoom WAD leave the initramfs (`CONFIG_RD_XZ` on the SS-5 dropped); fbDOOM scales the 320x200 frame by an integer factor and centres it (`doom.py --scale`: 1 for the CI timedemo, 0 for the largest factor). DEMO1 still gives 7,117 gametics on SS-5 (cg3, tcx), pc and sun4u | merged | #476 |
| wisp sound: ALSA with OSS PCM emulation in `kernel-fb` (AC97 on pc and sun4u, the SBus CS4231 on the SS-5); `soundtest` plays a square wave to `/dev/dsp` and `sound.py` checks QEMU's `-audiodev wav` capture (level, duration, frequency): 440 Hz for 1 s on pc and sun4u. The SS-5 stops after the first DMA buffer (see Known and not fixed); CI runs pc and sun4u | merged | #478 |
| 3dfx stage 2, third slice: Glide frames with a gamma ramp stay dmabufs (wsh-openglide 0.6: the dmabuf copy applies the ramp in a shader pass, in an EGL context of its own that shares OpenGLide's renderbuffers, readback only if that pass can't be had), and the dmabuf copies of wsh-openglide and mesapt are finished with an `EGL_KHR_fence_sync` fence instead of `glFinish` (`glFinish` without it). Tests: `glide-render --egl --dmabuf` in the package test (the mapped dmabuf equals the read frame, without and with ramps), `e2e/3dfx` expects the Glide gamma phase as a dmabuf and probes its Gouraud triangle, `GLIDE_GUEST_BENCH_GAMMA=1`. Lab, llvmpipe: 707 (egl-headless) and 1590 (dbus,gl=on) frames/s with gamma 2.0 as dmabufs against 1150 and 833 read back; the fences changed nothing measurable there (ROADMAP, Stage 2, "Third slice") | merged | #477 |
| wisp on aarch64 on QEMU's `virt` machine, including the wisp-test kit and action | in review | |
| Play DOOM on wisp: fbDOOM patch 07 (an FPS overlay drawn into the scaled frame, `-fps` or the `` ` `` key, `fbdoom: fps N` on serial; no measurable cost in paired timedemos, DEMO1 still 7,117 gametics), `doom.py --play` (VNC or a local window, `--sound` with a host backend, `--from-release`), a virtio keyboard for sun4u's `kernel-fb` (its PS/2 keyboard is unusable under OpenBIOS), the `wisp-fb` release of kernel-fb and static fbdoom per architecture (`.github/workflows/wisp-fb.yml`, manual, a release of its own so the wisp-test kit stays small), and `wsh-lab wisp-vm` (a wisp shell or Freedoom VM on a PVE node from the published files, the noVNC console to play). Lab: `--play --check` passed on pc, SS-5, sun4u and virt; in the PVE e2e container the shell VM on all four and the DOOM VM on all four (e2e/wisp/README.md, "Play DOOM"). Left: dispatch `wisp-fb.yml` with `publish` after the merge (until then `--from-release` and `wisp-vm --doom` have nothing to download) | in review | |
| SS-5 sound under wisp (Linux `snd-sun-cs4231`): OpenBIOS 0034 gives the CS4231 node `intr 0x39`, as Sun's PROM does, so Linux routes SBus level 5 instead of a software interrupt (#478); pve-qemu `wsh/0124` sets the codec's INT status bit and I24's PI with the APC's playback interrupts, which Linux's handler needs before it clears the APC (with 0034 alone the interrupt repeated until QEMU stopped), qtest `wsh/0125` (written to LEMU's requirements, offered to LEMU). Lab: the unchanged `kernel-fb` plays `soundtest 440 1000` (`ok=1`, 23 interrupts, 440.005 Hz for 1000 ms in the WAV); SunOS 4.1.4 and Solaris 2.6 still play. Left: `sound.py` sees ~150 frames of old ring samples ~36 ms after the tone (the APC's 50 ms take-ahead played out after Linux's stop), and the SS-5 joins wisp-boot's sound step once a published package has both (SPARC.md, "Audio") | in review | |
| CS4231 follow-ups from the LEMU maintainer's review of `wsh/0124`: a write to the codec status register clears PI, CI and TI in I24 as well as INT, as the datasheet and QEMU's ISA model do (pve-qemu `wsh/0126`, qtest `wsh/0127`); the SS-5 no longer plays old samples after Linux stops the DMA: what the APC takes (up to 50 ms ahead of the codec) waits in a FIFO in the model until the codec clock gets to it, the DMA address and count read as the codec's position, a DMA stop in the middle of a buffer drops what lies past it, and the end of the pipe (PMI) still plays everything as `wsh/0032` (`wsh/0128`, qtest `wsh/0129` `mid-stop`, `migrate-fifo`). A vmstate subsection `cs4231/fifo` carries the FIFO only while it holds samples. LEMU took 0124/0125 unchanged onto a local branch; 0126-0129 offered. Lab: `sound.py --arch sparc32` gives the 1000 ms tone, Linux's 22 ms of padding and at most 110 frames (2.5 ms) after it (before: 153-154 frames after 36 ms of silence); SunOS 4.1.4 and Solaris 2.6 play to the end; wisp batch and `--shell` on the eight sparc32 machines; `sun4m-cs4231-test` 10/10 (SPARC.md, "Audio") | in review | |
| 3dfx stage 2 on a GPU node: an NVIDIA GTX 1080 test node (driver 580, `nvidia_drm modeset=Y`; with `modeset=N` the export fails and every frame is read back) sends every Glide and MESA GL frame as a block-linear dmabuf to egl-headless on the GPU, gamma pass and fences included, also through PVE (`mesa-display=egl-headless`). TCG, 3000 frames: Glide 3502 frames/s egl-headless against 956 read back (llvmpipe 1150), with gamma 2.0 2516 against 775, MESA GL 1018 against 678; through PVE 3748 frames/s, 0.10 ms a copy. Harness: the D-Bus listener and `glide-render --dmabuf` import non-linear dmabufs through EGL and read them with `glReadPixels` (or say the probes are skipped), and the `egl`/`dbus` gate looks for the scanout's printf format, as the published binary holds the "as a dmabuf (no readback)" constant only in overlapping pieces (ROADMAP, Stage 2, "GPU node") | merged | #480 |
| 3dfx stage 2, fourth slice: a held OpenGL frame stays on the console (the OpenGL wrapper's display timer, `DispTimerMS`, gave it back to the VGA about 4 s after the last swap; offscreen that deferred deactivation is now ignored, `WM_ACTIVATE`, `wglDeleteContext` and the detach still hand back), double buffering for the dmabuf scanout (two exported buffers per window: wsh-openglide 0.8 `getOffscreenDmabufAt`/`getOffscreenScanoutAt` and mesapt's own; frames go on being copied into the second buffer while a D-Bus client reads the first and go as soon as it replies, mesapt's hold copy is gone), and on a GPU the hop from the game's context to ours waits in the GL stream (`EGL_KHR_wait_sync`; `QEMU_3DFX_WAIT_SYNC`). Tests: the Mesa guest's `MESA_GUEST_HOLD` (held 7 s, then deactivated), `glide-render --dmabuf` checks the second buffer and that the first keeps its frame, `e2e/3dfx` checks double buffering. Lab and an NVIDIA GTX 1080 test node: with a busy D-Bus client more frames reach it (`DBUS_DELAY_MS=2`, MESA GL: 2958 updates against 1649 on the lab, 710 against 445 on the GPU node), egl-headless unchanged; the wait in the stream saves 0.05-0.15 ms a copy on the GPU (ROADMAP, Stage 2, "Fourth slice") | merged | #489 |
| 3dfx stage 2 checked with the published packages (pve-qemu-kvm 11.1.3-4+wsh16, wsh-openglide 0.8): the Windows 98 harness checks a held frame again 1.5 s before the hold ends (`--hold 6` or more, summary column "Held frame") and reports double-buffered windows and QEMU's kept OpenGL frames. Windows 98 SE with `--hold 9`: Glide 2, Glide 3 and OpenGL pass on the lab with egl-headless (every frame as a dmabuf, double-buffered, OpenGL 819 frames/s), read back, and both through PVE, the frames still up 7.5-8.2 s after their swap (the published +wsh12 loses the OpenGL frame by 7.7 s); on the NVIDIA GPU node a PVE VM (`qm create`/`qm start` on the node, `mesa-display=egl-headless`) passes Windows 98 twice with every frame as a dmabuf on the GPU and the held frames kept, and the e2e/3dfx Linux guests there go as double-buffered dmabufs (two open in QEMU). #480's 3502 frames/s: the rate on that node follows the GPU's clocks (P5/P8 for this load) and the node's host; old and new binaries in twelve alternating runs both 436-2354 frames/s, medians 683 and 700 (ROADMAP, Stage 2, "Checked with the published packages"). Stage 2 leaves only AMD and Intel GPU nodes | in review | |
| 3dfx/streaming stage 3a, the D-Bus display from PVE: pve-qemu `wsh/0130` (VNC next to `-display dbus,gl=on`: the D-Bus console reads GL scanouts back into the console's surface once per refresh for the listeners without GL), `wsh/0131` (`-display dbus,refresh-ms=N`), `wsh/0132` (qtests); qemu-server `vga: ...,display=dbus` (also sparc32 cg3/tcx and sun4u), `mesa-display=dbus` (with GL), `dbus-refresh`, `audio0: driver=dbus`, a bus per VM (`wsh-dbus-display@<vmid>`, `/run/wsh-dbus-display/<vmid>.sock`, group `wsh-display`), VNC kept; pve-manager fields. Lab: the 3dfx Glide and Mesa guests pass in VNC's picture through `dbus,gl=on` while the D-Bus client maps the dmabufs; 33.6/61.6/125 refreshes/s at 30/14/5 ms; QEMU survives the client and the bus being killed; 1 s of AC97 and CS4231 sound reached an `AudioOutListener`; `wsh/0130` builds with `--disable-opengl` too (its readback under `CONFIG_OPENGL`, the D-Bus console then upstream's) (ROADMAP, Stage 3, "Stage 3a") | in review | |
| Solaris 2.6 and 2.5.1 on sun4u: traced with QEMU's gdbstub. 2.6's PCI host bridge driver (psycho and sabre in one) refuses a `ranges` property with fewer than four entries and fails its attach silently, so nothing below the sabre attached and the CD's root couldn't be mounted: openbios 0036 adds the 64-bit memory space as OBP has it. 2.5.1's boot program loads the kernel as whole 4 MB pages only when `/openprom` has `aligned-allocator` (the kernel's nucleus hme blocks live in the rest of its data page; without the property that page was unmapped, `Unhandled Exception 0x30`): openbios 0037; then 2.5.1 panicked on the firmware's locked translations (`map_prom: locked translation is not global`; 2.6 and later panic on global ones): openbios 0038 lists them without the lock bit. The installed 2.6 stopped in krtld: its installer adds the platform packages (the UltraSPARC-IIi cpu module link) by the root node's name, so openbios 0039 names the root `SUNW,Ultra-5_10` as OBP does. Install targets `sol26-sun4u` (28 min) and `sol251-sun4u` (67 min, with the Maintenance Update) pass `--check --export` through PVE with 0036-0039 mounted (suninstall, IDE disk, 1024 MB); published in pve-qemu-kvm 11.1.3-4+wsh15, with which both stored disks boot-test, so the targets are in the install matrix (no `matrix_skip`); the install scenario reads its screens from the serial stream when console messages scroll them away, waits out a slow preinstall phase, and takes any stack depth at OpenBIOS's prompt. Regression: the 11 stored sun4u disks (Solaris 7-10, Tribblix, NetBSD 11.1 and 9.3, OpenBSD 8.0, FreeBSD 12.4, Debian 7 and 13) boot-test 11/11 through PVE with 0036-0039, and wisp on sun4u passes (SPARC.md, "Solaris 2.6 and 2.5.1 on sun4u: the kernels") | published | #490 |
| sun4u keyboard under wisp (Linux i8042 on the ebus 8042): OpenBIOS 0035 adds the option `ps2-mouse?` (default false); set, the 8042 gets the `kdmouse` child Linux's sparc i8042 probe needs (it returned `-ENODEV` without it), each child its interrupt (the mouse to the sabre's INO `0x2a`, QEMU's ISA IRQ 12) and a `ranges` so the keyboard child translates to the port window. Off by default because Debian 7's Linux 3.2 panics in `sparc_i8042_probe()` once the probe succeeds. Linux 7.3 also needed its sparc OF driver renamed (`e2e/wisp/linux-patches/0001`, applied by `build.sh`: "Driver 'i8042' is already registered" without it). Lab: `framebuffer.py --arch sparc64` with the 0035 firmware passes the keytest (30, 48, 28, 1), wisp batch, shell, reboot and tier 2 on sun4u pass; boot tests of the stored sun4u disks pass with the default (NetBSD 11.1/9.3, OpenBSD 8.0, FreeBSD 12.4, Debian 7.11, Solaris 7/8/9/10, Tribblix; Debian 13 failed the same way with the published firmware: systemd's timeouts on a busy host, see "Debian 13 sun4u boot test on a busy host"); with the option set the `sparc64` matrix, NetBSD 11.1/9.3, OpenBSD 8.0, FreeBSD 12.4 and Solaris 8/9/10 pass and Debian 7.11 panics as above (Tribblix and Solaris 7 not run with it). The framebuffer runs keep the virtio keyboard on sun4u (#487) until a published package has 0035 (wisp README, "Framebuffer tier") | in review | |
| Debian 13 sun4u boot test on a busy host: the stored disk's boot test failed (`no 'login: ?$' within 900s`) because systemd's 90 s device and start timeouts run in wall-clock time; under TCG udev's coldplug takes about that long idle, and on a busy host `/boot`'s device timed out, `local-fs.target` failed and systemd stopped in emergency mode. Not the disk, the package or OpenBIOS (the same disk and pve-qemu-kvm 11.1.3-4+wsh13 pass on an idle host in 4.6 min, 5.8 through PVE). The boot scenarios append `systemd.default_timeout_start_sec=600 systemd.default_device_timeout_sec=600` at GRUB's editor and wait up to 30 min for `login:`; new installs get the same in a systemd drop-in. At host load 32-43: without the options 4 of 4 boots failed, with them 4 of 4 reached `login:` and the PVE boot test passed (27.5 min). `e2e/sparc/README.md`, "Debian 13 on sun4u" | in review | |
| Debian 13 sun4u install back to the main menu (the regression sweep of 2026-11-26): the late command added for the systemd timeouts wrote its drop-in with `printf '[Manager]\n...'`; the early command's cdebconf saves the answers escaping only newlines and the installer's main cdebconf loads every `\n` back as a newline, so finish-install got the command cut at `printf '[Manager]` (`syntax error: unterminated quoted string`), failed, and main-menu showed "Installation step failed". Reproduced with the lab's own QEMU (148 min to the failure) and in the installer's shell (syslog). The drop-in is now written with one `echo` per line, and `preseed_ports()` refuses a late command with a backslash. `e2e/sparc/README.md`, "Debian 13 on sun4u" | in review | |
| sun4u PS/2 keyboard and mouse on wisp's framebuffer tier: with OpenBIOS 0035 published (pve-qemu-kvm 11.1.3-4+wsh15 and later), `framebuffer.display_args()` gives sun4u `-prom-env ps2-mouse?=true` instead of the virtio keyboard and mouse, for `framebuffer.py`, the `doom.py` timedemo and `--play`; `psmouse` (no laptop protocol extensions) moved to the shared Bochs fragment, so the pc's config and image are unchanged and sun4u's `kernel-fb` grew 1,000 bytes (4,918,504 to 4,919,504); sparc64 keeps `CONFIG_VIRTIO_INPUT` for `wsh-lab wisp-vm`, since qemu-server sets no OpenBIOS variables. The key and mouse checks are strict now: `framebuffer.py` checks the evdev name of the keyboard and mouse `keytest` and `mousetest` open (before, sun4u passed on the virtio keyboard while the PS/2 one was there too) and the exact (+10, +5) move on pc, sun4u and virt. Lab (+wsh17): `framebuffer.py` passed on all five displays (sun4u: `AT Translated Set 2 keyboard` 30, 48, 28, 1; `ImExPS/2 Generic Explorer Mouse` X +10, Y +5, left press/release, right press), the sun4u DEMO1 timedemo 7,117 gametics at 23.90 FPS, `--play --check` with and without `--fps` (one earlier `--fps` run failed on the overlay screendump before any key; the rerun passed) (e2e/wisp/README.md, "The sun4u keyboard"). Left: dispatch `wisp-fb.yml` with `publish` after the merge, so the release's `kernel-fb-sparc64` has the PS/2 mouse | in review | |
| 3dfx/streaming stage 3b, an RDP server with sound for the D-Bus display: the optional package `wsh-qemu-rdp` (qemu-rdp from Marc-André Lureau's qemu-display at a pinned commit, crates from crates.io; patches for a credentials file, the bus name optional and relative mouse motion) with the unit `wsh-qemu-rdp@<vmid>` (bound to the VM's bus, 127.0.0.1 and port 20000 + VMID by default, a generated password, NLA, a self-signed node certificate); qemu-server gives the audio driver `dbus` 48 kHz. CI and lab (also through PVE): login, picture as QEMU's screendump, resize, keyboard, mouse, and rdpsnd sound from AC97 (x86) and the SS-5's CS4231 (ROADMAP, Stage 3, "Stage 3b") | in review | |
| 3dfx/streaming stage 3c, first slice: GStreamer sources and an input bridge for the D-Bus display: the optional package `wsh-gst-qemu-dbus` (our own C, GLib/GIO and GStreamer 1.26, meson) with the plugin `qemudbus`, `qemudbussrc` (the console as raw video: pixels, the shared map, or a linear dmabuf copied out before each `UpdateDMABUF` is answered) and `qemudbusaudiosrc` (the `AudioOutListener` PCM, the guest mixer's volume applied), and `qemu-dbus-input` (keys, buttons, relative and absolute motion from text commands, converted as `IsAbsolute` says). CI and lab, also through PVE: frames identical to QEMU's screendump (shared map, pixels, `dbus,gl=on` dmabufs), keys in the guest 5 ms after the bridge, relative (PS/2) and absolute (virtio tablet) motion, a 440 Hz tone at 440.0 Hz, EOS when QEMU quits; the 3dfx Glide and Mesa guests pass `e2e/3dfx` through it (ROADMAP, Stage 3, "Stage 3c") | in review | |
| 3dfx Glide for old Linux guests: qemu-3dfx's Linux guest wrapper (`wrappers/3dfx/dso/glidedso.c`, Glide 2.43) built as `libglide.so.2` with a `libglide2x.so` symlink (`scripts/build-3dfx-linux-glide.sh`, `make 3dfx-linux-glide`): i586 (`-march=pentium`, no CMOV/ENDBR32, `scripts/check-3dfx-drivers-isa.sh` now reads ELF), only `libc.so.6` at `GLIBC_2.0`, a SysV hash table for pre-2.5 loaders, no crt start files (crtbeginS.o pulled in `__cxa_finalize@GLIBC_2.1.3`), stamped with the same `__REV__`. Released as `qemu-3dfx-linux-glide-<shortsha>.tar.gz` next to the drivers zip, with a README (`/usr/lib`, `ldconfig`, root for `/dev/mem`). Glide 3 and OpenGL have no Linux guest wrapper upstream; the guide sends modern Linux guests to `vga: virtio-gl`. Test: `e2e/3dfx/test.sh`'s `glide-dso` guest (glide-guest linked with `-lglide2x`, the library in its initramfs's `/usr/lib` through ldconfig's cache) passes the scene, probes, FRONTDRAW and GAMMA headless and the window check with SDL under the published pve-qemu-kvm 11.1.3-4+wsh17 (qemu-3dfx b94d988); in qemu-3dfx-check's headless run and test.sh's default guests. Not run on an old distribution or through PVE (guide, "Linux guests") | in review | |
| sun4u snapshots and migration: pve-qemu `wsh/0133` gives the sabre host bridge (interrupt mapping registers, raised lines, outstanding request, PCI control and reset status), the sun4u IOMMU, the PCI configuration space of the ebus and the sabre's own function, and the CPU's SOFTINT, interrupt vector and `idle_halted` (subsection `cpu/sparc64_irq`) migration state, qtest `wsh/0134` (`sun4u-migration-test`). Before it a guest resumed from `loadvm`, `-loadvm`, `-incoming`, `qm rollback` or `qm suspend --todisk` without interrupts (the serial console silent). sun4u has no versioned machine types: older streams no longer load (they resumed without interrupts anyway). The browser build takes the fix from the series now; `web/patches/sun4u-migration-state.patch` (sabre and CPU only) is gone. Lab: wisp's shell, Debian 7.11 and FreeBSD 12.4 answer after `loadvm`, a migration to a file into a new QEMU and `-loadvm` in a new QEMU (timer, raw disk reads with the stored disk's md5, ping to 10.0.2.2); with the series up to 0132 the console stays silent after each. Through PVE (e2e container, Debian 7): `qm snapshot --vmstate 1` + `qm rollback`, `qm suspend --todisk` + `qm start` pass. sparc64 qtests 21/24 (2 skipped, `qmp-test` `oob` fails with and without the patches) (SPARC.md, "Snapshots and migration on sun4u") | in review | |
| 3dfx Glide from DOS: the drivers release's `GLIDE2X.DXE` (DJGPP) tested for the first time, in pure DOS: `e2e/3dfx/dos-test.sh` boots FreeDOS 1.4's boot floppy with our DJGPP test program (`e2e/3dfx/dos/glidedos.c`, linked with the DXE's `dxe3gen -Y` import library, the test scene read back and probed) and FreeDOS's own CWSDPMI, HIMEMX and JEMM386 (taken out of the Floppy Edition's package archive by sha256), headless as PVE runs it, and checks the frame in QEMU's screendump and DOS's text screen after it; new workflow `3dfx-dos.yml` (GitHub-hosted, free software only). With pve-qemu-kvm 11.1.3-4+wsh17 and `qemu-3dfx-drivers-b94d988`: passes with no memory manager, HIMEMX, and HIMEMX with JEMM386 (CWSDPMI as a VCPI client), under KVM, TCG and through PVE (`qm start`), 1260-1840 frames/s. `GLIDE2X.OVL` not tested: an LE library the game's DOS extender (DOS/4GW) loads, using that extender's INT 21h interface and flat model; no free extender loads it and the DJGPP image has no DOS/4GW or Watcom DOS libraries. `GLIDE3X.DXE` tested since (row "3dfx Glide 3 from DOS") | in review | |
| CI media cache: the downloaded test media (Alpine virt CDs, NetBSD CDs, fbDOOM and Freedoom archives) are saved to the Actions cache only by runs on main and restored by pull requests (`actions/cache/restore` + fetch script + `actions/cache/save` on main), instead of a copy per pull request that filled the 10 GB cache and evicted main's entries; `media-cache.yml` re-creates a missing entry daily; NetBSD CDs through `e2e/sparc/fetch_media.py`, Alpine pins in `e2e/pve/boot-media.sh` (`e2e/README.md`, "Downloaded media in the Actions cache") | in review | |
| A boot through PVE on every PR that changes the packages (was "Later"; #357 added the `boot` job for `qemu-server.patch` with x86 i440fx and aarch64): it now also runs for `pve-manager.patch` and `pve-qemu.patch` (and the pins), with pve-manager built from the PR when it changes and `qemu-system-x86_64`/`-aarch64` built from the PR's pve-qemu tree (`e2e/pve/build-qemu.sh`, about 10 min on 12 cores) over the published package; VMs created through the API (`pvesh create`), `qm start` and `qm stop`; cases `i440fx`, `q35`, `ovmf` (q35 with OVMF) and `aarch64` (no longer skipped). A case passes only with firmware output and the login prompt on the board's console tty (`ttyS0`, `ttyAMA0`): Linux gets a login onto any serial port, so `login:` alone missed a socket wired to the wrong UART, #248's sparc64 bug. Lab, with the installed `QemuServer.pm` broken in a scratch container: #248's `-bios` fix reverted fails `aarch64` at `qm start` (`qemuAccepts` catches it too since #249); the aarch64 socket on a `pci-serial` and the x86 socket on COM2 pass `qemuAccepts` and every old check but fail here. With all three packages from the branch: login after 16-29 s on x86 (KVM), 60-79 s under TCG, 122 s on aarch64 (TCG, busy host); 34-80 s and 43 s on a quieter host with the published packages. `e2e/README.md`, "Booting a guest through PVE" | in review | #357 |
| sparc installs before merge for QEMU and OpenBIOS changes: `sparc lab PR QEMU` (`.github/workflows/sparc-lab-pr-qemu.yml`) runs the four NetBSD installs of `sparc lab NetBSD` on pull requests that change `submodules/pve-qemu.patch`, the pve-qemu pin or `openbios/`, with that pull request's `qemu-system-sparc`/`-sparc64` (`e2e/sparc/pr-qemu.sh`: the pve-qemu tree with the whole series applied by quilt without fuzz, only `--target-list=sparc-softmmu,sparc64-softmmu`, ccache cached per pull request) and its three OpenBIOS images (a missing `openbios-sparc64`, which the package build only warns about, fails the job), put into the lab image by `pr-qemu.Dockerfile`; what was built is in `versions.txt` and the run summary. GitHub-hosted runners, so fork pull requests run it and the `sparc-lab` runner still runs no pull request code; not a required check. Lab: main's series built cold in 169 s (78 s from ccache) and passed 4/4 installs; a series that doesn't apply and an OpenBIOS patch that doesn't apply both failed the build; a `wsh/0021` that builds but never raises the cmd646 interrupt failed the sun4u install and passed the SS-5 (e2e/sparc/README.md, "Before merge") | in review | |
| CI media cache for FreeDOS: the FreeDOS 1.4 Floppy Edition zip, which `3dfx-dos.yml`, `sparc-lab-dos.yml` and `audio-matrix.yml` downloaded from ibiblio on every run, is one Actions cache entry (`freedos-fd14-floppy-<sha256 prefix>`, `${{ runner.temp }}/freedos`) saved by main only, with a `freedos` job in `media-cache.yml`; one pin (`e2e/sparc/targets_dos.py`, `FREEDOS_ZIP`) that the three harnesses import, fetched and checked by `e2e/sparc/fetch_media.py` (now also `--key`), given to the harnesses as `FREEDOS_ZIP` (`dos-test.sh --freedos-zip`); the audio image builds from the repository root to carry the pin; `tests/test_fetch_media.py` guards against a second copy of the pin and checks that the workflows share key and path (`e2e/README.md`, "Downloaded media in the Actions cache") | in review | |
| 3dfx demo `wshdemo` (`e2e/3dfx/demo`, `make 3dfx-demo`): one C core without a C library (a lit, mipmapped cube in front of a depth-tested wall; a fogged tunnel with additive stars and an alpha-blended square; a plasma uploaded as a 256x256 texture every frame; title card with the wrapper's build string, frame rate and frame-time graph; Space, G/Shift+G gamma, R resolution, F, Esc) and three front ends: Windows `WSHDEMO.EXE` (Glide 2, Glide 3, OpenGL; mingw-w64 without a C runtime, `KERNEL32`/`USER32`/`GDI32` only, 53 KB), DOS `WSHDEMO.EXE` (DJGPP, `GLIDE2X.DXE` through the `dxe3gen -Y` import library, 120 KB) and Linux `wshdemo` (`libglide.so.2`, its own `_start`, glibc 2.0 symbols, 50 KB), all i586 (`scripts/check-3dfx-drivers-isa.sh --no-p6`, which now also reads ELF programs and GCC assembler output for DJGPP code). Test modes `-bench N` (frame rate per part), `-check` (a fixed frame per part read back, probes in flat areas) and `-hold S` (the held frame's probes for the host). Released as `wshdemo-<shortsha>.zip` and `wshdemo-linux-<shortsha>.tar.gz` with the drivers. Tests: a `demo` guest in `e2e/3dfx/test.sh` (headless default, `qemu-3dfx-check.yml`), after `GLIDEDOS.EXE` in `dos-test.sh` (`3dfx-dos.yml`), optional `demo-*` tests in the Windows 98 harness. TCG, llvmpipe, published pve-qemu-kvm with `qemu-3dfx-drivers-b94d988`: Linux guest passes at 640x480, 800x600 and 1024x768 (cube 256-808, tunnel 50-118, plasma 111-326 frames/s, depending on the load of the shared host), FreeDOS passes in all three memory profiles (127-188, 30-40, 67-91); the OpenGL backend passes its checks on the host's Mesa (`plat_egl.c`), and `WSHDEMO.EXE -api opengl` under Wine on Mesa at all three resolutions. Not run in a Windows guest yet: Glide 2, Glide 3 and OpenGL through the wrappers (3dfx guide, "Demo") | in review | |
| Sun PROMs' NVRAM in LEMU's form: pve-qemu `wsh/0059`-`0060` replaced by the version LEMU ported onto its own `m48t59` storage, so both carry the same code: `wsh/0073` (new, before 0059 in the series) is LEMU's storage (Antoni Sawicki's and Ørjan Malde's commits squashed, `Origin:` lines), 0059 the sysbus `drive` on top (built on LEMU), 0060 the qtest with a delayed-write case. Writes now reach the image 100 ms after the first of a batch and when the VM stops (QMP `quit`, SIGTERM); a SIGKILL within 100 ms loses the last write. Lab: whole series without fuzz, `sun4m-nvram-test` 8/8, `qtest-sparc`/`qtest-sparc64` as before; the LX PROM (raw and qcow2) and the SS-20 PROM boot by themselves after the one-time setenv; through PVE `sol26-ss20prom-nvram` passes, and `qm stop` right after the setenv, `vzdump --mode stop` and `qmrestore` keep the volume. `submodules/SPARC.md`, "The NVRAM kept in a volume"; `upstream/lemu-port.md` | in review | |
| 3dfx game `wshspace` (`e2e/3dfx/space`, `make 3dfx-space`): a procedural space exploration and asteroid mining game on the wshdemo pattern (one C core without a C library or libm, generated textures, meshes and soft-synth audio, no data files), for the same three targets: Windows `WSHSPACE.EXE` (Glide 2, Glide 3, OpenGL; 94 KB, capped at 96 KB), DOS `WSHSPACE.EXE` (DJGPP, Glide 2) and Linux `wshspace` (`libglide.so.2`), all i586 (`--no-p6`). Same test modes as wshdemo (`-bench N`, `-check`, `-hold S`). Windows `-hostgl` (the system `OPENGL32.DLL` in a window, no mode change), `-log FILE` and `-nocom` for runs outside a guest; outside a guest (no `C:\WIN3DFX`) errors also show in a message box. Shared `w3d.h`: COM1 is opened and written with a 200 ms timeout, so a UART that blocks can't hang the program. All Windows builds use `-fno-tree-loop-distribute-patterns`: without it GCC 14 at `-Os` turned the own `strlen` into a call to itself. Checked: `-hostgl -check` passes for `WSHSPACE.EXE` and `WSHDEMO.EXE` on a host GPU. Not run in a guest yet, and not released with the drivers | in review | |
| A break on a serial console no longer hangs the guest: QEMU's ESCC set RR0's Break/Abort bit for good and kept an interrupt up that neither RR3 nor RR2 named, so Solaris and SunOS on ttya spun in their serial interrupt (QEMU at 100% of a core), Linux never reached the firmware prompt and NetBSD never entered ddb. pve-qemu `wsh/0141` models the Z8530's external/status latch for the bit (an interrupt at the start and at the end, named in RR3 and RR2, cleared by Reset Ext/Status Interrupts; the break ends one character time after it began but not before the guest has seen its start, with a NUL in the receiver), `wsh/0142` the qtest. With QMP `chardev-send-break` Solaris 2.6, SunOS 4.1.4 and Linux (wisp) stop at the firmware prompt and `go` resumes them, NetBSD 9.3 and 11.1 enter ddb; the `stopa` matrix has the break cases. PVE still can't send a break (it could through QMP). `submodules/SPARC.md`, "Stop-A" | in review | |
| sun4u: the IDE interrupt lost at Debian 13's power-off (1 of 9 boots on a busy host) was QEMU's sunhme, not the cmd646: Linux resets the NIC and frees its interrupt when the interface goes down, the model kept receiving, the next frame raised an interrupt nobody cleared, and the sabre (one request at a time) held every IDE interrupt behind it; the same request, sent again at the next `up`, panicked Linux in `happy_meal_interrupt`. Shown with QEMU traces (`sabre_*`, `sunhme_*`, timestamps). pve-qemu `wsh/0135`: an ERX reset turns the receive DMA off until the guest enables it and each reset drops its engine's status; qtest `wsh/0136` (`sun4u-sunhme-reset-test`). `wsh/0137`-`0138`: disabling a PCI slot in the sabre now drops a request of any of the slot's inos (found reading the code, not what Debian hit). Lab, Debian 13 with `dd` on the IDE disk and `enp2s0` down and up every 3 s, or down once with frames sent from the host side: 11 of 18 runs failed on the published 11.1.3-4+wsh17 (9 panics, 2 lost IDE interrupts as at the power-off), 0 of 11 with the fix (4 at the load where 3 of 4 failed); NetBSD 11.1, OpenBSD 8.0, FreeBSD 12.4, Debian 7 and Solaris 10 still ping through `hme0` after a down/up. The cmd646, the idle halt and the earlier sabre and `%softint` fixes ruled out; a different, unreproduced lost-wakeup race found in the Linux idle helper (fixed since, `wsh/0139`). `submodules/SPARC.md`, "The lost IDE interrupt at Debian 13's power-off" | in review | |
| sun4u Linux idle halt: a tick between the helper's check and the halt is no longer slept through (was "Known and not fixed"; found by reading, never seen on a guest). `helper_sparc64_idle_linux()` (`wsh/0070`) checked for a pending interrupt without the BQL and then set `cs->halted`; a tick in between (`tick_irq()` sets `TICK_INT` and `halted = 0` under the BQL) is masked at `%pil` 14, raises no `CPU_INTERRUPT_HARD`, and the vCPU thread slept until the next interrupt vector, as Linux arms no next tick before taking this one. pve-qemu `wsh/0139` checks again and halts under the BQL; the other idle helpers halt at `%pil` 0, where the tick raises `CPU_INTERRUPT_HARD`, so they keep the window without the effect. qtest `wsh/0140` (`sun4u-idle-test` case `tick-race` per idle loop, 80 cases, 240 s in `slow_qtests`: the test runs ~70 s, over meson's 60 s default) holds the CPU in the window by writing the `sparc64_idle` trace to a full FIFO until a tick has fired: without 0139 the three Linux layouts fail every run (15/15), the `%pil` 0 loops pass; with it 50/50. Lab: `qtest-sparc64` 22 OK (`qmp-test` `oob` failing as before); wisp's shell at 6.2-6.7% of a host core with 0139, 5.7-6.8% without, 100% with `idle-halt=off`, `crc 100000` and the clock unchanged (`submodules/SPARC.md`, "sparc64 (sun4u)", "Idle") | in review | |
| `wsh-lab wisp-vm` with sun4u's PS/2 keyboard and mouse: a sun4u framebuffer or DOOM VM gets `-prom-env 'ps2-mouse?=true'` in its `args` (qemu-server has no setting for OpenBIOS variables, and `wisp-vm` already sets `args` as root for `-kernel`) instead of the virtio keyboard. It checks first that the node's `/usr/share/kvm/openbios-sparc64` has the option (OpenBIOS 0035, pve-qemu-kvm 11.1.3-4+wsh15 and later). With older firmware it keeps the virtio keyboard and prints a note, so sparc64's `kernel-fb` keeps `CONFIG_VIRTIO_INPUT`. Other sun4u VMs (Debian 7's Linux 3.2 panics with the option) are unchanged. Lab, in the PVE e2e container (pve-qemu-kvm 11.1.3-4+wsh20, the published `wisp-fb`): `keytest` read `AT Translated Set 2 keyboard` 30, 48, 28, 1, and `mousetest` read `ImExPS/2 Generic Explorer Mouse` X +10, Y +5 and the buttons, both through QMP. The fallback was checked against a firmware file without the option (e2e/wisp/README.md, "Doom in a PVE VM"). `--doom` on sun4u was not rerun | in review | |
| More than 512 MB on SS-10/SS-20, up to 2048 MB with OpenBIOS: Solaris counts only memory below 512 MB as memory behind the SS-10's and SS-20's controllers (eight SIMM slots of 64 MB, read from the ECC controller's implementation bits), so with more it panicked at boot (2.6: `kernel read fault at addr=0x0` in `kvm_init`); the `/memory` layout played no part. pve-qemu `wsh/0143` presents the SS-600MP's MCC above 512 MB under OpenBIOS (512 MB and less, and the Sun PROM, unchanged), `wsh/0144` its qtest; OpenBIOS ran out of heap at 1 GB, 0040 takes the SRMMU tables in chunks and makes the heap 288K. Lab: Solaris 2.5.1, 2.6, 7, 8, 9 on SS-20 and 2.6, 7 on SS-10 boot the stored disks with 2048 MB (2.6 with 2 and 4 CPUs); NetBSD, SunOS 4.1.x, Debian 4.0 and Solaris 2.4/2.6 at 512/256 MB on SS-20/SS-5 unchanged. qemu-server and the UI take up to 2048 MB on SS-10/SS-20 with OpenBIOS (wizard preset 512), the SS-20 PROM stays at 512. Not verified: installs and the PVE path with more than 512 MB, more than 2048 MB (`submodules/SPARC.md`, "More than 512 MB on SS-10 and SS-20") | in review | |
| Audio signature for guest sound tests: one fixed signal in `e2e/wisp/audiosig.h` (integer math, no C library or libm, no 64-bit division): 8 segments of 500 ms, triangle waves of 400 + 100 k Hz left and 600 + 150 k Hz right in segment k, -6 dBFS, 4 s, at any rate from 8000 to 48000 Hz; `e2e/audio/wavcheck.py --signature [N]` finds N of them in a `-audiodev wav` recording and checks each segment's frequency per channel (3 %), the duration, gaps over 2 ms per channel, swapped channels and mono, and tells an old-samples tail from a dropout (unit tests: resampled, 8-bit, swapped, mono, cut after one buffer, dropouts, tails, the header against its Python model). wisp: `soundtest sig [rate..]` (8000, 22050, 44100 Hz by default); `sound.py` boots once more per machine for it, in wisp-boot's sound step. wshspace: `-audiotest` through each platform's own backend, no display; its Linux OSS backend now keeps two fragments queued and writes no more than fits (the test found a 7 ms dropout after the first fragment on AC97), its DOS backend plays 8-bit stereo at exactly 22050 Hz on a DSP 4.x (SB16; mono at 22222 Hz before, still so on older DSPs) and no longer loses a ring of sound to a torn read of the DMA address (the two bytes read while the DMA moved; seen in CI without a memory manager) or to a step back of `uclock()`: it reads the address until the bytes agree, counts bytes written and played, and mixes 186 ms ahead in a 743 ms ring; new `e2e/3dfx/space/audio-test.sh` (Linux guest, AC97, job in `audio-matrix.yml`) and a last step in each boot of `dos-test.sh` (`-device sb16`, `3dfx-dos.yml`): the DOS test the audio matrix asked for. Lab with pve-qemu-kvm 11.1.3-4+wsh27: every segment within 0.01 % on pc, sun4u, virt and the SS-5 at all three rates (4.000-4.003 s, no gap), wshspace on Linux (KVM and TCG) and DOS (all three memory profiles) 4.000 s, no gap. Windows `-audiotest` builds (96,768 of 98,304 bytes), not run in a guest | in review | |
| 3dfx/streaming stage 3d, Moonlight to Wolf: a Moonlight client streams a VM's D-Bus display (picture, sound, keyboard, mouse) through Wolf (games-on-whales) with `qemudbussrc` (and a `compositor` that repeats the newest picture at the client's frame rate) into x264, `qemudbusaudiosrc` into Opus and `wolf-input-bridge` (Wolf's uinput keyboard and mice into `qemu-dbus-input`) as an app's runner; `e2e/streaming` builds Wolf, moonlight-embedded and a measuring client (`wsh-moonlight-probe`) from source at pinned commits and measures (`test.sh`, workflow `streaming.yml` for PRs touching it and by hand). Lab, published pve-qemu-kvm, TCG, 1280x800 H.264 at 60 frames/s: pairing with a PIN entered on the node, the picture 1.6/255 from QEMU's screendump, guest draw to decoded frame 48-61 ms median, keys and buttons in the guest 1.3-2.2 ms after the client, a 440.0 Hz tone in the client's audio, with and without `dbus,gl=on`; on a PVE node with an NVIDIA GPU, Wolf in a privileged container (template from the Dockerfile's `ct` stage) streamed a `qm start` VM with every check passed (x264 54 ms, NVENC 50 ms median); an unprivileged container is refused by the VM's bus (dbus-daemon checks the group against the node's user database). Wolf needed a patch for apps without a compositor (ROADMAP, Stage 3, "Stage 3d") | in review | |
| 3dfx/streaming stage 3d, an unprivileged container: qemu-server's VM option `dbus-display-uids` (root only) lets host uids such as an unprivileged container's root (100000) onto that VM's D-Bus display bus: a bus configuration per VM (`/run/qemu-server/<vmid>.dbus-display.conf`, the shared policy plus each uid), a node user `wsh-display-<uid>` for a uid without one (dbus-daemon refuses a uid it can't look up, whatever the policy says) and an ACL entry `--x` on `/run/wsh-dbus-display` while a VM names the uid; `wsh-gst-qemu-dbus` authenticates without a uid (GLib's `CROSS_NAMESPACE`). CI and lab: the clients as root of a user namespace mapped to 100000 get the picture, sound and input; uid 200000, uid 100000 on another VM's bus and a node user outside `wsh-display` are refused; no real node yet (ROADMAP, Stage 3, "Stage 3d: an unprivileged container") | in review | |
| 3dfx/streaming stage 3e, tiled dmabufs and the audio dropout: `qemudbussrc` reads dmabufs it can't map (NVIDIA's block-linear) through EGL (an EGLImage on the render node's EGL device, read back as `BGRx`, read again 20 ms later since NVIDIA's driver doesn't wait for QEMU's drawing), so `dbus,gl=on` streams on an NVIDIA node; `qemudbusaudiosrc` sends silence while the guest plays nothing, which ends the dropout at a tone's start (Wolf's `audiorate` filled the gap at once and its leaky queue dropped the tone's start); `e2e/streaming` fails on a dropout or an audio burst, takes a package build (`WSH_GST_DEB`) and gets an EGL run. Lab: every check passed, the tone without a dropout, first sound 38-56 ms after the command (was 90-160); NVIDIA node: the frame identical to QEMU's screendump through EGL, Moonlight with every check passed, GL 89-96 ms median with x264 against 53-71 ms without (ROADMAP, Stage 3, "Stage 3e") | in review | |
| 3dfx/streaming stage 3f, a Windows 98 guest with Glide through Moonlight: `w3dstrm.exe` (`e2e/3dfx/win98`, a Glide 2/3 program that takes commands on COM1, animates at 60 frames/s with the frame number in eight cells where the probe client reads its points and reports every swap) and `e2e/streaming/stream3dfx.py` (latency for every guest frame, pacing, input to picture, keyboard, mouse, a WinMM tone, the demos); `wolf-config.py` scales before its compositor (a guest mode change, 1280x1024 desktop to 640x480 Glide, showed unscaled on a checkerboard), `wolf-pair` ignores the caller's `XDG_RUNTIME_DIR`. NVIDIA node, KVM, Wolf in a privileged container: guest swap to decoded frame 23.6-25.7 ms median with Glide read back (x264, NVENC, Glide 3) and 24.9-33.1 ms with `dbus,gl=on`, frames at `qemudbussrc` 0.7 ms (read back) and 2.0-2.6 ms (GL) after the swap, 58.8-60.1 of 60 guest frames a second at the client, input to picture 40-44 ms, keys and the tablet exact; sound fails in the guest (its AC97 driver), not in the stream. Unprivileged container: the input needs a udev rule on the node (Wolf's event devices are `root:input`), the bus waits for a qemu-server with `dbus-display-uids` on the node (ROADMAP, Stage 3, "Stage 3f") | in review | |
| 3dfx/streaming stage 3g, the unprivileged container on a node: Wolf in an unprivileged container with a uid range of its own, the VM with `dbus-display-uids`, Wolf's input devices given to the container's root by a udev rule on the node (no way without a node change found); the `ct` template gets a DHCP client (`dhcpcd-base`); docs: the unprivileged recipe, the udev rule, Wolf's ports and PVE firewall rules, pairing a client on the network. NVIDIA node, KVM, wisp at refresh 30 ms, x264, every check passed: guest draw to decoded frame 61.3 ms median on the loopback and 60.6 ms with the probe on another machine, keys 2.6 and 3.0 ms; other uids and a VM that doesn't list the uid refused; the Windows 98 Glide guest 26.1 ms median with every check but sound passed, only with `qemudbussrc shared-map=false` (the shared map got no `UpdateMap` for the Glide surface read back) (ROADMAP, Stage 3, "Stage 3g") | in review | |
| wisp-netbsd, the NetBSD sibling of wisp (`e2e/wisp-netbsd/`): a second, independent OS test of the same machines. NetBSD 11.1's `build.sh -U` cross-builds its toolchain, libc and a small memory-disk kernel per architecture in a Debian container without root, from the release's source sets pinned by SHA-256; PID 1 is a static C program against NetBSD's libc that prints wisp's markers (banner, `uname`, CPUs, memory, a clock check, a file check on the remounted md root, wisp's compute loop with the same CRC) and powers off with `reboot(RB_HALT | RB_POWERDOWN)`; `run.py` reuses wisp's runner. sparc32 boots with QEMU's `-kernel` and OpenBIOS as it is (OpenBIOS starts NetBSD's ELF kernel like Linux's image) on all eight sun4m machines; sparc64 from a boot disk (Sun label, NetBSD's bootblk and `ofwboot`), since OpenBIOS's sun4u `-kernel` only starts Linux images; amd64 with `-kernel` through its PVH entry on `pc` and `q35`. No QEMU or OpenBIOS change. Kernels 2.5/4.3/7.5 MB as files (1.4/1.6/2.7 MB text and data without the ramdisk), ramdisks 0.9-1.0 MB, PID 1 613-767 KB (jemalloc through stdio). Lab, published 11.1.3-4+wsh30, 36 of 36 boots: power-off after 2.2-2.4 s on sun4m, 10.1-10.3 s on sun4u (8.7 s of it before the kernel), 2.4-2.5 s on pc/q35. Tools about 5 min per architecture on the lab host; with tools and libc cached a build takes 24 s. CI: `wisp-netbsd.yml`, one job per architecture, tools and libc cached; not a required check. Left: "Later", "wisp-netbsd, what is left" | lab-tested | #551 |
| 3dfx VMs run with KVM: a `vga: ...,mesa=1` VM ran in TCG even with KVM on, since qemu-server starts the 3dfx binary by its own name and QEMU prefers KVM by default only when the program name ends in `kvm` (`/usr/bin/kvm`). qemu-server now passes `accel=kvm` to the 3dfx binary when the VM's `kvm` option is on (`accel=tcg` with `kvm: 0`, as before). On a node a Windows 98 Glide benchmark went from 12.4 to 200 frames per second with KVM. cfg2cmd tests (`vga-mesa*`, `vga-mesa-kvm0`), Playwright `3dfx-accel.spec.ts` (query-kvm of a `qm start` VM, gated on the installed qemu-server), the Windows 98 harness checks the running VM's accelerator. Earlier "KVM" figures of 3dfx VMs started by PVE were most likely TCG (3dfx guide, "KVM") | in review | |
| 3dfx Glide 3 from DOS: the drivers release's `GLIDE3X.DXE` (DJGPP) tested for the first time. `e2e/3dfx/dos/glidedos.c` built with `-DGLIDE3` is `GLID3DOS.EXE` (an 8.3 name; `GLIDE3DOS.EXE` doesn't run in DOS), linked with `libfxgl3.a`, the `dxe3gen -Y` import library `build.sh` now makes from qemu-3dfx's `gl301dxe.c`: the same scene through the Glide 3 API (`grGet(GR_NUM_BOARDS)`/`grGetString` instead of `grGlideGetVersion`, `grVertexLayout`, `grSstWinClose` with the context), read back with `grLfbReadRegion`, `GLIDE3DOS:` lines on COM1. `dos-test.sh` runs it after `GLIDEDOS.EXE` in each FreeDOS boot (`wait=3` first, `-- --no-glide3` leaves it out) and checks its probes in QEMU's screendump and the VGA afterwards; `3dfx-dos.yml` unchanged apart from names. Found on the way: `GLIDEDOS.EXE` linked libgcc's i686 unwinder (CMOV), which crt0 calls at start-up; both programs now define the two frame-registration entry points as the demo does, and `build.sh` runs `scripts/check-3dfx-drivers-isa.sh --no-p6` on their code and libgcc members. The harness's "VGA after" check of `GLIDEDOS.EXE` now waits for `GLIDEDOS: CLOSED` instead of QEMU's `offscreen closed`, which reaches the log late (it ran during the next window). Lab, pve-qemu-kvm 11.1.3-4+wsh35, wsh-openglide 0.9, `qemu-3dfx-drivers-b94d988`: Glide 2 and Glide 3 pass with no memory manager, HIMEMX, and HIMEMX with JEMM386, under KVM and TCG (see the 3dfx guide). Follow-up: `wshdemo -api glide3` in DOS (the DOS demo is Glide 2 only) | in review | |

## In progress

Nothing outside the open pull requests. Solaris 10 on sun4u (#294, #298) and Tribblix (#318) are
merged; what is left of them is item 2 under "Next".

## Next, in this order

1. **Idle on sparc64, what is left.** NetBSD, OpenBSD, Solaris 7-10, Tribblix and Linux idle on
   sun4u (see Done: `wsh/0042`-`0044`, `wsh/0070`-`0072`). Not covered: other kernel builds than the
   ones in `SPARC.md` (each new one: `-trace sparc64_idle_match`, and if nothing matches, read its idle
   loop and add a layout with a qtest case); Tribblix not measured again with `wsh/0070`-`0072`; and
   sun4v/`niagara` (hypervisor `cpu_yield`), out of scope.
2. **Solaris and Tribblix on sun4u, what is left.** Both install through `lab.py install`
   (`sol251-sun4u`, `sol26-sun4u`, `sol7-sun4u` to `sol10-sun4u`, `tribblix-m34-sun4u`; 2.6 and 2.5.1
   with pve-qemu-kvm 11.1.3-4+wsh15 or later, openbios 0036-0039, Done). Open:
   - after the firmware reboot (Done): Tribblix's reboot not tried; the reboot's boot string is
     still dropped (Solaris 8's mini-root needs `auto-boot?` false and `boot disk:b`; the `sparc64`
     matrix case `nb111-reboot-bootstr-sparc64` only checks that such a reboot comes back);
   - Tribblix: with a ZFS root FMA marks the IDE disk DEGRADED during the install (EIO on first
     attempts that ZFS retries, no data errors; a UFS install, `ROOT_FS=ufs`, hasn't been booted;
     Debian 13's lost IDE interrupt was the sunhme holding the sabre, `wsh/0135`, and whether
     Tribblix's EIO has the same cause is not checked);
     the live CD's package catalogue is older than its packages (a Tribblix issue); 257 minutes
     through PVE, over the install matrix's 240-minute limit, so it stays out of it.
   Details: `submodules/SPARC.md`, "Solaris on sun4u" and "Tribblix on sun4u".
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
4. **x86 retro.** Starts from the owner's notes and known problems (DOS and the first megabyte of
   memory among them). Then, like sparc: measure, profiles, tests.
   - **Started with DOS.** `lab.py install msdos622` installs MS-DOS 6.22 from its three floppies
     into a PVE VM (~4 min under TCG), driven on the VGA text screen through an exact reader of the
     text buffer (`vgatext.py`), with the disk swaps done by `install.MediaSwapper`; `freedos14`
     does FreeDOS 1.4 the same way, and CI installs FreeDOS from its floppies on a GitHub-hosted
     runner. The first megabyte is measured (`dos_mem.py`, the [DOS guide](docs/src/content/docs/guides/dos.md)):
     SeaBIOS 1.17 leaves 110K of read-only gap after the VGA, NIC and vapic ROMs, EMM386 makes
     98-102K of it one UMB, no NIC and no vapic ROM give 118K, a dummy option ROM never helps, and
     an `I=` range into SeaBIOS's data at E9000 hangs DOS. `machine: pc,legacy-bios-layout=1`
     (qemu-server, Machine > Advanced in the UI) drops the NICs' and the vapic ROM without `args:`:
     124K gap, 114K UMB, 118K with `I=`, measured through PVE. Idle: `msdos622` loads
     `WSHIDLE.COM` (a 142-byte TSR in the repo, `HLT` in INT 28h and INT 2Fh/1680h, typed in with
     `DEBUG` on the first boot), FreeDOS's installer already loads `FDAPM APMDOS`; a DOS VM at its
     prompt takes 1-2% of a host core instead of 100%, and both targets' checks verify it.
     `POWER.EXE` idles too but slows keyboard-polling programs 2.5-10 times. Games: Wolfenstein 3D
     hangs on a black screen under QEMU's default VGA retrace emulation and runs with the precise one,
     `vga: std,retrace=precise` (Hardware > Display in the UI, the DOS guide's "VGA retrace").
     The Incredible Machine 1 and 2 stayed black on every `vga` model while they ran: QEMU
     read the VGA attribute address register (3C0h) as 0 in the flip-flop's data state, and the
     games restore the address they read there after loading the palette, which turns the display
     off. pve-qemu `wsh/0051` (qtest `wsh/0052`, in review) returns the address in both states, as
     the VGA does; reproduced on plain QEMU 11.1.3, `upstream/qemu-vga-ar-index-read.md`.
   - Next for DOS (`ne2k_isa` is on the ISA bus since #304: an ISA NIC needs no option ROM; for most
     guests `rtl8139` stays the better choice): Windows 3.1 on top of `msdos622` (its SETUP has a graphical part, so OCR or the
     screendump for those screens); other DOS versions (5.0, 6.0, PC DOS 7) as targets.
   - Driver and patch packs: the owner's curated DOS and Windows 9x drivers and patches (the VBE
     display drivers among them) that the README and the guest operating systems guide mention. First
     sort out what may be published: much of it is proprietary, and what isn't gets a source and a
     licence next to it; the rest stays a list of what to get and where. Then a guide per pack.
   - **Audio: matrix in CI.** `e2e/audio/` (workflow `audio-matrix.yml`, GitHub-hosted, weekly)
     records each device with QEMU's `wav` backend and checks the tones: SB16, AdLib, PC speaker
     and `sb16-adlib-pcspk` under FreeDOS with our own `AUDTEST.COM`; AC97, Intel HDA (ich6/ich9),
     ES1370, virtio-sound and USB audio under a Debian kernel + initramfs; every `audio0` value also
     through qemu-server (`driver=wav`: `qm showcmd`, then a real `qm start` that records). All
     play. Found: on q35 PVE's machine config adds a codec-less `ich9-intel-hda` at 00:1b.0, so
     `audio0` is the guest's second card; qemu-server puts two codecs on one HDA controller; Linux
     starts AC97/HDA muted; SB16 direct DAC isn't emulated; the wav header's sizes stay 0 however
     QEMU ends, a QEMU 11 bug (the voices' references keep the backend from being finalized; also
     in plain 11.1.3; [write-up](upstream/qemu-audio-wav-header-sizes.md)); the matrix checks the
     header's format on every recording and ends QEMU by `quit`, SIGTERM, SIGKILL and `qm stop`. Table and
     the headless-node answer (`pa` with `server=`, also for PipeWire desktops) in the
     [audio reference](docs/src/content/docs/reference/audiodev.md). A DOS test of a sound card
     through a program's own driver now exists: wshspace `-audiotest` plays the audio signature
     (`e2e/wisp/audiosig.h`) on the SB16 in `dos-test.sh`, checked by `wavcheck.py --signature`.
     Next: GUS and CS4231A (a DOS test for each, on that pattern); Windows guests (9x with SB16/ES1370, XP with AC97/HDA); listening on a
     real node over `pa`.
   - Display: std VGA, Cirrus, VMware, QXL against noVNC and SPICE, for DOS, Windows 3.x–XP and
     older Linux.
   - Streaming: 2D/3D video and audio in one connection (Moonlight to Sunshine or Wolf), without a
     desktop the VM dies with; keep VNC beside it. The existing `vga: …,server=` path drops VNC,
     uses `-vga` instead of a device, and sets no `XAUTHORITY`. 3dfx goes in stages, sizes are
     estimates:
     - **Stage 0: OpenGLide shipped, tests without Windows** (`packages/wsh-openglide`, `e2e/3dfx`).
       qemu-3dfx's Glide device `dlopen()`s `libglide2x.so`/`libglide3x.so`, which no package had;
       `wsh-openglide` builds OpenGLide from kjliew/qemu-xtra (pinned, X11/GLX). CI renders a
       Glide 2 and a Glide 3 scene through the installed libraries under Xvfb (llvmpipe, softpipe)
       and checks pixels, then boots a Linux guest in the published `qemu-system-x86_64-3dfx` whose
       `/init` draws the same scene through qemu-3dfx's own Linux guest wrapper (`glidedso.c`,
       i386, `/dev/mem`), reads it back through the pass-through and checks it and the SDL window
       (about 10 s under TCG). Found on the way: QEMU dies with `BadMatch` when the X server offers
       a 32-bit ARGB visual (Xvfb with Composite: OpenGLide's GLX config picks it, SDL's window
       has 24 bits); SDL needs `libegl1`; a guest LFB read that drains queued calls comes back
       shifted by their data (glidept puts the pixels after it, the wrappers read from the start).
       pve-qemu-kvm depends on `wsh-openglide` and `libegl1` whenever it ships the 3dfx binary (a
       dependency, not a recommendation: the 3dfx VM stops without either, and the UI shouldn't
       have to check what is installed). Finished (in review): OpenGLide wrote
       `OpenGLid.ini`/`.log` into QEMU's working directory and `exit(0)`ed QEMU when it couldn't;
       under PVE QEMU always daemonizes and then runs in `/`, so the files landed in `/` of the
       node, and a different working directory from qemu-server couldn't help. `wsh-openglide`
       now takes the directory from `OPENGLIDE_DIR` and never exits (a patch in
       `packages/wsh-openglide/patches/`), and qemu-server sets `OPENGLIDE_DIR` for the 3dfx
       binary to `/run/qemu-server/<vmid>-3dfx` (root, 0700). The Mesa pass-through has a
       Windows-free test too: there is no Linux guest wrapper for it upstream, so the second
       guest of `e2e/3dfx` (`mesa-guest.c`) speaks the mesapt device's protocol itself (the
       revision handshake, the wgl calls, single GL calls, glReadPixels through the frame memory)
       and draws the same scene; both guests also pass when PVE starts them (`qm start` of a
       `mesa=1,server=` VM with `args: -kernel ...`, checked by hand).
     - **Stage 1: EGL offscreen, Glide (merged, #404).** Without an SDL window (PVE's VNC console,
       `-display none`, egl-headless, dbus, gtk, `sdl,gl=on`) qemu-3dfx's Glide device no longer
       ends QEMU: it has OpenGLide render offscreen and copies each frame into the first graphic
       console, which VNC and screendump show in place of the VGA; the VGA comes back when the
       Glide window closes. OpenGLide got an EGL platform
       (`packages/wsh-openglide/patches/0002-egl-offscreen.patch`, on top of Stage 0's 0001: a
       desktop GL compatibility context on Mesa's surfaceless EGL, else an EGL device or the
       default display; a framebuffer object whose two colour attachments are Glide's back and
       front buffers; `getOffscreenSize`/`getOffscreenFrame` exports), chosen by a new `setConfig`
       flag, so the same library serves the SDL/GLX path unchanged. qemu-3dfx side (`submodules/qemu-3dfx.patch`, new
       `hw/3dfx/fxdisp.c`): the choice per Glide window (offscreen unless the display is SDL
       without GL; `QEMU_3DFX_OFFSCREEN=1` forces it), the window opened and closed synchronously,
       `glReadPixels` after each swap on the vCPU thread (and after any call once the last read is
       50 ms old, for front-buffer drawing), a main-loop bottom half that copies the frame into a
       console surface of its own (`ui/console.c`'s pass-through flag keeps the VGA out); a library
       without the EGL platform, or an EGL failure, makes `grSstWinOpen` fail cleanly. No change to
       pve-qemu's own patch or to qemu-server: `vga: std,mesa=1` without `server=` already gets
       the 3dfx binary, VNC and (Stage 0) `OPENGLIDE_DIR`. Tested: the package test renders Glide 2 and 3 offscreen with no X
       server (llvmpipe and softpipe; the front-buffer read counts with both, unlike GLX on
       llvmpipe); `e2e/3dfx` with `GLIDE_DISPLAY=vnc` boots the Linux guest headless (no X server
       installed) and checks the frame in QEMU's screendump and the VGA's 720x400 afterwards;
       `qemu-3dfx-check.yml` runs it and the SDL run with the binary it builds (about 2 min each).
       Measured (TCG, llvmpipe, 640x480, the test scene): a read 0.14-0.2 ms, the console updated
       0.02-0.03 ms after it, the guest draws 1100-1750 frames/s offscreen against ~2100 with the
       SDL window. Left then: Glide gamma and MSAA offscreen; the Mesa pass-through on EGL; the
       last frame of front-buffer drawing waited for the next Glide call; a check through a PVE
       node (`qm start` with `mesa=1`, the noVNC console). Stage 1b took all but Glide MSAA and the
       node check.
     - **Stage 1b: EGL offscreen, Mesa/OpenGL (in review).** Without an SDL window the Mesa
       pass-through no longer ends QEMU at the guest's first `wglChoosePixelFormat`: a new
       `hw/mesa/mglcntx_egl.c` (in `submodules/qemu-3dfx.patch`) takes over `mglcntx_linux.c`'s
       entry points from the guest's DLL attach to its detach (one hook line each; the SDL/GLX path
       is unchanged) and renders on a desktop GL context of Mesa's surfaceless EGL (libEGL
       `dlopen()`ed), current on an EGL pbuffer the size of the guest's display. The pbuffer is the
       window, so the guest's framebuffer 0, `GL_BACK` and default viewport need no rewriting (an
       FBO would need `glBindFramebuffer(0)`, draw/read buffer and framebuffer queries
       intercepted). At each `wglSwapBuffers` the frame is read (`glReadPixels`, the guest's read
       and pack state put back) into `fxdisp`, now one instance per device with a read callback;
       `mesa_renderer_stat`/`mesa_gui_fullscreen` go through wrappers that switch the console's
       pass-through instead, so the VGA comes back when the guest deactivates its window or ends
       its context. `wglCreateContextAttribsARB`, ARB pbuffers, `wglUseFontBitmapsA` (built-in
       font) work offscreen; no libEGL, display or context fails `wglChoosePixelFormat`/
       `wglCreateContext` with a message, QEMU keeps running. Contained extras: gamma offscreen for
       both (OpenGL: `wglSetDeviceGammaRamp3DFX` kept and applied in fxdisp's copy; Glide:
       wsh-openglide's EGL platform keeps `grGammaCorrectionValue`/`grLoadGammaTable` and applies
       them in `getOffscreenFrame`, a change to `0002-egl-offscreen.patch`); the last frame of
       Glide front-buffer drawing is read 50 ms after the last call on that call's vCPU thread
       (`async_run_on_cpu` from a main-loop timer); OpenGL MSAA where a test pbuffer of the
       multisampled config gives its frame back (not llvmpipe: `glReadPixels` fails with
       `GL_INVALID_OPERATION` and a resolving blit returns black; softpipe has no such config;
       both then render without, with a message). No change to qemu-server: `mesa=1` without
       `server=` already gets the 3dfx binary and VNC, and the Mesa side needs no environment of
       its own. Tested (`e2e/3dfx`, `GLIDE_DISPLAY=vnc`, TCG, no X server, llvmpipe and softpipe):
       the Mesa guest's frame in the screendump, the gamma ramp's colour, the VGA back after; the
       Mesa guest again with a 4x pixel format, and with no EGL driver (its OpenGL fails, QEMU
       stays up); the Glide guest's front-buffer drawing reaching the console with no further call,
       and Glide gamma; the SDL runs unchanged. Measured (TCG, llvmpipe, 640x480): an OpenGL frame
       read 0.32-0.52 ms (it waits for the frame to finish rendering; 4-9 ms with softpipe), the
       console updated 0.03 ms after it, the Mesa guest draws 760-1840 frames/s offscreen
       (the lower end with a gamma ramp set; ~1800 with the SDL window); Glide unchanged (a read
       0.17-0.18 ms, 1100-1350 frames/s; ~2400 with the SDL window). Left:
       Glide MSAA offscreen; OpenGL MSAA on drivers without multisampled pbuffer reads; OpenGL
       front-buffer drawing without a swap; a display mode change while OpenGL frames show; the
       guest's OpenGL cursor offscreen; Glide on top of an active OpenGL window; a check through a
       PVE node with a Windows guest (`qm start` with `mesa=1`, the noVNC console).
     - **Stage 2: dmabuf scanout (Glide and MESA GL done, double-buffered, tested through PVE in Windows 98 and on an NVIDIA GPU node; left: AMD/Intel GPU nodes).** When QEMU's
       display has GL (`-display egl-headless`, `-display dbus,gl=on`), a Glide frame goes to the
       console as a dmabuf instead of being read back. wsh-openglide (new
       `packages/wsh-openglide/patches/0003-egl-dmabuf-scanout.patch`): a third renderbuffer of the
       window's size, exported once through `EGL_MESA_image_dma_buf_export` (`getOffscreenDmabuf`),
       and per frame a blit of the front buffer into it plus `glFinish` (`getOffscreenScanout`;
       unscaled and unflipped, which llvmpipe does as a memory copy, so the rows stay bottom up and
       the dmabuf says `y0_top`). A buffer of its own rather than the front buffer, so the next swap
       can't change a frame the display still reads. qemu-3dfx (`fxdisp.c`): the dmabuf way is chosen
       when the window opens, if the console has GL and the export works; the vCPU thread copies the
       frame unless the console is gl-blocked (a D-Bus client still reads the last one; the newest
       frame then follows 50 ms later through the existing stale timer), and a main-loop bottom half
       calls `qemu_console_gl_scanout_dmabuf` once and `qemu_console_gl_update` per frame. Everything
       that touches the console's GL state runs on the main loop (the vCPU thread has OpenGLide's
       context current), including giving the console back to the VGA: a GL scanout has no surface,
       and `vga_update_display()` dereferences it (QEMU crashed at the first close until the hand-back
       set a surface first). Readback stays for everything else: no GL display (PVE's default: VNC
       with `-display none`), a library without the exports, `QEMU_3DFX_DMABUF=0`, frames with a gamma
       ramp set (the copy applies none), and (in the first slice) all of MESA GL. Instead of the `gbm_surface` planned,
       the renderer exports its own buffer: the frames are rendered in OpenGLide's context, and the
       display imports from it, so nothing has to be imported into OpenGLide. QEMU side (in
       `submodules/pve-qemu-qemu-3dfx.patch`, the 3dfx binary only): without a render node
       `egl_rendernode_init()` falls back to Mesa's surfaceless EGL platform (llvmpipe exports and
       imports dmabufs through `/dev/udmabuf`), so both GL displays start on a node without a GPU;
       egl-headless honours a dmabuf's `y0_top` (it took every dmabuf as top down). Found on the way:
       an EGL platform display is one handle per process, so OpenGLide's and the MESA GL
       pass-through's `eglTerminate` at close destroyed QEMU's own display context (QEMU ended in
       libepoxy, "Couldn't find current GLX or EGL context"); neither terminates now, which also
       fixes Glide closing while a GL context is open. QEMU's `screendump` has no surface during a
       GL scanout ("Error: no surface"), so the tests read what VNC serves, or what the D-Bus client
       got. Tested (lab, TCG, llvmpipe, no render node, `/dev/udmabuf` passed to the container):
       `e2e/3dfx` with the new `GLIDE_DISPLAY=egl` (egl-headless, the frame checked as VNC serves it)
       and `GLIDE_DISPLAY=dbus` (dbus,gl=on with the test's own listener,
       `e2e/3dfx/dbus-listener.py`, which maps each dmabuf and writes the frame for the probes;
       `DBUS_DELAY_MS` delays its replies): the Glide guest's frame, front-buffer drawing (through
       the dmabuf) and gamma (read back), the VGA back after; the Mesa guest read back with both;
       `vnc` and `sdl` unchanged. Windows 98 SE (`win98-test.sh` with the new `--display egl` and
       `--openglide`, KVM, `cpu: pentium3`): Glide 2 and Glide 3 pass as dmabufs (the frame as VNC
       serves it, the desktop back at 1024x768; 0.07 ms a copy, 0.5-0.6 ms egl-headless's update;
       960-970 frames/s against 1540-1700 read back in the same run with `--display vnc`), OpenGL
       passes read back. Measured (640x480, the test scene, a lab under other load):

       | Display | Glide guest | vCPU thread per frame | main loop per frame |
       | --- | --- | --- | --- |
       | VNC, `-display none` (readback) | 1440-1790 frames/s | 0.14-0.16 ms `glReadPixels` | 0.02-0.03 ms copy |
       | egl-headless + VNC (dmabuf) | 830-1070 frames/s | 0.07 ms copy and `glFinish` | 0.57-0.78 ms (egl-headless imports, blits and reads the frame for VNC) |
       | dbus,gl=on (dmabuf), listener replies at once | 2140 frames/s | 0.07 ms | 0.04 ms; 152 of 306 frames held while the client read |
       | dbus,gl=on, listener replies 2 ms late | 2630 frames/s | 0.08 ms | 0.04 ms; 256 held |

       With egl-headless the frame still goes through system memory for VNC (egl-headless reads it
       on the main loop, under the BQL), which costs more than the readback with Mesa's software
       renderer; the dmabuf way pays off where the consumer takes the dmabuf itself (D-Bus, stage 3)
       or on a GPU, where `glReadPixels` stalls the pipeline.
       Second slice (in review): MESA GL as a dmabuf (`hw/mesa/mglcntx_egl.c`, `egl_export` and
       `egl_scanout`, registered through the same `fxdisp_dmabuf`, so the bottom half, the
       back-pressure and the readback fallback are #425's). The copy runs in a GL context of
       mesapt's own, created on the guest's config without sharing, and made current on the
       guest's window pbuffer only for the copy: it reads framebuffer 0 directly, so no object of
       ours lands in the guest's namespace (a legacy GL guest may bind names it never got from
       `glGen*`) and none of the guest's state (scissor, read buffer, framebuffer bindings,
       `GL_FRAMEBUFFER_SRGB`, pack state) has to be saved and put back; it costs two
       `eglMakeCurrent` (0.03 ms) and a `glFinish` in the guest's context, as another context
       reads the frame. Per frame: a blit of the back buffer (the front one when single-buffered)
       into a renderbuffer exported once through `EGL_MESA_image_dma_buf_export`, unscaled and
       unflipped (rows bottom up, `y0_top` as for Glide), then `glFinish`. With a gamma ramp the
       copy is two passes, the frame into a texture and a draw through a 256x1 lookup texture (a
       12-line GLSL 1.20 shader, the same lookup the readback applies), so ramp frames stay
       dmabufs. A pbuffer has no swap, and the guest draws its next frame into the same back
       buffer, so a frame held while a D-Bus client is busy would be half overwritten by the time
       the stale timer takes it: fxdisp gains a hold callback (`fxdisp_hold`, called at a swap
       whose frame is held), with which mesapt copies the frame into a second renderbuffer, and
       the scanout that follows copies from there. Readback stays for MESA GL with no GL display,
       `QEMU_3DFX_DMABUF=0`, an EGL display without the export, a multisampled window (a
       resolving blit needs identical formats; llvmpipe never gets one, `egl_msaa_works`, so it
       is untested), and ramp frames if the shader can't be built. Tested (lab, KVM, llvmpipe,
       `/dev/udmabuf`): `e2e/3dfx` `egl`, `dbus` and `dbus` with `DBUS_DELAY_MS=2`: the Mesa
       guest's probes match as VNC serves them and as the D-Bus listener maps them, its gamma
       phase arrives as a dmabuf with the ramp (`#0000b5`), every frame went as a dmabuf, the
       VGA comes back after; `egl` with `QEMU_3DFX_DMABUF=0` reads both guests back (the test now
       checks that); `vnc` and `sdl` unchanged; Glide unchanged. Windows 98 SE (`win98-test.sh
       --display egl --openglide`, KVM): OpenGL passes as a dmabuf (0.87-1.09 ms a copy, 600-770
       frames/s against 2200 read back with `--display vnc`), Glide 2 and 3 still pass as dmabufs;
       the harness's summary now says per window how many frames went as a dmabuf. Measured (640x480, the test
       scene, KVM, a lab under other load; the bench without a gamma ramp unless noted):

       | Display | Mesa guest | vCPU thread per frame | main loop per frame |
       | --- | --- | --- | --- |
       | VNC, `-display none` (readback) | 357 frames/s (359 with a ramp) | 0.65 ms `glReadPixels` (0.45 with a ramp) | copy, 0.03-0.04 ms to the console |
       | egl-headless + VNC, `QEMU_3DFX_DMABUF=0` | 448 frames/s (395 with a ramp) | 0.39 ms (0.36) | as above, plus egl-headless's upload |
       | egl-headless + VNC (dmabuf) | 326 frames/s (253-310 with a ramp) | 0.81-0.98 ms (1.19-1.55 with a ramp) | 0.75-0.98 ms |
       | dbus,gl=on (dmabuf), listener replies at once | 326 frames/s (364 with a ramp) | 1.11 ms (1.23) | 0.05-0.08 ms; 5-8 frames held |
       | dbus,gl=on, listener replies 2 ms late, with a ramp | 405 frames/s | 1.21 ms | 0.06 ms; 157 of 302 held |

       The copy costs more than the readback on llvmpipe. Instrumented (egl-headless, no ramp):
       0.35 ms waiting for the guest's frame (`glFinish`; the readback waits as long), 0.03 ms
       for the two context switches, 0.6 ms for the blit and its `glFinish`: llvmpipe converts
       the pbuffer's pixel format into the `GL_RGBA8` renderbuffer by drawing (no renderbuffer
       format gave its memcpy path, and desktop GL has no BGRA8 one), where Glide's
       renderbuffer-to-renderbuffer blit is a 0.06 ms memcpy. On a GPU it is a GPU blit.
       Third slice (in review): Glide gamma ramps as dmabufs, and EGL fences for the copies.
       wsh-openglide 0.6 (`0003-egl-dmabuf-scanout.patch`): with a ramp set, `getOffscreenScanout`
       copies through it instead of refusing: in a second EGL context that shares OpenGLide's
       objects (its renderbuffers) but not its state, so nothing of OpenGLide's (texture units,
       enables, blend, viewport, client arrays) is saved or touched, the front buffer goes into a
       texture and is drawn into the scanout buffer through a 256x1 lookup texture (mesapt's GLSL
       1.20 shader), unflipped (`y0_top` as before); the plain blit stays for frames without a
       ramp, and the readback's CPU lookup is unchanged. Only when that pass can't be had (no
       context, no shader) is a ramp frame refused and read back; qemu-3dfx's `fxdisp.c` needed no
       change (it reads back whatever the scanout refuses). The copies of wsh-openglide and mesapt
       (the guest's frame before mesapt's context reads it, and each copy before the display reads
       it) are finished with an `EGL_KHR_fence_sync` fence and `eglClientWaitSyncKHR` (flush bit,
       no timeout), `glFinish` without the extension; a wait in the GL stream (`eglWaitSyncKHR`)
       is left for a GPU node, since a context reading another's rendering needs it done and the
       software renderers can't be relied on to wait in the stream. llvmpipe has the extension,
       so the fences are used (QEMU's log says which). Tested (lab, TCG, llvmpipe,
       `/dev/udmabuf`): the package test's new `glide-render --egl --dmabuf` maps the exported
       dmabuf and compares it with `getOffscreenFrame`, all 307200 pixels equal without a ramp,
       with gamma 2.0 (`#0000b5` top left), with a Glide 3 table of a different ramp per channel
       (`#00ff40`) and after the reset; `e2e/3dfx` `egl`, `dbus` and `dbus` with
       `DBUS_DELAY_MS=2`: every Glide frame as a dmabuf ("0 frames read back instead"), the gamma
       phase's too, its probes `#0000b5` and, new, `#939294` in the Gouraud triangle (a frame
       upside down fails); `egl` with `QEMU_3DFX_DMABUF=0` and `vnc` read back with the same
       colours; the Mesa guest unchanged. Measured (640x480, the test scene; `GLIDE_GUEST_BENCH=3000`
       with the new `GLIDE_GUEST_BENCH_GAMMA=1`, which keeps gamma 2.0 for the bench):

       | Glide guest, gamma 2.0 | before (0.5: ramp frames read back) | after (0.6: dmabuf) |
       | --- | --- | --- |
       | egl-headless + VNC | 1150 frames/s, 0.39 ms read, egl-headless's update 7.1 ms | 707 frames/s, 0.44 ms copy, update 0.54 ms |
       | dbus,gl=on, listener replies at once | 833 frames/s, 0.40 ms read | 1590 frames/s, 0.42 ms copy, update 0.04 ms |
       | VNC, `-display none` | 1120 frames/s, 0.39 ms read (unchanged) | |

       With egl-headless the readback still wins on llvmpipe (egl-headless reads the dmabuf back for
       VNC anyway), as for MESA GL. The gamma pass costs 0.44 ms against the plain blit's 0.07 ms
       (two `eglMakeCurrent`, the front buffer into a texture, a draw through the lookup), and its
       first frame builds the shader (about 40 ms once, estimated from the averages). The fences changed nothing measurable on
       llvmpipe: Glide's plain copy 0.07 ms before and after, mesapt's copy 1.1-1.8 ms before and
       1.1-1.4 ms after, within the lab's run-to-run spread.
       GPU node (in review): an NVIDIA GTX 1080 test node (proprietary driver 580, TCG) with the
       published pve-qemu-kvm 11.1.3-4+wsh11 and wsh-openglide 0.6. It needs `nvidia_drm modeset=Y`:
       with `modeset=N` NVIDIA's GBM backend doesn't start and its EGL advertises
       `EGL_MESA_image_dma_buf_export`, but `eglExportDMABUFImageMESA` fails (`EGL_BAD_MATCH`), so
       QEMU's display ends up on Mesa's llvmpipe and every frame is read back (correct frames, no
       crash). With `modeset=Y` the export works (`AB24`, stride 2560, NVIDIA's block-linear
       modifier `0x300000000cdb014`), egl-headless runs on the GPU and imports the block-linear
       buffers, every Glide and MESA GL frame goes as a dmabuf, the copies are finished with an
       `EGL_KHR_fence_sync` fence, and the Glide gamma pass runs on the GPU with the right colours;
       a PVE VM with `vga: std,mesa=1,mesa-display=egl-headless` passes (VNC, 6/6 probes). Measured
       (3000 frames, TCG, frames/s): Glide egl-headless 3502 (the lab's llvmpipe 1150, the GPU read
       back 956), Glide with gamma 2.0 egl-headless 2516 (llvmpipe 707, GPU read back 775), MESA GL
       egl-headless 1018 (GPU read back 678); through PVE 200000 Glide frames at 3748 frames/s, all
       as dmabufs, 0.10 ms a copy (0.28 ms with the gamma pass). So on a GPU egl-headless is the
       faster choice, unlike on llvmpipe. The harness learned block-linear buffers: the D-Bus
       listener and `glide-render --dmabuf` import a dmabuf that isn't linear through EGL
       (`EGL_EXT_image_dma_buf_import_modifiers`, `glReadPixels`) instead of mapping it, and say
       "pixel probes skipped" / "not verified" where that import fails (on the GTX 1080 both
       imports work: `glide-render --dmabuf` finds all 307200 pixels equal to `getOffscreenFrame`
       without and with ramps, and `e2e/3dfx` `dbus` passes with its probes); the `egl`/`dbus` gate of
       `e2e/3dfx/test.sh` looks for the scanout's printf format, since the published binary holds
       "...as a dmabuf (no readback)" only in overlapping pieces (glib's inline `g_strdup` becomes a
       memcpy of two overlapping loads), so those modes no longer skip against published packages.
       Containers on that node: `docker --gpus all` failed (`nvidia-container-cli`, a driver
       installed with `nvidia-installer`), so the tests ran with the NVIDIA devices and EGL/GBM
       libraries and their glvnd/GBM json files mounted by hand, `--security-opt
       apparmor=unconfined` (the host's `docker-default` profile denies the AF_UNIX sockets of Xvfb
       and QEMU's monitor) and `--init` (QEMU's `-daemonize` leaves a zombie otherwise).
       Left: AMD and Intel GPU nodes (untested; there is no such node). Follow-ups outside Stage 2:
       `docker --gpus all` on a node whose driver came from `nvidia-installer` (the NVIDIA container
       toolkit's driver RPC failed); Windows 98 with dbus,gl=on (the harness has no D-Bus client
       yet, so it belongs with stage 3's client) and a real game over time; the D-Bus listener's
       30 ms refresh cap. Done since (fourth slice, below): the held OpenGL frame, double
       buffering, the wait in the GL stream, and the checks after its merge ("Checked with the
       published packages", below): Windows 98 with the held frame, and a PVE VM on the GPU node.
       Settled since: GitHub's runners have
       `/dev/udmabuf` (`qemu-3dfx-check.yml` ran the `egl` and `dbus` modes there, all frames as
       dmabufs, run of 2026-11-22); the published wsh-openglide has had the exports since 0.5 (cut
       from #425 itself, 2026-11-21; the `3dfx in Windows 98` runs that read Glide back predate it),
       and the Windows 98 runs through PVE below sent Glide as dmabufs with the published packages.
       Fourth slice (in review): a held OpenGL frame stays, double buffering, and a wait in the GL
       stream. The OpenGL frame that went back to the VGA about 4 s after the last swap was
       upstream's display timer: the guest wrapper passes `DispTimerMS` (2000 ms unless its config
       says otherwise, `DISPTMR_DEFAULT`), mesapt re-arms a timer at every swap,
       `glFlush`/`glFinish` and `wglMakeCurrent`, and when it fires `MGLActivateHandler(0, 1)`
       schedules a deactivation for another `DispTimerMS` later, which ends in `MGLRendererStat(0)`
       and, offscreen, `fxdisp_renderer(0)`: the VGA. With an SDL window that is upstream's design
       and stays; offscreen (`MGLEglActive()`) the deferred deactivation is now ignored, and QEMU
       says so once per pause ("offscreen: no swap for 2000 ms, the frame stays ..."). The console
       still goes back at the guest's `WM_ACTIVATE` (the wrapper's hook, 0xFD8; Windows also sends
       it when the active window is destroyed), `wglDeleteContext` and the DLL detach. The Mesa
       guest of `e2e/3dfx` gains `MESA_GUEST_HOLD=<s>`: the wrapper's default timer, the first frame
       held for `<s>` seconds (`HELD`, probed at 7 s: the frame's #000080), then the wrapper's
       `WM_ACTIVATE` with `WA_INACTIVE` (`DEACTIVATED`: the VGA's #000000), then the gamma phase
       shows frames again; `test.sh` runs it headless when the binary has the message. With the
       published 11.1.3-4+wsh12 the `HELD` probe found the VGA (#000000), as in Windows 98. Double
       buffering: `fxdisp.c` takes two exported buffers per window (`fxdisp_dmabuf(..., nbuf)`, the
       export and scanout callbacks take the buffer's index). A frame is copied into the buffer the
       console has as long as the display is done with it (egl-headless reads it within its update;
       switching would cost egl-headless a new import and a D-Bus client a new file descriptor), and
       into the other one while the console is gl-blocked (a D-Bus client still reads the last
       frame), each new frame replacing the one waiting there; the waiting frame goes as soon as the
       client replies (a 1 ms main-loop poll instead of the 50 ms stale timer). wsh-openglide 0.8
       (`0003-egl-dmabuf-scanout.patch`): `getOffscreenDmabufAt(i, ...)` and
       `getOffscreenScanoutAt(i)` for two scanout buffers
       (`getOffscreenDmabuf`/`getOffscreenScanout` are buffer 0; with an older library qemu-3dfx
       keeps one buffer and the held frames of before). mesapt: two renderbuffers, and the hold copy
       (`egl_hold`, its stage renderbuffer, `fxdisp_hold`) is gone, as no frame has to wait in the
       guest's back buffer any more. Readback and the no-GL paths are unchanged. `glide-render --egl
       --dmabuf` checks the second buffer too (gamma 2.0, all 307200 pixels equal to the read) and
       that buffer 0 still holds its last frame after a copy into buffer 1; `e2e/3dfx` checks that
       both guests are double-buffered with egl-headless and dbus,gl=on. A wait in the GL stream:
       where a context of ours reads another context's frame (mesapt's copy context reading the
       guest's pbuffer, wsh-openglide's gamma context reading OpenGLide's front buffer) the producer
       now flushes a fence and the consumer waits for it with `eglWaitSyncKHR` (`EGL_KHR_wait_sync`)
       instead of the CPU waiting; the copy itself is still finished on the CPU before the display
       gets it, since the display reads it from a context of its own and QEMU passes it no fence. On
       when the extension is there and the renderer is not Mesa's llvmpipe or softpipe (which don't
       all wait in the stream); `QEMU_3DFX_WAIT_SYNC=1` or `0` decides instead; the client wait and
       `glFinish` stay as fallbacks. Tested (lab: KVM, llvmpipe, `/dev/udmabuf`, under other agents'
       load; an NVIDIA GTX 1080 test node: TCG, driver 580, `nvidia_drm modeset=Y`, idle, load
       average about 1): `e2e/3dfx` `egl`, `dbus` (also with `DBUS_DELAY_MS=2` and `10`), `vnc`,
       `egl` with `QEMU_3DFX_DMABUF=0`, `sdl` on the lab; `egl`, `dbus` with `DBUS_DELAY_MS=2` and
       `vnc` on the GPU node; the package test (`glide-render --dmabuf`) on the lab. Measured (3000
       frames of the test scene, `GLIDE_GUEST_BENCH=3000`; before: the published pve-qemu-kvm
       11.1.3-4+wsh12 and wsh-openglide 0.7, after: this change; frames/s of the guest, then the
       D-Bus listener's updates):

       | Run | Glide before | Glide after | MESA GL before | MESA GL after |
       | --- | --- | --- | --- | --- |
       | lab, dbus,gl=on, listener replies at once | 773 fps, 1489 updates (1557 held) | 923 fps, 1637 updates (1613 waited, 117 replaced) | 182 fps, 2909 updates | 167 fps, 3055 updates |
       | lab, dbus,gl=on, `DBUS_DELAY_MS=2` | 564 fps, 895 updates (2231 held) | 656 fps, 937 updates (2282 waited, 1486 replaced) | 222 fps, 1649 updates (1532 held) | 169 fps, 2958 updates (2943 waited, 91 replaced) |
       | lab, dbus,gl=on, `DBUS_DELAY_MS=10` | 1773 fps, 278 updates (2883 held) | 1225 fps, 324 updates (2653 replaced) | 307 fps, 761 updates | 273 fps, 992 updates (2000 replaced) |
       | GPU node, dbus,gl=on, `DBUS_DELAY_MS=2` | 15787 fps, 300 updates (2886 held) | 2692 fps, 428 updates (2343 replaced) | 2776 fps, 445 updates (2751 held) | 1250 fps, 710 updates (2027 replaced) |
       | GPU node, egl-headless | 1040 fps | 1552, 1492 fps | 481 fps | 535, 534 fps |

       With a D-Bus client that is busy, more of the guest's frames reach it (the listener's
       updates), as the newest frame is ready when the client replies instead of up to 50 ms later;
       the guest's own rate goes down where it used to skip the copies of held frames (on the GPU
       node a held Glide frame cost nothing, so the guest drew 15787 frames/s of which the client
       got 300), and with llvmpipe a MESA GL copy costs 2-3 ms. Before, mesapt copied a held frame
       twice (the hold copy, then the scanout), now once. egl-headless gains nothing from the second
       buffer and isn't slowed by it (the lab's egl-headless runs, three each: Glide 465-690
       frames/s before, 306-753 after, MESA GL 204-257 before, 118-247 after, the low ones in one
       run under the heaviest load). The wait in the GL stream on the GPU node: Glide with gamma 2.0
       (the gamma pass's hop) 0.33-0.40 ms a copy and 1063-1388 frames/s with the wait, 0.38-0.52 ms
       and 939-1276 frames/s without (three runs each); MESA GL's copy 0.55-0.61 ms with it,
       0.61-0.74 ms without. The GPU node's egl-headless Glide rate of #480 (3502 frames/s) wasn't
       reached on this day with either build (1040 before, 1492-1552 after).
       Checked with the published packages (after #489): pve-qemu-kvm 11.1.3-4+wsh16 (its 3dfx
       binary's `--version` says +wsh15) and wsh-openglide 0.8, on the lab also the same code built
       from the branch. The Windows 98 harness gains a check of the held frame: with `--hold 6` or
       more it takes a second picture 1.5 s before the hold ends and fails a frame that is gone
       (summary column "Held frame"); its summary also says which windows were double-buffered and
       how often QEMU kept a held OpenGL frame. Windows 98 SE, `--hold 9`, KVM, `cpu: pentium3`:
       on the lab (llvmpipe, `/dev/udmabuf`) Glide 2, Glide 3 and OpenGL pass with `--display egl`
       (every frame as a dmabuf, double-buffered; 876, 833 and 819 frames/s, copies 0.08, 0.08 and
       0.66 ms), `--display vnc` (read back) and both through PVE (`--pve`, the e2e PVE container),
       each frame still in the console 7.5-8.2 s after its swap; the published +wsh12 fails the
       OpenGL frame with egl-headless (gone at 7.7 s), so the check sees the old fault. On the
       NVIDIA GPU node, a PVE VM made with `qm create`/`qm start` on the node itself (`vga:
       std,mesa=1,mesa-display=egl-headless`, KVM): Windows 98 passes Glide 2, Glide 3 and OpenGL
       twice, every frame as a block-linear dmabuf on the GPU, double-buffered, the held frames
       kept (433-1460, 1623-2237 and 431-1250 frames/s; read back, `mesa-display` unset: 867, 474
       and 600); the e2e/3dfx Linux guests in a VM with the guest as `-kernel`/`-initrd` through
       `args` (TCG, 3000 frames): QEMU says "frames to the graphic console as a dmabuf" and
       "double-buffered", has two dmabufs open (`/proc/<pid>/fdinfo`, `exp_name: drm`; one with
       +wsh12), Glide 675-1676 frames/s with egl-headless against 545 read back, MESA GL 600-697
       against 760-836. Why #480's 3502 doesn't come back: the rate on that node follows the GPU's
       clocks and the host. The GTX 1080 runs one 640x480 stream in P5 (734 MHz core, 810 MHz
       memory, 50-65% busy), falls to P8 (139-227 MHz, 405 MHz memory) during the guest's 5 s hold
       before its benchmark and is in P0 (1657/5005 MHz) only around a VM's start; a 30000-frame
       benchmark settles in P5 (+wsh12: 1516 frames/s egl-headless, 652 read back; +wsh16: 882 and
       545 later in the day); the node is a VM (CPU steal up to 18% seen) whose load went from 0.1
       to 1.5 during these runs. With the same binary the Glide rate varied up to 5x: in
       alternating runs of +wsh12 (with wsh-openglide 0.7) and +wsh16 (0.8) outside PVE, twelve
       pairs, the old one gave 436-2354 frames/s (median 683), the new one 478-1135 (median 700),
       the new one faster in 7 of 12, runs that fell to P8 during the benchmark among the slowest;
       so double buffering isn't the cause, and 3502 is the top of the spread. Persistence mode is
       off on the node, but QEMU keeps the GPU open for the whole run; fixed clocks (`nvidia-smi
       -lgc`) would make such numbers comparable and weren't tried (a host setting).
       - **PVE: the display of a 3dfx VM (merged, #431).** qemu-server: `vga: ...,mesa=1,mesa-display=`
         `none|egl-headless` (default `none`: no `-display`, frames read back, as before);
         `egl-headless` adds `-display egl-headless` next to PVE's `-vnc`, so noVNC keeps working.
         Refused at create and update without the 3dfx binary (`mesa=1` on the host's
         architecture), with a `server` (SDL) or without a VNC console (`none`, `serial*`); refused at
         start on a node with neither a render node nor `/dev/udmabuf`, where QEMU would stop anyway
         (Mesa then has no `EGL_MESA_image_dma_buf_export`: "egl: render node init failed").
         QEMU runs as root in its systemd scope, with no device policy, so `/dev/udmabuf` (root:kvm
         0660) needs no udev rule; Ubuntu kernels build it in (`CONFIG_UDMABUF=y`). `dbus,gl=on` was
         not offered here: QEMU refused VNC next to it ("Display vnc is incompatible with the GL
         context"), so PVE's console would have gone; stage 3a adds it as `mesa-display=dbus`, with
         a QEMU patch that keeps VNC (below). pve-manager: **3DFX/Mesa display** in the Display dialog, under **Enable
         3DFX/Mesa** and only while it's checked. Tested (lab PVE container, no GPU, `/dev/udmabuf`,
         TCG): cfg2cmd and unit tests, the e2e Playwright tests (`qm showcmd`, refusals, the
         dialog) and `e2e/tests/3dfx-gl-display.spec.ts`, which boots the Glide guest of
         `e2e/3dfx/test.sh` through `qm start` (`e2e/3dfx/pve-guest-setup.sh` puts it in the
         container) and checks the frame in the noVNC console, read back and with egl-headless (4
         open dmabufs against 1); QEMU, run with PVE's command line in the foreground, said "frames
         to the graphic console as a dmabuf" (944 frames/s). Left: AMD and Intel GPU nodes (an
         NVIDIA one passes, Stage 2's "GPU node"). Done since (see the
         Done table): Windows 98 through PVE with egl-headless, the frame spec in CI, and the PVE
         kernel's `CONFIG_UDMABUF` (`=y` in the published configs of `proxmox-kernel-7.0.14-30-pve`,
         the default, and `7.3.5-1-pve`).
     - **Stage 3: the streaming client (~3-4 weeks).** A D-Bus listener in the Wolf/Sunshine
       container imports the dmabuf into the encoder; input through the D-Bus Keyboard/Mouse
       interfaces.
     - D-Bus display, found so far: `-display dbus` is in the package already and works without GL
       on VGA, cirrus, cg3 and TCX; its 30 ms refresh cap needs a small QEMU patch; the bus name
       `org.qemu` is fixed, so one dbus-daemon per VM; a dmabuf streamer must run on the same
       kernel (the host or an LXC).
     - **Stage 3a: the D-Bus display from PVE (in review).** pve-qemu `wsh/0130`: with
       `-display dbus,gl=on` a listener without GL (VNC) is accepted; the D-Bus console's own
       listener reads the GL scanout (texture or dmabuf, imported into QEMU's EGL context, `y0_top`
       honoured) into the console's surface at the display refresh after a GL update, only while
       such a listener exists, and tells only the listeners without GL
       (`qemu_console_update_2d()`, new in `ui/console.c`), so D-Bus clients get no extra updates.
       Once per refresh, not per frame as egl-headless. All of it is under `CONFIG_OPENGL` (the
       dmabuf release under `CONFIG_GBM` as well, as meson finds GBM without OpenGL): built with
       `--disable-opengl` and the D-Bus display on (a minimal sparc64 build), the D-Bus console is
       upstream's. `wsh/0131`: `-display dbus,refresh-ms=N`
       (1-3000; each client's listener gets that interval). `wsh/0132`: qtests (the option in
       `query-display-options`, a listener registered on such a display). The 3dfx port
       (`wsh/0099`) applies unchanged. qemu-server: `vga: ...,display=dbus` (std, cirrus, vmware,
       virtio, tcx, cg3; sparc32 and sun4u included), `mesa-display=dbus` (the same with `gl=on`,
       3dfx binary, render node or `/dev/udmabuf`), `dbus-refresh=<ms>`, `audio0: driver=dbus`
       (`-audiodev dbus`, tied with `audiodev=`), `-vnc` kept. The VM's bus: the systemd unit
       `wsh-dbus-display@<vmid>` (a `dbus-daemon` with `/usr/share/qemu-server/dbus-display.conf`,
       shipped by qemu-server, which also creates the group `wsh-display`) on
       `/run/wsh-dbus-display/<vmid>.sock` (directory `root:wsh-display 0750`, which keeps others
       from the socket dbus-daemon makes 0777; root owns `org.qemu`, root and the group may connect and call it), started before QEMU, stopped
       at the cleanup. pve-manager: **D-Bus display** and **D-Bus refresh (ms)** in the Display
       dialog, `D-Bus` among the audio drivers. Tested (lab, TCG, llvmpipe, `/dev/udmabuf`): the
       qtests; cfg2cmd (5 commands, 7 refusals) and unit tests (`run_dbus_display_tests.pl`, the
       unit start/stop mocked); `e2e/3dfx` `GLIDE_DISPLAY=dbus DBUS_PICTURE=vnc` with the 3dfx
       binary built from the series: Glide and Mesa guests pass every probe (frame, front buffer,
       gamma, held frame, VGA back) in the picture VNC serves while the D-Bus listener maps every
       dmabuf; without GL, a guest changing VGA text memory every few ms gave the listener 33.6
       refreshes/s by default, 61.6 with `refresh-ms=14`, 125 with 5 (loaded host); QEMU kept
       running and VNC answering after the client and then the dbus-daemon were SIGKILLed; sound:
       wisp's `soundtest 440 1000` (framebuffer kernels) put 1.01-1.02 s of 44.1 kHz stereo on an
       `AudioOutListener` from AC97 (x86) and from the SS-5's CS4231. Through PVE (the e2e container
       with these qemu-server and pve-manager debs and the series' QEMU binaries, `/dev/udmabuf`):
       `qm start` of an x86 (`std,display=dbus,dbus-refresh=14`, AC97 on `dbus`), an SS-5 (`cg3`,
       CS4231 on `dbus`), a sun4u (`std`) and a 3dfx (`mesa-display=dbus`, surfaceless EGL) VM:
       each bus active before QEMU, `busctl tree org.qemu` shows `Console_0` (and `Audio`), PVE's
       VNC socket answers; a member of `wsh-display` (not root) registered the test listener on
       the x86 VM (pixels, the audio stream's `Init`) and on the 3dfx VM (the VGA as dmabufs);
       `nobody` can't connect, the group can't own `org.qemu`; the bus killed, the VM and VNC go
       on; `qm stop` stops the bus and removes the socket. The Playwright specs
       (`e2e/tests/dbus-display.spec.ts`, the UI test in `ui-hardware.spec.ts`) were written but
       not run (no Playwright on the lab; their steps were run by hand there). Found: QEMU blocks its main
       loop while it sets up a listener's peer connection (it calls the client's properties
       synchronously), so a client must keep its own main loop running across `RegisterListener`
       and `RegisterOutListener` (the test listener registers the audio asynchronously); the
       `RegisterOutListener` reply can come late. Not verified: a GPU node with `dbus,gl=on`
       (the NVIDIA node was busy), a client in an LXC (uid mapping onto `wsh-display`), migration
       of a VM with the D-Bus display (the bus is per node; not tried), the GL scanout's cursor
       (not blended into VNC's picture).
     - **Stage 3b: qemu-rdp (in review).** The optional package `wsh-qemu-rdp`
       (`packages/wsh-qemu-rdp`): qemu-rdp from qemu-display `8ac3da9` (2026-06-04, the last
       commit whose qemu-rdp takes every crate from crates.io; later ones take IronRDP and
       usbredir-proto from git for USB redirection), crates through `cargo vendor`, built offline
       with Debian 13's `rustc-web` 1.96 (ironrdp 0.15 needs 1.89). Patches: the workspace cut to
       qemu-rdp (0001), the commit in `--version` (0002), `--credentials-file` and the bus name
       `org.QemuDisplay.RDP` optional (0003: the VM's bus lets nobody but root own a name, and
       upstream stopped without it), relative mouse motion when the guest's mouse isn't absolute
       (0004: PS/2, the Sun mouse). The unit `wsh-qemu-rdp@<vmid>` (user `wsh-qemu-rdp` in
       `wsh-display`, sandboxed, `BindsTo`/`WantedBy` the VM's bus unit, so once enabled it starts
       and stops with `qm start`/`qm stop`), `/etc/wsh-qemu-rdp/<vmid>.conf` written at the first
       start (127.0.0.1, port 20000 + VMID, user `rdp`, a generated password), a self-signed node
       certificate; NLA only (qemu-rdp refuses clients without credentials). qemu-server: the
       audio driver `dbus` gets `out.frequency=48000` (qemu-rdp has only 48 kHz formats and passes
       QEMU's samples unconverted: at 44.1 kHz it dropped every buffer). CI (`wsh-qemu-rdp.yml`,
       `test.sh`): wisp's framebuffer kernels on x86 (AC97, PS/2) and the SS-5 (cg3, CS4231) with
       the published pve-qemu-kvm, FreeRDP 3 on Xvfb. Lab, also through PVE (`qm start` of both
       VMs): login (wrong password refused), picture identical to QEMU's screendump (1280x800 and
       1024x768, about 0.2 s after the guest drew it), the window following the guest's modes
       (640x480, 720x400, 1280x800), keys in the guest in 15-17 ms, mouse buttons and relative
       motion in QEMU's input layer (the published wisp-fb kernel has no `mousetest`), sound: a
       440 Hz tone of 2.0 s (x86) and 1.8-2.0 s (SS-5) through rdpsnd/Opus at 437-438 Hz; qemu-rdp
       ends with QEMU (also after a SIGKILL, through PVE's cleanup). Found: the bus policy rejects
       QEMU's calls to the client (`Clipboard.Register`), so no clipboard. Not verified: Windows'
       or Remmina's client, a guest that acts on the client's size (virtio-gpu), absolute pointer
       motion in a guest, frame rates under load, a client over a real network.
     - **Stage 3c, first slice: GStreamer sources and the input bridge (in review).** The optional
       package `wsh-gst-qemu-dbus` (`packages/wsh-gst-qemu-dbus`), our own code in C with GLib/GIO
       and Debian 13's GStreamer 1.26 (meson): qemu-display's Rust crates would have brought a zbus
       runtime and gstreamer-rs to vendor, while GStreamer and QEMU's D-Bus display are both GLib and
       GIO's D-Bus covers the listener protocol in a few hundred lines. The plugin `qemudbus`:
       `qemudbussrc` registers a listener on `Console_<n>` of the VM's bus (`address=` or `vmid=`),
       on a thread and main context of its own, and outputs the console as raw video in its own
       format (BGRx), one buffer per change, live with a variable frame rate, renegotiating on mode
       changes, EOS when QEMU closes the connection. It takes `Scanout`/`Update` (pixels),
       `ScanoutMap`/`UpdateMap` (the surface in shared memory, offered unless `shared-map=false`) and
       `ScanoutDMABUF`/`UpdateDMABUF`: a linear dmabuf is mapped and the changed part copied out
       before the reply, so QEMU's gl-block lasts a copy, not the pipeline. `qemudbusaudiosrc`
       registers an `AudioOutListener`, follows one stream, outputs its PCM (S16LE 48 kHz stereo from
       qemu-server's driver) with continuous timestamps, and applies the guest mixer's volume and
       mute, which QEMU passes separately (`apply-volume`). Found: QEMU sets up a listener's peer
       connection and reads its `Interfaces` property synchronously, blocking its main loop, so the
       client's end authenticates asynchronously with message processing held until the object is
       registered. `qemu-dbus-input` reads `key CODE 1|0` (Linux key codes, mapped to QEMU's key
       numbers), `qkey`, `btn`, `wheel`, `rel`, `abs X Y [W H]`, `query`, `sync` on standard input
       and sends them to `Keyboard`/`Mouse`; QEMU refuses absolute positions for a relative pointer
       and relative motion for an absolute one, so the bridge converts (rel moves its own pointer on
       a tablet, abs becomes the difference on a PS/2 or Sun mouse) and prints mode changes. CI
       (`wsh-gst-qemu-dbus.yml`, `test.sh`): the published pve-qemu-kvm runs wisp's framebuffer
       kernels with the D-Bus display on a bus with qemu-server's policy, the clients run as a member
       of `wsh-display`: x86 (std VGA, PS/2, AC97, the shared map), aarch64 virt (bochs-display,
       virtio tablet, AC97, `shared-map=false`), the SS-5 (cg3, CS4231, Sun mouse) and x86 in the
       3dfx binary with `dbus,gl=on` (llvmpipe, `/dev/udmabuf`); `gst-launch-1.0 qemudbussrc ! videoconvert ! multifilesink` and
       `qemudbusaudiosrc ! wavenc`. Lab, also through PVE (`qm start` of a `display=dbus` and a
       `mesa-display=dbus` VM, TCG): the newest frame identical to QEMU's screendump (1280x800, 0 of
       1,024,000 pixels differ) on every path; `UpdateDMABUF` answered in 0.07-0.08 ms on average and
       at most 0.6-0.8 ms; keys (30, 48, 1) in the guest 5.1-10.6 ms after the line reached the
       bridge; PS/2 and Sun mouse motion exact (+40, +25 from `rel 10 5` and two `abs`), virtio tablet absolute X
       16383 then 16639 of 32767 (`abs 640 400`, `rel 10 0` on 1280x800); a 2.00 s tone at 440.0 Hz in
       the WAV; the pipeline ends by itself when QEMU quits. `e2e/3dfx/test.sh` takes another listener
       (`DBUS_LISTENER`): with `tests/gst-listener.py` (qemudbussrc and an appsink) the Glide and Mesa
       guests pass every probe in qemudbussrc's frames, double-buffered dmabufs, the held frame and
       the VGA back. 3000-frame benches on a host other jobs kept busy (so the rates swing): Glide
       493.6 frames/s with qemudbussrc (1806 updates reached it, 58.8/s; replies 0.39 ms on average,
       at most 14 ms) against 248.5 with `dbus-listener.py`; Mesa 542 and 614 frames/s (replies 0.22-
       0.24 ms on average, at most 1.9 ms; `DMA_BUF_IOCTL_SYNC` around the copy cost no more than the
       spread) against 818 with `dbus-listener.py`, which copies nothing on the reply (it maps the
       dmabuf and reads it every 100 ms); a first Mesa run during the heaviest load gave 60 frames/s
       and replies up to 51 ms. Not verified: a GPU node (tiled dmabufs aren't read yet), the
       SS-5 through PVE (it passes `test.sh`), a client in an LXC.
     - **Stage 3d: Moonlight to Wolf (in review).** Wolf (games-on-whales, `db709cf`, its v2026.11)
       rather than Sunshine: Wolf takes any GStreamer pipeline as an app's video and audio source,
       Sunshine captures from KMS, X11, Wayland or NvFBC only. Each VM is one Moonlight app
       (`e2e/streaming/wolf-config.py` writes Wolf's `config.toml` from Wolf's defaults): video
       `qemudbussrc ! compositor ! video/x-raw,framerate={fps}/1`, then Wolf's software path
       (`videoconvertscale ! videorate ! I420`, `x264enc tune=zerolatency`); the compositor repeats the
       newest picture, since `qemudbussrc` sends a buffer per change and Moonlight ends a session with
       no video for 10 s (and `videorate` lets a buffer go only when the next comes). Audio
       `qemudbusaudiosrc` into Wolf's Opus path. Input: Wolf makes uinput devices for the client's
       keyboard (Moonlight's Windows key codes mapped to Linux codes by Wolf's inputtino) and mice
       (relative, and absolute on 19200 x 12000); the app's runner, `wolf-input-bridge`, grabs them
       (EVIOCGRAB) and writes `qemu-dbus-input` lines (`key`, `btn`, `wheel`, `rel`, `abs X Y 19200
       12000`), so it starts and stops with the session. Found in Wolf: an app with
       `start_virtual_compositor = false` (also Wolf's own "Test ball") never starts (the session
       waits for a Wayland socket with an empty name and stops; `e2e/streaming/wolf-no-compositor.patch`,
       still so on Wolf's main of 2026-11-19, worth sending upstream), and Wolf crashes at start
       without a PulseAudio server to connect to (a null context in its PulseAudio router), so one runs
       next to it. `e2e/streaming`: `Dockerfile` builds Wolf (with Boost 1.87 from its source release
       by sha256, as Debian 13 has no Boost.Process 1.87+), the interpipe elements,
       moonlight-embedded (`33142e5`) and `wsh-moonlight-probe` (`moonlight-probe.c`: a Moonlight
       client on moonlight-embedded's libgamestream and moonlight-common-c that decodes every frame
       with libavcodec and reports its times and colours, decodes the audio into a WAV and sends
       input from text commands) from source on Debian 13, no prebuilt Wolf or Moonlight;
       `test.sh` runs QEMU, the VM's bus and Wolf in one container (`node.sh`) and the client in
       another, pairs with a random PIN entered on the node through Wolf's API socket (`wolf-pair`),
       and `stream3d.py` checks and measures. CI: `streaming.yml` on PRs that touch it and by hand
       (not required; most of its time is the source build). Lab, published pve-qemu-kvm
       11.1.3-4+wsh28 and wsh-gst-qemu-dbus 0.1+g56da148, TCG, wisp's framebuffer kernel at 1280x800, H.264 1280x800 at 60 frames/s (about 7 Mbit/s),
       five runs, every check passed: the decoded frame 1.6/255 from QEMU's screendump (1.4% of the
       pixels off by more than 48: 4:2:0 at the colour edges); from the guest's `fbtest` report to
       the decoded frame 55, 48 and 51 ms median at `refresh-ms` 30, 16 and 8 (min 29-43, max 63-70,
       10 samples each), 61 and 49 ms with `dbus,gl=on` (dmabufs through `/dev/udmabuf`) at 30 and 8
       (a second series: 62, 51 and 54 ms at 30, 8 and GL 30); the client's decode 0.7 ms of that; while the guest draws without a pause 33.2 new pictures/s
       reach the client at 30 ms (33.3 possible), 37.9 at 16, 40.6 at 8 (then the guest's drawing is
       the limit), out of a steady 60 frames/s whose intervals spread from 5 to 35 ms (stdev 8-9
       ms); keys A, B, Esc as Linux 30, 48, 1 in the guest 1.3-1.7 ms median after the client sent
       them, 0.3 ms of that through Wolf to the bridge; mouse buttons 1.4-2.2 ms; positions and
       relative motion add up exactly on the PS/2 mouse; `soundtest 440 2000` as 440.0 Hz in the
       client's Opus audio, 1.93-1.98 s, with one dropout of 50-85 ms just after the tone's start in
       every run with Wolf's input devices (none in the one run without `/dev/uinput`, where the
       input checks are skipped), the first sound at the client 90-160 ms after the command; without
       `/dev/uinput` the bridge stays idle so the session goes on. On a PVE node (an NVIDIA GPU on
       NVIDIA's driver): the VM from `qm start` (`vga: std,display=dbus`, `audio0: AC97,driver=dbus`,
       TCG), Wolf in a privileged container made from the Dockerfile's new `ct` stage (`docker
       export` as the template; `wolf-start` starts PulseAudio and Wolf, `wolf-config.py` now keeps
       paired clients), the bus directory bind-mounted at `/srv/wsh-dbus-display` (the container's
       systemd mounts its own `/run` over a bind mount there), `/dev/uinput` as a device and the
       node's `/dev/input` bind-mounted; the probe client in the container on the loopback: every
       check passed, guest draw to decoded frame 54 ms median with x264 at refresh 30 ms, 47 ms at
       8 ms, 50 ms with NVENC (`H264_ENCODER=nvenc`: `nvh264enc` on NV12, since Wolf's own NVIDIA
       pipeline also wants `cudaconvertscale`, which needs the CUDA toolkit's `libnvrtc`; the driver's
       libraries copied into the container), keys 1.1-1.5 ms, 440.0 Hz, the same audio dropout. An
       unprivileged container with its group mapped onto `wsh-display` reaches the socket but not
       the bus: GLib sends `AUTH EXTERNAL` with the container's uid 0 (`REJECTED`), and with the
       uid left out the bus authenticates the host uid 100000 and then refuses it, since
       dbus-daemon 1.16 checks `<allow group=...>` against the node's user database, not the
       peer's groups (a process on the node with `wsh-display` only as a supplementary group is
       refused too). `dbus,gl=on` on the NVIDIA GPU: QEMU's EGL and GBM work there, but the console's
       dmabufs are block-linear (`XB24`, modifier `0x300000000cdb014`) and `qemudbussrc` drops them
       (linear only), so the client keeps its first picture. Not verified: a client on another
       machine over the network, a real Moonlight client on a TV or phone (moonlight-embedded
       paired and its libraries streamed; its own SDL or X11 output wasn't run), the absolute
       pointer (wisp's x86 kernel has no USB HID and its `mousetest` takes the PS/2 mouse), a 3dfx
       game through it.
     - **Stage 3d: an unprivileged container (in review).** The two refusals above, one each:
       `wsh-gst-qemu-dbus` connects with GLib's `G_DBUS_CONNECTION_FLAGS_CROSS_NAMESPACE`
       (`AUTH EXTERNAL` without a uid, on the bus and on the listener's connection QEMU
       authenticates), and qemu-server's new VM option `dbus-display-uids` (`uid[;uid...]`, root
       only, needs the D-Bus display) names host uids for that VM's bus. dbus-daemon has no way
       round its user database: `bus_policy_allow_unix_user()` refuses a uid it can't look up
       before any rule is read, and `<allow user="100000"/>` without a user is "Unknown username"
       at load. So at the VM's start qemu-server writes the VM's bus configuration
       (`/run/qemu-server/<vmid>.dbus-display.conf`: an `<include>` of the shared policy, then per
       uid `<allow user>` in the default context and `<policy user>` with `send_destination=org.qemu`;
       the unit reads it), adds a user `wsh-display-<uid>` (system, no home, `nologin`) for a uid
       without one, and gives each uid `--x` on `/run/wsh-dbus-display` by an ACL entry, which goes
       when no running VM names it (qemu-server now depends on `acl`); no group mapping or
       `/etc/subgid` entry in the container. Considered and not taken: `ANONYMOUS` with
       `<allow_anonymous/>` (no uid at all on the bus, only the directory left as the gate), a
       directory open to all (`0751`), an include directory for hand-written policies (a per-node
       edit, and per node, not per VM). Tests: qemu-server's `run_dbus_display_tests.pl` (parsing,
       the generated configuration, users, the ACL across two VMs sharing a uid, a restart without
       the uids, a uid without a user) and cfg2cmd (`dbus-display-uids` with and without the
       display); `packages/wsh-gst-qemu-dbus/test.sh` gains a run with the clients in a user
       namespace whose root is the host's uid 100000 (`unshare`; CI now runs the container with
       `seccomp=unconfined`) on a bus set up by qemu-server's own `DBusDisplay.pm`: `qemu-dbus-input`,
       a picture from `qemudbussrc` and the listener of `qemudbusaudiosrc` get in; the e2e spec
       `dbus-display.spec.ts` checks the same on PVE with a node process as uid 100000 (skipped
       until a qemu-server with the option is published); uid 200000, uid 100000
       on a VM's bus that doesn't name it and a node user outside `wsh-display` are refused. Not
       verified: a real node and `pct` (the bind mount and the default idmap in an unprivileged
       container), Wolf's input devices in an unprivileged container (`root:input 0660` on the
       node's `/dev/input`), the `wsh-qemu-rdp` and probe clients from a container.
     - **Stage 3e: tiled dmabufs through EGL, and the audio dropout (in review).** `qemudbussrc`
       reads a dmabuf it can't map (a GPU's tiled layout: NVIDIA's block-linear, `XB24` with modifier
       `0x300000000cdb014` on the GTX 1080) through EGL (`src/qemudbusgl.c`): the EGL device of the
       render node (`EGL_EXT_platform_device`, no GBM or window system; else a software device or
       Mesa's surfaceless platform), the dmabuf as an EGLImage with its modifier, bound to an external
       texture, drawn 1:1 into a framebuffer with red and blue swapped and read back with
       `glReadPixels` (`BGRx`, the console's usual format), before the reply to `UpdateDMABUF` as the
       linear path's copy. `dmabuf-import=auto|mmap|egl`, `render-node=`; linear dmabufs are still
       mapped. Found: NVIDIA's driver doesn't make a read of the dmabuf wait for QEMU's drawing
       (QEMU only flushes before `UpdateDMABUF`; Mesa's implicit synchronisation hides that), so the
       last frame missed its lower rows now and then; the rows read through EGL are read once more
       20 ms later, and a picture that changed goes out again (1 in about 66 updates did). The audio
       dropout of 3d: `qemudbusaudiosrc` sent nothing until the guest played, Wolf's `audiorate`
       then filled the whole time since the stream's start with silence at once, and the leaky queue
       before it (`max-size-buffers=3`) dropped the tone's first 50 ms meanwhile (GStreamer's log:
       offsets 573638 to 576038); it grew with the session's length and the host's load, hence
       "with input devices". The source now sends silence in real time while the guest plays
       nothing, and its timestamps run on without going back (a burst from QEMU stays continuous; a
       Write more than 200 ms ahead is dropped). `e2e/streaming`: a dropout inside the tone fails the
       sound check, and so does more than 250 ms of audio reaching the client at once (the probe's
       `audio-ahead`: 11.6 s before, 5 ms now); `test.sh` takes a wsh-gst-qemu-dbus build
       (`WSH_GST_DEB`; `streaming.yml` builds the branch's) and a run `x86_64-egl`; the package's
       `test.sh` gets `x86_64-egl` too. Lab: every check passed with the published pve-qemu-kvm,
       x86 at refresh 30, 16 and 8 ms and GL at 30 ms (mapped and through EGL on llvmpipe, the frame
       identical to QEMU's screendump), 440.0 Hz for 2.03 s without a dropout, the first sound at
       the client 38-56 ms after the command (was 90-160). On the NVIDIA node: a `mesa-display=dbus`
       VM through EGL, the frame identical to QEMU's screendump in four runs of four (`UpdateDMABUF`
       answered in 0.7 ms on average), and Moonlight through Wolf with every check passed: guest draw
       to decoded frame 89-96 ms median with x264 (53-71 ms without GL in the same session) and
       77 ms with NVENC (55 ms without GL). Not verified: a guest drawing with GL (wisp has no GL
       program; the GL runs have QEMU's VGA picture uploaded as a texture), another GPU vendor's
       tiled layout.
     - **Stage 3f: a Windows 98 guest with Glide (in review).** The guest program `w3dstrm.exe`
       (`e2e/3dfx/win98/w3dstrm.c`, built by `build.sh` with the others; `w3d.h` gains a read-write
       COM1 and a longer open timeout for it) starts from the StartUp folder and takes commands on
       COM1 (`glide`/`glide3`, `bars`, `still`, `tone`, `run`, `quit`): its Glide window animates at 60
       frames/s, writes the frame number's low eight bits into eight black or white cells across the
       bottom (where `wsh-moonlight-probe` reads its eight points) and reports every swap (`F <frame>
       <ms>`), so each decoded frame names its guest frame and the serial line dates it; B held shows
       colour bars (input to picture). `e2e/streaming/stream3dfx.py` (on the node, importing
       `stream3d.py`) checks and measures: picture against the known frame (QEMU's screendump has no
       surface with GL), latency of every guest frame that reaches the client, pacing, input, keys,
       the tablet, a WinMM tone, `WSHDEMO.EXE` and `WSHSPACE.EXE` run by the program; optionally a
       second `qemudbussrc` in the container splits the latency. Found: a guest mode change
       (Windows' 1280x1024 desktop, then Glide's 640x480) came out unscaled in the corner on a
       checkerboard, as Wolf's `compositor` keeps its first size, so `wolf-config.py` scales before
       it; `pct exec` passes the node's `XDG_RUNTIME_DIR` on and `wolf-pair` looked for Wolf's socket
       there; the clone of the operator's Windows 98 disk stops at a network logon dialog
       (`--enter-after` presses Enter). On the NVIDIA node (pve-qemu-kvm 11.1.3-4+wsh27, KVM, the
       wsh-gst-qemu-dbus of 3e, Wolf in a privileged container, the probe on the loopback, 570-650
       samples a run): guest swap to decoded frame 25.7 ms median (x264), 23.6 ms (NVENC) and 25.5 ms
       (Glide 3) with Glide read back into the console, 28.6 and 33.1 ms (x264) and 24.9 ms (NVENC)
       with `dbus,gl=on`; frames reach `qemudbussrc` 0.7 ms (read back) and 2.0-2.6 ms (GL) after
       the swap, since Glide frames go out at the swap and not at QEMU's refresh; 58.8-60.1 new
       pictures a second out of the guest's 60 (every one with NVENC, intervals' stdev 1.8 ms);
       the picture 2.3/255 from the known frame, 1.1/255 from QEMU's screendump; keys A, B, Z as
       virtual keys 65, 66, 90 in the program 2.9-4.0 ms after the client, input to picture 40-44 ms,
       absolute positions exact through the USB tablet (relative motion moves in the 640x480
       console's pixels, so twice as far on the 1280x1024 desktop); `WSHDEMO.EXE` at 90 frames/s
       gave a new picture in every client frame. GL's 22-36 ms on wisp's VGA picture in 3e is not the
       EGL path (2-5 ms here): it sits with the VGA surface's texture upload at the refresh, which a
       first read can miss (about 5% of second reads changed the picture in a Glide run). Sound
       failed in this guest: a 2 s `waveOutWrite` was done after 0.34 s with 0.2-0.3 s in QEMU's
       stream. The cause was QEMU's AC97, not the guest's SigmaTel STAC97 driver: the driver writes
       the bus master's control register again with RPBM set after each new LVI, and QEMU restarted
       the engine at each such write and skipped the buffer playing (seen in a trace of the guest's
       AC97 accesses through QEMU's `memory_region_ops_*` events); pve-qemu-kvm `wsh/0170` starts
       it only when RPBM goes from 0 to 1 (qtest `playback_cr_rewrite`). With it, on the node
       (`stream3dfx.py --skip glide`, a clone without the Glide drivers): 1.99 s at 443.0 Hz
       without a dropout at the client, first loud packet 75-93 ms after the command (before: 0.28
       s at 458.7 Hz, five dropouts, 173 ms); 3 s tones 2.98-2.99 s, with one late gap of about 30 ms
       at the client in two runs of five and none in QEMU's own stream; `WSHSPACE.EXE -audiotest`
       passes the signature check (it had waited at its renderer menu, now skipped with
       `-audiotest`). The 0.68% high pitch is in the guest's data (Windows' 22050 to 48000 Hz
       conversion; the codec stays at 48000 Hz).
       Unprivileged container (a uid range of its own, 300000; `pct create` unpacks with the default
       100000, so the owners were shifted before the first start): Wolf runs; `/dev/uinput` works
       but the event devices it makes are `root:input 0660` on the node and `nobody` in the container,
       so the input needs a udev rule on the node (`ATTRS{name}=="Wolf *"`, owner the container's
       root, `LIBINPUT_IGNORE_DEVICE`; checked with `udevadm verify`, not installed); the bus refuses
       the container at the socket directory until a qemu-server with `dbus-display-uids` runs on the
       node (not yet installed there). Not verified: a commercial Glide game, the sound in a full Glide run (the guest with sound had no Glide
       drivers), SB16 in Windows 98 (its driver is in the CAB files).
     - **Stage 3g: the unprivileged container on a node (in review).** On the NVIDIA node with
       qemu-server 9.2.24+wsh3 (`dbus-display-uids`), pve-qemu-kvm 11.1.3-4+wsh29 and
       wsh-gst-qemu-dbus 0.3 (`CROSS_NAMESPACE`, the EGL import): Wolf in an unprivileged container
       with a uid range of its own (300000, the owners shifted before the first start), the VM with
       `dbus-display-uids: 300000`, and the node's udev rule for Wolf's input devices (now installed
       there: devices named `Wolf *` owned by the container's root, `LIBINPUT_IGNORE_DEVICE`). The
       container's root gets the VM's picture, sound listener and input; a user in the container
       (301000 on the node) and uid 200000 on the node are refused at the socket directory, the
       container's root on a VM that doesn't list it is refused by that VM's bus. `stream3d.py` on
       wisp's x86 kernel (KVM, refresh 30 ms, x264), every check passed: loopback 61.3 ms median
       guest draw to decoded frame, keys 2.6 ms, the picture 1.59/255, 440.0 Hz for 2.03 s without a
       dropout; over the network (the probe on another machine in the same VLAN, clocks within about
       1 ms) 60.6 ms, keys 3.0 ms, the mouse exact. No way without a node change was found for the
       input (the container can't `chown` the node's device nodes; a bind mount keeps their owner;
       mapping the node's `input` group would hand over every input device). Found: the `ct`
       template had no DHCP client (`ip=dhcp` failed; `dhcpcd-base` added); a directory under the
       node's `/root` can't be bind-mounted into an unprivileged container, so `stream3d.py`'s
       shared directory is the container's own through `/proc/<pid>/root`; Wolf's ports are TCP
       47984, 47989, 48010 and UDP 47999, 48100, 48200 (and mDNS), not Sunshine's; the user
       `wsh-display-<uid>` makes `useradd` warn about `SYS_UID_MAX` (harmless). Docs: the
       unprivileged recipe, the udev rule with the uid as a placeholder, the network and PVE
       firewall rules, pairing a client. The Windows 98 Glide guest of 3f (a full clone, the
       drivers of `b94d988`, `w3dstrm.exe`) through the same container: 26.1 ms median guest swap
       to decoded frame, 59.8 new frames a second, keys, tablet and input to picture (42 ms) as in
       the privileged container, but only with `qemudbussrc shared-map=false` (`SRC_PROPS`): with
       the shared map QEMU sent one `ScanoutMap` for the Glide surface and no `UpdateMap` after it,
       so the client kept the first picture. Not verified: a real Moonlight client on a PC, TV or
       phone.
     - Left for stage 3: 3c's second slice, dmabufs as dmabufs (`memory:DMABuf` caps for a hardware
       encoder, the reply to `UpdateDMABUF` held until the encoder is done or a copy on the GPU, which
       would also spare the EGL path its read back), the cursor drawn in or passed on, and
       `ScanoutDMABUF2`; 3e: the VGA path's 22-36 ms with `dbus,gl=on` on the NVIDIA node (3f: not
       the EGL import; most likely the VGA texture upload at the refresh and a first read that misses
       it), a fence from QEMU instead of the second read (QEMU would have to pass one), a guest
       drawing with OpenGL (`gltest.exe`, the demo's OpenGL) through it; 3f: the occasional 30 ms late
       gap in the client's audio (not in QEMU's stream), the sound in a Glide run with the drivers,
       a commercial Glide game, `stream3dfx.py` as a workflow on the
       lab runner (the operator's disk, like `3dfx-win98.yml`); 3d: a real Moonlight client on a PC, TV or phone (3g ran the unprivileged container end to end
       with the probe client, also over the network); 3g: why QEMU sends no `UpdateMap` for a Glide
       surface read back (until then `shared-map=false` for such a VM, or `qemudbussrc` falling back
       to the pixels by itself), the frame interval spread while the picture changes (still
       pictures come at an even 16.7 ms), Wolf's no-compositor patch upstream, and a repeat in
       `qemudbussrc` itself instead of the compositor.
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

- **Hookscripts in the web UI** (from the old TODO.md). Add, change and remove a VM's `hookscript`
  (a snippet volume) in the VM's Options, instead of only through `qm set --hookscript`. Not started.
- **Sound with the VNC console** (from the old TODO.md). noVNC has no audio channel; today sound reaches a
  client through qemu-rdp (stage 3b) or the GStreamer sources (stage 3c). Left open: whether a VNC
  console should get sound at all (QEMU's VNC audio extension, which noVNC doesn't implement), or
  whether the RDP and streaming paths cover it. Not started.
- **Mirror storage, after step 3.** Left open: a rename that also sets the drives of the VMs that use
  the old volume ID (now the window only lists them); `pvesm` subcommands for the two calls (`pvesh`
  works); rename and link on a storage with a description file by writing its entries (refused now;
  `wsh-lab mirror` edits the file); a rename or link run on a CIFS storage without `mfsymlinks` (not
  tested).
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
- **Browser SPARC (WebAssembly).** Run `qemu-system-sparc -M SS-5` on the docs site with QEMU's
  upstream Emscripten host support: wasm64 with the TCI interpreter (TCI is the only TCG backend
  there; the Wasm-emitting TCG backend is an out-of-tree series by Kohei Tokunaga, not in
  11.2.0-rc1). Step 1 (done 2026-11-21, `submodules/SPARC.md`, "TCI (QEMU's TCG interpreter)"):
  native TCI against TCG on the lab host: compiled code 8-35x slower, boots 1.6-6x. Step 2 (Done,
  see the table): wisp's shell on a serial-only page, `/browser-sparc/`, started from a migrated
  snapshot; built from Debian packages only (`web/Dockerfile`). Phase 1 of wisp's other machines
  (Done, see the table): the same serial shell on sun4u, the PC and Arm virt (`?arch=`). What is
  left:
  - publishing: run `browser-sparc.yml` with `publish` once, so the `browser-sparc` release exists
    and the next Pages deploy carries the files;
  - phase 2, a canvas display with keyboard (and mouse) for wisp's framebuffer kernel and fbDOOM:
    a small Emscripten display backend that copies QEMU's surface to a canvas (DisplayChangeListener
    `dpy_gfx_update` into a SharedArrayBuffer the page draws from with `putImageData`), key events
    into `qemu_input_event_send_key_qcode()`, the `kernel-fb` kernels (`TIER_FB=1`), per machine
    the display device (TCX/cg3, std VGA/bochs on sun4u and the PC, ramfb or virtio-gpu on Arm) and
    keyboard (Sun keyboard on the ESCC, PS/2 on sun4u and the PC, virtio-keyboard on Arm), the
    fbDOOM files (`e2e/wisp/doom/`) and snapshots taken with the display on. Estimate 4-6 days, most
    of it the backend and per-machine input, with fbDOOM's frame rate under the interpreter the open
    question (expect a few frames a second);
  - phase 3, WebAudio: an Emscripten audio backend (QEMU's audio driver API into an AudioWorklet
    through a ring buffer in shared memory), the CS4231 on the SS-5, a PC sound card and Arm's
    virtio-sound or an emulated HDA, and wisp's tier-sound kernels. Estimate 3-5 days, the clock
    coupling (the device runs on the virtual clock, the worklet on the sound card's) being the hard
    part;
  - a smaller PC module (36 MB of WebAssembly with every x86 board and device; a device file with
    the `pc` machine's devices only, as Arm's `minimal`);
  - speed: the interpreter in WebAssembly is about 5x slower than native TCI (Memory64, Asyncify);
    the Wasm TCG backend once it is upstream;
  - networking (a WebSocket proxy), a NetBSD/sparc disk fetched in ranges (the sun4u IOMMU's
    migration state is in pve-qemu `wsh/0133`), and a local-only picker
    for a user's `ss5.bin` and Sun disks (Sun firmware and installed Sun systems are never
    published).
  Generic Wasm pieces (display and audio backends) are written against plain upstream QEMU;
  LEMU-derived code stays in wsh-pve.
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
  the original SunOS 4.1.3 stopped early in a device probe: its generic sun4m kernel probes for VME
  controllers the SS-10 doesn't have, and QEMU raised the data access error (trap 0x29) for the bus
  error where the SuperSPARC takes a data access exception (0x09), the only trap 4.1.3's nofault
  path handles. pve-qemu `wsh/0049` (qtest `wsh/0050`) does as the SuperSPARC for loads and
  fetches (published in pve-qemu-kvm 11.1.3-2+wsh31), and `sunos413-ss10` is an automated target
  since (5/6 installs through PVE on +wsh31, in review, below). 4.1.2 (SS-600MP) installs and
  boots on one CPU in the lab with pve-qemu `wsh/0063`-`0065` (the VMEbus interface registers, the
  lance's own buffer memory) and openbios 0028 (the `dma` and `lebuffer` node names it knows), merged
  (#430, published in 11.1.3-3+wsh13); `sunos412-ss600mp` is an automated target with qemu-server's SS-600MP
  profile (in review, see "Done"). More CPUs need the module ID that 4.1.2 reads from the MMU
  control register (a Ross module, which QEMU doesn't emulate, or a cheaper lead below), and
  Solaris 2.6 and later refuse the machine by name under any firmware, while 2.1-2.5.1 install under
  Sun's 600MP PROM (6g below, `submodules/SPARC.md`). Sun's own SS-600MP boot PROM
  knows the SuperSPARC and doesn't need a Ross model; it stops in its power-on self test ("Sun's
  SS-600MP boot PROM" below). OpenBIOS 0019-0022 run the Solaris
  2.1-2.4 boot program: 2.2 (SS-10), 2.3 and 2.4 (SS-5 and SS-20) are install targets under OpenBIOS
  since pve-qemu-kvm 11.1.3-2+wsh22 (`sol22-ss10`, `sol23-ss5`, `sol23-ss20`, `sol24-ss5`,
  `sol24-ss20`; 2.3 and 2.4 on the SS-20 also run with 2 and 4 CPUs); 2.1 stops in QEMU after its
  device configuration (its kernel switches to a context it hasn't filled yet). Fixed in pve-qemu
  `wsh/0047` (qtest `wsh/0048`, SPARC.md, "Older Sun releases on sun4m"), published in pve-qemu-kvm
  11.1.3-2+wsh29; `sol21-ss10` is an automated target since (3/3 installs through PVE on +wsh30, 2/2
  on 11.1.3-3+wsh6).
  Open for 2.1: `/opt` and `/export/home` aren't mounted at boot, and 2 CPUs still trap in
  `cpu_startup`.
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
- **Solaris releases not tried yet.** With media on the lab host: none left.
  (2.2, 2.3, 2.4 on the SS-20, 2.5 and 2.1 are done: "Done" and the item above; 2.5.1 on the SS-20
  under OpenBIOS and 2.6 and 7 on the SS-10 are install targets, "Done"; 8 2/02 and 9 9/05 install on the SS-5 and SS-20, and on sun4u with OpenBIOS
  0024; 8 2/02 also under `ss5.bin` on the SS-5, `sol8-ss5-prom`; 7 3/99 on sun4u, `sol7-sun4u`.) Needing media: 8 2/04, and an earlier Solaris 10 update on sun4u. Out of reach: 2.0 and SunOS
  4.1.1 or older (sun4c only), Solaris 11 (no UltraSPARC IIi).
- **OpenBSD 8.0 on sun4u through the tool: DHCP.** `--ip dhcp` is refused for `openbsd80-sun4u`
  (the lab's own runs got an address with `inet autoconf`). The IDE timeouts with ntpd on are fixed
  ("Done": `wsh/0045`).
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
  stored disks, plus installs of targets that have none yet. Done: the monthly `reinstall=all`
  (first Saturday of the month, 07:17 UTC, 720-minute limit; about 6 h): every target without
  `matrix_skip` installed again and its stored disk replaced when the check passes. Still to do:
  automate more targets (Solaris 2.2-10, SunOS 4.1.3_U1B and 4.1.4, NetBSD 11.1 on sun4u, SS-5 and SS-20, OpenBSD 8.0
  on sun4u, Tribblix, Debian 7 on sun4u, and Red Hat Linux 6.2 and Debian 4.0 on SS-5 and SS-20 are automated). Today the weekly `pve` matrix reinstalls Solaris 2.6 on
  SS-5.
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
- **Sun's SS-600MP boot PROM, and a second CPU under SunOS 4.1.2: scoped** (2026-11-22,
  `submodules/SPARC.md`, "Sun's own SS-600MP boot PROM"). The 600MP PROM knows the Cypress/Ross
  605, the Ross 625 and the SuperSPARC (with or without MXCC), so QEMU's SuperSPARC is a module it
  supports. On the published 11.1.3-4+wsh4 it stops QEMU within seconds (`Trap 0x01`, an
  instruction fetch translated in boot mode with the MMU on): pve-qemu `wsh/0120`-`0121` (lab
  build, not published) fix that. It then looped silently in its power-on self test, which reads
  back SuperSPARC diagnostic registers QEMU didn't keep; `wsh/0145`-`0150` (2026-11-25) keep them
  and fix the board timer bits it checks; `wsh/0151`-`0158` (2026-11-25) take it through the
  board's counter-timer, IOMMU, VMEbus control and lance address port tests to the lance's
  register size check (progress `0xc1`); `wsh/0159`-`0161` (2026-11-26) give it the bus errors
  that check wants; `wsh/0171`-`0172` (2026-11-26) make its SCSI DMA the ESC gate array it
  tests (`0xc3`); `wsh/0173`-`0176` (2026-11-26) take it through the lance loopback test (`0xc4`) and
  the I/O cache tag and data test (`0xc6`); `wsh/0177`-`0180` (2026-11-26) through the ESP's register
  test (`0xe4`); `wsh/0181`-`0183` (2026-11-26) through the ESP's DMA read test (`0xe5`), after which the
  rest of its POST passes and it reaches `ok` on ttya, with a Data Access Exception before it;
  `wsh/0184`-`0187` (2026-11-26) clear that exception and `probe-scsi`, and `boot disk` boots the stored
  `sunos412-ss600mp` disk from Sun's PROM to a root shell.
  - **Steps for the PROM, in order:**
    1. Keep the SuperSPARC store buffer diagnostic registers (ASI 0x30-0x32): done, pve-qemu `wsh/0145` (feature `sbuf-diag`).
    2. Read back the MXCC stream data registers: done, `wsh/0146`.
    3. Keep the I- and D-cache tag and data RAMs (ASI 0x0c-0x0f) with the TMS390Z50 geometry: done, `wsh/0147` (feature `cache-diag`); qtests `wsh/0148`.
    4. Pass the board's counter-timer tests: the four user timer bits and the user timer's limit bit, done (`wsh/0149`, qtest `wsh/0150`); the test's back-to-back counter reads, which passed only on some runs (QEMU's I/O is faster than a timer tick): done, a read with no tick since the last one returns one tick more, at most 16 ahead, on the SS-600MP only (`slavio_timer` property `read-ahead`; `wsh/0151`, qtest `wsh/0152`); the test passes on every run.
    5. The IOMMU's SBus slot configuration, base and TLB data registers (progress `0xad`-`0xaf`), the VMEbus control register (`0xb0`) and the lance's register address port (`0xc1`): done, the 600MP's masks from the PROM's compare reads (`wsh/0153`, `0155`, `0157`, qtests `0154`, `0156`, `0158`).
    6. The lance's register size check (`0xc1`): done. Loads at the power-of-two offsets of the lance's page through the MMU bypass ASI, with the MMU off, take a data access exception with SFSR `0x436` (bus error bit 10, FT 5) and the SFAR; stores there come back as M-to-S write errors in the IOMMU's AFSR/AFAR with a level 15 interrupt (`wsh/0159`, `0160`, qtest `0161`; CPU feature `buserr-trap`, set by the SS-600MP only).
    6a. The on-board DMA (`0xc3`, slot f `0x81000`): done. It is the ESC gate array (device ID 4): control register bits `0x00042b90`, a 24-bit byte count, no address-loaded bit, and wrong-size accesses trap and set the slave size error bit (`wsh/0171`, qtest `0172`; property `esc`, SS-600MP only). `sunos412-ss600mp` still attaches `dma0`/`esp0`/`sd0` and logs in.
    6b. The lance loopback test (`0xc4`) and the I/O cache test (`0xc6`): done. The PROM leaves garbage in the receive descriptor's message count word, which QEMU's descriptor check rejected (CSR0 MISS), and gives a 40-byte buffer for a 32-byte frame, which QEMU padded to 60; the lance now receives as the Am7990 there (`wsh/0173`, qtests `0174`; lance property `am7990`, SS-600MP only, because with it the SS-5 and SS-20 PROMs' loopback test passes and their default network boot with a blank NVRAM no longer falls back to `ok`). The VMEbus interface's I/O cache tags (bits 31-20, one per 32-byte line) and 32 KB of data at `0xf.df00_0000` are storage (`wsh/0175`, qtest `0176`). Tests `0xc5` and `0xc7`-`0xe3` pass or are skipped without the diagnostic switch.
    6c. The ESP's register test (`0xe4`): done. Configuration register 2 doesn't keep bit 5 on the 600MP (`sysbus-esp` property `cfg2-mask`, `0xdf` on the SS-600MP only; `wsh/0177`, qtest `0178`), and the ESP's registers sit behind the ESC, which takes only byte accesses there and sets its slave size error bit for other sizes (`esc-esp` region, `wsh/0179`, qtest `0180`). SunOS 4.1.2 still takes its ESP236 path and attaches `esp0`/`sd0`; the other machines are unchanged. The chip is a FAS-family part (it has a configuration register 3), not an ESP100A.
    6d. The ESP's DMA read test (`0xe5`): done. With the IOMMU turned off the PROM puts the ESP in chip test mode with target mode forced, gives it Send Data with DMA (`0xa2`) and waits for the ESC's transfer count zero bit (`DMAESC_TCZERO`) before reading the bytes back from the FIFO (`wsh/0181`, IOMMU property `enable-bit`; `wsh/0182`, ESP property `target-test` and the ESC's count and TCZERO; qtest `0183`; SS-600MP only). The DMA write and write error tests don't run without the diagnostic switch and aren't modelled. The rest of the POST then passes or is skipped, and the PROM prints its MMU setup on ttya and reaches `ok`.
    6e. The monitor's device probing: done. `0xf.f8c0_0a04` is the MXCC control register of MBus module 8 (CPU 0) in the module's MBus space (each module ID n at `0xf.f000_0000 + (n << 24)`, the MXCC's ASI 2 registers at offset `0x00c0_0000`); the PROM's `mxcc-ctl@` reads it there and sets E$ enable (`wsh/0184`, hwdef field `mbus_mxcc`, a `mxcc-mbus` region per CPU with an MXCC). The PROM then probes its CPUs, memory and SBus, prints its banner, tests memory and, with QEMU's blank NVRAM, boots from the network; Stop-A on the keyboard (QMP `send-key`) gives `ok` (a ttya break is too short for its polling). `probe-scsi` listed every target as Unit 0-7: it selects without ATN and puts the LUN in the CDB (`wsh/0185`, `sysbus-esp` property `cdb-lun`). `boot disk` then loaded SunOS 4.1.2, whose audio driver wrote the PROM's `audio` node at obio `0x500000` (an AMD 79C30) and panicked (`wsh/0186`, an unimplemented `sun-audio` device). Qtests `wsh/0187`; all SS-600MP only. `sunos412-ss600mp` boots from the PROM to its login, reads its disk and pings.
    6f. `ok` without Stop-A, and SunOS 4.1.2 installed under the PROM: done. QEMU's NVRAM (OpenBIOS's layout) failed the PROM's configuration checksum, so it set `diag-switch?` and booted from the network for ever. Its configuration area (the first 6 KB, an XOR checksum over `0x20`-`0x17ff`, three self test flags outside it) worked out in the lab; with the SS-600MP and a firmware that isn't OpenBIOS QEMU writes it with the PROM's defaults but `diag-switch?` and `auto-boot?` false and `skip-vme-loopback?` true, so the PROM stops at `ok` on ttya within 10 s without a keyboard (`wsh/0188`, hwdef field `prom_config`; qtest `0189`; the other machines' NVRAM byte for byte as before). qemu-server's SS-600MP profile takes `bios: ss600mp.bin` (pve-manager mirrors it; `wsh-sun-proms` knows the image's hash), and the lab target `sunos412-ss600mp-prom` installs SunOS 4.1.2 from its CD under the PROM through PVE (`boot cdrom`, the miniroot booted by the PROM, suninstall, first boot, check; 256 MB, since with 64 or 128 MB the PROM loops in its self test).
    6g. Solaris 2.x under the PROM: done for 2.1-2.5.1 (in review). 2.6 and later halt after their banner on this machine under any firmware: the kernel refuses the root node name `SUNW,SPARCsystem-600` ("This hardware platform is not supported by this release of Solaris"; OpenBIOS names it correctly too, so nothing to fix there). Under the PROM 2.1-2.5.1 hung after `clock gained ... days`: the PROM's `bcopy?` makes the kernel zero and copy pages with the MXCC stream registers and poll their RDY bit, which QEMU read as 0 (`wsh/0190`, CPU feature `mxcc-stream-rdy`, SS-600MP only; qtest `0191`). The lab targets `sol21-ss600mp-prom`, `sol22-`, `sol23-`, `sol24-`, `sol25-` and `sol251-ss600mp-prom` install through PVE. More than one CPU under the PROM: not yet; QEMU starts the second CPU powered off and the PROM, which expects every module to run it from reset, sees one (`1 X 390Z55`); starting all at reset stops the PROM early (its multiprocessor start isn't modelled). Medium, not started.
    7. With the diagnostic switch (lab-only, bit 2 of the system control register) the POST prints and runs a longer list, which also needs the MXCC's 2 MB external cache RAM and the MMU's root/level-2 page table pointer cache (ASI 6): medium and large.
    - Its POST and the monitor's probing pass now, it stops at `ok` by itself and installs and boots SunOS 4.1.2 and Solaris 2.1-2.5.1; what is left is more than one CPU under it (6g) and the diagnostic switch's longer list (7).
  - **A Ross or Cypress CPU model** (RT620/RT625 or CY7C601/CY7C605): large (MMU control layout with the module ID, ICCR, Ross cache and flush ASIs, the hyperSPARC instruction buffer). Nothing to start from: QEMU dropped name-only definitions in 2013, and none was found in MAME, TME or a qemu-devel search (LEMU not checked). It would face the PROM's Ross tests too, so it isn't the way to Sun's PROM.
  - **Cheaper lead for 4.1.2's second CPU:** the kernel skips its module ID check when bits 15-16 of the MMU control register read all ones (AC and TC on the SuperSPARC). Try OpenBIOS setting them on machine ID 66 on the installed GENERIC kernel with `-smp 2`: small if it holds, not tested.
  - **Unlocks:** Sun's PROM only when its POST passes. No older SunOS (4.1.2 is the first sun4m release). Solaris 2.6's refusal is the kernel refusing the machine by name (any firmware); 2.1-2.5.1 run (6g).
- **SMP on sparc64 (sun4u): scoped, parked** (2026-11-22). Today `sun4u` refuses more than one CPU.
  - **What is missing in QEMU 11.1.3:**
    - `hw/sparc64/sun4u.c` sets `max_cpus = 1` ("XXX for now"; niagara is the same) and creates one CPU.
    - `main_cpu_reset()` keeps a single static reset count.
    - `ASI_UPA_CONFIG` reads 0, so every CPU would see MID 0.
    - The interrupt dispatch registers (`ASI_INTR_W`, 0x77) are not handled: a guest's cross-call raises an MMU fault. The dispatch status (0x48) always reads "delivered".
  - **What is missing in OpenBIOS:** it builds one CPU node, and `start-cpu` is unimplemented. There is no `SUNW,start-cpu`, `SUNW,start-cpu-by-cpuid` or `SUNW,stop-self`, and no parking for a second CPU in `entry.S`.
  - **Already in place:** MTTCG, TSO ordering and TCG atomics for sparc64 are upstream; tick and stick are per CPU.
  - **Machine model:** NetBSD, OpenBSD, Linux and Solaris start CPUs through those client-interface services and cross-call through 0x77/0x48 with the BUSY/NACK protocol. So a 2-4 CPU `sun4u` with the sabre (a machine that never existed) is likely enough. An Ultra 60/E450 model with a Psycho bridge isn't needed.
  - **Steps:**
    1. QEMU: N CPUs (the others start powered off), MID in `ASI_UPA_CONFIG`, dispatch with NACK, reset per CPU, a qtest (small to medium).
    2. OpenBIOS: CPU nodes, parking, the start/stop services, a client interface entered from any CPU (medium, new firmware assembly, the risky part). Steps 1 and 2 together are the smallest useful step: wisp tier 2 and NetBSD 11.1 with `-smp 2`/`4`.
    3. Idle halt on every CPU (the BSDs, Linux).
    4. Proxmox: the profile's CPU limit, the wizard, e2e tests, a `sparc64-smp` lab matrix.
    5. Solaris 9/10 and Tribblix: the remaining PROM services and a sun4u port of the multiprocessor idle match (`wsh/0023`) per compiler layout (medium).
  - **Why parked:** on TCG more CPUs only help parallel CPU-bound work (sparc32 measured 1.6-2.7x throughput with 2-4 CPUs, `submodules/SPARC.md` "SMP"). Installs and interactive use, what the sparc64 profile serves, gain nothing, and the open sun4u items give more.
  - **If picked up:** a time-boxed proof of steps 1-3 with wisp and NetBSD; go on only if NetBSD shows `hw.ncpu = 2` and passes a 30-minute soak. SMP on sun4v/`niagara` stays out of scope: it has no mondo queues, disk or network.
- **WRP in retronet** (owner's request, 2026-11-21). Look into tenox7's Web Rendering Proxy (WRP),
  which renders modern pages as images (ISMAP/GIF) for old browsers, as a service next to the
  retronet gateway and vintagehive, so the Solaris/Netscape, Windows 9x and DOS guests can read
  today's web.
- **Demo ideas to show and post** (collected 2026-11-21; the owner drops what isn't wanted). Public
  demos use OpenBIOS and our own software only: no Sun PROMs, MS-DOS, Windows or NeXT material.
  1. *A SPARCstation 5 boots Linux in your browser*: the Browser SPARC item above with wisp, the tiny
     nolibc kernel+initramfs (`e2e/wisp/`) instead of a NetBSD disk; the page exists
     (`/browser-sparc/`, resumed from a snapshot in under a second); optionally
     three terminals side by side (SS-5, sun4u, PC) running the same `init.c`, big- and little-endian
     in the banner.
  2. *A GitHub Action for big-endian testing*: build a C program for sparc32 v8 (nolibc or
     uClibc-ng), boot it in the wisp kernel under QEMU, return pass/fail in seconds; useful to other
     projects for endianness and alignment bugs. Built with nolibc (see "Done": wisp-test,
     `.github/actions/wisp-test`); to show it, publish the `wisp-test-kit` release and point a
     post at the self-test's failing and passing runs. uClibc-ng for sparc32 is left for later
     (Buildroot, as item 10).
  3. *The emulation ladder*: one compute loop native, under KVM, TCG, TCI and TCI-in-Wasm, and nested
     (sparc in x86 in Wasm), as a chart or short video, with the TCI numbers from the lab. The
     page exists (guide "The emulation ladder"); native, KVM and the nested rung are not measured yet.
  4. *ASCII Mandelbrot or a ray tracer on the serial console* of all three architectures at once,
     recorded with asciinema and timed. wisp's shell has the Mandelbrot (`mandel` with `wisp=shell`).
     Recorded 2026-11-22: `wisp-mandel-ss5.cast`, `-sun4u.cast` and `-pc.cast` (boot, `mandel`,
     `poweroff`, real time, 3.7-4.7 s each; `e2e/wisp/record.py`), shown in the guide "wisp",
     "Mandelbrot on three architectures"; the owner uploads them to the `media` release. A ray
     tracer and a side-by-side view are not done. wisp also draws the Mandelbrot set on the
     framebuffer (#472).
  5. *An AI drives a SPARCstation*: a recording of an agent using `sparc-lab-mcp` to log in to
     Solaris 2.6 or SunOS 4.1.4, compile a program with the period compiler and run it.
  6. *3dfx in the browser*: a Glide demo in Windows 98 rendered offscreen and shown in PVE's noVNC
     without a GPU or X server (a clip; the Windows desktop stays out of published material, so a
     self-made Glide scene or a freely distributable demo); stronger once stage 2 (dmabuf,
     Moonlight) is done.
  7. *Retronet*: an SS-20 with Netscape, a Windows 9x and a DOS machine on retronet reading today's
     web through WRP and talking over IRC/BBS through the dial-up setup ("three machines from 1996
     read Hacker News").
  8. *The fastest SPARCstation that ever existed*: the emulated SS-20 (4 CPUs) and SS-5 against
     published 1995 figures for real machines (Dhrystone, nbench from the lab's bench), with the LX
     on its own PROM as a curiosity (results only, no PROM).
  9. *A living museum*: a page to pick a machine and OS (SunOS, Solaris 2.x, NetBSD, OpenBSD,
     Debian 4, Red Hat 6.2) and watch its install and first boot from the existing recordings. The
     page exists (guide "Living museum") and now has the sun4u boots (Solaris 9, Solaris 10,
     Tribblix), aarch64 (Alpine, through Proxmox VE) and the wisp casts (SS-5, sun4u, pc) too; only
     the NetBSD-on-sparc64-under-PVE cast stays out (no matching first boot).
  10. *Doom on sparc*: fbDOOM on the cg3/TCX framebuffer, then in the browser through Wasm; needs the
     a libc under wisp (Buildroot with uClibc-ng). fbDOOM with Freedoom runs under wisp on SS-5 and
     sun4u (#473); the browser (Wasm) part is still open.
- **wisp on more architectures:** riscv64, tested with Debian's QEMU since
  the package doesn't build `riscv64-softmmu`.
- **wisp on the ESP32-S31 (idea):** Espressif's first chip with a paging MMU (Sv32) and up to 16 MB
  PSRAM on its boards, with an experimental Linux BSP from Espressif (2026). A riscv32 tier tested
  in `qemu-system-riscv32 -M virt` first; real hardware once the BSP or mainline support matures.
  Smaller ESP32 parts (C-series, P4 without MMU) don't fit Linux.
- **wisp-netbsd, what is left** (the prototype is in Done; `e2e/wisp-netbsd/README.md`, "Next"):
  - the `timecounter went backwards` warning NetBSD prints once in most sun4m boots (QEMU's
    slavio counter-timer as NetBSD's `timer0` timecounter reads it, or NetBSD's code);
  - sparc64 boot time: 8.7 s to the kernel's first line, most of it OpenBIOS reading the 3.6 MB
    kernel from the boot disk; try a gzipped kernel (`ofwboot` reads those). A `-kernel` path
    would need OpenBIOS to start an ELF at its entry and pass what `ofwboot` passes;
  - PID 1 without stdio (`write(2)` and a small formatter drop jemalloc and most of the 600-720 KB),
    then, as planned, our own syscall stubs instead of libc ("nolibc for NetBSD");
  - kernel size (1.4 MB sparc32, 1.6 MB sparc64, 2.7 MB amd64 without the ramdisk): what is left
    in `conf/std`, amd64's ACPI;
  - sparc32 SMP on SS-10/SS-20 (`-smp 2`, `-smp 4`) and tier 2 as in wisp (disk controllers, a NIC).
  Not FreeBSD or OpenBSD (no 32-bit sparc), not illumos (x86_64 only, needs an illumos build host).

## Known and not fixed

| What | Notes |
| --- | --- |
| OpenBIOS 0009 on sparc64 prints `decode-unit isn't unique.` / `encode-unit isn't unique.` at power-on | Its `drivers/pci.c` hunk redefines the two words in the ebus node, which already has the PCI bridge's methods. Harmless so far; untested idea: give the ebus node its own methods (found by the LEMU port) |
| SS-5 with OpenBIOS: `(enter)` then `go` at the prompt stops QEMU with `Trap 0x21` (instruction access error, traps off) | OpenBIOS 0008's prompt/resume path; not a supported path, reproducible with `-M SS-5 -prom-env auto-boot?=false` (found by the LEMU port) |
| The Solaris 2.6 CD on SS-20 sometimes hangs after `Configuring devices...` | A race in Solaris's init, not QEMU: init waits for the installer's `rcS` with a check of the child and a `pause()` that `SIGCLD` can fall between, and then sleeps for good (traced with the gdbstub; a signal sent to init from the debugger lets the boot go on). 2 of 213 lab boots with pve-qemu `wsh/0001`-`0013`, 0 of 82 with `0001`-`0138` (too few to call it gone). `matrix.py` boots such a CD case once more (`RETRY`), as `lab.py install` does; nothing to fix in QEMU or OpenBIOS (`submodules/SPARC.md`, "The CD boot that stops after `Configuring devices...`") |
| The SunOS 4.1.4 install kernel crashes QEMU with 256 MB (`Trap 0x29`) | 64 MB works; the installed system runs with 256 MB. The install target `sunos414-ss5` runs its install phase with 64 MB and sets 256 MB afterwards |
| `zs3: ring buffer overflow` in Solaris under load | Mouse data arrives faster than a 1200 baud mouse would send it; harmless. Pacing the ESCC mouse would remove it |
| X in Solaris 2.6 only starts at 1024x768 on cg3 | Larger sizes give a text console; qemu-server has no resolution option |
| Sun's SS-600MP boot PROM doesn't get through its power-on self test | Without `wsh/0120` QEMU stops on `Trap 0x01` within seconds; with it and `wsh/0145`-`0161` the PROM passes its CPU module tests (store buffer, MXCC, cache RAMs) and the board's counter-timer, IOMMU, VMEbus control and lance address port tests, passes the lance's register size check (bus errors with the MMU off, `wsh/0159`-`0161`) passes the on-board DMA's register and size checks (`wsh/0171`-`0172`), the lance loopback and I/O cache tests (`wsh/0173`-`0176`), the ESP's register test (`wsh/0177`-`0180`) and loops in the ESP's DMA read test (progress `0xe5`). Silent throughout. Scope and steps in "Later" ("Sun's SS-600MP boot PROM"); qemu-server offers OpenBIOS only on the SS-600MP. Since `wsh/0181`-`0188` it passes its self test, probes, stops at `ok` by itself and installs SunOS 4.1.2 (6e, 6f); qemu-server takes `ss600mp.bin` on the SS-600MP |
| NeXTSTEP 3.3 and OPENSTEP 4.2 hang on the disk during their install unless the VM has `machine: SS-5,esp-irq-latency=500` | QEMU's ESP raises its interrupt in the same instruction that starts a command; NeXT's driver deadlocks. The opt-in delay (`wsh/0040`) is in pve-qemu-kvm 11.1.3-2+wsh24, qemu-server 9.2.19+wsh2 and pve-manager 9.2.31+wsh2 (the UI field); off by default, as it costs about 2 ms per disk command (`submodules/SPARC.md`, "NeXTSTEP 3.3 and OPENSTEP 4.2"; the sparc guide, "SCSI interrupt delay") |
| OpenBIOS doesn't boot an installed NeXTSTEP/OPENSTEP disk | `Unhandled Exception 0x00000021` in NeXT's boot program before its banner; `ss5.bin` boots it (with `-v`: its boot graphics end in `Data Access Error` on the 8-bit TCX). Not diagnosed |
| A disk installed on SS-5 does not boot on SS-10/SS-20 | Device paths differ; needs a repair from the CD's miniroot, not written or tested |
| Solaris 2.5.1 and 2.6 idle on SS-10/SS-20/SS-5 only for the kernel builds in `SPARC.md` | A differently compiled idle loop is not recognised and spins as before |
| sun4u idle only for the kernel builds in `SPARC.md` (NetBSD 9.3/11.1, OpenBSD 8.0, Solaris 7 3/99, 8 2/02 and 1/01, 9 9/05 and 10 1/13, Tribblix m34, Linux 6.1-7.3 as Debian and wisp build it, Debian 7's Linux 3.2) | A differently compiled idle loop is not recognised and spins as before (`-trace sparc64_idle_match` shows a match) |
| Linux 3.2 (Debian 7) on sun4u is slow under TCG: the install takes about 85 minutes, a boot to `login:` 2.5 minutes | QEMU retranslates its code all the time: after the install `info jit` showed 1.2 million blocks with 0.19% of the hash table in use, 4 million invalidations and 23 flushes of the 1 GB code buffer (a boot fills it once or twice). Where the writes to code pages come from wasn't traced; it may also be behind the `dpkg-deb` soft lockups reported for Debian 12 on QEMU sun4u (`submodules/SPARC.md`, "Debian 7 on sun4u") |
| A CD that answers as a disk (`cd_as_disk=1`) has no field in the web UI | Set it with `qm set` or the API; the CD/DVD editor keeps it when the medium changes |
| Live migration of a VM without `-cpu`; `qm suspend --todisk` | Not working or not tested |
| `floppy.spec.ts` "Hardware: Add -> Floppy Drive" times out on a fresh container | Passes on rerun; a cold-start flake |
| `build-deb.yml`'s separate 3dfx job has not run in a package build yet | A branch dispatch would publish, so it was checked with actionlint and a local run of the hand-over step; the first pve-qemu build on main is its test (its run should show `qemu-system-x86_64-3dfx from the 3dfx build of ...` and the release no "Optional extras missing") |
| 3dfx Glide: QEMU dies with `BadMatch` on an X server with a 32-bit ARGB visual | OpenGLide's GLX config picks the 32-bit visual, SDL's window has the 24-bit default (seen on Xvfb with Composite and Mesa; real Xorg with a hardware GLX not checked). `e2e/3dfx` runs Xvfb with `-extension Composite` |
| 3dfx offscreen (VNC console): no Glide MSAA; OpenGL MSAA only where the EGL driver reads a multisampled pbuffer back | Glide's framebuffer object is single-sampled (multisampled buffers would need a resolve before every LFB read and swap). OpenGL checks a test pbuffer when the window is made and renders without MSAA otherwise; Mesa's llvmpipe and softpipe can't. Stage 1b leftovers in the Streaming item |
| 3dfx Glide: OpenGLide writes `OpenGLid.ini`/`OpenGLid.log` into QEMU's working directory | And `exit(0)`s the process when it can't write there (its library constructor). Where qemu-server's QEMU runs from is not checked |
| 3dfx Glide: a guest LFB read that drains queued calls comes back shifted | glidept puts the pixels after the drained calls' data, the guest wrappers (Linux, Windows, DJGPP) copy from the start; a read after a swap or a direct call is right. Upstream (qemu-3dfx) material; `e2e/3dfx` reports it without counting it |
| 3dfx with an SDL window: the second or third 3D window in one VM ends QEMU with an X error | Seen in the Windows 98 test on Xvfb (`BadRequest` when Glide 3 followed Glide 2, `BadLength` when OpenGL followed both); each test alone passes. Headless (offscreen) not affected |
| SS-5 fbDOOM sound (`doom.py --sound --arch sparc32`) stops early | With 1024-byte (5.8 ms) periods Linux sometimes handles a PI late under TCG; the codec has then played the next buffer too, PMI comes as soon as the PI is cleared, and `snd_cs4231_sbus_interrupt()` ignores an APC interrupt with the pipe-empty bit (`APC_XINT_EMPT`), so playback never resumes. Lab 2026-11-23: the WAV held 0.1-28 s of a 38-75 s demo in most runs, before and after `wsh/0128` alike (one or two runs of three passed, 6-9 bursts); 2026-11-24, 8 pairs on a busier lab host: without 0128 0.10-0.41 s in six runs, 16 s in one, one hang until the 900 s timeout; with it 0.10-0.39 s in all eight; no run passed either way. The demo itself completes 7,117 gametics in every run that ends. CI doesn't run sound on the SS-5 |
| sun4u: the sabre keeps one interrupt request to the CPU at a time | An interrupt the guest never clears (a device that interrupts after its driver is gone) holds back every other one, the IDE's included; on real hardware each ino has its own state. The case Debian 13 hit (the sunhme after its reset) is fixed in `wsh/0135`; the model itself is unchanged (`submodules/SPARC.md`, "The lost IDE interrupt at Debian 13's power-off") |
| Streaming: after `qm stop`/`qm start` of a VM, `wolf-input-bridge` stays on the old VM bus | The client's input no longer reaches the guest until `wolf-start <vmid>` runs again in the container; should reconnect by itself (display reference, "Open issues seen on a node", a) |
| Streaming: a Windows 98 guest with `usb-tablet` hung after its desktop loaded while Moonlight sent input early | Twice, under TCG and KVM. The tablet is a suspicion, not a finding; a run with `tablet: 0` (PS/2 mouse) is being tested (same section, b) |
| Windows 98: fatal exception 0E in VWIN32 when `WSHSPACE.EXE` was quit with Escape | Seen under TCG; not yet reproduced under KVM (same section, c) |
| Streaming with NVENC: Wolf scales and converts on the CPU (`videoscale`, `videoconvertscale`) before `nvh264enc` at the client's native resolution | Candidate: `cudaupload` and `cudaconvertscale`, as Wolf's own default apps do (same section, d) |

## The lab host

The self-hosted runner (label `sparc-lab`) holds what the lab needs and git does not:

| Path | Content |
| --- | --- |
| `/mnt/os/iso` | install media: SunOS 4.1.4, Solaris 2.4–10, and under `other-os/` NetBSD, OpenBSD (8.0 sparc64; 5.8 and 5.9 sparc), FreeBSD (12.4 sparc64), Debian (12 and 13 sparc64, 7.11 sparc netinst and CD 1, 4.0r9 sparc netinst), Ubuntu 9.04 server sparc, Alpine, Red Hat Linux 6.2, Tribblix, NeXTSTEP 3.3 (SPARC/PA-RISC), OPENSTEP 4.2 (User and Developer) |
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
`%softint` race, the ESP CDB counted with the message out bytes and the trap a bus error takes on a
SuperSPARC load (SunOS 4.1.3, `upstream/qemu-sparc32-supersparc-bus-error-trap.md`) and the VGA
attribute address read as 0 in the data state (The Incredible Machine,
`upstream/qemu-vga-ar-index-read.md`) (QEMU); the ESP selection timeout, Stop-A powering the machine
off, the sparc64 fixes 0003-0011 and 0013-0017, and the MMU miss handlers enabling interrupts at
TL 1 and the trap-state walk through TL 0 (0032-0033, found with FreeBSD 12.4) (OpenBIOS); the
SS-600MP's VMEbus registers, lebuffer and node names for SunOS 4.1.2 (both,
`upstream/qemu-sun4m-ss600mp-vme-lebuffer.md`).
Not written up yet: the TTE page-size truncation, if it is not merged upstream.

On hold until reproduced on plain QEMU without LEMU patches: the ESCC mouse rate and the audio
mixer's 6 dB on a mono output (seen with LEMU's CS4231). The `wav` backend's empty header sizes are
not CS4231's: the x86 audio matrix gets them from every x86 device on pve-qemu-kvm 11.1, whose wsh
patches don't touch QEMU's audio code; still to check on plain QEMU before a report.

The ESCC break that never ends reproduces on plain QEMU 11.1.3 (no wsh patches, the package's
OpenBIOS: Solaris 2.6's shell on ttya dead for 120 s after QMP `chardev-send-break`), so it can go
to QEMU as a bug report (`submodules/SPARC.md`, "Stop-A"; not written up yet). The fix, `wsh/0141`,
is written on top of LEMU's ESCC patches and stays ours.
