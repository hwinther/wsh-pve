# Browser SPARC: QEMU for WebAssembly (wasm64, TCG interpreter) for the four machines wisp runs on
# (qemu-system-sparc SS-5, -sparc64 sun4u, -x86_64 pc, -aarch64 virt), their firmware, wisp's kernels
# and xterm.js, for the page in docs/public/browser-sparc/. Everything comes from Debian packages
# (Debian's emscripten, Debian source packages for QEMU and its libraries, Debian's xterm.js and
# kernel source) and from the project's own apt repository (OpenBIOS and SeaBIOS from pve-qemu-kvm).
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
# The snapshot stage boots wisp to its prompt on native QEMUs built from the same tree and saves each
# machine as a migration stream, which the page loads with -incoming instead of booting (2.5 minutes
# of OpenBIOS and Linux under the interpreter in a browser on the SS-5, under a second resumed).
# The machines' options are in docs/public/browser-sparc/machines.json, which the page and the
# snapshot scripts both read.
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
        libglib2.0-dev zlib1g-dev libfdt-dev device-tree-compiler dpkg-dev xz-utils ca-certificates \
    && emcc --version | head -n 1

FROM toolchain AS deps
COPY web/scripts/build-deps.sh /usr/local/bin/
RUN build-deps.sh /work/deps && rm -rf /work/deps

FROM deps AS qemu
COPY web/scripts/build-qemu.sh /usr/local/bin/
COPY submodules/pve-qemu.patch /src/pve-qemu.patch
COPY web/patches/ /src/web-patches/
RUN build-qemu.sh /work/qemu /src/pve-qemu.patch /out /native && rm -rf /work/qemu

# wisp's kernels with its interactive shell (e2e/wisp, tier 1 only) for the four machines, as
# e2e/wisp/Dockerfile builds them.
FROM ${DEBIAN} AS kernel
ENV DEBIAN_FRONTEND=noninteractive
RUN echo 'deb http://deb.debian.org/debian trixie-backports main' > /etc/apt/sources.list.d/backports.list \
    && apt-get update \
    && apt-get install --no-install-recommends --assume-yes python3 make bc bison flex cpio rsync xz-utils \
        libelf-dev libssl-dev gcc libc6-dev gcc-sparc64-linux-gnu gcc-aarch64-linux-gnu patch \
    && apt-get install --no-install-recommends --assume-yes -t trixie-backports linux-source-7.3
COPY e2e/wisp/ /wisp/
RUN cd /wisp && TIER2=0 JOBS=$(nproc) ./build.sh sparc32 sparc64 x86_64 aarch64 \
    && mkdir /kernels && for a in sparc32 sparc64 x86_64 aarch64; do \
        cp "out/$a/kernel" "/kernels/wisp-$a-kernel" && echo "wisp $a kernel: $(cat "out/$a/sizes")"; \
    done > /kernels-versions.txt

# The firmware from the published pve-qemu-kvm (the project's own patched build, the files a PVE VM
# uses): OpenBIOS for sparc32 and sparc64, SeaBIOS and the option ROMs QEMU's PC loads with -kernel
# (linuxboot_dma.bin) and always (kvmvapic.bin); the Arm virt machine boots its kernel directly. And
# xterm.js from Debian's libjs-xterm. Unpacked from the .debs without installing them.
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
    && for f in openbios-sparc32 openbios-sparc64 bios-256k.bin linuxboot_dma.bin kvmvapic.bin; do \
        cp "/tmp/root/usr/share/kvm/$f" /files/; done \
    && cp /tmp/root/usr/share/javascript/xterm/xterm/lib/xterm.js \
        /tmp/root/usr/share/javascript/xterm/xterm/css/xterm.css /files/ \
    && for d in ./*.deb; do dpkg-deb -W --showformat='${Package} ${Version}\n' "$d"; done > /files/versions-files.txt

# Each machine at wisp's first prompt, booted with the page's options (make-snapshot.py), and the
# console transcript up to there. clock-check.py then resumes each with QEMU's main loop held up and
# fails the build if the guest's clock falls behind (web/patches/slavio-timer-missed-ticks.patch
# for the SS-5; the others keep time from clocks that read the virtual clock).
FROM qemu AS snapshot
COPY web/scripts/make-snapshot.py web/scripts/clock-check.py /usr/local/bin/
COPY docs/public/browser-sparc/machines.json /src/machines.json
COPY --from=kernel /kernels/ /page/
COPY --from=files /files/ /page/
RUN for a in sparc32 sparc64 x86_64 aarch64; do \
        make-snapshot.py /src/machines.json "$a" /native /page /snap \
        && clock-check.py /src/machines.json "$a" /native /snap || exit 1; done

# The page's binary files (the assets of the `browser-sparc` release, see docs/public/browser-sparc/)
# and versions.txt with what went into them.
FROM ${DEBIAN} AS bundle
COPY --from=qemu /out/ /bundle/
COPY --from=kernel /kernels/ /bundle/
COPY --from=kernel /kernels-versions.txt /tmp/
COPY --from=files /files/ /tmp/files/
COPY --from=snapshot /snap/ /bundle/
RUN cd /tmp/files && cp openbios-sparc32 openbios-sparc64 bios-256k.bin linuxboot_dma.bin kvmvapic.bin \
        xterm.js xterm.css /bundle/ \
    && cat /tmp/kernels-versions.txt versions-files.txt >> /bundle/versions.txt \
    && cd /bundle && sha256sum qemu-system-* openbios-* *.bin wisp-* xterm.* > SHA256SUMS \
    && ls -l /bundle && cat /bundle/versions.txt

FROM scratch AS dist
COPY --from=bundle /bundle/ /
