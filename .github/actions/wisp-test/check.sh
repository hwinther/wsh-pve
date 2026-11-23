#!/usr/bin/env bash
# Called under the same timeout as a normal boot. Drain serial output even while the check runs.
set -euo pipefail
mode=$1 log=$2 status=$3
shift 3
fifo=${status}.fifo
mkfifo "$fifo"
"$@" </dev/null >"$fifo" 2>&1 &
guest=$!
trap 'kill -KILL "$guest" 2>/dev/null || :; wait "$guest" 2>/dev/null || :; rm -f "$fifo"' EXIT
exec 3<"$fifo"
: > "$log"
started=false
while IFS= read -r line <&3; do
	printf '%s\n' "$line" >> "$log"
	line=${line%$'\r'}
	case "$mode:$line" in
	'run:WISP-RUN v=1 start'|'test:WISP-BANNER '*) started=true ;;
	esac
	if [ "$started" = true ] && { [ -z "${WISP_READY:-}" ] || [[ "$line" =~ $WISP_READY ]]; }; then
		cat <&3 >> "$log" &
		drain=$!
		rc=0
		bash -o pipefail -c "$WISP_CHECK" 3<&- || rc=$?
		echo "$rc" > "$status"
		kill "$guest" 2>/dev/null || :
		wait "$guest" || :
		wait "$drain"
		exit 0
	fi
done
wait "$guest"
