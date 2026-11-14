# The sparc lab: qemu-system-sparc from the published pve-qemu-kvm (the build users run), plus the
# harness that drives a guest through its serial console and framebuffer (lab.py).
#
# Build context: the repository root (for the keyrings).
#   docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .
#
# qemu-7.2.Dockerfile builds on this image with an upstream QEMU (7.2.0 by default) for comparisons.
FROM debian:13
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg python3 python3-pil \
        python3-pyte tesseract-ocr fonts-dejavu-core xz-utils \
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
# The firmware directory qemu-server passes as -L (openbios-sparc32/64, ss5.bin, ss10/ss20 PROMs).
ENV LAB_FIRMWARE=/usr/share/kvm

COPY e2e/sparc/ /lab/
WORKDIR /lab
ENTRYPOINT ["python3", "/lab/lab.py"]
