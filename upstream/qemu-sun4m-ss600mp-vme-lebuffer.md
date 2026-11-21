# sun4m SS-600MP: no VMEbus interface registers, and the lance has an ledma instead of its lebuffer

Material for a bug report to upstream QEMU and OpenBIOS, for the owner to write and send by hand
(neither takes AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0063` (the VME
registers), `0064` (the lebuffer) and the qtest `0065`, and in `openbios/patches/0028` (the node
names); not in a published package yet. Our own finding in QEMU's and OpenBIOS's code, independent
of LEMU (column "may send" in [README.md](README.md)). Tested in the lab with SunOS 4.1.2, the first
release for the SPARCserver 600MP (`submodules/SPARC.md`, "Older Sun releases on sun4m").

**Plain QEMU:** not tried on plain 11.1.3; the code involved is the same there (our series changes
neither the SS-600MP's hwdef nor the bypass ASIs' trap, and its OpenBIOS has the same node names).

## What happens

On `-M SS-600MP` with OpenBIOS, SunOS 4.1.2's CD kernel loads and stops before its banner with
`Unhandled Exception 0x00000029` at `pc f80a6054` (OpenBIOS's trap handler). For machine type 0x71
the kernel clears the SBus and ECC fault registers and then reads, changes and writes back the
VMEbus interface's control register at physical `0xf.df01_0000` (it also touches `+4` and `+8`),
with `lda`/`sta` in the MMU bypass ASI 0x2f. `hw/sparc/sun4m.c`'s `ss600mp_hwdef` has nothing
there.

With that page answering, the kernel prints its banner and runs its installer, but attaches no disk
and no network interface: it finds the ESP only under a node named `dma` and the lance only under
an `lebuffer`, the buffer memory the 600MP's lance works in (SBus slot f offset `0x40000`, below
the lance at `0x60000`). OpenBIOS gives machine ID 66 the SS-10's `espdma` and `ledma`
(`drivers/sbus.c` even notes that `SS600MP_LEBUFFER` "should be 0x40000"), and QEMU gives the
lance the SS-10's ledma and DVMA. A lance node directly on the SBus is refused (`le0: not used -
unsupported SBus card for this architecture!`).

## The changes

- QEMU 0063: an unimplemented device over `0xf.df01_0000`-`0fff` on the SS-600MP (no VMEbus model;
  the VME spaces stay empty, so the kernel's probes find no VME device).
- QEMU 0064: a `lebuffer-size` property on `sparc32-dma`. When set, the lance's DMA goes to a RAM
  region of that size (its address modulo the size) in an address space of its own, mapped for the
  CPU through an alias, and its interrupt bypasses the ledma's interrupt enable. The SS-600MP sets
  128 KB at `0xe.f004_0000`.
- OpenBIOS 0028: on machine ID 66 the DMA node is `dma` (with `ob_esp_init()` taking its path) and
  the lance's parent `lebuffer` (`reg` slot f `0x40000` size `0x20000`).

With all three SunOS 4.1.2 installs and boots (`SunOS sunos412 4.1.2 1 sun4m`) and `le0` answers
ping over user networking. The SS-5, SS-10, SS-20 and LX are unchanged (qtest `sun4m-ss600mp-test`,
wisp on the four machines, Solaris 2.6 on the SS-5 and SunOS 4.1.3_U1B on the SS-20 with ping).

## Also

With `-smp 2` CPU 1 panics in the kernel's `check_cpuid`: it expects the MBus module ID in bits
15-16 of the MMU control register, as the 600MP's Ross modules have it. QEMU's SS-600MP has
SuperSPARC CPUs only, so that needs a Ross CPU model; not attempted.
