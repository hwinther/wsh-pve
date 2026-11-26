"""Unit tests for win98_test.py's parsing and disk logic (no QEMU, no Windows, no mtools).

    python3 -m unittest discover -s e2e/3dfx/win98/tests -v
"""
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import win98_test as w  # noqa: E402


def scene():
    with open(w.SCENE_H) as f:
        return w.parse_scene(f.read())


def image(sc, fill=(0, 0, 0x80)):
    """A W x H RGB image of the clear colour with every probe's expected colour at its pixel."""
    pix = bytearray(bytes(fill) * (sc["w"] * sc["h"]))
    for p in sc["probes"]:
        o = (p["y"] * sc["w"] + p["x"]) * 3
        pix[o:o + 3] = bytes(p["rgb"])
    return pix


class Scene(unittest.TestCase):
    def test_probes_from_scene_h(self):
        sc = scene()
        self.assertEqual((sc["w"], sc["h"]), (640, 480))
        self.assertEqual(sc["tolerance"], 24)
        self.assertEqual(len(sc["probes"]), 8)
        first = sc["probes"][0]
        self.assertEqual((first["what"], first["x"], first["y"], first["rgb"]), ("clear, top left", 10, 10, [0, 0, 0x80]))
        red = next(p for p in sc["probes"] if p["what"] == "red triangle")
        self.assertEqual((red["x"], red["y"], red["rgb"]), (166, 293, [255, 0, 0]))

    def test_gouraud_expectations_match_the_c_code(self):
        # the "want" values glide-guest.c and glidetst.exe print for the Gouraud probes
        sc = scene()
        want = {(320, 407): [0x55, 0x54, 0x56], (400, 452): [0x13, 0x0c, 0xe0], (320, 320): [0x10, 0xde, 0x11]}
        for p in sc["probes"]:
            if p["gouraud"]:
                self.assertEqual(p["rgb"], want[(p["x"], p["y"])], p["what"])

    def test_parse_scene_rejects_text_without_probes(self):
        with self.assertRaises(ValueError):
            w.parse_scene("#define W 640\n")


class Ppm(unittest.TestCase):
    def test_parse(self):
        data = b"P6\n# QEMU\n2 1\n255\n" + bytes([1, 2, 3, 4, 5, 6])
        self.assertEqual(w.parse_ppm(data), (2, 1, bytes([1, 2, 3, 4, 5, 6])))

    def test_truncated(self):
        with self.assertRaises(ValueError):
            w.parse_ppm(b"P6\n2 2\n255\n" + bytes(6))
        with self.assertRaises(ValueError):
            w.parse_ppm(b"P5\n1 1\n255\n\x00")

    def test_check_probes_frame_matches(self):
        sc = scene()
        res, bad = w.check_probes(sc, sc["w"], sc["h"], image(sc))
        self.assertEqual(bad, 0)
        self.assertTrue(all(r["ok"] for r in res))

    def test_check_probes_tolerance_and_mismatch(self):
        sc = scene()
        pix = image(sc)
        red = next(p for p in sc["probes"] if p["what"] == "red triangle")
        o = (red["y"] * sc["w"] + red["x"]) * 3
        pix[o:o + 3] = bytes([255 - 24, 24, 0])  # just within the tolerance
        self.assertEqual(w.check_probes(sc, sc["w"], sc["h"], pix)[1], 0)
        pix[o:o + 3] = bytes([255 - 25, 0, 0])
        res, bad = w.check_probes(sc, sc["w"], sc["h"], pix)
        self.assertEqual(bad, 1)
        self.assertEqual(next(r for r in res if not r["ok"])["got"], [230, 0, 0])

    def test_check_probes_desktop_is_not_the_scene(self):
        sc = scene()
        # a grey 1024x768 desktop: at most the clear-colour probes could match, none here
        res, bad = w.check_probes(sc, 1024, 768, bytes([0xc0] * (1024 * 768 * 3)))
        self.assertEqual(bad, len(sc["probes"]))

    def test_check_probes_scaled(self):
        # the scene stretched to 1024x768 (an SDL window at the desktop's size): nearest pixel
        sc = scene()
        small = image(sc)
        big = bytearray(1024 * 768 * 3)
        for y in range(768):
            sy = y * 480 // 768
            for x in range(1024):
                o, so = (y * 1024 + x) * 3, (sy * 640 + x * 640 // 1024) * 3
                big[o:o + 3] = small[so:so + 3]
        res, bad = w.check_probes(sc, 1024, 768, bytes(big), scaled=True)
        self.assertEqual(bad, 0, [r for r in res if not r["ok"]])
        self.assertEqual((res[3]["x"], res[3]["y"]), (int(166.5 * 1.6), int(293.5 * 1.6)))

    def test_xwd(self):
        # 2x1 ZPixmap, 32 bits per pixel, LSB first, masks ff0000/ff00/ff, window name "QEMU\0"
        name = b"QEMU\x00"
        header = struct.pack(">25I", 100 + len(name), 7, 2, 24, 2, 1, 0, 0, 32, 0, 32, 32, 8, 4,
                             0xff0000, 0xff00, 0xff, 8, 0, 0, 2, 1, 0, 0, 0)
        img = struct.pack("<II", 0x00ff0000, 0x00102030)
        self.assertEqual(w.parse_xwd(header + name + img), (2, 1, bytes([255, 0, 0, 0x10, 0x20, 0x30])))
        with self.assertRaises(ValueError):
            w.parse_xwd(header[:50])
        with self.assertRaises(ValueError):
            w.parse_xwd(header + name + img[:4])

    def test_check_probes_smaller_image(self):
        sc = scene()
        res, bad = w.check_probes(sc, 320, 200, bytes(320 * 200 * 3))
        self.assertEqual(bad, len(sc["probes"]))
        self.assertIsNone(res[1]["got"])  # (630, 10) is outside


class SerialLog(unittest.TestCase):
    def test_lines_split_across_reads(self):
        s = w.Serial("/nonexistent")
        self.assertEqual(s.feed(b"\x00noise\r\nGLIDE2: STA"), [])
        self.assertEqual(s.feed(b"RT GLIDE2X.DLL\r\nGLIDE2: FRAME\r\nW3DRUN: DONE 1 programs\r\nOPENGL: PA"),
                         [("GLIDE2", "START GLIDE2X.DLL"), ("GLIDE2", "FRAME"), ("W3DRUN", "DONE 1 programs")])
        self.assertEqual(s.feed(b"SS\n"), [("OPENGL", "PASS")])
        self.assertEqual(len(s.lines), 4)

    def test_poll_missing_file(self):
        self.assertEqual(w.Serial("/nonexistent/serial.log").poll(), [])

    def test_poll_reads_growth(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "serial.log")
            s = w.Serial(p)
            with open(p, "wb") as f:
                f.write(b"GLIDE3: FRAME\r\n")
            self.assertEqual(s.poll(), [("GLIDE3", "FRAME")])
            with open(p, "ab") as f:
                f.write(b"GLIDE3: CLOSED\r\n")
            self.assertEqual(s.poll(), [("GLIDE3", "CLOSED")])

    def test_bench(self):
        self.assertEqual(w.parse_bench("BENCH 300 frames in 184 ms, 1630.4 fps"),
                         {"frames": 300, "ms": 184, "fps": 1630.4})
        self.assertIsNone(w.parse_bench("FRAME"))

    def test_verdicts(self):
        self.assertEqual(w.verdict_of("PASS"), "PASS")
        self.assertEqual(w.verdict_of("FAIL 2"), "FAIL 2")
        self.assertEqual(w.verdict_of("ERROR grSstWinOpen (no Glide device)"), "ERROR grSstWinOpen (no Glide device)")
        self.assertIsNone(w.verdict_of("ok   guest LFB back  red triangle"))
        self.assertIsNone(w.verdict_of("FAIL grLfbReadRegion of the back buffer"))


def fat32_disk(path, clean):
    """A tiny raw disk: an MBR with one FAT32 LBA partition at sector 63 and its boot sector and
    two FATs (only what clean_bits() reads)."""
    mbr = bytearray(512)
    mbr[446 + 4] = 0x0C
    struct.pack_into("<I", mbr, 446 + 8, 63)
    struct.pack_into("<I", mbr, 446 + 12, 2000)
    mbr[510:512] = b"\x55\xaa"
    boot = bytearray(512)
    struct.pack_into("<H", boot, 11, 512)
    struct.pack_into("<H", boot, 14, 32)
    boot[16] = 2
    struct.pack_into("<I", boot, 36, 8)
    fat1 = 0x0FFFFFFF if clean else 0x07FFFFFF
    with open(path, "wb") as f:
        f.write(mbr + bytes(62 * 512) + boot)
        for i in range(2):
            f.seek(63 * 512 + (32 + i * 8) * 512)
            f.write(struct.pack("<II", 0x0FFFFFF8, fat1))
        f.seek(63 * 512 + 64 * 512)
        f.write(bytes(512))


class Disk(unittest.TestCase):
    def test_partition_offset(self):
        mbr = bytearray(512)
        mbr[446 + 16 + 4] = 0x0B  # second entry
        struct.pack_into("<I", mbr, 446 + 16 + 8, 2048)
        mbr[510:512] = b"\x55\xaa"
        self.assertEqual(w.partition_offset(bytes(mbr)), 2048 * 512)
        with self.assertRaises(ValueError):
            w.partition_offset(bytes(512))
        mbr[446 + 16 + 4] = 0x83
        with self.assertRaises(ValueError):
            w.partition_offset(bytes(mbr))

    def test_clean_bits_fat16(self):
        boot = bytearray(512)
        struct.pack_into("<H", boot, 11, 512)
        struct.pack_into("<H", boot, 14, 4)
        boot[16] = 2
        struct.pack_into("<H", boot, 22, 100)
        self.assertEqual(w.clean_bits(bytes(boot)), ([4 * 512 + 2, 104 * 512 + 2], 2, 0xC000))

    def test_mark_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "disk.raw")
            fat32_disk(p, clean=False)
            self.assertTrue(w.mark_clean(p))
            with open(p, "rb") as f:
                for i in range(2):
                    f.seek(63 * 512 + (32 + i * 8) * 512 + 4)
                    self.assertEqual(struct.unpack("<I", f.read(4))[0], 0x0FFFFFFF)
            self.assertFalse(w.mark_clean(p))  # already clean: nothing written

    def test_rtc_after(self):
        listing = ("Volume Serial Number is 204E-1EF0\nDirectory for ::/WINDOWS\n\n"
                   "SYSTEM   DAT   4079648 2025-04-26   8:59 \n")
        user = "USER     DAT    438304 2025-04-26  23:30 \n"
        self.assertEqual(w.rtc_after([listing]), "2025-04-26T09:59:00")
        self.assertEqual(w.rtc_after([listing, user]), "2025-04-27T00:30:00")
        self.assertIsNone(w.rtc_after(["mdir: File not found"]))

    def test_run_list(self):
        txt = w.run_list(["glide2", "opengl"], hold=5, bench=300, timeout=120, delay=10)
        self.assertEqual(txt.split("\r\n"), ["delay 10", "run 120 GLIDETST.EXE hold=5 bench=300", "delay 8",
                                             "run 120 GLTEST.EXE hold=5 bench=300", "shutdown", ""])
        self.assertIn("run 120 GLIDETST.EXE glide3 hold=1 bench=0\r\nstay", w.run_list(["glide3"], 1, 0, 120, 0, stay=True))
        self.assertIn("run 120 GLTEST.EXE ctx2=1 hold=5 bench=0\r\n", w.run_list(["opengl-ctx"], 5, 0, 120, 0))

    def test_unpack_drivers(self):
        with tempfile.TemporaryDirectory() as d:
            z = os.path.join(d, "qemu-3dfx-drivers-b94d988.zip")
            with zipfile.ZipFile(z, "w") as zf:
                for name in ("FXMEMMAP.VXD", "glide.dll", "glide2x.dll", "glide3x.dll", "glide2x.ovl", "opengl32.dll"):
                    zf.writestr(f"qemu-3dfx-drivers-b94d988/{name}", b"x")
                zf.writestr("qemu-3dfx-drivers-b94d988/VERSION.txt",
                            "qemu-3dfx guest drivers\n\nsubmodule commit: b94d988698766872e39d15bea07da92efdf7c112\n")
            dest = os.path.join(d, "out")
            self.assertEqual(w.unpack_drivers(z, dest), "b94d988")
            self.assertTrue(os.path.exists(os.path.join(dest, "fxmemmap.vxd")))
            # a directory works too, and a missing driver is an error
            os.unlink(os.path.join(dest, "glide3x.dll"))
            with self.assertRaises(ValueError):
                w.unpack_drivers(dest, os.path.join(d, "again"))


class QemuLog(unittest.TestCase):
    LOG = ("glidept: offscreen 640x480, frames to the graphic console\n"
           "2    frames in 5.1  seconds, 0.4  FPS        glidept: offscreen closed after 5.4 s: 302 swaps (56.4 per s), "
           "303 reads of 0.14 ms average (1 after the last call), 303 frames to the console, 0.02 ms after their read on "
           "average\n                                                glidept: grSstWinClose called\n"
           "mesapt: offscreen closed after 5.3 s: 302 swaps (57.0 per s), 302 reads of 0.40 ms average (0 after the last "
           "call), 302 frames to the console, 0.02 ms after their read on average\n"
           # the published stage-1 binary: no "(n after the last call)"
           "glidept: offscreen closed after 5.3 s: 302 swaps (57.1 per s), 302 reads of 0.14 ms average, 250 frames to the "
           "console, 0.02 ms after their read on average\n")

    def test_offscreen_stats(self):
        st = w.offscreen_stats(self.LOG)
        self.assertEqual([s["device"] for s in st], ["glidept", "mesapt", "glidept"])
        self.assertEqual(st[0], {"device": "glidept", "open_s": 5.4, "swaps": 302, "swaps_per_s": 56.4, "reads": 303,
                                 "read_ms": 0.14, "frames_to_console": 303, "console_ms": 0.02})
        self.assertEqual(st[1]["read_ms"], 0.40)
        self.assertEqual(st[2]["frames_to_console"], 250)
        self.assertEqual(w.offscreen_stats("glidept: DLL loaded - glide2x.dll\n"), [])

    DMABUF_LOG = ("mesapt: offscreen closed after 12.0 s: 2010 swaps (167.5 per s), 2010 reads of 0.00 ms average "
                  "(0 after the last call), 2010 frames to the console, 0.60 ms after their read on average\n"
                  "mesapt: dmabuf scanout: 2010 frames copied to the dmabuf in 1.02 ms average, the display's update "
                  "0.80 ms a frame, 3 held while the display was busy, 0 frames read back instead\n"
                  "mesapt: dmabuf scanout: double-buffered, 1 of the held frames replaced by a newer one before they "
                  "went\n"
                  "glidept: offscreen closed after 5.0 s: 300 swaps (60.0 per s), 300 reads of 0.00 ms average "
                  "(0 after the last call), 300 frames to the console, 0.50 ms after their read on average\n"
                  "glidept: dmabuf scanout: 300 frames copied to the dmabuf in 0.07 ms average, the display's update "
                  "0.50 ms a frame, 0 held while the display was busy, 0 frames read back instead\n")

    def test_offscreen_stats_double_buffered(self):
        st = w.offscreen_stats(self.DMABUF_LOG)
        self.assertEqual([(s["device"], s["dmabuf_frames"], s["double_buffered"]) for s in st],
                         [("mesapt", 2010, True), ("glidept", 300, False)])
        self.assertEqual(st[0]["replaced"], 1)
        self.assertNotIn("replaced", st[1])

    def test_display_timer_held(self):
        log = "mesapt: offscreen: no swap for 2000 ms, the frame stays (the display timer gives the console back\n"
        self.assertEqual(len(w.HELD_RE.findall(log * 2)), 2)

    def test_select_tests(self):
        stage1 = b"...glidept: offscreen %dx%d, frames to %s..."
        stage1b = b"...%s: offscreen %dx%d, frames to %s...no SDL window: rendering offscreen, EGL %d.%d..."
        self.assertEqual(w.select_tests("auto", "vnc", stage1), ["glide2", "glide3"])
        self.assertEqual(w.select_tests("auto", "vnc", stage1b), ["glide2", "glide3", "opengl", "opengl-ctx"])
        self.assertEqual(w.select_tests("auto", "vnc", b"stage 0"), [])
        self.assertEqual(w.select_tests("auto", "sdl", b"stage 0"), ["glide2", "glide3", "opengl", "opengl-ctx"])
        self.assertEqual(w.select_tests("opengl, glide2", "vnc", b""), ["opengl", "glide2"])

    def test_guest_cpu(self):
        self.assertEqual(w.guest_cpu("kvm"), "pentium3")
        self.assertTrue(w.guest_cpu("tcg").startswith("pentium3,+sse2,"))
        self.assertIn("+sse4.2", w.guest_cpu("tcg"))
        # drivers built for the Pentium: the plain pentium3 under TCG too
        self.assertEqual(w.guest_cpu("tcg", "i586"), "pentium3")
        self.assertEqual(w.guest_cpu("kvm", "i586"), "pentium3")

    def test_drivers_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(w.drivers_baseline(d))
            with open(os.path.join(d, "version.txt"), "w") as f:
                f.write("qemu-3dfx guest drivers\n\nsubmodule commit: b94d988698766872e39d15bea07da92efdf7c112\n"
                        "revision (__REV__): b94d988-\n")
            self.assertIsNone(w.drivers_baseline(d))
            with open(os.path.join(d, "version.txt"), "a") as f:
                f.write("built for i586 (-march=pentium, x87 math; no MMX, SSE or later)\n")
            self.assertEqual(w.drivers_baseline(d), "i586")


class Verdicts(unittest.TestCase):
    def result(self, guest="PASS", frame=True, after=True):
        return {"tests": {"glide2": {"guest": guest, "frame": {"ok": frame}, "after": {"ok": after}}}}

    def test_all_three_needed(self):
        r = self.result()
        self.assertTrue(w.evaluate(r, ["glide2"]))
        self.assertEqual(r["tests"]["glide2"]["verdict"], "PASS")
        for kw in ({"guest": "FAIL 1"}, {"frame": False}, {"after": False}):
            r = self.result(**kw)
            self.assertFalse(w.evaluate(r, ["glide2"]), kw)
            self.assertTrue(r["tests"]["glide2"]["verdict"].startswith("FAIL: "))

    def test_held_frame(self):
        r = self.result()
        r["tests"]["glide2"]["held"] = {"ok": True, "at_s": 7.6}
        self.assertTrue(w.evaluate(r, ["glide2"]))
        r["tests"]["glide2"]["held"] = {"ok": False, "at_s": 7.6}
        self.assertFalse(w.evaluate(r, ["glide2"]))
        self.assertIn("held frame was gone 7.6 s", r["tests"]["glide2"]["verdict"])

    def test_sdl_after_not_checked(self):
        r = self.result(after=None)
        self.assertTrue(w.evaluate(r, ["glide2"]))

    def test_never_ran(self):
        r = {"tests": {"opengl": {"guest": None, "frame": None, "after": None}}}
        self.assertFalse(w.evaluate(r, ["opengl"]))
        self.assertIn("no verdict", r["tests"]["opengl"]["verdict"])


class Pve(unittest.TestCase):
    def test_des_known_answers(self):
        # FIPS 46 / the classic worked example, and a weak-key style vector
        self.assertEqual(w.des_encrypt(bytes.fromhex("133457799BBCDFF1"), bytes.fromhex("0123456789ABCDEF")).hex(),
                         "85e813540f0ab405")
        self.assertEqual(w.des_encrypt(bytes.fromhex("0E329232EA6D0D73"), bytes.fromhex("8787878787878787")).hex(),
                         "0000000000000000")

    def test_vnc_auth_mirrors_the_key_bits(self):
        challenge = bytes(range(16))
        # "@" (0x40) mirrored is 0x02, so the key is 02 00 00 00 00 00 00 00
        key = bytes.fromhex("0200000000000000")
        self.assertEqual(w.vnc_auth_response("@", challenge),
                         w.des_encrypt(key, challenge[:8]) + w.des_encrypt(key, challenge[8:]))
        self.assertEqual(len(w.vnc_auth_response("a-longer-password", challenge)), 16)

    def args(self, display, rtc):
        import types
        return types.SimpleNamespace(display=display, memory=512, rtc_base=rtc)

    def test_create_options(self):
        o = w.pve_create_options(self.args("egl", "2025-04-26T09:59:00"), "w3d9398:9398/disk.raw", "/o/serial.log",
                                 "/o/qemu.log", "kvm", "pentium3")
        opt = dict(zip(o[::2], o[1::2]))
        self.assertEqual(opt["--vga"], "std,mesa=1,mesa-display=egl-headless")
        self.assertEqual(opt["--scsi0"], "w3d9398:9398/disk.raw,cache=unsafe")
        self.assertEqual((opt["--kvm"], opt["--cpu"], opt["--startdate"]), ("1", "pentium3", "2025-04-26T09:59:00"))
        self.assertEqual((opt["--machine"], opt["--vmgenid"]), ("pc-i440fx-11.0", "0"))
        self.assertIn("-d plugin -D /o/qemu.log", opt["--args"])
        self.assertIn("-device AC97,id=audio0,bus=pci.0,addr=0x4", opt["--args"])
        self.assertNotIn("--audio0", opt)
        o = w.pve_create_options(self.args("vnc", "localtime"), "v", "s", "q", "tcg", "pentium3")
        opt = dict(zip(o[::2], o[1::2]))
        self.assertEqual((opt["--vga"], opt["--kvm"], opt["--localtime"]), ("std,mesa=1", "0", "1"))
        self.assertNotIn("--startdate", opt)


if __name__ == "__main__":
    unittest.main()
