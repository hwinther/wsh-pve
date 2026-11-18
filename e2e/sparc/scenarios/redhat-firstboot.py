"""The first boot of a Red Hat Linux 6.2 (SPARC) that redhat-install-sparc.py installed, as `lab.py
install` runs it: logs in as root on ttyS0 (no password yet: the kickstart's %post left it empty),
sets root's password, writes the marker file and the rest of the network, optionally adds a user,
and powers off.

    lab.py run scenarios/redhat-firstboot.py --pve 9600 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=redhat62-ss5\\n...')"

  ROOT_PASSWORD  root's new password, typed at passwd's prompts (they don't echo)    (none: unchanged)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                       (none: no file)
  USER           a non-root user to add (home /home/USER, /bin/bash)                (none)
  USER_PASSWORD  that user's password, set with passwd as root                    (none: locked)
  HOSTNAME       HOSTNAME in /etc/sysconfig/network, and with NET_IP in /etc/hosts as
                 HOSTNAME.NET_DOMAIN (or .localdomain) and HOSTNAME             (none)
  NET_GATEWAY    the default router: GATEWAY in /etc/sysconfig/network            (none)
  NET_DNS        name servers, space separated; NET_DOMAIN their domain: /etc/resolv.conf  (none)

The address and netmask come from the kickstart file (the install); the values here are typed with
`echo`, so the marker must not contain single quotes.
"""
import _redhat

DEFAULTS = {**_redhat.DEFAULTS, "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "", "USER": "", "USER_PASSWORD": "",
            "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "", "NET_NETWORK": "", "NET_GATEWAY": "", "NET_DNS": "",
            "NET_DOMAIN": "", "HOSTNAME": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return _redhat.qemu_args(v, out)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    _redhat.shell(m, f"rm -f {path}")
    for line in lines:
        _redhat.shell(m, f"echo '{line}' >> {path}")


def run(m, v):
    _redhat.boot_disk(m, v)
    _redhat.login(m)
    if v["ROOT_PASSWORD"]:
        _redhat.passwd(m, "root", v["ROOT_PASSWORD"])
        m.snap("root password set")
    if v["MARKER"]:
        write_lines(m, MARKER_FILE, v["MARKER"].splitlines())
        _redhat.shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    network(m, v)
    if v["USER"]:
        user = v["USER"]
        _redhat.shell(m, f"useradd -m -d /home/{user} -s /bin/bash {user}")
        if v["USER_PASSWORD"]:
            _redhat.passwd(m, user, v["USER_PASSWORD"])
        # /bin/ls: root's `ls` is an alias with --color, whose escape sequences can split across two
        # reads of the console and leave the end marker off the start of its line
        _redhat.shell(m, f"grep '^{user}:' /etc/passwd; /bin/ls -ld /home/{user}")
        m.snap(f"user {user}")
    _redhat.power_off(m)


def network(m, v):
    """What the kickstart file doesn't set, in Red Hat's own files (rc.sysinit and init.d/network read
    them): HOSTNAME= in /etc/sysconfig/network and the address and name in /etc/hosts, the default
    router as GATEWAY=, the name servers and domain in /etc/resolv.conf. The address and netmask are
    the installer's (/etc/sysconfig/network-scripts/ifcfg-eth0)."""
    if v["HOSTNAME"]:
        name = v["HOSTNAME"]
        # a name with a dot first: sendmail waits 2 minutes at every boot for a fully qualified name
        # when /etc/hosts has only the short one and there is no DNS (Red Hat's own default is
        # localhost.localdomain)
        names = f"{name}.{v['NET_DOMAIN'] or 'localdomain'} {name}"
        _redhat.shell(m, "grep -v '^HOSTNAME=' /etc/sysconfig/network > /tmp/network &&"
                         f" echo HOSTNAME={name} >> /tmp/network && cat /tmp/network > /etc/sysconfig/network;"
                         f" rm -f /tmp/network; hostname {name}")
        if v["NET_IP"]:
            _redhat.shell(m, f"echo '{v['NET_IP']} {names}' >> /etc/hosts")
    if v["NET_GATEWAY"]:
        _redhat.shell(m, f"echo GATEWAY={v['NET_GATEWAY']} >> /etc/sysconfig/network")
    if v["NET_DNS"]:
        write_lines(m, "/etc/resolv.conf", ([f"search {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else [])
                    + [f"nameserver {s}" for s in v["NET_DNS"].split()])
    _redhat.shell(m, "cat /etc/sysconfig/network /etc/sysconfig/network-scripts/ifcfg-eth0 /etc/hosts;"
                     " cat /etc/resolv.conf 2>/dev/null")
    m.snap("network")
