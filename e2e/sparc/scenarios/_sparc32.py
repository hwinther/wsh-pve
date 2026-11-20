"""The sparc32 machine (SS-5 unless MACHINE says otherwise) the scenarios share, laid out the way
qemu-server builds it for a `arch: sparc` VM: disk on SCSI target 3, CD-ROM on target 6 with 512-byte
physical blocks, lance NIC.

Variables (lab.py run ... --var KEY=VALUE):
  QEMU      qemu-system-sparc binary                        (qemu-system-sparc)
  BIOS      openbios-sparc32 | ss5.bin | ss10_v2.25_rom ...  (openbios-sparc32)
  MACHINE   SS-5 | SS-10 | SS-20 ...                         (SS-5)
  MEM       MiB                                              (256)
  SMP       CPUs, -smp only when > 1 (SS-10/SS-20: up to 4)  (1)
  CPU       -cpu model, e.g. TI-SuperSparc-II                (none: the machine's default)
  TCG_THREAD single | multi: -accel tcg,thread=...          (none: QEMU's default, multi)
  VGA       cg3 | tcx | none                                 (cg3)
  RES       -g WxH[xDEPTH], the framebuffer size              (none: QEMU's 1024x768)
  CONSOLE   serial | fb: where the PROM puts its console     (serial)
            serial = ttya (OpenBIOS: input/output-device=ttya; the Sun PROMs fall back to ttya
            only without a keyboard, so `serial` with a Sun PROM also drops the framebuffer)
  NOGRAPHIC 1 = -nographic instead of a -vga device, what qemu-server passes for `vga: serialN`:
            no framebuffer, and QEMU disables the keyboard/mouse ESCC (zs1). OpenBSD/sparc 5.9
            panics with a keyboard there ("stray interrupt ipl 0xc", "crazy interrupts")  (none)
  ISO       the install CD                                   (required)
  CDROM_AS  cd | hd: Solaris 2.4/2.5 only boot the installer from a CD that answers as a disk
  DISK      the guest disk; created from TEMPLATE when it doesn't exist  (<out>/disk.raw)
  TEMPLATE  a Sun-labelled disk template (.raw or .raw.xz)    (none: a blank 3 GiB disk)
  DISK2     a second disk (the bench disk), must exist        (none)
  DISK2_ID  its SCSI target; 0-2 would come before the boot disk in OpenBIOS's probe  (4)
  DISK2_RO  1 = read only, 0 = writable                       (1)
  REFRESH   seconds between display updates, 0 = none          (0.5 with a framebuffer, else 0)
            A connected VNC client does this; without it cg3 never raises its vsync interrupt.
  TRACE     QEMU trace events, comma separated (e.g. cg3_write,esp_*), logged to <out>/trace.log
  PROM_ENV  OpenBIOS variables, space separated, each passed as -prom-env (auto-boot?=false for
            solaris-webstart-serial.py; through PVE, install.py puts them into the VM's `args`)  (none)
  PROM_NAME_UNNAMED 1 = with a Sun PROM, name the SBus node QEMU's SS-20 leaves without a name
            before `boot` (Solaris 2.1/2.2 panic on it; name_unnamed_sbus_nodes)  (none)
  AUDIO     wav: the SS-5's CS4231 plays into <out>/audio.wav (-audiodev wav, -machine audiodev),
            44.1 kHz stereo. The header's sizes stay 0 when the guest powers off: the
            samples are what follows its 44 bytes (SPARC.md, "Audio")  (none: no sound)
  NET       user: QEMU user networking (slirp; the guest is 10.0.2.15, the host side 10.0.2.2)
            tap: a tap interface in the lab container (labtap0, 10.0.2.2/24, the same addresses),
            which needs `docker run --cap-add NET_ADMIN --device /dev/net/tun`
            none (default): the lance NIC with nothing behind it
"""
import os
import re
import shutil
import subprocess

from lab import QemuDied

DEFAULTS = {
    "QEMU": "qemu-system-sparc", "BIOS": "openbios-sparc32", "MACHINE": "SS-5", "MEM": "256",
    "SMP": "1", "CPU": "", "VGA": "cg3", "CONSOLE": "serial", "CDROM_AS": "cd", "TEMPLATE": "", "DISK": "",
    "ISO": "", "REFRESH": "",
}


def prepare_disk(v, out):
    if v.get("REFRESH", "") == "":
        v["REFRESH"] = "0" if v["VGA"] == "none" else "0.5"
    disk = v["DISK"] or os.path.join(out, "disk.raw")
    v["DISK"] = disk
    if os.path.exists(disk):
        return disk
    t = v["TEMPLATE"]
    if not t:
        with open(disk, "wb") as f:
            f.truncate(3 << 30)
    elif t.endswith(".xz"):
        shutil.copy(t, disk + ".xz")
        subprocess.run(["xz", "-d", disk + ".xz"], check=True)  # xz writes a sparse file
    else:
        subprocess.run(["cp", "--sparse=always", t, disk], check=True)
    return disk


def qemu_args(v, out):
    if not v["ISO"] and not v.get("NO_CD"):
        raise SystemExit("set ISO=<install CD>")
    disk = prepare_disk(v, out)
    fw = os.environ.get("LAB_FIRMWARE", "/usr/share/kvm")
    accel = ["-accel", f"tcg,thread={v['TCG_THREAD']}"] if v.get("TCG_THREAD") else []
    args = [v["QEMU"], "-L", fw, "-nodefaults", *accel,
            "-machine", f"type={v['MACHINE']}" if accel else f"accel=tcg,type={v['MACHINE']}",
            "-m", v["MEM"], "-bios", v["BIOS"], "-boot", v.get("BOOT", "d")]
    if int(v.get("SMP") or 1) > 1:
        args += ["-smp", v["SMP"]]
    if v.get("CPU"):
        args += ["-cpu", v["CPU"]]
    sun_prom = not v["BIOS"].startswith("openbios")
    if v.get("NOGRAPHIC") == "1":
        args += ["-nographic"]
    elif v["VGA"] == "none" or (v["CONSOLE"] == "serial" and sun_prom):
        args += ["-vga", "none"]
    else:
        args += ["-vga", v["VGA"]]
        if v.get("RES"):
            args += ["-g", v["RES"]]
    if v["CONSOLE"] == "serial" and not sun_prom:
        args += ["-prom-env", "input-device=ttya", "-prom-env", "output-device=ttya"]
    for env in v.get("PROM_ENV", "").split():
        args += ["-prom-env", env]
    args += ["-drive", f"file={disk},if=none,id=drive-scsi3,format=raw,cache=unsafe",
             "-device", "scsi-hd,channel=0,scsi-id=3,lun=0,drive=drive-scsi3,id=scsi3"]
    if v.get("DISK2"):
        if not os.path.exists(v["DISK2"]):
            raise SystemExit(f"DISK2={v['DISK2']} doesn't exist")
        ro = ",readonly=on" if v.get("DISK2_RO", "1") == "1" else ""
        t = v.get("DISK2_ID") or "4"
        args += ["-drive", f"file={v['DISK2']},if=none,id=drive-scsi{t},format=raw,cache=unsafe{ro}",
                 "-device", f"scsi-hd,channel=0,scsi-id={t},lun=0,drive=drive-scsi{t},id=scsi{t}"]
    if v["ISO"]:
        cd = "scsi-hd" if v["CDROM_AS"] == "hd" else "scsi-cd"
        media = "" if cd == "scsi-hd" else ",media=cdrom"
        args += ["-drive", f"file={v['ISO']},if=none,id=drive-scsi6,format=raw,readonly=on{media}",
                 "-device", f"{cd},channel=0,scsi-id=6,lun=0,drive=drive-scsi6,id=scsi6,physical_block_size=512"]
    for ev in filter(None, v.get("TRACE", "").split(",")):
        args += ["-trace", ev]
    if v.get("TRACE"):
        args += ["-D", os.path.join(out, "trace.log")]
    if v.get("AUDIO") == "wav":
        args += ["-audiodev", f"wav,id=snd0,path={os.path.join(out, 'audio.wav')}", "-machine", "audiodev=snd0"]
    if v.get("NET") == "user":
        args += ["-net", "nic,model=lance", "-net", "user"]
    elif v.get("NET") == "tap":
        tap_up()
        args += ["-netdev", f"tap,id=net0,ifname={TAP},script=no,downscript=no", "-net", "nic,model=lance,netdev=net0"]
    else:
        args += ["-net", "nic,model=lance"]
    return args


TAP = "labtap0"


def tap_up():
    """NET=tap: the tap interface QEMU attaches to, with the address user networking gives the host side
    (10.0.2.2), so the guest is set up the same either way. Kept for the next run if it exists."""
    if not os.path.exists(f"/sys/class/net/{TAP}"):
        subprocess.run(["ip", "tuntap", "add", "dev", TAP, "mode", "tap"], check=True)
    subprocess.run(["ip", "addr", "replace", "10.0.2.2/24", "dev", TAP], check=True)
    subprocess.run(["ip", "link", "set", TAP, "up"], check=True)


# The ESP SCSI controller by node names only: OpenBIOS resolves a path without unit addresses to the
# first node of that name, so this one path works on SS-5 (/iommu@0,10000000/sbus@0,10001000/...) and
# SS-10/SS-20 (/iommu@f,e0000000/sbus@f,e0001000/...). The packaged OpenBIOS's aliases use it too.
ESP = "/iommu/sbus/espdma/esp"


def prom_boot(m, v, target):
    """Get to the PROM prompt and boot `target` ("cdrom" or "disk"), with the console on ttya.

    OpenBIOS: its `cdrom` alias only finds a CD-ROM device, and stock OpenBIOS since QEMU 9.2 has no
    `disk` alias (the packaged one is fixed, and so was the one in 7.2: they boot the disk by
    themselves), so anything else boots by device path at the `0 >` prompt. Sun PROMs: with a
    keyboard ("Keyboard Present", the lab's own QEMU with -vga none) input stays on the keyboard
    while output goes to ttya, so `ttya io` is typed on the keyboard first; without one ("No
    Keyboard": QEMU's -nographic, which qemu-server passes for `vga: serialN`) the PROM reads ttya
    already.

    A sun4u VM through PVE (ARCH sparc64, from lab.pve_vars; the Solaris 8/9 sun4u targets share these
    scenarios): qemu-server passes the boot device as `-boot order=c|d` and OpenBIOS boots it by
    itself ("Trying disk:a..."); with `auto-boot?` false (an install's prom_env) it stops at `0 >`,
    where the `cdrom:f` or `disk:a` alias is booted."""
    if v.get("ARCH") == "sparc64":
        if m.expect_any([r"0 >", r"Trying \S+\.\.\."], 300) == 0:
            m.snap("OpenBIOS prompt")
            m.send(f"boot {'cdrom:f' if target == 'cdrom' else 'disk:a'}\r")
        return
    if v["BIOS"].startswith("openbios"):
        if target == "cdrom" and v["CDROM_AS"] != "hd" and v.get("BOOT", "d") == "d":
            return  # -boot d: OpenBIOS boots the CD by itself
        if m.expect_any([r"0 >", r"bootpath: "], 300) == 1:
            return  # it found the boot device by itself
        m.snap("OpenBIOS prompt")
        path = f"{ESP}/sd@6,0:d" if target == "cdrom" else f"{ESP}/sd@3,0:a"
        m.send(f"boot {path}\r")
        return
    seen = m.expect_any([r"Keyboard Present", r"No Keyboard", r"\nok "], 600)
    keyboard = seen != 1  # the banner missed (attached late): as before, type `ttya io`
    if seen != 2:
        m.expect(r"\nok ", 600)
    m.snap("PROM prompt")
    if v["CONSOLE"] == "serial" and keyboard:
        m.fb_type("ttya io\r")
        m.expect(r"ok ", 30)
    if v.get("PROM_NAME_UNNAMED") == "1":
        name_unnamed_sbus_nodes(m)
    m.send(f"boot {target}\r")


def name_unnamed_sbus_nodes(m, name="SUNW,DBRIe"):
    """PROM_NAME_UNNAMED=1 (Sun PROMs on QEMU's SS-20, lab only): give a name to the SBus node the PROM
    leaves without one. QEMU's SS-20 puts an unimplemented device (reads 0) where the DBRI's FCode PROM
    would be (slot e); the Sun SS-10/SS-20 PROMs make a node for it without a `name` property, and
    Solaris 2.1/2.2 panic on it (`BAD TRAP: type=9`, a strcmp on NULL in get_neighbors, from
    impl_init_tree). Later releases don't mind. OBP 2.x has no word to select a node by phandle, so the
    setter `find-device` uses (a headerless word) is taken from `see find-device`."""
    m.send("see find-device\r")
    setter = m.expect(r"r> \((\w{8})\) throw", 30).group(1)
    m.expect(r"ok ", 30)
    m.send("cd /iommu/sbus\r")
    m.expect(r"ok ", 30)
    m.send("ls\r")
    listing = m.expect(r"ls\n((?:.*\n)*?)ok ", 30).group(1)
    nodes = re.findall(r"^(\w{8}) <Unnamed>", listing, re.M)
    for ph in dict.fromkeys(nodes):
        m.send(f'{ph} {setter} execute " {name}" device-name device-end\r')
        m.expect(r"ok ", 30)
    m.send("device-end\r")
    m.expect(r"ok ", 30)
    m.snap(f"named {len(set(nodes))} unnamed SBus node(s)")


def login(m, prompt=r"console login:", timeout=1800, password=""):
    """Wait for the login prompt, answering Solaris's first-boot questions on the way (the root
    password they ask for: `password`, none by default), and log in as root with `password`.

    Solaris 2.3 asks in its older style, one screen per prompt ("What is your root password?", then
    "Please re-enter your root password."), and its first login then insists on a new password
    ("Choose a new password."): `password` again, twice."""
    form = r"create a root password"
    old = r"What is your root password\?"
    i = m.expect_any([form, r"Press Return to continue", prompt, old], timeout)
    while i != 2:
        if i == 3:
            m.quiet(2, 120)
            m.snap("root password")
            m.send(password + "\r")
            m.expect(r"re-enter your root password", 120)
            m.quiet(2, 120)
            m.send(password + "\r")
            i = m.expect_any([form, r"(?!)", prompt, old], timeout)
            continue
        if i == 1:
            m.snap("press return")
            m.send("\r")
            i = m.expect_any([form, r"Press Return to continue", prompt], timeout)
            continue
        # sysidroot draws its whole form at once ("Root password:", "Press Return to continue.",
        # "Re-enter your root password."), so the prompts in the output say nothing about where the
        # cursor is: wait for the form to settle and type the password twice, then look only for
        # what comes after the form (a mismatch draws it again). The field doesn't echo.
        m.snap("root password")
        for _ in range(2):
            m.quiet(2, 120)
            m.send(password + "\r")
        i = m.expect_any([form, r"System identification is completed", prompt, old], timeout)
        if i == 1:
            i = m.expect_any([form, r"(?!)", prompt, old], timeout)
    m.snap("login prompt")
    m.send("root\r")
    if password:
        m.expect(r"Password:\s*$", 60)
        m.send(password + "\r")
        if m.expect_any([r"#\s*$", r"New password:\s*$"], 120) == 1:
            m.snap("new password")
            m.send(password + "\r")
            m.expect(r"Re-enter new\s+password:\s*$", 60)
            m.send(password + "\r")
            m.expect(r"#\s*$", 120)
        return
    m.expect(r"#\s*$", 120)


def power_off(m, command):
    """Shut the guest down with `command` ("halt", "init 5") and end QEMU. OpenBIOS powers the machine
    off; the Sun PROMs stop at `ok` ("Program terminated"), so QEMU is told to quit there. Solaris
    2.3's `init 5` reboots ("rebooting..."); the Sun PROM then fails its network boot and stops at
    `ok` too, OpenBIOS starts again (its banner), and QEMU is told to quit there."""
    m.send(f"sync; {command}\r")
    try:
        i = m.expect_any([r"power off|Power down", r"Program terminated|rebooting\.\.\."], 600)
    except QemuDied:
        if m.proc.returncode == 0:  # powered off before the message was read
            m.log("QEMU exited with 0")
            return
        raise
    if i == 1:
        m.expect(r"\nok |Welcome to OpenBIOS", 300)
        m.snap("PROM prompt after shutdown")
        m.stop()
        return
    m.wait_exit(300)
