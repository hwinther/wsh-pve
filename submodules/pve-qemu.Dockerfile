FROM scratch AS build
LABEL org.opencontainers.image.title="pve-qemu+wsh"
LABEL org.opencontainers.image.description="Proxmox VE QEMU/KVM + wsh patch"
COPY /build/repo /build/repo

FROM scratch AS final
COPY --from=build /build/repo/pve-qemu-kvm_*.deb /opt/repo/
CMD ["bash"]
