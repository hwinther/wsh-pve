"""The DOS memory-profile framework (dos_profiles.py, scenarios/dos-profile.py, the test programs in
dos_tools.py): rendering, parsers and the WAV reader without a guest (standard library only), and with
WSH_LAB_GUEST_TESTS=1 and FREEDOS_DISK (the disk tests/test_freedos.py installed, kept with FREEDOS_OUT)
every FreeDOS profile booted from a copy of that disk under the lab's QEMU and checked:

    cd e2e/sparc && python3 -m unittest -v tests/test_dos_profiles.py
    docker run --rm -v "$PWD/out:/out" -e WSH_LAB_GUEST_TESTS=1 -e FREEDOS_DISK=/out/c.raw \\
        --entrypoint python3 wsh-sparc-lab -m unittest -v tests/test_dos_profiles.py

  DOSPROF_OUT   where the evidence goes (default: FREEDOS_DISK's directory, dosprof/)
"""
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import dos_profiles as dp  # noqa: E402
import dos_tools  # noqa: E402

MSDOS_MEM = """Memory Type        Total  =   Used  +   Free
----------------  -------   -------   -------
Conventional         640K       27K      613K
Upper                 43K       22K       20K
Reserved               0K        0K        0K
Extended (XMS)*   31,573K      501K   31,072K
----------------  -------   -------   -------
Total memory      32,256K      550K   31,706K

Total under 1 MB     683K       49K      634K

Total Expanded (EMS)                4,480K (4,587,520 bytes)
Free Expanded (EMS)*                4,096K (4,194,304 bytes)

* EMM386 is using XMS memory to simulate EMS memory as needed.
  Free EMS memory may change as free XMS memory changes.

Largest executable program size       613K (628,016 bytes)
Largest free upper memory block        17K  (17,664 bytes)
MS-DOS is resident in the high memory area.
"""

FREEDOS_MEM = """Memory Type         Total      Used       Free
----------------  --------   --------   --------
Conventional          639K        19K       620K
Upper                  43K        13K        30K
Reserved              342K       342K         0K
Extended (XMS)     31,616K       495K    31,121K
----------------  --------   --------   --------
Total memory       32,640K       869K    31,771K

Total under 1 MB      682K        32K       650K

Total Expanded (EMS)                   31M (32,522,240 bytes)
Free Expanded (EMS)                    30M (31,899,648 bytes)

Largest executable program size       620K (634,864 bytes)
Largest free upper memory block        28K ( 28,416 bytes)
FreeDOS is resident in the high memory area.
"""


def wav(samples, rate=8000, ch=1, finished=True):
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    size = len(pcm) if finished else 0
    return (b"RIFF" + struct.pack("<I", 36 + size if finished else 0) + b"WAVE" + b"fmt " +
            struct.pack("<IHHIIHH", 16, 1, ch, rate, rate * ch * 2, ch * 2, 16) + b"data" +
            struct.pack("<I", size) + pcm)


class Rendering(unittest.TestCase):
    def test_every_profile_renders(self):
        for flavour in dp.FLAVOURS:
            for name, prof in dp.PROFILES[flavour].items():
                if prof.get("keep"):
                    continue
                cfg = dp.config_lines(flavour, prof)
                auto = dp.autoexec_lines(flavour, prof)
                self.assertTrue(cfg[-1].split("=")[0] in ("SHELL", "SHELLHIGH"), cfg)
                self.assertEqual(auto[-1], "CALL C:\\WSHPROF\\MEASURE.BAT")
                self.assertIn(f"SET BLASTER={dp.BLASTER}", auto)
                for line in cfg + auto:  # what DOS reads: ASCII, no tabs, short lines
                    self.assertTrue(line.isascii() and "\t" not in line and len(line) < 128, line)

    def test_load_high_or_low(self):
        ms = dp.PROFILES["msdos"]
        self.assertIn("LH C:\\DOS\\WSHIDLE.COM", dp.autoexec_lines("msdos", ms["full"]))
        self.assertIn("C:\\DOS\\WSHIDLE.COM", dp.autoexec_lines("msdos", ms["maxconv"]))
        fd = dp.PROFILES["freedos"]
        self.assertIn("LH C:\\FREEDOS\\BIN\\CTMOUSE.EXE", dp.autoexec_lines("freedos", fd["full"]))
        self.assertIn("C:\\FREEDOS\\BIN\\CTMOUSE.EXE", dp.autoexec_lines("freedos", fd["noemm"]))
        self.assertNotIn("C:\\FREEDOS\\BIN\\CTMOUSE.EXE", " ".join(dp.autoexec_lines("freedos", fd["maxconv"])))
        self.assertTrue(dp.config_lines("freedos", fd["full"])[-1].startswith("SHELLHIGH="))
        self.assertTrue(dp.config_lines("freedos", fd["noemm"])[-1].startswith("SHELL="))

    def test_extra_drivers(self):
        extra = {"drivers": {"config": ["C:\\X\\CD.SYS /D:CD001"], "autoexec": ["C:\\X\\MOUSE.EXE"]},
                 "idle": "C:\\X\\IDLE.COM", "env": ["SET SOUND=C:\\SB16"]}
        ms = dp.PROFILES["msdos"]
        self.assertIn("DEVICEHIGH=C:\\X\\CD.SYS /D:CD001", dp.config_lines("msdos", ms["ems"], extra))
        self.assertIn("DEVICE=C:\\X\\CD.SYS /D:CD001", dp.config_lines("msdos", ms["noemm"], extra))
        self.assertNotIn("C:\\X\\CD.SYS", " ".join(dp.config_lines("msdos", ms["maxconv"], extra)))
        auto = dp.autoexec_lines("msdos", ms["full"], extra)
        self.assertEqual(auto[4:8], ["SET SOUND=C:\\SB16", "LH C:\\X\\IDLE.COM", "LH C:\\X\\MOUSE.EXE",
                                     "CALL C:\\WSHPROF\\MEASURE.BAT"])

    def test_menus(self):
        names = ["full", "ems", "maxconv", "noemm"]
        cfg, auto = dp.menu_lines("msdos", names)
        self.assertEqual(cfg[0], "[MENU]")
        self.assertIn("[EMS]", cfg)
        self.assertIn("MENUITEM=MAXCONV, " + dp.PROFILES["msdos"]["maxconv"]["title"], cfg)
        self.assertIn("GOTO %CONFIG%", auto)
        self.assertEqual(auto[-2:], [":END", "CALL C:\\WSHPROF\\MEASURE.BAT"])
        self.assertEqual(auto.count("CALL C:\\WSHPROF\\MEASURE.BAT"), 1)
        cfg, auto = dp.menu_lines("freedos", names)
        self.assertIn("MENU 2 - " + dp.PROFILES["freedos"]["ems"]["title"], cfg)
        self.assertTrue(any(x.startswith("2?DEVICE=C:\\FREEDOS\\BIN\\JEMMEX.EXE FRAME=D800") for x in cfg), cfg)
        self.assertIn(":3", auto)

    def test_measure_and_run(self):
        m = dp.measure_lines("msdos")
        self.assertIn("C:\\WSHPROF\\SNDCHK.COM >C:\\WSHPROF\\OUT\\SNDCHK.TXT", m)
        self.assertNotIn("C:\\WSHPROF\\SNDCHK.COM >C:\\WSHPROF\\OUT\\SNDCHK.TXT", dp.measure_lines("msdos", sound=False))
        self.assertEqual(dp.run_lines(["D:", "DOOM"]), ["ECHO WSHPROF GAME", "D:", "DOOM"])
        self.assertEqual(dp.crlf(["A", "B"]), b"A\r\nB\r\n")
        self.assertEqual(dp.shell_autoexec("SHELL=C:\\FREEDOS\\BIN\\COMMAND.COM C:\\FREEDOS\\BIN /P=C:\\FDAUTO.BAT"),
                         "FDAUTO.BAT")
        self.assertEqual(dp.shell_autoexec("SHELL=C:\\COMMAND.COM C:\\ /E:1024 /P"), "AUTOEXEC.BAT")


class Parsers(unittest.TestCase):
    def test_msdos_mem(self):
        m = dp.parse_mem(MSDOS_MEM)
        self.assertEqual((m["conv_free"], m["upper_total"], m["upper_free"], m["xms_free"]), (613, 43, 20, 31072))
        self.assertEqual((m["ems_total"], m["ems_free"]), (4480, 4096))
        self.assertEqual((m["largest_exe"], m["largest_umb"], m["high"]), (628016, 17664, True))

    def test_freedos_mem(self):
        m = dp.parse_mem(FREEDOS_MEM)
        self.assertEqual((m["conv_free"], m["upper_free"], m["xms_free"]), (620, 30, 31121))
        self.assertEqual((m["ems_total"], m["ems_free"]), (31760, 31152))
        self.assertEqual((m["largest_exe"], m["largest_umb"], m["high"]), (634864, 28416, True))

    def test_country_separators(self):
        # COUNTRY=047 (and others) writes the thousands with a space
        text = MSDOS_MEM.replace("31,573K      501K   31,072K", "31 573K   10 765K   21 491K")
        text = text.replace("613K (628,016 bytes)", "612K (626 960 bytes)").replace("4,480K (4,587,520", "4 480K (4 587 520")
        m = dp.parse_mem(text)
        self.assertEqual((m["conv_free"], m["xms_free"], m["largest_exe"], m["ems_total"]), (613, 21491, 626960, 4480))

    def test_no_ems(self):
        m = dp.parse_mem("Conventional 640K 20K 620K\nLargest executable program size 620K (634,000 bytes)\n")
        self.assertIsNone(m["ems_total"])
        self.assertFalse(m["high"])

    def test_programs(self):
        p = dp.parse_programs({
            "VGARTRC.TXT": "VGARTRC TIMEOUT longest display enable run 0001\n",
            "VGAAR.TXT": "VGAAR 3C0h address/data state 2000 FAIL\n",
            "SNDCHK.TXT": "SNDCHK SB DSP 0405\nSNDCHK AdLib tone and PC speaker beep played\n",
            "EMSCHK.TXT": "EMSCHK pages 0118 free 0100 frame D800\n"})
        self.assertEqual(p["retrace"], ("timeout", 1))
        self.assertEqual(p["vgaar"], {"address": "20", "data": "00", "ok": False})
        self.assertEqual((p["sb_dsp"], p["sound_played"]), ("4.05", True))
        self.assertEqual(p["ems"], {"kb": 4480, "free_kb": 4096, "frame": "D800"})
        p = dp.parse_programs({"VGARTRC.TXT": "VGARTRC OK display enable run 0008", "SNDCHK.TXT": "SNDCHK SB DSP none",
                               "EMSCHK.TXT": "EMSCHK pages 07C1 free 079B frame none"})
        self.assertEqual((p["retrace"], p["sb_dsp"], p["ems"]["frame"], p["vgaar"]), (("ok", 8), "none", None, None))
        self.assertEqual(dp.parse_programs({"EMSCHK.TXT": "EMSCHK none"})["ems"], "none")

    def test_check(self):
        row = {"code": 0, "status": "passed", "conv_free": 620, "retrace": ("ok", 8),
               "vgaar": {"ok": True}, "sb_dsp": "4.05", "sound_played": True, "blaster": dp.BLASTER,
               "audio": {"sound_s": 0.8}, "screen_lit": 0.1, "ems": {"kb": 4480, "frame": "D800"}}
        ems, full = dp.PROFILES["freedos"]["ems"], dp.PROFILES["freedos"]["full"]
        self.assertEqual(dp.check(row, ems, "ok"), [])
        self.assertEqual(len(dp.check(row, full, "ok")), 1)  # a frame where the profile has none
        self.assertEqual(dp.check({**row, "ems": "none"}, full, "ok"), [])
        self.assertEqual(len(dp.check({**row, "ems": "none"}, full, "timeout")), 1)
        bad = dp.check({**row, "audio": {"sound_s": 0}, "screen_lit": 0.0, "vgaar": {"ok": False}}, ems, "ok")
        self.assertEqual(len(bad), 3, bad)

    def test_wav(self):
        quiet, loud = [0] * 800, [3000, -3000] * 400
        with tempfile.TemporaryDirectory() as d:
            for finished in (True, False):  # a killed QEMU leaves 0 as the data size
                p = os.path.join(d, "a.wav")
                with open(p, "wb") as f:
                    f.write(wav(quiet + loud + loud + quiet, finished=finished))
                self.assertEqual(dp.audio_stats(p), {"seconds": 0.4, "sound_s": 0.2, "peak": 3000})
            self.assertEqual(dp.audio_stats(os.path.join(d, "missing.wav"))["sound_s"], 0)

    def test_guest_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "qemu-d.log")
            with open(p, "w") as f:
                f.write("sb16: unknown command 0x10\nsb16: unknown command 0x11\nvga: odd 3\n")
            self.assertEqual(dp.guest_errors(p), {"count": 3, "first": ["sb#: unknown command #", "vga: odd #"]})

    def test_partition_offset(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.raw")
            mbr = bytearray(512)
            mbr[446 + 4] = 0x06
            mbr[446 + 8:446 + 12] = struct.pack("<I", 63)
            mbr[510:512] = b"\x55\xaa"
            with open(p, "wb") as f:
                f.write(mbr)
            self.assertEqual(dp.partition_offset(p), 32256)
            mbr[446 + 4] = 0x83
            with open(p, "wb") as f:
                f.write(mbr)
            with self.assertRaises(ValueError):
                dp.partition_offset(p)


class Programs(unittest.TestCase):
    """The hand-assembled test programs: they assemble, stay small, end with their messages and exit
    through INT 21h AH=4Ch."""

    def test_assemble(self):
        for name, want in (("vgartrc", b"VGARTRC TIMEOUT"), ("vgaar", b"VGAAR 3C0h"), ("sndchk", b"SNDCHK SB DSP"),
                           ("emschk", b"EMMXXXX0\x00")):
            code = dos_tools.COMS[name]()
            self.assertLess(len(code), 512, name)
            self.assertIn(want, code)
            self.assertIn(b"\xb8\x00\x4c\xcd\x21", code, name)  # mov ax,4C00h / int 21h

    def test_vgaar_sequence(self):
        code = dos_tools.attr_com()
        # 3DAh read, then 20h to 3C0h, then the data-state read of 3C0h
        self.assertTrue(code.startswith(b"\xba\xda\x03\xec\xb2\xc0\xb0\x20\xee\xec"))

    def test_opl_tables(self):
        code = dos_tools.sound_com()
        tone = b"".join(bytes(p) for p in dos_tools.OPL_TONE) + b"\xff"
        self.assertIn(tone, code)


GUEST_TESTS = os.environ.get("WSH_LAB_GUEST_TESTS") == "1"


@unittest.skipUnless(GUEST_TESTS and os.environ.get("FREEDOS_DISK"),
                     "boots FreeDOS; set WSH_LAB_GUEST_TESTS=1 and FREEDOS_DISK (from tests/test_freedos.py)")
class FreeDosProfiles(unittest.TestCase):
    """Every FreeDOS profile under `-vga std,retrace=precise`, once more under plain `std` (VGARTRC
    must time out there: QEMU's dumb retrace), and the profiles as one startup menu."""

    @classmethod
    def setUpClass(cls):
        cls.disk = os.environ["FREEDOS_DISK"]
        cls.out = os.environ.get("DOSPROF_OUT") or os.path.join(os.path.dirname(cls.disk), "dosprof")
        os.makedirs(cls.out, exist_ok=True)
        cls.rows = []

    @classmethod
    def tearDownClass(cls):
        with open(os.path.join(cls.out, "summary.md"), "w", encoding="utf-8") as f:
            f.write(dp.table(cls.rows) + "\n")
        print("\n" + dp.table(cls.rows), flush=True)

    def one(self, label, name, vga, retrace, menu=None):
        t0 = time.time()
        row = dp.run_one(self.disk, "freedos", name, os.path.join(self.out, label), menu=menu,
                         variables={"VGA": vga, "QEMU": shutil.which("qemu-system-x86_64") or "qemu-system-x86_64"})
        row["profile"] = label
        self.rows.append(row)
        print(f"\n{label}: {time.time() - t0:.0f}s, conv {row.get('conv_free')}K, ems {row.get('ems')}, "
              f"retrace {row.get('retrace')}, vgaar {row.get('vgaar')}, audio {row['audio']}", flush=True)
        self.assertEqual(dp.check(row, dp.PROFILES["freedos"][name], retrace), [], row)
        return row

    def test_profiles(self):
        conv = {n: self.one(n, n, "std,retrace=precise", "ok")["conv_free"] for n in dp.PROFILES["freedos"]}
        # loading drivers low costs conventional memory; loading them high gives it back
        self.assertGreater(conv["full"], conv["noemm"])
        self.assertGreater(conv["maxconv"], conv["noemm"])

    def test_dumb_retrace(self):
        self.one("full-std", "full", "std", "timeout")

    def test_menu(self):
        names = ["full", "ems", "maxconv", "noemm"]
        cfg = dp.menu_lines("freedos", names)
        for i, n in enumerate(names, 1):
            self.one(f"menu{i}-{n}", n, "std,retrace=precise", "ok", menu=(i, cfg))


if __name__ == "__main__":
    unittest.main()
