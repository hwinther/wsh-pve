"""Install OpenBSD/sparc64 from its install CD (bsd.rd) on the serial console: sun4u, disk and CD-ROM on
the built-in IDE, hme0 with a static address, root's password, the auto layout on wd0, the sets from
the CD without X11, then halt (ntpd stays on, as the installer sets it: _openbsd.py). The disk then
boots with openbsd-firstboot.py.

    lab.py run scenarios/openbsd-install-sparc64.py --out /mnt/runs/obi \
        --var ISO=/mnt/os/iso/other-os/openbsd8.0/install80.iso --var ROOT_PASSWORD=wshlab

  HOSTNAME       the host name                                                  (openbsd)
  IP, NETMASK    hme0's address (the first boot can change it)                  (10.0.2.15, 255.255.255.0)
  ROOT_PASSWORD  root's password, typed at the installer's prompts (no echo)     (required)
  SETS           the set selections, in order, before `done` (space separated)  (-x*: all but X11)
  TIMEZONE       the installer's time zone                                       (UTC)
  INSTALL_TIMEOUT  seconds for the whole dialogue, set extraction included        (3600)
  NTPD           off: `ntpd_flags=NO` in the new system's /etc/rc.conf.local     (on)

`lab.py install openbsd80-sun4u` runs it against a PVE VM, then openbsd-firstboot.py. 8.0's installer
on one host core: the questions take a minute or two, the sets (base, comp, man, game) and the kernel
relink most of the rest (submodules/SPARC.md, "sparc64").
"""
import _openbsd

DEFAULTS = {**_openbsd.DEFAULTS, "HOSTNAME": "openbsd", "IP": "10.0.2.15", "NETMASK": "255.255.255.0",
            "ROOT_PASSWORD": "", "SETS": "-x*", "TIMEZONE": "UTC", "INSTALL_TIMEOUT": "3600", "NTPD": ""}


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<OpenBSD sparc64 install CD>")
    return _openbsd.qemu_args(v, out)


def run(m, v):
    if not v["ROOT_PASSWORD"]:
        raise SystemExit("set ROOT_PASSWORD (the installer needs one)")
    m.expect(r"OpenBSD [\d.]+ \(RAMDISK", int(v["TIMEOUT"]))
    m.snap("bsd.rd kernel")
    asked = _openbsd.installer(m, v, int(v["INSTALL_TIMEOUT"]))
    m.metrics["questions"] = len(asked)
    m.expect(_openbsd.PROMPT, 120)
    m.snap("installer shell")
    # the new system is under /mnt while the installer's shell runs; mount its root if it isn't
    _openbsd.shell(m, f"mount | grep -q ' on /mnt ' || mount /dev/{v.get('DISK_NAME') or 'wd0'}a /mnt; mount")
    if not _openbsd.ntpd_on(v):
        _openbsd.disable_ntpd(m, "/mnt")
        m.snap("ntpd off")
    _openbsd.halt_installer(m)
