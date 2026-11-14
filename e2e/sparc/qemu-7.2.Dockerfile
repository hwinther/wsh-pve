# The sparc lab with an upstream QEMU, 7.2.0 by default: the version the sparc guests ran on before
# the ESP and ESCC fixes, kept for comparing against the published build. QEMU_REF takes any git tag
# or commit.
#
# Build the lab image (Dockerfile) first; this one adds the upstream binaries to it:
#   docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .
#   docker build -f e2e/sparc/qemu-7.2.Dockerfile -t wsh-sparc-lab:7.2.0 e2e/sparc
#
# QEMU 7.2 is built on Debian 12, which builds it as is; on Debian 13 it needs extra fixes.
ARG LAB_IMAGE=wsh-sparc-lab

FROM debian:12 AS build
ARG QEMU_REF=v7.2.0
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ninja-build python3 python3-venv pkg-config git ca-certificates \
      libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libpng-dev flex bison
RUN git clone https://gitlab.com/qemu-project/qemu.git /src && git -C /src checkout "$QEMU_REF"
WORKDIR /src/build
RUN ../configure --prefix=/usr/local --target-list=sparc-softmmu,sparc64-softmmu --disable-docs --disable-werror \
      --disable-gtk --disable-sdl --disable-vnc --disable-opengl --enable-png \
    && ninja qemu-system-sparc qemu-system-sparc64 qemu-img

FROM ${LAB_IMAGE}
RUN apt-get update && apt-get install --no-install-recommends --assume-yes \
        libglib2.0-0t64 libpixman-1-0 libfdt1 zlib1g libpng16-16t64 \
    && rm -rf /var/lib/apt/lists/*
# /usr/local/bin comes first in PATH, so the scenarios' qemu-system-sparc is this one.
COPY --from=build /src/build/qemu-system-sparc /src/build/qemu-system-sparc64 /src/build/qemu-img /usr/local/bin/
# OpenBIOS plus the framebuffers' FCode ROMs: without QEMU,cgthree.bin OpenBIOS can't create the cg3 node
# ("Invalid FCode start byte" at SBus slot 3) and Solaris sees no framebuffer at all.
COPY --from=build /src/pc-bios/openbios-sparc32 /src/pc-bios/openbios-sparc64 \
     /src/pc-bios/QEMU,cgthree.bin /src/pc-bios/QEMU,tcx.bin /usr/local/share/qemu/
# The Sun PROMs are not in upstream QEMU; the lab image has them from the published package.
RUN cp /usr/share/kvm/ss5.bin /usr/share/kvm/ss10_v2.25_rom /usr/share/kvm/ss20_v2.25_rom /usr/local/share/qemu/
ENV LAB_FIRMWARE=/usr/local/share/qemu
