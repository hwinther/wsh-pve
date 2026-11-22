"""What the Debian 13 (debian-ports sparc64, sid) install, first-boot and boot scenarios share, on sun4u
(_sparc64.py: disk on the built-in IDE's primary master, the netinst on the secondary master, sunhme;
the console on ttya, which Linux calls ttyS0). README.md, "Debian 13 on sun4u".

  ANSWERS_ISO  the answer CD (a lab QEMU of its own): an ISO 9660 image with preseed.cfg and wshlab on
               the IDE secondary slave (qemu-server's ide3), which Linux calls sr1 (the netinst on the
               secondary master is sr0). Default: <out>/preseed.iso, written from
               answer_media.preseed_ports() with IP, NETMASK, GATEWAY, DNS, DOMAIN and HOSTNAME.
               Attached to a PVE VM, the VM has it already (`lab.py install` puts it on ide3)
"""
import os
import time

import _redhat
import _sparc64
from lab import QemuDied

DEFAULTS = {**_sparc64.DEFAULTS, "MEM": "1024", "BOOT": "c", "ANSWERS_ISO": ""}
ANSWERS_DRIVE = "ide3"  # IDE secondary slave: Linux's sr1, after the netinst's sr0
ANSWERS_DEV = "/dev/sr1"
PROMPT = r":~# ?$"  # root's bash prompt in its home, `root@<host>:~# `
GRUB_MENU = r"Press enter to boot the selected OS"
KERNEL = r"Linux version \d+\.\d+"

# A Linux root shell on ttyS0 behaves as Red Hat's does
shell = _redhat.shell
check_output = _redhat.check_output


def qemu_args(v, out, answers=False):
    """The lab's own QEMU: _sparc64's machine, with `answers` the answer CD on the IDE secondary slave
    (ANSWERS_ISO, or one written from the network variables)."""
    args = _sparc64.qemu_args(v, out)
    if answers:
        import answer_media
        iso = v["ANSWERS_ISO"]
        if not iso:
            iso = os.path.join(out, "preseed.iso")
            with open(iso, "wb") as f:
                f.write(answer_media.image("preseed-ports", v["IP"], v["NETMASK"], v["GATEWAY"] or None,
                                           v["DNS"].split(), v["DOMAIN"] or None, v["HOSTNAME"] or None,
                                           v.get("APT_PROXY") or None))
        args += ["-drive", f"file={iso},if=none,id=drive-ide3,format=raw,readonly=on,media=cdrom",
                 "-device", "ide-cd,bus=ide.1,unit=1,drive=drive-ide3,id=ide3"]
    return args


def boot_options(dev=ANSWERS_DEV):
    """The kernel options the install scenario types on GRUB's `linux` line for the netinst's kernel:
    priority critical in English with a US keymap, and preseed/early_command, which debian-installer
    runs at start-up (S33preseed_early_command, after env2debconf has read the kernel's environment
    into its database) before any question: load the IDE and CD drivers itself (hw-detect hasn't run
    yet), mount the answer CD read-only and run `wshlab` from it (answer_media.PRESEED_PORTS_LOADER).
    The mount is retried until the drive is there. GRUB's script quoting takes the double quotes, and
    GRUB hands the kernel the word with its spaces in quotes, which the kernel strips again."""
    return ('priority=critical locale=en_US.UTF-8 keymap=us preseed/early_command="modprobe pata_cmd64x;'
            f'modprobe sr_mod;modprobe isofs;until mount -r -t iso9660 {dev} /mnt;do sleep 1;done;sh /mnt/wshlab"')


def grub_boot_cd(m, options, timeout=600):
    """The netinst's GRUB (2.14, from the CD's boot block): its menu has no timeout. `c` gives the
    command line, where the scenario types what the menu's `boot_one` does, with `options` on the
    `linux` line itself. Not through the menu's `$options`: GRUB splits an unquoted variable at the
    spaces and escapes the double quotes it then finds in a word (`\\"`), so early_command reached
    debian-installer with its quotes and failed (exit code 2)."""
    m.expect(GRUB_MENU, timeout)
    m.snap("GRUB menu")
    m.send("c")
    m.expect(r"grub> $", 60)
    m.send(f"linux /install/vmlinux {options} --- quiet\r")
    m.expect(r"grub> $", 300)
    m.send("initrd /install/initrd.gz\r")
    m.expect(r"grub> $", 300)  # the kernel and initrd are read from the CD
    m.snap("GRUB: kernel and initrd loaded")
    m.send("boot\r")


def boot_disk(m, timeout=900):
    """The installed disk to the kernel: OpenBIOS boots GRUB's boot block from the disk (`boot-device`
    disk), GRUB shows its menu for 5 s and boots the first entry; Return takes it at once. The kernel
    runs with `quiet` (no banner): GRUB's own "Loading Linux" line is the sign it took the entry."""
    m.expect(r"GNU GRUB", timeout)
    m.expect(r"automatically in|Press enter to boot", 120)
    m.snap("GRUB")
    m.send("\r")
    m.expect(r"Loading Linux \d", 300)
    m.expect(r"Loading initial ramdisk", 600)
    m.snap("kernel and initrd loaded")


def login(m, password="", timeout=900):
    """Wait for `login:` on ttyS0 (systemd's serial-getty on the console) and log in as root
    (`password`, none by default)."""
    m.expect(r"login: ?$", timeout)
    m.snap("login prompt")
    time.sleep(1)
    m.send("root\r")
    if password:
        m.expect(r"Password: ?$", 60)
        time.sleep(1.5)  # login prints the prompt before it turns echo off
        m.send(password + "\r")
    m.expect(PROMPT, 180)
    time.sleep(0.5)
    shell(m, "true")  # past the login messages


def passwd(m, user, password):
    """Set `user`'s password with chpasswd: trixie's passwd(1) asks twice and checks the password's
    strength through PAM, chpasswd as root just sets it. The password goes through a here-document
    that the shell doesn't echo back, so it is in no cast or screenshot."""
    m.send("stty -echo\r")
    time.sleep(0.5)
    m.send(f"chpasswd <<'WSH-EOF'\r{user}:{password}\rWSH-EOF\r")
    time.sleep(0.5)
    m.send("stty echo\r")
    out = shell(m, f"passwd -S {user}")
    if f"{user} P " not in out:
        raise AssertionError(f"{user}'s password wasn't set: {out!r}")


def power_off(m, timeout=600):
    """`poweroff` and wait for QEMU to end (OpenBIOS powers sun4u off when Linux asks it to)."""
    m.send("poweroff\r")
    try:
        code = m.wait_exit(timeout)
    except QemuDied:
        code = m.proc.returncode
    if code != 0:
        raise AssertionError(f"QEMU exited with {code} at power-off")
