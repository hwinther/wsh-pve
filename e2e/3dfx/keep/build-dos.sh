#!/bin/sh
# Builds wshkeep for DOS (Glide 2 via GLIDE2X.DXE and Glide 3 via GLIDE3X.DXE, selected with
# -api glide2|glide3) in the DJGPP image (ghcr.io/hwinther/wsh-pve/djgpp-build:13) into
# OUTDIR/WSHKEEP.EXE, checked for Pentium ISA (--no-p6) and <= 96 KB (.kkrieger size budget):
#
#   docker run --rm -v "$PWD:/src:ro" -v "$OUT:/out" ghcr.io/hwinther/wsh-pve/djgpp-build:13 \
#     sh /src/e2e/3dfx/keep/build-dos.sh /out
#
# Copyright 2026 WsHosting ENK, GPL-3.
set -eu
OUT=${1:?usage: build-dos.sh OUTDIR}
SRC=${SRC:-/src}
D=$SRC/e2e/3dfx/keep
CC=i686-pc-msdosdjgpp-gcc
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

CFLAGS="-march=pentium -Os -Wall -Wextra -Wno-unused-parameter -std=gnu99 -fno-math-errno -fno-asynchronous-unwind-tables -I$D -I$SRC/e2e/wisp"
for f in keep be_glide2 be_glide3 plat_dos; do
	# shellcheck disable=SC2086
	$CC $CFLAGS -S -o "$work/$f.s" "$D/$f.c"
	$CC -c -o "$work/$f.o" "$work/$f.s"
done
# shellcheck disable=SC2086
$CC $CFLAGS -s -Wl,-Map,"$work/wshkeep.map" -o "$work/wshkeep.exe" \
	"$work/keep.o" "$work/be_glide2.o" "$work/be_glide3.o" "$work/plat_dos.o"
cp "$work/wshkeep.exe" "$OUT/WSHKEEP.EXE"

"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 \
	"$work/keep.s" "$work/be_glide2.s" "$work/be_glide3.s" "$work/plat_dos.s"
libgcc=$($CC -print-libgcc-file-name)
members=$(sed -n 's|^.*/libgcc\.a(\([^)]*\))$|\1|p' "$work/wshkeep.map" | sort -u)
for m in $members; do
	(cd "$work" && i686-pc-msdosdjgpp-ar x "$libgcc" "$m")
	"$SRC/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$work/$m"
done
echo "build-dos.sh: libgcc members linked: ${members:-none}"
game_bytes=$(i686-pc-msdosdjgpp-size "$work/keep.o" "$work/be_glide2.o" "$work/be_glide3.o" "$work/plat_dos.o" | awk 'NR>1 { s += $1 + $2 } END { print s }')
[ "$game_bytes" -le 98304 ] || { echo "build-dos.sh: game code+data is $game_bytes bytes (over 96 KB)" >&2; exit 1; }
size=$(wc -c < "$OUT/WSHKEEP.EXE")
[ "$size" -lt 204800 ] || { echo "build-dos.sh: WSHKEEP.EXE is $size bytes (over 200 KB)" >&2; exit 1; }
echo "build-dos.sh: ok $OUT/WSHKEEP.EXE ($size bytes with DJGPP DPMI runtime, game code+data $game_bytes bytes)"
