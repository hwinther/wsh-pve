# lmbench 3.0-a9's network tests, sourced by run.sh ($BIN, $T set) with NETPART set (Bourne sh's `.`
# takes no arguments):
#   lo    over the loopback interface (lo0): server and client both in the guest
#   nic   over le0 to the peer outside the guest at $BENCH_PEER, whose servers (lmbench on Linux)
#         bench-disk.py starts and stops; it also measures the guest-to-peer direction of bw_tcp
#         itself (nic_bw_out), since that needs the server in the guest
# Each server forks into the background (-s) and is stopped with -S <host>. Every client and stop runs
# at most NET_TIMEOUT seconds and is killed after that (a BENCH-ERROR), so a test that loops can't
# hang the run. lmbench's defaults otherwise: 1-byte transactions, bw_tcp 64 KB messages after its
# 7.5 s warm-up; ENOUGH as in lmbench.sh.
ENOUGH=100000; export ENOUGH
NT=${NET_TIMEOUT:-120}

# bounded <file> <command...>: run it in the background with its output in <file>, kill it after NT s
bounded() {
  f=$1; shift
  "$@" > $f 2>&1 &
  p=$!
  ( sleep $NT; kill $p 2>/dev/null && echo "killed after $NT s" >> $f ) &
  k=$!
  wait $p
  kill $k 2>/dev/null
}
# net <name> <unit> <command...>: the number in the last line of the client's output, as lmbench.sh's lm
net() {
  n=$1; u=$2; shift 2
  bounded $T/net.out "$@"
  v=`nawk 'NF { l = $0 } END { n = split(l, f, /[ :]+/); for (i = n; i > 0; i--) if (f[i] ~ /^[0-9.]+$/) { print f[i]; exit } }' $T/net.out`
  if grep 'killed after' $T/net.out >/dev/null; then v=; fi
  case "$v" in
    "" | -*) echo "BENCH-ERROR $n `tail -2 $T/net.out | tr '\n' ' '`" ;;
    *) echo "BENCH $n $v $u" ;;
  esac
}
# server <program>: start its server in the guest; stop <program>: shut it down again
server() { bounded $T/srv.out $BIN/$1 -s; sleep 1; }
stop() { bounded $T/srv.out $BIN/$1 -S localhost; }

case $NETPART in
lo)
  server lat_tcp; net lm_tcp us $BIN/lat_tcp localhost; stop lat_tcp
  server lat_udp; net lm_udp us $BIN/lat_udp localhost; stop lat_udp
  server lat_connect; net lm_connect us $BIN/lat_connect localhost; stop lat_connect
  server bw_tcp; net lm_tcp_bw MB/s $BIN/bw_tcp localhost; stop bw_tcp
  # Sun RPC through rpcbind (started at boot by /etc/init.d/rpc)
  server lat_rpc
  net lm_rpc_tcp us $BIN/lat_rpc -p tcp localhost
  net lm_rpc_udp us $BIN/lat_rpc -p udp localhost
  stop lat_rpc
  ;;
nic)
  if [ -z "$BENCH_PEER" ]; then
    echo "BENCH-SKIP nic_tcp nic_udp nic_bw_in nic_bw_out: no NIC peer (BENCH_PEER not set)"
  else
    net nic_tcp us $BIN/lat_tcp $BENCH_PEER
    net nic_udp us $BIN/lat_udp $BENCH_PEER
    net nic_bw_in MB/s $BIN/bw_tcp $BENCH_PEER
  fi
  ;;
esac
