#!/usr/bin/env bash
# Checks or refreshes submodules/pve-qemu-qemu-3dfx.patch, our port of qemu-3dfx's QEMU patch
# (submodules/qemu-3dfx/00-qemu*-mesa-glide.patch, made for an older QEMU) to the QEMU in pve-qemu.
# In the package it is the quilt patch wsh/0099-WSH-qemu-3dfx.patch, applied after Proxmox's patches
# and ours (pve-qemu.patch adds wsh/0001...), so this rebuilds that tree: the QEMU commit pve-qemu's
# HEAD points at, with every patch of debian/patches/series (after pve-qemu.patch) applied the way
# dpkg-source does it (no fuzz), in a git worktree of submodules/pve-qemu/qemu.
#
#   scripts/refresh-qemu-3dfx-patch.sh            refresh: apply the patch and rewrite it from the
#                                                 result (new line numbers and context)
#   scripts/refresh-qemu-3dfx-patch.sh --check    only say whether it applies (what the package build
#                                                 needs); changes nothing
#   scripts/refresh-qemu-3dfx-patch.sh --continue rewrite the patch from the work tree, once the
#                                                 conflicts of a failed refresh are resolved there
#
#   --work DIR   where the QEMU work tree goes (default: build/qemu-3dfx-refresh/qemu)
#   --keep       with --check: when the patch applies, leave the work tree with it applied (for
#                scripts/check-qemu-3dfx-build.sh, which compiles it); remove it with
#                `git -C submodules/pve-qemu/qemu worktree remove --force DIR`
#
# When the patch doesn't apply, refresh merges it with `git apply --3way` (the patch's index lines
# name blobs of the QEMU repository) and leaves the work tree with conflict markers: resolve them,
# port whatever QEMU renamed (the 3dfx/mesa overlay in submodules/qemu-3dfx/qemu-{0,1}/hw is copied
# over as is by the Makefile, so the patch has to keep the names it calls, like
# graphic_hw_passthrough), then run --continue. `make pve-qemu-3dfx` builds the result.
#
# Needs submodules/pve-qemu and its qemu submodule checked out (`make restore-pve-qemu`); the
# pve-qemu work tree may have pve-qemu.patch applied or not, the series comes from its HEAD.
# Exit status: 0 applies (or refreshed), 1 doesn't apply (or conflicts left), 2 usage or setup error.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
pve="$top/submodules/pve-qemu"
patch_file="$top/submodules/pve-qemu-qemu-3dfx.patch"
series_name="wsh/0099-WSH-qemu-3dfx.patch"
mode=refresh work="$top/build/qemu-3dfx-refresh/qemu" keep=0

usage() {
    sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --check) mode="check"; shift ;;
        --continue) mode="continue"; shift ;;
        --work) work="${2:?}"; shift 2 ;;
        --keep) keep=1; shift ;;
        -h|--help) usage ;;
        *) echo "refresh-qemu-3dfx-patch: unknown option '$1'" >&2; usage ;;
    esac
done

die() { echo "refresh-qemu-3dfx-patch: $*" >&2; exit 2; }
g() { git -c user.name=refresh-qemu-3dfx-patch -c user.email=refresh-qemu-3dfx-patch@localhost \
    -c core.autocrlf=false -c diff.mnemonicPrefix=false -c diff.noprefix=false "$@"; }

# The patch as git writes it against the series (HEAD of the work tree). It keeps the placeholder
# for the qemu-3dfx revision (rev_ in system/vl.c), which the Makefile stamps.
write_patch() {
    g -C "$work" add -A
    g -C "$work" diff --cached HEAD > "$patch_file.new"
    mv "$patch_file.new" "$patch_file"
    echo "refresh-qemu-3dfx-patch: wrote ${patch_file#"$top"/} ($(grep -c '^diff --git' "$patch_file") files)"
}

remove_work() {
    g -C "$pve/qemu" worktree remove --force "$work" 2>/dev/null || rm -rf "$work"
    g -C "$pve/qemu" worktree prune
}

if [ "$mode" = continue ]; then
    case "$(g -C "$work" log -1 --format=%an 2>/dev/null)" in
        refresh-qemu-3dfx-patch) ;;
        *) die "no work tree from a refresh in $work" ;;
    esac
    if grep -rlE '^(<<<<<<<|>>>>>>>)( |$)' --exclude-dir=.git "$work" >/dev/null 2>&1; then
        echo "refresh-qemu-3dfx-patch: conflict markers left in:" >&2
        grep -rlE '^(<<<<<<<|>>>>>>>)( |$)' --exclude-dir=.git "$work" >&2
        exit 1
    fi
    find "$work" \( -name '*.orig' -o -name '*.rej' \) -not -path '*/.git/*' -delete
    write_patch
    remove_work
    exit 0
fi

[ -f "$pve/debian/rules" ] || die "submodules/pve-qemu is not checked out (make restore-pve-qemu)"
[ -e "$pve/qemu/.git" ] || die "submodules/pve-qemu/qemu is not checked out (git -C submodules/pve-qemu submodule update --init qemu)"
qemu_commit=$(g -C "$pve" rev-parse HEAD:qemu)

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

# pve-qemu's HEAD with pve-qemu.patch applied, for debian/patches: the series and the patches in it
g -C "$pve" archive HEAD | tar -x -C "$scratch"
patch -d "$scratch" -p1 -s -t -F0 --no-backup-if-mismatch -i "$top/submodules/pve-qemu.patch" \
    || die "submodules/pve-qemu.patch does not apply to pve-qemu $(g -C "$pve" rev-parse --short HEAD)"

[ ! -e "$work" ] || remove_work
mkdir -p "$(dirname "$work")"
g -C "$pve/qemu" worktree add -q --detach "$work" "$qemu_commit"

n=0
while read -r entry _; do
    case "$entry" in ''|'#'*|"$series_name") continue ;; esac
    patch -d "$work" -p1 -s -t -F0 -N --no-backup-if-mismatch -i "$scratch/debian/patches/$entry" \
        || die "$entry from debian/patches/series does not apply"
    n=$((n + 1))
done < "$scratch/debian/patches/series"
g -C "$work" add -A
g -C "$work" commit -q --no-verify -m "QEMU $(cat "$work/VERSION") with the $n patches of pve-qemu's series"

echo "refresh-qemu-3dfx-patch: QEMU $(cat "$work/VERSION") ($(g -C "$pve" rev-parse --short HEAD:qemu)) + $n patches of debian/patches/series; applying ${patch_file#"$top"/}"
# As dpkg-source applies it: no fuzz. The "patching file"/"FAILED" lines are what
# scripts/report-qemu-extras.sh quotes from the build log.
if patch -d "$work" -p1 -t -F0 -N --no-backup-if-mismatch -r - -i "$patch_file"; then
    applied=1
else
    applied=0
fi

if [ "$mode" = check ]; then
    if [ "$applied" = 1 ]; then
        if [ "$keep" = 1 ]; then
            echo "refresh-qemu-3dfx-patch: ${patch_file#"$top"/} applies (kept in ${work#"$top"/})"
        else
            remove_work
            echo "refresh-qemu-3dfx-patch: ${patch_file#"$top"/} applies"
        fi
        exit 0
    fi
    remove_work
    echo "refresh-qemu-3dfx-patch: ${patch_file#"$top"/} does not apply (scripts/refresh-qemu-3dfx-patch.sh refreshes it)" >&2
    exit 1
fi

if [ "$applied" = 0 ]; then
    g -C "$work" reset -q --hard HEAD
    g -C "$work" clean -qfdx
    if g -C "$work" apply --3way "$patch_file"; then
        echo "refresh-qemu-3dfx-patch: merged without conflicts, check the result before using it"
    else
        echo "refresh-qemu-3dfx-patch: resolve the conflicts in $work, then run $0 --continue" >&2
        exit 1
    fi
fi
write_patch
remove_work
