#!/usr/bin/env bash
# Builds the 3dfx binary of pve-qemu-kvm the cheap way: only qemu-system-x86_64, from the tree the
# package build uses for it, and says whether it has qemu-3dfx in it. For a qemu-3dfx promotion PR
# (and any PR that changes the qemu-3dfx pin or its port), instead of a full `make pve-qemu-bundle`.
#
# The tree is the one `make pve-qemu-3dfx` builds: the QEMU commit pve-qemu points at, with the
# patches of debian/patches/series after pve-qemu.patch (scripts/refresh-qemu-3dfx-patch.sh --check
# --keep), submodules/pve-qemu-qemu-3dfx.patch on top, qemu-3dfx's hw/3dfx and hw/mesa copied in,
# submodules/qemu-3dfx.patch applied to them and the revision stamped. It is configured by
# debian/rules itself (same configure options and CFLAGS as the package), with the target list cut
# down to x86_64-softmmu, and only qemu-system-x86_64 is built. scripts/check-qemu-extras.sh then
# checks the binary for the qemu-3dfx banner and revision, as the package build does.
#
#   scripts/check-qemu-3dfx-build.sh [options]
#
#   --work DIR     where the tree goes (default: build/qemu-3dfx-build)
#   --jobs N       parallel compile jobs (default: the number of CPUs)
#   --image IMAGE  build image (default: the Makefile's DOCKER_BUILD_IMAGE)
#   --docker CMD   docker or podman (default: docker)
#   --keep         leave the tree (and the build directory in it) when done
#
# Needs submodules/pve-qemu with its qemu submodule, and submodules/qemu-3dfx, checked out; docker,
# git and patch on the host; network for `meson subprojects download`. The container runs as the
# calling user, so the tree stays removable.
# Prints `check-qemu-3dfx-build: PASS ...` or `check-qemu-3dfx-build: FAIL (<stage>) ...` last.
# Exit status: 0 the binary built and has qemu-3dfx, 1 it doesn't (the stage says why), 2 setup error.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
pve="$top/submodules/pve-qemu"
q3="$top/submodules/qemu-3dfx"
work="$top/build/qemu-3dfx-build" jobs="" image="" docker=docker keep=0

usage() {
    sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --work) work="${2:?}"; shift 2 ;;
        --jobs) jobs="${2:?}"; shift 2 ;;
        --image) image="${2:?}"; shift 2 ;;
        --docker) docker="${2:?}"; shift 2 ;;
        --keep) keep=1; shift ;;
        -h|--help) usage ;;
        *) echo "check-qemu-3dfx-build: unknown option '$1'" >&2; usage ;;
    esac
done

die() { echo "check-qemu-3dfx-build: $*" >&2; exit 2; }
fail() {
    echo "check-qemu-3dfx-build: FAIL ($1) $2"
    exit 1
}

[ -n "$jobs" ] || jobs=$(nproc)
[ -n "$image" ] || image=$(sed -n 's/^DOCKER_BUILD_IMAGE *= *//p' "$top/Makefile")
[ -n "$image" ] || die "no build image (--image)"
[ -d "$q3/qemu-0/hw/3dfx" ] && [ -d "$q3/qemu-1/hw/mesa" ] \
    || die "submodules/qemu-3dfx is not checked out (git submodule update --init submodules/qemu-3dfx)"
case "$work" in /*) ;; *) work="$PWD/$work" ;; esac

qemu="$work/qemu"
cleanup() {
    [ "$keep" = 1 ] && return
    git -C "$pve/qemu" worktree remove --force "$qemu" 2>/dev/null || rm -rf "$qemu"
    git -C "$pve/qemu" worktree prune 2>/dev/null || true
    rm -rf "$work"
}
trap cleanup EXIT
start=$(date +%s)

# 1. The package tree with the port applied (exit 1: it doesn't apply; 2: setup)
rc=0
"$top/scripts/refresh-qemu-3dfx-patch.sh" --check --keep --work "$qemu" || rc=$?
case "$rc" in
    0) ;;
    1) fail apply "submodules/pve-qemu-qemu-3dfx.patch does not apply (scripts/refresh-qemu-3dfx-patch.sh refreshes it)" ;;
    *) die "scripts/refresh-qemu-3dfx-patch.sh --check failed (exit $rc)" ;;
esac

# 2. qemu-3dfx's overlay, our fix-up of it and the revision stamp, as the Makefile does them
rev=$(git -C "$q3" rev-parse HEAD)
cp -r "$q3/qemu-0/hw/3dfx" "$q3/qemu-1/hw/mesa" "$qemu/hw/"
if ! patch -d "$qemu" -p2 -t -N --no-backup-if-mismatch -i "$top/submodules/qemu-3dfx.patch"; then
    fail overlay "submodules/qemu-3dfx.patch does not apply to qemu-3dfx ${rev:0:7}"
fi
sed -i -e "s/\(rev_\[\).*\].*/\1] = \"${rev:0:7}-\"/" \
    "$qemu/system/vl.c" "$qemu/hw/3dfx/g2xfuncs.h" "$qemu/hw/mesa/mglfuncs.h"

# 3. debian/ from pve-qemu's HEAD with pve-qemu.patch applied, configured for x86_64 only
scratch=$(mktemp -d)
git -C "$pve" archive HEAD | tar -x -C "$scratch"
patch -d "$scratch" -p1 -s -t -F0 --no-backup-if-mismatch -i "$top/submodules/pve-qemu.patch" \
    || die "submodules/pve-qemu.patch does not apply to pve-qemu"
rm -rf "$qemu/debian"
cp -r "$scratch/debian" "$qemu/debian"
rm -rf "$scratch"
grep -q -- '--target-list=' "$qemu/debian/rules" || die "debian/rules has no --target-list"
sed -i -e 's/--target-list=[^ ]*/--target-list=x86_64-softmmu/' "$qemu/debian/rules"
# The worktree's .git names a path that doesn't exist in the container; the build doesn't need it
rm -f "$qemu/.git"

# 4. Configure (debian/rules) and build qemu-system-x86_64 in the build image, then check it
echo "check-qemu-3dfx-build: building qemu-system-x86_64 with qemu-3dfx ${rev:0:7} in $image (-j$jobs)"
rc=0
# shellcheck disable=SC2016 # expanded by the shell in the container
"$docker" run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e JOBS="$jobs" \
    -v "$qemu:/work/qemu" -v "$top/scripts:/work/scripts:ro" -w /work/qemu \
    "$image" bash -euo pipefail -c '
        echo "::group::meson subprojects download"
        meson subprojects download --sourcedir . >/dev/null
        echo "::endgroup::"
        echo "::group::configure (debian/rules)"
        make -f debian/rules build/config.status || exit 3
        echo "::endgroup::"
        ninja -C build -j "$JOBS" qemu-system-x86_64 || exit 4
        mkdir -p /tmp/root/usr/bin
        cp build/qemu-system-x86_64 /tmp/root/usr/bin/qemu-system-x86_64-3dfx
        /work/scripts/check-qemu-extras.sh --root /tmp/root --only 3dfx --expect 3dfx || exit 5
    ' || rc=$?
took=$(( $(date +%s) - start ))
case "$rc" in
    0) echo "check-qemu-3dfx-build: PASS qemu-system-x86_64 with qemu-3dfx ${rev:0:7} built in ${took}s" ;;
    3) fail configure "debian/rules could not configure the tree (${took}s)" ;;
    4) fail compile "qemu-system-x86_64 did not build (${took}s; compiler errors above)" ;;
    5) fail binary "qemu-system-x86_64 built but has no qemu-3dfx banner (${took}s)" ;;
    *) fail container "the build container exited with $rc (${took}s)" ;;
esac
