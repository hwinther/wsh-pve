"""init.c built on the host (glibc, not PID 1): its lines must parse with the runner's code and
its CRC must be wisp's. Skipped without a C compiler."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import run  # noqa: E402

CC = shutil.which("cc") or shutil.which("gcc")


@unittest.skipUnless(CC and sys.platform.startswith("linux"), "needs a C compiler on Linux")
class HostInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wisp-netbsd-init-")
        binary = os.path.join(cls.tmp, "init-host")
        subprocess.run([CC, "-O2", "-Wall", "-Wextra", "-Werror", '-DWISP_ARCH="x86_64"',
                        "-o", binary, os.path.join(HERE, "..", "init.c")], check=True)
        out = subprocess.run([binary], cwd=cls.tmp, capture_output=True, text=True, check=True,
                             timeout=120).stdout
        cls.lines = [(0.0, line) for line in out.splitlines()]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_markers_and_checks(self):
        texts = [t for _, t in self.lines]
        self.assertEqual(texts[0], "WISP-BANNER wsh-pve wisp-netbsd v1")
        self.assertTrue(texts[1].startswith("WISP-INFO uname: "))
        checks = run.scan_checks(self.lines)
        self.assertEqual(sorted(checks), ["clock", "file"])
        self.assertTrue(all(c["ok"] for c in checks.values()), checks)

    def test_result_line(self):
        result = run.wisp_run.parse_result(self.lines[-1][1])
        self.assertEqual(result["arch"], "x86_64")
        self.assertEqual(result["loops"], 4096)
        self.assertEqual(result["crc"], run.wisp_run.KNOWN_CRC[4096])
        self.assertEqual(result["status"], "notpid1")

    def test_file_check_cleans_up(self):
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "wisp-file-check")))


if __name__ == "__main__":
    unittest.main()
