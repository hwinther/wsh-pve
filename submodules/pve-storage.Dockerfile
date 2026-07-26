FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
ARG IMAGE_DESCRIPTION="Proxmox VE Storage + wsh patch"
LABEL org.opencontainers.image.title="pve-storage+wsh"
LABEL org.opencontainers.image.description="$IMAGE_DESCRIPTION"
COPY --from=build /build/repo/libpve-storage-perl_*.deb /opt/repo/
CMD ["bash"]
