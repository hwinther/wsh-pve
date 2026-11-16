#!/bin/bash
# The retro net gateway test, hermetic (no internet): builds the gateway and the helpers, brings up
# the gateway between a retro network, a LAN and a fake internet, runs the retro client's checks
# (DHCP, DNS, the 1999 web transparently and through the proxy, instant messaging, isolation) and
# then the LAN side's checks, and removes everything again. Exit code 0 when every check passes.
#
#   retronet/test.sh            # KEEP=1 leaves the stack running for a look afterwards
set -uo pipefail
cd "$(dirname "$0")"

export COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-retronet-test}
dc() { docker compose -f compose.yml -f compose.test.yml "$@"; }
n=0 failed=0
ok()  { n=$((n+1)); echo "ok $n - $*"; }
nok() { n=$((n+1)); failed=$((failed+1)); echo "not ok $n - $*"; }

cleanup() {
  if [ $failed -ne 0 ] || [ "${SHOW_LOGS:-0}" = 1 ]; then
    echo "# gateway log (last 150 lines)"
    dc logs --no-color --tail 150 gateway 2>&1 | sed 's/^/#   /'
    echo "# nftables counters"
    dc exec -T gateway nft list table inet retronet 2>&1 | grep -E 'counter packets [1-9]' | sed 's/^/#   /'
  fi
  [ "${KEEP:-0}" = 1 ] || dc down -v --remove-orphans >/dev/null 2>&1
}
trap cleanup EXIT

echo "# build"
start=$(date +%s)
dc build gateway fakenet || { nok "build"; exit 1; }
echo "# built in $(( $(date +%s) - start )) s"

echo "# start the gateway, the fake internet and the LAN canary"
if ! dc up -d --wait --wait-timeout 180 gateway fakenet canary; then
  nok "the gateway became healthy"; exit 1
fi
ok "the gateway is healthy"

dc exec -T gateway retronet-user add alice alice123 && dc exec -T gateway retronet-user add bob bob123 \
  && ok "two accounts created with retronet-user" || nok "retronet-user add"

echo "# LAN side: positive controls"
dc exec -T canary sh -c 'curl -sS -m 5 http://192.168.98.10/ | grep -q CANARY-LAN' \
  && ok "control: the canary answers on the LAN" || nok "control: the canary does not answer"
dc exec -T canary ping -c1 -W2 192.168.98.1 >/dev/null \
  && ok "control: the Docker host answers ping on the LAN (192.168.98.1)" || nok "control: no ping from the Docker host"
before=$(dc exec -T canary cat /tmp/hits | wc -l)

echo "# retro client"
dc run --rm -T client
rc=$?
[ $rc -eq 0 ] && ok "the retro client's checks passed" || nok "the retro client's checks failed (exit $rc)"

echo "# LAN side"
for port in 1990 80 53 5190 22; do
  if dc exec -T canary python3 probe.py 192.168.98.2 $port | grep -q '^CONNECTED'; then
    nok "the gateway answers on its uplink address, port $port"
  else
    ok "nothing on the gateway's uplink address, port $port"
  fi
done
dc exec -T canary sh -c '! dig +short +time=2 +tries=1 @192.168.98.2 hive.com | grep -v "^;" | grep -q .' \
  && ok "no DNS for the LAN on the gateway's uplink address" || nok "the gateway answers DNS on the uplink"
hits=$(dc exec -T canary cat /tmp/hits)
extra=$(sed "1,${before}d" <<<"$hits")
if [ -z "$extra" ]; then
  ok "the canary saw no connection from the retro side or the gateway"
else
  nok "the canary was reached: $extra"
fi
cdx=$(dc logs --no-color fakenet 2>/dev/null | grep -c 'CDX url=http://www.example.com/ year=1999' || true)
[ "$cdx" -ge 1 ] && ok "the gateway asked the (fake) Wayback Machine directly, for 1999 ($cdx lookups)" \
  || nok "no CDX lookup for 1999 reached the fake Wayback Machine"

echo "# stop and start"
s=$(date +%s)
dc stop -t 20 gateway >/dev/null 2>&1
e=$(( $(date +%s) - s ))
[ $e -lt 15 ] && ok "the gateway stops on SIGTERM (${e} s)" || nok "the gateway took ${e} s to stop"
if dc start gateway >/dev/null 2>&1 && dc up -d --wait --wait-timeout 120 gateway >/dev/null 2>&1; then
  ok "the gateway starts again on its existing state"
else
  nok "the gateway did not come back"
fi
grep -qx alice <<<"$(dc exec -T gateway retronet-user list)" && ok "accounts survive the restart" || nok "accounts lost on restart"

echo "1..$n"
echo "# image: $(docker image inspect retronet-gateway:local --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1000000}')"
[ $failed -eq 0 ] || { echo "# $failed of $n failed"; exit 1; }
echo "# all $n passed"
