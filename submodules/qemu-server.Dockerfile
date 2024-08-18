FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
ARG VERSION_INCREMENTS=1
COPY submodules/qemu-server /src/submodules/qemu-server
COPY submodules/qemu-server.patch /src/submodules/qemu-server.patch
COPY .git /src/.git
WORKDIR /src/submodules/qemu-server
RUN patch -p1 -i ../qemu-server.patch
# TODO: fix the tests instead of skipping them
ENV DEB_BUILD_OPTIONS=nocheck
ENV EMAIL=docker@wsh.no
RUN GIT_CHANGES=$(git log -1 --pretty=format:%s -- ../qemu-server.patch)\
    dch -l +wsh -D bookworm "${GIT_CHANGES}"
RUN grep "\+wsh" debian/changelog
RUN git diff -p debian/changelog > /tmp/changelog.diff
RUN make deb
RUN ls -l /src/submodules/qemu-server/*.deb

FROM scratch AS final
COPY --from=build /src/submodules/qemu-server/*.deb /opt/repo/
CMD ["bash"]
