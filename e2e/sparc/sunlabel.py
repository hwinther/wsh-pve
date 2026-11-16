"""A Sun (SMI) disk label, the sector 0 Solaris and SunOS read the disk geometry and slices from. The
Solaris 2.x installers list only disks that carry one, and the old releases can't label an emulated
disk themselves, so `lab.py install` writes it into a blank image before importing it as the VM's disk.

    label(**targets.SUN29G)  # the 512 bytes of the lab's SUN2.9G template's first sector

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


def write_disk(path, size_gib, geometry=None):
    """A sparse raw image of `size_gib` GiB, labelled with `geometry` (label()'s arguments) if given."""
    with open(path, "wb") as f:
        if geometry:
            f.write(label(**geometry))
        f.truncate(size_gib << 30)
    return path
