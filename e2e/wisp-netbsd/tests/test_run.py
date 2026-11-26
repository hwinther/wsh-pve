"""Unit tests for wisp-netbsd's run.py (no QEMU needed):
python3 -m unittest discover -s e2e/wisp-netbsd/tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import run  # noqa: E402

KERNEL = "[   1.0000000] NetBSD 11.1 (WISP)"
RESULT = ("WISP-RESULT v=1 arch=sparc32 machine=sparc release=11.1 cpus=1 mem_kb=131072 "
          "uptime_ms=1830 loops=4096 crc=0x35a46014 loop_ms=2210 status=ok")
CLOCK = "WISP-CHECK name=clock ok=1 sleep_ms=200 mono_ms=210 real_ms=210"
FILE = "WISP-CHECK name=file ok=1 bytes=65536 remount=1 errno=0"


def raw(lines, exit_code=0, timed_out=False):
    return {"load1": 0.1, "load5": 0.1, "t_exit": 9.0, "exit_code": exit_code,
            "timed_out": timed_out, "max_rss_kb": 65536, "user_s": 1.0, "sys_s": 0.1,
            "lines": [(float(i), text) for i, text in enumerate(lines)]}


GOOD = ["Copyright (c) 1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005,",
        KERNEL, "total memory = 128 MB", "WISP-BANNER wsh-pve wisp-netbsd v1",
        "WISP-INFO uname: NetBSD 11.1 sparc", CLOCK, FILE, RESULT, "halted"]


class Evaluate(unittest.TestCase):
    def test_good_boot(self):
        rec = run.evaluate("sparc32", raw(GOOD))
        self.assertTrue(rec["ok"], rec["problems"])
        self.assertEqual(rec["t_kernel"], 1.0)
        self.assertEqual(rec["t_banner"], 3.0)
        self.assertEqual(rec["t_result"], 7.0)
        self.assertEqual(rec["release"], "11.1")
        self.assertEqual(rec["checks"]["file"]["remount"], "1")

    def test_failed_check(self):
        lines = [x.replace("name=clock ok=1", "name=clock ok=0") for x in GOOD]
        rec = run.evaluate("sparc32", raw(lines))
        self.assertFalse(rec["ok"])
        self.assertIn("clock check failed", rec["problems"])

    def test_missing_check(self):
        rec = run.evaluate("sparc32", raw([x for x in GOOD if x != FILE]))
        self.assertIn("no file check", rec["problems"])

    def test_check_status_in_result(self):
        lines = [x.replace("status=ok", "status=checkfailed") for x in GOOD]
        rec = run.evaluate("sparc32", raw(lines))
        self.assertIn("status checkfailed", rec["problems"])

    def test_wrong_arch_and_crc(self):
        lines = [x.replace("crc=0x35a46014", "crc=0x00000001") for x in GOOD]
        rec = run.evaluate("x86_64", raw(lines))
        self.assertIn("arch sparc32 != x86_64", rec["problems"])
        self.assertIn("crc 0x00000001 != 0x35a46014", rec["problems"])

    def test_poweroff_failed_and_timeout(self):
        rec = run.evaluate("sparc32", raw(GOOD + ["WISP-POWEROFF-FAILED"], -9, True))
        self.assertIn("power-off failed", rec["problems"])
        self.assertIn("timed out", rec["problems"])

    def test_linux_banner_is_not_the_kernel_marker(self):
        lines = ["Linux version 7.3.4"] + GOOD[2:]
        rec = run.evaluate("sparc32", raw(lines))
        self.assertIsNone(rec["t_kernel"])


class Command(unittest.TestCase):
    def test_sparc32_default(self):
        cmd = run.qemu_command("sparc32", firmware="/fw", out="/o")
        self.assertEqual(cmd[:3], ["qemu-system-sparc", "-M", "SS-5"])
        self.assertIn("-nodefaults", cmd)
        self.assertNotIn("-append", cmd)
        self.assertEqual(cmd[-2:], ["-kernel", os.path.join("/o", "sparc32", "kernel")])
        self.assertEqual(cmd[cmd.index("-L") + 1], "/fw")

    def test_sparc64_boots_from_its_disk(self):
        cmd = run.qemu_command("sparc64", out="/o")
        self.assertNotIn("-kernel", cmd)
        drive = cmd[cmd.index("-drive") + 1]
        self.assertTrue(drive.startswith("file=" + os.path.join("/o", "sparc64", "disk.img")))
        self.assertIn("snapshot=on", drive)
        self.assertEqual(cmd[cmd.index("-boot") + 1], "c")

    def test_machine_and_memory_override(self):
        cmd = run.qemu_command("sparc32", qemu_dir="/q", machine="SS-20", memory=256)
        self.assertEqual(cmd[:3], [os.path.join("/q", "qemu-system-sparc"), "-M", "SS-20"])
        self.assertEqual(cmd[cmd.index("-m") + 1], "256")

    def test_every_arch_has_a_kernel_config(self):
        conf = os.path.join(os.path.dirname(run.__file__), "config")
        machines = {"sparc32": "sparc", "sparc64": "sparc64", "x86_64": "amd64"}
        for arch in run.ARCHES:
            with self.subTest(arch=arch):
                path = os.path.join(conf, f"WISP.{machines[arch]}")
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                self.assertIn("MEMORY_DISK_ROOT_SIZE=WISP_MD_BLOCKS", text)
                self.assertIn("MEMORY_DISK_IS_ROOT", text)


if __name__ == "__main__":
    unittest.main()
