#!/bin/sh
# Build the wsh-gst-qemu-dbus package inside the build image (packages/wsh-gst-qemu-dbus/
# build.Dockerfile) from the repository at /src (read only) into OUT, then run lintian on it. The
# source is all in this directory (meson.build, src/); nothing is fetched. The version comes from
# git on the host (version.sh), passed in the environment:
#
#   eval "$(packages/wsh-gst-qemu-dbus/version.sh)"
#   docker build -f packages/wsh-gst-qemu-dbus/build.Dockerfile -t wsh-gst-qemu-dbus-build packages/wsh-gst-qemu-dbus
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-gst-qemu-dbus:/out" \
#     -e WSH_GST_QEMU_DBUS_VERSION -e WSH_GST_QEMU_DBUS_COMMIT -e WSH_GST_QEMU_DBUS_EPOCH \
#     wsh-gst-qemu-dbus-build /src/packages/wsh-gst-qemu-dbus/build.sh /out
#
# (`make wsh-gst-qemu-dbus` does this.) The changelog's date is the wsh-pve commit's, so
# dpkg-buildpackage sets SOURCE_DATE_EPOCH from it.
set -eu
OUT=${1:?usage: build.sh OUTDIR}
SRC=${SRC:-/src}
PKG="$SRC/packages/wsh-gst-qemu-dbus"
: "${WSH_GST_QEMU_DBUS_VERSION:?set by version.sh}" "${WSH_GST_QEMU_DBUS_COMMIT:?set by version.sh}" \
	"${WSH_GST_QEMU_DBUS_EPOCH:?set by version.sh}"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
tree="$work/wsh-gst-qemu-dbus-$WSH_GST_QEMU_DBUS_VERSION"
mkdir "$tree"
cp -r "$PKG/meson.build" "$PKG/meson.options" "$PKG/src" "$PKG/debian" "$PKG/README.md" "$tree/"
# debhelper runs an executable config file: only debian/rules is one
find "$tree/debian" -type f -exec chmod 644 {} +
chmod 755 "$tree/debian/rules"

date=$(date -u -R -d "@$WSH_GST_QEMU_DBUS_EPOCH")
cat > "$tree/debian/changelog" <<CHANGELOG
wsh-gst-qemu-dbus ($WSH_GST_QEMU_DBUS_VERSION) trixie; urgency=medium

  * Built from wsh-pve commit
    $WSH_GST_QEMU_DBUS_COMMIT.

 -- WsHosting ENK <debian@wsh.no>  $date
CHANGELOG

# noddebs: no -dbgsym package (nothing publishes it)
DEB_BUILD_OPTIONS=$(echo "${DEB_BUILD_OPTIONS:-} noddebs" | sed 's/^ *//')
export DEB_BUILD_OPTIONS
(cd "$tree" && dpkg-buildpackage --build=binary --no-sign)
arch=$(dpkg-architecture -qDEB_HOST_ARCH)
deb="wsh-gst-qemu-dbus_${WSH_GST_QEMU_DBUS_VERSION}_${arch}.deb"
mkdir -p "$OUT"
cp "$work/$deb" "$OUT/"
echo "built $OUT/$deb"
dpkg-deb --info "$OUT/$deb"
dpkg-deb --contents "$OUT/$deb"
sha256sum "$OUT/$deb"
lintian --info --display-info --fail-on error,warning --profile debian "$OUT/$deb"
