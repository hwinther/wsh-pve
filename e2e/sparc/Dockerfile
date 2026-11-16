# The sparc lab: qemu-system-sparc from the published pve-qemu-kvm (the build users run), plus the
# harness that drives a guest through its serial console and framebuffer (lab.py).
#
# Build context: the repository root (for the keyrings).
#   docker build -f e2e/sparc/Dockerfile -t wsh-sparc-lab .
#
# qemu-7.2.Dockerfile builds on this image with an upstream QEMU (7.2.0 by default) for comparisons.

# The Linux side of the bench disk's network tests (bench/README, "Network"): lmbench 3.0-a9's
# bw_tcp, lat_tcp and lat_udp, the same unmodified version as on the bench disk, fetched and checked
# against the sha256 pinned in bench/handover.py and built by bench/peer-build.sh.
FROM debian:13 AS lmbench-peer
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates python3 gcc make libc6-dev libtirpc-dev \
    && rm -rf /var/lib/apt/lists/*
COPY e2e/sparc/bench/handover.py e2e/sparc/bench/peer-build.sh /tmp/
RUN python3 -I /tmp/handover.py fetch /tmp/dl lmbench-3.0-a9.tgz \
    && sh /tmp/peer-build.sh /tmp/dl/lmbench-3.0-a9.tgz /opt/lmbench-peer

FROM debian:13
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg python3 python3-pil \
        python3-pyte tesseract-ocr fonts-dejavu-core xz-utils vpx-tools genisoimage libtirpc3t64 iproute2 \
    && rm -rf /var/lib/apt/lists/*
# Recordings (recording.py): vpxenc (vpx-tools, ~5 MB) encodes the framebuffer video, and the
# asciinema player (pinned version, hash checked) goes next to each run's index.html.
COPY e2e/sparc/recording.py /tmp/recording.py
RUN python3 /tmp/recording.py fetch-player /usr/share/asciinema-player && rm /tmp/recording.py

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

COPY --from=lmbench-peer /opt/lmbench-peer/ /opt/lmbench-peer/
COPY e2e/sparc/ /lab/
WORKDIR /lab
ENTRYPOINT ["python3", "/lab/lab.py"]
