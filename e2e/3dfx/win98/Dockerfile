# The Windows 98 3dfx test (e2e/3dfx/win98-test.sh): the published pve-qemu-kvm's
# qemu-system-x86_64-3dfx, wsh-openglide (Glide on the host), Mesa (llvmpipe, EGL for the offscreen
# console), mtools (writing the test programs and the guest drivers onto a copy of the operator's
# disk), mingw-w64 (building our own test programs), Xvfb and xwd (only for the SDL run) and the
# harness. No Windows file is in it.
#
# Build context: the repository root (for the keyrings and the test scene).
#   docker build -f e2e/3dfx/win98/Dockerfile -t wsh-3dfx-win98 .
FROM debian:13
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg python3 mtools \
        gcc-mingw-w64-i686 binutils-mingw-w64-i686 \
        libgl1 libgl1-mesa-dri libegl1 libegl-mesa0 xvfb xauth x11-utils x11-apps \
    && rm -rf /var/lib/apt/lists/*
COPY proxmox-archive-keyring-trixie.gpg /usr/share/keyrings/proxmox-archive-keyring.gpg
COPY repo/conf/wsh-pve.gpg.key /tmp/wsh-pve.gpg.key
# The published versions (win98-test.sh): a new pve-qemu-kvm or wsh-openglide rebuilds the layer below
ARG WSH_PACKAGES=unknown
RUN echo "packages: $WSH_PACKAGES" && gpg --dearmor < /tmp/wsh-pve.gpg.key > /usr/share/keyrings/wsh-pve.gpg \
    && printf 'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n' \
        > /etc/apt/sources.list.d/proxmox.sources \
    && printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
        > /etc/apt/sources.list.d/wsh-pve.sources \
    && printf 'Package: pve-qemu-kvm\nPin: origin debian.wshosting.no\nPin-Priority: 1001\n' > /etc/apt/preferences.d/wsh-pve \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes pve-qemu-kvm wsh-openglide \
    && rm -rf /var/lib/apt/lists/*
COPY packages/wsh-openglide/tests/scene.h /w3d/packages/wsh-openglide/tests/scene.h
COPY e2e/3dfx/win98/ /w3d/e2e/3dfx/win98/
COPY e2e/3dfx/demo/ /w3d/e2e/3dfx/demo/
COPY e2e/3dfx/audio/ /w3d/e2e/3dfx/audio/
COPY e2e/wisp/audiosig.h /w3d/e2e/wisp/audiosig.h
COPY scripts/check-3dfx-drivers-isa.sh /w3d/scripts/check-3dfx-drivers-isa.sh
# The test programs (w3drun.exe, glidetst.exe, gltest.exe)
RUN sh /w3d/e2e/3dfx/win98/build.sh /w3d/bin
# The demo (e2e/3dfx/demo), for the optional demo-* tests: WSHDEMO.EXE
RUN sh /w3d/e2e/3dfx/demo/build-win.sh /w3d/bin
WORKDIR /w3d/e2e/3dfx/win98
ENTRYPOINT ["python3", "/w3d/e2e/3dfx/win98/win98_test.py"]
