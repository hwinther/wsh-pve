"""Install Debian GNU/Linux 4.0 "etch" for SPARC on sun4m (SS-5 unless MACHINE says otherwise) from the
netinst CD with a preseed file: the answers are on a second CD (_debian.py, ANSWERS_ISO), the scenario
types the boot line at SILO's prompt (_debian.boot_line) and nothing else; debian-installer fetches
the base system from archive.debian.org, installs SILO on the disk and reboots, and the scenario
stops the VM at the firmware's banner.

    lab.py run scenarios/debian-install-sparc.py --out /mnt/sparc/runs/deb40 --var NET=user \
        --var ISO=/mnt/sparc/iso/other-os/debian-40r9-sparc-netinst.iso --var GATEWAY=10.0.2.2 --var DNS=10.0.2.3

  IP, NETMASK, GATEWAY, DNS, DOMAIN, HOSTNAME
                          the network the preseed file sets on eth0 (a lab QEMU of its own: the answer
                          CD is written from them unless ANSWERS_ISO is given; NET=user: QEMU's
                          10.0.2.2 router and 10.0.2.3 name server reach the archive)
  TIMEOUT                 seconds for the install from the boot line to the reboot  (5400)

`lab.py install debian40-ss5` builds the answer CD (answer_media.py) and runs this against a PVE VM,
then debian-firstboot.py.

With ARCH=sparc64 it installs Debian GNU/Linux 7 "wheezy" on sun4u the same way, from CD 1 with nothing
fetched (answer_media.preseed_wheezy, _debian.boot_line64; README.md, "Debian GNU/Linux 7 on sun4u");
`lab.py install debian7-sun4u` runs it:

    lab.py run scenarios/debian-install-sparc.py --out <runs>/deb7 --var ARCH=sparc64 \
        --var ISO=<iso>/other-os/debian-7.11.0-sparc-CD-1.iso --var HOSTNAME=debian7-sun4u
"""
import time

import _debian

DEFAULTS = {**_debian.DEFAULTS, "IP": "10.0.2.15", "NETMASK": "255.255.255.0", "GATEWAY": "", "DNS": "",
            "DOMAIN": "", "HOSTNAME": "", "TIMEOUT": "5400"}

# A question box on the screen (newt: `[!] Title` or `[!!] Title`) means the preseed file didn't answer
# it: the scenario snaps it and fails there instead of waiting for the timeout
QUESTION = r"\[!!?\] [A-Z]"


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<Debian 4.0 sparc netinst CD>")
    return _debian.qemu_args(v, out, answers=True)


def run(m, v):
    _debian.boot_cd(m, v)
    m.snap("SILO")
    t0 = time.time()
    m.send((_debian.boot_line64() if _debian.sparc64(v) else _debian.boot_line()) + "\r")
    m.expect(r"Linux version 3\.2" if _debian.sparc64(v) else r"Linux version 2\.6\.18", 300)
    m.expect(r"Kernel command line: .*early_command", 60)
    # finish-install's last step (after the file systems are unmounted), then the machine resets
    if m.expect_any([r"Rebooting into your new system", QUESTION], int(v["TIMEOUT"]), screen=True) == 1:
        m.quiet(3, 60)
        m.snap("question")
        raise AssertionError("debian-installer asked a question the preseed file doesn't answer (the last snapshot)")
    m.snap("rebooting")
    if _debian.sparc64(v):
        # the kernel's last line before it asks the firmware to reset: the install is complete. The
        # firmware's RAM clear after that reset took 5-6 minutes without pve-qemu wsh/0112 (TB flush
        # on reset), so the VM is stopped here rather than at the banner
        m.expect(r"Restarting system", 300)
        m.metrics["install_s"] = round(time.time() - t0, 1)
        m.snap("reset")
        m.log("the install asked the firmware to reset: stopping the VM")
        m.stop()
        return
    i = m.expect_any([r"Welcome to OpenBIOS", r"SPARCstation \d+, (No )?Keyboard"], 300)
    m.metrics["install_s"] = round(time.time() - t0, 1)
    m.snap("reboot")
    m.log(f"the install rebooted ({'OpenBIOS' if i == 0 else 'firmware'}): stopping the VM")
    m.stop()
