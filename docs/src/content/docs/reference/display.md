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
  Nobody else may connect. A client in a container gets the directory bind-mounted and a member of
  that group (as the host sees its user).
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
device's **Backend Driver > D-Bus**. Refused: `dbus-refresh` or the audio driver `dbus` without the
D-Bus display; the D-Bus display with a `server` (SDL), with `qxl*`, `virtio-gl`, `none` or
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

- **Who may**: root, or a member of `wsh-display` (the bus's policy, see [D-Bus display](#d-bus-display)).
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
  up to 14 ms on a busy host). It reads linear dmabufs only (Mesa's software renderer through `/dev/udmabuf`, which the
  tests use); a GPU's tiled dmabufs (NVIDIA's) aren't read yet: it warns and drops those frames.
  The mouse cursor isn't drawn into the picture. When the VM stops it ends the stream (EOS).
- **`qemudbusaudiosrc`** gives the guest's playback as raw PCM as QEMU sends it (48 kHz signed
  16-bit stereo with qemu-server's audio driver `dbus`), in 10 ms buffers. QEMU passes the guest
  mixer's volume and mute separately; the element applies them (`apply-volume=false` passes the
  samples as they are).
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
  CS4231, Sun mouse) and on x86 with
  `dbus,gl=on`: the frame identical to QEMU's screendump, keys in the guest 5 ms after the bridge
  read them, relative and absolute motion and buttons, a 440 Hz tone of 2.00 s at 440.0 Hz, the end
  of stream when QEMU quits. Also through PVE (`qm start` of a `display=dbus` and a
  `mesa-display=dbus` VM).

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
same rates within a picture a second. The host was shared with other jobs.

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
- **Sound**: `soundtest 440 2000` in the client's decoded Opus audio: 440.0 Hz, 1.93-1.98 s; the
  first 50-85 ms after the tone's start were lost (one dropout) in every run with input devices,
  not in the one run without them, and the first sound reaches the client 90-160 ms after the
  command was typed.

### On a node

Tested on a PVE node (pve-qemu-kvm 11.1.3-4, qemu-server with the D-Bus display, an NVIDIA GPU on
NVIDIA's own driver): Wolf in a **privileged** container, the VM started with `qm start`.

**An unprivileged container doesn't work with the bus as it is.** Mapping the container's group
onto `wsh-display` (an `lxc.idmap` line and `root:<gid>:1` in `/etc/subgid`) does give the
container the socket directory, but the VM's bus then refuses it, for two reasons:

- GLib's D-Bus client authenticates with `AUTH EXTERNAL <uid>`, the uid it sees in the container
  (0), while the bus sees the host's uid (100000): the bus says `REJECTED EXTERNAL`.
- With the uid left out of `AUTH EXTERNAL` (or given as the host's), the bus accepts the
  authentication and then drops the connection: dbus-daemon (1.16) checks `<allow group=...>`
  against the user database of the node, not the connecting process's groups. A uid without a
  line in the node's `/etc/passwd` and `/etc/group` (the container's root, 100000) isn't in
  `wsh-display` for it. The same is true of a process on the node with `wsh-display` only as a
  supplementary group.

An unprivileged container would need the bus policy to name it (for example `<allow user="100000"/>`
next to the group, which qemu-server's policy file doesn't offer a place for yet), or a user for that
uid in the node's `wsh-display` group.

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
  `wolf-start` again (other VMs, another encoder) keeps the paired clients.
- Moonlight reaches Wolf on TCP 47984, 47989 and 48010 and UDP 47999, 48100 and 48200 of the
  container's address.

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

**Measured on the node** (TCG guest, wisp's framebuffer kernel at 1280x800, PS/2 mouse; the probe
client in the container on the loopback, so no network in the numbers; 10 latency samples each):

| | x264, refresh 30 ms | x264, refresh 8 ms | NVENC, refresh 30 ms |
| --- | --- | --- | --- |
| Guest draws -> decoded at the client, median (min-max) | 54 ms (41-73) | 47 ms (43-60) | 50 ms (39-65) |
| New pictures per second while the guest draws | 32.6 | 38.6 | (not comparable, see below) |
| Key: client -> the guest's serial line, median | 1.1 ms | 1.3 ms | 1.5 ms |
| Sound: `soundtest 440 2000` | 440.0 Hz, 1.93 s | 440.0 Hz, 1.93 s | 440.0 Hz, 1.93 s |

Every check passed in those three runs (picture against QEMU's screendump, keyboard, mouse,
sound), with the same dropout just after the tone's start as in the lab. NVENC saved about 4 ms
of the median against x264. Its CBR stream keeps refining a still picture for a few frames, which the
probe counts as changes (51 "new" pictures a second at a 30 ms refresh), so its picture rate isn't
comparable.

**`dbus,gl=on` on the NVIDIA GPU** (`mesa=1,mesa-display=dbus`): QEMU's EGL and GBM work with
NVIDIA's driver (the 3dfx binary opened the render node and started; the stream ran). But the
console's dmabufs are NVIDIA's block-linear layout (`XB24`, modifier `0x300000000cdb014`), which
`qemudbussrc` can't map yet (it reads linear dmabufs only), so it drops every frame and the client
keeps its first picture. That needs 3c's second slice, an EGL import of tiled dmabufs.

Not verified yet: an unprivileged container (blocked, see above), a client on another machine over
the network, a real Moonlight client on a TV or phone, a 3dfx game through it.

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
