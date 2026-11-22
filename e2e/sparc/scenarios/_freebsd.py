"""What the FreeBSD install, first-boot and boot scenarios share: FreeBSD/sparc64 12.4 (the last release
with the port) on sun4u, OpenBIOS, disk and CD-ROM on the built-in IDE (CMD646: `ada0`, `cd0`), sunhme
(`hme0`), serial console (`ttyu0`). Attached to a PVE VM (`--pve`, `lab.py install freebsd124-sun4u`)
the VM is what PVE built from the target's profile.

The install CD (disc1) boots to bsdinstall, which asks for the console type on ttya and then shows
dialog(1) screens. install() leaves the dialogs at once: it takes the welcome screen's Shell button
and runs `bsdinstall script` there with a script it types (installerconfig(): the auto layout on ada0,
the distribution sets from the CD's /usr/freebsd-dist), the installer's own unattended mechanism, so
no dialog screen is driven by its layout. Root has no password after it; the first boot sets one at
passwd's prompts, which don't echo (freebsd-firstboot.py), as for NetBSD.

root's shell is csh with the prompt `root@<host>:~ #` (`root@:~ #` before a host name is set); the
installer's shell is sh with `# `.
"""
import re
import time

import _netbsd
import _sparc64

DEFAULTS = {**_sparc64.DEFAULTS, "NIC_NAME": "", "DISK_NAME": "", "TIMEOUT": "900"}
PROMPT = r"^[^\n]*# ?$"  # root's prompt (csh `root@host:~ #`, the installer's sh `#`)
CONSOLE_TYPE = r"Console type \[[\w-]+\]: ?$"
KERNEL = r"FreeBSD [\d.]+-RELEASE[^\n]* (?:GENERIC|r\d+)"  # the kernel's banner
# The ata(4) driver gave up on a command, or the kernel stopped an interrupt source as a storm
# (FreeBSD bug 239068 on QEMU 2.12-3.0: `interrupt storm detected on "vec2016:"`, the cmd646)
DISK_TROUBLE = r"interrupt storm detected|(?:ada|cd)\d+: .*(?:timeout|TIMEOUT)|ata\d+: (?:timeout|TIMEOUT)"


def qemu_args(v, out):
    return _sparc64.qemu_args(v, out)


def nic(v):
    return v.get("NIC_NAME") or "hme0"


def disk(v):
    return v.get("DISK_NAME") or "ada0"


def shell(m, command, timeout=300):
    """Run a command at the prompt and return its output (up to the marker line). csh and sh alike."""
    m.send(f"{command}; echo END-OF-COMMAND")
    m.send("\r")
    return m.expect(r"^((?:.*\n)*?)END-OF-COMMAND\s*$", timeout).group(1)  # at a line start: not the echo


def login(m, password="", timeout=900):
    """Wait for `login:` on the console and log in as root (no Password prompt while root has none)."""
    m.expect(r"login: ?$", timeout)
    m.snap("login prompt")
    m.send("root\r")
    i = m.expect_any([r"Password: ?$", PROMPT], 120)
    if i == 0:
        m.send(password + "\r")
        m.expect(PROMPT, 120)
    shell(m, "true")  # past the login messages


def passwd(m, user, password):
    """`passwd user` at its prompts (no echo): FreeBSD's asks twice. Through sh, whatever root's shell
    (csh): the echoed command line must not itself match PASSWD-RC=<digits>."""
    m.send(f"sh -c 'passwd {user}; echo PASSWD-RC=$?'\r")
    for _ in range(4):
        r = m.expect(r"(?P<prompt>[Pp]assword: ?$)|PASSWD-RC=(?P<rc>\d+)", 120)
        if r.group("rc") is not None:
            break
        time.sleep(1)
        m.send(password + "\r")
    else:
        raise AssertionError(f"passwd {user} kept asking")
    if r.group("rc") != "0":
        raise AssertionError(f"passwd {user} failed (exit {r.group('rc')})")
    shell(m, "true")


def installerconfig(v):
    """The lines of bsdinstall's script: the preamble (the disk, the sets, where they are) and the setup
    script, which runs in the new system: the host name and a static address on the NIC (the first
    boot writes the network again), dumpdev off, sendmail off (it waits on DNS at every boot)."""
    dists = v.get("DISTRIBUTIONS") or "kernel.txz base.txz"
    lines = [f"PARTITIONS={disk(v)}", f'DISTRIBUTIONS="{dists}"', "BSDINSTALL_DISTDIR=/usr/freebsd-dist",
             "nonInteractive=YES", "#!/bin/sh",
             f"sysrc hostname={v['HOSTNAME']}",
             f'sysrc ifconfig_{nic(v)}="inet {v["IP"]} netmask {v["NETMASK"]}"',
             "sysrc dumpdev=NO", 'sysrc sendmail_enable=NONE', "sysrc sshd_enable=YES"]
    if any("'" in line for line in lines):
        raise ValueError("no single quotes in the installer script")
    return lines


def install(m, v, timeout):
    """From bsdinstall's console-type question to an installed disk: vt100, the welcome screen's Shell
    button, the script typed into /tmp/installerconfig, `bsdinstall script`, its exit code checked.
    Leaves the installer's shell at its prompt."""
    m.expect(CONSOLE_TYPE, int(v["TIMEOUT"]))
    m.quiet(2, 60)
    m.snap("console type")
    m.send("vt100\r")
    # the welcome dialog: "Would you like to begin an installation or use the live CD?" (wrapped)
    m.expect(r"<Install>.*<Live CD>", 300, screen=True)
    m.quiet(2, 60)
    m.snap("welcome")
    # Install | Shell | Live CD: the button's hot key. Not the arrow keys: dialog reads vt100's cursor
    # keys as ESC O C, and ESC [ C's ESC cancels the dialog, which is the Live CD
    m.send("s")
    if m.expect_any([r"type 'exit' to return to the installer", r"login: ?$"], 120) == 1:
        raise AssertionError("the welcome screen took the Live CD, not the Shell")
    m.expect(PROMPT, 60)
    shell(m, "true")
    m.snap("installer shell")
    shell(m, "rm -f /tmp/installerconfig")
    for line in installerconfig(v):
        shell(m, f"echo '{line}' >> /tmp/installerconfig")
    shell(m, "cat /tmp/installerconfig; ls -l /usr/freebsd-dist")
    m.snap("installer script")
    t0 = time.time()
    m.send("bsdinstall script /tmp/installerconfig; echo BSDINSTALL-RC=$?\r")
    if m.expect_any([r"BSDINSTALL-RC=(\d+)", DISK_TROUBLE], timeout) == 1:
        m.snap("disk trouble")
        raise AssertionError("disk trouble on the console during the install")
    rc = re.search(r"BSDINSTALL-RC=(\d+)", m.text[-200:])
    m.metrics["install_s"] = round(time.time() - t0, 1)
    m.quiet(2, 60)
    m.snap("bsdinstall script done")
    if not rc or rc.group(1) != "0":
        shell(m, "tail -40 /tmp/bsdinstall_log")
        raise AssertionError(f"bsdinstall script failed ({rc.group(1) if rc else '?'}); see /tmp/bsdinstall_log above")
    shell(m, "tail -5 /tmp/bsdinstall_log; gpart show; mount | grep /mnt || true")


HALT_WAIT = 300


def power_off(m, v=None, command="shutdown -p now", wait=HALT_WAIT):
    """`shutdown -p now` (or `command`) and wait for the VM to end (OpenBIOS powers sun4u off)."""
    t0 = time.time()
    m.send(command + "\r")
    wait_off(m, wait)
    m.metrics["poweroff_s"] = round(time.time() - t0, 1)


def wait_off(m, timeout=600):
    _netbsd.wait_off(m, timeout)


def check_disk(m):
    """Fail on disk trouble anywhere on the console so far (DISK_TROUBLE)."""
    found = re.findall(rf".*(?:{DISK_TROUBLE}).*", m.text)
    m.metrics["disk_trouble"] = len(found)
    if found:
        raise AssertionError(f"disk trouble on the console: {found[:3]}")
