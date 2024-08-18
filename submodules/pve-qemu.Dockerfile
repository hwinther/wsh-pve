FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/pve-qemu /src/submodules/pve-qemu
COPY submodules/pve-qemu.patch /src/submodules/pve-qemu.patch
COPY .git /src/.git
WORKDIR /src/submodules/pve-qemu
RUN patch -p1 -i ../pve-qemu.patch
ENV EMAIL=docker@wsh.no
RUN make deb
RUN ls -l /src/submodules/pve-qemu/*.deb

FROM scratch AS final
COPY --from=build /src/submodules/pve-qemu/*.deb /opt/repo/
CMD ["bash"]
