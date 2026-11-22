// Data for the living museum picker (components/LivingMuseum.astro, guides/living-museum.mdx):
// demo idea 9 in ROADMAP.md ("pick a machine and OS ... and watch its install and first boot from
// the existing recordings"). Every fact here comes from one of four places: guides/sparc-recordings.mdx
// (the recordings themselves), guides/dos.md, guides/lab-install.md (the "Try it yourself"
// commands and timings) or a README under e2e/. Add a scenario when sparc-recordings.mdx documents
// an install/boot pair (or a section with matching casts/videos).
//
// Recordings aren't in git: see components/LabCast.astro and components/LabVideo.astro for where
// they come from and what a visitor sees when a copy of the site doesn't have them.

export interface LivingMuseumMedia {
  kind: "cast" | "video";
  src: string; // e.g. /recordings/sol26-install-ss5.cast
  caption: string;
  poster?: string; // cast: an asciinema npt marker; video: an image path
  captions?: string; // video only: a WebVTT track
  width?: number; // video only
  height?: number; // video only
}

export interface LivingMuseumStage {
  label: string; // "Install", "First boot", ...
  media: LivingMuseumMedia;
}

export interface LivingMuseumTryIt {
  command: string; // an exact command from guides/lab-install.md (or e2e/*/README.md)
  note: string; // what it does and how long it takes, from the same source
}

export interface LivingMuseumScenario {
  id: string;
  machine: string; // picker value
  machineLabel: string;
  os: string; // picker value
  osLabel: string;
  osFamily: string; // optgroup label; matches the OS families named in ROADMAP.md's demo idea 9
  blurb: string;
  stages: LivingMuseumStage[];
  tryIt?: LivingMuseumTryIt; // from guides/lab-install.md: the target name may differ from `os`/`id`
}

const scenarios: LivingMuseumScenario[] = [
  {
    id: "sol26-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol26",
    osLabel: "Solaris 2.6",
    osFamily: "Solaris 2.x",
    blurb:
      "The End User install from the Solaris 2.6 (5/98) CD on the serial console, then the same disk " +
      "with the console on a cg3 framebuffer: the OpenBIOS banner, the kernel, the root password " +
      "questions and the CDE login screen. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol26-install-ss5.cast",
          caption: "Solaris 2.6 End User install, SS-5 with OpenBIOS, serial console",
          poster: "npt:0:20",
        },
      },
      {
        label: "First boot (cg3 framebuffer)",
        media: {
          kind: "video",
          src: "/recordings/sol26-cg3-ss5.webm",
          captions: "/recordings/sol26-cg3-ss5.vtt",
          poster: "/recordings/sol26-cg3-ss5-poster.png",
          width: 1024,
          height: 768,
          caption: "Solaris 2.6 on SS-5 with a cg3 framebuffer, OpenBIOS banner to dtlogin (time-lapse, 10x)",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol26-ss5 --check",
      note: "about 12 minutes, ends logged in as root/wshlab (lab-install.md)",
    },
  },
  {
    id: "sol26-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol26",
    osLabel: "Solaris 2.6",
    osFamily: "Solaris 2.x",
    blurb:
      "An installed Solaris 2.6 disk booting on SS-20 with OpenBIOS: the PROM, the kernel, the " +
      "first-boot questions, login, uname/df/ifconfig and init 5, which powers the VM off.",
    stages: [
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol26-boot-ss20.cast",
          caption: "Solaris 2.6 booting an installed disk, SS-20 with OpenBIOS, serial console",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol26-ss20 --check",
      note: "about 12 minutes, makes a fresh VM rather than reusing a stored disk (lab-install.md)",
    },
  },
  {
    id: "sol26-ss20-4cpu",
    machine: "ss20-4cpu",
    machineLabel: "SPARCstation 20 (SS-20), 4 CPUs",
    os: "sol26",
    osLabel: "Solaris 2.6",
    osFamily: "Solaris 2.x",
    blurb:
      "The same stored SS-20 disk in a VM with four cores: the PROM and the kernel bring up four " +
      "SuperSPARC CPUs, then login, psrinfo (four on-line) and mpstat 1 3 at the idle shell, where " +
      "the CPUs sit idle (QEMU's solaris-smp-idle halts them). SS-20, OpenBIOS, 512 MB.",
    stages: [
      {
        label: "Four CPUs at the idle shell",
        media: {
          kind: "cast",
          src: "/recordings/sol26-smp4-ss20.cast",
          caption: "Solaris 2.6 on SS-20 with 4 CPUs: psrinfo and mpstat, serial console",
          poster: "npt:0:10",
        },
      },
    ],
  },
  {
    id: "sol21-ss10",
    machine: "ss10",
    machineLabel: "SPARCstation 10 (SS-10)",
    os: "sol21",
    osLabel: "Solaris 2.1",
    osFamily: "Solaris 2.x",
    blurb:
      "The oldest Solaris the lab runs (SunOS 5.1), the first release for sun4m, made possible by " +
      "pve-qemu patch wsh/0047. The CD (as a disk) boots the installer, system identification, then " +
      "2.1's own suninstall menus. SS-10, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol21-install-ss10.cast",
          caption: "Solaris 2.1 install, SS-10 with OpenBIOS under PVE, serial console (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol21-boot-ss10.cast",
          caption: "Solaris 2.1 booting the installed disk, SS-10 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol21-ss10 --check",
      note: "about 11 minutes; needs pve-qemu-kvm 11.1.3-2+wsh29 or later (lab-install.md)",
    },
  },
  {
    id: "sol22-ss10",
    machine: "ss10",
    machineLabel: "SPARCstation 10 (SS-10)",
    os: "sol22",
    osLabel: "Solaris 2.2",
    osFamily: "Solaris 2.x",
    blurb:
      "Made possible by OpenBIOS patches 0019-0023. The CD (as a disk) boots the installer, one " +
      "system identification question per screen, Quick Install, End User, the file systems and the " +
      "packages. SS-10, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol22-install-ss10.cast",
          caption: "Solaris 2.2 install, SS-10 with OpenBIOS under PVE, serial console (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol22-boot-ss10.cast",
          caption: "Solaris 2.2 first boot of the installed disk, SS-10 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol22-ss10 --check",
      note: "about 9 minutes; needs pve-qemu-kvm 11.1.3-2+wsh22 or later (lab-install.md)",
    },
  },
  {
    id: "sunos413u1b-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sunos413u1b",
    osLabel: "SunOS 4.1.3_U1B",
    osFamily: "SunOS",
    blurb:
      "SunOS 4.1.3_U1B (Solaris 1.1.1B), the first SunOS 4 for the SS-5 and SS-20. The install " +
      "copies the CD's miniroot to the swap slice and runs suninstall's Quick install (Programmer); " +
      "the check boots the disk, logs in and halts. SS-5, OpenBIOS, 64 MB for the install, 256 MB after.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sunos413-install-ss5.cast",
          caption: "SunOS 4.1.3_U1B install from CD, SS-5 with OpenBIOS under PVE, serial console",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sunos413-boot-ss5.cast",
          caption: "SunOS 4.1.3_U1B booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sunos413u1b-ss5 --check",
      note: "about 6 minutes (lab-install.md)",
    },
  },
  {
    id: "sunos413-ss10",
    machine: "ss10",
    machineLabel: "SPARCstation 10 (SS-10)",
    os: "sunos413",
    osLabel: "SunOS 4.1.3",
    osFamily: "SunOS",
    blurb:
      "SunOS 4.1.3 (Solaris 1.1, kernel built July 1992), the first SunOS 4 for the SS-10, from its " +
      "own CD; needs pve-qemu patch wsh/0049 for the SuperSPARC bus-error trap its VME probe hits. " +
      "The same install as 4.1.3_U1B. SS-10, OpenBIOS, 64 MB for the install, 256 MB after.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sunos413-install-ss10.cast",
          caption: "SunOS 4.1.3 install from CD, SS-10 with OpenBIOS under PVE, serial console",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sunos413-boot-ss10.cast",
          caption: "SunOS 4.1.3 booting the installed disk, SS-10 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sunos413-ss10 --check",
      note: "about 6 minutes; needs pve-qemu-kvm 11.1.3-2+wsh31 or later (lab-install.md)",
    },
  },
  {
    id: "sunos412-ss600mp",
    machine: "ss600mp",
    machineLabel: "SPARCserver 600MP",
    os: "sunos412",
    osLabel: "SunOS 4.1.2",
    osFamily: "SunOS",
    blurb:
      "The oldest Sun release the lab runs: SunOS 4.1.2 (Solaris 1.0.1), the first release for " +
      "sun4m, on its first sun4m machine. Needs pve-qemu patches wsh/0063-0065 (the 600MP's VMEbus " +
      "registers and its network chip's buffer memory) and OpenBIOS patch 0028. One CPU, 64 MB for " +
      "the install, 256 MB after.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sunos412-install-ss600mp.cast",
          caption: "SunOS 4.1.2 install from CD, SPARCserver 600MP with OpenBIOS under PVE, serial console",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sunos412-boot-ss600mp.cast",
          caption: "SunOS 4.1.2 booting the installed disk, SPARCserver 600MP with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sunos412-ss600mp --check",
      note:
        "needs pve-qemu-kvm 11.1.3-3+wsh13 or later and the SS-600MP profile (lab-install.md); " +
        "6.2 minutes in the run that made this recording (install 143 s, first boot 150 s, check 51 s; e2e/sparc/README.md)",
    },
  },
  {
    id: "netbsd111-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "netbsd111",
    osLabel: "NetBSD 11.1",
    osFamily: "NetBSD",
    blurb:
      "sysinst from the NetBSD 11.1 sparc CD: the microroot loads the installation tools from the " +
      "CD, then the disk, the Minimal set, root without a password and power off. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/netbsd111-install-ss5.cast",
          caption: "NetBSD 11.1 sparc install with sysinst, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/netbsd111-boot-ss5.cast",
          caption: "NetBSD 11.1 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install netbsd111-sparc --check",
      note: "the lab-install.md target name for this profile; about 7 minutes",
    },
  },
  {
    id: "openbsd59-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "openbsd59",
    osLabel: "OpenBSD 5.9",
    osFamily: "OpenBSD",
    blurb:
      "OpenBSD 5.9, the last release of the sparc port: cd59.iso boots bsd.rd from the OpenBIOS " +
      "prompt, and the sets come from a second CD the lab makes from the release's directory. le0 " +
      "with a static address, root's password, the auto layout on sd0, all the sets except X11. " +
      "SS-5, OpenBIOS, 256 MB, no framebuffer.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/openbsd59-install-ss5.cast",
          caption: "OpenBSD 5.9 sparc install, SS-5 with OpenBIOS under PVE, serial console (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/openbsd59-boot-ss5.cast",
          caption: "OpenBSD 5.9 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install openbsd59-ss5 --check",
      note: "about 10 minutes (lab-install.md)",
    },
  },
  {
    id: "openbsd80-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "openbsd80",
    osLabel: "OpenBSD 8.0",
    osFamily: "OpenBSD",
    blurb:
      "The OpenBSD 8.0 sparc64 install CD on sun4u: the installer on ttya with a static address on " +
      "hme0, root's password, the auto layout on the IDE disk, all the sets except X11, ntpd on. " +
      "sun4u, OpenBIOS, 512 MB, IDE disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/openbsd80-install-sun4u.cast",
          caption: "OpenBSD 8.0 sparc64 install, sun4u with OpenBIOS under PVE, serial console (3x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/openbsd80-boot-sun4u.cast",
          caption: "OpenBSD 8.0 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install openbsd80-sun4u --check",
      note: "about 19 minutes; keeps ntpd off (lab-install.md)",
    },
  },
  {
    id: "debian40-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "debian40",
    osLabel: "Debian GNU/Linux 4.0 (etch)",
    osFamily: "Debian 4",
    blurb:
      "The netinst CD with a preseed file: one line typed at SILO's boot: loads the lab's answers " +
      "from a second CD, and debian-installer runs unattended from there (network, the base system " +
      "and the kernel from archive.debian.org, the disk, SILO, the reboot). SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/debian40-install-ss5.cast",
          caption: "Debian 4.0 (etch) preseeded netinst install, SS-5 with OpenBIOS under PVE (4x)",
          poster: "npt:0:20",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/debian40-boot-ss5.cast",
          caption: "Debian 4.0 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install debian40-ss5 --gateway <gw> --dns <dns> --check",
      note:
        "about 22-26 minutes; needs a route to archive.debian.org for the packages, hence " +
        "--gateway/--dns (or --apt-proxy for a cache; lab-install.md)",
    },
  },
  {
    id: "redhat62-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "redhat62",
    osLabel: "Red Hat Linux 6.2",
    osFamily: "Red Hat 6.2",
    blurb:
      "The Red Hat Linux 6.2 sparc CD with a kickstart file from a second CD made on the node: one " +
      "line at SILO's boot: prompt starts the installer (Linux 2.2.14), which runs unattended in " +
      "text mode apart from the three boot loader screens the lab answers; then the Base packages " +
      "and the reboot. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/redhat62-install-ss5.cast",
          caption: "Red Hat Linux 6.2 kickstart install, SS-5 with OpenBIOS under PVE, serial console",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/redhat62-boot-ss5.cast",
          caption: "Red Hat Linux 6.2 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install redhat62-ss5 --check",
      note: "about 6 minutes (lab-install.md)",
    },
  },
  {
    id: "freedos14-pc",
    machine: "pc",
    machineLabel: "x86 (i440fx)",
    os: "freedos14",
    osLabel: "FreeDOS 1.4",
    osFamily: "FreeDOS",
    blurb:
      "An x86 VM (i440fx, SeaBIOS, Pentium, std VGA, 32 MB, TCG): the FreeDOS 1.4 Floppy Edition " +
      "installer on the VGA text screen, partitioning (with a reboot), formatting and the six disk " +
      "swaps, which the lab does through the PVE API; then the check boot from the hard disk with " +
      "VER, the marker and MEM. A frame a second, played ten times faster; the captions are the " +
      "lab's steps.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "video",
          src: "/recordings/freedos14-install.webm",
          captions: "/recordings/freedos14-install.vtt",
          poster: "/recordings/freedos14-install-poster.png",
          width: 640,
          height: 480,
          caption:
            "FreeDOS 1.4 install from the Floppy Edition under PVE, VGA text screen (time-lapse, 10x)",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "video",
          src: "/recordings/freedos14-boot.webm",
          captions: "/recordings/freedos14-boot.vtt",
          poster: "/recordings/freedos14-boot-poster.png",
          width: 640,
          height: 480,
          caption: "FreeDOS 1.4 booting the installed disk under PVE (time-lapse, 10x)",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install freedos14 --check",
      note: "about 11 minutes; VGA console, no login password (lab-install.md; dos.md)",
    },
  },
];

export default scenarios;
