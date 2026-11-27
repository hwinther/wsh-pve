"""Boot an installed ReactOS to its desktop and check it (lab.py install reactos0416 --check, boot-test):
the logon report on COM1 (C:\\wshlab.cmd from the Run key: `ver`, the host name, the boot loader's
default, the marker, `ipconfig`) must match VERSION and CHECK, the desktop screenshot must be the
configured size and not blank, and with IDLE_BELOW the VM idling at the desktop must take less than
that much of a host core. Then power off from the Run dialog.

Own QEMU: DISK=<the installed disk> CHECK="(?m)^target=reactos0416$"
"""
import re
import time

import _reactos

DEFAULTS = {"DISK": "/tmp/reactos-c.raw", "VERSION": r"(?m)^Version 0\.4\.16-x86 ","CHECK": "",
            "IDLE_BELOW": "", "IDLE_SECONDS": "15", "SIZE": "1024x768", "TIMEOUT": "600", "FB_VIDEO": "2"}


def qemu_args(v, out):
    return _reactos.qemu_args(v, out)


def run(m, v):
    t0 = time.time()
    text = _reactos.wait_report(m, int(v["TIMEOUT"]))
    m.metrics["logon_s"] = round(time.time() - t0)
    for name, rx in (("VERSION", v["VERSION"]), ("CHECK", v["CHECK"]), ("boot loader", r"(?m)^DefaultOS=ReactOS$")):
        if rx and not re.search(rx, text):
            raise AssertionError(f"{name} {rx!r} not in the logon report:\n{text}")
    m.fb_stable(8, timeout=120)
    step = m.snap("desktop", term=True)
    m.fb_check(step["fb_png"], tuple(int(x) for x in v["SIZE"].split("x")) if v["SIZE"] else None)
    _reactos.settle(m)  # the report's cmd window closes, the logon's work ends
    if v["IDLE_BELOW"]:
        m.cpu_use(int(v["IDLE_SECONDS"]), below=float(v["IDLE_BELOW"]))
    _reactos.dismiss_dialogs(m)
    _reactos.shutdown(m)
