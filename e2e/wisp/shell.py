"""Drive wisp's interactive shell (wisp=shell) over the serial console: run.py --shell.

QEMU's serial console is on stdin and stdout. The driver waits for each prompt, sends the next
command and keeps what came back; at the end it checks the answers: the line editing (a mistyped
"help" fixed with two Backspaces), the info lines, the CRC of bench and of "crc 64" against the
model in run.py, every row of mandel against mandel_rows() below, the endian game's byte-order
line and first round against endian_words()/endian_answer() (for the architecture under test) and
a deliberately wrong guess's reply, and the power-off. With a tier-2 profile (run.py --shell
--tier2), the script also has disk, net and smp (tier2_script()), and run.py checks their lines
with tier2.py. Python standard library only.
"""

import os
import re
import signal
import subprocess
import threading
import time

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PROMPT = re.compile(r"wisp:(\S+)> ")
FOOTER = re.compile(r"  \d+ x \d+ points, ")
LOOP = re.compile(r"crc32 0x([0-9a-f]{8}) after (\d+) rounds \(\d+ KiB\) in (\d+) ms")

# "hepl" and two Backspaces (DEL, what a terminal sends) and "lp": the kernel's line discipline
# makes it "help". "endian" starts a new game and shows round 1; "endian 0" is a deliberately
# wrong guess (check_answers checks its reply against the model's answer for the arch under test).
SCRIPT = ("hepl\x7f\x7flp", "info", "bench", "crc 64", "mandel", "endian", "endian 0", "poweroff")

# Architectures this lab boots as big-endian; the rest (x86_64, i386) are little-endian.
BIG_ENDIAN_ARCHES = ("sparc32", "sparc64")


def arch_is_big_endian(arch):
    """True for the big-endian architectures under test (sparc32, sparc64)."""
    return arch in BIG_ENDIAN_ARCHES


def reboot_script(script):
    """A script that ends with reboot instead of poweroff (run.py --reboot): QEMU runs with
    -no-reboot, so the machine's reset ends it as the power-off does."""
    return script[:-1] + ("reboot",)


def tier2_script(profile):
    """SCRIPT with the tier-2 commands for a profile's devices (tier2.py) before the poweroff:
    disk and net take their devices from the kernel command line, smp runs with more than one
    CPU."""
    extra = []
    if profile["disks"]:
        extra.append("disk")
    if profile.get("nic"):
        extra.append("net")
    if profile.get("smp", 1) > 1:
        extra.append("smp")
    return SCRIPT[:-1] + tuple(extra) + SCRIPT[-1:]


# init.c's Mandelbrot: 4.12 fixed point, 78 x 20 characters, 32 iterations.
MANDEL_COLS, MANDEL_ROWS, MANDEL_ITER = 78, 20, 32
MANDEL_X0, MANDEL_DX, MANDEL_DY = -9216, 158, 248
MANDEL_CHARS = " .:-=+*#%@"


def mandel_count(cx, cy):
    x = y = n = 0
    while n < MANDEL_ITER:
        # Python's >> on a negative number rounds down, as gcc's arithmetic shift does
        x2 = (x * x) >> 12
        y2 = (y * y) >> 12
        if x2 + y2 > 4 << 12:
            break
        y = ((x * y) >> 11) + cy
        x = x2 - y2 + cx
        n += 1
    return n


def mandel_rows():
    """The rows init.c's mandel prints (without the leading space): the same integer math."""
    rows = []
    for row in range(MANDEL_ROWS):
        cy = (2 * row - (MANDEL_ROWS - 1)) * MANDEL_DY
        out = []
        for col in range(MANDEL_COLS):
            cx = MANDEL_X0 + col * MANDEL_DX
            n = mandel_count(cx, cy)
            out.append("@" if n == MANDEL_ITER else MANDEL_CHARS[n * 9 // MANDEL_ITER])
        rows.append("".join(out))
    return rows


# init.c's endian game: a xorshift32 stream seeded with "endi", one word per round, and the value
# the machine under test's CPU reads from that word's bytes (the "bytes" line prints them low
# address first, which is high byte first): the word unchanged on a big-endian CPU, byte-swapped
# on a little-endian one. check_answers() checks SCRIPT's "endian" and "endian 0" against this
# model for the arch under test; tests/test_shell.py also drives a full game with its own scripts.
ENDIAN_SEED = 0x656E6469  # "endi"


def endian_words(n, seed=ENDIAN_SEED):
    """The first n words of the endian game's xorshift32 stream, in round order: the same
    generator xorshift() advances for the tier-2 checks, seeded for the game alone."""
    x = seed
    words = []
    for _ in range(n):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        words.append(x)
    return words


def endian_answer(word, big_endian=False):
    """The 32-bit value the machine under test's CPU reads from word's bytes (the "bytes" line
    prints them low address first, i.e. high byte first): word unchanged for a big-endian CPU,
    with its bytes reversed for a little-endian one."""
    order = "big" if big_endian else "little"
    return int.from_bytes(word.to_bytes(4, "big"), order)


def endian_bytes_line(word):
    """The "bytes" line init.c's endian game prints for one round's word."""
    return "  bytes {:02x} {:02x} {:02x} {:02x}".format((word >> 24) & 0xFF, (word >> 16) & 0xFF,
                                                         (word >> 8) & 0xFF, word & 0xFF)


def endian_byteorder_line(big_endian):
    """The line init.c's endian game prints once, when a new game starts, naming this machine's
    byte order."""
    return "  this machine is {}-endian".format("big" if big_endian else "little")


def endian_explain(big_endian):
    """The short line init.c's endian game prints after a wrong guess, naming the byte order that
    makes the right value what it is."""
    if big_endian:
        return "  big-endian: the first byte is the most significant"
    return "  little-endian: the first byte is the least significant"


def clean(text):
    """Console text without colour sequences and carriage returns."""
    return ANSI.sub("", text).replace("\r", "")


def as_typed(command):
    """The line a terminal makes of the keys: each Backspace (DEL or ^H) removes a character."""
    out = []
    for c in command:
        if c in "\x7f\b":
            if out:
                out.pop()
        else:
            out.append(c)
    return "".join(out)


def split_transcript(text, echo=True):
    """[(prompt arch, [output lines])] per command, from a whole console transcript.

    The text before the first prompt (the boot) is dropped. With echo (a terminal in canonical
    mode), the first line after a prompt is the echoed command and is dropped too.
    """
    parts = PROMPT.split(clean(text))
    out = []
    # parts: [boot, arch1, after1, arch2, after2, ...]
    for i in range(1, len(parts) - 1, 2):
        lines = parts[i + 1].split("\n")
        if echo:
            lines = lines[1:]
        if lines and lines[-1] == "":
            lines.pop()
        out.append((parts[i], lines))
    return out


def check_answers(arch, script, answers, crc_for, default_loops):
    """Problems with the answers to the script's commands, and the numbers worth reporting."""
    problems, numbers = [], {}
    if len(answers) < len(script):
        problems.append(f"{len(answers)} of {len(script)} commands answered")
    for (prompt_arch, lines), command in zip(answers, script):
        typed = as_typed(command)
        name = typed.split(" ")[0]
        if prompt_arch != arch:
            problems.append(f"{name}: prompt arch {prompt_arch} != {arch}")
        text = "\n".join(lines)
        if name == "help":
            if "  mandel " not in text or "  poweroff " not in text:
                problems.append("help: no command list"
                                + (" (typed with Backspace)" if typed != command else ""))
        elif name == "info":
            m = re.search(r"^  arch +(\S+)", text, re.M)
            if not m or m.group(1) != arch:
                problems.append(f"info: arch {m.group(1) if m else None} != {arch}")
            for key, pattern in (("cpus", r"\d+"), ("memory", r"\d+ kB"),
                                 ("uptime", r"\d+\.\d{3} s"), ("pid", r"\d+")):
                if not re.search(rf"^  {key} +{pattern}", text, re.M):
                    problems.append(f"info: no {key} line")
        elif name in ("bench", "crc"):
            m = LOOP.search(text)
            if not m:
                problems.append(f"{name}: no result")
                continue
            crc, loops, ms = int(m.group(1), 16), int(m.group(2)), int(m.group(3))
            want_loops = default_loops if name == "bench" else int(command.split()[1])
            want = crc_for(loops)
            if loops != want_loops:
                problems.append(f"{name}: {loops} rounds != {want_loops}")
            elif want is not None and crc != want:
                problems.append(f"{name}: crc 0x{crc:08x} != 0x{want:08x}")
            numbers[f"{name}_ms"] = ms
            numbers[f"{name}_crc"] = f"0x{crc:08x}"
        elif name == "mandel":
            rows = [line[1:] for line in lines if not FOOTER.match(line)]
            want = mandel_rows()
            if rows != want:
                bad = [i for i, (a, b) in enumerate(zip(rows, want)) if a != b]
                problems.append(f"mandel: {len(rows)} rows, {len(want)} wanted, differing rows "
                                f"{bad[:5]}")
            m = re.search(r"points, \d+ iterations, (\d+) ms", text)
            if m:
                numbers["mandel_ms"] = int(m.group(1))
        elif name == "endian":
            big_endian = arch_is_big_endian(arch)
            word = endian_words(1)[0]
            if command.strip() == "endian":
                # a new game: the byte-order line, then round 1's bytes line
                if endian_byteorder_line(big_endian) not in lines:
                    problems.append(f"endian: no {'big' if big_endian else 'little'}-endian line")
                if endian_bytes_line(word) not in lines:
                    problems.append("endian: no first round bytes line")
            else:
                # a deliberately wrong guess ("endian 0"): the reply must carry the model's
                # right answer for this arch, not another architecture's
                want = endian_answer(word, big_endian)
                if f"0x{want:08x}" not in text:
                    problems.append(f"endian: wrong-guess reply missing 0x{want:08x}")
        elif name == "poweroff":
            if "powering off" not in text:
                problems.append("poweroff: no answer")
        elif name == "reboot":
            if "restarting" not in text:
                problems.append("reboot: no answer")
            if "Reboot failed" in text or "Kernel panic" in text:
                problems.append("reboot: the kernel panicked instead of restarting")
    return problems, numbers


def drive(cmd, script, timeout, prompt_timeout=60):
    """Boot QEMU, answer each prompt with the next command; return the raw run record."""
    load = os.getloadavg()
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True)
    chunks = []  # (t, text)
    cond = threading.Condition()

    def reader():
        while True:
            data = os.read(proc.stdout.fileno(), 4096)
            with cond:
                if not data:
                    chunks.append((time.monotonic() - t0, None))
                    cond.notify_all()
                    return
                chunks.append((time.monotonic() - t0, data.decode("utf-8", "replace")))
                cond.notify_all()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    timed_out = threading.Event()

    def kill():
        timed_out.set()
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    timer = threading.Timer(timeout, kill)
    timer.start()
    times = []  # seconds from sending a command (or start) to the next prompt

    def text():
        return "".join(c for _, c in chunks if c)

    def wait_prompt(count):
        """Wait for the count-th prompt at the end of the output; False at EOF or timeout."""
        deadline = time.monotonic() + prompt_timeout
        with cond:
            while True:
                if len(PROMPT.findall(clean(text()))) >= count and \
                        re.search(r"> $", clean(text())):
                    return True
                if (chunks and chunks[-1][1] is None) or timed_out.is_set():
                    return False
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                cond.wait(min(left, 0.5))

    sent = time.monotonic()
    for n, command in enumerate(script, 1):
        if not wait_prompt(n):
            break
        times.append(round(time.monotonic() - sent, 3))
        sent = time.monotonic()
        try:
            proc.stdin.write((command + "\n").encode())
            proc.stdin.flush()
        except BrokenPipeError:
            break
    _, status, rusage = os.wait4(proc.pid, 0)
    t_exit = time.monotonic() - t0
    timer.cancel()
    thread.join(5)
    return {
        "load1": round(load[0], 2), "load5": round(load[1], 2), "t_exit": t_exit,
        "exit_code": os.waitstatus_to_exitcode(status), "timed_out": timed_out.is_set(),
        "max_rss_kb": rusage.ru_maxrss, "user_s": round(rusage.ru_utime, 3),
        "sys_s": round(rusage.ru_stime, 3), "text": text(), "prompt_s": times,
        "t_prompt": first_prompt_time(chunks),
    }


def first_prompt_time(chunks):
    """Seconds from the start to the chunk that completed the first prompt, or None."""
    acc = ""
    for t, c in chunks:
        if c is None:
            break
        acc += c
        if PROMPT.search(clean(acc)):
            return round(t, 3)
    return None
