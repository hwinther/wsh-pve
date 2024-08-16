ARG VERSION_INCREMENTS=1
FROM ghcr.io/hwinther/wsh-pve/pve-build:12 AS build
COPY submodules/pve-manager /src/submodules/pve-manager
COPY submodules/pve-manager.patch /src/submodules/pve-manager.patch
COPY .git /src/.git
WORKDIR /src/submodules/pve-manager
RUN patch -p1 -i ../pve-manager.patch
ENV EMAIL=docker@wsh.no
RUN for i in $(seq 1 ${VERSION_INCREMENTS}); do \
    dch -l +wsh -D bookworm "Add WSH patches"; \
done
RUN grep "\+wsh" debian/changelog
RUN make deb

FROM scratch AS final
COPY --from=build /src/submodules/pve-manager/*.deb /opt/repo/
RUN ls -l /opt/repo
CMD ["bash"]
