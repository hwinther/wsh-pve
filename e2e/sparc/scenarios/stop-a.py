"""Stop-A (L1-A, the Sun keyboard's abort) or a break on ttya sent to a running sparc32 guest: QEMU must
stay up, the guest must land where a Sun would put it (the PROM prompt) and `go` must give it back.

    lab.py run scenarios/stop-a.py --out /mnt/runs/stopa --var DISK=/mnt/runs/stopa/disk.raw

The chord goes in through QMP `send-key`, as PVE (`qm sendkey <vmid> stop-a`) and its noVNC console
send it: qcode `stop` is the Sun keyboard's Stop (L1). A break goes in through QMP
`chardev-send-break` on ttya (PVE's serial console has no way to send one); before pve-qemu
wsh/0160 QEMU's ESCC never ended a break and the guest hung in its serial interrupt.

OpenBIOS before openbios/patches/0008 powered the machine off on the client's op_enter ("abort,
power off" on ttya, QEMU exits 0; under PVE, which runs QEMU with -no-shutdown, qmeventd then ends
the VM). With 0008 the guest stays in memory at the `0 >` prompt and `go` resumes it.

  GUEST     solaris | sunos | netbsd: what DISK holds (the login prompt and first-boot questions);
            none: no guest, Stop-A at the firmware's own prompt                     (solaris)
  CONSOLE   fb | serial: where the firmware and the guest put the console; serial means no
            framebuffer unless VGA says otherwise (Solaris prefers one for its console)  (fb)
  AT        dtlogin: wait for Solaris's dtlogin (1024x768 cg3) instead of the first login
            prompt on the framebuffer                                                (none)
  KEYS      the chord as qcodes, pressed in this order and released in reverse     (stop a)
  BREAK     1: a break on ttya instead of the chord                                 (none)
  EXPECT    prom: the PROM prompt (the CPU stays in the firmware, "Type 'go' to resume" on a
            serial console); none: the guest ignores it and goes on; RX: a regex the console
            must show (NetBSD's GENERIC kernel enters its own debugger: `db>`)       (prom)
  RESUME    go: type `go` and check the guest answers; boot: type `boot` (OpenBIOS resets the
            machine) and wait for the login prompt again; anything else is typed as is (`c` for
            ddb) before the check                                                    (go)
  SHELL     1: log in as root (serial console only) and check with a command after the resume
            that the guest still runs                                                (1 on serial)
  REPEAT    how many times to go round                                               (2)

Metrics (result.json): rounds, the PC in the firmware while at the prompt (prom_pc).
"""
import re
import time

from _sparc32 import DEFAULTS as BASE, login, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "CONSOLE": "fb", "BOOT": "c", "NO_CD": "1", "GUEST": "solaris", "KEYS": "stop a", "BREAK": "",
            "EXPECT": "prom", "RESUME": "go", "SHELL": "", "REPEAT": "2", "AT": "", "VGA": ""}

PROMPTS = {"solaris": r"console login:", "sunos": r"login:", "netbsd": r"login:"}
GO = r"Type\s+'go' to resume"
# OpenBIOS for sparc32 runs at 0xffd00000 and up; Solaris, SunOS and NetBSD kernels run below it.
PROM_BASE = 0xFFD00000


def qemu_args(v, out):
    if not v["VGA"]:  # Solaris puts its console on a framebuffer when there is one
        v["VGA"] = "none" if v["CONSOLE"] == "serial" else "cg3"
    return sparc32_args(v, out)


def pcs(m, n=5):
    """The CPU's PC, n samples 0.2 s apart."""
    out = []
    for _ in range(n):
        out.append(int(re.search(r"pc: ([0-9a-f]+)", m.hmp("info registers")).group(1), 16))
        time.sleep(0.2)
    return out


def boot_fb(m, v):
    """Firmware to the guest's login prompt with the console on the framebuffer (first-boot questions
    answered). Returns "console", "dtlogin" or, without a guest, "prom"."""
    if v["GUEST"] == "none":
        m.fb_expect(r"Welcome to Open|for detailed information|ROM Rev", 300)
        time.sleep(15)  # nothing to boot (a blank disk): OpenBIOS stops at its prompt
        return "prom"
    if not v["BIOS"].startswith("openbios"):
        # The Sun PROMs find their NVRAM invalid and stop at ok after trying the network
        # (fb-display.py); with diag-switch? false `boot disk` boots the disk.
        for line in ("setenv diag-switch? false", "boot disk"):
            m.fb_expect_any([r"^\s*ok\b"], 300, tail=2)
            m.fb_stable(3, 120, 1)
            m.fb_type(line + "\r", hold=100, delay=0.3)
            time.sleep(3)
    prompt = PROMPTS[v["GUEST"]]
    while True:
        i = m.fb_expect_any([prompt, r"Please enter your user name", r"password:", r"Press Return to continue"],
                            1800, tail=8)
        if i == 1 or (i == 0 and v["AT"] != "dtlogin"):
            return ["console", "dtlogin"][i]
        if i == 0:  # AT=dtlogin: the console prompt comes first, dtlogin replaces it
            time.sleep(5)
            continue
        m.snap(["", "", "root password", "press return"][i])
        m.fb_type("\r")
        time.sleep(5)


def boot_serial(m, v):
    if v["GUEST"] == "none":
        m.expect(r"0 >", 300)
        return "prom"
    prom_boot(m, v, "disk")
    if v["SHELL"] != "0":
        login(m, PROMPTS[v["GUEST"]], 1800)
        return "shell"
    m.expect(PROMPTS[v["GUEST"]], 1800)
    return "console"


def check_alive(m, v, where, n):
    """The guest takes input and answers after the resume."""
    if where == "shell":
        m.send("expr 6 \\* 7\r")
        m.expect(r"^42\s*$", 120)
    elif where == "prom":
        if v["CONSOLE"] == "serial":
            m.send("1 2 + .\r")
            m.expect(r"3\s+ok", 30)
        else:
            m.fb_type("1 2 + .\r")
            time.sleep(2)
    # At a login prompt: Return gives the prompt again. With EXPECT=none the keys of an ignored chord
    # were typed as a user name, so the guest asks for its password instead.
    elif v["CONSOLE"] == "serial":
        m.send("\r")
        m.expect(PROMPTS[v["GUEST"]] + "|Password:", 120)
    elif where == "console":
        m.fb_type("\r")
        m.fb_expect_any([PROMPTS[v["GUEST"]], r"Password:"], 120, tail=4)
    elif n == 1:  # dtlogin: a user name moves it on to the password or the desktop question
        m.fb_type("root\r")
        m.fb_expect(r"enter your password|Which one would you like|Welcome to Solaris", 120)
    else:  # dtlogin, later rounds: the CPU is back in the guest
        pc = pcs(m)
        if all(p >= PROM_BASE for p in pc):
            raise AssertionError(f"round {n}: still in the firmware after the resume: PC {[hex(p) for p in pc]}")
    m.snap(f"round {n}: the guest answers")


def run(m, v):
    if v["CONSOLE"] == "serial" and not v["SHELL"]:
        v["SHELL"] = "1"
    where = boot_fb(m, v) if v["CONSOLE"] == "fb" else boot_serial(m, v)
    m.snap(f"at the {where} prompt")
    keys = v["KEYS"].split()
    rounds = int(v["REPEAT"])
    for n in range(1, rounds + 1):
        if v["BREAK"]:
            m.qmp.cmd("chardev-send-break", id="ttya")
            m.log(f"round {n}: break on ttya")
        else:
            m.fb_key(*keys)
            m.log(f"round {n}: send-key {' '.join(keys)}")
        time.sleep(3)
        m._check_alive()
        if v["EXPECT"] == "prom":
            if v["CONSOLE"] == "serial":
                m.expect(GO, 30)
            elif where == "console":  # over dtlogin the firmware's small print is beyond OCR
                m.fb_expect_any([r"go.{0,3}\s+to\s+resume"], 30, 2, tail=4)
            pc = pcs(m)  # a guest debugger reading the console through the firmware also shows here
            m.log("PC: " + " ".join(f"{p:08x}" for p in pc))
            if where != "prom" and not all(p >= PROM_BASE for p in pc):
                raise AssertionError(f"round {n}: the CPU isn't in the firmware: PC {[hex(p) for p in pc]}")
            m.metrics["prom_pc"] = f"{pc[-1]:08x}"
            m.snap(f"round {n}: PROM prompt")
        elif v["EXPECT"] != "none":
            if v["CONSOLE"] == "serial":
                m.expect(v["EXPECT"], 30)
            else:
                m.fb_expect_any([v["EXPECT"]], 30, 2, tail=3)
            m.snap(f"round {n}: {v['EXPECT']}")
        else:
            m.snap(f"round {n}: after the chord")
        if v["EXPECT"] != "none" and where != "prom":
            resume = v["RESUME"]
            if resume == "boot":
                (m.send if v["CONSOLE"] == "serial" else m.fb_type)("boot\r")
                m.log(f"round {n}: boot")
                if v["CONSOLE"] == "serial":
                    m.expect(r"Resetting", 30)
                else:  # the old login prompt is still on the screen until the reset clears it
                    m.fb_expect(r"Welcome to Open|for detailed information|ROM Rev", 120, 2)
                where = boot_fb(m, v) if v["CONSOLE"] == "fb" else boot_serial(m, v)
                m.snap(f"round {n}: booted again, at the {where} prompt")
            else:
                (m.send if v["CONSOLE"] == "serial" else m.fb_type)(resume + "\r")
                m.log(f"round {n}: {resume}")
                time.sleep(3)
        m._check_alive()
        check_alive(m, v, where, n)
        m.metrics["rounds"] = n
    m.stop()
