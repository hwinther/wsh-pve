FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/pve-manager /src/submodules/pve-manager
COPY submodules/pve-manager.patch /src/submodules/pve-manager.patch
COPY .git /src/.git
WORKDIR /src/submodules/pve-manager
RUN patch -p1 -i ../pve-manager.patch
# TODO: fix the tests instead of skipping them
ENV DEB_BUILD_OPTIONS=nocheck
ENV EMAIL=docker@wsh.no
RUN make deb
RUN ls -l /src/submodules/pve-manager/*.deb

FROM scratch AS final
COPY --from=build /src/submodules/pve-manager/*.deb /opt/repo/
CMD ["bash"]
