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
# GLIDE_DISPLAY=vnc runs the guests headless instead: no X server is installed or started, QEMU has
# `-display none` and a VNC server (PVE's console), so qemu-3dfx renders offscreen (Glide through
# wsh-openglide's EGL platform, MESA GL on an EGL pbuffer of its own; both on Mesa's surfaceless EGL)
# and copies each frame into the VM's console; the host checks the probes in QEMU's screendump of
# that console (HMP, the image VNC serves) while the frame is up, and that the console shows the VGA
# again once the guest has closed its Glide window or GL context. Headless, the guests do more: the
# Glide guest draws into its front buffer without a swap (FRONTDRAW: the frame must reach the console
# with no further call) and sets a gamma of 2.0 (GAMMA), the Mesa guest sets a gamma ramp of 2.0
# through wglSetDeviceGammaRamp3DFX (GAMMA); the host checks the console's top left pixel each time.
# Two more headless runs of the Mesa guest: mesa-msaa asks for a 4x multisampled pixel format (QEMU
# uses one only where the EGL driver gives its frame back, not with Mesa's software renderers, and
# says so), mesa-noegl has no EGL driver (glvnd finds no vendor): the guest's wglChoosePixelFormat
# must fail and QEMU keep running.
#
# /src is this repository with submodules/qemu-3dfx checked out (the guest wrapper's source and the
# mesapt headers, at the commit the published binary was built from). Without a .deb argument ("-")
# wsh-openglide comes from the apt repository. Everything else is Debian's and the apt repository's:
# pve-qemu-kvm, Xvfb, Mesa, gcc with i386 multilib, and Debian's kernel (amd64, which runs the static
# i386 /init through its IA32 emulation). QEMU_BIN tests another qemu-system-x86_64 with qemu-3dfx
# (one built from this checkout, e.g. by scripts/check-qemu-3dfx-build.sh --out), installed over the
# published one; the published pve-qemu-kvm still provides its libraries and firmware. GUESTS picks
# the guests ("glide mesa" by default, "glide mesa mesa-msaa mesa-noegl" headless). OUTDIR gets
# <guest>-serial.log, <guest>-qemu.log and <guest>-window.ppm (<guest>-screendump.ppm and the phases'
# <guest>-<PHASE>.ppm with VNC). GALLIUM_DRIVER picks Mesa's renderer (llvmpipe by default; with
# softpipe the Glide guest's front-buffer read counts too). GLIDE_GUEST_BENCH=<n> has each guest draw
# <n> more frames after the check and report its frame rate. Exit 0 when every guest reports PASS and
# its window (or screendump) matches; 77 when the binary has no qemu-3dfx (the optional extra is
# missing) or, with VNC, can't render Glide offscreen yet (a binary that renders Glide but not MESA GL
# offscreen skips the Mesa guests headless).
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
case "$MODE" in
sdl) GUESTS=${GUESTS:-glide mesa} ;;
vnc) GUESTS=${GUESTS:-glide mesa mesa-msaa mesa-noegl} ;;
*) fail "GLIDE_DISPLAY is sdl or vnc, not '$MODE'" ;;
esac
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
# libegl1: SDL loads libEGL.so.1 for QEMU's window and QEMU stops without it; libegl-mesa0: Mesa's
# EGL, also for the offscreen platform; libgl1: mesapt dlopen()s libGL.so.1; x11-utils: xdpyinfo,
# xwininfo; binutils: strings. With VNC no X server is installed (socat talks to QEMU's monitor);
# libx11-dev is only glide-render's build dependency.
if [ "$MODE" = sdl ]; then
	extra="xvfb xauth x11-utils"
else
	extra="socat"
fi
# shellcheck disable=SC2086 # extra is a list of packages
apt-get install --no-install-recommends --assume-yes -qq pve-qemu-kvm "$DEB" $extra binutils \
	libgl1 libgl1-mesa-dri libegl1 libegl-mesa0 gcc gcc-multilib libc6-dev-i386 libx11-dev cpio linux-image-amd64 > /dev/null
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
if [ "$MODE" = vnc ] && ! grep -aq 'offscreen %dx%d, frames to' "$QEMU"; then
	echo "SKIP: $QEMU has no offscreen display for qemu-3dfx yet (it would need an SDL window)"
	exit 77
fi
if [ "$MODE" = vnc ] && ! grep -aq 'rendering offscreen, EGL' "$QEMU"; then
	echo "SKIP: $QEMU renders Glide offscreen, but not MESA GL yet (the Mesa guests need an SDL window)"
	# shellcheck disable=SC2086 # GUESTS is a list
	GUESTS=$(printf '%s\n' $GUESTS | grep -v '^mesa' | tr '\n' ' ' || true)
fi
# The guest wrapper's revision must be the host binary's ("featuring qemu-3dfx@<rev>-..."): glidept
# and mesapt refuse a wrapper built from another qemu-3dfx commit
rev=$("$QEMU" --version | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
[ -n "$rev" ] || fail "$QEMU --version names no qemu-3dfx revision"
src_rev=${QEMU3DFX_REV:-} # the submodule's commit (7 digits), when the caller passes it
echo "host binary: ${QEMU_BIN:-$QEMU}, qemu-3dfx $rev; guest wrapper source: ${src_rev:-unknown}; Mesa: $GALLIUM_DRIVER; guests: $GUESTS"
[ -z "$src_rev" ] || [ "$rev" = "$src_rev" ] \
	|| echo "WARNING: the published binary and the submodule differ; the guests are built from the submodule with the binary's revision"

step "the guests: glide-guest and mesa-guest as /init, i386, static"
work=$(mktemp -d)
# QEMU writes screendumps with mode 0600 and the container runs as root: make OUT readable for the
# host (the CI artifact upload runs as the runner user)
trap 'kill $(jobs -p) 2> /dev/null || true; [ ! -s "$work/qemu.pid" ] || kill "$(cat "$work/qemu.pid")" 2> /dev/null || true; rm -rf "$work"; chmod -R a+rX "$OUT" 2> /dev/null || true' EXIT
Q3=$SRC/submodules/qemu-3dfx
TESTS=$SRC/packages/wsh-openglide/tests
mkdir -p "$work/glide" "$work/mesa"
gcc -m32 -static -O2 -Wall -I"$Q3/qemu-0/hw/3dfx" -I"$Q3/wrappers/3dfx/src" -I"$TESTS" -D__REV__="\"$rev-\"" \
	-o "$work/glide/init" "$SRC/e2e/3dfx/glide-guest.c" "$Q3/wrappers/3dfx/dso/glidedso.c"
gcc -m32 -static -O2 -Wall -I"$Q3/qemu-1/hw/mesa" -I"$TESTS" -D__REV__="\"$rev-\"" \
	-o "$work/mesa/init" "$SRC/e2e/3dfx/mesa-guest.c" -lm
for g in glide mesa; do
	(cd "$work/$g" && echo init | cpio -o -H newc --quiet) > "$work/$g.initrd"
done
cc -O2 -Wall -o "$work/glide-render" "$TESTS/glide-render.c" -ldl -lX11
kernel=$(find /boot -name 'vmlinuz-*' | sort -V | tail -n 1)
echo "kernel $kernel, initrds $(wc -c < "$work/glide.initrd") and $(wc -c < "$work/mesa.initrd") bytes"

if [ "$MODE" = sdl ]; then
	step "Xvfb for QEMU's SDL display"
	# -extension Composite: see packages/wsh-openglide/test.sh (a 32-bit visual would give BadMatch)
	Xvfb :42 -screen 0 1024x768x24 -extension Composite -nolisten tcp > "$OUT/xvfb.log" 2>&1 &
	export DISPLAY=:42 SDL_VIDEODRIVER=x11
	for _ in $(seq 50); do xdpyinfo > /dev/null 2>&1 && break; sleep 0.1; done
	xdpyinfo > /dev/null 2>&1 || fail "Xvfb didn't start"
	display="-display sdl"
else
	unset DISPLAY
	display="-display none -vnc unix:$work/vnc.sock -monitor unix:$work/mon.sock,server=on,wait=off"
fi
accel=tcg
[ ! -w /dev/kvm ] || accel=kvm

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
# ppm_pixel FILE X Y: the pixel's colour as rrggbb, from a P6 image as QEMU's screendump writes it
# (three header lines: "P6", "<width> <height>", "255")
ppm_pixel() {
	hdr=$(head -n 3 "$1" | wc -c)
	pw=$(head -n 2 "$1" | tail -n 1 | cut -d ' ' -f 1)
	od -An -tx1 -j $((hdr + ($3 * pw + $2) * 3)) -N 3 "$1" | tr -d ' \n'
}
# near RRGGBB RRGGBB: every channel within 24 (the scene's tolerance)
near() {
	for i in 1 3 5; do
		d=$(($(printf '%d' "0x$(printf '%s' "$1" | cut -c "$i-$((i + 1))")") - $(printf '%d' "0x$(printf '%s' "$2" | cut -c "$i-$((i + 1))")")))
		[ "$d" -ge -24 ] && [ "$d" -le 24 ] || return 1
	done
}

# run_guest NAME TAG INITRD PREFIX PHASES [QEMU-ARGS...]: boot the guest INITRD, follow its console
# until QEMU ends, capture the VM's window (or, headless, a screendump of its console) once the guest
# prints "<TAG>: FRAME"; then the guest must have reported "<TAG>: PASS" and the capture must match.
# Headless, PREFIX is the device's prefix in QEMU's messages (glidept, mesapt): the console must show
# the VGA again once QEMU says "<PREFIX>: offscreen closed"; PHASES ("<PHASE>:<rrggbb> ...") are
# further screendumps, each when the guest prints "<TAG>: <PHASE>", whose top left pixel must show
# that colour. GUEST_APPEND adds to the kernel command line. QEMU runs daemonized (as qemu-server
# runs it) when the arguments include -daemonize.
run_guest() {
	name=$1 tag=$2 initrd=$3 prefix=$4 phases=$5
	shift 5
	serial=$OUT/$name-serial.log
	qlog=$OUT/$name-qemu.log
	: > "$serial"
	rm -f "$work/qemu.pid"
	front=0
	[ "$GALLIUM_DRIVER" != softpipe ] || front=1
	if [ "$MODE" = sdl ]; then
		step "$name: QEMU ($accel) with an SDL display on Xvfb"
	else
		step "$name: QEMU ($accel) headless: no display, a VNC server, the monitor on a socket"
	fi
	# shellcheck disable=SC2086 # display is a list of options
	"$QEMU" -machine pc -accel "$accel" -m 256 -nodefaults -vga std $display -no-reboot \
		-kernel "$kernel" -initrd "$work/$initrd.initrd" -serial "file:$serial" -pidfile "$work/qemu.pid" \
		-append "console=ttyS0 rdinit=/init panic=-1 quiet GLIDE_GUEST_FRONT=$front GLIDE_GUEST_BENCH=$BENCH ${GUEST_APPEND:-}" \
		"$@" > "$qlog" 2>&1 &
	bg=$!
	for _ in $(seq 100); do [ -s "$work/qemu.pid" ] && break; sleep 0.1; done
	[ -s "$work/qemu.pid" ] || { cat "$qlog"; fail "$name: QEMU didn't start"; }
	qemu=$(cat "$work/qemu.pid")
	echo "pid $qemu"
	window_ok="" vga_after="" closed_seen="" phases_done="" phases_failed="" phases_report=""
	deadline=$(($(date +%s) + TIMEOUT))
	while kill -0 "$qemu" 2> /dev/null; do
		if [ -z "$window_ok" ] && grep -q "^$tag: FRAME" "$serial"; then
			sleep 1 # the guest holds the frame for 5 s
			echo "frame up; QEMU's working directory: $(readlink "/proc/$qemu/cwd")"
			window_ok=no
			if [ "$MODE" = sdl ]; then
				win=$(xwininfo -root -tree | awk '/QEMU/ { print $1; exit }')
				if [ -n "$win" ] && "$work/glide-render" --check-window "$win" --ppm "$OUT/$name-window.ppm"; then
					window_ok=yes
				fi
			elif screendump "$OUT/$name-screendump.ppm" && "$work/glide-render" --check-ppm "$OUT/$name-screendump.ppm"; then
				window_ok=yes
			fi
		fi
		for phase in $phases; do
			key=${phase%%:*} want=${phase#*:}
			case " $phases_done " in *" $key "*) continue ;; esac
			grep -q "^$tag: $key" "$serial" || continue
			phases_done="$phases_done $key"
			sleep 1 # the guest holds it for 3 s
			got=none
			! screendump "$OUT/$name-$key.ppm" || got=$(ppm_pixel "$OUT/$name-$key.ppm" 10 10)
			if [ "$got" != none ] && near "$got" "$want"; then
				phases_report="$phases_report ok:$key(#$got)"
			else
				phases_report="$phases_report FAIL:$key(#$got,want#$want)"
				phases_failed="$phases_failed $key"
			fi
		done
		if [ "$MODE" = vnc ] && [ -z "$closed_seen" ] && grep -q "$prefix: offscreen closed" "$qlog"; then
			closed_seen=1
			sleep 0.5
			! screendump "$OUT/$name-after.ppm" || vga_after="$(ppm_size "$OUT/$name-after.ppm") #$(ppm_pixel "$OUT/$name-after.ppm" 10 10)"
		fi
		[ "$(date +%s)" -lt "$deadline" ] || { kill "$qemu"; cat "$serial"; fail "$name: timeout after ${TIMEOUT}s"; }
		sleep 0.2
	done
	wait "$bg" || true
	step "$name: the guest's console"
	cat "$serial"
	step "$name: QEMU's output"
	cat "$qlog"
	grep -q "^$tag: PASS" "$serial" || fail "$name: the guest didn't report PASS"
	if [ "$MODE" = sdl ]; then
		[ "$window_ok" = yes ] || fail "$name: the VM's window doesn't show the frame (${window_ok:-never captured})"
	else
		[ "$window_ok" = yes ] || fail "$name: the VM's console (screendump) doesn't show the frame (${window_ok:-never captured})"
		grep -q "$prefix: offscreen [0-9]" "$qlog" || fail "$name: QEMU didn't render offscreen"
		# after the window: the VGA's picture (the Glide guest's 720x400 text mode, the Mesa guest's
		# cleared 640x480 VBE mode), not the frame (its dark blue clear at the top left)
		echo "console after the offscreen window closed: ${vga_after:-not captured}"
		case "$vga_after" in
		"") fail "$name: no screendump after the offscreen window closed" ;;
		"640x480 #"*) ! near "${vga_after#*#}" 000080 || fail "$name: the console didn't go back to the VGA after the offscreen window closed" ;;
		esac
		for phase in $phases; do
			case " $phases_done " in *" ${phase%%:*} "*) ;; *) fail "$name: the guest never reached ${phase%%:*}" ;; esac
		done
		[ -z "$phases" ] || echo "phases:$phases_report"
		[ -z "$phases_failed" ] || fail "$name: the console's colour is wrong in:$phases_failed"
	fi
	grep "^$tag: BENCH" "$serial" || true
	grep -o "$prefix: offscreen window .*" "$qlog" || true
	grep -o "$prefix: offscreen closed.*" "$qlog" || true
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
		# Headless: front-buffer drawing (dark green) and a gamma of 2.0 (the clear's 0x80 blue to
		# 0xb5), when the library applies gamma offscreen
		phases="" append=""
		if [ "$MODE" = vnc ]; then
			append="GLIDE_GUEST_EXTRA=1"
			# The front-buffer timer came with the OpenGL offscreen code (stage 1b); an older binary
			# (the published one, in wsh-openglide.yml) shows such a frame only at the next call
			if strings "$QEMU" | grep -q 'rendering offscreen, EGL'; then
				phases="FRONTDRAW:006000"
			else
				echo "info: this qemu-3dfx shows front-buffer drawing only at the next call (not checked)"
			fi
			if strings "$libglide" | grep -q EGLSetGamma; then
				phases="$phases GAMMA:0000b5"
			else
				echo "info: this wsh-openglide applies no gamma offscreen (not checked)"
			fi
		fi
		(cd "$work" && export OPENGLIDE_DIR="$ogl" GUEST_APPEND="$append" &&
			run_guest glide GLIDE-GUEST glide glidept "$phases" -daemonize)
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
		if [ "$MODE" = vnc ]; then
			GUEST_APPEND="MESA_GUEST_GAMMA=1"
			run_guest mesa MESA-GUEST mesa mesapt "GAMMA:0000b5"
			GUEST_APPEND=""
		else
			run_guest mesa MESA-GUEST mesa mesapt ""
		fi
		;;
	mesa-msaa)
		[ "$MODE" = vnc ] || fail "mesa-msaa: headless only (GLIDE_DISPLAY=vnc)"
		GUEST_APPEND="MESA_GUEST_MSAA=4"
		run_guest mesa-msaa MESA-GUEST mesa mesapt ""
		GUEST_APPEND=""
		grep -q 'mesapt: offscreen window .* samples 1 [1-9]' "$OUT/mesa-msaa-qemu.log" \
			|| echo "info: mesa-msaa: no multisampled EGL config with this Mesa (rendered without)"
		;;
	mesa-noegl)
		# No EGL driver (glvnd finds no vendor): the guest's wglChoosePixelFormat must fail and QEMU
		# keep running until the guest powers the VM off
		[ "$MODE" = vnc ] || fail "mesa-noegl: headless only (GLIDE_DISPLAY=vnc)"
		step "mesa-noegl: QEMU ($accel) headless with no EGL driver"
		: > "$OUT/mesa-noegl-serial.log"
		rc=0
		# shellcheck disable=SC2086 # display is a list of options
		__EGL_VENDOR_LIBRARY_FILENAMES=/nonexistent.json timeout "$TIMEOUT" "$QEMU" -machine pc -accel "$accel" \
			-m 256 -nodefaults -vga std $display -no-reboot -kernel "$kernel" -initrd "$work/mesa.initrd" \
			-serial "file:$OUT/mesa-noegl-serial.log" -append "console=ttyS0 rdinit=/init panic=-1 quiet" \
			> "$OUT/mesa-noegl-qemu.log" 2>&1 || rc=$?
		cat "$OUT/mesa-noegl-serial.log" "$OUT/mesa-noegl-qemu.log"
		[ "$rc" = 0 ] || fail "mesa-noegl: QEMU exited with $rc"
		grep -q '^MESA-GUEST: ERROR wglChoosePixelFormat' "$OUT/mesa-noegl-serial.log" \
			|| fail "mesa-noegl: the guest's wglChoosePixelFormat didn't fail"
		grep -q "^mesapt: .*the guest's OpenGL fails" "$OUT/mesa-noegl-qemu.log" \
			|| fail "mesa-noegl: QEMU didn't say why the guest's OpenGL fails"
		echo "ok: no EGL: the guest's OpenGL failed, QEMU kept running"
		;;
	*) fail "unknown guest '$guest'" ;;
	esac
done
if [ "$MODE" = sdl ]; then
	step "all passed: $GUESTS (qemu-3dfx $rev, Mesa $GALLIUM_DRIVER, $accel)"
else
	step "all passed headless: $GUESTS, screendumps match, VGA back after (qemu-3dfx $rev, Mesa $GALLIUM_DRIVER, $accel, no X server)"
fi
