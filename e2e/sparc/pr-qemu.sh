#!/bin/sh
# Builds qemu-system-sparc and qemu-system-sparc64 from a pull request's pve-qemu tree, for the NetBSD
# installs before merge (.github/workflows/sparc-lab-pr-qemu.yml, e2e/sparc/README.md "Before
# merge"). Runs as root in the lab image (e2e/sparc/Dockerfile): its apt sources have the Proxmox
# repository for libproxmox-backup-qemu0-dev, and its pve-qemu-kvm brings the runtime libraries, so
# the binaries run in the lab image (pr-qemu.Dockerfile puts them there).
#
#   pr-qemu.sh <pve-qemu tree> <build dir> <output dir>
#
# <pve-qemu tree>: submodules/pve-qemu at the pull request's pin with submodules/pve-qemu.patch
# applied and its qemu submodule checked out. Every patch of debian/patches/series is pushed onto
# its qemu tree with quilt and no fuzz (as dpkg-source would apply them; one that doesn't apply
# fails the build), then only the two sparc targets are configured and built.
#
# Environment: JOBS (default: nproc), PKGVERSION (the suffix `--version` shows, default wsh-pr),
# CCACHE_DIR (when set, the compiler runs through ccache with that cache).
# Output: <output dir>/qemu-system-sparc, qemu-system-sparc64 and qemu-version.txt (their --version).
set -eu
TREE=$(cd "$1" && pwd)
mkdir -p "$2" "$3"
BUILD=$(cd "$2" && pwd)
OUT=$(cd "$3" && pwd)
JOBS=${JOBS:-$(nproc)}
PKGVERSION=${PKGVERSION:-wsh-pr}

log() { printf '%s\n' "pr-qemu: $*" >&2; }

apt-get update -qq
# quilt for the series, git for the meson wraps configure fetches (keycodemapdb, ...)
apt-get install -y -qq --no-install-recommends build-essential ninja-build python3 python3-venv pkg-config \
	libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libpng-dev libslirp-dev flex bison \
	libsystemd-dev uuid-dev libproxmox-backup-qemu0-dev quilt git ccache >/dev/null
git config --global --add safe.directory '*'

cd "$TREE/qemu"
[ -f VERSION ] || { log "$TREE/qemu has no QEMU tree (qemu submodule not checked out?)"; exit 1; }
export QUILT_PATCHES=../debian/patches
n=$(grep -cv '^[[:space:]]*\(#\|$\)' "$QUILT_PATCHES/series")
# (quilt unapplied fails once the whole series is in: a second run on the same tree)
if quilt unapplied >/dev/null 2>&1 && ! quilt push -a -q --fuzz=0 >/tmp/quilt.log 2>&1; then
	tail -n 20 /tmp/quilt.log >&2
	log "the series doesn't apply: $(quilt next 2>/dev/null || echo '?') fails"
	exit 1
fi
log "QEMU $(cat VERSION): $n patches applied, last $(quilt top)"

cc=gcc
if [ -n "${CCACHE_DIR:-}" ]; then
	mkdir -p "$CCACHE_DIR"
	export CCACHE_DIR CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-600M}" CCACHE_NOHASHDIR=1 CCACHE_BASEDIR="$TREE"
	ccache -z >/dev/null
	cc="ccache gcc"
fi

cd "$BUILD"
nice -n 10 "$TREE/qemu/configure" --target-list=sparc-softmmu,sparc64-softmmu --cc="$cc" \
	--disable-docs --disable-werror --disable-gtk --disable-sdl --disable-opengl --disable-capstone \
	--enable-png --enable-slirp --with-pkgversion="$PKGVERSION" >/dev/null
nice -n 10 ninja -j"$JOBS" qemu-system-sparc qemu-system-sparc64
[ -z "${CCACHE_DIR:-}" ] || ccache -s >&2 || true

cp qemu-system-sparc qemu-system-sparc64 "$OUT/"
for b in qemu-system-sparc qemu-system-sparc64; do
	"$OUT/$b" --version | head -n 1
done > "$OUT/qemu-version.txt"
cat "$OUT/qemu-version.txt" >&2
