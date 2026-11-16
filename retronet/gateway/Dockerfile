# The retro net gateway: one image with DHCP/DNS (dnsmasq), the redirects and the egress filter
# (nftables), an allowlisting egress proxy (tinyproxy) and VintageHive, run by a small supervisor
# under tini. The same image runs under Docker and as a Proxmox VE container created from an OCI image.
#
#   docker build -f retronet/gateway/Dockerfile -t retronet-gateway retronet
#
# amd64 only: VintageHive is published self-contained for linux-x64.

# VintageHive, built from a pinned commit (https://github.com/FoxCouncil/VintageHive, MIT).
FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:fe0fd4e93bd2fbb47c883b7a6369e5c8d3db8bf01cdc5981f6ee35fbdf3ff4fb AS vintagehive
ARG VINTAGEHIVE_COMMIT=5c2d4f0e8526d54f5f4da3542344d11b7cd49285
WORKDIR /src
RUN git init -q . \
 && git remote add origin https://github.com/FoxCouncil/VintageHive.git \
 && git fetch -q --depth 1 origin "$VINTAGEHIVE_COMMIT" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "$VINTAGEHIVE_COMMIT"
# One local change: build the HTTPS listener only when that service is on (gateway/patches).
COPY gateway/patches/ /patches/
RUN git apply --verbose /patches/vintagehive-*.patch
RUN dotnet publish VintageHive.csproj -c Release -r linux-x64 --self-contained true \
      -p:UseAppHost=true -p:PublishReadyToRun=false -o /out \
 # Not used here, and not redistributed: ffmpeg (radio is off), the Windows DLLs, Ghostscript (printing
 # is off) and the bundled OpenSSL 1.0.2a (only the HTTPS "DialNine" proxy loads it, and it is off).
 && rm -f /out/libs/ffmpeg* /out/libs/*.dll /out/libs/libssl.so /out/libs/libcrypto.so \
 && cp LICENSE /out/LICENSE.VintageHive \
 && echo "$VINTAGEHIVE_COMMIT" > /out/VINTAGEHIVE_COMMIT

FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
LABEL org.opencontainers.image.source="https://github.com/hwinther/wsh-pve" \
      org.opencontainers.image.description="Retro net gateway: DHCP, DNS, filtered egress and the web of 1999 (VintageHive) for retro guests"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tini dnsmasq-base nftables tinyproxy sqlite3 iproute2 procps ca-certificates libicu76 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --home-dir /var/lib/retronet/vintagehive --shell /usr/sbin/nologin vintagehive \
 && getent passwd dnsmasq tinyproxy >/dev/null

COPY --from=vintagehive /out /opt/vintagehive
COPY gateway/rootfs/ /
COPY services/ /etc/retronet/services.d/
RUN chmod 0755 /usr/local/sbin/retronet-* /etc/retronet/services.d/*/run /etc/retronet/services.d/*/init 2>/dev/null; \
    chmod 0755 /opt/vintagehive/VintageHive \
 # VintageHive opens libs/geonames.db in WAL mode, which needs a writable directory
 && chown -R vintagehive:vintagehive /opt/vintagehive/libs \
 # VintageHive keeps its state in <app dir>/vfs; point that at the state directory.
 && ln -s /var/lib/retronet/vintagehive /opt/vintagehive/vfs \
 && rm -f /etc/retronet/services.d/README.md

# All state lives here (leases, VintageHive's databases and hosted files, the generated admin password).
VOLUME /var/lib/retronet

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=3 CMD ["/usr/local/sbin/retronet-health"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/sbin/retronet-entrypoint"]
