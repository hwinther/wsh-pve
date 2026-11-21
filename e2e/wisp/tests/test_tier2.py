"""Unit tests for tier 2 (tier2.py and the disk and SMP checks of init.c built for the host).

    python3 -m unittest discover -s e2e/wisp/tests

The host build is not PID 1: its disk check takes a file instead of a block device, and its SMP
check forks one child per CPU of the host. The network check needs a NIC and root, so it is only
checked under QEMU (run.py --tier2).
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
import tier2  # noqa: E402

INIT_C = os.path.join(HERE, "..", "init.c")


def xorshift_words(seed, n):
    x, out = seed, []
    for _ in range(n):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out.append(x)
    return out


def disk_line(index=0, dev="sda", **over):
    read = tier2.crc(tier2.stream(tier2.DISK_HOST_SEED + index, tier2.DISK_READ))
    written = tier2.crc(tier2.stream(tier2.DISK_GUEST_SEED + index, tier2.DISK_SPAN))
    fields = {
        "v": "1", "dev": dev, "index": str(index), "size_kb": "4096", "read_kb": "4096",
        "read_crc": f"0x{read:08x}", "read_bad": "0", "read_ms": "40", "write_kb": "1024",
        "write_crc": f"0x{written:08x}", "write_ms": "20", "verify_crc": f"0x{written:08x}",
        "verify_bad": "0", "verify_ms": "10", "status": "ok",
    }
    fields.update(over)
    return "WISP-DISK " + " ".join(f"{k}={v}" for k, v in fields.items())


NET = ("WISP-NET v=1 if=eth0 mac=52:54:00:12:34:56 addr=10.0.2.15 peer=10.0.2.2 "
       "peer_mac=52:55:0a:00:02:02 arp_tries=1 arp_ms=3 payload=1400 echoes=8 rtt_min_us=200 "
       "rtt_avg_us=300 rtt_max_us=500 status=ok")
SMP2 = ("WISP-SMP v=1 cpus=2 loops=4096 crc=0x35a46014 wall_ms=700 pinned=yes "
        "percpu=0:0x35a46014:350,1:0x35a46014:360 status=ok")


class Model(unittest.TestCase):
    def test_stream_is_init_c_generator_little_endian(self):
        words = xorshift_words(tier2.DISK_HOST_SEED, 4)
        want = b"".join(w.to_bytes(4, "little") for w in words)
        self.assertEqual(tier2.stream(tier2.DISK_HOST_SEED, 16), want)

    def test_compute_loop_seed_gives_known_crc(self):
        # the compute loop is the same generator: 64 rounds of 16 KiB from its seed
        self.assertEqual(tier2.crc(tier2.stream(2463534242, 64 * 16384)), 0x36C8A4F9)

    def test_profiles(self):
        names = [p["name"] for p in tier2.profiles("x86_64", "pc")]
        self.assertEqual(names, ["ide+virtio-blk+e1000", "virtio-net", "smp2", "smp4"])
        self.assertEqual([p["name"] for p in tier2.profiles("sparc32", "SS-5")], ["esp+lance"])
        self.assertEqual([p["name"] for p in tier2.profiles("sparc32", "SS-20")],
                         ["esp+lance", "smp2", "smp4"])
        self.assertEqual([p["name"] for p in tier2.profiles("sparc64", "sun4u")],
                         ["cmd646+virtio-blk+hme"])
        self.assertEqual(tier2.shell_profile("sparc32", "SS-10")["smp"], 2)
        self.assertEqual(tier2.shell_profile("sparc64", "sun4u")["smp"], 1)

    def test_qemu_and_kernel_args(self):
        p = tier2.profiles("x86_64", "pc")[0]
        args = tier2.qemu_args(p, ["/a.img", "/b.img"])
        self.assertEqual(args, ["-drive", "file=/a.img,format=raw,if=ide,index=0",
                                "-drive", "file=/b.img,format=raw,if=none,id=wd1",
                                "-device", "virtio-blk-pci,drive=wd1",
                                "-nic", "user,model=e1000"])
        self.assertEqual(tier2.kernel_args(p), ["wisp_disk=sda,vda", "wisp_net=eth0"])
        sun4m = tier2.profiles("sparc32", "SS-20")
        self.assertIn("file=/a.img,format=raw,if=scsi,index=0",
                      tier2.qemu_args(sun4m[0], ["/a.img"]))
        self.assertEqual(tier2.qemu_args(sun4m[2], []), ["-smp", "4"])
        self.assertEqual(tier2.kernel_args(sun4m[2], "sparc32"),
                         ["esp_scsi.esp_bus_reset_settle=0", "lpj=2000000", "wisp_smp=1"])

    def test_command_line_and_script(self):
        p = tier2.shell_profile("x86_64", "pc")
        cmd = run.qemu_command("x86_64", kernel="/k", interactive=True,
                               append_extra=tier2.kernel_args(p))
        self.assertEqual(cmd[-1], "console=ttyS0 panic=-1 wisp=shell wisp_disk=sda,vda "
                                  "wisp_net=eth0 wisp_smp=1")
        self.assertEqual(shell.tier2_script(p)[-4:], ("disk", "net", "smp", "poweroff"))
        self.assertEqual(shell.tier2_script(tier2.shell_profile("sparc64", "sun4u"))[-3:],
                         ("disk", "net", "poweroff"))


class Check(unittest.TestCase):
    profile = {"name": "t", "disks": (("ide", "sda"), ("virtio", "vda")), "nic": "e1000",
               "smp": 2}

    def text(self, *extra):
        return "\n".join((disk_line(0, "sda"), disk_line(1, "vda"), NET, SMP2) + extra)

    def test_good(self):
        problems, numbers = tier2.check(self.text(), self.profile, run.crc_for, 4096)
        self.assertEqual(problems, [])
        self.assertEqual([d["dev"] for d in numbers["disks"]], ["sda", "vda"])
        self.assertEqual(numbers["net"]["rtt_avg_us"], 300)
        self.assertEqual(numbers["smp"], {"cpus": 2, "wall_ms": 700, "cpu_ms": [350, 360]})
        self.assertEqual(tier2.summary(numbers),
                         ("sda 40/20/10 vda 40/20/10", "3 / 300", "2 x 360 / 700"))

    def test_shell_indent(self):
        text = "\n".join("  " + x for x in self.text().split("\n"))
        self.assertEqual(tier2.check(text, self.profile, run.crc_for, 4096)[0], [])

    def test_missing_and_bad(self):
        text = "\n".join((disk_line(0, "sda", read_crc="0x00000000", status="read-mismatch"),
                          NET.replace("echoes=8", "echoes=3").replace("status=ok", "status=lost"),
                          SMP2.replace("1:0x35a46014", "1:0x35a46015")))
        problems, _ = tier2.check(text, self.profile, run.crc_for, 4096)
        self.assertIn("disk sda: status read-mismatch", problems)
        self.assertIn("disk vda: no WISP-DISK line", problems)
        self.assertTrue(any(p.startswith("disk sda: read_crc 0x00000000") for p in problems))
        self.assertIn("net: status lost", problems)
        self.assertIn("net: 3 of 8 echoes", problems)
        self.assertIn("smp: crc of CPU 1 != 0x35a46014", problems)

    def test_wrong_cpu_count(self):
        problems, _ = tier2.check(SMP2, dict(self.profile, disks=(), nic=None, smp=4),
                                  run.crc_for, 4096)
        self.assertIn("smp: 2 CPUs != 4", problems)

    def test_evaluate_tier2(self):
        good = ("WISP-RESULT v=1 arch=x86_64 machine=x86_64 release=7.3.4 cpus=2 mem_kb=1 "
                "uptime_ms=1 loops=4096 crc=0x35a46014 loop_ms=96 status=ok")
        raw = {"load1": 1.0, "load5": 1.0, "exit_code": 0, "timed_out": False, "max_rss_kb": 1024,
               "user_s": 1, "sys_s": 0, "t_exit": 3.0,
               "lines": [(0.5 * i, t) for i, t in enumerate([good] + self.text().split("\n"))]}
        rec = run.evaluate_tier2("x86_64", raw, None, self.profile, None)
        self.assertTrue(rec["ok"], rec["problems"])
        rec["label"] = "tcg"
        self.assertIn("| x86_64 | pc | tcg | t | sda 40/20/10 vda 40/20/10 | 3 / 300 "
                      "| 2 x 360 / 700 | 3.00 | yes |", run.tier2_table([rec]))


class Image(unittest.TestCase):
    def test_image_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            images = tier2.Images(tmp, {"disks": (("ide", "sda"),)})
            path = images.paths[0]
            self.assertIn("the guest's pattern is not at", images.check()[0])
            with open(path, "r+b") as fh:
                fh.seek(tier2.DISK_SPAN)
                fh.write(tier2.stream(tier2.DISK_GUEST_SEED, tier2.DISK_SPAN))
            self.assertEqual(images.check(), [])
            with open(path, "r+b") as fh:
                fh.seek(3 * tier2.DISK_SPAN)
                fh.write(b"x")
            self.assertEqual(images.check(), ["image 0: changed outside the written span"])


CC = shutil.which("cc") or shutil.which("gcc")


@unittest.skipUnless(CC and sys.platform.startswith("linux"), "no C compiler for Linux")
class HostInit(unittest.TestCase):
    """init.c built against the host's C library: the disk check on files, SMP on host CPUs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = os.path.join(cls.tmp.name, "init-host")
        subprocess.run([CC, "-O2", "-Wall", "-Wextra", "-Werror", '-DWISP_ARCH="host"', "-o",
                        cls.binary, INIT_C], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_init(self, env, script=()):
        return subprocess.run([self.binary], input="".join(c + "\n" for c in script).encode(),
                              env=env, capture_output=True, timeout=120, check=False)

    def test_batch_disk_and_smp(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a.img"), os.path.join(tmp, "b.img")
            tier2.make_image(a, 0)
            tier2.make_image(b, 1)
            proc = self.run_init({"loops": "64", "wisp_disk": f"{a},{b}", "wisp_smp": "1"})
            self.assertEqual(proc.returncode, 0)
            text = proc.stdout.decode()
            cpus = min(len(os.sched_getaffinity(0)), 64)
            profile = {"disks": (("file", a), ("file", b)), "nic": None, "smp": cpus}
            problems, numbers = tier2.check(text, profile, run.crc_for, 64)
            if cpus == 1:  # the SMP line is checked from 2 CPUs on
                self.assertIn("WISP-SMP v=1 cpus=1 loops=64 crc=0x36c8a4f9", text)
            self.assertEqual(problems, [], text)
            self.assertEqual(tier2.check_image(a, 0) + tier2.check_image(b, 1), [])
            self.assertEqual(numbers["disks"][1]["size_kb"], 4096)

    def test_disk_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            small, wrong = os.path.join(tmp, "small.img"), os.path.join(tmp, "wrong.img")
            with open(small, "wb") as fh:
                fh.write(bytes(1024 * 1024))
            tier2.make_image(wrong, 3)  # disk 0 expects the host pattern of index 0
            text = self.run_init({"wisp_disk": f"{small},{wrong},{tmp}/none"}).stdout.decode()
            lines = tier2.lines(text, "WISP-DISK")
            self.assertEqual([d["status"] for d in lines],
                             ["too-small", "read-mismatch", "no-device"])
            self.assertEqual(lines[1]["verify_bad"], "0")

    def test_shell_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.img")
            tier2.make_image(a, 0)
            proc = self.run_init({"wisp": "shell", "loops": "64", "wisp_disk": a},
                                 ["disk", "smp", "net nosuch0", "help", "poweroff"])
            answers = shell.split_transcript(proc.stdout.decode(), echo=False)
            self.assertRegex(answers[0][1][0], r"^  WISP-DISK v=1 dev=.*status=ok$")
            self.assertRegex(answers[1][1][0], r"^  WISP-SMP v=1 cpus=\d+ loops=64 "
                                               r"crc=0x36c8a4f9 .*status=ok$")
            # not root, or no such interface: no NIC to test on the host
            self.assertRegex(answers[2][1][0], r"^  WISP-NET v=1 if=nosuch0 .*"
                                               r"status=(no-socket|no-interface)$")
            self.assertIn("  smp             the compute loop on every CPU at once",
                          answers[3][1])
            self.assertEqual(tier2.check_image(a, 0), [])


if __name__ == "__main__":
    unittest.main()
