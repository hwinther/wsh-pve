#!/bin/bash
# The retro client's half of the test: a guest with no proxy configured, on the retro segment only.
# Prints TAP-style lines; exit 1 when any check fails.
set -u
GW=${GW:?} GW_UPLINK=${GW_UPLINK:?} CANARY=${CANARY:?} HOSTGW=${HOSTGW:?} FAKE=${FAKE:?} EXAMPLE_IP=${EXAMPLE_IP:?}
UA="Mozilla/4.0 (compatible; MSIE 5.0; Windows 98)"
n=0 failed=0
ok()    { n=$((n+1)); echo "ok $n - $*"; }
nok()   { n=$((n+1)); failed=$((failed+1)); echo "not ok $n - $*"; }
check() { local d=$1; shift; if "$@"; then ok "$d"; else nok "$d"; fi; }
has()   { grep -q -- "$1" <<<"$2"; }
hasnt() { ! grep -q -e CANARY-LAN -e ApiVersion <<<"$1"; }
first() { head -n1 <<<"$1" | cut -d' ' -f1; }
cd /opt/retronet-test
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY

echo "# DHCP"
ip -4 addr flush dev eth0
ip -4 route flush table main
if busybox udhcpc -i eth0 -n -q -t 6 -T 2 -s /opt/retronet-test/udhcpc.script >/tmp/udhcpc.log 2>&1; then
  ok "a lease from the gateway: $(cat /tmp/lease)"
else
  nok "no DHCP lease"; cat /tmp/udhcpc.log; echo "1..$n"; exit 1
fi
addr=$(ip -4 -o addr show dev eth0 | awk '{print $4}')
pool=${GW%.*}
[[ $addr =~ ^${pool//./\\.}\.1[0-9][0-9]/24$ ]] && ok "address $addr is in the gateway's pool" || nok "address $addr is not in the pool"
check "default route via the gateway" has "via $GW" "$(ip -4 route show default)"
check "DNS server is the gateway" grep -qx "nameserver $GW" /etc/resolv.conf

echo "# DNS"
q() { dig +short +time=3 +tries=1 "$@" | head -n1; }
check "hive.com resolves to the gateway" test "$(q hive.com)" = "$GW"
check "admin.hive.com resolves to the gateway" test "$(q admin.hive.com)" = "$GW"
check "an instant-messaging sign-on name resolves to the gateway" test "$(q login.oscar.aol.com)" = "$GW"
check "other names are resolved upstream (www.example.com is $EXAMPLE_IP)" test "$(q www.example.com)" = "$EXAMPLE_IP"
check "an upstream answer pointing into private space is dropped" test -z "$(q private.archive.org)"
check "a DNS server set by hand in the guest is answered by the gateway" test "$(q @8.8.8.8 hive.com)" = "$GW"

echo "# Web, transparent (no proxy configured)"
body=$(curl -0 -sS -m 30 -A "$UA" http://www.example.com/ 2>&1)
check "HTTP/1.0 GET http://www.example.com/ returns the 1999 capture" has RETRONET-FIXTURE-1999 "$body"
check "links are rewritten to the original site" has 'href="http://www.example.com/news.html"' "$body"
check "links with the full archive prefix are rewritten too" has 'href="http://www.example.com/about.html"' "$body"
check "the archive's scripts and styles are stripped" bash -c '! grep -q -e archive_analytics -e _static -e archive.org/includes <<<"$1"' _ "$body"
img=$(grep -o 'src="[^"]*logo.gif"' <<<"$body" | sed 's/^src="//; s/"$//')
check "the archived image loads (${img:-no img tag})" has GIF89a "$(curl -0 -sS -m 30 -A "$UA" "${img:-http://invalid/}" 2>&1 | head -c 6)"

echo "# Web, proxy set by hand"
check "proxy $GW:1990 serves the capture" has RETRONET-FIXTURE-1999 "$(curl -0 -sS -m 30 -A "$UA" -x "http://$GW:1990" http://www.example.com/ 2>&1)"
check "proxy $GW:80 serves the capture" has RETRONET-FIXTURE-1999 "$(curl -0 -sS -m 30 -A "$UA" -x "http://$GW:80" http://www.example.com/ 2>&1)"

echo "# A browser that sends no Host header"
out=$(python3 probe.py "$EXAMPLE_IP" 80 'GET / HTTP/1.0\r\nUser-Agent: NCSA_Mosaic/2.0\r\n\r\n')
check "transparent request without Host: the connection closes with no response" test "$(first "$out")" = CONNECTED -a "$(sed 1d <<<"$out" | wc -c)" -le 1
check "the same browser with the proxy set (absolute URI) gets the page" has RETRONET-FIXTURE-1999 \
  "$(python3 probe.py "$GW" 1990 'GET http://www.example.com/ HTTP/1.0\r\nUser-Agent: NCSA_Mosaic/2.0\r\n\r\n')"

echo "# Period services through the redirects"
oscar=$(python3 oscar_client.py login.oscar.aol.com alice alice123 bob bob123 2>&1); rc=$?
sed 's/^/#   /' <<<"$oscar"
check "instant messaging (OSCAR): sign-on with MD5, a message between two sessions, a bad password refused" test $rc -eq 0
check "FTP to any address reaches the gateway's FTP server" has $'\n220' "$(python3 probe.py "$EXAMPLE_IP" 21)"
check "telnet to any address reaches the gateway's BBS" test "$(python3 probe.py "$EXAMPLE_IP" 23 | sed 1d | wc -c)" -gt 1

echo "# Isolation: direct"
check "no ping to the LAN canary $CANARY" bash -c "! ping -c1 -W2 $CANARY >/dev/null 2>&1"
check "no ping to the Docker host $HOSTGW" bash -c "! ping -c1 -W2 $HOSTGW >/dev/null 2>&1"
check "no ping to the internet ($FAKE)" bash -c "! ping -c1 -W2 $FAKE >/dev/null 2>&1"
out=$(python3 probe.py "$CANARY" 8080 'GET / HTTP/1.0\r\n\r\n')
check "TCP to the canary's port 8080 is refused by the gateway ($(head -n1 <<<"$out"))" test "$(first "$out")" = REFUSED
check "TCP to the canary's port 80 ends at the archive proxy, not the canary" hasnt "$(python3 probe.py "$CANARY" 80 "GET / HTTP/1.0\r\nHost: $CANARY\r\n\r\n")"
for port in 22 2375 8006; do
  out=$(python3 probe.py "$HOSTGW" $port)
  check "TCP to the Docker host $HOSTGW:$port is refused by the gateway ($(head -n1 <<<"$out"))" test "$(first "$out")" = REFUSED
done
for port in 1990 80 53 5190; do
  out=$(python3 probe.py "$GW_UPLINK" $port)
  check "the gateway's uplink address $GW_UPLINK:$port is not reachable ($(head -n1 <<<"$out"))" test "$(first "$out")" != CONNECTED
done
out=$(python3 probe.py "$EXAMPLE_IP" 443)
ms=$(awk 'NR==1{print $2}' <<<"$out")
check "transparent HTTPS (443) is refused at once ($(head -n1 <<<"$out") ms)" test "$(first "$out")" = REFUSED -a "${ms:-9999}" -lt 1000
s=$(date +%s); curl -sS -m 10 https://www.example.com/ >/dev/null 2>&1; rc=$?; e=$(( $(date +%s) - s ))
check "curl https://www.example.com/ fails fast (exit $rc after ${e}s)" test $rc -ne 0 -a $e -le 2
check "UDP to the internet (NTP) gets no answer" bash -c "! timeout 8 busybox ntpd -n -q -w -p $FAKE >/dev/null 2>&1"

echo "# Isolation: through the HTTP proxy"
for url in "http://$CANARY/" "http://$CANARY:8080/" "http://canary.example.net/" "http://$HOSTGW:2375/version" \
           "http://$HOSTGW/" "http://$GW_UPLINK:1990/" \
           "http://rebind.web.archive.org/web/19990117083513if_/http://www.example.com/" \
           "http://web.archive.org.canary.example.net/web/19990117083513if_/http://www.example.com/" \
           "http://private.archive.org/web/19990117083513if_/http://www.example.com/"; do
  check "proxy request for $url does not reach it" hasnt "$(curl -0 -sS -m 30 -x "http://$GW:1990" "$url" 2>&1)"
done
check "CONNECT through the proxy to the canary fails" hasnt "$(curl -sS -m 15 -p -x "http://$GW:1990" "http://$CANARY/" 2>&1)"
check "CONNECT to a public host on 443 is no tunnel either" bash -c "! curl -sS -m 15 -x http://$GW:1990 https://www.example.com/ >/dev/null 2>&1"
check "FTP over the proxy to the canary fails" hasnt "$(curl -sS -m 15 -x "http://$GW:1990" "ftp://$CANARY/" 2>&1)"
for port in 1996 9999 1953 1988 1980; do
  out=$(python3 probe.py "$GW" $port)
  check "no SOCKS / HTTPS proxy / DNS proxy / IRC / SMTP listener: $GW:$port ($(head -n1 <<<"$out"))" test "$(first "$out")" = REFUSED
done

echo "1..$n"
[ $failed -eq 0 ] || { echo "# $failed of $n failed"; exit 1; }
echo "# all $n passed"
