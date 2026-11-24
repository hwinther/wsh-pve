#!/bin/sh
# Boots a small guest through PVE in the e2e container: the VM is created through the API (`pvesh
# create`, pve-manager's API tree into qemu-server), started with `qm start`, and the test waits
# until the serial console shows the guest's login prompt, then stops it with `qm stop`. The e2e
# suite only checks that QEMU accepts the command qemu-server builds; this starts it for real, so a
# start-up bug that only shows once the firmware and the guest run (like the three fixed in #248)
# fails here.
#
# Runs inside the container (e2e.yml, job `boot`):
#
#   docker exec -i <container> sh -s -- <case> <vmid> <iso volume> [timeout s] < e2e/pve/boot-test.sh
#
#   case        i440fx   x86_64, pc (i440fx), SeaBIOS, CD on ide2 (x86_64 is an alias)
#               q35      x86_64, q35, SeaBIOS, CD on ide2 (AHCI)
#               ovmf     x86_64, q35, OVMF with a 4M efidisk, CD on ide2
#               aarch64  virt, OVMF (AAVMF) with an efidisk, CD on virtio-scsi; always TCG
#   iso volume  an Alpine `virt` ISO on the `local` storage, e.g. local:iso/alpine-virt-x86_64.iso
#
# x86_64 runs under KVM when /dev/kvm exists, else TCG; BOOT_TEST_TCG=1 forces TCG.
#
# The serial console (serial0: socket, vga: serial0) goes to /tmp/boot-<vmid>.log in the container.
# Passes when the log shows firmware output (SeaBIOS, or OVMF's BdsDxe or GRUB on OVMF's console),
# then the login prompt on the board's console port (Alpine's issue names it: /dev/ttyS0 on x86_64,
# /dev/ttyAMA0 on aarch64), and `qm stop` works. Both checks matter: Linux puts a getty on whatever
# serial port it finds, so a socket wired to an extra UART instead of the console port (#248's
# sparc64 bug) still reaches `login:`, on another tty and without the firmware's output. Fails when
# `qm start` fails, the time runs out, the VM stops first or a check fails. The VM is stopped and
# destroyed either way.
set -eu

case=$1
vmid=$2
iso=$3
timeout=${4:-300}
log=/tmp/boot-$vmid.log
sock=/var/run/qemu-server/$vmid.serial0
node=$(hostname)

kvm=0
if [ -c /dev/kvm ] && [ "${BOOT_TEST_TCG:-0}" != 1 ]; then kvm=1; fi

# Common to every case: a serial console only, no disk but the CD (and the efidisk).
set -- --vmid "$vmid" --name "boot-$case" --serial0 socket --vga serial0
case "$case" in
    x86_64 | i440fx)
        fw="SeaBIOS|Booting from" tty=ttyS0
        set -- "$@" --memory 512 --cores 1 --kvm "$kvm" --ide2 "$iso,media=cdrom" --boot order=ide2
        ;;
    q35)
        fw="SeaBIOS|Booting from" tty=ttyS0
        set -- "$@" --machine q35 --memory 512 --cores 1 --kvm "$kvm" --ide2 "$iso,media=cdrom" --boot order=ide2
        ;;
    ovmf)
        fw="BdsDxe|GRUB" tty=ttyS0
        set -- "$@" --machine q35 --bios ovmf --efidisk0 "local:1,efitype=4m" --memory 512 --cores 1 --kvm "$kvm" \
            --ide2 "$iso,media=cdrom" --boot order=ide2
        ;;
    aarch64)
        fw="BdsDxe|GRUB" tty=ttyAMA0
        set -- "$@" --arch aarch64 --bios ovmf --efidisk0 local:1 --memory 1024 --cores 2 \
            --scsihw virtio-scsi-pci --scsi0 "$iso,media=cdrom" --boot order=scsi0
        ;;
    *)
        echo "boot-test: unknown case $case" >&2
        exit 2
        ;;
esac
pvesh create "/nodes/$node/qemu" "$@" >/dev/null

# shellcheck disable=SC2329 # called by the trap
cleanup() {
    qm stop "$vmid" --skiplock 1 >/dev/null 2>&1 || true
    qm destroy "$vmid" --purge 1 >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "::group::$case: VM config and QEMU command"
qm config "$vmid"
qm showcmd "$vmid" --pretty
echo "::endgroup::"

# The socket chardev drops what the guest writes while no client is connected, so the reader is
# started first and connects as soon as QEMU has created the socket, before the firmware prints
# anything. Perl, because it is there in every PVE node. The log is emptied here, not by the
# background job's redirection, so the loop below never reads a previous run's log.
: > "$log"
perl -MIO::Socket::UNIX -e '
    my $s;
    for (1 .. 1200) { last if $s = IO::Socket::UNIX->new(Peer => $ARGV[0]); select(undef, undef, undef, 0.05) }
    $s or die "boot-test: no serial socket $ARGV[0]\n";
    $| = 1;
    my $buf;
    print $buf while sysread($s, $buf, 4096);
' "$sock" >> "$log" 2>&1 &
reader=$!

start=$(date +%s)
if ! qm start "$vmid"; then
    echo "::error::$case: qm start failed"
    kill "$reader" 2>/dev/null || true
    exit 1
fi

result=1
while :; do
    if grep -q 'login:' "$log" 2>/dev/null; then
        result=0
        break
    fi
    elapsed=$(( $(date +%s) - start ))
    if [ "$elapsed" -ge "$timeout" ]; then
        echo "::error::$case: no login prompt on the serial console after ${timeout}s"
        break
    fi
    if ! qm status "$vmid" | grep -q running; then
        echo "::error::$case: the VM stopped after ${elapsed}s without reaching the login prompt"
        break
    fi
    sleep 1
done
elapsed=$(( $(date +%s) - start ))

if [ "$result" = 0 ] && ! grep -Eq "$fw" "$log"; then
    echo "::error::$case: login prompt, but no firmware output ($fw) before it: the serial socket is not the firmware's console port"
    result=1
fi
if [ "$result" = 0 ] && ! grep -q "(/dev/$tty)" "$log"; then
    got=$(sed -n 's/.*(\/dev\/\([A-Za-z0-9]*\)).*/\1/p' "$log" | head -n 1)
    echo "::error::$case: the login prompt is on ${got:-an unnamed tty}, not $tty: the serial socket is not the board's console port"
    result=1
fi

kill "$reader" 2>/dev/null || true
if [ "$result" = 0 ] && ! qm stop "$vmid"; then
    echo "::error::$case: qm stop failed"
    result=1
fi

echo "::group::$case: serial console"
# Without the escape sequences the firmware and the installer draw with
sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$log" | tr -d '\000-\010\013-\037' || true
echo
echo "::endgroup::"

# How far it got, for the summary: firmware, boot loader, kernel, init, login.
for marker in 'SeaBIOS' 'BdsDxe' 'ISOLINUX' 'GRUB' 'EFI stub' 'Linux version' 'Welcome to Alpine' 'login:'; do
    if grep -q "$marker" "$log" 2>/dev/null; then echo "seen: $marker"; fi
done
accel=tcg
if [ "$case" != aarch64 ] && [ "$kvm" = 1 ]; then accel=kvm; fi
if [ "$result" = 0 ]; then
    echo "$case: login prompt on $tty after ${elapsed}s ($accel)"
fi
exit "$result"
