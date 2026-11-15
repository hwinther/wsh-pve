"""Boot an Alpine Linux CD (alpine-standard-*.iso) to its login prompt, log in as root (the live CD
has no password) and run COMMAND. Attach mode only: a PVE VM with the CD attached and `serial0: socket`.

    lab.py run scenarios/alpine-boot-cd.py --pve 200 --out /work/runs/alpine

  CONSOLE  serial: everything on the serial console (aarch64 with `vga: serial0`: AAVMF, GRUB and the
           kernel use the PL011 when there is no display); fb: the screen (x86_64, whose boot loader
           and kernel use the VGA console), read by OCR and typed on through send-key, and COMMAND's
           output is also written to /dev/ttyS0, where it must arrive on the serial socket
           (from the VM's config: serial without a display, else fb)
  COMMAND  run after login                                          (uname -m)
  EXPECT   regex its output must match                              (the VM's arch)
"""
import re

DEFAULTS = {"CONSOLE": "serial", "COMMAND": "uname -m", "EXPECT": "", "TIMEOUT": "900"}


def qemu_args(v, out):
    raise SystemExit("alpine-boot-cd.py drives a PVE VM: lab.py run ... --pve <vmid>")


def run(m, v):
    expect = v["EXPECT"] or re.escape(v.get("ARCH", ""))
    timeout = int(v["TIMEOUT"])
    if v["CONSOLE"] == "serial":
        m.expect(r"Welcome to Alpine Linux", timeout)
        m.expect(r"login: $", 120)
        m.snap("login prompt")
        m.send("root\r")
        m.expect(r":~# $", 60)
        m.send(f"{v['COMMAND']}\r")
        out = m.expect(rf"^({expect})\s*$", 60).group(1)
    else:
        m.fb_expect(r"login:", timeout, interval=10)
        m.snap("login prompt")
        m.fb_type("root\r")
        m.fb_expect(r"localhost ?:\S{0,3}# ?_?\s*$", 60)  # OCR reads "localhost:~#" as "localhost :“# _"
        # the serial port too: the same output through /dev/ttyS0 must reach the serial socket (after
        # a newline: the getty there has left "localhost login: " on the line)
        m.fb_type(f"{v['COMMAND']}; (echo; {v['COMMAND']}) > /dev/ttyS0\r")
        out = m.expect(rf"^({expect})\s*$", 60).group(1)
        m.fb_expect(expect, 30)
    m.snap(f"{v['COMMAND']}: {out}")
    m.stop()
