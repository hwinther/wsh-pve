# wsh-gst-qemu-dbus

The optional `wsh-gst-qemu-dbus` package: GStreamer sources and an input bridge for QEMU's D-Bus
display, the pieces a streaming server on a PVE node (stage 3 of the 3dfx/streaming plan in
`ROADMAP.md`) is built from. How to use them on a node is in the docs,
[Display reference, "Streaming sources (GStreamer)"](../../docs/src/content/docs/reference/display.md#streaming-sources-gstreamer).

- **`qemudbussrc`**: the picture of a console as live raw video. It registers a listener on
  `Console_<n>` of the VM's bus and copies what QEMU sends: the pixels (`Scanout`/`Update`), the
  console's surface in shared memory (`ScanoutMap`/`UpdateMap`, offered unless `shared-map=false`),
  or a dmabuf (`ScanoutDMABUF`/`UpdateDMABUF`, `-display dbus,gl=on`), read before each
  `UpdateDMABUF` is answered, so the guest's GL frames wait for a copy, not for the pipeline. A
  linear dmabuf (Mesa's llvmpipe through `/dev/udmabuf`) is mapped; any other layout (a GPU's tiled
  one, NVIDIA's block-linear) is imported through EGL (`src/qemudbusgl.c`: an EGLImage on the GPU's
  EGL device, drawn into a framebuffer as `BGRx` and read back with `glReadPixels`; the rows are
  read again 20 ms later, since NVIDIA's driver doesn't make the read wait for QEMU's drawing).
  `dmabuf-import=mmap` keeps to linear ones, `dmabuf-import=egl` reads all through EGL (the tests),
  `render-node=` picks the GPU. When the VM stops it sends EOS, or with `reconnect=true` keeps the
  last picture and listens to the VM's next run (also starting before the VM runs).
- **`qemudbusaudiosrc`**: the guest's playback (`-audiodev dbus`) as live PCM, scaled by the guest
  mixer's volume (`apply-volume`), with silence in real time while the guest plays nothing
  (`silence`), so the stream has no gaps and its timestamps never go back; `reconnect=true` as for
  `qemudbussrc`.
- **`qemu-dbus-input`**: keyboard, buttons, relative and absolute motion from text commands on
  standard input to the console's `Keyboard` and `Mouse` interfaces, as relative or absolute motion
  as the guest's pointer takes it (`IsAbsolute`); it prints `closed` and exits 3 when QEMU leaves
  the bus. The protocol is in `debian/qemu-dbus-input.1`.

The code is ours (C, GLib/GIO and GStreamer 1.26 from Debian 13, built with meson). It doesn't use
qemu-display's Rust crates: GStreamer elements and QEMU's D-Bus display are both GLib, so GIO's
D-Bus covers the listener protocol in a few hundred lines, with no crates to vendor.

| File | What it is |
| --- | --- |
| `src/qemudbus.c` | The connection: the bus, `org.qemu`, a listener on a peer-to-peer connection, its own thread |
| `src/gstqemudbussrc.c` | `qemudbussrc` |
| `src/qemudbusgl.c` | The EGL import of dmabufs that can't be mapped |
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
llvmpipe through `/dev/udmabuf`: dmabufs; skipped without `/dev/udmabuf`), `x86_64-egl` (the same
with `dmabuf-import=egl`: the dmabufs through EGL, on Mesa's software device) and `sparc32` (SS-5,
cg3, CS4231, Sun mouse).
Each checks the newest frame against QEMU's screendump pixel for pixel, `keytest` and `mousetest`
in the guest through the bridge, a 440 Hz tone from `soundtest` without a dropout in the WAV the
audio pipeline wrote, and that the video pipeline ends by itself when QEMU quits.
After the runs, the clients as the root of an unprivileged container (a user namespace whose root
is the host's uid 100000; `docker run --security-opt seccomp=unconfined`, else skipped) on a bus
set up as qemu-server does for `dbus-display-uids: 100000`, and the ones that must stay out (uid
200000, uid 100000 on a VM's bus that doesn't name it, a node user outside `wsh-display`).

The clients authenticate with `G_DBUS_CONNECTION_FLAGS_CROSS_NAMESPACE`: `AUTH EXTERNAL` without a
uid, so the bus (and QEMU, on the listener's connection) takes the uid the kernel reports for the
socket. In a user namespace the uid the client sees isn't that one, and the bus would refuse it.

With real GL frames (the 3dfx Glide and Mesa guests), with the package and `python3-gi`,
`gir1.2-gstreamer-1.0` and `gir1.2-gst-plugins-base-1.0` installed in the container first:

```sh
GLIDE_DISPLAY=dbus DBUS_LISTENER=/src/packages/wsh-gst-qemu-dbus/tests/gst-listener.py \
  sh /src/e2e/3dfx/test.sh - /out
```

## Not there yet

- Dmabufs as dmabufs: frames are copied to system memory. A dmabuf output (`memory:DMABuf`) for a
  hardware encoder, held until the encoder is done with it, is the next step.
- The EGL import still copies: the frame goes from the GPU to system memory (`glReadPixels`), as
  the linear path's copy does.
- The cursor: `CursorDefine`/`MouseSet` are answered but the cursor isn't drawn into the picture.
- `ScanoutDMABUF2` (multi-plane, sub-rectangles) isn't offered, so QEMU uses `ScanoutDMABUF`.
- QEMU's peer-to-peer mode (`-display dbus,p2p=yes` with QMP `add_client`): only a bus address.
