"""What the NetBSD install, first-boot and boot scenarios share, on sparc64 (sun4u, _sparc64.py) and
sparc (sun4m, _sparc32.py): ARCH picks the machine for a QEMU of the lab's own; attached to a PVE VM
(`--pve`, `lab.py install`) the VM is what PVE built from the target's profile.

  ARCH      sparc64 | sparc                                       (sparc64)
  NIC_NAME  the guest's interface: hme0 (sunhme, sparc64), le0 (lance, sparc)  (by ARCH)

sysinst() answers sysinst on the serial console (vt100) from its first menu to "Exit Install System"
(then a shell on sparc64; sparc's microroot halts and powers off by itself, finish_install()); root
is left without a password (netbsd-firstboot.py sets it).
"""
import time

import _sparc32
import _sparc64
from lab import QemuDied

DEFAULTS = {"ARCH": "sparc64", "NIC_NAME": "", "SETS": "b", "TIMEOUT": "900"}
NICS = {"sparc64": "hme0", "sparc": "le0"}
PROMPT = r"^[^\n]*# ?$"  # root's shell prompt (the bare `#` or `<host>#`)


def defaults(arch):
    """The scenario's DEFAULTS for ARCH: the machine's variables, then these."""
    base = _sparc64.DEFAULTS if arch == "sparc64" else {**_sparc32.DEFAULTS, "VGA": "none"}
    return {**base, **DEFAULTS, "ARCH": arch}


def qemu_args(v, out):
    if v["ARCH"] == "sparc64":
        return _sparc64.qemu_args(v, out)
    return _sparc32.qemu_args(v, out)


def nic(v):
    return v.get("NIC_NAME") or NICS[v["ARCH"]]


def choose(m, screen, letter, title, timeout=300):
    """Wait for `screen` (regex) on the terminal, then pick `letter` (empty: the current item)."""
    m.expect(screen, timeout, screen=True)
    m.quiet(2, 120)
    m.snap(title)
    if letter:
        m.send(letter)
        time.sleep(1)
    m.send("\r")
    time.sleep(2)


def sysinst(m, v):
    """sysinst from its language menu: the first disk with the default partition sizes, the sets
    v["SETS"] (a = full, b = without X11, c = minimal) from the CD-ROM, root without a password,
    the configuration menu's defaults; ends at the shell after "Exit Install System"."""
    choose(m, r"Installation messages in English", "a", "language")
    choose(m, r"Install NetBSD to hard disk", "a", "main menu")
    choose(m, r"Shall we continue", "b", "continue")
    choose(m, r"Available disks", "a", "disk")
    choose(m, r"Use default partition sizes", "b", "partitioning")
    choose(m, r"Partition sizes ok", "x", "partition sizes")
    choose(m, r"ready to install NetBSD", "b", "last chance")
    choose(m, r"Select your distribution", v["SETS"], "distribution")
    choose(m, r"Install from", "a", "install from CD-ROM")
    # optional sets missing from the CD, then the extraction, then "complete": Return each time
    while True:
        i = m.expect_any([r"Hit enter to continue", r"New password:"], 3600)
        if i == 1:
            break
        m.quiet(2, 120)
        m.send("\r")
        time.sleep(2)
    m.snap("root password")
    m.send("\r")  # none
    choose(m, r"Not now, continue", "x", "entropy")
    # the configuration menu (time zone, root shell, sshd, ...): keep the defaults
    if m.expect_any([r"Finished configuring", r"installation of NetBSD-[\d.]+ is now complete"], 600,
                    screen=True) == 0:
        choose(m, r"Finished configuring", "x", "configuration")
    choose(m, r"installation of NetBSD-[\d.]+ is now complete", "", "complete", 600)
    choose(m, r"Exit Install System", "x", "exit")
    # sparc64's CD drops to a shell; sparc's microroot halts and powers off by itself
    return m.expect_any([r"#\s*$", r"Back in microroot; halting machine"], 120) == 0


def finish_install(m, v, at_shell):
    """After sysinst(): power off from the shell, or wait for the microroot's own power-off."""
    if at_shell:
        power_off(m)
        return
    m.snap("microroot halts")
    wait_off(m)


def boot_disk(m, v):
    """Get the installed disk booting: sun4u's OpenBIOS boots it by itself (`-boot c`, or PVE's boot
    order); on sun4m stock OpenBIOS may stop at `0 >`, where _sparc32.prom_boot() types the path."""
    if v["ARCH"] == "sparc":
        _sparc32.prom_boot(m, v, "disk")


def shell(m, command, timeout=300):
    """Run a command at root's prompt and return its output (up to the marker line)."""
    m.send(f"{command}; echo END-OF-COMMAND")
    m.send("\r")
    return m.expect(r"^((?:.*\n)*?)END-OF-COMMAND\s*$", timeout).group(1)  # at a line start: not the echo


def login(m, password="", timeout=900):
    """Wait for the console's `login:` and log in as root (`password`, none by default)."""
    m.expect(r"login: ?$", timeout)
    m.snap("login prompt")
    m.send("root\r")
    if password:
        m.expect(r"Password: ?$", 60)
        m.send(password + "\r")
    m.expect(PROMPT, 120)
    shell(m, "true")  # past the login messages


def passwd(m, user, password):
    """Set `user`'s password with passwd(1) at its prompts, which don't echo. NetBSD's passwd asks
    again once after a short or all-lower-case password, then takes it; every prompt gets the same
    answer until passwd ends."""
    m.send(f"passwd {user}; echo PASSWD-RC=$?\r")
    for _ in range(8):
        r = m.expect(r"(?P<prompt>[Pp]assword: ?$)|PASSWD-RC=(?P<rc>\d+)", 120)
        if r.group("rc") is not None:
            break
        time.sleep(0.5)
        m.send(password + "\r")
    else:
        raise AssertionError(f"passwd {user} kept asking")
    if r.group("rc") != "0":
        raise AssertionError(f"passwd {user} failed (exit {r.group('rc')})")
    shell(m, "true")


def power_off(m):
    """`sync; halt -p` and wait for the VM to end (OpenBIOS powers sun4u and sun4m off)."""
    m.send("sync; halt -p\r")
    wait_off(m)


def wait_off(m, timeout=600):
    """Wait for the VM to power itself off (QEMU exits with 0)."""
    try:
        code = m.wait_exit(timeout)
    except QemuDied:
        code = m.proc.returncode  # it was gone before wait_exit() looked
    if code != 0:
        raise AssertionError(f"QEMU exited with {code} at power-off")
