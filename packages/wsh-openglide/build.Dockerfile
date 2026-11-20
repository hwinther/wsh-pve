# The build image of the wsh-openglide package (packages/wsh-openglide/build.sh): Debian 13, pinned
# by digest (Dependabot bumps it), with debhelper, the package's build dependencies, git (the
# upstream source is fetched at the pinned commit) and lintian. Build context: packages/wsh-openglide.
#   docker build -f packages/wsh-openglide/build.Dockerfile -t wsh-openglide-build packages/wsh-openglide
FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes build-essential debhelper dpkg-dev \
       libgl-dev libglu1-mesa-dev libtool libx11-dev libxxf86vm-dev git ca-certificates lintian \
    && rm -rf /var/lib/apt/lists/*
