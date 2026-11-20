# The x86 audio matrix (audio_matrix.py): the PVE node of the e2e tests (e2e/pve/Dockerfile, the
# published packages) with the matrix's guests and harness in it, so the same image runs QEMU
# directly and through qemu-server (`qm showcmd`, `qm start`).
#
# Build the PVE image first; this one adds the guests to it (build context: e2e/audio):
#   docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
#   docker build -f e2e/audio/Dockerfile --build-arg PVE_IMAGE=wsh-pve-e2e:local -t wsh-audio e2e/audio
#
# The guests are built from Debian packages and this directory only (build-guests.sh): the DOS test
# program (nasm), Debian's kernel, busybox and aplay. FreeDOS is downloaded at run time by URL and
# sha256 (audio_matrix.py, FREEDOS_ZIP).
ARG PVE_IMAGE=wsh-pve-e2e:local

FROM debian:13 AS guests
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes nasm python3 linux-image-amd64 busybox-static \
        alsa-utils kmod cpio gzip xz-utils zstd \
    && rm -rf /var/lib/apt/lists/*
COPY audtest.asm guest-init.sh build-guests.sh /src/
RUN sh /src/build-guests.sh /guests

FROM ${PVE_IMAGE}
# pve-manager adds the enterprise repository, which needs a subscription
RUN rm -f /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/ceph.sources \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3 mtools \
    && rm -rf /var/lib/apt/lists/*
COPY --from=guests /guests/ /audio/guests/
COPY audio_matrix.py wavcheck.py test_wavcheck.py /audio/
WORKDIR /audio
