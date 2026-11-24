#!/bin/sh
# Build the wsh-qemu-rdp package inside the build image (packages/wsh-qemu-rdp/build.Dockerfile)
# from the repository at /src (read only) into OUT, then run lintian on it. The upstream source,
# qemu-display, is fetched with git at the commit pinned in upstream.env and our patches
# (patches/*.patch) are applied to it; its crates come from crates.io through `cargo vendor` (the only
# other network access), and the package itself builds offline from the vendored tree. The version
# comes from git on the host (version.sh), passed in the environment:
#
#   eval "$(packages/wsh-qemu-rdp/version.sh)"
#   docker build -f packages/wsh-qemu-rdp/build.Dockerfile -t wsh-qemu-rdp-build packages/wsh-qemu-rdp
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-qemu-rdp:/out" \
#     -e WSH_QEMU_RDP_VERSION -e WSH_QEMU_RDP_COMMIT -e WSH_QEMU_RDP_EPOCH \
#     wsh-qemu-rdp-build /src/packages/wsh-qemu-rdp/build.sh /out
#
# (`make wsh-qemu-rdp` does this.) The changelog's date is the wsh-pve commit's, so
# dpkg-buildpackage sets SOURCE_DATE_EPOCH from it. Patch 0001 leaves the workspace with qemu-rdp
# and the two crates it uses; cargo then drops the other members' packages from Cargo.lock, and the
# build stops if that changed anything but dropping them (a version) or left a crate that doesn't
# come from crates.io. JOBS limits cargo's parallel jobs (default: all CPUs).
set -eu
OUT=${1:?usage: build.sh OUTDIR}
SRC=${SRC:-/src}
PKG="$SRC/packages/wsh-qemu-rdp"
: "${WSH_QEMU_RDP_VERSION:?set by version.sh}" "${WSH_QEMU_RDP_COMMIT:?set by version.sh}" "${WSH_QEMU_RDP_EPOCH:?set by version.sh}"
value_of() { sed -n "s/^$1=//p" "$PKG/upstream.env"; }
url=$(value_of QEMU_DISPLAY_URL)
upstream=$(value_of QEMU_DISPLAY_COMMIT)
rdp_version=$(value_of QEMU_RDP_VERSION)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
src="$work/qemu-display"
git init -q "$src"
git -C "$src" fetch -q --depth 1 "$url" "$upstream"
git -C "$src" -c advice.detachedHead=false checkout -q FETCH_HEAD
got=$(git -C "$src" rev-parse HEAD)
[ "$got" = "$upstream" ] || { echo "build.sh: fetched $got, not the pinned $upstream" >&2; exit 1; }
got=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$src/qemu-rdp/Cargo.toml" | head -n 1)
[ "$got" = "$rdp_version" ] || { echo "build.sh: qemu-rdp is $got at the pin, upstream.env says $rdp_version" >&2; exit 1; }
# Our changes (patches/*.patch, in order; each says what it changes and why)
for p in "$PKG"/patches/*.patch; do
	[ -e "$p" ] || continue
	echo "build.sh: applying $(basename "$p")"
	git -C "$src" apply "$p"
done

tree="$work/wsh-qemu-rdp-$WSH_QEMU_RDP_VERSION"
mkdir "$tree"
tar -C "$src" --exclude=.git -c . | tar -x -C "$tree"

# The crates, from crates.io only, into vendor/ of the tree (the package builds with --offline)
locked_pairs() { awk '/^\[\[package\]\]/{n=""} /^name = /{n=$3} /^version = /{if (n != "") print n, $3}' "$1" | sort -u; }
cp "$tree/Cargo.lock" "$work/Cargo.lock.upstream"
(cd "$tree" && CARGO_HOME="$work/cargo-home" cargo vendor --quiet --versioned-dirs vendor > /dev/null)
mkdir -p "$tree/.cargo"
printf '%s\n' '[source.crates-io]' 'replace-with = "vendored-sources"' '' \
	'[source.vendored-sources]' 'directory = "vendor"' > "$tree/.cargo/config.toml"
if grep -n '^source = "git+' "$tree/Cargo.lock"; then
	echo "build.sh: the lock file above takes crates from git, not crates.io" >&2
	exit 1
fi
locked_pairs "$work/Cargo.lock.upstream" > "$work/pairs.upstream"
locked_pairs "$tree/Cargo.lock" > "$work/pairs.rdp"
changed=$(comm -23 "$work/pairs.rdp" "$work/pairs.upstream")
if [ -n "$changed" ]; then
	printf 'build.sh: cargo changed these crates in Cargo.lock (not only dropped others):\n%s\n' "$changed" >&2
	exit 1
fi
echo "build.sh: $(wc -l < "$work/pairs.upstream") crates locked upstream, $(wc -l < "$work/pairs.rdp") for qemu-rdp, $(find "$tree/vendor" -mindepth 1 -maxdepth 1 -type d | wc -l) vendored"

# The licenses of the vendored crates, as their manifests give them, for the package's docs
for d in "$tree"/vendor/*/; do
	name=$(sed -n 's/^name = "\(.*\)"$/\1/p' "$d/Cargo.toml" | head -n 1)
	version=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$d/Cargo.toml" | head -n 1)
	license=$(sed -n 's/^license = "\(.*\)"$/\1/p' "$d/Cargo.toml" | head -n 1)
	[ -n "$license" ] || license="see $(sed -n 's/^license-file = "\(.*\)"$/\1/p' "$d/Cargo.toml" | head -n 1) in the crate"
	printf '%s %s: %s\n' "$name" "$version" "$license"
done > "$tree/vendored-crates.txt"

cp -r "$PKG/debian" "$tree/"
cp "$PKG/wsh-qemu-rdp-unit" "$tree/"
# debhelper runs an executable config file: only debian/rules is one
find "$tree/debian" -type f -exec chmod 644 {} +
chmod 755 "$tree/debian/rules" "$tree/wsh-qemu-rdp-unit"

date=$(date -u -R -d "@$WSH_QEMU_RDP_EPOCH")
cat > "$tree/debian/changelog" <<CHANGELOG
wsh-qemu-rdp ($WSH_QEMU_RDP_VERSION) trixie; urgency=medium

  * qemu-rdp $rdp_version from qemu-display commit
    $upstream,
    built from wsh-pve commit
    $WSH_QEMU_RDP_COMMIT.

 -- WsHosting ENK <debian@wsh.no>  $date
CHANGELOG

# noddebs: no -dbgsym package (nothing publishes it)
DEB_BUILD_OPTIONS=$(echo "${DEB_BUILD_OPTIONS:-} noddebs${JOBS:+ parallel=$JOBS}" | sed 's/^ *//')
export DEB_BUILD_OPTIONS QEMU_RDP_GIT_HASH="$upstream"
(cd "$tree" && dpkg-buildpackage --build=binary --no-sign)
arch=$(dpkg-architecture -qDEB_HOST_ARCH)
deb="wsh-qemu-rdp_${WSH_QEMU_RDP_VERSION}_${arch}.deb"
mkdir -p "$OUT"
cp "$work/$deb" "$OUT/"
echo "built $OUT/$deb"
dpkg-deb --info "$OUT/$deb"
dpkg-deb --contents "$OUT/$deb"
sha256sum "$OUT/$deb"
# Overrides, each with its reason: debian/wsh-qemu-rdp.lintian-overrides (in the package)
lintian --info --display-info --fail-on error,warning --profile debian "$OUT/$deb"
