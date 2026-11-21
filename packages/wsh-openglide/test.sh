#!/bin/sh
# Test a built wsh-openglide package in a clean Debian 13 (as root, in a throwaway container): the
# host side of qemu-3dfx's Glide pass-through, without QEMU or a guest.
#
#   docker run --rm -v "$PWD/build/wsh-openglide:/deb" -v "$PWD/packages/wsh-openglide/test.sh:/test.sh:ro" \
#     debian:trixie sh /test.sh /deb/wsh-openglide_<version>_amd64.deb /deb/glide-render [OUTDIR]
#
# apt installs the package; libglide2x.so and libglide3x.so (the names qemu-3dfx dlopen()s) are in the
# linker's search path and resolve all their symbols. Then glide-render (tests/glide-render.c, built
# by build.sh) renders a known scene through each library under Xvfb with Mesa's software renderers
# and checks its pixels: Glide 2 into a window it hands over (what qemu-3dfx does with the SDL
# window), Glide 2 into the library's own window, and Glide 3 through the wrap3x_ entry points, with
# llvmpipe and with softpipe (llvmpipe doesn't return a front buffer after a swap, softpipe does: the
# front-buffer read counts only with softpipe). Then glide-render runs in a working directory it can't
# write to: it must still render (no exit from the library), and with OPENGLIDE_DIR the library's
# OpenGLid.ini and OpenGLid.log go there. With OUTDIR, the window of each run is saved there as
# a PPM. Then `apt purge` must leave nothing of the package behind. Exit 0 when everything passed.
set -eu
DEB=${1:?usage: test.sh /path/to/wsh-openglide_VERSION_ARCH.deb /path/to/glide-render [OUTDIR]}
RENDER=${2:?usage: test.sh DEB glide-render [OUTDIR]}
OUT=${3:-}
export DEBIAN_FRONTEND=noninteractive
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

step "the test's tools: Xvfb, Mesa (llvmpipe, softpipe)"
apt-get update -qq
apt-get install --no-install-recommends --assume-yes -qq xvfb xauth libgl1-mesa-dri binutils > /dev/null

step "apt install $DEB"
apt-get install --no-install-recommends --assume-yes "$DEB"
dpkg -s wsh-openglide | grep -E '^(Status|Version|Depends):'
version=$(dpkg-query -W -f '${Version}' wsh-openglide)

step "the libraries where qemu-3dfx's dlopen() finds them"
libdir=$(dirname "$(dpkg -L wsh-openglide | grep '/libglide2x\.so$')")
case "$libdir" in /usr/lib/*-linux-gnu) ;; *) fail "the libraries aren't in the multiarch directory: '$libdir'" ;; esac
for lib in libglide2x.so libglide3x.so; do
	path=$libdir/$lib
	[ -e "$path" ] || fail "$path is missing"
	ldconfig -p | grep -q "^[[:space:]]*$lib\.0 " || fail "$lib.0 isn't in the ld.so cache"
	if ldd -r "$path" 2>&1 | grep -E 'not found|undefined symbol'; then
		fail "$lib has unresolved libraries or symbols"
	fi
	# the entry points qemu-3dfx looks up (glide2x_impl.c init_glide2x(), conf_glide2x())
	for s in grGlideInit grSstWinOpen grDrawTriangle grBufferSwap grLfbReadRegion setConfig setConfigRes; do
		nm -D --defined-only "$path" | grep -q " T $s\$" || fail "$lib doesn't export $s"
	done
	echo "ok $path"
done
nm -D --defined-only "$libdir/libglide3x.so" | grep -q ' T wrap3x_grDrawTriangle$' \
	|| fail "libglide3x.so doesn't export wrap3x_grDrawTriangle"

# OpenGLide writes OpenGLid.ini and OpenGLid.log into the working directory when it is loaded (or
# into OPENGLIDE_DIR, checked below): run it in a directory of its own.
work=$(mktemp -d)
cd "$work"
# -extension Composite: without it Xvfb offers a 32-bit ARGB visual, which OpenGLide's GLX config
# picks, and a window of the default 24-bit visual (ours, like QEMU's) then fails with BadMatch
XVFB_ARGS="-screen 0 1024x768x24 -extension Composite"
failed=""
for driver in llvmpipe softpipe; do
	for mode in "glide2x:" "glide2x-own-window:--own-window" "glide3x:--glide3"; do
		name=${mode%%:*}
		args=${mode#*:}
		[ "$driver" = softpipe ] || args="$args --no-front"
		ppm=""
		[ -z "$OUT" ] || [ "$name" = glide2x-own-window ] || ppm="--ppm $OUT/$name-$driver.ppm"
		step "glide-render $name with $driver"
		# shellcheck disable=SC2086 # args and ppm are lists of words
		if ! LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=$driver xvfb-run -a -s "$XVFB_ARGS" "$RENDER" $args $ppm; then
			failed="$failed $name/$driver"
		fi
	done
done
[ -s OpenGLid.log ] || fail "the library wrote no OpenGLid.log into the working directory"

# Where the files go (patches/0001-openglide-dir-no-exit.patch). Up to 0.1 the library's
# constructor ended the process with status 0 when it couldn't create OpenGLid.log, before main():
# glide-render's "all probes match" line shows it got that far. /proc: a working directory that not
# even root can create files in.
step "glide-render in a working directory it can't write to, with and without OPENGLIDE_DIR"
for dir in "" "$work/ogl"; do
	mkdir -p "$work/ogl"
	out=$(cd /proc && OPENGLIDE_DIR=$dir LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe \
		xvfb-run -a -s "$XVFB_ARGS" "$RENDER" --no-front 2>&1) || { echo "$out"; failed="$failed unwritable-cwd${dir:+/OPENGLIDE_DIR}"; continue; }
	echo "$out" | tail -n 1
	echo "$out" | grep -q '^glide2x: all probes match' \
		|| { echo "$out"; failed="$failed unwritable-cwd${dir:+/OPENGLIDE_DIR}"; continue; }
	if [ -n "$dir" ]; then
		[ -s "$dir/OpenGLid.log" ] && [ -s "$dir/OpenGLid.ini" ] \
			|| { ls -la "$dir"; failed="$failed OPENGLIDE_DIR-files"; }
		echo "ok OPENGLIDE_DIR=$dir: $(cd "$dir" && echo OpenGLid.*)"
	fi
done
cd /
rm -r "$work"
[ -z "$failed" ] || fail "rendering:$failed"

step "apt purge"
apt-get purge --assume-yes wsh-openglide
# where a package's files go (not the mounted .deb, nor a checkout of this repository)
left=$(find /usr /etc /var -xdev \( -name 'libglide2x*' -o -name 'libglide3x*' -o -name '*wsh-openglide*' \) -print)
[ -z "$left" ] || fail "left after the purge: $left"
echo "nothing left behind"

step "all passed ($version)"
