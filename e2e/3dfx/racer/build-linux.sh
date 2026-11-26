#!/usr/bin/env bash
# Builds wshracer for i386 Linux guests (Glide 2 through libglide.so.2) with gcc-multilib into
# OUTDIR/wshracer: i586 (-march=pentium, x87, no P6/CMOV/SSE), custom _start requiring nothing
# newer than GLIBC_2.0, needing only libc.so.6 and libglide.so.2, and <= 96 KB (.kkrieger budget).
#
#   e2e/3dfx/racer/build-linux.sh OUTDIR [GLIDE_LIB_DIR]
# Copyright 2026 WsHosting ENK, GPL-3.
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2; exit 2; }
out=$1
libdir=${2:-}
here=$(cd "$(dirname "$0")" && pwd)
top=$(cd "$here/../../.." && pwd)
MAX_GLIBC=${MAX_GLIBC:-2.0}
CC=${CC:-gcc}
fail() { echo "build-linux.sh: FAIL $*" >&2; exit 1; }
mkdir -p "$out"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [ -z "$libdir" ]; then
	libdir=$work/linux-glide
	bash "$top/scripts/build-3dfx-linux-glide.sh" "$top/submodules/qemu-3dfx" 0000000 "$libdir" > /dev/null
fi
[ -e "$libdir/libglide2x.so" ] || fail "no libglide2x.so in $libdir"

"$CC" -m32 -march=pentium -mtune=generic -Os -Wall -Wextra -Wno-unused-parameter -std=gnu99 \
	-I"$here" -I"$top/e2e/wisp" -fno-pic -no-pie -fno-stack-protector -U_FORTIFY_SOURCE -fcf-protection=none \
	-fno-asynchronous-unwind-tables -fno-math-errno -nostartfiles -static-libgcc \
	-Wl,--hash-style=both -Wl,-z,noseparate-code -Wl,-z,noexecstack -Wl,--as-needed -s \
	-o "$out/wshracer" "$here/racer.c" "$here/be_glide2.c" "$here/plat_linux.c" -L"$libdir" -lglide2x
bin=$out/wshracer

needed=$(objdump -p "$bin" | awk '$1 == "NEEDED" { print $2 }' | sort | paste -sd ' ')
[ "$needed" = "libc.so.6 libglide.so.2" ] || fail "$bin needs '$needed', not libglide.so.2 and libc.so.6"
newest=$(objdump -T "$bin" | grep -o 'GLIBC_[0-9][0-9.]*' | sed 's/^GLIBC_//' | sort -u -V | tail -n 1)
[ -n "$newest" ] || fail "$bin has no versioned glibc symbol"
[ "$(printf '%s\n%s\n' "$newest" "$MAX_GLIBC" | sort -V | tail -n 1)" = "$MAX_GLIBC" ] \
	|| fail "$bin needs GLIBC_$newest, newer than GLIBC_$MAX_GLIBC: $(objdump -T "$bin" | grep "GLIBC_$newest" | awk '{ print $NF }' | tr '\n' ' ')"
objdump -p "$bin" | grep -q '^ *HASH ' || fail "$bin has no SysV hash table (DT_HASH)"
p6=$(objdump -d --no-show-raw-insn "$bin" | grep -cE $'\t(cmov|fcmov|fcomi|fucomi|endbr32|nop[wl] )' || true)
[ "$p6" = 0 ] || fail "$bin has $p6 instructions a Pentium lacks (CMOV, FCOMI, ENDBR32, long NOP)"
"$top/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$bin"
size=$(wc -c < "$bin")
[ "$size" -le 98304 ] || fail "$bin is $size bytes (over 96 KB)"
echo "build-linux.sh: ok $bin ($size bytes, needs $needed, newest GLIBC_$newest)"
