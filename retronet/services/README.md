# Gateway services

Each directory here is one service of the gateway image, copied to `/etc/retronet/services.d/<name>/`.
`retronet-init` and `retronet-supervise` read these files; nothing else needs to change to add a
service (a Battle.net-compatible server or a period IRC network later, for example).

| File | Used by | Meaning |
| --- | --- | --- |
| `run` | supervisor | Starts the service in the foreground (`exec`), dropping root itself. Restarted when it exits. |
| `init` | `retronet-init` | Optional. Runs as root before any service starts, after the filter is loaded. Gets `RETRONET_GW`, `RETRONET_STATE`, `RETRONET_CFG_YEAR` and friends. |
| `redirects` | `retronet-init` | `<tcp\|udp> <guest port\|-> <gateway port or range>` per line. A guest connection to the guest port on any address is redirected to the gateway port; `-` only opens the gateway port to guests. |
| `dns-names` | dnsmasq | Names (and their subdomains) answered with the gateway's address. |

The services so far:

- `dns`: dnsmasq, DHCP and DNS on the retro segment.
- `archive-cache`: the archive cache (`archive_cache.py`, Python standard library only). VintageHive
  sends every Wayback lookup and fetch to it; it answers from its store under
  `/var/lib/retronet/archive-cache` and, online, fetches misses from web.archive.org. It is the only
  process the egress filter lets reach ports 80 and 443. `default-urls.txt` is the warm-up list
  (`make-default-urls.py` writes it from a VintageHive checkout).
- `vintagehive`: [VintageHive](https://github.com/FoxCouncil/VintageHive) (MIT), the archive proxy
  for the web of 1999, the portal, instant messaging (OSCAR, MSNP, YMSG), FTP, the telnet BBS, news
  and finger. Built from a pinned commit in `../gateway/Dockerfile`.

A service that needs the internet needs its own rule in the `output` chain written by
`retronet-init`; keep that the exception.
