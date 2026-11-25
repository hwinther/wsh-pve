# Stage 3d of the 3dfx/streaming plan: Moonlight to Wolf, with a VM's D-Bus display as Wolf's video
# and audio source (e2e/streaming/test.sh builds and runs these images; see its header).
#
# Everything is built from source at pinned commits on Debian 13; no prebuilt Wolf or Moonlight
# image or binary is used. Build context: a directory test.sh assembles (this directory's files,
# the apt keyrings and qemu-server's bus policy).
#
#   wolf-build   Wolf (games-on-whales) at WOLF_COMMIT (its v2026.11) with wolf-no-compositor.patch,
#                its CMake dependencies at the commits Wolf pins (FetchContent, git), mdns_cpp
#                (unpinned there) at MDNS_CPP_COMMIT, Boost from its source release (by sha256), and
#                the interpipe GStreamer elements Wolf's pipelines use at INTERPIPE_COMMIT
#   node         a PVE node's streaming side in one container: the published pve-qemu-kvm and
#                wsh-gst-qemu-dbus from the wsh-pve apt repository, dbus-daemon with qemu-server's
#                bus policy, Wolf, x264 (software encoding), PulseAudio (Wolf won't start without
#                one), wolf-config.py, wolf-input-bridge, wolf-pair and node.sh as the entry point
#   client-build moonlight-embedded at MOONLIGHT_COMMIT (its moonlight-common-c submodule as
#                pinned there) and wsh-moonlight-probe (moonlight-probe.c) on its libraries
#   client       moonlight-embedded's `moonlight` (pairing), wsh-moonlight-probe and stream3d.py
FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6 AS wolf-build
ARG WOLF_COMMIT=db709cfd3f0f49dfd7d00495940119309692b535
ARG MDNS_CPP_COMMIT=0d57ae3db73d94ab2e7ac0a799a9165c8a221c80
ARG INTERPIPE_COMMIT=0c454917cb3cf4f2b2f2729f5f72a4dee072c7c9
# Wolf wants Boost 1.87 with Boost.Process, which Debian 13 doesn't build (1.83, and 1.88 without
# process): Wolf's own fallback, Boost's CMake source release, taken here by its sha256
ARG BOOST_VERSION=1.87.0
ARG BOOST_SHA256=7da75f171837577a52bbf217e17f8ea576c7c246e4594d617bfde7fafd408be5
ARG JOBS=6
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates git build-essential \
       cmake ninja-build meson pkgconf curl xz-utils libssl-dev libcurl4-openssl-dev \
       libevdev-dev libudev-dev libpulse-dev libunwind-dev libdrm-dev libpci-dev libicu-dev \
       libwayland-dev libglib2.0-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/games-on-whales/wolf.git /src/wolf \
    && git -C /src/wolf checkout --quiet "$WOLF_COMMIT" \
    && git clone https://github.com/games-on-whales/mdns_cpp.git /src/mdns_cpp \
    && git -C /src/mdns_cpp checkout --quiet "$MDNS_CPP_COMMIT" \
    && git clone https://github.com/games-on-whales/gst-interpipe.git /src/gst-interpipe \
    && git -C /src/gst-interpipe checkout --quiet "$INTERPIPE_COMMIT" \
    && curl -fsSL -o /src/boost.tar.xz \
       "https://github.com/boostorg/boost/releases/download/boost-$BOOST_VERSION/boost-$BOOST_VERSION-cmake.tar.xz" \
    && echo "$BOOST_SHA256  /src/boost.tar.xz" | sha256sum -c \
    && mkdir /src/boost \
    && tar -xJf /src/boost.tar.xz -C /src/boost --strip-components=1 \
    && rm /src/boost.tar.xz
# Boost first, installed (static) where Wolf's find_package and its dependencies' find Boost
WORKDIR /src/boost
RUN cmake -B /build/boost -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
       -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DBOOST_ENABLE_PYTHON=OFF \
       -DBOOST_INCLUDE_LIBRARIES="log;container;locale;process;align;json;system;filesystem;thread;asio" \
    && ninja -C /build/boost -j "$JOBS" \
    && cmake --install /build/boost \
    && for d in /src/boost/libs/*/include /src/boost/libs/*/*/include; do [ ! -d "$d/boost" ] || cp -rn "$d/boost" /usr/local/include/; done \
    && rm -rf /build/boost
WORKDIR /src/wolf
# Apps without a Wayland compositor (ours) don't start at that commit: wolf-no-compositor.patch
COPY wolf-no-compositor.patch /src/
RUN git apply /src/wolf-no-compositor.patch
RUN cmake -B /build/wolf -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
       -DBUILD_SHARED_LIBS=OFF -DADD_STACKTRACE_INFO=OFF -DBUILD_FAKE_UDEV_CLI=OFF \
       -DFETCHCONTENT_SOURCE_DIR_MDNS_CPP=/src/mdns_cpp -DBoost_USE_STATIC_LIBS=ON \
    && ninja -C /build/wolf -j "$JOBS" wolf \
    && install -D -m 0755 /build/wolf/src/moonlight-server/wolf /out/usr/local/bin/wolf
WORKDIR /src/gst-interpipe
RUN meson setup /build/interpipe --prefix=/usr -Denable-gtk-doc=false -Dtests=disabled \
    && ninja -C /build/interpipe \
    && DESTDIR=/out meson install -C /build/interpipe

FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6 AS client-build
ARG MOONLIGHT_COMMIT=33142e58ebd576085a076f4ce24881d20b3c4ef5
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates git build-essential \
       cmake pkgconf libopus-dev libexpat1-dev libssl-dev libavahi-client-dev uuid-dev \
       libcurl4-openssl-dev libevdev-dev libudev-dev libavcodec-dev libavutil-dev libswscale-dev \
       libsdl2-dev libasound2-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/moonlight-stream/moonlight-embedded.git /src/moonlight \
    && git -C /src/moonlight checkout --quiet "$MOONLIGHT_COMMIT" \
    && git -C /src/moonlight submodule update --init --recursive --quiet
WORKDIR /src/moonlight
RUN cmake -B /build/moonlight -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
       -DENABLE_X11=OFF -DENABLE_CEC=OFF -DENABLE_PULSE=OFF \
    && make -C /build/moonlight -j "$(nproc)" \
    && DESTDIR=/out make -C /build/moonlight install
COPY moonlight-probe.c /src/probe/
RUN gcc -O2 -Wall -Wextra -Wno-unused-parameter -o /out/usr/local/bin/wsh-moonlight-probe \
       /src/probe/moonlight-probe.c -I/src/moonlight/libgamestream \
       -I/src/moonlight/third_party/moonlight-common-c/src \
       -L/build/moonlight/libgamestream -lgamestream -lmoonlight-common \
       $(pkg-config --cflags --libs libavcodec libavutil libswscale opus) -lpthread -lm

FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6 AS client
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates libopus0 libexpat1 \
       libssl3t64 libavahi-client3 libuuid1 libcurl4t64 libevdev2 libudev1 libavcodec61 \
       libavutil59 libswscale8 libasound2t64 libsdl2-2.0-0 python3 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=client-build /out/ /
COPY --chmod=0755 stream3d.py /usr/local/bin/
RUN ldconfig && moonlight --help > /dev/null 2>&1; ldd /usr/local/bin/moonlight /usr/local/bin/wsh-moonlight-probe | grep -v "=> /" | grep -q "not found" && exit 1 || true

FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6 AS node
ENV DEBIAN_FRONTEND=noninteractive
COPY proxmox-archive-keyring-trixie.gpg /usr/share/keyrings/proxmox-archive-keyring.gpg
COPY wsh-pve.gpg.key /tmp/wsh-pve.gpg.key
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg \
    && gpg --dearmor < /tmp/wsh-pve.gpg.key > /usr/share/keyrings/wsh-pve.gpg \
    && printf 'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n' \
       > /etc/apt/sources.list.d/proxmox.sources \
    && printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
       > /etc/apt/sources.list.d/wsh-pve.sources \
    && printf 'Package: pve-qemu-kvm\nPin: origin debian.wshosting.no\nPin-Priority: 1001\n' > /etc/apt/preferences.d/wsh-pve \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes pve-qemu-kvm wsh-gst-qemu-dbus dbus-daemon \
       gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly \
       libegl1 libegl-mesa0 libgl1-mesa-dri python3 curl procps pulseaudio \
       libcurl4t64 libevdev2 libudev1 libpulse0 libunwind8 libdrm2 libpci3 libicu76 libssl3t64 \
    && rm -rf /var/lib/apt/lists/* /tmp/wsh-pve.gpg.key
COPY --from=wolf-build /out/ /
COPY --from=wolf-build /src/wolf/src/moonlight-server/state/default/config.include.toml /usr/local/share/wolf/
COPY dbus-display.conf /usr/share/qemu-server/dbus-display.conf
COPY --chmod=0755 wolf-input-bridge wolf-config.py wolf-pair node.sh /usr/local/bin/
RUN ldconfig \
    && ! ldd /usr/local/bin/wolf | grep "not found" \
    && gst-inspect-1.0 interpipesrc > /dev/null && gst-inspect-1.0 x264enc > /dev/null \
    && gst-inspect-1.0 qemudbussrc > /dev/null \
    && groupadd --system wsh-display
ENTRYPOINT ["/usr/local/bin/node.sh"]

# A PVE container template for a node (docs: display reference, "Streaming to Moonlight"): Wolf,
# the sources and the bridge, PulseAudio, x264 and GStreamer's nvcodec elements (NVENC, with the
# node's NVIDIA libraries copied in), and the client for checks from inside the container, on
# systemd. No QEMU: the VM runs on the node. `docker export` of this image is the template.
FROM debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6 AS ct
ENV DEBIAN_FRONTEND=noninteractive
COPY wsh-pve.gpg.key /tmp/wsh-pve.gpg.key
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg \
    && gpg --dearmor < /tmp/wsh-pve.gpg.key > /usr/share/keyrings/wsh-pve.gpg \
    && printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
       > /etc/apt/sources.list.d/wsh-pve.sources \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes systemd-sysv ifupdown iproute2 \
       wsh-gst-qemu-dbus gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
       gstreamer1.0-plugins-ugly gstreamer1.0-plugins-bad python3 curl procps pulseaudio \
       libcurl4t64 libevdev2 libudev1 libpulse0 libunwind8 libdrm2 libpci3 libicu76 libssl3t64 \
       libopus0 libexpat1 libavahi-client3 libuuid1 libavcodec61 libavutil59 libswscale8 \
       libasound2t64 libsdl2-2.0-0 \
    && rm -rf /var/lib/apt/lists/* /tmp/wsh-pve.gpg.key \
    && groupadd --system wsh-display
COPY --from=wolf-build /out/ /
COPY --from=wolf-build /src/wolf/src/moonlight-server/state/default/config.include.toml /usr/local/share/wolf/
COPY --from=client-build /out/ /
COPY --chmod=0755 wolf-input-bridge wolf-config.py wolf-pair wolf-start stream3d.py /usr/local/bin/
RUN ldconfig && ! ldd /usr/local/bin/wolf /usr/local/bin/wsh-moonlight-probe | grep "not found"
