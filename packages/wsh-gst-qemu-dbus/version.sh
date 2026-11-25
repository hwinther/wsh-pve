#!/bin/sh
# The version of the wsh-gst-qemu-dbus package at the checked-out commit, from git, printed as
# shell assignments (eval "$(packages/wsh-gst-qemu-dbus/version.sh)"):
#
#   WSH_GST_QEMU_DBUS_VERSION=0.<N>+g<sha7>   N: commits on the path to HEAD that touch
#                                             packages/wsh-gst-qemu-dbus; sha7: the newest's
#   WSH_GST_QEMU_DBUS_COMMIT=<sha>            that newest commit
#   WSH_GST_QEMU_DBUS_EPOCH=<unix time>       its committer date (SOURCE_DATE_EPOCH)
#
# Every commit that changes the package adds one to N, so on main (linear: squash merges) the
# version only goes up, and a later commit that leaves the package alone gives the same version:
# the same package. A working tree with uncommitted changes to it gets ".dirty" appended (local
# builds only). Needs the full history (fetch-depth: 0).
set -eu
cd "$(dirname "$0")/../.."
INPUTS=packages/wsh-gst-qemu-dbus

if [ "$(git rev-parse --is-shallow-repository)" = true ]; then
	echo "version.sh: a shallow clone can't count the commits (fetch the full history)" >&2
	exit 1
fi
n=$(git rev-list --count HEAD -- "$INPUTS")
commit=$(git log -1 --format=%H -- "$INPUTS")
epoch=$(git log -1 --format=%ct -- "$INPUTS")
if [ -z "$commit" ]; then  # not committed yet (a local build of a new package)
	commit=$(git rev-parse HEAD)
	epoch=$(git log -1 --format=%ct HEAD)
fi
version="0.$n+g$(printf %.7s "$commit")"
if [ -n "$(git status --porcelain -- "$INPUTS")" ]; then
	version="$version.dirty"
fi
echo "WSH_GST_QEMU_DBUS_VERSION=$version"
echo "WSH_GST_QEMU_DBUS_COMMIT=$commit"
echo "WSH_GST_QEMU_DBUS_EPOCH=$epoch"
