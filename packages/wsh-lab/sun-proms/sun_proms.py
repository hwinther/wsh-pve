#!/usr/bin/env python3
"""wsh-sun-proms: install Sun boot PROM images you are entitled to use, from a source you provide.

The PROMs go where QEMU looks for firmware (/usr/share/kvm), so qemu-server's sparc32 profiles and
the PVE UI find them under the names they use (bios: ss5.bin, ss20_v2.25_rom, lx.bin). Every file is
checked against a manifest of known images (name, size, SHA-256); unknown or differing files are
refused unless --force.

  wsh-sun-proms install --source SRC [NAME ...]   copy the known PROMs found in SRC
  wsh-sun-proms status                            which known PROMs are there, and from where
  wsh-sun-proms verify [NAME ...]                 exit 1 unless the PROMs there match the manifest
  wsh-sun-proms remove [NAME ...]                 remove the PROMs this tool installed

SRC is a local directory, a tar or zip archive, a git repository URL (cloned with your own git
credentials into a temporary directory) or an HTTPS URL (a base URL the PROMs are under by name, or
an archive). Nothing about the source is stored except its location without credentials. Standard
library only: this runs with the python3 of any PVE node.
"""

import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field

DEFAULT_DIR = "/usr/share/kvm"
DEFAULT_STATE = "/var/lib/wsh-sun-proms/installed.tsv"
DEFAULT_MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")
ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".zip")
GIT_PREFIXES = ("git@", "ssh://", "git://", "git+https://", "git+ssh://", "git+file://", "git+http://")
LOOPBACK = ("localhost", "127.0.0.1", "::1")
# No file in a source larger than this is read: the PROMs are a few hundred KiB
MAX_FILE = 16 * 1024 * 1024
HTTP_TIMEOUT = 60

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


class Error(Exception):
    """A failure to report without a traceback."""


@dataclass(frozen=True)
class Prom:
    name: str
    machine: str
    size: int
    sha256: str
    description: str


@dataclass
class Manifest:
    proms: list
    path: str = ""
    by_name: dict = field(default_factory=dict)
    by_sha: dict = field(default_factory=dict)

    def __post_init__(self):
        self.by_name = {p.name: p for p in self.proms}
        self.by_sha = {p.sha256: p for p in self.proms}

    def sizes(self):
        return {p.size for p in self.proms}


def valid_name(name):
    """A plain file name: no directory part, not hidden, not empty."""
    return bool(name) and "/" not in name and "\\" not in name and not name.startswith(".") and "\0" not in name


def load_manifest(path):
    """Reads and checks the manifest: every entry with a plain name, a size and a lowercase SHA-256,
    names and hashes unique. Raises Error on anything else."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise Error(f"can't read the manifest {path}: {e.strerror}") from e
    except json.JSONDecodeError as e:
        raise Error(f"the manifest {path} isn't JSON: {e}") from e
    entries = data.get("proms") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise Error(f"the manifest {path} has no 'proms' list")
    proms, names, hashes = [], set(), set()
    for i, e in enumerate(entries):
        where = f"{path}: entry {i + 1}"
        if not isinstance(e, dict):
            raise Error(f"{where} isn't an object")
        name, sha, size = e.get("name"), e.get("sha256"), e.get("size")
        if not isinstance(name, str) or not valid_name(name):
            raise Error(f"{where}: bad name {name!r}")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise Error(f"{where} ({name}): sha256 must be 64 lowercase hex digits")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise Error(f"{where} ({name}): size must be a positive integer")
        for key in ("machine", "description"):
            if not isinstance(e.get(key), str) or not e[key]:
                raise Error(f"{where} ({name}): no {key}")
        if name in names:
            raise Error(f"{where}: {name} is listed twice")
        if sha in hashes:
            raise Error(f"{where} ({name}): its sha256 is listed twice")
        names.add(name)
        hashes.add(sha)
        proms.append(Prom(name, e["machine"], size, sha, e["description"]))
    return Manifest(proms, path)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(manifest, name, data):
    """'ok' when DATA is the manifest's NAME, 'mismatch' when NAME is known but DATA differs,
    'unknown' when the manifest has no NAME."""
    prom = manifest.by_name.get(name)
    if prom is None:
        return "unknown"
    if len(data) == prom.size and sha256_bytes(data) == prom.sha256:
        return "ok"
    return "mismatch"


# ---------------------------------------------------------------------------------------------
# Sources: each gives candidates, (path in the source, loader) pairs; a loader returns the bytes.


@dataclass
class Candidate:
    path: str  # where in the source, for messages
    size: int
    load: object  # () -> bytes

    @property
    def name(self):
        return self.path.rstrip("/").rsplit("/", 1)[-1]


def strip_credentials(source):
    """The source as it may be recorded and printed: a URL without user, password, query or fragment
    (tokens travel in any of them); scp-like git addresses (git@host:path) and paths unchanged."""
    if "://" not in source:
        return source
    u = urllib.parse.urlsplit(source)
    host = u.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = host + (f":{u.port}" if u.port else "")
    return urllib.parse.urlunsplit((u.scheme, netloc, u.path, "", ""))


def source_kind(source, forced=None):
    """dir, archive, git or http, from the source's form (or --type)."""
    if forced:
        return forced
    low = source.lower()
    if low.startswith(GIT_PREFIXES):
        return "git"
    if low.startswith(("https://", "http://")):
        return "git" if low.rstrip("/").endswith(".git") else "http"
    if low.startswith("file://"):
        return "git"
    if os.path.isdir(source):
        # a bare repository (repo.git) is cloned, a working tree read as it is
        if os.path.isfile(os.path.join(source, "HEAD")) and os.path.isdir(os.path.join(source, "objects")):
            return "git"
        return "dir"
    if os.path.isfile(source):
        return "archive"
    raise Error(f"no such directory or file: {source} (a URL needs https://, ssh:// or git@host:path)")


def dir_candidates(root):
    if not os.path.isdir(root):
        raise Error(f"not a directory: {root}")
    out = []
    for top, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for f in sorted(files):
            p = os.path.join(top, f)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if not os.path.isfile(p) or size > MAX_FILE:
                continue
            rel = os.path.relpath(p, root).replace(os.sep, "/")

            def load(p=p):
                with open(p, "rb") as fh:
                    return fh.read(MAX_FILE + 1)

            out.append(Candidate(rel, size, load))
    return out


def archive_candidates(data, label):
    """The regular files of a tar or zip archive (DATA, its bytes), read in memory: nothing is
    extracted, so names like ../x can't escape."""
    out = []
    if zipfile.is_zipfile(io.BytesIO(data)):
        z = zipfile.ZipFile(io.BytesIO(data))
        for info in z.infolist():
            if info.is_dir() or info.file_size > MAX_FILE:
                continue
            out.append(Candidate(info.filename, info.file_size, lambda info=info: z.read(info)))
        return out
    try:
        t = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except tarfile.TarError as e:
        raise Error(f"{label} is neither a tar nor a zip archive: {e}") from e
    for m in t.getmembers():
        if not m.isfile() or m.size > MAX_FILE:
            continue

        def load(m=m):
            f = t.extractfile(m)
            return f.read() if f else b""

        out.append(Candidate(m.name, m.size, load))
    return out


def read_limited(stream, label):
    data = stream.read(MAX_FILE * 8 + 1)
    if len(data) > MAX_FILE * 8:
        raise Error(f"{label} is larger than {MAX_FILE * 8 // (1024 * 1024)} MiB")
    return data


def check_http_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme == "https":
        return
    if u.scheme == "http" and (u.hostname or "") in LOOPBACK:
        return  # a test server on this host
    raise Error(f"only https:// URLs are fetched: {strip_credentials(url)}")


def http_get(url):
    """The body of URL, or None on 404. Certificates are checked (urllib's default context)."""
    check_http_url(url)
    # user:password in the URL goes as basic auth, for this request only; the query stays (a signed
    # URL's token is in it)
    u = urllib.parse.urlsplit(url)
    headers = {"User-Agent": "wsh-sun-proms"}
    if u.username is not None:
        cred = f"{urllib.parse.unquote(u.username)}:{urllib.parse.unquote(u.password or '')}"
        headers["Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
        host = f"[{u.hostname}]" if ":" in (u.hostname or "") else (u.hostname or "")
        url = urllib.parse.urlunsplit((u.scheme, host + (f":{u.port}" if u.port else ""), u.path, u.query, ""))
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return read_limited(r, strip_credentials(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Error(f"{strip_credentials(url)}: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise Error(f"{strip_credentials(url)}: {e.reason}") from e


def http_candidates(base, names):
    """An archive URL gives its files; a base URL gives BASE/<name> for each wanted name it has."""
    if urllib.parse.urlsplit(base).path.lower().endswith(ARCHIVE_SUFFIXES):
        data = http_get(base)
        if data is None:
            raise Error(f"{strip_credentials(base)}: not found (404)")
        return archive_candidates(data, strip_credentials(base))
    base = base if base.endswith("/") else base + "/"
    out = []
    for name in names:
        data = http_get(base + urllib.parse.quote(name))
        if data is not None:
            out.append(Candidate(name, len(data), lambda data=data: data))
    return out


def git_clone(url, ref, dest):
    """A shallow clone of URL into DEST with the user's own git configuration and credentials; git
    prompts only when there is a terminal to prompt on."""
    git = shutil.which("git")
    if not git:
        raise Error("a git source needs git: apt install git")
    if url.lower().startswith("git+"):
        url = url[4:]
    cmd = [git, "clone", "--quiet", "--depth", "1", "--no-tags"]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, dest]
    env = dict(os.environ)
    if not sys.stdin.isatty():
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
    r = subprocess.run(cmd, env=env, stdin=None if sys.stdin.isatty() else subprocess.DEVNULL, check=False)
    if r.returncode != 0:
        raise Error(f"git clone of {strip_credentials(url)} failed (exit {r.returncode})")


# ---------------------------------------------------------------------------------------------
# What is on the node: the files, the package that owns them, and this tool's record.


def dpkg_owner(path):
    """The package that has PATH installed, or None (also without dpkg)."""
    query = shutil.which("dpkg-query")
    if not query:
        return None
    r = subprocess.run([query, "-S", path], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        pkg, sep, owned = line.partition(": ")
        if sep and owned.strip() == path and "diversion" not in pkg:
            return pkg.split(":")[0].split(",")[0].strip()
    return None


@dataclass
class Record:
    name: str
    sha256: str
    size: int
    dir: str
    source: str
    installed: str


class State:
    """What this tool installed: one line per file, name TAB sha256 TAB size TAB dir TAB source TAB
    time. The source is recorded without credentials. The file goes away when nothing is in it."""

    def __init__(self, path):
        self.path = path
        self.records = {}
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) != 6 or not parts[2].isdigit():
                        continue
                    r = Record(parts[0], parts[1], int(parts[2]), parts[3], parts[4], parts[5])
                    self.records[(r.dir, r.name)] = r
        except FileNotFoundError:
            pass

    def get(self, d, name):
        return self.records.get((d, name))

    def put(self, r):
        self.records[(r.dir, r.name)] = r

    def drop(self, d, name):
        self.records.pop((d, name), None)

    def in_dir(self, d):
        return [r for (rd, _), r in sorted(self.records.items()) if rd == d]

    def save(self):
        if not self.records:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            try:
                os.rmdir(os.path.dirname(self.path))
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(self.path), mode=0o755, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for _, r in sorted(self.records.items()):
                f.write("\t".join([r.name, r.sha256, str(r.size), r.dir, r.source.replace("\t", " "), r.installed]) + "\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.path)


@dataclass
class Row:
    name: str
    machine: str
    state: str  # ok, mismatch, missing, unknown
    source: str
    sha256: str = ""
    size: int = 0
    description: str = ""


def describe_source(path, sha, state, d):
    """Where the file at PATH (SHA) came from: the package that owns it, this tool's record, or
    neither."""
    owner = dpkg_owner(path)
    if owner:
        return f"package {owner}"
    r = state.get(d, os.path.basename(path))
    if r and r.sha256 == sha:
        return f"wsh-sun-proms, from {r.source} ({r.installed[:10]})"
    if r:
        return "changed since wsh-sun-proms installed it"
    return "not recorded (copied by hand?)"


def survey(manifest, d, state):
    """One row per known PROM, then one per file this tool installed with --force that the
    manifest doesn't know."""
    rows = []
    for p in manifest.proms:
        path = os.path.join(d, p.name)
        if not os.path.isfile(path):
            rows.append(Row(p.name, p.machine, "missing", "", description=p.description))
            continue
        sha = sha256_file(path)
        size = os.path.getsize(path)
        st = "ok" if sha == p.sha256 and size == p.size else "mismatch"
        rows.append(Row(p.name, p.machine, st, describe_source(path, sha, state, d), sha, size, p.description))
    for r in state.in_dir(d):
        if r.name in manifest.by_name:
            continue
        path = os.path.join(d, r.name)
        if os.path.isfile(path):
            sha = sha256_file(path)
            rows.append(Row(r.name, "?", "unknown", describe_source(path, sha, state, d), sha, os.path.getsize(path)))
    return rows


# ---------------------------------------------------------------------------------------------
# Commands


def say(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"wsh-sun-proms: {msg}", file=sys.stderr, flush=True)


def write_file(d, name, data):
    """DATA as D/NAME, mode 0644 (owner root when run as root), replaced in one step."""
    os.makedirs(d, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        fix_file(tmp)
        os.replace(tmp, os.path.join(d, name))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def fix_file(path):
    os.chmod(path, 0o644)
    if os.geteuid() == 0:
        os.chown(path, 0, 0)


def pick(manifest, candidates, wanted, force):
    """Decides which candidate to install for each wanted name. Returns (plan, problems, missing):
    plan is [(name, candidate, data, verdict)], verdict ok, mismatch (with --force) or unknown (with
    --force); problems are refusals; missing are known names the source doesn't have."""
    by_name = {}
    for c in candidates:
        by_name.setdefault(c.name, []).append(c)
    sizes = manifest.sizes()
    hashed = {}  # candidate path -> (sha, data), for files of a size the manifest has

    def content(c):
        if c.path not in hashed:
            data = c.load()
            hashed[c.path] = (sha256_bytes(data), data)
        return hashed[c.path]

    plan, problems, missing = [], [], []
    for name in wanted:
        prom = manifest.by_name.get(name)
        same_name = by_name.get(name, [])
        if prom is None:
            if not same_name:
                problems.append(f"{name}: unknown to the manifest and not in the source")
            elif not force:
                problems.append(f"{name}: unknown to the manifest (its sha256 can't be checked); --force installs it anyway")
            else:
                sha, data = content(same_name[0])
                plan.append((name, same_name[0], data, "unknown"))
            continue
        chosen = None
        # the right content under its own name, else under any name (a renamed copy)
        for c in same_name + [c for c in candidates if c.name != name and c.size == prom.size]:
            if c.size not in sizes:
                continue
            sha, data = content(c)
            if sha == prom.sha256:
                chosen = (c, data)
                break
        if chosen:
            plan.append((name, chosen[0], chosen[1], "ok"))
        elif same_name:
            sha, data = content(same_name[0])
            if force:
                plan.append((name, same_name[0], data, "mismatch"))
            else:
                problems.append(
                    f"{name}: {same_name[0].path} in the source has sha256 {sha} ({len(data)} bytes), the manifest "
                    f"expects {prom.sha256} ({prom.size} bytes); --force installs it anyway"
                )
        else:
            missing.append(name)
    return plan, problems, missing


def cmd_install(args, manifest):
    d = os.path.abspath(args.dir)
    explicit = bool(args.names)
    wanted = args.names or [p.name for p in manifest.proms]
    for n in wanted:
        if not valid_name(n):
            raise Error(f"not a file name: {n!r}")
    kind = source_kind(args.source, args.type)
    label = strip_credentials(args.source) if kind in ("git", "http") else os.path.abspath(args.source)
    say(f"Source: {label} ({kind})")

    with tempfile.TemporaryDirectory(prefix="wsh-sun-proms.") as tmp:
        if kind == "dir":
            candidates = dir_candidates(args.source)
        elif kind == "archive":
            with open(args.source, "rb") as f:
                candidates = archive_candidates(read_limited(f, args.source), args.source)
        elif kind == "git":
            git_clone(args.source, args.ref, os.path.join(tmp, "src"))
            candidates = dir_candidates(os.path.join(tmp, "src"))
        else:
            candidates = http_candidates(args.source, wanted)
        plan, problems, missing = pick(manifest, candidates, wanted, args.force)

    state = State(args.state)
    rc = EXIT_OK
    for p in problems:
        warn(f"refused: {p}")
        rc = EXIT_FAIL
    done = 0
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, cand, data, verdict in plan:
        target = os.path.join(d, name)
        sha = sha256_bytes(data)
        if os.path.isfile(target):
            have = sha256_file(target)
            owner = dpkg_owner(target)
            if have == sha:
                if owner:
                    say(f"  {name:<16} already there, from package {owner}")
                else:
                    if not args.dry_run:
                        fix_file(target)
                    if not state.get(d, name):
                        state.put(Record(name, sha, len(data), d, label, now))
                    say(f"  {name:<16} already installed")
                done += 1
                continue
            if not args.force:
                whose = f"package {owner}'s" if owner else "a different"
                warn(f"refused: {target} is {whose} file (sha256 {have}); --force replaces it")
                rc = EXIT_FAIL
                continue
        if args.dry_run:
            say(f"  {name:<16} would install from {cand.path} ({verdict})")
            done += 1
            continue
        try:
            write_file(d, name, data)
        except PermissionError as e:
            raise Error(f"can't write {target}: {e.strerror} (run as root)") from e
        state.put(Record(name, sha, len(data), d, label, now))
        note = {"ok": "sha256 matches", "mismatch": "sha256 DIFFERS, --force", "unknown": "not in the manifest, --force"}[verdict]
        say(f"  {name:<16} installed from {cand.path} ({note})")
        done += 1
    for name in missing:
        if explicit:
            warn(f"{name}: not in the source")
            rc = EXIT_FAIL
        else:
            say(f"  {name:<16} not in the source")
    if not args.dry_run:
        try:
            state.save()
        except PermissionError as e:
            raise Error(f"can't write {args.state}: {e.strerror} (run as root)") from e
    if done == 0 and rc == EXIT_OK:
        warn("no known Sun PROM found in the source")
        rc = EXIT_FAIL
    return rc


def print_rows(rows, d, as_json):
    if as_json:
        json.dump({"dir": d, "proms": [r.__dict__ for r in rows]}, sys.stdout, indent=2)
        print()
        return
    say(f"Sun boot PROMs in {d}:")
    for r in rows:
        mark = {"ok": "ok", "mismatch": "MISMATCH", "missing": "missing", "unknown": "unknown"}[r.state]
        say(f"  {r.name:<16} {r.machine:<6} {mark:<9}{(' ' + r.source) if r.source else ''}")
        if r.state in ("mismatch", "unknown"):
            say(f"  {'':<16} {'':<6} {'':<9} sha256 {r.sha256}, {r.size} bytes")


def cmd_status(args, manifest):
    d = os.path.abspath(args.dir)
    print_rows(survey(manifest, d, State(args.state)), d, args.json)
    return EXIT_OK


def cmd_verify(args, manifest):
    d = os.path.abspath(args.dir)
    rows = survey(manifest, d, State(args.state))
    print_rows(rows, d, args.json)
    for n in args.names:
        if n not in manifest.by_name:
            raise Error(f"{n} is not in the manifest")
    required = set(args.names) or ({p.name for p in manifest.proms} if args.all else set())
    rc = EXIT_OK
    present = 0
    for r in rows:
        if r.state == "missing":
            if r.name in required:
                warn(f"{r.name}: missing")
                rc = EXIT_FAIL
            continue
        if args.names and r.name not in required:
            continue
        present += 1
        if r.state == "mismatch":
            warn(f"{r.name}: sha256 {r.sha256} isn't the manifest's {manifest.by_name[r.name].sha256}")
            rc = EXIT_FAIL
        elif r.state == "unknown":
            warn(f"{r.name}: not in the manifest")
            rc = EXIT_FAIL
    if present == 0 and rc == EXIT_OK:
        warn(f"no known Sun PROM in {d}")
        rc = EXIT_FAIL
    return rc


def cmd_remove(args, manifest):
    d = os.path.abspath(args.dir)
    state = State(args.state)
    names = args.names or [p.name for p in manifest.proms] + [r.name for r in state.in_dir(d) if r.name not in manifest.by_name]
    rc = EXIT_OK
    for name in names:
        if not valid_name(name):
            raise Error(f"not a file name: {name!r}")
        path = os.path.join(d, name)
        rec = state.get(d, name)
        if name not in manifest.by_name and not rec:
            # never a file of the directory that is neither a known PROM nor installed by this tool
            raise Error(f"{name} is neither in the manifest nor installed by wsh-sun-proms")
        if not os.path.isfile(path):
            if rec:
                state.drop(d, name)
            if args.names:
                say(f"  {name:<16} not there")
            continue
        owner = dpkg_owner(path)
        if owner:
            say(f"  {name:<16} kept: it belongs to package {owner} (apt removes it with the package)")
            if args.names:
                rc = EXIT_FAIL
            continue
        sha = sha256_file(path)
        if not (rec and rec.sha256 == sha) and not args.force:
            why = "changed since wsh-sun-proms installed it" if rec else "not installed by wsh-sun-proms"
            warn(f"kept {path}: {why}; --force removes it")
            rc = EXIT_FAIL
            continue
        if args.dry_run:
            say(f"  {name:<16} would remove")
            continue
        try:
            os.unlink(path)
        except PermissionError as e:
            raise Error(f"can't remove {path}: {e.strerror} (run as root)") from e
        state.drop(d, name)
        say(f"  {name:<16} removed")
    if not args.dry_run:
        try:
            state.save()
        except PermissionError as e:
            raise Error(f"can't write {args.state}: {e.strerror} (run as root)") from e
    return rc


def parser():
    prog = os.environ.get("WSH_SUN_PROMS_PROG", "wsh-sun-proms")
    p = argparse.ArgumentParser(
        prog=prog,
        description="Install Sun boot PROM images you are entitled to use, from a source you provide, "
        "into the directory QEMU reads, checked against a manifest of known images.",
        epilog=f"Examples: {prog} install --source /path/to/proms | {prog} install --source "
        "git@example.org:you/proms.git | {prog} status | {prog} verify --all".replace("{prog}", prog),
    )
    p.add_argument("--version", action="store_true", help="print the version and exit")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=os.environ.get("WSH_SUN_PROMS_DIR", DEFAULT_DIR),
                        help=f"where the PROMs go (default {DEFAULT_DIR}, where QEMU looks; $WSH_SUN_PROMS_DIR)")
    common.add_argument("--manifest", default=os.environ.get("WSH_SUN_PROMS_MANIFEST", DEFAULT_MANIFEST),
                        help="the manifest of known PROMs ($WSH_SUN_PROMS_MANIFEST)")
    common.add_argument("--state", default=os.environ.get("WSH_SUN_PROMS_STATE", DEFAULT_STATE),
                        help=f"the record of what this tool installed (default {DEFAULT_STATE})")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    i = sub.add_parser("install", parents=[common], help="install the known PROMs found in a source")
    i.add_argument("names", nargs="*", metavar="NAME", help="only these PROMs (default: every known one in the source)")
    i.add_argument("--source", "-s", required=True,
                   help="a directory, a tar/zip archive, a git repository URL or an HTTPS base or archive URL")
    i.add_argument("--type", choices=["dir", "archive", "git", "http"], help="the kind of source, when its form doesn't say")
    i.add_argument("--ref", help="git: the branch or tag to clone (default: the remote's HEAD)")
    i.add_argument("--force", action="store_true", help="install unknown or differing files, replace a different file")
    i.add_argument("--dry-run", "-n", action="store_true", help="show what would be installed, change nothing")

    s = sub.add_parser("status", parents=[common], help="which known PROMs are there, whether they match, and from where")
    s.add_argument("--json", action="store_true", help="as JSON")

    v = sub.add_parser("verify", parents=[common], help="exit 1 unless the PROMs there match the manifest")
    v.add_argument("names", nargs="*", metavar="NAME", help="these must be there and match")
    v.add_argument("--all", action="store_true", help="every known PROM must be there and match")
    v.add_argument("--json", action="store_true", help="as JSON")

    r = sub.add_parser("remove", parents=[common], help="remove the PROMs this tool installed")
    r.add_argument("names", nargs="*", metavar="NAME", help="only these (default: every known one)")
    r.add_argument("--force", action="store_true", help="also remove files this tool didn't install (never a package's)")
    r.add_argument("--dry-run", "-n", action="store_true", help="show what would be removed, change nothing")
    return p


def version():
    v = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "VERSION")
    try:
        with open(v, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.version:
        say(version())
        return EXIT_OK
    if not args.command:
        p.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        manifest = load_manifest(args.manifest)
        return {"install": cmd_install, "status": cmd_status, "verify": cmd_verify, "remove": cmd_remove}[args.command](
            args, manifest
        )
    except Error as e:
        warn(str(e))
        return EXIT_FAIL
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
