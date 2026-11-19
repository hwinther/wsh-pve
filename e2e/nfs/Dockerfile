# An NFSv4 server for the e2e tests (docker-compose.e2e.yml, service nfs): NFS-Ganesha, which serves
# NFS from user space, so the runner needs no nfsd kernel module. It exports /export read-write without
# root squash; the PVE container mounts it as an NFS storage (tests/mirror.spec.ts). /export must be a
# volume: Ganesha's VFS backend needs file handles, which neither the container's overlay nor a tmpfs
# gives it.
#
# Build context: e2e/nfs.
FROM debian:13

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes nfs-ganesha nfs-ganesha-vfs \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /export /var/run/ganesha /var/lib/nfs/ganesha

COPY ganesha.conf /etc/ganesha/ganesha.conf

EXPOSE 2049
HEALTHCHECK --interval=2s --timeout=2s --start-period=5s --retries=15 \
    CMD bash -c '</dev/tcp/127.0.0.1/2049'

# -F: foreground; the log to stdout (docker logs)
CMD ["ganesha.nfsd", "-F", "-L", "/dev/stdout", "-f", "/etc/ganesha/ganesha.conf"]
