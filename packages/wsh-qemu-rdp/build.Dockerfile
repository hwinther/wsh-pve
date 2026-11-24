# The build image of the wsh-qemu-rdp package (packages/wsh-qemu-rdp/build.sh): Debian 13, pinned
# by digest (Dependabot bumps it), with debhelper, git (the upstream source is fetched at the pinned
# commit), the Rust toolchain, the package's C libraries and lintian. Build context:
# packages/wsh-qemu-rdp.
#   docker build -f packages/wsh-qemu-rdp/build.Dockerfile -t wsh-qemu-rdp-build packages/wsh-qemu-rdp
#
# The toolchain is Debian 13's rustc-web/cargo-web (1.96 at the time of writing; Debian keeps it
# current for the browsers it ships), not rustc/cargo (1.85): ironrdp 0.15 needs rustc 1.89.
FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes build-essential debhelper dpkg-dev \
       cargo-web rustc-web pkg-config libopus-dev libpixman-1-dev git ca-certificates lintian \
    && rm -rf /var/lib/apt/lists/*
