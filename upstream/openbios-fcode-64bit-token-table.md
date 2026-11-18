# OpenBIOS: 64-bit FCode tokens from 0x24a on run the wrong words

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0017-sparc64-fcode-put-xa-plus-and-xa1-plus-into-the-64-bit-table.patch`;
`openbios/Dockerfile` applies it to `openbios-sparc64` only (the code is generic: every 64-bit build
has the bug).

## Summary

`forth/device/table.fs` builds the FCode master table. The 64-bit extension's tokens are 0x241 to
0x254. The table's 32-bit branch (`64bit? [ELSE]`) keeps that layout: seven reserved tokens
(0x241-0x247), `/x` at 0x248, twelve reserved tokens (0x249-0x254). The 64-bit branch lists

```
bxjoin <l@ lxjoin wxjoin x, x@ x! /x /x*        \ 0x241-0x249
\   ['], /xa+                                   \ commented out
\   ['], /xa1+                                  \ commented out
xbflip xbflips xbsplit xlflip xlflips xlsplit xwflip xwflips xwsplit
```

With the two entries for 0x24a (`xa+`) and 0x24b (`xa1+`) commented out, every following word sits
two tokens too early, and each token from 0x24a on runs the word two places further down the
standard's list: `xbflip`'s token runs at 0x24a, ..., and FCode that uses `xlsplit` (0x251) gets
`xwflips` (0x253 in the standard). The last two tokens (0x253, 0x254) are unassigned. The two words
exist: `forth/lib/64bit.fs` defines `xa+` and `xa1+` (the comment's names had a stray `/`).

- **Affected:** current master `e5ac46dd24` (QEMU 11.1.3); the table entries are from `7c14e1e`
  ("hook up new 64bit words into fcode table").
- **Who to tell:** Mark Cave-Ayland (OpenBIOS maintainer), openbios@openbios.org.

## What it looks like

The ZFS boot block of illumos and Solaris (`usr/src/psm/stand/bootblks/zfs/common/zfs.fth`, removed
from illumos-gate in 2023 but still what Tribblix ships for SPARC) does its 64-bit compares with
`xlsplit` (`x0=`, `xcmp`). Booting a Tribblix m34 disk installed with its default ZFS root on
`-M sun4u`:

```
Trying disk:a...
Loading FCode image...
Loaded 4168 bytes
entry point is 0x4000
Evaluating FCode...
Unhandled Exception 0x0000000000000030
PC = 0x00000000ffd0f498 NPC = 0x00000000ffd0f49c
```

The boot block had loaded its second stage (the `zfs-file-system` package, 16 KB at 512 KB into
the slice) and was opening the pool. The PC is in `unaligned-l@`. The Forth return stack (read from
memory after the exception: `PC`, `rstack`, `rstackcnt` in the firmware's data) went through
`$open-package`, the package's `open`, `scan-vdev` and `x0=`, whose first call was `xwflips`
instead of `xlsplit`: it took the value to split (0) as an address and read from it.

## Fix

Put the two entries in:

```
  ['], xa+
  ['], xa1+
```

## Verification

With the fix the same disk boots: the boot block reads the pool, loads the kernel and the boot
archive from ZFS, and Tribblix comes up from its ZFS root (`submodules/SPARC.md`, "Tribblix on
sun4u"). The hsfs and UFS boot blocks (Solaris 10, Tribblix's CD) use none of these tokens and boot
as before; the lab's `sparc64` and `solaris10` matrices ran with the fixed firmware (results in
`submodules/SPARC.md`).
