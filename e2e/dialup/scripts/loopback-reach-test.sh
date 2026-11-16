#!/bin/sh
# Can a slirp PPP client reach services bound to the host's 127.0.0.1 via 10.0.2.2?
mkdir -p /tmp/lo && echo "secret-localhost-service" > /tmp/lo/index.html
(cd /tmp/lo && python3 -m http.server 8081 --bind 127.0.0.1 >/dev/null 2>&1 &)
(TMO=25 inner.sh /opt/slirp-fixed/usr/bin/slirp nodefaultroute >/dev/null 2>&1 &)
sleep 12
ip route add 10.0.2.2/32 dev ppp0 2>&1
curl -s -m 5 --interface ppp0 http://10.0.2.2:8081/ || echo "no answer"
sleep 15; pkill -f "http.server 8081"
