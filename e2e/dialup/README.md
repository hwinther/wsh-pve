# Dial-up test

An end-to-end test of emulated modem dial-up from a QEMU guest's serial port: the guest's 16550 on
a UNIX socket (what `serial0: socket` gives a Proxmox VE VM), [atduck](https://github.com/nandhp/atduck)
as the Hayes modem, and an "ISP side" on a pty: slirp (user-mode, no login) or a real `pppd` server
(PAP, MS-CHAPv2, MPPE). The guide for a real node is `docs/src/content/docs/guides/dialup.md`.

```sh
docker build -t dialup-test e2e/dialup
docker run --rm --init --device /dev/kvm --device /dev/ppp --cap-add NET_ADMIN \
  -v "$PWD/results:/results" dialup-test
```

`/dev/kvm` is optional (TCG otherwise). `/dev/ppp` and `NET_ADMIN` are needed only by the `pppd`
scenario, which is skipped without them. Exit code 0 when every scenario ends as expected:

| Scenario | What | Expected |
| --- | --- | --- |
| `stock` | Debian's unpatched `/usr/bin/slirp` on 5555 | fails the way the bug does: slirp exits, the modem echoes the guest's PPP frames (`Serial line is looped back`) |
| `slirp` | patched slirp on 5555 | the guest gets an address and fetches a URL |
| `pppd` | `pppd` server with PAP login on 5557, NAT | the same, and `PAP peer authentication succeeded` |
| `redial` | hang up with `+++`, `ATH0`, dial again | the second call works |

`SCENARIOS="slirp redial"` selects some. Logs per scenario land in `/results`.

- `patches/slirp-64bit-select-timeout.patch`: the fix. `main_loop()` stores its "block forever" value
  of -1 through a `(u_int)` cast; where `tv_usec` is 64 bits wide it becomes 4294967295, `select()`
  fails with `EINVAL` and slirp exits right after its first LCP packet. `slirp-fullbolt` from the
  same package is built without that code and works.
- `patches/slirp-ppp-fakeip.patch`: from atduck, for hosts whose name resolves to a loopback address.
- `files/`: the restricted dial plan, the `pppd` wrapper and peers file, a systemd unit per VM and a
  hookscript. The unit and the hookscript have not run on a Proxmox VE node.
- `scripts/`: the tiny guest (Debian kernel, busybox, pppd as an initramfs), the test entrypoint and
  the measuring helpers.

This is not part of any workflow yet.
