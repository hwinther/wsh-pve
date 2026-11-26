#!/bin/sh
# Builds wshkeep for Windows 9x/ME/2000/XP (Glide 2, Glide 3 and OpenGL in one WSHKEEP.EXE) with
# mingw-w64 (gcc-mingw-w64-i686) into OUTDIR: without mingw-w64's C runtime, Windows 4.0 subsystem,
# static imports from KERNEL32, USER32 and GDI32 only (WINMM.DLL is loaded at run time if present),
# for a Pentium (-march=pentium, x87, --no-p6), capped at 96 KB (.kkrieger size budget).
#
#   e2e/3dfx/keep/build-win.sh OUTDIR
# Copyright 2026 WsHosting ENK, GPL-3.
set -eu
out=${1:?usage: build-win.sh OUTDIR}
here=$(cd "$(dirname "$0")" && pwd)
top=$(cd "$here/../../.." && pwd)
CC=${CC:-i686-w64-mingw32-gcc}
OBJDUMP=${OBJDUMP:-i686-w64-mingw32-objdump}
mkdir -p "$out"
exe=$out/WSHKEEP.EXE
"$CC" -Os -std=gnu99 -Wall -Wextra -Wno-unused-parameter -Wno-cast-function-type -march=pentium -mfpmath=387 \
	-fno-builtin -fno-tree-loop-distribute-patterns -fno-math-errno -fno-stack-protector \
	-fno-asynchronous-unwind-tables -mno-stack-arg-probe -I"$here" -I"$top/e2e/wisp" \
	-I"$top/e2e/3dfx/win98" -nostdlib -nostartfiles -mwindows -Wl,--subsystem,windows:4.0 -Wl,--major-os-version,4 \
	-Wl,--minor-os-version,0 -s -o "$exe" "$here/keep.c" "$here/be_glide2.c" "$here/be_glide3.c" "$here/be_gl.c" \
	"$here/plat_win.c" -lgdi32 -luser32 -lkernel32 -lgcc
dlls=$("$OBJDUMP" -p "$exe" | sed -n 's/^\tDLL Name: //p' | tr '[:lower:]' '[:upper:]' | sort | tr '\n' ' ')
for d in $dlls; do
	case $d in KERNEL32.DLL | USER32.DLL | GDI32.DLL) ;; *)
		echo "build-win.sh: WSHKEEP.EXE imports $d (only KERNEL32, USER32 and GDI32 are allowed)" >&2
		exit 1
		;;
	esac
done
"$top/scripts/check-3dfx-drivers-isa.sh" --no-p6 "$exe"
size=$(wc -c < "$exe")
[ "$size" -le 98304 ] || { echo "build-win.sh: WSHKEEP.EXE is $size bytes (over 96 KB)" >&2; exit 1; }
echo "build-win.sh: ok $exe ($size bytes, imports $dlls)"
