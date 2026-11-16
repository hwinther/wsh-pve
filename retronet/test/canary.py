#!/usr/bin/env python3
"""A "LAN" host for the isolation tests: answers HTTP on ports 80 and 8080 with a marker and logs
every connection to /tmp/hits. Any hit that is not the test's own control means isolation failed."""

import socketserver
import sys
import threading

MARKER = b"CANARY-LAN-SECRET"


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(3)
        try:
            first = self.rfile.readline(512).decode("latin-1").strip()
        except OSError:
            first = ""
        line = f"HIT {self.client_address[0]} port {self.server.server_address[1]} {first!r}\n"
        with open("/tmp/hits", "a") as f:
            f.write(line)
        sys.stdout.write("canary: " + line)
        sys.stdout.flush()
        body = MARKER + b"\n"
        self.wfile.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    open("/tmp/hits", "w").close()
    for port in (80, 8080):
        threading.Thread(target=Server(("0.0.0.0", port), Handler).serve_forever, daemon=True).start()
    threading.Event().wait()
