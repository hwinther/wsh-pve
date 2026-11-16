---
title: Dial-up modem
description: Emulated modem dial-up from a guest's serial port, for retro guests that expect a modem
---

A guest that only knows how to reach a network through a modem can dial out over its serial port: a
modem emulator on the Proxmox VE node answers the AT commands, and a PPP server behind it gives the
guest an address. Nothing here needs the WSH packages; it is a recipe for the node.

:::caution
The mechanics were tested end to end in a container (`e2e/dialup` in the repository) with a Linux
guest. The Proxmox VE parts (the per-VM service and the hookscript) and the Windows settings follow
from that but have not been run on a node or in a Windows guest.
:::

## How it fits together

1. The VM gets `serial0: socket`. QEMU exposes the guest's COM1 as the UNIX socket
   `/var/run/qemu-server/<vmid>.serial0`.
2. [atduck](https://github.com/nandhp/atduck), a Hayes modem emulator, connects to that socket and
   answers `ATDT<number>`.
3. Each number in atduck's dial plan starts a program on a pty: slirp for user-mode networking
   without a login, or a real `pppd` server with a user name and password.

Only one program can hold the socket, so `qm terminal <vmid>` and atduck exclude each other. If the VM
uses `vga: serial0`, put the modem on `serial1: socket` (COM2).

## If PPP hangs while a BBS number works

Debian's `/usr/bin/slirp` exits about a millisecond after it starts on any 64-bit host: a timeout of
-1 is stored through a 32-bit cast, `select()` fails, and slirp quits right after its first packet.
atduck then drops back to command mode with echo on, and the guest sees its own PPP frames come back
(`Serial line is looped back` in pppd; Windows stays on "Verifying user name and password"). Numbers
that do not start slirp, such as telnet targets, are not affected.

Two ways out:

- **No build:** use `slirp-fullbolt` from the same package, which is built without the faulty code.
  It needs the node's host name to resolve to a real address, which is normal on a Proxmox VE node.
- **Patched package:** rebuild `slirp` with the two patches in `e2e/dialup/patches` (the fix, and
  atduck's patch for host names that resolve to loopback). `e2e/dialup/Dockerfile` shows the steps.

## Setup on the node

```sh
qm set 102 --serial0 socket
apt install slirp ppp perl libio-pty-perl git
git clone https://github.com/nandhp/atduck /opt/atduck
ln -sf /usr/bin/slirp-fullbolt /opt/atduck/slirp-nandhp-patch
```

Replace everything after `__DATA__` in `/opt/atduck/lib/ATduck/DialPlan.pm` with
`e2e/dialup/files/dialplan-restricted.txt`. atduck's own plan has a number that gives a shell on the
node as the atduck user, numbers that telnet anywhere, and dial-out; the restricted plan has none of
those.

| Number | ISP side | Login | Needs |
| --- | --- | --- | --- |
| 5555 | slirp, PPP | none (any name and password) | nothing; runs unprivileged |
| 5556 | slirp, SLIP | none | nothing |
| 5557 | `pppd` | PAP | root, NAT |
| 5558 | `pppd` | none | root, NAT |
| 5559 | `pppd` | MS-CHAPv2 | root, NAT |
| 5560 | `pppd` | MS-CHAPv2 with 128-bit MPPE | root, NAT, `ppp_mppe` |
| 5561 | `pppd call dialup-isp` | PAP | group `dip`; runs unprivileged |

For the `pppd` numbers: install `e2e/dialup/files/isp-pppd` to `/usr/local/sbin/`, and
`peers-dialup-isp` to `/etc/ppp/peers/dialup-isp` with `ms-dns` set to your resolver; put a line such
as `dialup * secret *` in `/etc/ppp/pap-secrets` and `/etc/ppp/chap-secrets` (mode 600); enable
`net.ipv4.ip_forward` and masquerade the link addresses (10.0.3.0/24 by default).

Run it by hand with `cd /opt/atduck && ./atduck unix:/var/run/qemu-server/102.serial0`, or per VM
with `e2e/dialup/files/atduck@.service` and the hookscript `dialup-hook.sh`. QEMU creates the socket
as `root:root 0755`, so an unprivileged atduck cannot open it until the hookscript changes its group.
atduck exits when the VM stops (the unit restarts it), and its children outlive a plain kill (the
unit kills the whole control group).

## In the guest

**Linux:**

```sh
pppd /dev/ttyS0 115200 connect "chat -v -f /etc/ppp/chat" disconnect "chat -v -f /etc/ppp/hangup" \
  noauth local nocrtscts noipdefault defaultroute usepeerdns
```

`/etc/ppp/chat`:

```text
"" ATZ
OK ATDT5555
CONNECT ""
```

`/etc/ppp/hangup`:

```text
"" "\d\d+++\d\d\c"
OK ATH0
OK ""
```

The hang-up script matters: the modem control lines do not cross the socket, so without `+++` and
`ATH0` the modem stays online and the next call fails. For 5557 add `user dialup` and the matching
`pap-secrets` line.

**Windows 9x, NT 4, XP** (not tested):

- Add a "Standard 28800 bps Modem" or "Standard 56000 bps Modem" on COM1 by hand, maximum speed
  115200, "Wait for dial tone" off.
- Number 5557 with the user name and password from `pap-secrets`, or 5555 with anything.
- Server type PPP. Off: "Log on to network", "Require encrypted password", "Require data
  encryption" (or dial 5559 and 5560 for those).
- TCP/IP only. slirp never answers NetBEUI or IPX/SPX, and the connection stalls on them.

## What to expect

At 115200, on a busy host: about 11–14 kB/s down and 20 kB/s up, and 3–6 ms round trip through
`pppd` or 12–16 ms through slirp. QEMU's emulated 16550 limits the download rate; a higher port speed
in the guest is accepted and gains nothing. QEMU uses about one host core while the link is busy.

## Security

- With slirp the guest reaches services bound to the node's 127.0.0.1 through 10.0.2.2. Prefer the
  `pppd` numbers with a firewall rule if that matters.
- Use the restricted dial plan.
