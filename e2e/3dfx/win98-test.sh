#!/usr/bin/env bash
# The qemu-3dfx pass-through in a real Windows 98 SE guest (e2e/3dfx/win98/): builds the test image,
# fetches the guest drivers that match the binary under test (the qemu-3dfx-drivers-<rev> release of
# this repository) and runs the harness (win98_test.py) in a container. The Windows disk is the
# operator's own, installed in a PVE VM with `cpu: pentium3`, 512 MB, `scsihw: lsi` with the disk on
# scsi0, `vga: std,mesa=1`, an rtl8139 NIC and AC97 (raw, one FAT32 partition); it is only read, and
# nothing from it leaves PRIVATE (see the 3dfx guide, "Testing in Windows 98").
#
#   e2e/3dfx/win98-test.sh --template DISK.raw --out OUT --private PRIVATE [options] [-- harness options]
#
#   --template FILE   the installed Windows 98 SE disk (read only)
#   --out DIR         logs and the summary: our own text only, fit for an upload
#   --private DIR     the disk copy and the screendumps (they show Windows: keep them on this host)
#   --qemu-bin FILE   test this qemu-system-x86_64-3dfx (e.g. scripts/check-qemu-3dfx-build.sh --out)
#                     instead of the published pve-qemu-kvm's; it is installed over the published one
#   --drivers ZIP     the guest drivers (default: gh release download qemu-3dfx-drivers-<rev>, the
#                     revision the binary names; needs gh and a token, GH_TOKEN in CI)
#   --image NAME      the test image's tag (default wsh-3dfx-win98:local); --no-build uses it as it is
#   --docker CMD      docker or podman (default docker)
#
# Harness options after --: --tests glide2,glide3,opengl (default auto), --display sdl (starts Xvfb),
# --accel tcg|kvm, --cpu, --bench N, --timeout S; see win98_test.py --help. /dev/kvm is passed to
# the container when it exists. Exit status: the harness's (0 all passed, 1 a test failed, 2 setup,
# 77 the binary has no qemu-3dfx or can't show it headless).
set -euo pipefail

top=$(cd "$(dirname "$0")/../.." && pwd)
template="" out="" priv="" qbin="" drivers="" image="wsh-3dfx-win98:local" build=1 docker=docker
die() { echo "win98-test.sh: $*" >&2; exit 2; }
while [ $# -gt 0 ]; do
    case "$1" in
        --template) template=${2:?}; shift 2 ;;
        --out) out=${2:?}; shift 2 ;;
        --private) priv=${2:?}; shift 2 ;;
        --qemu-bin) qbin=${2:?}; shift 2 ;;
        --drivers) drivers=${2:?}; shift 2 ;;
        --image) image=${2:?}; shift 2 ;;
        --no-build) build=0; shift ;;
        --docker) docker=${2:?}; shift 2 ;;
        --) shift; break ;;
        -h | --help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; exit 0 ;;
        *) die "unknown option '$1' (harness options go after --)" ;;
    esac
done
if [ -z "$template" ] || [ -z "$out" ] || [ -z "$priv" ]; then die "--template, --out and --private are required"; fi
[ -f "$template" ] || die "no template file at $template (docker reads it, so it may be root-only)"
[ -z "$qbin" ] || [ -x "$qbin" ] || die "no executable $qbin"
mkdir -p "$out" "$priv"
out=$(cd "$out" && pwd)
priv=$(cd "$priv" && pwd)
template=$(cd "$(dirname "$template")" && pwd)/$(basename "$template")

if [ "$build" = 1 ]; then
    # --pull: the newest published pve-qemu-kvm and wsh-openglide
    "$docker" build --pull -f "$top/e2e/3dfx/win98/Dockerfile" -t "$image" "$top"
fi

mounts=(-v "$template:/w3d-in/template.raw:ro" -v "$out:/w3d-out" -v "$priv:/w3d-private")
install=""
if [ -n "$qbin" ]; then
    qbin=$(cd "$(dirname "$qbin")" && pwd)/$(basename "$qbin")
    mounts+=(-v "$qbin:/w3d-in/qemu-system-x86_64-3dfx:ro")
    # in the published binary's place: QEMU finds its firmware relative to its own path
    install="install -m 755 /w3d-in/qemu-system-x86_64-3dfx /usr/bin/qemu-system-x86_64-3dfx && "
fi
run_in_image() { "$docker" run --rm "${mounts[@]}" --entrypoint sh "$image" -c "$install$1"; }

# The revision the binary was built from names the guest drivers' release
rev=$(run_in_image "qemu-system-x86_64-3dfx --version" | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
if [ -z "$rev" ]; then
    echo "SKIP: the binary has no qemu-3dfx (the optional 3dfx extra is missing)"
    exit 77
fi
if [ -z "$drivers" ]; then
    mkdir -p "$priv/release"
    gh release download "qemu-3dfx-drivers-$rev" -R hwinther/wsh-pve -p "qemu-3dfx-drivers-$rev.zip" \
        -D "$priv/release" --clobber
    drivers=$priv/release/qemu-3dfx-drivers-$rev.zip
fi
[ -r "$drivers" ] || die "no guest drivers at $drivers"
drivers=$(cd "$(dirname "$drivers")" && pwd)/$(basename "$drivers")
mounts+=(-v "$drivers:/w3d-in/drivers.zip:ro")
echo "qemu-3dfx $rev, guest drivers $(basename "$drivers")"

kvm=()
[ ! -e /dev/kvm ] || kvm=(--device /dev/kvm)
xvfb=""
case " $* " in
    *" --display sdl "* | *" --display=sdl "*)
        # -extension Composite: a 32-bit visual gives BadMatch (e2e/3dfx/test.sh); a screen larger than
        # the guest's desktop, or the SDL window comes out smaller than it
        xvfb="(Xvfb :42 -screen 0 1920x1200x24 -extension Composite -nolisten tcp > /w3d-out/xvfb.log 2>&1 &) && sleep 2 && export DISPLAY=:42 SDL_VIDEODRIVER=x11 && "
        ;;
esac
status=0
"$docker" run --rm "${kvm[@]}" "${mounts[@]}" --entrypoint sh "$image" -c \
    "$install${xvfb}exec python3 /w3d/e2e/3dfx/win98/win98_test.py --template /w3d-in/template.raw \
    --drivers /w3d-in/drivers.zip --out /w3d-out --private /w3d-private \"\$@\"" win98-test "$@" || status=$?
# the container wrote as root: the summary and logs readable for the caller (an artifact upload)
"$docker" run --rm -v "$out:/w3d-out" --entrypoint chmod "$image" -R a+rX /w3d-out || true
exit "$status"
