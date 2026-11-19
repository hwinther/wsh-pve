# OpenBIOS: Solaris 2.3 and 2.4 don't boot on sparc32

Material for a bug report to OpenBIOS. We carry four fixes:

- `openbios/patches/0019-sparc32-give-the-solaris-2.0-2.4-boot-block-the-obp-words-it-uses.patch`
- `openbios/patches/0020-sparc32-keep-the-forth-heap-inside-the-firmwares-own-virtual-range.patch`
- `openbios/patches/0021-sparc32-take-node-0-as-the-root-node-in-the-romvec-property-operations.patch`
- `openbios/patches/0022-sparc32-run-the-romvec-calls-with-interrupts-masked.patch`

`openbios/Dockerfile` builds `openbios-sparc32` with them, and pve-qemu installs that over QEMU's
image.

## Summary

On `qemu-system-sparc -M SS-5` (also SS-10/SS-20) with OpenBIOS, the install CDs of Solaris 2.3
Edition II and 2.4 HW 3/95 stop right after the boot block:

```
Trying cdrom:d...
Not a bootable ELF image
Loading a.out image...
Loaded 7483136 bytes
entry point is 0x4000
bootpath: /iommu@0,10000000/sbus@0,10001000/espdma@5,8400000/esp@5,8800000/sd@6,0:d
switching to new context:
(is ?
Unhandled Exception 0x00000009
PC = 0xffd076c8 NPC = 0xffd076cc
Stopping execution
```

Solaris 2.5 and later boot. With Sun's own PROM (`ss5.bin`) 2.3 and 2.4 boot and install. Four
separate gaps in OpenBIOS stop them, one after the other.

- **Affected:** current master `e5ac46dd24` (QEMU 11.1.3's `roms/openbios`) and, as far as the
  code shows, every earlier version.
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org; the code is at <https://github.com/openbios/openbios>.

## 1. The boot block is FCode that uses OBP 2.x words (patch 0019)

The boot block that these CDs and installed disks boot (on the slice, the a.out that OpenBIOS
loads at 0x4000) is a few hundred bytes of machine code wrapped around an FCode program. The
machine code calls the romvec's `pv_fortheval` with `byte-load` on that FCode (the debug build
shows `obp_fortheval_v2(0 0 0 5588 1 byte-load)`). The FCode reads the UFS file system and loads
`/ufsboot`. It finds what it needs by name with `$find`, prints `<name> ?` for a name it doesn't
find, and uses:

| Word | Use | OpenBIOS before |
| --- | --- | --- |
| `romvec` | the romvec address; if missing, the FCode uses 0xffe80010 (where the OBP 2.x PROMs keep it) | missing: the read at 0xffe80098 is the exception above |
| `load-base` | the buffer, set with `(is` | an nvram config word on sparc32, not a value |
| `(is` ( x xt -- ) | sets `load-base` | missing (the `(is ?` above) |
| `op-open` ( cstr -- ihandle ), `op-close`, `op-read` ( len adr ihandle -- actual ), `op-seek` ( lo hi ihandle -- status ) | the romvec's v2 device operations with the first C argument on top; it opens the boot path it reads through `pv_v2bootargs` | missing |
| `adjust-header`, `init-program`, `?go` | start the loaded program: for an ELF `/ufsboot` the FCode copies the segments to their addresses itself, sets `load-base` to the entry point, then calls `init-program` and `?go` | `init-program` only knows a.out/ELF/... headers at `load-base`; the other two missing |
| `file-size`, `$=`, `alloc-mem`, `free-mem` | | present |

The fix defines the missing words in the sparc32 dictionary (`arch/sparc32/init.fs`), makes
`load-base` a value on sparc32 as nvram.fs already does on sparc64, and lets `init-program` start
code at `load-base` when no known header is there (a C helper that sets the entry, calls
`arch_init_program()` and marks the state valid). An a.out or ELF image at `load-base` still goes
to OpenBIOS's `init-program`.

## 2. The Forth heap below 0xffd00000 (patch 0020)

With that, `/ufsboot` loads the 2.3 kernel, which stops with

```
panic - kernel: can't remove OBP hole
```

OpenBIOS maps its 128K Forth heap at `OF_CODE_START - 128K` (0xffce0000), outside the 2 MB from
0xffd00000 that `ofmem_init()` reserves for the firmware. The Solaris 2.3 kernel's kernelmap is
0xfc000000-0xffd00000 (`Sysbase`, `Syslimit` in its symbol table), and it takes the holes in
`/virtual-memory` `available` that start inside that range out of the map; the hole from
0xffce0000 to 0xfff00000 runs past its end, and the kernel panics. A Sun PROM keeps all its mappings between
0xffd00000 and 0xfff00000. The fix maps the heap above the I/O area, inside the reserved range
(about 200K are free there with the current image size), and falls back to the old place if it
doesn't fit.

## 3. Node 0 in the property operations (patch 0021)

Next the 2.3 kernel prints its banner and panics:

```
BAD TRAP: type=9 rp=f0141d54 addr=fffff000 mmu_fsr=2a6 rw=2
kernel write fault at addr=0xfffff000, pme=0x0
```

in `impl_create_root_class` (its symbol table). The debug build shows the call just before it:
`obp_proplen(0x0, name) = -1`: the kernel asks for the root's `name` with node 0, which the OBP
2.x property operations take for the root node (the same kernel boots under `ss5.bin`). OpenBIOS
returns -1 for node 0, and the kernel allocates a buffer of that length. The fix looks node 0 up as the root (the peer
of node 0) in `no_proplen`, `no_getprop` and `no_nextprop`.

## 4. Romvec calls with interrupts enabled (patch 0022)

The 2.4 kernel then panicked in 2 of 4 boots inside OpenBIOS (`BAD TRAP: type=9 ... addr=0`, in
`c@` under `obp_proplen`), called from its idle thread (`init_swift_idle_cpu` →
`prom_getproplen("platform-pm")` in its symbol table) with interrupts on. The Forth engine behind
the romvec isn't reentrant; a second romvec call that comes in during the first (from an interrupt
or a thread it wakes) overwrites its state. The fix raises PIL to 15 in the romvec handler for the
duration of each call and returns at the caller's PIL. With it, 2.4 booted in both runs since (the install from
the CD, the installed disk).

## Tested

`e5ac46dd24` + our patches 0001-0018 and these, Debian 13's `gcc-sparc64-linux-gnu`, QEMU 11.1.3
with the pve-qemu series; see `submodules/SPARC.md`, "Older Sun releases on sun4m", for the table.
Solaris 2.3 Edition II and 2.4 HW 3/95 on SS-5, and 2.2 on SS-10, install and boot the installed
disk under OpenBIOS with the CD answering as a disk (`scsi-hd`; from a `scsi-cd` their kernels
can't mount root, the same under the Sun PROM, so not a firmware matter). Solaris 2.1 on SS-10
gets through its device configuration, then QEMU stops on an instruction access error (not the
firmware). The sparc lab's `smoke` and `idle` matrices (Solaris 2.5.1, 2.6, SunOS 4.1.4, NetBSD
11.1) still pass.

## Sending it upstream

The fixes were written with an AI agent (Claude Code). Say so in the report, or describe the bugs
and the fixes in prose and let the maintainer write the patches. The FCode boot block and the OBP
word list come from observing the CD's boot block at run time (its FCode detokenized with
`detok`), not from Sun source.
