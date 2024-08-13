FROM debian:12-slim AS install
LABEL maintainer="Hans Christian Winther-Sørensen <docker@wsh.no>"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install --no-install-recommends --assume-yes nginx reprepro nano && apt-get clean

FROM ghcr.io/hwinther/wsh-pve/qemu-server:latest AS qemu-server
FROM ghcr.io/hwinther/wsh-pve/pve-qemu:latest AS pve-qemu
FROM ghcr.io/hwinther/wsh-pve/pve-manager:latest AS pve-manager

FROM install AS final
RUN mkdir -p /opt/repo/incoming
COPY --from=qemu-server /opt/repo/*.deb /opt/repo/incoming/
COPY --from=pve-qemu /opt/repo/*.deb /opt/repo/incoming/
COPY --from=pve-manager /opt/repo/*.deb /opt/repo/incoming/
RUN mkdir /opt/repo/conf
COPY repo-conf/* /opt/repo/conf/
WORKDIR /opt/repo
RUN reprepro -Vb . includedeb bookworm /opt/repo/incoming/pve-manager_*_amd64.deb
RUN reprepro -Vb . includedeb bookworm /opt/repo/incoming/pve-qemu_*_amd64.deb
RUN reprepro -Vb . includedeb bookworm /opt/repo/incoming/qemu-server_*_amd64.deb
CMD ["bash"]
