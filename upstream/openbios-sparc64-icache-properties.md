# OpenBIOS: sparc64 CPU node reports the E-cache as the I-cache, Solaris 9 "VAC too big!"

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0004-sparc64-give-the-cpu-node-the-icache-size.patch`; `openbios/Dockerfile`
builds `openbios-sparc64` with it.

## Summary

On sun4u, the CPU node's `icache-line-size` and `icache-size` properties carry the E-cache values
from the CPU table. An UltraSPARC IIi (QEMU's default `TI-UltraSparc-IIi`) is reported with a 1 MB
instruction cache with 64-byte lines. The real cache is 16 KB with 32-byte lines, which is what
the table's I-cache fields hold.

64-bit Solaris 9 stops in `startup_modules()` once it gets that far (it needs
`openbios-sparc64-virtual-available.md` first):

```
SunOS Release 5.9 Version Generic 64-bit
panic[cpu0]/thread=140a000: VAC too big!
00000000014098c0 unix:startup_modules+118 (12000, 142a400, 30000018000, 103, 78004000, 1430800)
```

- **Affected:** every sparc64 OpenBIOS since `4cbc339` ("Create extra CPU properties required by
  OpenSolaris kernel", 2010-05-02), up to the current master `e5ac46dd24`.
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org.

## Evidence

`cpu_generic_init()` in `arch/sparc64/openbios.c`:

```c
    PUSH(cpu->ecache_line_size);   /* should be icache_line_size */
    fword("encode-int");
    push_str("icache-line-size");
    fword("property");

    PUSH(cpu->ecache_size);        /* should be icache_size */
    fword("encode-int");
    push_str("icache-size");
    fword("property");
```

The same firmware with both fields corrected boots Solaris 9 past the panic. The next stop,
`boot_alloc: pp is NULL or free`, is a different problem.

The 2016 "VAC too big!" that `6e3d3fd` worked around (by shortening `/virtual-memory`'s
`available`) is most likely this bug. With the shortened list Solaris 9 stops earlier, in
`startup_memlist()` with `BOP_ALLOC failed`, so it never reaches the cache check. This is inferred
from the order of the two panics in our runs; we did not reproduce the 2016 tree.

## Fix

Use `icache_line_size` and `icache_size` for the two properties.
