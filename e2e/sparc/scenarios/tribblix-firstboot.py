"""The first boot of Tribblix on sun4u after tribblix-install-sparc64.py, as `lab.py install
tribblix-m34-sun4u` runs it: logs in as root with the live CD's password (the installer copied it),
sets root's password, locks the live CD's user `jack`, writes the marker file, sets up the network
with ipadm, optionally adds a user, and powers off with `init 5`.

    lab.py run scenarios/tribblix-firstboot.py --pve 9401 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=tribblix-m34-sun4u\\n...')"
    lab.py run scenarios/tribblix-firstboot.py --out /mnt/sparc/runs/first --var DISK=<the installed disk>

  ROOT_PASSWORD  root's new password, typed at passwd's prompts (they don't echo)  (none: stays tribblix)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                     (none: no file)
  USER           a non-root user to add (home /export/home/USER, /bin/sh)       (none)
  USER_PASSWORD  that user's password, set with passwd as root                  (none: locked)
  NET_MODE       static | dhcp: a persistent address on NIC_NAME (ipadm)         (none)
  NET_IP, NET_NETMASK, NET_GATEWAY   static: the address, its netmask, a persistent default route
  NET_DNS        name servers, space separated; NET_DOMAIN their domain: /etc/resolv.conf and
                 `hosts: files dns`                                              (none)
  HOSTNAME       checked against /etc/nodename (live_install.sh -n set it); also into /etc/inet/hosts
  NIC_NAME       the interface                                                  (hme0)
  TIMEOUT        seconds from the start to the login prompt (the first boot imports
                 the SMF manifests: 35-70 minutes under TCG)                     (6600)

The values are typed on the serial console: passwords at prompts that don't echo, the marker with
`echo`, so it must not contain single quotes.
"""
import ipaddress
import re

from _sparc64 import DEFAULTS as BASE, qemu_args as sparc64_args, shell
from _tribblix import BANNER, FAIL, LIVE_ROOT_PASSWORD, login, power_off

DEFAULTS = {**BASE, "MEM": "2048", "BOOT": "c", "NET": "user", "ROOT_PASSWORD": "", "MARKER": "", "USER": "",
            "USER_PASSWORD": "", "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "", "NET_NETWORK": "",
            "NET_GATEWAY": "", "NET_DNS": "", "NET_DOMAIN": "", "HOSTNAME": "", "NET_IF": "", "NIC_NAME": "hme0",
            "TIMEOUT": "6600"}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return sparc64_args(v, out)


def write_lines(m, path, lines):
    """`path` with exactly these lines (echo, one line at a time)."""
    if any("'" in line for line in lines):
        raise ValueError(f"{path}: no single quotes")
    shell(m, f"rm -f {path}")
    for line in lines:
        shell(m, f"echo '{line}' >> {path}")


def passwd(m, user, password):
    """Set a password with passwd as root. illumos's passwd applies /etc/default/passwd's construction
    rules to root too (MINNONALPHA=1 refuses `wshlab`, as on Solaris 10), so the rules are relaxed
    for this one call and the file put back as it was."""
    shell(m, "cp -p /etc/default/passwd /tmp/passwd.default && grep -v '^#*MINNONALPHA=' /tmp/passwd.default"
             " > /etc/default/passwd && echo MINNONALPHA=0 >> /etc/default/passwd")
    try:
        m.send(f"passwd {user}\r")
        for _ in range(2):  # "New Password:", "Re-enter new Password:"
            m.expect(r"[Pp]assword:\s*$", 60)
            m.send(password + "\r")
        if m.expect_any([r"[#$]\s*$", r"[Tt]ry again|[Pp]assword:\s*$"], 60) == 1:
            m.key("ctrl-c")
            raise AssertionError(f"passwd {user} refused the password")
    finally:
        shell(m, "cp -p /tmp/passwd.default /etc/default/passwd && rm /tmp/passwd.default")


def run(m, v):
    if m.expect_any([BANNER, FAIL], 900) == 1:
        m.snap("failure")
        raise AssertionError("the disk didn't boot (firmware or ZFS boot block)")
    m.snap("kernel banner")
    login(m, LIVE_ROOT_PASSWORD, int(v["TIMEOUT"]))
    m.metrics["login_s"] = round(m.elapsed(), 1)
    if v["ROOT_PASSWORD"]:
        passwd(m, "root", v["ROOT_PASSWORD"])
        m.snap("root password set")
    # A ZFS root (ROOT_FS=zfs) comes up DEGRADED: FMA counted the I/Os that ZFS had to retry during
    # the install (submodules/SPARC.md, "Tribblix on sun4u"); there were no data errors
    shell(m, "if zpool list rpool >/dev/null 2>&1; then zpool clear rpool; zpool status -x; fi", 300)
    # the live CD's own user, jack/jack, came along with its /etc: locked
    out, _ = shell(m, "if grep '^jack:' /etc/passwd >/dev/null; then passwd -l jack; passwd -s jack; fi")
    if re.search(r"^jack\s+(?!LK)\S+", out, re.M):
        raise AssertionError(f"jack isn't locked:\n{out}")
    if v["MARKER"]:
        lines = v["MARKER"].splitlines()
        write_lines(m, MARKER_FILE, lines)
        out, _ = shell(m, f"chmod 644 {MARKER_FILE}; cat {MARKER_FILE}")
        if lines[0] not in out:
            raise AssertionError(f"{MARKER_FILE} doesn't hold the marker:\n{out}")
        m.snap("marker file")
    if v["USER"]:
        user = v["USER"]
        shell(m, f"mkdir -p /export/home; useradd -d /export/home/{user} -m -s /bin/sh {user}")
        if v["USER_PASSWORD"]:
            passwd(m, user, v["USER_PASSWORD"])
        out, _ = shell(m, f"grep '^{user}:' /etc/passwd; ls -ld /export/home/{user}")
        if f"{user}:" not in out:
            raise AssertionError(f"useradd {user} didn't add the user:\n{out}")
        m.snap(f"user {user}")
    if v["NET_MODE"]:
        network(m, v)
    m.metrics["poweroff_s"] = round(power_off(m), 1)


def network(m, v):
    """A persistent address on the NIC (ipadm keeps it in /etc/ipadm/ipadm.conf), the default route
    (route -p), DNS (/etc/resolv.conf, nsswitch from /etc/nsswitch.dns) and the host name in
    /etc/inet/hosts."""
    nic = v["NIC_NAME"] or "hme0"
    # The installed system comes up with NWAM (network/physical:nwam), which takes every NIC by DHCP
    # (`hme0/_b dhcp`) and owns the interfaces: switch to network/physical:default and a fixed
    # configuration first. Under TCG nwam's stop method can time out and leave it in maintenance
    # (svcadm disable -s would then wait for ever): poll, and clear it into disabled
    shell(m, "svcadm disable network/physical:nwam; svcadm enable network/physical:default; i=0;"
             " while [ $i -lt 90 ]; do case $(svcs -H -o state network/physical:nwam) in disabled) break ;;"
             " maintenance) svcadm clear network/physical:nwam ;; esac; sleep 10; i=$((i+1)); done;"
             " svcs network/physical", 1200)
    shell(m, f"ipadm delete-if {nic} 2>/dev/null; ipadm create-if {nic}", 300)
    if v["NET_MODE"] == "dhcp":
        shell(m, f"ipadm create-addr -T dhcp -w 60 {nic}/v4", 120)
    elif v["NET_MODE"] == "static":
        prefix = ipaddress.ip_network(f"0.0.0.0/{v['NET_NETMASK'] or '255.255.255.0'}").prefixlen
        shell(m, f"ipadm create-addr -T static -a local={v['NET_IP']}/{prefix} {nic}/v4")
        if v["HOSTNAME"]:
            shell(m, f"echo '{v['NET_IP']} {v['HOSTNAME']}' >> /etc/inet/hosts")
        if v["NET_GATEWAY"]:
            # route -p for now and /etc/inet/static_routes; /etc/defaultrouter as well: in one lab
            # boot the default route didn't come back from static_routes alone (routing services
            # time out under TCG)
            shell(m, f"route -p add default {v['NET_GATEWAY']}; echo {v['NET_GATEWAY']} > /etc/defaultrouter")
    else:
        raise ValueError(f"NET_MODE {v['NET_MODE']}: static or dhcp")
    if v["NET_DNS"]:
        lines = ([f"domain {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else []) + [f"nameserver {s}" for s in v["NET_DNS"].split()]
        write_lines(m, "/etc/resolv.conf", lines)
        shell(m, "cp /etc/nsswitch.dns /etc/nsswitch.conf")
    out, _ = shell(m, f"cat /etc/nodename; ipadm show-addr {nic}/v4; netstat -rn -f inet; cat /etc/resolv.conf"
                      " 2>/dev/null; grep '^hosts:' /etc/nsswitch.conf", 120)
    if v["HOSTNAME"] and v["HOSTNAME"] not in out:
        raise AssertionError(f"the host name {v['HOSTNAME']} isn't in /etc/nodename:\n{out}")
    if v["NET_MODE"] == "static" and v["NET_IP"] not in out:
        raise AssertionError(f"{nic} doesn't have {v['NET_IP']}:\n{out}")
    m.snap(f"network: {v['NET_MODE']}")
