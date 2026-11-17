"""MS-DOS 6.22 SETUP from the three Setup floppies, answered on the VGA text screen.

Disk 1 boots into SETUP. On an empty disk it offers to configure the unallocated space (FDISK: one
primary partition over the whole disk), restarts the machine with Disk 1 still in A:, formats C:,
confirms the date/time/country/keyboard settings, takes C:\\DOS, copies and asks for Setup Disk #2 and
#3, then for the floppy to be removed, and restarts into the installed system. This scenario follows
every screen by its text, presses ENTER, waits for the disk swaps (done by install.MediaSwapper, or by
the scenario itself when SWAPS lists the disks: a QEMU of the lab's own), empties the drive when asked,
and ends at the C:\\> prompt of the first boot from the hard disk.

Variables: SWAPS (see _dos.swaps), DRIVE (floppy0), TIMEOUT (per screen, seconds; 300).
Own QEMU: FLOPPY=Disk1.img DISK=/work/dos.raw SWAPS="floppy0=Disk2.img floppy0=Disk3.img".
"""
import _dos

DEFAULTS = {"DRIVE": "floppy0", "TIMEOUT": "300", "DISK_MB": "1024"}


def qemu_args(v, out):
    return _dos.qemu_args(v, out)


def run(m, v):
    t = int(v["TIMEOUT"])
    drive = v["DRIVE"]
    own = _dos.swaps(v)
    m.vga_expect(r"Welcome to Setup", timeout=t)
    m.vga_snap("SETUP: welcome")
    _dos.key(m, "ret")
    i, s = m.vga_expect_any([r"Configure unallocated disk space", r"Setup will use the following system settings"],
                            timeout=t)
    if i == 0:
        m.vga_snap("SETUP: configure the unallocated space (FDISK)")
        _dos.key(m, "ret")
        m.vga_expect(r"Setup will restart your computer now", timeout=t)
        m.vga_snap("SETUP: restart after partitioning")
        _dos.key(m, "ret")
        # the restart boots Disk 1 again; SETUP formats C: and goes on by itself
        m.vga_expect(r"Setup will use the following system settings", timeout=t * 2)
    m.vga_snap("SETUP: system settings")
    _dos.key(m, "ret")
    m.vga_expect(r"Setup will place your MS-DOS files", timeout=t)
    m.vga_snap("SETUP: C:\\DOS")
    _dos.key(m, "ret")
    medium = m.medium(drive)
    n = 0
    while True:
        i, s = m.vga_expect_any([r"Setup Disk #(\d)", r"Remove disks from all floppy disk drives",
                                 r"MS-DOS Setup Complete"], timeout=t * 2)
        if i == 0:
            n += 1
            m.vga_snap(f"SETUP: asks for disk {n + 1}")
            if own:
                m.change_medium(*own[n - 1])
            medium = _dos.wait_medium_change(m, drive, medium)
            m.log(f"{drive} now holds {medium}")
            _dos.key(m, "ret")
            # don't see the same prompt again before SETUP has read the disk
            _dos.wait_gone(m, r"Setup Disk #%d" % (n + 1), timeout=t)
        elif i == 1:
            m.vga_snap("SETUP: remove the floppy")
            m.change_medium(drive, "none")
            _dos.key(m, "ret")
            _dos.wait_gone(m, r"Remove disks from all floppy disk drives", timeout=t)
        else:
            m.vga_snap("SETUP: complete")
            _dos.key(m, "ret")
            break
    if n != 2:
        raise AssertionError(f"SETUP asked for {n} more disks, expected 2")
    _dos.boot_to_prompt(m, t)
    m.vga_snap("first boot from the hard disk: C:\\>")
