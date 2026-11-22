"""Unit tests for the interactive shell: shell.py's model and parser, and init.c built for the host.

    python3 -m unittest discover -s e2e/wisp/tests

The host build ("cc init.c" against the host's C library) is not PID 1, so poweroff ends it with
exit status 0; the tests skip it when there is no C compiler.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import run  # noqa: E402
import shell  # noqa: E402

INIT_C = os.path.join(HERE, "..", "init.c")


def golden_mandel():
    """tests/mandel.txt: the 20 rows, each closed with '|' so no editor trims the spaces."""
    with open(os.path.join(HERE, "mandel.txt"), encoding="utf-8") as fh:
        return [line.rstrip("\n")[:-1] for line in fh]


class Mandel(unittest.TestCase):
    def test_model_matches_golden(self):
        self.assertEqual(shell.mandel_rows(), golden_mandel())

    def test_shape(self):
        rows = shell.mandel_rows()
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(len(r) == 78 for r in rows))
        # nearly symmetric about the real axis, which falls between rows 9 and 10 (rounding
        # down in the shifts makes a few characters differ)
        diff = sum(a != b for r, m in zip(rows, rows[::-1]) for a, b in zip(r, m))
        self.assertLess(diff, 20)
        # the main cardioid is in the set
        self.assertIn("@" * 20, rows[9])

    def test_fixed_point_stays_in_32_bits(self):
        # the largest |x * y| the iteration can reach before the escape test: |z| <= 2 plus |c|
        bound = int(6.5 * 4096)
        self.assertLess(bound * bound, 2**31)


TRANSCRIPT = (
    "OpenBIOS\r\nLinux version 7.3.4\r\nWISP-BANNER wsh-pve wisp v1\r\n"
    "\x1b[1;36m logo\x1b[0m\r\n\r\n"
    "\x1b[1;32mwisp\x1b[0m:\x1b[1;34msparc32\x1b[0m> hepl\b \b\b \blp\r\n"
    "  help            this list\r\n  mandel          the Mandelbrot set\r\n"
    "  poweroff        power the machine off\r\n"
    "\x1b[1;32mwisp\x1b[0m:\x1b[1;34msparc32\x1b[0m> info\r\n"
    "  arch      sparc32 (sparc)\r\n  kernel    Linux 7.3.4 #1\r\n  cpus      1\r\n"
    "  memory    109024 kB, 107812 kB free\r\n  uptime    0.402 s\r\n  pid       1\r\n"
    "\x1b[1;32mwisp\x1b[0m:\x1b[1;34msparc32\x1b[0m> bench\r\n"
    "  crc32 0x35a46014 after 4096 rounds (65536 KiB) in 348 ms\r\n  188321 KiB/s\r\n"
    "\x1b[1;32mwisp\x1b[0m:\x1b[1;34msparc32\x1b[0m> crc 64\r\n"
    "  crc32 0x36c8a4f9 after 64 rounds (1024 KiB) in 6 ms\r\n"
    "\x1b[1;32mwisp\x1b[0m:\x1b[1;34msparc32\x1b[0m> mandel\r\n"
    + "".join(f" {r}\r\n" for r in shell.mandel_rows())
    + "  78 x 20 points, 32 iterations, 90 ms\r\n"
    "\x1b[1;32mwisp\x1b[0m:\x1b[1;34msparc32\x1b[0m> poweroff\r\n"
    "  powering off\r\nreboot: Power down\r\n"
)


class Transcript(unittest.TestCase):
    def check(self, text, arch="sparc32"):
        answers = shell.split_transcript(text)
        return shell.check_answers(arch, shell.SCRIPT, answers, run.crc_for, run.DEFAULT_LOOPS)

    def test_split(self):
        answers = shell.split_transcript(TRANSCRIPT)
        self.assertEqual(len(answers), 6)
        self.assertEqual(answers[1], ("sparc32", ["  arch      sparc32 (sparc)",
                                                  "  kernel    Linux 7.3.4 #1", "  cpus      1",
                                                  "  memory    109024 kB, 107812 kB free",
                                                  "  uptime    0.402 s", "  pid       1"]))
        self.assertEqual(answers[5], ("sparc32", ["  powering off", "reboot: Power down"]))

    def test_good_transcript(self):
        problems, numbers = self.check(TRANSCRIPT)
        self.assertEqual(problems, [])
        self.assertEqual(numbers, {"bench_ms": 348, "bench_crc": "0x35a46014", "crc_ms": 6,
                                   "crc_crc": "0x36c8a4f9", "mandel_ms": 90})

    def test_wrong_crc(self):
        problems, _ = self.check(TRANSCRIPT.replace("0x36c8a4f9", "0x36c8a4f8"))
        self.assertEqual(problems, ["crc: crc 0x36c8a4f8 != 0x36c8a4f9"])

    def test_one_wrong_mandel_character(self):
        rows = shell.mandel_rows()
        bad = rows[3][:40] + ("#" if rows[3][40] != "#" else "%") + rows[3][41:]
        problems, _ = self.check(TRANSCRIPT.replace(f" {rows[3]}\r\n", f" {bad}\r\n", 1))
        self.assertEqual(problems, ["mandel: 20 rows, 20 wanted, differing rows [3]"])

    def test_wrong_arch_and_missing_answers(self):
        cut = TRANSCRIPT[:TRANSCRIPT.index("bench\r\n")]
        problems, _ = self.check(cut, arch="sparc64")
        self.assertIn("3 of 6 commands answered", problems)
        self.assertIn("info: arch sparc32 != sparc64", problems)
        self.assertIn("help: prompt arch sparc32 != sparc64", problems)

    def test_help_without_backspace_handling(self):
        text = TRANSCRIPT.replace("  mandel          the Mandelbrot set\r\n", "")
        problems, _ = self.check(text)
        self.assertEqual(problems, ["help: no command list (typed with Backspace)"])

    def test_evaluate_shell_record(self):
        raw = {"load1": 1.0, "load5": 1.0, "exit_code": 0, "timed_out": False, "max_rss_kb": 2048,
               "user_s": 1.0, "sys_s": 0.1, "t_prompt": 2.5, "prompt_s": [2.5, 0.1], "t_exit": 3.0,
               "text": TRANSCRIPT}
        rec = run.evaluate_shell("sparc32", raw, None)
        self.assertTrue(rec["ok"], rec["problems"])
        self.assertEqual(rec["mandel_ms"], 90)
        rec["label"] = "tcg"
        self.assertIn("| sparc32 | SS-5 | tcg | 1.00 | 2.50 | 348 | 90 | 3.00 | 2 | yes |",
                      run.shell_table([rec]))
        raw.update(exit_code=-9, timed_out=True, text=TRANSCRIPT + "WISP-POWEROFF-FAILED\r\n")
        self.assertEqual(run.evaluate_shell("sparc32", raw, None)["problems"],
                         ["power-off failed", "timed out"])

    def test_reboot_script(self):
        script = shell.reboot_script(shell.SCRIPT)
        self.assertEqual(script[:-1], shell.SCRIPT[:-1])
        self.assertEqual(script[-1], "reboot")
        # what the sun4u shell answers since the firmware restarts the machine (openbios 0030)
        text = TRANSCRIPT.replace("poweroff\r\n  powering off\r\nreboot: Power down\r\n",
                                  "reboot\r\n  restarting\r\nreboot: Restarting system\r\n")
        answers = shell.split_transcript(text)
        problems, _ = shell.check_answers("sparc32", script, answers, run.crc_for,
                                          run.DEFAULT_LOOPS)
        self.assertEqual(problems, [])
        # before it: Linux's restart through the firmware's boot service returned
        problems, _ = shell.check_answers("sparc32", script, shell.split_transcript(
            text.replace("reboot: Restarting system\r\n",
                         "Kernel panic - not syncing: Reboot failed!\r\n")),
            run.crc_for, run.DEFAULT_LOOPS)
        self.assertEqual(problems, ["reboot: the kernel panicked instead of restarting"])

    def test_command_line(self):
        cmd = run.qemu_command("sparc32", kernel="/k", interactive=True)
        self.assertEqual(cmd[-1], "console=ttyS0 panic=-1 wisp=shell")


CC = shutil.which("cc") or shutil.which("gcc")


@unittest.skipUnless(CC, "no C compiler")
class HostInit(unittest.TestCase):
    """init.c built against the host's C library: the shell's logic without QEMU."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = os.path.join(cls.tmp.name, "init-host")
        subprocess.run([CC, "-O2", "-Wall", "-Wextra", "-Werror", '-DWISP_ARCH="host"', "-o",
                        cls.binary, INIT_C], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def start(self, env, script):
        return subprocess.run([self.binary], input="".join(c + "\n" for c in script).encode(),
                              env=env, capture_output=True, timeout=60, check=False)

    def test_batch_mode(self):
        proc = self.start({"loops": "64"}, [])
        self.assertEqual(proc.returncode, 0)
        line = [x for x in proc.stdout.decode().splitlines() if x.startswith("WISP-RESULT ")][0]
        result = run.parse_result(line)
        self.assertEqual((result["arch"], result["loops"], result["crc"], result["status"]),
                         ("host", 64, 0x36C8A4F9, "notpid1"))

    def test_shell_script(self):
        proc = self.start({"wisp": "shell"}, shell.SCRIPT)
        self.assertEqual(proc.returncode, 0)
        text = proc.stdout.decode()
        # a pipe: no echo, and init.c itself applies the Backspaces
        answers = shell.split_transcript(text, echo=False)
        problems, numbers = shell.check_answers("host", shell.SCRIPT, answers, run.crc_for,
                                                run.DEFAULT_LOOPS)
        self.assertEqual(problems, [])
        self.assertEqual(numbers["crc_crc"], "0x36c8a4f9")
        self.assertEqual(numbers["bench_crc"], "0x35a46014")

    def test_mandel_rows_are_the_golden_ones(self):
        proc = self.start({"wisp": "shell"}, ["mandel", "poweroff"])
        lines = shell.split_transcript(proc.stdout.decode(), echo=False)[0][1]
        self.assertEqual([x[1:] for x in lines[:20]], golden_mandel())

    def test_line_editing_and_errors(self):
        script = ["  \x1b[Acrc\x08\x08\x08", "crc", "crc 0", "crc 1000001", "nosuch arg", "",
                  "\tcrc   1", "poweroff"]
        answers = shell.split_transcript(self.start({"wisp": "shell"}, script).stdout.decode(),
                                         echo=False)
        usage = ["  usage: crc <rounds>, 1 to 1000000"]
        self.assertEqual([a[1] for a in answers[:7]], [
            [],  # an arrow key and a word erased with ^H: an empty line
            usage, usage, usage,
            ["  nosuch: unknown command, try help"],
            [],
            [answers[6][1][0]],
        ])
        self.assertRegex(answers[6][1][0], r"^  crc32 0x[0-9a-f]{8} after 1 rounds \(16 KiB\)")
        self.assertEqual(int(answers[6][1][0].split()[1], 16), run.expected_crc(1))

    @unittest.skipIf(os.path.exists("/test"), "the host has a /test")
    def test_test_mode_reports_a_missing_test(self):
        # wisp=test runs /test (the wisp-test action's initramfs has it); here there is none, so
        # the child's exec fails, and the result line carries its exit code 127
        proc = self.start({"wisp": "test"}, [])
        self.assertEqual(proc.returncode, 0)
        lines = proc.stdout.decode().splitlines()
        self.assertIn("WISP-TEST-ERROR exec /test failed: errno 2", lines)
        self.assertRegex(lines[-1], r"^WISP-TEST v=1 exit=127 signal=0 ms=\d+$")

    def test_end_of_input_powers_off(self):
        proc = self.start({"wisp": "shell"}, ["help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("  poweroff        power the machine off", proc.stdout.decode())


if __name__ == "__main__":
    unittest.main()
