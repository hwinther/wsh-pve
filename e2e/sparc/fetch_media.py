#!/usr/bin/env python3
"""Download pinned media of targets.MEDIA (those with a "url", such as the NetBSD CDs) and check them.

    python3 fetch_media.py DIR NAME [NAME ...]

Each NAME ends up as DIR/NAME: kept when it is already the pinned medium (its size, sha256 and, where
pinned, sha512), downloaded from its "url" otherwise (through NAME.part, so an interrupted download is
never taken for the medium). Exit 1 when a medium doesn't match after the download, 2 for a name that
targets.MEDIA doesn't have or has no URL for.

tests/test_netbsd.py takes its CD from here, and the workflows run it before the Actions cache is
saved (sparc-lab-netbsd.yml, media-cache.yml), so the cache only ever holds checked media. Standard
library only: it runs on a GitHub-hosted runner without the lab image.
"""
import hashlib
import os
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import targets  # noqa: E402


def digests(path):
    """(sha256, sha512) of the file, in one read."""
    h256, h512 = hashlib.sha256(), hashlib.sha512()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h256.update(block)
            h512.update(block)
    return h256.hexdigest(), h512.hexdigest()


def tested(path, med):
    """Whether `path` is the medium of targets.MEDIA: its size, sha256 and (where pinned) sha512."""
    if not os.path.exists(path) or os.path.getsize(path) != med["size"]:
        return False
    h256, h512 = digests(path)
    return h256 == med["sha256"] and med.get("sha512", h512) == h512


def fetch(name, directory, attempts=3):
    """DIR/NAME, the pinned medium `name`: downloaded when it isn't there or isn't the pinned one.
    Raises RuntimeError when the file still doesn't match afterwards."""
    med = targets.MEDIA[name]
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    if not tested(path, med):
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(med["url"], timeout=600) as r, open(path + ".part", "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
                os.replace(path + ".part", path)
                break
            except OSError as e:
                if attempt == attempts:
                    raise
                print(f"{name}: download failed ({e}), again in {10 * attempt} s", file=sys.stderr, flush=True)
                time.sleep(10 * attempt)
    if not tested(path, med):
        raise RuntimeError(f"{path}: not the tested {name} (size {med['size']}, sha256 {med['sha256']},"
                           f" sha512 {med.get('sha512', '-')})")
    return path


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    directory, names = argv[0], argv[1:]
    for name in names:
        if not targets.MEDIA.get(name, {}).get("url"):
            print(f"fetch_media: {name}: not a downloadable medium of targets.MEDIA", file=sys.stderr)
            return 2
    for name in names:
        try:
            path = fetch(name, directory)
        except RuntimeError as e:
            print(f"fetch_media: {e}", file=sys.stderr)
            return 1
        print(f"{path}: {targets.MEDIA[name]['size']} bytes, sha256 {targets.MEDIA[name]['sha256']}: ok", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
