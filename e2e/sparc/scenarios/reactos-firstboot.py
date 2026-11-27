"""First boot of an installed ReactOS (after reactos-install.py, which left the boot loader's default
without the kernel debugger, so COM1 is free): at the desktop, cmd.exe writes the logon report
C:\\wshlab.cmd and puts it into the Run key, writes the marker C:\\WSHLAB.TXT, each file read back on
COM1 and written again when a key got lost, then runs the report once (it must have the marker and
DefaultOS=ReactOS) and powers off. Every later logon sends the report to COM1 by itself
(reactos-boot-disk.py reads it).

Fails when the kernel debugger is on (its log on COM1).

Own QEMU: DISK=<the installed disk> MARKER="target=reactos0416\\nby=..."
"""
import re
import time

import _reactos

DEFAULTS = {"DISK": "/tmp/reactos-c.raw", "MARKER": "target=reactos0416", "TIMEOUT": "600", "FB_VIDEO": "2"}


def run(m, v):
    t0 = time.time()
    time.sleep(30)  # boot and logon (TCG: ~60 s to the desktop)
    m.metrics["settle_s"] = _reactos.settle(m, need=3, timeout=int(v["TIMEOUT"]))
    if re.search(_reactos.KD_BOOT, m.text):
        raise AssertionError("the kernel debugger is on (the boot loader's default is still ReactOS_KdSerial)")
    m.fb_stable(8, timeout=120)
    m.metrics["desktop_s"] = round(time.time() - t0)
    m.snap("desktop of the first boot", term=False)
    _reactos.dismiss_dialogs(m)
    _reactos.open_cmd(m)
    m.metrics["report_tries"] = _reactos.write_file_checked(m, _reactos.REPORT_SCRIPT, _reactos.REPORT_LINES)
    _reactos.type_line(m, f"reg add {_reactos.RUN_KEY} /v wshlab /d {_reactos.REPORT_SCRIPT} /f")
    got = _reactos.read_back(m, f"reg query {_reactos.RUN_KEY} /v wshlab", _reactos.REPORT_SCRIPT)
    if not got or not any(re.search(r"wshlab\s+REG_SZ\s+" + re.escape(_reactos.REPORT_SCRIPT), x) for x in got):
        raise AssertionError(f"the Run key doesn't have the report: {got!r}")
    lines = [x for x in v["MARKER"].replace("\\n", "\n").splitlines() if x.strip()]
    m.metrics["marker_tries"] = _reactos.write_file_checked(m, "C:\\WSHLAB.TXT", lines)
    cursor = m.serial_cursor()
    _reactos.type_line(m, _reactos.REPORT_SCRIPT)
    r = _reactos.wait_serial(m, _reactos.REPORT, cursor, 120, what="the report")
    text = _reactos.report(m, r)
    m.log("report:\n" + text)
    got = [x.rstrip() for x in text.splitlines()]
    if not all(x.rstrip() in got for x in lines) or "DefaultOS=ReactOS" not in got:
        raise AssertionError(f"the report lacks the marker or DefaultOS=ReactOS:\n{text}")
    m.snap("the logon report on COM1, with the marker", term=True)
    _reactos.type_line(m, "exit")
    _reactos.shutdown(m)


def qemu_args(v, out):
    return _reactos.qemu_args(v, out)
