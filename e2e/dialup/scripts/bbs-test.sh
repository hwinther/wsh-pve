#!/bin/sh
# Check the restricted dial plan: whitelisted telnet BBS works, shell/arbitrary numbers do not.
cd /opt/atduck; pkill -f "perl ./atduck"; rm -f /tmp/m.sock
socat TCP-LISTEN:2323,reuseaddr SYSTEM:"echo WELCOME-TO-THE-BBS; sleep 2" &
./atduck -D -l /tmp/m.sock > /tmp/bbs.log 2>&1 &
sleep 1
(printf "ATZ\r"; sleep 1; printf "ATDT5553\r"; sleep 4; printf "ATDT5550\r"; sleep 2; printf "ATDT8127000000001002323\r"; sleep 2) | timeout 15 socat - UNIX-CONNECT:/tmp/m.sock | tr -d "\r" | grep -a -v "^$"
pkill -f "perl ./atduck"
