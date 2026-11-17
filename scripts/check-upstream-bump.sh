#!/bin/bash
# Checks a submodule that the nightly sync moved to a new upstream commit, before the new pointer
# goes to main:
#   1. our patch (submodules/<name>.patch) applies without a rejected hunk (a debian/changelog hunk
#      may fail: the build rewrites the changelog anyway);
#   2. the patched package's build dependencies are met by the build image, and if not, whether
#      they are installable from the image's apt sources (then only the image is stale).
# Run from the repository root with the submodule already at the new commit. The submodule's work
# tree is restored afterwards.
#
# Usage: scripts/check-upstream-bump.sh <submodule>
# Env:   REPORT       Markdown report file (default: check-upstream-bump.md)
#        BUILD_IMAGE  build image (default: DOCKER_BUILD_IMAGE from the Makefile)
#        SKIP_DEPS=1  only check the patch
# Exit:  0 the bump can go to main; 1 hold it back (the report says why); 2 usage error
set -u

name=${1:-}
[ -n "$name" ] && [ -d "submodules/$name" ] || { echo "usage: $0 <submodule>" >&2; exit 2; }
report=${REPORT:-check-upstream-bump.md}
image=${BUILD_IMAGE:-$(sed -n 's/^DOCKER_BUILD_IMAGE = //p' Makefile)}
sub="submodules/$name"
patchfile="$sub.patch"
held=0

restore() {
    git -C "$sub" checkout -q -- . 2>/dev/null
    git -C "$sub" clean -fdq 2>/dev/null
}
trap restore EXIT

{
    echo "### \`$name\` at upstream \`$(git -C "$sub" rev-parse --short HEAD)\`"
    echo
    echo "Upstream: $(git -C "$sub" log -1 --format='%s (%cs)')"
    echo
} > "$report"

# 1. The patch.
if [ -f "$patchfile" ]; then
    out=$(patch --dry-run -d "$sub" -p1 -i "../$name.patch" 2>&1)
    failed=$(printf '%s\n' "$out" | awk '
        /^(checking|patching) file / { f = $3 }
        /FAILED/ && f != "" { print f }
        /^can.t find file to patch/ { print "(missing file)" }' | sort -u | grep -vx 'debian/changelog')
    if [ -n "$failed" ]; then
        held=1
        {
            echo "**Patch:** \`$patchfile\` no longer applies. Rejected hunks in:"
            echo
            printf '%s\n' "$failed" | sed 's/^/- `/; s/$/`/'
            echo
            echo "Refresh the patch against this upstream commit in a PR that also moves the pointer."
            echo
        } >> "$report"
    else
        echo "**Patch:** applies." >> "$report"
        echo >> "$report"
    fi
else
    echo "**Patch:** none for this submodule." >> "$report"
    echo >> "$report"
fi

# 2. Build dependencies, on the patched tree (only if the patch applied).
if [ "$held" = 0 ] && [ "${SKIP_DEPS:-0}" != 1 ] && [ -f "$sub/debian/control" ]; then
    [ -f "$patchfile" ] && patch -s -d "$sub" -p1 --no-backup-if-mismatch --reject-file=/dev/null -i "../$name.patch" >/dev/null 2>&1
    deps=$(docker run --rm --user root -v "$PWD/$sub:/src" -w /src "$image" bash -c '
        if out=$(dpkg-checkbuilddeps 2>&1); then echo "IMAGE_OK"; exit 0; fi
        echo "IMAGE_MISSING ${out#*unmet build dependencies: }"
        apt-get update -qq >/dev/null 2>&1
        if sim=$(apt-get build-dep -s ./ 2>&1); then echo "REPO_OK"; else
            echo "REPO_MISSING"; printf "%s\n" "$sim" | grep -E "^ |Depends|unmet|E:" | head -20; fi
    ' 2>&1)
    rc=$?
    if [ $rc -ne 0 ] && ! printf '%s\n' "$deps" | grep -q '^IMAGE_'; then
        held=1
        { echo "**Build dependencies:** the check could not run (\`$image\`):"; echo; echo '```'
          printf '%s\n' "$deps" | tail -20; echo '```'; echo; } >> "$report"
    elif printf '%s\n' "$deps" | grep -q '^IMAGE_OK'; then
        echo "**Build dependencies:** met by \`$image\`." >> "$report"
    else
        held=1
        missing=$(printf '%s\n' "$deps" | sed -n 's/^IMAGE_MISSING //p')
        {
            echo "**Build dependencies:** \`$image\` lacks: \`$missing\`."
            echo
            if printf '%s\n' "$deps" | grep -q '^REPO_OK'; then
                echo "They are installable from the image's apt sources: only the image is stale."
                echo "Dispatch \`publish-pve-build-image.yml\`, then run this sync again."
            else
                echo "They are not installable from the image's apt sources yet (Proxmox has not"
                echo "published them, or the patch needs something else). apt says:"
                echo
                echo '```'
                printf '%s\n' "$deps" | sed -n '/^REPO_MISSING/,$p' | sed 1d
                echo '```'
                echo
                echo "Wait for the packages, rebuild the image, then run this sync again."
            fi
        } >> "$report"
    fi
    echo >> "$report"
fi

if [ "$held" = 1 ]; then
    echo "Held back: main keeps its current \`$sub\` pointer." >> "$report"
else
    echo "OK: the new pointer can go to main." >> "$report"
fi
cat "$report"
exit $held
