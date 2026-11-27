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
                                              sunos413-ss10, sunos412-ss600mp, reactos0416
  pve_matrix.py recordings                    sol26-ss20-smp4, sol22-install-ss10
  lab.py install <target> --check [--gateway G --dns D] --out <runs>/install-<target>/1-install-<target>
                                              the 2026-11-26 sweep (published packages, two at a time):
                                              sol23/sol24/sol25/sol251/sol7 on SS-5 and SS-20, sol26-ss10,
                                              sol7-ss10, sol251/sol26/sol7-sun4u, sunos414-ss5,
                                              sunos413u1b-ss20, netbsd111-sparc64, netbsd111-sparc-ss20,
                                              netbsd93-sparc64, netbsd93-sparc, netbsd93-sparc-ss20,
                                              openbsd59-ss20, freebsd124-sun4u, redhat62-ss20,
                                              debian40-ss20 (a route out), debian7-sun4u
                                              and last the Web Start installs: sol8-ss5, sol8-ss5-prom,
                                              sol8-ss20, sol9-ss5, sol9-ss20, sol8-sun4u
  lab.py install <target> --check --out <runs>/install-<target>/1-install-<target>
                                              the 2026-11-27 SS-600MP runs (published packages, one at a
                                              time, ss600mp.bin in /usr/share/kvm): sunos412-ss600mp-prom,
                                              sol21/sol22/sol23/sol24/sol25/sol251-ss600mp-prom
  lab.py install debian40-ss5 --check --gateway G --dns D --out <runs>/debian40-ss5/1-install-debian40-ss5
                                              (a route out: pve_matrix.py passes none)
  matrix.py machines, display                 sol26-disk-openbios-ss20, sol26-disk-openbios-cg3-1024x768

One asset isn't made here: sunos412-cg3-single-user-ss600mp.webm, .vtt and -poster.png are the
fb-bell.py run (GUEST=sunos4 MACHINE=SS-600MP VGA=cg3) on the stored sunos412-ss600mp disk in the lab's
own QEMU, 2026-11-22 (e2e/sparc/README.md, "Older Sun releases: Solaris 2.1-2.5, SunOS
4.1.2-4.1.3_U1B"), uploaded by hand.

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
    # lab.py install <target> --check into the install matrix's layout (the 2026-11-26 sweep; Debian with a
    # route out)
    ("install-sol23-ss5/1-install-sol23-ss5/install", "sol23-install-ss5.cast", 1, 2),
    ("install-sol23-ss5/1-install-sol23-ss5/check", "sol23-boot-ss5.cast", 1, 1),
    ("install-sol23-ss20/1-install-sol23-ss20/install", "sol23-install-ss20.cast", 1, 2),
    ("install-sol23-ss20/1-install-sol23-ss20/check", "sol23-boot-ss20.cast", 1, 1),
    ("install-sol24-ss5/1-install-sol24-ss5/install", "sol24-install-ss5.cast", 1, 2),
    ("install-sol24-ss5/1-install-sol24-ss5/check", "sol24-boot-ss5.cast", 1, 1),
    ("install-sol24-ss20/1-install-sol24-ss20/install", "sol24-install-ss20.cast", 1, 2),
    ("install-sol24-ss20/1-install-sol24-ss20/check", "sol24-boot-ss20.cast", 1, 1),
    ("install-sol25-ss5/1-install-sol25-ss5/install", "sol25-install-ss5.cast", 1, 2),
    ("install-sol25-ss5/1-install-sol25-ss5/check", "sol25-boot-ss5.cast", 1, 1),
    ("install-sol25-ss20/1-install-sol25-ss20/install", "sol25-install-ss20.cast", 1, 2),
    ("install-sol25-ss20/1-install-sol25-ss20/check", "sol25-boot-ss20.cast", 1, 1),
    ("install-sol251-ss5/1-install-sol251-ss5/install", "sol251-install-ss5.cast", 1, 4),
    ("install-sol251-ss5/1-install-sol251-ss5/check", "sol251-boot-ss5.cast", 1, 1),
    ("install-sol251-ss20/1-install-sol251-ss20/install", "sol251-install-ss20.cast", 1, 4),
    ("install-sol251-ss20/1-install-sol251-ss20/check", "sol251-boot-ss20.cast", 1, 1),
    ("install-sol26-ss10/1-install-sol26-ss10/install", "sol26-install-ss10.cast", 1, 2),
    ("install-sol26-ss10/1-install-sol26-ss10/check", "sol26-boot-ss10.cast", 1, 1),
    ("install-sol7-ss5/1-install-sol7-ss5/install", "sol7-install-ss5.cast", 1, 2),
    ("install-sol7-ss5/1-install-sol7-ss5/check", "sol7-boot-ss5.cast", 1, 1),
    ("install-sol7-ss20/1-install-sol7-ss20/install", "sol7-install-ss20.cast", 1, 2),
    ("install-sol7-ss20/1-install-sol7-ss20/check", "sol7-boot-ss20.cast", 1, 1),
    ("install-sol7-ss10/1-install-sol7-ss10/install", "sol7-install-ss10.cast", 1, 2),
    ("install-sol7-ss10/1-install-sol7-ss10/check", "sol7-boot-ss10.cast", 1, 1),
    ("install-sol251-sun4u/1-install-sol251-sun4u/install", "sol251-install-sun4u.cast", 1, 6),
    ("install-sol251-sun4u/1-install-sol251-sun4u/check", "sol251-boot-sun4u.cast", 1, 2),
    ("install-sol26-sun4u/1-install-sol26-sun4u/install", "sol26-install-sun4u.cast", 1, 3),
    ("install-sol26-sun4u/1-install-sol26-sun4u/check", "sol26-boot-sun4u.cast", 1, 2),
    ("install-sol7-sun4u/1-install-sol7-sun4u/install", "sol7-install-sun4u.cast", 1, 3),
    ("install-sol7-sun4u/1-install-sol7-sun4u/check", "sol7-boot-sun4u.cast", 1, 2),
    ("install-sunos414-ss5/1-install-sunos414-ss5/install", "sunos414-install-ss5.cast", 1, 1),
    ("install-sunos414-ss5/1-install-sunos414-ss5/check", "sunos414-boot-ss5.cast", 1, 1),
    ("install-sunos413u1b-ss20/1-install-sunos413u1b-ss20/install", "sunos413u1b-install-ss20.cast", 1, 1),
    ("install-sunos413u1b-ss20/1-install-sunos413u1b-ss20/check", "sunos413u1b-boot-ss20.cast", 1, 1),
    ("install-netbsd111-sparc64/1-install-netbsd111-sparc64/install", "netbsd111-install-sun4u.cast", 1, 2),
    ("install-netbsd111-sparc64/1-install-netbsd111-sparc64/check", "netbsd111-boot-sun4u.cast", 1, 1),
    ("install-netbsd111-sparc-ss20/1-install-netbsd111-sparc-ss20/install", "netbsd111-install-ss20.cast", 1, 2),
    ("install-netbsd111-sparc-ss20/1-install-netbsd111-sparc-ss20/check", "netbsd111-boot-ss20.cast", 1, 1),
    ("install-netbsd93-sparc64/1-install-netbsd93-sparc64/install", "netbsd93-install-sun4u.cast", 1, 4),
    ("install-netbsd93-sparc64/1-install-netbsd93-sparc64/check", "netbsd93-boot-sun4u.cast", 1, 1),
    ("install-netbsd93-sparc/1-install-netbsd93-sparc/install", "netbsd93-install-ss5.cast", 1, 2),
    ("install-netbsd93-sparc/1-install-netbsd93-sparc/check", "netbsd93-boot-ss5.cast", 1, 1),
    ("install-netbsd93-sparc-ss20/1-install-netbsd93-sparc-ss20/install", "netbsd93-install-ss20.cast", 1, 2),
    ("install-netbsd93-sparc-ss20/1-install-netbsd93-sparc-ss20/check", "netbsd93-boot-ss20.cast", 1, 1),
    ("install-openbsd59-ss20/1-install-openbsd59-ss20/install", "openbsd59-install-ss20.cast", 1, 2),
    ("install-openbsd59-ss20/1-install-openbsd59-ss20/check", "openbsd59-boot-ss20.cast", 1, 1),
    ("install-freebsd124-sun4u/1-install-freebsd124-sun4u/install", "freebsd124-install-sun4u.cast", 1, 2),
    ("install-freebsd124-sun4u/1-install-freebsd124-sun4u/check", "freebsd124-boot-sun4u.cast", 1, 2),
    ("install-redhat62-ss20/1-install-redhat62-ss20/install", "redhat62-install-ss20.cast", 1, 1),
    ("install-redhat62-ss20/1-install-redhat62-ss20/check", "redhat62-boot-ss20.cast", 1, 1),
    ("install-debian40-ss20/1-install-debian40-ss20/install", "debian40-install-ss20.cast", 1, 4),
    ("install-debian40-ss20/1-install-debian40-ss20/check", "debian40-boot-ss20.cast", 1, 1),
    ("install-debian7-sun4u/1-install-debian7-sun4u/install", "debian7-install-sun4u.cast", 1, 4),
    ("install-debian7-sun4u/1-install-debian7-sun4u/check", "debian7-boot-sun4u.cast", 1, 2),
    # the same sweep's Web Start installs (Solaris 8 and 9), run after the others
    ("install-sol8-ss5/1-install-sol8-ss5/install", "sol8-install-ss5.cast", 1, 2),
    ("install-sol8-ss5/1-install-sol8-ss5/check", "sol8-boot-ss5.cast", 1, 1),
    ("install-sol8-ss5-prom/1-install-sol8-ss5-prom/install", "sol8-install-ss5-prom.cast", 1, 2),
    ("install-sol8-ss5-prom/1-install-sol8-ss5-prom/check", "sol8-boot-ss5-prom.cast", 1, 1),
    ("install-sol8-ss20/1-install-sol8-ss20/install", "sol8-install-ss20.cast", 1, 2),
    ("install-sol8-ss20/1-install-sol8-ss20/check", "sol8-boot-ss20.cast", 1, 1),
    ("install-sol9-ss5/1-install-sol9-ss5/install", "sol9-install-ss5.cast", 1, 2),
    ("install-sol9-ss5/1-install-sol9-ss5/check", "sol9-boot-ss5.cast", 1, 1),
    ("install-sol9-ss20/1-install-sol9-ss20/install", "sol9-install-ss20.cast", 1, 2),
    ("install-sol9-ss20/1-install-sol9-ss20/check", "sol9-boot-ss20.cast", 1, 1),
    ("install-sol8-sun4u/1-install-sol8-sun4u/install", "sol8-install-sun4u.cast", 1, 3),
    ("install-sol8-sun4u/1-install-sol8-sun4u/check", "sol8-boot-sun4u.cast", 1, 2),
    # lab.py install <target> --check, the SS-600MP under its own PROM (ss600mp.bin), 2026-11-27
    ("install-sunos412-ss600mp-prom/1-install-sunos412-ss600mp-prom/install",
     "sunos412-install-ss600mp-prom.cast", 1, 1),
    ("install-sunos412-ss600mp-prom/1-install-sunos412-ss600mp-prom/check",
     "sunos412-boot-ss600mp-prom.cast", 1, 1),
    ("install-sol21-ss600mp-prom/1-install-sol21-ss600mp-prom/install", "sol21-install-ss600mp-prom.cast", 1, 2),
    ("install-sol21-ss600mp-prom/1-install-sol21-ss600mp-prom/check", "sol21-boot-ss600mp-prom.cast", 1, 1),
    ("install-sol22-ss600mp-prom/1-install-sol22-ss600mp-prom/install", "sol22-install-ss600mp-prom.cast", 1, 2),
    ("install-sol22-ss600mp-prom/1-install-sol22-ss600mp-prom/check", "sol22-boot-ss600mp-prom.cast", 1, 1),
    ("install-sol23-ss600mp-prom/1-install-sol23-ss600mp-prom/install", "sol23-install-ss600mp-prom.cast", 1, 2),
    ("install-sol23-ss600mp-prom/1-install-sol23-ss600mp-prom/check", "sol23-boot-ss600mp-prom.cast", 1, 1),
    ("install-sol24-ss600mp-prom/1-install-sol24-ss600mp-prom/install", "sol24-install-ss600mp-prom.cast", 1, 2),
    ("install-sol24-ss600mp-prom/1-install-sol24-ss600mp-prom/check", "sol24-boot-ss600mp-prom.cast", 1, 1),
    ("install-sol25-ss600mp-prom/1-install-sol25-ss600mp-prom/install", "sol25-install-ss600mp-prom.cast", 1, 2),
    ("install-sol25-ss600mp-prom/1-install-sol25-ss600mp-prom/check", "sol25-boot-ss600mp-prom.cast", 1, 1),
    ("install-sol251-ss600mp-prom/1-install-sol251-ss600mp-prom/install", "sol251-install-ss600mp-prom.cast", 1, 4),
    ("install-sol251-ss600mp-prom/1-install-sol251-ss600mp-prom/check", "sol251-boot-ss600mp-prom.cast", 1, 1),
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
    # lab.py install reactos0416 --check --out <runs>/install-reactos0416/1-install-reactos0416
    ("install-reactos0416/1-install-reactos0416/install", "reactos0416-install"),  # install (VGA, then GUI)
    ("install-reactos0416/1-install-reactos0416/check", "reactos0416-boot"),
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
