ARG VERSION_INCREMENTS=1
FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/qemu-server /src/submodules/qemu-server
COPY submodules/qemu-server.patch /src/submodules/qemu-server.patch
COPY .git /src/.git
WORKDIR /src/submodules/qemu-server
RUN patch -p1 -i ../qemu-server.patch
# TODO: fix the tests instead of skipping them
ENV DEB_BUILD_OPTIONS=nocheck
ENV EMAIL=docker@wsh.no
RUN for i in $(seq 1 ${VERSION_INCREMENTS}); do \
    dch -l +wsh -D bookworm "Add WSH patches"; \
done
RUN grep "\+wsh" debian/changelog
RUN make deb

FROM scratch AS final
COPY --from=build /src/submodules/qemu-server/*.deb /opt/repo/
RUN ls -l /opt/repo
CMD ["bash"]
