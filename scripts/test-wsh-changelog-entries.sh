#!/usr/bin/env bash
# Tests scripts/wsh-changelog-entries.sh against a throwaway git repository with the layout of this
# one (submodules/<package>.patch, .changelog.patch, gitlinks, openbios/), and
# scripts/wsh-changelog-dch.sh with a dch on PATH that records its arguments. Covers: commits since
# the previous build, the package's paths only, merge and "Update changelog" commits left out,
# the upstream sync line, Dependabot commits, the cap, the fallbacks and --rev.
#
#   scripts/test-wsh-changelog-entries.sh
#
# Needs bash and git. Exit status: 0 when every case passes, 1 otherwise.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
entries="$top/scripts/wsh-changelog-entries.sh"
dchscript="$top/scripts/wsh-changelog-dch.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

failed=0
# check NAME EXPECTED ACTUAL
check() {
    if [ "$2" = "$3" ]; then
        echo "ok   $1"
    else
        echo "FAIL $1"
        echo "  expected:"; printf '%s\n' "$2" | sed 's/^/    /'
        echo "  got:"; printf '%s\n' "$3" | sed 's/^/    /'
        failed=1
    fi
}

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
repo="$work/repo"
git init -q -b main "$repo"
cd "$repo"
git config user.name "Some One"
git config user.email "someone@example.invalid"
git config commit.gpgsign false

# commit SUBJECT FILE...: appends a line to each file and commits it
commit() {
    local subject="$1" f
    shift
    for f in "$@"; do
        mkdir -p "$(dirname "$f")"
        echo "$subject" >> "$f"
        git add "$f"
    done
    git commit -q -m "$subject"
}
# gitlink PATH SHA: points the submodule pointer PATH at SHA (no real submodule needed)
gitlink() { git update-index --add --cacheinfo "160000,$2,$1"; }
dependabot() {
    GIT_AUTHOR_NAME="dependabot[bot]" GIT_AUTHOR_EMAIL="49699333+dependabot[bot]@users.noreply.github.com" commit "$@"
}

commit "initial" README.md
commit "feat(qemu): an old change (#1)" submodules/pve-qemu.patch
commit "Update changelog for pve-qemu (11.1.3-4-wsh1)" submodules/pve-qemu.changelog.patch

# Nothing since the build: the last subject of the patch
check "empty range falls back to the patch's last subject" \
    "feat(qemu): an old change (#1)" "$("$entries" pve-qemu)"

commit "fix(sparc32): a qemu patch change (#10)" submodules/pve-qemu.patch
commit "feat(sparc64): an OpenBIOS change (#11)" openbios/patches/0001.patch
commit "docs: not an input (#12)" docs/readme.md
commit "feat(3dfx): the 3dfx port (#13)" submodules/pve-qemu-qemu-3dfx.patch
gitlink submodules/qemu-3dfx 1111111111111111111111111111111111111111
git commit -q -m "chore(3dfx): promote qemu-3dfx (#14)"
commit "feat(pve): a pve-manager change (#15)" submodules/pve-manager.patch
commit "Update changelog for pve-manager (9.2.32-wsh1)" submodules/pve-manager.changelog.patch
dependabot "chore(deps): bump debian in /openbios (#16)" openbios/Dockerfile
# a merge commit (not squashed) touching an input
git switch -q -c side
commit "fix(3dfx): fix on a side branch (#17)" submodules/qemu-3dfx.patch
git switch -q main
git merge -q --no-ff -m "Merge branch 'side'" side
gitlink submodules/pve-qemu 2222222222222222222222222222222222222222
git commit -q -m "Update submodule pve-qemu"

expected="fix(sparc32): a qemu patch change (#10)
feat(sparc64): an OpenBIOS change (#11)
feat(3dfx): the 3dfx port (#13)
chore(3dfx): promote qemu-3dfx (#14)
fix(3dfx): fix on a side branch (#17)
Sync with upstream pve-qemu 2222222"
check "pve-qemu: inputs since the build, oldest first; no docs, merges, other packages, Dependabot" \
    "$expected" "$("$entries" pve-qemu)"

check "pve-manager: nothing since its build, falls back" \
    "feat(pve): a pve-manager change (#15)" "$("$entries" pve-manager)"

check "--rev: the range ends at the given commit" \
    "fix(sparc32): a qemu patch change (#10)
feat(sparc64): an OpenBIOS change (#11)" "$("$entries" --rev HEAD~7 pve-qemu)"

check "cap: WSH_CHANGELOG_MAX entries, then a count" \
    "fix(sparc32): a qemu patch change (#10)
feat(sparc64): an OpenBIOS change (#11)
... and 4 more commits" "$(WSH_CHANGELOG_MAX=2 "$entries" pve-qemu)"

check "runs from a subdirectory" "$expected" "$(cd openbios && "$entries" pve-qemu)"

# A build with only Dependabot's commits since the previous one lists them
commit "Update changelog for pve-qemu (11.1.3-4-wsh2)" submodules/pve-qemu.changelog.patch
dependabot "chore(deps): bump debian in /openbios (#18)" openbios/Dockerfile
check "Dependabot only: listed" "chore(deps): bump debian in /openbios (#18)" "$("$entries" pve-qemu)"

# pve-storage: never built here, and its sync commit is the only input
gitlink submodules/pve-storage 3333333333333333333333333333333333333333
git commit -q -m "Update submodule pve-storage"
check "never built: falls back to HEAD's subject when the patch has no commits" \
    "Update submodule pve-storage" "$("$entries" pve-storage)"
commit "Update changelog for pve-storage (9.1.0-wsh1)" submodules/pve-storage.changelog.patch
gitlink submodules/pve-storage 4444444444444444444444444444444444444444
git commit -q -m "Update submodule pve-storage"
check "pve-storage: the sync line" "Sync with upstream pve-storage 4444444" "$("$entries" pve-storage)"

rc=0
"$entries" not-a-package > /dev/null 2>&1 || rc=$?
check "unknown package: usage error" 2 "$rc"

# A shallow clone without the previous build: the fallback
git clone -q --depth 1 "file://$repo" "$work/shallow"
check "shallow clone: falls back" "Update submodule pve-storage" \
    "$(cd "$work/shallow" && "$entries" pve-storage)"

# wsh-changelog-dch.sh: dch -l for the first entry, dch -a for the others, -- before each
mkdir -p "$work/bin"
cat > "$work/bin/dch" <<'EOF'
#!/usr/bin/env bash
printf '%s|' "$@" >> "$DCH_LOG"
echo >> "$DCH_LOG"
EOF
chmod +x "$work/bin/dch"
export DCH_LOG="$work/dch.log"
PATH="$work/bin:$PATH" WSH_CHANGELOG_ENTRIES="first (#1)
-second, with a dash
\$third \"quoted\"" "$dchscript" trixie
check "dch: -l +wsh with the first, -a with the rest" \
    "-l|+wsh|-D|trixie|--|first (#1)|
-a|--|-second, with a dash|
-a|--|\$third \"quoted\"|" "$(cat "$DCH_LOG")"

rc=0
PATH="$work/bin:$PATH" WSH_CHANGELOG_ENTRIES="" "$dchscript" trixie > /dev/null 2>&1 || rc=$?
check "dch: no entries is an error" 2 "$rc"

exit "$failed"
