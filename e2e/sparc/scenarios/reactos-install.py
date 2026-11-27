"""ReactOS 0.4.16 from its release CD with the lab's answer file (the medium reactos0416-wshlab.iso, made by
`lab.py media reactos0416 --convert` from ReactOS-0.4.16-i386.iso: answer_media.reactos_unattend).

1. The CD's boot menu (FreeLoader, VGA text, 3 s) starts the Live environment by default: the
   scenario picks "ReactOS Setup (Text Mode)" on the text screen (vgatext.py).
2. The text-mode setup reads i386/unattend.inf (UnattendSetupEnabled = yes): partitions and formats
   the disk (FAT), copies the files, installs FreeLoader to the MBR and reboots, without a question.
   Its screens are recorded from the text buffer.
3. The graphical second stage runs from the disk with the same answers (computer name, Administrator
   password, 1024x768x32, locale), reboots, and the installed system logs on by itself. From here the
   screen is graphical; the scenario follows ReactOS's debug log on COM1 (the setup boots the installed
   system with /DEBUGPORT=COM1 /KDSERIAL) and answers the kernel debugger when an assertion stops in it
   (`_reactos.Debugger`; one in Cc during the second stage, not every run).
4. At the desktop (the third boot's explorer), once the guest is idle (keys typed while it installs
   devices get lost): Esc closes the New Hardware Wizard (QEMU's fw_cfg device), Win+R opens
   cmd.exe, and the scenario types the boot loader fix (default entry "ReactOS" without the debugger,
   TimeOut=3: _reactos.FREELDR_FIX) and `shutdown -r -t 0`. A boot that prints the debugger's command
   line again means a lost key: typed once more (3 tries). Then, at the desktop of the boot without
   the debugger, `shutdown -s -t 0`.

Own QEMU: ISO=reactos0416-wshlab.iso DISK=/work/c.raw (DISK_GB 4); the target: lab.py install reactos0416.
"""
import time

import lab
import _reactos

DEFAULTS = {"TIMEOUT": "3600", "DISK": "/tmp/reactos-c.raw", "DISK_GB": "4", "FB_VIDEO": "2"}


def qemu_args(v, out):
    return _reactos.qemu_args(v, out)


def boot_menu(m, timeout=300):
    """Pick the setup in FreeLoader's menu of the CD (the default, the Live environment, starts after 3 s)."""
    end = time.time() + timeout
    while time.time() < end:
        s = m.vga_screen()
        if s.text_mode and "ReactOS Setup (Text Mode)" in s.text:
            for _ in range(3):
                if any("ReactOS Setup (Text Mode)" in t for _, t in s.highlighted()):
                    break
                m.fb_key("up")
                time.sleep(0.3)
                s = m.vga_screen()
            else:
                raise AssertionError(f"can't select the setup in the boot menu:\n{s.text}")
            m.vga_snap("the CD's boot menu: ReactOS Setup (Text Mode)")
            m.fb_key("ret")
            return
        m._check_alive()
        time.sleep(0.15)
    raise lab.Timeout(f"no boot menu of the ReactOS CD within {timeout}s")


def run(m, v):
    t = int(v["TIMEOUT"])
    t0 = time.time()
    dbg = _reactos.Debugger(m)
    boot_menu(m)
    _reactos.wait_serial(m, _reactos.KD_BOOT, 0, 300, dbg, "the setup's kernel")
    m.vga_expect(r"ReactOS [0-9.]+-x86 Setup", timeout=300)
    m.vga_snap("text-mode setup (unattended)")
    # the text screens of the first stage (partition, format, copy, boot loader), each once
    last = None
    while _reactos.count(m, _reactos.KD_BOOT) < 2:
        dbg.poll()
        s = m.vga_screen()
        if s.text_mode:
            head = "\n".join(s.lines[:12])
            if head != last and s.text.strip():
                last = head
                m.vga_snap("text-mode setup")
        m._check_alive()
        if time.time() - t0 > t:
            raise lab.Timeout("the text-mode setup didn't reboot")
        time.sleep(1)
    m.metrics["text_setup_s"] = round(time.time() - t0)
    m.log(f"second stage (graphical setup) after {m.metrics['text_setup_s']}s")
    t1 = time.time()
    shot = time.time()
    while _reactos.count(m, _reactos.KD_BOOT) < 3:
        dbg.poll()
        if time.time() - shot > 30:
            shot = time.time()
            m.snap("graphical setup", term=False)
        m._check_alive()
        if time.time() - t0 > t:
            raise lab.Timeout("the graphical setup didn't reboot")
        time.sleep(2)
    m.metrics["gui_setup_s"] = round(time.time() - t1)
    m.log(f"installed system booting after {m.metrics['gui_setup_s']}s of the second stage")
    third = m.text.rfind("Command Line: ")
    # explorer's desktop window (its property bag is looked up when the desktop is drawn)
    _reactos.wait_serial(m, r"AllFolders\\+Desktop", third, max(60, t - (time.time() - t0)), dbg, "the desktop")
    m.fb_stable(8, timeout=300)
    m.metrics["desktop_s"] = round(time.time() - t0)
    m.snap("the installed system's desktop (logged on as Administrator)", term=False)
    # The boot loader's default: typed at cmd.exe, then a reboot shows whether it took (a boot with the
    # kernel debugger prints its command line on COM1, one without prints nothing)
    for attempt in range(1, 4):
        m.metrics["settle_s"] = _reactos.settle(m, poll=dbg.poll)
        _reactos.dismiss_dialogs(m)
        _reactos.open_cmd(m)
        for line in _reactos.FREELDR_FIX:
            _reactos.type_line(m, line)
        m.snap(f"boot loader default typed (attempt {attempt})", term=False)
        cursor = m.serial_cursor()
        _reactos.type_line(m, "shutdown -r -t 0")
        _reactos.wait_serial(m, r"Shutting down NT", cursor, 120, dbg, "the reboot")
        r = m.serial_wait(_reactos.KD_BOOT, cursor, timeout=150)
        if not r["matched"]:
            break
        m.log(f"the kernel debugger is still on after the reboot (attempt {attempt}): typing the default again")
        _reactos.wait_serial(m, r"AllFolders\\+Desktop", r["cursor"], 600, dbg, "the desktop")
        m.fb_stable(8, timeout=300)
    else:
        raise AssertionError("the boot loader's default didn't change in 3 tries")
    m.metrics["freeldr_attempts"] = attempt
    time.sleep(30)
    _reactos.settle(m, need=3)
    m.fb_stable(8, timeout=300)
    m.snap("desktop of a boot without the kernel debugger", term=False)
    _reactos.dismiss_dialogs(m)
    _reactos.shutdown(m)
    m.metrics["install_s"] = round(time.time() - t0)
