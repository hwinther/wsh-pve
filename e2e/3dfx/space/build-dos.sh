#!/bin/sh
# Builds wshspace for DOS (Glide 2 through qemu-3dfx's GLIDE2X.DXE) in the DJGPP image
# (ghcr.io/hwinther/wsh-pve/djgpp-build:13) into OUTDIR/WSHSPACE.EXE, checked for Pentium ISA
# (--no-p6) and <= 96 KB (.kkrieger size budget):
#
#   docker run --rm -v "$PWD:/src:ro" -v "$OUT:/out" ghcr.io/hwinther/wsh-pve/djgpp-build:13 \
#     sh /src/e2e/3dfx/space/build-dos.sh /out
#
# Copyright 2026 WsHosting ENK, GPL-3.
set -eu
OUT=${1:?usage: build-dos.sh OUTDIR}
SRC=${SRC:-/src}
Q3=$SRC/submodules/qemu-3dfx
D=$SRC/e2e/3dfx/space
CC=i686-pc-msdosdjgpp-gcc
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

$CC -march=pentium -I"$Q3/wrappers/3dfx/src" -I"$Q3/qemu-0/hw/3dfx" -D__REV__="\"0000000-\"" -Wall -Werror -O3 \
	-fomit-frame-pointer -c -o "$work/glidedxe.o" "$Q3/wrappers/3dfx/dxe/glidedxe.c"
(cd "$work" && DXE_LD_LIBRARY_PATH=$(dirname "$(dirname "$(command -v $CC)")")/i686-pc-msdosdjgpp/lib \
	dxe3gen -o glide2x.dxe -Y libfxgl2.a -E _Convert -E _gr -E _gu glidedxe.o -lc)

CFLAGS="-march=pentium -Os -Wall -Wextra -Wno-unused-parameter -std=gnu99 -fno-math-errno -fno-asynchronous-unwind-tables -I$D"
for f in space be_glide2 plat_dos; do
	# shellcheck disable=SC2086
	$CC $CFLAGS -S -o "$work/$f.s" "$D/$f.c"
	$CC -c -o "$work/$f.o" "$work/$f.s"
done
# shellcheck disable=SC2086
$CC $CFLAGS -s -Wl,-Map,"$work/wshspace.map" -o "$work/wshspace.exe" "$work/space.o" "$work/be_glide2.o" "$work/plat_dos.o" \
	"$work/libfxgl2.a"
cp "$work/wshspace.exe" "$OUT/WSHSPACE.EXE"

"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/space.s" "$work/be_glide2.s" "$work/plat_dos.s"
libgcc=$($CC -print-libgcc-file-name)
members=$(sed -n 's|^.*/libgcc\.a(\([^)]*\))$|\1|p' "$work/wshspace.map" | sort -u)
for m in $members; do
	(cd "$work" && i686-pc-msdosdjgpp-ar x "$libgcc" "$m")
	"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/$m"
done
echo "build-dos.sh: libgcc members linked: ${members:-none}"
# Check both our own compiled code+data (<= 96 KB) and the full EXE with DJGPP's static DPMI+DXE runtime (< 200 KB, as wshdemo)
game_bytes=$(i686-pc-msdosdjgpp-size "$work/space.o" "$work/be_glide2.o" "$work/plat_dos.o" | awk 'NR>1 { s += $1 + $2 } END { print s }')
[ "$game_bytes" -le 98304 ] || { echo "build-dos.sh: game code+data is $game_bytes bytes (over 96 KB)" >&2; exit 1; }
size=$(wc -c < "$OUT/WSHSPACE.EXE")
[ "$size" -lt 204800 ] || { echo "build-dos.sh: WSHSPACE.EXE is $size bytes (over 200 KB)" >&2; exit 1; }
echo "build-dos.sh: ok $OUT/WSHSPACE.EXE ($size bytes with DJGPP DPMI runtime, game code+data $game_bytes bytes)"
