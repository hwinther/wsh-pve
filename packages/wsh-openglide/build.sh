#!/bin/sh
# Build the wsh-openglide package inside the build image (packages/wsh-openglide/build.Dockerfile)
# from the repository at /src (read only) into OUT, then run lintian on it. The upstream source,
# qemu-xtra's openglide/, is fetched with git at the commit pinned in upstream.env (network access
# once); the version comes from git on the host (version.sh), passed in the environment:
#
#   eval "$(packages/wsh-openglide/version.sh)"
#   docker build -f packages/wsh-openglide/build.Dockerfile -t wsh-openglide-build packages/wsh-openglide
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-openglide:/out" \
#     -e WSH_OPENGLIDE_VERSION -e WSH_OPENGLIDE_COMMIT -e WSH_OPENGLIDE_EPOCH \
#     wsh-openglide-build /src/packages/wsh-openglide/build.sh /out
#
# (`make wsh-openglide` does this.) The changelog's date is the wsh-pve commit's, so
# dpkg-buildpackage sets SOURCE_DATE_EPOCH from it. Besides the .deb, OUT gets glide-render, the
# test program of tests/glide-render.c built against nothing but libX11 and libdl (it dlopen()s the
# library the way qemu-3dfx does); test.sh runs it against the installed package.
set -eu
OUT=${1:?usage: build.sh OUTDIR}
SRC=${SRC:-/src}
PKG="$SRC/packages/wsh-openglide"
: "${WSH_OPENGLIDE_VERSION:?set by version.sh}" "${WSH_OPENGLIDE_COMMIT:?set by version.sh}" "${WSH_OPENGLIDE_EPOCH:?set by version.sh}"
url=$(sed -n 's/^QEMU_XTRA_URL=//p' "$PKG/upstream.env")
upstream=$(sed -n 's/^QEMU_XTRA_COMMIT=//p' "$PKG/upstream.env")

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git init -q "$work/qemu-xtra"
git -C "$work/qemu-xtra" fetch -q --depth 1 "$url" "$upstream"
git -C "$work/qemu-xtra" -c advice.detachedHead=false checkout -q FETCH_HEAD
got=$(git -C "$work/qemu-xtra" rev-parse HEAD)
[ "$got" = "$upstream" ] || { echo "build.sh: fetched $got, not the pinned $upstream" >&2; exit 1; }

tree="$work/wsh-openglide-$WSH_OPENGLIDE_VERSION"
cp -r "$work/qemu-xtra/openglide" "$tree"
cp "$work/qemu-xtra/LICENSE" "$tree/LICENSE"
cp -r "$PKG/debian" "$PKG/tests" "$tree/"
# debhelper runs an executable config file: only debian/rules is one
find "$tree/debian" "$tree/tests" -type f -exec chmod 644 {} +
chmod 755 "$tree/debian/rules"

date=$(date -u -R -d "@$WSH_OPENGLIDE_EPOCH")
cat > "$tree/debian/changelog" <<CHANGELOG
wsh-openglide ($WSH_OPENGLIDE_VERSION) trixie; urgency=medium

  * OpenGLide from qemu-xtra commit
    $upstream,
    built from wsh-pve commit
    $WSH_OPENGLIDE_COMMIT.

 -- WsHosting ENK <debian@wsh.no>  $date
CHANGELOG

# noddebs: no -dbgsym package (nothing publishes it)
DEB_BUILD_OPTIONS=$(echo "${DEB_BUILD_OPTIONS:-} noddebs" | sed 's/^ *//')
export DEB_BUILD_OPTIONS
(cd "$tree" && dpkg-buildpackage --build=binary --no-sign)
arch=$(dpkg-architecture -qDEB_HOST_ARCH)
deb="wsh-openglide_${WSH_OPENGLIDE_VERSION}_${arch}.deb"
mkdir -p "$OUT"
cp "$work/$deb" "$OUT/"
cc -Wall -Wextra -Werror -O2 -o "$OUT/glide-render" "$PKG/tests/glide-render.c" -ldl -lX11
echo "built $OUT/$deb"
dpkg-deb --info "$OUT/$deb"
dpkg-deb --contents "$OUT/$deb"
sha256sum "$OUT/$deb"
# Overrides, each with its reason: debian/wsh-openglide.lintian-overrides (in the package)
lintian --info --display-info --fail-on error,warning --profile debian "$OUT/$deb"
