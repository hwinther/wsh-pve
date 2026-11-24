#!/usr/bin/env bash
# Prints the debian/changelog entries of the next +wsh build of a package, one per line, oldest
# first: the subjects of the commits since the previous wsh build of that package that changed what
# goes into it. scripts/wsh-changelog-dch.sh writes them into debian/changelog (build-deb.yml and the
# Makefile's pve-qemu and pve-qemu-3dfx targets), and build-deb.yml lists them in the release notes.
#
# The previous build is the newest commit that touched submodules/<package>.changelog.patch (each
# build commits "Update changelog for <package> (<version>)"). The commits after it count when they
# touch the package's inputs, the paths of build-deb-trigger-patches.yml plus the submodule pointer:
#   pve-qemu     submodules/pve-qemu.patch, submodules/pve-qemu-qemu-3dfx.patch, submodules/qemu-3dfx,
#                submodules/qemu-3dfx.patch, openbios/, submodules/pve-qemu
#   pve-manager, qemu-server, pve-storage
#                submodules/<package>.patch, submodules/<package>
# - Merge commits and "Update changelog for ..." commits are left out.
# - The nightly upstream sync's "Update submodule <package>" commit is written as
#   "Sync with upstream <package> <short sha>" (the new submodule commit).
# - Dependabot's commits (base image bumps in openbios/) are left out when there are other entries;
#   when there are none, the build is for them and they are listed.
# - More than WSH_CHANGELOG_MAX entries (default 30): the first ones, then "... and N more commits".
# - No previous build in the history (a shallow clone, or a package never built) or no commits in
#   the range (a build run by hand): the subject of the last commit to submodules/<package>.patch,
#   the single entry these builds had before.
#
# Run from anywhere in the repository; needs the history (fetch-depth: 0).
#
# Usage: scripts/wsh-changelog-entries.sh [--rev <commit>] <package>
#   --rev  the commit being built (default: HEAD)
# Exit:  0 (always prints at least one entry); 2 usage error
set -euo pipefail

usage() { echo "usage: $0 [--rev <commit>] pve-qemu|pve-manager|qemu-server|pve-storage" >&2; exit 2; }

rev=HEAD
pkg=""
while [ $# -gt 0 ]; do
    case "$1" in
        --rev) [ $# -ge 2 ] || usage; rev=$2; shift 2 ;;
        -*) usage ;;
        *) [ -z "$pkg" ] || usage; pkg=$1; shift ;;
    esac
done

case "$pkg" in
    pve-qemu)
        paths=(submodules/pve-qemu.patch submodules/pve-qemu-qemu-3dfx.patch submodules/qemu-3dfx
            submodules/qemu-3dfx.patch openbios submodules/pve-qemu) ;;
    pve-manager | qemu-server | pve-storage)
        paths=("submodules/$pkg.patch" "submodules/$pkg") ;;
    *) usage ;;
esac
max=${WSH_CHANGELOG_MAX:-30}

cd "$(git rev-parse --show-toplevel)"

fallback() {
    local s
    s=$(git log -1 --format=%s "$rev" -- "submodules/$pkg.patch" 2>/dev/null || true)
    [ -n "$s" ] || s=$(git log -1 --format=%s "$rev")
    printf '%s\n' "$s"
    exit 0
}

last=$(git log -1 --format=%H "$rev" -- "submodules/$pkg.changelog.patch")
[ -n "$last" ] || fallback

entries=()
bot=()
while IFS=$'\t' read -r sha author subject; do
    case "$subject" in
        "Update changelog for "*) continue ;;
        "Update submodule $pkg")
            subject="Sync with upstream $pkg $(git rev-parse --short "$sha:submodules/$pkg")" ;;
    esac
    case "$author" in
        dependabot\[bot\]*) bot+=("$subject"); continue ;;
    esac
    entries+=("$subject")
done < <(git log --reverse --no-merges --format=$'%H\t%an\t%s' "$last..$rev" -- "${paths[@]}")

[ ${#entries[@]} -gt 0 ] || entries=(${bot[@]+"${bot[@]}"})
[ ${#entries[@]} -gt 0 ] || fallback

if [ "${#entries[@]}" -gt "$max" ]; then
    printf '%s\n' "${entries[@]:0:max}"
    echo "... and $((${#entries[@]} - max)) more commits"
else
    printf '%s\n' "${entries[@]}"
fi
