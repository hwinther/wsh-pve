#!/bin/sh
# Builds the Windows 98 test programs (w3drun.exe, glidetst.exe, gltest.exe, and w3dstrm.exe for
# e2e/streaming) with Debian's mingw-w64 (gcc-mingw-w64-i686) into OUTDIR, without mingw-w64's C
# runtime (see w3d.h): Windows 4.0 subsystem, i686 without SSE (the guest's CPU is a Pentium III;
# x87 floating point), imports from KERNEL32, USER32 and GDI32 only, which the end of this script
# checks.
#
#   e2e/3dfx/win98/build.sh OUTDIR
set -eu
out=${1:?usage: build.sh OUTDIR}
here=$(cd "$(dirname "$0")" && pwd)
scene=$here/../../../packages/wsh-openglide/tests
CC=${CC:-i686-w64-mingw32-gcc}
OBJDUMP=${OBJDUMP:-i686-w64-mingw32-objdump}
mkdir -p "$out"
for p in w3drun glidetst gltest w3dstrm; do
	"$CC" -O2 -Wall -Wextra -Wno-unused-parameter -Wno-cast-function-type -march=i686 -mno-sse -mfpmath=387 \
		-fno-tree-loop-distribute-patterns -fno-stack-protector \
		-fno-asynchronous-unwind-tables -mno-stack-arg-probe -I"$here" -I"$scene" \
		-nostdlib -nostartfiles -mwindows -Wl,--subsystem,windows:4.0 -Wl,--major-os-version,4 \
		-Wl,--minor-os-version,0 -s -o "$out/$p.exe" "$here/$p.c" -lgdi32 -luser32 -lkernel32 -lgcc
	dlls=$("$OBJDUMP" -p "$out/$p.exe" | sed -n 's/^\tDLL Name: //p' | tr '[:lower:]' '[:upper:]' | sort | tr '\n' ' ')
	for d in $dlls; do
		case $d in KERNEL32.DLL | USER32.DLL | GDI32.DLL) ;; *)
			echo "build.sh: $p.exe imports $d (only KERNEL32, USER32 and GDI32 are allowed)" >&2
			exit 1
			;;
		esac
	done
	echo "$p.exe: $(wc -c < "$out/$p.exe") bytes, imports $dlls"
done
