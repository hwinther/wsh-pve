# Retro net gateway

One container image that is the gateway of an isolated "retro" network: DHCP and DNS for the guests,
the web of 1999 (Wayback Machine, ProtoWeb) through [VintageHive](https://github.com/FoxCouncil/VintageHive),
period services (instant messaging, FTP, a telnet BBS, news), and an egress filter so the guests
reach neither the node nor the LAN. The design is in `../RETRONET.md`; the user guide is
`docs/src/content/docs/guides/retronet.md`.

| Path | What |
| --- | --- |
| `gateway/Dockerfile` | The image: Debian 13, dnsmasq, nftables, tinyproxy, VintageHive (pinned commit, one patch in `gateway/patches/`), tini |
| `gateway/rootfs/` | `retronet-init` (configuration, filter, generated configs), `retronet-supervise`, `retronet-health`, `retronet-user`, the default `retronet.conf` |
| `services/` | One directory per service: run script, redirects, DNS names, egress allowlist (see `services/README.md`) |
| `compose.yml` | The gateway between a retro network and an uplink, for a trial by hand |
| `compose.online.yml` | Adds the real internet to the trial |
| `compose.test.yml`, `test/`, `test.sh` | The hermetic test |

## Test

```sh
retronet/test.sh          # exit code 0 when every check passes; KEEP=1 keeps the stack running
```

No internet is needed after the images are built: a fake Wayback Machine (`test/fakenet.py`) and DNS
server stand in for archive.org on a fake internet (192.88.99.0/24), a canary (`test/canary.py`)
stands for the LAN, and a client on the retro network takes a DHCP lease and runs
`test/client-tests.sh` (web, transparent and through the proxy; instant messaging with
`test/oscar_client.py`; isolation). The workflow `.github/workflows/retronet.yml` runs it on pull
requests that touch `retronet/`.

With a remote Docker host, everything stays inside the compose networks; nothing is published.

## Trial by hand

```sh
RETRONET_ADMIN_PASSWORD=change-me-please docker compose -f retronet/compose.yml -f retronet/compose.online.yml up -d --build
docker compose -f retronet/compose.yml -f retronet/compose.online.yml run --rm guest
#   (in the guest) curl -0 http://www.netscape.com/ | head
```
