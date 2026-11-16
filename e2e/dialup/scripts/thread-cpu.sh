#!/bin/sh
# thread-cpu.sh: per-thread CPU of the running QEMU over 10 s
Q=$(pgrep -x qemu-system-x86 | head -1)
for t in /proc/$Q/task/*; do echo "$(cat $t/comm | tr ' ' _) $(awk '{print $14+$15}' $t/stat)"; done > /tmp/a; sleep 10
for t in /proc/$Q/task/*; do echo "$(cat $t/comm | tr ' ' _) $(awk '{print $14+$15}' $t/stat)"; done > /tmp/b
paste /tmp/a /tmp/b | awk '{d=$4-$2; if(d>0) print $1, d/10 "% over 10s"}'
