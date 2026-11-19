"""BEL on the sparc32 framebuffer console (cg3). The firmware's terminal answers BEL by inverting the
screen, waiting and inverting it back. OpenBIOS before openbios/patches/0026 waited on its
millisecond counter, which only its own level-14 timer interrupt advances; once a client OS has its
own trap table that handler never runs, so the wait never ended: the screen stayed inverted and the
console hung (Solaris 2.6 on the framebuffer console: a BEL from `echo`, or Tab in bash with no
unique match). The scenario rings the bell at the firmware prompt and then in the guest, and checks
that the screen comes back to its colours and the shell goes on.

    lab.py run scenarios/fb-bell.py --out /mnt/runs/bell --var DISK=/mnt/runs/bell/disk.raw \
        [--var GUEST=solaris|sunos4|netbsd|prom] [--var EXPECT=back|hang]

  GUEST    solaris: `boot disk:a -s`, the root password at sulogin; sunos4: `boot disk:a -s`;
           netbsd: multi-user, root login; prom: only the firmware prompt (no DISK needed)  (solaris)
  EXPECT   back: the screen must come back and the shell answer (a fixed firmware);
           hang: the screen must stay inverted and the shell not answer for WAIT seconds
           (shows the bug with an unfixed firmware)                                   (back)
  WAIT     seconds to watch after the BEL                                             (30)
  PASSWORD the root password                                                          (wshlab)
  TICKS_SYM the address of the firmware's `obp_ticks` (hex) when its ELF is stripped, as the
           packaged one is: `nm` of openbios-builtin.elf.nostrip from the same sources     (none)
  TAB      a command that starts bash (e.g. `exec /usr/bin/bash`): ring bash's completion bell
           (Tab after `echo /usr/s`) instead of echoing a BEL                         (none)
  LOOP     1: also time the firmware's own wait at the prompt (prom_loop_ms: get-msecs around
           100000 reads of get-msecs, read back by OCR)                               (none)

DISK must be a copy: the guest writes to it. The consoles are on the framebuffer and the Sun
keyboard (CONSOLE=fb); `auto-boot?` is false, so the firmware stops at its prompt first. Metrics:
prom_dark_s and guest_dark_s (how long the screen stayed inverted, from screenshots about every
0.2 s), guest_hung and, when the guest hangs: `info registers` (pc, npc, psr, tbr), five PC samples
and the firmware's tick count (`obp_ticks`, read twice 5 s apart, through the symbol in the firmware
ELF).
"""
import os
import re
import struct
import time

from _sparc32 import DEFAULTS as BASE, qemu_args as sparc32_args

DEFAULTS = {**BASE, "CONSOLE": "fb", "BOOT": "c", "NO_CD": "1", "GUEST": "solaris", "EXPECT": "back",
            "WAIT": "30", "PASSWORD": "wshlab", "LOOP": "", "TAB": "", "PROM_ENV": "auto-boot?=false"}

BANNER = r"for detailed information"  # the prompt follows it (OCR misreads "0 >")
# One BEL (tr: every guest's echo treats escapes differently), then a line only the shell's output
# has (the quotes split it in the typed command).
BEL_LINE = r"echo B | tr B '\007'; echo AFTER-''BEL"
BEL3_LINE = r"for i in 1 2 3; do echo B | tr B '\007'; done; echo DONE-''THREE"


def qemu_args(v, out):
    return sparc32_args(v, out)


def luma(m):
    from PIL import Image

    img = Image.open(m.screendump("_bell")).convert("L")
    return sum(img.resize((64, 48)).getdata()) / (64 * 48)


def elf_symbol(path, name):
    """The value of `name` in the symbol table of a 32-bit big-endian ELF (the sparc32 firmware)."""
    with open(path, "rb") as f:
        data = f.read()
    shoff, = struct.unpack_from(">I", data, 0x20)
    shentsize, shnum = struct.unpack_from(">HH", data, 0x2e)
    secs = [struct.unpack_from(">IIIIIIIIII", data, shoff + i * shentsize) for i in range(shnum)]
    for s in secs:
        if s[1] != 2:  # SHT_SYMTAB
            continue
        strtab = secs[s[6]]
        for off in range(s[4], s[4] + s[5], 16):
            st_name, st_value = struct.unpack_from(">II", data, off)
            start = strtab[4] + st_name
            if data[start:data.index(b"\0", start)].decode() == name:
                return st_value
    return None


def read_word(m, addr):
    """A word at a virtual address, through the CPU's current MMU context (HMP x)."""
    r = re.search(r":\s*0x([0-9a-f]+)", m.hmp(f"x /1wx 0x{addr:x}"))
    return int(r.group(1), 16) if r else None


def registers(m):
    out = m.hmp("info registers")
    regs = {}
    for key in ("pc", "npc", "psr", "tbr"):
        r = re.search(rf"\b{key}:\s*([0-9a-fx]+)", out, re.I)
        if r:
            regs[key] = r.group(1)
    return regs, out


def watch(m, seconds, done_rx=None):
    """Screenshots for up to `seconds`: how long the screen was dark, whether it is light at the end
    and whether done_rx showed up in the OCR text (without done_rx: stop once it is light again)."""
    t0, dark_since, dark_total, seen, light = time.time(), None, 0.0, False, True
    while time.time() - t0 < seconds:
        light = luma(m) > 128
        now = time.time()
        if not light and dark_since is None:
            dark_since = now
        if light and dark_since is not None:
            dark_total += now - dark_since
            dark_since = None
            if done_rx is None:
                break
        if light and done_rx and re.search(done_rx, m.fb_text(m.screendump("_bell_ocr")), re.M):
            seen = True
            break
        time.sleep(0.1)
    if dark_since is not None:
        dark_total += time.time() - dark_since
    return round(dark_total, 1), light, seen


def shell_ready(m, timeout):
    """Until the shell answers `echo READY` (split by quotes in the typed line)."""
    end = time.time() + timeout
    while True:
        m.fb_stable(3, 600, 1)
        m.fb_type("echo RE''ADY\r")
        try:
            m.fb_expect(r"^\W*READY\W*$", 20, 3)
            return
        except Exception:
            if time.time() > end:
                raise


def prom_bell(m, v):
    m.fb_type("7 emit\r")
    dark, light, _ = watch(m, 20)
    m.metrics["prom_dark_s"] = dark
    m.snap(f"firmware prompt: 7 emit, dark for {dark}s")
    if not light:
        raise AssertionError("the screen didn't come back after 7 emit at the firmware prompt")
    if v["LOOP"]:
        m.fb_type("get-msecs d# 100000 0 do dup get-msecs - 0< drop loop get-msecs swap - .d\r")
        time.sleep(5)
        text = m.fb_text(m.screendump("_loop"))
        r = re.findall(r"\.d\s+(\d+)\s+ok", text)
        m.metrics["prom_loop_ms"] = int(r[-1]) if r else None
        m.snap(f"firmware prompt: 100000 counter reads took {m.metrics['prom_loop_ms']} ms")


def hang_evidence(m, v):
    regs, out = registers(m)
    m.metrics["registers"] = regs
    m.log("info registers while hung:\n" + out)
    fw = v["BIOS"] if v["BIOS"].startswith("/") else os.path.join(os.environ.get("LAB_FIRMWARE", "/usr/share/kvm"), v["BIOS"])
    for reg in ("tbr", "psr"):
        out = m.hmp(f"p ${reg}").strip()
        m.metrics[reg] = out
        m.log(f"${reg} = {out}")
    # the packaged firmware is stripped: TICKS_SYM gives obp_ticks from a build of the same sources
    sym = int(v["TICKS_SYM"], 16) if v.get("TICKS_SYM") else elf_symbol(fw, "obp_ticks")
    ptr = read_word(m, sym) if sym is not None else None
    t1 = read_word(m, ptr) if ptr else None
    time.sleep(5)
    t2 = read_word(m, ptr) if ptr else None
    pcs = []
    for _ in range(5):
        pcs.append(registers(m)[0].get("pc"))
        time.sleep(0.5)
    m.metrics["obp_ticks"] = {"symbol": hex(sym or 0), "pointer": hex(ptr or 0), "t0": t1, "t0+5s": t2}
    m.metrics["pc_samples"] = pcs
    m.log(f"obp_ticks at {hex(sym or 0)} -> {hex(ptr or 0)}: {t1}, 5 s later {t2}; PCs {pcs}")


def guest_bell(m, v):
    m.snap("before the BEL")
    m.fb_type(BEL_LINE + "\r")
    dark, light, seen = watch(m, int(v["WAIT"]), r"^\W*AFTER-BEL\W*$")
    m.metrics["guest_dark_s"] = dark
    m.metrics["guest_hung"] = not seen
    m.snap(f"after the BEL: dark {dark}s, {'light' if light else 'dark'}, "
           f"{'the shell answered' if seen else 'no answer'}")
    if not seen:
        hang_evidence(m, v)
    if v["EXPECT"] == "hang":
        if seen or light:
            raise AssertionError("expected the console to hang with the screen inverted")
        return
    if not seen or not light:
        raise AssertionError("the console didn't come back after the BEL")
    m.fb_type(BEL3_LINE + "\r")
    dark, light, seen = watch(m, int(v["WAIT"]), r"^\W*DONE-THREE\W*$")
    m.metrics["guest_dark3_s"] = dark
    m.snap(f"three BELs: dark {dark}s, {'the shell answered' if seen else 'no answer'}")
    if not seen or not light:
        raise AssertionError("the console didn't come back after three BELs")


def guest_tab(m, v):
    """The report's case: bash's completion bell. `exec bash`, `echo /usr/s` and Tab (more than one
    match: bash rings the bell), then Ctrl-U and a line only the shell's output has."""
    m.fb_type(v["TAB"] + "\r")
    shell_ready(m, 60)
    m.snap("bash")
    m.fb_type("echo /usr/s")
    m.fb_key("tab")
    dark, light, _ = watch(m, int(v["WAIT"]) // 2)
    m.fb_key("ctrl", "u")
    m.fb_type("echo AFTER-''TAB\r")
    _, light, seen = watch(m, int(v["WAIT"]) // 2, r"^\W*A\w+-\s*T\w{2}\W*$")  # OCR has read it as "APTER- TAB."
    m.metrics["tab_dark_s"] = dark
    m.metrics["guest_hung"] = not seen
    m.snap(f"after Tab: dark {dark}s, {'light' if light else 'dark'}, "
           f"{'the shell answered' if seen else 'no answer'}")
    if not seen:
        hang_evidence(m, v)
    if v["EXPECT"] == "hang":
        if seen or light:
            raise AssertionError("expected the console to hang with the screen inverted")
    elif not seen or not light:
        raise AssertionError("the console didn't come back after bash's completion bell")


def run(m, v):
    m.fb_expect(BANNER, 300, 2)
    m.fb_stable(2, 60, 1)
    m.snap("firmware prompt")
    prom_bell(m, v)
    if v["GUEST"] == "prom":
        m.stop()
        return
    # disk:a: some installed disks (Solaris 9) don't load from plain `disk` ("No valid state ...")
    if v["GUEST"] == "solaris":
        m.fb_type("boot disk:a -s\r")
        m.fb_expect(r"system maintenance|root password", 900, 5)
        m.fb_stable(2, 60, 1)
        m.fb_type(v["PASSWORD"] + "\r")
        shell_ready(m, 300)
    elif v["GUEST"] == "sunos4":
        m.fb_type("boot disk:a -s\r")
        m.fb_expect(r"SunOS Release", 900, 5)
        shell_ready(m, 600)
    else:  # netbsd
        m.fb_type("boot disk:a\r")
        m.fb_expect(r"login:", 900, 5)
        m.fb_stable(2, 60, 1)
        m.fb_type("root\r")
        m.fb_expect(r"Password:", 120, 3)
        m.fb_type(v["PASSWORD"] + "\r")
        shell_ready(m, 300)
    m.snap("guest shell")
    if v["TAB"]:
        guest_tab(m, v)
    else:
        guest_bell(m, v)
    if v["EXPECT"] == "back":
        m.fb_type("sync; sync\r")
        time.sleep(3)
    m.stop()
