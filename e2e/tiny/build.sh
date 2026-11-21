#!/bin/sh
# Builds the tiny test system for one or more architectures:
#   ./build.sh [x86_64|i386|sparc32|sparc64|all]...
# Output per architecture in out/<arch>/: kernel (initramfs built in), init (PID 1), config, sizes.
#
# Kernel: `make tinyconfig` plus config/common.config and config/<arch>.config, with the initramfs
# (an uncompressed cpio of /init and /dev/console) linked into the image. PID 1: init.c, built static
# against the kernel's own nolibc (tools/include/nolibc) and the kernel's UAPI headers.
#
# Environment: KSRC (an unpacked kernel tree; default: unpack /usr/src/linux-source-*.tar.xz into
# build/), BUILD (default build/), OUT (default out/), JOBS (default 4).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=${BUILD:-$HERE/build}
OUT=${OUT:-$HERE/out}
JOBS=${JOBS:-4}
ALL="x86_64 i386 sparc32 sparc64"

log() { printf '%s\n' "tiny: $*" >&2; }

kernel_source() {
	if [ -n "${KSRC:-}" ]; then
		return
	fi
	KSRC=$BUILD/linux
	if [ ! -f "$KSRC/Makefile" ]; then
		tarball=$(ls /usr/src/linux-source-*.tar.xz 2>/dev/null | sort -V | tail -n 1)
		[ -n "$tarball" ] || { log "no KSRC and no /usr/src/linux-source-*.tar.xz"; exit 1; }
		log "unpacking $tarball"
		mkdir -p "$KSRC"
		tar -xJf "$tarball" -C "$KSRC" --strip-components=1
	fi
}

# Per architecture: kernel ARCH, kernel CROSS_COMPILE, image path in the build tree and make target,
# the compiler and flags for init.
arch_vars() {
	case "$1" in
	x86_64)
		KARCH=x86_64 KCROSS= IMAGE=arch/x86/boot/bzImage TARGET=bzImage
		UCC=gcc UCFLAGS="-m64" ;;
	i386)
		KARCH=i386 KCROSS= IMAGE=arch/x86/boot/bzImage TARGET=bzImage
		UCC=i686-linux-gnu-gcc UCFLAGS="-m32 -march=i686" ;;
	sparc32)
		KARCH=sparc KCROSS=sparc64-linux-gnu- IMAGE=arch/sparc/boot/image TARGET=image
		UCC=sparc64-linux-gnu-gcc UCFLAGS="-m32 -mcpu=v8" ;;
	sparc64)
		KARCH=sparc64 KCROSS=sparc64-linux-gnu- IMAGE=arch/sparc/boot/image TARGET=image
		UCC=sparc64-linux-gnu-gcc UCFLAGS="-m64" ;;
	*)
		log "unknown architecture: $1 (one of: $ALL)"; exit 2 ;;
	esac
}

kmake() {
	nice -n 10 make -s -C "$KSRC" O="$KB" ARCH="$KARCH" CROSS_COMPILE="$KCROSS" "$@"
}

build_one() {
	arch=$1
	arch_vars "$arch"
	B=$BUILD/$arch
	KB=$B/kbuild
	SYSROOT=$B/sysroot
	O=$OUT/$arch
	mkdir -p "$KB" "$SYSROOT" "$O"

	log "$arch: headers"
	kmake headers_install INSTALL_HDR_PATH="$SYSROOT"
	nice -n 10 make -s -C "$KSRC/tools/include/nolibc" headers OUTPUT="$B/" >/dev/null

	log "$arch: init"
	# -nostdlib -nostdinc -static as in tools/testing/selftests/nolibc; libgcc only where the
	# compiler has it (init.c avoids 64-bit division on 32-bit targets, so it needs none).
	libgcc=$($UCC $UCFLAGS -print-libgcc-file-name 2>/dev/null || true)
	[ -f "$libgcc" ] || libgcc=
	# shellcheck disable=SC2086
	nice -n 10 $UCC $UCFLAGS -Os -static -nostdlib -nostdinc -s -fno-asynchronous-unwind-tables \
		-fno-ident -fno-stack-protector -Wall -Wextra -I"$SYSROOT/include" \
		-DTINY_ARCH="\"$arch\"" -o "$B/init" "$HERE/init.c" $libgcc
	cat > "$B/initramfs.list" <<EOF
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
file /init $B/init 0755 0 0
EOF

	log "$arch: kernel config"
	kmake tinyconfig >/dev/null
	"$KSRC/scripts/kconfig/merge_config.sh" -m -O "$KB" "$KB/.config" \
		"$HERE/config/common.config" "$HERE/config/$arch.config" >/dev/null
	"$KSRC/scripts/config" --file "$KB/.config" --set-str INITRAMFS_SOURCE "$B/initramfs.list"
	kmake olddefconfig >/dev/null
	check_config "$KB/.config" "$HERE/config/common.config" "$HERE/config/$arch.config"

	log "$arch: kernel ($TARGET, -j$JOBS)"
	kmake -j"$JOBS" "$TARGET"

	cp "$KB/$IMAGE" "$O/kernel"
	cp "$B/init" "$O/init"
	cp "$KB/.config" "$O/config"
	kernel_size=$(wc -c < "$O/kernel")
	init_size=$(wc -c < "$O/init")
	release=$(cat "$KB/include/config/kernel.release")
	printf 'arch=%s release=%s kernel_bytes=%s init_bytes=%s\n' \
		"$arch" "$release" "$kernel_size" "$init_size" | tee "$O/sizes"
}

# Every line of the fragments must have survived olddefconfig (a missing dependency drops it silently).
check_config() {
	cfg=$1
	shift
	bad=0
	for frag in "$@"; do
		grep -E '^(CONFIG_[A-Z0-9_]+=.*|# CONFIG_[A-Z0-9_]+ is not set)$' "$frag" | while IFS= read -r line; do
			case "$line" in
			"# "*)
				sym=${line#\# }; sym=${sym%% *}
				if grep -q "^$sym=" "$cfg"; then log "wanted unset, is set: $sym"; echo bad; fi ;;
			*)
				if ! grep -qxF "$line" "$cfg"; then log "not in .config: $line"; echo bad; fi ;;
			esac
		done
	done | grep -q bad && bad=1
	[ "$bad" = 0 ] || { log "config fragment not applied (see above)"; exit 1; }
}

[ $# -gt 0 ] || set -- all
kernel_source
for a in "$@"; do
	if [ "$a" = all ]; then
		for b in $ALL; do build_one "$b"; done
	else
		build_one "$a"
	fi
done
