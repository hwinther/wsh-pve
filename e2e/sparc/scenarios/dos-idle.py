"""Host CPU of a DOS guest idling at the prompt, and that it still answers while idle.

Boots an installed DOS from its hard disk to the prompt, waits SETTLE seconds and measures QEMU's host
CPU use over IDLE seconds (`cpu_pct`, percent of one core; BELOW/ABOVE fail the run outside a bound).
Then checks what an idle driver could break: the BIOS timer (`ticks_per_s`, the tick count at
0040:006C read over QMP for 5 s: 18.2 when the timer interrupt is delivered), the keyboard (a typed
`ECHO` comes back on the screen) and, with BUSY (programs on the guest, space separated, e.g.
`C:\\BUSY.COM C:\\BUSYK.COM` from `dos_tools.py com`), a busy program's speed: each prints the loop
count of five seconds in hex (`busy`: {program: count}).

Runs against a PVE VM (`--pve <vmid>`) or the lab's own QEMU (`_dos.qemu_args`: DISK=...).
"""
import re
import struct
import time

import _dos

DEFAULTS = {"IDLE": "30", "SETTLE": "10", "BELOW": "", "ABOVE": "", "BUSY": "", "KEYBOARD": "us",
            "TIMEOUT": "300",
            # no framebuffer video: its screendump every second would be part of what is measured
            "FB_VIDEO": "0"}


def qemu_args(v, out):
    return _dos.qemu_args({**v, "BOOT": v.get("BOOT", "c")}, out)


def ticks(m):
    return struct.unpack("<I", m.pmem(0x46C, 4))[0]


def run(m, v):
    _dos.boot_to_prompt(m, int(v["TIMEOUT"]))
    _dos.us_keyboard(m, v["KEYBOARD"])
    _dos.run(m, "CLS")
    m.vga_snap("idle at the prompt")
    time.sleep(float(v["SETTLE"]))
    m.cpu_use(float(v["IDLE"]), below=v["BELOW"] or None, above=v["ABOVE"] or None)

    t0, w0 = ticks(m), time.time()
    time.sleep(5)
    rate = (ticks(m) - t0) / (time.time() - w0)
    m.metrics["ticks_per_s"] = round(rate, 1)
    m.log(f"BIOS timer: {rate:.1f} ticks/s while idle")
    if not 15 <= rate <= 22:
        raise AssertionError(f"the BIOS timer runs at {rate:.1f} ticks/s while idle, expected 18.2")

    out = _dos.run(m, "ECHO WSH IDLE KEYS OK")
    if "WSH IDLE KEYS OK" not in out:
        raise AssertionError(f"ECHO printed {out!r}")

    busy = {}
    for prog in v["BUSY"].split():
        out = _dos.run(m, prog, timeout=60)
        hexes = re.findall(r"^([0-9A-F]{8})$", out, re.M)
        if not hexes:
            raise AssertionError(f"{prog} printed no count: {out!r}")
        busy[prog] = int(hexes[-1], 16)
        m.log(f"{prog}: {busy[prog]} iterations in 5 s")
    if busy:
        m.metrics["busy"] = busy
    m.vga_snap("after the checks")
