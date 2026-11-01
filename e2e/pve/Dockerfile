# A single-node Proxmox VE in a container, for the e2e tests: the web UI (pveproxy on 8006), the API
# and `qm`, with the WSH packages installed over the Proxmox ones. It never starts a guest; the tests
# create VMs and check the resulting /etc/pve/qemu-server/<vmid>.conf and `qm showcmd` output.
#
# Runs systemd as PID 1 in a privileged container (pmxcfs mounts /etc/pve with FUSE). No kernel, no
# cluster, no storage daemons: only pve-cluster (pmxcfs), pvedaemon and pveproxy.
#
# Build context: the repository root (for proxmox-archive-keyring-trixie.gpg and repo/conf).
#
#   PACKAGES=repo     install the WSH packages from the published apt repo (debian.wshosting.no)
#   PACKAGES=local    install the .deb files in e2e/pve/debs/ instead (the build-deb artifacts)
FROM debian:13

ARG PVE_COMPONENT=pve-no-subscription
ARG PACKAGES=repo

ENV DEBIAN_FRONTEND=noninteractive \
    container=docker

COPY proxmox-archive-keyring-trixie.gpg /usr/share/keyrings/proxmox-archive-keyring.gpg
COPY repo/conf/wsh-pve.gpg.key /tmp/wsh-pve.gpg.key

# Package scripts must not try to start services during the build; systemd starts them at run time.
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d

RUN apt-get update \
    && apt-get install --no-install-recommends --assume-yes ca-certificates gnupg \
    && gpg --dearmor < /tmp/wsh-pve.gpg.key > /usr/share/keyrings/wsh-pve.gpg \
    && printf 'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: %s\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n' \
        "$PVE_COMPONENT" > /etc/apt/sources.list.d/proxmox.sources \
    && if [ "$PACKAGES" = repo ]; then \
        printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
            > /etc/apt/sources.list.d/wsh-pve.sources; \
        printf 'Package: pve-manager qemu-server pve-qemu-kvm\nPin: origin debian.wshosting.no\nPin-Priority: 1001\n' \
            > /etc/apt/preferences.d/wsh-pve; \
    fi

COPY e2e/pve/debs/ /tmp/debs/

# The PVE stack without the kernel or proxmox-ve meta package. With PACKAGES=local, apt installs the
# local .debs in the same transaction so their dependencies resolve from the Proxmox repo.
RUN apt-get update \
    && LOCAL_DEBS="" \
    && if [ "$PACKAGES" = local ]; then LOCAL_DEBS="$(ls /tmp/debs/*.deb)"; fi \
    && apt-get install --no-install-recommends --assume-yes \
        systemd systemd-sysv dbus iproute2 curl procps \
        pve-cluster pve-manager qemu-server pve-qemu-kvm proxmox-widget-toolkit \
        $LOCAL_DEBS \
    && rm -rf /var/lib/apt/lists/* /tmp/debs

# Everything a container node doesn't need. Masking a unit that doesn't exist is harmless.
RUN systemctl mask \
        pve-firewall.service pve-ha-crm.service pve-ha-lrm.service pve-guests.service \
        pvescheduler.service pvebanner.service pvenetcommit.service corosync.service \
        ksmtuned.service ksm.service lxcfs.service lxc.service lxc-net.service lxc-monitord.service \
        spiceproxy.service proxmox-firewall.service pve-lxc-syscalld.service \
        postfix.service chrony.service systemd-timesyncd.service smartmontools.service \
        rpcbind.service rpcbind.socket nfs-blkmap.service open-iscsi.service iscsid.service iscsid.socket \
        lvm2-monitor.service lvm2-lvmpolld.socket dm-event.socket blk-availability.service \
        zfs-import-cache.service zfs-import-scan.service zfs-mount.service zfs-share.service zfs-zed.service \
        ceph.target rrdcached.service \
        systemd-networkd.service systemd-networkd.socket systemd-resolved.service networking.service \
        getty@tty1.service console-getty.service systemd-logind.service \
        apt-daily.timer apt-daily-upgrade.timer e2scrub_all.timer fstrim.timer \
    && rm -f /usr/sbin/policy-rc.d

COPY e2e/pve/pve-e2e-setup.sh /usr/local/sbin/pve-e2e-setup
COPY --chmod=644 e2e/pve/pve-e2e-setup.service /etc/systemd/system/
COPY e2e/pve/entrypoint.sh /usr/local/sbin/entrypoint
RUN chmod +x /usr/local/sbin/pve-e2e-setup /usr/local/sbin/entrypoint \
    && systemctl enable pve-e2e-setup.service

EXPOSE 8006
STOPSIGNAL SIGRTMIN+3
HEALTHCHECK --interval=5s --timeout=5s --start-period=60s --retries=24 \
    CMD test -f /run/pve-e2e-ready && curl -skf -o /dev/null https://localhost:8006/

ENTRYPOINT ["/usr/local/sbin/entrypoint"]
