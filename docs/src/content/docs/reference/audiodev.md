---
title: Audio Device Reference
description: A reference page for the audio device hardware panel.
---

QEMU offers various audio devices and outputs to emulate sound hardware in virtual machines. This page outlines the available audio devices and configuration options for managing audio in QEMU. It supports both modern and older audio devices, ensuring compatibility with many guest operating systems. Additionally, QEMU supports network forwarding for remote audio configurations, allowing audio streams to be forwarded over a network connection.
The WSH PVE patches enable ALSA, PulseAudio and Pipewire with the configuration options outlined in this reference document.

## Audio Devices

The following audio devices are defined in the UI, and the existing Intel devices are fully named to make it easier to understand which driver should be used.

![Audio device menu](../../../assets/audiodev.png)

- **sb16**: Creative Sound Blaster 16 (ISA)
- **adlib**: Yamaha YM3812 (ISA)
- **pcspk**: PC Speaker
- **sb16-adlib-pcspk**: A combination of sb16, adlib, and pcspk with a single driver
- **cs4231**: Crystal CS4231, built into the SPARCstation 5 (SPARC 32-bit, machine SS-5 only; the
  only device offered there). Use it with `none`, `alsa`, `pa` or `pipewire`: SPICE needs a SPICE
  display, which SPARC doesn't have. See [Sound on the SS-5](/guides/sparc/#sound-on-the-ss-5).

## Which device works in which guest

Tested on x86 with the published packages by the [audio matrix](#how-this-is-tested): each guest
plays a known tone, QEMU's `wav` backend records it, and the recording must hold that tone. Every
row passed directly on QEMU and through qemu-server (`qm showcmd`, then the same command with the
`wav` backend, then a real `qm start` with `driver=none`).

| `audio0: device=` | QEMU device | Guest tested | Result | Notes |
| --- | --- | --- | --- | --- |
| `sb16` | `sb16` (ISA) | DOS: own program, DSP 4.05, 8-bit PCM by DMA | plays | `BLASTER=A220 I5 D1 H5 T6`: QEMU's fixed defaults, qemu-server sets no resources. DMA playback only: direct DAC (DSP command `10h`) isn't emulated, so programs that play through it are silent. |
| `adlib` | `adlib` (ISA, OPL2) | DOS: own program, FM tone at 388h | plays | Also answers at 220h-223h and 228h-229h, where a real SB16 has its OPL3; QEMU's is an OPL2 (YM3812). Adlib's timer detection works. |
| `pcspk` | machine property `pcspk-audiodev` | DOS: PIT channel 2 through port 61h | plays | qemu-server only sets it for machine version 4.2 or newer; on an older pinned machine version the speaker is silent without an error. |
| `sb16-adlib-pcspk` | all three on one backend | DOS: the three tones in turn | plays | The usual choice for DOS games: digital sound, FM music and the speaker. |
| `AC97` | `AC97` (PCI, ICH AC'97 + STAC9700) | Linux `snd-intel8x0` | plays | Linux starts the mixer muted; a distribution's `alsactl init` or desktop unmutes it, a minimal system needs `amixer`. Windows 2000 and later have drivers. |
| `intel-hda` | `intel-hda` + `hda-micro` + `hda-duplex` | Linux `snd-hda-intel` (generic codec) | plays | Two codecs on one controller (as in stock Proxmox VE); Linux warns that their mixer controls exist twice. Mixer muted at start, as for AC97. Windows Vista and later. |
| `ich9-intel-hda` | `ich9-intel-hda` + the same codecs | Linux, machine q35 | plays | On q35 Proxmox VE's machine config already has an `ich9-intel-hda` **without codecs** at 00:1b.0, so the guest sees two controllers and `audio0` is the **second card**. Point the guest's default at it (Linux: `defaults.pcm.card 1`), or the first card stays silent. |
| `cs4231` | SPARCstation 5 only | | | Refused on x86. See [Sound on the SS-5](/guides/sparc/#sound-on-the-ss-5). |

In QEMU but not offered by qemu-server (would need `args:`):

| QEMU device | Guest tested | Result | Notes |
| --- | --- | --- | --- |
| `ES1370` (PCI) | Linux `snd-ens1370` | plays | The mixer isn't muted at start. Windows 9x/2000 drivers exist (Ensoniq AudioPCI). |
| `virtio-sound-pci` | Linux `virtio_snd` (5.13+) | plays | Modern Linux only. |
| `usb-audio` (with `qemu-xhci`) | Linux `snd-usb-audio` | plays | Needs a USB controller. |
| `gus` (ISA, Gravis Ultrasound GF1) | - | not tested | Port 240h, IRQ 7, DMA 3: IRQ 7 is LPT1's when the VM has a parallel port. |
| `cs4231a` (ISA, Windows Sound System) | - | not tested | Port 534h, IRQ 9, DMA 3: IRQ 9 is also `ne2k_isa`'s default, and DMA 3 is the GUS's. |
| `hda-output` | - | not tested | An output-only HDA codec. |

ISA resources at a glance (QEMU defaults, none settable through qemu-server): SB16 220h/IRQ 5/DMA
1 and 5, AdLib 388h, GUS 240h/IRQ 7/DMA 3, CS4231A 534h/IRQ 9/DMA 3, `ne2k_isa` 300h/IRQ 9. The
devices qemu-server offers don't conflict with each other or with `ne2k_isa`.

## Backend driver (audio output)

The additional backend drivers support both local and remote audio output.

![Audio driver menu](../../../assets/audiodriver.png)

- **alsa**: ALSA (local sound)
- **pa**: PulseAudio (local sound)
- **pipewire**: PipeWire (local sound)

### Where the sound goes on a headless node

A Proxmox VE node usually has no speakers and nobody logged in, so the choice is where to send it:

- **`spice`** (the default): to the SPICE client (`remote-viewer`) of a VM with a SPICE display
  (`vga: qxl`). The web console (noVNC) carries no sound.
- **`none`**: the guest has its sound card and plays into nothing. Useful for guests that want a
  card to start, and what the tests use for `qm start`.
- **`pa` with `server=`**: a PulseAudio server elsewhere, for example
  `qm set <vmid> --audio0 device=sb16-adlib-pcspk,driver=pa,server=tcp:<desktop>:4713`, with
  `module-native-protocol-tcp` loaded there. A desktop running PipeWire answers too, through
  `pipewire-pulse` (the same protocol). This is the way to listen to a VM on a headless node.
- **`pa` without `server=`**, **`pipewire`**, **`alsa`**: the node's own sound server or card. On a
  headless node there usually is none; `pipewire` takes no `server=` (QEMU's PipeWire backend has
  no such option), so for a remote PipeWire desktop use `pa`.
- **`wav`** (QEMU's file recorder): what the tests use. qemu-server doesn't offer it; to record a
  VM, leave `audio0` out and add the device yourself, for example
  `args: -audiodev wav,id=rec,path=/var/tmp/vm.wav -device sb16,audiodev=rec`. The file's header
  gets its sizes only when QEMU closes it (guest power off, `qm stop`); a killed QEMU leaves them 0.

## Remote Audio Configuration

The audio server option enables configuring unix sockets for a local audio pipeline, or a remote host.

![Audio menu](../../../assets/audio.png)

- server (default value `unix:/tmp/pulse-server`)

A unix socket must already be configured and allow the context pveproxy is running under to connect to it.

Alternatively you can use the tcp, tcp4 or tcp6 protocol prefixes to connect to a remote machine, e.g. tcp:192.168.0.100:4713

## How this is tested

`e2e/audio/` in the repository, run by the `x86 audio matrix` workflow on GitHub-hosted runners
(weekly, on demand and on pull requests that touch it) against the published packages:

- **DOS**: FreeDOS 1.4's boot floppy (downloaded by URL and sha256) with its start-up files
  replaced, so it runs `AUDTEST.COM`, a small program written for the test (`audtest.asm`, built
  with nasm). It plays 1000 Hz on the SB16 (8-bit PCM by DMA), 440 Hz on the OPL2 and 750 Hz on the
  PC speaker, one after the other, then powers off through ACPI.
- **Linux**: Debian's kernel and an initramfs with busybox, `aplay` and one sound driver; it unmutes
  the mixer, plays a 660 Hz tone, reports on the serial console and powers off. No install.
- **The check**: the wav file must hold the expected tones (zero-crossing frequency within 4 %, RMS
  above -50 dBFS, at least 0.15 s) and no tone of a device that isn't attached, so
  `sb16-adlib-pcspk` must give all three and `sb16` only the 1000 Hz one.
- **Through Proxmox VE** (the e2e node in a container): a VM per `audio0` value, `qm showcmd` must
  have the expected `-device`/`-machine`/`-audiodev` arguments, the same command with `none`
  swapped for `wav` must play the tones, and `qm start` must run the guest to its power off.

The results table is in the workflow's job summary; the recordings and logs are its artifact.

## Further reading

- Read [about PulseAudio server strings](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/ServerStrings/) in the official PulseAudio documentation.
- Read [about PulseAudio network setup](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/Network/) in the official PulseAudio documentation.
