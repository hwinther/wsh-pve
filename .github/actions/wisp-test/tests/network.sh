#!/usr/bin/env bash
# Exercise the public inputs and outputs with a fake serial console.
set -euo pipefail
action=$(cd "$(dirname "$0")/.." && pwd)/wisp-test.sh
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
export WISP_KIT=$tmp/kit WISP_WORK=$tmp/work WISP_INSTALL=false WISP_ARCH=x86_64
export WISP_BINARY=/bin/true PATH="$tmp/bin:$PATH" GITHUB_OUTPUT=$tmp/outputs
mkdir -p bin kit/x86_64
touch kit/x86_64/kernel
echo format=1 > kit/VERSION
cat > bin/qemu-system-x86_64 <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" > invocation
if [[ $* == *wisp=test* ]]; then
    echo 'WISP-TEST v=1 exit=0 signal=0 ms=5'
else
    echo 'ready early'
    echo 'WISP-RUN v=1 start'
    echo 'httpd ready'
    if [ -n "${WISP_CHECK:-}" ]; then sleep 0.1; fi
    echo 'WISP-RUN v=1 exit=7 signal=0 ms=5'
fi
SH
chmod +x bin/qemu-system-x86_64

expect() {
	local want=$1 pattern=$2 rc=0
	shift 2
	: > "$GITHUB_OUTPUT"
	env "$@" bash "$action" > log 2>&1 || rc=$?
	if [ "$rc" != "$want" ] || ! grep -Fq "$pattern" log; then
		cat log >&2
		echo "expected exit $want and '$pattern', got $rc" >&2
		exit 1
	fi
}
expect 0 'exit code 0'
expect 2 'unknown mode' WISP_MODE=service
expect 2 'network must be true or false' WISP_NETWORK=yes
expect 2 'forward requires network' WISP_FORWARD=80
for port in 0 65536 xyz; do
	expect 2 'invalid guest TCP port' WISP_NETWORK=true WISP_FORWARD="$port"
done
expect 2 'ready requires check' WISP_READY=ok
expect 2 'invalid ready regex' WISP_CHECK=true 'WISP_READY=['
expect 2 'run mode requires a format 2 kit' WISP_MODE=run
expect 2 'no x86_64/kernel-net' WISP_NETWORK=true

echo format=2 > kit/VERSION
touch kit/x86_64/kernel-net
export WISP_MODE=run WISP_NETWORK=true WISP_FORWARD=08080
expect 1 'exit code 7'
expect 0 'runner check exited with 0' 'WISP_READY=^httpd ready$' 'WISP_CHECK=echo "$WISP_PORT" > port'
grep -Fx "port=$(cat port)" outputs
grep -Fx "user,model=e1000,hostfwd=tcp:127.0.0.1:$(cat port)-:8080" invocation
grep -Fx "$WISP_KIT/x86_64/kernel-net" invocation
grep -F 'wisp=run ip=dhcp' invocation
expect 1 'runner check exited with 23' 'WISP_CHECK=exit 23'
expect 2 'guest stopped before the runner check' 'WISP_READY=^ready early$' WISP_CHECK=true
expect 2 'timed out after 1 s' WISP_TIMEOUT=1 'WISP_CHECK=sleep 15'
echo 'network input tests passed'
