#!/bin/sh
# Build the Linux side of the bench disk's network tests (bench/README, "Network") in the lab image:
#   sh peer-build.sh <lmbench-3.0-a9.tgz> <out dir>
# lmbench's own scripts/build, the sources unmodified. Two build-environment settings only, for a
# current Debian: -std=gnu89 (gcc 14 rejects lmbench's K&R-style implicit declarations by default)
# and libtirpc for <rpc/rpc.h> and pmap_* (glibc has dropped Sun RPC), through a compiler wrapper
# because scripts/build sets LDLIBS itself.
set -e
TGZ=$1
OUT=$2
W=`mktemp -d`
printf '#!/bin/sh\nexec gcc -std=gnu89 -I/usr/include/tirpc "$@" -ltirpc\n' > $W/lmcc
chmod +x $W/lmcc
cd $W && tar xzf $TGZ && cd lmbench-3.0-a9/src
O=../bin/linux
env CC=$W/lmcc CFLAGS=-O2 OS=linux MAKE=make ../scripts/build $O/bw_tcp $O/lat_tcp $O/lat_udp > $W/build.log 2>&1 \
  || { tail -30 $W/build.log; exit 1; }
mkdir -p $OUT
cp $O/bw_tcp $O/lat_tcp $O/lat_udp $OUT
grep -m1 'lib_timing.c' $W/build.log | sed "s|^$W/lmcc|lmcc|" > $OUT/BUILDINFO
rm -rf $W
