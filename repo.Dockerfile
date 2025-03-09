FROM debian:12-slim AS install
LABEL maintainer="Hans Christian Winther-Sørensen <docker@wsh.no>"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install --no-install-recommends --assume-yes nginx reprepro expect nano && apt-get clean

FROM ghcr.io/hwinther/wsh-pve/qemu-server:latest AS qemu-server
FROM ghcr.io/hwinther/wsh-pve/pve-qemu:latest AS pve-qemu
FROM ghcr.io/hwinther/wsh-pve/pve-manager:latest AS pve-manager

FROM install AS final
RUN mkdir -p /opt/repo-incoming
COPY --from=qemu-server /opt/repo/*.deb /opt/repo-incoming/
COPY --from=pve-qemu /opt/repo/*.deb /opt/repo-incoming/
COPY --from=pve-manager /opt/repo/*.deb /opt/repo-incoming/
WORKDIR /opt/repo
# ENV GPG_TTY=/dev/console
COPY .gpg /tmp/.gpg-key
COPY .gpg-password /tmp/.gpg-password
# RUN cat /tmp/.gpg-key | gpg --import --batch
# ARG SIGNING_PASSWORD
# RUN echo ${SIGNING_PASSWORD} | gpg --pinentry-mode loopback --batch --yes --passphrase-fd 0 /tmp/.gpg-key
# RUN cat your-passphrase-file.txt | gpg --pinentry-mode loopback --passphrase-fd 0 --sign your-file-to-sign.txt 
RUN update-alternatives --set pinentry /usr/bin/pinentry-curses >/dev/null || gpg-connect-agent reloadagent /bye >/dev/null
RUN gpg --pinentry-mode loopback --passphrase-file=/tmp/.gpg-password /tmp/.gpg-key
RUN gpg --list-keys
COPY scripts/reprepro.exp /usr/local/bin/reprepro.exp
CMD ["bash"]
