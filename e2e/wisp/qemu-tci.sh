#!/bin/sh
# Builds QEMU with the TCG interpreter (TCI) for wisp's targets, inside the wisp
# image (its apt sources include the Proxmox repository for libproxmox-backup-qemu0-dev):
#   ./qemu-tci.sh <qemu source tree> <build dir> [targets]
# The source tree is pve-qemu's `qemu` with its debian/patches applied (quilt push -a), or plain
# upstream QEMU 11.1. Default targets: x86_64-softmmu,i386-softmmu,sparc-softmmu,sparc64-softmmu.
# Then: ./run.py --qemu-dir <build dir> --label tci ...
#
# MODE=tcg builds the same tree without the interpreter, for a like-for-like TCG comparison.
set -eu
SRC=$(cd "$1" && pwd)
BUILD=$2
TARGETS=${3:-x86_64-softmmu,i386-softmmu,sparc-softmmu,sparc64-softmmu}
MODE=${MODE:-tci}
JOBS=${JOBS:-4}

apt-get update -qq
apt-get install -y -qq --no-install-recommends build-essential ninja-build python3 python3-venv pkg-config \
	libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libpng-dev libslirp-dev flex bison \
	libsystemd-dev uuid-dev libproxmox-backup-qemu0-dev >/dev/null

extra=
[ "$MODE" = tci ] && extra=--enable-tcg-interpreter
mkdir -p "$BUILD"
cd "$BUILD"
[ -f build.ninja ] || nice -n 10 "$SRC/configure" --target-list="$TARGETS" \
	--disable-docs --disable-werror --disable-gtk --disable-sdl --disable-vnc --disable-opengl \
	--disable-capstone --enable-png --enable-slirp --with-pkgversion="wisp-$MODE" $extra
bins=
for t in $(echo "$TARGETS" | tr , ' '); do
	bins="$bins qemu-system-${t%-softmmu}"
done
# shellcheck disable=SC2086
nice -n 10 ninja -j"$JOBS" $bins
