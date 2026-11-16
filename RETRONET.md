# Retro net

A design note, written 2026-11-16 from a study of existing projects. Nothing here is built yet
except the dial-up part (`docs/src/content/docs/guides/dialup.md`, `e2e/dialup`). "Read" below means
read in the project's source or documentation; nothing was installed or run.

The aim: a retro guest reaches a period "ISP" through its network card or through a modem on its
serial port, and gets a web it can display and the services of its time, without settings in the
guest where that can be avoided. The guest must not reach the node or the LAN through it.

## Decided

- **One network first, and it is the web of 1999.** One isolated segment and one service
  container. Later, other years or other kinds of page conversion can be chosen by the number
  dialled or by the proxy address.
- **No GUI for now.** Documentation and tests first. A GUI, if it comes, is one "Modem" checkbox
  that stores its state in settings that already exist (`serialN: socket`, a VM tag, the bridge).
- **No new keys in VM configs.** qemu-server refuses a config with a key it does not know, so a VM
  with a `modem0:` line would not start once an optional package is removed.
- **Optional.** Everything is a separate package or container that cannot break the core packages.

## Topology

```
 PVE node (no address on the retro segment)
   VM, NIC (ne2k, pcnet, lance, sunhme ...) ──┐
   VM, NIC ───────────────────────────────────┼── retro segment (layer 2 only)
                                              │
   VM, serial port as a modem                 │ eth0, the gateway address
     /var/run/qemu-server/<vmid>.serialN      │
       │ relay on the node (socat)       ┌────┴───────────────────────────┐
       └──► /run/wsh-retro/modem/ ──────►│ service container (LXC)        │
            (the only directory shared   │  modem emulator, pppd          │
             with the container)         │  DHCP, DNS overrides           │
                                         │  redirects for 80 and IM ports │
                                         │  proxies, period services      │
                                         └────┬───────────────────────────┘
                                              │ eth1, uplink
                                              ▼ only DNS and 80/443 to the internet; the LAN is denied
```

- The segment is a bridge or an SDN VNet used as layer 2 only, with no gateway address on the node:
  a gateway there would let guests reach the node's own services.
- The service container is the only way out. Its uplink is filtered so the proxies cannot be used
  to reach the node or the LAN, both by the node's firewall and inside the container.
- Dial-up guests land in the same subnet as NIC guests: the modem emulator and `pppd` (with
  `proxyarp`) run in the container, and the node only relays the VM's serial socket into one shared
  directory. The directory `/var/run/qemu-server` itself must never be shared with the container: it
  also holds every VM's QMP socket.
- slirp is not used on this network: it would hide every dial-up guest behind the container's own
  address, and settings per guest address would stop working.

## Services

| Part | Candidate | Why | To know |
| --- | --- | --- | --- |
| Archive web, portal, period services | [VintageHive](https://github.com/FoxCouncil/VintageHive) (MIT, .NET) | Wayback Machine for a chosen year (1997–2021, per client address) and ProtoWeb; AIM/ICQ, Yahoo, MSN, FTP, a telnet BBS, news, Gopher, radio in one process | Alpha, one maintainer, last tagged release 2023: pin a commit and build it. No PPP, DHCP or NTP. Default admin password, an open SOCKS proxy, an HTTPS proxy that fetches any address, and Wayback lookups through the author's own relay by default: all to be changed or switched off. Its HTTPS side loads a bundled x86-64 OpenSSL 1.0.2a |
| Today's web for old browsers | [WebOne](https://github.com/atauenis/webone) | HTTPS fetched upstream and served as HTTP, image conversion, PAC and WPAD, SSL 3 and TLS 1.0 on Linux | Not for the first network (1999 only). Its licence asks that users are told their traffic is changed |
| AIM/ICQ, if VintageHive's is not enough | [Open OSCAR Server](https://github.com/mk6i/open-oscar-server) (MIT) | The more mature implementation; TOC and old ICQ over UDP | Uses the same port as VintageHive's: one of them per network. Creates users without a password by default |
| Pages that need JavaScript | [WRP](https://github.com/tenox7/wrp) (Apache-2.0) | Renders the page to an image map | Needs Chromium; later |
| Fallback archive proxy | [WaybackProxy](https://github.com/richardg867/WaybackProxy) (GPL-3.0) | Simple, has an image | |

Later additions the owner has material for: a Battle.net-compatible server for StarCraft, and a
period IRC network (server, services, eggdrop bots, mIRC set-ups).

## What the guest must still do itself

- A browser from before 1996 sends no `Host:` header and needs the proxy typed in.
- HTTPS: a transparent proxy cannot work for SSL 2 and SSL 3 clients (they do not name the host).
  Old browsers stay on `http://` and the proxy fetches HTTPS for them. A guest that must speak HTTPS
  to the proxy needs the proxy's CA installed.
- Guests without a DHCP client (Windows 3.x with Trumpet, SunOS 4) get a fixed address by hand.

## Stages

| Stage | What | Tested by |
| --- | --- | --- |
| 0 | By hand: a VM on an isolated bridge running VintageHive, the proxy typed into one guest | a smoke test with `curl` |
| 1 | The service container as gateway for NIC guests: DHCP, DNS overrides, redirect of port 80 and the IM ports, uplink filter | a compose stack in CI: an HTTP/1.0 client gets the archived fixture (a fake Wayback server, no internet), an OSCAR login from a small script, and negative tests that the node and private ranges are unreachable directly and through the proxies |
| 2 | Dial-up into the same network: modem emulator and `pppd` in the container, the relay on the node | `e2e/dialup` extended: the tiny guest dials, gets an address in the retro subnet and fetches a page through the proxy |
| 3 | Packaging: an optional package for the node (relay unit, a small command), the container as a template | install tests in containers |
| 4 | GUI, if still wanted | Playwright |

Not worth doing: transparent HTTPS for old clients, Docker inside an LXC container, an SDN plug-in,
running any of these services on the node.

## Open

- Whether guests on this network may also reach today's internet (with the LAN denied), or only
  the 1999 web and the local services.
- Addressing for dial-up and fixed-address guests (an address derived from the VM id is the
  simplest), and whether settings per guest key on the address.
- Whether the Wayback lookups go straight to archive.org or through VintageHive's relay.
- Names: nothing in a package or the UI is named after AIM, ICQ, MSN or Battle.net. Client software
  for them is the user's own and is neither shipped nor downloaded by tests.
