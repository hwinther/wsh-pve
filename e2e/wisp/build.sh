#!/bin/sh
# Builds wisp, the tiny test system, for one or more architectures:
#   ./build.sh [x86_64|i386|sparc32|sparc64|aarch64|all]...
# Output per architecture in out/<arch>/: kernel (initramfs built in), kernel-t2, optional kernel-net and kernel-fb,
# init (PID 1), resolved configs, sizes, and sysroot.tar.xz (the UAPI and nolibc headers init was built with,
# for the wisp-test action's kit: kit.sh).
#
# Kernel: `make tinyconfig` plus config/common.config and config/<arch>.config, with the initramfs
# (an uncompressed cpio of /init and /dev/console) linked into the image. kernel-t2, for the tier-2
# checks (run.py --tier2), adds config/tier2/common.config and config/tier2/<arch>.config: disk and
# network drivers, devtmpfs, packet sockets, and SMP where the machines have more than one CPU. All
# kernels have the same PID 1: init.c, built static against the kernel's own nolibc
# (tools/include/nolibc) and the kernel's UAPI headers.
#
# Environment: KSRC (an unpacked kernel tree, used as it is; default: unpack /usr/src/linux-source-*.tar.xz into
# build/), BUILD (default build/), OUT (default out/), JOBS (default 4), TIER2 (default 1; 0 skips
# kernel-t2), TIER_FB (default 0; 1 adds kernel-fb on SS-5, sun4u, x86_64 pc and aarch64 virt),
# TIER_NET (default 0; 1 adds kernel-net with the tier-2 drivers and IPv4).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=${BUILD:-$HERE/build}
OUT=${OUT:-$HERE/out}
JOBS=${JOBS:-4}
TIER2=${TIER2:-1}
ALL="x86_64 i386 sparc32 sparc64 aarch64"

log() { printf '%s\n' "wisp: $*" >&2; }

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
	# linux-patches/*.patch, each once: an unpacked tree from before a patch was added gets it too
	for p in "$HERE"/linux-patches/*.patch; do
		[ -e "$p" ] || continue
		name=$(basename "$p")
		grep -qxF "$name" "$KSRC/.wisp-patches" 2>/dev/null && continue
		log "applying $name"
		patch -d "$KSRC" -p1 -s --forward -i "$p"
		echo "$name" >> "$KSRC/.wisp-patches"
	done
}

# Per architecture: kernel ARCH, kernel CROSS_COMPILE, image path in the build tree and make target,
# the compiler and flags for init.
arch_vars() {
	case "$1" in
	aarch64)
		KARCH=arm64 KCROSS=aarch64-linux-gnu- IMAGE=arch/arm64/boot/Image TARGET=Image
		# Match the kernel page size instead of padding init to the 64 KiB linker default.
		UCC=aarch64-linux-gnu-gcc UCFLAGS="-Wl,-z,max-page-size=4096" ;;
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
	rm -f "$O/kernel-t2" "$O/config-t2" "$O/kernel-net" "$O/config-net" "$O/kernel-fb" "$O/config-fb"

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
		-DWISP_ARCH="\"$arch\"" -o "$B/init" "$HERE/init.c" $libgcc
	cat > "$B/initramfs.list" <<EOF
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
file /init $B/init 0755 0 0
EOF

	c1=$HERE/config/common.config c2=$HERE/config/$arch.config
	build_kernel "$KB" kernel config "$c1" "$c2"
	cp "$B/init" "$O/init"
	tar -C "$SYSROOT" -cJf "$O/sysroot.tar.xz" include
	t2_size=-
	if [ "$TIER2" = 1 ]; then
		build_kernel "$B/kbuild-t2" kernel-t2 config-t2 "$c1" "$c2" \
			"$HERE/config/tier2/common.config" "$HERE/config/tier2/$arch.config"
		t2_size=$(wc -c < "$O/kernel-t2")
	fi
	net_size_field=
	if [ "${TIER_NET:-0}" = 1 ]; then
		# Reuse the tier-2 objects after saving its image and resolved config.
		build_kernel "$B/kbuild-t2" kernel-net config-net "$c1" "$c2" \
			"$HERE/config/tier2/common.config" "$HERE/config/tier2/$arch.config" \
			"$HERE/config/tier-net/common.config"
		net_size_field=" kernel_net_bytes=$(wc -c < "$O/kernel-net")"
	fi
	fb_size_field=
	if [ "${TIER_FB:-0}" = 1 ] && [ "$arch" != i386 ]; then
		case "$arch" in
		sparc32|aarch64) driver=$arch ;;
		sparc64|x86_64) driver=bochs ;;
		esac
		build_kernel "$B/kbuild-t2" kernel-fb config-fb "$c1" "$c2" \
			"$HERE/config/tier2/common.config" "$HERE/config/tier2/$arch.config" \
			"$HERE/config/tier-fb/common.config" "$HERE/config/tier-fb/$driver.config"
		fb_size_field=" kernel_fb_bytes=$(wc -c < "$O/kernel-fb")"
	fi
	kernel_size=$(wc -c < "$O/kernel")
	init_size=$(wc -c < "$O/init")
	release=$(cat "$B/kbuild/include/config/kernel.release")
	printf 'arch=%s release=%s kernel_bytes=%s kernel_t2_bytes=%s init_bytes=%s%s%s\n' \
		"$arch" "$release" "$kernel_size" "$t2_size" "$init_size" "$net_size_field" "$fb_size_field" | tee "$O/sizes"
}

# build_kernel <kbuild dir> <image name> <config name> <fragments...>: tinyconfig plus the fragments
# (a later fragment wins over an earlier one), the initramfs, the image into $O.
build_kernel() {
	KB=$1 name=$2 cfgname=$3
	shift 3
	mkdir -p "$KB"
	log "$arch: $name config"
	kmake tinyconfig >/dev/null
	"$KSRC/scripts/kconfig/merge_config.sh" -m -O "$KB" "$KB/.config" "$@" >/dev/null
	"$KSRC/scripts/config" --file "$KB/.config" --set-str INITRAMFS_SOURCE "$B/initramfs.list"
	kmake olddefconfig >/dev/null
	check_config "$KB/.config" "$@"

	log "$arch: $name ($TARGET, -j$JOBS)"
	kmake -j"$JOBS" "$TARGET"
	cp "$KB/$IMAGE" "$O/$name"
	cp "$KB/.config" "$O/$cfgname"
}

# Every line of the fragments must have survived olddefconfig (a missing dependency drops it
# silently); where fragments set the same symbol, the last one counts.
check_config() {
	cfg=$1
	shift
	bad=0
	awk '/^CONFIG_[A-Z0-9_]+=/ { s = $0; sub(/=.*/, "", s); want[s] = $0; order[++n] = s }
		/^# CONFIG_[A-Z0-9_]+ is not set$/ { s = $2; want[s] = $0; order[++n] = s }
		END { for (i = 1; i <= n; i++) if (!(order[i] in seen)) { seen[order[i]] = 1; print want[order[i]] } }' \
		"$@" | while IFS= read -r line; do
		case "$line" in
		"# "*)
			sym=${line#\# }; sym=${sym%% *}
			if grep -q "^$sym=" "$cfg"; then log "wanted unset, is set: $sym"; echo bad; fi ;;
		*)
			if ! grep -qxF "$line" "$cfg"; then log "not in .config: $line"; echo bad; fi ;;
		esac
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
