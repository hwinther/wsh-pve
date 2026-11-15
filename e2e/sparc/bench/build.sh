#!/bin/sh
# Build the bench disk in the build guest (Solaris 2.6 with gcc 2.95.3, README "The bench disk"):
#   sh <cd>/bench/build.sh [<cd>] [<disk>]     (defaults: the CD this script is on, c0t4d0)
# Compiles the benchmarks from the hand-over CD's sources with fixed flags, newfs's slice 0 of <disk>
# (a blank disk with a Sun label, bench/sunlabel.py) and puts the binaries, the sources as downloaded,
# run.sh and the README on it. Prints COMPILE <name> <seconds> (guest wall time of each compile) and
# ends with BUILD-OK or BUILD-FAILED <reason>.
CD=${1:-`cd \`dirname $0\`/.. && pwd`}
DISK=${2:-c0t4d0}
# Plain SPARC V8 (umul/udiv; microSPARC-II and SuperSPARC are both V8), no -mcpu=supersparc tuning
CFLAGS="-O2 -mcpu=v8"
PATH=/usr/local/bin:/usr/ccs/bin:/usr/xpg4/bin:/usr/bin:/usr/sbin; export PATH
W=/export/home/bench-build
M=/benchdisk
LMB="lat_syscall lat_sig lat_pipe lat_proc hello lat_pagefault lat_mmap bw_file_rd bw_mem lat_mem_rd lat_fs"

fail() { echo "BUILD-FAILED $*"; exit 1; }
# timed <name> <shell command>: run it (output to $W/<name>.log), print COMPILE <name> <seconds>
timed() {
  /usr/bin/time sh -c "$2" > $W/$1.log 2> $W/$1.time || { tail -20 $W/$1.log; fail "$1, see $W/$1.log"; }
  nawk -v n=$1 '$1 == "real" { k = split($2, p, ":"); s = (k == 2) ? p[1] * 60 + p[2] : p[1]; print "COMPILE " n " " s }' $W/$1.time | tee -a $W/compile.times
}

[ -x /usr/local/bin/gcc ] || fail "no /usr/local/bin/gcc: boot the build disk"
[ -f $CD/src/dhry-c ] || fail "no $CD/src/dhry-c: mount the hand-over CD"
rm -rf $W; mkdir -p $W/bin $W/dhry || fail "mkdir $W"
# compat251.o: fstat64 from fstat, so the static binaries also run on Solaris 2.5.1 (compat251.c)
gcc $CFLAGS -c -o $W/compat251.o $CD/bench/compat251.c || fail "compat251.c"
C=$W/compat251.o
cd $W/dhry && sh $CD/src/dhry-c 2>/dev/null
# The only source change: drop dhry_1.c's K&R `extern int times ();`, which clashes with the prototype
# in Solaris's <sys/times.h> (Dhrystone's README_C asks for the times() declaration to be adapted).
sed '/^extern *int *times *();/d' dhry_1.c > dhry_1s.c
[ `wc -l < dhry_1.c` -eq `expr \`wc -l < dhry_1s.c\` + 1` ] || fail "dhry_1.c: times() declaration not found"
timed dhry "gcc $CFLAGS -static -DHZ=100 -o $W/bin/dhry dhry_1s.c dhry_2.c $C"
cd $W && timed whetstone "gcc $CFLAGS -static -o $W/bin/whetstone $CD/src/whetstone.c $C -lm"
cd $W && timed hanoi "gcc $CFLAGS -static -o $W/bin/hanoi $CD/src/hanoi.c $C"
cd $W && tar xf $CD/src/nbench-byte-2.2.3.tar && cd nbench-byte-2.2.3 || fail "nbench tar"
timed nbench "make CC=gcc CFLAGS='-s -static -Wall $CFLAGS' LINKFLAGS=$C"
cp nbench $W/bin || fail "nbench"
cd $W && tar xf $CD/src/lmbench-3.0-a9.tar && cd lmbench-3.0-a9/src || fail "lmbench tar"
O=../bin/sparc-sun-solaris2.6
T=; for b in $LMB; do T="$T $O/$b"; done
timed lmbench "env CC=gcc CFLAGS='$CFLAGS -static' OS=sparc-sun-solaris2.6 MAKE=make ../scripts/build $T"
# Link each program again with compat251.o: lmbench's own link lines (from its log) plus the object
# (in CFLAGS it would break the Makefile's gcc -S steps)
grep -E "^gcc .* -o $O/[a-z_]+ [a-z_]+\.c( |$)" $W/lmbench.log > $W/lmbench.links
[ `wc -l < $W/lmbench.links` -eq `echo $LMB | wc -w` ] || fail "lmbench: link lines in lmbench.log"
while read cmd; do eval "$cmd $C" || fail "lmbench: $cmd $C"; done < $W/lmbench.links
for b in $LMB; do cp $O/$b $W/bin || fail "lmbench $b"; done

# The disk: drvconfig + disks make the /dev links for a target the install didn't see
drvconfig; disks
[ -c /dev/rdsk/${DISK}s0 ] || fail "no /dev/rdsk/${DISK}s0"
echo y | newfs /dev/rdsk/${DISK}s0 > $W/newfs.log 2>&1 || fail "newfs: `tail -2 $W/newfs.log`"
mkdir -p $M && mount -F ufs /dev/dsk/${DISK}s0 $M || fail "mount"
mkdir $M/bin $M/nbench $M/src
cp $W/bin/* $M/bin
cp $CD/src/dhry-c $CD/src/whetstone.c $CD/src/hanoi.c $CD/src/timeit.c $CD/src/nbench-byte-2.2.3.tar.gz $CD/src/lmbench-3.0-a9.tgz $M/src
cp $W/nbench-byte-2.2.3/NNET.DAT $M/nbench && cp $CD/bench/nbench.cfg $M/nbench/NBENCH.CFG
cp $CD/bench/run.sh $CD/bench/lmbench.sh $CD/bench/README $CD/bench/SOURCES $M && cp $CD/bench/compat251.c $M/src
{
  echo "Built `date` on `uname -a`"
  echo; echo "CFLAGS (Dhrystone, Whetstone; nbench adds -s -Wall, all link -static): $CFLAGS"
  echo "Dhrystone: -DHZ=100 (times(), TIMES is dhry.h's default)"
  echo "lmbench: `grep 'gcc .*-c lib_timing.c' $W/lmbench.log | head -1`"
  echo; gcc -v 2>&1
  echo; echo "Compile times (guest wall seconds, on the build machine):"; cat $W/compile.times
  echo; cd $M/bin && ls -l
} > $M/BUILDINFO
chmod -R a+rX $M
cd /
BENCH_TARGET=3 sh $M/run.sh dhry | grep 'BENCH dhry_dps' || fail "dhry doesn't run from the disk"
umount $M || fail "umount"
echo BUILD-OK
