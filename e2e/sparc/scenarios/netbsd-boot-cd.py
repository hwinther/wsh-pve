"""Boot a NetBSD install CD (tested: NetBSD-11.1-sparc64.iso) to sysinst on the serial console, leave
it for the shell and run COMMAND. Attach mode only: a PVE VM with `serial0: socket`, `vga: serial0`.

    lab.py run scenarios/netbsd-boot-cd.py --pve 400 --out /work/runs/netbsd64

sparc64 (sun4u, OpenBIOS): with qemu-server's sparc64 profile, the CD on the built-in IDE (`ide2`)
first in the boot order becomes `-boot order=d` and OpenBIOS boots it by itself; `BOOT=` (empty)
requires that and fails at the `0 >` prompt. A qemu-server before the profile gave the devices
`bootindex` paths that OpenBIOS can't boot ("No valid state has been set"); for that, the default
`BOOT=cdrom:f` types `boot cdrom:f` at the prompt.

  BOOT     what to boot at the OpenBIOS prompt; empty: never type  (cdrom:f)
  COMMAND  run in the shell                                        (uname -m)
  EXPECT   regex its output must match                             (the VM's arch)
"""
import re

DEFAULTS = {"BOOT": "cdrom:f", "COMMAND": "uname -m", "EXPECT": ""}


def qemu_args(v, out):
    raise SystemExit("netbsd-boot-cd.py drives a PVE VM: lab.py run ... --pve <vmid>")


def run(m, v):
    if m.expect_any([r"0 > ", r"NetBSD IEEE 1275"], 300) == 0:
        m.snap("OpenBIOS prompt")
        if not v["BOOT"]:
            raise AssertionError("OpenBIOS stopped at its prompt instead of booting the CD by itself")
        m.send(f"boot {v['BOOT']}\r")
    else:
        m.snap("OpenBIOS boots the CD by itself")
    m.expect(r"NetBSD \d+\.\d+ \(", 900)  # the kernel banner
    m.expect(r"Terminal type \(just hit ENTER", 900)
    m.snap("terminal type")
    m.send("vt100\r")
    m.expect(r"Installation messages in English", 300, screen=True)
    m.quiet(2, 60)
    m.snap("sysinst: language")
    m.send("\r")  # a, the highlighted entry
    m.expect(r"x: Exit Install System", 120, screen=True)
    m.quiet(2, 60)
    m.snap("sysinst: main menu")
    m.send("x")
    m.quiet(2, 60)
    m.send("\r")
    m.expect(r"\n# $", 120)
    m.send(f"{v['COMMAND']}\r")
    out = m.expect(rf"^({v['EXPECT'] or re.escape(v.get('ARCH', ''))})\s*$", 60).group(1)
    m.snap(f"{v['COMMAND']}: {out}")
    m.stop()
