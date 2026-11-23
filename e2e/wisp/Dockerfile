# wisp, the tiny test system: a kernel and a one-program initramfs (PID 1 built with the kernel's nolibc)
# for x86_64, i386, sparc32 and sparc64, and the published pve-qemu-kvm to boot them.
#
# Build context: the repository root (for the keyrings).
#   docker build -f e2e/wisp/Dockerfile -t wsh-wisp .
#   docker run --rm -v "$PWD/out:/wisp/out" wsh-wisp ./build.sh all
#   docker run --rm -v "$PWD/out:/wisp/out" wsh-wisp ./run.py --arch sparc32
#
# The kernel source is Debian's linux-source from trixie-backports: nolibc gained sparc in 6.16,
# trixie itself has 6.12.
FROM debian:13
ENV DEBIAN_FRONTEND=noninteractive
RUN echo 'deb http://deb.debian.org/debian trixie-backports main' > /etc/apt/sources.list.d/backports.list \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg python3 make bc bison flex \
        cpio rsync squashfs-tools xz-utils libelf-dev libssl-dev gcc libc6-dev gcc-sparc64-linux-gnu gcc-i686-linux-gnu time \
    && apt-get install --no-install-recommends --assume-yes -t trixie-backports linux-source-7.3 \
    && rm -rf /var/lib/apt/lists/*

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

COPY e2e/wisp/ /wisp/
WORKDIR /wisp
