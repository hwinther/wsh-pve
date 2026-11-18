"""The first boot of a Debian 4.0 (sparc) that debian-install-sparc.py installed, as `lab.py install` runs
it: logs in as root on ttyS0 (no password yet: the preseed file's late command emptied it), sets
root's password, writes the marker file, optionally adds a user, and powers off.

    lab.py run scenarios/debian-firstboot.py --pve 9900 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=debian40-ss5\\n...')"

  ROOT_PASSWORD  root's new password, typed at passwd's prompts (they don't echo)    (none: unchanged)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                       (none: no file)
  USER           a non-root user to add (home /home/USER, /bin/bash)                (none)
  USER_PASSWORD  that user's password, set with passwd as root                    (none: locked)

The network (address, netmask, router, name servers, domain, host name) is the installer's, from the
preseed file (/etc/network/interfaces, /etc/resolv.conf, /etc/hostname); the values here are typed
with `echo`, so the marker must not contain single quotes.
"""
import _debian

DEFAULTS = {**_debian.DEFAULTS, "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "", "USER": "", "USER_PASSWORD": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return _debian.qemu_args(v, out)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    _debian.shell(m, f"rm -f {path}")
    for line in lines:
        _debian.shell(m, f"echo '{line}' >> {path}")


def run(m, v):
    _debian.boot_disk(m, v)
    _debian.login(m)
    if v["ROOT_PASSWORD"]:
        _debian.passwd(m, "root", v["ROOT_PASSWORD"])
        m.snap("root password set")
    if v["MARKER"]:
        write_lines(m, MARKER_FILE, v["MARKER"].splitlines())
        _debian.shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    _debian.shell(m, "cat /etc/hostname /etc/network/interfaces /etc/resolv.conf 2>/dev/null")
    m.snap("network")
    if v["USER"]:
        user = v["USER"]
        _debian.shell(m, f"useradd -m -d /home/{user} -s /bin/bash {user}")
        if v["USER_PASSWORD"]:
            _debian.passwd(m, user, v["USER_PASSWORD"])
        _debian.shell(m, f"grep '^{user}:' /etc/passwd; /bin/ls -ld /home/{user}")
        m.snap(f"user {user}")
    _debian.power_off(m)
