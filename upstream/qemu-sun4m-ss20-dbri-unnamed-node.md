# sun4m SS-20 and LX: the DBRI stub gives Sun's PROMs a node without a name, Solaris 2.1/2.2 and SunOS 4.1.4 panic on it

For the owner, to send as a bug report if wanted (QEMU doesn't take AI-written code, and this
write-up was made with an AI agent). Found 2026-11-20 in the wsh-pve lab with QEMU 11.1.3 and the
wsh-pve series (wsh/0001-0041); nothing in that series touches the code below. Since 2026-11-21
pve-qemu carries a fix of ours, `debian/patches/wsh/0057` with the qtest `0058` (in review, not in a
package yet; "The fix (0057)" below), after the same node turned up on the SPARCstation LX
([qemu-sun4m-lx-onboard-sbus.md](qemu-sun4m-lx-onboard-sbus.md)).

## What happens

`hw/sparc/sun4m.c` puts two unimplemented devices where the SS-20's DBRI (ISDN + CS4215 audio)
would be, in SBus slot e:

```c
if (hwdef->dbri_base) {
    /* ISDN chip with attached CS4215 audio codec */
    /* prom space */
    create_unimplemented_device("sun-DBRI.prom", hwdef->dbri_base + 0x1000, 0x30);
    /* reg space */
    create_unimplemented_device("sun-DBRI", hwdef->dbri_base + 0x10000, 0x100);
}
```

Sun's SS-20 PROM (2.25) and SS-10 PROM (2.25, which runs on `-M SS-20 -cpu TI-SuperSparc-50`) probe
slot e, read zeros where the FCode would be, and create an SBus node without a `name` property:

```
ok cd /iommu/sbus
ok ls
ffd76500 <Unnamed>
ffd76370 SUNW,bpp@f,4800000
...
```

Solaris 2.1 and 2.2 walk the device tree early in `startup` and compare node names; the missing name
is a NULL pointer:

```
BAD TRAP: type=9 rp=f00a8054 addr=0 mmu_fsr=126 rw=1
kernel read fault at addr=0x0, pme=0x0
MMU sfsr=126: Invalid Address on supv data fetch at level 1
pid=0, pc=0xf002b300 ...
panic: Data fault
```

The 2.1 kernel's symbol table puts the traceback at strcmp, `get_neighbors`, `di_dfs` (three
levels), `impl_init_tree`, `startup`. Solaris 2.3 and later boot with the same PROM and node.

## Evidence it is the node

Naming the node at the PROM prompt before `boot` is enough: with it the 2.2 CD boots to its
installer under the SS-20 PROM, and 2.1 gets as far as it does under OpenBIOS (where it then needs
qemu-sparc32-context-switch-ifetch.md). OBP 2.x has no word to select a node by phandle; the
setter that `find-device` uses is headerless, so its address comes from `see find-device`
(`r> (ffd4e390) throw` with this PROM):

```
ok ffd76500 ffd4e390 execute " SUNW,DBRIe" device-name device-end
ok cd /iommu/sbus
ok ls
ffd76500 SUNW,DBRIe
```

Leaving `sun-DBRI.prom` out instead doesn't help (tried with the SS-10 PROM): its probe of slot e then takes a data access
error and it stops at `ok` without a banner. So the PROM wants something answering there, and a fix
would rather make the stub look like an SBus device the PROM can name (a minimal FCode header with a
`name`, as the real DBRI's PROM has) than remove it.

## The same node on the LX (2026-11-21)

The SPARCstation LX's PROM (OBP 2.10) has the DBRI in slot 2, and its own FCode for that slot maps
0x40 bytes at slot offset `0x1000` and byte-loads them, the same window. With the LX's on-board
devices mapped (wsh/0056, which gives `-M LX` the SS-20's DBRI stub) it too makes the node
without a `name`, and SunOS 4.1.4 panics in its autoconfiguration:

```
BAD TRAP: cpu=0 type=9 rp=f00e0af4 addr=0 mmu_fsr=126 rw=1
kernel read fault at addr=0x0, pme=0x0
panic: Data access exception
```

Named by hand, the CD's kernel reaches the installer, but the installed GENERIC kernel still panics
the same way: its `dbri` driver wants the node's `reg` and `intr` too. With `name`, `reg` (slot
offset `0x10000`, 0x100 bytes) and an SBus level 5 interrupt added by hand it boots, and the driver
reports `dbri: DBRI Reg8 bad!` and `Audio: no Audio device found` and lets go.

## The fix (0057)

The window (now 0x40 bytes) holds a small FCode program of ours instead of zeros:

```
" SUNW,DBRIe" encode-string " name" property
my-address 10000 + my-space 100 reg
5 0 intr
```

(tokenized by hand: start1 header, 48 bytes of program). That is the node a DBRI makes; the
registers behind it are still the unimplemented device, so the drivers find no codec and go without
sound: SunOS 4.1.4 as above, Solaris 2.6 `WARNING: dbri: DBRI Reg8 bad!`, NetBSD 9.3 `dbri0: chip
never acked WAIT`, `no codec detected, aborting` (about 3 s at boot). The window is mapped at
priority -1000 like the unimplemented devices, because on the LX the TCX or cg3 that `-vga` adds
sits at the slot's base with a 64 KB ROM over offset `0x1000`.

Tested in the lab (2026-11-21, 11.1.3 with wsh/0001-0058): the Solaris 2.2 CD reaches its installer
under `ss20_v2.25_rom` without the node being named at the prompt (without 0057: `BAD TRAP: type=9`,
`panic: Data fault`); the stored Solaris 2.6 SS-20 disk boots under that PROM with and without it;
on the LX, SunOS 4.1.4 and 4.1.3_U1B install and boot, Solaris 2.6 and NetBSD 9.3 boot. qtest
`sun4m-onboard-sbus-test` checks the FCode on the LX and the SS-20 (header, checksum, length,
program) and fails without 0057. Solaris 2.1 under the SS-20 PROM was not retried with it.

## Reproducing

```sh
qemu-system-sparc -M SS-20 -cpu TI-SuperSparc-50 -m 256 -bios ss20_v2.25_rom -nographic \
  -drive file=Solaris_2.2.img,if=none,id=cd,format=raw,readonly=on \
  -device scsi-hd,scsi-id=6,drive=cd
# at ok:  boot cdrom      (the CD as a disk; from scsi-cd these releases can't mount root)
```

The PROM is Sun's and isn't in QEMU; the report would have to say that it was seen with Sun's
PROMs only.
