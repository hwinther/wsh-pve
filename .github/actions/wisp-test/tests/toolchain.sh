#!/usr/bin/env bash
# Exercise the action's source-build path without a network, compiler or guest.
set -euo pipefail
action=$(cd "$(dirname "$0")/.." && pwd)/wisp-test.sh
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
export WISP_WORK="$tmp/work dir" WISP_KIT="$tmp/kit" WISP_INSTALL=false
export WISP_SOURCES=hello.c WISP_LIBC=uclibc
mkdir -p kit/{sparc32,x86_64} bin sdk/bin
touch hello.c kit/{sparc32,x86_64}/kernel
echo format=1 > kit/VERSION
export PATH="$tmp/bin:$PATH"
touch bin/qemu-system-{sparc,x86_64}
chmod +x bin/qemu-system-*
cat > bin/curl <<'SH'
#!/usr/bin/env bash
set -eu
# Record the download URL and serve the fixture for either architecture.
echo "${@: -1}" > url
while [ "$1" != -o ]; do shift; done
cp sdk.tar.xz "$2"
SH
cat > sdk/relocate-sdk.sh <<'SH'
#!/bin/sh
touch "$(dirname "$0")/relocated"
SH
for prefix in sparc-buildroot-linux-uclibc x86_64-buildroot-linux-uclibc; do
	cat > "sdk/bin/$prefix-gcc" <<'SH'
#!/bin/sh
set -eu
test -f "$WISP_WORK/sdk/relocated"
printf '%s\n' "${0##*/}" "$@" > invocation
exit 1
SH
done
chmod +x bin/curl sdk/relocate-sdk.sh sdk/bin/*-gcc
tar -cJf sdk.tar.xz sdk
export WISP_TOOLCHAIN_SHA256
WISP_TOOLCHAIN_SHA256=$(sha256sum sdk.tar.xz | cut -d' ' -f1)

expect_error() {
	local message=$1 rc=0
	shift
	env "$@" bash "$action" > output 2>&1 || rc=$?
	if [ "$rc" != 2 ] || ! grep -Fq "$message" output; then
		cat output >&2
		echo "expected action error: $message (got exit $rc)" >&2
		exit 1
	fi
}

for arch in sparc32 x86_64; do
	expect_error 'build failed' WISP_ARCH="$arch" WISP_CFLAGS=-Wall
	[ "$(cat url)" = "https://github.com/hwinther/wsh-pve/releases/download/wisp-toolchain/wisp-toolchain-$arch.tar.xz" ]
	target=$arch
	[ "$arch" != sparc32 ] || target=sparc
	printf '%s\n' "$target-buildroot-linux-uclibc-gcc" -static -O2 -Wall -o "$WISP_WORK/test" hello.c > expected
	diff -u expected invocation
done
expect_error 'build failed' WISP_TOOLCHAIN_URL=https://example.invalid/sdk
[ "$(cat url)" = https://example.invalid/sdk ]
rm url invocation
expect_error 'toolchain SHA-256 mismatch' WISP_TOOLCHAIN=sdk.tar.xz WISP_TOOLCHAIN_SHA256=0000
[ ! -e url ] && [ ! -e invocation ] || exit 1
expect_error 'build failed' WISP_TOOLCHAIN=sdk.tar.xz
[ ! -e url ]
expect_error "unknown libc 'other'" WISP_LIBC=other
for arch in sparc64 i386; do
	expect_error "no uClibc-ng SDK for $arch; see 'Your own toolchain'" WISP_ARCH="$arch"
done
echo 'toolchain input tests passed'
