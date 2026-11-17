"""Install Solaris 10 1/13 on sun4u from its DVD with the text installer on ttya (disk and DVD on the
built-in IDE, sunhme with DHCP), until the installer reports success and tries to reboot. The disk then
boots with sparc64-boot-disk.py GUEST=solaris10 (the first boot asks for the keyboard layout: F2).

    lab.py run scenarios/solaris10-install-sparc64.py --out /mnt/sparc/runs/sol10i \
        --var ISO=/mnt/sparc/iso/sol-10-u11-ga-sparc-dvd.iso

  DHCP       yes: hme0 by DHCP (the lab's user network has a DHCP server); no: a static address
             (HOSTNAME, IP, NETMASK; no default route: `lab.py install`'s first boot writes
             /etc/defaultrouter)                                         (yes)
  HOSTNAME   host name (asked only without DHCP)                        (sol10)
  IP         the static address with DHCP=no                            (10.0.2.15)
  NETMASK    its netmask with DHCP=no                                   (255.255.255.0)
  ROOT_PASSWORD  root password (`lab.py install` sets it; masked in result.json)  (ROOTPW)
  ROOTPW     root password when ROOT_PASSWORD is empty                  (lab12345)
  DISK_GB    size of the blank disk; the default software group needs ~5.3 GB  (16)
  MEM        MiB                                                        (1024)

Through Proxmox VE (`lab.py install sol10-sun4u`, attach mode) the hardware comes from the VM's config
and the scenario stops the VM itself at the end: the installer's reboot doesn't come back (OpenBIOS has
no client-interface reboot), so `install` ejects the DVD, boots the disk and runs
solaris10-firstboot.py.

Needs pve-qemu-kvm with openbios-sparc64 from openbios/ (patches 0003-0011) and the cmd646 fix
(wsh/0021). About 80 min on one host core: ~13 min to the first installer screens, ~60 min of package
copying. The installer is driven by screen title (curses, terminal type DEC VT100): Esc-2 is F2, Ctrl-N/
Ctrl-P move, Return marks [X]; every other screen keeps its default. Keys typed while a screen is still
being drawn are lost, so each screen first settles.
"""
import re
import time

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args

DEFAULTS = {**BASE, "MEM": "1024", "NET": "user", "DISK_GB": "16", "HOSTNAME": "sol10", "DHCP": "yes",
            "IP": "10.0.2.15", "NETMASK": "255.255.255.0", "ROOT_PASSWORD": "", "ROOTPW": "lab12345",
            "TIMEOUT": "1200", "INSTALL_TIMEOUT": "10800", "MAX_SCREENS": "80"}

EARLY_PANIC = "before the installer"  # in the status of a panic before anything is written to the disk
TITLE = r"^\S? ?(\S.+?) (?:─{4}|q{4})"  # a screen's title line: "─ Time Zone ────"


def qemu_args(v, out):
    if not v["ISO"]:
        raise SystemExit("set ISO=<Solaris 10 1/13 SPARC DVD>")
    return sparc64_args(v, out)


def move(m, direction, n):
    for _ in range(int(n)):
        m.key("ctrl-n" if direction == "down" else "ctrl-p")


def root_password(m, v):
    pw = v["ROOT_PASSWORD"] or v["ROOTPW"]
    m.send(pw)
    m.key("tab")
    m.send(pw)
    m.key("tab")


def name_service_none(m, v):
    # NIS+, NIS, DNS, LDAP, None: mark None, the last entry
    if not re.search(r"\[X\] None", m.screen_text()):
        move(m, "down", 8)
        m.send(" ")


def select(m, label):
    """Mark the choice that starts with `label` in a one-of list ("[X] Yes" / "[ ] No"): the cursor
    starts on the marked entry, Ctrl-N/Ctrl-P move, Return marks."""
    options = re.findall(r"^\W*\[([ X])\] +(\S.*?)\s*$", m.screen_text(), re.M)
    names = [name for _, name in options]
    want = next((i for i, name in enumerate(names) if name.startswith(label)), None)
    if want is None:
        raise AssertionError(f"no choice {label!r} on the screen ({names})")
    marked = next((i for i, (x, _) in enumerate(options) if x == "X"), 0)
    if want != marked:
        move(m, "down" if want > marked else "up", abs(want - marked))
        m.send("\r")


def dhcp(m, v):
    select(m, "Yes" if v["DHCP"].lower() == "yes" else "No")


def field(m, value, old=""):
    """Type `value` into the screen's text field; `old`: what it holds already, erased first."""
    for _ in range(len(old)):
        m.key("backspace")
    m.send(value)


def netmask(m, v):
    # the field comes filled in with the class's netmask: "Netmask for hme0 255.255.255.0"
    shown = re.search(r"^\s*Netmask for \w+ +(\S+)\s*$", m.screen_text(), re.M)
    old = shown.group(1) if shown else ""
    if old != v["NETMASK"]:
        field(m, v["NETMASK"], old)


def confirm_network(m, v):
    """With a static address: the values the installer took (a field that wasn't empty shows here)."""
    screen = m.screen_text()
    if v["DHCP"].lower() != "yes":
        for value in (v["HOSTNAME"], v["IP"], v["NETMASK"]):
            if not re.search(rf":\s*{re.escape(value)}\s*$", screen, re.M):
                raise AssertionError(f"{value} isn't on the confirmation screen:\n{screen}")


def media_dvd(m, v):
    if not re.search(r"\[X\]  CD/DVD", m.screen_text()):
        move(m, "up", 1)
        m.send("\r")


def first_disk(m, v):
    if not re.search(r"\[X\] +c\d", m.screen_text()):
        m.send("\r")


# Screen title (regex on the title) -> what to do before F2; checked in this order
SCREENS = [
    (r"^Root Password$", root_password),
    (r"^Name Service$", name_service_none),
    (r"^DHCP for", dhcp),
    (r"^Choose Media$", media_dvd),
    (r"^Select Disks$", first_disk),
    (r"^Host Name", lambda m, v: field(m, v["HOSTNAME"])),
    (r"^IP Address", lambda m, v: field(m, v["IP"])),
    (r"^Subnet for", lambda m, v: select(m, "Yes")),
    (r"^Netmask", netmask),
    (r"^IPv6 for", lambda m, v: select(m, "No")),
    # the first boot writes /etc/defaultrouter (lab.py install), so no route from the installer
    (r"Default Route", lambda m, v: select(m, "None")),
    (r"^Confirm Information for (hme|eri|bge)\d", confirm_network),
]


def next_screen(m, old, timeout=1200):
    """Wait until the terminal shows an installer screen other than `old` (or the copy progress)."""
    end = time.time() + timeout
    while True:
        try:
            m.quiet(3, 60)
        except Exception:  # the copy progress never goes quiet
            pass
        screen = m.screen_text()
        if "MBytes Installed" in screen:
            return screen
        if screen != old and re.search(TITLE, screen, re.M):
            return screen
        if time.time() > end:
            raise RuntimeError(f"no new installer screen after:\n{old}")
        time.sleep(2)


def run(m, v):
    t0 = time.time()
    m.expect(r"SunOS Release 5\.10", int(v["TIMEOUT"]))
    m.snap("kernel banner")
    if m.expect_any([r"Please make a choice \(0 - 10\)", r"panic\[cpu"], int(v["TIMEOUT"])) == 1:
        # seen once in 6 DVD boots through PVE: BAD TRAP type 0x4e in the firmware's code during
        # prom_finddevice from vfs_mountroot. Nothing is written to the disk yet (EARLY_PANIC: what
        # `lab.py install` retries on)
        m.quiet(5, 300)
        m.snap("panic")
        raise AssertionError(f"{EARLY_PANIC}: kernel panic while booting the DVD")
    m.snap("language")
    m.send("0\r")
    m.expect(r"What type of terminal are you using", 600)
    m.snap("terminal type")
    m.send("3\r")  # DEC VT100

    screen, seen = None, {}
    for _ in range(int(v["MAX_SCREENS"])):
        screen = next_screen(m, screen)
        if "MBytes Installed" in screen:
            break
        title = re.search(TITLE, screen, re.M).group(1).strip()
        seen[title] = seen.get(title, 0) + 1
        m.snap(title)
        if seen[title] > 3:
            raise AssertionError(f"the installer stays on {title!r}")
        time.sleep(3)
        for rx, action in SCREENS:
            if re.search(rx, title):
                action(m, v)
                break
        else:
            # a list with nothing marked (the help text itself says "mark it [X]."): mark the first entry
            if re.search(r"\[ \] \w", screen) and not re.search(r"\[X\] \w", screen):
                time.sleep(1)
                m.send("\r")
                m.quiet(2, 60)
        time.sleep(1)
        m.key("f2")
    m.metrics["questions_s"] = round(time.time() - t0, 1)
    m.snap("installing")

    i = m.expect_any([r"Solaris 10 software installation succeeded", r"panic\[cpu"], int(v["INSTALL_TIMEOUT"]))
    if i == 1:
        m.quiet(5, 300)
        m.snap("panic")
        raise AssertionError("kernel panic during the install")
    m.snap("installation succeeded")
    # boot blocks, boot archive, sync; Auto Reboot is the default: the firmware comes back, or (without
    # a client-interface reboot in the firmware) Solaris says the reboot call returned
    i = m.expect_any([r"OpenBIOS for Sparc64", r"reboot call returned"], 3600)
    m.metrics["install_s"] = round(time.time() - t0, 1)
    m.metrics["rebooted"] = i == 0
    m.snap("reboot")
    m.stop()
