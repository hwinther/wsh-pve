# wsh-qemu-rdp

The optional `wsh-qemu-rdp` package: [qemu-rdp](https://gitlab.com/marcandre.lureau/qemu-display)
(Marc-André Lureau's qemu-display project, MIT), an RDP server for QEMU's D-Bus display, and the
unit `wsh-qemu-rdp@<vmid>.service` that serves one PVE VM's display with it: screen, keyboard,
mouse and sound (rdpsnd) to any RDP client. How to use it on a node is in the docs,
[Display reference, "RDP (qemu-rdp)"](../../docs/src/content/docs/reference/display.md#rdp-qemu-rdp).

| File | What it is |
| --- | --- |
| `upstream.env` | The pinned qemu-display commit, its date and qemu-rdp's version there |
| `version.sh` | The package version from git: `<qemu-rdp version>+git<date>.<sha7>.wsh<N>` |
| `build.Dockerfile`, `build.sh` | The build in Debian 13 (`make wsh-qemu-rdp`): fetch, patch, `cargo vendor`, offline build, lintian |
| `patches/` | Our changes to qemu-display, each saying what and why |
| `debian/` | The packaging; the unit is `debian/wsh-qemu-rdp@.service` |
| `wsh-qemu-rdp-unit` | The unit's helper (`prepare`: config, certificate, credentials; `run`: qemu-rdp) |
| `test.sh`, `tests/rdp_test.py` | The end-to-end test: x86 and SS-5 wisp guests through FreeRDP (CI: `wsh-qemu-rdp.yml`) |

## Pin and bump

The pin is qemu-display `8ac3da9` (2026-06-04), the last commit whose qemu-rdp takes every crate
from crates.io (ironrdp 0.15). Later commits take IronRDP and `usbredir-proto` from git
repositories, for USB redirection; the build vendors crates.io only, so a bump past that point waits
until those crates are published, or needs a patch that drops the USB redirection.

To bump: edit `upstream.env` (commit, committer date, qemu-rdp's version), check that the patches
still apply, and run `make wsh-qemu-rdp` and `test.sh`. `build.sh` stops if the pinned qemu-rdp
version doesn't match, if the lock file takes a crate from anywhere but crates.io, or if cutting the
workspace down (patch 0001) changed any locked version instead of only dropping packages.

The toolchain is Debian 13's `rustc-web`/`cargo-web` (ironrdp 0.15 needs rustc 1.89; Debian 13's
`rustc` is 1.85). The crates are fetched at build time, not stored in this repository; the package's
`/usr/share/doc/wsh-qemu-rdp/vendored-crates.txt` lists each crate, its version and its license.

## Build and test

```sh
make wsh-qemu-rdp                        # build/wsh-qemu-rdp/wsh-qemu-rdp_<version>_amd64.deb
# the guests: kernel-fb-x86_64 and kernel-fb-sparc32 of the wisp-fb release (SHA256SUMS there)
docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-qemu-rdp:/deb:ro" -v "$KERNELS:/kernels:ro" \
  -v "$OUT:/out" debian:trixie sh /src/packages/wsh-qemu-rdp/test.sh \
  /deb/wsh-qemu-rdp_<version>_amd64.deb /out
```
