"""A Sun PROM VM with an NVRAM volume (`nvram0`), through PVE: the one-time setup, auto-boot after a
cold start, and a reconfiguration boot, with Solaris to the login prompt each time. Attach mode only
(`lab.py run --pve <vmid>`); the VM needs `vga: serial0` (the PROM reads ttya) and a blank `nvram0`.

    lab.py run scenarios/sun-prom-nvram.py --pve <vmid> --out /work/runs/nvram

  ROOT_PASSWORD  root's password, for the login and the first-boot questions  (none)
  CHECK          a regex the logged-in `eeprom` must print                   (diag-switch?=false)

1. First start, blank volume: the PROM finds its NVRAM invalid, tries the network and stops at `ok`.
   `setenv diag-switch? false` (the PROM writes it into the volume), then `boot disk`. A stored disk
   with a pending first boot reconfigures here (`Configuring the /devices directory`) and asks for
   the root password (login() answers it). Logged in, `eeprom` must show `diag-switch?=false`, then
   `halt`, which stops at `ok` ("Program terminated") with the VM still running.
2. `qm stop`, `qm start` (PveMachine.power_cycle(), a new QEMU process): nothing is typed; the PROM
   must boot the disk by itself (an `ok` prompt fails the run) and Solaris reach the login prompt,
   with `le0` configured (before pve-qemu `wsh/0061` QEMU stopped there with `Trap 0x29`).
3. `reboot -- -r` from the shell: the PROM boots the disk with `-r`, Solaris rebuilds /devices
   (`Configuring the /devices directory`), which loads `dbri` (before pve-qemu `wsh/0066` it panicked
   there under the SS-20 and SS-10 PROMs), and reaches the login prompt again; then `init 5`, which
   powers the VM off (PVE ends QEMU). On the SS-20 PROM `/devices` must have the DBRI's nodes.

Any `BAD TRAP`, `panic` or QEMU `Trap 0x..` on the console fails the run. Times go to result.json
(`metrics`): `setup_to_login` (from the first `ok`), `autoboot_to_login` (from `qm start`),
`reconfigure_to_login` (from `reboot`), and `first_boot_reconfigured`. See submodules/SPARC.md, "The
SS-20 PROM through PVE".
"""
import re

from _sparc32 import DEFAULTS as BASE, login
from lab import QemuDied

DEFAULTS = {**BASE, "VGA": "none", "ROOT_PASSWORD": "", "CHECK": r"diag-switch\?=false"}

PANIC = r"BAD TRAP|panic\[cpu|panic:|Trap 0x[0-9a-f]+ \("
UP = r"configuring network interfaces:[^\n]*\n"  # Solaris 2.6: le0 is plumbed before drvconfig runs


def qemu_args(v, out):
    raise SystemExit("sun-prom-nvram.py: attach mode only (lab.py run --pve <vmid>)")


def no_panic(m, what):
    hit = re.search(PANIC, m.text)
    if hit:
        raise RuntimeError(f"{what}: {hit.group(0)!r} on the console")


def prom_boots(m):
    """After a start or a reboot: True when the PROM boots by itself (the kernel banner comes), False
    when it stops at `ok`."""
    return m.expect_any([r"\nok ", r"SunOS Release"], 600) == 1


def boot_to_login(m, v, what, reconfigure=False):
    """From the kernel banner (already matched) to a root shell: no panic on the way, le0 configured,
    and with `reconfigure` the /devices rebuild seen."""
    m.snap(f"{what}: kernel banner")
    if m.expect_any([PANIC, UP], 600) == 0:
        no_panic(m, what)
    line = m.text[max(0, m.pos - 200):m.pos].splitlines()[-1]
    if "le0" not in line:
        raise RuntimeError(f"{what}: le0 not configured: {line.strip()!r}")
    if reconfigure and m.expect_any([PANIC, r"Configuring the /devices directory"], 600) == 0:
        no_panic(m, what)
    if m.expect_any([PANIC, r"The system is coming up"], 600) == 0:  # drvconfig (dbri) is done by then
        no_panic(m, what)
    login(m, password=v["ROOT_PASSWORD"])
    no_panic(m, what)
    m.snap(f"{what}: logged in")


def shell(m, command, expect=None, timeout=300):
    m.send(command + "\r")
    if expect:
        m.expect(expect, timeout)
    m.expect(r"\n#\s*$", timeout)


def halt_to_ok(m, what):
    """`halt`: Solaris stops at the PROM's `ok` ("Program terminated"); the VM keeps running."""
    m.send("sync; halt\r")
    m.expect(r"Program terminated", 600)
    m.expect(r"\nok ", 120)
    m.snap(f"{what}: ok after halt")


def power_off(m, what):
    """`init 5`: the SS-20 powers itself off, and PVE ends QEMU (qmeventd); a PROM that stops at `ok`
    instead passes too (lab.py stops the VM)."""
    m.send("sync; init 5\r")
    try:
        m.expect(r"Program terminated", 600)
        m.snap(f"{what}: ok after init 5")
    except QemuDied:
        m.log(f"{what}: powered off")


def run(m, v):
    if v.get("ARCH") != "sparc" or v["BIOS"].startswith("openbios"):
        raise SystemExit("sun-prom-nvram.py: a sparc32 VM with a Sun PROM (bios ss20_v2.25_rom, ss5.bin, lx.bin)")

    # 1. blank volume: the PROM's defaults, the network tried, `ok`
    if prom_boots(m):
        raise RuntimeError("first start: the PROM booted by itself, so the volume wasn't blank")
    t = m.elapsed()
    m.snap("first start: ok (blank NVRAM)")
    m.send("setenv diag-switch? false\r")
    m.expect(r"\nok ", 60)
    m.send("boot disk\r")
    m.expect(r"SunOS Release", 600)
    cursor = m.pos
    boot_to_login(m, v, "first start")
    m.metrics["setup_to_login"] = round(m.elapsed() - t, 1)
    m.metrics["first_boot_reconfigured"] = "Configuring the /devices directory" in m.text[cursor:]
    shell(m, "uname -a; eeprom diag-switch? auto-boot? boot-device", v["CHECK"])
    m.snap("first start: eeprom")
    halt_to_ok(m, "first start")

    # 2. qm stop, qm start: nothing typed, the PROM boots the disk
    m.power_cycle()
    t = m.elapsed()
    if not prom_boots(m):
        m.snap("cold start: stopped at ok")
        raise RuntimeError("cold start: the PROM stopped at ok instead of booting the disk (NVRAM not kept?)")
    boot_to_login(m, v, "cold start")
    m.metrics["autoboot_to_login"] = round(m.elapsed() - t, 1)

    # 3. a reconfiguration boot through the PROM (boot-device with -r)
    t = m.elapsed()
    m.send("reboot -- -r\r")
    if not prom_boots(m):
        m.snap("boot -r: stopped at ok")
        raise RuntimeError("reboot -- -r: the PROM stopped at ok")
    boot_to_login(m, v, "boot -r", reconfigure=True)
    m.metrics["reconfigure_to_login"] = round(m.elapsed() - t, 1)
    cursor = m.pos
    shell(m, "uname -a; ls /devices/iommu*/sbus* | grep -i dbri; eeprom diag-switch?", v["CHECK"])
    m.snap("boot -r: state")
    # drvconfig attached dbri and made its nodes (SUNW,DBRIe@e,10000:sound,audio and audioctl)
    if v["BIOS"] == "ss20_v2.25_rom" and "SUNW,DBRIe@" not in m.text[cursor:]:
        raise RuntimeError("boot -r: no SUNW,DBRIe nodes in /devices (dbri not attached)")
    power_off(m, "boot -r")
