"""The first boot of a Debian 13 (sparc64) that debian13-install-sparc64.py installed, as `lab.py install`
runs it: GRUB boots the disk, root logs in on ttyS0 (no password yet: the preseed file's late command
emptied it), sets root's password, writes the marker file, optionally adds a user, and powers off.

    lab.py run scenarios/debian13-firstboot.py --pve 9900 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=debian13-sun4u\\n...')"

  ROOT_PASSWORD  root's new password (chpasswd, not echoed)                  (none: unchanged)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                  (none: no file)
  USER           a non-root user to add (home /home/USER, /bin/bash)           (none)
  USER_PASSWORD  that user's password                                        (none: locked)

The network (address, netmask, router, name servers, domain, host name) is the installer's, from the
preseed file (/etc/network/interfaces, /etc/resolv.conf, /etc/hostname); the marker is typed with
`echo`, so it must not contain single quotes.
"""
import _debian13

DEFAULTS = {**_debian13.DEFAULTS, "ISO": "", "ROOT_PASSWORD": "", "MARKER": "", "USER": "", "USER_PASSWORD": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return _debian13.qemu_args(v, out)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    _debian13.shell(m, f"rm -f {path}")
    for line in lines:
        _debian13.shell(m, f"echo '{line}' >> {path}")


def run(m, v):
    _debian13.boot_disk(m)
    _debian13.login(m)
    if v["ROOT_PASSWORD"]:
        _debian13.passwd(m, "root", v["ROOT_PASSWORD"])
        m.snap("root password set")
    if v["MARKER"]:
        write_lines(m, MARKER_FILE, v["MARKER"].splitlines())
        _debian13.shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    _debian13.shell(m, "cat /etc/hostname /etc/network/interfaces /etc/resolv.conf 2>/dev/null")
    m.snap("network")
    if v["USER"]:
        user = v["USER"]
        _debian13.shell(m, f"useradd -m -d /home/{user} -s /bin/bash {user}")
        if v["USER_PASSWORD"]:
            _debian13.passwd(m, user, v["USER_PASSWORD"])
        _debian13.shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /home/{user}")
        m.snap(f"user {user}")
    _debian13.shell(m, "sync")
    _debian13.power_off(m)
