#!/usr/bin/env bash
# Adds the +wsh entry to debian/changelog in the current directory (a package's source tree), with
# one line per change: the entries of scripts/wsh-changelog-entries.sh, which the caller computes on
# the host (the build image has dch but the repository's history is outside its mounts) and passes
# in WSH_CHANGELOG_ENTRIES, one per line. The first goes in with `dch -l +wsh` (the version), the
# others with `dch -a`. Run in the build image (ghcr.io/hwinther/wsh-pve/pve-build) by build-deb.yml
# and by the Makefile's pve-qemu and pve-qemu-3dfx targets, so both pve-qemu trees get the same
# version and the same entries. DEBEMAIL and DEBFULLNAME name the maintainer, as for dch.
#
# Usage: WSH_CHANGELOG_ENTRIES="$(scripts/wsh-changelog-entries.sh <package>)" \
#            scripts/wsh-changelog-dch.sh <distribution>
# Exit:  0 done; 2 usage error (no distribution or no entries); dch's status if it fails
set -euo pipefail

dist=${1:-}
[ -n "$dist" ] || { echo "usage: WSH_CHANGELOG_ENTRIES=... $0 <distribution>" >&2; exit 2; }

first=1
while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    if [ "$first" = 1 ]; then
        dch -l +wsh -D "$dist" -- "$entry"
        first=0
    else
        dch -a -- "$entry"
    fi
done <<< "${WSH_CHANGELOG_ENTRIES:-}"

if [ "$first" = 1 ]; then
    echo "$0: WSH_CHANGELOG_ENTRIES has no entries" >&2
    exit 2
fi
