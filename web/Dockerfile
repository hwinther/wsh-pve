# Browser SPARC: qemu-system-sparc for WebAssembly (wasm64, TCG interpreter), OpenBIOS, wisp's sparc32
# kernel and xterm.js, for the page in docs/public/browser-sparc/. Everything comes from Debian
# packages (Debian's emscripten, Debian source packages for QEMU and its libraries, Debian's xterm.js
# and kernel source) and from the project's own apt repository (OpenBIOS from pve-qemu-kvm).
#
# Build context: the repository root.
#   docker build -f web/Dockerfile --target dist -o web/dist .
# or web/build.sh, which also copies the result next to the page.
#
# Emscripten: QEMU 11.1's wasm64 build needs a recent one (its CI uses emsdk 4.0.10; trixie has 3.1.69),
# so the toolchain stage takes emscripten 6.0.5 from sid. Its dependencies (clang-21, python3.14,
# nodejs) come from sid with it, so the build tools are taken from sid as well. Debian's QEMU source
# (+ds) has no prebuilt Python wheels, firmware or device trees, so meson and QEMU's Python tooling
# come from Debian packages and the device trees are compiled (device-tree-compiler).
#
# The snapshot stage boots wisp to its prompt on a native qemu-system-sparc built from the same tree
# and saves it as a migration stream, which the page loads with -incoming instead of booting
# (2.5 minutes of OpenBIOS and Linux under the interpreter in a browser, under a second resumed).
ARG DEBIAN=debian:13

FROM ${DEBIAN} AS toolchain
ENV DEBIAN_FRONTEND=noninteractive
RUN sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources \
    && printf 'Types: deb deb-src\nURIs: http://deb.debian.org/debian\nSuites: sid\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.pgp\n' \
        > /etc/apt/sources.list.d/sid.sources \
    && printf 'Package: *\nPin: release n=sid\nPin-Priority: 100\n' > /etc/apt/preferences.d/sid \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes -t sid emscripten meson ninja-build pkgconf \
        autoconf automake libtool libltdl-dev bison flex python3-venv libglib2.0-dev-bin git patch \
        python3-pycotap python3-qemu-qmp python3-setuptools python3-wheel python3-pip gcc libc6-dev \
        libglib2.0-dev zlib1g-dev device-tree-compiler dpkg-dev xz-utils ca-certificates \
    && emcc --version | head -n 1

FROM toolchain AS deps
COPY web/scripts/build-deps.sh /usr/local/bin/
RUN build-deps.sh /work/deps && rm -rf /work/deps

FROM deps AS qemu
COPY web/scripts/build-qemu.sh /usr/local/bin/
COPY submodules/pve-qemu.patch /src/pve-qemu.patch
COPY web/patches/ /src/web-patches/
RUN build-qemu.sh /work/qemu /src/pve-qemu.patch /out /native && rm -rf /work/qemu

# wisp's sparc32 kernel with its interactive shell (e2e/wisp, tier 1 only), as e2e/wisp/Dockerfile
# builds it.
FROM ${DEBIAN} AS kernel
ENV DEBIAN_FRONTEND=noninteractive
RUN echo 'deb http://deb.debian.org/debian trixie-backports main' > /etc/apt/sources.list.d/backports.list \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3 make bc bison flex cpio rsync xz-utils \
        libelf-dev libssl-dev gcc libc6-dev gcc-sparc64-linux-gnu \
    && apt-get install --no-install-recommends --assume-yes -t trixie-backports linux-source-7.3
COPY e2e/wisp/ /wisp/
RUN cd /wisp && TIER2=0 JOBS=$(nproc) ./build.sh sparc32 && cp out/sparc32/kernel /wisp-sparc32-kernel

# OpenBIOS from the published pve-qemu-kvm (the project's own patched build) and xterm.js from
# Debian's libjs-xterm, unpacked from their .debs without installing them.
FROM ${DEBIAN} AS files
ENV DEBIAN_FRONTEND=noninteractive
COPY repo/conf/wsh-pve.gpg.key /tmp/wsh-pve.gpg.key
RUN apt-get update && apt-get install --no-install-recommends --assume-yes gnupg ca-certificates \
    && gpg --dearmor < /tmp/wsh-pve.gpg.key > /usr/share/keyrings/wsh-pve.gpg \
    && printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
        > /etc/apt/sources.list.d/wsh-pve.sources \
    && printf 'Types: deb\nURIs: http://deb.debian.org/debian\nSuites: sid\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.pgp\n' \
        > /etc/apt/sources.list.d/sid.sources \
    && printf 'Package: *\nPin: release n=sid\nPin-Priority: 100\n' > /etc/apt/preferences.d/sid \
    && apt-get update \
    && mkdir -p /files /tmp/debs && cd /tmp/debs \
    && apt-get download pve-qemu-kvm/trixie libjs-xterm/sid \
    && for d in ./*.deb; do dpkg-deb -x "$d" /tmp/root; done \
    && cp /tmp/root/usr/share/kvm/openbios-sparc32 /files/ \
    && cp /tmp/root/usr/share/javascript/xterm/xterm/lib/xterm.js \
        /tmp/root/usr/share/javascript/xterm/xterm/css/xterm.css /files/ \
    && for d in ./*.deb; do dpkg-deb -W --showformat='${Package} ${Version}\n' "$d"; done > /files/versions-files.txt

# The machine at wisp's first prompt, booted with the page's options (make-snapshot.py), and the
# console transcript up to there. clock-check.py then resumes it with QEMU's main loop held up and
# fails the build if the guest's clock falls behind (web/patches/slavio-timer-missed-ticks.patch).
FROM qemu AS snapshot
COPY web/scripts/make-snapshot.py web/scripts/clock-check.py /usr/local/bin/
COPY --from=kernel /wisp-sparc32-kernel /tmp/
COPY --from=files /files/openbios-sparc32 /tmp/
RUN make-snapshot.py /native/qemu-system-sparc /tmp/openbios-sparc32 /tmp/wisp-sparc32-kernel /snap 128 \
    && clock-check.py /native/qemu-system-sparc /snap/wisp-ss5-128m.state

# The page's binary files (the assets of the `browser-sparc` release, see docs/public/browser-sparc/)
# and versions.txt with what went into them.
FROM ${DEBIAN} AS bundle
COPY --from=qemu /out/ /bundle/
COPY --from=kernel /wisp-sparc32-kernel /bundle/
COPY --from=kernel /wisp/out/sparc32/sizes /tmp/wisp-sizes
COPY --from=files /files/ /tmp/files/
COPY --from=snapshot /snap/ /bundle/
RUN cd /tmp/files && cp openbios-sparc32 xterm.js xterm.css /bundle/ \
    && { echo "wisp sparc32 kernel: $(cat /tmp/wisp-sizes)"; cat versions-files.txt; } >> /bundle/versions.txt \
    && cd /bundle && sha256sum qemu-system-sparc.* openbios-sparc32 wisp-sparc32-kernel wisp-ss5-* xterm.* > SHA256SUMS \
    && ls -l /bundle && cat /bundle/versions.txt

FROM scratch AS dist
COPY --from=bundle /bundle/ /
