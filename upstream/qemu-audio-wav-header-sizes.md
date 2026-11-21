# QEMU: the `wav` audiodev never writes its header's sizes (the backend is never finalized)

Material for a bug report to upstream QEMU, for the owner to write and send by hand (QEMU doesn't
take AI-written code or text). Nothing is carried for it: the audio matrix and the docs read the
file anyway (`e2e/audio/wavcheck.py`, [audio reference](../docs/src/content/docs/reference/audiodev.md)).
Our own finding in QEMU's code, independent of LEMU (column "may send" in [README.md](README.md));
it replaces the "Hold" row about the wav header, which was first seen with LEMU's CS4231.

**Reproduced on plain QEMU** (2026-11-21): `qemu-system-x86_64` built from the v11.1.3 tag (the
tree had an uncommitted VGA change of ours in `hw/display/`, nothing in `audio/` or `hw/audio/`),
`-M pc -audiodev wav,id=a,path=o.wav -device sb16,audiodev=a`, a DOS guest that plays a tone and
powers off through ACPI: QEMU exits with 0, and the file's RIFF size (offset 4) and data size
(offset 40) are both 0. The same with the packaged pve-qemu-kvm 11.1.3-3+wsh6.

## Summary

`wav_fini_out()` (`audio/wavaudio.c`) is what seeks back and writes the two sizes. Since QEMU 11.0
it runs only from `audio_mixeng_backend_finalize()` (or when a HW voice is garbage-collected after
its last SW voice closed). At exit nothing finalizes the backend:

- `qemu_cleanup()` calls `audio_cleanup()`, which unparents the `/audiodevs` container. The
  container is finalized and drops its child reference on the backend.
- But every voice holds a reference of its own on the backend, since commit `1002fe3710` ("audio:
  keep a strong reference on the backend", 2026-02-23, in v11.0.0, not in v10.2.0):
  `audio_pcm_hw_add_new_*()` takes `object_ref(s)` for each HW voice, and `audio_pcm_create_voice_pair_*()`
  takes one for each SW voice (`audio/audio_template.h`). They are dropped when the device closes its
  voice (`audio_be_close_out()` and the HW voice's GC).
- Devices are not unrealized at exit, so their voices stay open, the backend's reference count never
  reaches 0 and `audio_mixeng_backend_finalize()` (which would call `fini_out` for every HW voice)
  never runs. Also a cycle: the backend's `hw_head_out` list owns the HW voices that hold it.

The file isn't closed either: its last samples reach it only because `exit()` flushes stdio.

Current master (`225d5bd469`, 2026-11-20) has the same code.

## Evidence

All with `-device sb16`, `adlib`, the PC speaker (`-machine pcspk-audiodev=`) or AC97/HDA; every
device behaves the same, so it is the backend, not a device:

| How QEMU ends | exit | RIFF / data size |
| --- | --- | --- |
| guest powers off (ACPI) | 0 | 0 / 0 |
| QMP `system_powerdown` (the DOS guest ignores it and powers off when done) | 0 | 0 / 0 |
| QMP `quit` | 0 | 0 / 0 |
| SIGTERM, SIGINT | 0 | 0 / 0 |
| SIGKILL | -9 | 0 / 0 (expected) |
| through Proxmox VE: guest power off, `qm stop` (QMP `quit`) | | 0 / 0 |

The fmt chunk is right (PCM, 2 channels, 44100 Hz, 176400 bytes/s, block align 4, 16 bit), the data
is whole frames, and the samples are good: only the two sizes are missing.

`strace -f -y -e trace=openat,lseek,write,close` of a run to the guest's power off: the wav file is
opened `O_WRONLY|O_CREAT|O_TRUNC`, gets the 44-byte header and 4096-byte writes, and at the end one
short write (the stdio flush in `exit()`). There is no `lseek` and no `close` on it. The block
device and the `-serial file:` chardev are closed in the same run, so `qemu_cleanup()` did run.

`-trace object_finalize -trace 'object_property_del*'` of the same run:

```
object_property_del obj=... type=container name=audiodevs value=0x...4480
object_finalize obj=0x...4480 type=container
object_property_del obj=0x...4480 type=container name=a value=0x...6cb0
object_property_del obj=0x...4480 type=container name=type value=...
object_property_del_child obj=... type=container child=... child-type=container   (chardevs)
...
object_finalize obj=... type=chardev-file
```

The container `audiodevs` is finalized and its child `a` (the `audio-wav` object) is deleted, but
there is no `object_finalize ... type=audio-wav`, while the chardev in the next container is
finalized.

## Reproducer

Any guest that plays something and powers off; without a guest, a frozen machine opens no voice and
the file isn't even created. The audio matrix's DOS guest does it in a few seconds
(`e2e/audio/`, `audio_matrix.py qemu --only dos-sb16`), and the check is two fields:

```
python3 -c "import struct,sys; d=open(sys.argv[1],'rb').read(); \
  print(len(d), struct.unpack('<I',d[4:8])[0], struct.unpack('<I',d[40:44])[0])" o.wav
```

A file whose sizes are right prints `<n> <n-8> <n-44>`.

## Where a fix could go (for the owner to judge)

Not tried here. In v10.2.0 `audio_cleanup()` was already the same `object_unparent()`, but the
container held the only reference, so the backend's finalize (then `audio_be_finalize()`, with the
same `fini_out` loop) ran at exit; from the code, 10.2 wrote the sizes (not run here). So either
shut the HW voices down from `audio_cleanup()` whatever the reference count (call `fini_out` for
each before unparenting), or don't count the voices' references as ownership at exit; or let
`wav_write_out()` keep the header current (rewrite the sizes every so many writes, or when the VM
stops), which would also help after SIGKILL.

## Impact on us

- `audio0: driver=wav` (qemu-server) and the audio matrix: the recordings are fine but tools that
  trust the header see an empty file. The docs say how to read it (all after byte 44, or
  `sox --ignore-length`); `wavcheck.py` does that and the matrix accepts sizes that are right or 0,
  so a fixed QEMU shows as "header sizes set" in the matrix summary.
- Every mixeng backend misses its `fini_out` at exit, not only `wav` (for the others it would close
  the host's audio connection, which the process exit does anyway); for `wav` it is the only place
  the header is completed. Not checked for the other backends.
