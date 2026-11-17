"""Put an installed MS-DOS back to the HIMEM-only CONFIG.SYS (dos_mem.CONFIGS["himem"]) after a
CONFIG.SYS that hangs it: F5 at "Starting MS-DOS..." skips CONFIG.SYS and AUTOEXEC.BAT, as a person
would, then the file is rewritten. dos_mem.py runs it after a variant that failed."""
import os
import sys

import _dos

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dos_mem  # noqa: E402

DEFAULTS = {"TIMEOUT": "120"}


def qemu_args(v, out):
    return _dos.qemu_args({**v, "BOOT": v.get("BOOT", "c")}, out)


def run(m, v):
    m.vga_expect(r"Starting MS-DOS", timeout=int(v["TIMEOUT"]), interval=0.1)
    _dos.key(m, "f5")
    _dos.at_prompt(m, int(v["TIMEOUT"]))
    _dos.write_file(m, "C:\\CONFIG.SYS", dos_mem.config_lines("himem"))
    m.vga_snap("CONFIG.SYS back to HIMEM only")
