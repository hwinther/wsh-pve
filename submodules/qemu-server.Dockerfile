FROM debian AS install
MAINTAINER Hans Christian Winther-Sørensen <docker@wsh.no>
COPY pve-dev.list /etc/apt/sources.list.d/
COPY proxmox-release-bookworm.gpg /etc/apt/trusted.gpg.d/
RUN apt-get update
ENV DEBIAN_FRONTEND=noninteractive
# For service configuration (perhaps it can be skipped instead?)
RUN apt-get install --no-install-recommends --assume-yes systemd
# Generic packages for dev workloads
RUN apt-get install --no-install-recommends --assume-yes git build-essential
# Packages from 'make deb' recommendations
RUN apt-get install --no-install-recommends --assume-yes libfile-readbackwards-perl libproxmox-acme-perl libproxmox-rs-perl libpve-access-control libpve-cluster-api-perl libpve-cluster-perl libpve-common-perl libpve-guest-common-perl libpve-http-server-perl libpve-notify-perl libpve-rs-perl libpve-storage-perl libtemplate-perl libtest-mockmodule-perl lintian proxmox-widget-toolkit pve-cluster pve-container pve-doc-generator pve-eslint qemu-server sq
# Missing deps from the other two rounds
RUN apt-get install --no-install-recommends --assume-yes debhelper-compat libpod-parser-perl
# Missing deps for qemu-server
RUN apt-get install --no-install-recommends --assume-yes libglib2.0-dev libjson-c-dev pkg-config pve-edk2-firmware

FROM install AS build
COPY submodules/qemu-server /src/submodules/qemu-server
COPY submodules/qemu-server.patch /src/submodules/qemu-server.patch
COPY .git /src/.git
WORKDIR /src/submodules/qemu-server
RUN patch -p1 -i ../qemu-server.patch
# TODO add changelog entry and increment version
RUN make deb

FROM debian AS final
RUN mkdir /opt/repo
COPY --from=build /src/submodules/qemu-server/*.deb /opt/repo/
CMD ["bash"]
