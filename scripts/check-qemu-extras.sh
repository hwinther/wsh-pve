#!/usr/bin/env bash
# Which optional extras a pve-qemu-kvm package has. The Makefile never fails the package build on
# them (pve-qemu-3dfx, openbios-sparc32, restore-sparc), so a build without one still publishes:
#
#   3dfx              /usr/bin/qemu-system-x86_64-3dfx, QEMU with qemu-3dfx (its "featuring qemu-3dfx@" banner)
#   openbios          openbios-sparc32 and QEMU,cgthree.bin built from openbios/, not QEMU's prebuilt images
#   openbios-sparc64  openbios-sparc64 built from openbios/ (Solaris 10 on sun4u), not QEMU's prebuilt image
#   sun-proms         ss5.bin, ss10_v2.25_rom and ss20_v2.25_rom from the private submodules/sparc
#
#   scripts/check-qemu-extras.sh --deb build/repo/pve-qemu-kvm_<version>_amd64.deb [options]
#   scripts/check-qemu-extras.sh --root /          (the installed package)
#
#   --built DIR    build/openbios of the same build: openbios and openbios-sparc64 count if the package
#                  has these files
#   --stock DIR    QEMU's pc-bios/ of the same build: openbios and openbios-sparc64 count if the
#                  package's files differ
#   --expect LIST  extras that must be present, comma-separated (default: all); the others are listed
#   --only LIST    check these extras only
#   --result FILE  one line per extra: <name> TAB present|missing|absent TAB <detail>
#                  (missing: expected and not there; absent: not expected and not there)
#   --markdown     print the table as Markdown (for $GITHUB_STEP_SUMMARY)
#
# Without --built/--stock (an installed package), openbios counts as ours when the build date in
# openbios-sparc32 is within two days of the package's qemu-system-sparc (QEMU's image is built
# months before a release, ours in the same run) and QEMU,cgthree.bin isn't QEMU's. openbios-sparc64
# counts as ours when its build date is within two days of the package's qemu-system-sparc64 and it
# has the Forth word upa-portid>bustype, which only openbios/patches/0009 defines (the OBP-style node
# names that give Solaris 10 its console): a date alone would also pass an image built here without
# the patches that matter.
#
# Exit status: 0 when every expected extra is present, 1 when one is missing, 2 on a usage error.
set -euo pipefail

ALL_EXTRAS="3dfx,openbios,openbios-sparc64,sun-proms"
# QEMU,cgthree.bin as QEMU ships it (850 bytes; QEMU 11.1)
STOCK_CG3_SHA256="a99f3a06fdac5cf5d72bd0fd24647d897302c3ff8e918add65168185f8cbdf4d"
PROMS="ss5.bin ss10_v2.25_rom ss20_v2.25_rom"
# A Forth word that only openbios/patches/0009-sparc64-name-upa-and-ebus-children-like-obp defines
SPARC64_MARKER="upa-portid>bustype"

deb="" root="" built="" stock="" expect="$ALL_EXTRAS" only="$ALL_EXTRAS" result="" markdown=0

usage() {
    sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --deb) deb="${2:?}"; shift 2 ;;
        --root) root="${2:?}"; shift 2 ;;
        --built) built="${2:?}"; shift 2 ;;
        --stock) stock="${2:?}"; shift 2 ;;
        --expect) expect="${2-}"; shift 2 ;;
        --only) only="${2:?}"; shift 2 ;;
        --result) result="${2:?}"; shift 2 ;;
        --markdown) markdown=1; shift ;;
        -h|--help) usage ;;
        *) echo "check-qemu-extras: unknown option '$1'" >&2; usage ;;
    esac
done
if { [ -n "$deb" ] && [ -n "$root" ]; } || { [ -z "$deb" ] && [ -z "$root" ]; }; then
    echo "check-qemu-extras: give either --deb or --root" >&2
    usage
fi
for name in ${expect//,/ } ${only//,/ }; do
    case ",$ALL_EXTRAS," in *",$name,"*) ;; *) echo "check-qemu-extras: unknown extra '$name'" >&2; exit 2 ;; esac
done

if [ -n "$deb" ]; then
    [ -f "$deb" ] || { echo "check-qemu-extras: no such file: $deb" >&2; exit 2; }
    root=$(mktemp -d)
    trap 'rm -rf "$root"' EXIT
    dpkg-deb -x "$deb" "$root"
    version=$(dpkg-deb -f "$deb" Version)
elif [ "$root" = / ]; then
    version=$(dpkg-query -W -f '${Version}' pve-qemu-kvm 2>/dev/null || echo unknown)
else
    version=unknown
fi
root="${root%/}"
kvm="$root/usr/share/kvm"

# shellcheck disable=SC2329 # used by the check_ functions
sha() { sha256sum "$1" | cut -d' ' -f1; }

# Whether the build date in OpenBIOS image $1 (its banner: "Nov 16 2026 06:37") is within two days of
# file $2, the QEMU binary of the same package. Appends to notes; sets status=no when it isn't.
# shellcheck disable=SC2329
check_built_with() {
    local image="$1" bin="$2" when ob_time pkg_time
    when=$(grep -aoE '(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [ 0-9][0-9] [0-9]{4} [0-9]{2}:[0-9]{2}' "$image" | head -n 1 || true)
    ob_time=$(date -u -d "$when" +%s 2>/dev/null || echo 0)
    pkg_time=$(stat -c %Y "$bin" 2>/dev/null || echo 0)
    if [ "$ob_time" -eq 0 ] || [ "$pkg_time" -eq 0 ]; then
        status=no notes+=("no build date in ${image##*/} or no ${bin##*/} to compare it with")
    elif [ $((pkg_time > ob_time ? pkg_time - ob_time : ob_time - pkg_time)) -gt $((2 * 86400)) ]; then
        status=no notes+=("${image##*/} built on $when, not with the package (QEMU's)")
    else
        notes+=("${image##*/} built on $when")
    fi
}

# check_<extra>: sets status (yes/no) and detail. Called by name below.
# shellcheck disable=SC2329
check_3dfx() {
    local bin="$root/usr/bin/qemu-system-x86_64-3dfx" rev
    if [ ! -f "$bin" ]; then
        status=no detail="no /usr/bin/qemu-system-x86_64-3dfx"
    elif ! grep -aq 'featuring qemu-3dfx@' "$bin"; then
        status=no detail="/usr/bin/qemu-system-x86_64-3dfx has no qemu-3dfx banner"
    else
        # The revision is only printed by --version, which needs the binary's libraries.
        rev=$("$bin" --version 2>/dev/null | sed -n 's/.*featuring qemu-3dfx@\([0-9a-f]*\).*/\1/p' || true)
        status=yes detail="/usr/bin/qemu-system-x86_64-3dfx${rev:+ (qemu-3dfx $rev)}"
    fi
}

# shellcheck disable=SC2329
check_openbios() {
    local ob="$kvm/openbios-sparc32" cg3="$kvm/QEMU,cgthree.bin" f notes=()
    for f in "$ob" "$cg3"; do
        [ -f "$f" ] || { status=no detail="no /usr/share/kvm/${f##*/}"; return; }
    done
    status=yes
    if [ -n "$built" ]; then
        for f in openbios-sparc32 'QEMU,cgthree.bin'; do
            if [ ! -f "$built/$f" ]; then
                status=no notes+=("$f not built")
            elif [ "$(sha "$built/$f")" != "$(sha "$kvm/$f")" ]; then
                status=no notes+=("$f is not the one built")
            fi
        done
    fi
    if [ -n "$stock" ]; then
        for f in openbios-sparc32 'QEMU,cgthree.bin'; do
            if [ -f "$stock/$f" ] && [ "$(sha "$stock/$f")" = "$(sha "$kvm/$f")" ]; then
                status=no notes+=("$f is QEMU's")
            fi
        done
    fi
    if [ -z "$built" ] && [ -z "$stock" ]; then
        check_built_with "$ob" "$root/usr/bin/qemu-system-sparc"
        if [ "$(sha "$cg3")" = "$STOCK_CG3_SHA256" ]; then
            status=no notes+=("QEMU,cgthree.bin is QEMU's")
        fi
    fi
    if [ "$status" = yes ]; then
        notes=("openbios-sparc32 and QEMU,cgthree.bin ($(stat -c %s "$cg3") bytes) from openbios/" "${notes[@]}")
    else
        notes=("QEMU's images" "${notes[@]}")
    fi
    detail=$(printf '%s; ' "${notes[@]}")
    detail="${detail%; }"
}

# shellcheck disable=SC2329
check_openbios_sparc64() {
    local ob="$kvm/openbios-sparc64" notes=()
    [ -f "$ob" ] || { status=no detail="no /usr/share/kvm/openbios-sparc64"; return; }
    status=yes
    if [ -n "$built" ]; then
        if [ ! -f "$built/openbios-sparc64" ]; then
            status=no notes+=("openbios-sparc64 not built")
        elif [ "$(sha "$built/openbios-sparc64")" != "$(sha "$ob")" ]; then
            status=no notes+=("openbios-sparc64 is not the one built")
        fi
    fi
    if [ -n "$stock" ] && [ -f "$stock/openbios-sparc64" ] && [ "$(sha "$stock/openbios-sparc64")" = "$(sha "$ob")" ]; then
        status=no notes+=("openbios-sparc64 is QEMU's")
    fi
    if [ -z "$built" ] && [ -z "$stock" ]; then
        check_built_with "$ob" "$root/usr/bin/qemu-system-sparc64"
        if ! grep -aqF -- "$SPARC64_MARKER" "$ob"; then
            status=no notes+=("no $SPARC64_MARKER in openbios-sparc64 (not built with openbios/patches/0009)")
        fi
    fi
    if [ "$status" = yes ]; then
        notes=("openbios-sparc64 from openbios/" "${notes[@]}")
    else
        notes=("QEMU's image" "${notes[@]}")
    fi
    detail=$(printf '%s; ' "${notes[@]}")
    detail="${detail%; }"
}

# shellcheck disable=SC2329
check_sun_proms() {
    local f missing=()
    for f in $PROMS; do [ -s "$kvm/$f" ] || missing+=("$f"); done
    if [ ${#missing[@]} -eq 0 ]; then
        status=yes detail="${PROMS// /, }"
    else
        status=no detail="no ${missing[*]}"
    fi
}

rows=() rc=0
for name in ${only//,/ }; do
    status="" detail=""
    "check_${name//-/_}"
    if [ "$status" = yes ]; then
        state=present
    elif [[ ",$expect," == *",$name,"* ]]; then
        state=missing rc=1
    else
        state=absent
    fi
    rows+=("$name"$'\t'"$state"$'\t'"$detail")
done

if [ -n "$result" ]; then
    printf '%s\n' "${rows[@]}" > "$result"
fi

if [ "$markdown" = 1 ]; then
    echo "### Optional extras in pve-qemu-kvm $version"
    echo
    echo "| Extra | State | Detail |"
    echo "| --- | --- | --- |"
    for row in "${rows[@]}"; do
        IFS=$'\t' read -r name state detail <<< "$row"
        case "$state" in present) mark="present" ;; missing) mark="**MISSING**" ;; *) mark="absent (not expected)" ;; esac
        echo "| $name | $mark | $detail |"
    done
else
    echo "pve-qemu-kvm $version"
    for row in "${rows[@]}"; do
        IFS=$'\t' read -r name state detail <<< "$row"
        printf '  %-16s %-8s %s\n' "$name" "$state" "$detail"
    done
fi
exit "$rc"
