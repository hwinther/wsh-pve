"""Install Debian 13 (debian-ports sparc64, sid) on sun4u from the netinst CD with a preseed file: the
answers are on a second CD (_debian13.py, ANSWERS_ISO), the scenario types the kernel options at the
netinst's GRUB command line (_debian13.boot_options) and nothing else; debian-installer fetches the
base system from deb.debian.org/debian-ports, installs GRUB on the disk and reboots, and the scenario
stops the VM at the firmware's banner.

    lab.py run scenarios/debian13-install-sparc64.py --out /mnt/runs/deb13 --var NET=user \
        --var ISO=/mnt/os/iso/other-os/debian-13.0.0-sparc64-NETINST-1-2026-06-11.iso \
        --var GATEWAY=10.0.2.2 --var DNS=10.0.2.3

  IP, NETMASK, GATEWAY, DNS, DOMAIN, HOSTNAME, APT_PROXY
                          the network the preseed file sets on the NIC (a lab QEMU of its own: the
                          answer CD is written from them unless ANSWERS_ISO is given; NET=user: QEMU's
                          10.0.2.2 router and 10.0.2.3 name server reach the mirror)
  TIMEOUT                 seconds for the install from GRUB to the reboot  (10800)

`lab.py install debian13-sun4u` builds the answer CD (answer_media.py) and runs this against a PVE VM,
then debian13-firstboot.py.
"""
import time

import _debian13

DEFAULTS = {**_debian13.DEFAULTS, "BOOT": "d", "IP": "10.0.2.15", "NETMASK": "255.255.255.0", "GATEWAY": "",
            "DNS": "", "DOMAIN": "", "HOSTNAME": "", "APT_PROXY": "", "TIMEOUT": "10800"}

# A question box on the screen (newt: `[!] Title` or `[!!] Title`) means the preseed file didn't answer
# it, or a step failed: the scenario snaps it and fails there instead of waiting for the timeout
QUESTION = r"\[!!?\] [A-Z]"


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<Debian 13 sparc64 netinst CD>")
    return _debian13.qemu_args(v, out, answers=True)


def run(m, v):
    _debian13.grub_boot_cd(m, _debian13.boot_options())
    t0 = time.time()
    # `quiet`: the kernel prints nothing; the installer's init starts its syslog first
    m.expect(r"Starting system log daemon", 600)
    m.snap("installer started")
    # finish-install's last step (after the file systems are unmounted), then the machine resets
    # (OpenBIOS 0030); a question or an error box fails the run
    if m.expect_any([r"Rebooting into your new system|Requesting system reboot|reboot: Restarting system",
                     QUESTION], int(v["TIMEOUT"]), screen=True) == 1:
        m.quiet(3, 60)
        m.snap("question")
        raise AssertionError("debian-installer stopped at a question or an error (the last snapshot)")
    m.snap("rebooting")
    m.expect(r"Welcome to OpenBIOS|OpenBIOS for Sparc64", 600)
    m.metrics["install_s"] = round(time.time() - t0, 1)
    m.snap("reboot")
    m.log("the install rebooted (OpenBIOS): stopping the VM")
    m.stop()
