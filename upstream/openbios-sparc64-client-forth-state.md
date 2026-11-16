# OpenBIOS: Forth state at client start breaks Solaris 10's `unix-tte` (three bugs)

Material for bug reports to OpenBIOS. We carry the fixes as
`openbios/patches/0005-sparc64-leave-no-active-package-after-preopen.patch`,
`0006-sparc64-client-dont-define-a-forth-constant.patch` and
`0007-sparc64-fcode-consume-instance-in-defining-words.patch`. `openbios/Dockerfile` applies them
to `openbios-sparc64` only. 0006 and 0007 change generic Forth code, so sparc32 and ppc have the
same bugs; we didn't test those builds with the patches.

## Summary

64-bit Solaris teaches the firmware to translate kernel addresses. It defines Forth words
through the client interface `interpret`: `kmem64-tte`, then the hme hash constants and
`unix-tte`. Later it runs `' unix-tte is va>tte-data`. On OpenBIOS (Solaris 10 1/13 DVD,
`-M sun4u`, serial console) that last step fails:

```
unix-tte:interpret: exception -13 caught
interpret ' unix-tte is va>tte-data failed with error ffffffffffffffed
```

The firmware keeps the early `kmem64-tte` handler for its TLB misses on kernel addresses after
the kernel has replaced the mappings that handler describes. The installer still comes up. Any
later firmware TLB miss on a kernel address is suspect. This is inferred: no crash was traced
to it.

Fixing the cause exposed two more bugs, one behind the other.

- **Affected:** current master `e5ac46dd24` (QEMU 11.1.3). `preopen` dates from 2009; the
  `forth` constant from `8a6d445` (2010-03); the FCode defining words never handled `instance`.
- **Who to tell:** Mark Cave-Ayland (OpenBIOS maintainer), openbios@openbios.org.

## 1. `/chosen` stays the active package (0005)

`preopen` in `arch/sparc64/init.fs` (the same code is in `arch/sparc32/init.fs`) does
`" /chosen" find-device` and never `device-end`. The `ok` prompt and every client program then
run with `/chosen` active: `get-current` is `/chosen`'s method list, and the search order holds
it in front of forth.

```
0 > active-package .  ffe1c6e8  ok          (the /chosen node)
```

Solaris's definitions went into `/chosen`'s word list. The kernel then creates its `os-io`
node with `" /" find-device new-device ... finish-device device-end`. `device-end` sets the order
to forth alone, so `unix-tte` was no longer visible. We traced each `interpret` call: the
active package was `/chosen` up to the `os-io` text and 0 afterwards. Fix: end `preopen` with
`device-end`. OBP has no active package at the ok prompt.

## 2. `11 constant forth` hides the FORTH vocabulary (0006)

`forth/debugging/client.fs` names the load-state file types with constants. The one for Forth
source is `11 constant forth`, which hides the `forth` vocabulary word from `vocabulary.fs`:

```
0 > only  ok
0 > forth  ok
1 > .s <1> 11
```

Solaris's debugger words (`data64.fth`, `kdbg.fth`) start with `only forth also definitions`,
so they ran with a stray cell on the stack. Before fix 1 the damage didn't show, because the
words ran inside `/chosen`. Nothing uses the constant; drop it.

## 3. FCode defining words leave `instance` set (0007)

`instance` sets `#instance`, and the next defining word consumes it through `instance?`. The
Forth defining words (`value`, `variable`, `defer`, `buffer:`) do this. The FCode ones
(`b(value)`, `b(variable)`, `b(defer)`, `b(buffer:)`) don't, so the flag survives an FCode
program that uses `instance`. The next Forth defining word then makes an instance word. Here
that was the kernel's `defer p@` in `data64.fth`, and with no active package (after fix 1)
`instance,` fetched the instance size through address 0:

```
Unhandled Exception 0x00000000ffeb6520
PC = 0x00000000ffd0f220 NPC = 0x00000000ffd0f224      (in the "@" primitive)
```

Evaluating the same text line by line showed the crash at `defer p@`. We infer that the
Solaris boot block (FCode) left the flag set, since nothing else in that boot uses `instance`;
we didn't trace it. Fix: the four FCode words call `instance? drop`. They still create static
data, as before. Supporting instance data in FCode is a larger change.

## Result

With all three fixes, `' unix-tte is va>tte-data` succeeds and Solaris 10 1/13 boots to the
installer as before. The `kdbg.fth` symbol-lookup words still stop at `could not find
debugger-vocabulary-hook` / `>threads`. Those are OBP-internal words (a `defer` that OBP runs on
entering the ok prompt, and access to a vocabulary's hash threads). Without them Solaris has no
symbol lookup in the firmware, which is optional.
