#!/bin/sh
# Inside the architecture's compiler container, after fetch.py.
set -eu
arch=$1 archive=$2 output=$3
case "$arch" in
    sparc32) prefix=sparc-buildroot-linux-uclibc- ;;
    x86_64) prefix=x86_64-buildroot-linux-uclibc- ;;
    sparc64) prefix=sparc64-linux-gnu- ;;
    *) echo "unknown architecture $arch" >&2; exit 2 ;;
esac
here=$(cd "$(dirname "$0")" && pwd)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
tar -xzf "$archive" --strip-components=1 -C "$build"
for change in "$here"/patches/*.patch; do
    patch -d "$build" -p1 --fuzz=0 < "$change"
done
make -C "$build/fbdoom" -j4 NOSDL=1 CROSS_COMPILE="$prefix" \
    CFLAGS="-std=gnu11 -Os -fcommon -fwrapv -DNORMALUNIX -DLINUX" LDFLAGS="-static -s"
cp "$build/fbdoom/fbdoom" "$output"
