FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
ARG IMAGE_DESCRIPTION="Proxmox VE QEMU/KVM + wsh patch"
LABEL org.opencontainers.image.title="pve-qemu+wsh"
LABEL org.opencontainers.image.description="$IMAGE_DESCRIPTION"
COPY --from=build /build/repo/pve-qemu-kvm_*.deb /opt/repo/
CMD ["bash"]
