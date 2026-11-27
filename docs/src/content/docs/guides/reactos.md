---
title: ReactOS under Proxmox VE
description: ReactOS 0.4.16 in a Proxmox VE VM with the WSH packages, by hand or unattended with the lab, and what works in it
---

[ReactOS](https://reactos.org/) is an open-source operating system that aims at binary
compatibility with Windows NT 5.2 (Windows Server 2003) programs and drivers. It is GPL, so its
release CD can be used and named here. ReactOS 0.4.16 installs from that CD into an ordinary x86 VM
and runs Win32 programs, our own OpenGL game among them. This page is the VM that works, the install
by hand and with the lab, and what was tried.

## The VM

| Option | Value | Why |
| --- | --- | --- |
| OS type | `wxp` | ReactOS reports NT 5.2; qemu-server keeps the RTC in local time, as Windows expects. |
| Time drift fix | off (`tdf: 0`) | For a Windows OS type qemu-server adds `-rtc driftfix=slew`. With it, ReactOS's setup hung under TCG before its first screen (see "Known issues"). |
| Machine | `pc` (i440fx) | ReactOS has drivers for the PIIX chipset, its IDE controller and ACPI. |
| CPU | `qemu64` | Any x86 model with CMPXCHG8B. |
| KVM | off (`kvm: 0`) for the lab | TCG gives the same timing every run; the setup's two stages take about 4 minutes under TCG. KVM wasn't tried. |
| Memory | 1024 MB, `balloon: 0` | ReactOS has no driver for the virtio balloon; a device without a driver opens the New Hardware Wizard at every logon. |
| USB tablet | off (`tablet: 0`) | The PS/2 mouse works without a driver install. |
| Display | `vga: std` | The VBE driver gives 1024x768 at 32 bits (set by the answer file). `cirrus` and `vmware` came up at 800x600. |
| Disk | IDE (`ide0`), 4 GiB, raw | ReactOS's ATA driver. The setup makes one FAT partition. AHCI and virtio weren't tried. |
| CD-ROM | `ide2` | The install CD. |
| NIC | `rtl8139` | Takes an address by DHCP right after the install; `e1000` works too. |
| Serial | `serial0: socket` | The install's debug log and the lab's logon report. |
| Sound | optional: `AC97` | The AC97 driver installs by itself, and our game's music played. |

```sh
qm create 140 --name reactos --ostype wxp --tdf 0 --machine pc --cpu qemu64 --kvm 0 --memory 1024 --balloon 0 \
  --tablet 0 --vga std --net0 rtl8139,bridge=vmbr0 --serial0 socket --ide0 local:4,format=raw \
  --ide2 local:iso/ReactOS-0.4.16-i386.iso,media=cdrom --boot 'order=ide0;ide2'
```

## Installing by hand

Start the VM and open its console. The CD's boot menu starts the Live environment after 3 seconds;
pick **ReactOS Setup (Text Mode)** instead. The text-mode setup asks for the language, the disk and
the file system, copies the files and reboots. The graphical second stage asks for the name, the
computer name and the Administrator password, and logs on to the desktop. Then
`qm set 140 --ide2 none,media=cdrom --boot order=ide0`.

The first logons may show the New Hardware Wizard for an "Other ACPI device" (QEMU's `fw_cfg`,
`ACPI\QEMU0002`, which has no driver). Cancel it.

## Installing with the lab

[Lab install targets](/guides/lab-install/) has the target `reactos0416`:

```sh
wsh-lab media reactos0416 --convert /path/to/ReactOS-0.4.16-i386.iso   # once: the CD with the answer file
wsh-lab install reactos0416 --vmid 140 --check
```

ReactOS has its own unattended setup: with `UnattendSetupEnabled = yes` in `i386/unattend.inf` on
the CD, the text-mode setup partitions, formats and copies without a question, and the second stage
takes the same answers (computer name `REACTOS`, Administrator password `wshlab`, 1024x768x32). The
release CD has that file with `UnattendSetupEnabled = no`, so `wsh-lab media --convert` writes a copy
of the CD, `reactos0416-wshlab.iso`, with the lab's answer file in its place. Nothing else on the CD
changes: the file is replaced in the sectors it already has, and the tool checks the release CD's
sha256 and the copy's. The answers are on the CD, so `--root-password`, `--hostname` and `--user`
are refused for this target.

The install then needs these things from the lab:

- **The boot menu.** The scenario picks the setup in the CD's menu, which it reads from the VGA text
  screen.
- **The kernel debugger.** The unattended setup makes the installed system boot "ReactOS (RosDbg)"
  with no menu: `/DEBUG /DEBUGPORT=COM1 /KDSERIAL`, as ReactOS's test bot runs it. The scenario
  follows that log on `serial0` to see the setup's progress. When an assertion stops in the
  debugger (one in the cache manager, `!Vacb->Dirty`, stopped the second stage in 1 of 4 installs),
  the scenario answers it on the serial port (`i`, ignore). Without an answer, the guest waits at
  `kdb:>` for good. None of the later installs hit an assertion, so the answer itself is untested.
- **The boot loader's default.** At the desktop the scenario opens `cmd.exe` (Win+R) and makes
  "ReactOS" (no debugger) the default with a 3 second menu, as an interactive install has it, then
  reboots. A boot that prints the debugger's log again means a key got lost, and it types the
  change once more.
- **Keys at the right time.** Right after the first logon ReactOS installs devices and may open the
  New Hardware Wizard; keys typed then got lost. The scenarios wait until the VM idles (below 30% of
  a host core) before they type, and type about 5 keys a second.

The first boot writes `C:\wshlab.cmd` and puts it into the Run key: at each logon it sends `ver`,
the host name, the boot loader's default, the marker and `ipconfig` to COM1, which is free once the
debugger is off. It then writes the marker `C:\WSHLAB.TXT`; both files are read back through COM1
and written again if they differ. The check boots once more and checks that report, a desktop
screenshot (1024x768, not blank), and that the VM idles at the desktop below 25% of a host core.
The VM's description has the login; the report on `serial0` (`qm terminal`) shows each logon.

## What works

Tried on the lab host under TCG with the published packages:

| | Result |
| --- | --- |
| Install | Text-mode setup ~75 s (~2 min through PVE, whose disk cache is `direct`), graphical setup ~100-120 s, desktop ~4-5 min after power-on; `wsh-lab install reactos0416 --check` 16.4 min in all |
| Display | `std`: 1024x768x32 (VBE), Lautus theme; `cirrus` and `vmware`: 800x600 |
| Network | `rtl8139` and `e1000`: DHCP lease, `ping` to the gateway; `ne2k_pci`: a lease; `pcnet`: no address yet when the logon report ran (not looked into) |
| Sound | `AC97`: the driver installs by itself, and wshracer's music reached the host's WAV capture |
| OpenGL | ReactOS's software Mesa (`OpenGL 1.1.0 (Mesa ReactOS SW Implementation)`) |
| Win32 | `WSHRACER.EXE -hostgl` (our 3dfx game, built with `make 3dfx-racer`): its pixel check passed (`-check`, 4 probes), and the autopilot demo ran with sound |
| Idle | 4-6% of a host core at the desktop |
| Power off | `shutdown -s -t 0` powers the VM off (ACPI) |

Not tried: KVM, AHCI and virtio disks, SB16,
more than one CPU, the USB tablet, and Glide (wshracer used OpenGL).

## Known issues

- **`-rtc driftfix=slew` hangs the setup under TCG.** qemu-server adds it for a Windows OS type
  (`wxp`, `w2k`, ...) when ACPI is on, unless `tdf: 0`. With it, the CD's setup stopped in the HAL
  before its first screen: 100% of a host core, and the last line of its debug log on COM1 was
  `(hal/halx86/legacy/bus/bushndlr.c:141) STUB Adjustment(Bus 0:ffffffff.0)`. The same boot without
  it (the lab's own QEMU with each of PVE's other devices: PCI bridges, `vmgenid`, the UHCI
  controller, the PIIX4 power-management globals) reached the setup's screens in 8 seconds. Not
  tried with KVM. Use `tdf: 0`, or OS type `other` with `localtime: 1`.
- **The unattended install leaves the debugger on.** See above: an installed system that boots
  "ReactOS (RosDbg)" with nothing on its serial port hangs at the first assertion. The lab's
  install changes the default. After an unattended install of your own, change `DefaultOS` in
  `C:\freeldr.ini` to `ReactOS`.
- **New Hardware Wizard for QEMU's `fw_cfg`.** No driver exists for `ACPI\QEMU0002`. Cancel the
  wizard; the lab presses Esc.
