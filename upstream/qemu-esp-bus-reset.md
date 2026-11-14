# QEMU: ESP rejects Select with ATN after a SCSI bus reset

Material for a bug report or patch to upstream QEMU. We carry the fix in pve-qemu as
`debian/patches/wsh/0001-esp.c-return-to-disconnected-mode-on-SCSI-bus-reset.patch`, with a
qtest in `0007-tests-qtest-am53c974-check-that-Select-with-ATN-work.patch` (both in
`submodules/pve-qemu.patch`).

## Summary

After a SCSI Bus Reset command (0x03), the ESP (`hw/scsi/esp.c`) stays in initiator mode. The
next Select with ATN (0x42, or 0xc2 with DMA) is then rejected as an illegal command: the chip
sets the illegal command bit, which is STAT_GE ("gross error") in the status register. Guests
that reset the bus to recover from an error can never select a target again.

- **Affected:** QEMU 10.1.0 and later. Still in upstream master as of 2026-11-14.
- **Introduced by:** `6f8ce26bb00db66e6cec632f16df3cd13e4df934` "esp.c: only allow ESP commands
  permitted in the current asc_mode" (Mark Cave-Ayland, July 2025; first in v10.1.0-rc0). It
  fixed WinNT MIPS ([#2464](https://gitlab.com/qemu-project/qemu/-/issues/2464)).
- **Who to tell:** Mark Cave-Ayland wrote the asc_mode change and most recent ESP work.
  `MAINTAINERS` lists `hw/scsi/*` and `am53c974-test.c` under SCSI: Paolo Bonzini (M),
  Fam Zheng (R).

## How it shows up

Solaris 2.5.1 (sparc32, `-M SS-5`, OpenBIOS or `ss5.bin`) can't boot from its install CD. Its
`esp` driver loops on:

```
esp0: gross error in esp status (c1)
esp0: undetermined selection failure
```

`0xc1` is STAT_INT | STAT_GE | STAT_DI. With `-trace esp_invalid_cmd`:

```
esp_invalid_cmd command 0xc2 asc_mode 0x1
```

On QEMU 7.2.0 the same boot reads the CD and installs. Solaris 2.6 reaches its installer and
installs on the affected versions too.

## Root cause

`esp_cmd_is_valid()` allows the disconnected-mode commands (Select, Select with ATN, ...) only
when `s->asc_mode == ESP_ASC_MODE_DIS`. `asc_mode` becomes `ESP_ASC_MODE_INI` when a target is
selected and goes back to `ESP_ASC_MODE_DIS` on Message Accepted, on a selection timeout and on
a chip reset (`esp_hard_reset()`), but not on a SCSI bus reset:

```c
static void esp_bus_reset(ESPState *s)
{
    bus_cold_reset(BUS(&s->bus));
}
```

A bus reset disconnects every device, so on real hardware the chip is back in disconnected
mode. The Solaris driver issues a bus reset to recover from a stuck command, then selects
again, and gets the illegal command interrupt every time.

## Fix

```diff
 static void esp_bus_reset(ESPState *s)
 {
     bus_cold_reset(BUS(&s->bus));
+    /* A SCSI bus reset disconnects every device: the chip is back in disconnected mode */
+    s->asc_mode = ESP_ASC_MODE_DIS;
 }
```

It doesn't change the chip reset path that #2464 is about (ICCS after a chip reset is still
illegal).

## Reproducer (qtest)

A new case in `tests/qtest/am53c974-test.c` (am53c974 is the PCI ESP, same `esp.c`; the test
runs for i386): select target 0 with ATN without DMA, issue a bus reset, select again, and
check that the status register has no STAT_GE.

```
QTEST_QEMU_BINARY=./qemu-system-i386 ./tests/qtest/am53c974-test
```

Run on 2026-11-14, `qemu-system-i386` built from each tree with the test added:

| Tree | `test_select_after_bus_reset_ok` | Other 11 am53c974 tests |
| --- | --- | --- |
| `ab1207401e` (parent of the culprit) | ok | ok |
| `6f8ce26bb0` (culprit) | **fails**: `stat & STAT_GE`: `0x40`, expected `0x00` | ok |
| v11.1.3 | **fails**: same assertion | ok |
| v11.1.3 + fix | ok | ok |

## How it was found

- A sparc32 install lab (`e2e/sparc` in this repository) runs Solaris installs unattended on a
  given QEMU and records the console.
- `git bisect run` over v7.2.0..v11.1.1 (sparc-softmmu only) booted the Solaris 2.5.1 CD at
  each step and classified the console output: 14 steps, first bad commit `6f8ce26bb0`.
- With the fix on 11.1.3, a full Solaris 2.5.1 install (End User, about an hour) and the boot
  of the installed disk pass. Solaris 2.6 installs and boots as before.

## Sending it upstream

QEMU declines contributions that include or are derived from AI-generated content
(`docs/devel/code-provenance.rst`). The fix and the qtest here were written with an AI agent,
so the safe route is a bug report, which can point at the one-line fix in prose and leave
the patch to the maintainer, or a patch written from scratch by a person.

- Bug report: open a GitLab issue at <https://gitlab.com/qemu-project/qemu/-/issues> with the
  summary, the console output, the trace line, the root cause and the first bad commit.
- Patch: `git format-patch` of the fix and the qtest, with
  `Fixes: 6f8ce26bb0 ("esp.c: only allow ESP commands permitted in the current asc_mode")`
  and a `Signed-off-by`.
- Send to qemu-devel@nongnu.org, Cc Mark Cave-Ayland, Paolo Bonzini and Fam Zheng
  (`scripts/get_maintainer.pl -f hw/scsi/esp.c`). QEMU doesn't take GitHub/GitLab merge
  requests.
- Drop our patch once a fixed QEMU reaches pve-qemu.
