"""Boot a DOS disk that dos_profiles.py prepared (a profile's CONFIG.SYS and AUTOEXEC.BAT, our test
programs, MEASURE.BAT and maybe RUN.BAT in C:\\WSHPROF) and watch it: nothing is typed except a
startup menu choice and "press a key" prompts. AUTOEXEC.BAT ends in MEASURE.BAT, which writes MEM and
our programs' results to C:\\WSHPROF\\OUT and echoes WSHPROF DONE; the runner reads the files after
QEMU stopped. With GAME_SECS, RUN.BAT starts a game after WSHPROF GAME; the scenario presses KEYS
("t:key,t:key", seconds after the game started) and samples the screen once a second: distinct
frames, the last change, still running or back at the prompt.

Vars: DISK (C:), GAMES (D:, snapshot=on), SOUND (combo: SB16 + AdLib + PC speaker into audio.wav;
none), CDROM (1: an empty IDE CD-ROM drive for a CD driver to find), MENU (the entry to pick at the
startup menu) and MENU_PROMPT (its regex), BOOT_TIMEOUT (240), GAME_SECS, KEYS, VGA (std or
std,retrace=precise), and _dos.qemu_args' MEM, CPU, ACCEL, QEMU.

Metrics: boot_s (to WSHPROF DONE), boot_log (the text lines seen), screen_lit (the share of non-black
pixels in the last screendump), and game_* with a game.
"""
import hashlib
import os
import re
import time

import _dos
import lab

DEFAULTS = {"SOUND": "combo", "CDROM": "1", "MENU": "", "MENU_PROMPT": r"Enter a choice:", "BOOT_TIMEOUT": "240",
            "GAME_SECS": "0", "KEYS": "", "GAMES": ""}


def qemu_args(v, out):
    a = _dos.qemu_args({**v, "BOOT": "c", "DISK2": ""}, out)
    if v["GAMES"]:
        a += ["-drive", f"if=ide,index=1,format=raw,snapshot=on,file={v['GAMES']}"]
    if v["CDROM"] == "1":
        a += ["-drive", "if=ide,index=2,media=cdrom"]
    if v["SOUND"] == "combo":
        a += ["-audiodev", f"wav,id=snd,path={out}/audio.wav", "-device", "sb16,audiodev=snd",
              "-device", "adlib,audiodev=snd", "-machine", "pcspk-audiodev=snd"]
    return a + ["-d", "guest_errors,unimp", "-D", f"{out}/qemu-d.log"]


def lit(m, name):
    """The share of pixels that aren't black in a screendump."""
    from PIL import Image

    png = m.screendump(name)
    with Image.open(png) as im:
        px = im.convert("L").getdata()
        return round(sum(1 for x in px if x > 16) / max(1, len(px)), 4)


def boot(m, v):
    """To WSHPROF DONE at a prompt (or WSHPROF GAME with a game); the boot's text lines."""
    log, seen = [], set()
    end = time.time() + int(v["BOOT_TIMEOUT"])
    menu_done, paused = not v["MENU"], 0
    want = "WSHPROF GAME" if float(v["GAME_SECS"] or 0) else "WSHPROF DONE"
    while time.time() < end:
        s = m.vga_screen()
        if s.text_mode:
            for x in s.lines:
                x = x.rstrip()
                if x and x not in seen:
                    seen.add(x)
                    log.append(x)
            cur = s.cursor_line()
            if not menu_done and re.search(v["MENU_PROMPT"], s.text):
                m.vga_snap("startup menu")
                _dos.key(m, v["MENU"], "ret")
                menu_done = True
            elif re.search(r"press a(ny)? key", cur, re.I) and paused < 3:
                time.sleep(0.5)
                _dos.key(m, "spc")
                paused += 1
            elif want in s.text and (want == "WSHPROF GAME" or re.search(_dos.PROMPT, cur, re.M)):
                m.metrics["boot_s"] = round(m.elapsed(), 1)
                m.metrics["boot_log"] = log
                return True
        # a game that clears the screen or leaves text mode at once: its marker may never be read, but
        # the measurements' screen is gone
        if want == "WSHPROF GAME" and "WSHPROF MEASURE" in seen and (
                "WSHPROF GAME" in seen or not s.text_mode or "WSHPROF MEASURE" not in s.text):
            m.metrics["boot_s"] = round(m.elapsed(), 1)
            m.metrics["boot_log"] = log
            return True
        m._check_alive()
        time.sleep(0.25)
    m.metrics["boot_log"] = log
    return False


def game(m, v):
    t0 = time.time()
    keys = sorted((float(t), k) for t, k in (x.split(":", 1) for x in v["KEYS"].split(",") if x))
    secs = float(v["GAME_SECS"])
    hashes, changes, n, last, result = [], [], 0, None, "still running"
    snap_at = [5, 20, 40]
    while time.time() - t0 < secs:
        el = time.time() - t0
        while keys and keys[0][0] <= el:
            _dos.key(m, keys.pop(0)[1])
        png = m.screendump(f"g{n:03d}")
        with open(png, "rb") as fh:
            h = hashlib.sha1(fh.read()).hexdigest()[:10]
        os.unlink(png)
        if last is not None and h != last:
            changes.append(round(el, 1))
        last = h
        hashes.append(h)
        n += 1
        s = m.vga_screen()
        m.metrics["game_mode"] = s.mode
        if snap_at and el >= snap_at[0]:
            snap_at.pop(0)
            m.vga_snap(f"game t={el:.0f}s") if s.text_mode else m.snap(f"game t={el:.0f}s", term=False)
        if el > 3 and s.text_mode and re.search(_dos.PROMPT, s.cursor_line(), re.M):
            time.sleep(1)
            s = m.vga_screen()
            if s.text_mode and re.search(_dos.PROMPT, s.cursor_line(), re.M):
                result = "back at the prompt"
                m.metrics["game_exit_screen"] = s.text
                break
        time.sleep(1.0)
    m.metrics.update({"game_result": result, "game_distinct_frames": len(set(hashes)),
                      "game_last_change_s": changes[-1] if changes else 0})


def run(m, v):
    try:
        if not boot(m, v):
            m.vga_snap("no WSHPROF marker")
            raise lab.Timeout(f"no WSHPROF marker within {v['BOOT_TIMEOUT']}s")
        if float(v["GAME_SECS"] or 0):
            game(m, v)
        else:
            time.sleep(1)
        s = m.vga_screen()
        m.vga_snap("done") if s.text_mode else m.snap("done", term=False)
    finally:
        try:
            m.metrics["screen_lit"] = lit(m, "last")
        except Exception:  # QEMU gone: the result says why
            pass
