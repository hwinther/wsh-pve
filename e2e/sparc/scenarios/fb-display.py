"""A framebuffer (VGA=cg3 or tcx, RES=WxH[xDEPTH]) from the firmware banner to the Solaris desktop: the
banner on the framebuffer, an installed Solaris to its login prompt with the console on the
framebuffer and, with X=1, dtlogin, a root login and the CDE desktop, its depth (xdpyinfo), the
keyboard, QEMU's host CPU use with X idle, a drawing benchmark and a soak. Every screenshot is
checked for RES's size and for not being blank. The Sun PROMs get `boot disk` typed at `ok`.

    lab.py run scenarios/fb-display.py --out /mnt/runs/tcx --var VGA=tcx --var RES=1024x768x24 \
        --var DISK=/mnt/runs/tcx/disk.raw [--var X=1 --var BENCH=3]

cg3-display.py is the cg3 size check; this one compares the two framebuffers like for like.

  X           1: log in at dtlogin and check the desktop (needs the ttya shell, see PREPARE)  (none)
  PREPARE     1: first run solaris-tcx-packages.py on DISK (TCX packages, a login on ttya; needs
              ISO), in <out>/prepare, on the same machine with the console on ttya  (none)
  PKGS        passed to solaris-tcx-packages.py; PKGS= (empty) adds only the ttya login, for a
              disk without the TCX packages                                          (its default)
  SHELL       1: log in on ttya (the login PREPARE adds) for the checks; on with X     (none)
  EXPECT      what Solaris should do with the framebuffer: x = the X server starts (dtlogin),
              console = it doesn't (the kernel has no driver, or X refuses it): the scenario
              checks the reason in DRIVER_EXPECT / XERR_EXPECT                       (x)
  DEPTH       the root window depth xdpyinfo must report with X=1                     (none)
  IDLE        seconds to measure QEMU's host CPU use over with the desktop idle      (0)
  BENCH       rounds of the drawing benchmark (xb.sh: text, scroll, fill, windows)   (0)
  ACCEL       1: one more benchmark round with QEMU's MMIO writes traced, counted per region
              (memory_region_ops_write: the TCX blitter/stippler vs. the rest)        (none)
  SOAK        seconds of drawing (benchmark rounds) before a last check that X still answers (0)
  INPUT       1: a dtterm under the pointer, the pointer moved through the monitor (screenshots,
              reported only), a click, a command typed on the Sun keyboard that must run  (none)
  SETTLE      seconds to wait on the desktop before measuring                        (30)
Metrics (result.json): dtlogin_s (QEMU start to dtlogin), desktop_s (user name Return to dtwm and
a still screen), depth, idle_cpu_pct, per test bench_<test>_s (median) and _cpu (QEMU % of a core),
accel_<region> counts, soak_rounds, pointer_boxes, keyboard.
"""
import os
import re
import statistics
import subprocess
import sys
import time

from _sparc32 import DEFAULTS as BASE, qemu_args as sparc32_args

DEFAULTS = {**BASE, "CONSOLE": "fb", "RES": "1024x768", "BOOT": "c", "NO_CD": "1", "X": "", "PREPARE": "",
            "SHELL": "", "EXPECT": "x", "DRIVER_EXPECT": "", "XERR_EXPECT": "", "DEPTH": "", "IDLE": "0",
            "BENCH": "0", "ACCEL": "", "SOAK": "0", "INPUT": "", "SETTLE": "30"}

BANNER = r"Welcome to Open|for detailed information|SPARCstation|ROM Rev"  # OCR reads OpenBIOS as "OpenBros"

# The drawing benchmark, written into the guest line by line (the tty takes 256 characters a line).
# text: an xterm without jump scroll cats 1500 lines (glyphs + one scroll per line: CopyArea);
# scroll: the same with jump scroll (xterm's default: fewer, larger scrolls);
# fill: xsetroot repaints the root window 20 times (solid fills);
# windows: 10 xterms mapped and destroyed.
XB = [
    "DISPLAY=:0; HOME=/; export DISPLAY HOME; X=/usr/openwin/bin",
    "[ -f /tmp/b.txt ] || ls -lR /usr/openwin | head -1500 > /tmp/b.txt",
    "n=0",
    "case $1 in",
    "text) $X/xterm +j -geometry 80x40+40+40 -e cat /tmp/b.txt ;;",
    "scroll) $X/xterm -j -geometry 80x40+60+60 -e cat /tmp/b.txt ;;",
    "fill) while [ $n -lt 10 ]; do $X/xsetroot -solid red; $X/xsetroot -solid blue; n=`expr $n + 1`; done ;;",
    "windows) while [ $n -lt 10 ]; do $X/xterm -geometry 80x24+$n+$n -e true; n=`expr $n + 1`; done ;;",
    "esac",
]
TESTS = ("text", "scroll", "fill", "windows")


def qemu_args(v, out):
    v["GUEST"] = "1" if v["DISK"] else ""  # sparc32_args fills DISK with a blank disk
    if v["PREPARE"] and v["DISK"]:
        lab = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lab.py")
        keep = ("QEMU", "BIOS", "MACHINE", "MEM", "CPU", "ISO")
        cmd = [sys.executable, lab, "run", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "solaris-tcx-packages.py"),
               "--out", os.path.join(out, "prepare"), "--var", f"DISK={v['DISK']}", "--var", "TTYA_LOGIN=1"]
        cmd += [x for k in keep if v.get(k) for x in ("--var", f"{k}={v[k]}")]
        if "PKGS" in v:  # PKGS= (empty) leaves the TCX packages out
            cmd += ["--var", f"PKGS={v['PKGS']}"]
        if subprocess.run(cmd).returncode:
            raise SystemExit(f"PREPARE failed, see {os.path.join(out, 'prepare')}")
    return sparc32_args(v, out)


def check(m, title, v):
    w, h = (int(x) for x in v["RES"].split("x")[:2])
    step = m.snap(title)
    m.fb_check(step["fb_png"], (w, h))
    return step


def sh(m, command, timeout=300):
    """A command on the ttya shell; returns (output, host seconds from Return to its end)."""
    m.send(f"{command}; echo END-OF-COMMAND")
    t0 = time.time()
    m.send("\r")
    out = m.expect(r"^((?:.*\n)*?)END-OF-COMMAND\s*$", timeout).group(1)
    return out.split("\n", 1)[1] if "\n" in out else "", time.time() - t0  # without the echoed command


def shell_login(m):
    m.send("\r")
    m.expect(r"ttya login:", 120)
    m.send("root\r")
    m.expect(r"#\s*$", 120)
    sh(m, "PS1='# '; export PS1")


def boot_to_login(m, v):
    """Firmware banner, then Solaris to console login or dtlogin (first-boot questions answered).
    Returns 0 for the console prompt, 1 for dtlogin, None without a guest (banner only)."""
    m.fb_expect(BANNER, 300)
    check(m, "firmware banner", v)
    if not v["GUEST"]:
        return None
    if not v["BIOS"].startswith("openbios"):
        # The Sun PROMs find their NVRAM invalid ("Incorrect configuration checksum") and set the
        # defaults with diag-switch? true: they try the network and stop at ok. `boot disk` from
        # there resets the SS-20 PROM, which forgets the command ("Rebooting with command:" and
        # the network again); with diag-switch? false the reset boots boot-device, the disk.
        # Typed slowly, Return only once the line reads right (the SS-20 PROM drops keys).
        for line in ("setenv diag-switch? false", "boot disk"):
            m.fb_expect_any([r"^\s*ok\b"], 300, tail=2)
            m.fb_stable(3, 120, 1)
            m.fb_type(line, hold=100, delay=0.3)
            m.fb_expect(r"ok\s+" + re.escape(line), 20, 2)
            m.snap(f"PROM: {line}")
            m.fb_type("\r")
        m.fb_expect(r"SunOS Release|Hostname:", 300)
    while True:
        i = m.fb_expect_any([r"console login:", r"Please enter your user name", r"password:",
                             r"Press Return to continue"], 1800, tail=8)
        if i < 2:
            break
        m.snap(["", "", "root password", "press return"][i])
        m.fb_type("\r")
        time.sleep(5)
    return i


def wait_dtlogin(m, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        out, _ = sh(m, "ps -e | egrep 'Xsun|dtgreet'")
        if "dtgreet" in out:
            return True
        time.sleep(5)
    return False


def x_login(m, v):
    """Log in as root (no password) at dtlogin and wait for the CDE desktop: dtwm running and the
    screen still for 10 s. Returns the host seconds from the user name's Return. root without a
    password goes straight on; the first login of a user asks which desktop to use (CDE is the
    default: Return)."""
    m.fb_expect(r"Please enter your user name", 300)
    m.fb_type("root\r")
    t0 = time.time()
    end = t0 + 900
    asked = set()
    while time.time() < end:
        out, _ = sh(m, "ps -e | grep dtwm")
        if "dtwm" in out:
            break
        text = m.fb_text(m.screendump("_fb_poll"))
        for key, rx in (("password", r"enter your password"), ("desktop", r"Which one would you like")):
            if key not in asked and re.search(rx, text, re.I):
                asked.add(key)
                m.snap(f"dtlogin asks for the {key}")
                m.fb_type("\r")
        time.sleep(2)
    else:
        raise AssertionError("no dtwm within 900 s of the login")
    m.fb_stable(10, 600, 1)
    return time.time() - t0 - 10


def write_xb(m):
    sh(m, "rm -f /tmp/xb.sh")
    for line in XB:
        sh(m, "echo '" + line.replace("'", "'\\''") + "' >> /tmp/xb.sh")
    sh(m, "sh /tmp/xb.sh none", 600)  # creates /tmp/b.txt


def bench_round(m, results):
    for t in TESTS:
        c0 = m.cpu_seconds()
        _, s = sh(m, f"sh /tmp/xb.sh {t}", 1800)
        results.setdefault(t, []).append(s)
        results.setdefault(t + "_cpu", []).append(100 * (m.cpu_seconds() - c0) / s)
        m.log(f"bench {t}: {s:.1f}s")


def accel(m, v):
    """One traced round: count QEMU's MMIO writes per memory region (RAM writes, i.e. the plain
    framebuffer planes, aren't MMIO and don't show)."""
    log = os.path.join(m.out, "accel-trace.log")
    m.hmp(f"logfile {log}")
    m.hmp("trace-event memory_region_ops_write on")
    bench_round(m, {})
    m.hmp("trace-event memory_region_ops_write off")
    m.hmp("logfile /dev/null")
    counts = {}
    with open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            r = re.search(r"name '([^']*)'", line)
            if r:
                counts[r.group(1)] = counts.get(r.group(1), 0) + 1
    os.unlink(log)  # can be large
    with open(os.path.join(m.out, "accel-counts.txt"), "w", encoding="utf-8") as f:
        for k, n in sorted(counts.items(), key=lambda x: -x[1]):
            f.write(f"{n:10d} {k}\n")
    for k, n in counts.items():
        if k.startswith(("tcx.", "cg3")):
            m.metrics[f"accel_{k}"] = n
    m.log("MMIO writes in one round: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items(), key=lambda x: -x[1])[:12]))


def find_cursor(before, after):
    """The bounding box of what changed between two screenshots (the pointer moved)."""
    from PIL import Image, ImageChops

    a, b = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
    return ImageChops.difference(a, b).getbbox()


def input_check(m, v):
    """Keyboard and mouse under X: a dtterm under the pointer (where X put it, the screen centre),
    the pointer moved in steps through the monitor (mouse_move; the Sun mouse is relative), each
    screenshot showing where the cursor is drawn, a click, then a command typed on the Sun keyboard
    into the dtterm; the guest must have run it. The pointer is only reported (pointer_boxes: what
    changed on the screen after each move; the CDE clock changes too)."""
    sh(m, "rm -f /tmp/kbd; (DISPLAY=:0 /usr/dt/bin/dtterm -geometry 60x10+300+300 &)")
    time.sleep(20)
    m.fb_stable(5, 300, 1)
    prev = m.snap("dtterm under the pointer")["fb_png"]
    boxes = []
    for i in range(4):
        m.hmp("mouse_move 40 -30")
        time.sleep(3)
        cur = m.snap(f"pointer moved by {40 * (i + 1)},{-30 * (i + 1)}")["fb_png"]
        boxes.append(find_cursor(prev, cur))
        prev = cur
    m.log(f"changed regions after each move: {boxes}")
    m.metrics["pointer_boxes"] = [list(b) if b else None for b in boxes]
    m.hmp("mouse_button 1")
    time.sleep(0.3)
    m.hmp("mouse_button 0")
    time.sleep(2)
    m.fb_type("echo typed-on-the-sun-keyboard > /tmp/kbd\r")
    time.sleep(5)
    m.snap("typed into the dtterm")
    out, _ = sh(m, "cat /tmp/kbd")
    if "typed-on-the-sun-keyboard" not in out:
        raise AssertionError(f"the dtterm didn't get the keys: /tmp/kbd has {out!r}")
    m.metrics["keyboard"] = "ok"


def run(m, v):
    want_x = v["EXPECT"] == "x"
    i = boot_to_login(m, v)
    if i is None:
        m.stop()
        return
    check(m, ["console login", "dtlogin"][i], v)
    if v["X"] or v["SHELL"] or not want_x:
        shell_login(m)
        out, _ = sh(m, "ls -l /dev/fb; modinfo | egrep 'tcx|cgthree'; grep 'console framebuffer' /var/adm/messages")
        m.snap("framebuffer in the guest")
        if v["DRIVER_EXPECT"] and not re.search(v["DRIVER_EXPECT"], out):
            raise AssertionError(f"no {v['DRIVER_EXPECT']!r} in:\n{out}")
        up = wait_dtlogin(m, 300 if want_x else 120)
        m.metrics["dtlogin_s"] = round(m.elapsed(), 1)
        if not want_x:
            err, _ = sh(m, "tail -8 /var/dt/Xerrors")
            m.snap("X server refused")
            if up:
                raise AssertionError("dtlogin came up, expected it not to")
            if v["XERR_EXPECT"] and not re.search(v["XERR_EXPECT"], err):
                raise AssertionError(f"no {v['XERR_EXPECT']!r} in /var/dt/Xerrors:\n{err}")
            m.stop()
            return
        if not up:
            err, _ = sh(m, "tail -8 /var/dt/Xerrors")
            raise AssertionError(f"dtlogin didn't come up; /var/dt/Xerrors:\n{err}")
    if not v["X"]:
        time.sleep(int(v["SETTLE"]))
        check(m, f"{v['SETTLE']}s after the login prompt", v)
        m.stop()
        return
    check(m, "dtlogin", v)
    m.metrics["desktop_s"] = round(x_login(m, v), 1)
    check(m, "desktop", v)
    out, _ = sh(m, "DISPLAY=:0 HOME=/ /usr/openwin/bin/xdpyinfo | egrep 'dimensions|depth of root|default visual'")
    r = re.search(r"depth of root window:\s+(\d+)", out)
    m.metrics["depth"] = int(r.group(1)) if r else None
    if v["DEPTH"] and m.metrics["depth"] != int(v["DEPTH"]):
        raise AssertionError(f"root window depth {m.metrics['depth']}, expected {v['DEPTH']}:\n{out}")
    if v["INPUT"]:
        input_check(m, v)
    if int(v["IDLE"]):
        time.sleep(int(v["SETTLE"]))
        m.metrics["idle_cpu_pct"] = round(m.cpu_use(int(v["IDLE"])), 1)
    if int(v["BENCH"]) or v["ACCEL"] or int(v["SOAK"]):
        write_xb(m)
    if int(v["BENCH"]):
        results = {}
        for n in range(int(v["BENCH"])):
            bench_round(m, results)
        for k, xs in results.items():
            m.metrics[f"bench_{k}" + ("" if k.endswith("_cpu") else "_s")] = round(statistics.median(xs), 1)
            m.metrics[f"bench_{k}_all"] = [round(x, 1) for x in xs]
        check(m, "after the benchmark", v)
    if v["ACCEL"]:
        accel(m, v)
    if int(v["SOAK"]):
        end, rounds = time.time() + int(v["SOAK"]), 0
        while time.time() < end:
            bench_round(m, {})
            rounds += 1
        m.metrics["soak_rounds"] = rounds
        out, _ = sh(m, "DISPLAY=:0 HOME=/ /usr/openwin/bin/xdpyinfo | grep 'depth of root'; ps -e | grep -c Xsun")
        check(m, f"after a {v['SOAK']}s soak", v)
        if "depth of root" not in out:
            raise AssertionError(f"X doesn't answer after the soak:\n{out}")
    sh(m, "sync; sync")
    m.stop()
