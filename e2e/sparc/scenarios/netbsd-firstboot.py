"""The first boot of a NetBSD that sysinst installed (netbsd-install-sparc64.py, netbsd-install-sparc.py),
as `lab.py install` runs it: logs in as root (no password yet), sets root's password, writes the
marker file, the host name and the network, optionally adds a user, and powers off with `halt -p`.

    lab.py run scenarios/netbsd-firstboot.py --pve 130 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=netbsd111-sparc64\\n...')"

  ARCH           sparc64 | sparc (from the VM's config with --pve)                    (sparc64)
  ROOT_PASSWORD  root's new password, typed at passwd's prompts (they don't echo)      (none: unchanged)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  HOSTNAME       /etc/myname                                                        (none)
  USER           a non-root user to add (home /home/USER, /bin/sh, group wheel)      (none)
  USER_PASSWORD  that user's password, set with passwd as root                      (none: locked)
  NET_MODE       static | dhcp                                                       (none)
  NET_IP, NET_NETMASK, NET_GATEWAY   static: /etc/ifconfig.<nic> and defaultroute in /etc/rc.conf
  NET_DNS        name servers, space separated; NET_DOMAIN their domain: /etc/resolv.conf  (none)
  NIC_NAME       the interface (hme0 on sparc64, le0 on sparc)

The values are typed on the serial console: passwords at prompts that don't echo, everything else
with `echo`, so the marker must not contain single quotes.
"""
import _netbsd

DEFAULTS = {**_netbsd.defaults("sparc64"), "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "",
            "HOSTNAME": "", "USER": "", "USER_PASSWORD": "", "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "",
            "NET_NETWORK": "", "NET_GATEWAY": "", "NET_DNS": "", "NET_DOMAIN": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return _netbsd.qemu_args(v, out)


def shell(m, command, timeout=300):
    return _netbsd.shell(m, command, timeout)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    shell(m, f"rm -f {path}")
    for line in lines:
        shell(m, f"echo '{line}' >> {path}")


def run(m, v):
    _netbsd.boot_disk(m, v)
    m.expect(r"NetBSD [\d.]+ \(GENERIC", 600)
    m.snap("kernel banner")
    _netbsd.login(m)
    if v["ROOT_PASSWORD"]:
        _netbsd.passwd(m, "root", v["ROOT_PASSWORD"])
        m.snap("root password set")
    if v["MARKER"]:
        write_lines(m, MARKER_FILE, v["MARKER"].splitlines())
        shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    if v["HOSTNAME"]:
        shell(m, f"echo {v['HOSTNAME']} > /etc/myname; hostname {v['HOSTNAME']}")
    if v["NET_MODE"]:
        network(m, v)
    if v["USER"]:
        user = v["USER"]
        shell(m, f"useradd -m -d /home/{user} -s /bin/sh -G wheel {user}")
        if v["USER_PASSWORD"]:
            _netbsd.passwd(m, user, v["USER_PASSWORD"])
        shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /home/{user}")
        m.snap(f"user {user}")
    _netbsd.power_off(m, v)


def network(m, v):
    """The network in NetBSD's own files, read by /etc/rc.d/network and dhcpcd at boot:

    static  /etc/ifconfig.<nic> (`inet <ip> netmask <mask>`), `defaultroute=<gw>` in /etc/rc.conf,
            the address and host name in /etc/hosts
    dhcp    `dhcpcd=YES` in /etc/rc.conf (dhcpcd sends the host name, takes the address, router and
            name servers and writes /etc/resolv.conf through resolvconf)
    dns     NET_DNS (+ NET_DOMAIN): /etc/resolv.conf (with DHCP, dhcpcd replaces it when the server
            sends name servers)"""
    nic = _netbsd.nic(v)
    if v["NET_MODE"] == "dhcp":
        shell(m, "echo dhcpcd=YES >> /etc/rc.conf")
    else:
        write_lines(m, f"/etc/ifconfig.{nic}", [f"inet {v['NET_IP']} netmask {v['NET_NETMASK']}"])
        if v["NET_GATEWAY"]:
            shell(m, f"echo defaultroute={v['NET_GATEWAY']} >> /etc/rc.conf")
        if v["HOSTNAME"]:
            names = v["HOSTNAME"] + (f" {v['HOSTNAME']}.{v['NET_DOMAIN']}" if v["NET_DOMAIN"] else "")
            shell(m, f"echo '{v['NET_IP']} {names}' >> /etc/hosts")
    if v["NET_DNS"]:
        write_lines(m, "/etc/resolv.conf", ([f"domain {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else [])
                    + [f"nameserver {s}" for s in v["NET_DNS"].split()])
    shell(m, f"cat /etc/ifconfig.{nic} /etc/resolv.conf 2>/dev/null; grep -E '^(dhcpcd|defaultroute)=' /etc/rc.conf;"
             " tail -2 /etc/hosts")
    m.snap(f"network: {v['NET_MODE']}")
