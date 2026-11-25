#!/usr/bin/env python3
"""Write a Wolf config.toml whose Moonlight apps are PVE VMs' D-Bus displays.

usage: wolf-config.py DEFAULTS OUT APP [APP ...]

DEFAULTS is Wolf's own default configuration (src/moonlight-server/state/default/
config.include.toml in Wolf's source; the node image keeps it in /usr/local/share/wolf). Its
[gstreamer] part (the encoders Wolf picks from, its sinks and audio settings) is kept as it is;
the profiles are replaced by one profile, the one Moonlight clients see, with an app per APP:

  TITLE=VMID          the VM's bus as qemu-server makes it, /run/wsh-dbus-display/VMID.sock
  TITLE=unix:path=..  any other D-Bus address of a QEMU started with -display dbus

Each app:
  - video: qemudbussrc (the console as raw video), a compositor that repeats the newest picture
    at the client's frame rate (qemudbussrc sends a buffer per change), then Wolf's software
    path: scaled to the client's size,
    I420, the client's colour settings, then the encoder Wolf picked (x264enc without a GPU)
  - audio: qemudbusaudiosrc (the guest's -audiodev dbus playback, 48 kHz stereo)
  - runner: wolf-input-bridge for the same bus (Moonlight's keyboard and mouse into the guest),
    started with the session and stopped with it (with --log $BRIDGE_LOG if that is set)
  - start_virtual_compositor and start_audio_server off: no Wayland compositor and no PulseAudio
"""

import os
import sys

# qemudbussrc sends a buffer per change of the picture and nothing while it stands still, but
# Moonlight ends a session that gets no video for 10 s (and videorate only lets a buffer go once
# the next one comes): a live compositor puts out the newest picture at the client's frame rate
REPEAT = "compositor ! video/x-raw, framerate={fps}/1"

VIDEO_PARAMS = (
    "videoconvertscale ! videorate ! video/x-raw, width={width}, height={height}, "
    "framerate={fps}/1, format=I420, chroma-site={color_range}, colorimetry={color_space}"
)


def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    defaults = open(sys.argv[1]).read()
    start = defaults.find("[gstreamer]")
    end = defaults.rfind(")for_c++_include")
    if start < 0:
        print(f"{sys.argv[1]}: no [gstreamer] section", file=sys.stderr)
        return 1
    gst = defaults[start:end if end > start else len(defaults)]
    out = [
        '# Written by wolf-config.py: PVE VMs\' D-Bus displays as Moonlight apps',
        'hostname = "wsh-pve"',
        "config_version = 7",
        "paired_clients = []",
        "",
        "[[profiles]]",
        'id = "moonlight-profile-id"',
        "",
    ]
    log = f" --log {os.environ['BRIDGE_LOG']}" if os.environ.get("BRIDGE_LOG") else ""
    for spec in sys.argv[3:]:
        title, _, target = spec.partition("=")
        if target.isdigit():
            address = f"unix:path=/run/wsh-dbus-display/{target}.sock"
        else:
            address = target
        out += [
            "[[profiles.apps]]",
            f"title = {toml_str(title)}",
            "start_virtual_compositor = false",
            "start_audio_server = false",
            "",
            "[profiles.apps.runner]",
            'type = "process"',
            f"run_cmd = {toml_str('wolf-input-bridge --address ' + address + log)}",
            "",
            "[profiles.apps.video]",
            f"source = {toml_str('qemudbussrc address=' + address + ' ! ' + REPEAT)}",
            f"video_params = {toml_str(VIDEO_PARAMS)}",
            "",
            "[profiles.apps.audio]",
            f"source = {toml_str('qemudbusaudiosrc address=' + address)}",
            "",
        ]
    with open(sys.argv[2], "w") as f:
        f.write("\n".join(out) + "\n" + gst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
