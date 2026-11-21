#!/bin/sh
# Build the wsh-lab package from the repository at /src (read only) into OUT, inside the build image
# (packages/wsh-lab/build.Dockerfile: Debian 13 with debhelper, dh-python and lintian), then run
# lintian on it. The version comes from git on the host (version.sh), passed in the environment:
#
#   eval "$(packages/wsh-lab/version.sh)"
#   docker build -f packages/wsh-lab/build.Dockerfile -t wsh-lab-build packages/wsh-lab
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-lab:/out" \
#     -e WSH_LAB_VERSION -e WSH_LAB_COMMIT -e WSH_LAB_EPOCH wsh-lab-build /src/packages/wsh-lab/build.sh /out
#
# (`make wsh-lab` does this.) The changelog's date is the commit's, so dpkg-buildpackage sets
# SOURCE_DATE_EPOCH from it and debhelper clamps the files' times to it: the same commit and build
# image give the same .deb. Needs network access once, for the asciinema player (npm, checked
# against its pinned integrity hash; the run pages embed it).
set -eu
OUT=${1:?usage: build.sh OUTDIR}
SRC=${SRC:-/src}
: "${WSH_LAB_VERSION:?set by version.sh}" "${WSH_LAB_COMMIT:?set by version.sh}" "${WSH_LAB_EPOCH:?set by version.sh}"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
tree="$work/wsh-lab-$WSH_LAB_VERSION"
mkdir -p "$tree/lab/scenarios" "$tree/lab/tests" "$tree/player"

cp -r "$SRC/packages/wsh-lab/debian" "$SRC/packages/wsh-lab/bin" "$SRC/packages/wsh-lab/man" "$SRC/packages/wsh-lab/sun-proms" "$tree/"
sparc="$SRC/e2e/sparc"
for f in lab.py recording.py install.py targets.py targets_dos.py vgatext.py dos_tools.py dos_mem.py sunlabel.py \
	answer_media.py mirror.py mcp_server.py lab-requirements.txt mcp-requirements.txt; do
	cp "$sparc/$f" "$tree/lab/"
done
cp "$sparc"/scenarios/*.py "$tree/lab/scenarios/"
cp "$sparc/tests/test_targets.py" "$sparc/tests/test_mirror.py" "$tree/lab/tests/"
echo "$WSH_LAB_VERSION" > "$tree/lab/VERSION"
chmod 755 "$tree/bin/"* "$tree/lab/lab.py" "$tree/lab/mcp_server.py" "$tree/lab/sunlabel.py" "$tree/debian/rules"
chmod 644 "$tree/lab/scenarios/"*.py "$tree/lab/tests/"*.py "$tree/lab/"*.txt "$tree/sun-proms/manifest.json" "$tree/sun-proms/test_sun_proms.py"
chmod 755 "$tree/sun-proms/sun_proms.py"
for f in install.py recording.py targets.py targets_dos.py vgatext.py dos_tools.py dos_mem.py answer_media.py mirror.py; do
	chmod 644 "$tree/lab/$f"
done
python3 "$sparc/recording.py" fetch-player "$tree/player"

date=$(date -u -R -d "@$WSH_LAB_EPOCH")
cat > "$tree/debian/changelog" <<EOF
wsh-lab ($WSH_LAB_VERSION) trixie; urgency=medium

  * Built from wsh-pve commit $WSH_LAB_COMMIT
    (e2e/sparc, packages/wsh-lab).

 -- WsHosting ENK <debian@wsh.no>  $date
EOF

(cd "$tree" && dpkg-buildpackage --build=all --no-sign)
mkdir -p "$OUT"
deb="wsh-lab_${WSH_LAB_VERSION}_all.deb"
cp "$work/$deb" "$OUT/"
echo "built $OUT/$deb"
dpkg-deb --info "$OUT/$deb"
dpkg-deb --contents "$OUT/$deb"
sha256sum "$OUT/$deb"
# Overrides, each with its reason: debian/wsh-lab.lintian-overrides (in the package)
lintian --info --display-info --fail-on error,warning --profile debian "$OUT/$deb"
