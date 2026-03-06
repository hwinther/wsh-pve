FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
ARG IMAGE_DESCRIPTION="Proxmox VE QEMU Server + wsh patch"
LABEL org.opencontainers.image.title="qemu-server+wsh"
LABEL org.opencontainers.image.description="$IMAGE_DESCRIPTION"
COPY --from=build /build/repo/qemu-server_*.deb /opt/repo/
CMD ["bash"]
