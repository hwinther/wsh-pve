# OpenBIOS: sparc64 `/virtual-memory` `available` stops at 0xff000000, Solaris 8/9/10 panic

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0003-sparc64-list-the-whole-virtual-address-space-as-available.patch`;
`openbios/Dockerfile` builds `openbios-sparc64` with it.

## Summary

On sun4u (`qemu-system-sparc64 -M sun4u`), the `available` property of `/virtual-memory` covers
only `0`-`0xff000000`. Claims above that address are not shown in it. 64-bit Solaris maps its
kernel heap at `0x30000000000` through the boot program, and Solaris uses the gaps in this list to
size the pool it takes the firmware's translations over into. Booting the install media
stops in the kernel:

- Solaris 10 1/13 (u11) DVD: `panic - kernel: no nucleus hblk8 to allocate`
- Solaris 9 DVD: `panic[cpu0]/thread=140a000: BOP_ALLOC failed`, in `segkmem_alloc` ←
  `kmem_init` ← `kobj_open_file` ← `startup_memlist`
- Solaris 8 1/01 Installation CD: `BOP_ALLOC failed`, the same call chain

The result is the same with 256 MB to 2 GB of RAM. (With the node-name fix of
`openbios-sparc64-node-names.md` also applied, Solaris 10 still panics at 1024 MB but not at
2048 MB; why the amount of RAM matters then was not traced.) QEMU issues
[#216](https://gitlab.com/qemu-project/qemu/-/issues/216) (Tribblix, `no nucleus hblk8 to
allocate`) and [#293](https://gitlab.com/qemu-project/qemu/-/issues/293) (Solaris 8, `BOP_ALLOC
failed`) report the same panics; neither records a cause.

- **Affected:** OpenBIOS since `6e3d3fd` ("libopenbios: limit upper virtual memory range to
  ofmem_arch_get_virt_top()", 2016-10) up to the current master `e5ac46dd24` (QEMU 11.1.3).
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS and wrote `6e3d3fd`. OpenBIOS takes
  patches at openbios@openbios.org; the code is at <https://github.com/openbios/openbios>.

## Evidence

QEMU 11.1.3, `-M sun4u -m 1024`, the DVD on the built-in IDE (`ide.1`), `-boot d`, serial console.
After Solaris 10's panic, at `0 >`, `" /virtual-memory" find-device .properties` showed 180
translations, 102 of them single 8 KB pages of the kernel heap at
`0x30000002000`-`0x30000168000`. None of those addresses appear as gaps in `available`, which
ends with the entry up to `0xff000000`.

The same build with the fix: Solaris 10 1/13 boots to the installer's `Select a Language` prompt;
Solaris 9 gets past `startup_memlist` (and then stops on the next, unrelated bug,
`openbios-sparc64-icache-properties.md`).

## Root cause

`ofmem_update_translations()` renders the `available` property of `/virtual-memory` as the
inverse of the claimed ranges up to `ofmem_arch_get_virt_top() - 1`, which is `0xff000000 - 1` on
sparc64 since `45b60c8`/`6e3d3fd`. A claim above that address leaves no gap in the list.

Solaris counts the virtual memory the firmware has handed out as the sum of the gaps
*between* the entries of this list (`size_virtalloc()` in `startup_modules()`, OpenSolaris/illumos
`usr/src/uts/sun4/os/memlist.c` and `startup.c`). It sizes the pool of "nucleus" hme blocks from
that count. At boot it moves the firmware's translations into its own page tables, taking hme blocks
from that pool (`sfmmu_hblk_alloc()` in `hat_sfmmu.c`). When the heap pages above
`0xff000000` are missing from the count, the pool is too small. Solaris 8 and 9 fail earlier: their
boot program refuses the heap allocation (`Alloc of 0x2000 at 0x16000 refused` in QEMU #293). This
is inferred from the stack trace; their source isn't public.

OBP on an Ultra lists the whole 64-bit address space in `available`. It pre-allocates the
UltraSPARC I/II VA hole (`0x0000080000000000`-`0xfffff80000000000`) and its own range below
4 GB, so neither is in the list. illumos `size_virtalloc()` expects exactly that layout: it
subtracts the hole when it finds a gap spanning it.

`6e3d3fd` limited the list because "64-bit Solaris appears to overflow in its memory list
calculations if the entire virtual memory space is represented". At that time the list ran
through the hole as one entry ending at 2^64.

## Fix

- `arch/sparc64/ofmem_sparc64.c`: `ofmem_init()` claims `OFMEM_VIRT_TOP`-4 GB (the firmware)
  and the VA hole before it inherits the boot translations.
- `libopenbios/ofmem_common.c`: on sparc64, the `available` property of `/virtual-memory`
  covers up to `(ucell)-1`.

Claims with an alignment (the firmware picks the address) still search only below
`OFMEM_VIRT_TOP`. sparc32 and ppc are unchanged.

## Regression check

See `submodules/SPARC.md`, "Solaris on sun4u": NetBSD 11.1 (CD and installed disk), OpenBSD 8.0
`bsd.rd` and the Debian 12 installer boot as before with this patch.
