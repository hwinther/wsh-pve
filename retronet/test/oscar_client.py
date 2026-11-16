#!/usr/bin/env python3
"""A minimal OSCAR client for the retro net test: FLAP/SNAC framing, the MD5 sign-on (auth key
request, hashed password, BOS redirect with a cookie) and one instant message between two sessions.

    oscar_client.py <server> <user1> <pass1> <user2> <pass2>

Exit 0 when user1 and user2 sign on, user2 receives user1's message, and a wrong password is
refused. Written from the protocol, not from any client software.
"""

import hashlib
import os
import socket
import struct
import sys
import time

MD5_SUFFIX = b"AOL Instant Messenger (SM)"  # the constant the protocol's MD5 sign-on hashes with
TIMEOUT = 10


class Conn:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=TIMEOUT)
        self.seq = 0x1000
        self.req = 1

    def close(self):
        self.sock.close()

    def _read_exact(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("connection closed")
            data += chunk
        return data

    def read_flap(self):
        hdr = self._read_exact(6)
        if hdr[0] != 0x2A:
            raise ValueError(f"not a FLAP: {hdr!r}")
        channel, _seq, length = hdr[1], *struct.unpack(">HH", hdr[2:6])
        return channel, self._read_exact(length)

    def send_flap(self, channel, data):
        self.seq = (self.seq + 1) & 0xFFFF
        self.sock.sendall(struct.pack(">BBHH", 0x2A, channel, self.seq, len(data)) + data)

    def send_snac(self, family, subtype, data=b""):
        self.req += 1
        self.send_flap(2, struct.pack(">HHHI", family, subtype, 0, self.req) + data)

    def read_snac(self, want=None, deadline=None):
        """Next SNAC (family, subtype, data); with want=(family, subtype), skip others until it arrives."""
        deadline = deadline or time.time() + TIMEOUT
        while time.time() < deadline:
            channel, data = self.read_flap()
            if channel == 4:
                raise ConnectionError("server signed us off")
            if channel != 2 or len(data) < 10:
                continue
            family, subtype = struct.unpack(">HH", data[:4])
            if want is None or (family, subtype) == want:
                return family, subtype, data[10:]
        raise TimeoutError(f"no SNAC {want}")


def tlv(t, value):
    if isinstance(value, str):
        value = value.encode("ascii")
    return struct.pack(">HH", t, len(value)) + value


def parse_tlvs(data):
    out, i = {}, 0
    while i + 4 <= len(data):
        t, n = struct.unpack(">HH", data[i:i + 4])
        out[t] = data[i + 4:i + 4 + n]
        i += 4 + n
    return out


def sign_on(host, user, password):
    """MD5 sign-on at the authorizer; returns the BOS connection, or raises PermissionError."""
    auth = Conn(host, 5190)
    channel, hello = auth.read_flap()
    assert channel == 1 and hello == b"\0\0\0\1", f"unexpected hello {channel} {hello!r}"
    auth.send_flap(1, b"\0\0\0\1")
    auth.send_snac(0x17, 0x06, tlv(0x01, user))
    _, _, data = auth.read_snac((0x17, 0x07))
    keylen = struct.unpack(">H", data[:2])[0]
    key = data[2:2 + keylen]
    digest = hashlib.md5(key + password.encode("ascii") + MD5_SUFFIX).digest()
    auth.send_snac(0x17, 0x02, tlv(0x01, user) + tlv(0x25, digest) + tlv(0x03, "retronet-test"))
    _, _, data = auth.read_snac((0x17, 0x03))
    tlvs = parse_tlvs(data)
    auth.close()
    if 0x08 in tlvs or 0x06 not in tlvs:
        raise PermissionError(f"sign-on refused for {user}: {tlvs!r}")
    bos_host, bos_port = tlvs[0x05].decode().rsplit(":", 1)
    cookie = tlvs[0x06]

    bos = Conn(bos_host, int(bos_port))
    channel, hello = bos.read_flap()
    assert channel == 1, f"unexpected BOS hello channel {channel}"
    bos.send_flap(1, b"\0\0\0\1" + tlv(0x06, cookie))
    bos.read_snac((0x01, 0x03))  # host online: the families the server offers
    # client ready: (family, version, tool id, tool version) for the families used here
    ready = b"".join(struct.pack(">HHHH", f, 1, 0x0110, 0x047B) for f in (0x01, 0x02, 0x03, 0x04))
    bos.send_snac(0x01, 0x02, ready)
    return bos, bos_host, int(bos_port)


def send_im(conn, to, text):
    frags = b"\x05\x01" + struct.pack(">H", 1) + b"\x01"  # features fragment
    body = struct.pack(">HH", 0, 0) + text.encode("ascii")
    frags += b"\x01\x01" + struct.pack(">H", len(body)) + body
    payload = os.urandom(8) + struct.pack(">H", 1) + bytes([len(to)]) + to.encode("ascii") + tlv(0x02, frags)
    conn.send_snac(0x04, 0x06, payload)


def main():
    host, u1, p1, u2, p2 = sys.argv[1:6]
    failures = 0

    try:
        sign_on(host, u1, p1 + "x")
        print(f"not ok - a wrong password for {u1} was accepted")
        failures += 1
    except PermissionError:
        print(f"ok - a wrong password for {u1} is refused")

    a, bos_host, bos_port = sign_on(host, u1, p1)
    print(f"ok - {u1} signed on (MD5), BOS at {bos_host}:{bos_port}")
    b, _, _ = sign_on(host, u2, p2)
    print(f"ok - {u2} signed on (MD5)")
    time.sleep(1.5)  # let the server drop the two authorizer connections

    text = f"hello from {u1} at {int(time.time())}"
    send_im(a, u2, text)
    try:
        _, _, data = b.read_snac((0x04, 0x07))
        if text.encode() in data and u1.encode() in data:
            print(f"ok - {u2} received the message from {u1}")
        else:
            print(f"not ok - {u2} got an ICBM without the text: {data!r}")
            failures += 1
    except (TimeoutError, socket.timeout) as e:
        print(f"not ok - {u2} received nothing: {e}")
        failures += 1

    a.send_flap(4, b"")
    b.send_flap(4, b"")
    a.close()
    b.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
