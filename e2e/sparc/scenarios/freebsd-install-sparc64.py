"""Install FreeBSD/sparc64 12.4 from its disc1 CD on the serial console: sun4u, disk and CD-ROM on the
built-in IDE, bsdinstall's console type answered, its welcome screen's Shell, then `bsdinstall script`
with the auto layout on ada0 and the kernel and base sets from the CD (_freebsd.install), then
`halt -p` from the installer's shell (its `shutdown -p now` only says "System shutdown time
has arrived" and leaves the machine on). The disk then boots with freebsd-firstboot.py.

    lab.py run scenarios/freebsd-install-sparc64.py --out /work/fbi \
        --var ISO=/work/iso/FreeBSD-12.4-RELEASE-sparc64-disc1.iso

  HOSTNAME       the host name                                                  (freebsd)
  IP, NETMASK    hme0's address (the first boot writes the network again)       (10.0.2.15, 255.255.255.0)
  DISTRIBUTIONS  the sets from /usr/freebsd-dist                                (kernel.txz base.txz)
  INSTALL_TIMEOUT  seconds for `bsdinstall script` (partitioning, extraction)    (5400)

`lab.py install freebsd124-sun4u` runs it against a PVE VM, then freebsd-firstboot.py.
"""
import _freebsd

DEFAULTS = {**_freebsd.DEFAULTS, "HOSTNAME": "freebsd", "IP": "10.0.2.15", "NETMASK": "255.255.255.0",
            "DISTRIBUTIONS": "", "INSTALL_TIMEOUT": "5400"}


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<FreeBSD sparc64 disc1 CD>")
    return _freebsd.qemu_args(v, out)


def run(m, v):
    m.expect(_freebsd.KERNEL, int(v["TIMEOUT"]))
    m.snap("kernel")
    _freebsd.install(m, v, int(v["INSTALL_TIMEOUT"]))
    _freebsd.check_disk(m)
    _freebsd.shell(m, "sync")
    m.snap("installed")
    try:
        _freebsd.power_off(m, v, "halt -p", wait=120)
    except Exception as e:  # the installer's shell may stop at the firmware instead of powering off
        m.log(f"installer power-off: {e}")
        m.snap("installer halted")
        m.stop()
