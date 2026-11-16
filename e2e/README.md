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
- `tests/sparc-profiles.spec.ts`: the sparc32 profiles (`submodules/SPARC.md`): each one created
  through the API and the create wizard, the refused combinations, `arch` set on create only, the
  Hardware editors, vzdump/qmrestore and snapshots, and the lab's machine arguments against
  `qm showcmd`.
- `tests/running-vm.spec.ts`: changes to a started VM (QEMU under TCG, no guest OS) for every
  sparc32 profile, sparc64 and an x86 control: the CD-ROM medium, net0's bridge, VLAN tag, link and
  rate (checked in QEMU and on the host, with a VLAN-aware `vmbr1` it creates), the changes that stay
  pending on sparc, and clone, move disk, suspend/resume and reset.
- `tests/qemu-extras.spec.ts`: the optional extras of the installed `pve-qemu-kvm` (3dfx binary,
  OpenBIOS and cg3 ROM from `openbios/`, Sun PROMs), with `scripts/check-qemu-extras.sh`. The package
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

`sparc/pve.Dockerfile` adds the sparc lab to this image; there, guests do run (under TCG): VMs created
through the API, started by PVE and driven by the lab (`sparc/README.md`, "Attach to a PVE VM").

## Running

```bash
docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
docker compose -f e2e/docker-compose.e2e.yml up -d --wait
cd e2e && npm ci && npx playwright install chromium && npx playwright test
```

The UI is at <https://localhost:8006> (root / `e2e-password`). The tests reach the container's shell
through the Docker Engine API: `DOCKER_HOST` (`tcp://…` or `unix://…`) or `/var/run/docker.sock`.

With a remote Docker host, published ports land on that host, so run Playwright in a container on
the compose network instead (`PVE_URL=https://pve:8006`, the Docker socket mounted).
