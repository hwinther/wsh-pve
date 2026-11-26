# wisp-netbsd, the NetBSD sibling of wisp: NetBSD's own sources and cross toolchain (built by its
# build.sh, no root), a memory-disk kernel per machine with a static PID 1, and the published
# pve-qemu-kvm to boot them.
#
# Build context: the repository root (for the keyrings).
#   docker build -f e2e/wisp-netbsd/Dockerfile -t wsh-wisp-netbsd .
#   docker run --rm -v "$PWD/build:/wisp-netbsd/build" -v "$PWD/out:/wisp-netbsd/out" wsh-wisp-netbsd ./build.sh sparc32
#   docker run --rm -v "$PWD/out:/wisp-netbsd/out" wsh-wisp-netbsd ./run.py --arch sparc32
#
# The NetBSD release's source sets from cdn.netbsd.org, each checked against the SHA-256 below
# (taken when the version was pinned, after checking the release's own source/sets/SHA512 file).
# src (userland, libc, build.sh and its tools), syssrc (the kernel), gnusrc (gcc and binutils for
# the cross toolchain), sharesrc (share/, which the tools build reads); not xsrc.

FROM debian:13 AS sources
ARG NETBSD_VERSION=11.1
ARG NETBSD_SRC_SHA256=f751b6a477ac9fda332fcca0f2518d2dfce0f0650153eecca497c2586f9351ca
ARG NETBSD_SYSSRC_SHA256=6452a0681e127cc05718364bc28a341e7d50a5895d21e27c0db11efbe4e4053e
ARG NETBSD_GNUSRC_SHA256=a41905b61c0483ef757f9051a21affb0b85917dd2ed83acbd24826efd128ef0f
ARG NETBSD_SHARESRC_SHA256=3db710b97a59c780e2599425d8519de7403c416c0c7d384009ca289e3759cc21
ENV DEBIAN_FRONTEND=noninteractive
# build.sh needs a host C and C++ compiler, make and the usual tools (BUILDING in the source tree);
# curl for the download, python3 for run.py.
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates curl gnupg python3 \
        gcc g++ libc6-dev make zlib1g-dev file xz-utils \
    && rm -rf /var/lib/apt/lists/*
# Download, check and unpack in one layer (3.7 GB unpacked; the tarballs don't stay in the image).
RUN base="https://cdn.netbsd.org/pub/NetBSD/NetBSD-${NETBSD_VERSION}/source/sets" \
    && mkdir -p /tmp/dl /usr/src/netbsd && cd /tmp/dl \
    && for set in src syssrc gnusrc sharesrc; do curl -fsSL --retry 3 -O "$base/$set.tgz"; done \
    && printf '%s  %s\n' \
        "$NETBSD_SRC_SHA256" src.tgz \
        "$NETBSD_SYSSRC_SHA256" syssrc.tgz \
        "$NETBSD_GNUSRC_SHA256" gnusrc.tgz \
        "$NETBSD_SHARESRC_SHA256" sharesrc.tgz | sha256sum -c - \
    && for set in src syssrc gnusrc sharesrc; do \
        tar -xzf "$set.tgz" -C /usr/src/netbsd --strip-components=2 && rm "$set.tgz"; done \
    && test -x /usr/src/netbsd/build.sh
ENV NETBSD_VERSION=${NETBSD_VERSION}
ENV NETBSDSRCDIR=/usr/src/netbsd

FROM sources
COPY proxmox-archive-keyring-trixie.gpg /usr/share/keyrings/proxmox-archive-keyring.gpg
COPY repo/conf/wsh-pve.gpg.key /tmp/wsh-pve.gpg.key
RUN gpg --dearmor < /tmp/wsh-pve.gpg.key > /usr/share/keyrings/wsh-pve.gpg \
    && printf 'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n' \
        > /etc/apt/sources.list.d/proxmox.sources \
    && printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
        > /etc/apt/sources.list.d/wsh-pve.sources \
    && printf 'Package: pve-qemu-kvm\nPin: origin debian.wshosting.no\nPin-Priority: 1001\n' > /etc/apt/preferences.d/wsh-pve \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes pve-qemu-kvm \
    && rm -rf /var/lib/apt/lists/*
# The firmware directory: openbios-sparc32/64 and SeaBIOS.
ENV WISP_FIRMWARE=/usr/share/kvm

# run.py reuses wisp's runner (e2e/wisp/run.py and what it imports).
COPY e2e/wisp/run.py e2e/wisp/shell.py e2e/wisp/tier2.py /wisp/
COPY e2e/wisp-netbsd/ /wisp-netbsd/
WORKDIR /wisp-netbsd
