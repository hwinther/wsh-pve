#!/usr/bin/env python3
"""A stand-in for the Wayback Machine on the test's fake internet: the CDX search API and the
archived copies of a small 1999 fixture for http://www.example.com/. Captures exist only for 1999,
so a page that arrives proves the gateway asked for the configured year. Every request is logged.
"""

import http.server
import sys
import urllib.parse
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixture")
TS = "19990117083513"
CAPTURES = {  # original URL -> (mimetype, file)
    "http://www.example.com/": ("text/html", "index.html"),
    "http://www.example.com/logo.gif": ("image/gif", "logo.gif"),
}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "fake-wayback/1"

    def log_message(self, fmt, *args):
        sys.stdout.write("fakenet: %s %s\n" % (self.client_address[0], fmt % args))
        sys.stdout.flush()

    def send(self, code, body, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/cdx/search/cdx":
            q = urllib.parse.parse_qs(url.query)
            original = q.get("url", [""])[0]
            year = q.get("from", [""])[0]
            sys.stdout.write(f"fakenet: CDX url={original} year={year}\n")
            if year == "1999" and original in CAPTURES:
                mime, name = CAPTURES[original]
                size = (FIXTURE / name).stat().st_size
                return self.send(200, f"{original} {TS} {mime} {size}\n".encode())
            return self.send(200, b"")
        if url.path.startswith(f"/web/{TS}"):
            # /web/<ts><flag>/<original>
            rest = self.path.split("/", 3)[3]
            if rest in CAPTURES:
                mime, name = CAPTURES[rest]
                return self.send(200, (FIXTURE / name).read_bytes(), mime)
        self.send(404, b"not archived\n")


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
