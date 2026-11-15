# The PVE node of the e2e tests (e2e/pve/Dockerfile) with the lab in it, for attach mode
# (`lab.py run --pve <vmid>`): the lab must run where /var/run/qemu-server/ and `qm` are, so its few
# dependencies go into the node instead of sharing sockets between two containers.
#
# Build the PVE image first; this one adds the lab to it (build context: e2e/sparc):
#   docker build -f e2e/pve/Dockerfile -t wsh-pve-e2e:local .
#   docker build -f e2e/sparc/pve.Dockerfile -t wsh-pve-lab e2e/sparc
#
# Run it like the e2e node (privileged, tmpfs /run), with the media mounted; pve_matrix.py runs inside.
ARG PVE_IMAGE=wsh-pve-e2e:local
FROM ${PVE_IMAGE}
# pve-manager adds the enterprise repository, which needs a subscription
RUN rm -f /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/ceph.sources \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3-pil python3-pyte tesseract-ocr \
        fonts-dejavu-core xz-utils \
    && rm -rf /var/lib/apt/lists/*
COPY . /lab/
WORKDIR /lab
