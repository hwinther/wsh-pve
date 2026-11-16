# openbios-sparc32 and the cg3 FCode ROM (QEMU,cgthree.bin) built from the OpenBIOS commit that QEMU
# ships, with the patches in patches/. debian/rules (pve-qemu.patch) installs each over QEMU's
# prebuilt image when build/openbios has it.
#
# openbios-sparc64 is built from the same commit as an optional extra: with every patch in patches/,
# including those named *-sparc64-*, which the sparc32 build leaves out. If that build fails the
# image still has the sparc32 files and no openbios-sparc64, and the package keeps QEMU's.
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
COPY patches/ /patches/
# sparc64: a copy of the clean tree, before the sparc32 build touches it
RUN cp -a /src /src64
WORKDIR /src
# The build tokenizes drivers/cgthree.fs (toke) into obj-sparc32/QEMU,cgthree.bin
RUN git apply $(ls /patches/*.patch | grep -v -- '-sparc64-') \
    && ./config/scripts/switch-arch sparc32 \
    && make build-verbose \
    && mkdir /out \
    && cp obj-sparc32/openbios-builtin.elf /out/openbios-sparc32 \
    && cp obj-sparc32/QEMU,cgthree.bin /out/
WORKDIR /src64
RUN if git apply /patches/*.patch \
        && ./config/scripts/switch-arch sparc64 \
        && make build-verbose; then \
      cp obj-sparc64/openbios-builtin.elf /out/openbios-sparc64; \
    else \
      echo "WARNING: openbios-sparc64 not built, the package keeps QEMU's"; \
    fi

FROM scratch
COPY --from=build /out/ /
