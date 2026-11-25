#!/bin/sh
# The wsh-gst-qemu-dbus package end to end in a throwaway Debian 13 container (as root), no GPU and
# no systemd, against the published pve-qemu-kvm.
#
#   docker run --rm [--device /dev/udmabuf] -v "$PWD:/src:ro" -v "$PWD/build/wsh-gst-qemu-dbus:/deb:ro" \
#     -v "$KERNELS:/kernels:ro" -v "$OUT:/out" debian:trixie \
#     sh /src/packages/wsh-gst-qemu-dbus/test.sh /deb/wsh-gst-qemu-dbus_<version>_amd64.deb /out
#
#   1. Installs the package (and pve-qemu-kvm from the apt repository, GStreamer's tools and base
#      and good plugins, Mesa's EGL for the GL run) and checks it: gst-inspect-1.0 finds both
#      elements, qemu-dbus-input --version gives the package's version.
#   2. Starts a VM's D-Bus display bus as wsh-dbus-display@100.service would: dbus-daemon, as root
#      with the group wsh-display, with qemu-server's policy (src/usr/dbus-display.conf, taken from
#      submodules/qemu-server.patch), on /run/wsh-dbus-display/100.sock. The clients run as the
#      user "streamer", a member of wsh-display, as a streaming server on the node would.
#   3. For each run in RUNS (default "x86_64 aarch64 x86_64-gl sparc32"): QEMU paused with wisp's
#      framebuffer kernel (KERNELS/kernel-fb-<arch>, from the wisp-fb release), -display dbus and
#      the audio driver dbus at 48 kHz, as qemu-server starts it; tests/stream_test.py runs the
#      pipelines and the bridge and checks the picture, the keyboard, the mouse, the sound and the
#      end of stream:
#        x86_64     pc, std VGA, AC97, PS/2 mouse (relative): the picture through the shared map
#        aarch64    virt, bochs-display, AC97, virtio keyboard and tablet (absolute):
#                   shared-map=false, so the pixels come in Scanout/Update
#        x86_64-gl  as x86_64 with qemu-system-x86_64-3dfx and -display dbus,gl=on (Mesa's
#                   llvmpipe through /dev/udmabuf): the picture as dmabufs, read before each
#                   UpdateDMABUF is answered; skipped without /dev/udmabuf
#        sparc32    SS-5, cg3, CS4231, Sun keyboard and mouse (relative): the shared map
#
# OUTDIR gets summary.txt, and per run the serial log, QEMU's screendump, the newest frame as PPM,
# the WAV the audio pipeline wrote and the logs of the pipelines and the bridge. Exit 0 when every
# check passes.
set -eu
DEB=${1:?usage: test.sh WSH-GST-QEMU-DBUS-DEB OUTDIR}
OUT=${2:?usage: test.sh WSH-GST-QEMU-DBUS-DEB OUTDIR}
SRC=${SRC:-/src}
KERNELS=${KERNELS:-/kernels}
RUNS=${RUNS:-x86_64 aarch64 x86_64-gl sparc32}
VMID=100
BUS=/run/wsh-dbus-display/$VMID.sock
RUN=/run/stream-test
USER_NAME=streamer
export DEBIAN_FRONTEND=noninteractive
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL $*" | tee -a "$OUT/summary.txt"; failed=1; }
pass() { echo "PASS $*" | tee -a "$OUT/summary.txt"; }
skip() { echo "SKIP $*" | tee -a "$OUT/summary.txt"; }
failed=0
mkdir -p "$OUT" "$RUN"
: > "$OUT/summary.txt"

step "Install"
apt-get update -qq
apt-get install --no-install-recommends --assume-yes -qq ca-certificates gnupg > /dev/null
cp "$SRC/proxmox-archive-keyring-trixie.gpg" /usr/share/keyrings/proxmox-archive-keyring.gpg
gpg --dearmor < "$SRC/repo/conf/wsh-pve.gpg.key" > /usr/share/keyrings/wsh-pve.gpg
printf 'Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n' \
	> /etc/apt/sources.list.d/proxmox.sources
printf 'Types: deb\nURIs: https://debian.wshosting.no/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/wsh-pve.gpg\n' \
	> /etc/apt/sources.list.d/wsh-pve.sources
printf 'Package: pve-qemu-kvm\nPin: origin debian.wshosting.no\nPin-Priority: 1001\n' > /etc/apt/preferences.d/wsh-pve
apt-get update -qq
# libegl1, libegl-mesa0, libgl1-mesa-dri: the 3dfx binary's EGL display (llvmpipe) for the GL run
apt-get install --no-install-recommends --assume-yes -qq "$DEB" pve-qemu-kvm dbus-daemon \
	gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good python3 \
	libegl1 libegl-mesa0 libgl1-mesa-dri > /dev/null
dpkg-query -W -f '${Package} ${Version}\n' wsh-gst-qemu-dbus pve-qemu-kvm gstreamer1.0-tools | tee "$OUT/versions.txt"

step "Package"
version=$(dpkg-query -W -f '${Version}' wsh-gst-qemu-dbus)
for element in qemudbussrc qemudbusaudiosrc; do
	if gst-inspect-1.0 "$element" > "$OUT/inspect-$element.txt" 2>&1 &&
		grep -q "Version.*$version" "$OUT/inspect-$element.txt"; then
		pass "plugin: gst-inspect-1.0 finds $element ($version)"
	else
		fail "plugin: gst-inspect-1.0 $element (see inspect-$element.txt)"
	fi
done
if [ "$(qemu-dbus-input --version)" = "qemu-dbus-input $version" ]; then
	pass "bridge: qemu-dbus-input --version is $version"
else
	fail "bridge: qemu-dbus-input --version says '$(qemu-dbus-input --version 2>&1)'"
fi

step "The VM's bus (as wsh-dbus-display@$VMID.service)"
# qemu-server creates the group; its bus policy comes from the patch (no qemu-server here)
getent group wsh-display > /dev/null || groupadd --system wsh-display
id "$USER_NAME" > /dev/null 2>&1 || useradd --system --no-create-home --groups wsh-display "$USER_NAME"
extract() {
	awk -v f="+++ b/$1" '$0 == f { on = 1; next } on && /^diff --git / { exit } on && /^@@/ { next }
		on { sub(/^\+/, ""); print }' "$SRC/submodules/qemu-server.patch"
}
mkdir -p /usr/share/qemu-server
[ -e /usr/share/qemu-server/dbus-display.conf ] ||
	extract src/usr/dbus-display.conf > /usr/share/qemu-server/dbus-display.conf
install -d -m 0750 -g wsh-display /run/wsh-dbus-display
setpriv --regid=wsh-display --clear-groups dbus-daemon --nofork --nopidfile \
	--config-file=/usr/share/qemu-server/dbus-display.conf --address="unix:path=$BUS" &
bus_pid=$!
for _ in $(seq 50); do [ -S "$BUS" ] && break; sleep 0.1; done
[ -S "$BUS" ] || { fail "bus: no socket"; exit 1; }

for run in $RUNS; do
	step "QEMU: $run"
	extra=
	display="dbus,addr=unix:path=$BUS,audiodev=snd0"
	expect=map
	mouse=relative
	shared=true
	case $run in
	x86_64)
		arch=x86_64
		machine="qemu-system-x86_64 -M pc -m 128 -vga std -device AC97,audiodev=snd0"
		console=ttyS0
		;;
	x86_64-gl)
		arch=x86_64
		if [ ! -e /dev/udmabuf ] && ! ls /dev/dri/renderD* > /dev/null 2>&1; then
			skip "$run: no /dev/udmabuf and no render node (docker run --device /dev/udmabuf)"
			continue
		fi
		if [ ! -x /usr/bin/qemu-system-x86_64-3dfx ]; then
			skip "$run: this pve-qemu-kvm has no qemu-system-x86_64-3dfx (QEMU with OpenGL)"
			continue
		fi
		machine="qemu-system-x86_64-3dfx -M pc -m 128 -vga std -device AC97,audiodev=snd0"
		console=ttyS0
		display="$display,gl=on"
		expect=dmabuf
		;;
	aarch64)
		arch=aarch64
		machine="qemu-system-aarch64 -M virt -cpu cortex-a57 -m 256 -device bochs-display
			-device virtio-keyboard-pci -device virtio-tablet-pci -device AC97,audiodev=snd0"
		console="ttyAMA0 earlycon=pl011,0x09000000"
		expect=pixels
		mouse=absolute
		shared=false
		;;
	sparc32)
		arch=sparc32
		machine="qemu-system-sparc -M SS-5 -m 128 -vga cg3 -machine audiodev=snd0"
		console=ttyS0
		;;
	*) echo "unknown run $run" >&2; exit 2 ;;
	esac
	kernel="$KERNELS/kernel-fb-$arch"
	[ -r "$kernel" ] || { fail "$run: no $kernel"; continue; }
	rm -f "$RUN/$run".*
	mkdir -p "$OUT/$run"
	# shellcheck disable=SC2086 # $machine is words
	$machine -accel tcg -nodefaults -kernel "$kernel" -append "console=$console wisp=shell" \
		-audiodev dbus,id=snd0,out.frequency=48000 -display "$display" $extra \
		-serial "unix:$RUN/$run.serial,server=on,wait=off" -qmp "unix:$RUN/$run.qmp,server=on,wait=off" \
		-S -daemonize -pidfile "$RUN/$run.pid" > "$OUT/$run/qemu.log" 2>&1 || {
		cat "$OUT/$run/qemu.log"
		fail "$run: QEMU didn't start"
		continue
	}
	if python3 -I "$SRC/packages/wsh-gst-qemu-dbus/tests/stream_test.py" --arch "$arch" --name "$run" \
		--serial "$RUN/$run.serial" --qmp "$RUN/$run.qmp" --address "unix:path=$BUS" \
		--outdir "$OUT/$run" --user "$USER_NAME" --expect "$expect" --mouse "$mouse" \
		--shared-map "$shared"; then
		:
	else
		failed=1
	fi
	cat "$OUT/$run/summary.txt" >> "$OUT/summary.txt" 2> /dev/null || true
	# the frames were only for the comparison (frame.ppm keeps the one compared)
	rm -rf "$OUT/$run/frames"
	pid=$(cat "$RUN/$run.pid" 2> /dev/null || true)
	if [ -n "$pid" ] && kill -0 "$pid" 2> /dev/null; then
		kill "$pid" 2> /dev/null || true
	fi
done

kill "$bus_pid" 2> /dev/null || true
step "Summary"
cat "$OUT/summary.txt"
if [ "$failed" = 0 ] && ! grep -q '^FAIL' "$OUT/summary.txt"; then
	echo "test.sh: all checks passed"
	exit 0
fi
echo "test.sh: some checks failed" >&2
exit 1
