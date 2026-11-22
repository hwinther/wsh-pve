#!/bin/sh
# Packs the kit of the wisp-test action (.github/actions/wisp-test) from build.sh's output:
#   ./kit.sh <tarball> [arch...]        (default: sparc32 sparc64 x86_64)
#
# wisp-test-kit/VERSION                 format=1, kernel release, commit, date
# wisp-test-kit/<arch>/kernel           the tier-1 kernel; its PID 1 runs /test with wisp=test
# wisp-test-kit/<arch>/include/         the UAPI and nolibc headers PID 1 was built with
#
# Environment: OUT (default out/), COMMIT (written to VERSION, default: git rev-parse HEAD).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$HERE/out}
[ $# -ge 1 ] || { echo "usage: $0 <tarball> [arch...]" >&2; exit 2; }
tarball=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
shift
[ $# -gt 0 ] || set -- sparc32 sparc64 x86_64

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
kit=$stage/wisp-test-kit
mkdir -p "$kit"
release=
for arch in "$@"; do
	for f in kernel sysroot.tar.xz sizes; do
		[ -f "$OUT/$arch/$f" ] || { echo "kit: no $OUT/$arch/$f (build.sh $arch)" >&2; exit 1; }
	done
	mkdir -p "$kit/$arch"
	cp "$OUT/$arch/kernel" "$kit/$arch/kernel"
	tar -xJf "$OUT/$arch/sysroot.tar.xz" -C "$kit/$arch"
	release=$(sed -n 's/.*release=\([^ ]*\).*/\1/p' "$OUT/$arch/sizes")
done
commit=${COMMIT:-$(git -C "$HERE" rev-parse HEAD 2>/dev/null || echo unknown)}
printf 'format=1\nkernel=%s\narches=%s\ncommit=%s\ndate=%s\n' "$release" "$*" "$commit" \
	"$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$kit/VERSION"
tar -C "$stage" --owner=0 --group=0 --numeric-owner -cJf "$tarball" wisp-test-kit
echo "kit: $tarball ($(wc -c < "$tarball") bytes)"
cat "$kit/VERSION"
