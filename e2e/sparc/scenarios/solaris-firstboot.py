"""The first boot of a freshly installed Solaris, as `lab.py install` runs it after the install: answers
the first-boot questions with the root password, logs in, writes the marker file, optionally adds a
user, and shuts down with `init 5`.

    lab.py run scenarios/solaris-firstboot.py --pve 120 --out /root/runs/first \
        --var ROOT_PASSWORD=wshlab --var MARKER="$(printf 'target=sol26-ss5\\ninstalled=...')"

  ROOT_PASSWORD  what the first-boot questions set root's password to (sysidroot)   (none)
  MARKER         the lines of /etc/wsh-lab-target, mode 644                         (none: no file)
  USER           a non-root user to add (home /export/home/USER, /bin/sh)           (none)
  USER_PASSWORD  that user's password, set with passwd as root                      (none: locked)
  DATA_DISK      a Sun-labelled disk added after the install (c0t4d0): its device    (none)
                 nodes (drvconfig; disks), newfs of slice 0, mounted on DATA_MOUNT
                 and in /etc/vfstab
  DATA_MOUNT     where the data disk is mounted: /data or /usr/local (what was in     (/data)
                 /usr/local is copied onto the new file system first)
  NET_MODE       static | dhcp: the network beyond the installer's address (network())  (none)
  NET_IP, NET_NETMASK, NET_NETWORK, NET_GATEWAY   static: the address, its netmask and network, the
                 default router (none)
  NET_DNS        name servers, space separated; NET_DOMAIN their domain              (none)

The values are typed on the serial console: passwords at prompts that don't echo, the marker with
`echo`, so it must not contain single quotes.
"""
from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "MARKER": "",
            "USER": "", "USER_PASSWORD": "", "DATA_DISK": "", "DATA_MOUNT": "/data", "NET_MODE": "", "NET_IP": "", "NET_NETMASK": "",
            "NET_NETWORK": "", "NET_GATEWAY": "", "NET_DNS": "", "NET_DOMAIN": ""}
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
    if v["DATA_DISK"]:
        data_disk(m, v["DATA_DISK"], v["DATA_MOUNT"] or "/data")
    if v["NET_MODE"]:
        network(m, v)
    power_off(m, "init 5")


def classful(address):
    """The class A/B/C network number of an address: what Solaris 2.6 looks /etc/netmasks up by."""
    octets = [int(x) for x in address.split(".")]
    keep = 1 if octets[0] < 128 else 2 if octets[0] < 192 else 3
    return ".".join([str(o) for o in octets[:keep]] + ["0"] * (4 - keep))


def network(m, v):
    """The network beyond the installer's static address, in Solaris 2.6's own files (rc scripts
    rootusr, inetinit and inetsvc read them at boot):

    static  /etc/netmasks (the netmask, under the classful network number 2.6 looks up, and the
            subnet's), /etc/defaultrouter (NET_GATEWAY)
    dhcp    /etc/dhcp.le0: rootusr runs `ifconfig le0 auto-dhcp primary`; the host name then comes
            from the server (dhcpinfo Hostname), `unknown` if it sends none; the default router from
            it; inetsvc writes resolv.conf, the hosts: line of nsswitch.conf and the address in
            /etc/hosts. The installer's address leaves /etc/hosts (loghost moves to localhost).
    dns     NET_DNS (+ NET_DOMAIN): /etc/resolv.conf and `hosts: files dns` (with DHCP the server's
            name servers replace them when it sends any)."""
    nic = v.get("NIC") or "le0"
    if v["NET_MODE"] == "dhcp":
        shell(m, f"touch /etc/dhcp.{nic}")
        shell(m, "echo '127.0.0.1\\tlocalhost\\tloghost' > /etc/inet/hosts")
    else:
        nets = [classful(v["NET_IP"])] + ([v["NET_NETWORK"]] if v["NET_NETWORK"] != classful(v["NET_IP"]) else [])
        for net in nets:
            # Solaris 7's installer has a Subnets screen (default yes, 255.255.255.0) and writes the
            # classful entry itself: replace it rather than add a second (the first one wins)
            shell(m, f"sed '/^{net.replace('.', '[.]')}[ \t]/d' /etc/inet/netmasks > /tmp/netmasks"
                     " && cat /tmp/netmasks > /etc/inet/netmasks && rm /tmp/netmasks")
            shell(m, f"echo '{net}\\t{v['NET_NETMASK']}' >> /etc/inet/netmasks")
        if v["NET_GATEWAY"]:
            shell(m, f"echo {v['NET_GATEWAY']} > /etc/defaultrouter")
    if v["NET_DNS"]:
        shell(m, "rm -f /etc/resolv.conf")
        lines = ([f"domain {v['NET_DOMAIN']}"] if v["NET_DOMAIN"] else []) + [f"nameserver {s}" for s in v["NET_DNS"].split()]
        for line in lines:
            shell(m, f"echo '{line}' >> /etc/resolv.conf")
        shell(m, "sed 's/^hosts:.*/hosts:      files dns/' /etc/nsswitch.conf > /tmp/nsswitch.conf"
                 " && cat /tmp/nsswitch.conf > /etc/nsswitch.conf && rm /tmp/nsswitch.conf")
    shell(m, f"ls /etc/dhcp.* /etc/defaultrouter /etc/resolv.conf 2>/dev/null; tail -3 /etc/inet/netmasks;"
             f" cat /etc/inet/hosts; grep '^hosts:' /etc/nsswitch.conf")
    m.snap(f"network: {v['NET_MODE']}")


def data_disk(m, disk, mount="/data"):
    """A disk added after the install, already labelled (sunlabel.data_geometry: slice 0 = the disk):
    the device nodes for the new target, a UFS on slice 0, mounted on `mount` at every boot. A
    mount point that has files already (/usr/local) gets them copied onto the new file system
    first, so mounting over it hides nothing."""
    if mount not in ("/data", "/usr/local"):
        raise ValueError(f"DATA_MOUNT {mount!r}: /data or /usr/local")
    shell(m, "drvconfig; disks", 300)
    shell(m, f"prtvtoc /dev/rdsk/{disk}s2")
    m.send(f"newfs /dev/rdsk/{disk}s0\r")
    m.expect(r"\(y/n\)\?\s*$", 120)
    m.send("y\r")
    m.expect(r"\n#\s*$", 1800)
    shell(m, f"mkdir -p {mount}; ls -lA {mount}")
    shell(m, f"if [ -n \"`ls -A {mount}`\" ]; then mount /dev/dsk/{disk}s0 /mnt && cd {mount} &&"
             f" find . -print | cpio -pdm /mnt; cd /; umount /mnt; fi", 600)
    shell(m, f"echo '/dev/dsk/{disk}s0 /dev/rdsk/{disk}s0 {mount} ufs 2 yes -' >> /etc/vfstab")
    shell(m, f"mount {mount}; df -k {mount}; ls -lA {mount}", 300)
    m.snap(f"data disk on {mount}")
