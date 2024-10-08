FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/qemu-server /src/submodules/qemu-server
COPY submodules/qemu-server.patch /src/submodules/qemu-server.patch
COPY .git /src/.git
WORKDIR /src/submodules/qemu-server
RUN patch -p1 -i ../qemu-server.patch
# TODO: fix the tests instead of skipping them
ENV DEB_BUILD_OPTIONS=nocheck
ENV EMAIL=docker@wsh.no
RUN make deb
RUN ls -l /src/submodules/qemu-server/*.deb

FROM scratch AS final
COPY --from=build /src/submodules/qemu-server/*.deb /opt/repo/
CMD ["bash"]
