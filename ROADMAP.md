# Roadmap

Where the work stands and what comes next, in order. Written 2026-11-16. The details behind each
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
| Retro net archive cache: persistent store of Wayback answers, offline replay, warm-up from VintageHive's links, export/import; the test replays a synthetic dataset | in review | branch `feat/retro-net-archive-cache` |
| Solaris with more than one CPU on SS-10/SS-20 (interrupt after `wr %psr` in a delay slot), pve-qemu-kvm 11.1.3-2+wsh10 | published | #266 |
| Up to 4 CPUs in the SS-10/SS-20 OpenBIOS profiles (qemu-server, UI); boot with 2 CPUs through PVE in the `pve` matrix | in review | this PR |
| Workflow hardening (job-level permissions, explicit secrets), upstream notes for ESP, OpenBIOS and APC | merged | #237, #238 |
| Install targets: `lab.py install <target>` on a node makes an installed VM with known login details from tested media (Solaris 2.6 on SS-5 and SS-20); the `pve` matrix runs it | in review | branch `feat/lab-install-targets` |

## In progress

Work that exists but is not merged. If this list is stale, check the open pull requests.

1. **Solaris on sun4u (OpenBIOS).** `openbios/` builds a patched `openbios-sparc64` as an optional
   extra. Five patches fix the virtual `available` list, the I-cache properties and the Forth
   state at client start. With them Solaris 10 1/13 boots its DVD to the installer's `Select a
   Language` prompt (it panicked before), and NetBSD, OpenBSD `bsd.rd` and the Debian installer
   boot as before. Still to do:
   - install it in the package (`debian/rules` hook in `pve-qemu.patch`);
   - console input to Solaris on ttya (characters never reach the UART's receive buffer; QEMU side);
   - the cmd646 `Interrupt not seen` warning (paulsheer/qemu has a fix);
   - Solaris 7/8/9 `pp is NULL or free`;
   - 2.5.1/2.6 boot-block exceptions.
   Details: `submodules/SPARC.md`, "Solaris on sun4u".
2. **MCP server around the lab** (`e2e/sparc/mcp_server.py`, branch `feat/lab-mcp-server`). An
   assistant sees and drives an allowed VM (PVE by VMID or tag, or a `lab.py serve` QEMU): screenshot,
   screen text (terminal or OCR), keys and text on the display or serial console, serial reads by
   cursor, wait for a pattern; reset, stop and the monitor only behind flags. stdio only. Tested
   with Alpine under `lab.py serve` (CI job) and Solaris 2.6 on a cg3 through PVE in the test node.
   Still to do: a run from an interactive client (Claude Code over SSH), the mouse (relative Sun
   mouse), and installing it on the lab node. Details: `e2e/sparc/README.md`, "MCP server".
3. **Promotion PR for qemu-3dfx** (branch `ci/qemu-3dfx-promotion`). The daily sync no longer
   moves the pin on main. `promote-qemu-3dfx.yml` (after the fork sync, or by hand) opens or
   updates one PR, `promote/qemu-3dfx`, with the upstream commits, the port check and a 3dfx-only
   build (`scripts/check-qemu-3dfx-build.sh`, about 3 minutes on 4 CPUs instead of the 20-minute
   package build); `qemu-3dfx-check.yml` runs the same build on every PR that touches the pin, the
   port or pve-qemu. Merging rebuilds `pve-qemu-kvm`. Not yet run on GitHub: after merge, dispatch
   `promote-qemu-3dfx.yml` once. How the pin moves: the 3dfx guide.

## Next, in this order

1. **Idle with more than one CPU.** Each vCPU of a multiprocessor sparc32 guest spins at 100% of a
   host core even when Solaris is idle; a bounded halt in the multiprocessor idle loop is the
   follow-up (`submodules/SPARC.md`, "SMP").
2. **Solaris on sun4u: the next walls.** The first OpenBIOS patches are in (see "In progress"):
   Solaris 10 1/13 reaches its installer's first prompt. Next: console input on ttya, the cmd646
   interrupt, then disk, network and an install. QEMU's sun4u devices (CMD646 IDE, hme) are ones
   Solaris drives, so a kernel that boots has a disk and a network.
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
   - DOS installs from floppies as install targets: a boot floppy and a sequence of install
     floppies (`floppy` content type), swapped by `install.MediaSwapper` when SETUP asks, FDISK and
     FORMAT answered on the VGA text screen. The data model is in place; missing are an exact VGA
     text reader (the text buffer at 0xB8000 through QMP `pmemsave` instead of OCR), an x86 retro
     profile table, the scenarios, and FreeDOS media for CI (`e2e/sparc/README.md`, "DOS and other
     floppy installs").
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
  more targets (Solaris 2.5.1 needs the CD as a disk; 7, 8 and 9, SunOS 4.1.4 and NetBSD are in the
  catalogue with what blocks each). Today the weekly `pve` matrix reinstalls Solaris 2.6 on SS-5.
- **A boot through PVE on every PR that changes `qemu-server.patch`.** Alpine on aarch64 and x86
  takes about a minute and needs only a small ISO, so it could run on GitHub-hosted runners. The
  three start-up bugs fixed in #248 all passed the "QEMU accepts the command" tests.
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
| The SunOS 4.1.4 install kernel crashes QEMU with 256 MB (`Trap 0x29`) | 64 MB works; the installed system runs with 256 MB |
| `zs3: ring buffer overflow` in Solaris under load | Mouse data arrives faster than a 1200 baud mouse would send it; harmless. Pacing the ESCC mouse would remove it |
| X in Solaris 2.6 only starts at 1024x768 on cg3 | Larger sizes give a text console; qemu-server has no resolution option |
| More than 512 MB on SS-10/SS-20 (Solaris 2.6 panics at boot) | Unverified lead: the MiSTer SS-20 project's OpenBIOS splits memory into several `/memory` entries because Solaris 8 panics early with all of it in one (`submodules/SPARC.md`, "SMP") |
| A disk installed on SS-5 does not boot on SS-10/SS-20 | Device paths differ; needs a repair from the CD's miniroot, not written or tested |
| Solaris 2.5.1 and 2.6 idle on SS-10/SS-20/SS-5 only for the kernel builds in `SPARC.md` | A differently compiled idle loop is not recognised and spins as before |
| A CD that answers as a disk (Solaris 2.4/2.5.1 installers) has no option | Workaround: copy the ISO to a raw volume on `scsi6` |
| Live migration of a VM without `-cpu`; `qm suspend --todisk` | Not working or not tested |
| `floppy.spec.ts` "Hardware: Add -> Floppy Drive" times out on a fresh container | Passes on rerun; a cold-start flake |
| `sync-from-upstream-trigger.yml` cannot work | Its `gh workflow run` steps have no token |
| The issue path of the optional-extras report | Has only run with nothing missing |

## The lab host

The self-hosted runner (label `sparc-lab`) holds what the lab needs and git does not:

| Path | Content |
| --- | --- |
| `/mnt/sparc/iso` | install media: SunOS 4.1.4, Solaris 2.4–10, and under `other-os/` NetBSD, OpenBSD, Debian, Alpine |
| `/srv/sparc/disks` | installed disks the matrices boot, and the Sun-labelled disk templates |
| `/mnt/sparc/disks` | newer disks: sparc64 installs, the bench disk and its build disk |
| `/mnt/sparc/src` | SunOS 4.1.4 and Solaris 2.6 source, for reference only |
| `/mnt/sparc/prom` | Sun firmware updates, for experiments only |
| `/mnt/sparc/runs` | run output and evidence directories |

None of the Sun software, firmware or source goes into this repository or into anything published
from it.

## Upstream reports to send

Write-ups are in `upstream/`: the ESP bus reset bug (QEMU), the ESP selection timeout (OpenBIOS),
the 1-byte APC region (QEMU), the TLB flush on every change of the SRMMU no-fault bit (QEMU) and
the interrupt not taken after a write to `%psr` in a delay slot (QEMU, the Solaris SMP hang).
QEMU declines AI-generated code contributions, so these are bug reports, not patches. Candidates
not written up yet: the TTE page-size truncation if it is not merged upstream, and the ESCC mouse
rate.
