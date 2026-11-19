---
title: Mirror Storage Reference
description: ISO and floppy images from a NAS folder tree as symlinks in a directory storage, shown in folders in the web UI.
---

A **mirror storage** is an ordinary Proxmox VE `dir` storage whose `template/iso` and
`template/floppy` directories hold **symlinks** to ISO and floppy images that live somewhere else,
typically on a NAS in a deep folder tree. Nothing is copied: the storage is an index of the NAS.

It needs no backend change. PVE lists a dir storage's ISO and floppy directories with `stat()`,
which follows symlinks, so a link shows up as a volume with its target's size, QEMU opens the target
through the link, and removing the volume removes only the link. Symlinks cross file systems, so the
target may be on an NFS or CIFS mount.

## The folders are in the link's name

A volume name can't contain a `/`, so the folders are kept in the link's name, joined with a double
underscore:

| On the NAS (below the tree's top) | Volume |
| --- | --- |
| `Solaris/2.6/solaris_2.6_598_sparc.iso` | `mirror:iso/Solaris__2.6__solaris_2.6_598_sparc.iso` |
| `DOS/MS-DOS 6.22/Disk 1.img` | `mirror:floppy/DOS__MS-DOS_6.22__Disk_1.img` |
| `top-level.iso` | `mirror:iso/top-level.iso` |

VM configs and the API use the volume name as it is
(`ide2: mirror:iso/Solaris__2.6__solaris_2.6_598_sparc.iso,media=cdrom`). The web UI shows the
folders:

- the storage's **ISO Images** and **Floppy Images** tabs group the images by folder
  (`Solaris / 2.6`, files without `__` under **Top level**), with the file name in the row and the
  volume name as its tooltip. Sorting, search (on the whole volume name), upload, download from URL
  and remove work as before. A storage without such names shows the usual flat list;
- the ISO selector of the CD/DVD drive editor and of the create wizard, and the floppy selector, show
  `Solaris / 2.6 / solaris_2.6_598_sparc.iso`; typing filters on the volume name, so any folder or
  file name part finds it.

Only ISO and floppy volumes are split, and only names whose parts are all non-empty (`__a.iso` and
`a____b.iso` stay as they are).

## Making the links: `wsh-lab mirror`

The [`wsh-lab`](/guides/lab-install/#install-the-lab-on-a-node) package makes and checks the links,
on the node, as root:

```sh
# a dir storage for the links, with both content types
mkdir -p /srv/mirror
pvesm add dir mirror --path /srv/mirror --content iso,floppy

# link every ISO and floppy image below a NAS folder (again later: only what is new)
wsh-lab mirror sync /mnt/pve/nas/media --storage mirror
wsh-lab mirror sync /mnt/pve/nas/media --storage mirror --prune --dry-run   # what would change
wsh-lab mirror sync /mnt/pve/nas/media --storage mirror --prune

# one file, named after its path below --root, or with a name of your own
wsh-lab mirror link /mnt/pve/nas/media/Solaris/2.6/solaris_2.6_598_sparc.iso --storage mirror --root /mnt/pve/nas/media
wsh-lab mirror link /mnt/pve/nas/media/odd/name.iso --storage mirror --as Odd__name.iso

# the links, their targets, dangling ones (exit code 1 when there is one)
wsh-lab mirror list --storage mirror
```

- **Content by extension**: `.iso` is an ISO; `.ima` and `.vfd` are floppies; `.img` (both kinds use
  it) is a floppy up to 2.88 MB and an ISO above, unless `link --content iso|floppy` or
  `sync --img-as iso|floppy` says otherwise.
- **Names**: each folder and file name is cleaned the way PVE cleans an uploaded file's name:
  characters other than `A-Z a-z 0-9 _ . -` become `_` (a run of them one `_`), so no space or
  comma reaches a VM config. The result must split back on `__` into the same parts, so a folder or
  file name that contains `__` and a folder whose name ends in `_` are **refused**: rename it on the
  NAS, or link it by hand with `--as`. `sync` reports such files, and two files that would get the
  same name, as conflicts (exit code 1) and links the rest.
- **Safety**: the tool only creates, replaces (`link --force`) and removes symlinks. A regular file of
  the same name in the storage is never touched (a conflict); link targets are absolute paths. It
  refuses a storage that isn't of type `dir` and one without `iso` or `floppy` content, and reads the
  storage's paths, `content-dirs` included, from `/etc/pve/storage.cfg`.
- **`--prune`** removes links whose target is gone **or outside the synced tree**. Keep one mirror
  storage per tree, or links made with `link` from other places are pruned.

## Caveats

- **Cluster**: links are plain files on one node's disk, but the targets must be at the same path on
  every node that runs the VMs (mount the NAS share at the same mount point everywhere). Marking the
  storage `shared` only makes sense when the link directory itself is shared.
- **A dangling link hides the volume**: when the NAS is not mounted or a file moved, PVE doesn't list
  the volume, and a VM whose drive points at it doesn't start (the CD/DVD drive can be set to "no
  media" first). `wsh-lab mirror list` shows dangling links; `sync --prune` removes them.
- **Uploads are regular files**: an upload or download from URL into the mirror storage writes a real
  file in `template/iso` or `template/floppy`, not onto the NAS. `wsh-lab mirror` leaves such files
  alone.
- **Write access**: floppy drives are writable by default, and a write goes through the link to the
  NAS file. Add `ro=1` to the drive for reference media.
- **Install targets** find a medium by name first, then by size and sha256 among the storage's
  volumes: `wsh-lab media` and `wsh-lab install --media-storage mirror` find
  `Solaris__2.6__solaris_2.6_598_sparc.iso` as `solaris_2.6_598_sparc.iso`
  ([Lab install targets, Media](/guides/lab-install/#media)).

## Further reading

- [Floppy Device Reference](/reference/floppy/) — the floppy content type
- [Lab install targets](/guides/lab-install/) — the `wsh-lab` package
