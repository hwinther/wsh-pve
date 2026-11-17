"""The first boot of an installed DOS from its hard disk: make the result predictable.

MS-DOS (FLAVOUR=msdos): replaces SETUP's CONFIG.SYS and AUTOEXEC.BAT with known ones (CONFIG below:
"himem" = HIMEM.SYS and DOS=HIGH; "emm386" adds EMM386 NOEMS and DOS=HIGH,UMB) without SMARTDRV, so
a VM that is stopped from outside loses nothing; KEYBOARD (us) other than us adds `KEYB <layout>`.
FreeDOS (FLAVOUR=freedos) keeps its own FDCONFIG.SYS/FDAUTO.BAT. Both write the marker C:\\WSHLAB.TXT
(MARKER: its lines, from install.Job.marker()) and end at the prompt; the lab then stops the VM.
"""
import _dos

DEFAULTS = {"FLAVOUR": "msdos", "CONFIG": "himem", "KEYBOARD": "us", "MARKER": "target=manual", "TIMEOUT": "300"}

CONFIGS = {
    "himem": ["DEVICE=C:\\DOS\\HIMEM.SYS", "DOS=HIGH", "FILES=30", "BUFFERS=20"],
    "emm386": ["DEVICE=C:\\DOS\\HIMEM.SYS", "DEVICE=C:\\DOS\\EMM386.EXE NOEMS", "DOS=HIGH,UMB", "FILES=30",
               "BUFFERS=20"],
}


def qemu_args(v, out):
    return _dos.qemu_args({**v, "BOOT": v.get("BOOT", "c")}, out)


def autoexec(v):
    lines = ["@ECHO OFF", "PROMPT $P$G", "PATH C:\\DOS", "SET TEMP=C:\\DOS"]
    if v["KEYBOARD"].lower() != "us":
        lines.append(f"KEYB {v['KEYBOARD'].upper()},,C:\\DOS\\KEYBOARD.SYS")
    return lines


def run(m, v):
    _dos.boot_to_prompt(m, int(v["TIMEOUT"]))
    m.vga_snap("first boot: the prompt")
    if v["FLAVOUR"] == "msdos":
        _dos.run(m, "CLS")
        _dos.write_file(m, "C:\\CONFIG.SYS", CONFIGS[v["CONFIG"]])
        _dos.write_file(m, "C:\\AUTOEXEC.BAT", autoexec(v))
    _dos.run(m, "CLS")
    _dos.write_file(m, "C:\\WSHLAB.TXT", v["MARKER"].splitlines())
    out = _dos.run(m, "TYPE C:\\WSHLAB.TXT")
    m.vga_snap("the marker")
    first = v["MARKER"].splitlines()[0]
    if first not in out:
        raise AssertionError(f"C:\\WSHLAB.TXT doesn't start with {first!r}:\n{out}")
