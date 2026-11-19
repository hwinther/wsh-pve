# OpenBIOS: sparc64 `/memory` `available` lists partial pages, Solaris 7-9 "pp is NULL or free"

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0024-sparc64-ofmem-list-whole-pages-in-memory-available.patch`;
`openbios/Dockerfile` builds `openbios-sparc64` with it.

## Summary

`ofmem` records claimed physical ranges to the byte, and `/memory`'s `available` property is
built from the gaps between them. The ELF loader claims each program segment with its exact
`p_memsz` (`elf_load.c`: `ofmem_claim(phdr[i].p_vaddr, phdr[i].p_memsz, 0)`), so after
Solaris's sun4u boot program is loaded at 0x100000 the list reads (1 GB of RAM):

```
available   00000000 00000000   00000000 00100000
            00000000 00123127   00000000 00000001
            00000000 00181540   00000000 3cef2ac0
```

OBP lists whole pages only. 64-bit Solaris 7, 8 and 9 count an entry that starts inside a page
one page short at its top: they have no page structure for the last page of the big entry (here
the page at 0x3d072000, just below 0x3d074000). OpenBIOS hands out physical memory from the top
down, so a few boot allocations after the kernel has built its page structures the boot program
claims exactly that page, and the kernel panics:

```
SunOS Release 5.9 Version Generic_118558-34 64-bit
panic[cpu0]/thread=140a000: boot_alloc: pp is NULL or free
0000000001408c20 unix:boot_mapin+80 (30000058000, 2000, 2000, 1000, 100, 78004000)
0000000001408cd0 unix:boot_alloc+4c (30000058000, 2000, 1000, 3000006db19, 3000006db2a, 30000060000)
```

Solaris 7 says `kmem_getpages: pp is NULL or free`. Solaris 10 boots with the same list.

- **Affected:** every sparc64 OpenBIOS we tried, up to the current master `e5ac46dd24` (QEMU
  11.1's `roms/openbios`). Before the fixes in `openbios-sparc64-virtual-available.md` and
  `openbios-sparc64-icache-properties.md` Solaris 8/9 stop earlier, so the panic only shows with
  those.
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org.

## Evidence

A debug build that logged every physical claim and release and every client `getprop` of
`/memory` `available` (the list as returned), booting the Solaris 9 9/05 DVD with 1 GB of RAM:

- the kernel reads `available` five times; the last read, before it builds its page structures,
  lists `00181540 3cef2ac0` (end 0x3d074000) as the top entry below the firmware;
- nothing is released during the boot;
- the boot allocations after that read are single 8 KB `claim`s on `/memory` (align 0x1000),
  answered top-down: the free pages below the firmware (`0x3fd1e000` down to `0x3fc00000`, the
  aligned entry `3fc00000 00120000` in that read), then `0x3d072000`, the last page of the big
  entry; the kernel panics on that one (`translate` of the failing virtual address at `0 >` gives `0x3d072000`).

The same holds for the other cases we measured: Solaris 8 2/02 with 1 GB (top entry `001410f0
3d254f10`, end 0x3d396000; the failing 80 KB allocation ends there) and 9 9/05 with 2 GB (`00181540
79e7eac0`, end 0x7a000000; the failing 520 KB allocation ends there). In each case the entry's start
is not page aligned and the failing allocation covers its last page.

## Fix

Round each `/memory` `available` entry's start up and its end down to the page size, and leave
out entries without a whole page. The allocator keeps its byte-granular ranges; a partly claimed
page is no longer listed, and it is not handed out either, since allocations are page aligned and
must not overlap a claimed range. With it Solaris 8 2/02 and 9 9/05 get past the panic to their
installers (results in `submodules/SPARC.md`, "Solaris on sun4u").

Rounding the ELF loader's claims to whole pages would fix this case too, but any client `claim`
with an odd size makes the same kind of gap.
