"""HTTP response and serial lifecycle checks without QEMU."""

import asyncio
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service


class Responses(unittest.TestCase):
    def test_two_gets_and_quit(self):
        for count in (1, 2):
            service.check_response(200, f"Linux 7.3.4 sparc request={count}\n".encode(),
                                   "sparc", count)
        service.check_response(200, b"bye\n", "sparc", None)

    def test_bad_replies(self):
        good = b"Linux 7.3.4 sparc request=1\n"
        for status, body, machine, count in [(404, good, "sparc", 1), (200, good, "sparc64", 1),
                                             (200, good, "sparc", 2), (200, good, "sparc", None),
                                             (200, b"Linux  sparc request=1\n", "sparc", 1)]:
            with self.subTest(body=body, status=status, machine=machine, count=count):
                with self.assertRaises(ValueError):
                    service.check_response(status, body, machine, count)


class Lifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_marker_order_and_exit(self):
        start = b"WISP-RUN v=1 start\r\n"
        ready = b"WISP-HTTPD listening port=8080\r\n"
        end = b"WISP-RUN v=1 exit=0 signal=0 ms=21\r\n"
        for lines, rc, ok in [(start + ready + end, 0, True), (ready + start + end, 0, False),
                              (start + ready, 0, False), (start + ready + end, 1, False),
                              (start + ready + end.replace(b"exit=0", b"exit=1"), 0, False)]:
            proc = AsyncMock()
            proc.stdout = asyncio.StreamReader()
            proc.stdout.feed_data(lines)
            proc.stdout.feed_eof()
            proc.wait.return_value = rc
            with self.subTest(lines=lines, rc=rc), patch.object(service, "requests"), patch("builtins.print"):
                run = service.console(proc, 1, "sparc32", time.monotonic())
                if ok:
                    await run
                else:
                    with self.assertRaises(RuntimeError):
                        await run
