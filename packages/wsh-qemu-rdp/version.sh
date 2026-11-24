#!/bin/sh
# The version of the wsh-qemu-rdp package at the checked-out commit, from git and the pinned
# upstream commit (upstream.env), printed as shell assignments (eval "$(packages/wsh-qemu-rdp/version.sh)"):
#
#   WSH_QEMU_RDP_VERSION=<v>+git<date>.<sha7>.wsh<N>   v: qemu-rdp's version at the pin; date and
#                                                      sha7: the pinned qemu-display commit's; N:
#                                                      commits on the path to HEAD that touch
#                                                      packages/wsh-qemu-rdp
#   WSH_QEMU_RDP_COMMIT=<sha>                          the newest of those wsh-pve commits
#   WSH_QEMU_RDP_EPOCH=<unix time>                     its committer date (SOURCE_DATE_EPOCH)
#
# A newer pin raises the date (or qemu-rdp's version) and every commit that changes the package adds
# one to N, so on main (linear: squash merges) the version only goes up, and a later commit that
# leaves the package alone gives the same version: the same package. A working tree with uncommitted
# changes to it gets ".dirty" appended (local builds only). Needs the full history (fetch-depth: 0).
set -eu
cd "$(dirname "$0")/../.."
INPUTS=packages/wsh-qemu-rdp

if [ "$(git rev-parse --is-shallow-repository)" = true ]; then
	echo "version.sh: a shallow clone can't count the commits (fetch the full history)" >&2
	exit 1
fi
value_of() { sed -n "s/^$1=//p" "$INPUTS/upstream.env"; }
upstream=$(value_of QEMU_DISPLAY_COMMIT)
date=$(value_of QEMU_DISPLAY_DATE)
rdp=$(value_of QEMU_RDP_VERSION)
n=$(git rev-list --count HEAD -- "$INPUTS")
commit=$(git log -1 --format=%H -- "$INPUTS")
epoch=$(git log -1 --format=%ct -- "$INPUTS")
if [ -z "$commit" ]; then  # not committed yet (a local build of a new package)
	commit=$(git rev-parse HEAD)
	epoch=$(git log -1 --format=%ct HEAD)
fi
version="$rdp+git$date.$(printf %.7s "$upstream").wsh$n"
if [ -n "$(git status --porcelain -- "$INPUTS")" ]; then
	version="$version.dirty"
fi
echo "WSH_QEMU_RDP_VERSION=$version"
echo "WSH_QEMU_RDP_COMMIT=$commit"
echo "WSH_QEMU_RDP_EPOCH=$epoch"
