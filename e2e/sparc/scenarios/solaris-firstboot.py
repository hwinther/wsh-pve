"""The first boot of a freshly installed Solaris, as `lab.py install` runs it after the install: answers
the first-boot questions with the root password, logs in, writes the marker file, optionally adds a
user, and shuts down with `init 5`.

    lab.py run scenarios/solaris-firstboot.py --pve 120 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=sol26-ss5\\ninstalled=...')"

  ROOT_PASSWORD  what the first-boot questions set root's password to (sysidroot)   (none)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  USER           a non-root user to add (home /export/home/USER, /bin/sh)           (none)
  USER_PASSWORD  that user's password, set with passwd as root                      (none: locked)

The values are typed on the serial console: passwords at prompts that don't echo, the marker with
`echo`, so it must not contain single quotes.
"""
from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "",
            "USER": "", "USER_PASSWORD": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return sparc32_args(v, out)


def shell(m, command, timeout=120):
    """Run a command at the root prompt and wait for the prompt after it."""
    m.send(command + "\r")
    m.expect(r"\n#\s*$", timeout)


def run(m, v):
    prom_boot(m, v, "disk")
    m.expect(r"SunOS Release", 600)
    m.snap("kernel banner")
    login(m, password=v["ROOT_PASSWORD"])
    if v["MARKER"]:
        lines = v["MARKER"].splitlines()
        if any("'" in line for line in lines):
            raise ValueError("MARKER must not contain single quotes")
        shell(m, f"rm -f {MARKER_FILE}")
        for line in lines:
            shell(m, f"echo '{line}' >> {MARKER_FILE}")
        shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    if v["USER"]:
        user = v["USER"]
        shell(m, f"mkdir -p /export/home; useradd -d /export/home/{user} -m -s /bin/sh {user}")
        if v["USER_PASSWORD"]:
            m.send(f"passwd {user}\r")
            for _ in range(2):  # "New password:", "Re-enter new password:"
                m.expect(r"[Pp]assword:\s*$", 60)
                m.send(v["USER_PASSWORD"] + "\r")
            m.expect(r"\n#\s*$", 60)
        shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /export/home/{user}")
        m.snap(f"user {user}")
    power_off(m, "init 5")
