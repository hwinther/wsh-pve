#!/bin/sh
# Puts the Glide test guest of e2e/3dfx/test.sh into the e2e PVE container, for
# e2e/tests/3dfx-gl-display.spec.ts: a VM that PVE starts with the 3dfx binary (`vga: ...,mesa=1`) boots
# Debian's kernel with glide-guest (e2e/3dfx/glide-guest.c, linked with qemu-3dfx's Linux guest
# wrapper) as /init, and the test checks its frame in PVE's noVNC console.
#
#   e2e/3dfx/pve-guest-setup.sh [CONTAINER]     (default: $PVE_CONTAINER, else wsh-pve-e2e)
#
# Runs on the Docker host, from the repository root (submodules/qemu-3dfx checked out). In the
# container it installs gcc, the i386 libc, cpio and linux-image-amd64 with apt (network needed) and
# leaves:
#
#   /root/3dfx-guest/vmlinuz        Debian's kernel
#   /root/3dfx-guest/glide.initrd   glide-guest as /init (i386, static)
#
# The guest wrapper is built with the revision of the container's /usr/bin/qemu-system-x86_64-3dfx
# ("featuring qemu-3dfx@<rev>-"), which glidept insists on, so build it again after replacing that
# binary with one of another qemu-3dfx commit.
set -eu

container=${1:-${PVE_CONTAINER:-wsh-pve-e2e}}
top=$(cd "$(dirname "$0")/../.." && pwd)
q3=submodules/qemu-3dfx
[ -f "$top/$q3/wrappers/3dfx/dso/glidedso.c" ] || {
    echo "pve-guest-setup: $q3 isn't checked out (git submodule update --init $q3)" >&2
    exit 2
}

echo "pve-guest-setup: the guest's sources to $container:/root/3dfx-guest/src"
docker exec "$container" sh -c 'rm -rf /root/3dfx-guest && mkdir -p /root/3dfx-guest/src'
(cd "$top" && tar -cf - e2e/3dfx/glide-guest.c packages/wsh-openglide/tests/scene.h \
    "$q3/qemu-0/hw/3dfx" "$q3/wrappers/3dfx/src" "$q3/wrappers/3dfx/dso") |
    docker exec -i "$container" tar -xf - -C /root/3dfx-guest/src

echo "pve-guest-setup: building it in $container"
docker exec -i "$container" sh -s << 'EOF'
set -eu
export DEBIAN_FRONTEND=noninteractive
cd /root/3dfx-guest
qemu=/usr/bin/qemu-system-x86_64-3dfx
[ -x "$qemu" ] || { echo "pve-guest-setup: no $qemu in the container (pve-qemu-kvm without the 3dfx extra)" >&2; exit 1; }
rev=$("$qemu" --version | sed -n 's/.*qemu-3dfx@\([0-9a-f]\{7\}\)-.*/\1/p')
[ -n "$rev" ] || { echo "pve-guest-setup: $qemu --version names no qemu-3dfx revision" >&2; exit 1; }
# the image has PVE's enterprise repository too, which refuses a node without a subscription
apt-get update -qq 2>&1 | grep -v 'enterprise.proxmox.com' || true
apt-get install --no-install-recommends --assume-yes -qq gcc gcc-multilib libc6-dev-i386 cpio linux-image-amd64 > /dev/null
s=src q3=src/submodules/qemu-3dfx
mkdir -p glide
gcc -m32 -static -O2 -Wall -I"$q3/qemu-0/hw/3dfx" -I"$q3/wrappers/3dfx/src" -I"$s/packages/wsh-openglide/tests" \
    -D__REV__="\"$rev-\"" -o glide/init "$s/e2e/3dfx/glide-guest.c" "$q3/wrappers/3dfx/dso/glidedso.c"
(cd glide && echo init | cpio -o -H newc --quiet) > glide.initrd
cp "$(find /boot -name 'vmlinuz-*' | sort -V | tail -n 1)" vmlinuz
rm -rf glide src
echo "pve-guest-setup: qemu-3dfx $rev; $(ls -l vmlinuz glide.initrd | awk '{ print $NF, $5 }' | tr '\n' ' ')"
EOF
