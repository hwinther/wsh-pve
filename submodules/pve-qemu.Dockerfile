FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
LABEL org.opencontainers.image.title="pve-qemu+wsh"
LABEL org.opencontainers.image.description="Proxmox VE QEMU/KVM + wsh patch"
COPY --from=build /build/repo/pve-qemu_*.deb /opt/repo/
CMD ["bash"]
