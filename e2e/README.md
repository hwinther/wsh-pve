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
  refusals expect the older "property is not defined in schema" (the option is refused either way).
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
  pass-through itself is tested.

"QEMU accepts it" means starting the generated command frozen (`-S`, no display, the tap swapped for a
hubport) and killing it: QEMU validates every machine, device and bus argument at startup, so a
command a real start would reject fails without running a guest.

Known bugs are marked `test.fail()`. They run, and turn red once fixed, so the marker gets removed.

## The PVE container

`pve/Dockerfile` (build context: the repository root) installs `pve-manager`, `qemu-server`,
`pve-qemu-kvm`, `libpve-storage-perl` and `pve-cluster` from Proxmox, with the WSH builds pinned over them. It runs systemd
as PID 1 in a privileged container (pmxcfs mounts `/etc/pve` with FUSE), with only pve-cluster,
pvedaemon and pveproxy, a directory storage and an empty `vmbr0` bridge. No guest is ever started.

- `--build-arg PACKAGES=repo` (default): the packages published at debian.wshosting.no.
- `--build-arg PACKAGES=local`: the `.deb` files in `pve/debs/` (the build-deb artifacts).
- `--build-arg PACKAGES=mixed`: the published packages, with the `.deb` files in `pve/debs/`
  installed over them (the boot job below: a pull request's qemu-server).

## Booting a guest through PVE (`boot`)

The suite never runs a guest, so a start-up bug that only shows once the firmware runs passes it
(the three fixed in #248 did). On a pull request that changes `submodules/qemu-server.patch` (or
`pve/boot-test.sh`, `pve/Dockerfile`, `e2e.yml`), e2e.yml's `boot` job builds that qemu-server
(`make qemu-server`), builds the image with `PACKAGES=mixed` and runs `pve/boot-test.sh` in it:
`qm create` and `qm start` of an Alpine `virt` CD on x86_64 (i440fx, SeaBIOS, KVM when the runner
has it) and on aarch64 (virt, OVMF with an efidisk, TCG; skipped when the image has no
`qemu-system-aarch64` or no `AAVMF_CODE.fd`), passing when the serial console shows the login
prompt. The ISOs are pinned by URL and sha256 in e2e.yml and cached. `e2e-required` includes the
job, so a failed boot blocks the merge.

```bash
docker exec -i wsh-pve-e2e sh -s -- x86_64 9001 local:iso/alpine-virt-x86_64.iso < e2e/pve/boot-test.sh
```

`sparc/pve.Dockerfile` adds the sparc lab to this image; there, guests do run (under TCG): VMs created
through the API, started by PVE and driven by the lab (`sparc/README.md`, "Attach to a PVE VM").

`audio/Dockerfile` adds the x86 audio matrix (`audio/audio_matrix.py`; workflow `audio-matrix.yml`):
a FreeDOS floppy with our own `AUDTEST.COM` and a Debian kernel + initramfs that play known tones
through each sound device, recorded with QEMU's `wav` backend and checked by `audio/wavcheck.py`,
directly and through qemu-server (`qm showcmd`, `qm start`). The results are described in the
[audio reference](../docs/src/content/docs/reference/audiodev.md).

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
