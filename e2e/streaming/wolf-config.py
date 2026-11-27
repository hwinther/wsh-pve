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
  - video: qemudbussrc (the console as raw video, reconnect=true: it follows the VM through a
    stop and a start), scaled to the client's size (stretched by default, so a guest's mode
    changes fill the picture), a compositor that repeats the newest picture at the client's
    frame rate (qemudbussrc sends a buffer per change), then the client's colour settings and
    the encoder
  - audio: qemudbusaudiosrc (the guest's -audiodev dbus playback, 48 kHz stereo, reconnect=true)
  - runner: wolf-input-bridge for the same bus (Moonlight's keyboard and mouse into the guest),
    started with the session and stopped with it (with --log $BRIDGE_LOG if that is set)
  - start_virtual_compositor and start_audio_server off: no Wayland compositor and no PulseAudio

Environment:
  H264_ENCODER  auto (default): the encoder Wolf picks (x264enc without a GPU), on I420 in system
                memory; nvenc: nvh264enc with Wolf's NVENC settings
  SCALER        where the picture is scaled to the client's size and converted for the encoder:
                cuda: on the GPU (cudaupload of the guest's picture at its own size, then
                cudacompositor scales and repeats it, cudaconvertscale makes NV12; needs
                H264_ENCODER=nvenc and GStreamer's CUDA elements, which need NVIDIA's libnvrtc);
                cpu: videoscale, compositor and videoconvertscale on the CPU;
                auto (default): cuda with nvenc when the CUDA elements are there, else cpu
  ASPECT        stretch (default): the picture fills the client's; keep: its aspect ratio is
                kept, with black borders (a 4:3 guest on a 16:9 client)
  SRC_PROPS     more properties for qemudbussrc (e.g. shared-map=false, render-node=...)
"""

import os
import shutil
import subprocess
import sys
import tomllib

# qemudbussrc sends a buffer per change of the picture and nothing while it stands still, but
# Moonlight ends a session that gets no video for 10 s (and videorate only lets a buffer go once
# the next one comes): a live compositor puts out the newest picture at the client's frame rate.
# The picture is scaled to the client's size before it: the compositor keeps the output size it
# negotiated first and draws a smaller picture after a mode change (a Glide game's 640x480 after
# a 1280x1024 desktop) unscaled in its top left corner, on its checkerboard
REPEAT = (
    "videoscale add-borders={borders} ! video/x-raw, width={{width}}, height={{height}},"
    " pixel-aspect-ratio=1/1 ! compositor background=black ! video/x-raw, framerate={{fps}}/1"
)

# SCALER=cuda: only the guest's picture, at its own (often small) size, is copied to the GPU
# (videoconvert passes it through unless cudaupload can't take its format, a 16-bit mode's
# RGB16); cudacompositor scales it to the client's size (its pad's width and height, whatever
# size comes in, so a mode change needs no renegotiation after it) and repeats the newest
# picture at the client's frame rate, in CUDA memory, which nvh264enc takes as it is
REPEAT_CUDA = (
    "videoconvert ! cudaupload ! cudacompositor background=black sink_0::width={{width}}"
    " sink_0::height={{height}}{sizing} ! video/x-raw(memory:CUDAMemory), width={{width}},"
    " height={{height}}, framerate={{fps}}/1"
)
CUDA_ELEMENTS = ("cudaupload", "cudacompositor", "cudaconvertscale")

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
VIDEO_PARAMS_CUDA = (
    "cudaconvertscale ! video/x-raw(memory:CUDAMemory), width={width}, height={height}, "
    "format=NV12, chroma-site={color_range}, colorimetry={color_space}, pixel-aspect-ratio=1/1"
)


def have_elements(names):
    """whether GStreamer has all these elements (the CUDA ones only when it found a GPU and
    libnvrtc when it scanned its plugins)"""
    if not shutil.which("gst-inspect-1.0"):
        return False
    return all(subprocess.run(["gst-inspect-1.0", "--exists", n], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0 for n in names)


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
    src_props = f" {os.environ['SRC_PROPS']}" if os.environ.get("SRC_PROPS") else ""
    if encoder != "auto" and encoder not in H264:
        print(f"H264_ENCODER={encoder}: auto or one of {', '.join(H264)}", file=sys.stderr)
        return 2
    scaler = os.environ.get("SCALER") or "auto"
    aspect = os.environ.get("ASPECT") or "stretch"
    if scaler not in ("auto", "cuda", "cpu") or aspect not in ("stretch", "keep"):
        print(f"SCALER={scaler} ASPECT={aspect}: SCALER is auto, cuda or cpu, ASPECT stretch or"
              " keep", file=sys.stderr)
        return 2
    if scaler == "cuda" and encoder != "nvenc":
        print("SCALER=cuda needs H264_ENCODER=nvenc", file=sys.stderr)
        return 2
    if scaler == "auto":
        scaler = "cuda" if encoder == "nvenc" and have_elements(CUDA_ELEMENTS) else "cpu"
    elif scaler == "cuda" and not have_elements(CUDA_ELEMENTS):
        print(f"SCALER=cuda: GStreamer has no {', '.join(CUDA_ELEMENTS)} here (libnvrtc, the"
              " GPU's devices?): the apps won't stream until it has", file=sys.stderr)
    print(f"wolf-config.py: H264_ENCODER={encoder} SCALER={scaler} ASPECT={aspect}",
          file=sys.stderr)
    if scaler == "cuda":
        repeat = REPEAT_CUDA.format(
            sizing=" sink_0::sizing-policy=keep-aspect-ratio" if aspect == "keep" else "")
        video_params = VIDEO_PARAMS_CUDA
    else:
        repeat = REPEAT.format(borders="true" if aspect == "keep" else "false")
        # x264enc takes I420, nvh264enc NV12 (or RGB) in system memory
        video_params = VIDEO_PARAMS % ("NV12" if encoder == "nvenc" else "I420")
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
            f"source = {toml_str(f'qemudbussrc address={address} reconnect=true{src_props} ! {repeat}')}",
            f"video_params = {toml_str(video_params)}",
            *([f"h264_encoder = {toml_str(H264[encoder])}"] if encoder != "auto" else []),
            "",
            "[profiles.apps.audio]",
            f"source = {toml_str(f'qemudbusaudiosrc address={address} reconnect=true')}",
            "",
        ]
    out += keep
    with open(sys.argv[2], "w") as f:
        f.write("\n".join(out) + "\n" + gst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
