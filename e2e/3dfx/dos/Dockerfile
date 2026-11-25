# The DOS Glide test (e2e/3dfx/dos-test.sh): the test program, the demo (e2e/3dfx/demo) and wshspace
# (e2e/3dfx/space, for its -audiotest on an sb16, checked by e2e/audio/wavcheck.py), built
# with DJGPP in the image that builds the qemu-3dfx guest drivers (djgpp.Dockerfile), then a Debian
# 13 with the published pve-qemu-kvm's qemu-system-x86_64-3dfx, wsh-openglide (Glide on the host),
# Mesa (llvmpipe, EGL for the offscreen console), mtools (the FreeDOS floppy) and the harness, with
# the FreeDOS pins and their download from e2e/sparc (targets_dos.py, fetch_media.py). The FreeDOS zip
# is passed in (dos-test.sh --freedos-zip; CI restores it from the Actions cache) or downloaded by the
# harness at run time (by URL and sha256); the guest drivers are passed in.
#
# Build context: the repository root, with submodules/qemu-3dfx checked out.
#   docker build -f e2e/3dfx/dos/Dockerfile -t wsh-3dfx-dos .
ARG DJGPP_IMAGE=ghcr.io/hwinther/wsh-pve/djgpp-build:13
FROM ${DJGPP_IMAGE} AS build
COPY submodules/qemu-3dfx/qemu-0/hw/3dfx/ /src/submodules/qemu-3dfx/qemu-0/hw/3dfx/
COPY submodules/qemu-3dfx/wrappers/3dfx/dxe/ /src/submodules/qemu-3dfx/wrappers/3dfx/dxe/
COPY submodules/qemu-3dfx/wrappers/3dfx/src/ /src/submodules/qemu-3dfx/wrappers/3dfx/src/
COPY packages/wsh-openglide/tests/scene.h /src/packages/wsh-openglide/tests/scene.h
COPY e2e/3dfx/dos/ /src/e2e/3dfx/dos/
COPY e2e/3dfx/demo/ /src/e2e/3dfx/demo/
COPY e2e/3dfx/space/ /src/e2e/3dfx/space/
COPY e2e/wisp/audiosig.h /src/e2e/wisp/audiosig.h
COPY scripts/check-3dfx-drivers-isa.sh /src/scripts/check-3dfx-drivers-isa.sh
# The wrapper's revision only matters for the glide2x.dxe built for comparison; the test loads the
# drivers release's
ARG QEMU3DFX_REV=0000000
RUN sh /src/e2e/3dfx/dos/build.sh /glidedos/bin "$QEMU3DFX_REV"
# The demo (e2e/3dfx/demo), which the harness runs after the test program: WSHDEMO.EXE
RUN sh /src/e2e/3dfx/demo/build-dos.sh /glidedos/bin
# wshspace (e2e/3dfx/space), which the harness runs last with -audiotest on an sb16: WSHSPACE.EXE
RUN sh /src/e2e/3dfx/space/build-dos.sh /glidedos/bin

FROM debian:13
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg python3 mtools \
        libgl1 libgl1-mesa-dri libegl1 libegl-mesa0 \
    && rm -rf /var/lib/apt/lists/*
COPY proxmox-archive-keyring-trixie.gpg /usr/share/keyrings/proxmox-archive-keyring.gpg
COPY repo/conf/wsh-pve.gpg.key /tmp/wsh-pve.gpg.key
# The published versions (dos-test.sh): a new pve-qemu-kvm or wsh-openglide rebuilds the layer below
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
COPY e2e/3dfx/win98/win98_test.py /w3d/e2e/3dfx/win98/win98_test.py
COPY e2e/3dfx/dos/ /w3d/e2e/3dfx/dos/
COPY e2e/sparc/targets_dos.py e2e/sparc/fetch_media.py /w3d/e2e/sparc/
COPY e2e/audio/wavcheck.py /w3d/e2e/audio/wavcheck.py
COPY --from=build /glidedos/bin/ /w3d/bin/
ENTRYPOINT ["python3", "/w3d/e2e/3dfx/dos/dos_test.py"]
