# The x86 audio matrix (audio_matrix.py): the PVE node of the e2e tests (e2e/pve/Dockerfile, the
# published packages) with the matrix's guests and harness in it, so the same image runs QEMU
# directly and through qemu-server (`audio0: driver=wav`, `qm showcmd`, `qm start`).
#
# Build the PVE image first; this one adds the guests to it (build context: the repository root,
# Dockerfile.dockerignore sends only this directory and the FreeDOS pins):
#   docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
#   docker build -f e2e/audio/Dockerfile --build-arg PVE_IMAGE=wsh-pve-e2e:local -t wsh-audio .
#
# The guests are built from Debian packages and this directory only (build-guests.sh): the DOS test
# program (nasm), Debian's kernel, busybox and aplay. FreeDOS is given at run time (FREEDOS_ZIP; CI
# restores it from the Actions cache) or downloaded by URL and sha256; the pins and the download are
# e2e/sparc's (targets_dos.py, fetch_media.py), in /sparc next to /audio as in the repository.
ARG PVE_IMAGE=wsh-pve-e2e:local

FROM debian:13 AS guests
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes nasm python3 linux-image-amd64 busybox-static \
        alsa-utils kmod cpio gzip xz-utils zstd \
    && rm -rf /var/lib/apt/lists/*
COPY e2e/audio/audtest.asm e2e/audio/guest-init.sh e2e/audio/build-guests.sh /src/
RUN sh /src/build-guests.sh /guests

FROM ${PVE_IMAGE}
# pve-manager adds the enterprise repository, which needs a subscription
RUN rm -f /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/ceph.sources \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3 mtools \
    && rm -rf /var/lib/apt/lists/*
COPY --from=guests /guests/ /audio/guests/
COPY e2e/sparc/targets_dos.py e2e/sparc/fetch_media.py /sparc/
COPY e2e/audio/audio_matrix.py e2e/audio/wavcheck.py e2e/audio/test_wavcheck.py /audio/
WORKDIR /audio
