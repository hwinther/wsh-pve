"""The first boot of Solaris 10 on sun4u after solaris10-install-sparc64.py, as `lab.py install
sol10-sun4u` runs it: answers the keyboard layout question (F2, the default), logs in as root with the
password the installer set, writes the marker file, optionally adds a user, sets up the default router
and DNS, and shuts down with `init 5` (OpenBIOS powers the machine off).

    lab.py run scenarios/solaris10-firstboot.py --pve 120 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=sol10-sun4u\\ninstalled=...')"
    lab.py run scenarios/solaris10-firstboot.py --out /mnt/sparc/runs/first \
        --var DISK=<a copy of the installed disk> --var ROOT_PASSWORD=lab12345

  ROOT_PASSWORD  root's password, set by the installer (solaris10-install-sparc64.py)  (none)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  USER           a non-root user to add (home /export/home/USER, /bin/sh)           (none)
  USER_PASSWORD  that user's password, set with passwd as root                      (none: locked)
  NET_MODE       static: NET_GATEWAY into /etc/defaultrouter (the installer set the address and
                 netmask)                                                           (none)
  NET_GATEWAY    the default router                                                 (none)
  NET_DNS        name servers, space separated; NET_DOMAIN their domain: /etc/resolv.conf and
                 `hosts: files dns`                                                 (none)
  TIMEOUT        seconds from the start to the login prompt (the first boot imports the SMF
                 manifests: ~14 min)                                                (2400)

The values are typed on the serial console: passwords at prompts that don't echo, the marker with
`echo`, so it must not contain single quotes.
"""
from _sparc64 import DEFAULTS as BASE, GUESTS, login, power_off, qemu_args as sparc64_args, shell

DEFAULTS = {**BASE, "MEM": "1024", "BOOT": "c", "ROOT_PASSWORD": "", "MARKER": "", "USER": "",
            "USER_PASSWORD": "", "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "", "NET_NETWORK": "",
            "NET_GATEWAY": "", "NET_DNS": "", "NET_DOMAIN": "", "HOSTNAME": "", "NET_IF": "",
            "TIMEOUT": "2400"}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return sparc64_args(v, out)


def guest(v):
    """The variables _sparc64.login() and power_off() read: Solaris 10's prompt and keyboard question,
    root with ROOT_PASSWORD."""
    return {**GUESTS["solaris10"], "PASSWORD": v["ROOT_PASSWORD"]}


def run(m, v):
    g = guest(v)
    m.expect(r"SunOS Release 5\.10", 900)
    m.snap("kernel banner")
    login(m, g, int(v["TIMEOUT"]))
    if v["MARKER"]:
        lines = v["MARKER"].splitlines()
        if any("'" in line for line in lines):
            raise ValueError("MARKER must not contain single quotes")
        shell(m, f"rm -f {MARKER_FILE}")
        for line in lines:
            shell(m, f"echo '{line}' >> {MARKER_FILE}")
        out, _ = shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        if lines[0] not in out:
            raise AssertionError(f"{MARKER_FILE} doesn't hold the marker:\n{out}")
        m.snap("marker file")
    if v["USER"]:
        user = v["USER"]
        shell(m, f"mkdir -p /export/home; useradd -d /export/home/{user} -m -s /bin/sh {user}")
        if v["USER_PASSWORD"]:
            m.send(f"passwd {user}\r")
            for _ in range(2):  # "New Password:", "Re-enter new Password:"
                m.expect(r"[Pp]assword:\s*$", 60)
                m.send(v["USER_PASSWORD"] + "\r")
            m.expect(r"#\s*$", 60)
        out, _ = shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /export/home/{user}")
        if f"{user}:" not in out:
            raise AssertionError(f"useradd {user} didn't add the user:\n{out}")
        m.snap(f"user {user}")
    if v["NET_MODE"]:
        network(m, v)
    m.metrics["poweroff_s"] = round(power_off(m, g), 1)


def network(m, v):
    """What the installer didn't set: the default router and DNS (it set the host name, the address
    and the netmask in /etc/hostname.hme0, /etc/inet/hosts and /etc/inet/netmasks)."""
    if v["NET_MODE"] != "static":
        raise ValueError(f"NET_MODE {v['NET_MODE']}: only static is supported on Solaris 10 yet")
    if v["NET_GATEWAY"]:
        shell(m, f"echo {v['NET_GATEWAY']} > /etc/defaultrouter")
    if v["NET_DNS"]:
        shell(m, "rm -f /etc/resolv.conf")
        lines = ([f"domain {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else []) + [f"nameserver {s}" for s in v["NET_DNS"].split()]
        for line in lines:
            shell(m, f"echo '{line}' >> /etc/resolv.conf")
        shell(m, "sed 's/^hosts:.*/hosts:      files dns/' /etc/nsswitch.conf > /tmp/nsswitch.conf"
                 " && cat /tmp/nsswitch.conf > /etc/nsswitch.conf && rm /tmp/nsswitch.conf")
    out, _ = shell(m, "cat /etc/hostname.* /etc/nodename; ls /etc/dhcp.* /etc/defaultrouter /etc/resolv.conf"
                      " 2>/dev/null; cat /etc/inet/hosts; grep -v '^#' /etc/inet/netmasks; grep '^hosts:' /etc/nsswitch.conf")
    if v["HOSTNAME"] and v["HOSTNAME"] not in out:
        raise AssertionError(f"the host name {v['HOSTNAME']} isn't in /etc/nodename:\n{out}")
    m.snap(f"network: {v['NET_MODE']}")
