"""wisp tier 2: the disk, network and SMP checks (run.py --tier2). Python standard library only.

Each machine family has one or more device profiles: the disks run.py attaches (a raw image per
disk, created for the run and filled with the host pattern), the NIC on QEMU's user-mode network
and the CPU count. kernel-t2 has the drivers; the kernel command line tells PID 1 what to check
(wisp_disk=sda,vda wisp_net=eth0 wisp_smp=1), and PID 1 prints one WISP-DISK line per disk, a
WISP-NET and a WISP-SMP line after its result line. This module builds the QEMU arguments, checks
those lines against the models here and, after QEMU has exited, the images themselves.
"""

import os
import re
import sys
import zlib
from array import array

# init.c's disk check: the host pattern fills the image, PID 1 reads DISK_READ bytes of it, writes
# DISK_SPAN bytes of its own pattern at offset DISK_SPAN and reads them back.
DISK_HOST_SEED = 0x686F7374   # "host"
DISK_GUEST_SEED = 0x67756573  # "gues"
DISK_SPAN = 1024 * 1024
DISK_READ = 4 * DISK_SPAN
DISK_SIZE = 4 * DISK_SPAN
NET_PAYLOAD = 1400
NET_ECHOES = 8


def family(arch, machine=None):
    """pc, sun4m or sun4u."""
    if arch in ("x86_64", "i386"):
        return "pc"
    if arch == "sparc64":
        return "sun4u"
    return "sun4m"


# Per family: the device profiles. A disk is (kind, name in the guest): ide (the PC's PIIX3 or
# sun4u's cmd646), scsi (sun4m's ESP) or virtio (virtio-blk-pci). nic is a -nic model.
PROFILES = {
    "pc": (
        {"name": "ide+virtio-blk+e1000", "disks": (("ide", "sda"), ("virtio", "vda")),
         "nic": "e1000"},
        {"name": "virtio-net", "disks": (), "nic": "virtio-net-pci"},
    ),
    "sun4m": (
        {"name": "esp+lance", "disks": (("scsi", "sda"),), "nic": "lance"},
    ),
    "sun4u": (
        {"name": "cmd646+virtio-blk+hme", "disks": (("ide", "sda"), ("virtio", "vda")),
         "nic": "sunhme"},
    ),
}

# CPU counts for the SMP runs, per architecture, and on sparc32 per machine: only the SS-10 and the
# SS-20 take more than one CPU (up to four); QEMU's sun4u has one.
SMP = {"x86_64": (2, 4), "i386": (2, 4), "sparc32": (2, 4), "sparc64": ()}
SMP_MACHINES = {"sparc32": ("SS-10", "SS-20")}


def smp_counts(arch, machine):
    """The -smp values to test on this machine (empty: uniprocessor only)."""
    if arch in SMP_MACHINES and machine not in SMP_MACHINES[arch]:
        return ()
    return SMP.get(arch, ())


def profiles(arch, machine):
    """Every tier-2 run for a machine: its device profiles, then one SMP run per CPU count."""
    out = [dict(p, smp=1) for p in PROFILES[family(arch, machine)]]
    for n in smp_counts(arch, machine):
        out.append({"name": f"smp{n}", "disks": (), "nic": None, "smp": n})
    return out


def shell_profile(arch, machine):
    """The profile for run.py --shell --tier2: the first device profile, with 2 CPUs if possible."""
    p = dict(PROFILES[family(arch, machine)][0])
    p["smp"] = 2 if smp_counts(arch, machine) else 1
    p["name"] += f"+smp{p['smp']}" if p["smp"] > 1 else ""
    return p


def qemu_args(profile, images):
    """QEMU arguments for a profile's devices; images: one path per disk."""
    args = []
    for i, ((kind, _name), path) in enumerate(zip(profile["disks"], images)):
        if kind == "virtio":
            args += ["-drive", f"file={path},format=raw,if=none,id=wd{i}",
                     "-device", f"virtio-blk-pci,drive=wd{i}"]
        else:
            args += ["-drive", f"file={path},format=raw,if={kind},index=0"]
    if profile.get("nic"):
        args += ["-nic", f"user,model={profile['nic']}"]
    if profile.get("smp", 1) > 1:
        args += ["-smp", str(profile["smp"])]
    return args


def kernel_args(profile, arch=None):
    """The kernel command line's tier-2 switches for a profile."""
    out = []
    if arch == "sparc32":
        # The ESP driver waits 3 s after its SCSI bus reset for real disks to settle, on every
        # boot (the ESP is on the board, with a disk or without); QEMU's need no time.
        out.append("esp_scsi.esp_bus_reset_settle=0")
        # A fixed delay-loop calibration (about what the lab host measures under TCG): when the
        # host deschedules QEMU during the kernel's calibration, it settles on lpj=8191, and with
        # that the boot CPU gives a second CPU microseconds instead of 2 s to start ("Processor 1
        # is stuck"), and the boot hangs in RCU stalls (1 of about 60 sparc32 boots on the lab).
        out.append("lpj=2000000")
    if profile["disks"]:
        out.append("wisp_disk=" + ",".join(name for _kind, name in profile["disks"]))
    if profile.get("nic"):
        out.append("wisp_net=eth0")
    if profile.get("smp", 1) > 1:
        out.append("wisp_smp=1")
    return out


_STREAMS = {}


def stream(seed, nbytes):
    """nbytes of init.c's xorshift32 stream from seed, each word little-endian (cached)."""
    key = (seed, nbytes)
    if key not in _STREAMS:
        words = array("I", bytes(nbytes))
        x = seed
        for i in range(nbytes // 4):
            x ^= (x << 13) & 0xFFFFFFFF
            x ^= x >> 17
            x ^= (x << 5) & 0xFFFFFFFF
            words[i] = x
        if sys.byteorder == "big":
            words.byteswap()
        _STREAMS[key] = words.tobytes()
    return _STREAMS[key]


def make_image(path, index):
    """A raw disk image for disk index, filled with the host pattern."""
    with open(path, "wb") as fh:
        fh.write(stream(DISK_HOST_SEED + index, DISK_SIZE))


def check_image(path, index):
    """Problems with an image after the run: the guest pattern at DISK_SPAN, the host's around."""
    with open(path, "rb") as fh:
        data = fh.read()
    host = stream(DISK_HOST_SEED + index, DISK_SIZE)
    guest = stream(DISK_GUEST_SEED + index, DISK_SPAN)
    problems = []
    if len(data) != DISK_SIZE:
        problems.append(f"image {index}: {len(data)} bytes")
    elif data[DISK_SPAN:2 * DISK_SPAN] != guest:
        problems.append(f"image {index}: the guest's pattern is not at {DISK_SPAN}")
    elif data[:DISK_SPAN] != host[:DISK_SPAN] or data[2 * DISK_SPAN:] != host[2 * DISK_SPAN:]:
        problems.append(f"image {index}: changed outside the written span")
    return problems


def crc(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def parse_line(text, prefix):
    """The key=value fields of the first line with prefix in text (indented in the shell), or
    None."""
    m = re.search(rf"^ *{prefix} (.*)$", text, re.M)
    if not m:
        return None
    return dict(item.partition("=")[::2] for item in m.group(1).split())


def lines(text, prefix):
    """Every line with prefix, as field dicts."""
    return [dict(item.partition("=")[::2] for item in m.group(1).split())
            for m in re.finditer(rf"^ *{prefix} (.*)$", text, re.M)]


def check(text, profile, crc_for, loops):
    """Problems with the tier-2 lines of a console transcript, and the numbers worth reporting."""
    problems, numbers = [], {}
    disks = {d.get("dev"): d for d in lines(text, "WISP-DISK")}
    numbers["disks"] = []
    for index, (kind, name) in enumerate(profile["disks"]):
        d = disks.get(name)
        if d is None:
            problems.append(f"disk {name}: no WISP-DISK line")
            continue
        if d.get("status") != "ok":
            problems.append(f"disk {name}: status {d.get('status')}")
        want = {
            "index": str(index),
            "read_kb": str(DISK_READ // 1024),
            "read_crc": f"0x{crc(stream(DISK_HOST_SEED + index, DISK_READ)):08x}",
            "write_crc": f"0x{crc(stream(DISK_GUEST_SEED + index, DISK_SPAN)):08x}",
            "verify_crc": f"0x{crc(stream(DISK_GUEST_SEED + index, DISK_SPAN)):08x}",
            "read_bad": "0", "verify_bad": "0",
        }
        for key, value in want.items():
            if d.get(key) != value:
                problems.append(f"disk {name}: {key} {d.get(key)} != {value}")
        numbers["disks"].append({"dev": name, "kind": kind, "size_kb": _int(d.get("size_kb")),
                                 "read_ms": _int(d.get("read_ms")),
                                 "write_ms": _int(d.get("write_ms")),
                                 "verify_ms": _int(d.get("verify_ms"))})
    if not numbers["disks"]:
        del numbers["disks"]
    if profile.get("nic"):
        n = parse_line(text, "WISP-NET")
        if n is None:
            problems.append("net: no WISP-NET line")
        else:
            if n.get("status") != "ok":
                problems.append(f"net: status {n.get('status')}")
            if n.get("echoes") != str(NET_ECHOES):
                problems.append(f"net: {n.get('echoes')} of {NET_ECHOES} echoes")
            numbers["net"] = {"nic": profile["nic"], "mac": n.get("mac"),
                              "peer_mac": n.get("peer_mac"),
                              "arp_tries": _int(n.get("arp_tries")),
                              "arp_ms": _int(n.get("arp_ms")),
                              "rtt_min_us": _int(n.get("rtt_min_us")),
                              "rtt_avg_us": _int(n.get("rtt_avg_us")),
                              "rtt_max_us": _int(n.get("rtt_max_us"))}
    if profile.get("smp", 1) > 1:
        s = parse_line(text, "WISP-SMP")
        if s is None:
            problems.append("smp: no WISP-SMP line")
        else:
            if s.get("status") != "ok":
                problems.append(f"smp: status {s.get('status')}")
            if s.get("cpus") != str(profile["smp"]):
                problems.append(f"smp: {s.get('cpus')} CPUs != {profile['smp']}")
            want = crc_for(_int(s.get("loops")) or 0)
            percpu = [c.split(":") for c in s.get("percpu", "").split(",") if c]
            if want is not None:
                bad = [c[0] for c in percpu if len(c) != 3 or int(c[1], 16) != want]
                if bad or len(percpu) != profile["smp"]:
                    problems.append(f"smp: crc of CPU {','.join(bad) or '?'} != 0x{want:08x}")
            if _int(s.get("loops")) != loops:
                problems.append(f"smp: {s.get('loops')} loops != {loops}")
            numbers["smp"] = {"cpus": _int(s.get("cpus")), "wall_ms": _int(s.get("wall_ms")),
                              "cpu_ms": [_int(c[2]) for c in percpu if len(c) == 3]}
    return problems, numbers


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class Images:
    """The raw images for a run's disks, in a directory of their own; checked after the run."""

    def __init__(self, directory, profile):
        self.paths = []
        os.makedirs(directory, exist_ok=True)
        for index, (kind, name) in enumerate(profile["disks"]):
            path = os.path.join(directory, f"disk{index}-{kind}-{name}.img")
            make_image(path, index)
            self.paths.append(path)

    def check(self):
        problems = []
        for index, path in enumerate(self.paths):
            problems += check_image(path, index)
        return problems

    def remove(self):
        for path in self.paths:
            try:
                os.unlink(path)
            except OSError:
                pass


def summary(numbers):
    """Short text columns for the table: disk ms (read/write/verify per disk), net, smp."""
    disk = " ".join(f"{d['dev']} {d['read_ms']}/{d['write_ms']}/{d['verify_ms']}"
                    for d in numbers.get("disks", ())) or "-"
    net = numbers.get("net")
    net_s = f"{net['arp_ms']} / {net['rtt_avg_us']}" if net else "-"
    smp = numbers.get("smp")
    smp_s = f"{smp['cpus']} x {max(smp['cpu_ms'] or [0])} / {smp['wall_ms']}" if smp else "-"
    return disk, net_s, smp_s
