"""Unit tests for run.py (no QEMU needed): python3 -m unittest discover -s e2e/wisp/tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import run  # noqa: E402

GOOD = ("WISP-RESULT v=1 arch=sparc32 machine=sparc release=7.3.4 cpus=1 mem_kb=109024 "
        "uptime_ms=433 loops=4096 crc=0x35a46014 loop_ms=96 status=ok")


class ParseResult(unittest.TestCase):
    def test_good_line(self):
        r = run.parse_result(GOOD)
        self.assertEqual(r["arch"], "sparc32")
        self.assertEqual(r["release"], "7.3.4")
        self.assertEqual(r["cpus"], 1)
        self.assertEqual(r["mem_kb"], 109024)
        self.assertEqual(r["loops"], 4096)
        self.assertEqual(r["crc"], 0x35A46014)
        self.assertEqual(r["status"], "ok")

    def test_console_noise_before_prefix_and_crlf(self):
        r = run.parse_result("\x1b[0m" + GOOD + "\r\n")
        self.assertEqual(r["loop_ms"], 96)

    def test_not_a_result(self):
        with self.assertRaises(ValueError):
            run.parse_result("WISP-BANNER wsh-pve wisp v1")

    def test_missing_field(self):
        with self.assertRaisesRegex(ValueError, "missing fields: crc"):
            run.parse_result(GOOD.replace(" crc=0x35a46014", ""))

    def test_bad_number(self):
        with self.assertRaisesRegex(ValueError, "cpus is not a number"):
            run.parse_result(GOOD.replace("cpus=1", "cpus=-"))

    def test_bad_crc(self):
        with self.assertRaisesRegex(ValueError, "bad crc"):
            run.parse_result(GOOD.replace("crc=0x35a46014", "crc=0xb1c5"))

    def test_bad_field(self):
        with self.assertRaisesRegex(ValueError, "bad field"):
            run.parse_result(GOOD + " junk")

    def test_truncated_line(self):
        # a line cut by a power-off in the middle of printing
        with self.assertRaises(ValueError):
            run.parse_result(GOOD[:60])


class Crc(unittest.TestCase):
    def test_python_model_matches_known_small(self):
        # 64 loops was measured on x86_64 under TCG; the model must reproduce it
        self.assertEqual(run.expected_crc(64), 0x36C8A4F9)

    def test_known_table_is_consistent(self):
        for loops, crc in run.KNOWN_CRC.items():
            if loops <= 64:
                self.assertEqual(run.expected_crc(loops), crc)

    def test_crc_for_unknown_large_is_none(self):
        self.assertIsNone(run.crc_for(999_999))

    def test_crc_for_computes_small(self):
        self.assertEqual(run.crc_for(1), run.expected_crc(1))


def lines(*texts, step=0.5):
    return [(i * step, t) for i, t in enumerate(texts)]


class Evaluate(unittest.TestCase):
    def raw(self, console, exit_code=0, timed_out=False):
        return {"load1": 1.0, "load5": 2.0, "exit_code": exit_code, "timed_out": timed_out,
                "max_rss_kb": 51200, "user_s": 1.0, "sys_s": 0.1, "t_exit": 9.0,
                "lines": console}

    def test_ok_run(self):
        console = lines("OpenBIOS", "Linux version 7.3.4 (x)", "Run /init as init process",
                        "WISP-BANNER wsh-pve wisp v1", GOOD, "reboot: Power down")
        rec = run.evaluate("sparc32", self.raw(console), None)
        self.assertTrue(rec["ok"], rec["problems"])
        self.assertEqual(rec["t_kernel"], 0.5)
        self.assertEqual(rec["t_banner"], 1.5)
        self.assertEqual(rec["t_result"], 2.0)
        self.assertEqual(rec["crc"], "0x35a46014")
        self.assertTrue(rec["crc_checked"])

    def test_wrong_crc(self):
        console = lines("WISP-BANNER x", GOOD.replace("0x35a46014", "0xdeadbeef"))
        rec = run.evaluate("sparc32", self.raw(console), None)
        self.assertFalse(rec["ok"])
        self.assertIn("crc 0xdeadbeef != 0x35a46014", rec["problems"])

    def test_wrong_arch(self):
        rec = run.evaluate("sparc64", self.raw(lines(GOOD)), None)
        self.assertIn("arch sparc32 != sparc64", rec["problems"])

    def test_poweroff_failed_and_timeout(self):
        console = lines(GOOD, "WISP-POWEROFF-FAILED")
        rec = run.evaluate("sparc32", self.raw(console, exit_code=-9, timed_out=True), None)
        self.assertEqual(rec["problems"], ["power-off failed", "timed out"])

    def test_no_result(self):
        rec = run.evaluate("x86_64", self.raw(lines("Kernel panic"), exit_code=0), None)
        self.assertEqual(rec["problems"], ["no result line"])
        self.assertIsNone(rec["t_banner"])

    def test_unknown_loop_count_is_not_checked(self):
        good = GOOD.replace("loops=4096", "loops=999999")
        rec = run.evaluate("sparc32", self.raw(lines(good)), 999999)
        self.assertTrue(rec["ok"], rec["problems"])
        self.assertFalse(rec["crc_checked"])


class Command(unittest.TestCase):
    def test_sparc32_default(self):
        cmd = run.qemu_command("sparc32", kernel="/k")
        self.assertEqual(cmd[:3], ["qemu-system-sparc", "-M", "SS-5"])
        self.assertIn("-no-reboot", cmd)
        self.assertEqual(cmd[-2:], ["-append", "console=ttyS0 panic=-1"])

    def test_aarch64_virt(self):
        cmd = run.qemu_command("aarch64", kernel="/k", machine="virt")
        self.assertEqual(cmd[:7], ["qemu-system-aarch64", "-M", "virt", "-cpu", "cortex-a57",
                                   "-m", "256"])
        self.assertIn("console=ttyAMA0 earlycon=pl011,0x09000000", cmd[-1])

    def test_overrides(self):
        cmd = run.qemu_command("sparc32", qemu_dir="/q", kernel="/k", machine="SS-20", memory=64,
                               loops=8, firmware="/fw")
        self.assertEqual(cmd[0], "/q/qemu-system-sparc")
        self.assertEqual(cmd[1:3], ["-M", "SS-20"])
        self.assertEqual(cmd[cmd.index("-m") + 1], "64")
        self.assertEqual(cmd[cmd.index("-L") + 1], "/fw")
        self.assertTrue(cmd[-1].endswith(" loops=8"))

    def test_every_arch_has_a_command(self):
        for arch in run.ARCHES:
            cmd = run.qemu_command(arch, kernel="/k")
            self.assertIn("-kernel", cmd)


class Table(unittest.TestCase):
    def test_table_has_a_row_per_record(self):
        console = lines("Linux version", "WISP-BANNER x", GOOD)
        rec = run.evaluate("sparc32", {"load1": 1.0, "load5": 2.0, "exit_code": 0,
                                       "timed_out": False, "max_rss_kb": 51200, "user_s": 1,
                                       "sys_s": 0, "t_exit": 3.0, "lines": console}, None)
        rec["label"] = "tcg"
        out = run.table([rec, rec]).splitlines()
        self.assertEqual(len(out), 4)
        self.assertIn("| sparc32 | SS-5 | tcg | 1.00 |", out[2])
        self.assertIn("| 50 | yes |", out[2])


if __name__ == "__main__":
    unittest.main()
