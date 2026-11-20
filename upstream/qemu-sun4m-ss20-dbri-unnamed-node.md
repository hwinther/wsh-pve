# sun4m SS-20: the DBRI stub gives Sun's PROMs a node without a name, Solaris 2.1/2.2 panic on it

For the owner, to send as a bug report if wanted (no patch: QEMU doesn't take AI-written code, and
this write-up was made with an AI agent). Found 2026-11-20 in the wsh-pve lab with QEMU 11.1.3 and
the wsh-pve series (wsh/0001-0041); nothing in that series touches the code below.

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

## Reproducing

```sh
qemu-system-sparc -M SS-20 -cpu TI-SuperSparc-50 -m 256 -bios ss20_v2.25_rom -nographic \
  -drive file=Solaris_2.2.img,if=none,id=cd,format=raw,readonly=on \
  -device scsi-hd,scsi-id=6,drive=cd
# at ok:  boot cdrom      (the CD as a disk; from scsi-cd these releases can't mount root)
```

The PROM is Sun's and isn't in QEMU; the report would have to say that it was seen with Sun's
PROMs only.
