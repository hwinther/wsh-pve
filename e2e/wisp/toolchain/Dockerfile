# wisp uClibc-ng cross toolchain, built with Buildroot: a real C library for wisp user programs
# (test binaries, later small network services) that need more than the kernel's nolibc gives
# wisp's own PID 1 (e2e/wisp/init.c stays on nolibc; see e2e/wisp/README.md, "A libc toolchain
# (uClibc-ng)"). Multi-stage: "build" runs Buildroot from source for one architecture; the final
# stage ships only the resulting toolchain, nothing Buildroot needed to build it.
#
#   docker build --build-arg WISP_ARCH=sparc32 \
#       --build-arg BUILDROOT_VERSION=<version> --build-arg BUILDROOT_SHA256=<sha256> \
#       -t wisp-toolchain-sparc32 e2e/wisp/toolchain
#   (build.sh wraps this and tags the image for GHCR; see build.sh)
#
# BUILDROOT_VERSION and BUILDROOT_SHA256 below are placeholders: REPLACE-ME. The maintainer picks
# a released Buildroot version from https://buildroot.org/downloads/ and its tarball's SHA-256
# (the matching buildroot-<version>.tar.gz.sign/.sha256 files there) and fills in both; this file
# does not guess either value, and building it unchanged fails (a 404, or a checksum mismatch).

FROM debian:13 AS build
ARG WISP_ARCH
ARG BUILDROOT_VERSION=REPLACE-ME
ARG BUILDROOT_SHA256=REPLACE-ME
ENV DEBIAN_FRONTEND=noninteractive

# Mandatory packages for a Buildroot build (the Buildroot manual, "System requirements"): a C and
# C++ compiler and the rest of build-essential, make, bash's usual tools (already in the base
# image) and, on top of a minimal Debian image: bc, bzip2, cpio, file, patch, perl, python3,
# rsync, unzip and xz-utils (uClibc-ng's own upstream tarball is .tar.xz; "which" comes with
# debianutils, which is Essential and already in the base image); wget and
# ca-certificates to fetch Buildroot and the sources it mirrors over https, and git because some
# Buildroot packages fetch from a repository instead of a tarball.
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes \
        build-essential bc bzip2 cpio file g++ make patch perl python3 rsync unzip wget git \
        ca-certificates xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /buildroot-src
RUN wget -q "https://buildroot.org/downloads/buildroot-${BUILDROOT_VERSION}.tar.gz" \
        -O "buildroot-${BUILDROOT_VERSION}.tar.gz" \
    && echo "${BUILDROOT_SHA256}  buildroot-${BUILDROOT_VERSION}.tar.gz" | sha256sum -c - \
    && tar -xzf "buildroot-${BUILDROOT_VERSION}.tar.gz" \
    && mv "buildroot-${BUILDROOT_VERSION}" buildroot \
    && rm "buildroot-${BUILDROOT_VERSION}.tar.gz"

# One of sparc32_uclibc_defconfig, sparc64_uclibc_defconfig, x86_64_uclibc_defconfig (this
# directory), picked by WISP_ARCH.
COPY ${WISP_ARCH}_uclibc_defconfig /buildroot-defconfig
WORKDIR /buildroot-src/buildroot

# "make sdk", not "make toolchain": Buildroot's internal toolchain is built for the paths of this
# build (under /buildroot-src/buildroot/output/host/...), and the final stage below moves it to
# /opt/wisp-toolchain/<arch>/, a different path than where it was built. "make sdk" (which builds
# the toolchain itself first, if it isn't built yet) packages host/ together with a
# relocate-sdk.sh script that rewrites the paths baked into the compiler's specs and sysroot
# references to wherever the SDK ends up unpacked, so the toolchain under /opt still finds its
# own headers and libraries. "make toolchain" alone would leave this build's own path hard-coded.
RUN make BR2_DEFCONFIG=/buildroot-defconfig defconfig \
    && make sdk

# verify: the sdk tarball's exact name and directory (Buildroot has used output/images/ with a
# toolchain-name-sdk.tar.gz-shaped file in recent releases, but the exact name depends on
# BUILDROOT_VERSION); the glob below is written to tolerate small naming differences, but check
# it once a version is chosen.
RUN mkdir -p "/opt/wisp-toolchain/${WISP_ARCH}" \
    && sdk_tarball=$(ls output/images/*sdk*.tar.gz 2>/dev/null | head -n 1) \
    && if [ -z "$sdk_tarball" ]; then sdk_tarball=$(ls output/images/*.tar.gz | head -n 1); fi \
    && tar -xzf "$sdk_tarball" -C "/opt/wisp-toolchain/${WISP_ARCH}" --strip-components=1 \
    && "/opt/wisp-toolchain/${WISP_ARCH}/relocate-sdk.sh"

FROM debian:13-slim AS final
ARG WISP_ARCH
ARG BUILDROOT_VERSION=REPLACE-ME
COPY --from=build /opt/wisp-toolchain/${WISP_ARCH} /opt/wisp-toolchain/${WISP_ARCH}
ENV PATH="/opt/wisp-toolchain/${WISP_ARCH}/bin:${PATH}"
LABEL org.opencontainers.image.description="wisp uClibc-ng toolchain (Buildroot ${BUILDROOT_VERSION}, ${WISP_ARCH})" \
      wisp.toolchain.buildroot-version="${BUILDROOT_VERSION}" \
      wisp.toolchain.arch="${WISP_ARCH}"
