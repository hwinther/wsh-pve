# OpenBIOS: Stop-A powers a running sparc32 guest off

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0008-sparc32-enter-the-prompt-on-op_enter-and-resume-with-go.patch`;
`openbios/Dockerfile` builds `openbios-sparc32` with it, and pve-qemu installs that over QEMU's
image.

## Summary

On sparc32 (`qemu-system-sparc -M SS-5`, also SS-10/SS-20), pressing Stop-A (L1-A, the Sun
keyboard's abort sequence) in a running Solaris turns the machine off. OpenBIOS prints on ttya

```
abort, power off
```

and QEMU exits with status 0, as for a guest power-off. Everything the guest had not written to
disk is lost. On a Sun the same keys stop the machine at the PROM's `ok` prompt and `go` resumes
the operating system where it was.

- **Affected:** the romvec's `pv_abort` (`op_enter` in Sun's naming) in
  `arch/sparc32/romvec.c` has powered off since it was written; current master `e5ac46dd24`
  (QEMU 11.1.3's `roms/openbios`) included.
- **Reached by:** every client that calls `op_enter`. Solaris 2.x (`debug_enter()` →
  `prom_enter_mon()`) and SunOS 4.1.4 call it on the keyboard abort sequence (Solaris also on a
  break on a serial console, which under QEMU hangs Solaris instead: a separate ESCC bug); QEMU
  sends the chord with `sendkey stop-a` (HMP), `send-key` with qcodes `stop` and `a` (QMP), and
  from a VNC client that sends the Stop key. NetBSD's GENERIC kernel enters its own debugger
  instead and isn't affected.
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS. OpenBIOS takes patches at
  openbios@openbios.org; the code is at <https://github.com/openbios/openbios>.

## Evidence

Solaris 2.6 on SS-5, OpenBIOS `e5ac46dd24`, cg3, console on the framebuffer, at `console login:`
and at the dtlogin screen; QMP `send-key` `stop` + `a`, QEMU traced with
`-trace slavio_aux2_mem_writeb`:

```
switching to new context:
abort, power off
slavio_aux2_mem_writeb Write aux2 0x01
```

QEMU exited 3 s after the keys, exit status 0, nothing on stderr (the write to the power-off bit
of the AUX2 register is `qemu_system_shutdown_request(SHUTDOWN_CAUSE_GUEST_SHUTDOWN)`). A
management layer that runs QEMU with `-no-shutdown` and ends it on a guest shutdown (Proxmox VE)
loses the VM the same way.

## Root cause

```c
void obp_abort(void)
{
    printk("abort, power off\n");
    *power_reg = 1;
    printk("power off failed\n");
    for (;;) {}
}
```

`op_enter` is "enter the monitor and return when the user types `go`", not "halt". `op_exit`
(`pv_halt`, Solaris's `halt`) powering off is a reasonable choice for a virtual machine; `op_enter`
doing the same is not.

## Fix

Run the Forth interpreter from `obp_abort()` and return to the client when it ends:

- `obp_abort()` raises PIL to 15 (the console is polled; the client's own keyboard and serial
  interrupt handlers would otherwise take the keys typed at the prompt), calls a Forth word
  `(enter)`, restores PIL and the data stack depth, and returns.
- `(enter)` (in `arch/sparc32/init.fs`) saves the input source (the client was started from the
  `boot` that `boot-command` evaluates, so the current source is that string), switches to an
  input buffer of its own, prints `Type  'go' to resume` and runs `outer-interpreter`.
- While a client is entered, `go` sets `terminate?` instead of starting a loaded image, so the
  interpreter returns to `(enter)` and from there to the client; `boot` calls `reset-all` first
  (the client still occupies memory), as the Sun PROMs reset before they boot.

The OpenBIOS mappings (console, keyboard, framebuffer, reset register) are still in the client's
MMU context, as for every other romvec call, so the prompt works without switching contexts.
Without a client (at the firmware's own prompt) the chord stays ignored, as before.

## Tested

With `e5ac46dd24` + 0001, 0002 and the fix, built with Debian 13's `gcc-sparc64-linux-gnu`, on
QEMU 11.1.3 with the pve-qemu series (the sparc lab's `scenarios/stop-a.py`, two rounds each):
see the table in `submodules/SPARC.md`, "Stop-A". In short: Solaris 2.6 on SS-5, SS-10 and SS-20
(also with 2 CPUs) and SunOS 4.1.4 on SS-5 drop to the prompt at the console login (Solaris also
at dtlogin), Forth works there, `go` resumes them (a login afterwards works), a second Stop-A
works the same, and `boot` resets and boots again. Stop-A at the firmware's own prompt is still
ignored, and NetBSD still enters its debugger.

## Sending it upstream

The fix was written with an AI agent (Claude Code). Say so in the report, or describe the bug and
the fix in prose and let the maintainer write the patch.
