"""Helpers for ReactOS guests on x86 (targets_dos.py "reactos0416"): the machine for the lab's own QEMU,
the kernel debugger on COM1 during the install, the report the installed system writes to COM1 at each
logon, and typing into the Run dialog and cmd.exe through QMP send-key (US layout).

The screen is graphical from the second setup stage on, so the scenarios read the serial console
instead of the screen: during the install ReactOS's own debug log (the unattended setup makes the
installed system boot "ReactOS (RosDbg)", /DEBUG /DEBUGPORT=COM1 /KDSERIAL), afterwards the lines
C:\\wshlab.cmd writes to COM1 (the install puts it into the Run key). Screenshots are evidence only.
"""
import os
import re
import subprocess
import time

import lab

# The kernel debugger's prompts on COM1: an assertion asks "Break repeatedly, break Once, Ignore,
# terminate Process or terminate Thread (boipt)?" and then reads its answer at "kdb:>"; a break-in
# without that question waits at "kdb:>" alone.
KDB = r"\(boipt\)\?\s*kdb:>|kdb:>"
KD_BOOT = r"kdinit\.c:\d+\) Command Line: "  # each boot with the kernel debugger on prints its options
REPORT = r"WSHLAB-LOGON\r?\n(?P<body>[\s\S]*?)WSHLAB-END"
REPORT_SCRIPT = "C:\\wshlab.cmd"
RUN_KEY = "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"

# What C:\wshlab.cmd runs at each logon (the Run key) and when the first boot calls it: the version,
# the host name, the boot loader's default entry, the marker and the network, between two marker lines,
# all to COM1 (free once the boot loader's default is the entry without the kernel debugger)
REPORT_LINES = [
    "@echo off",
    "echo WSHLAB-LOGON>COM1",
    "ver>COM1",
    "hostname>COM1",
    'type C:\\freeldr.ini | find "DefaultOS=">COM1',
    "if exist C:\\WSHLAB.TXT type C:\\WSHLAB.TXT>COM1",
    "ipconfig>COM1",
    "echo WSHLAB-END>COM1",
]

# The installed system's boot loader: the unattended setup leaves DefaultOS=ReactOS_KdSerial and
# TimeOut=0 (bootsup.c, for ReactOS's test bot). These commands make "ReactOS" (no debugger) the
# default with the 3 s menu an interactive install gets, keeping every other line of the file.
FREELDR_FIX = [
    "attrib -r -s -h C:\\freeldr.ini",
    "copy /y C:\\freeldr.ini C:\\freeldr.wsh",
    ">C:\\freeldr.ini echo [FREELOADER]",
    ">>C:\\freeldr.ini echo DefaultOS=ReactOS",
    ">>C:\\freeldr.ini echo TimeOut=3",
    'type C:\\freeldr.wsh | find /v "[FREELOADER]" | find /v "DefaultOS=" | find /v "TimeOut=" >>C:\\freeldr.ini',
    'type C:\\freeldr.ini | find "="',
]


def qemu_args(v, out):
    """The PC of the target's PVE profile for the lab's own QEMU: ISO (ide2), DISK (ide0, raw, made
    with DISK_GB GiB if missing), MEM, CPU, VGA, NIC (none: no NIC), ACCEL (tcg), EXTRA. The RTC
    runs in local time as qemu-server sets it for `ostype: wxp`."""
    disk = v["DISK"]
    if not os.path.exists(disk):
        with open(disk, "wb") as f:
            f.truncate(int(v.get("DISK_GB", "4")) << 30)
    args = [v.get("QEMU", "qemu-system-x86_64"), "-machine", f"pc,accel={v.get('ACCEL', 'tcg')}",
            "-cpu", v.get("CPU", "qemu64"), "-m", str(v.get("MEM", "1024")), "-vga", v.get("VGA", "std"),
            "-nodefaults", "-boot", "order=cd", "-rtc", "base=localtime",
            "-drive", f"if=ide,index=0,format=raw,file={disk}"]
    if v.get("ISO"):
        args += ["-drive", f"if=ide,index=2,media=cdrom,readonly=on,file={v['ISO']}"]
    if v.get("NIC", "rtl8139") != "none":
        args += ["-netdev", "user,id=n0", "-device", f"{v.get('NIC', 'rtl8139')},netdev=n0"]
    return args + v.get("EXTRA", "").split()


class Debugger:
    """Answers the kernel debugger's prompts on COM1 so the install goes on: an assertion with "i"
    (ignore it), a plain break-in with "cont". Without an answer the guest waits there for good (what
    a VM with nothing on its serial port does). poll() is called from the scenario's wait loops."""

    def __init__(self, m):
        self.m, self.cursor, self.answers = m, m.serial_cursor(), []

    def poll(self):
        r = self.m.serial_wait(KDB, self.cursor, timeout=0)
        if not r["matched"]:
            self.cursor = max(self.cursor, r["cursor"] - 200)  # a prompt that is still arriving matches later
            return
        self.cursor = r["cursor"]
        context = r["before"][-300:].strip().splitlines()
        reply = "i" if "boipt" in r["match"] else "cont"
        self.m.log(f"kernel debugger prompt after {context[-1] if context else '?'!r}: answering {reply!r}")
        self.answers.append({"t": round(self.m.elapsed()), "reply": reply, "before": "\n".join(context[-4:])})
        self.m.metrics["kdb_answers"] = len(self.answers)
        time.sleep(0.5)
        self.m.send(reply + "\r")


def wait_serial(m, pattern, cursor, timeout, dbg=None, what=None):
    """Wait for a regex on COM1 after `cursor`, answering debugger prompts meanwhile; returns
    serial_wait()'s match. Raises lab.Timeout with the last output."""
    end = time.time() + timeout
    while True:
        if dbg:
            dbg.poll()
        r = m.serial_wait(pattern, cursor, timeout=2)
        if r["matched"]:
            return r
        if time.time() > end:
            raise lab.Timeout(f"no {what or repr(pattern)} on COM1 within {timeout}s; last output:\n{r['tail'][-800:]}")


def count(m, pattern):
    return len(re.findall(pattern, m.text))


def esc(text):
    """A line for `echo` at cmd.exe's prompt: ^ before the characters cmd would act on."""
    if not text.isascii() or "%" in text or "\n" in text:
        raise ValueError(f"can't type {text!r} into cmd.exe")
    return re.sub(r"([\^&|<>()])", r"^\1", text)


# Keys go in slower than to DOS: while ReactOS installs a device or draws a window under TCG, keys
# typed at the DOS rate got lost, shift presses among them ("verC!" for "ver>COM1").
HOLD_MS, DELAY_S = 60, 0.12


def type_line(m, line, pause=0.8):
    m.fb_type(line, hold=HOLD_MS, delay=DELAY_S)
    time.sleep(0.3)
    m.fb_key("ret")
    time.sleep(pause)


def settle(m, below=30, seconds=5, need=2, timeout=600, poll=None):
    """Wait until the guest is idle: QEMU below `below` % of a host core in `need` samples of `seconds`
    in a row (after a logon ReactOS installs devices and opens the New Hardware Wizard; keys typed
    meanwhile get lost). `poll` (Debugger.poll) runs before each sample: a guest stopped in the
    kernel debugger is idle too. Returns the seconds it took."""
    t0, quiet = time.time(), 0
    while quiet < need:
        if poll:
            poll()
        pct = m.cpu_use(seconds)
        quiet = quiet + 1 if pct < below else 0
        if time.time() - t0 > timeout:
            raise lab.Timeout(f"the guest never idled below {below}% of a host core within {timeout}s")
    return round(time.time() - t0)


def run_dialog(m, command):
    """Win+R, the command, Enter (the Run dialog of ReactOS's explorer)."""
    m.fb_key("meta_l", "r")
    time.sleep(3)
    type_line(m, command, pause=1)


def open_cmd(m):
    run_dialog(m, "cmd")
    time.sleep(5)


def write_file(m, path, lines):
    """Write a text file from cmd.exe's prompt, one `echo` per line (redirection first, so a line that
    ends in a digit isn't taken as a handle number)."""
    for n, line in enumerate(lines):
        type_line(m, f"{'>' if n == 0 else '>>'}{path} echo {esc(line)}")


def read_back(m, command, last, timeout=30):
    """Run a command whose output goes to COM1 (`type FILE>COM1`) and return its lines, up to the line
    that ends with `last`."""
    cursor = m.serial_cursor()
    type_line(m, f"{command}>COM1")
    r = m.serial_wait(re.escape(last) + r"[ \t]*\n", cursor, timeout=timeout)
    if not r["matched"]:
        return None
    return [x.rstrip() for x in m.text[cursor - m.text_base:r["cursor"] - m.text_base].splitlines() if x.strip()]


def write_file_checked(m, path, lines, tries=3):
    """write_file(), then the file read back through COM1 must be `lines`; written again when not
    (a lost key). Needs COM1 free of the kernel debugger."""
    want = [x.rstrip() for x in lines]
    for attempt in range(1, tries + 1):
        write_file(m, path, lines)
        got = read_back(m, f"type {path}", want[-1])
        if got == want:
            m.log(f"{path}: {len(want)} lines, read back on COM1")
            return attempt
        m.log(f"{path} reads back as {got!r} (attempt {attempt}); writing it again")
    raise AssertionError(f"{path} doesn't read back as written after {tries} tries")


def dismiss_dialogs(m):
    """Esc twice: closes the New Hardware Wizard that the first logons show for QEMU's fw_cfg device
    (ACPI\\QEMU0002, no driver) and does nothing on an empty desktop."""
    for _ in range(2):
        m.fb_key("esc")
        time.sleep(2)


def report(m, r):
    """The text between WSHLAB-LOGON and WSHLAB-END, line ends as \\n."""
    body = re.search(REPORT, m.text[r["start"] - m.text_base:r["cursor"] - m.text_base]).group("body")
    return body.replace("\r\n", "\n").replace("\r", "\n")


def wait_report(m, timeout, what="the logon report (C:\\wshlab.cmd from the Run key)"):
    """Wait for a whole report from C:\\wshlab.cmd; fails at once when the kernel debugger is on (the
    boot loader's default wasn't changed)."""
    cursor = m.serial_cursor()
    end = time.time() + timeout
    while True:
        r = m.serial_wait(REPORT, cursor, timeout=5)
        if r["matched"]:
            text = report(m, r)
            m.log("report:\n" + text)
            return text
        if re.search(KD_BOOT, m.text):
            raise AssertionError("the kernel debugger is on (the boot loader's default is still ReactOS_KdSerial)")
        if time.time() > end:
            raise lab.Timeout(f"no {what} on COM1 within {timeout}s; last output:\n{r['tail'][-800:]}")


def shutdown(m, timeout=180, tries=2):
    """Power off from the Run dialog (ACPI) and wait for QEMU to end; once more when the guest is still
    running after `timeout` (a lost key in the command)."""
    for attempt in range(1, tries + 1):
        run_dialog(m, "shutdown -s -t 0")
        try:
            m.wait_exit(timeout)
            m.log("powered off")
            return
        except subprocess.TimeoutExpired:
            m.snap(f"still running {timeout}s after shutdown (attempt {attempt})", term=False)
            m.fb_key("esc")
            settle(m)
    raise lab.Timeout(f"the guest didn't power off after {tries} shutdown commands")
