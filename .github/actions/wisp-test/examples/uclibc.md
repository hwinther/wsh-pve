# Run the uClibc-ng example

From the repository root on an x86_64 Debian or Ubuntu host, run the existing
[hello program](../../../../e2e/wisp/toolchain/hello/hello.c) on both targets.

```sh
for arch in sparc32 x86_64; do
    WISP_ARCH="$arch" WISP_LIBC=uclibc WISP_SOURCES=e2e/wisp/toolchain/hello/hello.c \
        bash .github/actions/wisp-test/wisp-test.sh || exit 1
done
```

The program sorts 64-bit integers with `qsort`, divides the largest by the smallest and folds
the output of `snprintf` into its checksum. Both guests should print the same line.

```text
WISP-HELLO v=1 checksum=0xed3258f703d97351 status=ok
```
