#!/usr/bin/env python3
"""Run a fixed list of lab cases (scenario + variables) one after another and summarise them.

    matrix.py smoke --runs /mnt/runs/m1 [--disks /mnt/os/disks] [--iso /mnt/os/iso]
    matrix.py benchdisk --runs /mnt/runs/b1 [--bench /mnt/os/disks/bench-sol26.raw]

Each case runs `lab.py run` in <runs>/<case>/. A case that boots an installed disk gets a sparse copy
of it there (the image in --disks is never booted), deleted again when the case is done, so <runs>
ends up with only the evidence: result.json, index.html, steps.log, screenshots. Prints the summary
as a Markdown table (also written to <runs>/summary.md) and exits 1 if any case failed.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# name -> [(case, scenario, installed disk or None, install CD or None, variables)]
# The installed disks (End User installs by solaris-install-serial.py on SS-5) and the CD.
SOL26, SOL251 = "sol26-enduser-installed.raw", "sol251-enduser-installed.raw"
SOL26PMC = "sol26-enduser-pmc-installed.raw"  # SOL26 + the pmc driver (README: "Idle")
SUNOS414 = "sunos414-installed.raw"  # Quick Install, Programmer set (README: "SunOS 4.1.4")
SUNOS = {"PROMPT": "login:", "BUSY": "dd if=/dev/zero of=/dev/null count=20000"}
NETBSD111 = "netbsd111-installed.raw"  # sysinst Minimal installation (README: "Idle")
# The same End User install on SS-10 and SS-20 (each machine needs its own install), the last one with
# the Sun SS-20 PROM. That PROM only runs with -cpu TI-SuperSparc-40/50/60 (submodules/SPARC.md).
SOL26SS10, SOL26SS20 = "sol26-enduser-ss10-installed.raw", "sol26-enduser-ss20-installed.raw"
SOL26SS20PROM = "sol26-enduser-ss20prom-installed.raw"
SS20PROM = {"MACHINE": "SS-20", "BIOS": "ss20_v2.25_rom", "CPU": "TI-SuperSparc-50"}
CD26, CD251 = "solaris_2.6_598_sparc.iso", "solaris_2.5.1_1197.iso"
SOLARIS_IDLE = {"TRACE": "sparc_solaris_idle_match", "CPU_BELOW": "10"}
SOLARIS_SMP_IDLE = {"TRACE": "sparc_solaris_idle_mp_match", "CPU_BELOW": "20"}
# The sparc32 profiles (submodules/SPARC.md, "Supported profiles") and the 2.6 disk installed on each
DISPLAY_PROFILES = [("openbios-ss5", {}), ("ss5bin-ss5", {"BIOS": "ss5.bin"}),
                    ("openbios-ss10", {"MACHINE": "SS-10"}), ("openbios-ss20", {"MACHINE": "SS-20"}),
                    ("ss20prom-ss20", SS20PROM)]
DISPLAY_DISKS = [SOL26, SOL26, SOL26SS10, SOL26SS20, SOL26SS20PROM]
BENCH = {"DISK2": "@bench"}  # the bench disk (--bench), on target 4 read only (README: "The bench disk")
MATRICES = {
    "smoke": [
        ("sol26-disk-openbios-ss5", "solaris-boot-disk.py", SOL26, None, {}),
        ("sol251-disk-ss5bin-ss5", "solaris-boot-disk.py", SOL251, None, {"BIOS": "ss5.bin"}),
        ("sol26-cd-openbios-ss5", "solaris-boot-cd.py", None, CD26, {}),
    ],
    # SS-10/SS-20: the install CDs, and the disks installed on these machines (an SS-5 disk doesn't
    # boot there: Solaris finds neither c0t3d0s6 nor le0, can't mount /usr and halts). 512 MB is the
    # most Solaris 2.6 boots with. The CD reaches the installer with 2 and 4 CPUs; the installed 2.6
    # with more than one CPU is in the smp matrix (it needs pve-qemu patch 0019).
    # The 2.6 CD on SS-20 with one CPU and 256 MB sometimes stops in its idle loop after "Configuring
    # devices..." (about 1 boot in 6, OpenBIOS and Sun PROM alike).
    "machines": [
        ("sol26-cd-openbios-ss10", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-10"}),
        ("sol26-cd-openbios-ss10-512m", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-10", "MEM": "512"}),
        ("sol26-cd-openbios-ss20", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20"}),
        ("sol26-cd-openbios-ss20-512m", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20", "MEM": "512"}),
        ("sol26-cd-openbios-ss20-smp2", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20", "SMP": "2"}),
        ("sol26-cd-openbios-ss20-smp4", "solaris-boot-cd.py", None, CD26, {"MACHINE": "SS-20", "SMP": "4"}),
        ("sol26-cd-ss20prom-ss20-512m", "solaris-boot-cd.py", None, CD26, {**SS20PROM, "MEM": "512"}),
        ("sol251-cd-openbios-ss20", "solaris-boot-cd.py", None, CD251, {"MACHINE": "SS-20", "CDROM_AS": "hd"}),
        ("sol251-cd-ss20prom-ss20", "solaris-boot-cd.py", None, CD251, {**SS20PROM, "CDROM_AS": "hd"}),
        ("sol26-disk-openbios-ss10", "solaris-boot-disk.py", SOL26SS10, None, {"MACHINE": "SS-10"}),
        ("sol26-disk-openbios-ss20", "solaris-boot-disk.py", SOL26SS20, None, {"MACHINE": "SS-20"}),
        ("sol26-disk-openbios-ss20-512m", "solaris-boot-disk.py", SOL26SS20, None, {"MACHINE": "SS-20", "MEM": "512"}),
        ("sol26-disk-ss20prom-ss20", "solaris-boot-disk.py", SOL26SS20PROM, None, SS20PROM),
    ],
    # bench.py: the same jobs on SS-5 and SS-20 (one CPU); the numbers go to result.json. Only
    # meaningful on an otherwise idle host. The disks are fresh installs, so boot_s includes the
    # first-boot questions.
    "bench": [
        ("bench-sol26-openbios-ss5", "bench.py", SOL26, None, {}),
        ("bench-sol26-openbios-ss20", "bench.py", SOL26SS20, None, {"MACHINE": "SS-20"}),
        ("bench-sol26-ss20prom-ss20", "bench.py", SOL26SS20PROM, None, SS20PROM),
    ],
    # bench-disk.py: the bench disk's Dhrystone, Whetstone, Hanoi, nbench and lmbench on every machine
    # and firmware, one CPU, 256 MB, Solaris 2.6, and 2.5.1 on SS-5; the le0 tests over QEMU user
    # networking (bench-disk.py's NET default). Only meaningful on an otherwise idle host; ~10-12 min
    # a case (fresh disks: the first boot asks its questions).
    "benchdisk": [
        ("benchdisk-sol26-openbios-ss5", "bench-disk.py", SOL26, None, BENCH),
        ("benchdisk-sol26-ss5bin-ss5", "bench-disk.py", SOL26, None, {**BENCH, "BIOS": "ss5.bin"}),
        ("benchdisk-sol26-openbios-ss10", "bench-disk.py", SOL26SS10, None, {**BENCH, "MACHINE": "SS-10"}),
        ("benchdisk-sol26-openbios-ss20", "bench-disk.py", SOL26SS20, None, {**BENCH, "MACHINE": "SS-20"}),
        ("benchdisk-sol26-ss20prom-ss20", "bench-disk.py", SOL26SS20PROM, None, {**BENCH, **SS20PROM}),
        ("benchdisk-sol251-ss5bin-ss5", "bench-disk.py", SOL251, None, {**BENCH, "BIOS": "ss5.bin"}),
    ],
    # smp-soak.py: Solaris 2.6 with 2 and 4 CPUs (OpenBIOS, the only firmware that starts the other
    # CPUs) under load for SOAK seconds, every CPU on-line and busy, plus the speed-up of a parallel
    # job. Needs a package with pve-qemu patch 0019: before it, 2.6 hung within minutes with more
    # than one CPU (submodules/SPARC.md, "SMP"). Not single-threaded TCG: there every cross-call
    # waits for the other vCPU's time slice and the boot alone takes most of an hour.
    "smp": [
        ("smp-sol26-openbios-ss20-2cpu", "smp-soak.py", SOL26SS20, None,
         {**BENCH, "MACHINE": "SS-20", "SMP": "2", "SOAK": "600"}),
        ("smp-sol26-openbios-ss20-4cpu", "smp-soak.py", SOL26SS20, None,
         {**BENCH, "MACHINE": "SS-20", "SMP": "4", "SOAK": "600"}),
        ("smp-sol26-openbios-ss10-2cpu", "smp-soak.py", SOL26SS10, None,
         {**BENCH, "MACHINE": "SS-10", "SMP": "2", "SOAK": "600"}),
    ],
    # cg3 sizes (needs a package with the cg3 patches): OpenBIOS banner and the 2.6 disk to its login
    # prompt with the console on the framebuffer, each screenshot checked for the size; the Sun PROM
    # stays at 1024x768.
    "display": [
        ("cg3-ss5bin-1024x768", "cg3-display.py", None, None, {"BIOS": "ss5.bin"}),
        *[(f"sol26-disk-openbios-cg3-{res}", "cg3-display.py", SOL26, None, {"RES": res})
          for res in ("1024x768", "1152x900", "1280x1024", "1600x1200", "1920x1080")],
        # TCX (fb-display.py, submodules/SPARC.md "cg3 and TCX"): the banner at depth 8 and 24 with every
        # profile's firmware, the cg3 banner on SS-10/SS-20, and a 2.6 installed without a TCX (no
        # SUNWtcx): console through the PROM, no X
        *[(f"tcx{d}-{name}", "fb-display.py", None, None, {"VGA": "tcx", "RES": f"1024x768x{d}", **extra})
          for d in (8, 24) for name, extra in DISPLAY_PROFILES],
        *[(f"cg3-{name}", "fb-display.py", None, None, {"VGA": "cg3", **extra})
          for name, extra in DISPLAY_PROFILES if not name.endswith("ss5")],
        ("sol26-disk-openbios-tcx-nodriver-ss5", "fb-display.py", SOL26, CD26,
         {"VGA": "tcx", "PREPARE": "1", "PKGS": "", "EXPECT": "console", "DRIVER_EXPECT": "Can.t find driver",
          "XERR_EXPECT": "unknown type|Error loading module"}),
    ],
    # The 2.6 disks into the CDE desktop on TCX (depth 8 and 24) and cg3: PREPARE adds the TCX packages
    # and a ttya login first, then dtlogin, root's CDE session, the depth, the keyboard, idle CPU.
    # ~9 min a case. Left out: TCX 24 under ss5.bin (QEMU stops: TCX's ROM describes an 8-bit TCX
    # under a Sun PROM) and the SS-20 PROM (Solaris panics with any framebuffer console).
    "display-x": [
        (f"sol26-x-{vga}{d if vga == 'tcx' else ''}-{name}", "fb-display.py", disk, CD26,
         {"VGA": vga, **({"RES": f"1024x768x{d}"} if vga == "tcx" else {}), "PREPARE": "1", "X": "1",
          "DEPTH": str(d), "INPUT": "1", "IDLE": "60", **extra})
        for vga, d in (("tcx", 8), ("tcx", 24), ("cg3", 8))
        for (name, extra), disk in zip(DISPLAY_PROFILES, DISPLAY_DISKS)
        if name != "ss20prom-ss20" and not (d == 24 and name == "ss5bin-ss5")
    ],
    # Host CPU use of an idle guest (needs a package with the idle patches, submodules/SPARC.md):
    # Solaris 2.5.1 and 2.6 are halted in their idle loop by the solaris-idle machine option (on by
    # default), on SS-5 and SS-20; with it off, 2.6 with the pmc driver still idles through the APC
    # and without it the CPU spins.
    "idle": [
        ("sol26-idle-ss5", "idle.py", SOL26, None, {**SOLARIS_IDLE, "TRACE_EXPECT": r"Solaris idle loop \(2\.6"}),
        ("sol26-noidle-spins-ss5", "idle.py", SOL26, None, {"MACHINE": "SS-5,solaris-idle=off", "CPU_ABOVE": "80"}),
        ("sol26-pmc-idle-ss5", "idle.py", SOL26PMC, None,
         {"CHECK": "modinfo | grep pmc", "CHECK_EXPECT": r"pmc \(Power Management", "CPU_BELOW": "10"}),
        ("sol26-pmc-noidle-apc-ss5", "idle.py", SOL26PMC, None,
         {"MACHINE": "SS-5,solaris-idle=off", "CHECK": "modinfo | grep pmc",
          "CHECK_EXPECT": r"pmc \(Power Management", "CPU_BELOW": "10"}),
        ("sol26-idle-ss20", "idle.py", SOL26SS20, None,
         {**SOLARIS_IDLE, "MACHINE": "SS-20", "TRACE_EXPECT": r"Solaris idle loop \(2\.6"}),
        ("sol26-noidle-spins-ss20", "idle.py", SOL26SS20, None, {"MACHINE": "SS-20,solaris-idle=off", "CPU_ABOVE": "80"}),
        # More than one CPU: the multiprocessor idle loop, halted by solaris-smp-idle (on by default)
        ("sol26-idle-ss20-2cpu", "idle.py", SOL26SS20, None,
         {**SOLARIS_SMP_IDLE, "MACHINE": "SS-20", "SMP": "2", "TRACE_EXPECT": r"multiprocessor idle loop \(2\.6"}),
        ("sol26-idle-ss20-4cpu", "idle.py", SOL26SS20, None,
         {**SOLARIS_SMP_IDLE, "MACHINE": "SS-20", "SMP": "4", "TRACE_EXPECT": r"multiprocessor idle loop \(2\.6"}),
        ("sol26-noidle-spins-ss20-2cpu", "idle.py", SOL26SS20, None,
         {"MACHINE": "SS-20,solaris-smp-idle=off", "SMP": "2", "CPU_ABOVE": "150"}),
        ("sol251-idle-ss5", "idle.py", SOL251, None,
         {**SOLARIS_IDLE, "BIOS": "ss5.bin", "TRACE_EXPECT": r"Solaris idle loop \(2\.5\.1"}),
        # SunOS 4.1.4: halted in its idle loop by the sunos-idle machine option (on by default). Its dd
        # takes ~5 ms a block, so a tenth of the count.
        ("sunos414-idle-ss5", "idle.py", SUNOS414, None,
         {**SUNOS, "TRACE": "sparc_sunos_idle_match", "TRACE_EXPECT": "SunOS idle loop", "CPU_BELOW": "10"}),
        ("sunos414-noidle-spins-ss5", "idle.py", SUNOS414, None,
         {**SUNOS, "MACHINE": "SS-5,sunos-idle=off", "CPU_ABOVE": "80"}),
        # NetBSD 11.1's apc driver writes register 0 only, as before the APC got its 16 bytes
        ("netbsd111-idle-ss5", "idle.py", NETBSD111, None,
         {"PROMPT": "login:", "CHECK": "dmesg | grep apc", "CHECK_EXPECT": "apc0 at", "CPU_BELOW": "10"}),
    ],
    # Stop-A (L1-A) on running guests (stop-a.py, two rounds each): QEMU stays up, the guest stops at
    # the firmware prompt and `go` resumes it; `boot` there resets and boots again. Needs
    # openbios/patches/0008 (before it OpenBIOS powered the machine off). At 1152x900 Solaris's X
    # server doesn't start, so the console login prompt stays on the screen; at 1024x768 dtlogin.
    # NetBSD's GENERIC kernel enters ddb instead of the firmware. The chord in the wrong order is
    # ignored. A break on a ttya console (QMP chardev-send-break) does the same as Stop-A; it needs
    # pve-qemu wsh/0141 (before it the ESCC never ended a break and the guest hung in its serial
    # interrupt, submodules/SPARC.md, "Stop-A").
    "stopa": [
        ("stopa-sol26-console-openbios-ss5", "stop-a.py", SOL26, None, {"RES": "1152x900"}),
        ("stopa-sol26-dtlogin-openbios-ss5", "stop-a.py", SOL26, None, {"AT": "dtlogin"}),
        ("stopa-sol26-boot-openbios-ss5", "stop-a.py", SOL26, None, {"RES": "1152x900", "RESUME": "boot", "REPEAT": "1"}),
        ("stopa-sol26-reversed-openbios-ss5", "stop-a.py", SOL26, None, {"RES": "1152x900", "KEYS": "a stop", "EXPECT": "none"}),
        ("stopa-sol26-console-openbios-ss10", "stop-a.py", SOL26SS10, None, {"MACHINE": "SS-10", "RES": "1152x900"}),
        ("stopa-sol26-console-openbios-ss20", "stop-a.py", SOL26SS20, None, {"MACHINE": "SS-20", "RES": "1152x900"}),
        ("stopa-sunos414-openbios-ss5", "stop-a.py", SUNOS414, None, {"GUEST": "sunos"}),
        ("stopa-netbsd111-ddb-openbios-ss5", "stop-a.py", NETBSD111, None, {"GUEST": "netbsd", "EXPECT": "db.", "RESUME": "c"}),
        ("stopa-firmware-prompt-openbios-ss5", "stop-a.py", None, None, {"GUEST": "none", "EXPECT": "none"}),
        ("stopa-sol26-break-openbios-ss5", "stop-a.py", SOL26, None, {"CONSOLE": "serial", "BREAK": "1"}),
        ("stopa-sunos414-break-openbios-ss5", "stop-a.py", SUNOS414, None,
         {"GUEST": "sunos", "CONSOLE": "serial", "BREAK": "1", "SHELL": "0"}),
        ("stopa-netbsd111-break-ddb-openbios-ss5", "stop-a.py", NETBSD111, None,
         {"GUEST": "netbsd", "CONSOLE": "serial", "BREAK": "1", "SHELL": "0", "EXPECT": "db>", "RESUME": "c"}),
        ("stopa-break-firmware-prompt-openbios-ss5", "stop-a.py", None, None,
         {"GUEST": "none", "CONSOLE": "serial", "BREAK": "1", "EXPECT": "none"}),
    ],
}

# sparc64 (sun4u, OpenBIOS, scenarios/_sparc64.py): disk and CD-ROM on the built-in IDE, sunhme, serial
# console unless stated (submodules/SPARC.md, "sparc64"). The installed disk is in /mnt/os/disks on
# the lab host: run with --disks /mnt/os/disks. The network cases need outside access (NET=user).
NB111_64 = "netbsd111-sparc64-installed.raw"  # netbsd-install-sparc64.py with the defaults
NB111_CD64, NB93_CD64 = "other-os/NetBSD-11.1-sparc64.iso", "other-os/NetBSD-9.3-sparc64.iso"
OB80_CD64, DEB12_CD64 = "other-os/openbsd8.0/install80.iso", "other-os/debian-12.0.0-sparc64-NETINST-1.iso"
NB_NET64 = {"NET": "user",
            "COMMANDS": "dhcpcd -w -1 2>&1 | tail -1; ifconfig -a | grep 'inet ' ;; ftp -4 -o /tmp/r "
                        "http://cdn.netbsd.org/pub/NetBSD/README >/dev/null 2>&1; test -s /tmp/r && echo FETCHED",
            "CHECK": r"inet 10\.0\.2\.15 ;; FETCHED"}
MATRICES["sparc64"] = [
    ("nb111-cd-sparc64", "sparc64-boot-cd.py", None, NB111_CD64, {"GUEST": "netbsd"}),
    ("nb93-cd-sparc64", "sparc64-boot-cd.py", None, NB93_CD64, {"GUEST": "netbsd"}),
    ("ob80-cd-sparc64", "sparc64-boot-cd.py", None, OB80_CD64, {"GUEST": "openbsd"}),
    ("deb12-cd-sparc64", "sparc64-boot-cd.py", None, DEB12_CD64, {"GUEST": "debian"}),
    # -vga std with OpenBIOS's VGA driver; the keyboard is the i8042 PS/2 one (QMP send-key): on the
    # framebuffer sysinst asks no terminal type, so pick German in its first menu and look for it
    ("nb111-cd-vga-sparc64", "sparc64-boot-cd.py", None, NB111_CD64,
     {"GUEST": "netbsd", "VGA": "std", "CONSOLE": "fb", "EXPECT": "Installation auf Deutsch", "TYPE": "b\r",
      "TYPE_EXPECT": "Festplatte|installieren"}),
    ("nb111-install-sparc64", "netbsd-install-sparc64.py", None, NB111_CD64, {}),
    ("nb111-disk-sparc64", "sparc64-boot-disk.py", NB111_64, None, {"GUEST": "netbsd", "BOOTS": "2", **NB_NET64}),
    # virtio-net-pci as the NIC and a virtio-blk disk (the CD as a read-only disk): NetBSD drives both;
    # OpenBIOS doesn't boot from virtio-blk, so the system disk stays on IDE
    ("nb111-virtio-sparc64", "sparc64-boot-disk.py", NB111_64, NB111_CD64,
     {"GUEST": "netbsd", "NIC": "virtio-net-pci", "CD_BUS": "virtio-blk", **NB_NET64,
      "COMMANDS": NB_NET64["COMMANDS"] + " ;; dd if=/dev/rld0c of=/dev/null bs=64k count=160 2>&1 | tail -1",
      "CHECK": NB_NET64["CHECK"] + " ;; bytes transferred"}),
    # NetBSD/sparc64 spins in its idle loop on sun4u (nothing lets it stop the CPU); pve-qemu wsh/0042
    # halts it there (idle-halt, on by default): below 10% of a core, the loop recognised; with
    # idle-halt=off it spins, above 80%. Needs a package with wsh/0042-0044
    ("nb111-idle-sparc64", "sparc64-idle.py", NB111_64, None,
     {"GUEST": "netbsd", "WAIT": "pkill makemandb; sleep 2", "CPU_BELOW": "10", "TRACE": "sparc64_idle_match",
      "TRACE_EXPECT": "NetBSD idle loop"}),
    ("nb111-noidle-spins-sparc64", "sparc64-idle.py", NB111_64, None,
     {"GUEST": "netbsd", "WAIT": "pkill makemandb; sleep 2", "MACHINE": "sun4u,idle-halt=off", "CPU_ABOVE": "80"}),
    # reboot from the guest: the firmware's boot service resets the machine (openbios-sparc64 patch
    # 0030, pve-qemu-kvm 11.1.3-4+wsh3 or later; before it the boot service returned and the machine
    # didn't reset), the banner comes back in the same QEMU process and the disk boots to login: again, twice.
    # The second case passes a boot string (reboot -- netbsd): the firmware drops it and boots its
    # boot device again (submodules/SPARC.md, "The firmware reboot on sun4u"), so this only checks
    # that a reboot with one comes back too
    ("nb111-reboot-sparc64", "sparc64-reboot.py", NB111_64, None, {"GUEST": "netbsd", "REBOOTS": "2"}),
    ("nb111-reboot-bootstr-sparc64", "sparc64-reboot.py", NB111_64, None,
     {"GUEST": "netbsd", "REBOOT": "reboot -- netbsd", "REBOOTS": "1"}),
]

# Solaris 10 on sun4u: NEEDS THE SUN DVD on the lab host (/mnt/os/iso/sol-10-u11-ga-sparc-dvd.iso,
# Oracle's Solaris 10 1/13 SPARC DVD; Sun software, never in the repository). Its installer with the
# package's openbios-sparc64 and QEMU: the IDE disk attaches as dad0 without "Interrupt not seen after
# set_features" (pve-qemu wsh/0021), the language and terminal questions are answered on ttya
# (openbios/patches/0009) and the installer's first screen comes up. Needs the package built with
# openbios-sparc64; with QEMU's image the kernel stops at "no nucleus hblk8 to allocate".
SOL10_DVD = "sol-10-u11-ga-sparc-dvd.iso"
# The installed disk is solaris10-install-sparc64.py's (Sun software too: only on the lab host, in
# --disks), booted to the login prompt; the network check is the DHCP lease on hme0 and a ping of the
# user network's gateway.
SOL10_64 = "sol10-sun4u-installed.raw"
SOL10_NET = {"NET": "user", "TIMEOUT": "1500",
             "COMMANDS": "uname -a ;; echo | format ;; ifconfig hme0 ;; ping 10.0.2.2",
             "CHECK": r"SunOS \S+ 5\.10 ;; c0t0d0 ;; inet 10\.0\.2\.15 ;; is alive"}
MATRICES["solaris10"] = [
    ("sol10-cd-sparc64", "sparc64-boot-cd.py", None, SOL10_DVD, {"GUEST": "solaris10", "MEM": "1024"}),
    ("sol10-disk-sparc64", "sparc64-boot-disk.py", SOL10_64, None, {"GUEST": "solaris10", "MEM": "1024", **SOL10_NET}),
]
# The install itself (~80 min): not part of any scheduled run; needs --timeout 9000 (default 3600)
MATRICES["solaris10-install"] = [
    ("sol10-install-sparc64", "solaris10-install-sparc64.py", None, SOL10_DVD, {}),
]

# Left behind by a run but not evidence: the guest disk, QEMU's sockets, the display refresh buffer,
# the frames of the framebuffer video (lab.py removes them once fb.webm is encoded). The recordings
# (serial.cast, serial.fast.cast, fb.webm, fb.vtt) are evidence and stay.
LEFTOVERS = ("disk.raw", "*.sock", "_refresh.ppm", "_fb_poll.png", "_frames")

# bench-disk.py metrics that aren't benchmark results (they stay in the Status column)
BENCH_META = ("boot_s", "run_s", "run_cpu_pct", "cpus", "mem_mb", "load1_start", "load1_end")


def run_case(name, scenario, disk, iso, variables, a):
    out = os.path.join(a.runs, name)
    os.makedirs(out, exist_ok=True)
    if variables.get("DISK2") == "@bench":
        variables = {**variables, "DISK2": a.bench}
        if not os.path.isfile(a.bench):
            res = {"code": 1, "status": f"bench disk {a.bench} doesn't exist (--bench)", "elapsed": 0}
            print(f"=== {name}: {res['status']}", flush=True)
            return res
    cmd = [sys.executable, os.path.join(HERE, "lab.py"), "run", os.path.join(HERE, "scenarios", scenario),
           "--out", out]
    if disk:
        copy = os.path.join(out, "disk.raw")
        subprocess.run(["cp", "--sparse=always", os.path.join(a.disks, disk), copy], check=True)
        cmd += ["--var", f"DISK={copy}"]
    if iso:
        cmd += ["--var", f"ISO={os.path.join(a.iso, iso)}"]
    cmd += [x for k, val in variables.items() for x in ("--var", f"{k}={val}")]
    print(f"=== {name}: {' '.join(cmd)}", flush=True)
    t0, code = time.time(), 3
    try:
        with open(os.path.join(out, "lab.log"), "w", encoding="utf-8") as log:
            code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout).returncode
        res = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    except subprocess.TimeoutExpired:
        res = {"code": 1, "status": f"case timed out after {a.timeout}s"}
    except (OSError, ValueError) as e:
        res = {"code": code or 3, "status": f"no result.json ({e})"}
    finally:
        for pattern in LEFTOVERS:
            for p in glob.glob(os.path.join(out, pattern)):
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
    res.setdefault("elapsed", round(time.time() - t0, 1))
    print(f"=== {name}: {res['status'].splitlines()[0]} ({res['elapsed']}s)", flush=True)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("matrix", choices=sorted(MATRICES))
    p.add_argument("--runs", required=True, help="output directory, one subdirectory per case")
    p.add_argument("--disks", default="/mnt/os/disks", help="installed disk images (read only)")
    p.add_argument("--iso", default="/mnt/os/iso", help="install CDs (read only)")
    p.add_argument("--bench", default="/mnt/os/disks/bench-sol26.raw", help="the bench disk (read only)")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per case")
    a = p.parse_args()

    rows, failed, bench = [], 0, {}
    for name, scenario, disk, iso, variables in MATRICES[a.matrix]:
        res = run_case(name, scenario, disk, iso, variables, a)
        failed += res["code"] != 0
        vs = " ".join(f"{k}={v}" for k, v in variables.items()).replace("|", "\\|")
        status = res["status"].splitlines()[0][:120].replace("|", "\\|")
        metrics = res.get("metrics") or {}
        if scenario == "bench-disk.py":  # the BENCH values go to the comparison table below
            bench[name] = {k: val for k, val in metrics.items() if k not in BENCH_META}
            metrics = {k: val for k, val in metrics.items() if k in BENCH_META}
        if metrics:
            status += " (" + ", ".join(f"{k} {val}" for k, val in metrics.items()) + ")"
        rows.append(f"| {name} | {f'`{scenario}` {vs}'.strip()} | {'pass' if res['code'] == 0 else 'FAIL'} | "
                    f"{res['elapsed']:.0f}s | {status} |")
    table = "\n".join([f"### sparc lab: {a.matrix} ({len(rows) - failed}/{len(rows)} passed)", "",
                       "| Case | Scenario | Result | Time | Status |",
                       "| --- | --- | --- | --- | --- |", *rows])
    if any(bench.values()):  # one row per benchmark, one column per case
        names = list(dict.fromkeys(k for m in bench.values() for k in m))
        table += "\n\n| Benchmark | " + " | ".join(bench) + " |\n|" + " --- |" * (len(bench) + 1)
        for k in names:
            table += f"\n| {k} | " + " | ".join(f"{m[k]:g}" if k in m else "" for m in bench.values()) + " |"
    print("\n" + table)
    with open(os.path.join(a.runs, "summary.md"), "w", encoding="utf-8") as f:
        f.write(table + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
