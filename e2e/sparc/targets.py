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
is in the repository or downloaded by the tests.

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
             handed to the install scenario in order (SWAPS) for prompts that name no disk
  method     "scripted": the installer is answered on the console by `install` (a scenario, with
             `vars`), then `firstboot` (a scenario) sets the root password, writes the marker file
             /etc/wsh-lab-target and optionally adds a user, and powers off. "unattended" (the
             installer's own answer file on a second medium) is
             designed (README.md, "Install targets") but not implemented. DOS targets: targets_dos.py.
  boot       the boot order after the install (the media are ejected first)
  login      user and console of the finished VM; the password is DEFAULT_ROOT_PASSWORD unless
             --root-password says otherwise
  hostname   set by the installer
  network    how the guest's network is set up (the VM's notes say what one install got)
  net_modes  the --ip modes tested for an automated target: "static" (an address, with --netmask,
             --gateway, --dns, --domain) and/or "dhcp"; `lab.py install` refuses the others.
             ["none"]: the guest configures no network (DOS); only --bridge/--vlan apply
  minutes    how long `lab.py install` took on the lab host (TCG, one guest at a time)
  tested     date and packages of the last run that passed
"""

DEFAULT_ROOT_PASSWORD = "wshlab"  # public on purpose: these are throwaway lab VMs

# The packages of the last test run (the PVE test node with the published packages).
PACKAGES_2026_11_16 = {"pve-qemu-kvm": "11.1.3-2+wsh10", "qemu-server": "9.2.15+wsh6",
                       "pve-manager": "9.2.28+wsh4"}

MEDIA = {
    "solaris_2.6_598_sparc.iso": {
        "title": "Solaris 2.6 5/98 SPARC, Software CD", "content": "iso", "size": 565862400,
        "sha256": "17351669cb91a89562ed6bb23345879c4d18bd019a85085ad53f777e7b7a6b14",
        "lab": "solaris_2.6_598_sparc.iso"},
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
    "NetBSD-11.1-sparc64.iso": {
        "title": "NetBSD 11.1 sparc64 install CD (cdn.netbsd.org)", "content": "iso", "size": 694026240,
        "sha256": "a782b26be57325c8419fdb02030ea4e686a6ccf097baad2dae0a1a0c39e96f4e",
        "lab": "other-os/NetBSD-11.1-sparc64.iso"},
    "NetBSD-11.1-sparc.iso": {
        "title": "NetBSD 11.1 sparc install CD (cdn.netbsd.org)", "content": "iso", "size": 367329280,
        "sha256": "4a8985ecf7d21dad66c34c184d1535a9f901ee4ccc4d962c37558545b63b4636",
        "lab": "other-os/NetBSD-11.1-sparc.iso"},
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
    "sol251-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.5.1 11/97 End User on a SPARCstation 5 (ss5.bin)",
        "status": "catalogue",
        "blocked": "Its installer boots only from a CD that answers as a disk (scsi-hd); a PVE CD-ROM "
                   "drive is always a scsi-cd. The lab's workaround (the ISO imported read only as a disk "
                   "on target 6) isn't in `install` yet. The scripted install itself works (lab: ~60 min, "
                   "mostly its Maintenance Update).",
        "profile": {**SPARC32, "machine": "SS-5", "bios": "ss5.bin", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris_2.5.1_1197.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol251-ss5",
    },
    "sol7-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 7 3/99 on a SPARCstation 20 (OpenBIOS)",
        "status": "catalogue",
        "blocked": "The CD reaches the installer's language question on SS-5 and SS-20; no install was "
                   "run yet, so solaris-install-serial.py's screens are untested for 7.",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("3G"),
        "media": [{"name": "Sol7.399InstallationSparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol7-ss20",
    },
    "sol8-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 8 1/01 on a SPARCstation 20 (OpenBIOS)",
        "status": "catalogue",
        "blocked": "Web Start installer (a different dialogue from 2.6's) and three CDs (the media swap "
                   "below is the data model, untested). It needs more than 3 GB of disk: the 9G disk "
                   "(QEmu8G label). Reaches Web Start's first question on SS-5 and SS-20.",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("9G"),
        "media": [{"name": "sun-solaris-8-0101-installation-sparc.iso", "drive": "scsi6"},
                  {"name": "sun-solaris-8-0101-software-cd1-sparc.iso", "drive": "scsi6",
                   "at": r"Please insert.*Software 1 of 2"},
                  {"name": "sun-solaris-8-0101-software-cd2-sparc.iso", "drive": "scsi6",
                   "at": r"Please insert.*Software 2 of 2"}],
        "boot": "scsi3",
        "hostname": "sol8-ss20",
    },
    "sol9-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 9 on a SPARCstation 20 (OpenBIOS)",
        "status": "catalogue",
        "blocked": "Solaris 8 was the last release for sun4m; the 9 DVD still boots to its language menu "
                   "on SS-5 and SS-20, but no install was tried, and its installer is Web Start like 8's.",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("9G"),
        "media": [{"name": "SOL_9_SPARC_DVD.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol9-ss20",
    },
    "sunos414-ss5": {
        "title": "SunOS 4.1.4 Programmer install on a SPARCstation 5 (OpenBIOS)",
        "status": "catalogue",
        "blocked": "Installed by hand only (README.md, \"SunOS 4.1.4\"): the medium is a raw BIN that must "
                   "be cut to 2048-byte sectors, the install kernel needs 64 MB, the label's slice g must be "
                   "cut below 2 GB, the boot paths are typed at the OpenBIOS prompt, and suninstall's curses "
                   "menus redraw too lazily for the scripted driver.",
        "method": "scripted",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 64, "ostype": "other"},
        "disk": sun_disk("3G"),
        "media": [{"name": "sunos_4.1.4_install.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "sunos414",
    },
    "netbsd111-sparc64": {
        "title": "NetBSD 11.1 sparc64 without X11 (sun4u, OpenBIOS)",
        "status": "catalogue",
        "blocked": "netbsd-install-sparc64.py installs it under the lab's own QEMU; not yet run through "
                   "`install` (needs a sparc64 first-boot scenario and the root password in sysinst).",
        "method": "scripted",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 512,
                    "ostype": "other", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        "disk": {"bus": "ide0", "size": 8, "label": None},
        "media": [{"name": "NetBSD-11.1-sparc64.iso", "drive": "ide2"}],
        "install": {"scenario": "netbsd-install-sparc64.py", "vars": {"BOOT": ""}, "timeout": 2400},
        "boot": "ide0",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "netbsd111-sparc64",
        "network": "none configured (sysinst defaults)",
    },
    "sol10-sun4u": {
        "title": "Solaris 10 1/13 default software group on sun4u (OpenBIOS, IDE disk)",
        "status": "catalogue",
        "blocked": "solaris10-install-sparc64.py installs it under the lab's own QEMU (~80 min, SPARC.md "
                   "\"Solaris on sun4u\"); not yet run through `install` on a PVE node (needs a check "
                   "scenario through --pve, and the disk sizes here are plain images, not Sun-labelled).",
        "method": "scripted",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 1024,
                    "ostype": "solaris", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        "disk": {"bus": "ide0", "size": 16, "label": None},
        "media": [{"name": "sol-10-u11-ga-sparc-dvd.iso", "drive": "ide2"}],
        "install": {"scenario": "solaris10-install-sparc64.py", "vars": {"BOOT": ""}, "timeout": 10800},
        "boot": "ide0",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "sol10-sun4u",
        "network": "hme0 by DHCP (the installer's DHCP choice)",
    },
    "netbsd111-sparc": {
        "title": "NetBSD 11.1 sparc Minimal on a SPARCstation 5 (OpenBIOS)",
        "status": "catalogue",
        "blocked": "Installed by hand only (README.md, \"Idle\": microroot, then sysinst); no scenario yet.",
        "method": "scripted",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "other"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},
        "media": [{"name": "NetBSD-11.1-sparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "netbsd111-sparc",
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
            if med.get("at", "start") == "start":
                if med["drive"] in drives:
                    out.append(f"{name}: two media in {med['drive']} at the start")
                drives.add(med["drive"])
        if t.get("method") not in ("scripted", "unattended"):
            out.append(f"{name}: method {t.get('method')!r}")
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
    return out


# The x86 retro targets (DOS from floppies) live in targets_dos.py.
import targets_dos  # noqa: E402

MEDIA.update(targets_dos.MEDIA)
TARGETS.update(targets_dos.TARGETS)
