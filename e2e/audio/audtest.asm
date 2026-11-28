; AUDTEST.COM: the DOS side of the x86 audio matrix (e2e/audio/audio_matrix.py). Plays known tones on
; each of QEMU's ISA sound devices, one after the other, then powers the machine off through ACPI so
; QEMU exits and closes the wav file:
;
;   S  Sound Blaster 16 DSP: 1 s of 8-bit unsigned mono PCM at 16000 Hz by single-cycle DMA on
;      channel 1 (DSP command C0h), a 1000 Hz square wave
;   A  AdLib / OPL2 at 388h: channel 0, carrier only (the modulator fully attenuated), 440 Hz, 1 s
;   P  PC speaker: PIT channel 2 in mode 3 at 750 Hz (divisor 1591), gated through port 61h, 1 s
;   G  Gravis Ultrasound GF1 at 240h (QEMU's `gus`): reset, a 40-sample sine period written into
;      DRAM byte by byte through the DRAM I/O port (3x7h), then two looping 8-bit voices on it:
;      voice 0 panned hard left at FC 512 (half a sample per frame at 14 voices / 44100 Hz:
;      551.25 Hz), voice 1 hard right at FC 1024 (1102.5 Hz), 1 s. No DMA, no IRQ.
;   C  Crystal CS4231A (Windows Sound System codec) at 534h (QEMU's `cs4231a`): MODE2, outputs
;      unmuted, a mode change (MCE) to 16-bit signed stereo at 16000 Hz, then auto-init DMA on
;      channel 3 of a buffer with an 800 Hz square wave on the left and 1600 Hz on the right, 1 s.
;      The codec's interrupt stays disabled (IEN off), playback is stopped by clearing PEN. QEMU's
;      codec plays by DMA only (PIO playback isn't emulated) and has no WSS configuration register
;      at 530h, so none is written.
;
; Arguments pick the tests (any of S, A, P, G, C; none = all), e.g. `AUDTEST SAPGC` or `AUDTEST G`. The
; Sound Blaster resources are QEMU's defaults (iobase 0x220, irq 5, dma 1, dma16 5), which is what
; BLASTER=A220 I5 D1 H5 T6 says; the program does not read BLASTER. Interrupts are not used: the
; DSP's end-of-block IRQ 5 stays masked at the PIC (SeaBIOS masks it) and is acknowledged by reading
; 22Eh. The GUS and the CS4231A are at QEMU's defaults too (GUS 240h, IRQ 7, DMA 3; CS4231A 534h,
; IRQ 9, DMA 3). A device that is not there is reported and skipped; the analysis of the wav file
; decides.
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
GUS_BASE        equ     240h
GUS_VOICE       equ     GUS_BASE + 102h         ; 342h: voice select
GUS_SEL         equ     GUS_BASE + 103h         ; 343h: register select
GUS_DLO         equ     GUS_BASE + 104h         ; 344h: data low byte
GUS_DHI         equ     GUS_BASE + 105h         ; 345h: data high byte (the byte registers)
GUS_DRAM        equ     GUS_BASE + 107h         ; 347h: DRAM I/O
GUS_WAVE        equ     32                      ; DRAM address of the sine period
GUS_WAVE_LEN    equ     40                      ; its samples
GUS_FC_L        equ     512                     ; 0.5 sample per frame: 44100 / 80 = 551.25 Hz
GUS_FC_R        equ     1024                    ; 1 sample per frame: 44100 / 40 = 1102.5 Hz
GUS_VOL         equ     0F000h                  ; exponent 15, mantissa 0
CS_BASE         equ     534h                    ; index; +1 data, +2 status
CS_FORMAT       equ     52h                     ; I8: 16-bit signed LE, stereo, XTAL1 / divider 1 = 16000 Hz
CS_FRAMES       equ     4000                    ; 1/4 s: the DMA buffer auto-init repeats
CS_LHALF        equ     10                      ; frames per half period: 16000 / 20 = 800 Hz
CS_RHALF        equ     5                       ; 16000 / 10 = 1600 Hz
CS_AMP          equ     8000
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
        xor     bl, bl                          ; bit 0 = S, 1 = A, 2 = P, 3 = G, 4 = C
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
.a3:    cmp     al, 'G'
        jne     .a4
        or      bl, 8
.a4:    cmp     al, 'C'
        jne     .a5
        or      bl, 16
.a5:    dec     cx
        jmp     .arg
.argdone:
        test    bl, bl
        jnz     .have
        mov     bl, 31
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
.noP:   test    byte [tests], 8
        jz      .noG
        call    gus_test
        mov     cx, GAP_TICKS
        call    wait_ticks
.noG:   test    byte [tests], 16
        jz      .noC
        call    cs_test
        mov     cx, GAP_TICKS
        call    wait_ticks
.noC:
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

        call    dma_buffer
        jc      .nomem
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

; The DMA buffer: the first 64 KiB-aligned segment above the program's own 64 KiB segment (the
; stack is at its top; a DMA transfer must not cross a 64 KiB page); a COM program owns the memory
; after it. AX = [buf_seg] = the segment; CF set when it would be at 9000h or above.
dma_buffer:
        mov     ax, cs
        add     ax, 1000h + 0FFFh
        and     ax, 0F000h
        cmp     ax, 9000h
        cmc
        jc      .out
        mov     [buf_seg], ax
.out:   ret

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
; Gravis Ultrasound (GF1)

gus_test:
        mov     dx, msg_gus
        call    puts
        ; reset (register 4Ch = 0), then out of reset with the DAC off (1)
        mov     ax, 004Ch
        call    gus_w8
        mov     cx, 1
        call    wait_ticks
        mov     ax, 014Ch
        call    gus_w8
        mov     cx, 1
        call    wait_ticks
        ; two bytes into DRAM and back: an empty port reads FFh
        xor     bx, bx
        mov     al, 55h
        call    gus_poke
        inc     bx
        mov     al, 0AAh
        call    gus_poke
        dec     bx
        call    gus_peek
        cmp     al, 55h
        jne     .absent
        inc     bx
        call    gus_peek
        cmp     al, 0AAh
        jne     .absent
        xor     bx, bx
        xor     al, al
        call    gus_poke
        inc     bx
        call    gus_poke
        ; the sine period and one more sample (its first again: a voice interpolates towards the
        ; byte after the loop end), byte by byte through the DRAM I/O port
        mov     si, gus_wave
        mov     bx, GUS_WAVE
        mov     cx, GUS_WAVE_LEN + 1
.up:    lodsb
        call    gus_poke
        inc     bx
        loop    .up
        ; read it back
        mov     si, gus_wave
        mov     bx, GUS_WAVE
        mov     cx, GUS_WAVE_LEN + 1
.vfy:   call    gus_peek
        cmp     al, [si]
        jne     .bad
        inc     si
        inc     bx
        loop    .vfy

        mov     ax, 0CD0Eh                      ; 14 active voices (C0h | 13): 44100 Hz
        call    gus_w8
        ; every voice stopped, its volume ramp stopped, silent
        xor     cl, cl
.stop:  mov     al, cl
        call    gus_voice
        mov     ax, 0300h                       ; voice control: stop
        call    gus_w8
        mov     ax, 030Dh                       ; volume ramp control: stop
        call    gus_w8
        mov     al, 09h                         ; current volume 0
        xor     bx, bx
        call    gus_w16
        inc     cl
        cmp     cl, 14
        jb      .stop

        mov     dx, GUS_BASE                    ; mix control: line out on, line in off
        mov     al, 01h
        out     dx, al
        mov     ax, 034Ch                       ; running, DAC on, no IRQ
        call    gus_w8
        mov     al, 0                           ; voice 0: hard left (pan 0)
        mov     ah, 0
        mov     bx, GUS_FC_L
        call    gus_voice_on
        mov     al, 1                           ; voice 1: hard right (pan 15)
        mov     ah, 15
        mov     bx, GUS_FC_R
        call    gus_voice_on

        mov     cx, TONE_TICKS
        call    wait_ticks

        ; voice 0's position (register 8Bh: address bits 6-0 and fraction), for the log
        mov     al, 0
        call    gus_voice
        mov     al, 8Bh
        call    gus_sel
        mov     dx, GUS_DHI
        in      al, dx
        mov     ah, al
        dec     dx
        in      al, dx
        push    ax
        mov     al, 0
        call    gus_voice
        mov     ax, 0300h
        call    gus_w8
        mov     al, 1
        call    gus_voice
        mov     ax, 0300h
        call    gus_w8
        mov     ax, 014Ch                       ; DAC off
        call    gus_w8
        mov     dx, msg_gusok
        call    puts
        pop     ax
        push    ax
        mov     al, ah
        call    puthex
        pop     ax
        call    puthex
        jmp     crlf
.bad:   mov     dx, msg_gusbad
        jmp     puts
.absent:
        mov     dx, msg_gusnone
        jmp     puts

; voice AL: pan AH (0 left .. 15 right), frequency control BX; loops over the sine period from its
; start at GUS_VOL, the volume ramp off
gus_voice_on:
        push    ax
        call    gus_voice
        pop     ax
        mov     al, 0Ch                         ; pan position
        call    gus_w8
        mov     al, 01h                         ; frequency control
        call    gus_w16
        mov     al, 02h                         ; loop start: address bits 19-7, then 6-0 << 9
        mov     bx, GUS_WAVE >> 7
        call    gus_w16
        mov     al, 03h
        mov     bx, (GUS_WAVE & 7Fh) << 9
        call    gus_w16
        mov     al, 04h                         ; loop end
        mov     bx, (GUS_WAVE + GUS_WAVE_LEN) >> 7
        call    gus_w16
        mov     al, 05h
        mov     bx, ((GUS_WAVE + GUS_WAVE_LEN) & 7Fh) << 9
        call    gus_w16
        mov     al, 0Ah                         ; current position: the loop start
        mov     bx, GUS_WAVE >> 7
        call    gus_w16
        mov     al, 0Bh
        mov     bx, (GUS_WAVE & 7Fh) << 9
        call    gus_w16
        mov     al, 09h                         ; current volume
        mov     bx, GUS_VOL
        call    gus_w16
        mov     ax, 030Dh                       ; volume ramp: stopped
        call    gus_w8
        mov     ax, 0800h                       ; voice control: loop, 8-bit, forward, go
        jmp     gus_w8

gus_voice:                                      ; select voice AL
        push    dx
        mov     dx, GUS_VOICE
        out     dx, al
        pop     dx
        ret

gus_sel:                                        ; select register AL
        push    dx
        mov     dx, GUS_SEL
        out     dx, al
        pop     dx
        ret

gus_w8:                                         ; register AL = AH (a byte register: 3x5h)
        push    dx
        call    gus_sel
        mov     dx, GUS_DHI
        mov     al, ah
        out     dx, al
        pop     dx
        ret

gus_w16:                                        ; register AL = BX (low byte 3x4h, high 3x5h)
        push    dx
        call    gus_sel
        mov     dx, GUS_DLO
        mov     al, bl
        out     dx, al
        inc     dx
        mov     al, bh
        out     dx, al
        pop     dx
        ret

gus_addr:                                       ; DRAM address BX (bits 19-16 zero)
        push    ax
        push    dx
        mov     al, 43h
        call    gus_sel
        mov     dx, GUS_DLO
        mov     al, bl
        out     dx, al
        inc     dx
        mov     al, bh
        out     dx, al
        mov     al, 44h
        call    gus_sel
        xor     al, al
        out     dx, al
        pop     dx
        pop     ax
        ret

gus_poke:                                       ; DRAM[BX] = AL
        push    dx
        call    gus_addr
        mov     dx, GUS_DRAM
        out     dx, al
        pop     dx
        ret

gus_peek:                                       ; AL = DRAM[BX]
        push    dx
        call    gus_addr
        mov     dx, GUS_DRAM
        in      al, dx
        pop     dx
        ret

; one period of a sine, 8-bit signed, peak 100, and its first sample again
gus_wave:
        db      0, 16, 31, 45, 59, 71, 81, 89, 95, 99
        db      100, 99, 95, 89, 81, 71, 59, 45, 31, 16
        db      0, -16, -31, -45, -59, -71, -81, -89, -95, -99
        db      -100, -99, -95, -89, -81, -71, -59, -45, -31, -16
        db      0

; ---------------------------------------------------------------------------------------------
; Crystal CS4231A (Windows Sound System codec)

cs_test:
        mov     dx, msg_cs
        call    puts
        ; the index register reads 80h (INIT) while the codec initialises, FFh when nothing is there
        mov     dx, CS_BASE
        mov     cx, 0FFFFh
.init:  in      al, dx
        test    al, 80h
        jz      .ready
        loop    .init
        jmp     .absent
.ready: mov     al, 0Ch                         ; I12: the low nibble is 1010b on the CS4231/AD1848
        call    cs_rd
        mov     [cs_id], al
        and     al, 0Fh
        cmp     al, 0Ah
        jne     .absent
        mov     ax, 400Ch                       ; MODE2 (I16-I31)
        call    cs_wr
        mov     al, 19h                         ; I25: version and chip id
        call    cs_rd
        mov     [cs_id + 1], al
        mov     dx, msg_csid
        call    puts
        mov     al, [cs_id]
        call    puthex
        mov     al, '/'
        call    putc
        mov     al, [cs_id + 1]
        call    puthex
        call    crlf

        call    dma_buffer
        jc      .nomem
        ; 16-bit stereo frames: a square wave of CS_LHALF frames per half period on the left,
        ; CS_RHALF on the right; CS_FRAMES is a multiple of both periods, so the loop is seamless
        push    es
        mov     es, ax
        xor     di, di
        mov     cx, CS_FRAMES
        mov     bx, CS_AMP
        mov     bp, CS_AMP
        mov     dl, CS_LHALF
        mov     dh, CS_RHALF
.fill:  mov     ax, bx
        stosw
        mov     ax, bp
        stosw
        dec     dl
        jnz     .f1
        neg     bx
        mov     dl, CS_LHALF
.f1:    dec     dh
        jnz     .f2
        neg     bp
        mov     dh, CS_RHALF
.f2:    loop    .fill
        pop     es

        mov     ax, 0006h                       ; I6/I7: left and right DAC at 0 dB, unmuted
        call    cs_wr
        mov     ax, 0007h
        call    cs_wr
        mov     ax, 000Ah                       ; I10: interrupt off (IEN 0)
        call    cs_wr
        mov     ax, (((CS_FRAMES - 1) & 0FFh) << 8) | 0Fh   ; I15/I14: playback base count, frames - 1
        call    cs_wr
        mov     ax, (((CS_FRAMES - 1) >> 8) << 8) | 0Eh
        call    cs_wr
        ; mode change: MCE with I8 (format and rate) and I9 (autocalibration, single DMA
        ; channel, playback off), then MCE off and wait for the calibration (I11 bit 5)
        mov     ax, (CS_FORMAT << 8) | 48h
        call    cs_wr
        mov     ax, 0C49h
        call    cs_wr
        mov     dx, CS_BASE
        mov     al, 0Bh
        out     dx, al
        inc     dx
        mov     cx, 0FFFFh
.aci:   in      al, dx
        test    al, 20h
        jz      .cal
        loop    .aci
.cal:
        ; 8237 channel 3: single transfer, auto-init, memory to device
        mov     al, 07h                         ; mask channel 3
        out     0Ah, al
        xor     al, al
        out     0Ch, al
        mov     al, 5Bh                         ; single, auto-init, increment, read, channel 3
        out     0Bh, al
        xor     al, al
        out     06h, al
        out     06h, al
        mov     ax, [buf_seg]
        shr     ax, 12
        out     82h, al                         ; page register of channel 3
        mov     ax, CS_FRAMES * 4 - 1
        out     07h, al
        mov     al, ah
        out     07h, al
        mov     al, 03h                         ; unmask channel 3
        out     0Ah, al

        mov     ax, 0D09h                       ; I9: PEN (ACAL and SDC as before)
        call    cs_wr
        mov     cx, TONE_TICKS
        call    wait_ticks
        mov     ax, 0C09h                       ; PEN off
        call    cs_wr
        mov     al, 07h
        out     0Ah, al
        xor     al, al
        out     0Ch, al
        in      al, 07h
        mov     ah, al
        in      al, 07h
        xchg    al, ah                          ; low byte first
        push    ax
        mov     dx, msg_csok
        call    puts
        pop     ax
        push    ax
        mov     al, ah
        call    puthex
        pop     ax
        call    puthex
        jmp     crlf
.nomem: mov     dx, msg_csnomem
        jmp     puts
.absent:
        mov     dx, msg_csnone
        jmp     puts

cs_wr:                                          ; indirect register AL (with MCE 40h) = AH
        push    dx
        mov     dx, CS_BASE
        out     dx, al
        inc     dx
        mov     al, ah
        out     dx, al
        pop     dx
        ret

cs_rd:                                          ; AL = indirect register AL
        push    dx
        mov     dx, CS_BASE
        out     dx, al
        inc     dx
        in      al, dx
        pop     dx
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
msg_gus         db      'GUS: ', '$'
msg_gusnone     db      'no DRAM at 240h', 13, 10, '$'
msg_gusbad      db      'DRAM read back differs', 13, 10, '$'
msg_gusok       db      'DRAM at 240h, 551 Hz left (voice 0) and 1102 Hz right (voice 1) played, voice 0 at ', '$'
msg_cs          db      'CS4231A: ', '$'
msg_csnone      db      'no codec at 534h', 13, 10, '$'
msg_csid        db      'codec at 534h, I12/I25 ', '$'
msg_csnomem     db      'CS4231A: no DMA buffer below 9000:0', 13, 10, '$'
msg_csok        db      'CS4231A: 800 Hz left and 1600 Hz right played, 16-bit stereo 16000 Hz, DMA 3 count now ', '$'
msg_done        db      'AUDTEST: done', 13, 10, '$'
msg_nooff       db      'AUDTEST: ACPI power off did not happen', 13, 10, '$'
msg_crlf        db      13, 10, '$'

tests           db      0
opl_s1          db      0
opl_s2          db      0
sb_ver          db      0, 0
cs_id           db      0, 0
buf_seg         dw      0
com1            dw      0

prog_end:
