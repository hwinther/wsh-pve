#!/usr/bin/env bash
# Builds qemu-3dfx's Linux guest wrapper (wrappers/3dfx/dso/glidedso.c, Glide 2.x) as the shared
# library an old i386 Linux guest loads: libglide.so.2 (soname libglide.so.2), with libglide2x.so as
# a symlink to it, the other name Glide 2 programs and Mesa's old fxMesa driver were linked against.
# The wrapper maps the glidept MMIO page and the shared FIFO through /dev/mem and forwards every Glide
# call to the host's qemu-system-x86_64-3dfx, so the revision it is stamped with (__REV__) must be the
# host binary's, as for the Windows and DOS wrappers.
#
#   scripts/build-3dfx-linux-glide.sh QEMU3DFX_DIR REV OUTDIR
#
#   QEMU3DFX_DIR  a qemu-3dfx checkout (submodules/qemu-3dfx)
#   REV           its revision, 7 hex digits (git rev-parse --short=7 HEAD), or the one the host
#                 binary's --version names ("featuring qemu-3dfx@<rev>-...")
#   OUTDIR        gets libglide.so.2, libglide2x.so (symlink) and README.txt
#
# Built for old distributions: i586 (-march=pentium, x87 math, no CMOV, MMX or SSE; checked with
# scripts/check-3dfx-drivers-isa.sh and for CMOV/ENDBR32 here), no stack protector, fortify or CET
# (none of them in an old glibc or CPU), SysV hash table next to the GNU one (dynamic loaders before
# glibc 2.5 read only DT_HASH), libgcc linked statically, and only libc.so.6 needed. The build fails
# when the library needs a glibc symbol version newer than MAX_GLIBC (default 2.0: every glibc 2.x
# from 1997 on) or anything but libc.so.6. Needs gcc with -m32 (gcc-multilib) and binutils.
set -euo pipefail

[ $# -eq 3 ] || { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2; exit 2; }
Q3=$1 REV=$2 OUT=$3
MAX_GLIBC=${MAX_GLIBC:-2.0}
here=$(cd "$(dirname "$0")" && pwd)
fail() { echo "build-3dfx-linux-glide: FAIL $*" >&2; exit 1; }

[[ $REV =~ ^[0-9a-f]{7}$ ]] || fail "REV must be 7 hex digits, not '$REV'"
src=$Q3/wrappers/3dfx/dso/glidedso.c
[ -f "$src" ] || fail "$src: no such file (is the qemu-3dfx submodule checked out?)"
mkdir -p "$OUT"
rm -f "$OUT/libglide.so.2" "$OUT/libglide2x.so"

# The same CFLAGS as upstream's dso/Makefile (-Wall -Werror -O3 -fomit-frame-pointer), for the
# Pentium and position independent. -nostartfiles: the wrapper has no constructors, and the
# toolchain's crtbeginS.o would add a weak reference to __cxa_finalize (GLIBC_2.1.3, which a glibc
# 2.0 or 2.1 loader refuses) and ENDBR32 instructions
${CC:-gcc} -m32 -march=pentium -mtune=generic -O3 -fomit-frame-pointer -fPIC -Wall -Werror \
	-fno-stack-protector -U_FORTIFY_SOURCE -fcf-protection=none -fno-plt \
	-I"$Q3/qemu-0/hw/3dfx" -I"$Q3/wrappers/3dfx/src" -D__REV__="\"$REV-\"" \
	-shared -nostartfiles -static-libgcc -Wl,-soname,libglide.so.2 -Wl,--hash-style=both -Wl,-z,noseparate-code \
	-Wl,-z,noexecstack -Wl,--no-undefined -Wl,--as-needed \
	-o "$OUT/libglide.so.2" "$src"
ln -s libglide.so.2 "$OUT/libglide2x.so"
lib=$OUT/libglide.so.2

# What the library asks of the system: libc.so.6 only, no glibc symbol version past MAX_GLIBC
needed=$(objdump -p "$lib" | awk '$1 == "NEEDED" { print $2 }' | sort -u | paste -sd ' ')
[ "$needed" = libc.so.6 ] || fail "$lib needs ${needed:-nothing}, not just libc.so.6"
versions=$(objdump -T "$lib" | grep -o 'GLIBC_[0-9][0-9.]*' | sed 's/^GLIBC_//' | sort -u -V)
newest=$(printf '%s\n' "$versions" | tail -n 1)
[ -n "$newest" ] || fail "$lib has no versioned glibc symbol (not linked against glibc?)"
[ "$(printf '%s\n%s\n' "$newest" "$MAX_GLIBC" | sort -V | tail -n 1)" = "$MAX_GLIBC" ] \
	|| fail "$lib needs GLIBC_$newest, newer than GLIBC_$MAX_GLIBC: $(objdump -T "$lib" | grep "GLIBC_$newest" | awk '{ print $NF }' | tr '\n' ' ')"
objdump -p "$lib" | grep -q '^ *HASH ' || fail "$lib has no SysV hash table (DT_HASH)"
# A Pentium: no CMOV either (allowed for the Windows DLLs' MinGW runtime, not needed here), and no
# ENDBR32 (a hint NOP from the P6 on, an invalid opcode on a Pentium)
p6=$(objdump -d --no-show-raw-insn "$lib" | grep -cE $'\t(cmov|fcmov|fcomi|fucomi|endbr32|nop[wl] )' || true)
[ "$p6" = 0 ] || fail "$lib has $p6 instructions a Pentium lacks (CMOV, FCOMI, ENDBR32, long NOP)"
"$here/check-3dfx-drivers-isa.sh" "$lib"
glide_syms=$(objdump -T "$lib" | awk '$4 == ".text" && $NF ~ /^(gr|gu|Convert)/' | wc -l)

cat > "$OUT/README.txt" << EOF
qemu-3dfx Linux guest Glide wrapper (Glide 2.x)
================================================

qemu-3dfx revision (__REV__): $REV-
Built for i386 guests: i586 (Pentium, x87 math; no CMOV, MMX or SSE), glibc 2.0 or later
(newest symbol version required: GLIBC_$newest), needs only libc.so.6.

Files
  libglide.so.2   the Glide 2.x library (soname libglide.so.2, $glide_syms Glide entry points)
  libglide2x.so   symlink to libglide.so.2, the name 3dfx's Linux Glide 2 shipped as and that
                  programs and Mesa's old 3dfx (fxMesa) driver were linked against

It does not drive a Voodoo card: it forwards every Glide call to the qemu-3dfx Glide pass-through
of the VM's QEMU (qemu-system-x86_64-3dfx of pve-qemu-kvm with wsh-openglide on the Proxmox host).
The host binary must be built from the same qemu-3dfx revision: \`qemu-system-x86_64-3dfx --version\`
on the host ends in "featuring qemu-3dfx@$REV-...". Against another revision grGlideInit fails.

Installing (as root, in the guest)
  cp -P libglide.so.2 libglide2x.so /usr/lib/
  ldconfig
Remove or rename any other libglide.so.2 / libglide2x.so first (3dfx's own Glide, Device3Dfx).
A program that loads the library by another name gets a symlink of that name to libglide.so.2.

Running
  The wrapper maps physical memory through /dev/mem (the glidept MMIO page and the shared memory,
  in the PCI hole between 0xe8000000 and 0xfbdfffff): the Glide program must run as root (or
  setuid root, as 3dfx's Glide required too). CONFIG_STRICT_DEVMEM allows it (the range is not
  RAM). No kernel module is needed.

Covers Glide 2.x only (the Glide 2.43 API of qemu-3dfx's wrapper). Glide 3 (libglide3.so.3, which
later Mesa 3dfx drivers used) and OpenGL have no Linux guest wrapper in qemu-3dfx. A modern Linux
guest should use virtio-gpu with virgl (vga: virtio-gl) for OpenGL instead.
EOF
echo "build-3dfx-linux-glide: ok $lib (qemu-3dfx $REV, $glide_syms Glide entry points, needs $needed, newest GLIBC_$newest)"
