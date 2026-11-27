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
#   3. For each run in RUNS (default "x86_64 aarch64 x86_64-gl x86_64-egl sparc32"): QEMU paused
#      with wisp's framebuffer kernel (KERNELS/kernel-fb-<arch>, from the wisp-fb release),
#      -display dbus and the audio driver dbus at 48 kHz, as qemu-server starts it;
#      tests/stream_test.py runs the pipelines and the bridge and checks the picture, the keyboard,
#      the mouse, the sound and the end of stream:
#        x86_64     pc, std VGA, AC97, PS/2 mouse (relative): the picture through the shared map
#        aarch64    virt, bochs-display, AC97, virtio keyboard and tablet (absolute):
#                   shared-map=false, so the pixels come in Scanout/Update
#        x86_64-gl  as x86_64 with qemu-system-x86_64-3dfx and -display dbus,gl=on (Mesa's
#                   llvmpipe through /dev/udmabuf): the picture as dmabufs, read before each
#                   UpdateDMABUF is answered; skipped without /dev/udmabuf
#        x86_64-egl as x86_64-gl, with qemudbussrc dmabuf-import=egl: every dmabuf read through
#                   EGL (Mesa's software device), the way it reads a GPU's tiled dmabufs
#        sparc32    SS-5, cg3, CS4231, Sun keyboard and mouse (relative): the shared map
#   4. Reconnect (needs KERNELS/kernel-fb-x86_64): VM 102 stopped and started again with its bus,
#      as qemu-server does: qemudbussrc and qemudbusaudiosrc with reconnect=true start before the
#      VM, keep running while it is stopped and listen to its next run (new frames come);
#      qemu-dbus-input prints "closed" and exits 3 when the VM stops.
#   5. An unprivileged container's client: VM 101's bus with 'dbus-display-uids: 100000', set up by
#      qemu-server's PVE::QemuServer::DBusDisplay (from the patch): qemu-dbus-input, qemudbussrc and
#      qemudbusaudiosrc run as root of a user namespace whose root is the host's uid 100000 (unshare;
#      needs docker run --security-opt seccomp=unconfined, else skipped) and get in; uid 200000,
#      uid 100000 on VM 100's bus and a node user outside wsh-display are refused.
#
# OUTDIR gets summary.txt, and per run the serial log, QEMU's screendump, the newest frame as PPM,
# the WAV the audio pipeline wrote and the logs of the pipelines and the bridge. Exit 0 when every
# check passes.
set -eu
DEB=${1:?usage: test.sh WSH-GST-QEMU-DBUS-DEB OUTDIR}
OUT=${2:?usage: test.sh WSH-GST-QEMU-DBUS-DEB OUTDIR}
SRC=${SRC:-/src}
KERNELS=${KERNELS:-/kernels}
RUNS=${RUNS:-x86_64 aarch64 x86_64-gl x86_64-egl sparc32}
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
	libegl1 libegl-mesa0 libgl1-mesa-dri acl > /dev/null
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
	import=auto
	case $run in
	x86_64)
		arch=x86_64
		machine="qemu-system-x86_64 -M pc -m 128 -vga std -device AC97,audiodev=snd0"
		console=ttyS0
		;;
	x86_64-gl | x86_64-egl)
		arch=x86_64
		[ "$run" = x86_64-gl ] || import=egl
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
		--shared-map "$shared" --dmabuf-import "$import"; then
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

step "Reconnect: the VM stopped and started again (reconnect=true)"
# As qemu-server does it: the VM's bus starts before QEMU and stops with it, on the same socket
# path each run. The clients start before the VM's first run and must follow it through a stop
# and a start: qemudbussrc and qemudbusaudiosrc with reconnect=true keep running and listen to
# the next run, qemu-dbus-input exits 3 ("closed") when the VM stops.
RVMID=102
RBUS=/run/wsh-dbus-display/$RVMID.sock
ROUT=$OUT/reconnect
# run as the streaming user; not a function, so that $! of a background job is the process itself
AS_STREAMER="setpriv --reuid=$USER_NAME --regid=$USER_NAME --init-groups"
rvm_start() { # the bus, then QEMU (wisp's x86_64 framebuffer kernel, std VGA, AC97)
	setpriv --regid=wsh-display --clear-groups dbus-daemon --nofork --nopidfile \
		--config-file=/usr/share/qemu-server/dbus-display.conf --address="unix:path=$RBUS" &
	rbus_pid=$!
	for _ in $(seq 50); do [ -S "$RBUS" ] && break; sleep 0.1; done
	qemu-system-x86_64 -M pc -m 128 -vga std -device AC97,audiodev=snd0 -accel tcg -nodefaults \
		-kernel "$KERNELS/kernel-fb-x86_64" -append "console=ttyS0 wisp=shell" \
		-audiodev dbus,id=snd0,out.frequency=48000 -display "dbus,addr=unix:path=$RBUS,audiodev=snd0" \
		-serial null -daemonize -pidfile "$RUN/reconnect.pid" >> "$ROUT/qemu.log" 2>&1
}
rvm_stop() { # QEMU, then its bus
	pid=$(cat "$RUN/reconnect.pid" 2> /dev/null || true)
	if [ -n "$pid" ]; then
		kill "$pid" 2> /dev/null || true
		for _ in $(seq 50); do kill -0 "$pid" 2> /dev/null || break; sleep 0.1; done
	fi
	kill "$rbus_pid" 2> /dev/null || true
	wait "$rbus_pid" 2> /dev/null || true
	rm -f "$RBUS" "$RUN/reconnect.pid"
}
count() { grep -c -e "$1" "$2" 2> /dev/null || true; }
wait_count() { # PATTERN FILE N SECONDS: until FILE has N lines with PATTERN
	for _ in $(seq $(($4 * 10))); do
		[ "$(count "$1" "$2")" -ge "$3" ] && return 0
		sleep 0.1
	done
	return 1
}
newest_after() { # DIR STAMP: a frame in DIR newer than STAMP
	[ -n "$(find "$1" -name 'f*.rgb' -newer "$2" 2> /dev/null | head -n 1)" ]
}
if [ ! -r "$KERNELS/kernel-fb-x86_64" ]; then
	skip "reconnect: no $KERNELS/kernel-fb-x86_64"
else
	mkdir -p "$ROUT/frames"
	chown -R "$USER_NAME" "$ROUT"
	rm -f "$RBUS"
	$AS_STREAMER env GST_DEBUG=qemudbussrc:4 GST_DEBUG_NO_COLOR=1 gst-launch-1.0 -e qemudbussrc \
		address="unix:path=$RBUS" reconnect=true ! videoconvert ! video/x-raw,format=RGB ! \
		multifilesink location="$ROUT/frames/f%06d.rgb" max-files=5 > "$ROUT/video.log" 2>&1 &
	rvideo=$!
	$AS_STREAMER env GST_DEBUG=qemudbusaudiosrc:4 GST_DEBUG_NO_COLOR=1 gst-launch-1.0 -e \
		qemudbusaudiosrc address="unix:path=$RBUS" reconnect=true ! fakesink > "$ROUT/audio.log" 2>&1 &
	raudio=$!
	if wait_count "waiting for the VM" "$ROUT/video.log" 1 15 && wait_count "waiting for the VM" "$ROUT/audio.log" 1 15 &&
		kill -0 "$rvideo" 2> /dev/null && kill -0 "$raudio" 2> /dev/null; then
		pass "reconnect: qemudbussrc and qemudbusaudiosrc start before the VM runs and wait for it"
	else
		fail "reconnect: the elements didn't wait for the VM (see reconnect/video.log, audio.log)"
	fi
	rvm_start || fail "reconnect: QEMU didn't start (see reconnect/qemu.log)"
	if wait_count "listening on .* again" "$ROUT/video.log" 1 30 && wait_count "listening on .* again" "$ROUT/audio.log" 1 30 &&
		sleep 3 && [ -n "$(ls "$ROUT/frames")" ]; then
		pass "reconnect: both listen to the VM's first run, frames come"
	else
		fail "reconnect: no listener on the first run, or no frame (see reconnect/video.log, audio.log)"
	fi
	mkfifo "$ROUT/input.fifo"
	chown "$USER_NAME" "$ROUT/input.fifo"
	(
		rc=0
		$AS_STREAMER qemu-dbus-input --address "unix:path=$RBUS" < "$ROUT/input.fifo" > "$ROUT/input.log" 2>&1 || rc=$?
		echo "$rc" > "$ROUT/input.rc"
	) &
	exec 9> "$ROUT/input.fifo"
	wait_count "^ready" "$ROUT/input.log" 1 15 || fail "reconnect: qemu-dbus-input didn't connect (see reconnect/input.log)"
	rvm_stop
	for _ in $(seq 100); do [ -s "$ROUT/input.rc" ] && break; sleep 0.1; done
	if [ "$(cat "$ROUT/input.rc" 2> /dev/null)" = 3 ] && grep -q '^closed$' "$ROUT/input.log"; then
		pass "reconnect: qemu-dbus-input printed 'closed' and exited 3 when the VM stopped"
	else
		fail "reconnect: qemu-dbus-input exit '$(cat "$ROUT/input.rc" 2> /dev/null)' after the VM stopped (see reconnect/input.log)"
	fi
	exec 9>&-
	sleep 3
	if kill -0 "$rvideo" 2> /dev/null && kill -0 "$raudio" 2> /dev/null &&
		wait_count "waiting for the VM to run again" "$ROUT/video.log" 1 1 &&
		wait_count "waiting for the VM to run again" "$ROUT/audio.log" 1 1; then
		pass "reconnect: both elements kept running (no EOS) while the VM was stopped"
	else
		fail "reconnect: an element ended when the VM stopped (see reconnect/video.log, audio.log)"
	fi
	touch "$ROUT/restart.stamp"
	sleep 1
	rvm_start || fail "reconnect: QEMU didn't start (see reconnect/qemu.log)"
	if wait_count "listening on .* again" "$ROUT/video.log" 2 30 && wait_count "listening on .* again" "$ROUT/audio.log" 2 30; then
		ok=
		for _ in $(seq 150); do newest_after "$ROUT/frames" "$ROUT/restart.stamp" && ok=1 && break; sleep 0.1; done
		if [ -n "$ok" ]; then
			pass "reconnect: both listen to the VM's next run, and its frames come"
		else
			fail "reconnect: listening to the next run, but no new frame (see reconnect/video.log)"
		fi
	else
		fail "reconnect: no listener on the VM's next run (see reconnect/video.log, audio.log)"
	fi
	for p in $rvideo $raudio; do kill -INT "$p" 2> /dev/null || true; done
	rc_v=0
	rc_a=0
	wait "$rvideo" || rc_v=$?
	wait "$raudio" || rc_a=$?
	stats=$(grep -o 'stopped: .*' "$ROUT/video.log" | tail -n 1)
	if [ "$rc_v" = 0 ] && [ "$rc_a" = 0 ] && echo "$stats" | grep -q 'reconnects=2'; then
		pass "reconnect: both pipelines ended cleanly ($stats)"
	else
		fail "reconnect: pipelines exited $rc_v/$rc_a ($stats)"
	fi
	rvm_stop
	rm -rf "$ROUT/frames" "$ROUT/input.fifo"
fi

step "An unprivileged container (dbus-display-uids)"
# A client whose uid inside its user namespace (0) is the host's 100000, as in an unprivileged
# container, on the bus of VM $UVMID with 'dbus-display-uids: 100000'. qemu-server's own code
# (PVE::QemuServer::DBusDisplay from the patch, with a stand-in for PVE::Tools) writes the VM's bus
# configuration, adds the user for the uid and the directory's ACL entry; dbus-daemon reads that
# configuration, as wsh-dbus-display@<vmid>.service does.
UVMID=101
UBUS=/run/wsh-dbus-display/$UVMID.sock
userns() { # OUTER-UID COMMAND...: COMMAND as root of a user namespace whose root is OUTER-UID
	outer=$1
	shift
	unshare -U --map-users="0:$outer:65536" --map-groups="0:$outer:65536" --setuid 0 --setgid 0 "$@"
}
if [ ! -r "$KERNELS/kernel-fb-x86_64" ]; then
	skip "unprivileged container: no $KERNELS/kernel-fb-x86_64"
elif ! userns 100000 true 2> "$OUT/userns.log"; then
	skip "unprivileged container: no user namespaces here ($(cat "$OUT/userns.log"); docker run --security-opt seccomp=unconfined)"
else
	mkdir -p "$RUN/perl/PVE/QemuServer" /run/qemu-server "$OUT/userns"
	extract src/PVE/QemuServer/DBusDisplay.pm > "$RUN/perl/PVE/QemuServer/DBusDisplay.pm"
	cat > "$RUN/perl/PVE/Tools.pm" << 'EOF'
package PVE::Tools;
# the three subs of PVE::Tools that PVE::QemuServer::DBusDisplay uses
use strict;
use warnings;
use base 'Exporter';
our @EXPORT_OK = qw(run_command file_set_contents lock_file);
sub run_command {
    my ($cmd, %param) = @_;
    if (my $out = $param{outfunc}) {
        open(my $fh, '-|', @$cmd) or die "$cmd->[0]: $!\n";
        while (my $line = <$fh>) { chomp $line; $out->($line); }
        close($fh) or die "@$cmd failed\n";
    } else {
        system(@$cmd) == 0 or die "@$cmd failed\n";
    }
}
sub file_set_contents {
    my ($path, $data) = @_;
    open(my $fh, '>', $path) or die "$path: $!\n";
    print $fh $data;
    close($fh) or die "$path: $!\n";
}
sub lock_file {
    my ($path, $timeout, $code) = @_;
    eval { $code->() };
}
1;
EOF
	qsd() { perl -I"$RUN/perl" -MPVE::QemuServer::DBusDisplay -e "$1"; }
	qsd 'my $u = PVE::QemuServer::DBusDisplay::parse_uids("100000");
		PVE::QemuServer::DBusDisplay::ensure_users($u);
		PVE::Tools::file_set_contents(PVE::QemuServer::DBusDisplay::config_path('"$UVMID"'),
			PVE::QemuServer::DBusDisplay::bus_config($u));' || fail "unprivileged container: the bus configuration"
	cp "/run/qemu-server/$UVMID.dbus-display.conf" "$OUT/userns/"
	getent passwd 100000 > "$OUT/userns/passwd.txt" || true
	setpriv --regid=wsh-display --clear-groups dbus-daemon --nofork --nopidfile \
		--config-file="/run/qemu-server/$UVMID.dbus-display.conf" --address="unix:path=$UBUS" \
		2> "$OUT/userns/dbus-daemon.log" &
	ubus_pid=$!
	for _ in $(seq 50); do [ -S "$UBUS" ] && break; sleep 0.1; done
	qsd 'PVE::QemuServer::DBusDisplay::sync_dir_acl()' || fail "unprivileged container: the directory's ACL"
	getfacl --numeric /run/wsh-dbus-display > "$OUT/userns/acl.txt" 2>&1
	if grep -q '^user:100000:--x$' "$OUT/userns/acl.txt"; then
		pass "unprivileged container: uid 100000 has a user ($(cut -d: -f1 "$OUT/userns/passwd.txt")) and --x on /run/wsh-dbus-display"
	else
		fail "unprivileged container: no ACL entry for 100000 (see userns/acl.txt)"
	fi
	qemu-system-x86_64 -M pc -m 128 -vga std -device AC97,audiodev=snd0 -accel tcg -nodefaults \
		-kernel "$KERNELS/kernel-fb-x86_64" -append "console=ttyS0 wisp=shell" \
		-audiodev dbus,id=snd0,out.frequency=48000 -display "dbus,addr=unix:path=$UBUS,audiodev=snd0" \
		-serial null -daemonize -pidfile "$RUN/userns.pid" > "$OUT/userns/qemu.log" 2>&1 ||
		fail "unprivileged container: QEMU didn't start"
	export GST_REGISTRY=/tmp/gst-registry-userns.bin
	# the bus and a call on it (qemu-dbus-input), and the listener connections QEMU makes back
	# (qemudbussrc: a picture, qemudbusaudiosrc: its listener)
	if echo query | userns 100000 qemu-dbus-input --quiet --address "unix:path=$UBUS" \
		> "$OUT/userns/input.txt" 2>&1 && grep -q '^mode ' "$OUT/userns/input.txt"; then
		pass "unprivileged container: qemu-dbus-input as uid 100000: $(cat "$OUT/userns/input.txt")"
	else
		fail "unprivileged container: qemu-dbus-input as uid 100000 (see userns/input.txt)"
	fi
	if userns 100000 timeout 30 gst-launch-1.0 -q qemudbussrc address="unix:path=$UBUS" num-buffers=1 \
		! fakesink > "$OUT/userns/video.txt" 2>&1; then
		pass "unprivileged container: qemudbussrc as uid 100000 got a picture"
	else
		fail "unprivileged container: qemudbussrc as uid 100000 (see userns/video.txt)"
	fi
	# the guest plays nothing here: the listener registered (QEMU authenticated its connection) is
	# enough, then the pipeline is stopped
	userns 100000 env GST_DEBUG=qemudbusaudiosrc:4 timeout 5 gst-launch-1.0 -q qemudbusaudiosrc \
		address="unix:path=$UBUS" ! fakesink > "$OUT/userns/audio.txt" 2>&1 || true
	if grep -q 'listening on' "$OUT/userns/audio.txt"; then
		pass "unprivileged container: qemudbusaudiosrc as uid 100000 registered its listener"
	else
		fail "unprivileged container: qemudbusaudiosrc as uid 100000 (see userns/audio.txt)"
	fi
	# the others: another container's root (no ACL entry), the same uid on a VM's bus that doesn't
	# name it, a node user outside wsh-display
	refused() { # NAME LOG COMMAND...: passes when COMMAND fails
		name=$1
		log=$2
		shift 2
		if echo query | "$@" > "$OUT/userns/$log" 2>&1; then
			fail "unprivileged container: $name got in (see userns/$log)"
		else
			pass "unprivileged container: $name refused: $(tail -n 1 "$OUT/userns/$log")"
		fi
	}
	refused "uid 200000 (another container)" refused-200000.txt \
		userns 200000 qemu-dbus-input --quiet --timeout 2 --address "unix:path=$UBUS"
	refused "uid 100000 on VM $VMID's bus (no dbus-display-uids)" refused-other-vm.txt \
		userns 100000 qemu-dbus-input --quiet --timeout 2 --address "unix:path=$BUS"
	id outsider > /dev/null 2>&1 || useradd --system --no-create-home outsider
	refused "a node user outside wsh-display" refused-outsider.txt \
		setpriv --reuid=outsider --regid=outsider --init-groups \
		qemu-dbus-input --quiet --timeout 2 --address "unix:path=$UBUS"
	pid=$(cat "$RUN/userns.pid" 2> /dev/null || true)
	[ -z "$pid" ] || kill "$pid" 2> /dev/null || true
	kill "$ubus_pid" 2> /dev/null || true
	rm -f "/run/qemu-server/$UVMID.dbus-display.conf"
	qsd 'PVE::QemuServer::DBusDisplay::sync_dir_acl()' || fail "unprivileged container: the directory's ACL at the end"
	if getfacl --numeric /run/wsh-dbus-display 2>&1 | grep -q '^user:100000:'; then
		fail "unprivileged container: the ACL entry for 100000 stays after the VM's bus is gone"
	else
		pass "unprivileged container: the ACL entry goes with the VM's bus"
	fi
fi

kill "$bus_pid" 2> /dev/null || true
step "Summary"
cat "$OUT/summary.txt"
if [ "$failed" = 0 ] && ! grep -q '^FAIL' "$OUT/summary.txt"; then
	echo "test.sh: all checks passed"
	exit 0
fi
echo "test.sh: some checks failed" >&2
exit 1
