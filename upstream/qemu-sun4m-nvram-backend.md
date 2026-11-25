# sun4m: the NVRAM is rewritten at every start, so Sun's boot PROMs never boot by themselves

Material for a bug report or feature request to upstream QEMU, for the owner to write and send by
hand (QEMU doesn't take AI-written code or text). Carried in pve-qemu as
`debian/patches/wsh/0059` (the drive and the sun4m change) and the qtest `0060`. Since 2026-11-25
0059 is the form LEMU ported onto its own `m48t59` storage code (`wsh/0073`, LEMU origin), so the
carried patch is built on LEMU and not for QEMU ([README.md](README.md)); "The change" below
describes the earlier write-through version, our own and independent of LEMU, which is what a
patch to QEMU would have to start from again. The problem itself is plain QEMU's. Tested in the lab
(`submodules/SPARC.md`, "The NVRAM kept in a volume").

## What happens

`hw/sparc/sun4m.c`'s `nvram_init()` writes OpenBIOS's layout into the M48T08 (8 KB) at every
machine start: a CHRP system partition with the `-prom-env` variables at offset 0, a free partition
after it, and the Sun IDPROM (format, machine type, MAC address, host ID, checksum) at `0x1fd8`.
Nothing keeps the NVRAM across QEMU runs; `system_reset` keeps it, a new process doesn't.

OpenBIOS is fine with that: its variables come from `-prom-env` and its boot device from fw_cfg.
Sun's own boot PROMs, which `-bios` runs on `-M SS-5` (`ss5.bin`), `-M SS-20` (`ss20_v2.25_rom`)
and `-M LX` (the LX PROM, OBP 2.10), keep their configuration in the same bytes in their own format.
On every power-on they print

```text
Incorrect configuration checksum;
Setting NVRAM parameters to default values.
Setting diag-switch? NVRAM parameter to true
```

and, with `diag-switch?` true, boot `diag-device` (`net`), which fails, and stop at `ok`. A real
machine keeps what `setenv diag-switch? false` (or `auto-boot?`, `boot-device`) stored; under QEMU
it lasts until the process exits, so every start needs someone to type `boot disk`.

What the dumps show (the NVRAM read with `pmemsave` at `0x71200000` on `-M LX`): byte 0 is an XOR
checksum, byte 1 is `diag-switch?` (`0xff` true, `0x00` false) and outside the checksum, the other
variables at fixed offsets from `0x29e`. The PROM writes only its variables and the checksum: after
its defaults, the rest of QEMU's CHRP headers is still there. It never writes the IDPROM.

## The change (0059)

- The sysbus M48Txx (`sysbus-m48t02/08/59`) gets a `drive` property (`DEFINE_PROP_DRIVE`) for its
  NVRAM bytes, the clock registers left out (`0x7f8`, `0x1ff8` and `0x1ff0` bytes). The image is
  read at realize; every byte the guest changes is written through with `blk_pwrite()` (one byte,
  only when it changed), as `macio-nvram` does. The image must hold at least the NVRAM; larger
  images are fine (the first bytes are used). A read-only image is loaded and not written.
- A blank image (all zero) leaves the NVRAM as without a drive, so the board writes its default
  contents, which go through to the image. Any other image is "restored": the guest left it so.
- `nvram_init()` on sun4m leaves a restored NVRAM alone and writes only the IDPROM, from the command
  line, on every start: the machine's identity follows `-M` and the NIC's MAC address, and the Sun
  PROMs' checksum doesn't cover it (a start with another MAC still boots by itself). With
  `-prom-env` the OpenBIOS partitions are written on every start, as without a drive, so
  `-prom-env` keeps applying.
- The M48T08 is added as the machine's child `nvram`, so `query-block` names the device of the
  drive `/machine/nvram` (management tools map drives to devices by that path).

Usage:

```sh
qemu-img create -f raw nvram.raw 8K
qemu-system-sparc -M LX -bios <the LX PROM> -nographic ... \
  -drive if=none,id=nvram0,format=raw,file=nvram.raw -global sysbus-m48t08.drive=nvram0
```

Without a drive nothing changes. sun4u's `sysbus-m48t59` gets the property too, but `sun4u.c`
still writes its contents at every start; it isn't wired up there.

## Tested

- qtest `sun4m-nvram-test` (0060), on the SS-5: no drive (as before); a blank image gets QEMU's
  contents and keeps them; other contents are left alone across two starts, the guest's writes
  reach the image, the clock registers aren't stored, the IDPROM follows the MAC address;
  `-prom-env` rewrites the OpenBIOS partitions; a larger image keeps its tail; `-blockdev` by node
  name and the `/machine/nvram` path in `query-block`; a read-only image. `m48t59-test` and
  `prom-env-test` pass as before.
- LX PROM with Solaris 2.6 (lab, QEMU 11.1.3 with our series): first start on a blank 8 KB image
  stops at `ok` as before; `setenv diag-switch? false`; the next start boots the disk to `login:`
  without input (80 s), also with another MAC address on the next.
- The same through Proxmox VE for the LX and SS-5 PROMs, and OpenBIOS with and without the drive
  (`submodules/SPARC.md`). The SS-20 PROM boots the disk by itself too, but Solaris 2.6 then stops
  QEMU (`Trap 0x29 ... while interrupts disabled`); that happens without the drive as well when the
  PROM boots by itself after `setenv diag-switch? false` and `reset`, so it is a separate problem:
  the ledma's reset value ([qemu-sun4m-ledma-base-address-reset.md](qemu-sun4m-ledma-base-address-reset.md)).

## Open questions for upstream

- Whether a machine property (`-machine nvram=<node>`) would be preferred to `-global`.
- Whether sun4u should get the same treatment (its NVRAM is OpenBIOS-only today).
- Whether the IDPROM refresh should stay unconditional (it is what a real machine's identity chip
  does not do: there the IDPROM is fixed at manufacture).
