"""FreeDOS 1.4 from the Floppy Edition's 1.44 MB disks, answered on the VGA text screen: the same
machinery as the MS-DOS 6.22 install (floppy boot, partitioning with a reboot, formatting, disk swaps,
the screen read from the text buffer), with freely redistributable media, so it runs in CI.

The installer (FDI) asks its questions one at a time at the cursor: proceed, partition C: and reboot,
proceed again after the reboot, format, install; then it asks for each disk ("Insert diskette #2 ...",
then "Insert diskette containing file A:\\FREEDOS.024 ..." which doesn't say which disk), and at the end
whether to reboot. The disks go in in order: SWAPS (see _dos.swaps) when the scenario swaps them
itself, else an external swapper (install.MediaSwapper with "at" regexes). Ends at the C:\\> prompt of
the first boot from the hard disk.

Own QEMU: FLOPPY=x86BOOT.img DISK=/work/fd.raw SWAPS="floppy0=x86DSK01.img floppy0=x86DSK02.img ..."
STOP_AFTER=format|disk1 stops early (CI: partition, reboot, format and one disk swap).
"""
import re
import time

import lab
import _dos

DEFAULTS = {"DRIVE": "floppy0", "TIMEOUT": "600", "DISK_MB": "512", "STOP_AFTER": ""}

QUESTIONS = [
    (r"Do you want to proceed \[Y,N\]\?$", "y"),
    (r"Do you want to reboot now \[Y,N\]\?$", "y"),
    (r"Do you want to format your drive \[Y,N\]\?$", "y"),
    # "Insert diskette ... in A:" comes a moment before "Press a key to continue.": wait for the latter
    (r"Press (a|any) key to continue\.?$", None),
    (r"^[A-Z]:\\[^>]*>$", "done"),
]


def qemu_args(v, out):
    return _dos.qemu_args(v, out)


def answer(m, text):
    _dos.type_text(m, text)
    time.sleep(0.3)
    _dos.key(m, "ret")


def run(m, v):
    t = int(v["TIMEOUT"])
    drive = v["DRIVE"]
    own = _dos.swaps(v)
    medium = m.medium(drive)
    disks, steps, last, asked = 0, 0, None, None
    end = time.time() + 4 * t
    while time.time() < end:
        s = m.vga_expect("|".join(f"(?:{q})" for q, _ in QUESTIONS), timeout=t, tail=2)
        tail = s.tail(2)
        here = (tail, s.cursor)
        if here == last:  # the same prompt still waiting: our answer hasn't been taken yet
            time.sleep(1)
            continue
        last = here
        steps += 1
        if re.search(r"^[A-Z]:\\[^>]*>$", s.cursor_line()):
            if disks == 0:
                raise AssertionError(f"a DOS prompt before the install:\n{s.text}")
            break
        if re.search(r"Press (a|any) key to continue", tail):
            if re.search(r"Insert diskette", tail):
                want = re.search(r"Insert diskette (#\d+[^\n]*|containing file \S+)", tail).group(1)
                if want == asked:
                    # The same file again: the disk change wasn't seen yet when the key came. The disk in
                    # the drive is right (the files on a disk are read in order); press the key again.
                    m.log(f"FDI asks again for {want}: pressing a key again")
                    time.sleep(2)
                    _dos.key(m, "spc")
                    continue
                asked = want
                m.vga_snap(f"FDI asks for the next disk ({want})")
                disks += 1
                if own:
                    if disks > len(own):
                        raise AssertionError(f"FDI asks for disk {disks + 1}, SWAPS has {len(own)}")
                    m.change_medium(*own[disks - 1])
                medium = _dos.wait_medium_change(m, drive, medium)
                time.sleep(2)
                if v["STOP_AFTER"] == "disk1":
                    _dos.key(m, "spc")
                    m.vga_expect(r"Insert diskette containing file|Installing|\.\.\.", timeout=t)
                    m.vga_snap("reads disk 1: stopping here (STOP_AFTER=disk1)")
                    return
                _dos.key(m, "spc")
            else:
                _dos.key(m, "spc")
            continue
        for q, reply in QUESTIONS[:3]:
            if re.search(q, s.cursor_line()):
                m.vga_snap(f"FDI: {s.cursor_line().strip()}")
                if v["STOP_AFTER"] == "format" and "proceed" in q and "Success" in s.text and "QuickFormat" in s.text:
                    return
                if "reboot" in q and disks:
                    # the last package disk isn't bootable ("press any key to try again"): empty A:
                    m.change_medium(drive, "none")
                answer(m, reply)
                break
        else:
            raise AssertionError(f"unexpected screen:\n{s.text}")
    else:
        raise lab.Timeout("the install didn't finish")
    m.vga_snap("first boot from the hard disk")
    m.metrics["disks"] = disks
    if not own and disks < 6:
        raise AssertionError(f"FDI asked for {disks} disks, expected 6")
