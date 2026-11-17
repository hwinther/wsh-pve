#!/bin/sh
# The version of the wsh-lab package at the checked-out commit, from git, printed as shell
# assignments (eval "$(packages/wsh-lab/version.sh)"):
#
#   WSH_LAB_VERSION=0.<N>+g<sha7>    N: commits on the path to HEAD that touch the package's inputs
#   WSH_LAB_COMMIT=<sha>             the newest of them; sha7 is its first 7 hex digits
#   WSH_LAB_EPOCH=<unix time>        its committer date (SOURCE_DATE_EPOCH, the changelog's date)
#
# The inputs are the files the package is built from (INPUTS below). Every commit that changes one
# adds one to N, so on main (linear: squash merges) the version only goes up, and any later commit
# that leaves the inputs alone gives the same version, commit and date: the same package. Only ever
# add paths to INPUTS (removing one could lower N). A working tree with uncommitted changes to the
# inputs gets ".dirty" appended (local builds only). Needs the full history (fetch-depth: 0).
set -eu
cd "$(dirname "$0")/../.."

INPUTS="packages/wsh-lab
e2e/sparc/lab.py
e2e/sparc/recording.py
e2e/sparc/install.py
e2e/sparc/targets.py
e2e/sparc/sunlabel.py
e2e/sparc/mcp_server.py
e2e/sparc/scenarios
e2e/sparc/tests/test_targets.py
e2e/sparc/lab-requirements.txt
e2e/sparc/mcp-requirements.txt"

if [ "$(git rev-parse --is-shallow-repository)" = true ]; then
	echo "version.sh: a shallow clone can't count the commits (fetch the full history)" >&2
	exit 1
fi
# shellcheck disable=SC2086 # INPUTS is a list of paths without spaces
n=$(git rev-list --count HEAD -- $INPUTS)
# shellcheck disable=SC2086
commit=$(git log -1 --format=%H -- $INPUTS)
# shellcheck disable=SC2086
epoch=$(git log -1 --format=%ct -- $INPUTS)
version="0.$n+g$(printf %.7s "$commit")"
# shellcheck disable=SC2086
if [ -n "$(git status --porcelain -- $INPUTS)" ]; then
	version="$version.dirty"
fi
echo "WSH_LAB_VERSION=$version"
echo "WSH_LAB_COMMIT=$commit"
echo "WSH_LAB_EPOCH=$epoch"
