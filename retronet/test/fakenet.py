#!/usr/bin/env python3
"""The upstream stub on the test's fake internet: answers as web.archive.org for the few URLs the
archive cache's miss path is tested with (the 1999 web itself comes from the synthetic dataset in
the cache's store). Counts every request (GET /_stats) so the test can tell a store hit from an
upstream fetch. http://busy.example.com/ answers its first lookup with 429 and Retry-After: 2.
"""

import collections
import http.server
import json
import sys
import threading
import urllib.parse

TS = "19990605120000"
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00"
       b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def page(name):
    return (f'<html><head><title>{name}</title></head><body><h1>{name}</h1>'
            f'<p>STUB-ONLINE-1999 {name}</p>'
            f'<img src="/web/{TS}im_/http://{name}/{name.split(".")[0]}.gif">'
            f'<a href="/web/{TS}/http://{name}/more.html">more</a></body></html>').encode()


CAPTURES = {}
for host in ("stub.example.com", "warm.example.com", "busy.example.com"):
    CAPTURES[f"http://{host}/"] = ("text/html", page(host))
    CAPTURES[f"http://{host}/{host.split('.')[0]}.gif"] = ("image/gif", GIF)

counts = collections.Counter()
lock = threading.Lock()
busy_once = {"done": False}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "fake-wayback/2"

    def log_message(self, fmt, *args):
        sys.stdout.write("fakenet: %s %s\n" % (self.client_address[0], fmt % args))
        sys.stdout.flush()

    def send(self, code, body, ctype="text/plain", headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/_stats":
            with lock:
                return self.send(200, json.dumps(counts).encode(), "application/json")
        if url.path == "/cdx/search/cdx":
            q = urllib.parse.parse_qs(url.query)
            original, year = q.get("url", [""])[0], q.get("from", [""])[0]
            with lock:
                counts["cdx " + original] += 1
                if original == "http://busy.example.com/" and not busy_once["done"]:
                    busy_once["done"] = True
                    return self.send(429, b"slow down\n", headers=[("Retry-After", "2")])
            if year == "1999" and original in CAPTURES:
                mime, body = CAPTURES[original]
                return self.send(200, f"{original} {TS} {mime} {len(body)}\n".encode())
            return self.send(200, b"")
        if url.path.startswith(f"/web/{TS}"):
            rest = self.path.split("/", 3)[3]
            with lock:
                counts["web " + rest] += 1
            if rest in CAPTURES:
                mime, body = CAPTURES[rest]
                return self.send(200, body, mime)
        with lock:
            counts["other " + self.path] += 1
        self.send(404, b"not archived\n")


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
