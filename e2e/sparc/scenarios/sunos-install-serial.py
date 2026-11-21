"""SunOS 4.1.4 install over the serial console, from the CD to an installed disk that is powered off:
the CD's miniroot copied to the swap slice, then suninstall's Quick install from it. Tested in attach
mode (`lab.py install sunos414-ss5`, a PVE VM with `args: -prom-env auto-boot?=false` and 64 MB).

    lab.py run scenarios/sunos-install-serial.py --pve 400 --out /root/runs/sunos

The VM: SS-5 with OpenBIOS, `vga: serial0`, the CD (sunos414-cd.iso: the BIN with 2048-byte sectors)
on target 6 and a disk on target 3 with a Sun label whose slice g is under 2 GB (targets.SUN29G_SUNOS4;
Quick install keeps the label and newfs's a and g). OpenBIOS must stop at `0 >` after each reset
(auto-boot? false): the CD boots from slice d (the sun4m boot) and the miniroot from the disk's slice
b, both typed by path, because OpenBIOS drops the boot string of the miniroot's reboot.

Under a Sun PROM (BIOS not OpenBIOS; tested with the SPARCstation LX in the lab, submodules/SPARC.md,
"SPARCstation LX") the CD boots with `boot cdrom` and the PROM boots the miniroot by itself. Run it
with NOGRAPHIC=1: with a keyboard the PROM takes input from it again after each reset, and the
miniroot's shell then never sees ttya.

  SOFTWARE  the standard installation on suninstall's menu      (Programmer)
            Typical_user, Programmer, Full_install, Mini_install; only Programmer is tested
            (Full_install stopped at the Versatec set in the hand install)
  MEM       64: the CD's kernel stops QEMU with 256 MB (Trap 0x29); in attach mode the VM's memory
"""
import re

from _sparc32 import DEFAULTS as BASE, esp, qemu_args as sparc32_args
from _sunos4 import SHELL

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "MEM": "64", "SOFTWARE": "Programmer"}
SOFTWARE = ["Typical_user", "Programmer", "Full_install", "Mini_install"]


def qemu_args(v, out):
    return sparc32_args(v, out) + ["-prom-env", "auto-boot?=false"]


# What a Sun PROM (BIOS other than OpenBIOS, e.g. the LX's) boots for the paths typed at OpenBIOS
SUN_PROM_BOOT = {"/sd@6,0:d": "cdrom", "/sd@3,0:b -sw": "disk:b -sw"}


def prom(m, v, path, timeout=300):
    """Boot `path`, below the ESP (`/sd@6,0:d`), at the PROM prompt."""
    if v["BIOS"].startswith("openbios"):
        m.expect(r"0 >", timeout)
        m.snap("OpenBIOS prompt")
        m.send(f"boot {esp(v)}{path}\r")
        return
    # A Sun PROM ignores -prom-env (QEMU's NVRAM fails its checksum): at power-on it tries its default
    # boot device and stops at `ok`, but the miniroot's reboot string it boots by itself. With a
    # keyboard its input stays there (prom_boot).
    keyboard = m.expect_any([r"Keyboard Present", r"No Keyboard"], timeout) == 0
    if m.expect_any([r"\nok ", r"SunOS Release 4\.1"], timeout) == 1:
        return
    m.snap("PROM prompt")
    if keyboard:
        m.fb_type("ttya io\r")
        m.expect(r"ok ", 30)
    m.send(f"boot {SUN_PROM_BOOT[path]}\r")


def answer(m, prompt, reply, timeout=300, title=None):
    """Wait for a prompt on the serial output (its text, not the last character, which SunOS often
    sends only with the next key) and type the reply."""
    m.expect(prompt, timeout)
    m.snap(title or prompt)
    m.send(reply)


def run(m, v):
    if v["SOFTWARE"] not in SOFTWARE:
        raise ValueError(f"SOFTWARE must be one of {SOFTWARE}")
    prom(m, v, "/sd@6,0:d")  # the CD's slice d: the sun4m boot and munix
    m.expect(r"SunOS Release 4\.1", 600)
    m.snap("CD kernel banner")
    answer(m, r"1 - install SunOS mini-root[\s\S]*Enter a 1 or 2:", "1\r", 600, "install the mini-root")
    answer(m, r"Do you want to format and/or label disk[\s\S]*Enter a 1, 2, or 3:", "2\r", 300,
           "no format: the label is there")
    m.expect(r"Mini-root installation complete", 1200)
    answer(m, r"1 - reboot using the just-installed miniroot[\s\S]*Enter a 1 or 2:", "1\r", 60, "reboot")
    # OpenBIOS drops the reboot's boot string: the miniroot on slice b, single user, writable root
    prom(m, v, "/sd@3,0:b -sw")
    m.expect(r"root on sd0b", 600)
    m.expect(SHELL, 600)
    m.snap("miniroot shell")
    m.send("TERM=vt100; export TERM; suninstall\r")
    answer(m, r"Quick installation[\s\S]*Your choice \(or Q to quit\) >>", "1\r", 300, "Quick installation")
    # the [Y/N] prompts show the default; a typed letter replaces it, Return takes it
    answer(m, r"preserve the existing data partitions\? \[Y/N\] :", "y\r", 300, "preserve data partitions")
    m.expect(r"STANDARD INSTALLATIONS", 300, screen=True)
    m.expect(r"Mini_install", 60, screen=True)
    m.quiet(3, 120)
    screen = m.screen_text()
    listed = re.findall(r"^\s+(Typical_user|Programmer|Full_install|Mini_install)\s", screen, re.M)
    if v["SOFTWARE"] not in listed:
        raise RuntimeError(f"{v['SOFTWARE']} isn't on the menu: {listed}")
    m.snap("standard installations")
    # the cursor starts on the first entry; Space moves down, x selects
    m.send(" " * listed.index(v["SOFTWARE"]) + "x")
    m.expect(rf"Standard Installation: {v['SOFTWARE']}", 120, screen=True)
    answer(m, r"Start the installation\? \[Y/N\] :", "y\r", 60, "confirmation")
    m.expect(r"System Installation Begins", 300)
    m.snap("installing")
    i = m.expect_any([r"System installation completed", r"[Ee]rror|Please mount"], 3600)
    if i:
        m.quiet(10, 300)
        raise RuntimeError("suninstall reported a problem (the screen and /etc/install/suninstall.log)")
    answer(m, r"Reboot now\? \[Y/N\] :", "y\r", 300, "installation finished: reboot")
    # auto-boot? false: the reset stops at the prompt; power off there (the install phase ends)
    if not v["BIOS"].startswith("openbios"):
        # a Sun PROM: `ok` after its default boot device, or the installed system if it boots that
        m.expect_any([r"\nok ", r"SunOS Release 4\.1"], 600)
        m.snap("PROM prompt after the install")
        m.stop()
        return
    m.expect(r"0 >", 300)
    m.snap("OpenBIOS prompt after the install")
    m.send("power-off\r")
    m.wait_exit(120)
