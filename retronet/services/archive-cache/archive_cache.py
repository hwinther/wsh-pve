#!/usr/bin/env python3
"""The retro net's archive cache: a persistent, inspectable store of Wayback Machine answers that
VintageHive uses as its archive endpoint (its "worker" setting), with an offline replay mode, a
warm-up command and export/import of the store. Standard library only.

It speaks the protocol VintageHive's archive worker speaks, which is web.archive.org's own:

    GET /cdx/search/cdx?url=<url>&from=<year>&to=<year>&fl=original,timestamp,mimetype,length
    GET /web/<timestamp><flag>/<original url>          (flag: if_ for pages, im_ images, oe_ media)

Store layout (version 1), under --root:

    v1/<kind>/<host>/<sha256 of the key, 32 hex>.json   what was asked, status, type, when, from where
    v1/<kind>/<host>/<same>.body                        the response body exactly as archive.org sent it

kind is "cdx" or "web"; host is the host of the archived URL. A body's modification time is its
last use (least recently used entries go first when the store is over its size limit).

Commands: serve, stats, warm, export, import, purge, put-capture (see --help).
"""

import argparse
import datetime
import hashlib
import html.parser
import http.server
import io
import json
import os
import re
import shutil
import socketserver
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1"
USER_AGENT = "retronet-archive-cache/1 (+https://github.com/hwinther/wsh-pve; retro net gateway cache)"
CDX_FL = "original,timestamp,mimetype,length"
NEGATIVE_DAYS = 30
NAME_RE = re.compile(r"^[0-9a-f]{32}\.(json|body)$")
HOST_RE = re.compile(r"^[a-z0-9._-]{1,253}$")


def log(*args):
    print("archive-cache:", *args, file=sys.stderr, flush=True)


# --- keys ------------------------------------------------------------------------------------------

def host_of(url):
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    return host if HOST_RE.match(host) and host.strip(".") else "_"


def cdx_key(url, year_from, year_to, fl):
    return f"cdx|{url}|{year_from}|{year_to}|{fl}"


def web_key(rest):
    """rest: '<timestamp><flag>/<original url>' as it follows /web/ in the request path."""
    return f"web|{rest}"


def type_code(mimetype):
    """VintageHive's GetArchiveTypeCode: the flag it asks the archive for, by capture type."""
    m = mimetype or ""
    if m.startswith("image"):
        return "im_"
    if m.startswith("audio") or m.startswith("video") or "application/x-stuffit" in m or "application/zip" in m:
        return "oe_"
    return "if_"


# --- store -----------------------------------------------------------------------------------------

class Store:
    def __init__(self, root, max_bytes=0):
        self.root = os.path.abspath(root)
        self.base = os.path.join(self.root, "v" + VERSION)
        self.max_bytes = max_bytes
        self.lock = threading.Lock()
        os.makedirs(self.base, exist_ok=True)
        self.size = self._measure()
        self.last_sweep = 0.0

    def _paths(self, kind, host, key):
        name = hashlib.sha256(key.encode("utf-8", "surrogateescape")).hexdigest()[:32]
        d = os.path.join(self.base, kind, host)
        return d, os.path.join(d, name + ".json"), os.path.join(d, name + ".body")

    def _measure(self):
        total = 0
        for dirpath, _, files in os.walk(self.base):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        return total

    def get(self, kind, host, key):
        _, meta_path, body_path = self._paths(kind, host, key)
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("key") != key:
                return None, None  # hash collision on 128 bits: treat as a miss
            with open(body_path, "rb") as f:
                body = f.read()
        except (OSError, ValueError):
            return None, None
        try:
            os.utime(body_path)  # last use, for eviction
        except OSError:
            pass
        return meta, body

    def put(self, kind, host, key, meta, body):
        d, meta_path, body_path = self._paths(kind, host, key)
        os.makedirs(d, exist_ok=True)
        meta = dict(meta, key=key, kind=kind, host=host, size=len(body))
        old = sum(os.path.getsize(p) for p in (meta_path, body_path) if os.path.exists(p))
        for path, data in ((body_path, body), (meta_path, json.dumps(meta, indent=1, sort_keys=True).encode())):
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        with self.lock:
            self.size += os.path.getsize(meta_path) + os.path.getsize(body_path) - old
        self.maybe_evict()

    def maybe_evict(self):
        if not self.max_bytes or self.size <= self.max_bytes or time.time() - self.last_sweep < 30:
            return
        with self.lock:
            self.last_sweep = time.time()
            entries = []
            for dirpath, _, files in os.walk(self.base):
                for f in files:
                    if f.endswith(".body"):
                        p = os.path.join(dirpath, f)
                        try:
                            entries.append((os.path.getmtime(p), p))
                        except OSError:
                            pass
            entries.sort()
            target = int(self.max_bytes * 0.9)
            removed = 0
            for _, body in entries:
                if self.size <= target:
                    break
                for p in (body, body[:-5] + ".json"):
                    try:
                        self.size -= os.path.getsize(p)
                        os.remove(p)
                    except OSError:
                        pass
                removed += 1
            log(f"evicted {removed} entries; store now {self.size // 1048576} MB")

    def stats(self):
        out = {"root": self.root, "bytes": 0, "cdx": 0, "web": 0, "negative": 0, "hosts": 0}
        hosts = set()
        for kind in ("cdx", "web"):
            kd = os.path.join(self.base, kind)
            if not os.path.isdir(kd):
                continue
            for host in os.listdir(kd):
                hosts.add(host)
                for f in os.listdir(os.path.join(kd, host)):
                    p = os.path.join(kd, host, f)
                    out["bytes"] += os.path.getsize(p)
                    if f.endswith(".json"):
                        out[kind] += 1
                        try:
                            with open(p, encoding="utf-8") as fh:
                                if json.load(fh).get("negative"):
                                    out["negative"] += 1
                        except (OSError, ValueError):
                            pass
        out["hosts"] = len(hosts)
        return out


# --- upstream --------------------------------------------------------------------------------------

class Upstream:
    """Serialised, rate-limited fetches from web.archive.org (or a relay that speaks its protocol)."""

    def __init__(self, base, min_interval):
        self.base = base.rstrip("/")
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last = 0.0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.requests = 0
        # web.archive.org answers too many requests by refusing connections from the address for a
        # while; back off instead of knocking: 1 minute after the first refusal, doubling to an hour
        self.blocked_until = 0.0
        self.backoff = 0.0

    def fetch(self, path_and_query):
        """Returns (status, content_type, body); status 0 when the archive could not be reached.
        Called with self.lock held."""
        url = self.base + path_and_query
        if time.time() < self.blocked_until:
            return -1, "", b""
        for attempt in (1, 2):
            wait = self.last + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            self.requests += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with self.opener.open(req, timeout=60) as r:
                    self.backoff = 0.0
                    return r.status, r.headers.get("Content-Type", ""), r.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt == 1:
                    retry = e.headers.get("Retry-After", "5")
                    delay = min(int(retry) if retry.isdigit() else 5, 15)
                    log(f"upstream said {e.code}; waiting {delay} s before one retry: {path_and_query}")
                    self.last = time.time() + delay - self.min_interval
                    continue
                return e.code, e.headers.get("Content-Type", ""), e.read()
            except (urllib.error.URLError, OSError) as e:
                reason = getattr(e, "reason", e)
                if isinstance(reason, ConnectionRefusedError):
                    self.backoff = min(max(self.backoff * 2, 60.0), 3600.0)
                    self.blocked_until = time.time() + self.backoff
                    log(f"upstream refused the connection (rate limit?); no upstream requests for {int(self.backoff)} s")
                    return -1, "", b""
                else:
                    log(f"upstream unreachable: {e}: {path_and_query}")
                return 0, "", b""
        return 503, "", b""


# --- server ----------------------------------------------------------------------------------------

class Cache:
    def __init__(self, store, upstream, mode):
        self.store = store
        self.upstream = upstream
        self.mode = mode
        self.hits = self.misses = 0

    def answer(self, kind, host, key, path_and_query):
        meta, body = self.store.get(kind, host, key)
        fresh = meta is not None and not (
            meta.get("negative") and self.mode == "online"
            and time.time() - meta.get("fetched_epoch", 0) > NEGATIVE_DAYS * 86400)
        if fresh:
            self.hits += 1
            return meta["status"], meta.get("content_type", ""), body, "hit"
        if self.mode != "online":
            self.misses += 1
            # a miss in replay mode looks like "not archived" to VintageHive
            return (200, "text/plain", b"", "offline-miss") if kind == "cdx" else (404, "text/plain", b"not in the archive cache\n", "offline-miss")
        with self.upstream.lock:
            meta, body = self.store.get(kind, host, key)  # filled while we waited?
            if meta is not None and not meta.get("negative"):
                self.hits += 1
                return meta["status"], meta.get("content_type", ""), body, "hit"
            self.misses += 1
            status, ctype, body = self.upstream.fetch(path_and_query)
        negative = (kind == "cdx" and status == 200 and not body.strip()) or (kind == "web" and status == 404)
        if status == 200 or negative:
            now = time.time()
            self.store.put(kind, host, key, {
                "request": path_and_query, "status": status, "content_type": ctype, "negative": negative,
                "fetched": datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat(timespec="seconds"),
                "fetched_epoch": int(now), "upstream": self.upstream.base}, body)
            return status, ctype, body, "stored"
        if status == -1:
            return 503, "text/plain", b"the archive refuses connections for now; try again later\n", "backing-off"
        if status == 0:
            return 502, "text/plain", b"the archive could not be reached\n", "error"
        if status in (429, 503):
            return 503, "text/html", b"<html><body><h1>The archive is busy</h1><p>Try again in a minute.</p></body></html>", "busy"
        return status, ctype, body, "passed"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "retronet-archive-cache/1"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def send(self, status, ctype, body, headers=()):
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        cache = self.server.cache
        split = urllib.parse.urlsplit(self.path)
        if split.path == "/cdx/search/cdx":
            q = urllib.parse.parse_qs(split.query)
            url = q.get("url", [""])[0]
            yf, yt, fl = q.get("from", [""])[0], q.get("to", [""])[0], q.get("fl", [CDX_FL])[0]
            if not url:
                return self.send(400, "text/plain", b"url missing\n")
            upstream_q = urllib.parse.urlencode({"url": url, "from": yf, "to": yt, "fl": fl})
            status, ctype, body, how = cache.answer("cdx", host_of(url), cdx_key(url, yf, yt, fl), "/cdx/search/cdx?" + upstream_q)
        elif self.path.startswith("/web/") and "/" in self.path[5:]:
            rest = self.path[5:]
            status, ctype, body, how = cache.answer("web", host_of(rest.split("/", 1)[1]), web_key(rest), self.path)
        elif split.path == "/_stats":
            st = dict(cache.store.stats(), mode=cache.mode, hits=cache.hits, misses=cache.misses,
                      upstream_requests=cache.upstream.requests)
            return self.send(200, "application/json", json.dumps(st).encode())
        else:
            return self.send(404, "text/plain", b"not found\n")
        log(f"{how} {status} {self.path[:200]}")
        extra = ()
        if how == "backing-off":
            extra = (("Retry-After", str(max(1, int(cache.upstream.blocked_until - time.time())))),)
        self.send(status, ctype, body, extra)

    do_HEAD = do_GET


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def cmd_serve(a):
    store = Store(a.root, a.max_mb * 1048576)
    cache = Cache(store, Upstream(a.upstream, a.min_interval), a.mode)
    srv = Server((a.listen, a.port), Handler)
    srv.cache = cache
    log(f"serving {a.listen}:{a.port}, mode {a.mode}, upstream {a.upstream}, store {store.root} "
        f"({store.size // 1048576} MB of {a.max_mb or 'unlimited'} MB)")
    srv.serve_forever()


# --- client side: warm-up --------------------------------------------------------------------------

class Requisites(html.parser.HTMLParser):
    """Archive-relative links of page requisites (images, frames, backgrounds, embeds)."""
    ATTRS = {"img": "src", "frame": "src", "iframe": "src", "embed": "src", "input": "src",
             "body": "background", "td": "background", "table": "background"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []

    def handle_starttag(self, tag, attrs):
        want = self.ATTRS.get(tag)
        for k, v in attrs:
            if k == want and v:
                m = re.match(r"^(?:https?:)?(?://web\.archive\.org)?/web/(\d{14}[a-z]{0,2}_?/.+)$", v.strip())
                if m:
                    self.found.append(m.group(1))


def normalise(url):
    """The form VintageHive asks for (.NET Uri.ToString()): lower-case scheme and host, '/' path."""
    if "://" not in url:
        url = "http://" + url
    s = urllib.parse.urlsplit(url)
    netloc = s.hostname.lower() if s.hostname else ""
    if s.port and s.port != 80:
        netloc += f":{s.port}"
    return urllib.parse.urlunsplit((s.scheme.lower(), netloc, s.path or "/", s.query, ""))


def http_get(server, path, max_wait=0):
    """GET from the cache. With max_wait, a 503 with Retry-After (the cache backing off from
    archive.org) is waited out, up to max_wait seconds in all."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + max_wait
    while True:
        req = urllib.request.Request(server + path, headers={"User-Agent": "retronet-warm/1"})
        try:
            with opener.open(req, timeout=180) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            retry = e.headers.get("Retry-After", "")
            if e.code == 503 and retry.isdigit() and time.time() + int(retry) < deadline:
                print(f"waiting       {int(retry)} s: the archive refuses connections for now", flush=True)
                time.sleep(int(retry) + 1)
                continue
            return e.code, e.headers.get("Content-Type", ""), e.read()


def cmd_warm(a):
    urls = list(a.urls)
    files = a.file or ([a.default_list] if not urls and a.default_list else [])
    for f in files:
        with open(f, encoding="utf-8") as fh:
            urls += [l.split("#")[0].strip() for l in fh if l.split("#")[0].strip()]
    year = str(a.year)
    totals = {"pages": 0, "archived": 0, "requisites": 0, "requisites_ok": 0, "bytes": 0}
    started = time.time()
    for raw in urls:
        url = normalise(raw)
        totals["pages"] += 1
        q = urllib.parse.urlencode({"url": url, "from": year, "to": year, "fl": CDX_FL})
        status, _, body = http_get(a.server, "/cdx/search/cdx?" + q, a.max_wait)
        lines = [l.split() for l in body.decode("utf-8", "replace").splitlines() if len(l.split()) == 4]
        if status != 200:
            totals["errors"] = totals.get("errors", 0) + 1
            print(f"error         {url}  (lookup answered {status}; try again later)", flush=True)
            continue
        if not lines:
            print(f"not archived  {url}", flush=True)
            continue
        # VintageHive's choice: the largest capture of the year (first of equals)
        best = max(lines, key=lambda p: int(p[3]) if p[3].isdigit() else 0)
        rest = f"{best[1]}{type_code(best[2])}/{best[0]}"
        status, ctype, page = http_get(a.server, "/web/" + rest, a.max_wait)
        if status != 200:
            print(f"failed        {url}  ({status} for {rest})", flush=True)
            continue
        totals["archived"] += 1
        totals["bytes"] += len(page)
        req_ok = req_n = 0
        if a.requisites and ctype.startswith("text/html"):
            p = Requisites()
            try:
                p.feed(page.decode("latin-1"))
            except Exception:  # noqa: BLE001 - a broken 1999 page must not stop the run
                pass
            for r in list(dict.fromkeys(p.found))[:a.max_requisites]:
                req_n += 1
                s, _, b = http_get(a.server, "/web/" + r, a.max_wait)
                if s == 200:
                    req_ok += 1
                    totals["bytes"] += len(b)
            totals["requisites"] += req_n
            totals["requisites_ok"] += req_ok
        print(f"archived      {url}  {best[1]}  {len(page)} B" + (f"  requisites {req_ok}/{req_n}" if a.requisites else ""), flush=True)
        if a.delay:
            time.sleep(a.delay)
    totals["seconds"] = int(time.time() - started)
    print("summary " + json.dumps(totals), flush=True)


# --- export, import, purge, put-capture ------------------------------------------------------------

def cmd_export(a):
    store = Store(a.root)
    out = sys.stdout.buffer if a.file == "-" else open(a.file, "wb")
    with tarfile.open(fileobj=out, mode="w|gz") as tar:
        tar.add(store.base, arcname="v" + VERSION)
    if out is not sys.stdout.buffer:
        out.close()


def cmd_import(a):
    store = Store(a.root)
    src = sys.stdin.buffer if a.file == "-" else open(a.file, "rb")
    added = skipped = refused = 0
    with tarfile.open(fileobj=src, mode="r|gz") as tar:
        for m in tar:
            parts = m.name.split("/")
            if m.isdir():
                continue
            if not (m.isfile() and len(parts) == 4 and parts[0] == "v" + VERSION and parts[1] in ("cdx", "web")
                    and HOST_RE.match(parts[2]) and parts[2].strip(".") and NAME_RE.match(parts[3])):
                refused += 1
                continue
            dest = os.path.join(store.base, parts[1], parts[2], parts[3])
            if os.path.exists(dest) and not a.overwrite:
                skipped += 1
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with tar.extractfile(m) as f, open(dest + ".tmp", "wb") as o:
                shutil.copyfileobj(f, o)
            os.replace(dest + ".tmp", dest)
            added += 1
    print(json.dumps({"added": added, "skipped": skipped, "refused": refused}))


def cmd_purge(a):
    if not a.yes:
        sys.exit("purge removes every stored answer; add --yes")
    store = Store(a.root)
    shutil.rmtree(store.base)
    os.makedirs(store.base)
    print("purged " + store.base)


def cmd_put_capture(a):
    """Add a capture by hand (used to build the synthetic test dataset)."""
    store = Store(a.root)
    url = normalise(a.url)
    with open(a.body, "rb") as f:
        body = f.read()
    when = a.fetched or "1999-12-31T00:00:00+00:00"
    common = {"status": 200, "negative": False, "fetched": when, "fetched_epoch": 0, "upstream": "synthetic"}
    line = f"{url} {a.timestamp} {a.mimetype} {len(body)}\n".encode()
    q = urllib.parse.urlencode({"url": url, "from": a.year, "to": a.year, "fl": CDX_FL})
    store.put("cdx", host_of(url), cdx_key(url, str(a.year), str(a.year), CDX_FL),
              dict(common, request="/cdx/search/cdx?" + q, content_type="text/plain"), line)
    rest = f"{a.timestamp}{type_code(a.mimetype)}/{url}"
    store.put("web", host_of(url), web_key(rest), dict(common, request="/web/" + rest, content_type=a.content_type or a.mimetype), body)
    print("/web/" + rest)


def cmd_stats(a):
    if a.server:
        status, _, body = http_get(a.server, "/_stats")
        print(body.decode())
    else:
        print(json.dumps(Store(a.root).stats()))


def main():
    root_default = os.environ.get("RETRONET_ARCHIVE_ROOT", "/var/lib/retronet/archive-cache")
    server_default = os.environ.get("RETRONET_ARCHIVE_SERVER", "http://127.0.0.1:8890")
    ap = argparse.ArgumentParser(prog="retronet-archive", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=root_default, help="store directory (default %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the cache")
    s.add_argument("--listen", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8890)
    s.add_argument("--mode", choices=("online", "offline"), default="online",
                   help="online: store, and fetch on a miss; offline: replay the store only")
    s.add_argument("--upstream", default="https://web.archive.org")
    s.add_argument("--min-interval", type=float, default=5.0, help="seconds between upstream requests")
    s.add_argument("--max-mb", type=int, default=0, help="evict least recently used above this (0: no limit)")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("warm", help="fetch URLs (and their images and frames) through the running cache")
    s.add_argument("urls", nargs="*")
    s.add_argument("-f", "--file", action="append", help="file with one URL per line (# comments)")
    s.add_argument("--year", default=os.environ.get("RETRONET_YEAR", "1999"))
    s.add_argument("--requisites", action="store_true", help="also fetch each page's images and frames")
    s.add_argument("--max-requisites", type=int, default=20)
    s.add_argument("--delay", type=float, default=0.0, help="extra seconds between pages")
    s.add_argument("--max-wait", type=int, default=3600,
                   help="seconds to wait out the archive refusing connections before a URL counts as an error")
    s.add_argument("--server", default=server_default)
    s.add_argument("--default-list", help="list to warm when no URL and no --file is given")
    s.set_defaults(func=cmd_warm)

    s = sub.add_parser("export", help="write the store as a .tar.gz (- for stdout)")
    s.add_argument("file")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("import", help="add a .tar.gz made by export (- for stdin)")
    s.add_argument("file")
    s.add_argument("--overwrite", action="store_true")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("purge", help="remove every stored answer")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_purge)

    s = sub.add_parser("stats", help="entries, size; with --server also hits and misses")
    s.add_argument("--server", nargs="?", const=server_default)
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("put-capture", help="store a capture by hand: its CDX line and its body")
    s.add_argument("url")
    s.add_argument("year")
    s.add_argument("timestamp")
    s.add_argument("mimetype")
    s.add_argument("body")
    s.add_argument("--content-type")
    s.add_argument("--fetched")
    s.set_defaults(func=cmd_put_capture)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
