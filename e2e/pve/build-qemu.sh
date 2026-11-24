#!/bin/sh
# Builds qemu-system-x86_64 and qemu-system-aarch64 from a pull request's pve-qemu tree, for the
# boot test (e2e.yml, job `boot`) when the pull request changes the pve-qemu build: no workflow
# builds the pve-qemu-kvm package on a pull request (hours), so the two binaries the boot test
# starts are built from the tree dpkg-source would build and copied over the published package's.
# The firmware, keymaps and option ROMs stay the published package's.
#
# Runs in the e2e PVE image (its apt sources include the Proxmox repository, for
# libproxmox-backup-qemu0-dev):
#
#   docker run --rm --entrypoint sh -v "$PWD:/src" wsh-pve-e2e:boot /src/e2e/pve/build-qemu.sh \
#       /src/submodules/pve-qemu /src/build/boot-qemu
#
#   <pve-qemu>  submodules/pve-qemu with pve-qemu.patch applied and its qemu submodule checked out;
#               debian/patches/series is applied here (quilt, no fuzz) unless it already is
#   <build dir> where the binaries end up (<build dir>/qemu-system-x86_64, ...-aarch64)
#
# The paths, suffix and the options qemu-server's commands need (io_uring and native AIO for the
# drives, VNC, iSCSI for -iscsi, seccomp) are debian/rules'; the rest of its options are left out.
set -eu
PVE_QEMU=$(cd "$1" && pwd)
BUILD=$2
JOBS=${JOBS:-$(nproc)}

# pve-manager adds the enterprise repository, which needs a subscription (401 without one)
rm -f /etc/apt/sources.list.d/pve-enterprise.sources
apt-get update -qq
apt-get install -y -qq --no-install-recommends build-essential ninja-build python3 python3-venv pkg-config \
	libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libpng-dev libslirp-dev flex bison \
	libsystemd-dev uuid-dev libproxmox-backup-qemu0-dev liburing-dev libaio-dev libiscsi-dev \
	libseccomp-dev libnuma-dev libzstd-dev quilt git >/dev/null
# git for the meson wraps configure fetches (keycodemapdb, berkeley-softfloat-3, ...)
git config --global --add safe.directory '*'

cd "$PVE_QEMU/qemu"
if ! QUILT_PATCHES=../debian/patches quilt applied >/dev/null 2>&1; then
	QUILT_PATCHES=../debian/patches quilt push -a -q --fuzz=0
fi

mkdir -p "$BUILD"
cd "$BUILD"
[ -f build.ninja ] || "$PVE_QEMU/qemu/configure" \
	--prefix=/usr --datadir=/usr/share --sysconfdir=/etc --localstatedir=/var \
	--libexecdir=/usr/lib/kvm --with-suffix=kvm \
	--target-list=x86_64-softmmu,aarch64-softmmu \
	--with-pkgversion="pve-qemu-kvm_boot-test" \
	--disable-docs --disable-werror --disable-gtk --disable-sdl --disable-opengl --disable-capstone \
	--enable-linux-aio --enable-linux-io-uring --enable-libiscsi --enable-seccomp --enable-numa \
	--enable-slirp --enable-png --enable-vnc --enable-zstd
ninja -j"$JOBS" qemu-system-x86_64 qemu-system-aarch64
./qemu-system-x86_64 --version
