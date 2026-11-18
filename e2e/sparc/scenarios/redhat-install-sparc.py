"""Install Red Hat Linux 6.2 for SPARC on sun4m (SS-5 unless MACHINE says otherwise) from its CD with
kickstart: the answers are on a second CD (_redhat.py, KS_ISO), the scenario types the boot line at
SILO's prompt and answers only what 6.2's kickstart leaves on the screen (SILO's three screens);
the install reboots at the end, and the scenario stops the VM at the firmware's banner.

    lab.py run scenarios/redhat-install-sparc.py --out /mnt/sparc/runs/rh62 \
        --var ISO=/mnt/sparc/iso/other-os/redhat-6.2-sparc.iso --var TEMPLATE=<a Sun-labelled 3 GiB disk>

  IP, NETMASK             the address the kickstart file sets on eth0 (a lab QEMU of its own: the
                          answer CD is written from them unless KS_ISO is given)
  TIMEOUT                 seconds for the install from the boot line to the reboot  (3600)

The disk must have a Sun label (`lab.py install` writes one, sunlabel.py): on a blank disk anaconda
asks whether to initialize it ("Bad Partition Table"), which kickstart's `zerombr yes` doesn't
answer on SPARC. `lab.py install redhat62-ss5` builds the answer CD (answer_media.py) and runs this
against a PVE VM, then redhat-firstboot.py.
"""
import time

import _redhat

DEFAULTS = {**_redhat.DEFAULTS, "IP": "10.0.2.15", "NETMASK": "255.255.255.0", "TIMEOUT": "3600"}

# SILO's screens, which kickstart doesn't skip on SPARC (its `lilo` command skips the step "lilo",
# the SPARC screens are the step "silo"): F12 takes each screen's defaults (no kernel options; SILO
# in the disk's boot block; the PROM boot device and alias boxes as they are)
SILO_SCREENS = [(r"\|\s+Skip\s+\|", "SILO: kernel options"),
                (r"Where do you want to install the bootloader", "SILO: where"),
                (r"Device\s+Partition type\s+Default\s+Boot label", "SILO: boot images")]


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<Red Hat 6.2 SPARC CD>")
    return _redhat.qemu_args(v, out, answers=True)


def run(m, v):
    _redhat.boot_cd(m)
    m.snap("SILO")
    t0 = time.time()
    m.send("linux ks=cdrom:/ks.cfg\r")
    m.expect(r"Linux version 2\.2\.14", 300)
    m.expect(r"Red Hat install init version 6\.2", 300)
    m.snap("installer")
    for pattern, title in SILO_SCREENS:
        m.expect(pattern, 900, screen=True)
        m.quiet(2, 120)
        m.snap(title)
        _redhat.fkey(m, _redhat.F12)
    # the kickstart's `reboot`: anaconda unmounts and the kernel resets the machine to the firmware
    reboot = [r"Welcome to OpenBIOS", r"Resetting|Rebooting|SPARCstation \d+, (No )?Keyboard"]
    i = m.expect_any([r"Package Installation"] + reboot, 900, screen=True) - 1
    if i < 0:
        m.snap("packages")
        i = m.expect_any(reboot, int(v["TIMEOUT"]))
    m.metrics["install_s"] = round(time.time() - t0, 1)
    m.snap("reboot")
    m.log(f"the install rebooted ({'OpenBIOS' if i == 0 else 'firmware'}): stopping the VM")
    m.stop()
