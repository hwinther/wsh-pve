# OpenBIOS: empty SCSI targets probed as present, no `disk` alias on sparc32

Material for a bug report to OpenBIOS. We carry the fix as
`openbios/patches/0001-esp-treat-a-selection-timeout-as-no-device.patch`; `openbios/Dockerfile`
builds `openbios-sparc32` with it, and pve-qemu installs that over QEMU's image.

## Summary

On sparc32 (`qemu-system-sparc -M SS-5`), OpenBIOS treats every empty SCSI target as a
device of unknown type. The disk on target 3 then gets only the aliases `disk3`/`hd3`, there
is no `disk` alias, and the default `boot-device` (`disk:a disk`) fails:

```
Trying disk:a...
Trying disk...
No valid state has been set by load or init-program
```

- **Affected:** OpenBIOS since the ESP series of 2024-09-13 by Mark Cave-Ayland, up to the
  current master `e5ac46dd24`. QEMU ships it from 9.2 (`roms/openbios` updated 2024-09-24);
  QEMU 11.1.3 has `e5ac46dd24`. Per commit, built and run on QEMU 11.1.3 with a disk on target 3:

  | OpenBIOS commit | aliases |
  | --- | --- |
  | `70b61cd8a1` (before the series) | `disk`, `disk0` → `sd@3,0` |
  | `71bb3bf131` esp: clear FIFO before issuing ESP command | `disk`, `disk0` → `sd@3,0` |
  | `56fa1b2a72` esp: use ESP rather than DMA interrupt to detect end of transfer | none: no SCSI device found |
  | `c3a19c1e54` esp: correctly terminate successful SCSI commands | `UNKNOWN0`-`UNKNOWN7` for the empty targets, `disk3` → `sd@3,0`, no `disk` |

- **Not affected:** the OpenBIOS in QEMU 7.2.0 (v1.1, built 2022-03-07).
- **Who to tell:** Mark Cave-Ayland maintains OpenBIOS and wrote the change. OpenBIOS takes
  patches at openbios@openbios.org; the code is at <https://github.com/openbios/openbios>.

## Evidence

`" /aliases" find-device .properties` with one disk on target 3:

| | aliases |
| --- | --- |
| OpenBIOS 2022 (QEMU 7.2.0) | `disk`, `hd`, `disk0`, `hd0` → `sd@3,0` |
| OpenBIOS `e5ac46dd24` (QEMU 11.1.3) | `UNKNOWN`, `UNKNOWN0` → `sd@0,0`; `UNKNOWN1`, `UNKNOWN2` → `sd@1,0`, `sd@2,0`; `disk3`, `hd3` → `sd@3,0`; `UNKNOWN4`-`UNKNOWN7` → `sd@4,0`-`sd@7,0` |

The result follows the OpenBIOS image, not the QEMU version: the 2022 image gives `disk` on
both QEMU 7.2.0 and 11.1.3, and `e5ac46dd24` gives `UNKNOWN*` on both.

## Root cause

`do_command()` in `drivers/esp.c` issues Select with ATN and waits for BSERV, FDONE or DC. A
selection timeout on an empty target ends with ESP_INTR_DC and a status register of 0. The
function returns non-zero only when the status lacks ESP_STAT_TCNT, and returns that status,
so it returns 0, which callers read as success.

`inquiry()` then marks the target present with `media = buffer[0]`. The buffer still holds
the IDENTIFY byte 0x80 that the command started with, so the media type is "UNKNOWN".
`ob_esp_init()` counts UNKNOWN devices with the disks, so the empty targets 0-2 take
`disk0`-`disk2` numbering (as `UNKNOWN0`-`UNKNOWN2`) and the plain alias goes to target 0 as
`UNKNOWN`.

## Fix

```diff
 do_command(esp_private_t *esp, sd_private_t *sd, int cmdlen, int replylen)
 {
-    int status;
+    int status, intr;
 ...
-    while (!(esp->ll->regs[ESP_INTRPT] & (ESP_INTR_BSERV | ESP_INTR_FDONE | ESP_INTR_DC)));
+    while (!((intr = esp->ll->regs[ESP_INTRPT]) & (ESP_INTR_BSERV | ESP_INTR_FDONE | ESP_INTR_DC)));
     // Check status
     status = esp->ll->regs[ESP_STATUS];
 
+    /* Selection timed out: there is no device at this target */
+    if (intr & ESP_INTR_DC) {
+        DPRINTF("do_command: id %d, selection timeout\n", sd->id);
+        return -1;
+    }
```

The interrupt register is read once and kept, because reading it clears it.

## Tested

With `e5ac46dd24` + the fix, built with Debian 13's `gcc-sparc64-linux-gnu`, on QEMU 11.1.3:

- Aliases with a disk on target 3 and a CD-ROM on target 6: `disk`/`hd`/`disk0`/`hd0` →
  `sd@3,0` and `cdrom`/`cd`/`cdrom0`/`cd0` → `sd@6,0`, no `UNKNOWN*`.
- `-boot c` boots an installed Solaris 2.6 disk by itself ("Trying disk:a..." → SunOS).
- `-boot d` boots the Solaris 2.6 CD by itself ("Trying cdrom:d..." → SunOS).
- The sparc lab (`e2e/sparc`) on pve-qemu-kvm 11.1.3+wsh3 with this image: the installed Solaris
  2.6 disk boots to login and powers off (155 s), and a full Solaris 2.6 End User install from
  CD passes (516 s; the stock image: 523 s). With a `disk` alias the installer now marks
  c0t3d0 as "boot disk" and selects it by itself.

## Sending it upstream

The fix was written with an AI agent (Claude Code). OpenBIOS has no written policy on that as
far as we know, unlike QEMU (`docs/devel/code-provenance.rst` declines AI-generated content);
say so in the report, or describe the bug and the fix in prose and let the maintainer write
the patch.
