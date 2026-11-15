#!/usr/bin/env bash
# Keeps one GitHub issue per optional extra of pve-qemu-kvm that a build left out, from the result of
# scripts/check-qemu-extras.sh (--result). The package is published either way (the extras never fail
# the build); this is how a missing one gets noticed:
#
#   missing  open an issue for the extra, with the build log lines that explain it; when one is open
#            already, update it and comment, once per package version
#   present  comment on the extra's open issue and close it
#   absent   (not expected in this build) nothing
#
#   scripts/report-qemu-extras.sh --result extras.tsv --version 11.1.3-2+wsh5 [options]
#
#   --log FILE       the output of `make pve-qemu-bundle`, for the log excerpt
#   --commit SHA     the wsh-pve commit built
#   --run-url URL    the workflow run
#   --repo OWNER/NAME  (default: $GH_REPO or $GITHUB_REPOSITORY)
#   --assignee USER  assign new issues
#   --dry-run        print the gh commands that would change issues instead of running them
#   --issues FILE    the open issues as `gh issue list --json number,title,body` gives them, instead of
#                    asking GitHub (to try it without a token)
#
# Needs gh and jq; gh needs a token that may write issues (GH_TOKEN), except with --dry-run --issues.
# Exit status: 0 whatever the extras are (a missing one is not an error), 2 on a usage error, else gh's.
set -euo pipefail

result="" log="" version="" commit="" run_url="" assignee="" dry_run=0 issues_file=""
repo="${GH_REPO:-${GITHUB_REPOSITORY:-}}"

usage() {
    sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --result) result="${2:?}"; shift 2 ;;
        --log) log="${2:?}"; shift 2 ;;
        --version) version="${2:?}"; shift 2 ;;
        --commit) commit="${2-}"; shift 2 ;;
        --run-url) run_url="${2-}"; shift 2 ;;
        --repo) repo="${2:?}"; shift 2 ;;
        --assignee) assignee="${2-}"; shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        --issues) issues_file="${2:?}"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "report-qemu-extras: unknown option '$1'" >&2; usage ;;
    esac
done
[ -f "$result" ] || { echo "report-qemu-extras: --result FILE is required" >&2; usage; }
[ -n "$version" ] || { echo "report-qemu-extras: --version is required" >&2; usage; }
[ -n "$repo" ] || { echo "report-qemu-extras: --repo is required (or GH_REPO)" >&2; usage; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# A gh command that changes an issue: run it, or print it with --dry-run.
gh_write() {
    if [ "$dry_run" = 1 ]; then
        printf '+'
        printf ' %q' gh "$@"
        printf '\n'
    else
        gh "$@"
    fi
}

if [ -n "$issues_file" ]; then
    cp "$issues_file" "$work/issues.json"
else
    gh issue list --repo "$repo" --state open --limit 500 --json number,title,body > "$work/issues.json"
fi

title_of() { echo "pve-qemu-kvm built without the optional extra: $1"; }
marker_of() { echo "<!-- optional-extra: $1 -->"; }

effect_of() {
    case "$1" in
        3dfx) cat <<'EOF'
`/usr/bin/qemu-system-x86_64-3dfx` is not in the package. VMs with Display → **Enable 3DFX/Mesa** (`vga: ...,mesa=1`) don't start: qemu-server stops with `unable to stat file '/usr/bin/qemu-system-x86_64-3dfx'`. Other VMs are not affected, and no host binary matches the `qemu-3dfx-drivers-*` guest drivers of this build.
EOF
            ;;
        openbios) cat <<'EOF'
The package has QEMU's prebuilt `openbios-sparc32` and `QEMU,cgthree.bin` instead of the ones from `openbios/`. sparc32 VMs that boot OpenBIOS lose the fixes: with the disk on SCSI target 3 there is no `disk` alias and the default boot fails ("No valid state has been set by load or init-program"), and a cg3 larger than 1024x768 takes a data access fault at power-on (`submodules/SPARC.md`).
EOF
            ;;
        sun-proms) cat <<'EOF'
`ss5.bin`, `ss10_v2.25_rom` or `ss20_v2.25_rom` is not in `/usr/share/kvm`. The UI and API still offer them as firmware (`bios`), and VMs that use one don't start because QEMU can't load the PROM. VMs with OpenBIOS are not affected.
EOF
            ;;
    esac
}

# Markdown: the backquotes are meant literally.
# shellcheck disable=SC2016
fix_of() {
    case "$1" in
        3dfx) echo 'Refresh `submodules/pve-qemu-qemu-3dfx.patch` (and `submodules/qemu-3dfx.patch`) for the QEMU in this pve-qemu: `make pve-qemu-3dfx` shows the rejected hunks.' ;;
        openbios) echo '`make openbios-sparc32` builds `openbios/Dockerfile` alone. After a QEMU update, check `OPENBIOS_REF` and `openbios/patches/`.' ;;
        sun-proms) echo 'The build needs read access to the private `submodules/sparc` repository (`WORKFLOW_TOKEN`).' ;;
    esac
}

# The lines of the build log that explain why the extra is missing: from where its make target starts
# to its "WARNING: optional extra <name> missing" line, errors only (for 3dfx: each rejected hunk with
# the file it is for).
excerpt_of() {
    local name="$1" start errors
    case "$name" in
        3dfx) start='Building pve-qemu with 3dfx support' errors='FAILED|dpkg-source: error|dpkg-buildpackage: error|cannot stat|[Ee]rror:' ;;
        openbios) start='Building openbios-sparc32' errors='ERROR|[Ee]rror:|failed' ;;
        sun-proms) start='Restoring sparc submodule' errors='fatal:|[Ee]rror:|Permission denied|not found' ;;
    esac
    if [ -z "$log" ] || [ ! -f "$log" ]; then
        echo "(no build log)"
        return
    fi
    sed -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r$//' "$log" | awk -v name="$name" -v start="$start" -v errors="$errors" -v warn="^WARNING: optional extra $name missing" '
        found { next }
        !on && index($0, start) { on = 1 }
        !on { next }
        /^patching file / { file = $0; shown = 0; next }
        $0 ~ warn { print; found = 1; next }
        $0 ~ errors {
            if (file != "" && !shown && /FAILED/) { print file; shown = 1 }
            print
        }
        END { if (!found) print "(no \"WARNING: optional extra " name " missing\" line in the build log)" }
    ' | tail -n 40
}

while IFS=$'\t' read -r name state detail; do
    [ -n "$name" ] || continue
    title=$(title_of "$name")
    marker=$(marker_of "$name")
    number=$(jq -r --arg m "$marker" '[.[] | select((.body // "") | contains($m))][0].number // empty' "$work/issues.json")
    seen=$(jq -r --arg m "$marker" --arg v "<!-- last-version: $version -->" \
        '[.[] | select(((.body // "") | contains($m)) and ((.body // "") | contains($v)))] | length' "$work/issues.json")

    case "$state" in
        missing)
            body="$work/body-$name.md"
            {
                echo "$marker"
                echo "<!-- last-version: $version -->"
                echo "\`pve-qemu-kvm\` **$version** was built and published without the optional extra **$name**."
                echo
                [ -n "$commit" ] && echo "- Commit: https://github.com/$repo/commit/$commit"
                [ -n "$run_url" ] && echo "- Build: $run_url"
                echo "- Check (\`scripts/check-qemu-extras.sh\`): $detail"
                echo
                echo "**Effect:** $(effect_of "$name")"
                echo
                echo "**Build log:**"
                echo
                echo '```text'
                excerpt_of "$name"
                echo '```'
                echo
                echo "**Fix:** $(fix_of "$name")"
                echo
                echo "Optional extras never fail the package build. Later builds update this issue while **$name** is missing and close it when a build has it again."
            } > "$body"
            show_body=1
            if [ -z "$number" ]; then
                echo "$name: missing, opening an issue"
                args=(issue create --repo "$repo" --title "$title" --body-file "$body")
                [ -n "$assignee" ] && args+=(--assignee "$assignee")
                gh_write "${args[@]}"
            elif [ "$seen" -gt 0 ]; then
                echo "$name: missing, #$number already has $version"
                show_body=0
            else
                echo "$name: missing, updating #$number"
                gh_write issue edit "$number" --repo "$repo" --title "$title" --body-file "$body"
                gh_write issue comment "$number" --repo "$repo" \
                    --body "Still missing in **$version**${run_url:+ ($run_url)}."
            fi
            if [ "$dry_run" = 1 ] && [ "$show_body" = 1 ]; then
                sed 's/^/    | /' "$body"
            fi
            ;;
        present)
            if [ -n "$number" ]; then
                echo "$name: present, closing #$number"
                gh_write issue close "$number" --repo "$repo" --reason completed \
                    --comment "**$name** is back in \`pve-qemu-kvm\` **$version**${run_url:+ ($run_url)}: $detail"
            else
                echo "$name: present"
            fi
            ;;
        absent)
            echo "$name: absent, not expected in this build${number:+ (leaving #$number as it is)}"
            ;;
        *)
            echo "report-qemu-extras: unknown state '$state' for $name" >&2
            exit 2
            ;;
    esac
done < "$result"
