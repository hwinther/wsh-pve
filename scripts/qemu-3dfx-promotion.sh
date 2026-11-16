#!/usr/bin/env bash
# Promotion pull request for the qemu-3dfx pin (submodules/qemu-3dfx). The pin moves only through
# this PR: one branch, one PR, showing what changed upstream and whether our port still applies and
# builds. It never pushes to main and never merges. Two steps, so the one that builds upstream code
# holds no token that can write to this repository:
#
#   scripts/qemu-3dfx-promotion.sh check [options]
#       Read-only. Compares the pin on this checkout (main) with the master of the submodule's
#       repository and writes its decision and everything publish needs to --out DIR:
#         decision   nothing    upstream has nothing beyond the pin, and no PR is open
#                    close      upstream has nothing beyond the pin; a promotion PR is still open
#                    skip       the open PR already shows this target against this main (same
#                               fingerprint) and is not a draft (a draft, a failed check, is redone)
#                    hands-off  promote/qemu-3dfx has commits the promotion didn't make (a hand fix)
#                    update     the PR is to be opened or updated
#         new        the new pin (40 hex);  failed  1 when a check failed, else 0
#         title, body.md         the PR's title and body
#         port.patch             the port, refreshed by scripts/refresh-qemu-3dfx-patch.sh, when it
#                                no longer applied and the refresh worked
#         check.log, build.log   the logs
#       For update it moves submodules/qemu-3dfx to the new pin and runs
#       scripts/refresh-qemu-3dfx-patch.sh --check (and the refresh when the port doesn't apply) and
#       scripts/check-qemu-3dfx-build.sh. The checkout is put back afterwards.
#     --from SHA     the old pin (default: the gitlink of HEAD)
#     --to REF       the new pin (default: master of the submodule's repository)
#     --force        decide update even when the fingerprint is the same
#     --skip-build   leave out check-qemu-3dfx-build.sh (reported as "not run")
#     --jobs N       passed to check-qemu-3dfx-build.sh
#     --out DIR      default: build/qemu-3dfx-promotion
#     --pr-json FILE the open PR as `gh pr list --json number,body,isDraft` gives it, instead of
#                    asking GitHub (gh needs only read access: GH_TOKEN with pull-requests: read)
#
#   scripts/qemu-3dfx-promotion.sh publish --in DIR [--dry-run] [--pr-json FILE]
#       Carries out check's decision from DIR, treating everything in it as data: it runs nothing
#       from DIR or from qemu-3dfx and builds nothing. It checks that the new pin is 40 hex and in
#       the history of master as fetched here, the title, the size of the body, the port file;
#       works out the open PR and the pin on main itself; then commits main + the new gitlink (+ the
#       port) and force-pushes promote/qemu-3dfx, and opens, edits, readies or closes the PR. Again
#       leaves a branch with someone else's commits alone.
#       Needs gh with GH_TOKEN, a token that may write pull requests, and for the push PUSH_TOKEN (the
#       same token; used for that command only), except with --dry-run, which prints the push and gh
#       commands instead.
#
#   scripts/qemu-3dfx-promotion.sh body --from SHA --to SHA [options]
#       Only prints the PR body (Markdown) for the range; changes nothing, writes nothing.
#     --check-rc N --check-log FILE   result of refresh-qemu-3dfx-patch.sh --check
#     --build-rc N --build-log FILE   result of check-qemu-3dfx-build.sh (rc "skip": not run)
#     --port-changed                  the port is changed by the PR
#     --fingerprint X                 hidden marker, see check
#
#   --repo DIR   the qemu-3dfx clone with both commits (default: submodules/qemu-3dfx)
#
# Exit status: 0 done (whatever the checks said), 2 usage, setup or validation error, else what failed.
set -euo pipefail

top=$(cd "$(dirname "$0")/.." && pwd)
sub="submodules/qemu-3dfx"
branch="promote/qemu-3dfx"
port="submodules/pve-qemu-qemu-3dfx.patch"
marker="qemu-3dfx-promotion"
# In every commit this makes; a branch with other commits on it is someone's work and left alone
trailer="Generated-by: scripts/qemu-3dfx-promotion.sh"
tail_lines=40
max_body=60000
max_port=1048576

usage() {
    sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
}
die() { echo "qemu-3dfx-promotion: $*" >&2; exit 2; }
say() { echo "qemu-3dfx-promotion: $*" >&2; }

[ $# -gt 0 ] || usage
cmd="$1"; shift
case "$cmd" in check|publish|body) ;; -h|--help) usage ;; *) echo "qemu-3dfx-promotion: unknown command '$cmd'" >&2; usage ;; esac

from="" to="" repo="$top/$sub" dry_run=0 force=0 skip_build=0 jobs="" out="$top/build/qemu-3dfx-promotion"
in="" pr_json="" check_rc="" check_log="" build_rc="" build_log="" port_changed=0 fingerprint=""
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
        --in) in="${2:?}"; shift 2 ;;
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

# The submodule's URL from .gitmodules of this checkout, as https
sub_url() {
    local url
    url=$(git -C "$top" config -f .gitmodules "submodule.$sub.url")
    case "$url" in git@github.com:*) url="https://github.com/${url#git@github.com:}" ;; esac
    echo "$url"
}
web_url() { local url; url=$(sub_url); echo "${url%.git}"; }

# Upstream text (subject, author) for a table cell: one line, no control characters, at most 100
# characters, in a code span so nothing in it links, mentions or closes an issue; a backtick
# becomes ' and a pipe ¦ so it can't end the span or the cell
cell() {
    local s
    s=$(tr -d '\000-\037\177' | tr '`' "'" | sed -e 's/|/¦/g')
    [ "${#s}" -le 100 ] || s="${s:0:99}…"
    printf "\`%s\`" "${s:-(empty)}"
}

# A fence longer than any run of backticks in the text on stdin (at least 3)
fence_for() {
    awk '{ while (match($0, /`+/)) { if (RLENGTH > m) m = RLENGTH; $0 = substr($0, RSTART + RLENGTH) } }
        END { n = (m >= 3 ? m + 1 : 3); s = ""; for (i = 0; i < n; i++) s = s "`"; print s }'
}

# Text in a fenced block that nothing in it can close
fenced() {
    local lang="$1" text fence
    text=$(cut -c1-300)
    [ -n "$text" ] || text="(empty)"
    fence=$(fence_for <<<"$text")
    printf '%s%s\n%s\n%s\n' "$fence" "$lang" "$text" "$fence"
}

log_tail() {
    echo
    echo "<details><summary>Last $tail_lines lines of the log</summary>"
    echo
    if [ -s "$1" ]; then tail -n "$tail_lines" "$1" | fenced text; else echo "(empty)" | fenced text; fi
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
    local url old new n ancestor=1 line
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
        line=$(grep -E '^check-qemu-3dfx-build: (PASS|FAIL)' "$build_log" | tail -n 1 || true)
        if [ -n "$line" ]; then
            echo
            printf '%s' "$line" | cell
            echo
        fi
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
        fenced text <<<"$stat"
        echo
        echo '<details><summary>Diff of the patch files (first 300 lines)</summary>'
        echo
        git -C "$repo" diff "$old" "$new" -- ':(glob)*.patch' | head -n 300 | fenced diff
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

# ---- shared by check and publish ------------------------------------------------------------------

cd "$top"

# The open promotion PR: number, draft, fingerprint (read-only)
read_pr() {
    local pr
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
    [[ "$pr_number" =~ ^[0-9]*$ ]] || die "unexpected PR number '$pr_number'"
}

# git with PUSH_TOKEN for github.com, for this one command (environment, not argv or .git/config)
git_auth() {
    if [ -n "${PUSH_TOKEN:-}" ]; then
        GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" \
            GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$PUSH_TOKEN" | base64 | tr -d '\n')" \
            git "$@"
    else
        git "$@"
    fi
}

# How many commits on promote/qemu-3dfx the promotion didn't make (0 when there is no branch)
foreign_commits() {
    local base="$1" tip c n=0
    tip=$(git_auth ls-remote --exit-code origin "refs/heads/$branch" | cut -f1) || { echo 0; return; }
    [ -n "$tip" ] || { echo 0; return; }
    # base..tip is the branch's own commits only with main's history here
    [ "$(git rev-parse --is-shallow-repository)" = false ] || git_auth fetch -q --unshallow origin
    git_auth fetch -q origin "refs/heads/$branch"
    for c in $(git rev-list "$base..$tip"); do
        git log -1 --format=%B "$c" | grep -q -x -F "$trailer" || n=$((n + 1))
    done
    echo "$n"
}

# ---- check ---------------------------------------------------------------------------------------

if [ "$cmd" = check ]; then
    url=$(sub_url)
    mkdir -p "$out"
    rm -f "$out/decision" "$out/new" "$out/failed" "$out/title" "$out/body.md" "$out/port.patch"
    decide() { echo "$1" > "$out/decision"; say "decision: $1"; }

    # The submodule at the old pin, with upstream's master fetched
    old=${from:-$(git rev-parse "HEAD:$sub")}
    [ -e "$sub/.git" ] || git submodule update --init "$sub"
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
    echo "$new" > "$out/new"
    read_pr

    if [ "$old" = "$new" ] || git -C "$sub" merge-base --is-ancestor "$new" "$old"; then
        say "upstream has nothing beyond the pin"
        if [ -n "$pr_number" ]; then decide close; else decide nothing; fi
        exit 0
    fi
    [ "$(git rev-parse "HEAD:$sub")" != "$new" ] \
        || die "main already has qemu-3dfx at ${new:0:7} (--from ${old:0:7} is not its pin)"

    # What the checks depend on: the range, and on main the QEMU tree, our patches and these scripts
    fingerprint=$( { echo "$old $new"; git rev-parse HEAD:submodules/pve-qemu; git hash-object submodules/pve-qemu.patch \
        "$port" submodules/qemu-3dfx.patch scripts/refresh-qemu-3dfx-patch.sh scripts/check-qemu-3dfx-build.sh \
        scripts/check-qemu-extras.sh scripts/qemu-3dfx-promotion.sh; } | git hash-object --stdin)
    # A draft is a failed check: that one runs again every time (it may have been the network)
    if [ "$force" = 0 ] && [ -n "$pr_number" ] && [ "$pr_draft" = false ] && [ "$pr_fingerprint" = "$fingerprint" ]; then
        say "#$pr_number already shows ${new:0:7} against this main (fingerprint ${fingerprint:0:12})"
        decide skip
        exit 0
    fi

    # Someone pushed to the branch (a hand fix of the port): leave it to them and to the PR's checks
    others=$(foreign_commits "$(git rev-parse HEAD)")
    if [ "$others" -gt 0 ]; then
        say "$branch has $others commit(s) not made by the promotion"
        decide hands-off
        exit 0
    fi

    # shellcheck disable=SC2329 # run by the trap
    cleanup() {
        git -C "$sub" checkout -q "$sub_before" 2>/dev/null || true
        git checkout -q -- "$port" 2>/dev/null || true
    }
    trap cleanup EXIT
    git -C "$sub" checkout -q "$new"

    # pve-qemu and its QEMU, for the checks
    [ -f submodules/pve-qemu/debian/rules ] || git submodule update --init submodules/pve-qemu
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
            cp "$port" "$out/port.patch"
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
    echo "$failed" > "$out/failed"

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
    decide update
    exit 0
fi

# ---- publish -------------------------------------------------------------------------------------

[ -n "$in" ] && [ -d "$in" ] || die "publish needs --in DIR (the output of check)"
w() {
    if [ "$dry_run" = 1 ]; then
        printf 'dry-run:' >&2; printf ' %q' "$@" >&2; echo >&2
    else
        "$@"
    fi
}
decision=$(head -c 20 "$in/decision" 2>/dev/null | tr -d '\n') || true
case "$decision" in
    nothing|skip|hands-off) say "decision: $decision; nothing to publish"; exit 0 ;;
    close|update) ;;
    *) die "invalid decision '$decision'" ;;
esac

# The fork's master, fetched here (commits only), to check the new pin against
url=$(sub_url)
fork=$(mktemp -d)
wt=""
cleanup() {
    rm -rf "$fork"
    [ -z "$wt" ] || { git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"; git worktree prune; }
}
trap cleanup EXIT
git init -q --bare "$fork"
git -C "$fork" fetch -q --filter=blob:none --no-tags "$url" "+refs/heads/master:refs/heads/master"
master=$(git -C "$fork" rev-parse refs/heads/master)
old=$(git rev-parse "HEAD:$sub")
base=$(git rev-parse HEAD)
read_pr

if [ "$decision" = close ]; then
    if ! { git -C "$fork" cat-file -e "$old^{commit}" 2>/dev/null && git -C "$fork" merge-base --is-ancestor "$master" "$old"; }; then
        die "close: upstream's master ${master:0:7} has commits beyond the pin ${old:0:7}"
    fi
    if [ -z "$pr_number" ]; then
        say "close: no open PR"
        exit 0
    fi
    say "closing #$pr_number: the pin caught up"
    w gh pr close "$pr_number" --delete-branch \
        --comment "The pin on main is at ${old:0:7}, which has everything upstream's master (${master:0:7}) has. Nothing left to promote."
    exit 0
fi

# update: validate what check wrote
new=$(head -c 41 "$in/new" | tr -d '\n')
[[ "$new" =~ ^[0-9a-f]{40}$ ]] || die "the new pin is not a commit id"
[ "$new" != "$old" ] || die "main is already at ${new:0:7}"
if ! { git -C "$fork" cat-file -e "$new^{commit}" 2>/dev/null && git -C "$fork" merge-base --is-ancestor "$new" "$master"; }; then
    die "${new:0:7} is not in the history of upstream's master (${master:0:7})"
fi
failed=$(head -c 2 "$in/failed" | tr -d '\n')
case "$failed" in 0) suffix="" ;; 1) suffix=" (3dfx check failed)" ;; *) die "invalid failed flag" ;; esac
title=$(head -c 200 "$in/title" | head -n 1)
[ "$title" = "chore(deps): promote qemu-3dfx to ${new:0:7}$suffix" ] || die "unexpected title '$title'"
body="$in/body.md"
[ -s "$body" ] || die "no body"
[ "$(wc -c < "$body")" -le "$max_body" ] || die "the body is larger than $max_body bytes"
port_new=""
if [ -e "$in/port.patch" ]; then
    [ -f "$in/port.patch" ] && [ ! -L "$in/port.patch" ] || die "port.patch is not a regular file"
    [ "$(wc -c < "$in/port.patch")" -le "$max_port" ] || die "port.patch is larger than $max_port bytes"
    head -n 1 "$in/port.patch" | grep -q '^diff --git a/' || die "port.patch is not a patch"
    port_new="$in/port.patch"
fi

others=$(foreign_commits "$base")
if [ "$others" -gt 0 ]; then
    say "$branch has $others commit(s) not made by the promotion; leaving it alone"
    exit 0
fi

# The branch: main + the new gitlink (+ the port), in a worktree so this checkout stays as it is
wt=$(mktemp -d)
rmdir "$wt"
git worktree add -q --detach "$wt" "$base"
git -C "$wt" update-index --cacheinfo "160000,$new,$sub"
if [ -n "$port_new" ]; then
    cp "$port_new" "$wt/$port"
    git -C "$wt" add -- "$port"
fi
msg="$title

Upstream: $(web_url)/compare/$old...$new"
[ -z "$port_new" ] || msg="$msg
The port ($port) was refreshed by scripts/refresh-qemu-3dfx-patch.sh."
msg="$msg

$trailer"
git -C "$wt" commit -q --no-verify -m "$msg"
say "branch $branch: $(git -C "$wt" log -1 --format='%h %s') on ${base:0:7}"
git -C "$wt" diff --stat HEAD~1 HEAD >&2
if [ "$dry_run" = 1 ]; then
    w git -C "$wt" push --force origin "HEAD:refs/heads/$branch"
else
    git_auth -C "$wt" push --force origin "HEAD:refs/heads/$branch"
fi

# The PR: one, updated in place; a draft while a check fails
if [ -n "$pr_number" ]; then
    w gh pr edit "$pr_number" --title "$title" --body-file "$body"
    if [ "$failed" = 1 ] && [ "$pr_draft" = false ]; then
        w gh pr ready "$pr_number" --undo
    elif [ "$failed" = 0 ] && [ "$pr_draft" = true ]; then
        w gh pr ready "$pr_number"
    fi
else
    draft=()
    [ "$failed" = 0 ] || draft=(--draft)
    w gh pr create --base main --head "$branch" --title "$title" --body-file "$body" "${draft[@]}"
fi
