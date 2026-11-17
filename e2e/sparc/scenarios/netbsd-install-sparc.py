"""Install NetBSD/sparc from its CD on sun4m (SS-5 unless MACHINE says otherwise; disk on SCSI target 3,
CD-ROM on target 6, as qemu-server builds a sparc32 VM) with sysinst on the serial console, root
without a password, then power off.

    lab.py run scenarios/netbsd-install-sparc.py --out /mnt/sparc/runs/nb32 \
        --var ISO=/mnt/sparc/iso/other-os/NetBSD-11.1-sparc.iso

  SETS      sysinst's distribution menu: a = full, b = without X11, c = minimal  (c)

The CD's kernel boots a microroot that loads the installation tools from the CD first: medium
`1` (cdrom), the CD-ROM device and the path of instfs.tgz (the defaults), the terminal type (vt100,
the default), `I` for sysinst; then the same sysinst answers as on sparc64 (_netbsd.sysinst). With
a blank disk on target 3, OpenBIOS stops at `0 >` and _sparc32.prom_boot() boots the CD by path.
`lab.py install netbsd111-sparc` runs it against a PVE VM, then netbsd-firstboot.py.
"""
import _netbsd
from _sparc32 import prom_boot

DEFAULTS = {**_netbsd.defaults("sparc"), "SETS": "c"}


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<NetBSD sparc CD>")
    return _netbsd.qemu_args(v, out)


def run(m, v):
    prom_boot(m, v, "cdrom")
    m.expect(r"Installation medium to load the additional utilities from:", int(v["TIMEOUT"]))
    m.snap("microroot")
    m.send("1\r")  # cdrom
    m.expect(r"CD-ROM device to use \[[^]]*\]:", 120)
    m.send("\r")
    m.expect(r"Path to instfs\.tgz \[[^]]*\]", 120)
    m.send("\r")
    m.expect(r"Terminal type\? \[[^]]*\]", 900)
    m.send("vt100\r")
    m.expect(r"\(I\)nstall/Upgrade, \(H\)alt or \(S\)hell\?", 300)
    m.snap("install, halt or shell")
    m.send("I\r")
    _netbsd.finish_install(m, v, _netbsd.sysinst(m, v))
