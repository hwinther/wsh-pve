#!/bin/sh
# Build a tiny Linux guest (Debian kernel + busybox + pppd/chat) as an initramfs.
# Output: /guest/vmlinuz, /guest/initrd.gz
set -e
K=$(ls /lib/modules | head -1)
R=/tmp/guestroot; rm -rf $R; mkdir -p $R/bin $R/sbin $R/etc/ppp $R/lib/modules $R/proc $R/sys $R/dev $R/tmp $R/run $R/var/run $R/var/lock $R/var/log $R/root
cp /bin/busybox $R/bin/busybox
for m in drivers/net/slip/slhc drivers/net/ppp/ppp_generic drivers/net/ppp/ppp_async drivers/net/ppp/bsd_comp drivers/net/ppp/ppp_deflate; do
  xz -dc /lib/modules/$K/kernel/$m.ko.xz > $R/lib/modules/$(basename $m).ko
done
# pppd + chat with their shared libraries
for b in /usr/sbin/pppd /usr/sbin/chat; do
  cp $b $R/sbin/
  for l in $(ldd $b | awk '/=>/ {print $3} /ld-linux/ {print $1}'); do
    mkdir -p $R$(dirname $l); cp -L $l $R$l
  done
done
mkdir -p $R/usr/lib/x86_64-linux-gnu/pppd; cp -a /usr/lib/x86_64-linux-gnu/pppd/* $R/usr/lib/x86_64-linux-gnu/pppd/ 2>/dev/null || true
mkdir -p $R/usr/lib/x86_64-linux-gnu/ossl-modules; cp -L /usr/lib/x86_64-linux-gnu/ossl-modules/legacy.so $R/usr/lib/x86_64-linux-gnu/ossl-modules/ 2>/dev/null || true
# glibc NSS for name lookups in the busybox wget (static glibc busybox uses its own resolver for nslookup only)
for l in /lib/x86_64-linux-gnu/libnss_dns.so.2 /lib/x86_64-linux-gnu/libnss_files.so.2 /lib/x86_64-linux-gnu/libresolv.so.2; do [ -e $l ] && cp -L $l $R$l || true; done
echo 'hosts: files dns' > $R/etc/nsswitch.conf
echo 'root:x:0:0:root:/root:/bin/sh' > $R/etc/passwd
echo 'root:x:0:' > $R/etc/group
cp /guest-src/init $R/init; chmod +x $R/init
mkdir -p /guest
cp /boot/vmlinuz-$K /guest/vmlinuz
(cd $R && find . | cpio -o -H newc 2>/dev/null | gzip -1) > /guest/initrd.gz
ls -la /guest
