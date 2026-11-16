#!/bin/sh
# PVE hookscript: qm set <vmid> --hookscript local:snippets/dialup-hook.sh
# Starts/stops the per-VM modem emulator together with the VM.  (Untested on a real PVE host.)
vmid=$1; phase=$2
sock=/var/run/qemu-server/$vmid.serial0
case $phase in
  post-start)
    for i in 1 2 3 4 5 6 7 8 9 10; do [ -S "$sock" ] && break; sleep 0.5; done
    chgrp dialup "$sock" && chmod g+rw "$sock"
    systemctl start "atduck@$vmid.service" ;;
  pre-stop|post-stop)
    systemctl stop "atduck@$vmid.service" ;;
esac
exit 0
