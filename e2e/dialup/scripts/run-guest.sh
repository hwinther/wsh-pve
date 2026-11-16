#!/bin/sh
# End-to-end: QEMU guest (modem on COM1 = PVE "serial0: socket") dials atduck, which runs the ISP side.
# usage: run-guest.sh <slirp-binary | pppd-server> [extra kernel cmdline]
#   env: OUT (log dir), NUM (dial number, default 5555), BAUD, ACCEL (kvm|tcg), URL (fetched through the link),
#        QUICK=1 (skip latency/throughput part)
ISP=${1:-/usr/bin/slirp}; shift
OUT=${OUT:-/tmp/guest}; rm -rf $OUT; mkdir -p $OUT
NUM=${NUM:-5555}; BAUD=${BAUD:-115200}
ACCEL=${ACCEL:-$( [ -w /dev/kvm ] && echo kvm || echo tcg )}
HOSTIP=$(hostname -I | awk '{print $1}')
pkill -f "perl ./atduck" ; pkill -f "^./slirp-nandhp"; pkill -x pppd; pkill -x qemu-system-x86; pkill -f "http.server 8000"; pkill -f "TCP-LISTEN:9000"; sleep 0.5
# test payloads + servers inside this container
mkdir -p /srv/www; [ -f /srv/www/r256k ] || head -c 262144 /dev/urandom > /srv/www/r256k; echo ok > /srv/www/tiny; echo "hello through the modem" > /srv/www/hello.txt
(cd /srv/www && python3 -m http.server 8000 >/dev/null 2>&1 &)
socat -u TCP-LISTEN:9000,reuseaddr,fork OPEN:/dev/null >/dev/null 2>&1 &
cd /opt/atduck
if [ -x "$ISP" ]; then ln -sf "$ISP" ./slirp-nandhp-patch; fi
rm -f /tmp/modem.sock
# Same chardev/device shape that PVE generates for "serial0: socket"
qemu-system-x86_64 -name dialup-guest,debug-threads=on -accel $ACCEL -smp 1 -m 256 -display none -no-reboot -nic none \
  -chardev socket,id=serial0,path=/tmp/modem.sock,server=on,wait=off -device isa-serial,chardev=serial0 \
  -chardev file,id=con,path=$OUT/console.log -device isa-serial,chardev=con \
  -kernel /guest/vmlinuz -initrd /guest/initrd.gz \
  -append "console=ttyS1 quiet panic=-1 dial.num=$NUM dial.baud=$BAUD dial.url=${URL:-http://$HOSTIP:8000/hello.txt} ${QUICK:+dial.quick=1}${QUICK:-dial.host=$HOSTIP} $*" &
QPID=$!
while [ ! -S /tmp/modem.sock ]; do sleep 0.2; done
./atduck ${ATDUCK_OPTS:--D} unix:/tmp/modem.sock > $OUT/atduck.log 2>&1 &
APID=$!
/usr/local/bin/cpu-sampler.sh $QPID > $OUT/cpu.samples &
S=$(date +%s)
wait $QPID
E=$(date +%s)
echo "guest ran $((E-S)) s"
kill $APID 2>/dev/null
grep DIALTEST $OUT/console.log
# CPU summary written by the sampler (see cpu-sampler in the same dir)
/usr/local/bin/cpu-summary.sh $OUT/cpu.samples
