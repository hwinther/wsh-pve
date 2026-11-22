"""The sparc64 machine (sun4u, OpenBIOS) the sparc64 scenarios share, with the disk, CD-ROM and NIC on a
choice of buses so the layouts can be compared (submodules/SPARC.md, "sparc64").

The default is the layout that works for every guest tested: disk and CD-ROM on the machine's built-in
IDE controller (CMD646: disk = primary master, CD-ROM = secondary master), sunhme on pciB, serial
console. `LAYOUT=pve` is what qemu-server 9.2 builds for a VM from the create wizard today (LSI 53C895A
on pciB with the disk on target 0 and the CD-ROM on target 2, sunhme on pciB, virtio-balloon, -vga std,
bootindex on every device and `-boot menu=on,...`).

Variables (lab.py run ... --var KEY=VALUE):
  QEMU      qemu-system-sparc64 binary                        (qemu-system-sparc64)
  BIOS      firmware                                          (openbios-sparc64)
  MACHINE   sun4u | sun4v | niagara, with options             (sun4u)
  MEM       MiB                                               (512)
  SMP       CPUs, -smp only when > 1                          (1)
  CPU       -cpu model, e.g. TI-UltraSparc-II                 (none: the machine's default, UltraSparc IIi)
  VGA       std | none                                        (none)
  CONSOLE   serial | fb: where OpenBIOS puts its console      (serial)
            serial = ttya (-prom-env input-device=ttya output-device=ttya, needed when there is a VGA)
  ISO       the install CD                                    (none)
  DISK      the guest disk; created from TEMPLATE when it doesn't exist  (<out>/disk.raw)
  TEMPLATE  a disk image to start from (.raw or .raw.xz)      (none: a blank disk of DISK_GB)
  DISK_GB   size of a blank disk in GiB                       (8)
  DISK_BUS  ide | lsi | virtio-scsi | virtio-blk | none        (ide)
  CD_BUS    ide | lsi | virtio-scsi | virtio-blk (a read-only disk) | none  (ide)
  NIC       sunhme | virtio-net-pci | e1000 | ne2k_pci | ... | none  (sunhme), on pciB
  MAC       the NIC's MAC address (-device ...,mac=), as qemu-server sets net0's  (52:54:00:12:34:56)
  NET       user: QEMU user-mode networking with outside access (DHCP 10.0.2.15, gateway 10.0.2.2);
            anything else: the NIC is attached to a restricted user network (no outside access)
  BOOT      d (CD) | c (disk): OpenBIOS's `cdrom` or `disk` alias  (d)
  BOOTINDEX 1: bootindex on the disk (100), CD-ROM (101) and NIC (102) as qemu-server sets them
            (QEMU passes them to OpenBIOS as its boot order)    (none; LAYOUT=pve sets it)
  LAYOUT    pve: qemu-server's layout (DISK_BUS and CD_BUS lsi, ids 0 and 2, balloon, bootindex,
            -boot menu=on,strict=on,reboot-timeout=1000; VGA std unless set)  (none)
  EXTRA     more QEMU arguments, shell-quoted                  (none)
  TRACE     QEMU trace events, comma separated, logged to <out>/trace.log
"""
import os
import shlex
import shutil
import subprocess
import time

DEFAULTS = {
    "QEMU": "qemu-system-sparc64", "BIOS": "openbios-sparc64", "MACHINE": "sun4u", "MEM": "512",
    "SMP": "1", "CPU": "", "VGA": "", "CONSOLE": "serial", "ISO": "", "DISK": "", "TEMPLATE": "",
    "DISK_GB": "8", "DISK_BUS": "", "CD_BUS": "", "NIC": "sunhme", "MAC": "52:54:00:12:34:56", "NET": "", "BOOT": "d", "BOOTINDEX": "", "LAYOUT": "",
    "EXTRA": "", "REFRESH": "0",
}

def prepare_disk(v, out):
    disk = v["DISK"] or os.path.join(out, "disk.raw")
    v["DISK"] = disk
    if os.path.exists(disk):
        return disk
    t = v["TEMPLATE"]
    if not t:
        with open(disk, "wb") as f:
            f.truncate(int(v["DISK_GB"]) << 30)
    elif t.endswith(".xz"):
        shutil.copy(t, disk + ".xz")
        subprocess.run(["xz", "-d", disk + ".xz"], check=True)
    else:
        subprocess.run(["cp", "--sparse=always", t, disk], check=True)
    return disk


def _drive(bus, node, file, cd, unit, bootidx, bootindex):
    """-drive/-device for one disk or CD-ROM on `bus`. `unit`: 0 for the disk, 1 for the CD-ROM."""
    ro = ",readonly=on" if cd else ",cache=unsafe"
    media = ",media=cdrom" if cd and bus != "virtio-blk" else ""
    args = ["-drive", f"file={file},if=none,id={node},format=raw{ro}{media}"]
    boot = f",bootindex={bootindex}" if bootidx else ""
    kind = "cd" if cd else "hd"
    if bus == "ide":
        # CMD646: primary master (ide.0) for the disk, secondary master (ide.1) for the CD-ROM, which
        # is where OpenBIOS's `disk` and `cdrom` aliases point
        args += ["-device", f"ide-{kind},bus=ide.{unit},unit=0,drive={node},id={node}-dev{boot}"]
    elif bus == "lsi":
        sid = 2 if cd else 0  # qemu-server: scsi0 = target 0, scsi2 = target 2
        args += ["-device", f"scsi-{kind},bus=scsihw0.0,scsi-id={sid},drive={node},id={node}-dev{boot}"]
    elif bus == "virtio-scsi":
        args += ["-device", f"scsi-{kind},bus=scsihw1.0,channel=0,scsi-id=0,lun={2 if cd else 0},"
                            f"drive={node},id={node}-dev{boot}"]
    elif bus == "virtio-blk":
        args += ["-device", f"virtio-blk-pci,drive={node},id={node}-dev,bus=pciB{boot}"]
    else:
        raise SystemExit(f"unknown bus {bus}")
    return args


def qemu_args(v, out):
    pve = v.get("LAYOUT") == "pve"
    bootidx = pve or bool(v.get("BOOTINDEX"))
    disk_bus = v["DISK_BUS"] or ("lsi" if pve else "ide")
    cd_bus = v["CD_BUS"] or ("lsi" if pve else "ide")
    vga = v["VGA"] or ("std" if pve else "none")
    fw = os.environ.get("LAB_FIRMWARE", "/usr/share/kvm")
    args = [v["QEMU"], "-L", fw, "-nodefaults", "-machine", f"accel=tcg,type={v['MACHINE']}",
            "-m", v["MEM"], "-bios", v["BIOS"]]
    if pve:
        args += ["-boot", "menu=on,strict=on,reboot-timeout=1000"]
        if v.get("BOOT"):
            args += ["-boot", v["BOOT"]]
    elif v.get("BOOT"):
        args += ["-boot", v["BOOT"]]
    if int(v.get("SMP") or 1) > 1:
        args += ["-smp", v["SMP"]]
    if v.get("CPU"):
        args += ["-cpu", v["CPU"]]
    args += ["-vga", vga]
    if v["CONSOLE"] == "serial" and vga != "none":
        args += ["-prom-env", "input-device=ttya", "-prom-env", "output-device=ttya"]
    if pve:
        args += ["-device", "virtio-balloon-pci,id=balloon0,free-page-reporting=on"]
    buses = {disk_bus, cd_bus} if v["ISO"] else {disk_bus}
    if "lsi" in buses:
        args += ["-device", "lsi53c895a,id=scsihw0,bus=pciB"]
    if "virtio-scsi" in buses:
        args += ["-device", "virtio-scsi-pci,id=scsihw1,bus=pciB"]
    if disk_bus != "none":
        args += _drive(disk_bus, "drive-disk", prepare_disk(v, out), False, 0, bootidx, 100)
    if v["ISO"] and cd_bus != "none":
        args += _drive(cd_bus, "drive-cd", v["ISO"], True, 1, bootidx, 101)
    if v["NIC"] != "none":
        net = "user,id=net0" if v.get("NET") == "user" else "user,id=net0,restrict=on"
        boot = ",bootindex=102" if bootidx else ""
        args += ["-netdev", net, "-device", f"{v['NIC']},mac={v.get('MAC') or DEFAULTS['MAC']},netdev=net0,id=net0,bus=pciB{boot}"]
    for ev in filter(None, v.get("TRACE", "").split(",")):
        args += ["-trace", ev]
    if v.get("TRACE"):
        args += ["-D", os.path.join(out, "trace.log")]
    args += shlex.split(v.get("EXTRA", ""))
    return args


# Installed guests: login prompt, account (the lab's installs: NetBSD root without a password,
# OpenBSD and Debian root with "lab") and power-off command; COMMANDS = what sparc64-boot-disk.py records
GUESTS = {
    "netbsd": {"PROMPT": r"login: ?$", "USER": "root", "PASSWORD": "", "POWEROFF": "sync; halt -p",
               "COMMANDS": "uname -a ;; sysctl hw.ncpu hw.physmem64 ;; df -h /"},
    "openbsd": {"PROMPT": r"login: ?$", "USER": "root", "PASSWORD": "lab", "POWEROFF": "sync; halt -p",
                "COMMANDS": "uname -a ;; sysctl hw.ncpu hw.physmem ;; df -h /"},
    # the freebsd124-sun4u target's disk (the stored disk takes PASSWORD=wshlab); root's shell is csh,
    # whose here-documents (sparc64-idle.py's LOAD) end only at the quoted word: sh for the commands
    "freebsd": {"PROMPT": r"login: ?$", "USER": "root", "PASSWORD": "", "POWEROFF": "shutdown -p now",
                "LOGIN_SHELL": "exec /bin/sh",
                "COMMANDS": "uname -a ;; sysctl hw.ncpu hw.physmem ;; df -h /"},
    "debian": {"PROMPT": r"login: ?$", "USER": "root", "PASSWORD": "lab", "POWEROFF": "poweroff",
               "COMMANDS": "uname -a ;; nproc; free -m ;; lsblk ;; ip -br addr"},
    # solaris10-install-sparc64.py's disk; its first boot asks for the keyboard layout
    "solaris10": {"PROMPT": r"console login: ?$", "USER": "root", "PASSWORD": "lab12345", "POWEROFF": "init 5",
                  "FIRSTBOOT": r"Configure Keyboard Layout",
                  "COMMANDS": "uname -a ;; prtconf | head -2 ;; df -h /"},
    # Solaris 7, 8 and 9 (the sun4u install targets' disks; root's password is the install's)
    "solaris": {"PROMPT": r"console login: ?$", "USER": "root", "PASSWORD": "", "POWEROFF": "init 5",
                "COMMANDS": "uname -a ;; prtconf | head -2 ;; df -k /"},
}


def guest_defaults(v):
    """Fill PROMPT, USER, PASSWORD, POWEROFF and COMMANDS from GUEST where they are empty."""
    for k, val in GUESTS.get(v.get("GUEST", ""), {}).items():
        if not v.get(k):
            v[k] = val


def shell(m, command, timeout=600):
    """Run a command at the shell prompt; returns its output (up to the marker line) and the host
    seconds from Return to the marker."""
    m.send(f"{command}; echo END-OF-COMMAND")
    t0 = time.time()
    m.send("\r")
    out = m.expect(r"^((?:.*\n)*?)END-OF-COMMAND$", timeout).group(1)  # at a line start: not the echo
    return out, time.time() - t0


def login(m, v, timeout=900):
    """Wait for the login prompt (v["PROMPT"]) and log in as v["USER"]. A first-boot screen on the way
    (v["FIRSTBOOT"], a regex; Solaris 10's keyboard layout question) is accepted with F2."""
    while True:
        if not v.get("FIRSTBOOT") or m.expect_any([v["PROMPT"], v["FIRSTBOOT"]], timeout) == 0:
            break
        m.quiet(3, 120)
        time.sleep(3)  # keys typed while the screen is still drawn are lost
        m.snap("first-boot question")
        m.key("f2")
    if not v.get("FIRSTBOOT"):
        m.expect(v["PROMPT"], timeout)
    m.snap("login prompt")
    m.send(f"{v['USER']}\r")
    if v["PASSWORD"]:
        m.expect(r"[Pp]assword: ?$", 60)
        m.send(f"{v['PASSWORD']}\r")
    m.expect(r"[#$] ?$", 300)
    if v.get("LOGIN_SHELL"):  # a POSIX shell for the commands (FreeBSD's root has csh)
        m.send(v["LOGIN_SHELL"] + "\r")
        time.sleep(2)
    shell(m, "true")  # past any login messages


def power_off(m, v):
    """Power the guest off with v["POWEROFF"] and wait for QEMU to end (OpenBIOS powers sun4u off when
    the guest asks it to). Returns the host seconds it took."""
    t0 = time.time()
    m.send(f"{v['POWEROFF']}\r")
    code = m.wait_exit(600)
    if code != 0:
        raise AssertionError(f"QEMU exited with {code} after {v['POWEROFF']!r}")
    return time.time() - t0
