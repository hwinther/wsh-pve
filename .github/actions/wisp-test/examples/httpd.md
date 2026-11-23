# Test an HTTP service

After checkout in this repository, run the following step on an x86_64 Ubuntu runner.
Set `arch` to `sparc32` for SS-5 or `x86_64` for pc. Supply the format 2 kit built by
`e2e/wisp/kit.sh` using the `kit` input until that format is available in the kit release.

```yaml
- uses: ./.github/actions/wisp-test
  with:
    arch: sparc32
    sources: e2e/wisp/services/httpd/httpd.c
    libc: uclibc
    mode: run
    network: 'true'
    forward: '8080'
    ready: '^WISP-HTTPD listening port=8080$'
    check: curl -fsS "http://127.0.0.1:$WISP_PORT/"
```

The guest gets its address from DHCP. After httpd prints its listening line, curl reads a
response containing the guest's Linux release, machine and request count. The action stops
QEMU when curl finishes. For sun4u, compile the same source with
`sparc64-linux-gnu-gcc -static -Os -s -o httpd e2e/wisp/services/httpd/httpd.c` and use
`arch: sparc64` and `binary: httpd` in place of the source and libc inputs.
