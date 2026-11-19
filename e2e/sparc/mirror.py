"""A mirror storage: a PVE storage whose ISO and floppy directories hold symlinks to media that live
elsewhere (a NAS share in a deep folder tree, a torrent download folder), on the PVE node, as root.

By hand, one link or one tree at a time:

    lab.py mirror link <source-file> [--storage S] [--root DIR | --as NAME] [--content iso|floppy] [--force]
    lab.py mirror sync <source-dir> [--storage S] [--prune] [--img-as auto|iso|floppy] [--dry-run]
    lab.py mirror list [--storage S] [--json]

From a description file (`wsh-mirror.yaml` at the storage's root, or --config PATH), the source of
truth that the links are derived from:

    lab.py mirror init   --storage S [--watch DIR ...]   write a commented description file
    lab.py mirror plan   --storage S [--json]            what apply would change, files nothing covers,
                                                         entries whose file is gone or moved, clashes
    lab.py mirror apply  --storage S [--dry-run]         make the links match the file (idempotent)
    lab.py mirror import --storage S [--dry-run]         add entries for the files nothing covers
    lab.py mirror tidy   --storage S [--dry-run] [--include-manual]
                                                         drop entries whose file is gone, follow moves
    lab.py mirror timer  --storage S [--interval 10min] [--remove]
                                                         a systemd timer that runs apply

PVE lists the files of a dir storage's `template/iso` (and `template/floppy`, wsh-pve's floppy content)
with stat(), which follows symlinks: a link shows up as a volume with its target's size, QEMU opens the
target, and removing the volume removes only the link. The same holds for the btrfs, nfs, cephfs and
cifs storages, whose ISO and floppy directories are plain directories too (CIFS keeps symlinks only
when mounted with `mfsymlinks`).

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
  source, or give the link a name (`link --as`, or an entry in the description file);
- the name ends in an extension of its content type: `.iso`/`.img` for iso, `.img`/`.ima`/`.vfd` for
  floppy (pve-storage's ISO_EXT_RE_0 and wsh-pve's FLOPPY_EXT_RE_0, any case). `.img` is both: an image
  of up to 2.88 MB (FLOPPY_MAX) is a floppy, a larger one an ISO, unless `--content`/`--img-as` says.

The tool only ever creates, replaces or removes symlinks; it never touches a regular file in the
storage. `link` and `sync` write absolute link targets (unless --links says otherwise); the
description file's links are relative when the file is on the same file system as the link directory
(an NFS export that holds both the media and the mirror), so the mount path doesn't matter, and
absolute otherwise.
"""
import fnmatch
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time

SEPARATOR = "__"
STORAGE_CFG = "/etc/pve/storage.cfg"
# The default subdirectories of a storage's ISO and floppy content (pve-storage Plugin.pm
# $vtype_subdirs, floppy from wsh-pve); the same for every storage type that keeps them as files
SUBDIRS = {"iso": "template/iso", "floppy": "template/floppy"}
EXTENSIONS = {"iso": (".iso", ".img"), "floppy": (".img", ".ima", ".vfd")}
# The largest floppy image: a 2.88 MB ED disk
FLOPPY_MAX = 2949120
UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")
# Storage types whose ISO and floppy directories can hold symlinks; the network ones are mounted by PVE
MIRROR_TYPES = ("dir", "btrfs", "nfs", "cephfs", "cifs")
NETWORK_TYPES = ("nfs", "cephfs", "cifs")

# The description file, and the state and lock files apply keeps next to the links (at the storage's
# root, which PVE doesn't list)
CONFIG_NAME = "wsh-mirror.yaml"
STATE_NAME = ".wsh-mirror-state.json"
LOCK_NAME = ".wsh-mirror.lock"
# Names of files a download client is still writing (qBittorrent, uTorrent, Transmission, browsers)
INCOMPLETE = ["*.part", "*.!qB", "*.!ut", "*.incomplete", "*.crdownload", "*.partial"]
MIN_AGE = 300
# apply's exit code when another apply holds the lock (EX_TEMPFAIL); the timer's unit counts it a success
BUSY = 75
SYSTEMD_DIR = "/etc/systemd/system"
CONFIG_KEYS = {"version", "storage", "watch", "auto_import", "incomplete", "links", "checksums", "rules",
               "entries"}
RULE_KEYS = {"source", "prefix", "exclude", "img_as", "flatten"}
ENTRY_KEYS = {"name", "source", "origin", "content"}
WATCH_KEYS = {"path", "prefix"}

# Seams for the unit tests
clock = time.time
is_mounted = os.path.ismount


class MirrorError(Exception):
    pass


class Busy(MirrorError):
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


def storage_info(storage, cfg_path=None, warn=None):
    """{"type", "root", "dirs": {"iso": dir, "floppy": dir}} of a storage that can hold the links: a dir,
    btrfs, nfs, cephfs or cifs storage with iso or floppy content (at least one). A network storage must
    be mounted (PVE mounts it when it activates the storage), so links never land in the empty mount
    point. CIFS keeps symlinks only with the `mfsymlinks` mount option: without it, `warn` is told."""
    cfg_path = cfg_path or os.environ.get("WSH_LAB_STORAGE_CFG") or STORAGE_CFG
    try:
        with open(cfg_path, encoding="utf-8") as f:
            storages = parse_storage_cfg(f.read())
    except OSError as e:
        raise MirrorError(f"can't read {cfg_path} ({e.strerror}): run this on a PVE node")
    if storage not in storages:
        raise MirrorError(f"no storage {storage!r} in {cfg_path} (there are: {', '.join(sorted(storages))})")
    s = storages[storage]
    if s["type"] not in MIRROR_TYPES:
        raise MirrorError(f"storage {storage} is of type {s['type']}: a mirror storage is one of "
                          f"{', '.join(MIRROR_TYPES)} (a local one: "
                          f"`pvesm add dir <name> --path <dir> --content iso,floppy`)")
    root = s.get("path") or (f"/mnt/pve/{storage}" if s["type"] in NETWORK_TYPES else "")
    if not root:
        raise MirrorError(f"storage {storage} has no path")
    content = set(filter(None, s.get("content", "").split(",")))
    overrides = dict(d.split("=", 1) for d in filter(None, s.get("content-dirs", "").split(",")) if "=" in d)
    dirs = {ct: os.path.join(root, overrides.get(ct, sub)) for ct, sub in SUBDIRS.items() if ct in content}
    if not dirs:
        raise MirrorError(f"storage {storage} has neither iso nor floppy content (it has {','.join(sorted(content))}): "
                          f"`pvesm set {storage} --content {','.join(sorted(content | {'iso', 'floppy'}))}`")
    if s["type"] in NETWORK_TYPES and not is_mounted(root):
        raise MirrorError(f"storage {storage} ({s['type']}) isn't mounted at {root}: activate it first "
                          f"(`pvesm status --storage {storage}`)")
    if s["type"] == "cifs" and warn and "mfsymlinks" not in s.get("options", "") \
            and "mfsymlinks" not in mount_options(root):
        warn(f"storage {storage} is CIFS without the mfsymlinks mount option: the server may refuse "
             f"symlinks or follow them on its side (`pvesm set {storage} --options mfsymlinks`, then "
             f"remount)")
    return {"type": s["type"], "root": root, "dirs": dirs}


def storage_dirs(storage, cfg_path=None):
    """{"iso": dir, "floppy": dir} of a mirror storage, for the content types it has enabled."""
    return storage_info(storage, cfg_path)["dirs"]


def mount_options(path):
    """The mount options of the mount at `path`, '' when unknown."""
    try:
        with open("/proc/self/mounts", encoding="utf-8") as f:
            for line in f:
                fields = line.split()
                if len(fields) > 3 and fields[1] == path:
                    return fields[3]
    except OSError:
        pass
    return ""


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


def link_name(relpath, content, prefix=()):
    """The link name of a file at `relpath` (relative to the source tree): the prefix folders, its
    folders and file name, cleaned, joined with SEPARATOR. Refused when the name wouldn't split back
    into the same parts."""
    parts = [p for p in relpath.replace(os.sep, "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise MirrorError(f"{relpath!r} isn't a path inside the source tree")
    cleaned = list(prefix) + [clean(p) for p in parts]
    name = SEPARATOR.join(cleaned)
    if name.split(SEPARATOR) != cleaned:
        raise MirrorError(f"{relpath}: a folder or file name contains '{SEPARATOR}' or a folder ends in '_', so "
                          f"{name} wouldn't show the same folders; rename it or give it a name of its own")
    check_name(name, content)
    return name


def prefix_parts(prefix, where):
    """A rule's or watch directory's `prefix` ('Sun/Solaris') as cleaned folder names."""
    if prefix in (None, ""):
        return []
    if not isinstance(prefix, str):
        raise MirrorError(f"{where}: prefix is a string of folders ('Sun/Solaris')")
    parts = [clean(p) for p in prefix.split("/") if p]
    if not parts or SEPARATOR.join(parts).split(SEPARATOR) != parts:
        raise MirrorError(f"{where}: the prefix {prefix!r} doesn't make folders (no '__', no folder ending in '_')")
    return parts


def folders(name):
    """The folders and the file name the UI shows for a link name (as pve-manager splits it)."""
    parts = name.split(SEPARATOR)
    return [name] if any(p == "" for p in parts) else parts


# --- links -----------------------------------------------------------------------------------------

def inside(path, root):
    path, root = os.path.abspath(path), os.path.abspath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def existing_ancestor(path):
    path = os.path.abspath(path)
    while not os.path.exists(path):
        path = os.path.dirname(path)
    return path


def mount_point(path):
    path = os.path.realpath(existing_ancestor(path))
    while not is_mounted(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)
    return path


def link_text(target, link_dir, style="absolute"):
    """What a link in `link_dir` to `target` holds: the absolute path, or (relative) the path from the
    link's directory. auto: relative when the target is on the link directory's file system, inside
    its mount (an NFS export that holds both), so another mount path of the same export still finds
    it; absolute otherwise."""
    target = os.path.abspath(target)
    if style == "absolute":
        return target
    real_target = os.path.join(os.path.realpath(os.path.dirname(target)), os.path.basename(target))
    real_dir = os.path.realpath(existing_ancestor(link_dir))
    if style == "auto":
        try:
            same = os.stat(real_dir).st_dev == os.stat(os.path.dirname(real_target)).st_dev
        except OSError:
            same = False
        if not (same and inside(real_target, mount_point(real_dir))):
            return target
    # relative to where the link directory will be (it may not exist yet)
    return os.path.relpath(real_target, os.path.join(real_dir, os.path.relpath(os.path.abspath(link_dir),
                                                                                existing_ancestor(link_dir))))


def resolves_to(dest, target):
    """Whether the link at dest leads to the file target."""
    try:
        return os.path.samefile(dest, target)
    except OSError:
        return False


def make_link(target, dest, force=False, dry_run=False, style="absolute", adopt=False):
    """Create the symlink dest -> target. Returns 'created', 'exists' (already that link) or
    'replaced' (another link, with force; or with adopt one that leads to the same file in another
    style). Refuses a regular file or directory at dest, and another link without force."""
    text = link_text(target, os.path.dirname(dest), style)
    if os.path.islink(dest):
        current = os.readlink(dest)
        if current == text or (not adopt and not force and resolves_to(dest, target)):
            return "exists"
        if not (force or (adopt and resolves_to(dest, target))):
            raise MirrorError(f"{dest} is a link to {current}, not {text} (--force replaces the link)")
        if not dry_run:
            tmp = f"{dest}.wsh-lab-mirror.{os.getpid()}"
            os.symlink(text, tmp)
            os.replace(tmp, dest)
        return "replaced"
    if os.path.lexists(dest):
        raise MirrorError(f"{dest} exists and isn't a link: left alone")
    if not dry_run:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.symlink(text, dest)
    return "created"


def link_target_path(path):
    """The absolute path a link points at (its text resolved against its directory)."""
    return os.path.normpath(os.path.join(os.path.dirname(path), os.readlink(path)))


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


# --- the description file --------------------------------------------------------------------------

def _yaml():
    try:
        import yaml
    except ImportError:
        raise MirrorError("the description file needs PyYAML (Debian: apt install python3-yaml)")
    return yaml


def parse_age(value, where="min_age"):
    """Seconds from 300, '300s', '5min', '5m', '2h'."""
    if isinstance(value, bool):
        raise MirrorError(f"{where}: {value!r} isn't a duration")
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(s|sec|m|min|h|hr|d)?\s*", str(value))
    if not m:
        raise MirrorError(f"{where}: {value!r} isn't a duration (300, 30s, 5min, 2h)")
    return float(m.group(1)) * {None: 1, "s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600,
                                "d": 86400}[m.group(2)]


def resolve(path, root):
    """A path from the description file: absolute, or relative to the storage's root."""
    return os.path.normpath(os.path.join(root, os.path.expanduser(path)))


def has_glob(path):
    return any(c in path for c in "*?[")


def glob_base(pattern):
    """The directories in front of the first part with a wildcard."""
    parts = pattern.split("/")
    base = []
    for p in parts:
        if has_glob(p):
            break
        base.append(p)
    return "/".join(base) or "/"


def load_config(path, root):
    """The description file at `path` as checked, resolved settings (paths relative to `root`)."""
    yaml = _yaml()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        raise MirrorError(f"no description file {path} (`mirror init` writes one)")
    except OSError as e:
        raise MirrorError(f"can't read {path}: {e.strerror}")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise MirrorError(f"{path}: not valid YAML: {e}")
    return check_config(data if data is not None else {}, root, path)


def _list(value, where):
    if value is None:
        return []
    if not isinstance(value, list):
        raise MirrorError(f"{where}: a list")
    return value


def _keys(item, allowed, where):
    if not isinstance(item, dict):
        raise MirrorError(f"{where}: a mapping (key: value)")
    unknown = set(item) - allowed
    if unknown:
        raise MirrorError(f"{where}: unknown key(s) {', '.join(sorted(map(str, unknown)))} "
                          f"(known: {', '.join(sorted(allowed))})")


def check_config(data, root, path="wsh-mirror.yaml"):
    _keys(data, CONFIG_KEYS, path)
    if data.get("version", 1) != 1:
        raise MirrorError(f"{path}: version {data.get('version')!r}; this tool reads version 1")
    cfg = {"storage": data.get("storage"), "auto_import": bool(data.get("auto_import", False)),
           "links": data.get("links", "auto"), "checksums": bool(data.get("checksums", True)),
           "watch": [], "rules": [], "entries": [], "path": path}
    if cfg["links"] not in ("auto", "relative", "absolute"):
        raise MirrorError(f"{path}: links is auto, relative or absolute, not {cfg['links']!r}")
    inc = data.get("incomplete") or {}
    _keys(inc, {"patterns", "min_age"}, f"{path}: incomplete")
    cfg["incomplete"] = [str(p) for p in _list(inc.get("patterns", INCOMPLETE), f"{path}: incomplete.patterns")]
    cfg["min_age"] = parse_age(inc.get("min_age", MIN_AGE), f"{path}: incomplete.min_age")
    for i, w in enumerate(_list(data.get("watch"), f"{path}: watch")):
        where = f"{path}: watch[{i}]"
        w = {"path": w} if isinstance(w, str) else w
        _keys(w, WATCH_KEYS, where)
        if not isinstance(w.get("path"), str) or not w["path"]:
            raise MirrorError(f"{where}: a directory (path)")
        cfg["watch"].append({"raw": w["path"], "path": resolve(w["path"], root),
                             "prefix": prefix_parts(w.get("prefix"), where)})
    for i, r in enumerate(_list(data.get("rules"), f"{path}: rules")):
        where = f"{path}: rules[{i}]"
        _keys(r, RULE_KEYS, where)
        if not isinstance(r.get("source"), str) or not r["source"]:
            raise MirrorError(f"{where}: a source directory or glob")
        source = resolve(r["source"], root)
        img_as = r.get("img_as", "auto")
        if img_as not in ("auto", "iso", "floppy"):
            raise MirrorError(f"{where}: img_as is auto, iso or floppy")
        exclude = [str(x) for x in _list(r.get("exclude"), f"{where}: exclude")]
        cfg["rules"].append({"index": i, "raw": r["source"], "glob": source if has_glob(source) else None,
                             "base": glob_base(source) if has_glob(source) else source,
                             "prefix": prefix_parts(r.get("prefix"), where), "exclude": exclude,
                             "img_as": img_as, "flatten": bool(r.get("flatten", False))})
    names = {}
    for i, e in enumerate(_list(data.get("entries"), f"{path}: entries")):
        where = f"{path}: entries[{i}]"
        _keys(e, ENTRY_KEYS, where)
        for key in ("name", "source"):
            if not isinstance(e.get(key), str) or not e[key]:
                raise MirrorError(f"{where}: {key} is required")
        origin = e.get("origin", "manual")
        if origin not in ("manual", "import"):
            raise MirrorError(f"{where}: origin is manual or import, not {origin!r}")
        content = e.get("content")
        if content not in (None, "iso", "floppy"):
            raise MirrorError(f"{where}: content is iso or floppy")
        if e["name"] in names:
            raise MirrorError(f"{where}: the name {e['name']} is also entries[{names[e['name']]}]")
        names[e["name"]] = i
        cfg["entries"].append({"index": i, "name": e["name"], "raw": e["source"], "path": resolve(e["source"], root),
                               "origin": origin, "content": content})
    return cfg


def config_path(info, config=None):
    return os.path.abspath(config) if config else os.path.join(info["root"], CONFIG_NAME)


# --- scanning --------------------------------------------------------------------------------------

def walk_files(base, skip):
    """Every file below base (following file links, not directory links), sorted, outside `skip`."""
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not any(inside(os.path.join(dirpath, d), s) for s in skip))
        for fn in sorted(filenames):
            yield os.path.join(dirpath, fn)


def incomplete_reason(path, base, st, cfg, now):
    """Why a file is still being written ('name matches *.part', 'changed 40s ago'), or None."""
    rel = os.path.relpath(path, base) if base and inside(path, base) else os.path.basename(path)
    for part in rel.replace(os.sep, "/").split("/"):
        for pat in cfg["incomplete"]:
            if fnmatch.fnmatch(part.lower(), pat.lower()):
                return f"its name matches {pat}"
    age = now - st.st_mtime
    if age < cfg["min_age"]:
        return f"changed {int(age)}s ago (min_age {int(cfg['min_age'])}s)"
    return None


def source_available(path, bases):
    """Whether a missing file is really gone, or only unreachable (its share isn't mounted): gone when a
    rule's or watch directory containing it exists and isn't empty, or (outside them) when its
    directory exists."""
    containing = [b for b in bases if inside(path, b)]
    if containing:
        return any(os.path.isdir(b) and os.listdir(b) for b in containing)
    return os.path.isdir(os.path.dirname(path))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_state(root):
    try:
        with open(os.path.join(root, STATE_NAME), encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state.get("links"), dict) else {"version": 1, "links": {}}
    except (OSError, ValueError, AttributeError):
        return {"version": 1, "links": {}}


def write_state(root, state):
    path = os.path.join(root, STATE_NAME)
    tmp = f"{path}.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def build(cfg, info, state=None, now=None):
    """Everything the description file asks for, against the source trees and the storage now:

    desired   {(content, name): {"target", "origin" (rule N, entry, import, auto)}}: the links to have
    unmatched [{"path", "name"|None, "error"|None}]: complete files below a watch directory that no rule
              or entry covers (with auto_import they are in desired too)
    waiting   [{"path", "why"}]: files still being written, not linked
    gone      [{"entry", "available"}]: entries whose file is missing (available False: unreachable)
    moved     [{"key", "entry"|None, "old", "new"}]: missing files found elsewhere (same size+sha256)
    clashes   [{"name", "paths"}], errors [message]
    """
    now = clock() if now is None else now
    state = state if state is not None else {"links": {}}
    root, dirs = info["root"], info["dirs"]
    skip = list(dirs.values())
    stats, errors, waiting = {}, [], []
    bases = [r["base"] for r in cfg["rules"]] + [w["path"] for w in cfg["watch"]]

    def stat(path):
        if path not in stats:
            try:
                stats[path] = os.stat(path)
            except OSError:
                stats[path] = None
        return stats[path]

    # files apply has linked already: a recent change (a floppy image a VM writes to) doesn't unlink them
    linked = {os.path.realpath(rec["target"]) for rec in state["links"].values() if rec and rec.get("target")}

    def complete(path, base):
        st = stat(path)
        why = incomplete_reason(path, base, st, cfg, now)
        if why and why.startswith("changed") and os.path.realpath(path) in linked:
            return True
        if why:
            if not any(w["path"] == path for w in waiting):
                waiting.append({"path": path, "why": why})
            return False
        return True

    wanted = {}  # (content, name) -> [{"target", "origin"}]

    def want(content, name, target, origin):
        wanted.setdefault((content, name), []).append({"target": target, "origin": origin})

    # entries first: a file with an entry is linked under the entry's name only
    covered, gone = set(), []
    for e in cfg["entries"]:
        covered.add(os.path.realpath(e["path"]))
        st = stat(e["path"])
        if st is None or not os.path.isfile(e["path"]):
            gone.append({"entry": e, "available": source_available(e["path"], bases)})
            continue
        try:
            content = e["content"] or media_content(e["name"], size=st.st_size) or media_content(e["path"],
                                                                                                size=st.st_size)
            if not content:
                raise MirrorError(f"entry {e['name']}: not an ISO or floppy image name (.iso, .img, .ima, .vfd)")
            check_name(e["name"], content)
        except MirrorError as err:
            errors.append(str(err))
            continue
        if complete(e["path"], None):
            want(content, e["name"], e["path"], "entry" if e["origin"] == "manual" else "import")

    # rules, in order: the first rule that matches a file names it
    ruled, excluded = set(), set()
    found = []  # every complete medium seen below a rule or watch directory: candidates for moves
    for r in cfg["rules"]:
        if not os.path.isdir(r["base"]):
            errors.append(f"rule {r['index']}: {r['base']} isn't a directory (not mounted?)")
            continue
        if r["glob"]:
            paths = sorted(p for p in glob.glob(r["glob"], recursive=True) if os.path.isfile(p)
                           and not any(inside(p, s) for s in skip))
        else:
            paths = walk_files(r["base"], skip)
        for path in paths:
            real = os.path.realpath(path)
            rel = os.path.relpath(path, r["base"])
            if real in covered or real in ruled:
                continue
            # the path below the source ('*/old/*' also matches 'old/x.iso': './old/x.iso'), or the name
            if any(fnmatch.fnmatch(rel, x) or fnmatch.fnmatch(f"./{rel}", x) or
                   fnmatch.fnmatch(os.path.basename(path), x) for x in r["exclude"]):
                excluded.add(real)
                continue
            st = stat(path)
            if st is None:
                continue
            content = media_content(path, r["img_as"], st.st_size)
            if not content:
                continue
            ruled.add(real)
            if not complete(path, r["base"]):
                continue
            found.append(path)
            try:
                name = link_name(os.path.basename(path) if r["flatten"] else rel, content, r["prefix"])
            except MirrorError as err:
                errors.append(f"rule {r['index']}: {err}")
                continue
            want(content, name, path, f"rule {r['index']}")

    # watch directories: what nothing covers
    unmatched, seen = [], set()
    for w in cfg["watch"]:
        if not os.path.isdir(w["path"]):
            errors.append(f"watch {w['raw']}: {w['path']} isn't a directory (not mounted?)")
            continue
        for path in walk_files(w["path"], skip):
            real = os.path.realpath(path)
            if real in covered or real in ruled or real in excluded or real in seen:
                continue
            st = stat(path)
            if st is None:
                continue
            content = media_content(path, "auto", st.st_size)
            if not content:
                continue
            seen.add(real)
            if not complete(path, w["path"]):
                continue
            found.append(path)
            row = {"path": path, "content": content, "name": None, "error": None}
            try:
                row["name"] = link_name(os.path.relpath(path, w["path"]), content, w["prefix"])
            except MirrorError as err:
                row["error"] = str(err)
            unmatched.append(row)
            if cfg["auto_import"] and row["name"]:
                want(content, row["name"], path, "auto")

    # moves: a missing file (of an entry, or behind a link apply made) found elsewhere, by size and
    # sha256 (recorded when apply linked it; without checksums by inode)
    moved = []
    by_size = {}
    for path in found:
        if os.path.realpath(path) not in covered:
            by_size.setdefault(stat(path).st_size, []).append(path)

    def find_move(record):
        for c in by_size.get(record.get("size"), []):
            if record.get("sha256"):
                if sha256(c) == record["sha256"]:
                    return c
            elif record.get("ino") and stat(c).st_ino == record["ino"] and stat(c).st_dev == record.get("dev"):
                return c
        return None

    # an entry whose file moved keeps its name: linked to the new place (tidy records it in the file),
    # and the file isn't linked a second time by a rule or auto_import
    gone_keys = set()
    for g in gone:
        e = g["entry"]
        key = next((k for k in state["links"] if k.split("/", 1)[1] == e["name"]), None)
        rec = state["links"].get(key) if key else None
        new = find_move(rec) if rec and g["available"] else None
        if new:
            moved.append({"key": key, "entry": e, "old": e["path"], "new": new})
            gone_keys.add(key)
            real = os.path.realpath(new)
            for k in list(wanted):
                wanted[k] = [r for r in wanted[k] if os.path.realpath(r["target"]) != real]
                if not wanted[k]:
                    del wanted[k]
            unmatched = [u for u in unmatched if os.path.realpath(u["path"]) != real]
            want(key.split("/", 1)[0], e["name"], new, "moved entry")

    desired, clashes = {}, []
    for key, rows in sorted(wanted.items()):
        targets = sorted({os.path.realpath(r["target"]) for r in rows})
        if len(targets) > 1:
            clashes.append({"name": f"{key[0]}/{key[1]}", "paths": sorted(r["target"] for r in rows)})
        else:
            desired[key] = rows[0]

    for key, rec in sorted(state["links"].items()):
        content, name = key.split("/", 1)
        if (content, name) in desired or key in gone_keys or os.path.exists(rec.get("target", "")):
            continue
        if any(g["entry"]["name"] == name for g in gone):
            continue
        new = find_move(rec) if source_available(rec.get("target", ""), bases) else None
        if new:
            newname = next((n for (c, n), d in desired.items() if os.path.realpath(d["target"]) ==
                            os.path.realpath(new)), None)
            moved.append({"key": key, "entry": None, "old": rec["target"], "new": new, "name": newname})
    return {"desired": desired, "unmatched": unmatched, "waiting": waiting, "gone": gone, "moved": moved,
            "clashes": clashes, "errors": errors, "bases": bases}


def actions(cfg, info, result, state):
    """What apply does to the storage's links: [{"op": create|replace|remove|keep, ...}] and the problems
    it leaves alone ([{"op": "conflict"|"unmanaged"|"flagged", ...}])."""
    dirs, style = info["dirs"], cfg["links"]
    ops, managed = [], state["links"]
    for (content, name), d in sorted(result["desired"].items()):
        if content not in dirs:
            ops.append({"op": "conflict", "key": f"{content}/{name}",
                        "why": f"the storage has no {content} content"})
            continue
        dest = os.path.join(dirs[content], name)
        key = f"{content}/{name}"
        text = link_text(d["target"], dirs[content], style)
        row = {"key": key, "dest": dest, "target": d["target"], "text": text, "origin": d["origin"]}
        if os.path.islink(dest):
            current = os.readlink(dest)
            ours = key in managed or resolves_to(dest, d["target"])
            if current == text:
                ops.append({"op": "keep", **row})
            elif ours:
                ops.append({"op": "replace", "was": current, **row})
            else:
                ops.append({"op": "conflict", **row,
                            "why": f"a link to {current} that apply didn't make (remove it, or give the file "
                                   f"another name)"})
        elif os.path.lexists(dest):
            ops.append({"op": "conflict", **row, "why": "a regular file of that name: left alone"})
        else:
            ops.append({"op": "create", **row})
    gone_manual = {g["entry"]["name"]: g for g in result["gone"] if g["entry"]["origin"] == "manual"}
    unavailable = {g["entry"]["name"] for g in result["gone"] if not g["available"]}
    for key, rec in sorted(managed.items()):
        content, name = key.split("/", 1)
        if (content, name) in result["desired"]:
            continue
        dest = os.path.join(dirs.get(content, ""), name)
        if not os.path.islink(dest):
            continue
        if name in gone_manual:
            ops.append({"op": "flagged", "key": key, "dest": dest,
                        "why": f"the file of the manual entry is gone ({gone_manual[name]['entry']['path']}); "
                               f"link kept (`tidy --include-manual` drops the entry)"})
        elif name in unavailable or (not os.path.exists(rec.get("target", "")) and
                                     not source_available(rec.get("target", ""), result["bases"])):
            ops.append({"op": "flagged", "key": key, "dest": dest,
                        "why": f"{rec.get('target')} is unreachable (share not mounted?): link kept"})
        else:
            why = "its file is gone" if not os.path.exists(link_target_path(dest)) else "no longer described"
            ops.append({"op": "remove", "key": key, "dest": dest, "target": rec.get("target"), "why": why})
    for row in scan_links(dirs):
        key = f"{row['content']}/{row['name']}"
        if row["target"] is None or key in managed or (row["content"], row["name"]) in result["desired"]:
            continue
        ops.append({"op": "unmanaged", "key": key, "dest": row["path"], "target": row["target"]})
    return ops


def file_record(path, old=None, checksums=True):
    st = os.stat(path)
    rec = {"target": os.path.abspath(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns, "ino": st.st_ino,
           "dev": st.st_dev}
    if old and old.get("sha256") and all(old.get(k) == rec[k] for k in ("target", "size", "mtime_ns")):
        rec["sha256"] = old["sha256"]
    elif checksums:
        rec["sha256"] = sha256(path)
    return rec


class locked:
    """An exclusive flock on the storage's lock file (over NFS a lock the server holds for every node),
    waiting up to `wait` seconds; Busy when another run holds it."""

    def __init__(self, root, wait=0.0):
        self.path, self.wait, self.f = os.path.join(root, LOCK_NAME), wait, None

    def __enter__(self):
        import fcntl
        self.f = open(self.path, "a+")
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self.f.close()
                    raise Busy(f"another `mirror apply|import|tidy` holds {self.path}; try again later "
                               f"(or --wait SECONDS)")
                time.sleep(0.5)

    def __exit__(self, *exc):
        self.f.close()


# --- editing the description file, keeping its comments --------------------------------------------

def _yaml_scalar(value):
    if re.fullmatch(r"[A-Za-z0-9_./][A-Za-z0-9_./+=-]*", value) and value.lower() not in (
            "null", "true", "false", "yes", "no", "on", "off", "~"):
        return value
    return json.dumps(value)


def _last_mark(node):
    if hasattr(node, "value") and isinstance(node.value, list) and node.value:
        last = node.value[-1]
        return _last_mark(last[1] if isinstance(last, tuple) else last)
    return node.end_mark


def _end_line(node):
    m = _last_mark(node)
    return m.line if m.column > 0 else m.line - 1


def _entries_node(text):
    yaml = _yaml()
    root = yaml.compose(text)
    if root is None:
        return None, None
    for k, v in root.value:
        if k.value == "entries":
            return k, v
    return None, None


def entry_text(name, source, origin, indent):
    pad = " " * indent
    return (f"{pad}- name: {_yaml_scalar(name)}\n{pad}  source: {_yaml_scalar(source)}\n"
            f"{pad}  origin: {origin}\n")


def add_entries(text, new):
    """The description file's text with entries [(name, source, origin)] added at the end of `entries`,
    everything else (comments included) as it was."""
    if not new:
        return text
    yaml = _yaml()
    key, node = _entries_node(text)
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    if key is None:
        block = "".join(entry_text(*e, 2) for e in new)
        return "".join(lines) + "entries:\n" + block
    if isinstance(node, yaml.SequenceNode) and node.value and not node.flow_style:
        first = node.value[0]
        indent = max(first.start_mark.column - 2, 0)
        at = _end_line(node.value[-1]) + 1
        block = "".join(entry_text(*e, indent) for e in new)
        return "".join(lines[:at]) + block + "".join(lines[at:])
    empty_flow = isinstance(node, yaml.SequenceNode) and not node.value
    empty_null = isinstance(node, yaml.ScalarNode) and node.tag.endswith(":null")
    if not (empty_flow or empty_null):
        raise MirrorError("entries must be a block list ('- name: ...' lines) for import and tidy to edit it")
    indent = key.start_mark.column + 2
    block = "".join(entry_text(*e, indent) for e in new)
    if empty_flow or node.end_mark.index > node.start_mark.index:
        # 'entries: []' or 'entries: ~': drop the value, keep a comment after it
        text2 = text[:node.start_mark.index] + text[node.end_mark.index:]
        lines = text2.splitlines(keepends=True)
    at = key.start_mark.line + 1
    lines[key.start_mark.line] = re.sub(r":\s*(#.*)?$", lambda m: ":" + (f"  {m.group(1)}" if m.group(1) else ""),
                                        lines[key.start_mark.line].rstrip("\n")) + "\n"
    return "".join(lines[:at]) + block + "".join(lines[at:])


def edit_entries(text, remove=(), resource=None):
    """The description file's text without the entries at the indexes in `remove`, and with the source
    of the entries in `resource` ({index: new source}) replaced; the rest as it was."""
    resource = resource or {}
    if not remove and not resource:
        return text
    yaml = _yaml()
    key, node = _entries_node(text)
    if not isinstance(node, yaml.SequenceNode) or node.flow_style:
        raise MirrorError("entries must be a block list ('- name: ...' lines) for tidy to edit it")
    edits = []  # (start index, end index, replacement), applied from the end
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for i, item in enumerate(node.value):
        if i in remove:
            start_line = item.start_mark.line
            if not lines[start_line].lstrip().startswith("-"):
                start_line -= 1  # '-' alone on the line above
            end_line = _end_line(item)
            edits.append((offsets[start_line], offsets[end_line + 1], ""))
        elif i in resource:
            for k, v in item.value:
                if k.value == "source":
                    edits.append((v.start_mark.index, v.end_mark.index, _yaml_scalar(resource[i])))
    for start, end, repl in sorted(edits, reverse=True):
        text = text[:start] + repl + text[end:]
    return text


def write_text(path, text):
    tmp = f"{path}.wsh-lab-mirror.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    except OSError:
        pass
    os.replace(tmp, path)


def file_source(path, root):
    """How the description file names a source: relative to the storage's root when inside it."""
    return os.path.relpath(path, root) if inside(path, root) else path


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
        state = make_link(source, dest, force=a.force, style=a.links)
    except (MirrorError, OSError) as e:
        sys.exit(f"mirror link: {e}")
    print(f"{state:8} {a.storage}:{content}/{name} -> {source}")
    return 0


def cmd_sync(a):
    try:
        info = storage_info(a.storage, warn=warn)
        dirs = info["dirs"]
        if os.path.exists(os.path.join(info["root"], CONFIG_NAME)):
            raise MirrorError(f"storage {a.storage} has a description file ({CONFIG_NAME}): use `mirror import` "
                              f"and `mirror apply`, which keep the links it describes")
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
            state = make_link(target, dest, dry_run=a.dry_run, style=a.links)
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
            outside = not inside(link_target_path(row["path"]), source)
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


def warn(msg):
    print(f"warning  {msg}", file=sys.stderr)


def open_described(a, need_file=True):
    """(storage name, storage info, config path, config) for the description-file commands."""
    storage = a.storage
    if not storage and a.config:
        try:
            with open(a.config, encoding="utf-8") as f:
                storage = (_yaml().safe_load(f) or {}).get("storage")
        except OSError as e:
            raise MirrorError(f"can't read {a.config}: {e.strerror}")
    if not storage:
        raise MirrorError("which storage? --storage S (or `storage: S` in the --config file)")
    info = storage_info(storage, warn=warn)
    path = config_path(info, a.config)
    cfg = load_config(path, info["root"]) if need_file else None
    if cfg and cfg["storage"] and cfg["storage"] != storage:
        raise MirrorError(f"{path} describes storage {cfg['storage']}, not {storage}")
    return storage, info, path, cfg


def plan_report(storage, result, ops):
    """The plan as printable lines and a problem count."""
    lines, problems = [], 0
    vol = lambda key: f"{storage}:{key}"  # noqa: E731
    for o in ops:
        if o["op"] == "create":
            lines.append(f"link     {vol(o['key'])} -> {o['text']} ({o['origin']})")
        elif o["op"] == "replace":
            lines.append(f"relink   {vol(o['key'])} -> {o['text']} (was {o['was']})")
        elif o["op"] == "remove":
            lines.append(f"unlink   {vol(o['key'])} ({o['why']})")
        elif o["op"] == "conflict":
            problems += 1
            lines.append(f"conflict {vol(o['key'])}: {o['why']}")
        elif o["op"] == "flagged":
            lines.append(f"flagged  {vol(o['key'])}: {o['why']}")
        elif o["op"] == "unmanaged":
            lines.append(f"unmanaged {vol(o['key'])} -> {o['target']} (a link apply didn't make: left alone)")
    for u in result["unmatched"]:
        if u["error"]:
            lines.append(f"new      {u['path']}: {u['error']}")
        else:
            how = "linked by auto_import" if u["name"] and any(
                d["target"] == u["path"] and d["origin"] == "auto" for d in result["desired"].values()) \
                else "`import` adds it"
            lines.append(f"new      {u['path']} as {u['content']}/{u['name']} ({how})")
    moved_entries = {m["entry"]["index"] for m in result["moved"] if m["entry"]}
    for g in result["gone"]:
        e = g["entry"]
        if e["index"] in moved_entries:
            continue
        if not g["available"]:
            lines.append(f"unreachable entry {e['name']} -> {e['path']} (share not mounted?)")
        else:
            act = "`tidy` drops it" if e["origin"] == "import" else "`tidy --include-manual` drops it"
            lines.append(f"gone     entry {e['name']} -> {e['path']} ({e['origin']}; {act})")
    for m in result["moved"]:
        if m["entry"]:
            lines.append(f"moved    entry {m['entry']['name']}: {m['old']} -> {m['new']} (linked there under its "
                         f"name; `tidy` writes the new path into the file)")
        else:
            new = f" (now {m['name']})" if m.get("name") else ""
            lines.append(f"moved    {vol(m['key'])}: {m['old']} -> {m['new']}{new}; an entry with the old name "
                         f"keeps the volume ID")
    for w in result["waiting"]:
        lines.append(f"waiting  {w['path']}: {w['why']}")
    for c in result["clashes"]:
        problems += 1
        lines.append(f"clash    {vol(c['name'])}: the same name for {', '.join(c['paths'])}; none linked")
    for err in result["errors"]:
        problems += 1
        lines.append(f"error    {err}")
    return lines, problems


def summary(ops, result, done=False):
    n = lambda op: sum(o["op"] == op for o in ops)  # noqa: E731
    verbs = ("linked", "relinked", "unlinked") if done else ("to link", "to relink", "to unlink")
    return (f"{n('create')} {verbs[0]}, {n('replace')} {verbs[1]}, {n('remove')} {verbs[2]}, {n('keep')} in place, "
            f"{len(result['unmatched'])} not covered, {len(result['waiting'])} waiting, "
            f"{len(result['clashes'])} clashes, {n('conflict')} conflicts")


def cmd_plan(a):
    try:
        storage, info, path, cfg = open_described(a)
        state = read_state(info["root"])
        result = build(cfg, info, state)
        ops = actions(cfg, info, result, state)
    except MirrorError as e:
        sys.exit(f"mirror plan: {e}")
    lines, problems = plan_report(storage, result, ops)
    if a.json:
        print(json.dumps({"actions": ops, "unmatched": result["unmatched"], "waiting": result["waiting"],
                          "gone": [{"name": g["entry"]["name"], "source": g["entry"]["path"],
                                    "origin": g["entry"]["origin"], "available": g["available"]}
                                   for g in result["gone"]],
                          "moved": [{"key": m["key"], "entry": m["entry"]["name"] if m["entry"] else None,
                                     "old": m["old"], "new": m["new"]} for m in result["moved"]],
                          "clashes": result["clashes"], "errors": result["errors"]}, indent=1))
    else:
        for line in lines:
            print(line)
        print(summary(ops, result))
    return 1 if problems else 0


def cmd_apply(a):
    try:
        storage, info, path, cfg = open_described(a)
        with locked(info["root"], a.wait):
            state = read_state(info["root"])
            result = build(cfg, info, state)
            ops = actions(cfg, info, result, state)
            lines, problems = plan_report(storage, result, ops)
            new_links = {}
            for o in ops:
                try:
                    if o["op"] in ("create", "replace", "keep"):
                        if not a.dry_run and o["op"] != "keep":
                            make_link(o["target"], o["dest"], style=cfg["links"], adopt=True,
                                      force=o["op"] == "replace")
                        new_links[o["key"]] = file_record(o["target"], state["links"].get(o["key"]),
                                                          cfg["checksums"]) if not a.dry_run else None
                    elif o["op"] == "remove" and not a.dry_run:
                        if os.path.islink(o["dest"]):
                            os.unlink(o["dest"])
                    elif o["op"] == "flagged":
                        new_links[o["key"]] = state["links"].get(o["key"])
                except (MirrorError, OSError) as e:
                    # one link that can't be made (a CIFS share without mfsymlinks, a file that just
                    # went away) doesn't stop the others
                    lines.append(f"error    {storage}:{o['key']}: {e}")
                    problems += 1
                    if o["op"] == "remove" and o["key"] in state["links"]:
                        new_links[o["key"]] = state["links"][o["key"]]
            if not a.dry_run:
                write_state(info["root"], {"version": 1, "links": new_links})
    except Busy as e:
        print(f"mirror apply: {e}", file=sys.stderr)
        return BUSY
    except (MirrorError, OSError) as e:
        sys.exit(f"mirror apply: {e}")
    for line in lines:
        if not a.quiet or not line.startswith(("unmanaged", "new ", "waiting")):
            print(line)
    dry = " (dry run: nothing changed)" if a.dry_run else ""
    print(summary(ops, result, done=not a.dry_run) + dry)
    return 1 if problems else 0


def cmd_import(a):
    try:
        storage, info, path, cfg = open_described(a)
        with locked(info["root"], a.wait):
            result = build(cfg, info, read_state(info["root"]))
            taken = {n for (_, n) in result["desired"]} | {e["name"] for e in cfg["entries"]}
            new, skipped = [], []
            for u in result["unmatched"]:
                if not u["name"]:
                    skipped.append(f"{u['path']}: {u['error']}")
                elif u["name"] in taken and not any(d["target"] == u["path"] for d in result["desired"].values()):
                    skipped.append(f"{u['path']}: the name {u['name']} is taken")
                else:
                    taken.add(u["name"])
                    new.append((u["name"], file_source(u["path"], info["root"]), "import"))
            if new and not a.dry_run:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                text = add_entries(text, new)
                check_config(_yaml().safe_load(text), info["root"], path)
                write_text(path, text)
    except Busy as e:
        print(f"mirror import: {e}", file=sys.stderr)
        return BUSY
    except (MirrorError, OSError) as e:
        sys.exit(f"mirror import: {e}")
    for name, source, _ in new:
        print(f"import   {name} -> {source}")
    for s in skipped:
        print(f"skipped  {s}")
    dry = " (dry run: nothing changed)" if a.dry_run else ""
    print(f"{len(new)} entries added to {path}, {len(skipped)} skipped{dry}"
          + ("; `mirror apply` links them" if new and not a.dry_run else ""))
    return 1 if skipped else 0


def cmd_tidy(a):
    try:
        storage, info, path, cfg = open_described(a)
        with locked(info["root"], a.wait):
            result = build(cfg, info, read_state(info["root"]))
            origins = ("import", "manual") if a.include_manual else ("import",)
            moved = {m["entry"]["index"]: m for m in result["moved"] if m["entry"]
                     and m["entry"]["origin"] in origins}
            remove = {g["entry"]["index"]: g["entry"] for g in result["gone"] if g["available"]
                      and g["entry"]["origin"] in origins and g["entry"]["index"] not in moved}
            resource = {i: file_source(m["new"], info["root"]) for i, m in moved.items()}
            if (remove or resource) and not a.dry_run:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                text = edit_entries(text, remove, resource)
                check_config(_yaml().safe_load(text), info["root"], path)
                write_text(path, text)
    except Busy as e:
        print(f"mirror tidy: {e}", file=sys.stderr)
        return BUSY
    except (MirrorError, OSError) as e:
        sys.exit(f"mirror tidy: {e}")
    for i, m in sorted(moved.items()):
        print(f"follow   {m['entry']['name']}: {m['old']} -> {resource[i]}")
    for e in remove.values():
        print(f"drop     {e['name']} -> {e['path']} ({e['origin']}, file gone)")
    kept = [g for g in result["gone"] if g["entry"]["index"] not in remove and g["entry"]["index"] not in moved]
    for g in kept:
        e = g["entry"]
        print(f"kept     {e['name']} -> {e['path']} ({e['origin']}"
              + (", unreachable)" if not g["available"] else ", --include-manual drops it)"))
    dry = " (dry run: nothing changed)" if a.dry_run else ""
    print(f"{len(moved)} followed, {len(remove)} dropped, {len(kept)} kept{dry}"
          + ("; `mirror apply` updates the links" if (moved or remove) and not a.dry_run else ""))
    return 0


INIT_TEXT = """\
# wsh-mirror.yaml: what `wsh-lab mirror apply` links into the storage {storage}
# (`man wsh-lab`, https://debian.wshosting.no/reference/mirror/). Relative paths are relative to the
# storage's path ({root}). PVE doesn't see this file. To rename a volume, give its file an entry with
# the new name (or edit the entry's name) and run `wsh-lab mirror apply`.
version: 1
storage: {storage}
# Directories whose ISO and floppy images `plan` reports when no rule or entry covers them; `import`
# adds them as entries, auto_import links them right away. The name is the path below the directory,
# its folders joined with '__' (a prefix adds folders in front).
watch:{watch}
auto_import: false
# Files still being written are never linked: names like these, or changed less than min_age ago.
# Better still, let the download client keep unfinished files in a folder of their own.
incomplete:
  patterns: ['*.part', '*.!qB', '*.!ut', '*.incomplete', '*.crdownload', '*.partial']
  min_age: 5min
# relative link targets when the file is on the storage's file system (an NFS export holding both),
# absolute otherwise; or always relative / absolute
links: auto
# Rules link every image below a directory, or matching a glob, named after its path below it.
rules: []
#  - source: /mnt/pve/nas/torrents/*/*.iso
#    prefix: Torrents
#    exclude: ['*/extras/*']
#    flatten: false        # true: the file name alone after the prefix
# Single files with names of their own (origin: manual), and the ones `import` added (origin: import).
entries: []
#  - name: Solaris__2.6__solaris_2.6_598_sparc.iso
#    source: /mnt/pve/nas/sun/sol-2.6-598.iso
#    origin: manual
"""


def cmd_init(a):
    try:
        info = storage_info(a.storage, warn=warn)
        path = config_path(info, a.config)
        if os.path.exists(path) and not a.force:
            raise MirrorError(f"{path} exists (--force overwrites it)")
        watch = "".join(f"\n  - {_yaml_scalar(file_source(os.path.abspath(w), info['root']))}" for w in a.watch) \
            or " []"
        text = INIT_TEXT.format(storage=a.storage, root=info["root"], watch=watch)
        check_config(_yaml().safe_load(text), info["root"], path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except (MirrorError, OSError) as e:
        sys.exit(f"mirror init: {e}")
    print(f"wrote {path}; then `mirror plan --storage {a.storage}`")
    return 0


TIMER_INTERVAL = re.compile(r"\d+\s*(s|sec|m|min|h|hr|d)?")


def mirror_command():
    """How a systemd unit runs `mirror <subcommand>`: the package's wrapper, the checkout's lab.py, or
    this file on its own (`python3 mirror.py apply ...`)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if os.environ.get("LAB_PROG") == "wsh-lab" or here == "/usr/share/wsh-lab":
        return ["/usr/bin/wsh-lab", "mirror"]
    if os.path.exists(os.path.join(here, "lab.py")):
        return [sys.executable, os.path.join(here, "lab.py"), "mirror"]
    return [sys.executable, os.path.abspath(__file__)]


def systemctl(*args):
    subprocess.run(["systemctl", *args], check=True)


def unit_name(storage):
    return f"wsh-lab-mirror-{re.sub(r'[^A-Za-z0-9_.-]', '_', storage)}"


def cmd_timer(a):
    unit_dir = os.environ.get("WSH_LAB_SYSTEMD_DIR") or SYSTEMD_DIR
    try:
        if not TIMER_INTERVAL.fullmatch(a.interval):
            raise MirrorError(f"--interval {a.interval!r}: a systemd time span such as 10min, 1h")
        storage = a.storage
        if not storage and a.config:
            with open(a.config, encoding="utf-8") as f:
                storage = (_yaml().safe_load(f) or {}).get("storage")
        if not storage:
            raise MirrorError("which storage? --storage S (or `storage: S` in the --config file)")
        name = unit_name(storage)
        service, timer = (os.path.join(unit_dir, f"{name}.{ext}") for ext in ("service", "timer"))
        if a.remove:
            if os.path.exists(timer):
                systemctl("disable", "--now", f"{name}.timer")
            for p in (service, timer):
                if os.path.exists(p):
                    os.unlink(p)
            systemctl("daemon-reload")
            print(f"removed {name}.timer and {name}.service")
            return 0
        storage, info, path, cfg = open_described(a)  # the file must exist and be valid
        cmd = mirror_command() + ["apply", "--storage", storage, "--quiet"]
        if a.config:
            cmd += ["--config", os.path.abspath(a.config)]
        with open(service, "w", encoding="utf-8") as f:
            f.write(f"""[Unit]
Description=wsh-lab mirror apply for storage {storage} ({path})
Documentation=man:wsh-lab(1) https://debian.wshosting.no/reference/mirror/
After=network-online.target remote-fs.target pve-cluster.service

[Service]
Type=oneshot
ExecStart={shlex.join(cmd)}
# {BUSY}: another node's or run's apply held the lock
SuccessExitStatus={BUSY}
Nice=10
IOSchedulingClass=idle
""")
        with open(timer, "w", encoding="utf-8") as f:
            f.write(f"""[Unit]
Description=Run wsh-lab mirror apply for storage {storage} every {a.interval}

[Timer]
OnBootSec=2min
OnUnitInactiveSec={a.interval}
RandomizedDelaySec=30s

[Install]
WantedBy=timers.target
""")
        systemctl("daemon-reload")
        systemctl("enable", "--now", f"{name}.timer")
    except (MirrorError, OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"mirror timer: {e}")
    print(f"installed {timer} (every {a.interval}): {shlex.join(cmd)}")
    print(f"  systemctl list-timers {name}.timer; journalctl -u {name}.service")
    return 0


def cmd_mirror(a):
    return {"link": cmd_link, "sync": cmd_sync, "list": cmd_list, "init": cmd_init, "plan": cmd_plan,
            "apply": cmd_apply, "import": cmd_import, "tidy": cmd_tidy, "timer": cmd_timer}[a.mirror_cmd](a)


def add_commands(sub):
    m = sub.add_parser("mirror", help="a mirror storage: symlinks to ISO and floppy images elsewhere (a NAS), "
                                      "folders kept in the link name with '__'")
    msub = m.add_subparsers(dest="mirror_cmd", required=True)
    links_help = "link targets: absolute (default), relative, or auto (relative on the same file system)"
    lk = msub.add_parser("link", help="link one ISO or floppy image into the storage")
    lk.add_argument("source", help="the image")
    lk.add_argument("--storage", default="local", help="the mirror storage (local)")
    g = lk.add_mutually_exclusive_group()
    g.add_argument("--root", help="name the link after the source's path below this directory, joined with '__' "
                                  "(default: the file name alone)")
    g.add_argument("--as", dest="as_name", metavar="NAME", help="the link's name")
    lk.add_argument("--content", choices=sorted(SUBDIRS),
                    help="iso or floppy (default: by extension; .img by size, up to 2.88 MB a floppy)")
    lk.add_argument("--force", action="store_true", help="replace a link of that name to another target")
    lk.add_argument("--links", choices=("absolute", "relative", "auto"), default="absolute", help=links_help)
    sy = msub.add_parser("sync", help="link every ISO and floppy image under a directory tree")
    sy.add_argument("source", help="the top of the tree; the link names are the paths below it")
    sy.add_argument("--storage", default="local", help="the mirror storage (local)")
    sy.add_argument("--prune", action="store_true",
                    help="also remove links (never regular files) whose target is gone or outside the tree")
    sy.add_argument("--img-as", choices=("auto", "iso", "floppy"), default="auto",
                    help=".img files: by size (auto: up to 2.88 MB a floppy), or all ISO or all floppy")
    sy.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    sy.add_argument("--links", choices=("absolute", "relative", "auto"), default="absolute", help=links_help)
    ls = msub.add_parser("list", help="the storage's links and their targets, dangling ones marked")
    ls.add_argument("--storage", default="local", help="the mirror storage (local)")
    ls.add_argument("--json", action="store_true")

    def described(p, wait=True):
        p.add_argument("--storage", help="the mirror storage (default: `storage:` in the --config file)")
        p.add_argument("--config", metavar="PATH",
                       help=f"the description file (default: {CONFIG_NAME} at the storage's root; e.g. one in "
                            f"/etc/pve/nodes/<node>/ for a per-node mirror)")
        if wait:
            p.add_argument("--wait", type=float, default=0.0, metavar="SECONDS",
                           help="wait this long for another run's lock (default: give up at once, exit 75)")

    it = msub.add_parser("init", help=f"write a commented description file ({CONFIG_NAME})")
    it.add_argument("--storage", required=True, help="the mirror storage")
    it.add_argument("--config", metavar="PATH", help=f"where (default: {CONFIG_NAME} at the storage's root)")
    it.add_argument("--watch", action="append", default=[], metavar="DIR",
                    help="a directory whose images plan/import look at (repeatable)")
    it.add_argument("--force", action="store_true", help="overwrite an existing file")
    pl = msub.add_parser("plan", help="what apply would change; files nothing covers, gone, moved, clashes")
    described(pl, wait=False)
    pl.add_argument("--json", action="store_true")
    ap = msub.add_parser("apply", help="make the links match the description file (idempotent)")
    described(ap)
    ap.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    ap.add_argument("--quiet", action="store_true", help="only the changes and problems (for the timer)")
    im = msub.add_parser("import", help="add entries (origin: import) for the images no rule or entry covers")
    described(im)
    im.add_argument("--dry-run", action="store_true", help="say what would be added, change nothing")
    td = msub.add_parser("tidy", help="drop entries whose file is gone, follow moved files (import entries)")
    described(td)
    td.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    td.add_argument("--include-manual", action="store_true", help="manual entries too")
    tm = msub.add_parser("timer", help="install (or --remove) a systemd timer that runs apply")
    described(tm, wait=False)
    tm.add_argument("--interval", default="10min", help="how often (a systemd time span; 10min)")
    tm.add_argument("--remove", action="store_true", help="stop and remove the timer")


COMMANDS = {"mirror": cmd_mirror}


def main(argv=None):
    """`python3 mirror.py <command> ...` without lab.py (the e2e tests run it in the PVE container)."""
    import argparse
    p = argparse.ArgumentParser(prog="mirror.py")
    add_commands(p.add_subparsers(dest="cmd", required=True))
    a = p.parse_args(["mirror", *(sys.argv[1:] if argv is None else argv)])
    return cmd_mirror(a)


if __name__ == "__main__":
    sys.exit(main())
