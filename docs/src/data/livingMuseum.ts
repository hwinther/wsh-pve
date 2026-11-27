// Data for the living museum picker (components/LivingMuseum.astro, guides/living-museum.mdx):
// demo idea 9 in ROADMAP.md ("pick a machine and OS ... and watch its install and first boot from
// the existing recordings"). Every fact here comes from one of these places: guides/sparc-recordings.mdx
// and guides/wisp.mdx (the recordings themselves), guides/dos.md, guides/lab-install.md or a README
// under e2e/ (the "Try it yourself" commands and timings). Add a scenario when sparc-recordings.mdx
// or wisp.mdx documents an install/boot pair (or a section/subsection with matching casts/videos) -
// that covers the sun4u-only boots (Solaris 9, Solaris 10, Tribblix m34: stored disks, no install
// stage recorded) and wisp's Mandelbrot cast on three machines (SS-5, sun4u, pc; no installer or
// guest OS, so tryIt is an e2e/wisp/README.md `run.py` command instead of `wsh-lab install`).
// The install targets recorded in the 2026-11-26 sweep (guides/lab-install.md, "Regression sweep")
// each have an install/boot pair; the five sun4m machines that never ran an install (SS-4,
// SPARCclassic, LX, Voyager, SPARCbook) have wisp-netbsd's boot instead (sparc-recordings.mdx,
// "wisp-netbsd on the other sun4m machines"; tryIt from e2e/wisp-netbsd/README.md).
// Alpine on aarch64, a VM Proxmox VE started directly rather than one of the lab's own install
// targets, has no tryIt at all. Left out on purpose: the NetBSD install CD on sparc64 under PVE in
// the same sparc-recordings.mdx section as Alpine, which only reaches the sysinst shell and has no
// matching first boot (see guides/living-museum.mdx, "Seeing more").
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
      {
        label: "Single user (cg3 framebuffer)",
        media: {
          kind: "video",
          src: "/recordings/sunos412-cg3-single-user-ss600mp.webm",
          captions: "/recordings/sunos412-cg3-single-user-ss600mp.vtt",
          poster: "/recordings/sunos412-cg3-single-user-ss600mp-poster.png",
          width: 1024,
          height: 768,
          caption:
            "SunOS 4.1.2 booting the installed disk to single user on a cg3 (1024x768), SPARCserver 600MP " +
            "with OpenBIOS in the lab's QEMU, then the bell test",
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
    id: "sunos412-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sunos412",
    osLabel: "SunOS 4.1.2",
    osFamily: "SunOS",
    blurb:
      "The same SunOS 4.1.2 install under Sun's own 600MP boot PROM (ss600mp.bin): the PROM stops at ok " +
      "on ttya, the lab types boot cdrom, the PROM boots the miniroot from its reboot string by itself, " +
      "and boot disk for the first boot and the check. One CPU, 256 MB in every phase.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sunos412-install-ss600mp-prom.cast",
          caption: "SunOS 4.1.2 install from CD, SPARCserver 600MP with the Sun PROM under PVE, serial console",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sunos412-boot-ss600mp-prom.cast",
          caption: "SunOS 4.1.2 booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sunos412-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0188 (lab-install.md); 6.5 " +
        "minutes in the run that made this recording (install 158 s, first boot 160 s, check 55 s)",
    },
  },
  {
    id: "sol21-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sol21",
    osLabel: "Solaris 2.1",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.1 (SunOS 5.1) End User, the install of sol21-ss10 unchanged, under Sun's 600MP PROM " +
      "(ss600mp.bin): the CD as a disk, boot cdrom and boot disk typed at the PROM's ok. Needs pve-qemu " +
      "patch wsh/0190 (the MXCC stream registers' RDY bit; without it the kernel hangs after its clock " +
      "warning). After init 5 the PROM reboots with -a and stops at the boot program's Enter filename " +
      "question, which ends each boot. One CPU, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol21-install-ss600mp-prom.cast",
          caption: "Solaris 2.1 install, SPARCserver 600MP with the Sun PROM under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol21-boot-ss600mp-prom.cast",
          caption: "Solaris 2.1 booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol21-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0190 (lab-install.md); 12.0 " +
        "minutes in the run that made this recording (install 342 s, first boot 272 s, check 89 s)",
    },
  },
  {
    id: "sol22-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sol22",
    osLabel: "Solaris 2.2",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.2 End User, the install of sol22-ss10 unchanged, under Sun's 600MP PROM (ss600mp.bin): " +
      "the CD as a disk, boot cdrom and boot disk typed at the PROM's ok. Needs pve-qemu patch wsh/0190 " +
      "(the MXCC stream registers' RDY bit; without it the kernel hangs after its clock warning). After " +
      "init 5 the PROM reboots with -a and stops at the boot program's Enter filename question, which " +
      "ends each boot. One CPU, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol22-install-ss600mp-prom.cast",
          caption: "Solaris 2.2 install, SPARCserver 600MP with the Sun PROM under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol22-boot-ss600mp-prom.cast",
          caption: "Solaris 2.2 booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol22-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0190 (lab-install.md); 8.7 " +
        "minutes in the run that made this recording (install 278 s, first boot 148 s, check 84 s)",
    },
  },
  {
    id: "sol23-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sol23",
    osLabel: "Solaris 2.3",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.3 Edition II End User, the install of sol23-ss5 unchanged, under Sun's 600MP PROM " +
      "(ss600mp.bin): the CD as a disk, boot cdrom and boot disk typed at the PROM's ok. Needs pve-qemu " +
      "patch wsh/0190 (the MXCC stream registers' RDY bit; without it the kernel hangs after its clock " +
      "warning). After init 5 the PROM reboots with -a and stops at the boot program's Enter filename " +
      "question, which ends each boot. One CPU, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol23-install-ss600mp-prom.cast",
          caption: "Solaris 2.3 Edition II install, SPARCserver 600MP with the Sun PROM under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol23-boot-ss600mp-prom.cast",
          caption: "Solaris 2.3 Edition II booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol23-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0190 (lab-install.md); 9.0 " +
        "minutes in the run that made this recording (install 291 s, first boot 151 s, check 86 s)",
    },
  },
  {
    id: "sol24-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sol24",
    osLabel: "Solaris 2.4",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.4 HW 3/95 End User, the install of sol24-ss5 unchanged, under Sun's 600MP PROM " +
      "(ss600mp.bin): the CD as a disk, boot cdrom and boot disk typed at the PROM's ok. Needs pve-qemu " +
      "patch wsh/0190 (the MXCC stream registers' RDY bit; without it the kernel hangs after its clock " +
      "warning). One CPU, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol24-install-ss600mp-prom.cast",
          caption: "Solaris 2.4 HW 3/95 install, SPARCserver 600MP with the Sun PROM under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol24-boot-ss600mp-prom.cast",
          caption: "Solaris 2.4 HW 3/95 booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol24-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0190 (lab-install.md); 7.6 " +
        "minutes in the run that made this recording (install 239 s, first boot 132 s, check 72 s)",
    },
  },
  {
    id: "sol25-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sol25",
    osLabel: "Solaris 2.5",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5 HW 1/96 End User, the install of sol25-ss5 unchanged, under Sun's 600MP PROM " +
      "(ss600mp.bin): the CD as a disk, boot cdrom and boot disk typed at the PROM's ok. Needs pve-qemu " +
      "patch wsh/0190 (the MXCC stream registers' RDY bit; without it the kernel hangs after its clock " +
      "warning). One CPU, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol25-install-ss600mp-prom.cast",
          caption: "Solaris 2.5 HW 1/96 install, SPARCserver 600MP with the Sun PROM under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol25-boot-ss600mp-prom.cast",
          caption: "Solaris 2.5 HW 1/96 booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol25-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0190 (lab-install.md); 8.8 " +
        "minutes in the run that made this recording (install 268 s, first boot 164 s, check 79 s)",
    },
  },
  {
    id: "sol251-ss600mp-prom",
    machine: "ss600mp-prom",
    machineLabel: "SPARCserver 600MP, Sun PROM",
    os: "sol251",
    osLabel: "Solaris 2.5.1",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5.1 11/97 End User, the install of sol251-ss5 unchanged (most of it the Maintenance " +
      "Update), under Sun's 600MP PROM (ss600mp.bin): the CD as a disk, boot cdrom and boot disk typed " +
      "at the PROM's ok. Needs pve-qemu patch wsh/0190 (the MXCC stream registers' RDY bit; without it " +
      "the kernel hangs after its clock warning). One CPU, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol251-install-ss600mp-prom.cast",
          caption: "Solaris 2.5.1 11/97 install, SPARCserver 600MP with the Sun PROM under PVE (4x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol251-boot-ss600mp-prom.cast",
          caption: "Solaris 2.5.1 11/97 booting the installed disk, SPARCserver 600MP with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol251-ss600mp-prom --check",
      note:
        "needs the 600MP PROM image in /usr/share/kvm and pve-qemu up to wsh/0190 (lab-install.md); 37.8 " +
        "minutes in the run that made this recording (install 1992 s, first boot 172 s, check 88 s)",
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
    osFamily: "Debian",
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
  {
    id: "sol23-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol23",
    osLabel: "Solaris 2.3",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.3 Edition II, the first release for the SS-5: the CD as a disk boots the installer, one system identification question per screen, Quick Install (End User). The check logs in, records uname (SunOS 5.3), the marker and df, and powers off. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol23-install-ss5.cast",
          caption: "Solaris 2.3 Edition II install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol23-boot-ss5.cast",
          caption: "Solaris 2.3 Edition II booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol23-ss5 --check",
      note: "about 10 minutes (lab-install.md)",
    },
  },
  {
    id: "sol23-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol23",
    osLabel: "Solaris 2.3",
    osFamily: "Solaris 2.x",
    blurb:
      "The same Solaris 2.3 Edition II Quick Install on the SS-20 (the SS-20 needs 2.3 or later). SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol23-install-ss20.cast",
          caption: "Solaris 2.3 Edition II install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol23-boot-ss20.cast",
          caption: "Solaris 2.3 Edition II booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol23-ss20 --check",
      note: "about 9 minutes (lab-install.md)",
    },
  },
  {
    id: "sol24-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol24",
    osLabel: "Solaris 2.4",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.4 HW 3/95 from the CD as a disk under OpenBIOS (patches 0019-0022): the End User install, with the 4-digit year typed over 2.4's 19xx. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol24-install-ss5.cast",
          caption: "Solaris 2.4 install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol24-boot-ss5.cast",
          caption: "Solaris 2.4 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol24-ss5 --check",
      note: "about 8 minutes (lab-install.md)",
    },
  },
  {
    id: "sol24-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol24",
    osLabel: "Solaris 2.4",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.4 HW 3/95 on the SS-20: the End User install from the CD as a disk, then the check boot. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol24-install-ss20.cast",
          caption: "Solaris 2.4 install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol24-boot-ss20.cast",
          caption: "Solaris 2.4 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol24-ss20 --check",
      note: "about 8 minutes (lab-install.md)",
    },
  },
  {
    id: "sol25-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol25",
    osLabel: "Solaris 2.5",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5 HW 1/96: the CD as a disk, then an End User install like 2.6's, without 2.5.1's Maintenance Update. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol25-install-ss5.cast",
          caption: "Solaris 2.5 install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol25-boot-ss5.cast",
          caption: "Solaris 2.5 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol25-ss5 --check",
      note: "about 9 minutes (lab-install.md)",
    },
  },
  {
    id: "sol25-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol25",
    osLabel: "Solaris 2.5",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5 HW 1/96 on the SS-20, End User from the CD as a disk. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol25-install-ss20.cast",
          caption: "Solaris 2.5 install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol25-boot-ss20.cast",
          caption: "Solaris 2.5 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol25-ss20 --check",
      note: "about 9 minutes (lab-install.md)",
    },
  },
  {
    id: "sol251-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol251",
    osLabel: "Solaris 2.5.1",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5.1 11/97 under the SPARCstation 5 PROM (ss5.bin): the End User install from the CD as a disk, then the CD's Maintenance Update, which takes most of the 35 minutes. SS-5, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol251-install-ss5.cast",
          caption: "Solaris 2.5.1 install, SS-5 with the Sun PROM under PVE (4x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol251-boot-ss5.cast",
          caption: "Solaris 2.5.1 booting the installed disk, SS-5 with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol251-ss5 --check",
      note: "about 45 minutes (lab-install.md)",
    },
  },
  {
    id: "sol251-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol251",
    osLabel: "Solaris 2.5.1",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5.1 11/97 on the SS-20, which needs no Sun PROM: OpenBIOS boots the CD (as a disk) and the installed system. End User plus the Maintenance Update. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol251-install-ss20.cast",
          caption: "Solaris 2.5.1 install, SS-20 with OpenBIOS under PVE (4x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol251-boot-ss20.cast",
          caption: "Solaris 2.5.1 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol251-ss20 --check",
      note: "about 47 minutes (lab-install.md)",
    },
  },
  {
    id: "sol26-ss10",
    machine: "ss10",
    machineLabel: "SPARCstation 10 (SS-10)",
    os: "sol26",
    osLabel: "Solaris 2.6",
    osFamily: "Solaris 2.x",
    blurb:
      "The SS-20's Solaris 2.6 5/98 End User install unchanged on QEMU's SS-10. SS-10, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol26-install-ss10.cast",
          caption: "Solaris 2.6 install, SS-10 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol26-boot-ss10.cast",
          caption: "Solaris 2.6 booting the installed disk, SS-10 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol26-ss10 --check",
      note: "about 16 minutes (lab-install.md)",
    },
  },
  {
    id: "sol7-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol7",
    osLabel: "Solaris 7",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 7 3/99 with suninstall: 2.6's questions plus Subnets and Select 64 Bit (no), End User on the 3G disk. The check boots to SunOS 5.7. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol7-install-ss5.cast",
          caption: "Solaris 7 install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol7-boot-ss5.cast",
          caption: "Solaris 7 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol7-ss5 --check",
      note: "about 11 minutes (lab-install.md)",
    },
  },
  {
    id: "sol7-ss10",
    machine: "ss10",
    machineLabel: "SPARCstation 10 (SS-10)",
    os: "sol7",
    osLabel: "Solaris 7",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 7 3/99 on the SS-10, the same suninstall answers as on the SS-5 and SS-20. SS-10, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol7-install-ss10.cast",
          caption: "Solaris 7 install, SS-10 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol7-boot-ss10.cast",
          caption: "Solaris 7 booting the installed disk, SS-10 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol7-ss10 --check",
      note: "about 12 minutes (lab-install.md)",
    },
  },
  {
    id: "sol7-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol7",
    osLabel: "Solaris 7",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 7 3/99 on the SS-20 with suninstall, End User. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol7-install-ss20.cast",
          caption: "Solaris 7 install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol7-boot-ss20.cast",
          caption: "Solaris 7 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol7-ss20 --check",
      note: "about 10 minutes (lab-install.md)",
    },
  },
  {
    id: "sol251-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "sol251",
    osLabel: "Solaris 2.5.1",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.5.1 11/97 (the Ultra 5/10 media) on sparc64: suninstall on a Sun-labelled IDE disk, a 32-bit kernel, the Maintenance Update as on sun4m; needs OpenBIOS patches 0036-0039. sun4u, OpenBIOS, 1024 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol251-install-sun4u.cast",
          caption: "Solaris 2.5.1 install, sun4u with OpenBIOS under PVE (6x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol251-boot-sun4u.cast",
          caption: "Solaris 2.5.1 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol251-sun4u --check",
      note: "about 67 minutes (lab-install.md)",
    },
  },
  {
    id: "sol26-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "sol26",
    osLabel: "Solaris 2.6",
    osFamily: "Solaris 2.x",
    blurb:
      "Solaris 2.6 5/98 on sparc64: suninstall with the sun4m answers and a static address on hme0, a 32-bit kernel; needs OpenBIOS patches 0036-0039. sun4u, OpenBIOS, 1024 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol26-install-sun4u.cast",
          caption: "Solaris 2.6 install, sun4u with OpenBIOS under PVE (3x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol26-boot-sun4u.cast",
          caption: "Solaris 2.6 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol26-sun4u --check",
      note: "about 28 minutes (lab-install.md)",
    },
  },
  {
    id: "sol7-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "sol7",
    osLabel: "Solaris 7",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 7 3/99 on sparc64: suninstall with the 64-bit support it selects on sun4u, End User on a Sun-labelled IDE disk. sun4u, OpenBIOS, 2048 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol7-install-sun4u.cast",
          caption: "Solaris 7 install, sun4u with OpenBIOS under PVE (3x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol7-boot-sun4u.cast",
          caption: "Solaris 7 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol7-sun4u --check",
      note: "about 25 minutes (lab-install.md)",
    },
  },
  {
    id: "sunos414-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sunos414",
    osLabel: "SunOS 4.1.4",
    osFamily: "SunOS",
    blurb:
      "SunOS 4.1.4 (Solaris 1.1.2), the last SunOS 4: the CD (converted from its raw BIN image) copies its miniroot to the swap slice, then suninstall's Quick install (Programmer). SS-5, OpenBIOS, 64 MB for the install, 256 MB after.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sunos414-install-ss5.cast",
          caption: "SunOS 4.1.4 install, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sunos414-boot-ss5.cast",
          caption: "SunOS 4.1.4 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sunos414-ss5 --check",
      note: "about 6 minutes (lab-install.md)",
    },
  },
  {
    id: "sunos413u1b-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sunos413u1b",
    osLabel: "SunOS 4.1.3_U1B",
    osFamily: "SunOS",
    blurb:
      "SunOS 4.1.3_U1B (Solaris 1.1.1B) on the SS-20: the miniroot, suninstall's Quick install, sys-config at the first boot. SS-20, OpenBIOS, 64 MB for the install, 512 MB after, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sunos413u1b-install-ss20.cast",
          caption: "SunOS 4.1.3_U1B install, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sunos413u1b-boot-ss20.cast",
          caption: "SunOS 4.1.3_U1B booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sunos413u1b-ss20 --check",
      note: "about 6 minutes (lab-install.md)",
    },
  },
  {
    id: "netbsd111-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "netbsd111",
    osLabel: "NetBSD 11.1",
    osFamily: "NetBSD",
    blurb:
      "sysinst from the NetBSD 11.1 sparc CD on the SS-20: the microroot loads the installer, the Minimal set on a blank disk. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/netbsd111-install-ss20.cast",
          caption: "NetBSD 11.1 sparc install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/netbsd111-boot-ss20.cast",
          caption: "NetBSD 11.1 sparc booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install netbsd111-sparc-ss20 --check",
      note: "about 7 minutes (lab-install.md)",
    },
  },
  {
    id: "netbsd111-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "netbsd111",
    osLabel: "NetBSD 11.1",
    osFamily: "NetBSD",
    blurb:
      "sysinst from the NetBSD 11.1 sparc64 CD: the sets without X11 on the IDE disk; the check boots to NetBSD 11.1 (GENERIC). sun4u, OpenBIOS, 512 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/netbsd111-install-sun4u.cast",
          caption: "NetBSD 11.1 sparc64 install, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/netbsd111-boot-sun4u.cast",
          caption: "NetBSD 11.1 sparc64 booting the installed disk, sun4u with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install netbsd111-sparc64 --check",
      note: "about 11 minutes (lab-install.md)",
    },
  },
  {
    id: "netbsd93-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "netbsd93",
    osLabel: "NetBSD 9.3",
    osFamily: "NetBSD",
    blurb:
      "NetBSD 9.3's sysinst, which goes straight to its configuration menu after the sets (root's password is set at the first boot). Minimal set. SS-5, OpenBIOS, 256 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/netbsd93-install-ss5.cast",
          caption: "NetBSD 9.3 sparc install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/netbsd93-boot-ss5.cast",
          caption: "NetBSD 9.3 sparc booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install netbsd93-sparc --check",
      note: "about 7 minutes (lab-install.md)",
    },
  },
  {
    id: "netbsd93-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "netbsd93",
    osLabel: "NetBSD 9.3",
    osFamily: "NetBSD",
    blurb:
      "NetBSD 9.3 sparc, Minimal, on the SS-20. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/netbsd93-install-ss20.cast",
          caption: "NetBSD 9.3 sparc install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/netbsd93-boot-ss20.cast",
          caption: "NetBSD 9.3 sparc booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install netbsd93-sparc-ss20 --check",
      note: "about 6 minutes (lab-install.md)",
    },
  },
  {
    id: "netbsd93-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "netbsd93",
    osLabel: "NetBSD 9.3",
    osFamily: "NetBSD",
    blurb:
      "NetBSD 9.3 sparc64, the sets without X11 on the IDE disk; the check boots to NetBSD 9.3 (GENERIC). sun4u, OpenBIOS, 512 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/netbsd93-install-sun4u.cast",
          caption: "NetBSD 9.3 sparc64 install, sun4u with OpenBIOS under PVE (4x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/netbsd93-boot-sun4u.cast",
          caption: "NetBSD 9.3 sparc64 booting the installed disk, sun4u with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install netbsd93-sparc64 --check",
      note: "about 18 minutes (lab-install.md)",
    },
  },
  {
    id: "openbsd59-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "openbsd59",
    osLabel: "OpenBSD 5.9",
    osFamily: "OpenBSD",
    blurb:
      "OpenBSD 5.9, the last sparc release, on the SS-20: bsd.rd from cd59.iso, the sets from a second CD checked against SHA256.sig. One CPU: OpenBSD/sparc has no multiprocessor kernel. SS-20, OpenBIOS, 512 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/openbsd59-install-ss20.cast",
          caption: "OpenBSD 5.9 sparc install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/openbsd59-boot-ss20.cast",
          caption: "OpenBSD 5.9 sparc booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install openbsd59-ss20 --check",
      note: "about 10 minutes (lab-install.md)",
    },
  },
  {
    id: "freebsd124-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "freebsd124",
    osLabel: "FreeBSD 12.4",
    osFamily: "FreeBSD",
    blurb:
      "FreeBSD 12.4, the last release with sparc64: bsdinstall's unattended script mode (VTOC8 auto layout, kernel and base from the CD, sshd on); the check boots to 12.4-RELEASE and powers off. sun4u, OpenBIOS, 512 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/freebsd124-install-sun4u.cast",
          caption: "FreeBSD 12.4 sparc64 install, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/freebsd124-boot-sun4u.cast",
          caption: "FreeBSD 12.4 sparc64 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install freebsd124-sun4u --check",
      note: "about 16 minutes (lab-install.md)",
    },
  },
  {
    id: "redhat62-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "redhat62",
    osLabel: "Red Hat Linux 6.2",
    osFamily: "Red Hat 6.2",
    blurb:
      "Red Hat Linux 6.2 by kickstart from an answer CD made on the node; the lab types only SILO's three screens. The check boots Linux 2.2.14 from the disk. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/redhat62-install-ss20.cast",
          caption: "Red Hat Linux 6.2 kickstart install, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/redhat62-boot-ss20.cast",
          caption: "Red Hat Linux 6.2 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install redhat62-ss20 --check",
      note: "about 5 minutes (lab-install.md)",
    },
  },
  {
    id: "debian40-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "debian40",
    osLabel: "Debian GNU/Linux 4.0 (etch)",
    osFamily: "Debian",
    blurb:
      "Debian 4.0 etch from the netinst CD with a preseed file; the base system and the kernel come from archive.debian.org, so the VM needs a route out. The check boots Linux 2.6.18. SS-20, OpenBIOS, 512 MB, one CPU.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/debian40-install-ss20.cast",
          caption: "Debian 4.0 (etch) preseeded netinst install, SS-20 with OpenBIOS under PVE (4x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/debian40-boot-ss20.cast",
          caption: "Debian 4.0 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install debian40-ss20 --gateway <gw> --dns <dns> --check",
      note: "about 17-21 minutes; needs a router and DNS that reach archive.debian.org (lab-install.md)",
    },
  },
  {
    id: "debian7-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "debian7",
    osLabel: "Debian GNU/Linux 7.11 (wheezy)",
    osFamily: "Debian",
    blurb:
      "Debian 7.11 wheezy, the last official Debian release for sparc, preseeded from CD 1 alone (nothing fetched): the base system with the OpenSSH server, SILO, Linux 3.2. sun4u, OpenBIOS, 512 MB.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/debian7-install-sun4u.cast",
          caption: "Debian 7.11 (wheezy) preseeded install, sun4u with OpenBIOS under PVE (4x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/debian7-boot-sun4u.cast",
          caption: "Debian 7.11 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install debian7-sun4u --check",
      note: "about 69 minutes (lab-install.md)",
    },
  },
  {
    id: "sol8-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol8",
    osLabel: "Solaris 8",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 8 2/02, Entire Group, installed by Web Start from the Installation CD and two Software CDs, swapped through the PVE API when the installer asks; the install boots the mini-root at the firmware prompt itself (auto-boot? off while it runs). The check boots to SunOS 5.8. SS-5, OpenBIOS, 256 MB, 9G disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol8-install-ss5.cast",
          caption: "Solaris 8 2/02 Web Start install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol8-boot-ss5.cast",
          caption: "Solaris 8 2/02 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol8-ss5 --check",
      note: "about 37 minutes (lab-install.md)",
    },
  },
  {
    id: "sol8-ss5-prom",
    machine: "ss5-prom",
    machineLabel: "SPARCstation 5 (SS-5), Sun PROM",
    os: "sol8",
    osLabel: "Solaris 8",
    osFamily: "Solaris 7-10",
    blurb:
      "The same Solaris 8 2/02 Web Start install under the SPARCstation 5 PROM (ss5.bin), which boots the mini-root from Web Start's boot string by itself. SS-5, 256 MB, 9G disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol8-install-ss5-prom.cast",
          caption: "Solaris 8 2/02 Web Start install, SS-5 with the Sun PROM under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol8-boot-ss5-prom.cast",
          caption: "Solaris 8 2/02 booting the installed disk, SS-5 with the Sun PROM under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol8-ss5-prom --check",
      note: "about 47 minutes (lab-install.md)",
    },
  },
  {
    id: "sol8-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol8",
    osLabel: "Solaris 8",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 8 1/01, Entire Group, by Web Start from three CDs swapped by the install. SS-20, OpenBIOS, 512 MB, one CPU, 9G disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol8-install-ss20.cast",
          caption: "Solaris 8 1/01 Web Start install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol8-boot-ss20.cast",
          caption: "Solaris 8 1/01 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol8-ss20 --check",
      note: "about 30 minutes (lab-install.md)",
    },
  },
  {
    id: "sol9-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "sol9",
    osLabel: "Solaris 9",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 9 9/05, End User, by Web Start from the DVD: Solaris 9 is the last release for sun4m, and its installer and 32-bit kernel run on the emulated SS-5. SS-5, OpenBIOS, 256 MB, 9G disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol9-install-ss5.cast",
          caption: "Solaris 9 9/05 Web Start install, SS-5 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol9-boot-ss5.cast",
          caption: "Solaris 9 9/05 booting the installed disk, SS-5 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol9-ss5 --check",
      note: "about 30 minutes (lab-install.md)",
    },
  },
  {
    id: "sol9-ss20",
    machine: "ss20",
    machineLabel: "SPARCstation 20 (SS-20)",
    os: "sol9",
    osLabel: "Solaris 9",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 9, End User, by Web Start from the DVD on the SS-20. SS-20, OpenBIOS, 512 MB, one CPU, 9G disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol9-install-ss20.cast",
          caption: "Solaris 9 Web Start install, SS-20 with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol9-boot-ss20.cast",
          caption: "Solaris 9 booting the installed disk, SS-20 with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol9-ss20 --check",
      note: "about 27 minutes (lab-install.md)",
    },
  },
  {
    id: "sol8-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "sol8",
    osLabel: "Solaris 8",
    osFamily: "Solaris 7-10",
    blurb:
      "Solaris 8 2/02's Web Start on sparc64: the Installation CD copies a mini-root to the disk, the lab boots it at the firmware prompt, then End User with 64-bit support from Software 1 of 2. sun4u, OpenBIOS, 1024 MB, IDE disk.",
    stages: [
      {
        label: "Install",
        media: {
          kind: "cast",
          src: "/recordings/sol8-install-sun4u.cast",
          caption: "Solaris 8 2/02 Web Start install, sun4u with OpenBIOS under PVE (3x)",
          poster: "npt:0:10",
        },
      },
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol8-boot-sun4u.cast",
          caption: "Solaris 8 2/02 booting the installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol8-sun4u --check",
      note: "about 55 minutes (lab-install.md)",
    },
  },
  {
    id: "sol9-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "sol9",
    osLabel: "Solaris 9",
    osFamily: "Solaris 7-10",
    blurb:
      "A boot of the stored Solaris 9 9/05 disk, installed by Web Start from the DVD: OpenBIOS " +
      "for sparc64, the kernel, the services, login, uname, the marker, df, prtvtoc, ifconfig, " +
      "netstat -rn and init 5. sun4u, OpenBIOS, 1024 MB, IDE disk.",
    stages: [
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol9-boot-sun4u.cast",
          caption: "Solaris 9 9/05 booting an installed disk, sun4u with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol9-sun4u --check",
      note:
        "about 70 minutes for the Web Start install; needs pve-qemu-kvm 11.1.3-2+wsh25 or later " +
        "(OpenBIOS patches 0024 and 0025; lab-install.md)",
    },
  },
  {
    id: "sol10-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "sol10",
    osLabel: "Solaris 10",
    osFamily: "Solaris 7-10",
    blurb:
      "A boot of the stored Solaris 10 1/13 disk, installed by the text installer: OpenBIOS for " +
      "sparc64, the kernel, the services, login, uname/prtconf/df/ifconfig and init 5. sun4u, " +
      "OpenBIOS, 1024 MB, IDE disk.",
    stages: [
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/sol10-boot-sun4u.cast",
          caption: "Solaris 10 1/13 booting an installed disk, sun4u with OpenBIOS under PVE",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install sol10-sun4u --check",
      note: "about 110 minutes; needs pve-qemu-kvm 11.1.3-2+wsh13 or later (lab-install.md)",
    },
  },
  {
    id: "tribblix-m34-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "tribblix-m34",
    osLabel: "Tribblix m34 (illumos)",
    osFamily: "illumos",
    blurb:
      "A boot of the stored Tribblix m34 disk, installed by the live CD's own installer onto a ZFS " +
      "root: OpenBIOS, the illumos kernel, the SMF services, login, the system state and init 5. " +
      "The run takes about 29 minutes under TCG, most of it pauses, which are cut; it plays at 2x. " +
      "sun4u, OpenBIOS, 2048 MB, IDE disk.",
    stages: [
      {
        label: "First boot",
        media: {
          kind: "cast",
          src: "/recordings/tribblix-m34-boot-sun4u.cast",
          caption: "Tribblix m34 (illumos) booting an installed disk, sun4u with OpenBIOS under PVE (2x)",
          poster: "npt:0:10",
        },
      },
    ],
    tryIt: {
      command: "wsh-lab install tribblix-m34-sun4u --check",
      note:
        "about 4.3 hours for the install (its login prompt alone takes 45-70 minutes importing " +
        "service descriptions); the weekly lab matrix boot-tests a stored disk instead of " +
        "reinstalling every run (lab-install.md)",
    },
  },
  {
    id: "alpine319-aarch64",
    machine: "aarch64",
    machineLabel: "aarch64 (virt)",
    os: "alpine319",
    osLabel: "Alpine Linux 3.19",
    osFamily: "Alpine",
    blurb:
      "Not one of the sparc lab's install targets: a VM created through the Proxmox VE API and " +
      "started by qm start, with the lab attached to its serial socket (attach mode) instead of " +
      "driving an install. Alpine Linux 3.19 on aarch64 (the virt machine, AAVMF firmware) booting " +
      "to a root shell.",
    stages: [
      {
        label: "Boot",
        media: {
          kind: "cast",
          src: "/recordings/alpine-aarch64-pve.cast",
          caption: "Alpine Linux 3.19 on aarch64 (virt, AAVMF) under PVE, to a root shell",
          poster: "npt:0:8",
        },
      },
    ],
  },
  {
    id: "wisp-ss5",
    machine: "ss5",
    machineLabel: "SPARCstation 5 (SS-5)",
    os: "wisp",
    osLabel: "wisp (test kernel)",
    osFamily: "wisp",
    blurb:
      "wisp, the sparc lab's tiny nolibc test kernel (e2e/wisp/), booted directly with QEMU's " +
      "-kernel: no disk, no installer, no guest OS. Its interactive shell's mandel draws an ASCII " +
      "Mandelbrot set in fixed-point integer math, then poweroff shuts it down, all in real time. " +
      "SS-5, OpenBIOS, serial console, 128 MB: the prompt comes up after 2.2 s and mandel itself " +
      "takes 97 ms.",
    stages: [
      {
        label: "Boot, mandel, poweroff",
        media: {
          kind: "cast",
          src: "/recordings/wisp-mandel-ss5.cast",
          caption: "wisp's shell on sparc32: boot, mandel, poweroff (SS-5, OpenBIOS, serial console)",
          poster: "npt:0:3.8",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch sparc32 --shell',
      note: "the prompt after 2.2 s, mandel in 97 ms, power-off by 4-5 s (e2e/wisp/README.md)",
    },
  },
  {
    id: "wisp-sun4u",
    machine: "sun4u",
    machineLabel: "sun4u (sparc64)",
    os: "wisp",
    osLabel: "wisp (test kernel)",
    osFamily: "wisp",
    blurb:
      "The same wisp test kernel on sparc64: boot, mandel, poweroff, in real time. sun4u, " +
      "OpenBIOS, serial console, 256 MB: the prompt comes up after 2.2 s and mandel itself takes " +
      "13 ms.",
    stages: [
      {
        label: "Boot, mandel, poweroff",
        media: {
          kind: "cast",
          src: "/recordings/wisp-mandel-sun4u.cast",
          caption: "wisp's shell on sparc64: boot, mandel, poweroff (sun4u, OpenBIOS, serial console)",
          poster: "npt:0:3.7",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch sparc64 --shell',
      note: "the prompt after 2.2 s, mandel in 13 ms, power-off by 4-5 s (e2e/wisp/README.md)",
    },
  },
  {
    id: "wisp-pc",
    machine: "pc",
    machineLabel: "x86 (i440fx)",
    os: "wisp",
    osLabel: "wisp (test kernel)",
    osFamily: "wisp",
    blurb:
      "The same wisp test kernel on x86_64: boot, mandel, poweroff, in real time. pc (i440fx), " +
      "SeaBIOS, serial console, 128 MB: the prompt comes up after 1.3 s and mandel itself takes " +
      "6 ms.",
    stages: [
      {
        label: "Boot, mandel, poweroff",
        media: {
          kind: "cast",
          src: "/recordings/wisp-mandel-pc.cast",
          caption: "wisp's shell on x86_64: boot, mandel, poweroff (pc, SeaBIOS, serial console)",
          poster: "npt:0:3.0",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp:/wisp" wsh-wisp ./run.py --arch x86_64 --shell',
      note: "the prompt after 1.3 s, mandel in 6 ms, power-off by 4-5 s (e2e/wisp/README.md)",
    },
  },
  {
    id: "wisp-netbsd-ss4",
    machine: "ss4",
    machineLabel: "SPARCstation 4 (SS-4)",
    os: "wisp-netbsd",
    osLabel: "wisp-netbsd (NetBSD 11.1 test kernel)",
    osFamily: "wisp",
    blurb:
      "wisp-netbsd, wisp's NetBSD sibling (e2e/wisp-netbsd/): a small NetBSD 11.1 kernel with a " +
      "memory-disk root whose only program is PID 1, booted with QEMU's -kernel on the SPARCstation 4 (SS-4) " +
      "(QEMU's SS-4 machine, OpenBIOS, serial console, 128 MB). OpenBIOS's SBus probe, NetBSD's " +
      "autoconfiguration, then PID 1's markers, a clock check, a file check and wisp's compute loop, " +
      "and the power-off, all in real time: the kernel's banner after 1.9 s, power-off after 2.9 s.",
    stages: [
      {
        label: "Boot to power-off",
        media: {
          kind: "cast",
          src: "/recordings/wisp-netbsd-ss4.cast",
          caption: "wisp-netbsd (NetBSD 11.1) on the SPARCstation 4 (SS-4): OpenBIOS to power-off, serial console",
          poster: "npt:0:2.9",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out:ro" wsh-wisp-netbsd ./run.py --arch sparc32 --machine SS-4',
      note: "after build.sh sparc32; power-off after about 2.3 s on an idle host (e2e/wisp-netbsd/README.md)",
    },
  },
  {
    id: "wisp-netbsd-classic",
    machine: "classic",
    machineLabel: "SPARCclassic",
    os: "wisp-netbsd",
    osLabel: "wisp-netbsd (NetBSD 11.1 test kernel)",
    osFamily: "wisp",
    blurb:
      "wisp-netbsd, wisp's NetBSD sibling (e2e/wisp-netbsd/): a small NetBSD 11.1 kernel with a " +
      "memory-disk root whose only program is PID 1, booted with QEMU's -kernel on the SPARCclassic " +
      "(QEMU's SPARCClassic machine, OpenBIOS, serial console, 128 MB). OpenBIOS's SBus probe, NetBSD's " +
      "autoconfiguration, then PID 1's markers, a clock check, a file check and wisp's compute loop, " +
      "and the power-off, all in real time: the kernel's banner after 1.6 s, power-off after 2.5 s.",
    stages: [
      {
        label: "Boot to power-off",
        media: {
          kind: "cast",
          src: "/recordings/wisp-netbsd-classic.cast",
          caption: "wisp-netbsd (NetBSD 11.1) on the SPARCclassic: OpenBIOS to power-off, serial console",
          poster: "npt:0:2.5",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out:ro" wsh-wisp-netbsd ./run.py --arch sparc32 --machine SPARCClassic',
      note: "after build.sh sparc32; power-off after about 2.3 s on an idle host (e2e/wisp-netbsd/README.md)",
    },
  },
  {
    id: "wisp-netbsd-lx",
    machine: "lx",
    machineLabel: "SPARCstation LX",
    os: "wisp-netbsd",
    osLabel: "wisp-netbsd (NetBSD 11.1 test kernel)",
    osFamily: "wisp",
    blurb:
      "wisp-netbsd, wisp's NetBSD sibling (e2e/wisp-netbsd/): a small NetBSD 11.1 kernel with a " +
      "memory-disk root whose only program is PID 1, booted with QEMU's -kernel on the SPARCstation LX " +
      "(QEMU's LX machine, OpenBIOS, serial console, 128 MB). OpenBIOS's SBus probe, NetBSD's " +
      "autoconfiguration, then PID 1's markers, a clock check, a file check and wisp's compute loop, " +
      "and the power-off, all in real time: the kernel's banner after 1.5 s, power-off after 2.5 s.",
    stages: [
      {
        label: "Boot to power-off",
        media: {
          kind: "cast",
          src: "/recordings/wisp-netbsd-lx.cast",
          caption: "wisp-netbsd (NetBSD 11.1) on the SPARCstation LX: OpenBIOS to power-off, serial console",
          poster: "npt:0:2.5",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out:ro" wsh-wisp-netbsd ./run.py --arch sparc32 --machine LX',
      note: "after build.sh sparc32; power-off after about 2.3 s on an idle host (e2e/wisp-netbsd/README.md)",
    },
  },
  {
    id: "wisp-netbsd-voyager",
    machine: "voyager",
    machineLabel: "SPARCstation Voyager",
    os: "wisp-netbsd",
    osLabel: "wisp-netbsd (NetBSD 11.1 test kernel)",
    osFamily: "wisp",
    blurb:
      "wisp-netbsd, wisp's NetBSD sibling (e2e/wisp-netbsd/): a small NetBSD 11.1 kernel with a " +
      "memory-disk root whose only program is PID 1, booted with QEMU's -kernel on the SPARCstation Voyager " +
      "(QEMU's Voyager machine, OpenBIOS, serial console, 128 MB). OpenBIOS's SBus probe, NetBSD's " +
      "autoconfiguration, then PID 1's markers, a clock check, a file check and wisp's compute loop, " +
      "and the power-off, all in real time: the kernel's banner after 1.4 s, power-off after 2.4 s.",
    stages: [
      {
        label: "Boot to power-off",
        media: {
          kind: "cast",
          src: "/recordings/wisp-netbsd-voyager.cast",
          caption: "wisp-netbsd (NetBSD 11.1) on the SPARCstation Voyager: OpenBIOS to power-off, serial console",
          poster: "npt:0:2.4",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out:ro" wsh-wisp-netbsd ./run.py --arch sparc32 --machine Voyager',
      note: "after build.sh sparc32; power-off after about 2.3 s on an idle host (e2e/wisp-netbsd/README.md)",
    },
  },
  {
    id: "wisp-netbsd-sparcbook",
    machine: "sparcbook",
    machineLabel: "SPARCbook",
    os: "wisp-netbsd",
    osLabel: "wisp-netbsd (NetBSD 11.1 test kernel)",
    osFamily: "wisp",
    blurb:
      "wisp-netbsd, wisp's NetBSD sibling (e2e/wisp-netbsd/): a small NetBSD 11.1 kernel with a " +
      "memory-disk root whose only program is PID 1, booted with QEMU's -kernel on the SPARCbook " +
      "(QEMU's SPARCbook machine, OpenBIOS, serial console, 128 MB). OpenBIOS's SBus probe, NetBSD's " +
      "autoconfiguration, then PID 1's markers, a clock check, a file check and wisp's compute loop, " +
      "and the power-off, all in real time: the kernel's banner after 1.5 s, power-off after 2.4 s.",
    stages: [
      {
        label: "Boot to power-off",
        media: {
          kind: "cast",
          src: "/recordings/wisp-netbsd-sparcbook.cast",
          caption: "wisp-netbsd (NetBSD 11.1) on the SPARCbook: OpenBIOS to power-off, serial console",
          poster: "npt:0:2.4",
        },
      },
    ],
    tryIt: {
      command:
        'docker run --rm -v "$PWD/e2e/wisp-netbsd/out:/wisp-netbsd/out:ro" wsh-wisp-netbsd ./run.py --arch sparc32 --machine SPARCbook',
      note: "after build.sh sparc32; power-off after about 2.3 s on an idle host (e2e/wisp-netbsd/README.md)",
    },
  },
];

export default scenarios;
