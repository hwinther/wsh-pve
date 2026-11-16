# Helpers for the retro net test: the fake internet (Wayback stand-in and DNS), the LAN canary and
# the retro client. One image, three commands (see retronet/compose.test.yml).
FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 curl busybox dnsmasq-base bind9-dnsutils iproute2 iputils-ping ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY . /opt/retronet-test/
RUN chmod 0755 /opt/retronet-test/*.sh /opt/retronet-test/*.py /opt/retronet-test/udhcpc.script
WORKDIR /opt/retronet-test
