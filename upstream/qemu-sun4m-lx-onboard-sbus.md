# sun4m LX: the on-board cgsix, DBRI and bpp are missing, and the LX boot PROM stops at `ok`

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0056` (the devices),
`0057` (the DBRI's FCode PROM, see [qemu-sun4m-ss20-dbri-unnamed-node.md](qemu-sun4m-ss20-dbri-unnamed-node.md))
and the qtest `0058`; not in a published package yet. Our own finding in QEMU's code, independent
of LEMU (column "may send" in [README.md](README.md)). Tested in the lab (`submodules/SPARC.md`,
"SPARCstation LX with its own PROM").

**Plain QEMU:** on QEMU 11.1.3 the LX boot PROM doesn't get this far: its POST stops earlier, at
the FPU test that wants a deferred fp_exception ([qemu-sparc32-deferred-fp-exception.md](qemu-sparc32-deferred-fp-exception.md)).
What follows was seen with our series up to 0055, which has that fix and nothing else in the code
below. The missing regions themselves are visible on plain QEMU with `info mtree` on `-M LX`.

## What happens

The SPARCstation LX (4/30) has three SBus devices on the board: a cgsix (GX) frame buffer in slot
3, the DBRI (ISDN + CS4215 audio) in slot 2 and a parallel port (bpp, with its DMA) in slot 4,
offset `0xc800000`. Its boot PROM (OBP 2.10) carries the FCode for slots 2, 3 and 4 itself and runs
it on every boot, with or without a monitor or keyboard. A public map of that PROM and the
detokenized cgsix FCode are in [mdehling/sslx-vesa-mod](https://github.com/mdehling/sslx-vesa-mod).

`hw/sparc/sun4m.c`'s `ss_lx_hwdef` has none of the three. With `-M LX -m 64 -nographic -bios
<the LX PROM>`:

- with `-vga none` the slot 2 FCode, which byte-loads the DBRI's own FCode PROM from slot offset
  `0x1000`, takes a data access error: `Probing /iommu@0,10000000/sbus@0,10001000 at 2,0  Data
  Access Error`, then `ok`;
- with QEMU's default TCX in slot 2 the TCX's ROM answers there, and the cgsix FCode's first write
  (the THC, slot 3 offset `0x301094`) takes the error: `... at 3,0  cgsix Data Access Error`, `ok`.

The error ends the PROM's start-up: no banner, no boot (`boot disk` from that `ok` gets `Data
Access Exception`). With the slot 3 window answering, the PROM prints its banner and then takes
another error when it sets the DBRI's reset bit (a store to slot 2 offset `0x10000`). With the
whole of slot 2 and 3 answering, NetBSD 9.3 panics in `bppattach()` (`trap 0x29 ... sfva=0x7c800000`,
`lsi64854_attach` reading the bpp's DMA CSR).

## The change (0056)

`-M LX` gets the same treatment the SS-20 already has for its DBRI and bpp
(`create_unimplemented_device`):

- `dbri_base = 0x50000000`: the DBRI's PROM window at `+0x1000` and its registers at `+0x10000`;
- `bpp_base = 0x7c800000`;
- a new hwdef field `cg6_base = 0x60000000`, 16 MB of unimplemented device (the size of the
  cgsix FCode's `reg`).

Unimplemented devices map at priority -1000, so the TCX or cg3 that `-vga` puts at
`tcx_base = 0x50000000` (also slot 2 on the LX) keeps its addresses. With this the PROM probes all
slots, prints its banner and boots: Solaris 2.6 and NetBSD 9.3 to a login prompt over ttya. The
cgsix node is made from zeros: NetBSD attaches `cgsix0` (rev 0, 1 MB) as a second display,
Solaris 2.6's `cgsix` driver fails to attach, SunOS 4.1.4 attaches it without a console on it; none
hangs. OpenBIOS on `-M LX` boots as before (its probe of `0x60000000` now prints `Invalid FCode
start byte` instead of nothing).

What remains is the DBRI's node: QEMU's PROM window reads 0, so the PROM's node has no `name` or
`reg`, and SunOS 4.1.4 panics on it. That is the SS-20 report's problem; 0057 answers the window
with a small FCode program ([qemu-sun4m-ss20-dbri-unnamed-node.md](qemu-sun4m-ss20-dbri-unnamed-node.md)).

## Tested

qtest `sun4m-onboard-sbus-test` (0058): the three regions on `-M LX` at their addresses and
priority, the default TCX's ROM above them, none on the SS-5; fails without 0056. The LX PROM boots
Solaris 2.6 (installed from CD), NetBSD 9.3, SunOS 4.1.4 and 4.1.3_U1B (with 0057), with 64 and
128 MB. Stored SS-5, SS-10 and SS-20 disks boot as before.

## Reproducing

```sh
qemu-system-sparc -nodefaults -M LX -m 64 -bios <the LX PROM> -nographic -net nic,model=lance
# stops at ok after "at 2,0  Data Access Error"; without -nodefaults (TCX in slot 2) after
# "at 3,0  cgsix Data Access Error"
```

The PROM is Sun's and isn't in QEMU; the report would have to say that it was seen with Sun's PROM
only, and on our series because of the POST fix.
