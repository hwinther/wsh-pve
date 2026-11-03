"""The sparc32 (SS-5) machine the scenarios share, laid out the way qemu-server builds it for a
`arch: sparc` VM: disk on SCSI target 3, CD-ROM on target 6 with 512-byte physical blocks, lance NIC.

Variables (lab.py run ... --var KEY=VALUE):
  QEMU      qemu-system-sparc binary                        (qemu-system-sparc)
  BIOS      openbios-sparc32 | ss5.bin | ss10_v2.25_rom ...  (openbios-sparc32)
  MACHINE   SS-5 | SS-10 | SS-20 ...                         (SS-5)
  MEM       MiB                                              (256)
  VGA       cg3 | tcx | none                                 (cg3)
  CONSOLE   serial | fb: where the PROM puts its console     (serial)
            serial = ttya (OpenBIOS: input/output-device=ttya; the Sun PROMs fall back to ttya
            only without a keyboard, so `serial` with a Sun PROM also drops the framebuffer)
  ISO       the install CD                                   (required)
  CDROM_AS  cd | hd: Solaris 2.4/2.5 only boot the installer from a CD that answers as a disk
  DISK      the guest disk; created from TEMPLATE when it doesn't exist  (<out>/disk.raw)
  TEMPLATE  a Sun-labelled disk template (.raw or .raw.xz)    (none: a blank 3 GiB disk)
  REFRESH   seconds between display updates, 0 = none          (0.5 with a framebuffer, else 0)
            A connected VNC client does this; without it cg3 never raises its vsync interrupt.
  TRACE     QEMU trace events, comma separated (e.g. cg3_write,esp_*), logged to <out>/trace.log
"""
import os
import shutil
import subprocess

from lab import QemuDied

DEFAULTS = {
    "QEMU": "qemu-system-sparc", "BIOS": "openbios-sparc32", "MACHINE": "SS-5", "MEM": "256",
    "VGA": "cg3", "CONSOLE": "serial", "CDROM_AS": "cd", "TEMPLATE": "", "DISK": "", "ISO": "", "REFRESH": "",
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
    args = [v["QEMU"], "-L", fw, "-nodefaults", "-machine", f"accel=tcg,type={v['MACHINE']}",
            "-m", v["MEM"], "-bios", v["BIOS"], "-boot", v.get("BOOT", "d")]
    sun_prom = not v["BIOS"].startswith("openbios")
    if v["VGA"] == "none" or (v["CONSOLE"] == "serial" and sun_prom):
        args += ["-vga", "none"]
    else:
        args += ["-vga", v["VGA"]]
        if v.get("RES"):
            args += ["-g", v["RES"]]
    if v["CONSOLE"] == "serial" and not sun_prom:
        args += ["-prom-env", "input-device=ttya", "-prom-env", "output-device=ttya"]
    args += ["-drive", f"file={disk},if=none,id=drive-scsi3,format=raw,cache=unsafe",
             "-device", "scsi-hd,channel=0,scsi-id=3,lun=0,drive=drive-scsi3,id=scsi3"]
    if v["ISO"]:
        cd = "scsi-hd" if v["CDROM_AS"] == "hd" else "scsi-cd"
        media = "" if cd == "scsi-hd" else ",media=cdrom"
        args += ["-drive", f"file={v['ISO']},if=none,id=drive-scsi6,format=raw,readonly=on{media}",
                 "-device", f"{cd},channel=0,scsi-id=6,lun=0,drive=drive-scsi6,id=scsi6,physical_block_size=512"]
    for ev in filter(None, v.get("TRACE", "").split(",")):
        args += ["-trace", ev]
    if v.get("TRACE"):
        args += ["-D", os.path.join(out, "trace.log")]
    args += ["-net", "nic,model=lance", "-net", "user"] if v.get("NET") == "user" else ["-net", "nic,model=lance"]
    return args


ESP = "/iommu@0,10000000/sbus@0,10001000/espdma@5,8400000/esp@5,8800000"


def prom_boot(m, v, target):
    """Get to the PROM prompt and boot `target` ("cdrom" or "disk"), with the console on ttya.

    OpenBIOS: its `cdrom` alias only finds a CD-ROM device and its `disk` alias doesn't reach SCSI
    target 3, so anything else boots by device path. Sun PROMs: input stays on the keyboard while
    output goes to ttya, so `ttya io` is typed on the keyboard first."""
    if v["BIOS"].startswith("openbios"):
        if target == "cdrom" and v["CDROM_AS"] != "hd" and v.get("BOOT", "d") == "d":
            return  # -boot d: OpenBIOS boots the CD by itself
        m.expect(r"0 >", 300)
        m.snap("OpenBIOS prompt")
        path = f"{ESP}/sd@6,0:d" if target == "cdrom" else f"{ESP}/sd@3,0:a"
        m.send(f"boot {path}\r")
        return
    m.expect(r"\nok ", 600)
    m.snap("PROM prompt")
    if v["CONSOLE"] == "serial":
        m.fb_type("ttya io\r")
        m.expect(r"ok ", 30)
    m.send(f"boot {target}\r")


def power_off(m, command):
    """Shut the guest down with `command` ("halt", "init 5") and end QEMU. OpenBIOS powers the machine
    off; the Sun PROMs stop at `ok` ("Program terminated"), so QEMU is told to quit there."""
    m.send(f"sync; {command}\r")
    try:
        i = m.expect_any([r"power off|Power down", r"Program terminated"], 600)
    except QemuDied:
        if m.proc.returncode == 0:  # powered off before the message was read
            m.log("QEMU exited with 0")
            return
        raise
    if i == 1:
        m.expect(r"ok ", 60)
        m.snap("PROM prompt after shutdown")
        m.stop()
        return
    m.wait_exit(300)
