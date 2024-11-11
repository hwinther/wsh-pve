FROM scratch AS build
LABEL org.opencontainers.image.title="qemu-server+wsh"
LABEL org.opencontainers.image.description="Proxmox VE QEMU Server + wsh patch"
COPY /build/repo /build/repo

FROM scratch AS final
COPY --from=build /build/repo/qemu-server_*.deb /opt/repo/
CMD ["bash"]
