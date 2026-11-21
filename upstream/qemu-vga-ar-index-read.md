# QEMU: port 0x3c0 reads 0 in the attribute controller's data state (The Incredible Machine shows a black screen)

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Carried in pve-qemu as `debian/patches/wsh/0051`, with the qtest
`wsh/0052`; not in a published package yet. Our own finding in QEMU's code, independent of LEMU
(column "may send" in [README.md](README.md)). Found with the owner's DOS games in the x86 lab
([DOS guide](../docs/src/content/docs/guides/dos.md), "Known issues").

**Reproduced on plain QEMU** (2026-11-21): `qemu-system-x86_64` built from the v11.1.3 tag (a clean
checkout, `--target-list=x86_64-softmmu`, no patch of ours), `-M pc -vga std` and `-vga cirrus`:

- a 512-byte boot sector (below) sets mode 13h, draws colour bars, then runs the game's sequence. The
  value it saves reads back as `0x00`, and from then on the screen is black (screendump: 0 of 256000
  pixels not black; before the sequence all of them are);
- The Incredible Machine and The Incredible Machine 2 under MS-DOS 6.22 on `-vga std`: black for
  the whole run (every screendump black, two distinct frames in 45 s; with our series but without
  the change the same, and The Incredible Machine also on `-vga cirrus`);
- the qtest below fails in all 8 cases (std VGA, isa-vga, cirrus-vga, vmware-svga; two cases each).

The same tree with only the change described below: the boot sector saves `0x20` and the bars stay,
both games show their screens (18 and 21 distinct frames in 45 s), and the qtest passes 8 of 8.

## Summary

The VGA attribute controller has one port, 0x3c0, for its address and its data writes. A flip-flop
says which a write is; a read of input status 1 (0x3da) resets it to the address state. The address
register, with bit 5, the palette address source (PAS: 0 while the palette is loaded, 1 for normal
display), reads back at 0x3c0. QEMU returns it only in the address state; in the data state a read
of 0x3c0 returns 0.

A VGA port trace of The Incredible Machine on plain QEMU 11.1.3 (`-trace
enable=vga_std_*_io`), right after it sets its graphics mode:

```
read  0x3da                 flip-flop to the address state
read  0x3c0 -> 0x20         save the address (address state: correct)
write 0x3c0 0x10            index 0x10, mode control
read  0x3c1 -> 0x01
write 0x3c0 0x81            mode control |= 0x80 (flip-flop back to the address state)
write 0x3c0 0x20            index 0 with PAS (flip-flop now in the data state)
read  0x3c0 -> 0x00         save the address again: the VGA returns 0x20, QEMU 0
read  0x3da, write 0x3c0 0x0f, write 0x3c0 0x0f     palette register 15 = 15
...                                                 down to
read  0x3da, write 0x3c0 0x01, write 0x3c0 0x01     palette register 1 = 1
write 0x3c0 0x00            restore the saved address (address state): PAS cleared
```

That is the only read of 0x3c0 in the data state in the whole trace (DOS's boot and 25 s of the
game; 65 reads of 0x3c0 in all).
With 0 saved, the restore clears PAS. QEMU draws a blank screen whenever PAS is clear
(`vga_update_display()` and `vga_update_text()` test `ar_index & 0x20`), so the screen stays black
for as long as the game runs, while the game itself carries on (the lab records 44 s of sound from
The Incredible Machine 2 with and without the change). The Incredible Machine 2 was not traced; it
shows the same black screen and the same change fixes it.

- **Affected:** every device built on QEMU's common VGA port code, `vga_ioport_read()` (std VGA,
  `isa-vga`, `vmware-svga`, and from the code also `vga-mmio`, `qxl-vga`, `virtio-vga` and
  `ati-vga`), and `cirrus-vga`, which has its own copy of the same code (std, isa, vmware and cirrus
  tested). QEMU 11.1.3 and, from the code, many releases before it (not checked how far back).
- **Who to tell:** `MAINTAINERS`, "Standard VGA" (`hw/display/vga*`); `cirrus_vga.c` has no entry of
  its own there.

## What the hardware does

- IBM's VGA technical reference (a text copy:
  <https://www.read.seas.harvard.edu/~kohler/class/04f-aos/ref/hardware/ibm-vga.txt>), Attribute
  Address register: "This read/write register is at address 0x03C0"; the flip-flop "toggles for each
  Write operation to address 0x03C0. It does not toggle for Read operations to 03C0 or 03C1."; bit 5,
  IPAS, "is set to 0 to load color values to the registers in the internal palette. It is set to 1
  for normal operation of the attribute controller."
- OS/2 Museum, "The VGA Attribute Controller Is Weird" (2024-05-03,
  <http://www.os2museum.com/wp/learn-something-old-every-day-part-x-the-vga-attribute-controller-is-weird/>):
  on the VGA "reading port 3C0h returns the current attribute controller index register", and it
  describes the same bug in an unnamed emulator, which "erroneously applied the flip-flop state to
  reads from port 3C0h", with a blank screen (bit 5 of the index not set) as the result.
- FreeVGA, "Accessing the VGA Registers": "The address register is read and written via port 3C0h.
  The data register is written to port 3C0h and read from port 3C1h." No flip-flop condition for the
  read. It also says there is no standard way to read the flip-flop (IBM's VGA has an undocumented
  CRTC index 24h bit 7 for it), so a program that wants to restore the attribute address can't
  rely on knowing the flip-flop state when it reads 0x3c0.
- DOSBox Staging: `read_p3c0()` in `vga_attr.cpp` returns the index with bit 5 set while the palette
  is not being loaded, and neither checks nor toggles the flip-flop.
- QEMU's own Cirrus code already models the CL-GD54xx readbacks of the same state: CR24 (the
  flip-flop) and CR26 (the attribute index), so a driver on that chip can read the index in either
  state there too.

Ralf Brown's port list was not checked. QEMU's tracker was searched only by a web search (no match
for the game or for this read); <https://gitlab.com/qemu-project/qemu/-/issues> itself not yet.

## Where in the code

`hw/display/vga.c`, `vga_ioport_read()`:

```c
        case VGA_ATT_W:
            if (s->ar_flip_flop == 0) {
                val = s->ar_index;
            } else {
                val = 0;
            }
            break;
```

and the same in `hw/display/cirrus_vga.c`, `cirrus_vga_ioport_read()`, `case 0x3c0`. QEMU keeps PAS
inside `ar_index` (the write path stores `val & 0x3f`), so `ar_index` is exactly the register to
return.

## Fix (in prose)

Return `s->ar_index` for a read of 0x3c0 in both states of the flip-flop, in `vga.c` and in
`cirrus_vga.c`; the read doesn't change the flip-flop. Reads of 0x3c1 (the data register at
`ar_index & 0x1f`), the write path and the reset of the flip-flop by 0x3da stay as they are. No
migration change: no state is added.

Tested in our lab with that change (11.1.3 with our series): The Incredible Machine and The
Incredible Machine 2 show their screens on `-vga std` and `-vga cirrus`; the owner's other DOS games
(Doom, Doom II, Duke Nukem 3D, Wolfenstein 3D with `-vga std,retrace=precise`, Commander Keen 1 and
4, Leisure Suit Larry 1, Dune, Dune II) end on the same screen as without the change (the same
screendump for Wolfenstein 3D, both Keens, Larry, Dune and Dune II; Doom, Doom II and Duke Nukem 3D
run their demos, 42-64 distinct frames with and without), and the installed MS-DOS 6.22 and
FreeDOS 1.4 disks boot and pass their checks on std and cirrus.

## A test without a guest

`tests/qtest/vga-ar-index-test.c` (wsh/0052), port I/O on `-M pc` with `-device VGA`, `isa-vga`,
`cirrus-vga` and `vmware-svga` (each when built in), after setting the miscellaneous output register
to colour mode (no BIOS runs under qtest):

- **read:** read 0x3da, write `0x31` (PAS and the overscan index) to 0x3c0; 0x3c0 must read `0x31`
  twice (data state; the read must not toggle the flip-flop), the next write must land in the
  overscan register (read back through 0x3c1), and 0x3c0 must read `0x31` in the address state
  too; then the same without PAS (palette register 5);
- **palette-load:** the game's sequence above; the saved value must be `0x20`, PAS must be set
  afterwards in both states, and the palette registers (all 16 in the test) must hold what was
  written.

## Reproducing with a boot sector

Assembled with GNU as (`as --32`, `ld -m elf_i386 -Ttext 0x7c00 --oformat binary`), written to the
start of a 1.44 MB floppy image, booted with `-M pc -vga std -drive if=floppy,format=raw,file=...
-debugcon file:dbg.txt -monitor stdio`; the two bytes in `dbg.txt` are the saved value and the
address read back at the end, and `screendump` at 3 s (before the sequence) and 12 s (after) shows
the bars and then black.

```asm
        .code16
_start: cli
        xor %ax, %ax
        mov %ax, %ds
        mov %ax, %ss
        mov $0x7c00, %sp
        sti
        mov $0x0013, %ax        # mode 13h
        int $0x10
        mov $0xa000, %ax        # colour bars: pixel = x / 20 + 32
        mov %ax, %es
        xor %di, %di
        mov $200, %bx
row:    xor %cx, %cx
col:    mov %cx, %ax
        push %bx
        mov $20, %bl
        div %bl
        pop %bx
        add $32, %al
        stosb
        inc %cx
        cmp $320, %cx
        jne col
        dec %bx
        jnz row
        mov $0x86, %ah          # wait ~6 s
        mov $0x0060, %cx
        xor %dx, %dx
        int $0x15
        mov $0x3da, %dx         # flip-flop to address
        in %dx, %al
        mov $0x3c0, %dx
        mov $0x20, %al          # PAS, index 0
        out %al, %dx
        in %dx, %al             # save the address (data state)
        mov %al, %bl
        mov $0xe9, %dx
        out %al, %dx
        xor %cl, %cl
pal:    mov $0x3da, %dx         # palette register i = i
        in %dx, %al
        mov $0x3c0, %dx
        mov %cl, %al
        out %al, %dx
        out %al, %dx
        inc %cl
        cmp $16, %cl
        jne pal
        mov $0x3da, %dx         # restore the saved address
        in %dx, %al
        mov $0x3c0, %dx
        mov %bl, %al
        out %al, %dx
        mov $0x3da, %dx         # read it back (address state)
        in %dx, %al
        mov $0x3c0, %dx
        in %dx, %al
        mov $0xe9, %dx
        out %al, %dx
hang:   hlt
        jmp hang
        .org 510
        .byte 0x55, 0xaa
```

Plain v11.1.3: `dbg.txt` holds `00 00`, the second screendump is black. With the change: `20 20`
and the bars.
