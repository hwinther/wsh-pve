"""What the SunOS 4.1.4 scenarios share: the first boot's sys-config screens, the login and the shell.

SunOS 4.1.4's console output on ttya (zs) often holds back the last character of a burst until the
next one: a menu's cursor move or a field's echo shows up with the next key. The drivers here never
wait for that last character; they match the text before it and the screen titles (sys-config's
`SysConfA1` ... codes).
"""
import re
import time

from _sparc32 import ESP  # noqa: F401  (the scenarios boot by path)

SHELL = r"\n#\s*$"  # /bin/sh's root prompt; root's csh prompt is "<host># "


def shell(m, command, timeout=120):
    """Run a command at /bin/sh's root prompt and wait for the prompt after it."""
    m.send(command + "\r")
    m.expect(SHELL, timeout)


def gmt_moves(screen):
    """How many entries down the time zone region list Greenwich Mean Time is (the cursor starts on
    the first): the regions are the lines with `*   <name>`."""
    names = [x.strip() for x in re.findall(r"^\s+\*\s+(.+)$", screen, re.M)]
    if "Greenwich Mean Time" not in names:
        raise RuntimeError(f"no Greenwich Mean Time in the regions: {names}")
    return names.index("Greenwich Mean Time")


def sysconfig_rules(v):
    """(regex on the screen, answer, title) in the order they are tried: the screens of the first
    boot's sys-config (/usr/etc/install/sys-config) after an install without a network boot server.
    An answer is a string or a function of the screen. A retype screen comes before the screen it
    shares a code with."""
    ip, user = v.get("NET_IP", ""), v.get("USER", "")
    pw, upw = v["ROOT_PASSWORD"], v.get("USER_PASSWORD", "")
    return [
        (r"Enter choice \(1, 2, or 3\)", "2\r", "installation messages: manual setup"),
        (r"Press RETURN to begin the manual setup", "\r", "manual setup"),
        (r"SysConfA1", v["HOSTNAME"] + "\r", "host name"),
        (r"SysConfB1", lambda s: " " * gmt_moves(s) + "x", "time zone region"),
        (r"SysConfC\d+[\s\S]*GREENWICH MEAN TIME", "x", "time zone GMT"),
        (r"SysConfD1", "1\r", "system time: accept"),
        (r"SysConfE1", "1\r" if ip else "2\r", "network"),
        (r"SysConfE2", ip + "\r", "network address"),
        (r"SysConfE3", "2\r", "no NIS"),
        (r"SysConfF1", "y\r", "confirmation"),
        (r"SysConfH1[\s\S]*Retype new password", pw + "\r", "root password again"),
        (r"SysConfH1", pw + "\r", "root password"),
        (r"SysConfI1", "y\r" if user else "n\r", "user account"),
        (r"SysConfI2", "wsh-lab user\r", "user full name"),
        # the field has a suggestion in it (`luser`): erase it first
        (r"SysConfI3", "\b" * 12 + user + "\r", "user name"),
        (r"SysConfI4", "1001\r", "user id"),
        (r"SysConfI5[\s\S]*Retype new password", upw + "\r", "user password again"),
        (r"SysConfI5", upw + "\r", "user password"),
    ]


def which(rules, screen):
    return next((i for i, (rx, _, _) in enumerate(rules) if re.search(rx, screen)), None)


def sysconfig(m, v, timeout=900):
    """Answer sys-config until the login prompt. Each screen is answered once: after an answer the
    driver waits until the screen no longer matches the same rule (an echo that lags behind doesn't
    count as a new screen). An unknown screen that stays fails the run."""
    rules = sysconfig_rules(v)
    end = time.time() + timeout
    answered = []
    while True:
        m.quiet(2, timeout)
        screen = m.screen_text()
        if re.search(r"login:\s*$", screen):
            return answered
        i = which(rules, screen)
        if i is None:
            if time.time() > end:
                raise RuntimeError(f"sys-config: an unknown screen:\n{screen}")
            time.sleep(2)
            continue
        rx, answer, title = rules[i]
        if answered.count(title) >= 2:
            raise RuntimeError(f"sys-config asked for the {title} a third time:\n{screen}")
        m.snap(f"sys-config: {title}")
        m.send(answer(screen) if callable(answer) else answer)
        answered.append(title)
        left = time.time() + 300
        while which(rules, m.screen_text()) == i and not re.search(r"login:\s*$", m.screen_text()):
            if time.time() > left:
                raise RuntimeError(f"sys-config stayed on the {title} screen:\n{m.screen_text()}")
            m.quiet(2, 300)


def login(m, password, timeout=900):
    """Log in as root at `<host> login:` and start /bin/sh (root's shell is csh, whose history
    expansion would act on `!` in typed text)."""
    m.expect(r"login:\s*$", timeout)
    m.snap("login prompt")
    m.send("root\r")
    m.expect(r"Password:\s*$", 60)
    m.send(password + "\r")
    m.expect(r"#\s*$", 120)
    m.send("/bin/sh\r")
    m.expect(SHELL, 60)
