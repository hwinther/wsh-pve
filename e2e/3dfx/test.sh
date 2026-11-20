#!/bin/sh
# The Glide pass-through end to end without Windows or a game, in a throwaway Debian 13 container (as
# root): the published pve-qemu-kvm's qemu-system-x86_64-3dfx boots a Linux guest whose /init is
# glide-guest (glide-guest.c, linked with qemu-3dfx's own Linux guest wrapper), with an SDL display
# on Xvfb. The guest draws the test scene (packages/wsh-openglide/tests/scene.h) through the glidept
# device into the host's libglide2x.so (wsh-openglide), reads it back through the pass-through and
# checks it; the host checks the same probes in the VM's window while the frame is up.
#
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-openglide:/deb:ro" -v "$OUT:/out" \
#     debian:trixie sh /src/e2e/3dfx/test.sh /deb/wsh-openglide_<version>_amd64.deb /out
#
# /src is this repository with submodules/qemu-3dfx checked out (the guest wrapper's source, at the
# commit the published binary was built from). Without a .deb argument ("-") wsh-openglide comes from
# the apt repository. Everything else is Debian's and the apt repository's: pve-qemu-kvm, Xvfb, Mesa,
# gcc with i386 multilib, and Debian's kernel (amd64, which runs the static i386 /init through its
# IA32 emulation). OUTDIR gets serial.log, qemu.log and window.ppm. GALLIUM_DRIVER picks Mesa's
# renderer (llvmpipe by default; with softpipe the guest's front-buffer read counts too). Exit 0
# when the guest reports PASS and the window matches; 77 when the installed pve-qemu-kvm has no 3dfx
# binary (the optional extra is missing).
set -eu
DEB=${1:?usage: test.sh WSH-OPENGLIDE-DEB|- OUTDIR}
OUT=${2:?usage: test.sh WSH-OPENGLIDE-DEB|- OUTDIR}
SRC=${SRC:-/src}
QEMU=/usr/bin/qemu-system-x86_64-3dfx
TIMEOUT=${TIMEOUT:-240}
export DEBIAN_FRONTEND=noninteractive GALLIUM_DRIVER="${GALLIUM_DRIVER:-llvmpipe}" LIBGL_ALWAYS_SOFTWARE=1
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
mkdir -p "$OUT"

step "packages: pve-qemu-kvm (published), wsh-openglide, Xvfb, Mesa, i386 gcc, Debian's kernel"
apt-get update -qq
apt-get install --no-install-recommends --assume-yes -qq ca-certificates gnupg > /dev/null
cp "$SRC/proxmox-archive-keyring-trixie.gpg" /usr/share/keyrings/proxmox-archive-keyring.gpg
gpg --dearmor < "$SRC/repo/conf/wsh-pve.gpg.key" > /usr/share/keyrings/wsh-pve.gpg
printf 'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n' \
	> /etc/apt/sources.list.d/proxmox.sources
printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
	> /etc/apt/sources.list.d/wsh-pve.sources
printf 'Package: pve-qemu-kvm\nPin: origin debian.wshosting.no\nPin-Priority: 1001\n' > /etc/apt/preferences.d/wsh-pve
apt-get update -qq
[ "$DEB" != - ] || DEB=wsh-openglide
# libegl1: SDL loads libEGL.so.1 for QEMU's window and QEMU stops without it (pve-qemu-kvm doesn't
# depend on it); x11-utils: xdpyinfo, xwininfo
apt-get install --no-install-recommends --assume-yes -qq pve-qemu-kvm "$DEB" xvfb xauth x11-utils \
	libgl1-mesa-dri libegl1 libegl-mesa0 gcc gcc-multilib libc6-dev-i386 libx11-dev cpio linux-image-amd64 > /dev/null
dpkg-query -W -f '${Package} ${Version}\n' pve-qemu-kvm wsh-openglide

if [ ! -x "$QEMU" ]; then
	echo "SKIP: this pve-qemu-kvm has no $QEMU (the optional 3dfx extra is missing)"
	exit 77
fi
# The guest wrapper's revision must be the host binary's ("featuring qemu-3dfx@<rev>-..."): glidept
# refuses a wrapper built from another qemu-3dfx commit
rev=$("$QEMU" --version | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
[ -n "$rev" ] || fail "$QEMU --version names no qemu-3dfx revision"
src_rev=${QEMU3DFX_REV:-} # the submodule's commit (7 digits), when the caller passes it
echo "host binary: qemu-3dfx $rev; guest wrapper source: ${src_rev:-unknown}; Mesa: $GALLIUM_DRIVER"
[ -z "$src_rev" ] || [ "$rev" = "$src_rev" ] \
	|| echo "WARNING: the published binary and the submodule differ; the guest is built from the submodule with the binary's revision"

step "the guest: glide-guest as /init, i386, static"
work=$(mktemp -d)
trap 'kill $(jobs -p) 2> /dev/null || true; rm -rf "$work"' EXIT
mkdir "$work/root"
gcc -m32 -static -O2 -Wall -I"$SRC/submodules/qemu-3dfx/qemu-0/hw/3dfx" -I"$SRC/submodules/qemu-3dfx/wrappers/3dfx/src" \
	-I"$SRC/packages/wsh-openglide/tests" -D__REV__="\"$rev-\"" -o "$work/root/init" \
	"$SRC/e2e/3dfx/glide-guest.c" "$SRC/submodules/qemu-3dfx/wrappers/3dfx/dso/glidedso.c"
(cd "$work/root" && echo init | cpio -o -H newc --quiet) > "$work/initrd"
cc -O2 -Wall -o "$work/glide-render" "$SRC/packages/wsh-openglide/tests/glide-render.c" -ldl -lX11
kernel=$(find /boot -name 'vmlinuz-*' | sort -V | tail -n 1)
echo "kernel $kernel, initrd $(wc -c < "$work/initrd") bytes"

step "QEMU with an SDL display on Xvfb"
# -extension Composite: see packages/wsh-openglide/test.sh (a 32-bit visual would give BadMatch)
Xvfb :42 -screen 0 1024x768x24 -extension Composite -nolisten tcp > "$OUT/xvfb.log" 2>&1 &
export DISPLAY=:42 SDL_VIDEODRIVER=x11
for _ in $(seq 50); do xdpyinfo > /dev/null 2>&1 && break; sleep 0.1; done
xdpyinfo > /dev/null 2>&1 || fail "Xvfb didn't start"
front=0
[ "$GALLIUM_DRIVER" != softpipe ] || front=1
accel=tcg
[ ! -w /dev/kvm ] || accel=kvm
: > "$OUT/serial.log"
# In a directory of its own: OpenGLide writes OpenGLid.ini and OpenGLid.log into QEMU's working
# directory when glidept loads it (and ends QEMU if it can't)
(cd "$work" && exec "$QEMU" -machine pc -accel "$accel" -m 256 -nodefaults -vga std -display sdl -no-reboot \
	-kernel "$kernel" -initrd "$work/initrd" -serial "file:$OUT/serial.log" \
	-append "console=ttyS0 rdinit=/init panic=-1 quiet GLIDE_GUEST_FRONT=$front") > "$OUT/qemu.log" 2>&1 &
qemu=$!
echo "accel $accel, pid $qemu"

window_ok=""
deadline=$(($(date +%s) + TIMEOUT))
while kill -0 "$qemu" 2> /dev/null; do
	if [ -z "$window_ok" ] && grep -q '^GLIDE-GUEST: FRAME' "$OUT/serial.log"; then
		sleep 1 # the guest holds the frame for 5 s
		win=$(xwininfo -root -tree | awk '/QEMU/ { print $1; exit }')
		window_ok=no
		if [ -n "$win" ] && "$work/glide-render" --check-window "$win" --ppm "$OUT/window.ppm"; then
			window_ok=yes
		fi
	fi
	[ "$(date +%s)" -lt "$deadline" ] || { kill "$qemu"; cat "$OUT/serial.log"; fail "timeout after ${TIMEOUT}s"; }
	sleep 0.5
done
wait "$qemu" || true

step "the guest's console"
cat "$OUT/serial.log"
step "QEMU's output"
cat "$OUT/qemu.log"
[ -s "$work/OpenGLid.log" ] && echo "(OpenGLide wrote OpenGLid.log into QEMU's working directory)"

grep -q '^GLIDE-GUEST: PASS' "$OUT/serial.log" || fail "the guest didn't report PASS"
[ "$window_ok" = yes ] || fail "the VM's window doesn't show the frame (${window_ok:-never captured})"
step "all passed: guest PASS, window matches (qemu-3dfx $rev, Mesa $GALLIUM_DRIVER, $accel)"
