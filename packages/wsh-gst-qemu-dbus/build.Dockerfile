# The build image of the wsh-gst-qemu-dbus package (packages/wsh-gst-qemu-dbus/build.sh): Debian 13,
# pinned by digest (Dependabot bumps it), with debhelper, meson, the GStreamer and GLib development
# packages and lintian. Build context: packages/wsh-gst-qemu-dbus.
#   docker build -f packages/wsh-gst-qemu-dbus/build.Dockerfile -t wsh-gst-qemu-dbus-build packages/wsh-gst-qemu-dbus
FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes build-essential debhelper dpkg-dev \
       meson ninja-build pkgconf libglib2.0-dev libgstreamer1.0-dev \
       libgstreamer-plugins-base1.0-dev lintian \
    && rm -rf /var/lib/apt/lists/*
