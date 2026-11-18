# QEMU: ESP dispatches a byte-by-byte CDB too early after a message out phase

Material for a bug report to QEMU. The patch is pve-qemu's
`debian/patches/wsh/0038-esp-don-t-count-the-message-out-bytes-as-part-of-the.patch`, with the
qtest `sun4m-esp-test` in `wsh/0039` (both in `submodules/pve-qemu.patch`). QEMU doesn't take
AI-generated code, so this note describes the change for a patch written by hand.

## Summary

`esp_cdb_ready()` (`hw/scsi/esp.c`) decides whether the whole CDB is in the command FIFO by
comparing the number of bytes in `cmdfifo` with the CDB length that `scsi_cdb_length()` reads
from the first CDB byte. But `cmdfifo` starts with the message out bytes, `cmdfifo_cdb_offset`
of them (the IDENTIFY byte, and any further messages such as SDTR), so they are counted as CDB
bytes. A guest that sends the CDB in several Transfer Information commands gets its command
dispatched up to `cmdfifo_cdb_offset` bytes early.

- **Affected:** QEMU 11.1.3 (where it was found), and upstream master as of 2026-11-18 (the same
  `return cdblen < 0 ? false : (len >= cdblen);`). The comparison came with `5aa0df4067`
  ("esp.c: rework esp_cdb_length() into esp_cdb_ready()", Mark Cave-Ayland, March 2024); not
  bisected.
- **Existing reports:** none found in the QEMU GitLab issues (searched "esp cdb", "esp message
  out", "esp scsi sparc", "sun4m scsi", "esp.c" on 2026-11-18).
- **Who to tell:** Mark Cave-Ayland (most of the ESP work, and the sparc32 machines); `MAINTAINERS`
  lists `hw/scsi/*` under SCSI: Paolo Bonzini (M), Fam Zheng (R). qemu-devel@nongnu.org.

## How it shows up

The Debian 4.0 (etch) sparc installer's Linux 2.6.18 on `-M SS-5`. Its old `esp` driver
negotiates synchronous transfers with each target: Select with ATN and Stop (IDENTIFY only), a
5-byte extended SDTR message in the message out phase, then the CDB one byte per Transfer
Information command, without DMA. After IDENTIFY and the 5 message bytes, `cmdfifo` holds 6
bytes, so the first CDB byte makes 7 and passes `len >= 6`: the target gets a one-byte command,
answers CHECK CONDITION with ILLEGAL REQUEST, and Linux resets the bus and takes `sda` and `sr0`
offline; `cdrom-detect` finds no CD. With the fix the installer finds the CD (tested with a
`qemu-system-sparc` build by the agent working on the Debian 4.0 target).

## Fix

Count only the bytes after the message bytes:

```c
    return cdblen < 0 ? false : (len - s->cmdfifo_cdb_offset >= cdblen);
```

`len` is at least `cmdfifo_cdb_offset + 1` there (the function returns earlier otherwise), so
the subtraction can't go negative. `do_message_phase()` already takes `cmdfifo_cdb_offset` bytes
off the front before the command phase, so the CDB that reaches `scsi_req_new()` is the same.
The other callers are the paths where the CDB came with Select (`cmdfifo_cdb_offset` 1, or 0
for Select without ATN): there the old comparison was early by one byte when a DMA select was
ended by a non-DMA FIFO write, which this fixes too.

## Test

`tests/qtest/sun4m-esp-test.c` drives the SPARCstation 5's ESP registers (0x78800000, 4 bytes
apart) without DMA as Linux 2.6 does: Select with ATN and Stop with IDENTIFY, the SDTR message
with Transfer Information, then TEST UNIT READY one byte per Transfer Information, against a
`null-co` disk. The target must stay in the command phase until the sixth byte, and the command
must arrive whole: twice, the first answered with the reset's unit attention (CHECK CONDITION),
the second with GOOD. Without the fix the first CDB byte already moves the target to the status
phase.

## Regression check

`make check-qtest-sparc` and `check-qtest-sparc64` (with `am53c974-test`'s Select with ATN case
from our `wsh/0007` in the i386 build), and Solaris 2.6 and SunOS 4.1.4 disk boots on SS-5 in the
sparc lab; results in `submodules/SPARC.md`.
