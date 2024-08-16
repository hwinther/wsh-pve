ARG VERSION_INCREMENTS=1
FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/pve-qemu /src/submodules/pve-qemu
COPY submodules/pve-qemu.patch /src/submodules/pve-qemu.patch
COPY .git /src/.git
WORKDIR /src/submodules/pve-qemu
RUN patch -p1 -i ../pve-qemu.patch
ENV EMAIL=docker@wsh.no
RUN for i in $(seq 1 ${VERSION_INCREMENTS}); do \
    dch -l +wsh -D bookworm "Add WSH patches"; \
done
RUN grep "\+wsh" debian/changelog
RUN make deb

FROM scratch AS final
COPY --from=build /src/submodules/pve-qemu/*.deb /opt/repo/
RUN ls -l /opt/repo
CMD ["bash"]
