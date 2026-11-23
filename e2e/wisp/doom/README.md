# fbDOOM build inputs

Run `python3 e2e/wisp/doom/fetch.py DIRECTORY` with Python 3.11 or newer. It verifies new
and cached archives before extracting only `freedoom1.wad`. The source, archives, executable
and WAD are build products.

| Input | Pin | SHA-256 of the archive |
| --- | --- | --- |
| [fbDOOM](https://github.com/maximevince/fbDOOM/commit/e52885ff8a4cba99586c33b09339a9a56a69c041), GPL-2.0 | `e52885ff8a4cba99586c33b09339a9a56a69c041` | `216901bd4afeb0d37fd0100e986c909d8b4300d9c4eb9feeabe569b1e8b0551e` (computed here for the codeload tar.gz) |
| Freedoom, BSD-3-Clause | `v0.13.0`, `freedoom-0.13.0.zip` | `3f9b264f3e3ce503b4fb7f6bdcb1f419d93c7b546f4df3e874dd878db9688f59` from the [official signed CHECKSUM](https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0-CHECKSUM) |

`sh doom/build.sh ARCH VERIFIED_TARBALL OUTPUT` needs make, patch, and the architecture's
compiler. It applies the following diffs in order and links a stripped static binary without SDL.

| Patch | Purpose |
| --- | --- |
| 01-byte-order | Swap signed 16- and 32-bit WAD fields on big-endian targets. |
| 02-exit | Print the timed line and exit successfully on completion. Propagate engine errors to PID 1. |
| 03-framebuffer | Mount devtmpfs when needed, install the indexed palette or convert to native bitfields, and center the integer-scaled frame (the largest factor that fits, or fbDOOM's `-scaling N`; `doom.py --scale` passes it) using the device stride. Copy each expanded row vertically. Mark frame 70 for QMP. |
| 04-keyboard | Read the VT keyboard type as one byte, probe the correct descriptor and skip polling an unavailable keyboard. |
| 05-response-file | Enable and bound the upstream response-file parser so the OpenBIOS boot arguments stay short. |
| 06-oss-sound | Mix eight DMX effect channels with integer resampling, volume and stereo separation. Stream 44.1 kHz signed little-endian stereo to OSS from the game loop. |

The [wisp timedemo instructions](../README.md#freedoom-framebuffer-timedemo) cover building
the XZ squashfs data disk, booting and interpreting the measurements.
