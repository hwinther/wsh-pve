---
title: Display Reference
description: A reference page for the display hardware panel.
---

QEMU provides various display devices and options to emulate graphical output in virtual machines. This section outlines the available display devices and configuration options for managing graphical output in QEMU, ensuring compatibility with a wide range of guest operating systems and use cases.
The PVE WSH patches add graphic cards to the UI and adds support for X forwarding via GTK or GL, and an experimental 3DFX/Mesa passthrough option.

## Graphic card options

- tcx: TCX framebuffer (sparc only)
- cg3: CG3 framebuffer (sparc only), this is the preferred graphics card for sparc
- cirrus: Cirrus VGA - for MSDOS or other very old operating systems that can use a VESA1.2 compatible driver (but are too old to use generic SVGA/VESA2 - TODO: verify and add citation for the last part)

![Graphics card selection](../../../assets/displaycard.png)

## Server

Unset by default, if it is set to an X display value such as :0 (or 192.168.0.100:0) it will force GTK or SDL output depending on the other options that are set.

![Display menu](../../../assets/display.png)

## Enable 3DFX/Mesa

Experimental feature - it must be used in conjunction with the 3DFX/MESA drivers in Windows 9x/2000/ME.

Without a server, the Glide and OpenGL frames show in the VM's console (noVNC), rendered offscreen on the node; with a server they show in an SDL window on that X display.

See the [3DFX / Mesa passthrough guide](/guides/3dfx/) for how the host QEMU build and the guest drivers are paired by revision, and where to download the matching driver release.

## 3DFX/Mesa display

`mesa-display` picks the QEMU display a VM with 3DFX/Mesa enabled gets next to its VNC console:

- `none` (the default, **Default (read back)**): no `-display`; the Glide and OpenGL frames are read back into the console.
- `egl-headless` (**egl-headless (dmabuf)**): `-display egl-headless`, a display with GL that takes the Glide and OpenGL frames as a dmabuf and reads them into the console for VNC. It needs a GPU's render node or `/dev/udmabuf` on the node, and is slower than the default with Mesa's software renderer.

```sh
qm set 120 --vga std,mesa=1,mesa-display=egl-headless
```

In the web UI it is **Hardware > Display > 3DFX/Mesa display**, shown for x86 VMs while **Enable 3DFX/Mesa** is checked and the graphic card has a VNC console. Refused without `mesa=1`, with a `server` and with `none` or `serial*`; refused at start on a node with neither a render node nor `/dev/udmabuf`. When to use which and what the node needs: [Choosing the display](/guides/3dfx/#choosing-the-display-3dfxmesa-display).

## D-Bus display

`display=dbus` gives QEMU its D-Bus display (`-display dbus`) next to the VNC console: QEMU exports
the screen, the sound (with the audio driver `dbus`) and keyboard and mouse input over D-Bus, for a
client on the same node, such as a streaming server. The VNC console (noVNC) stays as it is.

```sh
qm set 130 --vga std,display=dbus
qm set 130 --vga std,display=dbus,dbus-refresh=14 --audio0 device=AC97,driver=dbus
qm set 120 --vga std,mesa=1,mesa-display=dbus   # 3DFX/Mesa: the D-Bus display with OpenGL
```

- **Its own bus.** QEMU owns the fixed name `org.qemu` on its bus, so each VM gets a bus of its own:
  qemu-server starts `wsh-dbus-display@<vmid>.service`, a `dbus-daemon`, before QEMU, and QEMU
  connects to `unix:path=/run/wsh-dbus-display/<vmid>.sock`
  (`-display dbus,addr=unix:path=...`). The stop (or the cleanup after QEMU exits) stops it and
  removes the socket. The directory is `root:wsh-display 0750` (the socket in it is `0777`, as
  dbus-daemon makes it), so only root and the group reach the socket; the bus's policy
  (`/usr/share/qemu-server/dbus-display.conf`) lets root own `org.qemu` and lets root and the
  members of the group `wsh-display` (created by the qemu-server package) connect and call it.
  Nobody else may connect, except the uids in `dbus-display-uids`. A client in a privileged
  container gets the directory bind-mounted; one in an unprivileged container also needs its uid
  in `dbus-display-uids` (see [On a node](#on-a-node)).
- **`dbus-display-uids`** (a VM option, `uid[;uid...]`, only root may set it): host uids that may
  use this VM's bus besides root and `wsh-display`, such as the root of an unprivileged container
  that streams the VM (`100000` with PVE's default mapping). At the VM's start qemu-server writes
  the VM's bus configuration (`/run/qemu-server/<vmid>.dbus-display.conf`: the shared policy plus
  each uid, which may connect and call `org.qemu` but not own a name), gives each uid a user on the
  node if it has none (`wsh-display-<uid>`, no home, no login shell: dbus-daemon refuses a uid it
  can't look up, whatever the policy says) and an ACL entry `--x` on `/run/wsh-dbus-display`, which
  goes when no running VM names the uid any more. Other VMs' buses still refuse the uid.
- **Without GL** (`display=dbus`) it works with every graphic card that has a picture: `std`,
  `cirrus`, `vmware`, `virtio`, and on sparc `tcx` and `cg3` (SS-5 and the other sparc32 machines)
  and sun4u's `std`. The client gets the console's pixels (`Scanout`/`Update`, or a shared memory
  map).
- **With GL** (`mesa-display=dbus`, the 3dfx binary): `-display dbus,gl=on`; the Glide and OpenGL
  frames reach the client as dmabufs, and the VNC console gets them read back (once per display
  refresh, by QEMU's own patch, as egl-headless does). It needs what egl-headless needs: a GPU's
  render node or `/dev/udmabuf`; see [Choosing the display](/guides/3dfx/#choosing-the-display-3dfxmesa-display).
- **`dbus-refresh`** (milliseconds, 1 to 1000): how often QEMU looks at the screen for changes and
  updates the client while one listens. QEMU's default is 30 ms, about 33 updates a second; 14
  suits a 70 Hz guest mode. A VGA's changes reach the client at most that often.
- **Sound**: `audio0: ...,driver=dbus` adds `-audiodev dbus` and ties it to the display
  (`audiodev=`); the client registers an `AudioOutListener` and gets the PCM.
- **The client goes or the bus goes**: QEMU keeps running when the client disconnects or is
  killed, and also when the `dbus-daemon` dies; the D-Bus display is then gone until the VM is
  restarted, while VNC goes on.

In the web UI it is **Hardware > Display > D-Bus display** and **D-Bus refresh (ms)**, and the audio
device's **Backend Driver > D-Bus** (`dbus-display-uids` only on the command line and in the API).
Refused: `dbus-refresh`, the audio driver `dbus` or `dbus-display-uids` without the D-Bus display; the D-Bus display with a `server` (SDL), with `qxl*`, `virtio-gl`, `none` or
`serial*`, and together with `mesa-display=egl-headless` (QEMU has one display next to VNC).

To look at a running VM's bus as root:

```sh
busctl --address=unix:path=/run/wsh-dbus-display/130.sock tree org.qemu
```

## RDP (qemu-rdp)

The optional package `wsh-qemu-rdp` serves a VM's D-Bus display over RDP, with sound: any RDP
client (FreeRDP, Remmina, Windows' Remote Desktop Connection) gets the screen, keyboard, mouse and
the guest's audio through rdpsnd. It is [qemu-rdp](https://gitlab.com/marcandre.lureau/qemu-display)
from Marc-André Lureau's qemu-display project (IronRDP; RemoteFX and bitmap codecs, no H.264), at a
pinned commit with a few changes of ours (`packages/wsh-qemu-rdp` in wsh-pve). It is a stopgap
until the Moonlight streaming path; it needs no GPU.

```sh
apt install wsh-qemu-rdp
qm set 130 --vga std,display=dbus --audio0 device=AC97,driver=dbus   # sparc32 SS-5: cg3 and cs4231
systemctl enable --now wsh-qemu-rdp@130
cat /etc/wsh-qemu-rdp/130.conf                                        # address, port, user, password
```

- **One unit per VM.** `wsh-qemu-rdp@<vmid>.service` runs qemu-rdp on the VM's bus
  (`/run/wsh-dbus-display/<vmid>.sock`) as the user `wsh-qemu-rdp`, a member of `wsh-display`
  (the package creates both), with systemd's sandboxing. It is bound to the bus's unit
  `wsh-dbus-display@<vmid>`: enabled, it starts whenever qemu-server starts the bus (`qm start`) and
  stops with it (`qm stop`, and the cleanup after QEMU exits). `systemctl enable --now` starts it at
  once if the VM runs. The enablement is per node: after a migration, enable it on the new node.
  qemu-server isn't changed for it: the VM's `vga` needs only `display=dbus` (or `mesa-display=dbus`).
- **Configuration**: `/etc/wsh-qemu-rdp/<vmid>.conf` (root, `0600`), written at the first start and
  read at each start (`systemctl restart wsh-qemu-rdp@<vmid>` after a change):
  - `LISTEN` (default `127.0.0.1`) and `PORT` (default 20000 + VMID; set it for a VMID of 40000 or
    more). By default only the node itself can connect: use an SSH tunnel
    (`ssh -L 20130:127.0.0.1:20130 root@node`, then connect to `localhost:20130`), or set
    `LISTEN=0.0.0.0` to open it to the node's networks.
  - `RDP_USER` (`rdp`) and `RDP_PASSWORD` (24 random letters and digits, generated): the login.
  - `CERT` and `KEY`: a TLS certificate and key (PEM) of your own. Without them the node gets a
    self-signed certificate (RSA 3072, ten years, the node's host name) in `/var/lib/wsh-qemu-rdp`
    at the first start; its SHA-256 fingerprint is in the unit's journal, to compare with what the
    client shows the first time.
  - `LOG`: qemu-rdp's log level (`error`, `warn` by default, `info`, `debug`, `trace`), in the journal.
- **Authentication and encryption**: qemu-rdp offers only NLA (CredSSP, with NTLM, over TLS); the
  client must send the configured user name and password before it gets a picture, and a client
  without NLA (plain RDP or TLS-only security) is refused. One user name and password per VM; the
  domain is ignored. Without a password qemu-rdp would refuse every client, so the unit won't start
  without one. qemu-rdp has no other access control (no per-user accounts, no client certificates),
  hence the default of listening on the node only.
- **Sound**: with `audio0: ...,driver=dbus` the guest's playback goes to the client through rdpsnd,
  as Opus where the client offers it (FreeRDP does) or PCM, at 48 kHz: qemu-server gives the
  audio driver `dbus` `out.frequency=48000` and QEMU resamples the guest's rate to it (qemu-rdp
  passes QEMU's samples on unconverted and has only 48 kHz formats; at QEMU's default 44.1 kHz it
  dropped every buffer). Tested with AC97 on x86 and the SS-5's CS4231. No recording (the guest's
  microphone).
- **Mouse**: with an absolute pointer in the guest (PVE's default USB tablet, `tablet: 1`, or
  virtio's) the client's pointer positions are passed as they are. With only a relative mouse (a
  PS/2 mouse with `tablet: 0`, Windows 9x and DOS VMs, the SPARCstation's Sun mouse), the change
  from the last position is passed (our patch; upstream passed nothing then), and the guest's own
  pointer acceleration applies, so its pointer drifts from the client's as with VNC's relative mode.
  The buttons and the wheel work either way.
- **Resize**: when the guest changes its mode, the client's window follows (firmware text mode to
  the kernel's framebuffer, for instance). A client that asks for a size of its own (FreeRDP's
  `/dynamic-resolution`) passes it to QEMU as the display's size hint, which only a guest driver
  that reads it acts on (virtio-gpu's; not tested).
- **Speed**: in the tests (TCG, no GPU, client on the same node), a key typed in FreeRDP reached
  the guest's serial line in 15-17 ms, and a full-screen picture change reached the client's window
  within about 0.2 s; RemoteFX at that screen came through pixel for pixel.
- **Not there**: H.264/AVC (RemoteFX and bitmaps only, so a full-screen game moves a lot of data;
  fine on a LAN, heavy over the Internet), USB redirection (in newer qemu-rdp, from crates not on
  crates.io yet), audio recording, multiple monitors, the clipboard: the VM's bus lets QEMU answer
  calls but not call qemu-rdp's clipboard object (the policy allows method calls to `org.qemu`
  only), and QEMU would need a clipboard agent in the VM too.

To test a VM's server from the node itself (FreeRDP 3 from Debian, `freerdp3-x11`):

```sh
xfreerdp3 /v:127.0.0.1:20130 /u:rdp /p:"$(sed -n 's/^RDP_PASSWORD=//p' /etc/wsh-qemu-rdp/130.conf)" \
  /cert:tofu /sound
```

## Streaming sources (GStreamer)

The optional package `wsh-gst-qemu-dbus` has the pieces a streaming server on the node takes a VM's
D-Bus display from: two GStreamer sources and an input bridge (`packages/wsh-gst-qemu-dbus` in
wsh-pve). They are the first part of the Moonlight streaming path (stage 3 in the ROADMAP); the
server built on them, Wolf, is in [Streaming to Moonlight](#streaming-to-moonlight). They need no
GPU.

```sh
apt install wsh-gst-qemu-dbus gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
qm set 130 --vga std,display=dbus --audio0 device=AC97,driver=dbus
gst-launch-1.0 qemudbussrc vmid=130 ! videoconvert ! autovideosink        # the picture
gst-launch-1.0 qemudbusaudiosrc vmid=130 ! audioconvert ! autoaudiosink   # the sound
qemu-dbus-input --vmid 130                                                 # input, one command per line
```

- **Who may**: root, a member of `wsh-display`, or a uid in the VM's `dbus-display-uids` (the bus's
  policy, see [D-Bus display](#d-bus-display)). The clients authenticate without naming a uid
  (GLib's `CROSS_NAMESPACE`), so they also work from a user namespace (an unprivileged container),
  where the uid they see isn't the one the bus sees.
  `vmid=` is short for `address=unix:path=/run/wsh-dbus-display/<vmid>.sock`; `console=` picks
  another console than 0. Each element registers its own listener, so they run next to each other,
  next to qemu-rdp and next to VNC.
- **`qemudbussrc`** gives raw video in the console's own format (`BGRx` for the usual 32-bit
  consoles, at the guest's resolution; a mode change renegotiates), one buffer per change of the
  picture, timestamped when it was taken (a live source with a variable frame rate: put `videorate`
  after it for a fixed one). Without GL it takes the console's surface through a shared memory map
  (or, with `shared-map=false`, the pixels in each update). With GL (`mesa-display=dbus`) QEMU hands
  it each frame as a dmabuf; it copies the changed part out and answers at once, since QEMU holds
  the guest's GL frames until the client answers (0.07-0.4 ms on average in the tests, single frames
  up to 14 ms on a busy host). A linear dmabuf (Mesa's software renderer through `/dev/udmabuf`) is
  mapped; a GPU's tiled one (NVIDIA's block-linear) is imported through EGL on the GPU's render
  node, drawn into a framebuffer and read back (`glReadPixels`, 0.7 ms on average for 1280x800 on a
  GTX 1080), and the rows are read once more 20 ms later, since NVIDIA's driver doesn't make the
  read wait for QEMU's drawing (without that the last frame missed rows now and then). The
  property `dmabuf-import` is `auto` (that), `mmap` (linear only, other frames dropped) or `egl`
  (all through EGL); `render-node=` picks the GPU when there are several. The element needs the
  GPU's EGL library where it runs (NVIDIA's, in a container: see [On a node](#on-a-node)). The
  mouse cursor isn't drawn into the picture. When the VM stops it ends the stream (EOS).
- **`qemudbusaudiosrc`** gives the guest's playback as raw PCM as QEMU sends it (48 kHz signed
  16-bit stereo with qemu-server's audio driver `dbus`), in 10 ms buffers. QEMU passes the guest
  mixer's volume and mute separately; the element applies them (`apply-volume=false` passes the
  samples as they are). QEMU sends nothing while the guest plays nothing; the element fills that
  with silence in real time (`silence=false` doesn't), so the stream has no gaps and its timestamps
  run on without jumping back: a gap made Wolf's `audiorate` push the whole pause as silence at
  once when the sound came, and the leaky queue before it dropped the sound's start meanwhile.
- **`qemu-dbus-input`** reads lines like `key 30 1` (Linux key code, press) and `key 30 0`
  (release), `btn left 1`, `wheel -1`, `rel 10 5` and `abs 640 400` (or `abs X Y W H`, scaled from a
  W x H client window), and sends them to the console's keyboard and mouse. QEMU takes absolute
  positions only from an absolute pointer in the guest (PVE's USB tablet, `tablet: 1`, or virtio's)
  and relative motion only from a relative one (PS/2 with `tablet: 0`, the Sun mouse); the bridge
  converts either to what the guest has, and says `mode absolute` or `mode relative`. `query` gives
  the mode and the console's size, `sync` waits for QEMU's answers. Keys still down when its input
  ends are released. `man qemu-dbus-input` has the whole protocol.
- **Tested** (`packages/wsh-gst-qemu-dbus/test.sh`, in CI; TCG, no GPU): wisp's framebuffer
  kernels on x86 (std VGA, PS/2, AC97), on aarch64's virt (virtio tablet, AC97), on the SS-5 (cg3,
  CS4231, Sun mouse) and on x86 with `dbus,gl=on` (the dmabufs mapped, and again through EGL on
  Mesa's software device): the frame identical to QEMU's screendump, keys in the guest 5 ms after
  the bridge read them, relative and absolute motion and buttons, a 440 Hz tone of 2.00 s at
  440.0 Hz without a dropout, the end of stream when QEMU quits. Also through PVE (`qm start` of a
  `display=dbus` and a `mesa-display=dbus` VM), and on a node with an NVIDIA GPU: a
  `mesa-display=dbus` VM's block-linear dmabufs through EGL, the frame identical to QEMU's
  screendump in four runs out of four.

## Streaming to Moonlight

A [Moonlight](https://moonlight-stream.org/) client (PC, phone, TV) can stream a VM's D-Bus display,
picture, sound, keyboard and mouse in one H.264/Opus connection, through
[Wolf](https://github.com/games-on-whales/wolf) (games-on-whales) on the node. This is stage 3d of
the ROADMAP's 3dfx/streaming plan, a working prototype: `e2e/streaming` in wsh-pve builds it, runs it
and measures it, and the steps for a node are below. It needs no GPU (x264, software encoding).

Wolf was chosen over Sunshine because Wolf takes any GStreamer pipeline as an app's video and audio
source (`[profiles.apps.video] source = ...` in its configuration), while Sunshine captures from KMS,
X11, Wayland or NvFBC and would need a capture backend of its own. Each VM is one Moonlight app:

```text
qemudbussrc address=unix:path=/run/wsh-dbus-display/<vmid>.sock ! compositor ! video/x-raw,framerate={fps}/1
  ! videoconvertscale ! videorate ! video/x-raw,width={width},height={height},format=I420,...
  ! x264enc tune=zerolatency ...                      (Wolf's software H.264 encoder settings)
qemudbusaudiosrc address=... ! ... ! opusenc ...      (Wolf's Opus settings)
runner: wolf-input-bridge --address ...               (Moonlight's keyboard and mouse into the VM)
```

- **Video**: `qemudbussrc` sends a buffer only when the picture changes, but Moonlight ends a session
  that gets no video for 10 seconds, so a `compositor` repeats the newest picture at the client's
  frame rate. Wolf scales it to the client's size and encodes it.
- **Sound**: `qemudbusaudiosrc` (the VM needs `audio0: ...,driver=dbus`).
- **Input**: Wolf turns the client's keyboard and mouse into virtual Linux input devices
  (`/dev/uinput`): "Wolf (virtual) keyboard" (Moonlight's Windows key codes already mapped to Linux
  key codes), "Wolf mouse virtual device" (relative motion, buttons, wheel) and "... (absolute)"
  (positions on a 19200 x 12000 area). The app's runner, `wolf-input-bridge`, grabs those devices
  and writes `qemu-dbus-input` lines: `key CODE 1|0`, `btn`, `wheel`, `rel DX DY`, and
  `abs X Y 19200 12000` for positions, which `qemu-dbus-input` scales to the console and converts to
  what the guest's pointer takes. Wolf starts the runner with the session and stops it after.
- **Apps without a compositor**: an app with `start_virtual_compositor = false` (ours, and Wolf's
  own "Test ball" example) never started in Wolf (it waited for a Wayland socket that no compositor
  makes); `e2e/streaming/wolf-no-compositor.patch` fixes that. Wolf also crashed at start without a
  PulseAudio server to connect to, even though these apps don't use one, so one runs next to it.
- **Files** (`e2e/streaming` in wsh-pve): `Dockerfile` (Wolf, moonlight-embedded and the probe
  client, all from source at pinned commits on Debian 13; its `ct` stage is a container template
  for a node), `wolf-config.py` (writes Wolf's `config.toml` with an app per VM from Wolf's
  defaults, keeping paired clients), `wolf-start` (PulseAudio and Wolf in that container),
  `wolf-input-bridge`, `wolf-pair` (enters a client's PIN through Wolf's API socket), `node.sh`,
  `moonlight-probe.c`, `stream3d.py` and `test.sh`.

### Measured

`e2e/streaming/test.sh` in the lab: the published pve-qemu-kvm (TCG) with wisp's framebuffer kernel
(1280x800, std VGA, AC97, PS/2 mouse) and Wolf in one container, moonlight-embedded (pairing) and
`wsh-moonlight-probe` (a Moonlight client on moonlight-embedded's libraries that decodes every frame
in software and reports it with its times) in another, H.264 1280x800 at 60 frames/s, about 7 Mbit/s.
All checks passed in five runs (QEMU's refresh 30, 16 and 8 ms without GL, 30 and 8 ms with
`dbus,gl=on` through `/dev/udmabuf`):

| | refresh 30 ms | 16 ms | 8 ms | GL, 30 ms | GL, 8 ms |
| --- | --- | --- | --- | --- | --- |
| Guest draws -> decoded at the client, median (min-max), 10 samples | 55 ms (43-70) | 48 ms (39-63) | 51 ms (29-65) | 61 ms (43-72) | 49 ms (36-62) |
| New pictures per second at the client while the guest draws without a pause | 33.2 | 37.9 | 40.6 | 32.2 | 41.8 |
| Key: client -> the guest's serial line, median | 1.5 ms | 1.7 ms | 1.3 ms | 1.3 ms | 1.3 ms |

A second series on the same host gave 62, 51 and 54 ms median (30 ms, 8 ms, GL at 30 ms) and the
same rates within a picture a second. The host was shared with other jobs. With the
wsh-gst-qemu-dbus of the audio fix and the EGL import (built from the branch, `WSH_GST_DEB`), two
series: 50-52, 53 and 50 ms median at 30, 16 and 8 ms, 54-59 ms with GL at 30 ms, 60-64 ms with
GL read through EGL (`x86_64-egl`, Mesa's software device), every check passed.

- **Picture**: the decoded frame against QEMU's screendump: mean difference 1.6 of 255 per channel,
  1.4% of the pixels off by more than 48 (the colour edges of 4:2:0 chroma).
- **Latency**: from the guest's report that it drew (`fbtest` on its serial line) to the first
  decoded frame that shows it; the client's own decoding is 0.7 ms of that. The rest is QEMU's
  refresh (the wait for the next look at the screen), the compositor's frame, x264 and the network.
- **Frame pacing**: the client gets a steady 60 frames/s (median interval 17-19 ms, but spread from
  5 to 35 ms: standard deviation 8-9 ms). New pictures come at QEMU's refresh at 30 ms (33.3 a
  second at most) and are bound by how fast the guest draws below that.
- **Input**: keys A, B, Esc and the mouse buttons reach the guest 1.3-2.2 ms after the client sends
  them; 0.3 ms of that is the way through Wolf to its virtual keyboard. Absolute positions and
  relative motion add up exactly on the guest's PS/2 mouse (+70, +30 for a position, `move 10 0`
  and a position 60, 30 away).
- **Sound**: `soundtest 440 2000` in the client's decoded Opus audio: 440.0 Hz, 2.03 s without a
  dropout, the first sound at the client 38-56 ms after the command was typed. Before the fix in
  `qemudbusaudiosrc`: 1.93-1.98 s with one dropout of 50-85 ms just after the tone's start in most
  runs, the first sound 90-160 ms after the command. The cause: the source sent nothing until the
  guest played, so Wolf's audio pipeline (`queue max-size-buffers=3 leaky=downstream ! audiorate !
  audioconvert ! opusenc`) got its first buffer at the running time the tone started; `audiorate`
  filled everything from the stream's start (11-12 s by then) with silence in one go, and while
  that went through Opus (about 80 ms) the leaky queue dropped the tone's first five 10 ms buffers,
  which `audiorate` then filled with silence too (its log: offset 573638, then 576038). How long
  that took grew with the session's length, so it showed in the runs with the input checks (which
  come before the sound), and only when the host was busy enough (four of seven runs with the old
  package had no dropout). The client got that silence as one burst (11.6 s of audio at once). Now the
  source sends silence in real time while the guest plays nothing; the check fails on a dropout
  inside the tone and when more than 250 ms of audio reach the client at once (5 ms now).

### On a node

Tested on a PVE node (pve-qemu-kvm 11.1.3-4, qemu-server with the D-Bus display, an NVIDIA GPU on
NVIDIA's own driver): Wolf in a **privileged** container, and in an **unprivileged** one (with
`dbus-display-uids` and a udev rule on the node, below), the VM started with `qm start`.

**The privileged container.** The template is `e2e/streaming/Dockerfile`'s `ct` stage (Debian 13
with systemd, Wolf, `wsh-gst-qemu-dbus`, x264, GStreamer's nvcodec, PulseAudio, `wolf-start`,
`wolf-config.py`, `wolf-input-bridge`, `wolf-pair`, and the probe client), exported with Docker:

```sh
docker build --target ct -t wsh-stream3d-ct <context>     # the context test.sh assembles
docker create --name ct-export wsh-stream3d-ct /bin/true
docker export ct-export | gzip > wsh-stream3d-ct.tar.gz
```

On the node, as root (`<vmid>` the VM, `<ctid>` the container):

```sh
qm set <vmid> --vga std,display=dbus --audio0 device=AC97,driver=dbus
qm start <vmid>              # qemu-server makes /run/wsh-dbus-display (kept from then on)
pct create <ctid> wsh-stream3d-ct.tar.gz --hostname wolf --unprivileged 0 --ostype debian \
  --rootfs local:4 --memory 1536 --cores 4 --features nesting=1 --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --dev0 /dev/uinput
cat >> /etc/pve/lxc/<ctid>.conf <<EOF
lxc.mount.entry: /run/wsh-dbus-display srv/wsh-dbus-display none bind,create=dir 0 0
lxc.mount.entry: /dev/input dev/input none bind,create=dir 0 0
lxc.cgroup2.devices.allow: c 13:* rwm
EOF
pct start <ctid>
pct exec <ctid> -- wolf-start <vmid>              # PulseAudio, Wolf, the app "wsh-vm-<vmid>"
```

- The bus directory goes to `/srv/wsh-dbus-display`, not `/run/...`: the container's systemd
  mounts its own `/run` over a bind mount there. The directory must exist when the container
  starts (a D-Bus VM started once since the node booted).
- `/dev/input` is the node's: Wolf's virtual keyboard and mice appear there when a session starts,
  and `wolf-input-bridge` grabs them (EVIOCGRAB), so the node's own desktop doesn't get the
  client's keys. The node's real keyboard and mouse are visible in the container too (it is
  privileged); the bridge takes only Wolf's devices.
- When a Moonlight client pairs, it shows a PIN: `pct exec <ctid> -- wolf-pair <pin>`. Running
  `wolf-start` again (other VMs, another encoder) keeps the paired clients. `pct exec` passes the
  node shell's environment on (`XDG_RUNTIME_DIR=/run/user/0` among it); `wolf-start` and
  `wolf-pair` use `/run/wolf` whatever it says, and `pct exec <ctid> -- env -i
  HOME=/root PATH=/usr/local/bin:/usr/bin:/bin ...` keeps the rest out.
- Moonlight reaches Wolf on TCP 47984, 47989 and 48010 and UDP 47999, 48100 and 48200 of the
  container's address.

**An unprivileged container** (the same template) streams with `dbus-display-uids` and a udev rule
on the node for Wolf's input devices. Tested end to end on the node above (qemu-server 9.2.24+wsh3,
pve-qemu-kvm 11.1.3-4+wsh29, wsh-gst-qemu-dbus 0.3): picture, sound, keyboard and mouse, from the
container's loopback and from a client on another machine (measured below). Give the container a
uid range of its own, so that no other container's root is the uid the VM's bus and the input
devices are given to. On the node, as root (`<uid>` the container's root on the node, here 300000):

```sh
echo 'root:<uid>:65536' >> /etc/subuid      # once per node, for the container's lxc.idmap
echo 'root:<uid>:65536' >> /etc/subgid
cat > /etc/udev/rules.d/90-wsh-wolf-uinput.rules <<EOF
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="Wolf *", OWNER="<uid>", GROUP="<uid>", MODE="0660", ENV{LIBINPUT_IGNORE_DEVICE}="1"
EOF
udevadm verify /etc/udev/rules.d/90-wsh-wolf-uinput.rules && udevadm control --reload
qm set <vmid> --vga std,display=dbus --audio0 device=AC97,driver=dbus --dbus-display-uids <uid>
qm start <vmid>
pct create <ctid> wsh-stream3d-ct.tar.gz --hostname wolf --unprivileged 1 --ostype debian \
  --rootfs local:4 --memory 2048 --cores 4 --features nesting=1 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --dev0 /dev/uinput
cat >> /etc/pve/lxc/<ctid>.conf <<EOF
lxc.idmap: u 0 <uid> 65536
lxc.idmap: g 0 <uid> 65536
lxc.mount.entry: /run/wsh-dbus-display srv/wsh-dbus-display none bind,create=dir 0 0
lxc.mount.entry: /dev/input dev/input none bind,create=dir 0 0
lxc.cgroup2.devices.allow: c 13:* rwm
EOF
pct mount <ctid>    # shift the template's owners from 100000+ to <uid>+ (see below)
python3 - /var/lib/lxc/<ctid>/rootfs <uid> <<'EOF'
import os, stat, sys
root, uid = sys.argv[1], int(sys.argv[2])
def shift(i): return i - 100000 + uid if 100000 <= i < 165536 else i
for d, dirs, files in os.walk(root):
    dirs[:] = [x for x in dirs if not os.path.ismount(os.path.join(d, x))]
    for p in [d] + [os.path.join(d, f) for f in files]:
        st = os.lstat(p)
        if (shift(st.st_uid), shift(st.st_gid)) != (st.st_uid, st.st_gid):
            os.lchown(p, shift(st.st_uid), shift(st.st_gid))
            if not stat.S_ISLNK(st.st_mode):
                os.chmod(p, stat.S_IMODE(st.st_mode))   # chown clears set-uid bits
EOF
pct unmount <ctid>
pct start <ctid>
pct exec <ctid> -- env -i HOME=/root PATH=/usr/local/bin:/usr/bin:/bin wolf-start <vmid>
```

- **Which uid**: the host uid of the container's root: what its `lxc.idmap` maps 0 to (`100000`
  with PVE's default mapping, which every unprivileged container shares). No group mapping is
  needed for the bus.
- **The owners before the first start**: `pct create` unpacks the template with PVE's default
  mapping (owners 100000 and up) before the `lxc.idmap` lines are in the configuration, so the
  container would then fail to start (`Permission denied` creating its mount points). The Python
  between `pct mount` and `pct unmount` adds `<uid> - 100000` to every uid and gid from 100000 to
  165535 under the container's root file system, without following symbolic links, and sets each
  mode again (`chown` clears set-uid bits).
- **What the uid gets on the bus**: this VM's screen, sound, keyboard and mouse, as a VNC console
  would give them. Every container whose root is that host uid and which has the directory
  bind-mounted gets them. Tested: the container's root reaches the VM's bus (picture, the sound
  listener, input); a user of the container (uid 1000, 301000 on the node) is refused at the
  socket directory (`Could not connect: Permission denied`), and so is uid 200000 on the node; the
  container's root on another VM's bus that doesn't list it gets through the directory but is
  refused by that bus (`The connection is closed`).
- **What stays on the node**: the user `wsh-display-<uid>` (locked, no home, `nologin`; `useradd`
  warns that the uid is above `SYS_UID_MAX`, which is harmless) is kept after the VM stops
  (`userdel wsh-display-<uid>` removes it); it lets that uid be named, nothing more (dbus-daemons
  accept a uid only with a user). The ACL entry goes when no running VM names the uid.
- **Input: the udev rule.** The container's root opens `/dev/uinput` (PVE makes the node `root:root
  0660` inside) and Wolf creates its keyboard and mice, but the event devices they become appear in
  the node's `/dev/input` as `root:input 0660`, which the bind mount shows the container as
  `nobody:nogroup`: opening them is refused (`EACCES`), so `wolf-input-bridge` gets nothing. The
  rule gives the devices named `Wolf ...` to the container's root and tells libinput (a desktop on
  the node) to leave them alone. What it changes on the node: those devices only, while they exist
  (Wolf makes them per session); the node's real keyboard and mouse stay `root:input`. Any process
  on the node that may write `/dev/uinput` (root) can make a device with such a name, which then
  goes to that uid. No way without a node change was found: the container's root can't `chown` a
  device node that belongs to the node's root, a bind mount of single device nodes keeps their
  owner, and mapping the node's `input` group into the container would hand it every input device
  of the node, its real keyboard included. A bridge on the node (reading Wolf's devices there)
  would be a node service and is not part of this design.
- **A DHCP client**: the `ct` template has `dhcpcd-base`, so `ip=dhcp` works (the first templates
  had no DHCP client and `ifup` failed with `No DHCP client software found!`).
- **`stream3d.py` with an unprivileged container**: a directory under `/root` on the node can't be
  bind-mounted into it (the mount is made inside the container's user namespace, which may not
  pass `/root`'s `0700`). Use the container's own directory through the node's `/proc`: `pct exec
  <ctid> -- sh -c 'mkdir -p /shared && chmod 1777 /shared'`, then `--shared
  /proc/$(lxc-info -n <ctid> -p -H)/root/shared` and an `--outdir` below it (made `0777` first, so
  the probe in the container may write there) with `--probe-outdir /shared/<name>`.
- **Without `dbus-display-uids`** (a qemu-server older than the option): Wolf starts in the
  unprivileged container, but `qemudbussrc` can't reach the socket (`Could not connect: Permission
  denied` on `/run/wsh-dbus-display`, `root:wsh-display 0750`).

**A Moonlight client on the network.** Wolf listens on the container's address: TCP 47984 (HTTPS,
pairing), 47989 (HTTP) and 48010 (RTSP), UDP 47999 (control), 48100 (video) and 48200 (audio), and
mDNS on UDP 5353 (Wolf's ports, not Sunshine's 47998-48010). Put the container's `net0` on the
bridge and VLAN the clients reach (`bridge=vmbr0,tag=<vlan>` on a VLAN-aware bridge) with DHCP or
a fixed address. PVE's firewall filters a container only when its `net0` has `firewall=1` (and the
datacenter's firewall is enabled); then the container's `/etc/pve/firewall/<ctid>.fw` needs:

```text
[OPTIONS]
enable: 1

[RULES]
IN ACCEPT -p tcp -dport 47984,47989,48010
IN ACCEPT -p udp -dport 47999,48100,48200
IN ACCEPT -p udp -dport 5353
```

(the last for mDNS discovery only: a client can add the host by its address). To pair a client
(Moonlight on a PC, TV or phone): add the host by the container's address (or pick it when mDNS
finds it, named `wsh-pve`), select it, and Moonlight shows a four-digit PIN. Enter it on the node:

```sh
pct exec <ctid> -- env -i HOME=/root PATH=/usr/local/bin:/usr/bin:/bin wolf-pair <pin>
```

`wolf-pair` waits up to 60 seconds for the request and answers it; the client then lists one app
per VM, `wsh-vm-<vmid>`. Pairings are kept in the container's `/etc/wolf/cfg/config.toml`, also
when `wolf-start` runs again. Wolf doesn't start by itself with the container: run `wolf-start`
after the container starts (the VMs must be running for their apps to stream).

**NVIDIA GPU: NVENC.** Add the GPU's devices and NVIDIA's libraries of the node's driver version
(here installed with NVIDIA's installer, not packages; copy them from the node), then start Wolf
with NVENC:

```sh
pct set <ctid> --dev1 /dev/dri/renderD128 --dev2 /dev/nvidia0 --dev3 /dev/nvidiactl --dev4 /dev/nvidia-modeset \
  --dev5 /dev/nvidia-uvm --dev6 /dev/nvidia-uvm-tools
for l in libcuda libnvidia-encode libnvcuvid libnvidia-ptxjitcompiler libnvidia-nvvm libnvidia-gpucomp; do
  pct push <ctid> /usr/lib/x86_64-linux-gnu/$l.so.<version> /usr/lib/x86_64-linux-gnu/$l.so.<version>
done
pct exec <ctid> -- sh -c 'cd /usr/lib/x86_64-linux-gnu && for l in libcuda.so.1 libnvidia-encode.so.1 \
  libnvcuvid.so.1 libnvidia-ptxjitcompiler.so.1; do ln -sf ${l%.so.1}.so.<version> $l; done &&
  ln -sf libnvidia-nvvm.so.<version> libnvidia-nvvm.so.4 && ldconfig'
pct exec <ctid> -- env H264_ENCODER=nvenc wolf-start <vmid>
```

Wolf doesn't pick NVENC by itself here: its NVIDIA pipeline also needs `cudaconvertscale`, which
needs the CUDA toolkit's runtime compiler (`libnvrtc`), not part of the driver. `H264_ENCODER=nvenc`
gives the apps `nvh264enc` (Wolf's settings: CBR, zero latency, preset p1, ultra-low-latency tune)
on NV12 in system memory.

**NVIDIA GPU: `dbus,gl=on`.** A VM with `mesa=1,mesa-display=dbus` (the 3dfx binary) hands the
console to `qemudbussrc` as dmabufs in NVIDIA's block-linear layout (`XB24`, modifier
`0x300000000cdb014` on the GTX 1080), which it reads through EGL on the render node. The container
needs `/dev/dri/renderD128` (and `/dev/dri/card0`, `/dev/nvidia0`, `/dev/nvidiactl`, as above) and
NVIDIA's EGL and GLES libraries with glvnd's vendor file:

```sh
pct set <ctid> --dev7 /dev/dri/card0
for l in libEGL_nvidia libGLESv2_nvidia libnvidia-eglcore libnvidia-glsi libnvidia-glcore libnvidia-tls \
    libnvidia-gpucomp libnvidia-glvkspirv libnvidia-allocator; do
  pct push <ctid> /usr/lib/x86_64-linux-gnu/$l.so.<version> /usr/lib/x86_64-linux-gnu/$l.so.<version>
done
pct exec <ctid> -- mkdir -p /usr/share/glvnd/egl_vendor.d
pct push <ctid> /usr/share/glvnd/egl_vendor.d/10_nvidia.json /usr/share/glvnd/egl_vendor.d/10_nvidia.json
pct exec <ctid> -- sh -c 'cd /usr/lib/x86_64-linux-gnu && ln -sf libEGL_nvidia.so.<version> libEGL_nvidia.so.0 &&
  ln -sf libGLESv2_nvidia.so.<version> libGLESv2_nvidia.so.2 &&
  ln -sf libnvidia-allocator.so.<version> libnvidia-allocator.so.1 && ldconfig'
```

`GST_DEBUG=qemudbussrc:4` then logs `dmabufs through EGL device /dev/dri/renderD128, EGL 1.5
(NVIDIA), GL renderer NVIDIA GeForce GTX 1080/PCIe/SSE2`. Without NVIDIA's EGL in the container
the element finds no GPU device and warns once that it can't read the console's dmabufs.

**Measured on the node** (TCG guest, wisp's framebuffer kernel at 1280x800, PS/2 mouse; the probe
client in the container on the loopback, so no network in the numbers; 10 latency samples each):

| | x264, refresh 30 ms | x264, refresh 8 ms | NVENC, refresh 30 ms |
| --- | --- | --- | --- |
| Guest draws -> decoded at the client, median (min-max) | 54 ms (41-73) | 47 ms (43-60) | 50 ms (39-65) |
| New pictures per second while the guest draws | 32.6 | 38.6 | (not comparable, see below) |
| Key: client -> the guest's serial line, median | 1.1 ms | 1.3 ms | 1.5 ms |
| Sound: `soundtest 440 2000` | 440.0 Hz, 1.93 s | 440.0 Hz, 1.93 s | 440.0 Hz, 1.93 s |

Every check passed in those three runs (picture against QEMU's screendump, keyboard, mouse,
sound), with the same dropout just after the tone's start as in the lab (fixed since, see below).
NVENC saved about 4 ms of the median against x264. Its CBR stream keeps refining a still picture
for a few frames, which the probe counts as changes (51 "new" pictures a second at a 30 ms
refresh), so its picture rate isn't comparable.

**With `dbus,gl=on`** (the tiled dmabufs through EGL; pve-qemu-kvm 11.1.3-4+wsh27 on the node, the
same VM switched between `vga: std,display=dbus` and `vga: std,mesa=1,mesa-display=dbus`, one
session, refresh 30 ms, every check passed in each run):

| | x264, no GL | x264, GL | NVENC, no GL | NVENC, GL |
| --- | --- | --- | --- | --- |
| Guest draws -> decoded at the client, median (min-max) | 53 ms (39-74), 71 ms (48-81) | 89 ms (74-110), 92 ms (77-110), 96 ms (78-111) | 55 ms (36-63) | 77 ms (59-87) |
| Sound: `soundtest 440 2000` | 440.0 Hz, 2.03 s | 440.0 Hz, 2.03 s | 440.0 Hz, 2.03 s | 440.0 Hz, 2.03 s |

GL costs 22-36 ms of the median here (in the lab, with Mesa's llvmpipe, 5-10 ms). It isn't the
read: `UpdateDMABUF` is answered in 0.7 ms on average (at most 6-12 ms), the second read 20 ms
later changed the picture once in about 66 updates, and reading the frames as `BGRx` instead of
`RGBx` changed nothing. QEMU's updates came 9-27 ms after the guest's report that it drew, as
without GL; where the rest goes is open.

**The unprivileged container, measured** (qemu-server 9.2.24+wsh3, pve-qemu-kvm 11.1.3-4+wsh29,
wsh-gst-qemu-dbus 0.3; KVM guest, wisp's framebuffer kernel at 1280x800, PS/2 mouse, refresh 30 ms,
x264; 10 latency samples each). Over the network the probe ran on another machine in the same
VLAN (0.2-0.4 ms ping) and `stream3d.py` on the node read its output; the two clocks agreed within
about 1 ms (ICMP timestamps), which is the error of those numbers:

| | loopback (probe in the container) | network (probe on another machine) |
| --- | --- | --- |
| Guest draws -> decoded at the client, median (min-max) | 61.3 ms (50.6-79.3) | 60.6 ms (41.4-72.4) |
| Frames per second at the client while the guest draws; new pictures | 60.5; 23.0 | 59.8; 28.8 |
| Key: client -> the guest's serial line, median | 2.6 ms | 3.0 ms |
| Key: client -> Wolf's virtual keyboard (the bridge reads it), median | 0.2 ms | 0.7 ms |
| Left button: client -> the guest's serial line | 3.7 ms | 4.2 ms |
| Sound: `soundtest 440 2000` | 440.0 Hz, 2.03 s, no dropout, first sound 28 ms after the command | not checked (the client's WAV stays on that machine) |

Every check passed (the picture 1.59/255 from QEMU's screendump on the loopback). The network adds
about half a millisecond to input; the picture's latency is the same within the spread, which is
QEMU's 30 ms refresh. The Windows 98 Glide guest of the next section through the same unprivileged
container (Glide read back, x264, the probe on the loopback, `SRC_PROPS=shared-map=false`, see
there): guest swap to decoded frame 26.1 ms median (20.8-34.7, 597 frames), 59.8 new guest
frames a second, keys A, B, Z and the tablet exact, input to picture 42.0 ms, as in the privileged
container. Not verified yet: a real Moonlight client on a PC, TV or phone (paired and
streamed by moonlight-embedded's libraries only). A Glide guest: below.

### A Windows 98 guest with Glide

Stage 3f: a Windows 98 SE VM drawing through Glide (qemu-3dfx), streamed through Wolf in the
privileged container above, with `e2e/streaming/stream3dfx.py` measuring. No game is needed: the
guest runs `w3dstrm.exe` (`e2e/3dfx/win98/w3dstrm.c`, built with the other Windows 98 test programs
by `e2e/3dfx/win98/build.sh`), a Glide program that takes commands on COM1 and animates at 60
frames a second: a white bar moving across the 640x480 picture and, in its bottom tenth, eight
cells with the frame number's low eight bits (white 1, black 0), where the probe client reads its
eight points. It reports every swap on COM1 (`F <frame> <ms>`), so each decoded frame at the
client says which guest frame it shows and the serial line says when the guest swapped it; that
gives the latency of every guest frame that reaches the client, and the pacing. B held down shows
colour bars instead (input to picture); keys and the mouse are reported as the program's window
gets them; `tone HZ MS` plays through WinMM; `run S PROGRAM` starts another program from
`C:\WIN3DFX` (the demos: `WSHDEMO.EXE`, `WSHSPACE.EXE`).

**The VM.** The guest's disk is the operator's own installed Windows 98 SE (a full clone of one; no
Windows file is in wsh-pve). With the VM stopped, put on its FAT partition (mtools, from the
streaming container with the image's directory bind-mounted, or anywhere else) qemu-3dfx's guest
drivers of the node's revision (`qemu-system-x86_64-3dfx --version` names it; the
`qemu-3dfx-drivers-<rev>` release: `FXMEMMAP.VXD`, `GLIDE.DLL`, `GLIDE2X.DLL`, `GLIDE3X.DLL` in
`C:\WINDOWS\SYSTEM`, `GLIDE2X.OVL` in `C:\WINDOWS`), `W3DSTRM.EXE`, `WSHDEMO.EXE` and
`WSHSPACE.EXE` in `C:\WIN3DFX`, and `W3DSTRM.EXE` once more in the Start menu's StartUp folder.
Then, on the node:

```sh
qm set <vmid> --vga std,memory=128,mesa=1,mesa-display=dbus --audio0 device=AC97,driver=dbus \
  --serial0 socket                       # or std,memory=128,mesa=1,display=dbus: Glide read back, no GL
qm start <vmid>
pct exec <ctid> -- env -i HOME=/root PATH=/usr/local/bin:/usr/bin:/bin H264_ENCODER=nvenc wolf-start <vmid>
python3 stream3dfx.py --node 127.0.0.1 --keydir /root/.cache/moonlight --app wsh-vm-<vmid> \
  --outdir <dir>/<name> --probe-outdir /shared/<name> --shared <dir> \
  --serial unix:/var/run/qemu-server/<vmid>.serial0 --qmp unix:/var/run/qemu-server/<vmid>.qmp \
  --probe-prefix "pct exec <ctid> -- env -i HOME=/root PATH=/usr/local/bin:/usr/bin:/bin" \
  --enter-after 45 --demo
```

`stream3dfx.py` and `stream3d.py` (it imports it) run on the node, where the VM's serial socket
and QMP are; `<dir>` is bind-mounted into the container at `/shared` (the probe writes its frames
and the client's sound there). The probe is paired in the container, on the loopback (`moonlight
pair -pin <pin> 127.0.0.1` there, then `wolf-pair <pin>`). `--enter-after` presses Enter in the
guest while `w3dstrm.exe` doesn't answer: the clone stopped at Windows' network logon dialog at
every boot, and at the first boot with these devices at two new-hardware wizards (the PCI bridge
and AC97 at its new address), which Enter took through. `--api glide3` uses Glide 3.
`--skip glide` leaves out the Glide window and the checks that need it, so a guest without
qemu-3dfx's drivers can still be checked for the stream and its sound.
`--tap-address unix:path=/srv/wsh-dbus-display/<vmid>.sock` adds a second listener in the
container during the latency seconds, which splits the latency at `qemudbussrc`.

**Glide read back needs `SRC_PROPS=shared-map=false`.** With `display=dbus` (no GL) and the shared
map that `qemudbussrc` offers by default, the client kept the first picture of the Glide window:
QEMU sent one `ScanoutMap` for the 640x480 surface and then no `UpdateMap` while the program swapped
60 times a second (on pve-qemu-kvm 11.1.3-4+wsh29; the Windows desktop before it came as plain
`Scanout`s). Without the map every swap came as a `Scanout` (240 in 4 s) and every check passed.
Start Wolf for such a VM with `pct exec <ctid> -- env -i HOME=/root
PATH=/usr/local/bin:/usr/bin:/bin SRC_PROPS=shared-map=false wolf-start <vmid>` (it applies to all
the apps of that Wolf; wisp's VGA picture streams either way).

**A mode change and Wolf's compositor.** The first runs showed the 640x480 Glide picture unscaled in
the top left corner of the client's 1280x800, on a checkerboard: the `compositor` that repeats the
newest picture keeps the size it negotiated first (the 1280x1024 desktop) and draws a smaller input
as it is. `wolf-config.py` now scales the picture to the client's size before the compositor
(stretched, as before) and gives the compositor a black background.

**Measured on the node** (the GTX 1080 node above; KVM, `cpu: pentium3`, 512 MB; Windows' desktop
1280x1024, the Glide window 640x480; the probe in the container on the loopback, H.264 1280x800 at
60 frames/s; 10 s of animation per run, 570-650 latency samples each; every check passed except
the sound, which works since `wsh/0170`, see below):

| | read back, x264 | read back, NVENC | GL, x264 | GL, NVENC |
| --- | --- | --- | --- | --- |
| Guest swap -> decoded at the client, median (min-max) | 25.7 ms (21.9-35.0); Glide 3: 25.5 ms (22.0-32.9) | 23.6 ms (20.5-28.2) | 28.6 ms (23.6-37.8); 33.1 ms (22.6-46.7) with the second listener | 24.9 ms (20.5-30.9), with the second listener |
| Guest swap -> `qemudbussrc` (the second listener), median | 0.7 ms | | 2.6 ms | 2.0 ms |
| New guest frames per second at the client (the guest: 60) | 59.9 | 60.0 | 59.2; 58.8 | 60.1 |
| Interval between new pictures, stdev | 2.1 ms | 1.8 ms | 2.7 ms; 7.3 ms | 1.8 ms |
| Key B -> the program's `WM_KEYDOWN`, median | 4.0 ms | 2.9 ms | 3.3-3.9 ms | 3.6 ms |
| Key B held -> the bars decoded at the client (input to picture), median | 39.7 ms | 41.7 ms | 41.5-43.8 ms | 40.1 ms |

- **Picture**: a still frame decoded at the client against the frame `w3dstrm.exe` drew (its known
  content, scaled to 1280x800): mean difference 2.3/255, 0.23-0.26% of the pixels off by more than
  48; against QEMU's screendump (read back only) 1.1/255. With GL, QEMU's screendump has no
  surface (`no surface`: the console scans a dmabuf out and no VNC client makes QEMU read it back),
  so the known frame is the reference there.
- **Latency**: from the guest's swap (its `F` line on the serial line) to the first decoded frame
  that shows that frame number. Glide frames go out at each swap, not at QEMU's refresh: they reach
  `qemudbussrc` 0.7 ms (read back) or 2.0-2.6 ms (GL, through EGL) after the swap. The rest, 23-30
  ms, is the compositor's next tick, the encoder, the loopback and the client's decode. That is
  half of wisp's 47-55 ms, whose VGA drawing waits for QEMU's refresh.
- **Where GL's cost went in stage 3e**: here `dbus,gl=on` adds 2-5 ms over the read back, not the
  22-36 ms of wisp's VGA picture. The EGL import and the read are the same, so the cost sits on
  the VGA path: with GL, QEMU uploads the VGA surface into a texture at the display refresh and
  hands that over, and NVIDIA's driver doesn't make the read wait for the upload, so a first read
  that misses it shows only in the read 20 ms later (in a Glide run 168 of 3488 second reads
  changed the picture, about 5%; a Glide frame read too early is replaced by the next swap 17 ms
  later anyway). Not measured on the VGA path itself: a fence from QEMU, or a read once the upload
  is done, would show whether that is all of it.
- **Pacing**: the guest's 60 swaps a second reach the client as 58.8-60.1 new pictures a second
  out of 60 frames; with NVENC every guest frame arrived and the intervals spread by 1.8 ms
  (stdev), with x264 a few frames were skipped (one guest frame in 40-80) and the spread was 2-7
  ms. The demos, unpaced: `WSHDEMO.EXE` (tunnel) at 90 frames/s in the guest (median of its FPS
  lines) gave the client a new picture in each of its 60 frames (stdev 4.8 ms); `WSHSPACE.EXE
  -auto` at 23-103 frames/s (median 60) gave 42 new pictures a second (stdev 9.1 ms).
- **Keyboard and mouse**: A, B, Z arrive as virtual keys 65, 66, 90 with scan codes 30, 48, 44,
  down and up, 2.9-4.0 ms after the client sent them. The VM's USB tablet takes absolute positions
  exactly (the client's centre is 639,511 of Windows' 1280x1024; +60,+30 on 1280x800 lands at
  699,550). Relative motion is moved in the console's pixels, which are the Glide window's
  640x480 while a game runs: `move 10 0` moved Windows' pointer by 20 and `move 0 10` by 21. The
  buttons reach the program 8-18 ms after the client.
- **Sound** (pve-qemu-kvm 11.1.3-4+wsh29 with `wsh/0170` on top, wsh-gst-qemu-dbus 0.3, x264;
  `stream3dfx.py --skip glide` on a clone without the Glide drivers; before `wsh/0170`, see
  below): `tone 440 2000` (one 2 s
  `waveOutWrite` at 22050 Hz) through AC97 and the guest's SigmaTel STAC97 driver arrives at the
  client as 1.99 s at 443.0 Hz without a dropout, the first loud packet 75-93 ms after the command
  (three runs); `tone 440 3000` as 2.98-2.99 s, 87-98 ms (one run 205 ms), and in two runs of five
  the client's audio had one gap of about 30 ms some 2.7 s into the tone, with all of the tone there
  (late, not lost; QEMU's own stream, recorded with `qemudbusaudiosrc` in the container, had none in
  four runs). `WSHSPACE.EXE -audiotest` passes `wavcheck.py --signature` on QEMU's stream: eight
  segments, 3.97 s, the largest gap 0.1 ms. Every frequency is 0.68% high (443.0 for 440, 402.7 and
  604.1 for 400 and 600) and the signature 0.68% short, in the guest's data already: the codec runs
  at 48000 Hz (the driver never changes its rate) and QEMU passes that on unchanged, so it comes
  from Windows' conversion from 22050 Hz (not checked with a 48000 Hz sound).
- **Sound before `wsh/0170`**: the 2 s tone was done after 0.32 s (0.6-0.8 s with pve-qemu-kvm
  wsh27), the client got 0.28 s of it at 458.7 Hz with five dropouts, and QEMU's stream carried 0.05
  s. A trace of the guest's accesses to the AC97 (QEMU's `memory_region_ops_*` trace events, enabled
  with QMP `trace-event-set-state` around the tone) shows the cause: after each new buffer the
  driver writes LVI and then the control register again with RPBM (run) set, and QEMU's AC97 started
  the engine afresh at every such write, moving it to the next buffer. So each new buffer skipped
  the one playing, the current index stayed at the last valid one, and WinMM got its buffers back
  long before they had played. On the ICH writing RPBM while it is set changes nothing; `wsh/0170`
  starts the engine only when RPBM goes from 0 to 1 (and resumes a paused engine in its buffer).
  Microsoft's AC97 sample driver, which the codec vendors' Windows 98 drivers are built on, does the
  same, so other WDM AC97 drivers should behave alike (only STAC97 tested). The AC97's bus, the
  tablet's interrupt and the D-Bus audio path were not the cause.
- **`WSHSPACE.EXE -audiotest` never finished** in stage 3f for another reason: on Windows it asked
  for a renderer first (Glide 2, Glide 3 or OpenGL) and waited at that menu; it now starts no
  renderer with `-audiotest`.
- **Other sound cards**: qemu-server (with the wsh patch) offers `sb16` (ISA) besides AC97 and the
  Intel HDA cards; Windows 98 SE has a driver for it in its CAB files (`SB16AWE.INF`, the legacy
  `*PNPB003`, found by the Add New Hardware wizard), not tried here. It has none for the ES1370
  (no `VEN_1274` in its INFs), which qemu-server doesn't offer either.

## VGA retrace

`retrace=precise` (x86 only) switches QEMU to its precise VGA retrace emulation: reading the input
status register (port 3DAh) reports display enable and vertical retrace with the timing of a real
CRT. QEMU's default, `dumb`, flips both bits together on every read, so a program that waits for
several reads in a row of "display blanked, not in vertical retrace" (a horizontal blank) never sees
it. Wolfenstein 3D (and likely other id and Apogee games of its
time) then stays on a black mode-13h screen; see the [DOS guide](/guides/dos/#vga-retrace-games).

```sh
qm set 130 --vga std,retrace=precise
```

In the web UI it is **Hardware > Display > VGA retrace: Precise (DOS games)**, shown for x86 VMs with a
display type that has it.

- QEMU has no device property for it, only the `-vga` option, and it applies to every VGA device of
  the VM. qemu-server adds `-vga none,retrace=precise` (`none` adds no device) next to the usual
  `-device` (with a `server`, the `-vga` it already passes gets `,retrace=precise`).
- Accepted for the types whose QEMU device is built on QEMU's VGA core: `std` (`VGA`), `cirrus`
  (`cirrus-vga`), `vmware` (`vmware-svga`), `qxl*` (`qxl-vga`), `virtio` and `virtio-gl`
  (`virtio-vga`, `virtio-vga-gl`). Refused at create, update and start with `none`, `serial*`, the
  sparc `tcx` and `cg3`, and on other architectures.
- `retrace=dumb` is QEMU's default and adds nothing to the command line.

## Further reading

- Read [about SPARC platform graphics combinations](https://wiki.qemu.org/Documentation/Platforms/SPARC) in QEMU documentation
