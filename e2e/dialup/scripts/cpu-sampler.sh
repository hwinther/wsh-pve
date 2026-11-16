#!/bin/sh
# cpu-sampler.sh <pid-to-watch> : prints "uptime pid comm cputicks" every second for the dial-up processes
while kill -0 $1 2>/dev/null; do
  for p in $(pgrep -x qemu-system-x86) $(pgrep -f "perl ./atduck") $(pgrep -f "^./slirp-nandhp") $(pgrep -x pppd); do
    [ -r /proc/$p/stat ] && awk -v p=$p -v up=$(cut -d' ' -f1 /proc/uptime) -v c="$(cat /proc/$p/comm 2>/dev/null)" '{print up, p, c, $14+$15}' /proc/$p/stat 2>/dev/null
  done
  sleep 1
done
