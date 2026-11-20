#!/usr/bin/env python3
"""The DOS "tools" disk for diagnostics, and test option ROMs.

    dos_tools.py disk --iso /mnt/sparc/iso/dos_drivers.iso --out tools.raw [--mb 32]
    dos_tools.py rom --kb 100 --out dummy100k.rom          # a valid, checksummed dummy option ROM
    dos_tools.py rom --owner --out owner-dummy.rom          # what the owner's Python 3 line writes
    dos_tools.py ls --iso ...                               # what the ISO has
    dos_tools.py com --name wshidle --out WSHIDLE.COM        # the HLT idle TSR (or busy, busyk)

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

`com` writes one of three small DOS programs, assembled here from hand-encoded 8086 instructions (a
few dozen bytes each, so no assembler is needed and every byte sits next to its instruction):
WSHIDLE.COM, an idle TSR that halts the CPU in DOS's idle call (INT 28h) and in "release the time
slice" (INT 2Fh AX=1680h), the HLT alternative to POWER.EXE that the DOS guide compares; BUSY.COM and
BUSYK.COM, which count loop iterations during five seconds of BIOS ticks and print the count in hex
(BUSYK also polls the keyboard with INT 16h AH=01h in every iteration, as a game's main loop does), to
check that an idle driver doesn't slow a busy program down.
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


# --- small DOS programs ----------------------------------------------------------------------------

def assemble(items, org=0x100):
    """A two-pass assembler for hand-encoded 8086 code. `items`: bytes (an instruction or data), a str
    (a label here), ("rel8", opcode, label) for a short jump, ("rel16", opcode, label) for a near call or
    jump, ("imm16", prefix, expr) for an instruction that ends in a 16-bit value, where expr(labels) gives
    the value (labels are addresses, `org` included), ("dd",) for a zeroed far pointer. Returns
    (code, labels)."""
    sizes = {"rel8": lambda it: 2, "rel16": lambda it: 3, "imm16": lambda it: len(it[1]) + 2,
             "dd": lambda it: 4}

    def size(it):
        if isinstance(it, str):
            return 0
        return len(it) if isinstance(it, bytes) else sizes[it[0]](it)

    labels, pc = {}, org
    for it in items:
        if isinstance(it, str):
            if it in labels:
                raise ValueError(f"label {it} twice")
            labels[it] = pc
        pc += size(it)
    out = bytearray()
    for it in items:
        pc = org + len(out)
        if isinstance(it, bytes):
            out += it
        elif isinstance(it, tuple) and it[0] == "rel8":
            rel = labels[it[2]] - (pc + 2)
            if not -128 <= rel <= 127:
                raise ValueError(f"short jump to {it[2]} out of range ({rel})")
            out += bytes([it[1], rel & 0xFF])
        elif isinstance(it, tuple) and it[0] == "rel16":
            out += bytes([it[1]]) + struct.pack("<h", labels[it[2]] - (pc + 3))
        elif isinstance(it, tuple) and it[0] == "imm16":
            out += it[1] + struct.pack("<H", it[2](labels) & 0xFFFF)
        elif isinstance(it, tuple):
            out += bytes(4)
    return bytes(out), labels


def _at(name, plus=0):
    return lambda labels: labels[name] + plus


def idle_tsr():
    """WSHIDLE.COM: a TSR that halts the CPU while DOS is idle. DOS calls INT 28h while it waits for a
    key at the prompt (in every console read); the handler does STI and HLT and then goes on to the
    previous handler, so the CPU sleeps until the next interrupt: the keyboard's at once, the timer's
    after at most 55 ms. INT 2Fh AX=1680h ("release the time slice", called by Windows-aware DOS
    programs while they wait) halts the same way and returns AL=0 (supported). A busy program calls
    neither, so it isn't slowed down. The environment is freed; what stays is the PSP and the
    handlers: 19 paragraphs (304 bytes)."""
    jmp_far_cs = b"\x2e\xff\x2e"              # jmp far [cs:addr]
    code, _ = assemble([
        ("rel16", 0xE9, "install"),           # jmp install
        "int28",
        b"\xfb",                              # sti
        b"\xf4",                              # hlt
        ("imm16", jmp_far_cs, _at("old28")),  # jmp far [cs:old28]
        "int2f",
        b"\x3d\x80\x16",                      # cmp ax,1680h
        ("rel8", 0x75, "chain2f"),            # jne chain2f
        b"\xfb",                              # sti
        b"\xf4",                              # hlt
        b"\x30\xc0",                          # xor al,al        ; supported
        b"\xcf",                              # iret
        "chain2f",
        ("imm16", jmp_far_cs, _at("old2f")),  # jmp far [cs:old2f]
        "old28", ("dd",),
        "old2f", ("dd",),
        "resident_end",
        "install",
        b"\xb8\x28\x35",                      # mov ax,3528h
        b"\xcd\x21",                          # int 21h          ; ES:BX = the INT 28h vector
        ("imm16", b"\x89\x1e", _at("old28")),     # mov [old28],bx
        ("imm16", b"\x8c\x06", _at("old28", 2)),  # mov [old28+2],es
        b"\xb8\x2f\x35",                      # mov ax,352Fh
        b"\xcd\x21",                          # int 21h
        ("imm16", b"\x89\x1e", _at("old2f")),     # mov [old2f],bx
        ("imm16", b"\x8c\x06", _at("old2f", 2)),  # mov [old2f+2],es
        ("imm16", b"\xba", _at("int28")),     # mov dx,int28
        b"\xb8\x28\x25",                      # mov ax,2528h
        b"\xcd\x21",                          # int 21h          ; INT 28h = DS:DX
        ("imm16", b"\xba", _at("int2f")),     # mov dx,int2f
        b"\xb8\x2f\x25",                      # mov ax,252Fh
        b"\xcd\x21",                          # int 21h
        ("imm16", b"\xba", _at("msg")),       # mov dx,msg
        b"\xb4\x09",                          # mov ah,9
        b"\xcd\x21",                          # int 21h          ; print msg
        b"\x8e\x06\x2c\x00",                  # mov es,[2Ch]     ; the environment's segment
        b"\xb4\x49",                          # mov ah,49h
        b"\xcd\x21",                          # int 21h          ; free it
        # mov dx,<paragraphs from the PSP to the end of the handlers>
        ("imm16", b"\xba", lambda lb: (lb["resident_end"] + 15) // 16),
        b"\xb8\x00\x31",                      # mov ax,3100h
        b"\xcd\x21",                          # int 21h          ; terminate and stay resident
        "msg", b"WSHIDLE: HLT in INT 28h and INT 2Fh/1680h\r\n$",
    ])
    return code


def busy_com(poll=False):
    """BUSY.COM (BUSYK.COM with `poll`): wait for a BIOS tick (the count at 0040:006C), count loop
    iterations until 91 more ticks (five seconds) have passed, print the 32-bit count as eight hex digits
    and exit. With `poll` every iteration also asks the BIOS for a key (INT 16h AH=01h), as a game's main
    loop does: an idle driver that halts on keyboard polls makes that one slower."""
    tick = b"\x1e\x6c\x04"                     # ModRM + disp16 for [046Ch]
    code, _ = assemble([
        b"\x31\xc0",                          # xor ax,ax
        b"\x8e\xc0",                          # mov es,ax
        b"\x26\x8b" + tick,                   # mov bx,[es:046Ch]
        "edge",
        b"\x26\x3b" + tick,                   # cmp bx,[es:046Ch]
        ("rel8", 0x74, "edge"),               # je edge          ; wait for the next tick
        b"\x26\x8b" + tick,                   # mov bx,[es:046Ch]
        b"\x83\xc3\x5b",                      # add bx,91        ; five seconds
        b"\x31\xf6",                          # xor si,si        ; the count's low word
        b"\x31\xff",                          # xor di,di        ; and high word
        "count",
        *([b"\xb4\x01",                       # mov ah,1
           b"\xcd\x16"] if poll else []),     # int 16h          ; a key waiting?
        b"\x83\xc6\x01",                      # add si,1
        b"\x83\xd7\x00",                      # adc di,0
        b"\x26\x3b" + tick,                   # cmp bx,[es:046Ch]
        ("rel8", 0x75, "count"),              # jne count
        b"\x89\xf8",                          # mov ax,di
        ("rel16", 0xE8, "hex"),               # call hex
        b"\x89\xf0",                          # mov ax,si
        ("rel16", 0xE8, "hex"),               # call hex
        b"\xb2\x0d", b"\xb4\x02", b"\xcd\x21",  # mov dl,0Dh / mov ah,2 / int 21h
        b"\xb2\x0a", b"\xb4\x02", b"\xcd\x21",  # mov dl,0Ah / mov ah,2 / int 21h
        b"\xb8\x00\x4c",                      # mov ax,4C00h
        b"\xcd\x21",                          # int 21h          ; exit
        "hex",                                # AX as four hex digits
        b"\xb9\x04\x00",                      # mov cx,4
        "digit",
        b"\x51",                              # push cx
        b"\xb1\x04",                          # mov cl,4
        b"\xd3\xc0",                          # rol ax,cl        ; the next nibble into AL
        b"\x59",                              # pop cx
        b"\x50",                              # push ax
        b"\x24\x0f",                          # and al,0Fh
        b"\x04\x30",                          # add al,'0'
        b"\x3c\x39",                          # cmp al,'9'
        ("rel8", 0x76, "print"),              # jbe print
        b"\x04\x07",                          # add al,7         ; 'A'-'F'
        "print",
        b"\x88\xc2",                          # mov dl,al
        b"\xb4\x02",                          # mov ah,2
        b"\xcd\x21",                          # int 21h
        b"\x58",                              # pop ax
        ("rel8", 0xE2, "digit"),              # loop digit
        b"\xc3",                              # ret
    ])
    return code


COMS = {"wshidle": idle_tsr, "busy": busy_com, "busyk": lambda: busy_com(poll=True)}


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
    c = sub.add_parser("com")
    c.add_argument("--name", choices=sorted(COMS), required=True)
    c.add_argument("--out", required=True)
    a = p.parse_args()
    if a.cmd == "disk":
        print(build_disk(a.iso, a.out, a.mb))
    elif a.cmd == "rom":
        data = owner_rom() if a.owner else option_rom(a.kb)
        with open(a.out, "wb") as f:
            f.write(data)
        print(a.out, rom_info(data))
    elif a.cmd == "com":
        data = COMS[a.name]()
        with open(a.out, "wb") as f:
            f.write(data)
        print(a.out, len(data), "bytes")
    else:
        for path, rec in Iso(a.iso).walk():
            print(f"{rec['size']:>10} {path}{'/' if rec['dir'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
