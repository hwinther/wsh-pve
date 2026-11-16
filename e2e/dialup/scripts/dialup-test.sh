#!/bin/sh
# dialup-test.sh - end-to-end regression test for emulated dial-up (QEMU 16550 socket -> atduck -> ISP side).
# Scenarios:
#   stock   : Debian's unpatched /usr/bin/slirp on 5555           -> expected to FAIL (reproduces the hang)
#   slirp   : patched slirp on 5555 (64-bit select fix + fakeip)  -> must PASS (guest gets IP, fetches URL)
#   pppd    : real pppd server, PAP login, on 5557 + NAT          -> must PASS (needs --cap-add NET_ADMIN --device /dev/ppp)
#   redial  : patched slirp, hang up with +++ATH, dial again      -> must PASS
# env: SCENARIOS (default "stock slirp pppd redial"), RESULTS (default /results), URL, ACCEL
RESULTS=${RESULTS:-/results}; mkdir -p $RESULTS
SCENARIOS=${SCENARIOS:-stock slirp pppd redial}
rc=0; summary=""
note() { summary="$summary
$1"; echo "$1"; }
for s in $SCENARIOS; do
  echo "=================== scenario $s"
  case $s in
    stock)
      OUT=$RESULTS/stock QUICK=1 run-guest.sh /opt/slirp-stock/usr/bin/slirp > $RESULTS/stock.txt 2>&1
      if grep -q "FETCH OK" $RESULTS/stock/console.log; then note "stock : UNEXPECTED PASS (bug not reproduced)"; rc=1
      elif grep -q "Loopback detected\|looped back" $RESULTS/stock/console.log && grep -q "NO CARRIER" $RESULTS/stock/atduck.log; then
        note "stock : bug reproduced as expected (slirp exited, atduck NO CARRIER, modem echoes PPP -> 'Serial line is looped back')"
      else note "stock : failed in an unexpected way, see $RESULTS/stock/"; rc=1; fi ;;
    slirp)
      OUT=$RESULTS/slirp run-guest.sh /usr/bin/slirp > $RESULTS/slirp.txt 2>&1
      if grep -q "FETCH OK" $RESULTS/slirp/console.log; then note "slirp : PASS ($(grep -o 'inet [0-9.]* peer [0-9.]*' $RESULTS/slirp/console.log | head -1))"
      else note "slirp : FAIL, see $RESULTS/slirp/"; rc=1; fi ;;
    pppd)
      if [ ! -w /dev/ppp ]; then note "pppd  : SKIPPED (no /dev/ppp; run with --device /dev/ppp --cap-add NET_ADMIN)"; continue; fi
      iptables -t nat -C POSTROUTING -s 10.0.3.0/24 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.0.3.0/24 -j MASQUERADE || { note "pppd  : SKIPPED (no NET_ADMIN for NAT)"; continue; }
      OUT=$RESULTS/pppd NUM=5557 run-guest.sh /usr/bin/slirp dial.user=dialup > $RESULTS/pppd.txt 2>&1
      cp /var/log/dialup-pppd.log $RESULTS/pppd/server-pppd.log 2>/dev/null
      if grep -q "FETCH OK" $RESULTS/pppd/console.log && grep -q "PAP peer authentication succeeded" /var/log/dialup-pppd.log; then
        note "pppd  : PASS (PAP login, $(grep -o 'inet [0-9.]* peer [0-9.]*' $RESULTS/pppd/console.log | head -1))"
      else note "pppd  : FAIL, see $RESULTS/pppd/"; rc=1; fi ;;
    redial)
      OUT=$RESULTS/redial QUICK=1 run-guest.sh /usr/bin/slirp dial.redial=1 dial.disc=1 > $RESULTS/redial.txt 2>&1
      if grep -q "REDIAL FETCH OK" $RESULTS/redial/console.log; then note "redial: PASS (+++ATH0 hang-up, second call works)"
      else note "redial: FAIL, see $RESULTS/redial/"; rc=1; fi ;;
  esac
done
echo "=================== summary$summary"
for s in slirp pppd; do [ -f $RESULTS/$s.txt ] && { echo "--- $s numbers"; grep -E "DOWNLOAD|UPLOAD|round-trip|tiny-GET 5|^CPU" $RESULTS/$s.txt; }; done
exit $rc
