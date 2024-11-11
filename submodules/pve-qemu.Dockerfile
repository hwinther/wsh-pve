FROM scratch AS final
COPY --from=build /build/repo/pve-qemu_*.deb /opt/repo/
CMD ["bash"]
