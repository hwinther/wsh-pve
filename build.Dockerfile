FROM debian:12 AS install
LABEL maintainer="Hans Christian Winther-Sørensen <docker@wsh.no>"
COPY pve-dev.list /etc/apt/sources.list.d/
COPY proxmox-release-bookworm.gpg /etc/apt/trusted.gpg.d/
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update
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
# Missing deps for pve-qemu
RUN apt-get install --no-install-recommends --assume-yes meson check libacl1-dev libaio-dev libattr1-dev libcap-ng-dev libcurl4-gnutls-dev libepoxy-dev libfdt-dev libgbm-dev libglusterfs-dev libgnutls28-dev libiscsi-dev libjpeg-dev libnuma-dev libpci-dev libpixman-1-dev libproxmox-backup-qemu0-dev librbd-dev libsdl1.2-dev libseccomp-dev libslirp-dev libspice-protocol-dev libspice-server-dev libsystemd-dev liburing-dev libusb-1.0-0-dev libusbredirparser-dev libvirglrenderer-dev libzstd-dev python3-sphinx python3-sphinx-rtd-theme python3-venv quilt xfslibs-dev libsdl2-dev libgtk-3-dev
# For dch
RUN apt-get install --no-install-recommends --assume-yes devscripts libdistro-info-perl
# For additional audio support
RUN apt-get install --no-install-recommends --assume-yes libasound2-dev libpulse-dev libpipewire-0.3-dev
# For pve-qemu-7.2-sparc build
RUN apt-get install --no-install-recommends --assume-yes texi2html texinfo
# WSH specific
RUN apt-get install --no-install-recommends --assume-yes jq
RUN apt-get clean
