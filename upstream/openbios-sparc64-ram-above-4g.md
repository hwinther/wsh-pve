# OpenBIOS: sparc64 stops with 4 GB of RAM or more

Material for a bug report to OpenBIOS. We carry the fixes as
`openbios/patches/0013-sparc64-ofmem-keep-the-upper-bits-of-physical-addresses-in-align_ptr.patch`,
`openbios/patches/0014-sparc64-ofmem-find-claim-memory-whose-1-1-virtual-range-is-free.patch` and
`openbios/patches/0015-sparc64-return-the-whole-physical-address-in-phys-lo.patch`;
`openbios/Dockerfile` builds `openbios-sparc64` with them. 0013 and 0014 change generic code
(`libopenbios/ofmem_common.c`); we apply them to the sparc64 build only.

## Summary

`qemu-system-sparc64 -M sun4u` takes any `-m`, but OpenBIOS only works with up to about 4 GB:

| `-m` | What happens (QEMU 11.1.3, OpenBIOS `e5ac46dd24`) |
| --- | --- |
| 3072 | NetBSD 11.1 boots, `hw.physmem64` = all of it |
| 4096 | OpenBIOS comes up; NetBSD 11.1's kernel stops right after the loader (`Unhandled Exception 0x0000000000000030` in the kernel; earlier runs printed `panic: Can't claim two pages of memory.` first) |
| 4352, 5120, 6144, 7168 | OpenBIOS stops before its banner: `Unhandled Exception 0x0000000000000030`, PC in `ofmem_posix_memalign()` |
| 8192 | OpenBIOS stops before its banner: `out of malloc memory (28)!`, then `Unhandled Exception 0x0000000000000030` |

Two separate bugs, one per symptom, and a third that shows once those are fixed: NetBSD boots
with 6 and 8 GB and crashes when its memory fills up.

- **Affected:** OpenBIOS master `e5ac46dd24` (QEMU 11.1.3's `roms/openbios`); the code involved is
  older. Real Ultra 5/10 machines had at most 512 MB / 1 GB, which may be why nobody hit it.
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org; the code is at <https://github.com/openbios/openbios>.

## Bug 1: `align_ptr()` cuts physical addresses to 32 bits

`libopenbios/ofmem_common.c`:

```c
static inline phys_addr_t align_ptr(uintptr_t x, size_t a)
{
    return (x + a - 1) & ~(a - 1);
}
```

`size_t` is `unsigned int` in OpenBIOS (`include/config.h`), so `~(a - 1)` is a 32-bit mask that
is zero-extended to 64 bits: every address bit above bit 31 is cleared.

`ofmem_posix_memalign()` takes the physical address of its next block (`va2pa()`), aligns it with
`align_ptr()` and turns it back into a virtual address with `pa2va()`. On sparc64 the firmware's
`.data` and `.bss`, the heap among them, are copied to the top of RAM by `entry.S`, so with more
than 4 GB of RAM their physical address is above 4 GB. `pa2va()` doesn't recognise the truncated
address as one of the firmware's and returns it unchanged, so the first `malloc()` (from
`ofmem_init()`) hands out a bogus pointer.

Evidence: a debug print in `ofmem_posix_memalign()` (next block, aligned physical address,
returned pointer, heap top, `va_shift`):

```
-m 4096: nm ffe85450 pa fff85460  ret ffe85460 top ffeb5418 vs fffffffffff00000   (fine)
-m 4352: nm ffe85450 pa ff85460   ret ff85460  top ffeb5418 vs ffffffffeff00000   (should be 10ff85460)
-m 8192: nm ffe85450 pa fff85460  ret fff85460 top ffeb5418 vs fffffffefff00000   (should be 1fff85460)
```

With 4352 MB the bogus pointer is below the heap top and the `memset()` faults (exception 0x30);
with 8192 MB it is above it and the allocator reports `out of malloc memory`.

**Fix:** take the address as a `phys_addr_t` and widen the mask:
`return (x + a - 1) & ~((phys_addr_t)a - 1);`

## Bug 2: a client-interface `claim` with an alignment ignores the virtual side

`ofmem_claim()` with `align != 0` (the client lets the firmware choose) takes physical memory from
the top of RAM down (`ofmem_claim_phys_(-1, size, align, 0, get_ram_size(), 1)`) and then claims
the same address as virtual memory for a 1:1 mapping. It only searches the physical list. If the
virtual range at that address is taken, the claim fails, although lower down there is memory free
in both lists.

On sparc64 the virtual range from `OFMEM_VIRT_TOP` (`0xff000000`) to 4 GB is the firmware's own.
With 4 GB of RAM the highest free physical memory ends at `0xffe80000` (`/memory` `available`
is `0`-`0xffe80000`), inside that range. NetBSD's first claim is
`OF_claim(NULL, 2 * PAGE_SIZE, PAGE_SIZE)` in `pmap_alloc_bootargs()`
(`sys/arch/sparc64/sparc64/pmap.c`); it gets -1 and the kernel panics with `Can't claim two pages
of memory.` With more RAM the top is above 4 GB; the 1:1 virtual range there is free, so the claim
would return an address above 4 GB, which clients never get with less RAM (not tried, see below).

**Fix:** search below `min(RAM size, ofmem_arch_get_virt_top())`, and while the virtual range of
the area found is taken, search again below that area. With up to 3 GB of RAM the first area found
has a free virtual range, as before.

## Bug 3: `claim`, `SUNW,retain` and `translate` cut phys.lo to 32 bits

`arch/sparc64/lib.c` returns a physical address as `phys.lo phys.hi` with
`PUSH(phys & 0xffffffff); PUSH(phys >> 32);` (`mem_claim()`, `mem_retain()`,
`mmu_translate()`). 64-bit clients read `phys.lo` alone and pass addresses in with `phys.hi` = 0:

- NetBSD/sparc64 (kernel and `ofwboot`), `sys/arch/sparc/include/openfirm.h` under
  `__sparc_v9__`: `#define CELL2HDQ(hi,lo) (lo)`, `#define HDQ2CELL_HI(x) (cell_t)(0)`
- illumos/Solaris on sparcv9, `usr/src/uts/sparc/v9/sys/prom_isa.h`:
  `#define p1275_cells2ull(h, l) ((unsigned long long)(cell_t)(l))`,
  `#define p1275_ull2cell_high(ll) (0LL)`

So above 4 GB they get the address without its upper bits. With bugs 1 and 2 fixed, NetBSD 11.1
boots with 6144 and 8192 MB and runs, but `ofwboot` claims the kernel's 4 MB pages from the top of
RAM (above 4 GB) and maps its own allocations at the truncated addresses. A trace of the firmware's
physical claims and maps with 6144 MB:

```
CP 17fe7e000 2000 a2000            <- /memory claim returns 0x17fe7e000
MAP 7fe7e000 fef7e000 2000 ...     <- ofwboot maps 0x7fe7e000
CP 17f800000 400000 a400000        <- the kernel's pages
```

While a tmpfs is being filled (at the same point with 6144 and 8192 MB, an estimated 3 GB in) the kernel's trap table is
overwritten and it stops with `trap type 0x10: cpu 0, pc=1000d00` and `panic: illegal
instruction`; apparently its own pages were handed out as free.

**Fix:** push the whole address as `phys.lo`; `phys.hi` keeps the upper 32 bits, so
`(phys.hi << 32) | phys.lo` still gives the same address. The methods that take an address in
already decode it as `(hi << 32) | lo`, which works for both conventions.

## Results with the three fixes

QEMU 11.1.3 (Proxmox's `pve-qemu-kvm` build), `-M sun4u`, one CPU, serial console, NetBSD 11.1
installed on the built-in IDE and Solaris 10 1/13 installed on the built-in IDE. The memory test
writes copies of a 32 MB random file into a tmpfs (swap off) until most of RAM is used and checks
that all copies have the same MD5 sum (details in `submodules/SPARC.md`, "More than 3 GB"):

| Guest | 2048 | 3072 | 4096 | 6144 | 8192 MB |
| --- | --- | --- | --- | --- | --- |
| NetBSD 11.1 | not run | passes (2 GB load) | passes (3 GB) | passes (5 GB) | passes (7 GB) |
| Solaris 10 1/13 | passes (1 GB) | passes (2 GB) | passes (3 GB) | not run | passes (6 GB) |

Each guest reports all of its memory (`hw.physmem64`; `Memory size:` in `prtconf`). Without the
fixes, every size from 4096 MB up fails as in the summary. The NetBSD 11.1, 9.3, OpenBSD 8.0 and
Debian 12 installers and the Solaris 10 DVD boot as before at their usual sizes (512 MB and
1024 MB).

## Not tried

- Claims above 4 GB (bug 2 without the cap below `OFMEM_VIRT_TOP`).
- More than 8 GB of RAM.
- sparc32 and ppc builds with these changes (both are generic code; with RAM below the virtual
  top nothing changes in bug 2, and bug 1 only matters for physical addresses above 4 GB).
