#!/usr/bin/env bash
# wisp-test: build a C program against nolibc or uClibc-ng (or take a static binary), boot it as /test in wisp
# (e2e/wisp/, a Linux tinyconfig kernel with a nolibc PID 1) under QEMU, and report how it ended.
# action.yml runs this script; it also runs on its own on a Debian or Ubuntu host. Settings come
# from the environment (the action's inputs, see README.md):
#
#   WISP_ARCH        sparc32 (default), sparc64 or x86_64
#   WISP_SOURCES     C files to build (whitespace-separated, globs allowed), or
#   WISP_BINARY      a static binary for the architecture instead
#   WISP_LIBC        nolibc (default) or uclibc (sparc32 and x86_64)
#   WISP_TOOLCHAIN   local SDK tarball instead of downloading WISP_TOOLCHAIN_URL
#   WISP_TOOLCHAIN_URL     SDK tarball URL (default: wisp-toolchain release for WISP_ARCH)
#   WISP_TOOLCHAIN_SHA256  the SDK tarball's SHA-256, checked when set
#   WISP_CFLAGS      more compiler flags (default optimisation: -O2)
#   WISP_ARGS        arguments for the program (whitespace-separated, no quoting)
#   WISP_MODE        test (default) or run
#   WISP_NETWORK     true to boot kernel-net with DHCP
#   WISP_FORWARD     guest TCP port to expose on loopback as WISP_PORT
#   WISP_READY       optional console regex for WISP_CHECK
#   WISP_CHECK       runner shell command whose exit status decides the result
#   WISP_TIMEOUT     seconds for the whole boot (default 60)
#   WISP_MACHINE     QEMU -M (default SS-5, sun4u, pc)
#   WISP_QEMU_ARGS   more QEMU arguments (whitespace-separated)
#   WISP_KIT         a kit directory or wisp-test-kit.tar.xz (default: download WISP_KIT_URL)
#   WISP_KIT_URL     where to download the kit from
#   WISP_KIT_SHA256  the kit tarball's SHA-256, checked when set
#   WISP_INSTALL     true (default): apt-get install what is missing
#   WISP_WORK        work directory (default $RUNNER_TEMP/wisp-test or /tmp/wisp-test)
#
# Exit code 0 when the program exited with 0, 1 otherwise. In GitHub Actions also sets the outputs
# result (pass, fail or error), exit-code, signal, signal-name, seconds, port and log, and writes a line
# to the job summary.
set -euo pipefail

ARCH=${WISP_ARCH:-sparc32}
LIBC=${WISP_LIBC:-nolibc}
TOOLCHAIN=${WISP_TOOLCHAIN:-}
TOOLCHAIN_URL=${WISP_TOOLCHAIN_URL:-https://github.com/hwinther/wsh-pve/releases/download/wisp-toolchain/wisp-toolchain-$ARCH.tar.xz}
TOOLCHAIN_SHA256=${WISP_TOOLCHAIN_SHA256:-}
SOURCES=${WISP_SOURCES:-}
BINARY=${WISP_BINARY:-}
USER_CFLAGS=${WISP_CFLAGS:-}
ARGS=${WISP_ARGS:-}
TIMEOUT=${WISP_TIMEOUT:-60}
MACHINE=${WISP_MACHINE:-}
QEMU_ARGS=${WISP_QEMU_ARGS:-}
KIT=${WISP_KIT:-}
KIT_URL=${WISP_KIT_URL:-https://github.com/hwinther/wsh-pve/releases/download/wisp-test-kit/wisp-test-kit.tar.xz}
KIT_SHA256=${WISP_KIT_SHA256:-}
INSTALL=${WISP_INSTALL:-true}
WORK=${WISP_WORK:-${RUNNER_TEMP:-/tmp}/wisp-test}
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=${WISP_MODE:-test}
NETWORK=${WISP_NETWORK:-false}
FORWARD=${WISP_FORWARD:-}
READY=${WISP_READY:-}
CHECK=${WISP_CHECK:-}

log() { printf 'wisp-test: %s\n' "$*" >&2; }
die() {
	log "$*"
	[ -z "${GITHUB_ACTIONS:-}" ] || printf '::error title=wisp-test::%s\n' "$*"
	output result error
	exit 2
}
output() { [ -z "${GITHUB_OUTPUT:-}" ] || printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"; }

case "$MODE" in test|run) ;; *) die "unknown mode '$MODE'" ;; esac
case "$NETWORK" in true|false) ;; *) die "network must be true or false" ;; esac
if [ -n "$FORWARD" ]; then
	[ "$NETWORK" = true ] || die "forward requires network"
	[[ "$FORWARD" =~ ^[0-9]{1,5}$ ]] && (( 10#$FORWARD >= 1 && 10#$FORWARD <= 65535 )) || die "invalid guest TCP port"
	FORWARD=$((10#$FORWARD))
fi
if [ -n "$READY" ]; then
	[ -n "$CHECK" ] || die "ready requires check"
	if [[ "" =~ $READY ]]; then :; elif [ "$?" = 2 ]; then die "invalid ready regex"; fi
fi

case "$LIBC" in
nolibc) ;;
uclibc)
	case "$ARCH" in
	sparc32) SDK_PREFIX=sparc-buildroot-linux-uclibc ;;
	x86_64) SDK_PREFIX=x86_64-buildroot-linux-uclibc ;;
	*) die "no uClibc-ng SDK for $ARCH; see 'Your own toolchain' in the action README" ;;
	esac ;;
*) die "unknown libc '$LIBC' (nolibc or uclibc)" ;;
esac

# Per architecture: QEMU binary and its package, machine, memory (MiB), compiler and its package,
# compiler flags, ELF machine number, whether nolibc's _start needs replacing (start-sparc.c).
case "$ARCH" in
sparc32)
	QEMU=qemu-system-sparc QEMU_PKG=qemu-system-sparc DEF_MACHINE=SS-5 MEM=128
	CC=sparc64-linux-gnu-gcc CC_PKG=gcc-sparc64-linux-gnu ARCH_CFLAGS="-m32 -mcpu=v8" EM=2 START=1 ;;
sparc64)
	QEMU=qemu-system-sparc64 QEMU_PKG=qemu-system-sparc DEF_MACHINE=sun4u MEM=256
	CC=sparc64-linux-gnu-gcc CC_PKG=gcc-sparc64-linux-gnu ARCH_CFLAGS="-m64" EM=43 START=1 ;;
x86_64)
	QEMU=qemu-system-x86_64 QEMU_PKG=qemu-system-x86 DEF_MACHINE=pc MEM=128
	# -march=x86-64: the baseline QEMU's default CPU (qemu64) runs. Ubuntu 26.04's amd64v3
	# packages (what ubuntu-latest installs on a capable CPU) have a gcc that defaults to
	# x86-64-v3, whose BMI2/AVX2 instructions qemu64 answers with SIGILL.
	CC=x86_64-linux-gnu-gcc CC_PKG=gcc-x86-64-linux-gnu ARCH_CFLAGS="-m64 -march=x86-64" EM=62 START=0
	[ "$(uname -m)" != x86_64 ] || { CC=gcc CC_PKG=gcc; } ;;
*)
	die "unknown arch '$ARCH' (sparc32, sparc64 or x86_64)" ;;
esac
[ -n "$SOURCES" ] || [ -n "$BINARY" ] || die "give sources or binary"
[ -z "$SOURCES" ] || [ -z "$BINARY" ] || die "give sources or binary, not both"
case "$TIMEOUT" in '' | *[!0-9]*) die "timeout must be a number of seconds" ;; esac

rm -rf "$WORK"
mkdir -p "$WORK"
LOG=$WORK/console.log
output log "$LOG"

# Packages: QEMU (its firmware comes along: OpenBIOS and SeaBIOS are in qemu-system-data and
# seabios), the cross compiler when there are sources, curl and xz for the kit.
need=()
command -v "$QEMU" >/dev/null || need+=("$QEMU_PKG")
[ -z "$SOURCES" ] || [ "$LIBC" = uclibc ] || command -v "$CC" >/dev/null || need+=("$CC_PKG")
if [ -z "$KIT" ] || { [ "$LIBC" = uclibc ] && [ -n "$SOURCES" ] && [ -z "$TOOLCHAIN" ]; }; then
	command -v curl >/dev/null || need+=(curl ca-certificates)
fi
[ -z "$FORWARD" ] || command -v python3 >/dev/null || need+=(python3)
command -v xz >/dev/null || need+=(xz-utils)
if [ ${#need[@]} -gt 0 ]; then
	[ "$INSTALL" = true ] || die "missing: ${need[*]} (install is off)"
	sudo=
	[ "$(id -u)" = 0 ] || sudo=sudo
	log "installing ${need[*]}"
	t=$(date +%s)
	$sudo env DEBIAN_FRONTEND=noninteractive apt-get update -qq
	$sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
		"${need[@]}" >/dev/null
	log "installed in $(($(date +%s) - t)) s"
fi

# The kit: kernels (with wisp's PID 1, which runs /test for wisp=test) and the nolibc sysroots.
if [ -z "$KIT" ]; then
	log "downloading $KIT_URL"
	curl -fsSL --retry 3 -o "$WORK/kit.tar.xz" "$KIT_URL" || die "kit download failed: $KIT_URL"
	KIT=$WORK/kit.tar.xz
fi
if [ -f "$KIT" ]; then
	if [ -n "$KIT_SHA256" ]; then
		echo "$KIT_SHA256  $KIT" | sha256sum -c --quiet - || die "kit SHA-256 mismatch"
	fi
	mkdir -p "$WORK/kit"
	tar -xJf "$KIT" -C "$WORK/kit" --strip-components=1
	KIT=$WORK/kit
fi
[ -f "$KIT/VERSION" ] || die "no VERSION in the kit ($KIT)"
fmt=$(sed -n 's/^format=//p' "$KIT/VERSION")
case "$fmt" in 1|2) ;; *) die "unsupported kit format '$fmt' (expected 1 or 2)" ;; esac
if [ "$fmt" = 1 ] && [ "$MODE" = run ]; then die "run mode requires a format 2 kit"; fi
kernel=kernel
if [ "$NETWORK" = true ]; then kernel=kernel-net; fi
[ -f "$KIT/$ARCH/$kernel" ] || die "the kit has no $ARCH/$kernel (network requires a format 2 kit)"
log "kit: $(tr '\n' ' ' < "$KIT/VERSION")"

# The program
if [ -n "$BINARY" ]; then
	[ -f "$BINARY" ] || die "binary not found: $BINARY"
	cp "$BINARY" "$WORK/test"
else
	# shellcheck disable=SC2206 # word splitting and globs are wanted here
	files=($SOURCES)
	for f in "${files[@]}"; do [ -f "$f" ] || die "source not found: $f"; done
	if [ "$LIBC" = uclibc ]; then
		if [ -z "$TOOLCHAIN" ]; then
			log "downloading $TOOLCHAIN_URL"
			TOOLCHAIN=$WORK/toolchain.tar.xz
			curl -fsSL --retry 3 -o "$TOOLCHAIN" "$TOOLCHAIN_URL" || die "toolchain download failed: $TOOLCHAIN_URL"
		fi
		[ -f "$TOOLCHAIN" ] || die "toolchain tarball not found: $TOOLCHAIN"
		if [ -n "$TOOLCHAIN_SHA256" ]; then
			echo "$TOOLCHAIN_SHA256  $TOOLCHAIN" | sha256sum -c --quiet - || die "toolchain SHA-256 mismatch"
		fi
		sdk=$WORK/sdk
		mkdir -p "$sdk"
		tar -xJf "$TOOLCHAIN" -C "$sdk" --strip-components=1 || die "cannot unpack $TOOLCHAIN"
		"$sdk/relocate-sdk.sh" || die "cannot relocate the SDK"
		CC=$sdk/bin/$SDK_PREFIX-gcc
		# shellcheck disable=SC2206
		flags=(-static -O2 $USER_CFLAGS)
	else
		# As e2e/wisp/build.sh builds PID 1: static, no C library but nolibc, the kit's headers only.
		# nolibc.h always, so that a file without any #include still gets the start code
		# shellcheck disable=SC2206
		flags=($ARCH_CFLAGS -static -nostdlib -nostdinc -I"$KIT/$ARCH/include" -include nolibc.h -fno-stack-protector
			-fno-asynchronous-unwind-tables -O2 $USER_CFLAGS)
		if [ "$START" = 1 ]; then
			# nolibc's sparc _start reads argc 96 bytes too low (e2e/wisp/README.md): rename it
			# and link a fixed one
			flags+=(-D_start=wisp_nolibc_start)
			files+=("$HERE/start-sparc.c")
		fi
		# libgcc where the compiler has one for these flags; sparc32 links none: without the multilib
		# package the compiler names its 64-bit libgcc for -m32, and the multilib's 32-bit libgcc is
		# V8+, which the sparc32 kernel refuses. It gets the 64-bit division helpers instead
		# (libgcc-sparc32.c).
		if [ "$ARCH" = sparc32 ]; then
			files+=("$HERE/libgcc-sparc32.c")
		else
			# shellcheck disable=SC2086
			libgcc=$($CC $ARCH_CFLAGS -print-libgcc-file-name 2>/dev/null || true)
			[ ! -f "$libgcc" ] || files+=("$libgcc")
		fi
	fi
	log "$CC ${flags[*]} ${files[*]}"
	"$CC" "${flags[@]}" -o "$WORK/test" "${files[@]}" || die "build failed"
fi
# An ELF for this architecture (byte 18-19: e_machine, in the file's byte order)
magic=$(od -An -tx1 -N4 "$WORK/test" | tr -d ' \n')
[ "$magic" = 7f454c46 ] || die "not an ELF file: ${BINARY:-the build}"
m=$(od -An -tu1 -j18 -N2 "$WORK/test" | awk '{ print ($1 > $2) ? $1 : $2 }')
if [ "$ARCH" = sparc32 ] && [ "$m" = 18 ]; then
	die "a SPARC V8+ binary (EM_SPARC32PLUS: V9 code, e.g. linked with Ubuntu's 32-bit sparc libgcc or glibc); sparc32 here is V8 and the kernel refuses it"
fi
[ "$m" = "$EM" ] || die "ELF machine $m, $ARCH is $EM"

# The initramfs, an uncompressed cpio (newc) with /test; the kernel unpacks it over the built-in
# one (/init, /dev/console).
cpio_entry() { # name mode file|-
	local name=$1 mode=$2 file=$3 size=0 nsize pad
	[ "$file" = - ] || size=$(wc -c < "$file")
	nsize=$((${#name} + 1))
	printf '070701%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X%08X' \
		"$4" "$mode" 0 0 1 0 "$size" 0 0 0 0 "$nsize" 0
	printf '%s\0' "$name"
	pad=$(((4 - (110 + nsize) % 4) % 4))
	head -c "$pad" /dev/zero
	if [ "$file" != - ]; then
		cat "$file"
		head -c $(((4 - size % 4) % 4)) /dev/zero
	fi
}
{
	cpio_entry test $((0100755)) "$WORK/test" 1
	cpio_entry TRAILER!!! 0 - 0
} > "$WORK/test.cpio"

# Boot
append="console=ttyS0 panic=-1 quiet wisp=$MODE"
net=()
export WISP_PORT=''
if [ "$NETWORK" = true ]; then
	append+=" ip=dhcp"
	case "$ARCH" in
	sparc32) nic=lance; append+=" esp_scsi.esp_bus_reset_settle=0 lpj=2000000" ;;
	sparc64) nic=sunhme ;;
	x86_64) nic=e1000 ;;
	esac
	net=(-nic "user,model=$nic")
	if [ -n "$FORWARD" ]; then
		WISP_PORT=$(python3 -c 'import socket
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])')
		net[1]+=",hostfwd=tcp:127.0.0.1:$WISP_PORT-:$FORWARD"
	fi
fi
output port "$WISP_PORT"
[ -z "$ARGS" ] || append="$append -- $ARGS"
# shellcheck disable=SC2206
cmd=("$QEMU" -M "${MACHINE:-$DEF_MACHINE}" -m "$MEM" -display none -serial stdio -monitor none
	-no-reboot -nodefaults -kernel "$KIT/$ARCH/$kernel" "${net[@]}" -initrd "$WORK/test.cpio"
	-append "$append" $QEMU_ARGS)
log "${cmd[*]}"
[ -z "${GITHUB_ACTIONS:-}" ] || echo "::group::Console ($ARCH)"
t0=$(date +%s%N)
rc=0
if [ -n "$CHECK" ]; then
	timeout --kill-after=5 "$TIMEOUT" bash "$HERE/check.sh" "$MODE" "$LOG" "$WORK/check-status" "${cmd[@]}" || rc=$?
	cat "$LOG"
else
	timeout --kill-after=5 "$TIMEOUT" "${cmd[@]}" < /dev/null | tee "$LOG" || rc=$?
fi
t1=$(date +%s%N)
[ -z "${GITHUB_ACTIONS:-}" ] || echo "::endgroup::"
secs=$(awk -v d=$((t1 - t0)) 'BEGIN { printf "%.1f", d / 1e9 }')
output seconds "$secs"

# The result line PID 1 prints (e2e/wisp/init.c, test_mode)
line=$(tr -d '\r' < "$LOG" | grep -oE "WISP-${MODE^^} v=1 exit=-?[0-9]+ signal=[0-9]+ ms=[0-9]+" | tail -n 1 || true)
err=$(tr -d '\r' < "$LOG" | grep -oE "WISP-${MODE^^}-ERROR .*" | head -n 1 || true)
signame() {
	if [ "$ARCH" = x86_64 ]; then
		case $1 in 4) echo SIGILL ;; 5) echo SIGTRAP ;; 6) echo SIGABRT ;; 7) echo SIGBUS ;;
		8) echo SIGFPE ;; 9) echo SIGKILL ;; 11) echo SIGSEGV ;; 31) echo SIGSYS ;; *) echo "signal $1" ;; esac
	else
		case $1 in 4) echo SIGILL ;; 5) echo SIGTRAP ;; 6) echo SIGABRT ;; 7) echo SIGEMT ;;
		8) echo SIGFPE ;; 9) echo SIGKILL ;; 10) echo SIGBUS ;; 11) echo SIGSEGV ;; 12) echo SIGSYS ;;
		*) echo "signal $1" ;; esac
	fi
}
code='' sig=0 name=''
if [ -n "$err" ]; then
	result=error why=${err#*-ERROR }
	case "$why" in
	*"errno 2") why="$why (a dynamic binary? it must be static)" ;;
	*"errno 8") why="$why (a format this kernel doesn't run)" ;;
	esac
elif [ -n "$line" ]; then
	code=$(echo "$line" | sed -E 's/.* exit=(-?[0-9]+) .*/\1/')
	sig=$(echo "$line" | sed -E 's/.* signal=([0-9]+) .*/\1/')
	ms=$(echo "$line" | sed -E 's/.* ms=([0-9]+)$/\1/')
	if [ "$sig" != 0 ]; then
		name=$(signame "$sig") code=
		result=fail why="killed by $name ($sig) after $ms ms"
	elif [ "$code" != 0 ]; then
		result=fail why="exit code $code after $ms ms"
	else
		result=pass why="exit code 0 after $ms ms"
	fi
elif [ "$rc" = 124 ] || [ "$rc" = 137 ]; then
	result=error why="timed out after $TIMEOUT s"
else
	result=error why="no result line (QEMU exit code $rc)"
fi
if [ -n "$CHECK" ] && [ -z "$err" ]; then
	if [ -f "$WORK/check-status" ]; then
		status=$(cat "$WORK/check-status")
		result=pass
		[ "$status" = 0 ] || result=fail
		why="runner check exited with $status"
	elif [ "$rc" != 124 ] && [ "$rc" != 137 ]; then
		result=error why="guest stopped before the runner check"
	else
		result=error why="timed out after $TIMEOUT s"
	fi
fi
output result "$result"
output exit-code "$code"
output signal "$sig"
output signal-name "$name"
log "$ARCH ${MACHINE:-$DEF_MACHINE}: $result, $why; $secs s from starting QEMU"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
	echo "wisp-test $ARCH (\`${MACHINE:-$DEF_MACHINE}\`): **$result**, $why; $secs s from starting QEMU" \
		>> "$GITHUB_STEP_SUMMARY"
fi
case "$result" in
pass) exit 0 ;;
fail)
	[ -z "${GITHUB_ACTIONS:-}" ] || printf '::error title=wisp-test %s::%s\n' "$ARCH" "$why"
	exit 1 ;;
*)
	[ -z "${GITHUB_ACTIONS:-}" ] || printf '::error title=wisp-test %s::%s\n' "$ARCH" "$why"
	exit 2 ;;
esac
