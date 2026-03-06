FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
ARG IMAGE_DESCRIPTION="Proxmox VE Manager + wsh patch"
LABEL org.opencontainers.image.title="pve-manager+wsh"
LABEL org.opencontainers.image.description="$IMAGE_DESCRIPTION"
COPY --from=build /build/repo/pve-manager_*.deb /opt/repo/
CMD ["bash"]
