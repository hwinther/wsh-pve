# QEMU: sun4m power management (APC) maps 1 byte, the firmware says 16

Material for a bug report to upstream QEMU. We carry the fix in pve-qemu as
`debian/patches/wsh/0011-hw-misc-slavio_misc-give-the-sun4m-APC-its-16-bytes-.patch`, with the
qtest `tests/qtest/sun4m-apc-test.c` in the same patch (in `submodules/pve-qemu.patch`).

## Summary

QEMU's sun4m APC device (`TYPE_APC`, `hw/misc/slavio_misc.c`) maps a 1-byte MMIO region. The
`power-management` node that the firmware builds for it declares 16 bytes (`reg` size 0x10), in
OpenBIOS and, by our reading of the guest's device tree, in Sun's SS-5 PROM. Linux and NetBSD only write register 0 (to idle the CPU), so they
never notice. Solaris 2.6's `pmc` driver maps all 16 bytes and writes other registers when it
attaches. The first of those stores falls outside the region, the CPU takes a bus error, and the
kernel panics at boot.

- **Affected:** every QEMU release with sun4m. The APC region has been 1 byte (`MISC_SIZE`) since
  the power management register was first mapped (`3475187dd8`, 2005, release 0.7.1), and exactly 1
  byte since sub-page I/O (`db7b5426a4`, 2007, first in 0.9.1). It has kept that size through each
  rework: its own `apc` device (`2582cfa0cb`, v0.11.0), the memory API (`9c48dee672`, v1.1) and
  QOM. It is still 1 byte in v11.1.3 and in master (`e9fa1f66f0`, 2026-11-13). The panic itself was
  seen on 11.1.3 only (see "What was verified").
- **Introduced by:** nothing recent. The size was never changed, so there is no regression to
  bisect.
- **Who to tell:** `MAINTAINERS` lists `hw/*/slavio_*.c` under Sun4m: Mark Cave-Ayland (M).

## Where in the code

`hw/misc/slavio_misc.c` (master):

```c
#define MISC_SIZE 1
...
static void apc_mem_writeb(void *opaque, hwaddr addr,
                           uint64_t val, unsigned size)
{
    APCState *s = opaque;

    trace_apc_mem_writeb(val & 0xff);
    qemu_irq_raise(s->cpu_halt);
}
...
static void apc_init(Object *obj)
{
    ...
    /* Power management (APC) XXX: not a Slavio device */
    memory_region_init_io(&s->iomem, obj, &apc_mem_ops, s,
                          "apc", MISC_SIZE);
```

`MISC_SIZE` is the size of the one-byte Slavio registers (configuration, diagnostic, modem, ...),
and the APC reuses it. Any write to the region halts the CPU until the next interrupt, and reads
return 0. A CPU access to `apc_base + 1` and above hits no device, so it goes to
`sparc_cpu_do_transaction_failed()` → `sparc_raise_mmu_fault()` (`target/sparc/ldst_helper.c`).
On sun4m that is a data access exception with a bus error in the SFSR.

`hw/sparc/sun4m.c` maps the device at 0x6a000000 on SS-5, SS-4, SPARCClassic and SPARCbook, at
0x71300000 on Voyager (commented `/* pmc */`) and at 0xefa000000 on SS-10, SS-20 and SS-600MP
(`/* XXX should not exist */`).

The firmware side, OpenBIOS `drivers/sbus.c`:

```c
#define APC_REGS         0x10
#define APC_OFFSET       0x0a000000ULL
...
    push_str("power-management");
    ...
    PUSH(APC_REGS);
    ...
    push_str("reg");
```

So on SS-5 the node reads `reg 00000004.0a000000.00000010`. When we wrote the fix, Sun's `ss5.bin`
showed the same `reg` in the guest. We have not checked that again for this note.

## How it shows up

Solaris 2.6 (5/98) on `-M SS-5` with OpenBIOS, installed to disk. The `pmc` driver ("Power
Management prototype v1.1", package `SUNWvygdr.m` on the 2.6 CD) is not installed by default. Once
it is installed and bound to the `power-management` node, the kernel panics at boot:

```
kernel write fault at addr=0x6a000002, pme=0x0
MMU sfsr=b6: Bus Access Error on supv data store at level 0
panic: trap: unexpected MMU trap
```

0x6a000002 is APC register 2, the first register the driver writes past the one QEMU maps. SFSR
0xb6 decodes as fault type 5 (bus error), access type 5 (supervisor data store), level 0, with the
fault address valid. That is the exact value `sparc_raise_mmu_fault()` builds for a supervisor
store to an unassigned address: `(5 << 2) | 2`, plus bit 5 (supervisor) and bit 7 (write).

When it attaches, the driver writes the registers at offsets 2, 4, 9, 0xa and 0xc, and does a
read-modify-write of the register at offset 5. After that, the kernel's idle loop writes register
0, and QEMU already handles that write.

## Reproducing

In a Solaris 2.6 guest on `qemu-system-sparc -M SS-5` (OpenBIOS, one CPU, 256 MB), with the 2.6
CD on SCSI target 6:

```sh
mount -F hsfs -o ro /dev/dsk/c0t6d0s0 /mnt
pkgadd -d /mnt/Solaris_2.6/Product SUNWvygdr.m     # answer y twice
echo 'pmc "power-management"' >> /etc/driver_aliases
echo 'forceload: drv/pmc' >> /etc/system
touch /reconfigure; init 6
```

- **Expected:** the system boots. `modinfo | grep pmc` lists `pmc (Power Management prototype
  v1.1)`, `prtconf -D` shows `power-management, instance #0 (driver name: pmc)`, and the idle
  guest stops using a whole host core.
- **Actual:** the panic above on every boot.

Without a guest, `info mtree` in the QEMU monitor on `-M SS-5` shows the region as a single byte:
`000000006a000000-000000006a000000 (prio 0, i/o): apc`. The qtest checks for this line with
`...-000000006a00000f` instead.

## Fix (in prose)

Make the APC region 16 bytes, the size the firmware declares. A write to register 0 still raises
the CPU halt line, and register 0 still reads 0, so Linux and NetBSD see no change. Registers 1-15
store the value written, read it back, are cleared on reset and never halt the CPU. QEMU doesn't
need to emulate what the registers do. `pmc` only needs its stores and loads to succeed, and after
attach it idles through register 0.

Smaller points that came up while doing this:

- The registers need to be in the migration stream. If they go in a subsection that is only sent
  when one of them is non-zero, a guest that only writes register 0 (Linux, NetBSD) migrates exactly
  as before.
- `apc_info` uses `.instance_size = sizeof(MiscState)`. It should be `sizeof(APCState)`. The current
  value is harmless only because `MiscState` is the larger struct.
- 16 bytes overlaps no other device at any of the three APC addresses above.
- The trace events `apc_mem_writeb`/`apc_mem_readb` don't record the offset. With more than one
  register, it helps if they do.

## Measurements

Using the sparc lab's `idle` scenario (`e2e/sparc`, `scenarios/idle.py`): SS-5, OpenBIOS, host CPU
used by QEMU over 60 s at the shell after login, on QEMU 11.1.3 as packaged by wsh-pve.

| Guest | QEMU | Host CPU | Guest clock over 60 s |
| --- | --- | --- | --- |
| Solaris 2.6 + `pmc` | 11.1.3 + 16-byte APC | 2.3% | 60 s |
| Solaris 2.6 + `pmc` | 11.1.3 | panics at boot | |
| Solaris 2.6, no `pmc` | 11.1.3 + 16-byte APC | 101.8% | 60 s |
| Solaris 2.6, no `pmc` | 11.1.3 | 101.5% | 60 s |

So an idle Solaris 2.6 guest goes from about 102% of a host core to about 2.3% once `pmc` can
attach. Guest time keeps up, and a `dd if=/dev/zero of=/dev/null` of 200000 blocks took 1.6 s with
`pmc` and 1.7 s without. The package with the fix also carried two SunOS 4.1.4 idle patches. These
don't affect Solaris, as the unchanged 101.8% without `pmc` shows. NetBSD 11.1 idles at 2.4% with
and without the fix (its `apc0` writes only register 0).

## What was verified

- **Region size history:** checked with `git log --follow -S`/`-G` on `hw/misc/slavio_misc.c` (and
  `hw/slavio_misc.c` before 2013) in a clone of qemu/qemu at `e9fa1f66f0` (v11.2.0-rc0-25,
  2026-11-13). The power management register was registered with `MISC_MAXADDR` (1) in
  `3475187dd8` (2005-07-02, release 0.7.1). The constant was renamed to `MISC_SIZE` (still 1) in
  `5aca8c3b2f` (2007-05-26), the commit after sub-page I/O (`db7b5426a4`). Both are first in 0.9.1.
  Before sub-page I/O, registrations were page-granular, and we have not checked how a guest
  behaved then. The APC got its own handlers in `0019ad5346` (2008, 0.10.0). It became the separate
  qdev device `apc` in `2582cfa0cb` (2009, v0.11.0) and moved to the memory API in `9c48dee672`
  (v1.1). It is `"apc", MISC_SIZE` in v11.1.3 and in master.
- **Firmware size:** `APC_REGS 0x10` in OpenBIOS master `drivers/sbus.c`, read for this note. For
  the Sun SS-5 PROM, the size comes from our patch's description and was not checked again.
- **Panic and fix:** run on QEMU 11.1.3 only. Older releases were not booted. They have the same
  1-byte region and, since the memory API, the same unassigned-access path to an MMU fault.
- **qtest:** `sun4m-apc-test` checks the region size on SS-5, SS-20 and Voyager, that registers
  1-15 read back, and that a reset clears them. On SS-5 under TCG, a tiny boot ROM checks that a CPU
  store to register 2 reads back without a fault and the CPU keeps running, and that a store to
  register 0 halts it. On 11.1.3 it fails without the fix (the region is 1 byte, register 2 doesn't
  read back) and passes 5/5 with it.
- **Existing reports:** searching the QEMU GitLab issues for "slavio_misc", "pmc solaris",
  "apc sparc" and "power-management sun4m" on 2026-11-15 found nothing.

## Sending it upstream

QEMU declines contributions that include or are derived from AI-generated content
(`docs/devel/code-provenance.rst`). The fix and the qtest here were written with an AI agent,
so the safe route is a bug report that describes the fix in prose and leaves the patch to the
maintainer, or a patch written from scratch by a person.

- Bug report: open a GitLab issue at <https://gitlab.com/qemu-project/qemu/-/issues> with the
  summary, the panic, the `info mtree` line, where the size comes from (`MISC_SIZE` vs the
  firmware's `reg`), the reproduction steps and the measurements.
- Cc Mark Cave-Ayland (`scripts/get_maintainer.pl -f hw/misc/slavio_misc.c`). QEMU doesn't take
  GitHub/GitLab merge requests; patches go to qemu-devel@nongnu.org.
- Drop our patch once a fixed QEMU reaches pve-qemu.
