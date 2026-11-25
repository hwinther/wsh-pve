# wsh-gst-qemu-dbus

The optional `wsh-gst-qemu-dbus` package: GStreamer sources and an input bridge for QEMU's D-Bus
display, the pieces a streaming server on a PVE node (stage 3 of the 3dfx/streaming plan in
`ROADMAP.md`) is built from. How to use them on a node is in the docs,
[Display reference, "Streaming sources (GStreamer)"](../../docs/src/content/docs/reference/display.md#streaming-sources-gstreamer).

- **`qemudbussrc`**: the picture of a console as live raw video. It registers a listener on
  `Console_<n>` of the VM's bus and copies what QEMU sends: the pixels (`Scanout`/`Update`), the
  console's surface in shared memory (`ScanoutMap`/`UpdateMap`, offered unless `shared-map=false`),
  or a linear dmabuf (`ScanoutDMABUF`/`UpdateDMABUF`, `-display dbus,gl=on`), read before each
  `UpdateDMABUF` is answered, so the guest's GL frames wait for a copy, not for the pipeline.
- **`qemudbusaudiosrc`**: the guest's playback (`-audiodev dbus`) as live PCM, scaled by the guest
  mixer's volume (`apply-volume`).
- **`qemu-dbus-input`**: keyboard, buttons, relative and absolute motion from text commands on
  standard input to the console's `Keyboard` and `Mouse` interfaces, as relative or absolute motion
  as the guest's pointer takes it (`IsAbsolute`). The protocol is in `debian/qemu-dbus-input.1`.

The code is ours (C, GLib/GIO and GStreamer 1.26 from Debian 13, built with meson). It doesn't use
qemu-display's Rust crates: GStreamer elements and QEMU's D-Bus display are both GLib, so GIO's
D-Bus covers the listener protocol in a few hundred lines, with no crates to vendor.

| File | What it is |
| --- | --- |
| `src/qemudbus.c` | The connection: the bus, `org.qemu`, a listener on a peer-to-peer connection, its own thread |
| `src/gstqemudbussrc.c` | `qemudbussrc` |
| `src/gstqemudbusaudiosrc.c` | `qemudbusaudiosrc` |
| `src/qemu-dbus-input.c` | `qemu-dbus-input` |
| `version.sh` | The package version from git: `0.<N>+g<sha7>` |
| `build.Dockerfile`, `build.sh` | The build in Debian 13 (`make wsh-gst-qemu-dbus`): meson, dpkg-buildpackage, lintian |
| `debian/` | The packaging and the bridge's man page |
| `test.sh`, `tests/stream_test.py` | The end-to-end test: wisp guests through the pipelines and the bridge (CI: `wsh-gst-qemu-dbus.yml`) |
| `tests/gst-listener.py` | `qemudbussrc` in place of `e2e/3dfx/dbus-listener.py` (`DBUS_LISTENER=` in `e2e/3dfx/test.sh`) |

## Build and test

```sh
make wsh-gst-qemu-dbus                   # build/wsh-gst-qemu-dbus/wsh-gst-qemu-dbus_<version>_amd64.deb
# the guests: kernel-fb-x86_64, -aarch64 and -sparc32 of the wisp-fb release (SHA256SUMS there)
docker run --rm --device /dev/udmabuf -v "$PWD:/src:ro" -v "$PWD/build/wsh-gst-qemu-dbus:/deb:ro" \
  -v "$KERNELS:/kernels:ro" -v "$OUT:/out" debian:trixie sh /src/packages/wsh-gst-qemu-dbus/test.sh \
  /deb/wsh-gst-qemu-dbus_<version>_amd64.deb /out
```

`test.sh` runs QEMU (the published pve-qemu-kvm) as qemu-server does, on a bus with qemu-server's
policy, and the clients as an unprivileged member of `wsh-display`. Runs (`RUNS`): `x86_64` (std
VGA, PS/2 mouse, AC97: the shared map), `aarch64` (virt, bochs-display, virtio tablet, AC97,
`shared-map=false`: pixels in the messages), `x86_64-gl` (the 3dfx binary with `dbus,gl=on`,
llvmpipe through `/dev/udmabuf`: dmabufs; skipped without `/dev/udmabuf`) and `sparc32` (SS-5, cg3,
CS4231, Sun mouse).
Each checks the newest frame against QEMU's screendump pixel for pixel, `keytest` and `mousetest`
in the guest through the bridge, a 440 Hz tone from `soundtest` in the WAV the audio pipeline
wrote, and that the video pipeline ends by itself when QEMU quits.

With real GL frames (the 3dfx Glide and Mesa guests), with the package and `python3-gi`,
`gir1.2-gstreamer-1.0` and `gir1.2-gst-plugins-base-1.0` installed in the container first:

```sh
GLIDE_DISPLAY=dbus DBUS_LISTENER=/src/packages/wsh-gst-qemu-dbus/tests/gst-listener.py \
  sh /src/e2e/3dfx/test.sh - /out
```

## Not there yet

- Dmabufs as dmabufs: frames are copied to system memory. A dmabuf output (`memory:DMABuf`) for a
  hardware encoder, held until the encoder is done with it, is the next step.
- A dmabuf that isn't linear (a GPU's tiled layout, NVIDIA's block-linear) can't be mapped: the
  element warns once and drops those frames (an EGL import would read them).
- The cursor: `CursorDefine`/`MouseSet` are answered but the cursor isn't drawn into the picture.
- `ScanoutDMABUF2` (multi-plane, sub-rectangles) isn't offered, so QEMU uses `ScanoutDMABUF`.
- QEMU's peer-to-peer mode (`-display dbus,p2p=yes` with QMP `add_client`): only a bus address.
