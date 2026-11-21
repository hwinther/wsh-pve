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
| Install target `sol21-ss10`: Solaris 2.1 End User on the SS-10 (OpenBIOS, one CPU, the CD as a disk), automated now that pve-qemu-kvm 11.1.3-2+wsh29 and later have `wsh/0047` (the sparc32 context-switch fetch); installed three times through PVE with `--check` on the published 11.1.3-2+wsh30, qemu-server 9.2.19+wsh4, pve-manager 9.2.32+wsh4 (3/3 passed, 9.7-10.1 min with three at once: install 5.3 min, first boot 2.9-3.3, check 1.2-1.3); `/opt` and `/export/home` still not mounted at boot | merged | #378 |
| OpenBSD 8.0 on sun4u with ntpd on: the IDE timeouts (`wd0: timeout`, then a guest that takes no interrupt) were a lost interrupt in QEMU's sabre (a PCI interrupt replaced the outstanding IDE request), fixed by pve-qemu `wsh/0045` (qtest `wsh/0046`, pve-qemu-kvm 11.1.3-2+wsh30); `openbsd80-sun4u` keeps ntpd on and checks it runs, no install retry (the stuck detection stays): 4 of 4 installs through PVE with `--check` (two with a way out, ntpd synced), 3 of 3 boots under disk load with ntpd slewing, no IDE timeout, ~17 min; the installer's "Exit to (S)hell" after "CONGRATULATIONS!" is answered again (broken by the OpenBSD 5.9 targets) | in review | |
| SunOS 4.1.3 on the SS-10: a bus error on a SuperSPARC load or instruction fetch takes the data or instruction access exception (trap 0x09/0x01, SFSR FT=5) instead of the access error (0x29/0x21), pve-qemu `wsh/0049` (CPU feature `buserr-access-exc` on the `TI-SuperSparc-*` models only; stores, the MMU bypass ASIs and the microSPARC unchanged), qtest `wsh/0050`; 4.1.3's kernel panicked in its VME probe (`BAD TRAP: type=29`). In the lab the 4.1.3 CD installs, boots and passes the check with the 4.1.4 scenarios (4 passes of 4, ~4.5 min each), stored SS-10/SS-20 and SS-5 disks boot as before (34 of 34: 18 on SS-10/SS-20, Solaris 2.6 also with 4 CPUs, and 16 on the SS-5); reproduced on plain QEMU 11.1.3. Target `sunos413-ss10` since 11.1.3-2+wsh31 (below), `upstream/qemu-sparc32-supersparc-bus-error-trap.md` | in review | |
| Install target `sunos413-ss10`: the original SunOS 4.1.3 Programmer install on the SS-10 (OpenBIOS, one CPU, the 4.1.4 scenarios unchanged), automated now that pve-qemu-kvm 11.1.3-2+wsh31 and later have `wsh/0049` (the SuperSPARC bus error trap); installed six times through PVE with `--check` on the published 11.1.3-2+wsh31, qemu-server 9.2.19+wsh4, pve-manager 9.2.32+wsh4 (5/6 passed, 5.9-6.1 min: install 2.2-2.4 min, first boot 2.5, check 0.9; 10.5 min on a busy host; one stopped on a console message from a second guest with the same static address, a test setup fault) | in review | |
| The Incredible Machine 1 and 2 (DOS) black on std and cirrus (every VGA model has the code): a read of the attribute address register (3C0h) returned 0 in the flip-flop's data state, the games restore what they read there after loading the palette, which clears the palette address source bit. pve-qemu `wsh/0051` returns the address in both states in `vga.c` and `cirrus_vga.c` (as the VGA and DOSBox do; 3C1h and the flip-flop unchanged), qtest `wsh/0052` (std, isa-vga, cirrus, vmware: 8 cases, all fail on plain QEMU 11.1.3). In the lab (11.1.3 with wsh/0001-0052, MS-DOS 6.22 with the owner's games) both games show their screens on std and cirrus (black without the patch; reproduced on plain 11.1.3 with the games, a 512-byte boot sector and the qtest); Doom, Doom II, Duke Nukem 3D, Wolfenstein 3D (`retrace=precise`), Keen 1 and 4, Larry 1, Dune and Dune II end on the same screen as without the patch (the same screendump, or the same running demo); the stored `msdos622` and `freedos14` disks pass their checks on std and cirrus; qtest-sparc unchanged. `upstream/qemu-vga-ar-index-read.md` | in review | |
| SPARCstation LX boot PROM (`lx.bin`, lab only): its POST stopped at `FPU SP Trap Priority <` because QEMU raised fp_exception on the excepting FPop; the sparc32 FPUs defer it to the next FP instruction, and a misaligned FP store after it takes its alignment trap first. pve-qemu `wsh/0053` models fp_exception_pending for IEEE 754 exceptions on every sparc32 CPU (system emulation; linux-user and sparc64 unchanged; V8 manual 7.3 and appendix L, the microSPARC and SuperSPARC manuals), qtest `wsh/0054` (36 cases on SS-5, SS-10 and LX; the 27 trap cases fail on plain QEMU 11.1.3), and `wsh/0055` caps the microSPARC-I machines (LX, SPARCClassic, SPARCbook) at the chip's 128 MB (OpenBIOS stopped with `Trap 0x21` at 256). In the lab the LX PROM passes all its FPU tests and reaches `ok` (still missing: stubs for its built-in SBus devices, then SunOS); Solaris 2.6 on SS-20 and SS-5 gets SIGFPE (`FPE_FLTDIV`, `si_addr` at the `fdivs`) 504 of 504 times and keeps running; 34 of 34 stored sparc32 disks boot and pass their checks as before (SS-5, SS-10, SS-20, Solaris 2.6 also with 4 CPUs); reproduced on plain QEMU 11.1.3. `upstream/qemu-sparc32-deferred-fp-exception.md` | in review | |
| SPARCstation LX with its own PROM (`lx.bin`, lab only) boots to a login prompt over ttya (`-nographic`): the PROM probes its on-board cgsix (slot 3), DBRI (slot 2) and bpp (slot 4) on every boot and stopped at `ok` on the first bus error. pve-qemu `wsh/0056` maps the three as unimplemented devices on `-M LX` (below a `-vga` frame buffer), `wsh/0057` answers the DBRI's FCode PROM window with an FCode program of ours that makes the node a DBRI has (name, `reg`, interrupt; SunOS 4.1.4 panicked on the node without it, as Solaris 2.1/2.2 do on the SS-20 PROM), qtest `wsh/0058`. In the lab: Solaris 2.6 installs from CD and boots (64 and 128 MB), NetBSD 9.3's stored disk boots (64, 128 MB), SunOS 4.1.4 and 4.1.3_U1B install and boot; the drivers find no codec behind the DBRI stub, the cgsix node stays unused; the Solaris 2.2 CD reaches its installer under the SS-20 PROM without the lab's node naming; 12 of 12 stored sparc32 disks boot as before, OpenBIOS on `-M LX` as before; qtest-sparc/sparc64 46 OK. `upstream/qemu-sun4m-lx-onboard-sbus.md`, `upstream/qemu-sun4m-ss20-dbri-unnamed-node.md` | in review | |
| SPARCstation LX in PVE: `machine: LX` with `bios: lx.bin` as a sparc32 profile in qemu-server and pve-manager (at most 128 MB, one CPU, `vga: serial0` by default or `none`, no OpenBIOS, no audio), cfg2cmd tests `sparc32-lx-*`, e2e in `sparc-profiles.spec.ts` (skipped against packages without the profile; QEMU started only where the node has `lx.bin`). In the lab's PVE container `qm start` boots the Solaris 2.6 LX disk to its login prompt (`boot disk` at `ok`). `lx.bin` goes into `pve-qemu-kvm` with the other Sun PROMs (`sun-proms` extra) (`submodules/SPARC.md`, "SPARCstation LX with its own PROM") | in review | |
| DOS games: `vga: ...,retrace=precise` in qemu-server and the UI (Hardware > Display, "VGA retrace: Precise (DOS games)"; x86 with a display on QEMU's VGA core: std, cirrus, vmware, qxl, virtio). QEMU takes its precise VGA retrace emulation only as a `-vga` option (no device property), so qemu-server adds `-vga none,retrace=precise` next to the `-device`; refused with `none`, `serial*`, `tcx`, `cg3` and off x86 at create, update and start. Wolfenstein 3D waits for display enable without vertical retrace on port 3DAh, which QEMU's default `dumb` emulation never reports: through PVE (TCG, the owner's MS-DOS 6.22 disks, the local qemu-server) it stays black in mode 13h for a minute with `vga: std` and shows its title and menu screens with `std,retrace=precise` (12 distinct screens in 60 s against 2). cfg2cmd tests, e2e (API, `qm showcmd`, QEMU accepts it, refusals, the UI field) with `test.fail` probes until a package has it | in review | |
| DOS memory profiles as data (`e2e/sparc/dos_profiles.py`, `scenarios/dos-profile.py`): Full (XMS + UMB, no EMS), EMS (frame at D800, set explicitly), Maximum conventional, No EMM386 and the disk's own files, for MS-DOS 6.22 and FreeDOS 1.4, also as one startup-menu `CONFIG.SYS`. Each profile is written onto a sparse copy of an installed disk with mtools (now in the lab image) and booted in the lab's QEMU; measured with `MEM` and four hand-assembled programs of ours (`dos_tools.py`: `EMSCHK` pages and frame, `VGARTRC` display enable on 3DAh, `VGAAR` the 3C0h data-state read, `SNDCHK` SB DSP + AdLib + PC speaker into the WAV), the screen and QEMU's guest-error log, and optionally a game per run (frames, last change, sound). CI: `tests/test_dos_profiles.py` in `sparc-lab-dos.yml` on the FreeDOS disk the job just installed (five profiles, the menu, plain `std` where VGARTRC must time out). VGAAR fails under pve-qemu-kvm 11.1.3-2+wsh16 and passes on 11.1.3-3+wsh2. Lab run on 11.1.3-3+wsh2 with the owner's MS-DOS 6.22 disks: the five profiles and a game matrix per profile; recommended profiles and results in the DOS guide ("Memory profiles") | in review | |
| DOS memory profiles, follow-up: the MS-DOS EMS profile gives EMM386 `RAM` without a size, so its EMS and VCPI pool is all free XMS (`RAM 4096` capped VCPI at 4 MB and Duke Nukem 3D, DOS/4GW, stopped for lack of memory); with it one boot runs all nine games of the matrix (Wolfenstein 3D with `retrace=precise`). A profile can bring its own `SHELL` line (also in a startup-menu block); MS-DOS 6.22's `MEM` line for a large EMS pool (no K, no closing parenthesis) is parsed. Wolfenstein 3D's black screen on plain `std` pinned down in the lab: its CRTC routine waits for several reads of "blanked, not in vertical retrace" on 3DAh, which `dumb` never gives (bits 0 and 3 flip together), and its timer-based timeout can't fire because the counter isn't running yet (sampled under TCG and KVM); no `CONFIG.SYS` changes it. DOS guide and display reference updated | in review | |
| 3dfx in a real Windows 98 SE guest (`e2e/3dfx/win98-test.sh`, workflow `3dfx in Windows 98`, by hand and weekly on the lab runner): the operator's own installed disk (never in the repository; path from an input or `WSH_WIN98_TEMPLATE`) is copied, the binary's `qemu-3dfx-drivers` release and our own test programs (mingw-w64, no C runtime: `glidetst.exe` for Glide 2 and 3, `gltest.exe` for OpenGL, `w3drun.exe` in StartUp, which powers Windows off) are written onto the copy with mtools, QEMU gets PVE's device set at PVE's PCI addresses (no new-hardware wizard); the programs report on COM1, the harness checks the frame in the console's screendump and the desktop after it; screendumps stay on the runner, the artifact has only logs and probe values. Published 11.1.3-3+wsh5: Glide 2 and 3 pass headless (KVM and TCG), OpenGL ends QEMU (SIGSEGV on loading `OPENGL32.DLL`); a binary from #407: all three pass (KVM 50-70 s a run, TCG 83 s; 1400-1700 Glide and 1900-2500 OpenGL frames/s). Found: the release's guest drivers need SSE2-SSE4.2/POPCNT, so `cpu: pentium3` without KVM faults ("illegal operation"); booting at the host's time can stop Windows 98 at a daylight-saving dialog | in review | |

## In progress

Nothing outside the open pull requests. Solaris 10 on sun4u (#294, #298) and Tribblix (#318) are
merged; what is left of them is item 2 under "Next".

## Next, in this order

**First, the Sun PROMs' NVRAM kept across starts,** so a Sun PROM's `setenv diag-switch? false`
lasts and it boots by itself (an M48T59 block backend plus a
per-VM volume in qemu-server; `submodules/SPARC.md`, "SPARCstation LX with its own PROM").

1. **Idle on sparc64, what is left.** The guests with a stored disk idle (see Done: `wsh/0042`-`0044`).
   Not covered: Linux on sun4u (Debian 12's install fails, so no disk; its `arch_cpu_idle()` does
   nothing on sun4u either), Solaris 8 (no stored disk yet; its `idle()` is probably laid out like 9's,
   not checked), other kernel builds than the ones in `SPARC.md`, and sun4v/`niagara` (hypervisor
   `cpu_yield`). Each new guest: disassemble its idle loop and add a layout with a qtest case.
2. **Solaris and Tribblix on sun4u, what is left.** Both install through `lab.py install`
   (`sol7-sun4u` to `sol10-sun4u`, `tribblix-m34-sun4u`). Open:
   - the firmware reboot: the installer's reboot and `reboot`/`init 6` return from the firmware;
     OpenBIOS 0012 (`.wip`) resets at the `ok` prompt but hangs when Solaris calls it (the tool stops
     or power-cycles the VM instead);
   - `sol10-sun4u` with `--ip dhcp` is not tested through the tool; Solaris 2.5.1/2.6 boot-block
     exceptions;
   - Tribblix: with a ZFS root FMA marks the IDE disk DEGRADED during the install (EIO on first
     attempts that ZFS retries, no data errors; a UFS install, `ROOT_FS=ufs`, hasn't been booted);
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
3. **x86 retro.** Starts from the owner's notes and known problems (DOS and the first megabyte of
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
     starts AC97/HDA muted; SB16 direct DAC isn't emulated; the wav header's sizes stay 0. Table and
     the headless-node answer (`pa` with `server=`, also for PipeWire desktops) in the
     [audio reference](docs/src/content/docs/reference/audiodev.md). Next: GUS and CS4231A (needs a
     DOS test for each); Windows guests (9x with SB16/ES1370, XP with AC97/HDA); listening on a
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
     - **Stage 2: dmabuf scanout (~2-3 weeks).** Zero copy: a `gbm_surface`,
       `qemu_console_gl_scanout_dmabuf` from a main-loop BH, `gl_block` back-pressure; shown through
       `egl-headless` and `-display dbus,gl=on`.
     - **Stage 3: the streaming client (~3-4 weeks).** A D-Bus listener in the Wolf/Sunshine
       container imports the dmabuf into the encoder; input through the D-Bus Keyboard/Mouse
       interfaces.
     - D-Bus display, found so far: `-display dbus` is in the package already and works without GL
       on VGA, cirrus, cg3 and TCX; its 30 ms refresh cap needs a small QEMU patch; the bus name
       `org.qemu` is fixed, so one dbus-daemon per VM; a dmabuf streamer must run on the same
       kernel (the host or an LXC). Quickest first step for remote sound from sparc32 guests:
       qemu-rdp (Marc-André Lureau's qemu-display project: D-Bus to RDP, with rdpsnd audio). LEMU's
       `-rdp` is the alternative without sound.
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
- **Browser SPARC (WebAssembly), researched 2026-11-21.** Run `qemu-system-sparc -M SS-5` on the
  docs site with QEMU's upstream Emscripten host support: wasm64 with the TCI interpreter is in
  11.1.3 (TCI is the only TCG backend there; the Wasm-emitting TCG backend is an out-of-tree series
  by Kohei Tokunaga, not in 11.2.0-rc1). The SS-5's devices need no change and `-bios` loads from
  Emscripten's file system, so OpenBIOS or a user's `ss5.bin` both work in principle; missing are a
  display backend (serial only at first), an audio backend and networking (a WebSocket proxy). Step 1:
  time a native `--enable-tcg-interpreter` build against the lab's SS-5 boots to estimate the speed.
  Step 2: a serial-only page (xterm.js, OpenBIOS and a NetBSD/sparc disk, `-nographic -nic none
  -audiodev none`, `coi-serviceworker` for the COOP/COEP headers GitHub Pages can't set, the disk
  fetched in ranges, optionally a migrated snapshot for an instant start), plus a local-only picker
  for `ss5.bin` and Sun disks, since Sun firmware and installed Sun systems are never published.
  Later: a canvas display with the Sun keyboard and mouse, WebAudio for the CS4231, and the Wasm TCG
  backend once it is upstream. Generic Wasm pieces (display and audio backends) are written against
  plain upstream QEMU; LEMU-derived code stays in wsh-pve.
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
  since (5/6 installs through PVE on +wsh31, in review, below). 4.1.2 (SS-600MP) is diagnosed and not
  planned: besides that trap it needs the SS-600MP's VMEbus interface registers at
  `0xf.df01_0000`, which QEMU's SS-600MP doesn't have, and its kernel knows the 4/600's
  `dma`/`esp`/`le` node names, not OpenBIOS's `espdma`/`ledma`. The SS-600MP needs a CPU model QEMU
  lacks: Sun's own SS-600MP boot PROM expects the Ross module's RT625 cache controller and MMU, which
  QEMU doesn't emulate, and under OpenBIOS Solaris 2.6 refuses the platform (`submodules/SPARC.md`).
  A Ross RT625 model would be a larger QEMU piece; not planned. OpenBIOS 0019-0022 run the Solaris
  2.1-2.4 boot program: 2.2 (SS-10), 2.3 and 2.4 (SS-5 and SS-20) are install targets under OpenBIOS
  since pve-qemu-kvm 11.1.3-2+wsh22 (`sol22-ss10`, `sol23-ss5`, `sol23-ss20`, `sol24-ss5`,
  `sol24-ss20`; 2.3 and 2.4 on the SS-20 also run with 2 and 4 CPUs); 2.1 stops in QEMU after its
  device configuration (its kernel switches to a context it hasn't filled yet). Fixed in pve-qemu
  `wsh/0047` (qtest `wsh/0048`, SPARC.md, "Older Sun releases on sun4m"), published in pve-qemu-kvm
  11.1.3-2+wsh29; `sol21-ss10` is an automated target since (3/3 installs through PVE on +wsh30).
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
- **sparc installs before merge for QEMU and OpenBIOS changes.** `sparc-lab-netbsd.yml` runs the
  NetBSD installs on the published pve-qemu-kvm (on lab changes, and daily once a new version is
  published), so a `submodules/pve-qemu.patch` or `openbios/**` change is first checked there after
  it is merged and built. Before merge it would need the PR's QEMU: not a full pve-qemu build, only
  `qemu-system-sparc`/`qemu-system-sparc64` from the patched source
  (`--target-list=sparc-softmmu,sparc64-softmmu`, about 10-15 minutes) and the OpenBIOS images,
  copied into the lab image in place of the package's, then the same four NetBSD targets.
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
- **WRP in retronet** (owner's request, 2026-11-21). Look into tenox7's Web Rendering Proxy (WRP),
  which renders modern pages as images (ISMAP/GIF) for old browsers, as a service next to the
  retronet gateway and vintagehive, so the Solaris/Netscape, Windows 9x and DOS guests can read
  today's web.
- **Demo ideas to show and post** (collected 2026-11-21; the owner drops what isn't wanted). Public
  demos use OpenBIOS and our own software only: no Sun PROMs, MS-DOS, Windows or NeXT material.
  1. *A SPARCstation 5 boots Linux in your browser*: the Browser SPARC item above with the tiny
     nolibc kernel+initramfs (`e2e/tiny/`) instead of a NetBSD disk, booting in seconds; optionally
     three terminals side by side (SS-5, sun4u, PC) running the same `init.c`, big- and little-endian
     in the banner.
  2. *A GitHub Action for big-endian testing*: build a C program for sparc32 v8 (nolibc or
     uClibc-ng), boot it in the tiny kernel under QEMU, return pass/fail in seconds; useful to other
     projects for endianness and alignment bugs.
  3. *The emulation ladder*: one compute loop native, under KVM, TCG, TCI and TCI-in-Wasm, and nested
     (sparc in x86 in Wasm), as a chart or short video, with the TCI numbers from the lab.
  4. *ASCII Mandelbrot or a ray tracer on the serial console* of all three architectures at once,
     recorded with asciinema and timed.
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
     Debian 4, Red Hat 6.2) and watch its install and first boot from the existing recordings.
  10. *Doom on sparc*: fbDOOM on the cg3/TCX framebuffer, then in the browser through Wasm; needs the
     tiny system's tier 2 (Buildroot with uClibc-ng) for a libc.

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
| 3dfx Glide: QEMU dies with `BadMatch` on an X server with a 32-bit ARGB visual | OpenGLide's GLX config picks the 32-bit visual, SDL's window has the 24-bit default (seen on Xvfb with Composite and Mesa; real Xorg with a hardware GLX not checked). `e2e/3dfx` runs Xvfb with `-extension Composite` |
| 3dfx offscreen (VNC console): no Glide MSAA; OpenGL MSAA only where the EGL driver reads a multisampled pbuffer back | Glide's framebuffer object is single-sampled (multisampled buffers would need a resolve before every LFB read and swap). OpenGL checks a test pbuffer when the window is made and renders without MSAA otherwise; Mesa's llvmpipe and softpipe can't. Stage 1b leftovers in the Streaming item |
| 3dfx Glide: OpenGLide writes `OpenGLid.ini`/`OpenGLid.log` into QEMU's working directory | And `exit(0)`s the process when it can't write there (its library constructor). Where qemu-server's QEMU runs from is not checked |
| 3dfx Glide: a guest LFB read that drains queued calls comes back shifted | glidept puts the pixels after the drained calls' data, the guest wrappers (Linux, Windows, DJGPP) copy from the start; a read after a swap or a direct call is right. Upstream (qemu-3dfx) material; `e2e/3dfx` reports it without counting it |
| 3dfx guest drivers need x86-64-v2 | The `qemu-3dfx-drivers` releases are built with `-march=x86-64-v2` (upstream's makefiles): a `cpu: pentium3` guest runs them under KVM only; under TCG it needs `+sse2,+sse3,+ssse3,+sse4.1,+sse4.2,+popcnt`. A build for i686 without SSE2 would let real Pentium III-era CPU models work everywhere; not tried |
| 3dfx with an SDL window: the second or third 3D window in one VM ends QEMU with an X error | Seen in the Windows 98 test on Xvfb (`BadRequest` when Glide 3 followed Glide 2, `BadLength` when OpenGL followed both); each test alone passes. Headless (offscreen) not affected |

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
`%softint` race, the ESP CDB counted with the message out bytes and the trap a bus error takes on a
SuperSPARC load (SunOS 4.1.3, `upstream/qemu-sparc32-supersparc-bus-error-trap.md`) and the VGA
attribute address read as 0 in the data state (The Incredible Machine,
`upstream/qemu-vga-ar-index-read.md`) (QEMU); the ESP selection timeout, Stop-A powering the machine
off, and the sparc64 fixes 0003-0011 and 0013-0017 (OpenBIOS).
Not written up yet: the TTE page-size truncation, if it is not merged upstream.

On hold until reproduced on plain QEMU without LEMU patches: the ESCC mouse rate and the ESCC break
that never ends (seen with LEMU's ESCC patches), and the audio mixer's 6 dB on a mono output (seen
with LEMU's CS4231). The `wav` backend's empty header sizes are not CS4231's: the x86 audio matrix
gets them from every x86 device on pve-qemu-kvm 11.1, whose wsh patches don't touch QEMU's audio
code; still to check on plain QEMU before a report.
