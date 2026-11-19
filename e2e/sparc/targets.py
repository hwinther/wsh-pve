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
`lab.py media <target> --convert <source>`, which checks the source's and the result's sha256; with
`from` "files" ({name: (size, sha256)}) it is made from those files in a directory (`--convert <dir>`;
`convert`: "openbsd-sets" = OpenBSD's sets on a CD, answer_media.openbsd_sets), each checked first.

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
  matrix_needs  "apt_cache": `pve_matrix.py install` installs it only with an apt cache (--apt-cache /
             WSH_LAB_APT_CACHE), which it hands the guest as --apt-proxy through a pinhole on its
             node's vmbr0; without one it skips it as it would a matrix_skip target
"""

import re

DEFAULT_ROOT_PASSWORD = "wshlab"  # public on purpose: these are throwaway lab VMs

# MEDIA "from" conversions (install.convert_medium): name -> (input sector size, offset, output size)
CONVERSIONS = {"bin2352": (2352, 16, 2048)}  # raw CD sectors (Mode 1): sync + header, 2048 data, EDC/ECC
# MEDIA "from" with "files" (install.convert_files): name -> the function of answer_media that makes the CD
FILE_CONVERSIONS = {"openbsd-sets": "openbsd_sets"}

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
# Solaris 2.3/2.5, SunOS 4.1.3_U1B and Debian 4.0 (the published packages of that day; Debian 4.0's
# Linux 2.6.18 esp driver needs the ESP fix wsh/0038, in pve-qemu-kvm 11.1.3-2+wsh20 and later)
PACKAGES_2026_11_19 ={"pve-qemu-kvm": "11.1.3-2+wsh21", "qemu-server": "9.2.19+wsh1", "pve-manager": "9.2.31+wsh1"}
# Solaris 2.2-2.4 under OpenBIOS (openbios 0019-0022) and OpenBSD 8.0 on sun4u (openbios 0023): in
# pve-qemu-kvm 11.1.3-2+wsh22 and later
PACKAGES_2026_11_19_WSH22 = {**PACKAGES_2026_11_19, "pve-qemu-kvm": "11.1.3-2+wsh22"}
# Solaris 8/9 on sun4u: pve-qemu-kvm 11.1.3-2+wsh23 (openbios 0001-0024) with openbios-sparc64 built
# from 0001-0025 mounted over the package's (0025 isn't in a package yet)
PACKAGES_2026_11_19_WSH23 = {**PACKAGES_2026_11_19, "pve-qemu-kvm": "11.1.3-2+wsh23"}
PACKAGES_2026_11_19_SUN4U89 = {**PACKAGES_2026_11_19, "pve-qemu-kvm": "11.1.3-2+wsh23 + openbios 0025"}
# the NetBSD 9.3 targets (published packages)
PACKAGES_2026_11_19_NB93 = {"pve-qemu-kvm": "11.1.3-2+wsh25", "qemu-server": "9.2.19+wsh2", "pve-manager": "9.2.31+wsh4"}

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
    "Solaris2.3Edition-II.iso": {
        "title": "Solaris 2.3 Edition II SPARC, Software CD", "content": "iso", "size": 426979328,
        "sha256": "e1c85daa46da28704bf21cb0e5bb71471c78516da6550a8230ed89a1f61d1d8f",
        "lab": "sun_solaris/Solaris/2.3/SPARC/Solaris2.3Edition-II.iso"},
    "Solaris_2.2.img": {
        "title": "Solaris 2.2 SPARC, Software CD (a raw CD image)", "content": "iso", "size": 388608000,
        "sha256": "276af9322e3f311b8bd8e4a567feb47ccc771cf9fd98a02aac61db749cbdafd8",
        "lab": "sun_solaris/Solaris/2.2/SPARC/Solaris_2.2.img"},
    "solaris2.5_sparc.iso": {
        "title": "Solaris 2.5 HW 1/96 SPARC, Software CD", "content": "iso", "size": 378101760,
        "sha256": "33f7b716af2354725c510b54e9e5f1bf7962352302137604e7c3570941b22259",
        "lab": "sun_solaris/Solaris/2.5/SPARC/solaris2.5_sparc.iso"},
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
    "Sol8.0202.Sparc.iso": {
        "title": "Solaris 8 2/02 SPARC, Installation CD", "content": "iso", "size": 584232960,
        "sha256": "82256fd48d4913332ecdfb5214965f869e7b2df3c8714d11815fc2d30c4fb8d9",
        "lab": "Solaris_8_0202_Bonus/Sol8.0202.Sparc.iso"},
    "Sol8.0202.Sparc-Software_1of2.iso": {
        "title": "Solaris 8 2/02 SPARC, Software CD 1 of 2", "content": "iso", "size": 655011840,
        "sha256": "79b9a265fc13d6fd3c6f9acb0bf48371372ba562d2cf8f4f3ed79a6363d4e5fe",
        "lab": "Solaris_8_0202_Bonus/Sol8.0202.Sparc-Software_1of2.iso"},
    "Sol8.0202.Sparc-Software_2of2.iso": {
        "title": "Solaris 8 2/02 SPARC, Software CD 2 of 2", "content": "iso", "size": 217231360,
        "sha256": "3d22d0782314d13d4fa6af5f47e7c7ff6723e49e316fb0f121499d4aa890f74f",
        "lab": "Solaris_8_0202_Bonus/Sol8.0202.Sparc-Software_2of2.iso"},
    "solaris-2.9-sparc.iso": {
        "title": "Solaris 9 9/05 SPARC, DVD", "content": "iso", "size": 3104112640,
        "sha256": "a7c3c20a95afc7124e5b7f0837ba9fb5c4167a7a4c76199390325062c983095d",
        "lab": "solaris-2.9-sparc/solaris-2.9-sparc.iso"},
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
    # SunOS 4.1.3_U1B (Solaris 1.1.1B): a plain image with 2048-byte sectors (no conversion), from the
    # lab host's .gz (gunzip -k)
    "sunos_4.1.3U1B.iso": {
        "title": "SunOS 4.1.3_U1B (Solaris 1.1.1B) install CD", "content": "iso", "size": 335851520,
        "sha256": "37bbb203e0e4267bb0977aa9237e777bdda840b03cb5a6044cf777bfe8ebb202",
        "lab": "sunos_202004/SunOS/SPARC/4.1.3U1B/sunos_4.1.3U1B.iso"},
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
    # NetBSD 9.3: the release moved to archive.netbsd.org (both SHA512s match its images/SHA512)
    "NetBSD-9.3-sparc64.iso": {
        "title": "NetBSD 9.3 sparc64 install CD (archive.netbsd.org)", "content": "iso", "size": 366673920,
        "sha256": "0db1b0bcde6c718d3f97fcade7d7dc31c030ab696d989ca45b431b8ac4d78a29",
        "lab": "other-os/NetBSD-9.3-sparc64.iso",
        "url": "https://archive.netbsd.org/pub/NetBSD-archive/NetBSD-9.3/images/NetBSD-9.3-sparc64.iso"},
    "NetBSD-9.3-sparc.iso": {
        "title": "NetBSD 9.3 sparc install CD (archive.netbsd.org)", "content": "iso", "size": 270991360,
        "sha256": "cc60918c249c7382b418c7a7da8040298ccef201d65087de12f0ed49629fa91e",
        "lab": "other-os/NetBSD-9.3-sparc.iso",
        "url": "https://archive.netbsd.org/pub/NetBSD-archive/NetBSD-9.3/images/NetBSD-9.3-sparc.iso"},
    "install80.iso": {
        "title": "OpenBSD 8.0 sparc64 install CD (cdn.openbsd.org)", "content": "iso", "size": 467599360,
        "sha256": "b8a80e5a10424ef32863d28dac7ae343666adfcfe0bbdfb4fc0230c130a560cb",
        "lab": "other-os/openbsd8.0/install80.iso",
        # freely redistributable; the sha256 is the one in the release's SHA256 file
        "url": "https://cdn.openbsd.org/pub/OpenBSD/8.0/sparc64/install80.iso"},
    # OpenBSD 5.9, the last release with the sparc (sun4m) port: its CD boots bsd.rd only (the release
    # has no install CD with the sets for sparc), so the sets come from a second CD made on the node from
    # the release's files (`lab.py media openbsd59-ss5 --convert <the release's directory>`). Sizes and
    # sha256 as in the release's signed SHA256 (the official EU mirror keeps the old releases)
    "cd59.iso": {
        "title": "OpenBSD 5.9 sparc boot CD (bsd.rd; ftp.eu.openbsd.org)", "content": "iso", "size": 4048896,
        "sha256": "34fb9b618b8d36bd7425e4505f1604f1bd23e1795b41bb19dc2cb9958fccc330",
        "lab": "other-os/openbsd5.9/cd59.iso",
        "url": "https://ftp.eu.openbsd.org/pub/OpenBSD/5.9/sparc/cd59.iso"},
    "openbsd59-sparc-sets.iso": {
        "title": "OpenBSD 5.9 sparc sets CD (bsd, bsd.rd, base, comp, man, game, SHA256.sig; made from the"
                 " release's files)",
        "content": "iso", "size": 116387840,
        "sha256": "d1bd7d02404299396b57c3ed39e4c1fc928d9c1743e6702e10c11dcd05d8c6af",
        "lab": "openbsd59-sparc-sets.iso",  # not on the lab host: pve_matrix.py makes it from "dir"
        "from": {"convert": "openbsd-sets", "dir": "other-os/openbsd5.9",
                 "url": "https://ftp.eu.openbsd.org/pub/OpenBSD/5.9/sparc/",
                 "files": {
                     "bsd": (3561739, "b9ac44a58d8e6fbb2dfc34ab46e52d56169162da4f0974113426cc58f34f38ae"),
                     "bsd.rd": (3504248, "6cb41aecf52926f2e1b9ab55eaeff2e5fff59c2cd8c2699b6875bb5af9b1ff5f"),
                     "base59.tgz": (50438928, "751a6531b1e9d34508288013bf329ee4c3b0038bc5ac919234c598a9c69bf4fd"),
                     "comp59.tgz": (46930332, "0bde8eab2e4d1ae01f61de3a4c0487106a114c2438755d0fea60f4fd52fe2469"),
                     "man59.tgz": (8994056, "5b2b14c5f83733c75eda3eb652f722765b20685f1da617be83d941fe318ab98b"),
                     "game59.tgz": (2838173, "c6217de3f64975077de376cff32dfc0002276b306b404abd67abfcca9ca5e517"),
                     # the signed list the installer checks the sets with, and the install notes (it
                     # asks before using a directory without them)
                     "SHA256.sig": (1802, "ddd3e98d4e8b74f1ddcba839e89eeddd8669b3cf97d8054b312a82a456bf4839"),
                     "INSTALL.sparc": (65874, "69113f6dab24e4ac79db8a3a80c4b341da312939f3cc75850803ce3c696bc3cf")}}},
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
    # NeXT's CDs carry a Sun label (OBP and OpenBIOS boot them) and a NeXT 4.3BSD file system with
    # 2048-byte sectors. Commercial media: no URL.
    "nextstep33_risc.iso": {
        "title": "NeXTSTEP 3.3 User CD for SPARC and PA-RISC", "content": "iso", "size": 369573888,
        "sha256": "19dae66e6623a034508097117036371f22b4a3d220a44baead904c343a1f09ea",
        "lab": "other-os/nextstep33_risc.iso"},
    # despite its name, the User CD also carries the SPARC and m68k versions (a three-way kernel)
    "Openstep-4.2-Intel-User.iso": {
        "title": "OPENSTEP 4.2 for Mach User CD (Intel, SPARC and m68k)", "content": "iso", "size": 512180224,
        "sha256": "b2b38021a6e169a1a614e5e7700655e1b77d35e3f7d1062aa3f760242a6b7d3d",
        "lab": "other-os/Openstep-4.2-Intel-User.iso"},
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
# The sparc64 profile for Solaris on sun4u (sol10-sun4u's): 1 GB, sunhme, the console on ttya
SUN4U_SOLARIS = {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 1024,
                 "ostype": "solaris", "net0": "sunhme", "serial0": "socket", "vga": "serial0"}

SOLARIS_SCRIPTED = {
    "method": "scripted",
    # solaris-install-serial.py's defaults: End User System Support, auto-layout, Networked with a
    # static address, no name service, time zone MET, manual reboot (it halts at the end)
    # retry_on: a boot of the CD that hangs before the installer's first prompt (QEMU's ESP deadlock,
    # SPARC.md "The ESP deadlock"; sol23-ss20 in install matrix run 44533778163) fails within
    # FIRST_PROMPT_TIMEOUT and gets one more boot: nothing is on the disk yet
    "install": {"scenario": "solaris-install-serial.py", "vars": {}, "timeout": 3600,
                "retry_on": "before the installer"},
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
               " which must reach archive.debian.org (or --apt-proxy), or only --apt-proxy at an address on"
               " the guest's network (no router, no name server); --domain",
    "net_modes": ["static"],
    "net_require": ["gateway", "dns"],  # unless --apt-proxy is an address on the guest's network
    "apt_proxy": True,
    # pve_matrix.py install gives them the apt cache through a pinhole on its node's vmbr0 (10.0.2.2:3142,
    # --apt-cache / WSH_LAB_APT_CACHE) and nothing else; without one it skips them
    "matrix_needs": "apt_cache",
}


OPENBSD59_SCRIPTED = {
    "method": "scripted",
    # the installer writes its disklabel. 8 GiB: the auto layout then has a 1 GB /usr/src, where the
    # installer copies the sets to check them against SHA256.sig (on 3 GiB it finds no room and
    # installs them unchecked)
    "disk": {"bus": "scsi3", "size": 8, "label": None},
    # the sets CD on target 5 is the installer's cd0 (scanned before the boot CD on 6)
    "media": [{"name": "cd59.iso", "drive": "scsi6"}, {"name": "openbsd59-sparc-sets.iso", "drive": "scsi5"}],
    "install": {"scenario": "openbsd-install-sparc.py", "vars": {"SETS_CD": "cd0", "VERIFY": "1"}, "timeout": 2400,
                "root_password": True},
    "firstboot": {"scenario": "openbsd-firstboot.py", "vars": {}, "timeout": 1800},
    "check": {"scenario": "openbsd-boot-disk.py", "vars": {}, "timeout": 1200,
              # one console line: OpenBSD's tty takes 255 characters (with --user's grep and the end marker)
              "commands": "uname -a; cat /etc/wsh-lab-target; df -k; disklabel sd0 | sed -n '/partitions:/,$p';"
                          " ifconfig le0; netstat -rn -f inet; cat /etc/resolv.conf; rcctl get ntpd flags;"
                          " pgrep -lx ntpd"},
    "boot": "scsi3",
    "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
    "nic": "le0",
    "network": "le0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain)",
    "net_modes": ["static"],
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
    # Solaris 2.2-2.4 boot under OpenBIOS with openbios 0019-0022 (pve-qemu-kvm 11.1.3-2+wsh22 and later;
    # SPARC.md, "Older Sun releases on sun4m"); before, only under a Sun PROM (ss5.bin, ss20_v2.25_rom).
    # Like 2.5.1, their installers need a CD that answers as a disk (from a scsi-cd the kernel can't
    # mount root). Solaris 2.4: 2.6's screens
    "sol24-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.4 HW 3/95 End User on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "install": {**SOLARIS_SCRIPTED["install"], "timeout": 7200},
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris_2.4_sparc.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol24-ss5",
        "net_modes": ["static"],  # no DHCP client before 2.6
        "minutes": 8,  # 8.2-8.3 min: install 4.5-4.7, first boot 2.2, --check 1.2
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
    },
    "sol24-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.4 HW 3/95 End User on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "install": {**SOLARIS_SCRIPTED["install"], "timeout": 7200},
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris_2.4_sparc.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol24-ss20",
        "net_modes": ["static"],
        "minutes": 8,  # 7.9 min (twice): install 4.3, first boot 2.2, --check 1.2
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
    },
    # Solaris 2.3 Edition II (the first release for the SS-5; the SS-20 needs 2.3 or later): sysidtool's
    # older one-question screens and Quick Install (solaris-install-serial.py's 2.3 path); the installer
    # reboots by itself at the end (OpenBIOS's banner instead of the Sun PROM's `ok`)
    "sol23-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.3 Edition II End User on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "Solaris2.3Edition-II.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol23-ss5",
        "net_modes": ["static"],  # no DHCP client before 2.6
        "minutes": 10,  # 9.8 min: install 5.9-6, first boot 2.3, --check 1.3
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
    },
    "sol23-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.3 Edition II End User on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("3G"),
        "media": [{"name": "Solaris2.3Edition-II.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol23-ss20",
        "net_modes": ["static"],
        "minutes": 9,  # 9.0-9.2 min: install 5.1-5.4, first boot 2.3, --check 1.3
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
    },
    # Solaris 2.2 runs on the SS-10 only of QEMU's sun4m machines (Sun supports it on the SS-10, not on
    # the later SS-5 and SS-20; under the SS-20 PROM its kernel panics). The 2.3 path of
    # solaris-install-serial.py (Quick Install); the CD as a disk
    "sol22-ss10": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.2 End User on a SPARCstation 10 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-10", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "Solaris_2.2.img", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol22-ss10",
        "net_modes": ["static"],
        "minutes": 9,  # 8.8-9.1 min: install 4.9-5.3, first boot 2.3, --check 1.3
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
    },
    # Solaris 2.5 (HW 1/96): OpenBIOS boots it, but like 2.5.1 its installer needs a CD that answers
    # as a disk (from a scsi-cd it hangs after the kernel banner). 2.6's screens; no Maintenance Update.
    "sol25-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.5 HW 1/96 End User on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris2.5_sparc.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol25-ss5",
        "net_modes": ["static"],  # no DHCP client before 2.6
        "minutes": 9,  # install 4.3, first boot 2.7, --check 1.3
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19, "with": "--check"},
    },
    "sol25-ss20": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 2.5 HW 1/96 End User on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512},
        "disk": sun_disk("3G"),
        "media": [{"name": "solaris2.5_sparc.iso", "drive": "scsi6", "as_disk": True}],
        "boot": "scsi3",
        "hostname": "sol25-ss20",
        "net_modes": ["static"],
        "minutes": 9,  # install 4.4, first boot 2.7, --check 1.3
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19, "with": "--check"},
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
    # Solaris 8 and 9 on the SS-5 (256 MB): the same Web Start installs as on the SS-20, from the
    # later updates (8 2/02, 9 9/05). 8 2/02's Installation CD asks for the first Software CD in its
    # own words, 9 9/05 adds a license question (solaris-webstart-serial.py).
    "sol8-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 8 2/02 Entire Group on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "install": {"scenario": "solaris-webstart-serial.py", "vars": {"TIMEZONE": "MET", "SOFTWARE": "2"},
                    "timeout": 7200, "root_password": True, "prom_env": {"auto-boot?": "false"}},
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("9G"),
        "media": [{"name": "Sol8.0202.Sparc.iso", "drive": "scsi6"},
                  {"name": "Sol8.0202.Sparc-Software_1of2.iso", "drive": "scsi6", "at": "scenario"},
                  {"name": "Sol8.0202.Sparc-Software_2of2.iso", "drive": "scsi6", "at": "scenario"}],
        "boot": "scsi3",
        "hostname": "sol8-ss5",
        "net_modes": ["static"],  # DHCP not tried yet (the first boot writes the same files as for 2.6)
        "minutes": 37,  # install 31.6, first boot 3.6, --check 1.6
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
    },
    "sol9-ss5": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 9 9/05 End User on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "install": {"scenario": "solaris-webstart-serial.py", "vars": {"TIMEZONE": "MET", "SOFTWARE": "4"},
                    "timeout": 7200, "root_password": True, "prom_env": {"auto-boot?": "false"}},
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256},
        "disk": sun_disk("9G"),
        "media": [{"name": "solaris-2.9-sparc.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "sol9-ss5",
        "net_modes": ["static"],  # DHCP not tried yet (the first boot writes the same files as for 2.6)
        "minutes": 30,  # install 23.7, first boot 4.5, --check 1.2
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check"},
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
    # The installer (bsd.rd) answered on ttya by what it asks (_openbsd.installer): hme0 static, root's
    # password, the auto layout on wd0, the sets without X11; ntpd off before the first boot (with a
    # network that reaches NTP servers, ntpd's clock slew was followed by wd0 read timeouts); the first
    # boot writes the marker and the network files. The installed GENERIC kernel needs openbios 0023
    # (pve-qemu-kvm 11.1.3-2+wsh22 and later). README.md, "The OpenBSD 8.0 install target"
    "openbsd80-sun4u": {
        "title": "OpenBSD 8.0 sparc64 without X11 (sun4u, OpenBIOS, IDE disk)",
        "status": "automated",
        "method": "scripted",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 512,
                    "ostype": "other", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        "disk": {"bus": "ide0", "size": 8, "label": None},  # the installer writes its disklabel
        "media": [{"name": "install80.iso", "drive": "ide2"}],
        # once in five installs the CD stopped answering while the sets were extracted (`cd0(pciide0:1:0):
        # timeout`, then silence): the scenario fails after 5 minutes of it and the install runs once more
        "install": {"scenario": "openbsd-install-sparc64.py", "vars": {"SETS": "-x*"}, "timeout": 5400,
                    "root_password": True, "retry_on": "IDE timeouts"},
        "firstboot": {"scenario": "openbsd-firstboot.py", "vars": {}, "timeout": 2400},
        "check": {"scenario": "openbsd-boot-disk.py", "vars": {}, "timeout": 1800,
                  # one console line: OpenBSD's tty takes 255 characters (with --user's grep and the
                  # end marker the scenario adds)
                  "commands": "uname -a; cat /etc/wsh-lab-target; df -k; disklabel wd0 | sed -n '/partitions:/,$p';"
                              " ifconfig hme0; netstat -rn -f inet; cat /etc/resolv.conf; rcctl get ntpd flags;"
                              " pgrep -lx ntpd"},
        "boot": "ide0",
        "login": {"user": "root", "console": "serial0 (qm terminal <vmid>)"},
        "hostname": "openbsd80-sun4u",
        "nic": "hme0",
        # The installer sets the address (hostname.hme0); the first boot writes it again with the
        # netmask, /etc/mygate and /etc/resolv.conf (openbsd-firstboot.py)
        "network": "hme0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain)",
        "net_modes": ["static"],
        "minutes": 20,  # 18.0-22.4 min (4 runs): install 9-11.6 (the sets, the kernel relink), first boot 5.3-6.5, --check 3.5-3.9
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22,
                   "with": "--check; --check --export; --check --ip --gateway --dns --domain --user; boot-test"},
    },
    # OpenBSD 5.9, the last release of the sparc port, on sun4m: cd59.iso boots bsd.rd (by path at
    # OpenBIOS's `0 >`), the sets come from the sets CD made on the node (`lab.py media <target>
    # --convert <the release's directory>`, MEDIA "from") on scsi5, the installer's cd0; answered on
    # ttya by what it asks (_openbsd.installer, 5.9's wording): le0 static, root's password, the auto
    # layout on sd0, all the sets on the CD (no X11), ntpd off; the first boot writes the marker and
    # the network files. The VM's -nographic (vga: serial0) matters: with the keyboard ESCC that QEMU
    # adds with a display, 5.9's kernel panics ("crazy interrupts"). README.md, "OpenBSD 5.9 on sun4m"
    "openbsd59-ss5": {
        **OPENBSD59_SCRIPTED,
        "title": "OpenBSD 5.9 sparc without X11 on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "other"},
        "hostname": "openbsd59-ss5",
        "minutes": 11,  # 10.2-12.2 min (3 runs, 8 GiB): install 3.2-4, first boot 5-7.6, --check ~1
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22,
                   "with": "--check; --check --export; --check --ip --gateway --dns --domain --user; boot-test"},
    },
    # The same on an SS-20 (one CPU: OpenBSD/sparc has no multiprocessor kernel)
    "openbsd59-ss20": {
        **OPENBSD59_SCRIPTED,
        "title": "OpenBSD 5.9 sparc without X11 on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512, "ostype": "other"},
        "hostname": "openbsd59-ss20",
        "minutes": 10,  # 10.0-10.2 min (2 runs, 8 GiB): install 3-3.7, first boot 5-6, --check ~1
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH22, "with": "--check; --check --ip --user"},
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
    # Solaris 9 9/05 and 8 2/02 on sun4u: the Web Start installs of sol9-ss5/sol8-ss5
    # (solaris-webstart-serial.py) with the IDE disk (c0t0d0) and its sun4u answers (64-bit and 32-bit
    # support), End User. Both need openbios-sparc64 with patch 0024 (pp is NULL or free; pve-qemu-kvm
    # 11.1.3-2+wsh23 and later), 9 also 0025 (pve-qemu-kvm 11.1.3-2+wsh25 and later; no ebus floppy node: its first, reconfiguring boot
    # panicked in the fd driver; 8 only warns). A reboot doesn't
    # come back on sun4u: the scenario stops the VM at `0 >` after the install (as sol10-sun4u), and
    # 8's reboot into the mini-root is a power cycle through PVE (lab.PveMachine.power_cycle()).
    "sol9-sun4u": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 9 9/05 End User on sun4u (OpenBIOS, IDE disk)",
        "status": "automated",
        "install": {"scenario": "solaris-webstart-serial.py",
                    "vars": {"TIMEZONE": "MET", "SOFTWARE": "4", "DISK": "c0t0d0", "PROMPT_TIMEOUT": "5400"},
                    "timeout": 9000, "root_password": True},
        "firstboot": {**SOLARIS_SCRIPTED["firstboot"], "timeout": 3600},
        "check": {**SOLARIS_SCRIPTED["check"], "timeout": 2400},
        "profile": {**SUN4U_SOLARIS},
        "disk": {"bus": "ide0", "size": 8, "label": None},  # a blank image: Web Start labels it
        "device": "c0t0d0",
        "media": [{"name": "solaris-2.9-sparc.iso", "drive": "ide2"}],
        "boot": "ide0",
        "hostname": "sol9-sun4u",
        "nic": "hme0",
        "network": "hme0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain)",
        "net_modes": ["static"],
        "minutes": 70,  # 70.0 min (install 59, first boot 6.7, --check 3.6), openbios 0025 mounted
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_SUN4U89, "with": "--check"},
    },
    # The Installation CD copies a mini-root to the swap slice (b) and reboots into it: on sun4u the
    # reboot returns to `0 >` (a panic), the VM is power-cycled and slice b booted at `0 >` (auto-boot?
    # false for the install phase); Web Start from the mini-root asks for Software 1 of 2 (End User
    # needs no Software 2 of 2)
    "sol8-sun4u": {
        **SOLARIS_SCRIPTED,
        "title": "Solaris 8 2/02 End User on sun4u (OpenBIOS, IDE disk)",
        "status": "automated",
        "install": {"scenario": "solaris-webstart-serial.py",
                    "vars": {"TIMEZONE": "MET", "SOFTWARE": "4", "DISK": "c0t0d0", "PROMPT_TIMEOUT": "5400"},
                    "timeout": 9000, "root_password": True, "prom_env": {"auto-boot?": "false"}},
        "firstboot": {**SOLARIS_SCRIPTED["firstboot"], "timeout": 3600},
        "check": {**SOLARIS_SCRIPTED["check"], "timeout": 2400},
        "profile": {**SUN4U_SOLARIS},
        "disk": {"bus": "ide0", "size": 8, "label": None},  # the Installation CD labels it
        "device": "c0t0d0",
        "media": [{"name": "Sol8.0202.Sparc.iso", "drive": "ide2"},
                  {"name": "Sol8.0202.Sparc-Software_1of2.iso", "drive": "ide2", "at": "scenario"}],
        "boot": "ide0",
        "hostname": "sol8-sun4u",
        "nic": "hme0",
        "network": "hme0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain)",
        "net_modes": ["static"],
        # 53.4-56.9 min (2 runs): install 42-46 (mini-root copy, power cycle, Web Start), first boot 6.3-6.4,
        # --check 4.4-4.5; one run with openbios 0025 mounted, one with the package's firmware
        "minutes": 55,
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_WSH23,
                   "with": "--check (the published firmware); --check (openbios 0025)"},
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
    # NetBSD 9.3: the 11.1 targets' profiles, scenarios and answers; 9.3's sysinst has no root password
    # prompt and no entropy question after the sets (_netbsd.AFTER_SETS)
    "netbsd93-sparc64": {
        **NETBSD_SCRIPTED,
        "title": "NetBSD 9.3 sparc64 without X11 (sun4u, OpenBIOS)",
        "status": "automated",
        "profile": {"arch": "sparc64", "machine": "sun4u", "bios": "openbios-sparc64", "memory": 512,
                    "ostype": "other", "net0": "sunhme", "serial0": "socket", "vga": "serial0"},
        "disk": {"bus": "ide0", "size": 8, "label": None},
        "media": [{"name": "NetBSD-9.3-sparc64.iso", "drive": "ide2"}],
        "install": {"scenario": "netbsd-install-sparc64.py", "vars": {"SETS": "b"}, "timeout": 2400},
        "check": netbsd_check("wd0"),
        "boot": "ide0",
        "nic": "hme0",
        "hostname": "netbsd93-sparc64",
        "network": "hme0: a static address (10.0.2.15/24 unless --ip/--netmask; --gateway, --dns, --domain) or DHCP",
        "minutes": 18,  # 18.4 min: install 13.9 (11.1's: 6-7), first boot 2.4, --check 1.7; boot-test 1.5
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_NB93, "with": "--check --export; boot-test"},
    },
    "netbsd93-sparc": {
        **NETBSD_SCRIPTED,
        "title": "NetBSD 9.3 sparc Minimal on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "other"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},
        "media": [{"name": "NetBSD-9.3-sparc.iso", "drive": "scsi6"}],
        "install": {"scenario": "netbsd-install-sparc.py", "vars": {"SETS": "c"}, "timeout": 2400},
        "check": netbsd_check("sd0"),
        "boot": "scsi3",
        "nic": "le0",
        "hostname": "netbsd93-sparc",
        "minutes": 7,  # 6.8 min: install 3.2, first boot 2, --check 1.2; boot-test of the stored disk 1.3
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_NB93, "with": "--check --export; boot-test"},
    },
    "netbsd93-sparc-ss20": {
        **NETBSD_SCRIPTED,
        "title": "NetBSD 9.3 sparc Minimal on a SPARCstation 20 (OpenBIOS, one CPU)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-20", "memory": 512, "ostype": "other"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},
        "media": [{"name": "NetBSD-9.3-sparc.iso", "drive": "scsi6"}],
        "install": {"scenario": "netbsd-install-sparc.py", "vars": {"SETS": "c"}, "timeout": 2400},
        "check": netbsd_check("sd0"),
        "boot": "scsi3",
        "nic": "le0",
        "hostname": "netbsd93-ss20",
        "minutes": 6,  # 6.1 min: install 2.8, first boot 2, --check 0.9
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19_NB93, "with": "--check --export; boot-test"},
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
    # ESP fix for a multi-byte message out (sync negotiation; wsh/0038, pve-qemu-kvm 11.1.3-2+wsh20 and
    # later). README.md, "Debian GNU/Linux 4.0"
    "debian40-ss5": {
        **DEBIAN_UNATTENDED,
        "title": "Debian GNU/Linux 4.0 (etch) base system on a SPARCstation 5 (OpenBIOS)",
        "status": "automated",
        "profile": {**SPARC32, "machine": "SS-5", "memory": 256, "ostype": "l26"},
        "disk": {"bus": "scsi3", "size": 3, "label": None},  # partman writes its own Sun label
        "media": [{"name": "debian-40r9-sparc-netinst.iso", "drive": "scsi6"}],
        "boot": "scsi3",
        "hostname": "debian40-ss5",
        # two installs at once on a shared host: 21.6 min with --apt-proxy (install 17.8, first boot 2.2,
        # check 1.2), 26 straight to the archive (22.1, 2.2, 1.5)
        "minutes": 24,
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19,
                   "with": "--check --user lab --gateway --dns --apt-proxy; --check --gateway --dns"},
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
        # two installs at once on a shared host: 17.4 min straight to the archive (install 14.2, first
        # boot 1.8, check 1.1), 20.7 with --apt-proxy (17, 2.2, 1.1)
        "minutes": 19,
        "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19,
                   "with": "--check --gateway --dns; --check --user lab --gateway --dns --apt-proxy"},
    },
}

# SunOS 4.1.3_U1B (Solaris 1.1.1B): the first SunOS 4 for the SS-5 and SS-20 (Sun lists the kernel patch
# 101508 for the SS-5's microSPARC-II; the CD's kernel and the installed one run without it). The 4.1.4
# install unchanged: the same miniroot on slice d, suninstall and sys-config screens.
_SUNOS4 = {k: v for k, v in TARGETS["sunos414-ss5"].items() if k not in ("title", "tested", "minutes")}
_SUNOS4["net_refuse"] = {k: v.replace("4.1.4", "4.1.3_U1B") for k, v in _SUNOS4["net_refuse"].items()}
TARGETS["sunos413u1b-ss5"] = {
    **_SUNOS4,
    "title": "SunOS 4.1.3_U1B Programmer install on a SPARCstation 5 (OpenBIOS)",
    "media": [{"name": "sunos_4.1.3U1B.iso", "drive": "scsi6"}],
    "hostname": "sunos413",
    "minutes": 6,  # install 2.5, first boot 2.6, --check 0.9
    "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19, "with": "--check"},
}
TARGETS["sunos413u1b-ss20"] = {
    **_SUNOS4,
    "title": "SunOS 4.1.3_U1B Programmer install on a SPARCstation 20 (OpenBIOS, one CPU)",
    "profile": {**SPARC32, "machine": "SS-20", "memory": 512, "ostype": "other"},
    "media": [{"name": "sunos_4.1.3U1B.iso", "drive": "scsi6"}],
    "hostname": "sunos413",
    "minutes": 6,  # install 2.5, first boot 2.6, --check 1
    "tested": {"date": "2026-11-19", "packages": PACKAGES_2026_11_19, "with": "--check"},
}

# NeXTSTEP 3.3 and OPENSTEP 4.2 (Mach) for SPARC: the CD's text stage (language, disk, copy the base
# system) and, after a reboot into the disk, Configure and the graphical Installer, all on the TCX
# framebuffer with the Sun keyboard and mouse (not on ttya). The installed disk boots only under the
# Sun PROM ss5.bin (OpenBIOS stops in NeXT's boot program) and only with `-v` typed at its `boot:`
# prompt (its boot graphics end in "Data Access Error" on QEMU's 8-bit TCX). README.md and
# submodules/SPARC.md, "NeXTSTEP 3.3 and OPENSTEP 4.2".
_NEXT_BLOCKED = ("Without a delayed ESP interrupt the guest's SCSI driver deadlocks (it spins at PIL 4 on a lock"
                 " that the code it interrupted holds) because QEMU's ESP raises its interrupt in the same"
                 " instruction that starts a command: each of 6 installs with the published packages (11.1.3-2+wsh21 and +wsh22) stopped that way"
                 " (while mounting root, preparing the disk or copying). pve-qemu patch wsh/0040 and the VM option"
                 " machine: SS-5,esp-irq-latency=500 (qemu-server, set in the profile) fix it; the targets wait for"
                 " published packages with them and for framebuffer scenarios (TCX, keyboard and mouse) and a Sun"
                 " PROM boot with -v after the CD stage.")
_NEXT = {
    "status": "catalogue",
    "blocked": _NEXT_BLOCKED,
    "method": "scripted",
    # ss5.bin for the whole install: the CD boots under it, the installed disk only under it
    # esp-irq-latency: the ESP's interrupt 500 us after the event, or NeXT's SCSI driver deadlocks
    "profile": {**SPARC32, "machine": "SS-5,esp-irq-latency=500", "bios": "ss5.bin", "memory": 256, "ostype": "other",
                "vga": "tcx"},
    "disk": {"bus": "scsi3", "size": 2, "label": None},  # the installer writes its own (NeXT) label
    "boot": "scsi3",
    # the setup ends logged in as `me` (no password; root has none either)
    "login": {"user": "me", "console": "the TCX framebuffer (VNC console)"},
}
TARGETS["nextstep33-ss5"] = {
    **_NEXT,
    "title": "NeXTSTEP 3.3 on a SPARCstation 5 (ss5.bin, TCX)",
    "media": [{"name": "nextstep33_risc.iso", "drive": "scsi6"}],
    "hostname": "nextstep33",
}
TARGETS["openstep42-ss5"] = {
    **_NEXT,
    "title": "OPENSTEP 4.2 for Mach on a SPARCstation 5 (ss5.bin, TCX)",
    "media": [{"name": "Openstep-4.2-Intel-User.iso", "drive": "scsi6"}],
    "hostname": "openstep42",
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
        if "from" in med and "files" in med["from"]:
            f = med["from"]
            if f.get("convert") not in FILE_CONVERSIONS or not f.get("dir") or not f["files"] or any(
                    not isinstance(size, int) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    for size, digest in f["files"].values()):
                out.append(f"{fname}: made from files: a known conversion, the lab directory, (size, sha256) each")
        elif "from" in med and (med["from"].get("name") not in MEDIA or med["from"].get("convert") not in CONVERSIONS):
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
