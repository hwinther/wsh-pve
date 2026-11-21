#!/bin/sh
# The Glide and MESA GL pass-through end to end without Windows or a game, in a throwaway Debian 13
# container (as root): the published pve-qemu-kvm's qemu-system-x86_64-3dfx boots two Linux guests in
# turn, with an SDL display on Xvfb, each drawing the test scene (packages/wsh-openglide/tests/scene.h)
# through the pass-through, reading it back and checking it; the host checks the same probes in the
# VM's window while the frame is up.
#
#   - glide: /init is glide-guest (glide-guest.c, linked with qemu-3dfx's own Linux guest wrapper),
#     through the glidept device into the host's libglide2x.so (wsh-openglide). QEMU is started the
#     way qemu-server starts it, with -daemonize (QEMU then runs in /) and OPENGLIDE_DIR set to a
#     directory of the VM's: OpenGLide's OpenGLid.ini and OpenGLid.log must land there, not in /.
#   - mesa: /init is mesa-guest (mesa-guest.c, which speaks the mesapt device's protocol itself: there
#     is no Linux guest wrapper for it upstream), through the mesapt device into the host's libGL.
#
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-openglide:/deb:ro" -v "$OUT:/out" \
#     debian:trixie sh /src/e2e/3dfx/test.sh /deb/wsh-openglide_<version>_amd64.deb /out
#
# /src is this repository with submodules/qemu-3dfx checked out (the guest wrapper's source and the
# mesapt headers, at the commit the published binary was built from). Without a .deb argument ("-")
# wsh-openglide comes from the apt repository. Everything else is Debian's and the apt repository's:
# pve-qemu-kvm, Xvfb, Mesa, gcc with i386 multilib, and Debian's kernel (amd64, which runs the static
# i386 /init through its IA32 emulation). GUESTS picks the guests ("glide mesa" by default). OUTDIR
# gets <guest>-serial.log, <guest>-qemu.log and <guest>-window.ppm. GALLIUM_DRIVER picks Mesa's
# renderer (llvmpipe by default; with softpipe the Glide guest's front-buffer read counts too). Exit 0
# when every guest reports PASS and its window matches; 77 when the installed pve-qemu-kvm has no 3dfx
# binary (the optional extra is missing).
set -eu
DEB=${1:?usage: test.sh WSH-OPENGLIDE-DEB|- OUTDIR}
OUT=${2:?usage: test.sh WSH-OPENGLIDE-DEB|- OUTDIR}
SRC=${SRC:-/src}
QEMU=/usr/bin/qemu-system-x86_64-3dfx
TIMEOUT=${TIMEOUT:-240}
GUESTS=${GUESTS:-glide mesa}
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
# libegl1: SDL loads libEGL.so.1 for QEMU's window and QEMU stops without it; libgl1: mesapt
# dlopen()s libGL.so.1; x11-utils: xdpyinfo, xwininfo; binutils: strings
apt-get install --no-install-recommends --assume-yes -qq pve-qemu-kvm "$DEB" xvfb xauth x11-utils binutils \
	libgl1 libgl1-mesa-dri libegl1 libegl-mesa0 gcc gcc-multilib libc6-dev-i386 libx11-dev cpio linux-image-amd64 > /dev/null
dpkg-query -W -f '${Package} ${Version}\n' pve-qemu-kvm wsh-openglide

if [ ! -x "$QEMU" ]; then
	echo "SKIP: this pve-qemu-kvm has no $QEMU (the optional 3dfx extra is missing)"
	exit 77
fi
# The guest wrapper's revision must be the host binary's ("featuring qemu-3dfx@<rev>-..."): glidept
# and mesapt refuse a wrapper built from another qemu-3dfx commit
rev=$("$QEMU" --version | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
[ -n "$rev" ] || fail "$QEMU --version names no qemu-3dfx revision"
src_rev=${QEMU3DFX_REV:-} # the submodule's commit (7 digits), when the caller passes it
echo "host binary: qemu-3dfx $rev; guest wrapper source: ${src_rev:-unknown}; Mesa: $GALLIUM_DRIVER; guests: $GUESTS"
[ -z "$src_rev" ] || [ "$rev" = "$src_rev" ] \
	|| echo "WARNING: the published binary and the submodule differ; the guests are built from the submodule with the binary's revision"

step "the guests: glide-guest and mesa-guest as /init, i386, static"
work=$(mktemp -d)
trap 'kill $(jobs -p) 2> /dev/null || true; [ ! -s "$work/qemu.pid" ] || kill "$(cat "$work/qemu.pid")" 2> /dev/null || true; rm -rf "$work"' EXIT
Q3=$SRC/submodules/qemu-3dfx
TESTS=$SRC/packages/wsh-openglide/tests
mkdir -p "$work/glide" "$work/mesa"
gcc -m32 -static -O2 -Wall -I"$Q3/qemu-0/hw/3dfx" -I"$Q3/wrappers/3dfx/src" -I"$TESTS" -D__REV__="\"$rev-\"" \
	-o "$work/glide/init" "$SRC/e2e/3dfx/glide-guest.c" "$Q3/wrappers/3dfx/dso/glidedso.c"
gcc -m32 -static -O2 -Wall -I"$Q3/qemu-1/hw/mesa" -I"$TESTS" -D__REV__="\"$rev-\"" \
	-o "$work/mesa/init" "$SRC/e2e/3dfx/mesa-guest.c"
for g in glide mesa; do
	(cd "$work/$g" && echo init | cpio -o -H newc --quiet) > "$work/$g.initrd"
done
cc -O2 -Wall -o "$work/glide-render" "$TESTS/glide-render.c" -ldl -lX11
kernel=$(find /boot -name 'vmlinuz-*' | sort -V | tail -n 1)
echo "kernel $kernel, initrds $(wc -c < "$work/glide.initrd") and $(wc -c < "$work/mesa.initrd") bytes"

step "Xvfb for QEMU's SDL display"
# -extension Composite: see packages/wsh-openglide/test.sh (a 32-bit visual would give BadMatch)
Xvfb :42 -screen 0 1024x768x24 -extension Composite -nolisten tcp > "$OUT/xvfb.log" 2>&1 &
export DISPLAY=:42 SDL_VIDEODRIVER=x11
for _ in $(seq 50); do xdpyinfo > /dev/null 2>&1 && break; sleep 0.1; done
xdpyinfo > /dev/null 2>&1 || fail "Xvfb didn't start"
accel=tcg
[ ! -w /dev/kvm ] || accel=kvm

# run_guest NAME TAG [QEMU-ARGS...]: boot the guest NAME (its initrd), follow its console until QEMU
# ends, capture the VM's window once the guest prints "<TAG>: FRAME"; then the guest must have
# reported "<TAG>: PASS" and the window must match. QEMU runs daemonized (as qemu-server runs it) when
# the arguments include -daemonize.
run_guest() {
	name=$1 tag=$2
	shift 2
	serial=$OUT/$name-serial.log
	: > "$serial"
	rm -f "$work/qemu.pid"
	front=0
	[ "$GALLIUM_DRIVER" != softpipe ] || front=1
	step "$name: QEMU ($accel) with an SDL display on Xvfb"
	"$QEMU" -machine pc -accel "$accel" -m 256 -nodefaults -vga std -display sdl -no-reboot \
		-kernel "$kernel" -initrd "$work/$name.initrd" -serial "file:$serial" -pidfile "$work/qemu.pid" \
		-append "console=ttyS0 rdinit=/init panic=-1 quiet GLIDE_GUEST_FRONT=$front" "$@" > "$OUT/$name-qemu.log" 2>&1 &
	bg=$!
	for _ in $(seq 100); do [ -s "$work/qemu.pid" ] && break; sleep 0.1; done
	[ -s "$work/qemu.pid" ] || { cat "$OUT/$name-qemu.log"; fail "$name: QEMU didn't start"; }
	qemu=$(cat "$work/qemu.pid")
	echo "pid $qemu"
	window_ok=""
	deadline=$(($(date +%s) + TIMEOUT))
	while kill -0 "$qemu" 2> /dev/null; do
		if [ -z "$window_ok" ] && grep -q "^$tag: FRAME" "$serial"; then
			sleep 1 # the guest holds the frame for 5 s
			echo "frame up; QEMU's working directory: $(readlink "/proc/$qemu/cwd")"
			win=$(xwininfo -root -tree | awk '/QEMU/ { print $1; exit }')
			window_ok=no
			if [ -n "$win" ] && "$work/glide-render" --check-window "$win" --ppm "$OUT/$name-window.ppm"; then
				window_ok=yes
			fi
		fi
		[ "$(date +%s)" -lt "$deadline" ] || { kill "$qemu"; cat "$serial"; fail "$name: timeout after ${TIMEOUT}s"; }
		sleep 0.5
	done
	wait "$bg" || true
	step "$name: the guest's console"
	cat "$serial"
	step "$name: QEMU's output"
	cat "$OUT/$name-qemu.log"
	grep -q "^$tag: PASS" "$serial" || fail "$name: the guest didn't report PASS"
	[ "$window_ok" = yes ] || fail "$name: the VM's window doesn't show the frame (${window_ok:-never captured})"
}

for guest in $GUESTS; do
	case $guest in
	glide)
		# OpenGLide's files (OpenGLid.ini, OpenGLid.log): in OPENGLIDE_DIR, as qemu-server sets it,
		# when the installed library knows it (wsh-openglide after 0.1); never in / (QEMU's working
		# directory once it daemonizes)
		ogl=$work/openglide
		mkdir -p "$ogl"
		rm -f /OpenGLid.ini /OpenGLid.log /OpenGLid.err
		libglide=$(ldconfig -p | awk '/libglide2x\.so\.0 / { print $NF; exit }')
		knows_dir=no
		! strings "$libglide" | grep -qx OPENGLIDE_DIR || knows_dir=yes
		(cd "$work" && export OPENGLIDE_DIR="$ogl" && run_guest glide GLIDE-GUEST -daemonize)
		step "glide: OpenGLide's files"
		ls -l "$ogl" /OpenGLid.* 2> /dev/null || true
		if [ "$knows_dir" = yes ]; then
			[ -s "$ogl/OpenGLid.log" ] && [ -s "$ogl/OpenGLid.ini" ] || fail "glide: no OpenGLid.log/.ini in OPENGLIDE_DIR"
			[ ! -e /OpenGLid.log ] || fail "glide: OpenGLide wrote OpenGLid.log into / although OPENGLIDE_DIR is set"
			echo "ok: OpenGLid.ini and OpenGLid.log in OPENGLIDE_DIR, nothing in /"
		else
			echo "info: this wsh-openglide predates OPENGLIDE_DIR (its files go into QEMU's working directory, /)"
		fi
		;;
	mesa)
		run_guest mesa MESA-GUEST
		;;
	*) fail "unknown guest '$guest'" ;;
	esac
done
step "all passed: $GUESTS (qemu-3dfx $rev, Mesa $GALLIUM_DRIVER, $accel)"
