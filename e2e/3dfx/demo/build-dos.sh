#!/bin/sh
# Builds wshdemo for DOS (Glide 2 through qemu-3dfx's GLIDE2X.DXE) in the DJGPP image that builds the
# guest drivers (djgpp.Dockerfile), into OUTDIR/WSHDEMO.EXE:
#
#   docker run --rm -v "$PWD:/src:ro" -v "$OUT:/out" ghcr.io/hwinther/wsh-pve/djgpp-build:13 \
#     sh /src/e2e/3dfx/demo/build-dos.sh /out
#
# The program links with libfxgl2.a, the import library dxe3gen -Y makes next to the DXE (from
# qemu-3dfx's wrappers/3dfx/dxe/glidedxe.c, as e2e/3dfx/dos/build.sh): its stubs load the drivers
# release's GLIDE2X.DXE at run time, so the program doesn't depend on the wrapper's revision. For a
# Pentium (-march=pentium; DJGPP's libc has no P6 instruction either), checked with
# scripts/check-3dfx-drivers-isa.sh --no-p6. /src is this repository with submodules/qemu-3dfx
# checked out. Copyright 2026 WsHosting ENK, GPL-3.
set -eu
OUT=${1:?usage: build-dos.sh OUTDIR}
SRC=${SRC:-/src}
Q3=$SRC/submodules/qemu-3dfx
D=$SRC/e2e/3dfx/demo
CC=i686-pc-msdosdjgpp-gcc
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# the import library (the revision stamped into this glide2x.dxe doesn't matter: only the stubs are used)
$CC -march=pentium -I"$Q3/wrappers/3dfx/src" -I"$Q3/qemu-0/hw/3dfx" -D__REV__="\"0000000-\"" -Wall -Werror -O3 \
	-fomit-frame-pointer -c -o "$work/glidedxe.o" "$Q3/wrappers/3dfx/dxe/glidedxe.c"
(cd "$work" && DXE_LD_LIBRARY_PATH=$(dirname "$(dirname "$(command -v $CC)")")/i686-pc-msdosdjgpp/lib \
	dxe3gen -o glide2x.dxe -Y libfxgl2.a -E _Convert -E _gr -E _gu glidedxe.o -lc)

CFLAGS="-march=pentium -O2 -Wall -Wextra -Wno-unused-parameter -std=gnu99 -fno-math-errno -fno-asynchronous-unwind-tables"
for f in demo be_glide2 plat_dos; do
	# shellcheck disable=SC2086 # CFLAGS is a list
	$CC $CFLAGS -S -o "$work/$f.s" "$D/$f.c"
done
# shellcheck disable=SC2086
$CC $CFLAGS -s -Wl,-Map,"$work/wshdemo.map" -o "$work/wshdemo.exe" "$work/demo.s" "$work/be_glide2.s" "$work/plat_dos.s" \
	"$work/libfxgl2.a"
cp "$work/wshdemo.exe" "$OUT/WSHDEMO.EXE"

# For a Pentium: DJGPP keeps read-only data in .text, so the program's disassembly would read tables
# as instructions; check our code in GCC's assembler output instead, and the libgcc members the link
# took (libc and crt0 are i386 code; libgcc is built for the i686)
"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/demo.s" "$work/be_glide2.s" "$work/plat_dos.s"
libgcc=$($CC -print-libgcc-file-name)
members=$(sed -n 's|^.*/libgcc\.a(\([^)]*\))$|\1|p' "$work/wshdemo.map" | sort -u)
for m in $members; do
	(cd "$work" && i686-pc-msdosdjgpp-ar x "$libgcc" "$m")
	"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/$m"
done
echo "build-dos.sh: libgcc members linked: ${members:-none}"
size=$(wc -c < "$OUT/WSHDEMO.EXE")
[ "$size" -lt 204800 ] || { echo "build-dos.sh: WSHDEMO.EXE is $size bytes (over 200 KB)" >&2; exit 1; }
echo "build-dos.sh: ok $OUT/WSHDEMO.EXE ($size bytes)"
