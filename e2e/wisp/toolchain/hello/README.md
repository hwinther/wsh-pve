# hello under wisp

`hello.c` exercises `printf`, `snprintf`, `malloc`, `free`, `qsort`, `strtol` and 64-bit
division. From the repository root, use a built toolchain image to compile a static executable.
The following shell commands stream the source and executable through Docker so the daemon can
run on a different machine.

```sh
arch=sparc32                  # or x86_64
case "$arch" in
    sparc32) prefix=sparc-buildroot-linux-uclibc ;;
    x86_64)  prefix=x86_64-buildroot-linux-uclibc ;;
esac
image=ghcr.io/hwinther/wsh-pve/wisp-toolchain-$arch:2025.02.20
docker run --rm -i "$image" sh -ec \
    '"$1-gcc" -static -O2 -x c -o /tmp/hello - && cat /tmp/hello' sh "$prefix" \
    < e2e/wisp/toolchain/hello/hello.c > "hello-$arch"
file "hello-$arch"
wc -c < "hello-$arch"
```

Boot the executable with the repository's `wsh-wisp` image (see the [wisp build
instructions](../../README.md#build)). The script downloads the published test kit (and checks its
SHA-256 when `WISP_KIT_SHA256` is set), packs the executable as `/test` and passes `wisp=test` to the kit's kernel. The QEMU
serial console is written to stdout.

```sh
tar -czf - "hello-$arch" .github/actions/wisp-test/wisp-test.sh |
    docker run --rm -i -w /tmp -e WISP_ARCH="$arch" -e WISP_BINARY="hello-$arch" \
        wsh-wisp sh -ec 'tar xz && bash .github/actions/wisp-test/wisp-test.sh'
```

The expected console line on both architectures is:

```
WISP-HELLO v=1 checksum=0xed3258f703d97351 status=ok
```

PID 1 should then report `WISP-TEST v=1 exit=0 signal=0` followed by the elapsed milliseconds.
