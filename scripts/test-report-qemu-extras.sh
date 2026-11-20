#!/usr/bin/env bash
# Tests scripts/report-qemu-extras.sh offline: --dry-run with --issues fixtures, and a gh on PATH that
# fails, so nothing reaches GitHub. Covers the paths a real build seldom takes: an extra missing with
# no issue yet (create, with the body and the log excerpt), missing again in a new version (edit and
# comment), missing in a version the issue already has (nothing), back again (close), absent, and a
# bad state.
#
#   scripts/test-report-qemu-extras.sh
#
# Needs bash and jq. Exit status: 0 when every case passes, 1 otherwise.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
script="$top/scripts/report-qemu-extras.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Any real gh call is a failure of the test
mkdir -p "$work/bin"
cat > "$work/bin/gh" <<'EOF'
#!/bin/sh
echo "test: gh was called: $*" >&2
exit 99
EOF
chmod +x "$work/bin/gh"
export PATH="$work/bin:$PATH"
# and should a real gh still be found: no token, no config, no host to reach
unset GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN
export GH_CONFIG_DIR="$work/gh-config" GH_HOST=gh.invalid

failed=0
pass() { echo "ok   $1"; }
fail() { echo "FAIL $1: $2"; failed=1 case_failed=1; }

# run NAME RESULT_TSV ISSUES_JSON: runs the script, output in $work/NAME.out, status in $rc
run() {
    local name="$1"
    case_failed=0
    printf '%b' "$2" > "$work/$name.tsv"
    printf '%s' "$3" > "$work/$name.json"
    rc=0
    "$script" --dry-run --issues "$work/$name.json" --repo owner/repo --result "$work/$name.tsv" \
        --log "$work/make.log" --version 11.1.3-2+wsh9 --commit 0123456789abcdef \
        --run-url https://example.invalid/run/1 --assignee someone > "$work/$name.out" 2>&1 || rc=$?
}
has() { grep -qF -- "$2" "$work/$1.out" || fail "$1" "expected '$2' in the output"; }
hasnt() { if grep -qF -- "$2" "$work/$1.out"; then fail "$1" "did not expect '$2' in the output"; fi; }
ok_if_clean() {
    [ "$rc" = 0 ] || fail "$1" "exit status $rc"
    hasnt "$1" "test: gh was called"
    [ "$case_failed" = 1 ] || pass "$1"
}

# A build log as make prints it: a rejected hunk of the 3dfx port, then the warning line
cat > "$work/make.log" <<'EOF'
INFO: Restoring sparc submodule
INFO: Building pve-qemu with 3dfx support
patching file hw/display/vga.c
Hunk #2 FAILED at 120.
1 out of 2 hunks FAILED -- saving rejects to file hw/display/vga.c.rej
some unrelated line
WARNING: optional extra 3dfx missing: submodules/pve-qemu-qemu-3dfx.patch does not apply to this pve-qemu, pve-qemu ships without qemu-system-x86_64-3dfx
INFO: Building pve-qemu deb package
EOF

marker='<!-- optional-extra: 3dfx -->'
title='pve-qemu-kvm built without the optional extra: 3dfx'

# 1. Missing, no issue: create one, assigned, with the body printed
run create '3dfx\tmissing\tno /usr/bin/qemu-system-x86_64-3dfx\nopenbios\tpresent\tours\n' '[]'
has create "3dfx: missing, opening an issue"
has create "+ gh issue create --repo owner/repo --title pve-qemu-kvm\\ built\\ without\\ the\\ optional\\ extra:\\ 3dfx"
has create "--assignee someone"
has create "    | $marker"
has create "    | <!-- last-version: 11.1.3-2+wsh9 -->"
# shellcheck disable=SC2016 # Markdown backquotes
has create '    | `pve-qemu-kvm` **11.1.3-2+wsh9** was built and published without the optional extra **3dfx**.'
has create "    | - Commit: https://github.com/owner/repo/commit/0123456789abcdef"
has create "    | - Check (\`scripts/check-qemu-extras.sh\`): no /usr/bin/qemu-system-x86_64-3dfx"
has create "    | patching file hw/display/vga.c"
has create "    | Hunk #2 FAILED at 120."
has create "    | WARNING: optional extra 3dfx missing: submodules/pve-qemu-qemu-3dfx.patch does not apply"
hasnt create "some unrelated line"
has create "openbios: present"
ok_if_clean create

# 2. Missing, open issue from an older version: edit it and comment
run update '3dfx\tmissing\tno binary\n' \
    "[{\"number\": 42, \"title\": \"$title\", \"body\": \"$marker\\n<!-- last-version: 11.1.3-2+wsh8 -->\\nold\"}]"
has update "3dfx: missing, updating #42"
has update "+ gh issue edit 42 --repo owner/repo"
has update "+ gh issue comment 42 --repo owner/repo --body"
has update "11.1.3-2+wsh9"
hasnt update "gh issue create"
ok_if_clean update

# 3. Missing, the issue already has this version: nothing to do, no body
run seen '3dfx\tmissing\tno binary\n' \
    "[{\"number\": 42, \"title\": \"$title\", \"body\": \"$marker\\n<!-- last-version: 11.1.3-2+wsh9 -->\"}]"
has seen "3dfx: missing, #42 already has 11.1.3-2+wsh9"
hasnt seen "+ gh"
hasnt seen "    | "
ok_if_clean seen

# 4. Present again with an open issue: close it
run close '3dfx\tpresent\t/usr/bin/qemu-system-x86_64-3dfx\n' \
    "[{\"number\": 42, \"title\": \"$title\", \"body\": \"$marker\"}]"
has close "3dfx: present, closing #42"
has close "+ gh issue close 42 --repo owner/repo --reason completed --comment"
ok_if_clean close

# 5. Present, absent, no issues: nothing to change
run quiet '3dfx\tpresent\tok\nsun-proms\tabsent\tnot expected\n' '[]'
has quiet "3dfx: present"
has quiet "sun-proms: absent, not expected in this build"
hasnt quiet "+ gh"
ok_if_clean quiet

# 6. An unknown state is a usage error (2)
run bad '3dfx\tbroken\tx\n' '[]'
if [ "$rc" = 2 ]; then pass bad; else fail bad "exit status $rc, expected 2"; fi

if [ "$failed" != 0 ]; then
    echo "test-report-qemu-extras: FAILED"
    exit 1
fi
echo "test-report-qemu-extras: all passed"
