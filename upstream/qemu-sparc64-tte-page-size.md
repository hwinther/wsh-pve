# QEMU: sparc64 TTEs lose the third page-size bit (32 MB and 256 MB pages)

Status note, not a new report: the bug is already on qemu-devel with a patch by someone else
(below). We don't carry a fix in pve-qemu. This file records what we checked against our build, so
the patch can be picked up, or dropped from our list, when it lands.

## Summary

UltraSPARC T1 (sun4v) and UltraSPARC IV+ encode the page size of a TTE in three bits; QEMU keeps
two. `TTE_PGSIZE()` in `target/sparc/cpu.h` reads only bits 62:61, `sun4v_tte_to_sun4u()` in
`target/sparc/ldst_helper.c` masks the sun4v size field with `& 3`, and `demap_tlb()` repeats the
2-bit arithmetic. A 256 MB page is decoded as 64 KB and a 32 MB page as 8 KB, so the guest faults
on the first access past the truncated entry.

- **Affected:** QEMU 11.1.3 (our `pve-qemu-kvm` 11.1.3-2+wsh7) and master on 2026-11-16 (the macro
  is unchanged: `#define TTE_PGSIZE(tte) (((tte) >> 61) & 3ULL)`).
- **Who hits it:** Solaris 10 1/13 (and OpenSolaris b134, Solaris 11) on `-M niagara` with more than
  1024 MB of RAM in the machine description, where the kernel maps itself with 256 MB pages.
  Nothing on sun4u that we run (NetBSD, OpenBSD, Linux) uses those sizes.
- **Reported upstream:** "target/sparc: implement TTE page-size for 32M/256M pages" by Dmitry
  Pimenov, v1 2026-07-27 (<https://lore.kernel.org/qemu-devel/20260727233646.332875-1-sun4qemu@gmail.com/>),
  v2 2026-09-18 (<https://lore.kernel.org/r/20260918105705.433093-1-sun4qemu@gmail.com>). Not merged
  on 2026-11-16. The author's copy, with his verification logs:
  `github.com/unix0cc/qemu-experimental-patches`, `upstream/0002-target-sparc-implement-TTE-page-size-for-32M-256M-pages.patch`
  (sha256 `c9218cab237f3702b9268d129b44782cbecff7493a835aea4e21382037b28b79`). The patch's own
  trailer says AI was used for code and analysis.
- **Who to tell:** `MAINTAINERS`, SPARC TCG CPUs: Mark Cave-Ayland, Artyom Tarasenko.

## How it shows up

Solaris 10 1/13 DVD on `-M niagara -m 2048` with a 2048 MB machine description (`unix0cc/md`,
`bin/_test/pagesize_256m/2048`, Sun's OpenSPARC T1 hypervisor and OpenBoot), `boot /virtual-devices/disk@0:f`: OpenBoot loads the
boot archive and `unix`, the kernel prints `WARNING: max-cpus property missing from MD platform
node, using default NCPU value` and then nothing more; no `SunOS Release` banner within 900 s, QEMU
keeps one host core busy.

## What was verified here

The patch applies cleanly to v11.1.3 (`005c61c0ef`). Built `qemu-system-sparc64` alone
(`--target-list=sparc64-softmmu`) with and without it; the same guest, firmware and RAM:

| QEMU | Result |
| --- | --- |
| `pve-qemu-kvm` 11.1.3-2+wsh7 | hangs after loading `unix` (above), 900 s |
| v11.1.3 + the patch | `SunOS Release 5.10 Version Generic_147147-26 64-bit` at 16 s, the installer's "Select a Language" at 313 s, "Identify This System" at 389 s |

With 1024 MB the package's QEMU reaches the installer without the patch (`submodules/SPARC.md`,
"sparc64: niagara (sun4v)").

## Sending it upstream

Nothing to send: the report and patch exist. If it stalls, a reply on the v2 thread with an
independent `Tested-by` and the result above is the useful contribution (a person should write
it; QEMU declines AI-generated content). Carry the patch in pve-qemu only if niagara becomes a
supported profile.
