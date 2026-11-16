#!/bin/sh
# Raw QEMU 16550 <-> UNIX socket throughput, no modem emulator, no PPP.  usage: raw-serial-test.sh [baud]
BAUD=${1:-115200}
rm -f /tmp/modem.sock; head -c 262144 /dev/urandom > /tmp/rx.bin
qemu-system-x86_64 -accel kvm -smp 1 -m 256 -display none -no-reboot -nic none \
  -chardev socket,id=serial0,path=/tmp/modem.sock,server=on,wait=off -device isa-serial,chardev=serial0 \
  -chardev file,id=con,path=/tmp/raw.log -device isa-serial,chardev=con \
  -kernel /guest/vmlinuz -initrd /guest/initrd.gz -append "console=ttyS1 quiet panic=-1 dial.raw=1 dial.baud=$BAUD" & Q=$!
while [ ! -S /tmp/modem.sock ]; do sleep 0.1; done
python3 - <<'P'
import socket,time
s=socket.socket(socket.AF_UNIX); s.connect("/tmp/modem.sock")
n=0; t0=None
while n<262144:
    d=s.recv(65536)
    if not d: break
    if t0 is None: t0=time.time()
    n+=len(d)
dt=time.time()-t0; print("host received %d bytes from guest in %.2f s = %.1f kB/s" % (n,dt,n/dt/1000))
time.sleep(1)
data=open("/tmp/rx.bin","rb").read(); t0=time.time(); s.sendall(data); print("host sendall returned after %.2f s" % (time.time()-t0))
time.sleep(40)
P
wait $Q; grep DIALTEST /tmp/raw.log
