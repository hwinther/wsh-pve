"""Boot an installed DOS from its hard disk and check it: the prompt, `VER` (VERSION: a regex), the
marker C:\\WSHLAB.TXT (CHECK: a regex it must contain) and `MEM` as evidence. With KEYBOARD other than
us (a KEYB layout in AUTOEXEC.BAT) the US layout is switched on with Ctrl-Alt-F1 before typing.

Then the guest idles at the prompt for IDLE seconds (15) and QEMU's host CPU use is recorded
(`cpu_pct`, percent of one core). With IDLE_BELOW it must stay below that: the guest's idle driver
halts the CPU (POWER.EXE in MS-DOS, FDAPM in FreeDOS); without one DOS keeps a whole core busy."""
import re
import time

import _dos

DEFAULTS = {"VERSION": r"(MS-DOS|FreeDOS)", "CHECK": r"(?m)^target=", "KEYBOARD": "us", "TIMEOUT": "300",
            "IDLE": "15", "IDLE_BELOW": ""}


def qemu_args(v, out):
    return _dos.qemu_args({**v, "BOOT": v.get("BOOT", "c")}, out)


def run(m, v):
    _dos.boot_to_prompt(m, int(v["TIMEOUT"]))
    m.vga_snap("boot from the hard disk")
    _dos.us_keyboard(m, v["KEYBOARD"])
    ver = _dos.run(m, "VER")
    if not re.search(v["VERSION"], ver):
        raise AssertionError(f"VER printed {ver!r}, expected {v['VERSION']!r}")
    _dos.run(m, "CLS")
    marker = _dos.run(m, "TYPE C:\\WSHLAB.TXT")
    m.vga_snap("the marker")
    if not re.search(v["CHECK"], marker):
        raise AssertionError(f"C:\\WSHLAB.TXT doesn't match {v['CHECK']!r}:\n{marker}")
    _dos.run(m, "CLS")
    mem = _dos.run(m, "MEM")
    m.metrics["mem"] = mem
    m.vga_snap("MEM")
    if float(v["IDLE"] or 0):
        time.sleep(3)  # let MEM's output settle; nothing reads the screen while the CPU use is measured
        m.cpu_use(float(v["IDLE"]), below=v["IDLE_BELOW"] or None)
