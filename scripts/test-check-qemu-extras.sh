#!/usr/bin/env bash
# Tests the sun-proms extra of scripts/check-qemu-extras.sh on fake roots, with fake PROM files and
# a test manifest (never real images): PROMs installed by wsh-sun-proms
# (packages/wsh-lab/sun-proms/sun_proms.py, run from this checkout) count as present and are named
# as its; files nobody recorded count too, as "not recorded"; a file changed after the install is
# no longer the tool's; a missing PROM fails the check.
#
#   scripts/test-check-qemu-extras.sh
#
# Needs bash and python3. Exit status: 0 when every case passes, 1 otherwise.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
check="$top/scripts/check-qemu-extras.sh"
tool="$top/packages/wsh-lab/sun-proms/sun_proms.py"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

failed=0
pass() { echo "ok   $1"; }
fail() { echo "FAIL $1: $2"; failed=1 case_failed=1; }

# The fake PROMs and a manifest of them
mkdir -p "$work/src"
for f in ss5.bin ss10_v2.25_rom ss20_v2.25_rom lx.bin; do
    printf 'fake %s\n' "$f" > "$work/src/$f"
done
python3 - "$work/src" "$work/manifest.json" <<'EOF'
import hashlib, json, os, sys
src, out = sys.argv[1], sys.argv[2]
proms = []
for name in sorted(os.listdir(src)):
    data = open(os.path.join(src, name), "rb").read()
    proms.append({"name": name, "machine": "test", "size": len(data),
                  "sha256": hashlib.sha256(data).hexdigest(), "description": "fake"})
json.dump({"proms": proms}, open(out, "w"))
EOF

# install ROOT [NAME...]: wsh-sun-proms into ROOT/usr/share/kvm with its record under ROOT
install() {
    local root="$1"
    shift
    python3 "$tool" install --manifest "$work/manifest.json" --dir "$root/usr/share/kvm" \
        --state "$root/var/lib/wsh-sun-proms/installed.tsv" --source "$work/src" "$@" > /dev/null
}
# run NAME ROOT: the check of sun-proms on ROOT, output in $work/NAME.out, status in $rc
run() {
    case_failed=0
    rc=0
    "$check" --root "$2" --only sun-proms > "$work/$1.out" 2>&1 || rc=$?
}
has() { grep -qF -- "$2" "$work/$1.out" || fail "$1" "expected '$2' in: $(cat "$work/$1.out")"; }
done_case() { [ "$case_failed" = 1 ] || pass "$1"; }

# 1. All four installed by wsh-sun-proms
root="$work/root1"
install "$root"
run tool "$root"
[ "$rc" = 0 ] || fail tool "exit status $rc"
has tool "present"
has tool "(wsh-sun-proms: ss5.bin, ss10_v2.25_rom, ss20_v2.25_rom, lx.bin)"
done_case tool

# 2. Two by the tool, two copied by hand
root="$work/root2"
install "$root" ss5.bin lx.bin
cp "$work/src/ss10_v2.25_rom" "$work/src/ss20_v2.25_rom" "$root/usr/share/kvm/"
run mixed "$root"
[ "$rc" = 0 ] || fail mixed "exit status $rc"
has mixed "(wsh-sun-proms: ss5.bin, lx.bin; not recorded: ss10_v2.25_rom, ss20_v2.25_rom)"
done_case mixed

# 3. Changed after the install: still present (the check only needs the file), no longer the tool's
printf 'changed\n' >> "$root/usr/share/kvm/lx.bin"
run changed "$root"
[ "$rc" = 0 ] || fail changed "exit status $rc"
has changed "(wsh-sun-proms: ss5.bin; not recorded: ss10_v2.25_rom, ss20_v2.25_rom, lx.bin)"
done_case changed

# 4. One missing: the check fails and names it
rm "$root/usr/share/kvm/ss20_v2.25_rom"
run missing "$root"
[ "$rc" = 1 ] || fail missing "exit status $rc, expected 1"
has missing "missing"
has missing "no ss20_v2.25_rom"
done_case missing

# 5. The older three only (SUN_PROMS), with wsh-sun-proms
root="$work/root3"
install "$root" ss5.bin ss10_v2.25_rom ss20_v2.25_rom
case_failed=0 rc=0
SUN_PROMS="ss5.bin ss10_v2.25_rom ss20_v2.25_rom" "$check" --root "$root" --only sun-proms > "$work/older.out" 2>&1 || rc=$?
[ "$rc" = 0 ] || fail older "exit status $rc"
has older "(wsh-sun-proms: ss5.bin, ss10_v2.25_rom, ss20_v2.25_rom)"
done_case older

exit "$failed"
