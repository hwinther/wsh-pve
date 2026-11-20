; AUDTEST.COM: the DOS side of the x86 audio matrix (e2e/audio/audio_matrix.py). Plays one known tone on
; each of the ISA sound devices qemu-server offers, one after the other, then powers the machine off
; through ACPI so QEMU exits and closes the wav file:
;
;   S  Sound Blaster 16 DSP: 1 s of 8-bit unsigned mono PCM at 16000 Hz by single-cycle DMA on
;      channel 1 (DSP command C0h), a 1000 Hz square wave
;   A  AdLib / OPL2 at 388h: channel 0, carrier only (the modulator fully attenuated), 440 Hz, 1 s
;   P  PC speaker: PIT channel 2 in mode 3 at 750 Hz (divisor 1591), gated through port 61h, 1 s
;
; Arguments pick the tests (any of S, A, P; none = all), e.g. `AUDTEST SAP` or `AUDTEST S`. The
; Sound Blaster resources are QEMU's defaults (iobase 0x220, irq 5, dma 1, dma16 5), which is what
; BLASTER=A220 I5 D1 H5 T6 says; the program does not read BLASTER. Interrupts are not used: the
; DSP's end-of-block IRQ 5 stays masked at the PIC (SeaBIOS masks it) and is acknowledged by reading
; 22Eh. A device that is not there is reported and skipped; the analysis of the wav file decides.
;
; Build: nasm -f bin -o AUDTEST.COM audtest.asm (Debian's nasm). Own code, no libraries.

        cpu     386
        org     100h

SB_BASE         equ     220h
SB_RATE         equ     16000
SB_LEN          equ     16000                   ; bytes = samples (8-bit mono): 1 s
SB_HALF         equ     8                       ; samples per half period: 16000 / 16 = 1000 Hz
PIT_DIV         equ     1591                    ; 1193182 / 1591 = 750 Hz
TONE_TICKS      equ     22                      ; ~1.2 s of BIOS ticks (18.2 Hz)
GAP_TICKS       equ     6                       ; ~0.3 s of silence between the tests

start:
        cld
        push    es
        mov     ax, 40h
        mov     es, ax
        mov     ax, [es:0]                      ; BIOS data area: COM1's port, 0 if none
        mov     [com1], ax
        pop     es
        mov     dx, msg_hello
        call    puts

        ; the command tail at 80h: length, then the text
        mov     si, 81h
        mov     cl, [80h]
        xor     ch, ch
        xor     bl, bl                          ; bit 0 = S, 1 = A, 2 = P
.arg:   jcxz    .argdone
        lodsb
        and     al, 0DFh                        ; upper case
        cmp     al, 'S'
        jne     .a1
        or      bl, 1
.a1:    cmp     al, 'A'
        jne     .a2
        or      bl, 2
.a2:    cmp     al, 'P'
        jne     .a3
        or      bl, 4
.a3:    dec     cx
        jmp     .arg
.argdone:
        test    bl, bl
        jnz     .have
        mov     bl, 7
.have:  mov     [tests], bl

        mov     cx, GAP_TICKS
        call    wait_ticks

        test    byte [tests], 1
        jz      .noS
        call    sb_test
        mov     cx, GAP_TICKS
        call    wait_ticks
.noS:   test    byte [tests], 2
        jz      .noA
        call    opl_test
        mov     cx, GAP_TICKS
        call    wait_ticks
.noA:   test    byte [tests], 4
        jz      .noP
        call    spk_test
        mov     cx, GAP_TICKS
        call    wait_ticks
.noP:
        mov     dx, msg_done
        call    puts
        call    acpi_off
        mov     dx, msg_nooff
        call    puts
        mov     ax, 4C00h
        int     21h

; ---------------------------------------------------------------------------------------------
; Sound Blaster 16

sb_test:
        mov     dx, msg_sb
        call    puts
        ; DSP reset: 1 to 226h, wait, 0, then AAh appears at 22Ah (22Eh bit 7 = data ready)
        mov     dx, SB_BASE + 6
        mov     al, 1
        out     dx, al
        mov     cx, 64
.rdl:   in      al, dx
        loop    .rdl
        xor     al, al
        out     dx, al
        call    dsp_read
        jc      .absent
        cmp     al, 0AAh
        jne     .absent
        ; version (E1h): major, minor
        mov     al, 0E1h
        call    dsp_write
        call    dsp_read
        jc      .absent
        mov     [sb_ver], al
        call    dsp_read
        jc      .absent
        mov     [sb_ver + 1], al
        mov     dx, msg_sbver
        call    puts
        mov     al, [sb_ver]
        call    puthex
        mov     al, '.'
        call    putc
        mov     al, [sb_ver + 1]
        call    puthex
        call    crlf

        ; the buffer: the first 64 KiB-aligned segment above the program's own 64 KiB segment
        ; (the stack is at its top; a DMA transfer must not cross a 64 KiB page); a COM program
        ; owns the memory after it
        mov     ax, cs
        add     ax, 1000h + 0FFFh
        and     ax, 0F000h
        cmp     ax, 9000h
        jae     .nomem
        mov     [buf_seg], ax
        mov     es, ax
        xor     di, di
        mov     cx, SB_LEN / (2 * SB_HALF)
.fill:  push    cx
        mov     al, 0C0h                        ; 128 + 64
        mov     cx, SB_HALF
        rep     stosb
        mov     al, 040h                        ; 128 - 64
        mov     cx, SB_HALF
        rep     stosb
        pop     cx
        loop    .fill
        push    cs
        pop     es

        ; 8237 channel 1: single transfer, memory to device, no auto-init
        mov     al, 05h                         ; mask channel 1
        out     0Ah, al
        xor     al, al
        out     0Ch, al                         ; clear the byte flip-flop
        mov     al, 49h                         ; single, increment, read, channel 1
        out     0Bh, al
        xor     al, al                          ; address 0 in the page
        out     02h, al
        out     02h, al
        mov     ax, [buf_seg]
        shr     ax, 12
        out     83h, al                         ; page register of channel 1
        mov     ax, SB_LEN - 1
        out     03h, al
        mov     al, ah
        out     03h, al
        mov     al, 01h                         ; unmask channel 1
        out     0Ah, al

        mov     al, 0D1h                        ; speaker on
        call    dsp_write
        mov     al, 41h                         ; output sample rate, high byte first
        call    dsp_write
        mov     al, SB_RATE >> 8
        call    dsp_write
        mov     al, SB_RATE & 0FFh
        call    dsp_write
        mov     al, 0C0h                        ; 8-bit DMA output, single cycle, FIFO off
        call    dsp_write
        mov     al, 00h                         ; mono, unsigned
        call    dsp_write
        mov     al, (SB_LEN - 1) & 0FFh
        call    dsp_write
        mov     al, (SB_LEN - 1) >> 8
        call    dsp_write

        mov     cx, TONE_TICKS
        call    wait_ticks

        mov     dx, SB_BASE + 0Eh               ; acknowledge the 8-bit IRQ
        in      al, dx
        mov     al, 0D3h                        ; speaker off
        call    dsp_write
        ; the channel's current count, for the log (the wav file decides)
        xor     al, al
        out     0Ch, al
        in      al, 03h
        mov     ah, al
        in      al, 03h
        push    ax
        mov     dx, msg_sbok
        call    puts
        pop     ax
        push    ax
        mov     al, ah
        call    puthex
        pop     ax
        call    puthex
        jmp     crlf
.nomem: mov     dx, msg_nomem
        jmp     puts
.absent:
        mov     dx, msg_sbnone
        jmp     puts

; AL to the DSP: wait for 22Ch bit 7 clear
dsp_write:
        push    cx
        push    dx
        push    ax
        mov     dx, SB_BASE + 0Ch
        mov     cx, 0FFFFh
.w:     in      al, dx
        test    al, 80h
        jz      .go
        loop    .w
.go:    pop     ax
        out     dx, al
        pop     dx
        pop     cx
        ret

; AL from the DSP; CF set on timeout
dsp_read:
        push    cx
        push    dx
        mov     cx, 0FFFFh
        mov     dx, SB_BASE + 0Eh
.w:     in      al, dx
        test    al, 80h
        jnz     .rd
        loop    .w
        stc
        jmp     .out
.rd:    mov     dx, SB_BASE + 0Ah
        in      al, dx
        clc
.out:   pop     dx
        pop     cx
        ret

; ---------------------------------------------------------------------------------------------
; AdLib / OPL2

opl_test:
        mov     dx, msg_opl
        call    puts
        ; detection by timer 1 (Adlib's documented method): the status shows C0h once it expires
        mov     ax, 6004h                       ; reset both timers
        call    opl_write
        mov     ax, 8004h                       ; reset the IRQ
        call    opl_write
        mov     dx, 388h
        in      al, dx
        and     al, 0E0h
        mov     [opl_s1], al
        mov     ax, 0FF02h                      ; timer 1 = FFh
        call    opl_write
        mov     ax, 2104h                       ; start timer 1
        call    opl_write
        mov     cx, 2                           ; >= 80 us
        call    wait_ticks
        mov     dx, 388h
        in      al, dx
        and     al, 0E0h
        mov     [opl_s2], al
        mov     ax, 6004h
        call    opl_write
        mov     ax, 8004h
        call    opl_write
        cmp     byte [opl_s1], 0
        jne     .nodet
        cmp     byte [opl_s2], 0C0h
        jne     .nodet
        mov     dx, msg_oplok
        call    puts
        jmp     .play
.nodet: mov     dx, msg_oplnone
        call    puts
.play:  ; play anyway: the wav file decides
        mov     si, opl_regs
.reg:   lodsw
        cmp     ax, 0FFFFh
        je      .on
        call    opl_write
        jmp     .reg
.on:    mov     ax, 3200h + 0B0h                ; key on, block 4, F-number high bits 2
        call    opl_write
        mov     cx, TONE_TICKS
        call    wait_ticks
        mov     ax, 1200h + 0B0h                ; key off
        call    opl_write
        ret

; AL = register, AH = value; the delays an OPL2 needs after the index and the data write
opl_write:
        push    cx
        push    dx
        push    ax
        mov     dx, 388h
        out     dx, al
        mov     cx, 6
.d1:    in      al, dx
        loop    .d1
        inc     dx
        mov     al, ah
        out     dx, al
        dec     dx
        mov     cx, 35
.d2:    in      al, dx
        loop    .d2
        pop     ax
        pop     dx
        pop     cx
        ret

; register, value pairs (as words: value in the high byte) for a plain 440 Hz sine on channel 0:
; F-number 580 at block 4 = 580 * 49716 / 2^16 = 440.0 Hz
opl_regs:
        dw      2001h                           ; waveform select enable
        dw      0008h, 00BDh                    ; CSM off, melodic mode
        dw      0120h                           ; modulator: multiple 1
        dw      3F40h                           ; modulator: fully attenuated (no FM)
        dw      0F060h                          ; modulator: attack F, decay 0
        dw      0FF80h                          ; modulator: sustain 15, release 15
        dw      2123h                           ; carrier: sustained, multiple 1
        dw      0043h                           ; carrier: full level
        dw      0F063h                          ; carrier: attack F, decay 0
        dw      0583h                           ; carrier: sustain level 0 (loudest), release 5
        dw      00E0h, 00E3h                    ; sine waveforms
        dw      00C0h                           ; FM, no feedback
        dw      44A0h                           ; F-number low byte (580 = 244h)
        dw      0FFFFh

; ---------------------------------------------------------------------------------------------
; PC speaker

spk_test:
        mov     dx, msg_spk
        call    puts
        mov     al, 0B6h                        ; channel 2, lo/hi, mode 3, binary
        out     43h, al
        mov     ax, PIT_DIV
        out     42h, al
        mov     al, ah
        out     42h, al
        in      al, 61h
        or      al, 03h                         ; gate on, speaker data on
        out     61h, al
        mov     cx, TONE_TICKS
        call    wait_ticks
        in      al, 61h
        and     al, 0FCh
        out     61h, al
        ret

; ---------------------------------------------------------------------------------------------
; ACPI soft-off (S5): PM1a_CNT = PMBASE + 4, SLP_EN | SLP_TYP 0 (QEMU's \_S5). PMBASE is read from
; the PIIX4 PM function (00:01.3, i440fx) or the ICH9 LPC bridge (00:1f.0, q35), register 40h.

acpi_off:
        mov     eax, 80000B00h                  ; 00:01.3, register 00h
        call    pci_read
        cmp     eax, 71138086h
        je      .piix
        mov     eax, 8000F800h                  ; 00:1f.0
        call    pci_read
        cmp     eax, 29188086h
        jne     .none
        mov     eax, 8000F840h
        jmp     .base
.piix:  mov     eax, 80000B40h
.base:  call    pci_read
        and     ax, 0FFC0h
        jz      .none
        mov     dx, ax
        add     dx, 4
        mov     ax, 2000h
        out     dx, ax
        mov     cx, 10                          ; QEMU exits; if not, return to DOS
        call    wait_ticks
.none:  ret

pci_read:                                       ; EAX = config address, returns the dword
        mov     dx, 0CF8h
        out     dx, eax
        mov     dx, 0CFCh
        in      eax, dx
        ret

; ---------------------------------------------------------------------------------------------
; helpers

; wait CX BIOS timer ticks (0040:006C, 18.2 Hz)
wait_ticks:
        push    es
        push    ax
        push    bx
        sti
        mov     ax, 40h
        mov     es, ax
.t:     mov     bx, [es:6Ch]
.s:     cmp     bx, [es:6Ch]
        je      .s
        loop    .t
        pop     bx
        pop     ax
        pop     es
        ret

puts:                                           ; DX = '$'-terminated string
        push    ax
        push    si
        mov     si, dx
.c:     lodsb
        cmp     al, '$'
        je      .e
        call    putc
        jmp     .c
.e:     pop     si
        pop     ax
        ret

; AL to the screen (DOS) and, when the BIOS found a COM1, to its UART too (polled, with a timeout,
; so a missing or stuck port never stalls the tones): the harness reads it from QEMU's -serial file
putc:
        push    ax
        push    bx
        push    cx
        push    dx
        mov     bl, al
        mov     dl, al
        mov     ah, 02h
        int     21h
        mov     dx, [com1]
        test    dx, dx
        jz      .out
        add     dx, 5                           ; line status: bit 5 = transmit holding register empty
        mov     cx, 0FFFFh
.w:     in      al, dx
        test    al, 20h
        jnz     .tx
        loop    .w
        jmp     .out
.tx:    sub     dx, 5
        mov     al, bl
        out     dx, al
.out:   pop     dx
        pop     cx
        pop     bx
        pop     ax
        ret

crlf:
        push    dx
        mov     dx, msg_crlf
        call    puts
        pop     dx
        ret

puthex:                                         ; AL as two hex digits
        push    ax
        shr     al, 4
        call    .nib
        pop     ax
        push    ax
        and     al, 0Fh
        call    .nib
        pop     ax
        ret
.nib:   add     al, '0'
        cmp     al, '9'
        jbe     .p
        add     al, 7
.p:     jmp     putc

msg_hello       db      'AUDTEST: wsh-pve audio matrix', 13, 10, '$'
msg_sb          db      'SB16: ', '$'
msg_sbver       db      'DSP version ', '$'
msg_sbnone      db      'no DSP at 220h', 13, 10, '$'
msg_sbok        db      'SB16: 1000 Hz PCM played, DMA 1 count now ', '$'
msg_nomem       db      'SB16: no DMA buffer below 9000:0', 13, 10, '$'
msg_opl         db      'OPL2: ', '$'
msg_oplok       db      'detected at 388h, 440 Hz', 13, 10, '$'
msg_oplnone     db      'not detected at 388h (playing anyway)', 13, 10, '$'
msg_spk         db      'PC speaker: 750 Hz', 13, 10, '$'
msg_done        db      'AUDTEST: done', 13, 10, '$'
msg_nooff       db      'AUDTEST: ACPI power off did not happen', 13, 10, '$'
msg_crlf        db      13, 10, '$'

tests           db      0
opl_s1          db      0
opl_s2          db      0
sb_ver          db      0, 0
buf_seg         dw      0
com1            dw      0

prog_end:
