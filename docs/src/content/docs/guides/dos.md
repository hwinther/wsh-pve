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
| Display | `vga: std` (`std,retrace=precise` for games) | `cirrus` and `vmware` measured the same for upper memory (each VGA BIOS takes C0000-C9FFF). Some games need the precise retrace, see [VGA retrace](#vga-retrace-games). |
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

## VGA retrace (games)

Wolfenstein 3D starts, switches to mode 13h and stays on a black screen. It waits on the VGA input
status register (port 3DAh) for "display enabled, not in vertical retrace". QEMU's default retrace
emulation (`dumb`) flips both bits on every read, so the two never come together. QEMU's precise
emulation reports them with a real CRT's timing. The WSH qemu-server sets it per VM:

```sh
qm set 130 --vga std,retrace=precise
```

In the web UI: **Hardware > Display > VGA retrace: Precise (DOS games)**. qemu-server accepts it with
`std`, `cirrus`, `vmware`, `qxl` and `virtio` (the [display reference](/reference/display/#vga-retrace)),
on x86 only; it was tried with `std` here. No `args:` and no root rights are needed.

Measured through PVE (TCG, an MS-DOS 6.22 VM with the game on D:, sb16-adlib-pcspk):

| `vga` | QEMU command | After `WOLF3D` (60 s, keys pressed at 15, 22, 30 and 40 s) |
| --- | --- | --- |
| `std` | `-device VGA` | mode 13h, black for the whole minute: 2 distinct screens (the prompt and black) |
| `std,retrace=precise` | `-vga none,retrace=precise -device VGA` | the title and menu screens: 12 distinct screens, the last change at 57 s |

In the same lab study on plain QEMU, DOOM, DOOM II, Duke Nukem 3D, Dune, Dune II, Commander Keen 1
and 4 and Leisure Suit Larry 1 ran with the default retrace as well as with the precise one. The
Incredible Machine 1 and 2 stayed on their first screen with both: a different problem.

## Memory profiles

No single `CONFIG.SYS` suits every DOS program: protected-mode games want XMS and no EMS frame in
the way, older ones want EMS, real-mode ones want every K of conventional memory, and a few DOS
extenders refuse to start under EMM386 at all. Four profiles cover them. The text below is for a VM
without a NIC (the free gap starts at CD800; with `ne2k_pci` start the ranges at CE00) and with
QEMU's Sound Blaster 16 (`audio0` or `args: -device sb16`), and assumes `WSHIDLE.COM` in `C:\DOS`
([Idle](#idle)).

**Full** (XMS and upper memory, no EMS): DOS/4GW and other protected-mode games such as Doom and
Duke Nukem 3D, and most programs.

```text
DEVICE=C:\DOS\HIMEM.SYS /TESTMEM:OFF
DEVICE=C:\DOS\EMM386.EXE NOEMS I=CD00-E8FF
DOS=HIGH,UMB
FILES=40
BUFFERS=20
STACKS=9,256
LASTDRIVE=Z
SHELL=C:\COMMAND.COM C:\ /E:1024 /P
```

```text
@ECHO OFF
PROMPT $P$G
PATH C:\DOS
SET BLASTER=A220 I5 D1 H5 T6
LH C:\DOS\WSHIDLE.COM
```

Load CD-ROM, mouse and keyboard drivers with `DEVICEHIGH=` and `LH` as well.

**EMS** (a page frame at D800 and upper memory around it): games that want expanded memory (The
Incredible Machine 2, Dune, King's Quest VII). The same as Full except the EMM386 line:

```text
DEVICE=C:\DOS\EMM386.EXE RAM 4096 FRAME=D800 I=CD00-D7FF I=E800-E8FF
```

Set the frame and the `I=` ranges around it explicitly. With `I=` over the whole gap, EMM386 finds
no room for a frame and quietly has no EMS at all: `MEM` shows no expanded memory, and a game that
needs it says it hasn't enough memory.

**Maximum conventional** (HIMEM only, nothing else loaded): real-mode games that need the most
conventional memory (Commander Keen, Leisure Suit Larry, Dune II):

```text
DEVICE=C:\DOS\HIMEM.SYS /TESTMEM:OFF
DOS=HIGH
```

with the same `FILES`/`BUFFERS`/`SHELL` lines, and only `SET BLASTER` and `C:\DOS\WSHIDLE.COM` in
`AUTOEXEC.BAT`.

**No EMM386** (HIMEM, drivers low): DOS extenders that refuse V86 mode. Like Maximum conventional,
with the drivers loaded low (`DEVICE=`, no `LH`).

`BLASTER=A220 I5 D1 H5 T6` is QEMU's SB16: port 220h, IRQ 5, 8-bit DMA 1, 16-bit DMA 5, type 6. QEMU
has no MPU-401, so no `P330`. MS-DOS 6's startup menu can hold all four in one `CONFIG.SYS`
(`[MENU]`, one block per profile, `GOTO %CONFIG%` in `AUTOEXEC.BAT`);
`e2e/sparc/dos_profiles.py show --flavour msdos --menu` prints one. FreeDOS 1.4's own startup menu
already has entries like Full (1), a compatible JEMMEX (2) and EMS with JEMM386 (3);
`dos_profiles.py show --flavour freedos` prints the four profiles for FreeDOS (JEMMEX `NOEMS`,
JEMMEX `FRAME=D800`, HIMEMX only, HIMEMX with the drivers low).

### Trying profiles with the lab

`e2e/sparc/dos_profiles.py` keeps the profiles as data and tries them on an installed disk without
touching it: for each profile it copies the disk, writes the profile's `CONFIG.SYS` and
`AUTOEXEC.BAT` and small test programs of ours onto the copy with mtools, boots the copy in the
lab's own QEMU and reads the results back from the copy. It measures `MEM`; `EMSCHK.COM` (EMS pages
and frame); `VGARTRC.COM` (does the VGA report display enable on eight reads of port 3DAh in a row,
as Wolfenstein 3D waits for: never with QEMU's default retrace, always with
`retrace=precise`); `VGAAR.COM` (does port 3C0h read back the attribute address in the data
state, what The Incredible Machine needs: `FAIL` before pve-qemu `wsh/0051`); `SNDCHK.COM` (the Sound
Blaster DSP's version, and an AdLib tone and a PC speaker beep that QEMU records into a WAV file);
whether the screen is lit at the end; and QEMU's guest-error log. With a games disk it starts one
game per run, presses its keys and samples the screen and the sound.

```sh
cd e2e/sparc
python3 dos_profiles.py show --flavour msdos                    # the profiles' CONFIG.SYS and AUTOEXEC.BAT
python3 dos_profiles.py run --flavour freedos --disk c.raw --out /work/prof --vga std,retrace=precise
python3 dos_profiles.py run --flavour msdos --disk c.raw --out /work/prof --menu        # the startup menu
python3 dos_profiles.py run --flavour msdos --disk c.raw --games-disk d.raw --games games.txt --out ...
```

It runs in the lab image (`e2e/sparc/Dockerfile`, which has mtools). CI runs it on FreeDOS after
installing FreeDOS from its floppies (`sparc-lab-dos.yml`, `tests/test_dos_profiles.py`): the
FreeDOS profiles, the startup menu and plain `-vga std`, with our own programs only.

### Measured

Lab image with pve-qemu-kvm 11.1.3-3+wsh2, the lab's own QEMU (TCG, Pentium, 32 MB, std VGA with
`retrace=precise`, no NIC, sb16 + adlib + PC speaker), 2026-11-21. In every run below VGARTRC
reported display enable, VGAAR read 20h in both states, `SNDCHK` found DSP 4.05 and its tone and
beep were in the recording, and the screen was lit at the end. Under plain `-vga std` VGARTRC never
saw two reads in a row with display enable; under pve-qemu-kvm 11.1.3-2+wsh16 (without `wsh/0051`)
VGAAR read `00` in the data state.

| Disk | Profile | Conventional free | Largest program | Upper free | EMS (frame) | XMS free |
| --- | --- | --- | --- | --- | --- | --- |
| MS-DOS 6.22 (the lab's `msdos622` install) | as installed (HIMEM, `DOS=HIGH`, WSHIDLE) | 621K | 620K | - | none | 31,552K |
| | Full | 614K | 613K | 107K | none | 31,240K |
| | EMS | 614K | 613K | 42K | 4,480K (D800) | 31,072K |
| | Maximum conventional / No EMM386 | 616K | 616K | - | none | 31,552K |
| MS-DOS 6.22 with a CD-ROM driver, mouse, `KEYB` and an idle TSR | its own `CONFIG.SYS` and `AUTOEXEC.BAT` | 613K | 612K | 63K | none | 20,815K |
| | Full | 613K | 613K | 86K | none | 31,240K |
| | EMS | 613K | 613K | 22K | 4,480K (D800) | 31,072K |
| | Maximum conventional (idle TSR only) | 616K | 616K | - | none | 31,552K |
| | No EMM386 (all of them low) | 595K | 595K | - | none | 31,552K |
| FreeDOS 1.4 (the `freedos14` install) | as installed (menu entry 2: JEMMEX `NOEMS`) | 628K | 628K | 86K | none | 31,073K |
| | Full (JEMMEX `NOEMS`, FDAPM and CTMOUSE high) | 628K | 628K | 94K | none | 31,201K |
| | EMS (JEMMEX `FRAME=D800`) | 626K | 626K | 32K | 31,760K (D800) | 31,249K |
| | Maximum conventional (HIMEMX, FDAPM) | 616K | 615K | - | none | 31,457K |
| | No JEMM (HIMEMX, FDAPM and CTMOUSE low) | 613K | 612K | - | none | 31,457K |

Booted from the MS-DOS 6 startup menu (one `CONFIG.SYS` with the four profiles, the entry picked at
the menu) and from FreeDOS's menu, each entry measured the same as its profile on its own. FreeDOS's
`MEM` also lists 8,592K of EMS under JEMMEX `NOEMS`: JEMM keeps a pool for VCPI, without a frame
(`EMSCHK` finds no EMS device). That disk's own `CONFIG.SYS` loads the Sound Blaster's CSP driver,
which sends commands QEMU's SB16 doesn't know (32 lines in the guest-error log, harmless); no other
run logged any.

**Games per profile** (the MS-DOS 6.22 disk with the drivers above, the games on a second disk,
`retrace=precise`; each game started after the measurements, keys pressed at fixed times, the screen
sampled once a second for 45-75 s). Cells: distinct screens, seconds with sound in the recording.
"Own files" is that disk's own `CONFIG.SYS`/`AUTOEXEC.BAT` (no `BLASTER` set). Every game that
started was still running at the end.

| Game | Own files | Full | EMS | Maximum conventional | No EMM386 |
| --- | --- | --- | --- | --- | --- |
| Doom | 54, 56 s | 55, 54 s | 55, 52 s | 55, 54 s | 55, 55 s |
| Duke Nukem 3D | 62, 70 s | 64, 69 s | **stops: not enough memory** | 62, 69 s | 62, 69 s |
| Wolfenstein 3D | 12, 46 s | 12, 46 s | 12, 46 s | 12, 46 s | 12, 46 s |
| Commander Keen 4 | 17, none | 16, none | 18, none | not measured | 15, none |
| Leisure Suit Larry 1 | not measured | 11, 11 s | 11, 11 s | not measured | 11, 11 s |
| The Incredible Machine | 17, 2 s | 17, 2 s | 17, 2 s | 19, 2 s | 17, 2 s |
| The Incredible Machine 2 | **needs EMS** | **needs EMS** | 21, 42 s | **needs EMS** | **needs EMS** |
| Dune | 40, none | 41, none | 40, none | 19, none | 41, none |
| Dune II | 16, 37 s | 17, 37 s | 18, 38 s | 17, 37 s | 16, 37 s |

- **Duke Nukem 3D under the EMS profile** stops at once ("requires 2607200 more bytes"): DOS/4GW
  gets its memory through VCPI from EMM386's EMS pool, which `RAM 4096` limits to 4 MB. Use Full for
  DOS/4GW games, or give EMM386 a larger pool.
- **Wolfenstein 3D needs `retrace=precise`**: the same run under the Full profile with plain
  `-vga std` showed 2 distinct screens (the prompt and black) and no sound in 60 s, and VGARTRC
  timed out (longest run of display enable: 1 read); with `retrace=precise`, 12 screens and 46 s of
  sound.
- **The Incredible Machine 2** needs 256K of EMS and says so without it; only the EMS profile runs
  it (with the 3C0h fix it shows its screens).
- Keen 4 and Dune made no sound in the sampled time with any profile; Doom, Duke Nukem 3D,
  Wolfenstein 3D and Dune II played sound with every profile that ran them, also with the disk's own
  files without `BLASTER` (they keep their own sound settings).

## Known issues

- **`ne2k_isa` doesn't start.** qemu-server offers the model but puts the ISA card on the PCI bus:
  `Device 'ne2k_isa' can't go on PCI bus`. Until that is fixed, use `ne2k_pci` (4K of option ROM) or
  no NIC.
- **No per-NIC ROM option in PVE.** `machine: ...,legacy-bios-layout=1` drops the ROM of every NIC
  of the VM (and the vapic ROM); removing only one NIC's ROM still needs
  `args: -global ne2k_pci.romfile=` (root only).
- **The Incredible Machine 1 and 2 show a black screen while their music plays.** QEMU's VGA read
  the attribute controller's address register (port 3C0h) as 0 when its flip-flop was in the data
  state; the games save the address that way while loading the palette and write it back, which
  turns the display off (the palette address source bit) for as long as they run. Every `vga`
  model QEMU offers has the same code, so changing it doesn't help. pve-qemu patch `wsh/0051`
  returns the address in both states, as the VGA does; pve-qemu-kvm 11.1.3-3+wsh2 and later have it
  (`VGAAR.COM` in [Memory profiles](#trying-profiles-with-the-lab) checks it).
  The Incredible Machine 2 also needs 256K of EMS (EMM386 with `RAM`); without it, it stops with
  "You do not have enough memory to run this program".
- **EMM386 must not include the top of the E segment.** `I=` up to EFFF lets DOS boot, then the
  keyboard is dead: SeaBIOS's data at E9000-EFFFF was handed out as UMB. Stay within the gap.
