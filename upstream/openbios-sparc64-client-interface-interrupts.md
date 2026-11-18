# OpenBIOS: sparc64 client interface switches window and trap state with interrupts enabled

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0016-sparc64-client-interface-runs-with-interrupts-disabled.patch`;
`openbios/Dockerfile` applies it to `openbios-sparc64` only.

## Summary

`sparc64_of_client_interface` (`arch/sparc64/call-client.S`) saves the caller's register windows
and trap registers into a context with `SAVE_CPU_STATE`, resets the window registers for the
firmware with `RESET_CPU_WINDOW_STATE`, and puts everything back with `RESTORE_CPU_STATE` on the
way out (`arch/sparc64/cpustate.h`). Both macros walk `%cwp` through every window with `wrpr`, and
the trap part rewrites `%tl`, `%tpc`, `%tnpc`, `%tstate`, `%tt` and `%tba`. Nothing in the entry
path touches `PSTATE.IE`, so all of it runs with the caller's interrupt enable.

NetBSD and Linux have never shown the problem here (we didn't check how their wrappers mask
interrupts around the call). Solaris and illumos don't mask them: `p1275_sparc_cif_handler()`
calls `client_handler`
(`usr/src/uts/sun4u/ml/mach_locore.S`), which switches `%wstate` and the MMU context and jumps to
the firmware with `PSTATE.IE` as it was, and with the kernel's own trap table in `%tba`
(`tba_taken_over`). An interrupt that arrives while the firmware walks the windows runs the
kernel's handler with `%cwp` pointing at an arbitrary window while `%cansave`, `%canrestore` and
`%otherwin` still describe the caller's window. The handler's `save` lands on a window that holds
live registers, which the walk then saves or restores as if nothing happened. An interrupt during
the trap part leaves trap registers that the walk overwrites.

- **Affected:** current master `e5ac46dd24` (QEMU 11.1.3), `-M sun4u`; the save/restore macros
  date from 2015.
- **Who to tell:** Mark Cave-Ayland (OpenBIOS maintainer), openbios@openbios.org.

## What it looks like

Tribblix m34 for SPARC (illumos, the live CD `tribblix-sparc-0m34.iso`, `-M sun4u -m 2048
-nographic`, CD and disk on the built-in IDE, our OpenBIOS patches 0001-0015 or only 0001-0011)
stopped on most boots of its live CD, in two ways, both shortly after a client interface call:

1. **Corrupted locals after a call.** `client_handler` restores `%pstate` from `%l4` after the call
   (`wrpr %l4, 0, %pstate`). `%l4` came back as 0: the kernel ran on in user mode at a kernel
   address, the next trap took the user path of `sys_trap`, and the system ended in an endless
   window spill at TL 1 (`qemu -d int`: nothing but `Window Spill (v=00bc)` at
   `priv_trap+0x44`, tens of thousands of them in a second). The saved trap frame showed `%tpc` `client_handler+0x7c` with `%tstate` `0x4480000006`,
   i.e. `%pstate` 0 one instruction after the `wrpr`.
2. **Garbage return addresses.** `panic[cpu0]/thread=180e000: bad stack overflow at TL 2`, the
   register windows showing nested traps whose saved `%tpc` were `0x1`, `0x3`, `0x7` and
   `0xffffffff`, the oldest one called from `prom_finddevice+0xb0`. Twice, with 1024 and 3072 MB,
   identical register dumps.
3. **Sometimes it got further:** one boot reached the keyboard layout question; another reached the
   login prompt and then hung in the window spill loop of item 1 at the first command typed.

Two further boots hung with the tick interrupt gone (the kernel idle, no level-14 interrupt any
more). That happened with this fix too, so it is something else: a race in QEMU
(`upstream/qemu-sparc64-softint-race.md`).

Solaris 10 1/13 showed the same once in six DVD boots through Proxmox VE: `BAD TRAP: type=4e`
(interrupt level 14) with the PC in the firmware, from `prom_finddevice` in `vfs_mountroot`.

## Fix

Clear `PSTATE.IE` on entry, before `SAVE_CPU_STATE`, and keep the caller's `%pstate` (with its
`IE`) in the context slot `RESTORE_CPU_GENERAL_STATE` reads, so that the windows and the trap
registers are put back with interrupts still off. Write the caller's `%pstate` last, just before
the return jump. The firmware itself then runs the call with interrupts disabled. A caller that
calls in with interrupts disabled sees no change.

```
	rdpr	%pstate, %g2
	andn	%g2, PSTATE_IE, %g3
	wrpr	%g3, %pstate
	...
	SAVE_CPU_STATE(cif)
	stx	%g2, [%g1 + 0xb0]		! the caller's %pstate
	...
	ldx	[%g1 + 0xb0], %g2
	andn	%g2, PSTATE_IE, %g3
	stx	%g3, [%g1 + 0xb0]
	RESTORE_CPU_STATE(cif)
	...
	wrpr	%g2, %pstate			! just before jmp %o7
```

## Verification

Without the patch (firmware with our patches 0001-0011 or 0001-0015, QEMU 11.1.3), 4 of 7 boots of
the Tribblix live CD ended in items 1 and 2 above. With it, neither came back in about ten boots:
live CD boots with QEMU started directly and through Proxmox VE, one of them with a loop of 30
`prtconf -vp` and `eeprom` (both walk the firmware's device tree through the client interface)
and a complete install, and the installed system's first and later boots. NetBSD 11.1 and 9.3, OpenBSD 8.0's `bsd.rd`,
the Debian 12 installer (the lab's `sparc64` matrix, 9/9) and Solaris 10 1/13 (the `solaris10`
matrix: the DVD to its installer, the installed disk with DHCP and ping, 2/2) behave as before.

A side effect to keep in mind: Forth `ms` waits for `obp-ticks`, which only the firmware's own
tick handler advances. A client interface call that ends up in `ms` while interrupts are off
would wait forever. Once a client has taken over the trap table that was already the case
before this change (the firmware's tick handler no longer runs), and nothing in the boot paths we
tested calls `ms`.
