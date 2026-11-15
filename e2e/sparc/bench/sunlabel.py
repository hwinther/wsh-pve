#!/usr/bin/env python3
"""Create a blank raw disk with a Sun (SMI) label: slice 0 the whole disk but the 2 alternate cylinders,
slice 2 the whole disk (backup). Solaris then only needs `newfs` on slice 0, no `format`.

    sunlabel.py bench.raw 32        # 32 MiB: 16 heads, 32 sectors, 126 + 2 cylinders

The label (sector 0) is the SunOS dk_label: ASCII name, VTOC, geometry at byte 420, 8 x (start
cylinder, blocks) at 444, magic 0xDABE at 508 and the XOR of the 255 big-endian words before it at 510.
"""
import struct
import sys

HEADS, SECTORS, ACYL = 16, 32, 2


def label(mib):
    ncyl = mib * 2048 // (HEADS * SECTORS) - ACYL
    blocks = ncyl * HEADS * SECTORS
    d = bytearray(512)
    d[0:128] = f"BENCH{mib}M cyl {ncyl} alt {ACYL} hd {HEADS} sec {SECTORS}".encode().ljust(128, b"\0")
    # VTOC: version 1, no volume name, 8 partitions (tag, flag): s0 usr, s2 backup (unmountable)
    parts = [(4, 0), (0, 0), (5, 1)] + [(0, 0)] * 5
    struct.pack_into(">I8sH", d, 128, 1, b"", 8)  # v_version, v_volume, v_nparts
    for i, (tag, flag) in enumerate(parts):
        struct.pack_into(">HH", d, 142 + 4 * i, tag, flag)
    struct.pack_into(">I", d, 186, 0x600DDEEE)  # v_sanity, after v_bootinfo[3]
    struct.pack_into(">12H", d, 420, 3600, ncyl + ACYL, 0, 0, 0, 1, ncyl, ACYL, HEADS, SECTORS, 0, 0)
    for i, (cyl, nblk) in enumerate([(0, blocks), (0, 0), (0, blocks)] + [(0, 0)] * 5):
        struct.pack_into(">II", d, 444 + 8 * i, cyl, nblk)
    struct.pack_into(">H", d, 508, 0xDABE)
    ck = 0
    for (w,) in struct.iter_unpack(">H", bytes(d[:510])):
        ck ^= w
    struct.pack_into(">H", d, 510, ck)
    return bytes(d), (ncyl + ACYL) * HEADS * SECTORS * 512


def main():
    path, mib = sys.argv[1], int(sys.argv[2])
    d, size = label(mib)
    with open(path, "wb") as f:
        f.write(d)
        f.truncate(size)
    print(f"{path}: {size >> 20} MiB, Sun label, slice 0 = {(size >> 9) - ACYL * HEADS * SECTORS} blocks")


if __name__ == "__main__":
    main()
