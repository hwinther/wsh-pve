# The lab image with a pull request's QEMU and OpenBIOS in place of the package's: qemu-system-sparc
# and qemu-system-sparc64 from pr-qemu.sh in /usr/local/bin (before the package's /usr/bin in PATH)
# and openbios-sparc32, openbios-sparc64 and QEMU,cgthree.bin from openbios/Dockerfile over those in
# LAB_FIRMWARE (/usr/share/kvm). The other firmware (the Sun PROMs) stays the package's.
#
# Build context: a directory with bin/ (the two binaries), firmware/ (the three images) and
# versions.txt (what was built, e2e/sparc/README.md "Before merge"):
#   docker build -f e2e/sparc/pr-qemu.Dockerfile --build-arg LAB_IMAGE=wsh-sparc-lab -t wsh-sparc-lab:pr <dir>
ARG LAB_IMAGE=wsh-sparc-lab
FROM ${LAB_IMAGE}
# --chmod: an Actions artifact drops the executable bit
COPY --chmod=0755 bin/qemu-system-sparc bin/qemu-system-sparc64 /usr/local/bin/
COPY firmware/openbios-sparc32 firmware/openbios-sparc64 firmware/QEMU,cgthree.bin /usr/share/kvm/
COPY versions.txt /lab-pr-versions.txt
# Fails here when a binary misses a library of the image or isn't the one PATH finds
RUN set -e; for b in qemu-system-sparc qemu-system-sparc64; do \
      [ "$(command -v "$b")" = "/usr/local/bin/$b" ]; "$b" --version | head -n 1; \
    done
