#!/bin/sh
# Runs before systemd: everything pve-cluster needs to find at boot.
set -eu

# pmxcfs refuses to start unless the node name resolves to a non-loopback address.
name="$(hostname)"
ip="$(ip -4 -o addr show scope global | awk 'NR==1 { split($4, a, "/"); print a[1] }')"
{
    echo "127.0.0.1 localhost"
    echo "$ip $name.e2e.local $name"
} > /etc/hosts

# Login for the UI and API (realm "Linux PAM standard authentication").
echo "root:${PVE_ROOT_PASSWORD:-e2e-password}" | chpasswd

# A bridge for the VM wizard's network step. Never carries traffic (no guest starts), it only has to
# exist and be listed by the node's network API, which reads /etc/network/interfaces.
cat > /etc/network/interfaces <<EOF
auto lo
iface lo inet loopback

auto vmbr0
iface vmbr0 inet manual
	bridge-ports none
	bridge-stp off
	bridge-fd 0
EOF
# A pending interfaces.new (left by a package script at build time) would replace it.
rm -f /etc/network/interfaces.new
ip link show vmbr0 >/dev/null 2>&1 || ip link add vmbr0 type bridge
ip link set vmbr0 up

exec /sbin/init
