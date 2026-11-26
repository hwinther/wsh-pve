#!/bin/sh
# The node side of e2e/streaming/test.sh, in one container: a VM's D-Bus display bus as qemu-server
# makes it (wsh-dbus-display@<vmid>), QEMU with the D-Bus display as qemu-server starts it (paused;
# the harness continues it), and Wolf with that VM as its Moonlight app (wolf-config.py).
#
# Environment:
#   RUN          x86_64 (std VGA, the shared map), x86_64-gl (the 3dfx binary, -display
#                dbus,gl=on, llvmpipe: dmabufs; needs /dev/udmabuf or a render node) or
#                x86_64-egl (as x86_64-gl, qemudbussrc reading the dmabufs through EGL)
#   REFRESH_MS   -display dbus,refresh-ms= (wsh/0131; qemu-server's dbus-refresh); empty: QEMU's 30
#   MOUSE        ps2 (the PC's PS/2 mouse, relative: wisp's x86 kernel has no USB HID driver) or
#                tablet (a virtio tablet as well, absolute, like PVE's default USB tablet)
#   KERNEL       wisp's framebuffer kernel (default /kernels/kernel-fb-x86_64)
#   VMID         the VM's id for the bus path (default 100)
# The guest's serial line and QMP are on TCP 4555 and 4556 for the harness in the client container.
set -eu
RUN=${RUN:-x86_64}
VMID=${VMID:-100}
MOUSE=${MOUSE:-ps2}
KERNEL=${KERNEL:-/kernels/kernel-fb-x86_64}
BUS=/run/wsh-dbus-display/$VMID.sock
export XDG_RUNTIME_DIR=/run/wolf
mkdir -p "$XDG_RUNTIME_DIR" /etc/wolf/cfg /out
log() { echo "node.sh: $*"; }

install -d -m 0750 -g wsh-display /run/wsh-dbus-display
setpriv --regid=wsh-display --clear-groups dbus-daemon --nofork --nopidfile \
	--config-file=/usr/share/qemu-server/dbus-display.conf --address="unix:path=$BUS" &
for _ in $(seq 50); do [ -S "$BUS" ] && break; sleep 0.1; done
[ -S "$BUS" ] || { log "no bus socket"; exit 1; }

display="dbus,addr=unix:path=$BUS,audiodev=snd0"
[ -z "${REFRESH_MS:-}" ] || display="$display,refresh-ms=$REFRESH_MS"
qemu=qemu-system-x86_64
if [ "$RUN" = x86_64-gl ] || [ "$RUN" = x86_64-egl ]; then
	qemu=qemu-system-x86_64-3dfx
	display="$display,gl=on"
fi
mouse=
[ "$MOUSE" = ps2 ] || mouse="-device virtio-tablet-pci"
# shellcheck disable=SC2086 # $mouse is words
$qemu -M pc -m 128 -accel tcg -nodefaults -vga std -device AC97,audiodev=snd0 $mouse \
	-kernel "$KERNEL" -append "console=ttyS0 wisp=shell" \
	-audiodev dbus,id=snd0,out.frequency=48000 -display "$display" \
	-serial tcp:0.0.0.0:4555,server=on,wait=off -qmp tcp:0.0.0.0:4556,server=on,wait=off \
	-S -daemonize -pidfile /run/qemu.pid > /out/qemu.log 2>&1 || { cat /out/qemu.log; exit 1; }
log "QEMU ($qemu, $display) paused"

# the bridge's log (when each input event left Wolf) where the harness reads it
[ ! -d /shared ] || export BRIDGE_LOG=/shared/wolf-input-bridge.log
[ "$RUN" != x86_64-egl ] || export SRC_PROPS=dmabuf-import=egl
wolf-config.py /usr/local/share/wolf/config.include.toml /etc/wolf/cfg/config.toml "wsh-vm-$VMID=unix:path=$BUS"
export WOLF_CFG_FILE=/etc/wolf/cfg/config.toml WOLF_PRIVATE_KEY_FILE=/etc/wolf/cfg/key.pem \
	WOLF_PRIVATE_CERT_FILE=/etc/wolf/cfg/cert.pem WOLF_USE_ZERO_COPY=FALSE WOLF_LOG_LEVEL=${WOLF_LOG_LEVEL:-INFO} \
	WOLF_DOCKER_SOCKET=/nonexistent/docker.sock HOST_APPS_STATE_FOLDER=/etc/wolf GST_DEBUG=${GST_DEBUG:-2}
# Wolf (at the pinned commit) crashes at start without a PulseAudio server (its PulseAudio router
# subscribes on a null context); these apps use none (start_audio_server = false), but Wolf needs
# one to connect to, as its own image runs one
pulseaudio --daemonize=yes --exit-idle-time=-1 --log-target=stderr 2> /out/pulseaudio.log || true
log "starting Wolf"
exec wolf
