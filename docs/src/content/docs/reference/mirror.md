---
title: Mirror Storage Reference
description: ISO and floppy images from a NAS, a torrent folder or any other tree as symlinks in a storage, shown in folders in the web UI, kept up to date from a description file.
---

A **mirror storage** is an ordinary Proxmox VE storage whose `template/iso` and `template/floppy`
directories hold **symlinks** to ISO and floppy images that live somewhere else: a NAS in a deep
folder tree, a VMware datastore being migrated, a folder of archive.org torrents that must stay as
they are for seeding. Nothing is copied: the storage is an index of the files.

The links themselves need no backend change. PVE lists a storage's ISO and floppy directories with
`stat()`, which follows symlinks, so a link shows up as a volume with its target's size, QEMU opens the
target through the link, and removing the volume removes only the link. Links work in `dir`, `btrfs`,
`nfs` and `cephfs` storages, and in `cifs` storages mounted with `mfsymlinks`. The WSH
libpve-storage-perl adds a [rename and an "add link" call](#rename-and-link-from-the-web-ui-and-the-api)
with buttons in the web UI, and lists a link whose target is gone as
[unavailable](#a-link-whose-target-isnt-reachable) instead of hiding it.

## The folders are in the volume's name

A volume name can't contain a `/`, so the folders are kept in the name, joined with a double
underscore:

| File (below the tree's top) | Volume |
| --- | --- |
| `Solaris/2.6/solaris_2.6_598_sparc.iso` | `mirror:iso/Solaris__2.6__solaris_2.6_598_sparc.iso` |
| `DOS/MS-DOS 6.22/Disk 1.img` | `mirror:floppy/DOS__MS-DOS_6.22__Disk_1.img` |
| `top-level.iso` | `mirror:iso/top-level.iso` |

VM configs and the API use the volume name as it is
(`ide2: mirror:iso/Solaris__2.6__solaris_2.6_598_sparc.iso,media=cdrom`). The web UI shows the
folders, in **any** storage, links or not:

- the storage's **ISO Images** and **Floppy Images** tabs group the images by folder
  (`Solaris / 2.6`, files without `__` under **Top level**), with the file name in the row and the
  volume name as its tooltip. Sorting, search (on the whole volume name), upload, download from URL
  and remove work as before. A storage without such names shows the usual flat list;
- the ISO selector of the CD/DVD drive editor and of the create wizard, and the floppy selector, show
  `Solaris / 2.6 / solaris_2.6_598_sparc.iso`.

Only ISO and floppy volumes are split, and only names whose parts are all non-empty (`__a.iso` and
`a____b.iso` stay as they are).

### The search field

The CD/DVD drive editor, the floppy drive editor (both on the VM's **Hardware** tab) and the create
wizard's **OS** tab have a **Search** field above the storage and image selectors. It has the focus
when the window opens (in the wizard, when the OS tab is shown), so you can type right away:

- it filters the image list as you type and opens it with what is left;
- case doesn't matter, and a word matches anywhere in the volume's name, folders included;
- several words separated by spaces must all match: `solaris 2.6` finds
  `Solaris__2.6__solaris_2.6_598_sparc.iso`, `598` finds it too;
- **Enter** picks the first entry left; a second Enter submits the dialog;
- an empty field shows every image, as before. The search changes nothing in the volume IDs or the
  VM config, and works the same in a storage without `__` names.

## Four ways to use it

None is forced: pick the simplest one that covers your media.

### 0. Plain files with `__` names

Rename (or upload) the images in any ISO/floppy storage with their folders in the name:
`Solaris__2.6__solaris_2.6_598_sparc.iso`, with the storage's **Rename** button or by hand. The UI
shows the folders; there are no links and no tool. A rename changes the volume ID, so set the CD drive
of VMs that use the image to the new name.

### 1. One node: a local storage of links

A local `dir` (or `btrfs`) storage holds links to images on anything mounted on the node: a NAS share,
a second disk. Link a whole tree with `wsh-lab mirror sync`, or describe it in a
[description file](#the-description-file) and run `apply`:

```sh
mkdir -p /srv/mirror
pvesm add dir mirror --path /srv/mirror --content iso,floppy
wsh-lab mirror sync /mnt/nas/media --storage mirror        # every image below the folder
```

The links point at absolute paths, so VMs on other nodes find the images only where the share is
mounted at the same path.

### 2. A cluster: ISOs and links on one NFS export

Keep the images and the mirror on the same NFS export (or CephFS; CIFS only with `mfsymlinks`) and
add it as a PVE storage with `iso` and `floppy` content. The images go below a folder of their own on
the export, the description file at its top:

```text
/export (the PVE storage "nasmirror", mounted at /mnt/pve/nasmirror on every node)
├── wsh-mirror.yaml
├── archive/Solaris/2.6/solaris_2.6_598_sparc.iso
└── template/iso/Solaris__2.6__solaris_2.6_598_sparc.iso -> ../../archive/Solaris/2.6/solaris_2.6_598_sparc.iso
```

```sh
pvesm add nfs nasmirror --server nas.example --export /export --content iso,floppy --options vers=4.2
wsh-lab mirror init --storage nasmirror --watch /mnt/pve/nasmirror/archive
wsh-lab mirror import --storage nasmirror && wsh-lab mirror apply --storage nasmirror
```

The links are **relative**, because each image is on the same file system as the link directory, so
they work wherever the export is mounted, and every node sees the same links. One node runs `apply`
(or a [timer](#a-changing-archive) on each node: a lock on the export lets only one run at a time).

### 3. An externally managed tree

The files are organised by something else and must stay where they are: a VMware migration's
datastore, torrents still seeding, hand-made folders next to them. The source needn't be a PVE storage
at all (an fstab mount, a storage whose content isn't `iso`; as an ISO storage it would look empty,
since PVE lists only files directly in `template/iso`). A [description file](#the-description-file)
stitches them into one tree: rules give each source a folder prefix, entries name single files, and
`import` adds what nothing covers yet. A [timer](#a-changing-archive) keeps the links up to date while
files arrive.

```yaml
# wsh-mirror.yaml at the root of the mirror storage
version: 1
storage: mirror
watch:
  - path: /mnt/torrents/complete
    prefix: Torrents
auto_import: false
incomplete:
  patterns: ['*.part', '*.!qB', '*.!ut', '*.incomplete', '*.crdownload', '*.partial']
  min_age: 5min
links: auto
rules:
  - source: /mnt/vmware/iso # every image below it
    prefix: VMware
    exclude: ['*/old/*']
  - source: /mnt/archive/sunsite/*/*.iso # a glob
    prefix: Sun
    flatten: true # the file name alone after the prefix
entries:
  # hand-made names for files that already are in VM configs
  - name: Solaris__2.6__solaris_2.6_598_sparc.iso
    source: /mnt/archive/sol-2.6-598-sparc.iso
    origin: manual
  - name: Torrents__debian-40r9-sparc__netinst.iso
    source: /mnt/torrents/complete/debian-40r9-sparc/netinst.iso
    origin: import
```

## The description file

`wsh-mirror.yaml` at the mirror storage's root (its `path`; PVE doesn't see the file) is the source of
truth: the links are derived from it. `wsh-lab mirror init` writes a commented one. A per-node mirror
can keep the file elsewhere, for instance in `/etc/pve/nodes/<node>/`, with `--config PATH` on every
command. Paths in it are absolute, or relative to the storage's root.

| Key | Meaning |
| --- | --- |
| `version` | `1` |
| `storage` | the PVE storage the file belongs to (checked; lets `--config` alone find it) |
| `watch` | directories (or `{path, prefix}`) whose images `plan` reports when no rule or entry covers them; `import` adds them as entries |
| `auto_import` | `true`: `apply` also links what `watch` finds and nothing covers, named by the default rule (the path below the watch directory, its folders joined with `__`, after the prefix); `false` (default): such files wait in `plan` until `import` |
| `incomplete.patterns` | names (of the file or any folder above it below its source) that are never linked; default `*.part`, `*.!qB`, `*.!ut`, `*.incomplete`, `*.crdownload`, `*.partial` |
| `incomplete.min_age` | a file changed (mtime) less than this ago isn't linked yet: `300`, `30s`, `5min`, `2h` (default 5 min) |
| `links` | `auto` (default): relative when the file is on the link directory's file system, inside its mount, else absolute; or always `relative`, `absolute` |
| `checksums` | `true` (default): `apply` records each linked file's sha256 once (to recognise a moved file); `false`: by inode only |
| `rules` | `source` (a directory, or a glob with `*`, `?`, `[...]`, `**`), `prefix` (folders, `Sun/Solaris`), `exclude` (patterns on the path below the source or the file name), `img_as` (`auto`, `iso`, `floppy` for `.img`), `flatten`. The first rule that matches a file names it |
| `entries` | `name` (the volume name), `source`, `origin` (`manual`, the default, or `import`), `content` (`iso`/`floppy`, for `.img`). A file with an entry is linked under the entry's name only, not by a rule |

YAML comments are kept: `import` and `tidy` edit only the entries they add, drop or change.

## Commands

All on the node, as root; `--storage S` names the mirror storage (or `storage:` in the `--config`
file).

| Command | What it does |
| --- | --- |
| `wsh-lab mirror init --storage S [--watch DIR ...]` | writes a commented `wsh-mirror.yaml` |
| `wsh-lab mirror plan --storage S [--json]` | what `apply` would link, relink and unlink; files no rule or entry covers (`new`); entries whose file is gone or moved (the same size and sha256 at a new path); name clashes; files still being written (`waiting`); links `apply` didn't make (`unmanaged`). Exit code 1 on clashes, conflicts or errors |
| `wsh-lab mirror apply --storage S [--dry-run] [--quiet]` | makes the links match the file. Idempotent, under a lock (`.wsh-mirror.lock` at the storage's root, an NFS lock on an export: exit code 75 while another run holds it, `--wait SECONDS` to wait). It never touches a regular file, nor a link it didn't make (its links are listed in `.wsh-mirror-state.json`), except to take over a link that already leads to the same file |
| `wsh-lab mirror import --storage S [--dry-run]` | **merges**: adds an entry (`origin: import`) for each complete file below a watch directory that no rule or entry covers, named by the default rule; never changes an existing entry |
| `wsh-lab mirror tidy --storage S [--dry-run] [--include-manual]` | drops entries whose file is gone and writes a moved file's new path into its entry; `import` entries only, unless `--include-manual` |
| `wsh-lab mirror timer --storage S [--interval 10min] [--remove]` | installs (or removes) a systemd timer that runs `apply --quiet` |

What `apply` does with files that are gone or moved:

- a file that moved (found again by size and sha256) keeps its entry's volume name: `apply` links
  the name to the new place at once, `tidy` writes the new path into the file;
- the link of a rule or an imported entry whose file is gone is removed; the link of a **manual**
  entry is kept and flagged (`tidy --include-manual` drops the entry);
- when a source's share isn't mounted (its directory is missing or empty), nothing below it counts as
  gone: links are kept and flagged as unreachable, and `tidy` keeps the entries.

**Renaming** a volume: edit its entry's `name` (or add an entry for a file a rule names) and run
`apply`; the old link goes, the new one comes. Set the CD drive of VMs that use the old name to the
new one. The web UI's Rename and Add link buttons and their API calls refuse a storage with a
description file (see [below](#a-storage-with-a-description-file)).

## Rename and link from the web UI and the API

In a `dir`, `btrfs`, `nfs`, `cephfs` or `cifs` storage, the **ISO Images** and **Floppy Images** tabs
have two more buttons:

- **Rename** renames the selected volume in place: a link is renamed itself (its target stays where
  it is), a regular file is renamed. The window takes a **Folder** (`Solaris / 2.6`, empty for the top
  level) and a **File name**, cleans them the way an upload's name is cleaned, and shows the resulting
  volume ID. It lists the VMs (that you may see) whose config uses the volume: a rename changes the
  volume ID and their drives keep the old one, so they don't start until the drive is set to the new
  name.
- **Add link from storage** links a volume of another storage in: pick the source with the same
  search field, storage and image selectors as the CD/DVD editor (the storage itself isn't offered),
  then the folder and file name of the link (prefilled from the source's name).

The buttons show only where the call is allowed: a storage type that can hold links, `Datastore.Allocate`
on the storage, and no description file.

### The API

| Call | Parameters | Permission |
| --- | --- | --- |
| `PUT /nodes/{node}/storage/{storage}/content/{volume}` | `rename`: the new file name, folders joined with `__` | `Datastore.Allocate` on the storage |
| `POST /nodes/{node}/storage/{storage}/link-volume` | `source-storage`, `volume` (`iso/name.iso`, or the full volume ID), `filename` (the link's name), `content` (`iso`/`floppy`, default the source's) | `Datastore.Allocate` on the storage **and** on the source storage |

```sh
pvesh set /nodes/pve1/storage/mirror/content/mirror:iso/sol-2.6.iso --rename Solaris__2.6__sol-2.6.iso
pvesh create /nodes/pve1/storage/mirror/link-volume --source-storage nas --volume iso/netbsd-9.3-sparc64.iso \
    --filename NetBSD__9.3__netbsd-9.3-sparc64.iso
```

The rename is a parameter of the content update call (`PUT`, which also sets notes and protection;
`rename` can't be combined with them): everything after `content/` in the URL is the volume ID, so the
content path has no room for a sub-path. The link call sits next to `upload` and `download-url`, the
other two ways a file gets into a storage's ISO and floppy directories. Both are synchronous; the link
call returns the new volume ID.

Both refuse:

- a name that exists, a dangling link of that name included (nothing is overwritten);
- a name with `/`, with characters other than `A-Z a-z 0-9 _ . -`, starting with `.`, with an empty
  folder (`a____b.iso`), or whose extension isn't one of the content type's (`.iso`/`.img` for ISO
  images; `.img`/`.ima`/`.vfd` for floppy images);
- other volume types and storage types, and a storage without that content type.

The link call also refuses a source in the same storage (rename it instead), a source that isn't a file
on the node that runs the call, and in a **shared** storage a source that not every node of that
storage has: a source storage that isn't shared, or is limited to fewer nodes (`nodes`).

The link is **relative** when the source is on the link directory's file system, inside its mount (the
rule of a description file's `links: auto`), and **absolute** otherwise: a link from an NFS storage's
ISO into a local mirror points at `/mnt/pve/<nfs-storage>/template/iso/...`, the path PVE mounts that
storage at on every node.

**Why `Datastore.Allocate` on the source too:** a link makes the source volume usable by everyone who
may use the mirror storage, also users who can't see the source storage. Only someone who could manage
the source storage's content may publish it that way. `Datastore.Audit` on the source is not enough.

### A storage with a description file

When `wsh-mirror.yaml` (or `.wsh-mirror-state.json`, which `apply` writes at the storage's root even
when the description file is elsewhere with `--config`) is at the storage's root, both calls are refused
and the buttons are hidden: the description file is the source of truth, and the next `apply` would
undo the change (a renamed link would come back under its old name, and the new one would be left as
an unmanaged link). Edit the file's entries instead and run `wsh-lab mirror apply`. The storage's
status (`GET /nodes/{node}/storage/{storage}/status`) has `mirror-described: 1` then.

Writing the change into the file from the API was the alternative: the API is Perl, the file is YAML
whose comments `wsh-lab mirror` keeps, and the edit would have to take the same lock as `apply` and
agree with its rules and entries. Refusing is simpler and can't lose a comment or race with a timer's
`apply`. A description file kept elsewhere with `--config` on a storage that `apply` hasn't run on yet
isn't seen.

### A link whose target isn't reachable

A link whose target is gone on this node (a share that isn't mounted here, a file that moved) is listed
with size 0 and `unavailable: 1`; before, PVE didn't list it at all. The ISO and floppy tabs show it
with a warning sign and "(unavailable on this node)", where it can be renamed or removed. The CD/DVD
and floppy selectors leave it out, and a VM whose drive uses it doesn't start on that node.

In a **cluster** the listing is per node (the API call runs on the node in the URL): a link in a local
storage exists on its node only; a link in a shared storage is seen by every node, and is unavailable
on a node where its target isn't mounted. That is why the link call refuses a link in a shared storage
to a volume of a storage that isn't on every node.

## A changing archive

Torrents still downloading, files copied in by hand: inotify doesn't see writes made on the NFS server
or by other clients, so a **scheduled job** keeps the links up to date:

```sh
wsh-lab mirror timer --storage nasmirror --interval 10min    # wsh-lab-mirror-nasmirror.timer
systemctl list-timers wsh-lab-mirror-nasmirror.timer
journalctl -u wsh-lab-mirror-nasmirror.service
wsh-lab mirror timer --storage nasmirror --remove
```

Each run is an `apply`: new files under a rule (and with `auto_import`, below a watch directory) are
linked, links of removed files go. Several nodes may run the timer on a shared export: the lock lets one
run at a time and the others skip that round.

**Incomplete files are never linked**: a file whose name (or a folder above it) matches
`incomplete.patterns`, or that changed less than `min_age` ago, waits (`plan` lists it as `waiting`).
Better still, let the download client keep unfinished files in a separate folder outside the watched
tree and move them in when they are complete (qBittorrent, Transmission and others have an
"incomplete downloads" folder setting).

## Linking by hand: `link`, `sync`, `list`

Without a description file:

```sh
# link every ISO and floppy image below a folder (again later: only what is new)
wsh-lab mirror sync /mnt/pve/nas/media --storage mirror
wsh-lab mirror sync /mnt/pve/nas/media --storage mirror --prune --dry-run   # what would change
wsh-lab mirror sync /mnt/pve/nas/media --storage mirror --prune

# one file, named after its path below --root, or with a name of your own
wsh-lab mirror link /mnt/pve/nas/media/Solaris/2.6/solaris_2.6_598_sparc.iso --storage mirror --root /mnt/pve/nas/media
wsh-lab mirror link /mnt/pve/nas/media/odd/name.iso --storage mirror --as Odd__name.iso

# the links, their targets, dangling ones (exit code 1 when there is one)
wsh-lab mirror list --storage mirror
```

`link` and `sync` write absolute link targets (`--links relative` or `auto` for relative ones).
`--prune` removes links whose target is gone **or outside the synced tree**: keep one mirror storage
per tree, or links made with `link` from other places are pruned. `sync` refuses a storage that has a
description file; use `import` and `apply` there.

## Names and safety

- **Content by extension**: `.iso` is an ISO; `.ima` and `.vfd` are floppies; `.img` (both kinds use
  it) is a floppy up to 2.88 MB and an ISO above, unless `link --content`, `sync --img-as`, a rule's
  `img_as` or an entry's `content` says otherwise.
- **Names**: each folder and file name is cleaned the way PVE cleans an uploaded file's name:
  characters other than `A-Z a-z 0-9 _ . -` become `_` (a run of them one `_`), so no space or comma
  reaches a VM config. The result must split back on `__` into the same parts, so a folder or file
  name that contains `__` and a folder whose name ends in `_` are **refused**: rename the source, or
  give the file a name of its own (`link --as`, an entry). Two files that would get the same name
  are a clash, and neither is linked.
- **Safety**: the tool only creates, replaces and removes symlinks. A regular file of the same name in
  the storage is never touched (a conflict). It reads the storage's paths, `content-dirs` included,
  from `/etc/pve/storage.cfg`, refuses storage types that can't hold links and a network storage that
  isn't mounted (so no link lands in an empty mount point), and warns about a CIFS storage without
  `mfsymlinks`.

## Caveats

- **Absolute links need the same mount path everywhere**: links in a local storage are plain files on
  one node, and their targets must be at the same path on every node that runs the VMs. Relative links
  on a shared export (way 2) don't have that problem.
- **A dangling link**: when the share isn't mounted or a file moved, the volume is listed as
  [unavailable](#a-link-whose-target-isnt-reachable) (with an older libpve-storage-perl it isn't listed
  at all), and a VM whose drive points at it doesn't start (the CD/DVD drive can be set to "no media"
  first). `wsh-lab mirror list` shows dangling links.
- **Uploads are regular files**: an upload or download from URL into the mirror storage writes a real
  file in `template/iso` or `template/floppy`, not onto the NAS. The tool leaves such files alone.
- **Write access**: floppy drives are writable by default, and a write goes through the link to the
  file. Add `ro=1` to the drive for reference media.
- **NFS-Ganesha with NFS 4.1/4.2 breaks removing a directory tree** from a Linux 7.0 client. The
  client asks for directory delegations (`GET_DIR_DELEGATION`, new in 4.1), NFS-Ganesha 6.5 answers
  `NFS4ERR_OP_ILLEGAL`, and a recursive removal (`rm -r`) then fails with `EISDIR` or `EREMOTEIO`.
  Mount such an export with `vers=4.0` (`--options vers=4.0` on `pvesm add nfs`). The Linux kernel
  NFS server (knfsd), which most NAS boxes run, isn't affected. The e2e tests use 4.0 against their
  Ganesha server for this reason (`e2e/tests/mirror.spec.ts`).
- **Install targets** find a medium by name first, then by size and sha256 among the storage's
  volumes: `wsh-lab media` and `wsh-lab install --media-storage mirror` find
  `Solaris__2.6__solaris_2.6_598_sparc.iso` as `solaris_2.6_598_sparc.iso`
  ([Lab install targets, Media](/guides/lab-install/#media)).

## Further reading

- [Floppy Device Reference](/reference/floppy/) — the floppy content type
- [Lab install targets](/guides/lab-install/) — the `wsh-lab` package
