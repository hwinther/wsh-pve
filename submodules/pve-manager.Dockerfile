FROM scratch AS build
LABEL org.opencontainers.image.title="pve-manager+wsh"
LABEL org.opencontainers.image.description="Proxmox VE Manager + wsh patch"
COPY /build/repo /build/repo

FROM scratch AS final
COPY --from=build /build/repo/pve-manager_*.deb /opt/repo/
CMD ["bash"]
