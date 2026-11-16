---
title: Retro net
description: An isolated network for retro guests with the web of 1999 and period services, served by one gateway container
---

The retro net is an isolated network segment for retro guests. One gateway container on it hands
out addresses, answers DNS, and gives the guests the web as it was in 1999 (from the Internet
Archive's Wayback Machine and from [ProtoWeb](https://protoweb.org/)) and the services of the time:
instant messaging, FTP, a telnet BBS, news. A guest needs no proxy settings if its browser sends a
`Host:` header. The guests reach neither the Proxmox VE node nor the LAN through the gateway.

Nothing here needs the WSH packages. The design and its decisions are in `RETRONET.md` in the
repository; the image is built from `retronet/`.

:::caution
The gateway is tested in containers only (`retronet/test.sh`, run in CI). It has not run on a
Proxmox VE node, as a container created from an OCI image, with a macvlan network, or with a real
retro browser or messaging client. The sections that describe those are marked untested.
:::

## What the gateway does

| Guest does | Gateway does |
| --- | --- |
| Asks for an address (DHCP) | Hands one out from `.100`–`.199` of its subnet, with itself as router and DNS server. Fixed leases in `/var/lib/retronet/dhcp-hosts` (dnsmasq `dhcp-host` syntax). |
| Looks up a name | Answers `hive.com` and the sign-on servers of period messaging clients with its own address; forwards everything else to the configured upstream DNS. A DNS server set by hand in the guest is answered by the gateway too. |
| Opens `http://` to any address | Redirects it to the archive proxy, which uses the `Host:` header to fetch the 1999 copy of the page through the gateway's archive cache. |
| Sets a proxy by hand | The same proxy at `gateway:1990` or `gateway:80`. |
| Connects to port 21, 23, 79, 119, 5190, 1863 or 5050 anywhere | Redirects it to the gateway's FTP server, telnet BBS, finger, news server or instant-messaging servers (OSCAR, MSNP, YMSG). |
| Anything else beyond the gateway, HTTPS included | Refuses it at once (TCP reset, ICMP unreachable). No packet from the segment is ever routed. |

The services come from [VintageHive](https://github.com/FoxCouncil/VintageHive), built from a pinned
commit. The portal is at `http://hive.com/`.

### Browsers

- **Browsers that send `Host:`** (Netscape Navigator 2 and later, Internet Explorer 3 and later,
  Opera, Lynx, most browsers from 1996 on): nothing to set. They connect to the site's real address,
  the gateway redirects the connection, the proxy reads the host name from the request.
- **Browsers that send no `Host:`** (early Mosaic, Cello, MacWeb and other browsers from before
  1996): set the HTTP proxy to the gateway's address, port 1990. Without it the gateway cannot know
  which site was meant: the connection is closed without a response, which these browsers show as
  "document contains no data" or a similar error.
- **HTTPS:** not available in this stage. A connection to port 443 is refused at once, so a browser
  fails quickly instead of hanging. Old browsers stay on `http://`; most 1999 pages are plain HTTP.
  VintageHive's HTTPS proxy ("DialNine") is off.
- **Today's web:** not reachable. Requests go to the Wayback Machine for the configured year, or to
  ProtoWeb. VintageHive's features that use today's internet (news and weather on the portal, search,
  radio, its list of retro-friendly live sites such as 68k.news) answer with an error page.

### Instant messaging

Accounts are VintageHive accounts: 3–8 letters or digits, a password of 3–8 characters. Create them
in the admin pages, from a client that registers in-band, or on the gateway:

```sh
docker exec <gateway> retronet-user add alice secret1
docker exec <gateway> retronet-user list
```

Clients find the server by their built-in sign-on host names, which resolve to the gateway, or by any
address on port 5190, 1863 or 5050. The test signs on two OSCAR sessions with the MD5 method and
passes a message between them; no messaging client software is shipped or downloaded by the tests.

### Admin pages

From a guest with the proxy set, `http://localhost/` through the proxy opens VintageHive's admin
pages (user `admin`). The password comes from `RETRONET_ADMIN_PASSWORD`, `admin_password_file` or,
if neither is given, is generated on the first start and kept in `/var/lib/retronet/admin-password`.
VintageHive's default password is refused. Settings that matter for isolation and the year are
written again on every start (see "Configuration"), so a change to them in the admin pages lasts
until the next restart.

## Archive cache

Every Wayback Machine lookup VintageHive makes goes to the gateway's archive cache, a small service
on the gateway's loopback (`retronet/services/archive-cache/`). It answers from a store on the state
volume, `/var/lib/retronet/archive-cache`, and only on a miss asks web.archive.org, then keeps the
answer. A page that was visited once, or warmed beforehand, never goes to archive.org again.

VintageHive caches as well (in `vfs/data/cache.db`: the chosen capture per URL and year, and the
rewritten pages for a year), but it cannot replay without archive.org, its entries are tied to its
own rewriting, and images are not kept when it uses an archive endpoint like this one. The archive
cache keeps what archive.org sent, unchanged, so it survives VintageHive upgrades and can be moved
between gateways.

| Mode (`archive_mode`) | Behaviour |
| --- | --- |
| `online` (default) | Answers from the store; a miss is fetched from `archive_upstream`, stored and served. Misses are fetched one at a time, at most one every `archive_min_interval` seconds (5), with a descriptive User-Agent. A 429 or 503 with `Retry-After` is waited out (up to 15 s) and retried once. When archive.org refuses connections (here it did after about 15 requests, whether 1 or 5 s apart, and let go within a few minutes), the cache stops asking for a minute, doubling up to an hour, and answers "unreachable" meanwhile; `retronet-warm` waits that out. |
| `offline` | Replays the store only. Anything not stored is "not archived" for the guest; nothing leaves the gateway. |

"Not archived" answers are stored too. Online they are asked again after 30 days. Above
`archive_max_mb` (4096) the least recently used entries are removed.

The store is plain files you can look into:

```text
/var/lib/retronet/archive-cache/v1/cdx/<host>/<hash>.json   the lookup (URL, year) and when it was made
/var/lib/retronet/archive-cache/v1/cdx/<host>/<hash>.body   archive.org's answer
/var/lib/retronet/archive-cache/v1/web/<host>/<hash>.json   the capture asked for, its type and status
/var/lib/retronet/archive-cache/v1/web/<host>/<hash>.body   the capture exactly as archive.org sent it
```

Lookups are kept per year (the year is part of the lookup), and a capture by its timestamp, so a
later network with another year shares the captures and has its own lookups.

### Warming up and moving a store

```sh
docker exec <gateway> retronet-warm --requisites                  # the sites VintageHive features
docker exec <gateway> retronet-warm --requisites http://www.netscape.com/ http://www.geocities.com/
docker exec <gateway> retronet-warm -f /path/in/container/urls.txt
docker exec <gateway> retronet-archive stats --server             # entries, size, hits, misses
docker exec <gateway> retronet-archive export - > archive.tgz     # the whole store
docker exec -i <gateway> retronet-archive import - < archive.tgz  # into another gateway
docker exec <gateway> retronet-archive purge --yes
```

`retronet-warm` asks for each URL what a guest's browser would cause: the lookup for the configured
year, the capture VintageHive would pick (the largest of the year), and with `--requisites` the
page's images and frames (up to `--max-requisites`, 20). It prints one line per URL (archived, not
archived, or error) and a summary, which is the coverage report. Without URLs it warms
`/etc/retronet/services.d/archive-cache/default-urls.txt`: the portal's link list and the sites in
VintageHive's live-site list, made from VintageHive's source by `make-default-urls.py`. At the
default pace a page with three images takes about 25 s, and archive.org's refusals add pauses; let
a long list run overnight.

:::caution[What is redistributed]
A warmed store is a collection of third-party web pages as archived by the Internet Archive. It
stays on your gateway's volume. Export and import are for moving it between your own gateways. The
image and the repository carry no archived pages: only the tool, the list of URLs, and a small
synthetic dataset with made-up pages that the tests replay (`retronet/test/dataset`).
:::

## Requirements of every form

- **Layer 2 next to the guests.** DHCP and the redirects only work when the gateway sits on the
  guests' segment itself. The retro bridge or VNet must have no address on the node: an address
  there would let guests reach the node directly, past the gateway.
- **Two interfaces:** one on the retro segment with the gateway's address, one uplink. The interface
  that has `RETRONET_ADDRESS` is the retro side; every other interface is uplink.
- **`NET_ADMIN`** for nftables and dnsmasq's DHCP. The later dial-up stage will also need `/dev/ppp`.
- **State** in one directory, `/var/lib/retronet` (leases, the archive cache, VintageHive's databases
  and hosted files, the generated admin password). Make it a volume or a mount point.
- **Configuration** by environment variables or one mounted file, `/etc/retronet/retronet.conf`.
- **amd64 only.**

## Configuration

Keys in `/etc/retronet/retronet.conf` (mount your own copy) or as environment variables
`RETRONET_<KEY>`; the environment wins.

| Key | Default | Meaning |
| --- | --- | --- |
| `address` | (required) | The gateway's address and prefix on the retro segment, e.g. `10.0.99.1/24` |
| `year` | `1999` | The Wayback Machine year for the whole network (1997–2021) |
| `upstream_dns` | from `/etc/resolv.conf` | DNS servers to forward to. Set it under Docker: Docker's `127.0.0.11` cannot pass the egress filter. |
| `uplink_gateway` | | The uplink's default gateway, if the runtime did not set one. A default route through the retro side is always removed. |
| `retro_interface` | | Adds `address` to this interface if no interface has it yet (a container with `ip=manual`) |
| `dhcp_range`, `dhcp_lease`, `domain` | `.100`–`.199`, `12h`, `retro.lan` | DHCP pool, lease time, local domain |
| `archive_mode` | `online` | `online` (store, fetch misses) or `offline` (replay the store only) |
| `archive_upstream` | `https://web.archive.org` | Where misses are fetched; a VintageHive archive worker speaks the same protocol |
| `archive_min_interval` | `5` | Seconds between two upstream requests |
| `archive_max_mb` | `4096` | Store size; least recently used entries go first above it (0: no limit) |
| `protoweb` | `yes` | ProtoWeb ahead of the Wayback Machine |
| `admin_password`, `admin_password_file` | generated | VintageHive's admin password (at least 8 characters) |

Written into VintageHive on every start: its address, the admin password, the year, the archive
settings, the ports, and these services off: SOCKS, the HTTPS proxy, VintageHive's own DNS server,
the gopher relay, radio (MMS, PNA), mail (SMTP, POP3, IMAP), IRC, printing, NetMeeting and the
file-transfer relay. Written once, then up to the owner: the portal, FTP, telnet, OSCAR, MSNP, YMSG,
news and finger (on).

## On a Docker host

The container must be on the retro segment at layer 2, so the Docker host needs an interface on the
retro VLAN or VNet (a VLAN sub-interface of its NIC, for example), and the gateway uses macvlan (or
ipvlan in L2 mode) on it. A Docker bridge network is not enough: it only reaches other containers on
the same host. This also works with a remote Docker host (`DOCKER_HOST`), as long as that host has
the retro VLAN.

:::caution[Untested]
The compose file below has not been run. Only Docker bridge networks are tested (CI).
:::

```yaml
# retro VLAN 99 on the Docker host's eth0; the uplink is an ordinary bridge network with NAT
services:
  gateway:
    image: ghcr.io/hwinther/wsh-pve/retronet-gateway:latest
    cap_add: [NET_ADMIN]
    restart: unless-stopped
    environment:
      RETRONET_ADDRESS: 10.0.99.1/24
      RETRONET_UPSTREAM_DNS: 9.9.9.9 149.112.112.112
      RETRONET_ADMIN_PASSWORD_FILE: /run/secrets/retronet_admin_password
    secrets: [retronet_admin_password]
    networks:
      retro:
        ipv4_address: 10.0.99.1
      uplink: {}
    volumes:
      - state:/var/lib/retronet
networks:
  retro:
    driver: macvlan
    driver_opts:
      parent: eth0.99           # created by the macvlan driver if it does not exist
    ipam:
      config:
        - subnet: 10.0.99.0/24
          ip_range: 10.0.99.240/29   # Docker's own allocations, outside the DHCP pool
          gateway: 10.0.99.254       # required by Docker; nothing on the segment should use it
  uplink: {}
secrets:
  retronet_admin_password:
    file: ./admin-password
volumes:
  state:
```

Notes: with macvlan the Docker host itself cannot talk to the gateway's retro address (a macvlan
property), which is what you want here. If Docker makes the retro network the default route, the
gateway removes it at start; set `RETRONET_UPLINK_GATEWAY` if the uplink then has no default route.

## As a Proxmox VE container from the OCI image

:::caution[Untested]
Not run on a node. Written from the Proxmox VE 9.1/9.2 documentation, which calls application
containers from OCI images a technology preview and leaves several details open (noted below).
:::

Proxmox VE 9.1 and later can create a container from an OCI image: on a storage's container
template view, **Pull from OCI registry** with `ghcr.io/hwinther/wsh-pve/retronet-gateway:latest`
(the image is public once the workflow on `main` has pushed it), then create the container from that
template with the wizard or `pct create`. The documentation says the image is converted to Proxmox
VE's LXC layout; it does not say how layers, `ENTRYPOINT`, `ENV`, `VOLUME` or `HEALTHCHECK` map,
nor whether the pull can be done from the command line or with registry credentials.

What the image needs there, and how it is built for it:

- **PID 1:** the entry point is `tini`, which reaps orphans and forwards signals to
  `retronet-supervise`; there is no systemd. If the container's `entrypoint` option does not come
  from the image, set it to `/usr/bin/tini -g -- /usr/local/sbin/retronet-entrypoint` (the default
  is `/sbin/init`, which this image does not have).
- **Environment:** the container's `env` option (a NUL-separated list) can carry the `RETRONET_*`
  keys. Or mount a `retronet.conf` at `/etc/retronet/retronet.conf`.
- **Network:** two devices. `net0` on the retro bridge (e.g. `vmbr99`, no address on the node) with
  the static address `ip=10.0.99.1/24` and no gateway; `net1` on the LAN bridge with `ip=dhcp` or a
  static address and `gw=`. For application containers Proxmox VE enables `host-managed` network
  configuration, so the node sets the addresses; the image only reads them (or, with `ip=manual` on
  `net0`, adds `RETRONET_ADDRESS` to `retro_interface` itself) and runs no DHCP client of its own.
- **Capabilities:** an unprivileged container has `CAP_NET_ADMIN` inside its own network namespace,
  which is what nftables and dnsmasq need; the documentation states no capability defaults for
  application containers, so this is to be confirmed. `/dev/ppp` for the dial-up stage would need
  device passthrough.
- **State:** add a mount point at `/var/lib/retronet` (`mp0`). An upgrade means pulling the new
  image and creating a new container from it (no in-place update of an OCI-based container is
  described), with the same mount point and settings.

## Trial by hand on a node (stage 0)

:::caution[Untested]
These steps have not been run on a node.
:::

1. Create a bridge with no address and no ports, e.g. `vmbr99` in `/etc/network/interfaces`:
   `auto vmbr99` / `iface vmbr99 inet manual` / `bridge-ports none` / `bridge-stp off` /
   `bridge-fd 0`, then `ifreload -a`. Only VMs and the gateway attach to it.
2. Create the gateway with `net0` on `vmbr99` (10.0.99.1/24) and `net1` on the LAN bridge: either
   a container from the OCI image (above), or a small Debian VM dedicated to it that runs the image
   with host networking, so the VM's two NICs are the gateway's:
   `docker run -d --name retronet --network host --cap-add NET_ADMIN -e RETRONET_ADDRESS=10.0.99.1/24
   -e RETRONET_UPSTREAM_DNS=9.9.9.9 -e RETRONET_ADMIN_PASSWORD=... -v retronet:/var/lib/retronet
   ghcr.io/hwinther/wsh-pve/retronet-gateway:latest` (the gateway's filter then applies to the VM).
3. Attach one retro VM's NIC (ne2k_pci, pcnet, rtl8139, e1000) to `vmbr99`. A guest with a DHCP
   client gets an address in 10.0.99.100–199; a guest without one takes a fixed address in the
   subnet with 10.0.99.1 as router and DNS server.
4. In the guest, open `http://www.netscape.com/` (no proxy), or set the proxy to 10.0.99.1:1990 in a
   browser older than 1996. From the gateway, `curl -0 -x http://10.0.99.1:1990 http://www.netscape.com/`
   is the smoke test.
5. Check isolation from the guest: the node's and the LAN's addresses must not answer (ping,
   `telnet <node> 8006`).

## Security notes

- Guests never route through the gateway: every connection from the segment ends at the gateway
  (a redirected service, or a refusal). The nftables `forward` chain drops anything that would be
  forwarded in any case.
- The gateway's own traffic is filtered by owner: only dnsmasq may send DNS, and only to the
  configured upstream servers; only the archive cache may open ports 80 and 443, and it only ever
  connects to its one configured upstream (it never uses a host name from a guest's request);
  VintageHive may reach ProtoWeb's proxy (port 7851) and nothing else outside. Private, loopback, link-local, CGNAT, multicast and reserved
  addresses are refused for everyone, so a name that resolves into the LAN (DNS rebinding, a crafted
  host name) leads nowhere. dnsmasq also drops upstream answers that point into private space. IPv6
  is not forwarded upstream at all.
- Nothing listens on the uplink side.
- VintageHive's admin pages are reachable from guests (through the proxy, `http://localhost/`),
  protected by the admin password.
- VintageHive's FTP server lets any guest upload to its hosting area (`ftp.<name>` hosts, served
  again as `http://www.<name>/`): there is no FTP authentication upstream yet. Disk use is bounded
  only by the state volume.
- VintageHive is alpha software with one maintainer. The image builds a pinned commit and applies one
  patch (`retronet/gateway/patches/`).

## Licences

The image redistributes, in binary form:

- VintageHive (MIT, `LICENSE.VintageHive` in `/opt/vintagehive`), its NuGet dependencies (MIT,
  Apache-2.0, and the Six Labors Split License for ImageSharp, Fonts and Drawing), and the
  `geonames.db` it ships (GeoNames data, CC BY 4.0). Removed from the image: VintageHive's bundled
  ffmpeg, Ghostscript and Windows DLLs, and its bundled OpenSSL 1.0.2a.
- The .NET runtime (MIT), published self-contained with VintageHive.
- Debian 13 packages: dnsmasq (GPL-2.0/GPL-3.0), nftables (GPL-2.0), Python 3 (PSF-2.0), sqlite3
  (public domain), tini (MIT), iproute2 (GPL-2.0), with Debian's copyright files in
  `/usr/share/doc`.
- The gateway's own scripts (GPL-3.0, like the rest of this repository).

Pages fetched from the Wayback Machine and ProtoWeb are not part of the image or the repository;
they are fetched for the guest and cached in the state directory (see "Archive cache").
