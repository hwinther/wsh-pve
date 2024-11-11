FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
LABEL org.opencontainers.image.title="qemu-server+wsh"
LABEL org.opencontainers.image.description="Proxmox VE QEMU Server + wsh patch"
COPY --from=build /build/repo/qemu-server_*.deb /opt/repo/
CMD ["bash"]
