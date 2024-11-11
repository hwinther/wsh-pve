FROM scratch AS build
COPY /build/repo /build/repo

FROM scratch AS final
COPY --from=build /build/repo/qemu-server_*.deb /opt/repo/
CMD ["bash"]
