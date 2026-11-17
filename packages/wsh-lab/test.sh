#!/bin/sh
# Test a built wsh-lab package in a clean Debian 13 (as root, in a throwaway container):
#
#   docker run --rm -v "$PWD/build/wsh-lab:/deb:ro" -v "$PWD/packages/wsh-lab/test.sh:/test.sh:ro" \
#     debian:trixie sh /test.sh /deb/wsh-lab_<version>_all.deb
#
# apt installs it with its dependencies; wsh-lab --version/--help, targets, media --dir and the refusal
# off a PVE node work; the catalogue's unit tests pass against the installed copy; wsh-lab-mcp explains
# its setup; with WSH_LAB_TEST_MCP=1 also `wsh-lab-mcp --setup` (network: PyPI) and the server's
# --check from the venv. Then `apt purge` must leave nothing of the package behind: no file of it, no
# venv, no __pycache__, no /var/lib/wsh-lab. Exit 0 when everything passed.
set -eu
DEB=${1:?usage: test.sh /path/to/wsh-lab_VERSION_all.deb}
export DEBIAN_FRONTEND=noninteractive
step() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

# What exists before the package, to compare with what is left after the purge
snapshot() {
	find / -xdev \( -path /proc -o -path /sys -o -path /dev -o -path /run -o -path /tmp -o -path /var/tmp \
		-o -path /var/cache -o -path /var/log -o -path /var/lib/apt -o -path /var/lib/dpkg \) -prune \
		-o -print | sort
}

step "apt install $DEB"
apt-get update -qq
# python3 and ca-certificates are on every PVE node; python3-venv (the MCP test) would otherwise
# bring ca-certificates along, which apt keeps as a recommendation of python3 after the purge
apt-get install --no-install-recommends --assume-yes -qq python3 ca-certificates > /dev/null
snapshot > /tmp/before
apt-get install --no-install-recommends --assume-yes "$DEB"
dpkg -s wsh-lab | grep -E '^(Status|Version|Depends):'
for p in python3-pyte python3-pil fonts-dejavu-core; do
	dpkg -s "$p" > /dev/null 2>&1 || fail "dependency $p not installed"
done

step "wsh-lab --version, --help"
version=$(wsh-lab --version)
[ "$version" = "$(dpkg-query -W -f '${Version}' wsh-lab)" ] || fail "wsh-lab --version says $version"
wsh-lab --help | tee /tmp/help
grep -q '^usage: wsh-lab ' /tmp/help || fail "wsh-lab --help doesn't name the command"
wsh-lab install --help > /dev/null

step "wsh-lab targets"
wsh-lab targets | tee /tmp/targets
grep -q '^sol26-ss5 .*automated' /tmp/targets || fail "sol26-ss5 isn't listed as automated"
wsh-lab targets --json | python3 -c 'import json, sys; t = json.load(sys.stdin); assert "sol26-ss20" in t, t.keys()'

step "wsh-lab media --dir"
mkdir -p /tmp/media
rc=0
wsh-lab media sol26-ss5 --dir /tmp/media > /tmp/media.out || rc=$?
cat /tmp/media.out
[ "$rc" = 1 ] && grep -q '^  missing .*solaris_2.6_598_sparc.iso' /tmp/media.out || fail "an empty directory isn't reported as missing (rc $rc)"
head -c 1048576 /dev/zero > /tmp/media/solaris_2.6_598_sparc.iso
rc=0
wsh-lab media sol26-ss5 --dir /tmp/media --no-checksum > /tmp/media.out || rc=$?
cat /tmp/media.out
[ "$rc" = 1 ] && grep -q 'size differs' /tmp/media.out || fail "a file of the wrong size isn't refused (rc $rc)"
rm -r /tmp/media

step "wsh-lab install off a PVE node is refused"
rc=0
wsh-lab install sol26-ss5 --vmid 120 > /tmp/install.out 2>&1 || rc=$?
cat /tmp/install.out
[ "$rc" != 0 ] && grep -q 'runs on the PVE node' /tmp/install.out || fail "install without qm wasn't refused (rc $rc)"

step "the catalogue's unit tests against the installed copy"
(cd / && python3 -m unittest discover -v -s /usr/share/wsh-lab/tests -p 'test_targets.py')

step "wsh-lab-mcp without its venv"
rc=0
wsh-lab-mcp --vm 1 --check > /tmp/mcp.out 2> /tmp/mcp.err || rc=$?
cat /tmp/mcp.err
[ "$rc" = 1 ] && grep -q 'wsh-lab-mcp --setup' /tmp/mcp.err || fail "wsh-lab-mcp doesn't explain its setup (rc $rc)"
[ ! -s /tmp/mcp.out ] || fail "wsh-lab-mcp wrote to stdout (the MCP stream)"
wsh-lab-mcp --help 2> /dev/null || fail "wsh-lab-mcp --help without a venv"

if [ "${WSH_LAB_TEST_MCP:-0}" = 1 ]; then
	step "wsh-lab-mcp --setup (PyPI) and --check"
	rc=0
	wsh-lab-mcp --setup 2> /tmp/setup.err || rc=$?
	[ "$rc" = 1 ] && grep -q 'apt install python3-venv' /tmp/setup.err || fail "--setup without python3-venv (rc $rc)"
	apt-get install --no-install-recommends --assume-yes -qq python3-venv > /dev/null
	apt-mark auto python3-venv > /dev/null  # autoremoved with the rest at the end
	wsh-lab-mcp --setup
	wsh-lab-mcp --lab demo=/tmp/no-such-run --check | tee /tmp/check.json
	python3 -c 'import json; d = json.load(open("/tmp/check.json")); assert "list_vms" in d["tools"], d'
	[ -d /var/lib/wsh-lab/mcp-venv ] || fail "no venv"
fi

step "apt purge"
apt-get purge --assume-yes wsh-lab
apt-get autoremove --purge --assume-yes -qq > /dev/null
deb_dir=$(dirname "$(realpath "$DEB")")
left=$(find / -xdev \( -path /proc -o -path /sys -o -path "$deb_dir" \) -prune -o \( -name '*wsh-lab*' -o -name '*wsh_lab*' \) -print)
[ -z "$left" ] || fail "left after the purge: $left"
snapshot > /tmp/after
if ! diff /tmp/before /tmp/after > /tmp/diff; then
	cat /tmp/diff
	fail "the file system differs from before the install"
fi
echo "nothing left behind"

step "all passed ($version)"
