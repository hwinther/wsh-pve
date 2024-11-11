FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
LABEL org.opencontainers.image.title="pve-manager+wsh"
LABEL org.opencontainers.image.description="Proxmox VE Manager + wsh patch"
COPY --from=build /build/repo/pve-manager_*.deb /opt/repo/
CMD ["bash"]
