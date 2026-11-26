#!/bin/sh
# Builds the DOS Glide test program in the DJGPP image (djgpp.Dockerfile, the one that builds the
# qemu-3dfx guest drivers):
#
#   docker run --rm -v "$PWD:/src:ro" -v "$OUT:/out" ghcr.io/hwinther/wsh-pve/djgpp-build:13 \
#     sh /src/e2e/3dfx/dos/build.sh /out REV
#
#   GLIDEDOS.EXE   the test program (glidedos.c), linked with libfxgl2.a
#   libfxgl2.a     the import library of GLIDE2X.DXE, made by dxe3gen -Y from qemu-3dfx's DXE wrapper
#                  (wrappers/3dfx/dxe/glidedxe.c), as its Makefile makes it; the stubs in it load the
#                  DXE at run time, so the program works with the GLIDE2X.DXE of the drivers release
#   glide2x.dxe    the wrapper built here as well, with __REV__ = REV (the revision the host binary
#                  names); the test uses the release's, this one is for comparison
#   VBELIST.EXE    lists the video BIOS's VESA modes (vbelist.c), a tool for DOS guests; its code is
#                  checked with scripts/check-3dfx-drivers-isa.sh --no-p6
#
# Everything for a Pentium (-march=pentium), as the drivers release. /src is this repository with
# submodules/qemu-3dfx checked out. Copyright 2026 WsHosting ENK, GPL-3.
set -eu
OUT=${1:?usage: build.sh OUTDIR REV}
REV=${2:?usage: build.sh OUTDIR REV}
SRC=${SRC:-/src}
Q3=$SRC/submodules/qemu-3dfx
CC=i686-pc-msdosdjgpp-gcc
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# glidedxe.c as wrappers/3dfx/dxe/Makefile (with submodules/qemu-3dfx-drivers.patch) builds it
$CC -march=pentium -I"$Q3/wrappers/3dfx/src" -I"$Q3/qemu-0/hw/3dfx" -D__REV__="\"$REV-\"" -Wall -Werror -O3 \
	-fomit-frame-pointer -c -o "$work/glidedxe.o" "$Q3/wrappers/3dfx/dxe/glidedxe.c"
(cd "$work" && DXE_LD_LIBRARY_PATH=$(dirname "$(dirname "$(command -v $CC)")")/i686-pc-msdosdjgpp/lib \
	dxe3gen -o glide2x.dxe -Y libfxgl2.a -E _Convert -E _gr -E _gu glidedxe.o -lc)

$CC -march=pentium -O2 -Wall -Werror -I"$SRC/packages/wsh-openglide/tests" -o "$work/glidedos.exe" \
	"$SRC/e2e/3dfx/dos/glidedos.c" "$work/libfxgl2.a"

$CC -march=pentium -O2 -Wall -Werror -S -o "$work/vbelist.s" "$SRC/e2e/3dfx/dos/vbelist.c"
$CC -s -o "$work/vbelist.exe" "$work/vbelist.s"
"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/vbelist.s"

cp "$work/glidedos.exe" "$OUT/GLIDEDOS.EXE"
cp "$work/vbelist.exe" "$OUT/VBELIST.EXE"
cp "$work/libfxgl2.a" "$work/glide2x.dxe" "$OUT/"
ls -l "$OUT"
