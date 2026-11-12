# The sparc lab: qemu-system-sparc from the published pve-qemu-kvm (the build users run), plus the
# harness that drives a guest through its serial console and framebuffer (lab.py).
#
# Build context: the repository root (for the keyrings).
#   docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .
#
# QEMU_FROM=upstream builds an upstream QEMU (QEMU_REF, a git tag or commit) with only the sparc
# targets instead, for comparing versions:
#   docker build -f e2e/sparc/Dockerfile --build-arg QEMU_FROM=upstream --build-arg QEMU_REF=v7.2.0 \
#     -t wsh-sparc-lab:7.2.0 .
ARG QEMU_FROM=wsh

FROM debian:12 AS upstream-build
ARG QEMU_REF=v7.2.0
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ninja-build python3 python3-venv pkg-config git ca-certificates \
      libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libpng-dev flex bison
RUN git clone https://gitlab.com/qemu-project/qemu.git /src && git -C /src checkout "$QEMU_REF"
WORKDIR /src/build
RUN ../configure --prefix=/usr/local --target-list=sparc-softmmu,sparc64-softmmu --disable-docs --disable-werror \
      --disable-gtk --disable-sdl --disable-vnc --disable-opengl --enable-png \
    && ninja qemu-system-sparc qemu-system-sparc64 qemu-img

FROM debian:13 AS base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg python3 python3-pil \
        python3-pyte tesseract-ocr fonts-dejavu-core xz-utils \
    && rm -rf /var/lib/apt/lists/*

FROM base AS qemu-wsh
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

FROM base AS qemu-upstream
RUN apt-get update && apt-get install --no-install-recommends --assume-yes \
        libglib2.0-0t64 libpixman-1-0 libfdt1 zlib1g libpng16-16t64 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=upstream-build /src/build/qemu-system-sparc /src/build/qemu-system-sparc64 /src/build/qemu-img /usr/local/bin/
# OpenBIOS plus the framebuffers' FCode ROMs: without QEMU,cgthree.bin OpenBIOS can't create the cg3 node
# ("Invalid FCode start byte" at SBus slot 3) and Solaris sees no framebuffer at all.
COPY --from=upstream-build /src/pc-bios/openbios-sparc32 /src/pc-bios/openbios-sparc64 \
     /src/pc-bios/QEMU,cgthree.bin /src/pc-bios/QEMU,tcx.bin /usr/local/share/qemu/
# The Sun PROMs are not in upstream QEMU; take them from the published package.
COPY --from=qemu-wsh /usr/share/kvm/ss5.bin /usr/share/kvm/ss10_v2.25_rom /usr/share/kvm/ss20_v2.25_rom /usr/local/share/qemu/
ENV LAB_FIRMWARE=/usr/local/share/qemu

FROM qemu-${QEMU_FROM}
COPY e2e/sparc/ /lab/
WORKDIR /lab
ENTRYPOINT ["python3", "/lab/lab.py"]
