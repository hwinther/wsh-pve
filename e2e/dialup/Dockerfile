# dialup-test: reproduce and regression-test emulated modem dial-up from a QEMU guest's serial port.
#   docker build -t dialup-test .
#   docker run --rm --device /dev/kvm --device /dev/ppp --cap-add NET_ADMIN -v $PWD/results:/results dialup-test
# (/dev/kvm optional -> TCG; /dev/ppp + NET_ADMIN only needed for the pppd-server scenario)
FROM debian:13

ARG ATDUCK_COMMIT=352c5f9
ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates git perl libio-pty-perl ppp socat iptables iproute2 procps psmisc hostname \
      python3 telnet qemu-system-x86 linux-image-amd64 busybox-static cpio xz-utils \
      dpkg-dev build-essential devscripts quilt \
 && apt-get build-dep -y slirp \
 && rm -rf /var/lib/apt/lists/*

# slirp: keep the stock Debian binary for the "bug reproduced" scenario, build a patched package
COPY patches/ /patches/
RUN mkdir -p /src && cd /src && apt-get update && apt-get source slirp && apt-get download slirp \
 && dpkg-deb -x slirp_*_amd64.deb /opt/slirp-stock \
 && cd slirp-1.0.17 \
 && cp /patches/slirp-64bit-select-timeout.patch debian/patches/018_64bit_select_timeout.patch \
 && cp /patches/slirp-ppp-fakeip.patch debian/patches/019_nandhp_ppp_fakeip.patch \
 && printf '018_64bit_select_timeout.patch\n019_nandhp_ppp_fakeip.patch\n' >> debian/patches/series \
 && DEBEMAIL=dialup@localhost DEBFULLNAME=dialup dch -l +dialup "Fix select() EINVAL exit on 64-bit; add nandhp PPP fakeip patch." \
 && dpkg-buildpackage -b -uc -us \
 && dpkg -i ../slirp_*+dialup*_amd64.deb \
 && cp ../slirp_*+dialup*_amd64.deb /opt/ \
 && rm -rf /var/lib/apt/lists/*

# atduck with a restricted dial plan
COPY files/ /files/
RUN git clone https://github.com/nandhp/atduck /opt/atduck && cd /opt/atduck && git checkout -q $ATDUCK_COMMIT \
 && cp lib/ATduck/DialPlan.pm /opt/DialPlan.pm.orig \
 && sed '/^__DATA__$/q' /opt/DialPlan.pm.orig > lib/ATduck/DialPlan.pm \
 && cat /files/dialplan-restricted.txt >> lib/ATduck/DialPlan.pm \
 && perl -Ilib -c lib/ATduck/DialPlan.pm \
 && install -m 755 /files/isp-pppd /usr/local/sbin/isp-pppd \
 && install -m 644 /files/peers-dialup-isp /etc/ppp/peers/dialup-isp \
 && printf 'dialup\t*\tsecret\t*\n' > /etc/ppp/pap-secrets && printf 'dialup\t*\tsecret\t*\n' > /etc/ppp/chap-secrets \
 && chmod 600 /etc/ppp/pap-secrets /etc/ppp/chap-secrets

# test harness + tiny guest (Debian kernel + busybox + pppd as an initramfs)
COPY scripts/run-guest.sh scripts/cpu-sampler.sh scripts/cpu-summary.sh scripts/dialup-test.sh scripts/inner.sh scripts/raw-serial-test.sh /usr/local/bin/
COPY scripts/build-guest.sh /guest-src/build-guest
COPY scripts/guest-init /guest-src/init
RUN chmod +x /usr/local/bin/*.sh && sh /guest-src/build-guest

VOLUME /results
ENTRYPOINT ["/usr/local/bin/dialup-test.sh"]
