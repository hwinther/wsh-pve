#!/bin/sh
# The version of the wsh-openglide package at the checked-out commit, from git and the pinned
# upstream commit (upstream.env), printed as shell assignments (eval "$(packages/wsh-openglide/version.sh)"):
#
#   WSH_OPENGLIDE_VERSION=0.<N>+git<date>.<sha7>   N: commits on the path to HEAD that touch
#                                                  packages/wsh-openglide; date and sha7: the pinned
#                                                  qemu-xtra commit's
#   WSH_OPENGLIDE_COMMIT=<sha>                     the newest of those wsh-pve commits
#   WSH_OPENGLIDE_EPOCH=<unix time>                its committer date (SOURCE_DATE_EPOCH)
#
# Every commit that changes the package (a bump of the upstream pin included) adds one to N, so on
# main (linear: squash merges) the version only goes up, and a later commit that leaves the package
# alone gives the same version: the same package. A working tree with uncommitted changes to it gets
# ".dirty" appended (local builds only). Needs the full history (fetch-depth: 0).
set -eu
cd "$(dirname "$0")/../.."
INPUTS=packages/wsh-openglide

if [ "$(git rev-parse --is-shallow-repository)" = true ]; then
	echo "version.sh: a shallow clone can't count the commits (fetch the full history)" >&2
	exit 1
fi
commit_of() { sed -n "s/^$1=//p" "$INPUTS/upstream.env"; }
upstream=$(commit_of QEMU_XTRA_COMMIT)
date=$(commit_of QEMU_XTRA_DATE)
n=$(git rev-list --count HEAD -- "$INPUTS")
commit=$(git log -1 --format=%H -- "$INPUTS")
epoch=$(git log -1 --format=%ct -- "$INPUTS")
if [ -z "$commit" ]; then  # not committed yet (a local build of a new package)
	commit=$(git rev-parse HEAD)
	epoch=$(git log -1 --format=%ct HEAD)
fi
version="0.$n+git$date.$(printf %.7s "$upstream")"
if [ -n "$(git status --porcelain -- "$INPUTS")" ]; then
	version="$version.dirty"
fi
echo "WSH_OPENGLIDE_VERSION=$version"
echo "WSH_OPENGLIDE_COMMIT=$commit"
echo "WSH_OPENGLIDE_EPOCH=$epoch"
