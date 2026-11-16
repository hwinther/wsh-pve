#!/bin/bash
# The retro client's checks of the archive cache, run after the main checks (client-tests.sh):
#   cache-tests.sh offline   the gateway replays its store only
#   cache-tests.sh online    misses are fetched from the upstream stub
#   cache-tests.sh again     the same pages once more (the test clears VintageHive's own cache first)
set -u
GW=${GW:?}
UA="Mozilla/4.0 (compatible; MSIE 5.0; Windows 98)"
n=0 failed=0
ok()    { n=$((n+1)); echo "ok $n - $*"; }
nok()   { n=$((n+1)); failed=$((failed+1)); echo "not ok $n - $*"; }
check() { local d=$1; shift; if "$@"; then ok "$d"; else nok "$d"; fi; }
has()   { grep -q -- "$1" <<<"$2"; }
get()   { curl -0 -sS -m 60 -A "$UA" "$@" 2>&1; }
cd /opt/retronet-test
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

ip -4 addr flush dev eth0
ip -4 route flush table main
busybox udhcpc -i eth0 -n -q -t 6 -T 2 -s /opt/retronet-test/udhcpc.script >/dev/null 2>&1 || { echo "not ok 1 - no DHCP lease"; exit 1; }

case ${1:-} in
offline)
  echo "# archive cache, offline (replay only)"
  check "the synthetic 1999 page is replayed from the store" has RETRONET-FIXTURE-1999 "$(get http://www.example.com/)"
  body=$(get http://stub.example.com/)
  check "a page that is not in the store is \"not archived\" (VintageHive's 404)" has "No Internet Archive availability data" "$body"
  check "... and nothing of the stub's page came back" bash -c '! grep -q STUB-ONLINE <<<"$1"' _ "$body"
  ;;
online)
  echo "# archive cache, online (miss: fetch, store, serve)"
  body=$(get http://stub.example.com/)
  check "a miss is fetched from the upstream and served" has "STUB-ONLINE-1999 stub.example.com" "$body"
  img=$(grep -o 'src="[^"]*stub.gif"' <<<"$body" | sed 's/^src="//; s/"$//')
  check "its image is fetched too (${img:-no img})" has GIF89a "$(get "${img:-http://invalid/}" | head -c 6)"
  s=$(date +%s)
  body=$(get http://busy.example.com/)
  e=$(( $(date +%s) - s ))
  check "an upstream 429 with Retry-After is waited out and retried (${e} s)" bash -c "grep -q 'STUB-ONLINE-1999 busy.example.com' <<<\"\$1\" && [ $e -ge 2 ]" _ "$body"
  check "the synthetic page still comes from the store after the gateway was recreated" has RETRONET-FIXTURE-1999 "$(get http://www.example.com/)"
  ;;
again)
  echo "# archive cache, the same pages again"
  check "the stub's page again" has "STUB-ONLINE-1999 stub.example.com" "$(get http://stub.example.com/)"
  check "its image again" has GIF89a "$(get "http://web.archive.org/web/19990605120000im_/http://stub.example.com/stub.gif" | head -c 6)"
  ;;
*) echo "usage: $0 offline|online|again"; exit 2 ;;
esac

echo "1..$n"
[ $failed -eq 0 ] || { echo "# $failed of $n failed"; exit 1; }
echo "# all $n passed"
