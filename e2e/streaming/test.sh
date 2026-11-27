#!/bin/sh
# Stage 3d end to end: a Moonlight client streams a VM's D-Bus display through Wolf.
#
#   e2e/streaming/test.sh OUTDIR [KERNELS]
#
# Needs only docker (also a remote one through DOCKER_HOST: nothing is bind-mounted from this
# machine; files go in with `docker cp` and the build context) and the repository. Builds the
# images of e2e/streaming/Dockerfile from source (Wolf, moonlight-embedded, our probe client; the
# first build takes 15-30 minutes), then for each run in RUNS:
#
#   node container    the published pve-qemu-kvm with wisp's framebuffer kernel (KERNELS/
#                     kernel-fb-x86_64, or the wisp-fb release's, checked against its SHA256SUMS),
#                     -display dbus on a bus with qemu-server's policy, AC97 on -audiodev dbus,
#                     a USB tablet; Wolf with that VM as its one Moonlight app: qemudbussrc ->
#                     x264enc, qemudbusaudiosrc -> Opus, wolf-input-bridge -> qemu-dbus-input
#   client container  moonlight-embedded pairs with Wolf (a random PIN, entered on the node
#                     with wolf-pair as the operator would), then stream3d.py streams with
#                     wsh-moonlight-probe and checks and measures (see stream3d.py)
#
# RUNS (default "x86_64:30 x86_64:16 x86_64:8", spaces or commas): ARCH:REFRESH_MS, where ARCH is x86_64 (std VGA,
# the shared map), x86_64-gl (the 3dfx binary with -display dbus,gl=on, llvmpipe, dmabufs:
# needs /dev/udmabuf on the Docker host) or x86_64-egl (as x86_64-gl, with qemudbussrc reading
# the dmabufs through EGL, dmabuf-import=egl, as it reads a GPU's tiled ones) and REFRESH_MS the
# D-Bus display's refresh-ms
# (qemu-server's dbus-refresh).
#
# Input: Wolf creates its virtual keyboard and mice through /dev/uinput, so the node container
# gets the Docker host's /dev/uinput and /dev/input (devices 13:*); wolf-input-bridge grabs the
# devices (EVIOCGRAB) so the host's own console doesn't see the test's keys. Without /dev/uinput
# on the Docker host (NO_UINPUT=1 forces it) the keyboard and mouse checks are skipped.
#
# OUTDIR gets summary.txt and per run the probe's log (every frame with its times), the serial
# log, Wolf's log, the bridge's log, the decoded frame and QEMU's screendump, the client's WAV.
# Exit 0 when every check passes. ROUNDS (default 10): latency samples per run. WSH_GST_DEB: a
# wsh-gst-qemu-dbus package to test (e.g. build/wsh-gst-qemu-dbus/*.deb from `make
# wsh-gst-qemu-dbus`) instead of the published one. GST_DEBUG goes to Wolf (wolf.log).
set -eu
OUT=${1:?usage: test.sh OUTDIR [KERNELS]}
KERNELS=${2:-}
RUNS=$(echo "${RUNS:-x86_64:30 x86_64:16 x86_64:8}" | tr ',' ' ')
ROUNDS=${ROUNDS:-10}
TAG=${TAG:-wsh-stream3d}
ID=${ID:-$$}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
NET=$TAG-net-$ID
VOL=$TAG-shared-$ID
CLIENT=$TAG-client-$ID
NODE=$TAG-node-$ID
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
: > "$OUT/summary.txt"
step() { printf '\n== %s\n' "$*"; }
failed=0
CTX=$(mktemp -d)
cleanup() {
	docker rm -f "$NODE" "$CLIENT" > /dev/null 2>&1 || true
	docker network rm "$NET" > /dev/null 2>&1 || true
	docker volume rm "$VOL" > /dev/null 2>&1 || true
	rm -rf "$CTX"
}
trap cleanup EXIT

step "Build context"
cp "$REPO"/e2e/streaming/Dockerfile "$REPO"/e2e/streaming/*.py "$REPO"/e2e/streaming/*.c "$REPO"/e2e/streaming/*.patch \
	"$REPO"/e2e/streaming/wolf-input-bridge "$REPO"/e2e/streaming/wolf-pair "$REPO"/e2e/streaming/wolf-start "$REPO"/e2e/streaming/wsh-wolf.service "$REPO"/e2e/streaming/node.sh "$CTX/"
cp "$REPO/proxmox-archive-keyring-trixie.gpg" "$CTX/"
cp "$REPO/repo/conf/wsh-pve.gpg.key" "$CTX/"
# qemu-server's bus policy, as wsh-dbus-display@<vmid> uses it (from the qemu-server patch)
awk -v f="+++ b/src/usr/dbus-display.conf" '$0 == f { on = 1; next } on && /^diff --git / { exit }
	on && /^@@/ { next } on { sub(/^\+/, ""); print }' "$REPO/submodules/qemu-server.patch" > "$CTX/dbus-display.conf"
grep -q '<busconfig>' "$CTX/dbus-display.conf" || { echo "no bus policy in the qemu-server patch" >&2; exit 1; }
mkdir -p "$CTX/kernels" "$CTX/debs"
if [ -n "${WSH_GST_DEB:-}" ]; then
	cp "$WSH_GST_DEB" "$CTX/debs/"
	echo "wsh-gst-qemu-dbus: $(basename "$WSH_GST_DEB") instead of the published package"
fi
if [ -n "$KERNELS" ]; then
	cp "$KERNELS/kernel-fb-x86_64" "$CTX/kernels/"
else
	base=https://github.com/hwinther/wsh-pve/releases/download/wisp-fb
	curl -fsSL -o "$CTX/kernels/SHA256SUMS" "$base/SHA256SUMS"
	curl -fsSL -o "$CTX/kernels/kernel-fb-x86_64" "$base/kernel-fb-x86_64"
	(cd "$CTX/kernels" && grep ' kernel-fb-x86_64$' SHA256SUMS | sha256sum -c)
fi

step "Images (Wolf, moonlight-embedded and the probe from source)"
docker build --target node -t "$TAG-node" "$CTX"
docker build --target client -t "$TAG-client" "$CTX"

step "Network and client"
docker network create "$NET" > /dev/null
docker volume create "$VOL" > /dev/null
docker run -d --name "$CLIENT" --network "$NET" -v "$VOL:/shared" "$TAG-client" sleep infinity > /dev/null
docker exec "$CLIENT" chmod 1777 /shared

input_args=
skip=
if [ "${NO_UINPUT:-0}" = 1 ] || ! docker run --rm -v /dev:/hostdev:ro "$TAG-client" test -c /hostdev/uinput; then
	echo "no /dev/uinput on the Docker host: keyboard and mouse checks skipped"
	skip=keyboard,mouse
else
	input_args=1
fi

for spec in $RUNS; do
	arch=${spec%%:*}
	refresh=${spec#*:}
	name="$arch-refresh$refresh"
	step "Run $name"
	dev=
	if [ "$arch" = x86_64-gl ] || [ "$arch" = x86_64-egl ]; then
		if docker run --rm -v /dev:/hostdev:ro "$TAG-client" test -c /hostdev/udmabuf; then
			dev="--device /dev/udmabuf"
		else
			echo "SKIP $name: no /dev/udmabuf on the Docker host" | tee -a "$OUT/summary.txt"
			continue
		fi
	fi
	docker rm -f "$NODE" > /dev/null 2>&1 || true
	# shellcheck disable=SC2086 # $dev is words
	docker create --name "$NODE" --network "$NET" --network-alias node -v "$VOL:/shared" \
		-e RUN="$arch" -e REFRESH_MS="$refresh" -e GST_DEBUG="${GST_DEBUG:-2}" $dev \
		${input_args:+--device /dev/uinput "--device-cgroup-rule=c 13:* rmw" -v /dev/input:/dev/input} \
		"$TAG-node" > /dev/null
	docker cp "$CTX/kernels/." "$NODE:/kernels/"
	docker start "$NODE" > /dev/null
	for _ in $(seq 120); do
		docker logs "$NODE" 2>&1 | grep -q "HTTP server listening" && break
		sleep 0.5
	done
	mkdir -p "$OUT/$name"
	if ! docker logs "$NODE" 2>&1 | grep -q "HTTP server listening"; then
		docker logs "$NODE" > "$OUT/$name/wolf.log" 2>&1 || true
		echo "FAIL $name: Wolf didn't start (wolf.log)" | tee -a "$OUT/summary.txt"
		failed=1
		continue
	fi

	# Pairing: the client shows a PIN, the operator enters it on the node (Wolf's API socket)
	pin=$(od -An -N2 -tu2 /dev/urandom | awk '{ printf "%04d", $1 % 10000 }')
	docker exec "$CLIENT" rm -rf /root/.cache/moonlight
	docker exec "$CLIENT" sh -c "moonlight pair -pin $pin node > /tmp/pair.log 2>&1" &
	pair_pid=$!
	if docker exec "$NODE" wolf-pair "$pin" 60 > /dev/null && wait "$pair_pid" &&
		docker exec "$CLIENT" grep -q "Succesfully paired" /tmp/pair.log; then
		echo "PASS $name: pair: moonlight-embedded paired with Wolf (PIN entered on the node)" | tee -a "$OUT/summary.txt"
	else
		docker exec "$CLIENT" cat /tmp/pair.log | grep -v -i pin || true
		echo "FAIL $name: pair: moonlight-embedded didn't pair" | tee -a "$OUT/summary.txt"
		failed=1
		docker logs "$NODE" > "$OUT/$name/wolf.log" 2>&1 || true
		continue
	fi

	docker exec "$CLIENT" rm -rf "/out/$name"
	docker exec "$CLIENT" python3 /usr/local/bin/stream3d.py --node node --keydir /root/.cache/moonlight \
		--app wsh-vm-100 --outdir "/out/$name" --name "$name" --refresh-ms "$refresh" \
		--rounds "$ROUNDS" ${skip:+--skip "$skip"} || failed=1
	docker cp "$CLIENT:/out/$name/." "$OUT/$name/"
	docker exec "$CLIENT" sh -c 'cp /shared/screendump.ppm /out/ 2> /dev/null; rm -f /shared/screendump.ppm' || true
	docker cp "$CLIENT:/out/screendump.ppm" "$OUT/$name/" 2> /dev/null || true
	docker logs "$NODE" > "$OUT/$name/wolf.log" 2>&1 || true
	docker cp "$CLIENT:/shared/wolf-input-bridge.log" "$OUT/$name/" 2> /dev/null || true
	docker exec "$CLIENT" rm -f /shared/wolf-input-bridge.log
	docker cp "$NODE:/out/qemu.log" "$OUT/$name/" 2> /dev/null || true
	cat "$OUT/$name/summary.txt" >> "$OUT/summary.txt" 2> /dev/null || true
	docker rm -f "$NODE" > /dev/null
done

step "Summary"
cat "$OUT/summary.txt"
if [ "$failed" = 0 ] && ! grep -q '^FAIL' "$OUT/summary.txt"; then
	echo "test.sh: all checks passed"
	exit 0
fi
echo "test.sh: some checks failed" >&2
exit 1
