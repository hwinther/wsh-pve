#!/bin/busybox sh
# /init of the Linux guest of the x86 audio matrix (e2e/audio/audio_matrix.py): a Debian kernel and
# this initramfs (busybox, aplay and the sound modules, build-guests.sh), no install.
#
# Kernel command line:
#   wsh.mods=a,b   module lists to load (/mods/<name>.list, made at build time with their
#                  dependencies in load order), e.g. snd-intel8x0 or snd-hda-codec-generic,snd-hda-intel
#
# Plays /tone.wav (660 Hz, 1.5 s) on the first card with a playback device (plughw:N,0), prints one
# line `AUDIOTEST result=<ok|nocard|fail> card=<name> index=<N> rc=<aplay exit>` on the console and
# powers off.
/bin/busybox --install -s /bin
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev

mods=$(sed -n 's/.*wsh\.mods=\([^ ]*\).*/\1/p' /proc/cmdline | tr ',' ' ')
for m in $mods; do
    while read -r ko args; do
        name=$(basename "$ko" .ko | tr - _)
        [ -d "/sys/module/$name" ] && continue  # a dependency of an earlier list
        insmod "$ko" $args 2>/dev/null || echo "AUDIOTEST insmod failed: $ko"
    done < "/mods/$m.list"
done

# card registration and /dev/snd/* can lag the module load by a moment (PCI probe, USB enumeration)
first_pcm() {
    for p in /dev/snd/pcmC*D0p; do
        [ -e "$p" ] && { p=${p#/dev/snd/pcmC}; echo "${p%D0p}"; return; }
    done
}
i=0
while [ -z "$(first_pcm)" ] && [ $i -lt 50 ]; do
    sleep 0.2
    i=$((i + 1))
done
sleep 0.5  # a second controller may still be probing
cat /proc/asound/cards 2>/dev/null
# The first card with a playback device, not card 0: on q35 PVE's machine config adds a controller
# without codecs at 00:1b.0 in front of audio0's
c=$(first_pcm)
if [ -z "$c" ]; then
    echo "AUDIOTEST result=nocard card=- rc=-"
else
    card=$(sed -n "s/^ *$c \[\([^ ]*\) *\].*/\1/p" /proc/asound/cards)
    [ "$c" = 0 ] || echo "AUDIOTEST note: card 0 has no playback device, using card $c"
    # ALSA starts the AC97 and HDA mixers muted (a distribution's alsactl init or the desktop unmutes
    # them; the ES1370's isn't): every simple control of the card to 80 % and unmuted
    n=0
    amixer -c "$c" scontrols | sed -n "s/^Simple mixer control '\(.*\)',\([0-9]*\)$/\1,\2/p" > /tmp/controls
    while read -r ctl; do
        amixer -q -c "$c" sset "$ctl" 80% unmute 2>/dev/null && n=$((n + 1))
    done < /tmp/controls
    echo "AUDIOTEST mixer: $n of $(wc -l < /tmp/controls) controls set to 80% unmuted"
    aplay -D "plughw:$c,0" /tone.wav
    rc=$?
    if [ $rc -eq 0 ]; then res=ok; else res=fail; fi
    echo "AUDIOTEST result=$res card=$card index=$c rc=$rc"
fi
sync
poweroff -f
