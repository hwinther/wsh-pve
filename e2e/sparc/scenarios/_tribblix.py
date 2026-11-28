"""What the Tribblix scenarios share (tribblix-install-sparc64.py, tribblix-firstboot.py,
tribblix-boot-disk.py): the console prompts and the login of Tribblix m34 SPARC on sun4u.

The live CD and a freshly installed disk have the same accounts: `root` with the password `tribblix`
and `jack`/`jack` (tribblix.org, "Installing Tribblix on SPARC"); the installer copies the live /etc.
The install target's first boot gives root the lab password.
"""
import re
import time

from _sparc64 import shell

BANNER = r"Welcome to Tribblix"
LOGIN = r"console login: ?$"
KEYBOARD = r"To select the keyboard layout, enter a number \[default \d+\]: ?"
LIVE_ROOT_PASSWORD = "tribblix"
# What stops a boot for good: a kernel panic, the firmware's prompt, or OpenBIOS stopping
FAIL = (r"panic\[cpu|Unhandled Exception|Can't open boot device|No valid state has been set|"
        r"Fast Data Access MMU Miss|BOOT: Failed|Boot load failed|^0 > ?$")


def login(m, password, timeout):
    """Wait for `console login:` (the boot fails on FAIL first) and log in as root. The live CD asks
    for the keyboard layout on the way (KEYBOARD): Return takes the default, US-English."""
    end = time.time() + timeout
    while True:
        i = m.expect_any([LOGIN, FAIL, KEYBOARD], max(1, end - time.time()))
        if i == 1:
            m.snap("failure")
            raise AssertionError("the boot failed before the login prompt")
        if i == 0:
            break
        m.snap("keyboard layout question")
        m.send("\r")
    m.quiet(3, 120)
    m.snap("login prompt")
    m.send("root\r")
    m.expect(r"[Pp]assword: ?$", 120)
    m.send(password + "\r")
    if m.expect_any([r"[#$] ?$", r"Login incorrect"], 300) == 1:
        raise AssertionError("root's login was refused")
    time.sleep(2)
    # root's shell is bash, whose bracketed paste mode puts ESC [?2004l in front of each command's
    # output: shell() wants its marker at the start of a line
    m.send("bind 'set enable-bracketed-paste off'\r")
    m.expect(r"[#$] ?$", 120)
    shell(m, "true")  # past the login messages


# illumos ZFS joins adjacent I/Os into one of up to zfs_vdev_aggregation_limit (1 MB), but dad, the
# driver of the sun4u IDE disk, refuses any buf over 128 KB (MAX_ATA_XFER_SIZE in dad.c; the
# aggregate fails without a message or an error count, and ZFS turns that into EIO), so ZFS retries
# the parts one at a time and FMA counts every failed first attempt: thousands of ereports, the disk
# DEGRADED (submodules/SPARC.md, "Tribblix on sun4u"). Aggregates of at most 128 KB fit.
AGGREGATION_LIMIT = 131072


def limit_zfs_aggregation(m):
    """Keep ZFS's aggregated I/Os within dad's 128 KB, now (mdb) and from the next boot on
    (/etc/system, which live_install.sh copies from the live CD to the installed system)."""
    shell(m, "modinfo | grep -w zfs >/dev/null || modload /kernel/fs/sparcv9/zfs; grep -q"
             " zfs_vdev_aggregation_limit /etc/system || echo 'set zfs:zfs_vdev_aggregation_limit"
             f" = {AGGREGATION_LIMIT:#x}' >> /etc/system", 300)
    out, _ = shell(m, f"echo 'zfs_vdev_aggregation_limit/W 0t{AGGREGATION_LIMIT}' | mdb -kw >/dev/null;"
                      " echo zfs_vdev_aggregation_limit/D | mdb -k; grep zfs_vdev /etc/system", 300)
    if not re.search(rf"zfs_vdev_aggregation_limit:\s+{AGGREGATION_LIMIT}\b", out):
        raise AssertionError(f"zfs_vdev_aggregation_limit wasn't set to {AGGREGATION_LIMIT}:\n{out}")


def power_off(m):
    """`init 5` (OpenBIOS powers sun4u off when the guest asks it to); returns the host seconds until
    QEMU ended."""
    t0 = time.time()
    m.send("sync; init 5\r")
    try:
        code = m.wait_exit(1800)  # services time out on the way down under TCG: 3.5-12.5 min seen
    except Exception:
        # one UFS first boot printed nothing for 30 minutes after "70 system services are now being
        # stopped" (submodules/SPARC.md, "Tribblix on sun4u"): keep the CPU's state for next time
        try:
            m.log("info registers:\n" + m.hmp("info registers"))
        except Exception as e:
            m.log(f"info registers failed: {type(e).__name__}: {e}")
        raise
    if code != 0:
        raise AssertionError(f"QEMU exited with {code} after init 5")
    return time.time() - t0
