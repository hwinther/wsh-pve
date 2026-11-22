#!/bin/sh
# Builds the wisp uClibc-ng toolchain image for one architecture:
#   build.sh <arch> [tag]            docker build; tags the image
#                                     ghcr.io/hwinther/wsh-pve/wisp-toolchain-<arch>:<tag>
#                                     (tag defaults to "latest"; a Buildroot version such as
#                                     2024.02.9 is a good tag once BUILDROOT_VERSION is filled in)
#   build.sh <arch> --export <dir>   also builds the image, then copies /opt/wisp-toolchain/<arch>
#                                     out of it as <dir>/wisp-toolchain-<arch>.tar.xz
#
# <arch>: sparc32, sparc64 or x86_64 (each needs its own <arch>_uclibc_defconfig in this
# directory). BUILDROOT_VERSION and BUILDROOT_SHA256 are still REPLACE-ME placeholders in
# Dockerfile; pass them with BUILD_ARGS, e.g.:
#   BUILD_ARGS='--build-arg BUILDROOT_VERSION=2024.02.9 --build-arg BUILDROOT_SHA256=...' \
#       ./build.sh sparc32
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ALL="sparc32 sparc64 x86_64"
BUILD_ARGS=${BUILD_ARGS:-}

log() { printf '%s\n' "wisp-toolchain: $*" >&2; }

[ $# -ge 1 ] || {
	log "usage: build.sh <arch> [tag] | build.sh <arch> --export <dir>"
	log "arch: one of $ALL"
	exit 2
}
ARCH=$1
shift

case " $ALL " in
*" $ARCH "*) : ;;
*) log "unknown architecture: $ARCH (one of: $ALL)"; exit 2 ;;
esac

[ -f "$HERE/${ARCH}_uclibc_defconfig" ] || {
	log "no ${ARCH}_uclibc_defconfig in $HERE"
	exit 2
}

EXPORT_DIR=
TAG=latest
if [ $# -ge 1 ] && [ "$1" = "--export" ]; then
	[ $# -ge 2 ] || { log "--export needs a directory"; exit 2; }
	EXPORT_DIR=$2
elif [ $# -ge 1 ]; then
	TAG=$1
fi

IMAGE="ghcr.io/hwinther/wsh-pve/wisp-toolchain-$ARCH:$TAG"

log "docker build --build-arg WISP_ARCH=$ARCH $BUILD_ARGS -t $IMAGE $HERE"
# shellcheck disable=SC2086 # BUILD_ARGS is meant to word-split into more --build-arg flags
docker build --build-arg WISP_ARCH="$ARCH" $BUILD_ARGS -t "$IMAGE" "$HERE"

if [ -n "$EXPORT_DIR" ]; then
	mkdir -p "$EXPORT_DIR"
	out="$EXPORT_DIR/wisp-toolchain-$ARCH.tar.xz"
	log "exporting /opt/wisp-toolchain/$ARCH to $out"
	cid=$(docker create "$IMAGE")
	# shellcheck disable=SC2064 # $cid is meant to expand now, not when the trap runs
	trap "docker rm -q '$cid' >/dev/null" EXIT
	docker cp "$cid:/opt/wisp-toolchain/$ARCH" - | xz -9 > "$out"
	log "wrote $out"
fi
