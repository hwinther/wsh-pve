FROM ghcr.io/hwinther/wsh-pve/reprepro:latest AS install

FROM ghcr.io/hwinther/wsh-pve/qemu-server:latest AS qemu-server
FROM ghcr.io/hwinther/wsh-pve/pve-qemu:latest AS pve-qemu
FROM ghcr.io/hwinther/wsh-pve/pve-manager:latest AS pve-manager

FROM install AS final
RUN mkdir -p /opt/repo-incoming
COPY --from=qemu-server /opt/repo/*.deb /opt/repo-incoming/
COPY --from=pve-qemu /opt/repo/*.deb /opt/repo-incoming/
COPY --from=pve-manager /opt/repo/*.deb /opt/repo-incoming/

WORKDIR /opt/repo
COPY .gpg /tmp/.gpg-key
RUN cat /tmp/.gpg-key | gpg --import --batch
RUN /usr/bin/echo -e "use-agent\npinentry-mode loopback" > "$HOME/.gnupg/gpg.conf"
RUN /usr/bin/echo -e "allow-preset-passphrase\nallow-loopback-pinentry" > "$HOME/.gnupg/gpg-agent.conf"
RUN gpg --list-keys
COPY --chmod=755 scripts/reprepro.exp /usr/local/bin/reprepro.exp
CMD ["bash"]
