#!/bin/sh
# Builds QEMU's libraries for the wasm64 Emscripten host from Debian source packages (apt-get source,
# upstream sources only: --skip-patches), the way QEMU's tests/docker/dockerfiles/emsdk-wasm64-cross.docker
# builds them from upstream tarballs: zlib, libffi, pcre2 (glib's regex; the emsdk image lets glib's
# meson fetch it as a subproject instead), pixman and glib, static, into $TARGET.
#
#   build-deps.sh <work dir>
#
# Environment: TARGET (install prefix, default /builddeps/target), JOBS (default: nproc), and the
# source package of each library as <package>[=<version>|/<suite>] (ZLIB, LIBFFI, PCRE2, PIXMAN, GLIB).
set -eu

WORK=$1
TARGET=${TARGET:-/builddeps/target}
JOBS=${JOBS:-$(nproc)}
ZLIB=${ZLIB:-zlib/trixie}
LIBFFI=${LIBFFI:-libffi=3.5.2-4}
PCRE2=${PCRE2:-pcre2/trixie}
PIXMAN=${PIXMAN:-pixman/trixie}
GLIB=${GLIB:-glib2.0/trixie}

export CFLAGS="-O3 -pthread -DWASM_BIGINT -sMEMORY64=1"
export CXXFLAGS="$CFLAGS"
export LDFLAGS="-sWASM_BIGINT -sASYNCIFY=1 -sMEMORY64=1 -L$TARGET/lib"
export CPATH="$TARGET/include"
export PKG_CONFIG_PATH="$TARGET/lib/pkgconfig"
export EM_PKG_CONFIG_PATH="$PKG_CONFIG_PATH"

log() { printf '%s\n' "build-deps: $*" >&2; }

# source <package spec>: fetch and unpack a Debian source package without its Debian patches, and
# cd into it. The version goes into $TARGET/versions.
source_pkg() {
	spec=$1
	name=${spec%%[=/]*}
	dir=$WORK/$name
	rm -rf "$dir"
	mkdir -p "$dir"
	cd "$dir"
	apt-get source -qq --download-only "$spec" >/dev/null 2>&1 || apt-get source --download-only "$spec"
	dsc=$(ls ./*.dsc)
	dpkg-source -x --skip-patches "$dsc" src >/dev/null
	ver=$(sed -n 's/^Version: //p' "$dsc")
	mkdir -p "$TARGET"
	printf '%s %s\n' "$name" "$ver" >> "$TARGET/versions"
	log "$name $ver"
	cd src
}

cross_file() {
	extra=$1
	cflags=$(printf "'%s', " $CFLAGS $extra | sed 's/, $//')
	ldflags=$(printf "'%s', " $LDFLAGS | sed 's/, $//')
	cat > "$WORK/cross.meson" <<EOF
[host_machine]
system = 'emscripten'
cpu_family = 'wasm64'
cpu = 'wasm64'
endian = 'little'

[binaries]
c = 'emcc'
cpp = 'em++'
ar = 'emar'
ranlib = 'emranlib'
pkgconfig = ['pkg-config', '--static']

[built-in options]
c_args = [$cflags]
cpp_args = [$cflags]
c_link_args = [$ldflags]
cpp_link_args = [$ldflags]
EOF
}

mkdir -p "$WORK" "$TARGET"
rm -f "$TARGET/versions"

source_pkg "$ZLIB"
emconfigure ./configure --prefix="$TARGET" --static >/dev/null
emmake make -j"$JOBS" install >/dev/null

source_pkg "$LIBFFI"
[ -x configure ] || autoreconf -fi >/dev/null
emconfigure ./configure --host=wasm64-unknown-linux --prefix="$TARGET" --enable-static \
	--disable-shared --disable-dependency-tracking --disable-builddir --disable-multi-os-directory \
	--disable-raw-api --disable-docs >/dev/null
emmake make -j"$JOBS" install SUBDIRS=include >/dev/null

source_pkg "$PCRE2"
[ -x configure ] || autoreconf -fi >/dev/null
emconfigure ./configure --host=wasm64-unknown-linux --prefix="$TARGET" --enable-static --disable-shared \
	--disable-jit --disable-pcre2grep-libz --disable-pcre2grep-libbz2 --disable-pcre2test-libedit \
	--disable-pcre2test-libreadline >/dev/null
emmake make -j"$JOBS" libpcre2-8.la >/dev/null
emmake make install-libLTLIBRARIES install-nodist_includeHEADERS install-pkgconfigDATA >/dev/null

source_pkg "$PIXMAN"
cross_file ""
meson setup _build --prefix="$TARGET" --cross-file="$WORK/cross.meson" --default-library=static \
	--buildtype=release -Dtests=disabled -Ddemos=disabled >/dev/null
meson install -C _build >/dev/null

# glib: res_query() stub as in the emsdk image (Emscripten has no libresolv).
mkdir -p "$WORK/stub"
cat > "$WORK/stub/res_query.c" <<'EOF'
#include <netdb.h>
int res_query(const char *name, int class, int type, unsigned char *dest, int len)
{
    h_errno = HOST_NOT_FOUND;
    return -1;
}
EOF
emcc $CFLAGS -c "$WORK/stub/res_query.c" -fPIC -o "$WORK/stub/libresolv.o"
emar rcs "$TARGET/lib/libresolv.a" "$WORK/stub/libresolv.o"

source_pkg "$GLIB"
cross_file "-Wno-incompatible-function-pointer-types"
meson setup _build --prefix="$TARGET" --cross-file="$WORK/cross.meson" --default-library=static \
	--buildtype=release --wrap-mode=nodownload -Dselinux=disabled -Dxattr=false -Dlibmount=disabled \
	-Dnls=disabled -Dtests=false -Dglib_debug=disabled -Dglib_assert=false -Dglib_checks=false \
	-Dintrospection=disabled -Dman-pages=disabled -Ddocumentation=false -Dsysprof=disabled >/dev/null
# As in the emsdk image: Emscripten lacks these in the final link, which meson doesn't detect.
sed -i -E '/#define HAVE_POSIX_SPAWN 1/d; /#define HAVE_PTHREAD_GETNAME_NP 1/d' _build/config.h
meson install -C _build >/dev/null

log "done:"
cat "$TARGET/versions" >&2
