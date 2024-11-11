FROM scratch AS final
COPY --from=build /build/pve-qemu/*.deb /opt/repo/
CMD ["bash"]
