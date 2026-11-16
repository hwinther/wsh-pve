#!/bin/sh
# Inner loop: pppd on a pty <-> socat <-> atduck (UNIX socket server), no guest.
# usage: inner.sh <slirp-binary> [extra pppd opts...]
SLIRP=${1:-/usr/bin/slirp}; shift
OUT=${OUT:-/tmp/inner}; rm -rf $OUT; mkdir -p $OUT
pkill -f "perl ./atduck -D" ; pkill -x socat; pkill -x pppd; pkill -f "^./slirp-nandhp"; sleep 0.5
cd /opt/atduck && ln -sf "$SLIRP" ./slirp-nandhp-patch
rm -f /tmp/m.sock
${ATDUCK_USER:+runuser -u $ATDUCK_USER --} ./atduck -D -D -l /tmp/m.sock >$OUT/atduck.log 2>&1 &
sleep 1
socat -x -lf $OUT/socat.log pty,link=/tmp/ttyM,raw,echo=0 UNIX-CONNECT:/tmp/m.sock 2>$OUT/socat.hex &
sleep 1
cat > /tmp/chat.txt <<C
ABORT BUSY
ABORT "NO CARRIER"
TIMEOUT 15
"" ATZ
OK ATDT${NUM:-5555}
CONNECT ""
C
timeout ${TMO:-40} pppd /tmp/ttyM 115200 connect "chat -v -f /tmp/chat.txt" nodetach debug ${AUTHOPT-noauth} local nocrtscts \
   noipdefault defaultroute usepeerdns persist maxfail 1 lcp-echo-interval 0 logfile $OUT/pppd.log "$@" >$OUT/pppd.out 2>&1
echo "pppd exit $?"
