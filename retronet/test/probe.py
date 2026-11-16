#!/usr/bin/env python3
"""probe.py <host> <port> [payload]: connect, send the payload (backslash escapes such as \\r\\n are
decoded), print what comes back. The first line is CONNECTED <ms>, REFUSED <ms> or TIMEOUT <ms>."""
import socket
import sys
import time

host, port = sys.argv[1], int(sys.argv[2])
payload = sys.argv[3].encode().decode("unicode_escape").encode("latin-1") if len(sys.argv) > 3 else b""
t = time.time()
try:
    s = socket.create_connection((host, port), timeout=4)
except ConnectionRefusedError:
    print(f"REFUSED {int((time.time() - t) * 1000)}")
    sys.exit(0)
except OSError as e:
    print(f"TIMEOUT {int((time.time() - t) * 1000)} {e}")
    sys.exit(0)
print(f"CONNECTED {int((time.time() - t) * 1000)}")
s.settimeout(8)
if payload:
    s.sendall(payload)
data = b""
try:
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
        if not payload:
            break  # a banner is enough
except OSError:
    pass
sys.stdout.write(data.decode("latin-1"))
