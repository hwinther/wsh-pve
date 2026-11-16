#!/usr/bin/env bash
# Promotion pull request for the qemu-3dfx pin (submodules/qemu-3dfx). The pin moves only through
# this PR: one branch, one PR, showing what changed upstream and whether our port still applies and
# builds. It never pushes to main and never merges.
#
#   scripts/qemu-3dfx-promotion.sh run [options]
#       Compares the pin on this checkout (main) with the master of the submodule's repository. When
#       master has commits beyond the pin: moves submodules/qemu-3dfx to it, runs
#       scripts/refresh-qemu-3dfx-patch.sh --check (and a refresh when the port no longer applies),
#       scripts/check-qemu-3dfx-build.sh, then force-pushes the branch (main + the new gitlink, and the
#       refreshed port if there is one) and opens or updates the PR. A failed check still opens the
#       PR, as a draft with "(3dfx check failed)" in its title. When master has nothing new, it
#       closes a PR that is left open. When the PR already shows this target against this main (same
#       fingerprint) and is not a draft, it does nothing; a draft (failed check) is checked again.
#       When the branch has commits the promotion didn't make (a hand fix), it leaves branch and PR
#       alone.
#     --dry-run      no push, no PR changes: print the commands instead (reading GitHub is fine)
#     --from SHA     the old pin (default: the gitlink of HEAD)
#     --to REF       the new pin (default: master of the submodule's repository)
#     --force        run the checks and update the PR even when the fingerprint is the same
#     --skip-build   leave out check-qemu-3dfx-build.sh (reported as "not run")
#     --jobs N       passed to check-qemu-3dfx-build.sh
#     --out DIR      where the title, body and logs go (default: build/qemu-3dfx-promotion)
#     --pr-json FILE the open PR as `gh pr list --json number,body,isDraft` gives it, instead of
#                    asking GitHub (for trying it without a token)
#
#   scripts/qemu-3dfx-promotion.sh body --from SHA --to SHA [options]
#       Only prints the PR body (Markdown) for the range; changes nothing, writes nothing.
#     --check-rc N --check-log FILE   result of refresh-qemu-3dfx-patch.sh --check
#     --build-rc N --build-log FILE   result of check-qemu-3dfx-build.sh (rc "skip": not run)
#     --port-changed                  the port had to be refreshed
#     --fingerprint X                 hidden marker, see run
#
#   --repo DIR   the qemu-3dfx clone with both commits (default: submodules/qemu-3dfx)
#
# run needs git, patch, docker, network, and gh with a token that may push branches and write pull
# requests (GH_TOKEN), except with --dry-run. The branch is pushed to the checkout's origin.
# Exit status: 0 done (whatever the checks said), 2 usage or setup error, else what failed.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
sub="submodules/qemu-3dfx"
branch="promote/qemu-3dfx"
port="submodules/pve-qemu-qemu-3dfx.patch"
marker="qemu-3dfx-promotion"
# In every commit this makes; a branch with other commits on it is someone's work and left alone
trailer="Generated-by: scripts/qemu-3dfx-promotion.sh"
tail_lines=40

usage() {
    sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
}
die() { echo "qemu-3dfx-promotion: $*" >&2; exit 2; }
say() { echo "qemu-3dfx-promotion: $*" >&2; }

[ $# -gt 0 ] || usage
cmd="$1"; shift
case "$cmd" in run|body) ;; -h|--help) usage ;; *) echo "qemu-3dfx-promotion: unknown command '$cmd'" >&2; usage ;; esac

from="" to="" repo="$top/$sub" dry_run=0 force=0 skip_build=0 jobs="" out="$top/build/qemu-3dfx-promotion"
pr_json="" check_rc="" check_log="" build_rc="" build_log="" port_changed=0 fingerprint=""
while [ $# -gt 0 ]; do
    case "$1" in
        --from) from="${2:?}"; shift 2 ;;
        --to) to="${2:?}"; shift 2 ;;
        --repo) repo="${2:?}"; shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        --force) force=1; shift ;;
        --skip-build) skip_build=1; shift ;;
        --jobs) jobs="${2:?}"; shift 2 ;;
        --out) out="${2:?}"; shift 2 ;;
        --pr-json) pr_json="${2:?}"; shift 2 ;;
        --check-rc) check_rc="${2:?}"; shift 2 ;;
        --check-log) check_log="${2:?}"; shift 2 ;;
        --build-rc) build_rc="${2:?}"; shift 2 ;;
        --build-log) build_log="${2:?}"; shift 2 ;;
        --port-changed) port_changed=1; shift ;;
        --fingerprint) fingerprint="${2:?}"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "qemu-3dfx-promotion: unknown option '$1'" >&2; usage ;;
    esac
done

# The web URL of the pinned repository (the submodule URL, which may be ssh or end in .git)
web_url() {
    local url
    url=$(git -C "$top" config -f .gitmodules "submodule.$sub.url")
    url=${url%.git}
    case "$url" in git@github.com:*) url="https://github.com/${url#git@github.com:}" ;; esac
    echo "$url"
}

# Upstream text in a Markdown table cell: no pipes, no HTML, no @mentions, one line
cell() { sed -e 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/|/\&#124;/g; s/@/\&#64;/g' | tr -d '\r\n'; }

# A log tail in a fenced block that its content can't close
# shellcheck disable=SC2016 # backticks in single quotes are Markdown here
log_tail() {
    local file="$1"
    echo
    echo '<details><summary>Last '"$tail_lines"' lines of the log</summary>'
    echo
    echo '````text'
    if [ -s "$file" ]; then tail -n "$tail_lines" "$file" | sed -e 's/^````/ ````/' | cut -c1-300; else echo "(empty)"; fi
    echo '````'
    echo
    echo '</details>'
}

# A check result that is a failure (not a pass, and not "not run")
failed_rc() { [ -n "$1" ] && [ "$1" != 0 ] && [ "$1" != skip ]; }

result_word() {
    case "$1" in
        0) echo "**pass**" ;;
        skip|"") echo "not run" ;;
        *) echo "**FAIL** (exit $1)" ;;
    esac
}

# shellcheck disable=SC2016 # backticks in single quotes are Markdown here
print_body() {
    local url old new n ancestor=1
    url=$(web_url)
    old=$(git -C "$repo" rev-parse --verify "$from^{commit}") || die "$from is not in $repo"
    new=$(git -C "$repo" rev-parse --verify "$to^{commit}") || die "$to is not in $repo"
    git -C "$repo" merge-base --is-ancestor "$old" "$new" || ancestor=0
    n=$(git -C "$repo" rev-list --count "$old..$new")

    echo "Moves the qemu-3dfx pin (\`$sub\`) from [\`${old:0:7}\`]($url/commit/$old) to [\`${new:0:7}\`]($url/commit/$new): $n upstream commit(s), [compare]($url/compare/$old...$new)."
    echo
    echo "Opened by \`promote-qemu-3dfx.yml\` (\`scripts/qemu-3dfx-promotion.sh\`). Nothing moves the pin on main but merging this PR; the branch is rewritten on the next run while upstream or main changes."
    if [ "$ancestor" = 0 ]; then
        echo
        echo "> [!WARNING]"
        echo "> The old pin is not an ancestor of the new one: upstream history was rewritten. The list shows the commits of the new pin that the old one lacks."
    fi

    echo
    echo "## Checks"
    echo
    echo "| Check | Result |"
    echo "| --- | --- |"
    echo "| \`scripts/refresh-qemu-3dfx-patch.sh --check\` (our port applies to the package's QEMU tree) | $(result_word "$check_rc") |"
    echo "| \`scripts/check-qemu-3dfx-build.sh\` (\`qemu-system-x86_64\` with qemu-3dfx, configured by \`debian/rules\`) | $(result_word "$build_rc") |"
    if [ "$port_changed" = 1 ]; then
        echo "| Port (\`$port\`) | **changed** in this PR (the promotion refreshes it with \`scripts/refresh-qemu-3dfx-patch.sh\` when it no longer applies): review its diff |"
    else
        echo "| Port (\`$port\`) | unchanged |"
    fi
    if [ -n "$check_log" ] && failed_rc "$check_rc"; then
        echo
        echo "### refresh-qemu-3dfx-patch.sh --check"
        log_tail "$check_log"
    fi
    if [ -n "$build_log" ] && [ "$build_rc" != skip ]; then
        echo
        echo "### check-qemu-3dfx-build.sh"
        echo
        grep -E '^check-qemu-3dfx-build: (PASS|FAIL)' "$build_log" | tail -n 1 | sed -e 's/^/`/; s/$/`/' || true
        log_tail "$build_log"
    fi
    if failed_rc "$check_rc" || failed_rc "$build_rc"; then
        echo
        echo "> [!CAUTION]"
        echo "> A check failed: merged as is, \`pve-qemu-kvm\` would be built without \`qemu-system-x86_64-3dfx\` (the package is still published, and the optional-extras issue would report it). Fix the port by pushing to this branch (\`scripts/refresh-qemu-3dfx-patch.sh\`, then \`--continue\`), or leave the PR open. Once the branch has a commit of someone else, the promotion leaves it alone; this PR's own checks then test it."
    fi

    echo
    echo "## Upstream commits"
    echo
    echo "| Commit | Date | Author | Subject |"
    echo "| --- | --- | --- | --- |"
    git -C "$repo" log --reverse --format='%H%x09%ad%x09%an%x09%s' --date=short "$old..$new" |
        while IFS=$'\t' read -r sha date author subject; do
            printf '| [`%s`](%s/commit/%s) | %s | %s | %s |\n' "${sha:0:7}" "$url" "$sha" "$date" \
                "$(printf '%s' "$author" | cell)" "$(printf '%s' "$subject" | cell)"
        done

    echo
    echo "## What changed upstream"
    echo
    echo "Upstream's QEMU patches (\`*.patch\` at its top level). Ours, \`$port\`, is a port of \`00-qemu92x-mesa-glide.patch\` to the package's QEMU and does not follow upstream by itself: a change to that file has to be carried over by hand."
    echo
    local stat
    stat=$(git -C "$repo" diff --stat=100 "$old" "$new" -- ':(glob)*.patch')
    if [ -n "$stat" ]; then
        echo '```text'
        echo "$stat"
        echo '```'
        echo
        echo '<details><summary>Diff of the patch files (first 300 lines)</summary>'
        echo
        echo '````diff'
        git -C "$repo" diff "$old" "$new" -- ':(glob)*.patch' | head -n 300 | sed -e 's/^````/ ````/' | cut -c1-300
        echo '````'
        echo
        echo '</details>'
    else
        echo "No change to upstream's QEMU patches."
    fi
    echo
    echo "The rest, by what it feeds:"
    echo
    echo "| Part | Used for | Change |"
    echo "| --- | --- | --- |"
    local part use s
    for part in "qemu-0/hw/3dfx:the 3dfx binary (copied into QEMU)" "qemu-1/hw/mesa:the 3dfx binary (copied into QEMU)" \
        "wrappers:the guest drivers (build-3dfx-drivers.yml)" "virgil3d:not built here" "scripts:not built here"; do
        use=${part#*:} part=${part%%:*}
        s=$(git -C "$repo" diff --shortstat "$old" "$new" -- "$part" | sed -e 's/^ *//')
        echo "| \`$part\` | $use | ${s:-none} |"
    done
    s=$(git -C "$repo" diff --shortstat "$old" "$new" -- . ':(exclude)qemu-0/hw/3dfx' ':(exclude)qemu-1/hw/mesa' \
        ':(exclude)wrappers' ':(exclude)virgil3d' ':(exclude)scripts' ':(exclude,glob)*.patch' | sed -e 's/^ *//')
    echo "| other | | ${s:-none} |"
    echo
    echo "Merging moves the pin on main, which builds the guest drivers (\`qemu-3dfx-drivers-${new:0:7}\`) and \`pve-qemu-kvm\` with the new 3dfx binary."
    echo
    echo "<!-- $marker from=$old to=$new fingerprint=${fingerprint:-none} -->"
}

if [ "$cmd" = body ]; then
    [ -n "$from" ] && [ -n "$to" ] || die "body needs --from and --to"
    print_body
    exit 0
fi

# ---- run ------------------------------------------------------------------------------------------

cd "$top"
command -v gh >/dev/null || [ -n "$pr_json" ] || [ "$dry_run" = 1 ] || die "gh is needed"
url=$(git config -f .gitmodules "submodule.$sub.url")
case "$url" in git@github.com:*) url="https://github.com/${url#git@github.com:}" ;; esac
mkdir -p "$out"

# The submodule at the old pin, with upstream's master fetched
old=${from:-$(git rev-parse "HEAD:$sub")}
if [ ! -e "$sub/.git" ]; then
    git -c "submodule.$sub.url=$url" submodule update --init "$sub"
fi
sub_before=$(git -C "$sub" rev-parse HEAD)
git -C "$sub" fetch -q "$url" "+refs/heads/master:refs/remotes/promotion/master"
if [ -n "$to" ]; then
    git -C "$sub" rev-parse -q --verify "$to^{commit}" >/dev/null || git -C "$sub" fetch -q "$url" "$to"
    new=$(git -C "$sub" rev-parse "$to^{commit}")
else
    new=$(git -C "$sub" rev-parse refs/remotes/promotion/master)
fi
git -C "$sub" rev-parse -q --verify "$old^{commit}" >/dev/null || die "the old pin $old is not in $url"
say "pin ${old:0:7}, upstream ${new:0:7}"

# The open promotion PR, if any
if [ -n "$pr_json" ]; then
    pr=$(cat "$pr_json")
elif command -v gh >/dev/null && { [ -n "${GH_TOKEN:-}" ] || gh auth status >/dev/null 2>&1; }; then
    pr=$(gh pr list --head "$branch" --state open --json number,body,isDraft)
else
    say "no gh token: assuming there is no open PR"
    pr="[]"
fi
pr_number=$(jq -r '.[0].number // ""' <<<"$pr")
pr_draft=$(jq -r '.[0].isDraft // false' <<<"$pr")
pr_fingerprint=$(jq -r '.[0].body // ""' <<<"$pr" | sed -n "s/.*<!-- $marker .*fingerprint=\([0-9a-f]*\) -->.*/\1/p" | tail -n 1)

w() {
    if [ "$dry_run" = 1 ]; then
        printf 'dry-run:' >&2; printf ' %q' "$@" >&2; echo >&2
    else
        "$@"
    fi
}

if [ "$old" = "$new" ] || git -C "$sub" merge-base --is-ancestor "$new" "$old"; then
    say "upstream has nothing beyond the pin"
    if [ -n "$pr_number" ]; then
        say "closing #$pr_number: the pin caught up"
        w gh pr close "$pr_number" --delete-branch \
            --comment "The pin on main is at ${old:0:7}, which has everything upstream's master (${new:0:7}) has. Nothing left to promote."
    fi
    exit 0
fi

# What the checks depend on: the range, and on main the QEMU tree, our patches and these scripts
fingerprint=$( { echo "$old $new"; git rev-parse HEAD:submodules/pve-qemu; git hash-object submodules/pve-qemu.patch \
    "$port" submodules/qemu-3dfx.patch scripts/refresh-qemu-3dfx-patch.sh scripts/check-qemu-3dfx-build.sh \
    scripts/check-qemu-extras.sh scripts/qemu-3dfx-promotion.sh; } | git hash-object --stdin)
# A draft is a failed check: that one runs again every time (it may have been the network)
if [ "$force" = 0 ] && [ -n "$pr_number" ] && [ "$pr_draft" = false ] && [ "$pr_fingerprint" = "$fingerprint" ]; then
    say "#$pr_number already shows ${new:0:7} against this main (fingerprint ${fingerprint:0:12}); nothing to do"
    exit 0
fi

base=$(git rev-parse HEAD)

# Someone pushed to the branch (a hand fix of the port): leave it to them and to the PR's checks
if remote_tip=$(git ls-remote --exit-code origin "refs/heads/$branch" | cut -f1) && [ -n "$remote_tip" ]; then
    # base..tip is the branch's own commits only with main's history here
    [ "$(git rev-parse --is-shallow-repository)" = false ] || git fetch -q --unshallow origin
    git fetch -q origin "refs/heads/$branch"
    others=0
    for c in $(git rev-list "$base..$remote_tip"); do
        git log -1 --format=%B "$c" | grep -q -x -F "$trailer" || others=$((others + 1))
    done
    if [ "$others" -gt 0 ]; then
        say "$branch has $others commit(s) not made by the promotion; leaving it alone"
        exit 0
    fi
fi

cleanup() {
    git -C "$sub" checkout -q "$sub_before" 2>/dev/null || true
    git checkout -q -- "$port" 2>/dev/null || true
    [ -z "${wt:-}" ] || { git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"; git worktree prune; }
}
trap cleanup EXIT
git -C "$sub" checkout -q "$new"

# pve-qemu and its QEMU, for the checks
if [ ! -f submodules/pve-qemu/debian/rules ]; then
    git submodule update --init submodules/pve-qemu
fi
git -C submodules/pve-qemu submodule update --init qemu

# 1. Does the port apply? When not, try the mechanical refresh, then check again
check_rc=0 port_changed=0
scripts/refresh-qemu-3dfx-patch.sh --check > "$out/check.log" 2>&1 || check_rc=$?
if [ "$check_rc" = 1 ]; then
    say "the port does not apply; trying scripts/refresh-qemu-3dfx-patch.sh"
    refresh_rc=0
    scripts/refresh-qemu-3dfx-patch.sh > "$out/refresh.log" 2>&1 || refresh_rc=$?
    if [ "$refresh_rc" = 0 ] && ! git diff --quiet -- "$port"; then
        port_changed=1
        check_rc=0
        { echo "(after the refresh)"; scripts/refresh-qemu-3dfx-patch.sh --check; } >> "$out/check.log" 2>&1 || check_rc=$?
    else
        cat "$out/refresh.log" >> "$out/check.log"
        git checkout -q -- "$port"
        rm -rf build/qemu-3dfx-refresh
        git -C submodules/pve-qemu/qemu worktree prune
    fi
fi
[ "$check_rc" -le 1 ] || die "refresh-qemu-3dfx-patch.sh --check could not run (exit $check_rc): $(tail -n 3 "$out/check.log")"
say "--check: exit $check_rc, port changed: $port_changed"

# 2. The 3dfx-only build
build_rc=skip
if [ "$skip_build" = 0 ]; then
    build_rc=0
    scripts/check-qemu-3dfx-build.sh ${jobs:+--jobs "$jobs"} > "$out/build.log" 2>&1 || build_rc=$?
    [ "$build_rc" -le 1 ] || die "check-qemu-3dfx-build.sh could not run (exit $build_rc): $(tail -n 3 "$out/build.log")"
    say "build check: exit $build_rc"
fi

failed=0
[ "$check_rc" = 0 ] || failed=1
[ "$build_rc" = 0 ] || [ "$build_rc" = skip ] || failed=1

# 3. Title and body
title="chore(deps): promote qemu-3dfx to ${new:0:7}"
[ "$failed" = 0 ] || title="$title (3dfx check failed)"
echo "$title" > "$out/title"
build_args=(--build-rc "$build_rc")
[ "$build_rc" = skip ] || build_args+=(--build-log "$out/build.log")
pc=()
[ "$port_changed" = 0 ] || pc=(--port-changed)
"$0" body --repo "$top/$sub" --from "$old" --to "$new" --check-rc "$check_rc" --check-log "$out/check.log" \
    "${build_args[@]}" "${pc[@]}" --fingerprint "$fingerprint" > "$out/body.md"
say "title: $title"
say "body: $out/body.md ($(wc -c < "$out/body.md") bytes)"

# 4. The branch: main + the new gitlink (+ the refreshed port), in a worktree so this checkout stays
wt=$(mktemp -d)
rmdir "$wt"
git worktree add -q --detach "$wt" "$base"
git -C "$wt" update-index --cacheinfo "160000,$new,$sub"
if [ "$port_changed" = 1 ]; then
    cp "$port" "$wt/$port"
    git -C "$wt" add -- "$port"
fi
msg="$title

Upstream: $(web_url)/compare/$old...$new"
[ "$port_changed" = 0 ] || msg="$msg
The port ($port) was refreshed by scripts/refresh-qemu-3dfx-patch.sh."
msg="$msg

$trailer"
git -C "$wt" diff --cached --quiet && die "main already has qemu-3dfx at ${new:0:7} (--from ${old:0:7} is not its pin): nothing to commit"
git -C "$wt" commit -q --no-verify -m "$msg"
say "branch $branch: $(git -C "$wt" log -1 --format='%h %s') on ${base:0:7}"
git -C "$wt" diff --stat HEAD~1 HEAD >&2
w git -C "$wt" push --force origin "HEAD:refs/heads/$branch"

# 5. The PR: one, updated in place; a draft while a check fails
if [ -n "$pr_number" ]; then
    w gh pr edit "$pr_number" --title "$title" --body-file "$out/body.md"
    if [ "$failed" = 1 ] && [ "$pr_draft" = false ]; then
        w gh pr ready "$pr_number" --undo
    elif [ "$failed" = 0 ] && [ "$pr_draft" = true ]; then
        w gh pr ready "$pr_number"
    fi
else
    draft=()
    [ "$failed" = 0 ] || draft=(--draft)
    w gh pr create --base main --head "$branch" --title "$title" --body-file "$out/body.md" "${draft[@]}"
fi
