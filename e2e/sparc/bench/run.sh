#!/bin/sh
# The bench disk's driver: runs the fixed benchmark set and prints one line per result,
#   BENCH <name> <value> <unit>
# between BENCH-BEGIN and BENCH-END (BENCH-ERROR <name> <reason> for a benchmark that failed), plus
# uname -a, psrinfo -v and the memory size. Only tools of the Solaris End User install are used, so it
# runs on any Solaris 2.5.1-9 sparc guest with the disk mounted (read only is fine), e.g. on /bench:
#   sh /bench/run.sh [only]     # only: run just the benchmarks whose name starts with it
# Files are written to $BENCH_TMP (default /var/tmp/bench, a UFS directory) and removed afterwards.
# The network tests run over lo0, and over le0 when BENCH_PEER names a host running lmbench's servers
# (bench-disk.py sets it up; README "Network"); without it the le0 tests are a BENCH-SKIP line.
B=`dirname $0`
BIN=$B/bin
T=${BENCH_TMP:-/var/tmp/bench}
ONLY=$1
PATH=/usr/bin:/usr/sbin:/sbin; export PATH
# Seconds each CPU benchmark aims for (the counts are scaled to it from a calibration run)
TARGET=${BENCH_TARGET:-20}

err() { echo "BENCH-ERROR $1 $2"; }
want() { [ -z "$ONLY" ] && return 0; case "$1" in "$ONLY"*) return 0;; esac; return 1; }
# user CPU seconds of the last `tm` command (from /usr/bin/time on stderr, into $T/time)
tm() { /usr/bin/time "$@" 2>$T/time; }
user() { nawk '$1 == "user" { print $2 }' $T/time; }
# scale count $1 that took $2 s to TARGET seconds
scale() { nawk -v n=$1 -v t=$2 -v g=$TARGET 'BEGIN { if (t < 0.1) t = 0.1; printf "%d\n", n * g / t }'; }

rm -rf $T; mkdir -p $T || exit 1
echo BENCH-BEGIN
uname -a
psrinfo -v
prtconf 2>/dev/null | grep Memory
echo "TARGET $TARGET"

# Dhrystone 2.1: runs read from stdin; calibrate until a run takes 2 s, then scale to TARGET.
if want dhry; then
  n=100000
  while :; do
    echo $n | tm $BIN/dhry >/dev/null; t=`user`
    [ `nawk -v t=$t 'BEGIN { print (t >= 2) }'` = 1 ] && break
    n=`expr $n \* 10`
    [ $n -gt 1000000000 ] && break
  done
  n=`scale $n $t`
  echo $n | $BIN/dhry > $T/dhry.out 2>&1
  dps=`nawk '/Dhrystones per Second:/ { print $NF }' $T/dhry.out`
  if [ -n "$dps" ]; then
    echo "BENCH dhry_runs $n runs"
    echo "BENCH dhry_dps $dps dhrystones/s"
    nawk -v d=$dps 'BEGIN { printf "BENCH dhry_mips %.1f VAX-MIPS\n", d / 1757 }'
  else
    err dhry "`tail -3 $T/dhry.out | tr '\n' ' '`"
  fi
fi

# Whetstone (netlib whetstone.c, double precision): its own timing has one-second resolution, so
# MWIPS = loops / (10 x user seconds) from /usr/bin/time (KIPS = 100 x loops / seconds).
if want whet; then
  n=1000
  while :; do
    tm $BIN/whetstone $n >/dev/null; t=`user`
    [ `nawk -v t=$t 'BEGIN { print (t >= 2) }'` = 1 ] && break
    n=`expr $n \* 10`
    [ $n -gt 100000000 ] && break
  done
  n=`scale $n $t`
  if tm $BIN/whetstone $n > $T/whet.out && grep "^Loops:" $T/whet.out >/dev/null; then
    t=`user`
    echo "BENCH whet_loops $n loops"
    nawk -v n=$n -v t=$t 'BEGIN { printf "BENCH whet_mwips %.1f MWIPS\n", n / (10 * t) }'
  else
    err whet "`tail -3 $T/whet.out | tr '\n' ' '`"
  fi
fi

# BYTE UNIX Benchmarks' Towers of Hanoi (10 disks: recursion deeper than the register windows):
# moves of the whole tower per second over TARGET seconds (alarm), as UnixBench's "lps".
if want hanoi; then
  $BIN/hanoi $TARGET > $T/hanoi.out 2>&1
  c=`nawk -F'|' '$1 == "COUNT" { print $2 }' $T/hanoi.out`
  if [ -n "$c" ]; then
    nawk -v c=$c -v t=$TARGET 'BEGIN { printf "BENCH hanoi_lps %.1f loops/s\n", c / t }'
  else
    err hanoi "`cat $T/hanoi.out`"
  fi
fi

# Not a recognised benchmark: the nawk loop of the lab's bench.py, the job that showed Solaris's
# microSPARC window-trap slowdown (SS-5 ~9x slower than SS-20); user seconds of 1,000,000 rounds.
if want nawk; then
  if tm nawk 'BEGIN { for (i = 0; i < 1000000; i++) s = (s + i * i) % 9973; print s }' > $T/nawk.out; then
    echo "BENCH nawk_s `user` s"
  else
    err nawk "`cat $T/nawk.out`"
  fi
fi

# nbench (BYTEmark 2.2.3): the fixed reduced configuration in nbench/NBENCH.CFG; the three indices against
# the AMD K6/233 baseline (MEMORY, INTEGER, FLOATING-POINT), the two original BYTEmark indices
# (Pentium 90 = 1) and iterations/s per test. A test whose runs vary too much gets nbench's "NOT 95 %
# statistically certain" warning and its numbers on a line of their own; nb_uncertain counts them.
# nbench's own output follows, each line starting with "# ".
if want nb; then
  ( cd $B/nbench && $BIN/nbench -cNBENCH.CFG ) > $T/nbench.out 2>&1
  if grep 'FLOATING-POINT INDEX' $T/nbench.out >/dev/null; then
    nawk -F: '
      function key(s) { gsub(/^ +| +$/, "", s); gsub(/[^A-Za-z]+/, "_", s); return tolower(s) }
      function num(s) { gsub(/ /, "", s); return s }
      /^(NUMERIC SORT|STRING SORT|BITFIELD|FP EMULATION|FOURIER|ASSIGNMENT|IDEA|HUFFMAN|NEURAL NET|LU DECOMPOSITION) *:/ {
        t = key($1); if (num($2) != "") { printf "BENCH nb_%s %s iter/s\n", t, num($2); t = "" } next }
      /^\*\* WARNING: The current test/ { u++ }
      /^ +:/ && t != "" { printf "BENCH nb_%s %s iter/s\n", t, num($2); t = "" }
      /^INTEGER INDEX/ { i++; printf "BENCH nb_%s %s index\n", (i == 1 ? "byte_int" : "int"), num($2) }
      /^FLOATING-POINT INDEX/ { f++; printf "BENCH nb_%s %s index\n", (f == 1 ? "byte_fp" : "fp"), num($2) }
      /^MEMORY INDEX/ { printf "BENCH nb_mem %s index\n", num($2) }
      END { printf "BENCH nb_uncertain %d tests\n", u }
    ' $T/nbench.out
  else
    err nbench "`tail -3 $T/nbench.out | tr '\n' ' '`"
  fi
  sed 's/^/# /' $T/nbench.out
fi

# lmbench 3.0-a9: a fixed subset (see README); microseconds, MB/s, operations/s.
if want lm && [ -x $BIN/lat_syscall ]; then
  . $B/lmbench.sh
fi

# lmbench's network tests (net.sh): over lo0 with the rest of lmbench, over le0 to $BENCH_PEER as nic_*
if [ -x $BIN/lat_tcp ]; then
  if want lm; then NETPART=lo; . $B/net.sh; fi
  if want nic; then NETPART=nic; . $B/net.sh; fi
fi

rm -rf $T
echo BENCH-END
