"""Helpers for DOS guests on x86: the console is the VGA text screen (lab.Machine.vga_screen(), exact) and
the keyboard is QMP send-key (US layout). Shared by the DOS install, first-boot, check and memory
scenarios. Works for a PVE VM (attach mode, no serial port) and for a QEMU of the lab's own
(qemu_args() below, for CI and for trying things without PVE).
"""
import os
import re
import time

import lab

PROMPT = r"^[A-Z]:\\[^>\n]*>$"  # C:\>, A:\>, C:\DOS> on the line the cursor is on

# How DOS's BIOS keyboard buffer (15 keys) wants to be fed: a key held 50 ms, then a pause. The guest
# reads the buffer from its idle loop, so under TCG and while it is busy with the disk a faster rate
# loses keys.
HOLD_MS, DELAY_S = 50, 0.06


def qemu_args(v, out):
    """A PC as the DOS targets' PVE profile builds it (targets_dos.X86_DOS), for the lab's own QEMU:
    FLOPPY (A:), DISK (C:, raw; created with DISK_MB MiB if missing), DISK2 (D:), VGA, MEM, CPU,
    ACCEL (tcg), OPTION_ROMS (comma-separated files for -option-rom), EXTRA (more arguments)."""
    args = [v.get("QEMU", "qemu-system-x86_64"), "-machine", f"pc,accel={v.get('ACCEL', 'tcg')}",
            "-cpu", v.get("CPU", "pentium"), "-m", str(v.get("MEM", "32")), "-vga", v.get("VGA", "std"),
            "-nodefaults", "-boot", f"order={v.get('BOOT', 'ac')}", "-net", "none"]
    if v.get("FLOPPY"):
        args += ["-drive", f"if=floppy,index=0,format=raw,readonly=on,file={v['FLOPPY']}"]
    if v.get("DISK"):
        disk = v["DISK"]
        if not os.path.exists(disk):
            with open(disk, "wb") as f:
                f.truncate(int(v.get("DISK_MB", "512")) << 20)
        args += ["-drive", f"if=ide,index=0,format=raw,file={disk}"]
    if v.get("DISK2"):
        args += ["-drive", f"if=ide,index=1,format=raw,file={v['DISK2']}"]
    for rom in filter(None, v.get("OPTION_ROMS", "").split(",")):
        args += ["-option-rom", rom]
    return args + v.get("EXTRA", "").split()


def swaps(v):
    """SWAPS ("floppy0=vol floppy0=vol ..."): the media the scenario inserts itself, in order."""
    return [tuple(x.split("=", 1)) for x in v.get("SWAPS", "").split()]


def key(m, *names):
    """Press keys one after another (qcodes: ret, esc, f3, up, ...); "ctrl-z" style chords too."""
    for name in names:
        m.fb_key(*name.split("-")) if "-" in name and len(name) > 1 else m.fb_key(name)
        time.sleep(0.2)


def type_text(m, text):
    """Type text; a newline is Enter."""
    m.fb_type(text, hold=HOLD_MS, delay=DELAY_S)


def at_prompt(m, timeout=120):
    """Wait for a DOS prompt on the cursor's line; returns the screen."""
    return m.vga_expect(PROMPT, timeout=timeout, tail=1)


def run(m, command, timeout=120, prompt=PROMPT):
    """Type a command at the prompt, wait for the next prompt, return the lines it printed (what is
    still on the screen: up to 23 lines; longer output belongs in a file). `prompt`: the regex of the
    prompt that follows (DOS's by default; DEBUG's `-`, for one)."""
    # Type the command, wait until it is on the screen, and only then press Enter: the screen before
    # Enter is never the screen after it, also when a command prints exactly what the previous one did
    # (the same TYPE twice on a full, scrolled screen ends on the same screen and cursor).
    type_text(m, command)
    tail = command[-20:]
    end = time.time() + 15
    def typed(s):  # a long command wraps: the line above the cursor's is full and continues on it
        return s.text_mode and (s.line(s.cursor[1] - 1) + s.cursor_line()).endswith(tail)

    before = m.vga_screen()
    while not typed(before) and time.time() < end:
        time.sleep(0.2)
        before = m.vga_screen()
    type_text(m, "\n")
    end = time.time() + timeout
    while True:
        time.sleep(0.5)
        s = m.vga_screen()
        if s.text_mode and re.search(prompt, s.cursor_line(), re.M) and (
                s.text != before.text or s.cursor != before.cursor):
            row = s.cursor[1]
            # the command's own line: the last line that ends with what was typed
            lines = [x.rstrip() for x in s.lines[:row]]
            idx = max((i for i, x in enumerate(lines) if x.endswith(command)), default=-1)
            return "\n".join(lines[idx + 1:])
        m._check_alive()
        if time.time() > end:
            raise lab.Timeout(f"{command!r}: no prompt within {timeout}s (cursor {s.cursor}, {s.cols}x{s.rows}, "
                              f"mode {s.mode}); screen:\n{s.text if s.text_mode else '-'}")


def write_file(m, path, lines):
    """Create a text file line by line with `ECHO line>>file`, one command per line, each typed at the
    prompt. Not COPY CON: it flushes the keyboard buffer when it starts reading, and lines typed while
    it was still opening the file were lost (CONFIG.SYS without its first line). Lines must be ASCII
    the US keyboard can type, without < > |, and no longer than about 100 characters."""
    for n, line in enumerate(lines):
        if re.search(r"[<>|]", line) or not line.strip() or line.strip().upper() in ("ON", "OFF"):
            raise ValueError(f"can't ECHO {line!r} into a file")
        run(m, f"ECHO {line}{'>' if n == 0 else '>>'}{path}")
    out = run(m, f"TYPE {path}")
    got = [x.rstrip() for x in out.splitlines()]
    want = [x.rstrip() for x in lines]
    if got[-len(want):] != want and "".join(got).replace(" ", "") != "".join(want).replace(" ", ""):
        raise AssertionError(f"{path} reads back as {got!r}, expected {want!r}")


DEBUG_PROMPT = r"^-$"


def debug_write(m, path, data, debug="DEBUG"):
    """Write a small binary file (a .COM program) from the DOS prompt with DEBUG, typed as a person
    would: `E` lines of hex bytes from 0100, the length in CX, `N` and `W`. For files that ECHO can't
    write (any byte value); up to 64K. Checks that DEBUG wrote the expected size and that DIR lists it."""
    if not 0 < len(data) <= 0xFF00:
        raise ValueError("DEBUG writes 1 byte to 65280 bytes from offset 0100")
    run(m, debug, prompt=DEBUG_PROMPT)
    for off in range(0, len(data), 16):
        chunk = " ".join(f"{b:02X}" for b in data[off:off + 16])
        run(m, f"E {0x100 + off:04X} {chunk}", prompt=DEBUG_PROMPT)
    run(m, "RCX", prompt=r"^:$")
    run(m, f"{len(data):X}", prompt=DEBUG_PROMPT)
    run(m, f"N {path}", prompt=DEBUG_PROMPT)
    out = run(m, "W", prompt=DEBUG_PROMPT)
    if not re.search(rf"Writing 0*{len(data):X} bytes", out, re.I):
        raise AssertionError(f"DEBUG W printed {out!r}, expected {len(data):X} bytes written")
    run(m, "Q")
    listing = run(m, f"DIR {path}")
    if not re.search(rf"\b{len(data)}\b", listing.replace(",", "")):
        raise AssertionError(f"DIR {path} doesn't list {len(data)} bytes:\n{listing}")


def us_keyboard(m, layout):
    """With another layout loaded by KEYB, switch to the US layout (Ctrl-Alt-F1), so typed commands come
    out as sent."""
    if layout and layout.lower() != "us":
        m.fb_key("ctrl", "alt", "f1")
        time.sleep(0.3)


def wait_medium_change(m, drive, old, timeout=180):
    """Wait until the drive holds another medium than `old` (put there by install.MediaSwapper or a
    person); returns the new one."""
    end = time.time() + timeout
    while time.time() < end:
        now = m.medium(drive)
        if now != old:
            return now
        m._check_alive()
        time.sleep(0.5)
    raise lab.Timeout(f"{drive} still holds {old} after {timeout}s: nothing swapped the disk")


def wait_gone(m, pattern, timeout=120):
    """Wait until a regex is no longer on the screen (a dialogue was answered)."""
    rx = re.compile(pattern, re.M)
    end = time.time() + timeout
    while time.time() < end:
        s = m.vga_screen()
        if s.text_mode and not rx.search(s.text):
            return s
        m._check_alive()
        time.sleep(0.5)
    raise lab.Timeout(f"{pattern!r} still on the screen after {timeout}s")


def boot_to_prompt(m, timeout=300):
    """From power-on to the DOS prompt of the installed system; returns the screen."""
    s = at_prompt(m, timeout)
    m.log(f"at the prompt: {s.cursor_line()!r}")
    return s
