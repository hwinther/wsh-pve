"""Boot an installed DOS from its hard disk and check it: the prompt, `VER` (VERSION: a regex), the
marker C:\\WSHLAB.TXT (CHECK: a regex it must contain) and `MEM` as evidence. With KEYBOARD other than
us (a KEYB layout in AUTOEXEC.BAT) the US layout is switched on with Ctrl-Alt-F1 before typing."""
import re

import _dos

DEFAULTS = {"VERSION": r"(MS-DOS|FreeDOS)", "CHECK": r"(?m)^target=", "KEYBOARD": "us", "TIMEOUT": "300"}


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
