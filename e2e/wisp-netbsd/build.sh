#!/bin/sh
# Builds wisp-netbsd, the NetBSD sibling of wisp, for one or more architectures:
#   ./build.sh [sparc32|sparc64|x86_64|all]...
# Output per architecture in out/<arch>/: kernel (the memory-disk root inside), init (PID 1),
# ramdisk.fs, config (the kernel configuration as built) and sizes; on sparc64 also disk.img, a
# boot disk with NetBSD's own boot loader (see build_bootdisk).
#
# All from NetBSD's own sources ($NETBSDSRCDIR, the release's source sets in the image), as an
# unprivileged user's build (build.sh -U):
#   1. tools: NetBSD's build.sh builds its cross toolchain (gcc, binutils, nbmake, nbconfig,
#      nbmakefs, nbmdsetimage, ...) for the machine. The slow step, kept in build/<arch>/tools and
#      reused while that directory exists.
#   2. libc: the headers, the C startup files (lib/csu), libc and libgcc, installed into
#      build/<arch>/dest, the sysroot PID 1 links against. Also kept.
#   3. init: init.c built static against that libc.
#   4. ramdisk.fs: an FFS image (nbmakefs, from a spec file: no root needed for the device nodes)
#      with /sbin/init, /dev/console and /dev/md0a, plus room for the file check.
#   5. kernel: config/WISP.<machine> with MEMORY_DISK_ROOT_SIZE set to the image's size, built by
#      build.sh kernel=..., the image put in with the tools' mdsetimage, then stripped.
#
# Environment: NETBSDSRCDIR (default /usr/src/netbsd), BUILD (default build/), OUT (default out/),
# JOBS (default 4).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${NETBSDSRCDIR:-/usr/src/netbsd}
BUILD=${BUILD:-$HERE/build}
OUT=${OUT:-$HERE/out}
JOBS=${JOBS:-4}
ALL="sparc32 sparc64 x86_64"
# Room on the memory disk besides PID 1: the file check writes 64 KiB, FFS needs its metadata.
MD_SLACK_KB=256

log() { printf '%s\n' "wisp-netbsd: $*" >&2; }

# Per architecture: NetBSD's MACHINE and the endianness of its FFS images.
arch_vars() {
	case "$1" in
	sparc32) M=sparc ENDIAN=be ;;
	sparc64) M=sparc64 ENDIAN=be ;;
	x86_64) M=amd64 ENDIAN=le ;;
	*) log "unknown architecture: $1 (one of: $ALL)"; exit 2 ;;
	esac
}

# NetBSD's build.sh for this machine: unprivileged (-U), update builds (-u), no warnings as
# errors from the host's newer compiler for the tools (-N1 keeps the log short). The MK* switches
# keep the libraries to the static ones PID 1 needs.
nbuild() {
	nice -n 10 "$SRC/build.sh" -U -u -N1 -j "$JOBS" -m "$M" -O "$B/obj" -T "$B/tools" -D "$B/dest" \
		-V MKPIC=no -V MKPROFILE=no -V MKLINT=no -V MKDEBUG=no -V MKDEBUGLIB=no -V MKCOMPAT=no \
		-V MKSANITIZER=no -V MKCTF=no -V MKMAN=no -V MKINFO=no -V MKNLS=no -V MKHTML=no \
		-V MKREPRO=yes -V MKREPRO_TIMESTAMP=0 "$@"
}

nbmake() {
	nice -n 10 "$B/tools/bin/nbmake-$M" -j "$JOBS" "$@"
}

build_tools() {
	if [ -x "$B/tools/bin/nbmake-$M" ] && [ -f "$B/tools/.wisp-done" ]; then
		log "$arch: tools (kept from an earlier build)"
		return
	fi
	log "$arch: tools (NetBSD build.sh, -j$JOBS)"
	nbuild tools
	touch "$B/tools/.wisp-done"
}

build_libc() {
	if [ -f "$B/dest/.wisp-libc" ]; then
		log "$arch: libc (kept from an earlier build)"
		return
	fi
	log "$arch: headers"
	nbmake -C "$SRC" do-distrib-dirs >/dev/null
	nbmake -C "$SRC" includes >/dev/null
	for dir in lib/csu lib/libc external/gpl3/gcc/lib/libgcc; do
		log "$arch: $dir"
		nbmake -C "$SRC/$dir" obj >/dev/null
		nbmake -C "$SRC/$dir" dependall >/dev/null
		nbmake -C "$SRC/$dir" install >/dev/null
	done
	touch "$B/dest/.wisp-libc"
}

build_init() {
	log "$arch: init"
	"${CROSS}gcc" --sysroot="$B/dest" -static -Os -Wall -Wextra -fno-ident -DWISP_ARCH="\"$arch\"" \
		-o "$B/init" "$HERE/init.c"
	"${CROSS}strip" -s -R .comment "$B/init"
}

# The ramdisk from a spec file: makefs creates the device nodes from it, so no root is needed.
build_ramdisk() {
	log "$arch: ramdisk"
	R=$B/root
	rm -rf "$R"
	mkdir -p "$R/sbin" "$R/dev"
	cp "$B/init" "$R/sbin/init"
	case "$M" in
	amd64) md_block=17 ;;
	*) md_block=5 ;;
	esac
	cat > "$B/ramdisk.spec" <<EOF
/set uid=0 gid=0
. type=dir mode=0755
./dev type=dir mode=0755
./dev/console type=char mode=0600 device=netbsd,0,0
./dev/md0a type=block mode=0640 device=netbsd,$md_block,0
./sbin type=dir mode=0755
./sbin/init type=file mode=0555
EOF
	init_kb=$(( ($(wc -c < "$B/init") + 1023) / 1024 ))
	size_kb=$(( (init_kb + MD_SLACK_KB + 63) / 64 * 64 ))
	rm -f "$B/ramdisk.fs"
	"$B/tools/bin/nbmakefs" -t ffs -B "$ENDIAN" -s "${size_kb}k" -F "$B/ramdisk.spec" -x \
		-T 0 -o bsize=4096,fsize=512,density=8192 "$B/ramdisk.fs" "$R" >/dev/null
	MD_BLOCKS=$(( size_kb * 2 ))
}

build_kernel() {
	log "$arch: kernel (config/WISP.$M, MEMORY_DISK_ROOT_SIZE=$MD_BLOCKS)"
	mkdir -p "$B/conf"
	sed "s/WISP_MD_BLOCKS/$MD_BLOCKS/" "$HERE/config/WISP.$M" > "$B/conf/WISP"
	nbuild kernel="$B/conf/WISP"
	K=$B/obj/sys/arch/$M/compile/WISP/netbsd
	cp "$K" "$B/kernel"
	"${CROSS}mdsetimage" "$B/kernel" "$B/ramdisk.fs"
	"${CROSS}strip" -s "$B/kernel"
	cp "$B/conf/WISP" "$O/config"
}

# sparc64 only: OpenBIOS's -kernel on sun4u starts a Linux image at a fixed address, so the
# kernel boots from a disk instead, the way NetBSD boots on a real sun4u: a Sun disk label with
# partition a over an FFS file system holding ofwboot and the kernel (netbsd), and the Forth
# bootblk (installboot) in the sectors after the label, which the firmware's "boot disk" runs.
build_bootdisk() {
	log "$arch: boot disk (bootblk, ofwboot, kernel)"
	for dir in sys/arch/sparc/stand/ofwboot sys/arch/sparc/stand/bootblk; do
		nbmake -C "$SRC/$dir" obj >/dev/null
		nbmake -C "$SRC/$dir" dependall >/dev/null
	done
	stand=$B/obj/sys/arch/sparc/stand
	D=$B/bootdisk
	rm -rf "$D"
	mkdir -p "$D"
	cp "$stand/ofwboot/ofwboot" "$D/ofwboot"
	cp "$B/kernel" "$D/netbsd"
	cat > "$B/bootdisk.spec" <<EOF
/set uid=0 gid=0
. type=dir mode=0755
./ofwboot type=file mode=0444
./netbsd type=file mode=0444
EOF
	# whole cylinders of 64 sectors (32 KiB) for the label, with 512 KiB of room for FFS
	kb=$(( ($(du -k -c "$D/ofwboot" "$D/netbsd" | tail -n 1 | cut -f 1) + 512 + 31) / 32 * 32 ))
	cyls=$(( kb / 32 ))
	rm -f "$B/disk.img"
	"$B/tools/bin/nbmakefs" -t ffs -B be -s "${kb}k" -F "$B/bootdisk.spec" -x -T 0 \
		-o bsize=8192,fsize=1024 "$B/disk.img" "$D" >/dev/null
	"$B/tools/bin/nbinstallboot" -m sparc64 "$B/disk.img" "$stand/bootblk/bootblk"
	printf 'V nsect 64\nV nhead 1\nV rpm 300\nV pcyl %s\nV ncyl %s\na 0 %s\nc 0 %s\nW\n' \
		"$cyls" "$cyls" $(( cyls * 64 )) $(( cyls * 64 )) | "$B/tools/bin/nbsunlabel" -nq "$B/disk.img"
	cp "$B/disk.img" "$O/disk.img"
}

build_one() {
	arch=$1
	arch_vars "$arch"
	B=$BUILD/$arch
	O=$OUT/$arch
	mkdir -p "$B" "$O"
	build_tools
	# The cross tools' prefix, e.g. .../tools/bin/sparc--netbsdelf- (gcc, strip, mdsetimage)
	CROSS=$(ls "$B"/tools/bin/*--netbsd*-gcc | head -n 1)
	CROSS=${CROSS%gcc}
	build_libc
	build_init
	build_ramdisk
	build_kernel
	cp "$B/init" "$B/ramdisk.fs" "$O/"
	cp "$B/kernel" "$O/kernel"
	disk_field=
	if [ "$M" = sparc64 ]; then
		build_bootdisk
		disk_field=" disk_bytes=$(wc -c < "$O/disk.img")"
	fi
	printf 'arch=%s machine=%s release=%s kernel_bytes=%s ramdisk_bytes=%s init_bytes=%s%s\n' \
		"$arch" "$M" "${NETBSD_VERSION:-unknown}" "$(wc -c < "$O/kernel")" \
		"$(wc -c < "$O/ramdisk.fs")" "$(wc -c < "$O/init")" "$disk_field" | tee "$O/sizes"
}

[ $# -gt 0 ] || set -- all
for a in "$@"; do
	if [ "$a" = all ]; then
		for b in $ALL; do build_one "$b"; done
	else
		build_one "$a"
	fi
done
