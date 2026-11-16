# Retro net

A design note, written 2026-11-16 from a study of existing projects. Built so far: the dial-up part
(`docs/src/content/docs/guides/dialup.md`, `e2e/dialup`) and stages 0 and 1, the gateway image
(`retronet/`, `docs/src/content/docs/guides/retronet.md`; see "Stages 0 and 1: built"). "Read"
below means read in the project's source or documentation.

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
| 0 | By hand: a VM on an isolated bridge running VintageHive, the proxy typed into one guest | a smoke test with `curl`. **Written** (guide, "Trial by hand on a node"), not run on a node; the same image ran by hand under Docker against the real archive.org |
| 1 | The service container as gateway for NIC guests: DHCP, DNS overrides, redirect of port 80 and the IM ports, uplink filter | a compose stack in CI: an HTTP/1.0 client gets the archived fixture (a fake Wayback server, no internet), an OSCAR login from a small script, and negative tests that the node and private ranges are unreachable directly and through the proxies. **Built**: `retronet/test.sh`, workflow `retronet.yml` |
| 2 | Dial-up into the same network: modem emulator and `pppd` in the container, the relay on the node | `e2e/dialup` extended: the tiny guest dials, gets an address in the retro subnet and fetches a page through the proxy |
| 3 | Packaging: an optional package for the node (relay unit, a small command), the container as a template | install tests in containers |
| 4 | GUI, if still wanted | Playwright |

Not worth doing: transparent HTTPS for old clients, Docker inside an LXC container, an SDN plug-in,
running any of these services on the node.

## Stages 0 and 1: built

The gateway is one OCI image (`retronet/gateway/Dockerfile`), used three ways: under Docker on a
host that has the retro VLAN (macvlan, or host networking in a dedicated VM), pulled by Proxmox VE
9.1+ as a container from an OCI image (two network devices: the retro bridge and the uplink), and in
CI. This replaces "service container (LXC)" above: the same image is the LXC container. Debian 13;
dnsmasq, nftables, tinyproxy and VintageHive run under `tini` and a small supervisor script, no
systemd; all state in `/var/lib/retronet`; configuration by `RETRONET_*` variables or one mounted
`retronet.conf`, so a container recreated from a new image loses nothing else. Services sit in
`retronet/services/<name>/` (run script, redirects, DNS names, egress allowlist), which leaves room
for the later ones (a Battle.net-compatible server, an IRC network) without touching the core; the
year is one key, `year`.

Decisions taken while building (they fill in or change what is above):

- **Today's internet: no** (the first open question). Guests get the 1999 web and the local services
  only. DNS is a walled garden with real names: dnsmasq answers the portal and the period sign-on
  names with the gateway's address and forwards the rest upstream, but every connection from the
  segment ends at the gateway, redirected to a local service or refused (TCP reset; 443 included). No
  packet from the segment is routed. What breaks: everything that is not plain HTTP or one of the
  redirected services (ping beyond the gateway, NTP, POP/SMTP/IRC/FTP to real servers, games, HTTPS).
- **Archive lookups go straight to web.archive.org** (the third open question). VintageHive's relay
  (its "worker", on by default and pointing at its author's Cloudflare cache) is off and can be set
  with `archive_relay`.
- **Egress is enforced outside VintageHive.** VintageHive reaches today's web in several places: a
  built-in list of live sites it passes through (68k.news, FrogFind and others), the portal's news,
  weather and search, radio, the gopher relay, and its archive path, which fetches any URL whose host
  merely *contains* `web.archive.org`. Its own "walled garden" switch refuses to start with the
  archive on, so it does not help here. Instead: VintageHive's HTTP clients go through tinyproxy (the
  environment proxy), which only connects to `*.archive.org`; the nftables `output` chain lets only
  tinyproxy open ports 80 and 443, only dnsmasq send DNS (to the configured servers), and
  VintageHive reach ProtoWeb's proxy port 7851, and refuses private, loopback, link-local, CGNAT and
  reserved addresses for everyone. Nothing listens on the uplink.
- **Instant messaging stays with VintageHive's OSCAR server.** The test's own client signs on with
  the MD5 method (auth key, hashed password, BOS redirect with a cookie) and passes a message between
  two sessions; Open OSCAR Server was not needed. MSNP and YMSG are on as well, untested.
- **Switched off in this stage** (and written back on every start): SOCKS, the HTTPS "DialNine"
  proxy, VintageHive's DNS server (dnsmasq answers), gopher, radio (MMS, PNA), mail, IRC, printing,
  NetMeeting, the file-transfer relay. VintageHive's default admin password is never left in place.
- **One VintageHive patch.** Its HTTPS listener loaded the bundled OpenSSL 1.0.2a in its constructor
  even with HTTPS off, so the image could not drop that library. The patch builds the listener only
  when the service is on (`retronet/gateway/patches/`); the image ships no OpenSSL 1.0.2a, ffmpeg or
  Ghostscript.

Learned:

- VintageHive is active (commits into August 2026, .NET 10), unlike what its last release (2023)
  suggests. Its configuration is the `config` table of `vfs/data/hive.db` (key and value;
  per-address overrides in `config_local`), seeded with `sqlite3` before it starts. Its direct
  archive path has `http://web.archive.org` built in; only the relay URL is configurable, so the test
  points the name `web.archive.org` at its stand-in through the gateway's own DNS.
- A request without `Host:` is dropped by VintageHive without a response (the connection closes);
  browsers that old need the proxy set by hand.
- VintageHive's admin pages are served for loopback URLs through the proxy (`http://localhost/`), so
  every guest can reach the login page.
- VintageHive's FTP server has no active mode (so no FTP bounce) and no authentication: any guest can
  upload to its hosting area.
- dnsmasq's rebind protection also refuses the documentation ranges (192.0.2.0/24, 198.51.100.0/24,
  203.0.113.0/24), so the test's fake internet uses 192.88.99.0/24.
- Some sites have no captures any more: `www.cnn.com` returns nothing for any year (excluded from the
  Wayback Machine); `www.netscape.com` for 1999 came back in 3 s with its links rewritten.
- Under Docker, `ip_forward` is read-only in the container, and Docker may put the default route on
  the retro network; the gateway removes that route.

## Open

- One gateway for the cluster or one per node. A shared gateway needs the retro network as a VLAN or
  SDN VNet on every node and, for the dial-up stage, a TCP relay from the node that runs the VM to the
  gateway, because the VM's serial socket is a local file on that node. A gateway per node needs
  neither: a container on the same node can have the relay directory bind-mounted. The image works
  either way.
- Whether the gateway should offer today's web later (WebOne) on a second network or proxy address.
- Addressing for dial-up and fixed-address guests (an address derived from the VM id is the
  simplest), and whether settings per guest key on the address.
- Names: nothing in a package or the UI is named after AIM, ICQ, MSN or Battle.net. Client software
  for them is the user's own and is neither shipped nor downloaded by tests.
