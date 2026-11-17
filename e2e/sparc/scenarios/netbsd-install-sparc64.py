"""Install NetBSD/sparc64 from its CD with sysinst on the serial console (sun4u, disk and CD-ROM on the
built-in IDE), root without a password, then power off. The disk then boots with
sparc64-boot-disk.py GUEST=netbsd.

    lab.py run scenarios/netbsd-install-sparc64.py --out /mnt/sparc/runs/nbi \
        --var ISO=/mnt/sparc/iso/other-os/NetBSD-11.1-sparc64.iso

  SETS      sysinst's distribution menu: a = full, b = without X11, c = minimal  (b)
  DISK_GB   size of the blank disk                                             (8)

~8 min for 11.1 without X11 on one host core (sysinst to power-off ~7 min). sysinst draws its menus
with curses: a letter moves the cursor, Return activates; each step waits for the screen it answers
(_netbsd.sysinst). `lab.py install netbsd111-sparc64` runs it against a PVE VM, then
netbsd-firstboot.py.
"""
import _netbsd

DEFAULTS = _netbsd.defaults("sparc64")


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<NetBSD sparc64 CD>")
    return _netbsd.qemu_args(v, out)


def run(m, v):
    m.expect(r"Terminal type", int(v["TIMEOUT"]))
    m.snap("terminal type")
    m.send("vt100\r")
    _netbsd.finish_install(m, v, _netbsd.sysinst(m, v))
