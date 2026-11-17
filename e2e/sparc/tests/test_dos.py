"""The DOS (x86 retro) parts that need no PVE node and no guest: the DOS targets' profiles and media,
the VM options install.py makes for them, the media swapper on the VGA text screen, the tools disk's
partition table and option ROMs (dos_tools.py), and the parsers of the first-megabyte matrix
(dos_mem.py) against output retyped from the measurements. Standard library only:

    cd e2e/sparc && python3 -m unittest -v tests/test_dos.py
"""
import os
import sys
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import dos_mem  # noqa: E402
import dos_tools  # noqa: E402
import install  # noqa: E402
import targets  # noqa: E402
import targets_dos  # noqa: E402
import vgatext  # noqa: E402

# What qemu-server accepts for an x86 VM, as far as the DOS profile uses it (upstream PVE 9).
PVE_X86_CPUS = {"486", "pentium", "pentium2", "pentium3", "qemu32", "kvm32", "qemu64", "kvm64", "host"}
PVE_NICS = {"e1000", "ne2k_isa", "ne2k_pci", "pcnet", "rtl8139", "virtio", "vmxnet3"}


class Targets(unittest.TestCase):
    def dos(self):
        return {n: t for n, t in targets.TARGETS.items() if n in targets_dos.TARGETS}

    def test_merged_into_the_catalogue(self):
        self.assertEqual(targets.problems(), [])
        self.assertIn("msdos622", targets.automated())
        self.assertIn("freedos14", targets.TARGETS)

    def test_profile(self):
        for name, t in self.dos().items():
            p = t["profile"]
            with self.subTest(target=name):
                self.assertNotIn("arch", p)  # x86_64, the default
                self.assertEqual(p["machine"], "pc")  # i440fx; isapc isn't accepted by qemu-server
                self.assertIn(p["cpu"], PVE_X86_CPUS)
                self.assertLessEqual(int(p["memory"]), 64)  # HIMEM.SYS of DOS 6.22 handles 64 MB
                self.assertEqual((p["balloon"], p["tablet"]), (0, 0))
                self.assertIn(p["net0"], PVE_NICS)
                self.assertNotEqual(p["net0"], "ne2k_isa")  # qemu-server puts it on the PCI bus: no start
                self.assertTrue(p["boot"].startswith("order=floppy0;"))
                self.assertEqual(p["boot"], f"order=floppy0;{t['disk']['bus']}")
                self.assertEqual(t["boot"], t["disk"]["bus"])
                self.assertRegex(t["disk"]["bus"], r"^ide[0-3]$")
                self.assertNotIn("serial0", p)  # the console is the VGA text screen
                self.assertEqual(t["login"]["password"], False)
                self.assertEqual(t["marker"], "C:\\WSHLAB.TXT")

    def test_media(self):
        for name, t in self.dos().items():
            with self.subTest(target=name):
                self.assertEqual(t["media"][0].get("at", "start"), "start")
                for med in t["media"]:
                    m = targets.MEDIA[med["name"]]
                    self.assertEqual((m["content"], m["size"]), ("floppy", 1474560))
                    self.assertEqual(med["drive"], "floppy0")
        names = [m["name"] for m in targets.TARGETS["msdos622"]["media"]]
        self.assertEqual(names, ["msdos622-disk1.img", "msdos622-disk2.img", "msdos622-disk3.img"])

    def test_vm_params_floppies_read_only(self):
        t = targets.TARGETS["msdos622"]
        vols = {m["name"]: f"local:floppy/{m['name']}" for m in t["media"]}
        a = types.SimpleNamespace(bridge="vmbr0", storage="local", vmid="130", name=None, target="msdos622")
        p = install.vm_params(t, a, vols, None)
        self.assertEqual(p["floppy0"], "local:floppy/msdos622-disk1.img,ro=1")
        self.assertEqual(p["ide0"], "local:1,format=raw")
        self.assertEqual(p["net0"], "ne2k_pci,bridge=vmbr0")
        self.assertEqual(p["boot"], "order=floppy0;ide0")

    def test_description_has_no_password(self):
        a = types.SimpleNamespace(target="msdos622", vmid="130", user=None, ip=None, out="/x", root_password=None,
                                  user_password=None, hostname=None)
        job = install.Job.__new__(install.Job)
        job.a, job.target, job.root_password, job.hostname = a, targets.TARGETS["msdos622"], "wshlab", "-"
        job.started = __import__("datetime").datetime(2026, 11, 17)
        job.media = []
        d = job.description()
        self.assertIn("Login: none", d)
        self.assertNotIn("wshlab", d)
        self.assertIn("Marker: C:\\WSHLAB.TXT", d)


def text_screen(text):
    lines = text.splitlines()
    buf = b"".join(x.encode("cp437").ljust(80)[:80] for x in lines + [""] * (25 - len(lines)))
    raw = bytes(b for ch in buf for b in (ch, 7))
    info = vgatext.parse_bda(b"\x00" * 0x49 + b"\x03" + b"\x50\x00" + b"\x00" * 0x38 + b"\x18" + bytes(0x7B))
    return vgatext.Screen(info, raw, True, 0xB8000)


class FakeVga:
    """What MediaSwapper uses of a DOS VM: vga_screen() and change_medium(); no serial console."""
    ser = None

    def __init__(self):
        self.screen, self.changes = text_screen(""), []

    def vga_screen(self):
        return self.screen

    def change_medium(self, drive, volume):
        self.changes.append((drive, volume))


class VgaSwapper(unittest.TestCase):
    def test_prompts_on_the_screen(self):
        c = FakeVga()
        s = install.MediaSwapper(c, [(r"Setup Disk #2", "floppy0", "local:floppy/d2.img,ro=1"),
                                     (r"Setup Disk #3", "floppy0", "local:floppy/d3.img,ro=1")])
        self.assertEqual(s.screen, "vga")
        c.screen = text_screen("Please insert the following disk in drive A:\n\n   Setup Disk #2")
        time.sleep(1.2)
        self.assertEqual(c.changes, [("floppy0", "local:floppy/d2.img,ro=1")])  # once, though still shown
        c.screen = text_screen("copying ... 58%")
        time.sleep(0.8)
        c.screen = text_screen("Please insert the following disk in drive A:\n\n   Setup Disk #3")
        s.thread.join(5)
        s.stop.set()
        self.assertEqual([v for _, v in c.changes], ["local:floppy/d2.img,ro=1", "local:floppy/d3.img,ro=1"])

    def test_same_prompt_twice_needs_it_gone_in_between(self):
        c = FakeVga()
        s = install.MediaSwapper(c, [(r"Insert diskette", "floppy0", "a"), (r"Insert diskette", "floppy0", "b")])
        c.screen = text_screen("Insert diskette #2")
        time.sleep(1.2)
        self.assertEqual(len(c.changes), 1)
        c.screen = text_screen("reading")
        time.sleep(0.8)
        c.screen = text_screen("Insert diskette containing file A:\\FREEDOS.024")
        s.thread.join(5)
        s.stop.set()
        self.assertEqual([v for _, v in c.changes], ["a", "b"])

    def test_serial_machines_keep_the_serial_swapper(self):
        m = types.SimpleNamespace(ser=object(), serial_cursor=lambda: 0, vga_screen=lambda: None,
                                  serial_wait=lambda *a, **k: {"matched": False, "cursor": 0})
        s = install.MediaSwapper(m, [])
        s.stop.set()
        self.assertEqual(s.screen, "serial")


class Tools(unittest.TestCase):
    def test_option_rom(self):
        for kb in (4, 32, 100):
            rom = dos_tools.option_rom(kb)
            self.assertEqual(len(rom), kb * 1024)
            self.assertEqual(rom[:4], b"\x55\xaa" + bytes([kb * 2]) + b"\xcb")
            self.assertEqual(sum(rom) & 0xFF, 0)
            self.assertEqual(dos_tools.rom_info(rom), {"bytes": kb * 1024, "signature": True,
                                                       "declared": kb * 1024, "checksum_ok": True})
        self.assertRaises(ValueError, dos_tools.option_rom, 128)

    def test_the_owners_line_writes_no_rom(self):
        rom = dos_tools.owner_rom()
        self.assertEqual(len(rom), 102403)
        self.assertEqual(rom[:8], bytes.fromhex("55c2aac388c38b6e"))
        self.assertFalse(dos_tools.rom_info(rom)["signature"])
        # the bytes it meant: valid, 200 blocks, the 0x6E fixes the checksum
        meant = b"\x55\xaa\xc8\xcb\x6e" + bytes(100 * 1024 - 5)
        self.assertEqual(dos_tools.rom_info(meant)["checksum_ok"], True)

    def test_mbr(self):
        total = 32 * 1024 * 1024 // 512
        total -= total % (16 * 63)
        mbr, n = dos_tools.mbr(total)
        self.assertEqual(len(mbr), 512)
        self.assertEqual(mbr[510:], b"\x55\xaa")
        e = mbr[446:462]
        self.assertEqual((e[0], e[4]), (0x80, 0x06))
        self.assertEqual(int.from_bytes(e[8:12], "little"), 63)
        self.assertEqual(int.from_bytes(e[12:16], "little"), n)
        self.assertEqual(e[1:4], bytes([1, 1, 0]))  # CHS 0/1/1: head 1, sector 1

    def test_tool_list(self):
        self.assertIn("UMASCAN.COM", dos_tools.TOOLS)
        for name in dos_tools.TOOLS:
            base, ext = name.split(".")
            self.assertTrue(len(base) <= 8 and len(ext) <= 3 and name == name.upper())


SEABIOS_LOG = """SeaBIOS (version rel-1.17.0-0-gb52ca86e094d-prebuilt.qemu.org)
Running option rom at c000:0003
Running option rom at ca00:0003
Searching bootorder for: /rom@genroms/kvmvapic.bin
Running option rom at cb00:0003
Space available for UMB: cd800-e9000, f4e20-f51d0
"""

# MEM /D of MS-DOS 6.22 with EMM386 NOEMS and DOS=HIGH,UMB, retyped (the parts the parser reads)
MEM_D = """Upper Memory Detail:

  Segment  Region       Total        Name         Type
  -------  ------  ----------------  -----------  --------
   0CE00       1      5,232    (5K)  IO           System Data
   0CF4A       1    101,216   (99K)  MSDOS        -- Free --

Memory Summary:

  Type of Memory       Total   =    Used    +    Free
  ----------------  ----------   ----------   ----------
  Conventional         654,336       22,000      632,336
  Upper                106,448        5,232      101,216
  Reserved                   0            0            0
  Extended (XMS)    32,366,592    2,162,688   30,203,904

  Largest executable program size        632,240   (617K)
  Largest free upper memory block        101,216    (99K)
  MS-DOS is resident in the high memory area.
"""

EMM386 = """  Available expanded memory  . . . . . . . .   256 KB
  Page frame segment . . . . . . . . . . . . D000 H
EMM386 Active.
"""


def umascan(c, d, e):
    return "\n".join([
        "│    F000 RRRRRRRR RRRRRRRR RRRRRRRR RRRRRRRR                                  │",
        f"│    E000 {e[:8]} {e[8:16]} {e[16:24]} {e[24:]}        RRRR  ROM                 │",
        f"│    D000 {d[:8]} {d[8:16]} {d[16:24]} {d[24:]}        ++++  RAM                 │",
        f"│    C000 {c[:8]} {c[8:16]} {c[16:24]} {c[24:]}        VVVV  Video Buffer        │",
        "│    B000 VVVVVVVV VVVVVVVV VVVVVVVV VVVVVVVV        EEEE  EMS Page Frame      │"])


class Matrix(unittest.TestCase):
    def test_seabios(self):
        sb = dos_mem.parse_seabios("SeaBIOS (version x)\nRunning option rom at c000:0003\n" + SEABIOS_LOG)
        self.assertEqual(sb["roms"], ["C0000", "CA000", "CB000"])  # the last boot only
        self.assertEqual((sb["umb_gap"], sb["gap_kb"]), ("cd800-e9000", 110))
        self.assertEqual(sb["genroms"], ["kvmvapic.bin"])

    def test_seabios_two_boots(self):
        boot = ("Scan for VGA option rom\nRunning option rom at c000:0003\nSeaBIOS (version x)\n"
                "Scan for option roms\nRunning option rom at {nic}:0003\n"
                "Space available for UMB: {gap}, f4e20-f51d0\n")
        sb = dos_mem.parse_seabios(boot.format(nic="ca00", gap="cd800-e9000")
                                   + boot.format(nic="cb00", gap="ce800-e9000"))
        self.assertEqual(sb["roms"], ["C0000", "CB000"])  # the banner after the VGA ROM doesn't cut it off
        self.assertEqual(sb["umb_gap"], "ce800-e9000")

    def test_gap_to_emm386_range(self):
        self.assertEqual(dos_mem.gap_range("cd800-e9000"), ("CE00", "E8FF"))
        self.assertEqual(dos_mem.config_lines("emm-noems-gap", "cd800-e9000")[1],
                         "DEVICE=C:\\DOS\\EMM386.EXE NOEMS I=CE00-E8FF")
        self.assertEqual(dos_mem.config_lines("emm-noems-e", "cd800-e9000")[1],
                         "DEVICE=C:\\DOS\\EMM386.EXE NOEMS I=CE00-EFFF")
        self.assertRaises(ValueError, dos_mem.config_lines, "emm-ram-gap", "")

    def test_mem(self):
        m = dos_mem.parse_mem(MEM_D)
        self.assertEqual((m["conv_free"], m["largest_exe"], m["largest_umb"]), (632336, 632240, 101216))
        self.assertEqual((m["upper_total"], m["upper_used"], m["upper_free"]), (106448, 5232, 101216))
        self.assertEqual(m["umb_free_blocks"], [("0CF4A", 101216)])
        self.assertEqual(m["umb_blocks"][0], ("0CE00", 5232, "IO", "System Data"))
        self.assertTrue(m["high"])

    def test_emm386(self):
        e = dos_mem.parse_emm386(EMM386)
        self.assertEqual((e["active"], e["page_frame"], e["ems_kb"]), (True, "D000", 256))
        self.assertIsNone(dos_mem.parse_emm386("Expanded memory services unavailable.\nEMM386 Active.")["page_frame"])

    def test_umascan(self):
        c = "R" * 22 + "+" * 6 + " " * 4
        u = dos_mem.parse_umascan(umascan(c, " " * 32, " " * 16 + "+" * 16))
        self.assertEqual([(r["kind"], r["start"], r["kb"]) for r in u["runs"]],
                         [("R", "C0000", 44), ("+", "CB000", 12), (".", "CE000", 104), ("+", "E8000", 32)])
        self.assertEqual((u["largest_unused_kb"], u["largest_ram_kb"]), (104, 32))


if __name__ == "__main__":
    unittest.main()
