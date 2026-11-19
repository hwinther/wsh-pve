"""A mirror storage: a PVE `dir` storage whose ISO and floppy directories hold symlinks to media that
live elsewhere (a NAS share in a deep folder tree), on the PVE node, as root:

    lab.py mirror link <source-file> [--storage S] [--root DIR | --as NAME] [--content iso|floppy] [--force]
    lab.py mirror sync <source-dir> [--storage S] [--prune] [--img-as auto|iso|floppy] [--dry-run]
    lab.py mirror list [--storage S] [--json]

PVE lists the files of a dir storage's `template/iso` (and `template/floppy`, wsh-pve's floppy content)
with stat(), which follows symlinks: a link shows up as a volume with its target's size, QEMU opens the
target, and removing the volume removes only the link. Symlinks cross file systems, so the target may
be on an NFS mount.

The folders are kept in the link's name, joined with a double underscore (SEPARATOR):
`Solaris/2.6/solaris_2.6_598_sparc.iso` under the source tree becomes the volume
`<storage>:iso/Solaris__2.6__solaris_2.6_598_sparc.iso`, and the web UI (pve-manager) shows it in the
folder `Solaris / 2.6`. Volume IDs and VM configs keep the plain name.

Naming rules (link_name):
- each folder or file name is cleaned the way PVE cleans an uploaded file's name: characters other
  than `A-Z a-z 0-9 _ . -` become `_` (a run of them one `_`), so a name never carries a comma or
  space into a VM config;
- the joined name must split back on `__` (from the left, as the UI splits it) into the same parts:
  a folder or file name that contains `__`, or a folder that ends in `_` (`a_/x.iso` would be
  `a___x.iso`, which splits into `a` and `_x.iso`), is refused, as is an empty part. Rename the
  source, or give the link a name with `link --as`;
- the name ends in an extension of its content type: `.iso`/`.img` for iso, `.img`/`.ima`/`.vfd` for
  floppy (pve-storage's ISO_EXT_RE_0 and wsh-pve's FLOPPY_EXT_RE_0, any case). `.img` is both: an image
  of up to 2.88 MB (FLOPPY_MAX) is a floppy, a larger one an ISO, unless `--content`/`--img-as` says.

The tool only ever creates, replaces (`--force`) or removes symlinks; it never touches a regular file
in the storage, and link targets are absolute paths.
"""
import json
import os
import re
import sys

SEPARATOR = "__"
STORAGE_CFG = "/etc/pve/storage.cfg"
# The default subdirectories of a dir storage (pve-storage Plugin.pm $vtype_subdirs, floppy from wsh-pve)
SUBDIRS = {"iso": "template/iso", "floppy": "template/floppy"}
EXTENSIONS = {"iso": (".iso", ".img"), "floppy": (".img", ".ima", ".vfd")}
# The largest floppy image: a 2.88 MB ED disk
FLOPPY_MAX = 2949120
UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


class MirrorError(Exception):
    pass


# --- storage ---------------------------------------------------------------------------------------

def parse_storage_cfg(text):
    """{storage: {"type": ..., option: value}} from the text of /etc/pve/storage.cfg."""
    storages, cur = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            m = re.match(r"^(\S+):\s*(\S+)\s*$", line)
            if not m:
                raise MirrorError(f"storage.cfg: can't read the line {line!r}")
            cur = storages[m.group(2)] = {"type": m.group(1)}
        elif cur is not None:
            key, _, value = line.strip().partition(" ")
            cur[key] = value.strip()
    return storages


def storage_dirs(storage, cfg_path=None):
    """{"iso": dir, "floppy": dir} of a dir storage, for the content types it has enabled (at least one).
    Refuses another storage type and a storage without iso or floppy content."""
    cfg_path = cfg_path or os.environ.get("WSH_LAB_STORAGE_CFG") or STORAGE_CFG
    try:
        with open(cfg_path, encoding="utf-8") as f:
            storages = parse_storage_cfg(f.read())
    except OSError as e:
        raise MirrorError(f"can't read {cfg_path} ({e.strerror}): run this on a PVE node")
    if storage not in storages:
        raise MirrorError(f"no storage {storage!r} in {cfg_path} (there are: {', '.join(sorted(storages))})")
    s = storages[storage]
    if s["type"] != "dir":
        raise MirrorError(f"storage {storage} is of type {s['type']}: a mirror storage must be a 'dir' storage "
                          f"(make one with `pvesm add dir <name> --path <dir> --content iso,floppy`)")
    if not s.get("path"):
        raise MirrorError(f"storage {storage} has no path")
    content = set(filter(None, s.get("content", "").split(",")))
    overrides = dict(d.split("=", 1) for d in filter(None, s.get("content-dirs", "").split(",")) if "=" in d)
    dirs = {ct: os.path.join(s["path"], overrides.get(ct, sub)) for ct, sub in SUBDIRS.items() if ct in content}
    if not dirs:
        raise MirrorError(f"storage {storage} has neither iso nor floppy content (it has {','.join(sorted(content))}): "
                          f"`pvesm set {storage} --content {','.join(sorted(content | {'iso', 'floppy'}))}`")
    return dirs


# --- names -----------------------------------------------------------------------------------------

def media_content(path, img_as="auto", size=None):
    """'iso', 'floppy' or None (not a medium) for a file name; `.img` by img_as, or with auto by its size."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".iso":
        return "iso"
    if ext in (".ima", ".vfd"):
        return "floppy"
    if ext == ".img":
        if img_as != "auto":
            return img_as
        if size is None:
            size = os.stat(path).st_size
        return "floppy" if size <= FLOPPY_MAX else "iso"
    return None


def clean(part):
    """A folder or file name as PVE cleans an upload's name, a run of other characters as one `_`."""
    return UNSAFE.sub("_", part)


def check_name(name, content):
    """Refuse a link name that PVE wouldn't list as `content` or that isn't safe in a VM config."""
    if not name or "/" in name or "\0" in name or "\n" in name:
        raise MirrorError(f"{name!r}: a link name is one file name (no '/')")
    if name.startswith("."):
        raise MirrorError(f"{name!r}: a link name doesn't start with '.'")
    if UNSAFE.search(name):
        raise MirrorError(f"{name!r}: only A-Z a-z 0-9 _ . - in a link name")
    if not name.lower().endswith(EXTENSIONS[content]):
        raise MirrorError(f"{name!r}: {content} volumes end in {', '.join(EXTENSIONS[content])}")
    if any(p == "" for p in name.split(SEPARATOR)):
        raise MirrorError(f"{name!r}: an empty part between '{SEPARATOR}' separators")


def link_name(relpath, content):
    """The link name of a file at `relpath` (relative to the source tree): its folders and file name,
    cleaned, joined with SEPARATOR. Refused when the name wouldn't split back into the same parts."""
    parts = [p for p in relpath.replace(os.sep, "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise MirrorError(f"{relpath!r} isn't a path inside the source tree")
    cleaned = [clean(p) for p in parts]
    name = SEPARATOR.join(cleaned)
    if name.split(SEPARATOR) != cleaned:
        raise MirrorError(f"{relpath}: a folder or file name contains '{SEPARATOR}' or a folder ends in '_', so "
                          f"{name} wouldn't show the same folders; rename it or use `link --as`")
    check_name(name, content)
    return name


def folders(name):
    """The folders and the file name the UI shows for a link name (as pve-manager splits it)."""
    parts = name.split(SEPARATOR)
    return [name] if any(p == "" for p in parts) else parts


# --- links -----------------------------------------------------------------------------------------

def inside(path, root):
    path, root = os.path.abspath(path), os.path.abspath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def make_link(target, dest, force=False, dry_run=False):
    """Create the symlink dest -> target (absolute). Returns 'created', 'exists' (already that link) or
    'replaced' (another link, with force). Refuses a regular file or directory at dest, and another link
    without force."""
    target = os.path.abspath(target)
    if os.path.islink(dest):
        current = os.readlink(dest)
        if current == target:
            return "exists"
        if not force:
            raise MirrorError(f"{dest} is a link to {current}, not {target} (--force replaces the link)")
        if not dry_run:
            tmp = f"{dest}.wsh-lab-mirror.{os.getpid()}"
            os.symlink(target, tmp)
            os.replace(tmp, dest)
        return "replaced"
    if os.path.lexists(dest):
        raise MirrorError(f"{dest} exists and isn't a link: left alone")
    if not dry_run:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.symlink(target, dest)
    return "created"


def scan_links(dirs):
    """Every entry of the storage's ISO and floppy directories: name, content, path, link target (None for
    a regular file), state ('ok', 'dangling', 'file')."""
    rows = []
    for content, d in sorted(dirs.items()):
        try:
            names = sorted(os.listdir(d))
        except FileNotFoundError:
            continue
        for name in names:
            path = os.path.join(d, name)
            if os.path.isdir(path):
                continue
            target = os.readlink(path) if os.path.islink(path) else None
            if target is None:
                state = "file"
            else:
                state = "ok" if os.path.isfile(path) else "dangling"
            rows.append({"name": name, "content": content, "path": path, "target": target, "state": state,
                         "size": os.path.getsize(path) if state != "dangling" else None,
                         "folders": folders(name)[:-1]})
    return rows


def sync_plan(source, img_as="auto"):
    """(links, conflicts) for a source tree: links = [(content, name, target)], conflicts = [message].
    Two files that end up with the same name are both reported, and neither is linked."""
    source = os.path.abspath(source)
    if not os.path.isdir(source):
        raise MirrorError(f"{source} isn't a directory")
    found, conflicts = {}, []
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames.sort()
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            if not os.path.isfile(path):
                continue
            try:
                content = media_content(path, img_as)
                if not content:
                    continue
                name = link_name(os.path.relpath(path, source), content)
            except MirrorError as e:
                conflicts.append(str(e))
                continue
            except OSError as e:
                conflicts.append(f"{path}: {e.strerror}")
                continue
            found.setdefault((content, name), []).append(path)
    links = []
    for (content, name), paths in sorted(found.items()):
        if len(paths) > 1:
            conflicts.append(f"{name}: the same name for {', '.join(paths)}; none linked")
        else:
            links.append((content, name, paths[0]))
    return links, conflicts


# --- commands --------------------------------------------------------------------------------------

def cmd_link(a):
    try:
        dirs = storage_dirs(a.storage)
        source = os.path.abspath(a.source)
        if not os.path.isfile(source):
            raise MirrorError(f"{a.source} isn't a file")
        content = a.content or media_content(source)
        if not content:
            raise MirrorError(f"{a.source}: not an ISO or floppy image (.iso, .img, .ima, .vfd)")
        if content not in dirs:
            raise MirrorError(f"storage {a.storage} has no {content} content")
        if a.as_name:
            name = a.as_name
            check_name(name, content)
        else:
            root = os.path.abspath(a.root) if a.root else os.path.dirname(source)
            if not inside(source, root):
                raise MirrorError(f"{source} isn't under --root {root}")
            name = link_name(os.path.relpath(source, root), content)
        dest = os.path.join(dirs[content], name)
        state = make_link(source, dest, force=a.force)
    except (MirrorError, OSError) as e:
        sys.exit(f"mirror link: {e}")
    print(f"{state:8} {a.storage}:{content}/{name} -> {source}")
    return 0


def cmd_sync(a):
    try:
        dirs = storage_dirs(a.storage)
        source = os.path.abspath(a.source)
        links, conflicts = sync_plan(source, a.img_as)
    except MirrorError as e:
        sys.exit(f"mirror sync: {e}")
    counts = {"created": 0, "exists": 0, "pruned": 0}
    wanted = set()
    for content, name, target in links:
        if content not in dirs:
            conflicts.append(f"{target}: storage {a.storage} has no {content} content")
            continue
        dest = os.path.join(dirs[content], name)
        wanted.add(dest)
        try:
            state = make_link(target, dest, dry_run=a.dry_run)
        except (MirrorError, OSError) as e:
            conflicts.append(str(e))
            continue
        counts[state] += 1
        if state != "exists":
            print(f"{state:8} {a.storage}:{content}/{name} -> {target}")
    if a.prune:
        for row in scan_links(dirs):
            if row["target"] is None or row["path"] in wanted:
                continue
            gone = row["state"] == "dangling"
            outside = not inside(row["target"], source)
            if gone or outside:
                if not a.dry_run:
                    os.unlink(row["path"])
                counts["pruned"] += 1
                why = "target gone" if gone else "target outside the tree"
                print(f"{'pruned':8} {a.storage}:{row['content']}/{row['name']} -> {row['target']} ({why})")
    for c in conflicts:
        print(f"conflict {c}")
    dry = " (dry run: nothing changed)" if a.dry_run else ""
    print(f"{counts['created']} created, {counts['exists']} already there, {counts['pruned']} pruned, "
          f"{len(conflicts)} conflicts{dry}")
    return 1 if conflicts else 0


def cmd_list(a):
    try:
        rows = scan_links(storage_dirs(a.storage))
    except MirrorError as e:
        sys.exit(f"mirror list: {e}")
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            vol = f"{a.storage}:{r['content']}/{r['name']}"
            target = r["target"] or "(a regular file, not a link)"
            print(f"{r['state']:8} {vol} -> {target}" if r["target"] else f"{r['state']:8} {vol} {target}")
        dangling = sum(r["state"] == "dangling" for r in rows)
        print(f"{sum(r['target'] is not None for r in rows)} links, {dangling} dangling, "
              f"{sum(r['target'] is None for r in rows)} regular files")
    return 1 if any(r["state"] == "dangling" for r in rows) else 0


def cmd_mirror(a):
    return {"link": cmd_link, "sync": cmd_sync, "list": cmd_list}[a.mirror_cmd](a)


def add_commands(sub):
    m = sub.add_parser("mirror", help="a mirror storage: symlinks to ISO and floppy images elsewhere (a NAS), "
                                      "folders kept in the link name with '__'")
    msub = m.add_subparsers(dest="mirror_cmd", required=True)
    lk = msub.add_parser("link", help="link one ISO or floppy image into the storage")
    lk.add_argument("source", help="the image (an absolute link to it is made)")
    lk.add_argument("--storage", default="local", help="the dir storage (local)")
    g = lk.add_mutually_exclusive_group()
    g.add_argument("--root", help="name the link after the source's path below this directory, joined with '__' "
                                  "(default: the file name alone)")
    g.add_argument("--as", dest="as_name", metavar="NAME", help="the link's name")
    lk.add_argument("--content", choices=sorted(SUBDIRS),
                    help="iso or floppy (default: by extension; .img by size, up to 2.88 MB a floppy)")
    lk.add_argument("--force", action="store_true", help="replace a link of that name to another target")
    sy = msub.add_parser("sync", help="link every ISO and floppy image under a directory tree")
    sy.add_argument("source", help="the top of the tree; the link names are the paths below it")
    sy.add_argument("--storage", default="local", help="the dir storage (local)")
    sy.add_argument("--prune", action="store_true",
                    help="also remove links (never regular files) whose target is gone or outside the tree")
    sy.add_argument("--img-as", choices=("auto", "iso", "floppy"), default="auto",
                    help=".img files: by size (auto: up to 2.88 MB a floppy), or all ISO or all floppy")
    sy.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    ls = msub.add_parser("list", help="the storage's links and their targets, dangling ones marked")
    ls.add_argument("--storage", default="local", help="the dir storage (local)")
    ls.add_argument("--json", action="store_true")


COMMANDS = {"mirror": cmd_mirror}
