#!/bin/sh
# The wsh-qemu-rdp package end to end in a throwaway Debian 13 container (as root), no GPU and no
# systemd: what wsh-qemu-rdp@<vmid>.service does, by hand, against the published pve-qemu-kvm.
#
#   docker run --rm -v "$PWD:/src:ro" -v "$PWD/build/wsh-qemu-rdp:/deb:ro" -v "$KERNELS:/kernels:ro" \
#     -v "$OUT:/out" debian:trixie sh /src/packages/wsh-qemu-rdp/test.sh /deb/wsh-qemu-rdp_<version>_amd64.deb /out
#
#   1. Installs the package (and pve-qemu-kvm from the apt repository, Xvfb, FreeRDP 3, xdotool,
#      ImageMagick) and checks it: qemu-rdp --version names the pinned commit, the user
#      wsh-qemu-rdp is in the group wsh-display, systemd-analyze verifies the unit.
#   2. Starts a VM's D-Bus display bus as wsh-dbus-display@100.service would: dbus-daemon, as root
#      with the group wsh-display, with qemu-server's policy (src/usr/dbus-display.conf, taken from
#      submodules/qemu-server.patch), on /run/wsh-dbus-display/100.sock.
#   3. For each guest in ARCHES (default "x86_64 sparc32"): QEMU as qemu-server starts it (root,
#      -display dbus with the audio driver dbus at 48 kHz; x86_64: pc, std VGA, AC97, PS/2 mouse;
#      sparc32: the SS-5, cg3, its CS4231) with wisp's framebuffer kernel (KERNELS/kernel-fb-<arch>,
#      from the wisp-fb release), paused, with QEMU's input events traced; `wsh-qemu-rdp-unit
#      prepare 100` (which writes /etc/wsh-qemu-rdp/100.conf with a generated password and makes
#      the node's certificate), then `wsh-qemu-rdp-unit run 100` as wsh-qemu-rdp:wsh-display; it
#      must listen on 127.0.0.1 only. tests/rdp_test.py then connects FreeRDP (sound into a
#      PulseAudio null sink), starts the guest and checks the login (x86_64), the picture, the
#      resize at the guest's mode changes (x86_64; cg3 has one mode), keyboard, mouse and sound.
#   4. qemu-rdp ends by itself when QEMU leaves the bus.
#
# OUTDIR gets summary.txt, each guest's serial log, qemu-rdp's and FreeRDP's logs, QEMU's
# screendump and the client's picture (PPM), and the rdpsnd stream FreeRDP played (WAV). Exit 0 when
# every check passes.
set -eu
DEB=${1:?usage: test.sh WSH-QEMU-RDP-DEB OUTDIR}
OUT=${2:?usage: test.sh WSH-QEMU-RDP-DEB OUTDIR}
SRC=${SRC:-/src}
KERNELS=${KERNELS:-/kernels}
ARCHES=${ARCHES:-x86_64 sparc32}
VMID=100
PORT=$((20000 + VMID))
UNIT=/usr/lib/wsh-qemu-rdp/wsh-qemu-rdp-unit
BUS=/run/wsh-dbus-display/$VMID.sock
RUN=/run/rdp-test
export DEBIAN_FRONTEND=noninteractive
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL $*" | tee -a "$OUT/summary.txt"; failed=1; }
pass() { echo "PASS $*" | tee -a "$OUT/summary.txt"; }
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
apt-get install --no-install-recommends --assume-yes -qq "$DEB" pve-qemu-kvm dbus xvfb freerdp3-x11 \
	xdotool imagemagick python3 iproute2 systemd pulseaudio pulseaudio-utils > /dev/null
dpkg-query -W -f '${Package} ${Version}\n' wsh-qemu-rdp pve-qemu-kvm freerdp3-x11 | tee "$OUT/versions.txt"

step "Package"
commit=$(sed -n 's/^QEMU_DISPLAY_COMMIT=//p' "$SRC/packages/wsh-qemu-rdp/upstream.env")
qemu-rdp --version | tee "$OUT/qemu-rdp-version.txt"
if grep -q "Git commit: $(printf %.10s "$commit")" "$OUT/qemu-rdp-version.txt"; then
	pass "version: qemu-rdp --version names the pinned commit"
else
	fail "version: qemu-rdp --version doesn't name $commit"
fi
if id -nG wsh-qemu-rdp | grep -qw wsh-display; then
	pass "user: wsh-qemu-rdp is in wsh-display ($(id wsh-qemu-rdp))"
else
	fail "user: wsh-qemu-rdp isn't in wsh-display ($(id wsh-qemu-rdp 2>&1))"
fi
# qemu-server's bus unit, which the unit binds to, from the patch (no qemu-server here)
extract() {
	awk -v f="+++ b/$1" '$0 == f { on = 1; next } on && /^diff --git / { exit } on && /^@@/ { next }
		on { sub(/^\+/, ""); print }' "$SRC/submodules/qemu-server.patch"
}
[ -e /usr/lib/systemd/system/wsh-dbus-display@.service ] ||
	extract src/usr/wsh-dbus-display@.service > /usr/lib/systemd/system/wsh-dbus-display@.service
mkdir -p /usr/share/qemu-server
[ -e /usr/share/qemu-server/dbus-display.conf ] ||
	extract src/usr/dbus-display.conf > /usr/share/qemu-server/dbus-display.conf
if out=$(systemd-analyze verify --man=no "/usr/lib/systemd/system/wsh-qemu-rdp@.service" 2>&1) &&
	! printf '%s' "$out" | grep -q 'wsh-qemu-rdp'; then
	pass "unit: systemd-analyze verify wsh-qemu-rdp@.service"
else
	printf '%s\n' "$out"
	fail "unit: systemd-analyze verify wsh-qemu-rdp@.service"
fi

step "The VM's bus (as wsh-dbus-display@$VMID.service)"
install -d -m 0750 -g wsh-display /run/wsh-dbus-display
setpriv --regid=wsh-display --clear-groups dbus-daemon --nofork --nopidfile \
	--config-file=/usr/share/qemu-server/dbus-display.conf --address="unix:path=$BUS" &
bus_pid=$!
for _ in $(seq 50); do [ -S "$BUS" ] && break; sleep 0.1; done
[ -S "$BUS" ] || { fail "bus: no socket"; exit 1; }

Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp > "$OUT/xvfb.log" 2>&1 &
xvfb_pid=$!
# FreeRDP's sound goes to a null sink, the default; rdp_test.py records its monitor
pulseaudio -D --exit-idle-time=-1 --disallow-exit -n --load=module-native-protocol-unix \
	--load="module-null-sink sink_name=rdp" 2> "$OUT/pulseaudio.log"
pactl set-default-sink rdp

for arch in $ARCHES; do
	step "QEMU: $arch"
	case $arch in
	x86_64) machine="qemu-system-x86_64 -M pc -vga std -device AC97,audiodev=snd0" ;;
	sparc32) machine="qemu-system-sparc -M SS-5 -vga cg3 -machine audiodev=snd0" ;;
	*) echo "unknown arch $arch" >&2; exit 2 ;;
	esac
	kernel="$KERNELS/kernel-fb-$arch"
	[ -r "$kernel" ] || { fail "$arch: no $kernel"; continue; }
	rm -f "$RUN/$arch".*
	# shellcheck disable=SC2086 # $machine is words
	$machine -accel tcg -m 128 -nodefaults -kernel "$kernel" -append "console=ttyS0 wisp=shell" \
		-audiodev dbus,id=snd0,out.frequency=48000 -display "dbus,addr=unix:path=$BUS,audiodev=snd0" \
		-serial "unix:$RUN/$arch.serial,server=on,wait=off" -qmp "unix:$RUN/$arch.qmp,server=on,wait=off" \
		-trace "enable=input_event_*,file=$OUT/trace-$arch.log" \
		-S -daemonize -pidfile "$RUN/$arch.pid" > "$OUT/qemu-$arch.log" 2>&1 || {
		cat "$OUT/qemu-$arch.log"
		fail "$arch: QEMU didn't start"
		continue
	}

	step "qemu-rdp: $arch"
	conf=/etc/wsh-qemu-rdp/$VMID.conf
	rm -rf "/run/wsh-qemu-rdp/$VMID"
	install -d -o wsh-qemu-rdp -m 0700 "/run/wsh-qemu-rdp/$VMID"
	first=0
	[ -e "$conf" ] || first=1
	"$UNIT" prepare "$VMID"
	if [ "$first" = 1 ]; then
		perms=$(stat -c '%a %U' "$conf")
		key=$(stat -c '%a %U' /var/lib/wsh-qemu-rdp/key.pem)
		if [ "$perms" = "600 root" ] && [ "$key" = "600 root" ] && grep -q "^PORT=$PORT$" "$conf" &&
			grep -q '^LISTEN=127.0.0.1$' "$conf" && grep -Eq '^RDP_PASSWORD=[A-Za-z0-9]{24}$' "$conf"; then
			pass "prepare: $conf ($perms) with 127.0.0.1:$PORT and a generated password; node key $key"
		else
			fail "prepare: $conf is $perms, the key $key"
			cat "$conf"
		fi
		echo "LOG=info" >> "$conf"
		"$UNIT" prepare "$VMID"
	fi
	setpriv --reuid=wsh-qemu-rdp --regid=wsh-display --init-groups "$UNIT" run "$VMID" \
		> "$OUT/qemu-rdp-$arch.log" 2>&1 &
	rdp_pid=$!
	listening=
	for _ in $(seq 100); do
		listening=$(ss -Hltn "sport = :$PORT" | awk '{ print $4 }')
		[ -n "$listening" ] && break
		sleep 0.2
	done
	if [ "$listening" = "127.0.0.1:$PORT" ]; then
		pass "$arch: qemu-rdp listens on $listening only, as wsh-qemu-rdp ($(ps -o user=,group= -p "$rdp_pid" 2>/dev/null || true))"
	else
		fail "$arch: qemu-rdp listens on '${listening:-nothing}'"
		cat "$OUT/qemu-rdp-$arch.log"
		kill "$rdp_pid" 2> /dev/null || true
		continue
	fi

	# the login once; cg3 has one mode, so no resize on the SS-5
	skip=
	[ "$arch" = x86_64 ] || skip=auth,resize
	password=$(sed -n 's/^RDP_PASSWORD=//p' "$conf" | tail -n 1)
	mkdir -p "$OUT/$arch"
	if python3 -I "$SRC/packages/wsh-qemu-rdp/tests/rdp_test.py" --arch "$arch" --serial "$RUN/$arch.serial" \
		--qmp "$RUN/$arch.qmp" --port "$PORT" --user rdp --password "$password" --outdir "$OUT/$arch" \
		--display :99 --skip "$skip" --input-trace "$OUT/trace-$arch.log"; then
		:
	else
		failed=1
	fi
	cat "$OUT/$arch/summary.txt" >> "$OUT/summary.txt" 2> /dev/null || true

	# QEMU leaves the bus: qemu-rdp ends by itself
	python3 -I -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.recv(4096)
s.sendall(b"{\"execute\":\"qmp_capabilities\"}\n{\"execute\":\"quit\"}\n"); s.recv(4096)' "$RUN/$arch.qmp" || true
	gone=
	for _ in $(seq 50); do
		kill -0 "$rdp_pid" 2> /dev/null || { gone=1; break; }
		sleep 0.2
	done
	if [ -n "$gone" ]; then
		pass "$arch: qemu-rdp ended when QEMU left the bus"
	else
		fail "$arch: qemu-rdp still runs 10 s after QEMU quit"
		kill "$rdp_pid" 2> /dev/null || true
	fi
	grep -h "Can't own\|RDP server ended\|rror" "$OUT/qemu-rdp-$arch.log" | head -5 || true
done

kill "$xvfb_pid" "$bus_pid" 2> /dev/null || true
step "Summary"
cat "$OUT/summary.txt"
if [ "$failed" = 0 ] && ! grep -q '^FAIL' "$OUT/summary.txt"; then
	echo "test.sh: all checks passed"
	exit 0
fi
echo "test.sh: some checks failed" >&2
exit 1
