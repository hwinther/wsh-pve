---
title: Setup Guide
description: Setting up the debian repository source and installing the packages
---

The following steps describe how you can add the PVE WSH debian repository in your proxmox cluster nodes.

You can choose to only install the packages on a few nodes in a given cluster, but you will not be able to migrate or restore guests with the extended configuration values to non-compatible PVE nodes.

## Installing the repository

```bash
# Add the repository signing key
sudo wget -O - /usr/share/keyrings/wsh-pve.gpg | gpg --dearmor -o /etc/apt/keyrings/wsh-pve.gpg

# Add the repository
sudo wget -O /etc/apt/sources.list.d/wsh-pve.sources http://debian.wshosting.no/debian/conf/wsh-pve.sources

# Update repository cache and show packages that can be installed
sudo apt update && sudo apt list --upgradable
pve-manager/stable 8.3.5+wsh1 all [upgradable from: 8.3.4+wsh1]
pve-qemu-kvm/stable 9.2.0-1+wsh2 amd64 [upgradable from: 9.1.2-3+wsh1]
qemu-server/stable 8.3.8+wsh3 amd64 [upgradable from: 8.3.8+wsh2]

# Install the replacement packages
sudo apt full-upgrade
```
