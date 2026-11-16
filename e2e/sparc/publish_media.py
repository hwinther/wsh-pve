#!/usr/bin/env python3
"""Pick the recordings the docs embed out of a matrix run and name them as the `media` release has them.

    publish_media.py <runs dir> <out dir>

<runs dir> is a matrix.py / pve_matrix.py output (or the downloaded `sparc-lab-<matrix>` artifact).
For each curated case that is in it and passed, the cast is time-compressed for viewing (recording.py,
the limits below) and the video copied, into <out dir>; then `gh release upload media <out dir>/*
--clobber` replaces those assets, and the docs site serves them as /recordings/ from its next deploy
(repo-update.yml). Prints what it wrote; writes nothing for a run without curated cases.
"""
import json
import os
import shutil
import sys

import recording

# case directory (relative to the runs dir) -> asset; casts: (name, max idle s, speed)
CASTS = [
    ("sol26-install-ss5/1-install-sol26-ss5/install", "sol26-install-ss5.cast", 1, 3),  # pve: lab.py install
    ("netbsd-sparc64/1-netbsd-boot-cd", "netbsd-sparc64-pve.cast", 1, 1),  # pve
    ("alpine-aarch64/1-alpine-boot-cd", "alpine-aarch64-pve.cast", 1, 1),  # pve
    ("sol26-disk-openbios-ss20", "sol26-boot-ss20.cast", 1, 1),  # machines
]
# videos: case -> asset base name (fb.webm, fb.vtt and the first step's screenshot as the poster)
VIDEOS = [("sol26-disk-openbios-cg3-1024x768", "sol26-cg3-ss5")]  # display


def passed(case):
    try:
        with open(os.path.join(case, "result.json"), encoding="utf-8") as f:
            return json.load(f).get("code") == 0
    except (OSError, ValueError):
        return False


def main(runs, out):
    os.makedirs(out, exist_ok=True)
    wrote = []
    for rel, name, max_idle, speed in CASTS:
        case = os.path.join(runs, rel)
        if passed(case) and os.path.exists(os.path.join(case, "serial.cast")):
            c = recording.compress_cast(os.path.join(case, "serial.cast"), os.path.join(out, name), max_idle, speed)
            wrote.append(f"{name}: {c['seconds']:.0f}s -> {c['fast_seconds']:.0f}s")
    for rel, base in VIDEOS:
        case = os.path.join(runs, rel)
        if passed(case) and os.path.exists(os.path.join(case, "fb.webm")):
            for src, ext in (("fb.webm", ".webm"), ("fb.vtt", ".vtt"), ("001-fb.png", "-poster.png")):
                if os.path.exists(os.path.join(case, src)):
                    shutil.copy(os.path.join(case, src), os.path.join(out, base + ext))
                    wrote.append(base + ext)
    print("\n".join(wrote) or f"no curated recordings in {runs}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
