#!/bin/sh
# Builds the DOS Glide test programs in the DJGPP image (djgpp.Dockerfile, the one that builds the
# qemu-3dfx guest drivers):
#
#   docker run --rm -v "$PWD:/src:ro" -v "$OUT:/out" ghcr.io/hwinther/wsh-pve/djgpp-build:13 \
#     sh /src/e2e/3dfx/dos/build.sh /out REV
#
#   GLIDEDOS.EXE   the Glide 2 test program (glidedos.c), linked with libfxgl2.a
#   GLID3DOS.EXE   the Glide 3 test program (glidedos.c with -DGLIDE3), linked with libfxgl3.a
#   libfxgl2.a     the import libraries of GLIDE2X.DXE and GLIDE3X.DXE, made by dxe3gen -Y from
#   libfxgl3.a     qemu-3dfx's DXE wrappers (wrappers/3dfx/dxe/glidedxe.c and gl301dxe.c), as its
#                  Makefile makes them; the stubs in them load the DXE at run time, so the programs
#                  work with the DXEs of the drivers release
#   glide2x.dxe    the wrappers built here as well, with __REV__ = REV (the revision the host binary
#   glide3x.dxe    names); the test uses the release's, these are for comparison
#
# Everything for a Pentium (-march=pentium), as the drivers release; the programs' own code (GCC's
# assembler output: DJGPP keeps read-only data in .text) and the libgcc members they link are checked
# with scripts/check-3dfx-drivers-isa.sh --no-p6. /src is this repository with submodules/qemu-3dfx
# checked out. Copyright 2026 WsHosting ENK, GPL-3.
set -eu
OUT=${1:?usage: build.sh OUTDIR REV}
REV=${2:?usage: build.sh OUTDIR REV}
SRC=${SRC:-/src}
Q3=$SRC/submodules/qemu-3dfx
CC=i686-pc-msdosdjgpp-gcc
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
libdir=$(dirname "$(dirname "$(command -v $CC)")")/i686-pc-msdosdjgpp/lib

# glidedxe.c and gl301dxe.c as wrappers/3dfx/dxe/Makefile (with submodules/qemu-3dfx-drivers.patch)
# builds them
for w in glidedxe gl301dxe; do
	$CC -march=pentium -I"$Q3/wrappers/3dfx/src" -I"$Q3/qemu-0/hw/3dfx" -D__REV__="\"$REV-\"" -Wall -Werror -O3 \
		-fomit-frame-pointer -c -o "$work/$w.o" "$Q3/wrappers/3dfx/dxe/$w.c"
done
(cd "$work" && DXE_LD_LIBRARY_PATH=$libdir dxe3gen -o glide2x.dxe -Y libfxgl2.a -E _Convert -E _gr -E _gu glidedxe.o -lc)
(cd "$work" && DXE_LD_LIBRARY_PATH=$libdir dxe3gen -o glide3x.dxe -Y libfxgl3.a -E _gr -E _gu gl301dxe.o -lc)

CFLAGS="-march=pentium -O2 -Wall -Werror -I$SRC/packages/wsh-openglide/tests"
# shellcheck disable=SC2086 # CFLAGS is a list
$CC $CFLAGS -S -o "$work/glidedos.s" "$SRC/e2e/3dfx/dos/glidedos.c"
# shellcheck disable=SC2086
$CC $CFLAGS -DGLIDE3 -S -o "$work/glide3dos.s" "$SRC/e2e/3dfx/dos/glidedos.c"
# shellcheck disable=SC2086
$CC $CFLAGS -Wl,-Map,"$work/glidedos.map" -o "$work/glidedos.exe" "$work/glidedos.s" "$work/libfxgl2.a"
# shellcheck disable=SC2086
$CC $CFLAGS -Wl,-Map,"$work/glide3dos.map" -o "$work/glide3dos.exe" "$work/glide3dos.s" "$work/libfxgl3.a"

# For a Pentium (see e2e/3dfx/demo/build-dos.sh): our code in GCC's assembler output, and the libgcc
# members the links took (libc and crt0 are i386 code; libgcc is built for the i686)
"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/glidedos.s" "$work/glide3dos.s"
libgcc=$($CC -print-libgcc-file-name)
members=$(sed -n 's|^.*/libgcc\.a(\([^)]*\))$|\1|p' "$work/glidedos.map" "$work/glide3dos.map" | sort -u)
for m in $members; do
	(cd "$work" && i686-pc-msdosdjgpp-ar x "$libgcc" "$m")
	"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/$m"
done
echo "build.sh: libgcc members linked: ${members:-none}"

cp "$work/glidedos.exe" "$OUT/GLIDEDOS.EXE"
cp "$work/glide3dos.exe" "$OUT/GLID3DOS.EXE"
cp "$work/libfxgl2.a" "$work/glide2x.dxe" "$work/libfxgl3.a" "$work/glide3x.dxe" "$OUT/"
ls -l "$OUT"
