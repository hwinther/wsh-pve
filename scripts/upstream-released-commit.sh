#!/bin/bash
# Prints the commit of submodules/<name> that Proxmox has published as a package: the newest
# commit on the submodule's upstream branch whose debian/changelog starts with the version that
# Proxmox's apt repository has (the newest of the suites below; by default pve-no-subscription only). The nightly sync moves the
# submodule to that commit instead of the branch tip, so main builds on released code, never on
# commits whose dependencies aren't published yet.
#
# Run from the repository root; the submodule must be checked out (any commit).
#
# Usage: scripts/upstream-released-commit.sh <submodule>
# Env:   UPSTREAM_REF     the branch to search (default: origin/master, fetched first)
#        PROXMOX_DISTS    apt dists URL (default: http://download.proxmox.com/debian/pve/dists/trixie)
#        PROXMOX_SUITES   suites to read (default: "pve-no-subscription"). Not pve-test by default:
#                         a pve-test release can depend on packages only pve-test has, and then
#                         our build of it doesn't install next to no-subscription.
# Output: the commit on stdout; what it found on stderr.
# Exit:  0 found; 1 not found (no published version, or no commit with exactly that version);
#        2 usage error
set -euo pipefail

name=${1:-}
[ -n "$name" ] && [ -d "submodules/$name" ] || { echo "usage: $0 <submodule>" >&2; exit 2; }
sub="submodules/$name"
case "$name" in
    pve-storage) pkg=libpve-storage-perl ;;
    pve-qemu) pkg=pve-qemu-kvm ;;
    *) pkg="$name" ;;
esac
dists=${PROXMOX_DISTS:-http://download.proxmox.com/debian/pve/dists/trixie}
suites=${PROXMOX_SUITES:-"pve-no-subscription"}
ref=${UPSTREAM_REF:-origin/master}

newer() { dpkg --compare-versions "$1" gt "$2"; }

published=""
for suite in $suites; do
    v=""
    while read -r x; do
        if [ -z "$v" ] || newer "$x" "$v"; then v=$x; fi
    done < <(curl -fsSL "$dists/$suite/binary-amd64/Packages.gz" 2>/dev/null | gunzip 2>/dev/null |
             awk -v p="$pkg" '/^Package: /{c=($2==p)} c&&/^Version: /{print $2}')
    echo "$pkg in $suite: ${v:-none}" >&2
    if [ -n "$v" ] && { [ -z "$published" ] || newer "$v" "$published"; }; then
        published=$v
    fi
done
[ -n "$published" ] || { echo "no published version of $pkg" >&2; exit 1; }

if [ "$ref" = origin/master ]; then
    git -C "$sub" fetch -q origin master
fi

# Commits that touched debian/changelog, newest first: the first whose top entry is the
# published version is the release (its "bump version to ..." commit). Later commits with the
# same version are unreleased work after it.
while read -r commit; do
    v=$(git -C "$sub" show "$commit:debian/changelog" 2>/dev/null | sed -n '1s/^[^(]*(\([^)]*\)).*/\1/p')
    [ -n "$v" ] || continue
    if [ "$v" = "$published" ]; then
        echo "$pkg $published is $(git -C "$sub" log -1 --format='%h %s (%cs)' "$commit")" >&2
        echo "$commit"
        exit 0
    fi
    if newer "$published" "$v"; then
        break # older than the published version: the release commit isn't on this branch
    fi
done < <(git -C "$sub" log --format=%H "$ref" -- debian/changelog)

echo "no commit on $ref has $pkg $published in debian/changelog" >&2
exit 1
