#!/usr/bin/env bash
# The qemu-3dfx Glide pass-through from DOS (e2e/3dfx/dos/): FreeDOS 1.4 from its boot floppy, our
# DJGPP test program and qemu-3dfx's DOS wrapper GLIDE2X.DXE, with free software only. Builds the
# test image (the program in the DJGPP image, the published pve-qemu-kvm and wsh-openglide), fetches
# the guest drivers that match the binary under test (the qemu-3dfx-drivers-<rev> release of this
# repository) and runs the harness (dos_test.py) in a container. See the 3dfx guide, "DOS games".
# Each boot ends with wshspace -audiotest on an SB16 (-device sb16, -audiodev wav), the audio
# signature checked by e2e/audio/wavcheck.py (--no-space-audio after -- leaves it out).
#
#   e2e/3dfx/dos-test.sh --out OUT [options] [-- harness options]
#
#   --out DIR         the summary, logs and screendumps (FreeDOS and the test scene only)
#   --qemu-bin FILE   test this qemu-system-x86_64-3dfx (e.g. scripts/check-qemu-3dfx-build.sh --out)
#                     instead of the published pve-qemu-kvm's; it is installed over the published one
#   --drivers ZIP     the guest drivers (default: gh release download qemu-3dfx-drivers-<rev>, the
#                     revision the binary names; needs gh and a token, GH_TOKEN in CI)
#   --freedos-zip ZIP the FreeDOS 1.4 Floppy Edition (FD14-FloppyEdition.zip), checked against its pin
#                     (e2e/sparc/targets_dos.py); default: downloaded into OUT/.freedos-cache. CI gives
#                     the one it restored from the Actions cache (e2e/sparc/fetch_media.py)
#   --image NAME      the test image's tag (default wsh-3dfx-dos:local); --no-build uses it as it is
#   --docker CMD      docker or podman (default docker)
#   --pve CONTAINER   PVE starts the VM: run the harness in this PVE container (e2e/pve/Dockerfile,
#                     privileged) with `qm create`/`qm start`; OUT must be bind-mounted into it at the
#                     same path. The program and the harness are copied in from the test image,
#                     mtools is installed with apt
#   --vmid N          the VM's ID with --pve (default 9397; must be free)
#
# Harness options after --: --profiles none,xms,emm386 (default all three), --accel auto|tcg|kvm,
# --cpu, --bench N, --hold S, --timeout S, --dxe FILE; see dos_test.py --help. /dev/kvm is passed to
# the container when it exists; FreeDOS is cached in OUT/.freedos-cache. Exit status: the harness's
# (0 all passed, 1 a profile failed, 2 setup, 77 the binary has no qemu-3dfx or can't show it headless).
set -euo pipefail

top=$(cd "$(dirname "$0")/../.." && pwd)
out="" qbin="" drivers="" fdzip="" image="wsh-3dfx-dos:local" build=1 docker=docker pve="" vmid=9397
die() { echo "dos-test.sh: $*" >&2; exit 2; }
while [ $# -gt 0 ]; do
    case "$1" in
        --out) out=${2:?}; shift 2 ;;
        --qemu-bin) qbin=${2:?}; shift 2 ;;
        --drivers) drivers=${2:?}; shift 2 ;;
        --freedos-zip) fdzip=${2:?}; shift 2 ;;
        --image) image=${2:?}; shift 2 ;;
        --no-build) build=0; shift ;;
        --docker) docker=${2:?}; shift 2 ;;
        --pve) pve=${2:?}; shift 2 ;;
        --vmid) vmid=${2:?}; shift 2 ;;
        --) shift; break ;;
        -h | --help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; exit 0 ;;
        *) die "unknown option '$1' (harness options go after --)" ;;
    esac
done
[ -n "$out" ] || die "--out is required"
[ -z "$qbin" ] || [ -x "$qbin" ] || die "no executable $qbin"
[ -z "$fdzip" ] || [ -r "$fdzip" ] || die "no FreeDOS zip at $fdzip"
[ -f "$top/submodules/qemu-3dfx/wrappers/3dfx/dxe/glidedxe.c" ] \
    || die "submodules/qemu-3dfx isn't checked out (git submodule update --init submodules/qemu-3dfx)"
mkdir -p "$out"
out=$(cd "$out" && pwd)

if [ "$build" = 1 ]; then
    # --pull refreshes only the base image; the layer that installs pve-qemu-kvm and wsh-openglide
    # stays cached until WSH_PACKAGES changes (see win98-test.sh)
    pkgs=$(curl -fsS https://debian.wshosting.no/debian/dists/trixie/main/binary-amd64/Packages 2> /dev/null \
        | awk '/^Package: (pve-qemu-kvm|wsh-openglide)$/ { p = $2 } /^Version:/ && p { printf "%s=%s ", p, $2; p = "" }') || true
    [ -n "$pkgs" ] || pkgs="unknown-$(date +%s)"
    rev_src=$(git -C "$top/submodules/qemu-3dfx" rev-parse --short=7 HEAD 2> /dev/null || echo 0000000)
    echo "dos-test: building the image for: $pkgs (qemu-3dfx submodule $rev_src)"
    "$docker" build --build-arg "WSH_PACKAGES=$pkgs" --build-arg "QEMU3DFX_REV=$rev_src" \
        -f "$top/e2e/3dfx/dos/Dockerfile" -t "$image" "$top"
fi

mounts=(-v "$out:/dos-out")
install=""
if [ -n "$qbin" ]; then
    qbin=$(cd "$(dirname "$qbin")" && pwd)/$(basename "$qbin")
    mounts+=(-v "$qbin:/dos-in/qemu-system-x86_64-3dfx:ro")
    # in the published binary's place: QEMU finds its firmware relative to its own path
    install="install -m 755 /dos-in/qemu-system-x86_64-3dfx /usr/bin/qemu-system-x86_64-3dfx && "
fi
run_in_image() { "$docker" run --rm "${mounts[@]}" --entrypoint sh "$image" -c "$install$1"; }
in_pve() { "$docker" exec -i "$pve" "$@"; }
qemu_version() { if [ -n "$pve" ]; then in_pve qemu-system-x86_64-3dfx --version; else run_in_image "qemu-system-x86_64-3dfx --version"; fi; }

if [ -n "$pve" ]; then
    in_pve test -d "$out" || die "the PVE container $pve doesn't see $out (bind-mount it at the same path)"
    if [ -n "$qbin" ]; then
        in_pve sh -c 'cat > /usr/bin/qemu-system-x86_64-3dfx.dos && chmod 755 /usr/bin/qemu-system-x86_64-3dfx.dos &&
            mv /usr/bin/qemu-system-x86_64-3dfx.dos /usr/bin/qemu-system-x86_64-3dfx' < "$qbin"
    fi
fi

# The revision the binary was built from names the guest drivers' release
rev=$(qemu_version | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
if [ -z "$rev" ]; then
    echo "SKIP: the binary has no qemu-3dfx (the optional 3dfx extra is missing)"
    exit 77
fi
if [ -z "$drivers" ]; then
    mkdir -p "$out/release"
    gh release download "qemu-3dfx-drivers-$rev" -R hwinther/wsh-pve -p "qemu-3dfx-drivers-$rev.zip" \
        -D "$out/release" --clobber
    drivers=$out/release/qemu-3dfx-drivers-$rev.zip
fi
[ -r "$drivers" ] || die "no guest drivers at $drivers"
drivers=$(cd "$(dirname "$drivers")" && pwd)/$(basename "$drivers")
echo "qemu-3dfx $rev, guest drivers $(basename "$drivers")"

if [ -n "$pve" ]; then
    # The program and the harness from the image; mtools from apt (the image has PVE's enterprise
    # repository too, which refuses a node without a subscription)
    in_pve sh -c 'rm -rf /root/glidedos && mkdir -p /root/glidedos'
    "$docker" run --rm --entrypoint tar "$image" -C /w3d -cf - . | in_pve tar -xf - -C /root/glidedos
    in_pve sh -c 'command -v mcopy > /dev/null || { export DEBIAN_FRONTEND=noninteractive;
        apt-get update -qq 2>&1 | grep -v enterprise.proxmox.com; apt-get install --no-install-recommends --assume-yes -qq mtools > /dev/null; }'
    dname=$(basename "$drivers")
    [ "$drivers" = "$out/$dname" ] || cp "$drivers" "$out/$dname"
    fdenv=()
    if [ -n "$fdzip" ]; then
        # where the PVE container sees it, like the drivers
        mkdir -p "$out/.freedos-cache"
        fdzip=$(cd "$(dirname "$fdzip")" && pwd)/$(basename "$fdzip")
        [ "$fdzip" = "$out/.freedos-cache/$(basename "$fdzip")" ] || cp "$fdzip" "$out/.freedos-cache/"
        fdenv=(FREEDOS_ZIP="$out/.freedos-cache/$(basename "$fdzip")")
    fi
    status=0
    in_pve env FREEDOS_CACHE="$out/.freedos-cache" "${fdenv[@]}" python3 /root/glidedos/e2e/3dfx/dos/dos_test.py --pve "$vmid" \
        --drivers "$out/$dname" --bin /root/glidedos/bin --out "$out" "$@" || status=$?
    in_pve chmod -R a+rX "$out" || true
    exit "$status"
fi

dname=$(basename "$drivers")
mounts+=(-v "$drivers:/dos-in/$dname:ro")
fdenv=()
if [ -n "$fdzip" ]; then
    fdzip=$(cd "$(dirname "$fdzip")" && pwd)/$(basename "$fdzip")
    mounts+=(-v "$fdzip:/dos-in/freedos/$(basename "$fdzip"):ro")
    fdenv=(-e "FREEDOS_ZIP=/dos-in/freedos/$(basename "$fdzip")")
fi
devices=()
[ ! -e /dev/kvm ] || devices=(--device /dev/kvm)
status=0
"$docker" run --rm "${devices[@]}" "${mounts[@]}" -e FREEDOS_CACHE=/dos-out/.freedos-cache "${fdenv[@]}" --entrypoint sh "$image" -c \
    "${install}exec python3 /w3d/e2e/3dfx/dos/dos_test.py --drivers \"/dos-in/$dname\" --bin /w3d/bin \
    --out /dos-out \"\$@\"" dos-test "$@" || status=$?
# the container wrote as root: the summary and logs readable for the caller (an artifact upload)
"$docker" run --rm -v "$out:/dos-out" --entrypoint chmod "$image" -R a+rX /dos-out || true
exit "$status"
