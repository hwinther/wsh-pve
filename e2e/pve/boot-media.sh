#!/bin/sh
# The Alpine virt CDs the boot test starts (e2e.yml, job `boot`; e2e/README.md, "Booting a guest
# through PVE"), pinned by URL and sha256 (dl-cdn.alpinelinux.org, v3.24 latest-releases.yaml). The
# pins live only here: e2e.yml's boot job and media-cache.yml both call this script, so the Actions
# cache key and the files always match.
#
#   boot-media.sh key        prints the Actions cache key of the two CDs
#   boot-media.sh fetch DIR  downloads into DIR each CD that is missing or not the pinned one, then
#                            checks both (exit 1 when one doesn't match after the download)
#
# DIR gets alpine-virt-x86_64.iso and alpine-virt-aarch64.iso, the names boot-test.sh is given.
set -eu

X86_URL=https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.4-x86_64.iso
X86_SHA256=157d353f8e54252cad2d9812a0d56bb7fa2231fc154a110e1d180d7480ef8b4f
ARM_URL=https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-virt-3.24.4-aarch64.iso
ARM_SHA256=cf88d8ba67389d20d9ed307366b52e487c15d7d3ee3233b62b95f709daa1d430

get() {
	file=$1/$2
	if [ ! -f "$file" ] || ! echo "$4  $file" | sha256sum -c --quiet >/dev/null 2>&1; then
		curl -fsSL --retry 3 -o "$file.part" "$3"
		mv "$file.part" "$file"
	fi
	echo "$4  $file" | sha256sum -c
}

case "${1:-}" in
key)
	echo "alpine-virt-iso-$X86_SHA256-$ARM_SHA256"
	;;
fetch)
	[ $# -eq 2 ] || { echo "usage: $0 fetch DIR" >&2; exit 2; }
	mkdir -p "$2"
	get "$2" alpine-virt-x86_64.iso "$X86_URL" "$X86_SHA256"
	get "$2" alpine-virt-aarch64.iso "$ARM_URL" "$ARM_SHA256"
	;;
*)
	echo "usage: $0 key | fetch DIR" >&2
	exit 2
	;;
esac
