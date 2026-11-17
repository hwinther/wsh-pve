"""The first boot of a freshly installed SunOS 4.1.4 (sunos-install-serial.py), as `lab.py install`
runs it: answers sys-config (manual setup, host name, time zone GMT, the static address, no NIS, the
root password, the optional user), logs in, writes the marker file and the network files, and powers
off with `halt`.

    lab.py run scenarios/sunos-firstboot.py --pve 400 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var HOSTNAME=sunos414 --var NET_IP=10.0.2.15 --var MARKER=target=x

  HOSTNAME       the host name sys-config sets                                      (sunos414)
  ROOT_PASSWORD  root's password, set by sys-config (1-8 characters)                (required)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  USER           a user added by sys-config (uid 1001, group staff, csh, home        (none)
                 /home/<host>/<user>)
  USER_PASSWORD  that user's password                                                (none)
  NET_IP         the static address sys-config gives le0; empty: not networked      (none)
  NET_NETMASK, NET_NETWORK, NET_GATEWAY   its netmask and network (/etc/netmasks), the default
                 router (/etc/defaultrouter); 4.1.4's rc.boot and rc.local read both
"""
from _sparc32 import DEFAULTS as BASE, power_off, prom_boot, qemu_args as sparc32_args
from _sunos4 import login, shell, sysconfig

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "HOSTNAME": "sunos414", "ROOT_PASSWORD": "",
            "MARKER": "", "USER": "", "USER_PASSWORD": "", "NET_IP": "", "NET_NETMASK": "", "NET_NETWORK": "",
            "NET_GATEWAY": ""}
MARKER_FILE = "/etc/wsh-lab-target"


def qemu_args(v, out):
    return sparc32_args(v, out)


def classful(address):
    """The class A/B/C network number of an address: what `ifconfig netmask +` looks up."""
    octets = [int(x) for x in address.split(".")]
    keep = 1 if octets[0] < 128 else 2 if octets[0] < 192 else 3
    return ".".join([str(o) for o in octets[:keep]] + ["0"] * (4 - keep))


def network(m, v):
    """/etc/netmasks (the netmask under the classful network number and the subnet's) and
    /etc/defaultrouter. SunOS's echo has no escapes: fields are separated by a space."""
    nets = [classful(v["NET_IP"])]
    if v["NET_NETWORK"] and v["NET_NETWORK"] != nets[0]:
        nets.append(v["NET_NETWORK"])
    for net in nets:
        shell(m, f"sed '/^{net.replace('.', '[.]')}[ \t]/d' /etc/netmasks > /tmp/netmasks"
                 " && cat /tmp/netmasks > /etc/netmasks && rm /tmp/netmasks")
        shell(m, f"echo '{net} {v['NET_NETMASK']}' >> /etc/netmasks")
    if v["NET_GATEWAY"]:
        shell(m, f"echo {v['NET_GATEWAY']} > /etc/defaultrouter")
    shell(m, "grep -v '^#' /etc/netmasks; cat /etc/defaultrouter 2>/dev/null; cat /etc/hostname.le0; grep -v '^#' /etc/hosts")
    m.snap("network files")


def run(m, v):
    if not v["ROOT_PASSWORD"]:
        raise ValueError("ROOT_PASSWORD: sys-config sets it")
    prom_boot(m, v, "disk")
    m.expect(r"SunOS Release 4\.1", 600)
    m.snap("kernel banner")
    answered = sysconfig(m, v)
    m.log(f"sys-config: {', '.join(answered)}")
    login(m, v["ROOT_PASSWORD"])
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
        shell(m, f"grep '^{v['USER']}:' /etc/passwd; ls -ld /home/{v['HOSTNAME']}/{v['USER']}")
        m.snap(f"user {v['USER']}")
    if v["NET_IP"] and v["NET_NETMASK"]:
        network(m, v)
    power_off(m, "halt")
