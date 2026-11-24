#!/usr/bin/env python3
"""Download pinned media and check them: those of targets.MEDIA with a "url" (such as the NetBSD CDs) and
the FreeDOS 1.4 Floppy Edition zip (targets_dos.FREEDOS_ZIP, by its file name FD14-FloppyEdition.zip).

    python3 fetch_media.py DIR NAME [NAME ...]
    python3 fetch_media.py --key NAME

Each NAME ends up as DIR/NAME: kept when it is already the pinned medium (its size, sha256 and, where
pinned, sha512), downloaded from its "url" otherwise (through NAME.part, so an interrupted download is
never taken for the medium). Exit 1 when a medium doesn't match after the download, 2 for a name that
has no pin with a URL. --key prints the Actions cache key of NAME: its "cache" name (or NAME) and the
first 16 hex digits of its sha256, so a new pin is a new entry.

tests/test_netbsd.py and tests/test_freedos.py take their media from here, so do the 3dfx DOS test and
the audio matrix (their images carry this file and targets_dos.py), and the workflows run it before the
Actions cache is saved (sparc-lab-netbsd.yml, sparc-lab-dos.yml, 3dfx-dos.yml, audio-matrix.yml,
media-cache.yml), so the cache only ever holds checked media. Standard library only: it runs on a
GitHub-hosted runner without the lab image. targets.py is imported only for a name that isn't the
FreeDOS zip, so the FreeDOS users need only this file and targets_dos.py.
"""
import hashlib
import os
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import targets_dos  # noqa: E402

FREEDOS_ZIP_NAME = os.path.basename(targets_dos.FREEDOS_ZIP["url"])


def medium(name):
    """The pin of `name` (url, size, sha256, maybe sha512 and cache), or None."""
    if name == FREEDOS_ZIP_NAME:
        return targets_dos.FREEDOS_ZIP
    import targets  # noqa: E402  (the whole catalogue; not in the images that only need FreeDOS)
    return targets.MEDIA.get(name)


def cache_key(name):
    med = medium(name)
    return f"{med.get('cache', name)}-{med['sha256'][:16]}"


def digests(path):
    """(sha256, sha512) of the file, in one read."""
    h256, h512 = hashlib.sha256(), hashlib.sha512()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h256.update(block)
            h512.update(block)
    return h256.hexdigest(), h512.hexdigest()


def tested(path, med):
    """Whether `path` is the pinned medium `med`: its size, sha256 and (where pinned) sha512."""
    if not os.path.exists(path) or os.path.getsize(path) != med["size"]:
        return False
    h256, h512 = digests(path)
    return h256 == med["sha256"] and med.get("sha512", h512) == h512


def mismatch(path, name, med):
    return RuntimeError(f"{path}: not the tested {name} (size {med['size']}, sha256 {med['sha256']},"
                        f" sha512 {med.get('sha512', '-')})")


def checked(path, name):
    """`path`, a copy of the medium `name` given by the caller (never downloaded over); RuntimeError
    when it isn't the pinned one."""
    med = medium(name)
    if not tested(path, med):
        raise mismatch(path, name, med)
    return path


def fetch(name, directory, attempts=3):
    """DIR/NAME, the pinned medium `name`: downloaded when it isn't there or isn't the pinned one.
    Raises RuntimeError when the file still doesn't match afterwards."""
    med = medium(name)
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
        raise mismatch(path, name, med)
    return path


def downloadable(name):
    return bool((medium(name) or {}).get("url"))


def main(argv):
    if len(argv) == 2 and argv[0] == "--key":
        if not downloadable(argv[1]):
            print(f"fetch_media: {argv[1]}: not a downloadable pinned medium", file=sys.stderr)
            return 2
        print(cache_key(argv[1]))
        return 0
    if len(argv) < 2 or argv[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    directory, names = argv[0], argv[1:]
    for name in names:
        if not downloadable(name):
            print(f"fetch_media: {name}: not a downloadable pinned medium", file=sys.stderr)
            return 2
    for name in names:
        try:
            path = fetch(name, directory)
        except RuntimeError as e:
            print(f"fetch_media: {e}", file=sys.stderr)
            return 1
        med = medium(name)
        print(f"{path}: {med['size']} bytes, sha256 {med['sha256']}: ok", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
