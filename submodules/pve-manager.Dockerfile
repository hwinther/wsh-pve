# FROM debian:12 AS install
# LABEL maintainer="Hans Christian Winther-Sørensen <docker@wsh.no>"
# COPY pve-dev.list /etc/apt/sources.list.d/
# COPY proxmox-release-bookworm.gpg /etc/apt/trusted.gpg.d/
# RUN apt-get update
# ENV DEBIAN_FRONTEND=noninteractive
# # For service configuration (perhaps it can be skipped instead?)
# RUN apt-get install --no-install-recommends --assume-yes systemd
# # Generic packages for dev workloads
# RUN apt-get install --no-install-recommends --assume-yes git build-essential
# # Packages from 'make deb' recommendations
# RUN apt-get install --no-install-recommends --assume-yes libfile-readbackwards-perl libproxmox-acme-perl libproxmox-rs-perl libpve-access-control libpve-cluster-api-perl libpve-cluster-perl libpve-common-perl libpve-guest-common-perl libpve-http-server-perl libpve-notify-perl libpve-rs-perl libpve-storage-perl libtemplate-perl libtest-mockmodule-perl lintian proxmox-widget-toolkit pve-cluster pve-container pve-doc-generator pve-eslint qemu-server sq
# # Missing deps from the other two rounds
# RUN apt-get install --no-install-recommends --assume-yes debhelper-compat libpod-parser-perl
# RUN apt-get clean

# FROM install AS build
FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/pve-manager /src/submodules/pve-manager
COPY submodules/pve-manager.patch /src/submodules/pve-manager.patch
COPY .git /src/.git
WORKDIR /src/submodules/pve-manager
RUN patch -p1 -i ../pve-manager.patch
# TODO: add changelog entry and increment version
RUN make deb

# FROM debian:12 AS final
# RUN mkdir /opt/repo
# COPY --from=build /src/submodules/pve-manager/*.deb /opt/repo/
# CMD ["bash"]

FROM scratch
COPY --from=build /src/submodules/pve-manager/*.deb /
