#!/usr/bin/env python3
"""Pick the recordings the docs embed out of a matrix run and name them as the `media` release has them.

    publish_media.py <runs dir> <out dir>

<runs dir> is a matrix.py / pve_matrix.py output (or the downloaded `sparc-lab-<matrix>` artifact).
For each curated case that is in it and passed, the cast is time-compressed for viewing (recording.py,
the limits below) and the video copied, into <out dir>; then `gh release upload media <out dir>/*
--clobber` replaces those assets, and the docs site serves them as /recordings/ from its next deploy
(repo-update.yml). Prints what it wrote; writes nothing for a run without curated cases.

The paths are the case directories the matrices write, so one runs directory can hold several runs
(`--runs` is the same for each; their case directories don't overlap). The gallery's recordings come
from these, all in the PVE test container (pve.Dockerfile):

  pve_matrix.py pve                           sol26-install-ss5, netbsd-sparc64, alpine-aarch64
  pve_matrix.py install --disks <stored disks> boot-tests: tribblix-m34-sun4u, sol10-sun4u, sol9-sun4u
  pve_matrix.py install --disks <empty dir>   installs (install, then the --check boot of the same
                                              run): netbsd111-sparc, sunos413u1b-ss5, freedos14,
                                              openbsd59-ss5, redhat62-ss5
  lab.py install <target> --check --out <runs>/install-<target>/1-install-<target>
                                              the same layout for one target: sol21-ss10, openbsd80-sun4u,
                                              sunos413-ss10, sunos412-ss600mp
  pve_matrix.py recordings                    sol26-ss20-smp4, sol22-install-ss10
  lab.py install debian40-ss5 --check --gateway G --dns D --out <runs>/debian40-ss5/1-install-debian40-ss5
                                              (a route out: pve_matrix.py passes none)
  matrix.py machines, display                 sol26-disk-openbios-ss20, sol26-disk-openbios-cg3-1024x768

A matrix run that has only some of them (the `sparc lab` workflow's publish_media) replaces only those.
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
    # install: boot-tests of the stored disks (their installs take hours)
    ("install-tribblix-m34-sun4u/1-boot-test-tribblix-m34-sun4u/check", "tribblix-m34-boot-sun4u.cast", 1, 2),
    ("install-sol10-sun4u/1-boot-test-sol10-sun4u/check", "sol10-boot-sun4u.cast", 1, 1),
    ("install-sol9-sun4u/1-boot-test-sol9-sun4u/check", "sol9-boot-sun4u.cast", 1, 1),
    # install: installs into an empty --disks, each with the --check boot of the same run
    ("install-netbsd111-sparc/1-install-netbsd111-sparc/install", "netbsd111-install-ss5.cast", 1, 2),
    ("install-netbsd111-sparc/1-install-netbsd111-sparc/check", "netbsd111-boot-ss5.cast", 1, 1),
    ("install-sunos413u1b-ss5/1-install-sunos413u1b-ss5/install", "sunos413-install-ss5.cast", 1, 1),
    ("install-sunos413u1b-ss5/1-install-sunos413u1b-ss5/check", "sunos413-boot-ss5.cast", 1, 1),
    ("install-sunos413-ss10/1-install-sunos413-ss10/install", "sunos413-install-ss10.cast", 1, 1),
    ("install-sunos413-ss10/1-install-sunos413-ss10/check", "sunos413-boot-ss10.cast", 1, 1),
    ("install-sunos412-ss600mp/1-install-sunos412-ss600mp/install", "sunos412-install-ss600mp.cast", 1, 1),
    ("install-sunos412-ss600mp/1-install-sunos412-ss600mp/check", "sunos412-boot-ss600mp.cast", 1, 1),
    ("install-openbsd59-ss5/1-install-openbsd59-ss5/install", "openbsd59-install-ss5.cast", 1, 2),
    ("install-openbsd59-ss5/1-install-openbsd59-ss5/check", "openbsd59-boot-ss5.cast", 1, 1),
    ("install-redhat62-ss5/1-install-redhat62-ss5/install", "redhat62-install-ss5.cast", 1, 1),
    ("install-redhat62-ss5/1-install-redhat62-ss5/check", "redhat62-boot-ss5.cast", 1, 1),
    ("install-sol21-ss10/1-install-sol21-ss10/install", "sol21-install-ss10.cast", 1, 2),
    ("install-sol21-ss10/1-install-sol21-ss10/check", "sol21-boot-ss10.cast", 1, 1),
    ("install-openbsd80-sun4u/1-install-openbsd80-sun4u/install", "openbsd80-install-sun4u.cast", 1, 3),
    ("install-openbsd80-sun4u/1-install-openbsd80-sun4u/check", "openbsd80-boot-sun4u.cast", 1, 2),
    # lab.py install debian40-ss5 --check (with a route out)
    ("debian40-ss5/1-install-debian40-ss5/install", "debian40-install-ss5.cast", 1, 4),
    ("debian40-ss5/1-install-debian40-ss5/check", "debian40-boot-ss5.cast", 1, 1),
    # recordings
    ("sol26-ss20-smp4/1-solaris-boot-disk", "sol26-smp4-ss20.cast", 1, 1),
    ("sol22-install-ss10/1-solaris-install-serial", "sol22-install-ss10.cast", 1, 2),
    ("sol22-install-ss10/2-solaris-boot-disk", "sol22-boot-ss10.cast", 1, 1),
]
# videos: case -> asset base name (fb.webm, fb.vtt and the first step's screenshot as the poster)
VIDEOS = [
    ("sol26-disk-openbios-cg3-1024x768", "sol26-cg3-ss5"),  # display
    ("install-freedos14/1-install-freedos14/install", "freedos14-install"),  # install (VGA)
    ("install-freedos14/1-install-freedos14/check", "freedos14-boot"),
]


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
