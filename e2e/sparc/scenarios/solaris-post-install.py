"""The post-install boot of an installed Solaris (`lab.py install --post-install <bundle>`, after the
first boot): checks that BASEDIR is the data disk, mounts the bundle's CD (in its own CD-ROM drive
for this phase only), adds every SVR4 package datastream in its DIR with `pkgadd -n` and an admin
file that answers every question, logs each package, optionally sets up the user's environment
(LOCAL_ENV), and shuts down with `init 5`.

    lab.py run scenarios/solaris-post-install.py --pve 120 --out /root/runs/post \
        --var ROOT_PASSWORD=wshlab --var BUNDLE=sun26gnu --var CD=c0t5d0 --var DIR=gnu/pkgs \
        --var DATA_DISK=c0t4d0 --var BASEDIR=/usr/local

  ROOT_PASSWORD  root's password                                                     (none)
  BUNDLE         the bundle's name (install.POST_INSTALL): the log, the package list  (none)
  CD             the CD-ROM with the bundle, as Solaris names it (scsi5: c0t5d0)       (none)
  DIR            the directory on the CD with the datastreams                         (none)
  DATA_DISK      the data disk (c0t4d0): BASEDIR must be its slice 0 in `df -k`         (none)
  BASEDIR        where the packages go (their BASEDIR; the admin file keeps it)        (/usr/local)
  USER           with LOCAL_ENV: the user whose dotfiles and login shell change       (none)
  LOCAL_ENV      1: /etc/profile and the user's ~/.profile get BASEDIR/bin and sbin   (none)
                 (after the system's directories) and MANPATH, the user's login
                 shell becomes LOGIN_SHELL. Root's stays /sbin/sh: root must be able
                 to log in single-user, when BASEDIR (the data disk) isn't mounted
  LOGIN_SHELL    the user's login shell with LOCAL_ENV                                (none)

What it leaves in the guest: /var/sadm/wsh-lab-BUNDLE.log (pkgadd's output), /etc/wsh-lab-BUNDLE.pkgs
(the package instances it added, which --check looks up with pkginfo) and /var/sadm/wsh-lab-admin
(the admin file). The run fails if a package fails or none was added. The packages come from the
CD only; nothing from it is copied into the evidence beyond the console output.
"""
import re

from _sparc32 import DEFAULTS as BASE, login, power_off, prom_boot, qemu_args as sparc32_args

DEFAULTS = {**BASE, "VGA": "none", "BOOT": "c", "NO_CD": "1", "ROOT_PASSWORD": "", "BUNDLE": "", "CD": "",
            "DIR": "", "DATA_DISK": "", "BASEDIR": "/usr/local", "USER": "", "LOCAL_ENV": "", "LOGIN_SHELL": ""}
ADMIN = "/var/sadm/wsh-lab-admin"
# pkgadd -a: nothing is asked; the packages go where their BASEDIR says (basedir=default)
ADMIN_LINES = ["mail=", "instance=overwrite", "partial=nocheck", "runlevel=nocheck", "idepend=nocheck",
               "rdepend=nocheck", "space=nocheck", "setuid=nocheck", "conflict=nocheck", "action=nocheck",
               "basedir=default"]


def qemu_args(v, out):
    return sparc32_args(v, out)


def shell(m, command, timeout=120):
    """Run a command at the root prompt and wait for the prompt after it."""
    m.send(command + "\r")
    m.expect(r"\n#\s*$", timeout)


def write_file(m, path, lines):
    """`path` with these lines, typed as a here-document with a quoted delimiter (nothing expanded),
    one line at a time at the shell's `> ` prompt (each under the tty's 256-character line)."""
    for line in lines:
        if len(line) > 200 or line == "WSH_EOF":
            raise ValueError(f"line for {path}: {line!r}")
    m.send(f"cat > {path} <<'WSH_EOF'\r")
    for line in lines:
        m.expect(r"\n> $", 30)
        m.send(line + "\r")
    m.expect(r"\n> $", 30)
    m.send("WSH_EOF\r")
    m.expect(r"\n#\s*$", 60)


def pkgadd_script(v):
    """The script that adds every datastream in /mnt/DIR, one line per package on the console."""
    b = v["BUNDLE"]
    return [
        f"L=/var/sadm/wsh-lab-{b}.log; P=/etc/wsh-lab-{b}.pkgs",
        "ok=0; bad=0; : > $L; : > $P",
        f"for d in /mnt/{v['DIR']}/*; do",
        "  set -- `pkginfo -d $d 2>/dev/null`; p=${2:-?}",
        f"  echo \"=== $d ($p)\" >> $L",
        f"  pkgadd -n -a {ADMIN} -d $d all >> $L 2>&1; rc=$?",
        "  if [ $rc -eq 0 -o $rc -eq 10 -o $rc -eq 20 ]; then",
        "    ok=`expr $ok + 1`; echo $p >> $P; echo \"pkgadd ok: $p\"",
        "  else",
        "    bad=`expr $bad + 1`; echo \"pkgadd FAILED (exit $rc): $p from `basename $d`\"",
        "  fi",
        "done",
        f"echo \"post-install {b}: $ok installed, $bad failed\"",
    ]


def run(m, v):
    for k in ("BUNDLE", "CD", "DIR", "DATA_DISK"):
        if not v[k]:
            raise ValueError(f"{k} is required")
    base = v["BASEDIR"]
    prom_boot(m, v, "disk")
    m.expect(r"SunOS Release", 600)
    m.snap("kernel banner")
    login(m, password=v["ROOT_PASSWORD"])
    # BASEDIR must be the data disk, mounted at boot from /etc/vfstab (the first boot put it there)
    m.send(f"df -k {base} | tail -1 | sed 's/^/df: /'\r")
    m.expect(rf"df: /dev/dsk/{v['DATA_DISK']}s0\s.*\s{base}[ \t]*$", 60)
    m.expect(r"\n#\s*$", 60)
    m.snap(f"{base} is the data disk")
    # the CD-ROM added for this phase: its device nodes, and vold stopped so it doesn't take the CD
    shell(m, "drvconfig; disks", 300)
    shell(m, "/etc/init.d/volmgt stop; sleep 2; ps -e | grep vold", 120)
    shell(m, f"mount -F hsfs -o ro /dev/dsk/{v['CD']}s0 /mnt && ls /mnt/{v['DIR']} | wc -l", 120)
    m.send(f"ls -d /mnt/{v['DIR']}/* >/dev/null 2>&1 && echo cd-mounted-ok\r")
    m.expect(r"(?m)^cd-mounted-ok", 60)
    m.expect(r"\n#\s*$", 60)
    m.snap("bundle CD mounted")
    write_file(m, ADMIN, ADMIN_LINES)
    write_file(m, "/tmp/wsh-pkgadd.sh", pkgadd_script(v))
    m.send("sh /tmp/wsh-pkgadd.sh\r")
    done = rf"post-install {re.escape(v['BUNDLE'])}: \d+ installed, \d+ failed"
    added, failed = 0, 0
    while True:  # one line per package; each may take a while under TCG
        i = m.expect_any([r"pkgadd ok: \S+", r"pkgadd FAILED[^\n]*", done], 1800)
        if i == 2:
            break
        added, failed = added + (i == 0), failed + (i == 1)
    m.expect(r"\n#\s*$", 60)
    m.log(f"{v['BUNDLE']}: {added} packages added, {failed} failed")
    shell(m, f"df -k {base}; cat /etc/wsh-lab-{v['BUNDLE']}.pkgs | wc -w")
    m.snap(f"{v['BUNDLE']}: {added} packages added, {failed} failed")
    shell(m, "cd /; umount /mnt; /etc/init.d/volmgt start", 120)
    if v["LOCAL_ENV"]:
        local_env(m, v)
    power_off(m, "init 5")
    if failed or not added:
        raise AssertionError(f"post-install {v['BUNDLE']}: {added} installed, {failed} failed"
                             f" (/var/sadm/wsh-lab-{v['BUNDLE']}.log in the guest)")


def local_env(m, v):
    """BASEDIR's bin and sbin on everyone's PATH (/etc/profile, after the system's directories, so
    root's commands stay Sun's) and MANPATH; with USER also in the user's ~/.profile, and the user's
    login shell LOGIN_SHELL. Root keeps /sbin/sh: it is on the root file system, which is all that is
    mounted in single-user mode, while LOGIN_SHELL is on the data disk."""
    base = v["BASEDIR"]
    # once only: /etc/profile and ~/.profile both have them (a login reads both)
    lines = ["# wsh-lab --local-env: the post-install packages",
             f"case :$PATH: in *:{base}/bin:*) ;; *) PATH=$PATH:{base}/bin:{base}/sbin; export PATH ;; esac",
             f"case :$MANPATH: in *:{base}/man:*) ;; *) MANPATH=${{MANPATH:-/usr/share/man}}:{base}/man:{base}/share/man;"
             " export MANPATH ;; esac"]
    m.send(f"test -x {v['LOGIN_SHELL']} && echo shell-present-ok\r")
    m.expect(r"(?m)^shell-present-ok", 60)
    m.expect(r"\n#\s*$", 60)
    write_file(m, "/tmp/wsh-env", lines)
    shell(m, "grep -s 'wsh-lab --local-env' /etc/profile >/dev/null || cat /tmp/wsh-env >> /etc/profile; tail -4 /etc/profile")
    if v["USER"]:
        user = v["USER"]
        home = f"/export/home/{user}"
        shell(m, f"grep -s 'wsh-lab --local-env' {home}/.profile >/dev/null || cat /tmp/wsh-env >> {home}/.profile;"
                 f" chown {user} {home}/.profile; cat {home}/.profile")
        shell(m, f"usermod -s {v['LOGIN_SHELL']} {user}; grep '^{user}:' /etc/passwd | cut -d: -f1,6-")
        # su runs the user's shell with -c but not as a login shell: $SHELL -l reads what a login reads
        m.send(f"su - {user} -c '$SHELL -l -c \"echo PATH=\\$PATH; which bash\"' | sed 's/^/{user}: /'\r")
        m.expect(rf"{user}: {v['LOGIN_SHELL']}[ \t]*$", 120)
        m.expect(r"\n#\s*$", 60)
    shell(m, "rm -f /tmp/wsh-env; grep '^root:' /etc/passwd | cut -d: -f1,6-")
    m.snap("local environment")
