#!/bin/bash
# The retro net gateway test, hermetic (no internet): builds the gateway and the helpers, brings up
# the gateway between a retro network, a LAN and a fake internet, and checks it from the retro client
# (DHCP, DNS, the 1999 web transparently and through the proxy, instant messaging, isolation) and
# from the LAN. The 1999 web comes from the gateway's archive cache replaying a synthetic dataset
# (offline); then the gateway is recreated online to check the cache's miss path, its store, the
# warm-up command and export/import against a small upstream stub. Everything is removed at the end.
# Exit code 0 when every check passes.
#
#   retronet/test.sh            # KEEP=1 leaves the stack running for a look afterwards
set -uo pipefail
cd "$(dirname "$0")"

export COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-retronet-test}
export RETRONET_TEST_ARCHIVE_MODE=offline
dc() { docker compose -f compose.yml -f compose.test.yml "$@"; }
n=0 failed=0
ok()  { n=$((n+1)); echo "ok $n - $*"; }
nok() { n=$((n+1)); failed=$((failed+1)); echo "not ok $n - $*"; }
expect() { local d=$1; shift; if "$@"; then ok "$d"; else nok "$d"; fi; }
tmp=$(mktemp -d)

# requests the upstream stub has seen for one key ("cdx <url>" or "web <url>"), or all
stub() {
  dc exec -T fakenet python3 -c "import json, urllib.request; d = json.load(urllib.request.urlopen('http://127.0.0.1/_stats')); print(sum(d.values()) if '$1' == 'all' else d.get('$1', 0))"
}
# a field of the running archive cache's statistics
acstat() {
  dc exec -T gateway sh -c "retronet-archive stats --server | python3 -c 'import json, sys; print(json.load(sys.stdin)[\"$1\"])'"
}
# forget what VintageHive cached itself, so the next request reaches the archive cache
clear_vh_cache() {
  dc exec -T gateway sqlite3 /var/lib/retronet/vintagehive/data/cache.db "DELETE FROM wayback; DELETE FROM waybackavailability;"
}
# GET from the archive cache inside the gateway: prints the status
acget() {
  dc exec -T gateway python3 -c "import urllib.request, urllib.error
try: print(urllib.request.urlopen('http://127.0.0.1:8890$1').status)
except urllib.error.HTTPError as e: print(e.code)"
}

cleanup() {
  if [ $failed -ne 0 ] || [ "${SHOW_LOGS:-0}" = 1 ]; then
    echo "# gateway log (last 150 lines)"
    dc logs --no-color --tail 150 gateway 2>&1 | sed 's/^/#   /'
    echo "# nftables counters"
    dc exec -T gateway nft list table inet retronet 2>&1 | grep -E 'counter packets [1-9]' | sed 's/^/#   /'
  fi
  [ "${KEEP:-0}" = 1 ] || dc down -v --remove-orphans >/dev/null 2>&1
  rm -rf "$tmp"
}
trap cleanup EXIT

echo "# build"
start=$(date +%s)
dc build gateway fakenet || { nok "build"; exit 1; }
echo "# built in $(( $(date +%s) - start )) s"

dc down -v --remove-orphans >/dev/null 2>&1 # leftovers of a KEEP=1 run
echo "# start the gateway (archive cache offline), the fake internet and the LAN canary"
if ! dc up -d --wait --wait-timeout 180 gateway fakenet canary; then
  nok "the gateway became healthy"; exit 1
fi
ok "the gateway is healthy"

dc exec -T gateway retronet-user add alice alice123 && dc exec -T gateway retronet-user add bob bob123 \
  && ok "two accounts created with retronet-user" || nok "retronet-user add"
out=$(tar -C test/dataset -czf - v1 | dc exec -T gateway retronet-archive import -)
expect "the synthetic dataset imported into the archive cache ($out)" grep -q '"added": 8' <<<"$out"

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
dc run --rm -T client /opt/retronet-test/cache-tests.sh offline
rc=$?
[ $rc -eq 0 ] && ok "the retro client's offline cache checks passed" || nok "the retro client's offline cache checks failed (exit $rc)"

echo "# LAN side"
for port in 1990 80 53 5190 8890 22; do
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

echo "# archive cache, offline"
expect "nothing reached the upstream stub while offline" test "$(stub all)" = 0
expect "the archive cache answered from its store ($(acstat hits) hits, $(acstat upstream_requests) upstream requests)" \
  test "$(acstat hits)" -gt 0 -a "$(acstat upstream_requests)" = 0

echo "# egress: only the archive cache reaches the web"
probe_as() { dc exec -T gateway setpriv --reuid="$1" --regid="$1" --init-groups timeout 5 bash -c "exec 3<>/dev/tcp/$2/80" >/dev/null 2>&1; }
if probe_as vintagehive 192.88.99.10; then nok "VintageHive's user can open port 80 on the internet"; else ok "VintageHive's user cannot open port 80 on the internet (the stub)"; fi
if probe_as archivecache 192.88.99.10; then ok "the archive cache's user can"; else nok "the archive cache's user cannot reach the upstream"; fi
if probe_as archivecache 192.168.98.10; then nok "the archive cache's user reaches the LAN canary"; else ok "the archive cache's user cannot reach the LAN canary"; fi
rules=$(dc exec -T gateway nft list chain inet retronet output)
vh_uid=$(dc exec -T gateway id -u vintagehive | tr -d '\r')
expect "no rule lets VintageHive out except to ProtoWeb's port 7851" \
  bash -c "[ \"\$(grep -E 'skuid (vintagehive|$vh_uid) ' <<<\"\$1\" | grep -v 'oifname \"lo\"' | grep -vc 'dport 7851')\" = 0 ]" _ "$rules"

echo "# stop and start"
web_before=$(acstat web)
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
expect "the archive store survives the restart ($web_before captures)" test "$(acstat web)" = "$web_before"

echo "# archive cache, online (gateway recreated)"
export RETRONET_TEST_ARCHIVE_MODE=online
if dc up -d --wait --wait-timeout 120 gateway >/dev/null 2>&1; then
  ok "the gateway is recreated with the archive cache online"
else
  nok "the gateway did not come back online"
fi
clear_vh_cache
dc run --rm -T client /opt/retronet-test/cache-tests.sh online
rc=$?
[ $rc -eq 0 ] && ok "the retro client's online cache checks passed" || nok "the retro client's online cache checks failed (exit $rc)"
expect "the miss went upstream once: one lookup, one page, one image" \
  test "$(stub 'cdx http://stub.example.com/')$(stub 'web http://stub.example.com/')$(stub 'web http://stub.example.com/stub.gif')" = 111
expect "the 429 was retried once (two lookups for busy.example.com)" test "$(stub 'cdx http://busy.example.com/')" = 2
expect "the dataset's page did not go upstream" test "$(stub 'cdx http://www.example.com/')" = 0
upstream_before=$(stub all)
clear_vh_cache
dc run --rm -T client /opt/retronet-test/cache-tests.sh again
rc=$?
[ $rc -eq 0 ] && ok "the retro client's repeat checks passed" || nok "the retro client's repeat checks failed (exit $rc)"
expect "the second request was served from the store, without an upstream request" test "$(stub all)" = "$upstream_before"

echo "# warm-up"
out=$(dc exec -T gateway retronet-warm --requisites http://warm.example.com/ http://nothing.example.com/)
sed 's/^/#   /' <<<"$out"
expect "retronet-warm archives a page and its image" grep -q 'archived *http://warm.example.com/ .*requisites 1/1' <<<"$out"
expect "retronet-warm reports what is not archived" grep -q 'not archived *http://nothing.example.com/' <<<"$out"
dc exec -T gateway retronet-warm http://nothing.example.com/ >/dev/null
expect "\"not archived\" is cached too (one upstream lookup for two warm-ups)" test "$(stub 'cdx http://nothing.example.com/')" = 1

echo "# export and import"
dc exec -T gateway retronet-archive export - > "$tmp/store.tgz"
web=$(acstat web) cdx=$(acstat cdx)
expect "export writes the store ($(wc -c < "$tmp/store.tgz") bytes, $web captures, $cdx lookups)" test -s "$tmp/store.tgz"
dc exec -T gateway retronet-archive purge --yes >/dev/null
expect "purge empties the store" test "$(acstat web)" = 0
out=$(dc exec -T gateway retronet-archive import - < "$tmp/store.tgz")
expect "import restores it ($out)" test "$(acstat web)" = "$web" -a "$(acstat cdx)" = "$cdx"
upstream_before=$(stub all)
expect "an imported capture is served" test "$(acget '/web/19990605120000if_/http://warm.example.com/')" = 200
expect "... from the store, without an upstream request" test "$(stub all)" = "$upstream_before"
if printf 'not a tarball' | dc exec -T gateway retronet-archive import - >/dev/null 2>&1; then
  nok "import accepted garbage"
else
  ok "import refuses garbage"
fi

echo "1..$n"
echo "# image: $(docker image inspect retronet-gateway:local --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1000000}')"
[ $failed -eq 0 ] || { echo "# $failed of $n failed"; exit 1; }
echo "# all $n passed"
