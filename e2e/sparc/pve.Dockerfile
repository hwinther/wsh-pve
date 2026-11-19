# The PVE node of the e2e tests (e2e/pve/Dockerfile) with the lab in it, for attach mode
# (`lab.py run --pve <vmid>`): the lab must run where /var/run/qemu-server/ and `qm` are, so its few
# dependencies go into the node instead of sharing sockets between two containers.
#
# Build the PVE image first; this one adds the lab to it (build context: e2e/sparc):
#   docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
#   docker build -f e2e/sparc/pve.Dockerfile -t wsh-pve-lab e2e/sparc
#
# Run it like the e2e node (privileged, tmpfs /run), with the media mounted; pve_matrix.py runs inside.
# mtools: the DOS tools disk and its results (dos_tools.py, dos_mem.py). socat: the guests' apt cache
# pinhole (pve_matrix.py --apt-cache; the PVE packages pull it in as well).
ARG PVE_IMAGE=wsh-pve-e2e:local
FROM ${PVE_IMAGE}
# pve-manager adds the enterprise repository, which needs a subscription
RUN rm -f /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/ceph.sources \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3-pil python3-pyte tesseract-ocr \
        fonts-dejavu-core xz-utils vpx-tools mtools socat \
    && rm -rf /var/lib/apt/lists/*
COPY recording.py /tmp/recording.py
RUN python3 /tmp/recording.py fetch-player /usr/share/asciinema-player && rm /tmp/recording.py
COPY . /lab/
WORKDIR /lab
