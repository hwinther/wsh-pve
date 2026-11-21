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
# GLIDE_DISPLAY=vnc runs the same guest headless instead: no X server is installed or started, QEMU
# has `-display none` and a VNC server (PVE's console), so qemu-3dfx renders offscreen through
# wsh-openglide's EGL platform (Mesa's surfaceless EGL) and copies each frame into the VM's console;
# the host checks the probes in QEMU's screendump of that console (HMP, the image VNC serves) while
# the frame is up, and that the console shows the VGA again after the guest closes its Glide window.
#
# /src is this repository with submodules/qemu-3dfx checked out (the guest wrapper's source, at the
# commit the published binary was built from). Without a .deb argument ("-") wsh-openglide comes from
# the apt repository. Everything else is Debian's and the apt repository's: pve-qemu-kvm, Xvfb, Mesa,
# gcc with i386 multilib, and Debian's kernel (amd64, which runs the static i386 /init through its
# IA32 emulation). QEMU_BIN tests another qemu-system-x86_64 with qemu-3dfx (one built from this
# checkout, e.g. by scripts/check-qemu-3dfx-build.sh --out), installed over the published one; the
# published pve-qemu-kvm still provides its libraries and firmware. OUTDIR gets serial.log, qemu.log
# and window.ppm (screendump.ppm with VNC). GALLIUM_DRIVER picks Mesa's renderer (llvmpipe by
# default; with softpipe the guest's front-buffer read counts too). GLIDE_GUEST_BENCH=<n> has the
# guest draw <n> more frames after the check and report its frame rate. Exit 0 when the guest
# reports PASS and the window (or screendump) matches; 77 when the binary has no qemu-3dfx (the
# optional extra is missing) or, with VNC, can't render offscreen yet.
set -eu
DEB=${1:?usage: test.sh WSH-OPENGLIDE-DEB|- OUTDIR}
OUT=${2:?usage: test.sh WSH-OPENGLIDE-DEB|- OUTDIR}
SRC=${SRC:-/src}
QEMU=/usr/bin/qemu-system-x86_64-3dfx
MODE=${GLIDE_DISPLAY:-sdl}
BENCH=${GLIDE_GUEST_BENCH:-0}
TIMEOUT=${TIMEOUT:-240}
export DEBIAN_FRONTEND=noninteractive GALLIUM_DRIVER="${GALLIUM_DRIVER:-llvmpipe}" LIBGL_ALWAYS_SOFTWARE=1
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
case "$MODE" in sdl | vnc) ;; *) fail "GLIDE_DISPLAY is sdl or vnc, not '$MODE'" ;; esac
mkdir -p "$OUT"

step "packages: pve-qemu-kvm (published), wsh-openglide, Mesa, i386 gcc, Debian's kernel ($MODE)"
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
# depend on it); libegl-mesa0: Mesa's EGL, for the offscreen platform; x11-utils: xdpyinfo, xwininfo.
# With VNC no X server is installed (socat talks to QEMU's monitor); libx11-dev is only glide-render's
# build dependency.
if [ "$MODE" = sdl ]; then
	extra="xvfb xauth x11-utils"
else
	extra="socat"
fi
# shellcheck disable=SC2086 # extra is a list of packages
apt-get install --no-install-recommends --assume-yes -qq pve-qemu-kvm "$DEB" $extra \
	libgl1-mesa-dri libegl1 libegl-mesa0 gcc gcc-multilib libc6-dev-i386 libx11-dev cpio linux-image-amd64 > /dev/null
dpkg-query -W -f '${Package} ${Version}\n' pve-qemu-kvm wsh-openglide
[ "$MODE" = sdl ] || ! command -v Xvfb > /dev/null || fail "an X server is installed in the headless run"
# Another binary goes where the published one is: QEMU finds its firmware relative to its own path
if [ -n "${QEMU_BIN:-}" ]; then
	install -m 755 "$QEMU_BIN" "$QEMU"
	echo "testing $QEMU_BIN (installed as $QEMU)"
fi

if [ ! -x "$QEMU" ]; then
	echo "SKIP: this pve-qemu-kvm has no $QEMU (the optional 3dfx extra is missing)"
	exit 77
fi
if [ "$MODE" = vnc ] && ! grep -aq 'glidept: offscreen' "$QEMU"; then
	echo "SKIP: $QEMU has no offscreen display for qemu-3dfx yet (it would need an SDL window)"
	exit 77
fi
# The guest wrapper's revision must be the host binary's ("featuring qemu-3dfx@<rev>-..."): glidept
# refuses a wrapper built from another qemu-3dfx commit
rev=$("$QEMU" --version | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
[ -n "$rev" ] || fail "$QEMU --version names no qemu-3dfx revision"
src_rev=${QEMU3DFX_REV:-} # the submodule's commit (7 digits), when the caller passes it
echo "host binary: ${QEMU_BIN:-$QEMU}, qemu-3dfx $rev; guest wrapper source: ${src_rev:-unknown}; Mesa: $GALLIUM_DRIVER"
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

front=0
[ "$GALLIUM_DRIVER" != softpipe ] || front=1
accel=tcg
[ ! -w /dev/kvm ] || accel=kvm
: > "$OUT/serial.log"
if [ "$MODE" = sdl ]; then
	step "QEMU with an SDL display on Xvfb"
	# -extension Composite: see packages/wsh-openglide/test.sh (a 32-bit visual would give BadMatch)
	Xvfb :42 -screen 0 1024x768x24 -extension Composite -nolisten tcp > "$OUT/xvfb.log" 2>&1 &
	export DISPLAY=:42 SDL_VIDEODRIVER=x11
	for _ in $(seq 50); do xdpyinfo > /dev/null 2>&1 && break; sleep 0.1; done
	xdpyinfo > /dev/null 2>&1 || fail "Xvfb didn't start"
	display="-display sdl"
else
	step "QEMU headless: no display, a VNC server, the monitor on a socket"
	unset DISPLAY
	display="-display none -vnc unix:$work/vnc.sock -monitor unix:$work/mon.sock,server=on,wait=off"
fi
# In a directory of its own: OpenGLide writes OpenGLid.ini and OpenGLid.log into QEMU's working
# directory when glidept loads it (and ends QEMU if it can't)
# shellcheck disable=SC2086 # display is a list of options
(cd "$work" && exec "$QEMU" -machine pc -accel "$accel" -m 256 -nodefaults -vga std $display -no-reboot \
	-kernel "$kernel" -initrd "$work/initrd" -serial "file:$OUT/serial.log" \
	-append "console=ttyS0 rdinit=/init panic=-1 quiet GLIDE_GUEST_FRONT=$front GLIDE_GUEST_BENCH=$BENCH") > "$OUT/qemu.log" 2>&1 &
qemu=$!
echo "accel $accel, pid $qemu"

# HMP command on the monitor socket (headless runs)
hmp() { printf '%s\n' "$*" | socat -t 2 - "UNIX-CONNECT:$work/mon.sock" > /dev/null 2>&1; }
# screendump to a file, waiting until QEMU has written it
screendump() {
	rm -f "$1"
	hmp "screendump $1" || return 1
	for _ in $(seq 50); do [ -s "$1" ] && break; sleep 0.1; done
	sleep 0.2
	[ -s "$1" ]
}
ppm_size() { head -c 20 "$1" | tr '\n' ' ' | awk '{ print $2 "x" $3 }'; }

window_ok="" vga_ok="" closed_seen=""
deadline=$(($(date +%s) + TIMEOUT))
while kill -0 "$qemu" 2> /dev/null; do
	if [ -z "$window_ok" ] && grep -q '^GLIDE-GUEST: FRAME' "$OUT/serial.log"; then
		sleep 1 # the guest holds the frame for 5 s
		window_ok=no
		if [ "$MODE" = sdl ]; then
			win=$(xwininfo -root -tree | awk '/QEMU/ { print $1; exit }')
			if [ -n "$win" ] && "$work/glide-render" --check-window "$win" --ppm "$OUT/window.ppm"; then
				window_ok=yes
			fi
		elif screendump "$OUT/screendump.ppm" && "$work/glide-render" --check-ppm "$OUT/screendump.ppm"; then
			window_ok=yes
		fi
	fi
	# Headless: once the guest has closed its Glide window, the console is the VGA's again
	if [ "$MODE" = vnc ] && [ -z "$closed_seen" ] && grep -q 'glidept: offscreen closed' "$OUT/qemu.log"; then
		closed_seen=1
		sleep 0.5
		if screendump "$OUT/after.ppm"; then
			vga_ok=$(ppm_size "$OUT/after.ppm")
		fi
	fi
	[ "$(date +%s)" -lt "$deadline" ] || { kill "$qemu"; cat "$OUT/serial.log"; fail "timeout after ${TIMEOUT}s"; }
	sleep 0.2
done
wait "$qemu" || true

step "the guest's console"
cat "$OUT/serial.log"
step "QEMU's output"
cat "$OUT/qemu.log"
[ -s "$work/OpenGLid.log" ] && echo "(OpenGLide wrote OpenGLid.log into QEMU's working directory)"

grep -q '^GLIDE-GUEST: PASS' "$OUT/serial.log" || fail "the guest didn't report PASS"
if [ "$MODE" = sdl ]; then
	[ "$window_ok" = yes ] || fail "the VM's window doesn't show the frame (${window_ok:-never captured})"
	step "all passed: guest PASS, window matches (qemu-3dfx $rev, Mesa $GALLIUM_DRIVER, $accel)"
else
	[ "$window_ok" = yes ] || fail "the VM's console (screendump) doesn't show the frame (${window_ok:-never captured})"
	grep -q '^glidept: offscreen [0-9]' "$OUT/qemu.log" || fail "QEMU didn't render offscreen"
	# after the Glide window: the VGA's 720x400 text mode (or whatever it shows), not 640x480 anymore
	echo "console after the Glide window closed: ${vga_ok:-not captured}"
	case "$vga_ok" in "" | 640x480) fail "the console didn't go back to the VGA after the Glide window closed" ;; esac
	step "all passed: guest PASS, screendump matches, VGA back after (qemu-3dfx $rev, Mesa $GALLIUM_DRIVER, $accel, no X server)"
fi
grep '^GLIDE-GUEST: BENCH' "$OUT/serial.log" || true
grep -o 'glidept: offscreen closed.*' "$OUT/qemu.log" || true
