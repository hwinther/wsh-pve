"""The MCP server (mcp_server.py) against a real guest, driven by the MCP Python SDK's own client over stdio.

Boots an Alpine Linux CD (x86_64, no Sun software) under `lab.py serve`, starts the server with that lab
VM as its only allowed VM and checks what an assistant would do: list the VMs, wait for the login prompt
on the serial console, log in, run a command and read its output, type on the display keyboard, take
screenshots (a valid PNG of the size reported, scaled on request), read the screen as text, and that a
VM not on the allow-list is refused and the power/monitor tools are absent unless enabled.

Runs in the MCP image (mcp.Dockerfile on top of the lab image):

    docker run --rm -v /srv/iso:/iso:ro -e MCP_TEST_ISO=/iso/alpine-virt-3.24.4-x86_64.iso \
      --entrypoint /opt/wsh-lab-mcp/bin/python wsh-lab-mcp -m unittest -v tests/test_mcp_server.py

  MCP_TEST_ISO    an Alpine x86_64 CD (standard or virt); without it the pinned one below is downloaded
                  and its sha256 checked, into MCP_TEST_CACHE (default /tmp/wsh-lab-mcp-test)
  MCP_TEST_ACCEL  kvm or tcg (default: kvm when /dev/kvm can be opened, else tcg)
"""
import asyncio
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

ISO_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.4-x86_64.iso"
ISO_SHA256 = "157d353f8e54252cad2d9812a0d56bb7fa2231fc154a110e1d180d7480ef8b4f"
BOOT_TIMEOUT = 600  # TCG on a shared runner: Alpine reaches its login prompt in ~30-90 s


def alpine_iso():
    if os.environ.get("MCP_TEST_ISO"):
        return os.environ["MCP_TEST_ISO"]
    cache = os.environ.get("MCP_TEST_CACHE", "/tmp/wsh-lab-mcp-test")
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, os.path.basename(ISO_URL))
    for attempt in (1, 2):
        if os.path.exists(path):
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            if h.hexdigest() == ISO_SHA256:
                return path
            os.unlink(path)
        if attempt == 1:
            with urllib.request.urlopen(ISO_URL, timeout=300) as r, open(path + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
            os.replace(path + ".part", path)
    raise RuntimeError(f"{ISO_URL}: sha256 isn't {ISO_SHA256}")


def accel():
    if os.environ.get("MCP_TEST_ACCEL"):
        return os.environ["MCP_TEST_ACCEL"]
    try:
        os.close(os.open("/dev/kvm", os.O_RDWR))
        return "kvm"
    except OSError:
        return "tcg"


class Keys(unittest.TestCase):
    """Key names and chords, without a guest."""

    def test_display_chords(self):
        import mcp_server as s

        self.assertEqual(s.display_chord("ctrl-alt-delete"), ["ctrl", "alt", "delete"])
        self.assertEqual(s.display_chord("Ctrl+Alt+Del"), ["ctrl", "alt", "delete"])
        self.assertEqual(s.display_chord("Stop-A"), ["stop", "a"])
        self.assertEqual(s.display_chord("L1-A"), ["stop", "a"])
        self.assertEqual(s.display_chord("ret"), ["ret"])
        self.assertEqual(s.display_chord("A"), ["shift", "a"])
        self.assertEqual(s.display_chord("-"), ["minus"])
        self.assertEqual(s.display_chord("shift-f1"), ["shift", "f1"])
        with self.assertRaises(ValueError):
            s.display_chord("ctrl-$(reboot)")

    def test_serial_keys(self):
        import mcp_server as s

        self.assertEqual(s.serial_key("ctrl-c"), ("key", "ctrl-c"))
        self.assertEqual(s.serial_key("ctrl-z"), ("text", "\x1a"))
        self.assertEqual(s.serial_key("Return"), ("key", "enter"))
        self.assertEqual(s.serial_key("f2"), ("key", "f2"))
        with self.assertRaises(ValueError):
            s.serial_key("Stop-A")

    def test_disabled_tools_are_absent(self):
        out = subprocess.run([sys.executable, os.path.join(HERE, "mcp_server.py"), "--lab", "x=/nonexistent",
                              "--check"], capture_output=True, text=True, check=True).stdout
        tools = set(json.loads(out)["tools"])
        self.assertEqual(tools, {"list_vms", "vm_status", "screenshot", "screen_text", "serial_read", "wait_for",
                                 "send_keys", "type_text", "serial_release"})
        out = subprocess.run([sys.executable, os.path.join(HERE, "mcp_server.py"), "--lab", "x=/nonexistent",
                              "--allow-reset", "--allow-hmp", "--check"], capture_output=True, text=True,
                             check=True).stdout
        self.assertTrue({"reset_vm", "hmp"} <= set(json.loads(out)["tools"]))
        self.assertNotIn("stop_vm", json.loads(out)["tools"])

    def test_nothing_allowed_refuses_to_start(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "mcp_server.py")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing allowed", r.stderr)


class AlpineGuest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix="mcp-test-")
        cls.run_dir = os.path.join(cls.work, "run")
        qemu = ["qemu-system-x86_64", "-accel", accel(), "-m", "512", "-cdrom", alpine_iso(), "-boot", "d",
                "-vga", "std", "-nic", "none"]
        with open(os.path.join(cls.work, "serve.log"), "wb") as log:
            cls.serve = subprocess.Popen([sys.executable, os.path.join(HERE, "lab.py"), "serve", "--out",
                                          cls.run_dir, "--no-ocr", "--", *qemu], stdout=log, stderr=subprocess.STDOUT)
        end = time.time() + 60
        while not os.path.exists(os.path.join(cls.run_dir, "ctl.sock")):
            if cls.serve.poll() is not None or time.time() > end:
                raise RuntimeError("lab.py serve didn't start:\n" + open(os.path.join(cls.work, "serve.log")).read())
            time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        subprocess.run([sys.executable, os.path.join(HERE, "lab.py"), "ctl", "--out", cls.run_dir, "stop"],
                       capture_output=True, timeout=60)
        try:
            cls.serve.wait(30)
        except subprocess.TimeoutExpired:
            cls.serve.kill()
        if os.environ.get("MCP_TEST_KEEP"):
            print(f"kept {cls.work}", file=sys.stderr)
        else:
            shutil.rmtree(cls.work, ignore_errors=True)

    def test_drive_the_guest(self):
        asyncio.run(self.drive())

    def test_exits_when_the_client_is_gone(self):
        """A client that goes away during a long wait_for: the server exits at once, not when the wait ends."""
        srv = subprocess.Popen([sys.executable, os.path.join(HERE, "mcp_server.py"), "--lab",
                                f"alpine={self.run_dir}"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for msg in ({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "wait_for",
                        "arguments": {"vm": "alpine", "pattern": "never-printed", "timeout_s": 300}}}):
            srv.stdin.write((json.dumps(msg) + "\n").encode())
            srv.stdin.flush()
        self.assertIn(b'"id":1', srv.stdout.readline().replace(b" ", b""))
        time.sleep(3)  # the wait is running
        self.assertIsNone(srv.poll())
        t0 = time.time()
        srv.stdin.close()
        srv.wait(30)
        self.assertLess(time.time() - t0, 10)
        srv.stdout.close()

    async def drive(self):
        from mcp import ClientSession, StdioServerParameters, stdio_client
        from PIL import Image

        params = StdioServerParameters(command=sys.executable, args=[
            os.path.join(HERE, "mcp_server.py"), "--lab", f"alpine={self.run_dir}"])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, **args):
                res = await s.call_tool(name, args)
                self.assertFalse(res.is_error, f"{name}: {res.content}")
                return res

            tools = {t.name: t for t in (await s.list_tools()).tools}
            for absent in ("reset_vm", "stop_vm", "hmp"):
                self.assertNotIn(absent, tools)
            self.assertTrue(tools["screenshot"].annotations.read_only_hint)
            self.assertTrue(tools["type_text"].annotations.destructive_hint)

            vms = (await call("list_vms")).structured_content["vms"]
            self.assertEqual([(v["vm"], v["kind"], v["arch"], v["display"], v["running"]) for v in vms],
                             [("alpine", "lab", "x86_64", "framebuffer", True)])
            st = (await call("vm_status", vm="alpine")).structured_content
            self.assertEqual(st["state"], "running")
            self.assertIsInstance(st["cpu_pct"], float)

            # Alpine's inittab runs a getty on ttyS0, the lab's serial port
            m = (await call("wait_for", vm="alpine", pattern=r"login: $", timeout_s=BOOT_TIMEOUT)).structured_content
            self.assertTrue(m["matched"], m)
            t = (await call("type_text", vm="alpine", text="root\n", to="serial")).structured_content
            self.assertIsInstance(t["serial_cursor"], int)
            m = (await call("wait_for", vm="alpine", pattern=r"# $", cursor=t["serial_cursor"],
                            timeout_s=60)).structured_content
            self.assertTrue(m["matched"], m)
            t = (await call("type_text", vm="alpine", text="echo mcp-$((6*7)); uname -m\n",
                            to="serial")).structured_content
            m = (await call("wait_for", vm="alpine", pattern=r"^mcp-(\d+)\s*$", cursor=t["serial_cursor"],
                            timeout_s=60)).structured_content
            self.assertTrue(m["matched"], m)
            self.assertEqual(m["groups"], ["42"])
            m = (await call("wait_for", vm="alpine", pattern=r"^x86_64\s*$", timeout_s=30)).structured_content
            self.assertTrue(m["matched"], m)
            # a timeout is a result, not an error, and says what it saw
            m = (await call("wait_for", vm="alpine", pattern="never-printed", timeout_s=2)).structured_content
            self.assertFalse(m["matched"])
            rd = (await call("serial_read", vm="alpine", cursor=t["serial_cursor"], max_chars=20)).structured_content
            self.assertEqual(len(rd["text"]), 20)
            self.assertTrue(rd["more"])

            # the serial terminal as text; the same screen twice is "unchanged"
            term = (await call("screen_text", vm="alpine", source="terminal")).structured_content
            self.assertIn("mcp-42", term["text"])
            again = (await call("screen_text", vm="alpine", source="terminal",
                                if_changed_since=term["screen_id"])).structured_content
            self.assertTrue(again["unchanged"])

            # the display keyboard: log in on the VGA console, write to the serial port from there
            await call("type_text", vm="alpine", text="root\n", to="display")
            await asyncio.sleep(3)
            t = (await call("type_text", vm="alpine", text="echo from-the-$((1+1))nd-console > /dev/ttyS0\n",
                            to="display")).structured_content
            self.assertEqual(t["to"], "display")
            m = (await call("wait_for", vm="alpine", pattern=r"from-the-2nd-console", cursor=t["serial_cursor"],
                            timeout_s=60)).structured_content
            self.assertTrue(m["matched"], m)
            k = (await call("send_keys", vm="alpine", keys=["ctrl-l", "shift-tab", "ret"],
                            to="display")).structured_content
            self.assertEqual(k["sent"], 3)

            # screenshots: a PNG of the size reported, scaled on request
            res = await call("screenshot", vm="alpine", max_width=0)
            meta = res.structured_content
            img = [c for c in res.content if c.type == "image"]
            self.assertEqual(len(img), 1)
            self.assertEqual(img[0].mime_type, "image/png")
            data =base64.b64decode(img[0].data)
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            with Image.open(io.BytesIO(data)) as im:
                self.assertEqual(im.size, (meta["width"], meta["height"]))
                self.assertGreaterEqual(im.width, 640)
                lo, hi = im.convert("L").getextrema()
                self.assertLess(lo, hi, "the screenshot is blank")
            small = await call("screenshot", vm="alpine", max_width=320)
            png = base64.b64decode([c for c in small.content if c.type == "image"][0].data)
            with Image.open(io.BytesIO(png)) as im:
                self.assertEqual(im.width, 320)

            # the display as text (OCR), when the image has tesseract
            if shutil.which("tesseract"):
                txt = (await call("screen_text", vm="alpine", source="display")).structured_content
                self.assertRegex(txt["text"], r"(?i)login|alpine|localhost")
                self.assertIn(txt["method"], ("vga-text", "ocr"))  # the text buffer while in a text mode

            # refused: a VM that isn't on the allow-list, PVE VMID or name
            for vm in ("100", "other"):
                res = await s.call_tool("screenshot", {"vm": vm})
                self.assertTrue(res.is_error)
                self.assertIn("isn't one this server may touch", res.content[0].text)
            res = await s.call_tool("hmp", {"vm": "alpine", "command": "info status"})
            self.assertTrue(res.is_error)


if __name__ == "__main__":
    unittest.main()
