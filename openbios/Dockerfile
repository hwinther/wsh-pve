# openbios-sparc32 and the cg3 FCode ROM (QEMU,cgthree.bin) built from the OpenBIOS commit that QEMU
# ships, with the patches in patches/. debian/rules (pve-qemu.patch) installs each over QEMU's
# prebuilt image when build/openbios has it.
#
#   docker build --output type=local,dest=build/openbios -f openbios/Dockerfile openbios
#
# OPENBIOS_REF must match roms/openbios in the QEMU that pve-qemu builds (11.1.3: e5ac46dd24).
FROM debian:13 AS build
ARG OPENBIOS_REF=e5ac46dd24e6216c36aa80462af25457e7029440
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc-sparc64-linux-gnu binutils-sparc64-linux-gnu fcode-utils xsltproc \
      git ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/openbios/openbios.git /src && git -C /src checkout "$OPENBIOS_REF"
WORKDIR /src
COPY patches/ /patches/
# The build tokenizes drivers/cgthree.fs (toke) into obj-sparc32/QEMU,cgthree.bin
RUN git apply /patches/*.patch \
    && ./config/scripts/switch-arch sparc32 \
    && make build-verbose \
    && mkdir /out \
    && cp obj-sparc32/openbios-builtin.elf /out/openbios-sparc32 \
    && cp obj-sparc32/QEMU,cgthree.bin /out/

FROM scratch
COPY --from=build /out/ /
