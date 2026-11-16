#!/usr/bin/env python3
"""Fetch the bench disk's sources (and gcc for the build disk), check them against the pinned sha256
sums and write the hand-over CD the Solaris guest reads them from (ISO 9660 + Rock Ridge, hsfs).

    python3 -I handover.py <download dir> <out.iso>

Downloads go to <download dir> (kept: a second run only checks them). Everything fetched is untrusted
third-party content: it is only checked, gunzipped (Solaris 2.6 has no gzip) and put on the CD, never
run here. The CD holds:

    /gcc/   the gcc package stream (pkgadd -d), for setting up the build disk
    /src/   the sources as downloaded, and the .tar files gunzipped from them
    /bench/ build.sh (run in the guest), run.sh and README from this directory, SOURCES (URLs, sha256)

Needs genisoimage (in the lab image).
"""
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SF = "https://archive.org/download/sunfreeware_20120304/sunfreeware-20120304.tar/sunfreeware-20120304%2Fsparc%2F2.6%2F"
UB = "https://raw.githubusercontent.com/kdlucas/byte-unixbench/c7ea5d492b1f82d4ccd270fee27863425e436235/UnixBench/src/"
# (directory on the CD, file name, URL, sha256)
FILES = [
    ("gcc", "gcc-2.95.3-sol26-sparc-local.gz", SF + "gcc-2.95.3-sol26-sparc-local.gz",
     "e463df88e87f7a5c77bce3b849a9cff0bc6e9415c02a8234707bfa2f86e802a8"),
    ("src", "dhry-c", "https://www.netlib.org/benchmark/dhry-c",
     "038a7e9169787125c3451a6c941f3aca5db2d2f3863871afcdce154ef17f4e3e"),
    ("src", "whetstone.c", "https://www.netlib.org/benchmark/whetstone.c",
     "333e4ceca042c146f63eec605573d16ae8b07166cbc44a17bec1ea97c6f1efbf"),
    ("src", "nbench-byte-2.2.3.tar.gz", "https://www.math.utah.edu/~mayer/linux/nbench-byte-2.2.3.tar.gz",
     "723dd073f80e9969639eb577d2af4b540fc29716b6eafdac488d8f5aed9101ac"),
    # BYTE UNIX Benchmarks' Towers of Hanoi (recursive: deeper than the register windows), UnixBench 5.1.3
    ("src", "hanoi.c", UB + "hanoi.c", "d43d265a4dbcd834b2294f6b63c86dd30df00379eef0df6e66ac00e8961e4129"),
    ("src", "timeit.c", UB + "timeit.c", "45fe6c98f93fbf517d717f8d8ff30ff0684e93b891b8a5e1bcbddbe783d1bc43"),
    ("src", "lmbench-3.0-a9.tgz",
     "https://downloads.sourceforge.net/project/lmbench/development/lmbench-3.0-a9/lmbench-3.0-a9.tgz",
     "cbd5777d15f44eab7666dcac418054c3c09df99826961a397d9acf43d8a2a551"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(dl, name, url, want):
    path = os.path.join(dl, name)
    if not os.path.exists(path):
        print(f"fetching {url}", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "sparc-lab-handover"})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.rename(path + ".part", path)
    got = sha256(path)
    if got != want:
        raise SystemExit(f"{path}: sha256 {got}, expected {want} (delete it to fetch again)")
    return path


def gunzip(src, dst):
    with gzip.open(src, "rb") as f, open(dst, "wb") as o:
        shutil.copyfileobj(f, o)


def main():
    dl, iso = sys.argv[1], sys.argv[2]
    os.makedirs(dl, exist_ok=True)
    with tempfile.TemporaryDirectory() as root:
        lines = []
        for sub, name, url, want in FILES:
            path = fetch(dl, name, url, want)
            d = os.path.join(root, sub)
            os.makedirs(d, exist_ok=True)
            if sub == "gcc":  # the package stream, gunzipped: pkgadd -d reads it directly
                gunzip(path, os.path.join(d, name[:-3]))
            else:
                shutil.copy(path, d)
                if name.endswith(".tar.gz"):
                    gunzip(path, os.path.join(d, name[:-3]))
                elif name.endswith(".tgz"):
                    gunzip(path, os.path.join(d, name[:-4] + ".tar"))
            lines.append(f"{name}\n  {url}\n  sha256 {want}\n")
        b = os.path.join(root, "bench")
        os.makedirs(b)
        for f in ("build.sh", "run.sh", "lmbench.sh", "nbench.cfg", "compat251.c", "README"):
            shutil.copy(os.path.join(HERE, f), b)
        with open(os.path.join(b, "SOURCES"), "w", encoding="ascii") as f:
            f.write("Downloaded files (sha256 of the file as fetched)\n\n" + "\n".join(lines))
        subprocess.run(["genisoimage", "-quiet", "-r", "-V", "BENCH_HANDOVER", "-o", iso, root], check=True)
    print(f"{iso}: {os.path.getsize(iso) >> 20} MiB, sha256 {sha256(iso)}")


if __name__ == "__main__":
    main()
