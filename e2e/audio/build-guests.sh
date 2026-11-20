#!/bin/sh
# Builds the guests of the x86 audio matrix into $1 (the build stage of e2e/audio/Dockerfile), from
# Debian packages and this directory only:
#
#   AUDTEST.COM   the DOS test program (audtest.asm, nasm); the matrix puts it on a FreeDOS boot floppy
#   vmlinuz       Debian's kernel (linux-image-amd64)
#   initrd.gz     busybox, aplay and amixer with their libraries, the sound modules and guest-init.sh as /init
#   tone.wav      the tone the Linux guest plays (660 Hz, 1.5 s, 48 kHz, 16-bit stereo), also in initrd
#   versions.txt  what went in
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$1
mkdir -p "$out"

nasm -f bin -o "$out/AUDTEST.COM" "$here/audtest.asm"

python3 - "$out/tone.wav" <<'EOF'
import math, struct, sys, wave
rate, freq, secs = 48000, 660, 1.5
n = int(rate * secs)
frames = bytearray()
for i in range(n):
    v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
    frames += struct.pack("<hh", v, v)
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(bytes(frames))
EOF

kver=$(ls /lib/modules | head -n 1)
cp "/boot/vmlinuz-$kver" "$out/vmlinuz"

root=$(mktemp -d)
mkdir -p "$root/bin" "$root/proc" "$root/sys" "$root/dev" "$root/mods/ko" "$root/usr/share"
cp /bin/busybox "$root/bin/busybox"
cp "$here/guest-init.sh" "$root/init"
chmod 755 "$root/init"
cp "$out/tone.wav" "$root/tone.wav"

# aplay, amixer and the shared libraries they need, at their own paths
mkdir -p "$root/tmp"
for prog in aplay amixer; do
    cp "/usr/bin/$prog" "$root/bin/$prog"
    for lib in $(ldd "/usr/bin/$prog" | grep -o '/[^ ]*'); do
        mkdir -p "$root$(dirname "$lib")"
        cp -L "$lib" "$root$lib"
    done
done
cp -r /usr/share/alsa "$root/usr/share/alsa"

# One load list per top-level module: its dependencies first (modprobe --show-depends), each module
# decompressed so busybox insmod can load it
for top in snd-intel8x0 snd-ens1370 snd-hda-codec-generic snd-hda-intel virtio_snd xhci-pci snd-usb-audio; do
    : > "$root/mods/$top.list"
    modprobe -S "$kver" --show-depends "$top" | while read -r kind path rest; do
        [ "$kind" = insmod ] || continue
        name=$(basename "$path")
        name=${name%.xz}
        name=${name%.zst}
        if [ ! -f "$root/mods/ko/$name" ]; then
            case "$path" in
                *.xz) xz -dc "$path" > "$root/mods/ko/$name" ;;
                *.zst) zstd -dc "$path" > "$root/mods/ko/$name" ;;
                *) cp "$path" "$root/mods/ko/$name" ;;
            esac
        fi
        echo "/mods/ko/$name $rest" >> "$root/mods/$top.list"
    done
done

(cd "$root" && find . | cpio -o -H newc --quiet | gzip -9) > "$out/initrd.gz"
rm -rf "$root"

{
    echo "kernel: $kver ($(dpkg-query -W -f '${Version}' "linux-image-$kver"))"
    echo "busybox-static: $(dpkg-query -W -f '${Version}' busybox-static)"
    echo "alsa-utils: $(dpkg-query -W -f '${Version}' alsa-utils)"
    echo "nasm: $(dpkg-query -W -f '${Version}' nasm)"
    echo "AUDTEST.COM: $(wc -c < "$out/AUDTEST.COM") bytes, sha256 $(sha256sum "$out/AUDTEST.COM" | cut -d' ' -f1)"
} > "$out/versions.txt"
cat "$out/versions.txt"
