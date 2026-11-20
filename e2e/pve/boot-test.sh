#!/bin/sh
# Boots a small guest through PVE in the e2e container: `qm create`, `qm start`, then waits until the
# serial console shows the guest's login prompt. The e2e suite only checks that QEMU accepts the
# command qemu-server builds; this starts it for real, so a start-up bug that only shows once the
# firmware and the guest run (the three fixed in #248) fails here.
#
# Runs inside the container (e2e.yml, job `boot`):
#
#   docker exec -i <container> sh -s -- <arch> <vmid> <iso volume> [timeout s] < e2e/pve/boot-test.sh
#
#   arch        x86_64 (i440fx, SeaBIOS, CD on ide2; KVM when /dev/kvm exists, else TCG)
#               aarch64 (virt, OVMF with an efidisk, CD on virtio-scsi; TCG)
#   iso volume  an Alpine `virt` ISO on the `local` storage, e.g. local:iso/alpine-virt-x86_64.iso
#
# The serial console (serial0: socket, vga: serial0) goes to /tmp/boot-<vmid>.log in the container.
# Exits 0 when the log shows `login:`, 1 when the time runs out or the VM stops first. The VM is
# stopped and destroyed either way.
set -eu

arch=$1
vmid=$2
iso=$3
timeout=${4:-300}
log=/tmp/boot-$vmid.log
sock=/var/run/qemu-server/$vmid.serial0

case "$arch" in
    x86_64)
        kvm=0
        if [ -c /dev/kvm ]; then kvm=1; fi
        qm create "$vmid" --name "boot-x86" --memory 512 --cores 1 --kvm "$kvm" \
            --serial0 socket --vga serial0 --ide2 "$iso,media=cdrom" --boot order=ide2
        ;;
    aarch64)
        qm create "$vmid" --name "boot-arm" --arch aarch64 --bios ovmf --efidisk0 local:1 --memory 1024 --cores 2 \
            --serial0 socket --vga serial0 --scsihw virtio-scsi-pci --scsi0 "$iso,media=cdrom" --boot order=scsi0
        ;;
    *)
        echo "boot-test: unknown arch $arch" >&2
        exit 2
        ;;
esac

cleanup() {
    qm stop "$vmid" --skiplock 1 >/dev/null 2>&1 || true
    qm destroy "$vmid" --purge 1 >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "::group::$arch: VM config and QEMU command"
qm config "$vmid"
qm showcmd "$vmid" --pretty
echo "::endgroup::"

start=$(date +%s)
qm start "$vmid"

# The socket chardev drops what the guest writes while no client is connected, so attach right
# after the start. Perl, because it is there in every PVE node.
perl -MIO::Socket::UNIX -e '
    my $s;
    for (1 .. 100) { last if $s = IO::Socket::UNIX->new(Peer => $ARGV[0]); select(undef, undef, undef, 0.1) }
    $s or die "boot-test: no serial socket $ARGV[0]\n";
    $| = 1;
    my $buf;
    print $buf while sysread($s, $buf, 4096);
' "$sock" > "$log" 2>&1 &
reader=$!

result=1
while :; do
    if grep -q 'login:' "$log" 2>/dev/null; then
        result=0
        break
    fi
    elapsed=$(( $(date +%s) - start ))
    if [ "$elapsed" -ge "$timeout" ]; then
        echo "::error::$arch: no login prompt on the serial console after ${timeout}s"
        break
    fi
    if ! qm status "$vmid" | grep -q running; then
        echo "::error::$arch: the VM stopped after ${elapsed}s without reaching the login prompt"
        break
    fi
    sleep 2
done
elapsed=$(( $(date +%s) - start ))

kill "$reader" 2>/dev/null || true
echo "::group::$arch: serial console"
# Without the escape sequences the firmware and the installer draw with
sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$log" | tr -d '\000-\010\013-\037' || true
echo
echo "::endgroup::"

# How far it got, for the summary: firmware, boot loader, kernel, init, login.
for marker in 'SeaBIOS' 'ISOLINUX' 'GRUB' 'EFI stub' 'Linux version' 'Welcome to Alpine' 'login:'; do
    if grep -q "$marker" "$log" 2>/dev/null; then echo "seen: $marker"; fi
done
if [ "$result" = 0 ]; then
    echo "$arch: login prompt after ${elapsed}s"
fi
exit "$result"
