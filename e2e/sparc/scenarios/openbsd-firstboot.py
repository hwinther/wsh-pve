"""The first boot of an OpenBSD/sparc64 that openbsd-install-sparc64.py installed, as `lab.py install`
runs it: logs in as root (the installer set the password), writes the marker file, the host name and
the network, optionally adds a user, checks ntpd (sparc64: enabled and running; sparc: off) and powers
off with `halt -p`.

    lab.py run scenarios/openbsd-firstboot.py --pve 9210 --out /mnt/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=openbsd80-sun4u\\n...')"

  ROOT_PASSWORD  root's password                                                    (required)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  HOSTNAME       /etc/myname (with NET_DOMAIN: <host>.<domain>)                     (none)
  USER           a non-root user to add (home /home/USER, ksh, group wheel)          (none)
  USER_PASSWORD  that user's password, set with passwd as root                      (none: locked)
  NET_MODE       static                                                              (none)
  NET_IP, NET_NETMASK, NET_GATEWAY   /etc/hostname.<nic>, /etc/mygate
  NET_DNS        name servers, space separated; NET_DOMAIN their domain: /etc/resolv.conf  (none)
  NIC_NAME       the interface                                                      (hme0)
  NTPD           on: ntpd enabled and running; off: turned off (_openbsd.ntpd_on)    (on for sparc64)

The values are typed on the serial console with `echo`, so the marker must not contain single quotes.
"""
import re

import _openbsd

DEFAULTS = {**_openbsd.DEFAULTS, "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "", "HOSTNAME": "", "USER": "",
            "USER_PASSWORD": "", "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "", "NET_NETWORK": "",
            "NET_GATEWAY": "", "NET_DNS": "", "NET_DOMAIN": "", "NTPD": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return _openbsd.qemu_args(v, out)


def shell(m, command, timeout=300):
    return _openbsd.shell(m, command, timeout)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    shell(m, f"rm -f {path}")
    for line in lines:
        shell(m, f"echo '{line}' >> {path}")


def run(m, v):
    m.expect(r"OpenBSD [\d.]+ \(GENERIC", 600)
    m.snap("kernel banner")
    _openbsd.login(m, v["ROOT_PASSWORD"])
    if v["MARKER"]:
        write_lines(m, MARKER_FILE, v["MARKER"].splitlines())
        shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    if v["HOSTNAME"]:
        fqdn = v["HOSTNAME"] + (f".{v['NET_DOMAIN']}" if v["NET_DOMAIN"] else "")
        shell(m, f"echo {fqdn} > /etc/myname; hostname {fqdn}")
    if v["NET_MODE"]:
        network(m, v)
    if v["USER"]:
        user = v["USER"]
        shell(m, f"useradd -m -d /home/{user} -s /bin/ksh -G wheel {user}")
        if v["USER_PASSWORD"]:
            _openbsd.passwd(m, user, v["USER_PASSWORD"])
        shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /home/{user}")
        m.snap(f"user {user}")
    check_ntpd(m, v)
    _openbsd.power_off(m, v)


def check_ntpd(m, v):
    """sparc64: ntpd enabled (`rcctl get ntpd flags` not NO) and running; sparc: turned off (the install
    did it; kept for a disk installed some other way) and not running."""
    on = _openbsd.ntpd_on(v)
    if not on:
        _openbsd.disable_ntpd(m)
    out = shell(m, "echo ntpd: flags=$(rcctl get ntpd flags) running=$(pgrep -x ntpd | wc -l | tr -d ' ')")
    mt = re.search(r"ntpd: flags=(\S*) running=(\d+)", out)
    if not mt:
        raise AssertionError(f"no ntpd state in {out.strip()!r}")
    if on and (mt.group(1) == "NO" or mt.group(2) == "0"):
        raise AssertionError(f"ntpd is disabled or not running: {mt.group(0)}")
    if not on and mt.group(0) != "ntpd: flags=NO running=0":
        raise AssertionError(f"ntpd is enabled or running: {mt.group(0)}")


def network(m, v):
    """The network in OpenBSD's own files, read by netstart at boot: /etc/hostname.<nic> (`inet <ip>
    <netmask>`), /etc/mygate (the router), /etc/resolv.conf (NET_DNS, NET_DOMAIN), the address and
    host name in /etc/hosts."""
    nic = _openbsd.nic(v)
    write_lines(m, f"/etc/hostname.{nic}", [f"inet {v['NET_IP']} {v['NET_NETMASK']}"])
    shell(m, f"chmod 640 /etc/hostname.{nic}")
    if v["NET_GATEWAY"]:
        write_lines(m, "/etc/mygate", [v["NET_GATEWAY"]])
    else:
        shell(m, "rm -f /etc/mygate")
    if v["NET_DNS"]:
        write_lines(m, "/etc/resolv.conf", ([f"domain {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else [])
                    + [f"nameserver {s}" for s in v["NET_DNS"].split()])
    if v["HOSTNAME"]:
        names = v["HOSTNAME"] + (f" {v['HOSTNAME']}.{v['NET_DOMAIN']}" if v["NET_DOMAIN"] else "")
        shell(m, f"grep -v '^{v['NET_IP']}[[:space:]]' /etc/hosts > /etc/hosts.new; echo '{v['NET_IP']} {names}' >> /etc/hosts.new;"
                 " mv /etc/hosts.new /etc/hosts; chmod 644 /etc/hosts")
    shell(m, f"cat /etc/hostname.{nic} /etc/mygate /etc/resolv.conf 2>/dev/null; tail -2 /etc/hosts")
    m.snap(f"network: {v['NET_MODE']}")
