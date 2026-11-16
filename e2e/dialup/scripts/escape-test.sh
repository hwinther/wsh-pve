#!/bin/sh
# Does atduck answer OK to "<1s silence>+++<1s silence>" while online?
cd /opt/atduck; pkill -f "perl ./atduck"; rm -f /tmp/m.sock
socat TCP-LISTEN:2323,reuseaddr SYSTEM:"echo BBS; sleep 30" &
./atduck -D -l /tmp/m.sock > /tmp/esc.log 2>&1 &
sleep 1
(printf "ATZ\r"; sleep 1; printf "ATDT5553\r"; sleep 3; printf "+"; sleep 0.02; printf "+"; sleep 0.02; printf "+"; sleep 3; printf "ATH0\r"; sleep 1) | timeout 15 socat - UNIX-CONNECT:/tmp/m.sock | tr -d "\r" | grep -a -v "^$"
echo ---; grep -E "Plus|Suspend" /tmp/esc.log
pkill -f "perl ./atduck"; pkill -f "TCP-LISTEN:2323"
