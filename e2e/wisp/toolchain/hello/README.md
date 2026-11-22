# hello: a libc smoke test for the wisp uClibc-ng toolchain

`hello.c` is a small C program built against ordinary libc, not the kernel's nolibc that wisp's
own PID 1 and the `.github/actions/wisp-test` programs use: `printf`, `snprintf`, `malloc`/`free`,
`qsort`, `strtol`, a struct with 64-bit fields and 64-bit division. Every input is fixed, so it
prints the same checksum line on every architecture and exits 0:

```
WISP-HELLO v=1 checksum=0x... status=ok
```

Once the toolchain (`../`) is built, compile with its cross compiler (the exact name under
`bin/` depends on Buildroot's toolchain prefix for the architecture, e.g.
`sparc64-buildroot-linux-uclibc-gcc`; `ls bin` in the exported toolchain shows it):

```sh
<prefix>-gcc -static -O2 -o hello hello.c
```

It is meant to run under wisp's test mode (`wisp=test`, `/test` from a second initramfs; see
`../../README.md`, "A libc toolchain (uClibc-ng)", and
`.github/actions/wisp-test/README.md`, "How it works", for how a binary is packed and run), the
same way the wisp-test action's nolibc test programs do today. Neither the toolchain nor this
program is built by anything in this repository yet.
