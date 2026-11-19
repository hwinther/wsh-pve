"""The install targets `lab.py install` knows: a tested VM profile, the install media it needs, how the
install is driven, and the login it ends with. Data only (install.py does the work); reviewed like code.

These are lab VMs with publicly documented passwords (DEFAULT_ROOT_PASSWORD, in this public
repository): never reuse a real secret here or with --root-password, and don't expose the VMs to an
untrusted network without changing the password.

MEDIA: the tested media by expected file name, the name they must have on the node's storage
(`<storage>:iso/<name>` or `<storage>:floppy/<name>`). The names are the ones the media have on
the lab host and in the docs (`lab` is the path under the lab host's media directory, for the `pve`
matrix, which links them into the test node's storage). size and sha256 are of the medium that was
tested; `lab.py install` refuses a medium with another checksum unless --allow-untested-media. No medium
is in the repository or downloaded by the tests. A medium with `from` is made by the user from another
medium in MEDIA (`convert`: "bin2352" = the 2048 data bytes of each 2352-byte raw CD sector) with
`lab.py media <target> --convert <source>`, which checks the source's and the result's sha256.

TARGETS: per target
  title      what it is
  status     "automated" (`lab.py install` does it, tested as `tested` says) or "catalogue" (listed
             with what it needs; `blocked` says why it isn't automated yet)
  profile    the VM: options for `pvesh create /nodes/<node>/qemu` that must fit qemu-server's
             profiles (submodules/SPARC.md, "Supported profiles"; tests/test_targets.py checks them
             against $SPARC32_PROFILES / $SPARC64_PROFILE in submodules/qemu-server.patch). net0 is the
             model; install adds the bridge.
  disk       bus (the profile's first disk), size in GiB, label: "sun" = a Sun (SMI) label with the
             geometry in `geometry` (the Solaris installers list only labelled disks), None = blank.
             A Sun-labelled disk made by sun_disk() also has `sizes`: the DISKS (by name) this target
             was tested with, the first the default (`lab.py install --disk-size` takes only these)
  media      [{name, drive, ...}]: the media in MEDIA, each with the drive it goes into at the start
             (`at: "start"`, default) or, for multi-volume installs, `at: <regex>`: inserted into
             `drive` when the installer's console shows that prompt (install.MediaSwapper), or `at: "scenario"`:
             handed to the install scenario in order (SWAPS) for prompts that name no disk.
             `as_disk: True`: the CD answers as a read-only disk (qemu-server's sparc32-only
             cd_as_disk=1, for the Solaris 2.4/2.5.1 installers); at the start only
  method     "scripted": the installer is answered on the console by `install` (a scenario, with
             `vars`), then `firstboot` (a scenario) sets the root password, writes the marker file
             /etc/wsh-lab-target and optionally adds a user, and powers off; `check` (a scenario,
             with --check) logs in and runs its "commands" (default: Solaris's). "unattended": the
             installer reads its own answer file from a CD made on the node (answer_media.py) that
             is in install "answers" `drive` for the install phase only (`format`: "kickstart",
             "preseed"); the install scenario answers what that leaves on the screen, first boot
             and check as "scripted" (Red Hat 6.2, Debian 4.0). DOS targets: targets_dos.py.
             install may have `memory` (MB for the install phase only; the profile's afterwards) and
             `prom_env` (OpenBIOS variables for the install phase only); check may have `commands`
             (what the check boot runs and records; default: Solaris's)
  boot       the boot order after the install (the media are ejected first)
  login      user and console of the finished VM; the password is DEFAULT_ROOT_PASSWORD unless
             --root-password says otherwise
  hostname   set by the installer
  network    how the guest's network is set up (the VM's notes say what one install got)
  nic        the guest's interface name in the notes and the marker (le0 unless given)
  dhcp_note  what the guest takes from a DHCP server, for the notes (Solaris 2.6's unless given)
  net_modes  the --ip modes tested for an automated target: "static" (an address, with --netmask,
             --gateway, --dns, --domain) and/or "dhcp"; `lab.py install` refuses the others.
             ["none"]: the guest configures no network (DOS); only --bridge/--vlan apply
  net_refuse {option: why}: network options (dns, domain, gateway, netmask) the guest can't use
  net_require  options a static address needs (["gateway", "dns"]: the installer fetches packages)
  apt_proxy  True: the installer fetches packages and takes --apt-proxy / WSH_LAB_APT_PROXY
  minutes    how long `lab.py install` took on the lab host (TCG, one guest at a time)
  tested     date and packages of the last run that passed
  matrix_skip  why `pve_matrix.py install` doesn't install an automated target by itself (too slow for
             the sparc lab job, or it needs more than the published packages give): only when
             --reinstall names it; once its stored disk exists (install-<target>.raw) the matrix
             boot-tests that. `lab.py install` still runs it
"""

import re

DEFAULT_ROOT_PASSWORD = "wshlab"  # public on purpose: these are throwaway lab VMs

# MEDIA "from" conversions (install.convert_medium): name -> (input sector size, offset, output size)
CONVERSIONS = {"bin2352": (2352, 16, 2048)}  # raw CD sectors (Mode 1): sync + header, 2048 data, EDC/ECC

# The packages of the last test run (the PVE test node with the published packages).
PACKAGES_2026_11_16 = {"pve-qemu-kvm": "11.1.3-2+wsh10", "qemu-server": "9.2.15+wsh6",
                       "pve-manager": "9.2.28+wsh4"}
PACKAGES_2026_11_17 = {**PACKAGES_2026_11_16, "pve-qemu-kvm": "11.1.3-2+wsh13"}
PACKAGES_2026_11_17_WSH15 = {**PACKAGES_2026_11_16, "pve-qemu-kvm": "11.1.3-2+wsh15"}
# qemu-server with cd_as_disk (9.2.18 built from the branch that added it; no published package yet)
PACKAGES_2026_11_18_CD_AS_DISK = {"pve-qemu-kvm": "11.1.3-2+wsh16", "qemu-server": "9.2.18 + cd_as_disk",
                                  "pve-manager": "9.2.30+wsh1"}
PACKAGES_2026_11_18 = {"pve-qemu-kvm": "11.1.3-2+wsh16", "qemu-server": "9.2.18+wsh3", "pve-manager": "9.2.30+wsh2"}
PACKAGES_2026_11_19 = {"pve-qemu-kvm": "11.1.3-2+wsh21", "qemu-server": "9.2.19+wsh1", "pve-manager": "9.2.31+wsh1"}
# qemu-system-sparc64 built from pve-qemu wsh/0001-0037 and openbios-sparc64 from openbios 0001-0017 (both
# in pve-qemu-kvm 11.1.3-2+wsh20 and later), in the PVE test container with the packages of that day
PACKAGES_2026_11_18_SUN4U = {"pve-qemu-kvm": "11.1.3-2+wsh16 + wsh/0034-0037 + openbios 0016-0017",
                             "qemu-server": "9.2.18+wsh1", "pve-manager": "9.2.30+wsh1"}
# Debian 4.0's Linux 2.6.18 esp driver: pve-qemu-kvm 11.1.3-2+wsh17 with the ESP fix (wsh/0038,
# esp_cdb_ready() counting the message bytes) built in; no published package has it yet
PACKAGES_ESP_FIX = {"pve-qemu-kvm": "11.1.3-2+wsh17, qemu-system-sparc a local build with wsh/0038",
                    "qemu-server": "9.2.18+wsh4", "pve-manager": "9.2.30+wsh3"}
ESP_FIX_NOTE = ("needs pve-qemu-kvm with wsh/0038 (QEMU's ESP took the first CDB byte after a multi-byte message"
                " out as a whole command: Linux 2.6.18 offlined the disk and CD), in no published package yet")

MEDIA = {
    "solaris_2.6_598_sparc.iso": {
        "title": "Solaris 2.6 5/98 SPARC, Software CD", "content": "iso", "size": 565862400,
        "sha256": "17351669cb91a89562ed6bb23345879c4d18bd019a85085ad53f777e7b7a6b14",
        "lab": "solaris_2.6_598_sparc.iso"},
    "solaris_2.4_sparc.iso": {
        "title": "Solaris 2.4 Hardware 3/95 SPARC, Software CD", "content": "iso", "size": 455819264,
        "sha256": "c23fe150a9963e5dacbfc988fa700c5f2c7506d36ad0b40910e77444709d1fa4",
        "lab": "solaris_2.4_sparc.iso"},
    "solaris_2.5.1_1197.iso": {
        "title": "Solaris 2.5.1 11/97 SPARC, Software CD", "content": "iso", "size": 452157440,
        "sha256": "18da51043271d0aa69d6fc098b84156673ef4f0728dace4a9e679f79d70d2422",
        "lab": "solaris_2.5.1_1197.iso"},
    "Sol7.399InstallationSparc.iso": {
        "title": "Solaris 7 3/99 SPARC, Installation CD", "content": "iso", "size": 588800000,
        "sha256": "3fe59c14307b924d40033f0f3a362c4384b4738a5a365a2f319d96883610c35d",
        "lab": "Sol7.399InstallationSparc.iso"},
    "sun-solaris-8-0101-installation-sparc.iso": {
        "title": "Solaris 8 1/01 SPARC, Installation CD", "content": "iso", "size": 584232960,
        "sha256": "d01915baa0503ad21fd9b99e0684e1231200ca3295e84f60a1bf310a956d51d4",
        "lab": "sun-solaris-8-0101-installation-sparc.iso"},
    "sun-solaris-8-0101-software-cd1-sparc.iso": {
        "title": "Solaris 8 1/01 SPARC, Software CD 1 of 2", "content": "iso", "size": 578023424,
        "sha256": "d50e437d82c96a906833fca182f813035d766b1645491eb06b221826ef9f39c8",
        "lab": "sun-solaris-8-0101-software-cd1-sparc.iso"},
    "sun-solaris-8-0101-software-cd2-sparc.iso": {
        "title": "Solaris 8 1/01 SPARC, Software CD 2 of 2", "content": "iso", "size": 214757376,
        "sha256": "1b6fafd007673f924dc40103b3d2c565342b287d6ff8ad53ac07e1b4b73b44d4",
        "lab": "sun-solaris-8-0101-software-cd2-sparc.iso"},
    "SOL_9_SPARC_DVD.iso": {
        "title": "Solaris 9 SPARC, DVD", "content": "iso", "size": 3368878080,
        "sha256": "feb49d1fa21227a1493b5b4a083b2ca12e60577ccd84e4a22b5d3b86fd209911",
        "lab": "SOL_9_SPARC_DVD.iso"},
    "sol-10-u11-ga-sparc-dvd.iso": {
        "title": "Solaris 10 1/13 (u11) SPARC, DVD", "content": "iso", "size": 2314731520,
        "sha256": "b1df86b976282145fd317d9def4efc27d7d64589f5542184a3e781c0787cf02b",
        "lab": "sol-10-u11-ga-sparc-dvd.iso"},
    "sunos_4.1.4_install.iso": {
        "title": "SunOS 4.1.4 (Solaris 1.1.2) install CD, raw BIN (2352-byte sectors)", "content": "iso",
        "size": 378178080, "sha256": "6088d836cf582128cdd69661c4b62399fbd6f4db9b817188b2d1509cebbb5f48",
        "lab": "sunos_4.1.4_install.iso"},
    # The same CD as a plain image: the 2048 data bytes of each 2352-byte Mode 1 sector of the BIN above
    # (`lab.py media sunos414-ss5 --convert <the BIN>` writes it; install.convert_medium).
    "sunos414-cd.iso": {
        "title": "SunOS 4.1.4 install CD, 2048-byte sectors (from sunos_4.1.4_install.iso)", "content": "iso",
        "size": 329297920, "sha256": "7b9b092a63bf5dde9f09eea25614c6da58e5c065758a8c24b96be1574bcaa0c8",
        "lab": "sunos414-cd.iso", "from": {"name": "sunos_4.1.4_install.iso", "convert": "bin2352"}},
    "NetBSD-11.1-sparc64.iso": {
        "title": "NetBSD 11.1 sparc64 install CD (cdn.netbsd.org)", "content": "iso", "size": 694026240,
        "sha256": "a782b26be57325c8419fdb02030ea4e686a6ccf097baad2dae0a1a0c39e96f4e",
        "lab": "other-os/NetBSD-11.1-sparc64.iso",
        # freely redistributable: tests/test_netbsd.py downloads it in CI (its SHA512 matches the
        # release's images/SHA512)
        "url": "https://cdn.netbsd.org/pub/NetBSD/NetBSD-11.1/images/NetBSD-11.1-sparc64.iso"},
    "NetBSD-11.1-sparc.iso": {
        "title": "NetBSD 11.1 sparc install CD (cdn.netbsd.org)", "content": "iso", "size": 367329280,
        "sha256": "4a8985ecf7d21dad66c34c184d1535a9f901ee4ccc4d962c37558545b63b4636",
        "lab": "other-os/NetBSD-11.1-sparc.iso",
        "url": "https://cdn.netbsd.org/pub/NetBSD/NetBSD-11.1/images/NetBSD-11.1-sparc.iso"},
    "redhat-6.2-sparc.iso": {
        "title": "Red Hat Linux 6.2 for SPARC, install CD", "content": "iso", "size": 623771648,
        "sha256": "74bdc6de56d3120f05372232cd4dae313d015e62be4b359672d9f8edca300987",
        "lab": "other-os/redhat-6.2-sparc.iso"},
    # The owner's own collection of SVR4 packages for Solaris 2.6 (GNU and other free tools, all with
    # BASEDIR /usr/local) on a CD image of his: a local-only medium for `lab.py install --post-install
    # sun26gnu` (POST_INSTALL). No URL, never in CI or a published recording; only its gnu/pkgs
    # directory is used (the image also has Sun patches and third-party apps, left alone).
    "sun26gnu.iso": {
        "title": "Solaris 2.6 GNU package collection (the owner's local CD image)", "content": "iso",
        "size": 287309824, "sha256": "7630cbd8866bdf644c931c599b64b467ed88b58836073d84ca13a16d5b80c366",
        "lab": "sun26gnu.iso", "local_only": True},
    "debian-40r9-sparc-netinst.iso": {
        "title": "Debian GNU/Linux 4.0r9 (etch) sparc netinst CD", "content": "iso", "size": 146124800,
        "sha256": "91aeb8639d53252215c99b69fa07ef1ae0e2bafec1c3c77fdfb9094327dd3afd",
        "lab": "other-os/debian-40r9-sparc-netinst.iso",
        "url": "https://cdimage.debian.org/mirror/cdimage/archive/4.0_r9/sparc/iso-cd/debian-40r9-sparc-netinst.iso"},
    "tribblix-sparc-0m34.iso": {
        "title": "Tribblix m34 SPARC live/install CD (iso.tribblix.org)", "content": "iso", "size": 710717440,
        "sha256": "afc1b115633c5a3c63bb683c0608fd22c41568eb5909f09556e045caa04aa323",
        "lab": "other-os/tribblix-sparc-0m34.iso",
        # open source (illumos, CDDL); the download page publishes its SHA-1 (f76238cf...5ca9)
        "url": "https://iso.tribblix.org/iso/tribblix-sparc-0m34.iso"},
}

# `lab.py install --post-install <bundle>`: SVR4 packages from a CD added to an installed Solaris
# target after its first boot (install.PostInstall, scenarios/solaris-post-install.py): the CD is in
# `drive` for that phase only, every datastream in `dir` goes through `pkgadd -n -a <admin file>`
# onto `basedir`, which must be the data disk (--data-disk, mounted there; /usr has ~70 MB free on
# the 3G and 9G layouts). `targets`: where it was tested; `shell`: what --local-env makes the user's
# login shell; `check`: (command, regex) pairs the --check boot runs and expects.
POST_INSTALL = {
    "sun26gnu": {
        "title": "GNU and other free tools for Solaris 2.6 (bash, coreutils, vim, wget, ...) under /usr/local",
        "medium": "sun26gnu.iso", "drive": "scsi5", "dir": "gnu/pkgs", "basedir": "/usr/local",
        "min_data_disk": 1, "timeout": 5400, "shell": "/usr/local/bin/bash",
        "targets": ["sol26-ss5", "sol26-ss20", "sol7-ss5", "sol7-ss20"],  # 2026-11-18, with --check
        "check": [("/usr/local/bin/bash --version | head -1", r"GNU bash, version \d"),
                  ("/usr/local/bin/vim --version | head -1", r"VIM - Vi IMproved \d"),
                  ("/usr/local/bin/wget --version | head -1", r"GNU Wget \d")],
    },
}

# The geometry of the lab's SUN2.9G disk template (sparc-SUN2.9G.raw.template.xz, the sparc guide's
# "Disks"): `sunlabel.label(**SUN29G)` writes the same label sector. Slices as the template has them;
# the installer's auto-layout replaces them.
SUN29G = {"name": "SUN2.9G", "ncyl": 2734, "acyl": 2, "pcyl": 3500, "heads": 21, "sectors": 99, "rpm": 5400,
          "parts": [(2, 0, 0, 195426), (3, 1, 94, 390852), (5, 1, 0, 5683986), (0, 0, 0, 0), (0, 0, 0, 0),
                    (0, 0, 0, 0), (4, 0, 282, 5097708), (0, 0, 0, 0)]}  # (tag, flag, start cyl, blocks)

# The lab's ~9 GB template (sparc-Qemu9G.raw.template.xz, an 8 GiB image; the owner set its
# geometry up with a sector calculator): `sunlabel.label(**QEMU8G)` writes the same label sector.
# 16202 data + 2 alternate cylinders of 16 heads x 60 sectors = 15556800 sectors (7.42 GiB); pcyl in
# the label is 16204 (the sparc guide's "custom type" lists 16200/2/16202, two fewer: the template
# is what was tested). Slices as the template has them; the installer's auto-layout replaces them.
QEMU8G = {"name": "QEmu8G", "ncyl": 16202, "acyl": 2, "pcyl": 16204, "heads": 16, "sectors": 60, "rpm": 3600,
          "parts": [(2, 0, 0, 263040), (3, 1, 274, 263040), (5, 1, 0, 15553920), (0, 0, 0, 0), (0, 0, 0, 0),
                    (0, 0, 0, 0), (4, 0, 548, 15027840), (0, 0, 0, 0)]}

# The disk sizes `lab.py install --disk-size` offers, by the names of the templates they come from:
# the image size (GiB), the label sunlabel.write_disk() writes (the template's, byte for byte,
# including the backup labels in the last track) and the template it matches.
DISKS = {
    "3G": {"size": 3, "geometry": SUN29G, "template": "sparc-SUN2.9G.raw.template.xz"},
    "9G": {"size": 8, "geometry": QEMU8G, "template": "sparc-Qemu9G.raw.template.xz"},
}

# SUN2.9G with slice g cut to 1000 cylinders (1015 MiB): SunOS 4 file systems stop at 2 GB, and
# suninstall's Quick install with "preserve the data partitions" newfs's a and g as the label has them
# (a: / 95 MB, b: swap 190 MB, g: /usr). The rest of the disk is left unused.
SUN29G_SUNOS4 = {**SUN29G, "parts": SUN29G["parts"][:6] + [(4, 0, 282, 1000 * 21 * 99)] + SUN29G["parts"][7:]}


def sun_disk(*sizes, bus="scsi3"):
    """A Sun-labelled first disk tested with these DISKS (the first is the default)."""
    return {"bus": bus, "label": "sun", "size": DISKS[sizes[0]]["size"], "geometry": DISKS[sizes[0]]["geometry"],
            "sizes": list(sizes)}


SPARC32 = {"arch": "sparc", "bios": "openbios-sparc32", "ostype": "solaris", "net0": "lance",
           "serial0": "socket", "vga": "serial0"}  # the text installer runs on ttya (no framebuffer)

SOLARIS_SCRIPTED = {
    "method": "scripted",
    # solaris-install-serial.py's defaults: End User System Support, auto-layout, Networked with a
    # static address, no name service, time zone MET, manual reboot (it halts at the end)
    "install": {"scenario": "solaris-install-serial.py", "vars": {}, "timeout": 3600},
    "firstboot": {"scenario": "solaris-firstboot.py", "vars": {}, "timeout": 1800},
    "check": {"scenario": "solaris-boot-disk.py", "vars": {}, "timeout": 1200},
    "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
    # The installer sets the static address (it has no DHCP choice); the first boot writes /etc/netmasks,
    # /etc/defaultrouter, /etc/resolv.conf and nsswitch.conf, or /etc/dhcp.le0 (solaris-firstboot.py)
    "network": "le0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain) or DHCP",
    "net_modes": ["static", "dhcp"],
}

NETBSD_SCRIPTED = {
    "method": "scripted",
    # the install scenario per target (netbsd-install-sparc64.py, netbsd-install-sparc.py); the first
    # boot sets root's password, the marker, /etc/myname and the network, then `halt -p`
    "firstboot": {"scenario": "netbsd-firstboot.py", "vars": {}, "timeout": 1200},
    "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
    "network": "le0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain) or DHCP",
    "net_modes": ["static", "dhcp"],
    # dhcpcd sends no host name by default and keeps /etc/myname
    "dhcp_note": "router and name servers from the DHCP server; the host name stays as installed (/etc/myname)",
}


# Red Hat Linux 6.2: anaconda reads a kickstart file from the answer CD (`answers`: made on the node,
# answer_media.py, in that drive for the install phase only); the first boot sets root's password,
# the marker, the router and DNS, the optional user (redhat-firstboot.py)
REDHAT_UNATTENDED = {
    "method": "unattended",
    "install": {"scenario": "redhat-install-sparc.py", "vars": {}, "timeout": 3600,
                "answers": {"format": "kickstart", "drive": "scsi5"}},
    "firstboot": {"scenario": "redhat-firstboot.py", "vars": {}, "timeout": 1200},
    "check": {"scenario": "redhat-boot-disk.py", "vars": {}, "timeout": 900,
              "commands": "uname -a; hostname; cat /etc/wsh-lab-target; df -k; /sbin/fdisk -l /dev/sda;"
                          " /sbin/ifconfig -a; /sbin/route -n; cat /etc/resolv.conf 2>/dev/null"},
    "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
    "nic": "eth0",
    # the kickstart file sets the address and netmask (ifcfg-eth0); the first boot the host name
    # (/etc/sysconfig/network, /etc/hosts), GATEWAY= and /etc/resolv.conf
    "network": "eth0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain)",
    "net_modes": ["static"],
}


# Debian 4.0 (etch): debian-installer reads a preseed file from the answer CD (`answers`: made on the
# node, answer_media.py, in that drive for the install phase only) and fetches the base system from
# archive.debian.org (or through --apt-proxy); the first boot sets root's password, the marker and
# the optional user (debian-firstboot.py)
DEBIAN_UNATTENDED = {
    "method": "unattended",
    "install": {"scenario": "debian-install-sparc.py", "vars": {}, "timeout": 5400,
                "answers": {"format": "preseed", "drive": "scsi5"}},
    "firstboot": {"scenario": "debian-firstboot.py", "vars": {}, "timeout": 1200},
    "check": {"scenario": "debian-boot-disk.py", "vars": {}, "timeout": 900,
              "commands": "uname -a; hostname; cat /etc/wsh-lab-target; cat /etc/debian_version; df -k;"
                          " /sbin/fdisk -l /dev/sda; /sbin/ifconfig -a; /sbin/route -n; cat /etc/resolv.conf;"
                          " grep -v '^#' /etc/apt/sources.list; netstat -ltn"},
    "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
    "nic": "eth0",
    # the preseed file sets all of it (/etc/network/interfaces, /etc/resolv.conf, /etc/hostname)
    "network": "eth0: a static address (10.0.2.15/24 unless --ip/--netmask) with --gateway and --dns,"
               " which must reach archive.debian.org (or --apt-proxy); --domain",
    "net_modes": ["static"],
    "net_require": ["gateway", "dns"],
    "apt_proxy": True,
}


def netbsd_check(disk):
    """The check boot of a NetBSD target: netbsd-boot-disk.py with NetBSD's commands (`disk`: the
    first disk's name in the guest)."""
    return {"scenario": "netbsd-boot-disk.py", "vars": {}, "timeout": 1200,
            "commands": f"uname -a; hostname; cat /etc/wsh-lab-target; df -k; disklabel {disk} | sed -n '/partitions:/,$p';"
                        " ifconfig -a; netstat -rn -f inet; cat /etc/resolv.conf 2>/dev/null"}


TARGETS = {
    "sol26-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.6 5/98 End User on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("3G", "9G"),  # 9G: tested 2026-11-17 (README.md, "Disk sizes")
        "media": [{"name": "solaris_2.6_598_sparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol26-ss5",
        "minutes": 12,  # install 7, first boot 3, --check 2
        "tested": {"date": "2026-11-16", "packages": PACKAGES_2026_11_16, "with": "--check"},
    },
    # An SS-5 install doesn't boot on SS-10/SS-20 (SPARC.md, "SS-10 and SS-20"): its own install.
    "sol26-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.6 5/98 End User on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("3G", "9G"),
        "media": [{"name": "solaris_2.6_598_sparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol26-ss20",
        "minutes": 12,  # install 7, first boot 3, --check 2
        "tested": {"date": "2026-11-16", "packages": PACKAGES_2026_11_16, "with": "--check --user lab --template"},
    },
    # Its installer boots only from a CD that answers as a disk (scsi-hd): the CD-ROM gets qemu-server's
    # sparc32-only cd_as_disk=1 ("as_disk"). 2.5.1 boots under the Sun PROM (ss5.bin); its install
    # copies the packages, then the Maintenance Update.
    "sol251-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.5.1 11/97 End User on a SPARCstation 5 (ss5.bin)",
        "status": "automated",
        # the Maintenance Update keeps the installer busy for most of an hour
        "install": {**SOLARIS_SCRIPTED["install"], "vars": {"FINISH_TIMEOUT": "6000"}, "timeout": 7200},
        "profile": {**SPARC32, "machine": "SS-5", "bios": "ss5.bin", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris_2.5.1_1197.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol251-ss5",
        "net_modes": ["static"],  # 2.5.1 has no DHCP client (dhcpagent came with 2.6)
        "minutes": 44,  # install 39 (most of it the Maintenance Update), first boot 3, --check 1.6
        "tested": {"date": "2026-11-18", "packages": PACKAGES_2026_11_18_CD_AS_DISK, "with": "--check"},
    },
    # Solaris 2.4 boots only under the Sun PROM ("Unhandled Exception 0x00000009" under OpenBIOS) and,
    # like 2.5.1, only from a CD that answers as a disk
    "sol24-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.4 HW 3/95 End User on a SPARCstation 5 (ss5.bin)",
        "status": "automated",
        "install": {**SOLARIS_SCRIPTED["install"], "timeout": 7200},
        "profile": {**SPARC32, "machine": "SS-5", "bios": "ss5.bin", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris_2.4_sparc.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol24-ss5",
        "net_modes": ["static"],  # no DHCP client before 2.6
        "minutes": 10,  # install 5, first boot 2.4, --check 1.4
        "tested": {"date": "2026-11-18", "packages": PACKAGES_2026_11_18_CD_AS_DISK, "with": "--check"},
    },
    # Solaris 7 asks 2.6's questions plus Subnets (default yes) and Select 64 Bit (default no):
    # solaris-install-serial.py unchanged
    "sol7-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 7 3/99 End User on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("3G", "9G"),  # 9G: tested 2026-11-18 (README.md, "Disk sizes")
        "media": [{"name": "Sol7.399InstallationSparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol7-ss5",
        "net_modes": ["static"],  # DHCP not tried yet (the first boot writes the same files as for 2.6)
        "minutes": 11,  # install 6, first boot 3, --check 1.5
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17, "with": "--check"},
    },
    "sol7-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 7 3/99 End User on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("3G", "9G"),  # 9G: tested 2026-11-18 (README.md, "Disk sizes")
        "media": [{"name": "Sol7.399InstallationSparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol7-ss20",
        "net_modes": ["static"],  # DHCP not tried yet (the first boot writes the same files as for 2.6)
        "minutes": 10,  # install 6, first boot 3, --check 1.5
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17, "with": "--check"},
    },
    # Web Start in command line mode (solaris-webstart-serial.py): the Installation CD copies a
    # mini-root to a swap slice and reboots into it; the two Software CDs go in when it asks
    # ("at": "scenario", in this order). Entire Group (1.6 GB with swap): the 9G disk.
    "sol8-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 8 1/01 Entire Group on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "install": {"scenario": "solaris-webstart-serial.py", "vars": {"TIMEZONE": "MET", "SOFTWARE": "2"},
                    "timeout": 7200,
                    # Web Start asks for the root password itself (the first boot doesn't)
                    "root_password": True,
                    # its reboot into the mini-root names the slice in a boot string that OpenBIOS
                    # drops: stop at the prompt instead and boot it by path (install.set_prom_env)
                    "prom_env": {"auto-boot?": "false"}},
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("9G"),
        "media": [{"name": "sun-solaris-8-0101-installation-sparc.iso", "drive": "scsi6"},
                  {"name": "sun-solaris-8-0101-software-cd1-sparc.iso", "drive": "scsi6", "at": "scenario"},
                  {"name": "sun-solaris-8-0101-software-cd2-sparc.iso", "drive": "scsi6", "at": "scenario"}],
        "boot": "scsi3",
        "hostname": "sol8-ss20",
        "net_modes": ["static"],  # DHCP not tried yet (the first boot writes the same files as for 2.6)
        "minutes": 30,  # install 24, first boot 3.5, --check 1.5
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17, "with": "--check"},
    },
    # Solaris 9 dropped sun4m from its supported platforms, but the DVD's install and the installed
    # 32-bit kernel run on an SS-20 under OpenBIOS. Web Start from the DVD (no mini-root copy),
    # the End User Group.
    "sol9-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 9 End User on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "install": {"scenario": "solaris-webstart-serial.py", "vars": {"TIMEZONE": "MET", "SOFTWARE": "4"},
                    "timeout": 7200, "root_password": True, "prom_env": {"auto-boot?": "false"}},
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("9G"),
        "media": [{"name": "SOL_9_SPARC_DVD.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol9-ss20",
        "net_modes": ["static"],  # DHCP not tried yet (the first boot writes the same files as for 2.6)
        "minutes": 27,  # install 20, first boot 5, --check 1.5
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17, "with": "--check"},
    },
    # The CD's miniroot copied to swap (slice b), suninstall's Quick install from it, then the first
    # boot's sys-config (host name, time zone GMT, address, root password, the optional user). The CD
    # is the BIN converted to 2048-byte sectors (MEDIA "from"). README.md, "SunOS 4.1.4".
    "sunos414-ss5": {
        "title": "SunOS 4.1.4 Programmer install on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "method": "scripted",
        "install": {"scenario": "sunos-install-serial.py", "vars": {"SOFTWARE": "Programmer"}, "timeout": 1800,
                    # the CD's install kernel stops QEMU with 256 MB ("Trap 0x29"): 64 MB for the
                    # install phase only, the profile's memory afterwards (Job.finish)
                    "memory": 64,
                    # OpenBIOS drops the miniroot's boot string: stop at `0 >` and boot by path
                    "prom_env": {"auto-boot?": "false"}},
        "firstboot": {"scenario": "sunos-firstboot.py", "vars": {}, "timeout": 1200},
        "check": {"scenario": "sunos-boot-disk.py", "vars": {}, "timeout": 900,
                  "commands": "uname -a; hostname; cat /etc/wsh-lab-target; df; dkinfo sd0; ifconfig -a; netstat -rn"},
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "other"},
        "disk": {"bus": "scsi3", "label": "sun", "size": 3, "geometry": SUN29G_SUNOS4},
        "media": [{"name": "sunos414-cd.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "sunos414",
        # sys-config takes the address (class netmask); the first boot adds /etc/netmasks and
        # /etc/defaultrouter, which 4.1.4's rc.boot and rc.local read
        "network": "le0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway)",
        "net_modes": ["static"],
        # 4.1.4's libc resolves host names through /etc/hosts or NIS only (DNS needs NIS or a rebuilt
        # libc), and it has no DHCP client
        "net_refuse": {"dns": "SunOS 4.1.4 resolves host names through /etc/hosts or NIS, not DNS",
                       "domain": "SunOS 4.1.4 resolves host names through /etc/hosts or NIS, not DNS"},
        "minutes": 6,  # install 2.2, first boot 2.5, --check 1
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17_WSH15, "with": "--check"},
    },
    # sysinst on the serial console leaves root without a password; netbsd-firstboot.py sets it, the
    # marker, the host name and the network (README.md, "NetBSD install targets")
    "netbsd111-sparc64": {
        **NETBSD_SCRIPTED,
        "title": "NetBSD 11.1 sparc64 without X11 (sun4u, OpenBIOS)",
        "status": "automated",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 512,
                    "ostype": "other", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        "disk": {"bus": "ide0", "size": 8, "label": None},
        "media": [{"name": "NetBSD-11.1-sparc64.iso", "drive": "ide2"}],
        "install": {"scenario": "netbsd-install-sparc64.py", "vars": {"SETS": "b"}, "timeout": 2400},
        "check": netbsd_check("wd0"),
        "boot": "ide0",
        "nic": "hme0",
        "hostname": "netbsd111-sparc64",
        "network": "hme0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain) or DHCP",
        "minutes": 11,  # 10.1-11.2 min: install 6-7, first boot 2.5, --check 1.7
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17_WSH15, "with": "--check"},
    },
    "sol10-sun4u": {
        "title": "Solaris 10 1/13 default software group on sun4u (OpenBIOS, IDE disk)",
        "status": "automated",
        "method": "scripted",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 1024,
                    "ostype": "solaris", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        # a blank image: the installer labels it (a plain image, not one of DISKS)
        "disk": {"bus": "ide0", "size": 16, "label": None},
        "device": "c0t0d0",  # the IDE disk as Solaris names it (the check's prtvtoc)
        "media": [{"name": "sol-10-u11-ga-sparc-dvd.iso", "drive": "ide2"}],
        # The text installer on ttya with a static address (DHCP=no), root's password asked by the
        # installer (root_password); its reboot at the end doesn't come back (OpenBIOS has no
        # client-interface reboot), so the scenario stops the VM and `install` boots the disk.
        "install": {"scenario": "solaris10-install-sparc64.py", "vars": {"BOOT": "", "DHCP": "no"},
                    "root_password": True, "retry_on": "before the installer", "timeout": 10800},
        "firstboot": {"scenario": "solaris10-firstboot.py", "vars": {}, "timeout": 3600},
        "check": {"scenario": "solaris10-boot-disk.py", "vars": {}, "timeout": 1800},
        "boot": "ide0",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "sol10-sun4u",
        "nic": "hme0",
        # The installer sets the host name, address and netmask; the first boot writes /etc/defaultrouter
        # and DNS (solaris10-firstboot.py). hme0 uses the IDPROM's MAC, which is net0's with pve-qemu
        # wsh/0034 (52:54:00:12:34:56 for every guest before it).
        "network": "hme0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain)",
        "net_modes": ["static"],
        "minutes": 110,  # 108.5-110.7 min: install ~81, first boot ~19, --check ~9
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17,
                   "with": "--check; --check --bridge --ip --gateway --dns --domain --user"},
    },
    # The live CD's own installer (live_install.sh -G: SMI label, ZFS root pool rpool, base overlay;
    # ROOT_FS=ufs in the install scenario uses ufs_install.sh) from a root shell on ttya; the first
    # boot sets root's password (the live CD's `tribblix` before), locks `jack`, writes the marker and
    # the network with ipadm. Needs openbios-sparc64 with patches 0016 and 0017. README.md, "The
    # Tribblix install target".
    "tribblix-m34-sun4u": {
        "title": "Tribblix m34 SPARC (illumos) base install on sun4u (OpenBIOS, IDE disk, ZFS root)",
        "status": "automated",
        "matrix_skip": "takes 3.5-4.3 h, too much of the sparc lab job's 240 minutes: installed on request"
                       " (--reinstall), its stored disk boot-tested otherwise (~26 min)",
        "method": "scripted",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 2048,
                    "ostype": "solaris", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        "disk": {"bus": "ide0", "size": 8, "label": None},  # live_install.sh labels it
        "device": "c1t0d0",  # the IDE disk as Tribblix names it
        "media": [{"name": "tribblix-sparc-0m34.iso", "drive": "ide2"}],
        "install": {"scenario": "tribblix-install-sparc64.py", "vars": {}, "timeout": 10800},
        "firstboot": {"scenario": "tribblix-firstboot.py", "vars": {}, "timeout": 7200},
        "check": {"scenario": "tribblix-boot-disk.py", "vars": {}, "timeout": 3600,
                  "commands": "uname -a; hostname; cat /etc/wsh-lab-target; df -k /; zpool status rpool;"
                              " ipadm show-addr; netstat -rn -f inet; cat /etc/resolv.conf 2>/dev/null"},
        "boot": "ide0",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "tribblix-m34",
        "nic": "hme0",
        # hme0 uses the IDPROM's MAC: net0's with pve-qemu wsh/0034, 52:54:00:12:34:56 before it
        "network": "hme0: a static address with ipadm (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns,"
                   " --domain)",
        "net_modes": ["static"],  # tribblix-firstboot.py has NET_MODE=dhcp (ipadm -T dhcp), not tried yet
        # Needs pve-qemu-kvm 11.1.3-2+wsh20 or later (OpenBIOS 0016-0017, QEMU wsh/0036). The live CD and the
        # installed system's first boot import the SMF manifests (~70 min each); later boots ~12-14 min
        # 2026-11-19 with the published packages: 207 (install 111, first boot 71, --check 25); 2026-11-18
        # with a local build: 257. A boot test of the stored disk: 26 (login 14, init 5 11)
        "minutes": 207,
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19, "with": "--check --export; boot-test"},
    },
    # The CD's microroot loads the install tools from the CD, then the same sysinst answers
    # (netbsd-install-sparc.py); a blank disk: no Sun label needed (sysinst writes a disklabel)
    "netbsd111-sparc": {
        **NETBSD_SCRIPTED,
        "title": "NetBSD 11.1 sparc Minimal on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "other"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},
        "media": [{"name": "NetBSD-11.1-sparc.iso", "drive": "scsi6"}],
        "install": {"scenario": "netbsd-install-sparc.py", "vars": {"SETS": "c"}, "timeout": 2400},
        "check": netbsd_check("sd0"),
        "boot": "scsi3",
        "nic": "le0",
        "hostname": "netbsd111-sparc",
        "minutes": 7,  # 6.6-6.8 min: install 3.5, first boot 2, --check 1
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17_WSH15, "with": "--check"},
    },
    "netbsd111-sparc-ss20": {
        **NETBSD_SCRIPTED,
        "title": "NetBSD 11.1 sparc Minimal on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512, "ostype": "other"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},
        "media": [{"name": "NetBSD-11.1-sparc.iso", "drive": "scsi6"}],
        "install": {"scenario": "netbsd-install-sparc.py", "vars": {"SETS": "c"}, "timeout": 2400},
        "check": netbsd_check("sd0"),
        "boot": "scsi3",
        "nic": "le0",
        "hostname": "netbsd111-ss20",
        "minutes": 7,  # 6.7-7.3 min: install 3.5, first boot 2, --check 1
        "tested": {"date": "2026-11-17", "packages": PACKAGES_2026_11_17_WSH15, "with": "--check"},
    },
    # Kickstart from an answer CD made on the node (answer_media.py) on scsi5, the first CD-ROM Linux
    # finds; SILO's three screens, which 6.2's kickstart doesn't skip on SPARC, answered by the
    # scenario; a Sun-labelled disk (on a blank one anaconda asks to initialize it). ostype l26: the
    # create wizard's "Linux" on sparc. README.md, "Red Hat Linux 6.2"
    "redhat62-ss5": {
        **REDHAT_UNATTENDED,
        "title": "Red Hat Linux 6.2 Base on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "l26"},
        "disk": sun_disk("3G"),
        "media": [{"name": "redhat-6.2-sparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "redhat62-ss5",
        "minutes": 6,  # 5.3-5.9 min: install 1.8-2.2, first boot 2.2-2.4, --check 1
        "tested": {"date": "2026-11-18", "packages": PACKAGES_2026_11_18,
                   "with": "--check --gateway --dns --domain"},
    },
    "redhat62-ss20": {
        **REDHAT_UNATTENDED,
        "title": "Red Hat Linux 6.2 Base on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512, "ostype": "l26"},
        "disk": sun_disk("3G"),
        "media": [{"name": "redhat-6.2-sparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "redhat62-ss20",
        "minutes": 5,  # 4.3 min: install 1.4, first boot 1.9, --check 0.7 (6.6 before the sendmail fix)
        "tested": {"date": "2026-11-18", "packages": PACKAGES_2026_11_18, "with": "--check; --check --user lab"},
    },
    # A preseed file from an answer CD made on the node (answer_media.py) on scsi5, loaded by
    # preseed/early_command on SILO's boot line; the netinst on scsi6 fetches the rest from
    # archive.debian.org (or --apt-proxy). A blank disk: on the lab's Sun-labelled one partman's new
    # label kept the old geometry and the recipe didn't fit. Linux 2.6.18's esp driver needs QEMU's
    # ESP fix for a multi-byte message out (sync negotiation). README.md, "Debian GNU/Linux 4.0"
    "debian40-ss5": {
        **DEBIAN_UNATTENDED,
        "title": "Debian GNU/Linux 4.0 (etch) base system on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "l26"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},  # partman writes its own Sun label
        "media": [{"name": "debian-40r9-sparc-netinst.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "debian40-ss5",
        "minutes": 23,  # 23.3 min with --apt-proxy: install 19.7 (base system from the archive), first boot 2.2, check 1.1
        "tested": {"date": "2026-11-18", "packages": PACKAGES_ESP_FIX,
                   "with": "--check --user lab --gateway --dns --apt-proxy"},
        "matrix_skip": ESP_FIX_NOTE,
    },
    "debian40-ss20": {
        **DEBIAN_UNATTENDED,
        "title": "Debian GNU/Linux 4.0 (etch) base system on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512, "ostype": "l26"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},  # partman writes its own Sun label
        "media": [{"name": "debian-40r9-sparc-netinst.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "debian40-ss20",
        "minutes": 19,  # 19.2 min straight to the archive: install 16.1, first boot 1.9, check 1
        "tested": {"date": "2026-11-18", "packages": PACKAGES_ESP_FIX,
                   "with": "--check --gateway --dns; --check --user lab --apt-proxy"},
        "matrix_skip": ESP_FIX_NOTE,
    },
}


def automated():
    return [name for name, t in TARGETS.items() if t["status"] == "automated"]


def problems():
    """What is wrong with the catalogue's own structure (tests/test_targets.py checks the profiles
    against qemu-server's tables); [] when nothing."""
    out = []
    for name, t in TARGETS.items():
        for key in ("title", "status", "profile", "disk", "media", "method", "boot", "login", "hostname"):
            if key not in t:
                out.append(f"{name}: no {key}")
        if t.get("status") not in ("automated", "catalogue"):
            out.append(f"{name}: status {t.get('status')!r}")
        if t.get("status") == "catalogue" and not t.get("blocked"):
            out.append(f"{name}: a catalogue entry says what blocks it")
        if t.get("status") == "automated":
            for key in ("install", "firstboot", "check", "network", "net_modes"):
                if key not in t:
                    out.append(f"{name}: automated without {key}")
        drives = set()
        for med in t.get("media", []):
            if med["name"] not in MEDIA:
                out.append(f"{name}: medium {med['name']} isn't in MEDIA")
            # qemu-server's cd_as_disk: sparc32 SCSI CD-ROMs only, and no live medium change (a scsi-hd
            # has no removable medium, so a swap would wait for the next start)
            if med.get("as_disk") and (t.get("profile", {}).get("arch") != "sparc" or not med["drive"].startswith("scsi")
                                       or med.get("at", "start") != "start"):
                out.append(f"{name}: as_disk is for a sparc32 SCSI CD-ROM at the start only ({med['name']})")
            if med.get("at", "start") == "start":
                if med["drive"] in drives:
                    out.append(f"{name}: two media in {med['drive']} at the start")
                drives.add(med["drive"])
        if t.get("method") not in ("scripted", "unattended"):
            out.append(f"{name}: method {t.get('method')!r}")
        if t.get("method") == "unattended":
            ans = t.get("install", {}).get("answers") or {}
            if not ans.get("format") or not re.fullmatch(r"(scsi|ide|sata)\d+", ans.get("drive", "")):
                out.append(f"{name}: unattended without install answers (format, drive)")
            elif ans["drive"] in drives | {t.get("disk", {}).get("bus")}:
                out.append(f"{name}: the answer CD's drive {ans['drive']} is taken")
        # the marker is typed with echo '...' (solaris-firstboot.py, netbsd-firstboot.py)
        if any("'" in str(t.get(k, "")) for k in ("title", "hostname", "dhcp_note")):
            out.append(f"{name}: a single quote in what the marker file gets")
        disk = t.get("disk", {})
        if disk.get("label") == "sun" and disk.get("geometry"):
            g = disk["geometry"]
            if (g["ncyl"] + g["acyl"]) * g["heads"] * g["sectors"] * 512 > disk["size"] << 30:
                out.append(f"{name}: the label is bigger than the disk")
        if "sizes" in disk:
            if not disk["sizes"] or any(s not in DISKS for s in disk["sizes"]):
                out.append(f"{name}: disk sizes {disk['sizes']} aren't all in DISKS")
            elif (disk["size"], disk["geometry"]) != (DISKS[disk["sizes"][0]]["size"], DISKS[disk["sizes"][0]]["geometry"]):
                out.append(f"{name}: the disk isn't its default size {disk['sizes'][0]}")
    for dname, d in DISKS.items():
        g = d["geometry"]
        if (g["ncyl"] + g["acyl"]) * g["heads"] * g["sectors"] * 512 > d["size"] << 30:
            out.append(f"disk {dname}: the label is bigger than the image")
    for fname, med in MEDIA.items():
        if med["content"] not in ("iso", "floppy"):
            out.append(f"{fname}: content {med['content']!r}")
        if len(med["sha256"]) != 64 or not med["size"]:
            out.append(f"{fname}: size and sha256 of the tested medium")
        if "from" in med and (med["from"].get("name") not in MEDIA or med["from"].get("convert") not in CONVERSIONS):
            out.append(f"{fname}: made from {med['from']}: a medium in MEDIA and a known conversion")
    for bname, b in POST_INSTALL.items():
        if b.get("medium") not in MEDIA:
            out.append(f"post-install {bname}: medium {b.get('medium')} isn't in MEDIA")
        for tname in b.get("targets", []):
            if tname not in TARGETS or TARGETS[tname].get("firstboot", {}).get("scenario") != "solaris-firstboot.py":
                out.append(f"post-install {bname}: {tname} isn't a Solaris target with solaris-firstboot.py")
            elif b.get("drive") in {m["drive"] for m in TARGETS[tname]["media"]} | {TARGETS[tname]["disk"]["bus"], "scsi4"}:
                out.append(f"post-install {bname}: drive {b.get('drive')} is taken on {tname}")
    for fname, med in MEDIA.items():
        if med.get("local_only") and med.get("url"):
            out.append(f"{fname}: a local-only medium has no URL")
    for name, t in TARGETS.items():
        for opt in t.get("net_refuse", {}):
            if opt not in ("dns", "domain", "gateway", "netmask"):
                out.append(f"{name}: net_refuse {opt!r}")
    return out


# The x86 retro targets (DOS from floppies) live in targets_dos.py.
import targets_dos  # noqa: E402

MEDIA.update(targets_dos.MEDIA)
TARGETS.update(targets_dos.TARGETS)
