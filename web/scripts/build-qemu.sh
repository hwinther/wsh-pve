#!/bin/sh
# Builds QEMU's system emulators for the wasm64 Emscripten host with the TCG interpreter, one
# WebAssembly module per target (qemu-system-sparc, -sparc64, -x86_64, -aarch64): upstream QEMU
# from Debian's source package (the release tarball, Debian patches skipped) plus wsh-pve's sparc
# patches (pve-qemu's debian/patches/wsh/, taken from submodules/pve-qemu.patch) and the page's own
# patches in web/patches/, against the libraries build-deps.sh put in $TARGET.
#
#   build-qemu.sh <work dir> <pve-qemu.patch> <output dir> [native output dir]
#
# Environment: TARGET (as build-deps.sh), JOBS, TARGETS (QEMU targets built with their default
# devices, default sparc-softmmu,sparc64-softmmu,x86_64-softmmu), MINIMAL_TARGETS (targets built in
# a tree of their own with only their configs/devices/<target>/minimal.mak, default
# aarch64-softmmu: the virt board alone), QEMU (source package spec, default qemu=1:11.1.3+ds-2),
# QEMU_VERSION (the upstream version the tree must have, default 11.1.3), WEB_PATCHES (the directory
# of web/patches/*.patch, default /src/web-patches).
set -eu

WORK=$1
PATCH=$2
OUT=$3
TARGET=${TARGET:-/builddeps/target}
JOBS=${JOBS:-$(nproc)}
QEMU=${QEMU:-qemu=1:11.1.3+ds-2}
QEMU_VERSION=${QEMU_VERSION:-11.1.3}
WEB_PATCHES=${WEB_PATCHES:-/src/web-patches}
TARGETS=${TARGETS:-sparc-softmmu,sparc64-softmmu,x86_64-softmmu}
MINIMAL_TARGETS=${MINIMAL_TARGETS-aarch64-softmmu}
# qemu-system-<arch> for each target in a comma-separated list
bins() { echo "$1" | tr , ' ' | sed 's/-softmmu//g; s/\([^ ]*\)/qemu-system-\1/g'; }

export CPATH="$TARGET/include"
export PKG_CONFIG_PATH="$TARGET/lib/pkgconfig"
export EM_PKG_CONFIG_PATH="$PKG_CONFIG_PATH"
export CFLAGS="-O3 -pthread -DWASM_BIGINT"
export CXXFLAGS="$CFLAGS"
export LDFLAGS="-sWASM_BIGINT -sASYNCIFY=1 -L$TARGET/lib"

log() { printf '%s\n' "build-qemu: $*" >&2; }

mkdir -p "$WORK" "$OUT"
WORK=$(cd "$WORK" && pwd)
PATCH=$(cd "$(dirname "$PATCH")" && pwd)/$(basename "$PATCH")
OUT=$(cd "$OUT" && pwd)

# The source: Debian's orig tarball is the upstream release tarball (with the meson subprojects QEMU
# needs offline: berkeley-softfloat-3, keycodemapdb) less some prebuilt firmware (+ds).
rm -rf "$WORK/qemu"
mkdir -p "$WORK/qemu"
cd "$WORK/qemu"
apt-get source -qq --download-only "$QEMU" >/dev/null 2>&1 || apt-get source --download-only "$QEMU"
dsc=$(ls ./*.dsc)
dpkg-source -x --skip-patches "$dsc" src >/dev/null
ver=$(cat src/VERSION)
[ "$ver" = "$QEMU_VERSION" ] || { log "source is QEMU $ver, want $QEMU_VERSION"; exit 1; }
log "qemu $(sed -n 's/^Version: //p' "$dsc") (upstream $ver)"

# The wsh patches, in the order of pve-qemu's series file (all of them apply to upstream with no
# fuzz; the Proxmox ones before them in the package's series are left out).
rm -rf "$WORK/pve-qemu" "$WORK"/build-* "$WORK"/native-*
mkdir -p "$WORK/pve-qemu"
cd "$WORK/pve-qemu"
git init -q .
# The patch files are new files in pve-qemu.patch, so they apply without pve-qemu's tree; the
# series file is a change to it, so its wsh entries are read from the patch text.
git apply --include='debian/patches/wsh/*' "$PATCH" 2>/dev/null
sed -n 's|^+\(wsh/[^ ]*\.patch\)$|\1|p' "$PATCH" > "$WORK/wsh-series"
n=0
cd "$WORK/qemu/src"
while read -r p; do
	patch -p1 --fuzz=0 --no-backup-if-mismatch -s < "$WORK/pve-qemu/debian/patches/$p" || { log "$p does not apply"; exit 1; }
	n=$((n + 1))
done < "$WORK/wsh-series"
[ "$n" -gt 0 ] || { log "no wsh patches found in $PATCH"; exit 1; }
log "$n wsh patches applied (last: $(tail -n 1 "$WORK/wsh-series"))"

# The page's own patches (web/patches/, each says why), after the wsh series. They go into the native
# build below as well: the snapshot's migration stream must come from the same device models.
m=0
for p in "$WEB_PATCHES"/*.patch; do
	[ -f "$p" ] || continue
	patch -p1 --fuzz=0 --no-backup-if-mismatch -s < "$p" || { log "$(basename "$p") does not apply"; exit 1; }
	m=$((m + 1))
	log "web patch applied: $(basename "$p")"
done

# QEMU unpacks its compressed EDK2 images (pc-bios/edk2-*.fd.bz2) for the Arm and x86 targets
# whenever bzip2 is installed, and --disable-install-blobs doesn't stop it; Debian's +ds tarball has
# none of them (Debian builds EDK2 separately), and the page boots without UEFI. Not a change to
# QEMU itself, so a sed here rather than a web patch.
grep -q '^ *unpack_edk2_blobs = bzip2\.found()$' meson.build || { log "meson.build: no edk2 unpack line"; exit 1; }
sed -i 's/^\( *unpack_edk2_blobs = \)bzip2\.found()$/\1false/' meson.build

# Configure as QEMU's CI wasm64 jobs do (--static --cpu=wasm64 --disable-tools
# --enable-tcg-interpreter), without optional features (no display, audio, network or image formats
# beyond the defaults the build needs) but libfdt, which the Arm virt machine needs. Each target
# links into a module of its own, so a machine's page loads only its own. The targets with their
# default devices share one tree; MINIMAL_TARGETS get one of their own with only the boards and
# devices of their minimal.mak (--without-default-devices applies to every target of a tree): the
# Arm target's default set is every Arm board QEMU has, 52 MB of WebAssembly against 26.5 with
# the virt board alone. No firmware blobs: Debian's +ds tarball has none, and the page brings its
# own.
#
# QEMU tests EMSCRIPTEN (in configure and the sources); Emscripten 4.0.10, which QEMU's CI uses,
# still defined it next to __EMSCRIPTEN__, Emscripten 6 defines only the latter. It goes in through
# EMCC_CFLAGS, which emcc adds to every call: meson ignores CFLAGS in a cross build, and QEMU's
# configs/meson/emscripten.txt, read after configure's cross file, replaces its c_args.
#
# tree_flags <minimal>: the device options of a tree
tree_flags() {
	if [ "$1" = minimal ]; then
		echo "--without-default-devices"
		for t in $(echo "$MINIMAL_TARGETS" | tr , ' '); do echo "--with-devices-${t%-softmmu}=minimal"; done
	fi
}
export EMCC_CFLAGS="-DEMSCRIPTEN=1"
for tree in default minimal; do
	targets=$TARGETS
	[ "$tree" = default ] || targets=$MINIMAL_TARGETS
	[ -n "$targets" ] || continue
	mkdir -p "$WORK/build-$tree"
	cd "$WORK/build-$tree"
	# shellcheck disable=SC2046
	emconfigure ../qemu/src/configure --static --cpu=wasm64 --disable-tools --enable-tcg-interpreter \
		--target-list="$targets" $(tree_flags "$tree") --without-default-features --enable-fdt=system \
		--disable-docs --disable-werror --disable-debug-info --disable-download --disable-install-blobs \
		--with-pkgversion="wsh-pve wasm" ||
		{ cat config.log meson-logs/meson-log.txt 2>/dev/null | tail -50; exit 1; }
	# shellcheck disable=SC2046
	emmake ninja -j"$JOBS" $(for b in $(bins "$targets"); do echo "$b.js"; done)
	for b in $(bins "$targets"); do
		cp "$b.js" "$b.wasm" "$OUT/"
		[ ! -f "$b.worker.js" ] || cp "$b.worker.js" "$OUT/"
	done
done
{
	echo "qemu $ver + $n wsh patches + $m web patches ($(sed -n 's/^Version: //p' "$WORK/qemu/$dsc"))"
	echo "emscripten $(emcc --version | head -n 1 | sed 's/.*) \([0-9.]*\).*/\1/')"
	cat "$TARGET/versions"
} > "$OUT/versions.txt"
ls -l "$OUT" >&2

# With a fourth argument: native emulators from the same trees, for the snapshots the page
# starts from (make-snapshot.py). A migration stream loads only into the same QEMU version and
# device set, so they are built from exactly these sources, patches and device options; TCG or TCI
# doesn't matter.
if [ -n "${4:-}" ]; then
	NATIVE=$4
	mkdir -p "$NATIVE"
	for tree in default minimal; do
		targets=$TARGETS
		[ "$tree" = default ] || targets=$MINIMAL_TARGETS
		[ -n "$targets" ] || continue
		mkdir -p "$WORK/native-$tree"
		cd "$WORK/native-$tree"
		# shellcheck disable=SC2046
		env -u EMCC_CFLAGS CFLAGS= LDFLAGS= CPATH= PKG_CONFIG_PATH= ../qemu/src/configure \
			--target-list="$targets" $(tree_flags "$tree") --without-default-features \
			--enable-fdt=system --disable-docs --disable-werror --disable-tools --disable-download \
			--disable-install-blobs --with-pkgversion="wsh-pve native" >/dev/null ||
			{ tail -50 meson-logs/meson-log.txt; exit 1; }
		# shellcheck disable=SC2046
		ninja -j"$JOBS" $(bins "$targets") >/dev/null
		for b in $(bins "$targets"); do cp "$b" "$NATIVE/"; done
	done
	log "native emulators for the snapshots in $NATIVE: $(ls "$NATIVE" | tr '\n' ' ')"
fi
