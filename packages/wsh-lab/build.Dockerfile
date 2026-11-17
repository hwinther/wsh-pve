# The build image of the wsh-lab package (packages/wsh-lab/build.sh): Debian 13, pinned by digest
# (Dependabot bumps it), with build-essential, debhelper, dh-python and lintian. Build context: packages/wsh-lab.
#   docker build -f packages/wsh-lab/build.Dockerfile -t wsh-lab-build packages/wsh-lab
FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes build-essential debhelper dh-python python3 lintian ca-certificates \
    && rm -rf /var/lib/apt/lists/*
