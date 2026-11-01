#!/bin/sh
# Runs once pmxcfs has mounted /etc/pve: storage the container can actually provide, then marks the
# node ready for the healthcheck.
set -eu

# Only a directory storage: the default local-lvm (LVM thin) doesn't exist in a container, and the
# wizard would offer it. Disks are created as files under /var/lib/vz/images.
cat > /etc/pve/storage.cfg <<'EOF'
dir: local
	path /var/lib/vz
	content images,iso,vztmpl,backup,snippets,rootdir
EOF

# Wait for the API: the tests start as soon as the healthcheck passes.
for _ in $(seq 1 60); do
    if pvesh get /version >/dev/null 2>&1; then
        touch /run/pve-e2e-ready
        exit 0
    fi
    sleep 1
done
echo "pve-e2e-setup: the API did not come up" >&2
exit 1
