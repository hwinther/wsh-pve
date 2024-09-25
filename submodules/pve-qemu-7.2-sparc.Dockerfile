FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
RUN apt-get -y install texi2html texinfo
COPY submodules/pve-qemu /src/submodules/pve-qemu
COPY submodules/pve-qemu-7.2-sparc.patch /src/submodules/pve-qemu-7.2-sparc.patch
COPY .git /src/.git
WORKDIR /src/submodules/pve-qemu
RUN git checkout 93d558c1eef8f3ec76983cbe6848b0dc606ea5f1
RUN patch -p1 -i ../pve-qemu-7.2-sparc.patch
ENV EMAIL=docker@wsh.no
RUN make deb || true
RUN ls -l /src/submodules/pve-qemu/pve-qemu-kvm-7.2.0/debian/pve-qemu-kvm/usr/bin/qemu-system-sparc*

FROM scratch AS final
COPY --from=build /src/submodules/pve-qemu/pve-qemu-kvm-7.2.0/debian/pve-qemu-kvm/usr/bin/qemu-system-sparc* /opt/bin/pve-qemu-7.2-sparc/
CMD ["bash"]
