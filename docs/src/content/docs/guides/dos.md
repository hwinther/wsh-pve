---
title: DOS under Proxmox VE
description: MS-DOS 6.22 and FreeDOS in a Proxmox VE VM with the WSH packages, from floppies by hand or with the lab, and what DOS gets of the first megabyte under SeaBIOS
---

MS-DOS 6.22 installs from its three Setup floppies into an ordinary x86 VM. The WSH packages add
what makes that comfortable: floppy images as a storage content type, two floppy drives per VM, the
floppy drive in the boot order and live disk swaps (see [Floppy drives](/reference/floppy/)). This
page is the recommended VM, the install by hand and with the lab, and what was measured about the
memory between 640K and 1 MB.

## The VM

| Option | Value | Why |
| --- | --- | --- |
| Machine | `pc` (i440fx) | `isapc` would have no PCI and no option ROMs, but qemu-server doesn't accept it (`machine: isapc` fails the format check). |
| CPU | `pentium` (`486` works too) | Period plausible for DOS 6.22 and enough for HIMEM.SYS and EMM386.EXE (they need a 386). |
| KVM | off (`kvm: 0`) for the lab, on is fine | TCG gives the same timing every run; DOS doesn't need the speed. DOS busy-waits either way; the lab's installs add an idle driver ([Idle](#idle)). |
| Memory | 32 MB, `balloon: 0` | HIMEM.SYS of DOS 6.22 handles up to 64 MB; DOS has no balloon driver. |
| USB tablet | off (`tablet: 0`) | DOS has no USB mouse driver. qemu-server adds the UHCI controller anyway; it has no option ROM. |
| Display | `vga: std` | `cirrus` and `vmware` measured the same for upper memory (each VGA BIOS takes C0000-C9FFF). |
| Disk | IDE, 1 GiB, raw | One FAT16 partition; SeaBIOS translates the geometry for disks above 504 MB. |
| Floppy | `floppy0` with Disk 1, `ro=1` | Read only: the images are shared reference media, and a written image no longer matches its checksum. |
| Boot order | `order=floppy0;ide0` | The floppy first while installing; SETUP's restart boots Disk 1 again. |
| NIC | `ne2k_pci` (unused by the install) | A DOS packet driver exists (RTL8029). Its iPXE option ROM costs 4K of upper memory (below). `ne2k_isa` would cost none but doesn't start, see "Known issues". |

The storage that holds the floppies needs the **Floppy image** content type (it is off on every
storage until enabled; [Floppy drives](/reference/floppy/)):

```sh
pvesm set local --content iso,vztmpl,backup,floppy     # the whole list: it replaces the current one
qm create 130 --name msdos622 --ostype other --machine pc --cpu pentium --kvm 0 --memory 32 --balloon 0 \
  --tablet 0 --vga std --net0 ne2k_pci,bridge=vmbr0 --ide0 local:1,format=raw \
  --floppy0 local:floppy/msdos622-disk1.img,ro=1 --boot 'order=floppy0;ide0'
```

## Installing by hand

Start the VM and open its console. SETUP offers to configure the unallocated disk space (it
partitions, then asks to restart with Disk 1 still in A:), formats C:, confirms date, country and
keyboard, takes `C:\DOS`, and asks for Setup Disk #2 and #3. Swap a disk on the running VM in its
**Hardware** panel or with `qm set 130 --floppy0 local:floppy/msdos622-disk2.img,ro=1`, then press
ENTER. When SETUP asks for the floppy to be removed, `qm set 130 --floppy0 none`, ENTER, and the VM
boots from C:. Then `qm set 130 --boot order=ide0`. Under TCG the whole install takes under a minute.

## Installing with the lab

[Lab install targets](/guides/lab-install/) has the target `msdos622`: it checks the three floppies
by sha256, creates the VM above through the API, drives SETUP on the VGA text screen (read exactly
from the text buffer, not by OCR), swaps the disks when SETUP asks, writes a known `CONFIG.SYS` and
`AUTOEXEC.BAT` (HIMEM, `DOS=HIGH`, no SMARTDRV, the idle driver `C:\DOS\WSHIDLE.COM`, see
[Idle](#idle)) and the marker `C:\WSHLAB.TXT`, and with `--check` boots once more and checks `VER`,
the marker, `MEM` and that the VM idles at the prompt (below 25% of a host core):

```sh
wsh-lab install msdos622 --vmid 130 --check                  # ~7.5 min
wsh-lab install msdos622 --vmid 131 --check --keyboard no    # adds KEYB NO to AUTOEXEC.BAT
```

DOS has no login: the VM's notes say so instead of a password. `freedos14` is the same for FreeDOS 1.4
from its Floppy Edition (seven disks), which is also what the CI test installs.

## Idle

DOS has no idle loop of its own: at the `C:\>` prompt it polls the keyboard and calls INT 28h ("DOS
is idle") in between, so a DOS VM keeps one host core at 100% all the time, under TCG and KVM alike.
An idle driver halts the CPU (`HLT`) while DOS waits; the timer and the keyboard interrupts wake it.

- **MS-DOS 6.22: `WSHIDLE.COM`** (in the repository: `e2e/sparc/dos_tools.py com --name wshidle`,
  142 bytes, 304 bytes resident). A TSR that does `STI; HLT` in INT 28h and in INT 2Fh AX=1680h
  ("release the time slice", which Windows-aware DOS programs call while they wait), then goes on to
  the previous handler. The `msdos622` target types it in with `DEBUG` on the first boot (no file
  transfer needed) as `C:\DOS\WSHIDLE.COM` and loads it from `AUTOEXEC.BAT`. By hand: copy it onto
  the disk, add `C:\DOS\WSHIDLE.COM` (or `LH C:\DOS\WSHIDLE.COM` with EMM386) to `AUTOEXEC.BAT`.
  `MEM` still reports 621K of conventional memory free with it (HIMEM, `DOS=HIGH`).
- **MS-DOS's own `POWER.EXE`** (`DEVICE=C:\DOS\POWER.EXE` in `CONFIG.SYS`) idles as well: it calls
  the APM BIOS, which SeaBIOS has, and halts the CPU there. But it also takes keyboard polls
  (INT 16h AH=01h) for idle time, so a program that polls the keyboard in its main loop, as many games
  do, runs 2.5-10 times slower, with `ADV:MAX` (the default), `ADV:REG` and `ADV:MIN` alike.
  `scenarios/dos-firstboot.py` takes it instead of WSHIDLE with `IDLE=power` (not a `wsh-lab install`
  option).
- **FreeDOS 1.4** idles out of the box: its installer writes `lh fdapm APMDOS` into `FDAUTO.BAT`
  (boot menu entries 1-3, the default is 2). Nothing to add; the `freedos14` check verifies it.

Measured through PVE (TCG, the `msdos622` and `freedos14` VMs, `scenarios/dos-idle.py`): host CPU of
the VM at the prompt over 30-60 s, the BIOS timer (ticks per second at 0040:006C), a typed `ECHO`,
and two busy programs that count loop iterations for five seconds (`BUSY.COM`, and `BUSYK.COM`, which
also polls INT 16h AH=01h in every iteration; `dos_tools.py com`). The busy counts vary by about ±20%
from run to run on the shared lab host; the ranges are over 6 runs (MS-DOS without and with
WSHIDLE, three of them alternating) and 2-3 runs for the others.

| Guest | Idle driver | Host CPU at the prompt | Timer | BUSY (millions / 5 s) | BUSYK (thousands / 5 s) |
| --- | --- | --- | --- | --- | --- |
| MS-DOS 6.22 | none | 100% | 18.1-18.4/s | 1043-1416 | 73-105 |
| MS-DOS 6.22 | `WSHIDLE.COM` | **1.1-1.6%** | 18.1-18.2/s | 1005-1380 | 73-87 |
| MS-DOS 6.22 | `POWER.EXE` (ADV:MAX) | 1.2-1.5% | 18.2-18.4/s | 1106-1337 | **9-20** |
| MS-DOS 6.22 | `POWER.EXE ADV:REG` / `ADV:MIN` | 1.1-1.4% | 18.0-18.2/s | 880-1234 | **12-33** |
| MS-DOS 6.22, EMM386 NOEMS | none | 100% | 18.2/s | 1719 | 86 |
| MS-DOS 6.22, EMM386 NOEMS | `WSHIDLE.COM` | 1.5% | 18.2/s | 1429 | 74 |
| MS-DOS 6.22, EMM386 NOEMS | `POWER.EXE` | 1.4% | 18.4/s | 1857 | 19 |
| FreeDOS 1.4 (JEMMEX) | none (`fdapm` removed) | 100% | 18.2/s | 1622 | 80 |
| FreeDOS 1.4 (JEMMEX) | `FDAPM APMDOS` (as installed) | **1.2%** | 18.2/s | 1887 | 97 |
| FreeDOS 1.4 (JEMMEX) | `WSHIDLE.COM` instead | 1.3% | 18.2/s | 1504 | 94 |

The keyboard answered in every run (the typed `ECHO` came back on the screen), and `HLT`
works under EMM386 and JEMMEX (V86 mode) too. Under KVM the same drivers apply; that was not measured.

## The first megabyte

What DOS 6.22 sees between 640K and 1 MB in this VM, measured with `MEM /D`, `EMM386` and UMASCAN
(a 1993 PC Magazine tool that maps 640K-1M in 2K cells), with SeaBIOS 1.17.0 as shipped in
pve-qemu-kvm 11.1, TCG, 32 MB. SeaBIOS's debug log gave the ROM addresses and the free gap.

**Layout of a stock VM** (std VGA, ne2k_pci):

| Range | What | Writable |
| --- | --- | --- |
| C0000-C9FFF | VGA BIOS (40K) | no |
| CA000-CAFFF | the NIC's iPXE ROM (4K after it shrinks itself) | no |
| CB000-CD7FF | `kvmvapic.bin` (10K, QEMU's APIC helper ROM, always loaded) | yes |
| CD800-E8FFF | free, zero-filled, read only: SeaBIOS's "Space available for UMB" (110K) | no |
| E9000-EFFFF | SeaBIOS's own runtime data (UMASCAN sees E8000-EFFFF as RAM) | **yes** |
| F0000-FFFFF | SeaBIOS | no |

**CONFIG.SYS on the stock VM** (no driver loaded high, so "upper memory" is what DOS could use):

| CONFIG.SYS | Conventional free | Upper memory (UMB) | Largest UMB | DOS usable |
| --- | --- | --- | --- | --- |
| none | 575K | 0 | 0 | yes |
| `HIMEM.SYS`, `DOS=HIGH` | 620K | 0 | 0 | yes |
| + `EMM386.EXE NOEMS`, `DOS=HIGH,UMB` | 617K | 98K | 98K, one block from CF4A | yes |
| + `EMM386.EXE NOEMS HIGHSCAN` | 617K | 98K | 98K | yes |
| + `EMM386.EXE NOEMS I=CE00-E8FF` (the gap) | 617K | 102K | 102K | yes |
| + `EMM386.EXE RAM` | 617K | 34K | 34K; 64K EMS page frame at D800 | yes |
| + `EMM386.EXE RAM I=CE00-E8FF` | 617K | 102K | 102K; no page frame reported | yes |
| + `EMM386.EXE NOEMS I=CE00-EFFF` | - | - | - | **no**: boots, then the keyboard is dead |

**VM variants** (EMM386 NOEMS, `DOS=HIGH,UMB`; HIMEM only gives 620K conventional in every variant):

| VM | Option ROMs (SeaBIOS) | Free gap | UMB, default scan | UMB, `I=` the gap | Needs `args:` |
| --- | --- | --- | --- | --- | --- |
| stock (std VGA, ne2k_pci) | VGA C0000, NIC CA000, vapic CB000 | 110K | 98K | 102K | no |
| `vga: cirrus` / `vga: vmware` | the same | 110K | 98K | 102K | no |
| no NIC | VGA, vapic | 114K | 102K | 106K | no |
| `-global ne2k_pci.romfile=` | VGA, vapic | 114K | 102K | 106K | yes |
| no NIC, `-global apic-common.vapic=off` | VGA only | 124K | 114K | **118K** | yes |
| `machine: pc,legacy-bios-layout=1` (ne2k_pci kept) | VGA only | 124K | 114K | **118K** | no |
| dummy ROM 4K | + CD800 | 106K | 94K | 98K | yes |
| dummy ROM 32K | + CD800 | 78K | 66K | 70K | yes |
| dummy ROM 100K (valid) | + CD800 | 10K | 98K (EMM386 maps over it) | 102K | yes |
| the owner's file (text, not a ROM) | none added | 110K | 98K | 102K | yes |

Every UMB was one contiguous block. Conventional memory is 617K with EMM386 loaded and nothing
moved high; loading drivers high (`DEVICEHIGH`, `LOADHIGH`) is what the UMB is for.

**Recommended:**

- Maximum conventional memory with nothing to load high: `HIMEM.SYS` and `DOS=HIGH` (620K).
- Maximum contiguous UMB with plain PVE options: no NIC (or a NIC only when needed), and

  ```text
  DEVICE=C:\DOS\HIMEM.SYS
  DEVICE=C:\DOS\EMM386.EXE NOEMS I=CD00-E8FF
  DOS=HIGH,UMB
  ```

  for 106K in one block (102K without the `I=`). With a NIC the range starts at CE00 (102K).
- The most with a PVE option: **Legacy BIOS memory layout** (below) drops the NIC's option ROM and
  QEMU's vapic ROM (10K) and keeps the NIC: 114K in one block, 118K with `I=CA00-E8FF`.
- The range to include is the free gap SeaBIOS reports: start one 4K page after the last ROM, end
  at E8FF. Never past E8FF: from E9000 on is SeaBIOS's data.

## The dummy option ROM

An old qemu-devel thread ("memory problem with qemu/seabios", 2012) suggested a 100K dummy option
ROM (`-option-rom dummy.rom`) for a program that misbehaved because SeaBIOS 1.7 left the upper memory
area writable. SeaBIOS changed in 2013 (1.7.4): unused upper memory is read only now, and only its
own data at the top of the E segment stays writable.

- **The original command writes no option ROM under Python 3.**
  `python3 -c 'import sys; sys.stdout.write("\x55\xaa\xc8\xcb\x6e" + "\x00"*(100*1024 - 5))'`
  writes text: Python 3 encodes `"\xaa"` as UTF-8, so the file is 102403 bytes starting
  `55 C2 AA C3 88 C3 8B 6E` and has no `55 AA` signature. SeaBIOS ignores it, so the VM is exactly a
  stock one (measured: the same gap and the same UMB as without it).
- **Written as bytes it is valid** (`C8` = 200 blocks of 512 bytes, `CB` = RETF as the init entry,
  `6E` makes the checksum zero):

  ```sh
  python3 -c 'import sys; sys.stdout.buffer.write(b"\x55\xaa\xc8\xcb\x6e" + b"\x00"*(100*1024 - 5))' > dummy.rom
  ```

  `e2e/sparc/dos_tools.py rom --kb 32 --out dummy32k.rom` writes one of any size with the checksum.
- **A valid dummy ROM never helps.** SeaBIOS puts it right after the other ROMs, inside the free
  gap, and write-protects it like them. Up to 64K (size byte below 0x80) EMM386 recognises it as a
  ROM and the UMB shrinks by exactly its size: 4K gave 94K instead of 98K, 32K gave 66K. At 100K
  (size byte 0xC8) neither takes it for a ROM (UMASCAN's source sign-extends the size byte; EMM386
  behaves the same, by measurement) and EMM386 maps its own RAM over it: the UMB is the stock 98K, as if the ROM weren't there. It makes
  no other area read only or more contiguous, and it doesn't protect SeaBIOS's writable data, which
  is above the gap.

## Legacy BIOS memory layout

The only gains beyond plain options come from dropping ROMs: the NICs' (4K for `ne2k_pci`) and QEMU's
vapic ROM (10K). The WSH qemu-server does both for one VM with a key of `machine`:

```sh
qm set 130 --machine pc,legacy-bios-layout=1
```

In the web UI it is **Hardware > Machine > Advanced > Legacy BIOS memory layout** (x86 VMs only).
qemu-server then adds `romfile=` (no option ROM) to every PCI NIC's `-device` and
`-global apic-common.vapic=off` (the abstract APIC type, so it covers QEMU's `apic` under TCG and
`kvm-apic` under KVM). An ISA NIC (`ne2k_isa`) has no ROM to drop. The rest of the VM stays as it was:
the NIC still works for a DOS packet driver, it only can't network-boot (no iPXE). The API refuses the
key on other architectures and with OVMF (`bios: ovmf`), where the option ROMs are UEFI drivers and
there is no upper memory area to gain. No `args:` and no root rights are needed.

Measured through PVE on the `msdos622` VM (TCG; EMM386 `NOEMS`, `DOS=HIGH,UMB`):

| `machine` | SeaBIOS option ROMs | Free gap | UMB, default scan | UMB, `I=` the gap |
| --- | --- | --- | --- | --- |
| `pc` (stock, ne2k_pci) | VGA C0000, NIC CA000, vapic CB000 | 110K (CD800-E8FFF) | 98K from CF4A | 102K |
| `pc,legacy-bios-layout=1` | VGA C0000 only | 124K (CA000-E8FFF) | 114K from CB4A | 118K (`I=CA00-E8FF`) |

The same as removing the NIC and adding `-global apic-common.vapic=off` by hand (measured side by
side). Under KVM the vapic ROM (`kvmvapic.bin` in `info roms`) is gone with the key as well; the UMB
was measured under TCG only.

## Known issues

- **`ne2k_isa` doesn't start.** qemu-server offers the model but puts the ISA card on the PCI bus:
  `Device 'ne2k_isa' can't go on PCI bus`. Until that is fixed, use `ne2k_pci` (4K of option ROM) or
  no NIC.
- **No per-NIC ROM option in PVE.** `machine: ...,legacy-bios-layout=1` drops the ROM of every NIC
  of the VM (and the vapic ROM); removing only one NIC's ROM still needs
  `args: -global ne2k_pci.romfile=` (root only).
- **EMM386 must not include the top of the E segment.** `I=` up to EFFF lets DOS boot, then the
  keyboard is dead: SeaBIOS's data at E9000-EFFFF was handed out as UMB. Stay within the gap.
