#!/usr/bin/env python3
"""A Sun (SMI) disk label, the sector 0 Solaris and SunOS read the disk geometry and slices from. The
Solaris 2.x installers list only disks that carry one, and the old releases can't label an emulated
disk themselves, so `lab.py install` writes it into a blank image before importing it as the VM's disk.

    label(**targets.SUN29G)  # the 512 bytes of the lab's SUN2.9G template's first sector
    write_disk("disk.raw", 8, targets.QEMU8G)  # the lab's Qemu9G template, byte for byte

`format` also writes the label as five backup copies into the odd sectors 1-9 of the last track of
the disk (the last track of the last alternate cylinder), and the templates have them: write_disk()
writes them too, so its image is the template (sparse) for both geometries.

Layout (SunOS dk_label): ASCII name at 0, VTOC at 128 (version 1, 8 slices, tag/flag per slice,
sanity 0x600DDEEE at 188), geometry at 420 (rpm, pcyl, spare, gap1, gap2, interleave, ncyl, acyl,
heads, sectors), 8 x (start cylinder, blocks) at 444, magic 0xDABE at 508 and the XOR of the 255
big-endian words before it at 510. bench/sunlabel.py writes the bench disk's label the same way.
"""
import struct


def label(name, ncyl, acyl, heads, sectors, parts, pcyl=None, rpm=3600):
    """The label sector for a disk of `ncyl` data + `acyl` alternate cylinders; `parts`: 8 x (tag,
    flag, start cylinder, blocks). The name gets the geometry appended, as `format` writes it."""
    if len(parts) != 8:
        raise ValueError("a Sun label has 8 slices")
    d = bytearray(512)
    text = f"{name} cyl {ncyl} alt {acyl} hd {heads} sec {sectors}".encode()
    d[0:len(text)] = text
    struct.pack_into(">I8sH", d, 128, 1, b"", 8)  # v_version, v_volume, v_nparts
    for i, (tag, flag, _, _) in enumerate(parts):
        struct.pack_into(">HH", d, 142 + 4 * i, tag, flag)
    struct.pack_into(">I", d, 188, 0x600DDEEE)  # v_sanity, after v_bootinfo[3]
    struct.pack_into(">12H", d, 420, rpm, pcyl or ncyl + acyl, 0, 0, 0, 1, ncyl, acyl, heads, sectors, 0, 0)
    for i, (_, _, cyl, blocks) in enumerate(parts):
        struct.pack_into(">II", d, 444 + 8 * i, cyl, blocks)
    struct.pack_into(">H", d, 508, 0xDABE)
    ck = 0
    for (w,) in struct.iter_unpack(">H", bytes(d[:510])):
        ck ^= w
    struct.pack_into(">H", d, 510, ck)
    return bytes(d)


def data_geometry(size_gib):
    """A label for a data disk of `size_gib` GiB (1-32) that Solaris takes without `format`: 16 heads x
    128 sectors (1 MiB per cylinder), 2 alternate cylinders, slice 0 (usr) and slice 2 (backup) the
    whole disk, so `newfs /dev/rdsk/cXtYd0s0` is all it needs. The label's cylinder count is 16 bits."""
    if not 1 <= size_gib <= 32:
        raise ValueError("a data disk is 1-32 GiB")
    ncyl, heads, sectors = (size_gib << 10) - 2, 16, 128
    blocks = ncyl * heads * sectors
    return {"name": f"WSHDATA{size_gib}G", "ncyl": ncyl, "acyl": 2, "heads": heads, "sectors": sectors,
            "parts": [(4, 0, 0, blocks), (0, 0, 0, 0), (5, 1, 0, blocks)] + [(0, 0, 0, 0)] * 5}


def backup_sectors(ncyl, acyl, heads, sectors, **_):
    """The sectors of the backup labels: 1, 3, 5, 7 and 9 of the last track of the last cylinder."""
    last_track = (ncyl + acyl) * heads * sectors - sectors
    return [last_track + i for i in (1, 3, 5, 7, 9)]


def write_disk(path, size_gib, geometry=None):
    """A sparse raw image of `size_gib` GiB, labelled with `geometry` (label()'s arguments) if given,
    with the backup labels."""
    with open(path, "wb") as f:
        if geometry:
            sector = label(**geometry)
            f.write(sector)
            for s in backup_sectors(**geometry):
                f.seek(s * 512)
                f.write(sector)
        f.truncate(size_gib << 30)
    return path


def main(argv):
    """sunlabel.py disk 3G|9G IMAGE    the install targets' disk (the template's image, sparse)
    sunlabel.py data GIB IMAGE       a data disk of 1-32 GiB (slice 0 = the disk: newfs, no format)"""
    import targets  # next to this file (the wsh-lab package: /usr/share/wsh-lab)

    if len(argv) != 3 or argv[0] not in ("disk", "data"):
        raise SystemExit(main.__doc__)
    kind, size, path = argv
    if kind == "disk":
        if size not in targets.DISKS:
            raise SystemExit(f"disk sizes: {', '.join(targets.DISKS)}")
        d = targets.DISKS[size]
        write_disk(path, d["size"], d["geometry"])
        print(f"{path}: {d['size']} GiB, {d['geometry']['name']} label (= {d['template']})")
    else:
        try:
            gib = int(size)
            g = data_geometry(gib)
        except ValueError as e:
            raise SystemExit(f"data disk: {e}")
        write_disk(path, gib, g)
        print(f"{path}: {gib} GiB, {g['name']} label, slice 0 = {g['parts'][0][3]} blocks")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
