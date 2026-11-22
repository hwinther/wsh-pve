"""The first boot of a FreeBSD/sparc64 that freebsd-install-sparc64.py installed, as `lab.py install`
runs it: logs in as root (no password yet), sets root's password, writes the marker file, the host
name and the network, optionally adds a user, and powers off with `shutdown -p now`.

    lab.py run scenarios/freebsd-firstboot.py --pve 9220 --out /mnt/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=freebsd124-sun4u\n...')"

  ROOT_PASSWORD  root's new password, typed at passwd's prompts (they don't echo)      (none: unchanged)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  HOSTNAME       `hostname` in /etc/rc.conf (with NET_DOMAIN: <host>.<domain>)       (none)
  USER           a non-root user to add (home /home/USER, /bin/sh, group wheel)      (none)
  USER_PASSWORD  that user's password, set with passwd as root                      (none: locked)
  NET_MODE       static | dhcp                                                       (none)
  NET_IP, NET_NETMASK, NET_GATEWAY   static: ifconfig_<nic> and defaultrouter in /etc/rc.conf
  NET_DNS        name servers, space separated; NET_DOMAIN their domain: /etc/resolv.conf  (none)
  NIC_NAME       the interface                                                      (hme0)

rc.conf is written with sysrc. The values are typed on the serial console: passwords at prompts that
don't echo, everything else with `echo`, so the marker must not contain single quotes.
"""
import _freebsd

DEFAULTS = {**_freebsd.DEFAULTS, "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "",
            "HOSTNAME": "", "USER": "", "USER_PASSWORD": "", "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "",
            "NET_NETWORK": "", "NET_GATEWAY": "", "NET_DNS": "", "NET_DOMAIN": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return _freebsd.qemu_args(v, out)


def shell(m, command, timeout=300):
    return _freebsd.shell(m, command, timeout)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    shell(m, f"rm -f {path}")
    for line in lines:
        shell(m, f"echo '{line}' >> {path}")


def run(m, v):
    m.expect(_freebsd.KERNEL, 600)
    m.snap("kernel banner")
    _freebsd.login(m)
    if v["ROOT_PASSWORD"]:
        _freebsd.passwd(m, "root", v["ROOT_PASSWORD"])
        m.snap("root password set")
    if v["MARKER"]:
        write_lines(m, MARKER_FILE, v["MARKER"].splitlines())
        shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        m.snap("marker file")
    if v["HOSTNAME"]:
        fqdn = v["HOSTNAME"] + (f".{v['NET_DOMAIN']}" if v["NET_DOMAIN"] else "")
        shell(m, f"sysrc hostname={fqdn}; hostname {fqdn}")
    if v["NET_MODE"]:
        network(m, v)
    if v["USER"]:
        user = v["USER"]
        shell(m, f"pw useradd {user} -m -d /home/{user} -s /bin/sh -G wheel")
        if v["USER_PASSWORD"]:
            _freebsd.passwd(m, user, v["USER_PASSWORD"])
        shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /home/{user}")
        m.snap(f"user {user}")
    _freebsd.check_disk(m)
    _freebsd.power_off(m, v)


def network(m, v):
    """The network in /etc/rc.conf (sysrc), read by rc.d/netif and dhclient at boot:

    static  `ifconfig_<nic>="inet <ip> netmask <mask>"`, `defaultrouter=<gw>`, the address and host
            name in /etc/hosts
    dhcp    `ifconfig_<nic>="DHCP"` (dhclient takes the address, router and name servers and writes
            /etc/resolv.conf)
    dns     NET_DNS (+ NET_DOMAIN): /etc/resolv.conf"""
    nic = _freebsd.nic(v)
    if v["NET_MODE"] == "dhcp":
        shell(m, f"sysrc ifconfig_{nic}=DHCP")
    else:
        shell(m, f"sysrc ifconfig_{nic}='inet {v['NET_IP']} netmask {v['NET_NETMASK']}'")
        if v["NET_GATEWAY"]:
            shell(m, f"sysrc defaultrouter={v['NET_GATEWAY']}")
        if v["HOSTNAME"]:
            names = v["HOSTNAME"] + (f" {v['HOSTNAME']}.{v['NET_DOMAIN']}" if v["NET_DOMAIN"] else "")
            shell(m, f"echo '{v['NET_IP']} {names}' >> /etc/hosts")
    if v["NET_DNS"]:
        write_lines(m, "/etc/resolv.conf", ([f"domain {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else [])
                    + [f"nameserver {s}" for s in v["NET_DNS"].split()])
    shell(m, f"grep -E '^(ifconfig_|defaultrouter|hostname)' /etc/rc.conf; cat /etc/resolv.conf 2>/dev/null; tail -2 /etc/hosts")
    m.snap(f"network: {v['NET_MODE']}")
