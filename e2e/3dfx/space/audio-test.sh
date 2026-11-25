#!/bin/sh
# wshspace -audiotest on Linux: the audio signature (e2e/wisp/audiosig.h) through the game's own OSS
# /dev/dsp backend, recorded by QEMU's `-audiodev wav` and checked by e2e/audio/wavcheck.py
# --signature (per segment and channel the frequency, the duration, no gaps, channels not swapped).
# In a throwaway Debian 13 container, as root, like e2e/3dfx/test.sh:
#
#   docker run --rm -v "$PWD:/src:ro" -v "$OUT:/out" debian:trixie sh /src/e2e/3dfx/space/audio-test.sh /out
#
# The guest is test.sh's demo guest with sound: Debian's kernel (amd64, which runs the i386 binary
# through its IA32 emulation) and an initramfs with wshspace's Linux build (build-linux.sh), the
# Linux guest Glide library (scripts/build-3dfx-linux-glide.sh: wshspace links libglide.so.2, but
# -audiotest opens no display, so the plain qemu-system-x86_64 runs it), Debian's i386 loader and
# libc, busybox, amixer and the sound modules (AC97: snd-intel8x0, with snd-pcm-oss for /dev/dsp).
# /init loads them, unmutes the card (ALSA starts AC97 muted), runs `wshspace -audiotest` and
# powers off. QEMU is the published pve-qemu-kvm's, with `-device AC97`.
#
# OUTDIR gets space-audio.wav, space-audio.json (wavcheck's result), serial.log and qemu.log.
# QEMU_BIN tests another qemu-system-x86_64. Exit 0 when wshspace says PASS and wavcheck finds the
# signature. Copyright 2026 WsHosting ENK, GPL-3.
set -eu
OUT=${1:?usage: audio-test.sh OUTDIR}
SRC=${SRC:-/src}
TIMEOUT=${TIMEOUT:-120}
export DEBIAN_FRONTEND=noninteractive
fail() { echo "FAIL: $*" >&2; exit 1; }
mkdir -p "$OUT"

echo "== packages: pve-qemu-kvm (published), Debian's kernel, busybox, alsa-utils, i386 gcc"
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
apt-get install --no-install-recommends --assume-yes -qq pve-qemu-kvm linux-image-amd64 busybox-static alsa-utils \
	kmod cpio xz-utils zstd gcc gcc-multilib libc6-dev-i386 binutils python3 > /dev/null
dpkg-query -W -f '${Package} ${Version}\n' pve-qemu-kvm
QEMU=${QEMU_BIN:-/usr/bin/qemu-system-x86_64}

echo "== wshspace and the guest"
work=$(mktemp -d)
trap 'rm -rf "$work"; chmod -R a+rX "$OUT" 2> /dev/null || true' EXIT
bash "$SRC/scripts/build-3dfx-linux-glide.sh" "$SRC/submodules/qemu-3dfx" 0000000 "$work/linux-glide" > /dev/null
bash "$SRC/e2e/3dfx/space/build-linux.sh" "$work/bin" "$work/linux-glide"
r=$work/root
mkdir -p "$r/bin" "$r/usr/lib" "$r/etc" "$r/mods/ko" "$r/usr/share" "$r/tmp"
cp "$work/bin/wshspace" "$r/wshspace"
cp -P "$work/linux-glide/libglide.so.2" "$work/linux-glide/libglide2x.so" "$r/usr/lib/"
interp=$(readelf -lW "$r/wshspace" | sed -n 's/.*Requesting program interpreter: \(.*\)]$/\1/p')
mkdir -p "$r$(dirname "$interp")"
cp -L "$interp" "$r$interp"
cp -L "$(gcc -m32 -print-file-name=libc.so.6)" "$r/usr/lib/libc.so.6"
echo /usr/lib > "$r/etc/ld.so.conf"
ldconfig -r "$r"
cp /bin/busybox "$r/bin/busybox"
# amixer (amd64) with its libraries at their own paths, and ALSA's configuration
cp /usr/bin/amixer "$r/bin/amixer"
for lib in $(ldd /usr/bin/amixer | grep -o '/[^ ]*'); do
	mkdir -p "$r$(dirname "$lib")"
	cp -L "$lib" "$r$lib"
done
cp -r /usr/share/alsa "$r/usr/share/alsa"
# the modules in load order (modprobe --show-depends), decompressed for busybox insmod
kver=$(ls /lib/modules | head -n 1)
: > "$r/mods/list"
for top in snd-intel8x0 snd-pcm-oss; do
	modprobe -S "$kver" --show-depends "$top" | while read -r kind path rest; do
		[ "$kind" = insmod ] || continue
		name=$(basename "$path")
		name=${name%.xz}
		name=${name%.zst}
		[ ! -f "$r/mods/ko/$name" ] || continue
		case "$path" in
		*.xz) xz -dc "$path" > "$r/mods/ko/$name" ;;
		*.zst) zstd -dc "$path" > "$r/mods/ko/$name" ;;
		*) cp "$path" "$r/mods/ko/$name" ;;
		esac
		echo "/mods/ko/$name $rest" >> "$r/mods/list"
	done
done
cat > "$r/init" << 'EOF'
#!/bin/busybox sh
/bin/busybox --install -s /bin
export PATH=/bin
mkdir -p /proc /sys /dev
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
while read -r ko args; do
	insmod "$ko" $args 2> /dev/null || echo "audio-test: insmod failed: $ko"
done < /mods/list
i=0
while [ ! -e /dev/dsp ] && [ $i -lt 50 ]; do sleep 0.2; i=$((i + 1)); done
cat /proc/asound/cards
amixer -c 0 scontrols | sed -n "s/^Simple mixer control '\(.*\)',\([0-9]*\)$/\1,\2/p" > /tmp/controls
while read -r ctl; do amixer -q -c 0 sset "$ctl" 80% unmute 2> /dev/null; done < /tmp/controls
echo "audio-test: /dev/dsp $(ls -l /dev/dsp 2>&1)"
/wshspace -audiotest
echo "audio-test: wshspace exit $?"
sync
poweroff -f
EOF
chmod 755 "$r/init"
(cd "$r" && find . | cpio -o -H newc --quiet | gzip -1) > "$work/initrd.gz"
kernel=/boot/vmlinuz-$kver
echo "kernel $kernel, initrd $(wc -c < "$work/initrd.gz") bytes, wshspace $(wc -c < "$r/wshspace") bytes"

accel=tcg
[ ! -w /dev/kvm ] || accel=kvm
echo "== QEMU ($accel): AC97 to $OUT/space-audio.wav"
rm -f "$OUT/space-audio.wav"
status=0
timeout "$TIMEOUT" "$QEMU" -machine pc -accel "$accel" -m 256 -nodefaults -vga none -display none -no-reboot \
	-kernel "$kernel" -initrd "$work/initrd.gz" -serial "file:$OUT/serial.log" \
	-append "console=ttyS0 rdinit=/init panic=-1 quiet" \
	-device AC97,audiodev=snd0 -audiodev "wav,id=snd0,path=$OUT/space-audio.wav" > "$OUT/qemu.log" 2>&1 || status=$?
tr -d '\r' < "$OUT/serial.log" | grep -E '^(WSHSPACE|audio-test):' || true
[ "$status" = 0 ] || fail "QEMU exited with $status (124: the $TIMEOUT s timeout)"
tr -d '\r' < "$OUT/serial.log" | grep -qx 'WSHSPACE: PASS' || fail "wshspace didn't say PASS"
python3 "$SRC/e2e/audio/wavcheck.py" "$OUT/space-audio.wav" --signature > "$OUT/space-audio.json" || status=$?
python3 - "$OUT/space-audio.json" << 'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
for s in r["signatures"]:
    print("signature: %.3f s from %.3f s, longest gap %s ms, left %s Hz, right %s Hz%s" % (
        s["duration_s"], s["start_s"], max(s["max_gap_ms"]), [g["left_hz"] for g in s["segments"]],
        [g["right_hz"] for g in s["segments"]], ", tail %s" % s["tail"] if s.get("tail") else ""))
print("wavcheck:", "ok" if r["ok"] else "; ".join(r["reasons"]))
EOF
[ "$status" = 0 ] || fail "wavcheck: the signature isn't right (see $OUT/space-audio.json)"
echo "PASS: wshspace -audiotest (OSS, AC97)"
