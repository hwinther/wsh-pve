"""The x86 retro install targets (DOS from floppies, and ReactOS from its CD): merged into targets.MEDIA
and targets.TARGETS by targets.py, kept here so the x86 profiles and their media live in one place. Data
only, like targets.py.

The VM profile (X86_DOS) and why each option is what it is: e2e/sparc/README.md, "DOS install
targets", and docs/src/content/docs/guides/dos.md. In short: i440fx (`machine: pc`; `isapc` isn't
accepted by qemu-server), a Pentium (period plausible for DOS 6.22, enough for HIMEM/EMM386), TCG for
reproducible timing (`kvm: 0`; KVM works too), 32 MB without a balloon, no USB tablet, std VGA, a 1 GiB
IDE disk (one FAT16 partition, SeaBIOS translates the geometry), the floppy drive first in the boot
order, and an ne2k_pci NIC that the install doesn't use (ne2k_isa would cost no upper memory but
qemu-server puts it on the PCI bus and the VM doesn't start; see the guide).

Floppies are attached read only (`ro=1`): they are shared reference media, and a written image would no
longer match its sha256. Microsoft's media are never in the repository; FreeDOS is freely
redistributable and the CI test downloads it by sha256 (FREEDOS_ZIP).
"""

PACKAGES_2026_11_17 = {"pve-qemu-kvm": "11.1.3-2+wsh11", "qemu-server": "9.2.15+wsh6",
                       "pve-manager": "9.2.28+wsh4"}
# the published packages of 2026-11-20 (qemu-server with the branch's legacy-bios-layout overlaid, which
# the DOS profile doesn't use)
PACKAGES_2026_11_20 = {"pve-qemu-kvm": "11.1.3-2+wsh26", "qemu-server": "9.2.19+wsh2",
                       "pve-manager": "9.2.31+wsh4"}
# the published packages of 2026-11-27 (ReactOS)
PACKAGES_2026_11_27 = {"pve-qemu-kvm": "11.1.3-4+wsh37", "qemu-server": "9.2.24+wsh5",
                       "pve-manager": "9.3.1+wsh1"}

X86_DOS = {"ostype": "other", "machine": "pc", "cpu": "pentium", "kvm": 0, "memory": 32, "balloon": 0,
           "tablet": 0, "vga": "std", "net0": "ne2k_pci", "boot": "order=floppy0;ide0"}

# The FreeDOS 1.4 Floppy Edition (GPL and other free licences), for CI and as a free target. The only pin
# of the zip: tests/test_freedos.py, the 3dfx DOS test (e2e/3dfx/dos/dos_test.py) and the audio matrix
# (e2e/audio/audio_matrix.py) import it, fetch_media.py downloads and checks it, and "cache" names its
# Actions cache entry (fetch_media.py --key; e2e/README.md, "Downloaded media in the Actions cache").
FREEDOS_ZIP = {"url": "https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/distributions/1.4/"
                      "FD14-FloppyEdition.zip",
               "sha256": "45b1fa7c52dd996c3bfa5e352ffcd410781b952a6ad629f15a4c9ec4bbaefc5a", "size": 23624258,
               "cache": "freedos-fd14-floppy"}

MEDIA = {
    "msdos622-disk1.img": {
        "title": "MS-DOS 6.22 Setup Disk 1 (1.44 MB, bootable)", "content": "floppy", "size": 1474560,
        "sha256": "b88030401122d234ea6aafba3cfed7de2b7b1782700a67be5498edca6f9fec5d", "lab": "msdos/622/Disk1.img"},
    "msdos622-disk2.img": {
        "title": "MS-DOS 6.22 Setup Disk 2", "content": "floppy", "size": 1474560,
        "sha256": "e1d48a415495a17d65316d5328a91d7df0910fb1e42b0b07e7dbf8a4b4df305a", "lab": "msdos/622/Disk2.img"},
    "msdos622-disk3.img": {
        "title": "MS-DOS 6.22 Setup Disk 3", "content": "floppy", "size": 1474560,
        "sha256": "52a3b4e7f5973c38f2517dbb20426bf5c8bd62f202e84a85d3d7283401d5e63c", "lab": "msdos/622/Disk3.img"},
    "msdos622-supp.img": {
        "title": "MS-DOS 6.22 Supplemental Disk", "content": "floppy", "size": 1474560,
        "sha256": "774ea0611b5602133f7719339294eb6936d1256bb534733ecdd9c9de47e57090", "lab": "msdos/622/Suppdisk.img"},
}
for _n, _sha in enumerate(["552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc",
                           "b9dd5315f50a8b770b3d2ecb623b18ed067660e22f421504d199254f7f653516",
                           "4a951f15da8dd98e54ea84f07fe2a7802e914aa8e66942f646d2e11ca3943e59",
                           "fbfd172e1ac4bc4abb3f656cae94e2727d2b48b4d02cef0362564048f83f35da",
                           "894d49c4dfdd294e33878ca317e19a0322f267f639b247a6b2a669799b4720f8",
                           "0362e084497c5c995ccab1523c4e39f94b7139f988ffa3a4f7e871452c352f3c",
                           "7a93d1d4e47f5edd5d0a9f17d57c3417ae135052db9449a67aa374a3b4316d80"]):
    _src = "x86BOOT.img" if _n == 0 else f"x86DSK{_n:02d}.img"
    MEDIA["freedos14-boot.img" if _n == 0 else f"freedos14-disk{_n}.img"] = {
        "title": f"FreeDOS 1.4 Floppy Edition, {'boot disk' if _n == 0 else f'disk {_n}'} (1.44 MB)",
        "content": "floppy", "size": 1474560, "sha256": _sha, "lab": f"freedos/14/{_src}",
        "zip": f"144m/{_src}"}

# The check fails when the guest idling at the prompt uses this much of a host core or more: with its idle
# driver DOS takes 1-2% (MS-DOS: WSHIDLE.COM, which the first boot puts in AUTOEXEC.BAT; FreeDOS: FDAPM
# APMDOS, which its installer puts in FDAUTO.BAT), without one 100%.
IDLE_BELOW = "25"

DOS_LOGIN = {"user": None, "password": False, "console": "VGA (noVNC console of VM <vmid>); no serial port"}

TARGETS = {
    "msdos622": {
        "title": "MS-DOS 6.22 from the three Setup floppies (i440fx, SeaBIOS, Pentium, std VGA)",
        "status": "automated",
        "method": "scripted",
        "profile": dict(X86_DOS),
        "disk": {"bus": "ide0", "size": 1, "label": None},
        "media": [{"name": "msdos622-disk1.img", "drive": "floppy0"},
                  {"name": "msdos622-disk2.img", "drive": "floppy0", "at": r"Setup Disk #2"},
                  {"name": "msdos622-disk3.img", "drive": "floppy0", "at": r"Setup Disk #3"}],
        # SETUP partitions (reboots), formats, copies with two disk swaps, asks for the floppy to be
        # removed and boots the disk; the first boot types in WSHIDLE.COM with DEBUG and writes CONFIG.SYS,
        # AUTOEXEC.BAT (which loads it) and the marker.
        "install": {"scenario": "dos622-install.py", "vars": {}, "timeout": 1800},
        "firstboot": {"scenario": "dos-firstboot.py", "vars": {"FLAVOUR": "msdos"}, "timeout": 900},
        "check": {"scenario": "dos-boot-disk.py", "vars": {"VERSION": r"MS-DOS Version 6\.22",
                                                           "IDLE_BELOW": IDLE_BELOW}, "timeout": 600},
        "boot": "ide0",
        "login": DOS_LOGIN,
        "marker": "C:\\WSHLAB.TXT",
        "hostname": "-",
        "network": "none: an ne2k_pci NIC (RTL8029) without a DOS driver loaded",
        "net_modes": ["none"],  # no network settings in the guest; --bridge and --vlan for the NIC
        "minutes": 8,  # 7.4 min: install ~79 s, first boot ~281 s (WSHIDLE.COM typed in), --check ~44 s (15 s idle)
        "tested": {"date": "2026-11-20", "packages": PACKAGES_2026_11_20, "with": "--check"},
    },
    "freedos14": {
        "title": "FreeDOS 1.4 from the Floppy Edition (base install, i440fx, SeaBIOS, Pentium, std VGA)",
        "status": "automated",
        "method": "scripted",
        "profile": dict(X86_DOS),
        "disk": {"bus": "ide0", "size": 1, "label": None},
        "media": [{"name": "freedos14-boot.img", "drive": "floppy0"}]
                 # FDI's later prompts name a file, not a disk ("Insert diskette containing file
                 # A:\FREEDOS.024"): the scenario inserts the disks in order (install passes SWAPS)
                 + [{"name": f"freedos14-disk{n}.img", "drive": "floppy0", "at": "scenario"} for n in range(1, 7)],
        "install": {"scenario": "freedos-install.py", "vars": {}, "timeout": 2400},
        "firstboot": {"scenario": "dos-firstboot.py", "vars": {"FLAVOUR": "freedos"}, "timeout": 900},
        "check": {"scenario": "dos-boot-disk.py", "vars": {"VERSION": r"Free(DOS|Com)",
                                                           "IDLE_BELOW": IDLE_BELOW}, "timeout": 600},
        "boot": "ide0",
        "login": DOS_LOGIN,
        "marker": "C:\\WSHLAB.TXT",
        "hostname": "-",
        "network": "none: an ne2k_pci NIC (RTL8029) without a DOS driver loaded",
        "net_modes": ["none"],  # no network settings in the guest; --bridge and --vlan for the NIC
        "minutes": 11,  # 10.3-11.3 min: install ~366 s, first boot ~180-300 s, --check ~35 s
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17, "with": "--check"},
    },
}


# ReactOS 0.4.16 (GPL): the release CD as published (github.com/reactos/reactos/releases, tag
# 0.4.16-release, ReactOS-0.4.16-iso.zip), and the same CD with the lab's answer file in i386/unattend.inf
# instead of the release's sample (answer_media.reactos_unattend, edited in place by
# answer_media.iso_replace: same size, nothing else changed). `lab.py media reactos0416 --convert
# ReactOS-0.4.16-i386.iso` writes it and checks both checksums. The README ("ReactOS") and the DOS
# guide's ReactOS section have the why of each option.
MEDIA.update({
    "ReactOS-0.4.16-i386.iso": {
        "title": "ReactOS 0.4.16 boot CD (i386, release ISO)", "content": "iso", "size": 406847488,
        "sha256": "6f15ca6e1edf5527b8489958d16c54f0da0e7948c305d7c89e74687c6cbf6855",
        "lab": "other-os/reactos/ReactOS-0.4.16-i386.iso"},
    "reactos0416-wshlab.iso": {
        "title": "ReactOS 0.4.16 boot CD with the lab's unattend.inf (from ReactOS-0.4.16-i386.iso)",
        "content": "iso", "size": 406847488,
        "sha256": "215ac517acc28a0b2c99292a88311fa0efdb3ab682471bd431cc1e77cd3de559",
        "lab": "other-os/reactos/reactos0416-wshlab.iso",
        "from": {"name": "ReactOS-0.4.16-i386.iso", "convert": "reactos-unattend"}},
})

# A PC that ReactOS 0.4.16 has drivers for: i440fx with ACPI, IDE (ATA), std VGA (VBE, 1024x768x32 from
# the answer file), an RTL8139 (DHCP by default), PS/2 mouse and keyboard (no USB tablet), no balloon
# (no virtio driver: a device without a driver opens the New Hardware Wizard), TCG like the DOS targets
# (KVM not tried), COM1 for the install's debug log and the logon report. ostype wxp: ReactOS reports
# NT 5.2, and qemu-server keeps the RTC in local time as for Windows. tdf 0: for a Windows ostype
# qemu-server also adds `-rtc driftfix=slew` (ACPI on), and with it ReactOS's setup hung under TCG in
# its HAL before the first screen (the last line on COM1: "STUB Adjustment(Bus 0:ffffffff.0)").
X86_REACTOS = {"ostype": "wxp", "tdf": 0, "machine": "pc", "cpu": "qemu64", "kvm": 0, "memory": 1024,
               "balloon": 0, "tablet": 0, "vga": "std", "net0": "rtl8139", "serial0": "socket",
               "boot": "order=ide0;ide2"}

TARGETS["reactos0416"] = {
    "title": "ReactOS 0.4.16 from its CD, unattended (i440fx, SeaBIOS, std VGA 1024x768, RTL8139)",
    "status": "automated",
    "method": "scripted",
    "profile": dict(X86_REACTOS),
    "disk": {"bus": "ide0", "size": 4, "label": None},
    "media": [{"name": "reactos0416-wshlab.iso", "drive": "ide2"}],
    # the text-mode setup and the graphical second stage run from the answer file; the scenario picks
    # the setup in the CD's boot menu, answers the kernel debugger, and at the desktop types the boot
    # loader's default (no debugger) and the logon report C:\wshlab.cmd (README.md, "ReactOS")
    "install": {"scenario": "reactos-install.py", "vars": {}, "timeout": 3600},
    "firstboot": {"scenario": "reactos-firstboot.py", "vars": {}, "timeout": 900},
    "check": {"scenario": "reactos-boot-disk.py", "vars": {"VERSION": r"(?m)^Version 0\.4\.16-x86 ",
                                                          "IDLE_BELOW": "25"}, "timeout": 900},
    "boot": "ide0",
    "login": {"user": "Administrator", "console": "VGA (noVNC console of VM <vmid>; logs on by itself);"
                                                  " serial0 has the logon report"},
    "marker": "C:\\WSHLAB.TXT",
    "hostname": "reactos",  # ComputerName REACTOS in the answer file (ReactOS shows it in capitals)
    # the answer file on the CD sets them, so other values would need another medium
    "fixed": {"root_password": "the answer file on the CD sets it", "hostname": "the answer file on the CD sets it",
              "user": "not implemented for ReactOS"},
    "network": "none set by the lab: ReactOS takes an address by DHCP on its RTL8139",
    "net_modes": ["none"],
    "minutes": 17,  # 16.4 min: install 580 s, first boot 279 s (the marker typed at ~5 keys/s), --check 93 s
    "tested": {"date": "2026-11-27", "packages": PACKAGES_2026_11_27, "with": "--check"},
}
