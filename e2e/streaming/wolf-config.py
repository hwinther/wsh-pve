#!/usr/bin/env python3
"""Write a Wolf config.toml whose Moonlight apps are PVE VMs' D-Bus displays.

usage: wolf-config.py DEFAULTS OUT APP [APP ...]

DEFAULTS is Wolf's own default configuration (src/moonlight-server/state/default/
config.include.toml in Wolf's source; the node image keeps it in /usr/local/share/wolf). Its
[gstreamer] part (the encoders Wolf picks from, its sinks and audio settings) is kept as it is;
the profiles are replaced by one profile, the one Moonlight clients see, with an app per APP:

  TITLE=VMID          the VM's bus as qemu-server makes it, /run/wsh-dbus-display/VMID.sock
  TITLE=unix:path=..  any other D-Bus address of a QEMU started with -display dbus (in a
                      container, where the node's /run/wsh-dbus-display is bind-mounted elsewhere)

The clients Wolf paired (its [[paired_clients]] in an existing OUT) are kept.

Each app:
  - video: qemudbussrc (the console as raw video), a compositor that repeats the newest picture
    at the client's frame rate (qemudbussrc sends a buffer per change), then Wolf's software
    path: scaled to the client's size,
    I420, the client's colour settings, then the encoder Wolf picked (x264enc without a GPU)
  - audio: qemudbusaudiosrc (the guest's -audiodev dbus playback, 48 kHz stereo)
  - runner: wolf-input-bridge for the same bus (Moonlight's keyboard and mouse into the guest),
    started with the session and stopped with it (with --log $BRIDGE_LOG if that is set)
  - H264_ENCODER=nvenc: nvh264enc instead of the encoder Wolf picks (x264enc without a GPU)
  - start_virtual_compositor and start_audio_server off: no Wayland compositor and no PulseAudio
"""

import os
import sys
import tomllib

# qemudbussrc sends a buffer per change of the picture and nothing while it stands still, but
# Moonlight ends a session that gets no video for 10 s (and videorate only lets a buffer go once
# the next one comes): a live compositor puts out the newest picture at the client's frame rate
REPEAT = "compositor ! video/x-raw, framerate={fps}/1"

# H264_ENCODER=nvenc: NVIDIA's encoder for these apps, on system-memory NV12. Wolf's
# own NVENC pipeline isn't picked without cudaconvertscale, which needs the CUDA toolkit's runtime
# compiler (libnvrtc), not part of the driver; its encoder settings are kept
H264 = {
    "nvenc": "nvh264enc gop-size=-1 bitrate={bitrate} vbv-buffer-size={vbv_buffer_size} aud=false"
    " rc-mode=cbr zerolatency=true preset=p1 tune=ultra-low-latency multi-pass=two-pass-quarter !"
    " h264parse ! video/x-h264, profile=main, stream-format=byte-stream",
}

VIDEO_PARAMS = (
    "videoconvertscale ! videorate ! video/x-raw, width={width}, height={height}, "
    "framerate={fps}/1, format=%s, chroma-site={color_range}, colorimetry={color_space}"
)


def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return toml_str(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise ValueError(f"can't write {v!r}")


def paired_clients(path):
    """the [[paired_clients]] of an existing config (Wolf writes them there when a client pairs),
    as TOML, so writing the config again keeps the pairings"""
    try:
        with open(path, "rb") as f:
            clients = tomllib.load(f).get("paired_clients", [])
    except (OSError, tomllib.TOMLDecodeError):
        return []
    out = []
    for c in clients:
        out.append("[[paired_clients]]")
        out += [f"{k} = {toml_value(v)}" for k, v in c.items() if not isinstance(v, dict)]
        for k, v in c.items():
            if isinstance(v, dict):
                out.append(f"[paired_clients.{k}]")
                out += [f"{k2} = {toml_value(v2)}" for k2, v2 in v.items()]
        out.append("")
    return out


def main():
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    defaults = open(sys.argv[1]).read()
    keep = paired_clients(sys.argv[2])
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
        *([] if keep else ["paired_clients = []"]),
        "",
        "[[profiles]]",
        'id = "moonlight-profile-id"',
        "",
    ]
    log = f" --log {os.environ['BRIDGE_LOG']}" if os.environ.get("BRIDGE_LOG") else ""
    encoder = os.environ.get("H264_ENCODER", "auto")
    if encoder != "auto" and encoder not in H264:
        print(f"H264_ENCODER={encoder}: auto or one of {', '.join(H264)}", file=sys.stderr)
        return 2
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
            # x264enc takes I420, nvh264enc NV12 (or RGB) in system memory
            f"video_params = {toml_str(VIDEO_PARAMS % ('NV12' if encoder == 'nvenc' else 'I420'))}",
            *([f"h264_encoder = {toml_str(H264[encoder])}"] if encoder != "auto" else []),
            "",
            "[profiles.apps.audio]",
            f"source = {toml_str('qemudbusaudiosrc address=' + address)}",
            "",
        ]
    out += keep
    with open(sys.argv[2], "w") as f:
        f.write("\n".join(out) + "\n" + gst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
