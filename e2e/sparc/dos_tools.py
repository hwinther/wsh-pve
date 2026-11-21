#!/usr/bin/env python3
"""The DOS "tools" disk for diagnostics, and test option ROMs.

    dos_tools.py disk --iso /mnt/sparc/iso/dos_drivers.iso --out tools.raw [--mb 32]
    dos_tools.py rom --kb 100 --out dummy100k.rom          # a valid, checksummed dummy option ROM
    dos_tools.py rom --owner --out owner-dummy.rom          # what the owner's Python 3 line writes
    dos_tools.py ls --iso ...                               # what the ISO has
    dos_tools.py com --name wshidle --out WSHIDLE.COM        # the HLT idle TSR (or busy, busyk, vgartrc, vgaar, sndchk, emschk)

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

`com` writes one of the small DOS programs, assembled here from hand-encoded 8086 instructions (a
few hundred bytes at most, so no assembler is needed and every byte sits next to its instruction).
The memory-profile tests (dos_profiles.py) use VGARTRC.COM (VGA retrace), VGAAR.COM (the 3C0h read),
SNDCHK.COM (Sound Blaster DSP, AdLib, PC speaker) and EMSCHK.COM (EMS pages and page frame); see
their functions below. The others:
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


TICK = b"\x1e\x6c\x04"                         # ModRM + disp16 for [046Ch], the BIOS tick count


def _print(label):
    """Print the $-terminated string at `label` (INT 21h AH=09h)."""
    return [("imm16", b"\xba", _at(label)), b"\xb4\x09", b"\xcd\x21"]   # mov dx,label / mov ah,9 / int 21h


def _exit(code):
    return [b"\xb8" + bytes([code, 0x4c]), b"\xcd\x21"]                  # mov ax,4C00h+code / int 21h


def _hex_ax():
    """The subroutine `hex`: AX as four hex digits (BUSY.COM's, as a callable block)."""
    return [
        "hex",
        b"\xb9\x04\x00",                      # mov cx,4
        "hex_digit",
        b"\x51", b"\xb1\x04", b"\xd3\xc0", b"\x59",  # push cx / mov cl,4 / rol ax,cl / pop cx
        b"\x50",                              # push ax
        b"\x24\x0f", b"\x04\x30", b"\x3c\x39",  # and al,0Fh / add al,'0' / cmp al,'9'
        ("rel8", 0x76, "hex_print"),          # jbe hex_print
        b"\x04\x07",                          # add al,7
        "hex_print",
        b"\x88\xc2", b"\xb4\x02", b"\xcd\x21",  # mov dl,al / mov ah,2 / int 21h
        b"\x58",                              # pop ax
        ("rel8", 0xE2, "hex_digit"),          # loop hex_digit
        b"\xc3",                              # ret
    ]


def _wait_ticks():
    """The subroutine `wait_ticks`: wait CX BIOS ticks (55 ms each); keeps ES."""
    return [
        "wait_ticks",
        b"\x06", b"\x31\xc0", b"\x8e\xc0",    # push es / xor ax,ax / mov es,ax
        "wait_next",
        b"\x26\x8b" + TICK,                   # mov bx,[es:046Ch]
        "wait_same",
        b"\x26\x3b" + TICK,                   # cmp bx,[es:046Ch]
        ("rel8", 0x74, "wait_same"),          # je wait_same
        ("rel8", 0xE2, "wait_next"),          # loop wait_next
        b"\x07", b"\xc3",                     # pop es / ret
    ]


RETRACE_RUN = 8


def retrace_com():
    """VGARTRC.COM: does the VGA ever report "display enabled" (input status 1, port 3DAh, bit 0 clear)
    on several reads in a row? A real VGA does for most of every scan line; QEMU's default retrace
    emulation (`dumb`) flips bits 0 and 3 on every read, so no two reads in a row agree, and a game that
    waits for a stretch of display enable (Wolfenstein 3D) waits for ever. QEMU's precise emulation
    (`-vga std,retrace=precise`, qemu-server `vga: std,retrace=precise`) reports a CRT's timing.

    Polls for RETRACE_RUN reads in a row with bit 0 clear, for at most one second (18 ticks); prints
    "VGARTRC OK" or "VGARTRC TIMEOUT", then the longest run seen in hex, and exits with errorlevel 0
    or 1."""
    code, _ = assemble([
        b"\x31\xc0", b"\x8e\xc0",             # xor ax,ax / mov es,ax
        b"\x26\x8b" + TICK,                   # mov bx,[es:046Ch]
        b"\x83\xc3\x12",                      # add bx,18        ; the deadline: one second
        b"\xba\xda\x03",                      # mov dx,3DAh
        b"\x31\xf6",                          # xor si,si        ; the longest run so far
        "restart",
        b"\x31\xc9",                          # xor cx,cx        ; this run
        "next",
        b"\x26\x3b" + TICK,                   # cmp bx,[es:046Ch]
        ("rel8", 0x74, "timeout"),            # je timeout
        b"\xec",                              # in al,dx
        b"\xa8\x01",                          # test al,1        ; 1: blanking (retrace)
        ("rel8", 0x75, "restart"),            # jnz restart
        b"\x41",                              # inc cx
        b"\x39\xf1",                          # cmp cx,si
        ("rel8", 0x76, "shorter"),            # jbe shorter
        b"\x89\xce",                          # mov si,cx
        "shorter",
        b"\x83\xf9" + bytes([RETRACE_RUN]),   # cmp cx,RETRACE_RUN
        ("rel8", 0x72, "next"),               # jb next
        *_print("ok"),
        b"\x89\xf0", ("rel16", 0xE8, "hex"),  # mov ax,si / call hex
        *_print("crlf"),
        *_exit(0),
        "timeout",
        *_print("to"),
        b"\x89\xf0", ("rel16", 0xE8, "hex"),  # mov ax,si / call hex
        *_print("crlf"),
        *_exit(1),
        *_hex_ax(),
        "ok", b"VGARTRC OK display enable run $",
        "to", b"VGARTRC TIMEOUT longest display enable run $",
        "crlf", b"\r\n$",
    ])
    return code


def attr_com():
    """VGAAR.COM: does a read of the attribute controller's address register (port 3C0h) return the
    address in the flip-flop's data state? A VGA (and DOSBox) does; QEMU before pve-qemu wsh/0051
    returned 0 there, and The Incredible Machine, which saves the address that way while it loads the
    palette and writes it back, turned the display off (the palette address source bit, 20h).

    Reads 3DAh (flip-flop to the address state), writes 20h (index 0 with PAS) to 3C0h, reads 3C0h (data
    state), reads 3DAh and 3C0h again (address state), writes 20h back and leaves the flip-flop in the
    address state, so the display stays on whatever the result. Prints "VGAAR 3C0h address/data state
    XXYY OK" (XX the address state's value, YY the data state's; both 20 on a VGA) or "... FAIL", and
    exits with errorlevel 0 or 1."""
    code, _ = assemble([
        b"\xba\xda\x03", b"\xec",             # mov dx,3DAh / in al,dx
        b"\xb2\xc0",                          # mov dl,0C0h      ; DX = 3C0h
        b"\xb0\x20", b"\xee",                 # mov al,20h / out dx,al ; now in the data state
        b"\xec", b"\x88\xc3",                 # in al,dx / mov bl,al
        b"\xb2\xda", b"\xec",                 # mov dl,0DAh / in al,dx ; the address state
        b"\xb2\xc0", b"\xec", b"\x88\xc7",    # mov dl,0C0h / in al,dx / mov bh,al
        b"\xb0\x20", b"\xee",                 # mov al,20h / out dx,al ; PAS on, index 0
        b"\xb2\xda", b"\xec",                 # mov dl,0DAh / in al,dx ; leave it in the address state
        *_print("msg"),
        b"\x89\xd8", ("rel16", 0xE8, "hex"),  # mov ax,bx / call hex
        b"\x80\xfb\x20",                      # cmp bl,20h
        ("rel8", 0x75, "fail"),               # jne fail
        *_print("ok"),
        *_exit(0),
        "fail",
        *_print("bad"),
        *_exit(1),
        *_hex_ax(),
        "msg", b"VGAAR 3C0h address/data state $",
        "ok", b" OK\r\n$",
        "bad", b" FAIL\r\n$",
    ])
    return code


def ems_com():
    """EMSCHK.COM: is there an expanded memory manager (the EMMXXXX0 device), how many 16K pages does
    it have and where is its page frame (INT 67h AH=42h and AH=41h)? A game that wants EMS needs the
    frame; JEMM386/JEMMEX with NOEMS still have pages (for VCPI) but no frame, and EMM386 given `I=`
    over the frame's area has neither. Prints "EMSCHK pages TTTT free FFFF frame SSSS" (hex; "frame
    none" without one) or "EMSCHK none" and exits with errorlevel 0 or 1."""
    code, _ = assemble([
        b"\xb8\x00\x3d",                      # mov ax,3D00h
        ("imm16", b"\xba", _at("dev")),       # mov dx,dev
        b"\xcd\x21",                          # int 21h          ; open EMMXXXX0
        ("rel8", 0x72, "none"),               # jc none
        b"\x89\xc3", b"\xb4\x3e", b"\xcd\x21",  # mov bx,ax / mov ah,3Eh / int 21h ; close
        b"\xb4\x42", b"\xcd\x67",             # mov ah,42h / int 67h ; BX free, DX total pages
        b"\x08\xe4",                          # or ah,ah
        ("rel8", 0x75, "none"),               # jnz none
        b"\x89\xd6", b"\x89\xdf",             # mov si,dx / mov di,bx
        *_print("pages"),
        b"\x89\xf0", ("rel16", 0xE8, "hex"),  # mov ax,si / call hex
        *_print("free"),
        b"\x89\xf8", ("rel16", 0xE8, "hex"),  # mov ax,di / call hex
        b"\xb4\x41", b"\xcd\x67",             # mov ah,41h / int 67h ; BX = the frame's segment
        b"\x08\xe4",                          # or ah,ah
        ("rel8", 0x75, "noframe"),            # jnz noframe
        b"\x53",                              # push bx
        *_print("frame"),
        b"\x58", ("rel16", 0xE8, "hex"),      # pop ax / call hex
        *_print("crlf"),
        *_exit(0),
        "noframe",
        *_print("noframe_msg"),
        *_exit(0),
        "none",
        *_print("none_msg"),
        *_exit(1),
        *_hex_ax(),
        "dev", b"EMMXXXX0\x00",
        "pages", b"EMSCHK pages $",
        "free", b" free $",
        "frame", b" frame $",
        "noframe_msg", b" frame none\r\n$",
        "none_msg", b"EMSCHK none\r\n$",
        "crlf", b"\r\n$",
    ])
    return code


# AdLib (OPL2) channel 0: modulator (operator 0) and carrier (operator 3), about 440 Hz; then key off.
OPL_TONE = [(0x20, 0x01), (0x40, 0x10), (0x60, 0xF0), (0x80, 0x77), (0xA0, 0x98),
            (0x23, 0x01), (0x43, 0x00), (0x63, 0xF0), (0x83, 0x77), (0xB0, 0x31)]
OPL_OFF = [(0xB0, 0x11)]


def sound_com():
    """SNDCHK.COM: the sound devices a DOS game finds. Resets the Sound Blaster DSP at 220h (226h, then
    AAh at 22Ah), asks for its version (E1h: 4.05 for QEMU's SB16) and prints "SNDCHK SB DSP 0405" or
    "SNDCHK SB DSP none"; plays a tone on the AdLib (OPL2 at 388h) for half a second and a 1 kHz beep on
    the PC speaker (PIT channel 2, port 61h) for a third of a second, which a host-side recording
    (QEMU's wav audiodev) picks up. Only fixed ports (220h, 388h), no BLASTER parsing."""
    def table(pairs):
        return b"".join(bytes(p) for p in pairs) + b"\xff"

    code, _ = assemble([
        b"\xfc",                              # cld              ; LODSB forwards
        b"\xba\x26\x02",                      # mov dx,226h
        b"\xb0\x01", b"\xee",                 # mov al,1 / out dx,al
        b"\xb9\x20\x00",                      # mov cx,32
        "rst_wait", b"\xec", ("rel8", 0xE2, "rst_wait"),  # in al,dx / loop
        b"\x30\xc0", b"\xee",                 # xor al,al / out dx,al
        ("rel16", 0xE8, "dsp_read"),          # call dsp_read
        b"\x3c\xaa",                          # cmp al,0AAh
        ("rel8", 0x75, "nosb"),               # jne nosb
        b"\xb2\x2c",                          # mov dl,2Ch       ; 22Ch, the write port
        b"\xb9\xff\xff",                      # mov cx,0FFFFh
        "wr_wait", b"\xec", b"\xa8\x80",      # in al,dx / test al,80h
        ("rel8", 0xE0, "wr_wait"),            # loopnz wr_wait   ; until ready (bit 7 clear)
        b"\xb0\xe1", b"\xee",                 # mov al,0E1h / out dx,al ; DSP version
        ("rel16", 0xE8, "dsp_read"), b"\x88\xc7",   # call dsp_read / mov bh,al
        ("rel16", 0xE8, "dsp_read"), b"\x88\xc3",   # call dsp_read / mov bl,al
        *_print("sb"),
        b"\x89\xd8", ("rel16", 0xE8, "hex"),  # mov ax,bx / call hex
        *_print("crlf"),
        ("rel8", 0xEB, "adlib"),              # jmp short adlib
        "nosb",
        *_print("none"),
        "adlib",
        ("imm16", b"\xbe", _at("tone")),      # mov si,tone
        ("rel16", 0xE8, "opl"),               # call opl
        b"\xb9\x09\x00",                      # mov cx,9         ; half a second
        ("rel16", 0xE8, "wait_ticks"),
        ("imm16", b"\xbe", _at("off")),       # mov si,off
        ("rel16", 0xE8, "opl"),
        b"\xb0\xb6", b"\xe6\x43",             # mov al,0B6h / out 43h,al ; PIT channel 2, square wave
        b"\xb8\xa9\x04",                      # mov ax,1193      ; 1193182 Hz / 1193 = 1 kHz
        b"\xe6\x42", b"\x88\xe0", b"\xe6\x42",  # out 42h,al / mov al,ah / out 42h,al
        b"\xe4\x61", b"\x0c\x03", b"\xe6\x61",  # in al,61h / or al,3 / out 61h,al ; speaker on
        b"\xb9\x06\x00",                      # mov cx,6
        ("rel16", 0xE8, "wait_ticks"),
        b"\xe4\x61", b"\x24\xfc", b"\xe6\x61",  # in al,61h / and al,0FCh / out 61h,al ; off
        *_print("played"),
        *_exit(0),
        "dsp_read",                           # AL = the next byte from the DSP (22Eh bit 7, then 22Ah)
        b"\xba\x2e\x02",                      # mov dx,22Eh
        b"\xb9\xff\xff",                      # mov cx,0FFFFh
        "rd_wait", b"\xec", b"\xa8\x80",      # in al,dx / test al,80h
        ("rel8", 0xE1, "rd_wait"),            # loopz rd_wait    ; until a byte is there (bit 7 set)
        b"\xb2\x2a", b"\xec", b"\xc3",        # mov dl,2Ah / in al,dx / ret
        "opl",                                # write the (register, value) pairs at SI, up to FFh
        b"\xac",                              # lodsb
        b"\x3c\xff",                          # cmp al,0FFh
        ("rel8", 0x74, "opl_done"),           # je opl_done
        b"\xba\x88\x03", b"\xee",             # mov dx,388h / out dx,al
        ("rel16", 0xE8, "opl_delay"),
        b"\xac", b"\x42", b"\xee",            # lodsb / inc dx / out dx,al
        ("rel16", 0xE8, "opl_delay"),
        ("rel8", 0xEB, "opl"),                # jmp short opl
        "opl_done", b"\xc3",
        "opl_delay",                          # 36 status reads, as the AdLib wants between writes
        b"\x51", b"\xb9\x24\x00",             # push cx / mov cx,36
        "opl_d", b"\xec", ("rel8", 0xE2, "opl_d"),  # in al,dx / loop
        b"\x59", b"\xc3",                     # pop cx / ret
        *_wait_ticks(),
        *_hex_ax(),
        "tone", table(OPL_TONE),
        "off", table(OPL_OFF),
        "sb", b"SNDCHK SB DSP $",
        "none", b"SNDCHK SB DSP none\r\n$",
        "played", b"SNDCHK AdLib tone and PC speaker beep played\r\n$",
        "crlf", b"\r\n$",
    ])
    return code


COMS = {"wshidle": idle_tsr, "busy": busy_com, "busyk": lambda: busy_com(poll=True),
        "vgartrc": retrace_com, "vgaar": attr_com, "sndchk": sound_com, "emschk": ems_com}


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
