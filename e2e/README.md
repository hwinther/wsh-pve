# e2e

Playwright tests against a single-node Proxmox VE running in a container with the WSH packages.

- `tests/vm-config.spec.ts`: VMs with WSH options created through the API; checks the stored config,
  the QEMU command qemu-server builds (`qm showcmd`) and whether QEMU accepts it. Also OVMF (UEFI) VMs on
  x86 (q35, i440fx, with and without an efidisk) and aarch64: two pflash drives and no `-bios`.
- `tests/ui-hardware.spec.ts`: the pve-manager additions, set through the web UI's Hardware view,
  with the same checks.
- `tests/floppy.spec.ts`: floppy support across all three packages: the `floppy` storage content
  type and its upload tab, floppy drives on i440fx and q35 (and their refusal on other
  architectures), and Hardware → Add → Floppy Drive.
- `tests/mirror.spec.ts`: a mirror storage (a dir storage of symlinks to images in a NAS tree made in
  the container, folders in the names with `__`): the volumes with the targets' sizes, a dangling
  link left out (or, with step 3's libpve-storage-perl, listed as unavailable), removing a volume
  removes only the link, a VM keeps the volume ID; step 3's rename and link calls (in place, relative
  or absolute links, refusals, a user without `Datastore.Allocate`, a storage with a description file,
  a link to the NFS storage's ISO) and their Rename / Add link windows; and pve-manager's
  folder view (the ISO and floppy tabs grouped by folder, search, remove, the CD/DVD and floppy
  selectors showing `Solaris / 2.6 / ...`), and the search field above the ISO and floppy selectors
  (focus on open, every word must match, Enter picks). The four ways to use it: plain `__` names in a
  dir storage; links in a local storage; ISOs and links on one NFS export (the `nfs` service, NFS-Ganesha
  in user space, mounted as a PVE NFS storage and a second time at another path, with `wsh-lab mirror`
  from this checkout making relative links and its systemd timer); the changing tree is in
  `sparc/tests/test_mirror.py`. The UI tests probe the installed pve-manager and are skipped on one
  without the folder view or the search field. Without the `nfs` service the NFS tests use a dir storage
  and a bind mount and say so in an annotation.
- `tests/sparc-profiles.spec.ts`: the sparc32 profiles (`submodules/SPARC.md`): each one created
  through the API and the create wizard, the refused combinations, `arch` set on create only, the
  Hardware editors, vzdump/qmrestore and snapshots, the lab's machine arguments against
  `qm showcmd`, and a CD that answers as a disk (`cd_as_disk=1`: `scsi-hd` on target 6, read only,
  an empty `scsi-cd` once ejected, and its refusals). The `cd_as_disk` tests probe the installed
  qemu-server once: with a package that lacks the option the test of what it does is skipped and the
  refusals expect the older "property is not defined in schema" (the option is refused either way). The
  SS-600MP tests (OpenBIOS only, one CPU, the refusals with the Ross module as the reason, the wizard)
  are skipped where the installed qemu-server or pve-manager has no SS-600MP profile, and QEMU is
  started only with a pve-qemu-kvm that has its lebuffer (`wsh/0064`).
- `tests/sparc64-profile.spec.ts`: the sparc64 profile (`submodules/SPARC.md`, "sparc64 (sun4u)"):
  the wizard's layout through the API (IDE disk and CD-ROM, `-boot order=d|c`, no `bootindex` or
  balloon), a serial console, four NICs, every refusal, a VM from the old wizard, and the wizard and
  Hardware editors.
- `tests/running-vm.spec.ts`: changes to a started VM (QEMU under TCG, no guest OS) for every
  sparc32 profile, sparc64 and an x86 control: the CD-ROM medium, net0's bridge, VLAN tag, link and
  rate (checked in QEMU and on the host, with a VLAN-aware `vmbr1` it creates), the changes that stay
  pending on sparc, and clone, move disk, suspend/resume and reset.
- `tests/qemu-extras.spec.ts`: the optional extras of the installed `pve-qemu-kvm` (3dfx binary,
  sparc32 and sparc64 OpenBIOS and cg3 ROM from `openbios/`, Sun PROMs), with `scripts/check-qemu-extras.sh`. The package
  build never fails on them, so this is where a published package without one turns red. The 3dfx
  VM commands (`mesa=1`, with and without `server`) are in `vm-config.spec.ts`; QEMU is started with
  `-display none`, or SDL's dummy video driver for the SDL display, so neither the X display nor the
  pass-through itself is tested here. There too, a real `qm start` of a `mesa=1` VM checks that
  QEMU gets `OPENGLIDE_DIR=/run/qemu-server/<vmid>-3dfx` (root, 0700, kept after the stop) for
  OpenGLide's files, and a VM without `mesa` doesn't. The pass-through itself is tested by `3dfx/test.sh`
  (outside Playwright, in the `wsh-openglide package` workflow), with two Linux guests in the
  published `qemu-system-x86_64-3dfx` and an SDL display on Xvfb. Glide: `/init`
  (`3dfx/glide-guest.c`) draws a scene through qemu-3dfx's Linux guest wrapper into `wsh-openglide`
  on the host, with QEMU daemonized as qemu-server starts it and `OPENGLIDE_DIR` set (OpenGLide's
  files must land there, not in `/`). Mesa: `/init` (`3dfx/mesa-guest.c`, which speaks the mesapt
  device's protocol itself, as there is no Linux guest wrapper for it upstream) draws the same scene
  through the MESA GL pass-through into the host's libGL. Each guest checks what it reads back and
  the host checks the VM's window. `3dfx/win98-test.sh` does the same in a real Windows 98 SE
  guest, from the operator's own disk, through qemu-3dfx's Windows wrappers (Glide 2, Glide 3,
  OpenGL), on the self-hosted lab runner only (the `3dfx in Windows 98` workflow; see the 3dfx guide).
  `vm-config.spec.ts` also checks `mesa-display=egl-headless` (`-display egl-headless` next to the VNC
  server, and its refusals), and `ui-hardware.spec.ts` the Display dialog's **3DFX/Mesa display**; both
  are skipped with packages that predate it.
- `tests/3dfx-gl-display.spec.ts`: a 3dfx VM started by PVE (`qm start`, TCG) with the Glide guest of
  `3dfx/test.sh` (Debian's kernel and the guest through the VM's `args`), once with the default display
  and once with `mesa-display=egl-headless`: the test scene in PVE's noVNC console (pixels of the
  console canvas), and more open dmabufs in QEMU with egl-headless (wsh-openglide's export and
  egl-headless' import). On a node with neither a render node nor `/dev/udmabuf` it checks that the
  egl-headless VM is refused at the start instead. Skipped unless the guest is in the container:
  `3dfx/pve-guest-setup.sh [container]` builds it there (apt, gcc, Debian's kernel), for the revision of
  the container's 3dfx binary. `e2e.yml` runs it before the suite (`PVE_GUEST_FETCH=1` fetches the
  qemu-3dfx submodule) and sets `E2E_3DFX_GUEST=required`, which fails the spec instead of skipping it
  when the guest is missing. `3dfx/win98-test.sh --pve CONTAINER` runs the Windows 98 test through PVE
  in the same container (`qm create`/`qm start`; see the 3dfx guide).

- `tests/dbus-display.spec.ts`: QEMU's D-Bus display next to VNC (`vga: ...,display=dbus`,
  `mesa-display=dbus`, `dbus-refresh`, `audio0: driver=dbus`): the commands (x86, SS-5 with the
  CS4231, sun4u, the 3dfx binary with `gl=on`), the refusals, and a real `qm start` that checks the
  VM's bus (`wsh-dbus-display@<vmid>`, `/run/wsh-dbus-display/<vmid>.sock`, group `wsh-display`),
  `busctl tree org.qemu`, the VNC socket, that `nobody` can't connect, that the VM outlives a killed
  bus and that the stop removes it. Skipped with a qemu-server without it; the start also needs a
  pve-qemu-kvm with `refresh-ms` (`wsh/0131`). What a client gets (frames, refresh rate, sound) is
  measured with `3dfx/dbus-listener.py` (`DBUS_LISTENER_AUDIO=1` adds an `AudioOutListener`), and
  `3dfx/test.sh` with `GLIDE_DISPLAY=dbus DBUS_PICTURE=vnc` checks the Glide and Mesa frames in the
  picture VNC serves next to `dbus,gl=on`.

- `streaming/test.sh` (not a Playwright spec; workflow `Streaming to Moonlight`): a Moonlight
  client streams a VM's D-Bus display through Wolf. It builds Wolf, moonlight-embedded and our
  measuring client from source, runs QEMU (the published pve-qemu-kvm, wisp's framebuffer kernel)
  and Wolf in one container and the client in another, pairs them, and checks and measures the
  picture, the latency from the guest's draw to the decoded frame, frame pacing against the D-Bus
  display's refresh, keyboard, mouse and sound. Needs only Docker, also a remote one; see its
  header and the display reference, "Streaming to Moonlight".

"QEMU accepts it" means starting the generated command frozen (`-S`, no display, the tap swapped for a
hubport) and killing it: QEMU validates every machine, device and bus argument at startup, so a
command a real start would reject fails without running a guest.

Known bugs are marked `test.fail()`. They run, and turn red once fixed, so the marker gets removed.

## wisp, the tiny test system (`wisp/`)

A kernel plus a one-program initramfs (PID 1 built with the kernel's nolibc) for x86_64, i386, sparc32
(SS-5, SS-20) and sparc64 (sun4u), booted with `-kernel` on a serial console: banner, `uname`, CPU count,
memory, a compute loop with a checksum and its time, one result line, power-off. `wisp/build.sh` builds
it in the `wisp/Dockerfile` image, `wisp/run.py` boots it under a given QEMU binary (TCG or a TCI build
from `wisp/qemu-tci.sh`) and reports times to PID 1 and power-off, the loop time and QEMU's peak RSS. See
`wisp/README.md` and the [wisp](../docs/src/content/docs/guides/wisp.mdx) guide. The `Wisp boot`
workflow boots it on pull requests that change `wisp/` or the pve-qemu build, with the pull request's own
QEMU when `pve-qemu.patch` or the pin changes (`wisp/README.md`, "CI").

## The PVE container

`pve/Dockerfile` (build context: the repository root) installs `pve-manager`, `qemu-server`,
`pve-qemu-kvm`, `libpve-storage-perl` and `pve-cluster` from Proxmox, with the WSH builds pinned over them. It runs systemd
as PID 1 in a privileged container (pmxcfs mounts `/etc/pve` with FUSE), with only pve-cluster,
pvedaemon and pveproxy, a directory storage and an empty `vmbr0` bridge. The suite never starts a guest (the boot job below does).

- `--build-arg PACKAGES=repo` (default): the packages published at debian.wshosting.no.
- `--build-arg PACKAGES=local`: the `.deb` files in `pve/debs/` (the build-deb artifacts).
- `--build-arg PACKAGES=mixed`: the published packages, with the `.deb` files in `pve/debs/`
  installed over them (the boot job below: a pull request's qemu-server and pve-manager).

## Booting a guest through PVE (`boot`)

The suite never runs a guest, so a start-up bug that only shows once the firmware runs passes it
(the three fixed in #248 did). e2e.yml's `boot` job starts guests through PVE with the pull
request's packages, on a pull request that changes `submodules/qemu-server.patch`,
`submodules/pve-manager.patch` or `submodules/pve-qemu.patch` (or one of their pins, `pve/` or
`e2e.yml`):

- qemu-server is always built from the pull request (`make qemu-server`), pve-manager when its
  patch or pin changes (`make pve-manager` with `DEB_BUILD_OPTIONS=nocheck`); the image is built
  with `PACKAGES=mixed` and must carry both.
- When the pve-qemu build changes, `pve/build-qemu.sh` builds `qemu-system-x86_64` and
  `qemu-system-aarch64` from the pull request's tree (pve-qemu at its pin with `pve-qemu.patch` and
  `debian/patches`, debian/rules' paths and the options qemu-server's commands need) in the image
  and copies them over the published package's. No workflow builds the whole pve-qemu-kvm package
  on a pull request; firmware, keymaps and option ROMs stay the published ones.
- `pve/boot-test.sh` then creates each VM through the API (`pvesh create`), starts it with
  `qm start`, waits for the login prompt of an Alpine `virt` CD on the serial console
  (`serial0: socket`, `vga: serial0`) and stops it with `qm stop`.

| Case | Machine | Firmware | CD | Accelerator |
| --- | --- | --- | --- | --- |
| `i440fx` | x86_64 `pc` | SeaBIOS | `ide2` | KVM when the runner has `/dev/kvm`, else TCG |
| `q35` | x86_64 `q35` | SeaBIOS | `ide2` (AHCI) | as above |
| `ovmf` | x86_64 `q35` | OVMF, 4M efidisk | `ide2` (AHCI) | as above |
| `aarch64` | `virt` | OVMF (AAVMF), efidisk | `scsi0` (virtio-scsi) | TCG |

A case passes when the serial log shows firmware output (SeaBIOS, or OVMF's `BdsDxe` or GRUB on
OVMF's console) and then `login:` on the board's console port: Alpine's issue line names the tty,
`/dev/ttyS0` on x86_64 and `/dev/ttyAMA0` on aarch64. `login:` alone is not enough: Linux puts a
getty on whatever serial port it finds, so a socket wired to an extra UART instead of the console
port (#248's sparc64 bug) still gets a login prompt, on another tty and without the firmware's
output. The reader connects to the socket before `qm start`, as soon as QEMU creates it, because
the socket drops what the guest writes while no client is connected.

Checked in the lab with broken qemu-server copies (the installed `PVE/QemuServer.pm` edited in a
scratch container, not committed); `qemuAccepts` is the suite's check, run with the same configs:

| Breakage | `qemuAccepts` | Boot test |
| --- | --- | --- |
| #248's `-bios` fix reverted (`-bios ovmf` for every OVMF VM) | aarch64 fails (since #249's test), x86 passes | aarch64 fails at `qm start`; x86 OVMF boots (x86 QEMU ignores `-bios` next to the pflash drives) |
| aarch64 socket on a `pci-serial` instead of `-serial` (the PL011) | passes | aarch64 fails: no firmware output, login on `ttyS0` |
| x86 socket on COM2 (`isa-serial,index=1`) instead of COM1 | passes | `i440fx` and `q35` fail: no SeaBIOS output, login on `ttyS1` |

The ISOs (Alpine 3.24.4 `virt`, x86_64 and aarch64) are pinned by URL and sha256 in `pve/boot-media.sh` and
come from the Actions cache (next section). The job summary lists the packages under test and each case's result.
`e2e-required` includes the job, so a failed boot blocks the merge.

```bash
docker exec -i wsh-pve-e2e sh -s -- q35 9001 local:iso/alpine-virt-x86_64.iso < e2e/pve/boot-test.sh
# TCG on x86 too, as on a runner without /dev/kvm:
docker exec -i -e BOOT_TEST_TCG=1 wsh-pve-e2e sh -s -- i440fx 9002 local:iso/alpine-virt-x86_64.iso < e2e/pve/boot-test.sh
```

`sparc/pve.Dockerfile` adds the sparc lab to this image; there, guests do run (under TCG): VMs created
through the API, started by PVE and driven by the lab (`sparc/README.md`, "Attach to a PVE VM").

`audio/Dockerfile` adds the x86 audio matrix (`audio/audio_matrix.py`; workflow `audio-matrix.yml`):
a FreeDOS floppy with our own `AUDTEST.COM` and a Debian kernel + initramfs that play known tones
through each sound device, recorded with QEMU's `wav` backend and checked by `audio/wavcheck.py`,
directly and through qemu-server (`audio0: driver=wav`, `qm showcmd`, then a real `qm start` that
records). The results are described in the
[audio reference](../docs/src/content/docs/reference/audiodev.md). `audio/wavcheck.py --signature`
checks the audio signature of `wisp/audiosig.h` (8 segments of 500 ms, a different triangle wave
on each channel; reference, "The audio signature"), which wisp's `soundtest sig`
(`wisp/sound.py`) and wshspace's `-audiotest` (`3dfx/space/audio-test.sh` on Linux,
`3dfx/dos-test.sh` on DOS with an SB16) play; the workflow also runs `3dfx/space/audio-test.sh`.

## Downloaded media in the Actions cache

The test media that CI downloads from third-party mirrors, pinned by URL and checksum, are kept in
the repository's Actions cache: the Alpine virt CDs of the `boot` job (`pve/boot-media.sh`), the
NetBSD CDs of `sparc-lab-netbsd.yml` (`sparc/targets.py`, fetched and checked by
`sparc/fetch_media.py`), the fbDOOM and Freedoom archives of `wisp-boot.yml`
(`wisp/doom/fetch.py`) and the FreeDOS 1.4 Floppy Edition zip of `3dfx-dos.yml`, `sparc-lab-dos.yml`
and `audio-matrix.yml` (below). Only runs on main save them (push, schedule, dispatch); a pull request
restores main's entry (a pull request can read its base branch's caches) and never saves its own
copy, so the 10 GB cache holds each medium once instead of once per pull request, and the mirrors
see a download only when the cache has no entry. Each job restores the entry, then runs the fetch
script, which checks what was restored and downloads only what is missing or not the pinned
medium, then saves only on main and only when the restore missed (`actions/cache/restore` and
`actions/cache/save` instead of `actions/cache`).

`media-cache.yml` keeps main's entries present: daily, on dispatch, and when a pin changes on main,
it looks up each entry without downloading it, and on a miss (a new pin, or an entry GitHub evicted
after 7 days unused) downloads, checks and saves that medium. Its jobs must use the same key and
`path` as the jobs that restore the entries (the cache version depends on the path). A pull request
that changes a pin downloads the new medium on each run until it is merged and main has saved it.
A new workflow that downloads media follows the same pattern and gets a job in `media-cache.yml`.

The FreeDOS zip (`FD14-FloppyEdition.zip`) is one entry for its three workflows. Its URL, size and
sha256 are pinned once, in `sparc/targets_dos.py` (`FREEDOS_ZIP`): the lab test
(`sparc/tests/test_freedos.py`), the 3dfx DOS harness (`3dfx/dos/dos_test.py`) and the audio matrix
(`audio/audio_matrix.py`) import it, and their images carry `targets_dos.py` and `fetch_media.py` at
the same relative path as in the repository. Each job runs `python3 e2e/sparc/fetch_media.py --key
FD14-FloppyEdition.zip` for the key (`freedos-fd14-floppy-` and the first 16 hex digits of the
sha256, so a new pin is a new entry), restores `${{ runner.temp }}/freedos`, runs `fetch_media.py
"$RUNNER_TEMP/freedos" FD14-FloppyEdition.zip`, saves on main, and gives the harness the zip as
`FREEDOS_ZIP` (`dos-test.sh --freedos-zip`; a read-only mount for the lab and the audio node). A
harness checks a given `FREEDOS_ZIP` and never downloads over it; without one it downloads the pinned
zip into its `FREEDOS_CACHE` as before. `sparc/tests/test_fetch_media.py` checks that the pin has no
second copy and that the four workflows use the same key and path. `sparc-lab-dos.yml` runs on
GitHub-hosted runners (no lab host media), on pull requests and by hand, so on main only a dispatch
or `media-cache.yml` saves the entry.

## Running

```bash
docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
docker compose -f e2e/docker-compose.e2e.yml up -d --wait
cd e2e && npm ci && npx playwright install chromium && npx playwright test
```

Compose also builds and starts `nfs` (`nfs/Dockerfile`), the NFS server of the mirror tests.

The UI is at <https://localhost:8006> (root / `e2e-password`). The tests reach the container's shell
through the Docker Engine API: `DOCKER_HOST` (`tcp://…` or `unix://…`) or `/var/run/docker.sock`.

With a remote Docker host, published ports land on that host, so run Playwright in a container on
the compose network instead (`PVE_URL=https://pve:8006`, the Docker socket mounted).
