#!/usr/bin/env python3
"""The DOS "tools" disk for diagnostics, and test option ROMs.

    dos_tools.py disk --iso /mnt/sparc/iso/dos_drivers.iso --out tools.raw [--mb 32]
    dos_tools.py rom --kb 100 --out dummy100k.rom          # a valid, checksummed dummy option ROM
    dos_tools.py rom --owner --out owner-dummy.rom          # what the owner's Python 3 line writes
    dos_tools.py ls --iso ...                               # what the ISO has

`disk` builds a small hard disk image (MBR, one FAT16 primary partition, 16 heads x 63 sectors like
SeaBIOS's geometry for a small IDE disk) that DOS sees as D: when it is the second IDE disk, with the
memory tools copied from the owner's utility CD (dos_drivers.iso, never in the repository) and an empty
OUT directory for results. A hard disk and not a floppy: a 1.44 MB floppy doesn't hold a toolbox, and
not the CD itself: reading it in DOS needs a CD-ROM driver and MSCDEX, which take conventional or upper
memory and would distort the very measurements the tools are for. Reading the ISO is pure Python
(ISO 9660 primary volume, no mount, no root), writing the FAT needs mtools (mformat, mcopy, mmd).

`rom` writes an option ROM that SeaBIOS loads into the option ROM area: 55 AA, the size in 512-byte
blocks, a RETF as the init entry (offset 3), zeros, and a last byte that makes the sum of all bytes 0
mod 256 (SeaBIOS checks it). The owner's original line,
`python3 -c 'import sys; sys.stdout.write("\\x55\\xaa\\xc8\\xcb\\x6e" + "\\x00"*(100*1024 - 5))'`,
writes text: Python 3 encodes "\\xaa" as UTF-8 (C2 AA), so the file is 102403 bytes starting
55 C2 AA C3 88 C3 8B 6E, has no 55 AA signature, and SeaBIOS ignores it. `--owner` writes exactly those
bytes for the measurement.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile

SECTOR = 2048
HEADS, SPT = 16, 63

# D:\ name -> path on dos_drivers.iso (case-insensitive). The memory tools of "PC Magazine DOS 6 Memory
# Management with Utilities" (Jeff Prosise, 1993; UMASCAN maps 640K-1M in 2K cells as ROM, RAM, video,
# EMS frame or unused), Uwe Sieber's UMBPCI tools, HimemX, CuteMouse.
TOOLS = {
    "UMASCAN.COM": "drivers/dosutil/umascan.com",
    "EMSINFO.COM": "drivers/dosutil/emsinfo.com",
    "HMAGAUGE.COM": "drivers/dosutil/hmagauge.com",
    "UMBFILES.COM": "drivers/dosutil/umbfiles.com",
    "UMBCHK.EXE": "drivers/umbpci/umbchk.exe",
    "UMBFILL.COM": "drivers/umbpci/umbfill.com",
    "HIMEMX.EXE": "drivers/himemx338/himemx.exe",
    "CTMOUSE.EXE": "cutemouse/bin/ctmouse.exe",
}


# --- ISO 9660, read only ---------------------------------------------------------------------------

class Iso:
    """The primary volume's directory tree of an ISO 9660 image (no Rock Ridge/Joliet needed: the DOS
    files have 8.3 names there)."""

    def __init__(self, path):
        self.f = open(path, "rb")
        pvd = self.read(16, SECTOR)
        if pvd[1:6] != b"CD001" or pvd[0] != 1:
            raise ValueError(f"{path}: no ISO 9660 primary volume descriptor")
        self.root = self.record(pvd[156:156 + 34])

    def read(self, lba, size):
        self.f.seek(lba * SECTOR)
        return self.f.read(size)

    @staticmethod
    def record(b):
        lba, size, flags, nlen = struct.unpack_from("<I", b, 2)[0], struct.unpack_from("<I", b, 10)[0], b[25], b[32]
        name = b[33:33 + nlen].decode("ascii", "replace")
        return {"lba": lba, "size": size, "dir": bool(flags & 2), "name": name.split(";")[0].rstrip(".")}

    def listdir(self, d):
        data, out, i = self.read(d["lba"], d["size"]), [], 0
        while i < len(data):
            n = data[i]
            if n == 0:  # records don't cross sectors: skip to the next one
                i = (i // SECTOR + 1) * SECTOR
                continue
            r = self.record(data[i:i + n])
            if r["name"] not in ("\x00", "\x01"):
                out.append(r)
            i += n
        return out

    def find(self, path):
        d = self.root
        for part in path.strip("/").split("/"):
            d = next((r for r in self.listdir(d) if r["name"].lower() == part.lower()), None)
            if d is None:
                raise FileNotFoundError(path)
        return d

    def cat(self, path):
        r = self.find(path)
        return self.read(r["lba"], r["size"])

    def walk(self, d=None, prefix=""):
        for r in self.listdir(d or self.root):
            p = f"{prefix}/{r['name']}".lstrip("/")
            yield p, r
            if r["dir"]:
                yield from self.walk(r, p)


# --- the disk --------------------------------------------------------------------------------------

def chs(lba):
    c, rem = divmod(lba, HEADS * SPT)
    h, s = divmod(rem, SPT)
    c = min(c, 1023)
    return bytes([h, ((c >> 2) & 0xC0) | (s + 1), c & 0xFF])


def mbr(total_sectors, start=SPT, ptype=0x06):
    """A master boot record with one active FAT16 primary partition from `start` to the end of the last
    whole cylinder (no boot code: the disk is never booted)."""
    cyl = total_sectors // (HEADS * SPT)
    end = cyl * HEADS * SPT
    entry = bytes([0x80]) + chs(start) + bytes([ptype]) + chs(end - 1) + struct.pack("<II", start, end - start)
    return bytes(446) + entry + bytes(48) + b"\x55\xaa", end - start


def build_disk(iso_path, out, mb=32, tools=None):
    tools = tools or TOOLS
    total = mb * 1024 * 1024 // 512
    total -= total % (HEADS * SPT)
    boot, nsect = mbr(total)
    with open(out, "wb") as f:
        f.truncate(total * 512)
        f.write(boot)
    img = f"{out}@@{SPT * 512}"
    env = {**os.environ, "MTOOLS_SKIP_CHECK": "1"}
    subprocess.run(["mformat", "-i", img, "-T", str(nsect), "-h", str(HEADS), "-s", str(SPT), "-H", str(SPT),
                    "-v", "WSHTOOLS", "::"], check=True, env=env)
    iso = Iso(iso_path)
    with tempfile.TemporaryDirectory() as tmp:
        for name, src in tools.items():
            p = os.path.join(tmp, name)
            with open(p, "wb") as f:
                f.write(iso.cat(src))
            subprocess.run(["mcopy", "-i", img, p, f"::/{name}"], check=True, env=env)
    subprocess.run(["mmd", "-i", img, "::/OUT"], check=True, env=env)
    return out


def read_file(disk, path):
    """A file from the tools disk's FAT partition (mtools), e.g. read_file(raw, "OUT/MEM1.TXT")."""
    r = subprocess.run(["mtype", "-i", f"{disk}@@{SPT * 512}", f"::/{path}"], capture_output=True,
                       env={**os.environ, "MTOOLS_SKIP_CHECK": "1"})
    if r.returncode:
        raise FileNotFoundError(f"{path} on {disk}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode("cp437").replace("\r", "")


# --- option ROMs -----------------------------------------------------------------------------------

def option_rom(kb):
    """A valid dummy option ROM of `kb` KiB (a multiple of 512 bytes up to 127.5 KiB)."""
    blocks = kb * 2
    if not 1 <= blocks <= 255:
        raise ValueError("an option ROM is 1-255 blocks of 512 bytes")
    rom = bytearray(blocks * 512)
    rom[0:4] = b"\x55\xaa" + bytes([blocks]) + b"\xcb"  # signature, size, RETF at the init entry
    rom[-1] = (-sum(rom)) & 0xFF
    return bytes(rom)


def owner_rom():
    """The bytes the owner's line writes under Python 3 with a UTF-8 stdout."""
    return ("\x55\xaa\xc8\xcb\x6e" + "\x00" * (100 * 1024 - 5)).encode("utf-8")


def rom_info(data):
    """What SeaBIOS would make of a ROM image: signature, declared size, checksum."""
    sig = data[:2] == b"\x55\xaa"
    return {"bytes": len(data), "signature": sig, "declared": data[2] * 512 if sig else None,
            "checksum_ok": sig and sum(data[:data[2] * 512]) & 0xFF == 0}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("disk")
    d.add_argument("--iso", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--mb", type=int, default=32)
    r = sub.add_parser("rom")
    r.add_argument("--kb", type=int, default=100)
    r.add_argument("--owner", action="store_true")
    r.add_argument("--out", required=True)
    s = sub.add_parser("ls")
    s.add_argument("--iso", required=True)
    a = p.parse_args()
    if a.cmd == "disk":
        print(build_disk(a.iso, a.out, a.mb))
    elif a.cmd == "rom":
        data = owner_rom() if a.owner else option_rom(a.kb)
        with open(a.out, "wb") as f:
            f.write(data)
        print(a.out, rom_info(data))
    else:
        for path, rec in Iso(a.iso).walk():
            print(f"{rec['size']:>10} {path}{'/' if rec['dir'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
